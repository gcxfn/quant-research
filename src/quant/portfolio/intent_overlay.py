"""Apply a registered account exposure multiplier to engine intents.

This is the static-arm boundary used by C0.  It intentionally does not claim
to implement C1/C2: dynamic states require a sequential runner with confirmed
equity, and must not be approximated by scaling a whole-window frame.
"""
from __future__ import annotations

from collections.abc import Iterable

import polars as pl

__all__ = ["IntentOverlayError", "apply_attack_exposure"]


class IntentOverlayError(ValueError):
    pass


def apply_attack_exposure(
    intents: pl.DataFrame,
    *,
    attack_symbols: Iterable[str],
    multiplier: float,
    config_id: str,
) -> pl.DataFrame:
    """Scale only buy/targeted sell weights for the attack sleeve.

    Full exits (sell with null target) stay full exits.  ETF/defensive symbols
    are unchanged.  The returned frame preserves row order and schema.
    """
    required = {"symbol", "side", "target_weight"}
    missing = sorted(required - set(intents.columns))
    if missing:
        raise IntentOverlayError(f"missing intent columns: {missing}")
    if not isinstance(config_id, str) or not config_id:
        raise IntentOverlayError("config_id must be non-empty")
    if not isinstance(multiplier, (int, float)) or not 0.0 < float(multiplier) <= 1.0:
        raise IntentOverlayError("multiplier must be inside (0, 1]")
    attack = set(attack_symbols)
    if any(not isinstance(s, str) or not s for s in attack):
        raise IntentOverlayError("attack_symbols must contain non-empty strings")
    return intents.with_columns(
        pl.when(
            pl.col("symbol").is_in(sorted(attack))
            & pl.col("target_weight").is_not_null()
        )
        .then(pl.col("target_weight") * float(multiplier))
        .otherwise(pl.col("target_weight"))
        .alias("target_weight")
    )
