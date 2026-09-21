"""Unit tests for the P2-R6 ETF rotation engine (synthetic data only).

Each test pins one preregistered semantic: next-open execution, min-5 CNY
commission, keep/sell discipline, rank backfill, suspension postponement,
limit proxy blocks, forced delist exits, T+1, B1/B2 benchmark arithmetic,
metrics and the frozen gate thresholds.  Synthetic values are never
profitability evidence.
"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl
import pytest

from quant.research import etf_rotation as er  # noqa: E402
from quant.research.etf_rotation import (  # noqa: E402
    ETF_FEE_BAND,
    GROSS_FEE_BAND,
    CodeDataBank,
    PoolRow,
    build_plan,
    cagr,
    concentration,
    evaluate_dev_gate,
    evaluate_test,
    evaluate_val_gate,
    ExecStats,
    group_pools,
    max_drawdown,
    monthly_top_decile,
    rank_pool,
    rebalance_days,
    simulate,
    simulate_b1,
    simulate_b2,
    topn,
    turnover_by_year,
    year_returns,
)
from quant.research.screen import fee_band_for  # noqa: E402

D = date


def weekdays(n: int, start: D = D(2016, 1, 4)) -> list[D]:
    days, day = [], start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def make_feat(codes: dict[str, dict[str, list]], calendar: list[D]) -> pl.DataFrame:
    """Hand-built feature frame: per-code column lists over ``calendar``.

    Recognized keys: open, close, pre_close, amount, adj_open, adj_close,
    last_row, r20, r60, r120, sma120, eligible, gate_ok.  Rows where the open
    is None are dropped (suspension)."""
    rows = []
    for code, cols in codes.items():
        for i, day in enumerate(calendar):
            open_ = cols['open'][i] if i < len(cols['open']) else None
            if open_ is None:
                continue
            rows.append({
                'ts_code': code, 'trade_date': day,
                'open': open_,
                'close': cols['close'][i],
                'pre_close': cols['pre_close'][i],
                'amount': cols.get('amount', [1e6] * len(calendar))[i],
                'adj_open': cols['adj_open'][i] if 'adj_open' in cols else open_,
                'adj_close': (cols['adj_close'][i] if 'adj_close' in cols
                              else cols['close'][i]),
                'last_row': cols.get('last_row', [False] * len(calendar))[i],
                'r20': cols.get('r20', [0.0] * len(calendar))[i],
                'r60': cols.get('r60', [0.0] * len(calendar))[i],
                'r120': cols.get('r120', [0.0] * len(calendar))[i],
                'sma120': cols.get('sma120', [0.0] * len(calendar))[i],
                'eligible': cols.get('eligible', [True] * len(calendar))[i],
                'gate_ok': cols.get('gate_ok', [True] * len(calendar))[i],
            })
    frame = pl.DataFrame(rows)
    return frame.with_columns(
        *(pl.col(c).cast(pl.Float64) for c in
          ('open', 'close', 'pre_close', 'amount', 'adj_open', 'adj_close',
           'r20', 'r60', 'r120', 'sma120')))


def flat_prices(code: str, opens: list[float], closes: list[float],
                pre_closes: list[float], **cols) -> dict:
    n = len(opens)
    out = {'open': opens, 'close': closes, 'pre_close': pre_closes}
    out['last_row'] = cols.pop('last_row', [False] * n)
    for key in ('adj_open', 'adj_close', 'r20', 'r60', 'r120', 'sma120',
                'eligible', 'gate_ok'):
        if key in cols:
            out[key] = cols.pop(key)
    assert not cols, f'unused cols {cols}'
    return out


# --------------------------------------------------------------------------- #
# calendar
# --------------------------------------------------------------------------- #
def test_rebalance_days_monthly_last_session():
    cal = [D(2016, 1, 4), D(2016, 1, 29), D(2016, 2, 1), D(2016, 2, 29),
           D(2016, 3, 1)]
    assert rebalance_days(cal, 'monthly', D(2016, 1, 1)) == [D(2016, 1, 29),
                                                             D(2016, 2, 29),
                                                             D(2016, 3, 1)]
    assert rebalance_days(cal, 'monthly', D(2016, 2, 1)) == [D(2016, 2, 29),
                                                             D(2016, 3, 1)]


def test_rebalance_days_weekly_iso_holiday_week():
    # 2016-01-01 (Fri, holiday absent); ISO 2015-W53 sessions Dec 28-31 are
    # before the start, so the first weekly signal is the W01 last session.
    cal = [D(2015, 12, 28), D(2015, 12, 29), D(2015, 12, 30), D(2015, 12, 31),
           D(2016, 1, 4), D(2016, 1, 5), D(2016, 1, 6), D(2016, 1, 7),
           D(2016, 1, 8), D(2016, 1, 11), D(2016, 1, 15)]
    assert rebalance_days(cal, 'weekly', D(2016, 1, 1)) == [D(2016, 1, 8),
                                                            D(2016, 1, 15)]


# --------------------------------------------------------------------------- #
# ranking
# --------------------------------------------------------------------------- #
def _row(code, r20, r60=0.0, r120=0.0, gate=True):
    return PoolRow(code, r20, r60, r120, gate, True)


def test_rank_pool_percentile_and_order():
    rows = [_row('A', 0.10), _row('B', 0.30), _row('C', 0.20)]
    ranked = rank_pool(rows, (20,))
    assert [r.code for r in ranked] == ['B', 'C', 'A']


def test_rank_pool_multi_window_mean_and_tie_break():
    # W=(20,60): A best on both; B/C swap windows -> equal mean -> code order
    rows = [_row('A', 0.30, 0.30), _row('B', 0.20, 0.10), _row('C', 0.10, 0.20)]
    ranked = rank_pool(rows, (20, 60))
    assert [r.code for r in ranked] == ['A', 'B', 'C']


def test_topn_gate_filters():
    rows = [_row('A', 0.4, gate=True), _row('B', 0.3, gate=False),
            _row('C', 0.2, gate=True), _row('D', 0.1, gate=True)]
    assert [r.code for r in topn(rows, (20,), gate=True)] == ['A', 'C', 'D']
    assert [r.code for r in topn(rows[:2], (20,), gate=True)] == ['A']


# --------------------------------------------------------------------------- #
# engine: basic rotation semantics
# --------------------------------------------------------------------------- #
BUDGET = 300.0  # per slot; fee min 5 CNY binds: max(300*0.0001, 5) = 5


def _basic_codes(cal):
    n = len(cal)
    tail8 = [10, 10.5, 11, 11, 11, 12, 12, 12]
    tail8c = [10.2, 10.8, 11.2, 11, 11.5, 12.2, 12.1, 12]
    tail8p = [10, 10.2, 10.8, 11.2, 11, 11.5, 12.2, 12.1]
    pad = lambda seq, fill: seq + [fill] * (n - len(seq))  # noqa: E731
    return {
        'A': flat_prices('A', pad(tail8, 12), pad(tail8c, 12), pad(tail8p, 12)),
        'B': flat_prices('B', [20] * n, [20] * n, [20] * n),
        'C': flat_prices('C', pad([30, 30, 30, 30, 31], 31),
                         pad([30, 30, 30, 30, 31], 31),
                         pad([30, 30, 30, 30, 30], 31)),
        'D': flat_prices('D', pad([40, 40, 40, 40, 40, 40.5], 41),
                         pad([40, 40, 40, 40, 40, 40.8], 41),
                         pad([40, 40, 40, 40, 40, 40.5], 41)),
    }


def test_engine_entry_at_next_open_and_fees():
    cal = weekdays(8)
    feat = make_feat(_basic_codes(cal), cal)
    bank = CodeDataBank(feat, cal)
    plans = [[D(2016, 1, 4)], [['A', 'B', 'C']]]
    result = simulate('T', bank, cal, cal[0], [cal[0]],
                      lambda t: ['A', 'B', 'C'], budget=BUDGET,
                      fees=ETF_FEE_BAND)
    buys = [t for t in result.trades if t['side'] == 'buy']
    assert len(buys) == 3
    assert all(t['session'] == cal[1] for t in buys)  # next open after signal
    a = next(t for t in buys if t['code'] == 'A')
    assert a['raw_price'] == 10.5 and a['fee'] == 5.0  # min commission binds
    assert a['notional'] == BUDGET
    assert a['units'] == pytest.approx((BUDGET - 5.0) / 10.5)
    # equity at signal-day close: all cash (no positions yet)
    assert result.equity[0] == pytest.approx(3 * BUDGET)


def test_engine_keep_and_rotate_discipline():
    cal = weekdays(8)
    codes = _basic_codes(cal)
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    # signal d0: A,B,C; signal d4: A,B,D -> C sold at d5 open, D bought there
    ranked = {cal[0]: ['A', 'B', 'C', 'D'], cal[4]: ['A', 'B', 'D', 'C']}
    result = simulate('T', bank, cal, cal[0], [cal[0], cal[4]],
                      lambda t: ranked[t], budget=BUDGET, fees=ETF_FEE_BAND)
    sells = [t for t in result.trades if t['side'] == 'sell']
    assert len(sells) == 1 and sells[0]['code'] == 'C'
    assert sells[0]['session'] == cal[5]
    assert sells[0]['raw_price'] == 31.0
    late_buys = [t for t in result.trades if t['side'] == 'buy'
                 and t['session'] == cal[5]]
    assert [t['code'] for t in late_buys] == ['D']
    assert result.exec_stats.sells_filled == 1
    assert result.exec_stats.buys_filled == 4
    # incumbents A/B were never traded again
    a_buys = [t for t in result.trades if t['side'] == 'buy'
              and t['code'] == 'A']
    assert len(a_buys) == 1


def test_plan_backfill_walks_full_rank_list():
    slots = [er._Slot(cash=BUDGET) for _ in range(3)]
    stats = ExecStats()
    plan = build_plan(slots, ['A', 'B', 'C', 'D', 'E'], stats)
    assert plan['n_buy'] == 3
    assert plan['buys'] == ['A', 'B', 'C', 'D', 'E']  # untruncated: backfill pool
    assert stats.planned_buy_legs == 3


def test_engine_entry_suspension_and_limit_up_backfill():
    cal = weekdays(8)
    codes = _basic_codes(cal)
    # A suspended at d1 (entry session); B limit-up open at d1 (+15%)
    codes['A'] = flat_prices(
        'A', [10, 10.5, 11, 11, 11, 12, 12, 12],
        [10.2, 10.8, 11.2, 11, 11.5, 12.2, 12.1, 12],
        [10, 10.2, 10.8, 11.2, 11, 11.5, 12.2, 12.1])
    codes['B'] = flat_prices(
        'B', [20, 23, 21, 21, 20, 20, 20, 20],
        [20, 21, 21, 21, 20, 20, 20, 20],
        [20, 20, 21, 21, 20, 20, 20, 20])
    codes['E'] = flat_prices('E', [50] * 8, [50] * 8, [50] * 8)
    feat = make_feat(codes, cal)
    # manually drop A's d1 row (suspension)
    feat = feat.filter(~((pl.col('ts_code') == 'A') & (pl.col('trade_date') == cal[1])))
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E']}
    result = simulate('T', bank, cal, cal[0], [cal[0]], lambda t: ranked[t],
                      budget=BUDGET, fees=ETF_FEE_BAND)
    fills = [t for t in result.trades if t['side'] == 'buy']
    assert [t['code'] for t in fills] == ['C', 'D', 'E']
    assert result.exec_stats.entry_suspended == 1
    assert result.exec_stats.entry_limit_blocked == 1


def test_engine_exit_postponed_and_slot_busy_cancel():
    cal = weekdays(10)
    codes = _basic_codes(cal)
    # A suspended at d3 (planned exit session); B limit-down open at d3
    codes['A'] = flat_prices(
        'A', [10, 10.5, 11, 11, 11, 11.5, 12, 12, 12, 12],
        [10.2, 10.8, 11.2, 11, 11, 11.8, 12.2, 12.1, 12, 12],
        [10, 10.2, 10.8, 11.2, 11, 11, 11.8, 12.2, 12.1, 12])
    codes['A']['last_row'] = [False] * 10
    feat = make_feat(codes, cal)
    feat = feat.filter(~((pl.col('ts_code') == 'A')
                         & (pl.col('trade_date') == cal[3])))
    codes['B'] = flat_prices(
        'B', [20, 20, 20, 17.5, 20, 20, 20, 20, 20, 20],
        [20, 20, 20, 18, 20, 20, 20, 20, 20, 20],
        [20, 20, 20, 20, 18, 20, 20, 20, 20, 20])  # d3 open 17.5/20 = -12.5%
    feat = pl.concat([feat.filter(pl.col('ts_code') != 'B'),
                      make_feat({'B': codes['B']}, cal)], how='vertical')
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E'],
              cal[2]: ['D', 'E', 'F', 'A', 'B'],
              cal[5]: ['D', 'E', 'F']}
    for code in ('E', 'F'):
        codes.setdefault(code, flat_prices(
            code, [50] * 10, [50] * 10, [50] * 10))
    feat = pl.concat([feat.filter(~pl.col('ts_code').is_in(['E', 'F'])),
                      make_feat({c: codes[c] for c in ('E', 'F')}, cal)],
                     how='vertical')
    bank = CodeDataBank(feat, cal)
    result = simulate('T', bank, cal, cal[0], [cal[0], cal[2], cal[5]],
                      lambda t: ranked[t], budget=BUDGET, fees=ETF_FEE_BAND)
    # d3: C's slot freed and filled with D; A/B exits postponed -> 2 buys cancelled
    assert result.exec_stats.buys_cancelled_slot_busy == 2
    assert result.exec_stats.exit_suspended == 1
    assert result.exec_stats.exit_limit_blocked == 1
    # d4: A and B postponed exits fill at the open
    late_sells = [t for t in result.trades if t['kind'] == 'sell_postponed']
    assert sorted(t['code'] for t in late_sells) == ['A', 'B']
    assert all(t['session'] == cal[4] for t in late_sells)
    assert result.exec_stats.sells_postponed_then_filled == 2
    # d6: re-planned buys for the freed A/B slots
    d6_buys = [t for t in result.trades if t['side'] == 'buy'
               and t['session'] == cal[6]]
    assert [t['code'] for t in d6_buys] == ['E', 'F']


def test_engine_forced_delist_exit_and_t1():
    cal = weekdays(8)
    codes = _basic_codes(cal)
    # C quotes end at d4: held from d1 -> forced exit at d4 close
    codes['C'] = flat_prices(
        'C', [30, 30, 30, 30, 31, 31, 31, 31],
        [30, 30, 30, 30, 30.5, 31, 31, 31],
        [30, 30, 30, 30, 30, 30.5, 31, 31],
        last_row=[False, False, False, False, True, False, False, False])
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E']}
    result = simulate('T', bank, cal, cal[0], [cal[0]], lambda t: ranked[t],
                      budget=BUDGET, fees=ETF_FEE_BAND)
    forced = [t for t in result.trades if t['kind'] == 'forced_delist_close']
    assert len(forced) == 1
    assert forced[0]['code'] == 'C' and forced[0]['session'] == cal[4]
    assert forced[0]['raw_price'] == 30.5  # close, not open
    assert result.exec_stats.sells_forced_delist == 1


def test_engine_no_forced_exit_on_entry_day_t1():
    cal = weekdays(8)
    codes = _basic_codes(cal)
    # B's last_row flag lands on d1 = the entry session: T+1 forbids a
    # same-day forced exit, so the position is carried (marked to market).
    codes['B'] = flat_prices(
        'B', [20, 20, 20, 20, 20, 20, 20, 20],
        [20, 20.5, 20, 20, 20, 20, 20, 20],
        [20, 20, 20.5, 20, 20, 20, 20, 20],
        last_row=[False, True, False, False, False, False, False, False])
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E']}
    result = simulate('T', bank, cal, cal[0], [cal[0]], lambda t: ranked[t],
                      budget=BUDGET, fees=ETF_FEE_BAND)
    assert result.exec_stats.sells_forced_delist == 0
    # position carried to the window end (mark-to-market)
    assert any(fo['code'] == 'B' for fo in result.final_open)


def test_engine_all_gate_fail_liquidates_to_cash():
    cal = weekdays(8)
    feat = make_feat(_basic_codes(cal), cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C'], cal[4]: []}
    result = simulate('T', bank, cal, cal[0], [cal[0], cal[4]],
                      lambda t: ranked[t], budget=BUDGET, fees=ETF_FEE_BAND)
    # all three incumbents leave the empty TopN -> sold at d5 open
    sells = [t for t in result.trades if t['side'] == 'sell']
    assert len(sells) == 3 and all(t['session'] == cal[5] for t in sells)
    # final equity == pure cash: proceeds minus a 5 CNY fee per leg
    expected = (sum(t['notional'] - 5.0 for t in sells))
    assert result.equity[-1] == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# B1 benchmark
# --------------------------------------------------------------------------- #
def test_b1_equal_weight_full_rebalance_hand_check():
    cal = weekdays(6)
    codes = {
        'X': flat_prices('X', [10, 10, 11, 11, 12.1, 12.1],
                         [10, 10, 11, 11, 12, 12],
                         [10, 10, 10, 11, 11, 12]),
        'Y': flat_prices('Y', [20, 20, 22, 22, 20, 20],
                         [20, 20, 22, 21, 20, 20],
                         [20, 20, 20, 22, 21, 20]),
    }
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    pools = {cal[0]: [PoolRow('X', 0, 0, 0, True, True),
                      PoolRow('Y', 0, 0, 0, True, True)],
             cal[2]: [PoolRow('X', 0, 0, 0, True, True)]}
    result = simulate_b1(pools, bank, cal, cal[0], [cal[0], cal[2]],
                         total=200_000.0, fees=ETF_FEE_BAND)
    # period 1: legs X,Y each 100,000 budget at d1 open; exits at d3 open
    bx = max(100_000 * 0.0001, 5.0)
    ux = (100_000 - bx) / 10.0
    gx = ux * 11.0
    fx = max(gx * 0.0001, 5.0)
    by = max(100_000 * 0.0001, 5.0)
    uy = (100_000 - by) / 20.0
    gy = uy * 22.0
    fy = max(gy * 0.0001, 5.0)
    v_after_p1 = (gx - fx) + (gy - fy)
    # period 2: N=1, budget = v_after_p1, entry d3 open 11; the window ends
    # before the next signal so the position is mark-to-market carried
    b2_ = max(v_after_p1 * 0.0001, 5.0)
    u2 = (v_after_p1 - b2_) / 11.0
    assert result.equity[0] == pytest.approx(200_000.0)      # cash before entry
    assert result.equity[3] == pytest.approx(u2 * 11.0)      # entry-day mark
    assert result.equity[-1] == pytest.approx(u2 * 12.0)     # carried mark
    assert result.exec_stats.buys_filled == 3


# --------------------------------------------------------------------------- #
# B2 benchmark
# --------------------------------------------------------------------------- #
def test_b2_buy_hold_hand_check():
    cal = weekdays(6)
    codes = {'I': flat_prices('I', [100, 101, 102, 103, 104, 105],
                              [100, 101, 102, 103, 104, 105],
                              [100, 100, 101, 102, 103, 104])}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    out = simulate_b2('I', bank, cal, cal[0], cal[5], total=200_000.0,
                      fees=ETF_FEE_BAND)
    assert out['entry_raw'] == 100 and out['exit_raw'] == 105
    assert out['gross_total_return'] == pytest.approx(0.05)
    fee_b = max(200_000 * 0.0001, 5.0)
    units = (200_000 - fee_b) / 100.0
    fee_s = max(units * 105 * 0.0001, 5.0)
    assert out['net_total_return'] == pytest.approx((units * 105 - fee_s)
                                                    / 200_000 - 1.0)


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def test_cagr_and_max_drawdown():
    days = weekdays(5)
    values = [100, 110, 99, 105, 108]
    m = max_drawdown(days, values)
    assert m['max_drawdown'] == pytest.approx(99 / 110 - 1)
    years = (days[-1] - days[0]).days / 365.25
    assert cagr(values[0], values[-1], days[0], days[-1]) \
        == pytest.approx((108 / 100) ** (1 / years) - 1)


def test_year_returns_chaining():
    days = weekdays(10)
    values = [100] * 5 + [110] * 5
    yr = year_returns(days, values)
    assert yr[days[0].year] == pytest.approx(0.10)


def test_turnover_by_year():
    cal = weekdays(8)
    codes = _basic_codes(cal)
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D'], cal[4]: ['A', 'B', 'D', 'C']}
    result = simulate('T', bank, cal, cal[0], [cal[0], cal[4]],
                      lambda t: ranked[t], budget=BUDGET, fees=ETF_FEE_BAND)
    tv = turnover_by_year(result)
    y = cal[0].year
    assert tv[y]['buy_notional'] == pytest.approx(4 * BUDGET)
    assert tv[y]['sell_notional'] == pytest.approx(1 * 31.0 * 295 / 30.0)


def test_monthly_top_decile():
    days = weekdays(40)  # spans ~2 months
    values = list(range(40))
    out = monthly_top_decile(days, values)
    assert out['top_decile_share'] is not None
    assert 0 < out['top_decile_share'] <= 1


def test_concentration_boundary_attribution():
    cal = weekdays(10)
    codes = _basic_codes(cal)
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    # position held across the boundary (cal[5]): attribution marks at the
    # boundary closes; A closes are [10.2,10.8,11.2,11,11.5,12.2,12.1,12,..]
    pos = {'code': 'A', 'entry_session': 1, 'entry_date': cal[1],
           'budget': 300.0, 'units': 29.5, 'entry_adj': 10.0,
           'entry_raw': 10.0, 'buy_fee': 5.0, 'proceeds': None,
           'exit_session': 9, 'exit_date': cal[9], 'exit_adj': 12.0,
           'exit_raw': 12.0, 'sell_fee': 5.0, 'pnl': 29.5 * 12 - 5 - 300,
           'exit_kind': 'sell_at_open'}
    out = concentration([pos], [], bank, cal, cal[5], cal[7])
    assert out['total_pnl'] == pytest.approx(29.5 * (12.0 - 12.2))
    assert out['top1_share'] is None  # negative total: shares undefined


# --------------------------------------------------------------------------- #
# gates (frozen prereg thresholds)
# --------------------------------------------------------------------------- #
def _gate_metrics(dev_net=0.10, dev_excess=0.05, years=None, mdd=-0.10,
                  b1_mdd=-0.05, turnover=3.0, top1=0.30, top3=0.60,
                  rate=0.99):
    years = years or {str(y): 0.03 for y in range(2016, 2021)}
    return {
        'freq': 'monthly',
        'dev': {'net_cagr': dev_net, 'b1_net_cagr': dev_net - dev_excess,
                'excess_by_year': years, 'max_drawdown': mdd,
                'b1_max_drawdown': b1_mdd,
                'max_one_side_turnover': turnover,
                'concentration': {'top1_share': top1, 'top3_share': top3,
                                  'total_pnl': 100.0},
                'execution_rate': rate},
    }


def test_dev_gate_all_pass():
    m = _gate_metrics()
    b1 = {'net_cagr': 0.05, 'max_drawdown': -0.15}  # B1 deeper than strategy
    verdict = evaluate_dev_gate(m, b1, 0.04, freq='monthly')
    assert verdict['dev_pass'] is True
    assert all(v for k, v in verdict.items()
               if k.startswith(('1', '2', '3', '4', '5', '6', '7', '8'))
               and isinstance(v, bool))


def test_dev_gate_fails_each_threshold():
    b1 = {'net_cagr': 0.05, 'max_drawdown': -0.15}
    # excess below 2pp (B1 CAGR matched so only check 2 can fail)
    assert evaluate_dev_gate(_gate_metrics(dev_excess=0.015),
                             {'net_cagr': 0.085, 'max_drawdown': -0.15}, 0.0,
                             freq='monthly')['dev_pass'] is False
    # only 3 positive years
    years = {str(y): (0.01 if y < 2019 else -0.01) for y in range(2016, 2021)}
    assert evaluate_dev_gate(_gate_metrics(years=years), b1, 0.0,
                             freq='monthly')['dev_pass'] is False
    # drawdown deeper than B1's (B1 given the shallower -0.05)
    assert evaluate_dev_gate(_gate_metrics(mdd=-0.15),
                             {'net_cagr': 0.05, 'max_drawdown': -0.05}, 0.0,
                             freq='monthly')['dev_pass'] is False
    # drawdown beyond the absolute 20% budget
    assert evaluate_dev_gate(_gate_metrics(mdd=-0.25),
                             {'net_cagr': 0.05, 'max_drawdown': -0.30}, 0.0,
                             freq='monthly')['dev_pass'] is False
    # monthly turnover above 6.0 (cap by frequency)
    assert evaluate_dev_gate(_gate_metrics(turnover=7.0), b1, 0.0,
                             freq='monthly')['dev_pass'] is False
    assert evaluate_dev_gate(_gate_metrics(turnover=7.0), b1, 0.0,
                             freq='weekly')['5_turnover_le_cap'] is True
    # concentration top1 > 40%
    assert evaluate_dev_gate(_gate_metrics(top1=0.45), b1, 0.0,
                             freq='monthly')['dev_pass'] is False
    # below random mean + 1pp
    assert evaluate_dev_gate(_gate_metrics(), b1, 0.10,
                             freq='monthly')['dev_pass'] is False
    # execution below 95%
    assert evaluate_dev_gate(_gate_metrics(rate=0.90), b1, 0.0,
                             freq='monthly')['dev_pass'] is False


def test_val_and_test_gates():
    m = {
        'freq': 'weekly',
        'val': {'net_cagr': 0.08, 'b1_net_cagr': 0.05,
                'excess_by_year': {'2021': 0.02, '2022': 0.04},
                'max_drawdown': -0.15, 'max_one_side_turnover': 8.0,
                'concentration': {'top1_share': 0.30, 'top3_share': 0.60}},
        'test': {'net_cagr': 0.03, 'b1_net_cagr': 0.04,
                 'max_drawdown': -0.10},
    }
    val = evaluate_val_gate(m, {'net_cagr': 0.05})
    assert val['val_pass'] is True
    test = evaluate_test(m, {'net_cagr': 0.04})
    assert test['test_pass'] is False  # excess -1pp < 0
    m['test']['net_cagr'] = 0.05
    assert evaluate_test(m, {'net_cagr': 0.04})['test_pass'] is True


# --------------------------------------------------------------------------- #
# fee convention
# --------------------------------------------------------------------------- #
def test_fee_band_convention():
    band = fee_band_for((ETF_FEE_BAND,), D(2020, 6, 1))
    assert band.commission_pct == 0.0001
    assert band.commission_min == 5.0
    assert band.stamp_sell_pct == 0.0
    gross = fee_band_for((GROSS_FEE_BAND,), D(2020, 6, 1))
    assert gross.commission_pct == 0.0 and gross.commission_min == 0.0
