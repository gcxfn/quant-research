"""v1.5 targeted tests: ``etf_routing='pm_only'`` (halfday clock).

Authority: ``docs/decisions/2026-09-21-etf-pm-only-routing.md`` -- the
approved "ETF trades a single 15:00 decision per day" expression inside the
halfday clock, motivated by a data fact (no ETF half-day bars exist; the
halfday guard structurally rejected the leg) and NOT by a strategy result.

Four targeted seams (the decision's acceptance list):

  t1  pm -> next-day pm on the REAL daily bar   a pm decision emits an
      order whose live session is the next day's pm; the fill is decided
      by the daily bar's low (whole-day range, section 8.1) at the
      decision-day close anchor -- strict penetration, never a
      touch-triggered fill, never a better price
  t2  am ETF intents are rejected               both entry points (static
      frame and provider) raise on an ETF row stamped 'am'; a STOCK am
      intent in the same account still runs (the guard must not
      over-reject), and its live session stays the halfday same-day pm
  t3  am snapshot = last traded close           an ETF position marked at
      an 11:30 decision point uses the last TRADED official close (the
      completed-am-bar override does not apply: the leg has no am bar by
      contract); the ledger snapshot is asserted against hand arithmetic
  t4  no ETF halfday bar required               an empty half-day table
      runs under pm_only (with a genuine fill) while the same inputs under
      the default routing are rejected by the am+pm guard; the mode/clock
      guards raise

All frames are inline synthetic (no real symbols); engineering only, zero
trial consumption.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.backtest.band_engine import BandContractError, run_band_backtest_intents

D1, D2, D3, D4 = (date(2024, 1, 2 + i) for i in range(4))
ETF = 'sh.510300'
STOCK = 'sh.600001'

HALF_SCHEMA = {
    'symbol': pl.String, 'trade_date': pl.Date, 'session': pl.String,
    'open': pl.Float64, 'high': pl.Float64, 'low': pl.Float64,
    'close': pl.Float64,
}
EMPTY_HALF = pl.DataFrame(schema=HALF_SCHEMA)
EMPTY_LIMITS = pl.DataFrame(schema={
    'symbol': pl.String, 'date': pl.Date,
    'limit_up': pl.Float64, 'limit_down': pl.Float64})
EMPTY_INSTR = pl.DataFrame(schema={
    'symbol': pl.String, 'is_etf': pl.Boolean, 'is_t0': pl.Boolean})


def daily_frame(symbol, rows):
    """rows: (date, open, high, low, close)."""
    closes = [float(r[4]) for r in rows]
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': closes,
        'preclose': [closes[0]] + closes[:-1],
        'tradestatus': [1.0] * len(rows)})


def half_frame(symbol, rows):
    """rows: (date, session, open, high, low, close)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows]})


def etf_meta(symbol=ETF):
    return {symbol: {"asset_class": "etf", "band": .1, "t_plus": 0}}


def row(symbol, side, day, sess, source, *, intent=None, target=None,
        weight=None, priority=1):
    return {'symbol': symbol, 'side': side, 'intent': intent,
            'decision_date': day, 'decision_session': sess,
            'source_signal': source, 'expiry_date': None,
            'priority': priority,
            'target_notional': None if target is None else float(target),
            'target_weight': None if weight is None else float(weight)}


def run_pm_only(provider, daily, half, *, intents=None, meta=None,
                clock="halfday", routing="pm_only", limits=None,
                instruments=None, initial_cash=200_000.0):
    return run_band_backtest_intents(
        intents, daily, half,
        EMPTY_LIMITS if limits is None else limits,
        instruments=EMPTY_INSTR if instruments is None else instruments,
        symbol_meta=meta if meta is not None else etf_meta(),
        initial_cash=initial_cash, execution_clock=clock, etf_routing=routing,
        intent_provider=provider)


def once(*, at=D1, sess='pm', symbol=ETF, **kw):
    """Provider that submits ONE buy at the given decision point; ``kw`` are
    the row fields (``target=`` notional, ``weight=`` ...)."""
    sent = {"done": False}

    def provider(day, session, ledger):
        if session == sess and day == at and not sent["done"]:
            sent["done"] = True
            return [row(symbol, 'buy', day, session, day, **kw)]
        return None
    return provider


def noop(day, session, ledger):
    return None


# ---------------------------------------------------------------------------
# t1: pm decision -> next-day pm live session on the real daily bar
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("live_low,fills", [(1.95, True), (2.005, False)])
def test_t1_pm_decision_matches_next_pm_on_the_daily_low(live_low, fills):
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),
        (D2, 2.00, 2.05, live_low, 2.01),
        (D3, 2.01, 2.06, 2.005, 2.05),
        (D4, 2.05, 2.07, 2.03, 2.06)])
    res = run_pm_only(once(target=10000.0), daily, EMPTY_HALF)
    assert res.fills.height == (1 if fills else 0)
    il = res.stats["intent_layer"]
    # the intent ticks at the pm decision point only and lives ONE half-day
    assert il["orders_generated"] == 1
    assert il["terminated_expired_halfday"] == 1
    if not fills:
        # strict penetration: the session low sits ABOVE the anchor (2.005 >
        # 2.00) and never fills (the low == anchor touch case is defended by
        # tests/test_band_contract.py::test_05_touch_penetrate)
        ev = res.events.filter(pl.col("event") == "not_penetrated")
        assert ev.height == 1 and ev["date"][0] == D2
        assert ev["session"][0] == "pm" and ev["ref_price"][0] == live_low
        return
    f = res.fills.row(0, named=True)
    # routing: pm decision on D1, live (D2, pm), matched on the REAL daily row
    assert (f["decision_date"], f["decision_session"]) == (D1, "pm")
    assert (f["date"], f["session"]) == (D2, "pm")
    # 10,000 CNY at the D1 official close 2.00 -> 5,000 shares (100-lot)
    assert f["shares"] == 5000 and f["price"] == 2.00
    assert f["notional"] == 10_000.0
    # fees: ETF -> commission max(1e-4 x notional, 5) = 5.0, no stamp either side
    assert f["commission"] == 5.0 and f["stamp_tax"] == 0.0
    assert f["fees_total"] == 5.0 and f["net_cash_flow"] == -10_005.0
    assert f["is_etf"] is True
    # the daily low of the live day is what decided the fill
    ev = res.events.filter(pl.col("event") == "filled_limit_buy")
    assert ev.height == 1 and ev["ref_price"][0] == live_low
    # nothing in this run depends on a half-day bar
    assert res.stats["etf_leg"]["routing"].startswith("halfday pm-only ETF")


def test_t1_am_decision_point_never_emits_an_etf_order_under_pm_only():
    """A real order is submitted at the first pm point; the am decision
    points must still carry nothing, and the order must live at the NEXT pm
    session.  (Independent review 2026-09-21: the earlier form of this test
    returned None everywhere, so its ``orders_generated == 0`` was
    unfalsifiable -- a regression that routed a pm-only ETF live session to
    an am session would have passed it.)"""
    daily = daily_frame(ETF, [(d, 2.0, 2.02, 1.95, 2.0) for d in (D1, D2)])
    seen: list = []
    submit = once(target=10_000.0)

    def provider(day, session, ledger):
        seen.append((day, session, len(ledger["positions"])))
        return submit(day, session, ledger)

    res = run_pm_only(provider, daily, EMPTY_HALF)
    # the provider is asked at EVERY decision point (ledger feedback); the
    # order exists only from the pm point on, and no am point emits one
    assert seen == [(D1, "am", 0), (D1, "pm", 0), (D2, "am", 0), (D2, "pm", 1)]
    assert res.stats["dynamic_layer"]["provider_calls"] == 4
    assert res.stats["intent_layer"]["orders_generated"] == 1
    assert res.fills.height == 1
    f = res.fills.row(0, named=True)
    assert (f["decision_date"], f["decision_session"]) == (D1, "pm")
    assert (f["date"], f["session"]) == (D2, "pm")
    # no event of any kind (fill or void) may carry a symbol in an am session
    am_events = res.events.filter((pl.col("session") == "am")
                                 & (pl.col("symbol") != ""))
    assert am_events.height == 0


# ---------------------------------------------------------------------------
# t2: an ETF am intent is rejected; a stock am intent still runs
# ---------------------------------------------------------------------------

def test_t2_etf_am_intents_rejected_both_entry_points():
    daily = daily_frame(ETF, [(d, 2.0, 2.02, 1.99, 2.0) for d in (D1, D2)])
    static = pl.DataFrame(
        [row(ETF, 'buy', D1, 'am', D1, target=10_000.0)],
        schema={'symbol': pl.String, 'side': pl.String, 'intent': pl.String,
                'decision_date': pl.Date, 'decision_session': pl.String,
                'source_signal': pl.Date, 'expiry_date': pl.Date,
                'priority': pl.Int64, 'target_notional': pl.Float64,
                'target_weight': pl.Float64})
    with pytest.raises(BandContractError, match="15:00 decision point"):
        run_pm_only(None, daily, EMPTY_HALF, intents=static)

    def bad_provider(day, session, ledger):
        return ([row(ETF, 'buy', day, session, day, target=10_000.0)]
                if session == "am" else None)

    with pytest.raises(BandContractError, match="15:00 decision point"):
        run_pm_only(bad_provider, daily, EMPTY_HALF)


def test_t2_stock_am_intent_still_runs_on_the_halfday_route():
    daily = pl.concat([
        daily_frame(ETF, [(d, 2.0, 2.02, 1.99, 2.0) for d in (D1, D2)]),
        daily_frame(STOCK, [(d, 10.0, 10.2, 9.8, 10.0) for d in (D1, D2)])])
    half = half_frame(STOCK, [
        (D1, "am", 10.0, 10.2, 9.9, 10.1),
        (D1, "pm", 10.1, 10.3, 9.95, 10.05),
        (D2, "am", 10.05, 10.1, 9.90, 10.0),
        (D2, "pm", 10.0, 10.2, 9.9, 10.1)])
    meta = {**etf_meta(), STOCK: {"asset_class": "stock"}}
    limits = daily.filter(pl.col("symbol") == STOCK).select(
        'symbol', 'date',
        (pl.col("close") * 1.1).alias("limit_up"),
        (pl.col("close") * 0.9).alias("limit_down"))
    res = run_pm_only(once(sess='am', target=10_000.0, symbol=STOCK), daily,
                      half, meta=meta, limits=limits)
    assert res.fills.height == 1
    f = res.fills.row(0, named=True)
    # section 7.1 stock route survives pm_only: am decision -> same-day pm,
    # matched on the stock's pm half-day bar (low 9.95 < anchor 10.10)
    assert (f["decision_session"], f["date"], f["session"]) == ("am", D1, "pm")
    assert f["price"] == 10.10 and f["shares"] == 900


# ---------------------------------------------------------------------------
# t3: am snapshot marks a pm-only ETF holding at the last traded close
# ---------------------------------------------------------------------------

def test_t3_am_snapshot_uses_last_traded_close():
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),      # pm decision anchor = 2.00
        (D2, 2.05, 2.12, 1.99, 2.10),      # fill 5,000 @ 2.00; close 2.10
        (D3, 2.11, 2.15, 2.08, 2.14),      # 11:30 mark = 2.10 (last traded)
        (D4, 2.14, 2.16, 2.10, 2.15)])
    ledgers: dict = {}

    def provider(day, session, ledger):
        ledgers[(day, session)] = ledger
        return ([row(ETF, 'buy', day, session, day, target=10_000.0)]
                if (day, session) == (D1, "pm") else None)

    res = run_pm_only(provider, daily, EMPTY_HALF)
    assert res.fills.height == 1
    # hand arithmetic: 200,000 - 10,000 - 5 = 189,995 settled cash
    cash = 189_995.0
    assert ledgers[(D3, "am")]["cash"] == cash
    # the am mark is the last TRADED close (D2's 2.10), not D3's close:
    # 189,995 + 5,000 x 2.10 = 200,495
    assert ledgers[(D3, "am")]["equity_snapshot"] == cash + 5000 * 2.10
    # the pm decision point marks the day's own official close
    assert ledgers[(D3, "pm")]["equity_snapshot"] == cash + 5000 * 2.14
    # ledger feedback shape: one clip acquired at the fill date, pm session
    pos = ledgers[(D3, "am")]["positions"][0]
    assert pos["symbol"] == ETF and pos["shares"] == 5000
    # ledger clips carry the per-clip fill price (host-side cost/R feedback;
    # added 2026-09-21 fixed-scheme prep -- clips_final frames unchanged)
    assert pos["clips"] == [{"shares": 5000, "acquired": D2.isoformat(),
                             "session": "pm", "price": 2.0}]
    assert pos["sellable_next_session"] == 5000


# ---------------------------------------------------------------------------
# t4: no ETF halfday bar required; the paired default still requires them
# ---------------------------------------------------------------------------

def test_t4_pm_only_needs_no_halfday_bars():
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00), (D2, 2.00, 2.05, 1.95, 2.01)])
    res = run_pm_only(once(target=10_000.0), daily, EMPTY_HALF)
    assert res.fills.height == 1
    assert res.stats["execution_clock"] == "halfday"
    assert res.stats["etf_leg"]["routing"].startswith("halfday pm-only ETF")
    assert res.stats["dynamic_layer"]["state_transition"].startswith(
        "halfday clock + pm-only ETF")


def test_t4_paired_default_and_mode_guards():
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00), (D2, 2.00, 2.05, 1.95, 2.01)])
    provider = once(target=10_000.0)
    # a non-empty half-day table that carries no ETF rows at all: the default
    # routing still requires the ETF am+pm pair (v1.4.2 behavior kept)
    other_half = half_frame(STOCK, [(D1, "pm", 1.0, 1.0, 1.0, 1.0)])
    with pytest.raises(BandContractError, match="requires ETF am and pm bars"):
        run_pm_only(provider, daily, other_half, routing="paired")
    with pytest.raises(BandContractError, match="etf_routing must be"):
        run_pm_only(provider, daily, EMPTY_HALF, routing="pm-only")
    with pytest.raises(BandContractError, match="halfday-clock ETF expression"):
        run_pm_only(provider, daily, EMPTY_HALF, clock="legacy")
    # a non-empty half-day table is still validated under pm_only
    bad = pl.DataFrame({
        'symbol': [STOCK], 'trade_date': [D1], 'session': ["pm"],
        'open': [1.0], 'high': [0.5], 'low': [1.2], 'close': [1.0]})
    with pytest.raises(BandContractError, match="high < low"):
        run_pm_only(provider, daily, bad)
