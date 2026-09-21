#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主对话独立验收：归因三段自写重算（前向收益/贡献聚合/统计）。

独立性边界：z 标准化与 rank 池沿共享库 r16 + F2R1 分数（仓库纪律：信号定义
单一来源，复用非缺陷，且该段已被 FA-S2 门对 F3R1 composite 逐位验证覆盖）。
本脚本独立实现 r 前向收益、c_i,t 聚合、t/分年统计三段，交叉验证
attribution_ew.csv 的判定相关数字。
"""
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import polars as pl

from quant.research import p2r16_trend_dispersion as r16

CHASSIS = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F2R1 = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
RUN = ROOT / "artifacts/runs/20260920T104102-factor-attrib-3ff0"
FAM = {"A": "A_price", "B": "B_value", "C": "C_micro", "D": "D_fund",
       "E": "E_event", "F": "F_xsec"}
DEV_END = date(2020, 12, 31)

# --- 1. signal days & pool (shared lib) -------------------------------------
cal = r16.market_calendar(ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet")
cf = cal["date"].to_list()
idx = {d: i for i, d in enumerate(cf)}
mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= date(2015, 1, 5)) & (pl.col("s") <= DEV_END))
SIG = [d for d in mes["s"].to_list()
       if idx[d] + 1 < len(cf) and cf[idx[d] + 1] <= DEV_END]
pool = r16.build_history_r16(ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet", cal)
pools = r16.signal_pools(pool, pl.DataFrame({"s": SIG}))
pools_at = r16.pools_by_signal(pools)
pool_set = {t: set(pools_at[t]["ranked"]) for t in SIG}

# --- 2. independent forward returns (own implementation) --------------------
panel = pl.read_parquet(
    ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
).filter(pl.col("date") <= DEV_END)
panel = panel.with_columns(
    (pl.col("close").cast(pl.Float64) / pl.col("preclose").cast(pl.Float64) - 1.0).alias("dr"))
panel = panel.with_columns(
    pl.int_range(pl.len()).over("symbol").alias("hd"))
panel = panel.filter(pl.col("tradestatus").cast(pl.Int64) == 1)
if "isST" in panel.columns:
    panel = panel.filter(pl.col("isST").cast(pl.Int64) == 0)
panel = panel.filter(pl.col("hd") >= 60)
H = 20
sigset = set(SIG)
R = {}
panel = panel.sort("symbol", "date")
rows = panel.select(["symbol", "date", "dr"]).iter_rows(named=True)
by_sym = defaultdict(list)
for r_ in rows:
    by_sym[r_["symbol"]].append((r_["date"], r_["dr"]))
for sym, lst in by_sym.items():
    n = len(lst)
    for i, (d, _) in enumerate(lst):
        if d in sigset and i + H < n:
            g = 1.0
            for j in range(i + 1, i + 1 + H):
                g *= 1.0 + max(lst[j][1], -0.9999)
            R[(d, sym)] = g - 1.0

# --- 3. factor scores, signs, z (rank pool per F3R1) ------------------------
all120 = pl.read_csv(F2R1 / "outputs/f2r1_all120.csv")
stats = {r_["factor_id"]: r_ for r_ in all120.iter_rows(named=True)}
dedup = pl.read_csv(
    ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212/outputs/dedup_clusters.csv")
REPS = sorted(dedup["representative"].to_list())
signs = {f: (1.0 if float(stats[f]["ic_mean"]) > 0 else -1.0) for f in REPS}
MIN_COV = -(-len(REPS) // 2)

wide = None
for f in REPS:
    fp = pl.read_parquet(F2R1 / "outputs" / FAM[f[0]] / f"{f}.parquet").rename({"value": f})
    wide = fp if wide is None else wide.join(fp, on=["symbol", "signal_date"],
                                             how="full", coalesce=True)
wide = wide.filter(pl.col("signal_date").is_in(pl.Series(SIG)))
Z = {}  # t -> sym -> {fid: z}
for t in SIG:
    g = wide.filter(pl.col("signal_date") == t)
    g = g.with_columns(sum(pl.col(f).is_not_null().cast(pl.Int8)
                           for f in REPS).alias("_n"))
    g = g.filter(pl.col("symbol").is_in(pl.Series(sorted(pool_set[t])))
                 & (pl.col("_n") >= MIN_COV))
    cnt = {f: g[f].count() for f in REPS}
    zt = {}
    for f in REPS:
        col = g[f].rank(method="average")
        p = (col - 1.0) / max(cnt[f] - 1.0, 1.0)  # nulls stay null
        gz = (p - 0.5) * signs[f]
        for sym, v in zip(g["symbol"].to_list(), gz.to_list()):
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                zt.setdefault(sym, {})[f] = v
    Z[t] = zt

# --- 4. contributions (own aggregation) --------------------------------------
sleeve = json.loads((CHASSIS / "outputs/sleeve_monthly_log.json")
                    .read_text(encoding="utf-8"))["EW"]
C = defaultdict(dict)  # fid -> t -> value
for entry in sleeve:
    t = date.fromisoformat(entry["month"])
    w = float(entry["w_T"])
    for s in entry["members"]:
        r = R.get((t, s))
        if r is None:
            continue
        zs = Z.get(t, {}).get(s)
        if not zs:
            continue
        for f, z in zs.items():
            C[f][t] = C[f].get(t, 0.0) + w * z * r

# --- 5. compare against attribution_ew.csv ------------------------------------
ew = pl.read_csv(RUN / "outputs/attribution_ew.csv")
byf = {r_["factor"]: r_ for r_ in ew.iter_rows(named=True)}
print(f"{'factor':6s} {'metric':16s} {'independent':>14s} {'reported':>14s} {'diff':>12s}")
fails = 0
for f in ("D19", "E16", "B12", "A17"):
    series = C[f]
    vals = np.array([series[t] for t in sorted(series)])
    rep = byf[f]
    checks = [
        ("n_months", len(vals), int(rep["n_months"])),
        ("cum", float(vals.sum()), float(rep["cum_contribution"])),
        ("contrib_2019", float(sum(v for t, v in series.items() if t.year == 2019)),
         float(rep["contrib_2019"])),
        ("contrib_2015", float(sum(v for t, v in series.items() if t.year == 2015)),
         float(rep["contrib_2015"])),
    ]
    mean = float(vals.mean())
    se = float(vals.std(ddof=1) / np.sqrt(len(vals)))
    checks.append(("t_stat", mean / se, float(rep["t_stat"])))
    for name, mine, theirs in checks:
        d = abs(mine - theirs)
        tol = 1e-9 if name in ("n_months",) else max(1e-6, abs(theirs) * 1e-4)
        flag = "OK" if d <= tol else "MISMATCH"
        if flag != "OK":
            fails += 1
        print(f"{f:6s} {name:16s} {mine:14.8f} {theirs:14.8f} {d:12.2e} {flag}")
print("== independent verification:", "ALL OK" if fails == 0 else f"{fails} MISMATCHES")
