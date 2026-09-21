"""Unit tests for the P2-R13 low-frequency survey (exp-20260918-p2r13).

Covers the prereg-mandated cases: preclose-bridge ex-dividend forward,
three PIT rules (northbound T+1 disclosure, accrual end+90d fallback,
block-trade T+1), month-end cross-section determinism, the C2 250-session
boundary, financial-industry exclusion, seed determinism, 2025+ zero-touch,
and the shift-inside-over rule (the P2-R10 M-1 bug class).
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from quant.research import p2r13_lowfreq as lf
from quant.research.p2r10_halfday import newey_west_t


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sessions(n: int, start: date = date(2015, 1, 5)) -> list[date]:
    """n 'trading sessions' as consecutive weekdays."""
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _hist_frame(rows: list[dict]) -> pl.DataFrame:
    return lf.attach_history_factors(pl.DataFrame(rows).sort('symbol',
                                                             'date'))


def _constant_stock(symbol: str, dates: list[date], price: float = 10.0,
                    amount: float = 1.0e8, is_st: float = 0.0) -> list[dict]:
    """Rows with preclose = prior close (no corporate actions)."""
    rows = []
    prev = price
    for i, d in enumerate(dates):
        rows.append({
            'symbol': symbol, 'date': d, 'open': price, 'close': price,
            'preclose': prev, 'amount': amount, 'isST': is_st,
            'tradestatus': 1.0, 'listing_index': i + 1,
            'mkt_idx': i,
        })
        prev = price
    return rows


# --------------------------------------------------------------------------- #
# 1. preclose bridge across an ex-dividend day
# --------------------------------------------------------------------------- #
def test_preclose_bridge_forward_includes_dividend() -> None:
    dates = _sessions(23)
    rows = _constant_stock('sh.600000', dates)
    # session index 10 goes ex-dividend: published preclose = prior close - 1
    rows[10]['preclose'] = 9.0
    hist = _hist_frame(rows)
    panel = pl.DataFrame({
        'month': [dates[0]], 's': [dates[0]], 's_idx': [0],
        'symbol': ['sh.600000'], 'close': [10.0],
        'C1': [None], 'C2': [None], 'C6': [None]},
        schema={'month': pl.Date, 's': pl.Date, 's_idx': pl.Int32,
                'symbol': pl.String, 'close': pl.Float64,
                'C1': pl.Float64, 'C2': pl.Float64, 'C6': pl.Float64})
    out = lf.attach_forward(hist, panel)
    fwd = out['fwd'][0]
    # entry at t1 open (10), exit at t21 open: chain accumulated 10/9 on the
    # ex-div day -> o_exit/o_entry = (10/9)*10 / 10 = 10/9 -> +11.11%
    assert fwd == pytest.approx(10.0 / 9.0 - 1.0, abs=1e-12)
    assert fwd > 0.05  # a naive open/open price ratio would be exactly 0


def test_forward_entry_requires_t_plus_1_session_exit_skips_suspension() -> None:
    dates = _sessions(25)
    rows = _constant_stock('sh.600000', dates)
    hist_all = _hist_frame(rows)
    panel = pl.DataFrame({
        'month': [dates[0]], 's': [dates[0]], 's_idx': [0],
        'symbol': ['sh.600000'], 'close': [10.0]},
        schema={'month': pl.Date, 's': pl.Date, 's_idx': pl.Int32,
                'symbol': pl.String, 'close': pl.Float64})
    # exit delayed: drop the t21 row (suspended at T+21), exit moves to t22
    hist_no_t21 = _hist_frame([r for i, r in enumerate(rows) if i != 21])
    fwd_full = lf.attach_forward(hist_all, panel)['fwd'][0]
    fwd_delayed = lf.attach_forward(hist_no_t21, panel)['fwd'][0]
    # one extra day of flat prices -> chain ratio 1.0 -> identical forward
    assert fwd_full == pytest.approx(fwd_delayed, abs=1e-12)
    assert fwd_full is not None
    # entry impossible: drop the t1 row -> fwd null
    hist_no_t1 = _hist_frame([r for i, r in enumerate(rows) if i != 1])
    assert lf.attach_forward(hist_no_t1, panel)['fwd'][0] is None


# --------------------------------------------------------------------------- #
# 2. PIT rules
# --------------------------------------------------------------------------- #
def test_pit_northbound_disclosure_t_plus_1() -> None:
    dates = _sessions(30)
    cal = pl.DataFrame({'date': dates,
                        'mkt_idx': list(range(len(dates)))})
    s_idx = 25
    panel = pl.DataFrame({
        's': [dates[s_idx]], 'symbol': ['sh.600000'], 's_idx': [s_idx]},
        schema={'s': pl.Date, 'symbol': pl.String, 's_idx': pl.Int32})
    hk = pl.DataFrame({
        'symbol': ['sh.600000'] * 3,
        'date': [dates[s_idx - 21], dates[s_idx - 1], dates[s_idx]],
        'ratio': [1.0, 5.0, 9.0]})
    out = lf.northbound_delta(hk, cal, panel)
    # T+1: the value disclosed for day s (9.0) must NOT be used; use s-1 (5.0)
    assert out['C3'][0] == pytest.approx(5.0 - 1.0)
    assert out['r_a'][0] == pytest.approx(5.0)


def test_pit_accrual_end_plus_90_fallback_and_ann_date() -> None:
    end = date(2015, 12, 31)
    assert lf.visible_date(None, end) == date(2016, 3, 30)  # +90d (leap yr)
    assert lf.visible_date(date(2016, 2, 1), end) == date(2016, 3, 30)
    assert lf.visible_date(date(2016, 4, 20), end) == date(2016, 4, 20)
    accrual = pl.DataFrame({
        'symbol': ['sh.600000', 'sh.600000'],
        'end_date': [end, date(2016, 12, 31)],
        'visible': [date(2016, 3, 30), date(2017, 4, 10)],
        'accrual': [0.10, 0.20]})
    panel = pl.DataFrame({
        's': [date(2016, 3, 29), date(2016, 3, 30),
              date(2017, 4, 9), date(2017, 4, 10)],
        'symbol': ['sh.600000'] * 4})
    out = lf.accrual_at_signal(accrual, panel).sort('s')
    assert out['C4'].to_list()[0] is None          # not yet visible
    assert out['C4'].to_list()[1] == pytest.approx(-0.10)
    assert out['C4'].to_list()[2] == pytest.approx(-0.10)
    assert out['C4'].to_list()[3] == pytest.approx(-0.20)


# --------------------------------------------------------------------------- #
# 3b. C3 month-drop rule over disclosure-universe members
# --------------------------------------------------------------------------- #
def test_c3_member_relative_month_drop() -> None:
    dates = _sessions(40)
    cal = pl.DataFrame({'date': dates, 'mkt_idx': list(range(len(dates)))})
    s1, s2 = dates[30], dates[39]
    panel = pl.DataFrame({
        's': [s1] * 3 + [s2] * 2,
        'symbol': ['sh.600000', 'sh.600001', 'sh.600002',
                   'sh.600000', 'sh.600001'],
        's_idx': [30] * 3 + [39] * 2,
        'C3': [0.5, None, 0.1, 0.2, 0.3]})
    # hk rows: 600000 and 600001 disclose recently before both signals;
    # 600002 never discloses (out-of-domain: not a member, not counted)
    hk_rows = []
    for sym in ('sh.600000', 'sh.600001'):
        for i in (8, 28, 38):
            hk_rows.append({'symbol': sym, 'date': dates[i], 'ratio': 1.0})
    hk = pl.DataFrame(hk_rows)
    panel_c3, drops = lf.c3_member_missing(panel, hk, cal)
    # month s1: members {600000, 600001}; 600001 missing -> rate .5 > .1 dropped
    # month s2: members {600000, 600001}; both valid -> kept
    assert [str(d) for d in panel_c3['s'].unique().to_list()] == [str(s2)]
    assert len(drops) == 1 and drops[0]['month'] == str(s1)
    assert drops[0]['members_n'] == 2 and drops[0]['missing_n'] == 1


def test_pit_block_trade_t_plus_1_window_boundary() -> None:
    def block_frame(trades: list[tuple[int, float, float]]) -> pl.DataFrame:
        return pl.DataFrame({
            'symbol': ['sh.600000'] * len(trades),
            't_idx': [t for t, _, _ in trades],
            'w': [w for _, w, _ in trades],
            'amt': [a for _, _, a in trades]},
            schema={'symbol': pl.String, 't_idx': pl.Int64,
                    'w': pl.Float64, 'amt': pl.Float64})

    panel = pl.DataFrame({
        's': [date(2020, 6, 30), date(2020, 7, 1)],
        'symbol': ['sh.600000'] * 2,
        's_idx': [100, 101]},
        schema={'s': pl.Date, 'symbol': pl.String, 's_idx': pl.Int32})
    # trades: (t, disc*amt, amt); window for s=100 is t in [80, 99]
    block = block_frame([(79, -10.0, 100.0),   # t = s-21: outside
                         (80, 10.0, 100.0),    # t = s-20: inside
                         (99, 30.0, 100.0),    # t = s-1:  inside
                         (100, 1000.0, 100.0)])  # t = s: T+1 -> only next
    out = lf.block_discount_factor(block, panel).sort('s')
    assert out['C5'][0] == pytest.approx(-(10.0 + 30.0) / 200.0)
    # signal 101: window [81, 100] includes day-99 and day-100 trades only
    assert out['C5'][1] == pytest.approx(-(30.0 + 1000.0) / 200.0)


# --------------------------------------------------------------------------- #
# 3. month-end cross-section determinism
# --------------------------------------------------------------------------- #
def test_month_end_sessions_last_session_per_month() -> None:
    cal = pl.DataFrame({'date': [date(2015, 1, 29), date(2015, 1, 30),
                                 date(2015, 2, 2), date(2015, 2, 27)],
                        'mkt_idx': [0, 1, 2, 3]})
    me = lf.month_end_sessions(cal)
    assert me['s'].to_list() == [date(2015, 1, 30), date(2015, 2, 27)]
    assert me['s_idx'].to_list() == [1, 3]


def test_decile_construction_deterministic_under_ties() -> None:
    rows = []
    for i in range(60):
        rows.append({'s': date(2020, 6, 30),
                     'symbol': f'sh.60{i:04d}',
                     'F': 0.0 if i < 30 else float(i),  # 30-way tie
                     'fwd': float(i) / 100.0})
    panel = pl.DataFrame(rows)
    a = lf.decile_monthly_spread(panel, 'F')
    b = lf.decile_monthly_spread(panel.sort('s', 'symbol'), 'F')
    assert a.equals(b)          # identical across calls and input orders
    assert a.select(pl.all_horizontal(
        pl.col('d1', 'd10').is_not_null())).item()  # every decile populated


# --------------------------------------------------------------------------- #
# 4. C2 250-session boundary + C1 window
# --------------------------------------------------------------------------- #
def test_c2_requires_250_own_sessions() -> None:
    dates = _sessions(260)
    rows = _constant_stock('sh.600000', dates)
    hist = _hist_frame(rows)
    # own-session index == listing_index here (no gaps)
    at_249 = hist.filter(pl.col('listing_index') == 249)
    at_250 = hist.filter(pl.col('listing_index') == 250)
    assert at_250['C2'][0] is not None
    assert at_250['C2'][0] == pytest.approx(1.0)  # constant price
    assert at_249['C2'][0] is None
    # C1 needs 60 own sessions
    assert hist.filter(pl.col('listing_index') == 59)['C1'][0] is None
    assert hist.filter(pl.col('listing_index') == 60)['C1'][0] \
        == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# 5. financial-industry exclusion (C4-only)
# --------------------------------------------------------------------------- #
def test_financial_exclusion_c4_only() -> None:
    panel = pl.DataFrame({
        's': [date(2020, 6, 30)] * 3,
        'symbol': ['sh.600000', 'sh.600036', 'sz.000001'],
        'C4': [0.1, 0.2, 0.3]})
    industries = pl.DataFrame({
        'symbol': ['sh.600036', 'sz.000001'],
        'industry': ['银行', '银行']})
    out = lf.apply_financial_exclusion(panel, industries)
    assert out['symbol'].to_list() == ['sh.600000']
    # other factors are NOT filtered by industries
    assert panel.height == 3


# --------------------------------------------------------------------------- #
# 6. seed determinism (M1 permutation) + NW hand case
# --------------------------------------------------------------------------- #
def test_tom_measurement_seeded_deterministic() -> None:
    dates = _sessions(300)
    rng = np.random.default_rng(7)
    pool = pl.DataFrame({
        'date': dates, 'r': rng.normal(0.0005, 0.01, len(dates))})
    cal = pl.DataFrame({'date': dates,
                        'mkt_idx': list(range(len(dates)))})
    a = lf.tom_measurement(pool, cal, dates[0], dates[-1])
    b = lf.tom_measurement(pool, cal, dates[0], dates[-1])
    assert a == b               # seeded: identical across calls
    assert a['n_windows'] >= 10
    assert a['permutation_p05'] <= a['permutation_p95']


def test_newey_west_lag6_hand_case() -> None:
    # x = [0, 1]: mean .5; g0 = .25; g1 = -.125
    # var = .25 + 2*(1 - 1/7)*(-.125) = .0357143; se = sqrt(var/2)
    t = newey_west_t([0.0, 1.0], 6)
    expected = 0.5 / math.sqrt((0.25 + 2 * (6 / 7) * (-0.125)) / 2)
    assert t == pytest.approx(expected, abs=1e-12)
    assert newey_west_t([1.0, 1.0], 6) is None


# --------------------------------------------------------------------------- #
# 7. 2025+ zero-touch
# --------------------------------------------------------------------------- #
def test_keep_complete_forward_drops_boundary_signal() -> None:
    # calendar ending 2024-12-31 at mkt_idx 999
    dates = [date(2024, 1, 1) + timedelta(days=i) for i in range(1000)]
    signals = pl.DataFrame({
        'month': [date(2024, 1, 1), date(2024, 12, 1)],
        's': [dates[900], dates[999]],
        's_idx': [900, 999]})
    kept = lf.keep_complete_forward(signals, last_mkt_idx=999)
    assert kept['s_idx'].to_list() == [900]  # 999 + 21 > 999 -> dropped


def test_build_history_freeze_filter(tmp_path) -> None:
    dates = _sessions(5) + [date(2025, 1, 2)]
    rows = _constant_stock('sh.600000', dates)
    frame = pl.DataFrame(rows)
    path = tmp_path / 'daily.parquet'
    frame.write_parquet(path)
    cal = pl.DataFrame({
        'date': dates, 'mkt_idx': list(range(len(dates)))})
    out = lf.build_history(path, cal)
    assert out['date'].max() <= lf.FREEZE_LAST
    assert out.height == 5


# --------------------------------------------------------------------------- #
# 8. shift-inside-over compliance (P2-R10 M-1 bug class)
# --------------------------------------------------------------------------- #
def test_shift_inside_over_no_cross_symbol_leak() -> None:
    dates = _sessions(30)
    rows = _constant_stock('sh.600000', dates, price=10.0)
    rows += _constant_stock('sz.000001', dates[:5], price=100.0)
    hist = _hist_frame(rows)
    b = hist.filter(pl.col('symbol') == 'sz.000001')
    # every row of the short symbol must be null for C6 (needs 21 own rows);
    # a global positional shift would leak sh.600000 values into it
    assert b['C6'].null_count() == 5
    assert b['C1'].null_count() == 5
    # chains restart per symbol: first row c_adj = close/preclose
    assert b['c_adj'][0] == pytest.approx(1.0)
    a_last = hist.filter(pl.col('symbol') == 'sh.600000')[-1]
    assert a_last['C6'][0] == pytest.approx(0.0)  # constant price -> no momentum


# --------------------------------------------------------------------------- #
# 9. universe waterfall at the signal session
# --------------------------------------------------------------------------- #
def test_universe_signals_waterfall() -> None:
    dates = _sessions(25)
    d = dates[-1]
    rows = []
    for sym, st, listing, amount, close in [
            ('sh.600000', 0.0, 2000, 2.0e8, 10.0),   # ok
            ('sh.600001', 1.0, 2000, 2.0e8, 10.0),   # ST
            ('sh.600002', 0.0, 100, 2.0e8, 10.0),    # new listing
            ('sz.300001', 0.0, 2000, 2.0e8, 10.0),   # ChiNext board
            ('sh.600003', 0.0, 2000, 1.0e6, 10.0),   # illiquid
            ('sh.600004', 0.0, 2000, 2.0e8, 1.5)]:   # close < 2
        rows += _constant_stock(sym, dates, price=close, amount=amount,
                                is_st=st)
        for r in rows[-len(dates):]:
            r['listing_index'] = listing
    hist = _hist_frame(rows)
    hist = hist.with_columns(
        pl.when(pl.col('symbol') == 'sh.600000').then(pl.lit(0.1))
        .when(pl.col('symbol') == 'sh.600001').then(pl.lit(0.2))
        .otherwise(pl.lit(None)).alias('C1'),
        pl.lit(None, dtype=pl.Float64).alias('C2'),
        pl.lit(None, dtype=pl.Float64).alias('C6'))
    signals = pl.DataFrame({'month': [d], 's': [d],
                            's_idx': [len(dates) - 1]})
    panel, counts = lf.universe_signals(hist, signals)
    assert panel['symbol'].to_list() == ['sh.600000']
    assert counts['after_st'] == 5
    assert counts['after_listing_120'] == 4
    assert counts['after_boards'] == 3
    assert counts['after_liq_50m'] == 2
    assert counts['after_close_2yuan'] == 1


# --------------------------------------------------------------------------- #
# 10. gates, annualization, misc helpers
# --------------------------------------------------------------------------- #
def test_increment_and_decile_gates() -> None:
    assert lf.increment_gate_pass(0.030, 0.020) is True   # 0.03 >= 0.026
    assert lf.increment_gate_pass(0.025, 0.020) is False
    assert lf.increment_gate_pass(None, 0.020) is False
    stats = {'n_months': 72, 'mean_aligned': 0.004,
             'annualized': 0.004 * 244 / 20,
             'month_share_same_sign': 0.60}
    assert lf.decile_gate_pass(stats) is True
    assert lf.decile_gate_pass({**stats,
                                'month_share_same_sign': 0.59}) is False
    assert lf.decile_gate_pass({**stats, 'annualized': 0.039}) is False


def test_spread_alignment_and_annualization() -> None:
    months = [date(2020, m, 28) for m in range(1, 13)]
    spread = pl.DataFrame({'s': months, 'spread': [0.01] * 6 + [-0.01] * 6})
    stats = lf.spread_window_stats(spread, date(2020, 1, 1),
                                   date(2020, 12, 31), direction=1)
    assert stats['mean_aligned'] == pytest.approx(0.0, abs=1e-12)
    stats_neg = lf.spread_window_stats(spread, date(2020, 1, 1),
                                       date(2020, 12, 31), direction=-1)
    assert stats_neg['mean_aligned'] == pytest.approx(0.0, abs=1e-12)
    spread_pos = pl.DataFrame({'s': months, 'spread': [0.01] * 12})
    stats_p = lf.spread_window_stats(spread_pos, date(2020, 1, 1),
                                     date(2020, 12, 31), direction=1)
    assert stats_p['annualized'] == pytest.approx(0.01 * 244 / 20)
    assert stats_p['month_share_same_sign'] == pytest.approx(1.0)


def test_ts_to_symbol() -> None:
    assert lf.ts_to_symbol('600000.SH') == 'sh.600000'
    assert lf.ts_to_symbol('000001.SZ') == 'sz.000001'
    assert lf.ts_to_symbol('BK0710.HK') is None
    assert lf.ts_to_symbol(None) is None
    assert lf.ts_to_symbol('430047.BJ') is None


def test_monthly_rank_ic_min_names() -> None:
    rows = []
    for i in range(3):  # only 3 names -> month dropped (min 50)
        rows.append({'s': date(2020, 6, 30), 'symbol': f'sh.60{i:04d}',
                     'C1': float(i), 'fwd': float(i)})
    ic = lf.monthly_rank_ic(pl.DataFrame(rows), 'C1')
    assert ic.height == 0


def test_round_trip_fee_segments() -> None:
    assert lf.round_trip_fee(date(2022, 1, 4)) == pytest.approx(
        2 * 5 + 20000 * 0.001)
    assert lf.round_trip_fee(date(2023, 8, 28)) == pytest.approx(
        2 * 5 + 20000 * 0.0005)


def test_correlation_matrix_diagonal() -> None:
    rows = []
    for m, month in enumerate([date(2020, 1, 23), date(2020, 2, 21)]):
        for i in range(60):
            rows.append({'s': month, 'symbol': f'sh.60{i:04d}',
                         'C1': float(i) + m, 'C2': float(i) * 2.0,
                         'C3': -float(i), 'C4': float(i) % 7,
                         'C5': float(i) / 3.0, 'C6': float(i) * 0.5})
    corr = lf.factor_correlation_matrix(pl.DataFrame(rows))
    assert all(v == 1.0 for k, v in corr['C1'].items() if k == 'C1')
    assert corr['C1']['C2'] == pytest.approx(1.0, abs=1e-9)
    assert corr['C1']['C3'] == pytest.approx(-1.0, abs=1e-9)
