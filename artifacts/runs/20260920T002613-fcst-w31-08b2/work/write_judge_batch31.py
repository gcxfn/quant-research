# -*- coding: utf-8 -*-
"""wave-31: 从 anno_batch31.py 生成 6 个 judge part 文件, 写出前全量自检。
自检项: 600 行、ordinal 连续、词表闭合、secondary!=primary、sd 合法、
confidence 合法、key_quote 非空<=40 且为 raw change_reason 逐字子串。
"""
import csv
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anno_batch31 import ANNOT

VOCAB = {
    "demand_up", "demand_down", "price_up", "price_down", "orders",
    "cost_up", "cost_down", "fx", "impairment", "non_recurring",
    "ma_restructuring", "epidemic_shock", "accounting", "core_ops", "other",
}
ROOT = "D:/量化"
RUN = os.path.join(ROOT, "artifacts", "runs", "20260920T002613-fcst-w31-08b2")
WORK = os.path.join(RUN, "work")
FEATURES = os.path.join(ROOT, "data", "features", "fcst-reason-struct-full-20260918")
RAW = os.path.join(ROOT, "data", "raw", "tushare", "forecast", "20260909-r1")

import polars as pl

idx = pl.read_parquet(os.path.join(FEATURES, "row_index.parquet"))
batch = idx.filter(pl.col("batch_id") == 31).sort("batch_idx")
meta = {r["ordinal"]: r for r in batch.iter_rows(named=True)}

reasons = {}
for fp in sorted(glob.glob(os.path.join(RAW, "chunk_*.csv"))):
    with open(fp, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                   (r.get("ann_date") or "").strip(),
                   (r.get("update_flag") or "").strip())
            reasons[key] = r.get("change_reason") or ""

fails = []
if len(ANNOT) != 600:
    fails.append(f"annotation count {len(ANNOT)} != 600")
ords = [a[0] for a in ANNOT]
if ords != list(range(18000, 18600)):
    fails.append("ordinal sequence not 18000..18599")

for oid, pc, sc, sd, q, cf in ANNOT:
    if pc not in VOCAB:
        fails.append(f"{oid}: primary {pc} not in vocab")
    if sc is not None:
        if sc not in VOCAB:
            fails.append(f"{oid}: secondary {sc} not in vocab")
        if sc == pc:
            fails.append(f"{oid}: secondary == primary ({pc})")
    if sd not in (-1, 0, 1):
        fails.append(f"{oid}: sd {sd} invalid")
    if cf not in ("high", "low"):
        fails.append(f"{oid}: confidence {cf} invalid")
    if not q or len(q) > 40:
        fails.append(f"{oid}: quote len {len(q)}")
        continue
    m = meta.get(oid)
    if m is None:
        fails.append(f"{oid}: not in row_index batch31")
        continue
    key = (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"])
    orig = reasons.get(key)
    if orig is None:
        fails.append(f"{oid}: raw row missing for {key}")
    elif q not in orig:
        fails.append(f"{oid}: quote NOT verbatim; q={q!r}; head={orig[:50]!r}")

if fails:
    print("SELF-CHECK FAILURES:", len(fails))
    for x in fails:
        print("FAIL:", x)
    raise SystemExit(1)

for part in range(1, 7):
    lo = 18000 + (part - 1) * 100
    lines = []
    for a in ANNOT:
        if lo <= a[0] < lo + 100:
            lines.append(json.dumps({
                "ordinal": a[0], "primary_code": a[1], "secondary_code": a[2],
                "supports_direction": a[3], "key_quote": a[4], "confidence": a[5],
            }, ensure_ascii=False, separators=(",", ":")))
    if len(lines) != 100:
        raise SystemExit(f"part{part}: {len(lines)} lines")
    out = os.path.join(WORK, f"batch_031_judge_part{part}.jsonl")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote part{part}: {len(lines)} rows, ordinals {lo}-{lo+99}")
print("SELF-CHECK OK: 600/600 quotes verbatim in raw CSV, vocab closed")
