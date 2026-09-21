# -*- coding: utf-8 -*-
"""F4R2-S1 probe: does the pinned v1.4 zones engine (7ad35014) TOLERATE a
disabled take-profit at the FRAME level (tp1_mult/tp1_frac null or column
absent), i.e. no TP intent emission + no crash + fail-closed asserts NOT
triggered?

Read-only probe (engine untouched).  Mini synthetic zones world built the
same way as tests/test_band_engine_v14_zones.py (W1-style, clearly
synthetic, no strategy judgement, zero trial consumption).  Cases:
  control      tp1 2.0/0.5 + tp2 null   -> expected: RUNS, -ztp intents exist
  null_tp1     tp1_mult/tp1_frac = None -> F4R2-S1 priority-(1) form A
  nan_tp1      tp1_mult/tp1_frac = NaN  -> F4R2-S1 priority-(1) form B
  drop_tp1cols tp1 columns removed      -> F4R2-S1 priority-(1) form C
Verdict rule: ALL of null_tp1 / nan_tp1 / drop_tp1cols must RUN with zero
ztp intents for the frame-level expression to be adjudicated FEASIBLE.
"""
from __future__ import annotations

import json
import math
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

DAILY = pl.DataFrame({
    "symbol": [A] * 6, "date": [D1, D2, D3, D4, D5, D6],
    "open": [10.0, 10.0, 10.2, 10.4, 10.6, 10.8],
    "high": [10.1, 10.3, 10.4, 10.6, 10.8, 11.0],
    "low": [9.9, 9.9, 10.1, 10.3, 10.5, 10.7],
    "close": [10.0, 10.2, 10.3, 10.5, 10.7, 10.9],
    "tradestatus": [1.0] * 6})
HALF = pl.DataFrame({
    "symbol": [A] * 12,
    "trade_date": [d for d in (D1, D2, D3, D4, D5, D6) for _ in ("am", "pm")],
    "session": ["am", "pm"] * 6,
    "open": [10.0, 10.0, 10.2, 10.2, 10.3, 10.3, 10.4, 10.4,
             10.6, 10.6, 10.8, 10.8],
    "high": [10.05, 10.1, 10.3, 10.35, 10.4, 10.45, 10.5, 10.55,
             10.7, 10.75, 10.9, 10.95],
    "low": [9.95, 9.95, 10.1, 10.15, 10.2, 10.25, 10.3, 10.35,
            10.5, 10.55, 10.7, 10.75],
    "close": [10.0, 10.0, 10.2, 10.2, 10.3, 10.3, 10.4, 10.4,
              10.6, 10.6, 10.8, 10.8]})
LIMITS = DAILY.select(
    "symbol", "date", (pl.col("close") * 1.9).alias("limit_up"),
    (pl.col("close") * 0.1).alias("limit_down"))


def zrow(**tp):
    base = {"signal_date": D1, "symbol": A, "rank": 1, "industry": "X",
            "sigma0": 1.0, "p0": 10.0, "w_t": 0.05,
            "ladder_offsets": "0.5,1.5,2.5", "ladder_fracs": "0.4,0.4,0.2",
            "tp1_mult": 2.0, "tp1_frac": 0.5,
            "tp2_mult": None, "tp2_frac": None,
            "stop_mult": 100.0, "invalid_mult": 10.0,
            "k_seats": 1, "ind_cap": 5, "buffer_mult": 2}
    base.update(tp)
    return pl.DataFrame([base], schema=ZONE_SCHEMA)


def probe(name, zones):
    out = {"case": name}
    try:
        res = run_band_backtest_zones(zones, DAILY, HALF, LIMITS,
                                      initial_cash=200_000.0)
        n_ztp = int(res.fills.filter(
            pl.col("order_id").str.contains("-ztp")).height)
        n_ztp_ev = int(res.events.filter(
            pl.col("event").str.starts_with("zone_tp")).height)
        out.update({"outcome": "RAN", "ztp_fill_orders": n_ztp,
                    "zone_tp_events": n_ztp_ev,
                    "n_fills": int(res.fills.height)})
    except BandContractError as exc:
        out.update({"outcome": "REJECTED_BandContractError",
                    "message": str(exc)[:300]})
    except Exception as exc:  # noqa: BLE001 -- record the exact type
        out.update({"outcome": f"REJECTED_{type(exc).__name__}",
                    "message": str(exc)[:300]})
    return out


results = [
    probe("control (tp1 2.0/0.5, tp2 null) -> TP expected", zrow()),
    probe("null_tp1 (tp1_mult/tp1_frac None)", zrow(tp1_mult=None,
                                                    tp1_frac=None)),
    probe("nan_tp1 (tp1_mult/tp1_frac NaN)",
          zrow(tp1_mult=float("nan"), tp1_frac=float("nan"))),
    probe("drop_tp1cols (columns removed)",
          zrow().drop(["tp1_mult", "tp1_frac"])),
]

feasible = all(
    r["outcome"] == "RAN" and r.get("ztp_fill_orders") == 0
    and r.get("zone_tp_events") == 0
    for r in results[1:])   # the three disable forms only
verdict = {
    "probe": "F4R2-S1 frame-level tp-disable feasibility (prereg sec 6)",
    "engine_pin_expected": "7ad35014d72711cb43ab6aedc232d70adf7eece60604b2a"
                           "057ee039c9bd11e78",
    "cases": results,
    "frame_level_feasible": feasible,
}
print(json.dumps(verdict, ensure_ascii=False, indent=1))
