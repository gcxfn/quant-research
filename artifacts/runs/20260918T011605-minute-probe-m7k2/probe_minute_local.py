# -*- coding: utf-8 -*-
"""本地分钟数据探测（半天 11:30 截面前置 probe）。

只读测量，不修改任何数据文件；抽样规模受限（每天至多 3 个整文件 + 每年 1 个
code 列投影 + 1 个月的 11:30 过滤扫描），不构成全量拉取。

输出：run 目录下 results.json（机器可读）+ stdout 摘要。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

REPO = Path(r"D:/量化")
RUN = REPO / "artifacts/runs/20260918T011605-minute-probe-m7k2"

BATCH_2015_2019 = REPO / "data/raw/user_minute_1m/20260913-143215"
BATCH_2020_2024 = REPO / "data/raw/user_minute_1m/20260913-2020-2024"
BATCH_2010_2014 = REPO / "data/raw/bigquant/minute-bulk-20260915-1/years"

# ETF 代码前缀（场内基金：沪 50/51/56/58，深 15/16/18；含少量已退市形态）
ETF_PREFIX_SH = ("50", "51", "56", "58")
ETF_PREFIX_SZ = ("15", "16", "18")


def day_path(year: int, yyyymmdd: str) -> Path | None:
    if 2015 <= year <= 2019:
        p = BATCH_2015_2019 / str(year) / f"{yyyymmdd}.parquet"
    elif 2020 <= year <= 2024:
        p = BATCH_2020_2024 / str(year) / f"{yyyymmdd}.parquet"
    elif 2010 <= year <= 2014:
        p = BATCH_2010_2014 / str(year) / f"{yyyymmdd}.parquet"
    else:
        return None
    return p if p.exists() else None


def prefix_breakdown(codes: list[str]) -> dict:
    """按交易所+前两位统计，单列内存友好。"""
    out: dict[str, int] = {}
    for c in codes:
        key = c[:3] if "." in c else c[:0]  # 如 510300.SH -> 510
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


def is_etf(code: str) -> bool:
    num, _, exch = code.partition(".")
    if exch == "SH":
        return num[:2] in ETF_PREFIX_SH
    if exch == "SZ":
        return num[:2] in ETF_PREFIX_SZ
    return False


def deep_sample(year: int, yyyymmdd: str) -> dict:
    p = day_path(year, yyyymmdd)
    if p is None:
        return {"year": year, "file": None, "error": "no file"}
    t0 = time.perf_counter()
    tbl = pq.read_table(p)
    read_s = time.perf_counter() - t0
    df = pl.from_arrow(tbl)
    codes = df["code"].to_list()
    etf_codes = [c for c in codes if is_etf(c)]
    tt = df["trade_time"]
    tt_min, tt_max = str(tt.min()), str(tt.max())
    # 11:30 bar：按实际取值格式匹配（兼容 HHMM 整型/字符串）
    bar_1130 = df.filter(
        pl.col("trade_time").cast(pl.Utf8).str.strip_chars()
        .str.slice(-4, 4).is_in(["1130"])
    )
    etf_1130 = bar_1130.filter(pl.col("code").map_elements(is_etf, return_dtype=pl.Boolean))
    sample_rows = []
    if etf_1130.height:
        cols = [c for c in ["code", "trade_time", "open", "high", "low", "close", "vol", "amount"] if c in etf_1130.columns]
        sample_rows = etf_1130.select(cols).head(3).to_dicts()
    return {
        "year": year,
        "file": str(p.relative_to(REPO)),
        "file_bytes": p.stat().st_size,
        "columns": tbl.column_names,
        "rows": df.height,
        "unique_codes": df["code"].n_unique(),
        "etf_codes": len(etf_codes),
        "trade_time_min": tt_min,
        "trade_time_max": tt_max,
        "bars_at_1130": bar_1130.height,
        "etf_bars_at_1130": etf_1130.height,
        "full_read_seconds": round(read_s, 3),
        "sample_etf_rows_1130": sample_rows,
        "prefix_top20": dict(list(prefix_breakdown(codes).items())[:20]),
    }


def year_etf_presence(year: int) -> dict:
    """每年取年中一个交易日，仅投影 code 列（快速）。"""
    p = day_path(year, f"{year}0601")
    if p is None:
        if 2015 <= year <= 2019:
            d = BATCH_2015_2019 / str(year)
        elif 2020 <= year <= 2024:
            d = BATCH_2020_2024 / str(year)
        else:
            d = BATCH_2010_2014 / str(year)
        cands = sorted(x for x in d.glob("*.parquet") if "0601" <= x.stem[4:] <= "0629")
        if not cands:
            return {"year": year, "error": "no june file"}
        p = cands[0]
    codes = pq.read_table(p, columns=["code"]).column("code").to_pylist()
    etf = [c for c in codes if is_etf(c)]
    return {
        "year": year,
        "file": str(p.relative_to(REPO)),
        "unique_codes": len(set(codes)),
        "etf_codes": len(set(etf)),
        "etf_examples": sorted(set(etf))[:5],
    }


def month_1130_scan_throughput() -> dict:
    """2024-06 整月按日 parquet，lazy 流式过滤 11:30 的 ETF 行，测吞吐。"""
    d = BATCH_2020_2024 / "2024"
    files = sorted(d.glob("202406*.parquet"))
    t0 = time.perf_counter()
    total_rows = 0
    etf_rows = 0
    for f in files:
        lf = pl.scan_parquet(f)
        sel = (
            lf.filter(
                pl.col("trade_time").cast(pl.Utf8).str.strip_chars()
                .str.slice(-4, 4) == "1130"
            )
        )
        df = sel.collect()
        total_rows += df.height
        etf_rows += df["code"].str.slice(0, 2).is_in(list(ETF_PREFIX_SH) + list(ETF_PREFIX_SZ)).sum()
    dt = time.perf_counter() - t0
    return {
        "scope": "2024-06 (user_minute_1m/2024, 22 trading days expected)",
        "files_scanned": len(files),
        "rows_at_1130_total": total_rows,
        "rows_at_1130_etf": int(etf_rows),
        "elapsed_seconds": round(dt, 3),
        "seconds_per_file": round(dt / max(len(files), 1), 3),
        "bytes_scanned": sum(f.stat().st_size for f in files),
    }


def main() -> None:
    result: dict = {"schema_version": 1, "purpose": "minute data availability + cost probe"}
    result["deep_samples"] = []
    for y, d in [(2010, "20100601"), (2015, "20150601"), (2024, "20240601")]:
        result["deep_samples"].append(deep_sample(y, d))
    result["year_etf_presence"] = [year_etf_presence(y) for y in range(2010, 2025)]
    result["month_scan_1130"] = month_1130_scan_throughput()
    out = RUN / "results.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
