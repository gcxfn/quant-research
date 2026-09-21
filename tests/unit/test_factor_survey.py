"""Factor survey primitive tests on synthetic frames (contract data only)."""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.research.factor_survey import (  # noqa: E402
    ic_series,
    quintile_spread,
    sign_consistency,
    window_ic_stats,
)

D = date


def one_day() -> date:
    return D(2022, 1, 4)


def panel(factor: list[float], fwd: list[float], day: date) -> pl.DataFrame:
    n = len(factor)
    return pl.DataFrame({
        'symbol': [f'sh.6000{i:04d}' for i in range(n)],
        'date': [day] * n,
        'f': factor,
        'fwd_ret': fwd,
    }, schema_overrides={'date': pl.Date})


def test_ic_is_plus_one_for_monotone_and_minus_for_inverted():
    d = one_day()
    n = 60
    fwd = [0.001 * i for i in range(n)]
    up = ic_series(panel([float(i) for i in range(n)], fwd, d), 'f')
    assert up['ic'][0] == pytest.approx(1.0)
    down = ic_series(panel([float(i) for i in range(n)], list(reversed(fwd)), d), 'f')
    assert down['ic'][0] == pytest.approx(-1.0)


def test_ic_day_with_fewer_than_min_stocks_is_dropped():
    d1 = D(2022, 1, 4)
    d2 = D(2022, 1, 5)
    big = panel([float(i) for i in range(60)], [0.01] * 60, d1)
    small = pl.DataFrame({
        'symbol': ['sh.600000', 'sh.600001'], 'date': [d2, d2],
        'f': [1.0, 2.0], 'fwd_ret': [0.01, 0.02]},
        schema_overrides={'date': pl.Date})
    out = ic_series(pl.concat([big, small]), 'f')
    assert out['date'].to_list() == [d1]


def test_ic_nulls_in_factor_or_forward_are_excluded():
    d = one_day()
    factor = [1.0, None, 3.0, 4.0, None] + [float(i) for i in range(60)]
    fwd = [0.01, 0.02, None, 0.04, 0.05] + [0.0] * 60
    out = ic_series(panel(factor, fwd, d), 'f')
    assert out['n'][0] == 62  # 65 rows - 2 null factor - 1 null fwd


def test_window_ic_stats_and_sign_consistency():
    # one ic observation per year, 2015..2020: five positive, one negative
    days = [D(y, 6, 1) for y in range(2015, 2021)]
    icf = pl.DataFrame({'date': days, 'ic': [0.05, 0.05, 0.05, 0.05, -0.05, 0.05]},
                       schema_overrides={'date': pl.Date})
    stats = window_ic_stats(icf, D(2015, 1, 1), D(2020, 12, 31))
    assert stats['days'] == 6
    assert stats['mean_ic'] == pytest.approx(0.05 * 4 / 6)
    assert len(stats['yearly']) == 6
    ok, detail = sign_consistency(stats, 4)
    assert ok and detail == '5/6'
    bad, _ = sign_consistency(stats, 6)
    assert not bad


def test_sign_consistency_with_no_data_fails_cleanly():
    ok, detail = sign_consistency({'yearly': [], 'mean_ic': None}, 4)
    assert not ok and detail == 'no covered years'


def test_quintile_spread_sign():
    d = one_day()
    n = 100
    spread = quintile_spread(panel([float(i) for i in range(n)],
                                   [-0.05 + 0.001 * i for i in range(n)], d), 'f')
    assert spread['spread_q5_q1'][0] > 0
    assert spread['5'][0] > spread['1'][0]
    assert spread['1'][0] < 0 < spread['5'][0]
