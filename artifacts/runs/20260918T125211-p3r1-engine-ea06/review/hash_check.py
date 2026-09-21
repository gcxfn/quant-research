# -*- coding: utf-8 -*-
"""独立复核 manifest.json 的哈希身份链（双签审阅项 5）。

不导入 band_engine 的 batch_aggregate_sha256：聚合哈希按 manifest 声明的规则
独立实现（对排序后的文件逐个求 sha256，拼 '<sha256>  <name>\\n' 行再求聚合），
以便同时校验"算法描述"与"文件实际内容"的一致性。
只读；输出打印，不修改任何文件。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"D:\量化")
RUN = ROOT / "artifacts" / "runs" / "20260918T125211-p3r1-engine-ea06"
manifest = json.loads((RUN / "manifest.json").read_text(encoding="utf-8"))

failures: list[str] = []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def agg_hash(folder: Path) -> tuple[str, int, int]:
    """独立实现：sha256 over sorted '<file-sha256>  <name>\\n' lines."""
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


# --- code hashes ------------------------------------------------------------
for rel, want in manifest["code_sha256"].items():
    check(f"code {rel}", sha256_file(ROOT / rel), want)

# --- authority chain --------------------------------------------------------
ac = manifest["authority_chain"]
check("contract_doc", sha256_file(ROOT / ac["contract_doc"]["path"]),
      ac["contract_doc"]["sha256"])
check("prereg_doc", sha256_file(ROOT / ac["prereg_doc"]["path"]),
      ac["prereg_doc"]["sha256"])
fc = manifest["frozen_config"]
check("frozen_config p3r1", sha256_file(ROOT / fc["path"]), fc["sha256"])

# prereg sha256:16 expectations
checks = ac["prereg_sha256_16_checks"]
r16 = sha256_file(ROOT / "configs/experiments/p2r16-trend-dispersion.json")[:16]
daily16 = sha256_file(ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet")[:16]
exf16 = sha256_file(ROOT / "data/processed/rqalpha-bundle-v2-1-20260918/ex_cum_factor.h5")[:16]
check("prereg r16_config:16", r16, checks["r16_config_sha256_16"]["prereg"])
check("prereg daily:16", daily16, checks["daily_parquet_sha256_16"]["prereg"])
check("prereg exf:16", exf16, checks["ex_cum_factor_sha256_16"]["prereg"])

# --- inputs -----------------------------------------------------------------
inp = manifest["inputs"]
check("daily_parquet full", sha256_file(ROOT / inp["daily_parquet"]["path"]),
      inp["daily_parquet"]["sha256"])
check("ex_cum_factor full", sha256_file(ROOT / inp["ex_cum_factor_h5"]["path"]),
      inp["ex_cum_factor_h5"]["sha256"])
agg, n_files, total = agg_hash(ROOT / inp["stk_limit_batch"]["path"])
check("stk_limit aggregate", agg, inp["stk_limit_batch"]["aggregate_sha256"])
ok_n = n_files == inp["stk_limit_batch"]["files"]
ok_b = total == inp["stk_limit_batch"]["total_bytes"]
print(f"[{'OK ' if ok_n else 'FAIL'}] stk_limit files: got {n_files} want {inp['stk_limit_batch']['files']}")
print(f"[{'OK ' if ok_b else 'FAIL'}] stk_limit bytes: got {total} want {inp['stk_limit_batch']['total_bytes']}")
if not ok_n:
    failures.append("stk_limit files")
if not ok_b:
    failures.append("stk_limit bytes")

# --- run outputs ------------------------------------------------------------
for rel, want in manifest["outputs"].items():
    p = RUN / rel
    if not p.exists():
        failures.append(f"missing output {rel}")
        print(f"[FAIL] output {rel}: MISSING")
        continue
    check(f"output {rel}", sha256_file(p), want)

print()
if failures:
    print("RESULT: FAIL ->", failures)
    sys.exit(1)
print("RESULT: ALL HASH CHECKS PASSED")
