"""Account-level risk overlay: the attack-exposure multiplier ``E_t``.

This module is the *state machine* of the account-level risk layer of
``docs/research/exp-20260920-account-risk-overlay-prereg.md``.  It answers one
question per decision point: how large may the **attack** sleeve be?  It does
not price a book, generate orders, touch cash or positions, and it never calls
``quant.backtest.band_engine``: a row here is a *target multiplier*, not a
trade (``docs/plans/daily-strategy-output-contract.md`` §4).

The three frozen configs (prereg §2, verbatim)
---------------------------------------------
==================  ==================================================
``C0`` control      constant ``E_t = 0.90``, no account-level reduction
``C1`` market trend ``000300`` close ``>`` SMA200 -> ``0.90``, else ``0.40``
``C2`` acct drawdn  own high-water drawdown ``<= 10%`` -> ``0.90``, else ``0.40``
==================  ==================================================

Dynamic account feedback (prereg ``exp-20260921-account-risk-dynamic``)
----------------------------------------------------------------------
The same state machine drives the **live ledger** through
:class:`AccountRiskDynamics`: the host feeds the account's own completed
closes (``observe_close``) at every 15:00-class decision point and asks for
one row per decision point (``step``).  The frozen dynamic family adds three
mechanisms over the *same* two exposure levels and the *same* recovery /
cooldown counters:

==================  ==================================================
``D0`` control      constant ``E_t = 0.90`` (carrier parity anchor)
``D1`` day loss     own single-session return ``<= -3.00%``
``D2`` phase dd     own ``dd`` from the trailing 60-session peak ``> 8.00%``
``D3`` hwm dd       own all-time high-water ``dd > 10.00%``
==================  ==================================================

``D0``/``D1``/``D2``/``D3`` are *not* members of :data:`POLICIES` (that table
is the frozen C0-C2 contract of the earlier prereg); they live in
:data:`DYNAMIC_POLICIES` and are resolved by :func:`dynamic_policy_for`.  Both
families share the transition core (:func:`_transition`), so the reduction /
recovery / cooldown semantics cannot drift between the batch resolver and the
incremental one.  ``D2``/``D3`` re-use the registered R8/R9 values verbatim
(``D60`` 8% with re-arm 4%, own-peak 10% with re-arm 5%); ``D1``'s 3% is the
one pre-run constant this prereg mints, written down before any run.

``E_t`` is the **only** lever this layer owns: a consumer multiplies the base
attack target by it and leaves the defensive sleeve and cash untouched
(prereg §1).  At the floor (``0.40``) new attack entries remain *allowed* at
reduced size - "暂停新增进攻仓位" is a separate account-level action and is
deliberately reserved for :attr:`OverlayState.BLOCKED`, which no frozen config
can reach (see ``hard_stop_drawdown`` below).  A consumer must never key an
entry gate off ``risk_state == reduced``.

Micro-decisions pinned here (all before any run, per prereg §2 "恢复和冷却
语义必须在运行前写入配置，不能依据结果临时改变")
-------------------------------------------------------------------------
* **asof only, keyed on the registered decision point.**  A decision point
  decides which completed session it may read (``recommendations.DecisionPoint``
  / ``SESSION_BOUNDS``): a 15:00-class point (``DAY0_CLOSE`` / ``PM_1500``)
  reads *that* trading day's close, ``AM_1130`` may only read the *previous*
  session's close (``close_asof``).  Consequence, stated deliberately: an
  11:30 row carries exactly the same asof date, state, exposure and trigger as
  the preceding close row - it exists to re-issue a plan, not to move the
  overlay.  A 15:00-time clock is mapped to a decision point by
  :func:`decision_point_of`; callers that know their point (the Day0/Day1
  loop) should pass ``decision_points`` explicitly.  No future close ever
  reaches a row (``bisect_right(dates, key) - 1``, the registered asof
  pattern).
* **lookback contract (C1).**  ``benchmark_close`` MUST carry at least
  ``sma_sessions`` sessions *before* the first decision point: the window is
  ``rolling_mean(N, min_samples=N)``, so a run that passes only the sample
  window gets ~199 leading ``INSUFFICIENT_DATA`` rows at ``level_off`` (which
  the plan layer turns into "no new attack entries") and the C1-vs-C0
  comparison would measure the warm-up, not the trend rule.  Use
  :func:`insufficient_data_rows` to assert the prologue is absent.  C2 has no
  such requirement: its reference peak starts at the run's first equity
  observation.
* **down-shift is immediate, up-shift is gated.**  A trigger lowers exposure on
  the decision point that observes it; restoring to ``level_on`` requires the
  fixed recovery condition (:attr:`OverlayPolicy.rearm_drawdown` for C2:
  R9's registered re-arm gap ``T/2``; ``close > SMA200`` for C1, the same
  condition as the trigger) to hold for ``recovery_confirmations`` consecutive
  **sessions** (R8 ``T20c2``'s registered two-session confirmation) **and**
  ``cooldown_sessions`` sessions to have elapsed since the lowering.
* **counter unit = judged sessions, not decision points.**  A "session" is one
  distinct asof observation day: the counters advance only when the asof index
  moves, so two decision points that re-read the same completed close count
  once.  Denominating them in decision points would let
  ``recovery_confirmations=2`` be satisfied by a single up-session (a 15:00
  row and the next 11:30 row share D's close) - the tests pin that.
* **no third exposure level.**  ``level_on``/``level_off`` are the only two
  values emitted: prereg §2 freezes "一个固定降档".  "Recovery must not jump
  straight back" is enforced by the confirmation + cooldown *delay*, never by
  an unregistered intermediate multiplier.
* **boundary.**  C1 off when ``close <= SMA200`` (registered
  ``sma_trend_state`` uses a strict ``>`` for on).  C2 off when
  ``drawdown > 10%`` (strict, prereg's "超过10%"); the registered research
  variant ``pdd_hysteresis_risk_fn`` uses ``dd >= threshold`` and therefore
  differs at exactly ``10.00%`` - that deviation is tested explicitly (with an
  exactly representable threshold, since ``1 - 90/100`` rounds *below* 10%).
* **insufficient data fails closed.**  No benchmark observation, an unformed
  SMA window or no account-equity observation yields
  :attr:`OverlayState.INSUFFICIENT_DATA` /
  :attr:`OverlayAction.FAIL_CLOSED` at ``level_off``
  (``None`` asof/``None`` drawdown), never a silent default.  The registered
  research fallback is the same ``level_off`` but is reported as risk-off.  A
  data gap starts no cooldown: availability restores the state at once.
* **first decision point.**  ``previous_state`` is ``None``; change detection
  compares against the implicit pre-overlay base (``normal`` at ``level_on``),
  so a first row that is not ``normal`` carries that state's own action and
  ``state_changed`` is true.  Invariant: ``action is HOLD`` iff
  ``state_changed`` is false (prereg: "规则只在状态发生变化时产生调仓目标").
* **``C0`` is the control anchor**: it never leaves ``normal`` and never emits
  a reduction, whatever the inputs say.
* **no ordering repair.**  Decision times must be strictly increasing and
  observation dates strictly increasing and unique; otherwise
  :class:`RiskOverlayError`.

Equivalence with the registered machinery
-----------------------------------------
``quant.research.etf_rotation`` already implements these two mechanisms
(``sma_trend_state``/``exposures_from_state`` for C1, ``pdd_risk_fn`` and
``pdd_hysteresis_risk_fn`` for C2).  This layer cannot call them: they are
long-form helpers over a polars frame that return only the boolean/exposure,
while every row here must also report its asof date, SMA value, high-water mark
and drawdown, and C2 additionally needs the prereg's strict ``> 10%`` boundary
plus the recovery gate.  Drift is therefore pinned by tests, not by reuse:
with the recovery gate disabled (``recovery_confirmations == 1``,
``cooldown_sessions == 0``) on a path whose drawdown only ever lands in
``> threshold`` (off) or ``<= rearm`` (new high) the emitted series must equal
``exposures_from_state(sma_trend_state(...), 0.90, 0.40)`` for C1 and
``pdd_risk_fn(0.10, 0.90, 0.40)`` for C2, session for session
(``tests/unit/test_risk_overlay.py``); a path parked inside the re-arm gap
(``rearm < dd <= threshold``) must equal ``pdd_hysteresis_risk_fn(0.10, 0.05)``
instead, and differ from ``pdd_risk_fn``, which pins the deliberate R9 gap.

The half-session model is NOT re-minted here:
:data:`SESSION_CLOSE` and the decision-point mapping are derived from
``recommendations.SESSION_BOUNDS`` / ``recommendations.DecisionPoint``.

Plan-layer bridge
-----------------
``recommendations.RiskState``/``Action`` are the plan vocabulary; this module's
:class:`OverlayState`/:class:`OverlayAction` are the overlay vocabulary.  They
are bridged explicitly and tested by :func:`to_plan_risk_state` /
:func:`to_plan_account_action` / :func:`attack_entry_allowed` so the plan layer
can consume a row without a second, unreconciled string set.

The module is not re-exported from ``quant.portfolio.__init__`` (owned
elsewhere); import it as ``quant.portfolio.risk_overlay``.
"""
from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from quant.portfolio.recommendations import SESSION_BOUNDS
from quant.portfolio.recommendations import Action as PlanAction
from quant.portfolio.recommendations import DecisionPoint, RiskState, Session

__all__ = [
    "ACTION_LABELS",
    "C0",
    "C1",
    "C2",
    "CONFIG_IDS",
    "COOLDOWN_SESSIONS",
    "D0",
    "D1",
    "D2",
    "D3",
    "DYNAMIC_CONFIG_IDS",
    "DYNAMIC_POLICIES",
    "LEVEL_OFF",
    "LEVEL_ON",
    "POLICIES",
    "REASON_LABELS",
    "RECOVERY_CONFIRMATIONS",
    "SAME_DAY_CLOSE_POINTS",
    "SESSION_CLOSE",
    "STATE_LABELS",
    "AccountRiskDynamics",
    "GateMechanism",
    "OverlayAction",
    "OverlayDecision",
    "OverlayPolicy",
    "OverlayReason",
    "OverlayState",
    "RiskOverlayError",
    "attack_entry_allowed",
    "close_asof",
    "decision_point_of",
    "dynamic_policy_for",
    "insufficient_data_rows",
    "policy_for",
    "resolve_overlay",
    "running_peak_drawdown",
    "to_plan_account_action",
    "to_plan_risk_state",
]

#: Config ids of the three frozen configurations (prereg §2).
C0 = "C0"
C1 = "C1"
C2 = "C2"
CONFIG_IDS = (C0, C1, C2)

#: Dynamic account-feedback configs (prereg exp-20260921 §3): the control
#: anchor plus the three pre-registered mechanisms, all driven by this
#: account's own completed closes only.
D0 = "D0"
D1 = "D1"
D2 = "D2"
D3 = "D3"
DYNAMIC_CONFIG_IDS = (D0, D1, D2, D3)

#: Exposure levels common to C0-C2: one fixed down-shift, two levels only.
LEVEL_ON = 0.90
LEVEL_OFF = 0.40

#: The half-session model is owned by ``recommendations``; this is a view of
#: the registered table, not a second convention.
SESSION_CLOSE = SESSION_BOUNDS[Session.PM][1]      # 15:00, the day's close

#: Decision points whose day's close is already complete when they are taken.
SAME_DAY_CLOSE_POINTS = frozenset(
    {DecisionPoint.DAY0_CLOSE, DecisionPoint.PM_1500}
)

#: Registered confirmation count (R8 ``T20c2``: two sessions above re-enter)
#: and cooldown, both denominated in SESSIONS (distinct asof observation days),
#: not in decision points.  Pre-run constants, never chosen from results.
RECOVERY_CONFIRMATIONS = 2
COOLDOWN_SESSIONS = 3


class OverlayState(str, Enum):
    """Account-level risk state of the overlay at one decision point."""

    NORMAL = "normal"
    REDUCED = "reduced"
    BLOCKED = "blocked"
    INSUFFICIENT_DATA = "insufficient_data"


class OverlayAction(str, Enum):
    """What the overlay changes at this decision point."""

    HOLD = "hold"
    REDUCE_ATTACK = "reduce_attack"
    BLOCK_NEW_ATTACK = "block_new_attack"
    RESTORE_ATTACK = "restore_attack"
    FAIL_CLOSED = "fail_closed"


class GateMechanism(str, Enum):
    """Which frozen rule decides the multiplier."""

    CONSTANT = "constant"
    INDEX_SMA = "index_sma"
    ACCOUNT_DRAWDOWN = "account_drawdown"
    DAILY_LOSS = "daily_loss"
    PHASE_DRAWDOWN = "phase_drawdown"


class OverlayReason(str, Enum):
    """Stable fail-closed reason codes of this module."""

    INVALID_FIELD = "invalid_field"
    UNKNOWN_CONFIG = "unknown_config"
    DECISION_TIMES_NOT_INCREASING = "decision_times_not_increasing"
    MISSING_BENCHMARK_SERIES = "missing_benchmark_series"
    MISSING_EQUITY_SERIES = "missing_equity_series"
    SERIES_NOT_INCREASING = "series_not_increasing"
    CONFIG_POLICY_MISMATCH = "config_policy_mismatch"


class RiskOverlayError(ValueError):
    """Fail-closed rejection.  Carries a stable :class:`OverlayReason`."""

    def __init__(self, reason: OverlayReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail

    def to_mapping(self) -> dict[str, Any]:
        return {"reason": self.reason.value, "detail": self.detail}


STATE_LABELS = {
    OverlayState.NORMAL: "正常",
    OverlayState.REDUCED: "账户级降仓",
    OverlayState.BLOCKED: "暂停新增进攻",
    OverlayState.INSUFFICIENT_DATA: "数据不足",
}

ACTION_LABELS = {
    OverlayAction.HOLD: "不动",
    OverlayAction.REDUCE_ATTACK: "降低进攻仓位",
    OverlayAction.BLOCK_NEW_ATTACK: "暂停新增进攻",
    OverlayAction.RESTORE_ATTACK: "恢复进攻仓位",
    OverlayAction.FAIL_CLOSED: "失败关闭",
}

REASON_LABELS = {
    "control_constant_exposure": "控制组：恒定暴露，无账户级降仓",
    "index_above_trend_sma": "指数收盘高于趋势均线",
    "index_at_or_below_trend_sma": "指数收盘不高于趋势均线",
    "drawdown_within_limit": "账户回撤在阈值内",
    "drawdown_beyond_limit": "账户回撤超过阈值",
    "phase_drawdown_within_limit": "账户距阶段峰回撤在阈值内",
    "phase_drawdown_beyond_limit": "账户距阶段峰回撤超过阈值",
    "daily_loss_within_limit": "单会话权益损失在阈值内",
    "daily_loss_beyond_limit": "单会话权益损失超过阈值",
    "account_hard_stop_breached": "账户回撤触及硬止损（非预登记配置）",
    "benchmark_observation_missing": "缺少可用基准行情观测",
    "sma_warmup_incomplete": "SMA 窗口尚未形成",
    "equity_observation_missing": "缺少可用账户权益观测",
    "recovery_pending_cooldown": "恢复条件已满足，仍在冷却期",
    "recovery_pending_confirmation": "恢复条件尚未连续确认",
    "recovery_confirmed": "恢复条件已确认，回到正常暴露",
}


def _require(condition: bool, reason: OverlayReason, detail: str) -> None:
    if not condition:
        raise RiskOverlayError(reason, detail)


def _as_datetime(value: Any, field_name: str) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, SESSION_CLOSE)
    raise RiskOverlayError(
        OverlayReason.INVALID_FIELD,
        f"{field_name} must be a date or datetime, got {type(value).__name__}",
    )


def decision_point_of(moment: dt.date | dt.datetime) -> DecisionPoint:
    """Registered decision point a bare clock time belongs to.

    At/after :data:`SESSION_CLOSE` (the registered PM close, 15:00) the day's
    close is complete -> ``PM_1500``.  Anything earlier (an 11:30 decision, a
    pre-open decision) can only read the previous session's close ->
    ``AM_1130``.  ``DAY0_CLOSE`` and ``PM_1500`` share the same availability,
    so a bare time cannot distinguish them; a caller of the Day0/Day1 loop
    should pass its own ``decision_points`` instead.
    """
    clock = _as_datetime(moment, "decision_time").time()
    return (DecisionPoint.PM_1500 if clock >= SESSION_CLOSE
            else DecisionPoint.AM_1130)


def _asof_key(
    trading_day: dt.date, decision_point: DecisionPoint
) -> dt.date:
    point = (decision_point if isinstance(decision_point, DecisionPoint)
             else DecisionPoint(decision_point))
    return (trading_day if point in SAME_DAY_CLOSE_POINTS
            else trading_day - dt.timedelta(days=1))


def _asof_pos(
    observations: Sequence[dt.date],
    *,
    trading_day: dt.date,
    decision_point: DecisionPoint,
) -> int | None:
    """Index of the latest completed observation, or ``None``."""
    pos = bisect.bisect_right(observations, _asof_key(trading_day, decision_point)) - 1
    return pos if pos >= 0 else None


def close_asof(
    observations: Sequence[dt.date],
    *,
    trading_day: dt.date,
    decision_point: DecisionPoint = DecisionPoint.PM_1500,
) -> dt.date | None:
    """Latest ``observations`` date whose close is complete for this decision.

    ``SAME_DAY_CLOSE_POINTS`` (15:00-class: ``DAY0_CLOSE`` / ``PM_1500``) may
    read ``trading_day`` itself; every other point may only read the previous
    session, so the key is ``trading_day - 1`` and the bisect finds the last
    completed session.  ``None`` when no observation precedes it.
    ``observations`` must be sorted (validated by :func:`resolve_overlay`).
    """
    pos = _asof_pos(observations, trading_day=trading_day,
                    decision_point=decision_point)
    return None if pos is None else observations[pos]


def _rolling_sma(closes: Sequence[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    total = 0.0
    for i, close in enumerate(closes):
        total += close
        if i >= window:
            total -= closes[i - window]
        out.append(total / window if i >= window - 1 else None)
    return out


def running_peak_drawdown(
    equity: Sequence[tuple[dt.date, float]],
) -> dict[dt.date, tuple[float, float]]:
    """``date -> (high_water_mark, drawdown)`` from observations up to that date.

    The peak is the all-time running maximum of the already-confirmed equity
    (registered PDD reference, never reset); ``drawdown = 1 - equity / peak``.
    """
    dates, values = _series(equity, "equity")
    out: dict[dt.date, tuple[float, float]] = {}
    peak: float | None = None
    for day, value in zip(dates, values):
        peak = value if peak is None else max(peak, value)
        out[day] = (peak, 1.0 - value / peak)
    return out


def running_phase_drawdown(
    equity: Sequence[tuple[dt.date, float]], window: int
) -> dict[dt.date, tuple[float, float]]:
    """``date -> (phase peak, drawdown)`` over a TRAILING window of sessions.

    The reference is the maximum of the last ``window`` completed
    observations (the current one included), so a run shorter than
    ``window`` judges against all of its own observations - the registered
    dynamic-family convention (prereg exp-20260921 §3, R8/R9 ``D60``).
    """
    dates, values = _series(equity, "equity")
    out: dict[dt.date, tuple[float, float]] = {}
    for i, day in enumerate(dates):
        peak = max(values[max(0, i - window + 1):i + 1])
        out[day] = (peak, 1.0 - values[i] / peak)
    return out


def _series(rows: Sequence[tuple[dt.date, float]], field_name: str) -> tuple[list[dt.date], list[float]]:
    dates: list[dt.date] = []
    values: list[float] = []
    for row in rows:
        _require(
            isinstance(row, (tuple, list)) and len(row) == 2,
            OverlayReason.INVALID_FIELD,
            f"{field_name} rows must be (date, value), got {row!r}",
        )
        day, value = row
        _require(
            isinstance(day, dt.date) and not isinstance(day, dt.datetime),
            OverlayReason.INVALID_FIELD,
            f"{field_name} dates must be datetime.date, got {day!r}",
        )
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and float(value) == float(value) and abs(float(value)) != float("inf"),
            OverlayReason.INVALID_FIELD,
            f"{field_name} values must be finite numbers, got {value!r}",
        )
        if dates:
            _require(
                day > dates[-1],
                OverlayReason.SERIES_NOT_INCREASING,
                f"{field_name} dates must strictly increase; {day} follows {dates[-1]}",
            )
        dates.append(day)
        values.append(float(value))
    return dates, values


@dataclass(frozen=True)
class OverlayPolicy:
    """Frozen rule set of one configuration.  Explicit, never implicit."""

    config_id: str
    mechanism: GateMechanism
    level_on: float = LEVEL_ON
    level_off: float = LEVEL_OFF
    sma_sessions: int = 200
    drawdown_threshold: float = 0.10
    #: D1 (prereg exp-20260921 §3): single-session own-equity loss magnitude
    #: that lowers the attack sleeve.  ``None``-free on purpose: it is a
    #: pre-run constant, never derived from a result.
    daily_loss_threshold: float = 0.03
    #: D2: trailing sessions forming the "phase" peak (R8/R9 ``D60``).
    phase_sessions: int = 60
    #: C2 recovery drawdown.  ``None`` -> ``drawdown_threshold / 2``
    #: (R9's registered re-arm gap ``T/2``).
    rearm_drawdown: float | None = None
    #: Tier 2, OFF-PREREG: no frozen config registers a hard stop (prereg §2
    #: "第一版使用一个固定降档").  ``None`` -> :attr:`OverlayState.BLOCKED`
    #: is unreachable.  A value must be registered before any run uses it.
    hard_stop_drawdown: float | None = None
    #: Consecutive SESSIONS (distinct asof observation days) on which the
    #: recovery condition must hold before a restore (R8 ``T20c2`` precedent).
    recovery_confirmations: int = RECOVERY_CONFIRMATIONS
    #: SESSIONS of minimum dwell after an exposure-lowering transition
    #: (measured in asof sessions, so an 11:30 row that re-reads the previous
    #: close does not advance it).
    cooldown_sessions: int = COOLDOWN_SESSIONS

    def __post_init__(self) -> None:
        _require(
            isinstance(self.config_id, str) and self.config_id != "",
            OverlayReason.INVALID_FIELD,
            f"config_id must be a non-empty string, got {self.config_id!r}",
        )
        if not isinstance(self.mechanism, GateMechanism):
            raise RiskOverlayError(
                OverlayReason.INVALID_FIELD,
                f"mechanism must be a GateMechanism, got {self.mechanism!r}",
            )
        _require(
            isinstance(self.sma_sessions, int) and not isinstance(self.sma_sessions, bool)
            and self.sma_sessions >= 2,
            OverlayReason.INVALID_FIELD,
            f"sma_sessions must be an int >= 2, got {self.sma_sessions!r}",
        )
        for name in ("recovery_confirmations", "cooldown_sessions"):
            value = getattr(self, name)
            _require(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0,
                OverlayReason.INVALID_FIELD,
                f"{name} must be a non-negative int, got {value!r}",
            )
        _require(
            self.recovery_confirmations >= 1,
            OverlayReason.INVALID_FIELD,
            "recovery_confirmations must be >= 1",
        )
        for name in ("level_on", "level_off"):
            value = getattr(self, name)
            _require(
                isinstance(value, float) and 0.0 <= value <= 1.0,
                OverlayReason.INVALID_FIELD,
                f"{name} must be a float in [0, 1], got {value!r}",
            )
        _require(
            self.level_off <= self.level_on,
            OverlayReason.INVALID_FIELD,
            f"level_off {self.level_off} must not exceed level_on {self.level_on}",
        )
        _require(
            isinstance(self.drawdown_threshold, float)
            and 0.0 < self.drawdown_threshold < 1.0,
            OverlayReason.INVALID_FIELD,
            f"drawdown_threshold must be in (0, 1), got {self.drawdown_threshold!r}",
        )
        _require(
            isinstance(self.daily_loss_threshold, float)
            and 0.0 < self.daily_loss_threshold < 1.0,
            OverlayReason.INVALID_FIELD,
            "daily_loss_threshold must be in (0, 1), got "
            f"{self.daily_loss_threshold!r}",
        )
        _require(
            isinstance(self.phase_sessions, int)
            and not isinstance(self.phase_sessions, bool)
            and self.phase_sessions >= 2,
            OverlayReason.INVALID_FIELD,
            f"phase_sessions must be an int >= 2, got {self.phase_sessions!r}",
        )
        if self.rearm_drawdown is not None:
            _require(
                isinstance(self.rearm_drawdown, float)
                and 0.0 <= self.rearm_drawdown < self.drawdown_threshold,
                OverlayReason.INVALID_FIELD,
                f"rearm_drawdown {self.rearm_drawdown!r} must be in "
                f"[0, {self.drawdown_threshold})",
            )
        if self.hard_stop_drawdown is not None:
            _require(
                isinstance(self.hard_stop_drawdown, float)
                and self.drawdown_threshold < self.hard_stop_drawdown < 1.0,
                OverlayReason.INVALID_FIELD,
                f"hard_stop_drawdown {self.hard_stop_drawdown!r} must be in "
                f"({self.drawdown_threshold}, 1)",
            )
            _require(
                self.mechanism is GateMechanism.ACCOUNT_DRAWDOWN,
                OverlayReason.INVALID_FIELD,
                "hard_stop_drawdown is an account-equity rule and requires the "
                "account_drawdown mechanism",
            )

    @property
    def rearm(self) -> float:
        """Drawdown level at which a C2 recovery may start."""
        return (self.drawdown_threshold / 2.0
                if self.rearm_drawdown is None else self.rearm_drawdown)


POLICIES: dict[str, OverlayPolicy] = {
    C0: OverlayPolicy(C0, GateMechanism.CONSTANT),
    C1: OverlayPolicy(C1, GateMechanism.INDEX_SMA, sma_sessions=200),
    C2: OverlayPolicy(C2, GateMechanism.ACCOUNT_DRAWDOWN, drawdown_threshold=0.10),
}

#: Frozen dynamic family (prereg exp-20260921 §3).  ``D3`` carries the
#: registered C2 mechanism verbatim (own high-water 10% / re-arm 5%) under the
#: dynamic-run id; ``D2`` carries R8/R9's ``D60`` (8% / re-arm 4%); ``D1`` is
#: this prereg's single pre-run constant (3%).  All three share the frozen
#: two-level exposure and the 2-session / 3-session recovery gate.
DYNAMIC_POLICIES: dict[str, OverlayPolicy] = {
    D0: OverlayPolicy(D0, GateMechanism.CONSTANT),
    D1: OverlayPolicy(D1, GateMechanism.DAILY_LOSS, daily_loss_threshold=0.03),
    D2: OverlayPolicy(D2, GateMechanism.PHASE_DRAWDOWN, phase_sessions=60,
                      drawdown_threshold=0.08, rearm_drawdown=0.04),
    D3: OverlayPolicy(D3, GateMechanism.ACCOUNT_DRAWDOWN,
                      drawdown_threshold=0.10, rearm_drawdown=0.05),
}


def policy_for(config_id: str) -> OverlayPolicy:
    """Frozen policy of ``C0``/``C1``/``C2``."""
    try:
        return POLICIES[config_id]
    except (KeyError, TypeError) as exc:
        raise RiskOverlayError(
            OverlayReason.UNKNOWN_CONFIG,
            f"unknown config_id {config_id!r}; expected one of {', '.join(CONFIG_IDS)}",
        ) from exc


def dynamic_policy_for(config_id: str) -> OverlayPolicy:
    """Frozen policy of ``D0``/``D1``/``D2``/``D3`` (dynamic family)."""
    try:
        return DYNAMIC_POLICIES[config_id]
    except (KeyError, TypeError) as exc:
        raise RiskOverlayError(
            OverlayReason.UNKNOWN_CONFIG,
            f"unknown dynamic config_id {config_id!r}; expected one of "
            f"{', '.join(DYNAMIC_CONFIG_IDS)}",
        ) from exc


@dataclass(frozen=True)
class OverlayDecision:
    """One decision point's account-level risk row.

    Contract fields (13) plus three diagnostics.  Machine-readable only: the
    display text lives in :data:`STATE_LABELS` / :data:`ACTION_LABELS` /
    :data:`REASON_LABELS` and in :meth:`describe`.
    """

    config_id: str
    decision_time: dt.datetime
    exposure_multiplier: float
    risk_state: OverlayState
    action: OverlayAction
    trigger_reason: str
    previous_state: OverlayState | None
    recovery_condition: str
    #: The asof **session date** from which a restore may be emitted (the
    #: counter is session-denominated); ``None`` when no lowering is active or
    #: the boundary lies beyond the supplied observations.
    cooldown_until: dt.date | None
    benchmark_as_of: dt.date | None
    equity_as_of: dt.date | None
    high_water_mark: float | None
    drawdown: float | None
    # diagnostics
    state_changed: bool
    benchmark_close: float | None
    benchmark_sma: float | None

    def __post_init__(self) -> None:
        _require(
            isinstance(self.exposure_multiplier, float)
            and 0.0 <= self.exposure_multiplier <= 1.0,
            OverlayReason.INVALID_FIELD,
            f"exposure_multiplier must be in [0, 1], got {self.exposure_multiplier!r}",
        )
        if not isinstance(self.risk_state, OverlayState):
            raise RiskOverlayError(
                OverlayReason.INVALID_FIELD, f"risk_state={self.risk_state!r}")
        if not isinstance(self.action, OverlayAction):
            raise RiskOverlayError(
                OverlayReason.INVALID_FIELD, f"action={self.action!r}")
        _require(
            isinstance(self.trigger_reason, str) and self.trigger_reason != "",
            OverlayReason.INVALID_FIELD,
            "trigger_reason must be a non-empty code",
        )
        _require(
            isinstance(self.recovery_condition, str) and self.recovery_condition != "",
            OverlayReason.INVALID_FIELD,
            "recovery_condition must be a non-empty code",
        )
        _require(
            self.state_changed is (self.action is not OverlayAction.HOLD),
            OverlayReason.INVALID_FIELD,
            "action must be HOLD iff the state did not change "
            "(prereg: state changes only produce retargets)",
        )
        _require(
            self.drawdown is None or self.high_water_mark is not None,
            OverlayReason.INVALID_FIELD,
            "drawdown requires a high_water_mark",
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready row (``None`` preserved; no display text)."""
        return {
            "config_id": self.config_id,
            "decision_time": self.decision_time.isoformat(),
            "exposure_multiplier": self.exposure_multiplier,
            "risk_state": self.risk_state.value,
            "action": self.action.value,
            "trigger_reason": self.trigger_reason,
            "previous_state": (None if self.previous_state is None
                               else self.previous_state.value),
            "recovery_condition": self.recovery_condition,
            "cooldown_until": (None if self.cooldown_until is None
                               else self.cooldown_until.isoformat()),
            "benchmark_as_of": (None if self.benchmark_as_of is None
                                else self.benchmark_as_of.isoformat()),
            "equity_as_of": (None if self.equity_as_of is None
                             else self.equity_as_of.isoformat()),
            "high_water_mark": self.high_water_mark,
            "drawdown": self.drawdown,
            "state_changed": self.state_changed,
            "benchmark_close": self.benchmark_close,
            "benchmark_sma": self.benchmark_sma,
        }

    def describe(self) -> str:
        """One display line (Chinese), separate from the machine fields."""
        parts = [
            self.decision_time.strftime("%Y-%m-%d %H:%M"),
            self.config_id,
            f"{STATE_LABELS[self.risk_state]}/{ACTION_LABELS[self.action]}",
            f"E={self.exposure_multiplier:.2f}",
            REASON_LABELS[self.trigger_reason],
        ]
        if self.benchmark_close is not None:
            line = f"指数={self.benchmark_close:.2f}"
            if self.benchmark_sma is not None:
                line += f"/均线={self.benchmark_sma:.2f}"
            parts.append(line)
        if self.drawdown is not None:
            parts.append(f"回撤={self.drawdown:.2%}")
        return " | ".join(parts)


# --------------------------------------------------------------------------- #
# plan-layer bridge
# --------------------------------------------------------------------------- #
_PLAN_STATE = {
    OverlayState.NORMAL: RiskState.NORMAL,
    OverlayState.REDUCED: RiskState.CAUTION,
    OverlayState.BLOCKED: RiskState.RISK_OFF,
    OverlayState.INSUFFICIENT_DATA: RiskState.RISK_OFF,
}

_PLAN_ACTION = {
    OverlayAction.HOLD: PlanAction.NO_ACTION,
    # the reduction itself travels in exposure_multiplier; the plan layer
    # still computes attack targets, so no entry gate is raised
    OverlayAction.REDUCE_ATTACK: PlanAction.NO_ACTION,
    OverlayAction.RESTORE_ATTACK: PlanAction.NO_ACTION,
    OverlayAction.BLOCK_NEW_ATTACK: PlanAction.ACCOUNT_DELEVER,
    OverlayAction.FAIL_CLOSED: PlanAction.ACCOUNT_DELEVER,
}

_ENTRY_ALLOWED = {
    OverlayState.NORMAL: True,
    OverlayState.REDUCED: True,
    OverlayState.BLOCKED: False,
    OverlayState.INSUFFICIENT_DATA: False,
}


def to_plan_risk_state(state: OverlayState) -> RiskState:
    """Overlay state -> ``recommendations.RiskState``.

    ``reduced`` maps to ``CAUTION`` (not ``RISK_OFF``) on purpose: the plan
    layer treats ``RISK_OFF`` as *entry blocked*, which would silently turn
    the 0.40 floor into a no-new-entry strategy.
    """
    if not isinstance(state, OverlayState):
        raise RiskOverlayError(
            OverlayReason.INVALID_FIELD, f"state must be an OverlayState, got {state!r}")
    return _PLAN_STATE[state]


def to_plan_account_action(action: OverlayAction) -> PlanAction:
    """Overlay action -> ``recommendations.Action`` (account-level actions)."""
    if not isinstance(action, OverlayAction):
        raise RiskOverlayError(
            OverlayReason.INVALID_FIELD, f"action must be an OverlayAction, got {action!r}")
    return _PLAN_ACTION[action]


def attack_entry_allowed(state: OverlayState) -> bool:
    """Whether new attack entries may be proposed in this state.

    True for ``normal`` and ``reduced`` (prereg §1: the base attack target is
    scaled by ``E_t``, entries stay allowed); false for ``blocked`` (reserved,
    unreachable in C0-C2) and for ``insufficient_data`` (repo rule: stale or
    missing data stops new suggestions).
    """
    if not isinstance(state, OverlayState):
        raise RiskOverlayError(
            OverlayReason.INVALID_FIELD, f"state must be an OverlayState, got {state!r}")
    return _ENTRY_ALLOWED[state]


# --------------------------------------------------------------------------- #
# resolution
# --------------------------------------------------------------------------- #
def _recovery_condition(policy: OverlayPolicy, state: OverlayState) -> str:
    if state is OverlayState.REDUCED or state is OverlayState.BLOCKED:
        if policy.mechanism is GateMechanism.INDEX_SMA:
            return (f"close_gt_sma{policy.sma_sessions}"
                    f"_confirm{policy.recovery_confirmations}"
                    f"_cooldown{policy.cooldown_sessions}")
        if policy.mechanism is GateMechanism.DAILY_LOSS:
            return (f"session_loss_le_{policy.daily_loss_threshold:.2%}"
                    f"_confirm{policy.recovery_confirmations}"
                    f"_cooldown{policy.cooldown_sessions}")
        if policy.mechanism is GateMechanism.PHASE_DRAWDOWN:
            return (f"phase_drawdown_le_rearm_confirm{policy.recovery_confirmations}"
                    f"_cooldown{policy.cooldown_sessions}")
        return (f"drawdown_le_rearm_confirm{policy.recovery_confirmations}"
                f"_cooldown{policy.cooldown_sessions}")
    if state is OverlayState.INSUFFICIENT_DATA:
        return "data_available"
    return "none"


def _advance_streak(
    holds: bool, session_pos: int | None, streak: int, streak_session: int | None
) -> tuple[int, int | None]:
    """Count consecutive qualifying SESSIONS.

    A second decision point that re-reads the same completed session (D 15:00
    then D+1 11:30) keeps the current count; a judged session that was skipped
    restarts it.
    """
    if not holds or session_pos is None:
        return 0, None
    if streak_session is None:
        return 1, session_pos
    if session_pos == streak_session:
        return streak, streak_session
    if session_pos == streak_session + 1:
        return streak + 1, session_pos
    return 1, session_pos


def _cooldown_elapsed(
    session_pos: int | None, lowered_session: int | None, cooldown_sessions: int
) -> bool:
    if lowered_session is None:
        return True
    if session_pos is None:
        return False
    return session_pos - lowered_session >= cooldown_sessions


# --------------------------------------------------------------------------- #
# raw target state + transition (the ONE core both drivers share)
# --------------------------------------------------------------------------- #
#: ``(target state, reason code, recovery condition holds)``.
_Target = tuple[OverlayState, str, bool]


def daily_loss_target(pol: OverlayPolicy, values: Sequence[float],
                      pos: int | None) -> _Target:
    """Target state of ``D1`` from ONE as-of index of the own equity series.

    The first observation establishes the reference (prereg §3 - the same
    convention C2 uses for its first peak), so it carries no measurable loss
    and the recovery condition holds.  A missing observation fails closed.
    """
    if pos is None:
        return OverlayState.INSUFFICIENT_DATA, "equity_observation_missing", False
    if pos <= 0:
        return OverlayState.NORMAL, "daily_loss_within_limit", True
    loss = 1.0 - values[pos] / values[pos - 1]
    if loss > pol.daily_loss_threshold:
        return OverlayState.REDUCED, "daily_loss_beyond_limit", False
    return OverlayState.NORMAL, "daily_loss_within_limit", True


def drawdown_target(pol: OverlayPolicy, pos: int | None, drawdown: float | None,
                    *, phase: bool) -> _Target:
    """Target state of ``D2``/``D3`` from one as-of drawdown observation.

    ``phase`` selects the ``D2`` reason codes (trailing 60-session peak);
    otherwise the ``D3`` high-water codes are used.  Boundaries are the
    registered strict ones: off when ``dd > threshold``, recoverable when
    ``dd <= rearm``.
    """
    if pos is None or drawdown is None:
        return OverlayState.INSUFFICIENT_DATA, "equity_observation_missing", False
    if pol.hard_stop_drawdown is not None and drawdown > pol.hard_stop_drawdown:
        return (OverlayState.BLOCKED, "account_hard_stop_breached",
                drawdown <= pol.rearm)
    if drawdown > pol.drawdown_threshold:
        return (OverlayState.REDUCED,
                "phase_drawdown_beyond_limit" if phase else "drawdown_beyond_limit",
                False)
    return (OverlayState.NORMAL,
            "phase_drawdown_within_limit" if phase else "drawdown_within_limit",
            drawdown <= pol.rearm)


@dataclass(frozen=True)
class _Transition:
    """One decision point's transition outcome (the shared core's result)."""

    state: OverlayState
    action: OverlayAction
    reason: str
    changed: bool
    streak: int
    streak_session: int | None
    lowered_session: int | None


def _transition(
    pol: OverlayPolicy,
    *,
    state: OverlayState | None,
    lowered_session: int | None,
    streak: int,
    streak_session: int | None,
    target: OverlayState,
    recoverable: bool,
    reason: str,
    session_pos: int | None,
) -> _Transition:
    """Down-shift immediate, up-shift gated (confirmations + cooldown).

    The single implementation used by both :func:`resolve_overlay` (batch
    as-of resolution) and :class:`AccountRiskDynamics` (live-ledger
    increment), so the two drivers cannot drift apart.
    """
    changed = False
    if target is OverlayState.INSUFFICIENT_DATA:
        changed = state is not OverlayState.INSUFFICIENT_DATA
        state = OverlayState.INSUFFICIENT_DATA
        action = OverlayAction.FAIL_CLOSED if changed else OverlayAction.HOLD
        streak, streak_session = 0, None
    elif target is OverlayState.BLOCKED:
        changed = state is not OverlayState.BLOCKED
        if changed:
            state = OverlayState.BLOCKED
            lowered_session = session_pos
            streak, streak_session = 0, None
        else:
            streak, streak_session = _advance_streak(
                recoverable, session_pos, streak, streak_session)
        action = OverlayAction.BLOCK_NEW_ATTACK if changed else OverlayAction.HOLD
    elif target is OverlayState.REDUCED:
        changed = state is not OverlayState.REDUCED
        if changed:
            state = OverlayState.REDUCED
            lowered_session = session_pos
        action = OverlayAction.REDUCE_ATTACK if changed else OverlayAction.HOLD
        streak, streak_session = 0, None
    elif state is OverlayState.NORMAL or state is None:
        state = OverlayState.NORMAL
        action = OverlayAction.HOLD
        changed = False
        streak, streak_session = 0, None
    else:  # target normal, currently reduced / blocked / insufficient_data
        streak, streak_session = _advance_streak(
            recoverable, session_pos, streak, streak_session)
        if state is OverlayState.INSUFFICIENT_DATA:
            # a data gap is not a risk trigger: restoring it starts no
            # cooldown and needs no confirmation
            state = OverlayState.NORMAL
            action = OverlayAction.RESTORE_ATTACK
            changed = True
            streak, streak_session = 0, None
        elif not _cooldown_elapsed(session_pos, lowered_session,
                                   pol.cooldown_sessions):
            action = OverlayAction.HOLD
            changed = False
            reason = "recovery_pending_cooldown"
        elif streak < pol.recovery_confirmations:
            action = OverlayAction.HOLD
            changed = False
            reason = "recovery_pending_confirmation"
        else:
            state = OverlayState.NORMAL
            action = OverlayAction.RESTORE_ATTACK
            changed = True
            lowered_session = None
            streak, streak_session = 0, None
        if action is OverlayAction.RESTORE_ATTACK:
            reason = "recovery_confirmed"
    return _Transition(state, action, reason, changed, streak, streak_session,
                       lowered_session)


def insufficient_data_rows(
    rows: Sequence[OverlayDecision],
) -> tuple[OverlayDecision, ...]:
    """Rows whose state is :attr:`OverlayState.INSUFFICIENT_DATA`.

    The C1 lookback guard: a benchmark series that starts at the first decision
    point yields ``sma_sessions - 1`` such rows at ``level_off``, which the plan
    layer reads as risk-off and would distort the C1-vs-C0 comparison.  A
    runner must assert this is empty (or explain each row) before accepting a
    C1 run.
    """
    return tuple(row for row in rows
                 if row.risk_state is OverlayState.INSUFFICIENT_DATA)


def resolve_overlay(
    decision_times: Sequence[dt.date | dt.datetime],
    *,
    config_id: str = C0,
    policy: OverlayPolicy | None = None,
    decision_points: Sequence[DecisionPoint] | None = None,
    benchmark_close: Sequence[tuple[dt.date, float]] | None = None,
    equity: Sequence[tuple[dt.date, float]] | None = None,
) -> tuple[OverlayDecision, ...]:
    """Resolve the frozen overlay into one row per decision point.

    ``decision_times`` must be strictly increasing.  ``benchmark_close`` is the
    000300 close series (required by ``C1``; it must carry at least
    ``sma_sessions`` sessions *before* the first decision point - see the module
    docstring) and ``equity`` the confirmed account equity series (required by
    ``C2``); both are read asof only.  ``decision_points`` optionally names each
    decision's registered :class:`~quant.portfolio.recommendations.DecisionPoint`
    (``DAY0_CLOSE`` / ``AM_1130`` / ``PM_1500``, same length as
    ``decision_times``); without it the point is derived from the clock time by
    :func:`decision_point_of`.  Pass ``policy`` only for an explicitly
    off-prereg variant; its ``config_id`` must match ``config_id``.

    The recovery and cooldown counters are denominated in judged **sessions**,
    so an 11:30 row re-reading the previous close neither advances nor resets
    them.  Rows carry one decision's worth of a target multiplier only: no
    orders, no fills, no account mutation.
    """
    if policy is None:
        pol = (policy_for(config_id) if config_id in POLICIES
               else dynamic_policy_for(config_id))
    else:
        pol = policy
        _require(
            pol.config_id == config_id,
            OverlayReason.CONFIG_POLICY_MISMATCH,
            f"policy.config_id={pol.config_id!r} but config_id={config_id!r}",
        )

    if pol.mechanism is GateMechanism.INDEX_SMA:
        _require(
            benchmark_close is not None,
            OverlayReason.MISSING_BENCHMARK_SERIES,
            f"{pol.config_id} requires the benchmark close series",
        )
    if pol.mechanism in (GateMechanism.ACCOUNT_DRAWDOWN,
                         GateMechanism.PHASE_DRAWDOWN,
                         GateMechanism.DAILY_LOSS):
        _require(
            equity is not None,
            OverlayReason.MISSING_EQUITY_SERIES,
            f"{pol.config_id} requires the account equity series",
        )

    moments = [_as_datetime(t, "decision_time") for t in decision_times]
    for i in range(1, len(moments)):
        _require(
            moments[i] > moments[i - 1],
            OverlayReason.DECISION_TIMES_NOT_INCREASING,
            f"decision_times must strictly increase; {moments[i]} follows {moments[i - 1]}",
        )
    if decision_points is None:
        points = [decision_point_of(moment) for moment in moments]
    else:
        _require(
            len(decision_points) == len(moments),
            OverlayReason.INVALID_FIELD,
            f"decision_points has {len(decision_points)} entries for "
            f"{len(moments)} decision times",
        )
        try:
            points = [DecisionPoint(point) for point in decision_points]
        except ValueError as exc:
            raise RiskOverlayError(
                OverlayReason.INVALID_FIELD,
                f"decision_points must be DecisionPoint values: {exc}",
            ) from exc

    bench_dates: list[dt.date] | None = None
    bench_closes: list[float] | None = None
    smas: list[float | None] = []
    if benchmark_close is not None:
        bench_dates, bench_closes = _series(benchmark_close, "benchmark_close")
        smas = _rolling_sma(bench_closes, pol.sma_sessions)

    dd_by_date: dict[dt.date, tuple[float, float]] | None = None
    dd_dates: list[dt.date] = []
    equity_values: list[float] = []
    if equity is not None:
        equity_values = [value for _day, value in equity]
        dd_by_date = (running_phase_drawdown(equity, pol.phase_sessions)
                      if pol.mechanism is GateMechanism.PHASE_DRAWDOWN
                      else running_peak_drawdown(equity))
        dd_dates = list(dd_by_date)

    # the series whose sessions denominates the recovery / cooldown counters
    driver: list[dt.date] | None = None
    if pol.mechanism is GateMechanism.INDEX_SMA:
        driver = bench_dates
    elif pol.mechanism in (GateMechanism.ACCOUNT_DRAWDOWN,
                           GateMechanism.PHASE_DRAWDOWN,
                           GateMechanism.DAILY_LOSS):
        driver = dd_dates
    else:
        driver = bench_dates if bench_dates is not None else dd_dates

    rows: list[OverlayDecision] = []
    state: OverlayState | None = None
    lowered_session: int | None = None
    streak = 0
    streak_session: int | None = None

    for i, moment in enumerate(moments):
        previous = state
        point = points[i]
        bench_pos = (None if bench_dates is None else
                     _asof_pos(bench_dates, trading_day=moment.date(),
                               decision_point=point))
        equity_pos = (None if dd_by_date is None else
                      _asof_pos(dd_dates, trading_day=moment.date(),
                                decision_point=point))
        bench_as_of = None if bench_pos is None else bench_dates[bench_pos]
        equity_as_of = None if equity_pos is None else dd_dates[equity_pos]
        session_pos = (bench_pos if pol.mechanism is GateMechanism.INDEX_SMA
                       else equity_pos if pol.mechanism is GateMechanism.ACCOUNT_DRAWDOWN
                       else bench_pos if bench_pos is not None else equity_pos)

        bench_close: float | None = None
        sma: float | None = None
        if bench_pos is not None:
            bench_close = bench_closes[bench_pos]
            sma = smas[bench_pos]

        hwm: float | None = None
        drawdown: float | None = None
        if equity_pos is not None:
            hwm, drawdown = dd_by_date[dd_dates[equity_pos]]

        # -- raw target state -------------------------------------------------
        recoverable = False
        if pol.mechanism is GateMechanism.CONSTANT:
            target, reason = OverlayState.NORMAL, "control_constant_exposure"
        elif pol.mechanism is GateMechanism.INDEX_SMA:
            if bench_as_of is None:
                target, reason = (OverlayState.INSUFFICIENT_DATA,
                                  "benchmark_observation_missing")
            elif sma is None:
                target, reason = OverlayState.INSUFFICIENT_DATA, "sma_warmup_incomplete"
            elif bench_close > sma:
                target, reason = OverlayState.NORMAL, "index_above_trend_sma"
                recoverable = True
            else:
                target, reason = OverlayState.REDUCED, "index_at_or_below_trend_sma"
        elif pol.mechanism is GateMechanism.DAILY_LOSS:
            target, reason, recoverable = daily_loss_target(
                pol, equity_values, equity_pos)
        elif pol.mechanism is GateMechanism.PHASE_DRAWDOWN:
            target, reason, recoverable = drawdown_target(
                pol, equity_pos, drawdown, phase=True)
        else:
            target, reason, recoverable = drawdown_target(
                pol, equity_pos, drawdown, phase=False)

        # -- transition (down-shift immediate, up-shift gated) ----------------
        step = _transition(
            pol, state=state, lowered_session=lowered_session, streak=streak,
            streak_session=streak_session, target=target,
            recoverable=recoverable, reason=reason, session_pos=session_pos)
        state, action, reason = step.state, step.action, step.reason
        changed, streak = step.changed, step.streak
        streak_session = step.streak_session
        lowered_session = step.lowered_session

        cooldown_until: dt.date | None = None
        if (state is OverlayState.REDUCED or state is OverlayState.BLOCKED) \
                and lowered_session is not None and driver is not None:
            boundary = lowered_session + pol.cooldown_sessions
            if boundary < len(driver):
                cooldown_until = driver[boundary]

        rows.append(OverlayDecision(
            config_id=pol.config_id,
            decision_time=moment,
            exposure_multiplier=(pol.level_on if state is OverlayState.NORMAL
                                 else pol.level_off),
            risk_state=state,
            action=action,
            trigger_reason=reason,
            previous_state=previous,
            recovery_condition=_recovery_condition(pol, state),
            cooldown_until=cooldown_until,
            benchmark_as_of=bench_as_of,
            equity_as_of=equity_as_of,
            high_water_mark=hwm,
            drawdown=drawdown,
            state_changed=changed,
            benchmark_close=bench_close,
            benchmark_sma=sma,
        ))

    return tuple(rows)


# --------------------------------------------------------------------------- #
# incremental ledger-driven machine (dynamic replay)
# --------------------------------------------------------------------------- #
class AccountRiskDynamics:
    """Incremental account-feedback state machine over ONE live ledger.

    Built for ``run_band_backtest_intents(..., intent_provider=...)``: the
    host feeds this account's **own completed closes** (``observe_close``,
    called at 15:00-class decision points with the ledger's equity snapshot)
    and asks for one row per decision point (``step``).  Nothing here reads a
    control arm, an index, a fill or an order - a row is a target multiplier
    plus its trigger diagnostics, never a trade.

    Registered semantics (prereg ``exp-20260921-account-risk-dynamic`` §3):

    * **as-of** rides the same table as :func:`close_asof`: a 15:00-class
      point reads that trading day's close, an ``AM_1130`` point may only read
      the previous completed session (so an 11:30 row repeats the previous
      row's state, asof, drawdown and exposure).
    * **counters are session-denominated**: they advance only when the asof
      session moves, so an 11:30 re-read neither advances nor resets the
      confirmations / cooldown.
    * **``cooldown_until`` is published only once that session has already
      been observed** (an increment cannot name a future date); the counters
      that gate the restore are exact regardless.
    * **both exposure levels and the recovery gate** come from
      :data:`DYNAMIC_POLICIES`; the transition itself is the shared
      :func:`_transition`, so this driver and :func:`resolve_overlay` cannot
      diverge.
    """

    def __init__(self, config_id: str = D0) -> None:
        self._policy = dynamic_policy_for(config_id)
        self._dates: list[dt.date] = []
        self._values: list[float] = []
        self._rows: list[OverlayDecision] = []
        self._state: OverlayState | None = None
        self._lowered_session: int | None = None
        self._streak = 0
        self._streak_session: int | None = None
        self._last_key: tuple[dt.date, int] | None = None

    # -- state ---------------------------------------------------------------
    @property
    def policy(self) -> OverlayPolicy:
        return self._policy

    @property
    def config_id(self) -> str:
        return self._policy.config_id

    @property
    def observations(self) -> tuple[tuple[dt.date, float], ...]:
        """Completed closes fed so far, oldest first."""
        return tuple(zip(self._dates, self._values))

    @property
    def rows(self) -> tuple[OverlayDecision, ...]:
        """Every row emitted so far, decision-point order."""
        return tuple(self._rows)

    # -- input ---------------------------------------------------------------
    def observe_close(self, trading_day: dt.date, equity: float) -> None:
        """Record ONE completed close (a 15:00-class decision's equity).

        Dates must strictly increase: two 15:00-class decisions for the same
        trading day would double-count the session in the recovery counters.
        """
        _require(
            isinstance(trading_day, dt.date)
            and not isinstance(trading_day, dt.datetime),
            OverlayReason.INVALID_FIELD,
            f"trading_day must be a datetime.date, got {trading_day!r}",
        )
        _require(
            isinstance(equity, (int, float)) and not isinstance(equity, bool)
            and float(equity) == float(equity) and abs(float(equity)) != float("inf")
            and float(equity) > 0.0,
            OverlayReason.INVALID_FIELD,
            f"equity must be a finite positive number, got {equity!r}",
        )
        if self._dates:
            _require(
                trading_day > self._dates[-1],
                OverlayReason.SERIES_NOT_INCREASING,
                f"equity observations must strictly increase; {trading_day} "
                f"follows {self._dates[-1]}",
            )
        self._dates.append(trading_day)
        self._values.append(float(equity))

    # -- one decision point ---------------------------------------------------
    def step(
        self,
        trading_day: dt.date,
        *,
        decision_point: DecisionPoint | None = None,
        decision_time: dt.datetime | None = None,
    ) -> OverlayDecision:
        """Resolve this decision point from the closes observed so far.

        ``decision_point`` defaults to the registered point of
        ``decision_time`` (or ``PM_1500``); callers that know their point (the
        half-day loop) should pass it explicitly, exactly as
        :func:`resolve_overlay` does.
        """
        _require(
            isinstance(trading_day, dt.date)
            and not isinstance(trading_day, dt.datetime),
            OverlayReason.INVALID_FIELD,
            f"trading_day must be a datetime.date, got {trading_day!r}",
        )
        if decision_point is None:
            if decision_time is None:
                point = DecisionPoint.PM_1500
            else:
                point = decision_point_of(decision_time)
        else:
            try:
                point = DecisionPoint(decision_point)
            except ValueError as exc:
                raise RiskOverlayError(
                    OverlayReason.INVALID_FIELD,
                    f"decision_point must be a DecisionPoint: {exc}") from exc
        session = Session.PM if point in SAME_DAY_CLOSE_POINTS else Session.AM
        key = (trading_day, 0 if session is Session.AM else 1)
        _require(
            self._last_key is None or key > self._last_key,
            OverlayReason.DECISION_TIMES_NOT_INCREASING,
            f"decision points must strictly increase; {key} follows "
            f"{self._last_key}",
        )
        self._last_key = key
        moment = (decision_time if decision_time is not None
                  else dt.datetime.combine(trading_day, SESSION_BOUNDS[session][1]))

        pol = self._policy
        previous = self._state
        pos = _asof_pos(self._dates, trading_day=trading_day,
                        decision_point=point)
        equity_as_of = None if pos is None else self._dates[pos]
        hwm: float | None = None
        drawdown: float | None = None
        if pos is not None:
            window = (pol.phase_sessions
                      if pol.mechanism is GateMechanism.PHASE_DRAWDOWN else None)
            hwm = (max(self._values[:pos + 1]) if window is None
                   else max(self._values[max(0, pos - window + 1):pos + 1]))
            drawdown = 1.0 - self._values[pos] / hwm
        recoverable = False
        if pol.mechanism is GateMechanism.CONSTANT:
            target, reason = OverlayState.NORMAL, "control_constant_exposure"
        elif pol.mechanism is GateMechanism.DAILY_LOSS:
            target, reason, recoverable = daily_loss_target(pol, self._values, pos)
        elif pol.mechanism is GateMechanism.PHASE_DRAWDOWN:
            target, reason, recoverable = drawdown_target(
                pol, pos, drawdown, phase=True)
        else:
            target, reason, recoverable = drawdown_target(
                pol, pos, drawdown, phase=False)

        step = _transition(
            pol, state=self._state, lowered_session=self._lowered_session,
            streak=self._streak, streak_session=self._streak_session,
            target=target, recoverable=recoverable, reason=reason,
            session_pos=pos)
        self._state = step.state
        self._streak = step.streak
        self._streak_session = step.streak_session
        self._lowered_session = step.lowered_session

        cooldown_until: dt.date | None = None
        if (step.state is OverlayState.REDUCED
                or step.state is OverlayState.BLOCKED) \
                and self._lowered_session is not None:
            boundary = self._lowered_session + pol.cooldown_sessions
            if boundary < len(self._dates):
                cooldown_until = self._dates[boundary]

        row = OverlayDecision(
            config_id=pol.config_id,
            decision_time=moment,
            exposure_multiplier=(pol.level_on
                                 if step.state is OverlayState.NORMAL
                                 else pol.level_off),
            risk_state=step.state,
            action=step.action,
            trigger_reason=step.reason,
            previous_state=previous,
            recovery_condition=_recovery_condition(pol, step.state),
            cooldown_until=cooldown_until,
            benchmark_as_of=None,
            equity_as_of=equity_as_of,
            high_water_mark=hwm,
            drawdown=drawdown,
            state_changed=step.changed,
            benchmark_close=None,
            benchmark_sma=None,
        )
        self._rows.append(row)
        return row
