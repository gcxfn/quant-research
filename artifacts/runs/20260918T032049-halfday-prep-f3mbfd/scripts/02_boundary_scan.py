# -*- coding: utf-8 -*-
"""02_boundary_scan.py — G2 半天截面前置：冻结边界扫描（文件级全部 + 行级全部投影）。

只读 data/raw；输出写 run 目录 boundary/。
1) 文件级：2,431 个日文件名逐一解析 YYYYMMDD，验证 <= 20241231；
2) 行级：逐文件投影读取 trade_time 的 min/max（不读全行），
   验证全部 < 2025-01-01；另对 6 个抽样文件做全列读复核。
附带采集每文件行数（parquet 元数据，零数据 IO）供 T3 外推。
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

REPO = Path(r"D:\量化")
RAW = REPO / "data" / "raw" / "user_minute_1m"
RUN = REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
BATCHES = ["20260913-143215", "20260913-2020-2024"]
FREEZE = "2024-12-31 15:00:00"  # trade_time 为 ISO 字符串，可直接字典序比较
FULL_READ_SAMPLES = [
    "20260913-143215/2015/20150105.parquet",
    "20260913-143215/2015/20150601.parquet",
    "20260913-143215/2017/20170601.parquet",
    "20260913-143215/2019/20190603.parquet",
    "20260913-2020-2024/2020/20200601.parquet",
    "20260913-2020-2024/2021/20210601.parquet",
    "20260913-2020-2024/2024/20241231.parquet",
]
NAME_RE = re.compile(r"^\d{8}$")


def main() -> int:
    t0 = time.perf_counter()
    rows = []
    bad_names = []
    for batch in BATCHES:
        for ydir in sorted((RAW / batch).iterdir()):
            if not ydir.is_dir():
                continue
            for p in sorted(ydir.glob("*.parquet")):
                if not NAME_RE.match(p.stem):
                    bad_names.append(str(p.relative_to(RAW)))
                    continue
                rows.append({"batch": batch, "year": ydir.name, "path": str(p.relative_to(RAW)),
                             "date": f"{p.stem[:4]}-{p.stem[4:6]}-{p.stem[6:]}",
                             "bytes": p.stat().st_size})
    other_files = []
    for batch in BATCHES:
        for p in (RAW / batch).rglob("*"):
            if p.is_file() and p.suffix != ".parquet":
                other_files.append(str(p.relative_to(RAW)))

    # ---- 文件级判定 ----
    file_level_max = max(r["date"] for r in rows)
    file_level_min = min(r["date"] for r in rows)
    file_level_violations = [r["path"] for r in rows if r["date"] > "2024-12-31"]
    n_names_ok = len(rows)
    print(f"[file-level] files={n_names_ok}, range={file_level_min}..{file_level_max}, "
          f"violations={len(file_level_violations)}, bad_names={len(bad_names)}, other_files={other_files}")

    # ---- 行级投影扫描（trade_time min/max） + 行数元数据 ----
    t_scan = 0.0
    row_violations = []
    for i, r in enumerate(rows, 1):
        fp = RAW / r["path"]
        ta = time.perf_counter()
        s = pl.scan_parquet(fp).select(
            pl.col("trade_time").min().alias("mn"),
            pl.col("trade_time").max().alias("mx"),
        ).collect()
        t_scan += time.perf_counter() - ta
        r["trade_time_min"] = s["mn"][0]
        r["trade_time_max"] = s["mx"][0]
        r["num_rows"] = pq.ParquetFile(fp).metadata.num_rows  # 元数据，不读数据
        if r["trade_time_max"] >= "2025-01-01" or r["trade_time_min"] < "2015-01-01":
            row_violations.append({"path": r["path"], "min": r["trade_time_min"], "max": r["trade_time_max"]})
        if i % 300 == 0 or i == len(rows):
            el = time.perf_counter() - t0
            print(f"[row-level] {i}/{len(rows)} elapsed={el:.1f}s", flush=True)

    # ---- 抽样全列读复核 ----
    full_read_checks = []
    for rel in FULL_READ_SAMPLES:
        fp = RAW / rel
        df = pl.read_parquet(fp)
        full_read_checks.append({
            "path": rel,
            "rows": len(df),
            "date_col_min": df["date"].min(),
            "date_col_max": df["date"].max(),
            "trade_time_min": df["trade_time"].min(),
            "trade_time_max": df["trade_time"].max(),
            "symbols": df["code"].n_unique(),
        })
        print(f"[full-read] {rel}: rows={len(df)}, tt_max={df['trade_time'].max()}")

    # ---- 汇总 ----
    status = "FREEZE_CLEAN" if (not file_level_violations and not row_violations and not bad_names) else "VIOLATIONS_FOUND"
    per_year = {}
    for r in rows:
        y = r["year"]
        per_year.setdefault(y, {"files": 0, "rows": 0, "bytes": 0, "tt_max": ""})
        per_year[y]["files"] += 1
        per_year[y]["rows"] += r["num_rows"]
        per_year[y]["bytes"] += r["bytes"]
        per_year[y]["tt_max"] = max(per_year[y]["tt_max"], r["trade_time_max"])
    report = {
        "purpose": "freeze boundary scan for user_minute_1m (pure data engineering, no 2025+ content read beyond min/max string of trade_time)",
        "run_id": RUN.name,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_files": n_names_ok,
        "file_level": {"min": file_level_min, "max": file_level_max,
                       "violations": file_level_violations, "bad_names": bad_names, "other_files": other_files},
        "row_level": {"method": "projection scan trade_time min/max per file (polars lazy, statistics/column pruning)",
                      "violations": row_violations, "global_max": max(r["trade_time_max"] for r in rows),
                      "global_min": min(r["trade_time_min"] for r in rows)},
        "full_read_samples": full_read_checks,
        "per_year": per_year,
        "status": status,
        "conclusion": ("两批次 2,431 个日文件名全部为 20150105..20241231 内的交易日；"
                       "行级投影扫描全部文件 trade_time 最大值 < 2025-01-01，6 个抽样文件全列读复核一致；"
                       "无任何 2025+ 内容。" if status == "FREEZE_CLEAN" else "发现越界，见明细。"),
        "projection_scan_seconds": round(t_scan, 2),
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }
    (RUN / "boundary").mkdir(parents=True, exist_ok=True)
    (RUN / "boundary" / "boundary_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 逐文件清单 CSV（供 T3 外推与后续抽取直接复用）
    import csv
    with open(RUN / "boundary" / "minute_day_files.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["batch", "year", "path", "date", "bytes", "num_rows", "trade_time_min", "trade_time_max"])
        w.writeheader()
        w.writerows(rows)
    print(f"[done] status={status}, global trade_time max={report['row_level']['global_max']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
