"""Dynamic intent-provider entry tests (2026-09-21 mainline task).

Covers the state transition the main plan requires before the hybrid
mainline can be accepted: "old recommendations void, the next plan
version re-issues explicitly, the risk fallback counts on":

  d1  ledger feedback + explicit re-issue   first buy never trades ->
      the half-day order dies, the intent is expired_halfday, the
      provider reads the untouched single-ledger state at the next
      decision point and re-submits; the re-issued order fills
  d2  risk carry, K=3 across half-days     an unfilled risk sell
      re-anchors at EVERY decision point, the streak counts three
      live sessions, then the armed fallback market-exits at the next
      open (fees hand-checked)
  d3  T+1 lock, partial sell, cash math    a stock bought on day-2 am
      cannot be sold in day-2 pm (void_t1_locked, streak counts); the
      carried risk order fills next morning at half the position; the
      settled-cash buckets and fees are hand-checked
  d4  cooldown recovery via feedback       an ETF round trip, then the
      provider's own cooldown logic (driven ONLY by the ledger) holds
      off re-buying for two decision points and re-enters after
  d5  provider guards                      non-list return, non-dict
      row, a row stamped with an EARLIER decision point, and a
      duplicate first decision point are all rejected fail-closed
  d6  suspension semantics under halfday   an unpriceable normal buy
      voids (expired_halfday_no_anchor, no auto re-hang); a risk sell
      whose live session is suspended freezes and re-issues next
      half-day (fill lands the day after)
  d7  static seed + dynamic extension      a static frame row and a
      provider row coexist; later same-symbol injection overrides the
      standing risk intent (an armed fallback would survive, verified
      indirectly via risk_state absence)

All data inline synthetic Polars frames (no real symbols); no strategy
judgement; zero trial consumption.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.backtest.band_engine import BandContractError, run_band_backtest_intents

D1, D2, D3, D4 = (date(2024, 1, 2 + i) for i in range(4))
ETF = 'sh.510300'
OTHER = 'sh.510050'
STOCK = 'sh.600001'


def daily_frame(symbol, rows):
    """rows: (date, open, high, low, close, preclose)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'preclose': [float(r[5]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def half_frame(symbol, rows):
    """rows: (date, session, open, high, low, close)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows]})


def limits_frame(daily, symbol=ETF):
    return daily.filter(pl.col('symbol') == symbol).select(
        'symbol', 'date',
        (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'))


def etf_meta():
    return {ETF: {"asset_class": "etf", "band": .1, "t_plus": 0}}


def row(symbol, side, day, sess, source, *, intent=None, target=None,
        weight=None, priority=1):
    return {'symbol': symbol, 'side': side, 'intent': intent,
            'decision_date': day, 'decision_session': sess,
            'source_signal': source, 'expiry_date': None,
            'priority': priority,
            'target_notional': None if target is None else float(target),
            'target_weight': None if weight is None else float(weight)}


def run_dyn(provider, daily, half, limits, *, intents=None, meta=None,
            initial_cash=200_000.0):
    return run_band_backtest_intents(
        intents, daily, half, limits,
        symbol_meta=meta if meta is not None else etf_meta(),
        initial_cash=initial_cash, execution_clock="halfday",
        intent_provider=provider)


# ---------------------------------------------------------------------------
# d1: ledger feedback + explicit re-issue
# ---------------------------------------------------------------------------

def test_d1_ledger_feedback_and_explicit_reissue():
    daily = daily_frame(ETF, [
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 2.0, 2.01, 1.95, 1.96, 2.0),
        (D3, 1.96, 1.97, 1.94, 1.95, 1.96)])
    half = half_frame(ETF, [
        (D1, 'am', 2.0, 2.01, 1.99, 2.0),
        (D1, 'pm', 2.0, 2.01, 2.0, 2.0),    # low == anchor: never trades
        (D2, 'am', 2.0, 2.01, 1.99, 2.0),
        (D2, 'pm', 2.0, 2.01, 1.95, 1.96),  # low 1.95 < 2.0: fills
        (D3, 'am', 1.96, 1.97, 1.94, 1.95),
        (D3, 'pm', 1.95, 1.96, 1.94, 1.95)])
    seen = []

    def provider(day, sess, ledger):
        seen.append({'day': day, 'sess': sess, 'ledger': ledger})
        if (day, sess) == (D1, 'am'):
            return [row(ETF, 'buy', D1, 'am', D1, target=20_000)]
        if (day, sess) == (D2, 'am'):
            return [row(ETF, 'buy', D2, 'am', D2, target=20_000)]
        return None

    res = run_dyn(provider, daily, half, limits_frame(daily))

    # provider was called at every decision point (3 days x 2)
    assert [(s['day'], s['sess']) for s in seen] == [
        (D1, 'am'), (D1, 'pm'), (D2, 'am'), (D2, 'pm'), (D3, 'am'), (D3, 'pm')]

    # ledger at (D1, 'pm'): untouched account, nothing carried forward
    led = seen[1]['ledger']
    assert led['date'] == D1 and led['session'] == 'pm'
    assert led['cash'] == 200_000.0
    assert led['pending_am_to_pm'] == 0.0 and led['pending_next_day'] == 0.0
    assert led['equity_snapshot'] == 200_000.0
    assert led['positions'] == []

    # the first buy never traded and the intent is void for its half-day;
    # BOTH buys are stamped expired_halfday at generation (an order lives
    # one half-day whether or not it fills -- fill-stop is a no-op on an
    # already-terminated intent)
    assert res.fills.height == 1
    assert res.fills['date'][0] == D2 and res.fills['session'][0] == 'pm'
    assert res.stats['intent_layer']['terminated_expired_halfday'] == 2
    assert res.stats['intent_layer']['dynamic_injected'] == 2
    assert res.stats['intent_layer']['provider_calls'] == 6
    assert res.stats['dynamic_layer']['dynamic_injected'] == 2
    assert res.stats['order_generation'] == 'engine_intents_dynamic'

    # fill: 10,000 x 2.0, commission min-5 binds, no stamp
    f = res.fills.row(0, named=True)
    assert f['shares'] == 10_000 and f['price'] == 2.0
    assert f['commission'] == 5.0 and f['stamp_tax'] == 0.0

    # ledger at (D2, 'pm') reflects the fill: cash 179,995, one clip
    led2 = seen[3]['ledger']
    assert led2['cash'] == pytest.approx(179_995.0)
    assert led2['equity_snapshot'] == pytest.approx(179_995.0 + 10_000 * 1.96)
    pos = led2['positions']
    assert len(pos) == 1 and pos[0]['symbol'] == ETF
    assert pos[0]['shares'] == 10_000
    # T+0 ETF: the whole clip is sellable in the upcoming pm session
    assert pos[0]['sellable_next_session'] == 10_000
    assert pos[0]['clips'][0]['acquired'] == D2.isoformat()


# ---------------------------------------------------------------------------
# d2: risk carry, K = 3 across half-days
# ---------------------------------------------------------------------------

def test_d2_risk_carry_three_halfdays_fallback():
    daily = daily_frame(ETF, [
        (D1, 2.00, 2.01, 1.90, 1.95, 2.00),
        (D2, 1.95, 1.96, 1.90, 1.90, 1.95),
        (D3, 1.90, 1.90, 1.85, 1.87, 1.90),
        (D4, 1.80, 1.85, 1.75, 1.82, 1.87)])
    half = half_frame(ETF, [
        (D1, 'am', 2.00, 2.01, 1.99, 2.00),
        (D1, 'pm', 2.00, 2.01, 1.90, 1.95),
        (D2, 'am', 1.95, 1.96, 1.94, 1.95),
        (D2, 'pm', 1.95, 1.95, 1.90, 1.90),   # high == anchor: unfilled (1)
        (D3, 'am', 1.90, 1.90, 1.85, 1.88),   # unfilled (2)
        (D3, 'pm', 1.88, 1.88, 1.85, 1.87),   # unfilled (3) -> armed
        (D4, 'am', 1.80, 1.85, 1.75, 1.82),   # fallback at open 1.80
        (D4, 'pm', 1.82, 1.84, 1.80, 1.83)])

    def provider(day, sess, ledger):
        if (day, sess) == (D1, 'am'):
            return [row(ETF, 'buy', D1, 'am', D1, target=20_000)]
        if (day, sess) == (D2, 'am'):
            return [row(ETF, 'sell', D2, 'am', D2, intent='risk')]
        return None

    res = run_dyn(provider, daily, half, limits_frame(daily))

    assert res.stats['k3_fallback']['armed'] == 1
    assert res.stats['k3_fallback']['executed'] == 1
    # risk order re-issued at every decision point after D2 am: the
    # intent layer never expires it (terminated_expired_halfday counts
    # only the buy)
    il = res.stats['intent_layer']
    assert il['terminated_expired_halfday'] == 1
    assert il['orders_generated'] == 5   # 1 buy + 4 risk re-issues

    sells = res.fills.filter(pl.col('side') == 'sell')
    assert sells.height == 1
    s = sells.row(0, named=True)
    assert s['fill_type'] == 'market_fallback'
    assert s['date'] == D4 and s['session'] == 'am'
    assert s['price'] == 1.80 and s['shares'] == 10_000
    # cash: 200,000 - 20,000 - 5 (buy) + 18,000 - 5 (fallback) = 197,990
    # (the am fallback proceeds settle into cash at the D4 pm boundary)
    assert res.daily['settled_cash'][-1] == pytest.approx(197_990.0)
    # nothing held any more
    assert res.clips_final.height == 0


# ---------------------------------------------------------------------------
# d3: T+1 lock, partial sell, fee math (stock)
# ---------------------------------------------------------------------------

def test_d3_t1_lock_partial_sell_and_fees():
    daily = daily_frame(STOCK, [
        (D1, 10.0, 10.05, 9.95, 10.0, 10.0),
        (D2, 10.0, 10.10, 9.90, 10.0, 10.0),
        (D3, 10.0, 10.10, 9.95, 10.0, 10.0)])
    half = half_frame(STOCK, [
        (D1, 'am', 10.0, 10.05, 9.99, 10.0),
        (D1, 'pm', 10.0, 10.05, 9.99, 10.0),
        (D2, 'am', 10.0, 10.05, 9.90, 10.0),   # buy fills at 10.0
        (D2, 'pm', 10.0, 10.05, 9.98, 10.0),   # risk sell T+1-locked
        (D3, 'am', 10.0, 10.10, 9.95, 10.05),  # carried sell fills 10.0
        (D3, 'pm', 10.0, 10.05, 9.95, 10.0)])
    ledgers = []

    def provider(day, sess, ledger):
        ledgers.append(ledger)
        if (day, sess) == (D1, 'pm'):
            # 20% of equity: below the 25% single-name cap
            return [row(STOCK, 'buy', D1, 'pm', D1, target=40_000)]
        if (day, sess) == (D2, 'am'):
            return [row(STOCK, 'sell', D2, 'am', D2, intent='risk',
                        target=20_000)]
        return None

    res = run_dyn(provider, daily, half, limits_frame(daily, symbol=STOCK),
                  meta={STOCK: {"asset_class": "stock", "band": .1,
                                "t_plus": 1}})

    assert res.fills.height == 2
    buy, sell = res.fills.rows(named=True)

    # buy: 4,000 shares at 10.0, commission min-5 binds
    assert (buy['date'], buy['session']) == (D2, 'am')
    assert buy['shares'] == 4_000 and buy['price'] == 10.0
    assert buy['commission'] == pytest.approx(5.0)

    # the same-day pm risk attempt is void t1-locked and counts into K
    ev = res.events.filter(pl.col('event') == 'void_t1_locked')
    assert ev.height == 1
    assert 'risk K' in ev['detail'][0]

    # carried sell fills next morning: half the position, stamp 0.05%
    assert (sell['date'], sell['session']) == (D3, 'am')
    assert sell['shares'] == 2_000 and sell['price'] == 10.0
    assert sell['fill_type'] == 'limit'
    assert sell['commission'] == pytest.approx(5.0)
    assert sell['stamp_tax'] == pytest.approx(20_000 * 0.0005)

    # ledger at the (D2, 'am') decision point, right after the fill: the
    # shares exist but T+1 locks every clip for the upcoming pm session;
    # by the (D2, 'pm') decision the next session is tomorrow's am and
    # the whole position reads sellable again
    led_am = ledgers[2]              # (D2, 'am')
    pos_am = led_am['positions'][0]
    assert pos_am['symbol'] == STOCK and pos_am['shares'] == 4_000
    assert pos_am['sellable_next_session'] == 0
    led_pm = ledgers[3]              # (D2, 'pm')
    assert led_pm['positions'][0]['sellable_next_session'] == 4_000

    # cash: 200,000 - 40,000 - 5 + 20,000 - 5 - 10 = 179,980
    # (am-sale proceeds settle into the same-day pm bucket)
    assert res.daily['settled_cash'][-1] == pytest.approx(179_980.0)
    remaining = res.clips_final.filter(pl.col('symbol') == STOCK)
    assert remaining['shares'].sum() == 2_000


# ---------------------------------------------------------------------------
# d4: cooldown recovery driven only by ledger feedback
# ---------------------------------------------------------------------------

def test_d4_cooldown_recovery_via_ledger():
    daily = daily_frame(ETF, [
        (D1, 2.0, 2.2, 1.9, 2.0, 2.0),
        (D2, 2.0, 2.2, 1.9, 2.0, 2.0),
        (D3, 2.0, 2.2, 1.9, 2.0, 2.0)])
    half = half_frame(ETF, [
        (D1, 'am', 2.0, 2.01, 1.99, 2.0),
        (D1, 'pm', 2.0, 2.01, 1.9, 1.95),   # buy fills at 2.0
        (D2, 'am', 2.1, 2.2, 2.05, 2.15),   # profit sell fills at 2.0
        (D2, 'pm', 2.15, 2.2, 2.1, 2.1),
        (D3, 'am', 2.0, 2.05, 1.95, 2.0),   # re-entry anchors at 2.0
        (D3, 'pm', 2.0, 2.05, 1.9, 1.95)])  # re-entry fills at 2.0
    state = {'cooldown_left': 0}

    def provider(day, sess, ledger):
        held = {p['symbol']: p['shares'] for p in ledger['positions']}
        if (day, sess) == (D1, 'am'):
            return [row(ETF, 'buy', D1, 'am', D1, target=20_000)]
        if (day, sess) == (D1, 'pm') and held.get(ETF):
            return [row(ETF, 'sell', D1, 'pm', D1, intent='profit')]
        # cooldown bookkeeping from ledger feedback only: a position that
        # disappeared after a sell starts a two-decision-point cooldown
        if (day, sess) == (D2, 'am') and not held.get(ETF):
            state['cooldown_left'] = 2
        if state['cooldown_left'] > 0:
            state['cooldown_left'] -= 1
            return None
        if (day, sess) == (D3, 'am'):
            return [row(ETF, 'buy', D3, 'am', D3, target=20_000)]
        return None

    res = run_dyn(provider, daily, half, limits_frame(daily))

    assert res.fills.height == 3
    sides = list(zip(res.fills['date'], res.fills['side']))
    assert sides == [(D1, 'buy'), (D2, 'sell'), (D3, 'buy')]
    # cooldown held: no order between the D2 am sell and the D3 am re-buy
    assert res.stats['intent_layer']['dynamic_injected'] == 3
    # final cash: 200,000 - 20,005 (buy) + 19,995 (sell) - 20,005
    # (re-buy) = 179,985 with 10,000 shares re-held
    assert res.daily['settled_cash'][-1] == pytest.approx(179_985.0)
    assert res.clips_final['shares'].sum() == 10_000


# ---------------------------------------------------------------------------
# d5: provider guards (fail-closed)
# ---------------------------------------------------------------------------

def test_d5_provider_guards():
    daily = daily_frame(ETF, [(D1, 2.0, 2.01, 1.99, 2.0, 2.0),
                              (D2, 2.0, 2.01, 1.99, 2.0, 2.0)])
    half = half_frame(ETF, [(d, s, 2.0, 2.01, 1.99, 2.0)
                            for d in (D1, D2) for s in ('am', 'pm')])

    with pytest.raises(BandContractError, match="must return a list"):
        run_dyn(lambda *a: 42, daily, half, limits_frame(daily))

    with pytest.raises(BandContractError, match="row must be a dict"):
        run_dyn(lambda *a: ["oops"], daily, half, limits_frame(daily))

    def late_stamp(day, sess, ledger):
        if (day, sess) == (D1, 'pm'):
            # stamped with the morning point: its live session already ran
            return [row(ETF, 'buy', D1, 'am', D1, target=10_000)]
        return None

    with pytest.raises(BandContractError,
                       match="must be issued at its own decision point"):
        run_dyn(late_stamp, daily, half, limits_frame(daily))

    def dup_within_batch(day, sess, ledger):
        if (day, sess) == (D1, 'am'):
            return [row(ETF, 'buy', D1, 'am', D1, target=10_000),
                    row(ETF, 'buy', D1, 'am', D1, target=5_000)]
        return None

    with pytest.raises(BandContractError, match="duplicate first decision"):
        run_dyn(dup_within_batch, daily, half, limits_frame(daily))

    # a static row occupying the same first point clashes with injection
    static = pl.DataFrame(
        [row(ETF, 'buy', D1, 'am', D1, target=10_000)],
        schema={'symbol': pl.String, 'side': pl.String, 'intent': pl.String,
                'decision_date': pl.Date, 'decision_session': pl.String,
                'source_signal': pl.Date, 'expiry_date': pl.Date,
                'priority': pl.Int64, 'target_notional': pl.Float64,
                'target_weight': pl.Float64})

    def same_point(day, sess, ledger):
        if (day, sess) == (D1, 'am'):
            return [row(ETF, 'sell', D1, 'am', D1, intent='risk')]
        return None

    with pytest.raises(BandContractError, match="duplicate first decision"):
        run_dyn(same_point, daily, half, limits_frame(daily), intents=static)

    # a buy row without any sizing target is rejected by the shared
    # per-row validator
    def no_target(day, sess, ledger):
        if (day, sess) == (D1, 'am'):
            r = row(ETF, 'buy', D1, 'am', D1)
            return [r]
        return None

    with pytest.raises(BandContractError,
                       match="exactly one of target_notional"):
        run_dyn(no_target, daily, half, limits_frame(daily))

    # signals + provider is rejected up front (engine-level entry)
    from quant.backtest.band_engine import run_band_backtest
    signals = pl.DataFrame({
        'symbol': [ETF], 'decision_date': [D1], 'decision_session': ['am'],
        'source_signal': [D1], 'expiry_date': [D2], 'priority': [1],
        'target_weight': [0.1]})
    with pytest.raises(BandContractError, match="requires intent mode"):
        run_band_backtest(signals, daily, half, limits_frame(daily),
                          symbol_meta=etf_meta(),
                          intent_provider=lambda *a: None)


# ---------------------------------------------------------------------------
# d6: suspension semantics under the halfday clock
# ---------------------------------------------------------------------------

def test_d6_suspension_normal_voids_risk_carries():
    # OTHER (ETF) is suspended ALL of D2 (no daily row, no bars); the
    # held STOCK has a daily row but NO pm bar on D2 (half-day
    # suspension -- the bar guard only pins ETF trading days)
    daily = pl.concat([
        daily_frame(STOCK, [
            (D1, 10.0, 10.05, 9.90, 10.0, 10.0),
            (D2, 10.0, 10.05, 9.90, 10.0, 10.0),
            (D3, 10.0, 10.10, 9.90, 10.0, 10.0)]),
        daily_frame(OTHER, [
            (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
            (D3, 2.0, 2.01, 1.99, 2.0, 2.0)])])   # D2 suspended
    half = pl.concat([
        half_frame(STOCK, [
            (D1, 'am', 10.0, 10.05, 9.99, 10.0),
            (D1, 'pm', 10.0, 10.05, 9.90, 9.95),   # buy fills at 10.0
            (D2, 'am', 10.0, 10.05, 9.95, 10.0),
            (D3, 'am', 10.0, 10.10, 9.90, 10.05),  # carried sell fills
            (D3, 'pm', 10.0, 10.05, 9.95, 10.0)]),  # D2 pm: suspended
        half_frame(OTHER, [
            (D1, 'am', 2.0, 2.01, 1.99, 2.0),
            (D1, 'pm', 2.0, 2.01, 1.99, 2.0),
            (D3, 'am', 2.0, 2.01, 1.99, 2.0),
            (D3, 'pm', 2.0, 2.01, 1.99, 2.0)])])
    limits = pl.concat([
        limits_frame(daily.filter(pl.col('symbol') == STOCK), symbol=STOCK),
        limits_frame(daily.filter(pl.col('symbol') == OTHER), symbol=OTHER)])

    def provider(day, sess, ledger):
        if (day, sess) == (D1, 'am'):
            return [row(STOCK, 'buy', D1, 'am', D1, target=40_000)]
        if (day, sess) == (D2, 'am'):
            # a normal buy into the all-day-suspended ETF and a risk exit
            # on the held stock (whose live pm session is suspended)
            return [row(OTHER, 'buy', D2, 'am', D2, target=10_000),
                    row(STOCK, 'sell', D2, 'am', D2, intent='risk')]
        return None

    res = run_dyn(provider, daily, half, limits,
                  meta={ETF: {"asset_class": "etf", "band": .1, "t_plus": 0},
                        OTHER: {"asset_class": "etf", "band": .1,
                                "t_plus": 0},
                        STOCK: {"asset_class": "stock", "band": .1,
                                "t_plus": 1}})

    il = res.stats['intent_layer']
    # the suspended-symbol normal buy voids: no anchor, no auto re-hang
    assert il['terminated_expired_halfday_no_anchor'] == 1
    assert il['emissions_skipped_no_anchor'] == 0
    # the stock buy on D1 pm filled; the risk sell could not trade in the
    # suspended D2 pm session (streak frozen) and re-issued into D3 am
    susp = res.events.filter((pl.col('event') == 'void_suspended')
                             & (pl.col('symbol') == STOCK))
    assert susp.height == 1
    assert 're-issue continues' in susp['detail'][0]
    sells = res.fills.filter(pl.col('side') == 'sell')
    assert sells.height == 1
    assert sells['date'][0] == D3 and sells['session'][0] == 'am'
    # fills: the D1 pm buy and the D3 am carried exit only (the OTHER
    # buy voided before any order was ever generated)
    assert res.fills.height == 2


# ---------------------------------------------------------------------------
# d7: static seed + dynamic extension, later injection overrides
# ---------------------------------------------------------------------------

def test_d7_static_seed_dynamic_override():
    daily = daily_frame(ETF, [
        (D1, 2.0, 2.2, 1.9, 2.0, 2.0),
        (D2, 2.0, 2.2, 1.9, 2.0, 2.0),
        (D3, 2.0, 2.2, 1.9, 2.0, 2.0)])
    half = half_frame(ETF, [
        (D1, 'am', 2.0, 2.01, 1.9, 2.0),
        (D1, 'pm', 2.0, 2.01, 1.9, 2.0),
        (D2, 'am', 2.0, 2.01, 1.9, 2.0),
        (D2, 'pm', 2.0, 2.01, 1.9, 2.0),
        (D3, 'am', 2.0, 2.01, 1.9, 2.0),
        (D3, 'pm', 2.0, 2.01, 1.9, 2.0)])
    static = pl.DataFrame(
        [row(ETF, 'buy', D1, 'am', D1, target=20_000)],
        schema={'symbol': pl.String, 'side': pl.String, 'intent': pl.String,
                'decision_date': pl.Date, 'decision_session': pl.String,
                'source_signal': pl.Date, 'expiry_date': pl.Date,
                'priority': pl.Int64, 'target_notional': pl.Float64,
                'target_weight': pl.Float64})

    def provider(day, sess, ledger):
        held = {p['symbol']: p['shares'] for p in ledger['positions']}
        if (day, sess) == (D2, 'am') and held.get(ETF):
            # replaces the standing risk carry with an explicit full exit
            return [row(ETF, 'sell', D2, 'am', D2, intent='risk')]
        return None

    res = run_dyn(provider, daily, half, limits_frame(daily), intents=static)

    assert res.stats['intent_layer']['n_intents'] == 1
    assert res.stats['intent_layer']['dynamic_injected'] == 1
    assert res.fills.height == 2
    sell = res.fills.filter(pl.col('side') == 'sell')
    assert sell.height == 1 and sell['date'][0] == D2
    assert res.clips_final.height == 0
    # cash: 200,000 - 5 (buy) + 20,000 - 5 (sell)
    assert res.daily['settled_cash'][-1] == pytest.approx(199_990.0)


# ---------------------------------------------------------------------------
# d8: suspended-day mark for held symbols (am snapshot guard)
# ---------------------------------------------------------------------------

def test_d8_suspension_mark_frozen_close_not_crash():
    """A held symbol suspended on day-3 has no am bar; the am decision
    snapshot must mark it at the frozen last-traded close (no look-ahead)
    instead of failing the run.  A TRADED day without an am bar stays a
    hard data defect (fail-closed) -- see the companion negative test."""
    daily = daily_frame(ETF, [
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 2.0, 2.01, 1.95, 1.96, 2.0),
        (D3, 1.96, 1.96, 1.96, 1.96, 1.96),   # suspended row
        (D4, 1.96, 1.97, 1.94, 1.95, 1.96)])
    daily = daily.with_columns(
        pl.when(pl.col('date') == D3).then(0.0).otherwise(1.0)
        .alias('tradestatus'))
    half = half_frame(ETF, [
        (D1, 'am', 2.0, 2.01, 1.99, 2.0),
        (D1, 'pm', 2.0, 2.01, 2.0, 2.0),
        (D2, 'am', 2.0, 2.01, 1.99, 2.0),
        (D2, 'pm', 2.0, 2.01, 1.95, 1.96),    # low 1.95: buy fills
        (D4, 'am', 1.96, 1.97, 1.94, 1.95),
        (D4, 'pm', 1.95, 1.96, 1.94, 1.95)])  # D3 suspended: no bars
    seen = []

    def provider(day, sess, ledger):
        seen.append({'day': day, 'sess': sess, 'ledger': ledger})
        if (day, sess) == (D2, 'am'):
            return [row(ETF, 'buy', D2, 'am', D2, target=20_000)]
        return None

    res = run_dyn(provider, daily, half, limits_frame(daily))

    assert res.fills.height == 1 and res.fills['date'][0] == D2
    # (D3, 'am'): suspended mark == last TRADED close 1.96 (not the
    # suspended row's stale close column, not any future price)
    led = seen[4]['ledger']    # (D3, 'am') is the 5th decision point
    assert (led['date'], led['session']) == (D3, 'am')
    assert led['equity_snapshot'] == pytest.approx(
        179_995.0 + 10_000 * 1.96)
    led_pm = seen[5]['ledger']
    assert led_pm['equity_snapshot'] == pytest.approx(led['equity_snapshot'])
    assert res.daily['equity'][-1] > 0


def test_d8b_traded_day_missing_am_bar_still_rejected():
    """Negative companion: the STOCK TRADED on day-3 (tradestatus=1) but
    the half-day frame has no am bar -- data defect, run fails closed.
    (An ETF symbol would trip the earlier whole-day bar guard first, so
    this uses a stock.)"""
    daily = daily_frame(STOCK, [
        (D1, 10.0, 10.05, 9.90, 10.0, 10.0),
        (D2, 10.0, 10.05, 9.90, 10.0, 10.0),
        (D3, 10.0, 10.10, 9.90, 10.0, 10.0)])
    half = half_frame(STOCK, [
        (D1, 'am', 10.0, 10.05, 9.99, 10.0),
        (D1, 'pm', 10.0, 10.05, 9.90, 9.95),   # buy fills at 10.0
        (D2, 'am', 10.0, 10.05, 9.95, 10.0),
        (D2, 'pm', 10.0, 10.05, 9.95, 10.0),
        (D3, 'pm', 10.0, 10.10, 9.90, 10.05)])  # am bar missing on traded day

    def provider(day, sess, ledger):
        if (day, sess) == (D1, 'am'):
            return [row(STOCK, 'buy', D1, 'am', D1, target=40_000)]
        return None

    with pytest.raises(BandContractError,
                       match="missing held-symbol am bar"):
        run_dyn(provider, daily, half, limits_frame(daily, symbol=STOCK),
                meta={STOCK: {"asset_class": "stock", "band": .1,
                              "t_plus": 1}})
