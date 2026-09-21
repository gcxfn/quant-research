# -*- coding: utf-8 -*-
"""F3R1 factor-combination runner (prereg exp-20260919-factor-round-f3r1, frozen).

Pipeline (single deterministic run, no RNG except seeded B3' draws):
 0. identity pins: engine v1.3, panels, F2R1 survivor frames, corr matrix
 1. calendar + month-end signal days (P3R2 precedent: 2020-12-31 dropped
    as signal, kept as expiry anchor)
 2. R16 pool verbatim (build_history_r16 + signal_pools)
 3. dedup: |rho|>=0.6 connected components on the F2R1 survivor corr
    matrix; representative = max |t_ic| (ties: coverage desc, id lex)
 4. composite: executable cross-section = R16 pool INTERSECTION coverage
    (>= ceil(M/2) reps non-null); component = (rank_pct-0.5)*sign(ic);
    arms F3-EW (equal weight) and F3-ICW (|icir| weight, pre-run patch)
 5. membership: r16.buffer_membership, K=10, entry top-10, exit rank>20,
    q5 OFF; intents = membership transitions only (buy on entry, sell
    full risk on exit; NO re-emission for sitting seats -- registered
    note: a buy that never fills leaves the seat in cash until the name
    cycles out and back in)
 6. benchmarks on the SAME executable pool via r16.simulate_r16:
    B1(m)_F3 fractional rate-only exposure=1; B3'_F3 random K=10 seeds
    17..36 integer STOCK_FEE_SCHEDULE, mean net CAGR
 7. band engine v1.3 intent runs per arm (initial_cash 200k)
 8. gate-8 attribution (7.7-m6 verbatim), metrics, eight gates verbatim
    (R16 prereg sec 2) + goal-alignment criterion (dev net CAGR >= 10%)
 9. outputs + manifest + report
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
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
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
ARMS = ["F3-EW", "F3-ICW"]
K = 10
ENGINE_SHA_EXPECT_FULL = "31022babbc2858ea27a9142141fba9c14f7361294ea84e4257025ce820aa6076"
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}

T0 = time.perf_counter()
BUDGET_S = 3600.0
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
        "experiment_id": "exp-20260919-factor-round-f3r1",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


# === 0. identity pins ========================================================
log("== 0. identity pins ==")
pins: dict = {}
engine_got = sha256_file(ENGINE_PY)
pins["engine"] = {"path": str(ENGINE_PY), "sha256": engine_got,
                  "expected": ENGINE_SHA_EXPECT_FULL,
                  "match": engine_got == ENGINE_SHA_EXPECT_FULL}
if not pins["engine"]["match"]:
    _fail(f"engine pin mismatch: {engine_got}")
pins["config"] = {"path": str(CONFIG), "sha256": sha256_file(CONFIG)}
pins["daily"] = {"path": str(DAILY_PARQUET), "sha256": sha256_file(DAILY_PARQUET)}
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
for name, p in [("split_factor", BUNDLE / "split_factor.h5"),
                ("dividends", BUNDLE / "dividends.h5")]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
log(f"  engine {engine_got[:16]} OK; data pins OK; "
    f"python {platform.python_version()} | rss {rss_gb():.2f} GB")

# === 1. calendar & signal days ===============================================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
assert sig_days and sig_days[-1] <= date(2020, 11, 30)
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]}); "
    "2020-12-31 dropped as signal (P3R2 precedent)")

# === 2. R16 pool verbatim ====================================================
log("== 2. R16 pool (build_history + signal_pools, verbatim) ==")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_sizes = {t: pools_at[t]["n"] for t in sig_days}
log(f"  pool n: min {min(pool_sizes.values())} max {max(pool_sizes.values())} "
    f"first {sig_days[0]} n={pool_sizes[sig_days[0]]}")
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
log(f"  {len(clusters)} clusters, {M} representatives: {reps}")
for c in sorted(cluster_table, key=lambda c: -c["size"])[:8]:
    log(f"    cluster rep {c['representative']} (size {c['size']}): "
        f"{c['members']}")
min_cov = -(-M // 2)  # ceil(M/2)
log(f"  coverage rule: >= {min_cov}/{M} reps non-null")
# pin every representative frame
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
weights = {fid: abs(float(stats[fid]["icir"])) if "icir" in stats else None
           for fid in reps}
# all120.csv carries t_ic / ic_mean; icir not present -> derive |icir| from
# t and n_dates (t = icir*sqrt(n)) -- prereg reads icir from F2R1 frozen
# evaluation; all120.json per-factor files hold icir. Load from family JSON.
import json as _json  # noqa: E402
icir_of: dict[str, float] = {}
for fid in reps:
    jp = F2R1 / FAMILY_DIR[fid[0]] / f"{fid}.json"
    j = _json.loads(jp.read_text(encoding="utf-8"))
    icir_of[fid] = float(j["eval"]["icir"])
    # cross-check t against all120 (same frozen source family); all120.csv
    # rounds to 2 dp -> half-step tolerance 0.005, not machine epsilon
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
    n_e = len(elig)
    # component rank-percentile within eligible, oriented
    comp_vals: dict[str, dict[str, float]] = {fid: {} for fid in reps}
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
        log(f"  {t}: pool {pool_sizes[t]} -> eligible {n_e}")
elig_sizes = {str(t): len(eligible[t]) for t in sig_days}
log(f"  eligible sizes: min {min(elig_sizes.values())} "
    f"median {int(np.median(list(elig_sizes.values())))} "
    f"max {max(elig_sizes.values())}")
check_budget("composite")

# === 5. membership + intent frames ===========================================
log("== 5. membership (buffer top10/exit>20) + static intent frames ==")
INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "priority": pl.Int64,
    "expiry_date": pl.Date, "target_weight": pl.Float64,
}
ranked_f3: dict[str, dict[date, list[str]]] = {}
members_hist: dict[str, dict[date, list[str]]] = {}
for arm in ARMS:
    ranked_f3[arm] = {}
    for t in sig_days:
        ranked = sorted(eligible[t],
                        key=lambda s: (-composite[arm][t].get(s, -9e9), s))
        ranked_f3[arm][t] = ranked
FRAMES: dict[str, pl.DataFrame] = {}
for arm in ARMS:
    prev: list[str] = []
    rows: list[dict] = []
    members_hist[arm] = {}
    for t in sig_days:
        members, info = r16.buffer_membership(
            prev, ranked_f3[arm][t], {}, K, False)
        members_hist[arm][t] = members
        Tp = next_sig.get(t)
        expiry = (date(Tp.year, Tp.month, Tp.day) if Tp is None else
                  date.fromordinal(Tp.toordinal() + 1))
        rank_of = {s: i + 1 for i, s in enumerate(ranked_f3[arm][t])}
        entered = [s for s in members if s not in prev]
        left = [s for s in prev if s not in members]
        for sym in entered:
            rows.append({"symbol": sym, "side": "buy", "intent": "",
                         "decision_date": t, "decision_session": "pm",
                         "source_signal": t, "priority": rank_of[sym],
                         "expiry_date": expiry,
                         "target_weight": 0.10})
        for sym in left:
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": t, "decision_session": "pm",
                         "source_signal": t, "priority": rank_of.get(sym, 10**6),
                         "expiry_date": expiry, "target_weight": None})
        prev = members
    fr = pl.DataFrame(rows, schema=INTENT_SCHEMA)
    keys = [(r["symbol"], r["side"], r["source_signal"]) for r in rows]
    if len(keys) != len(set(keys)):
        _fail(f"m5-b VIOLATION in {arm}: duplicate (symbol, side, source)")
    FRAMES[arm] = fr
    n_buy = int((fr["side"] == "buy").sum())
    n_sell = int((fr["side"] == "sell").sum())
    n_members = [len(members_hist[arm][t]) for t in sig_days]
    log(f"  {arm}: {fr.height} intents (buy {n_buy}, sell {n_sell}); "
        f"members/month min {min(n_members)} max {max(n_members)}; "
        f"m5-b PASS")
check_budget("intent frames")

# === 6. benchmarks on the executable pool ====================================
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
    f"mdd {b1m['max_drawdown']*100:.2f}% "
    f"({len(bank_syms)} union symbols)")
b3_cagrs = []
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

# === 7. band engine frames ===================================================
log("== 7. band engine market frames ==")
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
pins["daily"].update({"rows_total": daily_meta["rows_total"],
                      "rows_after_freeze_filter":
                          daily_meta["rows_after_freeze_filter"]})
PANEL_BY_ARM = {arm: sorted(set(FRAMES[arm]["symbol"].to_list()))
                for arm in ARMS}
_all_syms = sorted({s for arm in ARMS for s in PANEL_BY_ARM[arm]})
daily = (daily_full.filter(pl.col("symbol").is_in(_all_syms))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .select("symbol", "date", "open", "high", "low", "close", "tradestatus")
         .sort("symbol", "date"))
del daily_full
assert_frozen(daily, "date", "daily")
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
half_parts = []
for part in parts:
    f = pl.read_parquet(part)
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= DEV_START)
                 & (pl.col("trade_date") <= DEV_END))
    f = f.filter(pl.col("symbol").is_in(_all_syms))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame()
del half_parts
assert_frozen(half, "trade_date", "halfday")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})
limits = (limits_full.filter(pl.col("symbol").is_in(_all_syms))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
          .sort("symbol", "date"))
del limits_full
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(_all_syms))
dividends = divs_all.filter(pl.col("symbol").is_in(_all_syms))
del splits_all, divs_all
instruments = pl.DataFrame({"symbol": _all_syms, "is_etf": [False] * len(_all_syms),
                            "is_t0": [False] * len(_all_syms)})
log(f"  frames: panel {len(_all_syms)} symbols; daily {daily.height}; "
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


def close_le(sym: str, d: date) -> float | None:
    arr = close_arr.get(sym)
    if arr is None:
        return None
    dint, cls = arr
    i = int(np.searchsorted(dint, dint_of(d), side="right")) - 1
    return float(cls[i]) if i >= 0 else None


split_events: dict[str, list[tuple[date, float]]] = {}
for r in splits.filter(pl.col("ex_date") <= DEV_END).iter_rows(named=True):
    split_events.setdefault(r["symbol"], []).append(
        (r["ex_date"], float(r["split_factor"])))
for v in split_events.values():
    v.sort()

# === 8. engine runs ==========================================================
log("== 8. band engine intent runs ==")
results: dict = {}
for arm in ARMS:
    syms = PANEL_BY_ARM[arm]
    daily_c = daily.filter(pl.col("symbol").is_in(syms))
    half_c = half.filter(pl.col("symbol").is_in(syms))
    limits_c = limits.filter(pl.col("symbol").is_in(syms))
    splits_c = splits.filter(pl.col("symbol").is_in(syms))
    divs_c = dividends.filter(pl.col("symbol").is_in(syms))
    instr_c = instruments.filter(pl.col("symbol").is_in(syms))
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(FRAMES[arm], daily_c, half_c, limits_c,
                                    splits_c, divs_c, instr_c,
                                    initial_cash=200_000.0)
    wall = time.perf_counter() - t_cfg
    il = res.stats.get("intent_layer") or {}
    log(f"  {arm}: engine {wall:.1f}s; intents {il.get('n_intents')} "
        f"activated {il.get('activated')} orders {il.get('orders_generated')} "
        f"filled {il.get('stopped_filled')} override "
        f"{il.get('terminated_override')} expired {il.get('terminated_expired')} "
        f"| rss {rss_gb():.2f} GB")
    results[arm] = {"res": res, "wall_s": wall, "warnings": list(res.warnings)}
    check_budget(f"{arm} engine run")

# === 9. gate-8 attribution (7.7-m6 verbatim) =================================
log("== 9. gate-8 attribution ==")
RULE_OK = {"below_min_lot", "void_no_position", "void_insufficient_cash"}


def sidestr_class(sidestr: str) -> str:
    return "buy" if sidestr.startswith("buy") else "sell"


def attribute(arm: str) -> dict:
    res = results[arm]["res"]
    fr = FRAMES[arm]
    sources_by: dict = {}
    for r in fr.iter_rows(named=True):
        sources_by.setdefault((r["symbol"], r["side"]), []).append(
            (r["source_signal"], r["decision_session"]))
    src_cache: dict = {}

    def src_of(sym: str, side: str, d, s: str):
        key = (sym, side, dint_of(d), s)
        if key in src_cache:
            return src_cache[key]
        best = None
        for T, first_s in sources_by.get((sym, side), []):
            if T < d or (T == d and first_s == "pm" and s == "pm"):
                if best is None or T > best:
                    best = T
        src_cache[key] = best
        return best

    lifecycle: dict = {}
    for r in res.events.filter(pl.col("event") == "intent_lifecycle") \
                       .iter_rows(named=True):
        try:
            left, rest = r["detail"].split(" source ", 1)
            iso, reason = rest.split(": ", 1)
            src = date.fromisoformat(iso)
        except Exception:
            _fail(f"{arm}: unparsable intent_lifecycle detail {r['detail']!r}")
        sym, sidestr = left.split("/", 1)[0], left.split("/", 1)[1]
        lifecycle[(sym, sidestr_class(sidestr), src)] = reason
    ev_orders = res.events.filter(pl.col("order_id") != "")
    per_intent_events: dict = {}
    fill_sess = {"am": 0, "pm": 0}
    for r in ev_orders.iter_rows(named=True):
        parts = r["order_id"].rsplit("-", 4)
        if len(parts) != 5:
            _fail(f"{arm}: unparsable order_id {r['order_id']!r}")
        prefix, y, mo, dy, sess = parts
        if "-" not in prefix:
            _fail(f"{arm}: unparsable order_id prefix {prefix!r}")
        sym, sidestr = prefix.split("-", 1)
        sclass = sidestr_class(sidestr)
        d = date(int(y), int(mo), int(dy))
        T = src_of(sym, sclass, d, sess)
        if T is None:
            _fail(f"{arm}: event order {r['order_id']} has no source intent")
        per_intent_events.setdefault((sym, sclass, T), []).append(r["event"])
    fills = res.fills
    fill_by_intent: dict = {}
    if fills.height:
        for r in fills.select("symbol", "side", "decision_date",
                              "decision_session").iter_rows(named=True):
            sclass = "buy" if r["side"] == "buy" else "sell"
            T = src_of(r["symbol"], sclass, r["decision_date"],
                       r["decision_session"])
            if T is not None:
                k = (r["symbol"], sclass, T)
                fill_by_intent[k] = fill_by_intent.get(k, 0) + 1
    for r in (fills.select("decision_session").iter_rows() if fills.height
              else []):
        fill_sess[r[0]] = fill_sess.get(r[0], 0) + 1
    outcomes: dict = {}
    term = {"expiry": 0, "override_same_name": 0, "cap_void": 0,
            "suspension_abandon": 0}
    rule_blocked = {"below_min_lot": 0, "void_no_position": 0,
                    "void_insufficient_cash": 0}
    zero_emission = 0
    expiry_noop = 0
    for r in fr.iter_rows(named=True):
        k = (r["symbol"], r["side"], r["source_signal"])
        eng = lifecycle.get(k, "still_active(no lifecycle event)")
        evs = per_intent_events.get(k, [])
        if not evs:
            zero_emission += 1
        if fill_by_intent.get(k, 0) > 0:
            host = "filled"
        elif evs and all(e == "void_suspended" for e in evs):
            host = "terminated:suspension_abandon"
        elif evs and all(e in RULE_OK for e in evs):
            host = "executed_rule_blocked:" + evs[-1]
            rule_blocked[evs[-1]] += 1
        elif eng.startswith("cap_single_name"):
            host = "terminated:cap_void"
        elif eng.startswith("overridden"):
            host = "terminated:override_same_name"
        elif eng.startswith("expired") or eng.startswith("still_active"):
            if not evs:
                # zero-emission: suspended the whole window, or (sell side)
                # nothing ever held -- classify sell-with-no-position via
                # whether the symbol traded in-window
                noop = False
                if r["side"] == "sell":
                    arr = close_arr.get(r["symbol"])
                    if arr is not None:
                        dint, _ = arr
                        j = int(np.searchsorted(
                            dint, dint_of(r["source_signal"])))
                        noop = (j < len(dint)
                                and dint[j] < dint_of(r["expiry_date"]))
                if noop:
                    host = "terminated:expired_noop"
                    expiry_noop += 1
                else:
                    host = "terminated:suspension_abandon"
            else:
                host = "terminated:expiry"
        else:
            host = f"terminated:expiry(eng={eng})"
        outcomes[k] = host
        if host.startswith("terminated:"):
            reason = host.split(":", 1)[1]
            if reason == "suspension_abandon":
                term["suspension_abandon"] += 1
            elif reason == "override_same_name":
                term["override_same_name"] += 1
            elif reason == "cap_void":
                term["cap_void"] += 1
            else:
                term["expiry"] += 1
    n_filled = sum(1 for v in outcomes.values() if v == "filled")
    n_rule = sum(1 for v in outcomes.values()
                 if v.startswith("executed_rule_blocked"))
    n_term = sum(1 for v in outcomes.values() if v.startswith("terminated:"))
    mapped = ((n_filled + n_rule) / (n_filled + n_rule + n_term)
              if (n_filled + n_rule + n_term) else None)
    il = res.stats["intent_layer"]
    if n_filled != il["stopped_filled"]:
        _fail(f"{arm}: host filled {n_filled} != engine stopped_filled "
              f"{il['stopped_filled']}")
    return {"outcomes": outcomes, "termination": term,
            "mapped_rate": mapped, "n_filled": n_filled,
            "n_rule_blocked": n_rule, "rule_blocked": dict(rule_blocked),
            "n_terminated": n_term, "zero_emission_intents": zero_emission,
            "expiry_noop": expiry_noop,
            "order_session": res.stats["fill_rate_order_session"],
            "fill_sess_share": {
                s: (fill_sess[s] / sum(fill_sess.values())
                    if sum(fill_sess.values()) else None)
                for s in ("am", "pm")},
            "intent_layer": il}


attr: dict = {}
for arm in ARMS:
    attr[arm] = attribute(arm)
    a = attr[arm]
    log(f"  {arm}: gate8 mapped {(a['mapped_rate'] or 0)*100:.1f}% "
        f"(filled {a['n_filled']}, rule-blocked {a['n_rule_blocked']}, "
        f"terminated {a['n_terminated']}, zero-emission "
        f"{a['zero_emission_intents']}, expired-noop {a['expiry_noop']}); "
        f"term {a['termination']}")
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


# === 10. metrics & gates =====================================================
log("== 10. metrics & eight gates + goal criterion ==")
metrics: dict = {}
gates: dict = {}
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
             "7.7-m6: (filled + rule-blocked) / (filled + rule-blocked "
             "+ terminated); re-anchors neutral",
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
    FRAMES[arm].write_parquet(out_dir / f"{arm}_intents.parquet")
    results[arm]["res"].fills.write_parquet(out_dir / f"{arm}_fills.parquet")
    results[arm]["res"].events.write_parquet(out_dir / f"{arm}_events.parquet")
    results[arm]["res"].daily.write_parquet(
        out_dir / f"{arm}_daily_equity.parquet")
    results[arm]["res"].clips_final.write_parquet(
        out_dir / f"{arm}_clips_final.parquet")
    pl.DataFrame(comp_rows[arm],
                 schema={"symbol": pl.String, "signal_date": pl.Date,
                         "value": pl.Float64}).write_parquet(
        out_dir / f"{arm}_composite.parquet")
pl.DataFrame([{**c, "members": "|".join(c["members"])} for c in cluster_table]
             ).write_csv(out_dir / "dedup_clusters.csv")
pl.DataFrame([{"signal_date": t, "pool_n": pool_sizes[t],
               "eligible_n": len(eligible[t])} for t in sig_days]
             ).write_csv(out_dir / "pool_sizes.csv")
mg = {
    "experiment_id": "exp-20260919-factor-round-f3r1",
    "engine_sha256_16": engine_got[:16],
    "execution_model": "band engine v1.3 intent layer; one static frame "
                       "per arm; membership-transition intents only",
    "dedup": {"rho_threshold": 0.6, "clusters": len(clusters),
              "representatives": reps, "cluster_table": cluster_table,
              "min_components_required": min_cov},
    "benchmarks": {
        "b1m": {k: b1m[k] for k in ("net_cagr", "max_drawdown",
                                    "net_return_by_year")},
        "b1m_caliber": "executable pool equal-weight monthly fractional, "
                       "exposure=1, rate-only fees (R16 convention)",
        "b3prime": {"mean_net_cagr": B3P, "seeds": list(r16.B3_SEEDS),
                    "k": K,
                    "per_seed_net_cagr": b3_cagrs,
                    "caliber": "random K=10 integer lots STOCK_FEE_SCHEDULE "
                               "exposure=1 (R16 convention; K matches F3 "
                               "seats, R16 used K=20 for its K family)"}},
    "metrics": metrics, "gates": gates,
    "disclosures": {
        arm: {
            "gate8": {"mapped_rate": attr[arm]["mapped_rate"],
                      "filled": attr[arm]["n_filled"],
                      "rule_blocked": attr[arm]["rule_blocked"],
                      "termination": attr[arm]["termination"],
                      "zero_emission": attr[arm]["zero_emission_intents"],
                      "expired_noop": attr[arm]["expiry_noop"],
                      "order_session": attr[arm]["order_session"],
                      "decision_point_fill_share": attr[arm]["fill_sess_share"]},
            "seat_vacancy_note": "buy intents that expire unfilled leave "
                                 "the seat in cash until the name cycles out "
                                 "and re-enters (static frame, no re-emission)",
            "no_midcycle_rebalance": True,
            "engine_warnings_n": len(results[arm]["warnings"]),
            "engine_warnings_sample": results[arm]["warnings"][:3],
        } for arm in ARMS},
    "val_consumed": False,
    "stop_note": ("STOP: >=1 arm passed all dev gates; val requires "
                  "separate user approval" if n_pass else
                  f"no arm passed all dev gates ({n_pass}/{len(ARMS)}); "
                  "val not consumed"),
}
(out_dir / "metrics_and_gates.json").write_text(
    json.dumps(mg, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")

# report.md
rep = ["# F3R1 因子组合：两臂 band 引擎 v1.3 八门判定（dev）", "",
       f"- 运行 `{RUN_DIR.name}`；引擎 v1.3 sha256:16 `{engine_got[:16]}`；"
       "预登记 `docs/research/exp-20260919-factor-round-f3r1-prereg.md`（冻结，"
       "含 ICW 权重运行前澄清补钉）。",
       f"- 去重：42 幸存者 → {len(clusters)} 簇 → {M} 代表 "
       f"（{', '.join(reps)}）；可执行池 = R16 冻结池 ∩ 组合覆盖"
       f"（≥{min_cov}/{M} 代表非空）。",
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
        "## 死因与披露要点", ""]
for arm in ARMS:
    a = attr[arm]
    rep.append(
        f"- **{arm}**：门8 终止结构 {a['termination']}；规则阻断 "
        f"{a['rule_blocked']}；零发射意图 {a['zero_emission_intents']}；"
        f"过期空操作 {a['expiry_noop']}；席位置空规则=买入意图过期即空仓至"
        "该票离池再入（静态帧不重发，预登记 §5 登记注记）。")
rep += ["", "## 基准口径", "",
        f"- B1(m)_F3 = 可执行池等权月频 fractional、exposure=1、rate-only "
        f"费率（R16 原约定，本轮池重算）：净 {b1m['net_cagr']*100:+.2f}%、"
        f"回撤 {b1m['max_drawdown']*100:.2f}%。",
        f"- B3′_F3 = 随机 K=10、种子 17–36 共 20 次、整手 + STOCK_FEE_SCHEDULE："
        f"均值 {B3P*100:+.2f}%（R16 用 K=20 对应其 K 族，本轮对齐自身席位，"
        "偏差登记于预登记 §5）。"]
(RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

# manifest
engine_sha_at_end = sha256_file(ENGINE_PY)
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json", "runner.log"):
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260919-factor-round-f3r1",
    "status": "completed",
    "started_at_utc": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                "artifacts/runs/" + RUN_DIR.name + "/tmp/runner_f3r1.py"],
    "random_seed": "B3' seeds 17..36 (r16.B3_SEEDS); no other RNG",
    "engine": {"path": str(ENGINE_PY), "sha256_at_start": engine_got,
               "sha256_at_end": engine_sha_at_end,
               "version": "v1.3", "corporate_actions": None},
    "pins": pins,
    "config": json.loads(CONFIG.read_text(encoding="utf-8")),
    "signal_days": [str(d) for d in sig_days],
    "cluster_table": cluster_table,
    "representatives": reps,
    "trial_accounting": {"strategy_line": {"before": 262, "this_round": 2,
                                           "after": 264},
                         "factor_line": "no new trials (FT-01 unchanged)"},
    "gates_dev_pass": [arm for arm in ARMS
                       if gates[arm]["dev"]["dev_pass"]],
    "goal_met_arms": [arm for arm in ARMS
                      if gates[arm]["dev"]["goal_met"]],
    "advanced_to_validation": False,
    "val_consumed": False,
    "stop_note": mg["stop_note"],
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== manifest + report written; wall {time.perf_counter()-T0:.0f}s, "
    f"peak rss {PEAK_RSS:.2f} GB ==")
log(f"== VERDICT: {n_pass}/{len(ARMS)} dev_pass; goal-met arms: "
    f"{manifest['goal_met_arms']}; {mg['stop_note']} ==")
_logf.close()

