# -*- coding: utf-8 -*-
"""C0 correction run: B1 attribution v2 (boundary-aware, fill-cost
anchored, per-event funnel).

Review doc: quant_phase_ab_review_20260921 §三/§四/§八-C0.  Zero strategy
trials consumed: the B1 replay below uses the IDENTICAL config as the
phase-B main run (same pinned inputs, same code path, no parameter
change); assertions require the replay's fills and equity curve to be
bit-identical to the archived main-run outputs BEFORE any statistic is
emitted.  Statistics are pure post-processing of the replay ledger.

Fixes vs run 20260921T230639-eventfam-attrib-f38756:
1. every fixed-20-session label is boundary-aware (start/end dates,
   window_complete, crosses_dev_boundary); aggregates use complete
   windows only -- Dev statistics cannot read 2021+ prices;
2. the funnel separates slot_full / risk_blocked / held_or_pending /
   no_price / cap from order-unfilled (ttl/level/cap cancels), validated
   against the provider's own trigger counters;
3. post-fill returns anchor at the ACTUAL fill price (fill_cost_return),
   decision->fill drift uses actual decision anchor vs fill price, and
   per-event realized net PnL comes from the engine ledger (FIFO lots
   + dividend cash);
4. events carry type_upgrade / numeric_revision / numeric_available
   flags (review §六) so a strict-numeric arm can be preregistered later.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as _im
import json
import re
import subprocess
import sys
import time
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
import psutil  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.attribution_lib import (  # noqa: E402
    BuyLot, DividendCash, SellFill, classify_admission, complete_stats,
    decision_to_fill_return, fill_cost_return, fifo_event_pnl, tr_window)
from quant.research.event_family_signals import (  # noqa: E402
    BEvent, EventFamilyProvider, FamilyParams, SymbolSeries, TriggerEvent,
    MAX_SEATS, _attack_entries_allowed, b1_revision_events,
    b2_announcement_events, scan_a_triggers)
from quant.research.fixed_scheme_lib import build_atr20  # noqa: E402
from quant.research.risk_overlay_runner import (  # noqa: E402
    DynamicOverlayHost, LedgerMarks)
from quant.research.single_name_rules import SingleNameRules  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, assert_frozen, batch_aggregate_sha256, load_daily_panel,
    load_dividends_h5, load_split_factor_h5, load_stk_limit_batch,
    run_band_backtest_intents)

MAIN_RUN = ROOT / "artifacts/runs/20260921T223157-eventfam-main-cb4cff"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
T1_DIR = ROOT / "data/features/fcst-reason-struct-full-20260918"
FCST_RAW_DIR = ROOT / "data/raw/tushare/forecast/20260909-r1"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
SNR_PY = ROOT / "src/quant/research/single_name_rules.py"
EFS_PY = ROOT / "src/quant/research/event_family_signals.py"
ATTR_LIB_PY = ROOT / "src/quant/research/attribution_lib.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
B_DEV_FIRST, B_DEV_LAST = "20180904", "20201231"
WIN_SESSIONS = 20
INITIAL_CASH = 500_000.0
SNR_WIDE = {"atr_mult": 3.0, "dist_min": 0.10, "dist_max": 0.20}

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
LOG_PATH = RUN_DIR / "logs" / "runner.log"
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
        "run_id": RUN_DIR.name,
        "experiment_id": "exp-20260921-eventfam-attribution",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


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
DEPS = {p: _im.version(p) for p in ("polars", "numpy", "psutil")}
log(f"self {SELF_SHA_START[:16]}; git {GIT_BRANCH} {GIT_HEAD[:12]}")

# === 0. pins (main-run identity) ============================================
pins: dict = {}
for name, p in [("engine", ENGINE_PY), ("snr_module", SNR_PY),
                ("event_family_signals", EFS_PY),
                ("attribution_lib", ATTR_LIB_PY),
                ("daily", DAILY_PARQUET),
                ("main_manifest", MAIN_RUN / "manifest.json"),
                ("main_B1_fills", MAIN_RUN / "outputs" / "B1_fills.parquet"),
                ("main_B1_daily", MAIN_RUN / "outputs"
                 / "B1_daily_equity.parquet"),
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
pins["fcst_raw_chunks"] = {"n": len(fcst_chunk_shas), "sha256": fcst_chunk_shas}
log(f"  pins OK ({len(fcst_chunk_shas)} fcst chunks)")

# === 1. calendar / pools (verbatim from the main runner, DEV window) ========
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days = [d for d in all_mes["s"].to_list() if
            idx_of_full.get(d, 10**9) + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_by_month = [(t, pools_at[t]["ranked"]) for t in sig_days]
pool_set = {t: set(pools_at[t]["ranked"]) for t in sig_days}
pool_union = sorted(set().union(*pool_set.values()))
log(f"  pools: {len(sig_days)} months, union {len(pool_union)} symbols")

WARM_START = DEV_START - timedelta(days=300)
pool_daily = (
    pl.scan_parquet(DAILY_PARQUET)
    .filter((pl.col("tradestatus") == 1.0)
            & pl.col("symbol").is_in(pool_union)
            & (pl.col("date") >= WARM_START) & (pl.col("date") <= DEV_END))
    .select("symbol", "date", "high", "low", "close", "volume")
    .collect())
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
daily_ext_pool = (
    pl.scan_parquet(DAILY_PARQUET)
    .filter(pl.col("symbol").is_in(pool_union)
            & (pl.col("date") >= WARM_START) & (pl.col("date") <= DEV_END))
    .select("symbol", "date", "high", "low", "close")
    .collect())
atr_tbl = build_atr20(daily_ext_pool)
atr_of = lambda s, d: atr_tbl.atr(s, d)  # noqa: E731
log(f"  series: {len(series)}")

# c_adj (total-return) lookup, same warm start as the v1 attribution
cadj: dict[str, tuple] = {}
for (s,), g in (hist.filter(pl.col("date") >= date(2014, 6, 1))
                .partition_by("symbol", as_dict=True)).items():
    cadj[str(s)] = (
        [d.toordinal() for d in g["date"].to_list()],
        g["c_adj"].to_numpy().astype(np.float64))

# raw close lookup (fill-cost calibration) from the engine daily frame
raw_close: dict[str, tuple] = {}

month_ends = [t for t, _ in pool_by_month]


def _pool_member(sym: str, d: date) -> bool:
    j = bisect_right(month_ends, d)
    if j == 0:
        return False
    return sym in pool_set.get(month_ends[j - 1], set())


def _tda(d: date) -> date:
    j = bisect_right(calendar_full, d)
    return calendar_full[j] if j < len(calendar_full) else d


# === 2. B rows + all four event lists (identity vs main manifest) ===========
ri = pl.read_parquet(T1_DIR / "row_index.parquet").filter(
    (pl.col("ann_date") >= B_DEV_FIRST) & (pl.col("ann_date") <= B_DEV_LAST))
ann_rows = []
for p in sorted(T1_DIR.glob("batch_*.jsonl")):
    with p.open("r", encoding="utf-8") as f:
        ann_rows.extend(json.loads(x) for x in f)
ann = pl.DataFrame(ann_rows)
KEY = ["ts_code", "end_date", "ann_date", "update_flag"]
merged = ri.join(ann.select(KEY + ["primary_code"]), on=KEY, how="inner")
raw = pl.concat(
    [pl.read_csv(p) for p in sorted(FCST_RAW_DIR.glob("chunk_*.csv"))
     if B_DEV_FIRST[:6] <= p.stem.replace("chunk_", "") <= B_DEV_LAST[:6]],
    how="vertical").with_columns(
    pl.col("end_date").cast(pl.String), pl.col("ann_date").cast(pl.String),
    pl.col("update_flag").cast(pl.String))
merged = merged.join(raw.select(KEY + ["net_profit_min", "net_profit_max"]),
                     on=KEY, how="left")


def _ts(sym_ts):
    try:
        code, suf = sym_ts.split(".")
        return ("sh." if suf == "SH" else "sz.") + code if len(code) == 6 \
            and suf in ("SH", "SZ") else None
    except ValueError:
        return None


b_rows = [{"symbol": s, "end_date": r["end_date"], "ann_date": r["ann_date"],
           "update_flag": r["update_flag"], "type": r["type"],
           "primary_code": r["primary_code"],
           "net_profit_min": r["net_profit_min"],
           "net_profit_max": r["net_profit_max"]}
          for r in merged.iter_rows(named=True)
          if (s := _ts(r["ts_code"])) is not None]
log(f"  B rows: {len(b_rows)}")

P = {"A1": FamilyParams("A1"), "A2": FamilyParams("A2"),
     "B1": FamilyParams("B1"), "B2": FamilyParams("B2")}
events = {"A1": scan_a_triggers(pool_by_month, series, atr_of, P["A1"]),
          "A2": scan_a_triggers(pool_by_month, series, atr_of, P["A2"]),
          "B1": b1_revision_events(b_rows, series, _pool_member, _tda, P["B1"]),
          "B2": b2_announcement_events(b_rows, series, pool_by_month,
                                       _pool_member, P["B2"])}
main_mf = json.loads((MAIN_RUN / "manifest.json").read_text(encoding="utf-8"))
for k in P:
    n_run = main_mf["arms"][k]["n_events"]
    if len(events[k]) != n_run:
        _fail(f"{k}: rebuilt {len(events[k])} != run {n_run}")
    log(f"  events[{k}] = {len(events[k])} == run manifest (identity OK)")

# B1 default-path flag sanity: main arm must remain type-OR-numeric
b1_flags = {"type_upgrade": sum(e.type_upgrade for e in events["B1"]),
            "numeric_revision": sum(e.numeric_revision for e in events["B1"]),
            "numeric_available": sum(e.numeric_available for e in events["B1"])}
ev_ids = [f"{e.symbol}|{e.end_date}|a{e.ann_date.isoformat()}|u{e.update_flag}"
          for e in events["B1"]]
if len(set(ev_ids)) != len(ev_ids):
    _fail("B1 event ids collide")
# strict-numeric event-set probes (counting only; zero trials): the
# review-S6 question answered at the event-set level
n_strict_default = len(b1_revision_events(
    b_rows, series, _pool_member, _tda,
    FamilyParams("B1", label="probe-strict-numeric", b1_strict_numeric=True)))
n_strict_floor = len(b1_revision_events(
    b_rows, series, _pool_member, _tda,
    FamilyParams("B1", label="probe-strict-numeric-floor",
                 b1_strict_numeric=True, b1_floor_must_rise=True)))
b1_flags["strict_numeric_events"] = n_strict_default
b1_flags["strict_numeric_floor_rise_events"] = n_strict_floor
log(f"  B1 flags: {b1_flags}")

# === 3. engine frames (union over ALL four arms, as in the main run) ========
_union = sorted({e.symbol for evs in events.values() for e in evs})
daily_full, _meta = load_daily_panel(DAILY_PARQUET)
daily = (daily_full.filter(pl.col("symbol").is_in(_union))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .sort("symbol", "date"))
del daily_full
assert_frozen(daily, "date", "daily-stocks")
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
half_parts = []
for part in parts:
    f = pl.read_parquet(part)
    f = f.filter((pl.col("trade_date") >= DEV_START)
                 & (pl.col("trade_date") <= DEV_END)
                 & (pl.col("trade_date") <= FREEZE_END))
    f = f.filter(pl.col("symbol").is_in(_union))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical")
del half_parts
assert_frozen(half, "trade_date", "halfday")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits = (limits_full.rename({"up_limit": "limit_up",
                              "down_limit": "limit_down"})
          .filter(pl.col("symbol").is_in(_union))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
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
log(f"  frames: {len(_union)} symbols; daily {daily.height}; "
    f"half {half.height}")

session_pairs = sorted({(d, s) for d, s in zip(
    half["trade_date"].to_list(), half["session"].to_list())},
    key=lambda x: (x[0], 0 if x[1] == "am" else 1))
session_index = {sp: i for i, sp in enumerate(session_pairs)}


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
    raw_close[str(sym)] = (_dint(g["date"]),
                           g["close"].to_numpy().astype(np.float64))


def close_le(sym: str, d: date) -> float | None:
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d), side="right")) - 1
    return float(a[1][i]) if i >= 0 else None


_am_ix: dict[str, tuple] = {}
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


def raw_close_le(sym: str, d: date) -> float | None:
    a = raw_close.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d), side="right")) - 1
    return float(a[1][i]) if i >= 0 else None


# === 4. instrumented B1 replay ==============================================
class LoggingProvider(EventFamilyProvider):
    """Pass-through wrapper: records per-event admission and per-event
    order-lifecycle terminal state at every decision point."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.admission: list[dict] = []
        self.ev_outcome: dict[tuple, dict] = {}
        self.pending_span: dict[str, dict] = {}

    @staticmethod
    def ev_key(ev) -> tuple:
        return (ev.symbol, ev.end_date, ev.ann_date.isoformat(),
                ev.update_flag)

    def provider(self, day: date, sess: str, ledger: dict):
        held = {str(p["symbol"]) for p in ledger["positions"]
                if int(p["shares"]) > 0}
        pending_before = dict(self.pending)
        trig_before = dict(self.trig)
        rows = super().provider(day, sess, ledger)
        step = self.host.steps[-1]
        entry_allowed = _attack_entries_allowed(step.risk_state)
        pending_after = set(self.pending)
        newly = pending_after - set(pending_before)
        pending_survived = pending_after - newly
        evs = self.events_at.get((day, sess), [])
        outcomes, _counts = classify_admission(
            evs, held, pending_survived, entry_allowed,
            anchor_of=lambda s: self.price_at(s, day, sess),
            cap_of=lambda ev: (float(ev.cap_price)
                               if isinstance(ev, TriggerEvent) else None),
            max_seats=MAX_SEATS, risk_state=step.risk_state)
        for oc, ev in zip(outcomes, evs):
            key = self.ev_key(ev)
            self.admission.append({
                "day": day, "sess": sess, "symbol": ev.symbol,
                "ann_date": ev.ann_date, "decision_day": ev.decision_day,
                "key": key, "rank": oc.rank, "category": oc.category,
                "held_seats": oc.held_seats,
                "pending_seats": oc.pending_seats,
                "risk_state": oc.risk_state,
                "anchor_price": oc.anchor_price})
            if oc.category == "issued":
                self.ev_outcome.setdefault(key, {
                    "issued_at": (day, sess), "outcome": "issued"})
                span = self.pending_span.setdefault(ev.symbol, {
                    "key": key, "start": (day, sess)})
                if span["key"] != key:
                    _fail(f"pending overlap for {ev.symbol}: "
                          f"{span['key']} vs {key}")
        # terminal state of pendings removed at this point
        removed = set(pending_before) - pending_after
        if removed:
            d_trig = {k2: self.trig[k2] - trig_before.get(k2, 0)
                      for k2 in self.trig}
            for sym in removed:
                st = pending_before[sym]
                key = self.ev_key(st["ev"])
                rec = self.ev_outcome.setdefault(key, {"issued_at": None,
                                                       "outcome": "?"})
                if sym in held:
                    rec["outcome"] = "filled"
                else:
                    for reason, cnt_key in (("cancel_ttl", "cancel_ttl"),
                                            ("cancel_level", "cancel_level"),
                                            ("cancel_cap", "cancel_cap")):
                        if d_trig.get(cnt_key, 0) > 0:
                            rec["outcome"] = reason
                            d_trig[cnt_key] -= 1
                            break
                    else:
                        _fail(f"pending removed without counter: {sym} "
                              f"@ {day} {sess}")
                span = self.pending_span.get(sym)
                if span is not None and span["key"] == key:
                    span["end"] = (day, sess)
                    span["end_outcome"] = rec["outcome"]
                    del self.pending_span[sym]
        return rows


snr = SingleNameRules(atr_of, trail_after_1r=False,
                      high20_getter=None, **SNR_WIDE)
host = DynamicOverlayHost("D3", ledger_marks, trim_intent="risk")
efp = LoggingProvider(P["B1"], events["B1"], series, host, snr,
                      price_at, month_ends, session_index)
t_c = time.perf_counter()
res = run_band_backtest_intents(
    None, daily, half, limits, splits, dividends, instruments,
    symbol_meta={}, initial_cash=INITIAL_CASH,
    execution_clock="halfday", intent_provider=efp.provider,
    fees=None)
log(f"  B1 replay: {time.perf_counter() - t_c:.1f}s; fills {res.fills.height}"
    f" warnings {len(res.warnings)}; trig {efp.trig}")

# --- identity: replay == archived main-run outputs (bit-for-bit) ------------
main_fills = pl.read_parquet(MAIN_RUN / "outputs" / "B1_fills.parquet")
main_daily = pl.read_parquet(MAIN_RUN / "outputs" / "B1_daily_equity.parquet")
if not res.fills.sort("fill_id").equals(main_fills.sort("fill_id")):
    _fail("replay fills differ from the archived main-run B1 fills")
if not res.daily.equals(main_daily):
    _fail("replay daily equity differs from the archived main-run B1 curve")
if dict(efp.trig) != main_mf["metrics"]["B1"]["trigger_stats"]:
    _fail(f"replay trigger stats differ: {efp.trig} vs "
          f"{main_mf['metrics']['B1']['trigger_stats']}")
log("  identity OK: fills + daily equity + trigger stats == main run")

# funnel classification must reproduce the provider's own counters
_cls = {}
for r in efp.admission:
    _cls[r["category"]] = _cls.get(r["category"], 0) + 1
_expect = {"issued": efp.trig["issued"],
           "slot_full": efp.trig["skip_slots"],
           "held_or_pending": efp.trig["skip_held"],
           "no_price": efp.trig["skip_anchor"],
           "cap": efp.trig["skip_cap"]}
for k2, v in _expect.items():
    if _cls.get(k2, 0) != v:
        _fail(f"classify_admission {k2}: {_cls.get(k2, 0)} != provider {v}")
n_risk = _cls.get("risk_blocked", 0)
if sum(_cls.values()) != len(events["B1"]):
    _fail("funnel does not account for every event")
log(f"  funnel == provider counters: {_cls} risk_blocked={n_risk}")

# === 5. order / fill linkage from the replay event log ======================
dyn_rows = []      # entry submissions: (symbol, source, day, sess)
for r in res.events.filter(
        pl.col("detail").str.starts_with("dynamic:")).iter_rows(named=True):
    m = re.match(r"dynamic: (\S+)/buy/entry source (\S+)", r["detail"])
    if m:
        dyn_rows.append((m.group(1), m.group(2), r["date"], r["session"]))
order_rows = res.events.filter(
    (pl.col("side") == "buy") & pl.col("symbol").is_not_null())
def _order_point(order_id: str) -> tuple[date, str]:
    tail = order_id.rsplit("buy-", 1)[1]        # YYYY-MM-DD-sess
    return (date.fromisoformat(tail.rsplit("-", 1)[0]),
            tail.rsplit("-", 1)[1])


orders_by_key = {}
for r in order_rows.iter_rows(named=True):
    dd, ss = _order_point(r["order_id"])
    orders_by_key[(r["symbol"], dd, ss)] = r
fills_by_order: dict[str, list] = {}
for r in res.fills.filter(pl.col("side") == "buy").iter_rows(named=True):
    fills_by_order.setdefault(r["order_id"], []).append(r)

sess_ord = {sp: i for i, sp in enumerate(session_pairs)}  # noqa: F841 (audit aid)
sub_by_event: dict[tuple, list] = {}
for sym, source, d, s in dyn_rows:
    hit = [r for r in efp.admission
           if r["symbol"] == sym and r["category"] == "issued"
           and r["decision_day"].isoformat() == source]
    if len(hit) != 1:
        _fail(f"submission {sym} source {source}: {len(hit)} issuing events")
    sub_by_event.setdefault(hit[0]["key"], []).append((d, s))

# per-event FIFO lots / sells / dividends
sub_index: dict[tuple[str, date, str], str] = {}
for sym, source, d, s in dyn_rows:
    if (sym, d, s) in sub_index:
        _fail(f"duplicate entry submission {sym} {d} {s}")
    sub_index[(sym, d, s)] = source
adm_by_sym_source: dict[tuple[str, str], tuple] = {}
for r in efp.admission:
    if r["category"] == "issued":
        k2 = (r["symbol"], r["decision_day"].isoformat())
        if k2 in adm_by_sym_source:
            _fail(f"two issued events share {k2}")
        adm_by_sym_source[k2] = r["key"]

last_day = daily["date"].max()
lots: list[BuyLot] = []
sell_fills: list[SellFill] = []
div_cash: list[DividendCash] = []
seq = 0
for r in res.fills.sort("fill_id").iter_rows(named=True):
    if r["side"] == "sell":
        sell_fills.append(SellFill(
            r["symbol"], int(r["shares"]),
            float(r["net_cash_flow"]), r["date"]))
        continue
    # order_id = sym-buy-YYYY-MM-DD-sess  ->  its submission point
    tail = r["order_id"].rsplit("buy-", 1)[1]          # YYYY-MM-DD-sess
    d0 = date.fromisoformat(tail.rsplit("-", 1)[0])
    dec_s = tail.rsplit("-", 1)[1]
    source = sub_index.get((r["symbol"], d0, dec_s))
    if source is None:
        _fail(f"buy fill {r['order_id']} has no entry submission")
    key = adm_by_sym_source.get((r["symbol"], source))
    if key is None:
        _fail(f"buy fill {r['order_id']} has no issuing event")
    seq += 1
    lots.append(BuyLot(event_id="|".join(key), symbol=r["symbol"],
                       shares=int(r["shares"]),
                       net_cash_flow=float(r["net_cash_flow"]),
                       date=r["date"], seq=seq))

for r in res.events.filter(
        pl.col("event") == "corp_action_dividend").iter_rows(named=True):
    m = re.match(r"(\S+):", r["detail"])
    if m and r["cash_amount"] is not None:
        div_cash.append(DividendCash(m.group(1), float(r["cash_amount"]),
                                     r["date"]))

ev_pnl = fifo_event_pnl(
    lots, sell_fills, div_cash,
    last_close_of=lambda s: close_le(s, last_day))
open_shares = sum(e.open_shares for e in ev_pnl.values())
if open_shares != 0 or res.clips_final.height != 0:
    _fail(f"unexpected open positions at end: lots open {open_shares}, "
          f"clips_final {res.clips_final.height}")
log(f"  FIFO: {len(lots)} buy lots, {len(sell_fills)} sells, "
    f"{len(div_cash)} dividend rows; all closed")

# === 6. per-event funnel table ==============================================
pool_returns_cache: dict[date, dict] = {}


def pool_stats(d: date) -> dict:
    """Same-day pool cross-section, 20-session TR, complete windows only."""
    if d not in pool_returns_cache:
        j = bisect_right(month_ends, d)
        t = month_ends[j - 1] if j > 0 else month_ends[0]
        vals, n_all = [], 0
        for s2 in sorted(pool_set[t]):
            n_all += 1
            a = cadj.get(s2)
            if a is None:
                continue
            w = tr_window(a[0], a[1], d, WIN_SESSIONS, DEV_END)
            if w.no_data:
                continue
            if w.window_complete and w.factor is not None:
                vals.append(w.factor - 1.0)
        pool_returns_cache[d] = {"month_end": t, "n_pool": n_all,
                                 "n_complete": len(vals),
                                 "median": float(np.median(vals)) if vals
                                 else None,
                                 "mean": float(np.mean(vals)) if vals
                                 else None}
    return pool_returns_cache[d]


funnel: list[dict] = []
for ev in events["B1"]:
    key = LoggingProvider.ev_key(ev)
    event_id = f"B1|{ev.symbol}|{ev.end_date}|a{ev.ann_date.isoformat()}" \
               f"|u{ev.update_flag}"
    adm = [r for r in efp.admission if r["key"] == key]
    if len(adm) != 1:
        _fail(f"{event_id}: {len(adm)} admission rows")
    adm = adm[0]
    outcome_rec = efp.ev_outcome.get(key, {"outcome": "never_seen"})
    outcome = outcome_rec["outcome"]
    # --- diagnostic returns (boundary-aware) --------------------------------
    a = cadj.get(ev.symbol)
    w_dec = (tr_window(a[0], a[1], ev.decision_day, WIN_SESSIONS, DEV_END)
             if a else None)
    w_ann = (tr_window(a[0], a[1], ev.ann_date, WIN_SESSIONS, DEV_END)
             if a else None)
    # --- orders / fill -------------------------------------------------------
    subs = sub_by_event.get(key, [])
    order_prices = []
    order_outcomes: dict[str, int] = {}
    fill_price = fill_day = None
    for (d, s) in subs:
        o = orders_by_key.get((ev.symbol, d, s))
        if o is None:
            _fail(f"missing engine order for submission {ev.symbol} {d} {s}")
        if o["limit_price"] is not None:
            order_prices.append(float(o["limit_price"]))
        order_outcomes[o["event"]] = order_outcomes.get(o["event"], 0) + 1
        for fr in fills_by_order.get(o["order_id"], []):
            fill_price = float(fr["price"])
            fill_day = fr["date"]
    dec_anchor = adm["anchor_price"]
    w_fill = (tr_window(a[0], a[1], fill_day, WIN_SESSIONS, DEV_END)
              if (a and fill_day is not None) else None)
    rc = raw_close_le(ev.symbol, fill_day) if fill_day is not None else None
    pnl = ev_pnl.get("|".join([key[0], key[1], key[2], key[3]]))
    ctrl = pool_stats(ev.decision_day)
    reason = (""
              if outcome == "filled"
              else (adm["category"] if adm["category"] != "issued"
                    else outcome))
    funnel.append({
        "event_id": event_id,
        "symbol": ev.symbol,
        "announcement_version": f"{ev.end_date}#u{ev.update_flag}",
        "ann_date": ev.ann_date.isoformat(),
        "decision_time": f"{ev.decision_day.isoformat()} "
                         f"{ev.decision_sess}",
        "start_timestamp": f"{adm['day'].isoformat()} {adm['sess']}",
        "type_upgrade": ev.type_upgrade,
        "numeric_revision": ev.numeric_revision,
        "numeric_available": ev.numeric_available,
        "admission_rank": adm["rank"],
        "risk_state": adm["risk_state"],
        "held_seats": adm["held_seats"],
        "pending_seats": adm["pending_seats"],
        "category": adm["category"],
        "issued": adm["category"] == "issued",
        "order_price_first": order_prices[0] if order_prices else None,
        "order_price_last": order_prices[-1] if order_prices else None,
        "n_submissions": len(subs),
        "order_outcomes": json.dumps(order_outcomes),
        "fill_day": fill_day.isoformat() if fill_day else None,
        "fill_price": fill_price,
        "decision_anchor_price": dec_anchor,
        "skip_or_cancel_reason": reason,
        # --- three separate return columns (review §三) --------------------
        "diag_ret_from_decision_20": (w_dec.factor - 1.0
                                      if w_dec and w_dec.factor is not None
                                      else None),
        "diag_ret_from_announcement_20": (w_ann.factor - 1.0
                                          if w_ann and w_ann.factor
                                          is not None else None),
        "ret_from_fill_cost_20": (fill_cost_return(w_fill, fill_price, rc)
                                  if w_fill is not None else None),
        "decision_to_fill_price_ret": (
            decision_to_fill_return(fill_price, dec_anchor)
            if fill_price is not None else None),
        # --- boundary bookkeeping (review §四) ------------------------------
        "label_end_decision": (w_dec.end_date.isoformat()
                               if w_dec and w_dec.end_date else None),
        "window_complete": bool(w_dec.window_complete) if w_dec else False,
        "crosses_dev_boundary": (bool(w_dec.crosses_dev_boundary)
                                 if w_dec else False),
        # --- matched control / realized pnl ---------------------------------
        "matched_control_return": ctrl["median"],
        "pool_mean_20": ctrl["mean"],
        "pool_n": ctrl["n_pool"],
        "pool_n_complete": ctrl["n_complete"],
        "actual_net_pnl": pnl.realized_net_pnl if pnl else None,
        "buy_cost": pnl.buy_cost if pnl else None,
        "pnl_over_buy_cost": (pnl.realized_net_pnl / pnl.buy_cost
                              if pnl and pnl.buy_cost > 0 else None),
        "sell_proceeds": pnl.sell_proceeds if pnl else None,
        "dividend_cash": pnl.dividend_cash if pnl else None,
        "outcome": outcome,
    })

fdf = pl.DataFrame(funnel)
out_dir = RUN_DIR / "outputs"
fdf.write_parquet(out_dir / "B1_event_funnel.parquet")
fdf.write_csv(out_dir / "B1_event_funnel.csv")
pl.DataFrame([{"event_id": l.event_id, "symbol": l.symbol,
               "shares": l.shares, "net_cash_flow": l.net_cash_flow,
               "date": l.date.isoformat(), "seq": l.seq} for l in lots]
             ).write_csv(out_dir / "B1_buy_lots.csv")
pl.DataFrame([{"decision_day": d.isoformat(), **{k: v for k, v in s.items()
                                                 if k != "month_end"}}
              for d, s in pool_returns_cache.items()]
             ).sort("decision_day").write_csv(out_dir / "pool_control_by_day.csv")
log(f"  funnel table: {fdf.height} events -> outputs/")

# === 7. aggregates ==========================================================
def _col_stats(frame: pl.DataFrame, col: str) -> dict | None:
    v = frame[col].drop_nulls()
    if v.len() == 0:
        return None
    arr = v.to_numpy()
    return {"n": int(v.len()), "mean": float(arr.mean()),
            "median": float(np.median(arr)), "win": float((arr > 0).mean())}


comp = fdf.filter(pl.col("window_complete"))
cens = fdf.filter(~pl.col("window_complete"))
agg: dict = {
    "funnel_counts": _cls,
    "risk_blocked_events": n_risk,
    "events_total": fdf.height,
    "complete_windows": comp.height,
    "censored_windows": cens.height,
    "censored_event_ids": cens["event_id"].to_list(),
    "diag_decision_20": _col_stats(comp, "diag_ret_from_decision_20"),
    "diag_announcement_20": _col_stats(comp, "diag_ret_from_announcement_20"),
    "inc_vs_pool_median_mean_of_diffs": (
        float((comp["diag_ret_from_decision_20"]
               - comp["matched_control_return"]).drop_nulls().mean())),
    "inc_vs_pool_mean_mean_to_mean": (
        float(comp["diag_ret_from_decision_20"].drop_nulls().mean()
              - comp["pool_mean_20"].drop_nulls().mean())),
    "by_category": {},
    "fill_cost_ret_20": _col_stats(comp.filter(pl.col("outcome") == "filled"),
                                   "ret_from_fill_cost_20"),
    "decision_to_fill_ret": _col_stats(
        comp.filter(pl.col("outcome") == "filled"),
        "decision_to_fill_price_ret"),
    "actual_net_pnl": _col_stats(fdf.filter(pl.col("outcome") == "filled"),
                                 "actual_net_pnl"),
    "actual_pnl_over_buy_cost": _col_stats(
        fdf.filter(pl.col("outcome") == "filled"), "pnl_over_buy_cost"),
    "total_filled_net_pnl_cny": float(
        fdf.filter(pl.col("outcome") == "filled")["actual_net_pnl"]
        .drop_nulls().sum()),
    "total_buy_cost_cny": float(
        fdf.filter(pl.col("outcome") == "filled")["buy_cost"]
        .drop_nulls().sum()),
}
for cat in sorted(set(fdf["category"].to_list())):
    sub = comp.filter(pl.col("category") == cat)
    agg["by_category"][cat] = {
        "n": sub.height,
        "diag_decision_20": _col_stats(sub, "diag_ret_from_decision_20"),
        "inc_vs_pool_median": (
            float((sub["diag_ret_from_decision_20"]
                   - sub["matched_control_return"]).drop_nulls().mean())
            if sub.height else None)}
# stability groupings (review §五): month / symbol concentration
comp2 = comp.with_columns(
    pl.col("ann_date").str.slice(0, 7).alias("ann_month"))
agg["stability_by_month"] = {
    r["ann_month"]: {"n": r["n"], "mean_diag": r["mean_diag"]}
    for r in (comp2.group_by("ann_month").agg(
        pl.len().alias("n"),
        pl.col("diag_ret_from_decision_20").mean().alias("mean_diag"))
        .sort("ann_month").to_dicts())}
sym_grp = (comp2.group_by("symbol").agg(
    pl.len().alias("n_events"),
    pl.col("diag_ret_from_decision_20").mean().alias("mean_diag"),
    pl.col("actual_net_pnl").sum().alias("pnl_sum")).sort(
    ["n_events", "symbol"], descending=[True, False]))
agg["stability_by_symbol"] = {
    "n_symbols": sym_grp.height,
    "max_events_one_symbol": int(sym_grp["n_events"].max()),
    "top5_symbols_by_events": sym_grp.head(5).to_dicts(),
    "top5_pnl_share_of_positive": None}
pos_total = sum(v for v in fdf["actual_net_pnl"].drop_nulls().to_list()
                if v > 0)
top5 = sorted([v for v in fdf["actual_net_pnl"].drop_nulls().to_list()],
              reverse=True)[:5]
agg["stability_by_symbol"]["top5_pnl_share_of_positive"] = (
    sum(top5) / pos_total if pos_total > 0 else None)
log(json.dumps({k: agg[k] for k in
                ("funnel_counts", "complete_windows", "censored_windows",
                 "inc_vs_pool_median_mean_of_diffs",
                 "inc_vs_pool_mean_mean_to_mean")}, ensure_ascii=False))

SELF_SHA_END = sha256_file(SELF_PY)
if SELF_SHA_END != SELF_SHA_START:
    _fail("runner script changed during execution -- archived != executed")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-eventfam-attribution",
    "role": "C0-correction (review 2026-09-21 §八; fixes run "
            "20260921T230639-eventfam-attrib-f38756)",
    "status": "completed",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/tmp/runner_attrib2.py"],
    "runner_self": {"sha256_at_start": SELF_SHA_START,
                    "sha256_at_end": SELF_SHA_END},
    "git": {"head": GIT_HEAD, "branch": GIT_BRANCH},
    "dependencies": {"python": sys.version.split()[0], **DEPS},
    "peak_memory_mb": psutil.Process().memory_info().peak_wset / (1 << 20),
    "trials_consumed": 0,
    "trials_note": "B1 replay uses the identical config/inputs as the main "
                   "run; fills + equity + trigger stats asserted bit-equal "
                   "to the archived outputs before statistics are emitted",
    "identity": {"event_counts_equal_main_manifest": True,
                 "fills_equal_main_run": True,
                 "daily_equity_equal_main_run": True,
                 "trigger_stats_equal_main_run": True,
                 "funnel_counts_equal_provider_counters": True},
    "inputs": {"main_run": str(MAIN_RUN.relative_to(ROOT)),
               "main_run_manifest_sha": pins["main_manifest"]["sha256"],
               "b1_flags": b1_flags},
    "pins": pins,
    "aggregates": agg,
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(out_dir.rglob("*")) if p.is_file()},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter()-T0:.0f}s; "
    f"peak {manifest['peak_memory_mb']:.0f}MB ==")
_logf.close()
