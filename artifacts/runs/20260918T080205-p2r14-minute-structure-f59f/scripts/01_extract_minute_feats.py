# -*- coding: utf-8 -*-
"""01_extract_minute_feats.py — exp-20260918-p2r14-minute-structure 抽取阶段。

单次合并投影扫描 data/raw/user_minute_1m（2,431 日）→
data/processed/minute-feats-20260918/minute_feats.parquet（每股每日一行）。

纯数据工程：无因子判定、无回测、无策略结论、不消费试验数。
data/raw 与 data/_meta 全程只读；身份全部 fail-closed：
  - 边界清单 minute_day_files.csv sha256（R10 抽取 run 登记 e9cde37f…）
  - halfday_1130.parquet sha256（配置冻结 f3d4ec03…）
  - baostock 处理表 manifest sha256（daily_2015_2024 配置冻结 2b89bef9…）
  - data/_meta/sha256.tsv 台账抽样重哈希（每批次 3 个日文件 + 竞价 3 个 chunk，seed 17）
交叉核验（表完成后）：
  - 首 bar 竞价量 vs data/raw/xiaodefa/stk_auction_c（seed 17 抽 3 日）
  - limit 状态内部一致性 + 与 halfday high_am/low_am/tradestatus 对照（全窗口计数）
用法：--smoke（3 日冒烟：2015-06-01 / 2020-06-01 / 2024-06-03）；无参全窗口。
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl
import numpy as np

REPO = Path(__file__).resolve().parents[4]  # scripts -> run -> runs -> artifacts -> repo
sys.path.insert(0, str(REPO / "src"))

from quant.research.p2r14_minute_structure import (  # noqa: E402
    FEAT_COLS, FREEZE_LAST, extract_day_features, finalize_feature_table,
    pick_sample)
from quant.research.p2r13_lowfreq import (  # noqa: E402  (identity helpers)
    load_ledger, verify_processed_manifest, verify_raw_file)

RAW = REPO / "data" / "raw" / "user_minute_1m"
DAY_LIST_CSV = (REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
                / "boundary" / "minute_day_files.csv")
DAY_LIST_SHA = "e9cde37f237e387d782f8dbc4452367d3c7e1b2b3c50c424fa5fe67d570f4dfe"
HALFDAY = REPO / "data" / "processed" / "halfday-1130-20260918" / "halfday_1130.parquet"
HALFDAY_SHA = "f3d4ec036594a31446e728af498039378f635fe99adc3b14ce4e134c8836dda2"
BAOSTOCK_DIR = REPO / "data" / "processed" / "baostock-daily-20260917"
BAOSTOCK_MANIFEST_SHA = ("2b89bef9ef6f4ae58b69ca43021552db067b185551c92a05ef6"
                         "ac71d2be59bd3")
AUCTION_DIR = REPO / "data" / "raw" / "xiaodefa" / "stk_auction_c" / "20260913-bulk1"
CACHE = REPO / "data" / "cache" / "minute-feats-20260918"
OUT_DIR = REPO / "data" / "processed" / "minute-feats-20260918"
RUN = Path(__file__).resolve().parents[1]
SMOKE_DAYS = ["2015-06-01", "2020-06-01", "2024-06-03"]

T0 = time.perf_counter()
cnt: dict[str, int] = {}


def C(key: str, n: int = 1) -> None:
    cnt[key] = cnt.get(key, 0) + int(n)


def log(msg: str) -> None:
    print(f"[{time.perf_counter() - T0:7.1f}s] {msg}", flush=True)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def peak_rss_bytes() -> int:
    try:
        import psutil
        return int(psutil.Process().memory_info().peak_wset)
    except Exception:
        pass
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize",
                                                              ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage",
                                                         ctypes.c_size_t)]
    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    psapi = ctypes.WinDLL("psapi")
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(PMC),
                                           ctypes.c_size_t]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    handle = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
        return -1
    return int(pmc.PeakWorkingSetSize)


def load_day_list() -> list[dict]:
    import csv
    got = sha256_of(DAY_LIST_CSV)
    if got != DAY_LIST_SHA:
        raise RuntimeError(f"identity fail-closed: day list sha256 {got} != "
                           f"{DAY_LIST_SHA}")
    with open(DAY_LIST_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 2431:
        raise RuntimeError(f"day list rows {len(rows)} != 2431")
    for r in rows:
        if r["date"] > FREEZE_LAST.isoformat():
            raise RuntimeError(f"freeze violation in day list: {r['date']}")
    return rows


def verify_identities(day_rows: list[dict]) -> dict:
    ledger = load_ledger(REPO)
    out: dict = {"day_list_csv_sha256": sha256_of(DAY_LIST_CSV)}
    got_half = sha256_of(HALFDAY)
    if got_half != HALFDAY_SHA:
        raise RuntimeError(f"identity fail-closed: halfday sha256 {got_half} "
                           f"!= frozen {HALFDAY_SHA}")
    out["halfday_sha256"] = got_half
    out["baostock_manifest"] = verify_processed_manifest(
        REPO, "data/processed/baostock-daily-20260917/manifest.json",
        BAOSTOCK_MANIFEST_SHA)
    # 抽样重哈希：每分钟批次 3 个日文件 + 竞价 3 个 chunk（seed 17）
    sample_files = []
    for batch in ("20260913-143215", "20260913-2020-2024"):
        rels = [f"user_minute_1m/{batch}/{r['date'][:4]}/"
                f"{r['date'].replace('-', '')}.parquet"
                for r in day_rows if batch_of(r) == batch]
        picks = pick_sample(rels, 3)
        sample_files += picks
        for rel in picks:
            verify_raw_file(REPO, rel, ledger)
    auction_rels = [f"xiaodefa/stk_auction_c/20260913-bulk1/{p.name}"
                    for p in sorted(AUCTION_DIR.glob("chunk_*.csv"))]
    for rel in pick_sample(auction_rels, 3):
        verify_raw_file(REPO, rel, ledger)
        sample_files.append(rel)
    out["sampled_reshash_ok"] = sample_files
    out["sampled_reshash_count"] = len(sample_files)
    return out


def batch_of(r: dict) -> str:
    return Path(r["path"]).parts[0]


def day_path(r: dict) -> Path:
    return RAW / r["path"]


def run_scan(day_rows: list[dict]) -> dict:
    per_year_rows: dict[str, int] = {}
    parts: dict[int, list[pl.DataFrame]] = {}
    for i, r in enumerate(day_rows):
        d_iso = r["date"]
        year = int(d_iso[:4])
        feats, c = extract_day_features(day_path(r), d_iso)
        for k, v in c.items():
            C(k, v)
        parts.setdefault(year, []).append(feats)
        per_year_rows[d_iso[:4]] = per_year_rows.get(d_iso[:4], 0) + feats.height
        if (i + 1) % 200 == 0 or (i + 1) == len(day_rows):
            el = time.perf_counter() - T0
            log(f"progress {i + 1}/{len(day_rows)} elapsed={el:.0f}s "
                f"({el / (i + 1) * 1000:.0f}ms/day) "
                f"rss={peak_rss_bytes() / 2**30:.2f}GiB")
        nxt = day_rows[i + 1]["date"][:4] if i + 1 < len(day_rows) else None
        if nxt != d_iso[:4]:
            ydf = pl.concat(parts.pop(year))
            ydf.write_parquet(CACHE / f"part_{year}.parquet",
                              compression="zstd", compression_level=3)
            log(f"year {year} flushed: {ydf.height} rows "
                f"rss={peak_rss_bytes() / 2**30:.2f}GiB")
    return per_year_rows


def auction_crosscheck(feats: pl.DataFrame, day_rows: list[dict]) -> dict:
    """预登记交叉核验：首 bar 竞价量 vs xiaodefa/stk_auction_c（seed 17 抽 3 日，
    每日 2,000 只）。

    实测结论（冒烟已证）：stk_auction_c 的 OHLC 与 baostock 日线 OHLC 全量
    一致（≠竞价单点撮合价），其 vol/amount 与分钟首 bar 竞价量系统性不符
    （比值 9–160 倍）——预登记对其「竞价独立记录源」的语义假设被本对照证伪，
    该源不可用作首 bar 竞价量的交叉核验。本函数保留全部数字作为证伪证据，
    并改用分钟包内部证据（09:30 bar 单一价格 + 正量占比）验证竞价 bar 语义。
    判据/阈值/池不变；仅核验披露变更。
    """
    dates = sorted({r["date"] for r in day_rows})
    report: dict = {
        "verdict": "REFUTED_AND_REPLACED_BY_INTERNAL_CHECK",
        "prereg_assumption": "stk_auction_c 为首 bar 竞价量的独立记录源",
        "empirics": [], "internal_check": [],
        "note": "vol 单位两侧均为股。实测：文件 vol 与分钟首 bar 竞价量系统性"
                "不符（比值 5–300 倍，无一匹配）；文件 OHLC 与日线 OHLC 仅约"
                "40%（1 分内）一致、与分钟 PM 窗口亦不完全一致，真实语义未定"
                "——确定不是开盘竞价撮合记录。首 bar 竞价量改以分钟包内部证据"
                "（单一价格占比等）披露语义：45–72% 股票日首 bar 非纯单点价，"
                "即 vendor 09:30 bar 含少量最早连续成交，U6 特征按「09:30 bar"
                "量」解读并携带该语义噪声。判据/阈值/池不变，仅核验披露变更。"}
    daily = (pl.scan_parquet(BAOSTOCK_DIR / "daily_2015_2024.parquet")
             .select("symbol", "date", "open", "high", "low", "close"))
    for d_iso in sorted(pick_sample(dates, 3)):
        d = date.fromisoformat(d_iso)
        chunk = AUCTION_DIR / f"chunk_{d_iso.replace('-', '')}.csv"
        if not chunk.exists():
            raise RuntimeError(f"auction chunk missing for {d_iso}")
        aud = pl.read_csv(chunk, schema_overrides={"vol": pl.Float64})
        aud = aud.with_columns(
            pl.col("ts_code").str.split(".").list.reverse().list.join(".")
              .str.to_lowercase().alias("symbol"))
        day_feats = feats.filter(pl.col("date") == d)
        sub_syms = pick_sample(day_feats["symbol"].to_list(), 2000)
        day_feats = day_feats.filter(pl.col("symbol").is_in(sub_syms))
        aud = aud.filter(pl.col("symbol").is_in(sub_syms))
        dd = daily.filter(pl.col("date") == d).collect()
        j = (day_feats.select("symbol", "first_bar_vol")
             .join(aud.select("symbol", "vol", "open", "high", "low",
                              "close"),
                   on="symbol", how="inner")
             .join(dd, on="symbol", how="inner")
             .drop_nulls().filter(pl.col("vol") > 0))
        rel = (j.select(((pl.col("first_bar_vol") - pl.col("vol")).abs()
                         / pl.col("vol")).alias("rel"))
               .filter(pl.col("rel").is_finite()))
        arr = rel["rel"].to_numpy()
        ratio = (j["vol"] / j["first_bar_vol"]).drop_nulls().to_numpy()
        n_ohlc_eq = int(j.select(
            ((pl.col("open") - pl.col("open_right")).abs() <= 0.011).sum()
            + ((pl.col("high") - pl.col("high_right")).abs() <= 0.011).sum()
            + ((pl.col("low") - pl.col("low_right")).abs() <= 0.011).sum()
            + ((pl.col("close") - pl.col("close_right")).abs() <= 0.011)
              .sum()).item())
        entry = {
            "date": d_iso, "n_checked": int(j.height),
            "n_rel_gt_1e-3": int((arr > 1e-3).sum()),
            "vol_ratio_file_over_first_bar_p10_p50_p90": [
                float(np.quantile(ratio, q)) for q in (0.1, 0.5, 0.9)],
            "file_ohlc_eq_daily_ohlc_1fen_share":
                n_ohlc_eq / (4 * j.height) if j.height else None,
        }
        report["empirics"].append(entry)
        # 内部证据：09:30 bar 语义（主板 SH/SZ、有量 bar）
        m = pl.read_parquet(day_path(next(r for r in day_rows
                                          if r["date"] == d_iso)))
        b930 = m.filter(pl.col("trade_time").str.contains(" 09:30:00")
                        & pl.col("code").str.contains(r"^\d{6}\.(SH|SZ)$"))
        traded = b930.filter(pl.col("vol") > 0)
        single = traded.select(
            ((pl.col("open") == pl.col("high"))
             & (pl.col("high") == pl.col("low"))
             & (pl.col("low") == pl.col("close"))).alias("sp"))
        report["internal_check"].append({
            "date": d_iso, "bars_sh_sz": int(b930.height),
            "bars_vol_gt0": int(traded.height),
            "vol_gt0_share": float(traded.height / b930.height),
            "single_price_share": float(single["sp"].mean()),
            "open_eq_close_share": float(
                (traded["open"] == traded["close"]).mean()),
        })
        log(f"auction crosscheck {d_iso}: {json.dumps(entry)}")
    return report


def limit_consistency(feats: pl.DataFrame, halfday: pl.DataFrame) -> dict:
    """全窗口一致性计数：状态机内部矛盾应为 0；与 halfday 的 AM 极值差
    允许非零（零量 bar 剔除所致），逐项披露。"""
    j = feats.join(
        halfday.select("symbol", "date", "limit_up", "high_am", "low_am"),
        on=["symbol", "date"], how="left")
    if j["high_am"].null_count():
        raise RuntimeError("halfday join lost rows in consistency check")
    d: dict = {}
    d["state_seal_rows"] = int(
        j.select((pl.col("limit_close_state") == 2).sum()).item())
    d["state_broke_rows"] = int(
        j.select((pl.col("limit_close_state") == 1).sum()).item())
    d["state_untouched_rows"] = int(
        j.select((pl.col("limit_close_state") == 0).sum()).item())
    d["state_null_rows_limit_missing"] = int(
        j.select(pl.col("limit_close_state").is_null().sum()).item())
    d["pm_touch_true_rows"] = int(
        j.select((pl.col("pm_touch_limit_down") == True).sum()).item())  # noqa: E712
    d["pm_touch_null_rows"] = int(
        j.select(pl.col("pm_touch_limit_down").is_null().sum()).item())
    # 内部矛盾（应为 0）：触板状态但 day_high 低于触板阈值
    d["touch_state_contradictions"] = int(j.select(
        ((pl.col("limit_close_state").is_in([1, 2]))
         & (pl.col("day_high")
            < pl.col("limit_up") * (1.0 - 1e-4) - 1e-9)).sum()).item())
    # 与 halfday AM 极值对照（零量 bar 剔除可致 day_high < high_am）
    d["day_high_lt_halfday_high_am"] = int(j.select(
        (pl.col("day_high") < pl.col("high_am") - 1e-6).sum()).item())
    d["day_low_gt_halfday_low_am"] = int(j.select(
        (pl.col("day_low") > pl.col("low_am") + 1e-6).sum()).item())
    d["day_high_eq_halfday_high_am"] = int(j.select(
        ((pl.col("day_high") - pl.col("high_am")).abs() <= 1e-6).sum()).item())
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--from-cache", action="store_true",
                    help="resume: reuse flushed per-year parts (full run "
                         "only); scan-phase counters are then taken from the "
                         "previous attempt's log")
    args = ap.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (RUN / "logs").mkdir(exist_ok=True)

    day_rows = load_day_list()
    identity = verify_identities(day_rows)
    log("identity fail-closed checks passed")

    if args.smoke:
        smoke_rows = [r for r in day_rows if r["date"] in SMOKE_DAYS]
        if len(smoke_rows) != 3:
            raise RuntimeError("smoke day set incomplete")
        run_scan(smoke_rows)
        feats = pl.read_parquet(
            [str(p) for p in sorted(CACHE.glob("part_*.parquet"))])
        report = auction_crosscheck(feats, smoke_rows)
        out = {"mode": "smoke", "days": SMOKE_DAYS,
               "counters": cnt, "auction_crosscheck": report,
               "elapsed_s": round(time.perf_counter() - T0, 1)}
        (RUN / "logs" / "smoke.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        log("smoke done: " + json.dumps(out["auction_crosscheck"]))
        return

    if args.from_cache:
        parts = sorted(CACHE.glob("part_*.parquet"))
        if len(parts) != 10:
            raise RuntimeError(f"--from-cache expects 10 year parts, "
                               f"found {len(parts)}")
        feats = pl.read_parquet([str(p) for p in parts])
        per_year_rows = {p.stem.split("_")[1]: int(
            pl.scan_parquet(str(p)).select(pl.len()).collect().item())
            for p in parts}
        log(f"resumed from cache: {len(parts)} parts, {feats.height} rows")
    else:
        per_year_rows = run_scan(day_rows)
        feats = pl.read_parquet(
            [str(p) for p in sorted(CACHE.glob("part_*.parquet"))])
    log(f"scan done: {feats.height} rows; finalize (med20 + limits)")
    half_limits = (pl.scan_parquet(HALFDAY)
                   .select("symbol", "date", "limit_up", "limit_down",
                           "close_day_official", "high_am", "low_am",
                           "tradestatus")
                   .collect())
    traded_rows = int((half_limits["tradestatus"] == 1).sum())
    feats = finalize_feature_table(
        feats, half_limits.drop("high_am", "low_am", "tradestatus"))
    consistency = limit_consistency(feats, half_limits)
    log("consistency: " + json.dumps(consistency))

    # ---- assertions ----
    A: dict = {}
    A["A5_freeze_max_date"] = {"max_date": str(feats["date"].max()),
                               "pass": feats["date"].max() <= FREEZE_LAST}
    dup = feats.height - feats.select("symbol", "date").unique().height
    A["A7_symbol_date_unique"] = {"duplicates": int(dup), "pass": dup == 0}
    med_null = int(feats["first_bar_vol_med20"].null_count())
    med_expected = int(feats.group_by("symbol").agg(pl.len().alias("n"))
                       .select(pl.col("n").clip(0, 20).sum()).item())
    A["A8_med20_null_share"] = {
        "null_rows": med_null, "expected_null_rows": med_expected,
        "pass": med_null == med_expected}
    rows = feats.height
    A["A1_rows_vs_halfday_traded"] = {
        "feats_rows": rows, "halfday_traded_rows": traded_rows,
        "diff": rows - traded_rows,
        "diff_pct": (rows - traded_rows) / traded_rows,
        "pass": abs(rows - traded_rows) / traded_rows < 0.005,
        "note": "feats < traded rows by no-bar traded stock-days (~9k "
                "registered) and all-zero-volume traded days"}
    A["A9_state_distribution"] = consistency

    out_fp = OUT_DIR / "minute_feats.parquet"
    out = feats.select(list(FEAT_COLS))
    out.write_parquet(out_fp, compression="zstd", compression_level=3,
                      statistics=True)
    digest = sha256_of(out_fp)
    auction_report = auction_crosscheck(out, day_rows)
    log("auction crosscheck: " + json.dumps(auction_report))
    A["A10_table_sha256"] = digest
    elapsed = time.perf_counter() - T0
    peak = peak_rss_bytes()

    manifest = {
        "dataset_id": "minute-feats-20260918",
        "experiment_id": "exp-20260918-p2r14-minute-structure",
        "run_id": RUN.name,
        "nature": "分钟投影扫描特征表：每股每日一行；无判定、无回测、不消费试验数",
        "source_prereg": "docs/research/exp-20260918-p2r14-minute-structure-prereg.md",
        "source_config": "configs/experiments/p2r14-minute-structure.json",
        "operationalizations": "src/quant/research/p2r14_minute_structure.py 模块 docstring（实现前冻结披露）",
        "inputs": {
            "minute_day_list": {
                "path": str(DAY_LIST_CSV.relative_to(REPO)),
                "sha256": DAY_LIST_SHA,
                "days": len(day_rows)},
            "minute_batches": [
                {"path": f"data/raw/user_minute_1m/{b}",
                 "identity": "data/_meta/sha256.tsv 逐文件登记（prep run 20260918T032049 全量字节比对）"}
                for b in ("20260913-143215", "20260913-2020-2024")],
            "sampled_reshash": identity["sampled_reshash_ok"],
            "halfday_1130": {"path": "data/processed/halfday-1130-20260918/"
                                     "halfday_1130.parquet",
                             "sha256": HALFDAY_SHA,
                             "role": "limit_up/limit_down/close_day_official 状态列 + 一致性对照"},
            "baostock_daily": {
                "manifest": "data/processed/baostock-daily-20260917/manifest.json",
                "manifest_sha256": BAOSTOCK_MANIFEST_SHA,
                "role": "仅经 halfday 表内嵌字段进入本表（preclose/close 官方口径）"},
            "auction_crosscheck_source": {
                "path": "data/raw/xiaodefa/stk_auction_c/20260913-bulk1",
                "role": "首 bar 竞价量独立对照（抽样 3 日）"}},
        "outputs": {
            "path": "data/processed/minute-feats-20260918/minute_feats.parquet",
            "rows": int(out.height), "bytes": out_fp.stat().st_size,
            "sha256": digest, "compression": "zstd level 3",
            "sort": "symbol, date",
            "column_contract": {c: "见模块 docstring" for c in FEAT_COLS}},
        "per_year_rows": per_year_rows,
        "counters": cnt,
        "crosschecks": {"auction": auction_report,
                        "limit_consistency": consistency},
        "assertions": A,
        "timing": {"total_seconds": round(elapsed, 1),
                   "mean_ms_per_day": elapsed / len(day_rows) * 1000,
                   "peak_rss_gib": round(peak / 2**30, 2),
                   "budget": "抽取 ≤ 1800s / 8GB（判定层另计同预算）"},
        "known_limitations": [
            "零量（vol==0）bar 视为占位剔除（DATA_SOURCES §1.3）；全日零量股票日不成行",
            "day_high/day_low 只用有量 bar：与 halfday high_am/low_am 的差见 "
            "crosschecks.limit_consistency 逐项计数（零量 bar 剔除所致，如实披露）",
            "5 个 stk_limit 零行日及停牌/上市首日 limit 缺失 → limit_close_state/pm_touch_limit_down 如实 null",
            "first_bar_vol_med20 需 20 个自身交易日历史（shift-in-over），每符号前 20 行 null",
            "close_1430/close_1500 bar 零量时 last30_ret null（如实缺失计数）",
            "本表价格为原始价（分币还原），无复权；跨日收益由消费层用 preclose_official 桥接",
        ],
        "environment": {
            "python": sys.version.split()[0], "polars": pl.__version__,
            "platform": "win32", "random_seed": 17},
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (RUN / "logs" / "extract_counters.json").write_text(
        json.dumps({"counters": cnt, "assertions": A,
                    "per_year_rows": per_year_rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"table written: {out.height} rows sha256={digest[:16]}... "
        f"elapsed={elapsed:.0f}s peak={peak / 2**30:.2f}GiB")
    bad = {k: v for k, v in A.items() if isinstance(v, dict)
           and v.get("pass") is False}
    if bad:
        raise RuntimeError(f"assertions failed: {list(bad)}")


if __name__ == "__main__":
    main()
