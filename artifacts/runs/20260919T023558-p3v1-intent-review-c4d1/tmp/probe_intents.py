"""Adversarial probes for the v1.1 intent-layer re-review (read-only).

Each probe exercises a seam NOT covered by tests/test_band_intents.py:
  A  cap_single_name termination wiring in intent mode (no test exists)
  B  override arriving AFTER the K=3 fallback armed (disarm semantics)
  C  m3 boundary: pm decision for a symbol without a pm bar (afternoon
     suspension) -- does the engine re-issue at the 15:00 decision point?
  D  duplicate (symbol, side, source_signal) -> INTENT_BY_KEY collision
  F  same-decision-point multi-intent cash competition with retries
Probes print observations only; they assert nothing about desired outcomes
except where marked ENGINE-OBSERVED.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl

SRC = Path(r"D:\量化\src")
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quant.backtest.band_engine import run_band_backtest_intents  # noqa: E402

D = date
SYM = "sh.600001"

INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "expiry_date": pl.Date,
    "priority": pl.Int64, "target_notional": pl.Float64,
    "target_weight": pl.Float64,
}


def it(symbol, side, first_date, first_session, source, *, intent=None,
       expiry=None, priority=1, target=None, weight=None):
    return {"symbol": symbol, "side": side, "intent": intent,
            "decision_date": first_date, "decision_session": first_session,
            "source_signal": source, "expiry_date": expiry,
            "priority": priority,
            "target_notional": None if target is None else float(target),
            "target_weight": None if weight is None else float(weight)}


def daily_bars(symbol, rows):
    return pl.DataFrame({
        "symbol": [symbol] * len(rows), "date": [r[0] for r in rows],
        "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
        "tradestatus": [1.0] * len(rows)})


def half_bars(symbol, rows):
    return pl.DataFrame({
        "symbol": [symbol] * len(rows), "trade_date": [r[0] for r in rows],
        "session": [r[1] for r in rows],
        "open": [float(r[2]) for r in rows], "high": [float(r[3]) for r in rows],
        "low": [float(r[4]) for r in rows], "close": [float(r[5]) for r in rows],
    })


def auto_limits(daily):
    return daily.select(
        "symbol", "date",
        (pl.col("close") * 1.1).alias("limit_up"),
        (pl.col("close") * 0.9).alias("limit_down"),
    )


def run_i(intents, daily, half, limits=None, **kw):
    limits = limits if limits is not None else auto_limits(daily)
    frame = pl.DataFrame(intents, schema=INTENT_SCHEMA)
    return run_band_backtest_intents(frame, daily, half, limits, **kw)


D1, D2, D3, D4, D5, D6 = (D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9))
S1, S2, S3 = D(2024, 1, 2), D(2024, 1, 3), D(2024, 1, 4)

# falling world (world B of the tests)
DAILY_B = daily_bars(SYM, [
    (D1, 10.0, 10.1, 9.5, 9.6), (D2, 9.4, 9.5, 9.0, 9.1),
    (D3, 8.9, 9.0, 8.55, 8.6), (D4, 8.5, 8.55, 8.4, 8.5),
    (D5, 8.5, 8.52, 8.48, 8.5), (D6, 8.5, 8.52, 8.48, 8.5)])
HALF_B = half_bars(SYM, [
    (D1, "am", 10.0, 10.05, 9.9, 10.0), (D1, "pm", 9.9, 10.0, 9.5, 9.6),
    (D2, "am", 9.4, 9.5, 9.2, 9.3), (D2, "pm", 9.2, 9.25, 9.0, 9.1),
    (D3, "am", 8.9, 9.0, 8.7, 8.75), (D3, "pm", 8.7, 8.7, 8.55, 8.6),
    (D4, "am", 8.5, 8.55, 8.45, 8.5), (D4, "pm", 8.5, 8.55, 8.4, 8.5),
    (D5, "am", 8.5, 8.52, 8.48, 8.5), (D5, "pm", 8.5, 8.51, 8.49, 8.5),
    (D6, "am", 8.5, 8.52, 8.48, 8.5), (D6, "pm", 8.5, 8.51, 8.49, 8.5)])

print("=" * 72)
print("PROBE A: cap_single_name termination wiring in INTENT mode")
res = run_i(intents_frame := pl.DataFrame([
    it(SYM, "buy", D1, "am", S1, weight=1.0)]), DAILY_B, HALF_B)
il = res.stats["intent_layer"]
print("  terminated_cap:", il["terminated_cap"],
      "| orders_generated:", il["orders_generated"],
      "| fills:", res.fills.height)
life = res.events.filter(pl.col("event") == "intent_lifecycle")
print("  lifecycle:", life["detail"].to_list())
voids = res.events.filter(pl.col("event") == "void_cap_single_name")
print("  cap voids:", voids.height, "| void days:",
      res.stats["void_days"].get("cap_single_name"))
# ENGINE-OBSERVED expectation: terminated_cap == 1, zero generated orders
print("  VERDICT-A:", "OK" if (il["terminated_cap"] == 1
                              and il["orders_generated"] == 0) else "UNEXPECTED")

print("=" * 72)
print("PROBE B: override arriving AFTER the fallback armed (disarm?)")
res = run_i(pl.DataFrame([
    it(SYM, "buy", D1, "am", S1, target=10_000),
    it(SYM, "sell", D2, "am", S2, intent="risk"),
    it(SYM, "sell", D3, "pm", S3, intent="risk")]), DAILY_B, HALF_B)
il = res.stats["intent_layer"]
print("  armed:", res.stats["k3_fallback"]["armed"],
      "| executed:", res.stats["k3_fallback"]["executed"],
      "| terminated_override:", il["terminated_override"],
      "| stopped_filled:", il["stopped_filled"])
print("  fills:", res.fills.select("side", "fill_type", "date", "session",
                                    "shares", "price").to_dicts())
life = res.events.filter(pl.col("event") == "intent_lifecycle")
print("  lifecycle:", life["detail"].to_list())
np_ev = res.events.filter((pl.col("event") == "not_penetrated")
                          & (pl.col("symbol") == SYM)).sort("date", "session")
print("  unfilled streak details:", [d.split("; ")[-1] for d in
                                      np_ev["detail"].to_list()])
# ENGINE-OBSERVED: fallback armed at streak 3 (D3 pm session) but the
# (D3,pm)-decision override must disarm before the D4 am session -> no
# market_fallback fill; the new source's streak restarts at 1.
ok = (res.stats["k3_fallback"]["executed"] == 0
      and il["terminated_override"] == 1)
print("  VERDICT-B:", "armed-then-disarmed (no fallback)" if ok
      else "fallback fired despite override")

print("=" * 72)
print("PROBE C: m3 boundary -- pm decision for a symbol with NO pm bar")
DAILY_C = daily_bars(SYM, [
    (D1, 10.0, 10.1, 9.5, 9.6), (D2, 10.5, 10.8, 10.2, 10.7),
    (D3, 10.2, 10.5, 10.0, 10.3), (D4, 10.1, 10.3, 10.0, 10.2),
    (D5, 10.1, 10.3, 10.0, 10.2), (D6, 10.1, 10.3, 10.0, 10.2)])
HALF_C = half_bars(SYM, [
    (D1, "am", 10.0, 10.05, 9.9, 10.0), (D1, "pm", 9.9, 10.0, 9.5, 9.6),
    (D2, "am", 10.5, 10.7, 10.3, 10.6),           # D2 pm SUSPENDED (no row)
    (D3, "am", 10.2, 10.4, 10.1, 10.3), (D3, "pm", 10.3, 10.4, 10.2, 10.3),
    (D4, "am", 10.1, 10.3, 10.05, 10.2), (D4, "pm", 10.2, 10.25, 10.1, 10.2),
    (D5, "am", 10.1, 10.3, 10.05, 10.2), (D5, "pm", 10.2, 10.25, 10.1, 10.2),
    (D6, "am", 10.1, 10.3, 10.05, 10.2), (D6, "pm", 10.2, 10.25, 10.1, 10.2)])
res = run_i(pl.DataFrame([
    it(SYM, "buy", D1, "am", S1, target=10_000),
    it(SYM, "sell", D2, "am", S2, intent="risk")]), DAILY_C, HALF_C)
il = res.stats["intent_layer"]
print("  emissions_skipped_no_anchor:", il["emissions_skipped_no_anchor"])
np_ev = res.events.filter((pl.col("event") == "not_penetrated")
                          & (pl.col("symbol") == SYM)).sort("date", "session")
print("  unfilled emissions (live session -> anchor | streak):")
for r in np_ev.iter_rows(named=True):
    print("   ", r["date"], r["session"], "anchor", r["limit_price"],
          "|", r["detail"].split("; ")[-1])
print("  fills:", res.fills.select("side", "date", "session", "shares",
                                    "price").to_dicts())
# question: was an order EMITTED at the (D2,pm) decision (live D3 am) even
# though D2 has no pm bar?  look at generation evidence via events on D3 am
print("  (m3 letter says: no 15:00 decision point on a day without an "
      "S_pm bar; next re-issue at D3 am decision -> live D3 pm)")

print("=" * 72)
print("PROBE D: duplicate (symbol, side, source) -> INTENT_BY_KEY collision")
res = run_i(pl.DataFrame([
    it(SYM, "buy", D1, "am", S1, target=10_000),
    # both sell intents share source S1 -> same lifecycle key
    it(SYM, "sell", D2, "am", S1, intent="risk", weight=0.30),
    it(SYM, "sell", D2, "pm", S1, intent="risk")]), DAILY_C, HALF_C)
il = res.stats["intent_layer"]
print("  stopped_filled:", il["stopped_filled"],
      "| terminated_override:", il["terminated_override"])
life = res.events.filter(pl.col("event") == "intent_lifecycle")
print("  lifecycle:", life["detail"].to_list())
print("  fills:", res.fills.select("side", "date", "session", "shares",
                                    "price").to_dicts())
print("  clips_final:", res.clips_final.to_dicts())

print("=" * 72)
print("PROBE F: two-symbol cash competition; insufficient-cash retry loop")
SYM2 = "sh.600002"
DAILY_F = daily_bars(SYM, [
    (D1, 10.0, 10.1, 9.5, 9.6), (D2, 10.2, 10.3, 10.0, 10.2),
    (D3, 10.2, 10.3, 10.0, 10.2), (D4, 10.2, 10.3, 10.0, 10.2),
    (D5, 10.2, 10.3, 10.0, 10.2), (D6, 10.2, 10.3, 10.0, 10.2)])
HALF_F = half_bars(SYM, [
    (D1, "am", 10.0, 10.05, 9.9, 10.0), (D1, "pm", 9.9, 10.0, 9.5, 9.6)]
    + [(d_, s, 10.2, 10.3, 10.1, 10.2) for d_ in (D2, D3, D4, D5, D6)
       for s in ("am", "pm")])
def panels_two():
    d = pl.concat([DAILY_F, daily_bars(SYM2, [
        (D1, 10.0, 10.1, 9.5, 9.6), (D2, 10.2, 10.3, 10.0, 10.2),
        (D3, 10.2, 10.3, 10.0, 10.2), (D4, 10.2, 10.3, 10.0, 10.2),
        (D5, 10.2, 10.3, 10.0, 10.2), (D6, 10.2, 10.3, 10.0, 10.2)])])
    h = pl.concat([HALF_F, half_bars(SYM2, [
        (D1, "am", 10.0, 10.05, 9.9, 10.0), (D1, "pm", 9.9, 10.0, 9.5, 9.6)]
        + [(d_, s, 10.2, 10.3, 10.1, 10.2) for d_ in (D2, D3, D4, D5, D6)
           for s in ("am", "pm")])])
    return d, h
rows = [
    it(SYM, "buy", D1, "am", S1, target=12_000, priority=1),
    it(SYM2, "buy", D1, "am", S1, target=12_000, priority=2)]
d2, h2 = panels_two()
res = run_i(pl.DataFrame(rows), d2, h2, initial_cash=20_000.0)
print("  insufficient_cash voids:",
      res.stats["cash_friction"]["insufficient_cash_orders"])
print("  fills:")
for r in res.fills.sort("date", "session").iter_rows(named=True):
    print("   ", r["symbol"], r["date"], r["session"], r["shares"], "@",
          r["price"], "cash_flow", round(r["net_cash_flow"], 2))
print("  min settled cash:", res.daily["settled_cash"].min(),
      "| final:", res.stats["final"]["settled_cash"])
print("  intent_layer:", {k: v for k, v in
                          res.stats["intent_layer"].items() if k != "n_intents"})
print("=" * 72)
print("PROBES DONE")
