"""P2-R14 minute microstructure round (preregistered).

Implements the frozen protocol in
``docs/research/exp-20260918-p2r14-minute-structure-prereg.md`` and
``configs/experiments/p2r14-minute-structure.json`` (frozen 2026-09-18
08:10) exactly.  Six judgment units U1..U6 over minute-derived daily
microstructure features; every unit is a filter / event rule / marker /
adjudication use case, never a standalone entry trigger.

Extraction (single merged projection scan of ``user_minute_1m``, one row
per symbol-day): close_share30 / tail_amt_share (last-30-min amount
share), last30_ret (15:00/14:30 close), day_high/day_low (incl. PM),
am_range30 (09:30-10:00 range over full-day range), first_bar_vol (09:30
auction bar volume) + first_bar_vol_med20 (own 20-session median,
shift-in-over), pm_touch_limit_down and limit_close_state (seal/broke/
untouched vs stk_limit, float32 tolerance 1e-4/2e-4 per vendor-3).

Operationalizations disclosed BEFORE any judgment run (frozen here; none
of them touches a preregistered threshold or criterion):
- close_share30 window = bars with tod >= 14:30:00 (31 bars incl. the
  15:00 close auction), per proposal text ``sum(amount >= 14:30)``.
- am_range30 window = 09:30:00 <= tod <= 10:00:00 (31 bars); denominator
  = full-day (day_high - day_low); zero/negative denominator -> null.
- Zero-volume (vol == 0) bars are placeholder bars and are excluded from
  every minute aggregation (DATA_SOURCES §1.3 trap); symbol-days with no
  volume-bearing bar at all (suspended placeholders) are dropped from
  the feature table entirely.  ``tail_amt_share`` is the same quantity as
  ``close_share30`` (two proposal names for one column; both kept to
  satisfy the prereg column contract).
- T2 = close_day_official(t+1) / open_930(t+1) - 1 anchored to the next
  MARKET session (join on the session calendar, not a positional shift);
  if the symbol does not trade on t+1 (tradestatus != 1 or no row) the
  label is null and the row drops out of label statistics; labels that
  would land after 2024-12-31 are structurally null (2025+ zero-touch).
- U5 next-day amplitude = (day_high - day_low) / preclose_official of
  the next traded session, same anchoring as T2.
- Pool history columns (listing_index, amt_med20, daily_vol20) use
  ``daily_1999_2024.parquet`` so that 2015 signals have full 20/120-day
  windows - the same warmup precedent disclosed by the R10 review run
  (20260918T054627) and R13; the config-pinned ``daily_2015_2024``
  identity remains the source of everything else via the halfday table.
- U2/U3 control set per day = pool non-event stocks whose full-day
  return lies within +/-0.5pp of AT LEAST ONE same-day event (union of
  per-event buckets, nearest-event searchsorted implementation); daily
  diff = mean(event T2) - mean(control T2); NW lag 5 on the daily
  series; yearly criterion = sign of the yearly mean of that series.
- U4: control = same-day untouched (state == 0) pool stocks with full-day
  return in [5%, 9.5%] (the config parenthetical attaches the bucket to
  the control); seal/broke groups are the full state groups; both leg
  diffs require NW(5) |t| >= 3.
- U5 use-gate host proxy ("weakest AM decile", R10 host, disclosed):
  per-day bottom decile (ordinal) of the morning return
  F01 = close_1130/open_930 - 1 within the pool; removal = within-day
  top quartile of am_range30 among host rows; single-trade outcome =
  the R10 net1d convention on T1 (20k notional, wan-1 commission with
  5-yuan minimum, segmented stamp) - the same annotation-level caveat as
  R10 (13:01 buy -> close sell is not a T+1-implementable new entry).
- U6 rho uses the continuous auction ratio first_bar_vol/med20 (per-day
  Spearman vs F07/F03, min 50 names, dev mean); residual event effect =
  per-day OLS coefficient of T1 excess on [1, event, F03] over days with
  >= 5 events, NW(5) t on the coefficient series.
- Val (2021-2024) is consumed once and only for dev-passing units, with
  the dev-frozen direction; U4 keeps the dual-gate rule in val.

Dev = 2015-01-05..2020-12-31 (8th reuse, elimination only).  Trials
disclosed this round: 6 (cumulative 189).
"""
from __future__ import annotations

import random
from datetime import date
from pathlib import Path
from typing import Final

import numpy as np
import polars as pl

from quant.research.p2r10_halfday import (  # reused verbatim
    NW_LAG,
    SESSIONS_PER_YEAR,
    attach_net_one_day,
    daily_rank_ic,
    decile_spread_series,
    newey_west_t,
    spread_window_stats,
    window_ic,
    yearly_ic,
    WindowStats,
)

# --------------------------------------------------------------------------- #
# frozen protocol constants
# --------------------------------------------------------------------------- #
DEV_START: Final[date] = date(2015, 1, 5)
DEV_END: Final[date] = date(2020, 12, 31)
VAL_START: Final[date] = date(2021, 1, 1)
VAL_END: Final[date] = date(2024, 12, 31)
FREEZE_LAST: Final[date] = date(2024, 12, 31)
FREEZE_MAX_COMPACT: Final[str] = '20241231'
SH_CLOSE_AUCTION_START: Final[date] = date(2018, 8, 20)

SEED: Final[int] = 17
MIN_IC_STOCKS: Final[int] = 50  # R10 convention
U6_MIN_EVENTS_PER_DAY: Final[int] = 5

# float32 tolerances (vendor-3 §0: limit semantics 1e-4 / 2e-4)
LIMIT_TOL: Final[float] = 1e-4      # seal/touch vs limit_up: *(1 - 1e-4)
TOUCH_TOL: Final[float] = 2e-4      # pm touch vs limit_down: *(1 + 2e-4)
CTRL_BUFFER: Final[float] = 0.003   # U3 control must be > limit_down*(1+0.3%)

# U1 H-40
U1_IC_MAX: Final[float] = -0.02
U1_NW_T_MIN: Final[float] = 3.0
U1_ANNUAL_MIN: Final[float] = 0.04
U1_MONTH_SHARE_MIN: Final[float] = 0.60
U1_RESID_IC_MIN: Final[float] = 0.015  # |residual IC| gate
# U2 H-41
U2_LAST30_MIN: Final[float] = 0.015
U2_DAY_RET_MAX: Final[float] = 0.09
U2_TAIL_SHARE_MIN: Final[float] = 0.20
EVENT_BUCKET: Final[float] = 0.005   # +/-0.5pp same-day return bucket
U2_DIFF_MAX: Final[float] = -0.005   # event - control <= -0.5pp
U2_YEARS_MIN: Final[int] = 4         # >= 4/6 dev years same sign
U2_BASE_RATE_MIN: Final[float] = 0.005
# U3 H-42
U3_DIFF_MAX: Final[float] = -0.005
U3_MIN_EVENTS: Final[int] = 500
U3_HEAVY_MONTH: Final[float] = 0.30  # disclosure threshold
# U4 H-43 (adjudicating)
U4_BUCKET_LO: Final[float] = 0.05
U4_BUCKET_HI: Final[float] = 0.095
U4_BROKE_MAX: Final[float] = -0.005
U4_SEAL_MIN: Final[float] = 0.005
# U5 H-44
U5_IC_MIN: Final[float] = 0.02
U5_RESID_IC_MIN: Final[float] = 0.01
U5_P5_IMPROVE: Final[float] = 0.10
U5_MEAN_COST_MAX: Final[float] = 0.005
# U6 H-45
U6_VOL_MULT: Final[float] = 5.0
U6_DIFF_MAX: Final[float] = -0.003
U6_RHO_MAX: Final[float] = 0.70
U6_RESID_EFFECT_MAX: Final[float] = -0.0015

EXCLUDED_INDEX_SYMBOLS: Final[frozenset[str]] = frozenset(
    {'sz.000905', 'sz.000852'})
NEW_LISTING_SESSIONS: Final[int] = 120
LIQ_MEDIAN_AMOUNT: Final[float] = 50_000_000.0
MIN_CLOSE: Final[float] = 2.0

FEAT_COLS: Final[tuple[str, ...]] = (
    'symbol', 'date', 'close_share30', 'tail_amt_share', 'last30_ret',
    'day_high', 'day_low', 'am_range30', 'first_bar_vol',
    'first_bar_vol_med20', 'pm_touch_limit_down', 'limit_close_state')


# --------------------------------------------------------------------------- #
# extraction: one merged projection scan per day file
# --------------------------------------------------------------------------- #
def fen(s: pl.Expr) -> pl.Expr:
    """float32 -> float64 then restore the 0.01-yuan cent grid (R10 prep
    verified the vendor float32 cent encoding with zero residual)."""
    return (s.cast(pl.Float64) * 100).round() / 100


def extract_day_features(fp: Path, d_iso: str) -> tuple[pl.DataFrame, dict]:
    """One minute day parquet -> per-symbol feature row (see module
    docstring for the frozen operationalizations).

    Returns (features frame, counters).  Fail-closed: date/filename
    mismatch, any row dated after the freeze line, or a non-.BJ bar later
    than 15:00:00 raises.
    """
    c: dict[str, int] = {}
    if d_iso > FREEZE_LAST.isoformat():
        raise RuntimeError(f'freeze violation: requested day {d_iso} '
                           f'> {FREEZE_LAST}')
    tod = pl.col('trade_time').str.slice(11, 8).alias('tod')
    df = pl.read_parquet(fp).with_columns(tod)
    compact = d_iso.replace('-', '')
    c['source_rows'] = df.height
    n_mismatch = int(df.select((pl.col('date') != compact).sum()).item())
    c['date_col_mismatch_filename'] = n_mismatch
    if n_mismatch:
        raise RuntimeError(f'{d_iso}: date column mismatches filename '
                           f'({n_mismatch} rows)')
    n_freeze = int(df.select((pl.col('date') > FREEZE_MAX_COMPACT)
                             .sum()).item())
    c['date_col_rows_gt_freeze'] = n_freeze
    if n_freeze:
        raise RuntimeError(f'{d_iso}: rows after freeze line ({n_freeze})')
    is_bj = pl.col('code').str.ends_with('.BJ')
    gt15 = pl.col('tod') > '15:00:00'
    c['bj_rows_removed'] = int(df.select(is_bj.sum()).item())
    c['gt15_rows_removed_raw'] = int(df.select(gt15.sum()).item())
    c['gt15_rows_removed_non_bj'] = int(
        df.filter(~is_bj).select(gt15.sum()).item())
    if c['gt15_rows_removed_non_bj']:
        raise RuntimeError(f'{d_iso}: non-.BJ bars after 15:00 '
                           f"({c['gt15_rows_removed_non_bj']})")
    c['bar_1300_rows_present'] = int(
        df.select((pl.col('tod') == '13:00:00').sum()).item())
    df = df.filter(~is_bj & ~gt15)

    traded = df.filter(pl.col('vol') > 0)
    c['zerovol_bars_removed'] = df.height - traded.height

    agg = traded.group_by('code').agg(
        fen(pl.col('high').max()).alias('day_high'),
        fen(pl.col('low').min()).alias('day_low'),
        pl.col('amount').cast(pl.Float64).sum().alias('day_amt'),
        pl.col('amount').cast(pl.Float64)
          .filter(pl.col('tod') >= '14:30:00').sum().alias('tail_amt'),
        fen(pl.col('high').filter(pl.col('tod') <= '10:00:00').max())
          .alias('am30_high'),
        fen(pl.col('low').filter(pl.col('tod') <= '10:00:00').min())
          .alias('am30_low'),
    )
    b930 = (df.filter(pl.col('tod') == '09:30:00')
              .select('code', pl.col('vol').cast(pl.Float64)
                      .alias('first_bar_vol')))
    b1430 = (traded.filter(pl.col('tod') == '14:30:00')
                    .select('code', fen(pl.col('close')).alias('close_1430')))
    b1500 = (traded.filter(pl.col('tod') == '15:00:00')
                    .select('code', fen(pl.col('close')).alias('close_1500')))
    c['first_bar_zerovol'] = int((b930['first_bar_vol'] == 0).sum())

    out = (agg.join(b930, on='code', how='left')
              .join(b1430, on='code', how='left')
              .join(b1500, on='code', how='left'))
    n_codes = int(df.select(pl.col('code').n_unique()).item())
    out = out.filter(pl.col('day_amt') > 0)
    c['rows_dropped_all_zerovol'] = n_codes - out.height
    out = out.with_columns(
        (pl.col('tail_amt') / pl.col('day_amt')).alias('close_share30'),
        (pl.col('close_1500') / pl.col('close_1430') - 1.0)
          .alias('last30_ret'),
        ((pl.col('am30_high') - pl.col('am30_low'))
         / (pl.col('day_high') - pl.col('day_low'))).alias('am_range30'),
    )
    c['missing_close_1430'] = int(out['close_1430'].null_count())
    c['missing_close_1500'] = int(out['close_1500'].null_count())
    c['zero_range_denominator'] = int(
        out.select(((pl.col('day_high') - pl.col('day_low')) <= 0)
                   .sum()).item())
    out = out.with_columns(
        pl.col('close_share30').alias('tail_amt_share'),
        pl.lit(date.fromisoformat(d_iso)).alias('date'),
        pl.col('code').str.split('.').list.reverse().list.join('.')
          .str.to_lowercase().alias('symbol'),
    )
    c['rows_out'] = out.height
    # pre-finalize columns; med20 + limit columns are added by
    # finalize_feature_table on the concatenated panel.
    return (out.select(['symbol', 'date', 'close_share30', 'tail_amt_share',
                        'last30_ret', 'day_high', 'day_low', 'am_range30',
                        'first_bar_vol']), c)


def finalize_feature_table(feats: pl.DataFrame,
                           halfday_limits: pl.DataFrame) -> pl.DataFrame:
    """med20 (shift-in-over) + limit_up/limit_down state columns.

    ``halfday_limits``: (symbol, date, limit_up, limit_down,
    close_day_official) from the frozen halfday table.  State: 2 = sealed
    at close (close_day_official >= limit_up*(1-1e-4)), 1 = touched and
    closed off the board (broke), 0 = never touched; null when limit_up
    is missing (5 registered stk_limit zero-row days + suspended gaps).
    pm_touch_limit_down: day_low <= limit_down*(1+2e-4), null when
    limit_down missing.
    """
    df = feats.sort('symbol', 'date')
    # 2026-09-18 M-1 rule: shift INSIDE .over('symbol') - a positional
    # shift outside .over leaks the previous symbol's rows into each
    # symbol's first rows (R10 double-sign review finding).
    df = df.with_columns(
        pl.col('first_bar_vol').rolling_median(20, min_samples=20)
          .shift(1).over('symbol').alias('first_bar_vol_med20'))
    df = df.join(halfday_limits, on=['symbol', 'date'], how='left')
    df = df.with_columns(
        pl.when(pl.col('limit_up').is_null()).then(None)
          .when(pl.col('close_day_official')
                >= pl.col('limit_up') * (1.0 - LIMIT_TOL)).then(pl.lit(2))
          .when(pl.col('day_high')
                >= pl.col('limit_up') * (1.0 - LIMIT_TOL)).then(pl.lit(1))
          .otherwise(pl.lit(0)).cast(pl.Int8).alias('limit_close_state'))
    df = df.with_columns(
        pl.when(pl.col('limit_down').is_null()).then(None)
          .when(pl.col('day_low')
                <= pl.col('limit_down') * (1.0 + TOUCH_TOL))
          .then(True).otherwise(False).alias('pm_touch_limit_down'))
    return df.select(list(FEAT_COLS))


# --------------------------------------------------------------------------- #
# pool panel: feats + halfday + daily history + labels
# --------------------------------------------------------------------------- #
def board_ok_expr() -> pl.Expr:
    symbol = pl.col('symbol')
    return (symbol.str.starts_with('sh.60')
            | symbol.str.starts_with('sz.00')) \
        & ~symbol.is_in(EXCLUDED_INDEX_SYMBOLS)


def load_daily_history(daily_path) -> pl.DataFrame:
    """Per (symbol, own traded session): listing_index (1-based, all own
    sessions since 1999), amt_med20 (20-session rolling median INCLUDING
    the current session, R13 convention) and daily_vol20 (past-20 mean
    volume, shift(1), R10 convention).  Windows are computed on the full
    per-symbol history; only rows from 2013-06-01 on are returned (the
    join span needed to warm up every 2015-01-05 signal)."""
    return (
        pl.scan_parquet(daily_path)
        .filter(pl.col('tradestatus') == 1.0)
        .sort('symbol', 'date')
        .select(
            'symbol', 'date', 'amount',
            pl.int_range(pl.len()).over('symbol', order_by='date')
              .add(1).alias('listing_index'),
            pl.col('amount').rolling_median(20, min_samples=20)
              .over('symbol').alias('amt_med20'),
            pl.col('volume').rolling_mean(20, min_samples=20)
              .shift(1).over('symbol').alias('daily_vol20'),
        )
        .filter(pl.col('date') >= date(2013, 6, 1))
        .collect()
    )


def build_next_session_map(dates: pl.Series) -> pl.DataFrame:
    """(date, next_date) over the market session calendar; the last
    session (2024-12-31) has no next -> labels anchored there are
    structurally null (2025+ zero-touch)."""
    cal = dates.unique().sort().to_frame('date')
    return cal.with_columns(pl.col('date').shift(-1).alias('next_date'))


def attach_next_labels(feats: pl.DataFrame, halfday: pl.DataFrame,
                       panel: pl.DataFrame) -> pl.DataFrame:
    """Attach T2 / amp_next to ``panel`` (see module docstring for the
    frozen anchoring).  ``feats`` = pre-pool feature rows (they define
    the traded stock-day set and the session calendar); ``halfday`` = the
    full halfday table (supplies next-session prices + tradestatus, so a
    suspended next session nulls the label)."""
    hd = halfday.select('symbol', 'date', 'open_930', 'close_day_official',
                        'preclose_official', 'tradestatus')
    nxt = (feats.join(hd, on=['symbol', 'date'], how='inner')
           .select('symbol',
                   pl.col('date').alias('next_date'),
                   pl.col('open_930').alias('open_930_n'),
                   pl.col('close_day_official').alias('close_n'),
                   pl.col('day_high').alias('day_high_n'),
                   pl.col('day_low').alias('day_low_n'),
                   pl.col('preclose_official').alias('preclose_n'),
                   pl.col('tradestatus').alias('tradestatus_n')))
    panel = (panel.join(build_next_session_map(feats['date']),
                        on='date', how='left')
             .join(nxt, on=['symbol', 'next_date'], how='left'))
    return panel.with_columns(
        pl.when(pl.col('tradestatus_n') == 1)
          .then(pl.col('close_n') / pl.col('open_930_n') - 1.0)
          .otherwise(None).alias('T2'),
        pl.when(pl.col('tradestatus_n') == 1)
          .then((pl.col('day_high_n') - pl.col('day_low_n'))
                / pl.col('preclose_n'))
          .otherwise(None).alias('amp_next'),
    )


def build_panel(root: Path, feats: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Pool-filtered judgment panel (see module docstring).

    Pool: tradestatus==1, isST==0, SH/SZ main board (index symbols
    excluded), listing_index > 120, amt_med20 >= 50mm, close >= 2 CNY.
    Labels: day_ret, day_amp, F01, T1 (13:01 -> close, R10), T2 and
    amp_next (next traded session, suspension -> null, 2025+ -> null),
    F07/F03/F09 (R10 formulas on this pool), net1d (R10 convention).
    """
    counts: dict[str, object] = {'feats_rows': feats.height}
    if feats['date'].max() > FREEZE_LAST:
        raise RuntimeError('feature table exceeds the freeze line')
    halfday = (
        pl.scan_parquet(root / 'data/processed/halfday-1130-20260918'
                        '/halfday_1130.parquet')
        .select('symbol', 'date', 'preclose_official', 'open_930',
                'close_1100', 'close_1130', 'open_1300',
                'close_day_official', 'limit_up', 'limit_down',
                'vol_am', 'amount_am',
                'am_limit_up_touch_minutes', 'tradestatus', 'isST')
        .collect())
    panel = feats.join(halfday, on=['symbol', 'date'], how='inner')
    counts['feats_rows_missing_in_halfday'] = feats.height - panel.height
    if counts['feats_rows_missing_in_halfday']:
        raise RuntimeError('feature rows absent from the halfday table')
    hist = load_daily_history(
        root / 'data/processed/baostock-daily-20260917'
        / 'daily_1999_2024.parquet')
    panel = panel.join(hist, on=['symbol', 'date'], how='left')

    # Next-session label anchors use PRE-POOL rows only: a symbol must
    # simply have traded (bars + tradestatus == 1) on t+1 for its price
    # to anchor T2/amp_next; pool membership on t+1 is irrelevant, and
    # suspended placeholders (tradestatus == 0) null the label.
    panel = attach_next_labels(feats, halfday, panel)

    panel = panel.filter(pl.col('tradestatus') == 1)
    counts['after_tradestatus'] = panel.height
    panel = panel.filter(pl.col('isST') == 0)
    counts['after_st'] = panel.height
    panel = panel.filter(board_ok_expr())
    counts['after_boards'] = panel.height
    panel = panel.filter(pl.col('listing_index') > NEW_LISTING_SESSIONS)
    counts['after_listing_120'] = panel.height
    panel = panel.filter(pl.col('amt_med20') >= LIQ_MEDIAN_AMOUNT)
    counts['after_liq_50m'] = panel.height
    panel = panel.filter(pl.col('close_day_official') >= MIN_CLOSE)
    counts['pool_rows'] = panel.height

    panel = panel.with_columns(
        (pl.col('close_day_official') / pl.col('preclose_official') - 1.0)
          .alias('day_ret'),
        (pl.col('close_1130') / pl.col('open_930') - 1.0).alias('F01'),
        (pl.col('close_day_official') / pl.col('open_1300') - 1.0)
          .alias('T1'),
        (pl.col('vol_am') / pl.col('daily_vol20')).alias('F07'),
        ((pl.col('day_high') - pl.col('day_low'))
         / pl.col('preclose_official')).alias('day_amp'),
    )
    panel = panel.with_columns(
        pl.col('amount').log().alias('log_amount'),
        (pl.col('F01') - pl.col('F01').median().over('date')).alias('F02'),
        (pl.col('am_limit_up_touch_minutes').cast(pl.Float64) / 121.0)
          .alias('F09'),
    )
    panel = panel.with_columns(
        (pl.col('F02') * pl.col('F07')).alias('F03'))
    panel = attach_net_one_day(panel)
    panel = panel.select(
        'symbol', 'date', 'open_930', 'preclose_official',
        'limit_up', 'limit_down',
        'close_share30', 'tail_amt_share', 'last30_ret', 'day_high',
        'day_low', 'am_range30', 'first_bar_vol', 'first_bar_vol_med20',
        'pm_touch_limit_down', 'limit_close_state', 'day_ret', 'day_amp',
        'F01', 'F02', 'F03', 'F07', 'F09', 'T1', 'T2', 'amp_next',
        'net1d', 'log_amount', 'daily_vol20')
    panel = panel.sort('date', 'symbol')
    counts['pool_rows_null_T2'] = int(panel['T2'].null_count())
    counts['names_per_day_mean'] = float(
        panel.group_by('date').agg(pl.len().alias('n'))['n'].mean())
    return panel, counts


# --------------------------------------------------------------------------- #
# shared machinery: residual IC, event-control diffs
# --------------------------------------------------------------------------- #
def residual_ic_series(panel: pl.DataFrame, factor: str,
                       control_cols: list[str], target: str,
                       lo: date, hi: date,
                       min_names: int = MIN_IC_STOCKS) -> pl.DataFrame:
    """Per-day rank-residualization IC (R13 c4_pepb_residual_ic pattern):
    rank(factor) ~ OLS [1, rank(controls)]; Spearman(resid, target).
    Days with fewer than min_names complete pairs are dropped."""
    df = panel.filter(pl.col('date').is_between(lo, hi))
    rows: list[tuple[date, float, int]] = []
    keep = pl.col(factor).is_not_null() & pl.col(target).is_not_null()
    for c in control_cols:
        keep = keep & pl.col(c).is_not_null()
    for (day,), g in df.filter(keep).group_by(
            ['date'], maintain_order=True):
        if g.height < min_names:
            continue
        y = g[factor].rank(method='average').to_numpy()
        x = np.column_stack(
            [np.ones(g.height)]
            + [g[c].rank(method='average').to_numpy() for c in control_cols])
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        resid = y - x @ beta
        rt = g[target].rank(method='average').to_numpy()
        ic = float(np.corrcoef(resid, rt)[0, 1])
        rows.append((day, ic, g.height))
    return pl.DataFrame(
        rows, schema={'date': pl.Date, 'ic': pl.Float64, 'n': pl.Int64},
        orient='row')


def window_ic_stats(ic: pl.DataFrame, lo: date, hi: date) -> dict:
    """window_ic + directional gates applied by callers; NaN ICs are
    counted, never averaged (R10 convention)."""
    return window_ic(ic, lo, hi)


def control_mask_by_day(g: pl.DataFrame, ev_mask: pl.Expr,
                        extra_ctrl: pl.Expr | None,
                        bucket: float) -> tuple[pl.DataFrame, pl.DataFrame]:
    """One day partition -> (events, controls) using the union-of-buckets
    rule (nearest-event searchsorted).  Both sides carry non-null T2."""
    ev = g.filter(ev_mask & pl.col('T2').is_not_null()
                  & pl.col('day_ret').is_not_null())
    if ev.height == 0:
        return ev, ev.head(0)
    cand = g.filter(~ev_mask & pl.col('T2').is_not_null()
                    & pl.col('day_ret').is_not_null())
    if extra_ctrl is not None:
        cand = cand.filter(extra_ctrl)
    if cand.height == 0:
        return ev, cand
    er = np.sort(ev['day_ret'].to_numpy())
    cr = cand['day_ret'].to_numpy()
    idx = np.searchsorted(er, cr)
    left = np.clip(idx - 1, 0, er.size - 1)
    right = np.clip(idx, 0, er.size - 1)
    dist = np.minimum(np.abs(cr - er[left]), np.abs(cr - er[right]))
    return ev, cand.filter(pl.Series(dist <= bucket))


def event_control_diffs(panel: pl.DataFrame, event_expr: pl.Expr,
                        lo: date, hi: date, target: str = 'T2',
                        bucket: float = EVENT_BUCKET,
                        extra_ctrl: pl.Expr | None = None) -> pl.DataFrame:
    """Daily (n_event, n_ctrl, mean_event, mean_ctrl, diff) rows over
    [lo, hi]; days without both sides are absent (counted by callers)."""
    df = panel.filter(pl.col('date').is_between(lo, hi))
    out: list[list] = []
    for (day,), g in df.group_by(['date'], maintain_order=True):
        ev, ctrl = control_mask_by_day(g, event_expr, extra_ctrl, bucket)
        if ev.height == 0 or ctrl.height == 0:
            continue
        m_e = float(ev[target].mean())
        m_c = float(ctrl[target].mean())
        out.append([day, ev.height, ctrl.height, m_e, m_c, m_e - m_c])
    return pl.DataFrame(
        out,
        schema={'date': pl.Date, 'n_event': pl.Int64, 'n_ctrl': pl.Int64,
                'mean_event': pl.Float64, 'mean_ctrl': pl.Float64,
                'diff': pl.Float64},
        orient='row')


def pool_baseline_diffs(panel: pl.DataFrame, event_expr: pl.Expr,
                        lo: date, hi: date, target: str = 'T1',
                        extra_filter: pl.Expr | None = None
                        ) -> pl.DataFrame:
    """Daily diff of mean(target) events vs the FULL same-day pool
    equal-weight mean (events included in the baseline, per "同池等权"
    as written).  Days without events are absent."""
    df = panel.filter(pl.col('date').is_between(lo, hi))
    if extra_filter is not None:
        df = df.filter(extra_filter)
    rows: list[list] = []
    for (day,), gday in df.group_by(['date'], maintain_order=True):
        ev = gday.filter(event_expr)
        if ev.height == 0 or gday.height == 0:
            continue
        m_e = float(ev[target].mean())
        m_p = float(gday[target].mean())
        rows.append([day, ev.height, m_e, m_p, m_e - m_p])
    return pl.DataFrame(
        rows,
        schema={'date': pl.Date, 'n_event': pl.Int64,
                'mean_event': pl.Float64, 'mean_pool': pl.Float64,
                'diff': pl.Float64},
        orient='row')


def diff_gate(diffs: pl.DataFrame, gate_value: float,
              lo: date, hi: date) -> dict:
    """Mean diff gate + NW(5) t + yearly same-sign share over [lo, hi]."""
    w = diffs.filter(pl.col('date').is_between(lo, hi))
    n_days = w.height
    if n_days == 0:
        return {'n_days': 0, 'mean_diff': None, 'nw_t': None,
                'years': [], 'years_same_sign': None}
    arr = w['diff'].to_numpy()
    mean = float(arr.mean())
    years = []
    for year in sorted({d.year for d in w['date']}):
        yw = w.filter(pl.col('date').dt.year() == year)
        years.append({'year': year, 'n_days': yw.height,
                      'mean_diff': float(yw['diff'].mean())})
    want = -1.0 if gate_value < 0 else 1.0
    same = sum(1 for y in years if y['mean_diff'] * want > 0)
    return {'n_days': n_days, 'mean_diff': mean,
            'nw_t': newey_west_t(arr, NW_LAG), 'years': years,
            'years_same_sign': same / len(years) if years else None,
            'n_years': len(years)}


def events_heavy_month_share(panel: pl.DataFrame, event_expr: pl.Expr,
                             lo: date, hi: date) -> float | None:
    """Share of event stock-days falling in the heaviest calendar month
    (U3 clustering disclosure)."""
    ev = panel.filter(pl.col('date').is_between(lo, hi) & event_expr)
    if ev.height == 0:
        return None
    per = ev.group_by(pl.col('date').dt.month_start().alias('m')).agg(
        pl.len().alias('n'))
    return float(per['n'].max() / per['n'].sum())


def pick_sample(items, n: int, seed: int = SEED) -> list:
    """Deterministic sample (base seed 17 from the frozen config) over a
    sorted item list - used for identity re-hashing and cross-checks."""
    rng = random.Random(seed)
    return rng.sample(sorted(items), min(n, len(items)))


def p5_improvement(p5_before: float, p5_after: float) -> float | None:
    """Relative P5 improvement of the use gate: signed-distance ratio when
    the baseline P5 is negative (left tail), ratio-1 when positive."""
    if p5_before < 0:
        return (p5_after - p5_before) / abs(p5_before)
    if p5_before > 0:
        return p5_after / p5_before - 1.0
    return None


def use_gate_pass(improve: float | None, mean_cost: float) -> bool:
    """P5 improvement >= 10% AND mean-net cost of removal <= 0.5pp."""
    return (improve is not None and improve >= U5_P5_IMPROVE
            and mean_cost <= U5_MEAN_COST_MAX)


# --------------------------------------------------------------------------- #
# units (dev judgment; val re-runs the same function on 2021-2024)
# --------------------------------------------------------------------------- #
def _arm_exprs() -> dict[str, pl.Expr]:
    return {
        'sh_pre': (pl.col('symbol').str.starts_with('sh.60')
                   & (pl.col('date') < SH_CLOSE_AUCTION_START)),
        'sh_post': (pl.col('symbol').str.starts_with('sh.60')
                    & (pl.col('date') >= SH_CLOSE_AUCTION_START)),
        'sz_only': pl.col('symbol').str.starts_with('sz.00'),
    }


def u1_judge(panel: pl.DataFrame, lo: date, hi: date) -> dict:
    """U1 H-40: close_share30 vs T2.  Gates: rank IC <= -0.02 with
    NW(5)|t| >= 3; direction-aligned (negative) D10-D1 annualized >= 4%
    with same-sign months >= 60%; orthogonalized residual |IC| >= 0.015
    (vs log amount + same-day return)."""
    df = panel.filter(pl.col('date').is_between(lo, hi))
    ic = daily_rank_ic(df, 'close_share30', 'T2')
    stats = window_ic(ic, lo, hi)
    gate_ic = (stats['mean_ic'] is not None and stats['nw_t'] is not None
               and stats['mean_ic'] <= U1_IC_MAX
               and abs(stats['nw_t']) >= U1_NW_T_MIN)
    spread = decile_spread_series(df, 'close_share30', 'T2')
    ws = spread_window_stats(spread, lo, hi, direction=-1)
    gate_decile = (ws.annualized is not None
                   and ws.month_share_same_sign is not None
                   and ws.annualized >= U1_ANNUAL_MIN
                   and ws.month_share_same_sign >= U1_MONTH_SHARE_MIN)
    ric = residual_ic_series(df, 'close_share30',
                             ['log_amount', 'day_ret'], 'T2', lo, hi)
    resid_mean = float(ric['ic'].mean()) if ric.height else None
    resid_nw = (newey_west_t(ric['ic'].to_numpy(), NW_LAG)
                if ric.height else None)
    gate_incr = (resid_mean is not None
                 and abs(resid_mean) >= U1_RESID_IC_MIN)
    arms = {}
    for name, expr in _arm_exprs().items():
        sub = df.filter(expr)
        a_ic = window_ic(daily_rank_ic(sub, 'close_share30', 'T2'), lo, hi)
        a_ws = spread_window_stats(
            decile_spread_series(sub, 'close_share30', 'T2'), lo, hi,
            direction=-1)
        arms[name] = {'ic': a_ic, 'annualized': a_ws.annualized,
                      'month_share_same_sign': a_ws.month_share_same_sign,
                      'n_days': a_ws.n_days}
    return {
        'ic': stats, 'yearly_ic': yearly_ic(ic.filter(
            pl.col('date').is_between(lo, hi))),
        'decile': {'n_days': ws.n_days, 'annualized': ws.annualized,
                   'month_share_same_sign': ws.month_share_same_sign,
                   'mean_daily': ws.mean_daily},
        'residual': {'mean_ic': resid_mean, 'nw_t': resid_nw,
                     'n_days': ric.height},
        'arms': arms,
        'gates': {'ic': gate_ic, 'decile': gate_decile,
                  'increment_residual': gate_incr},
        'passed': bool(gate_ic and gate_decile and gate_incr),
    }


def u2_judge(panel: pl.DataFrame, lo: date, hi: date) -> dict:
    """U2 H-41 tail-pull event: last30_ret >= +1.5% AND day_ret < 9% AND
    tail_amt_share >= 20%; control = same-day +/-0.5pp bucket non-events.
    Gates: diff <= -0.5pp with NW|t| >= 3; >= 4/6 years same sign; base
    rate < 0.5% -> insufficient sample (not established)."""
    event = ((pl.col('last30_ret') >= U2_LAST30_MIN)
             & (pl.col('day_ret') < U2_DAY_RET_MAX)
             & (pl.col('tail_amt_share') >= U2_TAIL_SHARE_MIN))
    df = panel.filter(pl.col('date').is_between(lo, hi)
                      & pl.col('day_ret').is_not_null())
    n_events = int(df.select(event.sum()).item())
    base_rate = n_events / df.height if df.height else None
    diffs = event_control_diffs(df, event, lo, hi)
    g = diff_gate(diffs, U2_DIFF_MAX, lo, hi)
    gate_primary = (g['mean_diff'] is not None
                    and g['mean_diff'] <= U2_DIFF_MAX
                    and g['nw_t'] is not None
                    and abs(g['nw_t']) >= U1_NW_T_MIN)
    n_years = g.get('n_years', 0)
    gate_years = (g['years_same_sign'] is not None
                  and sum(1 for y in g['years']
                          if y['mean_diff'] < 0) >= U2_YEARS_MIN
                  and n_years == 6)
    enough = base_rate is not None and base_rate >= U2_BASE_RATE_MIN
    arms = {}
    for name, expr in _arm_exprs().items():
        sub = df.filter(expr)
        a = diff_gate(event_control_diffs(sub, event, lo, hi),
                      U2_DIFF_MAX, lo, hi)
        arms[name] = {'mean_diff': a['mean_diff'], 'nw_t': a['nw_t'],
                      'n_days': a['n_days']}
    return {
        'n_events': n_events, 'base_rate': base_rate,
        'diffs': g, 'arms': arms,
        'gates': {'primary': gate_primary, 'years': gate_years,
                  'base_rate_enough': enough},
        'passed': bool(gate_primary and gate_years and enough),
    }


def u3_judge(panel: pl.DataFrame, lo: date, hi: date) -> dict:
    """U3 H-42 limit-down freeze: event = pm_touch_limit_down; control =
    same-day +/-0.5pp bucket with low > limit_down*(1+0.3%).  Gates:
    diff <= -0.5pp, t >= 3, >= 4/6 years, >= 500 event stock-days;
    heaviest-month share > 30% is a registered clustering risk."""
    event = pl.col('pm_touch_limit_down') == True  # noqa: E712
    extra = ((pl.col('limit_down').is_not_null())
             & (pl.col('day_low') > pl.col('limit_down') * (1.0 + CTRL_BUFFER)))
    df = panel.filter(pl.col('date').is_between(lo, hi)
                      & pl.col('day_ret').is_not_null())
    n_events = int(df.filter(event & pl.col('T2').is_not_null()).height)
    n_events_all = int(df.filter(event).height)
    diffs = event_control_diffs(df, event, lo, hi, extra_ctrl=extra)
    g = diff_gate(diffs, U3_DIFF_MAX, lo, hi)
    gate_primary = (g['mean_diff'] is not None
                    and g['mean_diff'] <= U3_DIFF_MAX
                    and g['nw_t'] is not None
                    and abs(g['nw_t']) >= U1_NW_T_MIN)
    gate_years = (g['years_same_sign'] is not None
                  and sum(1 for y in g['years']
                          if y['mean_diff'] < 0) >= U2_YEARS_MIN
                  and g.get('n_years', 0) == 6)
    gate_sample = n_events >= U3_MIN_EVENTS
    heavy = events_heavy_month_share(df, event, lo, hi)
    return {
        'n_events_with_t2': n_events, 'n_events_all': n_events_all,
        'heavy_month_share': heavy,
        'heavy_month_flag': (heavy is not None and heavy > U3_HEAVY_MONTH),
        'diffs': g,
        'gates': {'primary': gate_primary, 'years': gate_years,
                  'sample_500': gate_sample},
        'passed': bool(gate_primary and gate_years and gate_sample),
    }


def u4_judge(panel: pl.DataFrame, lo: date, hi: date) -> dict:
    """U4 H-43 (adjudicating): seal/broke/untouched vs the 5-9.5%
    untouched bucket.  Dual gate: broke-ctrl <= -0.5pp AND
    seal-ctrl >= +0.5pp (both NW|t| >= 3).  Also returns the F09-T2
    mixture adjudication inputs (always written up, pass or fail)."""
    df = panel.filter(pl.col('date').is_between(lo, hi)
                      & pl.col('day_ret').is_not_null()
                      & pl.col('limit_close_state').is_not_null())
    ctrl_expr = ((pl.col('limit_close_state') == 0)
                 & (pl.col('day_ret') >= U4_BUCKET_LO)
                 & (pl.col('day_ret') <= U4_BUCKET_HI))

    def leg(group_expr: pl.Expr) -> dict:
        diffs = event_control_diffs(
            df.filter(ctrl_expr | group_expr),  # candidates: ctrl or group
            group_expr, lo, hi, extra_ctrl=ctrl_expr)
        g = diff_gate(diffs, 0.0, lo, hi)  # report-only gate value
        sub = df.filter(group_expr & pl.col('T2').is_not_null())
        ctrl_rows = diffs.select(
            (pl.col('mean_ctrl') * pl.col('n_ctrl')).sum().alias('w'),
            pl.col('n_ctrl').sum().alias('n'))
        ev_rows = diffs.select(
            (pl.col('mean_event') * pl.col('n_event')).sum().alias('w'),
            pl.col('n_event').sum().alias('n'))
        m_ctrl = (float(ctrl_rows['w'][0] / ctrl_rows['n'][0])
                  if ctrl_rows['n'][0] else None)
        m_ev = (float(ev_rows['w'][0] / ev_rows['n'][0])
                if ev_rows['n'][0] else None)
        return {'n_events': int(sub.height), 'mean_diff': g['mean_diff'],
                'nw_t': g['nw_t'], 'n_days': g['n_days'],
                'mean_event_t2': m_ev, 'mean_ctrl_t2': m_ctrl,
                'years': g['years']}

    broke = leg(pl.col('limit_close_state') == 1)
    seal = leg(pl.col('limit_close_state') == 2)
    gate_broke = (broke['mean_diff'] is not None
                  and broke['mean_diff'] <= U4_BROKE_MAX
                  and broke['nw_t'] is not None
                  and abs(broke['nw_t']) >= U1_NW_T_MIN)
    gate_seal = (seal['mean_diff'] is not None
                 and seal['mean_diff'] >= U4_SEAL_MIN
                 and seal['nw_t'] is not None
                 and abs(seal['nw_t']) >= U1_NW_T_MIN)
    # F09-T2 adjudication inputs: the R10 F09 reading recomputed on this
    # pool + per-state mean T2.
    f09_ic = window_ic(daily_rank_ic(df, 'F09', 'T2'), lo, hi)
    state_means: dict[str, float | None] = {}
    for s in (0, 1, 2):
        m = df.filter((pl.col('limit_close_state') == s)
                      & pl.col('T2').is_not_null())['T2'].mean()
        state_means[f'state_{s}'] = float(m) if m is not None else None
    return {
        'broke': broke, 'seal': seal,
        'gates': {'broke_negative': gate_broke, 'seal_positive': gate_seal},
        'passed': bool(gate_broke and gate_seal),
        'broke_also_positive': (broke['mean_diff'] is not None
                                and broke['mean_diff'] > 0),
        'f09_t2_ic': f09_ic, 'state_mean_t2': state_means,
    }


def u5_judge(panel: pl.DataFrame, lo: date, hi: date) -> dict:
    """U5 H-44 morning volatility concentration vs next-day amplitude.
    Prediction gate: rank IC >= +0.02 with t >= 3 and vol20/day-amp
    orthogonalized residual >= +0.01.  Use gate: removing the top
    am_range30 quartile of the weakest-AM-decile host improves the P5 of
    single-trade net returns by >= 10% at a mean-net cost <= 0.5pp.
    Both gates must pass."""
    df = panel.filter(pl.col('date').is_between(lo, hi))
    ic = daily_rank_ic(df, 'am_range30', 'amp_next')
    stats = window_ic(ic, lo, hi)
    gate_ic = (stats['mean_ic'] is not None and stats['nw_t'] is not None
               and stats['mean_ic'] >= U5_IC_MIN
               and abs(stats['nw_t']) >= U1_NW_T_MIN)
    ric = residual_ic_series(df, 'am_range30', ['daily_vol20', 'day_amp'],
                             'amp_next', lo, hi)
    resid_mean = float(ric['ic'].mean()) if ric.height else None
    resid_nw = (newey_west_t(ric['ic'].to_numpy(), NW_LAG)
                if ric.height else None)
    gate_resid = resid_mean is not None and resid_mean >= U5_RESID_IC_MIN

    host = df.filter(pl.col('F01').is_not_null()
                     & pl.col('T1').is_not_null()
                     & pl.col('net1d').is_not_null()
                     & pl.col('am_range30').is_not_null())
    host = host.with_columns(
        ((pl.col('F01').rank(method='ordinal').over('date') - 1.0)
         / pl.len().over('date')).alias('_pct_f01'))
    host = host.filter(pl.col('_pct_f01') <= 0.10)
    n_host = host.height
    use_stats: dict = {'n_host': n_host}
    gate_use = False
    if n_host >= 200:
        host = host.with_columns(
            ((pl.col('am_range30').rank(method='ordinal').over('date') - 1.0)
             / pl.len().over('date')).alias('_pct_ar30'))
        before = host['net1d'].to_numpy()
        after = host.filter(pl.col('_pct_ar30') <= 0.75)['net1d'].to_numpy()
        p5_b = float(np.percentile(before, 5))
        p5_a = float(np.percentile(after, 5))
        improve = p5_improvement(p5_b, p5_a)
        mean_b = float(before.mean())
        mean_a = float(after.mean())
        cost = mean_b - mean_a
        use_stats.update({
            'p5_before': p5_b, 'p5_after': p5_a, 'p5_improvement': improve,
            'mean_net_before': mean_b, 'mean_net_after': mean_a,
            'mean_net_cost': cost, 'n_after': int(after.size)})
        gate_use = use_gate_pass(improve, cost)
    return {
        'ic': stats,
        'residual': {'mean_ic': resid_mean, 'nw_t': resid_nw,
                     'n_days': ric.height},
        'use_gate': use_stats,
        'gates': {'prediction': gate_ic and gate_resid, 'use': gate_use},
        'passed': bool((gate_ic and gate_resid) and gate_use),
    }


def u6_judge(panel: pl.DataFrame, lo: date, hi: date) -> dict:
    """U6 H-45 auction volume burst: first_bar_vol >= 5 x med20.
    Primary gate: same-day T1 - pool equal weight <= -0.3pp with t >= 3.
    Orthogonality: mean per-day Spearman(auction_ratio, F07) < 0.7 and
    (., F03) < 0.7 AND F03-controlled residual event effect <= -0.15pp
    with NW|t| >= 3 - otherwise the unit is downgraded to an execution
    note and does not occupy a hypothesis slot."""
    df = panel.filter(pl.col('date').is_between(lo, hi)
                      & pl.col('T1').is_not_null()
                      & pl.col('first_bar_vol_med20').is_not_null()
                      & (pl.col('first_bar_vol_med20') > 0))
    event = pl.col('first_bar_vol') >= U6_VOL_MULT * pl.col(
        'first_bar_vol_med20')
    n_events = int(df.filter(event).height)
    diffs = pool_baseline_diffs(df, event, lo, hi, target='T1')
    g = diff_gate(diffs, U6_DIFF_MAX, lo, hi)
    gate_primary = (g['mean_diff'] is not None
                    and g['mean_diff'] <= U6_DIFF_MAX
                    and g['nw_t'] is not None
                    and abs(g['nw_t']) >= U1_NW_T_MIN)

    ratio = pl.col('first_bar_vol') / pl.col('first_bar_vol_med20')

    def mean_daily_rho(other: str) -> float | None:
        sub = (df.filter(pl.col(other).is_not_null())
                 .select('date', ratio.alias('_r'), pl.col(other)))
        per = (sub.group_by('date')
                  .agg(pl.corr('_r', other, method='spearman').alias('rho'),
                       pl.len().alias('n'))
                  .filter((pl.col('n') >= MIN_IC_STOCKS)
                          & pl.col('rho').is_finite()))
        return float(per['rho'].mean()) if per.height else None

    rho_f07 = mean_daily_rho('F07')
    rho_f03 = mean_daily_rho('F03')

    # per-day F03-controlled residual event effect on T1 excess
    dfx = df.with_columns(
        (pl.col('T1') - pl.col('T1').mean().over('date'))
          .alias('t1_excess'),
        event.fill_null(False).alias('_ev'),
        pl.col('F03').rank(method='average').over('date').alias('_rf03'))
    coefs: list[float] = []
    for (_,), gday in dfx.filter(pl.col('_rf03').is_not_null()).group_by(
            ['date'], maintain_order=True):
        ev = gday.filter(pl.col('_ev'))
        if ev.height < U6_MIN_EVENTS_PER_DAY:
            continue
        y = gday['t1_excess'].to_numpy()
        x = np.column_stack([np.ones(gday.height), gday['_ev'].to_numpy(),
                             gday['_rf03'].to_numpy()])
        beta, *_ = np.linalg.lstsq(x, y, rcond=None)
        coefs.append(float(beta[1]))
    coef_mean = float(np.mean(coefs)) if coefs else None
    coef_nw = newey_west_t(coefs, NW_LAG) if coefs else None
    ortho = (rho_f07 is not None and rho_f03 is not None
             and rho_f07 < U6_RHO_MAX and rho_f03 < U6_RHO_MAX
             and coef_mean is not None and coef_mean <= U6_RESID_EFFECT_MAX
             and coef_nw is not None and abs(coef_nw) >= U1_NW_T_MIN)

    # disclosure split: gap-up vs gap-down bursts (F04 = open/preclose - 1)
    split = {}
    for name, cond in (('gap_up', pl.col('preclose_official').is_not_null()
                        & (pl.col('open_930') >= pl.col('preclose_official'))),
                       ('gap_down', pl.col('preclose_official').is_not_null()
                        & (pl.col('open_930') < pl.col('preclose_official')))):
        d = pool_baseline_diffs(df, event, lo, hi, target='T1',
                                extra_filter=cond)
        gg = diff_gate(d, U6_DIFF_MAX, lo, hi)
        split[name] = {'mean_diff': gg['mean_diff'], 'nw_t': gg['nw_t'],
                       'n_days': gg['n_days']}
    return {
        'n_events': n_events, 'base_rate': (n_events / df.height
                                            if df.height else None),
        'diffs': g, 'split': split,
        'orthogonality': {'rho_f07': rho_f07, 'rho_f03': rho_f03,
                          'resid_coef_mean': coef_mean,
                          'resid_coef_nw_t': coef_nw,
                          'n_coef_days': len(coefs)},
        'gates': {'primary': gate_primary, 'orthogonality': bool(ortho)},
        'passed': bool(gate_primary and ortho),
        'downgraded_execution_note': bool(gate_primary and not ortho),
    }


UNIT_JUDGES: Final = {'U1': u1_judge, 'U2': u2_judge, 'U3': u3_judge,
                      'U4': u4_judge, 'U5': u5_judge, 'U6': u6_judge}


def run_dev_and_val(panel: pl.DataFrame) -> dict:
    """Dev judgment for all six units; val (2021-2024) once for dev
    passers only, direction frozen by the dev hypothesis."""
    out: dict[str, dict] = {}
    for uid, fn in UNIT_JUDGES.items():
        dev = fn(panel, DEV_START, DEV_END)
        entry: dict = {'dev': dev}
        if dev['passed']:
            entry['val'] = fn(panel, VAL_START, VAL_END)
        out[uid] = entry
    return out
