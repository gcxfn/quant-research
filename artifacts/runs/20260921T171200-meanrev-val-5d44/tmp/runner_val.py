# -*- coding: utf-8 -*-
"""Anchored mean-reversion VAL consumption (C1/M1/M2) - frozen prereg.

Prereg: docs/research/exp-20260921-mean-reversion-val-prereg.md
Monthly composition caliber (same as ETF-momentum stage A): monthly returns
are close/preclose chained daily returns (dividend/-split correct), weights
per holding, costs on turnover (0.01% commission both sides + 0.1% stamp
on sells). Six curves: B0 market EW, C1 stable-pool EW, C2 pure-decline
top5 (monthly rotation), M1 main+S1 sells, M2 main+S2 sells, M0 main+S1
no-stabilisation. No engine replay in this experiment (signal-level only).
Smoke: env MR_WINDOW="2017-01-01:2017-06-30".
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

PREREG = ROOT / "docs/research/exp-20260921-mean-reversion-val-prereg.md"
DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
DB_R2 = ROOT / "data/raw/tushare/daily_basic/20260913-r2"
DB_R1 = ROOT / "data/raw/tushare/daily_basic/20260909-r1"
FINA_DIR = ROOT / "data/raw/tushare/fina_indicator"
FCST_DIR = ROOT / "data/raw/tushare/forecast"

VAL_START, VAL_END = date(2021, 1, 4), date(2024, 12, 31)
BAND = 24              # months of PB history for the anchor
Z_TRIG = -1.5
TOPN = 5
MAX_HOLD = 10
MIN_HOLD_M = 3
MAX_HOLD_M = 6
HARD_STOP = -0.20
MV_MIN_WAN = 300_000.0          # total_mv >= 30亿 (tushare unit: 万元)
Z_SELL_S1 = (-0.5, 0.0, 0.5)    # thirds
Z_SELL_S2 = (-0.5, 0.0, 0.5, 1.0, 1.5)
ROE_MIN = 8.0
DEBT_MAX = 65.0
BAD_TYPES = {"预亏", "首亏", "续亏", "预减"}
COMM = 0.0001
STAMP = 0.001

_win = os.environ.get("MR_WINDOW", "full")
SMOKE = _win != "full"
if SMOKE:
    _a, _b = _win.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
else:
    WIN_START, WIN_END = VAL_START, VAL_END

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


log(f"meanrev-anchored; window {WIN_START}..{WIN_END}"
    f"{' (SMOKE)' if SMOKE else ''}")

# === 0. pins ================================================================
pins = {"prereg": {"sha256": sha256_file(PREREG)}}
for name, d in [("daily", DAILY.parent), ("daily_basic_r2", DB_R2),
                ("daily_basic_r1", DB_R1), ("fina", FINA_DIR),
                ("fcst", FCST_DIR)]:
    h = hashlib.sha256()
    n = 0
    for p in sorted(d.rglob("*.csv"))[:5000]:
        h.update(f"{sha256_file(p)}  {p.name}\n".encode())
        n += 1
    pins[name] = {"files_hashed": n, "sha256": h.hexdigest()}
log("pins done")

# === 1. month-end calendar & per-symbol monthly data ========================
log("== 1. daily panel -> monthly series ==")
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
# month-end rows & per-symbol stats
mstats = (panel.group_by("symbol", "ym")
          .agg(pl.col("date").max().alias("med"),
               pl.col("close").last().alias("close_me"),
               pl.col("isST").last().alias("isst_me"),
               (pl.col("dret") + 1.0).product().alias("mret"),
               pl.col("close").tail(10).mean().alias("ma10"),
               pl.col("close").tail(20).mean().alias("ma20"),
               pl.col("date").min().alias("first_bar"))
          .sort("symbol", "ym"))
# listing age must come from the FULL history (panel is date-truncated);
# a separate pass over the raw parquet keeps this PIT-correct
first_overall = (pl.read_parquet(DAILY, columns=["symbol", "date"])
                 .group_by("symbol")
                 .agg(pl.col("date").min().alias("first_bar_all"))
                 .sort("symbol"))
mstats = mstats.join(first_overall, on="symbol", how="left")
log(f"  month-symbol rows: {mstats.height}")

# === 2. daily_basic month-end PB/dv/mv ======================================
log("== 2. daily_basic month-end ==")


def ts_to_sym(code: str) -> str:
    n, ex = code.split(".")
    return f"{ex.lower()}.{n}"


month_last_days: dict[int, date] = {}
for (ym,), g in panel.group_by("ym", maintain_order=True):
    month_last_days[int(ym)] = g["date"].max()
need_days = sorted(set(month_last_days.values()))
db_rows = []
def _readable(p: Path) -> bool:
    return p.exists() and p.stat().st_size > 64


for d in need_days:
    for base in (DB_R2, DB_R1):
        p = base / f"chunk_{d.strftime('%Y%m%d')}.csv"
        if _readable(p):
            db_rows.append(p)
            break
log(f"  reading {len(db_rows)} month-end daily_basic chunks")
db = pl.concat([pl.read_csv(p, infer_schema_length=0)
                for p in db_rows], how="vertical")
for c_ in ("pb", "dv_ttm", "total_mv"):
    db = db.with_columns(
        pl.col(c_).cast(pl.Float64, strict=False).alias(c_))
db = db.filter(pl.col("pb").is_not_null() & (pl.col("pb") > 0))
db = db.with_columns(
    pl.col("trade_date").str.to_date("%Y%m%d").alias("td"))
db = db.with_columns(
    (pl.col("td").dt.year().cast(pl.Int64) * 100
     + pl.col("td").dt.month().cast(pl.Int64)).alias("ym"),
    pl.col("ts_code").map_elements(ts_to_sym, return_dtype=pl.String)
    .alias("symbol"))
db = db.select("symbol", "ym", "pb", "dv_ttm", "total_mv")
log(f"  daily_basic month-end rows: {db.height}")

# PB history per symbol: ym -> pb for the 24m band
pb_hist: dict[str, dict[int, float]] = defaultdict(dict)
for r in db.iter_rows(named=True):
    pb_hist[r["symbol"]][int(r["ym"])] = r["pb"]
dv_hist: dict[str, dict[int, float]] = defaultdict(dict)
for r in db.iter_rows(named=True):
    if r["dv_ttm"] is not None:
        dv_hist[r["symbol"]][int(r["ym"])] = r["dv_ttm"]
mv_me = {(r["symbol"], int(r["ym"])): r["total_mv"] for r in db.iter_rows(named=True)}

# === 3. fina PIT snapshots & forecast mine-field =============================
log("== 3. fina_indicator PIT + forecast ==")
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
log(f"  fina rows: {fina.height}")

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
log(f"  bad-forecast symbols: {len(bad_by_sym)}")

# PIT lookups prepared as sorted arrays per symbol
fina_by_sym: dict[str, list] = {}
for (sym,), g in fina.sort("ad").group_by("symbol", maintain_order=False):
    fina_by_sym[str(sym)] = list(zip(g["ann_ym"].to_list(),
                                     g["ad"].to_list(),
                                     g["roe_f"].to_list(),
                                     g["debt_f"].to_list()))

# monthly stats lookup
mrow: dict[tuple[str, int], dict] = {}
for r in mstats.iter_rows(named=True):
    mrow[(r["symbol"], int(r["ym"]))] = r

all_syms = sorted({s for s, _ in mrow})
sig_yms = sorted(ym for ym in month_last_days
                 if WIN_START <= month_last_days[ym] <= WIN_END)
# pre-signal yms for the 24m band and 24m price decline
pre_yms = sorted(ym for ym in month_last_days if ym < min(sig_yms))

# cumulative month return from a base ym to current ym per symbol
mret_by: dict[tuple[str, int], float] = {}
for r in mstats.iter_rows(named=True):
    mret_by[(r["symbol"], int(r["ym"]))] = r["mret"] - 1.0


def cum_ret(sym: str, yms: list[int]) -> float | None:
    g = 1.0
    seen = 0
    for y in yms:
        r_ = mret_by.get((sym, y))
        if r_ is None:
            return None
        g *= 1.0 + r_
        seen += 1
    return g - 1.0 if seen == len(yms) else None


from bisect import bisect_left  # noqa: E402


def _shift(ym: int, k: int) -> int:
    """ym=YYYYMM shifted by k months."""
    y, m = divmod(ym, 100)
    t = y * 12 + (m - 1) + k
    return (t // 12) * 100 + t % 12 + 1


def z_anchor(sym: str, ym: int) -> float | None:
    """z of this month's PB vs the previous BAND months of own history."""
    hist = pb_hist.get(sym)
    if not hist:
        return None
    keys = sorted(hist)
    idx = bisect_left(keys, ym)
    vals = [hist[y] for y in keys[max(0, idx - BAND):idx]]
    if len(vals) < 20:
        return None
    arr = np.array(vals)
    sd = arr.std()
    if sd <= 1e-9:
        return None
    cur = hist.get(ym)
    if cur is None:
        return None
    return float((cur - arr.mean()) / sd)


def stable_ok(sym: str, ym: int, med: date) -> bool:
    r_ = mrow.get((sym, ym))
    if r_ is None or r_["isst_me"] or r_["close_me"] is None:
        return False
    if r_["first_bar_all"] is None:
        return False
    age_m = ((med.year - r_["first_bar_all"].year) * 12
             + med.month - r_["first_bar_all"].month)
    if age_m < 36:
        return False
    dh = dv_hist.get(sym)
    if not dh or not any(v > 0 for k, v in dh.items() if _shift(ym, -24) <= k <= ym):
        return False
    mv = mv_me.get((sym, ym))
    if mv is None or mv < MV_MIN_WAN:
        return False
    rows = fina_by_sym.get(sym)
    if not rows:
        return False
    recent = [x for x in rows if x[0] <= ym][-2:]
    if len(recent) < 2 or any(x[2] < ROE_MIN for x in recent):
        return False
    if recent[-1][3] > DEBT_MAX:
        return False
    bad = bad_by_sym.get(sym)
    if bad:
        for k in range(0, 12):
            if _shift(ym, -k) in bad:
                return False
    return True


# === 4. strategy simulation =================================================
log("== 4. simulation ==")
results: dict[str, dict[str, float]] = {c: {} for c in
                                        ["B0", "C1", "C2", "M1", "M2", "M0"]}
turnover_acc = {c: 0.0 for c in results}
n_months = 0
pool_sizes = []
trig_counts = {"pool": 0, "trigger": 0}

# holdings: sym -> dict(bought_ym_k, cum_ret_base list of yms held)
hold: dict[str, dict[str, dict]] = {c: {} for c in ["M1", "M2", "M0"]}
w_prev: dict[str, dict[str, float]] = {c: {} for c in results}
ym_seq = sorted(ym for ym in month_last_days
                if WIN_START <= month_last_days[ym] <= WIN_END)
for i, ym in enumerate(ym_seq):
    med = month_last_days[ym]
    n_months += 1
    live = {}          # symbol -> this-month return for tradable universe
    for sym in all_syms:
        r_ = mrow.get((sym, ym))
        if r_ is None or r_["close_me"] is None:
            continue
        live[sym] = r_["mret"] - 1.0
    # ---- targets per curve ----
    stable = [s for s in live if stable_ok(s, ym, med)]
    pool_sizes.append(len(stable))
    zmap = {}
    for s in stable:
        z = z_anchor(s, ym)
        if z is not None and z <= Z_TRIG:
            zmap[s] = z
    trig_counts["pool"] += len(stable)
    trig_counts["trigger"] += len(zmap)
    # C2: pure 24m decline
    decline = {}
    for s in live:
        r_ = mrow.get((s, ym))
        if r_["isst_me"] or r_["first_bar_all"] is None:
            continue
        if (((med.year - r_["first_bar_all"].year) * 12
             + med.month - r_["first_bar_all"].month) < 36):
            continue
        mv = mv_me.get((s, ym))
        if mv is None or mv < MV_MIN_WAN:
            continue
        yms24 = [_shift(ym, -k - 1) for k in range(24)]
        cr = cum_ret(s, yms24)
        if cr is not None:
            decline[s] = cr
    c2_picks = sorted(decline, key=lambda s: decline[s])[:TOPN]

    for curve in results:
        if curve == "B0":
            w_new = {s: 1.0 / len(live) for s in live}
        elif curve == "C1":
            w_new = {s: 1.0 / len(stable) for s in stable} if stable else {}
        elif curve == "C2":
            w_new = {s: 1.0 / TOPN for s in c2_picks}
        else:
            # main groups: manage holding lifecycle
            sell_z = Z_SELL_S1 if curve in ("M1", "M0") else Z_SELL_S2
            n_batches = len(sell_z)
            H = hold[curve]
            # sells first
            for s in sorted(list(H)):
                h = H[s]
                held_months = i - h["entry_i"]
                r_ = mrow.get((s, ym))
                cum = cum_ret(s, [y2 for y2 in ym_seq[h["entry_i"]:i + 1]])
                cum = cum if cum is not None else 0.0
                if r_ is None:
                    continue                      # suspended: hold
                if cum <= HARD_STOP and held_months >= 1:
                    h["sold"] = 1.0
                elif held_months >= MIN_HOLD_M:
                    z_now = z_anchor(s, ym)
                    if held_months >= MAX_HOLD_M:
                        h["sold"] = 1.0
                    elif z_now is not None:
                        cleared = sum(1 for zz in sell_z if z_now >= zz)
                        h["sold"] = min(cleared / n_batches, 1.0)
            for s in list(H):
                if H[s].get("sold", 0.0) >= 1.0 - 1e-9:
                    del H[s]
            # buys: fill free slots
            free = MAX_HOLD - len(H)
            cands = sorted(zmap, key=lambda s: zmap[s])
            bought = []
            for s in cands:
                if free <= 0:
                    break
                if s in H:
                    continue
                r_ = mrow.get((s, ym))
                stab = curve != "M0"
                if stab and not (r_ and r_["ma10"] and r_["ma20"]
                                 and r_["ma10"] > r_["ma20"]):
                    continue
                H[s] = {"entry_i": i, "weight": 0.0, "sold": 0.0}
                bought.append(s)
                free -= 1
            # weights: entry-month buys get next month's exposure; for the
            # composition caliber we set the target at month END: equal
            # split across current holdings
            if H:
                eq = 1.0 / len(H)
                for s in H:
                    H[s]["weight_target"] = eq * (1.0 - H[s].get("sold", 0.0))
            w_new = {s: h.get("weight_target", 0.0) for s, h in H.items()
                     if h.get("weight_target", 0.0) > 1e-9}
        # ---- return & cost ----
        gross = sum(w * live.get(s, 0.0) for s, w in w_prev[curve].items())
        bought_amt = sum(w for s, w in w_new.items()
                         if w > w_prev[curve].get(s, 0.0))
        sold_amt = sum(w_prev[curve].get(s, 0.0) - w
                       for s, w in w_new.items()
                       if w < w_prev[curve].get(s, 0.0))
        # weight drift adjustment (positions grew/shrank with returns)
        grown = {}
        for s, w in w_prev[curve].items():
            grown[s] = w * (1.0 + live.get(s, 0.0))
        turn_b = sum(max(0.0, w_new.get(s, 0.0) - grown.get(s, 0.0))
                     for s in set(w_new) | set(grown))
        turn_s = sum(max(0.0, grown.get(s, 0.0) - w_new.get(s, 0.0))
                     for s in set(w_new) | set(grown))
        cost = turn_b * COMM + turn_s * (COMM + STAMP)
        turnover_acc[curve] += (turn_b + turn_s)
        results[curve][f"{ym}"] = gross - cost
        w_prev[curve] = w_new

log(f"  months {n_months}; pool median {int(np.median(pool_sizes))} "
    f"max {max(pool_sizes)}; triggers total {trig_counts['trigger']}")

# === 5. metrics =============================================================
def cagr_m(m: dict[str, float]) -> float:
    g = 1.0
    for k in sorted(m):
        g *= 1.0 + m[k]
    n = len(m) / 12.0
    return g ** (1 / n) - 1 if n > 0 else float('nan')


def mdd_m(m: dict[str, float]) -> float:
    eq = peak = 1.0
    dd = 0.0
    for k in sorted(m):
        eq *= 1.0 + m[k]
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    return dd


def yearly(m: dict[str, float]) -> dict[int, float]:
    per: dict[int, float] = {}
    for k in sorted(m):
        y = int(k[:4])
        per.setdefault(y, 1.0)
        per[y] *= 1.0 + m[k]
    return {y: v - 1 for y, v in per.items()}


b0 = results["B0"]
b0y = yearly(b0)
metrics, gates = {}, {}
for c in results:
    m = results[c]
    y = yearly(m)
    adv = sum(1 for yy in y if yy in b0y and y[yy] > b0y[yy])
    metrics[c] = {"cagr": cagr_m(m), "mdd": mdd_m(m),
                  "by_year": {str(k): v for k, v in y.items()},
                  "advantage_years": adv, "n_years": len(y),
                  "avg_annual_turnover": turnover_acc[c] / (len(m) / 12.0)}
for c in ("C1", "M1", "M2"):
    a = metrics[c]
    g = {"1_cagr_ge_B0_plus_2pp":
             a["cagr"] - metrics["B0"]["cagr"] >= 0.02,
         "2_mdd_le_30pct": abs(a["mdd"]) <= 0.30,
         "3_advantage_years_ge_3_of_4": a["advantage_years"] >= 3 and a["n_years"] == 4}
    if c in ("M1", "M2"):
        g["4_turnover_le_6"] = a["avg_annual_turnover"] <= 6.0
        g["identity"] = "dev-eliminated; diagnostic only"
    g["failed"] = sorted(k for k, v in g.items()
                         if isinstance(v, bool) and not v)
    g["val_pass"] = not g["failed"]
    gates[c] = g
    log(f"  {c}: cagr {a['cagr']*100:+.2f}% mdd {a['mdd']*100:.1f}% "
        f"adv {a['advantage_years']}/{a['n_years']} "
        f"turn {a['avg_annual_turnover']:.1f} -> "
        f"{'PASS' if g['val_pass'] else 'fail ' + str(g['failed'])}")
for c in ("B0", "C1", "C2", "M0"):
    a = metrics[c]
    log(f"  {c}: cagr {a['cagr']*100:+.2f}% mdd {a['mdd']*100:.1f}% "
        f"adv {a['advantage_years']}/{a['n_years']}")

(RUN_DIR / "outputs" / "metrics.json").write_text(
    json.dumps({"metrics": metrics, "gates": gates,
                "pool_sizes": {"median": int(np.median(pool_sizes)),
                               "max": max(pool_sizes)},
                "trigger_total": trig_counts,
                "monthly": results}, ensure_ascii=False, indent=1,
               default=str), encoding="utf-8")

if not SMOKE:
    rep = ["# 均值回归家族 val 消费（C1/M1/M2）报告", "",
           f"- 运行 `{RUN_DIR.name}`；预登记冻结；2021-01..2024-12；"
           "月度合成口径（月末收盘、close/preclose 链收益）。", "",
           "| 曲线 | 年化 | 回撤 | 优势年 | 年换手 | 判定 |",
           "|---|---|---|---|---|---|"]
    for c in results:
        a = metrics[c]
        verdict = (gates[c]["val_pass"] if c in gates else "-")
        rep.append(f"| {c} | {a['cagr']*100:+.2f}% | {a['mdd']*100:.1f}% "
                   f"| {a['advantage_years']}/{a['n_years']} "
                   f"| {a['avg_annual_turnover']:.1f} "
                   f"| {'**PASS**' if verdict is True else verdict} |")
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-mean-reversion-val",
    "status": "completed", "mode": "smoke" if SMOKE else "full",
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "pins": pins,
    "params": {"band_months": BAND, "z_trig": Z_TRIG, "topn": TOPN,
               "max_hold": MAX_HOLD, "min_hold_m": MIN_HOLD_M,
               "max_hold_m": MAX_HOLD_M, "hard_stop": HARD_STOP,
               "sell_s1": Z_SELL_S1, "sell_s2": Z_SELL_S2},
    "trial_accounting": {"strategy_line": {"before": 298,
                                           "this_round": 0 if SMOKE else 3,
                                           "after": 298 if SMOKE else 301},
                         "val_consumed_configs": ["C1", "M1", "M2"]},
    "known_simplifications": [
        "monthly composition caliber: month-end close fills, no intraday "
        "path, no limit boards; engine-grade replay required before any "
        "live claim (see ETF-momentum friction lesson)",
        "cash-flow/NI quality check replaced by dividend>0 (prereg layer 4)"],
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
