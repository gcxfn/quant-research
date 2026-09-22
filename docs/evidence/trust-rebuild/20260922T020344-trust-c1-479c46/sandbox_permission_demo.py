# -*- coding: utf-8 -*-
"""Dev 沙箱权限演示（C1-01 证据）。

证明两件事：
1. 受控导出的 Dev 沙箱能被加载器正常读取（含 SHA256 复算）；
2. 混合年份原始文件、Val 路径、未登记路径、超出 Dev 上限的日期请求，
   全部被拒绝 —— 研究运行没有“读全文件再内存过滤”的旁路。

运行：
    .venv/Scripts/python.exe docs/evidence/trust-rebuild/<C1-run>/sandbox_permission_demo.py

全部用例符合预期时退出码 0；任何一条与预期不符即退出码 1（明确失败，不静默）。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = next(p for p in [HERE.parent, *HERE.parents]
            if (p / "src" / "quant").is_dir() and (p / "data").is_dir())
sys.path.insert(0, str(REPO / "src"))

from quant.data.dev_sandbox import (  # noqa: E402  (path set above)
    DateRangeError, PathNotAllowedError, SandboxAccessError,
    SandboxRegistry, UnknownDatasetError)

OUT_OF_SCOPE_PATHS = [
    "data/raw/baostock/daily/sh.600000.csv",
    "data/processed/baostock-daily-20260917/daily_1999_2024.parquet",
    "data/processed/baostock-daily-20260917/daily_2015_2024.parquet",
    "data/processed/halfday-bars-20260918/year=2021/bars.parquet",
    "data/raw/tushare/forecast/20260909-r1/chunk_202101.csv",
    "data/features/fcst-reason-struct-full-20260918/row_index.parquet",
]

results: list[dict] = []


def check(name: str, expected_error, fn) -> None:
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001 - 演示脚本需要记录所有异常类型
        ok = expected_error is not None and isinstance(exc, expected_error)
        results.append({"case": name, "expected": expected_error.__name__ if expected_error else "no_error",
                        "got": type(exc).__name__, "ok": ok, "detail": str(exc)[:200]})
        return
    ok = expected_error is None
    results.append({"case": name, "expected": "no_error",
                    "got": "no_error", "ok": ok, "detail": str(value)[:200]})


registry = None

check("load sandbox registry", None,
      lambda: (globals().__setitem__("registry", SandboxRegistry.load(REPO)),
               "ok")[1])
assert registry is not None, "sandbox registry must load"
results.append({"case": "declared dataset kinds",
                "expected": "no_error", "got": "no_error", "ok": True,
                "detail": json.dumps(sorted(registry.manifest.datasets))})

check("read bars_daily slice", None,
      lambda: registry.read("bars_daily", start=date(2020, 12, 1),
                            end=date(2020, 12, 31),
                            symbols=["sh.600000", "sz.000001"],
                            columns=["symbol", "date", "close"]).height)
check("read bars_halfday slice", None,
      lambda: registry.read("bars_halfday", start=date(2020, 12, 28),
                            end=date(2020, 12, 31)).height)
check("read forecast B window", None,
      lambda: registry.read("forecast_event", start=date(2020, 12, 1),
                            end=date(2020, 12, 31)).height)
check("read limit slice", None,
      lambda: registry.read("limit", start=date(2020, 12, 28),
                            end=date(2020, 12, 31)).height)
check("sha256 re-verification of all declared files", None,
      lambda: {k: all(v.values())
               for k, v in ((ds, registry.verify_files(ds))
                            for ds in sorted(registry.manifest.datasets))})

for bad in ["baostock-daily-20260917", "halfday-bars-20260918",
            "etf-daily-20260919", "rqalpha-bundle-v2-1-20260918"]:
    check(f"refuse dataset_id={bad}", UnknownDatasetError,
          lambda bad=bad: SandboxRegistry.load(REPO, dataset_id=bad))

for path in OUT_OF_SCOPE_PATHS:
    check(f"refuse path={path}", PathNotAllowedError,
          lambda path=path: registry.resolve(path))

check("refuse read beyond dev_end (2021-01-04)", DateRangeError,
      lambda: registry.read("bars_daily", end=date(2021, 1, 4)))
check("refuse read before dev_start (2010-01-01)", DateRangeError,
      lambda: registry.read("bars_daily", start=date(2010, 1, 1)))
check("refuse undeclared column", SandboxAccessError,
      lambda: registry.read("bars_daily", columns=["ts_code"]))
check("refuse unknown kind", UnknownDatasetError,
      lambda: registry.read("bars_from_2024"))

key_a = registry.cache_key("bars_daily", start=date(2020, 12, 1),
                           end=date(2020, 12, 31),
                           symbols=["sh.600000", "sz.000001"],
                           adjust_mode="unadjusted",
                           code_digest="demo-code-v1")
key_b = registry.cache_key("bars_daily", start=date(2020, 12, 1),
                           end=date(2020, 12, 31),
                           symbols=["sh.600000", "sz.000001"],
                           adjust_mode="back_adjusted",
                           code_digest="demo-code-v1")
results.append({"case": "cache_key differs with adjust_mode",
                "expected": "no_error", "got": "no_error", "ok": key_a != key_b,
                "detail": f"{key_a[:16]} != {key_b[:16]} (len={len(key_a)})"})

for row in results:
    print(f"[{'PASS' if row['ok'] else 'FAIL'}] {row['case']} :: "
          f"expected={row['expected']} got={row['got']} :: {row['detail']}")
failed = [r for r in results if not r["ok"]]
print(json.dumps({"cases": len(results), "failed": len(failed),
                  "sandbox_dataset_id": registry.dataset_id}, ensure_ascii=False))
raise SystemExit(1 if failed else 0)
