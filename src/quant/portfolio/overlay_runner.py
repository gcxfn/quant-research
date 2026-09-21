"""Small, fail-closed orchestration boundary for account overlays."""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from quant.portfolio import risk_overlay as ro
from quant.portfolio.intent_overlay import apply_attack_exposure

__all__ = ["OverlayRunnerError", "resolve_run_overlays", "scale_run_intents"]


class OverlayRunnerError(ValueError):
    pass


def resolve_run_overlays(
    decision_times: Sequence[dt.datetime],
    *,
    config_id: str,
    decision_points: Sequence[ro.DecisionPoint],
    benchmark_close: Sequence[tuple[dt.date, float]] | None = None,
    equity: Sequence[tuple[dt.date, float]] | None = None,
) -> tuple[ro.OverlayDecision, ...]:
    """Resolve one chronological overlay path with its required observations."""
    if config_id == ro.C1 and benchmark_close is None:
        raise OverlayRunnerError("C1 requires benchmark_close history")
    if config_id == ro.C2 and equity is None:
        raise OverlayRunnerError("C2 requires confirmed equity history")
    try:
        return ro.resolve_overlay(
            decision_times, config_id=config_id, decision_points=decision_points,
            benchmark_close=benchmark_close, equity=equity,
        )
    except ro.RiskOverlayError as exc:
        raise OverlayRunnerError(str(exc)) from exc


def scale_run_intents(intents, *, attack_symbols, overlay: ro.OverlayDecision):
    """Apply one already-resolved overlay row to a static intent frame."""
    return apply_attack_exposure(
        intents,
        attack_symbols=attack_symbols,
        multiplier=overlay.exposure_multiplier,
        config_id=overlay.config_id,
    )
