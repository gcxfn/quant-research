# -*- coding: utf-8 -*-
"""04_extract_1130_prototype.py — G2 半天截面前置：11:30 快照抽取原型（仅 3 个抽样日，不做全窗口）。

只读 data/raw 与 data/processed；产物写 data/cache/halfday_1130_proto_20260918/（可重建，git 忽略）；
计时与外推写 run 目录。

抽取口径（原型）：
- 11:30 bar：trade_time 含 " 11:30:00" 的行（每股每日恰 1 根，已由 02/03 验证）；
- 列：code, date, open, high, low, close, vol, amount + pre_close（日级昨收，
  取自当日 09:30 首 bar 的 pre_close——分钟文件内逐 bar 的 pre_close 是上一分钟 bar 收价，不是昨收）；
- 分币还原：价格 float32 → float64，按 0.01 元取整（并统计还原残差比例）；
- vol/amount：float32 → float64（仅升精度，不改值；单位：股 / 元）。
"""
from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

import polars as pl

REPO = Path(r"D:\量化")
RAW = REPO / "data" / "raw" / "user_minute_1m"
POOL = REPO / "data" / "processed" / "baostock-daily-20260917" / "daily_2015_2024.parquet"
CACHE = REPO / "data" / "cache" / "halfday_1130_proto_20260918"
RUN = REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
DAYS = [
    ("2015-06-01", RAW / "20260913-143215/2015/20150601.parquet"),
    ("2020-06-01", RAW / "20260913-2020-2024/2020/20200601.parquet"),
    ("2024-06-03", RAW / "20260913-2020-2024/2024/20240603.parquet"),
]
PRICE_COLS = ["open", "high", "low", "close", "pre_close"]


def fen_restore_check(s: pl.Series) -> tuple[pl.Series, float]:
    """float32→float64 后按分取整；返回(还原序列, 不在 0.5 分内的比例)。"""
    v = s.cast(pl.Float64)
    resid = (v * 100 - (v * 100).round()).abs()
    bad = (resid > 0.05).sum() / len(v) if len(v) else 0.0
    return (v * 100).round() / 100, float(bad)


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    results = []
    for date, fp in DAYS:
        # --- 变体 A：全列读 + 过滤（基线） ---
        t0 = time.perf_counter()
        df = pl.read_parquet(fp)
        t_read = time.perf_counter() - t0

        t0 = time.perf_counter()
        bar = df.filter(pl.col("trade_time").str.contains(" 11:30:00")).select(
            ["code", "date", "open", "high", "low", "close", "vol", "amount"])
        first = df.filter(pl.col("trade_time").str.contains(" 09:30:00")).select(
            [pl.col("code"), pl.col("pre_close")])
        snap = bar.join(first, on="code", how="left").rename({"pre_close": "pre_close"})
        t_extract = time.perf_counter() - t0

        # 分币还原（价格列）
        t0 = time.perf_counter()
        bad_rates = {}
        for c in PRICE_COLS:
            snap = snap.with_columns(pl.col(c).cast(pl.Float64))
        for c in PRICE_COLS[:-1]:
            fixed, bad = fen_restore_check(snap[c])
            snap = snap.with_columns(fixed.alias(c))
            bad_rates[c] = bad
        # pre_close 已 cast；同样还原
        fixed, bad = fen_restore_check(snap["pre_close"])
        snap = snap.with_columns(fixed.alias("pre_close"))
        bad_rates["pre_close"] = bad
        snap = snap.with_columns(pl.col("vol").cast(pl.Float64), pl.col("amount").cast(pl.Float64))
        snap = snap.sort("code")
        t_round = time.perf_counter() - t0

        # --- 写出（zstd 与 snappy 两种，仅测大小） ---
        out_z = CACHE / f"snap1130_{date.replace('-', '')}.parquet"
        t0 = time.perf_counter()
        snap.write_parquet(out_z, compression="zstd", compression_level=3)
        t_write_z = time.perf_counter() - t0
        out_s = CACHE / f"snap1130_{date.replace('-', '')}_snappy.parquet"
        t0 = time.perf_counter()
        snap.write_parquet(out_s, compression="snappy")
        t_write_s = time.perf_counter() - t0

        # --- 与 baostock 日线核验 09:30 pre_close == 日线 preclose（昨收口径交叉证据） ---
        import datetime as _dt
        d_val = _dt.date.fromisoformat(date)
        daily = pl.read_parquet(POOL, columns=["symbol", "date", "preclose", "high", "low"])
        d0 = daily.filter(pl.col("date") == d_val)
        chk = snap.select([pl.col("code"), pl.col("pre_close")]).with_columns(
            (pl.col("code").str.split(".").list.reverse().list.join(".")).str.to_lowercase().alias("symbol")
        ).join(d0, on="symbol", how="inner")
        n = len(chk)
        diff = (chk["pre_close"] - chk["preclose"].cast(pl.Float64)).abs()
        match = (diff <= 0.005).sum()
        # 11:30 close 是否落在当日日线 high/low 内（口径互证）
        d1 = d0.select(
            ["symbol", pl.col("high").cast(pl.Float64).alias("d_high"), pl.col("low").cast(pl.Float64).alias("d_low")])
        chk2 = snap.with_columns(
            (pl.col("code").str.split(".").list.reverse().list.join(".")).str.to_lowercase().alias("symbol")
        ).join(d1, on="symbol", how="inner")
        in_range = ((chk2["close"] <= chk2["d_high"] + 1e-6) & (chk2["close"] >= chk2["d_low"] - 1e-6)).sum()

        row = {
            "date": date,
            "file": str(fp.relative_to(REPO)),
            "source_bytes": fp.stat().st_size,
            "source_rows": len(df),
            "snapshot_rows": len(snap),
            "read_full_s": round(t_read, 3),
            "extract_s": round(t_extract, 4),
            "fen_round_s": round(t_round, 4),
            "write_zstd_s": round(t_write_z, 4),
            "write_snappy_s": round(t_write_s, 4),
            "zstd_bytes": out_z.stat().st_size,
            "snappy_bytes": out_s.stat().st_size,
            "zstd_bytes_per_row": round(out_z.stat().st_size / len(snap), 2),
            "fen_bad_rate": bad_rates,
            "preclose_vs_baostock": {"matched": int(match), "of": n, "rate": round(match / n, 5) if n else None},
            "close_in_daily_range": {"in": int(in_range), "of": len(chk2)},
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False))
        out_s.unlink()  # snappy 变体仅用于测大小，不留副本

    # ---- 外推（用 02 号脚本采集的逐日 num_rows，代表性强） ----
    with open(RUN / "boundary" / "minute_day_files.csv", encoding="utf-8") as f:
        day_files = list(csv.DictReader(f))
    total_rows = sum(int(r["num_rows"]) for r in day_files)
    total_source_bytes = sum(int(r["bytes"]) for r in day_files)
    snap_rows_total = sum(int(r["num_rows"]) / 241 for r in day_files)  # SH/SZ 每股恰 241 bar

    rate_rows = sum(r["source_rows"] for r in results) / sum(
        r["read_full_s"] + r["extract_s"] + r["fen_round_s"] + r["write_zstd_s"] for r in results)
    rate_bytes = sum(r["source_bytes"] for r in results) / sum(
        r["read_full_s"] + r["extract_s"] + r["fen_round_s"] + r["write_zstd_s"] for r in results)
    est_rows = total_rows / rate_rows
    est_bytes = total_source_bytes / rate_bytes
    bpr = sum(r["zstd_bytes_per_row"] for r in results) / len(results)
    extrap = {
        "n_days_full_window": len(day_files),
        "total_source_rows": total_rows,
        "total_source_bytes": total_source_bytes,
        "snapshot_rows_total_est": round(snap_rows_total),
        "measured_rate_rows_per_s": round(rate_rows),
        "measured_rate_bytes_per_s": round(rate_bytes),
        "est_total_seconds_by_rows": round(est_rows),
        "est_total_seconds_by_bytes": round(est_bytes),
        "est_wall_minutes": round(min(est_rows, est_bytes) / 60, 1),
        "est_output_bytes_zstd": round(snap_rows_total * bpr),
        "zstd_bytes_per_snapshot_row_avg": round(bpr, 2),
        "note": "线性外推（按行/按字节两口径取保守小者）；3 个抽样日未覆盖 2016/2018/2022/2023，"
                "num_rows 来自 02 号脚本全窗口元数据，snap 行数按每股 241 bar 换算（483 个 .BJ 尾盘日误差可忽略且 .BJ 本就不入池）",
    }
    print("[extrapolate]", json.dumps(extrap, ensure_ascii=False))

    summary = {
        "purpose": "11:30 snapshot extraction prototype, 3 sample days ONLY (full window NOT run; awaiting preregistration)",
        "run_id": RUN.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "output_cache_dir": str(CACHE.relative_to(REPO)),
        "schema_of_snapshot": {c: str(t) for c, t in snap.schema.items()},
        "per_day": results,
        "extrapolation_full_window": extrap,
    }
    (RUN / "extract_1130_proto.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    CACHE.joinpath("extract_1130_proto_timing.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] cache={CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
