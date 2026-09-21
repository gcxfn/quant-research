# -*- coding: utf-8 -*-
"""复现批 34 基数嫌疑目标行：primary in {non_recurring, impairment} 且 sd==0 且原始 change_reason 含 上年/同期。"""
import csv
import json
import sys
from pathlib import Path

REPO = Path(r"D:/量化")
BATCH = REPO / "data/features/fcst-reason-struct-full-20260918/batch_034.jsonl"
RAW_DIR = REPO / "data/raw/tushare/forecast/20260909-r1"
OUT = REPO / "artifacts/runs/20260920T002613-fcst-w34-a31f/tmp/targets_34.json"

rows = [json.loads(l) for l in BATCH.read_text(encoding="utf-8").splitlines() if l.strip()]
assert len(rows) == 600, len(rows)

# 原始 change_reason 反查表
raw_map = {}
for f in sorted(RAW_DIR.glob("chunk_*.csv")):
    with open(f, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["ts_code"], r["end_date"], r["ann_date"], r["update_flag"])
            raw_map[key] = r["change_reason"]

targets = []
missing = []
for i, row in enumerate(rows):
    if row["primary_code"] not in ("non_recurring", "impairment") or row["supports_direction"] != 0:
        continue
    key = (row["ts_code"], row["end_date"], row["ann_date"], row["update_flag"])
    reason = raw_map.get(key)
    if reason is None:
        missing.append((i, key))
        continue
    if ("上年" in reason) or ("同期" in reason):
        targets.append({
            "ordinal": 19800 + i,
            "type": None,
            "primary_code": row["primary_code"],
            "secondary_code": row["secondary_code"],
            "key_quote": row["key_quote"],
            "change_reason": reason,
        })

# 补 type（从 raw csv 再取一次）
type_map = {}
for f in sorted(RAW_DIR.glob("chunk_*.csv")):
    with open(f, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["ts_code"], r["end_date"], r["ann_date"], r["update_flag"])
            type_map[key] = r["type"]
for t in targets:
    key = None  # 重新取：需要 ts_code 等，直接再读 batch
for i, row in enumerate(rows):
    for t in targets:
        if t["ordinal"] == 19800 + i:
            key = (row["ts_code"], row["end_date"], row["ann_date"], row["update_flag"])
            t["type"] = type_map.get(key)

OUT.write_text(json.dumps(targets, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"batch rows={len(rows)}  targets={len(targets)}  missing_raw={len(missing)}")
print(f"primary 分布: non_recurring={sum(1 for t in targets if t['primary_code']=='non_recurring')}, impairment={sum(1 for t in targets if t['primary_code']=='impairment')}")
