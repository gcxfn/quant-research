"""Unit tests for src/quant/factors/fund_derive.py (R12/R13 fixes).

Every case is a synthetic hand-computed counter-example from the
2026-09-20 strategy review; no real data touched.
"""
from __future__ import annotations

from datetime import date as D

import polars as pl
import pytest

from quant.factors.fund_derive import (
    FundDeriveError,
    latest_revision,
    single_quarter_diff,
    yoy_pit,
)


def fin(rows):
    """rows: (symbol, end_date, signal_date, np_cum) -- np cumulative."""
    return pl.DataFrame({
        "symbol": [r[0] for r in rows],
        "end_date": [r[1] for r in rows],
        "signal_date": [r[2] for r in rows],
        "n_income_attr_p": [float(r[3]) for r in rows],
    }).with_columns(pl.col("end_date").cast(pl.Date),
                    pl.col("signal_date").cast(pl.Date))


def test_r12_q1_keeps_level_not_prior_year_annual():
    """Review counter-example: 2019 annual cumulative 200, 2020Q1
    cumulative 50 -> the Q1 single quarter is 50.  The old
    ``month != 1`` branch subtracted the 2019 annual and produced -150."""
    df = fin([
        ("sz.000001", D(2019, 9, 30), D(2019, 10, 26), 160.0),
        ("sz.000001", D(2019, 12, 31), D(2020, 3, 25), 200.0),
        ("sz.000001", D(2020, 3, 31), D(2020, 4, 28), 50.0),
        ("sz.000001", D(2020, 6, 30), D(2020, 8, 20), 120.0),
    ])
    out, rep = single_quarter_diff(df, ["n_income_attr_p"])
    q = out.sort("end_date")["n_income_attr_p_q"].to_list()
    # Q3 has no Q2 base -> null; Q4 = 200-160; Q1 = 50 (level!); Q2 = 70
    assert q == [None, 40.0, 50.0, 70.0]
    assert rep["n_q1"] == 1 and rep["n_broken_chain"] == 1
    # the OLD expression, reproduced inline, gives the wrong Q1 (-150)
    old = df.sort("end_date").with_columns(
        (pl.col("n_income_attr_p")
         - pl.col("n_income_attr_p").shift(1).over("symbol")
         * (pl.col("end_date").dt.month() != 1).cast(pl.Float64))
        .alias("_np_q"))["_np_q"].to_list()
    assert old[2] == -150.0             # the defect, pinned


def test_r12_broken_chain_yields_null_not_cross_year():
    """2020Q1 followed directly by 2020Q3 (Q2 missing): the Q3 diff is
    null and counted -- never 2020Q3 minus 2020Q1 across the gap, and
    never Q3 minus the 2019 annual."""
    df = fin([
        ("sz.000001", D(2020, 3, 31), D(2020, 4, 28), 50.0),
        ("sz.000001", D(2020, 9, 30), D(2020, 10, 27), 180.0),
        ("sz.000001", D(2020, 12, 31), D(2021, 3, 30), 260.0),
    ])
    out, rep = single_quarter_diff(df, ["n_income_attr_p"])
    q = out.sort("end_date")["n_income_attr_p_q"].to_list()
    assert q == [50.0, None, 80.0]      # Q4 = 260 - 180 (same-year)
    assert rep["n_broken_chain"] == 1


def test_r12_duplicate_keys_rejected():
    df = fin([
        ("sz.000001", D(2020, 3, 31), D(2020, 4, 28), 50.0),
        ("sz.000001", D(2020, 3, 31), D(2020, 5, 9), 52.0),   # revision
    ])
    with pytest.raises(FundDeriveError, match="latest_revision"):
        single_quarter_diff(df, ["n_income_attr_p"])
    dedup = latest_revision(df)
    out, _ = single_quarter_diff(dedup, ["n_income_attr_p"])
    assert out["n_income_attr_p_q"].to_list() == [52.0]


def test_r13_unseen_last_year_revision_links_null():
    """Review pattern (002939-shaped): current 2017 annual announced
    2018-09-17; the ONLY revision of the 2016 annual became visible
    2020-01-07.  The old join brought the value through; the PIT join
    must null it and count the block."""
    cur = fin([("sz.002939", D(2017, 12, 31), D(2018, 9, 17), 110.0)])
    ly = fin([("sz.002939", D(2016, 12, 31), D(2020, 1, 7), 120.0)])
    out, rep = yoy_pit(pl.concat([cur, ly]), ["n_income_attr_p"])
    row = out.filter(pl.col("end_date") == D(2017, 12, 31)).row(0, named=True)
    assert row["n_income_attr_p_ly"] is None
    assert row["_ly_signal_date"] is None
    assert rep["n_yoy_blocked_unseen"] == 1
    assert rep["n_yoy_linked"] == 0


def test_r13_asof_picks_the_revision_visible_then():
    """The 2016 annual has an original (2017-04-25 = 95) read by the
    2017-annual report (announced 2018-09-17).  The 2018 annual has an
    original (2019-04-25 = 100) and an amendment (2020-01-07 = 120):
    the 2019-annual report (announced 2020-04-28) must join the
    AMENDED value 120; an earlier report would have joined the 100."""
    cur = fin([
        ("sz.002939", D(2017, 12, 31), D(2018, 9, 17), 110.0),
        ("sz.002939", D(2019, 12, 31), D(2020, 4, 28), 130.0),
    ])
    ly = fin([
        ("sz.002939", D(2016, 12, 31), D(2017, 4, 25), 95.0),
        ("sz.002939", D(2018, 12, 31), D(2019, 4, 25), 100.0),
        ("sz.002939", D(2018, 12, 31), D(2020, 1, 7), 120.0),
    ])
    out, rep = yoy_pit(pl.concat([cur, ly]), ["n_income_attr_p"])
    r17 = out.filter(pl.col("end_date") == D(2017, 12, 31)).row(0, named=True)
    r19 = out.filter(pl.col("end_date") == D(2019, 12, 31)).row(0, named=True)
    assert r17["n_income_attr_p_ly"] == 95.0
    assert r17["_ly_signal_date"] == D(2017, 4, 25)
    assert r19["n_income_attr_p_ly"] == 120.0
    assert r19["_ly_signal_date"] == D(2020, 1, 7)
    # every input row is itself a "current report": the 2018-original
    # and 2018-amendment rows each link the 2017 annual (visible), the
    # 2016 annual has no 2015 counterpart -> linked 4 / missing 1
    assert rep["n_current_rows"] == 5
    assert rep["n_yoy_linked"] == 4
    assert rep["n_yoy_blocked_unseen"] == 0
    assert rep["n_yoy_missing"] == 1


def test_r13_missing_prior_year_counted():
    df = fin([("sz.300001", D(2020, 3, 31), D(2020, 4, 28), 50.0)])
    out, rep = yoy_pit(df, ["n_income_attr_p"])
    assert out["n_income_attr_p_ly"].to_list() == [None]
    assert rep["n_yoy_missing"] == 1


def test_non_quarter_end_rejected():
    df = fin([("sz.000001", D(2020, 5, 15), D(2020, 6, 1), 50.0)])
    with pytest.raises(FundDeriveError, match="quarter-end"):
        single_quarter_diff(df, ["n_income_attr_p"])
    with pytest.raises(FundDeriveError, match="quarter-end"):
        yoy_pit(df, ["n_income_attr_p"])
