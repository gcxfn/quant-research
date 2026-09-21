# F0 factor-inputs audit -- main-conversation takeover (descriptive only, zero trials)
# Scans tushare/ (fundamentals, events, funds, index) + xiaodefa/ (price-derived dailies).
import csv, glob, io, json, os, sys, time
import datetime as dt
import polars as pl

ROOT = r"D:\量化"
OUT = os.path.join(ROOT, "artifacts", "runs", "20260919T170000-f0-factor-inputs-main", "outputs")
os.makedirs(OUT, exist_ok=True)
t0 = time.time()

DEV = (20150105, 20201231)
VAL = (20210101, 20241231)

def read_csv_any(path, **kw):
    try:
        return pl.read_csv(path, infer_schema_length=100, **kw)
    except Exception:
        return pl.DataFrame()

def date_range_of(df, col):
    s = df[col].cast(pl.Int64, strict=False).drop_nulls()
    return (int(s.min()), int(s.max())) if s.len() else (None, None)

def in_win(df, col, lo, hi):
    return df.filter((pl.col(col).cast(pl.Int64, strict=False) >= lo)
                     & (pl.col(col).cast(pl.Int64, strict=False) <= hi))

results = []

def audit_daily_dir(base, name, family, batch_glob="*"):
    """daily-frequency dataset: chunks by trade date (chunk_YYYYMMDD.csv) or per-symbol."""
    paths = sorted(glob.glob(os.path.join(base, "**", "chunk_*.csv"), recursive=True))
    if not paths:
        results.append({"dataset": name, "dir": base, "family": family, "status": "NO_CHUNKS"})
        return
    # date-coded chunks: chunk_YYYYMMDD
    dates = []
    for p in paths:
        b = os.path.basename(p)
        try:
            dates.append(int(b[6:14]))
        except ValueError:
            dates = []
            break
    if dates:
        dates.sort()
        d0, d1 = dates[0], dates[-1]
        dev = sum(1 for d in dates if DEV[0] <= d <= DEV[1])
        val = sum(1 for d in dates if VAL[0] <= d <= VAL[1])
        fut = sum(1 for d in dates if d >= 20250101)
        # sample 3 chunks: first dev, last dev, last val for symbols/rows/pit
        smp = [dates[0], dates[len(dates)//2], dates[-1]]
        syms, cols = set(), None
        nrows = 0
        for d in smp:
            p = os.path.join(base, find_batch(base, d))
            if p:
                df = read_csv_any(p)
                cols = df.columns
                if "ts_code" in df.columns:
                    syms.update(df["ts_code"].unique().to_list())
                nrows += df.height
        pit = [c for c in (cols or []) if c in ("ann_date", "disclosure_date", "ann_datetime", "update_flag")]
        results.append({"dataset": name, "dir": base, "family": family,
                        "shape": "date_chunks", "n_chunks": len(paths),
                        "date_first": d0, "date_last": d1,
                        "dev_days": dev, "val_days": val, "days_2025plus": fut,
                        "sample_cols": (cols or [])[:14], "pit_fields": pit,
                        "sample_symbols": len(syms)})
    else:
        # per-symbol chunks: sample up to 40
        import random
        random.seed(0)
        smp = paths if len(paths) <= 40 else random.sample(paths, 40)
        sym_dates, cols, syms = [], set((None,)), None
        first = df0 = None
        for p in smp:
            df = read_csv_any(p)
            if first is None:
                first, df0 = p, df
                cols = df.columns
            dc = "end_date" if "end_date" in df.columns else ("trade_date" if "trade_date" in df.columns else ("ann_date" if "ann_date" in df.columns else None))
            if dc:
                sym_dates.append(date_range_of(df, dc))
        pit = [c for c in (cols or []) if c in ("ann_date", "disclosure_date", "update_flag")]
        lo = min((x[0] for x in sym_dates if x[0]), default=None)
        hi = max((x[1] for x in sym_dates if x[1]), default=None)
        results.append({"dataset": name, "dir": base, "family": family,
                        "shape": "per_symbol_chunks", "n_chunks": len(paths),
                        "sampled": len(smp), "sample_date_first": lo, "sample_date_last": hi,
                        "sample_cols": (cols or [])[:16], "pit_fields": pit})

def find_batch(base, d):
    for sub in sorted(os.listdir(base)):
        cand = os.path.join(base, sub, f"chunk_{d}.csv")
        if os.path.exists(cand):
            return os.path.join(sub, f"chunk_{d}.csv")
    return None

TS = os.path.join(ROOT, "data", "raw", "tushare")
XD = os.path.join(ROOT, "data", "raw", "xiaodefa")

plan_ts = [
    ("daily_basic", "估值/日频指标"), ("stk_limit", "涨跌停"), ("margin_detail", "资金面/两融"),
    ("top_list", "资金面/龙虎榜"), ("top_inst", "资金面/龙虎榜"), ("dividend", "公告事件/分红"),
    ("forecast", "公告事件/业绩预告"), ("express", "公告事件/快报"), ("repurchase", "公告事件/回购"),
    ("stk_holdertrade", "公告事件/增减持"), ("share_float", "公告事件/解禁"),
    ("income", "财务/利润表"), ("balancesheet", "财务/资产负债表"), ("cashflow", "财务/现金流"),
    ("fina_indicator", "财务/指标"), ("disclosure_date", "PIT/披露日期"),
    ("index_member_all", "行业/成分"), ("stock_basic", "参考"), ("trade_cal", "参考"),
    ("index_daily", "行业/指数"), ("sw_index_daily", "行业/指数"), ("sw_index_daily_l2", "行业/指数"),
]
plan_xd = [
    ("adj_factor", "量价/复权"), ("suspend_d", "量价/停复牌"), ("stk_auction_c", "微观/竞价"),
    ("stk_auction_o", "微观/竞价"), ("moneyflow", "微观/资金流"), ("cyq_perf", "微观/筹码"),
    ("stk_nineturn", "微观/九转"), ("idx_factor_pro", "量价/指数因子"), ("ths_daily", "行业/同花顺"),
    ("dc_daily", "行业/东财"), ("ci_daily", "行业/中证"), ("sw_daily", "行业/申万"),
    ("hk_hold", "资金面/港股通"), ("ccass_hold", "资金面/港股通"), ("ggt_daily", "资金面/港股通"),
    ("limit_list_d", "涨跌停/清单"), ("daily_info", "参考/日信息"),
]
for name, fam in plan_ts:
    audit_daily_dir(os.path.join(TS, name), "tushare/" + name, fam)
for name, fam in plan_xd:
    audit_daily_dir(os.path.join(XD, name), "xiaodefa/" + name, fam)

# --- seam checks -------------------------------------------------------------
seams = {}
# daily_basic r1/r2: find batch dirs
db_base = os.path.join(TS, "daily_basic")
batches = sorted(os.listdir(db_base))
seams["daily_basic_batches"] = batches
# overlap row: read last day of earlier batch and first days of later
if len(batches) >= 2:
    b1, b2 = batches[0], batches[1]
    c1 = sorted(glob.glob(os.path.join(db_base, b1, "chunk_*.csv")))
    c2 = sorted(glob.glob(os.path.join(db_base, b2, "chunk_*.csv")))
    d1l = os.path.basename(c1[-1])[6:14] if c1 else None
    d2f = os.path.basename(c2[0])[6:14] if c2 else None
    n1 = read_csv_any(c1[-1]) if c1 else None
    n2 = read_csv_any(c2[0]) if c2 else None
    seams["daily_basic_seam"] = {
        "b1_last": d1l, "b2_first": d2f, "gap_or_overlap": None,
        "b1_last_rows": n1.height if n1 is not None else None,
        "b2_first_rows": n2.height if n2 is not None else None,
        "b1_last_ts": int(str(n1["trade_date"][0])) if n1 is not None else None,
        "b2_first_ts": int(str(n2["trade_date"][0])) if n2 is not None else None,
        "cols_equal": (n1.columns == n2.columns) if (n1 is not None and n2 is not None) else None,
    }
    if d1l and d2f:
        seams["daily_basic_seam"]["gap_or_overlap"] = int(d2f) - int(d1l)
# cyq_perf missing chunks vs adj_factor
af_days = set(int(os.path.basename(p)[6:14]) for p in glob.glob(os.path.join(XD, "adj_factor", "**", "chunk_*.csv"), recursive=True))
for ds in ("cyq_perf", "ci_daily", "sw_daily", "stk_auction_o", "moneyflow"):
    dd = set(int(os.path.basename(p)[6:14]) for p in glob.glob(os.path.join(XD, ds, "**", "chunk_*.csv"), recursive=True))
    if dd or ds == "cyq_perf":
        miss = sorted(af_days - dd)
        seams[f"{ds}_vs_adj_factor"] = {"adj_days": len(af_days), "this_days": len(dd),
                                        "missing_vs_adj": len(miss), "missing_sample": miss[:5]}
# margin_detail start
mg = sorted(glob.glob(os.path.join(TS, "margin_detail", "**", "chunk_*.csv"), recursive=True))
if mg:
    seams["margin_detail_first_day"] = os.path.basename(mg[0])[6:14]
    seams["margin_detail_last_day"] = os.path.basename(mg[-1])[6:14]

# --- cross-check vs v0 baostock panel ---------------------------------------
PROC = os.path.join(ROOT, "data", "processed", "baostock-daily-20260917")
xchk = {"panel_dir": PROC, "files": sorted(os.listdir(PROC))[:12]}
pp = None
for f in os.listdir(PROC):
    if f.endswith(".parquet"):
        pp = os.path.join(PROC, f)
        break
if pp:
    pan = pl.read_parquet(pp)
    xchk["panel_cols"] = pan.columns
    xchk["panel_rows"] = pan.height
    xchk["panel_symbols"] = pan["symbol"].n_unique() if "symbol" in pan.columns else None
# adj_factor vs panel adjusted close ratio consistency on 3 symbols x 3 dates
if pp and "symbol" in pan.columns:
    afmap = {}
    for p in glob.glob(os.path.join(XD, "adj_factor", "**", "chunk_*.csv"), recursive=True)[:4000]:
        pass  # too slow to load all here; sample via find_batch for chosen dates
    checks = []
    test_syms = [("sh.600519", "600519.SH"), ("sz.000001", "000001.SZ"), ("sh.601318", "601318.SH")]
    test_dates = [20150506, 20180702, 20201231]
    for bsym, tsym in test_syms:
        for d in test_dates:
            fn = find_batch(os.path.join(XD, "adj_factor"), d)
            if not fn:
                continue
            df = read_csv_any(os.path.join(XD, "adj_factor", fn))
            row = df.filter(pl.col("ts_code") == tsym)
            if row.height == 0:
                continue
            af = float(row["adj_factor"][0])
            prow = pan.filter((pl.col("symbol") == bsym) & (pl.col("date") == dt.date(d // 10000, d // 100 % 100, d % 100)))
            if prow.height == 0:
                continue
            checks.append({"symbol": bsym, "date": d, "adj_factor": af,
                           "panel_close": float(prow["close"][0]),
                           "panel_cols_present": [c for c in ("close", "adj_close", "adjusted_close") if c in pan.columns]})
    xchk["adj_factor_vs_panel_samples"] = checks

# --- skeleton review ---------------------------------------------------------
sk = {}
for f in ("core.py", "cache.py", "signals.py"):
    p = os.path.join(ROOT, "src", "quant", "factors", f)
    src = io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    sk[f] = {"lines": src.count("\n"), "chars": len(src),
             "defs": [l.split("(")[0].replace("def ", "") for l in src.splitlines() if l.strip().startswith("def ")][:20],
             "classes": [l.split(":")[0].replace("class ", "") for l in src.splitlines() if l.strip().startswith("class ")][:10]}

out = {"datasets": results, "seams": seams, "cross_check": xchk, "skeleton": sk,
       "elapsed_s": round(time.time() - t0, 1)}
_rows = [{k: (json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v) for k, v in r.items()} for r in results]
pl.DataFrame(_rows).write_csv(os.path.join(OUT, "factor_inputs_scan.csv"))
io.open(os.path.join(OUT, "f0_scan.json"), "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps({k: out[k] for k in ("seams",)}, ensure_ascii=False, indent=1)[:2000])
print("elapsed", out["elapsed_s"], "s; datasets scanned:", len(results))
print("cross:", json.dumps(xchk.get("adj_factor_vs_panel_samples", []), ensure_ascii=False)[:600])
print("skeleton:", json.dumps(sk, ensure_ascii=False)[:800])
