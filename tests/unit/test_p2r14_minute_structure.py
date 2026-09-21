"""Unit tests for the P2-R14 minute structure round (preregistered).

Hand-crafted samples cover: feature extraction on three minute-day
samples (SH before / SH on / after the 2018-08-20 SH close-auction
regime break, plus SZ), zero-volume placeholder exclusion, limit-state
float32 tolerances (1e-4/2e-4), the shift-in-over rule for
first_bar_vol_med20 (no cross-symbol leakage), next-session T2
anchoring with suspension and the 2025+ structural zero-touch, the
union-of-buckets control rule, the diff gate, the residual-IC
machinery, the U5 use-gate math and the seed-17 sampler.
"""
from __future__ import annotations

import random
import statistics
from datetime import date

import numpy as np
import polars as pl
import pytest

from quant.research.p2r10_halfday import newey_west_t
from quant.research.p2r14_minute_structure import (
    SEED,
    attach_next_labels,
    control_mask_by_day,
    diff_gate,
    extract_day_features,
    finalize_feature_table,
    p5_improvement,
    pick_sample,
    residual_ic_series,
    use_gate_pass,
)


# --------------------------------------------------------------------------- #
# synthetic minute-day builder
# --------------------------------------------------------------------------- #
def _bar(code: str, d_iso: str, tod: str, close: float, opn: float,
         high: float, low: float, vol: float, amount: float) -> dict:
    return {
        'code': code, 'trade_time': f'{d_iso} {tod}',
        'close': np.float32(close), 'open': np.float32(opn),
        'high': np.float32(high), 'low': np.float32(low),
        'vol': np.float32(vol), 'amount': np.float32(amount),
        'date': d_iso.replace('-', ''), 'pre_close': np.float32(close),
        'change': np.float32(0.0), 'pct_chg': np.float32(0.0),
        '__index_level_0__': 0,
    }


def _write_day(rows: list[dict], tmp_path, name: str):
    fp = tmp_path / name
    pl.DataFrame(rows).write_parquet(fp)
    return fp


def _sample_bars_post(d_iso: str, code: str) -> list[dict]:
    """SH close-auction regime (>= 2018-08-20): quiet 14:57/14:59, big
    15:00 auction bar; one zero-volume phantom bar mid-day."""
    return [
        _bar(code, d_iso, '09:30:00', 10.00, 10.00, 10.00, 10.00,
             100_000, 1_000_000),
        _bar(code, d_iso, '09:31:00', 10.10, 10.00, 10.20, 9.95,
             50_000, 500_000),
        _bar(code, d_iso, '09:40:00', 9.95, 10.00, 10.10, 9.90,
             30_000, 300_000),
        _bar(code, d_iso, '10:00:00', 10.20, 10.10, 10.30, 10.00,
             40_000, 400_000),
        _bar(code, d_iso, '11:30:00', 10.00, 10.00, 10.05, 10.00,
             20_000, 200_000),
        _bar(code, d_iso, '13:01:00', 10.00, 10.00, 10.05, 9.98,
             20_000, 200_000),
        _bar(code, d_iso, '13:30:00', 10.00, 10.00, 12.00, 8.00,
             0, 0),  # placeholder: phantom extremes must be excluded
        _bar(code, d_iso, '14:30:00', 10.50, 10.45, 10.50, 10.40,
             25_000, 260_000),
        _bar(code, d_iso, '14:31:00', 10.52, 10.50, 10.55, 10.50,
             5_000, 52_000),
        _bar(code, d_iso, '14:45:00', 10.60, 10.55, 10.62, 10.55,
             10_000, 106_000),
        _bar(code, d_iso, '15:00:00', 10.80, 10.80, 10.80, 10.80,
             90_000, 972_000),
    ]


def _extract(tmp_path, rows: list[dict], d_iso: str, name: str):
    fp = _write_day(rows, tmp_path, name)
    return extract_day_features(fp, d_iso)


# --------------------------------------------------------------------------- #
# 1. three hand-crafted day samples (SH post / SH pre / SZ) + placeholders
# --------------------------------------------------------------------------- #
def test_hand_sample_sh_post_2018_08_20(tmp_path):
    d_iso = '2018-08-20'
    rows = _sample_bars_post(d_iso, '600000.SH')
    # a fully suspended symbol: every bar zero volume -> row dropped
    rows += [_bar('600123.SH', d_iso, t, 5.0, 5.0, 5.0, 5.0, 0, 0)
             for t in ('09:30:00', '10:00:00', '15:00:00')]
    # .BJ rows are dropped (counted), including after-hours
    rows += [_bar('899001.BJ', d_iso, '09:31:00', 1.0, 1.0, 1.0, 1.0,
                  10, 10),
             _bar('899001.BJ', d_iso, '15:30:00', 1.0, 1.0, 1.0, 1.0,
                  10, 10)]
    out, c = _extract(tmp_path, rows, d_iso, 'day_post.parquet')
    assert out.height == 1
    r = out.row(0, named=True)
    assert r['symbol'] == 'sh.600000'
    assert r['date'] == date(2018, 8, 20)
    # day range from volume-bearing bars only (phantom 12.00/8.00
    # excluded); the 15:00 auction bar high 10.80 is the day high
    assert r['day_high'] == 10.80 and r['day_low'] == 9.90
    # first 30 min range (10.30-9.90) over full-day range (10.80-9.90)
    assert r['am_range30'] == pytest.approx(0.40 / 0.90)
    # auction bar volume
    assert r['first_bar_vol'] == 100_000
    # last 30 min amount: 260k + 52k + 106k + 972k = 1,390k of 3,990k
    assert r['close_share30'] == pytest.approx(1_390_000 / 3_990_000)
    assert r['tail_amt_share'] == r['close_share30']
    # 15:00 close vs 14:30 close (close auction settle price on this arm)
    assert r['last30_ret'] == pytest.approx(10.80 / 10.50 - 1.0)
    assert c['rows_dropped_all_zerovol'] == 1
    assert c['zerovol_bars_removed'] == 4  # suspended 3 + phantom 1
    assert c['bj_rows_removed'] == 2
    assert c['bar_1300_rows_present'] == 0


def test_hand_sample_sh_pre_2018_08_20(tmp_path):
    """Before the SH close auction the 14:57-15:00 bars trade
    continuously; extraction is uniform and last30_ret still anchors on
    the 14:30 and 15:00 bars (segment semantics live in the judgment
    arms, not the features)."""
    d_iso = '2018-08-17'
    rows = _sample_bars_post(d_iso, '600000.SH')
    rows = [r for r in rows
            if not r['trade_time'].endswith(('14:45:00', '14:31:00'))]
    rows += [
        _bar('600000.SH', d_iso, '14:57:00', 10.62, 10.60, 10.64, 10.60,
             8_000, 84_960),
        _bar('600000.SH', d_iso, '14:58:00', 10.63, 10.62, 10.65, 10.61,
             9_000, 95_670),
        _bar('600000.SH', d_iso, '14:59:00', 10.61, 10.63, 10.63, 10.60,
             7_000, 74_270),
    ]
    out, c = _extract(tmp_path, rows, d_iso, 'day_pre.parquet')
    r = out.row(0, named=True)
    assert r['symbol'] == 'sh.600000'
    tail = 260_000 + 84_960 + 95_670 + 74_270 + 972_000
    total = 1_000_000 + 500_000 + 300_000 + 400_000 + 200_000 + 200_000 \
        + 260_000 + 84_960 + 95_670 + 74_270 + 972_000
    assert r['close_share30'] == pytest.approx(tail / total)
    assert r['last30_ret'] == pytest.approx(10.80 / 10.50 - 1.0)
    assert c['rows_out'] == 1


def test_hand_sample_sz_symbol_mapping(tmp_path):
    d_iso = '2019-06-17'
    out, _ = _extract(tmp_path, _sample_bars_post(d_iso, '000001.SZ'),
                      d_iso, 'day_sz.parquet')
    assert out['symbol'][0] == 'sz.000001'


def test_fail_closed_freeze_and_determinism(tmp_path):
    rows = _sample_bars_post('2025-01-02', '600000.SH')
    with pytest.raises(RuntimeError, match='freeze'):
        _extract(tmp_path, rows, '2025-01-02', 'day_frozen.parquet')
    rows = _sample_bars_post('2024-12-31', '600000.SH')
    rows[0]['date'] = '20241230'  # filename/row mismatch
    with pytest.raises(RuntimeError, match='mismatch'):
        _extract(tmp_path, rows, '2024-12-31', 'day_bad.parquet')
    fp = _write_day(_sample_bars_post('2024-12-31', '600000.SH'),
                    tmp_path, 'day_ok.parquet')
    a, ca = extract_day_features(fp, '2024-12-31')
    b, cb = extract_day_features(fp, '2024-12-31')
    assert a.equals(b) and ca == cb


# --------------------------------------------------------------------------- #
# 2. limit state + touch tolerances (1e-4 / 2e-4)
# --------------------------------------------------------------------------- #
def _feat_row(**over) -> dict:
    row = {
        'symbol': 'sh.600000', 'date': date(2020, 6, 1),
        'close_share30': 0.1, 'tail_amt_share': 0.1, 'last30_ret': 0.0,
        'day_high': 10.0, 'day_low': 9.0, 'am_range30': 0.5,
        'first_bar_vol': 1000.0, 'first_bar_vol_med20': None,
        'limit_up': None, 'limit_down': None, 'close_day_official': 9.8,
    }
    row.update(over)
    return row


def test_limit_state_and_touch_tolerances():
    seal_thr = 11.0 * (1.0 - 1e-4)
    touch_thr = 9.0 * (1.0 + 2e-4)
    half = pl.DataFrame([
        _feat_row(symbol='sh.600001', close_day_official=seal_thr,
                  day_high=seal_thr, limit_up=11.0, limit_down=9.0,
                  day_low=touch_thr),
        _feat_row(symbol='sh.600002', close_day_official=10.5,
                  day_high=seal_thr, limit_up=11.0, limit_down=9.0),
        _feat_row(symbol='sh.600003', close_day_official=9.8,
                  day_high=seal_thr - 0.01, limit_up=11.0,
                  limit_down=9.0, day_low=touch_thr + 0.001),
        _feat_row(symbol='sh.600004', limit_up=None, limit_down=None),
    ])
    feats = half.drop('limit_up', 'limit_down', 'close_day_official')
    out = finalize_feature_table(feats, half)
    got = {r['symbol']: r for r in out.iter_rows(named=True)}
    assert got['sh.600001']['limit_close_state'] == 2      # sealed
    assert got['sh.600001']['pm_touch_limit_down'] is True  # == threshold
    assert got['sh.600002']['limit_close_state'] == 1      # broke
    assert got['sh.600003']['limit_close_state'] == 0      # untouched
    assert got['sh.600003']['pm_touch_limit_down'] is False
    assert got['sh.600004']['limit_close_state'] is None   # limit missing
    assert got['sh.600004']['pm_touch_limit_down'] is None


# --------------------------------------------------------------------------- #
# 3. first_bar_vol_med20: shift-in-over (no cross-symbol leakage)
# --------------------------------------------------------------------------- #
def test_first_bar_vol_med20_shift_in_over():
    d0 = date(2020, 1, 1)
    rows = []

    def frow(sym, vol, dh, dl, c30):
        return {'symbol': sym, 'date': d0, 'close_share30': c30,
                'tail_amt_share': c30, 'last30_ret': 0.0, 'day_high': dh,
                'day_low': dl, 'am_range30': 0.5, 'first_bar_vol': float(vol),
                'limit_up': None, 'limit_down': None,
                'close_day_official': dh - 0.2}

    for i in range(25):  # symbol A: first_bar_vol 1..25, 25 own sessions
        rows.append(frow('sh.600001', i + 1, 10.0, 9.0, 0.1))
    for i in range(25):  # symbol B: first_bar_vol 100..119
        rows.append(frow('sz.000002', 100 + i, 20.0, 19.0, 0.2))
    feats = pl.DataFrame(rows)
    # separate the symbols onto their own increasing session dates
    feats = feats.with_columns(
        (pl.col('date')
         + pl.duration(days=pl.int_range(pl.len()).over('symbol')))
        .alias('date')).drop('limit_up', 'limit_down',
                             'close_day_official')
    half = feats.with_columns(
        pl.lit(None, dtype=pl.Float64).alias('limit_up'),
        pl.lit(None, dtype=pl.Float64).alias('limit_down'),
        (pl.col('day_high') - 0.2).alias('close_day_official'))
    out = finalize_feature_table(feats, half).sort('symbol', 'date')
    a = out.filter(pl.col('symbol') == 'sh.600001')['first_bar_vol_med20']
    b = out.filter(pl.col('symbol') == 'sz.000002')['first_bar_vol_med20']
    # first 20 own rows are null (median needs 20 PAST values after shift)
    assert all(v is None for v in a[:20])
    assert all(v is None for v in b[:20])
    # row 20: median(1..20) = 10.5 ; row 24: median(5..24) = 14.5
    assert a[20] == pytest.approx(statistics.median(range(1, 21)))
    assert a[24] == pytest.approx(statistics.median(range(5, 25)))
    # no leakage: B's medians come from B's own 100..119, not A's 1..20
    assert b[20] == pytest.approx(statistics.median(range(100, 120)))
    assert b[24] == pytest.approx(statistics.median(range(104, 124)))


# --------------------------------------------------------------------------- #
# 4. next-session T2 anchoring: suspension + 2025+ structural zero-touch
# --------------------------------------------------------------------------- #
def test_t2_next_session_anchoring():
    d27, d30, d31 = date(2024, 12, 27), date(2024, 12, 30), date(2024, 12, 31)

    def frow(sym, d, o930, close, dh, dl, pc):
        return {'symbol': sym, 'date': d, 'close_share30': 0.1,
                'tail_amt_share': 0.1, 'last30_ret': 0.0, 'day_high': dh,
                'day_low': dl, 'am_range30': 0.5, 'first_bar_vol': 1.0,
                'first_bar_vol_med20': 1.0, 'pm_touch_limit_down': False,
                'limit_close_state': 0}

    def hrow(sym, d, o930, close, pc, ts):
        return {'symbol': sym, 'date': d, 'open_930': o930,
                'close_day_official': close, 'preclose_official': pc,
                'tradestatus': ts}

    # A trades all three sessions; B trades 12-27 and 12-31 only
    # (12-30 suspended: halfday placeholder row with tradestatus == 0 and
    # NO feats row)
    feats = pl.DataFrame([
        frow('sh.600001', d27, 10, 10.2, 10.3, 9.9, 10.0),
        frow('sh.600001', d30, 10.2, 10.1, 10.4, 10.0, 10.2),
        frow('sh.600001', d31, 10.1, 10.5, 10.6, 10.0, 10.1),
        frow('sz.000002', d27, 20, 20.4, 20.5, 19.5, 20.0),
        frow('sz.000002', d31, 20.4, 20.8, 21.0, 20.0, 20.4),
    ])
    half = pl.DataFrame([
        hrow('sh.600001', d27, 10, 10.2, 10.0, 1),
        hrow('sh.600001', d30, 10.2, 10.1, 10.2, 1),
        hrow('sh.600001', d31, 10.1, 10.5, 10.1, 1),
        hrow('sz.000002', d27, 20, 20.4, 20.0, 1),
        hrow('sz.000002', d30, 20.0, 20.0, 20.0, 0),  # suspended
        hrow('sz.000002', d31, 20.4, 20.8, 20.4, 1),
    ])
    panel = feats.join(half.drop('open_930'), on=['symbol', 'date'],
                       how='inner')
    out = attach_next_labels(feats, half, panel).sort('symbol', 'date')
    got = {(r['symbol'], r['date']): r for r in out.iter_rows(named=True)}
    # A on 12-27: T2 = close(12-30)/open930(12-30) - 1
    assert got[('sh.600001', d27)]['T2'] == pytest.approx(10.1 / 10.2 - 1)
    # A on 12-30: T2 uses 12-31
    assert got[('sh.600001', d30)]['T2'] == pytest.approx(10.5 / 10.1 - 1)
    # A on 12-31: next session would be 2025-01-02 -> structurally null
    assert got[('sh.600001', d31)]['T2'] is None
    # B on 12-27: next session 12-30 suspended -> label null
    assert got[('sz.000002', d27)]['T2'] is None
    # B on 12-31: null (freeze) even though a later row existed
    assert got[('sz.000002', d31)]['T2'] is None
    # amp_next same anchoring
    assert got[('sh.600001', d27)]['amp_next'] == pytest.approx(
        (10.4 - 10.0) / 10.2)


# --------------------------------------------------------------------------- #
# 5. union-of-buckets control rule
# --------------------------------------------------------------------------- #
def test_control_union_bucket():
    d = date(2020, 6, 1)

    def row(sym, ret, t2, ev):
        return {'symbol': sym, 'date': d, 'day_ret': ret, 'T2': t2, '_ev': ev}

    g = pl.DataFrame([
        row('a', 0.010, 0.01, True),    # event
        row('b', 0.020, 0.02, True),    # event
        row('c', 0.004, 0.00, False),   # 0.006 from nearest event -> out
        row('d', 0.006, 0.00, False),   # 0.004 -> in
        row('e', 0.014, 0.00, False),   # 0.004 -> in
        row('f', 0.014, None, False),   # in bucket but null T2 -> dropped
        row('h', 0.024, 0.00, False),   # 0.004 -> in
        row('i', 0.031, 0.00, False),   # 0.011 -> out
        row('j', 0.050, 0.00, True),    # event (null-free T2? yes)
    ])
    ev, ctrl = control_mask_by_day(g, pl.col('_ev'), None, 0.005)
    assert ev.height == 3
    assert sorted(ctrl['symbol'].to_list()) == ['d', 'e', 'h']


def test_diff_gate_mean_nw_years():
    d0 = date(2015, 6, 1)
    diffs = pl.DataFrame({
        'date': [d0, date(2015, 6, 2), date(2015, 6, 3),
                 date(2016, 6, 1), date(2016, 6, 2)],
        'diff': [-0.01, -0.01, 0.01, -0.01, 0.01],
        'n_event': [5] * 5, 'n_ctrl': [50] * 5,
        'mean_event': [0.0] * 5, 'mean_ctrl': [0.0] * 5,
    })
    g = diff_gate(diffs, -0.005, date(2015, 1, 1), date(2016, 12, 31))
    assert g['n_days'] == 5
    assert g['mean_diff'] == pytest.approx(-0.01 / 5)
    arr = diffs['diff'].to_numpy()
    # NW(5) wiring: the statistic itself is hand-tested in the R10 suite
    assert g['nw_t'] == pytest.approx(newey_west_t(arr, 5))
    assert g['n_years'] == 2
    y2015 = (-0.01 - 0.01 + 0.01) / 3
    y2016 = (-0.01 + 0.01) / 2
    by_year = {y['year']: y['mean_diff'] for y in g['years']}
    assert by_year[2015] == pytest.approx(y2015)
    assert by_year[2016] == pytest.approx(y2016)
    assert g['years_same_sign'] == pytest.approx(
        sum(1 for v in (y2015, y2016) if v < 0) / 2)


# --------------------------------------------------------------------------- #
# 6. residual-IC machinery
# --------------------------------------------------------------------------- #
def test_residual_ic_removes_control_and_keeps_signal():
    rng = np.random.default_rng(17)
    rows = []
    for k in range(5):
        d = date(2018, 1, 1 + k)
        ctrl = rng.uniform(0, 1, 300)
        noise = rng.uniform(0, 1, 300)
        sig = rng.uniform(0, 1, 300)
        tgt = ctrl * 0.8 + noise * 0.2
        fac = ctrl * 0.9 + sig * 0.1
        for i in range(300):
            rows.append({'date': d, 'symbol': f's{i:03d}', 'F': float(fac[i]),
                         'log_amount': float(ctrl[i]), 'day_ret': 0.0,
                         'T2': float(tgt[i])})
    panel = pl.DataFrame(rows)
    raw = panel.group_by('date').agg(
        pl.corr('F', 'T2', method='spearman').alias('ic'))
    raw_mean = float(raw['ic'].mean())
    ric = residual_ic_series(panel, 'F', ['log_amount', 'day_ret'], 'T2',
                             date(2018, 1, 1), date(2018, 1, 31))
    assert ric.height == 5
    resid_mean = float(ric['ic'].mean())
    # residualization kills most of the control's contribution but the
    # independent signal keeps the residual IC positive and below raw
    assert 0.0 < resid_mean < raw_mean


# --------------------------------------------------------------------------- #
# 7. U5 use-gate math + seed sampler
# --------------------------------------------------------------------------- #
def test_p5_improvement_and_use_gate():
    assert p5_improvement(-0.04, -0.036) == pytest.approx(0.10)
    assert p5_improvement(-0.04, -0.044) == pytest.approx(-0.10)
    assert p5_improvement(0.02, 0.025) == pytest.approx(0.25)
    assert p5_improvement(0.0, 0.01) is None
    assert use_gate_pass(0.10, 0.005) is True
    assert use_gate_pass(0.10, 0.006) is False
    assert use_gate_pass(0.05, 0.0) is False
    assert use_gate_pass(None, 0.0) is False


def test_pick_sample_seed17_deterministic():
    items = list(range(1000))
    a = pick_sample(items, 7)
    b = pick_sample(items, 7)
    assert a == b
    assert a == random.Random(SEED).sample(items, 7)
    c = pick_sample([3, 1, 2], 2)  # sorted before sampling
    assert c == random.Random(SEED).sample([1, 2, 3], 2)
