"""Unit tests for the P0 factor layer (``quant.factors``).

Covers hand-checked factor values, per-symbol boundaries, future-data
invariance (no leakage), invalid-input rejection, close-time signals, and the
content-addressed feature cache (identity/invalidation and corruption).
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from quant.factors import (  # noqa: E402
    FACTOR_COLUMNS,
    FeatureCache,
    FeatureCacheConflictError,
    FeatureCacheCorruptionError,
    FeatureCacheError,
    FeatureCacheKey,
    FactorValidationError,
    build_signals,
    compute_factors,
    sha256_file,
    source_code_sha256,
    validate_daily_frame,
)

FACTOR_DTYPES = {name: pl.Float64 for name in FACTOR_COLUMNS}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def series(n: int, *, start: float = 10.0, step: float = 0.5) -> list[float]:
    return [start + step * i for i in range(n)]


def make_frame(
    closes: dict[str, list[float | None]],
    *,
    start: date = date(2020, 1, 1),
    high_low: float = 0.02,
    amounts: dict[str, list[float | None]] | None = None,
) -> pl.DataFrame:
    """Build a valid daily frame from explicit per-symbol close paths."""

    rows: list[dict[str, Any]] = []
    for symbol, path in closes.items():
        for i, close in enumerate(path):
            if amounts is None:
                amount: float | None = float(1_000_000 + 1000 * i)
            else:
                raw = amounts[symbol][i]
                amount = None if raw is None else float(raw)
            row: dict[str, Any] = {
                "date": start + timedelta(days=i),
                "symbol": symbol,
                "volume": float(1000 + i),
                "amount": amount,
            }
            if close is None:
                row.update(open=None, high=None, low=None, close=None)
            else:
                row.update(
                    open=close,
                    high=close * (1.0 + high_low),
                    low=close * (1.0 - high_low),
                    close=close,
                )
            rows.append(row)
    return pl.DataFrame(
        rows,
        schema_overrides={
            "date": pl.Date,
            "symbol": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "amount": pl.Float64,
        },
    )


def factor_dict(frame: pl.DataFrame) -> dict[str, list[Any]]:
    return {name: frame[name].to_list() for name in FACTOR_COLUMNS}


def assert_factors_equal(left: pl.DataFrame, right: pl.DataFrame) -> None:
    assert left.height == right.height
    for name in FACTOR_COLUMNS:
        assert left[name].to_list() == right[name].to_list(), f"factor {name} differs"


# --------------------------------------------------------------------------- #
# compute_factors: hand calculation
# --------------------------------------------------------------------------- #
def test_compute_factors_hand_calculated_values() -> None:
    closes = series(25, start=10.0, step=0.5)
    amounts = [float(1_000_000 + 1000 * i) for i in range(25)]
    frame = make_frame({"a": closes}, high_low=0.02)
    out = compute_factors(frame)

    values = factor_dict(out)
    ret1 = [None] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, 25)]

    for i in range(25):
        assert values["ret_1"][i] == pytest.approx(ret1[i], rel=1e-12, abs=1e-15)

    for i in range(25):
        expected = None if i < 5 else closes[i] / closes[i - 5] - 1.0
        assert values["ret_5"][i] == pytest.approx(expected, rel=1e-12, abs=1e-15)

    for i in range(25):
        expected = None if i < 20 else closes[i] / closes[i - 20] - 1.0
        assert values["ret_20"][i] == pytest.approx(expected, rel=1e-12, abs=1e-15)

    for i in range(25):
        expected = None if i < 19 else statistics.fmean(closes[i - 19 : i + 1])
        assert values["sma_20"][i] == pytest.approx(expected, rel=1e-12, abs=1e-15)

    for i in range(25):
        expected = None if i < 19 else statistics.fmean(amounts[i - 19 : i + 1])
        assert values["amount_mean_20"][i] == pytest.approx(expected, rel=1e-12, abs=1e-9)

    for i in range(25):
        if i < 20:
            assert values["volatility_20"][i] is None
        else:
            expected = statistics.stdev(ret1[i - 19 : i + 1])
            assert values["volatility_20"][i] == pytest.approx(expected, rel=1e-12)

    for i in range(25):
        expected = (closes[i] * 1.02 - closes[i] * 0.98) / closes[i]
        assert values["range_pct"][i] == pytest.approx(expected, rel=1e-12, abs=1e-15)


def test_compute_factors_warmup_nulls_and_no_inf() -> None:
    frame = make_frame({"a": series(21)})
    out = compute_factors(frame)
    values = factor_dict(out)

    assert values["ret_1"][0] is None
    assert values["ret_5"][:5] == [None] * 5
    assert values["ret_20"][:20] == [None] * 20
    assert values["sma_20"][:19] == [None] * 19
    assert values["amount_mean_20"][:19] == [None] * 19
    assert values["volatility_20"][:20] == [None] * 20
    assert values["range_pct"][0] is not None

    # incomplete warm-up is allowed, but no value may be infinite
    for name in FACTOR_COLUMNS:
        infinite = out[name].is_infinite().fill_null(False)
        assert not bool(infinite.any()), name


def test_compute_factors_preserves_original_columns_and_order() -> None:
    frame = make_frame({"a": series(25)}).with_columns(
        pl.lit(1.0).alias("adj_factor")
    )
    out = compute_factors(frame)
    # exact order: every original column first, then the seven factors
    assert out.columns == list(frame.columns) + list(FACTOR_COLUMNS)
    assert out.schema["adj_factor"] == pl.Float64
    assert dict(out.select(FACTOR_COLUMNS).schema) == FACTOR_DTYPES
    assert out["close"].to_list() == frame["close"].to_list()


def test_compute_factors_is_deterministic() -> None:
    frame = make_frame({"a": series(30), "b": series(30, start=5.0, step=0.25)})
    assert_factors_equal(compute_factors(frame), compute_factors(frame))


def test_compute_factors_accepts_integer_and_float32_inputs() -> None:
    frame = make_frame({"a": series(25)}).with_columns(
        pl.col("close").cast(pl.Float32),
        pl.col("volume").cast(pl.Int64),
        pl.col("amount").cast(pl.Int64),
    )
    out = compute_factors(frame)
    assert dict(out.select(FACTOR_COLUMNS).schema) == FACTOR_DTYPES
    assert out.schema["volume"] == pl.Int64


def test_compute_factors_handles_empty_frame() -> None:
    frame = make_frame({"a": series(3)}).clear()
    out = compute_factors(frame)
    assert out.height == 0
    assert out.columns == list(frame.columns) + list(FACTOR_COLUMNS)


# --------------------------------------------------------------------------- #
# nulls and missing data
# --------------------------------------------------------------------------- #
def test_nulls_are_preserved_not_filled() -> None:
    closes: list[float | None] = series(35)
    closes[10] = None
    frame = make_frame({"a": closes})
    out = compute_factors(frame)

    assert out["close"].to_list()[10] is None
    values = factor_dict(out)
    assert values["range_pct"][10] is None
    assert values["ret_1"][10] is None
    # next row uses a null denominator, so it stays null instead of a stale value
    assert values["ret_1"][11] is None
    assert values["ret_5"][15] is None
    # windows containing the missing row are null, later windows recover
    assert values["sma_20"][19] is None
    assert values["sma_20"][29] is None
    assert values["sma_20"][30] is not None
    assert values["amount_mean_20"][19] is not None
    for name in FACTOR_COLUMNS:
        infinite = out[name].is_infinite().fill_null(False)
        assert not bool(infinite.any()), name


def test_null_amount_propagates_to_amount_mean_only() -> None:
    amounts = [float(1_000_000 + i) for i in range(30)]
    amounts[7] = None
    frame = make_frame({"a": series(30)}, amounts={"a": amounts})
    out = compute_factors(frame)
    assert out["amount_mean_20"][19] is None
    assert out["amount_mean_20"][20] is None
    # index 26 still has the missing row in its 20-row window, index 27 does not
    assert out["amount_mean_20"][26] is None
    assert out["amount_mean_20"][27] is not None
    assert out["sma_20"][19] is not None


# --------------------------------------------------------------------------- #
# symbol boundaries
# --------------------------------------------------------------------------- #
def test_symbol_windows_do_not_cross_boundaries() -> None:
    a = series(25, start=10.0, step=0.5)
    b = series(25, start=100.0, step=-1.0)
    both = make_frame({"a": a, "b": b})
    out = compute_factors(both)
    b_part = out.filter(pl.col("symbol") == "b")

    # first row of b must not inherit a's last close
    assert b_part["ret_1"][0] is None
    assert b_part["ret_5"][0] is None
    assert b_part["sma_20"][0] is None
    assert b_part["ret_1"][1] == pytest.approx(b[1] / b[0] - 1.0, rel=1e-12)
    expected_b_ret5 = b[5] / b[0] - 1.0
    assert b_part["ret_5"][5] == pytest.approx(expected_b_ret5, rel=1e-12)
    assert b_part["sma_20"][19] == pytest.approx(statistics.fmean(b[:20]), rel=1e-12)

    # each symbol computed alone gives identical values
    solo_a = compute_factors(make_frame({"a": a}))
    solo_b = compute_factors(make_frame({"b": b}))
    assert_factors_equal(out.filter(pl.col("symbol") == "a"), solo_a)
    assert_factors_equal(b_part, solo_b)


def test_symbols_with_different_history_lengths() -> None:
    frame = make_frame({"a": series(30), "b": series(12)})
    out = compute_factors(frame)
    b_part = out.filter(pl.col("symbol") == "b")
    assert b_part.height == 12
    assert b_part["sma_20"].to_list() == [None] * 12
    assert b_part["ret_5"][5] is not None
    assert b_part["ret_20"].to_list() == [None] * 12


# --------------------------------------------------------------------------- #
# future-data invariance (no leakage)
# --------------------------------------------------------------------------- #
def test_future_append_does_not_change_earlier_factors() -> None:
    closes = series(24)
    short = make_frame({"a": closes[:12], "b": series(12, start=4.0)})
    long = make_frame({"a": closes, "b": series(24, start=4.0)})
    cutoff = short["date"].max()

    f_short = compute_factors(short)
    f_prefix = compute_factors(long.filter(pl.col("date") <= cutoff))
    assert_factors_equal(f_short, f_prefix)
    assert f_prefix.height == f_short.height

    f_full = compute_factors(long)
    assert_factors_equal(
        f_full.filter(pl.col("date") <= cutoff).select(FACTOR_COLUMNS),
        f_short.select(FACTOR_COLUMNS),
    )


def test_mutating_future_prices_does_not_change_earlier_factors() -> None:
    long = make_frame({"a": series(24)})
    cutoff = long["date"][11]
    mutated = long.with_columns(
        pl.when(pl.col("date") > cutoff)
        .then(pl.col("close") * 50.0)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    baseline = compute_factors(long.filter(pl.col("date") <= cutoff))
    after = compute_factors(mutated).filter(pl.col("date") <= cutoff)
    assert_factors_equal(baseline, after.select(baseline.columns))


def test_signal_values_do_not_change_with_future_data() -> None:
    long = make_frame({"a": series(30)})
    cutoff = long["date"][19]
    mutated = long.with_columns(
        pl.when(pl.col("date") > cutoff)
        .then(pl.col("close") * 100.0)
        .otherwise(pl.col("close"))
        .alias("close")
    )
    baseline = build_signals(long.filter(pl.col("date") <= cutoff))
    after = build_signals(mutated).filter(pl.col("date") <= cutoff)
    for name in ("above_sma_20", "ret_5_positive", "signal"):
        assert baseline[name].to_list() == after[name].to_list()


# --------------------------------------------------------------------------- #
# invalid inputs
# --------------------------------------------------------------------------- #
VALID = make_frame({"a": series(25)})


@pytest.mark.parametrize(
    "mutator, keyword",
    [
        (lambda df: df.drop("amount"), "missing"),
        (lambda df: df.drop("close"), "missing"),
        (lambda df: df.with_columns(pl.col("date").cast(pl.String)), "dtype"),
        (
            lambda df: df.with_columns(pl.int_range(pl.len()).alias("symbol")),
            "dtype",
        ),
        (
            lambda df: df.with_columns(
                pl.when(pl.col("close") == 11.0).then(0.0).otherwise(pl.col("close")).alias("close")
            ),
            "strictly positive",
        ),
        (
            lambda df: df.with_columns(pl.lit(-1.0).alias("close")),
            "strictly positive",
        ),
        (
            lambda df: df.with_columns(pl.lit(float("inf")).alias("close")),
            "non-finite",
        ),
        (
            lambda df: df.with_columns(pl.lit(float("-inf")).alias("amount")),
            "non-finite",
        ),
        (
            lambda df: df.with_columns(pl.lit(float("nan")).alias("high")),
            "non-finite",
        ),
        (
            lambda df: df.with_columns(pl.lit(-5.0).alias("volume")),
            "non-negative",
        ),
    ],
)
def test_invalid_values_raise(mutator: Any, keyword: str) -> None:
    with pytest.raises(FactorValidationError, match=keyword):
        compute_factors(mutator(VALID))


def test_invalid_inputs_raise() -> None:
    with pytest.raises(FactorValidationError, match="duplicate"):
        compute_factors(pl.concat([VALID, VALID.head(1)]))

    unsorted = VALID.sort(["symbol", "date"], descending=[False, True])
    with pytest.raises(FactorValidationError, match="sorted"):
        compute_factors(unsorted)

    interleaved = pl.concat(
        [VALID.head(3), VALID.slice(5, 1), VALID.slice(3, 2), VALID.slice(6)]
    )
    with pytest.raises(FactorValidationError, match="sorted"):
        compute_factors(interleaved)

    null_symbol = VALID.with_columns(
        pl.when(pl.col("date") == VALID["date"][0])
        .then(pl.lit(None, dtype=pl.String))
        .otherwise(pl.col("symbol"))
        .alias("symbol")
    )
    with pytest.raises(FactorValidationError, match="null"):
        compute_factors(null_symbol)

    with pytest.raises(TypeError):
        compute_factors({"date": []})  # type: ignore[arg-type]


def test_validate_daily_frame_require_sorted_escape_hatch() -> None:
    unsorted = VALID.sort(["symbol", "date"], descending=[False, True])
    with pytest.raises(FactorValidationError):
        validate_daily_frame(unsorted)
    validate_daily_frame(unsorted, require_sorted=False)


# --------------------------------------------------------------------------- #
# build_signals
# --------------------------------------------------------------------------- #
def test_build_signals_hand_checked_and_null_warmup() -> None:
    closes = series(25)
    frame = make_frame({"a": closes})
    out = build_signals(frame)

    for name in ("above_sma_20", "ret_5_positive", "signal"):
        assert name in out.columns
        assert out.schema[name] == pl.Boolean

    values = out.select(["sma_20", "ret_5", "above_sma_20", "ret_5_positive", "signal"]).to_dicts()
    for i, row in enumerate(values):
        expected_above = None if row["sma_20"] is None else closes[i] > row["sma_20"]
        expected_positive = None if row["ret_5"] is None else row["ret_5"] > 0
        assert row["above_sma_20"] is expected_above
        assert row["ret_5_positive"] is expected_positive
        # Kleene logic: unknown AND false is false, otherwise unknown stays unknown
        if expected_above is None:
            expected_signal = False if expected_positive is False else None
        elif expected_positive is None:
            expected_signal = False if expected_above is False else None
        else:
            expected_signal = expected_above and expected_positive
        assert row["signal"] is expected_signal


def test_build_signals_triggers_on_rising_then_flat_series() -> None:
    rising = series(30, start=10.0, step=0.5)
    frame = make_frame({"a": rising})
    out = build_signals(frame)
    # close above its own 20-day mean and positive 5-day return
    assert out["signal"][20] is True
    assert out["above_sma_20"][20] is True
    assert out["ret_5_positive"][20] is True

    falling = [20.0 - 0.5 * i for i in range(30)]
    out_falling = build_signals(make_frame({"a": falling}))
    assert out_falling["signal"][25] is False


def test_build_signals_custom_windows_and_columns() -> None:
    closes = series(15)
    frame = make_frame({"a": closes})
    out = build_signals(frame, sma_window=5, ret_window=2, signal_column="entry")
    assert {"sma_5", "ret_2", "above_sma_5", "ret_2_positive", "entry"} <= set(out.columns)
    assert out["sma_5"][4] == pytest.approx(statistics.fmean(closes[:5]), rel=1e-12)
    assert out["ret_2"][2] == pytest.approx(closes[2] / closes[0] - 1.0, rel=1e-12)
    assert out.schema["entry"] == pl.Boolean


def test_build_signals_rejects_bad_windows() -> None:
    frame = make_frame({"a": series(10)})
    with pytest.raises(ValueError):
        build_signals(frame, sma_window=0)
    with pytest.raises(ValueError):
        build_signals(frame, ret_window=-1)


def test_build_signals_reuses_preexisting_factor_columns() -> None:
    frame = compute_factors(make_frame({"a": series(25)}))
    out = build_signals(frame)
    assert out["sma_20"].to_list() == frame["sma_20"].to_list()
    assert out["ret_5"].to_list() == frame["ret_5"].to_list()


# --------------------------------------------------------------------------- #
# feature cache: identity
# --------------------------------------------------------------------------- #
SOURCE_SHA = "a" * 64
DATASET_SHA = "b" * 64


def make_cache(root: Path, *, source_sha256: str = SOURCE_SHA) -> FeatureCache:
    return FeatureCache(root, source_sha256=source_sha256)


def make_key(cache: FeatureCache, frame: pl.DataFrame, **overrides: Any) -> FeatureCacheKey:
    kwargs: dict[str, Any] = {
        "dataset_id": "ds-daily-2015-2024",
        "dataset_sha256": DATASET_SHA,
        "adjustment": "none",
        "missing": "preserve",
    }
    kwargs.update(overrides)
    return cache.key_for_frame(frame, **kwargs)


def explicit_key(cache: FeatureCache, frame: pl.DataFrame, **overrides: Any) -> FeatureCacheKey:
    """Build a key from explicitly supplied fields (universe/date range included)."""

    dates = frame["date"]
    kwargs: dict[str, Any] = {
        "dataset_id": "ds-daily-2015-2024",
        "dataset_sha256": DATASET_SHA,
        "universe": frame["symbol"].unique().sort().to_list(),
        "date_start": str(dates.min()),
        "date_end": str(dates.max()),
        "adjustment": "none",
        "missing": "preserve",
    }
    kwargs.update(overrides)
    return cache.key_for(**kwargs)


def test_key_identity_is_stable_and_complete(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    base = make_key(cache, frame)
    assert base.feature_set_id().startswith("fset-")
    assert base == make_key(cache, frame)
    assert base.feature_set_id() == make_key(cache, frame).feature_set_id()
    # key_for_frame and an explicit key with the same fields are identical
    assert base == explicit_key(cache, frame)

    universe = frame["symbol"].unique().sort().to_list()
    assert base.universe == tuple(universe)
    assert base.date_start == str(frame["date"].min())
    assert base.date_end == str(frame["date"].max())

    variants = {
        "dataset_id": explicit_key(cache, frame, dataset_id="ds-other"),
        "dataset_sha256": explicit_key(cache, frame, dataset_sha256="c" * 64),
        "params": explicit_key(cache, frame, params={"sma_window": 10}),
        "adjustment": explicit_key(cache, frame, adjustment="qfq"),
        "missing": explicit_key(cache, frame, missing="forward_fill"),
        "universe": explicit_key(cache, frame, universe=("a", "b")),
        "date_start": explicit_key(cache, frame, date_start="2019-01-01"),
        "date_end": explicit_key(cache, frame, date_end="2021-01-01"),
        "source_sha256": make_cache(
            tmp_path / "features", source_sha256="d" * 64
        ).key_for_frame(frame, dataset_id="ds-daily-2015-2024", dataset_sha256=DATASET_SHA),
    }
    ids = {base.feature_set_id()} | {
        key.feature_set_id() for key in variants.values()
    }
    assert len(ids) == len(variants) + 1, "every identity component must change the key"


def test_key_params_are_canonical(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    left = explicit_key(cache, frame, params={"b": [2, 1], "a": {"z": 1, "y": 2}})
    right = explicit_key(cache, frame, params={"a": {"y": 2, "z": 1}, "b": (2, 1)})
    assert left.feature_set_id() == right.feature_set_id()
    different = explicit_key(cache, frame, params={"a": {"y": 2, "z": 1}, "b": [1, 2]})
    assert different.feature_set_id() != left.feature_set_id()


def test_key_rejects_bad_identity(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(10)})
    with pytest.raises(FeatureCacheError):
        explicit_key(cache, frame, dataset_sha256="not-a-sha")
    with pytest.raises(FeatureCacheError):
        explicit_key(cache, frame, dataset_id="  ")
    with pytest.raises(FeatureCacheError):
        explicit_key(cache, frame, universe=("a", "a"))
    with pytest.raises(FeatureCacheError):
        explicit_key(cache, frame, params={"bad": object()})
    with pytest.raises(FeatureCacheError):
        explicit_key(cache, frame, adjustment="")


def test_source_code_sha256_tracks_file_content(tmp_path: Path) -> None:
    first = tmp_path / "core.py"
    second = tmp_path / "signals.py"
    first.write_text("x = 1\n", encoding="utf-8")
    second.write_text("y = 2\n", encoding="utf-8")

    digest = source_code_sha256([first, second])
    assert len(digest) == 64
    assert digest == source_code_sha256([second, first])  # path order independent
    assert digest != source_code_sha256([first])

    first.write_text("x = 2\n", encoding="utf-8")
    assert source_code_sha256([first, second]) != digest

    default = source_code_sha256()
    assert len(default) == 64
    assert default == source_code_sha256()

    with pytest.raises(FeatureCacheError):
        source_code_sha256([tmp_path / "missing.py"])


def test_cache_uses_real_source_digest_for_identity(tmp_path: Path) -> None:
    source = tmp_path / "core.py"
    source.write_text("value = 1\n", encoding="utf-8")
    frame = make_frame({"a": series(25)})

    first = FeatureCache(tmp_path / "features", source_files=[source])
    second = FeatureCache(tmp_path / "features", source_files=[source])
    assert first.source_sha256 == second.source_sha256

    key_before = first.key_for_frame(
        frame, dataset_id="ds", dataset_sha256=DATASET_SHA
    )
    source.write_text("value = 2\n", encoding="utf-8")
    third = FeatureCache(tmp_path / "features", source_files=[source])
    key_after = third.key_for_frame(frame, dataset_id="ds", dataset_sha256=DATASET_SHA)
    assert key_before.feature_set_id() != key_after.feature_set_id()


# --------------------------------------------------------------------------- #
# feature cache: store / load / verify
# --------------------------------------------------------------------------- #
def test_cache_roundtrip_and_manifest(tmp_path: Path) -> None:
    root = tmp_path / "features"
    cache = make_cache(root)
    frame = make_frame({"a": series(25), "b": series(25, start=3.0)})
    features = compute_factors(frame)
    key = make_key(cache, frame)

    assert cache.get(key) is None

    result = cache.get_or_compute(key, lambda: features)
    assert (result.hit, result.rebuilt) == (False, False)
    assert result.path.parent == root
    assert result.path.name == key.feature_set_id()
    assert result.features.equals(features)

    hit = cache.get(key)
    assert hit is not None
    assert hit.hit is True
    assert hit.path == result.path
    assert hit.features.equals(features)

    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["key_sha256"] == key.key_sha256()
    assert manifest["key"] == key.canonical()
    assert manifest["source_sha256"] == SOURCE_SHA
    assert manifest["dataset"]["sha256"] == DATASET_SHA
    assert manifest["adjustment"] == "none"
    assert manifest["missing"] == "preserve"
    assert manifest["sorted_by"] == ["symbol", "date"]
    assert manifest["parquet_sha256"] == sha256_file(result.path / "features.parquet")
    assert manifest["row_count"] == features.height
    assert manifest["columns"] == features.columns
    assert sorted(manifest["factors"]) == sorted(FACTOR_COLUMNS)
    assert manifest["rebuild"] is None


def test_cache_hit_recomputes_nothing(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    key = make_key(cache, frame)
    calls = {"n": 0}

    def compute() -> pl.DataFrame:
        calls["n"] += 1
        return compute_factors(frame)

    first = cache.get_or_compute(key, compute)
    second = cache.get_or_compute(key, compute)
    assert calls["n"] == 1
    assert first.hit is False and second.hit is True


def test_cache_dataset_and_config_invalidation(tmp_path: Path) -> None:
    root = tmp_path / "features"
    cache = make_cache(root)
    frame = make_frame({"a": series(25)})
    features = compute_factors(frame)

    base = make_key(cache, frame)
    others = {
        "dataset": explicit_key(cache, frame, dataset_sha256="e" * 64),
        "dataset_id": explicit_key(cache, frame, dataset_id="ds-v2"),
        "params": explicit_key(cache, frame, params={"sma_window": 10}),
        "universe": explicit_key(cache, frame, universe=("a", "zzz")),
        "dates": explicit_key(cache, frame, date_start="2019-06-01"),
        "adjustment": explicit_key(cache, frame, adjustment="hfq"),
        "missing": explicit_key(cache, frame, missing="drop"),
    }

    stored = cache.get_or_compute(base, lambda: features)
    assert cache.get(base) is not None
    for name, key in others.items():
        assert key.feature_set_id() != base.feature_set_id(), name
        assert cache.get(key) is None, name
        assert not cache.directory_for(key).exists(), name

    # recomputing under a new identity creates a new directory, not a rewrite
    other_stored = cache.get_or_compute(others["dataset"], lambda: features)
    assert other_stored.path != stored.path
    assert stored.path.is_dir() and other_stored.path.is_dir()


def test_cache_put_is_idempotent_and_conflicts_are_rejected(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    key = make_key(cache, frame)
    features = compute_factors(frame)

    first = cache.put(key, features)
    second = cache.put(key, compute_factors(frame))
    assert first == second

    different_frame = make_frame({"a": series(25, start=7.0, step=0.9)})
    with pytest.raises(FeatureCacheConflictError):
        cache.put(key, compute_factors(different_frame))


def test_cache_put_validates_frame(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    key = make_key(cache, frame)
    with pytest.raises((FactorValidationError, FeatureCacheError)):
        cache.put(key, frame)  # no factor columns
    with pytest.raises(FactorValidationError):
        cache.put(key, compute_factors(frame).sort(["symbol", "date"], descending=[False, True]))


def test_cache_corruption_truncated_parquet_is_rebuilt_not_accepted(tmp_path: Path) -> None:
    root = tmp_path / "features"
    cache = make_cache(root)
    frame = make_frame({"a": series(25)})
    features = compute_factors(frame)
    key = make_key(cache, frame)

    stored = cache.get_or_compute(key, lambda: features)
    data_path = stored.path / "features.parquet"
    data_path.write_bytes(data_path.read_bytes()[:32])
    corrupted_bytes = data_path.read_bytes()

    with pytest.raises(FeatureCacheCorruptionError):
        cache.get(key)

    rebuilt = cache.get_or_compute(key, lambda: compute_factors(frame))
    assert rebuilt.rebuilt is True
    assert rebuilt.hit is False
    assert rebuilt.path != stored.path
    assert rebuilt.features.equals(features)

    # corrupt entry is preserved as-is, never overwritten or deleted
    assert data_path.read_bytes() == corrupted_bytes
    manifest = json.loads((rebuilt.path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["rebuild"] is not None
    assert manifest["rebuilt_from"] == stored.path.name

    # later hits use the valid rebuild instead of recomputing forever
    hit = cache.get(key)
    assert hit is not None and hit.hit is True
    assert hit.path == rebuilt.path
    assert hit.features.equals(features)


def test_cache_corruption_single_byte_tamper_is_detected(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    features = compute_factors(frame)
    key = make_key(cache, frame)
    stored = cache.get_or_compute(key, lambda: features)

    data_path = stored.path / "features.parquet"
    raw = bytearray(data_path.read_bytes())
    raw[len(raw) // 2] ^= 0xFF
    data_path.write_bytes(bytes(raw))

    with pytest.raises(FeatureCacheCorruptionError, match="sha256"):
        cache.get(key)


def test_cache_corruption_manifest_cases(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    features = compute_factors(frame)
    key = make_key(cache, frame)
    stored = cache.get_or_compute(key, lambda: features)
    manifest_path = stored.path / "manifest.json"
    original = manifest_path.read_text(encoding="utf-8")

    manifest_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(FeatureCacheCorruptionError, match="manifest"):
        cache.get(key)

    manifest_path.unlink()
    with pytest.raises(FeatureCacheCorruptionError, match="missing"):
        cache.get(key)

    manifest = json.loads(original)
    manifest["key_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FeatureCacheCorruptionError, match="identity"):
        cache.get(key)

    manifest = json.loads(original)
    manifest["parquet_sha256"] = "1" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FeatureCacheCorruptionError, match="sha256"):
        cache.get(key)

    manifest = json.loads(original)
    manifest["row_count"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(FeatureCacheCorruptionError):
        cache.get(key)


def test_cache_corruption_rebuild_keeps_every_attempt(tmp_path: Path) -> None:
    root = tmp_path / "features"
    cache = make_cache(root)
    frame = make_frame({"a": series(25)})
    features = compute_factors(frame)
    key = make_key(cache, frame)

    stored = cache.put(key, features)
    paths = {stored.name}
    for _ in range(2):
        # corrupt every existing candidate for this identity, then rebuild
        candidates = list(root.glob(f"{key.feature_set_id()}*"))
        assert candidates
        for directory in candidates:
            data_path = directory / "features.parquet"
            data_path.write_bytes(data_path.read_bytes()[:16])
        with pytest.raises(FeatureCacheCorruptionError):
            cache.get(key)
        result = cache.get_or_compute(key, lambda: compute_factors(frame))
        assert result.rebuilt is True
        paths.add(result.path.name)
    assert len(paths) == 3
    assert stored.is_dir()  # the original corrupt entry still exists


def test_cache_rejects_key_that_does_not_match_manifest(tmp_path: Path) -> None:
    cache = make_cache(tmp_path / "features")
    frame = make_frame({"a": series(25)})
    features = compute_factors(frame)
    key = make_key(cache, frame)
    stored = cache.get_or_compute(key, lambda: features)

    other_key = make_key(cache, frame, dataset_sha256="f" * 64)
    assert other_key.feature_set_id() != key.feature_set_id()
    assert cache.get(other_key) is None
    assert cache.root == tmp_path / "features"
    assert stored.path.is_dir()


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "blob.bin"
    payload = b"quant-factors" * 1000
    path.write_bytes(payload)
    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()
