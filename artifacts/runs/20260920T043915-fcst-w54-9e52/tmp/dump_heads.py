# -*- coding: utf-8 -*-
"""临时核对工具：输出每行 ordinal 与原文前缀，供标注映射核对。"""
import os

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(base, "work", "batch_054_cues.txt")
out = os.path.join(base, "tmp", "ordinal_heads.txt")
with open(src, encoding="utf-8") as f:
    lines = [ln.rstrip("\n") for ln in f if ln.strip()]
with open(out, "w", encoding="utf-8", newline="\n") as f:
    for ln in lines:
        parts = ln.split("|", 2)
        head = parts[2][:56].replace("\t", " ")
        f.write(parts[0] + "|" + head + "\n")
print("rows:", len(lines))
