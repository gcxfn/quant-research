#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-65 临时修复：merge 预检显示 cues 渲染把全角标点显示成半角，导致
key_quote 中非数字位置的逗号/括号与 raw 原文不一致。本脚本仅改 key_quote
引文（不改任何编码字段）：把 quote 里的 ',' 按位置规范化为 '，'
（数字千分位保留半角）、'(' ')' 规范化为 '（' '）'，然后对 raw 原文
逐字验证，仅当规范化后的 quote 确为原文子串才写回。"""
import csv
import glob
import json
import os

import polars as pl

ROOT = r"D:\量化"
RUN = r"D:\量化\artifacts\runs\20260920T061631-fcst-w65-847b"
FEATURES = os.path.join(ROOT, "data", "features", "fcst-reason-struct-full-20260918")
RAW = os.path.join(ROOT, "data", "raw", "tushare", "forecast", "20260909-r1")


def normalize(q):
    out = []
    for i, ch in enumerate(q):
        if ch == ",":
            prev = q[i - 1] if i > 0 else ""
            nxt = q[i + 1] if i + 1 < len(q) else ""
            out.append("," if (prev.isdigit() and nxt.isdigit()) else "，")
        elif ch == "(":
            out.append("（")
        elif ch == ")":
            out.append("）")
        else:
            out.append(ch)
    return "".join(out)


def main():
    idx = pl.read_parquet(os.path.join(FEATURES, "row_index.parquet"))
    batch = idx.filter(pl.col("batch_id") == 65).sort("batch_idx")
    meta = {r["ordinal"]: r for r in batch.iter_rows(named=True)}
    reasons = {}
    for fp in sorted(glob.glob(os.path.join(RAW, "chunk_*.csv"))):
        with open(fp, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                key = (r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                       (r.get("ann_date") or "").strip(),
                       (r.get("update_flag") or "").strip())
                reasons[key] = r.get("change_reason") or ""

    changed, unmatched = [], []
    for part in (1, 2):
        jpath = os.path.join(RUN, "work", f"batch_065_judge_part{part}.jsonl")
        with open(jpath, encoding="utf-8") as f:
            judges = [json.loads(x) for x in f.read().splitlines() if x.strip()]
        for j in judges:
            m = meta[j["ordinal"]]
            orig = reasons[(m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"])]
            newq = normalize(j["key_quote"])
            if newq != j["key_quote"]:
                if newq in orig:
                    changed.append((j["ordinal"], j["key_quote"], newq))
                    j["key_quote"] = newq
                else:
                    unmatched.append((j["ordinal"], newq))
        with open(jpath, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":"))
                              for x in judges) + "\n")

    print(json.dumps({"changed": len(changed), "unmatched": len(unmatched)},
                     ensure_ascii=False))
    for oid, old, new in changed:
        print(f"CHANGED {oid}: {old!r} -> {new!r}")
    for oid, q in unmatched:
        print(f"UNMATCHED {ordinal_str(oid)}: {q!r}")


def ordinal_str(x):
    return f"{x:05d}"


if __name__ == "__main__":
    main()
