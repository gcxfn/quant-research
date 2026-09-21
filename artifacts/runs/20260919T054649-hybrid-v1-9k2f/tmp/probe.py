# -*- coding: utf-8 -*-
"""Hybrid v1 pre-run data probe: panel/factors/dividends/rotation paths."""
import sys, json
from datetime import date
from pathlib import Path
ROOT = Path(r"D:\量化")
sys.path.insert(0, str(ROOT / "src"))
import polars as pl
import numpy as np

MEMBERS = ["sh.511010","sh.518880","sh.510050","sh.510300","sz.159915",
           "sh.510880","sh.513100","sh.513500"]
DEV_START, DEV_END = date(2015,1,5), date(2020,12,31)

etf = pl.read_parquet(ROOT/"data/processed/etf-daily-20260919/daily_2015_2024.parquet")
print("etf panel rows:", etf.height, "cols:", etf.columns)
print("etf dtypes:", {c: str(etf.schema[c]) for c in etf.columns})
e8 = etf.filter(pl.col("symbol").is_in(MEMBERS)).filter(
    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
print("member-dev rows:", e8.height, "per symbol:", 
      e8.group_by("symbol").len().sort("symbol").to_dicts())
print("preclose nulls:", e8.filter(pl.col("preclose").is_null()).height)
print("duplicate (symbol,date):", e8.height - e8.unique(["symbol","date"]).height)
print("date span:", e8["date"].min(), "..", e8["date"].max())

# SSE calendar dev segment
cal = pl.read_csv(ROOT/"data/raw/xiaodefa/trade_cal/20260913-bulk1/chunk_exchange-SSE_start_date-20140101_end_date-20261231.csv")
cal = cal.filter((pl.col("is_open")==1) & (pl.col("cal_date")>=20150105) & (pl.col("cal_date")<=20201231))
sse_days = set(cal["cal_date"].to_list())
panel_days = set(e8["date"].dt.year().cast(pl.Int64).mul(10000).add(e8["date"].dt.month().cast(pl.Int64).mul(100)).add(e8["date"].dt.day().cast(pl.Int64)).to_list())
print("assert iii: sse days", len(sse_days), "panel days", len(panel_days),
      "sse-panel", sorted(sse_days-panel_days)[:5], "panel-sse", sorted(panel_days-sse_days)[:5])

# adj factors for members
facs = {}
for m in MEMBERS:
    code = m.split(".")[1] + "." + m.split(".")[0].upper()
    p = ROOT/"data/raw/tushare/fund_adj/20260917-r1"/f"chunk_{code}.csv"
    f = pl.read_csv(p, schema_overrides={"trade_date": pl.Int64})
    f = f.filter((pl.col("trade_date")//10000).cast(pl.String).str.to_date("%Y%m%d").is_between(DEV_START, DEV_END))
    facs[m] = f.sort("trade_date")
    print(m, "factor rows dev:", f.height, "first/last:", f["trade_date"].min(), f["trade_date"].max())

# dividend candidates from preclose_mismatch_detail
det = pl.read_csv(ROOT/"data/processed/etf-daily-20260919/preclose_mismatch_detail.csv")
print("mismatch detail cols:", det.columns)
d8 = det.filter(pl.col("symbol").is_in(MEMBERS))
d8 = d8.filter((pl.col("date") >= date(2015,1,5)) & (pl.col("date") <= date(2020,12,31))) if d8.schema["date"] == pl.Date else d8
print("member mismatch rows dev:", d8.height, d8.schema["date"])
events = []
for r in d8.iter_rows(named=True):
    m = r["symbol"]; f = facs[m]
    dint = r["date"].year*10000 + r["date"].month*100 + r["date"].day
    idx = np.searchsorted(f["trade_date"].to_numpy(), dint)
    if idx == 0 or idx >= f.height or f["trade_date"][idx] != dint:
        print("  no factor row for", m, r["date"]); continue
    if idx == 0: continue
    ratio = float(f["adj_factor"][idx]) / float(f["adj_factor"][idx-1])
    if (r["preclose"] < r["prev_close"]) and (1.0 < ratio <= 1.06):
        events.append({"symbol": m, "date": r["date"], "div": r["prev_close"]-r["preclose"], "ratio": ratio,
                       "csv_ratio": r["factor_ratio"]})
print("events:", len(events))
for e in events: print("  ", e)
from collections import Counter
print(Counter(e["symbol"] for e in events))

# momentum: month-end sessions from stock calendar
from quant.research import p2r16_trend_dispersion as r16
calS = r16.market_calendar(ROOT/"data/processed/baostock-daily-20260917/daily_1999_2024.parquet")
mes = r16.month_end_sessions(calS).filter((pl.col("s")>=DEV_START)&(pl.col("s")<=DEV_END))
sig_days_dev = mes["s"].to_list()
print("month-end sessions:", len(sig_days_dev), sig_days_dev[:3], sig_days_dev[-2:])
me_list = sig_days_dev
adj = {}
for m in MEMBERS:
    f = facs[m]
    sub = e8.filter(pl.col("symbol")==m).select("date","close").sort("date")
    fmap = dict(zip(f["trade_date"].to_list(), f["adj_factor"].to_list()))
    rows = sub.with_columns((pl.col("date").dt.year()*10000+pl.col("date").dt.month()*100+pl.col("date").dt.day()).alias("dint"))
    ac = {}
    for r in rows.iter_rows(named=True):
        af = fmap.get(r["dint"])
        if af is None:
            # carry forward last factor
            ks = [k for k in fmap if k < r["dint"]]
            af = fmap[max(ks)] if ks else None
        ac[r["dint"]] = r["close"]*af
    adj[m] = ac
def me_dint(d): return d.year*10000+d.month*100+d.day
def month_shift(d, k):
    y, mo = d.year, d.month - k
    while mo <= 0: mo += 12; y -= 1
    cands = [x for x in me_list if (x.year, x.month) == (y, mo)]
    return cands[0] if cands else None
for lb in (6, 3):
    print(f"--- lookback {lb}m ranking (top-N each month) ---")
    for i, T in enumerate(me_list):
        T0 = month_shift(T, lb)
        if T0 is None:
            continue
        scores = {}
        ok = True
        for m in MEMBERS:
            a0, a1 = adj[m].get(me_dint(T0)), adj[m].get(me_dint(T))
            if a0 is None or a1 is None: ok = False; break
            scores[m] = a1/a0 - 1.0
        if not ok: continue
        ranked = sorted(scores, key=lambda m: (-scores[m], m))
        print(T, "top4:", [(m, round(scores[m]*100,1)) for m in ranked[:4]], "top2:", ranked[:2])
