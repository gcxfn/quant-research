"""Unit tests for the P2-R11 half-day combination (exp-20260918-p2r11).

Coverage required by the prereg: cash conservation (per-day
cash + holdings = equity), lot rounding, T+1, replacement budget,
limit-up buy block / limit-down sell postponement, circuit-breaker day,
corporate-action bridge (exact hand math; no-event day adj == 1),
segmented fees, seed determinism, freeze boundary (no 2025+ path),
and the M-1-safe shift-inside-over pattern for R11's own rolling gate.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from datetime import date

from quant.research.p2r11_halfday_combo import (
    CAPITAL,
    MarketArrays,
    _commission,
    add_composite,
    amount_median_20d,
    evaluate_dev_gates,
    evaluate_window_gates,
    random_score_array,
    run_portfolio,
    seasoned_listing_gate,
    window_metrics,
)


# --------------------------------------------------------------------------- #
# helpers: hand-built market arrays
# --------------------------------------------------------------------------- #
def _mkt(dates_rows: dict, breaker=(), score=None) -> MarketArrays:
    """dates_rows: {date: {sym: {col: val}}}; a missing symbol row means
    the symbol does not trade that day (no row at all)."""
    dates = sorted(dates_rows)
    syms = sorted({s for rows in dates_rows.values() for s in rows})
    s_pos = {s: i for i, s in enumerate(syms)}
    d_pos = {d: i for i, d in enumerate(dates)}
    cols = {k: [] for k in ('open_1300', 'close_1130', 'close_day',
                            'limit_up', 'limit_down', 'open_0925',
                            'preclose_ref', 'boundary_adj')}
    di, si, sc = [], [], []
    for d in dates:
        for s in syms:
            row = dates_rows[d].get(s)
            if row is None:
                continue
            di.append(d_pos[d])
            si.append(s_pos[s])
            sc.append((score or {}).get((d, s), np.nan))
            for k in cols:
                cols[k].append(row.get(k, np.nan))
    return MarketArrays(
        dates=dates, sym_names=syms,
        date_idx=np.array(di, dtype=np.int64),
        sym_idx=np.array(si, dtype=np.int64),
        score=np.array(sc, dtype=np.float64),
        breaker=np.array([d in set(breaker) for d in dates], dtype=bool),
        **{k: np.array(v, dtype=np.float64) for k, v in cols.items()})


def _day(o13=10.0, c1130=10.0, cday=10.0, lu=12.0, ld=8.0, o925=10.0,
         pre=None, adj=np.nan):
    return {'open_1300': o13, 'close_1130': c1130, 'close_day': cday,
            'limit_up': lu, 'limit_down': ld, 'open_0925': o925,
            'preclose_ref': pre if pre is not None else cday,
            'boundary_adj': adj}


D0, D1, D2 = date(2016, 6, 1), date(2016, 6, 2), date(2016, 6, 3)


def _flat_abc(**score_extra) -> dict:
    rows = {D0: {s: _day() for s in 'ABC'},
            D1: {s: _day() for s in 'ABC'},
            D2: {s: _day() for s in 'ABC'}}
    score = {(D0, 'A'): 2.0, (D0, 'B'): 1.0, (D0, 'C'): 0.5}
    return rows, {**score, **score_extra}


# --------------------------------------------------------------------------- #
# 1. cash conservation, lot, T+1, segmented fees (hand numbers)
# --------------------------------------------------------------------------- #
def test_c01_hand_scenario_cash_conservation_lot_t1_fees():
    rows, score = _flat_abc()
    res = run_portfolio(_mkt(rows, score=score), K=3, schedule='S_1130')
    # day 0: three lots of 5000 sh @10 -> 50000 each; commission exactly
    # max(50000*0.0001, 5) = 5 (minimum binds at parity)
    assert [t['shares'] for t in res.trades] == [5000.0] * 3
    assert all(t['buy_fee'] == pytest.approx(5.0) for t in res.trades)
    assert all(t['sell_day'] == 1 for t in res.trades)          # T+1
    cash0 = CAPITAL - 3 * (50000.0 + 5.0)
    assert res.equity[0] == pytest.approx(cash0 + 15000 * 10.0)
    # day 1: sell @close_1130=10: proceeds 150000, stamp 0.001 -> 150,
    # commission 15; nothing held afterwards -> equity == cash
    expected_cash1 = cash0 + 150000.0 - 150.0 - 15.0
    assert res.cash_final == pytest.approx(expected_cash1)
    assert res.equity[1] == pytest.approx(expected_cash1)
    assert res.equity[2] == pytest.approx(expected_cash1)
    bought = sum(t['shares'] * t['buy_price'] + t['buy_fee']
                 for t in res.trades)
    sold = sum(t['shares'] * t['sell_price'] - t['sell_fee']
               for t in res.trades)
    assert CAPITAL - bought + sold == pytest.approx(res.cash_final)
    assert res.open_positions == 0


def test_stamp_segmentation_2023_08_28_in_engine():
    rows = {date(2023, 8, 25): {s: _day() for s in 'AB'},
            date(2023, 8, 28): {s: _day() for s in 'AB'}}
    score = {(date(2023, 8, 25), 'A'): 1.0, (date(2023, 8, 25), 'B'): 0.5}
    res = run_portfolio(_mkt(rows, score=score), K=2, schedule='S_1130')
    # sell date 2023-08-28 -> stamp 0.0005: per name 5000 sh @10 = 50k
    # proceeds, stamp 25, commission max(5,5)=5
    for t in res.trades:
        assert t['sell_fee'] == pytest.approx(5.0 + 25.0)


def test_commission_minimum_binds_on_small_lots():
    assert _commission(1000.0) == pytest.approx(5.0)
    assert _commission(50_000.0) == pytest.approx(5.0)
    assert _commission(200_000.0) == pytest.approx(20.0)


def test_lot_never_exceeds_target_and_cash_stays_positive():
    # price 300: target 50000 affords exactly one lot (30000 <= 50000);
    # price 7: 71 lots of 100 within 50000.
    rows = {D0: {'A': _day(o13=300.0, lu=400.0, ld=250.0),
                 'B': _day(o13=7.0)},
            D1: {s: _day() for s in 'AB'}}
    score = {(D0, 'A'): 2.0, (D0, 'B'): 1.0}
    res = run_portfolio(_mkt(rows, score=score), K=2, schedule='S_1130')
    by_sym = {t['sym']: t for t in res.trades}
    assert by_sym[0]['shares'] == 100.0          # floor(50000/300/100)*100
    assert by_sym[1]['shares'] == 7100.0         # floor(50000/7/100)*100
    assert res.cash_final > 0


# --------------------------------------------------------------------------- #
# 2. replacement budget, limit-up block
# --------------------------------------------------------------------------- #
def test_replacement_skips_limit_up_within_budget_of_two():
    rows = {D0: {'A': _day(o13=11.0, lu=11.0),   # at limit-up: blocked
                 'B': _day(o13=12.0, lu=12.0),   # at limit-up: blocked
                 'C': _day()},
            D1: {s: _day() for s in 'ABC'}}
    score = {(D0, 'A'): 3.0, (D0, 'B'): 2.0, (D0, 'C'): 1.0}
    res = run_portfolio(_mkt(rows, score=score), K=1, schedule='S_1130')
    buys = [a for a in res.attempts if a['kind'] == 'buy']
    assert [a['sym'] for a in buys] == [0, 1, 2]      # A, B skipped; C taken
    assert [a['success'] for a in buys] == [False, False, True]
    assert any(t['sym'] == 2 for t in res.trades)


def test_replacement_budget_exhausted_slot_stays_empty():
    rows = {D0: {s: _day(o13=11.0, lu=11.0) for s in 'ABC'},
            D1: {s: _day() for s in 'ABC'}}
    score = {(D0, s): 1.0 - i for i, s in enumerate('ABC')}
    res = run_portfolio(_mkt(rows, score=score), K=1, schedule='S_1130')
    buys = [a for a in res.attempts if a['kind'] == 'buy']
    assert len(buys) == 3 and not any(a['success'] for a in buys)
    assert res.open_positions == 0
    assert res.equity[0] == pytest.approx(CAPITAL)    # cash idles


def test_one_slot_budget_fresh_per_second_slot():
    # K=2, four blocked candidates: slot 1 consumes A,B,C (initial + 2
    # backups) and stays empty; slot 2 starts fresh and attempts D.
    rows = {D0: {s: _day(o13=11.0, lu=11.0) for s in 'ABCD'},
            D1: {s: _day() for s in 'ABCD'}}
    score = {(D0, s): 1.0 - i for i, s in enumerate('ABCD')}
    res = run_portfolio(_mkt(rows, score=score), K=2, schedule='S_1130')
    buys = [a for a in res.attempts if a['kind'] == 'buy']
    assert [a['sym'] for a in buys] == [0, 1, 2, 3]
    assert res.open_positions == 0


# --------------------------------------------------------------------------- #
# 3. sell postponement: limit-down, suspension, breaker day
# --------------------------------------------------------------------------- #
def test_limit_down_sell_postpones_and_counts_failure():
    rows = {D0: {'A': _day()},
            D1: {'A': _day(c1130=9.0, ld=9.0)},     # sell point at limit-down
            D2: {'A': _day(c1130=9.5, ld=8.0)}}
    score = {(D0, 'A'): 1.0}
    res = run_portfolio(_mkt(rows, score=score), K=1, schedule='S_1130')
    sells = [a for a in res.attempts if a['kind'] == 'sell']
    assert [a['success'] for a in sells] == [False, True]
    sold = [t for t in res.trades if t['sell_day'] is not None][0]
    assert sold['sell_day'] == 2


def test_suspended_sell_day_missing_row_postpones():
    rows = {D0: {'A': _day()},
            D1: {},                                  # A suspended: no row
            D2: {'A': _day(c1130=10.2)}}
    score = {(D0, 'A'): 1.0}
    res = run_portfolio(_mkt(rows, score=score), K=1, schedule='S_1130')
    sells = [a for a in res.attempts if a['kind'] == 'sell']
    assert [a['success'] for a in sells] == [False, True]
    sold = [t for t in res.trades if t['sell_day'] is not None][0]
    assert sold['sell_day'] == 2
    assert res.equity[1] == pytest.approx(res.equity[0])   # carried mark


def test_breaker_day_1130_point_invalid_0925_valid():
    rows = {D0: {'A': _day()},
            D1: {'A': _day(c1130=10.4, o925=10.1)},
            D2: {'A': _day(c1130=10.6)}}
    score = {(D0, 'A'): 1.0, (D1, 'A'): 1.0}
    res = run_portfolio(_mkt(rows, breaker=(D1,), score=score),
                        K=1, schedule='S_1130')
    sells = [a for a in res.attempts if a['kind'] == 'sell']
    assert [a['success'] for a in sells] == [False, True]
    assert res.open_positions == 0
    buys = [a for a in res.attempts if a['kind'] == 'buy' and a['day'] == 1]
    assert buys == []                     # no 13:01 point -> no attempts

    res925 = run_portfolio(_mkt(rows, breaker=(D1,), score=score),
                           K=1, schedule='S_0925')
    sells925 = [a for a in res925.attempts if a['kind'] == 'sell']
    assert [a['success'] for a in sells925] == [True]
    sold = [t for t in res925.trades if t['sell_day'] is not None][0]
    assert sold['sell_day'] == 1
    assert sold['sell_price'] == pytest.approx(10.1)


# --------------------------------------------------------------------------- #
# 4. corporate-action bridge: boundary share adjustment (hand math)
# --------------------------------------------------------------------------- #
def test_ca_boundary_split_shares_adjust_value_preserved():
    # 2-for-1 split overnight D0 -> D1: prev close 10.5, preclose 5.25,
    # boundary adj = prev_close/preclose = 2.0 -> shares double, raw price
    # halves, value continuous.  Limit-down lowered with the split.
    rows = {D0: {'A': _day(cday=10.5)},
            D1: {'A': _day(pre=5.25, adj=2.0, c1130=5.4, cday=5.5,
                           ld=4.0)}}
    score = {(D0, 'A'): 1.0}
    res = run_portfolio(_mkt(rows, score=score), K=1, schedule='S_1130')
    bought = res.trades[0]
    sold = [t for t in res.trades if t['sell_day'] is not None][0]
    assert bought['buy_shares'] == pytest.approx(5000.0)   # floor(50k/10)
    assert sold['shares'] == pytest.approx(10000.0)        # doubled at split
    assert sold['sell_price'] == pytest.approx(5.4)
    assert (bought['buy_shares'] * 10.5
            == pytest.approx(sold['shares'] * 5.25))


def test_no_event_day_boundary_adj_exactly_one():
    daily = pl.DataFrame({
        'symbol': ['sz.000001'] * 3,
        'date': [D0, D1, D2],
        'close': [10.0, 10.1, 10.3],
        'preclose': [10.0, 10.0, 10.1],
    }).sort('symbol', 'date').with_columns(
        pl.col('close').shift(1).over('symbol').alias('prev'))
    adj = (daily['prev'] / daily['preclose']).to_list()
    assert adj[1] == pytest.approx(1.0)     # no event: preclose == prev
    assert adj[2] == pytest.approx(1.0)

    rows = {D0: {'A': _day(cday=10.0)},
            D1: {'A': _day(pre=10.0, adj=1.0, c1130=10.2)}}
    res = run_portfolio(_mkt(rows, score={(D0, 'A'): 1.0}),
                        K=1, schedule='S_1130')
    sold = [t for t in res.trades if t['sell_day'] is not None][0]
    assert sold['shares'] == res.trades[0]['shares']   # unchanged


# --------------------------------------------------------------------------- #
# 5. R11 rolling gate: M-1-safe pattern (shift inside over)
# --------------------------------------------------------------------------- #
def test_amount_median_20d_no_cross_symbol_leak(tmp_path):
    rows = []
    amounts = {'sh.600000': 100.0, 'sz.000001': 900.0}
    for sym in ('sh.600000', 'sz.000001'):
        for i in range(21):
            rows.append({'symbol': sym, 'date': date(2016, 6, 1 + i),
                         'tradestatus': 1.0,
                         'amount': amounts[sym] * (i + 1)})
    path = tmp_path / 'daily.parquet'
    pl.DataFrame(rows).write_parquet(path)
    med = amount_median_20d(path).sort('symbol', 'date')
    got: dict[str, list] = {}
    for r in med.iter_rows(named=True):
        got.setdefault(r['symbol'], []).append(r['amount_med20'])
    for sym in ('sh.600000', 'sz.000001'):
        assert all(v is None for v in got[sym][:20])   # warm-up: null
    assert got['sh.600000'][20] == pytest.approx(
        float(np.median([100.0 * (i + 1) for i in range(20)])))
    # the later symbol's first valid row must hold its OWN median, not the
    # earlier symbol's value (M-1 leak pattern)
    assert got['sz.000001'][20] == pytest.approx(
        float(np.median([900.0 * (i + 1) for i in range(20)])))


# --------------------------------------------------------------------------- #
# 6. composite scoring: direction flip, per-day standardization
# --------------------------------------------------------------------------- #
def test_composite_equal_z_direction_flip_high_score_is_buy_side():
    # F03/F06/F09/F11 all direction -1: LOW raw factor -> HIGH score.
    rows = [{'symbol': f'sz.{i:06d}', 'date': D0,
             'F03': float(v), 'F06': float(v), 'F09': float(v),
             'F11': float(v)}
            for i, v in enumerate([1.0, 2.0, 3.0, 4.0])]
    out = add_composite(pl.DataFrame(rows), 'equal_z')
    by_f03 = out.sort('F03')['score'].to_list()
    assert by_f03[0] > by_f03[-1]           # lowest raw factor -> top score
    assert abs(np.mean(out['score'].to_list())) < 1e-12   # z symmetric


# --------------------------------------------------------------------------- #
# 7. seed determinism
# --------------------------------------------------------------------------- #
def test_random_scores_deterministic_per_seed():
    mask = np.array([True, True, True, False, False])
    a = random_score_array(None, mask, 17)
    b = random_score_array(None, mask, 17)
    c = random_score_array(None, mask, 18)
    assert np.array_equal(a, b, equal_nan=True)
    assert not np.array_equal(a, c, equal_nan=True)
    assert np.isnan(a[3:]).all() and np.isfinite(a[:3]).all()


# --------------------------------------------------------------------------- #
# 8. freeze boundary: R11 read layer drops 2025+ rows
# --------------------------------------------------------------------------- #
def test_freeze_read_layer_drops_2025():
    from quant.research.p2r11_halfday_combo import _freeze
    df = pl.DataFrame({
        'symbol': ['sz.000001'] * 3,
        'date': [date(2024, 12, 31), date(2025, 1, 1), date(2025, 6, 30)],
        'x': [1.0, 2.0, 3.0]})
    out = _freeze(df.lazy()).collect()
    assert out.height == 1
    assert out['date'][0] == date(2024, 12, 31)


# --------------------------------------------------------------------------- #
# 9. listing gate: seasoning exemption + 120-session boundary
# --------------------------------------------------------------------------- #
def test_seasoned_listing_gate(tmp_path):
    day0 = date(2024, 1, 2)
    base = ([day0]
            + [day0 + __import__('datetime').timedelta(days=i + 1)
               for i in range(121)]
            + [day0 + __import__('datetime').timedelta(days=i + 200)
               for i in range(120)])
    daily = pl.DataFrame({
        'symbol': (['sz.000001'] + ['sz.000002'] * 121
                   + ['sz.000003'] * 120),
        'date': base,
        'tradestatus': [1.0] * 242})
    path = tmp_path / 'd.parquet'
    daily.write_parquet(path)
    gate = seasoned_listing_gate(path)
    last = (gate.sort('date').group_by('symbol', maintain_order=True)
            .agg(pl.col('date').last(), pl.col('listing_ok').last()))
    got = {r['symbol']: r['listing_ok'] for r in last.to_dicts()}
    assert got['sz.000002'] is True       # 121st session: past 120
    assert got['sz.000003'] is False      # only 120 sessions: still new
    first = gate.filter(pl.col('symbol') == 'sz.000001')
    assert first['listing_ok'].to_list() == [True]   # file-first-day exempt


# --------------------------------------------------------------------------- #
# 10. metrics + gates logic
# --------------------------------------------------------------------------- #
def test_window_metrics_hand_path():
    dates = [date(2016, 1, i) for i in (2, 3, 4, 5)]
    eq = np.array([100.0, 110.0, 99.0, 121.0])
    m = window_metrics(dates, eq, np.zeros(4), np.zeros(4), [], [],
                       dates[0], dates[-1])
    assert m['net_cagr'] == pytest.approx((121.0 / 100.0) ** (244 / 4) - 1)
    assert m['max_dd'] == pytest.approx(1 - 99.0 / 110.0)
    assert m['yearly_net'][2016] == pytest.approx(0.21)


def _good_metrics():
    return {'net_cagr': 0.05, 'max_dd': 0.10, 'turnover_annual': 100.0,
            'max_weight': 0.35, 'fill_rate': 0.97,
            'yearly_net': {y: 0.06 for y in range(2015, 2021)}}


def test_dev_gates_all_pass_and_each_failure():
    b1 = {'net_cagr': 0.02, 'max_dd': 0.15,
          'yearly_net': {y: 0.03 for y in range(2015, 2021)}}
    g = evaluate_dev_gates(_good_metrics(), b1, b3_mean_cagr=0.03)
    assert g['all_pass'] and all(c['pass'] for c in g['cells'].values())

    def fails(mut):
        m = {**_good_metrics(), **mut}
        return not evaluate_dev_gates(m, b1, 0.03)['all_pass']

    assert fails({'net_cagr': -0.01})            # g1 cagr > 0
    assert fails({'net_cagr': 0.035})            # g2 excess 1.5pp < 2pp
    # g3: exactly 5/6 advantage years still passes; 4/6 fails
    m5 = {**_good_metrics(),
          'yearly_net': {y: (0.06 if y != 2015 else 0.02)
                         for y in range(2015, 2021)}}
    g5 = evaluate_dev_gates(m5, b1, 0.03)
    assert g5['cells'][3]['value'] == 5 and g5['all_pass']
    m4 = {**_good_metrics(),
          'yearly_net': {y: (0.06 if y not in (2015, 2016) else 0.01)
                         for y in range(2015, 2021)}}
    assert not evaluate_dev_gates(m4, b1, 0.03)['all_pass']
    assert fails({'max_dd': 0.21})               # g4 > 0.20
    mdd = {**_good_metrics(), 'max_dd': 0.16}    # <= 0.20 but > B1 0.15
    assert not evaluate_dev_gates(mdd, b1, 0.03)['all_pass']
    assert fails({'turnover_annual': 301.0})     # g5
    assert fails({'max_weight': 0.41})           # g6
    assert fails({'fill_rate': 0.9499})          # g8
    assert not evaluate_dev_gates(_good_metrics(), b1, 0.045)['all_pass']


def test_window_gates_val_boundaries():
    b1 = {'net_cagr': 0.02, 'max_dd': 0.15,
          'yearly_net': {2021: 0.01, 2022: 0.02}}
    m = {'net_cagr': 0.035, 'max_dd': 0.10,
         'yearly_net': {2021: 0.05, 2022: 0.03}}
    assert evaluate_window_gates(m, b1)['all_pass']   # +1.5pp, 2/2, dd ok
    m2 = {**m, 'net_cagr': 0.025}                     # +0.5pp < +1pp
    assert not evaluate_window_gates(m2, b1)['all_pass']
    m3 = {**m, 'yearly_net': {2021: 0.05, 2022: 0.015}}
    assert not evaluate_window_gates(m3, b1)['all_pass']   # 1/2 years
