"""Backward-looking daily price/volume factors.

Contract
--------
Input is a Polars ``DataFrame`` with columns::

    date (Date), symbol (str), open/high/low/close (numeric),
    volume (numeric), amount (numeric)

The frame must use ``(symbol, date)`` as a unique key and must already be
sorted ascending by ``(symbol, date)``.  Every factor is computed with
backward-looking windows only: the value at row ``t`` depends on rows
``<= t`` of the same symbol and never on later rows.  Appending newer rows
therefore leaves all previously computed values bit-for-bit unchanged.

Missing values (``null``) are preserved, not filled.  Warm-up rows where a
window is not yet complete return ``null``.  Non-finite inputs (``nan`` or
``inf``) and non-positive prices are rejected.  Factor outputs are always
``Float64`` and never infinite.
"""

from __future__ import annotations

from typing import Any, Final

import polars as pl

__all__ = [
    "DEFAULT_FACTOR_PARAMS",
    "FACTOR_COLUMNS",
    "KEY_COLUMNS",
    "NUMERIC_COLUMNS",
    "PRICE_COLUMNS",
    "REQUIRED_COLUMNS",
    "FactorComputationError",
    "FactorError",
    "FactorValidationError",
    "compute_factors",
    "default_factor_params",
    "validate_daily_frame",
]

KEY_COLUMNS: Final[tuple[str, ...]] = ("symbol", "date")
PRICE_COLUMNS: Final[tuple[str, ...]] = ("open", "high", "low", "close")
VOLUME_COLUMNS: Final[tuple[str, ...]] = ("volume", "amount")
NUMERIC_COLUMNS: Final[tuple[str, ...]] = PRICE_COLUMNS + VOLUME_COLUMNS
REQUIRED_COLUMNS: Final[tuple[str, ...]] = ("date", "symbol") + NUMERIC_COLUMNS

#: Factor columns produced by :func:`compute_factors`, in output order.
FACTOR_COLUMNS: Final[tuple[str, ...]] = (
    "ret_1",
    "ret_5",
    "ret_20",
    "volatility_20",
    "amount_mean_20",
    "sma_20",
    "range_pct",
)

#: Fixed window parameters of :func:`compute_factors`.  This mapping is also
#: the default ``params`` component of a feature cache key, so changing a
#: window changes the cache identity (JSON-serialisable by design).
DEFAULT_FACTOR_PARAMS: Final[dict[str, Any]] = {
    "ret_windows": [1, 5, 20],
    "volatility_window": 20,
    "volatility_ddof": 1,
    "amount_mean_window": 20,
    "sma_window": 20,
    "range_pct_definition": "(high-low)/close",
    "missing": "preserve",
}


class FactorError(Exception):
    """Base class for factor layer errors."""


class FactorValidationError(FactorError, ValueError):
    """Raised when the input frame does not satisfy the documented contract."""


class FactorComputationError(FactorError):
    """Raised when a computed factor violates an internal invariant."""


def default_factor_params() -> dict[str, Any]:
    """Return a fresh copy of :data:`DEFAULT_FACTOR_PARAMS`."""

    return {
        "ret_windows": list(DEFAULT_FACTOR_PARAMS["ret_windows"]),
        "volatility_window": DEFAULT_FACTOR_PARAMS["volatility_window"],
        "volatility_ddof": DEFAULT_FACTOR_PARAMS["volatility_ddof"],
        "amount_mean_window": DEFAULT_FACTOR_PARAMS["amount_mean_window"],
        "sma_window": DEFAULT_FACTOR_PARAMS["sma_window"],
        "range_pct_definition": DEFAULT_FACTOR_PARAMS["range_pct_definition"],
        "missing": DEFAULT_FACTOR_PARAMS["missing"],
    }


def _count_true(expr: pl.Expr) -> int:
    return int(expr.cast(pl.Int64).sum())


def validate_daily_frame(df: pl.DataFrame, *, require_sorted: bool = True) -> None:
    """Validate a daily OHLCV frame against the factor contract.

    Raises :class:`FactorValidationError` (a ``ValueError`` subclass) on the
    first violated rule.  ``TypeError`` is raised when ``df`` is not a Polars
    ``DataFrame``.  Nulls are allowed and preserved; ``nan``/``inf`` are not.
    """

    if not isinstance(df, pl.DataFrame):
        raise TypeError(f"expected polars.DataFrame, got {type(df).__name__}")

    missing = [name for name in REQUIRED_COLUMNS if name not in df.columns]
    if missing:
        raise FactorValidationError(f"missing required columns: {missing}")

    if df.schema["date"] != pl.Date:
        raise FactorValidationError(
            f"column 'date' must have dtype Date, got {df.schema['date']}"
        )
    if df.schema["symbol"] != pl.String:
        raise FactorValidationError(
            f"column 'symbol' must have dtype String, got {df.schema['symbol']}"
        )
    for name in NUMERIC_COLUMNS:
        if not df.schema[name].is_numeric():
            raise FactorValidationError(
                f"column {name!r} must be numeric, got {df.schema[name]}"
            )

    for name in KEY_COLUMNS:
        nulls = int(df[name].null_count())
        if nulls:
            raise FactorValidationError(
                f"key column {name!r} contains {nulls} null value(s)"
            )

    duplicates = (
        df.group_by(list(KEY_COLUMNS))
        .len()
        .filter(pl.col("len") > 1)
        .sort("len", descending=True)
    )
    if duplicates.height:
        examples = duplicates.head(5).to_dicts()
        raise FactorValidationError(
            f"duplicate (symbol, date) keys: {duplicates.height} key(s) repeated; "
            f"examples: {examples}"
        )

    if require_sorted:
        symbols_sorted = bool(df["symbol"].is_sorted())
        dates_sorted = bool(
            df.select(pl.col("date").is_sorted().over("symbol").all()).item()
        )
        if not (symbols_sorted and dates_sorted):
            raise FactorValidationError(
                "frame must be sorted ascending by (symbol, date)"
            )

    # Non-finite check first so positivity messages only ever see real numbers.
    for name in NUMERIC_COLUMNS:
        finite = df[name].cast(pl.Float64).is_finite().fill_null(True)
        if not bool(finite.all()):
            bad = df.filter(~finite)
            raise FactorValidationError(
                f"column {name!r} contains non-finite value(s) (nan/inf); "
                f"row example: {bad.head(1).to_dicts()}"
            )

    for name in PRICE_COLUMNS:
        invalid = (df[name].cast(pl.Float64) <= 0).fill_null(False)
        if bool(invalid.any()):
            raise FactorValidationError(
                f"price column {name!r} must be strictly positive; "
                f"found {_count_true(invalid)} invalid value(s)"
            )

    for name in VOLUME_COLUMNS:
        invalid = (df[name].cast(pl.Float64) < 0).fill_null(False)
        if bool(invalid.any()):
            raise FactorValidationError(
                f"column {name!r} must be non-negative; "
                f"found {_count_true(invalid)} invalid value(s)"
            )


def _assert_no_infinite(df: pl.DataFrame) -> None:
    for name in FACTOR_COLUMNS:
        column = df[name]
        if column.dtype != pl.Float64:
            raise FactorComputationError(
                f"factor {name!r} must be Float64, got {column.dtype}"
            )
        infinite = column.is_infinite().fill_null(False)
        if bool(infinite.any()):
            raise FactorComputationError(
                f"factor {name!r} produced {_count_true(infinite)} infinite value(s)"
            )


def compute_factors(df: pl.DataFrame) -> pl.DataFrame:
    """Return ``df`` with the seven backward-looking factors appended.

    Columns added, in order: ``ret_1``, ``ret_5``, ``ret_20``,
    ``volatility_20`` (rolling std of ``ret_1``, ``ddof=1``),
    ``amount_mean_20``, ``sma_20``, ``range_pct`` = ``(high - low) / close``.

    All windows are computed per ``symbol``.  The output is sorted ascending
    by ``(symbol, date)`` and contains every original column unchanged.  Rows
    whose window is incomplete (warm-up) or whose inputs are null stay null;
    no value is ever forward-filled.  Raises :class:`FactorValidationError`
    for invalid input and never returns ``inf``.
    """

    validate_daily_frame(df)

    close = pl.col("close").cast(pl.Float64)
    high = pl.col("high").cast(pl.Float64)
    low = pl.col("low").cast(pl.Float64)
    amount = pl.col("amount").cast(pl.Float64)
    window = int(DEFAULT_FACTOR_PARAMS["amount_mean_window"])

    step1 = df.with_columns(
        [
            (close / close.shift(1).over("symbol") - 1.0).alias("ret_1"),
            (close / close.shift(5).over("symbol") - 1.0).alias("ret_5"),
            (close / close.shift(20).over("symbol") - 1.0).alias("ret_20"),
            ((high - low) / close).alias("range_pct"),
            close.rolling_mean(window, min_samples=window)
            .over("symbol")
            .alias("sma_20"),
            amount.rolling_mean(window, min_samples=window)
            .over("symbol")
            .alias("amount_mean_20"),
        ]
    )
    result = step1.with_columns(
        pl.col("ret_1")
        .rolling_std(
            int(DEFAULT_FACTOR_PARAMS["volatility_window"]),
            min_samples=int(DEFAULT_FACTOR_PARAMS["volatility_window"]),
            ddof=int(DEFAULT_FACTOR_PARAMS["volatility_ddof"]),
        )
        .over("symbol")
        .alias("volatility_20")
    )

    passthrough = [name for name in result.columns if name not in FACTOR_COLUMNS]
    result = result.select(passthrough + list(FACTOR_COLUMNS))
    _assert_no_infinite(result)
    return result
