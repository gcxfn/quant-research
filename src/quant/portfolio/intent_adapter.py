"""Convert one validated recommendation plan into band-engine intents.

This is an explicit boundary between the half-session output contract and the
historical backtest engine.  It deliberately drops passive items and carries
no price or stop fields: band_engine owns fills and order lifecycle.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from quant.portfolio import recommendations as rec

__all__ = ["IntentAdapterError", "plan_to_intents", "plan_to_intent_frame"]


class IntentAdapterError(ValueError):
    """A recommendation cannot be represented by the engine intent contract."""


def plan_to_intents(plan: rec.RecommendationPlan) -> tuple[dict[str, Any], ...]:
    """Return deterministic engine intent rows for order items in ``plan``.

    A plan is already validated before reaching this boundary.  The adapter
    still rejects unsupported or ambiguous order classes rather than silently
    inventing a fill.  ``target_weight`` is the post-trade weight emitted by
    the plan, and a full exit is represented by zero.
    """
    if not isinstance(plan, rec.RecommendationPlan):
        raise IntentAdapterError("plan must be a RecommendationPlan")
    decision_date = plan.valid_from.date()
    session = "am" if plan.decision_point is rec.DecisionPoint.AM_1130 else "pm"
    rows: list[dict[str, Any]] = []
    for item in plan.order_items:
        if item.recommended_quantity <= 0:
            raise IntentAdapterError(
                f"{item.symbol}: order item has no positive recommended_quantity"
            )
        side = item.side
        if side is rec.Side.BUY:
            intent = ""
        elif side is rec.Side.SELL:
            intent = "profit" if item.action is rec.Action.TAKE_PROFIT else "risk"
        else:
            raise IntentAdapterError(f"{item.symbol}: unsupported action {item.action.value}")
        rows.append({
            "symbol": item.symbol,
            "side": side.value,
            "intent": intent,
            "decision_date": decision_date,
            "decision_session": session,
            "source_signal": decision_date,
            "priority": len(rows) + 1,
            "expiry_date": plan.valid_until.date(),
            "target_weight": float(item.target_weight),
        })
    return tuple(rows)


def plan_to_intent_frame(plan: rec.RecommendationPlan):
    """Return a Polars frame matching ``band_engine``'s intent schema.

    Polars is imported here, at the actual engine boundary, so the pure plan
    layer remains usable without the research runtime.
    """
    try:
        import polars as pl
    except ImportError as exc:  # pragma: no cover - environment contract
        raise IntentAdapterError("polars is required at the engine boundary") from exc
    rows = plan_to_intents(plan)
    schema = {
        "symbol": pl.String, "side": pl.String, "intent": pl.String,
        "decision_date": pl.Date, "decision_session": pl.String,
        "source_signal": pl.Date, "priority": pl.Int64,
        "expiry_date": pl.Date, "target_weight": pl.Float64,
    }
    return pl.DataFrame(rows, schema=schema)
