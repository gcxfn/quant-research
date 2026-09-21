#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-34 标注代理自用：读取 judge34_data_a/b.json 的 600 行判定，
对 row_index(batch_id=34) 与 raw CSV 原文做与 merge/check 同口径的预校验
（词表闭合、secondary!=primary、sd/confidence 合法、key_quote 逐字子串且<=40），
全部通过后写出 batch_034_judge_part1..6.jsonl 并打印统计。
用法: python build_judge34.py
"""
import csv
import glob
import json
import os
from collections import Counter

import polars as pl

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(RUN_DIR, "..", "..", ".."))
FEATURES = os.path.join(REPO, "data", "features", "fcst-reason-struct-full-20260918")
RAW = os.path.join(REPO, "data", "raw", "tushare", "forecast", "20260909-r1")
VOCAB = {
    "demand_up", "demand_down", "price_up", "price_down", "orders",
    "cost_up", "cost_down", "fx", "impairment", "non_recurring",
    "ma_restructuring", "epidemic_shock", "accounting", "core_ops", "other",
}


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
    rows = []
    for name in ("judge34_data_a.json", "judge34_data_b.json"):
        with open(os.path.join(HERE, name), encoding="utf-8") as f:
            rows.extend(json.load(f))
    if [r[0] for r in rows] != list(range(19800, 20400)):
        print("FATAL: ordinal sequence mismatch in data files")
        raise SystemExit(1)

    idx = pl.read_parquet(os.path.join(FEATURES, "row_index.parquet"))
    batch = idx.filter(pl.col("batch_id") == 34).sort("batch_idx")
    meta = {r["ordinal"]: r for r in batch.iter_rows(named=True)}
    if len(meta) != 600:
        print(f"FATAL: batch_id=34 rows {len(meta)} != 600")
        raise SystemExit(1)
    reasons = load_reasons(RAW)

    fails = []
    recs = {}
    for oid, p, s, sd, q, cf in rows:
        if p not in VOCAB:
            fails.append(f"ordinal {oid:05d}: primary not in vocab")
        if s is not None and s not in VOCAB:
            fails.append(f"ordinal {oid:05d}: secondary not in vocab")
        if s is not None and s == p:
            fails.append(f"ordinal {oid:05d}: secondary == primary")
        if sd not in (-1, 0, 1):
            fails.append(f"ordinal {oid:05d}: sd invalid")
        if cf not in ("high", "low"):
            fails.append(f"ordinal {oid:05d}: confidence invalid")
        if not q or len(q) > 40:
            fails.append(f"ordinal {oid:05d}: quote empty or len {len(q)} > 40")
            continue
        m = meta.get(oid)
        if m is None:
            fails.append(f"ordinal {oid:05d}: not in row_index batch 34")
            continue
        key = (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"])
        orig = reasons.get(key)
        if orig is None:
            fails.append(f"ordinal {oid:05d}: raw row missing")
        elif q not in orig:
            fails.append(f"ordinal {oid:05d}: quote NOT verbatim; quote={q!r}; orig-head={orig[:60]!r}")
        else:
            recs[oid] = {"ordinal": oid, "primary_code": p, "secondary_code": s,
                         "supports_direction": sd, "key_quote": q, "confidence": cf}
    if fails:
        print("PRECHECK FAILURES:", len(fails))
        for x in fails:
            print("FAIL:", x)
        raise SystemExit(1)

    for part in range(1, 7):
        lo = 19800 + (part - 1) * 100
        path = os.path.join(HERE, f"batch_034_judge_part{part}.jsonl")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            for oid in range(lo, lo + 100):
                f.write(json.dumps(recs[oid], ensure_ascii=False,
                                   separators=(",", ":")) + "\n")

    pc = Counter(r[1] for r in rows)
    sc_null = sum(1 for r in rows if r[2] is None)
    sd = Counter(r[3] for r in rows)
    cf = Counter(r[5] for r in rows)
    print(json.dumps({
        "rows": len(rows),
        "primary": dict(sorted(pc.items(), key=lambda kv: -kv[1])),
        "secondary_null": sc_null,
        "supports_direction": {"+1": sd[1], "0": sd[0], "-1": sd[-1]},
        "confidence": dict(cf),
    }, ensure_ascii=False))
    print("WROTE batch_034_judge_part1..6.jsonl (600 rows)")


if __name__ == "__main__":
    main()
