#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-36 备制：由 w35 派生 extract_cues.py 与 merge_batch36.py（完整字面量替换+命中断言），
然后生成 batch_036_cues.txt。批情：ordinals 21000-21599，600 行全部预减（单一 type，
恶化组），沿用简化口径 ordinal|REASON。
"""
import os
import subprocess
import sys

W35 = "D:/量化/artifacts/runs/20260920T004424-fcst-w35-a7c3/scripts"
W36 = "D:/量化/artifacts/runs/20260920T011344-fcst-w36-b2e8/scripts"
PY = "D:/量化/.venv/Scripts/python.exe"


def derive(src_name, dst_name, replacements):
    with open(os.path.join(W35, src_name), encoding="utf-8") as f:
        text = f.read()
    for old, new in replacements:
        n = text.count(old)
        assert n == 1, f"{src_name}: pattern {old!r} hit {n} times (expect 1)"
        text = text.replace(old, new)
    with open(os.path.join(W36, dst_name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"derived {dst_name}: {len(replacements)} literal replacements, all hit exactly once")


derive(
    "extract_cues.py",
    "extract_cues.py",
    [
        ("default=35", "default=36"),
        ("沿自 wave-34 extract_cues.py，仅改 batch 默认 34→35，产物 work/batch_035_cues.txt",
         "沿自 wave-35 extract_cues.py，仅改 batch 默认 35→36，产物 work/batch_036_cues.txt"),
        ("本批 ordinals 20400–20999 共 600 行 type 分布为\n600 行全部预减（单一 type）",
         "本批 ordinals 21000–21599 共 600 行 type 分布为\n600 行全部预减（单一 type）"),
        ("产物: work/batch_035_cues.txt", "产物: work/batch_036_cues.txt"),
    ],
)

derive(
    "merge_batch35.py",
    "merge_batch36.py",
    [
        ('pl.col("batch_id") == 35', 'pl.col("batch_id") == 36'),
        ("expect_lo = 20400", "expect_lo = 21000"),
        ('f"batch_035_judge_part{part}.jsonl"', 'f"batch_036_judge_part{part}.jsonl"'),
        ('f"batch_035_part{part}.jsonl"', 'f"batch_036_part{part}.jsonl"'),
        ('f"batch_035_part{i}.jsonl"', 'f"batch_036_part{i}.jsonl"'),
        ('"batch_035.jsonl"', '"batch_036.jsonl"'),
        ("wave-35 专用：把 6 段逐行结构化判断(batch_035_judge_partN.jsonl)与 row_index 元信息\n程序化合并为 batch_035_partN.jsonl（全字段），并做合并前预校验：",
         "wave-36 专用：把 6 段逐行结构化判断(batch_036_judge_partN.jsonl)与 row_index 元信息\n程序化合并为 batch_036_partN.jsonl（全字段），并做合并前预校验："),
        ("ordinal 连续且与 row_index batch_id=35 的 batch_idx 顺序一一对应",
         "ordinal 连续且与 row_index batch_id=36 的 batch_idx 顺序一一对应"),
        ("沿自 wave-34 merge_batch34.py，仅改 batch=34→35、ordinal 基 19800→20400、文件名 batch_034→batch_035，校验逻辑逐行保留（含冻结区断言）；批次过滤行由主对话显式字面量替换（sed/子串模式对代码行无效的教训，见 w26 fix-note）。",
         "沿自 wave-35 merge_batch35.py，仅改 batch=35→36、ordinal 基 20400→21000、文件名 batch_035→batch_036，校验逻辑逐行保留（含冻结区断言）；批次过滤行由主对话显式字面量替换（sed/子串模式对代码行无效的教训，见 w26 fix-note）。"),
        ("用法: python merge_batch35.py --repo-root D:/量化\n产物: work/batch_035_part1..6.jsonl、data/features/fcst-reason-struct-full-20260918/batch_035.jsonl",
         "用法: python merge_batch36.py --repo-root D:/量化\n产物: work/batch_036_part1..6.jsonl、data/features/fcst-reason-struct-full-20260918/batch_036.jsonl"),
    ],
)

r = subprocess.run(
    [PY, os.path.join(W36, "extract_cues.py"), "--repo-root", "D:/量化", "--batch", "36"],
    capture_output=True, text=True, encoding="utf-8", cwd=W36,
)
print("stdout:", r.stdout.strip())
if r.returncode != 0:
    print("stderr:", r.stderr.strip())
    sys.exit(1)
