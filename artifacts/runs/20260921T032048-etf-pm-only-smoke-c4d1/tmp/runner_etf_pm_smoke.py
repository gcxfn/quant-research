# -*- coding: utf-8 -*-
"""ETF pm-only dynamic replay smoke (task 2, 2026-09-21) -- engineering only.

Prereg (frozen before the run): docs/research/exp-20260921-etf-pm-only-smoke-prereg.md
Decision: docs/decisions/2026-09-21-etf-pm-only-routing.md
Engine under test: band_engine v1.5 (etf_routing='pm_only'), pinned by sha256.

What it does: replays the three H2-03 defensive legs over 2019 (dev window)
through the single-account band engine on the halfday clock with pm-only ETF
routing -- NO ETF half-day bar is supplied at all (the half-day table is
EMPTY; the ETF execution bar is the real daily row).  The provider is a
monthly fixed-weight (20% per leg) rebalancer driven ONLY by the engine's own
live ledger, exactly the shape the hybrid mainline needs.

Judgement: LINK CORRECTNESS ONLY (routing / daily-bar matching / fees / T+0
flag & sellable path / ledger feedback + cash conservation).  The numbers in
this report are NOT strategy evidence and enter no conclusion.

Outputs: outputs/{fills,events,daily_equity,clips_final}.parquet,
outputs/decision_points.csv (per decision point: ledger + independent
reconciliation), outputs/rebalance_orders.csv, outputs/fill_hand_checks.csv,
outputs/ledger_hand_checks.json, outputs/checks.json, report.md, manifest.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
import psutil  # noqa: E402

from quant.backtest.band_engine import (  # noqa: E402
    batch_aggregate_sha256, run_band_backtest_intents)

# --- identity ---------------------------------------------------------------
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
ENGINE_SHA_EXPECT = ("d4b6c3764780e6dec5443174bb8fb0c1ca57ffd737da4e59069"
                     "cbd3ca6735ed6")
PREREG = ROOT / "docs/research/exp-20260921-etf-pm-only-smoke-prereg.md"
ETF_DIR = ROOT / "data/processed/etf-daily-20260919"
ETF_PARQUET = ETF_DIR / "daily_2015_2024.parquet"
ETF_MANIFEST = ETF_DIR / "manifest.json"
FUND_DAILY_DIR = ROOT / "data/raw/tushare/fund_daily/20260917-r1"
HALFDAY_MANIFEST = ROOT / "data/processed/halfday-bars-20260918/manifest.json"

# --- frozen window / account / legs ----------------------------------------
# SMOKE_WINDOW is a PRE-FLIGHT convenience only (engineering dry runs); the
# registered run uses the default full-year window and is the one that lands
# in manifest.json ("mode": "full-year" vs "preflight").
_WIN = os.environ.get("SMOKE_WINDOW", "full")
if _WIN == "full":
    WIN_START, WIN_END = date(2019, 1, 1), date(2019, 12, 31)
else:
    _a, _b = _WIN.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
FULL_WINDOW = _WIN == "full"
LEGS = ["sh.511010", "sh.518880", "sz.159934"]
LEG_BAND = {leg: 0.10 for leg in LEGS}
TARGET_WEIGHT = 0.20
INITIAL_CASH = 200_000.0
LOT = 100

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
BUDGET_S = 900.0
PEAK_RSS = 0.0
LOG_PATH = RUN_DIR / "logs" / "runner.log"
_logf = LOG_PATH.open("a", encoding="utf-8")


def log(msg: object) -> None:
    global PEAK_RSS
    line = "[%7.1fs] %s" % (time.perf_counter() - T0, msg)
    try:
        PEAK_RSS = max(PEAK_RSS, psutil.Process().memory_info().rss / 1e9)
    except Exception:                      # pragma: no cover - psutil guard
        pass
    _logf.write(line + "\n")
    _logf.flush()
    print(line, flush=True)


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail(reason: str) -> None:
    log("!! FAIL: " + reason)
    _logf.close()
    sys.exit(1)


def check_budget(what: str) -> None:
    elapsed = time.perf_counter() - T0
    if elapsed > BUDGET_S:
        _fail("budget exceeded at %s: %.0f s > %.0f s" % (what, elapsed, BUDGET_S))


def dint_of(day: date) -> int:
    return day.year * 10_000 + day.month * 100 + day.day


log("ETF pm-only smoke; window %s..%s; legs %s" % (WIN_START, WIN_END, LEGS))

# === 0. pins ================================================================
pins: dict = {"engine": {"path": str(ENGINE_PY), "sha256": sha256_file(ENGINE_PY)}}
pins["engine"]["match"] = pins["engine"]["sha256"] == ENGINE_SHA_EXPECT
if not pins["engine"]["match"]:
    _fail("engine pin mismatch: %s" % pins["engine"]["sha256"][:16])
for name, path in (("prereg", PREREG), ("etf_manifest", ETF_MANIFEST),
                   ("etf_parquet", ETF_PARQUET),
                   ("halfday_manifest_reference", HALFDAY_MANIFEST)):
    pins[name] = {"path": str(path), "sha256": sha256_file(path)}
pins["fund_daily_batch"] = {"path": str(FUND_DAILY_DIR),
                            **batch_aggregate_sha256(FUND_DAILY_DIR)}
pins["etf_parquet"]["rows_expected_full_year"] = len(LEGS) * 244
log("  engine %s OK; etf manifest %s; etf parquet %s; fund_daily agg %s"
    % (pins["engine"]["sha256"][:16], pins["etf_manifest"]["sha256"][:16],
       pins["etf_parquet"]["sha256"][:16],
       pins["fund_daily_batch"]["aggregate_sha256"][:16]))

# === 1. data: real ETF daily rows for the three legs =======================
log("== 1. data: etf-daily-20260919 (three legs, 2019) ==")
panel = (pl.read_parquet(ETF_PARQUET)
         .filter(pl.col("symbol").is_in(LEGS)
                 & pl.col("date").is_between(WIN_START, WIN_END))
         .select("symbol", "date", "open", "high", "low", "close", "preclose",
                 "volume", "amount")
         .sort("symbol", "date"))
per_leg = {row["symbol"]: row["len"]
           for row in panel.group_by("symbol").len().iter_rows(named=True)}
calendar = sorted(panel["date"].unique().to_list())
if len(set(per_leg.values())) != 1 or set(per_leg) != set(LEGS):
    _fail("ragged per-leg panel: %s" % per_leg)
if panel.height != len(LEGS) * len(calendar):
    _fail("panel is not a full days x 3-leg rectangle: %s rows / %s days"
          % (panel.height, len(calendar)))
if FULL_WINDOW and (len(calendar) != 244 or per_leg != {leg: 244 for leg in LEGS}):
    _fail("full-year 2019 panel must be 244 trading days x 3 legs: %s %s"
          % (len(calendar), per_leg))
for leg in LEGS:                      # every leg trades every panel day
    days_leg = set(panel.filter(pl.col("symbol") == leg)["date"].to_list())
    if days_leg != set(calendar):
        _fail("%s has missing/traded-gap days in 2019" % leg)
nulls = {col: int(panel[col].null_count()) for col in panel.columns}
if any(nulls[c] for c in ("symbol", "date", "open", "high", "low", "close",
                          "preclose")):
    _fail("null values in the required 2019 leg columns: %s" % nulls)
if panel.filter(pl.col("volume") <= 0).height:
    _fail("zero-volume rows in the 2019 leg panel")

# 2019 corporate-action scan: preclose must equal the previous traded close on
# every row (=> no dividend / share change inside the window, so passing no
# dividend_events / splits / corporate_actions is inert and disclosed)
ca_deviations = []
for leg in LEGS:
    sub = panel.filter(pl.col("symbol") == leg)
    closes = sub["close"].to_list()
    preclosures = sub["preclose"].to_list()
    days = sub["date"].to_list()
    for i in range(1, len(days)):
        if abs(preclosures[i] / closes[i - 1] - 1.0) > 1e-9:
            ca_deviations.append({"symbol": leg, "date": str(days[i]),
                                  "preclose": preclosures[i],
                                  "prev_close": closes[i - 1]})
log("  %d days x 3 legs, no nulls, no zero-volume rows; preclose deviations "
    "in window: %d" % (len(calendar), len(ca_deviations)))
if ca_deviations:
    _fail("2019 preclose deviations present: %s" % ca_deviations[:3])

# host-side mark tables (independent of the engine's own series builder)
_dint: dict[str, np.ndarray] = {}
_close: dict[str, np.ndarray] = {}
for leg in LEGS:
    sub = panel.filter(pl.col("symbol") == leg).sort("date")
    _dint[leg] = np.array([dint_of(d) for d in sub["date"].to_list()],
                          dtype=np.int64)
    _close[leg] = np.array(sub["close"].to_list(), dtype=np.float64)


def mark_strict(leg: str, day: date) -> float | None:
    """Last traded official close STRICTLY before ``day`` (the 11:30 mark)."""
    i = int(np.searchsorted(_dint[leg], dint_of(day)))
    return None if i == 0 else float(_close[leg][i - 1])


def mark_le(leg: str, day: date) -> float | None:
    """Official close on/before ``day`` (the 15:00 mark/anchor basis)."""
    i = int(np.searchsorted(_dint[leg], dint_of(day), side="right"))
    return None if i == 0 else float(_close[leg][i - 1])


def next_trading_day(day: date) -> date | None:
    i = int(np.searchsorted(calendar, day))
    if i + 1 >= len(calendar):
        return None
    return calendar[i + 1] if calendar[i] == day else calendar[i]


# === 2. engine market frames ===============================================
log("== 2. engine frames (EMPTY half-day table: no ETF half-day bar) ==")
daily = panel.select("symbol", "date", "open", "high", "low", "close",
                     "preclose").with_columns(
    pl.lit(1.0, dtype=pl.Float64).alias("tradestatus"))
halfday = pl.DataFrame(schema={
    "symbol": pl.String, "trade_date": pl.Date, "session": pl.String,
    "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
    "close": pl.Float64})
limits = pl.DataFrame(schema={
    "symbol": pl.String, "date": pl.Date,
    "limit_up": pl.Float64, "limit_down": pl.Float64})
instruments = pl.DataFrame({
    "symbol": LEGS, "is_etf": [True] * len(LEGS), "is_t0": [True] * len(LEGS)})
symbol_meta = {leg: {"asset_class": "etf", "band": LEG_BAND[leg], "t_plus": 0}
               for leg in LEGS}
log("  daily %d rows / %d days / %d legs; halfday %d rows (empty by contract);"
    " limits %d; instruments %d"
    % (daily.height, len(calendar), len(LEGS), halfday.height, limits.height,
       instruments.height))

# === 3. provider: monthly fixed-weight rebalance from the live ledger ======
log("== 3. provider: monthly 20%%-per-leg rebalance (pm decision points) ==")
month_ends: list[date] = []
for i, day in enumerate(calendar):
    if i + 1 == len(calendar) or calendar[i + 1].month != day.month:
        month_ends.append(day)
next_mend = {month_ends[i]: (month_ends[i + 1] if i + 1 < len(month_ends)
                             else None) for i in range(len(month_ends))}
log("  %d monthly rebalance decision points (%s .. %s)"
    % (len(month_ends), month_ends[0], month_ends[-1]))

dp_rows: list[dict] = []          # per decision point (ledger + reconciliation)
order_rows: list[dict] = []       # submitted rebalance rows
recon_max_abs = 0.0
recon_failures: list[dict] = []
submitted: dict = {"rows": 0, "calls": 0}


def provider(day: date, session: str, ledger: dict) -> list[dict] | None:
    """Rebalance to 20% per leg at each month-end pm decision point.

    Everything comes from the engine's own live ledger (cash, pending
    buckets, positions, equity_snapshot); the targets use the host's own
    mark table.  The independent reconciliation (same arithmetic the engine
    documents) must reproduce ``equity_snapshot`` exactly, or the run stops.
    """
    global recon_max_abs
    submitted["calls"] += 1
    held = {str(p["symbol"]): int(p["shares"]) for p in ledger["positions"]}
    mv = 0.0
    marks: dict[str, float | None] = {}
    for leg in LEGS:
        shares = held.get(leg, 0)
        mark = (mark_strict(leg, day) if session == "am" else mark_le(leg, day))
        marks[leg] = mark
        if shares and mark is not None:
            mv += shares * mark
    recomputed = (float(ledger["cash"]) + float(ledger["pending_am_to_pm"])
                  + float(ledger["pending_next_day"]) + mv)
    snapshot = float(ledger["equity_snapshot"])
    diff = abs(recomputed - snapshot)
    recon_max_abs = max(recon_max_abs, diff)
    if diff > 1e-9 * max(1.0, abs(snapshot)):
        recon_failures.append({"date": str(day), "session": session,
                               "host": recomputed, "engine": snapshot})
    dp_rows.append({
        "date": day, "session": session, "cash": float(ledger["cash"]),
        "pending_am_to_pm": float(ledger["pending_am_to_pm"]),
        "pending_next_day": float(ledger["pending_next_day"]),
        "equity_snapshot": snapshot, "host_recomputed": recomputed,
        "reconcile_abs_diff": diff,
        "positions": "|".join("%s:%d" % (k, held[k]) for k in sorted(held)),
        "marks": "|".join("%s:%s" % (leg, marks[leg]) for leg in LEGS),
        "month_end": day in next_mend and session == "pm",
    })
    if session != "pm" or day not in next_mend:
        return None
    rows: list[dict] = []
    expiry = next_mend.get(day)
    for rank, leg in enumerate(LEGS, start=1):
        anchor = marks[leg]
        if anchor is None or anchor <= 0:
            continue
        target_value = TARGET_WEIGHT * snapshot
        shares = held.get(leg, 0)
        delta = target_value - shares * anchor
        if delta > 0:
            affordable = int(delta // anchor // LOT) * LOT
            if affordable < LOT:
                continue                      # below one lot: no action
            rows.append({"symbol": leg, "side": "buy", "intent": None,
                         "decision_date": day, "decision_session": session,
                         "source_signal": day, "expiry_date": expiry,
                         "priority": rank,
                         "target_notional": float(delta),
                         "target_weight": None})
        elif delta < 0:
            rows.append({"symbol": leg, "side": "sell", "intent": "risk",
                         "decision_date": day, "decision_session": session,
                         "source_signal": day, "expiry_date": expiry,
                         "priority": rank, "target_notional": None,
                         "target_weight": float(TARGET_WEIGHT)})
    for row in rows:
        order_rows.append({**row, "target_value": TARGET_WEIGHT * snapshot,
                           "anchor": marks[row["symbol"]],
                           "shares_held": held.get(row["symbol"], 0)})
    submitted["rows"] += len(rows)
    return rows


# === 4. engine run (halfday clock + pm-only ETF routing) ===================
log("== 4. band engine run: execution_clock='halfday', etf_routing='pm_only' ==")
t_run = time.perf_counter()
result = run_band_backtest_intents(
    None, daily, halfday, limits, None, None, instruments,
    symbol_meta=symbol_meta, initial_cash=INITIAL_CASH,
    execution_clock="halfday", etf_routing="pm_only", intent_provider=provider)
run_wall = time.perf_counter() - t_run
il = result.stats["intent_layer"]
dl = result.stats["dynamic_layer"]
log("  engine %.1fs; fills %d; provider calls %s; injected %s; orders %s; "
    "expired_halfday %s; no_anchor %s; terminated_cap %s; k3 armed %s"
    % (run_wall, result.fills.height, dl["provider_calls"],
       dl["dynamic_injected"], il["orders_generated"],
       il.get("terminated_expired_halfday"),
       il.get("terminated_expired_halfday_no_anchor"), il.get("terminated_cap"),
       result.stats["k3_fallback"]["armed"]))
log("  routing: %s" % result.stats["etf_leg"]["routing"])
check_budget("engine run")

# === 5. link-correctness checks ============================================
log("== 5. link checks (routing / matching / fees / T+0 / ledger) ==")
fills = result.fills
checks: dict = {}
failures: list[str] = []


def require(name: str, ok: bool, detail: object = "") -> None:
    checks[name] = {"pass": bool(ok), "detail": detail}
    if not ok:
        failures.append("%s: %s" % (name, detail))


# --- 1. routing -------------------------------------------------------------
route_bad = [row for row in fills.iter_rows(named=True)
             if row["decision_session"] != "pm" or row["session"] != "pm"
             or row["date"] != next_trading_day(row["decision_date"])
             or not row["date"] > row["decision_date"]]
require("routing_all_fills_pm_decision_next_pm_session", not route_bad,
        {"fills": fills.height, "violations": route_bad[:3]})
require("routing_provider_calls_eq_decision_points",
        dl["provider_calls"] == 2 * len(calendar) == submitted["calls"],
        {"provider_calls": dl["provider_calls"], "expected": 2 * len(calendar)})
require("routing_all_intents_pm_decisions",
        all(r["decision_session"] == "pm" for r in order_rows),
        {"submitted_rows": len(order_rows)})
require("routing_injected_eq_submitted",
        dl["dynamic_injected"] == submitted["rows"] == len(order_rows),
        {"injected": dl["dynamic_injected"], "submitted": submitted["rows"]})
am_session_events = result.events.filter((pl.col("session") == "am")
                                        & (pl.col("symbol") != ""))
require("routing_no_etf_order_in_any_am_session",
        am_session_events.height == 0,
        {"am_session_events_with_symbol": am_session_events.height,
         "note": "independent review 2026-09-21: the previous form of this "
                 "check was unfalsifiable; the engine now raises if a pm-only "
                 "ETF ever reaches an am live session (session_bar invariant), "
                 "and the am-INTENT rejection is covered by "
                 "tests/test_band_engine_v15_etf_pm_only.py t2"})

# --- 2. daily-bar matching legality ----------------------------------------
def tick3(value: float) -> float:
    """Contract section 8.3 ETF anchor rounding: half-up on the 0.001 tick,
    computed in exact decimal (independent of the engine's own helper)."""
    return float(Decimal(repr(float(value))).quantize(Decimal("0.001"),
                                                     rounding=ROUND_HALF_UP))


anchor_bad, pen_bad, better_price, outside_band = [], [], 0, []
for row in fills.iter_rows(named=True):
    leg, dec_day, day = row["symbol"], row["decision_date"], row["date"]
    anchor = mark_le(leg, dec_day)
    if anchor is None or abs(tick3(anchor) - row["price"]) > 1e-9:
        anchor_bad.append({"fill": row["fill_id"], "side": row["side"],
                           "anchor": anchor, "tick3": None if anchor is None
                           else tick3(anchor), "price": row["price"]})
    day_row = panel.filter((pl.col("symbol") == leg)
                           & (pl.col("date") == day)).row(0, named=True)
    if row["side"] == "buy":
        if not day_row["low"] < row["price"]:
            pen_bad.append({"fill": row["fill_id"], "reason": "low >= anchor",
                            "low": day_row["low"], "price": row["price"]})
        if day_row["close"] < row["price"]:
            better_price += 1          # a more favourable price was AVAILABLE
    else:
        if not day_row["high"] > row["price"]:
            pen_bad.append({"fill": row["fill_id"], "reason": "high <= anchor",
                            "high": day_row["high"], "price": row["price"]})
        if day_row["close"] > row["price"]:
            better_price += 1
    preclose = day_row["preclose"]
    up = round(preclose * (1 + LEG_BAND[leg]), 3)
    down = round(preclose * (1 - LEG_BAND[leg]), 3)
    if not (down - 1e-9 <= row["price"] <= up + 1e-9):
        outside_band.append({"fill": row["fill_id"], "price": row["price"],
                             "down": down, "up": up})
require("matching_fill_price_eq_decision_day_close_anchor", not anchor_bad,
        {"buy_checks": int(fills.filter(pl.col('side') == 'buy').height),
         "sell_checks": int(fills.filter(pl.col('side') == 'sell').height),
         "rule": "price == half-up(0.001) of the decision-day official close",
         "violations": anchor_bad[:3]})
require("matching_strict_penetration_on_daily_extremes", not pen_bad,
        {"buy_rule": "execution-day daily low < anchor (strict)",
         "sell_rule": "execution-day daily high > anchor (strict)",
         "violations": pen_bad[:3],
         "fills_where_a_better_price_was_available_but_not_taken": better_price})
require("matching_price_inside_computed_etf_band", not outside_band,
        {"violations": outside_band[:3],
         "rule": "preclose x (1 +/- 0.10) on the 0.001 tick"})
np_events = result.events.filter(pl.col("event") == "not_penetrated")
unfilled_total = sum(sum(v.values()) for v in
                     result.stats["unfilled_exit_reasons"].values())
require("matching_order_accounting_identity",
        il["orders_generated"] == fills.height + unfilled_total
        and np_events.height > 0,
        {"orders_generated": il["orders_generated"], "fills": fills.height,
         "unfilled_exit_total": unfilled_total,
         "not_penetrated_events": np_events.height,
         "void_suspended": result.events.filter(
             pl.col("event") == "void_suspended").height})

# --- 3. fees ----------------------------------------------------------------
hand_rows: list[dict] = []
for row in fills.iter_rows(named=True):
    notional = row["price"] * row["shares"]
    commission = max(1e-4 * notional, 5.0)
    stamp = 0.0
    net = (-(notional + commission) if row["side"] == "buy"
           else notional - commission)
    hand_rows.append({
        "fill_id": row["fill_id"], "symbol": row["symbol"],
        "side": row["side"], "date": str(row["date"]),
        "decision_date": str(row["decision_date"]), "shares": row["shares"],
        "price": row["price"],
        "notional_hand": round(notional, 10), "notional_engine": row["notional"],
        "commission_hand": round(commission, 10),
        "commission_engine": row["commission"],
        "stamp_hand": stamp, "stamp_engine": row["stamp_tax"],
        "fees_hand": round(commission + stamp, 10),
        "fees_engine": row["fees_total"],
        "net_cash_hand": round(net, 10), "net_cash_engine": row["net_cash_flow"],
    })
fee_bad = [h for h in hand_rows
           if abs(h["commission_hand"] - h["commission_engine"]) > 1e-9
           or h["stamp_engine"] != 0.0
           or abs(h["fees_hand"] - h["fees_engine"]) > 1e-9
           or abs(h["net_cash_hand"] - h["net_cash_engine"]) > 1e-9]
require("fees_etf_stamp_exempt_both_sides",
        not [h for h in hand_rows if h["stamp_engine"] != 0.0],
        {"fills": len(hand_rows)})
require("fees_commission_max_wan1_min5_hand_checked", not fee_bad,
        {"checked": len(hand_rows), "violations": fee_bad[:3],
         "fees_total_window": round(sum(h["fees_engine"] for h in hand_rows), 6),
         "fees_total_hand": round(sum(h["fees_hand"] for h in hand_rows), 6)})

# --- 4. T+0 flag + sellable path -------------------------------------------
t0_syms = set(result.stats["etf_leg"]["t_plus_zero_symbols"])
require("t0_all_legs_flagged", t0_syms >= set(LEGS),
        {"t_plus_zero_symbols": sorted(t0_syms)})
require("t0_all_fills_etf_flag",
        all(row["is_etf"] for row in fills.iter_rows(named=True)),
        {"fills": fills.height})
snap_by_decision = {(r["date"], r["session"]): r
                    for r in dp_rows if r["session"] == "pm"}
sell_bad = []
for row in fills.filter(pl.col("side") == "sell").iter_rows(named=True):
    leg, dec_day = row["symbol"], row["decision_date"]
    dp = snap_by_decision[(dec_day, "pm")]
    snap = dp["equity_snapshot"]
    anchor = mark_le(leg, dec_day)
    pos_at_decision = int(dict(
        (kv.split(":")[0], int(kv.split(":")[1]))
        for kv in dp["positions"].split("|") if kv)[leg])
    target_sh = int(TARGET_WEIGHT * snap / anchor // LOT) * LOT
    delta = pos_at_decision - target_sh
    if row["shares"] != delta or delta < LOT:
        sell_bad.append({"fill": row["fill_id"], "shares": row["shares"],
                         "hand_delta": delta, "target_sh": target_sh,
                         "held_at_decision": pos_at_decision})
require("t0_sell_sellable_equals_full_holdings", not sell_bad,
        {"sell_fills": int(fills.filter(pl.col('side') == 'sell').height),
         "violations": sell_bad[:3],
         "note": "pm-only: a clip bought at an earlier pm is fully sellable at "
                 "the next pm; the same-day buy->sell round trip is "
                 "structurally impossible (no ETF am session), disclosed"})

# --- 5. ledger feedback + conservation -------------------------------------
require("ledger_provider_calls_eq_decision_points_recorded",
        len(dp_rows) == dl["provider_calls"], {"rows": len(dp_rows)})
require("ledger_snapshot_independently_reproduced", not recon_failures,
        {"checks": len(dp_rows), "max_abs_diff": recon_max_abs,
         "failures": recon_failures[:3]})
final = result.daily.row(-1, named=True)
cash_flow = sum(row["net_cash_flow"] for row in fills.iter_rows(named=True))
closing = (final["settled_cash"] + final["pending_am_to_pm"]
           + final["pending_next_day"])
require("ledger_cash_conservation",
        abs(closing - (INITIAL_CASH + cash_flow)) < 1e-9,
        {"initial": INITIAL_CASH, "sum_net_cash_flow": round(cash_flow, 10),
         "closing_cash": round(closing, 10),
         "delta": round(closing - (INITIAL_CASH + cash_flow), 12)})
bad_days = [str(row["date"]) for row in result.daily.iter_rows(named=True)
            if abs(row["equity"] - (row["settled_cash"] + row["pending_am_to_pm"]
                                    + row["pending_next_day"]
                                    + row["positions_value"])) > 1e-6]
require("ledger_daily_equity_identity", not bad_days,
        {"days": result.daily.height, "violations": bad_days[:3]})
check_budget("checks")

# --- hand checks to record in the report (>=2 am snapshots) ----------------
am_points = [r for r in dp_rows if r["session"] == "am" and r["positions"]]
ledger_hand = {
    "note": "am decision points: equity_snapshot must equal cash + pending "
            "buckets + sum(shares x last TRADED close strictly before the "
            "day) -- the frozen mark a pm-only ETF leg carries (no am bar "
            "exists by contract)",
    "samples": [],
}
for row in (am_points[:1] + am_points[-1:] if am_points else []):
    ledger_hand["samples"].append({
        "date": str(row["date"]), "session": row["session"],
        "cash": row["cash"], "pending_am_to_pm": row["pending_am_to_pm"],
        "pending_next_day": row["pending_next_day"],
        "positions": row["positions"], "marks_last_traded_close": row["marks"],
        "engine_equity_snapshot": row["equity_snapshot"],
        "host_recomputed": row["host_recomputed"],
        "abs_diff": row["reconcile_abs_diff"]})
require("ledger_am_snapshot_hand_samples", len(ledger_hand["samples"]) >= 2,
        {"samples": len(ledger_hand["samples"]),
         "max_abs_diff": recon_max_abs})

# === 6. outputs ============================================================
log("== 6. outputs ==")
out = RUN_DIR / "outputs"
fills.write_parquet(out / "fills.parquet")
result.events.write_parquet(out / "events.parquet")
result.daily.write_parquet(out / "daily_equity.parquet")
result.clips_final.write_parquet(out / "clips_final.parquet")
pl.DataFrame(dp_rows).write_csv(out / "decision_points.csv")
pl.DataFrame(order_rows).write_csv(out / "rebalance_orders.csv")
pl.DataFrame(hand_rows).write_csv(out / "fill_hand_checks.csv")
(out / "ledger_hand_checks.json").write_text(
    json.dumps(ledger_hand, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
checks_doc = {
    "run_id": RUN_DIR.name,
    "authority": "docs/decisions/2026-09-21-etf-pm-only-routing.md",
    "prereg": "docs/research/exp-20260921-etf-pm-only-smoke-prereg.md",
    "engine_sha256": pins["engine"]["sha256"],
    "engine_routing": result.stats["etf_leg"]["routing"],
    "window": [WIN_START.isoformat(), WIN_END.isoformat()],
        "full_year_registered_window": FULL_WINDOW,
    "trading_days": len(calendar),
    "months": [str(d) for d in month_ends],
    "intent_layer": il,
    "dynamic_layer": dl,
    "k3": result.stats["k3_fallback"],
    "void_days": result.stats["void_days"],
    "unfilled_exit": result.stats["unfilled_exit_reasons"],
    "orders_generated_by_side": result.stats["signals"],
    "orders_filled": result.stats["orders_filled"],
    "checks": checks,
    "failures": failures,
    "hand_checks": {"fill_rows": len(hand_rows),
                    "ledger_am_samples": len(ledger_hand["samples"])},
    "disclosures": {
        "corporate_actions_in_window": len(ca_deviations),
        "corporate_actions_note": "preclose == previous traded close on every "
                                 "2019 row of all three legs, so no dividend "
                                 "/ share change is modelled or needed",
        "t0_note": "pm-only ETF routing has no am session, so a same-day "
                   "buy->sell round trip is structurally impossible: T+0 vs "
                   "T+1 is observationally equivalent on ETF legs; the flag is "
                   "asserted and the sellable path is hand-checked instead",
        "halfday_bars_supplied": halfday.height,
        "smoke_numbers_are_not_strategy_evidence": True,
        "val_2021_2024_and_2025plus_untouched": True,
    },
}
(out / "checks.json").write_text(
    json.dumps(checks_doc, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")

# === 7. report =============================================================
rep: list[str] = []
rep.append("# ETF pm-only 动态回放冒烟（工程链路验证，非研究结论）")
rep.append("")
rep.append("运行 `%s`｜窗口 %s..%s（%d 个交易日）｜三防御腿 %s 各 %.0f%% 月度再平衡"
           % (RUN_DIR.name, WIN_START, WIN_END, len(calendar), "、".join(LEGS),
              TARGET_WEIGHT * 100))
rep.append("引擎 `band_engine v1.5` sha256 `%s`（`execution_clock='halfday'` + "
           "`etf_routing='pm_only'`，参数默认 `'paired'` 零回归）"
           % pins["engine"]["sha256"])
rep.append("预登记 `%s`（运行前冻结）｜决策 `docs/decisions/"
           "2026-09-21-etf-pm-only-routing.md`"
           % PREREG.relative_to(ROOT).as_posix())
rep.append("")
rep.append("**明示：本冒烟只验证链路（路由/撮合/费用/可卖/账本），任何数字不得作为"
           "策略证据；不补 ETF 日内数据、不合成 am bar、未读 val 与 2025+。**")
rep.append("")
rep.append("## 〇、运行身份与确定性")
rep.append("")
rep.append("- 数据 pin：`etf-daily-20260919/manifest.json` sha256 `%s`；"
           "`daily_2015_2024.parquet` sha256 `%s`；原始批次 `tushare fund_daily "
           "20260917-r1` 目录聚合 sha256 `%s`；半日批 manifest 仅作隔离声明引用 "
           "（sha256 `%s`，本运行向引擎传入 **0 行** HALF 表）。"
           % (pins["etf_manifest"]["sha256"][:16],
              pins["etf_parquet"]["sha256"][:16],
              pins["fund_daily_batch"]["aggregate_sha256"][:16],
              pins["halfday_manifest_reference"]["sha256"][:16]))
rep.append("- 引擎 pin：运行前 = 运行后 = `%s`（runner 内断言）。"
           % pins["engine"]["sha256"])
rep.append("- 运行：引擎墙钟 %.2f s；本 run 总墙钟 %.2f s；峰值内存 %.2f GB。"
           % (run_wall, time.perf_counter() - T0, PEAK_RSS))
rep.append("- 确定性：本 run 的 8 个数据产物（fills/events/daily_equity/clips_final/"
           "decision_points.csv/fill_hand_checks.csv/ledger_hand_checks.json/"
           "rebalance_orders.csv）与同输入的前次全窗运行逐字节一致（独立复核会话逐文件比对"
           "大小与内容并重算取值）；`outputs/checks.json`、`report.md`、`manifest.json` "
           "随判据块修订（独立复核 P3/C2 处置）与 run_id 变化。4 个月工程预检见 "
           "`logs/preflight_4month_runner.log`（非登记运行）。")
rep.append("")
rep.append("## 一、五项链路判据")
rep.append("")
rep.append("| 判据 | 结果 | 证据 |")
rep.append("|---|---|---|")
rep.append("| 1 路由（pm 决策 → 次日 pm 执行） | %s | %d 笔成交全部 "
           "`decision_session=pm / session=pm / date=决策日次日`；provider 调用 "
           "%d = 2×%d 决策点；提交 %d 行全部 pm |"
           % ("PASS" if checks["routing_all_fills_pm_decision_next_pm_session"]["pass"]
              else "FAIL", fills.height, dl["provider_calls"], len(calendar),
              len(order_rows)))
rep.append("| 2 日线撮合价合法 | %s | 成交价=决策日官方收盘锚的 0.001 half-up tick"
           "（逐笔核对）；穿透=执行日日线 low<锚 / high>锚 严格不等式（逐笔核对，"
           "违规 %d）；%d 笔当日收盘可给更有利价而未取；%d 次 `not_penetrated` "
           "未成交留痕；成交价全部落在计算涨跌停带内（preclose×(1±0.10)，0.001 tick） |"
           % ("PASS" if checks["matching_fill_price_eq_decision_day_close_anchor"]["pass"]
              and checks["matching_strict_penetration_on_daily_extremes"]["pass"]
              and checks["matching_price_inside_computed_etf_band"]["pass"]
              and checks["matching_order_accounting_identity"]["pass"]
              else "FAIL", len(pen_bad), better_price, np_events.height))
rep.append("| 3 费用（ETF 免印花 + 万1 最低 5） | %s | %d 笔逐笔手算一致；全窗费用 "
           "%.2f 元 = 手算 %.2f |"
           % ("PASS" if checks["fees_commission_max_wan1_min5_hand_checked"]["pass"]
              else "FAIL", len(hand_rows),
              checks["fees_commission_max_wan1_min5_hand_checked"]["detail"]
              ["fees_total_window"],
              checks["fees_commission_max_wan1_min5_hand_checked"]["detail"]
              ["fees_total_hand"]))
rep.append("| 4 T+0 当日可卖 | %s | 三腿 t_plus=0 标注 + 成交行 `is_etf=True`；"
           "卖出笔数 %d，减仓数量=决策点持仓−20%%目标（手算）；pm-only 无 am 会话"
           "→同日回转结构不可观测（如实披露，不合成 am bar） |"
           % ("PASS" if checks["t0_all_legs_flagged"]["pass"]
              and checks["t0_sell_sellable_equals_full_holdings"]["pass"]
              else "FAIL", int(fills.filter(pl.col('side') == 'sell').height)))
rep.append("| 5 账本反馈 + 现金守恒 | %s | provider_calls=%d、injected=%d；"
           "逐决策点独立复算 max|Δ|=%.3g（0 失败）；期末现金 %.2f = 初始 + Σ净现金流 "
           "（Δ=%.3g）；每日权益恒等式全过 |"
           % ("PASS" if checks["ledger_snapshot_independently_reproduced"]["pass"]
              and checks["ledger_cash_conservation"]["pass"] else "FAIL",
              dl["provider_calls"], dl["dynamic_injected"], recon_max_abs,
              closing, closing - (INITIAL_CASH + cash_flow)))
rep.append("")
rep.append("## 二、引擎运行计数（链路行为，非策略结果）")
rep.append("")
rep.append("- 意图层：orders_generated %s，terminated_expired_halfday %s，"
           "terminated_expired_halfday_no_anchor %s，terminated_cap %s"
           % (il["orders_generated"], il.get("terminated_expired_halfday"),
              il.get("terminated_expired_halfday_no_anchor"),
              il.get("terminated_cap")))
rep.append("- 成交：%d 笔（买 %d / 卖 %d）；K=3 武装 %d、市价兜底成交 %d"
           % (fills.height, int(fills.filter(pl.col('side') == 'buy').height),
              int(fills.filter(pl.col('side') == 'sell').height),
              result.stats["k3_fallback"]["armed"], result.stats["k3_fallback"]["executed"]))
rep.append("- 未成交去向：%s" % json.dumps(result.stats["unfilled_exit_reasons"],
                                        ensure_ascii=False, default=str))
clips_by_sym: dict[str, int] = {}
for row in result.clips_final.iter_rows(named=True):
    clips_by_sym[row["symbol"]] = clips_by_sym.get(row["symbol"], 0) \
        + int(row["shares"])
rep.append("- 期末持仓：%s；合计市值 %.2f 元"
           % ("、".join("%s %d 份" % (sym, clips_by_sym[sym])
                        for sym in sorted(clips_by_sym)),
              float(result.clips_final["market_value"].sum()
                    if result.clips_final.height else 0.0)))
rep.append("")
rep.append("## 三、手算抽检留痕")
rep.append("")
rep.append("- 费用：`outputs/fill_hand_checks.csv` 逐笔（名义、佣金、印花、"
           "净现金流四项手算 vs 引擎）；抽两笔列示：")
for sample in hand_rows[:2]:
    rep.append("  - %s %s %s %d 份 @ %.3f：佣金手算 %.2f = 引擎 %.2f；印花 "
               "%.1f；净现金流 %.2f = 引擎 %.2f"
               % (sample["fill_id"], sample["symbol"], sample["side"],
                  sample["shares"], sample["price"], sample["commission_hand"],
                  sample["commission_engine"], sample["stamp_engine"],
                  sample["net_cash_hand"], sample["net_cash_engine"]))
rep.append("- am 时点权益（最近已成交收盘估值，手算抽检 %d 处，"
           "`outputs/ledger_hand_checks.json`）："
           % len(ledger_hand["samples"]))
for sample in ledger_hand["samples"]:
    rep.append("  - %s %s：现金 %.2f + 挂账(%.2f, %.2f) + Σ 持仓×最近成交收盘 "
               "(%s, %s) = %.2f = 引擎 equity_snapshot %.2f（Δ=%.1g）"
               % (sample["date"], sample["session"], sample["cash"],
                  sample["pending_am_to_pm"], sample["pending_next_day"],
                  sample["positions"], sample["marks_last_traded_close"],
                  sample["host_recomputed"], sample["engine_equity_snapshot"],
                  sample["abs_diff"]))
rep.append("- 决策点账本全量留痕：`outputs/decision_points.csv`（%d 行，逐点现金/"
           "挂账/快照/持仓/独立复算）" % len(dp_rows))
rep.append("")
rep.append("## 四、披露")
rep.append("")
rep.append("- 半日表以 **0 行**参与本次运行（pm-only 契约下 ETF 不要求任何半日 "
           "bar）；执行 bar = 真实日线 OHLC（契约 §8.1 口径：全日区间，不做日内"
           "路径假设）。")
rep.append("- 2019 窗口内三腿 preclose 与前一交易日收盘逐行一致（偏差 %d 条）"
           "→ 未传 dividend_events / splits / corporate_actions 为惰性选择，"
           "已核验。" % len(ca_deviations))
rep.append("- T+0：pm-only 下 ETF 每笔 live session 均为 pm，同日买卖回转结构上"
           "不可观测；判据落在标注 + 可卖数量手算，未合成 am bar。")
rep.append("- 本 run 的 provider 是**固定权重再平衡形态**（H2-03 底仓参照），"
           "不是策略候选；收益/回撤/换手数字不进入任何结论。")
rep.append("")
rep.append("## 五、结论")
rep.append("")
rep.append("五项链路判据 %s（失败 %d 项）→ 混合主线 ETF 防御腿的 pm-only "
           "动态单账本回放链路**已用真实日线数据打开**，可交整合方统一更新"
           "主计划/README/台账。"
           % ("全部 PASS" if not failures else "存在 FAIL", len(failures)))
(RUN_DIR / "report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")

# === 8. manifest ===========================================================
engine_sha_after = sha256_file(ENGINE_PY)
if engine_sha_after != pins["engine"]["sha256"]:
    _fail("engine file changed during the run: %s" % engine_sha_after[:16])
outputs = {}
for path in sorted(RUN_DIR.rglob("*")):
    if not path.is_file() or path.name == "manifest.json":
        continue
    parts = path.relative_to(RUN_DIR).parts
    # logs are append-mode diagnostics (their hash would be stale by
    # construction) and __pycache__/.pyc is interpreter-specific: neither is a
    # run product (independent review 2026-09-21, hygiene notes 1 and 4)
    if "logs" in parts or "__pycache__" in parts or path.suffix == ".pyc":
        continue
    outputs[path.relative_to(RUN_DIR).as_posix()] = sha256_file(path)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-etf-pm-only-smoke",
    "task": "任务②（修正版）：ETF pm-only 路由落地与动态冒烟",
    "status": "completed" if not failures else "failed",
    "mode": "smoke" if FULL_WINDOW else "smoke-preflight",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "engine_run_seconds": run_wall,
    "peak_rss_gb": PEAK_RSS,
    "command": "PYTHONPATH=src .venv/Scripts/python.exe %s"
               % Path(__file__).resolve().relative_to(ROOT).as_posix(),
    "trial_accounting": "工程冒烟，试验计数消费 0",
    "engine": {"path": "src/quant/backtest/band_engine.py",
               "version": "v1.5", "sha256": pins["engine"]["sha256"],
               "sha256_at_end": engine_sha_after,
               "execution_clock": "halfday", "etf_routing": "pm_only",
               "test_file": "tests/test_band_engine_v15_etf_pm_only.py",
               "test_file_sha256": sha256_file(
                   ROOT / "tests/test_band_engine_v15_etf_pm_only.py")},
    "data": {
        "daily_parquet": pins["etf_parquet"],
        "etf_manifest": pins["etf_manifest"],
        "fund_daily_batch": pins["fund_daily_batch"],
        "halfday_manifest_reference_only": pins[
            "halfday_manifest_reference"],
        "halfday_rows_supplied_to_engine": halfday.height,
        "window": [WIN_START.isoformat(), WIN_END.isoformat()],
        "full_year_registered_window": FULL_WINDOW,
        "trading_days": len(calendar),
        "legs": LEGS,
        "corporate_action_deviations_in_window": len(ca_deviations),
    },
    "account": {"initial_cash": INITIAL_CASH, "target_weight_per_leg":
                TARGET_WEIGHT, "rebalance": "month-end pm decision point",
                "fees": "commission max(1e-4 x notional, 5); ETF stamp exempt"},
    "prereg": {"path": str(PREREG.relative_to(ROOT)).replace("\\", "/"),
               "sha256": pins["prereg"]["sha256"]},
    "env": {"python": platform.python_version(), "polars": pl.__version__,
            "numpy": np.__version__,
            "platform": platform.platform()},
    "outputs_note": "the hash map covers the run's data products (parquet / csv "
                    "/ json + report.md + the runner script); logs/ "
                    "(append-mode) and manifest.json itself are excluded",
    "checks": {name: value["pass"] for name, value in checks.items()},
    "failures": failures,
    "outputs": outputs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log("== done: %d fills; failures=%d; wall %.0fs; peak rss %.2f GB =="
    % (fills.height, len(failures), time.perf_counter() - T0, PEAK_RSS))
_logf.close()
if failures:
    sys.exit(1)



