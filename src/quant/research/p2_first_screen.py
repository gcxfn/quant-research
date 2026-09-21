"""P2 first screen pipeline (preregistered in configs/experiments/p2-first-screen.json).

Flow: standardized daily table -> historical-fee event study for three fixed
signal sets (H1-reversal / H2-pullback / H2-chase) x holds {3,5,10} -> dev and
validation window aggregates -> preregistered selection rule.

Conventions fixed by the config and by the 2026-09-17 decisions:
- signals on adjusted levels (close*adj_factor); tradability on raw prices;
- main-board only universe (no STAR/BSE/ChiNext), no ST, no suspended rows,
  full 20-session amount-median history required, CSI index codes excluded;
- historical segmented fee schedule, 50k per-event budget, limit-up/down open
  proxy blocks entry/exit;
- dev window 2015..2020-12-31 with exit-side label purge, validation 2021..2024;
- benchmarks: cash, CSI500/CSI1000 same windows, eligible-pool equal weight,
  seeded daily random picks through the identical event pipeline.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from quant.data.adjustment import load_adjustment_factors
from quant.research.screen import (
    STATUS_COMPLETED,
    FeeBand,
    ScreenConfig,
    daily_rank_picks,
    eligible_universe,
    screen_returns,
)

DEV_END = date(2020, 12, 31)
VALIDATION_START = date(2021, 1, 1)


# --------------------------------------------------------------------------- #
# loading and factor frames
# --------------------------------------------------------------------------- #
def load_daily(root: Path, config: dict, *, symbol_limit: int | None = None) -> pl.DataFrame:
    """Identity-checked load of the pinned standardized research table."""
    data_cfg = config['data']
    path = root / data_cfg['file']
    daily = pl.read_parquet(path)
    if daily.height != int(data_cfg['rows_expected']):
        raise ValueError(
            f"row count mismatch for {data_cfg['file']}: {daily.height} != "
            f"{data_cfg['rows_expected']} (dataset identity broken)")
    n_symbols = daily['symbol'].n_unique()
    if symbol_limit is None and n_symbols != int(data_cfg['symbols_expected']):
        raise ValueError(
            f"symbol count mismatch: {n_symbols} != {data_cfg['symbols_expected']}")
    if symbol_limit is not None:
        # deterministic smoke subset: every k-th main-board stock, plus the two
        # benchmark indexes so index series stay computable
        symbols = sorted(s for s in daily['symbol'].unique().to_list()
                         if not (s.startswith('sh.68') or s.startswith('sz.3')))
        stride = max(1, len(symbols) // symbol_limit)
        subset = set(symbols[::stride][:symbol_limit])
        subset.update(config['benchmarks']['broad_index'].values())
        daily = daily.filter(pl.col('symbol').is_in(sorted(subset)))
    return daily.sort('symbol', 'date')


def attach_factors(daily: pl.DataFrame, root: Path, config: dict) -> pl.DataFrame:
    """Join xiaodefa adjustment factors and add adjusted return/rolling columns."""
    factors = load_adjustment_factors(
        root, date.fromisoformat(config['start']), date.fromisoformat(config['end']))
    joined = (daily
              .join(factors, on=['symbol', 'date'], how='left')
              .with_columns((pl.col('close') * pl.col('adj_factor')).alias('adj_close'))
              .sort('symbol', 'date'))
    joined = (joined
              .with_columns(
                  (pl.col('adj_close') / pl.col('adj_close').shift(1).over('symbol') - 1.0).alias('ret_1_adj'),
                  (pl.col('adj_close') / pl.col('adj_close').shift(5).over('symbol') - 1.0).alias('ret_5_adj'),
                  (pl.col('adj_close') / pl.col('adj_close').shift(20).over('symbol') - 1.0).alias('ret_20_adj'),
                  pl.col('adj_close').rolling_max(250, min_samples=250).over('symbol').alias('max250_adj'),
              )
              .with_columns(
                  pl.col('ret_1_adj').rolling_std(20, min_samples=20).over('symbol').alias('volatility_20'),
                  pl.col('volume').rolling_mean(20, min_samples=20).over('symbol').alias('vol_mean_20'),
                  pl.col('turn').rolling_mean(20, min_samples=20).over('symbol').alias('turn_mean_20'),
                  ((pl.col('high') - pl.col('low')) / pl.col('close'))
                      .rolling_mean(20, min_samples=20).over('symbol').alias('range_mean_20'),
                  pl.col('adj_close').rolling_mean(20, min_samples=20).over('symbol').alias('sma20_adj'),
                  pl.col('adj_close').rolling_std(20, min_samples=20).over('symbol').alias('std20_adj'),
                  pl.col('adj_close').rolling_mean(5, min_samples=5).over('symbol').alias('sma5_adj'),
                  pl.col('adj_close').rolling_mean(10, min_samples=10).over('symbol').alias('sma10_adj'),
                  # 30/60 weekly lines expressed in trading sessions (5/week)
                  pl.col('adj_close').rolling_mean(150, min_samples=150).over('symbol').alias('sma150_adj'),
                  pl.col('adj_close').rolling_mean(300, min_samples=300).over('symbol').alias('sma300_adj'),
              )
              # z-score of the adjusted close against its own 20-session mean;
              # a zero std would yield infinities, so z stays null there
              .with_columns(
                  pl.when(pl.col('std20_adj') > 1e-12)
                    .then((pl.col('adj_close') - pl.col('sma20_adj')) / pl.col('std20_adj'))
                    .otherwise(None).alias('z20'),
              )
              .with_columns(pl.col('z20').shift(1).over('symbol').alias('z20_prev')))
    return joined


def build_eligible(daily: pl.DataFrame, config: dict) -> pl.DataFrame:
    """Historical-at-time tradable pool with the preregistered H3 gate."""
    uf = config['universe_filter']
    gate_cols = daily.select('symbol', 'date', 'close', 'amount', 'tradestatus', 'isST')
    return eligible_universe(
        gate_cols,
        amount_median_window=int(uf['amount_median_window']),
        amount_min=float(uf['amount_median_20d_min']),
        price_min=float(uf['price_min']),
        allow_chinext=False)


#: columns consumed by the preregistered signal definitions (rounds 1-5)
SIGNAL_COLUMNS = ('symbol', 'date', 'open', 'preclose', 'close', 'high', 'low',
                  'pctChg', 'turn', 'volume', 'ret_1_adj', 'ret_5_adj', 'ret_20_adj',
                  'adj_close', 'max250_adj', 'volatility_20', 'vol_mean_20',
                  'turn_mean_20', 'range_mean_20', 'z20', 'z20_prev',
                  'sma5_adj', 'sma10_adj', 'sma150_adj', 'sma300_adj')


def signal_candidates(daily: pl.DataFrame, eligible: pl.DataFrame,
                      signal_set: str) -> pl.DataFrame:
    """Eligible rows meeting one preregistered signal definition, with score.

    Round-2 definitions (docs/research/exp-20260917-p2-round2-screen.md) all
    hold fixed thresholds chosen from round-1 evidence; pctChg and turn are in
    percent (baostock convention), ratios are scale-free.
    """
    feat = (daily.select(*SIGNAL_COLUMNS)
            .join(eligible.select('symbol', 'date', 'amount_med20'),
                  on=['symbol', 'date'], how='inner'))
    if signal_set == 'H1-reversal':
        return (feat.filter(pl.col('ret_5_adj') < -0.10)
                .with_columns((-pl.col('ret_5_adj')).alias('score')))
    if signal_set in ('H2-pullback', 'H2-chase'):
        ranked = feat.with_columns(
            (-pl.col('ret_20_adj')).rank(method='min').over('date').alias('_rank'),
            pl.len().over('date').alias('_n')).filter(
                pl.col('_rank') <= (0.2 * pl.col('_n')).ceil())
        if signal_set == 'H2-pullback':
            ranked = ranked.filter(pl.col('ret_1_adj') < 0)
        else:
            ranked = ranked.filter(pl.col('ret_1_adj') >= 0)
        return ranked.with_columns(pl.col('ret_20_adj').alias('score')).drop('_rank', '_n')
    if signal_set == 'R2-volconfirm-reversal':
        # deep 5-day drop WITH above-average volume (round 1 dropped the
        # volume dimension entirely)
        return (feat.filter((pl.col('ret_5_adj') < -0.08)
                            & (pl.col('vol_mean_20') > 0)
                            & (pl.col('volume') > 1.5 * pl.col('vol_mean_20')))
                .with_columns((-pl.col('ret_5_adj')).alias('score')))
    if signal_set == 'R2-lowvol-dip':
        # dip among the calmer half of the day's eligible pool
        return (feat.filter((pl.col('volatility_20')
                             <= pl.col('volatility_20').median().over('date'))
                            & (pl.col('ret_5_adj') < -0.05))
                .with_columns((-pl.col('ret_5_adj')).alias('score')))
    if signal_set == 'R2-near52w-dip':
        # within 10% of the 250-session adjusted high, down on the day
        return (feat.filter((pl.col('adj_close') >= 0.9 * pl.col('max250_adj'))
                            & (pl.col('ret_1_adj') < 0))
                .with_columns((pl.col('adj_close') / pl.col('max250_adj')).alias('score')))
    if signal_set == 'R2-turnover-capitulation':
        # turnover at least double its own 20-session mean on a >5% down day
        return (feat.filter((pl.col('turn_mean_20') > 0)
                            & (pl.col('turn') >= 2.0 * pl.col('turn_mean_20'))
                            & (pl.col('pctChg') < -5.0))
                .with_columns((pl.col('turn') / pl.col('turn_mean_20')).alias('score')))
    if signal_set == 'R2-gapdown-recovery':
        # gap down >2% at the open, recovered intraday (close above open)
        return (feat.filter(((pl.col('open') / pl.col('preclose') - 1.0) < -0.02)
                            & (pl.col('close') > pl.col('open')))
                .with_columns(((pl.col('close') - pl.col('open')) / pl.col('open')).alias('score')))
    if signal_set == 'R2-squeeze-breakout':
        # compressed 20-session range (lower half of the day) plus a >3% break day
        return (feat.filter((pl.col('range_mean_20')
                             <= pl.col('range_mean_20').median().over('date'))
                            & (pl.col('pctChg') > 3.0))
                .with_columns(pl.col('pctChg').alias('score')))
    if signal_set == 'R3-mr-z-oversold':
        # adjusted close >= 1.5 std below its own 20-session mean (deviation
        # from own trend, not raw return: distinct from round-1 H1)
        return (feat.filter(pl.col('z20').is_finite() & (pl.col('z20') <= -1.5))
                .with_columns((-pl.col('z20')).alias('score')))
    if signal_set == 'R3-mr-shrink-dip':
        # 5-day drop with SHRINKING volume (<=0.7x mean): the untested
        # opposite slice of round-2's failed high-volume reversal
        return (feat.filter((pl.col('ret_5_adj') <= -0.05)
                            & (pl.col('vol_mean_20') > 0)
                            & (pl.col('volume') <= 0.7 * pl.col('vol_mean_20')))
                .with_columns((-pl.col('ret_5_adj')).alias('score')))
    if signal_set == 'R3-mr-z-shrink-combo':
        # both price deviation and volume contraction (interaction test)
        return (feat.filter(pl.col('z20').is_finite() & (pl.col('z20') <= -1.0)
                            & (pl.col('vol_mean_20') > 0)
                            & (pl.col('volume') <= 0.8 * pl.col('vol_mean_20')))
                .with_columns((-pl.col('z20')).alias('score')))
    if signal_set == 'R3-mr-z-confirmed':
        # prior session >= 1.5 std below mean AND an up close today: enter the
        # reversion only after confirmation, not catching the knife
        return (feat.filter(pl.col('z20_prev').is_finite() & (pl.col('z20_prev') <= -1.5)
                            & (pl.col('ret_1_adj') > 0))
                .with_columns(pl.col('ret_1_adj').alias('score')))
    if signal_set.startswith('R5-trend-dip'):
        # user-specified (2026-09-17): price above the 30w/60w line (long
        # uptrend) but below the 5d/10d line (short pullback); deepest
        # pullback below the short line ranked first
        long_window, short_window = signal_set.rsplit('-', 2)[-2:]
        long_col = {'30w': 'sma150_adj', '60w': 'sma300_adj'}[long_window]
        short_col = {'5d': 'sma5_adj', '10d': 'sma10_adj'}[short_window]
        return (feat.filter((pl.col('adj_close') > pl.col(long_col))
                            & (pl.col('adj_close') < pl.col(short_col)))
                .with_columns((pl.col(short_col) / pl.col('adj_close') - 1.0).alias('score')))
    raise ValueError(f'unknown signal_set {signal_set!r}')


# --------------------------------------------------------------------------- #
# benchmarks
# --------------------------------------------------------------------------- #
def _shifted_adj_open(frame: pl.DataFrame, hold: int) -> pl.DataFrame:
    """Per-symbol calendar-window open levels with exact-session checks."""
    cal = (frame.select('date').unique().sort('date')
           .with_row_index('_i'))
    indexed = (frame.select('symbol', 'date', 'open', 'adj_factor', 'tradestatus')
               .join(cal, on='date')
               .sort('symbol', '_i'))
    return indexed.with_columns(
        pl.col('adj_factor').shift(-1).over('symbol').alias('_entry_f'),
        pl.col('adj_factor').shift(-(1 + hold)).over('symbol').alias('_exit_f'),
        pl.col('open').shift(-1).over('symbol').alias('_entry_open'),
        pl.col('open').shift(-(1 + hold)).over('symbol').alias('_exit_open'),
        pl.col('tradestatus').shift(-1).over('symbol').alias('_entry_ts'),
        pl.col('tradestatus').shift(-(1 + hold)).over('symbol').alias('_exit_ts'),
        pl.col('_i').shift(-1).over('symbol').alias('_entry_i'),
        pl.col('_i').shift(-(1 + hold)).over('symbol').alias('_exit_i'),
    )


def pool_daily_returns(daily: pl.DataFrame, eligible: pl.DataFrame,
                       hold: int) -> pl.DataFrame:
    """Equal-weight eligible-pool open-to-open return per session date.

    The calendar-window shifts run on the FULL daily frame (suspension rows
    included, so one row per symbol per session and row space == calendar
    space); eligibility is joined afterwards at the signal date t.  Otherwise
    a mid-window suspension would silently remove the symbol from the pool.
    Convention mirrors the event study: entry session t+1, exit session
    t+1+hold, exact calendar neighbors, both tradable.  No fees (registered
    pool benchmark definition).
    """
    shifted = _shifted_adj_open(daily, hold)
    ret = (shifted
           .join(eligible.select('symbol', 'date'), on=['symbol', 'date'],
                 how='inner')
           .filter((pl.col('tradestatus') == 1)
                   & (pl.col('_entry_ts') == 1) & (pl.col('_exit_ts') == 1)
                   & (pl.col('_entry_i') == pl.col('_i') + 1)
                   & (pl.col('_exit_i') == pl.col('_i') + 1 + hold)
                   & pl.col('_entry_f').is_not_null() & pl.col('_exit_f').is_not_null()
                   & pl.col('_entry_open').is_not_null() & pl.col('_exit_open').is_not_null())
           .with_columns(
               ((pl.col('_exit_open') * pl.col('_exit_f'))
                / (pl.col('_entry_open') * pl.col('_entry_f')) - 1.0).alias('pool_ret')))
    return (ret.group_by('date').agg(pl.col('pool_ret').mean().alias('pool_ret'),
                                     pl.len().alias('pool_n'))
            .sort('date'))


def index_daily_returns(daily: pl.DataFrame, symbol: str, hold: int) -> pl.DataFrame:
    """Index open-to-open return per session date, same window convention."""
    idx = daily.filter(pl.col('symbol') == symbol)
    if idx.height == 0:
        raise ValueError(f'index {symbol} missing from daily table')
    shifted = _shifted_adj_open(idx, hold)
    ret = (shifted
           .filter((pl.col('_entry_i') == pl.col('_i') + 1)
                   & (pl.col('_exit_i') == pl.col('_i') + 1 + hold)
                   & pl.col('_entry_open').is_not_null()
                   & pl.col('_exit_open').is_not_null())
           .with_columns(
               (pl.col('_exit_open') / pl.col('_entry_open') - 1.0).alias('idx_ret')))
    return ret.select(pl.col('date').alias('signal_date'), 'idx_ret').sort('signal_date')


def random_picks(eligible: pl.DataFrame, top_n: int, seed: int) -> pl.DataFrame:
    """Seeded uniform picks of ``top_n`` eligible symbols on every session."""
    rng = np.random.default_rng(seed)
    by_date = (eligible.select('symbol', 'date')
               .group_by('date').agg(pl.col('symbol').sort().alias('symbols'))
               .sort('date'))
    rows: list[dict] = []
    for record in by_date.iter_rows(named=True):
        n = len(record['symbols'])
        for position in rng.choice(n, size=min(top_n, n), replace=False):
            rows.append({'symbol': record['symbols'][int(position)],
                         'signal_date': record['date']})
    return pl.DataFrame(rows, schema={'symbol': pl.String, 'signal_date': pl.Date},
                        orient='row')


# --------------------------------------------------------------------------- #
# event study per config
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ConfigResult:
    signal_set: str
    hold: int
    events: pl.DataFrame
    n_purged_boundary: int


def run_signal_config(daily: pl.DataFrame, eligible: pl.DataFrame,
                      calendar: pl.Series, signal_set: str, hold: int,
                      config: dict) -> ConfigResult:
    ex = config['execution']
    bands = tuple(
        FeeBand(date.fromisoformat(b['from']), float(b['commission_pct']),
                float(b['commission_min']), float(b['stamp_sell_pct']))
        for b in config['fees']['schedule'])
    cfg = ScreenConfig(holding_days=int(hold), top_n=int(ex['top_n_per_day']),
                       capital=float(ex['capital']),
                       position_budget=float(ex['position_budget']),
                       fee_schedule=bands, block_limits=bool(ex['block_limits']),
                       limit_pct=float(ex['limit_pct']))
    prices = daily.select('symbol', 'date', 'open', 'adj_factor',
                          'tradestatus', 'isST', 'preclose')
    candidates = signal_candidates(daily, eligible, signal_set)
    picks = daily_rank_picks(candidates, pl.col('score'), n_per_day=int(ex['top_n_per_day']))
    events = screen_returns(picks, prices, cfg, calendar=calendar)
    dev = events.filter(pl.col('signal_date') <= DEV_END)
    n_purged = dev.filter(pl.col('exit_date') > DEV_END).height
    return ConfigResult(signal_set, int(hold), events, n_purged)


def run_random_config(daily: pl.DataFrame, eligible: pl.DataFrame,
                      calendar: pl.Series, hold: int, config: dict) -> pl.DataFrame:
    ex = config['execution']
    bands = tuple(
        FeeBand(date.fromisoformat(b['from']), float(b['commission_pct']),
                float(b['commission_min']), float(b['stamp_sell_pct']))
        for b in config['fees']['schedule'])
    cfg = ScreenConfig(holding_days=int(hold), top_n=int(ex['top_n_per_day']),
                       capital=float(ex['capital']),
                       position_budget=float(ex['position_budget']),
                       fee_schedule=bands, block_limits=bool(ex['block_limits']),
                       limit_pct=float(ex['limit_pct']))
    prices = daily.select('symbol', 'date', 'open', 'adj_factor',
                          'tradestatus', 'isST', 'preclose')
    return screen_returns(random_picks(eligible, int(ex['top_n_per_day']),
                                       int(config['seed'])), prices, cfg, calendar=calendar)


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #
def _window_frame(events: pl.DataFrame) -> pl.DataFrame:
    """Assign dev (purged) / validation windows; purge drops dev rows whose
    exit crosses 2020-12-31 so no return stream spans both windows."""
    return (events
            .with_columns(pl.col('signal_date').dt.year().alias('year'))
            .with_columns(
                pl.when(pl.col('signal_date') <= DEV_END).then(pl.lit('dev'))
                  .when(pl.col('signal_date') >= VALIDATION_START).then(pl.lit('validation'))
                  .otherwise(None).alias('window'))
            .filter(pl.col('window').is_not_null()))


def window_summary(events_w: pl.DataFrame, window: str, pool: pl.DataFrame,
                   hold: int) -> dict:
    """Headline stats and per-year net edge vs the pool benchmark."""
    part = events_w.filter(pl.col('window') == window)
    completed = part.filter(pl.col('status') == STATUS_COMPLETED)
    n_events = part.height
    n_done = completed.height
    summary: dict = {
        'n_events': n_events,
        'n_completed': n_done,
        'completion_rate': (n_done / n_events) if n_events else None,
        'status_counts': (part.group_by('status').len().sort('len', descending=True)
                          .to_dicts() if n_events else []),
    }
    if not n_done:
        summary.update({'mean_net_pct': None, 'median_net_pct': None,
                        'mean_gross_pct': None, 'total_net_profit_yuan': None,
                        'per_year': [], 'pool_mean_pct': None})
        return summary
    summary.update({
        'mean_net_pct': completed['net_return_pct'].mean(),
        'median_net_pct': completed['net_return_pct'].median(),
        'mean_gross_pct': completed['gross_return'].mean() * 100.0,
        'total_net_profit_yuan': float(
            ((completed['net_return_pct'] / 100.0)
             * (completed['entry_notional'] + completed['buy_fee'])).sum()),
    })
    pool_part = _pool_for_window(pool, window)
    summary['pool_mean_pct'] = (pool_part['pool_ret'].mean() * 100.0
                                if pool_part.height else None)
    # every calendar year of the window is reported; a year without events
    # counts as missing (and therefore as a non-positive edge year)
    year_range = range(2015, 2021) if window == 'dev' else range(2021, 2025)
    per_year = []
    for year in year_range:
        done_y = completed.filter(pl.col('year') == year)
        entry = {'year': int(year), 'n_completed': done_y.height}
        if done_y.height:
            entry['mean_net_pct'] = done_y['net_return_pct'].mean()
        pool_y = _pool_for_window(pool, window, year)
        if pool_y.height:
            entry['pool_mean_pct'] = pool_y['pool_ret'].mean() * 100.0
        if 'mean_net_pct' in entry and entry.get('pool_mean_pct') is not None:
            entry['net_edge_pct'] = entry['mean_net_pct'] - entry['pool_mean_pct']
        per_year.append(entry)
    summary['per_year'] = per_year
    return summary


def _pool_for_window(pool: pl.DataFrame, window: str, year: int | None = None) -> pl.DataFrame:
    lo = (date(2015, 1, 5) if window == 'dev' else VALIDATION_START)
    hi = (DEV_END if window == 'dev' else date(2024, 12, 31))
    part = pool.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
    if year is not None:
        part = part.filter(pl.col('date').dt.year() == year)
    return part


def concentration(events_w: pl.DataFrame, window: str) -> dict:
    """Top-decile symbol share of total net profit (kill criterion 3)."""
    completed = (events_w.filter((pl.col('window') == window)
                                 & (pl.col('status') == STATUS_COMPLETED)))
    if not completed.height:
        return {'n_symbols': 0, 'top_decile_share': None}
    profit = (completed
              .with_columns((pl.col('net_return_pct') / 100.0
                             * (pl.col('entry_notional') + pl.col('buy_fee'))
                             ).alias('_profit'))
              .group_by('symbol').agg(pl.col('_profit').sum().alias('profit')))
    total = float(profit['profit'].sum())
    n_symbols = profit.height
    n_top = max(1, math.ceil(0.1 * n_symbols))
    top = float(profit.sort('profit', descending=True).head(n_top)['profit'].sum())
    return {'n_symbols': n_symbols, 'total_profit_yuan': total,
            'top_decile_share': (top / total if total > 0 else None)}


def h3_gate_check(events_w: pl.DataFrame, window: str) -> dict:
    """Bottom amount-tercile share of net profit for H1 events (H3 falsifier)."""
    completed = (events_w.filter((pl.col('window') == window)
                                 & (pl.col('status') == STATUS_COMPLETED)))
    if not completed.height:
        return {'bottom_tercile_share': None}
    ranked = completed.with_columns(
        pl.col('amount_med20').rank(method='ordinal').alias('_r'),
        pl.len().alias('_n'))
    bottom = ranked.filter(pl.col('_r') <= (pl.col('_n') / 3.0).ceil())
    total = float(((completed['net_return_pct'] / 100.0)
                   * (completed['entry_notional'] + completed['buy_fee'])).sum())
    bottom_total = float(((bottom['net_return_pct'] / 100.0)
                          * (bottom['entry_notional'] + bottom['buy_fee'])).sum())
    return {'n_completed': completed.height,
            'total_profit_yuan': total,
            'bottom_tercile_share': (bottom_total / total if total > 0 else None)}


def selection_verdicts(dev: dict, conc: dict) -> dict:
    """Preregistered dev-window pass/fail booleans."""
    years = [y for y in dev['per_year'] if y.get('net_edge_pct') is not None]
    positive_years = sum(1 for y in years if y['net_edge_pct'] > 0)
    n_years = len([y for y in dev['per_year']])  # all dev years count
    checks = {
        'beats_pool_dev': (dev['mean_net_pct'] is not None and dev['pool_mean_pct'] is not None
                           and dev['mean_net_pct'] > dev['pool_mean_pct']),
        'positive_edge_years': f'{positive_years}/{n_years}',
        'positive_edge_years_ok': n_years > 0 and positive_years >= 4,
        'top_decile_share': conc['top_decile_share'],
        'concentration_ok': (conc['top_decile_share'] is not None
                             and conc['top_decile_share'] <= 0.40),
        'completion_ok': dev['completion_rate'] is not None and dev['completion_rate'] >= 0.60,
    }
    checks['dev_pass'] = (checks['beats_pool_dev'] and checks['positive_edge_years_ok']
                          and checks['concentration_ok'] and checks['completion_ok'])
    return checks


def validation_verdicts(val: dict) -> dict:
    years = [y for y in val['per_year'] if y.get('net_edge_pct') is not None]
    positive_years = sum(1 for y in years if y['net_edge_pct'] > 0)
    n_years = len(val['per_year'])
    checks = {
        'beats_pool_validation': (val['mean_net_pct'] is not None
                                  and val['pool_mean_pct'] is not None
                                  and val['mean_net_pct'] > val['pool_mean_pct']),
        'positive_edge_years': f'{positive_years}/{n_years}',
        'positive_edge_years_ok': n_years > 0 and positive_years >= 2,
    }
    checks['validation_pass'] = checks['beats_pool_validation'] and checks['positive_edge_years_ok']
    return checks


def benchmark_series_mean(series: pl.DataFrame, ret_col: str, window: str) -> float | None:
    lo = (date(2015, 1, 5) if window == 'dev' else VALIDATION_START)
    hi = (DEV_END if window == 'dev' else date(2024, 12, 31))
    part = series.filter((pl.col('signal_date') >= lo) & (pl.col('signal_date') <= hi))
    return float(part[ret_col].mean() * 100.0) if part.height else None
