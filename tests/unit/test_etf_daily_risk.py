"""Unit tests for the P2-R8 daily risk overlay (synthetic data only).

Each test pins one registered semantic from
``configs/experiments/p2r8-daily-risk.json``: the per-session mechanism
states (SMA incl. t, T20c2 two-day confirm, rolling-peak window boundary,
PDD own running peak, X1 OR-composition), trade-only-on-state-change, the
monthly collision merged into ONE combined execution, postponement with the
latest target winning, never-negative cash with the commission-minimum skip,
the B1(m) daily path with idle-cash carry, the C01 anchor equivalence with
the R7 engine, and net/gross trade parity.  Synthetic values are never
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
    constant_risk_fn,
    pdd_risk_fn,
    rolling_dd_state,
    simulate_b1_exposure,
    simulate_daily_risk,
    simulate_exposure,
    sma_trend_state,
    t20c2_state,
    turnover_by_year,
    window_execution_rate,
    x1_compose,
)

D = date


def weekdays(n: int, start: D = D(2016, 1, 4)) -> list[D]:
    days, day = [], start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def make_feat(codes: dict[str, dict[str, list]], calendar: list[D]) -> pl.DataFrame:
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
                'r20': 0.0, 'r60': 0.0, 'r120': 0.0, 'sma120': 0.0,
                'eligible': cols.get('eligible', [True] * len(calendar))[i],
                'gate_ok': True})
    frame = pl.DataFrame(rows)
    return frame.with_columns(
        *(pl.col(c).cast(pl.Float64) for c in
          ('open', 'close', 'pre_close', 'amount', 'adj_open', 'adj_close',
           'r20', 'r60', 'r120', 'sma120')))


def flat_prices(code: str, opens: list[float], closes: list[float],
                pre_closes: list[float]) -> dict:
    return {'open': opens, 'close': closes, 'pre_close': pre_closes}


def scripted_e(path: dict[D, float]):
    return lambda d, e: path[d]  # noqa: E731


def index_frame(closes: list[float], calendar: list[D]) -> pl.DataFrame:
    return pl.DataFrame({'trade_date': calendar,
                         'close': closes}).sort('trade_date')


# --------------------------------------------------------------------------- #
# per-session mechanism states
# --------------------------------------------------------------------------- #
def test_sma_trend_state_includes_t_and_cross_day():
    cal = weekdays(8)
    frame = index_frame([10.0] * 4 + [11.0] * 4, cal)
    st = sma_trend_state(frame, cal, 3)
    assert st[cal[0]] is False and st[cal[1]] is False   # SMA unavailable
    assert st[cal[2]] is False                # close 10 not > SMA(10,10,10)=10
    assert st[cal[3]] is False
    assert st[cal[4]] is True                 # 11 > (10+10+11)/3 = 10.33
    assert st[cal[5]] is True                 # 11 > (10+11+11)/3 = 10.67
    assert st[cal[6]] is False and st[cal[7]] is False  # 11 not > SMA 11


def test_t20c2_two_day_confirm_fast_out_slow_in():
    cal = weekdays(8)
    closes = [10.0, 10.0, 10.0, 11.0, 9.0, 11.0, 11.0, 11.0]
    st = t20c2_state(index_frame(closes, cal), cal, 3)
    assert st[cal[2]] is False                       # SMA unavailable at i<2
    assert st[cal[3]] is False   # one day above only: slow-in keeps off
    assert st[cal[4]] is False   # one day below: fast-out
    assert st[cal[5]] is False   # only one confirmed day again
    assert st[cal[6]] is True    # two consecutive sessions above -> on
    assert st[cal[7]] is False   # close 11 not > SMA(11,11,11)=11: fast-out


def test_rolling_dd_state_window_boundary_and_threshold():
    cal = weekdays(6)
    closes = [10.0, 12.0, 11.0, 13.0, 10.0, 13.1]
    st = rolling_dd_state(index_frame(closes, cal), cal, 3, 0.10)
    assert st[cal[0]] is False and st[cal[1]] is False   # window not formed
    assert st[cal[2]] is True    # 11 >= 12 x 0.9 = 10.8 (window exactly 3)
    assert st[cal[3]] is True    # 13 >= 13 x 0.9
    assert st[cal[4]] is False   # 10 < 13 x 0.9 = 11.7 -> risk-off trigger
    assert st[cal[5]] is True    # 13.1 >= 11.7 (peak stays 13)


def test_x1_composition_is_or_of_risk_off_conditions():
    d0, d1, d2 = weekdays(3)
    t200 = {d0: True, d1: False, d2: True}
    d252 = {d0: True, d1: True, d2: False}
    x1 = x1_compose(t200, d252)
    assert x1 == {d0: True, d1: False, d2: False}   # on iff BOTH on


def test_pdd_risk_fn_own_running_peak_never_resets():
    fn = pdd_risk_fn(0.10)
    d = D(2016, 1, 4)
    assert fn(d, 100.0) == 0.90       # first session: zero drawdown -> e_on
    assert fn(d, 90.0) == 0.90        # exactly at the boundary is on
    assert fn(d, 89.9) == 0.40
    assert fn(d, 105.0) == 0.90       # new peak 105
    assert fn(d, 94.0) == 0.40        # 94 < 105 x 0.9 = 94.5
    fresh = pdd_risk_fn(0.10)         # fresh instance, own peak
    assert fresh(d, 60.0) == 0.90


# --------------------------------------------------------------------------- #
# engine: trade only on state change; C01 anchor equivalence
# --------------------------------------------------------------------------- #
def test_c01_constant_risk_matches_r7_engine_bit_exact():
    cal = weekdays(8)
    codes = {c: flat_prices(c, [10.0] * 8, [10.0] * 8, [10.0] * 8)
             for c in ('A', 'B', 'C')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    signals = [cal[0], cal[4]]
    ranked = {cal[0]: ['A', 'B', 'C'], cal[4]: ['B', 'C', 'A']}
    r8 = simulate_daily_risk('C01', bank, cal, cal[0], signals,
                             lambda t: ranked[t], constant_risk_fn(0.75),
                             n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    r7 = simulate_exposure('C01', bank, cal, cal[0], signals,
                           lambda t: ranked[t], {x: 0.75 for x in signals},
                           n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    assert r8.sessions == r7.sessions
    assert r8.equity == r7.equity            # bit-exact float equality
    seq = lambda r: [(t['session'], t['code'], t['side'], t['kind'])  # noqa: E731
                     for t in r.trades]
    assert seq(r8) == seq(r7)
    assert r8.exec_stats.risk_legs_planned == 0   # zero risk trades
    assert all(t['kind'] not in ('retarget_buy', 'retarget_sell')
               for t in r8.trades)


def test_retarget_only_on_state_change_scales_held_legs():
    cal = weekdays(8)
    codes = {c: flat_prices(c, [10.0] * 8, [10.0] * 8, [10.0] * 8)
             for c in ('A', 'B', 'C')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    path = {x: 0.75 for x in cal}
    path[cal[2]] = 0.30       # down-scale after the entry
    path[cal[3]] = 0.30
    path[cal[4]] = 0.75       # up-scale again
    result = simulate_daily_risk(
        'T', bank, cal, cal[0], [cal[0]], lambda t: ['A', 'B', 'C'],
        scripted_e(path), n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    sells = [t for t in result.trades if t['kind'] == 'retarget_sell']
    buys = [t for t in result.trades if t['kind'] == 'retarget_buy']
    assert all(t['session'] == cal[3] for t in sells) and len(sells) == 3
    # target = 0.10 x 1185 = 118.5; value 295 -> sell 176.5 (fee min 5)
    assert all(t['notional'] == pytest.approx(176.5) for t in sells)
    assert all(t['units'] == pytest.approx(17.65) for t in sells)
    assert all(t['session'] == cal[5] for t in buys) and len(buys) == 3
    # cash after the sells = 300 + 3 x 171.5 = 814.5; equity(cal[4] close) =
    # 814.5 + 3 x 118.5 = 1170 -> target 0.25 x 1170 = 292.5; value 118.5
    # -> buy 174 (fee 5)
    assert all(t['notional'] == pytest.approx(174.0) for t in buys)
    assert all(t['units'] == pytest.approx(16.9) for t in buys)
    assert result.equity[5] == pytest.approx(292.5 + 3 * 28.75 * 10.0)
    st = result.exec_stats
    assert (st.risk_legs_planned, st.risk_buys_filled,
            st.risk_sells_filled) == (6, 3, 3)
    assert result.max_negative_cash == pytest.approx(0.0)
    # risk buys count toward the buy-side turnover books (gate 5, no exemption)
    book = turnover_by_year(result)[2016]
    assert book['buy_notional'] == pytest.approx(900.0 + 3 * 174.0)
    # gate-8 leg log carries the risk legs with resolved outcomes
    risk_legs = [l for l in result.leg_log if l['risk']]
    assert len(risk_legs) == 6
    assert all(l['outcome'] == 'filled' for l in risk_legs)


def test_monthly_collision_merges_into_one_combined_execution():
    cal = weekdays(10)
    codes = {c: flat_prices(c, [10.0] * 10, [10.0] * 10, [10.0] * 10)
             for c in ('A', 'B', 'C', 'D')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    path = {x: 0.75 for x in cal}
    for x in cal[3:]:
        path[x] = 0.30        # state changes exactly on the signal day cal[3]
    result = simulate_daily_risk(
        'T', bank, cal, cal[0], [cal[0], cal[3]],
        lambda t: {cal[0]: ['A', 'B', 'C'], cal[3]: ['D', 'B', 'C']}[t],
        scripted_e(path), n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    day = cal[4]
    kinds = [(t['code'], t['side'], t['kind'])
             for t in result.trades if t['session'] == day]
    assert ('A', 'sell', 'sell_at_open') in kinds          # leaver
    assert ('D', 'buy', 'open') in kinds                   # entrant at E_t
    assert sum(1 for c, s, k in kinds
               if c in ('B', 'C') and k == 'retarget_sell') == 2
    assert len(kinds) == 4
    assert not [t for t in result.trades
                if t['session'] > day]                     # ONE execution only
    d_buy = next(t for t in result.trades
                 if t['code'] == 'D' and t['side'] == 'buy')
    assert d_buy['notional'] == pytest.approx(118.5)   # 0.10 x 1185
    keep = [t for t in result.trades if t['kind'] == 'retarget_sell']
    assert all(t['notional'] == pytest.approx(176.5) for t in keep)
    legs = [l for l in result.leg_log if l['plan_date'] == cal[3]]
    assert {(l['side'], l['outcome']) for l in legs} == {
        ('sell', 'sell_at_open'), ('buy', 'filled'), ('rescale', 'filled')}
    assert result.max_negative_cash == pytest.approx(0.0)


def test_retarget_postponed_then_latest_target_wins():
    cal = weekdays(6)
    codes = {'A': flat_prices('A', [10.0, 10.0, 10.0, 8.0, 8.0, 8.0],
                              [10.0, 10.0, 10.0, 8.0, 8.0, 8.0],
                              [10.0, 10.0, 10.0, 10.0, 8.0, 8.0])}
    feat = make_feat(codes, cal).filter(
        ~((pl.col('ts_code') == 'A') & (pl.col('trade_date') == cal[2])))
    bank = CodeDataBank(feat, cal)
    path = {x: 1.0 for x in cal}
    path[cal[1]] = 0.10       # change #1: down-scale plan for cal[2]
    path[cal[2]] = 1.0        # change #2 at cal[2] close: LATEST target wins
    result = simulate_daily_risk(
        'T', bank, cal, cal[0], [cal[0]], lambda t: ['A'],
        scripted_e(path), n_slots=1, fees=ETF_FEE_BAND, total=1000.0)
    assert result.exec_stats.risk_suspended == 1   # A has no quote at cal[2]
    assert not [t for t in result.trades if t['session'] == cal[2]]
    buys = [t for t in result.trades if t['kind'] == 'retarget_buy']
    assert len(buys) == 1 and buys[0]['session'] == cal[3]
    # equity(cal[1] close) = 995; equity(cal[2] close) = 995 (marked at 10);
    # latest target = 0.25 x 995 = 248.75; value at cal[3] open = 196
    assert buys[0]['notional'] == pytest.approx(52.75)
    outcomes = {l['outcome'] for l in result.leg_log if l['risk']}
    assert outcomes == {'superseded_latest', 'filled'}
    pos = result.final_open[0]
    assert pos['units'] == pytest.approx(24.5 + 47.75 / 8.0)
    assert pos['budget'] == pytest.approx(250.0 + 52.75)
    assert result.max_negative_cash == pytest.approx(0.0)


def test_retarget_cash_never_negative_and_fee_min_skips():
    cal = weekdays(6)
    codes = {c: flat_prices(c, [10.0] * 6, [10.0] * 6, [10.0] * 6)
             for c in ('A', 'B', 'C', 'D')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    path = {x: 1.0 for x in cal}
    path[cal[1]] = 0.999      # tiny down-scale: sell gross 0.095 <= fee min 5
    path[cal[2]] = 1.0        # back on: delta exactly 0 -> no trade
    path[cal[3]] = 0.90       # real down-scale: sell 9.5 gross (executes)
    path[cal[4]] = 1.0        # up-scale with almost no cash -> cash-capped
    result = simulate_daily_risk(
        'T', bank, cal, cal[0], [cal[0]],
        lambda t: ['A', 'B', 'C', 'D'], scripted_e(path), n_slots=4,
        fees=ETF_FEE_BAND, total=400.0)
    # cal[1]: 4 legs of 100 (units 9.5, value 95 after fees), cash 0;
    # target 0.24975 x 380 = 94.905 -> sell 0.0095 units = gross 0.095; the
    # 5 CNY minimum would make proceeds negative and overdraw the pool -> skip
    assert not [t for t in result.trades if t['session'] == cal[2]]
    assert result.exec_stats.risk_sells_feemin_skipped == 4
    # cal[3]: delta exactly 0 (target 95 == value 95) -> no trade, filled
    assert not [t for t in result.trades if t['session'] == cal[3]]
    # cal[4]: target 0.225 x 380 = 85.5 -> sell 0.95 units (gross 9.5 > 5)
    sells = [t for t in result.trades if t['kind'] == 'retarget_sell']
    assert len(sells) == 4
    assert all(t['session'] == cal[4] for t in sells)
    assert all(t['notional'] == pytest.approx(9.5) for t in sells)
    assert result.max_negative_cash == pytest.approx(0.0)
    # cal[5]: target 0.25 x 360 = 90 -> buy 4.5 but cash 18 -> budget =
    # min(4.5, 18) = 4.5 <= commission min -> cash-capped skip
    assert [t for t in result.trades if t['kind'] == 'retarget_buy'] == []
    assert result.exec_stats.risk_buys_cash_capped == 4
    assert result.equity[-1] == pytest.approx(18.0 + 4 * 85.5)
    risk_legs = [l for l in result.leg_log if l['risk']]
    outcomes = [l['outcome'] for l in risk_legs]
    assert outcomes.count('cash_capped') == 8
    assert outcomes.count('filled') == 8


def test_net_gross_parity_with_risk_overlay():
    cal = weekdays(8)
    codes = {c: flat_prices(c, [10.0] * 8, [10.0] * 8, [10.0] * 8)
             for c in ('A', 'B', 'C')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    path = {x: 0.75 for x in cal}
    path[cal[2]] = 0.30
    path[cal[3]] = 0.30
    path[cal[4]] = 0.75
    net = simulate_daily_risk('T', bank, cal, cal[0], [cal[0]],
                              lambda t: ['A', 'B', 'C'], scripted_e(path),
                              n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    gross = simulate_daily_risk('T-g', bank, cal, cal[0], [cal[0]],
                                lambda t: ['A', 'B', 'C'], scripted_e(path),
                                n_slots=3, fees=GROSS_FEE_BAND, total=1200.0)
    seq = lambda r: [(t['session'], t['code'], t['side'], t['kind'])  # noqa: E731
                     for t in r.trades]
    assert seq(net) == seq(gross)
    assert gross.equity[-1] > net.equity[-1]   # fees are the only difference


# --------------------------------------------------------------------------- #
# B1(m) daily path
# --------------------------------------------------------------------------- #
def test_b1_daily_rescale_with_idle_cash_carry():
    cal = weekdays(6)
    codes = {'X': flat_prices('X', [10.0] * 6, [10.0] * 6, [10.0] * 6)}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    pools = {cal[0]: [PoolRow('X', 0, 0, 0, True, True)],
             cal[3]: [PoolRow('X', 0, 0, 0, True, True)]}
    path = {x: 1.0 for x in cal}
    path[cal[2]] = 0.20
    path[cal[3]] = 0.20
    path[cal[4]] = 0.20
    path[cal[5]] = 0.20
    result = simulate_b1_exposure(
        pools, bank, cal, cal[0], [cal[0], cal[3]], {}, total=200_000.0,
        fees=ETF_FEE_BAND, config_id='B1-T', risk_fn=scripted_e(path))
    # si1: 50,000 at 10 (fee 5) -> 4,999.5 units; idle 150,000
    assert result.equity[1] == pytest.approx(150_000.0 + 49_995.0)
    # si2 close E=0.20 -> target 0.2 x 199,995 = 39,999; si3 open sells
    # 999.6 units (gross 9,996, fee 5) into the IDLE pool (carry)
    assert result.equity[3] == pytest.approx(159_991.0 + 39_999.0)
    # si4: exits at the open join idle; re-entry 0.2 x 199,985 = 39,997
    assert result.equity[4] == pytest.approx(159_988.0 + 39_992.0)
    assert result.equity[5] == pytest.approx(result.equity[4])
    acc = result.extra['turnover_acc']
    assert acc[2016]['buy_notional'] == pytest.approx(50_000.0 + 39_997.0)
    assert acc[2016]['sell_notional'] == pytest.approx(9_996.0 + 39_999.0)


def test_b1_constant_risk_fn_matches_r7_engine_bit_exact():
    cal = weekdays(6)
    codes = {'X': flat_prices('X', [10.0] * 6, [10.0] * 6, [10.0] * 6),
             'Y': flat_prices('Y', [20.0] * 6, [20.0] * 6, [20.0] * 6)}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    pools = {cal[0]: [PoolRow('X', 0, 0, 0, True, True),
                      PoolRow('Y', 0, 0, 0, True, True)],
             cal[3]: [PoolRow('X', 0, 0, 0, True, True)]}
    with_fn = simulate_b1_exposure(
        pools, bank, cal, cal[0], [cal[0], cal[3]], {}, total=200_000.0,
        fees=ETF_FEE_BAND, config_id='B1-F', risk_fn=constant_risk_fn(0.75))
    without = simulate_b1_exposure(
        pools, bank, cal, cal[0], [cal[0], cal[3]],
        {cal[0]: 0.75, cal[3]: 0.75}, total=200_000.0, fees=ETF_FEE_BAND,
        config_id='B1-F')
    assert with_fn.equity == without.equity   # bit-exact
    assert with_fn.sessions == without.sessions


# --------------------------------------------------------------------------- #
# gate-8 with risk legs; section-0 preanalysis
# --------------------------------------------------------------------------- #
def test_gate8_window_counts_risk_and_monthly_legs():
    cal = weekdays(6)
    codes = {'A': flat_prices('A', [10.0, 10.0, 10.0, 8.0, 8.0, 8.0],
                              [10.0, 10.0, 10.0, 8.0, 8.0, 8.0],
                              [10.0, 10.0, 10.0, 10.0, 8.0, 8.0])}
    feat = make_feat(codes, cal).filter(
        ~((pl.col('ts_code') == 'A') & (pl.col('trade_date') == cal[2])))
    bank = CodeDataBank(feat, cal)
    path = {x: 1.0 for x in cal}
    path[cal[1]] = 0.10
    path[cal[2]] = 1.0
    result = simulate_daily_risk(
        'T', bank, cal, cal[0], [cal[0]], lambda t: ['A'],
        scripted_e(path), n_slots=1, fees=ETF_FEE_BAND, total=1000.0)
    rate = window_execution_rate(result.leg_log, cal[0], cal[-1])
    # planned: entry buy + superseded retarget + latest retarget = 3;
    # executed: entry fill + latest fill = 2 (superseded is NOT executed)
    assert rate['legs_planned'] == 3
    assert rate['legs_executed'] == 2
    assert rate['execution_rate'] == pytest.approx(2.0 / 3.0)


def test_preanalysis_sect0_index_only_statistics():
    n = 300
    cal = weekdays(n)
    closes = [100.0 + 0.1 * i for i in range(200)]        # steady uptrend
    closes += [119.0 - 3.0 * i for i in range(100)]       # sharp crash
    frame = index_frame(closes, cal)
    pre = er.preanalysis_sect0(
        frame, dev_start=cal[10], dev_end=cal[-1],
        stress_start=cal[0], stress_end=cal[-1])
    assert set(pre['mechanisms']) == {'T200', 'T60', 'T20c2', 'D252-10',
                                      'D252-15', 'D60-8', 'X1'}
    t60 = pre['mechanisms']['T60']
    assert t60['trigger_count'] >= 1
    assert t60['risk_off_share'] > 0
    dec = t60['depth_from_local_peak_at_trigger']
    assert dec['p50'] >= 0 and dec['max'] >= dec['p90'] >= dec['p50'] >= 0
    assert dec['n'] >= 1
    # the worst 5-session decline must be at least as negative as any
    # single session inside it (compounding)
    s1 = pre['index_stress']['worst_single_session']
    s5 = pre['index_stress']['worst_5_session']
    assert s1['ret'] < 0 and s5['ret'] <= s1['ret']
    worst = min(closes[i] / closes[i - 1] - 1.0 for i in range(200, n))
    assert s1['ret'] == pytest.approx(worst)


def test_exposures_from_state_mapping():
    d0, d1 = weekdays(2)
    expo = er.exposures_from_state({d0: True, d1: False}, 0.90, 0.20)
    assert expo == {d0: 0.90, d1: 0.20}
