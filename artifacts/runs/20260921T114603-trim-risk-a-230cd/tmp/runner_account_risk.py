# -*- coding: utf-8 -*-
"""Trim-leg caliber comparison (PROFIT group), prereg exp-20260921-trim-risk-fallback.

Derived verbatim from the task-1 account-risk runner; ONLY the engine pin
(v1.5 d4b6c3764780e6de) and trim_intent ("profit") differ.

Original docstring:

Prereg: docs/research/exp-20260921-account-risk-dynamic-prereg.md (frozen
BEFORE this file ran; thresholds, recovery, cooldown and the intent mapping
are all registered there).

Carrier = the F3R3 dynamic arm (run 20260921T024449-f3r3-dynamic-45037d):
same F2R1 factors, same dedup representatives, same EW/ICW composites, same
K=10 buffer membership, same half-day clock, same provider re-issue.  Only
ONE variable changes: the attack sleeve's exposure multiplier ``E_t``,
resolved by ``risk_overlay.AccountRiskDynamics`` from THIS account's own
completed closes (never a control arm) and applied through
``risk_overlay_runner.DynamicOverlayHost``:

* ``D0`` control  - constant E = 0.90 (ratio 1.0 -> carrier parity anchor);
* ``D1`` day loss - own single-session loss > 3.00% -> E = 0.40;
* ``D2`` phase dd - own drawdown from the trailing 60-session peak > 8.00%;
* ``D3`` hwm dd   - own all-time high-water drawdown > 10.00%.

Every curve runs its own engine pass on its own ledger (the state is path
dependent).  ``D0`` must reproduce the carrier's fills/events/daily/
clips_final frames bit-for-bit; that gate runs BEFORE any D1-D3 number is
reported (prereg §5).

Modes: env ACCOUNT_RISK_WINDOW="2015-01-01:2015-03-31" for the engineering
smoke (benchmarks and the comparison table are skipped); default full dev
window 2015-01-05..2020-12-31.
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
from quant.research.risk_overlay_runner import (  # noqa: E402
    DynamicOverlayHost, LedgerMarks)
from quant.portfolio import risk_overlay as ro  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_halfday_bars,
    load_split_factor_h5, load_stk_limit_batch, run_band_backtest_intents)

F2R1 = ROOT / "artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5/f3_inputs"
CONFIG = ROOT / "configs/experiments/f3r1-factor-combination.json"
PREREG = ROOT / "docs/research/exp-20260921-account-risk-dynamic-prereg.md"
CARRIER_RUN = ROOT / "artifacts/runs/20260921T024449-f3r3-dynamic-45037d"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
_win = os.environ.get("ACCOUNT_RISK_WINDOW", "full")
SMOKE = _win != "full"
if SMOKE:
    _a, _b = _win.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
else:
    WIN_START, WIN_END = DEV_START, DEV_END

# both arms are built (the pool/benchmark layer is arm-independent and is kept
# byte-identical to F3R3); only RUN_ARM is replayed through the engine
ARMS = ["F3-EW", "F3-ICW"]
RUN_ARM = "F3-ICW"
CURVES = ["D0", "D1", "D2", "D3"]
CURVE_LABEL = {"D0": "控制组（无账户级降仓）", "D1": "单日损失",
               "D2": "阶段回撤（60 会话峰）", "D3": "高水位回撤"}
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


log(f"account-risk dynamic replay; curves={','.join(CURVES)}; "
    f"window={WIN_START}..{WIN_END}{' (SMOKE)' if SMOKE else ''}")

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
log(f"  engine {engine_got[:16]} OK (frozen dynamic engine); pins OK; "
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
        for a, num, den in (("F3-EW", num_ew, den_ew),
                            ("F3-ICW", num_ic, den_ic)):
            if a not in composite or den == 0:
                continue    # only the arms in ARMS are registered to run
            composite[a][t][sym] = num / den
            comp_rows[a].append({"symbol": sym, "signal_date": t,
                                 "value": num / den})
    if len(sig_days) < 6 or t in (sig_days[0], sig_days[len(sig_days) // 2],
                                  sig_days[-1]):
        log(f"  {t}: pool {pool_sizes[t]} -> eligible {len(elig)}")
check_budget("composite")

# === 5. intent providers: seat re-issue from live ledger + risk overlay ====
log("== 5. seat membership + overlay hosts (one per curve) ==")
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


def make_provider(arm: str, config_id: str, marks: LedgerMarks):
    """Carrier rows + overlay rows, re-issued every half-day from the ledger.

    The carrier part is F3R3 verbatim: a member seat is re-bought until
    filled (pool membership only), a name that left the pool is exited with a
    risk full exit once per signal month (the engine's K=3 carry owns the
    retries).  The overlay part is the registered dynamic mapping: entries
    sized at ``0.10 x E_t / 0.90``, a proportional trim while reduced and a
    delta top-up while a restore is pending.
    """
    members_by_t = {t: set(members_hist[arm][t]) for t in sig_days}
    rank_by_t = {t: {s: i + 1 for i, s in enumerate(ranked_f3[arm][t])}
                 for t in sig_days}
    seats: dict[tuple[str, str, date], dict] = {}
    calls = {"n": 0, "entry_rows": 0, "exit_rows": 0, "overlay_rows": 0}
    host = DynamicOverlayHost(config_id, marks, trim_intent='profit')

    def provider(day: date, sess: str, ledger: dict) -> list[dict] | None:
        calls["n"] += 1
        T = sig_eff(day, sess)
        if T is None:
            return None
        members = members_by_t[T]
        rank_of = rank_by_t[T]
        expiry = date.fromordinal(next_sig[T].toordinal() + 1)
        held = {p["symbol"] for p in ledger["positions"]}
        exits: list[dict] = []
        for sym in sorted(held - members):
            if (sym, "sell", T) in seats:
                continue    # engine-side m3 carry owns intra-month retries
            exits.append({
                "symbol": sym, "side": "sell", "intent": "risk",
                "decision_date": day, "decision_session": sess,
                "source_signal": T, "priority": 10**6,
                "expiry_date": expiry, "target_weight": None})
            seats[(sym, "sell", T)] = {"n_sent": 1}
            calls["exit_rows"] += 1
        step = host.step(ledger, members=members, rank_of=rank_of,
                         source_signal=T, expiry=expiry)
        for sym in step.entry_symbols:
            st = seats.setdefault((sym, "buy", T), {"n_sent": 0})
            st["n_sent"] += 1
            calls["entry_rows"] += 1
        # entry/resize rows first, membership exits second: the carrier's own
        # submission order, so the intent-lifecycle event log is identical
        rows = list(step.rows) + exits
        calls["overlay_rows"] += len(step.rows)
        return rows or None

    return provider, seats, calls, host


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

# === 8. engine runs: four curves, one ledger each ===========================
log("== 8. band engine dynamic runs, one pass per curve ==")
arm = RUN_ARM
syms = sorted({s for t in sig_days for s in members_hist[arm][t]})
daily_c = daily.filter(pl.col("symbol").is_in(syms))
half_c = half.filter(pl.col("symbol").is_in(syms))
limits_c = limits.filter(pl.col("symbol").is_in(syms))
splits_c = splits.filter(pl.col("symbol").is_in(syms))
divs_c = dividends.filter(pl.col("symbol").is_in(syms))
instr_c = instruments.filter(pl.col("symbol").is_in(syms))
marks = LedgerMarks(daily, half)
results: dict = {}
HOSTS: dict = {}
CALLS: dict = {}
for config_id in CURVES:
    provider, seats, calls, host = make_provider(arm, config_id, marks)
    HOSTS[config_id] = host
    CALLS[config_id] = calls
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(
        None, daily_c, half_c, limits_c, splits_c, divs_c, instr_c,
        initial_cash=200_000.0, execution_clock="halfday",
        intent_provider=provider)
    wall = time.perf_counter() - t_cfg
    dl = res.stats.get("dynamic_layer") or {}
    il = res.stats.get("intent_layer") or {}
    submitted = calls["overlay_rows"] + calls["exit_rows"]
    if dl.get("dynamic_injected") != submitted:
        _fail(f"{config_id}: provider rows {submitted} != engine "
              f"dynamic_injected {dl.get('dynamic_injected')}")
    reduced = sum(1 for s in host.steps if s.risk_state == "reduced")
    log(f"  {config_id}: engine {wall:.1f}s; provider calls {dl.get('provider_calls')} "
        f"injected {dl.get('dynamic_injected')} "
        f"(entry {calls['entry_rows']} exit {calls['exit_rows']} "
        f"overlay {calls['overlay_rows']}); steps {len(host.steps)} "
        f"reduced {reduced}; orders {il.get('orders_generated')} "
        f"filled {il.get('stopped_filled')} "
        f"expired_halfday {il.get('terminated_expired_halfday')} "
        f"no_anchor {il.get('terminated_expired_halfday_no_anchor')} "
        f"override {il.get('terminated_override')} | rss {rss_gb():.2f} GB")
    results[config_id] = {"res": res, "wall_s": wall,
                          "warnings": list(res.warnings)}
    check_budget(f"{config_id} engine run")

# === 8b. carrier parity gate (prereg §5): D0 == F3R3's F3-ICW frames ========
log("== 8b. D0 carrier parity gate (five-frame comparison) ==")
PARITY_FRAMES = ("fills", "events", "daily_equity", "clips_final")
parity: dict = {}
if WIN_START == DEV_START and WIN_END == DEV_END:
    for name in PARITY_FRAMES:
        want = pl.read_parquet(CARRIER_RUN / "outputs" / f"F3-ICW_{name}.parquet")
        got = getattr(results["D0"]["res"],
                      "daily" if name == "daily_equity" else name)
        same = got.equals(want)
        info = {"rows": got.height, "carrier_rows": want.height,
                "equal": bool(same)}
        if not same and got.height == want.height \
                and got.schema == want.schema:
            # same shape: report WHERE they differ (order vs content)
            g = got.sort(got.columns)
            w = want.sort(want.columns)
            info["equal_sorted"] = bool(g.equals(w))
            diff = sum(1 for a, b in zip(g.iter_rows(), w.iter_rows())
                       if a != b)
            info["rows_differing_after_sort"] = diff
            info["first_difference"] = next(
                ({"got": list(a), "carrier": list(b)}
                 for a, b in zip(g.iter_rows(), w.iter_rows()) if a != b), None)
            positional = sum(1 for a, b in zip(got.iter_rows(), want.iter_rows())
                             if a != b)
            info["rows_differing_positionally"] = positional
        parity[name] = info
        log(f"  {name}: {got.height} rows, reference {want.height} rows, "
            f"equal={same}"
            + ("" if same else f"; sorted_equal={info.get('equal_sorted')} "
               f"diff={info.get('rows_differing_after_sort')} "
               f"positional={info.get('rows_differing_positionally')}"))
    if not all(v["equal"] for v in parity.values()):
        _fail("D0 does not reproduce the carrier frames; D1-D3 results are "
              "void per prereg §5")
else:
    log("  smoke window: parity gate skipped (reference run is the full dev "
        "window); D0-vs-carrier equality is re-checked in the full run")

# === 9. risk-layer trace summary ============================================
log("== 9. account-level state trace ==")


def trace_summary(config_id: str) -> dict:
    host = HOSTS[config_id]
    steps = host.steps
    rows = host.machine.rows
    lowered_at: list[int] = []
    cooldown_sessions: list[int] = []
    reductions = [s for s in steps if s.action == "reduce_attack"]
    restores = [s for s in steps if s.action == "restore_attack"]
    session_dates = [d for d, _v in host.machine.observations]
    index_of = {d: i for i, d in enumerate(session_dates)}
    for r in rows:
        if r.action is ro.OverlayAction.REDUCE_ATTACK:
            lowered_at.append(index_of[r.equity_as_of])
            if r.cooldown_until is not None and r.cooldown_until in index_of:
                cooldown_sessions.append(index_of[r.cooldown_until]
                                         - index_of[r.equity_as_of])
    # sessions spent reduced, judged once per completed close
    reduced_session_dates = sorted({r.equity_as_of for r in rows
                                    if r.risk_state.value == "reduced"
                                    and r.equity_as_of is not None})
    exposures = [s.ratio for s in steps if s.risk_state != "insufficient_data"]
    return {
        "config_id": config_id,
        "label": CURVE_LABEL[config_id],
        "provider_calls": len(steps),
        "reduce_events": len(reductions),
        "restore_events": len(restores),
        "fail_closed_events": sum(1 for s in steps
                                  if s.action == "fail_closed"),
        "reduced_sessions": len(reduced_session_dates),
        "reduced_session_dates": [d.isoformat()
                                  for d in reduced_session_dates],
        "lowered_session_index": lowered_at,
        "first_reduce": (reductions[0].decision_time.isoformat()
                         if reductions else None),
        "first_restore": (restores[0].decision_time.isoformat()
                          if restores else None),
        "cooldown_sessions_after_lowering": cooldown_sessions,
        "mean_ratio": float(np.mean(exposures)) if exposures else None,
        "min_ratio": float(np.min(exposures)) if exposures else None,
        "trim_rows": sum(len(s.trim_symbols) for s in steps),
        "topup_rows": sum(len(s.topup_symbols) for s in steps),
        "trim_dates": sorted({s.decision_time.date().isoformat() for s in steps
                              if s.trim_symbols}),
        "topup_dates": sorted({s.decision_time.date().isoformat() for s in steps
                               if s.topup_symbols}),
        "max_drawdown_seen": max((r.drawdown for r in rows
                                  if r.drawdown is not None), default=None),
        "intent_layer": results[config_id]["res"].stats["intent_layer"],
        "dynamic_layer": results[config_id]["res"].stats.get("dynamic_layer"),
    }


trace: dict = {}
for config_id in CURVES:
    trace[config_id] = trace_summary(config_id)
    t = trace[config_id]
    log(f"  {config_id}: reduce {t['reduce_events']} restore "
        f"{t['restore_events']} reduced-sessions {t['reduced_sessions']} "
        f"mean E-ratio {(t['mean_ratio'] or 1.0):.3f} trims {t['trim_rows']} "
        f"topups {t['topup_rows']} fail-closed {t['fail_closed_events']}")
check_budget("trace")

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


# === 10. comparison metrics (full mode only) =================================
log("== 10. comparison: D0 control vs the three pre-registered schemes ==")
metrics: dict = {}
if not SMOKE:
    for config_id in CURVES:
        res = results[config_id]["res"]
        sd, sv = er.slice_curve(res.daily["date"].to_list(),
                                res.daily["equity"].to_list(),
                                DEV_START, DEV_END)
        net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
        mdd_info = er.max_drawdown(sd, sv)
        mdd = mdd_info["max_drawdown"]
        yr = er.year_returns(sd, sv)
        df = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
        mean_eq = {int(r["yy"]): r["equity"] for r in
                   df.group_by("yy").agg(pl.col("equity").mean())
                   .iter_rows(named=True)}
        if res.fills.height:
            buy_by = {int(r["yy"]): r["n"] for r in
                      res.fills.filter(pl.col("side") == "buy")
                      .with_columns(pl.col("date").dt.year().alias("yy"))
                      .group_by("yy").agg(pl.col("notional").sum().alias("n"))
                      .iter_rows(named=True)}
        else:
            buy_by = {}
        tby = {y: {"buy_notional": buy_by.get(y, 0.0),
                   "mean_equity": mean_eq[y],
                   "one_side_turnover": buy_by.get(y, 0.0) / mean_eq[y]}
               for y in sorted(mean_eq)}
        gross = df.select(
            (pl.col("positions_value") / pl.col("equity")).alias("g")).to_series()
        cash_ratio = df.select(
            (pl.col("settled_cash") / pl.col("equity")).alias("c")).to_series()
        il = res.stats["intent_layer"]
        metrics[config_id] = {
            "label": CURVE_LABEL[config_id],
            "net_cagr": net_cagr,
            "net_total_return": sv[-1] / sv[0] - 1.0,
            "max_drawdown": mdd,
            "mdd_window": {"peak_date": mdd_info["peak_date"],
                           "trough_date": mdd_info["trough_date"]},
            "net_return_by_year": {int(k): v for k, v in yr.items()},
            "mean_gross_exposure": float(gross.mean()),
            "min_gross_exposure": float(gross.min()),
            "max_gross_exposure": float(gross.max()),
            "mean_cash_ratio": float(cash_ratio.mean()),
            "turnover_by_year": tby,
            "max_one_side_turnover": max(v["one_side_turnover"]
                                         for v in tby.values()),
            "max_single_name_weight": daily_max_single_name_weight(res),
            "fills": res.fills.height,
            "buy_fills": int((res.fills["side"] == "buy").sum()),
            "sell_fills": int((res.fills["side"] == "sell").sum()),
            "buy_notional": float(res.fills.filter(pl.col("side") == "buy")
                                  ["notional"].sum()),
            "sell_notional": float(res.fills.filter(pl.col("side") == "sell")
                                   ["notional"].sum()),
            "fees_total": float(res.fills["commission"].sum()
                                + res.fills["stamp_tax"].sum()),
            "k3_fallback": res.stats.get("k3_fallback"),
            "orders_generated": il.get("orders_generated"),
            "at_target_skips": il.get("at_target_skips"),
            "terminated_expired_halfday": il.get("terminated_expired_halfday"),
            "terminated_expired_halfday_no_anchor":
                il.get("terminated_expired_halfday_no_anchor"),
            "terminated_override": il.get("terminated_override"),
            "n_final_positions": res.clips_final.height,
            "final_equity": float(res.daily["equity"][-1]),
        }
        m = metrics[config_id]
        log(f"  {config_id}: net {net_cagr*100:+.2f}% mdd {mdd*100:.2f}% "
            f"gross {m['mean_gross_exposure']*100:.1f}% cash "
            f"{m['mean_cash_ratio']*100:.1f}% turn "
            f"{m['max_one_side_turnover']:.2f} fills {m['fills']}")

    base = metrics["D0"]
    for config_id in CURVES:
        m = metrics[config_id]
        m["saved_drawdown_pp"] = (abs(base["max_drawdown"])
                                  - abs(m["max_drawdown"])) * 100.0
        m["lost_net_cagr_pp"] = (base["net_cagr"] - m["net_cagr"]) * 100.0
        m["saved_per_lost"] = ((abs(base["max_drawdown"]) - abs(m["max_drawdown"]))
                               / (base["net_cagr"] - m["net_cagr"])
                               if abs(base["net_cagr"] - m["net_cagr"]) > 1e-12
                               else None)
        m["reduced_sessions"] = trace[config_id]["reduced_sessions"]
        m["reduce_events"] = trace[config_id]["reduce_events"]
        m["restore_events"] = trace[config_id]["restore_events"]
        m["mean_ratio"] = trace[config_id]["mean_ratio"]
        m["trim_rows"] = trace[config_id]["trim_rows"]
        m["topup_rows"] = trace[config_id]["topup_rows"]
    log("  comparison vs D0: "
        + "; ".join(f"{c} dd {metrics[c]['saved_drawdown_pp']:+.2f}pp / "
                    f"cagr {metrics[c]['lost_net_cagr_pp']:+.2f}pp"
                    for c in CURVES if c != "D0"))
    check_budget("metrics")

# === 11. outputs =============================================================
log("== 11. outputs ==")
out_dir = RUN_DIR / "outputs"
for config_id in CURVES:
    res = results[config_id]["res"]
    res.fills.write_parquet(out_dir / f"{config_id}_fills.parquet")
    res.events.write_parquet(out_dir / f"{config_id}_events.parquet")
    res.daily.write_parquet(out_dir / f"{config_id}_daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / f"{config_id}_clips_final.parquet")
    with (out_dir / f"{config_id}_state_trace.jsonl").open("w",
                                                           encoding="utf-8") as fh:
        for s in HOSTS[config_id].steps:
            fh.write(json.dumps(s.as_dict(), ensure_ascii=False,
                                default=str) + "\n")
pl.DataFrame(comp_rows[arm],
             schema={"symbol": pl.String, "signal_date": pl.Date,
                     "value": pl.Float64}).write_parquet(
    out_dir / f"{arm}_composite.parquet")
pl.DataFrame([{**c, "members": "|".join(c["members"])} for c in cluster_table]
             ).write_csv(out_dir / "dedup_clusters.csv")
pl.DataFrame([{"signal_date": t, "pool_n": pool_sizes[t],
               "eligible_n": len(eligible[t])} for t in sig_days]
             ).write_csv(out_dir / "pool_sizes.csv")

if not SMOKE:
    mg = {
        "experiment_id": "exp-20260921-trim-risk-fallback",
        "prereg": "docs/research/exp-20260921-account-risk-dynamic-prereg.md",
        "carrier": {"run": CARRIER_RUN.name, "arm": arm,
                    "engine_sha256_16": engine_got[:16],
                    "parity_gate": parity},
        "configs": {c: ro.DYNAMIC_POLICIES[c].__dict__ for c in CURVES},
        "execution_model": "band engine execution_clock='halfday', pure "
                           "dynamic intent_provider (no static frame); "
                           "entries sized 0.10 x E_t/0.90; trims are half-day "
                           "limit sells (intent='profit', no K=3 fallback); "
                           "restores are delta-notional buys",
        "metrics": metrics,
        "trace": {c: {k: v for k, v in trace[c].items()
                      if k not in ("intent_layer", "dynamic_layer")}
                  for c in CURVES},
        "dedup": {"rho_threshold": 0.6, "clusters": len(clusters),
                  "representatives": reps, "reps_match_f3r1": True},
        "benchmarks": {
            "b1m": {k: b1m[k] for k in ("net_cagr", "max_drawdown",
                                        "net_return_by_year")},
            "b3prime": {"mean_net_cagr": B3P, "seeds": list(r16.B3_SEEDS),
                        "k": K, "per_seed_net_cagr": b3_cagrs}},
        "disclosures": {
            c: {"intent_layer": trace[c]["intent_layer"],
                "dynamic_layer": trace[c]["dynamic_layer"],
                "engine_warnings_n": len(results[c]["warnings"]),
                "engine_warnings_sample": results[c]["warnings"][:3],
                "wallet_marks_reconciled": True,
                "no_forced_sale_for_account_legs": True,
                "no_midcycle_rebalance": True}
            for c in CURVES},
        "val_consumed": False,
        "stop_note": "mechanism comparison only: no curve is proposed as a "
                     "strategy; val 2021-2024 and 2025+ untouched",
    }
    (out_dir / "account_risk_comparison.json").write_text(
        json.dumps(mg, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")

    def pct(x):
        return "n/a" if x is None else f"{x*100:+.2f}%"

    rep = ["# 账户级风险动态回放：控制组 + 三档方案对照（dev，机制实验）", "",
           f"- 运行 `{RUN_DIR.name}`；引擎 sha256:16 `{engine_got[:16]}`；"
           "预登记 `docs/research/exp-20260921-account-risk-dynamic-prereg.md`（运行前冻结）。",
           f"- 载体：`{CARRIER_RUN.name}` 的单臂 {arm}（组合/去重/席位规则逐字照抄），"
           f"唯一变量 = 账户级暴露系数 E_t。信号 {sig_days[0]}..{sig_days[-1]}"
           f"（{len(sig_days)} 个月末）。",
           "- D0 与载体五帧一致性门："
           + "，".join(f"{k}={v['equal']}" for k, v in
                       sorted(mg["carrier"]["parity_gate"].items()))
           + "。val 2021–2024 与 2025+ 零接触；全部为历史回放，不构成盈利声称。", "",
           "## 四曲线对照表", "",
           "| 曲线 | 净CAGR | 最大回撤 | 触发(降/恢) | 降仓会话 | 冷却(会话) | "
           "平均敞口 | 平均现金 | 省回撤 | 丢年化 | 省÷丢 |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for config_id in CURVES:
        m = metrics[config_id]
        t = trace[config_id]
        cd = t["cooldown_sessions_after_lowering"]
        rep.append(
            f"| {config_id} {m['label']} | {m['net_cagr']*100:+.2f}% "
            f"| {m['max_drawdown']*100:.2f}% "
            f"| {m['reduce_events']}/{m['restore_events']} "
            f"| {m['reduced_sessions']} "
            f"| {min(cd) if cd else 0}–{max(cd) if cd else 0} "
            f"| {m['mean_gross_exposure']*100:.1f}% "
            f"| {m['mean_cash_ratio']*100:.1f}% "
            f"| {m['saved_drawdown_pp']:+.2f}pp | {m['lost_net_cagr_pp']:+.2f}pp "
            f"| {'n/a' if m['saved_per_lost'] is None else format(m['saved_per_lost'], '.2f')} |")
    rep += ["", "## 执行与费用结构", "",
            "| 曲线 | 换手(max年) | 成交数 | 单票max | 费用(元) | K3兜底 | "
            "at-target跳过 | 半日失效 | 无锚失效 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for config_id in CURVES:
        m = metrics[config_id]
        k3 = m["k3_fallback"] or {}
        rep.append(
            f"| {config_id} | {m['max_one_side_turnover']:.2f} | {m['fills']} "
            f"| {m['max_single_name_weight']*100:.1f}% | {m['fees_total']:.0f} "
            f"| {k3.get('executed')} | {m['at_target_skips']} "
            f"| {m['terminated_expired_halfday']} "
            f"| {m['terminated_expired_halfday_no_anchor']} |")
    rep += ["", "## 状态机细节", ""]
    for config_id in CURVES:
        t = trace[config_id]
        rep.append(
            f"- **{config_id} {t['label']}**：provider 调用 {t['provider_calls']}，"
            f"降档事件 {t['reduce_events']}，恢复事件 {t['restore_events']}，"
            f"fail-closed 行 {t['fail_closed_events']}，降仓会话 "
            f"{t['reduced_sessions']}，平均 E 比 "
            f"{(t['mean_ratio'] or 1.0):.3f}，降仓腿 {t['trim_rows']}、"
            f"补仓腿 {t['topup_rows']}，最深自身回撤 "
            f"{(t['max_drawdown_seen'] or 0)*100:.2f}%，"
            f"首次降档 {t['first_reduce']}，首次恢复 {t['first_restore']}。")
    rep += ["", "## 判定纪律",
            "",
            "- 本实验只做机制对照：任何单条曲线都不得作为策略结论或可实盘候选。",
            "- 控制组门未通过时三档结果作废（预登记 §5）；本轮门结果见上方一致性门。",
            "- 账户级降仓腿登记为不假设成交的半日限价单，未成交即由下一决策点显式重发，"
            "未使用 risk 类型 K=3 强制兜底。"]
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")
else:
    rep = ["# 账户级风险动态回放冒烟（工程链路验证，非研究结论）", "",
           f"- 运行 `{RUN_DIR.name}`；窗 {WIN_START}..{WIN_END}；"
           "基准与对照表按预登记跳过。", ""]
    for config_id in CURVES:
        res = results[config_id]["res"]
        t = trace[config_id]
        rep.append(
            f"- {config_id}：provider 调用 {t['provider_calls']}，降档 "
            f"{t['reduce_events']}，恢复 {t['restore_events']}，降仓会话 "
            f"{t['reduced_sessions']}，fills {res.fills.height}，"
            f"降仓腿 {t['trim_rows']}，补仓腿 {t['topup_rows']}。")
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

# manifest
engine_sha_at_end = sha256_file(ENGINE_PY)
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json", "runner.log"):
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-trim-risk-fallback",
    "status": "completed",
    "mode": "smoke" if SMOKE else "full",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                "artifacts/runs/" + RUN_DIR.name + "/tmp/runner_account_risk.py"],
    "random_seed": ("B3' seeds 17..36 (r16.B3_SEEDS); no other RNG"
                    if not SMOKE else "none (smoke skips benchmarks)"),
    "engine": {"path": str(ENGINE_PY), "sha256_at_start": engine_got,
               "sha256_at_end": engine_sha_at_end,
               "version": "rebuilt dynamic (v1.4.x)",
               "execution_clock": "halfday", "corporate_actions": None},
    "carrier": {"run": CARRIER_RUN.name, "arm": arm,
                "outputs": sorted(p.name for p in
                                  (CARRIER_RUN / "outputs").glob("F3-ICW_*"))},
    "curves": CURVES,
    "curves_config": {c: ro.DYNAMIC_POLICIES[c].__dict__ for c in CURVES},
    "carrier_parity_gate": parity,
    "pins": pins,
    "config": json.loads(CONFIG.read_text(encoding="utf-8")),
    "signal_days": [str(d) for d in sig_days],
    "cluster_table": cluster_table,
    "representatives": reps,
    "trial_accounting": {"strategy_line": {"before": 266, "this_round": 4,
                                           "after": 270},
                         "factor_line": "no new trials (FT-01 unchanged)"},
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
