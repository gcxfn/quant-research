# -*- coding: utf-8 -*-
"""03_schema_symbol_check.py — G2 半天截面前置：抽样 5 日文件 schema 一致性与股票池交集。

只读 data/raw 与 data/processed/baostock-daily-20260917；输出写 run 目录 schema_check/。
抽样日：2015-06-01 / 2017-06-01 / 2019-06-03 / 2021-06-01 / 2024-06-03（2024 加看 2024-12-31 的 .BJ 尾盘行为）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import polars as pl

REPO = Path(r"D:\量化")
RAW = REPO / "data" / "raw" / "user_minute_1m"
POOL = REPO / "data" / "processed" / "baostock-daily-20260917" / "daily_2015_2024.parquet"
RUN = REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
SAMPLES = {
    "2015": RAW / "20260913-143215/2015/20150601.parquet",
    "2017": RAW / "20260913-143215/2017/20170601.parquet",
    "2019": RAW / "20260913-143215/2019/20190603.parquet",
    "2021": RAW / "20260913-2020-2024/2021/20210601.parquet",
    "2024": RAW / "20260913-2020-2024/2024/20240603.parquet",
}
EXTRA = {"20241231": RAW / "20260913-2020-2024/2024/20241231.parquet"}


def to_baostock(code: str) -> str:
    sym, suf = code.split(".")
    return f"{suf.lower()}.{sym}"


def main() -> int:
    t0 = time.perf_counter()
    pool_syms = set(
        pl.scan_parquet(POOL).select(pl.col("symbol").unique()).collect()["symbol"].to_list()
    )
    print(f"[pool] baostock 日线池 symbols={len(pool_syms)} (格式如 sh.600000)")

    schemas = {}
    day_reports = {}
    union_minute = set()
    for tag, fp in {**SAMPLES, **EXTRA}.items():
        df = pl.read_parquet(fp)
        schemas[tag] = {n: str(t) for n, t in df.schema.items()}
        n_symbols = df["code"].n_unique()
        bars = df.group_by("code").len()
        b_min, b_max = bars["len"].min(), bars["len"].max()
        n_not241 = bars.filter(pl.col("len") != 241).height
        b1130 = df.filter(pl.col("trade_time").str.contains(" 11:30:00")).group_by("code").len()
        n_1130 = b1130.height
        n_1130_not1 = b1130.filter(pl.col("len") != 1).height
        suf = sorted(set(c.split(".")[-1] for c in df["code"].unique().to_list()))
        mset = set(df["code"].unique().to_list())
        union_minute |= {to_baostock(c) for c in mset if c.endswith((".SH", ".SZ"))}
        day_reports[tag] = {
            "file": str(fp.relative_to(REPO)),
            "rows": len(df),
            "symbols": n_symbols,
            "suffixes": suf,
            "bars_per_symbol_min_max": [b_min, b_max],
            "symbols_not_241_bars": n_not241,
            "bars_1130_total": n_1130,
            "bars_1130_not_exactly_1": n_1130_not1,
        }
        print(f"[{tag}] rows={len(df)}, symbols={n_symbols}, suffixes={suf}, "
              f"bars∈[{b_min},{b_max}], !=241: {n_not241}, 11:30 bars={n_1130} (not-1: {n_1130_not1})")

    # schema 一致性（5 个抽样日文件之间，不含额外复核文件）
    base = schemas["2015"]
    schema_diffs = {t: {k: v for k, v in s.items() if base.get(k) != v}
                    for t, s in schemas.items() if t != "2015"}
    schema_identical = all(not d for d in schema_diffs.values())

    # 与 baostock 池交集（仅抽样 5 日的 union）
    inter = union_minute & pool_syms
    minute_only = sorted(union_minute - pool_syms)
    bj_codes = set()
    for tag, fp in SAMPLES.items():
        df = pl.read_parquet(fp, columns=["code"])
        bj_codes |= set(df["code"].unique().to_list()) - {c for c in df["code"].unique().to_list() if c.endswith((".SH", ".SZ"))}
    day_level = {}
    for tag, fp in SAMPLES.items():
        df = pl.read_parquet(fp, columns=["code"])
        mset = {to_baostock(c) for c in df["code"].unique().to_list() if c.endswith((".SH", ".SZ"))}
        day_level[tag] = {
            "minute_sh_sz": len(mset),
            "in_pool": len(mset & pool_syms),
            "minute_only": len(mset - pool_syms),
            "minute_only_examples": sorted(mset - pool_syms)[:10],
            "pool_size": len(pool_syms),
        }
        print(f"[inter {tag}] minute(sh/sz)={len(mset)} in_pool={len(mset & pool_syms)} "
              f"minute_only={len(mset - pool_syms)}")

    report = {
        "purpose": "schema consistency + symbol intersection vs baostock pool (pure data engineering)",
        "run_id": RUN.name,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "pool_symbols": len(pool_syms),
        "schema_by_sample": schemas,
        "schema_identical_across_5_samples": schema_identical,
        "schema_diffs": schema_diffs,
        "day_reports": day_reports,
        "intersection_union_of_5_days": {
            "minute_union_sh_sz": len(union_minute),
            "in_pool": len(inter),
            "minute_only_total": len(minute_only),
        },
        "day_level_intersection": day_level,
        "non_sh_sz_codes_in_5_samples": sorted(bj_codes)[:30],
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }
    (RUN / "schema_check").mkdir(parents=True, exist_ok=True)
    (RUN / "schema_check" / "schema_symbol_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] schema_identical={schema_identical}, report -> schema_check/schema_symbol_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
