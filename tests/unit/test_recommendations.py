"""Unit tests for the recommendation output layer (synthetic data only).

Each test pins one clause of ``docs/plans/daily-strategy-output-contract.md`` and
``docs/plans/p3-band-contract.md``: the machine-readable plan fields, separate
attack / defense accounting, the registered limits (25% per symbol, 100% gross,
4 attack / 3 defense / 7 total, 3 new entries), version coverage (a new version
covers unfilled intents, a filled intent is protected and its quantity comes from
the account snapshot), half-session expiry, and fail-closed identity / freshness
rejection.  Synthetic numbers are never profitability evidence.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json

import pytest

from quant.portfolio import recommendations as rec

STRATEGY = "strat-r16-20260918"
DAY0 = dt.date(2026, 9, 21)
DAY1 = dt.date(2026, 9, 22)
DAY2 = dt.date(2026, 9, 23)
MARKET_AS_OF = dt.datetime(2026, 9, 21, 15, 0)
GENERATED_AT = MARKET_AS_OF
EQUITY = 200_000.0
VALID_FROM = dt.datetime(2026, 9, 22, 9, 30)
VALID_UNTIL = dt.datetime(2026, 9, 22, 11, 30)
TRADE_DATE = DAY1


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


def identity(*, strategy=STRATEGY, market_as_of=MARKET_AS_OF, version="acct-1"):
    return rec.PlanIdentity(
        strategy_version=strategy,
        market_as_of=market_as_of,
        account_snapshot_version=version,
    )


def item(
    symbol,
    action,
    *,
    name=None,
    sleeve=rec.Sleeve.ATTACK,
    current_quantity=0,
    recommended_quantity=0,
    target_weight=0.0,
    price_lower=None,
    price_upper=None,
    stop_price=None,
    risk_r=None,
    previous_action=None,
    change_reason="",
    trigger_reason="signal fired",
    invalidation_reason="signal invalidated",
    valid_until=VALID_UNTIL,
):
    return rec.RecommendationItem(
        symbol=symbol,
        name=name or f"name-{symbol}",
        sleeve=sleeve,
        action=action,
        current_quantity=current_quantity,
        recommended_quantity=recommended_quantity,
        target_weight=target_weight,
        valid_until=valid_until,
        trigger_reason=trigger_reason,
        invalidation_reason=invalidation_reason,
        price_lower=price_lower,
        price_upper=price_upper,
        risk_r=risk_r,
        stop_price=stop_price,
        previous_action=previous_action,
        change_reason=change_reason,
    )


def buy(
    symbol,
    *,
    quantity,
    price,
    weight,
    stop=None,
    sleeve=rec.Sleeve.ATTACK,
    action=rec.Action.NEW,
    current_quantity=0,
    previous_action=None,
    change_reason="",
    name=None,
    trade_date=TRADE_DATE,
):
    """A buy-style intent (new or add) with a fee-inclusive risk R when asked."""

    risk = None
    if stop is not None:
        risk = rec.risk_amount(
            quantity, price, stop, sleeve=sleeve, trade_date=trade_date
        )
    return item(
        symbol,
        action,
        name=name,
        sleeve=sleeve,
        current_quantity=current_quantity,
        recommended_quantity=quantity,
        target_weight=weight,
        price_lower=round(price * 0.99, 3),
        price_upper=price,
        stop_price=stop,
        risk_r=risk,
        previous_action=previous_action,
        change_reason=change_reason,
    )


def sell(
    symbol,
    *,
    quantity,
    weight,
    price,
    action=rec.Action.REDUCE,
    sleeve=rec.Sleeve.ATTACK,
    current_quantity=0,
    stop=None,
    previous_action=rec.Action.HOLD,
    change_reason="reduced",
    trade_date=TRADE_DATE,
):
    risk = None
    if stop is not None:
        risk = rec.risk_amount(
            current_quantity, price, stop, sleeve=sleeve, trade_date=trade_date
        )
    return item(
        symbol,
        action,
        sleeve=sleeve,
        current_quantity=current_quantity,
        recommended_quantity=quantity,
        target_weight=weight,
        price_lower=round(price * 0.99, 3),
        price_upper=round(price * 1.01, 3),
        stop_price=stop,
        risk_r=risk,
        previous_action=previous_action,
        change_reason=change_reason,
    )


def hold(
    symbol,
    *,
    current_quantity,
    weight,
    price,
    stop=None,
    sleeve=rec.Sleeve.ATTACK,
    previous_action=None,
    change_reason="unchanged",
    trade_date=TRADE_DATE,
):
    risk = None
    if stop is not None:
        risk = rec.risk_amount(
            current_quantity, price, stop, sleeve=sleeve, trade_date=trade_date
        )
    return item(
        symbol,
        rec.Action.HOLD,
        sleeve=sleeve,
        current_quantity=current_quantity,
        target_weight=weight,
        price_lower=round(price * 0.99, 3),
        price_upper=round(price * 1.01, 3),
        stop_price=stop,
        risk_r=risk,
        previous_action=previous_action,
        change_reason=change_reason,
    )


def plan(
    acct,
    items=(),
    *,
    version="rec-20260921T1500-day0",
    risk_state=rec.RiskState.NORMAL,
    account_action=rec.Action.NO_ACTION,
    note="",
    policy=None,
    ident=None,
    decision_point=rec.DecisionPoint.DAY0_CLOSE,
    generated_at=GENERATED_AT,
    valid_from=VALID_FROM,
    valid_until=VALID_UNTIL,
):
    return rec.build_plan(
        decision_point=decision_point,
        generated_at=generated_at,
        identity=ident or identity(version=acct.snapshot_version),
        account=acct,
        recommendation_version=version,
        valid_from=valid_from,
        valid_until=valid_until,
        items=tuple(items),
        risk_state=risk_state,
        account_action=account_action,
        note=note,
        policy=policy,
    )


def attack_buys(count, *, weight=0.05, price=10.0, stop=9.0):
    return [
        buy(f"60000{index}", quantity=1000, price=price, weight=weight, stop=stop)
        for index in range(count)
    ]


def defense_buys(count, *, weight=0.05, price=5.0):
    return [
        buy(f"51030{index}", sleeve=rec.Sleeve.DEFENSE, quantity=1000, price=price, weight=weight)
        for index in range(count)
    ]


def reason_of(exc_info):
    assert isinstance(exc_info.value, rec.RecommendationError)
    return exc_info.value.reason


# --------------------------------------------------------------------------- #
# sessions: one plan = one half session
# --------------------------------------------------------------------------- #
def test_session_windows_are_half_day():
    day0_from, day0_until = rec.session_window(
        rec.DecisionPoint.DAY0_CLOSE, trading_day=DAY0, next_trading_day=DAY1
    )
    assert (day0_from, day0_until) == (VALID_FROM, VALID_UNTIL)
    assert rec.served_session(rec.DecisionPoint.DAY0_CLOSE) is rec.Session.AM

    am_from, am_until = rec.session_window(rec.DecisionPoint.AM_1130, trading_day=DAY1)
    assert (am_from, am_until) == (
        dt.datetime(2026, 9, 22, 13, 0),
        dt.datetime(2026, 9, 22, 15, 0),
    )
    pm_from, pm_until = rec.session_window(
        rec.DecisionPoint.PM_1500, trading_day=DAY1, next_trading_day=DAY2
    )
    assert (pm_from, pm_until) == (
        dt.datetime(2026, 9, 23, 9, 30),
        dt.datetime(2026, 9, 23, 11, 30),
    )

    with pytest.raises(rec.RecommendationError) as exc:
        rec.session_window(rec.DecisionPoint.DAY0_CLOSE, trading_day=DAY0)
    assert reason_of(exc) is rec.Reason.MISSING_NEXT_SESSION


# --------------------------------------------------------------------------- #
# legal advice and separate sleeve accounting
# --------------------------------------------------------------------------- #
def test_new_entry_plan_is_legal_and_layered():
    acct = account()
    attack = buy("600000", quantity=4000, price=10.0, weight=0.20, stop=9.0)
    defense = buy("510300", sleeve=rec.Sleeve.DEFENSE, quantity=6000, price=5.0, weight=0.15)
    built = plan(acct, [attack, defense])

    assert built.entry_paused is False
    assert built.account_snapshot_version == acct.snapshot_version
    assert built.market_as_of == MARKET_AS_OF
    assert built.strategy_version == STRATEGY
    assert built.recommendation_version == "rec-20260921T1500-day0"
    assert built.decision_point is rec.DecisionPoint.DAY0_CLOSE
    assert built.risk_state is rec.RiskState.NORMAL
    assert built.account_action is rec.Action.NO_ACTION
    assert built.valid_from == VALID_FROM and built.valid_until == VALID_UNTIL
    assert built.equity == EQUITY and built.cash == acct.cash

    exposure = rec.validate_plan(built, account=acct)
    assert exposure.attack_weight == pytest.approx(0.20)
    assert exposure.defense_weight == pytest.approx(0.15)
    assert exposure.total_weight == pytest.approx(0.35)
    assert exposure.attack_symbols == 1 and exposure.defense_symbols == 1
    assert exposure.new_entries == 2
    assert exposure.symbol_limit_breaches == ()
    assert exposure.ok is True
    # the intent carries a fee-inclusive R, not a bare signal price distance
    assert built.item("600000").risk_r > 4000 * (10.0 - 9.0)


def test_omitted_holding_is_refused_and_reported():
    """A silent omission cannot buy extra seats: the gate is hard, and the
    diagnostic names the uncovered position for plans that skip validation."""

    acct = account(
        positions=[position(f"60000{index}", quantity=2000) for index in range(4)]
        + [position("600099", quantity=2000)]
    )
    silent = [
        hold(f"60000{index}", current_quantity=2000, weight=0.10, price=10.0, stop=9.0)
        for index in range(4)
    ]
    raw = plan_without_limits(acct, silent)
    exposure = rec.exposure_of(raw, account=acct)
    assert exposure.uncovered_positions == ("600099",)
    # the omitted holding is still counted, so layer statistics cannot understate
    assert exposure.attack_symbols == 5
    assert exposure.attack_weight == pytest.approx(0.50)
    assert exposure.ok is False
    assert exposure.uncovered_positions == ("600099",)
    assert all(isinstance(symbol, str) for symbol in exposure.uncovered_positions)
    assert exposure.to_mapping()["uncovered_positions"] == ["600099"]

    # the container itself refuses non-symbol payloads instead of serialising them
    with pytest.raises(rec.RecommendationError) as exc:
        dataclasses.replace(exposure, uncovered_positions=(position("600099", quantity=2000),))
    assert reason_of(exc) is rec.Reason.INVALID_FIELD

    with pytest.raises(rec.RecommendationError) as exc:
        rec.validate_plan(raw, account=acct)
    assert reason_of(exc) is rec.Reason.MISSING_POSITION_ITEM

    ledger = rec.RecommendationLedger()
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.publish(raw, account=acct)
    assert reason_of(exc) is rec.Reason.MISSING_POSITION_ITEM
    assert ledger.active_plan is None


def test_attack_and_defense_layers_are_accounted_separately():
    acct = account(
        positions=[
            position("600000", quantity=2000),
            position("510300", sleeve=rec.Sleeve.DEFENSE, quantity=4000, last=5.0, cost=5.0),
        ]
    )
    items = [
        hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
        buy(
            "510300",
            sleeve=rec.Sleeve.DEFENSE,
            action=rec.Action.ADD,
            current_quantity=4000,
            quantity=2000,
            price=5.0,
            weight=0.15,
            previous_action=rec.Action.HOLD,
            change_reason="trend intact, add to the target weight",
        ),
    ]
    built = plan(acct, items)
    exposure = rec.validate_plan(built, account=acct)

    assert exposure.attack_weight == pytest.approx(0.10)
    assert exposure.defense_weight == pytest.approx(0.15)
    assert exposure.total_weight == pytest.approx(0.25)
    assert exposure.attack_symbols == 1 and exposure.defense_symbols == 1
    assert exposure.new_entries == 0
    assert built.entry_paused is False  # an add is still a buy intent

    frozen = plan(
        acct,
        [
            hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
            hold(
                "510300",
                sleeve=rec.Sleeve.DEFENSE,
                current_quantity=4000,
                weight=0.10,
                price=5.0,
            ),
        ],
    )
    assert frozen.entry_paused is True
    assert rec.validate_plan(frozen, account=acct).new_entries == 0


# --------------------------------------------------------------------------- #
# registered limits
# --------------------------------------------------------------------------- #
def test_slot_limits_attack_defense_total():
    acct = account()
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, attack_buys(5))
    assert reason_of(exc) is rec.Reason.ATTACK_SLOT_LIMIT

    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, defense_buys(4))
    assert reason_of(exc) is rec.Reason.DEFENSE_SLOT_LIMIT

    # 4 attack + 3 defense is the full book and still passes
    full = account(
        positions=[
            position("600000", quantity=2000),
            position("600001", quantity=2000),
            position("600002", quantity=2000),
            position("600003", quantity=2000),
            position("510300", sleeve=rec.Sleeve.DEFENSE, quantity=4000, last=5.0, cost=5.0),
            position("510301", sleeve=rec.Sleeve.DEFENSE, quantity=4000, last=5.0, cost=5.0),
            position("510302", sleeve=rec.Sleeve.DEFENSE, quantity=4000, last=5.0, cost=5.0),
        ]
    )
    held = [
        hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
        hold("600001", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
        hold("600002", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
        hold("600003", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
        hold("510300", sleeve=rec.Sleeve.DEFENSE, current_quantity=4000, weight=0.10, price=5.0),
        hold("510301", sleeve=rec.Sleeve.DEFENSE, current_quantity=4000, weight=0.10, price=5.0),
        hold("510302", sleeve=rec.Sleeve.DEFENSE, current_quantity=4000, weight=0.10, price=5.0),
    ]
    exposure = rec.validate_plan(plan(full, held), account=full)
    assert exposure.total_symbols == 7
    assert exposure.attack_symbols == 4 and exposure.defense_symbols == 3
    assert exposure.ok is True

    # the total slot cap is registry-driven, not implied by the sleeve caps
    tight = rec.PlanPolicy(total_slots=5)
    with pytest.raises(rec.RecommendationError) as exc:
        plan(full, held, policy=tight)
    assert reason_of(exc) is rec.Reason.TOTAL_SLOT_LIMIT


def test_symbol_weight_limit():
    acct = account()
    heavy = buy("600000", quantity=6000, price=10.0, weight=0.30, stop=9.0)
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [heavy])
    assert reason_of(exc) is rec.Reason.SYMBOL_WEIGHT_LIMIT
    assert exc.value.symbol is None  # limit failures are plan-level

    # the same plan reports the breaching symbol in its layer statistics
    raw = rec.RecommendationPlan(
        recommendation_version="rec-raw",
        decision_point=rec.DecisionPoint.DAY0_CLOSE,
        generated_at=GENERATED_AT,
        market_as_of=MARKET_AS_OF,
        account_snapshot_version=acct.snapshot_version,
        strategy_version=STRATEGY,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        risk_state=rec.RiskState.NORMAL,
        account_action=rec.Action.NO_ACTION,
        equity=EQUITY,
        cash=acct.cash,
        items=(heavy,),
    )
    exposure = rec.exposure_of(raw, account=acct)
    assert exposure.symbol_limit_breaches == ("600000",)
    assert exposure.ok is False
    with pytest.raises(rec.RecommendationError) as exc:
        rec.validate_plan(raw, account=acct)
    assert reason_of(exc) is rec.Reason.SYMBOL_WEIGHT_LIMIT

    # exactly 25% is inside the limit
    assert rec.validate_plan(
        plan(acct, [buy("600000", quantity=4000, price=12.5, weight=0.25, stop=11.0)]),
        account=acct,
    ).ok


def test_gross_exposure_limit_and_fee_reserve():
    acct = account()
    heavy_book = attack_buys(3, weight=0.23, price=10.0) + defense_buys(1, weight=0.23, price=5.0)
    # the sleeve caps and the per-symbol cap pass: only the gross cap is breached
    exposure = rec.exposure_of(plan_without_limits(acct, heavy_book), account=acct)
    assert exposure.total_weight == pytest.approx(0.92)
    assert exposure.symbol_limit_breaches == ()
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, heavy_book, policy=rec.PlanPolicy(total_weight_limit=0.90))
    assert reason_of(exc) is rec.Reason.GROSS_EXPOSURE_LIMIT

    # cash must cover the orders *plus* fees: the fee reserve is not free
    broke = account(cash=1000.0)
    with pytest.raises(rec.RecommendationError) as exc:
        plan(broke, [buy("600000", quantity=100, price=10.0, weight=0.005, stop=9.0)])
    assert reason_of(exc) is rec.Reason.INSUFFICIENT_CASH


def plan_without_limits(acct, items):
    """Build a plan object directly so only ``exposure_of`` is exercised."""

    return rec.RecommendationPlan(
        recommendation_version="rec-raw",
        decision_point=rec.DecisionPoint.DAY0_CLOSE,
        generated_at=GENERATED_AT,
        market_as_of=MARKET_AS_OF,
        account_snapshot_version=acct.snapshot_version,
        strategy_version=STRATEGY,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        risk_state=rec.RiskState.NORMAL,
        account_action=rec.Action.NO_ACTION,
        equity=acct.equity,
        cash=acct.cash,
        items=tuple(items),
    )


def test_day0_new_entry_limit():
    acct = account()
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, attack_buys(4))
    assert reason_of(exc) is rec.Reason.DAY0_NEW_ENTRY_LIMIT

    three = plan(acct, attack_buys(3))
    assert rec.validate_plan(three, account=acct).new_entries == 3
    assert three.entry_paused is False

    # the cap is registry-driven: a pre-registered policy can lift it
    lifted_policy = rec.PlanPolicy(max_new_entries=4)
    lifted = plan(acct, attack_buys(4), policy=lifted_policy)
    assert rec.validate_plan(lifted, account=acct, policy=lifted_policy).new_entries == 4


# --------------------------------------------------------------------------- #
# intent shape
# --------------------------------------------------------------------------- #
def test_buy_intent_shape_failures():
    acct = account()
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [buy("600000", quantity=150, price=10.0, weight=0.01, stop=9.0)])
    assert reason_of(exc) is rec.Reason.INVALID_LOT

    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05)])
    assert reason_of(exc) is rec.Reason.MISSING_RISK_R

    # a stop above the buy band would fill at a loss by construction
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=10.5)])
    assert reason_of(exc) is rec.Reason.INVALID_STOP

    # an order without an executable band is not an intent
    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            acct,
            [
                item(
                    "600000",
                    rec.Action.NEW,
                    recommended_quantity=1000,
                    target_weight=0.05,
                    stop_price=9.0,
                    risk_r=1001.0,
                )
            ],
        )
    assert reason_of(exc) is rec.Reason.INVALID_FIELD

    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            acct,
            [
                item(
                    "600000",
                    rec.Action.NEW,
                    recommended_quantity=1000,
                    target_weight=0.05,
                    invalidation_reason="",
                )
            ],
        )
    assert reason_of(exc) is rec.Reason.MISSING_INTENT_REASON


def test_sell_size_respects_t1_sellable():
    acct = account(positions=[position("600000", quantity=1000, sellable=400)])
    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            acct,
            [sell("600000", current_quantity=1000, quantity=600, weight=0.02, price=10.0, stop=9.0)],
        )
    assert reason_of(exc) is rec.Reason.SELLABLE_QUANTITY_EXCEEDED

    built = plan(
        acct,
        [sell("600000", current_quantity=1000, quantity=400, weight=0.03, price=10.0, stop=9.0)],
    )
    exposure = rec.validate_plan(built, account=acct)
    assert exposure.attack_weight == pytest.approx(0.03)
    # the account is untouched: 400 sellable is a constraint reading, not a fill
    assert acct.position("600000").sellable_quantity == 400
    assert acct.position("600000").quantity == 1000


def test_hold_must_match_account_weight_and_quantity():
    acct = account(positions=[position("600000", quantity=1000)])
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [hold("600000", current_quantity=1000, weight=0.10, price=10.0, stop=9.0)])
    assert reason_of(exc) is rec.Reason.POSITION_WEIGHT_MISMATCH

    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [hold("600000", current_quantity=500, weight=0.05, price=10.0, stop=9.0)])
    assert reason_of(exc) is rec.Reason.POSITION_MISMATCH

    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            acct,
            [
                hold("600000", current_quantity=1000, weight=0.05, price=10.0, stop=9.0),
                item(
                    "600999",
                    rec.Action.NO_ACTION,
                    current_quantity=500,
                    change_reason="phantom holding",
                ),
            ],
        )
    assert reason_of(exc) is rec.Reason.UNKNOWN_POSITION_SYMBOL


def test_missing_position_item_is_never_fabricated():
    acct = account(positions=[position("600000", quantity=1000)])
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [])
    assert reason_of(exc) is rec.Reason.MISSING_POSITION_ITEM
    assert exc.value.symbol == "600000"

    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [hold("600000", current_quantity=1000, weight=0.05, price=10.0, stop=9.0), hold("600000", current_quantity=1000, weight=0.05, price=10.0, stop=9.0)])
    assert reason_of(exc) is rec.Reason.DUPLICATE_SYMBOL


# --------------------------------------------------------------------------- #
# fail-closed: stale or mismatched inputs never produce advice
# --------------------------------------------------------------------------- #
def test_stale_market_or_account_rejects_new_advice():
    stale_market = account(
        as_of=GENERATED_AT,
        market_as_of=GENERATED_AT - dt.timedelta(hours=24),
        version="acct-1",
    )
    stale_identity = identity(market_as_of=GENERATED_AT - dt.timedelta(hours=24))
    with pytest.raises(rec.RecommendationError) as exc:
        plan(stale_market, [], ident=stale_identity)
    assert reason_of(exc) is rec.Reason.MARKET_DATA_STALE

    stale_account = account(as_of=GENERATED_AT - dt.timedelta(hours=24), market_as_of=MARKET_AS_OF)
    with pytest.raises(rec.RecommendationError) as exc:
        plan(stale_account, [])
    assert reason_of(exc) is rec.Reason.ACCOUNT_SNAPSHOT_STALE

    # a lenient registered window accepts the same snapshot, so the gate is
    # policy-driven rather than hard-coded
    lenient = rec.PlanPolicy(max_account_staleness=dt.timedelta(hours=48))
    assert rec.validate_plan(
        plan(stale_account, [], policy=lenient), account=stale_account, policy=lenient
    ).ok


def test_identity_mismatch_rejects_new_advice():
    acct = account()
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [], ident=identity(strategy="strat-other"))
    assert reason_of(exc) is rec.Reason.STRATEGY_VERSION_MISMATCH
    assert exc.value.to_mapping()["reason"] == "strategy_version_mismatch"

    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [], ident=identity(market_as_of=GENERATED_AT - dt.timedelta(hours=1)))
    assert reason_of(exc) is rec.Reason.MARKET_AS_OF_MISMATCH

    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [], ident=identity(version="acct-0"))
    assert reason_of(exc) is rec.Reason.ACCOUNT_SNAPSHOT_MISMATCH

    wrong_money = rec.RecommendationPlan(
        recommendation_version="rec-raw",
        decision_point=rec.DecisionPoint.DAY0_CLOSE,
        generated_at=GENERATED_AT,
        market_as_of=MARKET_AS_OF,
        account_snapshot_version=acct.snapshot_version,
        strategy_version=STRATEGY,
        valid_from=VALID_FROM,
        valid_until=VALID_UNTIL,
        risk_state=rec.RiskState.NORMAL,
        account_action=rec.Action.NO_ACTION,
        equity=EQUITY + 1.0,
        cash=acct.cash,
    )
    with pytest.raises(rec.RecommendationError) as exc:
        rec.validate_plan(wrong_money, account=acct)
    assert reason_of(exc) is rec.Reason.EQUITY_MISMATCH

    wrong_cash = dataclasses.replace(wrong_money, equity=EQUITY, cash=acct.cash - 1.0)
    with pytest.raises(rec.RecommendationError) as exc:
        rec.validate_plan(wrong_cash, account=acct)
    assert reason_of(exc) is rec.Reason.CASH_MISMATCH

    # inputs stamped in the future are refused instead of being trusted
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [], generated_at=MARKET_AS_OF - dt.timedelta(hours=1))
    assert reason_of(exc) is rec.Reason.FUTURE_INPUT

    # a version that is born after its own window is dead on arrival
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [], generated_at=VALID_UNTIL)
    assert reason_of(exc) is rec.Reason.PLAN_EXPIRED


def test_empty_plan_is_legal_and_self_describing():
    acct = account()
    empty = plan(acct, [], note="no candidate met the entry conditions")
    assert empty.items == ()
    assert empty.entry_paused is True
    exposure = rec.validate_plan(empty, account=acct)
    assert (exposure.attack_weight, exposure.defense_weight, exposure.total_weight) == (0.0, 0.0, 0.0)
    assert exposure.new_entries == 0
    assert exposure.ok is True
    assert any("不新增" in line for line in empty.render_lines())
    assert empty.note in empty.render_lines()

    # a legal empty version is still a version: it goes through the ledger, has
    # nothing to carry and nothing to expire
    ledger = rec.RecommendationLedger()
    report = ledger.publish(empty, account=acct)
    assert report.outcomes == ()
    assert report.cancelled_symbols == ()
    assert ledger.pending_intents() == ()
    assert ledger.expire(VALID_UNTIL) == ()

    # no opportunity is not a failure, but a held position still needs an
    # explicit item instead of a fabricated hold
    held = account(positions=[position("600000", quantity=1000)])
    with pytest.raises(rec.RecommendationError) as exc:
        plan(held, [], note="no candidate")
    assert reason_of(exc) is rec.Reason.MISSING_POSITION_ITEM


def test_halfday_expiry_retires_unfilled_intents():
    acct = account()
    live = plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0)])
    assert live.is_live(VALID_FROM) is True
    assert live.is_live(VALID_UNTIL) is False
    assert live.is_expired(VALID_UNTIL) is True

    ledger = rec.RecommendationLedger()
    ledger.publish(live, account=acct)
    assert len(ledger.pending_intents()) == 1
    assert ledger.pending_intents(as_of=VALID_UNTIL) == ()

    outcomes = ledger.expire(VALID_UNTIL)
    assert [outcome.kind for outcome in outcomes] == [rec.IntentOutcomeKind.EXPIRED]
    assert outcomes[0].symbol == "600000"
    assert ledger.active_plan is None
    assert ledger.pending_intents() == ()
    assert ledger.account_truth is acct

    # an item may not outlive its plan
    late = dataclasses.replace(
        buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0),
        valid_until=VALID_UNTIL + dt.timedelta(minutes=30),
    )
    with pytest.raises(rec.RecommendationError) as exc:
        plan(acct, [late])
    assert reason_of(exc) is rec.Reason.INVALID_FIELD


# --------------------------------------------------------------------------- #
# version coverage: unfilled superseded, filled protected, account is truth
# --------------------------------------------------------------------------- #
PM_AS_OF = dt.datetime(2026, 9, 22, 11, 30)
PM_FROM = dt.datetime(2026, 9, 22, 13, 0)
PM_UNTIL = dt.datetime(2026, 9, 22, 15, 0)
FILL_AT = dt.datetime(2026, 9, 22, 9, 45)


def holding_account(
    *, quantity, price=10.0, cost=10.0, sellable=0, fee=5.0, version="acct-2"
):
    held = position("600000", quantity=quantity, sellable=sellable, cost=cost, last=price)
    return account(
        positions=[held],
        cash=EQUITY - held.market_value - fee,
        version=version,
        as_of=PM_AS_OF,
        market_as_of=PM_AS_OF,
    )


def pm_plan(acct, items=(), *, version="rec-20260922T1130"):
    items = tuple(dataclasses.replace(item, valid_until=PM_UNTIL) for item in items)
    return plan(
        acct,
        items,
        version=version,
        ident=identity(market_as_of=acct.market_as_of, version=acct.snapshot_version),
        decision_point=rec.DecisionPoint.AM_1130,
        generated_at=acct.as_of,
        valid_from=PM_FROM,
        valid_until=PM_UNTIL,
    )


def test_new_version_covers_unfilled_intents():
    acct = account()
    first = plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0)])
    ledger = rec.RecommendationLedger()
    ledger.publish(first, account=acct)
    assert [intent.symbol for intent in ledger.pending_intents()] == ["600000"]

    second = plan(
        acct,
        [buy("600001", quantity=1000, price=10.0, weight=0.05, stop=9.0)],
        version="rec-20260921T1530-day0",
    )
    report = ledger.publish(second, account=acct)

    assert report.superseded_version == first.recommendation_version
    assert report.superseded_valid_until == VALID_UNTIL
    assert report.new_version == second.recommendation_version
    assert report.cancelled_symbols == ("600000",)
    assert report.expired_symbols == ()
    assert report.protected_symbols == ()
    outcome = report.outcome("600000")
    assert outcome.kind is rec.IntentOutcomeKind.CANCELLED
    assert outcome.protected is False
    assert outcome.recommended_quantity == 1000 and outcome.filled_quantity == 0
    assert outcome.account_quantity == 0
    assert ledger.active_plan is second
    assert [intent.symbol for intent in ledger.pending_intents()] == ["600001"]


def test_filled_intent_is_protected_and_position_is_truth():
    acct = account()
    first = plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0)])
    ledger = rec.RecommendationLedger()
    ledger.publish(first, account=acct)

    after = holding_account(quantity=1000)
    recorded = ledger.record_fills(
        [rec.FillRecord("600000", rec.Side.BUY, 1000, 10.0, 5.0, FILL_AT)], account=after
    )
    assert len(recorded) == 1
    # the fill moved a counter, not the account
    assert ledger.pending_intents() == ()
    assert ledger.account_truth is acct
    assert after.position("600000").sellable_quantity == 0

    second = pm_plan(
        after,
        [
            hold(
                "600000",
                current_quantity=1000,
                weight=0.05,
                price=10.0,
                stop=9.0,
                previous_action=rec.Action.NEW,
                change_reason="the new entry filled last session",
            )
        ],
    )
    report = ledger.publish(second, account=after)

    assert report.protected_symbols == ("600000",)
    assert report.cancelled_symbols == ()
    outcome = report.outcome("600000")
    assert outcome.kind is rec.IntentOutcomeKind.FILLED
    assert outcome.filled_quantity == 1000
    assert outcome.account_quantity == 1000  # truth comes from the snapshot
    assert ledger.account_truth is after

    # the executed position cannot be denied by a suggestion, nor dropped
    with pytest.raises(rec.RecommendationError) as exc:
        pm_plan(
            after,
            [
                item(
                    "600000",
                    rec.Action.NO_ACTION,
                    current_quantity=0,
                    change_reason="claims the position is gone",
                )
            ],
        )
    assert reason_of(exc) is rec.Reason.POSITION_MISMATCH
    with pytest.raises(rec.RecommendationError) as exc:
        pm_plan(after, [])
    assert reason_of(exc) is rec.Reason.MISSING_POSITION_ITEM


def test_filled_intent_must_be_acknowledged():
    acct = account()
    first = plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0)])
    ledger = rec.RecommendationLedger()
    ledger.publish(first, account=acct)

    after = holding_account(quantity=1000)
    naive = pm_plan(
        after,
        [hold("600000", current_quantity=1000, weight=0.05, price=10.0, stop=9.0)],
    )
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.publish(
            naive, account=after, fills=[rec.FillRecord("600000", rec.Side.BUY, 1000, 10.0, 5.0, FILL_AT)]
        )
    assert reason_of(exc) is rec.Reason.FILLED_INTENT_NOT_ACKNOWLEDGED
    assert exc.value.symbol == "600000"
    # the rejected version never becomes live
    assert ledger.active_plan is first


def test_partial_fill_leaves_only_the_new_version_live():
    acct = account()
    first = plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0)])
    ledger = rec.RecommendationLedger()
    ledger.publish(first, account=acct)

    after = holding_account(quantity=600, sellable=600)
    second = pm_plan(
        after,
        [
            buy(
                "600000",
                action=rec.Action.ADD,
                current_quantity=600,
                quantity=400,
                price=10.0,
                weight=0.05,
                stop=9.0,
                previous_action=rec.Action.NEW,
                change_reason="complete the unfilled part",
            )
        ],
    )
    report = ledger.publish(
        second,
        account=after,
        fills=[rec.FillRecord("600000", rec.Side.BUY, 600, 10.0, 5.0, FILL_AT)],
    )
    outcome = report.outcome("600000")
    assert outcome.kind is rec.IntentOutcomeKind.FILLED_PARTIAL
    assert outcome.filled_quantity == 600
    assert outcome.protected is True
    assert "remainder" in outcome.note
    # the old 1000-share intent is gone; only the new 400-share intent is live
    assert [intent.recommended_quantity for intent in ledger.pending_intents()] == [400]


def test_fill_hygiene_failures():
    acct = account()
    first = plan(acct, [buy("600000", quantity=1000, price=10.0, weight=0.05, stop=9.0)])
    ledger = rec.RecommendationLedger()

    # a fill recorded while no version is live to match it against
    orphan = rec.FillRecord("600000", rec.Side.BUY, 1000, 10.0, 5.0, GENERATED_AT - dt.timedelta(hours=1))
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.publish(first, account=acct, fills=[orphan])
    assert reason_of(exc) is rec.Reason.FILL_WITHOUT_INTENT

    ledger.publish(first, account=acct)
    snapshot = rec.AccountSnapshot(
        snapshot_version="acct-live",
        as_of=PM_AS_OF,
        strategy_version=STRATEGY,
        market_as_of=MARKET_AS_OF,
        equity=EQUITY,
        cash=EQUITY,
    )

    # a sell fill against a buy-only version
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.record_fills(
            [rec.FillRecord("600000", rec.Side.SELL, 1000, 10.0, 5.0, FILL_AT)], account=snapshot
        )
    assert reason_of(exc) is rec.Reason.FILL_WITHOUT_INTENT

    # a fill for a symbol the version never mentioned
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.record_fills(
            [rec.FillRecord("600001", rec.Side.BUY, 1000, 10.0, 5.0, FILL_AT)], account=snapshot
        )
    assert reason_of(exc) is rec.Reason.FILL_WITHOUT_INTENT

    # traded outside the live half session (the snapshot is newer than the fill)
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.record_fills(
            [rec.FillRecord("600000", rec.Side.BUY, 1000, 10.0, 5.0, PM_FROM)],
            account=dataclasses.replace(snapshot, as_of=PM_FROM),
        )
    assert reason_of(exc) is rec.Reason.FILL_WITHOUT_INTENT

    # an odd-lot buy fill
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.record_fills(
            [rec.FillRecord("600000", rec.Side.BUY, 150, 10.0, 5.0, FILL_AT)], account=snapshot
        )
    assert reason_of(exc) is rec.Reason.INVALID_LOT

    # a fill larger than the advice
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.record_fills(
            [rec.FillRecord("600000", rec.Side.BUY, 1200, 10.0, 5.0, FILL_AT)], account=snapshot
        )
    assert reason_of(exc) is rec.Reason.FILL_EXCEEDS_INTENT

    # a fill traded after the snapshot the truth comes from
    stale = rec.AccountSnapshot(
        snapshot_version="acct-0",
        as_of=FILL_AT - dt.timedelta(minutes=5),
        strategy_version=STRATEGY,
        market_as_of=MARKET_AS_OF,
        equity=EQUITY,
        cash=EQUITY,
    )
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.record_fills(
            [rec.FillRecord("600000", rec.Side.BUY, 1000, 10.0, 5.0, FILL_AT)], account=stale
        )
    assert reason_of(exc) is rec.Reason.FILL_AFTER_ACCOUNT_SNAPSHOT
    # ... and nothing was recorded by the rejected attempts
    assert ledger.pending_intents(as_of=FILL_AT)[0].symbol == "600000"

    # the same version cannot be published twice
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.publish(first, account=acct)
    assert reason_of(exc) is rec.Reason.DUPLICATE_VERSION


def test_unfilled_intents_never_touch_the_account():
    held = position("600000", quantity=2000, sellable=1000, cost=9.5, last=10.0)
    acct = account(positions=[held], cash=100_000.0)
    before = account(positions=[position("600000", quantity=2000, sellable=1000, cost=9.5, last=10.0)], cash=100_000.0)

    first = plan(
        acct,
        [
            hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
            buy("600001", quantity=1000, price=10.0, weight=0.05, stop=9.0),
        ],
    )
    ledger = rec.RecommendationLedger()
    ledger.publish(first, account=acct)

    assert ledger.account_truth is acct
    assert ledger.account_truth == before
    assert acct.cash == 100_000.0
    assert acct.position("600000").quantity == 2000
    assert acct.position("600000").sellable_quantity == 1000
    assert acct.position("600000").average_cost == 9.5
    # two intents are live, one of them is an order: neither moved the account
    assert [intent.symbol for intent in ledger.pending_intents()] == ["600001"]

    with pytest.raises(dataclasses.FrozenInstanceError):
        acct.cash = 0.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        acct.positions[0].sellable_quantity = 0  # type: ignore[misc]

    second = plan(
        acct,
        [hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0)],
        version="rec-20260921T1530-day0",
    )
    report = ledger.publish(second, account=acct)
    assert report.cancelled_symbols == ("600001",)
    assert acct == before
    assert ledger.account_truth == before
    assert ledger.pending_intents() == ()


def test_risk_state_and_account_delever():
    acct = account(
        positions=[
            position("600000", quantity=2000),
            position("510300", sleeve=rec.Sleeve.DEFENSE, quantity=2000, last=5.0, cost=5.0),
        ]
    )
    reduced = [
        sell(
            "600000",
            action=rec.Action.ACCOUNT_DELEVER,
            current_quantity=2000,
            quantity=500,
            weight=0.075,
            price=10.0,
            stop=9.0,
        ),
        hold("510300", sleeve=rec.Sleeve.DEFENSE, current_quantity=2000, weight=0.05, price=5.0),
    ]
    built = plan(
        acct,
        reduced,
        risk_state=rec.RiskState.CAUTION,
        account_action=rec.Action.ACCOUNT_DELEVER,
    )
    assert built.account_action is rec.Action.ACCOUNT_DELEVER
    assert built.entry_paused is True
    assert rec.validate_plan(built, account=acct).attack_weight == pytest.approx(0.075)

    # risk-off / de-lever forbids opening new attack exposure
    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            account(),
            [buy("600001", quantity=1000, price=10.0, weight=0.05, stop=9.0)],
            risk_state=rec.RiskState.RISK_OFF,
        )
    assert reason_of(exc) is rec.Reason.ENTRY_BLOCKED_BY_RISK_STATE

    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            account(),
            [buy("600001", quantity=1000, price=10.0, weight=0.05, stop=9.0)],
            account_action=rec.Action.ACCOUNT_DELEVER,
        )
    assert reason_of(exc) is rec.Reason.ENTRY_BLOCKED_BY_RISK_STATE

    # de-lever acts on the attack sleeve only
    with pytest.raises(rec.RecommendationError) as exc:
        plan(
            acct,
            [
                hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
                sell(
                    "510300",
                    action=rec.Action.ACCOUNT_DELEVER,
                    sleeve=rec.Sleeve.DEFENSE,
                    current_quantity=2000,
                    quantity=500,
                    weight=0.0375,
                    price=5.0,
                ),
            ],
            risk_state=rec.RiskState.RISK_OFF,
            account_action=rec.Action.ACCOUNT_DELEVER,
        )
    assert reason_of(exc) is rec.Reason.ACCOUNT_DELEVER_SLEEVE


# --------------------------------------------------------------------------- #
# machine-readable output vs display text, fees, risk
# --------------------------------------------------------------------------- #
def test_machine_mapping_round_trip_and_display_text():
    acct = account(positions=[position("600000", quantity=2000)])
    built = plan(
        acct,
        [
            hold("600000", current_quantity=2000, weight=0.10, price=10.0, stop=9.0),
            buy("600001", quantity=1000, price=10.0, weight=0.05, stop=9.0),
        ],
        note="one new candidate",
    )
    payload = built.to_mapping()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["entry_paused"] is False
    assert payload["items"][1]["action"] == "new"
    assert payload["items"][1]["sleeve"] == "attack"
    assert payload["items"][1]["previous_action"] is None
    assert payload["items"][0]["risk_r"] > 0.0
    assert rec.RecommendationPlan.from_mapping(payload) == built
    # a tampered machine payload is refused instead of being coerced
    with pytest.raises(ValueError):
        rec.RecommendationPlan.from_mapping({**payload, "decision_point": "sometime"})

    lines = built.render_lines()
    assert isinstance(lines, tuple) and all(isinstance(line, str) for line in lines)
    assert "建议版本" in lines[0] and built.recommendation_version in lines[0]
    assert any("新建" in line for line in lines)
    assert any("持有" in line for line in lines)
    assert built.note in lines
    assert "建议版本" not in payload


def test_registered_fee_and_cap_defaults_match_the_band_engine():
    """One registered convention: the engine's defaults and these must agree.

    The recommendation layer never fills orders, but it reserves fees and sizes
    limit caps from the same schedule; a silent divergence would make the plan's
    cash reserve and 25% / 100% caps wrong at the wiring point.
    """

    from quant.backtest import band_engine

    fees = rec.FeeSchedule()
    engine = band_engine.FeeModel()
    assert fees.commission_rate == engine.commission_rate
    assert fees.commission_min == engine.commission_min
    assert fees.stamp_duty_pre_cut == engine.stamp_sell_before
    assert fees.stamp_duty_post_cut == engine.stamp_sell_from
    assert fees.stamp_duty_cut_date == engine.stamp_boundary
    assert fees.lot_size == band_engine.LOT
    assert rec.DEFAULT_POLICY.symbol_weight_limit == band_engine.CAP_SINGLE_NAME
    assert rec.DEFAULT_POLICY.total_weight_limit == band_engine.CAP_TOTAL


def test_fee_model_and_risk_amount():
    schedule = rec.FeeSchedule()
    assert schedule.commission(10_000.0) == 5.0  # the 5 yuan floor binds
    assert schedule.commission(100_000.0) == pytest.approx(10.0)

    equity_notional = 9.0
    assert rec.estimate_fees(
        rec.Side.SELL,
        quantity=1000,
        price=9.0,
        sleeve=rec.Sleeve.ATTACK,
        trade_date=dt.date(2023, 8, 25),
    ) == pytest.approx(5.0 + 9.0)
    assert rec.estimate_fees(
        rec.Side.SELL,
        quantity=1000,
        price=9.0,
        sleeve=rec.Sleeve.ATTACK,
        trade_date=dt.date(2023, 8, 28),
    ) == pytest.approx(5.0 + 4.5)
    assert rec.estimate_fees(
        rec.Side.SELL,
        quantity=1000,
        price=9.0,
        sleeve=rec.Sleeve.DEFENSE,
        trade_date=dt.date(2024, 1, 2),
    ) == pytest.approx(5.0)
    assert rec.estimate_fees(
        rec.Side.BUY,
        quantity=1000,
        price=equity_notional,
        sleeve=rec.Sleeve.ATTACK,
        trade_date=dt.date(2024, 1, 2),
    ) == pytest.approx(5.0)

    risk = rec.risk_amount(
        1000,
        10.0,
        9.0,
        sleeve=rec.Sleeve.ATTACK,
        trade_date=dt.date(2026, 9, 22),
    )
    assert risk == pytest.approx(1000.0 + 5.0 + 9.5)
    with pytest.raises(rec.RecommendationError) as exc:
        rec.risk_amount(
            1000, 9.0, 10.0, sleeve=rec.Sleeve.ATTACK, trade_date=dt.date(2026, 9, 22)
        )
    assert reason_of(exc) is rec.Reason.INVALID_STOP


def test_expired_version_is_rejected_by_the_ledger():
    expired_account = rec.AccountSnapshot(
        snapshot_version="acct-3",
        as_of=PM_UNTIL,
        strategy_version=STRATEGY,
        market_as_of=PM_AS_OF,
        equity=EQUITY,
        cash=EQUITY,
    )
    live = pm_plan(account(), [])
    assert live.is_expired(PM_UNTIL) is True and live.is_expired(PM_FROM) is False
    expired = dataclasses.replace(live, account_snapshot_version="acct-3")

    ledger = rec.RecommendationLedger()
    with pytest.raises(rec.RecommendationError) as exc:
        ledger.publish(expired, account=expired_account)
    assert reason_of(exc) is rec.Reason.PLAN_EXPIRED
    assert ledger.active_plan is None
