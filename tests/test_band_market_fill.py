"""Targeted tests: ``etf_market_fill`` (decision 2026-09-21-etf-market-fill).

An ETF config leg with etf_market_fill > 0 fills at the LIVE session's
close +/- slip instead of the strict-penetration gate.  Contract seams:

  m1  buy fills at close*(1+slip) even without penetration
  m2  sell fills at close*(1-slip)
  m3  default 0.0 keeps the strict-penetration caliber (same inputs as m1)
  m4  a close AT a day-limit edge stays unfilled (order expires)
  m5  parameter validation
  m6  quantity is computed at the fill price (not the decision anchor)

All frames inline synthetic; engineering only, zero trial consumption.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.backtest.band_engine import BandContractError, run_band_backtest_intents

D1, D2, D3, D4 = (date(2024, 1, 2 + i) for i in range(4))
ETF = 'sh.510300'
MK = 0.001
HALF_SCHEMA = {
    'symbol': pl.String, 'trade_date': pl.Date, 'session': pl.String,
    'open': pl.Float64, 'high': pl.Float64, 'low': pl.Float64,
    'close': pl.Float64}
EMPTY_HALF = pl.DataFrame(schema=HALF_SCHEMA)
EMPTY_LIMITS = pl.DataFrame(schema={
    'symbol': pl.String, 'date': pl.Date,
    'limit_up': pl.Float64, 'limit_down': pl.Float64})
EMPTY_INSTR = pl.DataFrame(schema={
    'symbol': pl.String, 'is_etf': pl.Boolean, 'is_t0': pl.Boolean})


def daily_frame(symbol, rows):
    closes = [float(r[4]) for r in rows]
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': closes,
        'preclose': [closes[0]] + closes[:-1],
        'tradestatus': [1.0] * len(rows)})


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


def once(*, at=D1, sess='pm', symbol=ETF, **kw):
    sent = {"done": False}

    def provider(day, session, ledger):
        if session == sess and day == at and not sent["done"]:
            sent["done"] = True
            return [row(symbol, 'buy', day, session, day, **kw)]
        return None
    return provider


def noop(day, session, ledger):
    return None


def run_mk(provider, daily, *, mk=MK, meta=None):
    return run_band_backtest_intents(
        None, daily, EMPTY_HALF, EMPTY_LIMITS,
        instruments=EMPTY_INSTR,
        symbol_meta=meta if meta is not None else etf_meta(),
        initial_cash=200_000.0, execution_clock="halfday",
        etf_routing="pm_only", intent_provider=provider,
        etf_market_fill=mk)


def test_m1_buy_fills_at_close_plus_slip_without_penetration():
    # D2 low 2.005 sits ABOVE the anchor 2.00: strict penetration would NOT
    # fill (see t1 parametrize); market mode fills at close*(1+slip).
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),
        (D2, 2.00, 2.05, 2.005, 2.01),
        (D3, 2.01, 2.06, 2.00, 2.05),
        (D4, 2.05, 2.07, 2.03, 2.06)])
    res = run_mk(once(target=10000.0), daily)
    f = res.fills
    assert f.height == 1 and f['side'][0] == 'buy'
    assert f['date'][0] == D2 and f['session'][0] == 'pm'
    assert abs(f['price'][0] - 2.012) < 1e-9      # tick(2.01 * 1.001)
    # m6: quantity at the FILL price: floor(10000/2.012/100)*100 = 4900
    assert f['shares'][0] == 4900
    ev = res.events.filter((pl.col('event') == 'filled_limit_buy'))
    assert 'market fill' in ev['detail'][0]


def test_m2_sell_fills_at_close_minus_slip():
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),
        (D2, 2.00, 2.05, 1.95, 2.01),
        (D3, 2.01, 2.06, 2.00, 2.05),
        (D4, 2.05, 2.07, 2.03, 2.06)])
    sent = {"n": 0}

    def provider(day, session, ledger):
        if session != 'pm':
            return None
        if day == D1 and sent["n"] == 0:
            sent["n"] = 1
            return [row(ETF, 'buy', day, session, day, target=10000.0)]
        if day == D2 and sent["n"] == 1 and ledger["positions"]:
            sent["n"] = 2
            return [row(ETF, 'sell', day, session, day, intent='risk')]
        return None

    res = run_mk(provider, daily)
    sells = res.fills.filter(pl.col('side') == 'sell')
    assert sells.height == 1
    # live D3 close 2.05 -> tick(2.05 * 0.999) = 2.048
    assert abs(sells['price'][0] - 2.048) < 1e-9
    assert sells['shares'][0] == 4900


def test_m3_default_keeps_strict_penetration_caliber():
    # identical inputs to m1 but WITHOUT etf_market_fill: no fill.
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),
        (D2, 2.00, 2.05, 2.005, 2.01),
        (D3, 2.01, 2.06, 2.00, 2.05),
        (D4, 2.05, 2.07, 2.03, 2.06)])
    res = run_mk(once(target=10000.0), daily, mk=0.0)
    assert res.fills.height == 0
    np_ = res.events.filter(pl.col('event') == 'not_penetrated')
    assert np_.height >= 1


def test_m4_close_at_limit_edge_stays_unfilled():
    # preclose 2.00, band 0.1 -> up 2.20: a D2 close AT the edge must not
    # fill; D3 (normal close 2.05) fills there.
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),
        (D2, 2.10, 2.20, 2.05, 2.20),
        (D3, 2.21, 2.25, 2.10, 2.05),
        (D4, 2.05, 2.07, 2.03, 2.06)])
    done = {"filled": False}

    def provider(day, session, ledger):
        if session != 'pm' or done["filled"]:
            return None
        if any(p["symbol"] == ETF for p in ledger["positions"]):
            done["filled"] = True
            return None
        return [row(ETF, 'buy', day, session, day, target=10000.0)]

    res = run_mk(provider, daily)
    f = res.fills
    assert f.height == 1 and f['date'][0] == D3
    skipped = res.events.filter(
        (pl.col('event') == 'not_penetrated')
        & (pl.col('date') == D2))
    assert skipped.height == 1
    assert 'day-limit edge' in skipped['detail'][0]


def test_m5_parameter_validation():
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.02, 1.99, 2.00),
        (D2, 2.00, 2.05, 1.95, 2.01),
        (D3, 2.01, 2.06, 2.00, 2.05),
        (D4, 2.05, 2.07, 2.03, 2.06)])
    for bad in (-0.001, 0.02, float('nan')):
        with pytest.raises(BandContractError):
            run_mk(noop, daily, mk=bad)
