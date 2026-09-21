"""Unit tests for the P2-R10 half-day survey (exp-20260918-p2r10-halfday-survey).

Every factor is hand-checked on synthetic samples; Newey-West t is checked
against three fully hand-derived cases; filters, the increment gate and the
F8 rolling-window boundary (with suspension skip) are all covered.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import polars as pl
import pytest

from quant.research.p2r10_halfday import (
    apply_sample_filters,
    daily_rank_ic,
    decile_gate_pass,
    decile_spread_series,
    compute_factors,
    factor_direction,
    ic_gate_pass,
    increment_gate_pass,
    load_daily_vol20,
    load_listing_index,
    net_one_day_trade,
    newey_west_t,
    spread_window_stats,
    stamp_for,
    WindowStats,
)


def _base_row(**over) -> dict:
    row = {
        'symbol': 'sz.000001', 'date': date(2016, 6, 1),
        'pre_close_vendor': 10.0, 'preclose_official': 10.0,
        'open_930': 10.0, 'close_1100': 10.5, 'close_1130': 11.0,
        'open_1300': 11.0, 'close_1500': 11.5, 'close_day_official': 11.55,
        'high_am': 11.2, 'low_am': 9.9, 'vol_am': 200.0, 'amount_am': 2000.0,
        'limit_up': 11.0, 'limit_down': 9.0,
        'am_limit_up_touch_minutes': 0, 'tradestatus': 1, 'isST': 0,
        'suspended_flag': False, 'bars_that_day': 241, 'daily_vol20': 100.0,
    }
    row.update(over)
    return row


def _factor_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows)


# --------------------------------------------------------------------------- #
# factor hand-calculations (F01..F12, T1, T2)
# --------------------------------------------------------------------------- #
def _three_stock_day() -> pl.DataFrame:
    """Day 2016-06-01, three board-OK stocks; F1 values 0.1 / 0.0 / -0.1."""
    a = _base_row(symbol='sz.000001', vol_am=200.0)
    b = _base_row(symbol='sh.600000', open_930=11.0, close_1130=11.0,
                  close_1100=11.0, preclose_official=10.0,
                  open_1300=11.0, close_day_official=12.1,
                  high_am=11.0, low_am=11.0, vol_am=25.0)
    c = _base_row(symbol='sz.300001', open_930=10.0, close_1130=9.0,
                  close_1100=9.5, preclose_official=10.0,
                  open_1300=9.0, close_day_official=9.45,
                  high_am=10.0, low_am=9.0, vol_am=50.0,
                  am_limit_up_touch_minutes=7)
    frame = _factor_frame([a, b, c])
    return frame


def test_factor_hand_calculations():
    df = compute_factors(_three_stock_day())
    got = {r['symbol']: r for r in df.to_dicts()}
    a, b, c = got['sz.000001'], got['sh.600000'], got['sz.300001']
    # F01 morning return
    assert a['F01'] == pytest.approx(0.1)
    assert b['F01'] == pytest.approx(0.0)
    assert c['F01'] == pytest.approx(-0.1)
    # F02 = F01 minus same-day cross-sectional median (median = 0.0)
    assert a['F02'] == pytest.approx(0.1)
    assert b['F02'] == pytest.approx(0.0)
    assert c['F02'] == pytest.approx(-0.1)
    # F07 volume ratio, F03 = F02 x F07
    assert a['F07'] == pytest.approx(2.0)
    assert b['F07'] == pytest.approx(0.25)
    assert a['F03'] == pytest.approx(0.2)
    assert c['F03'] == pytest.approx(-0.1 * 0.5)
    # F04 overnight gap; F05 = F04 x F02
    assert a['F04'] == pytest.approx(0.0)
    assert c['F04'] == pytest.approx(0.0)
    assert a['F05'] == pytest.approx(0.0)
    # F06 intraday position: (11.0-9.9)/(11.2-9.9+1e-12)
    assert a['F06'] == pytest.approx(1.1 / 1.3, rel=1e-9)
    # F09 touch share
    assert a['F09'] == pytest.approx(0.0)
    assert c['F09'] == pytest.approx(7.0 / 121.0)
    # F10 late-morning momentum
    assert a['F10'] == pytest.approx(11.0 / 10.5 - 1.0)
    # F11 = rank(F02) - rank(F07), average method, within day
    assert a['F11'] == pytest.approx(3.0 - 3.0)
    assert b['F11'] == pytest.approx(2.0 - 1.0)
    assert c['F11'] == pytest.approx(1.0 - 2.0)
    # F12 full-day official return
    assert a['F12'] == pytest.approx(11.55 / 10.0 - 1.0)
    # T1 afternoon official return
    assert a['T1'] == pytest.approx(11.55 / 11.0 - 1.0)
    # F08 with a single prior row: window of 5 not met -> null
    assert a['F08'] is None


def test_t2_uses_next_filtered_row_and_marks_last_null():
    rows = [
        _base_row(symbol='sz.000001', date=date(2016, 6, 1)),
        _base_row(symbol='sz.000001', date=date(2016, 6, 2),
                  open_930=11.0, close_1130=11.5, close_day_official=11.6,
                  open_1300=11.0),
        _base_row(symbol='sz.000001', date=date(2016, 6, 3),
                  open_930=12.0, close_1130=12.5, close_day_official=12.6,
                  open_1300=12.0),
    ]
    df = compute_factors(_factor_frame(rows))
    got = df.sort('date').to_dicts()
    assert got[0]['T2'] == pytest.approx(11.0 / 11.0 - 1.0)
    assert got[1]['T2'] == pytest.approx(12.0 / 11.5 - 1.0)
    assert got[2]['T2'] is None


def test_t2_skips_suspended_gap():
    # day 2 is suspended -> absent from the filtered frame; T2 of day 1
    # must reach day 3's open_930, not a placeholder bar.
    rows = [
        _base_row(symbol='sz.000001', date=date(2016, 6, 1)),
        _base_row(symbol='sz.000001', date=date(2016, 6, 3),
                  open_930=12.0, close_1130=12.5, close_day_official=12.6,
                  open_1300=12.0),
    ]
    df = compute_factors(_factor_frame(rows))
    first = df.filter(pl.col('date') == date(2016, 6, 1)).to_dicts()[0]
    assert first['T2'] == pytest.approx(12.0 / 11.0 - 1.0)


# --------------------------------------------------------------------------- #
# F08 rolling window boundary (own rows, suspension skip, min 5)
# --------------------------------------------------------------------------- #
def _f08_rows(symbol: str, dates: list[date], f1_values: list[float]) -> list[dict]:
    rows = []
    for d, f1 in zip(dates, f1_values):
        rows.append(_base_row(
            symbol=symbol, date=d,
            open_930=10.0, close_1130=10.0 * (1.0 + f1),
            close_1100=10.0, close_day_official=10.0,
            open_1300=10.0, preclose_official=10.0,
            high_am=max(10.0, 10.0 * (1.0 + f1)), low_am=10.0,
            vol_am=100.0))
    return rows


def test_f08_rolling_boundary_and_suspension_skip():
    days = [date(2016, 6, d) for d in (1, 2, 3, 6, 7, 8, 9)]
    a_vals = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    b_vals = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07]
    # B misses 2016-06-04 (index 3): suspension produced no row at all
    rows = (_f08_rows('sz.000001', days, a_vals)
            + _f08_rows('sh.600000', [days[0], days[1], days[2], days[4],
                                      days[5], days[6]], b_vals))
    df = compute_factors(_factor_frame(rows))
    a = sorted([r for r in df.to_dicts() if r['symbol'] == 'sz.000001'],
               key=lambda r: r['date'])
    assert a[4]['F08'] is None  # only 4 prior rows: window of 5 not met
    assert a[5]['F08'] == pytest.approx(-float(np.mean(
        [r['F02'] for r in a[:5]])))
    assert a[6]['F08'] == pytest.approx(-float(np.mean(
        [r['F02'] for r in a[1:6]])))
    # B: rolling runs over its own available rows; the suspended day leaves
    # no null and no gap-filling artefact.
    b = sorted([r for r in df.to_dicts() if r['symbol'] == 'sh.600000'],
               key=lambda r: r['date'])
    assert len(b) == 6
    assert b[4]['F08'] is None
    assert b[5]['F08'] == pytest.approx(-float(np.mean(
        [r['F02'] for r in b[:5]])))
    assert all(r['F02'] is not None for r in b)


# --------------------------------------------------------------------------- #
# Newey-West t: three hand-derived cases + degenerate handling
# --------------------------------------------------------------------------- #
def test_newey_west_t_hand_cases():
    # Case 1: zero mean -> t = 0 exactly (any autocovariance).
    x1 = [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]
    assert newey_west_t(x1) == pytest.approx(0.0, abs=1e-12)
    # Case 2: [1,2,3], lag5 truncated at T-1=2 usable lags:
    # g0=2/3, g1=(x1x2+x2x3)/3 = 0, g2=x1x3/3 = -1/3 (single pair).
    # V = (1/3)[g0 + 2(5/6*g1 + 4/6*g2)] = (1/3)(2/3 - 4/9) = 2/27
    # t = 2/sqrt(2/27) = sqrt(54) = 7.348469...
    assert newey_west_t([1.0, 2.0, 3.0]) == pytest.approx(math.sqrt(54.0),
                                                          rel=1e-12)
    # Case 3: [3,1,4,1,5] fully hand-derived:
    # mean 2.8; g0=2.56; g1=-1.728; g2=1.224; g3=-0.864; g4=0.088; g5=0
    # var = (1/5)[2.56 + 2(5/6*g1 + 4/6*g2 + 3/6*g3 + 2/6*g4)] = 0.101333...
    # se = sqrt(var) ... note code keeps var_raw = T*V then divides by T.
    var_v = (1.0 / 5.0) * (2.56 + 2.0 * ((5.0 / 6.0) * -1.728
                                         + (4.0 / 6.0) * 1.224
                                         + (3.0 / 6.0) * -0.864
                                         + (2.0 / 6.0) * 0.088))
    expected = 2.8 / math.sqrt(var_v)
    assert newey_west_t([3.0, 1.0, 4.0, 1.0, 5.0]) == pytest.approx(expected,
                                                                    rel=1e-12)
    assert expected == pytest.approx(8.7958, abs=1e-3)
    # degenerate: zero variance -> None; NaNs dropped; too-short -> None
    assert newey_west_t([1.0, 1.0, 1.0, 1.0]) is None
    assert newey_west_t([1.0, 2.0, 3.0, float('nan')]) == pytest.approx(
        math.sqrt(54.0), rel=1e-12)
    assert newey_west_t([1.0]) is None


# --------------------------------------------------------------------------- #
# sample filters
# --------------------------------------------------------------------------- #
def test_sample_filters_frozen_block():
    rows = [
        _base_row(symbol='sz.000001'),                                   # keep
        _base_row(symbol='sh.600000', tradestatus=0),                    # suspended
        _base_row(symbol='sz.300001', isST=1),                           # ST
        _base_row(symbol='sh.600004', preclose_official=None),           # missing
        _base_row(symbol='sh.600005', open_1300=None),                   # missing
        _base_row(symbol='sh.600006',
                  close_day_official=13.75),                             # T1=0.25
        _base_row(symbol='sh.600007',
                  close_day_official=13.31),                             # T1=0.21 keep
        _base_row(symbol='sh.688001'),                                   # STAR
        _base_row(symbol='sz.000905'),                                   # CSI index
        _base_row(symbol='sz.000852'),                                   # CSI index
        _base_row(symbol='sz.300002'),                                   # ChiNext keep
    ]
    halfday = _factor_frame(rows)
    listing = pl.DataFrame({
        'symbol': [r['symbol'] for r in rows],
        'date': [r['date'] for r in rows],
        'listing_index': [121, 121, 121, 121, 121, 121, 121, 121, 121, 121, 121],
    })
    kept = apply_sample_filters(halfday, listing)
    assert set(kept['symbol'].to_list()) == {'sz.000001', 'sh.600007',
                                             'sz.300002'}


def test_new_listing_120_sessions_boundary():
    rows = [
        _base_row(symbol='sz.000001'),
        _base_row(symbol='sh.600000'),
    ]
    halfday = _factor_frame(rows)
    listing = pl.DataFrame({
        'symbol': ['sz.000001', 'sh.600000'],
        'date': [r['date'] for r in rows],
        'listing_index': [120, 121],
    })
    kept = apply_sample_filters(halfday, listing)
    assert kept['symbol'].to_list() == ['sh.600000']


def test_listing_index_from_daily_skips_suspended():
    daily = pl.DataFrame({
        'symbol': ['sz.000001'] * 5,
        'date': [date(2016, 6, d) for d in (1, 2, 3, 4, 5)],
        'tradestatus': [1.0, 0.0, 1.0, 1.0, 1.0],
        'volume': [100.0, 0.0, 100.0, 100.0, 100.0],
    })
    idx = load_listing_index_from(daily)
    assert idx['listing_index'].to_list() == [1, 2, 3, 4]
    assert idx['date'].to_list() == [date(2016, 6, 1), date(2016, 6, 3),
                                     date(2016, 6, 4), date(2016, 6, 5)]


def load_listing_index_from(daily: pl.DataFrame) -> pl.DataFrame:
    """Test helper: same core as load_listing_index but on an in-memory frame."""
    return (daily.filter(pl.col('tradestatus') == 1.0)
            .select('symbol', 'date',
                    pl.int_range(pl.len()).over('symbol', order_by='date')
                    .add(1).alias('listing_index')))


def test_daily_vol20_skips_suspended_and_excludes_today(tmp_path):
    # 21 traded rows plus one suspended row in the middle: the suspended day
    # must not enter the rolling window, and today's own volume is excluded.
    dates = [date(2016, 6, d) for d in (1, 2, 3, 6, 7, 8, 9, 10, 13, 14, 15,
                                        16, 17, 20, 21, 22, 23, 24, 27, 28,
                                        29, 30)]
    volumes = [10.0 * (i + 1) for i in range(len(dates))]
    daily = pl.DataFrame({
        'symbol': ['sz.000001'] * (len(dates) + 1),
        'date': dates + [date(2016, 6, 6)],
        'tradestatus': [1.0] * len(dates) + [0.0],
        'volume': volumes + [999.0],
    })
    path = tmp_path / 'daily.parquet'
    daily.write_parquet(path)
    vol20 = load_daily_vol20(path).sort('date')
    assert vol20.height == len(dates)          # suspended row dropped
    vols = vol20['daily_vol20'].to_list()
    assert all(v is None for v in vols[:20])   # window of 20 not met before
    # 21st available row: mean of the first 20 traded volumes (10..200)
    assert vols[20] == pytest.approx(float(np.mean(volumes[:20])))
    # the 999.0 suspended placeholder volume cannot be inside any window
    assert all(v != pytest.approx(999.0) for v in vols if v is not None)


def test_daily_vol20_parquet_path(tmp_path):
    daily = pl.DataFrame({
        'symbol': ['sz.000001'] * 21,
        'date': [date(2016, 1, 1)] * 21,
        'tradestatus': [1.0] * 21,
        'volume': [float(i + 1) for i in range(21)],
    })
    path = tmp_path / 'daily.parquet'
    daily.write_parquet(path)
    vol20 = load_daily_vol20(path)
    assert vol20.height == 21
    got = vol20.sort('date', 'symbol')['daily_vol20'].to_list()
    assert got[19] is None
    assert got[20] == pytest.approx(10.5)


# --------------------------------------------------------------------------- #
# IC, deciles, gates
# --------------------------------------------------------------------------- #
def _ic_panel(day: date, values: list[float], noise: float = 0.0) -> pl.DataFrame:
    n = len(values)
    return pl.DataFrame({
        'symbol': [f'sz.{i:06d}' for i in range(n)],
        'date': [day] * n,
        'F01': values,
        'T1': values,
    })


def test_daily_rank_ic_perfect_and_min_stocks():
    panel = _ic_panel(date(2016, 6, 1), [float(i) for i in range(60)])
    ic = daily_rank_ic(panel, 'F01')
    assert ic.height == 1
    assert ic['ic'][0] == pytest.approx(1.0)
    assert ic['n'][0] == 60
    short = _ic_panel(date(2016, 6, 1), [float(i) for i in range(49)])
    assert daily_rank_ic(short, 'F01').height == 0


def test_decile_spread_direction():
    n = 200
    vals = [float(i) for i in range(n)]  # T1 identical to factor
    panel = _ic_panel(date(2016, 6, 1), vals)
    spread = decile_spread_series(panel, 'F01')
    assert spread.height == 1
    # top decile mean = mean(180..199)=189.5; bottom = mean(0..19)=9.5
    assert spread['spread'][0] == pytest.approx(180.0)


def test_decile_spread_zero_inflated_ties_no_crash():
    # F09-style: 70% of names tied at 0, remainder positive; ordinal ranks
    # must still populate d1 (tied zeros) and d10 (highest values).
    n = 100
    vals = [0.0] * 70 + [float(i) for i in range(1, 31)]
    panel = _ic_panel(date(2016, 6, 1), vals)
    spread = decile_spread_series(panel, 'F01')
    row = spread.to_dicts()[0]
    assert row['d1'] is not None and row['d10'] is not None
    # d1: 10 lowest ordinal ranks = zeros; d10: ranks 91..100 = values 21..30
    assert row['d1'] == pytest.approx(0.0)
    assert row['d10'] == pytest.approx(sum(range(21, 31)) / 10.0)


def test_gates_boundaries():
    assert ic_gate_pass({'mean_ic': 0.02, 'nw_t': 3.0})
    assert not ic_gate_pass({'mean_ic': 0.02, 'nw_t': 2.99})
    assert not ic_gate_pass({'mean_ic': 0.019, 'nw_t': 4.0})
    assert not ic_gate_pass({'mean_ic': None, 'nw_t': None})
    good = WindowStats(n_days=100, mean_daily=0.001,
                       annualized=0.244, month_share_same_sign=0.7,
                       n_months=10)
    assert decile_gate_pass(good)
    assert not decile_gate_pass(WindowStats(
        100, 0.001, 0.0399, 0.7, 10))
    assert not decile_gate_pass(WindowStats(
        100, 0.001, 0.30, 0.599, 10))
    # increment gate: momentum family only, 1.3x control
    assert increment_gate_pass('F01', 0.030, 0.020)   # 0.030 >= 0.026
    assert not increment_gate_pass('F01', 0.025, 0.020)
    assert increment_gate_pass('F03', 0.001, 0.020)   # non-momentum: skip
    assert not increment_gate_pass('F10', None, 0.020)
    assert not increment_gate_pass('F02', 0.05, None)
    assert factor_direction(0.01) == 1
    assert factor_direction(-0.01) == -1
    assert factor_direction(None) == 1


def test_spread_window_stats_direction_and_months():
    dates = [date(2016, 1, 1), date(2016, 2, 1), date(2016, 3, 1)]
    spread = pl.DataFrame({'date': dates, 'spread': [0.001, -0.002, 0.003]})
    pos = spread_window_stats(spread, date(2016, 1, 1), date(2016, 12, 31), 1)
    expected_mean = (0.001 - 0.002 + 0.003) / 3.0
    assert pos.mean_daily == pytest.approx(expected_mean)
    assert pos.annualized == pytest.approx(expected_mean * 244)
    assert pos.n_months == 3
    # direction -1 flips signs; same-sign share counts months matching the
    # overall (flipped) sign
    neg = spread_window_stats(spread, date(2016, 1, 1), date(2016, 12, 31), -1)
    assert neg.annualized == pytest.approx(-pos.annualized)
    assert 0.0 <= neg.month_share_same_sign <= 1.0


# --------------------------------------------------------------------------- #
# net reference (annotation only)
# --------------------------------------------------------------------------- #
def test_net_one_day_trade_hand_calc_and_stamp_segments():
    # 2016: stamp 0.001; gross 5% on 20k
    net = net_one_day_trade(0.05, date(2016, 6, 1))
    # buy fee 5; exit 21000; sell fee 5 + 21 = 26
    assert net == pytest.approx((21000.0 - 26.0) / 20005.0 - 1.0)
    # wan-1 on 20k = 2 yuan < 5 yuan minimum -> minimum binds
    assert net == pytest.approx(969.0 / 20005.0)
    # stamp segmentation
    assert stamp_for(date(2023, 8, 27)) == 0.001
    assert stamp_for(date(2023, 8, 28)) == 0.0005
    net2 = net_one_day_trade(0.05, date(2024, 1, 1))
    assert net2 == pytest.approx((21000.0 - 5.0 - 10.5) / 20005.0 - 1.0)


def test_attach_net_one_day_matches_scalar_formula():
    from quant.research.p2r10_halfday import attach_net_one_day
    rows = [_base_row(symbol='sz.000001', date=d,
                      close_day_official=10.0 * (1.0 + g),
                      open_1300=10.0)
            for d, g in [(date(2016, 6, 1), 0.05),
                         (date(2023, 8, 27), -0.02),
                         (date(2023, 8, 28), 0.03),
                         (date(2024, 3, 1), 0.0)]]
    panel = _factor_frame(rows).with_columns(
        (pl.col('close_day_official') / pl.col('open_1300') - 1.0).alias('T1'))
    got = attach_net_one_day(panel).sort('date')
    for r in got.to_dicts():
        assert r['net1d'] == pytest.approx(
            net_one_day_trade(r['T1'], r['date']), rel=1e-12)


# --------------------------------------------------------------------------- #
# M-1 fix (2026-09-18 double-sign review): shift must be INSIDE .over
# --------------------------------------------------------------------------- #
def test_m1_shift_inside_over_no_cross_symbol_leak_vol20(tmp_path):
    """Later-symbol first row must be null, not the previous symbol's value.

    Regression for the M-1 finding: .over('symbol').shift(1) shifted the
    whole column positionally, so the lexicographically LAST symbol's first
    row received the FIRST symbol's last rolling value.  Symbols are chosen
    so 'sz.000001' sorts after 'sh.600000' (the blind spot of the old
    single-symbol-ordered assertion).
    """
    rows = []
    volumes = {'sh.600000': 100.0, 'sz.000001': 250.0}
    for sym in ('sh.600000', 'sz.000001'):
        for i in range(21):
            rows.append({'symbol': sym, 'date': date(2016, 6, 1 + i),
                         'tradestatus': 1.0,
                         'volume': volumes[sym] * (i + 1)})
    path = tmp_path / 'daily.parquet'
    pl.DataFrame(rows).write_parquet(path)
    vol20 = load_daily_vol20(path).sort('symbol', 'date')
    got: dict[str, list] = {}
    for r in vol20.iter_rows(named=True):
        got.setdefault(r['symbol'], []).append(r['daily_vol20'])
    for sym in ('sh.600000', 'sz.000001'):
        assert got[sym][0] is None            # own window not met: null
    # each symbol's 21st row is the mean of its OWN first 20 volumes
    assert got['sh.600000'][20] == pytest.approx(
        float(np.mean([100.0 * (i + 1) for i in range(20)])))
    assert got['sz.000001'][20] == pytest.approx(
        float(np.mean([250.0 * (i + 1) for i in range(20)])))


def test_m1_f08_first_row_null_on_later_symbol():
    """F08 of the lexicographically later symbol's first row must be null."""
    rows = []
    vals = {'sh.600000': [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            'sz.000001': [0.02, 0.03, 0.04, 0.05, 0.06, 0.07]}
    for sym in ('sh.600000', 'sz.000001'):
        for i, f1 in enumerate(vals[sym]):
            rows.append(_base_row(
                symbol=sym, date=date(2016, 6, i + 1),
                open_930=10.0, close_1130=10.0 * (1.0 + f1),
                close_1100=10.0, close_day_official=10.0,
                open_1300=10.0, preclose_official=10.0,
                high_am=max(10.0, 10.0 * (1.0 + f1)), low_am=10.0,
                vol_am=100.0))
    df = compute_factors(_factor_frame(rows)).sort('symbol', 'date')
    f08: dict[str, list] = {}
    for r in df.iter_rows(named=True):
        f08.setdefault(r['symbol'], []).append(r['F08'])
    assert f08['sh.600000'][0] is None
    assert f08['sz.000001'][0] is None     # buggy code put a value here
    # each day's F02 = f1 - median(two symbols) = +-0.005 constant per side;
    # later symbol's 6th row: -mean of its OWN prior 5 F02 values
    assert f08['sz.000001'][5] == pytest.approx(-0.005)
    assert f08['sh.600000'][5] == pytest.approx(+0.005)
