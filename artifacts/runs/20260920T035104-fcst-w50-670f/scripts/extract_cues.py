#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-28 标注辅助：生成"ordinal|REASON"单行紧凑视图（控制标注上下文预算）。

沿自 wave-24 extract_cues.py，仅改 batch 默认 24→25，产物 work/batch_050_cues.txt；
行前缀查 row_index 后本批为混合 type 批，行格式为"ordinal|type|REASON"（type 逐行给出）；
supports_direction 按行内 type 所属组判定（改善组=预增/略增/扭亏/续盈、
恶化组=预减/略减/首亏/续亏/增亏/减亏/预亏；利空向原因在恶化组 +1/在改善组 -1，
利好向原因在改善组 +1/在恶化组 -1，中性/基数 0）。

- len(text) <= 400：整行原文展示（不改写）。
- len(text) > 400：句子级因果摘录（首句 + 命中因果标记的句子，单句截断 320 字符，
  截断处标 [...]；最多 6 句）。摘录为**原文连续句前缀**，key_quote 只取自
  单个所示句子的所示前缀，保证逐字连续；官方 checker 仍 100% 逐字校验。
- 元信息（ts_code/end_date/ann_date/update_flag）不进视图：merge 脚本从
  row_index 程序化合入。

用法: python extract_cues.py --repo-root D:/量化 [--batch 28]
产物: work/batch_050_cues.txt
"""
import argparse
import csv
import glob
import json
import os
import re

import polars as pl

CAUSAL = re.compile(
    r"(原因|由于|导致|造成|使得|致使|影响|受|拖累|侵蚀|主要|其次|一方面|另一方面|"
    r"一是|二是|三是|四是|五是|（[一二三四五六12345]）|\([一二三四五六12345]\)|"
    r"[12345][、．.]|基数|上年同期)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--batch", type=int, default=50)
    args = ap.parse_args()
    root = os.path.abspath(args.repo_root)
    features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-full-20260918")
    raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")
    work = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work")

    idx = pl.read_parquet(os.path.join(features_dir, "row_index.parquet"))
    batch = idx.filter(pl.col("batch_id") == args.batch).sort("batch_idx")
    type_counts = batch.group_by("type").len().sort("type")
    reasons = {}
    for fp in sorted(glob.glob(os.path.join(raw_dir, "chunk_*.csv"))):
        with open(fp, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                key = (r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                       (r.get("ann_date") or "").strip(),
                       (r.get("update_flag") or "").strip())
                reasons[key] = (r.get("change_reason") or "").strip()

    lines = []
    total = 0
    n_extracted = 0
    for m in batch.iter_rows(named=True):
        key = (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"])
        text = reasons[key]
        if len(text) <= 400:
            body = text
        else:
            n_extracted += 1
            sents = [s for s in re.split(r"(?<=[。；;！！])", text) if s.strip()]
            picked = []
            if sents:
                picked.append(sents[0])
            for s in sents[1:]:
                if CAUSAL.search(s):
                    picked.append(s)
            picked = picked[:6]
            shown = [(s[:320] + "[...]") if len(s) > 320 else s for s in picked]
            body = " ".join(shown)
        lines.append(f"{m['ordinal']:05d}|{m['type']}|{body}")
        total += 5 + 1 + len(body)
    out = os.path.join(work, f"batch_{args.batch:03d}_cues.txt")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({
        "rows": batch.height,
        "extracted_long": n_extracted,
        "type_counts": {r["type"]: r["len"] for r in type_counts.iter_rows(named=True)},
        "total_chars": total,
        "file_chars": len(open(out, encoding="utf-8").read()),
        "output": os.path.relpath(out, root).replace("\\", "/"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
