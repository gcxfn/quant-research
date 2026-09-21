# 主对话独立复检：对已归档 batch_NNN.jsonl 重算主键与逐字引用
# 用法: python accept_recheck.py <batch>
import csv
import glob
import json
import os
import sys

import polars as pl

batch = int(sys.argv[1])
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

idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
b = idx.filter(pl.col("batch_id") == batch).sort("batch_idx")
meta = {r["ordinal"]: r for r in b.iter_rows(named=True)}
lo = min(meta)

with open(os.path.join(features_dir, f"batch_{batch:03d}.jsonl"), encoding="utf-8") as f:
    rows = [json.loads(x) for x in f if x.strip()]

assert len(rows) == 600, f"row count {len(rows)} != 600"
bad_pk = bad_verb = bad_frozen = 0
for i, rec in enumerate(rows):
    oid = lo + i
    m = meta[oid]
    if (rec["ts_code"], str(rec["end_date"]), str(rec["ann_date"]), str(rec["update_flag"])) != \
       (m["ts_code"], str(m["end_date"]), str(m["ann_date"]), str(m["update_flag"])):
        bad_pk += 1
    if str(m["ann_date"]) >= "20250101":
        bad_frozen += 1
    orig = reasons[(rec["ts_code"], str(rec["end_date"]), str(rec["ann_date"]), str(rec["update_flag"]))]
    if rec["key_quote"] not in orig:
        bad_verb += 1

from collections import Counter
pc = Counter(r["primary_code"] for r in rows)
sd = Counter(r["supports_direction"] for r in rows)
cf = Counter(r["confidence"] for r in rows)
sec_nonnull = sum(1 for r in rows if r["secondary_code"] is not None)
print(f"batch {batch}: rows={len(rows)} bad_pk={bad_pk} bad_verbatim={bad_verb} frozen_violation={bad_frozen}")
print(f"  sd={dict(sorted(sd.items()))} conf={dict(cf)} secondary_nonnull={sec_nonnull}")
print(f"  primary={dict(sorted(pc.items(), key=lambda x: -x[1]))}")
