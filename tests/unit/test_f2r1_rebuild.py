from datetime import date as D
from pathlib import Path

import polars as pl
import pytest

from quant.research.f2r1_rebuild import (
    F2R1RebuildError,
    rebuild_e16,
    rebuild_financial_derivation,
    write_rebuild_run,
)


def _financial():
    return pl.DataFrame({
        "ts_code": ["000001.SZ"] * 5,
        "ann_date": ["20190401", "20200401", "20200720", "20210401", "20200401"],
        "end_date": ["20190331", "20200331", "20200630", "20210331", "20200331"],
        "n_income_attr_p": [90.0, 50.0, 120.0, 70.0, 52.0],
    })


def test_financial_path_calls_shared_derivers(monkeypatch):
    from quant.factors import fund_derive

    calls = {"latest": 0, "quarter": 0, "yoy": 0}
    latest = fund_derive.latest_revision
    quarter = fund_derive.single_quarter_diff
    yoy = fund_derive.yoy_pit
    monkeypatch.setattr(fund_derive, "latest_revision", lambda df: (calls.__setitem__("latest", calls["latest"] + 1) or latest(df)))
    monkeypatch.setattr(fund_derive, "single_quarter_diff", lambda df, cols: (calls.__setitem__("quarter", calls["quarter"] + 1) or quarter(df, cols)))
    monkeypatch.setattr(fund_derive, "yoy_pit", lambda df, cols: (calls.__setitem__("yoy", calls["yoy"] + 1) or yoy(df, cols)))
    out, report = rebuild_financial_derivation(
        {"fina": _financial()}, cumulative_columns=["n_income_attr_p"],
        yoy_columns=["n_income_attr_p"], signal_end=D(2020, 12, 31),
    )
    assert calls == {"latest": 1, "quarter": 1, "yoy": 1}
    assert out.filter(pl.col("end_date") == D(2020, 3, 31))["n_income_attr_p_q"].item() == 52.0
    assert report["quarter"]["n_q1"] == 2


def test_e16_deduplicates_event_before_365_day_sum():
    div = pl.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
        "ex_date": ["20200115", "20200115", "20180101"],
        "cash_div": [1.0, 1.0, 9.0],
    })
    panel = pl.DataFrame({
        "date": [D(2020, 12, 31)], "symbol": ["sz.000001"], "close": [10.0],
    }, schema_overrides={"date": pl.Date})
    out, report = rebuild_e16(div, panel, signal_end=D(2020, 12, 31))
    assert out["value"].item() == pytest.approx(0.1)
    assert report["input_rows"] == 3 and report["deduplicated_events"] == 2


def test_e16_resolves_conflicting_values_by_latest_announcement():
    div = pl.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ"],
        "ann_date": ["20200101", "20200110"],
        "ex_date": ["20200115", "20200115"],
        "cash_div": [1.0, 2.0],
    })
    panel = pl.DataFrame({
        "date": [D(2020, 12, 31)], "symbol": ["sz.000001"], "close": [10.0],
    }, schema_overrides={"date": pl.Date})
    out, report = rebuild_e16(div, panel, signal_end=D(2020, 12, 31))
    assert out["value"].item() == pytest.approx(0.2)
    assert report["conflicting_events_resolved"] == 1


def test_rejects_2025_inputs_and_does_not_write_run(tmp_path: Path):
    future = _financial().with_columns(pl.lit("20250101").alias("ann_date"))
    with pytest.raises(F2R1RebuildError, match="2025|2024"):
        rebuild_financial_derivation({"fina": future}, cumulative_columns=[], yoy_columns=[])
    assert not (tmp_path / "artifacts").exists()


def test_run_output_is_unique_and_preserves_existing(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# x\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    first = write_rebuild_run(repo_root=tmp_path, artifacts_root=tmp_path / "artifacts",
                              config={"experiment_id": "exp-test"})
    marker = first / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    second = write_rebuild_run(repo_root=tmp_path, artifacts_root=tmp_path / "artifacts",
                               config={"experiment_id": "exp-test"})
    assert second != first and marker.read_text(encoding="utf-8") == "keep"
