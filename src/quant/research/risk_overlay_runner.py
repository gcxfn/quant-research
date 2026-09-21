"""Derived runner contract for applying the account risk overlay to intents.

This module is deliberately separate from historical experiment runners.  It
owns only the bridge between ``risk_overlay`` rows and the band-engine intent
frame.  It does not alter historical artifacts and it does not turn a static
equity path into a claim of dynamic C2 replay.

The base F3R2 intent weights are registered at ``E=0.90``.  Therefore the
overlay is applied as ``E / 0.90``.  C0 consequently has an exact identity
mapping and is a useful parity control.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date, datetime, time
from math import isfinite
from typing import Iterable, Mapping, Sequence

import polars as pl

from quant.backtest.band_engine import BandResult, run_band_backtest_intents
from quant.portfolio import risk_overlay as ro
from quant.portfolio.recommendations import DecisionPoint


BASE_EXPOSURE = ro.LEVEL_ON
_REQUIRED = {
    "symbol", "side", "intent", "decision_date", "decision_session",
    "source_signal", "priority",
}


class OverlayRunnerError(ValueError):
    """Input or replay-contract error."""


@dataclass(frozen=True)
class OverlayReplayPlan:
    """Resolved overlay rows and the derived intent frame.

    ``dynamic_equity_required`` is true for C2.  A caller may inspect or pass
    the plan onward, but must provide equity from a preceding real ledger
    segment before treating it as a dynamic replay.
    """

    config_id: str
    overlay_rows: tuple[ro.OverlayDecision, ...]
    intents: pl.DataFrame
    dynamic_equity_required: bool
    reissued_decisions: int


@dataclass(frozen=True)
class C0ParityReport:
    """Machine-readable result of the C0 control harness."""

    frame_equal: bool
    result_equal: bool | None
    compared_frames: tuple[str, ...]


def _check_frame(frame: pl.DataFrame) -> None:
    missing = sorted(_REQUIRED - set(frame.columns))
    if missing:
        raise OverlayRunnerError(
            f"intents missing required columns: {', '.join(missing)}")
    if frame.is_empty():
        raise OverlayRunnerError("intents must not be empty")
    if frame.schema["decision_date"] != pl.Date:
        raise OverlayRunnerError("intents.decision_date must be Date")
    if frame.schema["source_signal"] != pl.Date:
        raise OverlayRunnerError("intents.source_signal must be Date")


def decision_times_from_intents(intents: pl.DataFrame) -> tuple[datetime, ...]:
    """Return unique decision timestamps represented by an intent frame."""
    _check_frame(intents)
    rows = intents.select("decision_date", "decision_session").unique(
        maintain_order=False).sort("decision_date", "decision_session")
    out: list[datetime] = []
    for row in rows.iter_rows(named=True):
        clock = time(11, 30) if row["decision_session"] == "am" else time(15)
        if row["decision_session"] not in {"am", "pm"}:
            raise OverlayRunnerError(
                f"invalid decision_session {row['decision_session']!r}")
        out.append(datetime.combine(row["decision_date"], clock))
    return tuple(out)


def resolve_overlay_rows(
    decision_times: Sequence[date | datetime],
    *,
    config_id: str,
    benchmark_close: Sequence[tuple[date, float]] | None = None,
    equity: Sequence[tuple[date, float]] | None = None,
    decision_points: Sequence[object] | None = None,
) -> tuple[ro.OverlayDecision, ...]:
    """Resolve the frozen overlay with the registered as-of machinery."""
    return ro.resolve_overlay(
        decision_times,
        config_id=config_id,
        benchmark_close=benchmark_close,
        equity=equity,
        decision_points=decision_points,
    )


def _overlay_ratio(row: ro.OverlayDecision, baseline: float) -> float:
    if baseline <= 0 or not isfinite(baseline):
        raise OverlayRunnerError("baseline exposure must be finite and > 0")
    ratio = row.exposure_multiplier / baseline
    if not isfinite(ratio) or ratio < 0:
        raise OverlayRunnerError(f"invalid overlay ratio {ratio!r}")
    return ratio


def _scaled(value: object, ratio: float) -> float | None:
    if value is None:
        return None
    number = float(value)
    if not isfinite(number) or number < 0:
        raise OverlayRunnerError(f"target_weight must be finite and >= 0, got {value!r}")
    return number * ratio


def apply_overlay_to_intents(
    base_intents: pl.DataFrame,
    overlay_rows: Sequence[ro.OverlayDecision],
    *,
    attack_symbols: Iterable[str],
    baseline_exposure: float = BASE_EXPOSURE,
    reissue_active_targets: bool = True,
) -> tuple[pl.DataFrame, int]:
    """Scale attack targets and add valid later decision-point overrides.

    Full exits (``target_weight is null``) remain full exits.  For an active
    target whose overlay changes between monthly decisions, a later intent is
    emitted at that decision point.  This is a target override consumed by the
    engine; it is not a fill assumption.
    """
    _check_frame(base_intents)
    attack = set(attack_symbols)
    ordered = sorted(overlay_rows, key=lambda r: r.decision_time)
    if not ordered:
        raise OverlayRunnerError("overlay_rows must not be empty")
    base_rows = base_intents.to_dicts()
    base_rows.sort(key=lambda r: (r["decision_date"], r["decision_session"],
                                 r["symbol"], r["side"], r["source_signal"]))
    point_for_key = {(r.decision_time.date(),
                      "am" if r.decision_time.time() <= time(11, 30) else "pm"): r
                     for r in ordered}
    overlay_keys = set(point_for_key)
    rows_by_key = {(r["decision_date"], r["decision_session"]): r
                   for r in base_rows}
    active: dict[str, dict] = {}
    output: list[dict] = []
    cursor = 0
    reissued = 0

    def apply_row(row: dict, ratio: float) -> dict:
        copy = dict(row)
        if copy["symbol"] in attack:
            copy["target_weight"] = _scaled(copy.get("target_weight"), ratio)
        return copy

    # First preserve every original intent, scaling it at its own decision
    # point when an overlay row exists there.
    for row in base_rows:
        key = (row["decision_date"], row["decision_session"])
        overlay = point_for_key.get(key)
        ratio = 1.0 if overlay is None else _overlay_ratio(overlay, baseline_exposure)
        scaled = apply_row(row, ratio)
        output.append(scaled)
        if row["symbol"] in attack:
            if row.get("target_weight") is None:
                active.pop(row["symbol"], None)
            else:
                # Keep the registered base target. Reapplying an overlay to an
                # already-scaled value would compound E at every reissue.
                active[row["symbol"]] = dict(row)

    if reissue_active_targets:
        # Reconstruct active targets at each overlay point.  A row past its
        # expiry is not re-hung; the engine's expiry semantics remain in force.
        for overlay in ordered:
            key = (overlay.decision_time.date(),
                   "am" if overlay.decision_time.time() <= time(11, 30) else "pm")
            if key in rows_by_key:
                continue
            for row in base_rows:
                row_key = (row["decision_date"], row["decision_session"])
                if row_key <= key and row["symbol"] in attack:
                    if row.get("target_weight") is None:
                        active.pop(row["symbol"], None)
                    else:
                        # Keep the source target unscaled here.  The synthetic
                        # override below applies the current ratio exactly
                        # once; storing an already scaled row would compound
                        # the reduction on every later decision point.
                        active[row["symbol"]] = dict(row)
            for symbol, current in sorted(active.items()):
                expiry = current.get("expiry_date")
                if expiry is not None and expiry < overlay.decision_time.date():
                    continue
                ratio = _overlay_ratio(overlay, baseline_exposure)
                target = _scaled(current.get("target_weight"), ratio)
                if target is None:
                    continue
                synthetic = dict(current)
                synthetic["decision_date"] = overlay.decision_time.date()
                synthetic["decision_session"] = key[1]
                synthetic["source_signal"] = overlay.decision_time.date()
                synthetic["target_weight"] = target
                output.append(synthetic)
                reissued += 1

    result = pl.DataFrame(output, schema=base_intents.schema).sort(
        "decision_date", "decision_session", "symbol", "side", "source_signal")
    return result, reissued


def make_replay_plan(
    base_intents: pl.DataFrame,
    *,
    config_id: str,
    attack_symbols: Iterable[str],
    decision_times: Sequence[date | datetime] | None = None,
    benchmark_close: Sequence[tuple[date, float]] | None = None,
    equity: Sequence[tuple[date, float]] | None = None,
    decision_points: Sequence[object] | None = None,
    baseline_exposure: float = BASE_EXPOSURE,
) -> OverlayReplayPlan:
    """Build a derived overlay plan without running the execution engine."""
    _check_frame(base_intents)
    times = (tuple(decision_times) if decision_times is not None
             else decision_times_from_intents(base_intents))
    rows = resolve_overlay_rows(
        times, config_id=config_id, benchmark_close=benchmark_close,
        equity=equity, decision_points=decision_points)
    intents, reissued = apply_overlay_to_intents(
        base_intents, rows, attack_symbols=attack_symbols,
        baseline_exposure=baseline_exposure,
        reissue_active_targets=True,
    )
    return OverlayReplayPlan(
        config_id=config_id, overlay_rows=tuple(rows), intents=intents,
        dynamic_equity_required=config_id == ro.C2,
        reissued_decisions=reissued,
    )


def run_overlay_backtest(
    plan: OverlayReplayPlan,
    *,
    dynamic_equity_confirmed: bool = False,
    **engine_kwargs,
) -> BandResult:
    """Run the derived intent frame through the unchanged band engine.

    This one-shot entry cannot verify iterative equity feedback. C2 is
    rejected even if the legacy confirmation flag is true; a boolean is not
    evidence that risk decisions use this run's executed ledger.
    """
    if plan.config_id == ro.C2 or plan.dynamic_equity_required:
        raise OverlayRunnerError(
            "C2 requires iterative ledger feedback; the one-shot runner "
            "cannot validate it through a confirmation flag")
    return run_band_backtest_intents(plan.intents, **engine_kwargs)


def run_c0_parity_harness(
    base_intents: pl.DataFrame,
    *,
    attack_symbols: Iterable[str],
    reference: BandResult | None = None,
    **engine_kwargs,
) -> tuple[BandResult, C0ParityReport]:
    """Run C0 and prove the derived frame/result equal the control."""
    plan = make_replay_plan(
        base_intents, config_id=ro.C0, attack_symbols=attack_symbols)
    frame_equal = plan.intents.equals(base_intents.sort(
        "decision_date", "decision_session", "symbol", "side", "source_signal"))
    if not frame_equal:
        raise OverlayRunnerError("C0 overlay changed the registered intent frame")
    result = run_overlay_backtest(plan, **engine_kwargs)
    compared = ("fills", "events", "daily", "clips_final")
    result_equal = None
    if reference is not None:
        result_equal = all(getattr(result, name).equals(getattr(reference, name))
                           for name in compared)
        if not result_equal:
            raise OverlayRunnerError("C0 engine outputs are not parity-equal")
    return result, C0ParityReport(frame_equal, result_equal, compared)


# --------------------------------------------------------------------------- #
# dynamic replay host driver (prereg exp-20260921 §4)
# --------------------------------------------------------------------------- #
#: Carrier seat weight at ``E = 0.90``: F3R3's registered entry target.  The
#: overlay scales it by ``E_t / E_base`` and nothing else.
BASE_ATTACK_WEIGHT = 0.10
#: Weight band (fraction of account equity) inside which no resize leg is sent.
RESIZE_TOLERANCE = 0.005


def _dint_of(day: date) -> int:
    return day.year * 10_000 + day.month * 100 + day.day


def _dint_series(column: pl.Series) -> list[int]:
    return [int(v) for v in column.dt.year().cast(pl.Int64) * 10_000
            + column.dt.month().cast(pl.Int64) * 100
            + column.dt.day().cast(pl.Int64)]


class LedgerMarks:
    """Decision-point marks replicated from the engine's own valuation rules.

    Under ``execution_clock='halfday'`` the engine marks a held symbol at the
    completed am close for an 11:30 decision and at the last official close
    on/before the day for a 15:00 decision (a symbol suspended today keeps its
    last traded close).  The host must size a top-up leg on the same numbers,
    so they are recomputed here and then *proven*: :meth:`reconcile` has to
    reproduce the engine's ``ledger['equity_snapshot']`` from cash + pending
    buckets + marked positions, and the run stops otherwise.
    """

    def __init__(self, daily: pl.DataFrame, halfday: pl.DataFrame) -> None:
        for column in ("symbol", "date", "close"):
            if column not in daily.columns:
                raise OverlayRunnerError(f"daily is missing required column {column!r}")
        for column in ("symbol", "trade_date", "session", "close"):
            if column not in halfday.columns:
                raise OverlayRunnerError(
                    f"halfday is missing required column {column!r}")
        trading = (daily.filter(pl.col("tradestatus") != 0)
                   if "tradestatus" in daily.columns else daily)
        self._dint: dict[str, list[int]] = {}
        self._close: dict[str, list[float]] = {}
        for (symbol,), group in trading.sort("symbol", "date").partition_by(
                "symbol", as_dict=True).items():
            self._dint[str(symbol)] = _dint_series(group["date"])
            self._close[str(symbol)] = [float(v) for v in group["close"]]
        self._am: dict[str, dict[int, float]] = {}
        for (symbol,), group in (halfday.filter(pl.col("session") == "am")
                                 .sort("symbol", "trade_date")
                                 .partition_by("symbol", as_dict=True).items()):
            self._am[str(symbol)] = {
                d: float(c) for d, c in
                zip(_dint_series(group["trade_date"]), group["close"])}

    def mark(self, symbol: str, day: date, session: str) -> float | None:
        """Mark of ``symbol`` at this decision point, or ``None`` if unpriced."""
        if session == "am":
            completed = self._am.get(symbol, {}).get(_dint_of(day))
            if completed is not None:
                return completed
        return self._close_on_or_before(symbol, day, strict=session == "am")

    def _close_on_or_before(self, symbol: str, day: date, *,
                            strict: bool) -> float | None:
        dints = self._dint.get(symbol)
        if not dints:
            return None
        key = _dint_of(day)
        pos = (bisect.bisect_left(dints, key) - 1 if strict
               else bisect.bisect_right(dints, key) - 1)
        return None if pos < 0 else self._close[symbol][pos]

    def reconcile(self, ledger: Mapping[str, object], *,
                  tolerance: float = 1e-9) -> float:
        """Recompute ``ledger['equity_snapshot']``; raise on any mismatch."""
        day = ledger["date"]
        session = str(ledger["session"])
        mv = 0.0
        for position in ledger["positions"]:
            mark = self.mark(str(position["symbol"]), day, session)
            if mark is not None:
                mv += int(position["shares"]) * mark
        equity = (float(ledger["cash"]) + float(ledger["pending_am_to_pm"])
                  + float(ledger["pending_next_day"]) + mv)
        snapshot = float(ledger["equity_snapshot"])
        if abs(equity - snapshot) > tolerance * max(1.0, abs(snapshot)):
            raise OverlayRunnerError(
                "ledger marks do not reconcile with the engine snapshot at "
                f"{day} {session}: host {equity:.6f} vs engine {snapshot:.6f}")
        return equity


@dataclass(frozen=True)
class DynamicStep:
    """One decision point's host verdict: targets and diagnostics, no fills."""

    decision_time: datetime
    risk_state: str
    action: str
    exposure_multiplier: float
    ratio: float
    equity: float
    high_water_mark: float | None
    drawdown: float | None
    trigger_reason: str
    cooldown_until: date | None
    target_weight: float
    weights: Mapping[str, float | None]
    entry_symbols: tuple[str, ...]
    trim_symbols: tuple[str, ...]
    topup_symbols: tuple[str, ...]
    pending_restore: tuple[str, ...]
    rows: tuple[dict, ...]

    def as_dict(self) -> dict:
        """JSON-ready trace row."""
        return {
            "decision_time": self.decision_time.isoformat(),
            "risk_state": self.risk_state,
            "action": self.action,
            "exposure_multiplier": self.exposure_multiplier,
            "ratio": self.ratio,
            "equity": self.equity,
            "high_water_mark": self.high_water_mark,
            "drawdown": self.drawdown,
            "trigger_reason": self.trigger_reason,
            "cooldown_until": (None if self.cooldown_until is None
                               else self.cooldown_until.isoformat()),
            "target_weight": self.target_weight,
            "weights": {k: v for k, v in sorted(self.weights.items())},
            "entry_symbols": list(self.entry_symbols),
            "trim_symbols": list(self.trim_symbols),
            "topup_symbols": list(self.topup_symbols),
            "pending_restore": sorted(self.pending_restore),
            "rows": len(self.rows),
        }


class DynamicOverlayHost:
    """Ledger -> overlay rows: one row per decision point, four frozen curves.

    ``D0`` is the parity anchor: it never leaves ``normal``, so no trim and no
    top-up leg is ever emitted and the carrier's intent stream is unchanged.
    ``D1``/``D2``/``D3`` add (a) a proportional trim to ``W_off`` while
    reduced, re-issued every decision point as a half-day limit order that
    assumes no fill, and (b) a delta top-up back to ``W_on`` while a restore
    is pending.  Nothing here reads a control arm: the state comes from this
    ledger's own ``equity_snapshot`` only (prereg §3).
    """

    def __init__(
        self,
        config_id: str,
        marks: LedgerMarks,
        *,
        base_weight: float = BASE_ATTACK_WEIGHT,
        baseline_exposure: float = BASE_EXPOSURE,
        tolerance: float = RESIZE_TOLERANCE,
        trim_intent: str = "risk",
    ) -> None:
        if not isfinite(baseline_exposure) or baseline_exposure <= 0:
            raise OverlayRunnerError("baseline_exposure must be finite and > 0")
        if not isfinite(base_weight) or base_weight <= 0:
            raise OverlayRunnerError("base_weight must be finite and > 0")
        if not isfinite(tolerance) or tolerance < 0:
            raise OverlayRunnerError("tolerance must be finite and >= 0")
        if trim_intent not in ("risk", "profit"):
            raise OverlayRunnerError(
                "trim_intent must be 'risk' (AGENTS fallback caliber) or "
                f"'profit' (legacy expire-void caliber), got {trim_intent!r}")
        self.machine = ro.AccountRiskDynamics(config_id)
        self.marks = marks
        self.base_weight = float(base_weight)
        self.baseline_exposure = float(baseline_exposure)
        self.tolerance = float(tolerance)
        # AGENTS §1: risk-reduction legs are 'risk' (K=3 open fallback carries
        # the explicit partial quantity, band_engine M1); 'profit' keeps the
        # task-1 legacy expire-void caliber for reproduction checks only.
        self.trim_intent = trim_intent
        self._pending_restore: set[str] = set()
        self.steps: list[DynamicStep] = []

    @property
    def config_id(self) -> str:
        return self.machine.config_id

    @staticmethod
    def _priority(rank_of: Mapping[str, int], symbol: str) -> int:
        try:
            return int(rank_of[symbol])
        except KeyError as exc:
            raise OverlayRunnerError(
                f"rank_of has no entry for {symbol!r}") from exc

    @staticmethod
    def _row(symbol: str, side: str, *, day: date, session: str,
             source: date, priority: int, expiry: date | None,
             intent: str = "", target_weight: float | None = None,
             target_notional: float | None = None) -> dict:
        if (target_weight is None) == (target_notional is None):
            raise OverlayRunnerError(
                f"{symbol} {side}: exactly one of target_weight/target_notional")
        return {
            "symbol": symbol, "side": side, "intent": intent,
            "decision_date": day, "decision_session": session,
            "source_signal": source, "expiry_date": expiry,
            "priority": int(priority),
            "target_weight": (None if target_weight is None
                              else float(target_weight)),
            "target_notional": (None if target_notional is None
                                else float(target_notional)),
        }

    def step(
        self,
        ledger: Mapping[str, object],
        *,
        members: Iterable[str],
        rank_of: Mapping[str, int],
        source_signal: date,
        expiry: date | None,
    ) -> DynamicStep:
        """Resolve this decision point and return the rows to submit.

        ``ledger`` is the engine's live-account feedback; ``members``/``rank_of``
        are the sealed period's seats.  The caller submits entry rows (pool
        members not held), resize rows (held members) and, separately, the
        carrier's own membership exits -- this driver never touches a symbol
        that left the pool.
        """
        equity = self.marks.reconcile(ledger)
        day = ledger["date"]
        session = str(ledger["session"])
        if session not in ("am", "pm"):
            raise OverlayRunnerError(f"invalid ledger session {session!r}")
        if session == "pm":
            self.machine.observe_close(day, equity)
        row = self.machine.step(
            day, decision_point=(DecisionPoint.PM_1500 if session == "pm"
                                 else DecisionPoint.AM_1130))
        ratio = row.exposure_multiplier / self.baseline_exposure
        target = self.base_weight * ratio
        held = {str(p["symbol"]): int(p["shares"])
                for p in ledger["positions"] if int(p["shares"]) > 0}
        seats = {str(s) for s in members}
        if row.action is ro.OverlayAction.REDUCE_ATTACK:
            self._pending_restore.clear()
        elif row.action is ro.OverlayAction.RESTORE_ATTACK:
            self._pending_restore |= (set(held) & seats)

        rows: list[dict] = []
        entries: list[str] = []
        trims: list[str] = []
        topups: list[str] = []
        weights: dict[str, float | None] = {}
        if ro.attack_entry_allowed(row.risk_state):
            for symbol in sorted(seats - set(held)):
                rows.append(self._row(
                    symbol, "buy", day=day, session=session,
                    source=source_signal,
                    priority=self._priority(rank_of, symbol), expiry=expiry,
                    target_weight=target))
                entries.append(symbol)
        for symbol in sorted(set(held) & seats):
            mark = self.marks.mark(symbol, day, session)
            if mark is None:
                weights[symbol] = None
                continue
            weight = held[symbol] * mark / equity
            weights[symbol] = weight
            if row.risk_state is ro.OverlayState.REDUCED:
                if weight > target + self.tolerance:
                    rows.append(self._row(
                        symbol, "sell", day=day, session=session,
                        source=source_signal,
                        priority=self._priority(rank_of, symbol), expiry=expiry,
                        intent=self.trim_intent, target_weight=target))
                    trims.append(symbol)
            elif symbol in self._pending_restore:
                if weight >= target - self.tolerance:
                    self._pending_restore.discard(symbol)
                else:
                    rows.append(self._row(
                        symbol, "buy", day=day, session=session,
                        source=source_signal,
                        priority=self._priority(rank_of, symbol), expiry=expiry,
                        target_notional=(target - weight) * equity))
                    topups.append(symbol)

        step = DynamicStep(
            decision_time=row.decision_time,
            risk_state=row.risk_state.value,
            action=row.action.value,
            exposure_multiplier=row.exposure_multiplier,
            ratio=ratio,
            equity=equity,
            high_water_mark=row.high_water_mark,
            drawdown=row.drawdown,
            trigger_reason=row.trigger_reason,
            cooldown_until=row.cooldown_until,
            target_weight=target,
            weights=weights,
            entry_symbols=tuple(entries),
            trim_symbols=tuple(trims),
            topup_symbols=tuple(topups),
            pending_restore=tuple(sorted(self._pending_restore)),
            rows=tuple(rows),
        )
        self.steps.append(step)
        return step


__all__ = [
    "BASE_ATTACK_WEIGHT", "BASE_EXPOSURE", "C0ParityReport", "DynamicOverlayHost",
    "DynamicStep", "LedgerMarks", "OverlayReplayPlan", "OverlayRunnerError",
    "RESIZE_TOLERANCE", "apply_overlay_to_intents", "decision_times_from_intents",
    "make_replay_plan", "resolve_overlay_rows", "run_c0_parity_harness",
    "run_overlay_backtest",
]
