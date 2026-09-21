"""Fee recost contract tests on synthetic saved events with hand-checked values.

Pins the recost semantics: the original schedule must reproduce the saved
fees before any re-pricing, quantities/notionals stay frozen, the dev /
validation split follows the signal date, non-completed rows are dropped and
fund-like symbols are rejected.  Synthetic frames are contract data only.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quant.research.screen import FeeBand, fee_band_for  # noqa: E402
from quant.research.fee_recost import (  # noqa: E402
    FeeRecostError,
    recost_events,
    summarize,
    window_for,
)

D = date

OLD_SCHEDULE = (
    FeeBand(D(2015, 1, 1), 0.0003, 5.0, 0.001),
    FeeBand(D(2020, 1, 1), 0.0002, 5.0, 0.001),
    FeeBand(D(2022, 1, 1), 0.00015, 5.0, 0.001),
    FeeBand(D(2023, 8, 28), 0.00015, 5.0, 0.0005),
)
# Target: user account actuals (stock): 0.025% min 5 both legs, 0.05% stamp.
TARGET_SCHEDULE = (FeeBand(D(2015, 1, 1), 0.00025, 5.0, 0.0005),)


def event_row(symbol: str, signal: date, entry: date, exit_: date, *,
              gross: float, entry_notional: float, config: str = 'cfg-h5',
              status: str = 'completed_label') -> dict:
    exit_notional = entry_notional * (1.0 + gross)
    buy_band = fee_band_for(OLD_SCHEDULE, entry)
    sell_band = fee_band_for(OLD_SCHEDULE, exit_)
    buy_fee = max(entry_notional * buy_band.commission_pct, 5.0)
    sell_fee = (max(exit_notional * sell_band.commission_pct, 5.0)
                + exit_notional * sell_band.stamp_sell_pct)
    net = (exit_notional - sell_fee) / (entry_notional + buy_fee) - 1.0
    return {
        'symbol': symbol, 'signal_date': signal, 'status': status,
        'entry_date': entry, 'exit_date': exit_, 'gross_return': gross,
        'net_return_pct': net * 100.0, 'quantity': 100,
        'entry_notional': entry_notional, 'buy_fee': buy_fee,
        'exit_notional': exit_notional, 'sell_fee': sell_fee,
        'config_id': config, 'signal_set': 'sig', 'hold': 5,
    }


def events_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col('signal_date'), pl.col('entry_date'), pl.col('exit_date'))


def test_window_split_by_signal_date():
    assert window_for(D(2015, 1, 5)) == 'dev'
    assert window_for(D(2020, 12, 31)) == 'dev'
    assert window_for(D(2021, 1, 1)) == 'validation'


def test_recost_hand_checked_values():
    # Trade A: full-budget 2019 trade; old band 3bp + 0.1% stamp.
    # old: buy max(50000*3bp,5)=15, sell max(51000*3bp,5)+51=66.3
    # old net = 50933.7/50015-1 = 0.018368489...
    # new: buy max(50000*2.5bp,5)=12.5, sell 12.75+25.5=38.25
    # new net = 50961.75/50012.5-1 = 0.0189802549...
    a = event_row('sh.600000', D(2019, 6, 2), D(2019, 6, 3), D(2019, 6, 10),
                  gross=0.02, entry_notional=50_000.0)
    # Trade B: 8k notional (min commission binds on both legs), dev signal,
    # exit in 2021 under the 2020 band (2bp + 0.1%).
    # old: buy 5, sell 5+7.6=12.6 -> net 7587.4/8005-1 = -0.0521673954...
    # new: buy 5, sell 5+3.8=8.8 -> net 7591.2/8005-1 = -0.0516926921...
    b = event_row('sz.000001', D(2020, 12, 30), D(2020, 12, 31),
                  D(2021, 1, 5), gross=-0.05, entry_notional=8_000.0)
    # Blocked rows are dropped by the recost.
    c = event_row('sz.000002', D(2019, 6, 2), D(2019, 6, 3), D(2019, 6, 10),
                  gross=0.01, entry_notional=50_000.0,
                  status='entry_limit_up')
    frame = events_frame([a, b, c])
    out = recost_events(frame, run_tag='t', old_schedule=OLD_SCHEDULE,
                        target_schedule=TARGET_SCHEDULE)
    assert out.height == 2
    row_a = out.filter(pl.col('symbol') == 'sh.600000').row(0, named=True)
    assert row_a['window'] == 'dev'
    assert row_a['buy_fee_old'] == pytest.approx(15.0)
    assert row_a['sell_fee_old'] == pytest.approx(66.3)
    assert row_a['net_old'] == pytest.approx(0.0183684894, abs=1e-9)
    assert row_a['buy_fee_new'] == pytest.approx(12.5)
    assert row_a['sell_fee_new'] == pytest.approx(38.25)
    assert row_a['net_new'] == pytest.approx(0.0189802549, abs=1e-9)
    row_b = out.filter(pl.col('symbol') == 'sz.000001').row(0, named=True)
    assert row_b['window'] == 'dev'  # split by signal date, not exit date
    assert row_b['sell_fee_old'] == pytest.approx(12.6)
    assert row_b['net_old'] == pytest.approx(-0.0521673954, abs=1e-9)
    assert row_b['sell_fee_new'] == pytest.approx(8.8)
    assert row_b['net_new'] == pytest.approx(-0.0516926921, abs=1e-9)
    assert row_b['net_diff'] == pytest.approx(row_b['net_new']
                                              - row_b['net_old'])


def test_recost_validation_row_and_summary():
    a = event_row('sh.600000', D(2021, 6, 1), D(2021, 6, 2), D(2021, 6, 9),
                  gross=0.03, entry_notional=50_000.0, config='cfg-h3')
    out = recost_events(events_frame([a]), run_tag='t',
                        old_schedule=OLD_SCHEDULE,
                        target_schedule=TARGET_SCHEDULE)
    assert out['window'].to_list() == ['validation']
    # 2021 old band: 2bp commission, 0.1% stamp; new: 2.5bp, 0.05%.
    summary = summarize(out)
    assert summary.height == 1
    row = summary.row(0, named=True)
    assert row['n_completed'] == 1
    # old sell = 15+51.5=... entry 50000*1.03=51500; buy max(10,5)=10;
    # sell max(10.3,5)+51.5=61.8; net=51438.2/50010-1=0.02856...
    assert row['mean_net_old_pct'] == pytest.approx(
        ((51500.0 - 61.8) / 50010.0 - 1.0) * 100.0, abs=1e-9)
    # new: buy 12.5, sell 12.875+25.75=38.625
    assert row['mean_net_new_pct'] == pytest.approx(
        ((51500.0 - 38.625) / 50012.5 - 1.0) * 100.0, abs=1e-9)
    assert row['mean_net_new_pct'] > row['mean_net_old_pct']


def test_recost_rejects_tampered_saved_fees():
    row = event_row('sh.600000', D(2019, 6, 2), D(2019, 6, 3), D(2019, 6, 10),
                    gross=0.02, entry_notional=50_000.0)
    row['buy_fee'] = row['buy_fee'] + 1.0
    with pytest.raises(FeeRecostError, match='do not reproduce'):
        recost_events(events_frame([row]), run_tag='t',
                      old_schedule=OLD_SCHEDULE,
                      target_schedule=TARGET_SCHEDULE)


def test_recost_rejects_fund_symbols():
    row = event_row('sh.510300', D(2019, 6, 2), D(2019, 6, 3), D(2019, 6, 10),
                    gross=0.02, entry_notional=50_000.0)
    with pytest.raises(FeeRecostError, match='fund/ETF'):
        recost_events(events_frame([row]), run_tag='t',
                      old_schedule=OLD_SCHEDULE,
                      target_schedule=TARGET_SCHEDULE)
