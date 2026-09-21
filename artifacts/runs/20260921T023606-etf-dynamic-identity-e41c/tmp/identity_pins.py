"""Runtime identity pins for the ETF dynamic-path verification (2026-09-21).

Recomputes, at verification time:
  - the frozen engine sha256 (must equal the pinned prefix bcbdd44bb855b803);
  - the half-day batch aggregate identity (engine's own helper);
  - the ETF processed dir aggregate identity (engine's own helper);
  - the raw fund_daily batch aggregate + the three legs' chunk sha256
    re-hashed against the batch manifest's declared values.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))
from quant.backtest.band_engine import batch_aggregate_sha256  # noqa: E402

RUN_DIR = ROOT / "artifacts/runs/20260921T023606-etf-dynamic-identity-e41c"
RAW = ROOT / "data/raw/tushare/fund_daily/20260917-r1"
LEGS = ["sh.511010", "sh.518880", "sz.159934"]

pins: dict = {}

engine = ROOT / "src/quant/backtest/band_engine.py"
digest = hashlib.sha256(engine.read_bytes()).hexdigest()
pins["engine"] = {"file": engine.name, "bytes": engine.stat().st_size,
                  "sha256": digest, "pinned_prefix": "bcbdd44bb855b803",
                  "prefix_match": digest.startswith("bcbdd44bb855b803")}

pins["halfday_batch"] = batch_aggregate_sha256(
    ROOT / "data/processed/halfday-bars-20260918")
pins["etf_processed_dir"] = batch_aggregate_sha256(
    ROOT / "data/processed/etf-daily-20260919")
pins["raw_fund_daily_batch"] = batch_aggregate_sha256(RAW)

manifest = json.loads((RAW / "manifest.json").read_text(encoding="utf-8"))
legs = {}
for s in LEGS:
    ts = s.split(".")[1] + "." + s.split(".")[0].upper()
    path = RAW / f"chunk_{ts}.csv"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    declared = manifest["chunks"][path.name]
    legs[s] = {"chunk": path.name, "rows_declared": declared["rows"],
               "sha256_declared": declared["sha256"], "sha256_actual": actual,
               "match": actual == declared["sha256"],
               "first_trade_date": declared["first_trade_date"],
               "last_trade_date": declared["last_trade_date"]}
pins["raw_leg_chunks"] = legs
pins["raw_batch_status"] = {"status": manifest["status"],
                            "range": manifest["range"],
                            "universe_count": manifest["universe"]["count"]}

(RUN_DIR / "tmp/identity_pins.json").write_text(
    json.dumps(pins, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
print(json.dumps(pins, ensure_ascii=False, indent=1, default=str))
