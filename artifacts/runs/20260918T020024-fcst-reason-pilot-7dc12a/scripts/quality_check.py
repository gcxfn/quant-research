#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pilot 全量质量自检：600 行结构化结果 → quality_report.json。

在 check_batch.py 校验逻辑之上汇总：
- quote 逐字子串 100% 程序验证
- primary/secondary 词表闭合、supports_direction/confidence 合法性
- other 率、secondary null 率、confidence 分布、supports_direction 分布
- type × primary_code、type × supports_direction 交叉表
- key_quote 长度分布；样本/池 change_reason 长度分布（吞吐外推用）
- 逐批耗时（解析 run.log 时间戳）与 token 量级估算

用法: python quality_check.py --repo-root D:/量化 --run-id <run_id>
"""
import argparse
import csv
import glob
import json
import os
import re
from collections import Counter
from datetime import datetime

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


def pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(p * len(sorted_vals)))]


def parse_batch_timings(log_path):
    """从 run.log 解析 batch_NN start/done 时间戳，返回每批耗时秒。"""
    pat = re.compile(r"=== (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2})?) batch_(\d+) (structuring start|done)")
    starts, dones = {}, {}
    if not os.path.exists(log_path):
        return {}
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            m = pat.search(line)
            if not m:
                continue
            ts = datetime.fromisoformat(m.group(1))
            b = int(m.group(2))
            if m.group(3) == "structuring start":
                starts.setdefault(b, ts)
            else:
                dones[b] = ts
    return {b: round((dones[b] - starts[b]).total_seconds(), 1)
            for b in starts if b in dones}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    root = os.path.abspath(args.repo_root)
    features_dir = os.path.join(root, "data", "features", "fcst-reason-struct-pilot-20260918")
    raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")
    run_dir = os.path.join(root, "artifacts", "runs", args.run_id)

    manifest = json.load(open(os.path.join(features_dir, "sample_manifest.json"), encoding="utf-8"))
    reasons = load_reasons(raw_dir)

    failures = []
    rows = []
    for b in (1, 2, 3):
        path = os.path.join(features_dir, f"batch_{b:02d}.jsonl")
        with open(path, encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        if len(lines) != BATCH_SIZE:
            failures.append(f"batch {b}: line count {len(lines)} != {BATCH_SIZE}")
        expect = [r for r in manifest["rows"] if r["batch"] == b]
        for i, ln in enumerate(lines):
            obj = json.loads(ln)
            mrow = expect[i]
            oid = mrow["ordinal"]
            key = (obj.get("ts_code"), obj.get("end_date"), obj.get("ann_date"), obj.get("update_flag"))
            mkey = (mrow["ts_code"], mrow["end_date"], mrow["ann_date"], mrow["update_flag"])
            if key != mkey:
                failures.append(f"ordinal {oid:03d}: key mismatch")
            for k in REQUIRED:
                if k not in obj:
                    failures.append(f"ordinal {oid:03d}: missing {k}")
            if obj.get("primary_code") not in VOCAB:
                failures.append(f"ordinal {oid:03d}: primary not in vocab")
            sc = obj.get("secondary_code")
            if sc is not None and (sc not in VOCAB or sc == obj.get("primary_code")):
                failures.append(f"ordinal {oid:03d}: secondary invalid")
            if obj.get("supports_direction") not in (-1, 0, 1):
                failures.append(f"ordinal {oid:03d}: supports_direction invalid")
            if obj.get("confidence") not in ("high", "low"):
                failures.append(f"ordinal {oid:03d}: confidence invalid")
            if obj.get("struct_version") != "llm-v1":
                failures.append(f"ordinal {oid:03d}: struct_version invalid")
            q = obj.get("key_quote", "")
            if not q or len(q) > 40 or q not in reasons.get(mkey, ""):
                failures.append(f"ordinal {oid:03d}: key_quote verbatim check FAILED")
            rows.append(obj)

    n = len(rows)
    prim = Counter(r["primary_code"] for r in rows)
    sec = Counter(r["secondary_code"] if r["secondary_code"] else "null" for r in rows)
    sd = Counter(r["supports_direction"] for r in rows)
    cf = Counter(r["confidence"] for r in rows)
    qlens = sorted(len(r["key_quote"]) for r in rows)

    types = {r_key["ordinal"]: r_key["type"] for r_key in manifest["rows"]}
    # batch 文件按 ordinal 顺序排列：batch b 的第 i 行 ordinal = (b-1)*200+i
    crosstab_tp, crosstab_ts = {}, {}
    for idx, r in enumerate(rows):
        t = types[idx]
        crosstab_tp.setdefault(t, Counter())[r["primary_code"]] += 1
        crosstab_ts.setdefault(t, Counter())[r["supports_direction"]] += 1

    input_chars = {}
    output_chars = {}
    for b in (1, 2, 3):
        with open(os.path.join(run_dir, "work", f"batch_{b:02d}_input.txt"), encoding="utf-8") as f:
            input_chars[b] = len(f.read())
        with open(os.path.join(features_dir, f"batch_{b:02d}.jsonl"), encoding="utf-8") as f:
            output_chars[b] = len(f.read())

    timings = parse_batch_timings(os.path.join(run_dir, "logs", "run.log"))

    total_in_chars = sum(input_chars.values())
    total_out_chars = sum(output_chars.values())

    report = {
        "run_id": args.run_id,
        "struct_version": "llm-v1",
        "n_rows_expected": 600,
        "n_rows_checked": n,
        "all_checks_passed": len(failures) == 0,
        "n_failures": len(failures),
        "failures": failures,
        "quote_verbatim_pass_rate": round(1 - sum(1 for x in failures if "key_quote" in x) / n, 6) if n else 0.0,
        "other_rate_primary": round(prim.get("other", 0) / n, 4),
        "secondary_null_rate": round(sec.get("null", 0) / n, 4),
        "primary_code_distribution": dict(sorted(prim.items(), key=lambda kv: -kv[1])),
        "secondary_code_distribution": dict(sorted(sec.items(), key=lambda kv: -kv[1])),
        "supports_direction_distribution": {str(k): v for k, v in sorted(sd.items())},
        "confidence_distribution": dict(sorted(cf.items())),
        "key_quote_len_chars": {"mean": round(sum(qlens) / len(qlens), 1), "p50": pct(qlens, 0.5),
                                 "p90": pct(qlens, 0.9), "max": qlens[-1]},
        "type_x_primary_code": {t: dict(c.most_common()) for t, c in sorted(crosstab_tp.items())},
        "type_x_supports_direction": {t: {str(k): v for k, v in sorted(c.most_common())}
                                       for t, c in sorted(crosstab_ts.items())},
        "sample_reason_len_chars": manifest["pool_reason_len_chars"] and {
            "mean": manifest["rows"] and round(sum(r["reason_len_chars"] for r in manifest["rows"]) / len(manifest["rows"]), 1)},
        "pool_reason_len_chars": manifest["pool_reason_len_chars"],
        "filter_counts": manifest["filter_counts"],
        "batch_wall_seconds_LLM_structuring": {str(k): v for k, v in sorted(timings.items())},
        "chars_per_batch": {
            "input_render": {str(b): input_chars[b] for b in sorted(input_chars)},
            "output_jsonl": {str(b): output_chars[b] for b in sorted(output_chars)},
            "total_input": total_in_chars,
            "total_output": total_out_chars,
        },
        "token_estimate_assumptions": (
            "中英混合中文文本按 0.6-1.1 token/字符估算；全量 API 调用还需每行约 600-1000 token 的"
            "系统提示/ schema 指令开销（批次内摊薄后约 300-500 token/行）。以下为量级估算，非实测 API 计费。"
        ),
    }
    if n:
        in_per_row = total_in_chars / n
        out_per_row = total_out_chars / n
        report["token_estimate_per_row"] = {
            "input_chars": round(in_per_row, 1),
            "output_chars": round(out_per_row, 1),
            "input_tokens_est": [round(in_per_row * 0.6), round(in_per_row * 1.1)],
            "output_tokens_est": [round(out_per_row * 0.6), round(out_per_row * 1.1)],
        }

    with open(os.path.join(features_dir, "quality_report.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print(json.dumps({
        "n_rows_checked": n,
        "all_checks_passed": report["all_checks_passed"],
        "n_failures": len(failures),
        "quote_verbatim_pass_rate": report["quote_verbatim_pass_rate"],
        "other_rate_primary": report["other_rate_primary"],
        "supports_direction_distribution": report["supports_direction_distribution"],
        "confidence_distribution": report["confidence_distribution"],
        "batch_wall_seconds": report["batch_wall_seconds_LLM_structuring"],
        "token_estimate_per_row": report.get("token_estimate_per_row"),
    }, ensure_ascii=False, indent=1))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
