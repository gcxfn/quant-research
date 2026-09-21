# -*- coding: utf-8 -*-
"""01_build_halfday_bars.py — dataset_id ``halfday-bars-20260918`` 扫描构建阶段。

纯数据工程：user_minute_1m（2015–2024，2,431 日）→ 每标的每交易日 上午/下午
各一根 OHLCV 半日 bar，供区间契约 v1 双决策点（11:30 / 15:00）挂单成交判定使用。
无因子、无回测、无策略结论、不消费试验数。data/raw 与 data/_meta 全程只读。

分段契约（随 manifest 落盘）：
  AM = trade_time 时段 <= 11:30:00 的 bar（含 09:30 集合竞价 bar；本包 AM 网格
       09:30..11:30 共 121 根/日）
  PM = trade_time 时段 >= 13:00:00 的 bar（含 15:00 收盘集合竞价 bar；本包无
       13:00 bar，PM 网格 13:01..15:00 共 120 根/日）
  n_minutes_expected = 该日文件内全市场出现的该时段 distinct 分钟网格数（逐日
       实测，不硬编码）；partial = n_minutes < n_minutes_expected（有量分钟不足）。
零量（vol==0）bar 为 vendor 占位（DATA_SOURCES §1.3 / R14 已验证约定），不进入
任何聚合；某标的某时段没有任何有量 bar → 不造行（缺行=该时段不可交易）。
单位（DATA_SOURCES §1 登记口径）：价格=元（float32 分币编码按分还原，R10 验证
零残差）；volume=股（f32 值逐个转 f64 后求和，值域内精确）；amount=元（同法）。
处理顺序沿用 R14 run 20260918T080205 已验证约定：date 列与文件名一致性、冻结
边界（<=2024-12-31）、.BJ 剔除、15:00 之后非 .BJ 行 raise。

用法：
  --smoke  2015-06 + 2024-06 全部交易日（覆盖两个批次）→ 写运行目录
           tmp/smoke_out/year=YYYY/，并做 2 标的 × 2 日纯 Python 手工聚合对齐。
  --full   全窗口 2,431 日 → 写 data/processed/halfday-bars-20260918/
           year=YYYY/bars.parquet（每整年 flush 一次）。
"""
from __future__ import annotations

import argparse
import ctypes
import csv
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[4]  # scripts -> run -> runs -> artifacts -> repo
sys.path.insert(0, str(REPO / "src"))

from quant.research.p2r13_lowfreq import (  # noqa: E402  (identity helpers)
    load_ledger, verify_processed_manifest, verify_raw_file)
from quant.research.p2r14_minute_structure import (  # noqa: E402
    FREEZE_LAST, pick_sample)

# 价格分币还原：float32 → f64 后 round(2)。R10 已验证 vendor float32 为分格
# 编码（零残差），故 round(2) 无损且逐值恰为该分值的最近 f64（R14 fen() 的
# `*100 再 /100` 变体带 ±1ulp 表示差；本表选精确表示，语义相同）。


def fen2(c: str) -> pl.Expr:
    return pl.col(c).cast(pl.Float64).round(2)

RAW = REPO / "data" / "raw" / "user_minute_1m"
DAY_LIST_CSV = (REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
                / "boundary" / "minute_day_files.csv")
DAY_LIST_SHA = "e9cde37f237e387d782f8dbc4452367d3c7e1b2b3c50c424fa5fe67d570f4dfe"
BAOSTOCK_MANIFEST_SHA = ("2b89bef9ef6f4ae58b69ca43021552db067b185551c92a05ef6"
                         "ac71d2be59bd3")
OUT_DIR = REPO / "data" / "processed" / "halfday-bars-20260918"
RUN = Path(__file__).resolve().parents[1]
SMOKE_MONTHS = ("2015-06", "2024-06")
FREEZE_MAX_COMPACT = "20241231"

COLUMNS = ["symbol", "trade_date", "session", "open", "high", "low", "close",
           "volume", "amount", "n_minutes", "n_minutes_expected", "partial"]

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
    """day list sha256 + baostock manifest + 每分钟批次抽 3 个日文件重哈希
    （seed 17，与 R14 同法）。"""
    ledger = load_ledger(REPO)
    out: dict = {"day_list_csv_sha256": sha256_of(DAY_LIST_CSV)}
    out["baostock_manifest"] = verify_processed_manifest(
        REPO, "data/processed/baostock-daily-20260917/manifest.json",
        BAOSTOCK_MANIFEST_SHA)
    sample_files: list[str] = []
    for batch in ("20260913-143215", "20260913-2020-2024"):
        rels = [f"user_minute_1m/{batch}/{r['date'][:4]}/"
                f"{r['date'].replace('-', '')}.parquet"
                for r in day_rows if r["path"].replace("\\", "/").startswith(batch + "/")]
        for rel in pick_sample(rels, 3):
            verify_raw_file(REPO, rel, ledger)
            sample_files.append(rel)
    out["sampled_reshash_ok"] = sample_files
    return out


def normalize_symbol() -> pl.Expr:
    return (pl.col("code").str.split(".").list.reverse().list.join(".")
            .str.to_lowercase().alias("symbol"))


def agg_session(traded: pl.DataFrame, d_iso: str, session: str,
                pred: pl.Expr, expected: int) -> pl.DataFrame:
    part = traded.filter(pred).sort("code", "tod")
    if part.height == 0:
        return pl.DataFrame(schema={c: t for c, t in [
            ("symbol", pl.String), ("trade_date", pl.Date),
            ("session", pl.String), ("open", pl.Float64), ("high", pl.Float64),
            ("low", pl.Float64), ("close", pl.Float64),
            ("volume", pl.Float64), ("amount", pl.Float64),
            ("n_minutes", pl.Int32), ("n_minutes_expected", pl.Int32),
            ("partial", pl.Boolean)]})
    out = part.group_by("code", maintain_order=True).agg(
        fen2("open").first().alias("open"),
        fen2("high").max().alias("high"),
        fen2("low").min().alias("low"),
        fen2("close").last().alias("close"),
        pl.col("vol").cast(pl.Float64).sum().alias("volume"),
        pl.col("amount").cast(pl.Float64).sum().alias("amount"),
        pl.len().cast(pl.Int32).alias("n_minutes"),
    )
    return out.with_columns(
        normalize_symbol(),
        pl.lit(date.fromisoformat(d_iso)).alias("trade_date"),
        pl.lit(session).alias("session"),
        pl.lit(expected, dtype=pl.Int32).alias("n_minutes_expected"),
        (pl.col("n_minutes") < pl.lit(expected, dtype=pl.Int32))
        .alias("partial"),
    ).select(COLUMNS)


def build_day(fp: Path, d_iso: str) -> pl.DataFrame:
    """单日文件 → 半日 bar 行（am/pm 各至多一行每标的）。fail-closed 语义同 R14。"""
    if d_iso > FREEZE_LAST.isoformat():
        raise RuntimeError(f"freeze violation: requested day {d_iso} "
                           f"> {FREEZE_LAST}")
    tod = pl.col("trade_time").str.slice(11, 8).alias("tod")
    df = pl.read_parquet(fp).with_columns(tod)
    compact = d_iso.replace("-", "")
    C("source_rows", df.height)
    n_mismatch = int(df.select((pl.col("date") != compact).sum()).item())
    if n_mismatch:
        raise RuntimeError(f"{d_iso}: date column mismatches filename "
                           f"({n_mismatch} rows)")
    n_freeze = int(df.select((pl.col("date") > FREEZE_MAX_COMPACT).sum()).item())
    if n_freeze:
        raise RuntimeError(f"{d_iso}: rows after freeze line ({n_freeze})")
    is_bj = pl.col("code").str.ends_with(".BJ")
    gt15 = pl.col("tod") > "15:00:00"
    C("bj_rows_removed", int(df.select(is_bj.sum()).item()))
    n_gt15_non_bj = int(df.filter(~is_bj).select(gt15.sum()).item())
    if n_gt15_non_bj:
        raise RuntimeError(f"{d_iso}: non-.BJ bars after 15:00 "
                           f"({n_gt15_non_bj})")
    df = df.filter(~is_bj & ~gt15)
    # 精确重复行 = vendor 复制伪影，剔除并计数；同 (code,tod) 但取值冲突 = 数据缺陷，raise
    n_exact_dup = df.height - df.unique().height
    if n_exact_dup:
        C("exact_duplicate_rows_removed", n_exact_dup)
        df = df.unique()
    n_key_dup = int(df.select(pl.struct("code", "trade_time").is_duplicated()
                              .sum()).item())
    if n_key_dup:
        raise RuntimeError(f"{d_iso}: conflicting duplicate (code, trade_time) "
                           f"rows ({n_key_dup})")
    tods = df["tod"].unique()
    exp_am = int((tods <= "11:30:00").sum())
    exp_pm = int((tods >= "13:00:00").sum())
    C("am_grid_minutes_sum", exp_am)
    C("pm_grid_minutes_sum", exp_pm)
    traded = df.filter(pl.col("vol") > 0)
    C("zerovol_bars_removed", df.height - traded.height)
    am = agg_session(traded, d_iso, "am", pl.col("tod") <= "11:30:00", exp_am)
    pm = agg_session(traded, d_iso, "pm", pl.col("tod") >= "13:00:00", exp_pm)
    C("rows_am", am.height)
    C("rows_pm", pm.height)
    C("partial_rows", int(am["partial"].sum()) + int(pm["partial"].sum()))
    C("codes_day", int(df["code"].n_unique()))
    return pl.concat([am, pm])


def run_scan(day_rows: list[dict], out_dir: Path) -> dict:
    per_year: dict[str, dict] = {}
    parts: dict[int, list[pl.DataFrame]] = {}
    for i, r in enumerate(day_rows):
        d_iso = r["date"]
        year = int(d_iso[:4])
        bars = build_day(RAW / r["path"], d_iso)
        parts.setdefault(year, []).append(bars)
        agg = per_year.setdefault(str(year), {"rows": 0, "symbol_days": set(),
                                              "days": 0})
        agg["rows"] += bars.height
        agg["days"] += 1
        if bars.height:
            agg["symbol_days"].update(
                zip(bars["symbol"].to_list(), bars["trade_date"].to_list()))
        if (i + 1) % 100 == 0 or (i + 1) == len(day_rows):
            el = time.perf_counter() - T0
            log(f"progress {i + 1}/{len(day_rows)} elapsed={el:.0f}s "
                f"({el / (i + 1) * 1000:.0f}ms/day) "
                f"rss={peak_rss_bytes() / 2**30:.2f}GiB")
        nxt = day_rows[i + 1]["date"][:4] if i + 1 < len(day_rows) else None
        if nxt != d_iso[:4]:
            ydf = pl.concat(parts.pop(year)).sort("trade_date", "symbol",
                                                  "session")
            yd = out_dir / f"year={year}"
            yd.mkdir(parents=True, exist_ok=True)
            fp = yd / "bars.parquet"
            ydf.write_parquet(fp, compression="zstd", compression_level=3,
                              statistics=True)
            per_year[str(year)]["rows"] = ydf.height
            per_year[str(year)]["symbols"] = int(ydf["symbol"].n_unique())
            per_year[str(year)]["symbol_days"] = int(ydf.select(
                pl.struct("symbol", "trade_date").n_unique()).item())
            per_year[str(year)]["sha256"] = sha256_of(fp)
            log(f"year {year} flushed: {ydf.height} rows "
                f"rss={peak_rss_bytes() / 2**30:.2f}GiB")
            del ydf
    return {y: {k: v for k, v in d.items() if k != "symbol_days"}
            for y, d in per_year.items()}


def py_aggregate_day(fp: Path, d_iso: str, symbol: str) -> dict:
    """纯 Python 手工聚合（对照用，不走 polars 聚合路径）。
    symbol 形如 'sh.600000'。返回 {'am': {...}, 'pm': {...}}。"""
    code = symbol[3:9] + "." + symbol[0:2].upper()
    rows = pl.read_parquet(fp)
    tod = rows["trade_time"].str.slice(11, 8).to_list()
    codes = rows["code"].to_list()
    o = rows["open"].to_list()
    h = rows["high"].to_list()
    l = rows["low"].to_list()
    c = rows["close"].to_list()
    v = rows["vol"].to_list()
    a = rows["amount"].to_list()
    out: dict[str, dict] = {}
    for sess, lo_ok, hi_ok in (("am", None, "11:30:00"),
                               ("pm", "13:00:00", None)):
        bars = [i for i in range(rows.height)
                if codes[i] == code and (lo_ok is None or tod[i] >= lo_ok)
                and (hi_ok is None or tod[i] <= hi_ok) and v[i] > 0]
        if not bars:
            continue
        bars.sort(key=lambda i: tod[i])
        fen = lambda x: round(float(x) * 100) / 100  # noqa: E731
        out[sess] = {
            "open": fen(o[bars[0]]), "high": max(fen(h[i]) for i in bars),
            "low": min(fen(l[i]) for i in bars), "close": fen(c[bars[-1]]),
            "volume": float(sum(float(v[i]) for i in bars)),
            "amount": float(sum(float(a[i]) for i in bars)),
            "n_minutes": len(bars),
        }
    return out


def smoke_spotcheck(out_dir: Path, smoke_rows: list[dict]) -> dict:
    """冒烟对齐：2 标的 × 2 日，纯 Python 聚合 vs 落盘行，逐值必须精确相等。"""
    checks = []
    for sym, d_iso in (("sh.600000", "2015-06-01"), ("sz.000001", "2015-06-01"),
                       ("sh.600000", "2024-06-03"), ("sz.300750", "2024-06-03")):
        r = next((r for r in smoke_rows if r["date"] == d_iso), None)
        if r is None:
            continue
        want = py_aggregate_day(RAW / r["path"], d_iso, sym)
        day = pl.read_parquet(out_dir / f"year={d_iso[:4]}" / "bars.parquet")
        got = day.filter((pl.col("symbol") == sym)
                         & (pl.col("trade_date") == date.fromisoformat(d_iso)))
        for sess, exp in want.items():
            row = got.filter(pl.col("session") == sess)
            if row.height != 1:
                checks.append({"symbol": sym, "date": d_iso, "session": sess,
                               "match": False, "reason": "row missing"})
                continue
            row = row.row(0, named=True)
            diffs = {k: (row[k], expv) for k, expv in exp.items()
                     if row[k] != expv}
            checks.append({"symbol": sym, "date": d_iso, "session": sess,
                           "match": not diffs, "diffs": diffs})
    bad = [c for c in checks if not c["match"]]
    if bad:
        raise RuntimeError(f"smoke spot check mismatches: {bad}")
    return {"n_checks": len(checks), "all_exact": True, "detail": checks}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    if args.smoke == args.full:
        raise SystemExit("choose exactly one of --smoke / --full")
    (RUN / "logs").mkdir(exist_ok=True)
    (RUN / "tmp").mkdir(exist_ok=True)

    day_rows = load_day_list()
    identity = verify_identities(day_rows)
    log("identity fail-closed checks passed")

    if args.smoke:
        smoke_rows = [r for r in day_rows
                      if r["date"][:7] in SMOKE_MONTHS]
        if not smoke_rows:
            raise RuntimeError("smoke day set empty")
        out_dir = RUN / "tmp" / "smoke_out"
    else:
        smoke_rows = day_rows
        out_dir = OUT_DIR
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if out_dir.exists():
        for p in sorted(out_dir.glob("year=*"), reverse=True):
            for f in p.iterdir():
                f.unlink()
            p.rmdir()
    out_dir.mkdir(parents=True, exist_ok=True)

    scan_start = time.perf_counter()
    per_year = run_scan(smoke_rows, out_dir)
    scan_s = time.perf_counter() - scan_start
    elapsed = time.perf_counter() - T0
    peak = peak_rss_bytes()
    summary = {
        "mode": "smoke" if args.smoke else "full",
        "days": len(smoke_rows),
        "out_dir": str(out_dir.relative_to(REPO)),
        "counters": cnt,
        "per_year": per_year,
        "identity": identity,
        "timing": {"total_s": round(elapsed, 1), "scan_s": round(scan_s, 1),
                   "mean_ms_per_day": scan_s / len(smoke_rows) * 1000,
                   "peak_rss_gib": round(peak / 2**30, 2)},
        "environment": {"python": sys.version.split()[0],
                        "polars": pl.__version__, "platform": "win32"},
    }
    suffix = "smoke" if args.smoke else "full"
    (RUN / "logs" / f"scan_summary_{suffix}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    log(f"scan done: {sum(d['rows'] for d in per_year.values())} rows "
        f"elapsed={elapsed:.0f}s peak={peak / 2**30:.2f}GiB")

    if args.smoke:
        spot = smoke_spotcheck(out_dir, smoke_rows)
        summary["spot_check"] = spot
        (RUN / "logs" / "smoke.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        log("smoke spot check: all exact")


if __name__ == "__main__":
    main()
