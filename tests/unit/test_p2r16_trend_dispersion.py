"""Unit tests for P2-R16 (exp-20260918-p2r16-trend-dispersion).

Prereg-mandated cases: the R8 mechanism reuse hash assertion and its
published-stat behavioral anchor, the H-47 buffer-band state machine
(entry/exit boundaries), month-end sampling of the frozen T200-40 path,
integer board lots and cash conservation, the 9.5% limit proxy blocks with
postpone semantics, B3' seed determinism, the Q5 double-high composite rank
construction, the 2025+ freeze boundary, fee segmentation, ex-dividend value
continuity of the chain-unit accounting, and force-exit on quote end.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from quant.research import p2r16_trend_dispersion as r16


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def weekday_sessions(n: int, start: date = date(2015, 1, 5)) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def cal_frame(dates: list[date]) -> pl.DataFrame:
    return pl.DataFrame({
        'date': dates,
        'mkt_idx': list(range(len(dates))),
    }).with_columns(pl.col('mkt_idx').cast(pl.Int64))


def raw_daily_frame(paths: dict[str, list[dict]]) -> pl.DataFrame:
    """rows: {'date', 'open', 'close', 'preclose', 'amount', 'turn',
    'isST', 'tradestatus'} per symbol (the processed-dataset schema)."""
    frames = []
    for sym, rows in paths.items():
        frames.append(pl.DataFrame({
            'symbol': [sym] * len(rows),
            **{k: [r[k] for r in rows] for k in rows[0]},
        }))
    return pl.concat(frames, how='vertical')


def constant_rows(dates: list[date], price: float = 10.0,
                  amount: float = 1.0e8, turn: float = 1.0,
                  is_st: float = 0.0) -> list[dict]:
    return [{'date': d, 'open': price, 'close': price,
             'preclose': price, 'amount': amount, 'turn': turn,
             'isST': is_st, 'tradestatus': 1.0} for d in dates]


def chain_columns(df: pl.DataFrame) -> pl.DataFrame:
    """c_adj/o_adj exactly as the module computes them (bridge)."""
    df = df.sort('symbol', 'date')
    df = df.with_columns(
        (pl.col('close') / pl.col('preclose')).cum_prod().over('symbol')
        .alias('c_adj'))
    df = df.with_columns(
        (pl.col('c_adj').shift(1).over('symbol')
         * pl.col('open') / pl.col('preclose')).alias('o_adj'))
    return df.with_columns(
        pl.int_range(pl.len()).over('symbol', order_by='date')
        .alias('mkt_idx'))


def make_bank(paths: dict[str, list[dict]],
              calendar: list[date]) -> r16.PriceBank:
    df = raw_daily_frame(paths)
    df = chain_columns(df)
    return r16.PriceBank(df, calendar, sorted(paths))


def flat_pools(ranked_by_signal: dict[date, list[str]],
               q5: dict[str, bool] | None = None) -> dict[date, dict]:
    return {s: {'ranked': ranked, 'q5': q5 or {}, 'n': len(ranked)}
            for s, ranked in ranked_by_signal.items()}


def pool_frame_from(hist: pl.DataFrame,
                    signals: pl.DataFrame) -> pl.DataFrame:
    return r16.signal_pools(hist, signals)


# --------------------------------------------------------------------------- #
# 1. R8 mechanism reuse: hash assertion + behavioral anchor + index basis
# --------------------------------------------------------------------------- #
def test_r8_mechanism_hash_assertion_passes_and_tamper_fails() -> None:
    out = r16.assert_mechanism_identity()
    assert out['module_sha256'] == r16.R8_MODULE_SHA256
    assert set(out['function_source_sha256']) >= {
        'sma_trend_state', 'exposures_from_state'}
    saved = r16.R8_MODULE_SHA256
    r16.R8_MODULE_SHA256 = '0' * 64
    try:
        with pytest.raises(RuntimeError, match='FAIL-CLOSED'):
            r16.assert_mechanism_identity()
    finally:
        r16.R8_MODULE_SHA256 = saved


def test_t200_state_is_index_based_and_falls_back_risk_off() -> None:
    """The frozen T200-40 basis is the INDEX series (R8 code as published),
    and the unavailable-SMA fallback is risk-off (e_low)."""
    dates = weekday_sessions(260)
    closes = [100.0 + i for i in range(260)]  # monotonically rising index
    index_close = pl.DataFrame({'trade_date': dates, 'close': closes})
    # calendar extends 10 sessions BEFORE the index starts: fallback there
    cal = [date(2014, 12, 1) + timedelta(days=i) for i in range(10)] + dates
    state = r16.t200_state(index_close, cal)
    assert all(state[d] is False for d in cal[:10])  # no index row: off
    assert all(state[d] is True for d in dates[200:])  # close > SMA200
    assert state[dates[198]] is False  # 199 rows: SMA200 not yet formed
    assert state[dates[199]] is True   # exactly 200 rows: SMA available
    # exposures: R8 levels E_ON=0.90 / e_low=0.40 sampled at month ends
    expo = r16.t200_month_end_exposures(index_close, cal, [cal[0], cal[-1]])
    assert expo[cal[0]] == 0.40 and expo[cal[-1]] == 0.90


def test_t200_behavioral_anchor_matches_r8_published_stats() -> None:
    """Synthetic-index smoke of the anchor mechanism: the checker must raise
    when the reproduced stats differ from the published dict."""
    dates = weekday_sessions(1300)
    index_close = pl.DataFrame(
        {'trade_date': dates,
         'close': [100.0 + (i % 300) for i in range(1300)]})
    saved = dict(r16.T200_BEHAVIORAL_ANCHOR)
    # garbage published values -> mismatch -> hard failure
    r16.T200_BEHAVIORAL_ANCHOR = {
        y: {'n_sessions': 1, 'n_switches': 0, 'off_share': 0.0,
            'mean_exposure': 1.0} for y in saved}
    try:
        with pytest.raises(RuntimeError, match='behavioral anchor'):
            r16.t200_behavioral_anchor_check(index_close, dates)
    finally:
        r16.T200_BEHAVIORAL_ANCHOR = saved
    # sanity: running the checker against ITS OWN reproduced stats passes
    states = r16.t200_state(index_close, dates)
    sess = [d for d in dates
            if date(2016, 1, 1) <= d <= date(2020, 12, 31)]
    reproduced = r16.switch_stats(sess, states)
    r16.T200_BEHAVIORAL_ANCHOR = {
        y: v for y, v in reproduced.items() if y in saved}
    try:
        out = r16.t200_behavioral_anchor_check(index_close, dates)
        assert out['all_match'] is True
    finally:
        r16.T200_BEHAVIORAL_ANCHOR = saved


# --------------------------------------------------------------------------- #
# 2. H-47 buffer band state machine (entry/exit boundaries)
# --------------------------------------------------------------------------- #
RANKED = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']  # ranks 1..8


def test_buffer_band_enter_at_K_stay_to_2K_exit_beyond() -> None:
    # K=3: enter only from ranks 1..3, leave only beyond rank 6
    members, info = r16.buffer_membership(['D', 'E', 'F'], RANKED, {}, 3,
                                          False)
    assert members == ['D', 'E', 'F']  # ranks 4,5,6 all inside the band
    assert info['n_entrants'] == 0 and info['n_cash_seats'] == 0
    members, _ = r16.buffer_membership(['E', 'F', 'G'], RANKED, {}, 3,
                                       False)
    assert members == ['E', 'F', 'A']  # rank 7 leaves; A fills the seat
    members, info = r16.buffer_membership([], RANKED, {}, 3, False)
    assert members == ['A', 'B', 'C']  # fresh: top K


def test_buffer_band_seat_priority_and_q5_entry_filter() -> None:
    # filter-on: Q5 names are skipped for ENTRIES but never force out members
    members, info = r16.buffer_membership([], RANKED, {'A': True, 'B': True},
                                          3, True)
    # strict reading: entrants must come from the RAW top K (ranks 1..3);
    # with A,B flagged only C qualifies -> the other 2 seats stay cash
    assert members == ['C']
    assert info['n_cash_seats'] == 2
    # incumbents at rank <=2K stay even when Q5-flagged
    members, _ = r16.buffer_membership(['B'], RANKED, {'B': True}, 3, True)
    assert members[0] == 'B'
    # kept incumbents occupy seats; the remaining top-K non-Q5 names fill
    members, info = r16.buffer_membership(['D'], RANKED, {'A': True}, 3,
                                          True)
    assert members == ['D', 'B', 'C']


def test_buffer_band_leaver_order_deterministic() -> None:
    members, info = r16.buffer_membership(['G', 'H'], RANKED, {}, 3, False)
    assert info['n_left'] == 2 and info['n_kept'] == 0
    assert members == ['A', 'B', 'C']


def test_full_rebalance_membership_ignores_state() -> None:
    members, info = r16.full_rebalance_membership(['X'], RANKED, {}, 3,
                                                  False)
    assert members == ['A', 'B', 'C'] and info['n_prev'] == 1


def test_random_membership_seed_deterministic() -> None:
    import random
    r1 = r16.random_membership([], RANKED, {}, random.Random(17), 4)
    r2 = r16.random_membership([], RANKED, {}, random.Random(17), 4)
    r3 = r16.random_membership([], RANKED, {}, random.Random(18), 4)
    assert r1[0] == r2[0]  # same seed -> identical draw
    assert len(r1[0]) == 4 and set(r1[0]) <= set(RANKED)
    assert r3[0] != r1[0]  # different seed -> different draw (fixed seeds)


# --------------------------------------------------------------------------- #
# 3. month-end sessions + freeze boundary
# --------------------------------------------------------------------------- #
def test_month_end_sessions_last_traded_day_of_month() -> None:
    dates = weekday_sessions(60)  # spans ~3 months
    cal = cal_frame(dates)
    me = r16.month_end_sessions(cal)
    by_month = {str(m): s for m, s in zip(me['month'].to_list(),
                                          me['s'].to_list())}
    for d in dates:
        key = str(date(d.year, d.month, 1))
        if key in by_month:
            assert by_month[key] >= d


def test_build_history_freeze_boundary_zero_touch(tmp_path) -> None:
    dates = weekday_sessions(30)
    rows = {'sh.600000': constant_rows(dates)}
    rows['sh.600000'].append({'date': date(2025, 1, 2), 'open': 10.0,
                              'close': 10.0, 'preclose': 10.0,
                              'amount': 1.0e8, 'turn': 1.0, 'isST': 0.0,
                              'tradestatus': 1.0})
    p = tmp_path / 'daily.parquet'
    raw_daily_frame(rows).write_parquet(p)
    hist = r16.build_history_r16(p, cal_frame(dates))
    assert hist['date'].max() <= date(2024, 12, 31)


# --------------------------------------------------------------------------- #
# 4. Q5 double-high composite rank construction
# --------------------------------------------------------------------------- #
def test_q5_top_decile_of_composite_vol_turn_rank(tmp_path) -> None:
    dates = weekday_sessions(150)
    paths = {
        'sh.600001': constant_rows(dates, amount=2.0e8, turn=1.0),
        # wiggly + high-turnover name: must be q5-flagged
        'sh.600002': [{'date': d, 'open': 10.0,
                       'close': 10.0 + (2.0 if i % 2 else -2.0),
                       'preclose': 10.0, 'amount': 2.0e8, 'turn': 9.0,
                       'isST': 0.0, 'tradestatus': 1.0}
                      for i, d in enumerate(dates)],
        'sh.600003': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600004': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600005': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600006': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600007': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600008': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600009': constant_rows(dates, amount=2.0e8, turn=1.0),
        'sh.600010': constant_rows(dates, amount=2.0e8, turn=1.0),
    }
    p = tmp_path / 'daily.parquet'
    raw_daily_frame(paths).write_parquet(p)
    hist = r16.build_history_r16(p, cal_frame(dates))
    sig = pl.DataFrame({'s': [dates[-1]]})
    pool = r16.signal_pools(hist, sig)
    assert pool.height == 10
    flagged = pool.filter(pl.col('q5'))['symbol'].to_list()
    assert flagged == ['sh.600002']  # the only double-high name


def test_q5_uncomputable_names_are_not_classified(tmp_path) -> None:
    # a young name (<20 sessions) has null vol20/turn20 -> not flagged
    dates = weekday_sessions(150)
    young = constant_rows(dates[-15:])
    paths = {'sh.600001': constant_rows(dates),
             'sh.600002': young}
    p = tmp_path / 'daily.parquet'
    raw_daily_frame(paths).write_parquet(p)
    hist = r16.build_history_r16(p, cal_frame(dates))
    sig = pl.DataFrame({'s': [dates[-1]]})
    pool = r16.signal_pools(hist, sig)
    # the young name fails listing>120 and is out of the pool entirely
    assert 'sh.600002' not in pool['symbol'].to_list()


# --------------------------------------------------------------------------- #
# 5. engine: lots, cash conservation, chain accounting, blocks, seeds
# --------------------------------------------------------------------------- #
def _engine_world(n_sessions: int = 40):
    dates = weekday_sessions(n_sessions)
    paths = {
        'sh.600000': constant_rows(dates),
        'sh.600001': constant_rows(dates),
        'sh.600002': constant_rows(dates),
        'sh.600003': constant_rows(dates),
    }
    bank = make_bank(paths, dates)
    return dates, bank


def test_engine_lots_cash_conservation_and_chain_accounting() -> None:
    dates, bank = _engine_world()
    signals = [dates[9], dates[19], dates[29]]
    pools = flat_pools({s: ['sh.600000', 'sh.600001'] for s in signals})
    exposures = {s: 0.90 for s in signals}
    res = r16.simulate_r16(
        'T', bank, dates, dates[0], signals, pools, exposures, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.full_rebalance_membership(prev, ranked, q5, 2, False))
    # every buy is in whole lots and cash never goes negative
    buys = [t for t in res.trades if t['side'] == 'buy']
    assert buys and all(t['shares'] % 100 == 0 for t in buys)
    assert res.min_cash >= 0.0
    # fee = max(cost x 1e-4, 5): 90k leg -> 9.0 CNY
    assert all(abs(t['fee'] - t['notional'] * 0.0001) < 1e-9
               for t in buys)
    # equity = cash + chain marks at flat prices: only the tiny fee drag
    for probe in (10, 15, 39):
        eq = res.equity[probe]
        assert eq <= 200_000.0 + 1e-6
        assert abs(eq - 200_000.0) < 200.0
    assert res.planned_legs == res.executed_legs  # nothing left pending


def test_engine_limit_blocks_postpone_then_fill() -> None:
    dates, bank = _engine_world(n_sessions=30)
    # exec day = dates[10]: sh.600000 opens +10% (limit-up proxy) -> blocked
    opens_a = [10.0] * 30
    opens_a[10] = 11.0   # +10% vs preclose 10
    closes_a = [10.0] * 30
    closes_a[10] = 10.5  # settles back within the band
    paths = {
        'sh.600000': [{'date': d, 'open': opens_a[i], 'close': closes_a[i],
                       'preclose': 10.0 if i == 0 else closes_a[i - 1],
                       'amount': 1.0e8, 'turn': 1.0, 'isST': 0.0,
                       'tradestatus': 1.0} for i, d in enumerate(dates)],
        'sh.600001': constant_rows(dates),
    }
    b2 = r16.PriceBank(chain_columns(raw_daily_frame(paths)), dates,
                       sorted(paths))
    signals = [dates[9], dates[19]]
    pools = flat_pools({s: ['sh.600000', 'sh.600001'] for s in signals})
    res = r16.simulate_r16(
        'T', b2, dates, dates[0], signals, pools,
        {s: 0.90 for s in signals}, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.full_rebalance_membership(prev, ranked, q5, 2, False))
    buy_a = [t for t in res.trades if t['side'] == 'buy'
             and t['symbol'] == 'sh.600000']
    assert buy_a and buy_a[0]['session'] == dates[11]  # postponed a day
    leg_a = [r for r in res.leg_log if r['symbol'] == 'sh.600000'
             and r['kind'] == 'buy_open'][0]
    assert leg_a['outcome'] == 'postponed_then_filled'


def test_engine_sell_blocked_by_limit_down_postpones() -> None:
    dates, bank = _engine_world(n_sessions=30)
    # month 1: buy sh.600000 at dates[10]; month 2 it leaves the pool and
    # opens -10% (limit-down proxy) on dates[20] -> the exit postpones
    closes_a = [10.0] * 30
    opens_a = [10.0] * 30
    opens_a[20] = 9.0    # -10% vs preclose 10
    closes_a[20] = 9.2
    closes_a[21:] = [9.2] * 9
    opens_a[21:] = [9.2] * 9
    paths = {
        'sh.600000': [{'date': d, 'open': opens_a[i], 'close': closes_a[i],
                       'preclose': 10.0 if i == 0 else closes_a[i - 1],
                       'amount': 1.0e8, 'turn': 1.0, 'isST': 0.0,
                       'tradestatus': 1.0} for i, d in enumerate(dates)],
        'sh.600001': constant_rows(dates),
    }
    b2 = r16.PriceBank(chain_columns(raw_daily_frame(paths)), dates,
                       sorted(paths))
    signals = [dates[9], dates[19]]
    pools = {signals[0]: {'ranked': ['sh.600000'], 'q5': {}, 'n': 1},
             signals[1]: {'ranked': ['sh.600001'], 'q5': {}, 'n': 1}}
    res = r16.simulate_r16(
        'T', b2, dates, dates[0], signals, pools,
        {s: 0.90 for s in signals}, K=1,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.full_rebalance_membership(prev, ranked, q5, 1, False))
    sell_a = [t for t in res.trades if t['side'] == 'sell'
              and t['symbol'] == 'sh.600000']
    assert sell_a and sell_a[0]['session'] == dates[21]
    leg = [r for r in res.leg_log if r['symbol'] == 'sh.600000'
           and r['kind'] == 'sell_full'][0]
    assert leg['outcome'] == 'postponed_then_filled'


def test_engine_force_exit_when_quotes_end() -> None:
    dates, bank = _engine_world(n_sessions=30)
    # sh.600000 quotes end after dates[24]: held into month 2 -> force-exit
    paths = {
        'sh.600000': constant_rows(dates[:25]),
        'sh.600001': constant_rows(dates),
    }
    b2 = r16.PriceBank(chain_columns(raw_daily_frame(paths)), dates,
                       sorted(paths))
    signals = [dates[9], dates[19]]
    pools = flat_pools({s: ['sh.600000', 'sh.600001'] for s in signals})
    res = r16.simulate_r16(
        'T', b2, dates, dates[0], signals, pools,
        {s: 0.90 for s in signals}, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.full_rebalance_membership(prev, ranked, q5, 2, False))
    force = [t for t in res.trades
             if t['kind'] == 'forced_delist_close']
    assert force and force[0]['session'] == dates[24]
    assert force[0]['symbol'] == 'sh.600000'
    # the position book closes it with the fee split recorded
    pos = [p for p in res.positions
           if p.get('exit_kind') == 'forced_delist_close']
    assert pos and pos[0]['symbol'] == 'sh.600000'


def test_engine_supersede_counts_not_executed() -> None:
    dates, bank = _engine_world(n_sessions=40)
    # sh.600000's quotes end at dates[15]; the month-2 pool lists it (hand
    # built), so its buy can never fill; the month-3 signal supersedes it
    paths = {
        'sh.600000': constant_rows(dates[:16]),
        'sh.600001': constant_rows(dates),
        'sh.600002': constant_rows(dates),
    }
    b2 = r16.PriceBank(chain_columns(raw_daily_frame(paths)), dates,
                       sorted(paths))
    signals = [dates[9], dates[19], dates[29]]
    pools = {
        signals[0]: {'ranked': ['sh.600001'], 'q5': {}, 'n': 1},
        signals[1]: {'ranked': ['sh.600000', 'sh.600001'], 'q5': {}, 'n': 2},
        signals[2]: {'ranked': ['sh.600001', 'sh.600002'], 'q5': {}, 'n': 2},
    }
    res = r16.simulate_r16(
        'T', b2, dates, dates[0], signals, pools,
        {s: 0.90 for s in signals}, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.full_rebalance_membership(prev, ranked, q5, 2, False))
    superseded = [r for r in res.leg_log if r['outcome'] == 'superseded']
    assert any(r['symbol'] == 'sh.600000' for r in superseded)


def test_engine_b3_seed_reproducibility() -> None:
    dates, bank = _engine_world(n_sessions=40)
    signals = [dates[9], dates[19], dates[29]]
    pools = flat_pools({s: ['sh.600000', 'sh.600001', 'sh.600002',
                            'sh.600003'] for s in signals})
    exposures = {s: 0.75 for s in signals}
    r1 = r16.simulate_r16('a', bank, dates, dates[0], signals, pools,
                          exposures, K=2, seed=17,
                          membership_fn=lambda prev, ranked, q5, rng:
                              r16.random_membership(prev, ranked, q5, rng, 2))
    r2 = r16.simulate_r16('b', bank, dates, dates[0], signals, pools,
                          exposures, K=2, seed=17,
                          membership_fn=lambda prev, ranked, q5, rng:
                              r16.random_membership(prev, ranked, q5, rng, 2))
    r3 = r16.simulate_r16('c', bank, dates, dates[0], signals, pools,
                          exposures, K=2, seed=18,
                          membership_fn=lambda prev, ranked, q5, rng:
                              r16.random_membership(prev, ranked, q5, rng, 2))
    assert r1.equity == r2.equity
    assert r1.equity != r3.equity or r1.membership_events != \
        r3.membership_events


def test_engine_ex_dividend_value_continuity() -> None:
    dates, bank = _engine_world(n_sessions=30)
    # sh.600000 goes ex-div 1 CNY at dates[15]: the PUBLISHED preclose is
    # adjusted to 9 and the price series continues at 9 (bridge r = 1.0)
    rows = []
    for i, d in enumerate(dates):
        px = 10.0 if i < 15 else 9.0
        pc = 10.0 if i < 15 else 9.0
        if i == 15:
            pc = 9.0  # adjusted preclose on the ex-div session
        rows.append({'date': d, 'open': px, 'close': px,
                     'preclose': pc, 'amount': 1.0e8, 'turn': 1.0,
                     'isST': 0.0, 'tradestatus': 1.0})
    paths = {'sh.600000': rows, 'sh.600001': constant_rows(dates)}
    b2 = r16.PriceBank(chain_columns(raw_daily_frame(paths)), dates,
                       sorted(paths))
    signals = [dates[9], dates[19]]
    pools = flat_pools({s: ['sh.600000', 'sh.600001'] for s in signals})
    res = r16.simulate_r16(
        'T', b2, dates, dates[0], signals, pools,
        {s: 0.90 for s in signals}, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.full_rebalance_membership(prev, ranked, q5, 2, False))
    eq_before = res.equity[dates.index(dates[14])]
    eq_after = res.equity[dates.index(dates[15])]
    # the chain-unit mark keeps the ex-div value continuous (the dividend
    # stays in the position value, repo bridge convention)
    assert abs(eq_after - eq_before) < 1e-6
    # and a later month rescale-sell reveals the corp-action raw count:
    # 9000 units at kappa=10 = 90,000 CNY -> 10,000 raw shares at 9 CNY;
    # rescale to ~0.9x trims 100 shares (900 CNY) - the split flows through
    sell = [t for t in res.trades if t['side'] == 'sell'
            and t['symbol'] == 'sh.600000']
    assert sell and sell[0]['shares'] == 100 \
        and sell[0]['raw_price'] == 9.0 \
        and sell[0]['notional'] == pytest.approx(900.0, rel=1e-9)


def test_engine_membership_turnover_books() -> None:
    dates, bank = _engine_world(n_sessions=40)
    signals = [dates[9], dates[19]]
    pools = {signals[0]: {'ranked': ['sh.600000', 'sh.600001'], 'q5': {},
                          'n': 2},
             signals[1]: {'ranked': ['sh.600000', 'sh.600002'], 'q5': {},
                          'n': 2}}
    res = r16.simulate_r16(
        'T', bank, dates, dates[0], signals, pools,
        {s: 0.75 for s in signals}, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.buffer_membership(prev, ranked, q5, 2, False))
    year = dates[9].year
    mt = res.membership_turnover[year]
    # one leaver exit (600001) + one entrant buy (600002) at month 2
    assert mt['sell_notional'] > 0 and mt['buy_notional'] > 0


def test_buffer_band_inside_engine_keeps_incumbents() -> None:
    dates, bank = _engine_world(n_sessions=40)
    signals = [dates[9], dates[19]]
    pools = {signals[0]: {'ranked': ['sh.600000', 'sh.600001', 'sh.600002',
                                     'sh.600003'], 'q5': {}, 'n': 4},
             signals[1]: {'ranked': ['sh.600002', 'sh.600003', 'sh.600000',
                                     'sh.600001'], 'q5': {}, 'n': 4}}
    res = r16.simulate_r16(
        'T', bank, dates, dates[0], signals, pools,
        {s: 0.90 for s in signals}, K=2,
        membership_fn=lambda prev, ranked, q5, rng:
            r16.buffer_membership(prev, ranked, q5, 2, False))
    ev = res.membership_events
    assert ev[0]['n_entrants'] == 2
    # month 2: incumbents at ranks 3,4 (inside 2K=4) are KEPT - no trades
    assert ev[1]['n_kept'] == 2 and ev[1]['n_entrants'] == 0
    buys_m2 = [t for t in res.trades if t['session'] > dates[19]
               and t['side'] == 'buy']
    assert not buys_m2


# --------------------------------------------------------------------------- #
# 6. fee segmentation (stamp cut)
# --------------------------------------------------------------------------- #
def test_sell_fee_stamp_segmentation() -> None:
    band_old = r16._fee_band(date(2023, 8, 27), r16.STOCK_FEE_SCHEDULE)
    band_new = r16._fee_band(date(2023, 8, 28), r16.STOCK_FEE_SCHEDULE)
    assert band_old.stamp_sell_pct == 0.001
    assert band_new.stamp_sell_pct == 0.0005
    notional = 9_000.0
    assert abs(r16._sell_fee(notional, band_old)
               - (max(notional * 0.0001, 5.0) + notional * 0.001)) < 1e-9
    assert abs(r16._sell_fee(notional, band_new)
               - (max(notional * 0.0001, 5.0) + notional * 0.0005)) < 1e-9


# --------------------------------------------------------------------------- #
# 7. gates
# --------------------------------------------------------------------------- #
def _mk_metrics(**over) -> dict:
    base = {
        'net_cagr': 0.10, 'excess_vs_b1m': 0.03,
        'excess_by_year': {str(y): 0.01 for y in range(2015, 2021)},
        'max_drawdown': -0.15, 'b1m_max_drawdown': -0.18,
        'max_one_side_turnover': 2.0, 'max_single_name_weight': 0.06,
        'execution_rate': 0.98,
    }
    base.update(over)
    return base


def test_dev_gate_eight_rules() -> None:
    g = r16.evaluate_dev_gates(_mk_metrics(), b3_mean=0.05)
    assert g['dev_pass'] and g['failed_gates'] == []
    assert g['mechanism_only_gate2_fail'] is False
    # gate 2 sole failure -> the registered double-valued condition fires
    g = r16.evaluate_dev_gates(_mk_metrics(excess_vs_b1m=0.005,
                                           excess_by_year={
                                               str(y): 0.001
                                               for y in range(2015, 2021)}),
                               b3_mean=0.05)
    assert g['failed_gates'] == ['2_excess_vs_B1m_ge_2pp']
    assert g['mechanism_only_gate2_fail'] is True
    # mdd deeper than B1(m) fails gate 4
    g = r16.evaluate_dev_gates(_mk_metrics(max_drawdown=-0.25), None)
    assert '4_mdd_le_20pct_and_le_B1m' in g['failed_gates']
    # turnover above 6.0 fails gate 5
    g = r16.evaluate_dev_gates(_mk_metrics(max_one_side_turnover=6.5), None)
    assert '5_one_side_turnover_le_6' in g['failed_gates']
    # weight above 40% fails gate 6
    g = r16.evaluate_dev_gates(_mk_metrics(max_single_name_weight=0.41),
                               None)
    assert '6_single_name_weight_le_40pct' in g['failed_gates']
    # execution rate below 95% fails gate 8
    g = r16.evaluate_dev_gates(_mk_metrics(execution_rate=0.94), None)
    assert '8_execution_rate_ge_95pct' in g['failed_gates']
    # below B3'+1pp fails gate 7
    g = r16.evaluate_dev_gates(_mk_metrics(net_cagr=0.055), b3_mean=0.05)
    assert '7_vs_B3prime_plus_1pp' in g['failed_gates']
    # fewer than 5/6 advantage years fails gate 3
    m = _mk_metrics()
    m['excess_by_year'] = {str(y): (0.01 if y < 2019 else -0.02)
                           for y in range(2015, 2021)}
    g = r16.evaluate_dev_gates(m, None)
    assert '3_advantage_years_ge_5_of_6' in g['failed_gates']


def test_val_gate_three_rules() -> None:
    m = {'net_cagr': 0.08, 'excess_vs_b1m': 0.02,
         'excess_by_year': {str(y): 0.005 for y in range(2021, 2025)},
         'max_drawdown': -0.12, 'b1m_max_drawdown': -0.16}
    g = r16.evaluate_val_gates(m)
    assert g['val_pass']
    m['max_drawdown'] = -0.25
    g = r16.evaluate_val_gates(m)
    assert not g['val_pass']
    assert '3_mdd_le_20pct_and_le_B1m' in g['failed_gates']


def test_window_execution_rate_counts_registered_outcomes() -> None:
    log = [
        {'plan_date': date(2015, 2, 1), 'outcome': 'filled'},
        {'plan_date': date(2015, 3, 1), 'outcome': 'postponed_then_filled'},
        {'plan_date': date(2015, 4, 1), 'outcome': 'superseded'},
        {'plan_date': date(2015, 5, 1), 'outcome': 'no_lots'},
        {'plan_date': date(2015, 6, 1), 'outcome': 'pending_at_end'},
    ]
    out = r16.window_execution_rate(log, date(2015, 1, 1), date(2015, 12, 31))
    assert out['legs_planned'] == 5
    assert out['legs_executed'] == 3
    assert abs(out['execution_rate'] - 0.6) < 1e-12


def test_exposures_fix75_constant() -> None:
    days = weekday_sessions(5)
    assert r16.fix75_exposures(days) == {d: 0.75 for d in days}
