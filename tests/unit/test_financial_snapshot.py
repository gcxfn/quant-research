from datetime import date as D

import polars as pl
import pytest

from quant.research.financial_snapshot import (
    FinancialSnapshotError,
    development_snapshot,
)


def test_snapshot_derives_signal_date_and_reports_discarded_rows():
    raw = pl.DataFrame({
        "id": ["old", "dev", "val", "unknown"],
        "ann_date": ["20191201", "20201220", "20210101", None],
        "end_date": ["20190930", "20200930", "20201231", None],
        "value": [1.0, 2.0, 3.0, 4.0],
    })
    out, report = development_snapshot(raw, dev_end=D(2020, 12, 31))
    assert out["id"].to_list() == ["old", "dev"]
    assert out.schema["signal_date"] == pl.Date
    assert report["total_rows"] == 4
    assert report["kept_rows"] == 2
    assert report["dropped_rows"] == 2
    assert report["dropped_after_dev_end"] == 1
    assert report["dropped_missing_signal_date"] == 1


def test_snapshot_filters_2025_before_returning_data():
    raw = pl.DataFrame({
        "signal_date": ["20250101"], "value": [1.0],
    })
    out, report = development_snapshot(raw)
    assert out.height == 0
    assert report["dropped_after_freeze_end"] == 1


def test_snapshot_accepts_date_typed_mixed_columns():
    raw = pl.DataFrame({
        "signal_date": [D(2020, 1, 2), D(2021, 1, 2)],
        "end_date": [D(2019, 12, 31), D(2020, 12, 31)],
    }, schema_overrides={"signal_date": pl.Date, "end_date": pl.Date})
    out, report = development_snapshot(raw)
    assert out.height == 1
    assert report["dropped_after_dev_end"] == 1
