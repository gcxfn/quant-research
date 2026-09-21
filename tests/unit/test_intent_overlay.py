import polars as pl
import pytest

from quant.portfolio.intent_overlay import IntentOverlayError, apply_attack_exposure


def _frame():
    return pl.DataFrame({
        "symbol": ["sh.600000", "sh.510300", "sh.600000"],
        "side": ["buy", "buy", "sell"],
        "target_weight": [0.20, 0.25, None],
    })


def test_scales_attack_and_leaves_defense_and_full_exit_unchanged():
    got = apply_attack_exposure(
        _frame(), attack_symbols=["sh.600000"], multiplier=0.4, config_id="C0"
    )
    assert got["target_weight"].to_list()[0] == pytest.approx(0.08)
    assert got["target_weight"].to_list()[1:] == [0.25, None]


def test_rejects_invalid_multiplier_and_missing_columns():
    with pytest.raises(IntentOverlayError):
        apply_attack_exposure(_frame(), attack_symbols=[], multiplier=0, config_id="C0")
    with pytest.raises(IntentOverlayError, match="missing"):
        apply_attack_exposure(pl.DataFrame({"symbol": ["x"]}), attack_symbols=[], multiplier=.9, config_id="C0")
