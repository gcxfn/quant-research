# -*- coding: utf-8 -*-
"""P2-R6 复核 项4 补充2：对全部 116 只窗内退市白名单 ETF 复算入池情况，
辨识文档"7 只 / 88 池行"的口径。只读。
"""
import json
from datetime import date
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
print("whitelist:", len(wl))

def parse_d(s):
    return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if s and len(s) == 8 else None

# 窗内退市 = delist_date 在 2015-01-05..2024-12-31
INW = {}
for r in wl:
    dd = parse_d(r["delist_date"])
    if dd and date(2015, 1, 5) <= dd <= date(2024, 12, 31):
        INW[r["ts_code"]] = r
print("窗内退市白名单:", len(INW), "(run 报 116)")

def u2_ok(r):
    return r["fund_type"] in ("股票型", "其他") and not any(k in (r["name"] or "") for k in QDII)

amt_cache = {}
def amounts(code):
    if code not in amt_cache:
        a = pl.read_csv(DAILY / f"chunk_{code}.csv", columns=["trade_date", "amount"], infer_schema_length=0)
        amt_cache[code] = dict(zip(a["trade_date"].to_list(), a["amount"].cast(pl.Float64).to_list()))
    return amt_cache[code]

def qualifies(code, tstr, liq=True):
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
    if liq:
        last20 = [d for d in dates if d <= tstr][-20:]
        am = amounts(code)
        xs = sorted(am[d] for d in last20)
        med = xs[len(xs)//2] if len(xs) % 2 else (xs[len(xs)//2 - 1] + xs[len(xs)//2]) / 2
        if med < 50000:
            return False
    return True

days_all = [d for d in calendar if "20150105" <= d <= "20241231"]
res_full, res_nolq = [], []
for code in INW:
    q = [d for d in days_all if qualifies(code, d, liq=True)]
    if q:
        res_full.append((code, len(q), q[0], q[-1]))
    qn = [d for d in days_all if qualifies(code, d, liq=False)]
    if qn:
        res_nolq.append((code, len(qn), qn[0], qn[-1]))

print("\n[U3 全条(含流动性)] 入池的窗内退市 ETF:")
for code, n, d0, d1 in sorted(res_full, key=lambda x: -x[1]):
    print(f"  {code} {INW[code]['name'][:18]:18s} 池行={n:4d} 首={d0} 末={d1}")
print("合计代码:", len(res_full), "合计池行:", sum(x[1] for x in res_full))

print("\n[不含流动性门槛] (仅注册表+历史门槛):")
tot = 0
for code, n, d0, d1 in sorted(res_nolq, key=lambda x: -x[1]):
    tot += n
    print(f"  {code} {INW[code]['name'][:18]:18s} 行={n:5d} 首={d0} 末={d1}")
print("合计代码:", len(res_nolq), "合计行:", tot)
