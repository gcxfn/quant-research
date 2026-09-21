"""P2-R16 trend + extreme dispersion (exp-20260918-p2r16-trend-dispersion).

Implements the preregistered protocol in
``docs/research/exp-20260918-p2r16-trend-dispersion-prereg.md`` and the frozen
config ``configs/experiments/p2r16-trend-dispersion.json`` EXACTLY:

- universe: SH/SZ main board (sh.60*/sz.00*, index symbols sz.000905/000852
  excluded), non-ST, trading at the signal, 20-own-session median amount
  >= 50,000,000 CNY, close >= 2 CNY, more than 120 own traded sessions
  (identical row filters to the R13 pool; constants and helpers imported
  from ``quant.research.p2r13_lowfreq``);
- membership: liquidity top list by the 20-session median amount with the
  H-47 buffer band (enter only from the top K, leave only when the rank
  drops beyond 2K) - a state machine with no alpha input;
- exposure paths: T200-40 = the R8-published TREND mechanism reused VERBATIM
  by import (``etf_rotation.sma_trend_state`` on the pinned 000300.SH index +
  ``etf_rotation.exposures_from_state`` with R8's E_ON=0.90 / e_low=0.40),
  sampled at month-end closes to set the NEXT month's exposure; FIX75 =
  constant 0.75 (R7/R8 anchor-arm level).  The index (not the pool itself)
  is the trend basis - that is R8's code as published; disclosed in the
  results doc;
- Q5 avoidance filter (filter-on arms only): entry candidates in the top
  decile of the equal-weight composite percentile rank of vol20 x turn20
  are dropped (V2-10 frozen construction: vol20 = 20-own-session std of
  close/preclose-1, turn20 = 20-own-session mean of ``turn``); ENTRY-SIDE
  only - incumbents are never force-exited by Q5 (V2-10 usage property
  "zero turnover increment");
- execution: month-end signal -> next session open; integer lots (100 raw
  shares); per-name target = exposure x equity / K; commission wan-1 with
  5-CNY minimum + segmented sell stamp (0.1% before 2023-08-28, 0.05% on or
  after); suspension or |open-vs-preclose| >= 9.5% proxy blocks the leg at
  that open and it retries at later opens (latest target supersedes;
  superseded legs count as NOT executed, R8 deviation-4 analog);
- accounting: positions are held in corporate-action-consistent chain units
  U with CNY value U * kappa (kappa = raw_close / c_adj of the preclose
  bridge); raw-share lots make the board-lot constraint exact; cash is real
  CNY and never negative; a held name whose quote series ends before the
  data end is force-exited at that last available close with fees (R6/R8
  convention);
- benchmarks: B1(m) = same-pool equal weight, full rebalance every signal,
  same exposure path (mechanism-matched, R7/R8 precedent), fractional units;
  B3' = random K=20 fresh draw per signal (seeds 17-36) through the same
  engine, computed per exposure path (R8 precedent); H-47 evidence arm =
  full-rebalance top-K membership baselines (K in {20,30} x filter {on,off},
  FIX75 path) reported descriptively against the buffer-band configs.

Deviations registered BEFORE any run are listed in ``DEVIATIONS`` (the CLI
records them in the manifest; see also the results doc).
"""
from __future__ import annotations

import hashlib
import inspect
import random
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np
import polars as pl

from quant.research import etf_rotation as er
from quant.research.etf_rotation import (  # VERBATIM R8 mechanism reuse
    cagr,
    exposures_from_state,
    load_index_close,
    max_drawdown,
    slice_curve,
    sma_trend_state,
    year_returns,
)
from quant.research.p2r13_lowfreq import (  # R13 infrastructure reuse
    DEV_END,
    DEV_START,
    FREEZE_LAST,
    LIQ_MEDIAN_AMOUNT,
    MIN_CLOSE,
    NEW_LISTING_SESSIONS,
    VAL_END,
    VAL_START,
    board_ok_expr,
    market_calendar,
    month_end_sessions,
    verify_processed_manifest,
)
from quant.research.screen import FeeBand

# --------------------------------------------------------------------------- #
# frozen protocol constants
# --------------------------------------------------------------------------- #
CAPITAL: float = 200_000.0
K_VALUES: tuple[int, ...] = (20, 30)
E_ON: float = 0.90           # R8 registered level-on for the TREND path
E_LOW: float = 0.40          # T200-40: the frozen e_low
FIX75_LEVEL: float = 0.75    # R7/R8 anchor-arm exposure
LOT: int = 100               # A-share board lot (raw shares)
LIMIT_PROXY: float = 0.095   # R6/R7/R8 registered open-vs-preclose proxy
Q5_TOP_DECILE: float = 0.90  # drop the top 10% of the composite rank
B3_SEEDS: tuple[int, ...] = tuple(range(17, 37))
STAMP_CUT: date = date(2023, 8, 28)

STOCK_FEE_SCHEDULE: tuple[FeeBand, ...] = (
    FeeBand(from_date=date(2015, 1, 1), commission_pct=0.0001,
            commission_min=5.0, stamp_sell_pct=0.001),
    FeeBand(from_date=STAMP_CUT, commission_pct=0.0001,
            commission_min=5.0, stamp_sell_pct=0.0005),
)
# B1(m) primary fee convention (DEVIATIONS item 2): the equal-weight pool
# benchmark holds ~1000-2000 names on 200k CNY -> per-leg notionals of
# ~50-150 CNY; the 5-CNY per-order minimum would charge ~3-10% per side and
# destroy the benchmark the prereg's gate design assumes (gate 2 is expected
# to be the DECIDING gate).  B1 pays the SAME rates with NO per-order
# minimum; the literal per-leg-minimum variant is computed as a disclosed
# sensitivity.  The strategy and B3' always pay the literal schedule.
B1_FEE_SCHEDULE_RATE_ONLY: tuple[FeeBand, ...] = (
    FeeBand(from_date=date(2015, 1, 1), commission_pct=0.0001,
            commission_min=0.0, stamp_sell_pct=0.001),
    FeeBand(from_date=STAMP_CUT, commission_pct=0.0001,
            commission_min=0.0, stamp_sell_pct=0.0005),
)

# --------------------------------------------------------------------------- #
# R8 mechanism identity chain (fail-closed)
# --------------------------------------------------------------------------- #
# src/quant/research/etf_rotation.py as executed by the COMPLETED R9 formal
# run 20260918T030528-p2r9-risk-delivery-ef2777dc, whose registered anchor
# regressions reproduce R8's published C01/C09/B1-100 curves bit-exactly
# (metrics.anchor_regressions.all_pass=true).  Every completed run since R9
# (R10/R11/R12/R13) pinned the same bytes.  The R8 formal run pinned an
# earlier file revision (9d283200..., before the R9 hysteresis additions);
# the R8-era bytes are not archived, so the equivalence chain to R8 is:
# current bytes == R9-verified bytes  AND  R9 anchors bit-exact vs R8  AND
# the R8-published T200 daily state statistics (configs.C02) are reproduced
# exactly on this round's calendar (``t200_behavioral_anchor`` below).
R8_MODULE_SHA256: str = ('1c064efce2cf211505f62f46ac61ca39abf63c1f529e00851'
                         '8a8b26d2ca59b70')
R8_RUN_DIR = '20260918T021054-p2r8-daily-risk-d19a9c07'
R9_RUN_DIR = '20260918T030528-p2r9-risk-delivery-ef2777dc'

# R8 published C02 (T200-L0.40) DAILY switch statistics for dev years
# 2016-2020 (artifacts/runs/<R8_RUN_DIR>/metrics.json -> configs.C02.dev
# .switch_stats_by_year), asserted against the verbatim-reused mechanism on
# this round's calendar (behavioral anchor of the reuse).
T200_BEHAVIORAL_ANCHOR: dict[str, dict] = {
    '2016': {'n_sessions': 244, 'n_switches': 5, 'off_share': 0.623,
             'mean_exposure': 0.5885},
    '2017': {'n_sessions': 244, 'n_switches': 2, 'off_share': 0.0164,
             'mean_exposure': 0.8918},
    '2018': {'n_sessions': 243, 'n_switches': 3, 'off_share': 0.786,
             'mean_exposure': 0.507},
    '2019': {'n_sessions': 244, 'n_switches': 3, 'off_share': 0.1066,
             'mean_exposure': 0.8467},
    '2020': {'n_sessions': 243, 'n_switches': 6, 'off_share': 0.1687,
             'mean_exposure': 0.8156},
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def assert_mechanism_identity() -> dict:
    """Fail-closed R8 mechanism reuse assertion (registered requirement).

    1. the imported ``etf_rotation`` module file must hash to
       ``R8_MODULE_SHA256`` (the R9-anchored bytes, also pinned by every
       completed run since R9);
    2. the VERBATIM-reused functions must come from that module (no local
       redefinition); their source hashes are recorded for future rounds.
    """
    module_file = Path(er.__file__)
    got = sha256_file(module_file)
    if got != R8_MODULE_SHA256:
        raise RuntimeError(
            f'FAIL-CLOSED R8 mechanism identity: {module_file} sha256 {got} '
            f'!= pinned {R8_MODULE_SHA256} (the TREND path must be reused '
            'verbatim from the R8/R9-verified module)')
    funcs: dict[str, str] = {}
    for name in ('sma_trend_state', 'exposures_from_state',
                 'constant_risk_fn'):
        fn = getattr(er, name)
        if fn.__module__ != 'quant.research.etf_rotation':
            raise RuntimeError(
                f'FAIL-CLOSED: {name} does not come from the pinned module')
        funcs[name] = hashlib.sha256(
            inspect.getsource(fn).encode('utf-8')).hexdigest()
    return {'module_file': str(module_file), 'module_sha256': got,
            'function_source_sha256': funcs,
            'r8_run_dir': R8_RUN_DIR, 'r9_run_dir': R9_RUN_DIR}


# --------------------------------------------------------------------------- #
# exposure paths (month-end sampled)
# --------------------------------------------------------------------------- #
def t200_state(index_close: pl.DataFrame,
               calendar: list[date]) -> dict[date, bool]:
    """R8 T200 VERBATIM: ``sma_trend_state`` on the pinned index (SMA200
    index sessions; unavailable -> risk-off, registered fallback)."""
    return sma_trend_state(index_close, calendar, 200)


def t200_month_end_exposures(index_close: pl.DataFrame, calendar: list[date],
                             signal_days: list[date]) -> dict[date, float]:
    """R8 T200-40 VERBATIM, month-end sampled: exposure levels from
    ``er.exposures_from_state(state, E_ON, E_LOW)`` at each signal close."""
    daily_e = exposures_from_state(t200_state(index_close, calendar),
                                   E_ON, E_LOW)
    return {d: daily_e[d] for d in signal_days}


def fix75_exposures(signal_days: list[date]) -> dict[date, float]:
    return {d: FIX75_LEVEL for d in signal_days}


def t200_fallback_signal_dates(index_close: pl.DataFrame,
                               calendar: list[date],
                               signal_days: list[date]) -> list[date]:
    """Month-end signals where the SMA200 is unavailable at that close (the
    registered fallback forces risk-off there; count disclosed)."""
    frame = index_close.with_columns(
        pl.col('close').rolling_mean(200, min_samples=200).alias('_sma'))
    first_valid = None
    for d, s in zip(frame['trade_date'].to_list(), frame['_sma'].to_list()):
        if s is not None:
            first_valid = d
            break
    if first_valid is None:
        return list(signal_days)
    return [d for d in signal_days if d < first_valid]


def switch_stats(sessions: list[date], states: dict[date, bool],
                 e_low: float = E_LOW, e_on: float = E_ON) -> dict:
    """Per-year daily switch statistics of a state path (R8's published
    format, used by the behavioral anchor)."""
    per_year: dict[int, dict] = {}
    prev: bool | None = None
    for day in sessions:
        s = states[day]
        e = e_on if s else e_low
        y = per_year.setdefault(day.year, {'n_sessions': 0, 'n_switches': 0,
                                           'off_sessions': 0, 'sum_e': 0.0})
        y['n_sessions'] += 1
        y['sum_e'] += e
        if prev is not None and s != prev:
            y['n_switches'] += 1
        if not s:
            y['off_sessions'] += 1
        prev = s
    return {str(y): {'n_sessions': v['n_sessions'],
                     'n_switches': v['n_switches'],
                     'off_share': round(v['off_sessions'] / v['n_sessions'],
                                        4),
                     'mean_exposure': round(v['sum_e'] / v['n_sessions'], 4)}
            for y, v in sorted(per_year.items())}


def t200_behavioral_anchor_check(index_close: pl.DataFrame,
                                 calendar: list[date]) -> dict:
    """Hard assertion that the verbatim-reused T200 mechanism reproduces the
    R8-published C02 daily state statistics on this round's calendar over
    the R8 dev years 2016-2020 (fail-closed; the R8 equivalence chain is
    DEVIATIONS item 5)."""
    states = t200_state(index_close, calendar)
    r16_sessions = [d for d in calendar
                    if date(2016, 1, 1) <= d <= date(2020, 12, 31)]
    got = {y: v for y, v in switch_stats(r16_sessions, states).items()
           if y in T200_BEHAVIORAL_ANCHOR}
    mismatches = {y: {'got': got.get(y),
                      'r8_published': T200_BEHAVIORAL_ANCHOR[y]}
                  for y in T200_BEHAVIORAL_ANCHOR
                  if got.get(y) != T200_BEHAVIORAL_ANCHOR[y]}
    if mismatches:
        raise RuntimeError(
            'FAIL-CLOSED T200 behavioral anchor: reproduced daily state '
            f'stats differ from the R8 published C02 values: {mismatches}')
    return {'anchor_years': sorted(T200_BEHAVIORAL_ANCHOR),
            'reproduced_stats': got, 'all_match': True}


# --------------------------------------------------------------------------- #
# history frame (R13 conventions: own-session windows, shift INSIDE .over)
# --------------------------------------------------------------------------- #
def build_history_r16(daily_path, cal: pl.DataFrame,
                      warmup_start: date = date(2012, 1, 1)) -> pl.DataFrame:
    """(symbol, session) frame with chain prices and the pool/Q5 inputs.

    Every shift/rolling lives INSIDE ``.over('symbol')`` (P2-R10 M-1 rule).
    ``listing_index`` counts ALL own traded sessions since the file start so
    pre-2015 listings are never "new" in 2015.  Rows on/after 2025-01-01 are
    dropped here (2025+ zero-touch, structural).
    """
    hist = (
        pl.scan_parquet(daily_path)
        .filter(pl.col('tradestatus') == 1.0)
        .sort('symbol', 'date')
        .select(
            'symbol', 'date', 'open', 'close', 'preclose', 'amount', 'turn',
            'isST',
            pl.int_range(pl.len()).over('symbol', order_by='date')
            .add(1).alias('listing_index'))
        .filter((pl.col('date') >= warmup_start)
                & (pl.col('date') <= FREEZE_LAST))
        .join(cal.lazy(), on='date', how='inner')
        .sort('symbol', 'date')
    )
    df = hist.collect()
    df = df.with_columns(
        (pl.col('close') / pl.col('preclose') - 1.0).alias('r'))
    df = df.with_columns(
        (pl.col('close') / pl.col('preclose')).cum_prod().over('symbol')
        .alias('c_adj'))
    df = df.with_columns(
        (pl.col('c_adj').shift(1).over('symbol')
         * pl.col('open') / pl.col('preclose')).alias('o_adj'))
    df = df.with_columns([
        pl.col('amount').rolling_median(20, min_samples=20)
        .over('symbol').alias('amt_med20'),
        pl.col('r').rolling_std(20, min_samples=20)
        .over('symbol').alias('vol20'),
        pl.col('turn').rolling_mean(20, min_samples=20)
        .over('symbol').alias('turn20'),
    ])
    leg_nulls = df.filter(pl.col('c_adj').is_null()
                          & (pl.col('listing_index') > 1))
    if leg_nulls.height:
        raise RuntimeError(
            f'null price leg in traded rows breaks the preclose bridge: '
            f'{leg_nulls.height} rows, e.g. '
            f'{leg_nulls.select("symbol", "date").head(3).rows()}')
    return df


def signal_pools(hist: pl.DataFrame, signals: pl.DataFrame) -> pl.DataFrame:
    """Frozen pool filters at each month-end signal + ranks + Q5 flags.

    Rows at signal session s with isST==0, listing_index>120, main board,
    amt_med20>=50M, close>=2 (identical row filters to the R13 pool).
    ``rank`` = 1-based rank by amt_med20 DESC, symbol ASC (deterministic).
    ``q5`` = True when the name is in the top decile of the composite itself
    (percentile rank of the equal-weight mean of the vol20 and turn20
    percentile ranks within the rankable cross-section > 0.90; V2-10
    construction: vol20 = 20-own-session std of close/preclose-1, turn20 =
    20-own-session mean of ``turn``); names with uncomputable vol20/turn20
    are NOT classified (q5=False, kept as entry candidates - the filter
    removes only the rankable top decile, per the V2-10 definition).
    """
    base = (hist.join(signals.select('s'), left_on='date', right_on='s',
                      how='inner')
            .filter(pl.col('isST') == 0.0)
            .filter(pl.col('listing_index') > NEW_LISTING_SESSIONS)
            .filter(board_ok_expr())
            .filter(pl.col('amt_med20') >= LIQ_MEDIAN_AMOUNT)
            .filter(pl.col('close') >= MIN_CLOSE))
    base = base.select(pl.col('date').alias('s'), 'symbol', 'amt_med20',
                       'vol20', 'turn20', 'close').sort('s', 'symbol')
    base = base.with_columns(
        ((pl.col('vol20').rank(method='average').over('s') - 1.0)
         / (pl.len().over('s') - 1.0)).alias('_rv'))
    base = base.with_columns(
        ((pl.col('turn20').rank(method='average').over('s') - 1.0)
         / (pl.len().over('s') - 1.0)).alias('_rt'))
    base = base.with_columns(
        ((pl.col('_rv') + pl.col('_rt')) / 2.0).alias('q5_comp'))
    base = base.with_columns(
        pl.col('amt_med20').rank(method='ordinal', descending=True)
        .over('s').cast(pl.Int64).alias('rank'))
    # Q5 = top DECILE of the composite itself (V2-10 "双高尾部十分位"):
    # percentile rank of q5_comp within the rankable cross-section
    base = base.with_columns(
        ((pl.col('q5_comp').rank(method='average').over('s') - 1.0)
         / (pl.col('q5_comp').is_not_null().sum().over('s') - 1.0))
        .alias('q5_pct'))
    base = base.with_columns(
        ((pl.col('q5_pct') > Q5_TOP_DECILE).fill_null(False))
        .alias('q5'))
    return base.sort('s', 'rank', 'symbol')


def pools_by_signal(pool_frame: pl.DataFrame) -> dict[date, dict]:
    """-> {signal_date: {'ranked': [symbol in rank order], 'q5': {sym: bool},
    'n': int}}."""
    out: dict[date, dict] = {}
    for (s,), g in pool_frame.group_by(['s'], maintain_order=True):
        ranked = g.sort('rank', 'symbol')['symbol'].to_list()
        q5 = dict(zip(g['symbol'].to_list(),
                      (bool(x) for x in g['q5'].to_list())))
        out[s] = {'ranked': ranked, 'q5': q5, 'n': len(ranked)}
    return out


# --------------------------------------------------------------------------- #
# membership rules
# --------------------------------------------------------------------------- #
def buffer_membership(prev: list[str], ranked: list[str],
                      q5: dict[str, bool], K: int,
                      q5_entry_filter: bool) -> tuple[list[str], dict]:
    """H-47 buffer band state machine: incumbents stay while their liquidity
    rank is <= 2K; new names enter only from the top K (and only when not
    Q5-flagged on filter-on arms); seats freed by leavers are filled in rank
    order; seats that cannot be filled from the eligible top K stay CASH
    (rule-compliant cash slot).  Q5 never force-exits an incumbent (V2-10
    usage property: zero turnover increment)."""
    rank_of = {c: i + 1 for i, c in enumerate(ranked)}
    kept = [m for m in prev if m in rank_of and rank_of[m] <= 2 * K]
    kept_set = set(kept)
    seats = K - len(kept)
    entrants: list[str] = []
    for c in ranked[:K]:
        if seats <= 0:
            break
        if c in kept_set or c in entrants:
            continue
        if q5_entry_filter and q5.get(c, False):
            continue
        entrants.append(c)
        seats -= 1
    info = {'n_kept': len(kept), 'n_entrants': len(entrants),
            'n_prev': len(prev), 'n_left': len(prev) - len(kept),
            'n_cash_seats': K - len(kept) - len(entrants)}
    return kept + entrants, info


def full_rebalance_membership(prev: list[str], ranked: list[str],
                              q5: dict[str, bool], K: int,
                              q5_entry_filter: bool,
                              ) -> tuple[list[str], dict]:
    """Full-rebaseline comparator (H-47 evidence arm): fresh top-K every
    signal, no state (``prev`` ignored)."""
    out: list[str] = []
    for c in ranked:
        if len(out) >= K:
            break
        if q5_entry_filter and q5.get(c, False):
            continue
        out.append(c)
    return out, {'n_kept': 0, 'n_entrants': len(out), 'n_prev': len(prev),
                 'n_left': 0, 'n_cash_seats': K - len(out)}


def random_membership(prev: list[str], ranked: list[str],
                      q5: dict[str, bool], rng: random.Random | None,
                      K: int) -> tuple[list[str], dict]:
    """B3' random membership: fresh seeded draw of K names each signal
    (``prev`` ignored: random ranks have no buffer state)."""
    codes = list(ranked)
    rng.shuffle(codes)
    return codes[:K], {'n_kept': 0, 'n_entrants': min(K, len(codes)),
                       'n_prev': len(prev), 'n_left': 0,
                       'n_cash_seats': max(0, K - len(codes))}


# --------------------------------------------------------------------------- #
# price bank (dense per-symbol arrays over the market calendar index)
# --------------------------------------------------------------------------- #
class PriceBank:
    """Dense float64 arrays (n_symbols x n_sessions) of the preclose-bridge
    chain prices, raw open/close and the open gap.

    ``kappa`` is the back-adjusted CLOSE in CNY: c_adj * K0 where K0 is the
    symbol's first loaded preclose; ``kappa_open`` the same for the adjusted
    open (o_adj * K0).  ``kappa_ff`` forward-fills kappa across the symbol's
    own sessions (mark a suspended name at its last own close); kappa_prev
    is kappa_ff delayed by one session (the value known at an open BEFORE
    that session's close exists - no intraday look-ahead in trade sizing).

    Positions are held in ADJUSTED UNITS u (invariant across corporate
    actions by construction of the bridge): CNY value = u * kappa.  Buying
    dS raw shares at an open costs cash dS * raw_open and adds
    u += dS * raw_open / kappa_open; the CURRENT raw share count of a
    position is derived on demand as u * kappa_open / raw_open (corporate
    actions multiply the real share count exactly through this identity).
    """

    def __init__(self, hist: pl.DataFrame, calendar: list[date],
                 symbols: list[str]):
        self.calendar = list(calendar)
        self.symbols = list(symbols)
        self.sym_idx = {s: i for i, s in enumerate(self.symbols)}
        n, t = len(self.symbols), len(self.calendar)
        shape = (n, t)
        self.kappa = np.full(shape, np.nan)      # adj close (c_adj * K0)
        self.kappa_open = np.full(shape, np.nan)  # adj open (o_adj * K0)
        self.raw_open = np.full(shape, np.nan)
        self.raw_close = np.full(shape, np.nan)
        self.gap = np.full(shape, np.nan)         # open/preclose - 1
        self.kappa_ff = np.full(shape, np.nan)
        self.kappa_prev = np.full(shape, np.nan)
        self.last_own = np.full(n, -1, dtype=np.int64)
        sub = (hist.filter(pl.col('symbol').is_in(self.symbols))
               .sort('symbol', 'mkt_idx')
               .with_columns(
                   pl.col('preclose').first().over('symbol').alias('_k0'),
                   (pl.col('open') / pl.col('preclose') - 1.0)
                   .alias('_gap')))
        sub = sub.with_columns(
            (pl.col('c_adj') * pl.col('_k0')).alias('_kappa'),
            (pl.col('o_adj') * pl.col('_k0')).alias('_kappa_open'))
        rows = np.fromiter((self.sym_idx[s] for s in
                            sub['symbol'].to_list()), dtype=np.int64,
                           count=sub.height)
        cols = sub['mkt_idx'].to_numpy().astype(np.int64)
        self.kappa[rows, cols] = sub['_kappa'].to_numpy()
        self.kappa_open[rows, cols] = sub['_kappa_open'].to_numpy()
        self.raw_open[rows, cols] = sub['open'].to_numpy()
        self.raw_close[rows, cols] = sub['close'].to_numpy()
        self.gap[rows, cols] = sub['_gap'].to_numpy()
        for i in range(n):
            row = self.kappa[i]
            mask = np.isfinite(row)
            if mask.any():
                idx = np.where(mask, np.arange(t), -1)
                np.maximum.accumulate(idx, out=idx)
                self.kappa_ff[i] = row[np.maximum(idx, 0)]
                self.last_own[i] = np.max(np.nonzero(mask)[0])
        self.kappa_prev[:, 1:] = self.kappa_ff[:, :-1]
        self.idx_of = {d: i for i, d in enumerate(self.calendar)}

    def tradable(self, sym: str, si: int) -> bool:
        i = self.sym_idx.get(sym)
        return (i is not None and 0 <= si < self.kappa.shape[1]
                and np.isfinite(self.kappa_open[i, si]))


# --------------------------------------------------------------------------- #
# simulation engine (one continuous curve; segments are slices)
# --------------------------------------------------------------------------- #
EXECUTED_OUTCOMES = frozenset({'filled', 'postponed_then_filled',
                               'at_target', 'no_lots', 'cash_capped',
                               'feemin_skipped'})


@dataclass
class R16Result:
    config_id: str
    sessions: list[date] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    leg_log: list[dict] = field(default_factory=list)
    positions: list[dict] = field(default_factory=list)
    final_open: list[dict] = field(default_factory=list)
    turnover_acc: dict[int, dict] = field(default_factory=dict)
    membership_turnover: dict[int, dict] = field(default_factory=dict)
    max_weight: list[float] = field(default_factory=list)
    membership_events: list[dict] = field(default_factory=list)
    n_members_series: list[int] = field(default_factory=list)
    min_cash: float = float('inf')
    planned_legs: int = 0
    executed_legs: int = 0

    def book(self, year: int) -> dict:
        return self.turnover_acc.setdefault(
            year, {'buy_notional': 0.0, 'sell_notional': 0.0})

    def mbook(self, year: int) -> dict:
        return self.membership_turnover.setdefault(
            year, {'buy_notional': 0.0, 'sell_notional': 0.0})


def _fee_band(day: date, bands: tuple[FeeBand, ...]) -> FeeBand:
    selected = bands[0]
    for band in bands:
        if day >= band.from_date:
            selected = band
        else:
            break
    return selected


def _buy_fee(notional: float, band: FeeBand) -> float:
    return max(notional * band.commission_pct, band.commission_min)


def _sell_fee(notional: float, band: FeeBand) -> float:
    return (max(notional * band.commission_pct, band.commission_min)
            + notional * band.stamp_sell_pct)


def simulate_r16(config_id: str, bank: PriceBank, calendar: list[date],
                 start: date, signal_days: list[date],
                 pools_at: dict[date, dict], exposures: dict[date, float],
                 *, K: int,
                 membership_fn: Callable[
                     [list[str], list[str], dict[str, bool],
                      random.Random | None],
                     tuple[list[str], dict]] | None = None,
                 fractional: bool = False,
                 fee_bands: tuple[FeeBand, ...] = STOCK_FEE_SCHEDULE,
                 seed: int | None = None,
                 capital: float = CAPITAL) -> R16Result:
    """Monthly engine: buffer-band membership, next-open execution, integer
    lots, postpone/supersede semantics, chain-unit accounting.

    fractional=True renders B1(m): the WHOLE pool equally weighted with
    fractional chain units (benchmark idealization; ``fee_bands`` selects
    the fee convention - see DEVIATIONS item 2).  B3' passes
    ``membership_fn=random_membership`` with a seed.
    """
    result = R16Result(config_id=config_id)
    rng = random.Random(seed) if seed is not None else None
    start_idx = next(i for i, d in enumerate(calendar) if d >= start)
    idx_of = bank.idx_of
    sig_at = {idx_of[d]: d for d in signal_days if d in idx_of}
    cash = capital
    U: dict[str, float] = {}       # adjusted units (corp-action invariant)
    open_entry: dict[str, dict] = {}
    pending: dict[str, dict] = {}
    current_members: list[str] = []

    def _raw_shares(sym: str, si: int) -> float:
        """Current raw share count of a held position at this open, derived
        from the adjusted units (corporate actions flow through exactly)."""
        u = U.get(sym, 0.0)
        if u <= 1e-9:
            return 0.0
        i = bank.sym_idx[sym]
        return u * float(bank.kappa_open[i, si]) \
            / float(bank.raw_open[i, si])

    def mark(si: int) -> float:
        if not U:
            return cash
        if fractional:
            i0 = si
            vec = np.zeros(len(bank.symbols))
            for sym, u in U.items():
                vec[bank.sym_idx[sym]] = u
            col = bank.kappa_ff[:, i0]
            return cash + float(np.dot(np.nan_to_num(col), vec))
        total = cash
        for sym, u in U.items():
            k = bank.kappa_ff[bank.sym_idx[sym], si]
            if np.isfinite(k):
                total += u * k
        return total

    def close_order(sym: str, o: dict) -> None:
        row = o['row']
        row['outcome'] = o.get('outcome')
        row['exec_date'] = o.get('exec_date')
        row['notional'] = o.get('notional')
        row['fee'] = o.get('fee')
        pending.pop(sym, None)

    for si in range(start_idx, len(calendar)):
        day = calendar[si]

        # ---- 1. pending orders at today's open (sells first) -------------
        def plan_side(o: dict) -> str:
            if o.get('outcome') is not None:
                return 'done'
            sym = o['symbol']
            if o['kind'] == 'sell_full':
                return 'sell'
            if not bank.tradable(sym, si):
                return 'buy'  # untradable: retry; side irrelevant now
            i = bank.sym_idx[sym]
            price = float(bank.raw_open[i, si])
            if fractional:
                prev_k = bank.kappa_prev[i, si]
                cur = U.get(sym, 0.0) * prev_k if np.isfinite(prev_k) \
                    else None
                if cur is None:
                    return 'hold'
                return 'sell' if o['target'] < cur else 'buy'
            target_shares = int(o['target'] / (price * LOT)) * LOT
            cur_sh = _raw_shares(sym, si)
            return 'sell' if target_shares < cur_sh else 'buy'

        orders = [pending[s] for s in sorted(pending)]
        for want_side in ('sell', 'buy'):
            for o in orders:
                if o.get('outcome') is not None:
                    continue  # already executed in the other pass
                sym = o['symbol']
                side = plan_side(o)
                if side != want_side:
                    if side == 'hold':
                        o['n_retry'] = o.get('n_retry', 0) + 1
                    continue
                if not bank.tradable(sym, si):
                    o['n_retry'] = o.get('n_retry', 0) + 1
                    continue  # suspended: retry at a later open
                i = bank.sym_idx[sym]
                price = float(bank.raw_open[i, si])
                kappa_open = float(bank.kappa_open[i, si])
                gap = float(bank.gap[i, si])
                band = _fee_band(day, fee_bands)
                postponed = o.get('n_retry', 0) > 0
                kind = o['kind']
                if want_side == 'sell':
                    if gap <= -LIMIT_PROXY:
                        o['n_retry'] = o.get('n_retry', 0) + 1
                        continue  # limit-down proxy blocks the sell
                    prev_k = bank.kappa_prev[i, si]
                    cur_val = U.get(sym, 0.0) * prev_k \
                        if np.isfinite(prev_k) else 0.0
                    cur_sh = _raw_shares(sym, si)
                    if fractional:
                        # fractional: trade CNY value directly
                        sh = (cur_val if o['kind'] == 'sell_full'
                              else max(0.0, cur_val - o['target']))
                        gross = sh
                    else:
                        sh = (cur_sh if o['kind'] == 'sell_full'
                              else cur_sh
                              - int(o['target'] / (price * LOT)) * LOT)
                        gross = sh * price
                    if gross <= band.commission_min and gross > 0:
                        # de-minimis guard (R8 deviation-9 analog): the
                        # minimum commission would exceed the proceeds and
                        # overdraw the never-negative cash pool
                        o['outcome'] = 'feemin_skipped'
                        o['exec_date'] = day
                        close_order(sym, o)
                        continue
                    if gross <= 0:
                        o['outcome'] = 'at_target'
                        o['exec_date'] = day
                        close_order(sym, o)
                        continue
                    fee = _sell_fee(gross, band)
                    cash += gross - fee
                    if fractional:
                        if o['kind'] == 'sell_full' or gross >= cur_val:
                            U.pop(sym, None)
                        else:
                            U[sym] = U.get(sym, 0.0) * (1.0 - gross
                                                        / cur_val)
                    else:
                        U[sym] = U.get(sym, 0.0) - gross / kappa_open
                        if U[sym] <= 1e-9:
                            U.pop(sym, None)
                    result.book(day.year)['sell_notional'] += gross
                    if o.get('member', False):
                        result.mbook(day.year)['sell_notional'] += gross
                    entry = None
                    if o['kind'] == 'sell_full' and not fractional:
                        entry = open_entry.pop(sym, None)
                        if entry is not None:
                            result.positions.append({
                                **entry, 'exit_day': day,
                                'exit_raw': price, 'sell_fee': fee,
                                'proceeds': gross - fee,
                                'exit_kind': kind,
                                'pnl': gross - fee - entry['budget']})
                    else:
                        entry = open_entry.get(sym)
                        if entry is not None and cur_val > 0:
                            frac = gross / cur_val
                            entry['units'] *= (1.0 - frac)
                            entry['budget'] *= (1.0 - frac)
                    result.trades.append({
                        'session': day, 'symbol': sym, 'side': 'sell',
                        'kind': kind, 'raw_price': price,
                        'shares': (0.0 if fractional else sh),
                        'notional': gross, 'fee': fee,
                        'entry_day': (entry or {}).get('entry_day')})
                    o['outcome'] = ('postponed_then_filled' if postponed
                                    else 'filled')
                    o['exec_date'] = day
                    o['notional'] = gross
                    o['fee'] = fee
                    close_order(sym, o)
                else:  # buy leg (entrant or rescale up)
                    if gap >= LIMIT_PROXY:
                        o['n_retry'] = o.get('n_retry', 0) + 1
                        continue  # limit-up proxy blocks the buy
                    cur_sh = _raw_shares(sym, si)
                    if fractional:
                        cur_units = U.get(sym, 0.0)
                        prev_k = bank.kappa_prev[i, si]
                        cur_val = cur_units * prev_k \
                            if np.isfinite(prev_k) else 0.0
                        delta_val = o['target'] - cur_val
                        if delta_val <= 1e-9:
                            o['outcome'] = 'at_target'
                            o['exec_date'] = day
                            close_order(sym, o)
                            continue
                        fee = _buy_fee(delta_val, band)
                        if delta_val > cash + 1e-6:
                            o['outcome'] = 'cash_capped'
                            o['exec_date'] = day
                            close_order(sym, o)
                            continue
                        cash -= delta_val
                        U[sym] = cur_units + (delta_val - fee) / kappa_open
                        result.book(day.year)['buy_notional'] += delta_val
                        o['outcome'] = ('postponed_then_filled' if postponed
                                        else 'filled')
                        o['exec_date'] = day
                        o['notional'] = delta_val
                        o['fee'] = fee
                        close_order(sym, o)
                    else:
                        target_shares = int(o['target'] / (price * LOT)) \
                            * LOT
                        delta_sh = target_shares - cur_sh
                        lots = (int(delta_sh // LOT) * LOT
                                if delta_sh > 0 else 0)
                        if lots <= 0:
                            o['outcome'] = 'at_target'
                            o['exec_date'] = day
                            close_order(sym, o)
                            continue
                        while lots > 0:
                            cost = lots * price
                            fee = _buy_fee(cost, band)
                            if cost + fee <= cash + 1e-6:
                                break
                            lots -= LOT
                        if lots <= 0:
                            o['outcome'] = ('no_lots'
                                            if target_shares < price * LOT
                                            else 'cash_capped')
                            o['exec_date'] = day
                            close_order(sym, o)
                            continue
                        cost = lots * price
                        fee = _buy_fee(cost, band)
                        cash -= cost + fee
                        new_units = cost / kappa_open
                        opened = U.get(sym, 0.0) <= 1e-9
                        if opened:
                            open_entry[sym] = {
                                'symbol': sym, 'entry_day': day,
                                'budget': cost + fee, 'units': new_units,
                                'entry_raw': price, 'buy_fee': fee}
                        else:
                            oe = open_entry.get(sym)
                            if oe is not None:
                                oe['budget'] += cost + fee
                                oe['units'] += new_units
                        U[sym] = U.get(sym, 0.0) + new_units
                        result.book(day.year)['buy_notional'] += cost
                        if opened and o.get('member', False):
                            result.mbook(day.year)['buy_notional'] += cost
                        result.trades.append({
                            'session': day, 'symbol': sym, 'side': 'buy',
                            'kind': kind, 'raw_price': price,
                            'shares': lots, 'notional': cost, 'fee': fee,
                            'entry_day': open_entry.get(sym, {})
                            .get('entry_day')})
                        o['outcome'] = ('postponed_then_filled' if postponed
                                        else 'filled')
                        o['exec_date'] = day
                        o['notional'] = cost
                        o['fee'] = fee
                        close_order(sym, o)

        # ---- 2. force-exit at the last own-session close -----------------
        for sym in sorted(list(U)):
            u = U.get(sym, 0.0)
            if u <= 1e-9:
                continue
            i = bank.sym_idx[sym]
            if bank.last_own[i] != si or si >= len(calendar) - 1:
                continue  # data-end rows are final_open, not delists
            if fractional:
                continue  # benchmark marks at the last close, no exit trade
            close_raw = float(bank.raw_close[i, si])
            k_close = float(bank.kappa[i, si])
            sh = u * k_close / close_raw  # current raw count at this close
            gross = sh * close_raw
            band = _fee_band(day, fee_bands)
            fee = _sell_fee(gross, band)
            cash += gross - fee
            U.pop(sym, None)
            entry = open_entry.pop(sym, None)
            if entry is not None:
                result.positions.append({
                    **entry, 'exit_day': day, 'exit_raw': close_raw,
                    'sell_fee': fee, 'proceeds': gross - fee,
                    'exit_kind': 'forced_delist_close',
                    'pnl': gross - fee - entry['budget']})
            result.book(day.year)['sell_notional'] += gross
            result.trades.append({
                'session': day, 'symbol': sym, 'side': 'sell',
                'kind': 'forced_delist_close', 'raw_price': close_raw,
                'shares': sh, 'notional': gross, 'fee': fee,
                'entry_day': (entry or {}).get('entry_day')})

        # ---- 3. month-end signal at this close ---------------------------
        t = sig_at.get(si)
        if t is not None:
            pool = pools_at.get(t)
            if pool is None:
                raise RuntimeError(f'{config_id}: missing pool at {t}')
            ranked: list[str] = pool['ranked']
            q5map: dict[str, bool] = pool['q5']
            exposure = exposures[t]
            base = mark(si)
            if fractional:
                members_next = list(ranked)
                info = {'n_kept': 0, 'n_entrants': len(ranked),
                        'n_left': 0, 'n_cash_seats': 0}
            else:
                members_next, info = membership_fn(current_members, ranked,
                                                   q5map, rng)
            result.membership_events.append({'signal': t, **info})
            result.n_members_series.append(len(members_next))
            target_per = (exposure * base
                          / (max(1, len(ranked)) if fractional else K))
            # supersede stale pending orders (latest target wins)
            for sym, o in pending.items():
                if o.get('outcome') is None:
                    o['row']['outcome'] = 'superseded'
            pending = {}
            members_set = set(members_next)
            for sym in sorted(U):
                if U.get(sym, 0.0) > 1e-9 and sym not in members_set \
                        and sym not in pending:
                    row = {'plan_date': t, 'symbol': sym,
                           'kind': 'sell_full', 'target': 0.0,
                           'outcome': None, 'exec_date': None,
                           'notional': None, 'fee': None}
                    result.leg_log.append(row)
                    pending[sym] = {'symbol': sym, 'kind': 'sell_full',
                                    'plan_date': t, 'target': 0.0,
                                    'member': True, 'row': row}
            for sym in members_next:
                if sym in pending:
                    continue
                kind = ('rescale' if U.get(sym, 0.0) > 1e-9
                        else 'buy_open')
                row = {'plan_date': t, 'symbol': sym, 'kind': kind,
                       'target': target_per, 'outcome': None,
                       'exec_date': None, 'notional': None, 'fee': None}
                result.leg_log.append(row)
                pending[sym] = {'symbol': sym, 'kind': kind,
                                'plan_date': t, 'target': target_per,
                                'member': True, 'row': row}
            current_members = list(members_next)

        # ---- 4. daily mark ----------------------------------------------
        eq = mark(si)
        if cash < -1e-6:
            raise RuntimeError(
                f'{config_id}: negative cash {cash:.6f} at {day}')
        result.min_cash = min(result.min_cash, cash)
        denom = eq if eq > 0 else 1.0
        wmax = 0.0
        for sym, u in U.items():
            k = bank.kappa_ff[bank.sym_idx[sym], si]
            if np.isfinite(k):
                wmax = max(wmax, u * k / denom)
        result.max_weight.append(wmax)
        result.sessions.append(day)
        result.equity.append(eq)

    for sym, o in pending.items():
        if o.get('outcome') is None:
            o['row']['outcome'] = 'pending_at_end'
    result.planned_legs = len(result.leg_log)
    result.executed_legs = sum(
        1 for r in result.leg_log if r['outcome'] in EXECUTED_OUTCOMES)
    si_last = len(result.sessions) - 1
    for sym in sorted(U):
        u = U.get(sym, 0.0)
        if u > 1e-9:
            i = bank.sym_idx[sym]
            k = bank.kappa_ff[i, si_last]
            sh = (u * float(bank.kappa_open[i, si_last])
                  / float(bank.raw_open[i, si_last])
                  if np.isfinite(bank.kappa_open[i, si_last]) else 0.0)
            result.final_open.append({
                'symbol': sym, 'shares': sh, 'units': u,
                'open_at_end': True,
                'mark_close': u * k if np.isfinite(k) else 0.0})
    return result


# --------------------------------------------------------------------------- #
# metrics and gates (frozen thresholds from the prereg / frozen config)
# --------------------------------------------------------------------------- #
def jsonable(obj):
    """Recursively convert numpy scalars/arrays to plain python types so the
    run manifest/metrics JSON serialization cannot fail."""
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return jsonable(obj.tolist())
    return obj


def window_execution_rate(leg_log: list[dict], start: date,
                          end: date) -> dict:
    """Registered gate-8 quantity (R8 scope): leg-level execution rate over
    legs PLANNED on signal days inside [start, end].  Executed = filled /
    postponed-then-filled / at-target / rule-compliant cash slot (no_lots,
    cash_capped, feemin_skipped); NOT executed = superseded / pending."""
    planned = [r for r in leg_log if start <= r['plan_date'] <= end]
    done = sum(1 for r in planned if r['outcome'] in EXECUTED_OUTCOMES)
    return {'legs_executed': done, 'legs_planned': len(planned),
            'execution_rate': (done / len(planned)) if planned else None}


def turnover_by_year(result: R16Result, sessions: list[date],
                     equity: list[float]) -> dict[int, dict]:
    eq_by_year: dict[int, list[float]] = {}
    for d, v in zip(sessions, equity):
        eq_by_year.setdefault(d.year, []).append(v)
    out: dict[int, dict] = {}
    for y, acc in result.turnover_acc.items():
        eqs = eq_by_year.get(y, [])
        mean_eq = sum(eqs) / len(eqs) if eqs else None
        mem = result.membership_turnover.get(
            y, {'buy_notional': 0.0, 'sell_notional': 0.0})
        out[y] = {'buy_notional': acc['buy_notional'],
                  'sell_notional': acc['sell_notional'],
                  'mean_equity': mean_eq,
                  'one_side_turnover': (acc['buy_notional'] / mean_eq
                                        if mean_eq else None),
                  'membership_buy_notional': mem['buy_notional'],
                  'membership_sell_notional': mem['sell_notional'],
                  'membership_one_side_turnover':
                      (mem['buy_notional'] / mean_eq if mean_eq else None)}
    return out


def segment_metrics(result: R16Result, seg_start: date, seg_end: date,
                    b1: R16Result | None,
                    fractional: bool = False) -> dict:
    sd, sv = slice_curve(result.sessions, result.equity, seg_start, seg_end)
    out: dict = {
        'net_cagr': cagr(sv[0], sv[-1], sd[0], sd[-1]),
        'net_total_return': sv[-1] / sv[0] - 1.0,
        'max_drawdown': max_drawdown(sd, sv)['max_drawdown'],
        'mdd_window': max_drawdown(sd, sv),
        'max_single_name_weight': max(result.max_weight[
            result.sessions.index(sd[0]):result.sessions.index(sd[-1]) + 1]),
    }
    to = turnover_by_year(result, result.sessions, result.equity)
    years = list(range(sd[0].year, sd[-1].year + 1))
    out['turnover_by_year'] = {str(y): to.get(y) for y in years}
    out['max_one_side_turnover'] = max(
        (to[y]['one_side_turnover'] for y in years if to.get(y)),
        default=None)
    out['max_membership_one_side_turnover'] = max(
        (to[y]['membership_one_side_turnover'] for y in years if to.get(y)),
        default=None)
    exec_w = window_execution_rate(result.leg_log, seg_start, seg_end)
    out['execution_rate'] = exec_w['execution_rate']
    out['execution_rate_window'] = exec_w
    strat_years = year_returns(sd, sv)
    out['net_return_by_year'] = {str(y): strat_years.get(y) for y in years}
    if b1 is not None:
        bd, bv = slice_curve(b1.sessions, b1.equity, seg_start, seg_end)
        out['b1m_net_cagr'] = cagr(bv[0], bv[-1], bd[0], bd[-1])
        out['b1m_max_drawdown'] = max_drawdown(bd, bv)['max_drawdown']
        out['excess_vs_b1m'] = (out['net_cagr'] - out['b1m_net_cagr']
                                if out['net_cagr'] is not None else None)
        b1_years = year_returns(bd, bv)
        out['excess_by_year'] = {
            str(y): (strat_years[y] - b1_years[y]
                     if y in strat_years and y in b1_years else None)
            for y in years}
        out['b1m_net_return_by_year'] = {str(y): b1_years.get(y)
                                         for y in years}
    me = result.membership_events
    if me and not fractional:
        in_window = [e for e in me if seg_start <= e['signal'] <= seg_end]
        if in_window:
            n = len(in_window)
            out['membership_stats'] = {
                'n_signals': n,
                'mean_kept': sum(e['n_kept'] for e in in_window) / n,
                'mean_entrants': sum(e['n_entrants'] for e in in_window) / n,
                'mean_left': sum(e['n_left'] for e in in_window) / n,
                'mean_cash_seats': sum(e['n_cash_seats']
                                       for e in in_window) / n}
    return out


def evaluate_dev_gates(m: dict, b3_mean: float | None) -> dict:
    """The 8 frozen dev gates (prereg section 2 = frozen config gates.dev):
    1 net_cagr>0; 2 excess vs B1(m)>=+2.0pp (expected deciding gate; if it
    is the ONLY failure -> the registered double-valued conclusion);
    3 advantage years>=5/6; 4 mdd<=20% AND <=B1(m); 5 annual one-side
    turnover<=6.0; 6 any-day single-name weight<=40%; 7 net_cagr >= B3'
    mean+1.0pp; 8 plan execution rate>=95%."""
    net = m['net_cagr']
    excess = m.get('excess_vs_b1m')
    checks: dict = {}
    checks['1_net_cagr_gt_0'] = net is not None and net > 0
    checks['2_excess_vs_B1m_ge_2pp'] = (excess is not None
                                        and excess >= 0.020)
    adv = sum(1 for e in m['excess_by_year'].values()
              if e is not None and e > 0)
    n_years = len(m['excess_by_year'])
    checks['3_advantage_years_ge_5_of_6'] = adv >= 5 and n_years == 6
    checks['4_mdd_le_20pct_and_le_B1m'] = (
        m['max_drawdown'] is not None
        and abs(m['max_drawdown']) <= 0.20
        and m.get('b1m_max_drawdown') is not None
        and abs(m['max_drawdown']) <= abs(m['b1m_max_drawdown']))
    to = m['max_one_side_turnover']
    checks['5_one_side_turnover_le_6'] = to is not None and to <= 6.0
    w = m['max_single_name_weight']
    checks['6_single_name_weight_le_40pct'] = w is not None and w <= 0.40
    checks['7_vs_B3prime_plus_1pp'] = (
        net is not None and b3_mean is not None
        and net >= b3_mean + 0.010)
    rate = m['execution_rate']
    checks['8_execution_rate_ge_95pct'] = (rate is not None
                                           and rate >= 0.95)
    checks['advantage_years'] = adv
    checks['dev_excess_vs_b1m'] = excess
    failed = [k for k, v in checks.items()
              if k[0].isdigit() and not v]
    checks['failed_gates'] = failed
    checks['dev_pass'] = not failed
    # registered double-valued conclusion condition (gate 2 sole failure)
    checks['mechanism_only_gate2_fail'] = failed == ['2_excess_vs_B1m_ge_2pp']
    return checks


def evaluate_val_gates(m: dict) -> dict:
    """The 3 frozen val gates (2021-2024, one-shot): excess vs B1(m)(val)
    >= +1.0pp; advantage years >= 2/4; mdd <= 20% AND <= B1(m)(val)."""
    excess = m.get('excess_vs_b1m')
    adv = sum(1 for e in m['excess_by_year'].values()
              if e is not None and e > 0)
    n_years = len(m['excess_by_year'])
    checks = {
        '1_excess_ge_1pp': excess is not None and excess >= 0.010,
        '2_advantage_years_ge_2_of_4': adv >= 2 and n_years == 4,
        '3_mdd_le_20pct_and_le_B1m': (
            m['max_drawdown'] is not None
            and abs(m['max_drawdown']) <= 0.20
            and m.get('b1m_max_drawdown') is not None
            and abs(m['max_drawdown']) <= abs(m['b1m_max_drawdown'])),
        'advantage_years': adv}
    failed = [k for k, v in checks.items()
              if k[0].isdigit() and not v]
    checks['failed_gates'] = failed
    checks['val_pass'] = not failed
    return checks


# registered deviations, fixed BEFORE any run (disclosed in the manifest,
# the report and the results doc; consumed only after disclosure)
DEVIATIONS = [
    {'id': 1,
     'item': 'history warmup reads daily_1999_2024.parquet (same processed '
             'dataset and manifest identity as the pinned '
             'daily_2015_2024.parquet; the 2015+ slice asserted '
             'row-count-identical to the pinned file) so listing_index, '
             'amt_med20 and vol20/turn20 exist at the FIRST 2015 signals - '
             'R13 precedent, disclosed there as the same deviation.'},
    {'id': 2,
     'item': 'B1(m) fee convention: the pool-equal-weight benchmark holds '
             '~800-2000 names on 200k CNY (per-leg ~50-150 CNY); the '
             'registered 5-CNY per-order minimum would charge ~3-10%/side '
             'and destroy the benchmark that the registered gate-2 design '
             '(expected DECIDING gate, +2pp margin) assumes.  Primary B1(m) '
             'pays the SAME commission RATE and segmented stamp with NO '
             'per-order minimum; the literal per-leg-minimum B1(m) is ALSO '
             'computed and disclosed as a sensitivity.  Strategy and B3" '
             'always pay the literal schedule (their legs are 4-9k CNY).'},
    {'id': 3,
     'item': 'Q5 is ENTRY-SIDE only: filter-on arms drop Q5-flagged names '
             'from the entry candidate list; incumbents are governed purely '
             'by the buffer-band rank rule.  V2-10 usage property "zero '
             'turnover increment" implies the filter never force-exits '
             'incumbents.  Un-fillable seats (top K exhausted by kept+Q5 '
             'names on filter-on arms) stay CASH (rule-compliant slot).'},
    {'id': 4,
     'item': 'TREND basis is the PINNED 000300.SH INDEX (R8 code as '
             'published: sma_trend_state on the index close vs SMA200 of '
             'index sessions); not pool-self.  The index batch starts '
             '2015-01-05, so SMA200 is unavailable at early 2015 signals '
             'and the REGISTERED fallback (unavailable -> risk-off e_low) '
             'applies; the affected signal count is disclosed in metrics '
             '(t200_fallback_signals) and the affected months are listed in '
             'the results doc.'},
    {'id': 5,
     'item': 'R8 module identity: the R8 formal run pinned '
             'etf_rotation.py@9d283200 (pre-R9 revision, bytes not '
             'archived); the current file hashes 1c064efc, the bytes of the '
             'COMPLETED R9 formal run whose registered anchor regressions '
             'reproduce R8 published C01/C09/B1-100 curves bit-exactly, '
             'and of every completed run since (R10-R13).  Equivalence '
             'chain: pinned bytes + R9-vs-R8 bit-exact anchors + the '
             'R8-published T200 daily state statistics reproduced exactly '
             'on this round calendar (behavioral anchor, hard-asserted).'},
    {'id': 6,
     'item': 'incumbent absent from the signal pool (suspended, ST, or '
             'eligibility lost) is planned a FULL EXIT at the next open '
             '(postponed until executable); the 2K buffer only protects '
             'rankable incumbents.  A quote series that ends before the '
             'data end is force-exited at the last available close with '
             'fees (R6/R8 convention).'},
    {'id': 7,
     'item': 'B3" is computed per exposure path (T200-40 and FIX75, 20 '
             'seeds each; seeds 17-36) and gate 7 uses the config path '
             'mean - R8 precedent (mechanism-matched B1/B3), avoiding a '
             '0.75-vs-path exposure mismatch inside the gate.  Random '
             'membership is a fresh draw each signal (no buffer state '
             'exists for random ranks) and does not apply Q5.'},
    {'id': 8,
     'item': 'board-lot reality: with 200k/K=20 legs of ~4-9k CNY, names '
             'priced above ~400-900 CNY have zero affordable lots and '
             'unfillable seats stay CASH (counted, disclosed).  Membership '
             'is liquidity-rank based with NO price re-selection (prereg: '
             'no alpha selection), so such members keep their seat in cash.'},
    {'id': 9,
     'item': 'partial (rescale) sell bookkeeping follows the R8 deviation-6 '
             'attribution convention (entry budget/units reduced '
             'proportionally by units); per-position pnl stays cash-flow '
             'consistent; no cash effect.'},
    {'id': 10,
     'item': 'the H-47 evidence arm (full-rebalance top-K baselines, '
             'K in {20,30} x filter {on,off}, FIX75 path) is DESCRIPTIVE '
             'ONLY (prereg-required comparator for the buffer-band '
             'turnover effect); it consumes no gates and is not counted as '
             'a trial.'},
]
