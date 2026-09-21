# -*- coding: utf-8 -*-
"""删除旧库 D:\\AI\\workspace\\个人量化（用户 2026-09-16 批准）。

先 robocopy /MIR 用空目录镜像清空（可处理长路径、大量文件），再删除空壳目录。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

TARGET = r"D:\AI\workspace\个人量化"


def size_of(path: str) -> tuple[int, int]:
    files = total = 0
    for dp, _dn, fns in os.walk(path):
        for f in fns:
            try:
                total += os.path.getsize(os.path.join(dp, f))
                files += 1
            except OSError:
                pass
    return files, total


def main() -> int:
    if not os.path.isdir(TARGET):
        print("target already gone")
        return 0
    files, total = size_of(TARGET)
    print(f"target files={files} bytes={total} ({total/2**30:.2f} GiB)", flush=True)
    if os.environ.get("DRY_RUN"):
        return 0

    empty = tempfile.mkdtemp(prefix="empty-mirror-")
    cmd = ["robocopy", empty, TARGET, "/MIR", "/R:1", "/W:1", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/MT:16"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("robocopy rc:", proc.returncode, flush=True)
    os.rmdir(empty)

    if os.path.isdir(TARGET):
        shutil.rmtree(TARGET, ignore_errors=True)
    print("target exists after wipe:", os.path.isdir(TARGET))
    return 0


if __name__ == "__main__":
    sys.exit(main())
