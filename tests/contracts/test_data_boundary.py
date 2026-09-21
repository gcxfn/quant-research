"""Freeze boundary and historical data reading contracts."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from quant.data.baostock_daily import (  # noqa: E402
    FREEZE_END,
    DailyLoader,
    daily_dataset_id,
    sample_universe,
)

ROOT = Path(__file__).resolve().parents[2]


def _make_csv(path: Path, code: str, dates: list[str], *, st_flags: list[float] | None = None) -> None:
    header = 'date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST\n'
    rows = []
    for i, day in enumerate(dates):
        st = '' if st_flags is None else str(st_flags[i])
        rows.append(f'{day},{code},10.0,10.5,9.8,10.2,10.1,100000,1020000,3,1.2,1,2.0,{st}\n')
    path.write_text(header + ''.join(rows), encoding='utf-8')


@pytest.fixture()
def fake_daily_root(tmp_path):
    daily = tmp_path / 'data/raw/baostock/daily'
    daily.mkdir(parents=True)
    _make_csv(daily / 'sh.600000.csv', 'sh.600000',
              ['2022-01-04', '2022-01-05', '2025-01-02'])
    _make_csv(daily / 'sh.600001.csv', 'sh.600001', ['2022-01-04', '2022-01-05'])
    _make_csv(daily / 'sh.688001.csv', 'sh.688001',
              ['2022-01-04', '2025-01-02'])
    _make_csv(daily / 'sz.000001.csv', 'sz.000001',
              ['2022-01-04', '2022-01-05', '2024-12-31', '2025-01-02'],
              st_flags=[0, 0, 1, 0])
    return tmp_path


def test_loader_enforces_freeze(fake_daily_root):
    daily = DailyLoader(fake_daily_root).load(['sh.600000'])
    assert daily['date'].max() <= FREEZE_END
    assert date(2025, 1, 2) not in daily['date'].to_list()


def test_loader_keeps_null_flags(fake_daily_root):
    daily = DailyLoader(fake_daily_root).load(['sh.600000'])
    assert daily['isST'].is_null().all()


def test_loader_reads_st_flags(fake_daily_root):
    daily = DailyLoader(fake_daily_root).load(['sz.000001'])
    row = daily.filter(pl.col('date') == date(2024, 12, 31))
    assert row['isST'].to_list() == [1.0]


def test_sample_universe_deterministic_and_excludes_boards(fake_daily_root):
    codes = sample_universe(fake_daily_root, size=10, stride=1)
    # 600001 lacks required end coverage; 688 excluded by board; 000001 passes
    assert codes == ['sh.600000', 'sz.000001']
    again = sample_universe(fake_daily_root, size=10, stride=1)
    assert codes == again


def test_daily_dataset_id_deterministic_and_sensitive(fake_daily_root):
    daily = DailyLoader(fake_daily_root).load(['sh.600000', 'sz.000001'])
    id1, sha1 = daily_dataset_id(daily)
    id2, sha2 = daily_dataset_id(daily)
    assert id1 == id2 == 'baostock-daily'
    assert sha1 == sha2
    # order of symbols must not matter
    id3, sha3 = daily_dataset_id(daily.sort('symbol', descending=True))
    assert sha3 == sha1
    # content change must change identity
    changed = daily.with_columns(
        pl.when(pl.col('date') == date(2022, 1, 4)).then(99.0).otherwise(pl.col('close')).alias('close'))
    _, sha4 = daily_dataset_id(changed)
    assert sha4 != sha1


def test_sample_universe_real_scale_smoke():
    root = Path(__file__).resolve().parents[2]
    if not (root / 'data/raw/baostock/daily').is_dir():
        pytest.skip('raw data not available')
    codes = sample_universe(root, size=200, stride=20)
    assert len(codes) == 200
    assert len(set(codes)) == 200
    assert not any(c.startswith('sh.688') or c.startswith('sh.689') for c in codes)


def test_loader_real_sample_boundary_and_scale():
    root = Path(__file__).resolve().parents[2]
    if not (root / 'data/raw/baostock/daily').is_dir():
        pytest.skip('raw data not available')
    codes = sample_universe(root, size=200, stride=20)
    daily = DailyLoader(root).load(codes)
    # per-code rows exceed 726 because files start at 1999; freeze filter only
    # bounds the top. Row identity, not a fixed total, is the contract here.
    assert daily.height >= 200 * 726
    assert daily['date'].max() == FREEZE_END
    assert daily.select(pl.col('symbol').n_unique()).item() == 200
    assert daily.select(pl.struct('symbol', 'date').is_duplicated().any()).item() is False
