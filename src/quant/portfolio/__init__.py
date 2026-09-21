"""Portfolio layer: machine-readable daily recommendations and version coverage.

:mod:`quant.portfolio.recommendations` is the output layer of the daily helper.
It validates a versioned plan against the authoritative account snapshot, keeps
attack (stock) and defense (ETF) sleeves accounted separately, enforces the
registered limits (4 attack / 3 defense / 7 total / 3 new entries / 25% per
symbol / 100% gross) and decides how a new version supersedes an older one.

Scope limits: this layer does not price a book, does not decide fills (that is
``quant.backtest.band_engine``) and never mutates an account - suggestions are
intents, and only back-filled executions plus the account snapshot are truth.
"""

from .recommendations import (
    ACTION_LABELS,
    DECISION_POINT_LABELS,
    DEFAULT_POLICY,
    RISK_STATE_LABELS,
    SLEEVE_LABELS,
    AccountSnapshot,
    Action,
    CoverageReport,
    DecisionPoint,
    FeeSchedule,
    FillRecord,
    IntentOutcome,
    IntentOutcomeKind,
    PlanExposure,
    PlanIdentity,
    PlanPolicy,
    Position,
    Reason,
    RecommendationError,
    RecommendationItem,
    RecommendationLedger,
    RecommendationPlan,
    RiskState,
    Session,
    Side,
    Sleeve,
    build_plan,
    estimate_fees,
    exposure_of,
    order_side,
    risk_amount,
    served_session,
    session_window,
    validate_plan,
)
from .intent_adapter import IntentAdapterError, plan_to_intent_frame, plan_to_intents

__all__ = [
    "ACTION_LABELS",
    "DECISION_POINT_LABELS",
    "DEFAULT_POLICY",
    "RISK_STATE_LABELS",
    "SLEEVE_LABELS",
    "AccountSnapshot",
    "Action",
    "CoverageReport",
    "DecisionPoint",
    "FeeSchedule",
    "FillRecord",
    "IntentOutcome",
    "IntentOutcomeKind",
    "PlanExposure",
    "PlanIdentity",
    "PlanPolicy",
    "Position",
    "Reason",
    "RecommendationError",
    "RecommendationItem",
    "RecommendationLedger",
    "RecommendationPlan",
    "RiskState",
    "Session",
    "Side",
    "Sleeve",
    "build_plan",
    "estimate_fees",
    "exposure_of",
    "order_side",
    "risk_amount",
    "served_session",
    "session_window",
    "validate_plan",
    "IntentAdapterError",
    "plan_to_intents",
    "plan_to_intent_frame",
]
