"""P2 round 4: cross-sectional factor survey (preregistered in
configs/experiments/p2-round4-factor-survey.json).

For each preregistered factor, on the eligible pool and a fixed 5-session
forward return (adjusted open t+1 -> t+6, exact sessions):

- per-day Spearman IC (+ yearly sign consistency),
- per-day quintile mean forward returns (Q5-Q1 spread, gross),
- the account-relevant tail exam: top-3/day picks signed by the dev IC sign
  through the identical event pipeline used in rounds 1-3 (historical fee
  schedule, limit-open blocks, 50k per-event budget),

then the two preregistered z-combination rules.  Screening happens on the dev
window only; the validation window is touched once, after screening and
combination weights are frozen.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from quant.data.adjustment import load_adjustment_factors
from quant.research.p2_first_screen import (
    DEV_END,
    VALIDATION_START,
    _shifted_adj_open,
    attach_factors,
    build_eligible,
    load_daily,
)
from quant.research.screen import (
    FeeBand,
    ScreenConfig,
    daily_rank_picks,
    screen_returns,
)

MIN_IC_STOCKS = 50


# --------------------------------------------------------------------------- #
# extra data sources (single-source tushare-compatible proxies; disclosed)
# --------------------------------------------------------------------------- #
def _ts_to_symbol(ts_code: pl.Expr) -> pl.Expr:
    parts = ts_code.str.split('.')
    suffix = parts.list.last()
    market = pl.when(suffix == 'SH').then(pl.lit('sh')).otherwise(pl.lit('sz'))
    return market + pl.lit('.') + parts.list.first()


def _read_chunks(paths: list[Path], start: date, end: date,
                 columns: list[str]) -> pl.DataFrame:
    """Read date-named chunks in [start, end] into a canonical column order.

    Some upstream batches mix two header orders (trade_date first vs ts_code
    first); selecting by name normalizes both before the vstack.
    """
    frames = []
    for base in paths:
        for chunk in sorted(base.glob('chunk_*.csv')):
            day = date.fromisoformat('{0}-{1}-{2}'.format(
                chunk.stem[6:10], chunk.stem[10:12], chunk.stem[12:14]))
            if day < start or day > end:
                continue
            frame = pl.read_csv(chunk)
            missing = [c for c in ('trade_date', 'ts_code', *columns) if c not in frame.columns]
            if missing:
                raise ValueError(f'{chunk}: missing expected columns {missing}')
            frames.append(frame.select('trade_date', 'ts_code', *columns))
    raw = pl.concat(frames)
    return (raw
            .with_columns(_ts_to_symbol(pl.col('ts_code')).alias('symbol'),
                          pl.col('trade_date').cast(pl.String)
                            .str.to_date('%Y%m%d').alias('date'))
            .select('symbol', 'date', *columns))


def load_moneyflow(root: Path, start: date, end: date) -> pl.DataFrame:
    return _read_chunks(
        [root / 'data/raw/xiaodefa/moneyflow/20260913-bulk1'], start, end,
        ['buy_lg_amount', 'buy_elg_amount', 'sell_lg_amount',
         'sell_elg_amount', 'net_mf_amount'])


def load_daily_basic(root: Path, start: date, end: date) -> pl.DataFrame:
    return _read_chunks(
        [root / 'data/raw/tushare/daily_basic/20260913-r2',
         root / 'data/raw/tushare/daily_basic/20260909-r1'], start, end,
        ['volume_ratio', 'circ_mv', 'pe_ttm', 'pb'])


def load_cyq(root: Path, start: date, end: date) -> pl.DataFrame:
    return _read_chunks(
        [root / 'data/raw/xiaodefa/cyq_perf/20260913-bulk1'], start, end,
        ['winner_rate'])


def load_margin(root: Path, start: date, end: date) -> pl.DataFrame:
    return _read_chunks(
        [root / 'data/raw/tushare/margin_detail/20260909-r1'], start, end,
        ['rzmre'])


# --------------------------------------------------------------------------- #
# factor panel
# --------------------------------------------------------------------------- #
def forward_returns(daily: pl.DataFrame, hold: int) -> pl.DataFrame:
    """(symbol, date, fwd_ret) with the event-study convention: adjusted open
    of session t+1 -> t+1+hold, exact calendar neighbors, tradable both ends."""
    shifted = _shifted_adj_open(daily, hold)
    return (shifted
            .filter((pl.col('tradestatus') == 1)
                    & (pl.col('_entry_ts') == 1) & (pl.col('_exit_ts') == 1)
                    & (pl.col('_entry_i') == pl.col('_i') + 1)
                    & (pl.col('_exit_i') == pl.col('_i') + 1 + hold)
                    & pl.col('_entry_f').is_not_null() & pl.col('_exit_f').is_not_null()
                    & pl.col('_entry_open').is_not_null() & pl.col('_exit_open').is_not_null())
            .with_columns(
                ((pl.col('_exit_open') * pl.col('_exit_f'))
                 / (pl.col('_entry_open') * pl.col('_entry_f')) - 1.0).alias('fwd_ret'))
            .select('symbol', 'date', 'fwd_ret'))


def build_factor_panel(daily: pl.DataFrame, eligible: pl.DataFrame,
                       root: Path, start: date, end: date,
                       extras: dict[str, pl.DataFrame]) -> pl.DataFrame:
    """Eligible rows x [fwd_ret + all preregistered factor columns]."""
    mf = (extras['moneyflow'].with_columns(
        ((pl.col('buy_lg_amount') + pl.col('buy_elg_amount')
          - pl.col('sell_lg_amount') - pl.col('sell_elg_amount')) * 1e4).alias('_lg_net'),
        (pl.col('net_mf_amount') * 1e4).alias('_net_mf')))
    db = extras['daily_basic']
    cyq = extras['cyq_perf']
    margin = extras['margin_detail']

    base = (daily.select(
        'symbol', 'date', 'amount', 'turn', 'ret_5_adj', 'ret_20_adj',
        'volatility_20', 'volume', 'vol_mean_20', 'z20', 'range_mean_20',
        'adj_close', 'max250_adj', 'open', 'preclose', 'close', 'high', 'low')
        .with_columns(
            (pl.col('volume') / pl.col('vol_mean_20')).alias('vol_ratio_20'),
            (pl.col('close') / (pl.col('amount') / pl.col('volume')) - 1.0).alias('close_vs_vwap'),
            ((pl.col('close') - pl.col('low'))
             / (pl.col('high') - pl.col('low'))).alias('intraday_pos'),
            (pl.col('open') / pl.col('preclose') - 1.0).alias('gap_1'),
            (pl.col('adj_close') / pl.col('max250_adj')).alias('near52w')))

    panel = (base
             .join(mf.select('symbol', 'date', '_lg_net', '_net_mf'),
                   on=['symbol', 'date'], how='left')
             .with_columns(
                 (pl.col('_lg_net') / pl.col('amount')).alias('mf_lg_net_ratio'),
                 (pl.col('_net_mf') / pl.col('amount')).alias('mf_net_ratio'))
             .sort('symbol', 'date')
             .with_columns(
                 pl.col('mf_lg_net_ratio').rolling_mean(5, min_samples=5)
                   .over('symbol').alias('mf_lg_net_ratio_5'))
             .join(db.rename({'volume_ratio': 'vr_ts', 'circ_mv': 'circ_mv',
                              'pe_ttm': 'pe_ttm', 'pb': 'pb'})
                     .select('symbol', 'date', 'vr_ts', 'circ_mv', 'pe_ttm', 'pb'),
                   on=['symbol', 'date'], how='left')
             .join(cyq.select('symbol', 'date', 'winner_rate'),
                   on=['symbol', 'date'], how='left')
             .join(margin.select('symbol', 'date', 'rzmre'),
                   on=['symbol', 'date'], how='left')
             .with_columns((pl.col('rzmre') / pl.col('amount')).alias('margin_buy_ratio')))

    keep = ('symbol', 'date', 'fwd_ret', 'ret_5', 'ret_20', 'volatility_20',
            'vol_ratio_20', 'turn_level', 'z20', 'range_mean_20', 'near52w',
            'close_vs_vwap', 'intraday_pos', 'gap_1', 'mf_lg_net_ratio',
            'mf_net_ratio', 'mf_lg_net_ratio_5', 'vr_ts', 'circ_mv', 'pe_ttm',
            'pb', 'winner_rate', 'margin_buy_ratio')
    renamed = {'ret_5_adj': 'ret_5', 'ret_20_adj': 'ret_20', 'turn': 'turn_level'}
    return (panel.join(eligible.select('symbol', 'date'), on=['symbol', 'date'],
                       how='inner')
            .join(forward_returns(daily, 5), on=['symbol', 'date'], how='left')
            .rename(renamed)
            .select(keep))


FACTOR_COLUMNS = ('ret_5', 'ret_20', 'volatility_20', 'vol_ratio_20', 'turn_level',
                  'z20', 'range_mean_20', 'near52w', 'close_vs_vwap', 'intraday_pos',
                  'gap_1', 'mf_lg_net_ratio', 'mf_net_ratio', 'mf_lg_net_ratio_5',
                  'vr_ts', 'circ_mv', 'pe_ttm', 'pb', 'winner_rate', 'margin_buy_ratio')


# --------------------------------------------------------------------------- #
# survey statistics
# --------------------------------------------------------------------------- #
def ic_series(panel: pl.DataFrame, factor: str) -> pl.DataFrame:
    """Per-day Spearman IC of a factor vs the forward return."""
    return (panel
            .filter(pl.col(factor).is_not_null() & pl.col(factor).is_finite()
                    & pl.col('fwd_ret').is_not_null())
            .group_by('date').agg(
                pl.corr(pl.col(factor), pl.col('fwd_ret'), method='spearman').alias('ic'),
                pl.len().alias('n'))
            .filter(pl.col('n') >= MIN_IC_STOCKS)
            .sort('date'))


def window_ic_stats(ic: pl.DataFrame, lo: date, hi: date) -> dict:
    part = ic.filter((pl.col('date') >= lo) & (pl.col('date') <= hi))
    if not part.height:
        return {'days': 0, 'mean_ic': None, 'ic_ir': None}
    mean = float(part['ic'].mean())
    std = float(part['ic'].std())
    by_year = (part.with_columns(pl.col('date').dt.year().alias('y'))
               .group_by('y').agg(pl.col('ic').mean().alias('yic')).sort('y'))
    return {'days': part.height, 'mean_ic': mean,
            'ic_ir': (mean / std if std and std > 0 else None),
            'yearly': [(int(r['y']), float(r['yic'])) for r in by_year.iter_rows(named=True)]}


def sign_consistency(stats: dict, required_years: int) -> tuple[bool, str]:
    """Same-sign yearly mean IC in >= required_years of the covered years."""
    yearly = stats.get('yearly') or []
    if not yearly or stats.get('mean_ic') is None:
        return False, 'no covered years'
    sign = 1 if stats['mean_ic'] >= 0 else -1
    ok_years = [y for y, yic in yearly if (yic >= 0 if sign > 0 else yic <= 0)]
    detail = f'{len(ok_years)}/{len(yearly)}'
    return len(ok_years) >= required_years and len(yearly) >= required_years, detail


def quintile_spread(panel: pl.DataFrame, factor: str) -> pl.DataFrame:
    """Per-day quintile mean forward returns and the Q5-Q1 spread."""
    ranked = (panel
              .filter(pl.col(factor).is_not_null() & pl.col(factor).is_finite()
                      & pl.col('fwd_ret').is_not_null())
              .with_columns(
                  ((pl.col(factor).rank(method='min').over('date') - 1)
                   / pl.len().over('date') * 5 + 1).floor().clip(1, 5)
                  .cast(pl.Int32).alias('q')))
    by_day = (ranked.group_by('date', 'q').agg(pl.col('fwd_ret').mean().alias('m')))
    wide = by_day.pivot(on='q', index='date', values='m').sort('date')
    return wide.with_columns((pl.col('5') - pl.col('1')).alias('spread_q5_q1'))


def build_screen_config(config: dict, hold: int) -> ScreenConfig:
    ex = config['execution']
    bands = tuple(
        FeeBand(date.fromisoformat(b['from']), float(b['commission_pct']),
                float(b['commission_min']), float(b['stamp_sell_pct']))
        for b in config['fees']['schedule'])
    return ScreenConfig(holding_days=hold, top_n=int(ex['top_n_per_day']),
                        capital=float(ex['capital']),
                        position_budget=float(ex['position_budget']),
                        fee_schedule=bands, block_limits=bool(ex['block_limits']),
                        limit_pct=float(ex['limit_pct']))


def tail_events(panel: pl.DataFrame, factor: str, direction: float,
                daily: pl.DataFrame, calendar: pl.Series,
                cfg: ScreenConfig) -> pl.DataFrame:
    """Top-3/day event study ranked by factor * direction."""
    feats = (panel
             .filter(pl.col(factor).is_not_null() & pl.col(factor).is_finite())
             .select('symbol', 'date',
                     (pl.col(factor) * direction).alias('score')))
    picks = daily_rank_picks(feats, pl.col('score'), n_per_day=cfg.top_n)
    prices = daily.select('symbol', 'date', 'open', 'adj_factor',
                          'tradestatus', 'isST', 'preclose')
    return screen_returns(picks, prices, cfg, calendar=calendar)
