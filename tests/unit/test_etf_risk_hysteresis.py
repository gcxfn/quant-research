"""Unit tests for the P2-R9 hysteresis layer (synthetic data only).

Each test pins one registered semantic from
``configs/experiments/p2r9-risk-delivery.json``: the hysteresis state machine
(init ON; OFF at dd >= T; re-arm at dd <= T/2 from the SAME reference peak;
unavailable window = triggered), the D-family rolling peak whose window keeps
rolling, the PDD all-time peak that never resets, the C11 X1 dual-arm
composition (either arm off -> off; both re-armed -> on), the N=4 leg budget
min(E/N, 25%) = 22.5% with the top-4 concentration DISCLOSURE (gate stays
top-1/top-3), the A1/A2 anchor shape (FIX75 and the NO-hysteresis D60 path
must be untouched by the hysteresis code), never-negative cash under N=4
re-sizing, the B1(m) same-hysteresis requirement, and net/gross parity for
equity-independent mechanisms.  Synthetic values are never profitability
evidence.
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
    concentration,
    constant_risk_fn,
    exposures_from_state,
    hysteresis_state,
    leg_frac,
    pdd_hysteresis_risk_fn,
    pdd_risk_fn,
    rolling_dd_series,
    rolling_dd_state,
    simulate_b1_exposure,
    simulate_daily_risk,
    simulate_exposure,
    turnover_decomposition,
    x1_hysteresis_risk_fn,
)

D = date


def weekdays(n: int, start: D = D(2016, 1, 4)) -> list[D]:
    days, day = [], start
    while len(days) < n:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def index_frame(closes: list[float], calendar: list[D]) -> pl.DataFrame:
    return pl.DataFrame({'trade_date': calendar,
                         'close': closes}).sort('trade_date')


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


# --------------------------------------------------------------------------- #
# hysteresis state machine (registered semantics)
# --------------------------------------------------------------------------- #
def test_hysteresis_state_trigger_rearm_and_hold_between():
    cal = weekdays(8)
    # T = 0.08, rearm = 0.04
    dd = {d: v for d, v in zip(cal, [0.00, 0.05, 0.08, 0.06, 0.041,
                                     0.04, 0.05, 0.079])}
    st = hysteresis_state(dd, cal, 0.08, 0.04, cal[0])
    assert st[cal[0]] is True      # init ON
    assert st[cal[1]] is True      # 5% < 8%: stays on
    assert st[cal[2]] is False     # dd >= T: OFF trigger
    assert st[cal[3]] is False     # 4% < 6% < 8%: holds OFF
    assert st[cal[4]] is False     # 4.1% > 4%: still OFF
    assert st[cal[5]] is True      # dd <= rearm: re-arm ON
    assert st[cal[6]] is True
    assert st[cal[7]] is True      # 7.9% < 8%: on (boundary is dd >= T -> off)


def test_hysteresis_state_init_on_fires_immediately_and_dd_none_is_triggered():
    cal = weekdays(4)
    dd = {cal[0]: 0.09, cal[1]: 0.02, cal[2]: None, cal[3]: 0.0}
    st = hysteresis_state(dd, cal, 0.08, 0.04, cal[0])
    assert st[cal[0]] is False     # init ON then dd >= T on the first session
    assert st[cal[1]] is True      # dd <= rearm: re-arm
    assert st[cal[2]] is False     # window not formed: registered fallback = triggered
    assert st[cal[3]] is True      # dd 0: re-arm once formed


def test_hysteresis_state_only_consumes_sessions_on_or_after_start():
    cal = weekdays(4)
    dd = {d: v for d, v in zip(cal, [0.09, 0.09, 0.0, 0.0])}
    st = hysteresis_state(dd, cal, 0.08, 0.04, cal[2])
    assert set(st) == {cal[2], cal[3]}     # warmup sessions not consumed
    assert st[cal[2]] is True and st[cal[3]] is True   # init ON at start


def test_rolling_dd_series_matches_r8_state_and_window_rolls():
    cal = weekdays(8)
    closes = [10.0, 12.0, 11.0, 13.0, 10.0, 13.1, 13.2, 9.0]
    frame = index_frame(closes, cal)
    dd = rolling_dd_series(frame, cal, 3)
    # consistency with the R8 no-hysteresis state: on iff dd is not None and dd <= T
    st_r8 = rolling_dd_state(frame, cal, 3, 0.10)
    for d in cal:
        assert st_r8[d] == bool(dd[d] is not None and dd[d] <= 0.10)
    assert dd[cal[0]] is None and dd[cal[1]] is None   # window not formed
    assert dd[cal[3]] == pytest.approx(0.0)            # close == peak
    assert dd[cal[4]] == pytest.approx(1.0 - 10.0 / 13.0)
    # the window KEEPS ROLLING: at cal[6] the 3-window is (13.0, 10.0, 13.1)...
    assert dd[cal[6]] == pytest.approx(1.0 - 13.2 / 13.2)
    # ...and at cal[7] the peak is 13.2 (the old 13.0 peak left the window)
    assert dd[cal[7]] == pytest.approx(1.0 - 9.0 / 13.2)


def test_hysteresis_d_family_rearm_via_window_roll():
    # 5-session window; a crash turns the machine OFF and it HOLDS OFF while
    # the old peak is still inside the rolling window; the machine re-arms
    # ONLY once the peak rolls OUT of the window (no price ever recovered)
    cal2 = weekdays(10)
    closes = [20.0, 20.0, 20.0, 20.0, 20.0, 18.0, 18.5, 19.0, 19.0, 19.0]
    dd = rolling_dd_series(index_frame(closes, cal2), cal2, 5)
    st = hysteresis_state(dd, cal2, 0.08, 0.04, cal2[0])
    assert st[cal2[4]] is True                  # flat at the peak: on
    assert st[cal2[5]] is False                 # dd 10% >= 8%: OFF trigger
    assert st[cal2[6]] is False                 # dd 7.5%: 4% < 7.5% < 8% -> hold OFF
    assert st[cal2[7]] is False                 # dd 5% vs peak 20: hold OFF
    assert st[cal2[8]] is False                 # window still contains 20: hold OFF
    # cal2[9]: window = cal2[5..9], peak rolls down to 19 = close -> dd 0 -> re-arm
    assert dd[cal2[9]] == pytest.approx(0.0)
    assert st[cal2[9]] is True                  # re-armed via window roll


def test_pdd_hysteresis_same_reference_peak_never_resets():
    fn = pdd_hysteresis_risk_fn(0.10, 0.05)
    d = D(2016, 1, 4)
    assert fn(d, 100.0) == 0.90        # first session: dd 0 -> on
    assert fn(d, 95.0) == 0.90         # dd 5% < 10%: on
    assert fn(d, 89.0) == 0.40         # dd 11% >= 10%: OFF
    assert fn(d, 93.0) == 0.40         # dd 7%: between 5% and 10% -> HOLD OFF
    assert fn(d, 95.5) == 0.90         # dd 4.5% <= 5% from the SAME peak 100: re-arm
    assert fn(d, 96.5) == 0.90         # dd 3.5% < 10%: stays on
    assert fn(d, 86.0) == 0.40         # dd 11%: OFF again
    assert fn(d, 101.0) == 0.90        # new all-time peak 101, dd 0 -> re-arm
    fresh = pdd_hysteresis_risk_fn(0.10, 0.05)   # fresh instance, own peak
    assert fresh(d, 50.0) == 0.90
    # plain R8 PDD would re-arm at dd 7%; hysteresis holds OFF there
    plain = pdd_risk_fn(0.10)
    assert plain(d, 100.0) == 0.90 and plain(d, 89.0) == 0.40
    assert plain(d, 93.0) == 0.90      # plain: dd 7% <= 10% -> back on
    hyst = pdd_hysteresis_risk_fn(0.10, 0.05)
    hyst(d, 100.0), hyst(d, 89.0)
    assert hyst(d, 93.0) == 0.40       # hysteresis: still OFF at dd 7%


def test_x1_hysteresis_dual_arm_composition():
    cal = weekdays(4)
    d_state = {cal[0]: True, cal[1]: False, cal[2]: True, cal[3]: True}
    fn = x1_hysteresis_risk_fn(d_state, 0.10, 0.05)
    assert fn(cal[0], 100.0) == 0.90   # both arms on
    assert fn(cal[1], 99.0) == 0.40    # D-arm off -> X1 off even with PDD on
    assert fn(cal[2], 89.0) == 0.40    # D-arm on but PDD fires (dd 11%)
    assert fn(cal[3], 94.0) == 0.40    # PDD dd 6%: hold OFF (rearm 5%)
    fn2 = x1_hysteresis_risk_fn(d_state, 0.10, 0.05)
    fn2(cal[0], 100.0)
    fn2(cal[1], 89.0)                  # PDD fires
    assert fn2(cal[2], 95.5) == 0.90   # PDD re-armed (dd 4.5%) AND D-arm on


# --------------------------------------------------------------------------- #
# N=4 leg budget and concentration disclosure
# --------------------------------------------------------------------------- #
def test_n4_leg_budget_and_top4_disclosure():
    assert leg_frac(0.90, 3) == 0.25     # N=3 saturates at 25% (75% on)
    assert leg_frac(0.90, 4) == 0.225    # N=4: 22.5% per leg (90% on)
    cal = weekdays(8)
    # A doubles, B/C/D flat: A dominates the P&L -> top1/top4 shares meaningful
    codes = {
        'A': flat_prices('A', [10.0] * 8, [10.0, 10.0, 10.0, 10.0, 10.0,
                                           10.0, 10.0, 20.0], [10.0] * 8),
        'B': flat_prices('B', [10.0] * 8, [10.0] * 8, [10.0] * 8),
        'C': flat_prices('C', [10.0] * 8, [10.0] * 8, [10.0] * 8),
        'D': flat_prices('D', [10.0] * 8, [10.0] * 8, [10.0] * 8),
    }
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    result = simulate_daily_risk(
        'N4', bank, cal, cal[0], [cal[0]], lambda t: ['A', 'B', 'C', 'D'],
        constant_risk_fn(0.90), n_slots=4, fees=ETF_FEE_BAND, total=2000.0)
    buys = [t for t in result.trades if t['kind'] == 'open']
    assert len(buys) == 4
    assert all(t['notional'] == pytest.approx(0.225 * 2000.0) for t in buys)
    conc = concentration(result.positions, result.final_open, bank, cal,
                         cal[0], cal[-1])
    assert 'top4_share' in conc                    # N=4 disclosure exists
    assert conc['top4_share'] == pytest.approx(1.0)  # all four codes positive
    ordered = sorted(conc['pnl_by_code'].values(), reverse=True)
    assert conc['top4_share'] == pytest.approx(sum(ordered[:4]) / conc['total_pnl'])
    # the GATE fields stay top-1/top-3 regardless of N
    assert conc['top1_share'] is not None and conc['top3_share'] is not None


# --------------------------------------------------------------------------- #
# A1/A2 anchor shape: hysteresis code must not perturb inherited paths
# --------------------------------------------------------------------------- #
def test_a2_no_hysteresis_d60_path_equals_r8_functions():
    cal = weekdays(12)
    closes = [10.0, 11.0, 12.0, 11.0, 10.5, 11.5, 12.5, 11.4, 10.4, 11.0,
              12.0, 13.0]
    frame = index_frame(closes, cal)
    # the R9 series maps to the R8 state session-for-session (A2 guarantee)
    dd = rolling_dd_series(frame, cal, 3)
    st_r8 = rolling_dd_state(frame, cal, 3, 0.08)
    expo_r9 = {d: (0.90 if (dd[d] is not None and dd[d] <= 0.08) else 0.40)
               for d in cal}
    expo_r8 = exposures_from_state(st_r8, 0.90, 0.40)
    assert expo_r9 == expo_r8
    # and the engine paths are bit-exact between the two constructions
    codes = {c: flat_prices(c, [10.0] * 12, [10.0] * 12, [10.0] * 12)
             for c in ('A', 'B', 'C')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    signals = [cal[0], cal[6]]
    ranked = {t: ['A', 'B', 'C'] for t in signals}
    r9 = simulate_daily_risk('A2', bank, cal, cal[0], signals,
                             lambda t: ranked[t],
                             lambda d, e, _e=expo_r9: _e[d],
                             n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    r8 = simulate_daily_risk('A2', bank, cal, cal[0], signals,
                             lambda t: ranked[t],
                             lambda d, e, _e=expo_r8: _e[d],
                             n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    assert r9.equity == r8.equity and r9.sessions == r8.sessions
    assert ([(t['session'], t['code'], t['side'], t['kind'])
             for t in r9.trades]
            == [(t['session'], t['code'], t['side'], t['kind'])
                for t in r8.trades])


def test_a1_fix75_engine_equivalence_net_and_gross():
    cal = weekdays(8)
    codes = {c: flat_prices(c, [10.0] * 8, [10.0] * 8, [10.0] * 8)
             for c in ('A', 'B', 'C')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    signals = [cal[0], cal[4]]
    ranked = {cal[0]: ['A', 'B', 'C'], cal[4]: ['B', 'C', 'A']}
    seq = lambda r: [(t['session'], t['code'], t['side'], t['kind'])  # noqa: E731
                     for t in r.trades]
    for fees in (ETF_FEE_BAND, GROSS_FEE_BAND):   # net AND gross
        r9 = simulate_daily_risk('A1', bank, cal, cal[0], signals,
                                 lambda t: ranked[t], constant_risk_fn(0.75),
                                 n_slots=3, fees=fees, total=1200.0)
        r7 = simulate_exposure('A1', bank, cal, cal[0], signals,
                               lambda t: ranked[t],
                               {x: 0.75 for x in signals},
                               n_slots=3, fees=fees, total=1200.0)
        assert r9.equity == r7.equity
        assert seq(r9) == seq(r7)
        assert r9.exec_stats.risk_legs_planned == 0


def test_hysteresis_n4_rescale_cash_never_negative():
    cal = weekdays(6)
    codes = {c: flat_prices(c, [10.0] * 6, [10.0] * 6, [10.0] * 6)
             for c in ('A', 'B', 'C', 'D')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    # E path forces a down-scale then an up-scale with almost no idle cash
    path = {x: 0.90 for x in cal}
    path[cal[1]] = 0.40       # off: sell down
    path[cal[2]] = 0.40
    path[cal[3]] = 0.90       # re-arm: buy back with the sold proceeds only
    result = simulate_daily_risk(
        'N4H', bank, cal, cal[0], [cal[0]], lambda t: ['A', 'B', 'C', 'D'],
        lambda d, e: path[d], n_slots=4, fees=ETF_FEE_BAND, total=400.0)
    assert result.max_negative_cash == pytest.approx(0.0)
    sells = [t for t in result.trades if t['kind'] == 'retarget_sell']
    buys = [t for t in result.trades if t['kind'] == 'retarget_buy']
    assert len(sells) == 4 and len(buys) == 4
    # re-size buys are capped by the idle pool: total buy notional <= total
    # sell proceeds (cash conservation)
    assert sum(t['notional'] for t in buys) <= sum(
        t['notional'] for t in sells) + 1e-9
    assert turnover_decomposition(result)[2016]['risk_buy_notional'] == \
        pytest.approx(sum(t['notional'] for t in buys))


# --------------------------------------------------------------------------- #
# B1(m) same hysteresis; net/gross parity for equity-independent mechs
# --------------------------------------------------------------------------- #
def test_b1m_same_hysteresis_machine_on_own_equity():
    # 4-code pool (frac = min(E/4, 25%)): X1..X4 rise, crash ~12.5%, then the
    # B1(m) instance must run the SAME hysteresis machine on its OWN equity:
    # OFF at dd >= 10%, holding OFF through the shallow bounce, re-arming only
    # when the instance equity makes a new all-time high (dd -> 0).
    cal = weekdays(9)
    closes = [10.0, 11.0, 12.0, 12.0, 10.5, 10.2, 10.15, 10.1, 24.5]
    opens = [10.0] + closes[:-1]          # gap-free opens (no 9.5% proxy trips)
    codes = {f'X{i}': flat_prices(f'X{i}', opens, closes, opens)
             for i in range(4)}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    pool = [PoolRow(f'X{i}', 0, 0, 0, True, True) for i in range(4)]
    pools = {cal[0]: pool, cal[4]: pool}
    result = simulate_b1_exposure(
        pools, bank, cal, cal[0], [cal[0], cal[4]], {}, total=200_000.0,
        fees=ETF_FEE_BAND, config_id='B1-PDDH',
        risk_fn=pdd_hysteresis_risk_fn(0.10, 0.05))
    e_at = result.extra['e_at']
    # rebuild the machine from the B1 instance's own marked equity and check
    # the level sequence follows hysteresis (same machine, own peak)
    peak, on = None, True
    for day, eq in zip(result.sessions, result.equity):
        peak = eq if peak is None else max(peak, eq)
        dd = 1.0 - eq / peak
        if on:
            if dd >= 0.10:
                on = False
        elif dd <= 0.05:
            on = True
        assert e_at[day] == (0.90 if on else 0.40)
    # the OFF state actually occurred, persisted, and re-armed at the new high
    offs = [day for day in cal if e_at[day] == 0.40]
    assert offs and offs[0] == cal[4] and offs[-1] == cal[7]
    assert e_at[cal[8]] == 0.90
    # the OFF rescale really sold (turnover books carry the risk sells)
    assert result.extra['turnover_acc'][2016]['sell_notional'] > 0.0


def test_net_gross_parity_hysteresis_dict_mech():
    cal = weekdays(8)
    codes = {c: flat_prices(c, [10.0] * 8, [10.0] * 8, [10.0] * 8)
             for c in ('A', 'B', 'C')}
    feat = make_feat(codes, cal)
    bank = CodeDataBank(feat, cal)
    dd = {d: (0.0 if i < 3 else 0.10 if i < 5 else 0.02)
          for i, d in enumerate(cal)}
    expo = exposures_from_state(hysteresis_state(dd, cal, 0.08, 0.04, cal[0]),
                                0.90, 0.40)
    seq = lambda r: [(t['session'], t['code'], t['side'], t['kind'])  # noqa: E731
                     for t in r.trades]
    net = simulate_daily_risk('H', bank, cal, cal[0], [cal[0]],
                              lambda t: ['A', 'B', 'C'],
                              lambda d, e, _e=expo: _e[d],
                              n_slots=3, fees=ETF_FEE_BAND, total=1200.0)
    gross = simulate_daily_risk('H-g', bank, cal, cal[0], [cal[0]],
                                lambda t: ['A', 'B', 'C'],
                                lambda d, e, _e=expo: _e[d],
                                n_slots=3, fees=GROSS_FEE_BAND, total=1200.0)
    assert seq(net) == seq(gross)              # parity: same trade sequence
    assert gross.equity[-1] > net.equity[-1]   # fees are the only difference
