# -*- coding: utf-8 -*-
"""V2 (F line) stage 1 -- B1(m) port validation (dev) + B1(m)(val) recompute.

Assembly is TL-30 verbatim (artifacts/runs/20260919T151630-hybrid-val-v1p3/
scripts/runner_hybrid_val.py sec 1-3, the block that replaced `del hist`):
  simulate_r16(K=0, fractional=True, fee_bands=B1_FEE_SCHEDULE_RATE_ONLY)
  on the R16 T200-40 monthly exposures over the shared R16 pool.
Dev phase port-checks net_cagr / max_drawdown / by-year against
R16 metrics.json configs.C05 b1m_* to 1e-9 (prereg sec 3); val phase
recomputes B1(m)(val) and asserts the TL-30 values
(-0.00148060230384095 / -0.23441429674947534) to 1e-9.

Run twice: VAL_WINDOW=dev then VAL_WINDOW=val.  Engine untouched, no RNG.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

WINDOW = os.environ.get("VAL_WINDOW", "dev")
assert WINDOW in ("dev", "val"), WINDOW
if WINDOW == "val":
    DEV_START, DEV_END = date(2021, 1, 4), date(2024, 12, 31)
else:
    DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)

R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
R16_METRICS = R16_RUN / "metrics.json"
R16_CONFIG = ROOT / "configs/experiments/p2r16-trend-dispersion.json"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
ENGINE_SHA_PIN = ("a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1f0a466b0675abf3")
REF_DEV = {"net_cagr": 0.0059905923579064435,
           "max_drawdown": -0.3982378364862026,
           "by_year": {"2015": 0.22735356961586017,
                       "2016": -0.036271319473570096,
                       "2017": -0.11258228102926204,
                       "2018": -0.1962740727688722,
                       "2019": 0.12375649932752708,
                       "2020": 0.09319791239431541}}
REF_VAL = {"net_cagr": -0.00148060230384095,
           "max_drawdown": -0.23441429674947534,
           "by_year": {"2021": 0.14274922609277585,
                       "2022": -0.05202635253338672,
                       "2023": -0.061879245529232296,
                       "2024": -0.021801197364535896}}

T0 = time.perf_counter()
LOG_PATH = RUN_DIR / "logs" / f"val_b1m_{WINDOW}.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_LINES: list[str] = []
_logf = LOG_PATH.open("a", encoding="utf-8", newline="\n")


def log(msg: object) -> None:
    line = f"[{time.perf_counter() - T0:7.1f}s] {msg}"
    LOG_LINES.append(line)
    _logf.write(line + "\n")
    _logf.flush()
    print(line, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "tmp" / f"val_b1m_{WINDOW}_FAIL.json").write_text(
        json.dumps({"stage": "val_b1m", "window": WINDOW, "status": "failed",
                    "failure_reason": reason,
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "log_tail": LOG_LINES[-100:]},
                   ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    _logf.close()
    sys.exit(1)


# === 0. identity pins ========================================================
log(f"== 0. identity pins (window {WINDOW}) ==")
engine_sha = sha256_file(ENGINE_PY)
if engine_sha != ENGINE_SHA_PIN:
    _fail(f"engine sha drift: {engine_sha} != {ENGINE_SHA_PIN}")
pins = {"engine": {"path": str(ENGINE_PY), "sha256": engine_sha,
                   "expected": ENGINE_SHA_PIN, "match": True,
                   "version": "v1.4.1 (non-zones path = v1.3 semantics)"},
        "r16_metrics": {"path": str(R16_METRICS), "sha256": sha256_file(R16_METRICS)},
        "r16_config": {"path": str(R16_CONFIG), "sha256": sha256_file(R16_CONFIG)},
        "daily": {"path": str(DAILY_PARQUET), "sha256": sha256_file(DAILY_PARQUET)},
        "index_000300": {"path": str(INDEX_CHUNK),
                         "sha256": sha256_file(INDEX_CHUNK)}}
log(f"  engine {engine_sha[:16]} == pin; daily "
    f"{pins['daily']['sha256'][:16]}")

# === 1. calendar + signals ===================================================
log("== 1. calendar + signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
assert sig_days and sig_days[-1] <= DEV_END, sig_days[-3:]
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]}); "
    f"last month-end dropped as signal, kept as expiry anchor")

# === 2. exposures + pools ====================================================
log("== 2. exposures (T200-40) + R16 pools ==")
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
anchor_check = r16.t200_behavioral_anchor_check(index_close, calendar_full)
log(f"  t200 behavioral anchor: {json.dumps(anchor_check)[:140]}")
exposures = r16.t200_month_end_exposures(index_close, calendar_full, sig_days)
log(f"  exposures[{sig_days[0]}]={exposures[sig_days[0]]:.2f} "
    f"[{sig_days[-1]}]={exposures[sig_days[-1]]:.2f}")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
log(f"  pool n: min {min(pools_at[t]['n'] for t in sig_days)} "
    f"max {max(pools_at[t]['n'] for t in sig_days)}")

# === 3. B1(m) simulate =======================================================
log("== 3. B1(m) simulate (K=0, fractional, rate_only, T200-40) ==")
bank_syms = sorted({s for t in sig_days for s in pools_at[t]["ranked"]})
bank = r16.PriceBank(hist, calendar_full, bank_syms)
b1_sim = r16.simulate_r16(
    f"B1-T200-40-rate_only-{WINDOW.upper()}", bank, calendar_full,
    DEV_START, sig_days, pools_at, exposures, K=0, fractional=True,
    fee_bands=r16.B1_FEE_SCHEDULE_RATE_ONLY)
bm = r16.segment_metrics(b1_sim, DEV_START, DEV_END, None, fractional=True)
by_year = {int(k): v for k, v in bm["net_return_by_year"].items()}
log(f"  B1(m)({WINDOW}): net_cagr {bm['net_cagr']:+.8f} "
    f"mdd {bm['max_drawdown']:.8f} by-year {by_year}")

# === 4. port check (dev) / reference assert (val) ============================
if WINDOW == "dev":
    log("== 4. dev port-check vs R16 metrics.json configs.C05 b1m_* (tol 1e-9) ==")
    for k in ("net_cagr", "max_drawdown"):
        if abs(bm[k] - REF_DEV[k]) > 1e-9:
            _fail(f"B1m dev port-check mismatch {k}: {bm[k]!r} vs "
                  f"r16_metrics C05 b1m_{k} {REF_DEV[k]!r}")
    ref_y = {int(k): v for k, v in REF_DEV["by_year"].items()}
    if set(ref_y) != set(by_year) or any(
            abs(ref_y[k] - by_year[k]) > 1e-9 for k in ref_y):
        _fail(f"B1m dev port-check by-year mismatch: {by_year} vs {ref_y}")
    log("  B1m DEV PORT PASS: reproduces R16 metrics.json configs.C05 b1m_* "
        "to 1e-9 (net_cagr / max_drawdown / every year)")
    status = "dev_port_pass"
else:
    log("== 4. val reference assert vs TL-30 run 20260919T151630-hybrid-val-v1p3 ==")
    for k in ("net_cagr", "max_drawdown"):
        if abs(bm[k] - REF_VAL[k]) > 1e-9:
            _fail(f"B1(m)(val) mismatch {k}: {bm[k]!r} vs TL-30 {REF_VAL[k]!r}")
    ref_y = {int(k): v for k, v in REF_VAL["by_year"].items()}
    if set(ref_y) != set(by_year) or any(
            abs(ref_y[k] - by_year[k]) > 1e-9 for k in ref_y):
        _fail(f"B1(m)(val) by-year mismatch: {by_year} vs {ref_y}")
    log("  B1(m)(val) REPRODUCES TL-30 (-0.148% / -23.44%) to 1e-9; "
        "port chain closed")
    status = "val_recomputed"

# === 5. output ==============================================================
out = {
    "stage": "val_b1m",
    "window": WINDOW,
    "status": status,
    "start": str(DEV_START),
    "end": str(DEV_END),
    "n_signal_days": len(sig_days),
    "signal_first": str(sig_days[0]),
    "signal_last": str(sig_days[-1]),
    "net_cagr": bm["net_cagr"],
    "max_drawdown": bm["max_drawdown"],
    "net_total_return": bm["net_total_return"],
    "net_return_by_year": {str(k): v for k, v in sorted(by_year.items())},
    "mdd_window": bm["mdd_window"],
    "benchmark_caliber": "T200-40 monthly exposures; R16 frozen pool; "
                         "simulate_r16(K=0, fractional=True, "
                         "B1_FEE_SCHEDULE_RATE_ONLY); TL-30 assembly verbatim",
    "reference": (REF_DEV if WINDOW == "dev" else REF_VAL),
    "reference_tolerance": 1e-9,
    "reference_source": ("R16 metrics.json configs.C05 b1m_* (dev)" if
                         WINDOW == "dev" else
                         "TL-30 run 20260919T151630-hybrid-val-v1p3 "
                         "outputs/metrics_and_gates.json metrics.R3-05."
                         "b1m_* (val)"),
    "pins": pins,
    "env": {"python": platform.python_version(), "polars": pl.__version__,
            "numpy": np.__version__, "platform": platform.platform()},
    "wall_seconds": time.perf_counter() - T0,
}
p = RUN_DIR / "outputs" / f"b1m_{WINDOW}.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
             encoding="utf-8", newline="\n")
log(f"== {WINDOW} done -> {p.name}; wall {out['wall_seconds']:.1f}s ==")
_logf.close()
