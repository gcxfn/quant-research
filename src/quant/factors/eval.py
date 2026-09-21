"""Forward-looking factor evaluation layer (F1).

Contract
--------
Input is a factor frame with columns ``symbol (str)``, ``signal_date (Date)``,
``value (Float64)`` — ``(symbol, signal_date)`` unique, no nulls in keys.
Forward returns are read from a daily panel (the v0 baostock frame:
``date/symbol/close/preclose/tradestatus/isST/...``) as the compound of
``close / preclose - 1`` over the ``horizon_days`` trading days **starting
the day after** ``signal_date`` (close signal -> next-day execution, aligned
with the band contract; the signal day's own return is never used).

``preclose`` is the exchange reference price, so the daily chain already
embeds dividends/splits — no separate adjustment factor is needed.  A symbol
with fewer than ``horizon_days`` remaining panel rows after ``signal_date``
yields no forward return and is dropped (documented truncation, not filled).

R11 (2026-09-20 strategy review): the forward-return chain runs over the
FULL panel — a symbol that turns ST (or halts) INSIDE the holding window
keeps those rows in its realized return; only a halted row's return is
frozen at 0.  Pool eligibility (``exclude_st`` / ``require_trading`` /
``min_history_rows``) is a POINT-IN-TIME check on the signal date row.
Deleting ST/halted rows before chaining (the pre-R11 behavior) skipped
mid-window losses and lengthened the effective window.  Callers bumping
``factor_meta`` versions should treat the R11 fix as a caliber change.

Freeze discipline: every date handled here (signal, panel, forward window)
must be ``<= 2024-12-31``; violations raise before any statistic is
computed.  This module produces evaluation statistics only — no selection
rule, no "good factor" verdict, and no access to anything on/after
2025-01-01.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date as Date
from typing import Any, Final, Sequence

import polars as pl

from .core import FactorError

__all__ = [
    "FREEZE_END",
    "FactorEvalConfig",
    "FactorEvalError",
    "eval_cache_key",
    "evaluate_factor",
    "pit_financial",
]

#: Research window hard stop (AGENTS.md: 2025-01-01 and later is frozen).
FREEZE_END: Final[Date] = Date(2024, 12, 31)

#: Board prefixes excluded from the eligible pool (AGENTS.md: 科创板/北交所
#: excluded; 创业板 allowed — account-permission dependent).
_EXCLUDED_BOARD_PREFIXES = ("sh.688", "bj.")


class FactorEvalError(FactorError, ValueError):
    """Raised on contract violations (bad frame, freeze breach, bad config)."""


@dataclass(frozen=True)
class FactorEvalConfig:
    """Evaluation parameters; every field participates in the cache key."""

    #: forward-return window in trading days after signal_date
    horizon_days: int = 10
    #: cross-sectional quantile groups per evaluation date
    n_groups: int = 10
    #: "D" = every trading day with data, "M" = month-end trading day only
    eval_freq: str = "D"
    #: pool filters (historical point-in-time where the panel supports it)
    exclude_st: bool = True
    require_trading: bool = True
    exclude_boards: bool = True
    #: require this many prior panel rows for a symbol before it is eligible
    min_history_rows: int = 60

    def __post_init__(self) -> None:
        if self.horizon_days < 1:
            raise FactorEvalError(f"horizon_days must be >= 1, got {self.horizon_days}")
        if self.n_groups < 2:
            raise FactorEvalError(f"n_groups must be >= 2, got {self.n_groups}")
        if self.eval_freq not in ("D", "M"):
            raise FactorEvalError(
                f"eval_freq must be 'D' or 'M', got {self.eval_freq!r}"
            )
        if self.min_history_rows < 0:
            raise FactorEvalError("min_history_rows must be >= 0")

    def canonical(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "n_groups": self.n_groups,
            "eval_freq": self.eval_freq,
            "exclude_st": self.exclude_st,
            "require_trading": self.require_trading,
            "exclude_boards": self.exclude_boards,
            "min_history_rows": self.min_history_rows,
        }


def eval_cache_key(
    factor_meta: dict[str, Any], panel_sha256: str, cfg: FactorEvalConfig
) -> str:
    """SHA-256 cache key: factor identity + panel identity + eval params.

    Follows AGENTS.md §5.4 (input version, pool/window/alignment caliber,
    factor code and params — never a bare filename).
    """

    payload = {
        "factor": factor_meta,
        "panel_sha256": panel_sha256,
        "eval": cfg.canonical(),
        "freeze_end": str(FREEZE_END),
    }
    canon = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# input validation
# ---------------------------------------------------------------------------

def _validate_factor_frame(factor: pl.DataFrame) -> None:
    if not isinstance(factor, pl.DataFrame):
        raise TypeError(f"expected polars.DataFrame, got {type(factor).__name__}")
    missing = [c for c in ("symbol", "signal_date", "value") if c not in factor.columns]
    if missing:
        raise FactorEvalError(f"factor frame missing columns: {missing}")
    if factor.schema["symbol"] != pl.String:
        raise FactorEvalError("column 'symbol' must be String")
    if factor.schema["signal_date"] != pl.Date:
        raise FactorEvalError("column 'signal_date' must have dtype Date")
    if not factor.schema["value"].is_numeric():
        raise FactorEvalError("column 'value' must be numeric")
    if int(factor["symbol"].null_count()) or int(factor["signal_date"].null_count()):
        raise FactorEvalError("factor key columns must not contain nulls")
    dup = factor.group_by("symbol", "signal_date").len().filter(pl.col("len") > 1)
    if dup.height:
        raise FactorEvalError(
            f"duplicate (symbol, signal_date) keys: {dup.height}; "
            f"example: {dup.head(3).to_dicts()}"
        )
    mx = factor["signal_date"].max()
    if mx is not None and mx > FREEZE_END:
        raise FactorEvalError(
            f"freeze breach: factor signal_date {mx} > {FREEZE_END} (2025+ frozen)"
        )


def _validate_panel(panel: pl.DataFrame) -> None:
    missing = [c for c in ("date", "symbol", "close", "preclose") if c not in panel.columns]
    if missing:
        raise FactorEvalError(f"panel missing required columns: {missing}")
    if panel.schema["date"] != pl.Date:
        raise FactorEvalError("panel column 'date' must have dtype Date")
    mx = panel["date"].max()
    if mx is not None and mx > FREEZE_END:
        raise FactorEvalError(f"freeze breach: panel date {mx} > {FREEZE_END} (2025+ frozen)")


# ---------------------------------------------------------------------------
# evaluation core
# ---------------------------------------------------------------------------

def _prepare_panel(panel: pl.DataFrame, cfg: FactorEvalConfig) -> pl.DataFrame:
    """Daily-return chain + history depth + SIGNAL-DATE eligibility flag.

    R11 (2026-09-20 strategy review): pool filters no longer DELETE panel
    rows.  A row the holder lives through -- an ST turn mid-window, a halt
    -- is real market outcome and stays in the forward-return chain; the
    "can I buy THIS day" question (ST status, trading status, history
    depth) is answered by ``sig_eligible`` and applied at the signal date
    only.  A halted row freezes the chain at return 0 (the price is frozen
    at the last trade); the resumption gap lands on the resumption day's
    own return.  A TRADING row with a null close/preclose return is a data
    defect and raises instead of silently entering the chain as 0.
    """

    out = panel.with_columns(
        (pl.col("close").cast(pl.Float64)
         / pl.col("preclose").cast(pl.Float64) - 1.0).alias("_day_ret_raw")
    )
    halted = (pl.col("tradestatus").cast(pl.Int64) == 0
              if "tradestatus" in out.columns else pl.lit(False))
    out = out.with_columns(
        pl.when(halted).then(0.0).otherwise(pl.col("_day_ret_raw"))
        .alias("day_ret"))
    if "tradestatus" in out.columns and cfg.require_trading:
        bad = out.filter(
            (pl.col("tradestatus").cast(pl.Int64) == 1)
            & pl.col("day_ret").is_null())
        if bad.height:
            raise FactorEvalError(
                "panel has %d trading row(s) with a null close/preclose "
                "return; fix the data before evaluating (e.g. %s)"
                % (bad.height,
                   bad.select("symbol", "date").head(3).to_dicts())
            )
    out = out.with_columns(
        pl.int_range(pl.len()).over("symbol").alias("hist_depth"))
    elig = pl.lit(True)
    if cfg.exclude_st and "isST" in out.columns:
        # a null isST on the signal date is ineligible (conservative)
        elig = elig & (pl.col("isST").cast(pl.Int64) == 0)
    if cfg.require_trading and "tradestatus" in out.columns:
        elig = elig & (pl.col("tradestatus").cast(pl.Int64) == 1)
    elig = elig & (pl.col("hist_depth") >= cfg.min_history_rows)
    out = out.with_columns(elig.alias("sig_eligible"))
    if cfg.exclude_boards:
        for pref in _EXCLUDED_BOARD_PREFIXES:
            out = out.filter(~pl.col("symbol").str.starts_with(pref))
    return out.select("date", "symbol", "day_ret", "sig_eligible")


def _forward_return_grid(ready: pl.DataFrame, horizon: int) -> pl.DataFrame:
    """Per (symbol, date t): compound return over the NEXT ``horizon`` rows.

    fwd(t) = prod(1 + day_ret[t+1 .. t+h]) - 1, computed from a reverse
    cumulative product per symbol: with cump(t) = prod(day t..end),
    fwd(t) = cump(t+h+1) / cump(t+1) - 1.  Rows where the window is
    truncated (fewer than h rows after t) are dropped.
    """

    grid = ready.sort("symbol", "date").with_columns(
        (1.0 + pl.col("day_ret").clip(-0.9999, None)).alias("_gross")
    )
    # suffix product per symbol, entirely inside the window so row alignment
    # is preserved: cump(t) = prod(day t..end) = [rev -> cum_prod -> rev]
    grid = grid.with_columns(
        pl.col("_gross")
        .reverse()
        .cum_prod()
        .reverse()
        .over("symbol")
        .alias("_cump")
    )
    grid = grid.with_columns(
        pl.col("_cump").shift(-1).over("symbol").alias("_cump_next"),
        # suffix product beyond the last row is the empty product 1.0
        pl.col("_cump").shift(-(horizon + 1)).over("symbol").fill_null(1.0).alias("_cump_after"),
        # row t+horizon must EXIST, else the window is incomplete -> drop
        pl.col("day_ret").shift(-horizon).over("symbol").is_not_null().alias("_has_row_h"),
    )
    # the last panel row (no t+1) and truncated windows are dropped
    grid = grid.with_columns(
        (pl.col("_cump_next") / pl.col("_cump_after")).alias("fwd_gross")
    ).filter(pl.col("_cump_next").is_not_null() & pl.col("_has_row_h"))
    return (
        grid.filter(pl.col("fwd_gross").is_not_null())
        .with_columns((pl.col("fwd_gross") - 1.0).alias("fwd_ret"))
        .select("date", "symbol", "fwd_ret")
    )


def _rank(col: str) -> pl.Expr:
    return pl.col(col).rank(method="average").cast(pl.Float64)


def _pearson_expr(x: pl.Expr, y: pl.Expr) -> pl.Expr:
    xc = x - x.mean()
    yc = y - y.mean()
    den = (xc.pow(2).mean().sqrt()) * (yc.pow(2).mean().sqrt())
    return pl.when(den > 0).then((xc * yc).mean() / den).otherwise(None)


def _pearson_pairs(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    vx = sum((x - mx) ** 2 for x in xs) / n
    vy = sum((y - my) ** 2 for y in ys) / n
    den = (vx * vy) ** 0.5
    return cov / den if den > 0 else float("nan")


def _eval_grid(
    factor: pl.DataFrame, ready: pl.DataFrame, cfg: FactorEvalConfig
) -> pl.DataFrame:
    """One row per (signal_date, symbol): value + forward return.

    R11: the signal row must exist in the panel AND be ``sig_eligible``
    (point-in-time ST/trading/history-depth check at the signal date);
    the forward window itself runs over the FULL chain, so mid-window ST
    turns and halts stay in the realized return.
    """

    fwd = _forward_return_grid(ready, cfg.horizon_days)
    sig = ready.select(
        "symbol", pl.col("date").alias("signal_date"), "sig_eligible")
    joined = (
        factor.join(sig, on=["symbol", "signal_date"], how="inner")
        .filter(pl.col("sig_eligible"))
        .join(
            fwd,
            left_on=["symbol", "signal_date"],
            right_on=["symbol", "date"],
            how="inner",
        )
        .filter(pl.col("fwd_ret").is_not_null() & pl.col("value").is_not_null())
    )

    if cfg.eval_freq == "M":
        month_ends = (
            joined.with_columns(pl.col("signal_date").dt.truncate("1mo").alias("_m"))
            .group_by("_m")
            .agg(pl.col("signal_date").max().alias("signal_date"))
            .select("signal_date")
        )
        joined = joined.join(month_ends, on="signal_date", how="semi")
    return joined.select("signal_date", "symbol", "value", "fwd_ret")


def evaluate_factor(
    factor: pl.DataFrame,
    panel: pl.DataFrame,
    cfg: FactorEvalConfig | None = None,
    *,
    others: dict[str, pl.DataFrame] | None = None,
) -> dict[str, Any]:
    """Evaluate one factor frame against the panel.

    Returns a dict (JSON-serialisable via ``default=str``):

    - ``n_dates``, ``coverage_mean_symbols`` — cross-section size stats;
    - ``ic_mean``, ``ic_std``, ``icir``, ``ic_win_rate`` — per-date
      Spearman IC of value vs forward return;
    - ``group_mean_ret`` (low->high factor quantile), ``long_short_mean``,
      ``monotonicity`` (Pearson of group index vs group mean return);
    - ``ic_by_year`` / ``long_short_by_year`` (2015 has its own key);
    - ``turnover_top_group`` — mean 1 - overlap of consecutive top groups;
    - ``corr_with_others`` (dict name -> mean cross-sectional Spearman rho);
    - ``config`` — the frozen config canonical dict.

    No selection rule is applied here; interpretation belongs to a
    preregistered F2 round.
    """

    cfg = cfg or FactorEvalConfig()
    _validate_factor_frame(factor)
    _validate_panel(panel)
    data = _eval_grid(factor, _prepare_panel(panel, cfg), cfg)
    if data.height == 0:
        raise FactorEvalError(
            "empty evaluation grid: factor/panel overlap is zero after pool "
            "filters and forward-window truncation"
        )

    # per-date IC
    per_date = (
        data.group_by("signal_date")
        .agg(n=pl.len(), ic=_pearson_expr(_rank("value"), _rank("fwd_ret")))
        .filter(pl.col("ic").is_not_null())
        .sort("signal_date")
    )
    if per_date.height == 0:
        raise FactorEvalError(
            "no valid IC dates (every cross-section has <2 rows or zero "
            "variance); evaluation undefined"
        )
    ic = per_date["ic"].to_list()
    n_dates = len(ic)
    ic_mean = sum(ic) / n_dates
    ic_std = (
        (sum((v - ic_mean) ** 2 for v in ic) / (n_dates - 1)) ** 0.5
        if n_dates > 1
        else 0.0
    )
    icir = ic_mean / ic_std if ic_std > 0 else float("nan")
    win = sum(1 for v in ic if v > 0) / n_dates

    # quantile groups per date (rank-based qcut; group 1 = lowest value)
    g = cfg.n_groups
    grp_frame = data.with_columns(
        ((_rank("value") / pl.len()).mul(g).ceil().cast(pl.Int32))
        .over("signal_date")
        .alias("grp")
    )
    gm = (
        grp_frame.group_by("signal_date", "grp")
        .agg(mret=pl.col("fwd_ret").mean())
        .group_by("grp")
        .agg(gmean=pl.col("mret").mean())
        .sort("grp")
    )
    group_means = gm["gmean"].to_list()
    group_idx = [float(i) for i in gm["grp"].to_list()]
    long_short_mean = (
        group_means[-1] - group_means[0] if len(group_means) >= 2 else float("nan")
    )
    mono = _pearson_pairs(group_idx, group_means) if len(group_means) >= 2 else float("nan")

    # yearly breakdown (2015 is its own key by construction)
    ic_by_year = {
        int(r["year"]): float(r["ic_mean"])
        for r in per_date.with_columns(pl.col("signal_date").dt.year().alias("year"))
        .group_by("year")
        .agg(ic_mean=pl.col("ic").mean())
        .sort("year")
        .to_dicts()
    }
    ls_by_year: dict[int, float] = {}
    for r in (
        grp_frame.with_columns(pl.col("signal_date").dt.year().alias("year"))
        .group_by("year", "grp")
        .agg(mret=pl.col("fwd_ret").mean())
        .pivot(on="grp", index="year", values="mret")
        .sort("year")
        .to_dicts()
    ):
        year = int(r.pop("year"))
        # a year with sparse coverage may miss some quantile groups entirely;
        # pivot fills those cells with null -> keep only realized group means
        cells = {int(k): float(v) for k, v in r.items() if v is not None}
        if len(cells) >= 2:
            ls_by_year[year] = cells[max(cells)] - cells[min(cells)]

    # turnover of the top group
    top_by_date: dict[Any, set[str]] = {}
    for r in (
        grp_frame.filter(pl.col("grp") == g).select("signal_date", "symbol").to_dicts()
    ):
        top_by_date.setdefault(r["signal_date"], set()).add(r["symbol"])
    dates_sorted = sorted(top_by_date)
    tovs = [
        1.0 - len(top_by_date[d0] & top_by_date[d1]) / len(top_by_date[d0])
        for d0, d1 in zip(dates_sorted, dates_sorted[1:])
        if top_by_date[d0] and top_by_date[d1]
    ]
    turnover = sum(tovs) / len(tovs) if tovs else float("nan")

    # correlation with other factor frames
    corr: dict[str, float] = {}
    for name, other in (others or {}).items():
        _validate_factor_frame(other)
        m = data.join(
            other.select(
                "symbol", "signal_date", pl.col("value").alias("_other")
            ),
            on=["symbol", "signal_date"],
            how="inner",
        ).filter(pl.col("_other").is_not_null())
        if m.height == 0:
            corr[name] = float("nan")
            continue
        rhos = (
            m.group_by("signal_date")
            .agg(rho=_pearson_expr(_rank("value"), _rank("_other")))
            .filter(pl.col("rho").is_not_null())["rho"]
            .to_list()
        )
        corr[name] = sum(rhos) / len(rhos) if rhos else float("nan")

    return {
        "n_dates": n_dates,
        "coverage_mean_symbols": float(per_date["n"].mean()),
        "ic_mean": ic_mean,
        "ic_std": ic_std,
        "icir": icir,
        "ic_win_rate": win,
        "group_mean_ret": group_means,
        "long_short_mean": long_short_mean,
        "monotonicity": mono,
        "ic_by_year": ic_by_year,
        "long_short_by_year": ls_by_year,
        "turnover_top_group": turnover,
        "corr_with_others": corr,
        "config": cfg.canonical(),
    }


# ---------------------------------------------------------------------------
# PIT helper for announcement-grained inputs
# ---------------------------------------------------------------------------

def pit_financial(events: pl.DataFrame) -> pl.DataFrame:
    """Map announcement rows to ``(symbol, signal_date, end_date)`` PIT rows.

    Input columns (tushare style): ``ts_code``, ``end_date``, ``ann_date``
    (optional), ``f_ann_date`` (optional), ``update_flag`` (optional).
    Per ``(ts_code, end_date)`` the row with the LATEST ``ann_date`` wins
    (amendments replace earlier reads).  Equal-date rows are resolved by
    explicit lexicographic tie-breaks over the remaining columns.
    ``signal_date`` = ``f_ann_date``
    when present else ``ann_date``; when both are missing the row falls
    back to quarter-end + 90 days (DATA_COVERAGE discipline) and is flagged
    in the boolean ``used_90d_fallback`` column.
    Symbol style is converted to panel style (``600519.SH`` -> ``sh.600519``).
    Output is sorted by ``(symbol, signal_date)`` and unique on it.
    """

    for col in ("ts_code", "end_date"):
        if col not in events.columns:
            raise FactorEvalError(f"pit_financial: missing column {col!r}")
    df = events
    for col in ("ann_date", "f_ann_date", "update_flag"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.String).alias(col))

    df = df.with_columns(
        pl.col("ann_date").cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False),
        pl.col("f_ann_date").cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False),
        pl.col("end_date").cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False),
    )
    # latest announcement wins per (ts_code, end_date)
    tie = sorted(c for c in df.columns if c not in {"ts_code", "end_date", "ann_date"})
    df = df.sort(
        ["ts_code", "end_date", "ann_date", *tie], nulls_last=True
    ).group_by("ts_code", "end_date").last()
    df = df.with_columns(
        pl.concat_str(
            pl.col("ts_code").str.split(".").list.last().str.to_lowercase(),
            pl.lit("."),
            pl.col("ts_code").str.split(".").list.first(),
        ).alias("symbol")
    )
    fallback = pl.col("f_ann_date").fill_null(pl.col("ann_date")).is_null()
    df = df.with_columns(
        pl.coalesce(
            pl.col("f_ann_date"),
            pl.col("ann_date"),
            pl.col("end_date") + pl.duration(days=90),
        ).alias("signal_date"),
        fallback.alias("used_90d_fallback"),
    )
    out = df.select("symbol", "signal_date", "end_date", "used_90d_fallback")
    dup = out.group_by("symbol", "signal_date").len().filter(pl.col("len") > 1)
    if dup.height:
        # One signal date can contain several report periods.  Choose the
        # earliest period, then a canonical row order, instead of group order.
        tie = sorted(c for c in out.columns if c not in {"symbol", "signal_date", "end_date"})
        out = out.sort(
            ["symbol", "signal_date", "end_date", *tie], nulls_last=True
        ).group_by("symbol", "signal_date").first()
    return out.sort("symbol", "signal_date")
