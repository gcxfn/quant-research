"""Strategy-plan assembly adapter: caller candidates + account overlay -> plan.

This module is the only place where the strategy layer's intents (attack
candidates, defense candidates, an :class:`~quant.portfolio.risk_overlay.OverlayDecision`)
are turned into a *validated* :class:`~quant.portfolio.recommendations.RecommendationPlan`.
It adds no strategy of its own: it sizes, arms, degrades and drops, and then hands
the result to :func:`quant.portfolio.recommendations.build_plan`, which stays the
single validation authority (header identity, coverage, limits, cash).

Non-goals (AGENTS.md 1 / 4): no broker connection, no order transmission, no fill
matching, no historical backtest, no new factors, no new stop / account-level
thresholds.  Synthetic fixtures only; nothing here is profitability evidence.

Load-bearing rulings
--------------------
1. **The account-level overlay scales the attack sleeve only** (prereg
   ``exp-20260920-account-risk-overlay-prereg`` 1: "只改变账户级进攻暴露系数
   ``E_t``。基础进攻目标权重乘以 ``E_t``").  ``attack_target = base_target_weight *
   overlay.exposure_multiplier``; every defense ``target_weight`` passes through
   untouched.  The prereg's 剩余资金 stays in the defense layer or cash by shrinking
   the attack target, not by writing extra defense items here.
2. **The entry gate is sleeve-scoped.**  An attack buy (new or add) needs
   ``attack_entry_allowed(risk_state)`` **and** ``account_action is not
   ACCOUNT_DELEVER``; a defense buy only needs the overlay state not to be
   ``INSUFFICIENT_DATA``.  Two reasons: ``build_plan`` refuses *every* attack buy
   item when ``risk_state is RISK_OFF`` or ``account_action is ACCOUNT_DELEVER``
   (so a partially built attack name whose scaled target still exceeds its carried
   weight must not be re-added), and AGENTS.md 6 requires "停止新增建议" during a
   data gap.  ``BLOCK_NEW_ATTACK`` (reachable only through an off-prereg
   ``hard_stop_drawdown``) blocks new attack exposure by name, so the defense base
   sleeve stays available there - suppressing it would contaminate a
   hard-stop arm against the registered C0-C2 comparison.
3. **The plan-level ``account_action`` is the registered account action.**  A
   ``reduce_attack`` / ``restore_attack`` / ``hold`` row maps to ``NO_ACTION``:
   writing ``ACCOUNT_DELEVER`` there would make ``build_plan`` reject the very
   retarget the overlay asked for.  The 账户级降仓 information is carried by the
   scaled attack items, ``risk_state`` and the note, never by that field.
4. **Sizing is achieved-target, not requested-target.**  Quantities come from the
   account mark (``position.last_price``) for held symbols and from the candidate's
   ``reference_price`` for new entries, rounded down to whole lots; the emitted
   ``target_weight`` is the weight actually achieved by those whole lots.
5. **Bands and exit class come from the candidate, never from this module.**  A
   fixed width here would mint executable prices from an unregistered parameter;
   p3-band-contract 1.1 (buy limit = signal-day close, sell limit = re-anchored
   daily to the latest close) and 10.1 (sigma0 ladder) own those numbers.  Order
   lifecycles (``risk`` -> K=3 open-market fallback, ``profit`` -> silent expiry)
   follow from the item's action, so the action class is never re-derived from the
   exposure multiplier (``level_on`` is 0.90, i.e. below 1.0 for every config).
6. **Over-cap buys are voided whole, never trimmed** (p3-band-contract 7.7 M2:
   "越限整单作废并计数披露 ... 引擎不做上限裁剪式部分成交").  A new entry whose
   ``base x E_t`` target exceeds ``policy.symbol_weight_limit`` is dropped and
   counted; an add is degraded to a passive carry at the carried weight and
   counted.  Existing holdings that drifted over the cap by price movement are
   disclosure-only: this module never force-reduces them (a caller that wants the
   rescale must send an explicit sell candidate).
7. **One item per symbol, coverage is fail-closed.**  ``validate_plan`` requires an
   explicit item for every held symbol, so a held symbol with no candidate gets a
   carried item here.  The caller's ``action`` is validated against its own **base**
   target, and a candidate whose base target equals the carried weight is
   authoritative: it carries at the carried weight (a passive item's target *is* the
   carried weight, and a caller that restates every holding at its current weight
   must not be drained by ``E_t`` once per decision point).  When the base target
   does differ, the emitted order follows the **post-overlay** target ``base x E_t``:
   an :class:`~quant.portfolio.risk_overlay.OverlayDecision` cannot carry a multiplier
   above 1, so scaling moves a target *down* only, and a buy-labelled name pulled
   below its carried weight is emitted as ``account_delever`` (the registered
   account-level de-lever) rather than raising ``candidate_action_mismatch`` and
   costing the whole half session.  A sell label with a base target *above* the
   carried weight, or a passive label with a base target *away* from it, contradicts
   the candidate's own frame and is rejected.  A held *attack* symbol carried
   without a base target cannot absorb ``E_t``; that gap is emitted at the carried
   weight plus the machine-parseable token ``unscaled_attack_holding=<symbol>``
   (visible through ``plan.note`` / ``render_lines``), never silently.
   ``carried_stops`` is the only way to arm it: this module owns no stop level, so
   without such an entry the carry can only be ``no_action`` (``_validate_item``
   exempts ``no_action`` from the stop requirement, so nothing else would catch the
   missing zone).
8. **Missing stops are split, not blanket** (AGENTS.md 1 requires a stop for every
   attack candidate).  A held attack symbol whose candidate requests an order but
   omits ``stop_price`` is a strategy-layer defect -> ``missing_stop``; a held
   symbol with no candidate at all is a legal carry -> ``no_action``, or ``hold``
   with a ``carried_stops`` entry (no stop is required for a passive item).
   Otherwise AGENTS.md 6 ("只输出风险提示和需要补录的数据") could not be emitted at
   all while the coverage gate forces an item per holding.
9. **Cash mirrors** :func:`~quant.portfolio.recommendations.exposure_of` exactly:
   ``quantity * price_upper + estimate_fees(BUY, ..., trade_date=valid_from.date(),
   schedule=policy.fees)`` against ``account.cash``.  Using a different fee schedule
   or trade date would make the admission loop disagree with the validator and turn
   a "drop the order" case into a raised ``insufficient_cash``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import math
import re
from collections.abc import Mapping

from quant.portfolio import recommendations as rec
from quant.portfolio import risk_overlay as ro

__all__ = [
    "AttackCandidate",
    "DefenseCandidate",
    "StrategyPlanError",
    "StrategyPlanReason",
    "assemble_plan",
    "parse_notes",
]


# --------------------------------------------------------------------------- #
# note tokens (machine-readable disclosure of what this module dropped)
# --------------------------------------------------------------------------- #
NOTE_SEPARATOR = " | "
_NOTE_CODE = re.compile(r"^[a-z][a-z0-9_]*$")

ENTRY_BLOCKED = "entry_blocked"
"""Buy suppressed because the account-level entry gate was closed."""

WEIGHT_CAP_VOIDED = "weight_cap_voided"
"""Order voided whole because its target weight would pass the symbol cap (M2)."""

NEW_ENTRY_CAP_VOIDED = "new_entry_cap_voided"
"""New entry dropped because ``policy.max_new_entries`` was already used up."""

CASH_EXHAUSTED = "cash_exhausted"
"""Buy dropped because cash (fee-inclusive) did not cover it."""

SUB_LOT_SKIPPED = "sub_lot_skipped"
"""Candidate dropped because the scaled target rounds to zero whole lots."""

ORDER_NOT_REACHABLE = "order_not_reachable"
"""Buy/sell intent with no target to reach: its base target already equals the
carried weight, or the scaled target lands exactly there."""

UNSCALED_ATTACK_HOLDING = "unscaled_attack_holding"
"""Held attack symbol carried without a base target, so E_t never reached it."""


def parse_notes(note: str) -> dict[str, tuple[str, ...]]:
    """Machine-readable view of a plan note.

    Only ``snake_case_code=value[,value]`` segments are collected, so the Chinese
    display text in the same note is ignored.  Values keep their order.
    """

    tokens: dict[str, list[str]] = {}
    for segment in str(note).split(NOTE_SEPARATOR):
        key, sep, value = segment.partition("=")
        key = key.strip()
        if not sep or not _NOTE_CODE.match(key):
            continue
        bucket = tokens.setdefault(key, [])
        for item in value.split(","):
            item = item.strip()
            if item:
                bucket.append(item)
    return {key: tuple(values) for key, values in tokens.items()}


def _format_note(display: str, dropped: dict[str, list[str]]) -> str:
    segments = [display]
    for key, symbols in dropped.items():
        if symbols:
            segments.append(f"{key}={','.join(symbols)}")
    return NOTE_SEPARATOR.join(segments)


def _drop(dropped: dict[str, list[str]], token: str, symbol: str) -> None:
    bucket = dropped.setdefault(token, [])
    if symbol not in bucket:
        bucket.append(symbol)


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
class StrategyPlanReason(str, enum.Enum):
    """Fail-closed reasons raised by this module (never defaulted, never repaired)."""

    OVERLAY_MARKET_MISMATCH = "overlay_market_mismatch"
    DECISION_TIME_MISMATCH = "decision_time_mismatch"
    INVALID_CANDIDATE = "invalid_candidate"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    SLEEVE_MISMATCH = "sleeve_mismatch"
    CANDIDATE_ACTION_MISMATCH = "candidate_action_mismatch"
    MISSING_TRIGGER_REASON = "missing_trigger_reason"
    MISSING_INVALIDATION_REASON = "missing_invalidation_reason"
    MISSING_REFERENCE_PRICE = "missing_reference_price"
    MISSING_PRICE_BAND = "missing_price_band"
    MISSING_STOP = "missing_stop"
    INVALID_STOP = "invalid_stop"
    STOP_ALREADY_BREACHED = "stop_already_breached"


class StrategyPlanError(ValueError):
    """Raised instead of guessing: an unassemblable version must not be emitted."""

    def __init__(
        self,
        reason: StrategyPlanReason,
        detail: str,
        symbol: str | None = None,
    ) -> None:
        self.reason = StrategyPlanReason(reason)
        self.detail = detail
        self.symbol = symbol
        super().__init__(f"{self.reason.value}: {detail}")

    def to_mapping(self) -> dict[str, str | None]:
        return {
            "reason": self.reason.value,
            "detail": self.detail,
            "symbol": self.symbol,
        }


def _require(
    condition: bool,
    reason: StrategyPlanReason,
    detail: str,
    symbol: str | None = None,
) -> None:
    if not condition:
        raise StrategyPlanError(reason, detail, symbol=symbol)


# --------------------------------------------------------------------------- #
# strategy-layer inputs
# --------------------------------------------------------------------------- #
@dataclasses.dataclass(frozen=True)
class AttackCandidate:
    """One attack-sleeve intent from the strategy layer.

    ``base_target_weight`` is the *pre-overlay* target: the assembler multiplies it
    by ``OverlayDecision.exposure_multiplier`` (prereg 1).  ``reference_price`` is
    the price the target weight is measured at for a new entry (p3-band-contract
    1.1: the signal-day close, used as the buy limit, is not re-anchored); for a
    held symbol the account mark is used instead.  ``price_lower`` / ``price_upper``
    are the candidate's own executable band and are never derived here.
    """

    symbol: str
    name: str
    base_target_weight: float
    trigger_reason: str
    invalidation_reason: str = ""
    stop_price: float | None = None
    reference_price: float | None = None
    price_lower: float | None = None
    price_upper: float | None = None
    action: rec.Action = rec.Action.NEW
    previous_action: rec.Action | None = None
    change_reason: str = ""


@dataclasses.dataclass(frozen=True)
class DefenseCandidate:
    """One defense-sleeve intent.  ``target_weight`` is never scaled by ``E_t``.

    Defense exits (AGENTS.md 1: "防御资产也必须有趋势、回撤或状态切换形式的风险退出
    条件") are carried by the action plus ``invalidation_reason``: a defense item
    needs no ``stop_price`` / ``risk_r``, and offering one is rejected rather than
    ignored.
    """

    symbol: str
    name: str
    target_weight: float
    trigger_reason: str
    invalidation_reason: str = ""
    reference_price: float | None = None
    price_lower: float | None = None
    price_upper: float | None = None
    action: rec.Action = rec.Action.NEW
    previous_action: rec.Action | None = None
    change_reason: str = ""


@dataclasses.dataclass(frozen=True)
class _Intent:
    """Sleeve-agnostic view of a candidate (one emit path for both sleeves)."""

    symbol: str
    name: str
    sleeve: rec.Sleeve
    action: rec.Action
    base_target_weight: float
    trigger_reason: str
    invalidation_reason: str
    stop_price: float | None
    reference_price: float | None
    price_lower: float | None
    price_upper: float | None
    previous_action: rec.Action | None
    change_reason: str


def _as_action(value: object, *, symbol: str, field: str) -> rec.Action:
    if isinstance(value, rec.Action):
        return value
    try:
        return rec.Action(value)  # type: ignore[arg-type]
    except ValueError as exc:
        raise StrategyPlanError(
            StrategyPlanReason.INVALID_CANDIDATE,
            f"{symbol}: {field}={value!r} is not a registered action",
            symbol=symbol,
        ) from exc


def _as_weight(value: object, *, symbol: str, field: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise StrategyPlanError(
            StrategyPlanReason.INVALID_CANDIDATE,
            f"{symbol}: {field}={value!r} is not a number",
            symbol=symbol,
        ) from exc
    _require(
        math.isfinite(number) and 0.0 <= number <= 1.0,
        StrategyPlanReason.INVALID_CANDIDATE,
        f"{symbol}: {field}={number!r} must be in [0, 1]",
        symbol=symbol,
    )
    return number


def _as_price(value: object, *, symbol: str, field: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise StrategyPlanError(
            StrategyPlanReason.INVALID_CANDIDATE,
            f"{symbol}: {field}={value!r} is not a number",
            symbol=symbol,
        ) from exc
    _require(
        math.isfinite(number) and number > 0.0,
        StrategyPlanReason.INVALID_CANDIDATE,
        f"{symbol}: {field}={number!r} must be > 0",
        symbol=symbol,
    )
    return number


def _check_common(
    *,
    symbol: object,
    name: object,
    action: rec.Action,
    trigger_reason: object,
    invalidation_reason: object,
    price_lower: object,
    price_upper: object,
    previous_action: object,
) -> None:
    _require(
        bool(str(symbol).strip()),
        StrategyPlanReason.INVALID_CANDIDATE,
        "candidate has no symbol",
    )
    label = str(symbol)
    _require(
        bool(str(name).strip()),
        StrategyPlanReason.INVALID_CANDIDATE,
        f"{label}: candidate has no name (the output contract requires a non-empty name)",
        symbol=label,
    )
    _require(
        bool(str(trigger_reason).strip()),
        StrategyPlanReason.MISSING_TRIGGER_REASON,
        f"{label}: every item needs a trigger condition",
        symbol=label,
    )
    if action in rec.ORDER_ACTIONS:
        _require(
            bool(str(invalidation_reason).strip()),
            StrategyPlanReason.MISSING_INVALIDATION_REASON,
            f"{label}: order action {action.value} needs an invalidation condition",
            symbol=label,
        )
    banded = price_lower is not None or price_upper is not None
    _require(
        (price_lower is None) == (price_upper is None),
        StrategyPlanReason.INVALID_CANDIDATE,
        f"{label}: price_lower and price_upper must be given together",
        symbol=label,
    )
    if banded:
        lower = _as_price(price_lower, symbol=label, field="price_lower")
        upper = _as_price(price_upper, symbol=label, field="price_upper")
        _require(
            lower <= upper,
            StrategyPlanReason.INVALID_CANDIDATE,
            f"{label}: price_lower={lower} is above price_upper={upper}",
            symbol=label,
        )
    if action is rec.Action.NEW:
        _require(
            previous_action is None,
            StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
            f"{label}: a new entry has no previous action (got {previous_action!r})",
            symbol=label,
        )


def _intent_from_attack(candidate: AttackCandidate) -> _Intent:
    action = _as_action(candidate.action, symbol=str(candidate.symbol), field="action")
    _check_common(
        symbol=candidate.symbol,
        name=candidate.name,
        action=action,
        trigger_reason=candidate.trigger_reason,
        invalidation_reason=candidate.invalidation_reason,
        price_lower=candidate.price_lower,
        price_upper=candidate.price_upper,
        previous_action=candidate.previous_action,
    )
    label = str(candidate.symbol)
    stop = candidate.stop_price
    if stop is not None:
        stop = _as_price(stop, symbol=label, field="stop_price")
    reference = candidate.reference_price
    if reference is not None:
        reference = _as_price(reference, symbol=label, field="reference_price")
    previous = (
        None
        if candidate.previous_action is None
        else _as_action(candidate.previous_action, symbol=label, field="previous_action")
    )
    return _Intent(
        symbol=label,
        name=str(candidate.name),
        sleeve=rec.Sleeve.ATTACK,
        action=action,
        base_target_weight=_as_weight(
            candidate.base_target_weight, symbol=label, field="base_target_weight"
        ),
        trigger_reason=str(candidate.trigger_reason),
        invalidation_reason=str(candidate.invalidation_reason or ""),
        stop_price=stop,
        reference_price=reference,
        price_lower=candidate.price_lower,
        price_upper=candidate.price_upper,
        previous_action=previous,
        change_reason=str(candidate.change_reason or ""),
    )


def _intent_from_defense(candidate: DefenseCandidate) -> _Intent:
    action = _as_action(candidate.action, symbol=str(candidate.symbol), field="action")
    label = str(candidate.symbol)
    _require(
        action is not rec.Action.ACCOUNT_DELEVER,
        StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
        f"{label}: account_delever is an attack-sleeve action",
        symbol=label,
    )
    _check_common(
        symbol=candidate.symbol,
        name=candidate.name,
        action=action,
        trigger_reason=candidate.trigger_reason,
        invalidation_reason=candidate.invalidation_reason,
        price_lower=candidate.price_lower,
        price_upper=candidate.price_upper,
        previous_action=candidate.previous_action,
    )
    reference = candidate.reference_price
    if reference is not None:
        reference = _as_price(reference, symbol=label, field="reference_price")
    previous = (
        None
        if candidate.previous_action is None
        else _as_action(candidate.previous_action, symbol=label, field="previous_action")
    )
    return _Intent(
        symbol=label,
        name=str(candidate.name),
        sleeve=rec.Sleeve.DEFENSE,
        action=action,
        base_target_weight=_as_weight(
            candidate.target_weight, symbol=label, field="target_weight"
        ),
        trigger_reason=str(candidate.trigger_reason),
        invalidation_reason=str(candidate.invalidation_reason or ""),
        stop_price=None,
        reference_price=reference,
        price_lower=candidate.price_lower,
        price_upper=candidate.price_upper,
        previous_action=previous,
        change_reason=str(candidate.change_reason or ""),
    )


# --------------------------------------------------------------------------- #
# sizing helpers
# --------------------------------------------------------------------------- #
def _carried_stops(
    values: Mapping[str, float] | None,
    *,
    account: rec.AccountSnapshot,
    covered: Mapping[str, rec.Sleeve],
) -> dict[str, float]:
    """Validated stop book for held attack symbols this version has no candidate for.

    The strategy layer owns every registered stop and moving protection line, so a
    carry can only be armed from here: this module never invents a level, and a
    symbol without one is carried as ``no_action`` (see the module docstring).
    """

    if values is None:
        return {}
    stops: dict[str, float] = {}
    for raw_symbol, raw_stop in values.items():
        symbol = str(raw_symbol)
        position = account.position(symbol)
        _require(
            position is not None,
            StrategyPlanReason.INVALID_CANDIDATE,
            f"{symbol}: carried_stops only arms symbols the account holds",
            symbol=symbol,
        )
        _require(
            position.sleeve is rec.Sleeve.ATTACK,
            StrategyPlanReason.INVALID_CANDIDATE,
            f"{symbol}: a defense holding has no price stop in this layer (its exit is "
            "the action plus invalidation_reason)",
            symbol=symbol,
        )
        _require(
            symbol not in covered,
            StrategyPlanReason.DUPLICATE_CANDIDATE,
            f"{symbol}: carried_stops duplicates this symbol's candidate; put the stop "
            "on the candidate instead",
            symbol=symbol,
        )
        stops[symbol] = _as_price(raw_stop, symbol=symbol, field="carried_stops")
    return stops


def _lot_floor(notional: float, price: float, lot: int) -> int:
    """Largest whole-lot quantity whose notional at ``price`` fits ``notional``.

    The ``1e-9`` share tolerance absorbs float noise on exact lot boundaries; it can
    never add a lot, because it is far smaller than one share.
    """

    if price <= 0.0 or lot <= 0:
        return 0
    return int(math.floor((notional / price + 1e-9) / lot)) * lot


def _achieved_weight(quantity: int, price: float, equity: float) -> float:
    return (quantity * price) / equity


def _buy_cost(
    *,
    sleeve: rec.Sleeve,
    quantity: int,
    price_upper: float,
    trade_date: dt.date,
    schedule: rec.FeeSchedule,
) -> float:
    """Fee-inclusive cost of one buy, identical to ``exposure_of``'s accounting."""

    return quantity * price_upper + rec.estimate_fees(
        rec.Side.BUY,
        quantity,
        price_upper,
        sleeve=sleeve,
        trade_date=trade_date,
        schedule=schedule,
    )


def _require_band(intent: _Intent) -> None:
    _require(
        intent.price_lower is not None and intent.price_upper is not None,
        StrategyPlanReason.MISSING_PRICE_BAND,
        f"{intent.symbol}: order action {intent.action.value} needs an executable band "
        "(the strategy layer owns the registered limit prices)",
        symbol=intent.symbol,
    )


def _attack_buy_stop(intent: _Intent, *, entry_price: float) -> float:
    """Registered stop of an attack buy, rejected rather than repaired when absent."""

    _require(
        intent.stop_price is not None,
        StrategyPlanReason.MISSING_STOP,
        f"{intent.symbol}: an attack order needs a stop price (AGENTS.md 1)",
        symbol=intent.symbol,
    )
    stop = float(intent.stop_price)  # type: ignore[arg-type]
    _require(
        0.0 < stop < entry_price,
        StrategyPlanReason.INVALID_STOP,
        f"{intent.symbol}: stop_price={stop} must sit below the entry price {entry_price}",
        symbol=intent.symbol,
    )
    _require(
        stop < float(intent.price_lower),  # type: ignore[arg-type]
        StrategyPlanReason.INVALID_STOP,
        f"{intent.symbol}: stop_price={stop} must sit below the buy band lower bound "
        f"{intent.price_lower}",
        symbol=intent.symbol,
    )
    return stop


def _held_stop(symbol: str, stop: object, position: rec.Position) -> float:
    """Registered stop for an already-held attack symbol, anchored on the mark.

    ``risk_amount`` needs ``0 < stop < anchor``; the anchor is the account mark, so
    a stop at or above the mark means the line is already breached and no positive
    R exists for this version.
    """

    _require(
        stop is not None,
        StrategyPlanReason.MISSING_STOP,
        f"{symbol}: a held attack name needs a stop price for its armed item "
        "(AGENTS.md 1)",
        symbol=symbol,
    )
    value = _as_price(stop, symbol=symbol, field="stop_price")
    _require(
        value < position.last_price,
        StrategyPlanReason.STOP_ALREADY_BREACHED,
        f"{symbol}: stop_price={value} is at or above the mark "
        f"{position.last_price}; exit the position instead of arming a new version",
        symbol=symbol,
    )
    return value


# --------------------------------------------------------------------------- #
# item emission
# --------------------------------------------------------------------------- #
def _item(
    intent: _Intent,
    *,
    action: rec.Action,
    current_quantity: int,
    recommended_quantity: int,
    target_weight: float,
    valid_until: dt.datetime,
    change_reason: str,
    price_lower: float | None = None,
    price_upper: float | None = None,
    stop_price: float | None = None,
    risk_r: float | None = None,
) -> rec.RecommendationItem:
    return rec.RecommendationItem(
        symbol=intent.symbol,
        name=intent.name,
        sleeve=intent.sleeve,
        action=action,
        current_quantity=current_quantity,
        recommended_quantity=recommended_quantity,
        target_weight=target_weight,
        valid_until=valid_until,
        trigger_reason=intent.trigger_reason,
        invalidation_reason=intent.invalidation_reason,
        price_lower=price_lower,
        price_upper=price_upper,
        risk_r=risk_r,
        stop_price=stop_price,
        previous_action=intent.previous_action,
        change_reason=change_reason,
    )


def _default_change_reason(
    intent: _Intent, *, action: rec.Action, target_weight: float, multiplier: float
) -> str:
    label = rec.ACTION_LABELS[action]
    if intent.sleeve is rec.Sleeve.ATTACK and multiplier != 1.0:
        base = f"基础目标 {intent.base_target_weight:.2%} × 账户系数 {multiplier:.2f}"
        return f"{label}：{base} -> 目标仓位 {target_weight:.2%}"
    return f"{label}：目标仓位 {target_weight:.2%}"


def _passive_action(intent: _Intent, stop: object) -> rec.Action:
    """Passive item for a carried symbol: 持有 needs a stop, 不动 does not.

    AGENTS.md 1 requires a stop zone for every attack line, so an attack carry
    without a stop source can only be ``no_action`` (``_validate_item`` exempts it
    from the stop requirement); a defense carry never needs one, and the caller's
    own ``hold`` label is honoured.
    """

    if intent.sleeve is rec.Sleeve.ATTACK:
        return rec.Action.HOLD if stop is not None else rec.Action.NO_ACTION
    return (
        intent.action if intent.action in rec.PASSIVE_ACTIONS else rec.Action.NO_ACTION
    )


def _passive(
    intent: _Intent,
    position: rec.Position,
    *,
    stop: object,
    equity: float,
    valid_until: dt.datetime,
    trade_date: dt.date,
    policy: rec.PlanPolicy,
    change_reason: str,
    keep_band: bool = True,
) -> rec.RecommendationItem:
    """Carried item at the current weight; no quantity is ordered."""

    action = _passive_action(intent, stop)
    stop_price: float | None = None
    risk: float | None = None
    if action is rec.Action.HOLD and intent.sleeve is rec.Sleeve.ATTACK:
        stop_price = _held_stop(intent.symbol, stop, position)
        risk = rec.risk_amount(
            position.quantity,
            position.last_price,
            stop_price,
            sleeve=intent.sleeve,
            trade_date=trade_date,
            schedule=policy.fees,
        )
    banded = keep_band and intent.price_lower is not None and intent.price_upper is not None
    return _item(
        intent,
        action=action,
        current_quantity=position.quantity,
        recommended_quantity=0,
        target_weight=position.weight(equity),
        valid_until=valid_until,
        change_reason=change_reason,
        price_lower=intent.price_lower if banded else None,
        price_upper=intent.price_upper if banded else None,
        stop_price=stop_price,
        risk_r=risk,
    )


def _carried_intent(position: rec.Position) -> _Intent:
    """Synthetic intent for a held symbol this version has no candidate for."""

    return _Intent(
        symbol=position.symbol,
        name=position.name,
        sleeve=position.sleeve,
        action=rec.Action.NO_ACTION,
        base_target_weight=0.0,
        trigger_reason="账户持仓维持：本版无对应候选/信号",
        invalidation_reason="",
        stop_price=None,
        reference_price=None,
        price_lower=None,
        price_upper=None,
        previous_action=None,
        change_reason="",
    )


def _emit_intent(
    intent: _Intent,
    *,
    account: rec.AccountSnapshot,
    overlay: ro.OverlayDecision,
    policy: rec.PlanPolicy,
    attack_open: bool,
    data_gap: bool,
    admit_buy,
    dropped: dict[str, list[str]],
    valid_until: dt.datetime,
    trade_date: dt.date,
) -> rec.RecommendationItem | None:
    """One candidate -> at most one item, or a recorded drop.

    The emitted order follows the **post-overlay** target ``base_target_weight x
    E_t``; the caller's ``action`` is validated against its own *base* target
    instead, because ``E_t <= 1`` (an :class:`~quant.portfolio.risk_overlay.OverlayDecision`
    cannot carry a multiplier above 1) means scaling can move a target down across
    the carried weight but never up.  A candidate whose base target already equals
    the carried weight carries unchanged, whatever its label; a buy-labelled name
    pulled *below* the carried weight is the normal de-lever case and is emitted as
    ``account_delever``, while a sell label with a base target above the carried
    weight, or a passive label with a base target away from it, contradicts the
    caller's own frame and is rejected.

    Buys are admitted through ``admit_buy`` (cash and the new-entry cap) and gated
    per sleeve: an attack buy needs ``attack_open``, a defense buy only needs the
    data gap to be closed.  A refused buy is dropped for a new entry and degraded
    to a passive carry for a held one, so the coverage gate is never traded away.
    """

    symbol = intent.symbol
    equity = account.equity
    tol = policy.weight_tolerance
    lot = policy.fees.lot_size
    position = account.position(symbol)
    if position is not None and position.sleeve is not intent.sleeve:
        raise StrategyPlanError(
            StrategyPlanReason.SLEEVE_MISMATCH,
            f"{symbol}: candidate is {intent.sleeve.value} but the account holds it as "
            f"{position.sleeve.value}",
            symbol=symbol,
        )

    multiplier = (
        overlay.exposure_multiplier if intent.sleeve is rec.Sleeve.ATTACK else 1.0
    )
    target = intent.base_target_weight * multiplier
    current_weight = 0.0 if position is None else position.weight(equity)
    buy_open = attack_open if intent.sleeve is rec.Sleeve.ATTACK else not data_gap
    # display text for the cause that closed the gate, used by the degrade records
    gate_reason = (
        f"账户级新增进攻暂停（风险状态 {ro.STATE_LABELS[overlay.risk_state]}）："
        "买单意图作废，维持现有仓位"
        if intent.sleeve is rec.Sleeve.ATTACK
        else "行情/基准数据不足（失败关闭）：本版停止新增暴露，维持现有仓位"
    )

    def degrade(change_reason: str, *, stop: object) -> rec.RecommendationItem:
        """Held symbol whose order was cancelled: carry it, never lose coverage."""

        return _passive(
            intent,
            position,
            stop=stop,
            equity=equity,
            valid_until=valid_until,
            trade_date=trade_date,
            policy=policy,
            change_reason=change_reason,
        )

    # ---------------------------------------------------------------- new entry
    if position is None:
        if intent.action is not rec.Action.NEW:
            raise StrategyPlanError(
                StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
                f"{symbol}: the account does not hold this symbol, so the only legal "
                f"action is new (got {intent.action.value})",
                symbol=symbol,
            )
        if target <= tol:
            _drop(dropped, SUB_LOT_SKIPPED, symbol)
            return None
        if not buy_open:
            _drop(dropped, ENTRY_BLOCKED, symbol)
            return None
        if target > policy.symbol_weight_limit + tol:
            _drop(dropped, WEIGHT_CAP_VOIDED, symbol)
            return None
        price = intent.reference_price
        if price is None:
            raise StrategyPlanError(
                StrategyPlanReason.MISSING_REFERENCE_PRICE,
                f"{symbol}: a new entry needs reference_price to size the order",
                symbol=symbol,
            )
        _require_band(intent)
        quantity = _lot_floor(target * equity, float(price), lot)
        achieved = _achieved_weight(quantity, float(price), equity)
        if quantity <= 0 or achieved <= current_weight + tol:
            _drop(dropped, SUB_LOT_SKIPPED, symbol)
            return None
        if not admit_buy(
            sleeve=intent.sleeve,
            quantity=quantity,
            price_upper=float(intent.price_upper),  # type: ignore[arg-type]
            is_new=True,
            symbol=symbol,
        ):
            return None
        stop: float | None = None
        risk: float | None = None
        if intent.sleeve is rec.Sleeve.ATTACK:
            stop = _attack_buy_stop(intent, entry_price=float(price))
            risk = rec.risk_amount(
                quantity,
                float(price),
                stop,
                sleeve=intent.sleeve,
                trade_date=trade_date,
                schedule=policy.fees,
            )
        return _item(
            intent,
            action=rec.Action.NEW,
            current_quantity=0,
            recommended_quantity=quantity,
            target_weight=achieved,
            valid_until=valid_until,
            change_reason=intent.change_reason
            or _default_change_reason(
                intent,
                action=rec.Action.NEW,
                target_weight=achieved,
                multiplier=multiplier,
            ),
            price_lower=intent.price_lower,
            price_upper=intent.price_upper,
            stop_price=stop,
            risk_r=risk,
        )

    # ------------------------------------------------------------------- carried
    if intent.action is rec.Action.NEW:
        raise StrategyPlanError(
            StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
            f"{symbol}: the account already holds this symbol, so a new-entry action is "
            "illegal (the output contract separates new from add)",
            symbol=symbol,
        )
    # the caller's own frame: what its base target asks for, before any scaling
    base_gap = intent.base_target_weight - current_weight
    if base_gap > tol and intent.action not in rec.BUY_ACTIONS:
        raise StrategyPlanError(
            StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
            f"{symbol}: base target {intent.base_target_weight:.6f} is above the carried "
            f"weight {current_weight:.6f} but the candidate asks for "
            f"{intent.action.value}; scaling can only lower a target, so this cannot be "
            "explained by the account-level multiplier",
            symbol=symbol,
        )
    if base_gap < -tol and intent.action not in rec.SELL_ACTIONS:
        raise StrategyPlanError(
            StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
            f"{symbol}: base target {intent.base_target_weight:.6f} is below the carried "
            f"weight {current_weight:.6f} but the candidate asks for "
            f"{intent.action.value}; an order is required by the candidate's own target",
            symbol=symbol,
        )
    if abs(base_gap) <= tol:
        # The candidate states no change, and that is authoritative: a passive item's
        # target *is* the carried weight, and a labelled order has nothing to do.  A
        # caller that restates base == carried for its holdings must not be trimmed by
        # E_t at every decision point (that would drain the sleeve geometrically under
        # a constant multiplier); the de-lever bites on restated targets that differ.
        if intent.action in rec.ORDER_ACTIONS:
            _drop(dropped, ORDER_NOT_REACHABLE, symbol)
        if intent.change_reason:
            reason = intent.change_reason
        elif intent.action in rec.ORDER_ACTIONS:
            reason = (
                f"目标仓位与现有仓位一致（基础目标 {intent.base_target_weight:.2%}），"
                f"{rec.ACTION_LABELS[intent.action]}意图不产生订单"
            )
        else:
            reason = f"维持现有仓位 {current_weight:.2%}（候选未给出变化）"
        return degrade(reason, stop=intent.stop_price)

    # ------------------------------------------------------------------- the order
    # From here the candidate's own target asks for a change, so the post-overlay
    # target decides the emitted order.  E_t <= 1 means scaling can move a target
    # down across the carried weight, never up.
    if target > current_weight + tol:
        _require(
            intent.action in rec.BUY_ACTIONS,
            StrategyPlanReason.CANDIDATE_ACTION_MISMATCH,
            f"{symbol}: scaled target {target:.6f} is above the carried weight "
            f"{current_weight:.6f} but the candidate asks for {intent.action.value}",
            symbol=symbol,
        )
        if not buy_open or target > policy.symbol_weight_limit + tol:
            token = ENTRY_BLOCKED if not buy_open else WEIGHT_CAP_VOIDED
            _drop(dropped, token, symbol)
            return degrade(
                gate_reason
                if not buy_open
                else f"目标仓位 {target:.2%} 超过单标的上限 "
                f"{policy.symbol_weight_limit:.0%}，整单作废，维持现有仓位",
                stop=intent.stop_price,
            )
        price = position.last_price
        desired = _lot_floor(target * equity, price, lot)
        quantity = _lot_floor(max(desired - position.quantity, 0), 1.0, lot)
        achieved = _achieved_weight(position.quantity + quantity, price, equity)
        if quantity <= 0 or achieved <= current_weight + tol:
            _drop(dropped, SUB_LOT_SKIPPED, symbol)
            return degrade(
                "缩放后不足一个整手，买单意图作废，维持现有仓位",
                stop=intent.stop_price,
            )
        _require_band(intent)
        if not admit_buy(
            sleeve=intent.sleeve,
            quantity=quantity,
            price_upper=float(intent.price_upper),  # type: ignore[arg-type]
            is_new=False,
            symbol=symbol,
        ):
            return degrade(
                "现金不足（含费用），买单意图作废，维持现有仓位",
                stop=intent.stop_price,
            )
        stop = None
        risk = None
        if intent.sleeve is rec.Sleeve.ATTACK:
            stop = _attack_buy_stop(intent, entry_price=price)
            risk = rec.risk_amount(
                position.quantity,
                price,
                stop,
                sleeve=intent.sleeve,
                trade_date=trade_date,
                schedule=policy.fees,
            )
        return _item(
            intent,
            action=intent.action,
            current_quantity=position.quantity,
            recommended_quantity=quantity,
            target_weight=achieved,
            valid_until=valid_until,
            change_reason=intent.change_reason
            or _default_change_reason(
                intent,
                action=intent.action,
                target_weight=achieved,
                multiplier=multiplier,
            ),
            price_lower=intent.price_lower,
            price_upper=intent.price_upper,
            stop_price=stop,
            risk_r=risk,
        )

    # --------------------------------------------------------------- sell / trim
    if target >= current_weight - tol:
        # scaling landed exactly on the carried weight: nothing left to do
        _drop(dropped, ORDER_NOT_REACHABLE, symbol)
        return degrade(
            f"缩放后目标仓位 {target:.2%} 与现有仓位一致，"
            f"{rec.ACTION_LABELS[intent.action]}意图不产生订单",
            stop=intent.stop_price,
        )
    # a buy or passive label reaching here was pulled below the carried weight by E_t
    # alone; account_delever is the registered class for that trim (a risk reduction
    # that must happen, unlike a profit exit), and it is attack-only, which E_t < 1
    # guarantees (the defense sleeve is never scaled)
    converted = intent.action not in rec.SELL_ACTIONS
    action = rec.Action.ACCOUNT_DELEVER if converted else intent.action
    price = position.last_price
    desired = _lot_floor(target * equity, price, lot)
    sell = min(position.quantity - desired, position.sellable_quantity)
    achieved = _achieved_weight(position.quantity - sell, price, equity)
    if sell <= 0 or achieved >= current_weight - tol:
        return degrade(
            "可卖数量不足（T+1 或冻结）或不足一个整手，"
            "减仓意图未执行，本半日维持现有仓位",
            stop=intent.stop_price,
        )
    if intent.change_reason:
        change_reason = intent.change_reason
    elif converted:
        change_reason = (
            f"账户级降仓：基础目标 {intent.base_target_weight:.2%} × 账户系数 "
            f"{multiplier:.2f} -> 目标仓位 {achieved:.2%}，"
            f"{rec.ACTION_LABELS[intent.action]}意图按降仓执行"
        )
    else:
        change_reason = _default_change_reason(
            intent, action=action, target_weight=achieved, multiplier=multiplier
        )
    _require_band(intent)
    stop = risk = None
    if intent.sleeve is rec.Sleeve.ATTACK:
        stop = _held_stop(symbol, intent.stop_price, position)
        risk = rec.risk_amount(
            position.quantity,
            price,
            stop,
            sleeve=intent.sleeve,
            trade_date=trade_date,
            schedule=policy.fees,
        )
    return _item(
        intent,
        action=action,
        current_quantity=position.quantity,
        recommended_quantity=sell,
        target_weight=achieved,
        valid_until=valid_until,
        change_reason=change_reason,
        price_lower=intent.price_lower,
        price_upper=intent.price_upper,
        stop_price=stop,
        risk_r=risk,
    )


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #
def assemble_plan(
    *,
    decision_point: rec.DecisionPoint,
    trading_day: dt.date,
    generated_at: dt.datetime,
    account: rec.AccountSnapshot,
    overlay: ro.OverlayDecision,
    recommendation_version: str,
    attack_candidates: tuple[AttackCandidate, ...] | list[AttackCandidate] = (),
    defense_candidates: tuple[DefenseCandidate, ...] | list[DefenseCandidate] = (),
    carried_stops: Mapping[str, float] | None = None,
    next_trading_day: dt.date | None = None,
    policy: rec.PlanPolicy | None = None,
) -> rec.RecommendationPlan:
    """Assemble and validate one half-session version.

    ``strategy_version`` / ``market_as_of`` / ``account_snapshot_version`` come from
    the account snapshot: ``validate_plan`` requires the plan identity to equal the
    account identity, so a separate parameter could only introduce a second,
    disagreeing identity.

    Candidate order is priority order inside each sleeve; the attack sleeve is
    consumed before the defense sleeve for the ``max_new_entries`` budget.  Attack
    weight is scaled by ``overlay.exposure_multiplier`` and defense weight is not
    (prereg 1): a held attack name whose base target differs from its carried weight
    is executed at ``base x E_t`` (under a lowered state that can be a trim even for
    a buy-labelled candidate, emitted as ``account_delever``), while a candidate whose
    base target equals the carried weight carries unchanged - an explicit hold is
    authoritative.  A held symbol with no candidate is carried at its current weight
    (``no_action``, or ``hold`` when ``carried_stops`` supplies the registered stop);
    the module never invents a stop, so without that mapping an attack carry reaches
    the plan without a stop zone and is disclosed by the
    ``unscaled_attack_holding`` token.

    Raises :class:`StrategyPlanError` for an unassemblable input and
    :class:`~quant.portfolio.recommendations.RecommendationError` for a version that
    fails the registered limits.
    """

    point = rec.DecisionPoint(decision_point)
    pol = policy or rec.DEFAULT_POLICY
    _require(
        isinstance(account, rec.AccountSnapshot),
        StrategyPlanReason.INVALID_CANDIDATE,
        f"account must be an AccountSnapshot, got {type(account).__name__}",
    )
    _require(
        isinstance(overlay, ro.OverlayDecision),
        StrategyPlanReason.INVALID_CANDIDATE,
        f"overlay must be an OverlayDecision, got {type(overlay).__name__}",
    )
    _require(
        isinstance(trading_day, dt.date) and not isinstance(trading_day, dt.datetime),
        StrategyPlanReason.INVALID_CANDIDATE,
        f"trading_day must be a date, got {trading_day!r}",
    )
    _require(
        isinstance(generated_at, dt.datetime),
        StrategyPlanReason.INVALID_CANDIDATE,
        f"generated_at must be a datetime, got {generated_at!r}",
    )
    # The overlay row is the one that produced the exposure multiplier; it must be
    # the row for this account's market cut-off and this trading day.
    _require(
        overlay.decision_time == account.market_as_of,
        StrategyPlanReason.OVERLAY_MARKET_MISMATCH,
        f"overlay decision_time {overlay.decision_time} is not the account market_as_of "
        f"{account.market_as_of}: the exposure multiplier would come from another cut-off",
    )
    _require(
        overlay.decision_time.date() == trading_day,
        StrategyPlanReason.DECISION_TIME_MISMATCH,
        f"overlay decision_time {overlay.decision_time} does not belong to trading day "
        f"{trading_day}",
    )

    valid_from, valid_until = rec.session_window(
        point, trading_day=trading_day, next_trading_day=next_trading_day
    )
    trade_date = valid_from.date()

    intents: list[_Intent] = []
    seen: dict[str, rec.Sleeve] = {}
    for attack in attack_candidates:
        _require(
            isinstance(attack, AttackCandidate),
            StrategyPlanReason.INVALID_CANDIDATE,
            f"attack_candidates must hold AttackCandidate, got {type(attack).__name__}",
        )
        intent = _intent_from_attack(attack)
        if intent.symbol in seen:
            raise StrategyPlanError(
                StrategyPlanReason.DUPLICATE_CANDIDATE,
                f"{intent.symbol}: more than one candidate in this version (the output "
                "contract allows one item per symbol)",
                symbol=intent.symbol,
            )
        seen[intent.symbol] = intent.sleeve
        intents.append(intent)
    for defense in defense_candidates:
        _require(
            isinstance(defense, DefenseCandidate),
            StrategyPlanReason.INVALID_CANDIDATE,
            f"defense_candidates must hold DefenseCandidate, got {type(defense).__name__}",
        )
        intent = _intent_from_defense(defense)
        if intent.symbol in seen:
            raise StrategyPlanError(
                StrategyPlanReason.DUPLICATE_CANDIDATE,
                f"{intent.symbol}: more than one candidate in this version (the output "
                "contract allows one item per symbol)",
                symbol=intent.symbol,
            )
        seen[intent.symbol] = intent.sleeve
        intents.append(intent)

    account_action = ro.to_plan_account_action(overlay.action)
    risk_state = ro.to_plan_risk_state(overlay.risk_state)
    # the entry gate is sleeve-scoped, exactly like the registered mechanisms and the
    # validator's ENTRY_BLOCKED_BY_RISK_STATE raise: blocking new attack exposure is
    # an attack-sleeve action, while a data gap fails closed for both sleeves
    attack_open = ro.attack_entry_allowed(overlay.risk_state) and (
        account_action is not rec.Action.ACCOUNT_DELEVER
    )
    data_gap = overlay.risk_state is ro.OverlayState.INSUFFICIENT_DATA
    stops = _carried_stops(carried_stops, account=account, covered=seen)

    dropped: dict[str, list[str]] = {}
    budget = account.cash + pol.weight_tolerance * max(account.equity, 1.0)
    spent = 0.0
    new_entries = 0

    def admit_buy(
        *, sleeve: rec.Sleeve, quantity: int, price_upper: float, is_new: bool, symbol: str
    ) -> bool:
        nonlocal spent, new_entries
        if is_new and new_entries >= pol.max_new_entries:
            _drop(dropped, NEW_ENTRY_CAP_VOIDED, symbol)
            return False
        cost = _buy_cost(
            sleeve=sleeve,
            quantity=quantity,
            price_upper=price_upper,
            trade_date=trade_date,
            schedule=pol.fees,
        )
        if spent + cost > budget:
            _drop(dropped, CASH_EXHAUSTED, symbol)
            return False
        spent += cost
        if is_new:
            new_entries += 1
        return True

    items: list[rec.RecommendationItem] = []
    for intent in intents:
        emitted = _emit_intent(
            intent,
            account=account,
            overlay=overlay,
            policy=pol,
            attack_open=attack_open,
            data_gap=data_gap,
            admit_buy=admit_buy,
            dropped=dropped,
            valid_until=valid_until,
            trade_date=trade_date,
        )
        if emitted is not None:
            items.append(emitted)

    for position in account.positions:
        if position.symbol in seen:
            continue
        stop = stops.get(position.symbol)
        if stop is None:
            change_reason = "本版无该标的候选：维持现有仓位，不产生订单"
        else:
            change_reason = (
                "本版无该标的候选：按策略层给定的止损/移动保护线持有，不产生订单"
            )
        if position.sleeve is rec.Sleeve.ATTACK and overlay.exposure_multiplier < 1.0:
            _drop(dropped, UNSCALED_ATTACK_HOLDING, position.symbol)
            change_reason += (
                f"；账户级进攻系数 {overlay.exposure_multiplier:.2f} 未覆盖该标的"
                "（策略层未给出基础目标），暴露未被缩放"
            )
        items.append(
            _passive(
                _carried_intent(position),
                position,
                stop=stop,
                equity=account.equity,
                valid_until=valid_until,
                trade_date=trade_date,
                policy=pol,
                change_reason=change_reason,
                keep_band=False,
            )
        )

    display = (
        f"账户级风险 {ro.STATE_LABELS[overlay.risk_state]} / "
        f"账户动作 {rec.ACTION_LABELS[account_action]} / "
        f"进攻暴露系数 {overlay.exposure_multiplier:.2f} / "
        f"触发 {overlay.trigger_reason}"
    )
    return rec.build_plan(
        decision_point=point,
        generated_at=generated_at,
        identity=rec.PlanIdentity(
            strategy_version=account.strategy_version,
            market_as_of=account.market_as_of,
            account_snapshot_version=account.snapshot_version,
        ),
        account=account,
        recommendation_version=recommendation_version,
        valid_from=valid_from,
        valid_until=valid_until,
        items=tuple(items),
        risk_state=risk_state,
        account_action=account_action,
        note=_format_note(display, dropped),
        policy=pol,
    )
