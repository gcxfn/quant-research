"""Adjustment factor integration for the standardized daily table.

Contract: adjusted_close = close * adj_factor / adj_factor_latest_within_window
(back-adjusted to the last trading day of the loaded window), so the most
recent prices equal unadjusted close and multi-day returns are continuous
across corporate actions. Trading prices for orders/fills stay unadjusted;
adjusted series is for signals/labels only (root AGENTS.md §4).

Factor source: data/raw/xiaodefa/adj_factor/20260913-bulk1/chunk_YYYYMMDD.csv
(ts_code, trade_date, adj_factor), full-market 2014-01-02..2026-09-11, stocks
only. Cross-checked against baostock/adjust_factor on sh.600000 2022-07-21:
jump ratio 1.0555532 vs 1.0555555 (2e-6 difference, rounding-level).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

ADJ_DIR = Path('data/raw/xiaodefa/adj_factor/20260913-bulk1')


def _to_symbol(ts_code: str) -> str:
    """tushare-style ts_code (600000.SH) -> repo symbol (sh.600000)."""
    code, suffix = ts_code.split('.')
    market = 'sh' if suffix == 'SH' else 'sz'
    return f'{market}.{code}'


def _to_ts_code(symbol: str) -> str:
    """repo symbol (sh.600000) -> tushare-style ts_code (600000.SH)."""
    market, code = symbol.split('.')
    suffix = 'SH' if market == 'sh' else 'SZ'
    return f'{code}.{suffix}'


def load_adjustment_factors(root: Path, start: date, end: date,
                            symbols: set[str] | None = None) -> pl.DataFrame:
    """Long table (symbol, date, adj_factor) for trading days in [start, end].

    Reads only the daily chunks intersecting the window (bounded IO).
    """
    frames = []
    for chunk in sorted((root / ADJ_DIR).glob('chunk_*.csv')):
        stem_date = chunk.stem[len('chunk_'):]
        day = date.fromisoformat(f'{stem_date[:4]}-{stem_date[4:6]}-{stem_date[6:8]}')
        if day < start or day > min(end, date(2024, 12, 31)):
            continue
        frame = pl.read_csv(chunk)
        frame = frame.with_columns(
            pl.col('ts_code').map_elements(_to_symbol, return_dtype=pl.String).alias('symbol'),
            pl.col('trade_date').cast(pl.String).str.to_date('%Y%m%d').alias('date'),
        ).select('symbol', 'date', 'adj_factor')
        if symbols is not None:
            frame = frame.filter(pl.col('symbol').is_in(sorted(symbols)))
        frames.append(frame)
    factors = pl.concat(frames)
    return factors.sort('symbol', 'date')


def attach_adjusted_close(daily: pl.DataFrame, factors: pl.DataFrame,
                          *, suspended_col: str = 'tradestatus') -> pl.DataFrame:
    """Return daily + adj_factor + adjusted_close columns.

    adjusted_close = close * adj_factor / last_adj_factor(symbol)
    The most recent date in the frame therefore has adjusted_close == close.

    Rows with tradestatus==0 (suspended) may lack a factor: their close is a
    stale carry-forward and never tradable, so adj_factor/adjusted_close stay
    null there and downstream trading logic must exclude suspended rows.
    A trading row (tradestatus!=0) with a missing factor still raises.
    """
    joined = daily.join(factors, on=['symbol', 'date'], how='left')
    if suspended_col in joined.columns:
        missing = joined.filter(
            pl.col('adj_factor').is_null() & pl.col('close').is_not_null()
            & (pl.col(suspended_col) != 0))
    else:
        missing = joined.filter(pl.col('adj_factor').is_null() & pl.col('close').is_not_null())
    if missing.height:
        raise ValueError(f'{missing.height} trading rows lack adjustment factor; '
                         f'example: {missing.select("symbol", "date").head(3).to_dicts()}')
    joined = joined.join(latest_factor(joined), on='symbol', how='left')
    return joined.with_columns(
        (pl.col('close') * pl.col('adj_factor') / pl.col('_last_factor')).alias('adjusted_close')
    )


def latest_factor(joined: pl.DataFrame) -> pl.DataFrame:
    return (joined.sort('date').group_by('symbol', maintain_order=True).last()
            .select('symbol', pl.col('adj_factor').alias('_last_factor')))
