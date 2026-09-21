# -*- coding: utf-8 -*-
"""deepscan 引擎冒烟测试(只读)"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import deepscan as ds

RAW = ds.RAW

t = time.time()
u = RAW / "xiaodefa" / "trade_cal" / "20260913-bulk1"
print("=== trade_cal full:", u.exists())
r = ds.scan_tabular(u, "full")
print({k: r.get(k) for k in ("status", "rows_total", "primary_key", "duplicate_rows", "date_coverage", "unit_check")})
print("issues:", r["issues"])

print("=== tx json")
r = ds.scan_json_unit(RAW / "tx" / "sh510300" / "20260904T185625")
print({k: r.get(k) for k in ("rows_total", "date_coverage", "unit_check_conclusion", "sha256_verified_pages")})
print("issues:", r["issues"])

print("=== ths json")
p = sorted((RAW / "ths" / "sh510050").iterdir())[0]
r = ds.scan_json_unit(p)
print({k: r.get(k) for k in ("rows_total", "date_coverage", "unit_check_conclusion", "sha256_verified_pages")})

print("=== em_fin json")
p = sorted((RAW / "em_fin" / "sh600030").iterdir())[0]
r = ds.scan_json_unit(p)
print({k: r.get(k) for k in ("rows_total", "date_coverage")})
print("issues:", r["issues"])

print("=== user_dataset zip")
r = ds.scan_zip_unit(RAW / "user_dataset" / "2026-09-03" / "上证")
print({k: (len(r.get(k) or []) if isinstance(r.get(k), list) else r.get(k)) for k in ("zips",)})
print("zip0:", {k: r["zips"][0].get(k) for k in ("zip", "members", "csv_members", "uncompressed_bytes")} if r["zips"] else None)
print("issues:", r["issues"])

print("=== user_minute_1m inventory-only (小批次)")
r = ds.scan_inventory_only(RAW / "user_minute_1m" / "20260913-2020-2024")
print({k: r.get(k) for k in ("files", "top_files")})
print("issues:", r["issues"])

print(f"SMOKE OK {round(time.time()-t,1)}s")
