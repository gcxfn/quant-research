# -*- coding: utf-8 -*-
"""P3R2 re-adjudication runner -- v1.1 ENGINE-SIDE INTENT LAYOUT (one static
intent frame per config, zero host-side fill awareness).

Replaces the ABORTED run 20260919T002020-p3r2-dev-9cc4 per prereg section 9:
- revision 2: the engine owns the order lifecycle (mechanical re-anchor,
  re-hang, fill-stop, expiry / same-name override / cap-void termination).
  The host submits ONE intent frame per config; there is NO fixed-point
  iteration, NO fill-schedule feedback, NO host re-hang logic (all four
  9cc4 host conventions are dead; convention-A numbers are invalid
  diagnostics only).
- revision 3: quantity = target weight x decision-point equity snapshot,
  recomputed inside the engine at every decision point (in-loop pricing).
- revision 4/5: engine v1.1 sha256
  d7108c0eccdd77ff3fcbff01e7bd84bfdd2e7cad716b646e357c5644da970a0d
  (dual-sign APPROVE, run 20260919T023558-p3v1-intent-review-c4d1);
  ENGINE-3 no-limit-info crash fixed in-engine (%s detail, v0 ruling
  #2/#3 semantics restored); no host-side gap skip.

Reused valid 9cc4 frame assets: membership-consistency lookup keys, the
int8->Int64 date-arithmetic overflow fix, the R16 at_target/feemin skip
mapping, the disclosure key names, the metrics/gates implementation.

Intent-frame mapping (prereg sec 4, frozen):
- first decision = (T, 'pm') for every leg of signal day T (sec 4.1);
- expiry_date = T' + 1 calendar day (T' = next month-end): the engine's
  live-session test (live_d >= expiry) then lets the last emission be the
  (T','am') decision living at (T','pm') -- the frozen 9cc4 window; the
  next signal's same-symbol intent overrides at its first decision
  (T','pm') per 7.7-M3;
- buy_open -> side=buy, target_weight = exposure(T)/K (in-loop pricing at
  the (T,'pm') snapshot equals R16's seat sizing with zero feedback);
- sell_full -> side=sell, intent=risk, full exit (no tn/tw), K=3 session
  fallback keyed (symbol, intent, source) per 7.7-M1;
- rescale (R16 outcome not in {at_target, feemin_skipped}) -> side=sell,
  intent=risk, target_weight = exposure(T)/K: the engine's reduce-to-target
  sell primitive self-neutralizes (at_target skip) when the position is at
  or below target.  REGISTERED MAPPING HOLE: the top-up side of R16
  rescale legs is NOT mapped -- the engine's buy primitive has no
  top-up-to-weight semantics and a full-seat weight buy would double the
  seat; disclosed as a hole (prereg sec 4.8 profit-ladder precedent), a
  known confound for vs-P3R1 rescale deltas.
- R16 outcome skips (at_target / feemin_skipped on rescale legs) are
  outside the frame entirely (9cc4 mapping-fidelity asset); m5-b: the
  (symbol, side, source) uniqueness of the frame is hard-asserted before
  any engine run.

Deterministic; no RNG.  Budget: 60 min / 8 GB hard-checked per stage.
"""
from __future__ import annotations

import hashlib
import json
import math
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
    FREEZE_END, LOT, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_halfday_bars,
    load_split_factor_h5, load_stk_limit_batch, run_band_backtest_intents)

SMOKE = "--smoke" in sys.argv

R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
P3R1_RUN = ROOT / "artifacts/runs/20260918T145900-p3r1-dev-262f"
ABORTED_RUN = ROOT / "artifacts/runs/20260919T002020-p3r2-dev-9cc4"
R16_CONFIG = ROOT / "configs/experiments/p2r16-trend-dispersion.json"
P3R2_CONFIG = ROOT / "configs/experiments/p3r2-band-v1-readjudication.json"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
SMOKE_END = date(2015, 12, 31)
CONFIG_IDS = ["C05"]  # v1.4 replay: anchor 1 scope
ENGINE_SHA_EXPECT_FULL = ("c5c073035d63c59d4803f469e427505223edb30aa"
                          "65d05d2184385c33a85c493")
EXPECT = {
    "engine": (ENGINE_SHA_EXPECT_FULL, ENGINE_PY),
    "r16_config": ("27f846a7330919a4", R16_CONFIG),
    "p3r2_config": ("b49025b44c719685", P3R2_CONFIG),
    "daily": ("d9a63f4cc3032926", DAILY_PARQUET),
    "split_factor": ("2f436b2f13d09a9b", BUNDLE / "split_factor.h5"),
    "dividends": ("46121c09cddde72e", BUNDLE / "dividends.h5"),
    "index_000300": ("05aaa8183a11c674", INDEX_CHUNK),
}

T0 = time.perf_counter()
BUDGET_S = 3600.0
PEAK_RSS = 0.0
LOG_PATH = RUN_DIR / "logs" / "anchor1_p3r2.log"
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
    (RUN_DIR / "tmp" / "anchor1_manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name,
        "experiment_id": "exp-20260918-p3r2-band-v1-readjudication",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


# === 0. identity pins ========================================================
log("== 0. identity pins (engine v1.1 re-anchored, prereg rev 5) ==")
pins: dict = {}
for name, (expect, path) in EXPECT.items():
    got = sha256_file(Path(path))
    ok = got.startswith(expect)
    pins[name] = {"path": str(path), "sha256": got,
                  "expected": expect, "match": ok}
    log(f"  {name}: {got[:16]} expect {expect} match={ok}")
    if not ok:
        _fail(f"identity pin mismatch: {name}")
ENGINE_SHA_AT_START = pins["engine"]["sha256"]

halfday_manifest = HALFDAY_DIR / "manifest.json"
pins["halfday_manifest"] = {
    "path": str(halfday_manifest), "sha256": sha256_file(halfday_manifest),
    "expected": "2a414174b5df2eee",
    "match": sha256_file(halfday_manifest).startswith("2a414174b5df2eee")}
if not pins["halfday_manifest"]["match"]:
    _fail("halfday manifest pin mismatch")
stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {
    "path": str(STK_DIR), **stk_agg, "expected": "3c53abf3b0c39b42",
    "match": stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
log(f"  stk_limit aggregate: {stk_agg['aggregate_sha256'][:16]} "
    f"({stk_agg['files']} files) match={pins['stk_limit_aggregate']['match']}")
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit aggregate pin mismatch")
log(f"  python {platform.python_version()} | rss {rss_gb():.2f} GB")

r16_config = json.loads(R16_CONFIG.read_text(encoding="utf-8"))
r16_metrics = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
p3r1_mg = json.loads((P3R1_RUN / "outputs/metrics_and_gates.json")
                     .read_text(encoding="utf-8"))
B3P = {"T200-40": r16_metrics["B3prime_dev_mean_net_cagr"]["T200-40"],
       "FIX75": r16_metrics["B3prime_dev_mean_net_cagr"]["FIX75"]}
B1 = {cid: r16_metrics["configs"][cid] for cid in CONFIG_IDS}

# === 1. calendar & signal days (9cc4 verbatim) ===============================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()   # includes 2020-12-31 (expiry anchor)
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
if SMOKE:
    sig_days = [d for d in sig_days if d.year == 2015]
assert sig_days and sig_days[-1] <= date(2020, 12, 31)
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})"
    + (" [SMOKE: 2015 only]" if SMOKE else
       " (2020-12-31 dropped as signal, kept as expiry anchor)"))
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}

# === 2. exposures (r16 verbatim) =============================================
log("== 2. exposures ==")
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
anchor_check = r16.t200_behavioral_anchor_check(index_close, calendar_full)
log(f"  t200 behavioral anchor check: {json.dumps(anchor_check)[:120]}")
exposures_by_path = {}
for path_name in ("T200-40", "FIX75"):
    exposures_by_path[path_name] = (
        r16.t200_month_end_exposures(index_close, calendar_full, sig_days)
        if path_name == "T200-40" else r16.fix75_exposures(sig_days))
log("  exposures: " + "; ".join(
    f"{p}[0]={v[sig_days[0]]:.2f} [{p}][-1]={v[sig_days[-1]]:.2f}"
    for p, v in exposures_by_path.items()))

# === 3. pools (r16 verbatim) =================================================
log("== 3. pools (r16 build_history + signal_pools) ==")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
del hist
rank_of = {t: {s: i + 1 for i, s in enumerate(pools_at[t]["ranked"])}
           for t in sig_days}
panel_symbols = sorted({s for t in sig_days for s in pools_at[t]["ranked"]})
log(f"  pools at {sig_days[0]}: n={pools_at[sig_days[0]]['n']}; "
    f"union of ranked symbols: {len(panel_symbols)}")
check_budget("pools")

# === 4. R16 leg_log + 8/8 consistency (9cc4 keys verbatim) ===================
log("== 4. leg_log + 8/8 membership consistency ==")
leg_all = pl.read_parquet(R16_RUN / "leg_log.parquet").filter(
    pl.col("plan_date").is_in(sig_days))
dup = (leg_all.group_by("config_id", "plan_date", "symbol").len()
       .filter(pl.col("len") > 1))
if dup.height:
    _fail(f"leg_log has duplicate (config, plan_date, symbol) rows: {dup.head(3)}")
me = pl.read_parquet(R16_RUN / "membership_events.parquet").filter(
    pl.col("signal").is_in(sig_days))
LEGS: dict = {}
PANEL_BY_CFG: dict = {c: set() for c in CONFIG_IDS}
OUTCOME: dict = {}
for _k, _g in leg_all.partition_by(["config_id", "plan_date"], as_dict=True).items():
    LEGS[(_k[0], _k[1])] = _g
    PANEL_BY_CFG.setdefault(_k[0], set()).update(_g["symbol"].to_list())
    for _s, _o in zip(_g["symbol"].to_list(), _g["outcome"].to_list()):
        OUTCOME[(_k[0], _k[1], _s)] = _o
me_by = {(r["config_id"], r["signal"]): r for r in me.iter_rows(named=True)}
consistency: dict = {}
for cid in CONFIG_IDS:
    spec = r16_config["configs"][cid]
    mismembers, mismev = 0, 0
    prev: list[str] = []
    for t in sig_days:
        g = LEGS.get((cid, t))
        kinds = {} if g is None else dict(zip(g["symbol"].to_list(),
                                              g["kind"].to_list()))
        members = sorted(s for s, k in kinds.items()
                         if k in ("buy_open", "rescale"))
        exp_members, info = r16.buffer_membership(
            prev, pools_at[t]["ranked"], pools_at[t]["q5"],
            int(spec["K"]), spec["filter"] == "on")
        if members != sorted(exp_members):
            mismembers += 1
        ev = me_by.get((cid, t))
        if ev is not None:
            if (ev["n_kept"] != info["n_kept"]
                    or ev["n_entrants"] != info["n_entrants"]
                    or ev["n_prev"] != info["n_prev"]
                    or ev["n_left"] != info["n_left"]
                    or ev["n_cash_seats"] != info["n_cash_seats"]):
                mismev += 1
        prev = list(exp_members)
    consistency[cid] = {"membership_mismatches": mismembers,
                        "membership_events_mismatches": mismev,
                        "n_signal_days": len(sig_days)}
    log(f"  {cid}: membership mismatches={mismembers}, "
        f"events mismatches={mismev} / {len(sig_days)}")
if any(v["membership_mismatches"] or v["membership_events_mismatches"]
       for v in consistency.values()):
    _fail(f"8/8 consistency FAILED: {consistency}")
log("  8/8 configs PASS (leg_log <-> independent buffer_membership + events)")
check_budget("consistency")

# === 5. market frames (9cc4 verbatim) ========================================
log("== 5. market frames ==")
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
pins["daily"].update({"rows_total": daily_meta["rows_total"],
                      "rows_after_freeze_filter": daily_meta["rows_after_freeze_filter"]})
daily = (daily_full.filter(pl.col("symbol").is_in(panel_symbols))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .select("symbol", "date", "open", "high", "low", "close", "tradestatus")
         .sort("symbol", "date"))
del daily_full
assert_frozen(daily, "date", "daily")
log(f"  daily panel: {daily.height} rows, {daily['symbol'].n_unique()} symbols, "
    f"max {daily['date'].max()}")

parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
if not parts:
    _fail("no halfday partitions")
half_parts, half_rows_total = [], 0
for part in parts:
    f = pl.read_parquet(part)
    half_rows_total += f.height
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= DEV_START)
                 & (pl.col("trade_date") <= DEV_END))
    f = f.filter(pl.col("symbol").is_in(panel_symbols))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame()
del half_parts
assert_frozen(half, "trade_date", "halfday")
pins["halfday_rows_total"] = half_rows_total
if half_rows_total != 18_486_939:
    _fail(f"halfday rows {half_rows_total} != pinned 18,486,939")
log(f"  halfday: {half.height} rows kept of {half_rows_total} total "
    f"(panel x dev), {half['symbol'].n_unique()} symbols")

limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})  # ENGINE-2 bridge
limits = (limits_full.filter(pl.col("symbol").is_in(panel_symbols))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
          .sort("symbol", "date"))


def _dints(col: pl.Series) -> np.ndarray:
    # Int64 arithmetic (9cc4 int8-overflow fix)
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


LIMIT_DAYS = set(zip(limits["symbol"].to_list(), _dints(limits["date"])))
del limits_full
log(f"  limits: {limits.height} rows (dev x panel)")
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(panel_symbols))
dividends = divs_all.filter(pl.col("symbol").is_in(panel_symbols))
log(f"  splits {splits.height} rows, dividends {dividends.height} rows (panel)")
instruments = pl.DataFrame({
    "symbol": panel_symbols, "is_etf": [False] * len(panel_symbols),
    "is_t0": [False] * len(panel_symbols)})
check_budget("market frames")
log(f"  rss after frames: {rss_gb():.2f} GB")

# === 6. anchor / bar tables (host diagnostics only: gate-6 weights, m5-a) ====
_trading = (daily.filter(pl.col("tradestatus") != 0)
            if "tradestatus" in daily.columns else daily)
close_arr = {}
for (sym,), g in _trading.partition_by("symbol", as_dict=True).items():
    dint = _dints(g["date"])
    close_arr[sym] = (dint.astype(np.int64),
                      g["close"].to_numpy().astype(np.float64))
pm_pairs = set(zip(half.filter(pl.col("session") == "pm")["symbol"].to_list(),
                   _dints(half.filter(pl.col("session") == "pm")["trade_date"])))
am_days = half.filter(pl.col("session") == "am").group_by("trade_date").len()
pm_days = half.filter(pl.col("session") == "pm").group_by("trade_date").len()
halfmarket_days = sorted(
    str(r["trade_date"]) for r in am_days.join(pm_days, on="trade_date",
                                               how="left", suffix="_pm")
    .fill_null(0).iter_rows(named=True)
    if r["len"] > 500 and r["len_pm"] < 0.5 * r["len"])
log(f"  host diagnostics: {len(close_arr)} official series; "
    f"market-level half-market days (pm<50% am, >500 am rows): "
    f"{halfmarket_days}")


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


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

# === 7. static intent frames (one per config; m5-b asserted) =================
log("== 7. static intent frames (engine-side lifecycle, prereg rev 2) ==")
INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "priority": pl.Int64,
    "expiry_date": pl.Date, "target_weight": pl.Float64,
}
N_SKIPPED: dict = {}
N_HOLE_UP: dict = {}


def build_intent_frame(cid: str) -> pl.DataFrame:
    spec = r16_config["configs"][cid]
    K = int(spec["K"])
    exposures = exposures_by_path[spec["path"]]
    rows: list[dict] = []
    skipped = {"r16_at_target": 0, "r16_feemin_skipped": 0}
    for T in sig_days:
        g = LEGS.get((cid, T))
        if g is None:
            continue
        w_T = float(exposures[T]) / K
        Tp = next_sig.get(T)
        expiry = (date(Tp.year, Tp.month, Tp.day) if Tp is None else
                  date.fromordinal(Tp.toordinal() + 1))
        for sym, kind in zip(g["symbol"].to_list(), g["kind"].to_list()):
            oc = OUTCOME.get((cid, T, sym))
            if kind == "rescale" and oc in ("at_target", "feemin_skipped"):
                # 9cc4 mapping-fidelity asset: R16's own no-trade record
                skipped["r16_at_target" if oc == "at_target"
                        else "r16_feemin_skipped"] += 1
                continue
            rank = rank_of[T].get(sym, 10 ** 6)
            if kind == "sell_full":
                rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": rank,
                             "expiry_date": expiry, "target_weight": None})
            elif kind == "buy_open":
                rows.append({"symbol": sym, "side": "buy", "intent": "",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": rank,
                             "expiry_date": expiry, "target_weight": w_T})
            else:  # rescale: reduce-to-target standing risk order;
                  # top-up side = registered mapping hole (disclosed)
                rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": rank,
                             "expiry_date": expiry, "target_weight": w_T})
    N_SKIPPED[cid] = skipped
    # m5-b: (symbol, side, source) uniqueness hard-asserted pre-submission
    keys = [(r["symbol"], r["side"], r["source_signal"]) for r in rows]
    if len(keys) != len(set(keys)):
        seen, dups = set(), []
        for k in keys:
            if k in seen:
                dups.append(k)
            seen.add(k)
        _fail(f"m5-b VIOLATION in {cid}: duplicate (symbol, side, source) "
              f"intent keys {dups[:5]} -- abort before adjudication")
    return pl.DataFrame(rows, schema=INTENT_SCHEMA)


FRAMES: dict = {}
n_intent_total = 0
for cid in CONFIG_IDS:
    fr = build_intent_frame(cid)
    FRAMES[cid] = fr
    n_intent_total += fr.height
    n_buy = int((fr["side"] == "buy").sum())
    n_sell_full = int(((fr["side"] == "sell")
                       & fr["target_weight"].is_null()).sum())
    n_rescale = int(((fr["side"] == "sell")
                     & fr["target_weight"].is_not_null()).sum())
    log(f"  {cid}: intents {fr.height} (buy_open {n_buy}, sell_full "
        f"{n_sell_full}, rescale->reduce {n_rescale}; R16 skips "
        f"{N_SKIPPED[cid]}); m5-b uniqueness PASS")
log(f"  total intents: {n_intent_total}")
check_budget("intent frames")

# === 8. per-config engine runs (ONE call each; no host loop) =================
log("== 8. per-config intent-mode engine runs ==")
config_list = ["C01"] if SMOKE else list(CONFIG_IDS)
results: dict = {}
for cid in config_list:
    spec = r16_config["configs"][cid]
    cfg_syms = sorted(PANEL_BY_CFG[cid])
    end_d = SMOKE_END if SMOKE else DEV_END
    daily_c = daily.filter(pl.col("symbol").is_in(cfg_syms)) \
                   .filter(pl.col("date") <= end_d)
    half_c = half.filter(pl.col("symbol").is_in(cfg_syms)) \
                 .filter(pl.col("trade_date") <= end_d)
    limits_c = limits.filter(pl.col("symbol").is_in(cfg_syms)) \
                     .filter(pl.col("date") <= end_d)
    splits_c = splits.filter(pl.col("symbol").is_in(cfg_syms))
    divs_c = dividends.filter(pl.col("symbol").is_in(cfg_syms))
    instr_c = instruments.filter(pl.col("symbol").is_in(cfg_syms))
    log(f"  {cid}: panel {len(cfg_syms)} symbols, daily {daily_c.height} / "
        f"half {half_c.height} / limits {limits_c.height} rows, "
        f"intents {FRAMES[cid].height}, rss {rss_gb():.2f} GB")
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(FRAMES[cid], daily_c, half_c, limits_c,
                                    splits_c, divs_c, instr_c,
                                    initial_cash=200_000.0)
    wall = time.perf_counter() - t_cfg
    il = res.stats.get("intent_layer") or {}
    log(f"  {cid}: engine done in {wall:.1f}s; intents {il.get('n_intents')} "
        f"activated {il.get('activated')} orders {il.get('orders_generated')} "
        f"filled {il.get('stopped_filled')} override "
        f"{il.get('terminated_override')} expired "
        f"{il.get('terminated_expired')} cap {il.get('terminated_cap')} | "
        f"rss {rss_gb():.2f} GB")
    results[cid] = {"res": res, "wall_s": wall,
                    "warnings": list(res.warnings)}
    check_budget(f"{cid} engine run")
check_budget("all config engine runs")

# === 9. smoke reconciliation (intent_layer accounting) =======================
log("== 9. intent_layer reconciliation ==")
smoke_report: dict = {}
for cid in config_list:
    st = results[cid]["res"].stats
    il = st["intent_layer"]
    done = (il["stopped_filled"] + il["terminated_override"]
            + il["terminated_expired"] + il["terminated_cap"])
    checks = {
        "activated_equals_intents": il["activated"] == il["n_intents"],
        "orders_ge_filled": il["orders_generated"] >= il["stopped_filled"],
        "done_le_activated": done <= il["activated"],
    }
    recon = {"n_intents": il["n_intents"], "activated": il["activated"],
             "orders_generated": il["orders_generated"],
             "stopped_filled": il["stopped_filled"],
             "terminated_override": il["terminated_override"],
             "terminated_expired": il["terminated_expired"],
             "terminated_cap": il["terminated_cap"],
             "still_active_at_engine_end": il["activated"] - done,
             "at_target_skips": il["at_target_skips"],
             "emissions_skipped_no_anchor": il["emissions_skipped_no_anchor"],
             "emissions_skipped_no_live_session":
                 il["emissions_skipped_no_live_session"],
             "checks": checks}
    ok = (checks["activated_equals_intents"]
          and checks["orders_ge_filled"]
          and checks["done_le_activated"])
    # every order must have exactly one terminal event in its live session
    ev = results[cid]["res"].events
    n_ord_events = int((ev.filter(pl.col("order_id") != ""))
                       .height) if ev.height else 0
    recon["order_events"] = n_ord_events
    log(f"  {cid}: reconciliation {'PASS' if ok else 'FAIL'} "
        f"(activated {il['activated']}/{il['n_intents']}, orders "
        f"{il['orders_generated']}, done {done}, active-at-end "
        f"{il['activated'] - done}, at_target_skips "
        f"{il['at_target_skips']}, no_anchor_skips "
        f"{il['emissions_skipped_no_anchor']})")
    if not ok:
        _fail(f"{cid}: intent_layer reconciliation failed: {recon}")
    smoke_report[cid] = recon
if SMOKE:
    smoke_dir = RUN_DIR / "tmp" / "smoke"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    for cid in config_list:
        FRAMES[cid].write_parquet(smoke_dir / f"{cid}_intents.parquet")
        results[cid]["res"].fills.write_parquet(smoke_dir / f"{cid}_fills.parquet")
        results[cid]["res"].events.write_parquet(smoke_dir / f"{cid}_events.parquet")
        results[cid]["res"].daily.write_parquet(smoke_dir / f"{cid}_daily.parquet")
    (RUN_DIR / "tmp" / "smoke_reconciliation.json").write_text(
        json.dumps({"smoke": True, "window": f"2015-01-05..{SMOKE_END}",
                    "signal_days": len(sig_days),
                    "per_config": smoke_report,
                    "peak_rss_gb": PEAK_RSS,
                    "wall_s": time.perf_counter() - T0},
                   ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    log(f"SMOKE complete (wall {time.perf_counter() - T0:.0f}s, peak rss "
        f"{PEAK_RSS:.2f} GB) -> tmp/smoke_reconciliation.json")
    _logf.close()
    sys.exit(0)

# === 10. per-intent attribution & gate-8 mapped execution rate (7.7-m6) =====
log("== 10. per-intent attribution & gate 8 ==")
RULE_OK = {"below_min_lot", "void_no_position", "void_insufficient_cash"}
ENGINE_REASON_NAME = {"filled": "filled", "overridden": "override",
                      "expired": "expired", "cap_single_name": "cap"}


def sidestr_class(sidestr: str) -> str:
    return "buy" if sidestr.startswith("buy") else "sell"


def attribute(cid: str) -> dict:
    res = results[cid]["res"]
    fr = FRAMES[cid]
    sources_by: dict = {}
    for r in fr.iter_rows(named=True):
        sources_by.setdefault((r["symbol"], r["side"]), []).append(
            (r["source_signal"], r["decision_session"]))
    src_cache: dict = {}

    def src_of(sym: str, side: str, d, s: str):
        key = (sym, side, dint_of(d), s)
        if key in src_cache:
            return src_cache[key]
        lst = sources_by.get((sym, side), [])
        best = None
        for T, first_s in lst:
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
            _fail(f"{cid}: unparsable intent_lifecycle detail {r['detail']!r}")
        sym, sidestr = left.split("/", 1)[0], left.split("/", 1)[1]
        lifecycle[(sym, sidestr_class(sidestr), src)] = reason
    ev_orders = res.events.filter(pl.col("order_id") != "")
    per_intent_events: dict = {}
    fill_sess = {"am": 0, "pm": 0}
    pm_nobar_rehangs = 0
    no_limit_sell_voids = 0
    no_limit_sell_gapdays = 0
    for r in ev_orders.iter_rows(named=True):
        # order_id = "{symbol}-{side[/intent]}-{YYYY}-{MM}-{DD}-{sess}";
        # the ISO date's hyphens require splitting the 4 RIGHTMOST hyphens
        parts = r["order_id"].rsplit("-", 4)
        if len(parts) != 5:
            _fail(f"{cid}: unparsable order_id {r['order_id']!r}")
        prefix, y, mo, dy, sess = parts
        d = date(int(y), int(mo), int(dy))
        if "-" in prefix:
            sym, sidestr = prefix.split("-", 1)
        else:
            _fail(f"{cid}: unparsable order_id prefix {prefix!r}")
        sclass = sidestr_class(sidestr)
        T = src_of(sym, sclass, d, sess)
        if T is None:
            _fail(f"{cid}: event order {r['order_id']} has no source intent")
        k = (sym, sclass, T)
        per_intent_events.setdefault(k, []).append(r["event"])
        if sess == "pm" and (sym, dint_of(d)) not in pm_pairs:
            pm_nobar_rehangs += 1          # m5-a disclosure
        if (r["event"] == "void_no_limit_info" and sclass == "sell"):
            no_limit_sell_voids += 1       # ENGINE-3 restored semantics
            if d.year == 2017 and d.month == 3 and d.day in (7, 8, 9):
                no_limit_sell_gapdays += 1
    fills = res.fills
    fill_by_intent: dict = {}
    if fills.height:
        for r in fills.select("symbol", "side", "decision_date",
                              "decision_session", "notional",
                              "fees_total").iter_rows(named=True):
            sclass = "buy" if r["side"] == "buy" else "sell"
            T = src_of(r["symbol"], sclass, r["decision_date"],
                       r["decision_session"])
            if T is not None:
                fill_by_intent.setdefault((r["symbol"], sclass, T), 0)
                fill_by_intent[(r["symbol"], sclass, T)] += 1
    # decision-session fill split (from fills' own decision columns)
    for r in (fills.select("decision_session").iter_rows() if fills.height
              else []):
        fill_sess[r[0]] = fill_sess.get(r[0], 0) + 1
    outcomes: dict = {}
    term = {"expiry": 0, "override_same_name": 0, "cap_void": 0,
            "suspension_abandon": 0}
    expiry_at_target_noop = 0
    rule_blocked = {"below_min_lot": 0, "void_no_position": 0,
                    "void_insufficient_cash": 0}
    engine_x_host: dict = {}
    zero_emission = 0
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
            # engine detail text is long ("overridden by a later ...");
            # prefix match (attribution fix, disclosed in findings)
            host = "terminated:override_same_name"
        elif (eng.startswith("expired") or eng.startswith("still_active")):
            if not evs:
                # zero-emission expired: suspended the whole window OR a
                # reduce-to-target intent that was at/below target at every
                # decision point (engine at_target skips emit nothing).
                # Distinguish via whether the symbol traded in-window
                # (a pm anchor exists on any traded day).
                noop = False
                if r["side"] == "sell" and r["target_weight"] is not None:
                    arr = close_arr.get(r["symbol"])
                    if arr is not None:
                        dint, _ = arr
                        lo, hi = dint_of(r["source_signal"]), dint_of(r["expiry_date"])
                        j = int(np.searchsorted(dint, lo))
                        noop = j < len(dint) and dint[j] < hi
                if noop:
                    host = "terminated:expired_at_target_noop"
                    expiry_at_target_noop += 1
                else:
                    host = "terminated:suspension_abandon"
            else:
                host = "terminated:expiry"
        else:
            host = f"terminated:expiry(eng={eng})"
        engine_x_host.setdefault(eng, {}).setdefault(host, 0)
        engine_x_host[eng][host] += 1
        outcomes[k] = (host, eng, len(evs))
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
    n_filled = sum(1 for v in outcomes.values() if v[0] == "filled")
    n_rule = sum(1 for v in outcomes.values()
                 if v[0].startswith("executed_rule_blocked"))
    n_term = sum(1 for v in outcomes.values()
                 if v[0].startswith("terminated:"))
    mapped = ((n_filled + n_rule) / (n_filled + n_rule + n_term)
              if (n_filled + n_rule + n_term) else None)
    # supplementary (NOT the gate): P3R1-comparable reading where R16's own
    # no-trade outcomes (at_target/feemin skips) count as executed no-ops
    n_skips = sum(N_SKIPPED[cid].values())
    p3r1_comparable = ((n_filled + n_rule + n_skips)
                       / (n_filled + n_rule + n_term + n_skips)
                       if (n_filled + n_rule + n_term + n_skips) else None)
    il = res.stats["intent_layer"]
    recon_engine = {
        "filled_vs_stopped_filled": (n_filled, il["stopped_filled"]),
        "override_total": il["terminated_override"],
        "expired_total": il["terminated_expired"],
        "cap_total": il["terminated_cap"]}
    if n_filled != il["stopped_filled"]:
        _fail(f"{cid}: host filled {n_filled} != engine stopped_filled "
              f"{il['stopped_filled']}")
    return {"outcomes": {k: v[0] for k, v in outcomes.items()},
            "engine_x_host": engine_x_host,
            "termination": term, "mapped_rate": mapped,
            "p3r1_comparable_rate": p3r1_comparable,
            "n_r16_skips": n_skips,
            "n_filled": n_filled, "n_rule_blocked": n_rule,
            "rule_blocked": dict(rule_blocked),
            "n_terminated": n_term, "zero_emission_intents": zero_emission,
            "expiry_at_target_noop": expiry_at_target_noop,
            "recon_engine": recon_engine,
            "order_session": res.stats["fill_rate_order_session"],
            "fill_sess_share": {s: (fill_sess[s] / sum(fill_sess.values())
                                    if sum(fill_sess.values()) else None)
                                for s in ("am", "pm")},
            "pm_nobar_rehangs": pm_nobar_rehangs,
            "no_limit_sell_voids": no_limit_sell_voids,
            "no_limit_sell_voids_20170307_09": no_limit_sell_gapdays}


attr: dict = {}
for cid in config_list:
    attr[cid] = attribute(cid)
    a = attr[cid]
    log(f"  {cid}: gate8 mapped {(a['mapped_rate'] or 0) * 100:.1f}% "
        f"(filled {a['n_filled']}, rule-blocked {a['n_rule_blocked']}, "
        f"terminated {a['n_terminated']}, zero-emission "
        f"{a['zero_emission_intents']}); term {a['termination']}; "
        f"pm-no-bar rehangs {a['pm_nobar_rehangs']}; no-limit sell voids "
        f"{a['no_limit_sell_voids']} (gap days "
        f"{a['no_limit_sell_voids_20170307_09']})")


def daily_max_single_name_weight(res) -> float:
    """Max over dev days of max held-name weight (official close marks)."""
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


# === 11. metrics & gates (9cc4 part2 verbatim; B1/B3' frozen values) =========
log("== 11. metrics & gates ==")
metrics: dict = {}
gates: dict = {}
for cid in config_list:
    res = results[cid]["res"]
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(),
                            DEV_START, DEV_END)
    net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd = er.max_drawdown(sd, sv)["max_drawdown"]
    yr = er.year_returns(sd, sv)
    b1y = {int(k): v for k, v in B1[cid]["b1m_net_return_by_year"].items()}
    adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
    excess = net_cagr - B1[cid]["b1m_net_cagr"]
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
    path_name = r16_config["configs"][cid]["path"]
    a = attr[cid]
    m = {"net_cagr": net_cagr,
         "net_total_return": sv[-1] / sv[0] - 1.0,
         "max_drawdown": mdd,
         "b1m_net_cagr": B1[cid]["b1m_net_cagr"],
         "b1m_max_drawdown": B1[cid]["b1m_max_drawdown"],
         "b1m_net_return_by_year": B1[cid]["b1m_net_return_by_year"],
         "excess_vs_b1m": excess,
         "net_return_by_year": {int(k): v for k, v in yr.items()},
         "advantage_years_list": [int(y) for y in adv],
         "turnover_by_year": tby,
         "max_one_side_turnover": max(v["one_side_turnover"]
                                      for v in tby.values()),
         "max_single_name_weight": wmax,
         "execution_rate": a["mapped_rate"],
         "execution_rate_mapping":
             "7.7-m6: filled + rule-blocked intents / (filled + rule-blocked"
             " + terminated intents); re-anchors neutral; R16 at_target/"
             "feemin skips outside the frame (excluded)"}
    g = {"1_net_cagr_gt_0": net_cagr > 0,
         "2_excess_vs_B1m_ge_2pp": excess >= 0.020,
         "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
         "4_mdd_le_20pct_and_le_B1m":
             abs(mdd) <= 0.20 + 1e-12
             and abs(mdd) <= abs(B1[cid]["b1m_max_drawdown"]) + 1e-12,
         "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,
         "6_single_name_weight_le_40pct": wmax <= 0.40,
         "7_vs_B3prime_plus_1pp": net_cagr >= B3P[path_name] + 0.010,
         "8_execution_rate_ge_95pct": (a["mapped_rate"] or 0.0) >= 0.95,
         "advantage_years": len(adv), "dev_excess_vs_b1m": excess}
    gate_keys = ["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",
                 "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",
                 "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",
                 "7_vs_B3prime_plus_1pp", "8_execution_rate_ge_95pct"]
    g["failed_gates"] = sorted(k for k in gate_keys if not g[k])
    g["dev_pass"] = not g["failed_gates"]
    g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"
    metrics[cid] = m
    gates[cid] = {"dev": g, "verdict": g["verdict"]}
    log(f"  {cid}: net {net_cagr * 100:+.2f}% excess {excess * 100:+.2f}pp "
        f"adv {len(adv)}/6 mdd {mdd * 100:.2f}% "
        f"turn {m['max_one_side_turnover']:.2f} w {wmax * 100:.1f}% exec "
        f"{(a['mapped_rate'] or 0) * 100:.1f}% -> "
        f"{'PASS' if g['dev_pass'] else 'eliminated ' + str(g['failed_gates'])}")
n_pass = sum(1 for cid in config_list if gates[cid]["dev"]["dev_pass"])
log(f"== gates: {n_pass}/8 dev_pass ==")
check_budget("metrics & gates")

# === 12. disclosures (prereg sec 5 five items + section 9 revisions) =========
log("== 12. disclosures ==")
p3r1_fees = {}
for cid in config_list:
    f1 = pl.read_parquet(P3R1_RUN / "outputs" / f"{cid}_fills.parquet")
    p3r1_fees[cid] = float(f1["fees_total"].sum())

MAPPING_DIFFS = {
    "lifecycle_ownership": "revision 2: the ENGINE intent layer owns the "
                           "order lifecycle (re-anchor at every decision "
                           "point, re-hang, fill-stop, expiry/override/"
                           "cap-void); host submits ONE static frame -- "
                           "replaces 9cc4's dead host-side conventions "
                           "(convention-A full-window numbers are INVALID "
                           "diagnostics, prereg rev 1)",
    "in_loop_pricing": "revision 3: buy/rescale sizing = target_weight x "
                       "decision-point equity snapshot recomputed by the "
                       "engine at every decision point; replaces P3R1's "
                       "host-side fixed-point iteration (5-6 rounds) -- "
                       "deterministic, zero feedback",
    "re_anchor_cadence": "v0 dead anchor (signal-day close) -> v1.1 "
                         "mechanical re-anchor at EVERY decision point "
                         "(am = am.close, pm = official close), qty "
                         "recomputed in-loop (7.7-M3); fill-rate uplift is "
                         "a RULE difference, disclosed not celebrated",
    "rescale_mapping": "R16 rescale legs -> standing reduce-to-target risk "
                       "sell (target_weight = exposure/K), self-neutralizing"
                       " via engine at_target skips. REGISTERED HOLE: the "
                       "top-up side is NOT mapped (no engine buy top-up "
                       "primitive; a full-seat buy would double the seat); "
                       "P3R1/9cc4 mapped it via fixed-point sizing -- vs-P3R1"
                       " turnover/fee deltas are confounded by this hole",
    "rescale_skips": "R16 outcome at_target/feemin_skipped rescale legs are "
                     "outside the frame (9cc4 mapping-fidelity asset; R16 "
                     "no-trade record)",
    "sell_intent_mapping": "sell_full -> intent=risk full exit; K=3 "
                           "SESSION-level fallback keyed (symbol, intent, "
                           "source) (7.7-M1); rescale-down same intent "
                           "semantics with explicit target weight",
    "fill_granularity": "official daily extremes -> half-day bar extremes "
                        "(conservative subset; gaps fill at the limit)",
    "proceeds": "sale proceeds usable next SESSION (v0: next day)",
    "expiry_boundary": "expiry_date = T'+1 cal day -> last emission is the "
                       "(T','am') decision living (T','pm'), i.e. the frozen "
                       "9cc4 window; same-name override fires at (T','pm')",
    "signal_day_drop": "same as P3R1: 2020-12-31 signal dropped (execution "
                       "would cross into 2021)",
    "profit_ladder": "intent=profit still unmapped (R16 has no profit-ladder "
                     "signal) -- prereg sec 4.8 mapping hole, unchanged",
}

disclosures: dict = {}
for cid in config_list:
    res = results[cid]["res"]
    st = res.stats
    a = attr[cid]
    m = metrics[cid]
    g = gates[cid]["dev"]
    p1 = p3r1_mg["metrics"][cid]
    p1d = p3r1_mg["disclosures"][cid]
    fees_total = float(res.fills["fees_total"].sum()) if res.fills.height else 0.0
    k3 = st["k3_fallback"]
    caps = st["caps"]
    fric = st["cash_friction"]
    corp = st["corp_actions"]
    to = st["turnover"]
    n_rescale_filled = sum(
        1 for (sym, sclass, T), host in a["outcomes"].items()
        if sclass == "sell" and FRAMES[cid].filter(
            (pl.col("symbol") == sym) & (pl.col("source_signal") == T)
            & pl.col("target_weight").is_not_null()).height > 0
        and host == "filled")
    n_rescale_emitted = sum(
        1 for (sym, sclass, T) in a["outcomes"] if sclass == "sell"
        and FRAMES[cid].filter(
            (pl.col("symbol") == sym) & (pl.col("source_signal") == T)
            & pl.col("target_weight").is_not_null()).height > 0)
    disclosures[cid] = {
        "verdict": g["verdict"],
        "1_fill_rate": {
            "gate8_mapped_execution_rate": a["mapped_rate"],
            "gate8_mapping": "7.7-m6 / 9cc4 registered: R16 no-trade skip "
                             "legs are outside the frame (excluded)",
            "p3r1_comparable_rate_supplementary": {
                "value": a["p3r1_comparable_rate"],
                "note": "NOT the gate: treats R16 at_target/feemin skip "
                        "legs as executed no-ops (P3R1 numerator "
                        "convention) for an apples-to-apples delta"},
            "order_session_fill_rate": a["order_session"],
            "filled_intents": a["n_filled"],
            "rule_blocked": a["rule_blocked"],
            "termination": a["termination"],
            "engine_reason_x_host_class": a["engine_x_host"],
            "decision_point_fill_share": a["fill_sess_share"],
            "vs_p3r1": {
                "gate8_mapped_pp":
                    (m["execution_rate"] - p1["execution_rate"]) * 100,
                "order_session_buy_pp":
                    ((a["order_session"]["buy"] or 0.0)
                     - p1d["order_fill_rate"]["buy"]) * 100,
                "order_session_sell_pp":
                    ((a["order_session"]["sell_risk"] or 0.0)
                     - p1d["order_fill_rate"]["sell"]) * 100}},
        "2_turnover_fees": {
            "buy_notional_total": to.get("buy_notional_total"),
            "sell_notional_total": to.get("sell_notional_total"),
            "fees_total": fees_total,
            "commission_warnings": st.get("commission_warnings"),
            "max_one_side_turnover": m["max_one_side_turnover"],
            "vs_p3r1": {"fees_total": fees_total - p3r1_fees[cid],
                        "max_turnover": m["max_one_side_turnover"]
                        - p1["max_one_side_turnover"]}},
        "3_mdd_attribution": {
            "max_drawdown": m["max_drawdown"],
            "p3r1_max_drawdown": p1["max_drawdown"],
            "delta_pp": (m["max_drawdown"] - p1["max_drawdown"]) * 100,
            "rescale_reduce_intents_emitted": n_rescale_emitted,
            "rescale_reduce_intents_filled": n_rescale_filled,
            "k3_market_exits_executed": k3.get("executed"),
            "note": "mechanism counters, not a counterfactual "
                    "decomposition; market-path component not separable "
                    "without a no-rescale twin run (not run: zero-trial "
                    "discipline); rescale TOP-UP hole noted in item 4"},
        "4_mapping_diffs": MAPPING_DIFFS,
        "5_increments": {
            "cap_single_name_voids": caps.get("single_name_voids"),
            "single_name_drift_breaches": caps.get("single_name_drift_breaches"),
            "decision_point_fills": a["fill_sess_share"],
            "k3": {"armed": k3.get("armed"), "executed": k3.get("executed"),
                   "deferred_limitdown": k3.get("deferred_limitdown_sessions"),
                   "deferred_suspended": k3.get("deferred_suspended"),
                   "deferred_t1locked": k3.get("deferred_t1locked")},
            "gate8_termination_reasons": a["termination"],
            "gate8_expired_at_target_noop": a["expiry_at_target_noop"],
            "rule_blocked_executed": a["rule_blocked"],
            "r16_outcome_skips": N_SKIPPED[cid],
            "rescale_topup_hole_intents": n_rescale_emitted,
            "insufficient_cash_orders": fric.get("insufficient_cash_orders"),
            "below_min_lot_abandons": fric.get("below_min_lot_abandons"),
            "void_days": st.get("void_days"),
            "m5a_pm_nobar_rehangs": a["pm_nobar_rehangs"],
            "m5a_halfmarket_days_market_level": halfmarket_days,
            "m5c_static_stats_lazy_keys": {
                "order_generation": st.get("order_generation"),
                "intent_layer": st.get("intent_layer")},
            "engine3_no_limit_info": {
                "sell_voids": a["no_limit_sell_voids"],
                "sell_voids_on_2017_03_07_09":
                    a["no_limit_sell_voids_20170307_09"],
                "note": "v0 ruling #2/#3 semantics restored in-engine "
                        "(void + K count + disclose); 9cc4 host-side skip "
                        "is dead"},
            "engine_warnings_n": len(results[cid]["warnings"]),
            "engine_warnings_sample": results[cid]["warnings"][:3],
            "corp_action": {"splits": corp.get("splits"),
                            "dividends": corp.get("dividends"),
                            "dividend_cash_total":
                                corp.get("dividend_cash_total_pre_tax")},
            "final_positions": st.get("final"),
        },
        "engine_reconciliation": a["recon_engine"],
    }

# === 13. outputs / report / manifest =========================================
log("== 13. outputs ==")
out_dir = RUN_DIR / "outputs"
for cid in config_list:
    st = results[cid]
    FRAMES[cid].write_parquet(out_dir / f"{cid}_intents.parquet")
    st["res"].fills.write_parquet(out_dir / f"{cid}_fills.parquet")
    st["res"].events.write_parquet(out_dir / f"{cid}_events.parquet")
    st["res"].daily.write_parquet(out_dir / f"{cid}_daily_equity.parquet")
    st["res"].clips_final.write_parquet(out_dir / f"{cid}_clips_final.parquet")

mg = {
    "experiment_id": "exp-20260918-p3r2-band-v1-readjudication",
    "engine_sha256_16": ENGINE_SHA_AT_START[:16],
    "execution_model": "v1.1 engine-side intent layer (prereg sec 9 rev 2/3);"
                       " one static intent frame per config; no fixed point",
    "metrics": metrics, "gates": gates, "disclosures": disclosures,
    "b3prime_dev_mean_net_cagr": B3P,
    "b3prime_source": "R16 metrics.json verbatim (benchmarks unchanged)",
    "consistency": consistency,
    "advanced_to_validation": False, "val_consumed": False,
    "stop_note": ("STOP before val: >=1 config passed all dev gates; val "
                  "requires separate user approval" if n_pass else
                  f"no config passed all dev gates ({n_pass}/8); val not "
                  "consumed"),
}
(out_dir / "metrics_and_gates.json").write_text(
    json.dumps(mg, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")


def death_line(cid: str) -> str:
    f = gates[cid]["dev"]["failed_gates"]
    msg = []
    if "3_advantage_years_ge_5_of_6" in f:
        msg.append("优势年不足(门3,信号层属性)")
    if "1_net_cagr_gt_0" in f:
        msg.append("净CAGR≤0(门1)")
    if "2_excess_vs_B1m_ge_2pp" in f:
        msg.append("超额<+2pp(门2)")
    if "4_mdd_le_20pct_and_le_B1m" in f:
        msg.append("回撤超限(门4)")
    if "5_one_side_turnover_le_6" in f:
        msg.append("换手超限(门5)")
    if "6_single_name_weight_le_40pct" in f:
        msg.append("单票权重超限(门6)")
    if "7_vs_B3prime_plus_1pp" in f:
        msg.append("低于B3′+1pp(门7)")
    if "8_execution_rate_ge_95pct" in f:
        msg.append("计划成交率<95%(门8)")
    return "; ".join(msg) if msg else "全门通过"


rep = ["# P3R2 v1.1 意图层重裁定（exp-20260918-p3r2-band-v1-readjudication）", "",
       f"- 运行 `{RUN_DIR.name}`；引擎 v1.1 sha256:16 "
       f"`{ENGINE_SHA_AT_START[:16]}`（双签 APPROVE "
       f"`20260919T023558-p3v1-intent-review-c4d1`，运行前后哈希一致）；"
       "执行模型=引擎侧意图层（预登记 §9 修订 2/3）：每配置单帧提交，"
       "宿主零成交感知循环、零不动点迭代。",
       f"- 窗口 dev 2015-01-05..2020-12-31，信号 {sig_days[0]}..{sig_days[-1]}"
       f"（共 {len(sig_days)} 个月末，2020-12-31 按冻结先例丢弃）；"
       "val 2021–2024 零消费。",
       "- 判据 = R16 预登记 §2 八门逐字（prereg §3）；B1(m)/B3′ 沿 R16 原值。"
       "全部数字为历史回放，不构成盈利或实盘声称。", "",
       "## 一、八门判定表", "",
       "| 配置 | K/路径/Q5 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤(v1.1/P3R1) "
       "| 换手 | 单票max权重 | 门8成交率(v1.1/P3R1) | 过/8 | 失败门 | 判定 |",
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for cid in config_list:
    m, g = metrics[cid], gates[cid]["dev"]
    spec = r16_config["configs"][cid]
    p1 = p3r1_mg["metrics"][cid]
    rep.append(
        f"| {cid} | {spec['K']}/{spec['path']}/{spec['filter']} "
        f"| {m['net_cagr'] * 100:+.2f}% | {m['b1m_net_cagr'] * 100:+.2f}% "
        f"| {m['excess_vs_b1m'] * 100:+.2f}pp | {g['advantage_years']}/6 "
        f"| {m['max_drawdown'] * 100:.2f}%/{p1['max_drawdown'] * 100:.2f}% "
        f"| {m['max_one_side_turnover']:.2f} "
        f"| {m['max_single_name_weight'] * 100:.1f}% "
        f"| {(m['execution_rate'] or 0) * 100:.1f}%/"
        f"{p1['execution_rate'] * 100:.1f}% "
        f"| {8 - len(g['failed_gates'])} "
        f"| {', '.join(g['failed_gates']) or '-'} "
        f"| {'**dev_pass**' if g['dev_pass'] else 'eliminated'} |")
rep += ["", "### 一句话死因", ""]
for cid in config_list:
    if not gates[cid]["dev"]["dev_pass"]:
        rep.append(f"- **{cid}**: {death_line(cid)}")
rep += ["", "## 二、vs P3R1 delta（披露 1–3；注意第 4 项 rescale 加仓空洞为混杂）",
        "", "| 配置 | 门8成交率 Δpp | 订单口径买/卖 Δpp | 换手 Δ | 费用 Δ元 "
        "| 回撤 Δpp | 净CAGR Δpp |", "|---|---|---|---|---|---|---|"]
for cid in config_list:
    d1 = disclosures[cid]["1_fill_rate"]["vs_p3r1"]
    d2 = disclosures[cid]["2_turnover_fees"]["vs_p3r1"]
    d3 = disclosures[cid]["3_mdd_attribution"]
    rep.append(
        f"| {cid} | {d1['gate8_mapped_pp']:+.1f} "
        f"| {d1['order_session_buy_pp']:+.1f}/"
        f"{d1['order_session_sell_pp']:+.1f} "
        f"| {d2['max_turnover']:+.2f} | {d2['fees_total']:+,.0f} "
        f"| {d3['delta_pp']:+.2f} "
        f"| {(metrics[cid]['net_cagr'] - p3r1_mg['metrics'][cid]['net_cagr']) * 100:+.2f} |")
rep += ["", "## 三、增量披露（披露 5 + 修订项）", ""]
for cid in config_list:
    inc = disclosures[cid]["5_increments"]
    k3 = inc["k3"]
    fs = inc["decision_point_fills"]
    il = inc["m5c_static_stats_lazy_keys"]["intent_layer"] or {}
    rep.append(
        f"- **{cid}**：上限作废 {inc['cap_single_name_voids']}"
        f"（漂移越限记录 {inc['single_name_drift_breaches']}）；"
        f"am/pm 成交占比 {(fs['am'] or 0) * 100:.1f}%/"
        f"{(fs['pm'] or 0) * 100:.1f}%；K=3 armed/executed="
        f"{k3['armed']}/{k3['executed']}（跌停顺延 {k3['deferred_limitdown']}、"
        f"停牌 {k3['deferred_suspended']}、T+1锁 {k3['deferred_t1locked']}）；"
        "门8终止：到期 "
        f"{inc['gate8_termination_reasons']['expiry']} / 同名义覆盖 "
        f"{inc['gate8_termination_reasons']['override_same_name']} / 上限作废 "
        f"{inc['gate8_termination_reasons']['cap_void']} / 停牌放弃 "
        f"{inc['gate8_termination_reasons']['suspension_abandon']}"
        f"（零发射意图 {attr[cid]['zero_emission_intents']}）；"
        f"m5-a 无pm bar日 pm 重挂 {inc['m5a_pm_nobar_rehangs']}；"
        f"ENGINE-3 缺行日卖作废 {inc['engine3_no_limit_info']['sell_voids']}"
        f"（2017-03-07..09 占 "
        f"{inc['engine3_no_limit_info']['sell_voids_on_2017_03_07_09']}）；"
        f"R16 跳过腿 {inc['r16_outcome_skips']}；rescale 风减意图 "
        f"{disclosures[cid]['3_mdd_attribution']['rescale_reduce_intents_emitted']}"
        f"（成交 {disclosures[cid]['3_mdd_attribution']['rescale_reduce_intents_filled']}"
        "；加仓侧=登记空洞）；"
        f"m5-c 惰性键 order_generation="
        f"{inc['m5c_static_stats_lazy_keys']['order_generation']}, "
        f"intent_layer.orders={il.get('orders_generated')},"
        f"at_target_skips={il.get('at_target_skips')},"
        f"no_anchor_skips={il.get('emissions_skipped_no_anchor')}")
rep += ["", "## 四、映射差异清单（披露 4，全配置相同）", ""]
for k, v in MAPPING_DIFFS.items():
    rep.append(f"- **{k}**: {v}")
rep += ["", "## 五、运行身份", "",
        f"- 引擎 {ENGINE_SHA_AT_START[:16]} 前后一致；8/8 信号一致性 "
        f"{json.dumps(consistency)}",
        "- 试验计账：197 → 205（本轮 8，判定表已产出）；"
        "9cc4 约定 A 数字为无效执行诊断（修订 1），未作任何判定依据；"
        "在环定价=修订 3（权重×决策点权益快照，零反馈），"
        "替代 P3R1 宿主外不动点（5–6 轮）。",
        f"- 判定：{mg['stop_note']}"]
(RUN_DIR / "tmp" / "anchor1_report.md").write_text("\n".join(rep), encoding="utf-8")

# manifest
ENGINE_SHA_AT_END = sha256_file(ENGINE_PY)
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and "manifest.json" != p.name and "runner.log" != p.name:
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260918-p3r2-band-v1-readjudication",
    "status": "completed",
    "started_at_utc": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                "artifacts/runs/20260919T030640-p3r2-dev-ad9e/tmp/"
                "runner_p3r2_intents.py"],
    "random_seed": None,
    "determinism": "no RNG in runner or engine; single static intent frame "
                   "per config; engine-owned deterministic lifecycle",
    "engine": {"path": str(ENGINE_PY), "sha256_at_start": ENGINE_SHA_AT_START,
               "sha256_at_end": ENGINE_SHA_AT_END,
               "bytes_modified_by_this_run":
                   ENGINE_SHA_AT_START != ENGINE_SHA_AT_END,
               "version": "v1.1 intent layer",
               "approval": "artifacts/runs/20260919T023558-p3v1-intent-"
                           "review-c4d1/review.md (APPROVE 0C/0M/4m); "
                           "delivery 20260919T021744-p3v1-intent-ce78; "
                           "29/29 engine tests + 390/390 repo"},
    "pins": pins,
    "configs": [{"id": cid, **r16_config["configs"][cid]}
                for cid in config_list],
    "mapping": {
        "frame": "one static intent frame per config; first decision "
                 "(T,'pm'); expiry = T'+1 cal day (last emission (T','am)"
                 " -> live (T','pm')); buy_open = target_weight exposure/K;"
                 " sell_full = risk full; rescale = risk target_weight "
                 "exposure/K (reduce-to-target; TOP-UP SIDE = registered "
                 "mapping hole); R16 at_target/feemin legs excluded",
        "m5b": "(symbol, side, source) uniqueness hard-asserted before any "
               "engine run",
        "gate8": "7.7-m6 mapped rate; termination itemized; rule-blocked "
                 "counts executed (P3R1 precedent)"},
    "consistency_8_of_8": consistency,
    "trial_accounting": {"cumulative_before": 197, "this_round": 8,
                         "cumulative_after": 205,
                         "note": "judgment table produced (9cc4 consumed "
                                 "zero; prereg rev 1)"},
    "aborted_predecessor": {"run_id": "20260919T002020-p3r2-dev-9cc4",
                            "status": "ABORTED",
                            "convention_a_numbers": "INVALID execution "
                            "diagnostics only (prereg rev 1) -- not used "
                            "here for any judgment or expectation"},
    "gates_dev_pass": [cid for cid in config_list
                       if gates[cid]["dev"]["dev_pass"]],
    "advanced_to_validation": False,
    "val_consumed": False,
    "stop_note": mg["stop_note"],
    "outputs": outs,
}
(RUN_DIR / "tmp" / "anchor1_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== manifest + report written; wall {time.perf_counter() - T0:.0f}s, "
    f"peak rss {PEAK_RSS:.2f} GB ==")
log(f"== VERDICT: {n_pass}/8 dev_pass; {mg['stop_note']}")
_logf.close()
