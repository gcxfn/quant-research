#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性分层抽样：业绩预告 change_reason LLM 结构化 pilot。

规则（一次性定死）：
- 数据源: data/raw/tushare/forecast/20260909-r1/chunk_*.csv（97 个月块，只读）
- 池: ann_date <= 20241231 且 change_reason 非空(strip 后非空)
- ann_date >= 20250101 一行不进入（冻结区），排除数写入统计
- 分层: (type 枚举 x ann_date 年份)，比例分配 + 最大余数法，每非空层至少 1，上限为层大小
- 种子 17，层内按 (ts_code, ann_date, end_date, update_flag) 排序后
  numpy default_rng(17).choice 无放回抽取；层按 (type, year) 升序遍历
- 输出 600 行、3 批 x 200 行；同输入重跑结果逐字节一致

产物：
- features_dir/sample_manifest.json  规则+种子+计数+600 行主键
- work_dir/batch_NN_input.txt        供 LLM 逐批阅读的渲染文件
- work_dir/sampling_stats.json       过滤计数、层表、文本长度统计
- work_dir/input_identity.json       输入文件 sha256 身份
"""
import argparse
import csv
import glob
import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import numpy as np

SEED = 17
N_TARGET = 600
BATCH_SIZE = 200
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
        root, "data", "features", "fcst-reason-struct-pilot-20260918")
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
                    "change_reason": cr,
                    "source_file": fname,
                })

    # 主键唯一性断言（ts_code, ann_date, end_date, update_flag）
    keys = [(x["ts_code"], x["ann_date"], x["end_date"], x["update_flag"]) for x in rows]
    if len(set(keys)) != len(keys):
        raise SystemExit("duplicate primary keys in pool; sampler must be revised")

    strata = {}
    for x in rows:
        strata.setdefault((x["type"], x["ann_date"][:4]), []).append(x)
    strat_keys = sorted(strata.keys())
    N = len(rows)

    # 比例分配 + 最大余数法；每非空层至少 1；不超过层大小；总和恰为 N_TARGET
    quota = {k: len(strata[k]) * N_TARGET / N for k in strat_keys}
    alloc = {k: min(len(strata[k]), max(1, int(quota[k] // 1))) for k in strat_keys}
    resid = N_TARGET - sum(alloc.values())
    frac_desc = sorted(strat_keys, key=lambda k: (-(quota[k] - int(quota[k])), k))
    frac_asc = list(reversed(frac_desc))
    i = 0
    guard = 0
    while resid != 0 and guard < 1000000:
        k = (frac_desc if resid > 0 else frac_asc)[i % len(frac_desc)]
        if resid > 0 and alloc[k] < len(strata[k]):
            alloc[k] += 1
            resid -= 1
        elif resid < 0 and alloc[k] > 1:
            alloc[k] -= 1
            resid += 1
        i += 1
        guard += 1
    if sum(alloc.values()) != N_TARGET:
        raise SystemExit(f"allocation sums to {sum(alloc.values())}, expected {N_TARGET}")

    rng = np.random.default_rng(SEED)
    sampled = []
    for k in strat_keys:
        cand = sorted(
            strata[k],
            key=lambda x: (x["ts_code"], x["ann_date"], x["end_date"], x["update_flag"]))
        n_h = alloc[k]
        idx = rng.choice(len(cand), size=n_h, replace=False)
        for j in sorted(int(t) for t in idx):
            sampled.append(cand[j])

    manifest_rows = []
    for ordinal, x in enumerate(sampled):
        manifest_rows.append({
            "ordinal": ordinal,
            "batch": ordinal // BATCH_SIZE + 1,
            "ts_code": x["ts_code"],
            "ann_date": x["ann_date"],
            "end_date": x["end_date"],
            "update_flag": x["update_flag"],
            "type": x["type"],
            "source_file": x["source_file"],
            "reason_sha1_12": hashlib.sha1(x["change_reason"].encode("utf-8")).hexdigest()[:12],
            "reason_len_chars": len(x["change_reason"]),
        })

    lens = sorted(x["reason_len_chars"] for x in manifest_rows)

    def pct(p):
        return lens[min(len(lens) - 1, int(p * len(lens)))]

    manifest = {
        "pilot": "fcst-reason-struct-pilot",
        "struct_version": "llm-v1",
        "created_at": datetime.now(CST).isoformat(timespec="seconds"),
        "seed": SEED,
        "n_target": N_TARGET,
        "n_batches": N_TARGET // BATCH_SIZE,
        "batch_size": BATCH_SIZE,
        "raw_dataset": "tushare forecast 20260909-r1 (97 monthly chunks)",
        "sampling_rules": (
            "pool = ann_date<=20241231 AND change_reason non-empty; "
            "strata=(type x ann_date year); proportional largest-remainder allocation, "
            "min 1 per non-empty stratum, cap at stratum size; within stratum rows sorted by "
            "(ts_code, ann_date, end_date, update_flag) then numpy default_rng(17) choice "
            "without replacement; strata traversed in (type, year) ascending order; "
            "ordinal 0..599 in traversal order; batch = ordinal // 200 + 1"
        ),
        "filter_counts": {
            "total_rows_all_chunks": n_total,
            "pool_rows": N,
            "excluded_ann_date_ge_2025_with_reason": n_ge2025_nonempty,
            "excluded_ann_date_le_2024_change_reason_empty": n_le2024_empty,
            "excluded_ann_date_missing_or_invalid": n_missing_anndate,
            "of_which_invalid_anndate_but_reason_nonempty": n_anndate_bad,
        },
        "pool_reason_len_chars": None,
        "strata": [
            {"type": t, "year": y, "pool_n": len(strata[(t, y)]), "sampled_n": alloc[(t, y)]}
            for (t, y) in strat_keys
        ],
        "rows": manifest_rows,
    }

    # 池级文本长度统计（供吞吐外推）
    pool_lens = sorted(len(x["change_reason"]) for x in rows)

    def ppct(p):
        return pool_lens[min(len(pool_lens) - 1, int(p * len(pool_lens)))]

    manifest["pool_reason_len_chars"] = {
        "mean": round(sum(pool_lens) / len(pool_lens), 1),
        "p50": ppct(0.50),
        "p90": ppct(0.90),
        "p99": ppct(0.99),
        "max": pool_lens[-1],
    }

    with open(os.path.join(features_dir, "sample_manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    # 渲染 LLM 阅读用输入文件（每批一份）
    header = (
        "# fcst-reason-struct-pilot 输入渲染（由 sample_fcst_reason_pilot.py seed=17 生成）\n"
        "# 每条记录两行：元信息行 + REASON 行。key_quote 必须是 REASON 文本的逐字子串。\n"
        "# 词表: demand_up/demand_down/price_up/price_down/orders/cost_up/cost_down/fx/impairment/\n"
        "#       non_recurring/ma_restructuring/epidemic_shock/accounting/core_ops/other\n"
    )
    for b in range(1, N_TARGET // BATCH_SIZE + 1):
        lines = [header]
        for x in manifest_rows:
            if x["batch"] != b:
                continue
            src = next(r for r in sampled if
                       (r["ts_code"], r["ann_date"], r["end_date"], r["update_flag"])
                       == (x["ts_code"], x["ann_date"], x["end_date"], x["update_flag"]))
            lines.append(
                f"### ordinal={x['ordinal']:03d} type={x['type']} ts_code={x['ts_code']} "
                f"end_date={x['end_date']} ann_date={x['ann_date']} update_flag={x['update_flag']}\n"
                f"REASON: {src['change_reason']}\n\n")
        with open(os.path.join(work_dir, f"batch_{b:02d}_input.txt"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write("".join(lines))

    stats = {
        "run_note": "sampling stats for pilot",
        "filter_counts": manifest["filter_counts"],
        "n_strata": len(strat_keys),
        "sample_reason_len_chars": {
            "mean": round(sum(lens) / len(lens), 1), "p50": pct(0.50),
            "p90": pct(0.90), "p99": pct(0.99), "max": lens[-1]},
        "pool_reason_len_chars": manifest["pool_reason_len_chars"],
        "type_totals_pool": {},
    }
    tt = {}
    for x in rows:
        tt[x["type"]] = tt.get(x["type"], 0) + 1
    stats["type_totals_pool"] = dict(sorted(tt.items(), key=lambda kv: -kv[1]))
    with open(os.path.join(work_dir, "sampling_stats.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, ensure_ascii=False, indent=1)
    with open(os.path.join(work_dir, "input_identity.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(input_identity, f, ensure_ascii=False, indent=1)

    print(json.dumps({
        "n_files": len(files),
        "total_rows": n_total,
        "pool_rows": N,
        "excluded_2025plus": n_ge2025_nonempty,
        "excluded_empty_reason": n_le2024_empty,
        "n_strata": len(strat_keys),
        "sampled": len(manifest_rows),
        "sample_reason_len_mean": stats["sample_reason_len_chars"]["mean"],
        "pool_reason_len_mean": manifest["pool_reason_len_chars"]["mean"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
