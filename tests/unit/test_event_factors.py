"""Unit tests for event factor structuring v1 (quant.data.event_batches).

Synthetic frames only: direction dictionaries, forecast correction chain,
share_float aggregation, ts_available next-trading-day rollover (weekends
and holidays), freeze-line filtering and fail-closed drops.  Nothing here is
profitability evidence.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.data import event_batches as eb  # noqa: E402

CAL = [
    date(2024, 1, 8),   # Mon
    date(2024, 1, 9),   # Tue
    date(2024, 1, 10),  # Wed
    date(2024, 1, 12),  # Fri (Thu 2024-01-11 treated as holiday)
    date(2024, 1, 15),  # Mon
    date(2024, 1, 17),  # Wed, calendar end
]


def _frame(rows: list[dict], cols: list[str]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=cols, orient='row' if rows else None)


# --------------------------------------------------------------------------- #
# forecast: direction dictionary + correction chain + magnitude
# --------------------------------------------------------------------------- #
FORECAST_COLS = [
    'ts_code', 'ann_date', 'end_date', 'type', 'p_change_min', 'p_change_max',
    'net_profit_min', 'net_profit_max', 'last_parent_net', 'first_ann_date',
    'summary', 'change_reason', 'update_flag',
]


def _fc_row(code, ann, end, ftype, pmin=None, pmax=None, first=None, flag=0,
            reason=None, summary=None):
    return [code, ann, end, ftype, pmin, pmax, None, None, None, first,
            summary, reason, flag]


def test_forecast_direction_dictionary():
    rows = [
        _fc_row('000001.SZ', '20240110', '20231231', '预增', 50.0),
        _fc_row('000002.SZ', '20240110', '20231231', '略增', 20.0),
        _fc_row('000003.SZ', '20240110', '20231231', '扭亏'),
        _fc_row('000004.SZ', '20240110', '20231231', '续盈'),
        _fc_row('000005.SZ', '20240110', '20231231', '预减', -30.0),
        _fc_row('000006.SZ', '20240110', '20231231', '略减', -10.0),
        _fc_row('000007.SZ', '20240110', '20231231', '首亏'),
        _fc_row('000008.SZ', '20240110', '20231231', '续亏'),
        _fc_row('000009.SZ', '20240110', '20231231', '不确定'),
        _fc_row('000010.SZ', '20240110', '20231231', '增亏'),
        _fc_row('000011.SZ', '20240110', '20231231', '减亏'),
        _fc_row('000012.SZ', '20240110', '20231231', '其他'),
    ]
    raw = _frame(rows, FORECAST_COLS)
    events, stats = eb.build_forecast(raw, 'tushare/forecast/test', CAL)
    got = dict(zip(events['ts_code'], events['direction']))
    expect = {'000001.SZ': 1, '000002.SZ': 1, '000003.SZ': 1, '000004.SZ': 1,
              '000005.SZ': -1, '000006.SZ': -1, '000007.SZ': -1, '000008.SZ': -1,
              '000009.SZ': 0, '000010.SZ': 0, '000011.SZ': 0, '000012.SZ': 0}
    assert got == expect
    assert set(events['direction_source']) == {'field_enum'}
    assert set(events['confidence']) == {'high'}


def test_forecast_chain_keeps_earliest_version_no_merging():
    rows = [
        # later revision must be dropped entirely (not merged field-wise)
        _fc_row('600000.SH', '20240305', '20231231', '预减', -5.0, -1.0,
                first='20240301', flag=1, reason='修正版'),
        # earliest disclosure wins
        _fc_row('600000.SH', '20240115', '20231231', '预增', 50.0, 60.0,
                first='20240110', flag=0, reason='首次', summary='预计增长50%-60%'),
        # same (first_ann, ann) tie case is counted, deterministic pick
        _fc_row('600001.SH', '20240201', '20231231', '预增', 10.0, None,
                first='20240101', flag=0),
        _fc_row('600001.SH', '20240201', '20231231', '预减', -10.0, None,
                first='20240101', flag=1),
    ]
    raw = _frame(rows, FORECAST_COLS)
    events, stats = eb.build_forecast(raw, 'tushare/forecast/test', CAL)
    assert events.height == 2  # one per (ts_code, end_date)
    first = events.filter(pl.col('ts_code') == '600000.SH')
    assert first['direction'][0] == 1            # earliest version, not revision
    assert first['magnitude'][0] == 50.0         # first version's values only
    assert first['raw_text'][0] == '首次'        # no first-non-null merging
    assert first['summary'][0] == '预计增长50%-60%'
    assert stats['chain_groups'] == 2
    assert stats['chain_tie_groups'] == 1        # 600001.SH tie counted, not silently resolved
    tie = events.filter(pl.col('ts_code') == '600001.SH')
    assert tie['direction'][0] == 1              # deterministic: first by update_flag order


def test_forecast_magnitude_null_and_fail_closed():
    rows = [
        _fc_row('600002.SH', '20240110', '20231231', '首亏'),          # no p_change
        _fc_row('600003.SH', None, '20231231', '预增', 30.0),          # missing ann -> drop
    ]
    raw = _frame(rows, FORECAST_COLS)
    events, stats = eb.build_forecast(raw, 'tushare/forecast/test', CAL)
    assert events.height == 1
    assert events['magnitude'][0] is None
    assert events['magnitude_max'][0] is None
    assert events['direction'][0] == -1
    assert stats['fail_closed_missing_knowledge_dropped'] == 1


def test_forecast_first_ann_fallback():
    rows = [_fc_row('600004.SH', '20240110', '20231231', '预增', 5.0, first=None)]
    raw = _frame(rows, FORECAST_COLS)
    _, stats = eb.build_forecast(raw, 'tushare/forecast/test', CAL)
    assert stats['first_ann_date_fallback_to_ann_date'] == 1


# --------------------------------------------------------------------------- #
# express: sign derived
# --------------------------------------------------------------------------- #
def test_express_sign_and_nulls():
    rows = [
        ['000001.SZ', '20240115', '20231231', 100.0],
        ['000002.SZ', '20240115', '20231231', -50.5],
        ['000003.SZ', '20240115', '20231231', 0.0],
        ['000004.SZ', '20240115', '20231231', None],
    ]
    raw = pl.DataFrame(rows, schema=['ts_code', 'ann_date', 'end_date', 'yoy_net_profit'], orient='row')
    events, stats = eb.build_express(raw, 'tushare/express/test', CAL)
    got = dict(zip(events['ts_code'], events['direction']))
    assert got == {'000001.SZ': 1, '000002.SZ': -1, '000003.SZ': 0, '000004.SZ': 0}
    assert set(events['direction_source']) == {'derived'}
    assert stats['null_magnitude_rows'] == 1
    assert stats['zero_magnitude_rows'] == 1
    assert events.filter(pl.col('ts_code') == '000002.SZ')['magnitude'][0] == -50.5


# --------------------------------------------------------------------------- #
# repurchase: plan filter + same-day campaigns
# --------------------------------------------------------------------------- #
def test_repurchase_plan_filter_and_same_day_campaigns():
    rows = [
        ['000001.SZ', '20240110', '20241231', '预案', '20241231', 1000.0, 5000.0],
        ['000001.SZ', '20240110', '20251231', '预案', '20251231', 2000.0, 9000.0],
        ['000001.SZ', '20240301', '20241231', '完成', '20241231', 1000.0, 4800.0],
        ['000002.SZ', '20240112', '20241231', '实施', None, None, None],
    ]
    raw = pl.DataFrame(
        rows,
        schema=['ts_code', 'ann_date', 'end_date', 'proc', 'exp_date', 'vol', 'amount'],
        orient='row',
    )
    events, stats = eb.build_repurchase(raw, 'tushare/repurchase/test', CAL)
    assert events.height == 2                                # only 预案 rows
    assert set(events['direction']) == {1}
    assert set(events['confidence']) == {'high'}
    assert stats['non_plan_rows_filtered_out'] == 2
    assert stats['same_day_campaign_groups_kept'] == 1
    plans = events.filter(pl.col('ts_code') == '000001.SZ').sort('event_id')
    assert plans['event_id'].to_list() == [
        'repurchase_plan.000001.SZ.20240110.1',
        'repurchase_plan.000001.SZ.20240110.2',
    ]
    assert events['magnitude'][0] is None
    assert events['ts_event'][0] == events['ts_knowledge'][0] == date(2024, 1, 10)


# --------------------------------------------------------------------------- #
# share_float: aggregation
# --------------------------------------------------------------------------- #
def test_share_float_aggregation_and_null_ratio():
    rows = [
        # same (ts_code, float_date, share_type, ann_date) two holders -> summed
        ['000001.SZ', '20240105', '20240110', 1000.0, 1.5, '张三', '首发原始股'],
        ['000001.SZ', '20240105', '20240110', 2000.0, 2.5, '李四', '首发原始股'],
        # separate share_type stays separate
        ['000001.SZ', '20240105', '20240110', 500.0, 0.5, '王五', '定增股份'],
        # all-ratio-null group -> magnitude null
        ['000002.SZ', '20240105', '20240110', 300.0, None, '赵六', '其他类型'],
        # same (ts_code, float_date, share_type) announced twice -> earliest ann wins
        ['000003.SZ', '20240106', '20240112', 100.0, 0.2, '孙七', '首发原始股'],
        ['000003.SZ', '20240109', '20240112', 900.0, 1.8, '周八', '首发原始股'],
    ]
    raw = pl.DataFrame(
        rows,
        schema=['ts_code', 'ann_date', 'float_date', 'float_share', 'float_ratio',
                'holder_name', 'share_type'],
        orient='row',
    )
    events, stats = eb.build_share_float(raw, 'tushare/share_float/test', CAL)
    assert events.height == 4
    main = events.filter(
        (pl.col('ts_code') == '000001.SZ') & (pl.col('ts_event') == date(2024, 1, 10))
        & (pl.col('float_share_sum') == 3000.0)
    )
    assert main.height == 1
    assert main['magnitude'][0] == 4.0            # 1.5 + 2.5 summed ratio
    assert main['direction'][0] == -1
    assert main['confidence'][0] == 'medium'
    assert main['ts_knowledge'][0] == date(2024, 1, 5)   # earliest ann in group
    null_row = events.filter(pl.col('ts_code') == '000002.SZ')
    assert null_row['magnitude'][0] is None
    assert null_row['float_share_sum'][0] == 300.0
    assert stats['groups_with_multiple_ann_dates'] == 1
    multi = events.filter(pl.col('ts_code') == '000003.SZ')
    assert multi['ts_knowledge'][0] == date(2024, 1, 6)  # earliest of the two ann dates
    assert multi['magnitude'][0] == 2.0                  # sums span all rows of the group
    assert multi['agg_ann_date_count'][0] == 2
    assert stats['source_rows_aggregated'] == 6


# --------------------------------------------------------------------------- #
# holdertrade: IN/DE + unknown dropped
# --------------------------------------------------------------------------- #
def test_holdertrade_direction_unknown_dropped_and_pk_report():
    rows = [
        ['000001.SZ', '20240110', '张三', 'G', 'IN', 1000.0, 0.5],
        ['000002.SZ', '20240110', '李四公司', 'C', 'DE', 5000.0, 1.2],
        ['000003.SZ', '20240110', '王五', 'P', 'XX', 10.0, 0.01],  # unknown -> drop
    ]
    raw = pl.DataFrame(
        rows,
        schema=['ts_code', 'ann_date', 'holder_name', 'holder_type', 'in_de',
                'change_vol', 'change_ratio'],
        orient='row',
    )
    events, stats = eb.build_holdertrade(raw, 'tushare/stk_holdertrade/test', CAL)
    got = dict(zip(events['ts_code'], events['direction']))
    assert got == {'000001.SZ': 1, '000002.SZ': -1}
    assert stats['unknown_in_de_dropped'] == 1
    assert set(events['confidence']) == {'medium'}
    assert events['ts_event'][0] == events['ts_knowledge'][0] == date(2024, 1, 10)
    # candidate-key collision reporting does not raise on content-distinct rows
    dup = pl.DataFrame(
        [['000001.SZ', '20240110', '张三', 'G', 'IN', 1000.0, 0.5],
         ['000001.SZ', '20240110', '张三', 'G', 'IN', 1000.0, 0.9]],
        schema=['ts_code', 'ann_date', 'holder_name', 'holder_type', 'in_de',
                'change_vol', 'change_ratio'], orient='row',
    )
    report = eb.assert_pk_unique(
        dup, ['ts_code', 'ann_date', 'holder_name', 'in_de', 'change_vol'], 't'
    )
    assert report['collision_groups'] == 1 and report['collision_rows'] == 2


def test_assert_pk_raises_on_exact_duplicates():
    dup = pl.DataFrame(
        [['000001.SZ', '20240110', '张三', 'G', 'IN', 1000.0, 0.5],
         ['000001.SZ', '20240110', '张三', 'G', 'IN', 1000.0, 0.5]],
        schema=['ts_code', 'ann_date', 'holder_name', 'holder_type', 'in_de',
                'change_vol', 'change_ratio'], orient='row',
    )
    with pytest.raises(RuntimeError, match='exact duplicate'):
        eb.assert_pk_unique(dup, ['ts_code', 'ann_date'], 't')


# --------------------------------------------------------------------------- #
# disclosure_shift
# --------------------------------------------------------------------------- #
def test_disclosure_shift_fields_and_chain_order():
    rows = [
        # same (ts_code, end_date) revised twice onto the same pre_date:
        # chain seq ordered by ann_date
        ['000001.SZ', '20240201', '20231231', '20240425', None],
        ['000001.SZ', '20240120', '20231231', '20240425', '20240425'],
        # different pre_date -> independent event
        ['000002.SZ', '20240115', '20231231', '20240330', '20240330'],
    ]
    raw = pl.DataFrame(
        rows, schema=['ts_code', 'ann_date', 'end_date', 'pre_date', 'actual_date'],
        orient='row',
    )
    events, stats = eb.build_disclosure(raw, 'tushare/disclosure_date/test', CAL)
    assert events.height == 3
    assert set(events['direction']) == {0}
    assert set(events['confidence']) == {'medium'}
    assert events['magnitude'][0] is None
    assert set(events['direction_source']) == {'field_enum'}
    assert stats['null_pre_date_dropped'] == 0
    same = events.filter(pl.col('ts_code') == '000001.SZ').sort('event_id')
    assert same['event_id'].to_list() == [
        'disclosure_shift.000001.SZ.20240425.1',
        'disclosure_shift.000001.SZ.20240425.2',
    ]
    assert same.sort('event_id')['ts_knowledge'].to_list() == [
        date(2024, 1, 20), date(2024, 2, 1),
    ]


# --------------------------------------------------------------------------- #
# ts_available rollover
# --------------------------------------------------------------------------- #
def test_ts_available_rollover_weekend_holiday_before_and_after():
    frame = pl.DataFrame(
        {
            'ts_knowledge': [
                date(2024, 1, 12),  # Fri -> Mon 15 (weekend)
                date(2024, 1, 10),  # Wed -> Fri 12 (Thu holiday)
                date(2024, 1, 13),  # Sat -> Mon 15
                date(2024, 1, 5),   # before calendar -> first day 01-08
                date(2024, 1, 17),  # calendar last day -> null
                date(2024, 1, 19),  # after calendar -> null
            ]
        }
    )
    out, stats = eb.compute_ts_available(frame, CAL)
    got = out['ts_available'].to_list()
    assert got[0] == date(2024, 1, 15)
    assert got[1] == date(2024, 1, 12)
    assert got[2] == date(2024, 1, 15)
    assert got[3] == date(2024, 1, 8)
    assert got[4] is None
    assert got[5] is None
    assert stats['knowledge_before_calendar_mapped_to_first_day'] == 1
    assert stats['available_beyond_calendar_null'] == 2


def test_ts_available_strictly_next_day():
    # knowledge ON a trading day -> strictly next trading day
    frame = pl.DataFrame({'ts_knowledge': [date(2024, 1, 8)]})
    out, _ = eb.compute_ts_available(frame, CAL)
    assert out['ts_available'][0] == date(2024, 1, 9)


# --------------------------------------------------------------------------- #
# freeze split
# --------------------------------------------------------------------------- #
def test_split_freeze_counts_out_of_bounds():
    frame = pl.DataFrame(
        {'ts_available': [date(2024, 12, 30), date(2024, 12, 31), None, date(2025, 1, 2)]}
    )
    keep, oob = eb.split_freeze(frame)
    assert keep.height == 2
    assert oob == 2


def test_end_to_end_freeze_on_express_builder():
    cal_dec = [date(2024, 12, 27), date(2024, 12, 30), date(2024, 12, 31)]
    rows = [
        # knowledge 20241228 (Sat) -> available 20241230: in bounds
        ['000001.SZ', '20241228', '20240930', 10.0],
        # knowledge 20241231 -> next trading day beyond calendar: out of bounds
        ['000002.SZ', '20241231', '20240930', -3.0],
    ]
    raw = pl.DataFrame(rows, schema=['ts_code', 'ann_date', 'end_date', 'yoy_net_profit'],
                       orient='row')
    events, stats = eb.build_express(raw, 'tushare/express/test', cal_dec)
    keep, oob = eb.split_freeze(events)
    assert keep.height == 1 and keep['ts_code'][0] == '000001.SZ'
    assert keep['ts_available'][0] == date(2024, 12, 30)
    assert oob == 1
    assert stats['available_beyond_calendar_null'] == 1


# --------------------------------------------------------------------------- #
# code normalisation + event_id uniqueness
# --------------------------------------------------------------------------- #
def test_standard_code_filter_counts_bj_and_nonstandard():
    raw = pl.DataFrame(
        [['000001.SZ'], ['830974.BJ'], ['400145'], ['600000.SH'], [None]],
        schema=['ts_code'], orient='row',
    )
    kept, stats = eb.filter_standard_codes(raw)
    assert kept['ts_code'].to_list() == ['000001.SZ', '600000.SH']
    assert stats['removed_bj'] == 1
    assert stats['removed_nonstandard'] == 2  # '400145' and null


def test_event_id_unique_across_families():
    rows = [
        _fc_row('000001.SZ', '20240110', '20231231', '预增', 50.0, 60.0, first='20240110'),
    ]
    fc, _ = eb.build_forecast(_frame(rows, FORECAST_COLS), 'tushare/forecast/test', CAL)
    ex, _ = eb.build_express(
        pl.DataFrame([['000001.SZ', '20240110', '20231231', 1.0]],
                     schema=['ts_code', 'ann_date', 'end_date', 'yoy_net_profit'],
                     orient='row'),
        'tushare/express/test', CAL,
    )
    common = [c for c in fc.columns if c in ex.columns]
    combined = pl.concat([fc.select(common), ex.select(common)])
    assert combined['event_id'].n_unique() == combined.height
    assert fc['event_id'][0] == 'forecast.000001.SZ.20231231.1'
    assert ex['event_id'][0] == 'express.000001.SZ.20231231.1'
    assert set(fc['in_pool'].to_list() if 'in_pool' in fc.columns else []) == set()
