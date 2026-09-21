"""Unit tests for the account-level risk overlay (synthetic data only).

Each test pins one clause of ``docs/research/exp-20260920-account-risk-overlay-prereg.md``
and of ``docs/plans/daily-strategy-output-contract.md`` §4: the three frozen
configs (C0 constant 0.90; C1 ``close > SMA200``; C2 own high-water drawdown
``> 10%``), the asof-only rule (no future bar and no same-day close for an
11:30 decision), the immediate down-shift / gated up-shift ("状态变化才产生
调仓目标" plus the prereg's mandatory recovery and cooldown semantics), the
insufficient-data fail-closed rows, strict ordering, input immutability, the
invariant that only the attack multiplier is emitted, and the explicit bridge
to ``quant.portfolio.recommendations`` (``reduced`` must NOT block entries).
Two anchors pin the emitted exposure series against the registered research
machinery in ``quant.research.etf_rotation``: C1 against ``sma_trend_state`` +
``exposures_from_state``, C2 against ``pdd_risk_fn(0.10, 0.90, 0.40)`` on a path
that never parks inside the re-arm gap and against
``pdd_hysteresis_risk_fn(0.10, 0.05)`` on one that does; a further test pins the
deliberate boundary deviation (prereg "超过10%" = strict ``>``) from the
registered inclusive ``dd >= threshold``.  The half-session model itself is
taken from ``recommendations`` (``DecisionPoint`` / ``SESSION_BOUNDS``), the
recovery counters are pinned to be session-denominated (a 11:30 row re-reading
the previous close must not satisfy a confirmation), and the C1 lookback
contract is pinned with ``insufficient_data_rows``.  Synthetic numbers are
never profitability evidence; nothing here runs an experiment or consumes
trials.
"""
from __future__ import annotations

import copy
import dataclasses
import datetime as dt
from datetime import date, timedelta

import polars as pl
import pytest

from quant.portfolio import recommendations as rec
from quant.portfolio import risk_overlay as ro
from quant.research import etf_rotation as er

D = date
CLOSE = dt.time(15, 0)
NOON = dt.time(11, 30)

#: The frozen contract of one decision row (13 fields) plus its diagnostics.
CONTRACT_FIELDS = {
    "config_id",
    "decision_time",
    "exposure_multiplier",
    "risk_state",
    "action",
    "trigger_reason",
    "previous_state",
    "recovery_condition",
    "cooldown_until",
    "benchmark_as_of",
    "equity_as_of",
    "high_water_mark",
    "drawdown",
}


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def weekdays(n: int, start: D = D(2016, 1, 4)) -> list[D]:
    out: list[D] = []
    day = start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def series(cal: list[D], values: list[float]) -> list[tuple[D, float]]:
    return [(day, float(value)) for day, value in zip(cal, values)]


def decisions(cal: list[D], at: dt.time = CLOSE) -> list[dt.datetime]:
    return [dt.datetime.combine(day, at) for day in cal]


# C1: rise, trend break, trend recovery.  SMA5 forms at index 4, so
# risk-on on 4-8, risk-off on 9-12 and risk-on again from 13.
C1_VALUES = [10.0, 11, 12, 13, 14, 15, 16, 17, 18, 9, 10, 11, 12, 13, 14, 15]


def c1_policy(**overrides) -> ro.OverlayPolicy:
    """C1 with a 5-session SMA so a small synthetic series forms a window."""
    kwargs = {"sma_sessions": 5}
    kwargs.update(overrides)
    return ro.OverlayPolicy(ro.C1, ro.GateMechanism.INDEX_SMA, **kwargs)


def c2_policy(**overrides) -> ro.OverlayPolicy:
    kwargs: dict = {}
    kwargs.update(overrides)
    return ro.OverlayPolicy(ro.C2, ro.GateMechanism.ACCOUNT_DRAWDOWN, **kwargs)


def c1_rows(**overrides):
    cal = weekdays(16)
    return cal, ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C1,
        policy=c1_policy(**overrides),
        benchmark_close=series(cal, C1_VALUES),
    )


# --------------------------------------------------------------------------- #
# frozen configs
# --------------------------------------------------------------------------- #
def test_frozen_policies_match_the_prereg_table():
    assert ro.CONFIG_IDS == (ro.C0, ro.C1, ro.C2)
    assert set(ro.POLICIES) == set(ro.CONFIG_IDS)
    assert ro.POLICIES[ro.C0].mechanism is ro.GateMechanism.CONSTANT
    assert ro.POLICIES[ro.C1].mechanism is ro.GateMechanism.INDEX_SMA
    assert ro.POLICIES[ro.C1].sma_sessions == 200
    assert ro.POLICIES[ro.C2].mechanism is ro.GateMechanism.ACCOUNT_DRAWDOWN
    assert ro.POLICIES[ro.C2].drawdown_threshold == 0.10
    # one fixed down-shift: R9's registered re-arm gap T/2, no third level
    assert ro.POLICIES[ro.C2].rearm == pytest.approx(0.05)
    for policy in ro.POLICIES.values():
        assert (policy.level_on, policy.level_off) == (ro.LEVEL_ON, ro.LEVEL_OFF)
        assert policy.hard_stop_drawdown is None
        assert policy.recovery_confirmations == 2
        assert policy.cooldown_sessions == 3


def test_half_session_model_is_the_registered_one():
    assert ro.SESSION_CLOSE == rec.SESSION_BOUNDS[rec.Session.PM][1]
    assert ro.SAME_DAY_CLOSE_POINTS == {rec.DecisionPoint.DAY0_CLOSE,
                                        rec.DecisionPoint.PM_1500}
    day = D(2016, 1, 4)
    assert ro.decision_point_of(dt.datetime.combine(day, CLOSE)) is rec.DecisionPoint.PM_1500
    assert ro.decision_point_of(day) is rec.DecisionPoint.PM_1500
    assert ro.decision_point_of(dt.datetime.combine(day, NOON)) is rec.DecisionPoint.AM_1130
    assert ro.decision_point_of(dt.datetime(2016, 1, 4, 9, 0)) is rec.DecisionPoint.AM_1130
    cal = weekdays(4)
    # a 15:00-class point may read that day's close, an 11:30 point may not
    assert ro.close_asof(cal, trading_day=cal[2],
                         decision_point=rec.DecisionPoint.PM_1500) == cal[2]
    assert ro.close_asof(cal, trading_day=cal[2],
                         decision_point=rec.DecisionPoint.AM_1130) == cal[1]
    assert ro.close_asof(cal[:2], trading_day=cal[0],
                         decision_point=rec.DecisionPoint.AM_1130) is None


def test_row_exposes_the_frozen_contract_fields():
    cal, rows = c1_rows()
    names = {field.name for field in dataclasses.fields(ro.OverlayDecision)}
    assert CONTRACT_FIELDS <= names
    assert set(rows[0].as_dict()) == names
    assert rows[0].as_dict()["decision_time"] == dt.datetime.combine(cal[0], CLOSE).isoformat()
    assert rows[0].as_dict()["risk_state"] in {s.value for s in ro.OverlayState}
    assert rows[0].describe()  # display text is separate from the codes


# --------------------------------------------------------------------------- #
# C0 control anchor
# --------------------------------------------------------------------------- #
def test_c0_stays_at_the_control_level_without_any_input():
    cal = weekdays(6)
    rows = ro.resolve_overlay(decisions(cal), config_id=ro.C0)
    assert [r.exposure_multiplier for r in rows] == [ro.LEVEL_ON] * 6
    assert {r.risk_state for r in rows} == {ro.OverlayState.NORMAL}
    assert {r.action for r in rows} == {ro.OverlayAction.HOLD}
    assert {r.state_changed for r in rows} == {False}
    assert all(r.cooldown_until is None for r in rows)
    assert all(r.benchmark_as_of is None and r.equity_as_of is None for r in rows)
    assert all(r.high_water_mark is None and r.drawdown is None for r in rows)
    assert rows[0].previous_state is None
    assert rows[1].previous_state is ro.OverlayState.NORMAL


def test_c0_ignores_a_crashing_benchmark_and_a_crashing_account():
    cal = weekdays(8)
    rows = ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C0,
        benchmark_close=series(cal, [100.0, 99, 98, 97, 50, 40, 30, 20]),
        equity=series(cal, [100.0, 99, 98, 97, 50, 40, 30, 20]),
    )
    assert [r.exposure_multiplier for r in rows] == [ro.LEVEL_ON] * 8
    assert {r.risk_state for r in rows} == {ro.OverlayState.NORMAL}
    # diagnostics are still reported honestly for the control row
    assert rows[7].high_water_mark == 100.0
    assert rows[7].drawdown == pytest.approx(0.80)
    assert rows[7].equity_as_of == cal[7]


# --------------------------------------------------------------------------- #
# C1: asof, single reduction, recovery gate
# --------------------------------------------------------------------------- #
def test_c1_exposure_series_equals_the_registered_trend_machinery():
    cal = weekdays(16)
    closes = C1_VALUES
    rows = ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C1,
        # gate disabled: recover on the first qualifying decision point
        policy=c1_policy(recovery_confirmations=1, cooldown_sessions=0),
        benchmark_close=series(cal, closes),
    )
    frame = pl.DataFrame({"trade_date": cal, "close": closes}).sort("trade_date")
    registered_state = er.sma_trend_state(frame, cal, 5)
    registered = er.exposures_from_state(registered_state, ro.LEVEL_ON, ro.LEVEL_OFF)
    assert [r.exposure_multiplier for r in rows] == [registered[day] for day in cal]
    assert ([r.risk_state is ro.OverlayState.NORMAL for r in rows]
            == [registered_state[day] for day in cal])
    # the warm-up rows are the same 0.40 fallback, labelled honestly
    assert rows[3].exposure_multiplier == ro.LEVEL_OFF
    assert rows[3].risk_state is ro.OverlayState.INSUFFICIENT_DATA
    assert registered_state[cal[3]] is False


def test_c1_asof_ignores_a_future_close_and_uses_the_previous_session_at_1130():
    cal = weekdays(11)
    closes = C1_VALUES[:10] + [30.0]
    moments = (decisions(cal[:9])
               + [dt.datetime.combine(cal[9], NOON)]
               + [dt.datetime.combine(cal[9], CLOSE)])
    rows = ro.resolve_overlay(
        moments, config_id=ro.C1, policy=c1_policy(), benchmark_close=series(cal, closes)
    )
    at_noon, at_close = rows[9], rows[10]
    assert at_noon.decision_time.time() == NOON
    assert at_noon.benchmark_as_of == cal[8]          # previous session close
    assert at_close.benchmark_as_of == cal[9]         # same-day close
    assert at_noon.benchmark_close == closes[8]
    assert at_close.benchmark_close == closes[9]

    # appending a later, crashing bar must not move an earlier row
    later = ro.resolve_overlay(
        moments,
        config_id=ro.C1,
        policy=c1_policy(),
        benchmark_close=series(cal[:10], closes[:10]) + [(cal[10], 1.0)],
    )
    assert [r.as_dict() for r in later[:11]] == [r.as_dict() for r in rows[:11]]


def test_c1_trend_break_reduces_exactly_once_then_holds():
    cal, rows = c1_rows()
    assert rows[8].risk_state is ro.OverlayState.NORMAL   # still above SMA5 (18 > 16)
    reduces = [i for i, row in enumerate(rows) if row.action is ro.OverlayAction.REDUCE_ATTACK]
    assert reduces == [9]
    assert rows[9].exposure_multiplier == ro.LEVEL_OFF
    assert rows[9].risk_state is ro.OverlayState.REDUCED
    assert rows[9].trigger_reason == "index_at_or_below_trend_sma"
    assert rows[9].previous_state is ro.OverlayState.NORMAL
    for row in rows[10:13]:
        assert row.action is ro.OverlayAction.HOLD
        assert row.state_changed is False
        assert row.exposure_multiplier == ro.LEVEL_OFF
        assert row.trigger_reason == "index_at_or_below_trend_sma"


def test_c1_recovery_waits_for_confirmation_then_restores():
    cal, rows = c1_rows()          # defaults: 2 confirmations, 3-decision cooldown
    assert rows[13].benchmark_close > rows[13].benchmark_sma
    assert rows[13].action is ro.OverlayAction.HOLD            # streak 1 of 2
    assert rows[13].risk_state is ro.OverlayState.REDUCED
    assert rows[13].trigger_reason == "recovery_pending_confirmation"
    assert rows[13].recovery_condition == "close_gt_sma5_confirm2_cooldown3"
    assert rows[14].action is ro.OverlayAction.RESTORE_ATTACK
    assert rows[14].exposure_multiplier == ro.LEVEL_ON
    assert rows[14].risk_state is ro.OverlayState.NORMAL
    assert rows[14].state_changed is True
    assert rows[14].trigger_reason == "recovery_confirmed"
    assert rows[15].action is ro.OverlayAction.HOLD
    assert rows[15].trigger_reason == "index_above_trend_sma"


def test_c1_cooldown_blocks_an_immediate_recovery():
    cal = weekdays(12)
    closes = [10.0, 11, 12, 13, 14, 15, 9, 9.5, 20, 21, 22, 23]
    rows = ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C1,
        policy=c1_policy(recovery_confirmations=1, cooldown_sessions=3),
        benchmark_close=series(cal, closes),
    )
    assert rows[6].action is ro.OverlayAction.REDUCE_ATTACK          # 9 <= SMA5 12.6
    assert rows[6].cooldown_until == cal[9]          # session-denominated
    # the trend is back on at index 8, but the cooldown outranks it
    assert rows[8].benchmark_close > rows[8].benchmark_sma
    assert rows[8].action is ro.OverlayAction.HOLD
    assert rows[8].risk_state is ro.OverlayState.REDUCED
    assert rows[8].trigger_reason == "recovery_pending_cooldown"
    assert rows[8].cooldown_until == cal[9]
    assert rows[9].action is ro.OverlayAction.RESTORE_ATTACK
    assert rows[9].exposure_multiplier == ro.LEVEL_ON

    # with no cooldown the single-session confirmation restores one row sooner
    faster = ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C1,
        policy=c1_policy(recovery_confirmations=1, cooldown_sessions=0),
        benchmark_close=series(cal, closes),
    )
    assert faster[8].action is ro.OverlayAction.RESTORE_ATTACK


def test_c1_warm_up_and_missing_benchmark_observations_fail_closed():
    cal = weekdays(16)
    rows = ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C1,
        policy=c1_policy(),
        benchmark_close=series(cal, C1_VALUES),
    )
    for row in rows[:4]:                      # SMA5 not yet formed
        assert row.risk_state is ro.OverlayState.INSUFFICIENT_DATA
        assert row.exposure_multiplier == ro.LEVEL_OFF
        assert row.benchmark_sma is None
        assert row.benchmark_as_of is not None
        assert row.trigger_reason == "sma_warmup_incomplete"
    assert rows[0].action is ro.OverlayAction.FAIL_CLOSED
    assert rows[1].action is ro.OverlayAction.HOLD
    assert rows[4].action is ro.OverlayAction.RESTORE_ATTACK   # window formed, trend on
    assert rows[4].exposure_multiplier == ro.LEVEL_ON

    late = ro.resolve_overlay(
        decisions(cal[:6]),
        config_id=ro.C1,
        policy=c1_policy(),
        benchmark_close=series(cal[3:], C1_VALUES[3:6]),
    )
    assert late[0].benchmark_as_of is None
    assert late[0].trigger_reason == "benchmark_observation_missing"
    assert late[0].action is ro.OverlayAction.FAIL_CLOSED


# --------------------------------------------------------------------------- #
# C2: high-water mark, drawdown, boundary, anchors
# --------------------------------------------------------------------------- #
def test_c2_high_water_mark_and_drawdown_are_asof_running_peak_values():
    cal = weekdays(4)
    ladder = series(cal, [100.0, 120, 90, 120])
    peak = ro.running_peak_drawdown(ladder)
    assert peak[cal[0]] == (100.0, 0.0)
    assert peak[cal[1]] == (120.0, 0.0)
    assert peak[cal[2]][0] == 120.0
    assert peak[cal[2]][1] == pytest.approx(0.25)
    assert peak[cal[3]] == (120.0, 0.0)

    rows = ro.resolve_overlay(
        decisions(cal), config_id=ro.C2, policy=c2_policy(), equity=ladder)
    assert [r.high_water_mark for r in rows] == [100.0, 120.0, 120.0, 120.0]
    assert [r.drawdown for r in rows] == pytest.approx([0.0, 0.0, 0.25, 0.0])
    assert [r.equity_as_of for r in rows] == cal
    assert rows[2].action is ro.OverlayAction.REDUCE_ATTACK
    assert rows[3].risk_state is ro.OverlayState.REDUCED       # needs re-arm + gate
    assert rows[3].action is ro.OverlayAction.HOLD


def test_c2_exposure_series_equals_the_registered_pdd_machinery():
    # Path A never parks inside the re-arm gap: every judged session is either
    # deeper than 10% (off), at/inside 5% (re-arm) or a new high.  There the
    # strict prereg gate and the registered R9 re-arm gap must coincide with
    # the no-hysteresis registered PDD gate, session for session.
    cal_a = weekdays(8)
    path_a = series(cal_a, [100.0, 110, 105, 98, 130, 128, 127, 131])
    rows_a = ro.resolve_overlay(
        decisions(cal_a),
        config_id=ro.C2,
        policy=c2_policy(recovery_confirmations=1, cooldown_sessions=0),
        equity=path_a,
    )
    registered_off = er.pdd_risk_fn(0.10, ro.LEVEL_ON, ro.LEVEL_OFF)
    plain = [registered_off(day, value) for day, value in path_a]
    hysteresis = er.pdd_hysteresis_risk_fn(0.10, 0.05, ro.LEVEL_ON, ro.LEVEL_OFF)
    gapped = [hysteresis(day, value) for day, value in path_a]
    assert [r.exposure_multiplier for r in rows_a] == plain == gapped
    assert rows_a[3].action is ro.OverlayAction.REDUCE_ATTACK   # dd 10.9% > 10%
    assert rows_a[4].action is ro.OverlayAction.RESTORE_ATTACK  # new high re-arms

    # Path B parks at 6%: inside R9's registered re-arm gap (T/2 = 5%), so the
    # overlay holds off exactly like pdd_hysteresis_risk_fn and unlike
    # pdd_risk_fn, which re-arms as soon as dd <= 10%.
    cal_b = weekdays(6)
    path_b = series(cal_b, [100.0, 110, 98, 104, 104, 110])
    rows_b = ro.resolve_overlay(
        decisions(cal_b),
        config_id=ro.C2,
        policy=c2_policy(recovery_confirmations=1, cooldown_sessions=0),
        equity=path_b,
    )
    hysteresis_b = er.pdd_hysteresis_risk_fn(0.10, 0.05, ro.LEVEL_ON, ro.LEVEL_OFF)
    registered_off_b = er.pdd_risk_fn(0.10, ro.LEVEL_ON, ro.LEVEL_OFF)
    assert [r.exposure_multiplier for r in rows_b] == [
        hysteresis_b(day, value) for day, value in path_b]
    assert rows_b[3].drawdown == pytest.approx(1.0 - 104.0 / 110.0)
    assert rows_b[3].exposure_multiplier == ro.LEVEL_OFF       # 6% > 5%: still off
    assert registered_off_b(cal_b[3], 104.0) == ro.LEVEL_ON    # registered PDD: on
    assert rows_b[5].action is ro.OverlayAction.RESTORE_ATTACK

    # the frozen C2 additionally delays that re-arm with 2 confirmations and a
    # 3-session cooldown: on path A the new high is not enough by itself
    default_rows = ro.resolve_overlay(
        decisions(cal_a), config_id=ro.C2, policy=c2_policy(), equity=path_a)
    assert default_rows[4].exposure_multiplier == ro.LEVEL_OFF
    assert plain[4] == ro.LEVEL_ON
    assert default_rows[5].trigger_reason == "recovery_pending_cooldown"
    assert default_rows[6].action is ro.OverlayAction.RESTORE_ATTACK


def test_recovery_counters_are_denominated_in_sessions_not_decision_points():
    # d6 15:00 lowers; d7 11:30 re-reads d6's close (no new session); only the
    # d7 15:00 row is the first recovery session, so 2 confirmations are met at
    # d8 15:00 - not one decision point earlier.
    cal = weekdays(10)
    closes = [10.0, 11, 12, 13, 14, 15, 9, 20, 21, 22]
    moments = [dt.datetime.combine(cal[6], CLOSE),
               dt.datetime.combine(cal[7], NOON),
               dt.datetime.combine(cal[7], CLOSE),
               dt.datetime.combine(cal[8], NOON),
               dt.datetime.combine(cal[8], CLOSE),
               dt.datetime.combine(cal[9], CLOSE)]
    rows = ro.resolve_overlay(
        moments,
        config_id=ro.C1,
        policy=c1_policy(recovery_confirmations=2, cooldown_sessions=0),
        benchmark_close=series(cal, closes),
    )
    assert rows[0].action is ro.OverlayAction.REDUCE_ATTACK
    assert rows[0].benchmark_as_of == cal[6]
    assert rows[1].benchmark_as_of == cal[6]                  # d7 11:30 re-reads d6
    assert rows[1].risk_state is ro.OverlayState.REDUCED
    assert rows[1].action is ro.OverlayAction.HOLD
    assert rows[2].benchmark_as_of == cal[7]                  # first recovery session
    assert rows[2].action is ro.OverlayAction.HOLD
    assert rows[2].trigger_reason == "recovery_pending_confirmation"
    assert rows[3].benchmark_as_of == cal[7]                  # same session again
    assert rows[3].action is ro.OverlayAction.HOLD            # must NOT count twice
    assert rows[3].trigger_reason == "recovery_pending_confirmation"
    assert rows[4].benchmark_as_of == cal[8]                  # second session
    assert rows[4].action is ro.OverlayAction.RESTORE_ATTACK
    assert rows[5].action is ro.OverlayAction.HOLD


def test_c1_lookback_of_sma_sessions_before_the_first_decision_is_required():
    cal = weekdays(260)
    closes = [100.0 + i * 0.5 for i in range(260)]
    ladder = series(cal, closes)
    short = ro.resolve_overlay(
        decisions(cal), config_id=ro.C1,
        policy=ro.OverlayPolicy(ro.C1, ro.GateMechanism.INDEX_SMA),
        benchmark_close=ladder,
    )
    # only 200 bars after the first decision: the whole window is a prologue
    assert len(ro.insufficient_data_rows(short)) == 199
    assert short[0].trigger_reason == "sma_warmup_incomplete"
    assert short[0].exposure_multiplier == ro.LEVEL_OFF
    # a benchmark carrying 200 sessions before the first decision has none
    warm = ro.resolve_overlay(
        decisions(cal[200:]), config_id=ro.C1,
        policy=ro.OverlayPolicy(ro.C1, ro.GateMechanism.INDEX_SMA),
        benchmark_close=ladder,
    )
    assert ro.insufficient_data_rows(warm) == ()
    assert warm[0].benchmark_as_of == cal[200]
    assert warm[0].benchmark_sma is not None
    assert {r.risk_state for r in warm} == {ro.OverlayState.NORMAL}


def test_decision_points_may_be_supplied_and_must_match():
    cal = weekdays(4)
    closes = [10.0, 11, 12, 13]
    moments = [dt.datetime.combine(day, CLOSE) for day in cal]
    explicit = ro.resolve_overlay(
        moments,
        config_id=ro.C1,
        policy=c1_policy(),
        decision_points=[rec.DecisionPoint.PM_1500] * 4,
        benchmark_close=series(cal, closes),
    )
    derived = ro.resolve_overlay(
        moments, config_id=ro.C1, policy=c1_policy(),
        benchmark_close=series(cal, closes))
    assert [r.as_dict() for r in explicit] == [r.as_dict() for r in derived]
    early = ro.resolve_overlay(
        [dt.datetime.combine(cal[3], CLOSE)],
        config_id=ro.C1,
        policy=c1_policy(),
        decision_points=[rec.DecisionPoint.AM_1130],
        benchmark_close=series(cal, closes),
    )
    assert early[0].benchmark_as_of == cal[2]      # 11:30 cannot read d3's close
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay(moments, config_id=ro.C1, policy=c1_policy(),
                           decision_points=[rec.DecisionPoint.PM_1500],
                           benchmark_close=series(cal, closes))
    assert exc.value.reason is ro.OverlayReason.INVALID_FIELD


def test_c2_drawdown_boundary_is_strict_not_inclusive():
    # 1 - 75/100 == 0.25 exactly, so the comparator is exercised exactly
    cal = weekdays(3)
    ladder = series(cal, [100.0, 75.0, 70.0])
    policy = c2_policy(drawdown_threshold=0.25, rearm_drawdown=0.10)
    rows = ro.resolve_overlay(decisions(cal), config_id=ro.C2, policy=policy, equity=ladder)
    assert rows[1].drawdown == 0.25
    assert rows[1].action is ro.OverlayAction.HOLD
    assert rows[1].exposure_multiplier == ro.LEVEL_ON          # prereg: "超过25%"
    assert rows[2].action is ro.OverlayAction.REDUCE_ATTACK
    # registered research variant uses dd >= threshold and fires at the boundary
    registered_fn = er.pdd_hysteresis_risk_fn(0.25, 0.10, ro.LEVEL_ON, ro.LEVEL_OFF)
    registered = [registered_fn(day, value) for day, value in ladder]
    assert registered[0] == ro.LEVEL_ON
    assert registered[1] == ro.LEVEL_OFF


def test_c2_missing_equity_observations_fail_closed_until_data_arrives():
    cal = weekdays(6)
    moments = decisions(cal)
    rows = ro.resolve_overlay(
        moments,
        config_id=ro.C2,
        policy=c2_policy(),
        equity=series(cal[2:], [100.0, 90.0, 90.0, 95.0]),
    )
    assert [r.risk_state for r in rows[:2]] == [ro.OverlayState.INSUFFICIENT_DATA] * 2
    assert rows[0].action is ro.OverlayAction.FAIL_CLOSED
    assert rows[0].equity_as_of is None and rows[0].drawdown is None
    assert rows[0].exposure_multiplier == ro.LEVEL_OFF
    # a data gap is not a risk trigger: the first usable row restores at once
    assert rows[2].action is ro.OverlayAction.RESTORE_ATTACK
    assert rows[2].exposure_multiplier == ro.LEVEL_ON


def test_c2_hard_stop_is_off_prereg_and_never_fires_without_it():
    cal = weekdays(4)
    ladder = series(cal, [100.0, 70.0, 69.0, 68.0])
    plain = ro.resolve_overlay(decisions(cal), config_id=ro.C2,
                               policy=c2_policy(), equity=ladder)
    assert all(row.risk_state is not ro.OverlayState.BLOCKED for row in plain)
    assert plain[1].risk_state is ro.OverlayState.REDUCED     # dd 30% > 10%
    blocked = ro.resolve_overlay(
        decisions(cal),
        config_id=ro.C2,
        policy=c2_policy(hard_stop_drawdown=0.25),
        equity=ladder,
    )
    assert blocked[0].risk_state is ro.OverlayState.NORMAL
    assert blocked[1].risk_state is ro.OverlayState.BLOCKED   # dd 30% > 25%
    assert blocked[1].action is ro.OverlayAction.BLOCK_NEW_ATTACK
    assert blocked[1].exposure_multiplier == ro.LEVEL_OFF     # E_t is the only lever
    assert blocked[2].action is ro.OverlayAction.HOLD         # state unchanged
    with pytest.raises(ro.RiskOverlayError) as exc:
        c2_policy(hard_stop_drawdown=1.5)
    assert exc.value.reason is ro.OverlayReason.INVALID_FIELD


# --------------------------------------------------------------------------- #
# cross-config invariants
# --------------------------------------------------------------------------- #
def test_only_two_exposure_levels_are_emitted_and_always_within_bounds():
    cal = weekdays(16)
    ladders = {
        ro.C1: ro.resolve_overlay(
            decisions(cal), config_id=ro.C1, policy=c1_policy(),
            benchmark_close=series(cal, C1_VALUES)),
        ro.C2: ro.resolve_overlay(
            decisions(cal), config_id=ro.C2, policy=c2_policy(),
            equity=series(cal, [100.0, 110, 105, 98, 103, 120, 118, 117, 119, 121,
                                99, 98, 97, 96, 95, 94])),
        ro.C0: ro.resolve_overlay(decisions(cal), config_id=ro.C0),
    }
    for config_id, rows in ladders.items():
        assert len(rows) == 16
        assert {row.config_id for row in rows} == {config_id}
        assert {row.exposure_multiplier for row in rows} <= {ro.LEVEL_ON, ro.LEVEL_OFF}
        assert all(0.0 <= row.exposure_multiplier <= 1.0 for row in rows)
        assert all(row.trigger_reason in ro.REASON_LABELS for row in rows)
        assert all(row.describe() for row in rows)
        assert all(row.action is ro.OverlayAction.HOLD or row.state_changed for row in rows)
        for i, row in enumerate(rows):
            assert row.previous_state == (rows[i - 1].risk_state if i else None)


def test_state_changes_are_the_only_rows_that_retarget():
    cal, rows = c1_rows()
    for previous, row in zip(rows, rows[1:]):
        same = row.risk_state is previous.risk_state
        assert (row.action is ro.OverlayAction.HOLD) == same


def test_inputs_are_never_mutated():
    cal = weekdays(16)
    moments = decisions(cal[:15]) + [dt.datetime.combine(cal[15], NOON)]
    bench = series(cal, C1_VALUES)
    ladder = series(cal, C1_VALUES)
    snap = (copy.deepcopy(moments), copy.deepcopy(bench), copy.deepcopy(ladder))
    ro.resolve_overlay(moments, config_id=ro.C1, policy=c1_policy(),
                       benchmark_close=bench, equity=ladder)
    assert moments == snap[0] and bench == snap[1] and ladder == snap[2]


# --------------------------------------------------------------------------- #
# fail-closed input contract
# --------------------------------------------------------------------------- #
def test_out_of_order_and_duplicate_decision_times_are_rejected():
    cal = weekdays(3)
    good = decisions(cal)
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay([good[1], good[0]], config_id=ro.C0)
    assert exc.value.reason is ro.OverlayReason.DECISION_TIMES_NOT_INCREASING
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay([good[0], good[0]], config_id=ro.C0)
    assert exc.value.reason is ro.OverlayReason.DECISION_TIMES_NOT_INCREASING


def test_observation_series_must_be_strictly_increasing():
    cal = weekdays(3)
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay(
            decisions(cal), config_id=ro.C1, policy=c1_policy(),
            benchmark_close=[(cal[1], 10.0), (cal[1], 11.0), (cal[2], 12.0)])
    assert exc.value.reason is ro.OverlayReason.SERIES_NOT_INCREASING


def test_missing_inputs_unknown_config_and_mismatched_policy_are_rejected():
    cal = weekdays(3)
    moments = decisions(cal)
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay(moments, config_id=ro.C1)
    assert exc.value.reason is ro.OverlayReason.MISSING_BENCHMARK_SERIES
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay(moments, config_id=ro.C2)
    assert exc.value.reason is ro.OverlayReason.MISSING_EQUITY_SERIES
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.policy_for("C9")
    assert exc.value.reason is ro.OverlayReason.UNKNOWN_CONFIG
    with pytest.raises(ro.RiskOverlayError) as exc:
        ro.resolve_overlay(moments, config_id=ro.C2, policy=c1_policy(),
                           benchmark_close=series(cal, [1.0, 2.0, 3.0]))
    assert exc.value.reason is ro.OverlayReason.CONFIG_POLICY_MISMATCH


# --------------------------------------------------------------------------- #
# plan-layer bridge
# --------------------------------------------------------------------------- #
EQUITY = 200_000.0
MARKET_AS_OF = dt.datetime(2026, 9, 21, 15, 0)
VALID_FROM = dt.datetime(2026, 9, 22, 9, 30)
VALID_UNTIL = dt.datetime(2026, 9, 22, 11, 30)


def _buy_item() -> rec.RecommendationItem:
    price, stop, quantity = 10.0, 9.0, 1000
    return rec.RecommendationItem(
        symbol="600000",
        name="name-600000",
        sleeve=rec.Sleeve.ATTACK,
        action=rec.Action.NEW,
        current_quantity=0,
        recommended_quantity=quantity,
        target_weight=0.05,
        valid_until=VALID_UNTIL,
        trigger_reason="signal fired",
        invalidation_reason="signal invalidated",
        price_lower=round(price * 0.99, 3),
        price_upper=price,
        stop_price=stop,
        risk_r=rec.risk_amount(quantity, price, stop, sleeve=rec.Sleeve.ATTACK,
                               trade_date=dt.date(2026, 9, 22)),
    )


def _build_plan(row: ro.OverlayDecision) -> rec.RecommendationPlan:
    account = rec.AccountSnapshot(
        snapshot_version="acct-1",
        as_of=MARKET_AS_OF,
        strategy_version="strat-risk-overlay",
        market_as_of=MARKET_AS_OF,
        equity=EQUITY,
        cash=EQUITY,
        positions=(),
    )
    return rec.build_plan(
        decision_point=rec.DecisionPoint.DAY0_CLOSE,
        generated_at=MARKET_AS_OF,
        identity=rec.PlanIdentity(
            strategy_version="strat-risk-overlay",
            market_as_of=MARKET_AS_OF,
            account_snapshot_version="acct-1",
        ),
        account=account,
        recommendation_version=f"rec-{row.config_id}-{row.decision_time:%Y%m%d%H%M}",
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        items=(_buy_item(),),
        risk_state=ro.to_plan_risk_state(row.risk_state),
        account_action=ro.to_plan_account_action(row.action),
    )


def test_bridge_maps_every_overlay_state_and_action():
    assert ro.to_plan_risk_state(ro.OverlayState.NORMAL) is rec.RiskState.NORMAL
    assert ro.to_plan_risk_state(ro.OverlayState.REDUCED) is rec.RiskState.CAUTION
    assert ro.to_plan_risk_state(ro.OverlayState.BLOCKED) is rec.RiskState.RISK_OFF
    assert ro.to_plan_risk_state(ro.OverlayState.INSUFFICIENT_DATA) is rec.RiskState.RISK_OFF
    assert ro.to_plan_account_action(ro.OverlayAction.HOLD) is rec.Action.NO_ACTION
    assert ro.to_plan_account_action(ro.OverlayAction.REDUCE_ATTACK) is rec.Action.NO_ACTION
    assert ro.to_plan_account_action(ro.OverlayAction.RESTORE_ATTACK) is rec.Action.NO_ACTION
    assert (ro.to_plan_account_action(ro.OverlayAction.BLOCK_NEW_ATTACK)
            is rec.Action.ACCOUNT_DELEVER)
    assert (ro.to_plan_account_action(ro.OverlayAction.FAIL_CLOSED)
            is rec.Action.ACCOUNT_DELEVER)
    assert ro.attack_entry_allowed(ro.OverlayState.NORMAL) is True
    assert ro.attack_entry_allowed(ro.OverlayState.REDUCED) is True
    assert ro.attack_entry_allowed(ro.OverlayState.BLOCKED) is False
    assert ro.attack_entry_allowed(ro.OverlayState.INSUFFICIENT_DATA) is False
    for call in (ro.to_plan_risk_state, ro.to_plan_account_action, ro.attack_entry_allowed):
        with pytest.raises(ro.RiskOverlayError):
            call("normal")


def test_reduced_state_does_not_block_new_attack_entries_in_the_plan_layer():
    cal, rows = c1_rows()
    reduced = [row for row in rows if row.risk_state is ro.OverlayState.REDUCED][0]
    plan = _build_plan(reduced)
    assert plan.entry_paused is False
    assert [item.symbol for item in plan.items] == ["600000"]

    dry = [row for row in rows if row.risk_state is ro.OverlayState.INSUFFICIENT_DATA][0]
    with pytest.raises(rec.RecommendationError) as exc:
        _build_plan(dry)
    assert exc.value.reason is rec.Reason.ENTRY_BLOCKED_BY_RISK_STATE
