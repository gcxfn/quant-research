"""P3 band-contract engine v1.4 zones-mode acceptance tests.

Maps to docs/plans/p3-band-contract.md section 10 (frozen v1.4 task:
ladder_buy / take_profit / stop_sell / seat recycling / gate-8 v1.4) and
the BR-1..BR-12 interface rulings in the run
20260919T222634-engine-v14-impl brief.  Every scenario is a synthetic
daily + half-day panel with HAND-CALCULATED expectations written next to
the asserts (sigma0 = 1.0 unless stated; commissions max(wan1 x notional,
5) = 5 yuan on every fill here; sell stamp 0.0005 from 2023-08-28).

Section 10.3 coverage map:
  1  ladder fill order / lots .......... test_t01
  2  invalidation line (fill first) .... test_t02
  3  half-day re-anchor ................. test_t03
  4  TP two tiers / same session ........ test_t04 (+gap test_t05,
     +no-k3 test_t06)
  5  TP keeps ladder .................... test_t07
  6  stop ratchet ....................... test_t08
  7  stop gap fills at open ............. test_t09
  8  stop T+1 across days ............... test_t10 (+partial test_t20)
  9  stop before TP, same session ....... test_t11
  10 seat recycling ..................... test_t12 / t13 / t14
  11 month boundary ..................... test_t15
  12 cash competition (m7) .............. test_t16
Extras: mixed ETF-intent ledger (t17), ladder expiry BR-9 (t18),
below-min-lot scan continuation (t19), stats shape / zero regression
(t21), determinism (t22), validation raises (t23..t27).

All data inline synthetic Polars frames, clearly marked synthetic; no
strategy judgement; zero trial consumption.
"""
from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest

from quant.backtest.band_engine import (  # noqa: E402
    BandContractError,
    run_band_backtest,
    run_band_backtest_intents,
    run_band_backtest_zones,
)

D = date
# panel days (all weekdays): D1..D8 Jan, F1..F4 Feb (month-boundary world)
D1, D2, D3, D4, D5, D6, D7, D8 = (D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9, 10, 11))
F1, F2, F3, F4 = D(2024, 2, 1), D(2024, 2, 2), D(2024, 2, 5), D(2024, 2, 6)
SD1, SD2 = D1, F1

A = 'sh.600001'
B = 'sh.600002'
C = 'sh.600003'
D5X = 'sh.600005'
ETF = 'sz.159001'


def sess_key(d: date, s: str) -> int:
    return (d.year * 10_000 + d.month * 100 + d.day) * 2 + (0 if s == 'am' else 1)


ZONE_SCHEMA = {
    'signal_date': pl.Date, 'symbol': pl.String, 'rank': pl.Int64,
    'industry': pl.String, 'sigma0': pl.Float64, 'p0': pl.Float64,
    'w_t': pl.Float64, 'ladder_offsets': pl.String, 'ladder_fracs': pl.String,
    'tp1_mult': pl.Float64, 'tp1_frac': pl.Float64,
    'tp2_mult': pl.Float64, 'tp2_frac': pl.Float64,
    'stop_mult': pl.Float64, 'invalid_mult': pl.Float64,
    'k_seats': pl.Int64, 'ind_cap': pl.Int64, 'buffer_mult': pl.Int64,
}


def zrow(symbol, rank, industry, sd=SD1, *, sigma0=1.0, p0=10.0, w_t=0.05,
         offsets='0.5,1.5,2.5', fracs='0.4,0.4,0.2', tp1_mult=2.0,
         tp1_frac=0.5, tp2_mult=3.0, tp2_frac=1.0, stop_mult=100.0,
         invalid_mult=10.0, k_seats=1, ind_cap=5, buffer_mult=2):
    """One zones row.  Defaults: stop_mult 100 and invalid_mult 10 keep the
    stop/invalidation lines far away (p0 - 100 x sigma0 < 0) so tests
    exercise one mechanism at a time; the stop/invalidation tests override."""
    return {'symbol': symbol, 'rank': rank, 'industry': industry,
            'signal_date': sd, 'sigma0': sigma0, 'p0': p0, 'w_t': w_t,
            'ladder_offsets': offsets, 'ladder_fracs': fracs,
            'tp1_mult': tp1_mult, 'tp1_frac': tp1_frac,
            'tp2_mult': tp2_mult, 'tp2_frac': tp2_frac,
            'stop_mult': stop_mult, 'invalid_mult': invalid_mult,
            'k_seats': k_seats, 'ind_cap': ind_cap, 'buffer_mult': buffer_mult}


def zones_frame(rows):
    return pl.DataFrame(rows, schema=ZONE_SCHEMA)


def daily_multi(rows_by_sym):
    syms, rows = [], []
    for sym, bars in rows_by_sym.items():
        for r in bars:
            syms.append(sym)
            rows.append(r)
    return pl.DataFrame({
        'symbol': syms, 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def half_multi(rows_by_sym):
    syms, rows = [], []
    for sym, bars in rows_by_sym.items():
        for r in bars:
            syms.append(sym)
            rows.append(r)
    return pl.DataFrame({
        'symbol': syms, 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows]})


def wide_limits(daily, f=0.9):
    """Synthetic +-90% price-limit band.  REAL A-share limits are +-10%,
    but a +-10% band collapses onto crash-day worlds (the v1.x suites
    cover limit legality); the wide synthetic band keeps deep ladder
    tiers and TP targets legal so each test exercises one mechanism."""
    return daily.select(
        'symbol', 'date',
        (pl.col('close') * (1 + f)).alias('limit_up'),
        (pl.col('close') * (1 - f)).alias('limit_down'))


def run_z(zones, daily, half, *, cash=200_000.0, **kw):
    return run_band_backtest_zones(zones, daily, half, wide_limits(daily),
                                   initial_cash=cash, **kw)


def buys(res):
    return res.fills.filter(pl.col('side') == 'buy')


def sells(res):
    return res.fills.filter(pl.col('side') == 'sell')


def zf(res):
    return res.stats['zones']


# --- world W1: sequential ladder fill on a one-side decline (t01/t03) ------
# sigma0 = 1, p0 = 10, w_t = 0.05 -> snapshot 200000 x 0.05 / 10 = 1000
# shares; tiers 0.4/0.4/0.2 -> 400/400/200.  stop_mult 100, invalid 10.
W1_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 9.95, 7.6, 8.0),
    (D3, 7.9, 8.0, 5.4, 6.0),
    (D4, 6.0, 6.1, 5.9, 6.0),
    (D5, 6.0, 6.1, 5.9, 6.0),
    (D6, 6.0, 6.1, 5.9, 6.0)]})
W1_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 7.6, 8.0),
    (D3, 'am', 7.9, 8.0, 5.4, 6.0), (D3, 'pm', 6.0, 6.1, 5.8, 5.9),
    (D4, 'am', 6.0, 6.1, 5.9, 6.0), (D4, 'pm', 6.0, 6.1, 5.9, 6.0),
    (D5, 'am', 6.0, 6.1, 5.9, 6.0), (D5, 'pm', 6.0, 6.1, 5.9, 6.0),
    (D6, 'am', 6.0, 6.1, 5.9, 6.0), (D6, 'pm', 6.0, 6.1, 5.9, 6.0)]})


def test_t01_ladder_sequence_and_lots():
    """SS10.3-1.  Hand-calc (sigma0=1, p0=10, w_t=0.05, cash 200000):
    (D1,pm) admission snapshot 200000 -> total floor(10000/10/100)x100
    = 1000; tiers 400/400/200.  Tier limits from anchor P (am=am.close,
    pm=official close): (D1,pm) P=10.0 -> 9.5/8.5/7.5 live D2am.
    D2am low 9.2: a1 fills 400@9.5.  (D2,am) P=9.3 -> a2 7.8 live D2pm;
    D2pm low 7.6: a2 fills 400@7.8.  (D2,pm) P=8.0 -> a3 5.5 live D3am;
    D3am low 5.4: a3 fills 200@5.5.  Cash: 200000 - (3800+5) - (3120+5)
    - (1100+5) = 191965.  WAC = (3800+3120+1100)/1000 = 8.02."""
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=100.0)]),
                W1_DAILY, W1_HALF)
    f = buys(res)
    assert f.height == 3
    assert [abs(x - v) < 1e-9 for x, v in
            zip(f['price'].to_list(), [9.5, 7.8, 5.5])]
    assert f['shares'].to_list() == [400, 400, 200]
    # per-tier fill-stop: each tier fills exactly once (decision/live routing)
    assert f['decision_session'].to_list() == ['pm', 'am', 'pm']
    assert f['session'].to_list() == ['am', 'pm', 'am']
    assert [x.isoformat() for x in f['date'].to_list()] == \
        ['2024-01-03', '2024-01-03', '2024-01-04']
    # lot conservation: all shares multiples of 100, total = target
    assert all(s % 100 == 0 for s in f['shares'].to_list())
    assert res.zones['shares_bought'][0] == 1000
    assert res.zones['total_target_shares'][0] == 1000
    assert res.zones['tier_filled_shares'][0] == '400,400,200'
    assert abs(res.zones['wac_final'][0] - 8.02) < 1e-9
    assert abs(res.daily['settled_cash'][-1] - 191_965.0) < 1e-6
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'holding' and z['exit_reason'] == 'end_of_data'
    assert z['admitted_key'] == sess_key(D1, 'pm')
    assert z['first_fill_key'] == sess_key(D2, 'am')
    # fixed zone frame columns (BR-1)
    assert res.zones.columns == [
        'signal_date', 'symbol', 'rank', 'industry', 'admitted_key',
        'phase_final', 'exit_reason', 'total_target_shares',
        'tier_filled_shares', 'shares_bought', 'wac_final', 'hwm_final',
        'stop_line_final', 'armed_events', 'first_fill_key']


def test_t03_halfday_reanchor():
    """SS10.3-3.  Tier order prices follow the decision anchor P: the
    (D1,pm) decision uses the OFFICIAL close 10.0, the (D2,am) decision
    uses am.close 9.3, the (D2,pm) decision the official close 8.0 -- the
    a3 tier's unfilled-order limits are 7.5 / 6.8 and it then fills at
    5.5 = 8.0 - 2.5 x 1.0."""
    res = run_z(zones_frame([zrow(A, 1, 'X')]), W1_DAILY, W1_HALF)
    np_ev = res.events.filter(
        (pl.col('event') == 'not_penetrated') & (pl.col('symbol') == A))
    # a2 (live D2am, anchor 10.0 -> 8.5) and a3 (live D2am 7.5)
    d2am = sorted(np_ev.filter((pl.col('date') == D2)
                               & (pl.col('session') == 'am'))['limit_price'])
    assert [abs(x - v) < 1e-9 for x, v in zip(d2am, [7.5, 8.5])]
    # (D2,am) re-anchor: a3 at 9.3 - 2.5 = 6.8, live D2pm
    d2pm = np_ev.filter((pl.col('date') == D2)
                        & (pl.col('session') == 'pm'))['limit_price']
    assert [abs(x - 6.8) < 1e-9 for x in d2pm]
    # (D2,pm) re-anchor: a3 fills at 8.0 - 2.5 = 5.5 on D3am
    f3 = buys(res).filter(pl.col('date') == D3)
    assert abs(f3['price'][0] - 5.5) < 1e-9
    assert f3['decision_date'][0] == D2 and f3['decision_session'][0] == 'pm'


# --- world W2: rally -> TP double trigger (t04/t05/t06) --------------------
# a1 fills D2am 400@9.5 (WAC 9.5); TP1 = 11.5 (200 sh), TP2 = 12.5 (all).
W2_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 9.95, 9.0, 9.4),
    (D3, 9.4, 11.6, 9.3, 11.5),
    (D4, 11.4, 12.6, 11.3, 12.5),
    (D5, 11.4, 11.5, 11.3, 11.4),
    (D6, 11.4, 11.5, 11.3, 11.4)]})
W2_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 9.0, 9.4),
    (D3, 'am', 9.4, 11.6, 9.3, 11.5), (D3, 'pm', 11.4, 11.45, 11.3, 11.4),
    (D4, 'am', 11.4, 12.6, 11.3, 12.5), (D4, 'pm', 12.5, 12.55, 12.4, 12.5),
    (D5, 'am', 11.4, 11.5, 11.3, 11.4), (D5, 'pm', 11.4, 11.45, 11.3, 11.4),
    (D6, 'am', 11.4, 11.5, 11.3, 11.4), (D6, 'pm', 11.4, 11.45, 11.3, 11.4)]})


def test_t04_tp_double_tier_same_session():
    """SS10.3-4.  b1 (+2 sigma = 11.5, frac 0.5) fills D3am 200@11.5;
    b2 (+3 sigma = 12.5) fills D4am; on D4am BOTH targets are exceeded
    (high 12.6) and both orders fill IN THE SAME SESSION at their own
    prices: b1 100@11.5 (re-sized from the remaining 200 shares) then b2
    shares=None 100@12.5.  Cash: 200000 - 3805 + (2300-5-1.15)
    + (1150-5-0.575) + (1250-5-0.625) = 201877.65.  Full clear -> cooling."""
    res = run_z(zones_frame([zrow(A, 1, 'X')]), W2_DAILY, W2_HALF)
    s = sells(res)
    assert s.height == 3
    assert [abs(x - v) < 1e-9 for x, v in
            zip(s['price'].to_list(), [11.5, 11.5, 12.5])]
    assert s['shares'].to_list() == [200, 100, 100]
    assert s['intent'].to_list() == ['profit', 'profit', 'profit']
    # same-session double trigger: two profit fills on D4am
    assert (s['date'] == D4).sum() == 2
    assert abs(s.filter(pl.col('date') == D4)['price'][0] - 11.5) < 1e-9
    assert abs(s.filter(pl.col('date') == D4)['price'][1] - 12.5) < 1e-9
    # hand-calc: 200000 - 3805 + 2293.85 + 1144.425 + 1244.375 = 200877.65
    assert abs(res.daily['settled_cash'][-1] - 200_877.65) < 1e-6
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'cooling' and z['exit_reason'] == 'tp_cleared'
    assert z['tier_filled_shares'] == '400,0,0'
    assert abs(z['wac_final'] - 9.5) < 1e-9
    # TP fill did NOT touch the WAC (BR-4a: sells neither add nor reset)


def test_t05_tp_gap_fills_at_limit():
    """SS10.3-4 (gap).  D3am opens 12.0, above the b1 target 11.5: the
    conservative gap rule fills AT THE LIMIT 11.5, never at the open."""
    daily = daily_multi({A: [
        (D1, 10.0, 10.1, 9.9, 10.0),
        (D2, 9.9, 9.95, 9.0, 9.4),
        (D3, 12.0, 12.2, 11.0, 11.6),
        (D4, 11.6, 11.7, 11.4, 11.5),
        (D5, 11.5, 11.6, 11.4, 11.5),
        (D6, 11.5, 11.6, 11.4, 11.5)]})
    half = half_multi({A: [
        (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
        (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 9.0, 9.4),
        (D3, 'am', 12.0, 12.2, 11.0, 11.6), (D3, 'pm', 11.6, 11.7, 11.4, 11.5),
        (D4, 'am', 11.5, 11.6, 11.4, 11.5), (D4, 'pm', 11.5, 11.6, 11.4, 11.5),
        (D5, 'am', 11.5, 11.6, 11.4, 11.5), (D5, 'pm', 11.5, 11.6, 11.4, 11.5),
        (D6, 'am', 11.5, 11.6, 11.4, 11.5), (D6, 'pm', 11.5, 11.6, 11.4, 11.5)]})
    res = run_z(zones_frame([zrow(A, 1, 'X')]), daily, half)
    first_tp = sells(res).row(0, named=True)
    assert first_tp['date'] == D3 and first_tp['session'] == 'am'
    assert abs(first_tp['price'] - 11.5) < 1e-9   # the limit, not open 12.0


def test_t06_tp_no_k3_silent():
    """SS10.3-4 (no k3).  TP orders that never penetrate expire silently
    every session; no market fallback ever arms (profit intent)."""
    res = run_z(zones_frame([zrow(A, 1, 'X')]), W2_DAILY, W2_HALF)
    assert res.fills.filter(pl.col('fill_type') == 'market_fallback').height == 0
    assert res.stats['k3_fallback']['armed'] == 0
    assert res.stats['k3_fallback']['executed'] == 0
    # hand-count of silent TP expirations: the (D2,am) hang lives D2pm but
    # the shares were acquired THAT DAY -> void_t1_locked (T+1, not an
    # expiry); (D2,pm) hang lives D3am: b1 fills, b2 expires (+1);
    # (D3,am) hang lives D3pm: b1+b2 expire (+2); (D3,pm) hang lives D4am:
    # both fill.  Total 3 order-sessions.
    assert zf(res)['tp_expired_sessions'] == 3
    assert res.events.filter(
        pl.col('event') == 'void_t1_locked').height == 2


# --- world W3: TP then ladder continues (t07) ------------------------------
# a1 400@9.5 D2am; b1 fills D3pm 200@11.5 (high 11.6; the D2pm high stays
# at 10.0 so the T+1-locked shares are never asked for); a2 re-anchored at
# the (D3,pm) decision to 11.5-1.5 = 10.0 fills D4am 400@10.0 (low 9.4).
# D5am high 11.8 sits BETWEEN the pre-fix wrong TP target 11.75 (all-time
# buy average 9.75 + 2) and the correct held-average target 11.8333
# (R9, v1.4.2): it must NOT fill.
W3_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 10.0, 9.0, 9.8),
    (D3, 9.6, 11.6, 9.0, 11.5),
    (D4, 10.2, 11.4, 9.4, 9.5),
    (D5, 9.5, 11.8, 9.3, 9.4),
    (D6, 9.5, 11.8, 9.3, 9.4)]})
W3_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.5, 10.0, 9.4, 9.8),
    (D3, 'am', 9.6, 10.2, 9.0, 10.2), (D3, 'pm', 10.2, 11.6, 10.1, 11.5),
    (D4, 'am', 10.2, 11.4, 9.4, 9.5), (D4, 'pm', 9.5, 9.6, 9.3, 9.4),
    (D5, 'am', 9.5, 11.8, 9.3, 9.4), (D5, 'pm', 9.5, 11.8, 9.3, 9.4),
    (D6, 'am', 9.5, 11.8, 9.3, 9.4), (D6, 'pm', 9.5, 11.8, 9.3, 9.4)]})


def test_t07_tp_keeps_ladder():
    """SS10.3-5.  A b1 fill does NOT cancel the in-flight ladder: after
    b1 (200@11.5, D3pm) the a2 tier still fills (400@10.0, D4am).  R9
    (v1.4.2) hand-calc: after the 200-share sell the held cost is
    200 x 9.5 = 1900; the a2 buy adds 4000 -> WAC = 5900/600 =
    9.8333333... and TP1 re-anchors to 9.8333 + 2 x 1.0 = 11.8333 (NOT
    the all-time-buy 9.75 + 2 = 11.75)."""
    res = run_z(zones_frame([zrow(A, 1, 'X')]), W3_DAILY, W3_HALF)
    f = res.fills
    assert [(r['side'], r['shares'], round(r['price'], 6))
            for r in f.iter_rows(named=True)] == [
        ('buy', 400, 9.5), ('sell', 200, 11.5), ('buy', 400, 10.0)]
    z = res.zones.row(0, named=True)
    assert z['tier_filled_shares'] == '400,400,0'
    assert abs(z['wac_final'] - 5900.0 / 600.0) < 1e-9
    # R9 regression guard: D5/D6 highs 11.8 sit between the wrong target
    # 11.75 and the correct 11.8333 -- no TP fill may occur there.
    assert sells(res).filter(pl.col('date') >= D5).height == 0
    assert not any(11.75 <= p < 5900.0 / 600.0 + 2.0
                   for p in sells(res)['price'].to_list())
    # re-anchored b1 target = 9.8333 + 2 x 1.0 = 11.8333 (silent TP
    # expiries carry the limit on the session_expired event)
    se_ev = res.events.filter(
        (pl.col('event') == 'session_expired') & (pl.col('symbol') == A))
    assert any(abs(x - (5900.0 / 600.0 + 2.0)) < 1e-6
               for x in se_ev['limit_price'])


# --- world W4: stop ratchet (t08) ------------------------------------------
# a1 400@9.5 D2am; (D2,am) HWM 9.3 -> line 6.3; D2pm close 10.5 -> HWM 10.5,
# line 7.5; the market then falls to 7.6-7.8: the naive HWM-3sigma from the
# fallen anchor would be ~4.6 but the ratchet keeps 7.5 and the lows never
# cross it -> no trigger, line stays 7.5.
W4_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 10.6, 9.2, 10.5),
    (D3, 10.5, 10.6, 7.6, 8.0),
    (D4, 7.7, 7.8, 7.55, 7.7),
    (D5, 7.7, 7.8, 7.6, 7.7),
    (D6, 7.7, 7.8, 7.6, 7.7)]})
W4_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 10.6, 9.2, 10.5),
    (D3, 'am', 10.5, 10.6, 7.8, 8.0), (D3, 'pm', 8.0, 8.1, 7.6, 7.7),
    (D4, 'am', 7.7, 7.8, 7.55, 7.7), (D4, 'pm', 7.7, 7.8, 7.6, 7.7),
    (D5, 'am', 7.7, 7.8, 7.6, 7.7), (D5, 'pm', 7.7, 7.8, 7.6, 7.7),
    (D6, 'am', 7.7, 7.8, 7.6, 7.7), (D6, 'pm', 7.7, 7.8, 7.6, 7.7)]})


def test_t08_stop_ratchet():
    """SS10.3-6.  HWM path 9.3 -> 10.5 -> (fall) : the stop line =
    max(historical line, HWM - 3 x sigma0) NEVER decreases -- after the
    fall the recomputed line would be 7.7 - 3 = 4.7 but the frozen line
    stays 7.5; all lows stay above 7.5 so the stop never triggers."""
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=3.0)]),
                W4_DAILY, W4_HALF)
    z = res.zones.row(0, named=True)
    assert abs(z['hwm_final'] - 10.5) < 1e-9
    assert abs(z['stop_line_final'] - 7.5) < 1e-9
    assert res.fills.filter(pl.col('side') == 'sell').height == 0
    assert z['phase_final'] == 'holding'
    assert zf(res)['stop_armed_events'] == 0


# --- world W5: stop gap fills at the open (t09) ----------------------------
# line 7.5 (as W4); D3am opens 7.0 (gap below the line), low 6.9: fill at
# min(line, open) = 7.0 -- NOT at the line 7.5.
W5_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 10.6, 9.2, 10.5),
    (D3, 7.0, 7.1, 6.9, 7.0),
    (D4, 7.0, 7.1, 6.9, 7.0),
    (D5, 7.0, 7.1, 6.9, 7.0),
    (D6, 7.0, 7.1, 6.9, 7.0)]})
W5_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 10.6, 9.2, 10.5),
    (D3, 'am', 7.0, 7.1, 6.9, 7.0), (D3, 'pm', 7.0, 7.05, 6.95, 7.0),
    (D4, 'am', 7.0, 7.1, 6.9, 7.0), (D4, 'pm', 7.0, 7.05, 6.95, 7.0),
    (D5, 'am', 7.0, 7.1, 6.9, 7.0), (D5, 'pm', 7.0, 7.05, 6.95, 7.0),
    (D6, 'am', 7.0, 7.1, 6.9, 7.0), (D6, 'pm', 7.0, 7.05, 6.95, 7.0)]})


def test_t09_stop_gap_open():
    """SS10.3-7.  Gap through the stop line: fill price = min(line, open)
    = the OPEN 7.0, not the line 7.5.  All 400 shares sellable (acquired
    D2) -> full clear at trigger -> cooling, no fallback armed."""
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=3.0)]),
                W5_DAILY, W5_HALF)
    s = sells(res)
    assert s.height == 1
    row = s.row(0, named=True)
    assert row['fill_type'] == 'stop' and row['intent'] == 'risk'
    assert abs(row['price'] - 7.0) < 1e-9     # open, not the line 7.5
    assert row['shares'] == 400 and row['date'] == D3 \
        and row['session'] == 'am'
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'cooling' and z['exit_reason'] == 'stop_cleared'
    assert z['armed_events'] == 0
    assert zf(res)['stop_armed_events'] == 0
    # hand-calc: 200000 - 3805 + (2800 - 5 - 1.4) = 198988.60
    assert abs(res.daily['settled_cash'][-1] - 198_988.60) < 1e-6


# --- world W6: stop T+1 residual -> K=3 fallback (t10) ----------------------
# a1 400@9.5 D2am; (D2,am) line 6.3; D2pm crashes to low 5.8 -> trigger but
# the clip was acquired TODAY (am) -> 0 sellable -> armed; D3am fallback
# sells 400 at the open 5.9.
W6_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 9.95, 5.8, 6.0),
    (D3, 5.9, 6.0, 5.7, 5.8),
    (D4, 5.8, 5.9, 5.7, 5.8),
    (D5, 5.8, 5.9, 5.7, 5.8),
    (D6, 5.8, 5.9, 5.7, 5.8)]})
W6_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 5.8, 6.0),
    (D3, 'am', 5.9, 6.0, 5.7, 5.8), (D3, 'pm', 5.8, 5.85, 5.75, 5.8),
    (D4, 'am', 5.8, 5.9, 5.7, 5.8), (D4, 'pm', 5.8, 5.85, 5.75, 5.8),
    (D5, 'am', 5.8, 5.9, 5.7, 5.8), (D5, 'pm', 5.8, 5.85, 5.75, 5.8),
    (D6, 'am', 5.8, 5.9, 5.7, 5.8), (D6, 'pm', 5.8, 5.85, 5.75, 5.8)]})


def test_t10_stop_t1_armed_fallback():
    """SS10.3-8.  Stop triggers on the buy day: 0 sellable (T+1) -> no
    'stop' fill, the K=3 open-market fallback arms directly (gate-8
    stop_armed_events) and executes at the NEXT session's open 5.9."""
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=3.0)]),
                W6_DAILY, W6_HALF)
    assert res.fills.filter(pl.col('fill_type') == 'stop').height == 0
    fb = res.fills.filter(pl.col('fill_type') == 'market_fallback')
    assert fb.height == 1
    row = fb.row(0, named=True)
    assert row['date'] == D3 and row['session'] == 'am'
    assert abs(row['price'] - 5.9) < 1e-9 and row['shares'] == 400
    assert row['intent'] == 'risk'
    z = res.zones.row(0, named=True)
    assert z['armed_events'] == 1 and z['phase_final'] == 'cooling' \
        and z['exit_reason'] == 'stop_cleared'
    zg = zf(res)
    assert zg['stop_armed_events'] == 1
    assert zg['stop_armed_resolved_fallback'] == 1
    assert zg['stop_armed_resolved_other'] == 0
    assert zg['stop_armed_stuck_end'] == 0
    # the same-session fallback attempt deferred on T+1 (existing executor)
    assert res.events.filter(
        pl.col('event') == 'market_exit_deferred_t1locked').height == 1
    # hand-calc: 200000 - 3805 + (2360 - 5 - 1.18) = 198548.82
    assert abs(res.daily['settled_cash'][-1] - 198_548.82) < 1e-6


def test_t20_stop_partial_sellable_residual():
    """SS10.3-8 (partial).  a1 fills D2am (acquired D2); a2+a3 fill D3am
    (acquired D3; 400+200 shares).  D3pm triggers the stop (low 6.0 <
    line 6.3): only the 400 shares acquired D2 are sellable -> stop fill
    400@6.3; the 600 D3-acquired shares are T+1 locked -> fallback armed,
    executes D4am at the open 6.1.
    Cash: 200000 - 9575 + (2520-5-1.26) + (3660-5-1.83) = 196591.91."""
    daily = daily_multi({A: [
        (D1, 10.0, 10.1, 9.9, 10.0),
        (D2, 9.9, 9.95, 8.9, 9.2),
        (D3, 9.2, 9.3, 6.0, 6.6),
        (D4, 6.1, 6.2, 5.9, 6.0),
        (D5, 6.0, 6.1, 5.9, 6.0),
        (D6, 6.0, 6.1, 5.9, 6.0)]})
    half = half_multi({A: [
        (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
        (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 8.9, 9.2),
        (D3, 'am', 9.2, 9.3, 6.5, 6.6), (D3, 'pm', 6.6, 6.7, 6.0, 6.2),
        (D4, 'am', 6.1, 6.2, 5.9, 6.0), (D4, 'pm', 6.0, 6.05, 5.95, 6.0),
        (D5, 'am', 6.0, 6.1, 5.9, 6.0), (D5, 'pm', 6.0, 6.05, 5.95, 6.0),
        (D6, 'am', 6.0, 6.1, 5.9, 6.0), (D6, 'pm', 6.0, 6.05, 5.95, 6.0)]})
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=3.0)]), daily, half)
    s = sells(res)
    assert s.height == 2
    stop_fill = s.filter(pl.col('fill_type') == 'stop').row(0, named=True)
    assert stop_fill['shares'] == 400
    assert abs(stop_fill['price'] - 6.3) < 1e-9     # min(line 6.3, open 6.6)
    assert stop_fill['date'] == D3 and stop_fill['session'] == 'pm'
    fb = s.filter(pl.col('fill_type') == 'market_fallback').row(0, named=True)
    assert fb['shares'] == 600 and abs(fb['price'] - 6.1) < 1e-9
    assert fb['date'] == D4 and fb['session'] == 'am'
    z = res.zones.row(0, named=True)
    assert z['armed_events'] == 1 and z['phase_final'] == 'cooling'
    zg = zf(res)
    assert zg['stop_armed_events'] == 1
    assert zg['stop_armed_resolved_fallback'] == 1
    # hand-calc: buys 3805+3085+1345 = 8235 (a1 400@9.5, a2 400@7.7,
    # a3 200@6.7); sells (2520-5-1.26) + (3660-5-1.83)
    #   -> 200000 - 8235 + 2513.74 + 3653.17 = 197931.91
    assert abs(res.daily['settled_cash'][-1] - 197_931.91) < 1e-6


# --- world W7: stop before TP in the same session (t11) ---------------------
# line 7.5, TP1 target 11.5; D3am low 7.4 AND high 11.6: the stop segment
# runs before the C segment -> the TP order is cancelled, only the stop
# fills (at min(7.5, open 10.4) = 7.5).
W7_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 10.6, 9.2, 10.5),
    (D3, 10.4, 11.6, 7.4, 8.0),
    (D4, 8.0, 8.1, 7.9, 8.0),
    (D5, 8.0, 8.1, 7.9, 8.0),
    (D6, 8.0, 8.1, 7.9, 8.0)]})
W7_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 10.6, 9.2, 10.5),
    (D3, 'am', 10.4, 11.6, 7.4, 8.0), (D3, 'pm', 8.0, 8.1, 7.9, 8.0),
    (D4, 'am', 8.0, 8.1, 7.9, 8.0), (D4, 'pm', 8.0, 8.1, 7.9, 8.0),
    (D5, 'am', 8.0, 8.1, 7.9, 8.0), (D5, 'pm', 8.0, 8.1, 7.9, 8.0),
    (D6, 'am', 8.0, 8.1, 7.9, 8.0), (D6, 'pm', 8.0, 8.1, 7.9, 8.0)]})


def test_t11_stop_before_tp_same_session():
    """SS10.3-9.  Same-session stop + TP both touchable: the frozen
    ruling 10.1-3 (stop first) is enforced by segment order -- the TP
    order is cancelled before the C segment, so the high 11.6 > target
    11.5 does NOT fill; only the stop fills 400@7.5."""
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=3.0)]),
                W7_DAILY, W7_HALF)
    s = sells(res)
    assert s.height == 1
    row = s.row(0, named=True)
    assert row['fill_type'] == 'stop'
    assert abs(row['price'] - 7.5) < 1e-9    # min(line 7.5, open 10.4)
    assert res.fills.filter(pl.col('intent') == 'profit').height == 0
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'cooling' and z['exit_reason'] == 'stop_cleared'
    # the D2pm TP pair is T+1-VOIDED (shares acquired that day), not
    # expired; the D3am pair is cancelled by the stop before the C segment
    assert zf(res)['tp_expired_sessions'] == 0
    assert res.events.filter(
        pl.col('event') == 'void_t1_locked').height == 2
    # hand-calc: 200000 - 3805 + (3000 - 5 - 1.5) = 199188.50
    assert abs(res.daily['settled_cash'][-1] - 199_188.50) < 1e-6


# --- world W8: seat recovery after a stop full clear (t12) ------------------
# A (rank1) stops out D3am (fill 400@6.3, full clear -> cooling at the
# (D3,am) decision); the SAME decision's scan admits B (rank2, k_seats=1);
# B's a1 (limit 20.0-0.5 = 19.5) fills D3pm at 19.5.
W8_DAILY = daily_multi({
    A: [(D1, 10.0, 10.1, 9.9, 10.0),
        (D2, 9.9, 10.1, 9.0, 9.2),
        (D3, 9.2, 9.3, 6.1, 6.2),
        (D4, 6.2, 6.3, 6.1, 6.2),
        (D5, 6.2, 6.3, 6.1, 6.2),
        (D6, 6.2, 6.3, 6.1, 6.2)],
    B: [(D1, 20.0, 20.1, 19.9, 20.0), (D2, 20.0, 20.1, 19.9, 20.0),
        (D3, 20.0, 20.1, 19.9, 20.0), (D4, 20.0, 20.1, 19.9, 20.0),
        (D5, 20.0, 20.1, 19.9, 20.0), (D6, 20.0, 20.1, 19.9, 20.0)]})
W8_HALF = half_multi({
    A: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
        (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 9.0, 9.2),
        (D3, 'am', 9.2, 9.3, 6.1, 6.2), (D3, 'pm', 6.2, 6.3, 6.1, 6.2),
        (D4, 'am', 6.2, 6.3, 6.1, 6.2), (D4, 'pm', 6.2, 6.3, 6.1, 6.2),
        (D5, 'am', 6.2, 6.3, 6.1, 6.2), (D5, 'pm', 6.2, 6.3, 6.1, 6.2),
        (D6, 'am', 6.2, 6.3, 6.1, 6.2), (D6, 'pm', 6.2, 6.3, 6.1, 6.2)],
    B: [(D1, 'am', 20.0, 20.05, 19.95, 20.0), (D1, 'pm', 20.0, 20.05, 19.95, 20.0),
        (D2, 'am', 20.0, 20.05, 19.95, 20.0), (D2, 'pm', 20.0, 20.05, 19.95, 20.0),
        (D3, 'am', 20.0, 20.05, 19.95, 20.0), (D3, 'pm', 20.0, 20.1, 19.4, 19.9),
        (D4, 'am', 19.9, 20.0, 19.8, 19.9), (D4, 'pm', 19.9, 20.0, 19.8, 19.9),
        (D5, 'am', 19.9, 20.0, 19.8, 19.9), (D5, 'pm', 19.9, 20.0, 19.8, 19.9),
        (D6, 'am', 19.9, 20.0, 19.8, 19.9), (D6, 'pm', 19.9, 20.0, 19.8, 19.9)]})


def test_t12_seat_recovery_after_stop_cooling():
    """SS10.3-10 (recovery + cooling).  k_seats=1: B stays unadmitted while
    A holds.  A's stop full-clears D3am -> cooling at the (D3,am) decision
    and the SAME decision's rank-ordered scan admits B (A is skipped: a
    zone already exists for A this month -> cooling blocks re-entry).  B's
    a1 fills D3pm 200@19.5 (p0=20, w_t=0.05 -> total 500 -> tiers 200/200/100)."""
    res = run_z(zones_frame([zrow(A, 1, 'X', stop_mult=3.0),
                             zrow(B, 2, 'Y', p0=20.0)]),
                W8_DAILY, W8_HALF)
    zrows = {r['symbol']: r for r in res.zones.iter_rows(named=True)}
    assert set(zrows) == {A, B}          # exactly one zone per symbol
    assert zrows[A]['phase_final'] == 'cooling' \
        and zrows[A]['exit_reason'] == 'stop_cleared'
    assert zrows[B]['admitted_key'] == sess_key(D3, 'am')
    b_fill = buys(res).filter(pl.col('symbol') == B).row(0, named=True)
    assert b_fill['date'] == D3 and b_fill['session'] == 'pm'
    assert abs(b_fill['price'] - 19.5) < 1e-9 and b_fill['shares'] == 200
    # A never re-entered (cooling): A bought exactly once
    assert buys(res).filter(pl.col('symbol') == A).height == 1
    # hand-calc: 200000 - 3805 + (2520-5-1.26) - (3900+5) = 194803.74
    assert abs(res.daily['settled_cash'][-1] - 194_803.74) < 1e-6


def test_t13_industry_count_inflight():
    """SS10.3-10 (industry).  ind_cap=1: A (industry X) admitted and
    IN-FLIGHT (ladder hung, never fills -- lows stay above the a1 limit)
    already consumes the X quota -- B (also X, rank2) is skipped, C
    (industry Y, rank3) is admitted."""
    daily = daily_multi({
        A: [(d, 10.0, 10.05, 9.6, 9.7) for d in (D1, D2, D3, D4, D5, D6)],
        B: [(d, 10.5, 10.6, 10.4, 10.5) for d in (D1, D2, D3, D4, D5, D6)],
        C: [(d, 10.5, 10.6, 10.4, 10.5) for d in (D1, D2, D3, D4, D5, D6)]})
    half = half_multi({
        A: [(d, s, 10.0, 10.05, 9.6, 9.7)
            for d in (D1, D2, D3, D4, D5, D6) for s in ('am', 'pm')],
        B: [(d, s, 10.5, 10.55, 10.45, 10.5)
            for d in (D1, D2, D3, D4, D5, D6) for s in ('am', 'pm')],
        C: [(d, s, 10.5, 10.55, 10.45, 10.5)
            for d in (D1, D2, D3, D4, D5, D6) for s in ('am', 'pm')]})
    res = run_z(zones_frame([zrow(A, 1, 'X', k_seats=3, ind_cap=1),
                             zrow(B, 2, 'X', k_seats=3, ind_cap=1),
                             zrow(C, 3, 'Y', k_seats=3, ind_cap=1)]),
                daily, half)
    assert set(res.zones['symbol']) == {A, C}     # B blocked by X quota
    assert zf(res)['n_admitted'] == 2
    # A stayed in-flight (never filled): its a1 = anchor - 0.5 <= 9.2 < low 9.6
    assert buys(res).height == 0


def test_t14_seat_cap_hold_plus_inflight():
    """SS10.3-10 (seat cap).  k_seats=2: A and B admitted at the boundary
    (held + in-flight = 2); C (rank3) is never admitted while both stay
    active."""
    daily = daily_multi({
        A: [(d, 10.0, 10.05, 9.6, 9.7) for d in (D1, D2, D3, D4, D5, D6)],
        B: [(d, 10.5, 10.6, 10.4, 10.5) for d in (D1, D2, D3, D4, D5, D6)],
        C: [(d, 10.5, 10.6, 10.4, 10.5) for d in (D1, D2, D3, D4, D5, D6)]})
    half = half_multi({
        A: [(d, s, 10.0, 10.05, 9.6, 9.7)
            for d in (D1, D2, D3, D4, D5, D6) for s in ('am', 'pm')],
        B: [(d, s, 10.5, 10.55, 10.45, 10.5)
            for d in (D1, D2, D3, D4, D5, D6) for s in ('am', 'pm')],
        C: [(d, s, 10.5, 10.55, 10.45, 10.5)
            for d in (D1, D2, D3, D4, D5, D6) for s in ('am', 'pm')]})
    res = run_z(zones_frame([zrow(A, 1, 'X', k_seats=2),
                             zrow(B, 2, 'Y', k_seats=2),
                             zrow(C, 3, 'Z', k_seats=2)]),
                daily, half)
    assert set(res.zones['symbol']) == {A, B}


# --- world W9: month boundary (t15) ----------------------------------------
# Month 1 (SD1=2024-01-02): A rank1 (X), C rank2 (W); k=2, buffer 2 (<=4).
# A fills 400@9.5 D2am; C fills 800@4.5 D2am (p0=5).  Flat until F1.
# Month 2 (SD2=2024-02-01): A rank5 (>4 -> full exit), C rank1 (<=4 ->
# continuation, sigma0 2), B rank2 (new).  At the (F1,pm) boundary the
# old ladders' unfilled tiers expire (tier_expired 2+2), A becomes
# exiting_boundary (risk sell @ anchor 9.3, priority 1e6+5), C continues
# (WAC 4.5 kept; TP1 re-anchors to 4.5+2x2 = 8.5).  Seats: A+C held = 2 = k
# -> B waits; A's risk sell fills F2am 400@9.3 -> A done at (F2,am) and the
# freed seat admits B (total floor(0.05x200230/10/100)x100 = 1000).
W9_FLAT_A = [(D3, 9.2, 9.3, 9.0, 9.2), (D4, 9.2, 9.3, 9.0, 9.2),
             (D5, 9.2, 9.3, 9.0, 9.2), (D6, 9.2, 9.3, 9.0, 9.2),
             (D7, 9.2, 9.3, 9.0, 9.2), (D8, 9.2, 9.3, 9.0, 9.2),
             (F1, 9.2, 9.3, 9.0, 9.3)]
W9_FLAT_C = [(d, 4.9, 5.0, 4.8, 4.9) for d in
             (D3, D4, D5, D6, D7, D8, F1, F2, F3, F4)]


def _w9_world():
    daily = daily_multi({
        A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 9.95, 9.0, 9.2)]
           + W9_FLAT_A
           + [(F2, 9.2, 9.4, 9.1, 9.3), (F3, 9.2, 9.3, 9.0, 9.2),
              (F4, 9.2, 9.3, 9.0, 9.2)],
        C: [(D1, 5.0, 5.05, 4.95, 5.0), (D2, 4.95, 5.0, 4.4, 4.9)]
           + W9_FLAT_C,
        B: [(F1, 10.0, 10.05, 9.95, 10.0), (F2, 9.9, 9.95, 9.0, 9.2),
            (F3, 9.2, 9.3, 8.5, 8.8), (F4, 8.8, 8.9, 8.7, 8.8)]})
    half = half_multi({
        A: [(D1, 'am', 10.0, 10.05, 9.9, 10.0),
            (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 9.95, 9.2, 9.3),
            (D2, 'pm', 9.3, 9.4, 9.0, 9.2)]
           + [(d, s, 9.2, 9.3, 9.0, 9.2) for d in
              (D3, D4, D5, D6, D7, D8) for s in ('am', 'pm')]
           + [(F1, 'am', 9.2, 9.3, 9.0, 9.2), (F1, 'pm', 9.2, 9.3, 9.0, 9.3),
              (F2, 'am', 9.2, 9.4, 9.1, 9.3), (F2, 'pm', 9.3, 9.35, 9.2, 9.3),
              (F3, 'am', 9.2, 9.3, 9.0, 9.2), (F3, 'pm', 9.2, 9.3, 9.0, 9.2),
              (F4, 'am', 9.2, 9.3, 9.0, 9.2), (F4, 'pm', 9.2, 9.3, 9.0, 9.2)],
        C: [(D1, 'am', 5.0, 5.05, 4.95, 5.0), (D1, 'pm', 5.0, 5.05, 4.95, 5.0),
            (D2, 'am', 4.95, 5.0, 4.4, 4.9), (D2, 'pm', 4.9, 5.0, 4.8, 4.9)]
           + [(d, s, 4.9, 5.0, 4.8, 4.9) for d in
              (D3, D4, D5, D6, D7, D8, F1, F2, F3, F4) for s in ('am', 'pm')],
        B: [(F1, 'am', 10.0, 10.05, 9.95, 10.0), (F1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (F2, 'am', 9.9, 9.95, 9.0, 9.3), (F2, 'pm', 9.3, 9.35, 9.0, 9.2),
            (F3, 'am', 9.2, 9.3, 8.5, 8.8), (F3, 'pm', 8.8, 8.9, 8.7, 8.8),
            (F4, 'am', 8.8, 8.9, 8.7, 8.8), (F4, 'pm', 8.8, 8.9, 8.7, 8.8)]})
    return daily, half


def test_t15_month_boundary_exit_continue_refill():
    """SS10.3-11.  Month boundary at (SD2, 'pm'): A rank5 > buffer 2 x K 2
    -> exiting_boundary + full-exit risk sell (priority 10^6+5) which
    fills F2am at the anchor 9.3 -> zone done boundary_cleared; C rank1
    continues with sigma0 2 (TP1 target 4.5 + 2 x 2 = 8.5, WAC 4.5 kept);
    B is admitted only after A's exit fills releases the seat (admitted at
    the (F2,am) decision)."""
    daily, half = _w9_world()
    zones = zones_frame([
        zrow(A, 1, 'X', sd=SD1, stop_mult=3.0, k_seats=2, buffer_mult=2),
        zrow(C, 2, 'W', sd=SD1, p0=5.0, stop_mult=3.0,
             k_seats=2, buffer_mult=2),
        zrow(A, 5, 'X', sd=SD2, stop_mult=3.0, k_seats=2, buffer_mult=2),
        zrow(C, 1, 'W', sd=SD2, p0=5.0, sigma0=2.0, stop_mult=3.0,
             k_seats=2, buffer_mult=2),
        zrow(B, 2, 'Y', sd=SD2, k_seats=2, buffer_mult=2)])
    res = run_z(zones, daily, half)
    zrows = {r['symbol']: r for r in res.zones.iter_rows(named=True)}
    # A: month1 admission, boundary exit, risk sell fills 400@9.3 F2am
    assert zrows[A]['phase_final'] == 'done'
    assert zrows[A]['exit_reason'] == 'boundary_cleared'
    a_sell = sells(res).row(0, named=True)
    assert a_sell['intent'] == 'risk' and a_sell['priority'] == 10 ** 6 + 1
    assert abs(a_sell['price'] - 9.3) < 1e-9
    assert a_sell['date'] == F2 and a_sell['session'] == 'am'
    # C: continuation -- new signal month, rank 1, WAC kept, sigma0 refreshed
    assert zrows[C]['signal_date'] == SD2
    assert zrows[C]['rank'] == 1
    assert zrows[C]['phase_final'] == 'holding'
    assert abs(zrows[C]['wac_final'] - 4.5) < 1e-9
    # C TP1 re-anchored: 4.5 + 2 x 2.0 = 8.5 (silent expiry carries the
    # limit on the session_expired event at F2am; C's TP2 10.5 voids on
    # the synthetic limit band -- disclosure only)
    c_tp = res.events.filter(
        (pl.col('event') == 'session_expired') & (pl.col('symbol') == C)
        & (pl.col('date') == F2) & (pl.col('session') == 'am'))
    assert any(abs(x - 8.5) < 1e-9 for x in c_tp['limit_price'])
    # B: admitted only after A's exit frees the seat
    assert zrows[B]['admitted_key'] == sess_key(F2, 'am')
    b_fill = buys(res).filter(pl.col('symbol') == B).row(0, named=True)
    assert b_fill['date'] == F3 and b_fill['session'] == 'am'
    assert abs(b_fill['price'] - 8.7) < 1e-9   # (F2,pm) anchor 9.2 - 0.5
    assert b_fill['shares'] == 400             # tier 0.4 x 1000 -> 400
    # unfilled month-1 tiers expired at the boundary: A a2+a3, C a2+a3 (=4);
    # B's own unfilled a2+a3 expire at the data end (no next session) -> 6
    assert zf(res)['tier_expired'] == 6
    # hand-calc: 200000 - 3805 - 3605 + (3720-5-1.86) - (3480+5)
    #   = 192818.14
    assert abs(res.daily['settled_cash'][-1] - 192_818.14) < 1e-6
    life = res.events.filter(pl.col('event') == 'zone_continued')
    assert life.height == 1 and C in life['detail'][0]


# --- world W10: cash competition across five ladders (t16) ------------------
# cash 105000; five candidates rank1..5, w_t 0.28 -> total floor(0.28 x
# 105000 / 10 / 100) x 100 = 2900 shares each; tiers 1100/1100/500 at
# 9.5/8.5/7.5.  Per-name demand 10450+9350+3750 = 23550 (+3 x 5 fees).
# Processing order = (priority=1000+rank, symbol): ranks 1-4 fully fund
# (4 x 23565 = 94260); rank5 a1 10455 fits the remaining 10740, a2/a3 void
# insufficient_cash.  Final cash 105000 - 94260 - 10455 = 285.
W10_SYMS = ['sh.600001', 'sh.600002', 'sh.600003', 'sh.600004', 'sh.600005']


def _w10_world():
    daily_rows = {s: [(D1, 10.0, 10.1, 9.9, 10.0),
                      (D2, 8.0, 8.1, 7.0, 7.5),
                      (D3, 7.5, 7.6, 7.4, 7.5)] for s in W10_SYMS}
    half_rows = {s: [(D1, 'am', 10.0, 10.05, 9.9, 10.0),
                     (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
                     (D2, 'am', 8.0, 8.1, 7.0, 7.5),
                     (D2, 'pm', 7.5, 7.6, 7.4, 7.5),
                     (D3, 'am', 7.5, 7.6, 7.4, 7.5),
                     (D3, 'pm', 7.5, 7.6, 7.4, 7.5)] for s in W10_SYMS}
    return daily_multi(daily_rows), half_multi(half_rows)


def test_t16_cash_priority_m7():
    """SS10.3-12 (m7).  Same decision point, five ladders competing for
    cash: lower rank = lower priority number = funded first; the rank-5
    ladder's a1 fills and its a2/a3 void insufficient_cash (the engine
    never downsizes).  Booking order follows (priority, symbol)."""
    daily, half = _w10_world()
    zones = zones_frame([
        zrow(s, i + 1, 'i%d' % (i + 1), w_t=0.28, k_seats=5, ind_cap=5)
        for i, s in enumerate(W10_SYMS)])
    res = run_z(zones, daily, half, cash=105_000.0)
    f = buys(res)
    assert f.height == 13                     # 4 names x 3 tiers + rank5 a1
    assert f['shares'].to_list() == [1100, 1100, 500] * 4 + [1100]
    assert f['symbol'].to_list()[-1] == D5X   # rank5 booked last
    assert abs(f['price'][-1] - 9.5) < 1e-9
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 2
    assert abs(res.daily['settled_cash'][-1] - 285.0) < 1e-6
    # the voided rank-5 tiers expire at the data end (never filled)
    assert zf(res)['tier_expired'] == 2
    zr5 = res.zones.filter(pl.col('symbol') == D5X).row(0, named=True)
    assert zr5['tier_filled_shares'] == '1100,0,0'
    assert zr5['total_target_shares'] == 2900


# --- mixed ETF-intent + zones (t17) -----------------------------------------

INTENT_SCHEMA = {
    'symbol': pl.String, 'side': pl.String, 'intent': pl.String,
    'decision_date': pl.Date, 'decision_session': pl.String,
    'source_signal': pl.Date, 'expiry_date': pl.Date,
    'priority': pl.Int64, 'target_notional': pl.Float64,
    'target_weight': pl.Float64,
}


def test_t17_mixed_etf_intent_one_ledger():
    """BR-1: zones (stock leg) compose with an intent frame (ETF leg) on
    ONE ledger.  ETF buy intent (D1,pm) target 10000 at the official close
    5.0 -> 2000 shares, lives (D2,pm), fills 2000@5.0 (low 4.9), ETF pays
    no stamp, commission 5.  Stock a1 fills 400@9.5 D2am (cost 3805).
    Final cash 200000 - 3805 - 10005 = 186190."""
    daily = daily_multi({
        A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 9.95, 9.0, 9.4),
            (D3, 9.4, 9.5, 9.3, 9.4)],
        ETF: [(D1, 5.0, 5.05, 4.95, 5.0), (D2, 5.0, 5.05, 4.9, 5.0),
              (D3, 5.0, 5.05, 4.95, 5.0)]})
    half = half_multi({
        A: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 9.0, 9.4),
            (D3, 'am', 9.4, 9.5, 9.3, 9.4), (D3, 'pm', 9.4, 9.5, 9.3, 9.4)],
        ETF: [(D1, 'pm', 5.0, 5.05, 4.95, 5.0), (D2, 'pm', 5.0, 5.05, 4.9, 5.0),
              (D3, 'pm', 5.0, 5.05, 4.95, 5.0)]})
    intents = pl.DataFrame([{
        'symbol': ETF, 'side': 'buy', 'intent': None, 'decision_date': D1,
        'decision_session': 'pm', 'source_signal': D1, 'expiry_date': None,
        'priority': 1, 'target_notional': 10_000.0, 'target_weight': None}],
        schema=INTENT_SCHEMA)
    res = run_band_backtest_zones(
        zones_frame([zrow(A, 1, 'X')]), daily, half, wide_limits(daily),
        symbol_meta={ETF: {'asset_class': 'etf'}},
        intents=intents, initial_cash=200_000.0)
    etf_fills = res.fills.filter(pl.col('symbol') == ETF)
    assert etf_fills.height == 1
    ef = etf_fills.row(0, named=True)
    assert ef['is_etf'] and abs(ef['price'] - 5.0) < 1e-9
    assert ef['shares'] == 2000 and ef['session'] == 'pm'
    assert ef['stamp_tax'] == 0.0
    assert buys(res).filter(pl.col('symbol') == A).height == 1
    assert abs(res.daily['settled_cash'][-1] - 186_190.0) < 1e-6
    assert 'intent_layer' in res.stats and 'zones' in res.stats
    assert res.zones['symbol'].to_list() == [A]


# --- ladder expiry (BR-9) ----------------------------------------------------

def test_t18_ladder_expiry_br9():
    """BR-9: a ladder that never fills expires at its month's expiry
    (= next signal_date + 1 day): at the (SD2,'pm') decision the month-1
    zone's 3 unfilled tiers are cancelled and the never-filled zone is
    done.  The month-2 zone then expires the same way at the data end
    (no next session).  Total tier_expired = 6; zero fills."""
    daily = daily_multi({
        A: [(d, 10.5, 10.6, 10.4, 10.5) for d in (D1, D2, D3, D4)],
        B: [(d, 10.5, 10.6, 10.4, 10.5) for d in (D1, D2, D3, D4)]})
    half = half_multi({
        A: [(d, s, 10.5, 10.55, 10.45, 10.5)
            for d in (D1, D2, D3, D4) for s in ('am', 'pm')],
        B: [(d, s, 10.5, 10.55, 10.45, 10.5)
            for d in (D1, D2, D3, D4) for s in ('am', 'pm')]})
    # p0 = 10.5, w_t 0.05 -> total floor(10000/10.5/100)x100 = 900;
    # tiers 300/300/100 (all unfilled: a1 = anchor - 0.5 = 10.0 vs low 10.45)
    zones = zones_frame([zrow(A, 1, 'X', sd=D1, p0=10.5),
                         zrow(B, 1, 'X', sd=D3, p0=10.5)])
    res = run_z(zones, daily, half)
    zrows = {r['symbol']: r for r in res.zones.iter_rows(named=True)}
    assert zrows[A]['phase_final'] == 'done'
    assert zrows[A]['exit_reason'] == 'ladder_expired'
    assert zrows[B]['exit_reason'] == 'ladder_expired'
    assert zf(res)['tier_expired'] == 6
    assert res.fills.height == 0


def test_t19_below_min_lot_scan_continues():
    """BR-3/S-v14-2: a candidate whose one-shot total floors below one lot
    (w_t 0.001 -> 0.001 x 200000 / 10 = 20 shares) is done immediately
    (below_min_lot) and the scan CONTINUES to the next rank."""
    daily = daily_multi({
        A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 9.95, 9.0, 9.4),
            (D3, 9.4, 9.5, 9.3, 9.4)],
        B: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 9.95, 9.0, 9.4),
            (D3, 9.4, 9.5, 9.3, 9.4)]})
    half = half_multi({
        A: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 9.0, 9.4),
            (D3, 'am', 9.4, 9.5, 9.3, 9.4), (D3, 'pm', 9.4, 9.5, 9.3, 9.4)],
        B: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 9.0, 9.4),
            (D3, 'am', 9.4, 9.5, 9.3, 9.4), (D3, 'pm', 9.4, 9.5, 9.3, 9.4)]})
    res = run_z(zones_frame([zrow(A, 1, 'X', w_t=0.001, k_seats=2),
                             zrow(B, 2, 'Y', k_seats=2)]), daily, half)
    zrows = {r['symbol']: r for r in res.zones.iter_rows(named=True)}
    assert zrows[A]['phase_final'] == 'done'
    assert zrows[A]['exit_reason'] == 'below_min_lot'
    assert zf(res)['tier_below_min_lot'] == 1
    # B took the seat and filled a1
    assert buys(res).filter(pl.col('symbol') == B).height == 1
    assert zrows[B]['admitted_key'] == sess_key(D1, 'pm')


# --- stats shape / zero regression / determinism ----------------------------

def test_t21_stats_shape_zero_regression():
    """BR-12: without a zones frame there is NO stats['zones'] key and
    BandResult.zones is None; with zones the gate-8 v1.4 block carries the
    BR-10 counters."""
    daily, half = W1_DAILY, W1_HALF
    res_nz = run_band_backtest_intents(
        pl.DataFrame([{
            'symbol': A, 'side': 'buy', 'intent': None, 'decision_date': D1,
            'decision_session': 'am', 'source_signal': D1,
            'expiry_date': None, 'priority': 1, 'target_notional': 10_000.0,
            'target_weight': None}], schema=INTENT_SCHEMA),
        daily, half, wide_limits(daily), initial_cash=200_000.0)
    assert res_nz.zones is None
    assert 'zones' not in res_nz.stats
    assert res_nz.stats['engine_version'] == 'band_engine v1.5'
    res_z = run_z(zones_frame([zrow(A, 1, 'X')]), daily, half)
    zblk = res_z.stats['zones']
    for key in ('stop_armed_events', 'stop_armed_resolved_fallback',
                'stop_armed_resolved_other', 'stop_armed_stuck_end',
                'tp_expired_sessions', 'tier_expired', 'tier_invalidated',
                'tier_below_min_lot'):
        assert key in zblk
    assert res_z.stats['engine_version'] == 'band_engine v1.5'
    assert res_z.zones is not None and res_z.zones.height == 1


def test_t22_determinism():
    """Same zones input twice -> bit-identical frames and stats."""
    zones = zones_frame([zrow(A, 1, 'X', stop_mult=3.0)])
    r1 = run_z(zones, W1_DAILY, W1_HALF)
    r2 = run_z(zones, W1_DAILY, W1_HALF)
    assert r1.fills.equals(r2.fills)
    assert r1.events.equals(r2.events)
    assert r1.daily.equals(r2.daily)
    assert r1.clips_final.equals(r2.clips_final)
    assert r1.zones.equals(r2.zones)
    assert (json.dumps(r1.stats, sort_keys=True, default=str)
            == json.dumps(r2.stats, sort_keys=True, default=str))


# --- validation raises (fail-closed, BR-1) -----------------------------------

def test_t23_raise_etf_symbol_in_zones():
    """BR-2: a zones symbol marked asset_class='etf' in symbol_meta raises."""
    daily = daily_multi({A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({A: [(D1, s, 10.0, 10.05, 9.95, 10.0)
                           for s in ('am', 'pm')]})
    with pytest.raises(BandContractError):
        run_band_backtest_zones(
            zones_frame([zrow(ETF, 1, 'X')]), daily, half, wide_limits(daily),
            symbol_meta={ETF: {'asset_class': 'etf'}})


def test_t24_raise_priority_base():
    """BR-1: with zones active, intent priorities >= zone_priority_base
    raise (cross-layer priority ambiguity is forbidden).  The zones row
    uses a symbol DISJOINT from the intent frame (S-v14-15 overlap guard;
    the original same-symbol form predates that adjudication)."""
    daily = daily_multi({
        A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)],
        B: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({
        A: [(D1, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')]
        + [(D2, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')],
        B: [(D1, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')]
        + [(D2, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')]})
    intents = pl.DataFrame([{
        'symbol': A, 'side': 'buy', 'intent': None, 'decision_date': D1,
        'decision_session': 'am', 'source_signal': D1, 'expiry_date': None,
        'priority': 1000, 'target_notional': 10_000.0, 'target_weight': None}],
        schema=INTENT_SCHEMA)
    with pytest.raises(BandContractError):
        run_band_backtest_zones(
            zones_frame([zrow(B, 1, 'X')]), daily, half, wide_limits(daily),
            intents=intents)
    # a priority below the base passes validation (the zone candidate's
    # w_t floors below one lot -> done, no zone orders; the intent fills)
    intents2 = intents.with_columns(pl.lit(999, dtype=pl.Int64)
                                    .alias('priority'))
    res = run_band_backtest_zones(
        zones_frame([zrow(B, 1, 'X', w_t=0.001)]), daily, half,
        wide_limits(daily), intents=intents2)
    # the intent order fills; the zone candidate is below_min_lot
    assert res.fills.height == 1
    assert res.zones['exit_reason'].to_list() == ['below_min_lot']


def test_t25_raise_signal_date_not_calendar_day():
    """BR-1: signal_date must be a daily-panel calendar day (the boundary
    executes at the (signal_date,'pm') decision point)."""
    daily = daily_multi({A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({A: [(D1, s, 10.0, 10.05, 9.95, 10.0)
                           for s in ('am', 'pm')]})
    bad = D(2024, 1, 6)          # Saturday, absent from the panel
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', sd=bad)]), daily, half)


def test_t26_raise_k_seats_inconsistent():
    """BR-1: k_seats (and ind_cap / buffer_mult) must be constant within a
    signal_date."""
    daily = daily_multi({A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({A: [(D1, s, 10.0, 10.05, 9.95, 10.0)
                           for s in ('am', 'pm')]})
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', k_seats=1),
                           zrow(B, 2, 'Y', k_seats=2)]), daily, half)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', ind_cap=1),
                           zrow(B, 2, 'Y', ind_cap=2)]), daily, half)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', buffer_mult=2),
                           zrow(B, 2, 'Y', buffer_mult=3)]), daily, half)


def test_t27_raise_validation_misc():
    """BR-1 validation: zones+signals mutex, empty frame, duplicate
    (signal_date, symbol), duplicate rank, fracs sum != 1, half-supplied
    tp2, rank < 1, ladder list length mismatch, zones not a DataFrame."""
    daily = daily_multi({A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({A: [(D1, s, 10.0, 10.05, 9.95, 10.0)
                           for s in ('am', 'pm')]})
    # mutex with static signals (BR-1: zones and signals are exclusive)
    signals = pl.DataFrame([{
        'symbol': A, 'decision_date': D1, 'decision_session': 'pm',
        'side': 'buy', 'anchor_price': 10.0, 'priority': 1,
        'target_notional': 10_000.0, 'shares': None}],
        schema={'symbol': pl.String, 'decision_date': pl.Date,
                'decision_session': pl.String, 'side': pl.String,
                'anchor_price': pl.Float64, 'priority': pl.Int64,
                'target_notional': pl.Float64, 'shares': pl.Int64})
    with pytest.raises(BandContractError):
        run_band_backtest(signals, daily, half, wide_limits(daily),
                          zones=zones_frame([zrow(A, 1, 'X')]))
    # empty frame
    with pytest.raises(BandContractError):
        run_z(zones_frame([]), daily, half)
    # duplicate (signal_date, symbol)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X'), zrow(A, 2, 'Y')]), daily, half)
    # duplicate rank
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X'), zrow(B, 1, 'Y')]), daily, half)
    # fracs must sum to 1
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', fracs='0.4,0.4,0.1')]), daily, half)
    # tp2 half-supplied
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', tp2_mult=3.0, tp2_frac=None)]),
              daily, half)
    # rank < 1
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 0, 'X')]), daily, half)
    # ladder list length mismatch
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', offsets='0.5,1.5')]), daily, half)
    # zones must be a polars frame
    with pytest.raises(BandContractError):
        run_band_backtest_zones(
            [{'symbol': A}], daily, half, wide_limits(daily))


def test_t28_raise_tp2_frac_not_one():
    """S-v14-12 (adjudicated fail-closed 2026-09-20): a fractional tp2_frac
    is rejected -- v1.4 implements tp2 only as the full-clear tier
    (shares=None incl. corp-action odd lots); a fractional value would
    silently mis-size, so it fails closed instead of being ignored."""
    daily = daily_multi({A: [(D1, 10.0, 10.1, 9.9, 10.0),
                             (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({A: [(D1, s, 10.0, 10.05, 9.95, 10.0)
                           for s in ('am', 'pm')]
                       + [(D2, s, 10.0, 10.05, 9.95, 10.0)
                          for s in ('am', 'pm')]})
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', tp2_frac=0.7)]), daily, half)
    # tp2_frac = 1.0 (the only supported value) passes validation and the
    # candidate is admitted at (D1, pm) with a D2 live session
    res = run_z(zones_frame([zrow(A, 1, 'X', tp2_frac=1.0)]), daily, half)
    assert res.zones.height == 1


def test_t29_raise_zones_intent_symbol_overlap():
    """S-v14-15 (adjudicated fail-closed 2026-09-20): a zones symbol also
    present in the intent frame is undefined behavior (the zone WAC
    aggregates zladder buys only) -- rejected; disjoint symbols still
    compose on one ledger (cf. t17)."""
    daily = daily_multi({
        A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)],
        B: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 10.0, 10.1, 9.9, 10.0)]})
    half = half_multi({
        A: [(D1, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')]
        + [(D2, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')],
        B: [(D1, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')]
        + [(D2, s, 10.0, 10.05, 9.95, 10.0) for s in ('am', 'pm')]})
    intents = pl.DataFrame([{
        'symbol': A, 'side': 'buy', 'intent': None, 'decision_date': D1,
        'decision_session': 'pm', 'source_signal': D1, 'expiry_date': None,
        'priority': 1, 'target_notional': 10_000.0, 'target_weight': None}],
        schema=INTENT_SCHEMA)
    # zones symbol A overlaps the intent-frame symbol A -> reject
    with pytest.raises(BandContractError):
        run_band_backtest_zones(
            zones_frame([zrow(A, 1, 'X')]), daily, half, wide_limits(daily),
            intents=intents, initial_cash=200_000.0)
    # disjoint zones symbol B composes normally
    res = run_band_backtest_zones(
        zones_frame([zrow(B, 1, 'X')]), daily, half, wide_limits(daily),
        intents=intents, initial_cash=200_000.0)
    assert res.zones.height == 1 and 'zones' in res.stats


# --- v1.4.1 (contract section 10.8): optional tp1 (zero-tier take-profit) ---
# World W7: ladder fill -> invalidation cancels the unfilled tiers -> ratchet
# stop triggers.  sigma0=1, p0=10, w_t=0.05 -> 1000 target shares, tiers
# 400/400/200; stop_mult=3, invalid_mult=2 (invalidation line 8.0).
# tp1/tp2 are NULL for the whole frame: NO profit intent may appear; ladder,
# invalidation, ratchet stop and seat recycling must behave exactly as with
# a supplied tp1.
W9_DAILY = daily_multi({A: [
    (D1, 10.0, 10.1, 9.9, 10.0),
    (D2, 9.9, 9.95, 7.9, 9.0),
    (D3, 7.5, 7.6, 6.2, 6.3),
    (D4, 7.4, 7.5, 7.3, 7.4),
    (D5, 7.4, 7.5, 7.3, 7.4),
    (D6, 7.4, 7.5, 7.3, 7.4)]})
W9_HALF = half_multi({A: [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
    (D2, 'am', 9.9, 9.95, 9.2, 9.3), (D2, 'pm', 9.3, 9.4, 7.9, 9.0),
    (D3, 'am', 7.5, 7.6, 6.2, 6.3), (D3, 'pm', 7.4, 7.5, 7.3, 7.4),
    (D4, 'am', 7.4, 7.5, 7.3, 7.4), (D4, 'pm', 7.4, 7.5, 7.3, 7.4),
    (D5, 'am', 7.4, 7.5, 7.3, 7.4), (D5, 'pm', 7.4, 7.5, 7.3, 7.4),
    (D6, 'am', 7.4, 7.5, 7.3, 7.4), (D6, 'pm', 7.4, 7.5, 7.3, 7.4)]})


def test_t30_tp1_null_no_tp_intent():
    """v1.4.1 SS10.8: tp1_mult/tp1_frac null (columns present, values null)
    -> the zone RUNS with the zero-tier take-profit: ZERO -ztp orders (no
    fill, no event trace, no expiry counter), while the ladder fills,
    the invalidation line cancels the unfilled tiers and the 3-sigma
    ratchet stop clears the position exactly as in v1.4 (cf. t09).

    Hand-calc: a1 400@9.5 D2am (WAC 9.5); (D2,am) HWM 9.3 -> stop line 6.3;
    (D2,pm) session low 7.9 < invalidation 8.0 -> a2+a3 cancelled
    (tier_invalidated 2); stop line stays 6.3; D3am low 6.2 < 6.3 ->
    stop fills 400 at min(6.3, open 7.5) = 6.3.  Cash:
    200000 - 3805 + (2520 - 5 - 1.26) = 198708.74."""
    res = run_z(zones_frame([zrow(A, 1, 'X', tp1_mult=None, tp1_frac=None,
                                  tp2_mult=None, tp2_frac=None,
                                  stop_mult=3.0, invalid_mult=2.0)]),
                W9_DAILY, W9_HALF)
    # runs: exactly one ladder fill and one stop fill, NO profit fill
    f = res.fills
    assert f.height == 2
    assert f.filter(pl.col('order_id').str.contains('-ztp')).height == 0
    assert f.filter(pl.col('intent') == 'profit').height == 0
    buy = buys(res).row(0, named=True)
    assert abs(buy['price'] - 9.5) < 1e-9 and buy['shares'] == 400
    sell = sells(res).row(0, named=True)
    assert sell['fill_type'] == 'stop' and sell['intent'] == 'risk'
    assert abs(sell['price'] - 6.3) < 1e-9 and sell['shares'] == 400
    assert sell['date'] == D3 and sell['session'] == 'am'
    # zero take-profit intent across the WHOLE event log as well (a hung or
    # cancelled ztp order would leave its order_id on an event row)
    assert res.events.filter(
        pl.col('order_id').str.contains('-ztp')).height == 0
    assert zf(res)['tp_expired_sessions'] == 0
    assert zf(res)['tp_below_min_lot'] == 0
    # invalidation fired (a2+a3), ladder expired never, stop never armed
    inv = res.events.filter(pl.col('event') == 'zone_tier_invalidated')
    assert inv.height == 1 and abs(inv['ref_price'][0] - 7.9) < 1e-9
    assert zf(res)['tier_invalidated'] == 2 and zf(res)['tier_expired'] == 0
    assert zf(res)['stop_armed_events'] == 0
    # lifecycle: filled -> invalidated -> stop-cleared, WAC/lines as hand-calc
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'cooling' and z['exit_reason'] == 'stop_cleared'
    assert z['tier_filled_shares'] == '400,0,0'
    assert abs(z['wac_final'] - 9.5) < 1e-9
    assert abs(z['hwm_final'] - 9.3) < 1e-9
    assert abs(z['stop_line_final'] - 6.3) < 1e-9
    # hand-calc: 200000 - 3805 + 2513.74 = 198708.74
    assert abs(res.daily['settled_cash'][-1] - 198_708.74) < 1e-6
    # tp1 columns DROPPED entirely behave identically (column-absent form)
    zones_dropped = zones_frame(
        [zrow(A, 1, 'X', tp1_mult=None, tp1_frac=None,
              tp2_mult=None, tp2_frac=None, stop_mult=3.0, invalid_mult=2.0)]
    ).drop(['tp1_mult', 'tp1_frac'])
    res2 = run_z(zones_dropped, W9_DAILY, W9_HALF)
    assert res2.fills.equals(res.fills)
    assert res2.events.equals(res.events)
    assert res2.zones.equals(res.zones)
    assert abs(res2.daily['settled_cash'][-1] - 198_708.74) < 1e-6


def test_t31_tp1_null_tp2_set_rejected():
    """v1.4.1 fail-closed: tp1 null with tp2 set is rejected (the second
    tier cannot exist without the first) -- both the null form and the
    columns-dropped form; a half-supplied tp1 is rejected like tp2
    (v1.4 'supplied together' semantics, kept verbatim)."""
    base = dict(stop_mult=100.0)
    # tp1 null + tp2 set (null form)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', tp1_mult=None, tp1_frac=None,
                                tp2_mult=3.0, tp2_frac=1.0, **base)]),
              W2_DAILY, W2_HALF)
    # tp1 columns dropped + tp2 set (column-absent form)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', tp2_mult=3.0, tp2_frac=1.0,
                                **base)]).drop(['tp1_mult', 'tp1_frac']),
              W2_DAILY, W2_HALF)
    # half-supplied tp1 (one field without the other)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', tp1_mult=None, tp1_frac=0.5,
                                tp2_mult=None, tp2_frac=None, **base)]),
              W2_DAILY, W2_HALF)
    with pytest.raises(BandContractError):
        run_z(zones_frame([zrow(A, 1, 'X', tp1_mult=2.0, tp1_frac=None,
                                tp2_mult=None, tp2_frac=None, **base)]),
              W2_DAILY, W2_HALF)


def test_t32_tp1_present_same_as_v14():
    """v1.4.1: with tp1 SUPPLIED every v1.4 assertion and emission is kept
    verbatim.  World W2 + the v1.4 acceptance hand-calc (t04): b1 200@11.5
    D3am; on D4am b1 re-sized 100@11.5 then b2 full-clear 100@12.5; cash
    200877.65.  The same world with tp1/tp2 null emits no sell at all and
    the BUY side is field-identical between the two runs (only the
    take-profit layer is switched off)."""
    res = run_z(zones_frame([zrow(A, 1, 'X')]), W2_DAILY, W2_HALF)
    # v1.4 known values, unchanged (t04)
    s = sells(res)
    assert [abs(x - v) < 1e-9 for x, v in
            zip(s['price'].to_list(), [11.5, 11.5, 12.5])]
    assert s['shares'].to_list() == [200, 100, 100]
    assert s['intent'].to_list() == ['profit'] * 3
    assert abs(res.daily['settled_cash'][-1] - 200_877.65) < 1e-6
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'cooling' and z['exit_reason'] == 'tp_cleared'
    assert abs(z['wac_final'] - 9.5) < 1e-9
    # same world, tp1/tp2 null: zero take-profit, position held to the end
    res0 = run_z(zones_frame([zrow(A, 1, 'X', tp1_mult=None, tp1_frac=None,
                                   tp2_mult=None, tp2_frac=None)]),
                 W2_DAILY, W2_HALF)
    assert res0.fills.filter(
        pl.col('order_id').str.contains('-ztp')).height == 0
    assert res0.fills.filter(pl.col('side') == 'sell').height == 0
    assert res0.events.filter(
        pl.col('order_id').str.contains('-ztp')).height == 0
    assert zf(res0)['tp_expired_sessions'] == 0
    z0 = res0.zones.row(0, named=True)
    assert z0['phase_final'] == 'holding' \
        and z0['exit_reason'] == 'end_of_data'
    assert abs(z0['wac_final'] - 9.5) < 1e-9
    # hand-calc: 200000 - 3805 = 196195 (the a1 fill only)
    assert abs(res0.daily['settled_cash'][-1] - 196_195.0) < 1e-6
    # the buy side is field-identical: switching tp off touches nothing else
    assert buys(res).equals(buys(res0))


# --- v1.4.2 review fixes: R8 limit-down stop deferral, R10 stamp_buy cash ---

def strict_limit_frame(daily, on_date, down, up):
    """Real A-share-shaped limit band on ONE day (everything else wide).
    The wide +-90% band of ``wide_limits`` can never express a locked
    limit-down board, so R8 needs an explicit floor/ceiling row."""
    return daily.select(
        'symbol', 'date',
        pl.when(pl.col('date') == on_date).then(pl.lit(up))
          .otherwise(pl.col('close') * 1.9).alias('limit_up'),
        pl.when(pl.col('date') == on_date).then(pl.lit(down))
          .otherwise(pl.col('close') * 0.1).alias('limit_down'))


def test_t33_stop_limitdown_not_booked_as_filled():
    """R8 (v1.4.2).  Hand-calc: a1 400@9.5 D2am (WAC 9.5).  (D2,am) HWM
    = am close 9.3, stop line = 9.3 - 0.5 x 1.0 = 8.8.  D3am is a LOCKED
    limit-down board: OHLC all 7.2 = limit_down (pre-close 8.0 x 0.9), so
    the stop fill price min(8.8, 7.2) = 7.2 has no bid to trade against.
    The pre-fix engine booked 400@7.2 as a certain 'stop' fill; now: NO
    stop fill, a zone_stop_deferred_limitdown event, the K=3 fallback
    armed, deferred again on the same locked am board, and filled at the
    D3pm open 7.5 (board reopened) as market_fallback.  Cash:
    200000 - 3805 + (3000 - 5 - 1.5) = 199188.5 settled on D4."""
    daily = daily_multi({A: [
        (D1, 10.0, 10.1, 9.9, 10.0),
        (D2, 9.3, 9.5, 9.0, 8.0),
        (D3, 7.2, 7.7, 7.2, 7.6),
        (D4, 7.5, 7.6, 7.4, 7.5)]})
    half = half_multi({A: [
        (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
        (D2, 'am', 9.3, 9.5, 9.0, 9.3), (D2, 'pm', 9.3, 9.5, 9.0, 8.0),
        (D3, 'am', 7.2, 7.2, 7.2, 7.2), (D3, 'pm', 7.5, 7.7, 7.3, 7.6),
        (D4, 'am', 7.5, 7.6, 7.4, 7.5), (D4, 'pm', 7.5, 7.6, 7.4, 7.5)]})
    res = run_band_backtest_zones(
        zones_frame([zrow(A, 1, 'X', stop_mult=0.5)]), daily, half,
        strict_limit_frame(daily, D3, 7.2, 7.92))
    # no stop fill was booked on the locked board
    assert res.fills.filter(pl.col('fill_type') == 'stop').height == 0
    assert res.fills.filter(
        (pl.col('side') == 'sell') & (pl.col('date') == D3)
        & (pl.col('session') == 'am')).height == 0
    # the deferral is visible as an event and a stat
    assert res.events.filter(
        pl.col('event') == 'zone_stop_deferred_limitdown').height == 1
    assert zf(res)['stop_deferred_limitdown'] == 1
    # K=3 armed by the stop, deferred on the same locked am board ...
    assert res.events.filter(
        pl.col('event') == 'market_exit_deferred_limitdown').height == 1
    # ... then filled at the D3pm open as the open-market fallback
    fb = res.fills.filter(pl.col('fill_type') == 'market_fallback')
    assert fb.height == 1
    row = fb.row(0, named=True)
    assert row['date'] == D3 and row['session'] == 'pm'
    assert row['shares'] == 400 and abs(row['price'] - 7.5) < 1e-9
    assert zf(res)['stop_armed_events'] == 1
    assert zf(res)['stop_armed_resolved_fallback'] == 1
    z = res.zones.row(0, named=True)
    assert z['phase_final'] == 'cooling' \
        and z['exit_reason'] == 'stop_cleared'
    assert abs(z['wac_final'] - 9.5) < 1e-9
    assert abs(res.daily['settled_cash'][-1] - 199_188.5) < 1e-6


def test_t34_stamp_buy_in_cash_reservation():
    """R10 (v1.4.2).  Cash 40,020; four names, one tiny-offset tier each,
    1,000 shares @9.95 (D2am low 9.8 < 9.95), commission 5 per order, meta
    stamp_buy = 1% (a SYNTHETIC override that exists purely to expose the
    interface -- the A-share default is 0).  Full need per order = 9,950 +
    5 + 99.5 = 10,054.5, so only THREE orders fit: the pre-fix engine
    reserved notional + commission only (4 x 9,955 = 39,820 <= cash), let
    all four fill and drove settled cash to 40,020 - 39,820 - 398 = -198."""
    rows = [zrow(s, r, 'I%d' % r, offsets='0.05', fracs='1.0', w_t=0.25,
                 k_seats=4)
            for s, r in zip((A, B, C, D5X), (1, 2, 3, 4))]
    daily = daily_multi({
        A: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 10.0, 9.8, 9.9)],
        B: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 10.0, 9.8, 9.9)],
        C: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 10.0, 9.8, 9.9)],
        D5X: [(D1, 10.0, 10.1, 9.9, 10.0), (D2, 9.9, 10.0, 9.8, 9.9)]})
    half = half_multi({
        A: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 10.0, 9.8, 9.9), (D2, 'pm', 9.9, 10.0, 9.85, 9.9)],
        B: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 10.0, 9.8, 9.9), (D2, 'pm', 9.9, 10.0, 9.85, 9.9)],
        C: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
            (D2, 'am', 9.9, 10.0, 9.8, 9.9), (D2, 'pm', 9.9, 10.0, 9.85, 9.9)],
        D5X: [(D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.0, 10.05, 9.95, 10.0),
              (D2, 'am', 9.9, 10.0, 9.8, 9.9), (D2, 'pm', 9.9, 10.0, 9.85, 9.9)]})
    meta = {s: {'asset_class': 'stock', 'stamp_buy': 0.01}
            for s in (A, B, C, D5X)}
    res = run_band_backtest_zones(
        zones_frame(rows), daily, half, wide_limits(daily),
        symbol_meta=meta, initial_cash=40_020.0)
    f = buys(res)
    assert f.height == 3
    assert all(abs(p - 9.95) < 1e-9 for p in f['price'].to_list())
    assert f['shares'].to_list() == [1000, 1000, 1000]
    # the rank-4 name lost the cash race, not one of the winners
    assert D5X not in set(f['symbol'].to_list())
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 1
    assert res.events.filter(
        pl.col('event') == 'void_insufficient_cash')['symbol'].to_list() == [D5X]
    # settled cash never goes negative: 40,020 - 3 x 10,054.5 = 9,856.5
    assert min(res.daily['settled_cash'].to_list()) >= -1e-9
    assert abs(res.daily['settled_cash'][-1] - 9_856.5) < 1e-6
    # the booked debit carries the stamp: one order = 10,054.5 exactly
    one = f.row(0, named=True)
    assert abs(one['net_cash_flow'] + 10_054.5) < 1e-6
    assert abs(one['stamp_tax'] - 99.5) < 1e-9
