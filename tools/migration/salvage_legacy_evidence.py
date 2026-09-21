# -*- coding: utf-8 -*-
"""抢救旧库「证据层」并打一个源码快照（删除旧库前的最后一步）。

1) 定向复制证据文件（审核记录、补丁清单、来源目录、能力评审）到 docs/legacy/artifacts-evidence/。
2) 把旧库源码/配置/文档打成一个 zip（排除数据、产物、依赖、二进制），放到 docs/legacy/old-source-snapshot.zip。
"""
from __future__ import annotations

import os
import shutil
import zipfile

OLD = r"D:\AI\workspace\个人量化"
NEW = r"D:\量化\docs\legacy"

EVIDENCE = {
    "artifacts/user-minute-1m-review-20260913-1": None,          # 该目录内的文本证据
    "artifacts/xiaodefa-bulk-20260913": None,
    "artifacts/xiaodefa-minute-coverage-20260913": None,
    "artifacts/bigquant-sdk-enabled-20260914-1": None,
    "artifacts/bigquant-source-repair-20260914-1": None,
    "artifacts/user-csv-minute-review-20260913": None,
    "artifacts/ten-year-fixed-strategies-minute-accounts-20260913-12": ["verification.json", "manifest.json", "blocking-review.json"],
}
TEXT_EXTS = {".md", ".json", ".csv", ".txt", ".py"}
MAX_BYTES = 4 << 20

ZIP_SKIP_DIRS = {".venvs", ".git", "__pycache__", ".pytest_cache", ".orca-worktree-trash", ".code-review-graph",
                 "node_modules", "data", "artifacts", ".hermes", "docs"}
ZIP_SKIP_EXTS = {".parquet", ".bin", ".zip", ".pkl", ".npy", ".feather", ".db", ".ldb", ".exe", ".dll", ".pyd",
                 ".so", ".whl", ".tar", ".gz", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".mp4", ".pdf"}
ZIP_MAX_BYTES = 2 << 20


def copy_evidence() -> tuple[int, int]:
    count = total = 0
    for rel, only in EVIDENCE.items():
        base = os.path.join(OLD, rel.replace("/", os.sep))
        if not os.path.isdir(base):
            print("  missing:", rel)
            continue
        for dp, _dirs, fns in os.walk(base):
            for f in fns:
                if only is not None and f not in only:
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext not in TEXT_EXTS:
                    continue
                src = os.path.join(dp, f)
                if os.path.getsize(src) > MAX_BYTES:
                    continue
                dst = os.path.join(NEW, "artifacts-evidence", os.path.relpath(src, os.path.join(OLD, "artifacts")))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                count += 1
                total += os.path.getsize(src)
    return count, total


def build_snapshot() -> tuple[str, int, int]:
    out = os.path.join(NEW, "old-source-snapshot.zip")
    n = size = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dp, dirs, fns in os.walk(OLD):
            dirs[:] = [d for d in dirs if d not in ZIP_SKIP_DIRS]
            for f in fns:
                src = os.path.join(dp, f)
                ext = os.path.splitext(f)[1].lower()
                if ext in ZIP_SKIP_EXTS:
                    continue
                try:
                    sz = os.path.getsize(src)
                except OSError:
                    continue
                if sz > ZIP_MAX_BYTES:
                    continue
                zf.write(src, os.path.relpath(src, OLD))
                n += 1
                size += sz
    return out, n, size


if __name__ == "__main__":
    c, b = copy_evidence()
    print(f"evidence files={c} bytes={b/2**20:.2f} MiB")
    out, n, size = build_snapshot()
    print(f"snapshot {out} entries={n} raw={size/2**20:.2f} MiB zip={os.path.getsize(out)/2**20:.2f} MiB")
