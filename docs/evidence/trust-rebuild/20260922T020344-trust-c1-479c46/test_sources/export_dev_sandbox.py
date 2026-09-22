#!/usr/bin/env python
"""薄命令入口：受控导出 Dev-only 沙箱工作集。

实际逻辑在 ``src/quant/data/dev_sandbox_export.py``。用法::

    .venv/Scripts/python.exe tools/export_dev_sandbox.py --run-id <C1-run-id>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from quant.data.dev_sandbox_export import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--repo-root", str(ROOT), *sys.argv[1:]]))
