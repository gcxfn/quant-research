"""P2-R11 half-day candidate combination (exp-20260918-p2r11-halfday-combo).

Implements the frozen protocol in
``docs/research/exp-20260918-p2r11-halfday-combo-prereg.md`` and the frozen
config ``configs/experiments/p2r11-halfday-combo.json``:

- pool: R10 sample machinery REUSED by import, with the single frozen
  universe change of excluding ChiNext (sz.30*) plus the two frozen
  liquidity gates (past-20-traded-session median daily amount >= 30M CNY;
  same-day morning amount >= 3M CNY),
- factors F03/F06/F09/F11 come from R10's ``compute_factors`` (imported,
  never reimplemented); daily_vol20 uses the M-1-fixed R10 loader,
- composite: per-day 1%/99% winsorize + z-standardize, direction-flipped
  with the R10-frozen directions (fail-closed asserted at run time),
- portfolio engine: 11:30 signal -> 13:01 buy (open_1300) -> frozen sell
  schedules (next 09:25 daily open / next 11:30 close_1130 / next official
  close / T+2 13:01), limit-up buy block with <=2 replacements per slot,
  limit-down / suspension sell postponement counted as execution failure,
  K-slot concurrency, lot rounding, 200k capital, min(equity/K, 50k)
  sizing, wan-1 commission (5-yuan minimum) + historical segmented stamp,
- corporate-action bridge: preclose bridge across days, raw same-day
  division within a day; held share counts adjust at the day boundary by
  close(prev traded day)/preclose(today) so raw-price marking stays
  consistent (reinvested-dividend approximation, disclosed),
- benchmarks B1 (same-pool equal-weight whole pool, same timing/fees) and
  B3' (same engine, random priorities, seeds 17-36),
- frozen dev/validation/test gates evaluated procedurally (one-way).

Known-pattern discipline: every rolling/shift on a per-symbol column uses
``expr.shift(1).over('symbol')`` (shift INSIDE over) - the M-1 bug pattern
``.over('symbol').shift(1)`` is forbidden here and covered by unit tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final

import numpy as np
import polars as pl

from quant.research.p2r10_halfday import (  # reused R10 machinery
    EXCLUDED_INDEX_SYMBOLS,
    NEW_LISTING_SESSIONS,
    SESSIONS_PER_YEAR,
    compute_factors,
    load_daily_vol20,
    load_listing_index,
    stamp_for,
)

# --------------------------------------------------------------------------- #
# frozen constants (configs/experiments/p2r11-halfday-combo.json)
# --------------------------------------------------------------------------- #
FACTORS: Final[tuple[str, ...]] = ('F03', 'F06', 'F09', 'F11')
# R10 dev-IC directions for the four registered candidates (all negative:
# high raw factor = weak afternoon).  Fail-closed asserted against the R10
# run metrics at CLI start; high composite score = buy side after flip.
FROZEN_DIRECTIONS: Final[dict[str, int]] = {
    'F03': -1, 'F06': -1, 'F09': -1, 'F11': -1}
R10_RUN_METRICS: Final[str] = ('artifacts/runs/20260918T051252-'
                               'p2r10-halfday-survey-54a3d885/metrics.json')

COMMISSION_PCT: Final[float] = 0.0001
COMMISSION_MIN: Final[float] = 5.0
CAPITAL: Final[float] = 200_000.0
PER_STOCK_CAP: Final[float] = 50_000.0
LOT: Final[int] = 100
REPLACEMENT_BUDGET: Final[int] = 2          # per slot: initial + 2 backups
WINSOR_Q: Final[float] = 0.01
DEV_WINDOW: Final[tuple[date, date]] = (date(2015, 1, 5), date(2020, 12, 31))
VAL_WINDOW: Final[tuple[date, date]] = (date(2021, 1, 1), date(2022, 12, 31))
TEST_WINDOW: Final[tuple[date, date]] = (date(2023, 1, 1), date(2024, 12, 31))
MEDIAN_AMOUNT_20D_MIN: Final[float] = 30_000_000.0
AMOUNT_AM_MIN: Final[float] = 3_000_000.0
LIMIT_EPS: Final[float] = 0.001
MAX_WEIGHT: Final[float] = 0.40
MAX_TURNOVER: Final[float] = 300.0
MIN_FILL_RATE: Final[float] = 0.95
DEV_EXCESS_MIN: Final[float] = 0.02
DEV_B3_MARGIN: Final[float] = 0.01
DEV_MAX_DD: Final[float] = 0.20
DEV_ADV_YEARS_MIN: Final[int] = 5
WINDOW_EXCESS_MIN: Final[float] = 0.01
WINDOW_ADV_YEARS_MIN: Final[int] = 2

CONFIGS: Final[dict[str, dict]] = {
    'C01': {'composite': 'equal_z', 'K': 3, 'sell': 'S_1130'},
    'C02': {'composite': 'equal_z', 'K': 3, 'sell': 'S_close'},
    'C03': {'composite': 'equal_z', 'K': 3, 'sell': 'S_T2_1301'},
    'C04': {'composite': 'equal_z', 'K': 5, 'sell': 'S_1130'},
    'C05': {'composite': 'single_F03', 'K': 3, 'sell': 'S_1130'},
    'C06': {'composite': 'single_F06', 'K': 3, 'sell': 'S_1130'},
    'C07': {'composite': 'single_F09', 'K': 3, 'sell': 'S_1130'},
    'C08': {'composite': 'single_F11', 'K': 3, 'sell': 'S_1130'},
    'C09': {'composite': 'equal_z', 'K': 3, 'sell': 'S_0925'},
    'C10': {'composite': 'drop_f06', 'K': 3, 'sell': 'S_1130'},
    'C11': {'composite': 'rank_avg', 'K': 3, 'sell': 'S_1130'},
    'C12': {'composite': 'equal_z', 'K': 10, 'sell': 'S_1130'},
}
PRIORITY: Final[tuple[str, ...]] = ('C01', 'C11', 'C10', 'C04', 'C12',
                                    'C02', 'C03', 'C09', 'C05', 'C06',
                                    'C07', 'C08')
SELL_OFFSETS: Final[dict[str, int]] = {   # trading-day offset of first sell
    'S_0925': 1, 'S_1130': 1, 'S_close': 1, 'S_T2_1301': 2,
}
SELL_POINTS: Final[dict[str, str]] = {
    'S_0925': 'open0925', 'S_1130': 'close1130',
    'S_close': 'close_day', 'S_T2_1301': 'open1300',
}
B3_SEEDS: Final[tuple[int, ...]] = tuple(range(17, 37))

P2R10_MODULE_SHA256_AFTER_M1_FIX: Final[str] = (
    '25eb29ada94e336eeddb2d81e718f0983dfde7434ff87db6a4729b29f5009188')


# --------------------------------------------------------------------------- #
# pool construction (R10 machinery reused; ChiNext exclusion is the single
# frozen universe change, plus the two frozen liquidity gates)
# --------------------------------------------------------------------------- #
def board_ok_r11(symbol: pl.Expr) -> pl.Expr:
    """SH/SZ mainboard only: ChiNext sz.30* excluded (the single frozen
    R11 universe change), STAR 68*, Beijing .BJ and the two CSI
    cross-listed indexes excluded (reused R10 exclusion set)."""
    return (
        (symbol.str.starts_with('sh.60'))
        | (symbol.str.starts_with('sz.00'))
    ) & ~symbol.is_in(EXCLUDED_INDEX_SYMBOLS)


def amount_median_20d(daily_path) -> pl.DataFrame:
    """Past-20-traded-session median daily amount per (symbol, date).

    M-1-safe pattern: rolling_median(...).shift(1).over('symbol') - the
    shift is INSIDE the window so each symbol's first 20 rows stay null
    (insufficient-history rule: <20 rows -> excluded from the pool).
    Suspended rows are filtered first (they do not advance history).
    """
    return (
        _freeze(pl.scan_parquet(daily_path))
        .filter(pl.col('tradestatus') == 1.0)
        .sort('symbol', 'date')
        .select('symbol', 'date',
                pl.col('amount').rolling_median(20, min_samples=20)
                .shift(1).over('symbol').alias('amount_med20'))
        .collect()
    )


def seasoned_listing_gate(daily_path) -> pl.DataFrame:
    """120-traded-session listing gate on the 2015-2024 daily file.

    Frozen rule: pre-2015 listings are exempt.  Operationalisation on this
    file (disclosed): a symbol whose first in-file traded date equals the
    file's first traded date is treated as seasoned (exempt); every other
    symbol needs listing_index > 120 in-file traded sessions (R10's
    load_listing_index; suspensions do not advance the index).
    """
    listing = load_listing_index(daily_path)
    file_first = listing['date'].min()
    firsts = listing.group_by('symbol').agg(
        pl.col('date').min().alias('_first_date'))
    return (listing
            .join(firsts, on='symbol')
            .with_columns(
                ((pl.col('_first_date') == pl.lit(file_first))
                 | (pl.col('listing_index') > NEW_LISTING_SESSIONS)
                 ).alias('listing_ok'))
            .select('symbol', 'date', 'listing_index', 'listing_ok'))


POOL_COLS: Final[list[str]] = ['symbol', 'date', 'F03', 'F06', 'F09', 'F11']


def _freeze(lf: pl.LazyFrame) -> pl.LazyFrame:
    """Read-layer freeze: no row on/after 2025-01-01 may enter any path."""
    return lf.filter(pl.col('date') < date(2025, 1, 1))


def build_pool(halfday_path, daily_2015_path, daily_1999_path,
               smoke: bool = False) -> tuple[pl.DataFrame, dict]:
    """Filtered factor panel (pool rows only) + waterfall counts.

    Filter order: suspended/ST -> boards (no ChiNext) -> listing 120d ->
    20d median amount -> morning amount (FINAL pool) -> factors.  All
    cross-sectional statistics inside compute_factors therefore see only
    the final pool.
    """
    counts: dict[str, object] = {}
    halfday = _freeze(pl.scan_parquet(halfday_path)).select(
        'symbol', 'date', 'preclose_official', 'open_930', 'close_1100',
        'close_1130', 'open_1300', 'close_day_official', 'high_am',
        'low_am', 'vol_am', 'amount_am', 'am_limit_up_touch_minutes',
        'tradestatus', 'isST', 'suspended_flag').collect()
    counts['halfday_rows_total'] = halfday.height
    df = (halfday
          .filter(pl.col('tradestatus') == 1)
          .filter(~pl.col('suspended_flag'))
          .filter(pl.col('isST') == 0))
    counts['after_suspended_st'] = df.height
    df = df.filter(board_ok_r11(pl.col('symbol')))
    counts['after_boards_no_chinext'] = df.height

    listing = seasoned_listing_gate(daily_2015_path)
    med20 = amount_median_20d(daily_2015_path)
    df = (df.join(listing, on=['symbol', 'date'], how='left')
            .join(med20, on=['symbol', 'date'], how='left')
            .filter(pl.col('listing_ok'))          # null-safe: null -> drop
            )
    counts['after_listing_120d'] = df.height
    df = df.filter(pl.col('amount_med20') >= MEDIAN_AMOUNT_20D_MIN)
    counts['after_median_amount_20d_30m'] = df.height
    df = df.filter(pl.col('amount_am') >= AMOUNT_AM_MIN)
    counts['after_amount_am_3m'] = df.height

    vol20 = load_daily_vol20(daily_1999_path)
    df = df.join(vol20, on=['symbol', 'date'], how='left')
    df = compute_factors(df)
    if smoke:
        df = df.filter((pl.col('date') >= DEV_WINDOW[0])
                       & (pl.col('date') <= date(2015, 3, 31)))
        counts['after_smoke_window'] = df.height
    counts['pool_rows'] = df.height
    counts['pool_symbols'] = df['symbol'].n_unique()
    counts['pool_days'] = df['date'].n_unique()
    return df.select(POOL_COLS), counts


def build_execution_table(halfday_path, daily_2015_path) -> pl.DataFrame:
    """Market table over ALL active halfday rows (superset of the pool so a
    held position can always be marked/sold even after leaving the pool):
    execution prices, limits, 09:25 daily open, and the preclose boundary
    adjustment factor close(prev traded day)/preclose(today) - the M-1-safe
    shift-inside-over pattern."""
    active = _freeze(
        pl.scan_parquet(halfday_path)
        .select('symbol', 'date', 'close_1130', 'open_1300',
                'close_day_official', 'limit_up', 'limit_down',
                'tradestatus', 'suspended_flag')
        .filter(pl.col('tradestatus') == 1)
        .filter(~pl.col('suspended_flag'))
        .drop('tradestatus', 'suspended_flag'))
    daily = _freeze(
        pl.scan_parquet(daily_2015_path)
        .select('symbol', 'date', 'open', 'close', 'preclose',
                'tradestatus')
        .filter(pl.col('tradestatus') == 1.0)
        .sort('symbol', 'date')
        .with_columns(
            pl.col('close').shift(1).over('symbol').alias('_prev_close'))
        .select('symbol', 'date',
                pl.col('open').alias('open0925'),
                pl.col('preclose').alias('preclose_ref'),
                (pl.col('_prev_close') / pl.col('preclose')
                 ).alias('boundary_adj')))
    return active.join(daily, on=['symbol', 'date'], how='left').collect()


def mark_breaker_days(halfday_path) -> list[date]:
    """Market-wide halt days: EVERY active stock flat across
    close_1100 -> close_1130 -> open_1300 (vendor forward-filled
    placeholders, no afternoon trade).  On 2015-2024 data this isolates
    2016-01-07 (next-highest share 0.83).  The CLI fail-closed asserts the
    flagged set equals {2016-01-07}."""
    flat = (
        _freeze(pl.scan_parquet(halfday_path))
        .select('date', 'close_1100', 'close_1130', 'open_1300',
                'tradestatus', 'suspended_flag')
        .filter(pl.col('tradestatus') == 1)
        .filter(~pl.col('suspended_flag'))
        .with_columns(
            ((pl.col('open_1300') == pl.col('close_1130'))
             & (pl.col('close_1130') == pl.col('close_1100'))
             & pl.col('open_1300').is_not_null()).alias('_flat'))
        .group_by('date')
        .agg(pl.col('_flat').mean().alias('share'))
        .filter(pl.col('share') == 1.0)
        .sort('date')
        .collect())
    return flat['date'].to_list()


# --------------------------------------------------------------------------- #
# composite scores
# --------------------------------------------------------------------------- #
def _z_expr(factor: str) -> pl.Expr:
    """1%/99% winsorize (linear interpolation) then z-standardize, within
    day; constant cross-sections (std null/0) map to z=0 (neutral); null
    factor stays null."""
    w = pl.col(factor).clip(
        pl.col(factor).quantile(WINSOR_Q, interpolation='linear').over('date'),
        pl.col(factor).quantile(1 - WINSOR_Q, interpolation='linear')
        .over('date'))
    sd = pl.col(factor).std().over('date')
    mean = pl.col(factor).mean().over('date')
    z = pl.when(sd.is_null() | (sd == 0)).then(0.0).otherwise((w - mean) / sd)
    return pl.when(pl.col(factor).is_not_null()).then(z).otherwise(None)


def _rank_expr(factor: str) -> pl.Expr:
    return (pl.when(pl.col(factor).is_not_null())
            .then(pl.col(factor).rank(method='average').over('date'))
            .otherwise(None))


def add_composite(panel: pl.DataFrame, kind: str) -> pl.DataFrame:
    """Add the frozen composite `score` column for one config kind."""
    members = {
        'equal_z': FACTORS,
        'drop_f06': ('F03', 'F09', 'F11'),
    }.get(kind)
    if members is not None:
        expr = pl.sum_horizontal(
            [pl.lit(float(FROZEN_DIRECTIONS[f])) * _z_expr(f)
             for f in members]) / len(members)
    elif kind.startswith('single_'):
        f = kind.split('_', 1)[1]
        expr = pl.lit(float(FROZEN_DIRECTIONS[f])) * _z_expr(f)
    elif kind == 'rank_avg':
        expr = pl.sum_horizontal(
            [pl.lit(float(FROZEN_DIRECTIONS[f])) * _rank_expr(f)
             for f in FACTORS]) / len(FACTORS)
    elif kind == 'random':
        raise ValueError('random scores are generated by the CLI per seed')
    else:
        raise ValueError(f'unknown composite kind {kind}')
    return panel.with_columns(expr.alias('score'))


# --------------------------------------------------------------------------- #
# market arrays for the engine
# --------------------------------------------------------------------------- #
@dataclass
class MarketArrays:
    """Columnar market data sorted by (date_idx, sym_idx)."""
    dates: list[date]
    sym_names: list[str]
    date_idx: np.ndarray
    sym_idx: np.ndarray
    score: np.ndarray                 # NaN where not a candidate
    open_1300: np.ndarray
    close_1130: np.ndarray
    close_day: np.ndarray
    limit_up: np.ndarray
    limit_down: np.ndarray
    open_0925: np.ndarray
    preclose_ref: np.ndarray
    boundary_adj: np.ndarray
    breaker: np.ndarray               # per date_idx bool

    def day_slice(self, d: int) -> tuple[int, int]:
        lo = int(np.searchsorted(self.date_idx, d, side='left'))
        hi = int(np.searchsorted(self.date_idx, d, side='right'))
        return lo, hi


def prepare_market(exec_tab: pl.DataFrame, breaker: list[date]) -> dict:
    """Sort the execution table once, factorize dates/symbols once, and
    keep static arrays; per-config runs then only swap the score array."""
    tab = exec_tab.sort('date', 'symbol').with_row_index('_r')
    dates = tab['date'].unique().sort().to_list()
    sym_names = tab['symbol'].unique().sort().to_list()
    d_pos = {d: i for i, d in enumerate(dates)}
    s_pos = {s: i for i, s in enumerate(sym_names)}
    bset = set(breaker)
    return {
        'frame': tab,
        'dates': dates,
        'sym_names': sym_names,
        'date_idx': np.array([d_pos[d] for d in tab['date']],
                             dtype=np.int64),
        'sym_idx': np.array([s_pos[s] for s in tab['symbol']],
                            dtype=np.int64),
        'open_1300': tab['open_1300'].to_numpy().astype(np.float64),
        'close_1130': tab['close_1130'].to_numpy().astype(np.float64),
        'close_day': tab['close_day_official'].to_numpy().astype(np.float64),
        'limit_up': tab['limit_up'].to_numpy().astype(np.float64),
        'limit_down': tab['limit_down'].to_numpy().astype(np.float64),
        'open_0925': tab['open0925'].to_numpy().astype(np.float64),
        'preclose_ref': tab['preclose_ref'].to_numpy().astype(np.float64),
        'boundary_adj': tab['boundary_adj'].to_numpy().astype(np.float64),
        'breaker': np.array([d in bset for d in dates], dtype=bool),
    }


def market_arrays_with_score(static: dict, score: np.ndarray) -> MarketArrays:
    return MarketArrays(
        dates=static['dates'], sym_names=static['sym_names'],
        date_idx=static['date_idx'], sym_idx=static['sym_idx'],
        score=score,
        open_1300=static['open_1300'], close_1130=static['close_1130'],
        close_day=static['close_day'], limit_up=static['limit_up'],
        limit_down=static['limit_down'], open_0925=static['open_0925'],
        preclose_ref=static['preclose_ref'],
        boundary_adj=static['boundary_adj'], breaker=static['breaker'])


def score_array(static: dict, pool: pl.DataFrame, kind: str) -> np.ndarray:
    """Composite score aligned to the sorted execution-table rows; NaN
    outside the pool.  The row index keeps the join order-stable."""
    scored = add_composite(pool, kind).select('symbol', 'date', 'score')
    joined = (static['frame']
              .join(scored, on=['symbol', 'date'], how='left')
              .sort('_r'))
    return joined['score'].to_numpy().astype(np.float64)


def random_score_array(static: dict, is_pool: np.ndarray,
                       seed: int) -> np.ndarray:
    """Uniform random priorities for B3', restricted to pool rows
    (NaN elsewhere); deterministic per seed."""
    rng = np.random.default_rng(seed)
    r = rng.random(is_pool.size)
    return np.where(is_pool, r, np.nan)


def pool_mask(static: dict, pool: pl.DataFrame) -> np.ndarray:
    keys = pool.select(pl.col('symbol'), pl.col('date'),
                       pl.lit(True).alias('_in_pool'))
    joined = (static['frame']
              .join(keys, on=['symbol', 'date'], how='left')
              .sort('_r'))
    return joined['_in_pool'].fill_null(False).to_numpy()


# --------------------------------------------------------------------------- #
# portfolio engine
# --------------------------------------------------------------------------- #
@dataclass
class Position:
    sym: int
    shares: float
    last_price: float
    buy_day: int
    due_day: int
    schedule: str


@dataclass
class RunResult:
    equity: np.ndarray                # post-close mark, one entry per day
    max_weight: np.ndarray            # per-day max single-position weight
    buy_notional: np.ndarray          # per-day bought notional (fees excl)
    trades: list[dict] = field(default_factory=list)
    attempts: list[dict] = field(default_factory=list)
    cash_final: float = 0.0
    open_positions: int = 0
    open_value: float = 0.0           # mark value of still-open positions


def _commission(notional: float) -> float:
    return max(notional * COMMISSION_PCT, COMMISSION_MIN)


def run_portfolio(mkt: MarketArrays, K: int, schedule: str) -> RunResult:
    """Event loop.  Intraday order: boundary CA adjustment -> 09:25 sells
    -> 11:30 sells -> 13:01 sells (S_T2_1301) -> 13:01 buys -> official-
    close sells -> marks.  Cash freed at/before 13:01 funds same-point
    buys; close-sale cash is only usable the next day."""
    n_days = len(mkt.dates)
    equity = np.zeros(n_days)
    max_weight = np.zeros(n_days)
    buy_notional = np.zeros(n_days)
    cash = CAPITAL
    positions: dict[int, Position] = {}
    trades: list[dict] = []
    attempts: list[dict] = []
    open_trade: dict[int, int] = {}

    def row_of(sym: int, d: int) -> int | None:
        lo, hi = mkt.day_slice(d)
        if hi == lo:
            return None
        s = lo + int(np.searchsorted(mkt.sym_idx[lo:hi], sym))
        if s >= hi or mkt.sym_idx[s] != sym:
            return None
        return s

    def try_sell(pos: Position, d: int) -> None:
        nonlocal cash
        point = SELL_POINTS[pos.schedule]
        s = row_of(pos.sym, d)
        px = np.nan
        if s is not None:
            if point == 'open0925':
                px = mkt.open_0925[s]     # 09:25 auction traded even on
            else:                         # breaker days (morning open)
                if not mkt.breaker[d]:    # later points invalid on halts
                    col = {'close1130': mkt.close_1130,
                           'close_day': mkt.close_day,
                           'open1300': mkt.open_1300}[point]
                    px = col[s]
        blocked = not np.isfinite(px)
        if not blocked:
            ld = mkt.limit_down[s]
            if np.isfinite(ld) and px <= ld + LIMIT_EPS:
                blocked = True            # sell point at limit-down
        if blocked:
            attempts.append({'day': d, 'kind': 'sell', 'sym': pos.sym,
                             'success': False, 'reason': 'blocked'})
            pos.due_day = d + 1
            return
        proceeds = pos.shares * px
        stamp = proceeds * stamp_for(mkt.dates[d])
        fee = _commission(proceeds)
        cash += proceeds - stamp - fee
        ti = open_trade.pop(pos.sym)
        trades[ti].update(sell_day=d, sell_price=px, sell_fee=fee + stamp,
                          shares=pos.shares)   # post-CA sold count
        del positions[pos.sym]
        attempts.append({'day': d, 'kind': 'sell', 'sym': pos.sym,
                         'success': True, 'reason': ''})

    def fill_slots(d: int, empty: int, taken: set[int]) -> None:
        nonlocal cash
        lo, hi = mkt.day_slice(d)
        seg_sym = mkt.sym_idx[lo:hi]
        sc = mkt.score[lo:hi]
        idx = np.flatnonzero(np.isfinite(sc))
        if idx.size == 0:
            return
        order = idx[np.lexsort((seg_sym[idx], -sc[idx]))]
        eq0 = cash + sum(p.shares * p.last_price
                         for p in positions.values())
        target = min(eq0 / K, PER_STOCK_CAP)
        cursor = 0
        for _slot in range(empty):
            skips = 0
            while cursor < len(order) and skips <= REPLACEMENT_BUDGET:
                j = int(order[cursor])
                cursor += 1
                sym = int(seg_sym[j])
                if sym in taken:
                    continue              # not a candidate: held already
                px = mkt.open_1300[lo + j]
                lu = mkt.limit_up[lo + j]
                ok = np.isfinite(px)
                if ok and (not np.isfinite(lu) or px >= lu - LIMIT_EPS):
                    ok = False            # limit-up at 13:01 (or unknown:
                                          # conservative block, disclosed)
                if ok:
                    budget = min(target, cash)
                    shares = float(int(budget / px / LOT) * LOT)
                    while shares >= LOT and shares * px + \
                            _commission(shares * px) > cash:
                        shares -= LOT     # keep cash non-negative
                    if shares < LOT:
                        ok = False        # not one lot within target
                if not ok:
                    attempts.append({'day': d, 'kind': 'buy', 'sym': sym,
                                     'success': False,
                                     'reason': 'unbuyable'})
                    skips += 1
                    continue
                cost = shares * px
                fee = _commission(cost)
                cash -= cost + fee
                buy_notional[d] += cost
                positions[sym] = Position(sym=sym, shares=shares,
                                          last_price=px, buy_day=d,
                                          due_day=d + SELL_OFFSETS[schedule],
                                          schedule=schedule)
                taken.add(sym)
                open_trade[sym] = len(trades)
                trades.append({'buy_day': d, 'sell_day': None, 'sym': sym,
                               'shares': shares, 'buy_shares': shares,
                               'buy_price': px, 'buy_fee': fee,
                               'sell_price': None, 'sell_fee': None})
                attempts.append({'day': d, 'kind': 'buy', 'sym': sym,
                                 'success': True, 'reason': ''})
                break

    for d in range(n_days):
        # morning boundary: CA adjustment for positions held overnight
        for pos in positions.values():
            if pos.buy_day >= d:
                continue
            s = row_of(pos.sym, d)
            adj = mkt.boundary_adj[s] if s is not None else np.nan
            if np.isfinite(adj) and adj > 0:
                pos.shares *= adj
                pos.last_price = mkt.preclose_ref[s]
        # sells due today at their schedule point (chronological)
        for point in ('open0925', 'close1130', 'open1300'):
            for pos in [p for p in list(positions.values())
                        if p.due_day == d
                        and SELL_POINTS[p.schedule] == point]:
                try_sell(pos, d)
        # 13:01 buys (no valid 13:01 point on a market breaker day)
        if not mkt.breaker[d]:
            empty = K - len(positions)
            if empty > 0:
                fill_slots(d, empty, set(positions.keys()))
        # official-close sells (after buys: cash usable next day only)
        for pos in [p for p in list(positions.values())
                    if p.due_day == d
                    and SELL_POINTS[p.schedule] == 'close_day']:
            if pos.sym in positions:
                try_sell(pos, d)
        # marks
        vals = [p.shares * p.last_price for p in positions.values()]
        total = cash + sum(vals)
        equity[d] = total
        max_weight[d] = (max(vals) / total) if vals and total > 0 else 0.0
    open_value = sum(p.shares * p.last_price for p in positions.values())
    return RunResult(equity=equity, max_weight=max_weight,
                     buy_notional=buy_notional, trades=trades,
                     attempts=attempts, cash_final=cash,
                     open_positions=len(positions), open_value=open_value)


# --------------------------------------------------------------------------- #
# metrics and gates
# --------------------------------------------------------------------------- #
def window_metrics(dates: list[date], eq: np.ndarray, max_w: np.ndarray,
                   buy_notional: np.ndarray, trades: list[dict],
                   attempts: list[dict], lo: date, hi: date) -> dict:
    idx = [i for i, dd in enumerate(dates) if lo <= dd <= hi]
    if not idx:
        return {}
    e = eq[idx]
    n = len(idx)
    years = n / SESSIONS_PER_YEAR
    base = e[0]
    cagr = float((e[-1] / base) ** (1.0 / years) - 1.0) if base > 0 \
        else float('nan')
    peak = np.maximum.accumulate(e)
    max_dd = float(np.max(1.0 - e / peak))
    turn = float(buy_notional[idx].sum() / e.mean() / years)
    w = float(np.max(max_w[idx]))
    win_attempts = [a for a in attempts if lo <= dates[a['day']] <= hi]
    n_att = len(win_attempts)
    n_ok = sum(1 for a in win_attempts if a['success'])
    fill = float(n_ok / n_att) if n_att else float('nan')
    yearly = {}
    for yy in sorted({dates[i].year for i in idx}):
        yi = [i for i in idx if dates[i].year == yy]
        prev = [i for i in idx if dates[i].year == yy - 1]
        start = eq[prev[-1]] if prev else eq[idx[0]]
        yearly[yy] = float(eq[yi[-1]] / start - 1.0)
    return {'n_days': n, 'net_cagr': cagr, 'max_dd': max_dd,
            'turnover_annual': turn, 'max_weight': w,
            'fill_rate': fill, 'n_attempts': n_att,
            'yearly_net': yearly, 'equity_end': float(e[-1]),
            'equity_start': float(base)}


def evaluate_dev_gates(m: dict, b1: dict, b3_mean_cagr: float) -> dict:
    excess = m['net_cagr'] - b1['net_cagr']
    adv = sum(1 for yy, r in m['yearly_net'].items()
              if yy in b1['yearly_net'] and r > b1['yearly_net'][yy])
    cells = {
        1: {'value': m['net_cagr'], 'rule': 'net_cagr > 0',
            'pass': bool(m['net_cagr'] > 0)},
        2: {'value': excess, 'rule': '>= +0.02 vs B1',
            'pass': bool(excess >= DEV_EXCESS_MIN)},
        3: {'value': adv, 'rule': '>= 5/6 years beat B1',
            'pass': bool(adv >= DEV_ADV_YEARS_MIN)},
        4: {'value': m['max_dd'], 'vs_b1': b1['max_dd'],
            'rule': '<= 0.20 and <= B1.max_dd',
            'pass': bool(m['max_dd'] <= DEV_MAX_DD
                         and m['max_dd'] <= b1['max_dd'])},
        5: {'value': m['turnover_annual'], 'rule': '<= 300x annual one-side',
            'pass': bool(m['turnover_annual'] <= MAX_TURNOVER)},
        6: {'value': m['max_weight'], 'rule': '<= 0.40 any day',
            'pass': bool(m['max_weight'] <= MAX_WEIGHT)},
        7: {'value': m['net_cagr'] - b3_mean_cagr,
            'rule': '>= B3prime_mean_cagr + 0.01',
            'pass': bool(m['net_cagr'] >= b3_mean_cagr + DEV_B3_MARGIN)},
        8: {'value': m['fill_rate'], 'rule': '>= 0.95 plan fill rate',
            'pass': bool(m['fill_rate'] >= MIN_FILL_RATE)},
    }
    return {'cells': cells,
            'all_pass': all(c['pass'] for c in cells.values())}


def evaluate_window_gates(m: dict, b1: dict) -> dict:
    excess = m['net_cagr'] - b1['net_cagr']
    adv = sum(1 for yy, r in m['yearly_net'].items()
              if yy in b1['yearly_net'] and r > b1['yearly_net'][yy])
    cells = {
        1: {'value': excess, 'rule': '>= +0.01 vs B1',
            'pass': bool(excess >= WINDOW_EXCESS_MIN)},
        2: {'value': adv, 'rule': '2/2 years beat B1',
            'pass': bool(adv >= WINDOW_ADV_YEARS_MIN)},
        3: {'value': m['max_dd'], 'vs_b1': b1['max_dd'],
            'rule': '<= 0.20 and <= B1.max_dd',
            'pass': bool(m['max_dd'] <= DEV_MAX_DD
                         and m['max_dd'] <= b1['max_dd'])},
    }
    return {'cells': cells,
            'all_pass': all(c['pass'] for c in cells.values())}


# --------------------------------------------------------------------------- #
# B1 benchmark (same pool, equal-weight whole pool, same timing/fees)
# --------------------------------------------------------------------------- #
def b1_daily_marks(pool: pl.DataFrame, exec_tab: pl.DataFrame,
                   breaker: list[date]) -> pl.DataFrame:
    """Per-cycle net return of the equal-weight whole-pool benchmark.

    Cycle d -> next market day: buy whole pool at 13:01 (open_1300), sell
    next 11:30 (close_1130).  Per-name leg = (close_day/open_1300) x
    (close_1130(T+1)/preclose(T+1)) - 1 (preclose bridge, same-day raw
    division).  Fees proportional: wan-1 both sides + segmented stamp on
    the sell date; the 5-yuan minimum is meaningless at pool scale
    (disclosed).  Cycles touching a breaker day 11:30/13:01 point are
    excluded (placeholder prices).
    """
    dates = exec_tab['date'].unique().sort().to_list()
    bset = pl.Series('b', breaker, dtype=pl.Date)
    cal_next = pl.DataFrame({'date': dates[:-1], 'sell_date': dates[1:]})
    cal_prev = pl.DataFrame({'date': dates[1:], 'buy_date': dates[:-1]})
    t = (exec_tab.select('symbol', 'date', 'open_1300',
                         'close_day_official')
         .join(pool.select('symbol', 'date'), on=['symbol', 'date'],
               how='inner')
         .join(cal_next, on='date', how='inner')
         .rename({'date': 'buy_date'}))
    nxt = (exec_tab.select('symbol', 'date', 'close_1130', 'preclose_ref')
           .join(cal_prev, on='date', how='inner')
           .rename({'date': 'sell_date'}))
    legs = (t.join(nxt, on=['symbol', 'buy_date', 'sell_date'],
                   how='inner')
            .filter(pl.col('close_1130').is_not_null()
                    & pl.col('open_1300').is_not_null()
                    & pl.col('close_day_official').is_not_null()
                    & pl.col('preclose_ref').is_not_null()
                    & ~pl.col('sell_date').is_in(bset)
                    & ~pl.col('buy_date').is_in(bset)))
    legs = legs.with_columns(
        (((pl.col('close_day_official') / pl.col('open_1300'))
          * (pl.col('close_1130') / pl.col('preclose_ref')) - 1.0)
         ).alias('gross'))
    legs = legs.with_columns(
        pl.when(pl.col('sell_date') >= date(2023, 8, 28)).then(0.0005)
        .otherwise(0.001).alias('stamp'))
    legs = legs.with_columns(
        ((1.0 + pl.col('gross')) * (1.0 - COMMISSION_PCT - pl.col('stamp'))
         / (1.0 + COMMISSION_PCT) - 1.0).alias('net'))
    return legs.group_by('buy_date').agg(
        pl.col('net').mean().alias('r'), pl.len().alias('n')).sort('buy_date')


def b1_equity_series(marks: pl.DataFrame, dates: list[date]
                     ) -> np.ndarray:
    """Daily equity marks of B1: mark at the sell day 11:30, i.e. the
    cycle completing on day T marks at T."""
    nxt = {d: nd for d, nd in zip(dates[:-1], dates[1:])}
    dpos = {d: i for i, d in enumerate(dates)}
    eq = np.full(len(dates), np.nan)
    cur = CAPITAL
    for row in marks.iter_rows(named=True):
        nd = nxt.get(row['buy_date'])
        if nd is None:
            continue
        cur *= (1.0 + row['r'])
        eq[dpos[nd]] = cur
    last = CAPITAL
    for i in range(len(dates)):
        if np.isnan(eq[i]):
            eq[i] = last
        else:
            last = eq[i]
    return eq
