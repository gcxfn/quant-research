"""Daily recommendation output layer: versioned plans, layer limits, coverage.

A recommendation plan is the machine-readable output of one decision point
(Day0 close, Day1 11:30, Day1 15:00).  Nothing in this module prices a book,
talks to a broker or mutates an account: a plan is a set of *intents*, positions
and cash only ever come from :class:`AccountSnapshot`, and only recorded
:class:`FillRecord` rows decide what was actually executed.

Invariants pinned here (``docs/plans/daily-strategy-output-contract.md``,
``docs/plans/p3-band-contract.md`` 7.3/7.7/1.2):

* one plan = one half-session window (``valid_from``/``valid_until``) plus its
  own identity: ``strategy_version``, ``market_as_of``,
  ``account_snapshot_version`` and ``recommendation_version``;
* sleeves are accounted separately - attack (stocks) at most 4, defense (ETF or
  other defensive assets) at most 3, at most 7 in total, at most 3 new entries
  per plan, at most 25% per symbol and at most 100% gross with the fee reserve
  paid out of cash;
* an empty plan is legal and self-describing through ``entry_paused``; it is
  never padded with a fabricated filler position ("no opportunity" is not a
  system failure);
* identity, freshness and consistency failures are fail-closed: a stale or
  mismatched market / account / strategy input raises
  :class:`RecommendationError` with a stable :class:`Reason` code instead of
  returning advice built from defaulted or empty fields;
* a new version cancels the *unfilled* intents of the previous one; a *filled*
  intent is protected (never re-issued, never overwritten) and the quantity it
  produced is read back from the account snapshot, never from the suggestion;
* unfilled intents never change cash, positions, sellable quantity or cost -
  :class:`RecommendationLedger` records them and nothing else.

``price_lower``/``price_upper`` are the executable band for the served session;
whether an order actually filled is decided by ``quant.backtest.band_engine``
(strict penetration, no favourable intraday path), not here.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

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
]


# --------------------------------------------------------------------------- #
# enums
# --------------------------------------------------------------------------- #
class Sleeve(str, Enum):
    """Asset sleeve.  Stocks are attack; ETF / defensive assets are defense."""

    ATTACK = "attack"
    DEFENSE = "defense"


class Action(str, Enum):
    """Recommendation action for one symbol, or for the account as a whole."""

    NEW = "new"
    ADD = "add"
    REDUCE = "reduce"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    HOLD = "hold"
    NO_ACTION = "no_action"
    ACCOUNT_DELEVER = "account_delever"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class RiskState(str, Enum):
    """Account-level risk state produced by the risk layer."""

    NORMAL = "normal"
    CAUTION = "caution"
    RISK_OFF = "risk_off"


class Session(str, Enum):
    """Half sessions of one trading day."""

    AM = "am"
    PM = "pm"


class DecisionPoint(str, Enum):
    """Decision points of the daily loop."""

    DAY0_CLOSE = "day0_close"  # Day0 after the 15:00 close -> next trading day am
    AM_1130 = "am_1130"        # Day1 11:30                    -> same day pm
    PM_1500 = "pm_1500"        # Day1 15:00                    -> next trading day am


class IntentOutcomeKind(str, Enum):
    """What happened to a previous version's intent when a new one arrived."""

    FILLED = "filled"
    FILLED_PARTIAL = "filled_partial"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class Reason(str, Enum):
    """Stable fail-closed reason codes.  Never replaced by a default value."""

    INVALID_FIELD = "invalid_field"
    FUTURE_INPUT = "future_input"
    MISSING_NEXT_SESSION = "missing_next_session"
    PLAN_EXPIRED = "plan_expired"
    DUPLICATE_VERSION = "duplicate_version"
    DUPLICATE_SYMBOL = "duplicate_symbol"
    MARKET_DATA_STALE = "market_data_stale"
    ACCOUNT_SNAPSHOT_STALE = "account_snapshot_stale"
    MARKET_AS_OF_MISMATCH = "market_as_of_mismatch"
    STRATEGY_VERSION_MISMATCH = "strategy_version_mismatch"
    ACCOUNT_SNAPSHOT_MISMATCH = "account_snapshot_mismatch"
    EQUITY_MISMATCH = "equity_mismatch"
    CASH_MISMATCH = "cash_mismatch"
    UNKNOWN_POSITION_SYMBOL = "unknown_position_symbol"
    POSITION_MISMATCH = "position_mismatch"
    SLEEVE_MISMATCH = "sleeve_mismatch"
    MISSING_POSITION_ITEM = "missing_position_item"
    POSITION_WEIGHT_MISMATCH = "position_weight_mismatch"
    INVALID_TARGET_WEIGHT = "invalid_target_weight"
    SYMBOL_WEIGHT_LIMIT = "symbol_weight_limit"
    GROSS_EXPOSURE_LIMIT = "gross_exposure_limit"
    ATTACK_SLOT_LIMIT = "attack_slot_limit"
    DEFENSE_SLOT_LIMIT = "defense_slot_limit"
    TOTAL_SLOT_LIMIT = "total_slot_limit"
    DAY0_NEW_ENTRY_LIMIT = "day0_new_entry_limit"
    MISSING_INTENT_REASON = "missing_intent_reason"
    MISSING_CHANGE_REASON = "missing_change_reason"
    INVALID_PREVIOUS_ACTION = "invalid_previous_action"
    INVALID_LOT = "invalid_lot"
    INVALID_STOP = "invalid_stop"
    MISSING_RISK_R = "missing_risk_r"
    SELLABLE_QUANTITY_EXCEEDED = "sellable_quantity_exceeded"
    INSUFFICIENT_CASH = "insufficient_cash"
    ENTRY_BLOCKED_BY_RISK_STATE = "entry_blocked_by_risk_state"
    ACCOUNT_DELEVER_SLEEVE = "account_delever_sleeve"
    FILL_WITHOUT_INTENT = "fill_without_intent"
    FILL_EXCEEDS_INTENT = "fill_exceeds_intent"
    FILL_AFTER_ACCOUNT_SNAPSHOT = "fill_after_account_snapshot"
    FILLED_INTENT_NOT_ACKNOWLEDGED = "filled_intent_not_acknowledged"


class RecommendationError(ValueError):
    """Fail-closed rejection.  Carries a stable :class:`Reason` and a detail."""

    def __init__(
        self, reason: Reason, detail: str, *, symbol: str | None = None
    ) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail
        self.symbol = symbol

    def to_mapping(self) -> dict[str, Any]:
        return {"reason": self.reason.value, "detail": self.detail, "symbol": self.symbol}


def _require(
    condition: bool, reason: Reason, detail: str, *, symbol: str | None = None
) -> None:
    if not condition:
        raise RecommendationError(reason, detail, symbol=symbol)


def _as_enum(value: Any, enum_cls: type[Enum], field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise RecommendationError(
            Reason.INVALID_FIELD,
            f"{field_name}={value!r} is not a valid {enum_cls.__name__}",
        ) from exc


def _as_text(value: Any, field_name: str) -> str:
    _require(isinstance(value, str), Reason.INVALID_FIELD, f"{field_name} must be a string")
    return value


def _as_datetime(value: Any, field_name: str) -> dt.datetime:
    _require(
        isinstance(value, dt.datetime),
        Reason.INVALID_FIELD,
        f"{field_name} must be a datetime, got {type(value).__name__}",
    )
    return value


def _as_int(value: Any, field_name: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        Reason.INVALID_FIELD,
        f"{field_name} must be an int, got {type(value).__name__}",
    )
    return value


def _as_float(value: Any, field_name: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value)),
        Reason.INVALID_FIELD,
        f"{field_name} must be a finite number, got {value!r}",
    )
    return float(value)


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    number = _as_float(value, field_name)
    _require(number > 0.0, Reason.INVALID_FIELD, f"{field_name} must be positive")
    return number


# --------------------------------------------------------------------------- #
# action algebra
# --------------------------------------------------------------------------- #
BUY_ACTIONS = frozenset({Action.NEW, Action.ADD})
SELL_ACTIONS = frozenset(
    {Action.REDUCE, Action.TAKE_PROFIT, Action.STOP_LOSS, Action.ACCOUNT_DELEVER}
)
ORDER_ACTIONS = BUY_ACTIONS | SELL_ACTIONS
PASSIVE_ACTIONS = frozenset({Action.HOLD, Action.NO_ACTION})


def order_side(action: Action) -> Side | None:
    """Side of the order an action implies, or ``None`` for hold / no_action."""

    if action in BUY_ACTIONS:
        return Side.BUY
    if action in SELL_ACTIONS:
        return Side.SELL
    return None


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
SESSION_BOUNDS: dict[Session, tuple[dt.time, dt.time]] = {
    Session.AM: (dt.time(9, 30), dt.time(11, 30)),
    Session.PM: (dt.time(13, 0), dt.time(15, 0)),
}

SERVED_SESSION: dict[DecisionPoint, Session] = {
    DecisionPoint.DAY0_CLOSE: Session.AM,
    DecisionPoint.AM_1130: Session.PM,
    DecisionPoint.PM_1500: Session.AM,
}


def served_session(decision_point: DecisionPoint) -> Session:
    """Half session a decision point's plan is allowed to trade in."""

    return SERVED_SESSION[_as_enum(decision_point, DecisionPoint, "decision_point")]


def session_window(
    decision_point: DecisionPoint,
    *,
    trading_day: dt.date,
    next_trading_day: dt.date | None = None,
) -> tuple[dt.datetime, dt.datetime]:
    """``(valid_from, valid_until)`` of the session served by a decision point.

    A 15:00 style decision serves the *next* trading day's morning session, an
    11:30 decision serves the *same* day's afternoon session.  Orders live for
    exactly one half session and die at its end.
    """

    session = served_session(decision_point)
    if session is Session.AM:
        _require(
            next_trading_day is not None,
            Reason.MISSING_NEXT_SESSION,
            "an am-serving decision point needs next_trading_day",
        )
        day = next_trading_day
    else:
        day = trading_day
    _require(isinstance(day, dt.date), Reason.INVALID_FIELD, "trading day must be a date")
    lower, upper = SESSION_BOUNDS[session]
    return dt.datetime.combine(day, lower), dt.datetime.combine(day, upper)


# --------------------------------------------------------------------------- #
# fees and risk
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FeeSchedule:
    """Research fee schedule (AGENTS.md 1.1).  Not a broker fee feed."""

    commission_rate: float = 1e-4
    commission_min: float = 5.0
    stamp_duty_pre_cut: float = 0.001
    stamp_duty_post_cut: float = 0.0005
    stamp_duty_cut_date: dt.date = dt.date(2023, 8, 28)
    slippage_rate: float = 0.0
    lot_size: int = 100

    def commission(self, notional: float) -> float:
        if notional <= 0.0:
            return 0.0
        return max(notional * self.commission_rate, self.commission_min)

    def stamp_duty_on(
        self, *, sleeve: Sleeve, side: Side, notional: float, trade_date: dt.date
    ) -> float:
        """Sell-side stock stamp duty only; ETF (defense) is exempt."""

        if side is not Side.SELL or sleeve is Sleeve.DEFENSE or notional <= 0.0:
            return 0.0
        rate = (
            self.stamp_duty_pre_cut
            if trade_date < self.stamp_duty_cut_date
            else self.stamp_duty_post_cut
        )
        return notional * rate

    def slippage(self, notional: float) -> float:
        return notional * self.slippage_rate


DEFAULT_FEES = FeeSchedule()


def estimate_fees(
    side: Side,
    quantity: int,
    price: float,
    *,
    sleeve: Sleeve,
    trade_date: dt.date,
    schedule: FeeSchedule = DEFAULT_FEES,
) -> float:
    """Commission + sell-side stamp duty + registered slippage for one fill."""

    side = _as_enum(side, Side, "side")
    sleeve = _as_enum(sleeve, Sleeve, "sleeve")
    notional = abs(quantity) * float(price)
    return (
        schedule.commission(notional)
        + schedule.stamp_duty_on(
            sleeve=sleeve, side=side, notional=notional, trade_date=trade_date
        )
        + schedule.slippage(notional)
    )


def risk_amount(
    quantity: int,
    entry_price: float,
    stop_price: float,
    *,
    sleeve: Sleeve,
    trade_date: dt.date,
    schedule: FeeSchedule = DEFAULT_FEES,
) -> float:
    """Fee-inclusive risk R in yuan for one intent.

    R is measured from the *actual* entry cost against the protective stop plus
    both legs' fees (commission / stamp duty / registered slippage), so a signal
    price never stands in for a real cost.
    """

    quantity = _as_int(quantity, "quantity")
    _require(quantity > 0, Reason.INVALID_FIELD, "quantity must be positive")
    entry = _as_float(entry_price, "entry_price")
    stop = _as_float(stop_price, "stop_price")
    _require(0.0 < stop < entry, Reason.INVALID_STOP, "stop must sit below the entry price")
    distance = (entry - stop) * quantity
    fees = estimate_fees(
        Side.BUY, quantity, entry, sleeve=sleeve, trade_date=trade_date, schedule=schedule
    ) + estimate_fees(
        Side.SELL, quantity, stop, sleeve=sleeve, trade_date=trade_date, schedule=schedule
    )
    return distance + fees


# --------------------------------------------------------------------------- #
# account truth
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Position:
    """One authoritative holding.  Batches live in the account engine."""

    symbol: str
    name: str
    sleeve: Sleeve
    quantity: int
    sellable_quantity: int
    average_cost: float
    last_price: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _as_text(self.symbol, "symbol"))
        object.__setattr__(self, "name", _as_text(self.name, "name"))
        object.__setattr__(self, "sleeve", _as_enum(self.sleeve, Sleeve, "sleeve"))
        object.__setattr__(self, "quantity", _as_int(self.quantity, "quantity"))
        object.__setattr__(
            self, "sellable_quantity", _as_int(self.sellable_quantity, "sellable_quantity")
        )
        object.__setattr__(self, "average_cost", _as_float(self.average_cost, "average_cost"))
        object.__setattr__(self, "last_price", _as_float(self.last_price, "last_price"))
        _require(self.symbol != "", Reason.INVALID_FIELD, "symbol must not be empty")
        _require(
            self.quantity > 0, Reason.INVALID_FIELD, f"{self.symbol}: quantity must be positive"
        )
        _require(
            0 <= self.sellable_quantity <= self.quantity,
            Reason.INVALID_FIELD,
            f"{self.symbol}: sellable_quantity must be within [0, quantity]",
        )
        _require(
            self.average_cost > 0.0,
            Reason.INVALID_FIELD,
            f"{self.symbol}: average_cost must be positive",
        )
        _require(
            self.last_price > 0.0,
            Reason.INVALID_FIELD,
            f"{self.symbol}: last_price must be positive",
        )

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    def weight(self, equity: float) -> float:
        return self.market_value / equity

    def to_mapping(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sleeve": self.sleeve.value,
            "quantity": self.quantity,
            "sellable_quantity": self.sellable_quantity,
            "average_cost": self.average_cost,
            "last_price": self.last_price,
        }


@dataclass(frozen=True)
class AccountSnapshot:
    """Versioned, immutable account truth.

    ``as_of`` is when positions and fills were confirmed; ``market_as_of`` is the
    market cut-off the snapshot was valued on and must match the plan's own
    ``market_as_of``.  Suggestions never write into this object.
    """

    snapshot_version: str
    as_of: dt.datetime
    strategy_version: str
    market_as_of: dt.datetime
    equity: float
    cash: float
    positions: tuple[Position, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "snapshot_version", _as_text(self.snapshot_version, "snapshot_version")
        )
        object.__setattr__(self, "as_of", _as_datetime(self.as_of, "as_of"))
        object.__setattr__(
            self, "strategy_version", _as_text(self.strategy_version, "strategy_version")
        )
        object.__setattr__(
            self, "market_as_of", _as_datetime(self.market_as_of, "market_as_of")
        )
        object.__setattr__(self, "equity", _as_float(self.equity, "equity"))
        object.__setattr__(self, "cash", _as_float(self.cash, "cash"))
        object.__setattr__(self, "positions", tuple(self.positions))
        _require(
            self.snapshot_version != "",
            Reason.INVALID_FIELD,
            "snapshot_version must not be empty",
        )
        _require(
            self.strategy_version != "",
            Reason.INVALID_FIELD,
            "strategy_version must not be empty",
        )
        _require(self.equity > 0.0, Reason.INVALID_FIELD, "equity must be positive")
        _require(self.cash >= 0.0, Reason.INVALID_FIELD, "cash must not be negative")
        seen: set[str] = set()
        for position in self.positions:
            _require(
                isinstance(position, Position),
                Reason.INVALID_FIELD,
                f"positions must be Position, got {type(position).__name__}",
            )
            _require(
                position.symbol not in seen,
                Reason.DUPLICATE_SYMBOL,
                f"account snapshot lists {position.symbol} twice",
                symbol=position.symbol,
            )
            seen.add(position.symbol)

    def position(self, symbol: str) -> Position | None:
        for position in self.positions:
            if position.symbol == symbol:
                return position
        return None

    @property
    def held_symbols(self) -> tuple[str, ...]:
        return tuple(position.symbol for position in self.positions)

    @property
    def gross_value(self) -> float:
        return sum(position.market_value for position in self.positions)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "snapshot_version": self.snapshot_version,
            "as_of": self.as_of.isoformat(),
            "strategy_version": self.strategy_version,
            "market_as_of": self.market_as_of.isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "positions": [position.to_mapping() for position in self.positions],
        }


@dataclass(frozen=True)
class FillRecord:
    """One back-filled execution.  Only fills move cash and positions."""

    symbol: str
    side: Side
    quantity: int
    price: float
    fee: float
    traded_at: dt.datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _as_text(self.symbol, "symbol"))
        object.__setattr__(self, "side", _as_enum(self.side, Side, "side"))
        object.__setattr__(self, "quantity", _as_int(self.quantity, "quantity"))
        object.__setattr__(self, "price", _as_float(self.price, "price"))
        object.__setattr__(self, "fee", _as_float(self.fee, "fee"))
        object.__setattr__(self, "traded_at", _as_datetime(self.traded_at, "traded_at"))
        _require(self.symbol != "", Reason.INVALID_FIELD, "fill symbol must not be empty")
        _require(self.quantity > 0, Reason.INVALID_FIELD, "fill quantity must be positive")
        _require(self.price > 0.0, Reason.INVALID_FIELD, "fill price must be positive")
        _require(self.fee >= 0.0, Reason.INVALID_FIELD, "fill fee must not be negative")

    def to_mapping(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "fee": self.fee,
            "traded_at": self.traded_at.isoformat(),
        }


# --------------------------------------------------------------------------- #
# policy, identity, items, plan
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlanPolicy:
    """Registered limits and freshness windows.  Explicit, never implicit."""

    max_market_staleness: dt.timedelta = dt.timedelta(hours=6)
    max_account_staleness: dt.timedelta = dt.timedelta(hours=6)
    symbol_weight_limit: float = 0.25
    total_weight_limit: float = 1.0
    attack_slots: int = 4
    defense_slots: int = 3
    total_slots: int = 7
    max_new_entries: int = 3
    weight_tolerance: float = 1e-6
    fees: FeeSchedule = DEFAULT_FEES

    def __post_init__(self) -> None:
        for name, value in (
            ("max_market_staleness", self.max_market_staleness),
            ("max_account_staleness", self.max_account_staleness),
        ):
            _require(
                isinstance(value, dt.timedelta) and value > dt.timedelta(0),
                Reason.INVALID_FIELD,
                f"{name} must be a positive timedelta",
            )
        for name, value in (
            ("symbol_weight_limit", self.symbol_weight_limit),
            ("total_weight_limit", self.total_weight_limit),
        ):
            _require(
                0.0 < float(value) <= 1.0,
                Reason.INVALID_FIELD,
                f"{name} must be inside (0, 1]",
            )
        for name, value in (
            ("attack_slots", self.attack_slots),
            ("defense_slots", self.defense_slots),
            ("total_slots", self.total_slots),
            ("max_new_entries", self.max_new_entries),
        ):
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                Reason.INVALID_FIELD,
                f"{name} must be a non-negative int",
            )


DEFAULT_POLICY = PlanPolicy()


@dataclass(frozen=True)
class PlanIdentity:
    """The three identities a plan and its account snapshot must agree on."""

    strategy_version: str
    market_as_of: dt.datetime
    account_snapshot_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "strategy_version", _as_text(self.strategy_version, "strategy_version")
        )
        object.__setattr__(self, "market_as_of", _as_datetime(self.market_as_of, "market_as_of"))
        object.__setattr__(
            self,
            "account_snapshot_version",
            _as_text(self.account_snapshot_version, "account_snapshot_version"),
        )
        _require(
            self.strategy_version != "",
            Reason.INVALID_FIELD,
            "strategy_version must not be empty",
        )
        _require(
            self.account_snapshot_version != "",
            Reason.INVALID_FIELD,
            "account_snapshot_version must not be empty",
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "strategy_version": self.strategy_version,
            "market_as_of": self.market_as_of.isoformat(),
            "account_snapshot_version": self.account_snapshot_version,
        }


@dataclass(frozen=True)
class RecommendationItem:
    """One symbol's recommendation inside a version.

    ``recommended_quantity`` is the size of *this* order: positive for buys and
    sells alike, zero for hold / no_action.  ``target_weight`` is the post-trade
    weight of the symbol in account equity, so a full exit states ``0.0``.
    ``current_quantity`` must equal the authoritative held quantity.
    """

    symbol: str
    name: str
    sleeve: Sleeve
    action: Action
    current_quantity: int
    recommended_quantity: int
    target_weight: float
    valid_until: dt.datetime
    trigger_reason: str
    invalidation_reason: str
    price_lower: float | None = None
    price_upper: float | None = None
    risk_r: float | None = None
    stop_price: float | None = None
    previous_action: Action | None = None
    change_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _as_text(self.symbol, "symbol"))
        object.__setattr__(self, "name", _as_text(self.name, "name"))
        object.__setattr__(self, "sleeve", _as_enum(self.sleeve, Sleeve, "sleeve"))
        object.__setattr__(self, "action", _as_enum(self.action, Action, "action"))
        object.__setattr__(
            self, "current_quantity", _as_int(self.current_quantity, "current_quantity")
        )
        object.__setattr__(
            self,
            "recommended_quantity",
            _as_int(self.recommended_quantity, "recommended_quantity"),
        )
        object.__setattr__(
            self, "target_weight", _as_float(self.target_weight, "target_weight")
        )
        object.__setattr__(self, "valid_until", _as_datetime(self.valid_until, "valid_until"))
        object.__setattr__(
            self, "trigger_reason", _as_text(self.trigger_reason, "trigger_reason")
        )
        object.__setattr__(
            self,
            "invalidation_reason",
            _as_text(self.invalidation_reason, "invalidation_reason"),
        )
        object.__setattr__(self, "price_lower", _optional_float(self.price_lower, "price_lower"))
        object.__setattr__(self, "price_upper", _optional_float(self.price_upper, "price_upper"))
        object.__setattr__(self, "risk_r", _optional_float(self.risk_r, "risk_r"))
        object.__setattr__(self, "stop_price", _optional_float(self.stop_price, "stop_price"))
        if self.previous_action is not None:
            object.__setattr__(
                self,
                "previous_action",
                _as_enum(self.previous_action, Action, "previous_action"),
            )
        object.__setattr__(self, "change_reason", _as_text(self.change_reason, "change_reason"))
        _require(self.symbol != "", Reason.INVALID_FIELD, "item symbol must not be empty")
        _require(self.name != "", Reason.INVALID_FIELD, f"{self.symbol}: name must not be empty")
        _require(
            self.current_quantity >= 0,
            Reason.INVALID_FIELD,
            f"{self.symbol}: current_quantity must be >= 0",
        )
        _require(
            self.recommended_quantity >= 0,
            Reason.INVALID_FIELD,
            f"{self.symbol}: recommended_quantity must be >= 0",
        )
        _require(
            self.target_weight >= 0.0,
            Reason.INVALID_FIELD,
            f"{self.symbol}: target_weight must be >= 0",
        )
        if self.price_lower is not None and self.price_upper is not None:
            _require(
                self.price_lower <= self.price_upper,
                Reason.INVALID_FIELD,
                f"{self.symbol}: price_lower must not exceed price_upper",
            )

    @property
    def side(self) -> Side | None:
        return order_side(self.action)

    @property
    def is_order(self) -> bool:
        return self.side is not None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "sleeve": self.sleeve.value,
            "action": self.action.value,
            "current_quantity": self.current_quantity,
            "recommended_quantity": self.recommended_quantity,
            "target_weight": self.target_weight,
            "price_lower": self.price_lower,
            "price_upper": self.price_upper,
            "trigger_reason": self.trigger_reason,
            "invalidation_reason": self.invalidation_reason,
            "valid_until": self.valid_until.isoformat(),
            "risk_r": self.risk_r,
            "stop_price": self.stop_price,
            "previous_action": (
                None if self.previous_action is None else self.previous_action.value
            ),
            "change_reason": self.change_reason,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RecommendationItem":
        _require(
            isinstance(payload, Mapping),
            Reason.INVALID_FIELD,
            "item payload must be a mapping",
        )
        previous = payload.get("previous_action")
        return cls(
            symbol=payload["symbol"],
            name=payload["name"],
            sleeve=payload["sleeve"],
            action=payload["action"],
            current_quantity=payload["current_quantity"],
            recommended_quantity=payload["recommended_quantity"],
            target_weight=payload["target_weight"],
            valid_until=dt.datetime.fromisoformat(payload["valid_until"]),
            trigger_reason=payload["trigger_reason"],
            invalidation_reason=payload["invalidation_reason"],
            price_lower=payload.get("price_lower"),
            price_upper=payload.get("price_upper"),
            risk_r=payload.get("risk_r"),
            stop_price=payload.get("stop_price"),
            previous_action=None if previous is None else Action(previous),
            change_reason=payload.get("change_reason", ""),
        )


# display text is kept separate from the machine-readable fields
ACTION_LABELS: dict[Action, str] = {
    Action.NEW: "新建",
    Action.ADD: "补仓",
    Action.REDUCE: "减仓",
    Action.TAKE_PROFIT: "止盈",
    Action.STOP_LOSS: "止损",
    Action.HOLD: "持有",
    Action.NO_ACTION: "不动",
    Action.ACCOUNT_DELEVER: "账户级降仓",
}
SLEEVE_LABELS: dict[Sleeve, str] = {Sleeve.ATTACK: "进攻", Sleeve.DEFENSE: "防御"}
RISK_STATE_LABELS: dict[RiskState, str] = {
    RiskState.NORMAL: "正常",
    RiskState.CAUTION: "观察",
    RiskState.RISK_OFF: "风险关闭",
}
DECISION_POINT_LABELS: dict[DecisionPoint, str] = {
    DecisionPoint.DAY0_CLOSE: "Day0收盘",
    DecisionPoint.AM_1130: "11:30",
    DecisionPoint.PM_1500: "15:00",
}


@dataclass(frozen=True)
class RecommendationPlan:
    """One versioned recommendation set for one half session."""

    recommendation_version: str
    decision_point: DecisionPoint
    generated_at: dt.datetime
    market_as_of: dt.datetime
    account_snapshot_version: str
    strategy_version: str
    valid_from: dt.datetime
    valid_until: dt.datetime
    risk_state: RiskState
    account_action: Action
    equity: float
    cash: float
    items: tuple[RecommendationItem, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recommendation_version",
            _as_text(self.recommendation_version, "recommendation_version"),
        )
        object.__setattr__(
            self, "decision_point", _as_enum(self.decision_point, DecisionPoint, "decision_point")
        )
        object.__setattr__(self, "generated_at", _as_datetime(self.generated_at, "generated_at"))
        object.__setattr__(self, "market_as_of", _as_datetime(self.market_as_of, "market_as_of"))
        object.__setattr__(
            self,
            "account_snapshot_version",
            _as_text(self.account_snapshot_version, "account_snapshot_version"),
        )
        object.__setattr__(
            self, "strategy_version", _as_text(self.strategy_version, "strategy_version")
        )
        object.__setattr__(self, "valid_from", _as_datetime(self.valid_from, "valid_from"))
        object.__setattr__(self, "valid_until", _as_datetime(self.valid_until, "valid_until"))
        object.__setattr__(self, "risk_state", _as_enum(self.risk_state, RiskState, "risk_state"))
        object.__setattr__(
            self, "account_action", _as_enum(self.account_action, Action, "account_action")
        )
        object.__setattr__(self, "equity", _as_float(self.equity, "equity"))
        object.__setattr__(self, "cash", _as_float(self.cash, "cash"))
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "note", _as_text(self.note, "note"))
        for item in self.items:
            _require(
                isinstance(item, RecommendationItem),
                Reason.INVALID_FIELD,
                f"items must be RecommendationItem, got {type(item).__name__}",
            )
        _require(
            self.recommendation_version != "",
            Reason.INVALID_FIELD,
            "recommendation_version must not be empty",
        )
        _require(
            self.strategy_version != "", Reason.INVALID_FIELD, "strategy_version must not be empty"
        )
        _require(
            self.account_snapshot_version != "",
            Reason.INVALID_FIELD,
            "account_snapshot_version must not be empty",
        )
        _require(self.equity > 0.0, Reason.INVALID_FIELD, "equity must be positive")
        _require(self.cash >= 0.0, Reason.INVALID_FIELD, "cash must not be negative")
        _require(
            self.valid_from <= self.valid_until,
            Reason.INVALID_FIELD,
            "valid_from must not be after valid_until",
        )

    # -- convenience ------------------------------------------------------ #
    @property
    def order_items(self) -> tuple[RecommendationItem, ...]:
        return tuple(item for item in self.items if item.is_order)

    @property
    def new_entry_items(self) -> tuple[RecommendationItem, ...]:
        return tuple(item for item in self.items if item.action is Action.NEW)

    @property
    def entry_paused(self) -> bool:
        """True when this version opens nothing new - the explicit "no entry"."""

        return not any(item.action in BUY_ACTIONS for item in self.items)

    def item(self, symbol: str) -> RecommendationItem | None:
        for item in self.items:
            if item.symbol == symbol:
                return item
        return None

    def is_live(self, as_of: dt.datetime) -> bool:
        return self.valid_from <= as_of < self.valid_until

    def is_expired(self, as_of: dt.datetime) -> bool:
        return as_of >= self.valid_until

    # -- serialization ---------------------------------------------------- #
    def to_mapping(self) -> dict[str, Any]:
        return {
            "recommendation_version": self.recommendation_version,
            "decision_point": self.decision_point.value,
            "generated_at": self.generated_at.isoformat(),
            "market_as_of": self.market_as_of.isoformat(),
            "account_snapshot_version": self.account_snapshot_version,
            "strategy_version": self.strategy_version,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "risk_state": self.risk_state.value,
            "account_action": self.account_action.value,
            "equity": self.equity,
            "cash": self.cash,
            "entry_paused": self.entry_paused,
            "note": self.note,
            "items": [item.to_mapping() for item in self.items],
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RecommendationPlan":
        _require(
            isinstance(payload, Mapping), Reason.INVALID_FIELD, "plan payload must be a mapping"
        )
        return cls(
            recommendation_version=payload["recommendation_version"],
            decision_point=payload["decision_point"],
            generated_at=dt.datetime.fromisoformat(payload["generated_at"]),
            market_as_of=dt.datetime.fromisoformat(payload["market_as_of"]),
            account_snapshot_version=payload["account_snapshot_version"],
            strategy_version=payload["strategy_version"],
            valid_from=dt.datetime.fromisoformat(payload["valid_from"]),
            valid_until=dt.datetime.fromisoformat(payload["valid_until"]),
            risk_state=payload["risk_state"],
            account_action=payload["account_action"],
            equity=payload["equity"],
            cash=payload["cash"],
            items=tuple(RecommendationItem.from_mapping(row) for row in payload.get("items", ())),
            note=payload.get("note", ""),
        )

    def render_lines(self) -> tuple[str, ...]:
        """Human display text, kept apart from the machine-readable fields."""

        lines = [
            f"建议版本 {self.recommendation_version}"
            f"|决策点 {DECISION_POINT_LABELS[self.decision_point]}"
            f"|行情截止 {self.market_as_of:%Y-%m-%d %H:%M}"
            f"|有效至 {self.valid_until:%Y-%m-%d %H:%M}",
            f"账户权益 {self.equity:,.2f}|现金 {self.cash:,.2f}"
            f"|风险状态 {RISK_STATE_LABELS[self.risk_state]}"
            f"|账户动作 {ACTION_LABELS[self.account_action]}",
        ]
        if self.entry_paused:
            lines.append("本版不新增：无满足条件的候选（非系统故障）")
        for item in self.items:
            if item.price_lower is None or item.price_upper is None:
                band = "-"
            else:
                band = f"{item.price_lower:.3f}~{item.price_upper:.3f}"
            lines.append(
                f"[{SLEEVE_LABELS[item.sleeve]}] {item.symbol} {item.name} "
                f"{ACTION_LABELS[item.action]} 现持{item.current_quantity} "
                f"建议{item.recommended_quantity} 目标{item.target_weight:.2%} 区间{band} "
                f"触发:{item.trigger_reason} 失效:{item.invalidation_reason or '-'}"
            )
        if self.note:
            lines.append(self.note)
        return tuple(lines)


# --------------------------------------------------------------------------- #
# exposure accounting
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlanExposure:
    """Separate attack / defense accounting plus the registered limit flags."""

    equity: float
    cash: float
    attack_weight: float
    defense_weight: float
    total_weight: float
    attack_symbols: int
    defense_symbols: int
    total_symbols: int
    new_entries: int
    buy_notional: float
    buy_fees: float
    symbol_limit_breaches: tuple[str, ...]
    uncovered_positions: tuple[str, ...]
    total_limit_breached: bool
    attack_slot_breached: bool
    defense_slot_breached: bool
    total_slot_breached: bool
    new_entry_limit_breached: bool

    def __post_init__(self) -> None:
        # Symbol fields are part of the machine-readable output: coerce and
        # refuse anything that is not a non-empty symbol, so a slip such as
        # passing Position objects can never reach ``to_mapping``.
        for name in ("symbol_limit_breaches", "uncovered_positions"):
            symbols = tuple(getattr(self, name))
            for symbol in symbols:
                _require(
                    isinstance(symbol, str) and symbol != "",
                    Reason.INVALID_FIELD,
                    f"{name} must contain non-empty symbols, got {symbol!r}",
                )
            object.__setattr__(self, name, symbols)

    @property
    def ok(self) -> bool:
        return not (
            self.symbol_limit_breaches
            or self.uncovered_positions
            or self.total_limit_breached
            or self.attack_slot_breached
            or self.defense_slot_breached
            or self.total_slot_breached
            or self.new_entry_limit_breached
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "equity": self.equity,
            "cash": self.cash,
            "attack_weight": self.attack_weight,
            "defense_weight": self.defense_weight,
            "total_weight": self.total_weight,
            "attack_symbols": self.attack_symbols,
            "defense_symbols": self.defense_symbols,
            "total_symbols": self.total_symbols,
            "new_entries": self.new_entries,
            "buy_notional": self.buy_notional,
            "buy_fees": self.buy_fees,
            "symbol_limit_breaches": list(self.symbol_limit_breaches),
            "uncovered_positions": list(self.uncovered_positions),
            "total_limit_breached": self.total_limit_breached,
            "attack_slot_breached": self.attack_slot_breached,
            "defense_slot_breached": self.defense_slot_breached,
            "total_slot_breached": self.total_slot_breached,
            "new_entry_limit_breached": self.new_entry_limit_breached,
            "ok": self.ok,
        }


def exposure_of(
    plan: RecommendationPlan,
    *,
    account: AccountSnapshot,
    policy: PlanPolicy | None = None,
) -> PlanExposure:
    """Layer statistics of a plan.  Computes flags but never raises on them."""

    pol = policy or DEFAULT_POLICY
    attack_weight = 0.0
    defense_weight = 0.0
    attack_symbols = 0
    defense_symbols = 0
    breaches: list[str] = []
    covered: set[str] = set()
    for item in plan.items:
        covered.add(item.symbol)
        weight = item.target_weight
        if item.sleeve is Sleeve.ATTACK:
            attack_weight += weight
            if weight > pol.weight_tolerance:
                attack_symbols += 1
        else:
            defense_weight += weight
            if weight > pol.weight_tolerance:
                defense_symbols += 1
        if weight > pol.symbol_weight_limit + pol.weight_tolerance:
            breaches.append(item.symbol)
    # A holding the plan never mentions still exists after the session, so it is
    # counted at its carried weight.  Validated plans cover every holding (the
    # hard gate below), so this only keeps an unvalidated plan's statistics from
    # understating sleeves, seats and the per-symbol cap.
    uncovered = tuple(
        position for position in account.positions if position.symbol not in covered
    )
    for position in uncovered:
        weight = position.weight(account.equity)
        if position.sleeve is Sleeve.ATTACK:
            attack_weight += weight
            if weight > pol.weight_tolerance:
                attack_symbols += 1
        else:
            defense_weight += weight
            if weight > pol.weight_tolerance:
                defense_symbols += 1
        if weight > pol.symbol_weight_limit + pol.weight_tolerance:
            breaches.append(position.symbol)
    buy_notional = 0.0
    buy_fees = 0.0
    trade_date = plan.valid_from.date()
    for item in plan.items:
        if item.action not in BUY_ACTIONS:
            continue
        price = item.price_upper or 0.0
        notional = item.recommended_quantity * price
        buy_notional += notional
        buy_fees += estimate_fees(
            Side.BUY,
            item.recommended_quantity,
            price,
            sleeve=item.sleeve,
            trade_date=trade_date,
            schedule=pol.fees,
        )
    total_weight = attack_weight + defense_weight
    total_symbols = attack_symbols + defense_symbols
    new_entries = len(plan.new_entry_items)
    return PlanExposure(
        equity=plan.equity,
        cash=plan.cash,
        attack_weight=attack_weight,
        defense_weight=defense_weight,
        total_weight=total_weight,
        attack_symbols=attack_symbols,
        defense_symbols=defense_symbols,
        total_symbols=total_symbols,
        new_entries=new_entries,
        buy_notional=buy_notional,
        buy_fees=buy_fees,
        symbol_limit_breaches=tuple(breaches),
        uncovered_positions=tuple(position.symbol for position in uncovered),
        total_limit_breached=total_weight > pol.total_weight_limit + pol.weight_tolerance,
        attack_slot_breached=attack_symbols > pol.attack_slots,
        defense_slot_breached=defense_symbols > pol.defense_slots,
        total_slot_breached=total_symbols > pol.total_slots,
        new_entry_limit_breached=new_entries > pol.max_new_entries,
    )


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _validate_header(
    plan: RecommendationPlan, account: AccountSnapshot, policy: PlanPolicy
) -> None:
    _require(
        plan.strategy_version == account.strategy_version,
        Reason.STRATEGY_VERSION_MISMATCH,
        f"plan strategy_version={plan.strategy_version!r} but the account snapshot has "
        f"{account.strategy_version!r}",
    )
    _require(
        plan.market_as_of == account.market_as_of,
        Reason.MARKET_AS_OF_MISMATCH,
        f"plan market_as_of={plan.market_as_of.isoformat()} but the account snapshot has "
        f"{account.market_as_of.isoformat()}",
    )
    _require(
        plan.account_snapshot_version == account.snapshot_version,
        Reason.ACCOUNT_SNAPSHOT_MISMATCH,
        f"plan account_snapshot_version={plan.account_snapshot_version!r} but the account "
        f"snapshot is {account.snapshot_version!r}",
    )
    money_tolerance = policy.weight_tolerance * max(account.equity, 1.0)
    _require(
        abs(plan.equity - account.equity) <= money_tolerance,
        Reason.EQUITY_MISMATCH,
        f"plan equity={plan.equity} but the account has {account.equity}",
    )
    _require(
        abs(plan.cash - account.cash) <= money_tolerance,
        Reason.CASH_MISMATCH,
        f"plan cash={plan.cash} but the account has {account.cash}",
    )
    _require(
        plan.market_as_of <= plan.generated_at,
        Reason.FUTURE_INPUT,
        f"market_as_of={plan.market_as_of.isoformat()} is after "
        f"generated_at={plan.generated_at.isoformat()}",
    )
    _require(
        account.as_of <= plan.generated_at,
        Reason.FUTURE_INPUT,
        f"account snapshot as_of={account.as_of.isoformat()} is after "
        f"generated_at={plan.generated_at.isoformat()}",
    )
    _require(
        plan.generated_at < plan.valid_until,
        Reason.PLAN_EXPIRED,
        f"valid_until={plan.valid_until.isoformat()} is not after "
        f"generated_at={plan.generated_at.isoformat()}",
    )
    _require(
        plan.generated_at - plan.market_as_of <= policy.max_market_staleness,
        Reason.MARKET_DATA_STALE,
        f"market_as_of={plan.market_as_of.isoformat()} is older than "
        f"{policy.max_market_staleness} relative to generated_at={plan.generated_at.isoformat()}",
    )
    _require(
        plan.generated_at - account.as_of <= policy.max_account_staleness,
        Reason.ACCOUNT_SNAPSHOT_STALE,
        f"account snapshot as_of={account.as_of.isoformat()} is older than "
        f"{policy.max_account_staleness} relative to "
        f"generated_at={plan.generated_at.isoformat()}",
    )


def _current_weight(item: RecommendationItem, account: AccountSnapshot) -> float:
    position = account.position(item.symbol)
    if position is None:
        return 0.0
    return position.weight(account.equity)


def _validate_item(
    item: RecommendationItem,
    *,
    plan: RecommendationPlan,
    account: AccountSnapshot,
    policy: PlanPolicy,
) -> None:
    symbol = item.symbol
    position = account.position(symbol)
    current_weight = _current_weight(item, account)
    if position is None:
        _require(
            item.current_quantity == 0,
            Reason.UNKNOWN_POSITION_SYMBOL,
            f"{symbol} is not in the account snapshot but claims current_quantity="
            f"{item.current_quantity}",
            symbol=symbol,
        )
    else:
        _require(
            item.current_quantity == position.quantity,
            Reason.POSITION_MISMATCH,
            f"{symbol}: current_quantity={item.current_quantity} but the account holds "
            f"{position.quantity}",
            symbol=symbol,
        )
        _require(
            item.sleeve is position.sleeve,
            Reason.SLEEVE_MISMATCH,
            f"{symbol}: sleeve={item.sleeve.value} but the account has {position.sleeve.value}",
            symbol=symbol,
        )
    _require(
        plan.valid_from <= item.valid_until <= plan.valid_until,
        Reason.INVALID_FIELD,
        f"{symbol}: item valid_until={item.valid_until.isoformat()} is outside the plan window "
        f"[{plan.valid_from.isoformat()}, {plan.valid_until.isoformat()}]",
        symbol=symbol,
    )
    _require(
        item.trigger_reason.strip() != "",
        Reason.MISSING_INTENT_REASON,
        f"{symbol}: trigger_reason must not be empty",
        symbol=symbol,
    )
    if item.is_order:
        _require(
            item.invalidation_reason.strip() != "",
            Reason.MISSING_INTENT_REASON,
            f"{symbol}: invalidation_reason must not be empty for action "
            f"{item.action.value}",
            symbol=symbol,
        )
    if item.action is Action.NEW:
        _require(
            item.previous_action is None,
            Reason.INVALID_PREVIOUS_ACTION,
            f"{symbol}: a new entry must not carry previous_action="
            f"{item.previous_action.value if item.previous_action else None}",
            symbol=symbol,
        )
    else:
        _require(
            item.previous_action is not None or item.change_reason.strip() != "",
            Reason.MISSING_CHANGE_REASON,
            f"{symbol}: action {item.action.value} needs previous_action or change_reason",
            symbol=symbol,
        )
    if item.action is Action.NEW:
        _require(
            item.current_quantity == 0 and item.recommended_quantity > 0,
            Reason.INVALID_FIELD,
            f"{symbol}: a new entry needs current_quantity=0 and a positive order size",
            symbol=symbol,
        )
    if item.action in BUY_ACTIONS:
        _require(
            item.recommended_quantity % policy.fees.lot_size == 0,
            Reason.INVALID_LOT,
            f"{symbol}: buy size {item.recommended_quantity} is not a multiple of "
            f"{policy.fees.lot_size}",
            symbol=symbol,
        )
        _require(
            item.target_weight > current_weight + policy.weight_tolerance,
            Reason.INVALID_TARGET_WEIGHT,
            f"{symbol}: buy target_weight={item.target_weight} must exceed the current "
            f"weight {current_weight}",
            symbol=symbol,
        )
    if item.action in SELL_ACTIONS:
        _require(
            item.recommended_quantity > 0,
            Reason.INVALID_FIELD,
            f"{symbol}: sell size must be positive",
            symbol=symbol,
        )
        if position is not None:
            _require(
                item.recommended_quantity <= position.quantity,
                Reason.POSITION_MISMATCH,
                f"{symbol}: sell size {item.recommended_quantity} exceeds the held "
                f"{position.quantity}",
                symbol=symbol,
            )
            _require(
                item.recommended_quantity <= position.sellable_quantity,
                Reason.SELLABLE_QUANTITY_EXCEEDED,
                f"{symbol}: sell size {item.recommended_quantity} exceeds the sellable "
                f"{position.sellable_quantity}",
                symbol=symbol,
            )
        _require(
            item.target_weight < current_weight - policy.weight_tolerance,
            Reason.INVALID_TARGET_WEIGHT,
            f"{symbol}: sell target_weight={item.target_weight} must stay below the current "
            f"weight {current_weight}",
            symbol=symbol,
        )
    if item.action in PASSIVE_ACTIONS:
        _require(
            item.recommended_quantity == 0,
            Reason.INVALID_FIELD,
            f"{symbol}: {item.action.value} must not carry an order size",
            symbol=symbol,
        )
        _require(
            abs(item.target_weight - current_weight) <= policy.weight_tolerance,
            Reason.POSITION_WEIGHT_MISMATCH,
            f"{symbol}: {item.action.value} target_weight={item.target_weight} must equal the "
            f"account weight {current_weight}",
            symbol=symbol,
        )
    if item.is_order:
        _require(
            item.price_lower is not None and item.price_upper is not None,
            Reason.INVALID_FIELD,
            f"{symbol}: order action {item.action.value} needs price_lower and price_upper",
            symbol=symbol,
        )
    if item.sleeve is Sleeve.ATTACK and item.action is not Action.NO_ACTION:
        _require(
            item.stop_price is not None and item.risk_r is not None,
            Reason.MISSING_RISK_R,
            f"{symbol}: attack items need stop_price and risk_r",
            symbol=symbol,
        )
    _require(
        (item.stop_price is None) == (item.risk_r is None),
        Reason.MISSING_RISK_R,
        f"{symbol}: stop_price and risk_r must be given together",
        symbol=symbol,
    )
    if (
        item.action in BUY_ACTIONS
        and item.price_lower is not None
        and item.stop_price is not None
    ):
        _require(
            item.stop_price < item.price_lower,
            Reason.INVALID_STOP,
            f"{symbol}: stop_price={item.stop_price} must sit below the buy band lower "
            f"bound {item.price_lower}",
            symbol=symbol,
        )
    if item.action is Action.ACCOUNT_DELEVER:
        _require(
            item.sleeve is Sleeve.ATTACK,
            Reason.ACCOUNT_DELEVER_SLEEVE,
            f"{symbol}: account_delever applies to the attack sleeve only",
            symbol=symbol,
        )


def _enforce_limits(
    plan: RecommendationPlan, exposure: PlanExposure, policy: PlanPolicy
) -> None:
    _require(
        not exposure.symbol_limit_breaches,
        Reason.SYMBOL_WEIGHT_LIMIT,
        f"symbols above {policy.symbol_weight_limit:.0%}: "
        f"{', '.join(exposure.symbol_limit_breaches)}",
    )
    _require(
        not exposure.total_limit_breached,
        Reason.GROSS_EXPOSURE_LIMIT,
        f"gross target weight {exposure.total_weight:.6f} is above "
        f"{policy.total_weight_limit:.6f}",
    )
    _require(
        not exposure.attack_slot_breached,
        Reason.ATTACK_SLOT_LIMIT,
        f"attack sleeve holds {exposure.attack_symbols} positions, limit "
        f"{policy.attack_slots}",
    )
    _require(
        not exposure.defense_slot_breached,
        Reason.DEFENSE_SLOT_LIMIT,
        f"defense sleeve holds {exposure.defense_symbols} positions, limit "
        f"{policy.defense_slots}",
    )
    _require(
        not exposure.total_slot_breached,
        Reason.TOTAL_SLOT_LIMIT,
        f"portfolio holds {exposure.total_symbols} positions, limit {policy.total_slots}",
    )
    _require(
        not exposure.new_entry_limit_breached,
        Reason.DAY0_NEW_ENTRY_LIMIT,
        f"plan opens {exposure.new_entries} new positions, limit {policy.max_new_entries}",
    )
    cost = exposure.buy_notional + exposure.buy_fees
    _require(
        cost <= plan.cash + policy.weight_tolerance * max(plan.equity, 1.0),
        Reason.INSUFFICIENT_CASH,
        f"buy orders need {cost:.4f} (notional {exposure.buy_notional:.4f} + fees "
        f"{exposure.buy_fees:.4f}) but only {plan.cash:.4f} is available",
    )


def validate_plan(
    plan: RecommendationPlan,
    *,
    account: AccountSnapshot,
    policy: PlanPolicy | None = None,
) -> PlanExposure:
    """Fail-closed validation.  Returns layer statistics or raises.

    Nothing is defaulted or repaired: a plan that cannot be proven against the
    account snapshot and the registered limits is rejected with a
    :class:`Reason` code.
    """

    pol = policy or DEFAULT_POLICY
    _require(
        isinstance(plan, RecommendationPlan),
        Reason.INVALID_FIELD,
        f"plan must be a RecommendationPlan, got {type(plan).__name__}",
    )
    _require(
        isinstance(account, AccountSnapshot),
        Reason.INVALID_FIELD,
        f"account must be an AccountSnapshot, got {type(account).__name__}",
    )
    _validate_header(plan, account, pol)
    seen: set[str] = set()
    for item in plan.items:
        _require(
            item.symbol not in seen,
            Reason.DUPLICATE_SYMBOL,
            f"plan lists {item.symbol} twice",
            symbol=item.symbol,
        )
        seen.add(item.symbol)
    for position in account.positions:
        _require(
            position.symbol in seen,
            Reason.MISSING_POSITION_ITEM,
            f"held {position.symbol} has no item in this version "
            f"(hold/no_action must be explicit)",
            symbol=position.symbol,
        )
    for item in plan.items:
        _validate_item(item, plan=plan, account=account, policy=pol)
    exposure = exposure_of(plan, account=account, policy=pol)
    _enforce_limits(plan, exposure, pol)
    return exposure


def build_plan(
    *,
    decision_point: DecisionPoint,
    generated_at: dt.datetime,
    identity: PlanIdentity,
    account: AccountSnapshot,
    recommendation_version: str,
    valid_from: dt.datetime,
    valid_until: dt.datetime,
    items: Sequence[RecommendationItem] = (),
    risk_state: RiskState = RiskState.NORMAL,
    account_action: Action = Action.NO_ACTION,
    note: str = "",
    policy: PlanPolicy | None = None,
) -> RecommendationPlan:
    """Build and validate one version.  Raises rather than defaulting fields."""

    pol = policy or DEFAULT_POLICY
    item_tuple = tuple(items)
    for item in item_tuple:
        _require(
            isinstance(item, RecommendationItem),
            Reason.INVALID_FIELD,
            f"items must be RecommendationItem, got {type(item).__name__}",
        )
    blocked = _as_enum(risk_state, RiskState, "risk_state") is RiskState.RISK_OFF or (
        _as_enum(account_action, Action, "account_action") is Action.ACCOUNT_DELEVER
    )
    if blocked:
        for item in item_tuple:
            _require(
                not (item.sleeve is Sleeve.ATTACK and item.action in BUY_ACTIONS),
                Reason.ENTRY_BLOCKED_BY_RISK_STATE,
                f"{item.symbol}: account de-lever / risk-off forbids new attack exposure",
                symbol=item.symbol,
            )
    plan = RecommendationPlan(
        recommendation_version=recommendation_version,
        decision_point=decision_point,
        generated_at=generated_at,
        market_as_of=identity.market_as_of,
        account_snapshot_version=identity.account_snapshot_version,
        strategy_version=identity.strategy_version,
        valid_from=valid_from,
        valid_until=valid_until,
        risk_state=risk_state,
        account_action=account_action,
        equity=account.equity,
        cash=account.cash,
        items=item_tuple,
        note=note,
    )
    validate_plan(plan, account=account, policy=pol)
    return plan


# --------------------------------------------------------------------------- #
# version coverage
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IntentOutcome:
    """What a previous version's intent became once a new version arrived."""

    symbol: str
    sleeve: Sleeve
    previous_action: Action
    kind: IntentOutcomeKind
    recommended_quantity: int
    filled_quantity: int
    account_quantity: int
    note: str = ""

    @property
    def protected(self) -> bool:
        """A filled intent is protected: never re-issued, never overwritten."""

        return self.kind in (IntentOutcomeKind.FILLED, IntentOutcomeKind.FILLED_PARTIAL)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "sleeve": self.sleeve.value,
            "previous_action": self.previous_action.value,
            "kind": self.kind.value,
            "recommended_quantity": self.recommended_quantity,
            "filled_quantity": self.filled_quantity,
            "account_quantity": self.account_quantity,
            "protected": self.protected,
            "note": self.note,
        }


@dataclass(frozen=True)
class CoverageReport:
    """Outcome of publishing a new version over the previous one."""

    superseded_version: str | None
    superseded_valid_until: dt.datetime | None
    new_version: str
    outcomes: tuple[IntentOutcome, ...]

    def outcome(self, symbol: str) -> IntentOutcome | None:
        for outcome in self.outcomes:
            if outcome.symbol == symbol:
                return outcome
        return None

    @property
    def protected_symbols(self) -> tuple[str, ...]:
        return tuple(outcome.symbol for outcome in self.outcomes if outcome.protected)

    @property
    def cancelled_symbols(self) -> tuple[str, ...]:
        return tuple(
            outcome.symbol
            for outcome in self.outcomes
            if outcome.kind is IntentOutcomeKind.CANCELLED
        )

    @property
    def expired_symbols(self) -> tuple[str, ...]:
        return tuple(
            outcome.symbol
            for outcome in self.outcomes
            if outcome.kind is IntentOutcomeKind.EXPIRED
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "superseded_version": self.superseded_version,
            "superseded_valid_until": (
                None
                if self.superseded_valid_until is None
                else self.superseded_valid_until.isoformat()
            ),
            "new_version": self.new_version,
            "protected_symbols": list(self.protected_symbols),
            "cancelled_symbols": list(self.cancelled_symbols),
            "expired_symbols": list(self.expired_symbols),
            "outcomes": [outcome.to_mapping() for outcome in self.outcomes],
        }


class RecommendationLedger:
    """Holds the live version and decides how versions supersede each other.

    The ledger is deliberately passive.  It records the authoritative account
    snapshot and the back-filled executions, and it hands intents back out; it
    never prices, never sizes and never mutates cash, positions, sellable
    quantity or cost.  An unfilled intent exists only as a live intent until its
    half session ends, and a filled intent is never re-issued.

    Lifecycle: :meth:`publish` installs a version, :meth:`record_fills` back-fills
    executions against it (a partially filled intent keeps its remainder live),
    :meth:`pending_intents` reports what is still live, :meth:`expire` closes the
    half session, and the next :meth:`publish` reports how the previous version's
    intents ended.
    """

    def __init__(self, policy: PlanPolicy | None = None) -> None:
        self._policy = policy or DEFAULT_POLICY
        self._active: RecommendationPlan | None = None
        self._account: AccountSnapshot | None = None
        self._fills: tuple[FillRecord, ...] = ()
        self._filled_quantity: dict[str, int] = {}

    @property
    def policy(self) -> PlanPolicy:
        return self._policy

    @property
    def active_plan(self) -> RecommendationPlan | None:
        return self._active

    @property
    def account_truth(self) -> AccountSnapshot | None:
        """The authoritative snapshot.  Suggestions never write into it."""

        return self._account

    @property
    def fills(self) -> tuple[FillRecord, ...]:
        """Executions recorded against the live version."""

        return self._fills

    def _check_fill(self, fill: FillRecord, *, account: AccountSnapshot) -> None:
        _require(
            isinstance(fill, FillRecord),
            Reason.INVALID_FIELD,
            f"fills must be FillRecord, got {type(fill).__name__}",
        )
        if fill.side is Side.BUY:
            _require(
                fill.quantity % self._policy.fees.lot_size == 0,
                Reason.INVALID_LOT,
                f"{fill.symbol}: buy fill {fill.quantity} is not a multiple of "
                f"{self._policy.fees.lot_size}",
                symbol=fill.symbol,
            )
        _require(
            fill.traded_at <= account.as_of,
            Reason.FILL_AFTER_ACCOUNT_SNAPSHOT,
            f"{fill.symbol}: fill traded_at={fill.traded_at.isoformat()} is after the "
            f"account snapshot as_of={account.as_of.isoformat()}",
            symbol=fill.symbol,
        )

    def record_fills(
        self,
        fills: Sequence[FillRecord],
        *,
        account: AccountSnapshot | None = None,
    ) -> tuple[FillRecord, ...]:
        """Back-fill executions of the live version.

        A fill without a matching live intent, a fill traded outside the live
        half session, or a fill beyond the recommended size is refused.  Only the
        quantity counters move: cash, positions, sellable quantity and cost stay
        exactly as the account snapshot reports them.
        """

        plan = self._active
        _require(
            plan is not None,
            Reason.FILL_WITHOUT_INTENT,
            "no version is live to match fills against",
        )
        assert plan is not None
        snapshot = account or self._account
        _require(
            snapshot is not None,
            Reason.INVALID_FIELD,
            "an account snapshot is required to check fills",
        )
        assert snapshot is not None
        recorded: list[FillRecord] = []
        for fill in fills:
            self._check_fill(fill, account=snapshot)
            intent = next(
                (
                    candidate
                    for candidate in plan.order_items
                    if candidate.symbol == fill.symbol and candidate.side is fill.side
                ),
                None,
            )
            _require(
                intent is not None,
                Reason.FILL_WITHOUT_INTENT,
                f"{fill.symbol}: no {fill.side.value} intent in version "
                f"{plan.recommendation_version!r}",
                symbol=fill.symbol,
            )
            assert intent is not None
            _require(
                plan.valid_from <= fill.traded_at <= plan.valid_until,
                Reason.FILL_WITHOUT_INTENT,
                f"{fill.symbol}: fill traded_at={fill.traded_at.isoformat()} is outside the "
                f"live window [{plan.valid_from.isoformat()}, {plan.valid_until.isoformat()}]",
                symbol=fill.symbol,
            )
            running = self._filled_quantity.get(fill.symbol, 0) + fill.quantity
            _require(
                running <= intent.recommended_quantity,
                Reason.FILL_EXCEEDS_INTENT,
                f"{fill.symbol}: recorded {running} against a recommended "
                f"{intent.recommended_quantity}",
                symbol=fill.symbol,
            )
            self._filled_quantity[fill.symbol] = running
            recorded.append(fill)
        self._fills = self._fills + tuple(recorded)
        return tuple(recorded)

    def publish(
        self,
        plan: RecommendationPlan,
        *,
        account: AccountSnapshot,
        fills: Sequence[FillRecord] = (),
    ) -> CoverageReport:
        """Publish ``plan`` as the live version over the current one.

        ``fills`` are back-filled executions of the *superseded* half session that
        have not been passed to :meth:`record_fills` yet; they are matched by
        symbol and side.  A fill with no matching intent, a fill traded after the
        account snapshot, or an over-sized fill is refused instead of being
        silently ignored.
        """

        _require(
            not plan.is_expired(account.as_of),
            Reason.PLAN_EXPIRED,
            f"plan valid_until={plan.valid_until.isoformat()} has already ended at "
            f"as_of={account.as_of.isoformat()}",
        )
        validate_plan(plan, account=account, policy=self._policy)

        previous = self._active
        all_fills = self._fills + tuple(fills)
        for fill in all_fills:
            self._check_fill(fill, account=account)
        if previous is None:
            _require(
                not all_fills,
                Reason.FILL_WITHOUT_INTENT,
                f"{len(all_fills)} fill(s) recorded while no version is live to match them",
            )
        outcomes: list[IntentOutcome] = []
        if previous is not None:
            _require(
                plan.recommendation_version != previous.recommendation_version,
                Reason.DUPLICATE_VERSION,
                f"recommendation_version {plan.recommendation_version!r} is already the "
                f"live version",
            )
            by_symbol: dict[str, int] = {}
            for fill in all_fills:
                intent = next(
                    (
                        item
                        for item in previous.order_items
                        if item.symbol == fill.symbol and item.side is fill.side
                    ),
                    None,
                )
                _require(
                    intent is not None,
                    Reason.FILL_WITHOUT_INTENT,
                    f"{fill.symbol}: no {fill.side.value} intent in version "
                    f"{previous.recommendation_version!r}",
                    symbol=fill.symbol,
                )
                assert intent is not None
                _require(
                    previous.valid_from <= fill.traded_at <= previous.valid_until,
                    Reason.FILL_WITHOUT_INTENT,
                    f"{fill.symbol}: fill traded_at={fill.traded_at.isoformat()} is outside "
                    f"the superseded window [{previous.valid_from.isoformat()}, "
                    f"{previous.valid_until.isoformat()}]",
                    symbol=fill.symbol,
                )
                by_symbol[fill.symbol] = by_symbol.get(fill.symbol, 0) + fill.quantity
            previous_expired = previous.is_expired(account.as_of)
            for item in previous.order_items:
                filled = by_symbol.get(item.symbol, 0)
                _require(
                    filled <= item.recommended_quantity,
                    Reason.FILL_EXCEEDS_INTENT,
                    f"{item.symbol}: filled {filled} exceeds the recommended "
                    f"{item.recommended_quantity}",
                    symbol=item.symbol,
                )
                position = account.position(item.symbol)
                account_quantity = 0 if position is None else position.quantity
                if filled == 0:
                    if previous_expired:
                        kind = IntentOutcomeKind.EXPIRED
                        note = "half session ended unfilled"
                    else:
                        kind = IntentOutcomeKind.CANCELLED
                        note = "superseded by the new version before filling"
                elif filled < item.recommended_quantity:
                    kind = IntentOutcomeKind.FILLED_PARTIAL
                    note = "partially filled; the remainder is not carried over"
                else:
                    kind = IntentOutcomeKind.FILLED
                    note = "filled; the position comes from the account snapshot"
                outcomes.append(
                    IntentOutcome(
                        symbol=item.symbol,
                        sleeve=item.sleeve,
                        previous_action=item.action,
                        kind=kind,
                        recommended_quantity=item.recommended_quantity,
                        filled_quantity=filled,
                        account_quantity=account_quantity,
                        note=note,
                    )
                )
            for outcome in outcomes:
                if not outcome.protected:
                    continue
                new_item = plan.item(outcome.symbol)
                _require(
                    new_item is not None,
                    Reason.FILLED_INTENT_NOT_ACKNOWLEDGED,
                    f"{outcome.symbol}: version {previous.recommendation_version!r} filled "
                    f"{outcome.filled_quantity} but the new version does not mention the "
                    f"symbol",
                    symbol=outcome.symbol,
                )
                assert new_item is not None
                _require(
                    new_item.previous_action is outcome.previous_action,
                    Reason.FILLED_INTENT_NOT_ACKNOWLEDGED,
                    f"{outcome.symbol}: the executed advice "
                    f"({outcome.previous_action.value}) must be carried as previous_action "
                    f"by the new version",
                    symbol=outcome.symbol,
                )
        report = CoverageReport(
            superseded_version=None if previous is None else previous.recommendation_version,
            superseded_valid_until=None if previous is None else previous.valid_until,
            new_version=plan.recommendation_version,
            outcomes=tuple(outcomes),
        )
        self._active = plan
        self._account = account
        self._fills = ()
        self._filled_quantity = {}
        return report

    def pending_intents(
        self, *, as_of: dt.datetime | None = None
    ) -> tuple[RecommendationItem, ...]:
        """Intents still live at ``as_of``: unfilled, inside the window.

        Suggestions are returned, never applied: nothing here can change cash,
        positions, sellable quantity or cost.
        """

        plan = self._active
        if plan is None:
            return ()
        if as_of is None:
            if self._account is None:
                return ()
            as_of = self._account.as_of
        if plan.is_expired(as_of):
            return ()
        pending = []
        for item in plan.order_items:
            if self._filled_quantity.get(item.symbol, 0) >= item.recommended_quantity:
                continue
            pending.append(item)
        return tuple(pending)

    def expire(self, as_of: dt.datetime) -> tuple[IntentOutcome, ...]:
        """Close the half session: unfilled intents die, the version retires."""

        plan = self._active
        if plan is None or not plan.is_expired(as_of):
            return ()
        account = self._account
        outcomes = []
        for item in self.pending_intents(as_of=plan.valid_from):
            position = None if account is None else account.position(item.symbol)
            outcomes.append(
                IntentOutcome(
                    symbol=item.symbol,
                    sleeve=item.sleeve,
                    previous_action=item.action,
                    kind=IntentOutcomeKind.EXPIRED,
                    recommended_quantity=item.recommended_quantity,
                    filled_quantity=self._filled_quantity.get(item.symbol, 0),
                    account_quantity=0 if position is None else position.quantity,
                    note="half session ended unfilled; re-issue only through a new version",
                )
            )
        self._active = None
        self._fills = ()
        self._filled_quantity = {}
        return tuple(outcomes)
