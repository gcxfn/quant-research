# -*- coding: utf-8 -*-
"""Fixed-scheme experiment: hybrid mainline full-contract replay.

Prereg (frozen): docs/research/exp-20260921-fixed-scheme-prereg.md
User-approved 2026-09-21: BOTH stock legs x 4 account-level configs = 8
curves, 40/60 attack/defense, one round.

Per curve: single ledger, halfday clock for stocks + pm-only daily routing
for the three defensive ETFs (engine v1.5 + clip-price feedback), monthly
signals, K=4 buffered seats, batch-level ATR20 stops / +2R half / +3R clear
/ protection line, defensive 60d/10% drawdown exits, monthly rebalance.
Benchmarks: B1(m)_mix = 0.4*B1(m)_F3 + 0.6*defensive; B3'_mix likewise.
Smoke mode: env FIXED_WINDOW="2015-01-01:2015-03-31" runs M-F x G0 only.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.fixed_scheme_lib import (  # noqa: E402
    DEFENSE_SYMBOLS, ConstantOverlayHost, DefensiveLeg, build_atr20,
    defensive_month_returns, mix_from_monthly, monthly_returns_from_equity,
    cagr_from_monthly, mdd_from_monthly, t200_monthly, yearly_from_monthly)
from quant.research.single_name_rules import SingleNameRules  # noqa: E402
from quant.research.risk_overlay_runner import (  # noqa: E402
    DynamicOverlayHost, LedgerMarks)
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_halfday_bars,
    load_split_factor_h5, load_stk_limit_batch, run_band_backtest_intents)

F2R1 = ROOT / "artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5/f3_inputs"
PREREG = ROOT / "docs/research/exp-20260921-fixed-scheme-prereg.md"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
ETF_PARQUET = ROOT / "data/processed/etf-daily-20260919/daily_2015_2024.parquet"
FUND_ADJ_DIR = ROOT / "data/raw/tushare/fund_adj/20260917-r1"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
CURVE_NAME = "MLG3"
STOP_MODE = "wide"        # wide = 3xATR20, 10%..20% (r2 prereg)
SIGNAL_FREQ = "monthly"           # quarterly = season-end signals
_win = os.environ.get("FIXED_WINDOW", "full")
SMOKE = _win != "full"
if SMOKE:
    _a, _b = _win.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
else:
    WIN_START, WIN_END = DEV_START, DEV_END

ENGINE_SHA_EXPECT_16 = "f3650f8440c713b8"
F3R1_REPS = ["A17", "A20", "A25", "B11", "B12", "B14", "C19", "D08", "D09",
             "D10", "D14", "D18", "D19", "D20", "D21", "D25", "E16", "F02",
             "F06", "F09"]
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}
K = 4
ARMS = ["MF", "MC"]            # stock legs: factor / trend-dispersion
GCFGS = ["G0", "G1", "G2", "G3"]
CURVES = ["R2A"]
LEG, GCFG = "MF", "G3"
ETF_META = {s: {"asset_class": "etf", "band": 0.10, "t_plus": 0}
            for s in DEFENSE_SYMBOLS}

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
BUDGET_S = 1800.0 if not SMOKE else 900.0
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
        "experiment_id": "exp-20260921-fixed-scheme-r2",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


log(f"fixed-scheme; window={WIN_START}..{WIN_END}"
    f"{' (SMOKE: MF-G0 only)' if SMOKE else ''}; curves={CURVES}")

# === 0. pins ================================================================
pins: dict = {}
engine_got = sha256_file(ENGINE_PY)
pins["engine"] = {"path": str(ENGINE_PY), "sha256": engine_got,
                  "expected_16": ENGINE_SHA_EXPECT_16,
                  "match": engine_got.startswith(ENGINE_SHA_EXPECT_16)}
if not pins["engine"]["match"]:
    _fail(f"engine pin mismatch: {engine_got[:16]}")
pins["prereg"] = {"sha256": sha256_file(PREREG)}
for name, p in [("daily", DAILY_PARQUET), ("etf_daily", ETF_PARQUET),
                ("index_000300", INDEX_CHUNK),
                ("split_factor", BUNDLE / "split_factor.h5"),
                ("dividends", BUNDLE / "dividends.h5")]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
hm = sha256_file(HALFDAY_DIR / "manifest.json")
pins["halfday_manifest"] = {"sha256": hm,
                            "match": hm.startswith("2a414174b5df2eee")}
if not pins["halfday_manifest"]["match"]:
    _fail("halfday manifest pin mismatch")
stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {
    **stk_agg, "match":
        stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit pin mismatch")
fa_agg = batch_aggregate_sha256(FUND_ADJ_DIR)
pins["fund_adj_aggregate"] = {"sha256": fa_agg["aggregate_sha256"]}
log(f"  engine {engine_got[:16]} OK; pins OK; rss {rss_gb():.2f} GB")

# === 1. calendar & signals ==================================================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= WIN_START) & (pl.col("s") <= DEV_END))
sig_days_dev = [d for d in all_mes["s"].to_list()
                if SIGNAL_FREQ != "quarterly" or d.month in (3, 6, 9, 12)]
hi = min(WIN_END, DEV_END)
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= hi]
assert sig_days
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})")

# === 2. pools ===============================================================
log("== 2. R16 pools ==")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_sizes = {t: pools_at[t]["n"] for t in sig_days}
log(f"  pool n min {min(pool_sizes.values())} max {max(pool_sizes.values())}")
check_budget("pools")

# === 3. legs: factor composite (M-F) and trend ranked (M-C) =================
log("== 3. stock legs ==")
corr = pl.read_csv(F2R1 / "f2r1_survivors_corr.csv")
all120 = pl.read_csv(F2R1 / "f2r1_all120.csv")
surv = all120.filter(pl.col("screen_pass"))
assert surv.height == 43
stats = {r["factor_id"]: r for r in surv.iter_rows(named=True)}
ids = corr["factor"].to_list()
mat = {r["factor"]: [float(r[c]) if r[c] is not None else np.nan for c in ids]
       for r in corr.iter_rows(named=True)}
adj = {i: {j for j in ids if i != j and abs(mat[i][ids.index(j)]) >= 0.6}
       for i in ids}
seen: set = set()
clusters = []
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
reps = sorted(sorted(c, key=lambda f: (-abs(stats[f]["t_ic"]),
                                       -stats[f]["coverage"], f))[0]
              for c in clusters)
if reps != F3R1_REPS:
    _fail(f"dedup reps != F3R1: {reps}")
M = len(reps)
min_cov = -(-M // 2)
import json as _json  # noqa: E402
icir_of, signs, weights = {}, {}, {}
for fid in reps:
    j = _json.loads((F2R1 / FAMILY_DIR[fid[0]] / f"{fid}.json")
                    .read_text(encoding="utf-8"))
    icir_of[fid] = float(j["eval"]["icir"])
    signs[fid] = 1.0 if float(stats[fid]["ic_mean"]) > 0 else -1.0
    weights[fid] = abs(icir_of[fid])
wide = None
for fid in reps:
    f = pl.read_parquet(F2R1 / FAMILY_DIR[fid[0]] / f"{fid}.parquet")
    f = f.filter(pl.col("signal_date").is_in(pl.Series(sig_days))
                 ).rename({"value": fid})
    wide = f if wide is None else wide.join(
        f, on=["symbol", "signal_date"], how="full", coalesce=True)
wide = wide.filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
composite: dict[date, dict[str, float]] = {}
eligible: dict[date, list[str]] = {}
pool_set = {t: set(pools_at[t]["ranked"]) for t in sig_days}
for t in sig_days:
    have = (wide.filter(pl.col("signal_date") == t).with_columns(
        sum(pl.col(f).is_not_null().cast(pl.Int8) for f in reps).alias("_n"))
        .filter(pl.col("symbol").is_in(pl.Series(sorted(pool_set[t]))))
        .filter(pl.col("_n") >= min_cov))
    with_parts = have
    for fid in reps:
        with_parts = with_parts.with_columns(
            ((pl.col(fid).rank(method="average") - 1.0)
             / pl.max_horizontal(pl.col(fid).count() - 1.0, 1))
            .alias(f"_p_{fid}"))
    composite[t] = {}
    elig = have["symbol"].to_list()
    eligible[t] = sorted(elig)
    for r in with_parts.iter_rows(named=True):
        num = den = 0.0
        for fid in reps:
            p = r.get(f"_p_{fid}")
            if p is None:
                continue
            num += weights[fid] * (p - 0.5) * signs[fid]
            den += weights[fid]
        if den > 0:
            composite[t][r["symbol"]] = num / den
log(f"  M-F: {M} reps; eligible median "
    f"{int(np.median([len(eligible[t]) for t in sig_days]))}")

# membership per leg (K=4, entry top4 / exit rank>8; M-C keeps q5)
ranked_leg: dict[str, dict[date, list[str]]] = {"MF": {}, "MC": {}}
members_leg: dict[str, dict[date, list[str]]] = {"MF": {}, "MC": {}}
import json as _j
ML_PRED = _j.loads((ROOT / "artifacts/runs/20260921T125117-alpha158-90aa2"
                    "/outputs/ml_scores.json").read_text(encoding="utf-8"))
for t in sig_days:
    scores = ML_PRED.get(t.isoformat(), {})
    if scores:
        pool = set(pools_at[t]["ranked"]) & set(scores)
        ranked_leg["MF"][t] = sorted(
            pool, key=lambda s: (-scores[s], s))
    else:
        ranked_leg["MF"][t] = []
    ranked_leg["MC"][t] = []
for leg in ("MF", "MC"):
    prev: list[str] = []
    for t in sig_days:
        q5 = pools_at[t]["q5"] if leg == "MC" else {}
        q5_on = leg == "MC"
        members, _ = r16.buffer_membership(prev, ranked_leg[leg][t], q5,
                                           K, q5_on)
        members_leg[leg][t] = members
        prev = members
    n_m = [len(members_leg[leg][t]) for t in sig_days]
    log(f"  {leg}: members/month min {min(n_m)} max {max(n_m)}")
check_budget("legs")

# === 4. market frames (stocks + ETFs in ONE daily frame) ====================
log("== 4. market frames ==")
_union_stocks = sorted({s for leg in ARMS for t in sig_days
                        for s in members_leg[leg][t]})
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
pins["daily"].update({"rows_total": daily_meta["rows_total"]})
daily_st = (daily_full.filter(pl.col("symbol").is_in(_union_stocks))
            .filter((pl.col("date") >= WIN_START) & (pl.col("date") <= WIN_END))
            .sort("symbol", "date"))
if "preclose" not in daily_st.columns:
    daily_st = daily_st.with_columns(
        pl.col("close").shift(1).over("symbol").alias("preclose"))
assert_frozen(daily_st, "date", "daily-stocks")
daily_ext = (daily_full.filter(pl.col("symbol").is_in(_union_stocks))
             .filter((pl.col("date") >= WIN_START - timedelta(days=90))
                     & (pl.col("date") <= WIN_END))
             .sort("symbol", "date"))
atr_tbl = build_atr20(daily_ext)
del daily_ext, daily_full
etf = (pl.read_parquet(ETF_PARQUET)
       .filter(pl.col("symbol").is_in(list(DEFENSE_SYMBOLS)))
       .filter((pl.col("date") >= WIN_START) & (pl.col("date") <= WIN_END))
       .select("symbol", "date", "open", "high", "low", "close", "preclose")
       .with_columns(pl.lit(1.0, dtype=pl.Float64).alias("tradestatus"))
       .sort("symbol", "date"))
assert_frozen(etf, "date", "etf-daily")
daily = pl.concat([daily_st, etf], how="diagonal")
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
half_parts = []
for part in parts:
    f = pl.read_parquet(part)
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= WIN_START)
                 & (pl.col("trade_date") <= WIN_END))
    f = f.filter(pl.col("symbol").is_in(_union_stocks))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame()
del half_parts
assert_frozen(half, "trade_date", "halfday")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})
limits = (limits_full.filter(pl.col("symbol").is_in(_union_stocks))
          .filter((pl.col("date") >= WIN_START) & (pl.col("date") <= WIN_END))
          .sort("symbol", "date"))
del limits_full
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(_union_stocks))
dividends = divs_all.filter(pl.col("symbol").is_in(_union_stocks))
del splits_all, divs_all
instruments = pl.DataFrame({
    "symbol": _union_stocks + list(DEFENSE_SYMBOLS),
    "is_etf": [False] * len(_union_stocks) + [True] * len(DEFENSE_SYMBOLS),
    "is_t0": [False] * len(_union_stocks) + [True] * len(DEFENSE_SYMBOLS)})
log(f"  frames: {len(_union_stocks)} stocks + {len(DEFENSE_SYMBOLS)} ETFs; "
    f"daily {daily.height}; half {half.height}; limits {limits.height}; "
    f"rss {rss_gb():.2f} GB")
check_budget("frames")

# lookups
def _dint(col: pl.Series) -> np.ndarray:
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


_close_ix: dict[str, tuple] = {}
for (sym,), g in (daily.filter(pl.col("tradestatus") != 0)
                  .partition_by("symbol", as_dict=True)).items():
    _close_ix[str(sym)] = (_dint(g["date"]),
                           g["close"].to_numpy().astype(np.float64),
                           g["high"].to_numpy().astype(np.float64))


def close_le(sym: str, d: date) -> float | None:
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d), side="right")) - 1
    return float(a[1][i]) if i >= 0 else None


def high60_le(sym: str, d: date) -> float | None:
    a = _close_ix.get(sym)
    if a is None:
        return None
    j = int(np.searchsorted(a[0], dint_of(d), side="right"))
    lo = max(j - 60, 0)
    return float(np.max(a[2][lo:j])) if j > lo else None


_am_ix: dict[str, tuple] = {}
if half.height:
    amf = half.filter(pl.col("session") == "am")
    for (sym,), g in amf.partition_by("symbol", as_dict=True).items():
        _am_ix[str(sym)] = (_dint(g["trade_date"]),
                            g["close"].to_numpy().astype(np.float64))


def am_close(sym: str, d: date) -> float | None:
    a = _am_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d)))
    return float(a[1][i]) if i < len(a[0]) and int(a[0][i]) == dint_of(d) \
        else None


def price_at(sym: str, d: date, sess: str) -> float | None:
    if sess == "am":
        return am_close(sym, d)
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d)))
    return float(a[1][i]) if i < len(a[0]) and int(a[0][i]) == dint_of(d) \
        else None


e_table_g1 = t200_monthly(INDEX_CHUNK, calendar_full, sig_days)

# === 5. benchmarks ==========================================================
def_m = defensive_month_returns(pl.read_parquet(ETF_PARQUET), FUND_ADJ_DIR)
pins["defensive_months"] = len(def_m)
if not SMOKE:
    log("== 5. benchmarks B1(m)_mix / B3'_mix ==")
    pools_f3 = {t: {"ranked": list(ranked_leg["MF"][t]), "q5": {},
                    "n": len(ranked_leg["MF"][t])} for t in sig_days}
    bank_syms = sorted({s for t in sig_days for s in pools_f3[t]["ranked"]})
    bank = r16.PriceBank(hist, calendar_full, bank_syms)
    exposures = {t: 1.0 for t in sig_days}
    b1 = r16.simulate_r16("B1m-F3", bank, calendar_full, DEV_START, sig_days,
                          pools_f3, exposures, K=0, fractional=True,
                          fee_bands=r16.B1_FEE_SCHEDULE_RATE_ONLY)
    b1m_m = monthly_returns_from_equity(b1.sessions, b1.equity)
    b1mix_m = mix_from_monthly(b1m_m, def_m, 0.4)
    B1M = {"cagr": cagr_from_monthly(b1mix_m), "mdd": mdd_from_monthly(b1mix_m),
           "by_year": yearly_from_monthly(b1mix_m)}
    b3m_list = []
    for seed in r16.B3_SEEDS:
        sim = r16.simulate_r16(
            f"B3p-s{seed}", bank, calendar_full, DEV_START, sig_days,
            pools_f3, exposures, K=K, fractional=False,
            membership_fn=lambda p, r_, q, rng, _K=K: r16.random_membership(
                p, r_, q, rng, _K),
            seed=seed, fee_bands=r16.STOCK_FEE_SCHEDULE)
        b3m_list.append(mix_from_monthly(
            monthly_returns_from_equity(sim.sessions, sim.equity), def_m, 0.4))
    b3_cagrs = [cagr_from_monthly(m) for m in b3m_list]
    B3P = float(np.mean(b3_cagrs))
    log(f"  B1(m)_mix net {B1M['cagr']*100:+.2f}% mdd {B1M['mdd']*100:.2f}%; "
        f"B3'_mix mean {B3P*100:+.2f}%")
    del bank, b1
    check_budget("benchmarks")

# === 6. provider factory ====================================================
ledger_marks = LedgerMarks(daily, half)
sig_sorted = sorted(sig_days)


def sig_eff(day: date, sess: str) -> date | None:
    idx = bisect_left(sig_sorted, day)
    if idx < len(sig_sorted) and sig_sorted[idx] == day:
        return day if sess == "pm" else (sig_sorted[idx - 1] if idx else None)
    return sig_sorted[idx - 1] if idx else None


G_DYN = {"G2": "D2", "G3": "D3"}


def make_provider(leg: str, gcfg: str):
    members_by_t = {t: set(members_leg[leg][t]) for t in sig_days}
    rank_by_t = {t: {s: i + 1 for i, s in enumerate(ranked_leg[leg][t])}
                 for t in sig_days}
    seats_spy: dict = {}
    all_seats: set = set()
    calls = {"n": 0, "stock_rows": 0, "etf_rows": 0}
    marks_fn = (lambda s, d: price_at(s, d, "pm"))
    host = (DynamicOverlayHost(G_DYN[gcfg], ledger_marks,
                               trim_intent="risk")
            if gcfg in G_DYN else
            ConstantOverlayHost(e_table_g1 if gcfg == "G1"
                                else {t: 1.0 for t in sig_days}, marks_fn))
    _snr_kw = ({} if STOP_MODE == "original" else
               {"atr_mult": 3.0, "dist_min": 0.10, "dist_max": 0.20})
    snr = SingleNameRules(lambda s, d: atr_tbl.atr(s, d), **_snr_kw)
    dleg = DefensiveLeg(close_at=close_le, high60_at=high60_le)
    stops = {"stops": 0, "protections": 0, "takes": 0}

    def provider(day: date, sess: str, ledger: dict) -> list[dict] | None:
        calls["n"] += 1
        T = sig_eff(day, sess)
        rows: list[dict] = []
        if T is not None:
            members = members_by_t[T]
            rank_of = rank_by_t[T]
            expiry = (date.fromordinal(next_sig[T].toordinal() + 1)
                      if next_sig.get(T) else None)
            held = {p["symbol"] for p in ledger["positions"]}
            # seat exits (rank > 2K) -> full risk exit, once per (sym,sell,T)
            # (STOCKS only -- the defensive ETFs are not pool members).
            # Deferred below: a symbol already exiting via the single-name
            # rules this decision point must not emit a second row.
            exit_rows = []
            for sym in sorted(s for s in held - members
                              if s not in ETF_META):
                if (sym, "sell", T) in seats_spy:
                    continue
                exit_rows.append({
                    "symbol": sym, "side": "sell", "intent": "risk",
                    "decision_date": day, "decision_session": sess,
                    "source_signal": T, "priority": 10**6,
                    "expiry_date": expiry, "target_weight": None,
                    "target_notional": None})
                seats_spy[(sym, "sell", T)] = 1
            # single-name batch rules FIRST: any exit they emit outranks
            # the overlay's resize rows for that symbol this decision point
            stock_pos = [p for p in ledger["positions"]
                         if p["symbol"] not in ETF_META]
            prices = {p["symbol"]: price_at(p["symbol"], day, sess)
                      for p in stock_pos}
            sn_rows = snr.decide(stock_pos, prices, day=day, session=sess)
            for r in sn_rows:
                r["decision_date"] = day
                r["decision_session"] = sess
                stops["stops" if r["target_weight"] is None else "takes"] += 1
            # overlay: entries / trims / topups at E-scaled seat weight
            st = host.step(ledger, members=members, rank_of=rank_of,
                           source_signal=T, expiry=expiry)
            taken = {x["symbol"] for x in sn_rows}
            overlay_rows = [r for r in st.rows
                            if r["symbol"] not in taken]
            taken |= {r["symbol"] for r in overlay_rows}
            exit_rows = [r for r in exit_rows
                         if r["symbol"] not in taken]
            rows.extend(sn_rows + overlay_rows + exit_rows)
            calls["stock_rows"] += (len(overlay_rows) + len(sn_rows)
                                    + len(exit_rows))
        if sess == "pm":
            # every pm point keeps re-issuing toward target (the smoke-
            # verified form); monthly signals govern the STOCK seats only
            etf_rows = dleg.decide(day, ledger, rebalance=True,
                                   equity=ledger["equity_snapshot"])
            rows.extend(etf_rows)
            calls["etf_rows"] += len(etf_rows)
        for r in rows:
            all_seats.add((r["symbol"], r["side"], r["source_signal"]))
        return rows or None

    return (provider, seats_spy, calls, host, snr, dleg, stops,
            all_seats)


# === 7. engine runs =========================================================
log("== 7. engine runs ==")
results: dict = {}
SEATS: dict = {}


def _max_weight(res) -> float:
    dates = res.daily["date"].to_list()
    eq = res.daily["equity"].to_list()
    per: dict = {}
    for r in res.fills.select("symbol", "date", "side", "shares") \
                     .iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    wmax = 0.0
    state: dict = {}
    for d, e in zip(dates, eq):
        if e <= 0:
            continue
        td = dint_of(d)
        for sym, evs in per.items():
            st = state.setdefault(sym, [0, 0])
            while st[1] < len(evs) and evs[st[1]][0] <= td:
                ev = evs[st[1]]
                st[0] += ev[2] if ev[1] == "buy" else -ev[2]
                st[1] += 1
            if st[0] > 0:
                px = close_le(sym, d)
                if px and px > 0 and st[0] * px / e > wmax:
                    wmax = st[0] * px / e
    return wmax


def _exec_rate(curve: str) -> float:
    """Seat-signal caliber (prereg §5): every distinct (symbol, side,
    source) row the provider submitted is one seat; a seat is filled when
    a fill of that (symbol, side) lands at a decision point its source
    already governed (F3R3 attribution rule)."""
    seats = SEATS[curve]
    fills = results[curve]["res"].fills
    filled = set()
    if fills.height:
        rows = fills.select("symbol", "side", "decision_date",
                            "decision_session").iter_rows(named=True)
        for r in rows:
            best = None
            for (y, sc, T) in seats:
                if y != r["symbol"] or sc != r["side"]:
                    continue
                if (T < r["decision_date"]
                        or (T == r["decision_date"]
                            and r["decision_session"] == "pm")):
                    if best is None or T > best:
                        best = T
            if best is not None:
                filled.add((r["symbol"], r["side"], best))
    return len(filled) / len(seats) if seats else 1.0
for curve in CURVES:
    leg, gcfg = LEG, GCFG
    provider, _spy, calls, host, snr, dleg, stops, all_seats =         make_provider(leg, gcfg)
    SEATS[curve] = all_seats
    t_c = time.perf_counter()
    res = run_band_backtest_intents(
        None, daily, half, limits, splits, dividends, instruments,
        symbol_meta=ETF_META, initial_cash=200_000.0,
        execution_clock="halfday", etf_routing="pm_only",
        intent_provider=provider)
    wall = time.perf_counter() - t_c
    il = res.stats.get("intent_layer") or {}
    dl = res.stats.get("dynamic_layer") or {}
    log(f"  {curve}: {wall:.1f}s; calls {dl.get('provider_calls')} "
        f"injected {dl.get('dynamic_injected')} orders {il.get('orders_generated')} "
        f"filled {il.get('stopped_filled')} k3 {res.stats.get('k3_armed')} "
        f"| etf exits {len(dleg.exits)} sn {stops} | rss {rss_gb():.2f} GB")
    results[curve] = {"res": res, "wall_s": wall,
                      "warnings": list(res.warnings), "calls": dict(calls),
                      "etf_exits": list(dleg.exits), "sn": dict(stops)}
    check_budget(curve)

# === 8. metrics & gates =====================================================
metrics: dict = {}
gates: dict = {}
if not SMOKE:
    log("== 8. metrics & eight gates ==")
    b1y = B1M["by_year"]
    for curve in CURVES:
        res = results[curve]["res"]
        sd, sv = er.slice_curve(res.daily["date"].to_list(),
                                res.daily["equity"].to_list(),
                                DEV_START, DEV_END)
        net = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
        mdd = er.max_drawdown(sd, sv)["max_drawdown"]
        yr = er.year_returns(sd, sv)
        adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
        excess = net - B1M["cagr"]
        dfy = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
        mean_eq = {int(r["yy"]): r["equity"] for r in dfy.group_by("yy")
                   .agg(pl.col("equity").mean()).iter_rows(named=True)}
        buy_by = {int(r["yy"]): r["n"] for r in
                  res.fills.filter(pl.col("side") == "buy")
                  .with_columns(pl.col("date").dt.year().alias("yy"))
                  .group_by("yy").agg(pl.col("notional").sum().alias("n"))
                  .iter_rows(named=True)}
        tby = {y: buy_by.get(y, 0.0) / mean_eq[y] for y in sorted(mean_eq)}
        wmax = _max_weight(res)
        a = {"net_cagr": net, "max_drawdown": mdd,
             "excess_vs_b1mix": excess,
             "net_by_year": {int(k): v for k, v in yr.items()},
             "advantage_years": len(adv),
             "max_turnover": max(tby.values()),
             "max_single_weight": wmax,
             "b1mix_cagr": B1M["cagr"], "b1mix_mdd": B1M["mdd"],
             "b3mix": B3P}
        g = {"1_net_cagr_gt_0": net > 0,
             "2_excess_vs_B1mix_ge_2pp": excess >= 0.020,
             "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
             "4_mdd_le_20pct_and_le_B1mix":
                 abs(mdd) <= 0.20 + 1e-12 and abs(mdd) <= abs(B1M["mdd"]) + 1e-12,
             "5_one_side_turnover_le_6": a["max_turnover"] <= 6.0,
             "6_single_name_weight_le_40pct": wmax <= 0.40,
             "7_vs_B3mix_plus_1pp": net >= B3P + 0.010,
             "8_execution_rate_ge_95pct": _exec_rate(curve) >= 0.95}
        gk = list(g)[:8]
        g["failed_gates"] = sorted(k for k in gk if not g[k])
        g["dev_pass"] = not g["failed_gates"]
        g["goal_cagr_ge_10pct"] = net >= 0.10
        metrics[curve] = a
        gates[curve] = g
        log(f"  {curve}: net {net*100:+.2f}% exc {excess*100:+.2f}pp "
            f"adv {len(adv)}/6 mdd {mdd*100:.2f}% turn {a['max_turnover']:.2f} "
            f"w {wmax*100:.1f}% exec {_exec_rate(curve)*100:.1f}% "
            f"-> {'PASS' if g['dev_pass'] else 'fail ' + str(g['failed_gates'])};"
            f" 10% {'MET' if g['goal_cagr_ge_10pct'] else 'no'}")

# === 9. outputs =============================================================
log("== 9. outputs ==")
out_dir = RUN_DIR / "outputs"
for curve in CURVES:
    res = results[curve]["res"]
    res.fills.write_parquet(out_dir / f"{curve}_fills.parquet")
    res.events.write_parquet(out_dir / f"{curve}_events.parquet")
    res.daily.write_parquet(out_dir / f"{curve}_daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / f"{curve}_clips_final.parquet")
if not SMOKE:
    (out_dir / "metrics_and_gates.json").write_text(
        json.dumps({"metrics": metrics, "gates": gates,
                    "benchmarks": {"b1mix": {k: (v if not isinstance(v, dict)
                                                 else {str(k2): v2 for k2, v2
                                                       in v.items()})
                                             for k, v in B1M.items()},
                                   "b3mix_mean": B3P,
                                   "b3mix_per_seed": b3_cagrs}},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    rep = ["# 固定方案实验：混合主线完整合同回放（dev）", "",
           f"- 运行 `{RUN_DIR.name}`；引擎 {engine_got[:16]}；预登记已冻结。",
           f"- {len(CURVES)} 条曲线 = 2 股票腿 × 4 账户级配置；40/60；"
           "全部历史回放，不构成盈利声称。", "",
           "| 曲线 | 净CAGR | 超额 | 优势年 | 回撤 | 换手 | 单票max | "
           "门8 | 过/8 | 失败门 | ≥10% | 判定 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for curve in CURVES:
        a, g = metrics[curve], gates[curve]
        rep.append(
            f"| {curve} | {a['net_cagr']*100:+.2f}% "
            f"| {a['excess_vs_b1mix']*100:+.2f}pp | {a['advantage_years']}/6 "
            f"| {a['max_drawdown']*100:.2f}% | {a['max_turnover']:.2f} "
            f"| {a['max_single_weight']*100:.1f}% "
            f"| {_exec_rate(curve)*100:.1f}% | {8-len(g['failed_gates'])} "
            f"| {','.join(g['failed_gates']) or '-'} "
            f"| {'MET' if g['goal_cagr_ge_10pct'] else 'no'} "
            f"| {'**PASS**' if g['dev_pass'] else 'eliminated'} |")
    n_pass = sum(1 for c in CURVES if gates[c]["dev_pass"])
    rep += ["", f"## {n_pass}/{len(CURVES)} 过全部门；"
            + ("val 消费须用户批准" if n_pass else "val 不消费"), ""]
    (RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-fixed-scheme-r2",
    "status": "completed", "mode": "smoke" if SMOKE else "full",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0, "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                "artifacts/runs/" + RUN_DIR.name + "/tmp/runner_fixed_scheme.py"],
    "engine": {"sha256_at_start": engine_got,
               "sha256_at_end": sha256_file(ENGINE_PY),
               "version": "v1.5+clip-price", "clock": "halfday+pm_only"},
    "pins": pins,
    "curves": CURVES,
    "trial_accounting": {"strategy_line": {"before": 273, "this_round":
                                           0 if SMOKE else 8, "after":
                                           273 if SMOKE else 281},
                         "factor_line": "no new trials"},
    "disclosures": {
        curve: {"provider_calls": results[curve]["calls"]["n"],
                "etf_exits": results[curve]["etf_exits"],
                "single_name": results[curve]["sn"],
                "warnings_n": len(results[curve]["warnings"]),
                "warnings_sample": results[curve]["warnings"][:3]}
        for curve in CURVES},
    "known_simplifications": [
        "ETF cash dividends are NOT modelled (18 events in dev per the "
        "hybrid-v1 audit); defensive benchmark uses adj-factor returns, so "
        "the strategy defensive leg is slightly UNDERSTATED vs benchmark"],
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(RUN_DIR.rglob("*"))
                if p.is_file() and p.name not in ("manifest.json",
                                                  "runner.log")},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter()-T0:.0f}s; peak rss {PEAK_RSS:.2f} GB")
_logf.close()
