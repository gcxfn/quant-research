import datetime as dt

import pytest

from quant.portfolio import recommendations as rec
from quant.portfolio.intent_adapter import (
    IntentAdapterError, plan_to_intent_frame, plan_to_intents,
)


def _item(action, target=0.2, qty=100):
    return rec.RecommendationItem(
        symbol="sh.600000", name="demo", sleeve=rec.Sleeve.ATTACK,
        action=action, current_quantity=100, recommended_quantity=qty,
        target_weight=target, valid_until=dt.datetime(2026, 9, 21, 15),
        trigger_reason="test", invalidation_reason="test", price_lower=10,
        price_upper=10.2, stop_price=9.5,
    )


def _plan(items):
    return rec.RecommendationPlan(
        recommendation_version="r1", decision_point=rec.DecisionPoint.PM_1500,
        generated_at=dt.datetime(2026, 9, 20, 15),
        market_as_of=dt.datetime(2026, 9, 20, 15),
        account_snapshot_version="a1", strategy_version="s1",
        valid_from=dt.datetime(2026, 9, 20, 15),
        valid_until=dt.datetime(2026, 9, 21, 15),
        risk_state=rec.RiskState.NORMAL, account_action=rec.Action.NO_ACTION,
        equity=500000, cash=300000, items=tuple(items),
    )


def test_maps_buy_profit_and_risk_to_engine_rows():
    plan = _plan([_item(rec.Action.NEW), _item(rec.Action.TAKE_PROFIT, 0.1),
                  _item(rec.Action.STOP_LOSS, 0.0)])
    rows = plan_to_intents(plan)
    assert [r["side"] for r in rows] == ["buy", "sell", "sell"]
    assert [r["intent"] for r in rows] == ["", "profit", "risk"]
    assert rows[-1]["target_weight"] == 0.0
    assert all(r["decision_session"] == "pm" for r in rows)


def test_passive_items_are_not_submitted():
    plan = _plan([_item(rec.Action.HOLD, qty=0)])
    assert plan_to_intents(plan) == ()


def test_rejects_non_positive_order_quantity():
    plan = _plan([_item(rec.Action.NEW, qty=0)])
    with pytest.raises(IntentAdapterError, match="positive"):
        plan_to_intents(plan)


def test_emits_band_engine_frame_schema():
    frame = plan_to_intent_frame(_plan([_item(rec.Action.NEW)]))
    assert frame.columns == [
        "symbol", "side", "intent", "decision_date", "decision_session",
        "source_signal", "priority", "expiry_date", "target_weight",
    ]
    assert frame.schema["decision_date"].is_nested() is False
    assert frame["target_weight"].to_list() == [0.2]
