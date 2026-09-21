# -*- coding: utf-8 -*-
"""F4R2-S1 probe, v1.4.1 engine (pin a01cb29c..., dual-signed re-pin after
the F4R2-S1 adjudication): verify the adjudicated tp-disable expression.

Cases (mini synthetic world, tests/test_band_engine_v14_zones.py style;
synthetic data, no strategy judgement, zero trial consumption):
  control          tp1 2.0/0.5 + tp2 3.0/1.0 -> expected: RAN, >=1 ztp fill
                   (rally world reaches WAC+2sigma)
  null_tp1_D1      tp1/tp2 all None           -> RAN, 0 ztp fills/orders,
                   ladder buys still emitted (v1.4.1 zero-tier TP)
  drop_tp1cols     tp1/tp2 columns absent     -> RAN, outputs field-equal
                   to null_tp1_D1 (fills/events/daily/zones/clips_final)
  nan_tp1          tp1_mult = NaN             -> BandContractError (kept
                   fail-closed for supplied values)
  tp2_without_tp1  tp1 None, tp2 3.0/1.0      -> BandContractError (v1.4.1
                   new guardrail)
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

RUN = Path(__file__).resolve().parents[1]
ROOT = RUN.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from quant.backtest.band_engine import (  # noqa: E402
    BandContractError, run_band_backtest_zones)

D = date
D1, D2, D3, D4, D5, D6 = (D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9))
A = "sh.600001"

ZONE_SCHEMA = {
    "signal_date": pl.Date, "symbol": pl.String, "rank": pl.Int64,
    "industry": pl.String, "sigma0": pl.Float64, "p0": pl.Float64,
    "w_t": pl.Float64, "ladder_offsets": pl.String, "ladder_fracs": pl.String,
    "tp1_mult": pl.Float64, "tp1_frac": pl.Float64,
    "tp2_mult": pl.Float64, "tp2_frac": pl.Float64,
    "stop_mult": pl.Float64, "invalid_mult": pl.Float64,
    "k_seats": pl.Int64, "ind_cap": pl.Int64, "buffer_mult": pl.Int64}

# decline to WAC 8.02 (three tiers fill, tests W1 sequence) then rally to
# 10.5 so the control's WAC+2*sigma = 10.02 take-profit fills
DAILY = pl.DataFrame({
    "symbol": [A] * 6, "date": [D1, D2, D3, D4, D5, D6],
    "open": [10.0, 9.9, 7.9, 6.0, 7.5, 10.3],
    "high": [10.1, 9.95, 8.0, 8.0, 10.5, 10.8],
    "low": [9.9, 7.6, 5.4, 5.9, 7.4, 10.2],
    "close": [10.0, 8.0, 6.0, 7.5, 10.3, 10.6],
    "tradestatus": [1.0] * 6})
HALF = pl.DataFrame({
    "symbol": [A] * 12,
    "trade_date": [d for d in (D1, D2, D3, D4, D5, D6) for _ in ("am", "pm")],
    "session": ["am", "pm"] * 6,
    "open": [10.0, 10.0, 9.9, 9.3, 7.9, 6.0, 6.0, 6.0, 7.5, 7.5, 10.3, 10.3],
    "high": [10.05, 10.1, 9.95, 9.4, 8.0, 6.1, 6.1, 8.0, 10.5, 10.5, 10.6, 10.8],
    "low": [9.9, 9.95, 9.2, 7.6, 5.4, 5.8, 5.9, 5.9, 7.4, 7.4, 10.2, 10.2],
    "close": [10.0, 10.0, 9.3, 8.0, 6.0, 5.9, 6.0, 7.5, 10.3, 10.3, 10.4, 10.6]})
LIMITS = DAILY.select(
    "symbol", "date", (pl.col("close") * 1.9).alias("limit_up"),
    (pl.col("close") * 0.1).alias("limit_down"))


def zframe(**tp):
    base = {"signal_date": D1, "symbol": A, "rank": 1, "industry": "X",
            "sigma0": 1.0, "p0": 10.0, "w_t": 0.05,
            "ladder_offsets": "0.5,1.5,2.5", "ladder_fracs": "0.4,0.4,0.2",
            "tp1_mult": 2.0, "tp1_frac": 0.5,
            "tp2_mult": 3.0, "tp2_frac": 1.0,
            "stop_mult": 100.0, "invalid_mult": 10.0,
            "k_seats": 1, "ind_cap": 5, "buffer_mult": 2}
    base.update(tp)
    return pl.DataFrame([base], schema=ZONE_SCHEMA)


def probe(name, zones):
    out = {"case": name}
    try:
        res = run_band_backtest_zones(zones, DAILY, HALF, LIMITS,
                                      initial_cash=200_000.0)
        f = res.fills
        out.update({
            "outcome": "RAN",
            "engine_version": res.stats.get("engine_version"),
            "n_ladder_buy_fills": int(f.filter(
                pl.col("order_id").str.contains("-zladder-")).height),
            "ztp_fill_orders": int(f.filter(
                pl.col("order_id").str.contains("-ztp")).height),
            "ztp_sell_intents": int(res.events.filter(
                (pl.col("event") == "order_submitted")
                & (pl.col("detail").str.contains("profit")).or_(
                    pl.col("event").str.contains("tp"))).height)
                if "detail" in res.events.columns else None,
            "n_fills": int(f.height)})
    except BandContractError as exc:
        out.update({"outcome": "REJECTED_BandContractError",
                    "message": str(exc)[:300]})
    except Exception as exc:  # noqa: BLE001
        out.update({"outcome": f"REJECTED_{type(exc).__name__}",
                    "message": str(exc)[:300]})
    return out


def fields_equal(df_a: pl.DataFrame, df_b: pl.DataFrame) -> bool:
    if df_a.columns != df_b.columns or df_a.height != df_b.height:
        return False
    for col in df_a.columns:
        a, b = df_a[col], df_b[col]
        if a.dtype != b.dtype:
            return False
        if a.dtype in (pl.Float64, pl.Float32):
            for x, y in zip(a, b):
                if x is None or y is None:
                    if x is not y:
                        return False
                elif abs(x - y) > 1e-12:
                    return False
        else:
            if a.to_list() != b.to_list():
                return False
    return True


r_null = probe("null_tp1_D1 (tp1/tp2 all None; D1 arm form)",
               zframe(tp1_mult=None, tp1_frac=None,
                      tp2_mult=None, tp2_frac=None))
r_drop = probe("drop_tp1cols (columns absent)",
               zframe().drop(["tp1_mult", "tp1_frac", "tp2_mult",
                              "tp2_frac"]))
null_vs_drop_outputs_equal = None
if r_null["outcome"] == "RAN" and r_drop["outcome"] == "RAN":
    zones_null = zframe(tp1_mult=None, tp1_frac=None,
                        tp2_mult=None, tp2_frac=None)
    zones_drop = zframe().drop(["tp1_mult", "tp1_frac",
                                "tp2_mult", "tp2_frac"])
    res_n = run_band_backtest_zones(zones_null, DAILY, HALF, LIMITS,
                                    initial_cash=200_000.0)
    res_d = run_band_backtest_zones(zones_drop, DAILY, HALF, LIMITS,
                                    initial_cash=200_000.0)
    null_vs_drop_outputs_equal = {
        "fills": fields_equal(res_n.fills, res_d.fills),
        "events": fields_equal(res_n.events, res_d.events),
        "daily_equity": fields_equal(res_n.daily, res_d.daily),
        "zones": fields_equal(res_n.zones, res_d.zones),
        "clips_final": fields_equal(res_n.clips_final, res_d.clips_final)}

results = [
    probe("control (tp1 2.0/0.5 + tp2 3.0/1.0; TP fill expected)", zframe()),
    r_null,
    r_drop,
    probe("nan_tp1 (tp1_mult NaN)", zframe(tp1_mult=float("nan"))),
    probe("tp2_without_tp1 (tp1 None, tp2 3.0/1.0)",
          zframe(tp1_mult=None, tp1_frac=None)),
]

verdict = {
    "probe": "F4R2-S1 v1.4.1 adjudicated tp-disable expression check",
    "engine_pin_expected": "a01cb29ce4cf214814dd51679295f70ac780dc5dffb27"
                           "0ea1f0a466b0675abf3",
    "cases": results,
    "null_vs_drop_outputs_field_equal": null_vs_drop_outputs_equal,
    "adjudicated_form_ok": bool(
        r_null["outcome"] == "RAN" and r_null.get("ztp_fill_orders") == 0
        and r_null.get("n_ladder_buy_fills", 0) >= 3
        and null_vs_drop_outputs_equal
        and all(null_vs_drop_outputs_equal.values())),
}
print(json.dumps(verdict, ensure_ascii=False, indent=1))
