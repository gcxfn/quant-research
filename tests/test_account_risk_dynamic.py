"""Dynamic account-risk replay tests (prereg exp-20260921, synthetic only).

Two layers, both hand-checked:

* ``n*`` - the incremental state machine (``risk_overlay.AccountRiskDynamics``)
  and its host driver: trigger, recovery confirmation, cooldown (session
  denominated), high-water / phase reference updates, fail-closed data gaps,
  and equivalence with the batch resolver of the same frozen policies.
* ``e*`` - real half-day engine runs with the host driver attached to
  ``intent_provider``: control parity, a trim leg and its top-up, and the
  ledger-mark reconciliation guard.

No experiment is consumed here: everything runs on synthetic bars.
"""
from __future__ import annotations

import datetime as dt
from datetime import date

import polars as pl
import pytest

from quant.backtest.band_engine import run_band_backtest_intents
from quant.portfolio import risk_overlay as ro
from quant.portfolio.recommendations import DecisionPoint
from quant.research.risk_overlay_runner import (
    DynamicOverlayHost, LedgerMarks, OverlayRunnerError)

D1, D2, D3, D4, D5, D6, D7 = (date(2024, 1, 2 + i) for i in range(7))
STOCK = 'sh.600001'
CLOSE = dt.time(15, 0)
NOON = dt.time(11, 30)


def d(n: int) -> date:
    """n-th synthetic session (calendar days; the machine reads dates only)."""
    return date(2024, 3, 1) + dt.timedelta(days=n)


def machine_rows(config_id: str, series: list[float]) -> list[ro.OverlayDecision]:
    """Feed one close per session and step both decision points of each day."""
    m = ro.AccountRiskDynamics(config_id)
    out: list[ro.OverlayDecision] = []
    for i, value in enumerate(series):
        out.append(m.step(d(i), decision_point=DecisionPoint.AM_1130))
        m.observe_close(d(i), value)
        out.append(m.step(d(i), decision_point=DecisionPoint.PM_1500))
    return out


# ---------------------------------------------------------------------------
# n1: D1 daily loss - trigger, session-denominated cooldown, confirmed restore
# ---------------------------------------------------------------------------

def test_n1_daily_loss_trigger_cooldown_and_restore():
    # d1 100 (reference) | d2 96 (-4% -> trigger) | d3 97 | d4 98 | d5 99 |
    # d6 100.  Cooldown = 3 judged sessions, confirmations = 2.
    series = [100.0, 96.0, 97.0, 98.0, 99.0, 100.0]
    rows = machine_rows('D1', series)
    # (day, session) order is am before pm; index = 2*i + (0 am, 1 pm)
    def row(day_i: int, session: int) -> ro.OverlayDecision:
        return rows[2 * day_i + session]

    # first 11:30 has no completed close at all: fail closed, no entries
    first = row(0, 0)
    assert first.risk_state is ro.OverlayState.INSUFFICIENT_DATA
    assert first.action is ro.OverlayAction.FAIL_CLOSED
    assert first.equity_as_of is None
    assert ro.attack_entry_allowed(first.risk_state) is False

    # the first close establishes the reference: normal, and the gap restore
    # needs neither confirmation nor cooldown
    assert row(0, 1).risk_state is ro.OverlayState.NORMAL
    assert row(0, 1).action is ro.OverlayAction.RESTORE_ATTACK
    assert row(0, 1).exposure_multiplier == ro.LEVEL_ON

    # the -4% session lowers exposure on the decision point that sees it
    trig = row(1, 1)
    assert trig.risk_state is ro.OverlayState.REDUCED
    assert trig.action is ro.OverlayAction.REDUCE_ATTACK
    assert trig.exposure_multiplier == ro.LEVEL_OFF
    assert trig.trigger_reason == 'daily_loss_beyond_limit'
    assert trig.equity_as_of == d(1)
    # the 11:30 row re-reads d2's close: same state, no new decision
    assert row(2, 0).risk_state is ro.OverlayState.REDUCED
    assert row(2, 0).action is ro.OverlayAction.HOLD
    assert row(2, 0).equity_as_of == d(1)

    # a recovered session inside the 3-session cooldown holds, and the 11:30
    # re-read must neither advance nor reset the confirmation streak
    assert row(2, 1).action is ro.OverlayAction.HOLD
    assert row(2, 1).trigger_reason == 'recovery_pending_cooldown'
    assert row(3, 1).trigger_reason == 'recovery_pending_cooldown'

    # session 4 is the 4th judged session after the lowering (>= 3) and the
    # recovery condition has held for 2+ sessions: restore to 0.90
    restore = row(4, 1)
    assert restore.risk_state is ro.OverlayState.NORMAL
    assert restore.action is ro.OverlayAction.RESTORE_ATTACK
    assert restore.exposure_multiplier == ro.LEVEL_ON
    assert restore.trigger_reason == 'recovery_confirmed'
    assert row(5, 0).risk_state is ro.OverlayState.NORMAL
    assert row(5, 0).action is ro.OverlayAction.HOLD
    assert row(5, 1).action is ro.OverlayAction.HOLD

    # the incremental driver can only name a cooldown boundary it has already
    # observed; the gate itself is session-counted and is pinned above
    assert trig.cooldown_until is None
    reduced_sessions = [r for r in rows
                        if r.risk_state is ro.OverlayState.REDUCED]
    assert len(reduced_sessions) == 6        # 3 sessions x (am + pm)
    # every row whose state did not change is HOLD, and vice versa
    for r in rows:
        assert r.state_changed is (r.action is not ro.OverlayAction.HOLD)


def test_n1b_fresh_loss_during_cooldown_restarts_confirmations():
    # d2 -4% (trigger: the cooldown is anchored at this transition) | d4
    # -6.06% AGAIN while already reduced: the state does not change, so the
    # cooldown anchor is NOT re-taken, but the confirmation streak restarts
    # (d4 is not a recovered session), which still delays the restore
    series = [100.0, 96.0, 97.0, 91.2, 95.0, 96.0, 97.0]
    rows = machine_rows('D1', series)
    def row(day_i: int, session: int) -> ro.OverlayDecision:
        return rows[2 * day_i + session]

    assert row(1, 1).trigger_reason == 'daily_loss_beyond_limit'   # d2 -4%
    assert row(3, 1).trigger_reason == 'daily_loss_beyond_limit'   # d4 -6.06%
    # d5: the cooldown (3 sessions from index 1) has elapsed, but the fresh
    # loss reset the streak, so the restore waits for a second confirmation
    assert row(4, 1).trigger_reason == 'recovery_pending_confirmation'
    assert row(4, 1).risk_state is ro.OverlayState.REDUCED
    assert row(4, 1).exposure_multiplier == ro.LEVEL_OFF
    assert row(5, 1).action is ro.OverlayAction.RESTORE_ATTACK
    assert row(5, 1).exposure_multiplier == ro.LEVEL_ON
    # without the fresh loss (n1's shape) the restore would have landed one
    # session earlier, at index 4
    assert row(4, 1).action is ro.OverlayAction.HOLD


# ---------------------------------------------------------------------------
# n2: phase drawdown uses a TRAILING window of sessions
# ---------------------------------------------------------------------------

def test_n2_phase_drawdown_reference_forgets_old_highs():
    ref = ro.running_phase_drawdown(
        [(d(0), 100.0), (d(1), 90.0), (d(2), 80.0), (d(3), 85.0),
         (d(4), 120.0)], 3)
    assert ref[d(0)] == (100.0, 0.0)
    assert ref[d(1)] == (100.0, pytest.approx(0.10))
    assert ref[d(2)] == (100.0, pytest.approx(0.20))
    # the 100 has fallen out of the 3-session window: peak 90 -> dd 5.56%
    assert ref[d(3)] == (90.0, pytest.approx(1 - 85 / 90))
    # a new high inside the window resets the reference
    assert ref[d(4)] == (120.0, 0.0)


def test_n2b_phase_drawdown_trigger_and_recovery():
    # window = all available sessions here; 8% off the phase peak lowers,
    # 4% or better re-arms (values chosen away from the exact 4.0000%
    # boundary: ``1 - 96/100`` is 0.040000000000000036 in binary)
    series = [100.0, 100.0, 96.0, 91.2, 96.1, 96.1, 96.1]
    rows = machine_rows('D2', series)
    assert rows[2 * 2 + 1].risk_state is ro.OverlayState.NORMAL   # dd 4%
    trig = rows[2 * 3 + 1]                                        # dd 8.8%
    assert trig.risk_state is ro.OverlayState.REDUCED
    assert trig.trigger_reason == 'phase_drawdown_beyond_limit'
    assert trig.high_water_mark == pytest.approx(100.0)
    assert trig.drawdown == pytest.approx(0.088)
    # recovery condition holds from d5 (dd = 3.9%), cooldown 3 sessions from
    # session index 3 -> the earliest restore is session index 6
    assert rows[2 * 4 + 1].trigger_reason == 'recovery_pending_cooldown'
    assert rows[2 * 6 + 1].action is ro.OverlayAction.RESTORE_ATTACK
    assert rows[2 * 6 + 1].exposure_multiplier == ro.LEVEL_ON


# ---------------------------------------------------------------------------
# n3: high-water drawdown never resets its peak
# ---------------------------------------------------------------------------

def test_n3_high_water_peak_is_the_running_maximum():
    series = [100.0, 96.0, 89.0, 90.2, 92.0, 95.5, 95.5, 95.5, 95.5]
    rows = machine_rows('D3', series)
    # 96 (dd 4%) stays normal; 89 (dd 11%) lowers
    assert rows[2 * 1 + 1].risk_state is ro.OverlayState.NORMAL
    trig = rows[2 * 2 + 1]
    assert trig.risk_state is ro.OverlayState.REDUCED
    assert trig.trigger_reason == 'drawdown_beyond_limit'
    assert trig.high_water_mark == pytest.approx(100.0)
    assert trig.drawdown == pytest.approx(0.11)
    # the peak is the all-time maximum, so 90.2 (dd 9.8%) and 92 (dd 8%) are
    # NOT recoverable even though they are well off the phase window's own low
    assert rows[2 * 3 + 1].trigger_reason == 'recovery_pending_cooldown'
    assert rows[2 * 4 + 1].risk_state is ro.OverlayState.REDUCED
    assert rows[2 * 4 + 1].high_water_mark == pytest.approx(100.0)
    # 95.5 -> dd 4.5% <= 5% re-arm; cooldown (3 sessions from index 2) and two
    # confirming sessions land on session index 6
    assert rows[2 * 6 + 1].action is ro.OverlayAction.RESTORE_ATTACK
    # D0 never leaves normal whatever the inputs say
    control = machine_rows('D0', series)
    assert {r.risk_state for r in control} == {ro.OverlayState.NORMAL}
    assert {r.exposure_multiplier for r in control} == {ro.LEVEL_ON}


# ---------------------------------------------------------------------------
# n4: the incremental machine and the batch resolver cannot drift
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('config_id', ['D0', 'D1', 'D2', 'D3'])
def test_n4_incremental_matches_batch_resolver(config_id):
    series = [100.0 + 6.0 * ((i * 7) % 11) - 20.0 * (i % 5 == 4)
              for i in range(30)]
    decision_times: list[dt.datetime] = []
    points: list[DecisionPoint] = []
    for i in range(len(series)):
        decision_times += [dt.datetime.combine(d(i), NOON),
                           dt.datetime.combine(d(i), CLOSE)]
        points += [DecisionPoint.AM_1130, DecisionPoint.PM_1500]
    batch = ro.resolve_overlay(
        decision_times, config_id=config_id,
        decision_points=points,
        equity=[(d(i), v) for i, v in enumerate(series)])
    incremental = machine_rows(config_id, series)
    # every contract field matches; ``cooldown_until`` is the one diagnosic an
    # increment cannot publish ahead of the observations (see the machine
    # docstring), so it is compared only where the boundary is already known
    batch_rows = [r.as_dict() for r in batch]
    incr_rows = [r.as_dict() for r in incremental]
    for got, want in zip(incr_rows, batch_rows):
        assert {k: v for k, v in got.items() if k != 'cooldown_until'} == \
            {k: v for k, v in want.items() if k != 'cooldown_until'}
        if got['cooldown_until'] is not None:
            assert got['cooldown_until'] == want['cooldown_until']


# ---------------------------------------------------------------------------
# n5: guards (fail-closed)
# ---------------------------------------------------------------------------

def test_n5_guards():
    with pytest.raises(ro.RiskOverlayError, match='unknown dynamic config_id'):
        ro.AccountRiskDynamics('C2')
    with pytest.raises(ro.RiskOverlayError, match='finite positive'):
        ro.AccountRiskDynamics('D1').observe_close(d(0), 0.0)
    m = ro.AccountRiskDynamics('D3')
    m.observe_close(d(0), 100.0)
    with pytest.raises(ro.RiskOverlayError, match='strictly increase'):
        m.observe_close(d(0), 101.0)
    m.step(d(1), decision_point=DecisionPoint.AM_1130)
    # the same decision point twice would double-count the session counters
    with pytest.raises(ro.RiskOverlayError, match='strictly increase'):
        m.step(d(1), decision_point=DecisionPoint.AM_1130)
    with pytest.raises(ro.RiskOverlayError, match='strictly increase'):
        m.step(d(0), decision_point=DecisionPoint.PM_1500)
    # an 11:30 decision cannot silently read a close from the future
    assert m.step(d(1), decision_point=DecisionPoint.PM_1500).equity_as_of == d(0)
    # D0-D3 register no hard stop, so BLOCKED is unreachable
    assert all(p.hard_stop_drawdown is None
               for p in ro.DYNAMIC_POLICIES.values())
    assert set(ro.DYNAMIC_POLICIES) == set(ro.DYNAMIC_CONFIG_IDS)


# ---------------------------------------------------------------------------
# engine helpers (same shape as tests/test_band_dynamic.py)
# ---------------------------------------------------------------------------

def daily_frame(symbol, rows):
    """rows: (date, open, high, low, close, preclose)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'preclose': [float(r[5]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def half_frame(symbol, rows):
    """rows: (date, session, open, high, low, close)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows]})


def limits_frame(daily, symbol=STOCK):
    return daily.filter(pl.col('symbol') == symbol).select(
        'symbol', 'date',
        (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'))


def entry_row(symbol, day, session, source, weight, priority=1, expiry=None):
    return {'symbol': symbol, 'side': 'buy', 'intent': '',
            'decision_date': day, 'decision_session': session,
            'source_signal': source, 'expiry_date': expiry,
            'priority': priority, 'target_weight': float(weight),
            'target_notional': None}


def run_with(provider, daily, half, limits,
             cash=200_000.0, meta=None):
    return run_band_backtest_intents(
        None, daily, half, limits,
        symbol_meta=(meta if meta is not None
                     else {STOCK: {"asset_class": "stock", "band": .1,
                                   "t_plus": 1}}),
        initial_cash=cash, execution_clock="halfday",
        intent_provider=provider)


# ---------------------------------------------------------------------------
# e1: D0 is the carrier: no trim, no top-up, identical frames
# ---------------------------------------------------------------------------

def test_e1_control_host_keeps_the_carrier_stream():
    daily = daily_frame(STOCK, [
        (D1, 2.00, 2.01, 1.99, 2.00, 2.00),
        (D2, 2.00, 2.01, 1.99, 2.00, 2.00),
        (D3, 1.60, 1.62, 1.58, 1.60, 2.00),
        (D4, 1.60, 1.62, 1.58, 1.60, 1.60)])
    half = half_frame(STOCK, [
        (D1, 'am', 2.00, 2.01, 1.99, 2.00),
        (D1, 'pm', 2.00, 2.01, 1.99, 2.00),
        (D2, 'am', 2.00, 2.01, 1.99, 2.00),
        (D2, 'pm', 2.00, 2.01, 1.99, 2.00),
        (D3, 'am', 1.60, 1.62, 1.58, 1.60),
        (D3, 'pm', 1.60, 1.62, 1.58, 1.60),
        (D4, 'am', 1.60, 1.62, 1.58, 1.60),
        (D4, 'pm', 1.60, 1.62, 1.58, 1.60)])
    limits = limits_frame(daily)
    marks = LedgerMarks(daily, half)

    def carrier(day, sess, ledger):
        held = {p['symbol'] for p in ledger['positions']}
        if STOCK not in held:
            return [entry_row(STOCK, day, sess, D1, 0.10)]
        return None

    host = DynamicOverlayHost('D0', marks)

    def with_host(day, sess, ledger):
        step = host.step(ledger, members=[STOCK], rank_of={STOCK: 1},
                         source_signal=D1, expiry=None)
        assert step.risk_state == 'normal'
        assert step.exposure_multiplier == ro.LEVEL_ON
        assert step.ratio == pytest.approx(1.0)
        assert step.trim_symbols == () and step.topup_symbols == ()
        return list(step.rows) or None

    base = run_with(carrier, daily, half, limits)
    hosted = run_with(with_host, daily, half, limits)
    for name in ('fills', 'events', 'daily', 'clips_final'):
        assert getattr(hosted, name).equals(getattr(base, name)), name
    assert host.steps[0].entry_symbols == (STOCK,)
    assert host.steps[0].target_weight == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# e2: D1 trims to 0.40 exposure, then tops the seat back up on restore
# ---------------------------------------------------------------------------

def test_e2_daily_loss_trim_then_restore_topup():
    # A 25% seat (the registered single-name cap, passed as the host's base
    # weight for this test) bought at 2.00 in the D1 pm session: the D3 close
    # at 1.60 is a -5.0% ACCOUNT session, so D1 lowers exposure on (D3, pm).
    # The trim is a half-day limit order (no K=3 fallback) that fills in the
    # D4 am session; a flat 1.60 path then re-arms and the (D6, pm) restore
    # tops the seat back up to the normal target.
    daily = daily_frame(STOCK, [
        (D1, 2.00, 2.01, 1.99, 2.00, 2.00),
        (D2, 2.00, 2.01, 1.99, 2.00, 2.00),
        (D3, 1.60, 1.62, 1.58, 1.60, 2.00),
        (D4, 1.60, 1.62, 1.58, 1.60, 1.60),
        (D5, 1.60, 1.62, 1.58, 1.60, 1.60),
        (D6, 1.60, 1.62, 1.58, 1.60, 1.60),
        (D7, 1.60, 1.62, 1.58, 1.60, 1.60)])
    half = half_frame(STOCK, [
        (d_, s_, 2.00 if d_ <= D2 else 1.60, 2.01 if d_ <= D2 else 1.62,
         1.99 if d_ <= D2 else 1.58, 2.00 if d_ <= D2 else 1.60)
        for d_ in (D1, D2, D3, D4, D5, D6, D7) for s_ in ('am', 'pm')])
    limits = limits_frame(daily)
    marks = LedgerMarks(daily, half)
    host = DynamicOverlayHost('D1', marks, base_weight=0.25)

    def provider(day, sess, ledger):
        step = host.step(ledger, members=[STOCK], rank_of={STOCK: 1},
                         source_signal=D1, expiry=None)
        return list(step.rows) or None

    res = run_with(provider, daily, half, limits)

    # entry: 0.25 x 200,000 / 2.00 = 25,000 shares, commission min-5.  The
    # first 11:30 has no completed close (fail closed), so the seat is entered
    # at (D1, pm) and the engine's pm route fills it in the D2 am session.
    entry, trim, topup = res.fills.rows(named=True)
    assert (entry['date'], entry['session'], entry['side']) == (D2, 'am', 'buy')
    assert entry['shares'] == 25_000 and entry['price'] == 2.00
    assert entry['commission'] == pytest.approx(5.0)

    # the trigger fires on (D3, pm): equity 149,995 + 25,000 x 1.60 = 189,995,
    # one session -5.00%; the reduced target is 0.25 x 0.40/0.90 = 0.111111
    reduced = [s for s in host.steps if s.risk_state == 'reduced']
    assert len(reduced) == 6                      # 3 sessions x (am + pm)
    assert reduced[0].decision_time == dt.datetime.combine(D3, CLOSE)
    assert reduced[0].trigger_reason == 'daily_loss_beyond_limit'
    assert reduced[0].target_weight == pytest.approx(0.25 * 0.40 / 0.90)
    assert reduced[0].trim_symbols == (STOCK,)

    # trim: floor(0.111111 x 189,995 / 1.60 / 100) x 100 = 13,100 held, so
    # 11,900 sold at 1.60 in the (D3, pm) order's live session; a stock sell
    # pays the 0.05% stamp
    assert (trim['date'], trim['session'], trim['side']) == (D4, 'am', 'sell')
    assert trim['shares'] == 11_900 and trim['price'] == 1.60
    assert trim['commission'] == pytest.approx(5.0)
    assert trim['stamp_tax'] == pytest.approx(11_900 * 1.60 * 0.0005)
    assert trim['fill_type'] == 'limit'
    # the registered semantics: this leg never assumes a fill and never arms
    # the K=3 forced exit
    assert res.stats['k3_fallback']['armed'] == 0

    # restore: two restores exist (the data-gap one on (D1, pm) has nothing to
    # top up); the (D6, pm) row re-arms the seat and emits a delta top-up;
    # 13,100 x 1.60 = 20,960 held, equity 189,980.48, delta to 0.25 =
    # 0.25 x 189,980.48 - 20,960 = 26,535.12 -> floor /1.60/100 -> 16,500
    gap = [s for s in host.steps if s.action == 'restore_attack'
           and not s.topup_symbols]
    assert [s.risk_state for s in gap] == ['normal']
    assert gap[0].decision_time == dt.datetime.combine(D1, CLOSE)
    restored = [s for s in host.steps if s.action == 'restore_attack'
                and s.topup_symbols]
    assert len(restored) == 1
    assert restored[0].decision_time == dt.datetime.combine(D6, CLOSE)
    assert restored[0].topup_symbols == (STOCK,)
    assert (topup['date'], topup['session'], topup['side']) == (D7, 'am', 'buy')
    assert topup['shares'] == 16_500 and topup['price'] == 1.60
    assert topup['commission'] == pytest.approx(5.0)
    # the seat ends within the registered resize tolerance of the normal
    # target: 29,600 x 1.60 / equity
    final_equity = res.daily['equity'][-1]
    assert res.clips_final['shares'].sum() == 29_600
    assert 29_600 * 1.60 / final_equity == pytest.approx(
        0.25, abs=0.005 + 1e-9)
    assert res.daily['settled_cash'][-1] == pytest.approx(
        200_000.0 - 50_005.0 + (11_900 * 1.60 - 5.0 - 11_900 * 1.60 * 0.0005)
        - (16_500 * 1.60 + 5.0))


# ---------------------------------------------------------------------------
# e3: the ledger-mark reconciliation is fail-closed
# ---------------------------------------------------------------------------

def test_e3_ledger_mark_mismatch_fails_closed():
    daily = daily_frame(STOCK, [
        (D1, 2.00, 2.01, 1.99, 2.00, 2.00),
        (D2, 2.00, 2.01, 1.99, 2.00, 2.00)])
    half = half_frame(STOCK, [
        (D1, 'am', 2.00, 2.01, 1.99, 2.00),
        (D1, 'pm', 2.00, 2.01, 1.99, 2.00),
        (D2, 'am', 2.00, 2.01, 1.99, 2.00),
        (D2, 'pm', 2.00, 2.01, 1.99, 2.00)])
    marks = LedgerMarks(daily, half)
    # a ticker whose close column is a DIFFERENT price than the bar marks
    wrong = LedgerMarks(
        daily.with_columns(pl.when(pl.col('date') == D1)
                           .then(pl.lit(2.5)).otherwise(pl.col('close'))
                           .alias('close')), half)
    with pytest.raises(OverlayRunnerError, match='do not reconcile'):
        wrong.reconcile({'date': D1, 'session': 'pm', 'cash': 0.0,
                         'pending_am_to_pm': 0.0, 'pending_next_day': 0.0,
                         'equity_snapshot': 20_000.0,
                         'positions': [{'symbol': STOCK, 'shares': 10_000}]})
    # the faithful marks reconcile exactly
    assert marks.reconcile({
        'date': D1, 'session': 'pm', 'cash': 0.0, 'pending_am_to_pm': 0.0,
        'pending_next_day': 0.0, 'equity_snapshot': 20_000.0,
        'positions': [{'symbol': STOCK, 'shares': 10_000}]}) == 20_000.0
    # an unpriced symbol contributes nothing, exactly like the engine
    assert marks.reconcile({
        'date': D1, 'session': 'am', 'cash': 5.0, 'pending_am_to_pm': 1.0,
        'pending_next_day': 2.0, 'equity_snapshot': 8.0,
        'positions': [{'symbol': 'sh.999999', 'shares': 100}]}) == 8.0
