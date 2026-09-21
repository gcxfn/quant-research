# -*- coding: utf-8 -*-
"""01_extract_halfday.py — exp-20260918-halfday-extract：11:30 半天截面抽取（全窗口 2,431 日）。

纯数据工程：无因子、无回测、无策略结论、不消费试验数。
输入（只读）：
  - data/raw/user_minute_1m/{20260913-143215,20260913-2020-2024}/（2,431 个按日 parquet，
    身份见 data/_meta/sha256.tsv 与 prep run 20260918T032049-halfday-prep-f3mbfd）
  - data/raw/tushare/stk_limit/20260917-r1/（涨跌停，按列名归一读取；5 个零行日 → NaN）
  - data/processed/baostock-daily-20260917/daily_2015_2024.parquet（preclose/close/high/low/tradestatus/isST）
输出：
  - data/processed/halfday-1130-20260918/halfday_1130.parquet（每股每日一行）
  - data/cache/halfday-1130-20260918/part_<year>.parquet（分年增量落盘，可重建）
  - run 目录 manifest.json / logs

列契约（一次定死）：
  symbol(baostock 风格 sh/sz.XXXXXX), date(Date),
  pre_close_vendor(当日 09:30 首 bar 的 pre_close，vendor 昨收口径),
  preclose_official(baostock preclose，除权昨收),
  open_930/close_1100/close_1130/open_1300/close_1500（各关键 bar，分币还原）,
  close_day_official(baostock close),
  high_am/low_am（09:30–11:30 bar 的 max/min，分币还原）, vol_am/amount_am（09:30–11:30 求和，f64）,
  limit_up/limit_down（stk_limit r1 join，5 零行日 NaN）,
  am_limit_up_touch_minutes（上午内 fen_restore(high) >= limit_up 的分钟数，涨停板缺失→0）,
  tradestatus/isST（baostock join，Int8）, suspended_flag(tradestatus==0),
  bars_that_day（该股该日 ≤15:00 的 SH/SZ bar 数）。
过滤（全部计数）：.BJ 剔除；trade_time>15:00:00 剔除；冻结边界 ≤2024-12-31（文件名+行级双验）；
baostock 池外代码剔除（应为 0）。复权不做：原始价 + 官方昨收。
用法：--dates 2015-06-01,2020-06-01,2024-06-03 --smoke（冒烟）；无参（全窗口）。
"""
from __future__ import annotations

import argparse
import csv as _csv
import ctypes
import hashlib
import json
import random
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

REPO = Path(r"D:\量化")
RAW = REPO / "data" / "raw" / "user_minute_1m"
DAY_LIST_CSV = (REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
                / "boundary" / "minute_day_files.csv")
STK_LIMIT_DIR = REPO / "data" / "raw" / "tushare" / "stk_limit" / "20260917-r1"
STK_LIMIT_MANIFEST = STK_LIMIT_DIR / "manifest.json"
POOL = REPO / "data" / "processed" / "baostock-daily-20260917" / "daily_2015_2024.parquet"
POOL_MANIFEST = REPO / "data" / "processed" / "baostock-daily-20260917" / "manifest.json"
SHA_TSV = REPO / "data" / "_meta" / "sha256.tsv"
OUT_DIR = REPO / "data" / "processed" / "halfday-1130-20260918"
CACHE = REPO / "data" / "cache" / "halfday-1130-20260918"
RUN = Path(__file__).resolve().parents[1]
FREEZE_MAX = "2024-12-31"
FREEZE_MAX_COMPACT = "20241231"  # 分钟包 date 列为 YYYYMMDD 字符串
KEY_TODS = ["09:30:00", "11:00:00", "11:30:00", "13:01:00", "15:00:00"]
# 注：vendor 无 13:00 bar（下午自 13:01 起，121+120=241 根）；契约列 open_1300 实取 13:01 首 bar open，manifest 已注
EXPECTED_ROWS = 9_556_362  # prep §4 全窗口外推（断言 ±5%）
PROTO_DAYS = ["2015-06-01", "2020-06-01", "2024-06-03"]
PROTO_STAMP = {"2015-06-01": ("20260913-143215", "20150601"),
               "2020-06-01": ("20260913-2020-2024", "20200601"),
               "2024-06-03": ("20260913-2020-2024", "20240603")}
STK_ZERO_ROW_DAYS = {"2017-03-07", "2017-03-08", "2017-03-09", "2022-07-26", "2023-04-21"}

cnt: dict[str, int] = {}
DIAG_POOL_MISS: list[dict] = []


def C(key: str, n=1) -> None:
    cnt[key] = cnt.get(key, 0) + int(n)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def peak_rss_bytes() -> int:
    """Windows GetProcessMemoryInfo → PeakWorkingSetSize。"""

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    psapi = ctypes.WinDLL("psapi")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_uint32]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return -1
    return int(pmc.PeakWorkingSetSize)


def fen(s: pl.Expr) -> pl.Expr:
    """float32→float64 后按 0.01 元还原（prep 已验证 float32 分币编码，残差率 0）。"""
    return (s.cast(pl.Float64) * 100).round() / 100


def read_limit_chunk(d_iso: str) -> pl.DataFrame:
    """按列名归一读取 stk_limit r1 单日 chunk（深扫规则：列序不可信、空/零行文件显式列名）。"""
    schema = {"ts_code": pl.Utf8, "up_limit": pl.Float64, "down_limit": pl.Float64}
    fp = STK_LIMIT_DIR / f"chunk_{d_iso.replace('-', '')}.csv"
    if not fp.exists() or fp.stat().st_size == 0:
        C("stk_limit_chunk_file_missing_or_empty")
        return pl.DataFrame(schema={"code": pl.Utf8, "limit_up": pl.Float64,
                                    "limit_down": pl.Float64})
    raw = pl.read_csv(fp, schema_overrides=schema)
    if raw.height == 0:
        C("stk_limit_zero_row_day")  # 登记的 5 个零行日（仅表头文件）
        return pl.DataFrame(schema={"code": pl.Utf8, "limit_up": pl.Float64,
                                    "limit_down": pl.Float64})
    if any(c not in raw.columns for c in ("ts_code", "up_limit", "down_limit")):
        C("stk_limit_chunk_missing_columns")
        return pl.DataFrame(schema={"code": pl.Utf8, "limit_up": pl.Float64,
                                    "limit_down": pl.Float64})
    out = raw.select(pl.col("ts_code").alias("code"),
                     pl.col("up_limit").alias("limit_up"),
                     pl.col("down_limit").alias("limit_down"))
    dups = int(out.height) - int(out["code"].n_unique())
    if dups:
        C("stk_limit_duplicate_keys", dups)
    return out


def process_day(d_iso: str, fp: Path, daily_day: pl.DataFrame) -> pl.DataFrame:
    tod = pl.col("trade_time").str.slice(11, 8).alias("tod")
    df = pl.read_parquet(fp).with_columns(tod)

    C("source_rows", df.height)
    is_bj = pl.col("code").str.ends_with(".BJ")
    gt15 = pl.col("tod") > "15:00:00"
    C("bj_rows_removed", df.select(is_bj.sum()).item())
    C("gt15_rows_removed_raw", df.select(gt15.sum()).item())
    C("gt15_rows_removed_non_bj", df.filter(~is_bj).select(gt15.sum()).item())  # 应为 0
    C("bar_1300_rows_present", df.select((pl.col("tod") == "13:00:00").sum()).item())  # 应为 0
    C("date_col_mismatch_filename", df.select((pl.col("date") != d_iso.replace("-", "")).sum()).item())
    C("date_col_rows_gt_freeze", df.select((pl.col("date") > FREEZE_MAX_COMPACT).sum()).item())  # 应为 0

    df = df.filter(~is_bj & ~gt15)

    # ---- 上午聚合 + 触板分钟（先 join 涨跌停再按 code 聚合）----
    am = (df.filter(pl.col("tod") <= "11:30:00")
          .join(read_limit_chunk(d_iso), on="code", how="left"))
    amagg = am.group_by("code").agg(
        fen(pl.col("high").max()).alias("high_am"),
        fen(pl.col("low").min()).alias("low_am"),
        pl.col("vol").cast(pl.Float64).sum().alias("vol_am"),
        pl.col("amount").cast(pl.Float64).sum().alias("amount_am"),
        pl.col("limit_up").first().alias("limit_up"),
        pl.col("limit_down").first().alias("limit_down"),
        (fen(pl.col("high")) >= pl.col("limit_up")).fill_null(False).sum()
            .cast(pl.UInt32).alias("am_limit_up_touch_minutes"),
    )

    # ---- 关键 bar（每股每日每键恰 1 根，违例计数；prep 已证 11:30 恰 1）----
    kb = df.filter(pl.col("tod").is_in(KEY_TODS))
    dup = kb.group_by(["code", "tod"]).len().filter(pl.col("len") > 1)
    C("key_bar_dup_violations", 0 if dup.is_empty() else int(dup["len"].sum()))
    b930 = kb.filter(pl.col("tod") == "09:30:00").select(
        "code", fen(pl.col("open")).alias("open_930"),
        fen(pl.col("pre_close")).alias("pre_close_vendor"))
    b1100 = kb.filter(pl.col("tod") == "11:00:00").select(
        "code", fen(pl.col("close")).alias("close_1100"))
    b1130 = kb.filter(pl.col("tod") == "11:30:00").select(
        "code", fen(pl.col("close")).alias("close_1130"))
    b1300 = kb.filter(pl.col("tod") == "13:01:00").select(
        "code", fen(pl.col("open")).alias("open_1300"))
    b1500 = kb.filter(pl.col("tod") == "15:00:00").select(
        "code", fen(pl.col("close")).alias("close_1500"))

    snap = (df.group_by("code").len().rename({"len": "bars_that_day"})
            .join(b930, on="code", how="left")
            .join(b1100, on="code", how="left")
            .join(b1130, on="code", how="left")
            .join(b1300, on="code", how="left")
            .join(b1500, on="code", how="left")
            .join(amagg, on="code", how="left"))
    for c in ["open_930", "close_1100", "close_1130", "open_1300", "close_1500"]:
        C("key_bar_missing_" + c, int(snap[c].null_count()))  # 应为 0

    # ---- stk_limit join 缺口计数（左连 NaN 如实保留；5 零行日为登记缺口）----
    n_nan = int(snap["limit_up"].null_count())
    n_nan_dn = int(snap["limit_down"].null_count())
    C("stk_limit_unmatched_rows", n_nan)
    if n_nan and d_iso not in STK_ZERO_ROW_DAYS:
        C("stk_limit_unmatched_rows_outside_zero_days", n_nan)
    C("stk_limit_unmatched_rows_limit_down", n_nan_dn)

    # ---- baostock join（池外剔除并计数，应为 0）----
    snap = (snap.with_columns(
                pl.col("code").str.split(".").list.reverse().list.join(".")
                    .str.to_lowercase().alias("symbol"),
                pl.lit(date.fromisoformat(d_iso)).alias("date"))
            .drop("code"))
    dd = (daily_day.drop("date")
          .rename({"preclose": "preclose_official", "close": "close_day_official"})
          .with_columns(pl.lit(True).alias("_in_pool")))
    snap = snap.join(dd, on="symbol", how="left")
    n_miss = int(snap["_in_pool"].null_count())
    C("baostock_join_miss_rows_dropped", n_miss)
    if n_miss:
        miss_syms = sorted(snap.filter(pl.col("_in_pool").is_null())["symbol"].to_list())
        DIAG_POOL_MISS.append({"date": d_iso, "symbols": miss_syms})
        C("baostock_join_miss_symbols_distinct", len(miss_syms))
        snap = snap.filter(pl.col("_in_pool").is_not_null())
    snap = snap.drop("_in_pool")

    # ---- 无 bar 的 (symbol,date) 计数（不成行，入 manifest）----
    nobar = dd.select("symbol", "tradestatus").join(snap.select("symbol"), on="symbol", how="anti")
    C("no_bar_pairs_total", nobar.height)
    C("no_bar_pairs_suspended_tradestatus0",
      int(nobar.select((pl.col("tradestatus") == 0).sum()).item() or 0))

    snap = snap.with_columns(
        pl.col("tradestatus").cast(pl.Int8),
        pl.col("isST").cast(pl.Int8),
        (pl.col("tradestatus") == 0).fill_null(False).alias("suspended_flag"),
    )
    return snap.select([
        "symbol", "date", "pre_close_vendor", "preclose_official",
        "open_930", "close_1100", "close_1130", "open_1300", "close_1500", "close_day_official",
        "high_am", "low_am", "vol_am", "amount_am", "limit_up", "limit_down",
        "am_limit_up_touch_minutes", "tradestatus", "isST", "suspended_flag", "bars_that_day"])


def load_day_list() -> list[dict]:
    with open(DAY_LIST_CSV, encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    assert len(rows) == 2431, f"day list rows {len(rows)} != 2431"
    for r in rows:  # 文件级冻结边界双验之「文件名」侧
        assert Path(r["path"]).stem == r["date"].replace("-", ""), f"bad name {r['path']}"
        assert r["date"] <= FREEZE_MAX, f"freeze violation {r['date']}"
    return rows


def load_daily_map() -> tuple[pl.DataFrame, dict]:
    daily = pl.read_parquet(POOL, columns=["symbol", "date", "preclose", "close",
                                           "high", "low", "tradestatus", "isST"])
    assert daily["date"].max() <= date(2024, 12, 31), "pool table exceeds freeze line"
    dmap = {k[0]: v for k, v in
            daily.partition_by("date", maintain_order=True, as_dict=True).items()}
    return daily, dmap


def run_extract(day_rows, dmap, log) -> tuple[dict, dict]:
    parts_by_year: dict[int, list[pl.DataFrame]] = {}
    per_year_rows: dict[str, int] = {}
    per_day_stats = []
    for i, r in enumerate(day_rows):
        t1 = time.perf_counter()
        d_iso, year = r["date"], r["date"][:4]
        fp = RAW / Path(r["path"]).as_posix()
        dd = dmap.get(date.fromisoformat(d_iso))
        assert dd is not None, f"baostock missing date {d_iso}"
        snap = process_day(d_iso, fp, dd)
        parts_by_year.setdefault(int(year), []).append(snap)
        per_year_rows[year] = per_year_rows.get(year, 0) + snap.height
        per_day_stats.append({"date": d_iso, "rows": snap.height,
                              "s": round(time.perf_counter() - t1, 3)})
        if (i + 1) % 200 == 0 or (i + 1) == len(day_rows):
            el = time.perf_counter() - T_START
            log(f"progress {i+1}/{len(day_rows)} elapsed={el:.0f}s "
                f"({el/(i+1)*1000:.0f}ms/day) rss={peak_rss_bytes()/2**30:.2f}GiB")
        nxt = day_rows[i + 1]["date"][:4] if i + 1 < len(day_rows) else None
        if nxt != year:
            ydf = pl.concat(parts_by_year.pop(int(year)))
            ydf.write_parquet(CACHE / f"part_{year}.parquet",
                              compression="zstd", compression_level=3)
            log(f"year {year} flushed: {ydf.height} rows, "
                f"rss={peak_rss_bytes()/2**30:.2f}GiB")
    return per_year_rows, per_day_stats


def smoke_checks(dmap, log) -> None:
    """冒烟：重跑 3 个 prep 原型日，逐值对比 + 触板只数/日线区间对照。"""
    proto_dir = REPO / "data" / "cache" / "halfday_1130_proto_20260918"
    expected_touch = {"2015-06-01": 214, "2020-06-01": 106}  # prep §5.4 实测
    report = {}
    for d_iso, (batch, stamp) in PROTO_STAMP.items():
        fp = RAW / batch / d_iso[:4] / f"{stamp}.parquet"
        snap = process_day(d_iso, fp, dmap[date.fromisoformat(d_iso)])
        proto = pl.read_parquet(proto_dir / f"snap1130_{stamp}.parquet").with_columns(
            pl.col("code").str.split(".").list.reverse().list.join(".")
                .str.to_lowercase().alias("symbol"),
            pl.col("date").str.to_date("%Y%m%d"))
        j = (snap.select("symbol", "date", "pre_close_vendor", "close_1130",
                         "bars_that_day", "am_limit_up_touch_minutes")
             .join(proto.select("symbol", "date", "pre_close", "close"),
                   on=["symbol", "date"], how="inner"))
        n_pre = int((j["pre_close_vendor"] - j["pre_close"]).abs().gt(1e-9).sum())
        n_cls = int((j["close_1130"] - j["close"]).abs().gt(1e-9).sum())
        rng_rows = snap.join(
            dmap[date.fromisoformat(d_iso)].select(
                "symbol", pl.col("high").alias("d_high"), pl.col("low").alias("d_low")),
            on="symbol")
        in_range = int(rng_rows.select(
            ((pl.col("close_1130") <= pl.col("d_high") + 1e-6) &
             (pl.col("close_1130") >= pl.col("d_low") - 1e-6)).sum()).item())
        report[d_iso] = {
            "rows": snap.height, "joined_with_proto": j.height,
            "proto_keys_missing": snap.height - j.height,
            "pre_close_vendor_mismatch": n_pre, "close_1130_mismatch": n_cls,
            "bars_non241": int((snap["bars_that_day"] != 241).sum()),
            "close1130_in_daily_lowhigh": in_range,
            "am_touch_limit_up_stocks": int((snap["am_limit_up_touch_minutes"] >= 1).sum()),
            "prep_expected_touch_stocks": expected_touch.get(d_iso),
        }
        log(f"smoke {d_iso}: " + json.dumps(report[d_iso], ensure_ascii=False))
    (RUN / "logs" / "smoke_proto_compare.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN / "logs" / "smoke_counters.json").write_text(
        json.dumps(cnt, ensure_ascii=False, indent=2), encoding="utf-8")


def assertions(final: pl.DataFrame, out_fp: Path, day_rows, per_day_stats, log) -> dict:
    A: dict[str, dict] = {}

    # A1 行数 ≈ 9.56M ±5%
    lo, hi = EXPECTED_ROWS * 0.95, EXPECTED_ROWS * 1.05
    A["A1_rows_within_5pct"] = {"rows": final.height, "expected_prep_extrapolation": EXPECTED_ROWS,
                                "lower": int(lo), "upper": int(hi),
                                "pass": bool(lo <= final.height <= hi)}

    # A2 每股每年 ≤244
    per_sy = final.group_by(["symbol", pl.col("date").dt.year().alias("year")]).len()
    mx = int(per_sy["len"].max())
    A["A2_symbol_year_rows_le_244"] = {"max": mx, "limit": 244, "pass": mx <= 244}

    # A3 close_1130 ∈ baostock [low,high]：3 个 prep 原型日全量 + 20 抽样日全量
    rng = random.Random(20260918)
    pool_dates = [r["date"] for r in day_rows if r["date"] not in PROTO_DAYS]
    sample20 = sorted(rng.sample(pool_dates, 20))
    chk_set = {date.fromisoformat(d) for d in PROTO_DAYS + sample20}
    pool_range = pl.read_parquet(POOL, columns=["symbol", "date", "high", "low"])
    oor = ((pl.col("close_1130") > pl.col("high") + 1e-6) |
           (pl.col("close_1130") < pl.col("low") - 1e-6))
    sub = (final.filter(pl.col("date").is_in(sorted(chk_set)))
           .join(pool_range, on=["symbol", "date"], how="inner").with_columns(oor.alias("_oor")))
    viol = sub.filter(pl.col("_oor"))
    viol_proto = int(viol.filter(pl.col("date").is_in(
        [date.fromisoformat(d) for d in PROTO_DAYS])).height)
    viol_sample = viol.height - viol_proto
    (RUN / "logs" / "a3_checked_days_violations.json").write_text(
        json.dumps(viol.drop("_oor").select(
            "symbol", "date", "close_1130", "low", "high").to_dicts(),
            ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    A["A3_close1130_in_daily_range"] = {
        "proto_days_full": {d: {"pass": viol_proto == 0} for d in PROTO_DAYS},
        "proto_days_violations": viol_proto,
        "sampled_days": sample20, "rows_checked": sub.height,
        "sampled_days_violations": viol_sample,
        "violation_evidence": "logs/a3_checked_days_violations.json",
        "pass": viol_proto == 0 and viol_sample == 0}
    # 诊断性全窗口同项复核（成本一次 join），含归因拆分
    allj = final.join(pool_range, on=["symbol", "date"], how="inner").with_columns(
        oor.alias("_oor"))
    vall = allj.filter(pl.col("_oor"))
    n_susp = int(vall.select(pl.col("suspended_flag").sum()).item())
    (RUN / "logs" / "a3_full_window_violations.json").write_text(
        json.dumps(vall.drop("_oor").select(
            "symbol", "date", "close_1130", "low", "high", "tradestatus",
            "suspended_flag", "bars_that_day").to_dicts(),
            ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    A["A3b_close1130_in_daily_range_full_window_diagnostic"] = {
        "rows": allj.height, "violations": vall.height,
        "violations_suspended_placeholder": n_susp,
        "violations_trading_rows": vall.height - n_susp,
        "distinct_symbols": int(vall["symbol"].n_unique()),
        "attribution": "越界集中为停牌占位行（baostock 冻结日线 OHLC 与 vendor 冻结分钟价不一致，"
                       "如 sz.000033 长期停牌段 228 行）与极少量交易日源间分歧（2015 极端日）；"
                       "全部逐行证据见 logs/a3_full_window_violations.json",
        "note": "诊断性全窗口，非契约要求"}

    # A4 .BJ 残留 = 0
    n_bj = int(final.select(pl.col("symbol").str.starts_with("bj.").sum()).item())
    A["A4_bj_residual_zero"] = {"rows": n_bj,
                                "bj_rows_removed_in_extract": cnt.get("bj_rows_removed", 0),
                                "pass": n_bj == 0}

    # A5 冻结边界：2025+ 行 = 0（行级）
    n_future = int(final.select((pl.col("date") > date(2024, 12, 31)).sum()).item())
    A["A5_no_rows_after_2024_12_31"] = {"rows": n_future,
                                        "max_date": str(final["date"].max()),
                                        "row_level_violations_in_extract":
                                            cnt.get("date_col_rows_gt_freeze", 0),
                                        "pass": n_future == 0}

    # A6 与 prep 3 日原型逐值一致（同列：symbol/date/pre_close_vendor/close_1130）
    proto_dir = REPO / "data" / "cache" / "halfday_1130_proto_20260918"
    mism_pre = mism_cls = missing = 0
    for d_iso, (batch, stamp) in PROTO_STAMP.items():
        proto = pl.read_parquet(proto_dir / f"snap1130_{stamp}.parquet").with_columns(
            pl.col("code").str.split(".").list.reverse().list.join(".")
                .str.to_lowercase().alias("symbol"),
            pl.col("date").str.to_date("%Y%m%d"))
        j = (final.filter(pl.col("date") == date.fromisoformat(d_iso))
             .select("symbol", "date", "pre_close_vendor", "close_1130")
             .join(proto.select("symbol", "date", "pre_close", "close"),
                   on=["symbol", "date"], how="inner"))
        mism_pre += int((j["pre_close_vendor"] - j["pre_close"]).abs().gt(1e-9).sum())
        mism_cls += int((j["close_1130"] - j["close"]).abs().gt(1e-9).sum())
        missing += int(final.select((pl.col("date") == date.fromisoformat(d_iso)).sum()).item()) - j.height
    A["A6_proto_3day_value_identical"] = {
        "columns_compared": ["pre_close_vendor↔pre_close", "close_1130↔close"],
        "pre_close_mismatches": mism_pre, "close_1130_mismatches": mism_cls,
        "keys_missing_vs_proto": missing, "pass": mism_pre == 0 and mism_cls == 0 and missing == 0}

    # A7 (symbol,date) 唯一
    dupk = int(final.height - final.select(["symbol", "date"]).n_unique())
    A["A7_symbol_date_unique"] = {"duplicate_keys": dupk, "pass": dupk == 0}

    # A8 关键 bar 完整性与 bars_that_day 诊断
    nulls = {c: int(final[c].null_count()) for c in
             ["open_930", "close_1100", "close_1130", "open_1300", "close_1500", "high_am", "low_am"]}
    A["A8_key_bars_complete"] = {"nulls": nulls,
                                 "pass": all(v == 0 for v in nulls.values())}
    bdist = final.group_by("bars_that_day").len().sort("bars_that_day")
    A["diagnostics_bars_that_day_distribution"] = {
        str(int(r["bars_that_day"])): int(r["len"]) for r in bdist.iter_rows(named=True)}
    # 涨跌停 NaN 归因：5 个登记零行日之外，其余 NaN 是否=停牌股/新股首日（stk_limit 对停牌股不出价）
    nan_all = final.filter(pl.col("limit_up").is_null())
    zero_set = {date.fromisoformat(d) for d in STK_ZERO_ROW_DAYS}
    nan_out = nan_all.filter(~pl.col("date").is_in(sorted(zero_set)))
    firsts = final.group_by("symbol").agg(pl.col("date").min().alias("first"))
    nan_out_f = nan_out.join(firsts, on="symbol")
    A["diagnostics_limit_nan_days"] = {
        "expected_zero_row_days": sorted(STK_ZERO_ROW_DAYS),
        "nan_rows_on_zero_days": int(nan_all.filter(pl.col("date").is_in(sorted(zero_set))).height),
        "nan_rows_outside_zero_days_in_table": nan_out.height,
        "outside_distinct_dates": int(nan_out["date"].n_unique()),
        "outside_suspended_rows": int(nan_out.select(pl.col("suspended_flag").sum()).item()),
        "outside_is_stock_first_row": int((nan_out_f["date"] == nan_out_f["first"]).sum()),
        "attribution": "零行日外 NaN 集中为停牌股（tushare stk_limit 对停牌股不出涨跌停价）与少量上市首日；"
                       "与抽取期计数差 = 池外剔除行（其本身亦无涨跌停价）",
        "extraction_phase_unmatched_total": cnt.get("stk_limit_unmatched_rows", 0),
        "extraction_phase_unmatched_outside_zero_days":
            cnt.get("stk_limit_unmatched_rows_outside_zero_days", 0)}
    return A


def write_manifest(out_fp: Path, final_rows: int, day_rows, per_year_rows, per_day_stats,
                   log_lines, A) -> None:
    t_done = time.perf_counter()
    (RUN / "logs" / "baostock_join_miss_pairs.json").write_text(
        json.dumps(DIAG_POOL_MISS, ensure_ascii=False, indent=1), encoding="utf-8")
    manifest = {
        "run_id": RUN.name,
        "experiment_id": "exp-20260918-halfday-extract",
        "task": "user_minute_1m 全窗口（2015–2024, 2,431 日）→ 11:30 半天截面分析表（每股每日一行）",
        "nature": "纯数据工程：无因子、无回测、无策略结论、不消费试验数；data/raw 与 data/_meta 全程只读",
        "provenance": {
            "prereq_research_doc": "docs/research/exp-20260918-halfday-prep.md",
            "prereq_run": "artifacts/runs/20260918T032049-halfday-prep-f3mbfd",
            "reading_rules": "docs/DATA_COVERAGE.md（冻结过滤、列名归一、空表头校验）",
        },
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(T_START)),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "completed" if all(a.get("pass") for a in A.values() if isinstance(a, dict) and "pass" in a) else "completed_with_failed_assertions",
        "environment": {
            "platform": "win32 (Windows 10.0.26200 x64), Git Bash",
            "python": sys.version.split()[0] + " (D:/量化/.venv/Scripts/python.exe, -X utf8)",
            "polars": pl.__version__,
            "command": f"PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 "
                       f"artifacts/runs/{RUN.name}/scripts/01_extract_halfday.py",
        },
        "inputs": {
            "minute_batches": [
                {"path": "data/raw/user_minute_1m/20260913-143215",
                 "day_parquet_files": sum(1 for r in day_rows if r["batch"] == "20260913-143215"),
                 "identity": "data/_meta/sha256.tsv 逐文件登记（prep run 01 全量字节比对+抽样重哈希 REGISTERED_VERIFIED）"},
                {"path": "data/raw/user_minute_1m/20260913-2020-2024",
                 "day_parquet_files": sum(1 for r in day_rows if r["batch"] == "20260913-2020-2024"),
                 "identity": "同上；两批次合计 2,431 个日 parquet + 各 1 个 transfer-manifest.json = 2,433 条登记"},
            ],
            "minute_day_list": {
                "path": str(DAY_LIST_CSV.relative_to(REPO)),
                "sha256": sha256_of(DAY_LIST_CSV),
                "source": "prep run boundary/minute_day_files.csv（2,431 日 bytes/num_rows/trade_time min-max）",
                "sha256_tsv": {"path": "data/_meta/sha256.tsv", "sha256": sha256_of(SHA_TSV)},
            },
            "stk_limit": {
                "path": "data/raw/tushare/stk_limit/20260917-r1",
                "manifest_sha256": sha256_of(STK_LIMIT_MANIFEST),
                "rows": 9705448, "chunks": 2431, "range": "20150105..20241231",
                "registered_as": "docs/market-rules-handbook.md trade-009 涨跌停注册主源",
                "known_gap": "5 个零行日（2017-03-07/08/09、2022-07-26、2023-04-21）→ 本表 limit_up/limit_down 如实 NaN",
                "read_rule": "按列名归一（列序不可信）；零行日=仅表头文件",
            },
            "baostock_daily": {
                "path": "data/processed/baostock-daily-20260917/daily_2015_2024.parquet",
                "manifest_sha256": sha256_of(POOL_MANIFEST),
                "rows": 9532019, "note": "P1 已验收池（5,328 只；preclose/close/tradestatus/isST；未复权）",
            },
        },
        "outputs": {
            "halfday_1130_parquet": {
                "path": str(out_fp.relative_to(REPO)),
                "rows": final_rows, "bytes": out_fp.stat().st_size,
                "sha256": sha256_of(out_fp),
                "compression": "zstd level 3", "sort": "symbol, date",
            },
            "year_parts_cache": {
                "path": str(CACHE.relative_to(REPO)),
                "files": sorted(p.name for p in CACHE.glob("part_*.parquet")),
                "note": "分年增量落盘（可重建的中间产物，非唯一证据）",
            },
            "per_year_rows": per_year_rows,
        },
        "column_contract": COLUMN_CONTRACT,
        "filters_and_counts": dict(sorted(cnt.items())),
        "diagnostics_evidence": {
            "baostock_join_miss_pairs": "logs/baostock_join_miss_pairs.json（池外剔除的 (date,symbol) 逐行清单，应为空、非空则须归因）",
            "a3_checked_days_violations": "logs/a3_checked_days_violations.json",
            "a3_full_window_violations": "logs/a3_full_window_violations.json",
            "per_day_stats": "logs/per_day_stats.json",
        },
        "assertions": A,
        "timing": {
            "total_seconds": round(t_done - T_START, 1),
            "total_minutes": round((t_done - T_START) / 60, 2),
            "extract_phase_seconds": round(sum(d["s"] for d in per_day_stats), 1),
            "mean_ms_per_day": round(1000 * sum(d["s"] for d in per_day_stats) / max(len(per_day_stats), 1), 1),
            "peak_rss_bytes": PEAK_RSS[0], "peak_rss_gib": round(PEAK_RSS[0] / 2**30, 2),
            "budget": "30 min / 11 GB",
            "per_day_detail": "logs/per_day_stats.json",
        },
        "config_and_code_summary":
            "单脚本流式逐日处理：读分钟日文件→.BJ/15:00 过滤→上午聚合+触板计数+关键 bar→"
            "stk_limit r1 按日 chunk join（列名归一）→baostock 日线 join（池外剔除）→分年落盘→合并排序→断言",
        "random_seed": "断言抽样 random.Random(20260918)（仅用于 A3 的 20 日抽样，确定性）",
        "time_splits": "不适用（未计算任何标签/信号/收益；全部数据 ≤2024-12-31）",
        "known_limitations": KNOWN_LIMITATIONS,
        "logs": sorted(p.name for p in (RUN / "logs").glob("*")),
    }
    (RUN / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    (RUN / "logs" / "per_day_stats.json").write_text(
        json.dumps(per_day_stats, ensure_ascii=False), encoding="utf-8")
    (RUN / "logs" / "extract.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("manifest written:", RUN / "manifest.json")


COLUMN_CONTRACT = {
    "symbol": "baostock 风格 sh.XXXXXX / sz.XXXXXX（分钟包 600000.SH 无损映射；.BJ 已剔除）",
    "date": "交易日（pl.Date；与源文件名、行内 date 列双验一致）",
    "pre_close_vendor": "元，分钟包自带昨收口径=当日 09:30 首 bar 的 pre_close（vendor 内逐 bar pre_close 为上一分钟收价，"
                        "仅 09:30 bar 的等价昨收；除权日=原始前收，非交易所除权昨收——跨日收益一律改用 preclose_official）",
    "preclose_official": "元，baostock daily preclose join（除权昨收；跨日收益唯一合规昨收）",
    "open_930": "元，09:30 bar open，float32→float64 分币还原（0.01 元取整，prep 验证残差率 0）",
    "close_1100": "元，11:00 bar close，同上还原",
    "close_1130": "元，11:30 bar close，同上还原",
    "open_1300": "元，13:01 bar open（vendor 无 13:00 bar：下午自 13:01 起，121 上午+120 下午=241 根；"
                 "契约列名 open_1300 保留，语义=午后首根 bar open），分币还原",
    "close_1500": "元，15:00 bar close，同上还原；注意 2015–2017 沪市不得充当官方收盘（vendor 早收盘口径差，prep §5.1）",
    "close_day_official": "元，baostock daily close（官方日线收盘）",
    "high_am": "元，09:30–11:30 全部 bar 的 high 最大值，分币还原",
    "low_am": "元，09:30–11:30 全部 bar 的 low 最小值，分币还原",
    "vol_am": "股，09:30–11:30 bar vol 逐值 float32→float64 后求和（float32 编码精度受限为源数据已知缺陷）",
    "amount_am": "元，09:30–11:30 bar amount 逐值 float32→float64 后求和（同上）",
    "limit_up": "元，tushare stk_limit 20260917-r1 按 (date,ts_code) join 的 up_limit；5 个零行日如实 NaN",
    "limit_down": "元，同上 down_limit；5 个零行日如实 NaN",
    "am_limit_up_touch_minutes": "上午 09:30–11:30 内满足 fen_restore(high) >= limit_up 的 bar 数"
                                 "（涨停板缺失日为 0；触板≠可成交，成交语义须回测层保守建模）。"
                                 "注意与 prep §5.4 的 214/106 只区分：那是「11:30 单 bar high≥limit−0.005」口径"
                                 "（本 run 复算逐只一致 214/106），本列是全上午逐 bar 计数，"
                                 "股票级 ≥1 分钟只数为 2015-06-01=289、2020-06-01=139，两口径不同、均正确",
    "tradestatus": "baostock daily tradestatus（0=停牌 1=交易），Int8；停牌股有 241 根占位 bar 照常成行",
    "isST": "baostock daily isST（0/1），Int8，历史时点标记",
    "suspended_flag": "tradestatus==0；「该日无 bar」的 (symbol,date) 不成行，计数见 filters_and_counts.no_bar_pairs_*",
    "bars_that_day": "该股该日 ≤15:00 的 SH/SZ bar 数（常态 241=121 上午+120 下午；诊断占位/缺失用）",
    "adjustment": "本表不做任何复权：价格为原始价，昨收双口径（vendor/官方）并排供因子层自选",
}

KNOWN_LIMITATIONS = [
    "open_1300 实为 13:01 首 bar open：vendor 分钟包无 13:00 bar（下午 13:01–15:00 共 120 根，+上午 121=241）；列名按契约保留",
    "close_1130∈日线[low,high] 存在 268/9,440,361 全窗口越界行（0.0028%）：243 行为停牌占位行（baostock 冻结日线与 vendor 冻结分钟价不一致，"
    "sz.000033 长停段 228 行为主），25 行为交易日源间分歧（2015 极端日为主）；逐行证据见 logs/a3_full_window_violations.json",
    "baostock 池外分钟代码剔除 49 行（契约预期 0）：逐行清单与归因见 logs/baostock_join_miss_pairs.json",
    "vol_am/amount_am 源于 float32 编码 bar 值求和，精度受源编码限制（vendor 已知缺陷，非本表引入）",
    "5 个 stk_limit 零行日（2017-03-07/08/09、2022-07-26、2023-04-21）limit_up/limit_down 整日 NaN；"
    "零行日之外还有少量个股级 NaN（集中为停牌股——stk_limit 对停牌股不出价，及少量上市首日），如实保留，"
    "运行时归因计数见 assertions.diagnostics_limit_nan_days",
    "2015-07-01 为登记受审日（尾盘零量占位，实测波及 1,405 只），11:30 前数据不受影响；消费方按 DATA_SOURCES §1 处置",
    "22 项登记待补/受审证券日与 sz.300114 无分钟沿 DATA_SOURCES §1，本表如实缺行/缺值",
    "本表为普查层：股票池（科创板/ST/停牌/创业板权限）过滤留给消费层按历史时点执行，本表只提供 tradestatus/isST/板块可判列",
    "触板分钟数是「硬边界触碰」计数，不构成成交证据（一字板排队、瞬时开板不可见）",
    "baostock 2 行全空价格行（sz.000022 2018-12-26、sz.000043 2019-12-16，tradestatus=0）join 后 preclose/close 为 NaN",
]

PEAK_RSS = [0]
T_START = time.perf_counter()


def main() -> int:
    global T_START
    T_START = time.perf_counter()
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", default=None, help="逗号分隔 ISO 日期子集（冒烟用）")
    ap.add_argument("--smoke", action="store_true", help="只跑抽取与即席核对，不写最终表/manifest")
    args = ap.parse_args()

    CACHE.mkdir(parents=True, exist_ok=True)
    (RUN / "logs").mkdir(exist_ok=True)
    log_lines = []

    def log(msg: str) -> None:
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        log_lines.append(line)

    day_rows = load_day_list()
    log(f"day list OK: 2,431 files {day_rows[0]['date']}..{day_rows[-1]['date']}, "
        f"filename-level freeze check passed")
    if args.dates:
        want = set(args.dates.split(","))
        day_rows = [r for r in day_rows if r["date"] in want]
        log(f"smoke subset: {[r['date'] for r in day_rows]}")

    daily, dmap = load_daily_map()
    log(f"baostock daily loaded: {daily.height} rows, {len(dmap)} dates, "
        f"rss={peak_rss_bytes()/2**30:.2f}GiB")
    PEAK_RSS[0] = max(PEAK_RSS[0], peak_rss_bytes())

    if args.smoke:
        cnt.clear()
        smoke_checks(dmap, log)
        log("SMOKE DONE (no final output written)")
        return 0

    per_year_rows, per_day_stats = run_extract(day_rows, dmap, log)
    PEAK_RSS[0] = max(PEAK_RSS[0], peak_rss_bytes())

    t0 = time.perf_counter()
    part_files = sorted(CACHE.glob("part_*.parquet"))
    assert len(part_files) == len(per_year_rows), \
        f"part files {len(part_files)} != years {len(per_year_rows)}"
    final = pl.read_parquet(part_files).sort(["symbol", "date"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_fp = OUT_DIR / "halfday_1130.parquet"
    final.write_parquet(out_fp, compression="zstd", compression_level=3)
    PEAK_RSS[0] = max(PEAK_RSS[0], peak_rss_bytes())
    log(f"final written: rows={final.height} cols={final.width} "
        f"size={out_fp.stat().st_size/2**20:.1f}MiB in {time.perf_counter()-t0:.1f}s, "
        f"rss={peak_rss_bytes()/2**30:.2f}GiB")

    A = assertions(final, out_fp, day_rows, per_day_stats, log)
    for k, v in A.items():
        if isinstance(v, dict) and "pass" in v:
            log(f"{k}: pass={v['pass']} ({json.dumps({kk: vv for kk, vv in v.items() if kk != 'pass'}, ensure_ascii=False)[:300]})")
    write_manifest(out_fp, final.height, day_rows, per_year_rows, per_day_stats, log_lines, A)
    failed = [k for k, v in A.items() if isinstance(v, dict) and "pass" in v and not v["pass"]]
    log(f"DONE. failed_assertions={failed if failed else 'none'}")
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
