#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单批/全量结构化结果校验（fcst-reason-struct-pilot, struct_version=llm-v1）。

校验项：
1. 行数 = 200 且 ordinal 顺序与 sample_manifest 一致
2. 主键 (ts_code, end_date, ann_date, update_flag) 与 manifest 逐行相等
3. 字段齐全；primary_code/secondary_code 封闭词表闭合（secondary 可为 null）
4. supports_direction ∈ {-1,0,1}；confidence ∈ {high,low}；struct_version == llm-v1
5. key_quote 为该行 change_reason 原文逐字子串（100% 通过才放行），长度 ≤40 且 >0

用法: python check_batch.py --repo-root D:/量化 [--batch N|all]
退出码: 0 全部通过；1 有失败（打印逐条失败原因）
"""
import argparse
import csv
import glob
import json
import os

VOCAB = {
    "demand_up", "demand_down", "price_up", "price_down", "orders",
    "cost_up", "cost_down", "fx", "impairment", "non_recurring",
    "ma_restructuring", "epidemic_shock", "accounting", "core_ops", "other",
}
REQUIRED = ["ts_code", "end_date", "ann_date", "update_flag", "primary_code",
            "secondary_code", "supports_direction", "key_quote", "confidence",
            "struct_version"]
BATCH_SIZE = 200


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


def check_batch(features_dir, batch, reasons, manifest_rows):
    path = os.path.join(features_dir, f"batch_{batch:02d}.jsonl")
    fails = []
    if not os.path.exists(path):
        return [f"batch {batch:02d}: file missing"], 0
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    if len(lines) != BATCH_SIZE:
        fails.append(f"batch {batch:02d}: line count {len(lines)} != {BATCH_SIZE}")
    expect = [r for r in manifest_rows if r["batch"] == batch]
    n = 0
    for i, ln in enumerate(lines):
        try:
            obj = json.loads(ln)
        except Exception as e:
            fails.append(f"batch {batch:02d} line {i+1}: JSON parse error {e}")
            continue
        n += 1
        oid = obj.get("ordinal", i + 1)
        mrow = expect[i] if i < len(expect) else None
        if mrow is None:
            fails.append(f"batch {batch:02d} line {i+1}: extra line beyond manifest")
            continue
        oid = mrow["ordinal"]
        for k in REQUIRED:
            if k not in obj:
                fails.append(f"ordinal {oid:03d}: missing field {k}")
        key = (obj.get("ts_code"), obj.get("end_date"), obj.get("ann_date"),
               obj.get("update_flag"))
        mkey = (mrow["ts_code"], mrow["end_date"], mrow["ann_date"], mrow["update_flag"])
        if key != mkey:
            fails.append(f"ordinal {oid:03d}: key {key} != manifest {mkey}")
        pc = obj.get("primary_code")
        sc = obj.get("secondary_code")
        if pc not in VOCAB:
            fails.append(f"ordinal {oid:03d}: primary_code '{pc}' not in vocab")
        if sc is not None and sc not in VOCAB:
            fails.append(f"ordinal {oid:03d}: secondary_code '{sc}' not in vocab/null")
        if sc is not None and sc == pc:
            fails.append(f"ordinal {oid:03d}: secondary_code equals primary_code")
        sd = obj.get("supports_direction")
        if sd not in (-1, 0, 1):
            fails.append(f"ordinal {oid:03d}: supports_direction {sd!r} invalid")
        cf = obj.get("confidence")
        if cf not in ("high", "low"):
            fails.append(f"ordinal {oid:03d}: confidence {cf!r} invalid")
        if obj.get("struct_version") != "llm-v1":
            fails.append(f"ordinal {oid:03d}: struct_version != llm-v1")
        q = obj.get("key_quote", "")
        if not q:
            fails.append(f"ordinal {oid:03d}: key_quote empty")
        elif len(q) > 40:
            fails.append(f"ordinal {oid:03d}: key_quote length {len(q)} > 40")
        else:
            orig = reasons.get(mkey)
            if orig is None:
                fails.append(f"ordinal {oid:03d}: original row not found in raw CSVs")
            elif q not in orig:
                fails.append(f"ordinal {oid:03d}: key_quote NOT verbatim substring of change_reason; "
                             f"quote={q!r}; original={orig[:80]!r}...")
        if obj.get("confidence") == "high" and pc == "other":
            pass  # 允许：词表外的明确陈述
        if obj.get("confidence") == "low" and pc not in ("other",):
            pass  # 允许：编码需推断但引文存在
    return fails, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--batch", default="all")
    args = ap.parse_args()
    root = os.path.abspath(args.repo_root)
    features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-pilot-20260918")
    raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")
    manifest = json.load(open(os.path.join(features_dir, "sample_manifest.json"), encoding="utf-8"))
    reasons = load_reasons(raw_dir)
    batches = range(1, 4) if args.batch == "all" else [int(args.batch)]
    all_fails = []
    total = 0
    for b in batches:
        fails, n = check_batch(features_dir, b, reasons, manifest["rows"])
        total += n
        all_fails.extend(fails)
        status = "OK" if not fails else f"{len(fails)} FAILURES"
        print(f"batch {b:02d}: {n} rows checked -> {status}")
    for f_ in all_fails:
        print("FAIL:", f_)
    print(f"total rows checked: {total}; total failures: {len(all_fails)}")
    raise SystemExit(1 if all_fails else 0)


if __name__ == "__main__":
    main()
