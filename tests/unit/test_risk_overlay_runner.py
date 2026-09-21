from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.portfolio import risk_overlay as ro
from quant.research.risk_overlay_runner import (
    OverlayRunnerError,
    apply_overlay_to_intents,
    make_replay_plan,
    run_c0_parity_harness,
    run_overlay_backtest,
)


def intents_frame(rows):
    return pl.DataFrame(rows, schema={
        "symbol": pl.String, "side": pl.String, "intent": pl.String,
        "decision_date": pl.Date, "decision_session": pl.String,
        "source_signal": pl.Date, "priority": pl.Int64,
        "target_weight": pl.Float64,
    })


def test_c0_frame_is_identity_and_harness_runs_real_engine():
    d1 = date(2024, 1, 2)
    daily = pl.DataFrame({
        "symbol": ["S1", "S1"], "date": [d1, date(2024, 1, 3)],
        "open": [10.0, 10.0], "high": [10.1, 10.2],
        "low": [9.9, 9.9], "close": [10.0, 10.0],
        "tradestatus": [1.0, 1.0],
    })
    half = pl.DataFrame({
        "symbol": ["S1", "S1", "S1", "S1"],
        "trade_date": [d1, d1, date(2024, 1, 3), date(2024, 1, 3)],
        "session": ["am", "pm", "am", "pm"],
        "open": [10.0, 10.0, 10.0, 10.0],
        "high": [10.1, 10.1, 10.1, 10.1],
        "low": [9.9, 9.9, 9.9, 9.9],
        "close": [10.0, 10.0, 10.0, 10.0],
    })
    limits = daily.select(
        "symbol", "date",
        (pl.col("close") * 1.1).alias("limit_up"),
        (pl.col("close") * 0.9).alias("limit_down"),
    )
    intents = intents_frame([{
        "symbol": "S1", "side": "buy", "intent": "",
        "decision_date": d1, "decision_session": "pm",
        "source_signal": d1, "priority": 1, "target_weight": 0.20,
    }])
    result, report = run_c0_parity_harness(
        intents, attack_symbols={"S1"}, daily=daily, halfday=half,
        stk_limit=limits, initial_cash=200_000.0)
    assert result.fills.height == 1
    assert report.frame_equal is True
    assert report.result_equal is None


def test_reduced_overlay_reissues_active_target_at_later_decision():
    d1, d2 = date(2024, 1, 2), date(2024, 1, 3)
    base = intents_frame([{
        "symbol": "S1", "side": "buy", "intent": "",
        "decision_date": d1, "decision_session": "pm",
        "source_signal": d1, "priority": 1, "target_weight": 0.20,
    }])
    policy = ro.OverlayPolicy(ro.C1, ro.GateMechanism.INDEX_SMA,
                              sma_sessions=2, recovery_confirmations=1,
                              cooldown_sessions=0)
    rows = ro.resolve_overlay(
        [d2], config_id=ro.C1, policy=policy,
        benchmark_close=[(date(2024, 1, 1), 100.0), (d1, 90.0), (d2, 80.0)])
    derived, n = apply_overlay_to_intents(
        base, rows, attack_symbols={"S1"})
    assert n == 1
    assert derived.height == 2
    assert derived.sort("decision_date")["target_weight"].to_list() == [0.20, pytest.approx(0.20 * 0.4 / 0.9)]


@pytest.mark.parametrize("confirmed", [False, True])
def test_c2_run_is_fail_closed_without_dynamic_feedback_confirmation(confirmed):
    d1 = date(2024, 1, 2)
    base = intents_frame([{
        "symbol": "S1", "side": "buy", "intent": "",
        "decision_date": d1, "decision_session": "pm",
        "source_signal": d1, "priority": 1, "target_weight": 0.20,
    }])
    plan = make_replay_plan(
        base, config_id=ro.C2, attack_symbols={"S1"},
        equity=[(d1, 100_000.0)])
    with pytest.raises(OverlayRunnerError, match="iterative ledger feedback"):
        run_overlay_backtest(plan, dynamic_equity_confirmed=confirmed)

    # A caller-provided metadata flag cannot disguise a C2 configuration.
    from dataclasses import replace
    with pytest.raises(OverlayRunnerError, match="iterative ledger feedback"):
        run_overlay_backtest(replace(plan, dynamic_equity_required=False),
                             dynamic_equity_confirmed=confirmed)
