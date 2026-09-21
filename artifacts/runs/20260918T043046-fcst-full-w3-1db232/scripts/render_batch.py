#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""渲染全量结构化某批的 LLM 阅读输入（fcst-reason-struct-full, llm-v1）。

与 pilot 渲染格式一致：每条记录两行（元信息行 + REASON 行），key_quote 必须是
REASON 文本的逐字子串。行序来自 row_index.parquet（build_row_index.py 的确定性
全序），按 batch_id 过滤、batch_idx 升序。

用法: python render_batch.py --repo-root D:/量化 --batch 1
产物: run work_dir/batch_NNN_input.txt（canonical 渲染文件）
"""
import argparse
import csv
import glob
import json
import os

import polars as pl

BATCH_SIZE = 600
VOCAB_LINE = ("demand_up/demand_down/price_up/price_down/orders/cost_up/cost_down/fx/"
              "impairment/non_recurring/ma_restructuring/epidemic_shock/accounting/"
              "core_ops/other")


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
    ap.add_argument("--raw-dir", default=None)
    ap.add_argument("--features-dir", default=None)
    ap.add_argument("--work-dir", default=None)
    args = ap.parse_args()

    root = os.path.abspath(args.repo_root)
    raw_dir = args.raw_dir or os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")
    features_dir = args.features_dir or os.path.join(
        root, "data", "features", "fcst-reason-struct-full-20260918")
    work_dir = args.work_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work")
    os.makedirs(work_dir, exist_ok=True)

    idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
    batch_df = idx.filter(pl.col("batch_id") == args.batch).sort("batch_idx")
    if batch_df.height == 0:
        raise SystemExit(f"batch {args.batch} not in row_index.parquet")
    reasons = load_reasons(raw_dir)

    header = (
        f"# fcst-reason-struct-full wave(batch) {args.batch:03d} 输入渲染"
        f"（由 render_batch.py 从 row_index.parquet 生成，schema v1）\n"
        f"# 每条记录两行：元信息行 + REASON 行。key_quote 必须是 REASON 文本的逐字子串。\n"
        f"# 词表: {VOCAB_LINE}\n"
    )
    lines = [header]
    n_missing = 0
    for r in batch_df.iter_rows(named=True):
        key = (r["ts_code"], r["end_date"], r["ann_date"], r["update_flag"])
        reason = reasons.get(key)
        if reason is None:
            n_missing += 1
            raise SystemExit(f"ordinal {r['ordinal']}: key {key} not found in raw CSVs")
        lines.append(
            f"### ordinal={r['ordinal']:05d} type={r['type']} ts_code={r['ts_code']} "
            f"end_date={r['end_date']} ann_date={r['ann_date']} update_flag={r['update_flag']}\n"
            f"REASON: {reason}\n\n")
    out = os.path.join(work_dir, f"batch_{args.batch:03d}_input.txt")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(lines))
    print(json.dumps({
        "batch": args.batch,
        "rows_rendered": batch_df.height,
        "n_missing_in_raw": n_missing,
        "output": os.path.relpath(out, root).replace("\\", "/"),
        "chars": sum(len(x) for x in lines),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
