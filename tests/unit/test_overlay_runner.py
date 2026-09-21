import datetime as dt

import polars as pl
import pytest

from quant.portfolio.overlay_runner import OverlayRunnerError, resolve_run_overlays, scale_run_intents
from quant.portfolio.risk_overlay import C0, C1, C2, DecisionPoint


def test_c0_resolves_without_market_inputs_and_scales_attack_only():
    day = dt.date(2026, 1, 5)
    when = dt.datetime(2026, 1, 5, 15)
    rows = resolve_run_overlays([when], config_id=C0,
                                decision_points=[DecisionPoint.PM_1500])
    assert rows[0].exposure_multiplier == 0.9
    got = scale_run_intents(
        pl.DataFrame({"symbol": ["stock", "etf"], "side": ["buy", "buy"],
                      "target_weight": [0.2, 0.3]}),
        attack_symbols=["stock"], overlay=rows[0]
    )
    assert got["target_weight"].to_list()[0] == pytest.approx(.18)
    assert got["target_weight"].to_list()[1] == .3


def test_dynamic_configs_fail_closed_without_required_history():
    when = dt.datetime(2026, 1, 5, 15)
    point = [DecisionPoint.PM_1500]
    with pytest.raises(OverlayRunnerError, match="benchmark"):
        resolve_run_overlays([when], config_id=C1, decision_points=point)
    with pytest.raises(OverlayRunnerError, match="equity"):
        resolve_run_overlays([when], config_id=C2, decision_points=point)
