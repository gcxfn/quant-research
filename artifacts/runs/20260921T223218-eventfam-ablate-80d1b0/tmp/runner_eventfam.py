# -*- coding: utf-8 -*-
"""Phase-B runner: event-family candidates on the baseline replay stack.

Prereg: docs/research/stock_event_research_prereg.md (frozen before any
phase-B run; 22-attempt budget across 6 groups).  Usage:
``python runner_eventfam.py <group>`` with groups smoke/main/perturb/
rnd/delay/cost/ablate.  Each arm = FamilyParams + engine replay with the
baseline wiring (halfday clock, 500k, D3 dynamic overlay with risk-class
trims, SingleNameRules v4 semantics; A-family wide stop 3xATR 10..20%).

The archived tmp/runner_eventfam.py IS the executed file (self-pinned
start/end, edit-breaking fail-closed), mirroring the v4 baseline runner.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as _im
import json
import subprocess
import sys
import time
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
import psutil  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.event_family_signals import (  # noqa: E402
    BEvent, FamilyParams, SymbolSeries, TriggerEvent,
    EventFamilyProvider, b1_revision_events, b2_announcement_events,
    make_delayed_provider, random_month_picks, scan_a_triggers)
from quant.research.fixed_scheme_lib import (  # noqa: E402
    ATTACK_BUDGET_SEAT, build_atr20)
from quant.research.risk_overlay_runner import (  # noqa: E402
    DynamicOverlayHost, LedgerMarks)
from quant.research.single_name_rules import SingleNameRules  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, FeeModel, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_split_factor_h5,
    load_stk_limit_batch, run_band_backtest_intents)

GROUP = sys.argv[1] if len(sys.argv) > 1 else "smoke"
PREREG = ROOT / "docs/research/stock_event_research_prereg.md"
BASELINE_RUN = ROOT / "artifacts/runs/20260921T210100-baseline-replay4-9x4q2"
BASELINE_MANIFEST = BASELINE_RUN / "manifest.json"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
T1_DIR = ROOT / "data/features/fcst-reason-struct-full-20260918"
FCST_RAW_DIR = ROOT / "data/raw/tushare/forecast/20260909-r1"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
SNR_PY = ROOT / "src/quant/research/single_name_rules.py"
EFS_PY = ROOT / "src/quant/research/event_family_signals.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
B_DEV_FIRST, B_DEV_LAST = "20180904", "20201231"
INITIAL_CASH = 500_000.0
BUDGET_S = {"smoke": 1800.0}.get(GROUP, 3600.0)
BM1_CAGR = json.loads(BASELINE_MANIFEST.read_text(encoding="utf-8")
                      )["metrics"]["FULL-bin"]["net_cagr"]

ARM_MAIN = {"A1": FamilyParams("A1", label="main"),
            "A2": FamilyParams("A2", label="main"),
            "B1": FamilyParams("B1", label="main"),
            "B2": FamilyParams("B2", label="main")}
ARM_PERTURB = {
    "A1-vc060": FamilyParams("A1", label="pert1", vc_ratio=0.60),
    "A1-trail": FamilyParams("A1", label="pert2"),
    "A2-pb15": FamilyParams("A2", label="pert1", pullback_days=15),
    "A2-trail": FamilyParams("A2", label="pert2"),
    "B1-floor": FamilyParams("B1", label="pert1", b1_floor_must_rise=True),
    "B1-cool": FamilyParams("B1", label="pert2", b1_cooldown=20),
    "B2-cf10": FamilyParams("B2", label="pert1", confirm_sessions=10),
    "B2-yz": FamilyParams("B2", label="pert2", b2_types=("预增",))}
ARM_ABLATE = {
    "A1-nors": FamilyParams("A1", label="ablate", use_rs_filter=False),
    "B2-noconf": FamilyParams("B2", label="ablate", use_price_confirm=False)}
ARM_RND = {f"RND-{s}": FamilyParams("RND", label="control",
                                    rnd_seed=s) for s in (11, 23, 47)}
TRAIL_MARK = {"A1-trail", "A2-trail"}      # perturbation (2) arms
# FamilyParams has no trail field; mark via label and set the SNR flag here
GROUPS = {
    "smoke": {"arms": dict(list(ARM_MAIN.items())[:1])
              | {"B1": ARM_MAIN["B1"], "B2": ARM_MAIN["B2"]},
              "window": (date(2019, 1, 1), date(2019, 12, 31)),
              "bm2": False, "attempts": 0, "stress": None},
    "main": {"arms": dict(ARM_MAIN), "window": (DEV_START, DEV_END),
             "bm2": True, "attempts": 5, "stress": None},
    "perturb": {"arms": dict(ARM_PERTURB), "window": (DEV_START, DEV_END),
                "bm2": False, "attempts": 8, "stress": None},
    "rnd": {"arms": dict(ARM_RND), "window": (DEV_START, DEV_END),
            "bm2": False, "attempts": 3, "stress": None},
    "delay": {"arms": dict(ARM_MAIN), "window": (DEV_START, DEV_END),
              "bm2": False, "attempts": 2, "stress": "delay"},
    "cost": {"arms": dict(ARM_MAIN), "window": (DEV_START, DEV_END),
             "bm2": False, "attempts": 2, "stress": "cost"},
    "ablate": {"arms": dict(ARM_ABLATE), "window": (DEV_START, DEV_END),
               "bm2": False, "attempts": 2, "stress": None},
}
CFG = GROUPS[GROUP]
WIN0, WIN1 = CFG["window"]

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
LOG_PATH = RUN_DIR / "logs" / "runner.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_LINES: list[str] = []
_logf = LOG_PATH.open("a", encoding="utf-8")


def log(msg: object) -> None:
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


def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name, "experiment_id": "exp-20260921-event-families",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


def check_budget(what: str) -> None:
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


SELF_PY = Path(__file__).resolve()
SELF_SHA_START = sha256_file(SELF_PY)


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        _fail("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


GIT_HEAD = _git("rev-parse", "HEAD")
GIT_BRANCH = _git("rev-parse", "--abbrev-ref", "HEAD")
GIT_PORCELAIN = _git("status", "--porcelain")
DEPS = {p: _im.version(p) for p in ("polars", "numpy", "psutil")}
log(f"self {SELF_SHA_START[:16]}; git {GIT_BRANCH} {GIT_HEAD[:12]}; "
    f"group={GROUP} window={WIN0}..{WIN1}; BM1 cagr {BM1_CAGR*100:+.2f}%")

# === 0. pins ================================================================
pins: dict = {}
for name, p in [("engine", ENGINE_PY), ("snr_module", SNR_PY),
                ("event_family_signals", EFS_PY), ("prereg", PREREG),
                ("daily", DAILY_PARQUET),
                ("baseline_manifest", BASELINE_MANIFEST),
                ("split_factor", BUNDLE / "split_factor.h5"),
                ("dividends", BUNDLE / "dividends.h5"),
                ("t1_row_index", T1_DIR / "row_index.parquet")]:
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
fcst_chunk_shas = {}
for p in sorted(FCST_RAW_DIR.glob("chunk_*.csv")):
    m = p.stem.replace("chunk_", "")
    if B_DEV_FIRST[:6] <= m <= B_DEV_LAST[:6]:
        fcst_chunk_shas[p.name] = sha256_file(p)
pins["fcst_raw_chunks"] = {"n": len(fcst_chunk_shas),
                           "sha256": fcst_chunk_shas}
log(f"  pins OK ({len(fcst_chunk_shas)} fcst chunks)")

# === 1. calendar / pools ====================================================
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= WIN0) & (pl.col("s") <= WIN1))
sig_days = [d for d in all_mes["s"].to_list() if
            idx_of_full.get(d, 10**9) + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= WIN1]
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})")

hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_by_month = [(t, pools_at[t]["ranked"]) for t in sig_days]
pool_set = {t: set(pools_at[t]["ranked"]) for t in sig_days}
pool_union = sorted(set().union(*pool_set.values()))
n_pool = [len(v) for v in pool_set.values()]
log(f"  pool union {len(pool_union)} symbols; "
    f"pool size min/med/max {min(n_pool)}/{sorted(n_pool)[len(n_pool)//2]}"
    f"/{max(n_pool)}")
check_budget("pools")

WARM_START = WIN0 - timedelta(days=300)
pool_daily = (
    pl.scan_parquet(DAILY_PARQUET)
    .filter((pl.col("tradestatus") == 1.0)
            & pl.col("symbol").is_in(pool_union)
            & (pl.col("date") >= WARM_START) & (pl.col("date") <= WIN1))
    .select("symbol", "date", "high", "low", "close", "volume")
    .collect())
assert pool_daily["volume"].dtype.is_numeric(), "volume column missing"
series: dict[str, SymbolSeries] = {}
for (sym,), g in pool_daily.sort("symbol", "date").partition_by(
        "symbol", as_dict=True).items():
    series[str(sym)] = SymbolSeries(
        str(sym), g["date"].to_list(),
        g["close"].to_numpy().astype(np.float64),
        g["high"].to_numpy().astype(np.float64),
        g["low"].to_numpy().astype(np.float64),
        g["volume"].to_numpy().astype(np.float64))
del pool_daily
log(f"  symbol series: {len(series)}")

daily_ext_pool = (
    pl.scan_parquet(DAILY_PARQUET)
    .filter(pl.col("symbol").is_in(pool_union)
            & (pl.col("date") >= WARM_START) & (pl.col("date") <= WIN1))
    .select("symbol", "date", "high", "low", "close")
    .collect())
atr_tbl = build_atr20(daily_ext_pool)


class _High20:
    """Max HIGH over the 20 own sessions STRICTLY BEFORE the day."""

    def __init__(self, ser_map):
        self.m = ser_map

    def __call__(self, sym: str, d: date):
        s = self.m.get(sym)
        if s is None:
            return None
        i = s.idx_lt(d)
        if i < 20 - 1:
            return None
        return float(np.max(s.high[i - 19:i + 1]))


high20 = _High20(series)
atr_of = lambda s, d: atr_tbl.atr(s, d)  # noqa: E731
check_budget("series")

# === 2. B-family raw events ==================================================
need_b = any(p.family in ("B1", "B2") for p in CFG["arms"].values())
b_rows_all: list[dict] = []
if need_b:
    ri = pl.read_parquet(T1_DIR / "row_index.parquet").filter(
        (pl.col("ann_date") >= B_DEV_FIRST) & (pl.col("ann_date") <= B_DEV_LAST))
    ann_rows = []
    for p in sorted(T1_DIR.glob("batch_*.jsonl")):
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                ann_rows.append(json.loads(line))
    ann = pl.DataFrame(ann_rows)
    KEY = ["ts_code", "end_date", "ann_date", "update_flag"]
    merged = ri.join(ann.select(KEY + ["primary_code"]), on=KEY,
                     how="inner")
    raw_parts = []
    for name, sha in fcst_chunk_shas.items():
        raw_parts.append(pl.read_csv(FCST_RAW_DIR / name))
    raw = pl.concat(raw_parts, how="vertical")
    KEY = ["ts_code", "end_date", "ann_date", "update_flag"]
    raw = raw.with_columns(
        pl.col("end_date").cast(pl.String),
        pl.col("ann_date").cast(pl.String),
        pl.col("update_flag").cast(pl.String))
    if raw.select(KEY).n_unique() != raw.height:
        _fail("raw forecast chunks have duplicate (ts,end,ann,flag) keys")
    raw_key = raw.select(KEY + ["net_profit_min", "net_profit_max"])
    merged = merged.join(raw_key, on=KEY, how="left")
    if merged.height != ri.height:
        _fail(f"annotation join changed row count: {ri.height} -> "
              f"{merged.height}")

    def _ts_to_symbol(ts: str) -> str | None:
        try:
            code, suf = ts.split(".")
        except ValueError:
            return None
        if len(code) != 6 or suf not in ("SH", "SZ"):
            return None
        return ("sh." if suf == "SH" else "sz.") + code

    b_rows_all = [
        {"symbol": sym, "end_date": r["end_date"], "ann_date": r["ann_date"],
         "update_flag": r["update_flag"], "type": r["type"],
         "primary_code": r["primary_code"],
         "net_profit_min": r["net_profit_min"],
         "net_profit_max": r["net_profit_max"]}
        for r in merged.iter_rows(named=True)
        if (sym := _ts_to_symbol(r["ts_code"])) is not None]
    log(f"  B rows (dev, all versions): {len(b_rows_all)}")
    del ri, ann, ann_rows, raw, raw_parts, raw_key, merged
    check_budget("b-data")

month_ends = [t for t, _ in pool_by_month]


def _pool_member(sym: str, d: date) -> bool:
    j = bisect_right(month_ends, d)
    if j == 0:
        return False
    return sym in pool_set.get(month_ends[j - 1], set())


def _tda(d: date) -> date:
    j = bisect_right(calendar_full, d)
    return calendar_full[j] if j < len(calendar_full) else d


# === 3. per-arm event construction ===========================================
elig_cache: dict[tuple, list[TriggerEvent]] = {}


def build_arm_events(p: FamilyParams):
    if p.family == "RND":
        return random_month_picks(pool_by_month, p.rnd_seed)
    if p.family in ("A1", "A2"):
        ck = (p.family, p.rs_quantile, p.vc_ratio, p.use_rs_filter,
              p.pullback_days)
        if ck not in elig_cache:
            elig_cache[ck] = scan_a_triggers(pool_by_month, series,
                                             atr_of, p)
        return elig_cache[ck]
    if p.family == "B1":
        return b1_revision_events(b_rows_all, series, _pool_member, _tda, p)
    if p.family == "B2":
        return b2_announcement_events(b_rows_all, series, pool_by_month,
                                      _pool_member, p)
    raise ValueError(p.family)


arm_events: dict[str, list] = {}
for name, p in CFG["arms"].items():
    evs = build_arm_events(p)
    arm_events[name] = evs
    n_sym = len({e.symbol for e in evs})
    log(f"  events[{name}]: {len(evs)} triggers / {n_sym} symbols")
    check_budget(f"events-{name}")

# === 4. engine frames ========================================================
_union = sorted({e.symbol for evs in arm_events.values() for e in evs})
daily_full, _meta = load_daily_panel(DAILY_PARQUET)
daily = (daily_full.filter(pl.col("symbol").is_in(_union))
         .filter((pl.col("date") >= WIN0) & (pl.col("date") <= WIN1))
         .sort("symbol", "date"))
assert_frozen(daily, "date", "daily-stocks")
del daily_full
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
half_parts = []
for part in parts:
    f = pl.read_parquet(part)
    f = f.filter((pl.col("trade_date") >= WIN0)
                 & (pl.col("trade_date") <= WIN1)
                 & (pl.col("trade_date") <= FREEZE_END))
    f = f.filter(pl.col("symbol").is_in(_union))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame(
    schema={"trade_date": pl.Date, "symbol": pl.String, "session": pl.String,
            "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
            "close": pl.Float64})
del half_parts
assert_frozen(half, "trade_date", "halfday")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits = (limits_full.rename({"up_limit": "limit_up",
                              "down_limit": "limit_down"})
          .filter(pl.col("symbol").is_in(_union))
          .filter((pl.col("date") >= WIN0) & (pl.col("date") <= WIN1))
          .sort("symbol", "date"))
del limits_full
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(_union))
dividends = divs_all.filter(pl.col("symbol").is_in(_union))
del splits_all, divs_all
instruments = pl.DataFrame({"symbol": _union,
                            "is_etf": [False] * len(_union),
                            "is_t0": [False] * len(_union)})
log(f"  frames: {len(_union)} traded symbols; daily {daily.height}; "
    f"half {half.height}")
check_budget("frames")

session_pairs = sorted({(d, s) for d, s in zip(
    half["trade_date"].to_list(), half["session"].to_list())},
    key=lambda x: (x[0], 0 if x[1] == "am" else 1))
session_index = {sp: i for i, sp in enumerate(session_pairs)}
log(f"  decision points: {len(session_index)}")


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


_am_ix: dict[str, tuple] = {}
if half.height:
    amf = half.filter(pl.col("session") == "am")
    for (sym,), g in amf.partition_by("symbol", as_dict=True).items():
        _am_ix[str(sym)] = (_dint(g["trade_date"]),
                            g["close"].to_numpy().astype(np.float64))


def price_at(sym: str, d: date, sess: str) -> float | None:
    if sess == "am":
        a = _am_ix.get(sym)
        if a is None:
            return None
        i = int(np.searchsorted(a[0], dint_of(d)))
        return float(a[1][i]) if i < len(a[0]) and int(a[0][i]) == dint_of(d) \
            else None
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d)))
    return float(a[1][i]) if i < len(a[0]) and int(a[0][i]) == dint_of(d) \
        else None


ledger_marks = LedgerMarks(daily, half)

# === 5. arm replay ===========================================================
SNR_WIDE = {"atr_mult": 3.0, "dist_min": 0.10, "dist_max": 0.20}


def run_arm(name: str, p: FamilyParams, *, fee_model=None,
            delay_sessions: int | None = None):
    trail_on = name in TRAIL_MARK
    snr = SingleNameRules(atr_of, trail_after_1r=trail_on,
                          high20_getter=(high20 if trail_on else None),
                          **SNR_WIDE)
    host = DynamicOverlayHost("D3", ledger_marks, trim_intent="risk")
    efp = EventFamilyProvider(p, arm_events[name], series, host, snr,
                              price_at, month_ends, session_index)
    prov = efp.provider
    if delay_sessions:
        prov = make_delayed_provider(prov, delay_sessions)
    t_c = time.perf_counter()
    res = run_band_backtest_intents(
        None, daily, half, limits, splits, dividends, instruments,
        symbol_meta={}, initial_cash=INITIAL_CASH,
        execution_clock="halfday", intent_provider=prov,
        fees=fee_model)
    wall = time.perf_counter() - t_c
    il = res.stats.get("intent_layer") or {}
    k3 = res.stats.get("k3_fallback") or {}
    log(f"  {name}: {wall:.1f}s; injected {il.get('dynamic_injected')} "
        f"orders {il.get('orders_generated')} filled "
        f"{il.get('stopped_filled')}; k3 armed {k3.get('armed')} exec "
        f"{k3.get('executed')}; trig {efp.trig}; warnings "
        f"{len(res.warnings)}")
    return {"res": res, "wall_s": wall, "efp": efp, "snr": snr}


results: dict[str, dict] = {}
STRESS_ARMS: list[tuple[str, dict]] = []      # (name, extra cfg)
if CFG["stress"] is None:
    for name, p in CFG["arms"].items():
        results[name] = run_arm(name, p)
        check_budget(name)
elif CFG["stress"] == "delay":
    for n_sess, tag in ((1, "d1h"), (2, "d1d")):
        for name, p in CFG["arms"].items():
            key = f"{name}-{tag}"
            results[key] = run_arm(name, p, delay_sessions=n_sess)
            check_budget(key)
elif CFG["stress"] == "cost":
    fee2 = FeeModel(commission_rate=2e-4)
    for name, p in CFG["arms"].items():
        results[f"{name}-fee2x"] = run_arm(name, p, fee_model=fee2)
        check_budget(f"{name}-fee2x")
    for name, p in CFG["arms"].items():
        results[f"{name}-slip20"] = run_arm(name, p)
        check_budget(f"{name}-slip20")

# === 6. metrics ==============================================================
def cagr_from_equity(sessions, equity):
    if len(sessions) < 2 or equity[0] <= 0:
        return float("nan")
    days = (sessions[-1] - sessions[0]).days
    return (equity[-1] / equity[0]) ** (365.25 / max(days, 1)) - 1.0


def mdd_from_equity(equity):
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1.0)
    return mdd


def year_returns(sessions, equity):
    per: dict[int, float] = {}
    for d, e in zip(sessions, equity):
        per[d.year] = e
    years = sorted(per)
    return {years[i + 1]: per[years[i + 1]] / per[years[i]] - 1.0
            for i in range(len(years) - 1)}


def drawdown_spans(sessions, equity):
    spans, peak_i, trough_i = [], 0, 0
    for i in range(1, len(equity)):
        if equity[i] >= equity[peak_i]:
            spans.append({"peak": sessions[peak_i].isoformat(),
                          "trough": sessions[trough_i].isoformat(),
                          "end": sessions[i].isoformat(),
                          "len_sessions": i - peak_i,
                          "depth": equity[trough_i] / equity[peak_i] - 1.0,
                          "recovered": True})
            peak_i = i
            trough_i = i
        elif equity[i] < equity[trough_i]:
            trough_i = i
    open_span = None
    if peak_i < len(equity) - 1:
        open_span = {"peak": sessions[peak_i].isoformat(),
                     "trough": sessions[trough_i].isoformat(),
                     "end": sessions[-1].isoformat(),
                     "len_sessions": len(equity) - 1 - peak_i,
                     "depth": equity[trough_i] / equity[peak_i] - 1.0,
                     "recovered": False}
    best = max(spans + ([open_span] if open_span else []),
               key=lambda s: s["len_sessions"], default=None)
    return {"longest": best, "open_at_end": open_span}


def exposure_stats(res):
    dates = res.daily["date"].to_list()
    eq = res.daily["equity"].to_list()
    per: dict[str, list] = {}
    if res.fills.height:
        for r in (res.fills.select("symbol", "date", "side", "shares")
                  .iter_rows(named=True)):
            per.setdefault(r["symbol"], []).append(
                (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    state: dict[str, list] = {}
    w_sum = w_n = 0
    w_peak = 0.0
    for d, e in zip(dates, eq):
        if e <= 0:
            continue
        td = dint_of(d)
        mv = 0.0
        for sym, evs in per.items():
            st = state.setdefault(sym, [0, 0])
            while st[1] < len(evs) and evs[st[1]][0] <= td:
                ev = evs[st[1]]
                st[0] += ev[2] if ev[1] == "buy" else -ev[2]
                st[1] += 1
            if st[0] > 0:
                px = close_le(sym, d)
                if px and px > 0:
                    mv += st[0] * px
        w = mv / e
        w_sum += w
        w_n += 1
        w_peak = max(w_peak, w)
    return {"mean": w_sum / max(w_n, 1), "peak": w_peak}


def turnover_stats(res):
    eq = res.daily["equity"].to_list()
    mean_eq = sum(eq) / max(len(eq), 1)
    sell_n = buy_n = 0.0
    if res.fills.height:
        for r in (res.fills.select("side", "shares", "price")
                  .iter_rows(named=True)):
            notional = float(r["shares"]) * float(r["price"])
            if r["side"] == "sell":
                sell_n += notional
            else:
                buy_n += notional
    return {"sell_notional": sell_n, "buy_notional": buy_n,
            "mean_equity": mean_eq,
            "sell_over_mean_equity":
                sell_n / mean_eq if mean_eq > 0 else None}


def _tally_reasons(reasons):
    out: dict[str, int] = {}
    for key in {(r["symbol"], r["source"], r["reason"]) for r in reasons}:
        out[key[2]] = out.get(key[2], 0) + 1
    return out


def _tally_rows(reasons):
    out: dict[str, int] = {}
    for r in reasons:
        out[r["reason"]] = out.get(r["reason"], 0) + 1
    return out


def _tally_filled(reasons, fills):
    events: dict[str, list] = {}
    for r in reasons:
        events.setdefault(r["symbol"], []).append(
            (date.fromisoformat(r["source"]), r["reason"],
             r["day"] + r["sess"]))
    for v in events.values():
        v.sort()
    done = set()
    if fills.height:
        for r in fills.select("symbol", "side", "decision_date",
                              "decision_session").iter_rows(named=True):
            if r["side"] != "sell":
                continue
            evs = events.get(r["symbol"], [])
            best = None
            for src_d, rsn, fk in evs:
                if src_d <= r["decision_date"]:
                    if best is None or (src_d, fk) > (best[0], best[2]):
                        best = (src_d, rsn, fk)
            if best is not None:
                done.add((r["symbol"], best[0].isoformat(), best[1]))
    out: dict[str, int] = {}
    for _s, _d, rsn in done:
        out[rsn] = out.get(rsn, 0) + 1
    return out


def slippage_stress(res, slip=0.002):
    """Post-hoc 0.2%-adverse slippage reconstruction (lower bound: no
    reinvestment compounding of the extra costs)."""
    sd = res.daily["date"].to_list()
    sv = res.daily["equity"].to_list()
    if not res.fills.height:
        return {"net_cagr": float("nan"), "max_drawdown": float("nan")}
    cum = 0.0
    fi = 0
    fills_sorted = res.fills.sort(["date"])
    rows = [(r["date"], float(r["shares"]) * float(r["price"]))
            for r in fills_sorted.iter_rows(named=True)]
    out_eq = []
    for d, e in zip(sd, sv):
        while fi < len(rows) and rows[fi][0] <= d:
            cum += slip * rows[fi][1]
            fi += 1
        out_eq.append(e - cum)
    return {"net_cagr": cagr_from_equity(sd, out_eq),
            "max_drawdown": mdd_from_equity(out_eq)}


metrics: dict[str, dict] = {}
for name in results:
    res = results[name]["res"]
    efp = results[name]["efp"]
    sd = res.daily["date"].to_list()
    sv = res.daily["equity"].to_list()
    net = cagr_from_equity(sd, sv)
    if res.fills.height:
        t0 = res.fills["date"].min()
        i0 = next(i for i, d in enumerate(sd) if d >= t0)
        net_inv = cagr_from_equity(sd[i0:], sv[i0:])
    else:
        net_inv, t0 = float("nan"), None
    trig = dict(efp.trig)
    exec_rate = (trig["filled"] / trig["issued"]
                 if trig["issued"] else None)
    m = {
        "net_cagr": net, "net_cagr_investable_start": net_inv,
        "max_drawdown": mdd_from_equity(sv),
        "net_by_year": {int(k): v for k, v in
                        year_returns(sd, sv).items()},
        "n_fills": res.fills.height,
        "final_equity": sv[-1],
        "total_fees": float(res.fills["fees_total"].sum())
        if res.fills.height else 0.0,
        "exposure": exposure_stats(res),
        "turnover": turnover_stats(res),
        "drawdown": drawdown_spans(sd, sv),
        "trigger_stats": trig,
        "entry_execution_rate": exec_rate,
        "engine_fill_rate": res.stats.get("fill_rate_order_session"),
        "engine_warnings": len(res.warnings),
        "reasons_provider": _tally_reasons(efp.reason_log),
        "reasons_provider_rows": _tally_rows(efp.reason_log),
        "reasons_completed": _tally_filled(efp.reason_log, res.fills),
    }
    if name.endswith("-slip20"):
        m["slippage_stress"] = slippage_stress(res)
    metrics[name] = m
    dd = m["drawdown"]["longest"]
    log(f"  {name}: net {net*100:+.2f}% (inv {net_inv*100:+.2f}%) "
        f"mdd {m['max_drawdown']*100:.2f}% dd-len "
        f"{dd['len_sessions'] if dd else 0} expo "
        f"{m['exposure']['mean']*100:.1f}% fills {res.fills.height} "
        f"exec_rate {exec_rate if exec_rate is None else round(exec_rate, 3)}")

# === 7. BM2 ==================================================================
bm2 = None
if CFG["bm2"]:
    calendar_win = [d for d in calendar_full if WIN0 <= d <= WIN1]
    idx_df = pl.DataFrame({"date": calendar_win,
                           "mkt_idx_new": list(range(len(calendar_win)))},
                          schema={"date": pl.Date, "mkt_idx_new": pl.Int64})
    hist_win = (hist.filter((pl.col("date") >= WIN0)
                            & (pl.col("date") <= WIN1))
                .join(idx_df, on="date", how="inner")
                .drop("mkt_idx").rename({"mkt_idx_new": "mkt_idx"}))
    bank = r16.PriceBank(hist_win, calendar_win, pool_union)
    pools_full = {t: {"ranked": pools_at[t]["ranked"], "q5": {},
                      "n": len(pools_at[t]["ranked"])} for t in sig_days}
    exposures = {t: 1.0 for t in sig_days}
    bm2 = r16.simulate_r16("BM2", bank, calendar_win, WIN0, sig_days,
                           pools_full, exposures, K=0, fractional=True,
                           fee_bands=r16.STOCK_FEE_SCHEDULE,
                           capital=INITIAL_CASH)
    bm2_net = cagr_from_equity(bm2.sessions, bm2.equity)
    bm2_years = {int(k): v for k, v in
                 year_returns(bm2.sessions, bm2.equity).items()}
    metrics["BM2"] = {"net_cagr": bm2_net,
                      "max_drawdown": mdd_from_equity(bm2.equity),
                      "net_by_year": bm2_years,
                      "drawdown": drawdown_spans(bm2.sessions, bm2.equity),
                      "final_equity": bm2.equity[-1], "n_fills": None}
    log(f"  BM2: net {bm2_net*100:+.2f}% "
        f"mdd {metrics['BM2']['max_drawdown']*100:.2f}%")
    check_budget("bm2")

# === 8. gates (informational; report finalises) ==============================
gates: dict[str, dict] = {}
for name in list(CFG["arms"]) + [k for k in results if k not in CFG["arms"]]:
    if name not in metrics:
        continue
    m = metrics[name]
    if "slippage_stress" in m or name.startswith(("RND",)):
        continue
    yrs = m["net_by_year"]
    gate_years = {y: r for y, r in yrs.items() if y > WIN0.year}
    info = {"cagr_pos": m["net_cagr"] > 0,
            "beats_bm1": m["net_cagr"] > BM1_CAGR,
            "mdd_ok": m["max_drawdown"] >= -0.25}
    if bm2 is not None:
        by = bm2_years
        pos_years = [y for y, r in gate_years.items()
                     if y in by and r > by[y]]
        info["excess_years_vs_bm2"] = f"{len(pos_years)}/{len(gate_years)}"
    gates[name] = info

# === 9. outputs ==============================================================
out_dir = RUN_DIR / "outputs"
out_dir.mkdir(parents=True, exist_ok=True)
for name in results:
    res = results[name]["res"]
    tag = name.replace("/", "_")
    res.fills.write_parquet(out_dir / f"{tag}_fills.parquet")
    res.events.write_parquet(out_dir / f"{tag}_events.parquet")
    res.daily.write_parquet(out_dir / f"{tag}_daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / f"{tag}_clips_final.parquet")
    pl.DataFrame(results[name]["efp"].reason_log,
                 schema={"day": pl.String, "sess": pl.String,
                         "symbol": pl.String, "reason": pl.String,
                         "source": pl.String, "intent": pl.String}
                 ).write_csv(out_dir / f"{tag}_exit_reason_log.csv")
if bm2 is not None:
    pl.DataFrame({"date": bm2.sessions, "equity": bm2.equity}).write_csv(
        out_dir / "BM2_equity.csv")

SELF_SHA_END = sha256_file(SELF_PY)
if SELF_SHA_END != SELF_SHA_START:
    _fail("runner script changed during execution -- archived != executed")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-event-families",
    "status": "completed",
    "group": GROUP,
    "attempts_this_group": CFG["attempts"],
    "frozen_interpretive_choices": [
        "TYPE_ORDER total order for B1 strict improvement",
        "IMPROVE_CODES includes impairment (T1 empirical direction)",
        "A1 volume = prior-20 mean excluding trigger day; 60d high "
        "strictly above prior 60 closes; MA20 includes the day",
        "B1 compares adjacent versions by (ann_date, update_flag); "
        "same-day pairs never fire",
        "B holding age from the earliest live clip; time exit is "
        "profit-class (no K=3 fallback)",
        "entry chase cap = issue while decision anchor <= trigger "
        "price * 1.01 (re-checked on every re-issue)",
        "trail perturbation: line = max over time of (20-session high "
        "strictly before the day - 1*ATR20), +3R clear off, +2R half "
        "kept, wide stop kept",
        "delay stress re-stamps decision fields at release; source "
        "and expiry preserved",
        "commission x2 doubles the RATE only (5-CNY minimum kept); "
        "0.2% slippage is a post-hoc per-fill reconstruction (no "
        "reinvestment compounding)"],
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/tmp/runner_eventfam.py",
                GROUP],
    "runner_self": {"sha256_at_start": SELF_SHA_START,
                    "sha256_at_end": SELF_SHA_END},
    "git": {"head": GIT_HEAD, "branch": GIT_BRANCH,
            "dirty_untracked_lines": len(
                [l for l in GIT_PORCELAIN.splitlines() if l.strip()]),
            "committed": False},
    "dependencies": {"python": sys.version.split()[0], **DEPS},
    "peak_memory_mb": psutil.Process().memory_info().peak_wset / (1 << 20),
    "account": {"initial_cash": INITIAL_CASH,
                "legs": "stocks+cash (no ETF, cash earns nothing)"},
    "engine": {"sha256_at_start": pins["engine"]["sha256"],
               "sha256_at_end": sha256_file(ENGINE_PY)},
    "arms": {n: {"family": p.family, "describe": p.describe(),
                 "n_events": len(arm_events.get(n, []))}
             for n, p in CFG["arms"].items()},
    "bm1_reference": {"run": str(BASELINE_RUN.relative_to(ROOT)),
                      "net_cagr": BM1_CAGR},
    "pins": pins,
    "module_pins": {
        name: sha256_file(ROOT / rel) for name, rel in [
            ("single_name_rules", "src/quant/research/single_name_rules.py"),
            ("event_family_signals",
             "src/quant/research/event_family_signals.py"),
            ("risk_overlay_runner",
             "src/quant/research/risk_overlay_runner.py"),
            ("p2r16_trend_dispersion",
             "src/quant/research/p2r16_trend_dispersion.py")]},
    "seeds": {"engine": "deterministic", "rnd_arms": "numpy default_rng "
              "per arm seed", "pool_dedup": "events sorted by (day, "
              "-rank_key, symbol)"},
    "window": [str(WIN0), str(WIN1)],
    "metrics": metrics,
    "gates_informational": gates,
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(out_dir.rglob("*")) if p.is_file()},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter()-T0:.0f}s; "
    f"peak {manifest['peak_memory_mb']:.0f}MB ==")
_logf.close()
