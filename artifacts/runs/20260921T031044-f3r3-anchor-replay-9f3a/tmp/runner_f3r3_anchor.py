# ANCHOR REPLAY (task 2, 2026-09-21): verbatim copy of
#   artifacts/runs/20260921T024449-f3r3-dynamic-45037d/tmp/runner_f3r3.py
# with EXACTLY ONE edit: ENGINE_SHA_EXPECT_16 bcbdd44bb855b803 ->
# d4b6c3764780e6de (engine v1.5, whose etf_routing default leaves this
# stock-only path byte-identical).  Every other byte, assertion and input
# path is the F3R3 run's own, so the five output frames below are directly
# filecmp-able against artifacts/runs/20260921T024449-f3r3-dynamic-45037d/
# outputs/.  Zero trial consumption; the F3R3 run directory is untouched.
# -*- coding: utf-8 -*-
"""F3R3 dynamic-engine factor-combination runner.

Prereg: docs/research/exp-20260921-factor-round-f3r3-prereg.md (frozen).

Same portfolio as F3R1 (43 F2R1 survivors -> 20 correlation reps -> EW/ICW
composite -> buffer membership K=10), re-tested on the REBUILT engine with
execution_clock='halfday' and an intent_provider that re-issues intents at
every decision point from the live ledger (no static frame, no seat
vacancy: a member seat is re-bought every half-day until filled or the
name leaves the pool; sells stay engine-side m3 carry + K=3 fallback).

Steps 0-4 and 6-7 are verbatim F3R1; step 5 (static frames) is replaced by
provider factories; step 9 attribution is seat-signal aggregated.

Modes: env F3R3_WINDOW="2015-01-01:2015-03-31" for the engineering smoke
(benchmarks and gates skipped); default full dev window.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from bisect import bisect_left
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_halfday_bars,
    load_split_factor_h5, load_stk_limit_batch, run_band_backtest_intents)

F2R1 = ROOT / "artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5/f3_inputs"
CONFIG = ROOT / "configs/experiments/f3r1-factor-combination.json"
PREREG = ROOT / "docs/research/exp-20260921-factor-round-f3r3-prereg.md"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
_win = os.environ.get("F3R3_WINDOW", "full")
SMOKE = _win != "full"
if SMOKE:
    _a, _b = _win.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
else:
    WIN_START, WIN_END = DEV_START, DEV_END

ARMS = ["F3-EW", "F3-ICW"]
K = 10
ENGINE_SHA_EXPECT_16 = "d4b6c3764780e6de"
F3R1_REPS = ["A17", "A20", "A25", "B11", "B12", "B14", "C19", "D08", "D09",
             "D10", "D14", "D18", "D19", "D20", "D21", "D25", "E16", "F02",
             "F06", "F09"]
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
BUDGET_S = 3600.0 if not SMOKE else 900.0
PEAK_RSS = 0.0
LOG_PATH = RUN_DIR / "logs" / "runner.log"
LOG_LINES: list[str] = []
_logf = LOG_PATH.open("a", encoding="utf-8")


def log(msg: object) -> None:
    global PEAK_RSS
    line = f"[{time.perf_counter() - T0:7.1f}s] {msg}"
    LOG_LINES.append(str(line))
    _logf.write(line + "\n")
    _logf.flush()
    print(line, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rss_gb() -> float:
    global PEAK_RSS
    try:
        import psutil
        v = psutil.Process().memory_info().rss / 1e9
        PEAK_RSS = max(PEAK_RSS, v)
        return v
    except Exception:
        return float("nan")


def check_budget(what: str) -> None:
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name,
        "experiment_id": "exp-20260921-factor-round-f3r3",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


log(f"F3R3 dynamic-engine rerun; window={WIN_START}..{WIN_END}"
    f"{' (SMOKE)' if SMOKE else ''}")

# === 0. identity pins ========================================================
log("== 0. identity pins ==")
pins: dict = {}
engine_got = sha256_file(ENGINE_PY)
pins["engine"] = {"path": str(ENGINE_PY), "sha256": engine_got,
                  "expected_16": ENGINE_SHA_EXPECT_16,
                  "match": engine_got.startswith(ENGINE_SHA_EXPECT_16)}
if not pins["engine"]["match"]:
    _fail(f"engine pin mismatch: {engine_got[:16]}")
pins["prereg"] = {"path": str(PREREG), "sha256": sha256_file(PREREG)}
halfday_manifest = HALFDAY_DIR / "manifest.json"
hm = sha256_file(halfday_manifest)
pins["halfday_manifest"] = {"path": str(halfday_manifest), "sha256": hm,
                            "match": hm.startswith("2a414174b5df2eee")}
if not pins["halfday_manifest"]["match"]:
    _fail("halfday manifest pin mismatch")
stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {
    "path": str(STK_DIR), **stk_agg,
    "match": stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit aggregate pin mismatch")
for name, p in [("daily", DAILY_PARQUET),
                ("split_factor", BUNDLE / "split_factor.h5"),
                ("dividends", BUNDLE / "dividends.h5")]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
log(f"  engine {engine_got[:16]} OK (rebuilt dynamic engine); pins OK; "
    f"python {platform.python_version()} | rss {rss_gb():.2f} GB")

# === 1. calendar & signal days ===============================================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= WIN_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
hi = min(WIN_END, DEV_END)
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= hi]
assert sig_days, "no signal days in window"
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})")

# === 2. R16 pool verbatim ====================================================
log("== 2. R16 pool (build_history + signal_pools, verbatim) ==")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_sizes = {t: pools_at[t]["n"] for t in sig_days}
log(f"  pool n: min {min(pool_sizes.values())} max {max(pool_sizes.values())}")
check_budget("pools")

# === 3. dedup ================================================================
log("== 3. dedup: |rho|>=0.6 connected components, rep = max |t| ==")
corr = pl.read_csv(F2R1 / "f2r1_survivors_corr.csv")
all120 = pl.read_csv(F2R1 / "f2r1_all120.csv")
surv = all120.filter(pl.col("screen_pass"))
assert surv.height == 43, f"expected 43 survivors, got {surv.height}"
stats = {r["factor_id"]: r for r in surv.iter_rows(named=True)}
ids = corr["factor"].to_list()
assert sorted(ids) == sorted(stats), "corr matrix ids != survivor ids"
mat = {r["factor"]: [float(r[c]) if r[c] is not None else np.nan for c in ids]
       for r in corr.iter_rows(named=True)}
adj: dict[str, set[str]] = {i: set() for i in ids}
for i in ids:
    for j in ids:
        if i != j and abs(mat[i][ids.index(j)]) >= 0.6:
            adj[i].add(j)
seen: set[str] = set()
clusters: list[list[str]] = []
for i in ids:
    if i in seen:
        continue
    comp, stack = [], [i]
    seen.add(i)
    while stack:
        x = stack.pop()
        comp.append(x)
        for y in adj[x]:
            if y not in seen:
                seen.add(y)
                stack.append(y)
    clusters.append(sorted(comp))
reps: list[str] = []
cluster_table = []
for comp in clusters:
    rep = sorted(comp, key=lambda f: (-abs(stats[f]["t_ic"]),
                                      -stats[f]["coverage"], f))[0]
    reps.append(rep)
    cluster_table.append({"representative": rep, "members": comp,
                          "size": len(comp)})
reps = sorted(reps)
M = len(reps)
if reps != F3R1_REPS:
    _fail(f"dedup representatives differ from F3R1: {reps}")
log(f"  {len(clusters)} clusters, {M} representatives == F3R1 list OK")
min_cov = -(-M // 2)
for fid in reps:
    p = F2R1 / FAMILY_DIR[fid[0]] / f"{fid}.parquet"
    pins[f"rep_{fid}"] = {"path": str(p), "sha256": sha256_file(p)}
pins["corr_matrix"] = {"path": str(F2R1 / "f2r1_survivors_corr.csv"),
                       "sha256": sha256_file(F2R1 / "f2r1_survivors_corr.csv")}
pins["all120"] = {"path": str(F2R1 / "f2r1_all120.csv"),
                  "sha256": sha256_file(F2R1 / "f2r1_all120.csv")}

# === 4. composite ============================================================
log("== 4. composite: EW + ICW arms on executable cross-sections ==")
frames: dict[str, pl.DataFrame] = {}
for fid in reps:
    f = pl.read_parquet(F2R1 / FAMILY_DIR[fid[0]] / f"{fid}.parquet")
    f = f.filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
    frames[fid] = f
import json as _json  # noqa: E402
icir_of: dict[str, float] = {}
for fid in reps:
    jp = F2R1 / FAMILY_DIR[fid[0]] / f"{fid}.json"
    j = _json.loads(jp.read_text(encoding="utf-8"))
    icir_of[fid] = float(j["eval"]["icir"])
    t_json = j["screen"]["t_ic"] if "screen" in j else None
    if t_json is not None and abs(t_json - stats[fid]["t_ic"]) > 5.001e-3:
        _fail(f"{fid}: t_ic mismatch json {t_json} vs all120 {stats[fid]['t_ic']}")
weights = {fid: abs(icir_of[fid]) for fid in reps}
signs = {fid: 1.0 if float(stats[fid]["ic_mean"]) > 0 else -1.0
         for fid in reps}

pool_ranked = {t: pools_at[t]["ranked"] for t in sig_days}
pool_set = {t: set(pool_ranked[t]) for t in sig_days}
wide = None
for fid in reps:
    f = frames[fid].rename({"value": fid})
    wide = f if wide is None else wide.join(f, on=["symbol", "signal_date"],
                                            how="full", coalesce=True)
assert wide is not None
wide = wide.filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
log(f"  wide frame {wide.height} rows, {wide['symbol'].n_unique()} symbols")

eligible: dict[date, list[str]] = {}
composite: dict[str, dict[date, dict[str, float]]] = {a: {} for a in ARMS}
comp_rows: dict[str, list[dict]] = {a: [] for a in ARMS}
for t in sig_days:
    g = wide.filter(pl.col("signal_date") == t)
    have = g.with_columns(
        sum(pl.col(f).is_not_null().cast(pl.Int8) for f in reps).alias("_n"))
    have = (have.filter(pl.col("symbol").is_in(pl.Series(sorted(pool_set[t]))))
            .filter(pl.col("_n") >= min_cov))
    elig = have["symbol"].to_list()
    eligible[t] = sorted(elig)
    for a in ARMS:
        composite[a][t] = {}
    with_parts = have
    for fid in reps:
        with_parts = with_parts.with_columns(
            ((pl.col(fid).rank(method="average") - 1.0)
             / pl.max_horizontal(pl.col(fid).count() - 1.0, 1))
            .alias(f"_p_{fid}"))
    parts = {fid: {r["symbol"]: (r[f"_p_{fid}"] - 0.5) * signs[fid]
                   if r[f"_p_{fid}"] is not None else None
                   for r in with_parts.iter_rows(named=True)}
             for fid in reps}
    for sym in elig:
        num_ew, den_ew, num_ic, den_ic = 0.0, 0, 0.0, 0.0
        for fid in reps:
            v = parts[fid].get(sym)
            if v is None:
                continue
            num_ew += v
            den_ew += 1
            num_ic += weights[fid] * v
            den_ic += weights[fid]
        if den_ew == 0:
            continue
        composite["F3-EW"][t][sym] = num_ew / den_ew
        composite["F3-ICW"][t][sym] = num_ic / den_ic
        comp_rows["F3-EW"].append({"symbol": sym, "signal_date": t,
                                   "value": num_ew / den_ew})
        comp_rows["F3-ICW"].append({"symbol": sym, "signal_date": t,
                                    "value": num_ic / den_ic})
    if len(sig_days) < 6 or t in (sig_days[0], sig_days[len(sig_days) // 2],
                                  sig_days[-1]):
        log(f"  {t}: pool {pool_sizes[t]} -> eligible {len(elig)}")
check_budget("composite")

# === 5. provider factories (replaces F3R1 static frames) ====================
log("== 5. intent providers: seat re-issue from live ledger ==")
ranked_f3: dict[str, dict[date, list[str]]] = {}
members_hist: dict[str, dict[date, list[str]]] = {}
for arm in ARMS:
    ranked_f3[arm] = {}
    for t in sig_days:
        ranked_f3[arm][t] = sorted(
            eligible[t], key=lambda s: (-composite[arm][t].get(s, -9e9), s))
sig_sorted = sorted(sig_days)


def sig_eff(day: date, sess: str) -> date | None:
    """Effective signal: latest T' with T' < day or (T' == day and pm)."""
    idx = bisect_left(sig_sorted, day)
    if idx < len(sig_sorted) and sig_sorted[idx] == day:
        return day if sess == "pm" else (sig_sorted[idx - 1] if idx else None)
    return sig_sorted[idx - 1] if idx else None


def make_provider(arm: str):
    members_by_t = {t: set(members_hist[arm][t]) for t in sig_days}
    rank_by_t = {t: {s: i + 1 for i, s in enumerate(ranked_f3[arm][t])}
                 for t in sig_days}
    seats: dict[tuple[str, str, date], dict] = {}
    calls = {"n": 0, "buy_rows": 0, "sell_rows": 0}

    def provider(day: date, sess: str, ledger: dict) -> list[dict] | None:
        calls["n"] += 1
        T = sig_eff(day, sess)
        if T is None:
            return None
        members = members_by_t[T]
        rank_of = rank_by_t[T]
        held = {p["symbol"] for p in ledger["positions"]}
        rows: list[dict] = []
        for sym in sorted(members - held):
            Tp = next_sig.get(T)
            expiry = date.fromordinal(Tp.toordinal() + 1)
            rows.append({
                "symbol": sym, "side": "buy", "intent": "",
                "decision_date": day, "decision_session": sess,
                "source_signal": T, "priority": rank_of[sym],
                "expiry_date": expiry, "target_weight": 0.10})
            k = (sym, "buy", T)
            st = seats.setdefault(k, {"n_sent": 0})
            st["n_sent"] += 1
            calls["buy_rows"] += 1
        for sym in sorted(held - members):
            if (sym, "sell", T) in seats:
                continue    # engine-side m3 carry owns intra-month retries
            Tp = next_sig.get(T)
            expiry = date.fromordinal(Tp.toordinal() + 1)
            rows.append({
                "symbol": sym, "side": "sell", "intent": "risk",
                "decision_date": day, "decision_session": sess,
                "source_signal": T, "priority": 10**6,
                "expiry_date": expiry, "target_weight": None})
            seats[(sym, "sell", T)] = {"n_sent": 1}
            calls["sell_rows"] += 1
        return rows or None

    return provider, seats, calls


for arm in ARMS:
    members_hist[arm] = {}
    prev: list[str] = []
    for t in sig_days:
        members, _info = r16.buffer_membership(
            prev, ranked_f3[arm][t], {}, K, False)
        members_hist[arm][t] = members
        prev = members
    n_members = [len(members_hist[arm][t]) for t in sig_days]
    log(f"  {arm}: members/month min {min(n_members)} max {max(n_members)}")
check_budget("providers")

# === 6. benchmarks (full mode only) ==========================================
b1m = None
B3P = None
b3_cagrs: list[float] = []
if not SMOKE:
    log("== 6. benchmarks: B1(m)_F3 fractional + B3'_F3 random K=10 ==")
    pools_f3 = {t: {"ranked": list(ranked_f3["F3-EW"][t]), "q5": {},
                    "n": len(ranked_f3["F3-EW"][t])} for t in sig_days}
    bank_syms = sorted({s for t in sig_days for s in pools_f3[t]["ranked"]})
    bank = r16.PriceBank(hist, calendar_full, bank_syms)
    exposures = {t: 1.0 for t in sig_days}
    b1_sim = r16.simulate_r16(
        "B1m-F3-DEV", bank, calendar_full, DEV_START, sig_days, pools_f3,
        exposures, K=0, fractional=True, fee_bands=r16.B1_FEE_SCHEDULE_RATE_ONLY)
    b1m = r16.segment_metrics(b1_sim, DEV_START, DEV_END, None, fractional=True)
    log(f"  B1(m)_F3: net {b1m['net_cagr']*100:+.2f}% "
        f"mdd {b1m['max_drawdown']*100:.2f}% ({len(bank_syms)} union symbols)")
    for seed in r16.B3_SEEDS:
        sim = r16.simulate_r16(
            f"B3p-F3-s{seed}", bank, calendar_full, DEV_START, sig_days,
            pools_f3, exposures, K=K, fractional=False,
            membership_fn=lambda p, r_, q, rng, _K=K: r16.random_membership(
                p, r_, q, rng, _K),
            seed=seed, fee_bands=r16.STOCK_FEE_SCHEDULE)
        m = r16.segment_metrics(sim, DEV_START, DEV_END, None, fractional=False)
        b3_cagrs.append(m["net_cagr"])
    B3P = float(np.mean(b3_cagrs))
    log(f"  B3'_F3: mean net {B3P*100:+.2f}% "
        f"(seeds 17..36, range {min(b3_cagrs)*100:+.2f}..{max(b3_cagrs)*100:+.2f}%)")
    del bank, b1_sim
    check_budget("benchmarks")

# === 7. band engine market frames ============================================
log("== 7. band engine market frames ==")
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
pins["daily"].update({"rows_total": daily_meta["rows_total"],
                      "rows_after_freeze_filter":
                          daily_meta["rows_after_freeze_filter"]})
_union_syms = sorted({s for arm in ARMS
                      for t in sig_days for s in members_hist[arm][t]})
daily = (daily_full.filter(pl.col("symbol").is_in(_union_syms))
         .filter((pl.col("date") >= WIN_START) & (pl.col("date") <= WIN_END))
         .select("symbol", "date", "open", "high", "low", "close", "tradestatus")
         .sort("symbol", "date"))
del daily_full
assert_frozen(daily, "date", "daily")
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
half_parts = []
for part in parts:
    f = pl.read_parquet(part)
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= WIN_START)
                 & (pl.col("trade_date") <= WIN_END))
    f = f.filter(pl.col("symbol").is_in(_union_syms))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame()
del half_parts
assert_frozen(half, "trade_date", "halfday")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})
limits = (limits_full.filter(pl.col("symbol").is_in(_union_syms))
          .filter((pl.col("date") >= WIN_START) & (pl.col("date") <= WIN_END))
          .sort("symbol", "date"))
del limits_full
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(_union_syms))
dividends = divs_all.filter(pl.col("symbol").is_in(_union_syms))
del splits_all, divs_all
instruments = pl.DataFrame({"symbol": _union_syms,
                            "is_etf": [False] * len(_union_syms),
                            "is_t0": [False] * len(_union_syms)})
log(f"  frames: panel {len(_union_syms)} symbols; daily {daily.height}; "
    f"half {half.height}; limits {limits.height}; rss {rss_gb():.2f} GB")
check_budget("market frames")


def _dints(col: pl.Series) -> np.ndarray:
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


_trading = (daily.filter(pl.col("tradestatus") != 0)
            if "tradestatus" in daily.columns else daily)
close_arr = {}
for (sym,), g in _trading.partition_by("symbol", as_dict=True).items():
    dint = _dints(g["date"])
    close_arr[sym] = (dint.astype(np.int64),
                      g["close"].to_numpy().astype(np.float64))

split_events: dict[str, list[tuple[date, float]]] = {}
for r in splits.filter(pl.col("ex_date") <= WIN_END).iter_rows(named=True):
    split_events.setdefault(r["symbol"], []).append(
        (r["ex_date"], float(r["split_factor"])))
for v in split_events.values():
    v.sort()

# === 8. engine runs (dynamic halfday clock) ==================================
log("== 8. band engine dynamic intent runs (halfday clock) ==")
results: dict = {}
PROVIDERS: dict = {}
for arm in ARMS:
    syms = sorted({s for t in sig_days for s in members_hist[arm][t]})
    daily_c = daily.filter(pl.col("symbol").is_in(syms))
    half_c = half.filter(pl.col("symbol").is_in(syms))
    limits_c = limits.filter(pl.col("symbol").is_in(syms))
    splits_c = splits.filter(pl.col("symbol").is_in(syms))
    divs_c = dividends.filter(pl.col("symbol").is_in(syms))
    instr_c = instruments.filter(pl.col("symbol").is_in(syms))
    provider, seats, calls = make_provider(arm)
    PROVIDERS[arm] = {"seats": seats, "calls": calls}
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(
        None, daily_c, half_c, limits_c, splits_c, divs_c, instr_c,
        initial_cash=200_000.0, execution_clock="halfday",
        intent_provider=provider)
    wall = time.perf_counter() - t_cfg
    dl = res.stats.get("dynamic_layer") or {}
    il = res.stats.get("intent_layer") or {}
    log(f"  {arm}: engine {wall:.1f}s; provider calls {dl.get('provider_calls')} "
        f"injected {dl.get('dynamic_injected')} "
        f"(buy {calls['buy_rows']} sell {calls['sell_rows']}); "
        f"orders {il.get('orders_generated')} filled {il.get('stopped_filled')} "
        f"expired_halfday {il.get('terminated_expired_halfday')} "
        f"no_anchor {il.get('terminated_expired_halfday_no_anchor')} "
        f"override {il.get('terminated_override')} | rss {rss_gb():.2f} GB")
    if dl.get("dynamic_injected") != calls["buy_rows"] + calls["sell_rows"]:
        _fail(f"{arm}: provider rows {calls['buy_rows'] + calls['sell_rows']} "
              f"!= engine dynamic_injected {dl.get('dynamic_injected')}")
    results[arm] = {"res": res, "wall_s": wall, "warnings": list(res.warnings)}
    check_budget(f"{arm} engine run")

# === 9. seat-signal attribution (7.7-m6 adapted to dynamic mode) =============
log("== 9. seat-signal attribution ==")
RULE_OK = {"below_min_lot", "void_no_position", "void_insufficient_cash"}


def attribute(arm: str) -> dict:
    res = results[arm]["res"]
    seats = PROVIDERS[arm]["seats"]
    seat_syms = {sym for (sym, _s, _t) in seats}

    def seat_of(sym: str, sclass: str, d, s: str):
        best = None
        for (y, sc, T) in seats:
            if y != sym or sc != sclass:
                continue
            if T < d or (T == d and s == "pm"):
                if best is None or T > best:
                    best = T
        return best

    fills = res.fills
    filled_seats: set = set()
    if fills.height:
        for r in fills.select("symbol", "side", "decision_date",
                              "decision_session").iter_rows(named=True):
            sclass = "buy" if r["side"] == "buy" else "sell"
            T = seat_of(r["symbol"], sclass, r["decision_date"],
                        r["decision_session"])
            if T is not None:
                filled_seats.add((r["symbol"], sclass, T))
    ev_orders = res.events.filter(pl.col("order_id") != "")
    seat_events: dict = {}
    for r in ev_orders.iter_rows(named=True):
        parts_ = r["order_id"].rsplit("-", 4)
        if len(parts_) != 5:
            _fail(f"{arm}: unparsable order_id {r['order_id']!r}")
        prefix, y, mo, dy, sess = parts_
        sym, sidestr = prefix.split("-", 1)
        sclass = "buy" if sidestr.startswith("buy") else "sell"
        d = date(int(y), int(mo), int(dy))
        T = seat_of(sym, sclass, d, sess)
        if T is not None:
            seat_events.setdefault((sym, sclass, T), []).append(r["event"])
    n_filled = n_rule = n_term = 0
    rule_blocked_detail = {k: 0 for k in RULE_OK}
    outcome_by_seat: dict = {}
    for k in seats:
        if k in filled_seats:
            outcome_by_seat[k] = "filled"
            n_filled += 1
            continue
        evs = seat_events.get(k, [])
        if evs and all(e in RULE_OK for e in evs):
            outcome_by_seat[k] = "executed_rule_blocked:" + evs[-1]
            rule_blocked_detail[evs[-1]] += 1
            n_rule += 1
        else:
            outcome_by_seat[k] = "terminated:expired_seat"
            n_term += 1
    total = n_filled + n_rule + n_term
    mapped = (n_filled + n_rule) / total if total else None
    return {"outcome_by_seat": outcome_by_seat,
            "mapped_rate": mapped, "n_filled": n_filled,
            "n_rule_blocked": n_rule, "n_terminated": n_term,
            "n_seats": total, "rule_blocked": dict(rule_blocked_detail),
            "seat_symbols": len(seat_syms),
            "intent_layer": res.stats["intent_layer"],
            "dynamic_layer": res.stats.get("dynamic_layer")}


attr: dict = {}
for arm in ARMS:
    attr[arm] = attribute(arm)
    a = attr[arm]
    log(f"  {arm}: seats {a['n_seats']} (filled {a['n_filled']}, "
        f"rule-blocked {a['n_rule_blocked']} {a['rule_blocked']}, "
        f"expired-seat {a['n_terminated']}); mapped "
        f"{(a['mapped_rate'] or 0)*100:.1f}%")
check_budget("attribution")


def daily_max_single_name_weight(res) -> float:
    dates = res.daily["date"].to_list()
    eq_list = res.daily["equity"].to_list()
    per: dict = {}
    for r in res.fills.select("symbol", "date", "side", "shares") \
                     .iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    sp_by = {sym: sorted((dint_of(ed), f) for ed, f in evs)
             for sym, evs in split_events.items()}
    import math
    state: dict = {}
    wmax = 0.0
    for d, e in zip(dates, eq_list):
        td = dint_of(d)
        if e <= 0:
            continue
        for sym, evs in per.items():
            st = state.get(sym)
            if st is None:
                st = [0, 0, 0]
                state[sym] = st
            pos, i, si = st
            sp = sp_by.get(sym, [])
            while si < len(sp) and sp[si][0] <= td:
                pos = int(math.floor(pos * sp[si][1] + 0.5))
                si += 1
            while i < len(evs) and evs[i][0] <= td:
                ev = evs[i]
                while si < len(sp) and sp[si][0] <= ev[0]:
                    pos = int(math.floor(pos * sp[si][1] + 0.5))
                    si += 1
                pos += ev[2] if ev[1] == "buy" else -ev[2]
                i += 1
            st[0], st[1], st[2] = pos, i, si
            if pos > 0:
                px = close_le(sym, d)
                if px and px > 0 and pos * px / e > wmax:
                    wmax = pos * px / e
    return wmax


def close_le(sym: str, d: date) -> float | None:
    arr = close_arr.get(sym)
    if arr is None:
        return None
    dint, cls = arr
    i = int(np.searchsorted(dint, dint_of(d), side="right")) - 1
    return float(cls[i]) if i >= 0 else None


# === 10. metrics & gates (full mode only) ====================================
metrics: dict = {}
gates: dict = {}
if not SMOKE:
    log("== 10. metrics & eight gates + goal criterion ==")
    b1y_ref = {int(k): v for k, v in b1m["net_return_by_year"].items()}
    for arm in ARMS:
        res = results[arm]["res"]
        sd, sv = er.slice_curve(res.daily["date"].to_list(),
                                res.daily["equity"].to_list(),
                                DEV_START, DEV_END)
        net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
        mdd = er.max_drawdown(sd, sv)["max_drawdown"]
        yr = er.year_returns(sd, sv)
        adv = sorted(y for y in yr if y in b1y_ref and yr[y] > b1y_ref[y])
        excess = net_cagr - b1m["net_cagr"]
        df = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
        mean_eq = {int(r["yy"]): r["equity"] for r in
                   df.group_by("yy").agg(pl.col("equity").mean()).iter_rows(named=True)}
        if res.fills.height:
            buy_by = {int(r["yy"]): r["n"] for r in
                      res.fills.filter(pl.col("side") == "buy")
                      .with_columns(pl.col("date").dt.year().alias("yy"))
                      .group_by("yy").agg(pl.col("notional").sum().alias("n"))
                      .iter_rows(named=True)}
        else:
            buy_by = {}
        tby = {y: {"buy_notional": buy_by.get(y, 0.0), "mean_equity": mean_eq[y],
                   "one_side_turnover": buy_by.get(y, 0.0) / mean_eq[y]}
               for y in sorted(mean_eq)}
        wmax = daily_max_single_name_weight(res)
        a = attr[arm]
        m = {"net_cagr": net_cagr,
             "net_total_return": sv[-1] / sv[0] - 1.0,
             "max_drawdown": mdd,
             "b1m_net_cagr": b1m["net_cagr"],
             "b1m_max_drawdown": b1m["max_drawdown"],
             "b1m_net_return_by_year": b1m["net_return_by_year"],
             "excess_vs_b1m": excess,
             "net_return_by_year": {int(k): v for k, v in yr.items()},
             "advantage_years_list": [int(y) for y in adv],
             "turnover_by_year": tby,
             "max_one_side_turnover": max(v["one_side_turnover"]
                                          for v in tby.values()),
             "max_single_name_weight": wmax,
             "execution_rate": a["mapped_rate"],
             "execution_rate_mapping":
                 "F3R3 seat-signal: (filled + rule-blocked seats) / all "
                 "seats; dynamic re-issues within a seat collapse to one seat",
             "b3prime_mean_net_cagr": B3P}
        g = {"1_net_cagr_gt_0": net_cagr > 0,
             "2_excess_vs_B1m_ge_2pp": excess >= 0.020,
             "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y_ref) == 6,
             "4_mdd_le_20pct_and_le_B1m":
                 abs(mdd) <= 0.20 + 1e-12
                 and abs(mdd) <= abs(b1m["max_drawdown"]) + 1e-12,
             "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,
             "6_single_name_weight_le_40pct": wmax <= 0.40,
             "7_vs_B3prime_plus_1pp": net_cagr >= B3P + 0.010,
             "8_execution_rate_ge_95pct": (a["mapped_rate"] or 0.0) >= 0.95,
             "advantage_years": len(adv), "dev_excess_vs_b1m": excess}
        gate_keys = ["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",
                     "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",
                     "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",
                     "7_vs_B3prime_plus_1pp", "8_execution_rate_ge_95pct"]
        g["failed_gates"] = sorted(k for k in gate_keys if not g[k])
        g["dev_pass"] = not g["failed_gates"]
        g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"
        g["goal_criterion_dev_cagr_ge_10pct"] = net_cagr >= 0.10
        g["goal_met"] = g["dev_pass"] and g["goal_criterion_dev_cagr_ge_10pct"]
        metrics[arm] = m
        gates[arm] = {"dev": g, "verdict": g["verdict"]}
        log(f"  {arm}: net {net_cagr*100:+.2f}% excess {excess*100:+.2f}pp "
            f"adv {len(adv)}/6 mdd {mdd*100:.2f}% turn "
            f"{m['max_one_side_turnover']:.2f} w {wmax*100:.1f}% exec "
            f"{(a['mapped_rate'] or 0)*100:.1f}% -> "
            f"{'PASS' if g['dev_pass'] else 'eliminated ' + str(g['failed_gates'])}; "
            f"goal>=10% {'MET' if g['goal_criterion_dev_cagr_ge_10pct'] else 'not met'}")
    n_pass = sum(1 for arm in ARMS if gates[arm]["dev"]["dev_pass"])
    log(f"== gates: {n_pass}/{len(ARMS)} dev_pass ==")
    check_budget("metrics & gates")

# === 11. outputs =============================================================
log("== 11. outputs ==")
out_dir = RUN_DIR / "outputs"
for arm in ARMS:
    res = results[arm]["res"]
    res.fills.write_parquet(out_dir / f"{arm}_fills.parquet")
    res.events.write_parquet(out_dir / f"{arm}_events.parquet")
    res.daily.write_parquet(out_dir / f"{arm}_daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / f"{arm}_clips_final.parquet")
    pl.DataFrame(comp_rows[arm],
                 schema={"symbol": pl.String, "signal_date": pl.Date,
                         "value": pl.Float64}).write_parquet(
        out_dir / f"{arm}_composite.parquet")
    pl.DataFrame([{"symbol": s, "sclass": sc, "source_signal": str(T),
                   "outcome": o, "n_sent": PROVIDERS[arm]["seats"]
                   [(s, sc, T)]["n_sent"]}
                  for (s, sc, T), o in attr[arm]["outcome_by_seat"].items()]
                 ).sort("source_signal", "sclass", "symbol").write_csv(
        out_dir / f"{arm}_seat_outcomes.csv")
pl.DataFrame([{**c, "members": "|".join(c["members"])} for c in cluster_table]
             ).write_csv(out_dir / "dedup_clusters.csv")
pl.DataFrame([{"signal_date": t, "pool_n": pool_sizes[t],
               "eligible_n": len(eligible[t])} for t in sig_days]
             ).write_csv(out_dir / "pool_sizes.csv")

if not SMOKE:
    mg = {
        "experiment_id": "exp-20260921-factor-round-f3r3",
        "engine_sha256_16": engine_got[:16],
        "execution_model": "rebuilt band engine, execution_clock='halfday', "
                           "intent_provider seat re-issue from live ledger; "
                           "no static frame; seat vacancy removed",
        "dedup": {"rho_threshold": 0.6, "clusters": len(clusters),
                  "representatives": reps, "cluster_table": cluster_table,
                  "min_components_required": min_cov,
                  "reps_match_f3r1": True},
        "benchmarks": {
            "b1m": {k: b1m[k] for k in ("net_cagr", "max_drawdown",
                                        "net_return_by_year")},
            "b3prime": {"mean_net_cagr": B3P, "seeds": list(r16.B3_SEEDS),
                        "k": K, "per_seed_net_cagr": b3_cagrs}},
        "metrics": metrics, "gates": gates,
        "disclosures": {
            arm: {
                "seat_attribution": {
                    "seats": attr[arm]["n_seats"],
                    "filled": attr[arm]["n_filled"],
                    "rule_blocked": attr[arm]["rule_blocked"],
                    "expired_seat": attr[arm]["n_terminated"],
                    "mapped_rate": attr[arm]["mapped_rate"]},
                "dynamic_layer": attr[arm]["dynamic_layer"],
                "intent_layer": attr[arm]["intent_layer"],
                "seat_vacancy_removed": True,
                "no_midcycle_rebalance": True,
                "engine_warnings_n": len(results[arm]["warnings"]),
                "engine_warnings_sample": results[arm]["warnings"][:3],
            } for arm in ARMS},
        "val_consumed": False,
        "stop_note": ("STOP: >=1 arm passed all dev gates; val requires "
                      "separate user approval"
                      if any(gates[a]["dev"]["dev_pass"] for a in ARMS) else
                      "no arm passed all dev gates; val not consumed"),
    }
    (out_dir / "metrics_and_gates.json").write_text(
        json.dumps(mg, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    rep = ["# F3R3 动态引擎因子组合重测：两臂八门判定（dev）", "",
           f"- 运行 `{RUN_DIR.name}`；重建引擎 sha256:16 `{engine_got[:16]}`；"
           "预登记 `docs/research/exp-20260921-factor-round-f3r3-prereg.md`（运行前冻结）。",
           f"- 组合与 F3R1 完全一致：43 存活 → {len(clusters)} 簇 → {M} 代表；"
           "差异仅在执行模型（半日时钟 + provider 席位重发，席位置空取消）。",
           f"- 信号 {sig_days[0]}..{sig_days[-1]}（{len(sig_days)} 个月末）；"
           "val 2021–2024 零接触。全部数字为历史回放，不构成盈利声称。", "",
           "## 八门判定表", "",
           "| 臂 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤 | 换手 | 单票max | "
           "门8成交率 | B3′ | 过/8 | 失败门 | ≥10%目标 | 判定 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        m, g = metrics[arm], gates[arm]["dev"]
        rep.append(
            f"| {arm} | {m['net_cagr']*100:+.2f}% | {m['b1m_net_cagr']*100:+.2f}% "
            f"| {m['excess_vs_b1m']*100:+.2f}pp | {g['advantage_years']}/6 "
            f"| {m['max_drawdown']*100:.2f}% | {m['max_one_side_turnover']:.2f} "
            f"| {m['max_single_name_weight']*100:.1f}% "
            f"| {(m['execution_rate'] or 0)*100:.1f}% "
            f"| {B3P*100:+.2f}% | {8 - len(g['failed_gates'])} "
            f"| {', '.join(g['failed_gates']) or '-'} "
            f"| {'MET' if g['goal_criterion_dev_cagr_ge_10pct'] else 'not met'} "
            f"| {'**dev_pass**' if g['dev_pass'] else 'eliminated'} |")
    rep += ["", f"## 判定：{mg['stop_note']}", "",
            "## 与 F3R1（旧引擎）的对照", "",
            "| 臂 | F3R1 净CAGR | F3R3 净CAGR | F3R1 门8 | F3R3 门8 |",
            "|---|---|---|---|---|"]
    f3r1_ref = {"F3-EW": {"net": 9.47, "exec": 74.9},
                "F3-ICW": {"net": 15.28, "exec": 76.7}}
    for arm in ARMS:
        rep.append(
            f"| {arm} | {f3r1_ref[arm]['net']:+.2f}% "
            f"| {metrics[arm]['net_cagr']*100:+.2f}% "
            f"| {f3r1_ref[arm]['exec']:.1f}% "
            f"| {(metrics[arm]['execution_rate'] or 0)*100:.1f}% |")
    rep += ["", "注：F3R1 数字来自 "
            "`artifacts/runs/20260920T190500-f3r1-rebuild/`（旧引擎 v1.3 静态帧）。",
            "", "## 座位归因", ""]
    for arm in ARMS:
        a = attr[arm]
        rep.append(
            f"- **{arm}**：座位 {a['n_seats']}（成交 {a['n_filled']}、"
            f"规则阻断 {a['n_rule_blocked']} {a['rule_blocked']}、"
            f"过期空座 {a['n_terminated']}）；动态层 "
            f"{a['dynamic_layer']}。")
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")
else:
    rep = ["# F3R3 冒烟（工程链路验证，非研究结论）", "",
           f"- 运行 `{RUN_DIR.name}`；窗 {WIN_START}..{WIN_END}；"
           "基准与门判定按预登记跳过。", ""]
    for arm in ARMS:
        a = attr[arm]
        res = results[arm]["res"]
        rep.append(
            f"- {arm}：座位 {a['n_seats']}（成交 {a['n_filled']}、"
            f"规则阻断 {a['n_rule_blocked']}、过期 {a['n_terminated']}）；"
            f"fills {res.fills.height}；引擎动态层 {a['dynamic_layer']}。")
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

# manifest
engine_sha_at_end = sha256_file(ENGINE_PY)
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json", "runner.log"):
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-factor-round-f3r3",
    "status": "completed",
    "mode": "smoke" if SMOKE else "full",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                "artifacts/runs/" + RUN_DIR.name + "/tmp/runner_f3r3.py"],
    "random_seed": ("B3' seeds 17..36 (r16.B3_SEEDS); no other RNG"
                    if not SMOKE else "none (smoke skips benchmarks)"),
    "engine": {"path": str(ENGINE_PY), "sha256_at_start": engine_got,
               "sha256_at_end": engine_sha_at_end,
               "version": "rebuilt dynamic (v1.4.x)",
               "execution_clock": "halfday", "corporate_actions": None},
    "pins": pins,
    "config": json.loads(CONFIG.read_text(encoding="utf-8")),
    "signal_days": [str(d) for d in sig_days],
    "cluster_table": cluster_table,
    "representatives": reps,
    "trial_accounting": {"strategy_line": {"before": 264, "this_round": 2,
                                           "after": 266},
                         "factor_line": "no new trials (FT-01 unchanged)"},
    "gates_dev_pass": ([arm for arm in ARMS
                        if gates[arm]["dev"]["dev_pass"]]
                       if not SMOKE else "skipped (smoke)"),
    "advanced_to_validation": False,
    "val_consumed": False,
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== manifest + report written; wall {time.perf_counter()-T0:.0f}s, "
    f"peak rss {PEAK_RSS:.2f} GB ==")
_logf.close()
