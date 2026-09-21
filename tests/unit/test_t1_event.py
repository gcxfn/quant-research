"""Unit tests for src/quant/research/t1_event.py (R1/R2 fixes).

Synthetic counter-examples from the 2026-09-20 strategy review.
"""
from __future__ import annotations

from datetime import date as D

import numpy as np
import polars as pl
import pytest

from quant.research.t1_event import (
    drop_label_breach,
    label_window,
    nested_f_test,
)


def chain_frame(rows):
    return pl.DataFrame({
        "symbol": [r[0] for r in rows],
        "date": [r[1] for r in rows],
    }).with_columns(pl.col("date").cast(pl.Date))


def events_frame(rows):
    return pl.DataFrame({
        "symbol": [r[0] for r in rows],
        "signal_date": [r[1] for r in rows],
    }).with_columns(pl.col("signal_date").cast(pl.Date))


# --- R1 ----------------------------------------------------------------------

def test_r1_label_window_endpoints():
    """5-day chain; a signal on row 2 with horizon 3 has its window on
    rows 3..5: label_start = row 3, label_end = row 5 (the last return
    leg).  Windows never include the signal day itself."""
    days = [D(2020, 12, d) for d in (1, 2, 3, 4, 7)]
    chain = chain_frame([("sh.600001", d) for d in days]
                        + [("sh.600002", d) for d in days])
    ev = events_frame([("sh.600001", days[1])])
    out, rep = label_window(ev, chain, horizon=3)
    row = out.row(0, named=True)
    assert row["label_start"] == days[2]
    assert row["label_end"] == days[4]
    assert rep["n_no_signal_row"] == 0 and rep["n_truncated_window"] == 0


def test_r1_truncated_window_is_null_counted():
    days = [D(2020, 12, d) for d in (1, 2, 3, 4)]
    chain = chain_frame([("sh.600001", d) for d in days])
    ev = events_frame([("sh.600001", days[1])])
    out, rep = label_window(ev, chain, horizon=3)   # only 2 rows remain
    row = out.row(0, named=True)
    assert row["label_start"] == days[2]
    assert row["label_end"] is None
    assert rep["n_truncated_window"] == 1


def test_r1_signal_not_in_chain_counts_missing():
    """A signal date that the chain policy filtered out (halt/ST) cannot
    define a window: counted as n_no_signal_row, label columns null."""
    days = [D(2020, 12, d) for d in (1, 2, 3, 4, 7)]
    chain = chain_frame([("sh.600001", d) for d in days
                         if d != days[1]])            # signal day filtered
    ev = events_frame([("sh.600001", days[1])])
    out, rep = label_window(ev, chain, horizon=2)
    assert out["label_start"].to_list() == [None]
    assert out["label_end"].to_list() == [None]
    assert rep["n_no_signal_row"] == 1


def test_r1_boundary_gate_drops_crossing_labels():
    """The review's 53-event class in miniature: dev boundary 2020-12-31.
    A 2020-12-30 signal whose 3-day label ends 2021-01-05 crosses the
    boundary and MUST be dropped; the 2020-12-15 signal ending
    2020-12-30 stays; a 2021 signal is dropped on its own date."""
    days_a = [D(2020, 12, d) for d in (10, 15, 16, 17, 18)]
    days_b = [D(2020, 12, d) for d in (28, 29, 30, 31)] + [D(2021, 1, 4, )]
    chain = chain_frame([("sh.600001", d) for d in days_a]
                        + [("sh.600002", d) for d in days_b])
    ev = events_frame([
        ("sh.600001", D(2020, 12, 15)),   # window 16/17/18 -> kept
        ("sh.600002", D(2020, 12, 30)),   # window 31, 01-04, missing -> truncated
    ])
    win, _ = label_window(ev, chain, horizon=3)
    kept, rep = drop_label_breach(win, D(2020, 12, 31))
    assert kept["symbol"].to_list() == ["sh.600001"]
    assert rep["n_kept"] == 1 and rep["n_dropped"] == 1
    assert rep["n_dropped_signal_after"] == 0
    assert rep["n_dropped_label_after_or_missing"] == 1
    assert rep["max_label_end_kept"] == "2020-12-18"
    # a genuinely label-crossing event (not merely truncated)
    days_c = [D(2020, 12, d) for d in (29, 30, 31)] + [D(2021, 1, 4, ),
                                                       D(2021, 1, 5)]
    chain2 = chain_frame([("sh.600003", d) for d in days_c])
    ev2 = events_frame([("sh.600003", D(2020, 12, 30))])
    win2, _ = label_window(ev2, chain2, horizon=3)
    assert win2["label_end"][0] == D(2021, 1, 5)      # crosses the boundary
    kept2, rep2 = drop_label_breach(win2, D(2020, 12, 31))
    assert kept2.height == 0 and rep2["n_dropped"] == 1


def test_r1_windows_do_not_leak_across_symbols():
    days = [D(2020, 12, d) for d in (1, 2, 3)]
    chain = chain_frame([("sh.600001", days[0])]
                        + [("sh.600002", d) for d in days])
    ev = events_frame([("sh.600002", days[0])])
    out, _ = label_window(ev, chain, horizon=2)
    row = out.row(0, named=True)
    assert row["label_start"] == days[1]
    assert row["label_end"] == days[2]


# --- R2 ----------------------------------------------------------------------

def _review_world(n_copies: int = 3, cat_effect: float = 0.0, seed: int = 7):
    """month x type cell counts 3/1/1/3 per copy, y = month + type +
    independent fixed-seed noise (+ an optional category effect).
    Categories are drawn independently of the cells.  Returns
    (y, month, type, cat)."""
    rng = np.random.default_rng(seed)
    cells = ([("M1", "T1")] * 3 + [("M1", "T2")]
             + [("M2", "T1")] + [("M2", "T2")] * 3)
    y, mo, ty, ca = [], [], [], []
    for _ in range(n_copies):
        for m, t in cells:
            cat = rng.choice(["A", "B", "C"])
            y.append(1.0 * (m == "M2") + 0.5 * (t == "T2")
                     + rng.normal(0.0, 0.05) + cat_effect * (cat == "C"))
            mo.append(m)
            ty.append(t)
            ca.append(str(cat))
    return (np.array(y), np.array(mo), np.array(ty), np.array(ca))


def test_r2_sequential_demeaning_leaves_month_residue():
    """The review's 8-row counter-example: subtracting month means then
    type means re-introduces month differences.  Pinned (fixed eps) so
    the OLD pipeline's defect is executable documentation."""
    eps = [0.01, -0.02, 0.03, 0.00, 0.02, -0.01, 0.04, -0.03]
    mo = ["M1"] * 4 + ["M2"] * 4
    ty = ["T1", "T1", "T1", "T2", "T1", "T2", "T2", "T2"]
    y = [1.0 * (m == "M2") + 0.5 * (t == "T2") + e
         for m, t, e in zip(mo, ty, eps)]
    df = pl.DataFrame({"y": y, "month": mo, "type": ty})
    df = df.with_columns(
        (pl.col("y") - pl.col("y").mean().over("month")).alias("a1"))
    df = df.with_columns(
        (pl.col("a1") - pl.col("a1").mean().over("type")).alias("y_wd"))
    mm = df.group_by("month").agg(m=pl.col("y_wd").mean()).sort("month")
    vals = mm["m"].to_list()
    assert abs(vals[0] - vals[1]) > 0.05      # month residue survives


def test_r2_joint_control_no_fake_category_effect():
    """Joint least squares on [month, type] absorbs both factors
    simultaneously; the incremental F for a category that carries NO
    effect must not reject (the old sequential pipeline could)."""
    y, mo, ty, ca = _review_world(n_copies=3, cat_effect=0.0)
    res = nested_f_test(y, [mo, ty], ca)
    # the full model's residual is at the noise floor (24 x N(0, .05)^2)
    assert res["ssr_full"] < 0.2
    assert res["df1"] >= 1 and res["df2"] >= 10
    assert res["p"] > 0.05                     # no fake category signal


def test_r2_detects_a_real_category_effect():
    """Power check: a +1.5 effect on category C with the same noise must
    be detected (p << 0.05) -- the fix must not merely never reject."""
    y0, mo, ty, ca = _review_world(n_copies=3, cat_effect=0.0)
    y1, *_ = _review_world(n_copies=3, cat_effect=1.5)
    res = nested_f_test(y1, [mo, ty], ca)
    assert res["p"] < 0.05
    # sanity: the same effect on the NULL world is absent
    res0 = nested_f_test(y0, [mo, ty], ca)
    assert res["F"] > res0["F"]


def test_r2_degrees_of_freedom_follow_actual_ranks():
    """df1/df2 come from matrix ranks, not level counts: dropping one
    month level (fewer rows) shrinks df2 exactly by the row count while
    df1 (category rank increment) stays the same."""
    y, mo, ty, ca = _review_world(n_copies=3, cat_effect=0.0)
    full = nested_f_test(y, [mo, ty], ca)
    y2, mo2, ty2, ca2 = _review_world(n_copies=2, cat_effect=0.0)
    two = nested_f_test(y2, [mo2, ty2], ca2)
    assert full["df1"] == two["df1"]
    assert full["df2"] == two["df2"] + 8
    assert full["n"] == 24 and two["n"] == 16


def test_r2_degenerate_design_raises():
    y = np.arange(6, dtype=float)
    g = np.array(["a", "b", "c", "a", "b", "c"])
    h = np.array(["x", "y", "z", "x", "y", "z"])
    # h duplicates g's partition exactly -> adds no rank
    with pytest.raises(ValueError, match="degenerate"):
        nested_f_test(y, [g], h)
