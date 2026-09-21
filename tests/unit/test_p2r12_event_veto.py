"""Unit tests for the P2-R12 event veto chain (quant.research.p2r12_event_veto).

Synthetic frames only: PIT marking (announcement after the signal session
must never mark), unlock window boundaries, deterministic matching, forecast
revision chains, accrual PIT fallback and decile cut, financial exclusion,
bootstrap seed determinism, adjusted forward labels across a corporate
action, dev/val label purge, and C03/C06 gate math.  Nothing here is
profitability evidence.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from quant.research import p2r12_event_veto as ev  # noqa: E402

START = date(2020, 1, 1)


def _cal(n: int) -> ev.Calendar:
    days = [START + timedelta(days=i) for i in range(n)]
    return ev.Calendar(pl.Series(days))


def _sf_row(ts_code: str, float_d: date, k: date, mag: float = 2.0,
            agg: int = 1, in_pool: bool = True) -> dict:
    return {'event_id': f'unlock.{ts_code}.{float_d:%Y%m%d}.1',
            'ts_code': ts_code, 'ts_event': float_d, 'ts_knowledge': k,
            'magnitude': mag, 'agg_ann_date_count': agg, 'in_pool': in_pool}


SF_SCHEMA = {'event_id': pl.String, 'ts_code': pl.String, 'ts_event': pl.Date,
             'ts_knowledge': pl.Date, 'magnitude': pl.Float64,
             'agg_ann_date_count': pl.Int64, 'in_pool': pl.Boolean}


# --------------------------------------------------------------------------- #
# C01: PIT marking + activation window
# --------------------------------------------------------------------------- #
def test_unlock_pit_requires_knowledge_before_float():
    cal = _cal(120)
    rows = [
        # known 5 sessions before the float -> activates at knowledge
        _sf_row('000001.SZ', cal.date_at(50), cal.date_at(45)),
        # announced on the float date -> never markable (PIT counterexample)
        _sf_row('000002.SZ', cal.date_at(50), cal.date_at(50)),
        # announced after the float date -> never markable
        _sf_row('000003.SZ', cal.date_at(50), cal.date_at(60)),
    ]
    events, ranges, counts = ev.build_unlock_events(
        pl.DataFrame(rows, schema=SF_SCHEMA), cal)
    assert counts['announced_at_or_after_float'] == 2
    assert events.height == 1
    # activation at max(first session >= knowledge, float-21)
    assert events['pos'][0] == 45
    assert ranges['t0'][0] == 45 and ranges['t1'][0] == 48


def test_unlock_activation_window_boundaries():
    cal = _cal(120)
    # knowledge long before: activation pinned at float-21
    early = _sf_row('000010.SZ', cal.date_at(30), cal.date_at(1))
    # knowledge inside the window
    inside = _sf_row('000011.SZ', cal.date_at(30), cal.date_at(20))
    # knowledge one session before the float: entry would sit at the float
    late = _sf_row('000012.SZ', cal.date_at(30), cal.date_at(29))
    events, _, counts = ev.build_unlock_events(
        pl.DataFrame([early, inside, late], schema=SF_SCHEMA), cal)
    assert counts['out_of_calendar'] == 1
    by_sym = dict(zip(events['symbol'].to_list(), events['pos'].to_list()))
    assert by_sym['sz.000010'] == 30 - 21
    assert by_sym['sz.000011'] == 20
    # magnitude threshold, aggregation tightening, pool flag
    small = _sf_row('000013.SZ', cal.date_at(30), cal.date_at(20), mag=0.9)
    multi = _sf_row('000014.SZ', cal.date_at(30), cal.date_at(20), agg=2)
    out_pool = _sf_row('000015.SZ', cal.date_at(30), cal.date_at(20),
                       in_pool=False)
    events2, _, _ = ev.build_unlock_events(
        pl.DataFrame([small, multi, out_pool], schema=SF_SCHEMA), cal)
    assert events2.height == 0


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #
def _s_row(sym: str, d: date, ret5: float, fwd5: float, d5: int, q5: int,
           v1: bool = False) -> dict:
    return {'symbol': sym, 'date': d, 'pos': 5, 'year': d.year,
            'fwd5': fwd5, 'fwd10': 0.0, 'fwd60': 0.0,
            'exit5_date': d, 'exit10_date': d, 'exit60_date': d,
            'block5_exit': False, 'block5_window': False,
            'ret5': ret5, 'circ_mv': 100.0, 'd5': d5, 'q5': q5, 'v1': v1}


def test_matching_nearest_deterministic_and_unmarked():
    cal = _cal(10)
    d = cal.date_at(5)
    s = pl.DataFrame([
        _s_row('sz.000001', d, 0.050, 0.010, 3, 2, v1=True),   # event
        _s_row('sz.000002', d, 0.049, -0.020, 3, 2),           # nearest (0.001)
        _s_row('sz.000003', d, 0.052, 0.030, 3, 2),            # farther (0.002)
        _s_row('sz.000004', d, 0.0495, -0.050, 3, 2, v1=True),  # flagged: excluded
    ])
    events = pl.DataFrame([{'symbol': 'sz.000001', 'date': d, 'pos': 5}])
    matched, counts = ev.match_controls(s, events, 'v1', 'fwd5')
    assert counts['matched'] == 1
    row = matched.row(0, named=True)
    assert row['ctrl_symbol'] == 'sz.000002'
    assert row['excess'] == pytest.approx(0.010 - (-0.020))


def test_matching_tie_broken_by_symbol():
    cal = _cal(10)
    d = cal.date_at(5)
    # distances 0.25 exactly representable -> genuine tie
    s = pl.DataFrame([
        _s_row('sz.000001', d, 0.50, 0.010, 3, 2, v1=True),
        _s_row('sz.000002', d, 0.25, 0.000, 3, 2),
        _s_row('sz.000003', d, 0.75, 0.000, 3, 2),
    ])
    events = pl.DataFrame([{'symbol': 'sz.000001', 'date': d, 'pos': 5}])
    matched, _ = ev.match_controls(s, events, 'v1', 'fwd5')
    assert matched['ctrl_symbol'][0] == 'sz.000002'


def test_matching_no_candidate_is_not_matched():
    cal = _cal(10)
    d = cal.date_at(5)
    s = pl.DataFrame([_s_row('sz.000001', d, 0.050, 0.010, 3, 2, v1=True)])
    events = pl.DataFrame([{'symbol': 'sz.000001', 'date': d, 'pos': 5}])
    matched, counts = ev.match_controls(s, events, 'v1', 'fwd5')
    assert matched.height == 0
    assert counts['no_candidate_in_cell'] == 1


# --------------------------------------------------------------------------- #
# C02: forecast revision chains
# --------------------------------------------------------------------------- #
def _fc(ts: str, ann: str, end: str, ftype: str, pcm, first=None, uf=0):
    return {'ts_code': ts, 'ann_date': ann, 'end_date': end, 'type': ftype,
            'p_change_min': pcm, 'first_ann_date': first or ann,
            'update_flag': uf}


def test_forecast_chain_tail_vs_first():
    cal = _cal(120)
    raw = pl.DataFrame([
        _fc('000001.SZ', '20200110', '20191231', '预增', 50.0),
        _fc('000001.SZ', '20200120', '20191231', '预减', 10.0,
            first='20200110', uf=1),
        # same-type chain with a mild pcm drop: downgrade but not deep
        _fc('000002.SZ', '20200110', '20191231', '预增', 50.0),
        _fc('000002.SZ', '20200115', '20191231', '预增', 40.0,
            first='20200110', uf=1),
        # single-version first disclosure already negative
        _fc('000003.SZ', '20200112', '20191231', '预减', -20.0),
        # beyond the freeze line: never enters
        _fc('000004.SZ', '20250110', '20241231', '预增', 50.0),
        _fc('000004.SZ', '20250120', '20241231', '预减', 10.0,
            first='20250110', uf=1),
    ])
    down, firstneg, counts = ev.build_forecast_chains(raw, cal)
    assert counts['rows_in_freeze'] == 5
    assert counts['multi_version_chains'] == 2
    assert counts['downgrade_events'] == 2
    assert counts['deep_events'] == 1
    assert counts['first_negative_events'] == 1
    deep = down.filter(pl.col('deep'))
    assert deep['symbol'].to_list() == ['sz.000001']
    # event session = first session at/after the tail announcement
    assert down.filter(pl.col('symbol') == 'sz.000002')['pos'][0] \
        == cal.pos_at_or_after(date(2020, 1, 15))


def test_forecast_type_classification_ordering():
    assert ev.classify_forecast_type('预增') == 0
    assert ev.classify_forecast_type('扭亏') == 0
    assert ev.classify_forecast_type('不确定') == 1
    assert ev.classify_forecast_type(None) == 1
    assert ev.classify_forecast_type('首亏') == 2
    assert ev.classify_forecast_type('预减') == 2


# --------------------------------------------------------------------------- #
# C04: holder trade events
# --------------------------------------------------------------------------- #
def _ht(ts: str, ann: str, htype: str, in_de: str, ratio):
    return {'ts_code': ts, 'ann_date': ann, 'holder_type': htype,
            'in_de': in_de, 'change_ratio': ratio}


def test_holdertrade_c_filter_and_dedup():
    cal = _cal(120)
    raw = pl.DataFrame([
        _ht('000001.SZ', '20200301', 'C', 'DE', 0.7),
        _ht('000001.SZ', '20200301', 'C', 'DE', 1.2),   # same day -> max
        _ht('000002.SZ', '20200302', 'G', 'DE', 2.0),   # G/P arm only
        _ht('000003.SZ', '20200303', 'C', 'IN', 5.0),   # IN excluded
        _ht('000004.SZ', '20200304', 'C', 'DE', 0.3),   # below threshold
        _ht('000005.SZ', '20250301', 'C', 'DE', 5.0),   # beyond freeze
    ])
    c_ev, gp_ev, counts = ev.build_holdertrade_events(raw, cal)
    assert counts['rows_in_freeze'] == 5
    assert c_ev.height == 1
    assert c_ev['change_ratio'][0] == pytest.approx(1.2)
    assert c_ev['segment'][0] == 'post'
    assert gp_ev.height == 1 and gp_ev['symbol'][0] == 'sz.000002'


# --------------------------------------------------------------------------- #
# C05: accrual PIT + decile + exclusion
# --------------------------------------------------------------------------- #
def _cf(ts: str, end: str, ann, f_ann, np_, ocf):
    return {'ts_code': ts, 'ann_date': ann, 'f_ann_date': f_ann,
            'end_date': end, 'net_profit': np_, 'n_cashflow_act': ocf,
            'update_flag': '0'}


def _bs(ts: str, end: str, ann, f_ann, ta):
    return {'ts_code': ts, 'ann_date': ann, 'f_ann_date': f_ann,
            'end_date': end, 'total_assets': ta, 'update_flag': '0'}


def test_accrual_pit_fallback_and_failclosed():
    cal = _cal(120)
    cf = pl.DataFrame([
        # ann null -> f_ann used; pit = max(f_ann, end+90d)
        _cf('000001.SZ', '20191231', None, '20200415', 100.0, -50.0),
        # ann present, later than end+90d
        _cf('000002.SZ', '20191231', '20200601', None, 200.0, 0.0),
        # both announcements null -> fail-closed
        _cf('000003.SZ', '20191231', None, None, 100.0, 10.0),
        # industry unavailable -> excluded fail-closed
        _cf('000004.SZ', '20191231', '20200410', None, 100.0, 10.0),
        # non-positive total assets -> dropped
        _cf('000005.SZ', '20191231', '20200410', None, 100.0, 10.0),
    ])
    bs = pl.DataFrame([
        _bs('000001.SZ', '20191231', None, '20200415', 1000.0),
        _bs('000002.SZ', '20191231', '20200601', None, 4000.0),
        _bs('000003.SZ', '20191231', None, None, 1000.0),
        _bs('000004.SZ', '20191231', '20200410', None, 500.0),
        _bs('000005.SZ', '20191231', '20200410', None, 0.0),
    ])
    industries = pl.DataFrame({'ts_code': [f'00000{i}.SZ' for i in range(1, 6)],
                               'industry': ['造纸', '银行', '软件', None, '造纸']})
    cohorts, counts = ev.build_accrual_cohorts(cf, bs, industries, cal)
    assert counts['financial_excluded'] == 1          # 000002 银行
    assert counts['industry_unavailable_excluded'] == 1  # 000004
    assert cohorts['symbol'].to_list() == ['sz.000001']  # 000005 ta<=0
    row = cohorts.row(0, named=True)
    assert row['accrual'] == pytest.approx((100.0 - (-50.0)) / 1000.0)
    # pit = max(f_ann, end+90d) = max(2020-04-15, 2020-03-30)
    assert row['pit'] == date(2020, 4, 15)


def test_accrual_top_decile_marking():
    cal = _cal(120)
    n = 10
    cf = pl.DataFrame([_cf(f'0001{i:02d}.SZ', '20191231', '20200410', None,
                           float(i + 1), 0.0) for i in range(n)])
    bs = pl.DataFrame([_bs(f'0001{i:02d}.SZ', '20191231', '20200410', None,
                           100.0) for i in range(n)])
    industries = pl.DataFrame({'ts_code': [f'0001{i:02d}.SZ' for i in range(n)],
                               'industry': ['造纸'] * n})
    cohorts, _ = ev.build_accrual_cohorts(cf, bs, industries, cal)
    marked = cohorts.filter(pl.col('marked'))
    assert marked.height == 1
    # highest accrual = highest net profit at equal assets
    assert marked['symbol'][0] == 'sz.000109'


# --------------------------------------------------------------------------- #
# bootstrap + windows + years
# --------------------------------------------------------------------------- #
def test_bootstrap_seed_deterministic():
    rng = np.random.default_rng(7)
    values = rng.normal(0, 0.01, 400)
    clusters = np.repeat(np.arange(40), 10)
    a = ev.bootstrap_ci_mean(values, clusters)
    b = ev.bootstrap_ci_mean(values, clusters)
    assert a == b
    c = ev.bootstrap_ci_mean(values, clusters, seed=18)
    assert a['ci_lo'] != c['ci_lo']
    assert a['mean'] == pytest.approx(float(values.mean()))


def test_assign_window_purges_crossing_labels():
    events = pl.DataFrame({
        'date': [date(2020, 12, 28), date(2020, 12, 30), date(2021, 1, 4)],
        'exit5_date': [date(2021, 1, 6), date(2021, 1, 7), date(2021, 1, 11)],
    })
    out, counts = ev.assign_window(events)
    assert counts['purged_dev_exit_crossing'] == 2
    assert out['window'].to_list() == ['val']


def test_year_consistency_rules():
    five_years = [{'year': y, 'n': 10, 'metric': -0.01} for y in range(2016, 2021)]
    assert ev.year_consistency(five_years)['pass'] is True
    assert ev.year_consistency(five_years)['required'] == 4
    five_years[0]['metric'] = 0.01
    res = ev.year_consistency(five_years)
    assert res['n_same_sign'] == 4 and res['pass'] is True
    five_years[1]['metric'] = 0.02
    assert ev.year_consistency(five_years)['pass'] is False
    two_years = [{'year': 2019, 'n': 5, 'metric': -0.01},
                 {'year': 2020, 'n': 5, 'metric': 0.01}]
    assert ev.year_consistency(two_years)['pass'] is False
    above = [{'year': 2019, 'n': 5, 'metric': 1.8},
             {'year': 2020, 'n': 5, 'metric': 1.1}]
    res = ev.year_consistency(above, 'above', 1.5)
    assert res['n_same_sign'] == 1 and res['pass'] is False


# --------------------------------------------------------------------------- #
# forward labels across a corporate action
# --------------------------------------------------------------------------- #
def _daily_frame(n: int) -> pl.DataFrame:
    """Two symbols; an ex-div style event at i == 30: the raw price halves
    and adj_factor doubles, so adjusted levels stay continuous."""
    rows = []
    for sym, base in (('sz.000001', 10.0), ('sz.000002', 20.0)):
        for i in range(n):
            factor = 1.0 if i < 30 else 2.0
            adj = base + i * 0.1
            raw = adj / factor
            rows.append({'symbol': sym, 'date': START + timedelta(days=i),
                         'open': raw, 'close': raw,
                         'adj_factor': factor, 'tradestatus': 1.0,
                         'seal': False})
    return pl.DataFrame(rows).sort('symbol', 'date')


def test_forward_labels_across_corporate_action():
    daily = _daily_frame(70)
    out = ev.attach_labels(daily)
    # signal at i=25: entry open i=26, exit close i=30 across the ex-div:
    # adjusted levels are continuous, so the label is the economic return
    sig = out.filter((pl.col('symbol') == 'sz.000001')
                     & (pl.col('date') == START + timedelta(days=25)))
    expected = (10.0 + 3.0) / (10.0 + 2.6) - 1.0
    assert sig['fwd5'][0] == pytest.approx(expected)
    assert sig['exit5_date'][0] == START + timedelta(days=30)
    ret5_sig = out.filter((pl.col('symbol') == 'sz.000001')
                          & (pl.col('date') == START + timedelta(days=32)))
    expected_ret5 = (10.0 + 3.2) / (10.0 + 2.7) - 1.0
    assert ret5_sig['ret5'][0] == pytest.approx(expected_ret5)


def test_block_flags_any_sellable_session():
    daily = _daily_frame(70)
    daily = daily.with_columns(
        pl.when((pl.col('symbol') == 'sz.000001')
                & (pl.col('date') == START + timedelta(days=28)))
        .then(True)
        .when((pl.col('symbol') == 'sz.000001')
              & (pl.col('date') == START + timedelta(days=33)))
        .then(True)
        .otherwise(pl.col('seal')).alias('seal'))
    out = ev.attach_block_flags(ev.attach_labels(daily))
    # signal i=25: sellable t+2..t+5 = i 27..30: seal at 28 -> window True,
    # exit session (i=30) not sealed
    sig = out.filter((pl.col('symbol') == 'sz.000001')
                     & (pl.col('date') == START + timedelta(days=25)))
    assert bool(sig['block5_window'][0]) is True
    assert bool(sig['block5_exit'][0]) is False
    # signal i=28: exit i=33 sealed -> exit-blocked True
    sig28 = out.filter((pl.col('symbol') == 'sz.000001')
                       & (pl.col('date') == START + timedelta(days=28)))
    assert bool(sig28['block5_exit'][0]) is True


# --------------------------------------------------------------------------- #
# C03 and C06 gate math
# --------------------------------------------------------------------------- #
def _matched_row(d: date, ret_e: float, ret_c: float, block_e: bool,
                 block_c: bool) -> dict:
    return {'date': d, 'year': d.year, 'ret_event': ret_e, 'ret_ctrl': ret_c,
            'block5_exit': block_e, 'block5_exit_ctrl': block_c,
            'block5_window': block_e, 'block5_window_ctrl': block_c,
            'excess': ret_e - ret_c, 'window': 'dev'}


def test_c03_gate_cells():
    d0 = date(2019, 5, 6)
    rows = [_matched_row(d0, -0.02 - i * 0.001, -0.005, i < 10, i < 2)
            for i in range(50)]
    matched = pl.DataFrame(rows)
    out = ev.evaluate_c03(matched)
    dev = out['dev']
    assert dev['gate_tail'] is True          # marked P5 far below control P5
    assert dev['gate_block'] is True         # 10/50 vs 2/50 = 5x
    assert dev['gate_mean_cap'] is True      # marked mean below control
    assert dev['pass'] is True
    # mean cap breach: marked outperform by more than 0.15pp
    rows2 = [_matched_row(d0, 0.002, 0.0, False, False) for _ in range(50)]
    out2 = ev.evaluate_c03(pl.DataFrame(rows2))
    assert out2['dev']['gate_mean_cap'] is False
    assert out2['dev']['gate_tail'] is False
    assert out2['dev']['pass'] is False


def _c06_s_rows(n_days: int) -> pl.DataFrame:
    rng = np.random.default_rng(3)
    rows = []
    for d_i in range(n_days):
        d = date(2019, 1, 2) + timedelta(days=d_i)
        for i in range(20):
            rows.append({
                'symbol': f'sz.{i:06d}', 'date': d, 'pos': 100 + d_i,
                'year': d.year, 'fwd5': float(rng.normal(-0.001, 0.02)),
                'exit5_date': d + timedelta(days=5),
                'v1': i < 2, 'v2': False, 'v3': False, 'v4': False,
                'v5': 2 <= i < 5,
            })
    return pl.DataFrame(rows)


def test_c06_cut_mean_and_tail_math():
    s = _c06_s_rows(30)
    out = ev.evaluate_c06(s)
    host = s
    n_host = host.height
    veto = host.filter((pl.col('v1')) | (pl.col('v5')))
    assert out['dev']['n_host'] == n_host
    assert out['dev']['n_vetoed'] == veto.height
    assert out['dev']['cut_share'] == pytest.approx(veto.height / n_host)
    assert out['dev']['mean_loss'] == pytest.approx(
        float(veto['fwd5'].mean()) - float(host['fwd5'].mean()))


# --------------------------------------------------------------------------- #
# C05 incidence math
# --------------------------------------------------------------------------- #
def test_c05_incidence_ratio():
    cal = _cal(400)
    base = {'pit': date(2020, 4, 10),
            'pos': cal.pos_at_or_after(date(2020, 4, 10))}
    cohorts = pl.DataFrame([
        {'symbol': 'sz.000001', 'fy': 2019, **base, 'accrual': 0.2,
         'marked': True, 'rank_pct': 0.95},
        {'symbol': 'sz.000002', 'fy': 2019, **base, 'accrual': 0.1,
         'marked': False, 'rank_pct': 0.5},
        {'symbol': 'sz.000003', 'fy': 2019, **base, 'accrual': 0.05,
         'marked': False, 'rank_pct': 0.3},
    ])
    forecast_neg = pl.DataFrame({
        'symbol': ['sz.000001'],
        'ts_knowledge': [date(2020, 9, 1)],  # inside the 12-month window
    })
    out = ev.c05_incidence(cohorts, forecast_neg, date(2018, 9, 3))
    dev = out['windows']['dev']
    assert dev['n_marked'] == 1 and dev['n_cohort'] == 3
    assert dev['incidence_marked'] == 1.0
    assert dev['incidence_cohort'] == pytest.approx(1 / 3)
    assert dev['ratio'] == pytest.approx(3.0)
    assert dev['gate_ratio'] is True
    # a cohort whose 12-month window crosses the freeze line is not judged
    cohorts2 = cohorts.with_columns(
        pl.when(pl.col('symbol') == 'sz.000001')
        .then(date(2024, 6, 1)).otherwise(pl.col('pit')).alias('pit'))
    out2 = ev.c05_incidence(cohorts2, forecast_neg, date(2018, 9, 3))
    assert out2['windows']['val']['n_cohort'] == 0
    assert out2['windows']['val']['gate_ratio'] is False


# --------------------------------------------------------------------------- #
# stamp duty segmentation
# --------------------------------------------------------------------------- #
def test_stamp_segmentation_and_net():
    assert ev.stamp_for(date(2023, 8, 27)) == 0.001
    assert ev.stamp_for(date(2023, 8, 28)) == 0.0005
    net_before = ev.net_return(0.0, date(2023, 1, 1))
    net_after = ev.net_return(0.0, date(2023, 9, 1))
    assert net_before < net_after < 0.0  # costs only
