"""Unit tests for the strategy-plan assembly adapter (synthetic data only).

Each test pins one clause of the registered contracts: the account-level overlay
scales the attack sleeve only (``exp-20260920-account-risk-overlay-prereg`` 1), the
plan-level limits stay with ``recommendations.validate_plan`` (25% per symbol, 100%
gross, 4 attack / 3 defense / 7 total, 3 new entries), p3-band-contract 7.7 M2
over-cap buys are voided whole while drifted holdings are only carried, one item per
held symbol, and every fail-closed path raises a stable code instead of defaulting.
Synthetic numbers are never profitability evidence.
"""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from quant.portfolio import recommendations as rec
from quant.portfolio import risk_overlay as ro
from quant.portfolio import strategy_plan as sp

STRATEGY = "strat-r16-20260918"
DAY0 = dt.date(2026, 9, 21)
DAY1 = dt.date(2026, 9, 22)
DAY2 = dt.date(2026, 9, 23)
MARKET_AS_OF = dt.datetime(2026, 9, 21, 15, 0)
GENERATED_AT = MARKET_AS_OF
EQUITY = 200_000.0
REC_VERSION = "rec-20260921T1500-day0"


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def position(
    symbol,
    *,
    quantity,
    sleeve=rec.Sleeve.ATTACK,
    sellable=None,
    cost=10.0,
    last=10.0,
    name=None,
):
    return rec.Position(
        symbol=symbol,
        name=name or f"name-{symbol}",
        sleeve=sleeve,
        quantity=quantity,
        sellable_quantity=quantity if sellable is None else sellable,
        average_cost=cost,
        last_price=last,
    )


def account(
    *,
    positions=(),
    equity=EQUITY,
    cash=None,
    version="acct-1",
    as_of=GENERATED_AT,
    market_as_of=MARKET_AS_OF,
    strategy=STRATEGY,
):
    positions = tuple(positions)
    if cash is None:
        cash = equity - sum(item.market_value for item in positions)
    return rec.AccountSnapshot(
        snapshot_version=version,
        as_of=as_of,
        strategy_version=strategy,
        market_as_of=market_as_of,
        equity=equity,
        cash=cash,
        positions=positions,
    )


def band(price, width=0.01):
    return round(price * (1.0 - width), 3), price


def attack(
    symbol,
    *,
    base,
    price=10.0,
    stop=9.0,
    action=rec.Action.NEW,
    previous_action=None,
    change_reason="",
    with_band=True,
    **kwargs,
):
    lower, upper = band(price) if with_band else (None, None)
    return sp.AttackCandidate(
        symbol=symbol,
        name=f"name-{symbol}",
        base_target_weight=base,
        trigger_reason="signal fired",
        invalidation_reason="signal invalidated",
        stop_price=stop,
        reference_price=price,
        price_lower=lower,
        price_upper=upper,
        action=action,
        previous_action=previous_action,
        change_reason=change_reason,
        **kwargs,
    )


def defense(
    symbol,
    *,
    target,
    price=5.0,
    action=rec.Action.NEW,
    previous_action=None,
    change_reason="",
    with_band=True,
    **kwargs,
):
    lower, upper = band(price) if with_band else (None, None)
    return sp.DefenseCandidate(
        symbol=symbol,
        name=f"name-{symbol}",
        target_weight=target,
        trigger_reason="defense state",
        invalidation_reason="state switched",
        reference_price=price,
        price_lower=lower,
        price_upper=upper,
        action=action,
        previous_action=previous_action,
        change_reason=change_reason,
        **kwargs,
    )


def c0_rows(moments=(MARKET_AS_OF,)):
    """Control-group rows: constant NORMAL / E_t = 0.90, no series needed."""

    return ro.resolve_overlay(list(moments), config_id=ro.C0)


def c1_row(*, normal=False, warmup=False, at=MARKET_AS_OF):
    """A real C1 row: benchmark above the trend SMA (NORMAL) or at/below it (REDUCED)."""

    policy = dataclasses.replace(ro.policy_for(ro.C1), sma_sessions=3)
    if warmup:
        series = [(DAY0, 9.0)]
    elif normal:
        series = [(dt.date(2026, 9, 16), 9.0), (dt.date(2026, 9, 17), 9.0),
                  (dt.date(2026, 9, 18), 9.0), (DAY0, 12.0)]
    else:
        series = [(dt.date(2026, 9, 16), 10.0), (dt.date(2026, 9, 17), 10.0),
                  (dt.date(2026, 9, 18), 10.0), (DAY0, 9.0)]
    return ro.resolve_overlay(
        [at], config_id=ro.C1, policy=policy, benchmark_close=series
    )[0]


def c2_row(*, reduced=True, at=MARKET_AS_OF):
    """A real C2 row from the confirmed equity series (own high-water drawdown)."""

    series = (
        [(dt.date(2026, 9, 18), 110_000.0), (DAY0, 90_000.0)]
        if reduced
        else [(dt.date(2026, 9, 18), 90_000.0), (DAY0, 110_000.0)]
    )
    return ro.resolve_overlay([at], config_id=ro.C2, equity=series)[0]


def blocked_row(*, at=MARKET_AS_OF):
    """A BLOCKED row, reachable only through an explicitly off-prereg hard stop."""

    policy = dataclasses.replace(ro.policy_for(ro.C2), hard_stop_drawdown=0.15)
    series = [(dt.date(2026, 9, 18), 110_000.0), (DAY0, 80_000.0)]
    row = ro.resolve_overlay([at], config_id=ro.C2, policy=policy, equity=series)[0]
    assert row.risk_state is ro.OverlayState.BLOCKED
    assert row.action is ro.OverlayAction.BLOCK_NEW_ATTACK
    return row


def assemble(
    acct,
    row,
    *,
    attacks=(),
    defenses=(),
    carried_stops=None,
    decision_point=rec.DecisionPoint.DAY0_CLOSE,
    trading_day=DAY0,
    next_trading_day=DAY1,
    policy=None,
    generated_at=GENERATED_AT,
    version=REC_VERSION,
):
    return sp.assemble_plan(
        decision_point=decision_point,
        trading_day=trading_day,
        generated_at=generated_at,
        account=acct,
        overlay=row,
        recommendation_version=version,
        attack_candidates=list(attacks),
        defense_candidates=list(defenses),
        carried_stops=carried_stops,
        next_trading_day=next_trading_day,
        policy=policy,
    )


def reason_of(exc_info):
    value = exc_info.value
    assert isinstance(value, sp.StrategyPlanError)
    return value.reason


def notes(plan):
    return sp.parse_notes(plan.note)


# --------------------------------------------------------------------------- #
# the overlay scales the attack sleeve only
# --------------------------------------------------------------------------- #
def test_c0_scales_attack_and_leaves_defense_untouched():
    acct = account()
    plan = assemble(
        acct,
        c0_rows()[0],
        attacks=[attack("600000", base=0.10)],
        defenses=[defense("510300", target=0.10)],
    )

    rechecked = rec.validate_plan(plan, account=acct)
    assert plan.risk_state is rec.RiskState.NORMAL
    assert plan.account_action is rec.Action.NO_ACTION
    assert plan.items[0].action is rec.Action.NEW
    # 0.10 base x 0.90 overlay, whole lots off the reference price
    assert plan.items[0].recommended_quantity == 1800
    assert plan.items[0].target_weight == pytest.approx(0.09)
    # the defense target is registered as an absolute weight, never multiplied
    assert plan.items[1].sleeve is rec.Sleeve.DEFENSE
    assert plan.items[1].recommended_quantity == 4000
    assert plan.items[1].target_weight == pytest.approx(0.10)
    assert rechecked.total_weight == pytest.approx(0.19)
    assert rechecked.attack_weight == pytest.approx(0.09)
    assert rechecked.defense_weight == pytest.approx(0.10)
    assert sp.parse_notes(plan.note) == {}


def test_c1_reduced_row_retargets_attack_but_keeps_entries_open():
    row = c1_row()
    assert row.risk_state is ro.OverlayState.REDUCED
    assert row.exposure_multiplier == ro.LEVEL_OFF == 0.40
    acct = account()
    plan = assemble(acct, row, attacks=[attack("600000", base=0.10)])

    rec.validate_plan(plan, account=acct)
    assert plan.risk_state is rec.RiskState.CAUTION
    # ACCOUNT_DELEVER here would make build_plan refuse the reduced-size entry
    assert plan.account_action is rec.Action.NO_ACTION
    assert plan.entry_paused is False
    assert plan.items[0].action is rec.Action.NEW
    assert plan.items[0].recommended_quantity == 800
    assert plan.items[0].target_weight == pytest.approx(0.04)


def test_c2_drawdown_row_scales_attack_the_same_way():
    row = c2_row()
    assert row.risk_state is ro.OverlayState.REDUCED
    acct = account()
    plan = assemble(acct, row, attacks=[attack("600000", base=0.10)])

    rec.validate_plan(plan, account=acct)
    assert plan.items[0].recommended_quantity == 800
    assert plan.items[0].target_weight == pytest.approx(0.04)


def test_normal_and_reduced_rows_differ_only_by_the_multiplier():
    acct = account()
    on = assemble(acct, c1_row(normal=True), attacks=[attack("600000", base=0.10)])
    off = assemble(acct, c1_row(), attacks=[attack("600000", base=0.10)])

    assert on.risk_state is rec.RiskState.NORMAL
    assert off.risk_state is rec.RiskState.CAUTION
    assert on.items[0].target_weight == pytest.approx(0.09)
    assert off.items[0].target_weight == pytest.approx(0.04)


# --------------------------------------------------------------------------- #
# the entry gate
# --------------------------------------------------------------------------- #
def test_insufficient_data_closes_the_gate_without_raising_the_plan():
    row = c1_row(warmup=True)
    assert row.risk_state is ro.OverlayState.INSUFFICIENT_DATA
    assert row.action is ro.OverlayAction.FAIL_CLOSED
    assert row.exposure_multiplier == ro.LEVEL_OFF
    acct = account(positions=[position("600000", quantity=1000)])
    plan = assemble(
        acct,
        row,
        attacks=[
            attack("600002", base=0.05),
            attack(
                "600000",
                base=0.001,
                action=rec.Action.STOP_LOSS,
                previous_action=rec.Action.HOLD,
            ),
        ],
        defenses=[defense("510300", target=0.05)],
    )

    rec.validate_plan(plan, account=acct)
    assert plan.risk_state is rec.RiskState.RISK_OFF
    assert plan.account_action is rec.Action.ACCOUNT_DELEVER
    assert set(notes(plan)[sp.ENTRY_BLOCKED]) == {"600002", "510300"}
    # a risk exit is not new exposure and stays available
    exit_item = plan.item("600000")
    assert exit_item.action is rec.Action.STOP_LOSS
    assert exit_item.recommended_quantity == 1000


def test_closed_gate_suppresses_the_add_of_a_partially_built_attack_name():
    held = position("600000", quantity=400)  # 0.02 of equity
    acct = account(positions=[held])
    candidate = attack("600000", base=0.10, action=rec.Action.ADD,
                       previous_action=rec.Action.NEW)

    # control group: gate open -> the add is a real buy
    on = assemble(acct, c0_rows()[0], attacks=[candidate])
    assert on.item("600000").action is rec.Action.ADD
    assert on.item("600000").recommended_quantity == 1400

    # closed gate: build_plan refuses every attack buy, so the add must degrade
    off = assemble(acct, c1_row(warmup=True), attacks=[candidate])
    rec.validate_plan(off, account=acct)
    item = off.item("600000")
    assert item.action is rec.Action.HOLD
    assert item.recommended_quantity == 0
    assert item.target_weight == pytest.approx(held.weight(EQUITY))
    assert item.risk_r is not None and item.stop_price == 9.0
    assert notes(off)[sp.ENTRY_BLOCKED] == ("600000",)


# --------------------------------------------------------------------------- #
# 25% per symbol: void the order, never trim it (p3-band-contract 7.7 M2)
# --------------------------------------------------------------------------- #
def test_over_cap_buy_is_voided_whole_and_counted():
    acct = account()
    plan = assemble(
        acct,
        c0_rows()[0],
        attacks=[attack("600000", base=0.30), attack("600001", base=0.05)],
    )

    rec.validate_plan(plan, account=acct)
    assert plan.item("600000") is None
    assert plan.items == (plan.item("600001"),)
    assert plan.item("600001").recommended_quantity == 900
    assert notes(plan)[sp.WEIGHT_CAP_VOIDED] == ("600000",)


def test_over_cap_holding_is_not_force_reduced_but_a_rescale_candidate_is_honoured():
    drifted = position("600000", quantity=6000)  # 0.30 by price drift
    acct = account(positions=[drifted])

    # no candidate -> carried, never trimmed by this layer; the 25% gate belongs to
    # validate_plan and rejects a version that cannot legally hold it
    with pytest.raises(rec.RecommendationError) as caught:
        assemble(acct, c0_rows()[0])
    assert caught.value.reason is rec.Reason.SYMBOL_WEIGHT_LIMIT

    # the signal layer's explicit rescale is the only way out
    plan = assemble(
        acct,
        c0_rows()[0],
        attacks=[
            attack(
                "600000",
                base=0.20,
                action=rec.Action.REDUCE,
                previous_action=rec.Action.HOLD,
            )
        ],
    )
    rec.validate_plan(plan, account=acct)
    item = plan.item("600000")
    assert item.action is rec.Action.REDUCE
    assert item.recommended_quantity == 2400
    assert item.target_weight == pytest.approx(0.18)


# --------------------------------------------------------------------------- #
# limits stay with validate_plan; this layer only budgets cash and new entries
# --------------------------------------------------------------------------- #
def test_seat_and_gross_limits_are_left_to_the_validator():
    four = [position(f"60000{i}", quantity=4800) for i in range(4)]  # 4 x 0.24
    over_attack = account(positions=four, cash=30_000.0)
    with pytest.raises(rec.RecommendationError) as caught:
        # fifth attack symbol (gross 1.005 too) -> the registered gate rejects it
        assemble(over_attack, c0_rows()[0], attacks=[attack("600009", base=0.05)])
    assert caught.value.reason is rec.Reason.GROSS_EXPOSURE_LIMIT

    three_defense = [
        position(f"51{i:04d}", quantity=1920, sleeve=rec.Sleeve.DEFENSE, cost=10.0,
                 last=10.0)
        for i in range(3)
    ]
    account_four = rec.AccountSnapshot(
        snapshot_version="acct-1",
        as_of=GENERATED_AT,
        strategy_version=STRATEGY,
        market_as_of=MARKET_AS_OF,
        equity=EQUITY,
        cash=100_000.0,
        positions=tuple(three_defense),
    )
    with pytest.raises(rec.RecommendationError) as caught:
        assemble(account_four, c0_rows()[0], defenses=[defense("510300", target=0.02)])
    assert caught.value.reason is rec.Reason.DEFENSE_SLOT_LIMIT


def test_new_entry_cap_drops_the_surplus_without_padding():
    acct = account()
    five = [attack(f"60001{i}", base=0.02) for i in range(5)]
    plan = assemble(acct, c0_rows()[0], attacks=five)

    rec.validate_plan(plan, account=acct)
    assert len(plan.new_entry_items) == 3
    assert [item.symbol for item in plan.items] == ["600010", "600011", "600012"]
    assert set(notes(plan)[sp.NEW_ENTRY_CAP_VOIDED]) == {"600013", "600014"}

    # one candidate -> one item, never a padded plan
    single = assemble(acct, c0_rows()[0], attacks=[attack("600010", base=0.02)])
    assert len(single.items) == 1


def test_cash_budget_counts_fees_exactly_like_the_validator():
    cheap = account(cash=9003.0)
    plan = assemble(cheap, c0_rows()[0], attacks=[attack("600000", base=0.05)])
    assert plan.items == ()
    assert notes(plan)[sp.CASH_EXHAUSTED] == ("600000",)

    exact = account(cash=9005.0)
    plan = assemble(exact, c0_rows()[0], attacks=[attack("600000", base=0.05)])
    rec.validate_plan(plan, account=exact)
    assert plan.item("600000").recommended_quantity == 900


def test_sub_lot_candidate_is_dropped_and_disclosed():
    acct = account()
    plan = assemble(acct, c0_rows()[0], attacks=[attack("600000", base=0.0045, price=900.0)])

    assert plan.items == ()
    assert notes(plan)[sp.SUB_LOT_SKIPPED] == ("600000",)

    # a candidate whose scaled target is nothing at all is disclosed, not silent
    nothing = assemble(acct, c0_rows()[0], attacks=[attack("600001", base=0.0)])
    assert nothing.items == ()
    assert notes(nothing)[sp.SUB_LOT_SKIPPED] == ("600001",)


# --------------------------------------------------------------------------- #
# one item per held symbol, and the hazards that hide behind that rule
# --------------------------------------------------------------------------- #
def test_empty_account_yields_a_legal_empty_version():
    acct = account()
    plan = assemble(acct, c0_rows()[0])

    rec.validate_plan(plan, account=acct)
    assert plan.items == ()
    assert plan.entry_paused is True
    assert "本版不新增" in "\n".join(plan.render_lines())


def test_held_attack_symbol_without_a_base_target_is_carried_and_disclosed():
    stock = position("600000", quantity=1000)  # attack, 0.05
    etf = position("510300", quantity=4000, sleeve=rec.Sleeve.DEFENSE, cost=5.0, last=5.0)
    acct = account(positions=[stock, etf])
    plan = assemble(acct, c0_rows()[0])

    rec.validate_plan(plan, account=acct)
    assert [item.action for item in plan.items] == [rec.Action.NO_ACTION] * 2
    assert plan.item("510300").sleeve is rec.Sleeve.DEFENSE
    assert notes(plan)[sp.UNSCALED_ATTACK_HOLDING] == ("600000",)
    assert sp.UNSCALED_ATTACK_HOLDING in "\n".join(plan.render_lines())


def test_held_attack_candidate_without_a_stop_is_rejected_but_a_bare_hold_is_not():
    held = position("600000", quantity=1000)  # 0.05
    acct = account(positions=[held])

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            acct,
            c0_rows()[0],
            attacks=[
                attack(
                    "600000",
                    base=0.10,
                    action=rec.Action.ADD,
                    previous_action=rec.Action.NEW,
                    stop=None,
                )
            ],
        )
    assert reason_of(caught) is sp.StrategyPlanReason.MISSING_STOP

    # a held symbol with no candidate at all is a legal carry: no stop is required
    carried = assemble(acct, c0_rows()[0])
    assert carried.item("600000").action is rec.Action.NO_ACTION
    assert carried.item("600000").stop_price is None


def test_stop_at_or_above_the_mark_is_rejected_instead_of_minting_an_r():
    held = position("600000", quantity=1000, last=10.0)
    acct = account(positions=[held])
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            acct,
            c0_rows()[0],
            attacks=[
                attack(
                    "600000",
                    base=0.02,
                    stop=10.0,
                    action=rec.Action.REDUCE,
                    previous_action=rec.Action.HOLD,
                )
            ],
        )
    assert reason_of(caught) is sp.StrategyPlanReason.STOP_ALREADY_BREACHED


def test_order_that_the_scaling_leaves_without_work_is_disclosed_not_fatal():
    # base 0.05 x E_t 0.40 lands exactly on the carried 0.02: the add has nothing to do
    held = position("600000", quantity=400)
    acct = account(positions=[held])
    plan = assemble(
        acct,
        c1_row(),
        attacks=[
            attack("600000", base=0.05, action=rec.Action.ADD,
                   previous_action=rec.Action.NEW)
        ],
    )

    rec.validate_plan(plan, account=acct)
    item = plan.item("600000")
    assert item.action is rec.Action.HOLD
    assert item.recommended_quantity == 0
    assert item.target_weight == pytest.approx(held.weight(EQUITY))
    assert notes(plan)[sp.ORDER_NOT_REACHABLE] == ("600000",)


def test_blocked_row_blocks_attack_entries_but_keeps_the_defense_base_sleeve():
    assert blocked_row().risk_state is ro.OverlayState.BLOCKED
    acct = account()
    plan = assemble(
        acct,
        blocked_row(),
        attacks=[attack("600000", base=0.05)],
        defenses=[defense("510300", target=0.05)],
    )

    rec.validate_plan(plan, account=acct)
    assert plan.risk_state is rec.RiskState.RISK_OFF
    assert plan.account_action is rec.Action.ACCOUNT_DELEVER
    # block_new_attack is attack-scoped: the low-drawdown base sleeve stays available
    assert plan.item("600000") is None
    assert notes(plan)[sp.ENTRY_BLOCKED] == ("600000",)
    assert plan.item("510300").action is rec.Action.NEW
    assert plan.item("510300").recommended_quantity == 2000


def test_scaling_that_pulls_a_buy_below_the_carried_weight_becomes_a_de_lever():
    held = position("600000", quantity=2400)  # 0.12 of equity
    acct = account(positions=[held])
    candidate = attack("600000", base=0.20, action=rec.Action.ADD,
                       previous_action=rec.Action.NEW)

    # control arm: 0.20 x 0.90 = 0.18 is still above the carried 0.12 -> a real add
    on = assemble(acct, c0_rows()[0], attacks=[candidate])
    assert on.item("600000").action is rec.Action.ADD
    assert on.item("600000").recommended_quantity == 1200

    # lowered arm: 0.20 x 0.40 = 0.08 is below the carried 0.12 -> the de-lever sells
    off = assemble(acct, c1_row(), attacks=[candidate])
    rec.validate_plan(off, account=acct)
    item = off.item("600000")
    assert item.action is rec.Action.ACCOUNT_DELEVER
    assert item.recommended_quantity == 800
    assert item.target_weight == pytest.approx(0.08)
    assert item.target_weight < held.weight(EQUITY)
    assert item.stop_price == 9.0 and item.risk_r is not None
    assert "账户级降仓" in item.change_reason


def test_a_passive_label_carries_at_the_carried_weight_instead_of_being_trimmed():
    held = position("600000", quantity=2400)  # 0.12
    acct = account(positions=[held])
    # an explicit hold is authoritative: the item's target IS the carried weight, so a
    # restated base == carried must not be drained by E_t every decision point
    for row in (c1_row(), c0_rows()[0]):
        plan = assemble(
            acct,
            row,
            attacks=[attack("600000", base=0.12, action=rec.Action.HOLD)],
        )
        rec.validate_plan(plan, account=acct)
        item = plan.item("600000")
        assert item.action is rec.Action.HOLD
        assert item.recommended_quantity == 0
        assert item.target_weight == pytest.approx(held.weight(EQUITY))
        assert item.stop_price == 9.0 and item.risk_r is not None
        assert notes(plan) == {}


def test_a_base_flat_order_label_is_carried_not_turned_into_a_trim():
    held = position("600000", quantity=2400)  # 0.12
    acct = account(positions=[held])
    # base == carried with an add label: the candidate's own frame has nothing to do,
    # and 0.12 x 0.40 = 0.048 sitting below the weight must not become a sell
    plan = assemble(
        acct,
        c1_row(),
        attacks=[
            attack("600000", base=0.12, action=rec.Action.ADD,
                   previous_action=rec.Action.NEW)
        ],
    )

    rec.validate_plan(plan, account=acct)
    item = plan.item("600000")
    assert item.action is rec.Action.HOLD
    assert item.recommended_quantity == 0
    assert item.target_weight == pytest.approx(0.12)
    assert notes(plan)[sp.ORDER_NOT_REACHABLE] == ("600000",)


def test_labels_that_no_scaling_can_explain_are_still_rejected():
    held = position("600000", quantity=2400)  # 0.12
    acct = account(positions=[held])
    # a sell label with a base target above the carried weight
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            acct,
            c1_row(),
            attacks=[
                attack("600000", base=0.20, action=rec.Action.REDUCE,
                       previous_action=rec.Action.HOLD)
            ],
        )
    assert reason_of(caught) is sp.StrategyPlanReason.CANDIDATE_ACTION_MISMATCH

    # a passive label with a base target above the carried weight
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            acct,
            c1_row(),
            attacks=[attack("600000", base=0.20, action=rec.Action.NO_ACTION)],
        )
    assert reason_of(caught) is sp.StrategyPlanReason.CANDIDATE_ACTION_MISMATCH


def test_carried_stops_arm_the_carry_that_has_no_candidate():
    held = position("600000", quantity=1000)  # 0.05
    etf = position("510300", quantity=4000, sleeve=rec.Sleeve.DEFENSE, cost=5.0, last=5.0)
    acct = account(positions=[held, etf])
    plan = assemble(acct, c0_rows()[0], carried_stops={"600000": 9.0})

    rec.validate_plan(plan, account=acct)
    armed = plan.item("600000")
    assert armed.action is rec.Action.HOLD
    assert armed.stop_price == 9.0
    assert armed.risk_r == pytest.approx(rec.risk_amount(
        1000, 10.0, 9.0, sleeve=rec.Sleeve.ATTACK, trade_date=DAY1
    ))
    assert armed.recommended_quantity == 0
    assert notes(plan)[sp.UNSCALED_ATTACK_HOLDING] == ("600000",)

    # a stop book that cannot be used is rejected, never ignored
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], carried_stops={"600000": 9.0, "510300": 4.5})
    assert reason_of(caught) is sp.StrategyPlanReason.INVALID_CANDIDATE

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], carried_stops={"600001": 9.0})
    assert reason_of(caught) is sp.StrategyPlanReason.INVALID_CANDIDATE

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            account(positions=[held]),
            c0_rows()[0],
            carried_stops={"600000": 0.0},
        )
    assert reason_of(caught) is sp.StrategyPlanReason.INVALID_CANDIDATE

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            account(positions=[held]),
            c0_rows()[0],
            attacks=[
                attack("600000", base=0.05, action=rec.Action.HOLD)
            ],
            carried_stops={"600000": 9.0},
        )
    assert reason_of(caught) is sp.StrategyPlanReason.DUPLICATE_CANDIDATE

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(account(positions=[held]), c0_rows()[0], carried_stops={"600000": 10.0})
    assert reason_of(caught) is sp.StrategyPlanReason.STOP_ALREADY_BREACHED


def test_unsellable_reduce_degrades_to_hold_instead_of_an_illegal_order():
    held = position("600000", quantity=1000, sellable=0)
    acct = account(positions=[held])
    plan = assemble(
        acct,
        c0_rows()[0],
        attacks=[
            attack(
                "600000",
                base=0.02,
                action=rec.Action.REDUCE,
                previous_action=rec.Action.HOLD,
            )
        ],
    )

    rec.validate_plan(plan, account=acct)
    item = plan.item("600000")
    assert item.action is rec.Action.HOLD
    assert item.recommended_quantity == 0
    assert "可卖数量不足" in item.change_reason

    # a frozen defense exit carries as 不动 instead (no stop zone is needed there)
    etf = position("510300", quantity=4000, sellable=0, sleeve=rec.Sleeve.DEFENSE,
                   cost=5.0, last=5.0)
    defense_plan = assemble(
        account(positions=[etf]),
        c0_rows()[0],
        defenses=[
            defense("510300", target=0.0, price=5.0, action=rec.Action.STOP_LOSS,
                    previous_action=rec.Action.HOLD, with_band=True)
        ],
    )
    rec.validate_plan(defense_plan, account=account(positions=[etf]))
    carried = defense_plan.item("510300")
    assert carried.action is rec.Action.NO_ACTION
    assert carried.recommended_quantity == 0
    assert carried.stop_price is None and carried.risk_r is None


# --------------------------------------------------------------------------- #
# windows, identity and candidate hygiene
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "point,trading_day,next_day,expect",
    [
        (
            rec.DecisionPoint.DAY0_CLOSE,
            DAY0,
            DAY1,
            (dt.datetime(2026, 9, 22, 9, 30), dt.datetime(2026, 9, 22, 11, 30)),
        ),
        (
            rec.DecisionPoint.AM_1130,
            DAY1,
            None,
            (dt.datetime(2026, 9, 22, 13, 0), dt.datetime(2026, 9, 22, 15, 0)),
        ),
        (
            rec.DecisionPoint.PM_1500,
            DAY1,
            DAY2,
            (dt.datetime(2026, 9, 23, 9, 30), dt.datetime(2026, 9, 23, 11, 30)),
        ),
    ],
)
def test_every_decision_point_serves_its_registered_session(
    point, trading_day, next_day, expect
):
    moment = {
        rec.DecisionPoint.DAY0_CLOSE: MARKET_AS_OF,
        rec.DecisionPoint.AM_1130: dt.datetime(2026, 9, 22, 11, 30),
        rec.DecisionPoint.PM_1500: dt.datetime(2026, 9, 22, 15, 0),
    }[point]
    acct = account(as_of=moment, market_as_of=moment)
    row = ro.resolve_overlay([moment], config_id=ro.C0)[0]
    plan = assemble(
        acct,
        row,
        attacks=[attack("600000", base=0.05)],
        decision_point=point,
        trading_day=trading_day,
        next_trading_day=next_day,
        generated_at=moment,
    )

    assert (plan.valid_from, plan.valid_until) == expect
    assert plan.decision_point is point
    assert all(item.valid_until == plan.valid_until for item in plan.items)


def test_overlay_row_must_be_the_row_of_this_cut_off_and_day():
    acct = account()
    other = ro.resolve_overlay([dt.datetime(2026, 9, 22, 15, 0)], config_id=ro.C0)[0]
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, other)
    assert reason_of(caught) is sp.StrategyPlanReason.OVERLAY_MARKET_MISMATCH

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], trading_day=DAY1)
    assert reason_of(caught) is sp.StrategyPlanReason.DECISION_TIME_MISMATCH


def test_duplicate_and_missleeved_candidates_are_rejected():
    acct = account(positions=[position("510300", quantity=4000, sleeve=rec.Sleeve.DEFENSE)])
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[attack("600000", base=0.05)] * 2)
    assert reason_of(caught) is sp.StrategyPlanReason.DUPLICATE_CANDIDATE

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[attack("510300", base=0.05)])
    assert reason_of(caught) is sp.StrategyPlanReason.SLEEVE_MISMATCH

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            acct,
            c0_rows()[0],
            defenses=[
                defense(
                    "510300",
                    target=0.01,
                    action=rec.Action.ACCOUNT_DELEVER,
                )
            ],
        )
    assert reason_of(caught) is sp.StrategyPlanReason.CANDIDATE_ACTION_MISMATCH


def test_new_entry_action_is_required_off_position_and_forbidden_on_it():
    acct = account(positions=[position("600000", quantity=1000)])
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[attack("600000", base=0.10)])
    assert reason_of(caught) is sp.StrategyPlanReason.CANDIDATE_ACTION_MISMATCH

    empty = account()
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(
            empty,
            c0_rows()[0],
            attacks=[
                attack("600000", base=0.10, action=rec.Action.ADD,
                       previous_action=rec.Action.NEW)
            ],
        )
    assert reason_of(caught) is sp.StrategyPlanReason.CANDIDATE_ACTION_MISMATCH


def test_candidates_of_the_wrong_type_are_rejected():
    acct = account()
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[defense("510300", target=0.05)])
    assert reason_of(caught) is sp.StrategyPlanReason.INVALID_CANDIDATE

    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], defenses=[attack("600000", base=0.05)])
    assert reason_of(caught) is sp.StrategyPlanReason.INVALID_CANDIDATE


def test_missing_band_and_reason_fields_are_fail_closed():
    acct = account()
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[attack("600000", base=0.05, with_band=False)])
    assert reason_of(caught) is sp.StrategyPlanReason.MISSING_PRICE_BAND

    broken = dataclasses.replace(attack("600000", base=0.05), trigger_reason="  ")
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[broken])
    assert reason_of(caught) is sp.StrategyPlanReason.MISSING_TRIGGER_REASON

    silent = dataclasses.replace(attack("600000", base=0.05), invalidation_reason="")
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[silent])
    assert reason_of(caught) is sp.StrategyPlanReason.MISSING_INVALIDATION_REASON

    inverted = dataclasses.replace(
        attack("600000", base=0.05), price_lower=10.5, price_upper=10.0
    )
    with pytest.raises(sp.StrategyPlanError) as caught:
        assemble(acct, c0_rows()[0], attacks=[inverted])
    assert reason_of(caught) is sp.StrategyPlanReason.INVALID_CANDIDATE


# --------------------------------------------------------------------------- #
# end to end: one version carrying all eight actions, revalidated
# --------------------------------------------------------------------------- #
def test_one_version_can_carry_every_registered_action():
    positions = [
        position("600000", quantity=400),  # ADD
        position("600001", quantity=1000),  # ACCOUNT_DELEVER
        position("600002", quantity=1000),  # TAKE_PROFIT
        position("510300", quantity=4000, sleeve=rec.Sleeve.DEFENSE, cost=5.0, last=5.0),
        position("510500", quantity=4000, sleeve=rec.Sleeve.DEFENSE, cost=5.0, last=5.0),
        position("159915", quantity=4000, sleeve=rec.Sleeve.DEFENSE, cost=5.0, last=5.0),
    ]
    acct = account(positions=positions)
    plan = assemble(
        acct,
        c0_rows()[0],
        attacks=[
            attack("600000", base=0.05, action=rec.Action.ADD,
                   previous_action=rec.Action.NEW),
            attack("600001", base=0.02, action=rec.Action.ACCOUNT_DELEVER,
                   previous_action=rec.Action.HOLD),
            attack("600002", base=0.03, action=rec.Action.TAKE_PROFIT,
                   previous_action=rec.Action.HOLD),
            attack("600003", base=0.02),
        ],
        defenses=[
            defense("510300", target=0.05, price=5.0, action=rec.Action.STOP_LOSS,
                    previous_action=rec.Action.HOLD, with_band=True),
            defense("510500", target=0.06, price=5.0, action=rec.Action.REDUCE,
                    previous_action=rec.Action.HOLD, with_band=True),
            defense("159915", target=0.10, price=5.0, action=rec.Action.HOLD,
                    with_band=True),
        ],
    )

    exposure = rec.validate_plan(plan, account=acct)
    # eight registered actions need eight symbols and the portfolio admits seven
    # seats, so one version carries seven; NO_ACTION is the eighth (an uncandidated
    # holding, pinned by test_held_attack_symbol_without_a_base_target_is_carried...)
    assert {item.action for item in plan.items} == set(rec.Action) - {rec.Action.NO_ACTION}
    assert plan.item("159915").action is rec.Action.HOLD
    assert exposure.total_symbols == 7
    assert exposure.attack_symbols == 4
    assert exposure.defense_symbols == 3
    assert exposure.total_weight <= 1.0
    assert exposure.ok is True
    # the account-level facts are machine-readable, the note stays parseable
    assert plan.risk_state is rec.RiskState.NORMAL
    assert sp.parse_notes(plan.note) == {}
    assert "进攻暴露系数 0.90" in plan.note


def test_note_tokens_parse_only_codes_and_keep_symbol_order():
    note = "账户级风险 正常 / 账户动作 不动 | entry_blocked=600002,510300 | trailing text"
    assert sp.parse_notes(note) == {"entry_blocked": ("600002", "510300")}
    assert sp.parse_notes("进攻暴露系数 0.90") == {}
