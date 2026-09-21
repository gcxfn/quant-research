# -*- coding: utf-8 -*-
"""批 30 基数嫌疑目标行复现：primary in {non_recurring, impairment} 且 sd==0
且原始 change_reason 含 上年/同期。沿自批 34 t1_find_targets.py，基 17400。"""
import csv
import json
from pathlib import Path

REPO = Path(r"D:/量化")
BATCH = REPO / "data/features/fcst-reason-struct-full-20260918/batch_030.jsonl"
RAW_DIR = REPO / "data/raw/tushare/forecast/20260909-r1"
OUT = REPO / "artifacts/runs/20260919T231937-fcst-w30-467c/tmp/targets_30.json"

rows = [json.loads(l) for l in BATCH.read_text(encoding="utf-8").splitlines() if l.strip()]
assert len(rows) == 600, len(rows)

raw_map = {}
type_map = {}
for f in sorted(RAW_DIR.glob("chunk_*.csv")):
    with open(f, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["ts_code"], r["end_date"], r["ann_date"], r["update_flag"])
            raw_map[key] = r["change_reason"]
            type_map[key] = r["type"]

targets = []
missing = []
for i, row in enumerate(rows):
    if row["primary_code"] not in ("non_recurring", "impairment") or row["supports_direction"] != 0:
        continue
    key = (row["ts_code"], row["end_date"], row["ann_date"], row["update_flag"])
    reason = raw_map.get(key)
    if reason is None:
        missing.append((17400 + i, key))
        continue
    if ("上年" in reason) or ("同期" in reason):
        targets.append({
            "ordinal": 17400 + i,
            "type": type_map.get(key),
            "primary_code": row["primary_code"],
            "secondary_code": row["secondary_code"],
            "key_quote": row["key_quote"],
            "change_reason": reason,
        })

OUT.write_text(json.dumps(targets, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"batch rows={len(rows)}  targets={len(targets)}  missing_raw={len(missing)}")
print(f"primary 分布: non_recurring={sum(1 for t in targets if t['primary_code']=='non_recurring')}, impairment={sum(1 for t in targets if t['primary_code']=='impairment')}")
print(f"type 分布: {sorted(set(t['type'] for t in targets))}")
