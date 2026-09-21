"""End-to-end audit regression for the +2R halving leg (2026-09-21 Q1).

Full band-engine chain with SingleNameRules wired as the provider's
exit brain, on inline synthetic bars (no real symbols):

  e1  trigger -> not penetrated -> re-issued at every decision point
      (armed, not done) -> fills once -> state flips to done and the
      re-issuing stops.  No fallback arms (profit class).
  e2  order replacement: an external profit sell overrides the standing
      halving intent and trims to an intermediate holding (8,000); the
      NEXT decision point re-issues the halving target from the live
      ledger and the clip lands exactly on the 5,000 target -- no
      double-sell, no dropped leg.
  e3  multi-clip FIFO fill lands exactly on the frozen absolute target.
  e4  stop whole-exit rides intent='risk' with a frozen source: three
      unfilled half-days ARM the K=3 open-market fallback (whole sale
      at the next open).
  e5  the halving leg is profit class: the same three unfilled half-days
      must NOT arm any fallback; a bounce fills the re-anchored limit.
  e6  an external whole sale zeroes the position: the module purges the
      stale halving event and a later re-entry above the old target is
      not smashed down by it.

Hand-checked against the frozen parameters (ATR .4, cost 10.0, stop 9.2,
R .8, +2R 11.6).  Zero trial consumption.
"""
from __future__ import annotations

from datetime import date

import polars as pl

from quant.backtest.band_engine import run_band_backtest_intents
from quant.research.single_name_rules import SingleNameRules

SYM = "sh.600001"
D1, D2, D3, D4, D5 = (date(2024, 1, 2 + i) for i in range(5))

PRICE = {  # decision-point price table the provider reads
    (D1, "am"): 10.0, (D1, "pm"): 9.96,
    (D2, "am"): 11.6, (D2, "pm"): 11.4,
    (D3, "am"): 11.2, (D3, "pm"): 11.4,
    (D4, "am"): 11.45, (D4, "pm"): 11.5,
}


def daily_bars(rows):
    return pl.DataFrame({
        "symbol": [SYM] * len(rows), "date": [r[0] for r in rows],
        "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
        "tradestatus": [1.0] * len(rows)})


def half_bars(rows):
    return pl.DataFrame({
        "symbol": [SYM] * len(rows), "trade_date": [r[0] for r in rows],
        "session": [r[1] for r in rows],
        "open": [float(r[2]) for r in rows], "high": [float(r[3]) for r in rows],
        "low": [float(r[4]) for r in rows], "close": [float(r[5]) for r in rows]})


def auto_limits(daily):
    return daily.select(
        "symbol", "date",
        (pl.col("close") * 1.1).alias("limit_up"),
        (pl.col("close") * 0.9).alias("limit_down"))


def buy_row(day, sess, notional):
    return {"symbol": SYM, "side": "buy", "intent": None,
            "decision_date": day, "decision_session": sess,
            "source_signal": day, "expiry_date": None, "priority": 1,
            "target_notional": float(notional), "target_weight": None}


def profit_sell_row(day, sess, notional):
    return {"symbol": SYM, "side": "sell", "intent": "profit",
            "decision_date": day, "decision_session": sess,
            "source_signal": day, "expiry_date": None, "priority": 9,
            "target_notional": float(notional), "target_weight": None}


def run_case(provider, daily, half):
    return run_band_backtest_intents(
        None, daily, half, auto_limits(daily), symbol_meta={},
        initial_cash=400_000.0, execution_clock="halfday",
        intent_provider=provider)


# ---------------------------------------------------------------------------
# e1: trigger -> not penetrated -> re-issue -> fill -> done
# ---------------------------------------------------------------------------

def test_e1_halving_reissue_chain():
    daily = daily_bars([
        (D1, 10.0, 10.02, 9.94, 9.96),
        (D2, 10.5, 11.62, 11.30, 11.40),
        (D3, 11.35, 11.45, 11.10, 11.40),
        (D4, 11.40, 11.55, 11.30, 11.50)])
    half = half_bars([
        (D1, "am", 10.0, 10.02, 9.97, 10.0),
        (D1, "pm", 9.99, 10.01, 9.94, 9.96),   # low 9.94 < 10: buy fills
        (D2, "am", 10.5, 11.62, 10.5, 11.6),   # close 11.6 = +2R trigger
        (D2, "pm", 11.55, 11.58, 11.30, 11.40),  # high 11.58 < 11.6: no fill
        (D3, "am", 11.35, 11.38, 11.10, 11.20),  # high 11.38 < 11.4: no fill
        (D3, "pm", 11.25, 11.45, 11.15, 11.40),  # high 11.45 > 11.2: fills
        (D4, "am", 11.40, 11.50, 11.30, 11.45),
        (D4, "pm", 11.45, 11.55, 11.35, 11.50)])
    snr = SingleNameRules(lambda s, d: 0.4)
    submitted = []

    def provider(day, sess, ledger):
        rows = []
        if (day, sess) == (D1, "am"):
            rows.append(buy_row(day, sess, 100_000))
        stock_pos = [p for p in ledger["positions"]]
        rows.extend(snr.decide(stock_pos, {SYM: PRICE[(day, sess)]},
                               day=day, session=sess))
        submitted.append({"day": day, "sess": sess, "rows": len(rows)})
        return rows or None

    res = run_case(provider, daily, half)
    sells = res.fills.filter(pl.col("side") == "sell")
    assert sells.height == 1
    s = sells.to_dicts()[0]
    assert s["shares"] == 5_000 and s["price"] == 11.2  # keep-5,000 @ anchor
    # exactly two unfilled sell sessions before the fill -- profit-class
    # orders expire silently (event 'session_expired', no streak)
    nps = res.events.filter(
        (pl.col("event") == "session_expired")
        & (pl.col("symbol") == SYM)).height
    assert nps == 2
    # after the fill the ledger holds the halved clip and the rule is done:
    # D3-pm and both D4 decision points submit nothing
    assert submitted[-3:] == [{"day": D3, "sess": "pm", "rows": 0},
                              {"day": D4, "sess": "am", "rows": 0},
                              {"day": D4, "sess": "pm", "rows": 0}]
    st = snr.clip_diagnostics()[(SYM, D1.isoformat(), "pm")]
    assert st["half_armed"] is True and st["half_done"] is True
    # final holding = the 5,000-share halved target, single clip
    clips = res.clips_final.filter(pl.col("symbol") == SYM).to_dicts()
    assert sum(c["shares"] for c in clips) == 5_000


# ---------------------------------------------------------------------------
# e2: replacement by an external order, recovery from the live ledger
# ---------------------------------------------------------------------------

def test_e2_replacement_then_recovery():
    daily = daily_bars([
        (D1, 10.0, 10.02, 9.94, 9.96),
        (D2, 10.5, 11.62, 11.35, 11.40),
        (D3, 11.42, 11.55, 11.25, 11.45),
        (D4, 11.45, 11.60, 11.35, 11.50)])
    half = half_bars([
        (D1, "am", 10.0, 10.02, 9.97, 10.0),
        (D1, "pm", 9.99, 10.01, 9.94, 9.96),
        (D2, "am", 10.5, 11.62, 10.5, 11.6),     # +2R trigger
        (D2, "pm", 11.50, 11.58, 11.35, 11.40),  # not penetrated
        (D3, "am", 11.42, 11.55, 11.30, 11.35),  # replacement sell fills
        (D3, "pm", 11.36, 11.50, 11.25, 11.45),  # recovered halving fills
        (D4, "am", 11.45, 11.58, 11.35, 11.45),
        (D4, "pm", 11.46, 11.60, 11.36, 11.50)])
    snr = SingleNameRules(lambda s, d: 0.4)

    def provider(day, sess, ledger):
        rows = []
        if (day, sess) == (D1, "am"):
            rows.append(buy_row(day, sess, 100_000))
        if (day, sess) == (D2, "pm"):
            # an external overlay-style trim REPLACES the standing halving
            # intent this decision point (same symbol -> override)
            rows.append(profit_sell_row(day, sess, 8_000 * 11.40))
            return rows
        rows.extend(snr.decide(list(ledger["positions"]),
                               {SYM: PRICE2[(day, sess)]},
                               day=day, session=sess))
        return rows or None

    res = run_case(provider, daily, half)
    sells = res.fills.filter(pl.col("side") == "sell").to_dicts()
    assert [(s["shares"], s["price"]) for s in sells] == [
        (2_000, 11.40),   # replacement trim to 8,000
        (3_000, 11.35)]   # recovered halving to the 5,000 target
    clips = res.clips_final.filter(pl.col("symbol") == SYM).to_dicts()
    assert sum(c["shares"] for c in clips) == 5_000
    st = snr.clip_diagnostics()[(SYM, D1.isoformat(), "pm")]
    assert st["half_armed"] is True and st["half_done"] is True


PRICE2 = {  # e2 price table (D3 differs from e1)
    (D1, "am"): 10.0, (D1, "pm"): 9.96,
    (D2, "am"): 11.6, (D2, "pm"): 11.4,
    (D3, "am"): 11.35, (D3, "pm"): 11.45,
    (D4, "am"): 11.45, (D4, "pm"): 11.5,
}


# ---------------------------------------------------------------------------
# e3: multi-clip position, FIFO fill consumes the OTHER lot -- no oversell
# (review finding 1: the first Q1 fix re-counted per-clip keeps after a
# FIFO fill and sold the un-triggered lot down; the absolute-event fix
# must land exactly on the frozen target)
# ---------------------------------------------------------------------------

def test_e3_multiclip_fifo_no_oversell():
    daily = daily_bars([
        (D1, 10.0, 10.05, 9.94, 10.0),
        (D2, 10.9, 11.10, 10.8, 11.0),
        (D3, 11.9, 12.40, 11.8, 12.3),
        (D4, 12.25, 12.50, 12.1, 12.4),
        (D5, 12.3, 12.55, 12.2, 12.45)])
    half = half_bars([
        (D1, "am", 10.0, 10.02, 9.97, 10.0),
        (D1, "pm", 9.99, 10.01, 9.94, 10.0),     # buy 1 fills @10
        (D2, "am", 10.9, 11.05, 10.8, 11.0),
        (D2, "pm", 11.0, 11.05, 10.9, 11.0),     # buy 2 fills @11
        (D3, "am", 11.9, 12.35, 11.8, 12.3),     # +2R on lot 2 -> event
        (D3, "pm", 12.25, 12.50, 12.1, 12.4),    # high > 12.3: fills
        (D4, "am", 12.30, 12.40, 12.2, 12.3),    # no new orders expected
        (D4, "pm", 12.30, 12.50, 12.25, 12.4),
        (D5, "am", 12.35, 12.45, 12.25, 12.35),
        (D5, "pm", 12.40, 12.55, 12.3, 12.45)])
    # ATR by acquired day: lot 1 (D1, cost 10) wide R 1.5 -> +2R 13.0
    # (never triggered here); lot 2 (D2, cost 11) R 0.6 -> +2R 12.2
    atr_by_day = {D1: 0.75, D2: 0.30, D3: 0.30, D4: 0.30, D5: 0.30}
    snr = SingleNameRules(lambda s, d: atr_by_day[d])
    submitted = []

    def provider(day, sess, ledger):
        rows = []
        if (day, sess) == (D1, "am"):
            rows.append(buy_row(day, sess, 37_000))    # 3,700 @ 10
        if (day, sess) == (D2, "am"):
            rows.append(buy_row(day, sess, 4_700 * 11.0))  # 4,700 @ 11
        rows.extend(snr.decide(list(ledger["positions"]),
                               {SYM: PRICE3[(day, sess)]},
                               day=day, session=sess))
        submitted.append({"day": day, "sess": sess, "rows": len(rows)})
        return rows or None

    res = run_case(provider, daily, half)
    sells = res.fills.filter(pl.col("side") == "sell").to_dicts()
    # exactly ONE halving sell: 2,400 shares (position 8,400 -> 6,000),
    # consumed FIFO from lot 1 -- never the 6,100 the reviewed bug sold
    assert [(s["shares"],) for s in sells] == [(2_400,)]
    clips = res.clips_final.filter(pl.col("symbol") == SYM).to_dicts()
    assert sum(c["shares"] for c in clips) == 6_000
    assert {c["shares"] for c in clips} == {1_300, 4_700}  # FIFO on lot 1
    # after the event completes no further sell rows are submitted
    assert submitted[-3:] == [{"day": D4, "sess": "pm", "rows": 0},
                              {"day": D5, "sess": "am", "rows": 0},
                              {"day": D5, "sess": "pm", "rows": 0}]
    ev = snr.events()
    assert SYM not in ev                       # event completed
    st2 = snr.clip_diagnostics()[(SYM, D2.isoformat(), "pm")]
    assert st2["half_armed"] is True and st2["half_done"] is True


PRICE3 = {
    (D1, "am"): 10.0, (D1, "pm"): 10.0,
    (D2, "am"): 11.0, (D2, "pm"): 11.0,
    (D3, "am"): 12.3, (D3, "pm"): 12.4,
    (D4, "am"): 12.3, (D4, "pm"): 12.4,
    (D5, "am"): 12.35, (D5, "pm"): 12.45,
}


# ---------------------------------------------------------------------------
# e4: a stop whole-exit order arms the K=3 open-market fallback
# (second-review finding: whole-exit rows carried source=each new day, so
# the engine streak reset daily and stops NEVER armed -- exactly the leg
# AGENTS section 1 requires the fallback for)
# ---------------------------------------------------------------------------

def test_e4_stop_whole_exit_keeps_k3_fallback():
    daily = daily_bars([
        (D1, 10.0, 10.02, 9.94, 9.96),
        (D2, 9.50, 9.55, 8.98, 9.00),
        (D3, 8.95, 8.98, 8.78, 8.85),
        (D4, 8.80, 8.95, 8.75, 8.92),
        (D5, 8.90, 8.98, 8.82, 8.90)])
    # steady decline: every execution half-day's HIGH stays at/below the
    # standing order's (re-anchored) limit, so the stop sell goes unfilled
    # for three half-days (streak 1: D2-pm, 2: D3-am, 3: D3-pm -> armed);
    # the armed fallback then sells the WHOLE position at the D4-am open
    half = half_bars([
        (D1, "am", 10.0, 10.02, 9.97, 10.0),
        (D1, "pm", 9.99, 10.01, 9.94, 9.96),   # buy fills @10
        (D2, "am", 9.50, 9.55, 9.10, 9.10),    # close 9.10 <= stop 9.2
        (D2, "pm", 9.05, 9.08, 8.98, 9.00),    # high 9.08 <= 9.10: no fill
        (D3, "am", 8.95, 8.98, 8.85, 8.90),    # high 8.98 <= 9.00: no fill
        (D3, "pm", 8.88, 8.90, 8.78, 8.85),    # high 8.90 <= 8.90: no fill
        (D4, "am", 8.80, 8.95, 8.75, 8.90),    # fallback @ open 8.80
        (D4, "pm", 8.90, 8.96, 8.85, 8.92),
        (D5, "am", 8.90, 8.96, 8.85, 8.88),
        (D5, "pm", 8.88, 8.98, 8.82, 8.90)])
    snr = SingleNameRules(lambda s, d: 0.4)

    def provider(day, sess, ledger):
        rows = []
        if (day, sess) == (D1, "am"):
            rows.append(buy_row(day, sess, 100_000))
        rows.extend(snr.decide(list(ledger["positions"]),
                               {SYM: PRICE5[(day, sess)]},
                               day=day, session=sess))
        return rows or None

    res = run_case(provider, daily, half)
    sells = res.fills.filter(pl.col("side") == "sell").to_dicts()
    assert len(sells) == 1
    s = sells[0]
    # the K=3 fallback sells EVERYTHING at the OPEN
    assert s["shares"] == 10_000 and s["price"] == 8.80
    me = res.events.filter(pl.col("event") == "market_exit_filled")
    assert me.height == 1
    assert res.stats["k3_fallback"]["armed"] == 1
    assert snr.events() == {}        # position gone -> event purged
    assert res.clips_final.filter(pl.col("symbol") == SYM).height == 0


PRICE5 = {
    (D1, "am"): 10.0, (D1, "pm"): 9.96,
    (D2, "am"): 9.10, (D2, "pm"): 9.00,
    (D3, "am"): 8.90, (D3, "pm"): 8.85,
    (D4, "am"): 8.90, (D4, "pm"): 8.92,
    (D5, "am"): 8.88, (D5, "pm"): 8.90,
}


# ---------------------------------------------------------------------------
# e5: the halving leg is PROFIT class -- three unfilled half-days must NOT
# arm the fallback; the order simply keeps expiring and re-issuing until a
# bounce fills it at its (re-anchored) limit
# (counter-test to the pre-fix behavior where take_half rode intent='risk'
# and got force-sold at opens)
# ---------------------------------------------------------------------------

def test_e5_halving_profit_intent_never_arms_fallback():
    daily = daily_bars([
        (D1, 10.0, 10.02, 9.94, 9.96),
        (D2, 10.5, 11.62, 10.50, 11.45),
        (D3, 11.44, 11.45, 11.05, 11.15),
        (D4, 11.05, 11.25, 10.95, 11.05),
        (D5, 11.10, 11.20, 11.00, 11.10)])
    # same steady-decline shape as e4: the halving order is unfilled for
    # three half-days (D2-pm, D3-am, D3-pm) -- but as a PROFIT intent it
    # never arms; the D4-am bounce (high 11.25 > 11.15) fills it at 11.15
    half = half_bars([
        (D1, "am", 10.0, 10.02, 9.97, 10.0),
        (D1, "pm", 9.99, 10.01, 9.94, 9.96),
        (D2, "am", 10.5, 11.62, 10.5, 11.6),    # +2R trigger @11.6
        (D2, "pm", 11.58, 11.59, 11.40, 11.45),   # high 11.59 <= 11.6
        (D3, "am", 11.44, 11.45, 11.20, 11.30),   # high 11.45 <= 11.45
        (D3, "pm", 11.29, 11.30, 11.05, 11.15),   # high 11.30 <= 11.30
        (D4, "am", 11.05, 11.25, 10.95, 11.10),   # high 11.25 > 11.15: fill
        (D4, "pm", 11.10, 11.20, 11.00, 11.05),
        (D5, "am", 11.10, 11.18, 11.00, 11.08),
        (D5, "pm", 11.08, 11.15, 11.00, 11.05)])
    snr = SingleNameRules(lambda s, d: 0.4)

    def provider(day, sess, ledger):
        rows = []
        if (day, sess) == (D1, "am"):
            rows.append(buy_row(day, sess, 100_000))
        rows.extend(snr.decide(list(ledger["positions"]),
                               {SYM: PRICE4[(day, sess)]},
                               day=day, session=sess))
        return rows or None

    res = run_case(provider, daily, half)
    sells = res.fills.filter(pl.col("side") == "sell").to_dicts()
    assert len(sells) == 1
    s = sells[0]
    # filled at the standing order's re-anchored limit -- NOT at an open
    assert s["shares"] == 5_000 and s["price"] == 11.15
    assert res.events.filter(pl.col("event") == "market_exit_filled").height == 0
    assert res.stats["k3_fallback"]["armed"] == 0
    clips = res.clips_final.filter(pl.col("symbol") == SYM).to_dicts()
    assert sum(c["shares"] for c in clips) == 5_000
    assert snr.events() == {}


PRICE4 = {
    (D1, "am"): 10.0, (D1, "pm"): 9.96,
    (D2, "am"): 11.6, (D2, "pm"): 11.45,
    (D3, "am"): 11.30, (D3, "pm"): 11.15,
    (D4, "am"): 11.10, (D4, "pm"): 11.05,
    (D5, "am"): 11.08, (D5, "pm"): 11.05,
}


# ---------------------------------------------------------------------------
# e6: an external whole sale (account-trim style) zeroes the position;
# the module must purge the stale halving event so a later re-entry ABOVE
# the old target is not smashed down by it
# (second-review finding: cross-position event residue, over-sold 3,000)
# ---------------------------------------------------------------------------

def test_e6_external_zero_purges_stale_event():
    daily = daily_bars([
        (D1, 10.0, 10.02, 9.94, 9.96),
        (D2, 10.5, 11.62, 10.5, 11.45),
        (D3, 11.45, 11.55, 11.30, 11.40),
        (D4, 11.35, 11.45, 11.05, 11.30),
        (D5, 11.35, 11.50, 11.25, 11.45)])
    half = half_bars([
        (D1, "am", 10.0, 10.02, 9.97, 10.0),
        (D1, "pm", 9.99, 10.01, 9.94, 9.96),   # buy 10,000 @10
        (D2, "am", 10.5, 11.62, 10.5, 11.6),   # +2R -> halving event 5,000
        (D2, "pm", 11.50, 11.50, 11.35, 11.45),  # high 11.50 <= 11.6
        (D3, "am", 11.45, 11.50, 11.30, 11.40),  # external sell fills ALL
        (D3, "pm", 11.40, 11.48, 11.35, 11.42),
        (D4, "am", 11.35, 11.42, 11.20, 11.30),
        (D4, "pm", 11.30, 11.40, 11.10, 11.25),  # re-entry 8,100 @11.30
        (D5, "am", 11.30, 11.42, 11.25, 11.40),
        (D5, "pm", 11.40, 11.50, 11.30, 11.45)])
    snr = SingleNameRules(lambda s, d: 0.4)
    module_rows = []

    def provider(day, sess, ledger):
        rows = []
        if (day, sess) == (D1, "am"):
            rows.append(buy_row(day, sess, 100_000))
        if (day, sess) == (D2, "pm"):
            # external account-trim style WHOLE risk sell replaces every
            # same-symbol row at this decision point
            rows.append({"symbol": SYM, "side": "sell", "intent": "risk",
                         "decision_date": day, "decision_session": sess,
                         "source_signal": day, "expiry_date": None,
                         "priority": 9_000, "target_weight": None,
                         "target_notional": None})
            module_rows.append({"day": day, "sess": sess, "rows": 0})
            return rows
        if (day, sess) == (D4, "am"):
            rows.append(buy_row(day, sess, 92_000))
        sn = snr.decide(list(ledger["positions"]),
                        {SYM: PRICE6[(day, sess)]}, day=day, session=sess)
        rows.extend(sn)
        module_rows.append({"day": day, "sess": sess, "rows": len(sn)})
        return rows or None

    res = run_case(provider, daily, half)
    sells = res.fills.filter(pl.col("side") == "sell").to_dicts()
    # exactly ONE sell: the external whole exit (10,000 @ 11.45).  The
    # stale keep-5,000 event must NOT sell the re-entered 8,100 down
    assert [(s["shares"], s["price"]) for s in sells] == [(10_000, 11.45)]
    clips = res.clips_final.filter(pl.col("symbol") == SYM).to_dicts()
    # re-entry bought 8,100 (92,000 notional / 11.30 anchor, lot-rounded)
    # -- still above the stale keep-5,000 target, and NOT trimmed by it
    assert sum(c["shares"] for c in clips) == 8_100
    assert snr.events() == {}
    # after the purge the module emits nothing for the re-entered clip
    assert module_rows[-2:] == [{"day": D5, "sess": "am", "rows": 0},
                                {"day": D5, "sess": "pm", "rows": 0}]


PRICE6 = {
    (D1, "am"): 10.0, (D1, "pm"): 9.96,
    (D2, "am"): 11.6, (D2, "pm"): 11.45,
    (D3, "am"): 11.40, (D3, "pm"): 11.42,
    (D4, "am"): 11.30, (D4, "pm"): 11.25,
    (D5, "am"): 11.40, (D5, "pm"): 11.45,
}

