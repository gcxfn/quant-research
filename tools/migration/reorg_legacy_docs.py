# -*- coding: utf-8 -*-
"""重建 docs/legacy 结构：镜像旧库相对路径，并补回被误删的 docs 子目录。"""
from __future__ import annotations

import os
import shutil

OLD = r"D:\AI\workspace\个人量化"
LEG = r"D:\量化\docs\legacy"
KEEP_AT_ROOT = {"README.md", "AGENTS.md", "CHANGELOG.md", "artifacts-evidence", "old-source-snapshot.zip", "docs"}
DOCS_DIR = os.path.join(LEG, "docs")

os.makedirs(DOCS_DIR, exist_ok=True)

# 1) 把此前平铺在 legacy 根的旧 docs 内容移入 legacy/docs
for name in sorted(os.listdir(LEG)):
    if name in KEEP_AT_ROOT:
        continue
    src = os.path.join(LEG, name)
    dst = os.path.join(DOCS_DIR, name)
    if os.path.exists(dst):
        shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
    shutil.move(src, dst)
    print("moved into docs/:", name)

# 2) 从旧库补齐 docs 全树（.md/.json）
src_docs = os.path.join(OLD, "docs")
copied = 0
for dp, _dn, fns in os.walk(src_docs):
    for f in fns:
        if os.path.splitext(f)[1].lower() not in {".md", ".json"}:
            continue
        s = os.path.join(dp, f)
        rel = os.path.relpath(s, src_docs)
        d = os.path.join(DOCS_DIR, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(s, d)
        copied += 1
print(f"copied from old docs: {copied}")

md = sum(1 for dp, _dn, fns in os.walk(DOCS_DIR) for f in fns if f.endswith(".md"))
print(f"legacy/docs md files: {md}")
for probe in ["experiments/user-minute-ingestion-20260913.md", "experiments/xiaodefa-data-pull-20260913.md", "tasks/ten-year-fixed-strategies-20260912.md"]:
    p = os.path.join(DOCS_DIR, probe.replace("/", os.sep))
    print(("OK   " if os.path.exists(p) else "MISS ") + probe)
