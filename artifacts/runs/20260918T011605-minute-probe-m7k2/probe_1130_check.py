# -*- coding: utf-8 -*-
"""本地分钟包 11:30 bar 存在性复核（修正 trade_time 解析）+ 2024 代码构成。

只读测量；抽样 2 个交易日 + 1 个月投影扫描。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl

REPO = Path(r"D:/量化")
RUN = REPO / "artifacts/runs/20260918T011605-minute-probe-m7k2"
B15 = REPO / "data/raw/user_minute_1m/20260913-143215"
B20 = REPO / "data/raw/user_minute_1m/20260913-2020-2024"


def hm(col: str = "trade_time") -> pl.Expr:
    return pl.col(col).cast(pl.Utf8).str.slice(11, 5)


def check(path: Path) -> dict:
    t0 = time.perf_counter()
    df = pl.read_parquet(path)
    read_s = time.perf_counter() - t0
    m1130 = df.filter(hm() == "11:30")
    per_code = df.group_by("code").len()
    bars_stats = per_code["len"].describe().to_dicts()
    prefixes = (
        df.select(pl.col("code").str.slice(0, 3).alias("p3"))["p3"]
        .value_counts(sort=True)
        .head(25)
        .to_dicts()
    )
    return {
        "file": str(path.relative_to(REPO)),
        "file_bytes": path.stat().st_size,
        "rows": df.height,
        "unique_codes": df["code"].n_unique(),
        "bars_at_1130": m1130.height,
        "etf_prefix_rows_at_1130": int(
            m1130["code"].str.slice(0, 2).is_in(
                ["50", "51", "56", "58", "15", "16", "18"]
            ).sum()
        ),
        "bars_per_code_mean": bars_stats,
        "trade_time_sample": df["trade_time"].head(2).to_list(),
        "row_at_1130_sample": m1130.head(2).to_dicts(),
        "code_prefixes_top25": prefixes,
        "full_read_seconds": round(read_s, 3),
    }


def month_scan() -> dict:
    files = sorted((B20 / "2024").glob("202406*.parquet"))
    t0 = time.perf_counter()
    rows = 0
    for f in files:
        rows += pl.scan_parquet(f).filter(hm() == "11:30").select(pl.len()).collect().item()
    dt = time.perf_counter() - t0
    return {
        "scope": "user_minute_1m/2024/202406* (股票全市场)",
        "files": len(files),
        "rows_at_1130": rows,
        "elapsed_seconds": round(dt, 3),
        "seconds_per_file": round(dt / len(files), 4),
    }


def main() -> None:
    out = {
        "sample_20150601": check(B15 / "2015" / "20150601.parquet"),
        "sample_20240603": check(B20 / "2024" / "20240603.parquet"),
        "month_scan_1130": month_scan(),
    }
    (RUN / "results2_1130.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
