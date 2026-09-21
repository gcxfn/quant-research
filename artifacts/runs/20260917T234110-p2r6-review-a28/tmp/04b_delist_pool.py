# -*- coding: utf-8 -*-
"""P2-R6 复核 项4 补充：7 只窗内退市 ETF 的入池口径辨析——按"日频池"与"周频信号日池"分别复算，
核对文档"88 个池行、159962.SZ 最后合格日 2020-12-02"。只读。
"""
import json
from datetime import date, timedelta
from pathlib import Path
import polars as pl

DAILY = Path("data/raw/tushare/fund_daily/20260917-r1")
ADJDIR = Path("data/raw/tushare/fund_adj/20260917-r1")
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

files = sorted(DAILY.glob("chunk_*.csv"))
frames = []
for f in files:
    code = f.stem[len("chunk_"):]
    frames.append(pl.read_csv(f, columns=["trade_date"], infer_schema_length=0).with_columns(pl.lit(code).alias("code")))
allq = pl.concat(frames)
calendar = sorted(allq["trade_date"].unique().to_list())
cal_idx = {d: i for i, d in enumerate(calendar)}
per_code_dates = {}
for c, g in allq.group_by("code"):
    key = c[0] if isinstance(c, tuple) else c
    per_code_dates[key] = sorted(g["trade_date"].to_list())

adj_cov = set()
for f in ADJDIR.glob("chunk_*.csv"):
    try:
        if pl.scan_csv(f).select(pl.len()).collect().item() > 0:
            adj_cov.add(f.stem[len("chunk_"):])
    except Exception:
        pass

wl = [r for r in u1.iter_rows(named=True) if r["ts_code"] in per_code_dates and r["ts_code"] in adj_cov]
wl_map = {r["ts_code"]: r for r in wl}

amt_map = {}
for code in per_code_dates:
    a = pl.read_csv(DAILY / f"chunk_{code}.csv", columns=["trade_date", "amount"], infer_schema_length=0)
    amt_map[code] = dict(zip(a["trade_date"].to_list(), a["amount"].cast(pl.Float64).to_list()))

def parse_d(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if s and len(s) == 8 else None

def u2_ok(r):
    return r["fund_type"] in ("股票型", "其他") and not any(k in (r["name"] or "") for k in QDII)

def qualifies(code, tstr):
    r = wl_map[code]
    if not u2_ok(r):
        return False
    dates = per_code_dates[code]
    if tstr not in set(dates):
        return False
    n_hist = sum(1 for d in dates if d <= tstr)
    if n_hist < 120:
        return False
    ld = parse_d(r["list_date"])
    if ld is None:
        return False
    li = next((i for i, d in enumerate(calendar) if d >= ld.strftime("%Y%m%d")), None)
    if li is None or li > cal_idx[tstr] - 120:
        return False
    dd = parse_d(r["delist_date"])
    t = date(int(tstr[:4]), int(tstr[4:6]), int(tstr[6:8]))
    if dd is not None and dd <= t:
        return False
    last20 = [d for d in dates if d <= tstr][-20:]
    amts = sorted(amt_map[code][d] for d in last20)
    med = amts[len(amts)//2] if len(amts) % 2 else (amts[len(amts)//2 - 1] + amts[len(amts)//2]) / 2
    return med >= 50000

DOC7 = ["159911.SZ", "159962.SZ", "510260.SH", "510420.SH", "510430.SH", "510610.SH", "510620.SH"]
days_2016_2024 = [d for d in calendar if "20160101" <= d <= "20241231"]

# 周频信号日 = 每周最后一个交易日（按日历周分组取最大）
last_of_week = {}
for d in days_2016_2024:
    dt = date(int(d[:4]), int(d[4:6]), int(d[6:8]))
    yw = dt.strftime("%G-W%V")
    if yw not in last_of_week or d > last_of_week[yw]:
        last_of_week[yw] = d
weekly_days = sorted(last_of_week.values())
monthly_days = sorted({d[:6]: d for d in days_2016_2024}.values())
print("信号日数: 周频", len(weekly_days), "月频", len(monthly_days), "全部交易日", len(days_2016_2024))

ws, ms, ds_ = {}, {}, {}
for code in DOC7:
    q = [d for d in days_2016_2024 if qualifies(code, d)]
    qset = set(q)
    w = [d for d in weekly_days if d in qset]
    mo = [d for d in monthly_days if d in qset]
    ws[code], ms[code], ds_[code] = w, mo, q
    print(f"{code} delist={wl_map[code]['delist_date'] or '(空)'}: 日频池行={len(q)} 周频信号日={len(w)} 月频信号日={len(mo)}"
          + (f" 日频最后={q[-1]}" if q else ""))

print("\n合计: 日频", sum(len(v) for v in ds_.values()), "| 周频", sum(len(v) for v in ws.values()),
      "| 月频", sum(len(v) for v in ms.values()), "| 月+周", sum(len(v) for v in ms.values()) + sum(len(v) for v in ws.values()))
print("\n159962.SZ 日频合格日(全部):", ds_["159962.SZ"])
print("159962.SZ 月频合格日:", ms["159962.SZ"])
print("文档口径核对: 88 个池行 & 最后合格日 2020-12-02")
