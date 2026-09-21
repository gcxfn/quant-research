"""ETF pm-only routing probe (task 2, 2026-09-21; engineering only).

Authority: docs/decisions/2026-09-21-etf-pm-only-routing.md -- "探针 P1/P2
在 pm-only 模式下转为通过、P4 legacy 行为不变，作为语义闭环的核验点".

Cases (all inputs are REAL rows; no price or bar is synthesized except the
contract section 8.1 pm-session shape, which is a relabelling of the real
daily OHLC and is only used where it already existed in the pre-registered
P2/P4 probes):

  P1   halfday clock, DEFAULT routing, real ETF daily + real stock am/pm
       bars                      -> expect the v1.4.2 guard: BandContractError
       (this is the identity run's recorded P1, re-run as a control)
  P2   halfday clock, DEFAULT routing, + the section 8.1 single-pm-session
       ETF bars                  -> expect the same guard error
  P1p  halfday clock, etf_routing='pm_only', real ETF daily + real stock
       am/pm bars (NO ETF half-day row anywhere) -> expect a completed run
  P2p  same as P1p but with the section 8.1 ETF pm bars ALSO supplied
       -> expect a completed run (they are ignored: the daily row is the
       execution bar; supplying them must not change the P1p outcome)
  P3   halfday clock, stock-only control -> expect a completed run (harness
       sanity; recorded value 200,000 equity)
  P4   legacy clock, section 8.1 ETF bars, one real buy -> the identity
       run's own fixture; expect its recorded numbers unchanged
       (fill 2015-01-08 pm, 8,100 sh @ 2.445, cash 180,190.5, equity
       199,946.4)
  P4p  halfday clock, etf_routing='pm_only', real ETF daily, a buy
       re-issued at every pm decision point from the live ledger
       -> the dynamic semantic closure: every intent is a pm decision, every
       live session is the next day's pm, the fill is matched on the real
       daily bar, and fees/cash are hand-checked to the cent

Output: tmp/etf_pm_only_probe.json (deterministic bytes; rerun-stable).
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from quant.backtest.band_engine import (  # noqa: E402
    BandContractError, run_band_backtest_intents)

RUN_DIR = ROOT / "artifacts/runs/20260921T031044-engine-v15-pm-only-9f3a"
OUT = RUN_DIR / "tmp/etf_pm_only_probe.json"

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
        BS_DAILY, columns=DAILY_COLS).filter(
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

RETURNED_COLS = ("date", "session", "symbol", "side", "shares", "price",
                 "fees_total", "commission", "stamp_tax", "net_cash_flow",
                 "decision_date", "decision_session", "is_etf")


def call(tag: str, daily, half, meta, clock: str, provider=None,
         routing=None) -> dict:
    kwargs = {"execution_clock": clock}
    if routing is not None:
        kwargs["etf_routing"] = routing
    try:
        res = run_band_backtest_intents(
            None, daily, half, EMPTY_LIMITS, None, None, EMPTY_INSTR,
            symbol_meta=meta, initial_cash=200_000.0,
            intent_provider=provider, **kwargs)
    except BandContractError as exc:
        return {"tag": tag, "outcome": "BandContractError", "message": str(exc)}
    il = res.stats.get("intent_layer") or {}
    return {
        "tag": tag,
        "outcome": "ran",
        "routing_stats": res.stats["etf_leg"]["routing"],
        "rows": {k: res.daily[k][-1] for k in ("date", "settled_cash",
                                              "positions_value", "equity",
                                              "n_positions")},
        "orders_generated": il.get("orders_generated"),
        "orders_filled": res.stats.get("orders_filled"),
        "provider_calls": (res.stats.get("dynamic_layer") or {}).get(
            "provider_calls"),
        "dynamic_injected": (res.stats.get("dynamic_layer") or {}).get(
            "dynamic_injected"),
        "terminated_expired_halfday": il.get("terminated_expired_halfday"),
        "warnings": list(res.warnings)[:3],
        "fills": [{k: row[k] for k in RETURNED_COLS}
                  for row in res.fills.to_dicts()],
        "events": [{k: row[k] for k in ("date", "session", "event", "symbol",
                                        "limit_price", "ref_price", "shares")}
                   for row in res.events.to_dicts()],
    }


def noop_provider(day, sess, ledger):
    return None


def standing_buy_provider(symbol="sh.518880", notional=20_000.0, priority=1):
    """Re-issue the same real-price buy at EVERY pm decision point until it
    fills (the host's honest behaviour under the halfday clock: a normal
    recommendation is void after one decision point)."""
    state = {"filled": False, "submitted": []}

    def provider(day, sess, ledger):
        if sess != "pm" or state["filled"]:
            return None
        row = {"symbol": symbol, "side": "buy", "intent": None,
               "decision_date": day, "decision_session": sess,
               "source_signal": day, "expiry_date": None,
               "priority": priority, "target_notional": notional,
               "target_weight": None}
        state["submitted"].append(day.isoformat())
        return [row]
    return provider, state


def one_buy_provider(symbol="sh.518880", notional=20_000.0):
    """The identity run's P4 fixture: a single buy at the first pm point."""
    state = {"done": False}

    def provider(day, sess, ledger):
        if sess == "pm" and not state["done"]:
            state["done"] = True
            return [{"symbol": symbol, "side": "buy", "intent": None,
                     "decision_date": day, "decision_session": sess,
                     "source_signal": day, "expiry_date": None,
                     "priority": 1, "target_notional": notional,
                     "target_weight": None}]
        return None
    return provider


def hand_checks(case: dict, panel: pl.DataFrame, leg: str = "sh.518880",
                notional: float = 20_000.0) -> dict:
    """Independent arithmetic on the probe's own filled order."""
    if case.get("outcome") != "ran" or not case["fills"]:
        return {"applicable": False}
    fill = next(f for f in case["fills"] if f["symbol"] == leg)
    price = fill["price"]
    shares = int(notional // price // 100 * 100)
    commission = max(1e-4 * shares * price, 5.0)
    cash = 200_000.0 - shares * price - commission
    # the engine marks positions at the panel's last official close
    last_close = float(panel.filter(pl.col("symbol") == leg)["close"][-1])
    return {
        "applicable": True,
        "shares_hand": shares, "shares_engine": fill["shares"],
        "commission_hand": round(commission, 10),
        "commission_engine": fill["commission"],
        "stamp_hand": 0.0, "stamp_engine": fill["stamp_tax"],
        "cash_hand": round(cash, 10),
        "cash_engine": case["rows"]["settled_cash"],
        "last_close": last_close,
        "positions_value_hand": round(fill["shares"] * last_close, 10),
        "positions_value_engine": case["rows"]["positions_value"],
        "equity_hand": round(cash + fill["shares"] * last_close, 10),
        "equity_engine": case["rows"]["equity"],
        "routing_ok": (fill["decision_session"] == "pm"
                       and fill["session"] == "pm"
                       and fill["date"] > fill["decision_date"]),
        "next_trading_day": fill["date"] == min(
            d for d in DAYS if d > fill["decision_date"]),
    }


def main() -> dict:
    etf_daily = etf_daily_panel()
    stock_daily = stock_daily_panel()
    stock_half = stock_half_panel()
    etf_pm = etf_pm_only_bars(etf_daily)

    evidence: dict = {
        "run": RUN_DIR.name,
        "authority": "docs/decisions/2026-09-21-etf-pm-only-routing.md",
        "days": [d.isoformat() for d in DAYS],
        "etf_legs": ETF_LEGS, "stock_control": STOCK,
        "identity_source": ("artifacts/runs/20260921T023606-etf-dynamic-"
                            "identity-e41c/tmp/etf_dynamic_identity_probe.json"),
        "cases": {},
    }
    cases = evidence["cases"]
    cases["P1_paired_halfday_real_daily_real_stock_bars"] = call(
        "P1", pl.concat([etf_daily, stock_daily]), stock_half, ETF_META,
        "halfday", provider=noop_provider)
    cases["P2_paired_halfday_section81_bars"] = call(
        "P2", pl.concat([etf_daily, stock_daily]),
        pl.concat([stock_half, etf_pm]), ETF_META, "halfday",
        provider=noop_provider)
    cases["P1p_pm_only_halfday_real_daily_real_stock_bars"] = call(
        "P1p", pl.concat([etf_daily, stock_daily]), stock_half, ETF_META,
        "halfday", provider=noop_provider, routing="pm_only")
    cases["P2p_pm_only_halfday_section81_bars"] = call(
        "P2p", pl.concat([etf_daily, stock_daily]),
        pl.concat([stock_half, etf_pm]), ETF_META, "halfday",
        provider=noop_provider, routing="pm_only")
    cases["P3_control_stock_only_halfday"] = call(
        "P3", stock_daily, stock_half, None, "halfday", provider=noop_provider)

    p4_provider = one_buy_provider()
    p4 = call("P4", etf_daily, etf_pm, ETF_META, "legacy",
              provider=p4_provider)
    cases["P4_legacy_section81_bars_one_buy"] = p4
    cases["P4_legacy_section81_bars_one_buy"]["hand_checks"] = hand_checks(p4, etf_daily)

    provider, state = standing_buy_provider()
    p4p = call("P4p", etf_daily, stock_half, ETF_META, "halfday",
               provider=provider, routing="pm_only")
    p4p["submitted_at"] = state["submitted"]
    p4p["hand_checks"] = hand_checks(p4p, etf_daily)
    cases["P4p_pm_only_halfday_standing_buy"] = p4p

    # ---- assertions (the probe must fail loudly, not print a story) --------
    assert cases["P1_paired_halfday_real_daily_real_stock_bars"]["outcome"] \
        == "BandContractError"
    assert "requires ETF am and pm bars" in \
        cases["P1_paired_halfday_real_daily_real_stock_bars"]["message"]
    assert cases["P2_paired_halfday_section81_bars"]["outcome"] \
        == "BandContractError"
    for key in ("P1p_pm_only_halfday_real_daily_real_stock_bars",
                "P2p_pm_only_halfday_section81_bars",
                "P3_control_stock_only_halfday"):
        assert cases[key]["outcome"] == "ran", (key, cases[key])
        assert cases[key]["rows"]["equity"] == 200_000.0, key
    assert cases["P1p_pm_only_halfday_real_daily_real_stock_bars"]["routing_stats"] \
        .startswith("halfday pm-only ETF")
    # P1p and P2p must agree: supplying the section 8.1 synthetic pm bars
    # changes nothing under pm_only (the daily row is the execution bar)
    a = cases["P1p_pm_only_halfday_real_daily_real_stock_bars"]
    b = cases["P2p_pm_only_halfday_section81_bars"]
    assert a["rows"] == b["rows"] and a["fills"] == b["fills"], (a, b)
    # P4 legacy: the identity run's recorded outcome, unchanged (the fill's
    # decision point is the LAST re-issue, 01-07 pm -> live 01-08 pm; the
    # identity probe printed only a subset of columns, the other fields --
    # 8,100 sh @ 2.445, fee 5.0, cash 180,190.5, equity 199,946.4 -- are its
    # recorded numbers verbatim)
    assert cases["P4_legacy_section81_bars_one_buy"]["fills"] == [{
        "date": date(2015, 1, 8), "session": "pm", "symbol": "sh.518880",
        "side": "buy", "shares": 8100, "price": 2.445, "fees_total": 5.0,
        "commission": 5.0, "stamp_tax": 0.0, "net_cash_flow": -19809.5,
        "decision_date": date(2015, 1, 7), "decision_session": "pm",
        "is_etf": True}], cases["P4_legacy_section81_bars_one_buy"]["fills"]
    assert cases["P4_legacy_section81_bars_one_buy"]["rows"] == {
        "date": date(2015, 1, 9), "settled_cash": 180190.5,
        "positions_value": 19755.9, "equity": 199946.4, "n_positions": 1}
    # P4p: the dynamic closure
    hc = cases["P4p_pm_only_halfday_standing_buy"]["hand_checks"]
    assert hc["applicable"] and hc["routing_ok"] and hc["next_trading_day"]
    assert hc["shares_hand"] == hc["shares_engine"]
    assert hc["commission_hand"] == hc["commission_engine"] == 5.0
    assert hc["stamp_engine"] == 0.0
    assert abs(hc["cash_hand"] - hc["cash_engine"]) < 1e-9
    assert abs(hc["positions_value_hand"] - hc["positions_value_engine"]) < 1e-9
    assert abs(hc["equity_hand"] - hc["equity_engine"]) < 1e-9
    assert cases["P4p_pm_only_halfday_standing_buy"]["provider_calls"] == 2 * len(DAYS)
    OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=1,
                              default=str), encoding="utf-8")
    return evidence


if __name__ == "__main__":
    print(json.dumps(main(), ensure_ascii=False, indent=1, default=str))
