"""Adjustment series contracts: correctness of corporate-action adjustment and code conversion."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from quant.data.adjustment import (  # noqa: E402
    _to_symbol,
    _to_ts_code,
    attach_adjusted_close,
    load_adjustment_factors,
)

ROOT = Path(__file__).resolve().parents[2]


def test_code_conversion_roundtrip():
    assert _to_ts_code('sh.600000') == '600000.SH'
    assert _to_ts_code('sz.000001') == '000001.SZ'
    assert _to_symbol('600000.SH') == 'sh.600000'
    assert _to_symbol('000001.SZ') == 'sz.000001'
    # round trip
    assert _to_symbol(_to_ts_code('sh.600027')) == 'sh.600027'


def test_adjusted_close_contract_synthetic():
    # one symbol, a corporate action on day 2: factor jumps 1.0 -> 0.9.
    # Raw close drops 10% purely from ex-dividend; adjusted series must not.
    daily = pl.DataFrame({
        'symbol': ['sh.A'] * 3,
        'date': [date(2022, 1, 4), date(2022, 1, 5), date(2022, 1, 6)],
        'close': [10.0, 9.0, 9.1],
    })
    factors = pl.DataFrame({
        'symbol': ['sh.A'] * 3,
        'date': [date(2022, 1, 4), date(2022, 1, 5), date(2022, 1, 6)],
        'adj_factor': [1.0, 0.9, 0.9],
    })
    out = attach_adjusted_close(daily, factors)
    # back-anchored: adjusted = close * factor / last_factor
    # day1: 10*1.0/0.9 = 11.111; day2: 9*0.9/0.9 = 9.0 -> continuity holds
    assert abs(out['adjusted_close'][0] - 10.0 / 0.9) < 1e-9
    assert abs(out['adjusted_close'][1] - 9.0) < 1e-9
    r1 = out['adjusted_close'][1] / out['adjusted_close'][0] - 1
    r2 = out['adjusted_close'][2] / out['adjusted_close'][1] - 1
    assert abs(r1 - (9.0 / (10.0 / 0.9) - 1)) < 1e-9  # = +0.9%*0.9... exactly 0.9/1.0*9/10-1
    # the ex-date return must NOT show the fake -10% raw drop
    assert abs(r1 - (0.9 * 9.0 / 10.0 - 1)) < 1e-9
    assert r2 == pytest.approx(9.1 / 9.0 - 1)
    # last day equals unadjusted close (back-anchored)
    assert abs(out['adjusted_close'][-1] - out['close'][-1]) < 1e-12


def test_missing_factor_raises_for_trading_rows():
    daily = pl.DataFrame({
        'symbol': ['sh.X', 'sh.X'],
        'date': [date(2022, 1, 4), date(2022, 1, 5)],
        'close': [10.0, 10.0],
        'tradestatus': [1.0, 1.0],
    })
    factors = pl.DataFrame(schema={'symbol': pl.String, 'date': pl.Date, 'adj_factor': pl.Float64})
    with pytest.raises(ValueError, match='lack adjustment factor'):
        attach_adjusted_close(daily, factors)


def test_suspended_rows_may_lack_factor():
    """Suspended rows (tradestatus=0) legitimately miss factors: factor and
    adjusted_close stay null; trading rows must still be adjusted."""
    daily = pl.DataFrame({
        'symbol': ['sh.X', 'sh.X', 'sh.X'],
        'date': [date(2022, 1, 4), date(2022, 1, 5), date(2022, 1, 6)],
        'close': [10.0, 10.0, 10.0],
        'tradestatus': [1.0, 0.0, 1.0],
    })
    factors = pl.DataFrame({
        'symbol': ['sh.X', 'sh.X'],
        'date': [date(2022, 1, 4), date(2022, 1, 6)],
        'adj_factor': [2.0, 2.0],
    })
    out = attach_adjusted_close(daily, factors)
    suspended = out.filter(pl.col('date') == date(2022, 1, 5))
    assert suspended['adj_factor'].to_list() == [None]
    assert suspended['adjusted_close'].to_list() == [None]
    assert abs(out['adjusted_close'][0] - 10.0) < 1e-9
    assert abs(out['adjusted_close'][2] - 10.0) < 1e-9


def test_real_window_continuity_600000():
    """Ex-date 2022-07-21: unadjusted return shows a fake -5.9% drop;
    adjusted return must match the source's own pctChg (-0.7%)."""
    if not (ROOT / 'data/raw/xiaodefa/adj_factor').is_dir():
        pytest.skip('raw data not available')
    factors = load_adjustment_factors(ROOT, date(2022, 1, 1), date(2024, 12, 31),
                                      {'sh.600000'})
    # window caps at the freeze line; 2022-2024 trading days for one symbol
    assert factors.height == 242 + 242 + 242
    daily = pl.read_parquet(ROOT / 'data/processed/baostock-daily-20260917/daily_2015_2024.parquet',
                            )
    window = daily.filter((pl.col('date') >= pl.date(2022, 1, 1)) &
                          (pl.col('date') <= pl.date(2024, 12, 31)) &
                          (pl.col('symbol') == 'sh.600000'))
    out = attach_adjusted_close(window, factors)
    # anchor is the last day of the 2022-2024 window: adjusted == close there
    x_sorted = out.sort('date')
    last = x_sorted.row(x_sorted.height - 1, named=True)
    assert abs(last['adjusted_close'] - last['close']) < 1e-9
    x = out.sort('date')
    i = x['date'].to_list().index(date(2022, 7, 21))
    unadj = x['close'][i] / x['close'][i - 1] - 1
    adj = x['adjusted_close'][i] / x['adjusted_close'][i - 1] - 1
    source = x['pctChg'][i] / 100
    assert abs(unadj - (-0.0591)) < 1e-3  # fake dividend drop present in raw close
    assert abs(adj - source) < 5e-4  # adjusted return agrees with source pctChg
    assert abs(unadj - source) > 0.05  # and they are genuinely different
