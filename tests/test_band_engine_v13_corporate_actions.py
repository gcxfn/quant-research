"""P3 band-contract engine v1.3 acceptance tests -- section 9.2 ETF
share-change (份额变换) corporate actions (A/B/C items of the approved
task, docs/plans/p3-band-contract.md section 9 revision 1).

Semantics under test (section 9.2, revision 1 frozen 2026-09-19):
  - share multiplier = the ANNOUNCED ratio (513100 = 5, 513500 = 2);
    integer ratio x integer shares is exact (zero odd lots, zero discount);
    floor + preclose discount survives only as the non-integer fallback;
  - execution at the top of the ex-date (before any fill determination /
    valuation), per clip, m4 mirror (added shares acquired the ex-date,
    sellable next day; T+0 clips same-day pm);
  - guardrail |preclose x ratio - close(t-1)| / close(t-1) <= 2% is a
    LEGALITY gate, not zero-continuity (suspension NAV drift is real P&L);
  - in-flight orders are not auto-cancelled: stale anchors meet the
    existing safety nets (limit-legality void / mechanical re-anchor);
  - anti-misclassification: a >10% implied-yield "dividend" and a
    (symbol, date) dividend/share-change conflict are hard raises.

  test_ca1_integer_exact_transform   300 x 2 -> 600, zero odd lots, value
                                     identity to the cent (hand calc)
  test_ca1b_integer_m4_structure     keep/extra clip acquisition dates
  test_ca2_fractional_fallback       300 x 1.9848 -> 595 + 0.44 x preclose
                                     cash, Decimal reconciliation
  test_ca3_real_513100_ex_date_void  real event replay, single-symbol
                                     calendar: stale 5.192 buy faces the
                                     ex-date computed limits [0.934, 1.142]
                                     -> void_limit_out_of_range counted;
                                     transformation 1800 -> 9000; sell in
                                     the new domain; cash to the cent
  test_ca3b_real_513100_freeze       real event, mixed calendar (companion
                                     symbol trades the suspension day):
                                     void_suspended + m3 streak freeze +
                                     no-anchor skip + 15:00 re-anchor
  test_ca4_real_513500               real event replay: x2, +0.7678%
                                     guardrail residual, stale sell void,
                                     re-anchor, conservation
  test_ca5_t0_same_day_sell          armed K=3 fallback executes at the
                                     ex-date pm open; T+0 transformed clip
                                     sells same day (5000 vs T+1 control)
  test_ca6_misclassification_raises  513100-type jump fed to
                                     dividend_events raises (80% yield)
  test_ca7_conflict_raises           dividend + share change same
                                     (symbol, date) raises
  test_ca8_guardrail_raises          wrong ratio -> guardrail violation
  test_ca9_factor_jump_check         |factor_jump/ratio - 1| <= 2% gate
  test_ca10_stats_shape              no-event run: no new stats key;
                                     event run: share_changes counters
  test_c1_dividend_ex_date_same_day  C-debt: same-day buy on the ex-date
                                     receives NO dividend (ETF events path)
  test_c1b_dividend_ex_date_same_day C-debt: same edge on the v0 per-lot
                                     stock dividend path
  test_c2a_m7_equal_priority_cash    C-debt m7: same decision point, equal
                                     priority, scarce cash -> deterministic
                                     resolution ((priority, symbol) sort;
                                     creation order of the intent frame)
  test_c2b_m7_fifo_consumption       C-debt m7: partial reduce consumes the
                                     earliest clip first (creation order)
  test_c2c_m7_independent_clips      C-debt m7: today-acquired clip does
                                     not block the sellable clip's fill

Real-data tests read data/processed/etf-daily-20260919/daily_2015_2024.parquet
read-only (batch 20260917-r1 via the standardized parquet; event facts per
the section 9.1 revision-1 announcements).  No strategy judgement; zero
trial consumption.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from quant.backtest.band_engine import (  # noqa: E402
    BandContractError,
    run_band_backtest_intents,
)

D = date
ETF = 'sh.513100'

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


def etf_daily(symbol, rows):
    """Official daily backbone with a preclose column.
    rows: (date, open, high, low, close, preclose)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'preclose': [float(r[5]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def stock_daily(symbol, rows):
    """Stock daily bars without a preclose column (v0 path)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def pm_bars(daily):
    """Section 8.1: each ETF day synthesizes ONE pm session (daily OHLC)."""
    return daily.select(
        pl.col('symbol'), pl.col('date').alias('trade_date'),
        pl.lit('pm').alias('session'), pl.col('open'), pl.col('high'),
        pl.col('low'), pl.col('close'))


def stock_half(symbol, rows):
    """rows: (date, session, open, high, low, close)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows],
    })


EMPTY_LIMITS = pl.DataFrame(schema={'symbol': pl.String, 'date': pl.Date,
                                    'limit_up': pl.Float64,
                                    'limit_down': pl.Float64})
EMPTY_SPLITS = pl.DataFrame(schema={'symbol': pl.String, 'ex_date': pl.Date,
                                    'split_factor': pl.Float64})
EMPTY_DIVS = pl.DataFrame(schema={'symbol': pl.String, 'ex_date': pl.Date,
                                  'cash_per_lot_pre_tax': pl.Float64,
                                  'round_lot': pl.Int64})
EMPTY_INSTR = pl.DataFrame(schema={'symbol': pl.String, 'is_etf': pl.Boolean,
                                   'is_t0': pl.Boolean})

ETF_META = {ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 0}}


def ca_frame(rows):
    """rows: (symbol, date, ratio[, factor_jump])."""
    return pl.DataFrame({
        'symbol': [r[0] for r in rows], 'date': [r[1] for r in rows],
        'ratio': [float(r[2]) for r in rows],
        'factor_jump': [None if len(r) < 4 else float(r[3]) for r in rows]})


def run_etf(intents, daily, **kw):
    return run_band_backtest_intents(
        intents, daily, pm_bars(daily), EMPTY_LIMITS, EMPTY_SPLITS,
        EMPTY_DIVS, EMPTY_INSTR, symbol_meta=kw.pop('meta', ETF_META),
        corporate_actions=kw.pop('ca', None), **kw)


def fills_of(res, **cols):
    f = res.fills
    for k, v in cols.items():
        f = f.filter(pl.col(k) == v)
    return f


def events_of(res, event):
    return res.events.filter(pl.col('event') == event)


def assert_cash_conservation(res, initial=200_000.0):
    """Every cent accounted for: initial + sum(fill net flows) + corp cash
    events == final settled cash + pending buckets."""
    flows = res.fills['net_cash_flow'].sum() if res.fills.height else 0.0
    final = res.stats['final']
    corp = res.stats['corp_actions']['dividend_cash_total_pre_tax']
    odd = (res.stats.get('share_changes') or {}).get('odd_lot_cash_total', 0.0)
    lhs = initial + flows + corp + odd
    rhs = final['settled_cash'] + final['pending_am_to_pm'] \
        + final['pending_next_day']
    assert lhs == pytest.approx(rhs, abs=1e-6)


# ---------------------------------------------------------------------------
# ca1: announced integer ratio, exact transform, zero odd lots (hand calc)
# ---------------------------------------------------------------------------

def test_ca1_integer_exact_transform():
    D0, D1, D2, D3 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5), D(2024, 6, 6)
    daily = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        # ex-date: preclose 1.0 = 2.0 / 2 exactly (zero drift -> residual 0)
        (D2, 1.0, 1.01, 0.99, 1.005, 1.0),
        (D3, 1.0, 1.01, 1.0, 1.005, 1.005)])
    res = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=600),
        it(ETF, 'sell', D2, 'pm', D2, intent='risk')]), daily,
        ca=ca_frame([(ETF, D2, 2.0)]))
    # buy 300 @ 2.0 on D1 pm (anchor = D0 close)
    b = fills_of(res, side='buy').row(0, named=True)
    assert (b['date'], b['session'], b['price'], b['shares']) == \
        (D1, 'pm', 2.0, 300)
    # transformation: 300 -> 600, exact-integer path, no odd-lot cash
    ev = events_of(res, 'corp_action_share_change').row(0, named=True)
    assert (ev['date'], ev['ratio'], ev['shares']) == (D2, 2.0, 600)
    assert ev['cash_amount'] is None
    assert 'exact-integer' in ev['detail'] and 'residual +0.0000%' in ev['detail']
    # sell the whole transformed position next day (m4: sellable next day)
    s = fills_of(res, side='sell').row(0, named=True)
    assert (s['date'], s['session'], s['price'], s['shares']) == \
        (D3, 'pm', 1.005, 600)
    # value identity to the cent at the reference prices (300 x 2.0 ==
    # 600 x 1.0); the realized mark drift (1.005) is real P&L, not a leak
    assert Decimal(600) * Decimal('1.0') == Decimal(300) * Decimal('2.0')
    # hand-calc: cash 200,000 - 605 = 199,395; sell proceeds 598 pending
    d2 = res.daily.filter(pl.col('date') == D2).row(0, named=True)
    assert d2['positions_value'] == pytest.approx(600 * 1.005)
    assert res.daily['equity'][-1] == pytest.approx(199_993.0, abs=1e-6)
    assert_cash_conservation(res)
    assert res.stats['share_changes'] == {
        'events': 1, 'odd_lot_cash_total': 0.0,
        'shares_before': 300, 'shares_after': 600}


def test_ca1b_integer_m4_structure():
    """Keep/extra clip split: original shares keep their acquisition date,
    the added (ratio-1)x shares are acquired the ex-date."""
    D0, D1, D2, D3 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5), D(2024, 6, 6)
    daily = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 1.0, 1.01, 0.99, 1.005, 1.0),
        (D3, 1.0, 1.01, 1.0, 1.005, 1.005)])
    res = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=600)]), daily,
        ca=ca_frame([(ETF, D2, 2.0)]))
    cf = res.clips_final
    assert cf['shares'].sum() == 600
    # 300 keep (acquired D1) + 300 extra (acquired the ex-date D2)
    got = sorted(zip(cf['shares'].to_list(), cf['acquired'].to_list()))
    assert got == [(300, D1), (300, D2)]


# ---------------------------------------------------------------------------
# ca2: non-integer fallback: floor + preclose discount of the fraction
# ---------------------------------------------------------------------------

def test_ca2_fractional_fallback():
    D0, D1, D2, D3 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5), D(2024, 6, 6)
    daily = etf_daily(ETF, [
        (D0, 5.9544, 5.96, 5.9, 5.9544, 5.9544),
        (D1, 5.9544, 5.96, 5.9, 5.9544, 5.9544),
        # ex-date: preclose 3.0; 3.0 x 1.9848 = 5.9544 -> residual 0
        (D2, 3.0, 3.03, 2.97, 3.0, 3.0),
        (D3, 3.0, 3.02, 2.99, 3.005, 3.0)])
    res = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=1_800),
        it(ETF, 'sell', D2, 'pm', D2, intent='risk')]), daily,
        ca=ca_frame([(ETF, D2, 1.9848)]))
    b = fills_of(res, side='buy').row(0, named=True)
    # ETF anchors are tick-rounded to 0.001: 5.9544 -> 5.954
    assert (b['price'], b['shares']) == (5.954, 300)
    ev = events_of(res, 'corp_action_share_change').row(0, named=True)
    assert (ev['date'], ev['ratio'], ev['shares']) == (D2, 1.9848, 595)
    # odd-lot cash = (300 x 1.9848 - 595) x preclose 3.0 = 0.44 x 3 = 1.32
    assert ev['cash_amount'] == pytest.approx(1.32, abs=1e-9)
    assert 'floor+preclose fallback' in ev['detail']
    # Decimal reconciliation to the cent (hand calc)
    exact = Decimal(300) * Decimal('1.9848')          # 595.44
    assert int(exact) == 595
    odd = (exact - Decimal(595)) * Decimal('3.0')
    assert odd == Decimal('1.32')
    assert ev['cash_amount'] == pytest.approx(float(odd), abs=1e-9)
    # value identity: 300 x 5.9544 == 595 x 3.0 + 1.32 (Decimal-exact)
    assert Decimal(300) * Decimal('5.9544') == \
        Decimal(595) * Decimal('3.0') + Decimal('1.32')
    # whole odd-lot position (595 = 5 x 100 + 95) exits in ONE order
    s = fills_of(res, side='sell').row(0, named=True)
    assert (s['date'], s['price'], s['shares']) == (D3, 3.0, 595)
    assert res.stats['odd_lot_exits'] == 1
    assert res.stats['share_changes']['odd_lot_cash_total'] == \
        pytest.approx(1.32, abs=1e-9)
    assert_cash_conservation(res)


# ---------------------------------------------------------------------------
# ca3/ca3b/ca4: real event replays (section 9.1 revision-1 facts)
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
ETF_PARQUET = ROOT / 'data/processed/etf-daily-20260919/daily_2015_2024.parquet'

CA_513100 = (ETF, D(2022, 1, 14), 5.0, 5.0019)   # GuoTai 1:5, registered 01-12
CA_513500 = ('sh.513500', D(2022, 3, 30), 2.0, 1.9848)  # BoShi 1:2


def _slice_real(symbol, lo, hi):
    if not ETF_PARQUET.is_file():
        pytest.skip('real ETF parquet not available (data/ is not in git)')
    df = pl.read_parquet(ETF_PARQUET)
    return df.filter(
        (pl.col('symbol') == symbol)
        & (pl.col('date') >= pl.lit(lo).str.to_date())
        & (pl.col('date') <= pl.lit(hi).str.to_date())).sort('date')


def test_ca3_real_513100_ex_date_void():
    """Single-symbol calendar: the suspension day (2022-01-13) vanishes from
    the engine calendar, so the 2022-01-12 15:00 decision lives DIRECTLY at
    the ex-date pm session -- the stale 5.192 anchor meets the computed
    limits [round(1.038 x 0.9) = 0.934, round(1.038 x 1.1) = 1.142] and MUST
    void on limit legality (counted), never fill at the old price domain."""
    daily = _slice_real(ETF, '2021-12-01', '2022-01-31')
    res = run_etf(intents_frame([
        it(ETF, 'buy', D(2021, 12, 29), 'pm', D(2021, 12, 29), target=10_000),
        it(ETF, 'buy', D(2022, 1, 12), 'pm', D(2022, 1, 12), target=10_000),
        it(ETF, 'sell', D(2022, 1, 14), 'pm', D(2022, 1, 14),
           intent='risk')]), daily, ca=ca_frame([CA_513100]))
    # pre-event buy fills 2021-12-30 pm @ 5.402 x 1800
    b1 = fills_of(res, side='buy').row(0, named=True)
    assert (b1['date'], b1['session'], b1['price'], b1['shares']) == \
        (D(2021, 12, 30), 'pm', 5.402, 1800)
    # transformation at the top of 2022-01-14: 1800 -> 9000, exact x5
    ev = events_of(res, 'corp_action_share_change').row(0, named=True)
    assert (ev['date'], ev['ratio'], ev['shares']) == \
        (D(2022, 1, 14), 5.0, 9000)
    assert ev['cash_amount'] is None and 'exact-integer' in ev['detail']
    # guardrail residual |1.038 x 5 - 5.192| / 5.192 = 0.0385% <= 2%
    assert 'residual +0.0385%' in ev['detail']
    # stale-anchor buy voided on the ex-date by limit legality (counted)
    v = events_of(res, 'void_limit_out_of_range').row(0, named=True)
    assert (v['symbol'], v['date'], v['session'], v['limit_price']) == \
        (ETF, D(2022, 1, 14), 'pm', 5.192)
    assert '[0.934, 1.142]' in v['detail']
    assert res.stats['void_days']['limit_out_of_range'] >= 1
    # the voided buy intent is overridden at the 01-14 15:00 decision by the
    # sell intent; the sell re-anchors INTO the new domain and fills 01-17
    lc = [r['detail'] for r in events_of(res, 'intent_lifecycle')
          .iter_rows(named=True)]
    assert any('overridden' in d for d in lc)
    assert fills_of(res, side='buy').height == 1        # never a stale fill
    s = fills_of(res, side='sell').row(0, named=True)
    assert (s['date'], s['session'], s['price'], s['shares']) == \
        (D(2022, 1, 17), 'pm', 1.015, 9000)
    # no fill ever prints an old-domain price on/after the ex-date
    assert res.fills.filter(pl.col('date') >= D(2022, 1, 14))['price'].max() \
        < 1.142
    # cash to the cent: 200,000 - 9,728.60 + 9,130.00 (pm fill settled next
    # day; the window runs to 01-31 so the pending bucket is consumed)
    assert res.stats['final']['settled_cash'] == pytest.approx(199_401.40)
    assert res.stats['final']['pending_next_day'] == pytest.approx(0.0)
    assert res.daily['equity'][-1] == pytest.approx(199_401.40, abs=1e-6)
    assert_cash_conservation(res)


def test_ca3b_real_513100_suspension_freeze():
    """Mixed calendar (companion sh.510300 trades the suspension day): the
    01-12 sell lives at 01-13 pm -> void_suspended with the m3 streak
    freeze; no anchor at the suspended decision point -> no emission; the
    01-14 15:00 decision mechanically re-anchors into the new domain."""
    daily = pl.concat([
        _slice_real(ETF, '2021-12-01', '2022-01-31'),
        _slice_real('sh.510300', '2021-12-01', '2022-01-31')])
    res = run_etf(intents_frame([
        it(ETF, 'buy', D(2021, 12, 29), 'pm', D(2021, 12, 29), target=10_000),
        it(ETF, 'sell', D(2022, 1, 12), 'pm', D(2022, 1, 12),
           intent='risk')]), daily, ca=ca_frame([CA_513100]))
    assert fills_of(res, side='buy').row(0, named=True)['shares'] == 1800
    sus = events_of(res, 'void_suspended').row(0, named=True)
    assert (sus['symbol'], sus['date'], sus['session']) == \
        (ETF, D(2022, 1, 13), 'pm')
    assert 'K streak frozen' in sus['detail']
    assert res.stats['intent_layer']['emissions_skipped_no_anchor'] >= 1
    ev = events_of(res, 'corp_action_share_change').row(0, named=True)
    assert (ev['date'], ev['shares']) == (D(2022, 1, 14), 9000)
    s = fills_of(res, side='sell').row(0, named=True)
    assert (s['date'], s['session'], s['price'], s['shares']) == \
        (D(2022, 1, 17), 'pm', 1.015, 9000)
    assert res.fills.filter(pl.col('date') >= D(2022, 1, 14))['price'].max() \
        < 1.142
    assert_cash_conservation(res)


def test_ca4_real_513500():
    """BoShi 1:2 (registered 2022-03-28, suspended 03-29, resumed 03-30):
    guardrail residual +0.7678% (suspension NAV drift, real P&L, passes the
    2% legality gate); stale sell anchor voided; re-anchor; conservation."""
    daily = _slice_real('sh.513500', '2022-03-01', '2022-04-15')
    meta = {'sh.513500': {'asset_class': 'etf', 'band': 0.10, 't_plus': 0}}
    res = run_etf(intents_frame([
        it('sh.513500', 'buy', D(2022, 3, 23), 'pm', D(2022, 3, 23),
           target=10_000),
        it('sh.513500', 'sell', D(2022, 3, 28), 'pm', D(2022, 3, 28),
           intent='risk')]), daily, meta=meta, ca=ca_frame([CA_513500]))
    b = fills_of(res, side='buy').row(0, named=True)
    assert (b['date'], b['session'], b['price'], b['shares']) == \
        (D(2022, 3, 24), 'pm', 2.722, 3600)
    ev = events_of(res, 'corp_action_share_change').row(0, named=True)
    assert (ev['date'], ev['ratio'], ev['shares']) == \
        (D(2022, 3, 30), 2.0, 7200)
    assert 'exact-integer' in ev['detail']
    # |1.378 x 2 - 2.735| / 2.735 = +0.7678% <= 2% (NAV drift, not an error)
    assert 'residual +0.7678%' in ev['detail']
    # the 03-28 sell lives directly at 03-30 (03-29 absent from the
    # single-symbol calendar): stale anchor 2.735 > up 1.516 -> void
    v = events_of(res, 'void_limit_out_of_range').row(0, named=True)
    assert (v['date'], v['session'], v['limit_price']) == \
        (D(2022, 3, 30), 'pm', 2.735)
    assert '[1.24, 1.516]' in v['detail']
    assert res.stats['void_days']['limit_out_of_range'] >= 1
    s = fills_of(res, side='sell').row(0, named=True)
    assert (s['date'], s['session'], s['price'], s['shares']) == \
        (D(2022, 3, 31), 'pm', 1.39, 7200)
    assert res.fills.filter(pl.col('date') >= D(2022, 3, 30))['price'].max() \
        < 1.516
    assert res.stats['final']['settled_cash'] == pytest.approx(200_198.80)
    assert res.stats['final']['pending_next_day'] == pytest.approx(0.0)
    assert_cash_conservation(res)


# ---------------------------------------------------------------------------
# ca5: T+0 same-day sellability of transformed clips (armed K=3 fallback at
# the ex-date pm open -- the only order path that can act on the ex-date
# with a new-domain execution price)
# ---------------------------------------------------------------------------

def _t0_daily():
    days = [D(2024, 1, d) for d in (2, 3, 4, 5, 8, 9, 10)]
    rows = [(d, 10.0, 10.0, 9.95, 10.0, 10.0) for d in days[:5]]
    # ex-date 01-09: preclose 2.0 = 10.0 / 5 exactly; 01-10 follows
    rows += [(days[5], 2.0, 2.02, 1.99, 2.01, 2.0),
             (days[6], 2.0, 2.02, 1.99, 2.005, 2.01)]
    return etf_daily(ETF, rows), days


def test_ca5_t0_same_day_sell():
    daily, days = _t0_daily()
    res = run_etf(intents_frame([
        it(ETF, 'buy', days[0], 'pm', days[0], target=10_000),
        it(ETF, 'sell', days[1], 'pm', days[1], intent='risk')]), daily,
        ca=ca_frame([(ETF, days[5], 5.0)]))
    assert fills_of(res, side='buy').row(0, named=True)['shares'] == 1000
    # streak 3 at the 01-08 pm session (armed); 01-09 = ex-date: fallback
    # executes at the pm OPEN 2.0 (new domain) with the transformed clips
    ev = events_of(res, 'corp_action_share_change').row(0, named=True)
    assert (ev['date'], ev['shares']) == (days[5], 5000)
    fb = fills_of(res, fill_type='market_fallback').row(0, named=True)
    assert (fb['date'], fb['session'], fb['price'], fb['shares']) == \
        (days[5], 'pm', 2.0, 5000)
    # net = 10,000 - 5; the 4000 added shares (acquired TODAY) sold same day
    assert fb['net_cash_flow'] == pytest.approx(9_995.0)
    assert res.stats['k3_fallback']['armed'] == 1
    assert res.stats['k3_fallback']['executed'] == 1
    assert_cash_conservation(res)


def test_ca5b_t1_lock_control():
    """Control: t_plus=1 locks the same-day transformed clip -> the fallback
    sells only the 1000 original shares; the 4000 added shares remain."""
    daily, days = _t0_daily()
    res = run_etf(intents_frame([
        it(ETF, 'buy', days[0], 'pm', days[0], target=10_000),
        it(ETF, 'sell', days[1], 'pm', days[1], intent='risk')]), daily,
        meta={ETF: {'asset_class': 'etf', 'band': 0.10, 't_plus': 1}},
        ca=ca_frame([(ETF, days[5], 5.0)]))
    fb = fills_of(res, fill_type='market_fallback').row(0, named=True)
    assert (fb['price'], fb['shares']) == (2.0, 1000)
    cf = res.clips_final
    assert cf['shares'].to_list() == [4000]
    assert cf['acquired'].to_list() == [days[5]]


# ---------------------------------------------------------------------------
# ca6-ca9: hard gates at the engine entry
# ---------------------------------------------------------------------------

def test_ca6_misclassification_raises():
    """Feeding the 513100 share change (implied yield ~80%) into the
    dividend path must hard-raise (section 9.2-7)."""
    daily = _slice_real(ETF, '2021-12-01', '2022-01-31')
    divs = {'symbol': [ETF], 'date': [D(2022, 1, 14)],
            'div_per_share': [5.192 - 1.038]}
    with pytest.raises(BandContractError, match='MISCLASSIFICATION'):
        run_etf(intents_frame([
            it(ETF, 'buy', D(2021, 12, 29), 'pm', D(2021, 12, 29),
               target=10_000)]), daily, dividend_events=divs)
    # negative control: a normal ~2% dividend yield passes untouched
    D0, D1, D2 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5)
    daily2 = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 1.96, 1.97, 1.95, 1.96, 1.96)])
    res = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=2_000)]), daily2,
        dividend_events={'symbol': [ETF], 'date': [D2],
                         'div_per_share': [0.04]})
    assert events_of(res, 'corp_action_dividend')['cash_amount'][0] == \
        pytest.approx(1000 * 0.04)


def test_ca7_conflict_raises():
    D0, D1, D2 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5)
    daily = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 1.0, 1.01, 0.99, 1.005, 1.0)])
    with pytest.raises(BandContractError, match='CONFLICT'):
        run_etf(intents_frame([it(ETF, 'buy', D0, 'pm', D0, target=600)]),
                daily, ca=ca_frame([(ETF, D2, 2.0)]),
                dividend_events={'symbol': [ETF], 'date': [D2],
                                 'div_per_share': [0.05]})


def test_ca8_guardrail_raises():
    """Wrong ratio (or wrong date): |preclose x ratio - close(t-1)| / close
    (t-1) = 185% > 2% -> hard raise (section 9.2-5)."""
    D0, D1, D2 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5)
    daily = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 1.9, 1.91, 1.89, 1.9, 1.9)])
    with pytest.raises(BandContractError, match='guardrail VIOLATION'):
        run_etf(intents_frame([it(ETF, 'buy', D0, 'pm', D0, target=600)]),
                daily, ca=ca_frame([(ETF, D2, 3.0)]))


def test_ca9_factor_jump_check():
    D0, D1, D2 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5)
    daily = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        # ex-date: preclose 0.4 = 2.0 / 5 (guardrail residual 0)
        (D2, 0.4, 0.41, 0.39, 0.402, 0.4)])
    # |5.2 / 5 - 1| = 4% > 2% -> raise
    with pytest.raises(BandContractError, match='factor cross-check'):
        run_etf(intents_frame([it(ETF, 'buy', D0, 'pm', D0, target=600)]),
                daily, ca=ca_frame([(ETF, D2, 5.0, 5.2)]))
    # within tolerance (the real 513100 factor ratio 5.0019) -> passes
    res = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=600)]), daily,
        ca=ca_frame([(ETF, D2, 5.0, 5.0019)]))
    assert events_of(res, 'corp_action_share_change')['shares'][0] == 1500


def test_ca10_stats_shape():
    """No-event runs carry NO new stats key (byte-identical stats to v1.2);
    event runs expose the share_changes counters."""
    D0, D1, D2 = D(2024, 6, 3), D(2024, 6, 4), D(2024, 6, 5)
    daily = etf_daily(ETF, [
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D2, 1.0, 1.01, 0.99, 1.005, 1.0)])
    res0 = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=600)]), daily)
    assert 'share_changes' not in res0.stats
    res1 = run_etf(intents_frame([
        it(ETF, 'buy', D0, 'pm', D0, target=600)]), daily,
        ca=ca_frame([(ETF, D2, 2.0)]))
    assert res1.stats['share_changes'] == {
        'events': 1, 'odd_lot_cash_total': 0.0,
        'shares_before': 300, 'shares_after': 600}


# ---------------------------------------------------------------------------
# C-debt 1: dividend ex-date same-day edge (day-open holding caliber)
# ---------------------------------------------------------------------------

def test_c1_dividend_ex_date_same_day_etf():
    """dividend_events credit day-OPEN holdings only: a clip bought ON the
    ex-date receives no dividend; the pre-existing clip does."""
    Dm1, D0, D1, D2 = (D(2024, 3, 1), D(2024, 3, 4), D(2024, 3, 5),
                       D(2024, 3, 6))
    daily = etf_daily(ETF, [
        (Dm1, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D0, 2.0, 2.01, 1.99, 2.0, 2.0),
        (D1, 2.0, 2.01, 1.99, 2.0, 1.95),   # ex-date: div 0.05
        (D2, 2.0, 2.01, 1.99, 2.0, 2.0)])
    res = run_etf(intents_frame([
        it(ETF, 'buy', Dm1, 'pm', Dm1, target=2_000),   # fills D0 pm
        it(ETF, 'buy', D0, 'pm', D0, target=2_000)]),   # fills D1 = ex-date
        daily, dividend_events={'symbol': [ETF], 'date': [D1],
                                'div_per_share': [0.05]})
    assert fills_of(res).height == 2
    dv = events_of(res, 'corp_action_dividend').row(0, named=True)
    assert dv['cash_amount'] == pytest.approx(50.0)      # 1000 day-open only
    assert '1000 shares' in dv['detail'] and 'day open' in dv['detail']
    d1 = res.daily.filter(pl.col('date') == D1).row(0, named=True)
    # 200,000 - 2,005 - 2,005 + 50 = 196,040
    assert d1['settled_cash'] == pytest.approx(196_040.0)
    assert d1['positions_value'] == pytest.approx(2000 * 2.0)
    assert res.stats['etf_leg']['dividend_events_cash'] == pytest.approx(50.0)


def test_c1b_dividend_ex_date_same_day_stock():
    """Same edge on the v0 per-lot cash-dividend path (pre-ex = day-open
    share count; the same-day buyer is excluded)."""
    SYM = 'sh.600001'
    Dm1, D0, D1, D2 = (D(2024, 3, 1), D(2024, 3, 4), D(2024, 3, 5),
                       D(2024, 3, 6))
    daily = stock_daily(SYM, [
        (Dm1, 10.0, 10.05, 9.95, 10.0),
        (D0, 10.0, 10.05, 9.95, 10.0),
        (D1, 10.0, 10.05, 9.95, 10.0),      # ex-date (pure dividend)
        (D2, 10.0, 10.05, 9.95, 10.0)])
    half = pl.concat([
        stock_half(SYM, [(D0, 'am', 10.0, 10.02, 9.98, 10.0),
                         (D0, 'pm', 10.0, 10.02, 9.98, 10.0),
                         (D1, 'am', 10.0, 10.02, 9.98, 10.0),
                         (D1, 'pm', 10.0, 10.02, 9.98, 10.0)]),
    ])
    limits = daily.select('symbol', 'date',
                          (pl.col('close') * 1.1).alias('limit_up'),
                          (pl.col('close') * 0.9).alias('limit_down'))
    splits = pl.DataFrame(schema={'symbol': pl.String, 'ex_date': pl.Date,
                                  'split_factor': pl.Float64})
    divs = pl.DataFrame({'symbol': [SYM], 'ex_date': [D1],
                         'cash_per_lot_pre_tax': [41.0],
                         'round_lot': [100]})
    signals = pl.DataFrame([
        {'symbol': SYM, 'decision_date': Dm1, 'decision_session': 'pm',
         'side': 'buy', 'intent': None, 'anchor_price': 10.0, 'priority': 1,
         'target_notional': 10_000.0, 'shares': None},
        {'symbol': SYM, 'decision_date': D0, 'decision_session': 'pm',
         'side': 'buy', 'intent': None, 'anchor_price': 10.0, 'priority': 1,
         'target_notional': 10_000.0, 'shares': None}],
        schema={'symbol': pl.String, 'decision_date': pl.Date,
                'decision_session': pl.String, 'side': pl.String,
                'intent': pl.String, 'anchor_price': pl.Float64,
                'priority': pl.Int64, 'target_notional': pl.Float64,
                'shares': pl.Int64})
    from quant.backtest.band_engine import run_band_backtest
    res = run_band_backtest(signals, daily, half, limits, splits, divs)
    assert res.fills.height == 2                          # D0 am + D1 am
    dv = events_of(res, 'corp_action_dividend').row(0, named=True)
    assert dv['cash_amount'] == pytest.approx(410.0)      # 41/100 x 1000
    d1 = res.daily.filter(pl.col('date') == D1).row(0, named=True)
    # 200,000 - 10,005 - 10,005 + 410 = 180,400
    assert d1['settled_cash'] == pytest.approx(180_400.0)
    assert res.stats['corp_actions']['dividend_cash_total_pre_tax'] == \
        pytest.approx(410.0)


# ---------------------------------------------------------------------------
# C-debt 2: m7 multi-clip at one decision point
# ---------------------------------------------------------------------------

def test_c2a_m7_equal_priority_scarce_cash():
    """Same decision point, equal priority, cash scarce (pre-held positions):
    resolution is deterministic by the engine's (priority, symbol) stable
    sort over the intent-frame creation order -- PD (earlier in both the
    creation order and the sort) fills; PE voids on full funding."""
    PA, PB, PC, PD, PE = ('sh.600001', 'sh.600002', 'sh.600003',
                          'sh.600004', 'sh.600005')
    D0, D1 = D(2024, 3, 4), D(2024, 3, 5)
    daily = pl.concat([stock_daily(s, [(D0, 10.0, 10.05, 9.95, 10.0),
                                       (D1, 10.0, 10.05, 9.95, 10.0)])
                       for s in (PA, PB, PC, PD, PE)])
    half = pl.concat([stock_half(s, [(D0, 'am', 10.0, 10.02, 9.98, 10.0),
                                     (D0, 'pm', 10.0, 10.02, 9.98, 10.0),
                                     (D1, 'am', 10.0, 10.02, 9.98, 10.0),
                                     (D1, 'pm', 10.0, 10.02, 9.98, 10.0)])
                      for s in (PA, PB, PC, PD, PE)])
    limits = daily.select('symbol', 'date',
                          (pl.col('close') * 1.1).alias('limit_up'),
                          (pl.col('close') * 0.9).alias('limit_down'))
    # D0 am decisions x3 (hold 120k, cash 79,985); D0 pm decisions x2
    # (each 40,005: PD fills, PE sees only 39,980 -> void)
    intents = intents_frame([
        it(PA, 'buy', D0, 'am', D0, target=40_000),
        it(PB, 'buy', D0, 'am', D0, target=40_000),
        it(PC, 'buy', D0, 'am', D0, target=40_000),
        it(PD, 'buy', D0, 'pm', D0, target=40_000),
        it(PE, 'buy', D0, 'pm', D0, target=40_000)])
    res = run_band_backtest_intents(intents, daily, half, limits)
    filled = sorted(res.fills['symbol'].to_list())
    assert filled == [PA, PB, PC, PD]
    # PE voids on full funding (and keeps re-issuing/voiding while active --
    # an insufficient-cash void does not terminate the intent)
    assert set(events_of(res, 'void_insufficient_cash')['symbol']
               .to_list()) == {PE}
    assert res.stats['cash_friction']['insufficient_cash_orders'] >= 1
    assert (res.daily['settled_cash'] >= 0).all()


def test_c2b_m7_fifo_consumption():
    """Partial reduce consumes the EARLIEST clip first (clip creation order):
    position = clip A (1000, D1) + clip B (2000, D2); reduce-to-target
    15,000 -> sells 1500 = A(1000) + B(500); the remainder is B's.
    (Stock routing: pm decision -> next AM session.)"""
    SYM = 'sh.600010'
    D0, D1, D2, D3, D4 = (D(2024, 3, 4), D(2024, 3, 5), D(2024, 3, 6),
                          D(2024, 3, 7), D(2024, 3, 8))
    daily = stock_daily(SYM, [(d, 10.0, 10.05, 9.95, 10.0)
                              for d in (D0, D1, D2, D3, D4)])
    half = stock_half(SYM, [
        (D1, 'am', 10.0, 10.02, 9.98, 10.0), (D1, 'pm', 10.0, 10.02, 9.98, 10.0),
        (D2, 'am', 10.0, 10.02, 9.98, 10.0), (D2, 'pm', 10.0, 10.02, 9.98, 10.0),
        (D3, 'am', 10.0, 10.2, 9.98, 10.1),
    ])
    limits = daily.select('symbol', 'date',
                          (pl.col('close') * 1.1).alias('limit_up'),
                          (pl.col('close') * 0.9).alias('limit_down'))
    res = run_band_backtest_intents(
        intents_frame([
            it(SYM, 'buy', D0, 'pm', D0, target=10_000),   # clip A: fills D1 am
            it(SYM, 'buy', D1, 'pm', D1, target=20_000),   # clip B: fills D2 am
            it(SYM, 'sell', D2, 'pm', D2, intent='risk',
               weight=0.08)]),                             # reduce to ~15k
        daily, half, limits)
    # sell order (D2 pm decision) lives D3 am; fills @ 10.0 for 1500 shares
    # (A 1000 + B 500, FIFO by clip creation order)
    s = fills_of(res, side='sell').row(0, named=True)
    assert (s['date'], s['session'], s['price'], s['shares']) == \
        (D3, 'am', 10.0, 1500)
    cf = res.clips_final
    assert cf['shares'].to_list() == [1500]                # B remainder
    assert cf['acquired'].to_list() == [D2]                # the LATER clip


def test_c2c_m7_independent_clips():
    """Same-symbol multi-clip independent evaluation: a T+1-locked
    (today-acquired) clip does not block the sellable clip's fill."""
    SYM = 'sh.600011'
    D0, D1, D2, D3 = D(2024, 3, 4), D(2024, 3, 5), D(2024, 3, 6), D(2024, 3, 7)
    daily = stock_daily(SYM, [(d, 10.0, 10.05, 9.95, 10.0)
                              for d in (D0, D1, D2, D3)])
    half = stock_half(SYM, [
        (D1, 'am', 10.0, 10.02, 9.98, 10.0), (D1, 'pm', 10.0, 10.02, 9.98, 10.0),
        (D2, 'am', 10.0, 10.02, 9.98, 10.0), (D2, 'pm', 10.0, 10.2, 9.98, 10.1),
    ])
    limits = daily.select('symbol', 'date',
                          (pl.col('close') * 1.1).alias('limit_up'),
                          (pl.col('close') * 0.9).alias('limit_down'))
    res = run_band_backtest_intents(
        intents_frame([
            it(SYM, 'buy', D0, 'pm', D0, target=10_000),   # clip A: D1 am
            it(SYM, 'buy', D1, 'pm', D1, target=10_000),   # clip B: D2 am
            it(SYM, 'sell', D2, 'am', D2, intent='risk')]),  # full exit, D2 pm
        daily, half, limits)
    # D2 pm: only clip A (1000, acquired D1) is sellable -> fills 1000;
    # the locked clip B does not block the fill determination.  A full-exit
    # intent stops at its (partial-position) fill; B remains held.
    sells = fills_of(res, side='sell')
    assert sells.height == 1
    s0 = sells.row(0, named=True)
    assert (s0['date'], s0['session'], s0['shares']) == (D2, 'pm', 1000)
    cf = res.clips_final
    assert cf['shares'].to_list() == [1000]
    assert cf['acquired'].to_list() == [D2]
