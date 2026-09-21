# -*- coding: utf-8 -*-
"""P2-R6 复核 项4 v2：池规模与 U3 门槛独立重建（依 prereg §2.3 原文实现，不读策略代码）。
白名单=U1×行情覆盖×因子覆盖（run 口径 1168）；U2 品类过滤在信号日成员判定时施加。
只读。
"""
import json
from datetime import date
from pathlib import Path
import polars as pl

RUN = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"
DAILY = Path("data/raw/tushare/fund_daily/20260917-r1")
ADJDIR = Path("data/raw/tushare/fund_adj/20260917-r1")
m = json.load(open(f"{RUN}/metrics.json", encoding="utf-8"))
cfg = json.load(open("configs/experiments/p2r6-etf-rotation.json", encoding="utf-8"))
QDII = set(cfg["universe"]["u2_qdii_keywords_frozen"])

fb = pl.read_csv("data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv", infer_schema_length=0)

def u1_pass(code, name, market):
    if market != "E":
        return False
    num = code.split(".")[0]
    if code.endswith(".SZ"):
        return num[:3] in ("158", "159") or "ETF" in (name or "")
    if code.endswith(".SH"):
        return num[:2] in ("51", "52", "53", "55", "56", "58") or "ETF" in (name or "")
    return False

u1 = fb.filter(pl.struct(["ts_code", "name", "market"]).map_elements(
    lambda r: u1_pass(r["ts_code"], r["name"], r["market"]), return_dtype=pl.Boolean))
print("U1 registry pass:", u1.height, "(run 1873)")

files = sorted(DAILY.glob("chunk_*.csv"))
print("daily files:", len(files))
codes_cov, frames = [], []
for f in files:
    code = f.stem[len("chunk_"):]
    codes_cov.append(code)
    frames.append(pl.read_csv(f, columns=["trade_date"], infer_schema_length=0).with_columns(pl.lit(code).alias("code")))
allq = pl.concat(frames)
calendar = sorted(allq["trade_date"].unique().to_list())
cal_idx = {d: i for i, d in enumerate(calendar)}
per_code_dates = {}
for c, g in allq.group_by("code"):
    key = c[0] if isinstance(c, tuple) else c
    per_code_dates[key] = sorted(g["trade_date"].to_list())
print("calendar:", calendar[0], "->", calendar[-1], len(calendar), "sessions; covered codes:", len(codes_cov))

adj_cov = set()
for f in ADJDIR.glob("chunk_*.csv"):
    try:
        if pl.scan_csv(f).select(pl.len()).collect().item() > 0:
            adj_cov.add(f.stem[len("chunk_"):])
    except Exception:
        pass
wl_rows = [r for r in u1.iter_rows(named=True) if r["ts_code"] in per_code_dates and r["ts_code"] in adj_cov]
print("whitelist U1×daily×adj:", len(wl_rows), "(run 1168)")

# 预载 amount（千元）
amt_map = {}
for code in per_code_dates:
    a = pl.read_csv(DAILY / f"chunk_{code}.csv", columns=["trade_date", "amount"], infer_schema_length=0)
    amt_map[code] = dict(zip(a["trade_date"].to_list(), a["amount"].cast(pl.Float64).to_list()))

def parse_d(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if s and len(s) == 8 else None

LD = {r["ts_code"]: parse_d(r["list_date"]) for r in wl_rows}
DD = {r["ts_code"]: parse_d(r["delist_date"]) for r in wl_rows}
LD_IDX = {}
for c in per_code_dates:
    ld = LD.get(c)
    LD_IDX[c] = next((i for i, d in enumerate(calendar) if d >= ld.strftime("%Y%m%d")), None) if ld else None

def u2_ok(r):
    return r["fund_type"] in ("股票型", "其他") and not any(k in (r["name"] or "") for k in QDII)

def pool_at(tstr):
    t = date(int(tstr[:4]), int(tstr[4:6]), int(tstr[6:8]))
    tidx = cal_idx[tstr]
    out = {}
    for r in wl_rows:
        code = r["ts_code"]
        if not u2_ok(r):
            continue
        dates = per_code_dates[code]
        if tstr not in set(dates):
            continue
        n_hist = sum(1 for d in dates if d <= tstr)
        if n_hist < 120:
            continue
        li = LD_IDX[code]
        if li is None or li > tidx - 120:
            continue
        dd = DD[code]
        if dd is not None and dd <= t:
            continue
        last20 = [d for d in dates if d <= tstr][-20:]
        amts = sorted(amt_map[code][d] for d in last20)
        med = amts[len(amts)//2] if len(amts) % 2 else (amts[len(amts)//2 - 1] + amts[len(amts)//2]) / 2
        if med < 50000:
            continue
        out[code] = dict(med=med, name=r["name"], fund_type=r["fund_type"],
                         list_date=r["list_date"], delist_date=r["delist_date"], n_hist=n_hist)
    return out

# --- metrics pool_sizes vs 文档 ---
DOC_POOL = {"2016": (6, 7.3, 9), "2017": (6, 6.7, 9), "2018": (8, 11.1, 17), "2019": (16, 22.7, 28),
            "2020": (34, 45.7, 60), "2021": (52, 69.9, 87), "2022": (90, 99.8, 113),
            "2023": (105, 122.8, 145), "2024": (88, 128.8, 206)}
print("\n[池规模] metrics vs 文档 §5（月频 min/mean/max）:")
pm = []
for y in map(str, range(2016, 2025)):
    p = m["pool_sizes"]["monthly"][y]
    d = DOC_POOL[y]
    ok = abs(p["min"]-d[0]) < 0.5 and abs(p["mean"]-d[1]) < 0.05 and abs(p["max"]-d[2]) < 0.5
    if not ok:
        pm.append((y, p["min"], p["mean"], p["max"], d))
    print(f"  {y}: metrics {p['min']}/{p['mean']:.1f}/{p['max']} vs doc {d[0]}/{d[1]}/{d[2]} {'OK' if ok else '<-- DIFF'}")
print("  不一致年:", pm if pm else "无")

# --- 两个抽验信号日 ---
for day, idx_note in [("2016-12-30", 11), ("2019-12-31", 11)]:
    tstr = day.replace("-", "")
    p = pool_at(tstr)
    run_n = m["pool_sizes"]["monthly"][day[:4]]["sizes"][idx_note]
    print(f"\n[{day}] 我方重建合格池 n={len(p)}；run sizes 第12个月频信号日={run_n}  {'一致' if len(p)==run_n else '<-- 不一致'}")
    for code in sorted(p):
        r = p[code]
        print(f"  {code} {r['name'][:16]:16s} {r['fund_type']:3s} med20={r['med']:11.1f}千元 list={r['list_date']} delist={r['delist_date'] or '-'} hist={r['n_hist']}")
    print("  U3 各条: 全部 med>=50000:", all(r["med"] >= 50000 for r in p.values()),
          "| 全部 hist>=120:", all(r["n_hist"] >= 120 for r in p.values()))

# --- 7 只窗内退市 ETF 入池复核（月频信号日）---
DOC7 = ["159911.SZ", "159962.SZ", "510260.SH", "510420.SH", "510430.SH", "510610.SH", "510620.SH"]
last_of_month = {}
for d in calendar:
    last_of_month[d[:6]] = d
monthly_days = sorted(v for v in last_of_month.values() if "2016" <= v[:4] <= "2024")
print("\n月频信号日(2016-2024):", len(monthly_days))
wl_map = {r["ts_code"]: r for r in wl_rows}
total = 0
for code in DOC7:
    if code not in wl_map:
        print(f"  {code}: 不在白名单!"); continue
    r = wl_map[code]
    dates = per_code_dates[code]
    dset = set(dates)
    ok = []
    for tstr in monthly_days:
        if tstr not in dset or not u2_ok(r):
            continue
        t = date(int(tstr[:4]), int(tstr[4:6]), int(tstr[6:8]))
        tidx = cal_idx[tstr]
        n_hist = sum(1 for d in dates if d <= tstr)
        li = LD_IDX[code]
        if n_hist < 120 or li is None or li > tidx - 120:
            continue
        dd = DD[code]
        if dd is not None and dd <= t:
            continue
        last20 = [d for d in dates if d <= tstr][-20:]
        amts = sorted(amt_map[code][d] for d in last20)
        med = amts[len(amts)//2] if len(amts) % 2 else (amts[len(amts)//2 - 1] + amts[len(amts)//2]) / 2
        if med < 50000:
            continue
        ok.append(tstr)
    total += len(ok)
    print(f"  {code} {r['name'][:18]:18s} delist={r['delist_date'] or '(D,delist空)'}: 合格 {len(ok)} 信号日"
          + (f", 最后合格日={ok[-1]}" if ok else ""))
print("7 只合计池行(月频):", total, "(文档 88；文档另称 159962.SZ 最后合格日 2020-12-02)")
