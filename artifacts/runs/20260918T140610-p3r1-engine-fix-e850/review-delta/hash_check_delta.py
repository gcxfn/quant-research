# -*- coding: utf-8 -*-
"""增量复审 · manifest 哈希校验（F3 处置验收 + 新 pin 链）。

独立实现聚合哈希（不复用引擎函数）；同时校验旧 REJECT 运行目录未被改动。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\量化")
NEW = ROOT / "artifacts" / "runs" / "20260918T140610-p3r1-engine-fix-e850"
OLD = ROOT / "artifacts" / "runs" / "20260918T125211-p3r1-engine-ea06"
manifest = json.loads((NEW / "manifest.json").read_text(encoding="utf-8"))
old_manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))

failures: list[str] = []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def agg_hash(folder: Path) -> tuple[str, int, int]:
    files = sorted(p for p in folder.iterdir() if p.is_file())
    h = hashlib.sha256()
    total = 0
    for p in files:
        fh = hashlib.sha256()
        with p.open("rb") as s:
            for chunk in iter(lambda: s.read(1 << 20), b""):
                fh.update(chunk)
        h.update(f"{fh.hexdigest()}  {p.name}\n".encode("utf-8"))
        total += p.stat().st_size
    return h.hexdigest(), len(files), total


def check(label: str, got: str, want: str) -> None:
    ok = got == want
    print(f"[{'OK ' if ok else 'FAIL'}] {label}: got {got[:16]}… want {want[:16]}…")
    if not ok:
        failures.append(label)


# --- code -------------------------------------------------------------------
for rel, want in manifest["code_sha256"].items():
    check(f"code {rel}", sha256_file(ROOT / rel), want)

# --- authority chain / pins -------------------------------------------------
ac = manifest["authority_chain"]
check("contract_doc_amended", sha256_file(ROOT / ac["contract_doc_amended"]["path"]),
      ac["contract_doc_amended"]["sha256"])
check("prereg_doc (with §7)", sha256_file(ROOT / ac["prereg_doc"]["path"]),
      ac["prereg_doc"]["sha256"])
fc = manifest["frozen_config"]
check("frozen_config p3r1 (updated)", sha256_file(ROOT / fc["path"]), fc["sha256"])

pins = ac["pin_sha256_16_checks"]
check("pin split_factor:16", sha256_file(ROOT / "data/processed/rqalpha-bundle-v2-1-20260918/split_factor.h5")[:16],
      pins["split_factor_sha256_16"]["pinned"])
check("pin dividends:16", sha256_file(ROOT / "data/processed/rqalpha-bundle-v2-1-20260918/dividends.h5")[:16],
      pins["dividends_sha256_16"]["pinned"])
check("pin r16_config:16", sha256_file(ROOT / "configs/experiments/p2r16-trend-dispersion.json")[:16],
      pins["r16_config_sha256_16"]["pinned"])
check("pin daily:16", sha256_file(ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet")[:16],
      pins["daily_parquet_sha256_16"]["pinned"])
check("pin ex_cum_factor_audit:16",
      sha256_file(ROOT / "data/processed/rqalpha-bundle-v2-1-20260918/ex_cum_factor.h5")[:16],
      pins["ex_cum_factor_audit_sha256_16"]["pinned"])

# --- inputs -----------------------------------------------------------------
inp = manifest["inputs"]
check("stk_limit aggregate (unchanged)", agg_hash(ROOT / inp["stk_limit_batch"]["path"])[0],
      inp["stk_limit_batch"]["aggregate_sha256"])

# --- run outputs ------------------------------------------------------------
for rel, want in manifest["outputs"].items():
    check(f"output {rel}", sha256_file(NEW / rel), want)

# --- old REJECT run untouched (F3: archived evidence) -----------------------
old_outputs_unchanged = True
for rel, want in old_manifest["outputs"].items():
    p = OLD / rel
    if not p.exists() or sha256_file(p) != want:
        old_outputs_unchanged = False
        failures.append(f"old run output changed: {rel}")
check("old REJECT run outputs unmodified (F3 archive)",
      "yes" if old_outputs_unchanged else "no", "yes")
check("old manifest kept (status still completed)",
      old_manifest.get("status", "?"), "completed")

print()
if failures:
    print("RESULT: FAIL ->", failures)
    sys.exit(1)
print("RESULT: ALL DELTA HASH CHECKS PASSED")
