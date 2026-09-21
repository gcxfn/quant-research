# -*- coding: utf-8 -*-
"""Wide-pool short-term reversal, dispersed EW consumption - frozen prereg.

Prereg: docs/research/exp-20260921-short-reversal-prereg.md
Monthly composition caliber. Signal = signal month's own chained return;
buy the N deepest decliners of the WIDE floor pool, hold one month,
rotate. Curves: B0 market EW, REV30 (main), REV100, MOM30 (direction
counter-proof), SREV20 (narrow stable-pool sensitivity).
Smoke: env SR_WINDOW="2015-02-01:2015-05-31".
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import polars as pl

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]

PREREG = ROOT / "docs/research/exp-20260921-short-reversal-prereg.md"
DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
DB_R2 = ROOT / "data/raw/tushare/daily_basic/20260913-r2"
DB_R1 = ROOT / "data/raw/tushare/daily_basic/20260909-r1"
FINA_DIR = ROOT / "data/raw/tushare/fina_indicator"
FCST_DIR = ROOT / "data/raw/tushare/forecast"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
MV_MIN_WAN_WIDE = 200_000.0      # wide pool: 20亿
MV_MIN_WAN_STABLE = 300_000.0
COMM = 0.0001
STAMP = 0.001
ROE_MIN, DEBT_MAX = 8.0, 65.0
BAD_TYPES = {"预亏", "首亏", "续亏", "预减"}

_win = os.environ.get("SR_WINDOW", "full")
SMOKE = _win != "full"
if SMOKE:
    _a, _b = _win.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
else:
    WIN_START, WIN_END = DEV_START, DEV_END

T0 = time.perf_counter()
LOG = (RUN_DIR / "logs" / "runner.log").open("a", encoding="utf-8")


def log(m):
    line = f"[{time.perf_counter()-T0:7.1f}s] {m}"
    LOG.write(line + "\n")
    LOG.flush()
    print(line, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


log(f"short-reversal; window {WIN_START}..{WIN_END}"
    f"{' (SMOKE)' if SMOKE else ''}")

pins = {"prereg": {"sha256": sha256_file(PREREG)}}
pins["daily"] = {"sha256": sha256_file(DAILY)}
log("pins done")

# === 1. monthly series ======================================================
panel = pl.read_parquet(DAILY, columns=["symbol", "date", "close", "preclose",
                                        "tradestatus", "isST"])
panel = panel.filter((pl.col("date") >= date(2014, 6, 1))
                     & (pl.col("date") <= WIN_END))
panel = panel.with_columns(
    pl.when(pl.col("preclose") > 0)
      .then(pl.col("close") / pl.col("preclose") - 1.0)
      .otherwise(0.0).alias("dret"))
panel = panel.with_columns(
    (pl.col("date").dt.year() * 100 + pl.col("date").dt.month()).alias("ym"))
mstats = (panel.group_by("symbol", "ym")
          .agg(pl.col("date").max().alias("med"),
               pl.col("close").last().alias("close_me"),
               pl.col("isST").last().alias("isst_me"),
               (pl.col("dret") + 1.0).product().alias("mret"))
          .sort("symbol", "ym"))
first_overall = (pl.read_parquet(DAILY, columns=["symbol", "date"])
                 .group_by("symbol")
                 .agg(pl.col("date").min().alias("first_bar_all"))
                 .sort("symbol"))
mstats = mstats.join(first_overall, on="symbol", how="left")
month_last_days: dict[int, date] = {}
for (ym,), g in panel.group_by("ym", maintain_order=True):
    month_last_days[int(ym)] = g["date"].max()
log(f"  month-symbol rows: {mstats.height}")

# === 2. daily_basic month-end ===============================================
def ts_to_sym(code: str) -> str:
    n, ex = code.split(".")
    return f"{ex.lower()}.{n}"


def _readable(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 64


need_days = sorted(set(month_last_days.values()))
db_rows = []
for d in need_days:
    for base in (DB_R2, DB_R1):
        p = base / f"chunk_{d.strftime('%Y%m%d')}.csv"
        if _readable(p):
            db_rows.append(p)
            break
db = pl.concat([pl.read_csv(p, infer_schema_length=0) for p in db_rows],
               how="vertical")
for c_ in ("pb", "dv_ttm", "total_mv"):
    db = db.with_columns(pl.col(c_).cast(pl.Float64, strict=False).alias(c_))
db = db.with_columns(
    pl.col("trade_date").str.to_date("%Y%m%d").alias("td"))
db = db.with_columns(
    (pl.col("td").dt.year().cast(pl.Int64) * 100
     + pl.col("td").dt.month().cast(pl.Int64)).alias("ym"),
    pl.col("ts_code").map_elements(ts_to_sym, return_dtype=pl.String)
    .alias("symbol"))
db = db.select("symbol", "ym", "pb", "dv_ttm", "total_mv")
pb_hist: dict[str, dict[int, float]] = defaultdict(dict)
dv_hist: dict[str, dict[int, float]] = defaultdict(dict)
mv_me = {}
for r in db.iter_rows(named=True):
    pb_hist[r["symbol"]][int(r["ym"])] = r["pb"]
    if r["dv_ttm"] is not None:
        dv_hist[r["symbol"]][int(r["ym"])] = r["dv_ttm"]
    mv_me[(r["symbol"], int(r["ym"]))] = r["total_mv"]
log(f"  daily_basic month-end rows: {db.height}")

# === 3. fina PIT + forecast mine ============================================
_fina_files = [f for f in sorted(FINA_DIR.rglob("*.csv"))
               if f.stat().st_size > 64]
fina = pl.concat([pl.read_csv(f, infer_schema_length=0)
                  for f in _fina_files], how="vertical")
fina = fina.select("ts_code", "ann_date", "end_date", "roe",
                   "debt_to_assets")
fina = fina.filter(pl.col("ann_date").is_not_null())
fina = fina.with_columns(
    pl.col("ann_date").str.to_date("%Y%m%d").alias("ad"),
    pl.col("ts_code").map_elements(ts_to_sym, return_dtype=pl.String)
    .alias("symbol"))
fina = fina.with_columns(
    (pl.col("ad").dt.year().cast(pl.Int64) * 100
     + pl.col("ad").dt.month().cast(pl.Int64)).alias("ann_ym"))
fina = fina.with_columns(
    pl.col("roe").cast(pl.Float64, strict=False).alias("roe_f"),
    pl.col("debt_to_assets").cast(pl.Float64, strict=False).alias("debt_f"))
fina = fina.filter(pl.col("roe_f").is_not_null()
                   & pl.col("debt_f").is_not_null())
fina_by_sym: dict[str, list] = {}
for (sym,), g in fina.sort("ad").group_by("symbol", maintain_order=False):
    fina_by_sym[str(sym)] = list(zip(g["ann_ym"].to_list(),
                                     g["roe_f"].to_list(),
                                     g["debt_f"].to_list()))
_fcst_files = [f for f in sorted(FCST_DIR.rglob("*.csv"))
               if f.stat().st_size > 64]
fcst = pl.concat([pl.read_csv(f, infer_schema_length=0)
                  for f in _fcst_files], how="vertical")
fcst = fcst.select("ts_code", "ann_date", "type")
fcst = fcst.filter(pl.col("type").is_in(list(BAD_TYPES))
                   & pl.col("ann_date").is_not_null())
fcst = fcst.with_columns(
    pl.col("ann_date").str.to_date("%Y%m%d").alias("ad"),
    pl.col("ts_code").map_elements(ts_to_sym, return_dtype=pl.String)
    .alias("symbol"))
fcst = fcst.with_columns(
    (pl.col("ad").dt.year().cast(pl.Int64) * 100
     + pl.col("ad").dt.month().cast(pl.Int64)).alias("ann_ym"))
bad_by_sym: dict[str, set[int]] = defaultdict(set)
for r in fcst.iter_rows(named=True):
    bad_by_sym[r["symbol"]].add(int(r["ann_ym"]))
log(f"  fina rows {fina.height}; bad-forecast symbols {len(bad_by_sym)}")


def _shift(ym: int, k: int) -> int:
    y, m = divmod(ym, 100)
    t = y * 12 + (m - 1) + k
    return (t // 12) * 100 + t % 12 + 1


mrow: dict[tuple[str, int], dict] = {}
for r in mstats.iter_rows(named=True):
    mrow[(r["symbol"], int(r["ym"]))] = r
all_syms = sorted({s for s, _ in mrow})

pool_stats = {"wide": 0, "stable": 0, "n": 0}


def wide_ok(sym: str, ym: int, med: date) -> bool:
    r_ = mrow.get((sym, ym))
    if r_ is None or r_["isst_me"] or r_["close_me"] is None:
        return False
    if r_["first_bar_all"] is None:
        return False
    if ((med.year - r_["first_bar_all"].year) * 12
            + med.month - r_["first_bar_all"].month) < 12:
        return False
    mv = mv_me.get((sym, ym))
    if mv is None or mv < MV_MIN_WAN_WIDE:
        return False
    bad = bad_by_sym.get(sym)
    if bad and any(_shift(ym, -k) in bad for k in range(12)):
        return False
    return True


def stable_ok(sym: str, ym: int, med: date) -> bool:
    if not wide_ok(sym, ym, med):
        return False
    mv = mv_me.get((sym, ym))
    if mv is None or mv < MV_MIN_WAN_STABLE:
        return False
    dh = dv_hist.get(sym)
    if not dh or not any(v > 0 for k, v in dh.items()
                         if _shift(ym, -24) <= k <= ym):
        return False
    rows = fina_by_sym.get(sym)
    if not rows:
        return False
    recent = [x for x in rows if x[0] <= ym][-2:]
    if len(recent) < 2 or any(x[1] < ROE_MIN for x in recent):
        return False
    if recent[-1][2] > DEBT_MAX:
        return False
    return True


# === 4. simulation ==========================================================
results = {c: {} for c in ["B0", "REV30", "REV100", "MOM30", "SREV20"]}
turn_buy = {c: 0.0 for c in results}
w_prev = {c: {} for c in results}
ym_seq = sorted(ym for ym in month_last_days
                if WIN_START <= month_last_days[ym] <= WIN_END)
for i, ym in enumerate(ym_seq):
    med = month_last_days[ym]
    live = {}
    for sym in all_syms:
        r_ = mrow.get((sym, ym))
        if r_ is None or r_["close_me"] is None:
            continue
        live[sym] = r_["mret"] - 1.0
    wide = [s for s in live if wide_ok(s, ym, med)]
    stable = [s for s in live if stable_ok(s, ym, med)]
    if i == len(ym_seq) // 2:
        pool_stats.update({"wide": len(wide), "stable": len(stable),
                           "n": i})
    rev_wide = sorted(wide, key=lambda s: live[s])
    mom_wide = sorted(wide, key=lambda s: -live[s])
    rev_stable = sorted(stable, key=lambda s: live[s])
    for curve in results:
        if curve == "B0":
            w_new = {s: 1.0 / len(live) for s in live}
        elif curve == "REV30":
            w_new = {s: 1.0 / 30 for s in rev_wide[:30]}
        elif curve == "REV100":
            w_new = {s: 1.0 / 100 for s in rev_wide[:100]}
        elif curve == "MOM30":
            w_new = {s: 1.0 / 30 for s in mom_wide[:30]}
        else:
            w_new = {s: 1.0 / 20 for s in rev_stable[:20]}
        gross = sum(w * live.get(s, 0.0) for s, w in w_prev[curve].items())
        grown = {s: w * (1.0 + live.get(s, 0.0))
                 for s, w in w_prev[curve].items()}
        turn_b = sum(max(0.0, w_new.get(s, 0.0) - grown.get(s, 0.0))
                     for s in set(w_new) | set(grown))
        turn_s = sum(max(0.0, grown.get(s, 0.0) - w_new.get(s, 0.0))
                     for s in set(w_new) | set(grown))
        cost = turn_b * COMM + turn_s * (COMM + STAMP)
        turn_buy[curve] += turn_b
        results[curve][f"{ym}"] = gross - cost
        w_prev[curve] = w_new
log(f"  months {len(ym_seq)}; mid-run pools wide {pool_stats['wide']} "
    f"stable {pool_stats['stable']}")


# === 5. metrics & gates =====================================================
def cagr_m(m):
    g = 1.0
    for k in sorted(m):
        g *= 1.0 + m[k]
    return g ** (12.0 / len(m)) - 1 if m else float('nan')


def mdd_m(m):
    eq = peak = 1.0
    dd = 0.0
    for k in sorted(m):
        eq *= 1.0 + m[k]
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    return dd


def yearly(m):
    per = {}
    for k in sorted(m):
        y = int(k[:4])
        per.setdefault(y, 1.0)
        per[y] *= 1.0 + m[k]
    return {y: v - 1 for y, v in per.items()}


metrics, gates = {}, {}
for c in results:
    m = results[c]
    y = yearly(m)
    metrics[c] = {"cagr": cagr_m(m), "mdd": mdd_m(m),
                  "by_year": {str(k): v for k, v in y.items()},
                  "n_years": len(y),
                  "avg_annual_buy_turnover":
                      turn_buy[c] / (len(m) / 12.0)}
b0y = yearly(results["B0"])
for c in results:
    metrics[c]["advantage_years"] = sum(
        1 for yy in metrics[c]["by_year"] if int(yy) in b0y
        and metrics[c]["by_year"][yy] > b0y[int(yy)])
a = metrics["REV30"]
g = {"1_cagr_ge_B0_plus_2pp":
         a["cagr"] - metrics["B0"]["cagr"] >= 0.02,
     "2_mdd_le_30pct": abs(a["mdd"]) <= 0.30,
     "3_advantage_years_ge_4_of_6":
         a["advantage_years"] >= 4 and a["n_years"] >= 6,
     "4_buy_turnover_le_13": a["avg_annual_buy_turnover"] <= 13.0}
g["failed"] = sorted(k for k, v in g.items() if not v)
g["dev_pass"] = not g["failed"]
gates["REV30"] = g
for c in results:
    a_ = metrics[c]
    extra = (f" -> {'PASS' if gates[c]['dev_pass'] else 'fail ' + str(gates[c]['failed'])}"
             if c == "REV30" else "")
    log(f"  {c}: cagr {a_['cagr']*100:+.2f}% mdd {a_['mdd']*100:.1f}% "
        f"adv {a_['advantage_years']}/{a_['n_years']} "
        f"buy-turn {a_['avg_annual_buy_turnover']:.1f}{extra}")

(RUN_DIR / "outputs" / "metrics.json").write_text(
    json.dumps({"metrics": metrics, "gates": gates, "monthly": results},
               ensure_ascii=False, indent=1, default=str), encoding="utf-8")

if not SMOKE:
    rep = ["# 宽池短期反转（分散等权）dev 报告", "",
           f"- 运行 `{RUN_DIR.name}`；预登记冻结；2015-02..2020-12；"
           "月度合成口径。", "",
           "| 曲线 | 年化 | 回撤 | 优势年 | 年买换手 | 判定 |",
           "|---|---|---|---|---|---|"]
    for c in results:
        a_ = metrics[c]
        v = ("**PASS**" if c == "REV30" and gates["REV30"]["dev_pass"]
             else gates["REV30"]["failed"] if c == "REV30" else "-")
        rep.append(f"| {c} | {a_['cagr']*100:+.2f}% | {a_['mdd']*100:.1f}% "
                   f"| {a_['advantage_years']}/{a_['n_years']} "
                   f"| {a_['avg_annual_buy_turnover']:.1f} | {v} |")
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-short-reversal",
    "status": "completed", "mode": "smoke" if SMOKE else "full",
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "pins": pins,
    "params": {"mv_min_wide_wan": MV_MIN_WAN_WIDE,
               "mv_min_stable_wan": MV_MIN_WAN_STABLE,
               "lists": "REV30/REV100/MOM30/SREV20"},
    "trial_accounting": {"strategy_line": {"before": 301,
                                           "this_round": 0 if SMOKE else 5,
                                           "after": 301 if SMOKE else 306}},
    "known_simplifications": [
        "monthly composition caliber (month-end fills); engine gap lesson "
        "registered",
        "stamp duty modelled 0.1% throughout (conservative post-2023.08)"],
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(RUN_DIR.rglob("*"))
                if p.is_file() and p.name not in ("manifest.json",
                                                  "runner.log")},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log("done")
LOG.close()
