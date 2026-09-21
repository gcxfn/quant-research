"""Unit tests for the P2-R7 dynamic-exposure extension (synthetic data only).

Each test pins one registered semantic from
``configs/experiments/p2r7-etf-exposure.json``: the three exposure mechanisms
(FIX constant / VOLT clip boundaries / TREND SMA200 cross-day), the per-leg
min(exposure/N, 25%) sizing, the never-negative cash pool, the N=5
concentration disclosure, the mechanism-matched B1(m) sizing, and the
dev-window execution rate.  Synthetic values are never profitability evidence.
"""
from __future__ import annotations

import statistics
from datetime import date, timedelta

import polars as pl
import pytest

from quant.research import etf_rotation as er  # noqa: E402
from quant.research.etf_rotation import (  # noqa: E402
    ETF_FEE_BAND,
    GROSS_FEE_BAND,
    CodeDataBank,
    PoolRow,
    concentration,
    group_pools,
    leg_frac,
    pool_daily_returns,
    simulate_b1_exposure,
    simulate_exposure,
    trend_exposures,
    volt_exposures,
    window_execution_rate,
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
    """Hand-built feature frame (same convention as the P2-R6 tests)."""
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
# registered sizing: per-leg min(exposure / N, 25%)
# --------------------------------------------------------------------------- #
def test_leg_frac_min_rule():
    assert leg_frac(0.75, 3) == pytest.approx(0.25)   # FIX x Top3
    assert leg_frac(0.75, 5) == pytest.approx(0.15)   # FIX x Top5
    assert leg_frac(1.00, 3) == pytest.approx(0.25)   # 25% cap binds
    assert leg_frac(0.60, 3) == pytest.approx(0.20)
    assert leg_frac(0.40, 5) == pytest.approx(0.08)   # TREND floor x Top5


def test_fix_exposures_constant():
    days = weekdays(5)
    out = er.fix_exposures(days, 0.75)
    assert out == {d: 0.75 for d in days}


# --------------------------------------------------------------------------- #
# VOLT: clip(0.15 / vol60, 0.40, 1.00) with registered fallbacks
# --------------------------------------------------------------------------- #
def _volt_kwargs():
    return dict(target_vol=0.15, clip_min=0.40, clip_max=1.00, window=60,
                sessions_per_year=244)


def test_volt_exposures_mid_and_clip_bounds():
    cal = weekdays(70)
    sig = [cal[65]]
    # alternating +/-1%: the registered window is the 60 calendar sessions
    # ending at t (cal[6:66]); sessions without pool returns are skipped
    tail = {d: 0.01 if i % 2 == 0 else -0.01
            for i, d in enumerate(cal[8:70])}
    expo = volt_exposures(cal, sig, tail, **_volt_kwargs())
    window_vals = [tail[d] for d in cal[6:66] if d in tail]
    ann = statistics.stdev(window_vals) * 244 ** 0.5
    assert len(window_vals) == 58
    assert expo[sig[0]] == pytest.approx(min(1.0, max(0.40, 0.15 / ann)))
    assert 0.40 < expo[sig[0]] < 1.0
    # tiny vol -> upper clip
    tiny = {d: 0.0001 if i % 2 == 0 else -0.0001
            for i, d in enumerate(cal[8:70])}
    assert volt_exposures(cal, sig, tiny, **_volt_kwargs())[sig[0]] == 1.00
    # huge vol -> lower clip
    huge = {d: 0.10 if i % 2 == 0 else -0.10
            for i, d in enumerate(cal[8:70])}
    assert volt_exposures(cal, sig, huge, **_volt_kwargs())[sig[0]] == 0.40


def test_volt_exposures_fallbacks():
    cal = weekdays(70)
    sig = [cal[65]]
    # fewer than 2 pool returns in the window -> expanding std over all <= t
    sparse = {cal[60]: 0.001, cal[61]: -0.001, cal[62]: 0.001,
              cal[63]: -0.001, cal[64]: 0.001}
    expo = volt_exposures(cal, sig, sparse, **_volt_kwargs())
    ann = statistics.stdev(list(sparse.values())) * 244 ** 0.5
    assert expo[sig[0]] == pytest.approx(min(1.0, max(0.40, 0.15 / ann)))
    # no pool returns at all -> registered defensive floor
    assert volt_exposures(cal, sig, {}, **_volt_kwargs())[sig[0]] == 0.40
    # exactly-zero vol takes the formula limit clip_max (defensive; never
    # observed in real data)
    flat = {d: 0.005 for d in cal[8:70]}
    assert volt_exposures(cal, sig, flat, **_volt_kwargs())[sig[0]] == 1.00


def test_pool_daily_returns_cross_sectional_mean():
    cal = weekdays(4)
    codes = {
        'A': flat_prices('A', [10, 11, 12, 12], [10, 11, 12, 12],
                         [10, 10, 11, 12]),
        # B suspended on day 1 (row dropped): first own row is day 2
        'B': flat_prices('B', [None, 20, 22, 21], [None, 20, 22, 21],
                         [None, 20, 20, 22]),
    }
    feat = make_feat(codes, cal)
    ret = pool_daily_returns(feat)
    assert ret[cal[1]] == pytest.approx(0.10)          # A only (B first own row)
    assert ret[cal[2]] == pytest.approx(               # B now contributes
        ((12.0 / 11.0 - 1.0) + (22.0 / 20.0 - 1.0)) / 2.0)
    assert ret[cal[3]] == pytest.approx(
        ((12.0 / 12.0 - 1.0) + (21.0 / 22.0 - 1.0)) / 2.0)


# --------------------------------------------------------------------------- #
# TREND: 000300.SH close vs SMA200 (cross-day boundary, inclusive of t)
# --------------------------------------------------------------------------- #
def test_trend_exposures_sma200_cross_day_and_asof():
    cal = weekdays(205)
    closes = [100.0] * 200 + [101.0] * 5
    frame = pl.DataFrame({'trade_date': cal, 'close': closes}).sort('trade_date')
    sig = [cal[150], cal[199], cal[200], cal[204]]
    expo = trend_exposures(frame, sig, sma_sessions=200, level_on=0.90,
                           level_off=0.40)
    assert expo[cal[150]] == 0.40                       # SMA unavailable
    assert expo[cal[199]] == 0.40                       # close 100 not > SMA 100
    assert expo[cal[200]] == 0.90                       # 101 > (199*100+101)/200
    assert expo[cal[204]] == 0.90
    # the t session close is INCLUSIVE in the SMA window
    sma204 = (195 * 100.0 + 5 * 101.0) / 200.0
    assert sma204 == pytest.approx(100.025)
    # asof: a non-session signal day takes the last index row <= t
    off_cal = cal[198] + timedelta(days=1)  # lands on the next calendar day
    assert off_cal not in cal or off_cal == cal[199]
    expo2 = trend_exposures(frame, [off_cal], sma_sessions=200, level_on=0.90,
                            level_off=0.40)
    assert expo2[off_cal] == expo.get(off_cal, expo2[off_cal])


# --------------------------------------------------------------------------- #
# engine: sizing, signal-close equity mark, cash never negative
# --------------------------------------------------------------------------- #
def test_exposure_engine_entry_budget_and_next_open():
    cal = weekdays(8)
    codes = {
        'A': flat_prices('A', [10, 10.5, 11, 11, 11, 12, 12, 12],
                         [10.2, 10.8, 11.2, 11, 11.5, 12.2, 12.1, 12],
                         [10, 10.2, 10.8, 11.2, 11, 11.5, 12.2, 12.1]),
        'B': flat_prices('B', [20] * 8, [20] * 8, [20] * 8),
        'C': flat_prices('C', [30] * 8, [30] * 8, [30] * 8),
    }
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    result = simulate_exposure(
        'T', bank, cal, cal[0], [cal[0]], lambda t: ['A', 'B', 'C'],
        {cal[0]: 0.75}, n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    buys = [t for t in result.trades if t['side'] == 'buy']
    assert len(buys) == 3
    assert all(t['session'] == cal[1] for t in buys)   # next open
    assert all(t['notional'] == pytest.approx(300.0) for t in buys)
    a = next(t for t in buys if t['code'] == 'A')
    assert a['fee'] == 5.0 and a['units'] == pytest.approx(295.0 / 10.5)
    assert result.equity[0] == pytest.approx(1200.0)   # cash before entry
    assert result.max_negative_cash == pytest.approx(0.0)


def test_exposure_engine_budget_uses_signal_close_equity():
    cal = weekdays(6)
    codes = {
        'A': flat_prices('A', [10, 10, 20, 20, 20, 20],
                         [10, 20, 20, 20, 20, 20],
                         [10, 10, 20, 20, 20, 20]),
        'B': flat_prices('B', [10] * 6, [10] * 6, [10] * 6),
    }
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B'], cal[2]: ['B', 'A']}
    result = simulate_exposure(
        'T', bank, cal, cal[0], [cal[0], cal[2]], lambda t: ranked[t],
        {cal[0]: 1.0, cal[2]: 1.0}, n_slots=1, fees=ETF_FEE_BAND,
        total=1000.0)
    # d0: leg = min(1.0/1, 0.25) x 1000 = 250, buy at d1 open 10, fee 5
    a = next(t for t in result.trades if t['side'] == 'buy'
             and t['code'] == 'A')
    assert a['notional'] == pytest.approx(250.0)
    units_a = (250.0 - 5.0) / 10.0
    # d2 close equity = cash 750 + 24.5 x 20 = 1240 -> leg target 310
    b = next(t for t in result.trades if t['side'] == 'buy'
             and t['code'] == 'B')
    assert b['notional'] == pytest.approx(0.25 * (750.0 + units_a * 20.0))
    # A sold at the d3 open 20
    sell_a = next(t for t in result.trades if t['side'] == 'sell')
    assert sell_a['raw_price'] == 20.0
    assert result.max_negative_cash == pytest.approx(0.0)


def test_exposure_engine_cash_cap_and_fee_min_skip():
    """Crushed leavers fund less than the new leg targets: budgets are capped
    by available cash, and a budget at/below the commission minimum is a
    rule-compliant cash slot.  The cash pool never goes negative."""
    cal = weekdays(10)
    codes = {}
    for c in ('C', 'D', 'E', 'F'):
        codes[c] = flat_prices(c, [10] * 10, [10] * 10, [10] * 10)
    a_opens = [10, 10, 10, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    codes['A'] = flat_prices('A', a_opens, a_opens,
                             [10, 10, 10, 10, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    b_opens = [10, 10, 10, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
    codes['B'] = flat_prices('B', b_opens, b_opens,
                             [10, 10, 10, 10, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0])
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E', 'F'],
              cal[4]: ['C', 'D', 'E', 'F']}
    result = simulate_exposure(
        'T', bank, cal, cal[0], [cal[0], cal[4]], lambda t: ranked[t],
        {cal[0]: 1.0, cal[4]: 1.0}, n_slots=4, fees=ETF_FEE_BAND,
        total=1000.0)
    # d1: four legs of 250 (fee 5 each) -> cash 0
    # d4 close equity = 24.5 x (1 + 5 + 10 + 10) = 637 -> target 159.25
    # d5: sell A (19.5) + B (117.5) -> cash 137 < target
    buys = {t['code']: t for t in result.trades
            if t['side'] == 'buy' and t['session'] == cal[5]}
    assert set(buys) == {'E'}                       # F skipped
    assert buys['E']['notional'] == pytest.approx(137.0)
    assert result.exec_stats.buys_cash_capped == 1
    assert result.max_negative_cash == pytest.approx(0.0)
    d4_legs = [l for l in result.leg_log if l['plan_date'] == cal[4]]
    outcomes = {(l['side'], l['outcome']) for l in d4_legs}
    assert outcomes == {('sell', 'sell_at_open'), ('buy', 'filled'),
                        ('buy', 'cash_capped')}


def test_exposure_engine_fee_min_skip_from_tiny_equity():
    cal = weekdays(4)
    codes = {'A': flat_prices('A', [10] * 4, [10] * 4, [10] * 4)}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    result = simulate_exposure(
        'T', bank, cal, cal[0], [cal[0]], lambda t: ['A'],
        {cal[0]: 0.15}, n_slots=3, fees=ETF_FEE_BAND, total=80.0)
    # leg target = 0.05 x 80 = 4 <= commission min 5 -> rule-compliant cash
    assert result.exec_stats.buys_cash_capped == 1
    assert result.trades == []
    assert result.equity[-1] == pytest.approx(80.0)
    assert result.leg_log[0]['outcome'] == 'cash_capped'


def test_exposure_engine_postponed_exit_slot_busy_and_leg_log():
    cal = weekdays(10)
    codes = {
        'A': flat_prices('A', [10, 10.5, 11, 11, 11.5, 12, 12, 12, 12, 12],
                         [10.2, 10.8, 11.2, 11, 11, 11.8, 12.2, 12.1, 12, 12],
                         [10, 10.2, 10.8, 11.2, 11, 11, 11.8, 12.2, 12.1, 12]),
        'B': flat_prices('B', [20, 20, 20, 17.5, 20, 20, 20, 20, 20, 20],
                         [20, 20, 20, 18, 20, 20, 20, 20, 20, 20],
                         [20, 20, 20, 20, 18, 20, 20, 20, 20, 20]),
        'C': flat_prices('C', [30, 30, 30, 30, 31, 31, 31, 31, 31, 31],
                         [30, 30, 30, 30, 31, 31, 31, 31, 31, 31],
                         [30, 30, 30, 30, 30, 31, 31, 31, 31, 31]),
        'D': flat_prices('D', [40] * 10, [40] * 10, [40] * 10),
        'E': flat_prices('E', [50] * 10, [50] * 10, [50] * 10),
        'F': flat_prices('F', [50] * 10, [50] * 10, [50] * 10),
    }
    feat = make_feat(codes, cal)
    # A suspended on d3 (planned exit session)
    feat = feat.filter(~((pl.col('ts_code') == 'A')
                         & (pl.col('trade_date') == cal[3])))
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E', 'F'],
              cal[2]: ['D', 'E', 'F', 'A', 'B'],
              cal[5]: ['D', 'E', 'F']}
    result = simulate_exposure(
        'T', bank, cal, cal[0], [cal[0], cal[2], cal[5]],
        lambda t: ranked[t], {d: 0.75 for d in (cal[0], cal[2], cal[5])},
        n_slots=3, fees=ETF_FEE_BAND, total=900.0)
    assert result.exec_stats.exit_suspended == 1        # A
    assert result.exec_stats.exit_limit_blocked == 1    # B
    assert result.exec_stats.buys_cancelled_slot_busy == 2
    late = sorted(t['code'] for t in result.trades
                  if t['kind'] == 'sell_postponed')
    assert late == ['A', 'B']
    assert result.exec_stats.sells_postponed_then_filled == 2
    d6_buys = [t['code'] for t in result.trades if t['side'] == 'buy'
               and t['session'] == cal[6]]
    assert d6_buys == ['E', 'F']
    assert result.max_negative_cash == pytest.approx(0.0)
    # leg log resolves the postponed sells
    outcomes = {(l['code'], l['outcome']) for l in result.leg_log
                if l['side'] == 'sell'}
    assert ('A', 'postponed_then_filled') in outcomes
    assert ('B', 'postponed_then_filled') in outcomes
    assert ('C', 'sell_at_open') in outcomes


def test_exposure_engine_net_gross_trade_parity():
    cal = weekdays(10)
    codes = {c: flat_prices(c, [10] * 10, [10] * 10, [10] * 10)
             for c in ('A', 'B', 'C', 'D', 'E')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    ranked = {cal[0]: ['A', 'B', 'C', 'D', 'E'],
              cal[4]: ['D', 'E', 'A', 'B', 'C']}
    expo = {d: 0.75 for d in (cal[0], cal[4])}
    net = simulate_exposure('T', bank, cal, cal[0], [cal[0], cal[4]],
                            lambda t: ranked[t], expo, n_slots=5,
                            fees=ETF_FEE_BAND, total=1000.0)
    gross = simulate_exposure('T-g', bank, cal, cal[0], [cal[0], cal[4]],
                              lambda t: ranked[t], expo, n_slots=5,
                              fees=GROSS_FEE_BAND, total=1000.0)
    seq = lambda r: [(t['session'], t['code'], t['side']) for t in r.trades]  # noqa: E731
    assert seq(net) == seq(gross)


# --------------------------------------------------------------------------- #
# B1(m): mechanism-matched equal weight, min(exposure/N_pool, 25%)
# --------------------------------------------------------------------------- #
def test_b1m_exposure_sizing_hand_check():
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
    expo = {cal[0]: 0.75, cal[2]: 0.75}
    result = simulate_b1_exposure(pools, bank, cal, cal[0], [cal[0], cal[2]],
                                  expo, total=200_000.0, fees=ETF_FEE_BAND)
    # period 1: N_pool=2, frac = min(0.375, 0.25) = 0.25 -> 50,000 per leg
    bx = 5.0
    ux = (50_000.0 - bx) / 10.0
    uy = (50_000.0 - 5.0) / 20.0
    assert result.equity[0] == pytest.approx(200_000.0)
    assert result.equity[1] == pytest.approx(
        100_000.0 + ux * 10.0 + uy * 20.0)
    # exits at d3 open (X 11, Y 22); proceeds join the CARRIED idle (100k)
    gx = ux * 11.0
    fx = max(gx * 0.0001, 5.0)
    gy = uy * 22.0
    fy = max(gy * 0.0001, 5.0)
    realized = (gx - fx) + (gy - fy)
    base2 = 100_000.0 + realized
    # period 2: N_pool=1, frac = min(0.75, 0.25) = 0.25 of the base
    budget2 = 0.25 * base2
    fee2 = max(budget2 * 0.0001, 5.0)
    u2 = (budget2 - fee2) / 11.0
    idle2 = 0.75 * base2
    assert result.equity[3] == pytest.approx(idle2 + u2 * 11.0)
    assert result.exec_stats.buys_filled == 3


def test_b1m_gross_variant_fee_free():
    cal = weekdays(4)
    codes = {'X': flat_prices('X', [10, 10, 11, 11], [10, 10, 11, 11],
                              [10, 10, 10, 11])}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    pools = {cal[0]: [PoolRow('X', 0, 0, 0, True, True)],
             cal[2]: [PoolRow('X', 0, 0, 0, True, True)]}
    expo = {cal[0]: 0.75, cal[2]: 0.75}
    net = simulate_b1_exposure(pools, bank, cal, cal[0], [cal[0], cal[2]],
                               expo, total=200_000.0, fees=ETF_FEE_BAND)
    gross = simulate_b1_exposure(pools, bank, cal, cal[0], [cal[0], cal[2]],
                                 expo, total=200_000.0, fees=GROSS_FEE_BAND)
    assert gross.equity[-1] > net.equity[-1]
    # gross period 1: 50k at 10 -> 5,000 units; idle 150k; exits at d3 open
    # 11 join the idle pool -> base 205,000; re-entry 25% at 11, marked at
    # the d3 close 11
    base2 = 150_000.0 + 5000.0 * 11.0
    u2 = (0.25 * base2) / 11.0
    assert gross.equity[-1] == pytest.approx(0.75 * base2 + u2 * 11.0)


# --------------------------------------------------------------------------- #
# N=5 concentration disclosure and dev-window execution rate
# --------------------------------------------------------------------------- #
def test_concentration_top5_share_disclosed():
    cal = weekdays(10)
    codes = {c: flat_prices(c, [10] * 10, [10] * 10, [10] * 10)
             for c in ('A', 'B', 'C', 'D', 'E', 'F')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    # six fully-in-segment round trips with fabricated pnls (session indices)
    positions = [{'code': c, 'entry_session': 0, 'entry_date': cal[0],
                  'budget': 100.0, 'units': 10.0, 'entry_adj': 10.0,
                  'entry_raw': 10.0, 'buy_fee': 0.0, 'proceeds': 0.0,
                  'exit_session': 9, 'exit_date': cal[9],
                  'exit_adj': 10.0, 'exit_raw': 10.0, 'sell_fee': 0.0,
                  'proceeds': 0.0, 'pnl': pnl, 'exit_kind': 'sell_at_open'}
                 for c, pnl in (('A', 50.0), ('B', 40.0), ('C', 30.0),
                                ('D', 20.0), ('E', 10.0), ('F', 0.0))]
    out = concentration(positions, [], bank, cal, cal[0], cal[9])
    assert out['top1_share'] == pytest.approx(50.0 / 150.0)
    assert out['top3_share'] == pytest.approx(120.0 / 150.0)
    assert out['top5_share'] == pytest.approx(150.0 / 150.0)


def test_window_execution_rate_dev_only():
    log = [
        {'plan_date': D(2016, 1, 29), 'side': 'buy', 'outcome': 'filled'},
        {'plan_date': D(2016, 2, 26), 'side': 'buy', 'outcome': 'cash_capped'},
        {'plan_date': D(2016, 3, 31), 'side': 'sell', 'outcome': 'sell_at_open'},
        {'plan_date': D(2016, 4, 29), 'side': 'buy',
         'outcome': 'cancelled_slot_busy'},
        {'plan_date': D(2016, 12, 30), 'side': 'buy', 'outcome': 'filled'},
        {'plan_date': D(2021, 6, 30), 'side': 'buy', 'outcome': 'filled'},
    ]
    dev = window_execution_rate(log, D(2016, 1, 1), D(2020, 12, 31))
    assert dev['legs_planned'] == 5
    assert dev['legs_executed'] == 4      # the cancelled leg is not executed
    assert dev['execution_rate'] == pytest.approx(0.8)
    full = window_execution_rate(log, D(2016, 1, 1), D(2024, 12, 31))
    assert full['legs_planned'] == 6 and full['legs_executed'] == 5


# --------------------------------------------------------------------------- #
# pool framing sanity for the R7 config consumption
# --------------------------------------------------------------------------- #
def test_group_pools_eligible_only_rows():
    cal = weekdays(3)
    codes = {
        'A': flat_prices('A', [10, 10, 10], [10, 10, 10], [10, 10, 10],
                         eligible=[True, True, True]),
        'B': flat_prices('B', [10, 10, 10], [10, 10, 10], [10, 10, 10],
                         eligible=[True, False, True]),
    }
    feat = make_feat(codes, cal)
    pools = group_pools(feat)
    assert [r.code for r in pools[cal[1]]] == ['A']
    assert sorted(r.code for r in pools[cal[2]]) == ['A', 'B']
