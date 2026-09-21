"""P2-R10 half-day (11:30) cross-sectional signal survey (preregistered).

Implements the frozen protocol in
``docs/research/exp-20260918-p2r10-halfday-survey-prereg.md`` and
``configs/experiments/p2r10-halfday-survey.json`` exactly:

- 12 fixed factors F01..F12 computed at the 11:30 snapshot (one row per
  symbol-day from ``data/processed/halfday-1130-20260918``),
- frozen sample filters (suspended / ST / new listing <= 120 traded sessions /
  missing keys / |T1| > 0.21 / boards),
- targets T1 = close_day_official/open_1300 - 1 (open_1300 contractually is
  the 13:01 first afternoon bar open: vendor has no 13:00 bar) and
  descriptive T2 = next open_930 / close_1130 - 1,
- daily cross-sectional rank-IC (Spearman, min 50 names, same threshold as
  the R4 survey), Newey-West lag-5 t-stat,
- decile D10-D1 direction-aligned daily spread, annualized gross (244
  sessions/yr) and same-sign month share, plus the "buyable subset"
  (am_limit_up_touch_minutes == 0) disclosure,
- increment gate for the momentum family F01/F02/F10 vs the control F12,
- net reference (no gate): each decile-leg day treated as one-day trades at
  20k notional, wan-1 commission (5-yuan minimum binds) + historical
  segmented stamp duty.

F12 is the control and never counts toward the pass numerator.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Final

import numpy as np
import polars as pl

DEV_END: Final[date] = date(2020, 12, 31)
DEV_START: Final[date] = date(2015, 1, 1)
DESC_START: Final[date] = date(2021, 1, 1)
DESC_END: Final[date] = date(2024, 12, 31)

FACTOR_NAMES: Final[tuple[str, ...]] = tuple(f'F{i:02d}' for i in range(1, 13))
MOMENTUM_FAMILY: Final[tuple[str, ...]] = ('F01', 'F02', 'F10')
CONTROL: Final[str] = 'F12'

MIN_IC_STOCKS: Final[int] = 50  # same per-day minimum as the R4 survey
NW_LAG: Final[int] = 5
SESSIONS_PER_YEAR: Final[int] = 244  # same annualization as etf_rotation
T1_OUTLIER_BOUND: Final[float] = 0.21
NEW_LISTING_SESSIONS: Final[int] = 120
AM_BARS: Final[float] = 121.0
# CSI cross-listed indexes published inside the SZ 000xxx space (found and
# excluded by prior P2 rounds; they pass the naive board-prefix test).
EXCLUDED_INDEX_SYMBOLS: Final[frozenset[str]] = frozenset(
    {'sz.000905', 'sz.000852'})

IC_GATE_ABS_MEAN: Final[float] = 0.02
IC_GATE_NW_T: Final[float] = 3.0
DECILE_GATE_ANNUAL: Final[float] = 0.04
DECILE_GATE_MONTH_SHARE: Final[float] = 0.60
INCREMENT_GATE_RATIO: Final[float] = 1.3
PASS_MIN_FACTOR_COUNT: Final[int] = 2

# wan-1 commission, 5-yuan minimum, applied to a 20k notional one-day trade;
# historical segmented stamp duty (institutional facts, fee-recost run).
NET_NOTIONAL: Final[float] = 20000.0
NET_COMMISSION_PCT: Final[float] = 0.0001
NET_COMMISSION_MIN: Final[float] = 5.0
NET_STAMP_SEGMENTS: Final[tuple[tuple[date, float], ...]] = (
    (date(2015, 1, 1), 0.001),
    (date(2023, 8, 28), 0.0005),
)


def stamp_for(day: date) -> float:
    rate = NET_STAMP_SEGMENTS[0][1]
    for from_date, seg_rate in NET_STAMP_SEGMENTS:
        if day >= from_date:
            rate = seg_rate
        else:
            break
    return rate


def net_one_day_trade(gross_return: float, day: date) -> float:
    """Net return of one 20k-notional trade entered and exited same day.

    buy fee = max(notional*wan1, 5); sell fee = max(notional*wan1, 5)
    + notional*stamp(day).  Mirrors the fee-recost per-trade formula.
    """
    buy_fee = max(NET_NOTIONAL * NET_COMMISSION_PCT, NET_COMMISSION_MIN)
    exit_notional = NET_NOTIONAL * (1.0 + gross_return)
    sell_fee = max(NET_NOTIONAL * NET_COMMISSION_PCT, NET_COMMISSION_MIN) \
        + exit_notional * stamp_for(day)
    return (exit_notional - sell_fee) / (NET_NOTIONAL + buy_fee) - 1.0


# --------------------------------------------------------------------------- #
# Newey-West t-statistic (hand-derived cases in tests)
# --------------------------------------------------------------------------- #
def newey_west_t(values: list[float] | np.ndarray | pl.Series,
                 lag: int = NW_LAG) -> float | None:
    """One-mean Newey-West (Bartlett kernel) t-stat of the series mean.

    var = (1/T) * (g0 + 2 * sum_{l=1..L} (1 - l/(L+1)) * gl), gl = biased
    autocovariance at lag l; t = mean / sqrt(var).  Returns None when the
    variance is non-positive or undefined (degenerate series).
    """
    x = np.asarray(values, dtype=np.float64)
    x = x[np.isfinite(x)]
    t_len = x.size
    if t_len < 2:
        return None
    dev = x - x.mean()
    g0 = float(np.dot(dev, dev) / t_len)
    var = g0
    for l in range(1, min(lag, t_len - 1) + 1):
        gl = float(np.dot(dev[l:], dev[:-l]) / t_len)
        var += 2.0 * (1.0 - l / (lag + 1)) * gl
    if var <= 0.0:
        return None
    se = float(np.sqrt(var / t_len))
    if se == 0.0:
        return None
    return float(x.mean() / se)


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #
def load_daily_vol20(baostock_daily_path) -> pl.DataFrame:
    """Past-20-traded-sessions mean daily volume per (symbol, date).

    baostock daily rows with tradestatus == 1 only, each symbol's own row
    order, rolling(20).shift(1): suspended rows are skipped, today excluded.
    Uses the 1999-2024 daily file so pre-2015 history exists for every
    survivor of the era.

    2026-09-18 M-1 fix (P2-R10 double-sign review run
    20260918T054627-p2r10-review-c7d9x2): shift(1) moved INSIDE .over
    ('symbol'); the previous .over('symbol').shift(1) applied a global
    positional shift across symbols, leaking the previous symbol's value
    into each symbol's first row.
    """
    return (
        pl.scan_parquet(baostock_daily_path)
        .filter(pl.col('tradestatus') == 1.0)
        .sort('symbol', 'date')
        .with_columns(
            pl.col('volume').rolling_mean(20, min_samples=20)
            .shift(1).over('symbol').alias('daily_vol20'))
        .select('symbol', 'date', 'daily_vol20')
        .collect()
    )


def load_listing_index(baostock_daily_path) -> pl.DataFrame:
    """1-based index of the day within the symbol's own traded sessions.

    A stock is "new" while listing_index <= 120; suspensions do not advance
    the index (conservative: stays new longer).
    """
    return (
        pl.scan_parquet(baostock_daily_path)
        .filter(pl.col('tradestatus') == 1.0)
        .select('symbol', 'date',
                pl.int_range(pl.len()).over('symbol', order_by='date')
                .add(1).alias('listing_index'))
        .collect()
    )


def apply_sample_filters(halfday: pl.DataFrame,
                         listing: pl.DataFrame) -> pl.DataFrame:
    """Frozen sample_filters block of the config, in order."""
    symbol = pl.col('symbol')
    board_ok = (
        (symbol.str.starts_with('sh.60'))
        | (symbol.str.starts_with('sz.00'))
        | (symbol.str.starts_with('sz.30'))
    ) & ~symbol.is_in(EXCLUDED_INDEX_SYMBOLS)
    t1 = pl.col('close_day_official') / pl.col('open_1300') - 1.0
    return (
        halfday
        .filter(pl.col('tradestatus') == 1)
        .filter(pl.col('isST') == 0)
        .join(listing, on=['symbol', 'date'], how='left')
        .filter(pl.col('listing_index') > NEW_LISTING_SESSIONS)
        .filter(board_ok)
        .filter(pl.col('preclose_official').is_not_null()
                & pl.col('open_930').is_not_null()
                & pl.col('open_1300').is_not_null()
                & pl.col('close_day_official').is_not_null())
        .filter(t1.abs() <= T1_OUTLIER_BOUND)
    )


# --------------------------------------------------------------------------- #
# factor computation (post-filter cross-sections)
# --------------------------------------------------------------------------- #
def compute_factors(filtered: pl.DataFrame) -> pl.DataFrame:
    """F01..F12 + T1 + T2 on the filtered sample.

    All cross-sectional statistics (median for F02, ranks for F11, deciles)
    use the filtered sample only: suspended placeholder rows never enter a
    cross-section.  History factors: F08 = -mean(F02, past 5 own filtered
    rows, shift 1, min 5 rows); F07 from baostock daily vol20 (joined).
    """
    df = filtered.sort('symbol', 'date')
    df = df.with_columns(
        (pl.col('close_1130') / pl.col('open_930') - 1.0).alias('F01'),
        (pl.col('open_930') / pl.col('preclose_official') - 1.0).alias('F04'),
        ((pl.col('close_1130') - pl.col('low_am'))
         / (pl.col('high_am') - pl.col('low_am') + 1e-12)).alias('F06'),
        (pl.col('am_limit_up_touch_minutes') / AM_BARS).alias('F09'),
        (pl.col('close_1130') / pl.col('close_1100') - 1.0).alias('F10'),
        (pl.col('close_day_official') / pl.col('preclose_official')
         - 1.0).alias('F12'),
        (pl.col('close_day_official') / pl.col('open_1300') - 1.0).alias('T1'),
        (pl.col('vol_am') / pl.col('daily_vol20')).alias('F07'),
    )
    df = df.with_columns(
        (pl.col('F01') - pl.col('F01').median().over('date')).alias('F02'),
    )
    # 2026-09-18 M-1 fix: shift(1) inside .over('symbol') (per-symbol
    # history only); was .over('symbol').shift(1) which shifted the whole
    # column globally across symbols - see load_daily_vol20 docstring.
    df = df.with_columns(
        (-(pl.col('F02').rolling_mean(5, min_samples=5)
           .shift(1).over('symbol'))).alias('F08'),
    )
    df = df.with_columns(
        (pl.col('F02') * pl.col('F07')).alias('F03'),
        (pl.col('F04') * pl.col('F02')).alias('F05'),
        (pl.col('F02').rank(method='average').over('date')
         - pl.col('F07').rank(method='average').over('date')).alias('F11'),
    )
    df = df.with_columns(
        (pl.col('open_930').shift(-1).over('symbol')
         / pl.col('close_1130') - 1.0).alias('T2'),
    )
    return df


def factor_exprs() -> dict[str, pl.Expr]:
    """Row-level factor expressions (used by unit tests on raw frames)."""
    return {
        'F01': pl.col('close_1130') / pl.col('open_930') - 1.0,
        'F04': pl.col('open_930') / pl.col('preclose_official') - 1.0,
        'F06': ((pl.col('close_1130') - pl.col('low_am'))
                / (pl.col('high_am') - pl.col('low_am') + 1e-12)),
        'F07': pl.col('vol_am') / pl.col('daily_vol20'),
        'F09': pl.col('am_limit_up_touch_minutes') / AM_BARS,
        'F10': pl.col('close_1130') / pl.col('close_1100') - 1.0,
        'F12': pl.col('close_day_official') / pl.col('preclose_official') - 1.0,
        'T1': pl.col('close_day_official') / pl.col('open_1300') - 1.0,
    }


# --------------------------------------------------------------------------- #
# IC and decile machinery
# --------------------------------------------------------------------------- #
def daily_rank_ic(panel: pl.DataFrame, factor: str,
                  target: str = 'T1') -> pl.DataFrame:
    """Per-day Spearman rank-IC on pairs with both values non-null.

    Days with fewer than MIN_IC_STOCKS valid pairs are dropped.
    """
    return (
        panel.filter(pl.col(factor).is_not_null() & pl.col(target).is_not_null())
        .group_by('date')
        .agg(pl.corr(factor, target, method='spearman').alias('ic'),
             pl.len().alias('n'))
        .filter(pl.col('n') >= MIN_IC_STOCKS)
        .sort('date')
    )


def window_ic(ic: pl.DataFrame, lo: date, hi: date) -> dict:
    """IC stats over [lo, hi]; days with undefined (NaN) IC are excluded.

    NaN ICs arise on days where the factor is constant across the whole
    cross-section (e.g. F09 on stk_limit zero-row days, F10 on the
    2016-01-07 circuit-breaker afternoon) - they are counted and disclosed,
    never silently averaged.
    """
    w = ic.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
    n_dropped = int((~w['ic'].is_finite()).sum()) if w.height else 0
    w = w.filter(pl.col('ic').is_finite())
    if w.height == 0:
        return {'n_days': 0, 'mean_ic': None, 'nw_t': None,
                'n_days_dropped_nonfinite': n_dropped}
    return {'n_days': w.height,
            'mean_ic': float(w['ic'].mean()),
            'nw_t': newey_west_t(w['ic'].to_numpy(), NW_LAG),
            'n_days_dropped_nonfinite': n_dropped}


def yearly_ic(ic: pl.DataFrame, direction: int = 1) -> list[dict]:
    out = []
    finite_years = sorted({d.year for d, v in zip(ic['date'], ic['ic'])
                           if v is not None and np.isfinite(v)})
    for year in finite_years:
        w = ic.filter((pl.col('date').dt.year() == year)
                      & pl.col('ic').is_finite())
        out.append({'year': year, 'n_days': w.height,
                    'mean_ic': float(w['ic'].mean()),
                    'nw_t': newey_west_t(w['ic'].to_numpy(), NW_LAG)})
    return out


def _pivot_decile_legs(per_decile: pl.DataFrame, value_col: str) -> pl.DataFrame:
    """Wide (date, d1..d10) frame; missing deciles become null columns."""
    wide = per_decile.sort('date', '_decile').pivot(
        on='_decile', index='date', values=value_col)
    rename = {str(i): f'd{i}' for i in range(1, 11) if str(i) in wide.columns}
    wide = wide.rename(rename)
    missing = [pl.lit(None, dtype=pl.Float64).alias(f'd{i}')
               for i in range(1, 11) if f'd{i}' not in wide.columns]
    if missing:
        wide = wide.with_columns(missing)
    return wide.sort('date').select(
        ['date'] + [f'd{i}' for i in range(1, 11)])


def decile_spread_series(panel: pl.DataFrame, factor: str,
                         target: str = 'T1') -> pl.DataFrame:
    """Daily direction-agnostic D10-D1 spread (mean T1, equal weight).

    Deciles use ordinal ranks (deterministic; ties broken by the frame's
    symbol, date order) so zero-inflated factors (F09) still populate every
    decile; large tied groups are spread evenly across adjacent deciles
    (disclosed in the results doc).
    """
    ranked = (
        panel.filter(pl.col(factor).is_not_null() & pl.col(target).is_not_null())
        .with_columns(
            ((pl.col(factor).rank(method='ordinal').over('date') - 1.0)
             / pl.len().over('date')).alias('_pct')))
    ranked = ranked.with_columns(
        (((pl.col('_pct') * 10.0).floor().clip(0, 9)) + 1)
        .cast(pl.Int32).alias('_decile'))
    per_decile = ranked.group_by('date', '_decile').agg(
        pl.col(target).mean().alias('ret'), pl.len().alias('n'))
    wide = _pivot_decile_legs(per_decile, 'ret')
    return wide.with_columns(
        (pl.col('d10') - pl.col('d1')).alias('spread'))


@dataclass
class WindowStats:
    n_days: int
    mean_daily: float | None
    annualized: float | None
    month_share_same_sign: float | None
    n_months: int | None
    buyable_annualized: float | None = None
    buyable_month_share: float | None = None


def _finite_or_none(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return float(value)


def spread_window_stats(spread: pl.DataFrame, lo: date, hi: date,
                        direction: int) -> WindowStats:
    """Annualized gross spread + same-sign month share in [lo, hi]."""
    w = spread.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
    if w.height == 0:
        return WindowStats(0, None, None, None, 0)
    d = w.with_columns(pl.col('spread') * direction)
    mean_daily = _finite_or_none(float(d['spread'].mean()))
    months = d.group_by(pl.col('date').dt.month_start().alias('month')).agg(
        pl.col('spread').sum().alias('m'))
    n_months = months.height
    same = float((months['m'] * (1 if (mean_daily or 0.0) >= 0 else -1) > 0)
                 .mean()) if n_months else None
    same = _finite_or_none(same)
    annual = mean_daily * SESSIONS_PER_YEAR if mean_daily is not None else None
    return WindowStats(w.height, mean_daily, annual, same, n_months)


# --------------------------------------------------------------------------- #
# gates
# --------------------------------------------------------------------------- #
def ic_gate_pass(stats: dict) -> bool:
    return (stats['mean_ic'] is not None and stats['nw_t'] is not None
            and abs(stats['mean_ic']) >= IC_GATE_ABS_MEAN
            and abs(stats['nw_t']) >= IC_GATE_NW_T)


def decile_gate_pass(stats: WindowStats) -> bool:
    return (stats.annualized is not None
            and stats.month_share_same_sign is not None
            and stats.annualized >= DECILE_GATE_ANNUAL
            and stats.month_share_same_sign >= DECILE_GATE_MONTH_SHARE)


def increment_gate_pass(factor: str, ic_mean: float | None,
                        control_ic_mean: float | None) -> bool:
    if factor not in MOMENTUM_FAMILY:
        return True
    if ic_mean is None or control_ic_mean is None:
        return False
    return abs(ic_mean) >= INCREMENT_GATE_RATIO * abs(control_ic_mean)


def factor_direction(dev_mean_ic: float | None) -> int:
    return 1 if (dev_mean_ic or 0.0) >= 0.0 else -1


# --------------------------------------------------------------------------- #
# net reference (annotation only, no gate)
# --------------------------------------------------------------------------- #
def attach_net_one_day(panel: pl.DataFrame) -> pl.DataFrame:
    """Vectorized per-row net of one 20k-notional same-day round trip.

    buy fee = max(20000*wan1, 5) = 5 (minimum binds); sell fee = 5
    + exit_notional * stamp(date).  Equivalent to net_one_day_trade row-wise
    (hand-checked in tests).
    """
    exit_notional = NET_NOTIONAL * (1.0 + pl.col('T1'))
    stamp = pl.when(pl.col('date') >= date(2023, 8, 28)).then(0.0005) \
        .otherwise(0.001)
    return panel.with_columns(
        ((exit_notional
          - (pl.lit(NET_NOTIONAL * NET_COMMISSION_PCT)
             .clip(lower_bound=NET_COMMISSION_MIN)
             + exit_notional * stamp))
         / (NET_NOTIONAL + max(NET_NOTIONAL * NET_COMMISSION_PCT,
                               NET_COMMISSION_MIN)) - 1.0).alias('net1d'))


def net_reference(panel_with_net: pl.DataFrame, factor: str, direction: int,
                  lo: date, hi: date) -> dict:
    """Dev-window net reference for the direction-aligned D10-D1 spread.

    Each (day, leg) is the mean over constituent one-day 20k-notional trades
    (``net1d`` column from :func:`attach_net_one_day`).
    """
    ranked = (
        panel_with_net
        .filter(pl.col(factor).is_not_null() & pl.col('T1').is_not_null())
        .filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
        .with_columns(
            ((pl.col(factor).rank(method='ordinal').over('date') - 1.0)
             / pl.len().over('date')).alias('_pct')))
    ranked = ranked.with_columns(
        (((pl.col('_pct') * 10.0).floor().clip(0, 9)) + 1)
        .cast(pl.Int32).alias('_decile'))
    per_day = ranked.group_by('date', '_decile').agg(
        pl.col('net1d').mean().alias('net_mean'))
    wide = _pivot_decile_legs(per_day, 'net_mean')
    long_leg, short_leg = ('d10', 'd1') if direction == 1 else ('d1', 'd10')
    net_spread = wide.select((pl.col(long_leg) - pl.col(short_leg)).alias('ns'))
    mean_daily = _finite_or_none(float(net_spread['ns'].mean()))
    return {'mean_daily_net_spread': mean_daily,
            'annualized_net_spread': mean_daily * SESSIONS_PER_YEAR}
