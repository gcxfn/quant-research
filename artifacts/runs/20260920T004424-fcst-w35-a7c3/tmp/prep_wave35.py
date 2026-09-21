#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-35 备制：由 w34 派生 extract_cues.py 与 merge_batch35.py（完整字面量替换+命中断言），
然后生成 batch_035_cues.txt。批情：ordinals 20400-20999，600 行全部预减（单一 type，
恶化组），沿用简化口径 ordinal|REASON。
"""
import os
import shutil
import subprocess
import sys

W34 = "D:/量化/artifacts/runs/20260920T002613-fcst-w34-a31f/scripts"
W35 = "D:/量化/artifacts/runs/20260920T004424-fcst-w35-a7c3/scripts"
PY = "D:/量化/.venv/Scripts/python.exe"


def derive(src_name, dst_name, replacements, doc_lines=None):
    with open(os.path.join(W34, src_name), encoding="utf-8") as f:
        text = f.read()
    for old, new in replacements:
        n = text.count(old)
        assert n == 1, f"{src_name}: pattern {old!r} hit {n} times (expect 1)"
        text = text.replace(old, new)
    with open(os.path.join(W35, dst_name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"derived {dst_name}: {len(replacements)} literal replacements, all hit exactly once")


# --- extract_cues.py: 仅改 default 与 docstring 批情描述 ---
derive(
    "extract_cues.py",
    "extract_cues.py",
    [
        ("default=34", "default=35"),
        ("沿自 wave-24 extract_cues.py，仅改 batch 默认 24→25，产物 work/batch_034_cues.txt",
         "沿自 wave-34 extract_cues.py，仅改 batch 默认 34→35，产物 work/batch_035_cues.txt"),
        ("行前缀查 row_index 后本批 ordinals 19800–20399 共 600 行 type 分布为\n600 行全部续亏（单一 type），故沿用批 14-18/20/21 的\"ordinal|REASON\"简化口径\n（不保留 type 字段）；supports_direction 按 恶化组=续亏 判定",
         "行前缀查 row_index 后本批 ordinals 20400–20999 共 600 行 type 分布为\n600 行全部预减（单一 type），故沿用简化口径\"ordinal|REASON\"\n（不保留 type 字段）；supports_direction 按 恶化组=预减 判定"),
        ("产物: work/batch_034_cues.txt", "产物: work/batch_035_cues.txt"),
    ],
)

# --- merge_batch35.py: 代码行完整字面量替换（sed/子串对代码行无效的教训） ---
derive(
    "merge_batch34.py",
    "merge_batch35.py",
    [
        ('pl.col("batch_id") == 34', 'pl.col("batch_id") == 35'),
        ("expect_lo = 19800", "expect_lo = 20400"),
        ('f"batch_034_judge_part{part}.jsonl"', 'f"batch_035_judge_part{part}.jsonl"'),
        ('f"batch_034_part{part}.jsonl"', 'f"batch_035_part{part}.jsonl"'),
        ('f"batch_034_part{i}.jsonl"', 'f"batch_035_part{i}.jsonl"'),
        ('"batch_034.jsonl"', '"batch_035.jsonl"'),
        # docstring 派生说明
        ("wave-34 专用：把 6 段逐行结构化判断(batch_034_judge_partN.jsonl)与 row_index 元信息\n程序化合并为 batch_034_partN.jsonl（全字段），并做合并前预校验：",
         "wave-35 专用：把 6 段逐行结构化判断(batch_035_judge_partN.jsonl)与 row_index 元信息\n程序化合并为 batch_035_partN.jsonl（全字段），并做合并前预校验："),
        ("ordinal 连续且与 row_index batch_id=25 的 batch_idx 顺序一一对应",
         "ordinal 连续且与 row_index batch_id=35 的 batch_idx 顺序一一对应"),
        ("沿自 wave-25 merge_batch25.py，仅改 batch=25→34、ordinal 基 14400→19800、文件名 batch_025→batch_034，校验逻辑逐行保留（含冻结区断言）；批次过滤行由主对话显式字面量替换（sed/子串模式对代码行无效的教训，见 w26 fix-note）。",
         "沿自 wave-34 merge_batch34.py，仅改 batch=34→35、ordinal 基 19800→20400、文件名 batch_034→batch_035，校验逻辑逐行保留（含冻结区断言）；批次过滤行由主对话显式字面量替换（sed/子串模式对代码行无效的教训，见 w26 fix-note）。"),
        ("用法: python merge_batch34.py --repo-root D:/量化\n产物: work/batch_034_part1..6.jsonl、data/features/fcst-reason-struct-full-20260918/batch_034.jsonl",
         "用法: python merge_batch35.py --repo-root D:/量化\n产物: work/batch_035_part1..6.jsonl、data/features/fcst-reason-struct-full-20260918/batch_035.jsonl"),
    ],
)

# --- 生成 cues ---
r = subprocess.run(
    [PY, os.path.join(W35, "extract_cues.py"), "--repo-root", "D:/量化", "--batch", "35"],
    capture_output=True, text=True, encoding="utf-8", cwd=W35,
)
print("stdout:", r.stdout.strip())
if r.returncode != 0:
    print("stderr:", r.stderr.strip())
    sys.exit(1)
