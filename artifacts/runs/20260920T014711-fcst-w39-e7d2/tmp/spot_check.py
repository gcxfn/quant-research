# 语义抽检：基数类关键词扫描（按语义人工复核）+ 指定行明细
# 用法: python spot_check.py <batch> [ordinal ...]
import csv
import glob
import json
import os
import re
import sys

batch = int(sys.argv[1])
picks = [int(x) for x in sys.argv[2:]]
root = "D:/量化"
features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-full-20260918")
raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")

reasons = {}
for fp in sorted(glob.glob(os.path.join(raw_dir, "chunk_*.csv"))):
    with open(fp, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                   (r.get("ann_date") or "").strip(),
                   (r.get("update_flag") or "").strip())
            reasons[key] = r.get("change_reason") or ""

idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet")) if False else None
import polars as pl
idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
b = idx.filter(pl.col("batch_id") == batch).sort("batch_idx")
meta = {r["ordinal"]: r for r in b.iter_rows(named=True)}
lo = min(meta)

with open(os.path.join(features_dir, f"batch_{batch:03d}.jsonl"), encoding="utf-8") as f:
    rows = [json.loads(x) for x in f if x.strip()]

# 基数类语义扫描：上年/同期/上期/基数/具体年份 + 一次性/减值/非经常/补偿/处置/拆迁/转让
pat_base = re.compile(r"上年|去年同期|上期|基数|上一年|former")
pat_one = re.compile(r"一次性|非经常|减值|补偿|处置|拆迁|转让|政府补助|补贴|投资收益|营业外")
hits = []
for i, rec in enumerate(rows):
    oid = lo + i
    m = meta[oid]
    orig = reasons[(rec["ts_code"], str(m["end_date"]), str(m["ann_date"]), str(m["update_flag"]))]
    if pat_base.search(orig) and pat_one.search(orig):
        hits.append((oid, rec["primary_code"], rec["secondary_code"], rec["supports_direction"],
                     rec["key_quote"], orig[:110].replace("\n", " ")))
print(f"=== batch {batch}: baseline-suspect rows = {len(hits)} ===")
for h in hits:
    print(f"{h[0]} {h[1]}/{h[2]} sd={h[3]} q={h[4]}")
    print(f"    orig: {h[5]}")

if picks:
    print(f"=== picked rows ===")
    for oid in picks:
        rec = rows[oid - lo]
        m = meta[oid]
        orig = reasons[(rec["ts_code"], str(m["end_date"]), str(m["ann_date"]), str(m["update_flag"]))]
        print(f"{oid} {rec['ts_code']} {rec['primary_code']}/{rec['secondary_code']} sd={rec['supports_direction']} conf={rec['confidence']}")
        print(f"    q: {rec['key_quote']}")
        print(f"    orig: {orig[:200].replace(chr(10), ' ')}")
