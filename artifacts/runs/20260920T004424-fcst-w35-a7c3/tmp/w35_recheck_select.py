#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批 35 sd=0 基数嫌疑行复筛：primary in {non_recurring, impairment} 且 sd==0 且
原始 change_reason 含基数类关键词。输出候选行及其原文供逐行语义复核。"""
import csv
import glob
import json
import os
import sys

import polars as pl

ROOT = r"D:/量化"
RUN = os.path.join(ROOT, "artifacts", "runs", "20260920T004424-fcst-w35-a7c3")
WORK = os.path.join(RUN, "work")
FEAT = os.path.join(ROOT, "data", "features", "fcst-reason-struct-full-20260918")
RAW = os.path.join(ROOT, "data", "raw", "tushare", "forecast", "20260909-r1")
KEYWORDS = ["上年", "同期", "同比", "上期", "上年度", "去年", "前期", "上一年"]

sys.stdout.reconfigure(encoding="utf-8")

idx = pl.read_parquet(os.path.join(FEAT, "row_index.parquet"))
batch = idx.filter(pl.col("batch_id") == 35)
meta = {r["ordinal"]: r for r in batch.iter_rows(named=True)}

reasons = {}
for fp in sorted(glob.glob(os.path.join(RAW, "chunk_*.csv"))):
    with open(fp, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                   (r.get("ann_date") or "").strip(),
                   (r.get("update_flag") or "").strip())
            reasons[key] = r.get("change_reason") or ""

hits = []
for part in range(1, 7):
    with open(os.path.join(WORK, f"batch_035_judge_part{part}.jsonl"), encoding="utf-8") as f:
        for line in f:
            j = json.loads(line)
            m = meta[j["ordinal"]]
            orig = reasons.get((m["ts_code"], str(m["end_date"]), str(m["ann_date"]), str(m["update_flag"])), "")
            if j["primary_code"] in ("non_recurring", "impairment") and j["supports_direction"] == 0 \
                    and any(k in orig for k in KEYWORDS):
                hits.append({
                    "ordinal": j["ordinal"], "part": part,
                    "primary": j["primary_code"], "secondary": j["secondary_code"],
                    "key_quote": j["key_quote"], "confidence": j["confidence"],
                    "ts_code": m["ts_code"], "end_date": str(m["end_date"]),
                    "type": m.get("type"),
                    "reason": orig,
                })

print(f"TOTAL HITS: {len(hits)}")
for h in hits:
    print("=" * 80)
    print(f"ordinal={h['ordinal']} part={h['part']} primary={h['primary']} secondary={h['secondary']} type={h['type']}")
    print(f"ts_code={h['ts_code']} end_date={h['end_date']} quote={h['key_quote']}")
    print(f"REASON: {h['reason']}")
