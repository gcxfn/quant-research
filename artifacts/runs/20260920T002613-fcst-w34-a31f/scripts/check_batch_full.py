#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单批结构化结果校验（fcst-reason-struct-full, struct_version=llm-v1）。

与 pilot check_batch.py 同一校验逻辑，适配全量：
- 行清单来自 row_index.parquet（batch_id 过滤、batch_idx 升序），而非 sample_manifest
- 行数 = 该批 batch 行数（600；末批 167）
- 校验项与 pilot 完全一致：主键对齐、字段齐全、词表闭合、secondary≠primary、
  supports_direction/confidence/struct_version 合法、key_quote 原文逐字子串
  （≤40 且 >0）

用法: python check_batch_full.py --repo-root D:/量化 --batch 1
退出码: 0 全部通过；1 有失败（打印逐条失败原因）
"""
import argparse
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
REQUIRED = ["ts_code", "end_date", "ann_date", "update_flag", "primary_code",
            "secondary_code", "supports_direction", "key_quote", "confidence",
            "struct_version"]


def load_reasons(raw_dir):
    reasons = {}
    for fp in sorted(glob.glob(os.path.join(raw_dir, "chunk_*.csv"))):
        with open(fp, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                key = (r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                       (r.get("ann_date") or "").strip(),
                       (r.get("update_flag") or "").strip())
                reasons[key] = r.get("change_reason") or ""
    return reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--batch", type=int, required=True)
    args = ap.parse_args()
    root = os.path.abspath(args.repo_root)
    features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-full-20260918")
    raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")

    idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
    expect = (idx.filter(pl.col("batch_id") == args.batch).sort("batch_idx")
              .select(["ordinal", "ts_code", "end_date", "ann_date", "update_flag"])
              .rows(named=True))
    reasons = load_reasons(raw_dir)

    path = os.path.join(features_dir, f"batch_{args.batch:03d}.jsonl")
    fails = []
    if not os.path.exists(path):
        print(f"batch {args.batch:03d}: file missing")
        raise SystemExit(1)
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    if len(lines) != len(expect):
        fails.append(f"batch {args.batch:03d}: line count {len(lines)} != {len(expect)}")
    n = 0
    for i, ln in enumerate(lines):
        try:
            obj = json.loads(ln)
        except Exception as e:
            fails.append(f"batch {args.batch:03d} line {i+1}: JSON parse error {e}")
            continue
        n += 1
        if i >= len(expect):
            fails.append(f"batch {args.batch:03d} line {i+1}: extra line beyond row_index")
            continue
        mrow = expect[i]
        oid = mrow["ordinal"]
        for k in REQUIRED:
            if k not in obj:
                fails.append(f"ordinal {oid:05d}: missing field {k}")
        key = (obj.get("ts_code"), obj.get("end_date"), obj.get("ann_date"),
               obj.get("update_flag"))
        mkey = (mrow["ts_code"], mrow["end_date"], mrow["ann_date"], mrow["update_flag"])
        if key != mkey:
            fails.append(f"ordinal {oid:05d}: key {key} != row_index {mkey}")
        pc = obj.get("primary_code")
        sc = obj.get("secondary_code")
        if pc not in VOCAB:
            fails.append(f"ordinal {oid:05d}: primary_code '{pc}' not in vocab")
        if sc is not None and sc not in VOCAB:
            fails.append(f"ordinal {oid:05d}: secondary_code '{sc}' not in vocab/null")
        if sc is not None and sc == pc:
            fails.append(f"ordinal {oid:05d}: secondary_code equals primary_code")
        sd = obj.get("supports_direction")
        if sd not in (-1, 0, 1):
            fails.append(f"ordinal {oid:05d}: supports_direction {sd!r} invalid")
        cf = obj.get("confidence")
        if cf not in ("high", "low"):
            fails.append(f"ordinal {oid:05d}: confidence {cf!r} invalid")
        if obj.get("struct_version") != "llm-v1":
            fails.append(f"ordinal {oid:05d}: struct_version != llm-v1")
        q = obj.get("key_quote", "")
        if not q:
            fails.append(f"ordinal {oid:05d}: key_quote empty")
        elif len(q) > 40:
            fails.append(f"ordinal {oid:05d}: key_quote length {len(q)} > 40")
        else:
            orig = reasons.get(mkey)
            if orig is None:
                fails.append(f"ordinal {oid:05d}: original row not found in raw CSVs")
            elif q not in orig:
                fails.append(f"ordinal {oid:05d}: key_quote NOT verbatim substring of "
                             f"change_reason; quote={q!r}; original={orig[:80]!r}...")
    for f_ in fails:
        print("FAIL:", f_)
    print(f"batch {args.batch:03d}: {n} rows checked -> "
          f"{'OK' if not fails else f'{len(fails)} FAILURES'}")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
