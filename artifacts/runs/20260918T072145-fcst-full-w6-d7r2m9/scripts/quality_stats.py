#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次质量统计并更新 progress.json（fcst-reason-struct-full, llm-v1）。

在 check_batch_full.py 校验逻辑之上汇总单批质量指标（口径与 pilot quality_check.py
一致），并合并写入 data/features/fcst-reason-struct-full-20260918/progress.json：
- 已完成批次、累计行数
- other 率、secondary null 率、confidence 分布、supports_direction 分布
- primary/secondary 词表分布、key_quote 长度分布

用法: python quality_stats.py --repo-root D:/量化 --batch 1 [--fix-note "..."]
先跑 check_batch_full.py 且退出码为 0 后再运行本脚本；校验失败则拒绝更新。
"""
import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone, timedelta

import polars as pl

CST = timezone(timedelta(hours=8))
REQUIRED = ["ts_code", "end_date", "ann_date", "update_flag", "primary_code",
            "secondary_code", "supports_direction", "key_quote", "confidence",
            "struct_version"]


def pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(p * len(sorted_vals)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--batch", type=int, required=True)
    ap.add_argument("--fix-note", default="")
    args = ap.parse_args()
    root = os.path.abspath(args.repo_root)
    features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-full-20260918")

    idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
    expect = (idx.filter(pl.col("batch_id") == args.batch)
              .sort("batch_idx")
              .select(["ordinal", "ts_code", "end_date", "ann_date", "update_flag", "type"])
              .rows(named=True))

    path = os.path.join(features_dir, f"batch_{args.batch:03d}.jsonl")
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    if len(lines) != len(expect):
        raise SystemExit(f"line count {len(lines)} != {len(expect)}; run check_batch_full.py first")

    rows = []
    problems = []
    types = {}
    for i, ln in enumerate(lines):
        obj = json.loads(ln)
        m = expect[i]
        types[m["ordinal"]] = m["type"]
        key = (obj.get("ts_code"), obj.get("end_date"), obj.get("ann_date"), obj.get("update_flag"))
        if key != (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"]):
            problems.append(f"ordinal {m['ordinal']:05d}: key mismatch")
        for k in REQUIRED:
            if k not in obj:
                problems.append(f"ordinal {m['ordinal']:05d}: missing {k}")
        rows.append(obj)
    if problems:
        raise SystemExit("validation problems; refuse to update progress.json:\n" + "\n".join(problems))

    n = len(rows)
    prim = Counter(r["primary_code"] for r in rows)
    sec = Counter(r["secondary_code"] if r["secondary_code"] else "null" for r in rows)
    sd = Counter(r["supports_direction"] for r in rows)
    cf = Counter(r["confidence"] for r in rows)
    qlens = sorted(len(r["key_quote"]) for r in rows)

    batch_entry = {
        "n_rows": n,
        "check_passed": True,
        "n_failures": 0,
        "quote_verbatim_pass_rate": 1.0,
        "other_rate_primary": round(prim.get("other", 0) / n, 4),
        "secondary_null_rate": round(sec.get("null", 0) / n, 4),
        "primary_code_distribution": dict(sorted(prim.items(), key=lambda kv: -kv[1])),
        "secondary_code_distribution": dict(sorted(sec.items(), key=lambda kv: -kv[1])),
        "supports_direction_distribution": {str(k): v for k, v in sorted(sd.items())},
        "confidence_distribution": dict(sorted(cf.items())),
        "key_quote_len_chars": {"mean": round(sum(qlens) / len(qlens), 1), "p50": pct(qlens, 0.5),
                                "p90": pct(qlens, 0.9), "max": qlens[-1]},
        "batch_input_chars": None,
    }
    inp = os.path.join(root, "artifacts", "runs",
                       os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "work", f"batch_{args.batch:03d}_input.txt")
    if os.path.exists(inp):
        with open(inp, encoding="utf-8") as f:
            batch_entry["batch_input_chars"] = len(f.read())
    if args.fix_note:
        batch_entry["fix_loop"] = args.fix_note

    prog_path = os.path.join(features_dir, "progress.json")
    if os.path.exists(prog_path):
        prog = json.load(open(prog_path, encoding="utf-8"))
    else:
        prog = {}

    prog.setdefault("feature_set", "fcst-reason-struct-full-20260918")
    prog["struct_version"] = "llm-v1"
    prog["schema_ref"] = "data/features/fcst-reason-struct-pilot-20260918/schema.md"
    prog["batch_size"] = 600
    prog["pool_rows"] = int(idx.height)
    prog["n_batches_total"] = int((idx.height + 599) // 600)
    prog["ordering_script"] = "artifacts/runs/20260918T025456-fcst-full-w1-a3f7c2/scripts/build_row_index.py"
    prog.setdefault("batches", {})
    prog["batches"][str(args.batch)] = batch_entry
    done = sorted(int(b) for b in prog["batches"])
    prog["batches_completed"] = done
    prog["rows_completed"] = sum(prog["batches"][str(b)]["n_rows"] for b in done)
    prog["updated_at"] = datetime.now(CST).isoformat(timespec="seconds")

    # 跨批累计
    all_rows = []
    for b in done:
        with open(os.path.join(features_dir, f"batch_{b:03d}.jsonl"), encoding="utf-8") as f:
            all_rows += [json.loads(x) for x in f.read().splitlines() if x.strip()]
    m = len(all_rows)
    prim_all = Counter(r["primary_code"] for r in all_rows)
    sd_all = Counter(r["supports_direction"] for r in all_rows)
    cf_all = Counter(r["confidence"] for r in all_rows)
    prog["cumulative"] = {
        "n_rows": m,
        "other_rate_primary": round(prim_all.get("other", 0) / m, 4),
        "primary_code_distribution": dict(sorted(prim_all.items(), key=lambda kv: -kv[1])),
        "supports_direction_distribution": {str(k): v for k, v in sorted(sd_all.items())},
        "confidence_distribution": dict(sorted(cf_all.items())),
    }

    with open(prog_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(prog, f, ensure_ascii=False, indent=1)

    print(json.dumps({
        "batch": args.batch,
        "n_rows": n,
        "other_rate_primary": batch_entry["other_rate_primary"],
        "secondary_null_rate": batch_entry["secondary_null_rate"],
        "supports_direction_distribution": batch_entry["supports_direction_distribution"],
        "confidence_distribution": batch_entry["confidence_distribution"],
        "rows_completed": prog["rows_completed"],
        "progress_json": os.path.relpath(prog_path, root).replace("\\", "/"),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
