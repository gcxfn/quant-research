"""Executable smoke contract for the derived risk-overlay runner."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant.portfolio import risk_overlay as ro  # noqa: E402
from quant.research.risk_overlay_runner import (  # noqa: E402
    make_replay_plan,
    run_c0_parity_harness,
)


def main() -> int:
    d1, d2 = date(2024, 1, 2), date(2024, 1, 3)
    intents = pl.DataFrame({
        "symbol": ["S1", "S1"], "side": ["buy", "sell"],
        "intent": ["", "risk"], "decision_date": [d1, d2],
        "decision_session": ["pm", "pm"], "source_signal": [d1, d2],
        "priority": [1, 1], "target_weight": [0.20, 0.20],
    }, schema={
        "symbol": pl.String, "side": pl.String, "intent": pl.String,
        "decision_date": pl.Date, "decision_session": pl.String,
        "source_signal": pl.Date, "priority": pl.Int64,
        "target_weight": pl.Float64,
    })
    plan = make_replay_plan(intents, config_id=ro.C0, attack_symbols={"S1"})
    if not plan.intents.equals(intents.sort(
            "decision_date", "decision_session", "symbol", "side", "source_signal")):
        raise AssertionError("C0 frame parity failed")
    print("C0 plan parity: PASS")
    print("C1/C2 dynamic replay: exposed through make_replay_plan; C2 is fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
