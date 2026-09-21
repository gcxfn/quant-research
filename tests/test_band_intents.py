"""P3 band-contract engine v1.1 intent-layer acceptance tests.

Maps to docs/plans/p3-band-contract.md section 7.7-M3 (supplement:
execution subject = engine intent layer) and docs/research/
exp-20260918-p3r2-band-v1-readjudication-prereg.md section 9 revisions
2-4.  The host submits ONE static intent frame; the engine owns the order
lifecycle: per-decision-point mechanical re-anchor (11:30 = am.close,
15:00 = official close), quantity recomputed from target notional x
decision-point equity snapshot, fill-stop, expiry / same-name override /
cap-void termination, M1 K-streak keyed (symbol, intent, source).

The 21 static-frame tests in test_band_contract.py are unchanged; this
file adds only intent-mode coverage.  All data inline synthetic Polars
frames; no strategy judgement; zero trial consumption.

  test_i1_fill_stop          intent stops on first fill (no re-fill)
  test_i2_reanchor_streak    unfilled risk intent re-issued and re-anchored
                             at every decision point; K streak continues
  test_i3_expiry             expiry terminates the intent at the boundary
  test_i4_override           same-symbol later intent cancels the earlier
                             one and resets the streak (M1 source change)
  test_i5_rescale_weight     rescale-down recomputes explicit shares from
                             target weight x snapshot at each decision point
  test_i6_engine3_regression ENGINE-3: risk sell with bar but no stk_limit
                             row -- no crash, void counted into K (v0
                             ruling #2/#3 restored)
  test_i7_determinism        same input twice -> bit-identical outputs
  test_i8_guards             input validation (mutually exclusive sizing,
                             duplicate first decisions, both entry points)
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
)

D = date
SYM = 'sh.600001'

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


def daily_bars(symbol, rows):
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def half_bars(symbol, rows):
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows],
    })


def auto_limits(daily):
    return daily.select(
        'symbol', 'date',
        (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'),
    )


def run_i(intents, daily, half, limits=None, **kw):
    limits = limits if limits is not None else auto_limits(daily)
    return run_band_backtest_intents(intents, daily, half, limits,
                                     initial_cash=200_000.0, **kw)


D1, D2, D3, D4, D5, D6 = (D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9))
S1, S2 = D(2024, 1, 2), D(2024, 1, 3)

# world A: D1 dip (buy fills), then rise -- used by fill-stop / expiry
DAILY_A = daily_bars(SYM, [
    (D1, 10.0, 10.1, 9.95, 9.6 * 0 + 10.2),
    (D2, 10.9, 11.6, 11.0, 11.5),
    (D3, 11.4, 11.9, 11.3, 11.8),
    (D4, 11.7, 12.2, 11.6, 12.1),
    (D5, 12.0, 12.5, 11.9, 12.4),
    (D6, 12.3, 12.8, 12.2, 12.7)])
HALF_A = half_bars(SYM, [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 10.1, 10.3, 10.05, 10.2),
    (D2, 'am', 10.9, 11.3, 11.0, 11.2), (D2, 'pm', 11.3, 11.6, 11.3, 11.5),
    (D3, 'am', 11.4, 11.8, 11.35, 11.7), (D3, 'pm', 11.7, 12.0, 11.65, 11.8),
    (D4, 'am', 11.7, 12.1, 11.65, 12.0), (D4, 'pm', 12.0, 12.35, 11.95, 12.1),
    (D5, 'am', 12.0, 12.4, 11.95, 12.3), (D5, 'pm', 12.3, 12.6, 12.25, 12.4),
    (D6, 'am', 12.3, 12.7, 12.25, 12.6), (D6, 'pm', 12.6, 12.9, 12.55, 12.7)])

# world B: D1 dip (buy fills @10), then fall -- sell never penetrates until
# the K=3 fallback
DAILY_B = daily_bars(SYM, [
    (D1, 10.0, 10.1, 9.5, 9.6),
    (D2, 9.4, 9.5, 9.0, 9.1),
    (D3, 8.9, 9.0, 8.55, 8.6),
    (D4, 8.5, 8.55, 8.4, 8.5),
    (D5, 8.5, 8.52, 8.48, 8.5),
    (D6, 8.5, 8.52, 8.48, 8.5)])
HALF_B = half_bars(SYM, [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 9.9, 10.0, 9.5, 9.6),
    (D2, 'am', 9.4, 9.5, 9.2, 9.3), (D2, 'pm', 9.2, 9.25, 9.0, 9.1),
    (D3, 'am', 8.9, 9.0, 8.7, 8.75), (D3, 'pm', 8.7, 8.7, 8.55, 8.6),
    (D4, 'am', 8.5, 8.55, 8.45, 8.5), (D4, 'pm', 8.5, 8.55, 8.4, 8.5),
    (D5, 'am', 8.5, 8.52, 8.48, 8.5), (D5, 'pm', 8.5, 8.51, 8.49, 8.5),
    (D6, 'am', 8.5, 8.52, 8.48, 8.5), (D6, 'pm', 8.5, 8.51, 8.49, 8.5)])

# world C: D1 fill @10; D2 opens ~12 (rescale emits 200, fades unfilled);
# D2 close 10.4 -> recomputed emission 100 fills D3am (per-decision recompute)
DAILY_C = daily_bars(SYM, [
    (D1, 10.0, 10.1, 9.5, 9.6),
    (D2, 11.9, 12.05, 10.85, 11.0),
    (D3, 11.0, 11.2, 10.9, 11.1),
    (D4, 10.8, 10.85, 10.75, 10.8),
    (D5, 10.8, 10.85, 10.75, 10.8),
    (D6, 10.8, 10.85, 10.75, 10.8)])
HALF_C = half_bars(SYM, [
    (D1, 'am', 10.0, 10.05, 9.9, 10.0), (D1, 'pm', 9.9, 10.0, 9.5, 9.6),
    (D2, 'am', 11.9, 12.05, 11.85, 12.0), (D2, 'pm', 11.5, 11.9, 10.85, 11.0),
    (D3, 'am', 11.0, 11.2, 10.95, 11.1), (D3, 'pm', 11.1, 11.15, 11.0, 11.1),
    (D4, 'am', 10.8, 10.85, 10.75, 10.8), (D4, 'pm', 10.8, 10.83, 10.78, 10.8),
    (D5, 'am', 10.8, 10.85, 10.75, 10.8), (D5, 'pm', 10.8, 10.83, 10.78, 10.8),
    (D6, 'am', 10.8, 10.85, 10.75, 10.8), (D6, 'pm', 10.8, 10.83, 10.78, 10.8)])


def test_i1_fill_stop():
    """One buy intent = at most one fill: the engine stops re-issuing after
    the intent's order fills (revision 2 '成交即停')."""
    res = run_i(intents_frame([
        it(SYM, 'buy', D1, 'am', S1, target=10_000)]), DAILY_B, HALF_B)
    f = res.fills
    assert f.height == 1 and f['side'][0] == 'buy'
    assert f['shares'][0] == 1000 and abs(f['price'][0] - 10.0) < 1e-9
    assert f['decision_date'][0] == D1 and f['decision_session'][0] == 'am'
    assert f['date'][0] == D1 and f['session'][0] == 'pm'
    # no order activity for the symbol after the fill session
    late = res.events.filter((pl.col('symbol') == SYM)
                             & (pl.col('date') > D1))
    assert late.height == 0
    il = res.stats['intent_layer']
    assert il['stopped_filled'] == 1 and il['orders_generated'] >= 1
    life = res.events.filter(pl.col('event') == 'intent_lifecycle')
    assert life.height == 1 and 'filled' in life['detail'][0]
    # hand-calc: cash 200000 - 10000 - 5 commission = 189995
    assert abs(res.daily['settled_cash'][-1] - 189_995.0) < 1e-6


def test_i2_reanchor_streak():
    """Unfilled risk intent: re-issued at EVERY decision point with the
    re-anchored price (am=am.close, pm=official close); the M1 streak
    continues across re-anchors and arms the K=3 fallback at 3."""
    res = run_i(intents_frame([
        it(SYM, 'buy', D1, 'am', S1, target=10_000),
        it(SYM, 'sell', D2, 'am', S2, intent='risk')]), DAILY_B, HALF_B)
    # buy filled D1 pm; sell full-exit never penetrates (falling market)
    np_events = res.events.filter(
        (pl.col('event') == 'not_penetrated') & (pl.col('symbol') == SYM))
    # emissions: (D2,am)->pm, (D2,pm)->D3am, (D3,am)->D3pm; the (D3,pm)
    # emission at D4am is consumed by the fallback
    assert np_events.height == 3
    limits = np_events.sort('date', 'session')['limit_price'].to_list()
    assert [abs(x - v) < 1e-9 for x, v in zip(limits, [9.3, 9.1, 8.75])]
    details = np_events.sort('date', 'session')['detail'].to_list()
    assert 'risk K streak 1' in details[0]
    assert 'risk K streak 2' in details[1]
    assert 'risk K streak 3' in details[2]
    assert (res.stats['k3_fallback']['armed'] == 1
            and res.stats['k3_fallback']['executed'] == 1)
    fb = res.fills.filter(pl.col('fill_type') == 'market_fallback')
    assert fb.height == 1 and fb['shares'][0] == 1000
    assert fb['date'][0] == D4 and fb['session'][0] == 'am'
    assert abs(fb['price'][0] - 8.5) < 1e-9


def test_i3_expiry():
    """expiry_date terminates the intent: emissions stop once the live
    session would reach expiry; a lifecycle event is recorded."""
    res = run_i(intents_frame([
        it(SYM, 'buy', D1, 'am', S1, target=10_000, expiry=D3)]),
        DAILY_A, HALF_A)
    sym_events = res.events.filter(pl.col('symbol') == SYM)
    # emissions live D1pm (anchor 10.0, not penetrated), D2am (anchor 10.2
    # below the gap-up day's limit_down -> void_limit_out_of_range), D2pm
    # (anchor 11.2, not penetrated); the (D2,pm) decision would live at
    # D3 == expiry -> terminated instead
    assert sym_events['event'].to_list() == [
        'not_penetrated', 'void_limit_out_of_range', 'not_penetrated']
    assert res.fills.height == 0
    assert res.stats['intent_layer']['terminated_expired'] == 1
    life = res.events.filter(pl.col('event') == 'intent_lifecycle')
    assert life.height == 1 and 'expired' in life['detail'][0]
    assert res.stats['intent_layer']['stopped_filled'] == 0


def test_i4_override():
    """A later same-symbol intent cancels the earlier one from its first
    decision point (streak resets via the M1 source change)."""
    res = run_i(intents_frame([
        it(SYM, 'buy', D1, 'am', S1, target=10_000),
        it(SYM, 'sell', D1, 'pm', S1, intent='risk'),
        it(SYM, 'sell', D2, 'am', S2, intent='risk')]), DAILY_B, HALF_B)
    life = res.events.filter(pl.col('event') == 'intent_lifecycle')
    over = life.filter(pl.col('detail').str.contains('overridden'))
    assert over.height == 1 and S1.isoformat() in over['detail'][0]
    # intent1 emitted exactly once (live D2am, streak 1), then overridden;
    # intent2 restarts the streak at 0 -> its 3 unfilled sessions are
    # (D2,pm), (D3,am), (D3,pm) -> fallback at the NEXT session (D4,am)
    assert (res.stats['k3_fallback']['armed'] == 1
            and res.stats['k3_fallback']['executed'] == 1)
    fb = res.fills.filter(pl.col('fill_type') == 'market_fallback')
    assert fb.height == 1 and fb['date'][0] == D4 and fb['session'][0] == 'am'
    first_sell = res.events.filter(
        (pl.col('event') == 'not_penetrated') & (pl.col('symbol') == SYM)
        & (pl.col('date') == D2) & (pl.col('session') == 'am'))
    assert first_sell.height == 1
    # streak reset proof: the first intent2 emission reports streak 1 (not 2)
    second_first = res.events.filter(
        (pl.col('event') == 'not_penetrated') & (pl.col('symbol') == SYM)
        & (pl.col('date') == D2) & (pl.col('session') == 'pm'))
    assert 'risk K streak 1' in second_first['detail'][0]


def test_i5_rescale_weight():
    """rescale-down with target weight: the explicit share count is
    recomputed from weight x decision-point snapshot / anchor at EVERY
    decision point (revision 3).  First emission (anchor 12.0) = 200 shares,
    unfilled; second emission recomputed at the 10.4 close = 100 shares,
    filled -> proves the per-decision recompute.  The fill stops the intent
    (revision 2 '成交即停'): no third emission."""
    res = run_i(intents_frame([
        it(SYM, 'buy', D1, 'am', S1, target=10_000),
        it(SYM, 'sell', D2, 'am', S2, intent='risk', weight=0.05)]),
        DAILY_C, HALF_C)
    # first emission (200 @12.0) unfilled: D2pm high 11.9 <= 12.0
    np_events = res.events.filter(
        (pl.col('event') == 'not_penetrated') & (pl.col('symbol') == SYM))
    assert np_events.height == 1
    assert abs(np_events['limit_price'][0] - 12.0) < 1e-9
    # second emission recomputed at the 11.0 close (snapshot 200,995 x 5% /
    # 11.0 -> target 900) = 100 shares -> fills at the D3am session
    sells = res.fills.filter(pl.col('side') == 'sell')
    assert sells.height == 1 and sells['shares'][0] == 100
    assert abs(sells['price'][0] - 11.0) < 1e-9
    assert sells['date'][0] == D3 and sells['session'][0] == 'am'
    # fill-stop: no further emissions after the fill; BOTH intents stopped
    # on fill (the entry buy and the risk reduce)
    assert res.stats['intent_layer']['stopped_filled'] == 2
    late = res.events.filter((pl.col('symbol') == SYM)
                             & (pl.col('date') > D3))
    assert late.height == 0
    clips = res.clips_final.filter(pl.col('symbol') == SYM)
    assert clips['shares'].sum() == 900


def test_i6_engine3_regression():
    """ENGINE-3 regression: a live risk sell on a session WITH a bar but
    WITHOUT stk_limit rows must not crash; the void is disclosed and the
    session counts into the K streak (v0 ruling #2/#3 restored)."""
    daily = DAILY_B
    half = HALF_B
    limits = auto_limits(daily).filter(
        ~pl.col('date').is_in([D2, D3, D4]))
    signals = pl.DataFrame([
        {'symbol': SYM, 'decision_date': D1, 'decision_session': 'pm',
         'side': 'sell', 'intent': 'risk', 'anchor_price': 9.6,
         'priority': 1, 'target_notional': None, 'shares': None,
         'source_signal': D1},
        {'symbol': SYM, 'decision_date': D2, 'decision_session': 'am',
         'side': 'sell', 'intent': 'risk', 'anchor_price': 9.3,
         'priority': 1, 'target_notional': None, 'shares': None,
         'source_signal': D1},
        {'symbol': SYM, 'decision_date': D2, 'decision_session': 'pm',
         'side': 'sell', 'intent': 'risk', 'anchor_price': 9.1,
         'priority': 1, 'target_notional': None, 'shares': None,
         'source_signal': D1},
    ], schema={'symbol': pl.String, 'decision_date': pl.Date,
               'decision_session': pl.String, 'side': pl.String,
               'intent': pl.String, 'anchor_price': pl.Float64,
               'priority': pl.Int64, 'target_notional': pl.Float64,
               'shares': pl.Int64, 'source_signal': pl.Date})
    res = run_band_backtest(signals, daily, half, limits,
                            initial_cash=200_000.0)
    voids = res.events.filter(pl.col('event') == 'void_no_limit_info')
    assert voids.height == 3
    assert all('None' in d for d in voids['detail'].to_list())
    assert res.stats['k3_fallback']['armed'] == 1  # all 3 voids counted


def test_i7_determinism():
    """Same intent input twice -> bit-identical outputs."""
    intents = intents_frame([
        it(SYM, 'buy', D1, 'am', S1, target=10_000),
        it(SYM, 'sell', D2, 'am', S2, intent='risk', weight=0.05)])
    r1 = run_i(intents, DAILY_C, HALF_C)
    r2 = run_i(intents, DAILY_C, HALF_C)
    assert r1.fills.equals(r2.fills)
    assert r1.events.equals(r2.events)
    assert r1.daily.equals(r2.daily)
    assert r1.clips_final.equals(r2.clips_final)
    assert (json.dumps(r1.stats, sort_keys=True, default=str)
            == json.dumps(r2.stats, sort_keys=True, default=str))


def test_i8_guards():
    """Input guards: mutually exclusive entry points and sizing fields,
    duplicate same-symbol first decision points."""
    daily, half = DAILY_A, HALF_A
    good = intents_frame([it(SYM, 'buy', D1, 'am', S1, target=10_000)])
    with pytest.raises(BandContractError):
        run_band_backtest(good, daily, half, auto_limits(daily),
                          initial_cash=200_000.0, intent_frame=good)
    with pytest.raises(BandContractError):
        run_i(intents_frame([it(SYM, 'sell', D1, 'am', S1, intent='risk',
                                target=5_000, weight=0.05)]), daily, half)
    with pytest.raises(BandContractError):
        run_i(intents_frame([it(SYM, 'buy', D1, 'am', S1)]), daily, half)
    with pytest.raises(BandContractError):
        run_i(intents_frame([
            it(SYM, 'buy', D1, 'am', S1, target=10_000),
            it(SYM, 'sell', D1, 'am', S2, intent='risk')]), daily, half)
