"""P3 band-contract engine v1.2 ETF-leg acceptance tests (contract section 8).

Maps to docs/plans/p3-band-contract.md section 8 (TBD-A/B backfilled
2026-09-19) and section 8.6 scope freeze: the ONLY extensions are (1) ETF
pm-decision -> next-pm live routing and (2) computed ETF price limits /
cash-dividend events, plus per-symbol metadata via ``symbol_meta`` /
``dividend_events``.  Every v1.1 path is byte-identical when the new
optional frames are absent (test_h9).

The 29 prior tests (test_band_contract.py + test_band_intents.py) are
unchanged; this file adds only hybrid/ETF coverage.  All data inline
synthetic Polars frames; no strategy judgement; zero trial consumption.

  test_h1_pm_routing        etf pm decision lives next-day PM (vs stock
                            next-am); etf am decisions rejected
  test_h2_computed_limits   computed etf limits: 10%/20% bands, 0.001
                            half-up rounding incl. non-tick products
  test_h3_etf_fees          no stamp; commission min-5 binds / rate binds;
                            per-symbol fee overrides
  test_h4_dividend_events   dividend cash to settled cash; equity
                            invariance (total-return identity); meta gate
  test_h5_etf_suspension    no daily row -> intent frozen, K frozen,
                            re-hang at the next decision point
  test_h6_mixed_account     one ledger/equity curve; 25% single-name cap
                            voids an etf target-weight buy (whole order)
  test_h7_k3_fallback_pm    K=3 fallback executes at next PM open; opening
                            limit-down defer uses the COMPUTED limit
  test_h8_t_plus_zero       class-aware per-lot sellability (controlled
                            stock scenario); etf pm-only 0 == 1 equivalence
  test_h9_zero_regression   no-meta stock-only scenario is byte-identical
                            to the recorded v1.1 output (sha256 of CSV
                            serializations captured pre-change, run
                            20260919T044343-engine-v12-2632)

Adjudication delta (2026-09-19, second round; 12 further rulings accepted
as implemented -- see delivery.md section 7):
  test_h10_decimal_half_up  R1: exact-decimal band limits on half-tick
                            boundaries (1.705/3.415 cases) + a real
                            float-vs-decimal divergence case (0.565x0.9)
  test_h11_etf_stamp_buy    R3: etf meta stamp_buy forced 0 (both sides);
                            stock meta stamp_buy still charges
  test_h12_static_rejects   R12: the static signal entry hard-rejects
                            ETF-meta symbols
"""
from __future__ import annotations

import hashlib
import io
import math
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import polars as pl
import pytest

SRC = Path(__file__).resolve().parents[1] / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quant.backtest import band_engine as be  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    BandContractError,
    run_band_backtest_intents,
)

D = date
STOCK = 'sh.600001'
ETF = 'sh.510300'

INTENT_SCHEMA = {
    'symbol': pl.String, 'side': pl.String, 'intent': pl.String,
    'decision_date': pl.Date, 'decision_session': pl.String,
    'source_signal': pl.Date, 'expiry_date': pl.Date,
    'priority': pl.Int64, 'target_notional': pl.Float64,
    'target_weight': pl.Float64,
}


def it(symbol, side, first_date, first_session, source, *, intent=None,
       expiry=None, priority=1, target=None, weight=None):
    return {'symbol': symbol, 'side': side, 'intent': intent,
            'decision_date': first_date, 'decision_session': first_session,
            'source_signal': source, 'expiry_date': expiry,
            'priority': priority,
            'target_notional': None if target is None else float(target),
            'target_weight': None if weight is None else float(weight)}


def intents_frame(rows):
    return pl.DataFrame(rows, schema=INTENT_SCHEMA)


def mixed_daily(symbol, rows):
    """Official daily backbone with a preclose column.
    rows: (date, open, high, low, close, preclose)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'preclose': [float(r[5]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def half_bars(symbol, rows):
    """rows: (date, session, open, high, low, close)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows],
    })


def etf_pm_bars(symbol, daily):
    """Section 8.1: an ETF day synthesizes ONE pm session whose bar is the
    daily OHLC (no am session, no intraday-path assumption)."""
    return daily.select(
        pl.lit(symbol).alias('symbol'), pl.col('date').alias('trade_date'),
        pl.lit('pm').alias('session'), pl.col('open'), pl.col('high'),
        pl.col('low'), pl.col('close'))


def stock_limits(daily):
    """stk_limit rows for the STOCK symbols only (ETFs ignore stk_limit)."""
    return daily.filter(pl.col('symbol') != ETF).select(
        'symbol', 'date',
        (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'))


def run_h(intents, daily, half, limits, **kw):
    return run_band_backtest_intents(intents, daily, half, limits,
                                     initial_cash=kw.pop('initial_cash',
                                                         200_000.0), **kw)


def fills_of(res, **cols):
    f = res.fills
    for k, v in cols.items():
        f = f.filter(pl.col(k) == v)
    return f


def events_of(res, event):
    return res.events.filter(pl.col('event') == event)


def limits_from_void(detail):
    """Parse '[down, up]' out of a void_*_out_of_range detail string."""
    m = re.search(r'\[([0-9.]+), ([0-9.]+)\]', detail)
    assert m, detail
    return float(m.group(1)), float(m.group(2))


D1, D2, D3 = D(2024, 1, 2), D(2024, 1, 3), D(2024, 1, 4)
D4, D5, D6 = D(2024, 1, 5), D(2024, 1, 8), D(2024, 1, 9)
S1, S2 = D(2024, 1, 2), D(2024, 1, 3)


# ---------------------------------------------------------------------------
# h1: ETF 15:00 decision -> NEXT DAY PM session (stocks: next am, unchanged)
# ---------------------------------------------------------------------------

def test_h1_pm_routing():
    daily = pl.concat([
        mixed_daily(STOCK, [(D1, 10.0, 10.05, 9.9, 10.0, 10.0),
                            (D2, 10.0, 10.3, 9.9, 10.2, 10.0)]),
        mixed_daily(ETF, [(D1, 2.0, 2.01, 1.98, 2.0, 2.0),
                          (D2, 2.0, 2.02, 1.94, 1.98, 2.0)]),
    ])
    half = pl.concat([
        half_bars(STOCK, [(D1, 'pm', 10.0, 10.02, 9.98, 10.0),
                          (D2, 'am', 10.0, 10.25, 9.95, 10.2),
                          (D2, 'pm', 10.2, 10.28, 10.1, 10.2)]),
        etf_pm_bars(ETF, daily.filter(pl.col('symbol') == ETF)),
    ])
    res = run_h(intents_frame([
        it(STOCK, 'buy', D1, 'pm', S1, target=10_000),
        it(ETF, 'buy', D1, 'pm', S1, target=2_000)]),
        daily, half, stock_limits(daily),
        symbol_meta={ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 1}})
    # SAME (D1, pm) decision: the stock order lives NEXT am, the ETF order
    # lives NEXT PM (section 8.2; the ETF has no am session at all)
    sb = fills_of(res, symbol=STOCK).row(0, named=True)
    assert (sb['date'], sb['session'], sb['price'], sb['shares']) == \
        (D2, 'am', 10.0, 1000)
    eb = fills_of(res, symbol=ETF).row(0, named=True)
    assert (eb['date'], eb['session'], eb['price'], eb['shares']) == \
        (D2, 'pm', 2.0, 1000)
    assert (eb['decision_date'], eb['decision_session']) == (D1, 'pm')
    assert eb['is_etf']
    # the ETF leg never touches an am session
    assert res.events.filter((pl.col('symbol') == ETF)
                             & (pl.col('session') == 'am')).height == 0
    # an ETF intent may not carry an 11:30 decision at all (validation)
    with pytest.raises(BandContractError, match='15:00'):
        run_h(intents_frame([it(ETF, 'buy', D1, 'am', S1, target=2_000)]),
              daily, half, stock_limits(daily),
              symbol_meta={ETF: {'asset_class': 'etf'}})
    # unknown meta fields are rejected (fail-closed)
    with pytest.raises(BandContractError, match='unknown field'):
        run_h(intents_frame([it(ETF, 'buy', D1, 'pm', S1, target=2_000)]),
              daily, half, stock_limits(daily),
              symbol_meta={ETF: {'asset_class': 'etf', 'bands': 0.1}})


# ---------------------------------------------------------------------------
# h2: computed ETF price limits (TBD-A): round-half-up(preclose x
#     (1 +/- band), 0.001); 10%/20% bands; non-tick products
# ---------------------------------------------------------------------------

def test_h2_computed_limits():
    daily = pl.concat([
        # D1 close 2.00; D2 preclose 1.70 -> 10%: [1.53, 1.87], 20%: [1.36, 2.04]
        mixed_daily('E10', [(D1, 2.0, 2.01, 1.99, 2.0, 1.30),
                            (D2, 1.6, 1.61, 1.59, 1.6, 1.70)]),
        mixed_daily('E20', [(D1, 2.0, 2.01, 1.99, 2.0, 1.30),
                            (D2, 2.0, 2.02, 1.99, 2.0, 1.70),
                            (D3, 2.0, 2.01, 1.99, 2.0, 2.0)]),
        # non-tick products: 1.234x1.1 = 1.3574 -> 1.357 (down);
        # 1.234x0.9 = 1.1106 -> 1.111 (up)
        mixed_daily('ER', [(D1, 1.4, 1.41, 1.39, 1.4, 1.30),
                           (D2, 1.2, 1.21, 1.19, 1.2, 1.234)]),
    ])
    half = pl.concat([
        etf_pm_bars('E10', daily.filter(pl.col('symbol') == 'E10')),
        etf_pm_bars('E20', daily.filter(pl.col('symbol') == 'E20')),
        etf_pm_bars('ER', daily.filter(pl.col('symbol') == 'ER')),
    ])
    res = run_h(intents_frame([
        it('E10', 'buy', D1, 'pm', S1, target=2_000, expiry=D3),
        it('E20', 'buy', D1, 'pm', S1, target=2_000, expiry=D3),
        it('ER', 'buy', D1, 'pm', S1, target=2_000, expiry=D3)]),
        daily, half, stock_limits(daily),
        symbol_meta={'E10': {'asset_class': 'etf'},          # band defaults 10%
                     'E20': {'asset_class': 'etf', 'band': 0.20},
                     'ER': {'asset_class': 'etf', 'band': 0.10}})
    # E10: anchor (D1 close) 2.00 > up 1.87 -> whole order voided; the void
    # discloses the computed pair (E10 had no band -> default 0.10)
    v10 = events_of(res, 'void_limit_out_of_range').filter(
        pl.col('symbol') == 'E10').row(0, named=True)
    down, up = limits_from_void(v10['detail'])
    assert down == pytest.approx(1.53, abs=1e-9)   # 1.70 x 0.90 = 1.530
    assert up == pytest.approx(1.87, abs=1e-9)     # 1.70 x 1.10 = 1.870
    # E20: the SAME prices under a 20% band: 2.00 <= up 2.04 -> fills
    b20 = fills_of(res, symbol='E20').row(0, named=True)
    assert (b20['date'], b20['session'], b20['price'], b20['shares']) == \
        (D2, 'pm', 2.0, 1000)
    # ER: non-tick products round HALF-UP to the 0.001 tick, both directions
    vr = events_of(res, 'void_limit_out_of_range').filter(
        pl.col('symbol') == 'ER').row(0, named=True)
    down, up = limits_from_void(vr['detail'])
    assert down == pytest.approx(1.111, abs=1e-9)  # 1.234 x 0.9 = 1.1106
    assert up == pytest.approx(1.357, abs=1e-9)    # 1.234 x 1.1 = 1.3574
    # direct half-up helper checks (incl. the exact 4th-decimal cases)
    assert be._tick_round(1.234 * 1.1, be.ETF_PRICE_TICK) == pytest.approx(1.357, abs=1e-12)
    assert be._tick_round(1.234 * 0.9, be.ETF_PRICE_TICK) == pytest.approx(1.111, abs=1e-12)
    assert be._tick_round(1.70 * 1.2, be.ETF_PRICE_TICK) == pytest.approx(2.04, abs=1e-12)
    assert be._tick_round(1.70 * 0.8, be.ETF_PRICE_TICK) == pytest.approx(1.36, abs=1e-12)
    leg = res.stats['etf_leg']
    assert leg['etf_default_band_symbols'] == ['E10']
    assert leg['etf_bands'] == {'E10': 0.10, 'E20': 0.20, 'ER': 0.10}


# ---------------------------------------------------------------------------
# h3: ETF fees (section 8.3): stamp-free; commission max(wan1 x notional, 5);
#     per-symbol overrides
# ---------------------------------------------------------------------------

def test_h3_etf_fees():
    daily = mixed_daily(ETF, [(D1, 2.0, 2.01, 1.99, 2.0, 2.0),
                              (D2, 2.0, 2.02, 1.97, 2.0, 2.0)])
    half = etf_pm_bars(ETF, daily)
    meta = {ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 1}}

    # (a) 10,000 notional: rate leg 1.0 -> the 5-yuan minimum binds
    res = run_h(intents_frame([it(ETF, 'buy', D1, 'pm', S1, target=10_000)]),
                daily, half, stock_limits(daily), symbol_meta=meta)
    f = res.fills.row(0, named=True)
    assert (f['shares'], f['price'], f['notional']) == (5000, 2.0, 10_000.0)
    assert f['commission'] == pytest.approx(max(1e-4 * 10_000, 5.0))  # 5.0
    assert f['stamp_tax'] == 0.0 and f['is_etf']
    assert f['fees_total'] == pytest.approx(5.0)
    assert f['net_cash_flow'] == pytest.approx(-10_005.0)

    # (b) 100,000 notional (400k account: 25% cap satisfied): rate binds
    res = run_h(intents_frame([it(ETF, 'buy', D1, 'pm', S1, target=100_000)]),
                daily, half, stock_limits(daily), symbol_meta=meta,
                initial_cash=400_000.0)
    f = res.fills.row(0, named=True)
    assert (f['shares'], f['notional']) == (50_000, 100_000.0)
    assert f['commission'] == pytest.approx(max(1e-4 * 100_000, 5.0))  # 10.0
    assert f['stamp_tax'] == 0.0
    assert f['net_cash_flow'] == pytest.approx(-100_010.0)
    assert res.stats['commission_warnings'] == 1   # >50k guard disclosed

    # (c) per-symbol fee override: rate wan2, min 1 -> 10,000 x 2e-4 = 2.0
    res = run_h(intents_frame([it(ETF, 'buy', D1, 'pm', S1, target=10_000)]),
                daily, half, stock_limits(daily),
                symbol_meta={ETF: {'asset_class': 'etf',
                                   'commission_rate': 2e-4,
                                   'commission_min': 1.0}})
    f = res.fills.row(0, named=True)
    assert f['commission'] == pytest.approx(2.0)
    assert f['stamp_tax'] == 0.0


# ---------------------------------------------------------------------------
# h4: dividend_events -> settled cash; equity invariance; meta gate
# ---------------------------------------------------------------------------

def test_h4_dividend_events():
    daily = mixed_daily(ETF, [(D1, 2.0, 2.01, 1.99, 2.0, 2.0),
                              (D2, 2.0, 2.01, 1.99, 2.0, 2.0),
                              # ex-div: preclose 1.95 = 2.00 - 0.05; raw close 1.97
                              (D3, 1.97, 1.98, 1.96, 1.97, 1.95),
                              (D4, 1.97, 1.98, 1.96, 1.97, 1.97)])
    half = etf_pm_bars(ETF, daily)
    meta = {ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 1}}
    intents = intents_frame([it(ETF, 'buy', D1, 'pm', S1, target=2_000)])
    divs = {'symbol': [ETF, 'sh.999999'], 'date': [D3, D3],
            'div_per_share': [0.05, 1.00]}       # ghost symbol not in meta

    res = run_h(intents, daily, half, stock_limits(daily), symbol_meta=meta,
                dividend_events=divs)
    assert fills_of(res).height == 1             # buy filled D2 pm @2.00
    dv = events_of(res, 'corp_action_dividend')
    assert dv.height == 1                        # ghost event ignored
    assert dv['detail'][0].startswith(ETF)       # symbol lives in the detail
    assert dv['cash_amount'][0] == pytest.approx(1000 * 0.05)     # 50.0
    d2 = res.daily.filter(pl.col('date') == D2).row(0, named=True)
    d3 = res.daily.filter(pl.col('date') == D3).row(0, named=True)
    # hand-calc: cash 200,000 - 2,005 = 197,995; +50 dividend = 198,045;
    # positions 1000 x 1.97 = 1,970; equity 200,015
    assert d2['settled_cash'] == pytest.approx(197_995.0)
    assert d2['equity'] == pytest.approx(199_995.0)
    assert d3['settled_cash'] == pytest.approx(198_045.0)
    assert d3['positions_value'] == pytest.approx(1_970.0, abs=1e-6)
    assert d3['equity'] == pytest.approx(200_015.0, abs=1e-6)
    # invariance: the position's WEALTH (marks + received dividend cash)
    # moves ONLY by the total return (1.97 + 0.05) / 2.00 - 1 = +1%:
    # 2,000 x 1.01 = 2,020 = 1,970 price part + 50 cash part; the dividend
    # bridges the ex-drop exactly, marks and clip costs are raw
    tr = (1.97 + 0.05) / 2.00 - 1.0
    assert d3['positions_value'] + 50.0 == pytest.approx(
        d2['positions_value'] * (1.0 + tr), abs=1e-6)
    assert d3['equity'] - d2['equity'] == pytest.approx(
        1000 * (1.97 - 2.00) + 50.0, abs=1e-6)
    # valuation uses RAW prices; clip cost/shares untouched
    cf = res.clips_final.row(0, named=True)
    assert (cf['shares'], cf['last_close']) == (1000, pytest.approx(1.97))
    # same run WITHOUT the events frame: identical except exactly the 50 yuan
    res0 = run_h(intents, daily, half, stock_limits(daily), symbol_meta=meta)
    d30 = res0.daily.filter(pl.col('date') == D3).row(0, named=True)
    assert d30['settled_cash'] == pytest.approx(197_995.0)
    assert d3['equity'] - d30['equity'] == pytest.approx(50.0, abs=1e-9)
    assert res.stats['etf_leg']['dividend_events_cash'] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# h5: ETF suspension (no daily row): intent frozen, K frozen, re-hang
# ---------------------------------------------------------------------------

def test_h5_etf_suspension():
    # the stock trades every day and only anchors the market calendar (it
    # has no orders): the ETF's suspension day must REMAIN a calendar day
    # for the freeze semantics to be exercised (mixed panel = production case)
    cal = [(D1, 10.0, 10.05, 9.95, 10.0, 10.0),
           (D2, 10.0, 10.05, 9.95, 10.0, 10.0),
           (D3, 10.0, 10.05, 9.95, 10.0, 10.0),
           (D4, 10.0, 10.05, 9.95, 10.0, 10.0),
           (D5, 10.0, 10.05, 9.95, 10.0, 10.0),
           (D6, 10.0, 10.05, 9.95, 10.0, 10.0)]
    daily = pl.concat([
        mixed_daily(STOCK, cal),
        mixed_daily(ETF, [
            (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
            (D2, 2.0, 2.01, 1.95, 2.0, 2.0),
            # D3 suspended: NO etf daily row / pm bar
            (D4, 2.0, 2.0, 1.99, 2.0, 2.0),
            (D5, 1.99, 2.0, 1.98, 2.0, 2.0),
            (D6, 2.0, 2.05, 1.99, 2.03, 2.0)]),
    ])
    half = pl.concat([
        etf_pm_bars(ETF, daily.filter(pl.col('symbol') == ETF)),
    ])
    res = run_h(intents_frame([
        it(ETF, 'buy', D1, 'pm', S1, target=2_000),
        it(ETF, 'sell', D2, 'pm', S2, intent='risk')]),
        daily, half, stock_limits(daily),
        symbol_meta={ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 1}})
    assert fills_of(res, side='buy').height == 1   # D2 pm @2.00
    assert fills_of(res, symbol=STOCK).height == 0
    # suspension: the live sell voids for that session, streak FROZEN
    sus = events_of(res, 'void_suspended').row(0, named=True)
    assert (sus['date'], sus['session']) == (D3, 'pm')
    assert 'K streak frozen' in sus['detail']
    # no anchor at the suspended decision point -> intent stays active
    assert res.stats['intent_layer']['emissions_skipped_no_anchor'] >= 1
    # resumption re-hangs at the NEXT decision point (D4 pm -> live D5 pm);
    # the first unfilled session after resumption reports streak 1 (the
    # suspended day did NOT count)
    np_ev = events_of(res, 'not_penetrated').row(0, named=True)
    assert (np_ev['date'], np_ev['session']) == (D5, 'pm')
    assert 'risk K streak 1' in np_ev['detail']
    # then fills at the D6 pm session (high 2.05 > 2.00) at the limit
    sf = fills_of(res, side='sell').row(0, named=True)
    assert (sf['date'], sf['session'], sf['price'], sf['shares']) == \
        (D6, 'pm', 2.0, 1000)
    assert res.events.filter((pl.col('symbol') == ETF)
                             & (pl.col('session') == 'am')).height == 0
    # hand-calc: 200,000 - 2,005 + 1,995 pending = 199,990 equity
    assert res.daily['equity'][-1] == pytest.approx(199_990.0)


# ---------------------------------------------------------------------------
# h6: mixed account: one ledger / one equity curve; 25% cap binds ETF
#     target-weight buys (whole-order void, intent terminated)
# ---------------------------------------------------------------------------

def test_h6_mixed_account():
    flat = [(D1, 10.0, 10.05, 9.95, 10.0, 10.0),
            (D2, 10.0, 10.05, 9.95, 10.0, 10.0),
            (D3, 10.0, 10.05, 9.95, 10.0, 10.0)]
    daily = pl.concat([
        mixed_daily(STOCK, flat),
        mixed_daily('E', [(D1, 2.0, 2.01, 1.98, 2.0, 2.0),
                          (D2, 2.0, 2.01, 1.98, 2.0, 2.0),
                          (D3, 2.0, 2.01, 1.98, 2.0, 2.0)]),
        mixed_daily('E3', [(D1, 2.0, 2.01, 1.98, 2.0, 2.0),
                           (D2, 2.0, 2.01, 1.98, 2.0, 2.0),
                           (D3, 2.0, 2.01, 1.98, 2.0, 2.0)]),
    ])
    half = pl.concat([
        half_bars(STOCK, [(D2, 'am', 10.0, 10.02, 9.98, 10.0),
                          (D2, 'pm', 10.0, 10.03, 9.98, 10.0),
                          (D3, 'am', 10.0, 10.02, 9.98, 10.0),
                          (D3, 'pm', 10.0, 10.03, 9.98, 10.0)]),
        etf_pm_bars('E', daily.filter(pl.col('symbol') == 'E')),
        etf_pm_bars('E3', daily.filter(pl.col('symbol') == 'E3')),
    ])
    res = run_h(intents_frame([
        it(STOCK, 'buy', D1, 'pm', S1, target=10_000),
        it('E', 'buy', D1, 'pm', S1, weight=0.20),
        it('E3', 'buy', D1, 'pm', S1, weight=0.30)]),
        daily, half, stock_limits(daily),
        symbol_meta={'E': {'asset_class': 'etf'},
                     'E3': {'asset_class': 'etf'}})
    # both legs fill in ONE ledger: stock D2 am, ETF D2 pm
    sb = fills_of(res, symbol=STOCK).row(0, named=True)
    assert (sb['date'], sb['session'], sb['shares'], sb['is_etf']) == \
        (D2, 'am', 1000, False)
    eb = fills_of(res, symbol='E').row(0, named=True)
    # weight sizing x decision-point snapshot (200k x 20% = 40k -> 20,000 sh)
    assert (eb['date'], eb['session'], eb['shares'], eb['is_etf']) == \
        (D2, 'pm', 20_000, True)
    assert fills_of(res, symbol='E3').height == 0
    # 30% weight -> cost 60,000 > 25% x 200,000 -> WHOLE order voided,
    # intent terminated (M2)
    v = events_of(res, 'void_cap_single_name').row(0, named=True)
    assert v['symbol'] == 'E3'
    assert res.stats['caps']['single_name_voids'] == 1
    assert res.stats['intent_layer']['terminated_cap'] == 1
    # mixed-valuation equity: cash + stock x official close + etf x official
    d3 = res.daily.filter(pl.col('date') == D3).row(0, named=True)
    assert d3['settled_cash'] == pytest.approx(200_000.0 - 10_005.0 - 40_005.0)
    assert d3['positions_value'] == pytest.approx(
        1000 * 10.0 + 20_000 * 2.0, abs=1e-9)
    assert d3['equity'] == pytest.approx(199_990.0, abs=1e-6)
    assert d3['n_positions'] == 2


# ---------------------------------------------------------------------------
# h7: K=3 fallback executes at the next PM session open; the opening
#     limit-down defer uses the COMPUTED limit (m5 via TBD-A)
# ---------------------------------------------------------------------------

def test_h7_k3_fallback_pm():
    days = [D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9, 10)]  # D0..D6
    daily = mixed_daily(ETF, [
        (days[0], 10.0, 10.02, 9.95, 10.0, 10.0),
        (days[1], 9.8, 9.8, 9.4, 9.6, 10.0),
        (days[2], 9.0, 9.2, 8.9, 9.0, 9.6),
        (days[3], 8.4, 8.6, 8.3, 8.4, 9.0),
        (days[4], 8.1, 8.3, 8.0, 8.1, 8.4),
        (days[5], 7.29, 7.29, 7.15, 7.20, 8.1),   # opens at computed limit-down
        (days[6], 6.60, 6.70, 6.55, 6.60, 7.20)])  # open 6.60 > down 6.48
    half = etf_pm_bars(ETF, daily)
    res = run_h(intents_frame([
        it(ETF, 'buy', days[0], 'pm', S1, target=10_000),
        it(ETF, 'sell', days[1], 'pm', S2, intent='risk')]),
        daily, half, stock_limits(daily),
        symbol_meta={ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 1}})
    assert fills_of(res, side='buy').row(0, named=True)['session'] == 'pm'
    # streak counts PM sessions only: D2, D3, D4 pm -> 1, 2, 3 (armed)
    np_ev = events_of(res, 'not_penetrated').sort('date')
    assert [(r['date'], r['session']) for r in np_ev.iter_rows(named=True)] == \
        [(days[2], 'pm'), (days[3], 'pm'), (days[4], 'pm'), (days[5], 'pm')]
    assert ['streak 1' in d for d in np_ev['detail'].to_list()] == \
        [True, False, False, False]
    assert 'streak 4' in np_ev['detail'][-1]
    # D5 pm opens at the computed limit-down 7.29 (= 8.10 x 0.9) -> deferred
    def_ev = events_of(res, 'market_exit_deferred_limitdown').row(0, named=True)
    assert (def_ev['date'], def_ev['session']) == (days[5], 'pm')
    assert '7.2900' in def_ev['detail']       # computed down, m5
    # D6 pm: fallback executes at the PM OPEN (6.60), unconditionally
    fb = fills_of(res, fill_type='market_fallback').row(0, named=True)
    assert (fb['date'], fb['session'], fb['price'], fb['shares']) == \
        (days[6], 'pm', 6.60, 1000)
    # net = 6,600 - 5 commission - 0 stamp; pnl vs prev close 7.20
    assert fb['net_cash_flow'] == pytest.approx(6_595.0)
    assert res.stats['k3_fallback']['pnl_contribution_total'] == \
        pytest.approx(6_595.0 - 1000 * 7.20)
    k3 = res.stats['k3_fallback']
    assert (k3['armed'], k3['executed'],
            k3['deferred_limitdown_sessions']) == (1, 1, 1)
    # pm-only routing end to end: the armed fallback never attempts an am
    assert res.events.filter((pl.col('symbol') == ETF)
                             & (pl.col('session') == 'am')).height == 0


# ---------------------------------------------------------------------------
# h8: class-aware per-lot T+0 sellability (controlled scenario) + the
#     ETF pm-only 0 == 1 observational equivalence
# ---------------------------------------------------------------------------

def test_h8_t_plus_zero():
    daily = pl.concat([
        mixed_daily(STOCK, [(D1, 10.0, 10.05, 9.9, 10.0, 10.0),
                            (D2, 10.0, 10.5, 9.95, 10.3, 10.0),
                            (D3, 10.4, 10.6, 10.3, 10.5, 10.3)]),
    ])
    half = half_bars(STOCK, [
        (D2, 'am', 10.0, 10.3, 9.95, 10.2),
        (D2, 'pm', 10.25, 10.5, 10.15, 10.3),
        (D3, 'am', 10.4, 10.6, 10.35, 10.5),
        (D3, 'pm', 10.5, 10.55, 10.4, 10.5)])
    intents = intents_frame([
        it(STOCK, 'buy', D1, 'pm', S1, target=10_000),      # fills D2 am
        it(STOCK, 'sell', D2, 'am', S2, intent='risk')])    # lives D2 pm
    # t_plus=0: the D2-am clip is sellable at D2 pm -> SAME-DAY round trip
    res0 = run_h(intents, daily, half, stock_limits(daily),
                 symbol_meta={STOCK: {'asset_class': 'stock', 't_plus': 0}})
    rows0 = [(r['date'], r['session'], r['side'], r['shares'], r['price'])
             for r in res0.fills.sort('fill_id').iter_rows(named=True)]
    assert rows0 == [(D2, 'am', 'buy', 1000, 10.0),
                     (D2, 'pm', 'sell', 1000, 10.2)]
    # t_plus=1 (explicit): same-day sell locked -> void_t1_locked; the
    # re-issued sell fills the NEXT session (D3 am)
    res1 = run_h(intents, daily, half, stock_limits(daily),
                 symbol_meta={STOCK: {'asset_class': 'stock', 't_plus': 1}})
    rows1 = [(r['date'], r['session'], r['side'], r['shares'], r['price'])
             for r in res1.fills.sort('fill_id').iter_rows(named=True)]
    assert rows1 == [(D2, 'am', 'buy', 1000, 10.0),
                     (D3, 'am', 'sell', 1000, 10.3)]
    lock = events_of(res1, 'void_t1_locked').row(0, named=True)
    assert (lock['date'], lock['session']) == (D2, 'pm')

    # ETF pm-only rhythm: an ETF clip is created in the LAST session of the
    # day, so no later same-day session exists and t_plus 0 vs 1 are
    # observationally identical (the flag difference is unobservable here)
    etf_daily = mixed_daily(ETF, [(D1, 2.0, 2.01, 1.99, 2.0, 2.0),
                                  (D2, 2.0, 2.01, 1.98, 2.0, 2.0),
                                  (D3, 2.0, 2.02, 1.99, 2.0, 2.0)])
    etf_half = etf_pm_bars(ETF, etf_daily)
    etf_intents = intents_frame([
        it(ETF, 'buy', D1, 'pm', S1, target=2_000),
        it(ETF, 'sell', D2, 'pm', S2, intent='risk')])
    e0 = run_h(etf_intents, etf_daily, etf_half, stock_limits(etf_daily),
               symbol_meta={ETF: {'asset_class': 'etf', 'band': 0.10,
                                  't_plus': 0}})
    e1 = run_h(etf_intents, etf_daily, etf_half, stock_limits(etf_daily),
               symbol_meta={ETF: {'asset_class': 'etf', 'band': 0.10,
                                  't_plus': 1}})
    assert e0.fills.equals(e1.fills)
    assert e0.events.equals(e1.events)
    assert e0.daily.equals(e1.daily)
    assert fills_of(e0, side='sell').row(0, named=True)['session'] == 'pm'


# ---------------------------------------------------------------------------
# h9: zero regression -- no meta / no events, stock-only scenario is
#     byte-identical to the v1.1 engine (golden captured pre-change)
# ---------------------------------------------------------------------------

H9_FILLS_SHA = 'ab6cd52d3ea9939849cb9ccffa56c236148f4658e287c8a602733d795a426af2'
H9_EVENTS_SHA = '9a9f7c87667707b744a649a52ebe92589cbaaafef14c6936bc81fdfb3da05482'
H9_DAILY_SHA = 'e6dde4e3e6d2243a918bf234133a6b1c0e78968f240a1afaa0b0d5de79e94714'
H9_CLIPS_SHA = '036c596489022bd907d78f3674280aa106f9435541d31a83cc46c6c293f95b0a'


def _csv_sha(frame):
    buf = io.BytesIO()
    frame.write_csv(buf)
    return hashlib.sha256(buf.getvalue()).hexdigest()


def test_h9_zero_regression():
    """The v1.2 refactor must leave every no-meta path byte-identical.
    Golden = v1.1 engine output on this fixed scenario, captured before the
    edit (artifacts/runs/20260919T044343-engine-v12-2632/h9_golden*.csv)."""
    daily = pl.DataFrame({
        'symbol': [STOCK] * 6, 'date': [D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9)],
        'open': [10.0, 9.4, 8.9, 8.5, 8.5, 8.5],
        'high': [10.1, 9.5, 9.0, 8.55, 8.52, 8.52],
        'low': [9.5, 9.0, 8.55, 8.4, 8.48, 8.48],
        'close': [9.6, 9.1, 8.6, 8.5, 8.5, 8.5],
        'tradestatus': [1.0] * 6})
    half = pl.DataFrame({
        'symbol': [STOCK] * 12,
        'trade_date': [D(2024, 1, d) for d in (2, 2, 3, 3, 4, 4, 5, 5, 8, 8, 9, 9)],
        'session': ['am', 'pm'] * 6,
        'open': [10.0, 9.9, 9.4, 9.2, 8.9, 8.7, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5],
        'high': [10.05, 10.0, 9.5, 9.25, 9.0, 8.7, 8.55, 8.55, 8.52, 8.51,
                 8.52, 8.51],
        'low': [9.9, 9.5, 9.2, 9.0, 8.7, 8.55, 8.45, 8.4, 8.48, 8.49, 8.48,
                8.49],
        'close': [10.0, 9.6, 9.3, 9.1, 8.75, 8.6, 8.5, 8.5, 8.5, 8.5, 8.5,
                  8.5]})
    limits = daily.select(
        'symbol', 'date', (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'))
    intents = pl.DataFrame([
        it(STOCK, 'buy', D(2024, 1, 2), 'am', D(2024, 1, 2), target=10_000),
        it(STOCK, 'sell', D(2024, 1, 3), 'am', D(2024, 1, 3),
           intent='risk')], schema=INTENT_SCHEMA)
    res = run_band_backtest_intents(intents, daily, half, limits,
                                    initial_cash=200_000.0)
    assert _csv_sha(res.fills) == H9_FILLS_SHA
    assert _csv_sha(res.events) == H9_EVENTS_SHA
    assert _csv_sha(res.daily) == H9_DAILY_SHA
    assert _csv_sha(res.clips_final) == H9_CLIPS_SHA
    # readable spot rows from the golden fills (buy D2... = D1 pm fill,
    # then the K=3 market fallback at D5 am open)
    f = res.fills.sort('fill_id').to_dicts()
    assert (f[0]['side'], f[0]['date'], f[0]['session'], f[0]['shares'],
            f[0]['price'], f[0]['commission'], f[0]['stamp_tax'],
            f[0]['net_cash_flow']) == \
        ('buy', D(2024, 1, 2), 'pm', 1000, 10.0, 5.0, 0.0, -10_005.0)
    assert (f[1]['side'], f[1]['intent'], f[1]['fill_type'], f[1]['date'],
            f[1]['session'], f[1]['shares'], f[1]['price'],
            f[1]['net_cash_flow']) == \
        ('sell', 'risk', 'market_fallback', D(2024, 1, 5), 'am', 1000, 8.5,
         8_490.75)
    assert res.daily['equity'][-1] == pytest.approx(198_485.75)


# ---------------------------------------------------------------------------
# h10 (R1): decimal-EXACT half-up band limits on half-tick boundaries
# ---------------------------------------------------------------------------

def test_h10_decimal_half_up():
    # required boundary cases (exact decimal products end in 5 at the 4th
    # decimal): 1.705x1.1=1.8755 -> 1.876; 3.415x0.9=3.0735 -> 3.074
    assert be._etf_band_limit(1.705, 0.10, up=True) == 1.876
    assert be._etf_band_limit(1.705, 0.10, up=False) == 1.535   # 1.5345
    assert be._etf_band_limit(3.415, 0.10, up=True) == 3.757    # 3.7565
    assert be._etf_band_limit(3.415, 0.10, up=False) == 3.074
    # a REAL divergence: 0.565x0.9 = 0.5085 exact -> 0.509, while the legacy
    # float product path (floor(x*1000+0.5)/1000) lands 0.508 -- the danger
    # R1 removes
    legacy = math.floor(0.565 * (1 - 0.1) * 1000 + 0.5) / 1000
    assert legacy == 0.508
    assert be._etf_band_limit(0.565, 0.10, up=False) == 0.509
    # behavioral: the engine limit path uses the exact-decimal helper; a
    # panel with the dangerous preclose 1.705 shows [1.535, 1.876]
    daily = pl.concat([
        mixed_daily('EB', [(D1, 2.0, 2.01, 1.99, 2.0, 1.705),
                           (D2, 1.7, 1.71, 1.69, 1.7, 1.705),
                           (D3, 1.7, 1.71, 1.69, 1.7, 1.7)]),
    ])
    half = etf_pm_bars('EB', daily)
    res = run_h(intents_frame([
        it('EB', 'buy', D1, 'pm', S1, target=2_000, expiry=D3)]),
        daily, half, stock_limits(daily),
        symbol_meta={'EB': {'asset_class': 'etf', 'band': 0.10}})
    v = events_of(res, 'void_limit_out_of_range').row(0, named=True)
    down, up = limits_from_void(v['detail'])
    assert down == pytest.approx(1.535, abs=1e-12)   # 1.705 x 0.9
    assert up == pytest.approx(1.876, abs=1e-12)     # 1.705 x 1.1


# ---------------------------------------------------------------------------
# h11 (R3): ETF stamp exemption covers BOTH sides (meta stamp_buy forced 0)
# ---------------------------------------------------------------------------

def test_h11_etf_stamp_buy():
    daily = pl.concat([
        mixed_daily(ETF, [(D1, 2.0, 2.01, 1.99, 2.0, 2.0),
                          (D2, 2.0, 2.02, 1.97, 2.0, 2.0)]),
        mixed_daily(STOCK, [(D1, 10.0, 10.05, 9.9, 10.0, 10.0),
                            (D2, 10.0, 10.2, 9.95, 10.0, 10.0)]),
    ])
    half = pl.concat([
        etf_pm_bars(ETF, daily.filter(pl.col('symbol') == ETF)),
        half_bars(STOCK, [(D2, 'am', 10.0, 10.05, 9.95, 10.0)]),
    ])
    intents = intents_frame([
        it(ETF, 'buy', D1, 'pm', S1, target=10_000),
        it(STOCK, 'buy', D1, 'pm', S1, target=10_000)])
    # etf meta with a stamp_buy override: still 0 (contract precedence, R3)
    res = run_h(intents, daily, half, stock_limits(daily),
                symbol_meta={ETF: {'asset_class': 'etf', 'band': 0.10,
                                   'stamp_buy': 0.001}})
    ef = fills_of(res, symbol=ETF).row(0, named=True)
    assert (ef['shares'], ef['notional']) == (5000, 10_000.0)
    assert ef['stamp_tax'] == 0.0                           # forced exempt
    assert ef['commission'] == pytest.approx(5.0)
    assert ef['net_cash_flow'] == pytest.approx(-10_005.0)  # no stamp term
    # stock meta stamp_buy override still charges (the gate is etf-specific)
    res2 = run_h(intents, daily, half, stock_limits(daily),
                 symbol_meta={STOCK: {'asset_class': 'stock',
                                      'stamp_buy': 0.001}})
    sf = fills_of(res2, symbol=STOCK).row(0, named=True)
    assert sf['stamp_tax'] == pytest.approx(0.001 * 10_000.0)   # 10.0
    assert sf['net_cash_flow'] == pytest.approx(-(10_000.0 + 5.0 + 10.0))


# ---------------------------------------------------------------------------
# h12 (R12): the static signal entry hard-rejects ETF-meta symbols
# ---------------------------------------------------------------------------

def test_h12_static_rejects_etf_meta():
    SIGNAL_SCHEMA = {
        'symbol': pl.String, 'decision_date': pl.Date,
        'decision_session': pl.String, 'side': pl.String, 'intent': pl.String,
        'anchor_price': pl.Float64, 'priority': pl.Int64,
        'target_notional': pl.Float64, 'shares': pl.Int64,
    }
    etf_sig = pl.DataFrame([
        {'symbol': ETF, 'decision_date': D1, 'decision_session': 'pm',
         'side': 'buy', 'intent': None, 'anchor_price': 2.0, 'priority': 1,
         'target_notional': 2_000.0, 'shares': None}], schema=SIGNAL_SCHEMA)
    stock_sig = pl.DataFrame([
        {'symbol': STOCK, 'decision_date': D1, 'decision_session': 'pm',
         'side': 'buy', 'intent': None, 'anchor_price': 10.0, 'priority': 1,
         'target_notional': 10_000.0, 'shares': None}], schema=SIGNAL_SCHEMA)
    etf_daily = mixed_daily(ETF, [(D1, 2.0, 2.01, 1.99, 2.0, 2.0),
                                  (D2, 2.0, 2.01, 1.99, 2.0, 2.0)])
    etf_half = etf_pm_bars(ETF, etf_daily)
    meta = {ETF: {'asset_class': 'etf', 'band': 0.10}}
    # (a) etf-meta symbol itself signaled through the static entry
    with pytest.raises(BandContractError, match='static signal path'):
        be.run_band_backtest(etf_sig, etf_daily, etf_half,
                             stock_limits(etf_daily), symbol_meta=meta)
    # (b) etf-meta symbol only in the daily PANEL, signals for a stock:
    #     still rejected (no half-supported ETF legs on the static path)
    daily = pl.concat([
        etf_daily,
        mixed_daily(STOCK, [(D1, 10.0, 10.05, 9.9, 10.0, 10.0),
                            (D2, 10.0, 10.2, 9.95, 10.0, 10.0)]),
    ])
    half = pl.concat([etf_half,
                      half_bars(STOCK, [(D2, 'am', 10.0, 10.05, 9.95, 10.0)])])
    with pytest.raises(BandContractError, match='static signal path') as ei:
        be.run_band_backtest(stock_sig, daily, half, stock_limits(daily),
                             symbol_meta=meta)
    assert ETF in str(ei.value)
    # control: the SAME static run without the meta table keeps working
    ok = be.run_band_backtest(stock_sig, daily, half, stock_limits(daily))
    assert fills_of(ok, symbol=STOCK).height == 1
