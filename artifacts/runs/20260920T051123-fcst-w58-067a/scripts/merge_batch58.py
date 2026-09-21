#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-58 专用：把 6 段逐行结构化判断(batch_058_judge_partN.jsonl)与 row_index 元信息
程序化合并为 batch_058_partN.jsonl（全字段），并做合并前预校验：
- ordinal 连续且与 row_index batch_id=28 的 batch_idx 顺序一一对应
- 元信息 ts_code/end_date/ann_date/update_flag 直接取自 row_index（与渲染输入同源，零手抄）
- key_quote 必须是 raw change_reason 的逐字子串（对原始 CSV 反向校验，与
  check_batch_full 同口径预检）

沿自 wave-24 merge_batch24.py，仅改 batch=24→25、ordinal 基 13800→16200、
文件名 batch_024→batch_058，校验逻辑逐行保留（含冻结区断言）。

用法: python merge_batch28.py --repo-root D:/量化
产物: work/batch_058_part1..6.jsonl、data/features/fcst-reason-struct-full-20260918/batch_058.jsonl
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
    args = ap.parse_args()
    root = os.path.abspath(args.repo_root)
    run_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    work = os.path.join(run_dir, "work")
    features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-full-20260918")
    raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")

    idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
    batch = idx.filter(pl.col("batch_id") == 58).sort("batch_idx")
    meta = {r["ordinal"]: r for r in batch.iter_rows(named=True)}
    # 冻结区断言：本批不得含 ann_date >= 20250101 的行
    frozen = [m["ordinal"] for m in meta.values() if str(m["ann_date"]) >= "20250101"]
    if frozen:
        print("FROZEN-ZONE VIOLATION (ann_date>=20250101):", frozen)
        raise SystemExit(1)
    reasons = load_reasons(raw_dir)

    fails = []
    merged = []
    for part in range(1, 7):
        jpath = os.path.join(work, f"batch_058_judge_part{part}.jsonl")
        with open(jpath, encoding="utf-8") as f:
            judges = [json.loads(x) for x in f.read().splitlines() if x.strip()]
        expect_lo = 34200 + (part - 1) * 100
        if [j["ordinal"] for j in judges] != list(range(expect_lo, expect_lo + 100)):
            fails.append(f"part{part}: ordinal sequence mismatch")
            continue
        out_lines = []
        for j in judges:
            m = meta[j["ordinal"]]
            key = (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"])
            rec = {
                "ts_code": m["ts_code"],
                "end_date": m["end_date"],
                "ann_date": m["ann_date"],
                "update_flag": m["update_flag"],
                "primary_code": j["primary_code"],
                "secondary_code": j["secondary_code"],
                "supports_direction": j["supports_direction"],
                "key_quote": j["key_quote"],
                "confidence": j["confidence"],
                "struct_version": "llm-v1",
            }
            oid = j["ordinal"]
            if rec["primary_code"] not in VOCAB:
                fails.append(f"ordinal {oid:05d}: primary not in vocab")
            if rec["secondary_code"] is not None and rec["secondary_code"] not in VOCAB:
                fails.append(f"ordinal {oid:05d}: secondary not in vocab")
            if rec["secondary_code"] is not None and rec["secondary_code"] == rec["primary_code"]:
                fails.append(f"ordinal {oid:05d}: secondary == primary")
            if rec["supports_direction"] not in (-1, 0, 1):
                fails.append(f"ordinal {oid:05d}: sd invalid")
            if rec["confidence"] not in ("high", "low"):
                fails.append(f"ordinal {oid:05d}: confidence invalid")
            q = rec["key_quote"]
            if not q or len(q) > 40:
                fails.append(f"ordinal {oid:05d}: key_quote empty or len {len(q)} > 40")
            else:
                orig = reasons.get(key)
                if orig is None:
                    fails.append(f"ordinal {oid:05d}: raw row missing")
                elif q not in orig:
                    fails.append(f"ordinal {oid:05d}: quote NOT verbatim; quote={q!r}; orig={orig[:60]!r}")
            out_lines.append(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
        with open(os.path.join(work, f"batch_058_part{part}.jsonl"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write("\n".join(out_lines) + "\n")
        merged += out_lines

    if fails:
        print("PRECHECK FAILURES:", len(fails))
        for x in fails:
            print("FAIL:", x)
        raise SystemExit(1)
    out = os.path.join(features_dir, "batch_058.jsonl")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(merged) + "\n")
    print(json.dumps({
        "merged_rows": len(merged),
        "part_files": [f"batch_058_part{i}.jsonl" for i in range(1, 7)],
        "output": os.path.relpath(out, root).replace("\\", "/"),
        "precheck": "OK (600/600, quotes verbatim, vocab closed, secondary!=primary, frozen-zone clear)",
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
