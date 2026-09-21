"""ETF dynamic-path data identity probe (2026-09-21, engineering only).

Fail-closed verification that the frozen dynamic engine
(``band_engine`` sha256 bcbdd44bb855b803..., execution_clock='halfday')
cannot be driven with REAL ETF data from any repository dataset, because
no ETF half-day bars exist.

Cases (all inputs are REAL rows read from the pinned datasets; nothing is
fabricated):

  P1  real ETF daily panel (the three H2-03 defensive legs) + REAL stock
      half-day bars (the real batch has zero ETF rows) + etf meta,
      execution_clock='halfday'  -> expect BandContractError
      "halfday clock requires ETF am and pm bars"
  P2  same, but the ETF half-day frame is the contract-section-8.1 shape
      actually used by the H2-03 hybrid runner (a synthetic single 'pm'
      session built from the day's real OHLC) -> expect the same refusal
  P3  control: same harness, stock-only panel with ITS real half-day bars
      (am+pm), halfday clock -> expect a clean run (0 intents), proving the
      probe harness itself is sound and the refusal is ETF-specific
  P4  control: same real ETF daily + section-8.1 pm-only frame under the
      LEGACY clock with a single real-price ETF buy attempt at a pm
      decision -> expect a clean run, isolating the gap to the halfday
      clock (this is the route H2-03 already used)

Zero trial consumption; no strategy claim; no output beyond the JSON
evidence file.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))

from quant.backtest.band_engine import (  # noqa: E402
    BandContractError, run_band_backtest_intents)

RUN_DIR = ROOT / "artifacts/runs/20260921T023606-etf-dynamic-identity-e41c"
OUT = RUN_DIR / "tmp/etf_dynamic_identity_probe.json"

ETF_LEGS = ["sh.511010", "sh.518880", "sz.159934"]   # H2-03 defensive legs
STOCK = "sh.600000"
DAYS = [date(2015, 1, d) for d in (5, 6, 7, 8, 9)]   # 5 real trading days

ETF_DAILY = ROOT / "data/processed/etf-daily-20260919/daily_2015_2024.parquet"
BS_DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
HALF_DIR = ROOT / "data/processed/halfday-bars-20260918"

EMPTY_LIMITS = pl.DataFrame(schema={
    "symbol": pl.String, "date": pl.Date,
    "limit_up": pl.Float64, "limit_down": pl.Float64})
EMPTY_INSTR = pl.DataFrame(schema={
    "symbol": pl.String, "is_etf": pl.Boolean, "is_t0": pl.Boolean})

evidence: dict = {"run_id": RUN_DIR.name, "days": [d.isoformat() for d in DAYS],
                  "etf_legs": ETF_LEGS, "stock_control": STOCK, "cases": {}}


DAILY_COLS = ["symbol", "date", "open", "high", "low", "close", "preclose",
              "tradestatus"]


def _canon_daily(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.select(DAILY_COLS).select(pl.all().sort_by("date"))


def etf_daily_panel() -> pl.DataFrame:
    daily = pl.read_parquet(ETF_DAILY).filter(
        pl.col("symbol").is_in(ETF_LEGS) & pl.col("date").is_in(DAYS))
    assert daily.height == len(ETF_LEGS) * len(DAYS), daily.height
    return _canon_daily(daily.with_columns(pl.lit(1.0).alias("tradestatus")))


def stock_daily_panel() -> pl.DataFrame:
    daily = pl.read_parquet(
        BS_DAILY, columns=["symbol", "date", "open", "high", "low", "close",
                           "preclose", "tradestatus"]).filter(
        (pl.col("symbol") == STOCK) & pl.col("date").is_in(DAYS))
    assert daily.height == len(DAYS), daily.height
    return _canon_daily(daily)


def stock_half_panel() -> pl.DataFrame:
    half = pl.read_parquet(
        HALF_DIR / "year=2015/bars.parquet",
        columns=["symbol", "trade_date", "session", "open", "high", "low",
                 "close"]).filter(
        (pl.col("symbol") == STOCK) & pl.col("trade_date").is_in(DAYS))
    assert half.height == 2 * len(DAYS), half.height
    return half


def etf_pm_only_bars(panel: pl.DataFrame) -> pl.DataFrame:
    """Contract section 8.1 shape (the H2-03 hybrid runner's etf_pm_bars):
    one synthetic 'pm' session per ETF trading day, bar = the real daily
    OHLC.  Real prices, no intraday invention -- but no am session either."""
    return panel.select(
        pl.col("symbol"), pl.col("date").alias("trade_date"),
        pl.lit("pm", dtype=pl.String).alias("session"),
        pl.col("open"), pl.col("high"), pl.col("low"), pl.col("close"))


ETF_META = {s: {"asset_class": "etf", "band": 0.10, "t_plus": 0}
            for s in ETF_LEGS}


def call(tag: str, daily, half, meta, clock: str, provider=None) -> dict:
    try:
        res = run_band_backtest_intents(
            None, daily, half, EMPTY_LIMITS, None, None, EMPTY_INSTR,
            symbol_meta=meta, initial_cash=200_000.0,
            execution_clock=clock, intent_provider=provider)
    except BandContractError as exc:
        return {"outcome": "BandContractError", "message": str(exc)}
    il = res.stats.get("intent_layer") or {}
    return {
        "outcome": "ran",
        "rows": {k: res.daily[k][-1] for k in ("date", "settled_cash",
                                              "positions_value", "equity",
                                              "n_positions")},
        "session_events": res.stats.get("session_events"),
        "orders_generated": il.get("orders_generated"),
        "orders_filled": res.stats.get("orders_filled"),
        "terminations": {k: v for k, v in (il.get("terminations") or {}).items()
                         if v},
        "warnings": list(res.warnings)[:3],
        "fills": [{k: row[k] for k in ("date", "session", "symbol", "side",
                                       "shares", "price", "fees_total")}
                  for row in res.fills.to_dicts()][:4],
    }


etf_daily = etf_daily_panel()
stock_daily = stock_daily_panel()
stock_half = stock_half_panel()

def noop_provider(day, sess, ledger):
    return None


evidence["cases"]["P1_real_etf_daily_real_stock_bars_halfday"] = call(
    "P1", pl.concat([etf_daily, stock_daily]), stock_half, ETF_META, "halfday",
    provider=noop_provider)

evidence["cases"]["P2_pm_only_section81_bars_halfday"] = call(
    "P2", pl.concat([etf_daily, stock_daily]),
    pl.concat([stock_half, etf_pm_only_bars(etf_daily)]), ETF_META, "halfday",
    provider=noop_provider)

evidence["cases"]["P3_control_stock_only_halfday"] = call(
    "P3", stock_daily, stock_half, None, "halfday", provider=noop_provider)

calls: list = []
submitted = {"done": False}


def probe_provider(day, sess, ledger):
    calls.append({"day": day.isoformat(), "session": sess,
                  "cash": ledger["cash"],
                  "equity_snapshot": ledger["equity_snapshot"],
                  "positions": len(ledger["positions"])})
    if sess == "pm" and not submitted["done"]:   # one buy at the first pm
        submitted["done"] = True
        return [{"symbol": "sh.518880", "side": "buy", "intent": None,
                 "decision_date": day, "decision_session": sess,
                 "source_signal": day, "expiry_date": None, "priority": 1,
                 "target_notional": 20_000.0, "target_weight": None}]
    return None


p4 = call("P4", etf_daily, etf_pm_only_bars(etf_daily), ETF_META, "legacy",
          provider=probe_provider)
p4["provider_calls"] = calls[:3]
evidence["cases"]["P4_pm_only_section81_bars_legacy_one_buy"] = p4

OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=1,
                          default=str), encoding="utf-8")
print(json.dumps(evidence, ensure_ascii=False, indent=1, default=str))
