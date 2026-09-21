"""P2-R12 event veto chain (exp-20260918-p2r12-event-veto).

Implements the frozen preregistration
``docs/research/exp-20260918-p2r12-event-veto-prereg.md`` and
``configs/experiments/p2r12-event-veto.json``: five point-in-time event veto
marks (C01 unlock-ahead / C02 forecast downgrade / C03 disclosure-day
proximity / C04 company-level holder selling / C05 accrual extreme) judged
against same-day matched controls, plus the C06 veto-chain combination on the
equal-weight pool host and the C07 unlock x holder-sale overlap structure
(non-judging adjunct).

Registered time contract (uniform for every unit, mirrors the P2 screen
layer): the signal is generated at the close of signal session ``t``; marks
use only information with knowledge date <= ``t``; matching covariates
(prior-5-session return decile, free-float value quintile) are the ``t``
close cross-section of the eligible pool; entry is the open of ``t+1``; the
N-session forward label runs from the ``t+1`` open to the ``t+N`` close
(N sessions counted after the signal session), adjusted with the repository
xiaodefa adj_factor contract (``adjusted = price * adj_factor``; return
ratios are level-normalization free).  Entry and exit sessions must be
tradable.

Freeze discipline: every date-bearing input is filtered to ``<= 2024-12-31``
at load and re-asserted after filtering; labels may never cross the freeze
line.  Events are veto/filters only - nothing here can act as an entry
trigger.

Registered implementation decisions (disclosed; the prereg is silent on
these combiners, no criterion/threshold/pool is changed):
- control = same signal session, same (ret5 decile x circ_mv quintile) cell,
  unmarked by that unit's mark, closest prior-5-session return, ties by
  symbol; one control per event, control reuse allowed;
- Bootstrap 2,000 resamples, seed 17, clustered by signal session;
- C01 event = the activation signal session per unlock group (first session
  on which the veto becomes active), not every active session;
- C04 events collapse raw rows to one event per (ts_code, ann_date) at the
  max change_ratio; the G/P asymmetry arm pools G and P holders;
- C04 segment combiner: the unit passes only if both 2017-05-27 segments
  pass the primary gate; the val window necessarily judges the post segment
  only (pre has no val coverage) - disclosed;
- C03 gate (b) primary proxy for "limit-down blocked exit" = the scheduled
  exit session (t+5) closes sealed at its down_limit; the any-sellable-day
  variant (t+2..t+5) is reported alongside;
- C05 incidence cohorts are fiscal-year accrual cross-sections; a cohort is
  judged only when its full 12-month incidence window lies inside the
  forecast family coverage and the freeze line;
- C06 "P5 improvement" = (q05_kept - q05_host) / |q05_host| >= 0.10 and
  "mean loss per vetoed entry" = mean(fwd5[vetoed]) - mean(fwd5[host]).
"""
from __future__ import annotations

from datetime import date
from typing import Final

import numpy as np
import polars as pl

FREEZE_END: Final[date] = date(2024, 12, 31)
DEV_RANGE: Final[tuple[date, date]] = (date(2015, 1, 5), date(2020, 12, 31))
VAL_RANGE: Final[tuple[date, date]] = (date(2021, 1, 1), date(2024, 12, 31))
DEV_END: Final[date] = DEV_RANGE[1]

SEED: Final[int] = 17
N_BOOT: Final[int] = 2000

# frozen unit thresholds (configs/experiments/p2r12-event-veto.json, verbatim)
C01_PRIMARY_MAX: Final[float] = -0.003       # 5d excess <= -0.3pp
C01_NOREBOUND_MAX: Final[float] = -0.002     # 10d cumulative excess <= -0.2pp
C02_PRIMARY_MAX: Final[float] = -0.005       # downgrade group 5d <= -0.5pp
C02_DEEP_MAX: Final[float] = -0.010          # deep group <= -1.0pp
C02_DEEP_GAP: Final[float] = 0.003           # worse than first-negative >= 0.3pp
C02_MIN_SAMPLE: Final[int] = 300             # < 300 -> insufficient evidence
C03_TAIL_MIN: Final[float] = 0.015           # P5 gap >= 1.5pp
C03_BLOCK_RATIO: Final[float] = 2.0          # blocked-exit rate >= 2x
C03_MEAN_CAP: Final[float] = 0.0015          # mean loss <= 0.15pp
C04_PRIMARY_MAX: Final[float] = -0.005       # C-DE 10d <= -0.5pp
C04_GP_BOUND: Final[float] = 0.002           # G/P |diff| < 0.2pp
C05_INCIDENCE_RATIO: Final[float] = 1.5      # >= 1.5x same pool
C05_SECONDARY_MAX: Final[float] = -0.010     # 60d excess <= -1pp
C06_MEAN_LOSS_MAX: Final[float] = 0.001      # <= 0.1pp per vetoed entry
C06_TAIL_GAIN: Final[float] = 0.10           # P5 improvement >= 10%
C06_CUT_MAX: Final[float] = 0.15             # cut share <= 15%

# marks (frozen verbatim)
C01_MIN_FLOAT_RATIO: Final[float] = 1.0          # aggregated float_ratio >= 1%
C01_WINDOW_SESSIONS: Final[int] = 20             # float_date within next 20 sessions
C02_DEEP_PCM_DROP: Final[float] = 20.0           # p_change_min downshift >= 20pp
C03_WINDOW_SESSIONS: Final[int] = 3              # entry 1..3 sessions before pre_date
C04_MIN_CHANGE_RATIO: Final[float] = 0.5         # change_ratio >= 0.5%
C05_TOP_DECILE: Final[float] = 0.90              # top decile of cross-section
C04_SEGMENT_SPLIT: Final[date] = date(2017, 5, 27)

# forward horizons (sessions after the signal session; label = open(t+1)->close(t+N))
FWD_5: Final[int] = 5
FWD_10: Final[int] = 10
FWD_60: Final[int] = 60

# universe / pool (frozen)
AMOUNT_MED_WINDOW: Final[int] = 20
AMOUNT_MIN: Final[float] = 50_000_000.0
PRICE_MIN: Final[float] = 2.0
NEW_LISTING_SESSIONS: Final[int] = 120

#: adjustment-factor series of this stock oscillates between two levels
#: (data/_meta deep-scan blocker); its adjusted series is banned for return
#: computation until manually re-checked -> excluded fail-closed.
BANNED_ADJ_SYMBOLS: Final[frozenset[str]] = frozenset({'sh.600069'})

# C05 financial-industry exclusion (registered rule: xiaodefa stock_basic
# industry snapshot; stocks with unavailable industry attribution are
# excluded fail-closed).  Source: data/raw/xiaodefa/stock_basic/20260913-bulk1.
FINANCIAL_INDUSTRIES: Final[tuple[str, ...]] = ('银行', '保险', '证券')

STAMP_SEGMENTS: Final[tuple[tuple[date, float], ...]] = (
    (date(2015, 1, 1), 0.001),
    (date(2023, 8, 28), 0.0005),
)

IMPROVE_TYPES: Final[frozenset[str]] = frozenset({'预增', '略增', '扭亏', '续盈'})
WORSEN_TYPES: Final[frozenset[str]] = frozenset({'预减', '略减', '首亏', '续亏'})

DAILY_PARQUET: Final[str] = 'data/processed/baostock-daily-20260917/daily_2015_2024.parquet'
DAILY_1999_PARQUET: Final[str] = 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
EVENT_DIR: Final[str] = 'data/features/event-factors-v1-20260918'
ADJ_DIR: Final[str] = 'data/raw/xiaodefa/adj_factor/20260913-bulk1'
STK_LIMIT_DIR: Final[str] = 'data/raw/xiaodefa/stk_limit/20260913-bulk1'
STOCK_BASIC_DIR: Final[str] = 'data/raw/xiaodefa/stock_basic/20260913-bulk1'
CALENDAR_CSV: Final[str] = 'data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv'

#: C06 host starts where every family has coverage (disclosure_date 2019+)
C06_HOST_START: Final[date] = date(2019, 1, 1)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def ts_to_symbol(ts_code: str) -> str:
    code, suffix = ts_code.split('.')
    return ('sh.' if suffix == 'SH' else 'sz.') + code


def ts_symbol_expr() -> pl.Expr:
    """Vectorized ts_code -> repo symbol conversion."""
    return pl.concat_str([
        pl.when(pl.col('ts_code').str.ends_with('.SH')).then(pl.lit('sh.'))
          .otherwise(pl.lit('sz.')),
        pl.col('ts_code').str.slice(0, 6),
    ])


def is_standard_a_share_expr() -> pl.Expr:
    return pl.col('ts_code').str.contains(r'^\d{6}\.(SH|SZ)$')


def stamp_for(day: date) -> float:
    rate = STAMP_SEGMENTS[0][1]
    for from_date, seg_rate in STAMP_SEGMENTS:
        if day >= from_date:
            rate = seg_rate
        else:
            break
    return rate


def net_return(gross: float, day: date, notional: float = 20_000.0) -> float:
    """Net of one round trip at ``notional``: wan-1 commission (5-yuan min)
    both legs + historical segmented stamp duty on the sell leg."""
    buy_fee = max(notional * 0.0001, 5.0)
    exit_notional = notional * (1.0 + gross)
    sell_fee = max(notional * 0.0001, 5.0) + exit_notional * stamp_for(day)
    return (exit_notional - sell_fee) / (notional + buy_fee) - 1.0


class Calendar:
    """Trading-day calendar with positional lookups (the 2,431-session
    2015-01-05..2024-12-31 CSI000300 day set used by the event tables)."""

    def __init__(self, dates: pl.Series):
        if dates.dtype != pl.Date:
            raise ValueError('calendar dates must be pl.Date')
        self.dates: pl.Series = dates.unique().sort()
        self.n: int = self.dates.len()
        self._np = self.dates.to_numpy().astype('datetime64[D]')
        self._frame = pl.DataFrame({'date': self.dates}).with_row_index('pos')

    def pos_at_or_after(self, day: date) -> int | None:
        """Index of the first session on or after ``day`` (None beyond end)."""
        import numpy as _np
        idx = int(_np.searchsorted(self._np, _np.datetime64(day), side='left'))
        return idx if idx < self.n else None

    def date_at(self, pos: int) -> date:
        if not 0 <= pos < self.n:
            raise ValueError(f'calendar position {pos} out of range')
        return self.dates[pos]

    def expand_ranges(self, ranges: pl.DataFrame) -> pl.DataFrame:
        """(symbol, t0, t1) inclusive session ranges -> (symbol, pos) rows."""
        return (ranges
                .filter(pl.col('t0') <= pl.col('t1'))
                .with_columns(pl.int_ranges('t0', pl.col('t1') + 1).alias('pos'))
                .explode('pos')
                .select('symbol', 'pos'))


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def load_calendar(root) -> Calendar:
    df = pl.read_csv(root / CALENDAR_CSV)
    days = df['trade_date'].cast(pl.String).str.to_date('%Y%m%d')
    return Calendar(days)


def load_adjustment_factors_fast(root, end: date = FREEZE_END) -> pl.DataFrame:
    """Long (symbol, date, adj_factor) frame for chunks within the freeze.

    Same source and contract as ``quant.data.adjustment`` (sha256-verified
    batch), read through one glob scan; conversion vectorized.
    """
    return (
        pl.scan_csv(root / ADJ_DIR / 'chunk_*.csv')
        .select(pl.col('ts_code'), pl.col('trade_date').cast(pl.String),
                pl.col('adj_factor'))
        .with_columns(pl.col('trade_date').str.to_date('%Y%m%d').alias('date'),
                      ts_symbol_expr().alias('symbol'))
        .filter(pl.col('date') <= end)
        .select('symbol', 'date', 'adj_factor')
        .collect()
    )


def load_listing_index(root) -> pl.DataFrame:
    """1-based index of the session within the symbol's traded sessions
    (tradestatus==1 rows only; suspensions do not advance), computed on the
    full 1999-2024 standardized table so listing ages are exact."""
    return (
        pl.scan_parquet(root / DAILY_1999_PARQUET)
        .filter(pl.col('tradestatus') == 1.0)
        .select('symbol', 'date',
                pl.int_range(pl.len()).over('symbol', order_by='date')
                .add(1).alias('listing_index'))
        .collect()
    )


def load_circ_mv(root, end: date = FREEZE_END) -> pl.DataFrame:
    """(symbol, date, circ_mv) from daily_basic r2 (2015-2018) + r1 (2019+).

    The two batches have zero key overlap (asserted); daily-basic fields are
    known on the session itself.
    """
    parts = []
    for batch in ('data/raw/tushare/daily_basic/20260913-r2',
                  'data/raw/tushare/daily_basic/20260909-r1'):
        parts.append(
            pl.scan_csv(root / batch / 'chunk_*.csv')
            .select(pl.col('ts_code'), pl.col('trade_date').cast(pl.String),
                    pl.col('circ_mv'))
            .with_columns(pl.col('trade_date').str.to_date('%Y%m%d').alias('date'),
                          ts_symbol_expr().alias('symbol'))
            .filter(pl.col('date') <= end)
            .select('symbol', 'date', 'circ_mv')
            .collect())
    overlap = parts[0].join(parts[1], on=['symbol', 'date'], how='inner').height
    if overlap:
        raise ValueError(f'daily_basic r1/r2 key overlap: {overlap} rows')
    out = pl.concat(parts).sort('symbol', 'date')
    if out['date'].max() > end:
        raise ValueError('circ_mv freeze filter failed')
    return out


def load_down_limit(root, start: date, end: date = FREEZE_END) -> pl.DataFrame:
    """(symbol, date, down_limit) from xiaodefa stk_limit day chunks.

    Columns are taken by name (deep-scan rule); the single empty-header chunk
    (chunk_20220705.csv) is read header-less with explicit column names.
    """
    columns = ['trade_date', 'ts_code', 'up_limit', 'down_limit']
    good: list = []
    bad_file = None
    for path in sorted((root / STK_LIMIT_DIR).glob('chunk_*.csv')):
        with open(path, 'rb') as fh:
            if fh.readline().strip() == b'':
                bad_file = path
            else:
                good.append(path)

    def _norm(frame: pl.DataFrame) -> pl.DataFrame:
        return (frame
                .select(pl.col('trade_date').cast(pl.String), pl.col('ts_code'),
                        pl.col('down_limit'))
                .with_columns(pl.col('trade_date').str.to_date('%Y%m%d').alias('date'),
                              ts_symbol_expr().alias('symbol'))
                .filter((pl.col('date') >= start) & (pl.col('date') <= end))
                .select('symbol', 'date', 'down_limit'))

    frames = [_norm(pl.scan_csv(good).collect())] if good else []
    if bad_file is not None:
        frames.append(_norm(pl.read_csv(bad_file, has_header=False, skip_rows=1,
                                        new_columns=columns)))
    out = pl.concat(frames).sort('symbol', 'date')
    if out['date'].max() > end or out['date'].min() < start:
        raise ValueError('stk_limit date filter failed')
    return out


def load_financial_industries(root) -> pl.DataFrame:
    """(ts_code, industry) A-share snapshot from xiaodefa stock_basic."""
    frames = [pl.read_csv(chunk, infer_schema_length=0).select('ts_code', 'industry')
              for chunk in sorted((root / STOCK_BASIC_DIR).glob('chunk_*.csv'))]
    out = (pl.concat(frames)
           .filter(is_standard_a_share_expr())
           .unique(subset='ts_code', keep='first'))
    if out['ts_code'].n_unique() != out.height:
        raise ValueError('duplicate ts_code in stock_basic snapshot')
    return out


# --------------------------------------------------------------------------- #
# daily frame with labels, covariates and limit seals
# --------------------------------------------------------------------------- #
def attach_labels(daily: pl.DataFrame) -> pl.DataFrame:
    """ret5 covariate + forward labels/exit dates on an adjusted daily frame.

    Requires columns (symbol, date, tradestatus) sorted by (symbol, date)
    with a contiguous calendar row space per symbol; adjusted levels come
    from ``adj_close``/``adj_open`` when present, otherwise they are computed
    as ``close/open * adj_factor``.  Exit at session t+N, entry at t+1, both
    must be tradable.
    """
    if 'adj_close' not in daily.columns:
        daily = daily.with_columns(
            (pl.col('close') * pl.col('adj_factor')).alias('adj_close'),
            (pl.col('open') * pl.col('adj_factor')).alias('adj_open'))
    daily = daily.with_columns(
        (pl.col('adj_close') / pl.col('adj_close').shift(5).over('symbol') - 1.0)
        .alias('ret5'),
        pl.col('adj_open').shift(-1).over('symbol').alias('_entry_adj'),
        pl.col('tradestatus').shift(-1).over('symbol').alias('_entry_ts'),
    )
    for n in (FWD_5, FWD_10, FWD_60):
        daily = daily.with_columns(
            pl.col('adj_close').shift(-n).over('symbol').alias(f'_exit_adj{n}'),
            pl.col('tradestatus').shift(-n).over('symbol').alias(f'_exit_ts{n}'),
            pl.col('date').shift(-n).over('symbol').alias(f'exit{n}_date'),
        )
        valid = ((pl.col('_entry_ts').fill_null(0) == 1.0)
                 & (pl.col(f'_exit_ts{n}').fill_null(0) == 1.0)
                 & pl.col('_entry_adj').is_not_null()
                 & pl.col(f'_exit_adj{n}').is_not_null())
        daily = daily.with_columns(
            pl.when(valid)
            .then(pl.col(f'_exit_adj{n}') / pl.col('_entry_adj') - 1.0)
            .otherwise(None).alias(f'fwd{n}'))
    return daily.drop([c for c in daily.columns if c.startswith('_')
                       and c != '_i'])


def attach_block_flags(daily: pl.DataFrame) -> pl.DataFrame:
    """Blocked-exit proxies from the ``seal`` column (limit-down sealed
    close): exit-session (t+5) and any sellable session (t+2..t+5, T+1)."""
    return daily.with_columns(
        pl.col('seal').shift(-FWD_5).over('symbol').alias('block5_exit'),
        pl.any_horizontal(
            [pl.col('seal').shift(-k).over('symbol') for k in (2, 3, 4, FWD_5)]
        ).alias('block5_window'),
    )


def build_daily_frame(root, calendar: Calendar) -> tuple[pl.DataFrame, dict]:
    """Base daily frame: adjusted levels, prior-5 return, forward labels
    (5/10/60), exit dates, limit seals, listing age and pool eligibility."""
    from quant.research.screen import eligible_universe

    counts: dict = {}
    daily = pl.read_parquet(root / DAILY_PARQUET)
    counts['daily_rows'] = daily.height
    if daily['date'].max() > FREEZE_END:
        raise ValueError('daily table exceeds freeze line')
    factors = load_adjustment_factors_fast(root)
    counts['factor_rows'] = factors.height
    daily = (daily.select('symbol', 'date', 'open', 'close', 'amount',
                          'tradestatus', 'isST')
             .join(factors, on=['symbol', 'date'], how='left')
             .sort('symbol', 'date'))
    del factors
    daily = daily.with_columns(
        (pl.col('close') * pl.col('adj_factor')).alias('adj_close'),
        (pl.col('open') * pl.col('adj_factor')).alias('adj_open'),
        pl.col('open').alias('_open_raw'),
        pl.col('close').alias('_close_raw'),
        pl.int_range(pl.len()).over('symbol', order_by='date').alias('_i'),
    ).drop('open', 'close')
    # row-space contiguity: rows per symbol == session span + 1 (so shifts
    # over('symbol') are calendar-exact)
    span = daily.group_by('symbol').agg(pl.col('_i').min().alias('i0'),
                                        pl.col('_i').max().alias('i1'),
                                        pl.len().alias('n'))
    bad = span.filter((pl.col('i1') - pl.col('i0') + 1) != pl.col('n'))
    counts['noncontiguous_symbols'] = bad.height
    if bad.height:
        raise ValueError(f'{bad.height} symbols with non-contiguous row space')
    del span

    n_banned = daily.filter(pl.col('symbol').is_in(sorted(BANNED_ADJ_SYMBOLS))).height
    counts['banned_adj_rows_dropped'] = n_banned
    daily = daily.filter(~pl.col('symbol').is_in(sorted(BANNED_ADJ_SYMBOLS)))

    # pool eligibility before slimming (needs the raw close and amount)
    elig = eligible_universe(
        daily.select('symbol', 'date', '_close_raw', 'amount', 'tradestatus',
                     'isST')
        .rename({'_close_raw': 'close'}),
        amount_median_window=AMOUNT_MED_WINDOW, amount_min=AMOUNT_MIN,
        price_min=PRICE_MIN, allow_chinext=False)

    # limit-down seal; stk_limit loaded for the C03-relevant years 2019+
    limits = load_down_limit(root, date(2019, 1, 1))
    counts['stk_limit_rows'] = limits.height
    daily = (daily.join(limits, on=['symbol', 'date'], how='left')
             .with_columns((pl.col('_close_raw') <= pl.col('down_limit') + 1e-6)
                           .alias('seal'))
             .drop('down_limit'))
    del limits

    daily = attach_labels(daily)
    daily = attach_block_flags(daily)

    listing = load_listing_index(root)
    counts['listing_rows'] = listing.height
    elig = (elig.join(listing, on=['symbol', 'date'], how='left')
            .filter(pl.col('listing_index') > NEW_LISTING_SESSIONS)
            .select('symbol', 'date'))
    del listing
    counts['eligible_rows'] = elig.height

    keep = ['symbol', 'date', 'ret5', 'fwd5', 'fwd10', 'fwd60',
            'exit5_date', 'exit10_date', 'exit60_date',
            'block5_exit', 'block5_window']
    daily = (daily.select(keep)
             .join(elig, on=['symbol', 'date'], how='inner')
             .sort('symbol', 'date'))
    del elig
    if daily['date'].max() > FREEZE_END:
        raise ValueError('freeze violation after daily build')
    return daily, counts


def build_session_frame(daily: pl.DataFrame, circ_mv: pl.DataFrame,
                        calendar: Calendar) -> pl.DataFrame:
    """Eligible-pool signal-session frame S: covariates, bins, labels."""
    s = (daily.join(circ_mv, on=['symbol', 'date'], how='left')
         .filter(pl.col('ret5').is_not_null() & pl.col('circ_mv').is_not_null()))
    s = (s
         .with_columns(
             (((pl.col('ret5').rank(method='ordinal').over('date') - 1.0)
               / pl.len().over('date') * 10.0).floor().clip(0, 9) + 1)
             .cast(pl.Int32).alias('d5'),
             (((pl.col('circ_mv').rank(method='ordinal').over('date') - 1.0)
               / pl.len().over('date') * 5.0).floor().clip(0, 4) + 1)
             .cast(pl.Int32).alias('q5'))
         .join(calendar._frame, on='date', how='inner')
         .select('symbol', 'date', 'pos',
                 pl.col('date').dt.year().alias('year'),
                 'fwd5', 'fwd10', 'fwd60',
                 'exit5_date', 'exit10_date', 'exit60_date',
                 'block5_exit', 'block5_window', 'ret5', 'circ_mv', 'd5', 'q5')
         .sort('symbol', 'date'))
    return s


# --------------------------------------------------------------------------- #
# event builders (pure; testable on synthetic frames)
# --------------------------------------------------------------------------- #
def build_unlock_events(sf: pl.DataFrame, calendar: Calendar,
                        start: date = DEV_RANGE[0]) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """C01 unlock-ahead veto: activation signal sessions + active ranges.

    Mark: ts_knowledge <= signal session t, aggregated float_ratio >= 1%,
    agg_ann_date_count == 1, and the float date (mapped to its first session)
    2..21 sessions after t (entry t+1 lies within the 20 sessions before the
    float).  A group announced at/after its float date can never mark (PIT).
    """
    counts: dict = {}
    df = (sf.filter(pl.col('in_pool'))
          .filter(pl.col('agg_ann_date_count') == 1)
          .filter(pl.col('magnitude').is_not_null()
                  & (pl.col('magnitude') >= C01_MIN_FLOAT_RATIO))
          .select('event_id', 'ts_code', 'ts_event', 'ts_knowledge', 'magnitude'))
    counts['groups_passing_thresholds'] = df.height
    df = df.with_columns(ts_symbol_expr().alias('symbol')).drop('ts_code')
    rows: list[dict] = []
    ranges: list[dict] = []
    dropped = {'announced_at_or_after_float': 0, 'out_of_calendar': 0,
               'activation_before_window_start': 0}
    for rec in df.iter_rows(named=True):
        fpos = calendar.pos_at_or_after(rec['ts_event'])
        t_first = calendar.pos_at_or_after(rec['ts_knowledge'])
        if fpos is None or t_first is None:
            dropped['out_of_calendar'] += 1
            continue
        if rec['ts_knowledge'] >= rec['ts_event']:
            dropped['announced_at_or_after_float'] += 1
            continue
        lo = max(t_first, fpos - (C01_WINDOW_SESSIONS + 1))
        if lo > fpos - 2:
            dropped['out_of_calendar'] += 1
            continue
        if calendar.date_at(lo) < start:
            dropped['activation_before_window_start'] += 1
            continue
        rows.append({'event_id': rec['event_id'], 'symbol': rec['symbol'],
                     'pos': lo, 'float_pos': fpos, 'magnitude': rec['magnitude']})
        ranges.append({'symbol': rec['symbol'], 't0': lo, 't1': fpos - 2})
    counts.update(dropped)
    events = pl.DataFrame(rows, schema={
        'event_id': pl.String, 'symbol': pl.String, 'pos': pl.Int64,
        'float_pos': pl.Int64, 'magnitude': pl.Float64}, orient='row')
    ranges_df = pl.DataFrame(ranges, schema={
        'symbol': pl.String, 't0': pl.Int64, 't1': pl.Int64}, orient='row')
    return events, ranges_df, counts


def build_disclosure_ranges(dd: pl.DataFrame, calendar: Calendar,
                            start: date = DEV_RANGE[0]) -> tuple[pl.DataFrame, dict]:
    """C03 disclosure-proximity active signal sessions.

    Mark: ts_knowledge <= t and the scheduled disclosure day (first session
    at/after pre_date) 2..4 sessions after t, i.e. entry day t+1 is 1..3
    sessions before the disclosure.
    """
    counts: dict = {'records': dd.height}
    df = (dd.filter(pl.col('in_pool'))
          .select('ts_code', 'ts_event', 'ts_knowledge'))
    df = df.with_columns(ts_symbol_expr().alias('symbol')).drop('ts_code')
    ranges: list[dict] = []
    dropped = 0
    for rec in df.iter_rows(named=True):
        ppos = calendar.pos_at_or_after(rec['ts_event'])
        t_first = calendar.pos_at_or_after(rec['ts_knowledge'])
        if ppos is None or t_first is None:
            dropped += 1
            continue
        lo = max(ppos - (C03_WINDOW_SESSIONS + 1), t_first)
        hi = ppos - 2
        if lo > hi:
            dropped += 1
            continue
        if calendar.date_at(hi) < start:
            continue
        ranges.append({'symbol': rec['symbol'], 't0': lo, 't1': hi})
    counts['records_out_of_calendar_or_empty'] = dropped
    ranges_df = pl.DataFrame(ranges, schema={
        'symbol': pl.String, 't0': pl.Int64, 't1': pl.Int64}, orient='row')
    return ranges_df, counts


def classify_forecast_type(ftype: str | None) -> int:
    """IMPROVE=0 / NEUTRAL=1 / WORSEN=2 ordering for forecast types."""
    if ftype in IMPROVE_TYPES:
        return 0
    if ftype in WORSEN_TYPES:
        return 2
    return 1


def _type_class_expr(col: str) -> pl.Expr:
    return (pl.when(pl.col(col).is_in(list(IMPROVE_TYPES))).then(0)
            .when(pl.col(col).is_in(list(WORSEN_TYPES))).then(2)
            .otherwise(1))


def build_forecast_chains(raw: pl.DataFrame, calendar: Calendar) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """C02 forecast-revision chains from the full-version raw batch.

    Chain group = (ts_code, end_date), ordered by
    (coalesce(first_ann_date, ann_date), ann_date, update_flag); first and
    tail versions compared.  Downgrade = type class worsens OR p_change_min
    moves down; deep = improve->worsen type jump OR p_change_min downshift
    >= 20pp.  Event signal session = first session at/after the TAIL
    announcement (known at that close, entry next open).  Freeze filter:
    announcements after 2024-12-31 never enter.
    """
    counts: dict = {}
    df = (raw.filter(is_standard_a_share_expr())
          .with_columns(pl.col('ann_date').cast(pl.String).str.to_date('%Y%m%d').alias('ann'),
                        pl.col('end_date').cast(pl.String).str.to_date('%Y%m%d').alias('end'))
          .filter(pl.col('ann') <= FREEZE_END))
    counts['rows_in_freeze'] = df.height
    df = df.with_columns(
        pl.coalesce(pl.col('first_ann_date').cast(pl.String).str.to_date('%Y%m%d'),
                    pl.col('ann')).alias('order_key'),
        pl.col('update_flag').cast(pl.Int64).fill_null(0).alias('uf'),
        pl.col('type').cast(pl.String).alias('ftype'),
        pl.col('p_change_min').cast(pl.Float64, strict=False).alias('pcm'))
    df = (df.sort(['ts_code', 'end', 'order_key', 'ann', 'uf'])
          .group_by(['ts_code', 'end'], maintain_order=True)
          .agg(pl.len().alias('n_ver'),
               pl.col('ftype').first().alias('type_first'),
               pl.col('ftype').last().alias('type_tail'),
               pl.col('pcm').first().alias('pcm_first'),
               pl.col('pcm').last().alias('pcm_tail'),
               pl.col('ann').last().alias('ann_tail')))
    counts['chain_groups'] = df.height
    cls_f = _type_class_expr('type_first')
    cls_t = _type_class_expr('type_tail')
    df = df.with_columns(
        (cls_t > cls_f).alias('type_down'),
        (pl.col('pcm_first').is_not_null() & pl.col('pcm_tail').is_not_null()
         & (pl.col('pcm_tail') < pl.col('pcm_first'))).alias('pcm_down'),
        ((cls_f == 0) & (cls_t == 2)).alias('type_deep_jump'),
        (pl.col('pcm_first').is_not_null() & pl.col('pcm_tail').is_not_null()
         & ((pl.col('pcm_first') - pl.col('pcm_tail')) >= C02_DEEP_PCM_DROP)
         ).alias('pcm_deep'))
    revised = df.filter(pl.col('n_ver') >= 2)
    counts['multi_version_chains'] = revised.height
    down = revised.filter(pl.col('type_down') | pl.col('pcm_down'))
    counts['downgrade_events'] = down.height
    down = down.with_columns((pl.col('pcm_deep') | pl.col('type_deep_jump')).alias('deep'))
    counts['deep_events'] = int(down['deep'].sum()) if down.height else 0
    firstneg = df.filter((pl.col('n_ver') == 1) & (cls_f == 2))
    counts['first_negative_events'] = firstneg.height

    def to_events(frame: pl.DataFrame, extra: list[str]) -> pl.DataFrame:
        rows = []
        for rec in frame.iter_rows(named=True):
            t = calendar.pos_at_or_after(rec['ann_tail'])
            if t is None:
                continue
            row = {'symbol': ts_to_symbol(rec['ts_code']), 'pos': t}
            for col in extra:
                row[col] = bool(rec[col])
            rows.append(row)
        return pl.DataFrame(rows, orient='row') if rows else pl.DataFrame(
            schema={'symbol': pl.String, 'pos': pl.Int64})

    down_events = to_events(down, ['deep'])
    firstneg_events = to_events(firstneg, [])
    return down_events, firstneg_events, counts


def build_holdertrade_events(raw: pl.DataFrame, calendar: Calendar) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """C04 company-level (holder_type=C) and G/P decrease events.

    DE x holder_type x change_ratio >= 0.5%, one event per
    (ts_code, ann_date) at the max ratio; signal session = first session at
    or after the announcement; 2017-05-27 regime segment recorded.
    """
    counts: dict = {}
    df = (raw.filter(is_standard_a_share_expr())
          .with_columns(pl.col('ann_date').cast(pl.String).str.to_date('%Y%m%d').alias('ann'))
          .filter(pl.col('ann') <= FREEZE_END))
    counts['rows_in_freeze'] = df.height
    df = df.with_columns(pl.col('change_ratio').cast(pl.Float64, strict=False))

    def make(htypes: list[str], label: str) -> pl.DataFrame:
        part = (df.filter(pl.col('in_de') == 'DE')
                .filter(pl.col('holder_type').is_in(htypes))
                .filter(pl.col('change_ratio').is_not_null()
                        & (pl.col('change_ratio') >= C04_MIN_CHANGE_RATIO)))
        agg = (part.group_by(['ts_code', 'ann'])
               .agg(pl.col('change_ratio').max().alias('change_ratio'),
                    pl.len().alias('n_raw_rows')))
        rows = []
        for rec in agg.iter_rows(named=True):
            t = calendar.pos_at_or_after(rec['ann'])
            if t is None:
                continue
            rows.append({'symbol': ts_to_symbol(rec['ts_code']), 'pos': t,
                         'ann': rec['ann'], 'change_ratio': rec['change_ratio'],
                         'n_raw_rows': rec['n_raw_rows'],
                         'segment': 'pre' if rec['ann'] < C04_SEGMENT_SPLIT else 'post'})
        out = (pl.DataFrame(rows, orient='row') if rows else pl.DataFrame(
            schema={'symbol': pl.String, 'pos': pl.Int64, 'ann': pl.Date,
                    'change_ratio': pl.Float64, 'n_raw_rows': pl.UInt32,
                    'segment': pl.String}))
        counts[f'{label}_events'] = out.height
        return out

    c_events = make(['C'], 'c_de')
    gp_events = make(['G', 'P'], 'gp')
    return c_events, gp_events, counts


def pick_latest_report(df: pl.DataFrame) -> pl.DataFrame:
    """Per (ts_code, end_date) the row with the latest effective announcement
    (ann_date, fallback f_ann_date; both null fail-closed dropped), ties by
    update_flag then file order."""
    return (df.with_columns(
        pl.coalesce(pl.col('ann_date').cast(pl.String),
                    pl.col('f_ann_date').cast(pl.String)).alias('eff_ann'))
        .filter(pl.col('eff_ann').is_not_null())
        .with_columns(pl.col('eff_ann').str.to_date('%Y%m%d').alias('ann_eff'))
        .sort(['ts_code', 'end_date', 'ann_eff', 'update_flag'])
        .group_by(['ts_code', 'end_date'], maintain_order=True).last())


def build_accrual_cohorts(cashflow: pl.DataFrame, balancesheet: pl.DataFrame,
                          industries: pl.DataFrame,
                          calendar: Calendar) -> tuple[pl.DataFrame, dict]:
    """C05 annual-report accrual cohorts with PIT availability.

    accrual = (net_profit - n_cashflow_act) / total_assets on the latest PIT
    annual report; pit = max(effective ann_date, end_date + 90d); financial
    industries and stocks with unavailable industry attribution are excluded
    fail-closed; top decile of each fiscal-year cross-section = marked.
    Signal session t_signal = first session at/after pit.
    """
    counts: dict = {}
    cf = pick_latest_report(cashflow.select(
        'ts_code', 'ann_date', 'f_ann_date', 'end_date', 'net_profit',
        'n_cashflow_act', pl.col('update_flag').cast(pl.Int64).fill_null(0)))
    bs = pick_latest_report(balancesheet.select(
        'ts_code', 'ann_date', 'f_ann_date', 'end_date', 'total_assets',
        pl.col('update_flag').cast(pl.Int64).fill_null(0)))
    counts['cf_annual_keys'] = cf.height
    counts['bs_annual_keys'] = bs.height
    df = (cf.join(bs.select('ts_code', 'end_date', 'total_assets'),
                  on=['ts_code', 'end_date'], how='inner')
          .with_columns(pl.col('end_date').cast(pl.String).str.to_date('%Y%m%d')
                        .alias('end')))
    counts['joined_keys'] = df.height
    df = (df.filter(pl.col('end').dt.month() == 12)
          .with_columns(
              pl.max_horizontal(pl.col('ann_eff'),
                                pl.col('end').dt.offset_by('90d')).alias('pit'))
          .filter(pl.col('pit') <= FREEZE_END)
          .filter(pl.col('end').dt.year() >= 2014))
    counts['keys_pit_in_window'] = df.height
    df = (df.filter(pl.col('net_profit').is_not_null()
                    & pl.col('n_cashflow_act').is_not_null()
                    & pl.col('total_assets').is_not_null()
                    & (pl.col('total_assets') > 0))
          .with_columns(
              ((pl.col('net_profit') - pl.col('n_cashflow_act'))
               / pl.col('total_assets')).alias('accrual'),
              pl.col('end').dt.year().alias('fy')))
    counts['keys_with_valid_accrual'] = df.height

    fin = industries.filter(pl.col('industry').is_in(list(FINANCIAL_INDUSTRIES)))
    df = (df.join(fin.select(pl.col('ts_code'), pl.lit(True).alias('is_fin')),
                  on='ts_code', how='left')
          .join(industries.select(
              pl.col('ts_code'),
              pl.col('industry').is_not_null().alias('has_industry')),
              on='ts_code', how='left'))
    counts['financial_excluded'] = int(df['is_fin'].sum()) if df.height else 0
    counts['industry_unavailable_excluded'] = (int((~df['has_industry']).sum())
                                               if df.height else 0)
    df = df.filter(~pl.col('is_fin').fill_null(False)
                   & pl.col('has_industry').fill_null(False))
    counts['cohort_rows'] = df.height

    df = (df.with_columns(
        (pl.col('accrual').rank(method='average').over('fy') / pl.len().over('fy'))
        .alias('rank_pct'))
        .with_columns((pl.col('rank_pct') > C05_TOP_DECILE).alias('marked')))
    rows = []
    for rec in df.select('ts_code', 'fy', 'pit', 'accrual', 'marked', 'rank_pct') \
                 .iter_rows(named=True):
        t = calendar.pos_at_or_after(rec['pit'])
        if t is None:
            continue
        rows.append({'symbol': ts_to_symbol(rec['ts_code']), 'fy': rec['fy'],
                     'pit': rec['pit'], 'pos': t, 'accrual': rec['accrual'],
                     'marked': bool(rec['marked']), 'rank_pct': rec['rank_pct']})
    cohorts = pl.DataFrame(rows, orient='row') if rows else pl.DataFrame(
        schema={'symbol': pl.String, 'fy': pl.Int64, 'pit': pl.Date,
                'pos': pl.Int64, 'accrual': pl.Float64, 'marked': pl.Boolean,
                'rank_pct': pl.Float64})
    counts['cohorts_with_session'] = cohorts.height
    return cohorts.sort('symbol', 'pos'), counts


# --------------------------------------------------------------------------- #
# matching, windows and bootstrap
# --------------------------------------------------------------------------- #
def match_controls(s: pl.DataFrame, events: pl.DataFrame, flag_col: str,
                   ret_col: str = 'fwd5', carry_ctrl: tuple[str, ...] = (),
                   carry_event: tuple[str, ...] = ()) -> tuple[pl.DataFrame, dict]:
    """1:1 nearest-ret5 control per event within (date, d5, q5).

    Controls are S rows on the same signal session with ``flag_col`` == 0 and
    valid covariates.  Deterministic: smallest |ret5 difference|, ties by
    lexicographic symbol; one control per event, reuse allowed.
    ``carry_ctrl``/``carry_event`` copy additional S columns onto the control
    / event side (e.g. the 10-session label for C01's no-rebound arm).
    """
    counts = {'events': events.height}
    ev_cols = ['symbol', 'date', 'd5', 'q5', 'ret5', ret_col, *carry_event]
    ctrl_cols = ['symbol', 'date', 'd5', 'q5', 'ret5', ret_col, *carry_ctrl]
    ctrl_pool = (s.filter(pl.col(flag_col).fill_null(False) == 0)
                 .select(ctrl_cols)
                 .rename({'symbol': 'ctrl_symbol', 'ret5': 'ret5_ctrl',
                          ret_col: 'ret_ctrl',
                          **{c: f'{c}_ctrl' for c in carry_ctrl}}))
    ev = (events.join(s.select(ev_cols),
                      on=['symbol', 'date'], how='inner')
          .rename({ret_col: 'ret_event', 'ret5': 'ret5_event',
                   **{c: f'{c}_event' for c in carry_event}}))
    counts['events_with_covariates'] = ev.height
    pairs = (ev.join(ctrl_pool, on=['date', 'd5', 'q5'], how='left')
             .with_columns((pl.col('ret5_ctrl') - pl.col('ret5_event'))
                           .abs().alias('_dist')))
    matched = (pairs.sort(['date', 'symbol', '_dist', 'ctrl_symbol'],
                          nulls_last=True)
               .group_by(['date', 'symbol'], maintain_order=True).first()
               .drop('_dist'))
    n_cell_empty = int(matched['ret_ctrl'].is_null().sum())
    matched = matched.filter(pl.col('ret_ctrl').is_not_null())
    matched = matched.with_columns(
        (pl.col('ret_event') - pl.col('ret_ctrl')).alias('excess'))
    counts['matched'] = matched.height
    counts['no_candidate_in_cell'] = n_cell_empty
    counts['unmatched'] = counts['events_with_covariates'] - matched.height
    return matched, counts


def bootstrap_ci_mean(values, clusters, n_boot: int = N_BOOT, seed: int = SEED,
                      ci: float = 0.95) -> dict:
    """Day-clustered percentile bootstrap of the mean (seed 17, 2,000)."""
    values = np.asarray(values, dtype=np.float64)
    clusters = np.asarray(clusters)
    finite = np.isfinite(values)
    values, clusters = values[finite], clusters[finite]
    if values.size == 0:
        return {'mean': None, 'ci_lo': None, 'ci_hi': None, 'n': 0, 'n_clusters': 0}
    uniq, inv = np.unique(clusters, return_inverse=True)
    sums = np.bincount(inv, weights=values, minlength=uniq.size)
    cnts = np.bincount(inv, minlength=uniq.size).astype(np.float64)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, uniq.size, size=(n_boot, uniq.size))
    boot = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    alpha = (1.0 - ci) / 2.0
    return {'mean': float(values.mean()),
            'ci_lo': float(np.percentile(boot, 100 * alpha)),
            'ci_hi': float(np.percentile(boot, 100 * (1 - alpha))),
            'n': int(values.size), 'n_clusters': int(uniq.size)}


def assign_window(events: pl.DataFrame, exit_col: str = 'exit5_date') -> tuple[pl.DataFrame, dict]:
    """dev/val membership by signal session; dev rows whose label exit
    crosses 2020-12-31 are purged (P2 label-overlap convention)."""
    counts: dict = {}
    out = events.with_columns(
        pl.when(pl.col('date') <= DEV_END).then(pl.lit('dev'))
        .when(pl.col('date') >= VAL_RANGE[0]).then(pl.lit('val'))
        .otherwise(None).alias('window'))
    counts['events_total'] = out.height
    out = out.with_columns(
        pl.when((pl.col('window') == 'dev') & (pl.col(exit_col) > DEV_END))
        .then(None).otherwise(pl.col('window')).alias('window'))
    counts['purged_dev_exit_crossing'] = int(out['window'].is_null().sum())
    out = out.filter(pl.col('window').is_not_null())
    return out, counts


def year_consistency(per_year: list[dict], direction: str = 'negative',
                     threshold: float | None = None) -> dict:
    """分年同号 gate: same-sign in >= ceil(2/3 x covered years) (equals 4/6
    at six covered years; dev windows never exceed six years).  ``direction``
    is 'negative' (metric < 0), 'positive' (metric > 0) or 'above'
    (metric >= threshold)."""
    if direction == 'negative':
        same = [y for y in per_year if y['metric'] is not None and y['metric'] < 0]
    elif direction == 'positive':
        same = [y for y in per_year if y['metric'] is not None and y['metric'] > 0]
    elif direction == 'above' and threshold is not None:
        same = [y for y in per_year if y['metric'] is not None
                and y['metric'] >= threshold]
    else:
        raise ValueError(f'unsupported direction {direction!r}')
    n = len(per_year)
    required = int(np.ceil(2.0 / 3.0 * n)) if n else 0
    return {'n_years_covered': n, 'n_same_sign': len(same), 'required': required,
            'pass': bool(n >= 2 and len(same) >= required)}


def ci_excludes_zero(ci: dict | None, direction: str = 'negative') -> bool:
    if not ci or ci.get('ci_lo') is None:
        return False
    return bool(ci['ci_hi'] < 0) if direction == 'negative' else bool(ci['ci_lo'] > 0)


def window_excess_stats(matched: pl.DataFrame) -> dict:
    """Excess mean + clustered CI + per-year table for one matched frame."""
    if not matched.height:
        return {'n_matched': 0, 'mean_excess': None, 'ci': None,
                'per_year': [], 'years_gate': {'pass': False, 'n_years_covered': 0}}
    per_year = []
    for year in sorted(matched['year'].unique().to_list()):
        y = matched.filter(pl.col('year') == year)
        per_year.append({'year': int(year), 'n': y.height,
                         'metric': float(y['excess'].mean())})
    return {'n_matched': matched.height,
            'mean_excess': float(matched['excess'].mean()),
            'ci': bootstrap_ci_mean(matched['excess'].to_numpy(),
                                    matched['date'].to_numpy()),
            'per_year': per_year,
            'years_gate': year_consistency(per_year, 'negative')}


def run_excess_unit(events: pl.DataFrame, s: pl.DataFrame, flag_col: str,
                    ret_col: str, carry_ctrl: tuple[str, ...] = (),
                    carry_event: tuple[str, ...] = ()) -> tuple[pl.DataFrame, dict]:
    """Match -> dev/val windows with label purge -> window stats."""
    exit_col = 'exit' + ret_col[len('fwd'):] + '_date'
    matched, mcounts = match_controls(s, events, flag_col, ret_col=ret_col,
                                      carry_ctrl=carry_ctrl,
                                      carry_event=(*carry_event, exit_col))
    if exit_col + '_event' in matched.columns:
        matched = matched.rename({exit_col + '_event': exit_col})
    matched, wcounts = assign_window(matched, exit_col=exit_col)
    matched = matched.with_columns(pl.col('date').dt.year().alias('year'))
    out = {'dev': window_excess_stats(matched.filter(pl.col('window') == 'dev')),
           'val': window_excess_stats(matched.filter(pl.col('window') == 'val')),
           'counts': {**mcounts, **wcounts}}
    return matched, out


# --------------------------------------------------------------------------- #
# veto flags on S
# --------------------------------------------------------------------------- #
def attach_veto_flags(s: pl.DataFrame, calendar: Calendar,
                      unlock_ranges: pl.DataFrame, down_events: pl.DataFrame,
                      disclosure_ranges: pl.DataFrame, c_de_events: pl.DataFrame,
                      cohorts: pl.DataFrame) -> pl.DataFrame:
    """v1..v5 boolean columns on S (the five frozen marks).

    v5 uses an as-of join: latest annual report with pit <= session date;
    rows before a stock's first report stay unmarked (nothing known).
    """
    pos_marks = []
    for frame in (unlock_ranges, down_events, disclosure_ranges, c_de_events):
        cols = set(frame.columns)
        if 't0' in cols:
            marked = calendar.expand_ranges(frame)
        else:
            marked = frame.select('symbol', 'pos').unique(subset=['symbol', 'pos'])
        pos_marks.append(marked)
    s = s.with_columns(
        pl.lit(False).alias('v1'), pl.lit(False).alias('v2'),
        pl.lit(False).alias('v3'), pl.lit(False).alias('v4'))
    for flag_col, marked in zip(('v1', 'v2', 'v3', 'v4'), pos_marks):
        hits = (s.select('symbol', 'pos', flag_col)
                .join(marked.with_columns(pl.lit(True).alias('_hit')),
                      on=['symbol', 'pos'], how='inner')
                .unique(subset=['symbol', 'pos'])
                .select('symbol', 'pos', pl.col('_hit').alias(f'_{flag_col}')))
        s = (s.join(hits, on=['symbol', 'pos'], how='left')
             .with_columns(pl.col(f'_{flag_col}').fill_null(False)
                           .or_(pl.col(flag_col)).alias(flag_col))
             .drop(f'_{flag_col}'))
    co = (cohorts.select(pl.col('symbol'), pl.col('pit'), pl.col('marked'))
          .sort('symbol', 'pit'))
    s = (s.sort('symbol', 'date')
         .join_asof(co, left_on='date', right_on='pit', by='symbol',
                    strategy='backward')
         .with_columns(pl.col('marked').fill_null(False).alias('v5'))
         .drop('pit', 'marked')
         .sort('symbol', 'date'))
    return s


# --------------------------------------------------------------------------- #
# C03 / C05 / C06 / C07 evaluations
# --------------------------------------------------------------------------- #
def _q05(values: np.ndarray) -> float | None:
    v = np.asarray(values, dtype=np.float64)
    v = v[np.isfinite(v)]
    return float(np.percentile(v, 5)) if v.size else None


def evaluate_c03(matched_all: pl.DataFrame) -> dict:
    """C03 gates: (a) P5 gap, (b) blocked-exit rate ratio, (c) mean cap.

    Primary block proxy = exit-session (t+5) seal; the any-sellable-day
    variant is reported as ``block_ratio_window``.
    """
    out: dict = {}
    for window in ('dev', 'val'):
        part = matched_all.filter(pl.col('window') == window)
        stats: dict = {'n_matched': part.height}
        if part.height:
            q_marked = _q05(part['ret_event'].to_numpy())
            q_ctrl = _q05(part['ret_ctrl'].to_numpy())
            tail_gap = (q_ctrl - q_marked) if (q_marked is not None
                                               and q_ctrl is not None) else None
            mean_marked = float(part['ret_event'].mean())
            mean_ctrl = float(part['ret_ctrl'].mean())
            rate_m = float(part['block5_exit'].mean())
            rate_c = float(part['block5_exit_ctrl'].mean())
            rate_m_w = float(part['block5_window'].mean())
            rate_c_w = float(part['block5_window_ctrl'].mean())
            block_ratio = (rate_m / rate_c) if rate_c > 0 else None
            block_ratio_w = (rate_m_w / rate_c_w) if rate_c_w > 0 else None
            per_year = []
            for year in sorted(part['year'].unique().to_list()):
                y = part.filter(pl.col('year') == year)
                qm = _q05(y['ret_event'].to_numpy())
                qc = _q05(y['ret_ctrl'].to_numpy())
                per_year.append({'year': int(year), 'n': y.height,
                                 'metric': (qc - qm) if (qm is not None and qc is not None) else None})
            stats.update({
                'q05_marked': q_marked, 'q05_ctrl': q_ctrl, 'tail_gap': tail_gap,
                'mean_marked': mean_marked, 'mean_ctrl': mean_ctrl,
                'mean_loss': mean_marked - mean_ctrl,
                'block_rate_marked': rate_m, 'block_rate_ctrl': rate_c,
                'block_ratio': block_ratio,
                'block_rate_marked_window': rate_m_w,
                'block_rate_ctrl_window': rate_c_w,
                'block_ratio_window': block_ratio_w,
                'per_year': per_year,
                'years_gate': year_consistency(per_year, 'positive'),
            })
            stats['gate_tail'] = bool(tail_gap is not None and tail_gap >= C03_TAIL_MIN)
            stats['gate_block'] = bool(
                (block_ratio is not None and block_ratio >= C03_BLOCK_RATIO)
                or (block_ratio is None and rate_m > 0))  # controls never blocked
            stats['gate_mean_cap'] = bool(stats['mean_loss'] is not None
                                          and stats['mean_loss'] <= C03_MEAN_CAP)
            stats['pass'] = bool(stats['gate_tail'] and stats['gate_block']
                                 and stats['gate_mean_cap'])
        else:
            stats.update({'q05_marked': None, 'q05_ctrl': None, 'tail_gap': None,
                          'mean_loss': None, 'block_ratio': None, 'per_year': [],
                          'gate_tail': False, 'gate_block': False,
                          'gate_mean_cap': False, 'pass': False,
                          'years_gate': {'pass': False, 'n_years_covered': 0}})
        out[window] = stats
    return out


def c05_incidence(cohorts: pl.DataFrame, forecast_neg: pl.DataFrame,
                  forecast_start: date) -> dict:
    """C05 primary gate: 12-month first-loss/downgrade-forecast incidence.

    A cohort (symbol, fiscal year, pit) is judged only when its full window
    (pit, pit + 1 year] lies inside forecast coverage and the freeze line.
    Ratio = incidence(marked) / incidence(whole cohort) per fiscal year and
    pooled per window (dev/val assigned by pit).
    """
    by_symbol: dict[str, np.ndarray] = {}
    for rec in forecast_neg.group_by('symbol').agg(
            pl.col('ts_knowledge').sort()).iter_rows(named=True):
        ds = rec['ts_knowledge']
        by_symbol[rec['symbol']] = (np.array(ds, dtype='datetime64[D]')
                                    if ds else np.empty(0, dtype='datetime64[D]'))
    rows = []
    for rec in cohorts.iter_rows(named=True):
        pit = rec['pit']
        win_end = date(pit.year + 1, pit.month, pit.day)
        judged = (pit >= forecast_start) and (win_end <= FREEZE_END)
        hit = False
        if judged:
            ds = by_symbol.get(rec['symbol'])
            if ds is not None and ds.size:
                lo = np.searchsorted(ds, np.datetime64(pit), side='right')
                hi = np.searchsorted(ds, np.datetime64(win_end), side='right')
                hit = bool(hi > lo)
        rows.append({'symbol': rec['symbol'], 'fy': rec['fy'], 'pit': pit,
                     'marked': bool(rec['marked']), 'judged': judged,
                     'window': ('dev' if pit <= DEV_END else
                                'val' if pit >= VAL_RANGE[0] else None),
                     'hit': hit})
    detail = pl.DataFrame(rows, orient='row') if rows else pl.DataFrame()
    out: dict = {'cohorts_total': cohorts.height, 'windows': {}}
    for window in ('dev', 'val'):
        part = detail.filter((pl.col('window') == window) & pl.col('judged'))
        stats: dict = {}
        if part.height:
            marked = part.filter(pl.col('marked'))
            base = part
            n_m, h_m = marked.height, int(marked['hit'].sum())
            n_b, h_b = base.height, int(base['hit'].sum())
            inc_m = h_m / n_m if n_m else None
            inc_b = h_b / n_b if n_b else None
            ratio = (inc_m / inc_b) if (inc_m is not None and inc_b not in (None, 0.0)) else None
            per_year = []
            for fy in sorted(part['fy'].unique().to_list()):
                y = part.filter(pl.col('fy') == fy)
                ym = y.filter(pl.col('marked'))
                inc_y = (int(ym['hit'].sum()) / ym.height) if ym.height else None
                inc_by = int(y['hit'].sum()) / y.height
                ratio_y = (inc_y / inc_by) if (inc_y is not None and inc_by > 0) else None
                per_year.append({'year': int(fy), 'n_marked': ym.height,
                                 'n_cohort': y.height,
                                 'metric': ratio_y})
            stats.update({'n_marked': n_m, 'n_cohort': n_b,
                          'incidence_marked': inc_m, 'incidence_cohort': inc_b,
                          'ratio': ratio, 'per_year': per_year,
                          'years_gate': year_consistency(per_year, 'above',
                                                         C05_INCIDENCE_RATIO),
                          'gate_ratio': bool(ratio is not None
                                             and ratio >= C05_INCIDENCE_RATIO)})
        else:
            stats.update({'n_marked': 0, 'n_cohort': 0, 'ratio': None,
                          'gate_ratio': False, 'per_year': [],
                          'years_gate': {'pass': False, 'n_years_covered': 0}})
        out['windows'][window] = stats
    out['detail'] = detail
    return out


def evaluate_c06(s: pl.DataFrame) -> dict:
    """C06 chain combination on the equal-weight pool host (5-day labels).

    Host = every S row from C06_HOST_START with a complete fwd5 label (one
    random pool entry per row).  Veto = any of v1..v5.
    """
    host = (s.filter(pl.col('date') >= C06_HOST_START)
            .filter(pl.col('fwd5').is_not_null())
            .with_columns(
                pl.any_horizontal(['v1', 'v2', 'v3', 'v4', 'v5']).alias('veto'))
            .with_columns(pl.col('exit5_date').dt.year().alias('exit_year')))
    out: dict = {'host_rows': host.height}
    stamp = pl.when(pl.col('exit5_date') >= date(2023, 8, 28)).then(0.0005) \
        .otherwise(0.001)
    host = host.with_columns(
        ((pl.lit(20_000.0) * (1.0 + pl.col('fwd5')))
         - (pl.lit(5.0) + pl.lit(20_000.0) * (1.0 + pl.col('fwd5')) * stamp)
         ).alias('_exit_cash'))
    host = host.with_columns(
        (pl.col('_exit_cash') / pl.lit(20_005.0) - 1.0).alias('net5'))
    for window, (lo, hi) in (('dev', (C06_HOST_START, DEV_END)),
                             ('val', (VAL_RANGE[0], FREEZE_END))):
        part = host.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
        stats: dict = {'n_host': part.height}
        if part.height:
            vetoed = part.filter(pl.col('veto'))
            kept = part.filter(~pl.col('veto'))
            n_v = vetoed.height
            mean_host = float(part['fwd5'].mean())
            mean_vetoed = float(vetoed['fwd5'].mean()) if n_v else None
            mean_kept = float(kept['fwd5'].mean()) if kept.height else None
            q_host = _q05(part['fwd5'].to_numpy())
            q_kept = _q05(kept['fwd5'].to_numpy()) if kept.height else None
            tail_gain = None
            if q_host is not None and q_kept is not None and q_host != 0:
                tail_gain = (q_kept - q_host) / abs(q_host)
            cut = n_v / part.height
            per_year = []
            for year in sorted(part['date'].dt.year().unique().to_list()):
                y = part.filter(pl.col('date').dt.year() == year)
                yv = y.filter(pl.col('veto'))
                yk = y.filter(~pl.col('veto'))
                mh = float(y['fwd5'].mean())
                mv = float(yv['fwd5'].mean()) if yv.height else None
                qh = _q05(y['fwd5'].to_numpy())
                qk = _q05(yk['fwd5'].to_numpy()) if yk.height else None
                tg = ((qk - qh) / abs(qh)) if (qh is not None and qk is not None
                                               and qh != 0) else None
                per_year.append({'year': int(year), 'n_host': y.height,
                                 'n_vetoed': yv.height,
                                 'mean_loss': (mv - mh) if mv is not None else None,
                                 'tail_gain': tg})
            stats.update({
                'n_vetoed': n_v, 'cut_share': cut,
                'mean_host': mean_host, 'mean_vetoed': mean_vetoed,
                'mean_kept': mean_kept,
                'mean_loss': (mean_vetoed - mean_host) if mean_vetoed is not None else None,
                'q05_host': q_host, 'q05_kept': q_kept, 'tail_gain': tail_gain,
                'mean_host_net': float(part['net5'].mean()),
                'mean_kept_net': float(kept['net5'].mean()) if kept.height else None,
                'mean_vetoed_net': float(vetoed['net5'].mean()) if n_v else None,
                'veto_counts': {c: int(part[c].sum()) for c in
                                ('v1', 'v2', 'v3', 'v4', 'v5')},
                'per_year': per_year,
            })
            stats['gate_mean_loss'] = bool(stats['mean_loss'] is not None
                                           and stats['mean_loss'] <= C06_MEAN_LOSS_MAX)
            stats['gate_tail_gain'] = bool(tail_gain is not None
                                           and tail_gain >= C06_TAIL_GAIN)
            stats['gate_cut_share'] = bool(cut <= C06_CUT_MAX)
            stats['pass'] = bool(stats['gate_mean_loss'] and stats['gate_tail_gain']
                                 and stats['gate_cut_share'])
        else:
            stats.update({'gate_mean_loss': False, 'gate_tail_gain': False,
                          'gate_cut_share': False, 'pass': False})
        out[window] = stats
    return out


def evaluate_c07(unlock_events: pl.DataFrame, c_de_events: pl.DataFrame,
                 window_sessions: int = 10) -> dict:
    """Non-judging adjunct: unlock x company-DE sample overlap structure.

    A DE event overlaps an unlock when its signal session lies within
    +/- ``window_sessions`` sessions of the unlock float session.
    """
    de = c_de_events.select('symbol', 'pos').unique(subset=['symbol', 'pos'])
    pairs = unlock_events.join(de, on='symbol', how='inner')
    pairs = pairs.with_columns(
        (pl.col('pos_right') - pl.col('float_pos')).abs().alias('_gap'))
    near = pairs.filter(pl.col('_gap') <= window_sessions)
    return {
        'window_sessions': window_sessions,
        'n_unlock_events': unlock_events.height,
        'n_c_de_events': de.height,
        'n_unlock_with_nearby_de': near.select('event_id').unique().height,
        'share_unlock_with_nearby_de': (near.select('event_id').unique().height
                                        / unlock_events.height
                                        if unlock_events.height else None),
        'n_de_with_nearby_unlock': near.select('pos_right', 'symbol').unique().height,
        'share_de_with_nearby_unlock': (near.select('pos_right', 'symbol').unique().height
                                        / de.height if de.height else None),
    }


# --------------------------------------------------------------------------- #
# data identity validation (fail-closed)
# --------------------------------------------------------------------------- #
def _sha256(path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_sha_ledger(root) -> dict[str, str]:
    """data/_meta/sha256.tsv -> {relpath-under-data/raw: sha256}."""
    ledger: dict[str, str] = {}
    with open(root / 'data/_meta/sha256.tsv', encoding='utf-8') as fh:
        for line in fh:
            parts = line.rstrip('\n').split('\t')
            if len(parts) != 3:
                continue
            ledger[parts[0]] = parts[2]
    return ledger


def validate_identity(root, config: dict) -> dict:
    """Verify every authority-chain dataset against its manifest and the
    data/_meta sha256 ledger.  Raises on any mismatch (fail-closed)."""
    report: dict = {'checked_files': 0, 'batch_manifests': {}, 'notes': []}
    failures: list[str] = []
    ledger = load_sha_ledger(root)

    def expect_file(rel_under_raw: str, label: str) -> None:
        path = root / 'data/raw' / rel_under_raw
        expected = ledger.get(rel_under_raw)
        if expected is None:
            failures.append(f'{label}: {rel_under_raw} not in sha256 ledger')
            return
        if not path.is_file():
            failures.append(f'{label}: {rel_under_raw} missing on disk')
            return
        actual = _sha256(path)
        report['checked_files'] += 1
        if actual != expected:
            failures.append(f'{label}: {rel_under_raw} sha256 mismatch '
                            f'({actual[:12]}.. != {expected[:12]}..)')

    def expect_dir(dir_rel: str, label: str, *, manifest_too: bool = True) -> None:
        batch_dir = root / 'data/raw' / dir_rel
        files = sorted(p for p in batch_dir.glob('*')
                       if p.is_file() and p.name != 'manifest.json'
                       and not p.name.startswith('fetch'))
        if manifest_too:
            expect_file(f'{dir_rel}/manifest.json', f'{label}/manifest')
        for path in files:
            expect_file(f'{dir_rel}/{path.name}', label)

    # 1) processed daily dataset manifest (config pins its sha256)
    daily_cfg = next(d for d in config['authority_chain']['datasets']
                     if 'baostock-daily' in d['path'])
    manifest_path = root / 'data/processed/baostock-daily-20260917/manifest.json'
    actual = _sha256(manifest_path)
    if actual != daily_cfg['manifest_sha256']:
        failures.append(f'daily manifest sha mismatch: {actual[:12]}..')
    daily_manifest = json_load(manifest_path)
    for name, meta in daily_manifest['files'].items():
        n = pl.scan_parquet(root / 'data/processed/baostock-daily-20260917' / name) \
            .select(pl.len()).collect().item()
        if n != meta['rows']:
            failures.append(f'{name}: rows {n} != manifest {meta["rows"]}')
    report['daily_manifest'] = 'ok' if not failures else 'failed'

    # 2) event feature tables vs features manifest (incl. batch manifest shas)
    feat_manifest = json_load(root / EVENT_DIR / 'manifest.json')
    for family in ('share_float', 'disclosure_date', 'forecast'):
        meta = feat_manifest['families'][family]
        actual = _sha256(root / EVENT_DIR / meta['output_file'])
        if actual != meta['output_sha256']:
            failures.append(f'event table {family}: sha mismatch')
        rel = (meta['input_batch'].replace('\\', '/') + '/manifest.json')
        if rel.startswith('data/raw/'):
            rel = rel[len('data/raw/'):]
        expect_file(rel, f'features/{family}/batch_manifest')
        report['batch_manifests'][family] = meta['batch_manifest_sha256'][:12]

    # 3) full per-chunk verification of every consumed raw batch
    expect_dir('tushare/forecast/20260909-r1', 'forecast_raw')
    expect_dir('tushare/stk_holdertrade/20260909-r3', 'holdertrade_raw')
    expect_dir('tushare/share_float/20260909-r3', 'share_float_raw')
    expect_dir('tushare/disclosure_date/20260909-r1', 'disclosure_raw')
    expect_dir('tushare/daily_basic/20260909-r1', 'daily_basic_r1')
    expect_dir('tushare/daily_basic/20260913-r2', 'daily_basic_r2')
    expect_dir('tushare/cashflow/20260909-r3', 'cashflow_raw')
    expect_dir('tushare/balancesheet/20260909-r3', 'balancesheet_raw')
    expect_dir(ADJ_DIR.replace('data/raw/', ''), 'adj_factor')
    expect_dir(STK_LIMIT_DIR.replace('data/raw/', ''), 'stk_limit')
    expect_dir(STOCK_BASIC_DIR.replace('data/raw/', ''), 'stock_basic')
    expect_file(CALENDAR_CSV.replace('data/raw/', ''), 'calendar')

    # 4) income manifest only (listed by the config but not consumed; the
    # frozen accrual formula needs no income field - disclosed deviation)
    expect_file('tushare/income/20260909-r3/manifest.json', 'income_manifest')
    report['notes'].append('income batch verified at manifest level only '
                           '(not consumed by the frozen accrual formula)')

    if failures:
        raise ValueError('data identity validation failed:\n' + '\n'.join(failures))
    return report


def json_load(path) -> dict:
    import json
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)
