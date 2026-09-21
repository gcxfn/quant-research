"""P3 band-contract engine acceptance tests -- v1 (dual-session, clips).

Maps to docs/plans/p3-band-contract.md section 7 (v1 frozen contract) with
v0 section 4 acceptance intents preserved item by item.  All data is inline
synthetic Polars frames; the only real-data reads are the registered
split_factor/dividends rows in test_06b.  No strategy judgement; zero trial
consumption.

v0 -> v1 test map (every v0 item keeps a counterpart; semantic changes are
listed in the v1 run manifest):
  test_00_input_guards        v0-14 (guards) + v1: decision_session/intent/
                              decision-anchor existence
  test_01_fee_conservation    v0-1  + v1: ETF stamp exemption, session-level
                              settlement ledger
  test_02_t1_clip             v0-2  -> v1 clip-level T+1 (same-session sell
                              blocked, next session/partial FIFO allowed)
  test_03_lot_odd             v0-3  + v1: corp-action odd lot sellable TODAY
  test_04_cash_priority       v0-4  (same-session priority cash, full funding)
  test_05_touch_penetrate     v0-5  (half-day session low == p does not fill)
  test_06_corporate_actions   v0-6  (split per clip, per-lot dividend)
  test_06b_real_600000        v0-6 real stock/dates (2017-05-25, 2022-07-21)
  test_06c_split_loader_anchor_regression  v0 F2 loader regression
  test_07_suspension_limit    v0-7  (half-day suspension voids that session)
  test_08_risk_k3_profit      v0-8  -> v1: risk K=3 by SESSION with open
                              fallback + limit-down defer; profit expires
                              silently (NEW intent split)
  test_09_proceeds_timing     v0-9  -> v1: am proceeds usable same-day pm,
                              pm proceeds next-day am, same-session
                              sell->buy forbidden (NEW)
  test_10_stamp_segmentation  v0-10 + v1 ETF exemption
  test_14_frame_schema_regression          v0-14 (ENGINE-1 regression)
  test_15_multi_clip_fifo     NEW: add clips + FIFO partial sell
  test_16_t0_roundtrip        NEW: T+0 same-day round trip vs stock blocked
  test_17_am_reanchor_fill    NEW: 11:30 decision fills in S_pm at am.close
                              anchor + pm anchor-mismatch warning
  test_18_close_bridge        NEW: pre-cutoff mark = OFFICIAL daily close
                              (not pm.close) + bridge assertions
  test_19_caps                NEW: section 7.3 single-name 25% / total 100%
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END,
    BandContractError,
    assert_daily_halfday_bridge,
    assert_frozen,
    load_daily_panel,
    load_dividends_h5,
    load_split_factor_h5,
    run_band_backtest,
    stamp_rate,
)

D = date

SIGNAL_SCHEMA = {
    'symbol': pl.String, 'decision_date': pl.Date, 'decision_session': pl.String,
    'side': pl.String, 'intent': pl.String, 'anchor_price': pl.Float64,
    'priority': pl.Int64, 'target_notional': pl.Float64, 'shares': pl.Int64,
}


def sig(symbol, decision_date, decision_session, side, anchor, priority=1,
        *, intent=None, target=None, shares=None):
    return {'symbol': symbol, 'decision_date': decision_date,
            'decision_session': decision_session, 'side': side,
            'intent': intent, 'anchor_price': float(anchor),
            'priority': priority,
            'target_notional': None if target is None else float(target),
            'shares': shares}


def signals_frame(rows):
    return pl.DataFrame(rows, schema=SIGNAL_SCHEMA)


def daily_bars(symbol, rows):
    """rows: (date, open, high, low, close) -- official daily backbone."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def half_bars(symbol, rows):
    """rows: (date, session, open, high, low, close)."""
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows],
    })


def instruments_frame(rows):
    """rows: (symbol, is_etf, is_t0)."""
    return pl.DataFrame({
        'symbol': [r[0] for r in rows], 'is_etf': [bool(r[1]) for r in rows],
        'is_t0': [bool(r[2]) for r in rows]})


def splits_frame(rows):
    return pl.DataFrame({
        'symbol': [r[0] for r in rows], 'ex_date': [r[1] for r in rows],
        'split_factor': [float(r[2]) for r in rows]})


def dividends_frame(rows):
    return pl.DataFrame({
        'symbol': [r[0] for r in rows], 'ex_date': [r[1] for r in rows],
        'cash_per_lot_pre_tax': [float(r[2]) for r in rows],
        'round_lot': [int(r[3]) for r in rows]})


def auto_limits(daily, overrides=None):
    """Auto limits around each day's close (up=+10%, down=-10%).  Override
    pairs REPLACE the auto rows for that (symbol, date) -- no duplicates (the
    engine's per-symbol searchsorted takes the first matching row)."""
    frame = daily.select(
        'symbol', 'date',
        (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'),
    )
    if overrides:
        extra = pl.DataFrame(
            [{'symbol': s, 'date': d, 'limit_up': float(u),
              'limit_down': float(lo)} for (s, d), (u, lo) in overrides.items()],
            schema={'symbol': pl.String, 'date': pl.Date,
                    'limit_up': pl.Float64, 'limit_down': pl.Float64})
        frame = frame.join(extra.select('symbol', 'date'),
                           on=['symbol', 'date'], how='anti')
        frame = pl.concat([frame, extra], how='vertical')
    return frame


def run(signals, daily, half, limits=None, **kw):
    limits = limits if limits is not None else auto_limits(daily)
    return run_band_backtest(
        signals_frame(signals) if isinstance(signals, list) else signals,
        daily, half, limits, **kw)


def events_of(res, event):
    return res.events.filter(pl.col('event') == event)


# ---------------------------------------------------------------------------
# item 1: fee conservation (+ v1 ETF exemption, session settlement ledger)
# ---------------------------------------------------------------------------

def test_01_fee_conservation():
    daily = pl.concat([
        daily_bars('S1', [(D(2023, 8, 24), 10.0, 10.1, 9.9, 10.0),
                          (D(2023, 8, 25), 10.02, 10.08, 9.90, 10.0),
                          (D(2023, 8, 28), 10.0, 10.45, 9.98, 10.0),
                          (D(2023, 8, 29), 10.0, 10.05, 9.95, 10.0),
                          (D(2023, 8, 30), 10.0, 10.05, 9.95, 10.0)]),
        daily_bars('S2', [(D(2023, 8, 23), 20.0, 20.05, 19.9, 20.0),
                          (D(2023, 8, 24), 20.0, 20.1, 19.9, 20.0),
                          (D(2023, 8, 25), 20.0, 20.8, 19.50, 20.0),
                          (D(2023, 8, 28), 20.0, 20.05, 19.95, 20.0),
                          (D(2023, 8, 29), 20.0, 20.05, 19.95, 20.0),
                          (D(2023, 8, 30), 20.0, 20.05, 19.95, 20.0)]),
        daily_bars('E1', [(D(2023, 8, 24), 5.0, 5.05, 4.95, 5.0),
                          (D(2023, 8, 25), 5.0, 5.02, 4.95, 5.0),
                          (D(2023, 8, 28), 5.2, 5.3, 5.15, 5.2),
                          (D(2023, 8, 29), 5.2, 5.25, 5.15, 5.2),
                          (D(2023, 8, 30), 5.2, 5.25, 5.15, 5.2)]),
        daily_bars('S3', [(D(2023, 8, 28), 25.05, 25.1, 24.9, 25.0),
                          (D(2023, 8, 29), 25.02, 25.08, 24.90, 25.0),
                          (D(2023, 8, 30), 25.0, 25.1, 24.9, 25.0)]),
    ])
    half = pl.concat([
        half_bars('S1', [(D(2023, 8, 25), 'am', 10.02, 10.08, 9.90, 10.0),
                         (D(2023, 8, 25), 'pm', 10.0, 10.05, 9.98, 10.0),
                         (D(2023, 8, 28), 'am', 10.0, 10.45, 10.25, 10.0),
                         (D(2023, 8, 28), 'pm', 10.0, 10.05, 9.98, 10.0),
                         (D(2023, 8, 29), 'am', 10.0, 10.02, 9.98, 10.0),
                         (D(2023, 8, 29), 'pm', 10.0, 10.02, 9.98, 10.0),
                         (D(2023, 8, 30), 'am', 10.0, 10.02, 9.98, 10.0),
                         (D(2023, 8, 30), 'pm', 10.0, 10.02, 9.98, 10.0)]),
        half_bars('S2', [(D(2023, 8, 24), 'am', 20.02, 20.05, 19.90, 20.0),
                         (D(2023, 8, 24), 'pm', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 25), 'am', 20.02, 20.08, 19.50, 20.0),
                         (D(2023, 8, 25), 'pm', 20.0, 20.8, 19.98, 20.0),
                         (D(2023, 8, 28), 'am', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 28), 'pm', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 29), 'am', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 29), 'pm', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 30), 'am', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 30), 'pm', 20.0, 20.05, 19.95, 20.0)]),
        half_bars('E1', [(D(2023, 8, 25), 'am', 4.99, 5.01, 4.95, 5.0),
                         (D(2023, 8, 25), 'pm', 5.0, 5.02, 4.98, 5.0),
                         (D(2023, 8, 28), 'am', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 28), 'pm', 5.2, 5.30, 5.18, 5.2),
                         (D(2023, 8, 29), 'am', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 29), 'pm', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 30), 'am', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 30), 'pm', 5.2, 5.22, 5.18, 5.2)]),
        half_bars('S3', [(D(2023, 8, 29), 'am', 25.02, 25.08, 24.90, 25.0),
                         (D(2023, 8, 29), 'pm', 25.0, 25.05, 24.95, 25.0),
                         (D(2023, 8, 30), 'am', 25.0, 25.05, 24.95, 25.0),
                         (D(2023, 8, 30), 'pm', 25.0, 25.05, 24.95, 25.0)]),
    ])
    instruments = instruments_frame([('E1', True, False)])
    signals = [
        sig('S2', D(2023, 8, 23), 'pm', 'buy', 20.00, 1, target=20_000),
        sig('S1', D(2023, 8, 24), 'pm', 'buy', 10.00, 1, target=15_000),
        sig('E1', D(2023, 8, 24), 'pm', 'buy', 5.00, 1, target=10_000),
        sig('S2', D(2023, 8, 25), 'am', 'sell', 20.00, 1, intent='risk'),
        sig('S1', D(2023, 8, 25), 'pm', 'sell', 10.00, 1, intent='risk'),
        sig('E1', D(2023, 8, 28), 'am', 'sell', 5.20, 1, intent='profit'),
        sig('S3', D(2023, 8, 28), 'pm', 'buy', 25.00, 1, target=50_000),
    ]
    res = run(signals, daily, half, instruments=instruments)

    assert res.fills.height == 7
    # -- independent per-fill fee re-derivation (the fee-conservation core) --
    for row in res.fills.iter_rows(named=True):
        notional = row['price'] * row['shares']
        assert row['notional'] == pytest.approx(notional, abs=1e-9)
        commission = max(1e-4 * notional, 5.0)
        if row['side'] == 'sell':
            stamp = 0.0 if row['is_etf'] else \
                (0.001 if row['date'] < D(2023, 8, 28) else 0.0005) * notional
        else:
            stamp = 0.0
        assert row['commission'] == pytest.approx(commission, abs=1e-9), row
        assert row['stamp_tax'] == pytest.approx(stamp, abs=1e-9), row
        expected_net = (-notional - commission if row['side'] == 'buy'
                        else notional - commission - stamp)
        assert row['net_cash_flow'] == pytest.approx(expected_net, abs=1e-9)
    # hand-checked rows: anchors are the section 7.4 references and fills are
    # AT the limit
    s1b = res.fills.filter((pl.col('symbol') == 'S1')
                           & (pl.col('side') == 'buy')).row(0, named=True)
    assert (s1b['shares'], s1b['price'], s1b['commission'],
            s1b['session']) == (1500, 10.0, 5.0, 'am')
    s1s = res.fills.filter((pl.col('symbol') == 'S1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (s1s['date'], s1s['price'], s1s['stamp_tax']) == \
        (D(2023, 8, 28), 10.0, 15000.0 * 0.0005)       # on/after boundary
    s2s = res.fills.filter((pl.col('symbol') == 'S2')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (s2s['date'], s2s['session'], s2s['price'], s2s['stamp_tax']) == \
        (D(2023, 8, 25), 'pm', 20.0, 20000.0 * 0.001)  # before boundary
    e1s = res.fills.filter((pl.col('symbol') == 'E1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert e1s['stamp_tax'] == 0.0 and e1s['is_etf']   # v1 ETF exemption
    s3b = res.fills.filter((pl.col('symbol') == 'S3')).row(0, named=True)
    assert s3b['commission'] == pytest.approx(5.0)     # max(1e-4*50000, 5) = 5
    # the >50k guard does NOT fire at exactly 50,000 (strict >) -- and under
    # the section 7.3 single-name cap a BUY above 50k on a 200k account is
    # impossible anyway (the guard lives on appreciated-position sells)
    assert res.stats['commission_warnings'] == 0
    assert not [w for w in res.warnings if 'anchor mismatch' in w]

    # -- session-level cash/pending ledger rebuilt from fills alone ----------
    calendar = res.daily['date'].to_list()
    cash = 200_000.0
    pend_am, pend_nd = 0.0, 0.0
    qty = {}
    daily_marks = {}
    for key, part in daily.partition_by('symbol', as_dict=True).items():
        daily_marks[key[0]] = dict(zip(part['date'].to_list(),
                                       part['close'].to_list()))
    fills_by_key = {}
    for row in res.fills.iter_rows(named=True):
        fills_by_key.setdefault((row['date'], row['session']), []).append(row)
    for day in calendar:
        # S_am: yesterday's pm-fill proceeds release, then am fills settle
        cash += pend_nd
        pend_nd = 0.0
        for row in fills_by_key.get((day, 'am'), []):
            if row['side'] == 'buy':
                cash += row['net_cash_flow']
                qty[row['symbol']] = qty.get(row['symbol'], 0) + row['shares']
            else:
                pend_am += row['net_cash_flow']     # usable same-day pm
                qty[row['symbol']] = qty.get(row['symbol'], 0) - row['shares']
        # S_pm: am-fill proceeds release, then pm fills settle
        cash += pend_am
        pend_am = 0.0
        for row in fills_by_key.get((day, 'pm'), []):
            if row['side'] == 'buy':
                cash += row['net_cash_flow']
                qty[row['symbol']] = qty.get(row['symbol'], 0) + row['shares']
            else:
                pend_nd += row['net_cash_flow']     # usable next day am
                qty[row['symbol']] = qty.get(row['symbol'], 0) - row['shares']
        mv = sum(n * daily_marks[sym][max(d for d in daily_marks[sym] if d <= day)]
                 for sym, n in qty.items() if n)
        row = res.daily.filter(pl.col('date') == day).row(0, named=True)
        assert row['settled_cash'] == pytest.approx(cash, abs=1e-9), (day, row)
        assert row['pending_am_to_pm'] == pytest.approx(pend_am, abs=1e-9)
        assert row['pending_next_day'] == pytest.approx(pend_nd, abs=1e-9)
        assert row['equity'] == pytest.approx(cash + pend_am + pend_nd + mv,
                                              abs=1e-9)
    # hand-checked milestones
    d25 = res.daily.filter(pl.col('date') == D(2023, 8, 25)).row(0, named=True)
    assert d25['settled_cash'] == pytest.approx(
        200_000.0 - 20_005.0 - 15_005.0 - 10_005.0)
    assert d25['pending_next_day'] == pytest.approx(19_975.0)  # S2 pm sell
    d28 = res.daily.filter(pl.col('date') == D(2023, 8, 28)).row(0, named=True)
    assert d28['settled_cash'] == pytest.approx(
        154_985.0 + 19_975.0 + 14_987.5)
    assert d28['pending_next_day'] == pytest.approx(10_395.0)  # pm ETF sell
    d29 = res.daily.filter(pl.col('date') == D(2023, 8, 29)).row(0, named=True)
    assert d29['settled_cash'] == pytest.approx(
        189_947.5 + 10_395.0 - 50_005.0)


# ---------------------------------------------------------------------------
# item 2 (v1): clip-level T+1 -- same-session sell blocked, next session OK,
#              partial FIFO across acquisition dates
# ---------------------------------------------------------------------------

def test_02_t1_clip():
    daily = daily_bars('T1', [(D(2024, 3, 3), 10.2, 10.3, 10.1, 10.2),
                              (D(2024, 3, 4), 10.2, 10.6, 10.1, 10.5),
                              (D(2024, 3, 5), 10.5, 10.9, 10.4, 10.7),
                              (D(2024, 3, 6), 10.8, 11.0, 10.7, 10.85)])
    half = half_bars('T1', [
        (D(2024, 3, 4), 'am', 10.2, 10.5, 10.1, 10.4),
        (D(2024, 3, 4), 'pm', 10.4, 10.6, 10.1, 10.5),
        (D(2024, 3, 5), 'am', 10.5, 10.7, 10.4, 10.6),
        (D(2024, 3, 5), 'pm', 10.6, 10.8, 10.5, 10.7),
        (D(2024, 3, 6), 'am', 10.8, 10.9, 10.7, 10.8),
        (D(2024, 3, 6), 'pm', 10.8, 10.9, 10.75, 10.85)])
    signals = [
        sig('T1', D(2024, 3, 3), 'pm', 'buy', 10.2, 1, target=10_200),  # 1000
        sig('T1', D(2024, 3, 4), 'pm', 'sell', 10.4, 1, intent='risk'),
        sig('T1', D(2024, 3, 4), 'am', 'sell', 10.6, 1, intent='risk'),
        sig('T1', D(2024, 3, 4), 'pm', 'buy', 10.5, 1, shares=500),     # add clip
        sig('T1', D(2024, 3, 5), 'pm', 'sell', 10.7, 1, intent='risk',
            shares=300),
    ]
    res = run(signals, daily, half)
    # buy #1 fills 03-04 am (dec 03-03 pm); add clip fills 03-05 am
    b1 = res.fills.filter(pl.col('side') == 'buy').row(0, named=True)
    assert (b1['date'], b1['session'], b1['shares']) == (D(2024, 3, 4), 'am', 1000)
    # same-day sell blocked by clip T+1 (sell decided 03-04 pm lives 03-05 am --
    # the FIRST sell, decided 03-03 pm?  no: risk sell decided 03-04 am lives
    # 03-04 pm and is T+1-locked; decided 03-04 pm lives 03-05 am and fills)
    t1l = events_of(res, 'void_t1_locked')
    assert t1l.height == 1 and t1l['date'].item() == D(2024, 3, 4)
    # sell decided 03-04 pm fills 03-05 am: only the 03-04 clip is sellable
    s1 = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert (s1['date'], s1['session'], s1['shares']) == (D(2024, 3, 5), 'am', 1000)
    # the 03-05 pm sell (decided 03-05 pm?  no: decided 03-05 pm lives 03-06 am)
    s2 = res.fills.filter(pl.col('side') == 'sell')
    assert s2.height == 2
    s2r = s2.row(1, named=True)
    assert (s2r['date'], s2r['shares']) == (D(2024, 3, 6), 300)  # FIFO: 03-05 clip
    assert sorted(res.clips_final['shares'].to_list()) == [200]
    assert res.clips_final['acquired'].to_list() == [D(2024, 3, 5)]
    # real T+1 violation scan: every sell fill's consumed clips must have
    # been acquired strictly before the sell date (engine tracks per-clip
    # acquisition dates; a violation means same-day sell of a today-clip)
    for row in res.fills.filter(pl.col('side') == 'sell').to_dicts():
        assert row['date'] > D(2024, 3, 4), \
            'T+1 violation: sell of a today-acquired clip'


# ---------------------------------------------------------------------------
# item 3: lot invariant + corp-action odd lot sellable TODAY (188 sample)
# ---------------------------------------------------------------------------

def test_03_lot_odd():
    daily = pl.concat([
        daily_bars('L', [(D(2024, 5, 3), 10.0, 10.1, 9.9, 10.0),
                         (D(2024, 5, 6), 10.0, 10.1, 9.9, 10.0),
                         (D(2024, 5, 7), 9.0, 9.1, 8.9, 9.0),
                         (D(2024, 5, 8), 7.5, 9.4, 7.4, 7.5),
                         (D(2024, 5, 9), 7.5, 7.6, 7.4, 7.5)]),
    ])
    half = pl.concat([
        half_bars('L', [(D(2024, 5, 6), 'am', 10.0, 10.05, 9.90, 10.0),
                        (D(2024, 5, 6), 'pm', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 5, 7), 'am', 9.0, 9.02, 8.95, 9.0),
                        (D(2024, 5, 7), 'pm', 9.0, 9.02, 8.95, 9.0),
                        (D(2024, 5, 8), 'am', 7.5, 7.55, 7.45, 7.5),
                        (D(2024, 5, 8), 'pm', 7.5, 9.4, 7.45, 7.5),
                        (D(2024, 5, 9), 'am', 7.5, 7.55, 7.45, 7.5),
                        (D(2024, 5, 9), 'pm', 7.5, 7.55, 7.45, 7.5)]),
    ])
    splits = splits_frame([('L', D(2024, 5, 7), 1.5),     # 100 -> 150
                           ('L', D(2024, 5, 8), 1.25)])   # 150 -> 187.5 -> 188
    signals = [
        sig('L', D(2024, 5, 3), 'pm', 'buy', 10.0, 1, target=1_000),   # 100 sh
        sig('L', D(2024, 5, 8), 'am', 'sell', 7.5, 1, intent='risk'),
    ]
    res = run(signals, daily, half, splits=splits)
    assert (res.fills.filter(pl.col('side') == 'buy')['shares'] % 100 == 0).all()
    sells = res.fills.filter(pl.col('side') == 'sell')
    assert sells.height == 1
    s = sells.row(0, named=True)
    assert s['shares'] == 188                       # 150 x1.25 -> 187.5 -> 188
    assert s['date'] == D(2024, 5, 8)               # sold TODAY of the split
    assert 'odd_lot_exit' in s['detail']
    assert res.stats['odd_lot_exits'] == 1
    assert res.clips_final.height == 0
    # explicit non-lot shares are rejected outright
    with pytest.raises(BandContractError, match='multiple of 100'):
        run([sig('L', D(2024, 5, 3), 'pm', 'buy', 10.0, shares=250)], daily, half)


# ---------------------------------------------------------------------------
# item 4: cash non-negativity + priority consumption (same session)
# ---------------------------------------------------------------------------

def test_04_cash_priority():
    """Same-session cash competition in priority order.  Under the section
    7.3 caps: PD is AFFORDABLE but breaches the single-name 25% cap
    (52,005 > 50,000) -> cap void; PE needs 160,005 with only 111,990
    available -> full-funding void; both higher-priority orders fill."""
    daily = pl.concat([
        daily_bars('PA', [(D(2024, 3, 3), 40.0, 40.1, 39.9, 40.0),
                          (D(2024, 3, 4), 40.2, 40.5, 39.9, 40.0)]),
        daily_bars('PB', [(D(2024, 3, 3), 100.0, 100.1, 99.9, 100.0),
                          (D(2024, 3, 4), 100.2, 100.5, 99.9, 100.0)]),
        daily_bars('PD', [(D(2024, 3, 3), 100.0, 100.1, 99.9, 100.0),
                          (D(2024, 3, 4), 100.2, 100.5, 99.9, 100.0)]),
        daily_bars('PE', [(D(2024, 3, 3), 100.0, 100.1, 99.9, 100.0),
                          (D(2024, 3, 4), 100.2, 100.5, 99.9, 100.0)]),
    ])
    half = pl.concat([
        half_bars('PA', [(D(2024, 3, 4), 'am', 40.2, 40.5, 39.9, 40.0),
                         (D(2024, 3, 4), 'pm', 40.0, 40.2, 39.95, 40.0)]),
        half_bars('PB', [(D(2024, 3, 4), 'am', 100.2, 100.5, 99.9, 100.0),
                         (D(2024, 3, 4), 'pm', 100.0, 100.2, 99.95, 100.0)]),
        half_bars('PD', [(D(2024, 3, 4), 'am', 100.2, 100.5, 99.9, 100.0),
                         (D(2024, 3, 4), 'pm', 100.0, 100.2, 99.95, 100.0)]),
        half_bars('PE', [(D(2024, 3, 4), 'am', 100.2, 100.5, 99.9, 100.0),
                         (D(2024, 3, 4), 'pm', 100.0, 100.2, 99.95, 100.0)]),
    ])
    signals = [
        sig('PA', D(2024, 3, 3), 'pm', 'buy', 40.0, 1, shares=1200),
        sig('PD', D(2024, 3, 3), 'pm', 'buy', 101.0, 2, shares=500),
        sig('PB', D(2024, 3, 3), 'pm', 'buy', 100.0, 3, shares=400),
        sig('PE', D(2024, 3, 3), 'pm', 'buy', 100.0, 4, shares=1600),
    ]
    res = run(signals, daily, half)
    # PA (p1) 1200@40 = 48,005 -> ~24% of equity: fills, cash 151,995.
    # PD (p2) 520@100 = 52,005: affordable but 52,005 > 50,000 (25% of
    # ~200k) -> void_cap_single_name (never downsized).
    # PB (p3) 400@100 = 40,005 -> fills, cash 111,990.
    # PE (p4) 1600@100 = 160,005 > 111,990 -> void_insufficient_cash.
    pa = res.fills.filter(pl.col('symbol') == 'PA').row(0, named=True)
    pb = res.fills.filter(pl.col('symbol') == 'PB').row(0, named=True)
    assert (pa['shares'], pa['price']) == (1200, 40.0)
    assert (pb['shares'], pb['price']) == (400, 100.0)
    assert res.fills.height == 2
    assert events_of(res, 'void_cap_single_name')['symbol'].to_list() == ['PD']
    assert events_of(res, 'void_insufficient_cash')['symbol'].to_list() == ['PE']
    booked = events_of(res, 'filled_limit_buy')['symbol'].to_list()
    assert booked == ['PA', 'PB']
    assert (res.daily['settled_cash'] >= 0).all()
    d4 = res.daily.filter(pl.col('date') == D(2024, 3, 4)).row(0, named=True)
    assert d4['settled_cash'] == pytest.approx(200_000.0 - 48_005.0 - 40_005.0)
    assert res.stats['caps']['single_name_voids'] == 1
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 1
    assert res.stats['commission_warnings'] == 0


# ---------------------------------------------------------------------------
# item 5: touch (session low == p) does NOT fill; penetration fills at p
# ---------------------------------------------------------------------------

def test_05_touch_penetrate():
    daily = pl.concat([
        daily_bars('TA', [(D(2024, 6, 2), 10.0, 10.1, 9.9, 10.0),
                          (D(2024, 6, 3), 10.4, 10.5, 10.00, 10.3)]),
        daily_bars('TB', [(D(2024, 6, 2), 10.0, 10.1, 9.9, 10.0),
                          (D(2024, 6, 3), 10.4, 10.5, 9.99, 10.3)]),
    ])
    half = pl.concat([
        half_bars('TA', [(D(2024, 6, 3), 'am', 10.3, 10.5, 10.00, 10.4),
                         (D(2024, 6, 3), 'pm', 10.35, 10.45, 10.2, 10.3)]),
        half_bars('TB', [(D(2024, 6, 3), 'am', 10.3, 10.5, 9.99, 10.4),
                         (D(2024, 6, 3), 'pm', 10.35, 10.45, 10.2, 10.3)]),
    ])
    signals = [sig('TA', D(2024, 6, 2), 'pm', 'buy', 10.00, 1, target=20_000),
               sig('TB', D(2024, 6, 2), 'pm', 'buy', 10.00, 1, target=20_000)]
    res = run(signals, daily, half)
    assert res.fills.filter(pl.col('symbol') == 'TA').height == 0
    touch = res.events.filter((pl.col('symbol') == 'TA')
                              & (pl.col('event') == 'not_penetrated')).row(0, named=True)
    assert touch['limit_price'] == 10.0 and touch['ref_price'] == 10.0
    tb = res.fills.filter(pl.col('symbol') == 'TB').row(0, named=True)
    assert (tb['date'], tb['session'], tb['price'], tb['shares']) == \
        (D(2024, 6, 3), 'am', 10.0, 2000)     # fill AT the limit, not at 9.99


# ---------------------------------------------------------------------------
# item 6: corporate actions (split per clip, per-lot dividend, F2 exact)
# ---------------------------------------------------------------------------

def test_06_corporate_actions():
    daily = pl.concat([
        daily_bars('PD', [(D(2015, 1, 4), 10.0, 10.05, 9.95, 10.0),
                          (D(2015, 1, 5), 10.0, 10.2, 9.95, 10.0),
                          (D(2015, 1, 6), 10.0, 10.1, 9.9, 10.0),
                          (D(2015, 1, 7), 9.6, 9.7, 9.55, 9.65),
                          (D(2015, 1, 8), 9.65, 9.75, 9.6, 9.7),
                          (D(2015, 1, 9), 9.7, 9.8, 9.65, 9.75)]),
        daily_bars('ST', [(D(2015, 1, 4), 10.0, 10.05, 9.95, 10.0),
                          (D(2015, 1, 5), 10.0, 10.2, 9.95, 10.0),
                          (D(2015, 1, 6), 9.2, 9.3, 9.1, 9.2),
                          (D(2015, 1, 7), 9.2, 9.3, 9.15, 9.25),
                          (D(2015, 1, 8), 7.2, 7.3, 7.1, 7.2),
                          (D(2015, 1, 9), 7.2, 7.3, 7.15, 7.25)]),
    ])
    half = pl.concat([
        half_bars('PD', [(D(2015, 1, 5), 'am', 10.0, 10.15, 9.95, 10.0),
                         (D(2015, 1, 5), 'pm', 10.0, 10.1, 9.98, 10.0),
                         (D(2015, 1, 6), 'am', 10.0, 10.05, 9.95, 10.0),
                         (D(2015, 1, 6), 'pm', 10.0, 10.05, 9.95, 10.0),
                         (D(2015, 1, 7), 'am', 9.6, 9.68, 9.55, 9.65),
                         (D(2015, 1, 7), 'pm', 9.65, 9.7, 9.6, 9.65),
                         (D(2015, 1, 8), 'am', 9.68, 9.72, 9.6, 9.7),
                         (D(2015, 1, 8), 'pm', 9.7, 9.72, 9.65, 9.7),
                         (D(2015, 1, 9), 'am', 9.7, 9.78, 9.65, 9.75),
                         (D(2015, 1, 9), 'pm', 9.75, 9.78, 9.7, 9.75)]),
        half_bars('ST', [(D(2015, 1, 5), 'am', 10.0, 10.15, 9.95, 10.0),
                         (D(2015, 1, 5), 'pm', 10.0, 10.1, 9.98, 10.0),
                         (D(2015, 1, 6), 'am', 9.2, 9.25, 9.15, 9.2),
                         (D(2015, 1, 6), 'pm', 9.2, 9.25, 9.15, 9.2),
                         (D(2015, 1, 7), 'am', 9.2, 9.28, 9.15, 9.25),
                         (D(2015, 1, 7), 'pm', 9.25, 9.28, 9.2, 9.25),
                         (D(2015, 1, 8), 'am', 7.2, 7.25, 7.15, 7.2),
                         (D(2015, 1, 8), 'pm', 7.2, 7.25, 7.15, 7.2),
                         (D(2015, 1, 9), 'am', 7.2, 7.28, 7.15, 7.25),
                         (D(2015, 1, 9), 'pm', 7.25, 7.28, 7.2, 7.25)]),
    ])
    splits = splits_frame([('ST', D(2015, 1, 6), 1.1), ('ST', D(2015, 1, 8), 1.3)])
    dividends = dividends_frame([('PD', D(2015, 1, 7), 41.0, 100)])
    signals = [sig('PD', D(2015, 1, 4), 'pm', 'buy', 10.0, 1, target=10_000),
               sig('PD', D(2015, 1, 8), 'pm', 'sell', 9.7, 1, intent='risk'),
               sig('ST', D(2015, 1, 4), 'pm', 'buy', 10.0, 1, target=10_000)]
    res = run(signals, daily, half, splits=splits, cash_dividends=dividends)

    assert events_of(res, 'corp_action_split').filter(
        pl.col('detail').str.starts_with('PD')).height == 0
    div = events_of(res, 'corp_action_dividend').row(0, named=True)
    assert div['cash_amount'] == pytest.approx(410.0)  # 41.0/100 x 1000 pre-ex
    d6 = res.daily.filter(pl.col('date') == D(2015, 1, 6)).row(0, named=True)
    d7 = res.daily.filter(pl.col('date') == D(2015, 1, 7)).row(0, named=True)
    assert d6['settled_cash'] == pytest.approx(200_000.0 - 2 * 10_005.0)
    assert d7['settled_cash'] == pytest.approx(200_000.0 - 2 * 10_005.0 + 410.0)
    pd_sell = res.fills.filter((pl.col('symbol') == 'PD')
                               & (pl.col('side') == 'sell')).row(0, named=True)
    assert pd_sell['shares'] == 1000                   # dividend: no share change
    sp = events_of(res, 'corp_action_split')
    assert [(r['ratio'], r['shares']) for r in sp.iter_rows(named=True)] == \
        [(1.1, 1100), (1.3, 1430)]                     # F2: per-event ratios
    # m4: per-clip splitting creates sub-clips; total = 1000 -> 1100 -> 1430
    st_clips = res.clips_final.filter(pl.col('symbol') == 'ST')
    assert st_clips['shares'].sum() == 1430
    assert sorted(st_clips['acquired'].to_list()) ==         [D(2015, 1, 5), D(2015, 1, 6), D(2015, 1, 8), D(2015, 1, 8)]
    assert res.stats['corp_actions'] == {
        'splits': 2, 'dividends': 1, 'dividend_cash_total_pre_tax': 410.0}


def test_06b_real_600000_corp_actions():
    """Item 6 on the real stock/dates: sh.600000 2017-05-25 (x1.3 + dividend)
    and 2022-07-21 (pure dividend).  Reads the two registered bundle files
    read-only; bars are synthetic around the real ex-dates."""
    root = Path(__file__).resolve().parents[1]
    bundle = root / 'data/processed/rqalpha-bundle-v2-1-20260918'
    splits_all, _ = load_split_factor_h5(bundle / 'split_factor.h5')
    divs_all, _ = load_dividends_h5(bundle / 'dividends.h5')
    splits = splits_all.filter(pl.col('symbol') == 'sh.600000')
    divs = divs_all.filter(pl.col('symbol') == 'sh.600000')
    assert splits['ex_date'].to_list() == [D(2016, 6, 23), D(2017, 5, 25)]
    assert splits['split_factor'].to_list() == [1.1, 1.3]

    daily = daily_bars('sh.600000', [(D(2022, 7, 19), 7.79, 7.85, 7.75, 7.79),
                                     (D(2022, 7, 20), 7.79, 7.85, 7.75, 7.79),
                                     (D(2022, 7, 21), 7.40, 7.50, 7.35, 7.45),
                                     (D(2022, 7, 22), 7.45, 7.55, 7.40, 7.50)])
    half = half_bars('sh.600000', [
        (D(2022, 7, 20), 'am', 7.79, 7.83, 7.76, 7.80),
        (D(2022, 7, 20), 'pm', 7.80, 7.84, 7.75, 7.79),
        (D(2022, 7, 21), 'am', 7.40, 7.48, 7.36, 7.45),
        (D(2022, 7, 21), 'pm', 7.45, 7.50, 7.38, 7.45),
        (D(2022, 7, 22), 'am', 7.45, 7.53, 7.41, 7.50),
        (D(2022, 7, 22), 'pm', 7.50, 7.54, 7.42, 7.50)])
    signals = [sig('sh.600000', D(2022, 7, 19), 'pm', 'buy', 7.79, 1, shares=1000),
               sig('sh.600000', D(2022, 7, 21), 'pm', 'sell', 7.45, 1,
                   intent='risk')]
    res = run(signals, daily, half, splits=splits, cash_dividends=divs)
    assert events_of(res, 'corp_action_split').height == 0
    div = events_of(res, 'corp_action_dividend').row(0, named=True)
    assert div['cash_amount'] == pytest.approx(410.0)
    sell = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert sell['shares'] == 1000                       # pure dividend: unchanged

    daily = daily_bars('sh.600000', [(D(2017, 5, 22), 16.0, 16.05, 15.95, 16.0),
                                     (D(2017, 5, 23), 16.0, 16.05, 15.95, 16.0),
                                     (D(2017, 5, 24), 16.0, 16.1, 15.85, 16.0),
                                     (D(2017, 5, 25), 12.4, 12.5, 12.3, 12.4),
                                     (D(2017, 5, 26), 12.4, 12.5, 12.35, 12.45),
                                     (D(2017, 5, 29), 12.45, 12.55, 12.40, 12.50)])
    half = half_bars('sh.600000', [
        (D(2017, 5, 24), 'am', 16.0, 16.08, 15.86, 15.9),
        (D(2017, 5, 24), 'pm', 15.9, 16.05, 15.85, 16.0),
        (D(2017, 5, 25), 'am', 12.4, 12.45, 12.32, 12.4),
        (D(2017, 5, 25), 'pm', 12.4, 12.45, 12.32, 12.4),
        (D(2017, 5, 26), 'am', 12.4, 12.48, 12.36, 12.45),
        (D(2017, 5, 26), 'pm', 12.45, 12.48, 12.38, 12.45),
        (D(2017, 5, 29), 'am', 12.45, 12.52, 12.41, 12.50),
        (D(2017, 5, 29), 'pm', 12.50, 12.52, 12.42, 12.50)])
    signals = [sig('sh.600000', D(2017, 5, 23), 'pm', 'buy', 16.0, 1, shares=1000),
               sig('sh.600000', D(2017, 5, 26), 'pm', 'sell', 12.45, 1,
                   intent='risk')]
    res = run(signals, daily, half, splits=splits, cash_dividends=divs)
    sp = events_of(res, 'corp_action_split').row(0, named=True)
    assert sp['ratio'] == 1.3 and sp['shares'] == 1300
    div = events_of(res, 'corp_action_dividend').row(0, named=True)
    assert div['cash_amount'] == pytest.approx(200.0)   # 20.0/100 x 1000 pre-ex
    sell = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert sell['shares'] == 1300 and sell['price'] == 12.45
    d25 = res.daily.filter(pl.col('date') == D(2017, 5, 25)).row(0, named=True)
    assert d25['settled_cash'] == pytest.approx(200_000.0 - 16_005.0 + 200.0)


def test_06c_split_loader_anchor_regression():
    """F2 loader regression: (0, 1.0)-style anchor rows are dropped and the
    first real change-point keeps its OWN per-event ratio."""
    import h5py
    import numpy as np
    import tempfile
    split_dtype = np.dtype([('ex_date', np.int64), ('split_factor', np.float64)])
    arr = np.zeros(3, dtype=split_dtype)
    arr[0] = (0, 1.0)
    arr[1] = (20150106000000, 1.1)
    arr[2] = (20150108000000, 1.3)
    path = Path(tempfile.gettempdir()) / 'test_band_contract_splits.h5'
    with h5py.File(path, 'w') as f:
        f.create_dataset('600000.XSHG', data=arr)
    try:
        frame, meta = load_split_factor_h5(path)
        assert meta['anchor_rows_dropped'] == 1
        assert frame['ex_date'].to_list() == [D(2015, 1, 6), D(2015, 1, 8)]
        assert frame['split_factor'].to_list() == [1.1, 1.3]
        assert frame['symbol'].unique().to_list() == ['sh.600000']
    finally:
        path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# item 7: half-day suspension voids that session; limit legality
# ---------------------------------------------------------------------------

def test_07_suspension_limit():
    daily = pl.concat([
        daily_bars('SE', [(D(2016, 2, 29), 10.0, 10.05, 9.95, 10.0),
                          (D(2016, 3, 1), 10.0, 10.1, 9.9, 10.0),
                          (D(2016, 3, 2), 10.0, 10.2, 9.9, 10.1),
                          (D(2016, 3, 3), 10.1, 10.2, 10.0, 10.1)]),
        daily_bars('SF', [(D(2016, 2, 29), 10.3, 10.35, 10.25, 10.3),
                          (D(2016, 3, 1), 10.4, 10.5, 10.3, 10.4),
                          (D(2016, 3, 2), 10.4, 10.45, 10.2, 10.3),
                          (D(2016, 3, 3), 10.9, 11.2, 10.9, 11.0)]),
        daily_bars('SG', [(D(2016, 2, 29), 10.0, 10.05, 9.95, 10.0),
                          (D(2016, 3, 1), 10.0, 10.2, 9.9, 10.0),
                          (D(2016, 3, 2), 10.0, 10.1, 9.95, 10.0)]),
    ])
    half = pl.concat([
        half_bars('SE', [(D(2016, 3, 1), 'pm', 10.0, 10.05, 9.98, 10.0),   # am missing
                         (D(2016, 3, 2), 'am', 10.0, 10.15, 9.90, 10.1),
                         (D(2016, 3, 2), 'pm', 10.1, 10.15, 10.05, 10.1),
                         (D(2016, 3, 3), 'am', 10.1, 10.15, 10.05, 10.1),
                         (D(2016, 3, 3), 'pm', 10.1, 10.15, 10.05, 10.1)]),
        half_bars('SF', [(D(2016, 3, 1), 'am', 10.4, 10.45, 10.35, 10.4),
                         (D(2016, 3, 1), 'pm', 10.4, 10.45, 10.35, 10.4),
                         (D(2016, 3, 2), 'am', 10.4, 10.45, 10.2, 10.3),
                         (D(2016, 3, 2), 'pm', 10.3, 10.35, 10.25, 10.3),
                         (D(2016, 3, 3), 'am', 10.9, 11.2, 10.90, 11.0),
                         (D(2016, 3, 3), 'pm', 11.0, 11.1, 10.95, 11.0)]),
        half_bars('SG', [(D(2016, 3, 1), 'am', 10.0, 10.15, 9.9, 10.0),
                         (D(2016, 3, 1), 'pm', 10.0, 10.1, 9.95, 10.0),
                         (D(2016, 3, 2), 'am', 10.0, 10.08, 9.95, 10.0),
                         (D(2016, 3, 2), 'pm', 10.0, 10.05, 9.95, 10.0)]),
    ])
    limits = pl.concat([
        auto_limits(daily.filter(pl.col('symbol') == 'SE')),
        pl.DataFrame({
            'symbol': ['SF', 'SF'], 'date': [D(2016, 3, 2), D(2016, 3, 3)],
            'limit_up': [10.5, 12.0], 'limit_down': [9.5, 9.0]}),
    ])
    signals = [sig('SE', D(2016, 2, 29), 'pm', 'buy', 10.0, 1, target=10_000),
               sig('SE', D(2016, 3, 1), 'pm', 'buy', 10.0, 1, target=10_000),
               sig('SF', D(2016, 2, 29), 'pm', 'buy', 11.0, 1, target=22_000),
               sig('SF', D(2016, 3, 1), 'pm', 'buy', 11.0, 1, target=22_000),
               sig('SF', D(2016, 3, 2), 'pm', 'buy', 11.0, 1, target=22_000),
               sig('SG', D(2016, 2, 29), 'pm', 'buy', 10.0, 1, target=10_000),
               sig('SG', D(2016, 3, 1), 'pm', 'buy', 10.0, 1, target=10_000)]
    res = run(signals, daily, half, limits)
    # half-day suspension: am session void on 03-01, re-issue fills 03-02
    se = res.fills.filter(pl.col('symbol') == 'SE').row(0, named=True)
    assert (se['date'], se['session'], se['price']) == (D(2016, 3, 2), 'am', 10.0)
    se_sus = res.events.filter((pl.col('symbol') == 'SE')
                               & (pl.col('event') == 'void_suspended'))
    assert se_sus.height == 1 and se_sus['date'].item() == D(2016, 3, 1)
    # limit legality: out-of-range on 03-02, refilled inside range on 03-03
    sf_bad = res.events.filter((pl.col('symbol') == 'SF')
                               & (pl.col('event') == 'void_limit_out_of_range'))
    assert sf_bad.height == 1 and sf_bad['date'].item() == D(2016, 3, 2)
    sf = res.fills.filter(pl.col('symbol') == 'SF').row(0, named=True)
    assert (sf['date'], sf['price'], sf['shares']) == (D(2016, 3, 3), 11.0, 2000)
    # missing limit rows: never validateable, never fills.  SG has no limit
    # rows at all; SF's first decision point (03-01) also has none in this
    # fixture (the SF overrides start 03-02) -> both void there
    assert res.fills.filter(pl.col('symbol') == 'SG').height == 0
    assert events_of(res, 'void_no_limit_info')['symbol'].to_list() == \
        ['SF', 'SG', 'SG']
    assert res.stats['void_days']['suspended'] >= 1
    assert res.stats['void_days']['limit_out_of_range'] == 1
    assert res.stats['void_days']['no_limit_info'] == 3


# ---------------------------------------------------------------------------
# item 8 (v1): risk K=3 counted in SESSIONS with open fallback + limit-down
#              defer; profit intent expires silently
# ---------------------------------------------------------------------------

def test_08_risk_k3_profit():
    daily = pl.concat([
        daily_bars('KA', [(D(2016, 5, 31), 30.0, 30.05, 29.95, 30.0),
                          (D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),
                          (D(2016, 6, 2), 29.8, 29.9, 28.9, 29.0),
                          (D(2016, 6, 3), 27.4, 27.6, 27.0, 27.4),
                          (D(2016, 6, 6), 27.4, 27.5, 27.0, 27.4)]),
        daily_bars('KB', [(D(2016, 5, 31), 30.0, 30.05, 29.95, 30.0),
                          (D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),
                          (D(2016, 6, 2), 29.8, 29.9, 28.9, 29.0),
                          (D(2016, 6, 3), 26.0, 27.1, 24.5, 26.0),
                          (D(2016, 6, 6), 26.4, 26.5, 26.0, 26.2)]),
        daily_bars('KP', [(D(2016, 5, 31), 30.0, 30.05, 29.95, 30.0),
                          (D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),
                          (D(2016, 6, 2), 29.8, 29.9, 28.9, 29.0),
                          (D(2016, 6, 3), 27.4, 27.6, 27.0, 27.4),
                          (D(2016, 6, 6), 27.4, 27.5, 27.0, 27.4)]),
    ])
    half = pl.concat([
        half_bars('KA', [(D(2016, 5, 31), 'pm', 30.0, 30.05, 29.95, 30.0),
        (D(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
                         (D(2016, 6, 1), 'pm', 30.0, 30.1, 29.95, 30.0),
                         (D(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
                         (D(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
                         (D(2016, 6, 3), 'am', 27.5, 27.5, 27.0, 27.4),
                         (D(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4),
                         (D(2016, 6, 6), 'am', 27.4, 27.45, 27.0, 27.4),
                         (D(2016, 6, 6), 'pm', 27.4, 27.45, 27.0, 27.4)]),
        half_bars('KB', [(D(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
                         (D(2016, 6, 1), 'pm', 30.0, 30.1, 29.95, 30.0),
                         (D(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
                         (D(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
                         (D(2016, 6, 3), 'am', 26.0, 26.0, 25.5, 26.0),
                         (D(2016, 6, 3), 'pm', 24.6, 27.1, 24.5, 26.0),
                         (D(2016, 6, 6), 'am', 26.4, 26.5, 26.0, 26.2),
                         (D(2016, 6, 6), 'pm', 26.2, 26.3, 26.0, 26.2)]),
        half_bars('KP', [(D(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
                         (D(2016, 6, 1), 'pm', 30.0, 30.1, 29.95, 30.0),
                         (D(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
                         (D(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
                         (D(2016, 6, 3), 'am', 27.5, 27.5, 27.0, 27.4),
                         (D(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4),
                         (D(2016, 6, 6), 'am', 27.4, 27.45, 27.0, 27.4),
                         (D(2016, 6, 6), 'pm', 27.4, 27.45, 27.0, 27.4)]),
    ])
    overrides = {('KB', D(2016, 6, 3)): (29.6, 24.66),   # pm opens limit-down
                 ('KB', D(2016, 6, 6)): (28.8, 24.2)}
    limits = auto_limits(daily, overrides)
    signals = []
    for sym in ('KA', 'KB', 'KP'):
        signals.append(sig(sym, D(2016, 5, 31), 'pm', 'buy', 30.0, 1,
                           target=30_000))
    # risk sells re-issued at EVERY decision point (section 7.5 cadence)
    for sym, day, sess, q in [
            ('KA', D(2016, 6, 1), 'pm', 30.0), ('KA', D(2016, 6, 2), 'am', 29.5),
            ('KA', D(2016, 6, 2), 'pm', 29.0)]:
        signals.append(sig(sym, day, sess, 'sell', q, 1, intent='risk'))
    for sym, day, sess, q in [
            ('KB', D(2016, 6, 1), 'pm', 30.0), ('KB', D(2016, 6, 2), 'am', 29.5),
            ('KB', D(2016, 6, 2), 'pm', 29.0), ('KB', D(2016, 6, 3), 'am', 28.5),
            ('KB', D(2016, 6, 3), 'pm', 28.0)]:
        signals.append(sig(sym, day, sess, 'sell', q, 1, intent='risk'))
    for sym, day, sess, q in [
            ('KP', D(2016, 6, 1), 'pm', 30.0), ('KP', D(2016, 6, 2), 'am', 29.5),
            ('KP', D(2016, 6, 2), 'pm', 28.5)]:
        signals.append(sig(sym, day, sess, 'sell', q, 1, intent='profit'))
    res = run(signals, daily, half, limits)

    # KA: streaks 1..3 (06-02 am, 06-02 pm, 06-03 am) -> fallback 06-03 pm
    ka_streaks = res.events.filter((pl.col('symbol') == 'KA')
                                   & (pl.col('event') == 'not_penetrated'))
    assert [(r['date'], r['session']) for r in ka_streaks.iter_rows(named=True)] == \
        [(D(2016, 6, 2), 'am'), (D(2016, 6, 2), 'pm'), (D(2016, 6, 3), 'am')]
    ka = res.fills.filter((pl.col('symbol') == 'KA')
                          & (pl.col('side') == 'sell')).row(0, named=True)
    assert (ka['fill_type'], ka['date'], ka['session'], ka['price']) == \
        ('market_fallback', D(2016, 6, 3), 'pm', 27.5)
    assert ka['net_cash_flow'] == pytest.approx(27_500.0 - 5.0 - 27.5)
    # pnl vs previous official close (06-02 close 29.0)
    assert res.stats['k3_fallback']['pnl_contribution_list'][0] == \
        pytest.approx(27_467.5 - 29_000.0)

    # KB: 06-03 pm opens limit-down -> deferred; executes 06-06 am at open
    kb_def = events_of(res, 'market_exit_deferred_limitdown').row(0, named=True)
    assert (kb_def['date'], kb_def['session']) == (D(2016, 6, 3), 'pm')
    kb = res.fills.filter((pl.col('symbol') == 'KB')
                          & (pl.col('side') == 'sell')).row(0, named=True)
    assert (kb['fill_type'], kb['date'], kb['session'], kb['price']) == \
        ('market_fallback', D(2016, 6, 6), 'am', 26.4)
    kb_streaks = res.events.filter((pl.col('symbol') == 'KB')
                                   & (pl.col('event') == 'not_penetrated'))
    assert kb_streaks.height == 4        # 06-02 am/pm, 06-03 am, 06-03 pm

    # KP: profit intent expires silently, never market-exited
    assert res.fills.filter((pl.col('symbol') == 'KP')
                            & (pl.col('side') == 'sell')).height == 0
    assert events_of(res, 'market_exit_filled').filter(
        pl.col('detail').str.contains('KP')).height == 0
    kp_exp = events_of(res, 'session_expired').filter(
        pl.col('symbol') == 'KP')
    assert kp_exp.height == 3
    assert res.clips_final.filter(pl.col('symbol') == 'KP')['shares'].item() == 1000

    k3 = res.stats['k3_fallback']
    assert k3['armed'] == 2 and k3['executed'] == 2
    assert k3['deferred_limitdown_sessions'] == 1
    assert len(k3['pnl_contribution_list']) == 2


# ---------------------------------------------------------------------------
# item 9 (v1): am proceeds usable same-day pm; pm proceeds next-day am;
#              same-session sell->buy forbidden
# ---------------------------------------------------------------------------

def test_09_proceeds_timing():
    """Section 7.2 cash timing: am-fill proceeds are usable from the SAME
    day's pm session (P5's re-issued buy is only affordable after the
    am-sell release); pm-fill proceeds release the NEXT day's am (P2 sell
    -> pending carried overnight).  A same-session sell->buy path is
    forbidden: P2's first add live 09-06 am sees only 42,975 even though
    89,900 of am-sell proceeds are pending that very session."""
    daily = pl.concat([
        daily_bars('P1', [(D(2016, 9, 1), 150.00, 150.10, 149.90, 150.00), (D(2016, 9, 2), 150.05, 150.10, 149.90, 150.00), (D(2016, 9, 5), 150.02, 150.08, 149.95, 150.00), (D(2016, 9, 6), 150.50, 151.00, 149.90, 150.00), (D(2016, 9, 7), 150.90, 151.20, 150.70, 151.00), (D(2016, 9, 8), 150.50, 150.55, 150.40, 150.50), (D(2016, 9, 9), 150.00, 150.10, 149.90, 150.00)]),
        daily_bars('P2', [(D(2016, 9, 1), 60.00, 60.10, 59.90, 60.00), (D(2016, 9, 2), 60.05, 60.10, 59.90, 60.00), (D(2016, 9, 5), 60.02, 60.08, 59.95, 60.00), (D(2016, 9, 6), 60.10, 60.30, 59.90, 60.00), (D(2016, 9, 7), 60.10, 60.30, 59.90, 60.00), (D(2016, 9, 8), 60.00, 60.10, 59.90, 60.00), (D(2016, 9, 9), 60.00, 60.10, 59.90, 60.00)]),
        daily_bars('P4', [(D(2016, 9, 1), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 2), 50.05, 50.10, 49.90, 50.00), (D(2016, 9, 5), 50.02, 50.08, 49.95, 50.00), (D(2016, 9, 6), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 7), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 8), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 9), 50.00, 50.10, 49.90, 50.00)]),
        daily_bars('P5', [(D(2016, 9, 1), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 2), 50.05, 50.10, 49.90, 50.00), (D(2016, 9, 5), 50.02, 50.08, 49.95, 50.00), (D(2016, 9, 6), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 7), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 8), 50.00, 50.10, 49.90, 50.00), (D(2016, 9, 9), 50.00, 50.10, 49.90, 50.00)]),
    ])
    half = pl.concat([
        half_bars('P1', [(D(2016, 9, 2), 'am', 150.02, 150.08, 149.90, 150.00), (D(2016, 9, 2), 'pm', 150.00, 150.05, 149.95, 150.00), (D(2016, 9, 6), 'am', 150.50, 151.00, 149.90, 150.00), (D(2016, 9, 6), 'pm', 150.10, 150.20, 149.95, 150.00)]),
        half_bars('P2', [(D(2016, 9, 2), 'am', 60.02, 60.08, 59.90, 60.00), (D(2016, 9, 2), 'pm', 60.00, 60.05, 59.95, 60.00), (D(2016, 9, 5), 'am', 60.00, 60.05, 59.95, 60.00), (D(2016, 9, 5), 'pm', 60.00, 60.05, 59.95, 60.00), (D(2016, 9, 6), 'am', 60.10, 60.30, 59.90, 60.00), (D(2016, 9, 6), 'pm', 60.00, 60.20, 59.90, 60.00), (D(2016, 9, 7), 'am', 60.10, 60.30, 59.90, 60.00), (D(2016, 9, 7), 'pm', 60.00, 60.20, 59.90, 60.00), (D(2016, 9, 8), 'am', 60.00, 60.10, 59.90, 60.00), (D(2016, 9, 8), 'pm', 60.00, 60.10, 59.90, 60.00)]),
        half_bars('P4', [(D(2016, 9, 2), 'am', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 2), 'pm', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 5), 'am', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 5), 'pm', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 6), 'am', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 6), 'pm', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 7), 'am', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 7), 'pm', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 8), 'am', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 8), 'pm', 50.00, 50.05, 49.95, 50.00)]),
        half_bars('P5', [(D(2016, 9, 2), 'am', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 2), 'pm', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 5), 'am', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 5), 'pm', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 6), 'am', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 6), 'pm', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 7), 'am', 50.00, 50.05, 49.95, 50.00), (D(2016, 9, 7), 'pm', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 8), 'am', 50.00, 50.05, 49.90, 50.00), (D(2016, 9, 8), 'pm', 50.00, 50.05, 49.90, 50.00)]),
    ])
    signals = [
        # setup (all live 09-02 am, all under the 25% single-name cap)
        sig('P1', D(2016, 9, 1), 'pm', 'buy', 150.0, 1, shares=300),
        sig('P2', D(2016, 9, 1), 'pm', 'buy', 60.0, 2, shares=700),
        sig('P4', D(2016, 9, 1), 'pm', 'buy', 50.0, 3, shares=900),
        sig('P5', D(2016, 9, 1), 'pm', 'buy', 50.0, 4, shares=500),
        # 09-05 pm decisions, live 09-06 am:
        sig('P1', D(2016, 9, 5), 'pm', 'sell', 150.0, 1, intent='risk'),
        sig('P2', D(2016, 9, 5), 'pm', 'buy', 60.0, 1, shares=800),
        sig('P5', D(2016, 9, 5), 'pm', 'buy', 50.0, 2, shares=1000),
        # 09-06 am decision, live 09-06 pm:
        sig('P5', D(2016, 9, 6), 'am', 'buy', 50.0, 1, shares=400),
        # 09-06 pm decision, live 09-07 am:
        sig('P2', D(2016, 9, 6), 'pm', 'sell', 60.0, 1, intent='risk'),
        sig('P2', D(2016, 9, 8), 'am', 'sell', 60.0, 1, intent='risk'),
    ]
    res = run(signals, daily, half)
    # setup: cash 200,000 - 157,020 = 42,980
    #   (P1 45,005 + P2 42,010 + P4 45,005 + P5 25,005)
    d2 = res.daily.filter(pl.col('date') == D(2016, 9, 2)).row(0, named=True)
    assert d2['settled_cash'] == pytest.approx(42_980.0)
    # (a) same-session prohibition: the 09-06 am sells fill (P1 +44,950
    #     pending) but P2's 48,005 add sees only 42,975 of cash ->
    #     void_insufficient_cash (same-session sell->buy forbidden)
    v = res.events.filter((pl.col('symbol') == 'P2')
                          & (pl.col('date') == D(2016, 9, 6))
                          & (pl.col('session') == 'am'))
    assert v['event'].to_list() == ['void_insufficient_cash']
    p1s = res.fills.filter((pl.col('symbol') == 'P1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (p1s['date'], p1s['session'], p1s['shares']) == \
        (D(2016, 9, 6), 'am', 300)
    # (b) am proceeds release at pm: P5's re-issued 50,005 buy fills 09-06 pm
    p5 = res.fills.filter((pl.col('symbol') == 'P5')
                          & (pl.col('side') == 'buy')).to_dicts()
    assert [(r['date'], r['session'], r['shares']) for r in p5] == \
        [(D(2016, 9, 2), 'am', 500), (D(2016, 9, 6), 'pm', 400)]
    d6 = res.daily.filter(pl.col('date') == D(2016, 9, 6)).row(0, named=True)
    assert d6['settled_cash'] == pytest.approx(67_925.0)
    # (c) P2 sells its remaining 700 shares on 09-07 (proceeds settle
    #     same-day pm); P2 is then flat
    p2s = res.fills.filter((pl.col('symbol') == 'P2')
                           & (pl.col('side') == 'sell')).to_dicts()
    assert [(r['date'], r['session'], r['shares']) for r in p2s] == \
        [(D(2016, 9, 7), 'am', 700)]
    d7 = res.daily.filter(pl.col('date') == D(2016, 9, 7)).row(0, named=True)
    assert d7['settled_cash'] == pytest.approx(67_925.0 + 41_953.0)
    assert d7['pending_am_to_pm'] == 0.0
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 2
# ---------------------------------------------------------------------------
# item 10: stamp segmentation (2023-08-27 vs 2023-08-28) + ETF exemption
# ---------------------------------------------------------------------------

def test_10_stamp_segmentation():
    daily = pl.concat([
        daily_bars('X1', [(D(2023, 8, 24), 10.0, 10.1, 9.9, 10.0),
                          (D(2023, 8, 25), 10.1, 10.2, 9.9, 10.0),
                          (D(2023, 8, 27), 10.0, 10.2, 9.95, 10.1),
                          (D(2023, 8, 28), 10.0, 10.1, 9.95, 10.0)]),
        daily_bars('X2', [(D(2023, 8, 24), 10.0, 10.1, 9.9, 10.0),
                          (D(2023, 8, 25), 10.1, 10.2, 9.9, 10.0),
                          (D(2023, 8, 27), 10.0, 10.05, 9.95, 10.0),
                          (D(2023, 8, 28), 10.0, 10.3, 10.0, 10.2)]),
        daily_bars('E', [(D(2023, 8, 24), 5.0, 5.05, 4.95, 5.0),
                         (D(2023, 8, 25), 5.0, 5.05, 4.95, 5.0),
                         (D(2023, 8, 27), 5.0, 5.1, 4.95, 5.0),
                         (D(2023, 8, 28), 5.0, 5.05, 4.95, 5.0)]),
    ])
    half = pl.concat([
        half_bars('X1', [(D(2023, 8, 25), 'am', 10.05, 10.15, 9.90, 10.0),
                         (D(2023, 8, 25), 'pm', 10.0, 10.05, 9.95, 10.0),
                         (D(2023, 8, 27), 'am', 10.0, 10.1, 9.95, 10.05),
                         (D(2023, 8, 27), 'pm', 10.05, 10.2, 10.0, 10.1),
                         (D(2023, 8, 28), 'am', 10.0, 10.05, 9.95, 10.0),
                         (D(2023, 8, 28), 'pm', 10.0, 10.05, 9.95, 10.0)]),
        half_bars('X2', [(D(2023, 8, 25), 'am', 10.05, 10.15, 9.90, 10.0),
                         (D(2023, 8, 25), 'pm', 10.0, 10.05, 9.95, 10.0),
                         (D(2023, 8, 27), 'am', 10.0, 10.03, 9.95, 10.0),
                         (D(2023, 8, 27), 'pm', 10.0, 10.02, 9.95, 10.0),
                         (D(2023, 8, 28), 'am', 10.0, 10.3, 10.0, 10.2),
                         (D(2023, 8, 28), 'pm', 10.2, 10.25, 10.1, 10.2)]),
        half_bars('E', [(D(2023, 8, 25), 'am', 5.0, 5.02, 4.95, 5.0),
                        (D(2023, 8, 25), 'pm', 5.0, 5.02, 4.98, 5.0),
                        (D(2023, 8, 27), 'am', 5.0, 5.08, 4.98, 5.0),
                        (D(2023, 8, 27), 'pm', 5.0, 5.1, 4.98, 5.0),
                        (D(2023, 8, 28), 'am', 5.0, 5.03, 4.98, 5.0),
                        (D(2023, 8, 28), 'pm', 5.0, 5.02, 4.98, 5.0)]),
    ])
    instruments = instruments_frame([('E', True, False)])
    signals = [sig('X1', D(2023, 8, 24), 'pm', 'buy', 10.0, 1, target=20_000),
               sig('X1', D(2023, 8, 27), 'am', 'sell', 10.0, 1, intent='risk'),
               sig('X2', D(2023, 8, 24), 'pm', 'buy', 10.0, 1, target=20_000),
               sig('X2', D(2023, 8, 27), 'pm', 'sell', 10.0, 1, intent='risk'),
               sig('E', D(2023, 8, 24), 'pm', 'buy', 5.0, 1, target=10_000),
               sig('E', D(2023, 8, 27), 'am', 'sell', 5.0, 1, intent='risk')]
    res = run(signals, daily, half, instruments=instruments)
    x1s = res.fills.filter((pl.col('symbol') == 'X1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    x2s = res.fills.filter((pl.col('symbol') == 'X2')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    es = res.fills.filter((pl.col('symbol') == 'E')
                          & (pl.col('side') == 'sell')).row(0, named=True)
    assert x1s['date'] == D(2023, 8, 27)
    assert x1s['stamp_tax'] == pytest.approx(20_000.0 * 0.001)
    assert x2s['date'] == D(2023, 8, 28)
    assert x2s['stamp_tax'] == pytest.approx(20_000.0 * 0.0005)
    assert es['stamp_tax'] == 0.0 and es['is_etf']
    assert stamp_rate(D(2023, 8, 27)) == 0.001
    assert stamp_rate(D(2023, 8, 28)) == 0.0005


# ---------------------------------------------------------------------------
# item 14: frame schema regression (ENGINE-1)
# ---------------------------------------------------------------------------

def test_14_frame_schema_regression():
    """ENGINE-1 scale regression: logs longer than the 100-row inference
    window whose first 100 rows carry ratio/cash_amount = None (events) or
    prev_close = None (fills, buy phase) must build with the DECLARED schema
    dtypes (Null builder + f64 append crashed before the authorized fix)."""
    from quant.backtest import band_engine as be

    events = []
    for i in range(150):
        events.append({
            'date': D(2020, 1, 1), 'symbol': 'X', 'side': 'buy',
            'order_id': 'X-buy-2019-12-31', 'event': 'not_penetrated',
            'priority': 1, 'limit_price': 10.0, 'ref_price': 10.0,
            'shares': None, 'ratio': None, 'cash_amount': None, 'detail': ''})
    events.append({
        'date': D(2020, 2, 3), 'symbol': '', 'side': '', 'order_id': '',
        'event': 'corp_action_split', 'priority': None, 'limit_price': None,
        'ref_price': None, 'shares': 200, 'ratio': 2.0, 'cash_amount': None,
        'detail': 'X: shares 100 -> 200 (split_factor ratio 2.0)'})
    events.append({
        'date': D(2020, 2, 4), 'symbol': '', 'side': '', 'order_id': '',
        'event': 'corp_action_dividend', 'priority': None, 'limit_price': None,
        'ref_price': None, 'shares': None, 'ratio': None, 'cash_amount': 41.0,
        'detail': 'X: dividend'})
    ev = be._frame(events, be._EVENT_SCHEMA)
    assert ev.height == 152
    assert ev.schema['ratio'] == pl.Float64 and ev.schema['cash_amount'] == pl.Float64
    assert ev['ratio'][-2] == 2.0 and ev['cash_amount'][-1] == 41.0
    for col, dtype in be._EVENT_SCHEMA.items():
        assert ev.schema[col] == dtype, col

    fills = []
    for i in range(150):
        fills.append({
            'fill_id': 'F%06d' % i, 'order_id': 'X-buy-2019-12-31',
            'symbol': 'X', 'side': 'buy', 'intent': '', 'fill_type': 'limit',
            'date': D(2020, 1, 2), 'session': 'am',
            'decision_date': D(2019, 12, 31), 'decision_session': 'pm',
            'priority': 1, 'shares': 100, 'price': 10.0, 'notional': 1000.0,
            'commission': 5.0, 'stamp_tax': 0.0, 'fees_total': 5.0,
            'net_cash_flow': -1005.0, 'is_etf': False, 'detail': ''})
    fills.append({
        'fill_id': 'F000151', 'order_id': 'X-sell-2020-01-31', 'symbol': 'X',
        'side': 'sell', 'intent': 'risk', 'fill_type': 'limit',
        'date': D(2020, 2, 3), 'session': 'am',
        'decision_date': D(2020, 1, 31), 'decision_session': 'pm',
        'priority': 1, 'shares': 100, 'price': 10.5, 'notional': 1050.0,
        'commission': 5.0, 'stamp_tax': 1.05, 'fees_total': 6.05,
        'net_cash_flow': 1043.95, 'is_etf': False, 'detail': ''})
    fl = be._frame(fills, be._FILL_SCHEMA)
    assert fl.height == 151
    for col, dtype in be._FILL_SCHEMA.items():
        assert fl.schema[col] == dtype, col


# ---------------------------------------------------------------------------
# NEW 15: multi-clip adds + FIFO partial sell
# ---------------------------------------------------------------------------

def test_15_multi_clip_fifo():
    daily = pl.concat([
        daily_bars('M', [(D(2024, 5, 3), 10.0, 10.1, 9.9, 10.0),
                         (D(2024, 5, 6), 10.0, 10.1, 9.9, 10.0),
                         (D(2024, 5, 7), 10.4, 10.7, 10.3, 10.6),
                         (D(2024, 5, 8), 10.5, 10.7, 10.4, 10.6)]),
    ])
    half = pl.concat([
        half_bars('M', [(D(2024, 5, 6), 'am', 10.0, 10.05, 9.90, 10.0),
                        (D(2024, 5, 6), 'pm', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 5, 7), 'am', 10.45, 10.55, 10.40, 10.5),
                        (D(2024, 5, 7), 'pm', 10.5, 10.7, 10.40, 10.6),
                        (D(2024, 5, 8), 'am', 10.6, 10.65, 10.45, 10.6),
                        (D(2024, 5, 8), 'pm', 10.6, 10.7, 10.50, 10.6)]),
    ])
    signals = [
        sig('M', D(2024, 5, 3), 'pm', 'buy', 10.0, 1, target=5_000),   # 500 sh
        sig('M', D(2024, 5, 6), 'pm', 'buy', 10.5, 1, shares=300),     # 300 sh
        sig('M', D(2024, 5, 7), 'pm', 'sell', 10.6, 1, intent='profit',
            shares=600),
    ]
    res = run(signals, daily, half)
    buys = res.fills.filter(pl.col('side') == 'buy')
    assert buys['shares'].to_list() == [500, 300]
    assert buys['price'].to_list() == [10.0, 10.5]
    sell = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert sell['shares'] == 600                      # FIFO: clip1 500 + 100
    assert sell['date'] == D(2024, 5, 8)
    cf = res.clips_final.to_dicts()
    assert len(cf) == 1 and cf[0]['shares'] == 200
    assert cf[0]['acquired'] == D(2024, 5, 7)         # clip1 fully consumed
    assert res.stats['odd_lot_exits'] == 0            # 600 is a lot multiple


# ---------------------------------------------------------------------------
# NEW 16: T+0 same-day round trip vs stock blocked
# ---------------------------------------------------------------------------

def test_16_t0_roundtrip():
    """T+0 same-day round trip: S_am buy -> S_pm sell succeeds for the T+0
    ETF and is blocked for the stock.  A same-SESSION T+0 round trip (buy and
    sell both live in S_pm) is forbidden: the intraday path is
    unobservable."""
    daily = pl.concat([
        daily_bars('E', [(D(2024, 6, 2), 5.0, 5.05, 4.95, 5.0),
                         (D(2024, 6, 3), 5.0, 5.15, 4.9, 5.1),
                         (D(2024, 6, 4), 5.05, 5.15, 5.0, 5.1)]),
        daily_bars('S', [(D(2024, 6, 2), 10.0, 10.05, 9.95, 10.0),
                         (D(2024, 6, 3), 10.0, 10.15, 9.9, 10.0),
                         (D(2024, 6, 4), 10.0, 10.1, 9.9, 10.0)]),
    ])
    half = pl.concat([
        half_bars('E', [(D(2024, 6, 2), 'am', 5.0, 5.02, 4.95, 5.0),
                        (D(2024, 6, 2), 'pm', 5.0, 5.02, 4.98, 5.0),
                        (D(2024, 6, 3), 'am', 5.0, 5.02, 4.95, 5.0),
                        (D(2024, 6, 3), 'pm', 5.0, 5.15, 4.98, 5.1),
                        (D(2024, 6, 4), 'am', 5.1, 5.12, 5.05, 5.1),
                        (D(2024, 6, 4), 'pm', 5.1, 5.12, 5.05, 5.1)]),
        half_bars('S', [(D(2024, 6, 2), 'am', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 6, 2), 'pm', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 6, 3), 'am', 10.0, 10.05, 9.90, 10.0),
                        (D(2024, 6, 3), 'pm', 10.0, 10.15, 9.95, 10.0),
                        (D(2024, 6, 4), 'am', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 6, 4), 'pm', 10.0, 10.05, 9.95, 10.0)]),
    ])
    instruments = instruments_frame([('E', True, True), ('S', False, False)])
    signals = [
        sig('E', D(2024, 6, 2), 'pm', 'buy', 5.00, 1, target=10_000),
        sig('E', D(2024, 6, 3), 'am', 'sell', 5.10, 1, intent='risk'),
        sig('S', D(2024, 6, 2), 'pm', 'buy', 10.00, 1, target=10_000),
        sig('S', D(2024, 6, 3), 'am', 'sell', 10.05, 1, intent='risk'),
        # same-session T+0 round trip: forbidden (path unobservable); the
        # profit-intent sell finds its clip session-locked -> expires
        sig('E', D(2024, 6, 3), 'am', 'buy', 5.10, 2, target=5_100),
        sig('E', D(2024, 6, 3), 'am', 'sell', 5.15, 2, intent='profit'),
    ]
    res = run(signals, daily, half, instruments=instruments)
    e_b = res.fills.filter((pl.col('symbol') == 'E')
                           & (pl.col('side') == 'buy')).to_dicts()
    assert [(r['date'], r['session'], r['shares']) for r in e_b] ==         [(D(2024, 6, 3), 'am', 2000), (D(2024, 6, 3), 'pm', 1000)]
    e_s = res.fills.filter((pl.col('symbol') == 'E')
                           & (pl.col('side') == 'sell')).to_dicts()
    # T+0: the S_am clip is sellable in S_pm the same day
    assert [(r['date'], r['session'], r['shares']) for r in e_s] ==         [(D(2024, 6, 3), 'pm', 2000)]
    assert e_s[0]['stamp_tax'] == 0.0
    s_b = res.fills.filter((pl.col('symbol') == 'S')
                           & (pl.col('side') == 'buy')).row(0, named=True)
    assert (s_b['date'], s_b['session']) == (D(2024, 6, 3), 'am')
    s_v = res.events.filter((pl.col('symbol') == 'S')
                            & (pl.col('event') == 'void_t1_locked'))
    assert s_v.height == 1               # stock: same-day sell blocked
    assert res.fills.filter((pl.col('symbol') == 'S')
                            & (pl.col('side') == 'sell')).height == 0
    # E2's same-session pair (buy+sell both live 06-03 pm): the sell runs
    # before the buy books, so it can only consume the earlier am clip; the
    # pm clip it would round-trip stays held (same-session round trip
    # forbidden by the clip-session lock)
    assert res.clips_final.filter(pl.col('symbol') == 'E')['shares'].to_list() ==         [1000]
    assert len([r for r in res.fills.to_dicts()
                if r['symbol'] == 'E' and r['side'] == 'sell']) == 1


# ---------------------------------------------------------------------------
# NEW 17: 11:30 decision (am.close anchor) fills in S_pm; pm anchor-mismatch
#         warning
# ---------------------------------------------------------------------------

def test_17_am_reanchor_fill():
    daily = daily_bars('AR', [(D(2024, 7, 1), 10.35, 10.5, 10.25, 10.35),
                              (D(2024, 7, 2), 10.9, 11.0, 10.85, 10.95)])
    half = half_bars('AR', [
        (D(2024, 7, 1), 'am', 10.35, 10.4, 10.30, 10.4),
        (D(2024, 7, 1), 'pm', 10.38, 10.42, 10.30, 10.35),
        (D(2024, 7, 2), 'am', 10.9, 11.0, 10.85, 10.95),
        (D(2024, 7, 2), 'pm', 10.95, 11.0, 10.9, 10.95)])
    signals = [
        sig('AR', D(2024, 7, 1), 'am', 'buy', 10.4, 1, target=10_000),   # am.close
        sig('AR', D(2024, 7, 1), 'pm', 'buy', 10.9, 1, shares=100),      # mismatch
    ]
    res = run(signals, daily, half)
    b1 = res.fills.filter(pl.col('side') == 'buy').to_dicts()[0]
    assert (b1['date'], b1['session'], b1['price']) == (D(2024, 7, 1), 'pm', 10.4)
    b2 = res.fills.to_dicts()[-1]
    assert (b2['date'], b2['session'], b2['price']) == (D(2024, 7, 2), 'am', 10.9)
    mismatch = [w for w in res.warnings if 'anchor mismatch' in w]
    assert len(mismatch) == 1 and 'official daily close 10.35' in mismatch[0]


# ---------------------------------------------------------------------------
# NEW 18: close bridge -- pre-cutoff mark = OFFICIAL daily close (not
#         pm.close); bridge assertions raise on violations
# ---------------------------------------------------------------------------

def test_18_close_bridge():
    daily = daily_bars('BR', [(D(2017, 5, 23), 15.9, 16.0, 15.85, 15.9),
                              (D(2017, 5, 24), 16.0, 16.1, 15.80, 16.00),
                              (D(2017, 5, 25), 15.8, 15.9, 15.75, 15.8)])
    half = half_bars('BR', [
        (D(2017, 5, 23), 'am', 15.9, 15.95, 15.86, 15.9),
        (D(2017, 5, 23), 'pm', 15.9, 15.98, 15.85, 15.9),
        (D(2017, 5, 24), 'am', 15.95, 16.05, 15.85, 15.9),
        (D(2017, 5, 24), 'pm', 15.9, 16.0, 15.80, 15.85),   # pm.close 15.85
        (D(2017, 5, 25), 'am', 15.8, 15.85, 15.76, 15.8),
        (D(2017, 5, 25), 'pm', 15.8, 15.85, 15.76, 15.8)])
    # bridge: pre-cutoff pm.close mismatch disclosed, not raised
    info = assert_daily_halfday_bridge(daily, half)
    assert info['pm_close_mismatches_pre_cutoff'] >= 1

    signals = [sig('BR', D(2017, 5, 23), 'pm', 'buy', 15.9, 1, shares=1000)]
    res = run(signals, daily, half)
    b = res.fills.row(0, named=True)
    assert (b['date'], b['session'], b['price'], b['shares']) == \
        (D(2017, 5, 24), 'am', 15.9, 1000)
    # the 05-24 daily mark MUST be the official close 16.00 (not pm 15.85)
    d24 = res.daily.filter(pl.col('date') == D(2017, 5, 24)).row(0, named=True)
    assert d24['positions_value'] == pytest.approx(1000 * 16.00)
    assert d24['equity'] == pytest.approx(200_000.0 - 15_905.0 + 16_000.0)

    # post-cutoff pm.close mismatch: disclosed as a count (cross-source
    # rounding + closing-auction aggregation), never used as a mark
    bad_daily = daily_bars('BR2', [(D(2020, 7, 1), 10.0, 10.6, 9.9, 10.5)])
    bad_half = half_bars('BR2', [(D(2020, 7, 1), 'pm', 10.0, 10.5, 9.95, 10.0)])
    info_bad = assert_daily_halfday_bridge(bad_daily, bad_half)
    assert info_bad['pm_close_mismatches_post_cutoff'] >= 1
    assert abs(10.0 - 10.5) > 0.011  # the fixture mismatch is within one tick
    # half-day extreme outside the official daily range: DISCLOSED (count +
    # samples in the returned dict), not fatal -- the delivered halfday table
    # has 3 such rows in 18.5M (data-quality disclosure per section 7.4)
    bad_half2 = half_bars('BR2', [(D(2020, 7, 1), 'pm', 10.0, 10.7, 9.95, 10.5)])
    info2 = assert_daily_halfday_bridge(bad_daily, bad_half2)
    assert info2['range_violations'] == 1


# ---------------------------------------------------------------------------
# NEW 19: section 7.3 caps (single-name 25%, total 100%)
# ---------------------------------------------------------------------------

def test_19_caps():
    """Section 7.3 caps.  Single-name 25%% is enforced and reachable (hold
    22% -> add to 24% fills -> a further add would breach 25%% and voids).
    The total cap is DEFENSE-IN-DEPTH: for a fully funded affordable order
    MV + cost + fee <= cash + MV == equity, so it is mathematically implied
    by the funding rule and cannot fire on an affordable order (asserted as
    a zero counter with that comment)."""
    daily = pl.concat([
        daily_bars('A', [(D(2024, 3, 3), 40.0, 40.1, 39.9, 40.0),
                         (D(2024, 3, 4), 40.0, 40.1, 39.9, 40.0),
                         (D(2024, 3, 5), 40.0, 40.1, 39.9, 40.0),
                         (D(2024, 3, 6), 40.0, 40.1, 39.9, 40.0),
                         (D(2024, 3, 7), 40.0, 40.1, 39.9, 40.0)]),
    ])
    half = half_bars('A', [
        (D(2024, 3, 4), 'am', 40.0, 40.05, 39.9, 40.0),
        (D(2024, 3, 4), 'pm', 40.0, 40.05, 39.95, 40.0),
        (D(2024, 3, 5), 'am', 40.0, 40.05, 39.9, 40.0),
        (D(2024, 3, 5), 'pm', 40.0, 40.05, 39.95, 40.0),
        (D(2024, 3, 6), 'am', 40.0, 40.05, 39.9, 40.0),
        (D(2024, 3, 6), 'pm', 40.0, 40.05, 39.95, 40.0),
        (D(2024, 3, 7), 'am', 40.0, 40.05, 39.9, 40.0),
        (D(2024, 3, 7), 'pm', 40.0, 40.05, 39.95, 40.0)])
    signals = [
        # 1,100 @40 = 44,005 -> ~22% of equity: fills
        sig('A', D(2024, 3, 3), 'pm', 'buy', 40.0, 1, shares=1100),
        # +100 @40: 48,000 MV -> 24% of ~200k: still under 25%: fills
        sig('A', D(2024, 3, 4), 'pm', 'buy', 40.0, 1, shares=100),
        # +100 @40: 52,005 -> 26%: breaches the single-name cap: voids
        sig('A', D(2024, 3, 5), 'pm', 'buy', 40.0, 1, shares=100),
    ]
    res = run(signals, daily, half)
    assert res.fills.filter(pl.col('side') == 'buy')['shares'].to_list() ==         [1100, 100]
    a_void = res.events.filter((pl.col('symbol') == 'A')
                               & (pl.col('event') == 'void_cap_single_name'))
    assert a_void.height == 1
    assert a_void['shares'].item() == 100
    assert res.stats['caps']['single_name_voids'] == 1
    assert res.stats['caps']['total_voids'] == 0   # implied by full funding
    assert sorted(res.clips_final['shares'].to_list()) == [100, 1100]


# ---------------------------------------------------------------------------
# guards: freeze line, decision validation, duplicates, empty signals
# ---------------------------------------------------------------------------

def test_00_input_guards():
    bad_half = half_bars('Z', [(D(2025, 1, 2), 'am', 10.0, 10.1, 9.9, 10.0)])
    with pytest.raises(BandContractError, match='freeze violation'):
        assert_frozen(bad_half, 'trade_date', 'halfday')
    good_daily = daily_bars('Z', [(D(2024, 12, 30), 10.0, 10.1, 9.9, 10.0)])
    good_half = half_bars('Z', [(D(2024, 12, 30), 'am', 10.0, 10.1, 9.9, 10.0),
                                (D(2024, 12, 30), 'pm', 10.0, 10.1, 9.9, 10.0)])
    bad_sig = signals_frame([sig('Z', D(2025, 1, 2), 'am', 'buy', 10.0,
                                 target=10_000)])
    with pytest.raises(BandContractError, match='freeze violation'):
        run(bad_sig, good_daily, good_half)
    with pytest.raises(BandContractError, match='freeze violation'):
        assert_frozen(signals_frame([sig('Z', D(2025, 1, 2), 'am', 'buy', 10.0,
                                         target=10_000)]),
                      'decision_date', 'signals')

    # decision_session must be am/pm
    with pytest.raises(BandContractError, match="decision_session"):
        run([sig('Z', D(2024, 12, 27), 'noon', 'buy', 10.0, target=10_000)],
            good_daily, good_half)
    # sell without intent is rejected
    with pytest.raises(BandContractError, match='intent'):
        run([sig('Z', D(2024, 12, 27), 'pm', 'sell', 10.0)], good_daily, good_half)
    # duplicate same-name signal at one decision point
    with pytest.raises(BandContractError, match='duplicate signal'):
        run([sig('Z', D(2024, 12, 27), 'pm', 'buy', 10.0, target=10_000),
             sig('Z', D(2024, 12, 27), 'pm', 'buy', 10.0, target=10_000)],
            good_daily, good_half)
    # explicit non-lot shares rejected
    with pytest.raises(BandContractError, match='multiple of 100'):
        run([sig('Z', D(2024, 12, 27), 'pm', 'buy', 10.0, shares=250)],
            good_daily, good_half)
    # pm decision on a non-trading day: anchor reference missing -> loud
    # warning (host supplies the anchor; engine does not hard-fail)
    non_trading = daily_bars('Z', [(D(2024, 12, 28), 10.0, 10.1, 9.9, 10.0)])
    non_trading_half = half_bars('Z', [(D(2024, 12, 28), 'am', 10.0, 10.05,
                                        9.9, 10.0),
                                       (D(2024, 12, 28), 'pm', 10.0, 10.05,
                                        9.9, 10.0)])
    res_nt = run([sig('Z', D(2024, 12, 27), 'pm', 'buy', 10.0, target=10_000)],
                 non_trading, non_trading_half)
    assert any('anchor reference missing' in w for w in res_nt.warnings)

    # read layer filters a mixed-year daily parquet
    import tempfile
    path = Path(tempfile.gettempdir()) / 'test_band_contract_freeze.parquet'
    mixed = pl.concat([
        daily_bars('Z', [(D(2024, 12, 30), 10.0, 10.1, 9.9, 10.0)]),
        daily_bars('Z', [(D(2025, 1, 2), 10.0, 10.1, 9.9, 10.0)]),
    ])
    mixed.write_parquet(path)
    try:
        frame, meta = load_daily_panel(path)
        assert frame['date'].max() == D(2024, 12, 30) <= FREEZE_END
        assert meta['rows_dropped_by_freeze'] == 1
    finally:
        path.unlink(missing_ok=True)

    # empty signal table runs through and reports zero activity
    res = run([], good_daily, good_half)
    assert res.fills.height == 0
    assert res.daily['equity'].to_list() == pytest.approx([200_000.0])


# ---------------------------------------------------------------------------
# NEW 20: partial risk-exit fallback (explicit shares, M1)
# ---------------------------------------------------------------------------

def test_20_partial_risk_exit_fallback():
    """M1: a risk sell with EXPLICIT shares (partial risk-exit) triggers the
    K=3 fallback after 3 unfilled sessions but sells only the explicit
    quantity, retaining the rest of the position."""
    daily = pl.concat([
        daily_bars('PR', [(D(2016, 5, 31), 30.0, 30.05, 29.95, 30.0),
                          (D(2016, 6, 1), 30.2, 30.25, 29.90, 30.0),
                          (D(2016, 6, 2), 29.8, 29.9, 29.0, 29.0),
                          (D(2016, 6, 3), 27.5, 27.5, 27.0, 27.4),
                          (D(2016, 6, 3), 27.5, 27.5, 27.0, 27.4)])])
    half = half_bars('PR', [
        (D(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
        (D(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
        (D(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
        (D(2016, 6, 3), 'am', 27.5, 27.5, 27.0, 27.4),
        (D(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4)])
    signals = [
        sig('PR', D(2016, 5, 31), 'pm', 'buy', 30.0, 1, target=30_000),
        sig('PR', D(2016, 6, 1), 'pm', 'sell', 30.0, intent='risk',
            shares=800),
        sig('PR', D(2016, 6, 2), 'am', 'sell', 29.5, intent='risk',
            shares=800),
        sig('PR', D(2016, 6, 2), 'pm', 'sell', 29.0, intent='risk',
            shares=800),
    ]
    res = run(signals, daily, half)
    b = res.fills.filter(pl.col('side') == 'buy').row(0, named=True)
    assert (b['date'], b['shares'], b['price']) == (D(2016, 6, 1), 1000, 30.0)
    # 3 unfilled sessions -> armed -> 06-03 pm fallback
    # (K=3 fires with explicit shares -> only 800 sold, not full position)
    kf = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert (kf['fill_type'], kf['date'], kf['session'], kf['price'],
            kf['shares']) == \
        ('market_fallback', D(2016, 6, 3), 'pm', 27.5, 800)
    assert res.clips_final['shares'].to_list() == [200]
    assert res.stats['k3_fallback']['executed'] == 1


# ---------------------------------------------------------------------------
# NEW 21: m4 送转 added whole-lot clip (acquired = ex-date, next-day sellable)
# ---------------------------------------------------------------------------

def test_21_m4_split_added_whole_lot_clip():
    """m4 regression: 送转 added shares form a new clip with acquired =
    ex-date (not the original date); same-day sell blocked by T+1; next-day
    sellable.  Uses a 2x split on 500 shares -> 500 original + 500 added."""
    daily = pl.concat([
        daily_bars('W', [(D(2024, 6, 30), 20.0, 20.1, 19.9, 20.0),
                         (D(2024, 7, 1), 20.0, 20.1, 19.9, 20.0),
                         (D(2024, 7, 2), 20.0, 20.1, 19.9, 20.0),
                         (D(2024, 7, 3), 10.0, 10.1, 9.9, 10.0),   # ex-date
                         (D(2024, 7, 4), 10.0, 10.1, 9.9, 10.0),
                         (D(2024, 7, 5), 10.0, 10.1, 9.9, 10.0)]),
    ])
    half = pl.concat([
        half_bars('W', [(D(2024, 7, 1), 'am', 20.0, 20.05, 19.90, 20.0),
                        (D(2024, 7, 1), 'pm', 20.0, 20.05, 19.95, 20.0),
                        (D(2024, 7, 2), 'am', 20.0, 20.05, 19.90, 20.0),
                        (D(2024, 7, 2), 'pm', 20.0, 20.05, 19.95, 20.0),
                        (D(2024, 7, 3), 'am', 10.0, 10.05, 9.90, 10.0),
                        (D(2024, 7, 3), 'pm', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 7, 4), 'am', 10.0, 10.05, 9.90, 10.0),
                        (D(2024, 7, 4), 'pm', 10.0, 10.05, 9.95, 10.0),
                        (D(2024, 7, 5), 'am', 10.0, 10.05, 9.90, 10.0),
                        (D(2024, 7, 5), 'pm', 10.0, 10.05, 9.95, 10.0)]),
    ])
    splits = splits_frame([('W', D(2024, 7, 3), 2.0)])
    signals = [
        sig('W', D(2024, 6, 30), 'pm', 'buy', 20.0, 1, shares=500),
        sig('W', D(2024, 7, 2), 'pm', 'sell', 10.0, 1, intent='risk'),  # entire sellable
    ]
    res = run(signals, daily, half, splits=splits)
    # same-day sell on ex-date: only the 500 original shares are sellable
    # (the 500 added shares are acquired today -> T+1 locked)
    sp = events_of(res, 'corp_action_split').row(0, named=True)
    assert sp['ratio'] == 2.0 and sp['shares'] == 1000
    sell = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert (sell['date'], sell['shares'], sell['price']) ==         (D(2024, 7, 3), 500, 10.0)
    assert res.clips_final['shares'].to_list() == [500]
