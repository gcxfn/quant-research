#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-29 标注构建：ann_part1..6.json -> batch_029_judge_part1..6.jsonl
写前自检：vocab 封闭、secondary!=primary、sd/conf 合法、key_quote<=40 且为
raw change_reason 逐字子串（与 merge_batch29 同口径预检）。
"""
import csv
import glob
import json
import os
import polars as pl

VOCAB = {
    "demand_up", "demand_down", "price_up", "price_down", "orders",
    "cost_up", "cost_down", "fx", "impairment", "non_recurring",
    "ma_restructuring", "epidemic_shock", "accounting", "core_ops", "other",
}
ROOT = "D:/量化"
RUN = os.path.join(ROOT, "artifacts/runs/20260919T231937-fcst-w29-9a28")
WORK = os.path.join(RUN, "work")
ANN = os.path.join(WORK, "ann")
RAW = os.path.join(ROOT, "data/raw/tushare/forecast/20260909-r1")
FEAT = os.path.join(ROOT, "data/features/fcst-reason-struct-full-20260918")

idx = pl.read_parquet(os.path.join(FEAT, "row_index.parquet"))
batch = idx.filter(pl.col("batch_id") == 29).sort("batch_idx")
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
total = 0
for part in range(1, 7):
    with open(os.path.join(ANN, f"ann_part{part}.json"), encoding="utf-8") as f:
        ann = json.load(f)
    lo = 16800 + (part - 1) * 100
    expect = list(range(lo, lo + 100))
    if sorted(int(k) for k in ann) != expect:
        missing = set(expect) - {int(k) for k in ann}
        extra = {int(k) for k in ann} - set(expect)
        fails.append(f"part{part}: key set mismatch missing={sorted(missing)} extra={sorted(extra)}")
        continue
    out_lines = []
    for oid in expect:
        pc, sc, sd, q, cf = ann[str(oid)]
        total += 1
        if pc not in VOCAB:
            fails.append(f"{oid}: primary '{pc}' not in vocab")
        if sc is not None and sc not in VOCAB:
            fails.append(f"{oid}: secondary '{sc}' not in vocab")
        if sc == pc:
            fails.append(f"{oid}: secondary == primary")
        if sd not in (-1, 0, 1):
            fails.append(f"{oid}: sd {sd}")
        if cf not in ("high", "low"):
            fails.append(f"{oid}: confidence {cf}")
        if not q or len(q) > 40:
            fails.append(f"{oid}: quote len {len(q)}")
        else:
            m = meta[oid]
            key = (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"])
            orig = reasons.get(key)
            if orig is None:
                fails.append(f"{oid}: raw row missing")
            elif q not in orig:
                fails.append(f"{oid}: quote NOT verbatim; quote={q!r}; orig={orig[:70]!r}")
        out_lines.append(json.dumps({
            "ordinal": oid, "primary_code": pc, "secondary_code": sc,
            "supports_direction": sd, "key_quote": q, "confidence": cf,
        }, ensure_ascii=False, separators=(",", ":")))
    with open(os.path.join(WORK, f"batch_029_judge_part{part}.jsonl"),
              "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines) + "\n")

if fails:
    print(f"SELF-CHECK FAILURES: {len(fails)} / rows {total}")
    for x in fails:
        print("FAIL:", x)
    raise SystemExit(1)
print(f"OK: {total} rows, all quotes verbatim, judges written.")
