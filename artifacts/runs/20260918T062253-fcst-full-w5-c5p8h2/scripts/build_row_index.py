#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量结构化确定性全序清单（fcst-reason-struct-full, struct_version=llm-v1）。

与 pilot（sample_fcst_reason_pilot.py, seed=17）同一分层框架，展开为全序：
- 数据源: data/raw/tushare/forecast/20260909-r1/chunk_*.csv（97 个月块，只读）
- 池: ann_date <= 20241231 且 change_reason 非空(strip 后非空)，= 38,567 行
- 分层: (type 枚举 x ann_date 年份)，与 pilot 相同的 63 层
- 比例分配: 目标 = 全池 N（quota[k] = size[k]*N/N = size[k]，恒等分配，
  最大余数法退化为例外零调整）=> 每层全取
- 层内确定性序: (ts_code, ann_date, end_date, update_flag) 升序
  （前两列即任务规定的 ts_code, ann_date 升序；后两列为全局唯一主键的平局裁决）
- 层按 (type, year) 升序遍历，依次展开 => 全局序 ordinal 0..N-1
- batch_id = ordinal // 600 + 1（1 起）；batch_idx = ordinal % 600（0 起）
- pilot 的 rng 仅用于层内无放回抽取子集；全量分配取整层时 sorted(choice) 恒等
  于排序序，故本脚本不调用 rng，结果与 seed=17 框架一致且完全确定
- 同输入重跑逐字节一致；后续任何 wave 复用本脚本得到同一全序

产物：
- features_dir/row_index.parquet   全序清单（含 ordinal/batch_id/batch_idx、主键、
                                   type、source_file、reason_len_chars、reason_sha1_12；
                                   不含 change_reason 原文，原文以 raw CSV 为唯一事实源）
- work_dir/row_index_stats.json    过滤计数、层表、文本长度统计
- work_dir/input_identity.json     输入文件逐个 sha256 身份

用法: python build_row_index.py --repo-root D:/量化
"""
import argparse
import csv
import glob
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import polars as pl

SEED = 17  # 记录分层框架来源（pilot seed=17）；全序生成本身无随机成分
BATCH_SIZE = 600
CUTOFF = 20241231
CUTOFF_GE = 20250101

CST = timezone(timedelta(hours=8))


def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
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
    os.makedirs(features_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)

    files = sorted(glob.glob(os.path.join(raw_dir, "chunk_*.csv")))
    if not files:
        raise SystemExit(f"no chunk_*.csv under {raw_dir}")

    input_identity = {
        "raw_dir": os.path.relpath(raw_dir, root).replace("\\", "/"),
        "n_files": len(files),
        "files": [],
    }
    rows = []
    n_total = 0
    n_missing_anndate = 0
    n_ge2025_nonempty = 0
    n_le2024_empty = 0
    n_anndate_bad = 0
    for fp in files:
        fname = os.path.basename(fp)
        input_identity["files"].append(
            {"file": fname, "sha256": sha256_file(fp)})
        with open(fp, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                n_total += 1
                ad = (r.get("ann_date") or "").strip()
                cr = r.get("change_reason") or ""
                cr_nonempty = cr.strip() != ""
                if not ad.isdigit() or len(ad) != 8:
                    n_missing_anndate += 1
                    if cr_nonempty:
                        n_anndate_bad += 1
                    continue
                adv = int(ad)
                if adv >= CUTOFF_GE:
                    if cr_nonempty:
                        n_ge2025_nonempty += 1
                    continue
                if not cr_nonempty:
                    n_le2024_empty += 1
                    continue
                rows.append({
                    "ts_code": r["ts_code"].strip(),
                    "ann_date": ad,
                    "end_date": (r.get("end_date") or "").strip(),
                    "type": (r.get("type") or "").strip(),
                    "update_flag": (r.get("update_flag") or "").strip(),
                    "source_file": fname,
                    "reason_len_chars": len(cr),
                    "reason_sha1_12": hashlib.sha1(cr.encode("utf-8")).hexdigest()[:12],
                })

    # 主键唯一性断言（ts_code, ann_date, end_date, update_flag）
    keys = [(x["ts_code"], x["ann_date"], x["end_date"], x["update_flag"]) for x in rows]
    if len(set(keys)) != len(keys):
        raise SystemExit("duplicate primary keys in pool; row index must not be built")
    N = len(rows)

    strata = {}
    for x in rows:
        strata.setdefault((x["type"], x["ann_date"][:4]), []).append(x)
    strat_keys = sorted(strata.keys())

    # 比例分配（目标 = N）：quota[k] = size[k]*N/N 恒等于 size[k]，恒等分配
    alloc = {k: len(strata[k]) for k in strat_keys}
    if sum(alloc.values()) != N or any(alloc[k] != len(strata[k]) for k in strat_keys):
        raise SystemExit("full allocation is not identity; logic error")

    # 层按 (type, year) 升序遍历；层内 (ts_code, ann_date, end_date, update_flag) 升序
    ord_rows = []
    ordinal = 0
    for k in strat_keys:
        cand = sorted(
            strata[k],
            key=lambda x: (x["ts_code"], x["ann_date"], x["end_date"], x["update_flag"]))
        for x in cand:
            x["ordinal"] = ordinal
            x["batch_id"] = ordinal // BATCH_SIZE + 1
            x["batch_idx"] = ordinal % BATCH_SIZE
            ord_rows.append(x)
            ordinal += 1
    if ordinal != N:
        raise SystemExit(f"ordinal expansion {ordinal} != pool {N}")

    schema = {
        "ordinal": pl.UInt32,
        "batch_id": pl.UInt32,
        "batch_idx": pl.UInt32,
        "ts_code": pl.Utf8,
        "end_date": pl.Utf8,
        "ann_date": pl.Utf8,
        "update_flag": pl.Utf8,
        "type": pl.Utf8,
        "source_file": pl.Utf8,
        "reason_len_chars": pl.UInt32,
        "reason_sha1_12": pl.Utf8,
    }
    df = pl.from_dicts(ord_rows, schema=schema).sort("ordinal")
    out_parquet = os.path.join(features_dir, "row_index.parquet")
    df.write_parquet(out_parquet, compression="zstd")

    pool_lens = sorted(x["reason_len_chars"] for x in rows)

    def ppct(p):
        return pool_lens[min(len(pool_lens) - 1, int(p * len(pool_lens)))]

    stats = {
        "feature_set": "fcst-reason-struct-full-20260918",
        "struct_version": "llm-v1",
        "created_at": datetime.now(CST).isoformat(timespec="seconds"),
        "seed_note": "stratification framework inherited from pilot seed=17; "
                     "full-order expansion itself is deterministic (no rng call)",
        "batch_size": BATCH_SIZE,
        "pool_rows": N,
        "n_batches": (N + BATCH_SIZE - 1) // BATCH_SIZE,
        "last_batch_rows": N - (N // BATCH_SIZE) * BATCH_SIZE or BATCH_SIZE,
        "ordering_rules": (
            "pool = ann_date<=20241231 AND change_reason non-empty; "
            "strata=(type x ann_date year) in (type, year) ascending traversal; "
            "full allocation (target=N, identity per stratum); within stratum sorted by "
            "(ts_code, ann_date, end_date, update_flag) ascending"),
        "filter_counts": {
            "total_rows_all_chunks": n_total,
            "pool_rows": N,
            "excluded_ann_date_ge_2025_with_reason": n_ge2025_nonempty,
            "excluded_ann_date_le_2024_change_reason_empty": n_le2024_empty,
            "excluded_ann_date_missing_or_invalid": n_missing_anndate,
            "of_which_invalid_anndate_but_reason_nonempty": n_anndate_bad,
        },
        "n_strata": len(strat_keys),
        "strata": [
            {"type": t, "year": y, "pool_n": len(strata[(t, y)])}
            for (t, y) in strat_keys
        ],
        "pool_reason_len_chars": {
            "mean": round(sum(pool_lens) / len(pool_lens), 1),
            "p50": ppct(0.50), "p90": ppct(0.90),
            "p99": ppct(0.99), "max": pool_lens[-1],
        },
        "row_index_parquet_sha256": sha256_file(out_parquet),
    }
    with open(os.path.join(work_dir, "row_index_stats.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    with open(os.path.join(work_dir, "input_identity.json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(input_identity, f, ensure_ascii=False, indent=1)

    print(json.dumps({
        "n_files": len(files),
        "total_rows": n_total,
        "pool_rows": N,
        "excluded_2025plus": n_ge2025_nonempty,
        "excluded_empty_reason": n_le2024_empty,
        "n_strata": len(strat_keys),
        "n_batches": stats["n_batches"],
        "last_batch_rows": stats["last_batch_rows"],
        "pool_reason_len_mean": stats["pool_reason_len_chars"]["mean"],
        "pool_reason_len_max": stats["pool_reason_len_chars"]["max"],
        "row_index_parquet": os.path.relpath(out_parquet, root).replace("\\", "/"),
        "row_index_rows": df.height,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
