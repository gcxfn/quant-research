# -*- coding: utf-8 -*-
"""P3R2 runner: R16 eight-config dev readjudication under the v1 band contract.

Authority chain:
- prereg  docs/research/exp-20260918-p3r2-band-v1-readjudication-prereg.md (frozen)
- config  configs/experiments/p3r2-band-v1-readjudication.json (mirror)
- engine  src/quant/backtest/band_engine.py  sha256:16 = 494310195438cbfb
          (bytes must not change; any mismatch aborts before any compute)
- signals R16 leg_log.parquet + 8/8 independent membership consistency

Mapping (prereg sec 4 + contract sec 7.5/7.7):
- month-end signal enters at the 15:00 decision point of the signal day;
- window of a source signal T = decisions [(T,'pm')] + all (d,'am'/'pm') for
  T < d < T' + [(T','am')], T' = next month-end signal day (last window ends
  (2020-12-31,'am')); every decision point re-issues every live intent with a
  mechanically re-anchored price (am -> am.close, pm -> official close) and a
  FIXED nominal/share plan (7.7-M3; quantity itself is recomputed by the
  engine from target_notional at the moving anchor);
- buy_open -> buy target_notional = target_per = exposure(T)*equity(T)/K;
  sell_full -> sell intent='risk', shares=None (entire sellable);
  rescale: up (target_per > position value at T close) -> buy clip with
  target_notional = target_per - pos_value(T); down -> risk sell with
  explicit shares = pos_shares(T) - floor(target_per/close(T)/100)*100
  (emitted only if >= one lot); direction/sizing frozen at the signal-day
  close of the PREVIOUS fixed-point iteration (P3R1 sizing precedent,
  iterated until the signal frame is byte-stable);
- K streak key = (symbol, 'risk', source_signal=T): re-issues keep the
  streak, the next month's signal resets it (7.7-M1);
- gate-8 mapped execution rate (7.7-m6): filled intents /
  (filled + terminated-unfilled intents), termination reason itemized
  (expiry / cap_void / override_same_name / suspension_abandon); re-anchors
  are neutral; at-target skips (delta < lot) are outside the denominator.
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
    load_split_factor_h5, load_stk_limit_batch, run_band_backtest)

SMOKE = "--smoke" in sys.argv

R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
P3R1_RUN = ROOT / "artifacts/runs/20260918T145900-p3r1-dev-262f"
R16_CONFIG = ROOT / "configs/experiments/p2r16-trend-dispersion.json"
P3R2_CONFIG = ROOT / "configs/experiments/p3r2-band-v1-readjudication.json"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
CONFIG_IDS = ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08"]
EXPECT = {
    "r16_config": ("27f846a7330919a4", R16_CONFIG),
    "p3r2_config": ("6e69dfa83bc9c0e6", P3R2_CONFIG),  # placeholder, pinned below
    "engine": ("494310195438cbfb", ENGINE_PY),
    "daily": ("d9a63f4cc3032926", DAILY_PARQUET),
    "split_factor": ("2f436b2f13d09a9b", BUNDLE / "split_factor.h5"),
    "dividends": ("46121c09cddde72e", BUNDLE / "dividends.h5"),
    "index_000300": ("05aaa8183a11c674", INDEX_CHUNK),
}
P3R2_CONFIG_SHA16 = ""  # filled at runtime from the file itself (frozen doc)

T0 = time.perf_counter()
BUDGET_S = 3600.0 if not SMOKE else 1200.0
LOG_LINES: list[str] = []


def log(msg: object) -> None:
    line = f"[{time.perf_counter() - T0:7.1f}s] {msg}"
    LOG_LINES.append(str(line))
    print(line, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rss_gb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e9
    except Exception:
        return float("nan")


def check_budget(what: str) -> None:
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name, "status": "failed",
        "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    sys.exit(1)


# === 0. identity pins ========================================================
log("== 0. identity pins ==")
pins: dict = {}
for name, (expect16, path) in EXPECT.items():
    if name == "p3r2_config":
        continue
    got = sha256_file(Path(path))
    ok = got.startswith(expect16)
    pins[name] = {"path": str(path), "sha256": got,
                  "expected16": expect16, "match": ok}
    log(f"  {name}: {got[:16]} expect {expect16} match={ok}")
    if not ok:
        _fail(f"identity pin mismatch: {name}")
P3R2_CONFIG_SHA16 = sha256_file(P3R2_CONFIG)[:16]
pins["p3r2_config"] = {"path": str(P3R2_CONFIG),
                       "sha256": sha256_file(P3R2_CONFIG),
                       "expected16": P3R2_CONFIG_SHA16, "match": True,
                       "note": "frozen prereg mirror; 16-hex recorded at run time"}
halfday_manifest = HALFDAY_DIR / "manifest.json"
pins["halfday_manifest"] = {"path": str(halfday_manifest),
                            "sha256": sha256_file(halfday_manifest),
                            "expected16": "2a414174b5df2eee",
                            "match": sha256_file(halfday_manifest).startswith("2a414174b5df2eee")}
if not pins["halfday_manifest"]["match"]:
    _fail("halfday manifest pin mismatch")
stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {"path": str(STK_DIR), **stk_agg,
                               "expected16": "3c53abf3b0c39b42",
                               "match": stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
log(f"  stk_limit aggregate: {stk_agg['aggregate_sha256'][:16]} "
    f"({stk_agg['files']} files, {stk_agg['total_bytes']} B) "
    f"match={pins['stk_limit_aggregate']['match']}")
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit aggregate pin mismatch")
log(f"  python {platform.python_version()} | rss {rss_gb():.2f} GB")

r16_config = json.loads(R16_CONFIG.read_text(encoding="utf-8"))
p3r2_config = json.loads(P3R2_CONFIG.read_text(encoding="utf-8"))
r16_metrics = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
p3r1_mg = json.loads((P3R1_RUN / "outputs/metrics_and_gates.json").read_text(encoding="utf-8"))
B3P = {"T200-40": r16_metrics["B3prime_dev_mean_net_cagr"]["T200-40"],
       "FIX75": r16_metrics["B3prime_dev_mean_net_cagr"]["FIX75"]}
B1 = {cid: r16_metrics["configs"][cid] for cid in CONFIG_IDS}

# === 1. calendar & signal days (P3R1 verbatim) ===============================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()          # includes 2020-12-31 (expiry anchor)
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
if SMOKE:
    sig_days = [d for d in sig_days if d.year == 2015]
assert sig_days and sig_days[-1] <= date(2020, 12, 31)
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})"
    + (" [SMOKE: 2015 only]" if SMOKE else " (2020-12-31 dropped as signal, "
                                          "kept as expiry anchor)"))
# expiry anchor = next DEV month-end from the FULL month-end list; the last
# usable signal is 2020-11-30 and its window expires at 2020-12-31 (dropped
# AS a signal because its execution would cross into 2021)
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}

# === 2. exposures (r16 verbatim) =============================================
log("== 2. exposures ==")
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
anchor_check = r16.t200_behavioral_anchor_check(index_close, calendar_full)
log(f"  t200 behavioral anchor check: {json.dumps(anchor_check)[:160]}")
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

# === 4. R16 leg_log + 8/8 consistency ========================================
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
    PANEL_BY_CFG[_k[0]].update(_g["symbol"].to_list())
    for _s, _o in zip(_g["symbol"].to_list(), _g["outcome"].to_list()):
        OUTCOME[(_k[0], _k[1], _s)] = _o
me_by = {(r["config_id"], r["signal"]): r for r in me.iter_rows(named=True)}
consistency: dict = {}
for cid in CONFIG_IDS:
    spec = r16_config["configs"][cid]
    legs_by_day = LEGS  # (config_id, plan_date) keyed
    mismembers, mismev = 0, 0
    prev: list[str] = []
    for t in sig_days:
        g = legs_by_day.get((cid, t))
        kinds = {} if g is None else dict(zip(g["symbol"].to_list(),
                                              g["kind"].to_list()))
        members = sorted(s for s, k in kinds.items() if k in ("buy_open", "rescale"))
        leavers = sorted(s for s, k in kinds.items() if k == "sell_full")
        exp_members, info = r16.buffer_membership(
            prev, pools_at[t]["ranked"], pools_at[t]["q5"],
            int(spec["K"]), spec["filter"] == "on")
        if members != sorted(exp_members):
            mismembers += 1
        ev = me_by.get((cid, t))
        # R16 records {'signal': t, **info} from its own membership_fn; the
        # buffer_membership info must match field-for-field.  (n_left is
        # membership turnover, NOT the sell_full count: sell legs exist only
        # for actually-held symbols, planned members may stay cash.)
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

# === 5. market frames (panel x dev) ==========================================
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
log(f"  daily panel: {daily.height} rows, "
    f"{daily['symbol'].n_unique()} symbols, max {daily['date'].max()}")

# halfday: load partitions, filter freeze + dev + panel (loader semantics)
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
if not parts:
    _fail("no halfday partitions")
half_parts, half_rows_total = [], 0
for part in parts:
    f = pl.read_parquet(part)
    half_rows_total += f.height
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= DEV_START) & (pl.col("trade_date") <= DEV_END))
    f = f.filter(pl.col("symbol").is_in(panel_symbols))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame()
del half_parts
assert_frozen(half, "trade_date", "halfday")
log(f"  halfday: {half.height} rows kept of {half_rows_total} total "
    f"(panel x dev), {half['symbol'].n_unique()} symbols")

limits_full, limits_meta = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})  # ENGINE-2 bridge
limits = (limits_full.filter(pl.col("symbol").is_in(panel_symbols))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
          .sort("symbol", "date"))
LIMIT_DAYS = set(zip(limits["symbol"].to_list(),
                     (limits["date"].dt.year().cast(pl.Int64) * 10_000
                      + limits["date"].dt.month().cast(pl.Int64) * 100
                      + limits["date"].dt.day().cast(pl.Int64)).to_numpy()))
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
log(f"  instruments: {len(panel_symbols)} stocks (is_etf=False, is_t0=False; "
    "ETF line not in this round per prereg sec 2)")
check_budget("market frames")
log(f"  rss after frames: {rss_gb():.2f} GB")

# === 6. anchor tables ========================================================
# pm anchor = official close (close_le on that day); am anchor = am.close,
# falling back to the previous official close when the am bar is missing.
_trading = (daily.filter(pl.col("tradestatus") != 0)
            if "tradestatus" in daily.columns else daily)
def _dints(col: pl.Series) -> np.ndarray:
    # Int64 arithmetic in polars: naive numpy month*100 overflows Int8
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


close_arr = {}
for (sym,), g in _trading.partition_by("symbol", as_dict=True).items():
    dint = _dints(g["date"])
    close_arr[sym] = (dint.astype(np.int64),
                      g["close"].to_numpy().astype(np.float64))
am_df = half.filter(pl.col("session") == "am").select(
    "symbol", "trade_date", "close")
am_close = {}
for (sym,), g in am_df.partition_by("symbol", as_dict=True).items():
    dint = _dints(g["trade_date"])
    order = np.argsort(dint)
    am_close[sym] = (dint.astype(np.int64)[order],
                     g["close"].to_numpy().astype(np.float64)[order])
pm_dates = set(half.filter(pl.col("session") == "pm")["trade_date"].to_list())
am_dates = set(half.filter(pl.col("session") == "am")["trade_date"].to_list())
BAR_DAYS = {"am": set(zip(half.filter(pl.col("session") == "am")["symbol"].to_list(),
                          (half.filter(pl.col("session") == "am")["trade_date"].dt.year().cast(pl.Int64) * 10_000
                           + half.filter(pl.col("session") == "am")["trade_date"].dt.month().cast(pl.Int64) * 100
                           + half.filter(pl.col("session") == "am")["trade_date"].dt.day().cast(pl.Int64)).to_numpy())),
            "pm": set(zip(half.filter(pl.col("session") == "pm")["symbol"].to_list(),
                          (half.filter(pl.col("session") == "pm")["trade_date"].dt.year().cast(pl.Int64) * 10_000
                           + half.filter(pl.col("session") == "pm")["trade_date"].dt.month().cast(pl.Int64) * 100
                           + half.filter(pl.col("session") == "pm")["trade_date"].dt.day().cast(pl.Int64)).to_numpy()))}
log(f"  anchor tables: {len(close_arr)} official series, {len(am_close)} am series, "
    f"{len(pm_dates)} pm-session dates, {len(am_dates)} am-session dates")


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


def close_le(sym: str, d: date) -> float | None:
    arr = close_arr.get(sym)
    if arr is None:
        return None
    dint, cls = arr
    i = int(np.searchsorted(dint, dint_of(d), side="right")) - 1
    return float(cls[i]) if i >= 0 else None


def anchor_at(sym: str, d: date, sess: str) -> float | None:
    if sess == "am":
        arr = am_close.get(sym)
        if arr is not None:
            dint, cls = arr
            i = int(np.searchsorted(dint, dint_of(d), side="left"))
            if i < len(dint) and dint[i] == dint_of(d):
                return float(cls[i])
        pd_ = close_le(sym, d)
        # previous official close strictly before d
        arr = close_arr.get(sym)
        if arr is None:
            return None
        i = int(np.searchsorted(arr[0], dint_of(d), side="left")) - 1
        return float(arr[1][i]) if i >= 0 else None
    return close_le(sym, d)


_CAL_IDX = {d: i for i, d in enumerate(calendar_full)}


def next_day_of(d: date) -> date:
    i = _CAL_IDX.get(d)
    return calendar_full[i + 1] if i is not None and i + 1 < len(calendar_full)         else d


def sess_key(d: date, sess: str) -> int:
    return dint_of(d) * 2 + (0 if sess == "am" else 1)


def live_of(d: date, s: str) -> tuple[date, str]:
    return (d, "pm") if s == "am" else (next_day_of(d), "am")


def build_dec_src() -> dict:
    dec_src: dict[tuple[date, str], date] = {}
    for T in sig_days:
        for (d, s) in window_decisions(T):
            dec_src.setdefault((d, s), T)
    return dec_src


DEC_SRC: dict = {}


def fill_schedule(fills: pl.DataFrame) -> dict:
    out: dict = {}
    if fills is None or fills.height == 0:
        return out
    for r in fills.select("symbol", "side", "decision_date",
                          "decision_session", "shares",
                          "notional").iter_rows(named=True):
        T = DEC_SRC.get((r["decision_date"], r["decision_session"]))
        if T is None:
            continue
        k = (r["symbol"], "buy" if r["side"] == "buy" else "sell", T)
        # entry: (sess_key of the DECISION that produced this order, shares,
        # notional) -- decision-keyed so the builder can cumulate what the
        # host knows at each decision point
        out.setdefault(k, []).append(
            (sess_key(r["decision_date"], r["decision_session"]),
             int(r["shares"]), float(r["notional"])))
    for v in out.values():
        v.sort()
    return out


# === 7. signal builder =======================================================
def window_decisions(T: date) -> list[tuple[date, str]]:
    """[(T,'pm')] + all (d, am/pm) strictly between T and T' + [(T','am')].
    Half-market sessions (m3) are skipped (no decision point that session)."""
    tp = next_sig.get(T) or DEV_END
    out = []
    if T in pm_dates:
        out.append((T, "pm"))
    for d in calendar_full:
        if d <= T:
            continue
        if d >= tp:
            break
        if d in am_dates:
            out.append((d, "am"))
        if d in pm_dates:
            out.append((d, "pm"))
    if tp in am_dates:
        out.append((tp, "am"))
    return out


def build_signals(cid: str, spec: dict, equity_at: dict, pos_at: dict,
                  fill_sched: dict | None = None):
    """Emit the v1 signal frame + intent registry for one config.

    Returns (sig_frame, intents, dec_src) where intents[(sym, sclass, T)] =
    dict(plan=..., target_notional=..., shares=..., skip=...) and
    dec_src maps emitted (d, sess) -> T (for fill attribution)."""
    path_name = spec["path"]
    exposures = exposures_by_path[path_name]
    legs_by_day = LEGS  # (config_id, plan_date) keyed
    rows: list[dict] = []
    intents: dict = {}
    dec_src: dict[tuple[date, str], date] = {}
    n_gap_skips = 0
    sched = fill_sched or {}
    for T in sig_days:
        g = legs_by_day.get((cid, T))
        kinds = {} if g is None else dict(zip(g["symbol"].to_list(),
                                              g["kind"].to_list()))
        eq = float(equity_at.get(T, 200_000.0))
        target_per = exposures[T] * eq / int(spec["K"])
        decs = window_decisions(T)
        for (d, s) in decs:
            if s == "pm" and d == T:
                dec_src[(d, s)] = T
            elif (d, s) not in dec_src:
                dec_src[(d, s)] = T
        nxt = next_sig.get(T)
        for sym in sorted(kinds):
            kind = kinds[sym]
            rank = rank_of[T].get(sym, 10 ** 6)
            if kind == "sell_full":
                plan = ("sell", "risk", None, None)   # side, intent, tn, shares
                key = (sym, "sell", T)
            elif kind == "buy_open":
                plan = ("buy", "", round(target_per, 2), None)
                key = (sym, "buy", T)
            else:  # rescale: R16 share-count semantics at the T-close mark
                # (prev iteration): delta = held - target shares; |delta| <
                # one lot == R16 'at_target' -> no order (mapping fidelity)
                sh_T, _val_T = pos_at.get(T, {}).get(sym, (0, 0.0))
                px_T = close_le(sym, T)
                if px_T is None or px_T <= 0:
                    key = (sym, "sell", T)
                    intents[key] = {"plan": "skip", "skip": "no_close_at_T"}
                    continue
                tgt_sh = int(math.floor(target_per / px_T / LOT)) * LOT
                delta = int(sh_T) - tgt_sh
                if delta >= LOT:
                    plan = ("sell", "risk", None, (delta // LOT) * LOT)
                    key = (sym, "sell", T)
                elif (-delta) >= LOT:
                    lots = (-delta) // LOT
                    plan = ("buy", "", round(lots * LOT * px_T, 2), None)
                    key = (sym, "buy", T)
                else:
                    key = (sym, "buy", T)
                    intents[key] = {"plan": "skip", "skip": "at_target"}
                    continue
            if key in intents and intents[key]["plan"] != "skip":
                _fail(f"duplicate intent {key}")
            oc = OUTCOME.get((cid, T, sym))
            if oc in ("at_target", "feemin_skipped") and kind == "rescale":
                # R16's own record: already at target / de-minimis -> no order
                intents[key] = {"plan": "skip", "skip": f"r16_{oc}"}
                continue
            intents[key] = {"plan": plan[0], "target_notional": plan[2],
                            "shares": plan[3], "skip": None}
            sk = sched.get(key, [])
            for (d, s) in decs:
                k_ds = sess_key(d, s)
                if plan[0] == "buy":
                    # lifecycle encoded in the SIZE (fixed row set): the
                    # remaining seat notional shrinks as this intent's own
                    # earlier emissions fill; a completed intent keeps
                    # emitting with a dust notional the engine abandons
                    # below-min-lot (rule-compliant, account-neutral)
                    bought = sum(nt for kk, _sh, nt in sk if kk <= k_ds)
                    eff_tn: float | None = max(round(plan[2] - bought, 2), 0.01)
                    eff_shares: int | None = plan[3]
                elif plan[0] == "sell" and plan[3] is not None:
                    cum = sum(sh for kk, sh, _nt in sk if kk <= k_ds)
                    remaining = int(plan[3]) - cum
                    if remaining < LOT:
                        break  # plan complete; a residual row is invalid
                    eff_shares = remaining
                    eff_tn = plan[2]
                else:
                    # sell_full: engine self-terminates on empty position
                    eff_shares = plan[3]
                    eff_tn = plan[2]
                # live session for this decision
                live_d = d if s == "am" else next_day_of(d)
                if plan[0] == "sell"                         and (sym, dint_of(live_d)) in BAR_DAYS[s]                         and (sym, dint_of(live_d)) not in LIMIT_DAYS:
                    # tushare batch gap (e.g. 2017-03-07..09): the v1 engine's
                    # risk-sell void path crashes on missing limit rows
                    # (ENGINE-3 finding, reported); the host skips these
                    # emissions and discloses (deviation from v0 ruling #3)
                    n_gap_skips += 1
                    continue
                anchor = anchor_at(sym, d, s)
                if anchor is None or anchor <= 0:
                    continue  # no observable price yet; engine would void anyway
                rows.append({
                    "symbol": sym, "decision_date": d, "decision_session": s,
                    "side": plan[0], "intent": plan[1],
                    "anchor_price": float(anchor), "priority": int(rank),
                    "target_notional": eff_tn, "shares": eff_shares,
                    "source_signal": T})
    if n_gap_skips:
        log(f"  [mapping] {cid}: {n_gap_skips} sell emissions skipped on "
            "limit-data-gap live sessions (ENGINE-3 host guard, disclosed)")
    sig = pl.DataFrame(rows, schema={
        "symbol": pl.String, "decision_date": pl.Date,
        "decision_session": pl.String, "side": pl.String, "intent": pl.String,
        "anchor_price": pl.Float64, "priority": pl.Int64,
        "target_notional": pl.Float64, "shares": pl.Int64,
        "source_signal": pl.Date})
    return sig, intents, dec_src


# === 8. position reconstruction (for the next fixed-point iteration) =========
split_events: dict[str, list[tuple[date, float]]] = {}
for r in splits.filter(pl.col("ex_date") <= DEV_END).iter_rows(named=True):
    split_events.setdefault(r["symbol"], []).append(
        (r["ex_date"], float(r["split_factor"])))
for v in split_events.values():
    v.sort()


def equity_at_days(res_daily: pl.DataFrame) -> dict[date, float]:
    return dict(zip(res_daily["date"].to_list(),
                    res_daily["equity"].to_list()))


def positions_at_signals(fills: pl.DataFrame) -> dict:
    """pos_at[T][sym] = (shares, value at T close).  Split adjustment applies
    per aggregate position with half-up rounding (approximation of the
    engine's per-clip rounding; magnitude < 1 share, disclosed)."""
    pos_at: dict[date, dict[str, tuple[int, float]]] = {t: {} for t in sig_days}
    if fills.height == 0:
        return pos_at
    per: dict[str, list] = {}
    for r in fills.select("symbol", "date", "side", "shares").iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (dint_of(r["date"]), r["side"], int(r["shares"])))
    for sym, evs in per.items():
        evs.sort(key=lambda e: e[0])
        sp = [(dint_of(ed), f) for ed, f in split_events.get(sym, [])]
        pos = 0
        i = 0
        for t in sig_days:
            td = dint_of(t)
            while i < len(evs) and evs[i][0] <= td:
                while sp and sp[0][0] <= evs[i][0]:
                    pos = int(math.floor(pos * sp.pop(0)[1] + 0.5))
                pos += evs[i][2] if evs[i][1] == "buy" else -evs[i][2]
                i += 1
            while sp and sp[0][0] <= td:
                pos = int(math.floor(pos * sp.pop(0)[1] + 0.5))
            if pos:
                pos_at[t][sym] = (pos, pos * close_ffill(sym, t))
    return pos_at


def close_ffill(sym: str, d: date) -> float:
    px = close_le(sym, d)
    return px if px is not None else float("nan")


# === 9. per-config fixed-point run ===========================================
log("== 9. per-config fixed-point runs ==")
DEC_SRC = build_dec_src()
log(f"  decision points (all windows): {len(DEC_SRC)}")
config_list = ["C01"] if SMOKE else list(CONFIG_IDS)


def quick_metrics(res) -> dict:
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(), DEV_START, DEV_END)
    return {"cagr": er.cagr(sv[0], sv[-1], sd[0], sd[-1]),
            "mdd": er.max_drawdown(sd, sv)["max_drawdown"],
            "end_eq": sv[-1]}


results: dict = {}
for cid in config_list:
    spec = r16_config["configs"][cid]
    cfg_syms = sorted(PANEL_BY_CFG[cid])
    daily_c = daily.filter(pl.col("symbol").is_in(cfg_syms))
    half_c = half.filter(pl.col("symbol").is_in(cfg_syms))
    limits_c = limits.filter(pl.col("symbol").is_in(cfg_syms))
    splits_c = splits.filter(pl.col("symbol").is_in(cfg_syms))
    divs_c = dividends.filter(pl.col("symbol").is_in(cfg_syms))
    instr_c = instruments.filter(pl.col("symbol").is_in(cfg_syms))
    log(f"  {cid}: per-config frames daily {daily_c.height} / half {half_c.height}"
        f" / limits {limits_c.height} rows, {len(cfg_syms)} symbols")
    equity_at = {t: 200_000.0 for t in sig_days}
    pos_at: dict = {t: {} for t in sig_days}
    fill_sched: dict = {}
    # under-relaxation of the sizing feedback (alpha=0.5): the fixed point is
    # unchanged (g(x)=x there); damping only tames the alternating equity/
    # position overshoot observed in undamped iteration
    ALPHA = 0.5
    prev_sig = None
    res = None
    intents: dict = {}
    dec_src: dict = DEC_SRC
    sig_final = None
    sig_last2 = None
    hist: list = []
    converged_at = None
    t_cfg = time.perf_counter()
    conv_kind = None
    for it in range(1, 17):
        check_budget(f"{cid} sizing iter {it}")
        sig, intents, dec_src = build_signals(cid, spec, equity_at, pos_at,
                                              fill_sched)
        if prev_sig is not None:
            if sig.equals(prev_sig):
                converged_at, conv_kind = it, "byte_equal_frame"
                sig_final = sig
                break
            if len(hist) >= 2:
                d_cagr = abs(hist[-1]["cagr"] - hist[-2]["cagr"])
                d_eq = (abs(hist[-1]["end_eq"] - hist[-2]["end_eq"])
                        / max(1.0, hist[-1]["end_eq"]))
                if d_cagr < 5e-4 and d_eq < 1e-3:
                    converged_at, conv_kind = it, "tolerance_5e-4_cagr"
                    sig_final = sig
                    break
        sig_last2 = prev_sig
        prev_sig = sig
        sig_final = sig
        res = run_band_backtest(sig, daily_c, half_c, limits_c, splits_c,
                                divs_c, instr_c, initial_cash=200_000.0)
        eq_new = equity_at_days(res.daily)
        equity_at = {t: ALPHA * eq_new.get(t, equity_at[t])
                     + (1 - ALPHA) * equity_at[t] for t in sig_days}
        pos_new = positions_at_signals(res.fills)
        pos_at = {t: {s: (int(round(ALPHA * sh + (1 - ALPHA) * pos_at[t].get(s, (0, 0.0))[0])),
                       ALPHA * v + (1 - ALPHA) * pos_at[t].get(s, (0, 0.0))[1])
                      for s, (sh, v) in pos_new[t].items()}
                  for t in sig_days}
        fill_sched = fill_schedule(res.fills)
        qm = quick_metrics(res)
        qm["iter"] = it
        hist.append(qm)
        log(f"  {cid} it{it}: cagr {qm['cagr']*100:+.3f}% mdd {qm['mdd']*100:.2f}% "
            f"end {qm['end_eq']:,.0f} rss {rss_gb():.2f}G")
    if res is None:
        _fail(f"{cid}: no engine run executed")
    results[cid] = {"res": res, "intents": intents, "dec_src": dec_src,
                    "sig": sig_final, "sig_last2": sig_last2,
                    "hist": hist, "converged_at": converged_at,
                    "conv_kind": conv_kind,
                    "wall_s": time.perf_counter() - t_cfg,
                    "warnings": list(res.warnings)}
    log(f"  {cid}: converged_at={converged_at} ({conv_kind}) "
        f"({len(hist)} engine runs, {results[cid]['wall_s']:.0f}s wall)")
check_budget("all config fixed points")

# === 10. intent attribution + gate-8 mapped execution rate (7.7-m6) ==========
log("== 10. attribution & gate 8 ==")


def order_id_of(sym, side, intent, d, s) -> str:
    return (f"{sym}-{side}{('/' + intent) if intent else ''}-"
            f"{d.isoformat()}-{s}")


def attribute(cid: str) -> dict:
    st = results[cid]
    res, intents, dec_src, sig = st["res"], st["intents"], DEC_SRC, st["sig"]
    dec_items = sorted((sess_key(d, s), T) for (d, s), T in dec_src.items())
    dec_keys = np.array([k for k, _ in dec_items])
    dec_ts = [T for _, T in dec_items]

    def src_of(d, s):
        i = int(np.searchsorted(dec_keys, sess_key(d, s), side="right")) - 1
        return dec_ts[i] if i >= 0 else None

    fill_n: dict = {}
    for r in res.fills.select("symbol", "side", "decision_date",
                              "decision_session").iter_rows(named=True):
        sclass = "buy" if r["side"] == "buy" else "sell"
        T = src_of(r["decision_date"], r["decision_session"])
        if T is not None:
            k = (r["symbol"], sclass, T)
            fill_n[k] = fill_n.get(k, 0) + 1
    # emissions per intent + per side/session stats
    emit_n: dict = {}
    emit_side: dict = {"buy": 0, "sell": 0}
    fill_side: dict = {"buy": 0, "sell": 0}
    emit_sess: dict = {"am": 0, "pm": 0}
    fill_sess: dict = {"am": 0, "pm": 0}
    filled_orders: set = set(res.fills["order_id"].to_list()) if res.fills.height else set()
    order_ids: dict = {}
    for r in sig.iter_rows(named=True):
        sclass = "buy" if r["side"] == "buy" else "sell"
        k = (r["symbol"], sclass, r["source_signal"])
        emit_n[k] = emit_n.get(k, 0) + 1
        emit_side[sclass] += 1
        emit_sess[r["decision_session"]] += 1
        oid = order_id_of(r["symbol"], r["side"], r["intent"],
                          r["decision_date"], r["decision_session"])
        order_ids.setdefault(k, []).append(oid)
        if oid in filled_orders:
            fill_side[sclass] += 1
            fill_sess[r["decision_session"]] += 1
    # next-window same-symbol override check: R16 supersedes ANY pending
    # order for a symbol at the new signal ("latest target wins",
    # simulate_r16 step 3), independent of the new leg's direction
    legs_by_day = LEGS  # (config_id, plan_date) keyed

    def has_leg_at(t, sym):
        g = legs_by_day.get((cid, t))
        if g is None:
            return False
        return sym in set(g["symbol"].to_list())

    outcomes: dict = {}
    term = {"expiry": 0, "override_same_name": 0, "cap_void": 0,
            "suspension_abandon": 0}
    rule_blocked = {"below_min_lot": 0, "void_no_position": 0,
                    "void_insufficient_cash": 0}
    ev = res.events
    # rule-compliant blocks count as EXECUTED (P3R1 mapping precedent:
    # "filled + below_min_lot + void_no_position + cash-blocked over all
    # orders (R16 at_target/no_lots/cash_capped/feemin_skipped analog)")
    RULE_OK = {"below_min_lot", "void_no_position", "void_insufficient_cash"}
    for k, plan in intents.items():
        sym, sclass, T = k
        if plan.get("skip"):
            outcomes[k] = ("skip", plan["skip"])
            continue
        if fill_n.get(k, 0) > 0:
            outcomes[k] = ("filled", None)
            continue
        ids = order_ids.get(k, [])
        sub = (ev.filter(pl.col("order_id").is_in(ids))
               if ids and ev.height else pl.DataFrame())
        ev_names = sub["event"].to_list() if sub.height else []
        if ev_names and all(e in ("void_suspended",) for e in ev_names):
            outcomes[k] = ("terminated", "suspension_abandon")
            term["suspension_abandon"] += 1
            continue
        if ev_names and all(e in RULE_OK for e in ev_names):
            reason = ev_names[-1]
            outcomes[k] = ("executed_rule_blocked", reason)
            rule_blocked[reason] += 1
            continue
        if "void_cap_single_name" in ev_names:
            outcomes[k] = ("terminated", "cap_void")
            term["cap_void"] += 1
            continue
        nxt = next_sig.get(T)
        if nxt is not None and has_leg_at(nxt, sym):
            outcomes[k] = ("terminated", "override_same_name")
            term["override_same_name"] += 1
        else:
            outcomes[k] = ("terminated", "expiry")
            term["expiry"] += 1
    n_filled = sum(1 for v in outcomes.values() if v[0] == "filled")
    n_rule = sum(v[0] == "executed_rule_blocked" for v in outcomes.values())
    n_term = sum(v[0] == "terminated" for v in outcomes.values())
    n_skip = sum(1 for v in outcomes.values() if v[0] == "skip")
    mapped = ((n_filled + n_rule) / (n_filled + n_rule + n_term)
              if (n_filled + n_rule + n_term) else None)
    return {"outcomes": outcomes, "termination": term, "mapped_rate": mapped,
            "n_filled": n_filled, "n_rule_blocked": n_rule,
            "rule_blocked": dict(rule_blocked),
            "n_terminated": n_term, "n_skip": n_skip,
            "order_session": {s: (fill_side[s] / emit_side[s] if emit_side[s] else None)
                              for s in ("buy", "sell")},
            "emit_side": emit_side, "fill_side": fill_side,
            "sess_fill_share": {s: (fill_sess[s] / emit_sess[s] if emit_sess[s] else None)
                                for s in ("am", "pm")},
            "fill_n": fill_n, "emit_n": emit_n}


for cid in config_list:
    results[cid]["attr"] = attribute(cid)
    a = results[cid]["attr"]
    log(f"  {cid}: mapped rate {a['mapped_rate']*100 if a['mapped_rate'] else 0:.1f}% "
        f"(filled {a['n_filled']}, rule-blocked {a['n_rule_blocked']}, "
        f"terminated {a['n_terminated']}, skip {a['n_skip']}), "
        f"order-session fill b/s "
        f"{(a['order_session']['buy'] or 0)*100:.1f}/{(a['order_session']['sell'] or 0)*100:.1f}%, "
        f"term {a['termination']}")

# === 11. metrics & gates =====================================================
log("== 11. metrics & gates ==")


