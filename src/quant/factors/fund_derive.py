"""PIT financial derivation layer (R12/R13 fixes, 2026-09-20 review).

Repairs two defects found in the artifact-era ``build_d_fund_main.py``
(kept read-only under artifacts/runs/) and moves the corrected logic into
the shared package per the review's R4 recommendation:

- R12 -- single-quarter differencing.  The old code keyed the "keep the
  Q1 level" branch on ``end_date.month != 1``; a Q1 report period ends in
  month 3, so Q1 wrongly subtracted the prior-year ANNUAL cumulative
  (synthetic counter-example: 2019 annual 200, 2020Q1 cumulative 50 ->
  the old expression produced -150 instead of 50, poisoning D21 and the
  TTM chain).  :func:`single_quarter_diff` keys on the REPORT QUARTER
  (month 3 = Q1) and validates same-year quarter continuity; a broken
  chain yields null, never a silent cross-year subtraction.

- R13 -- year-over-year visibility.  The old join brought last year's
  VALUE without its ``signal_date``, so a current report could reference
  a last-year revision that was not yet public on the current
  announcement date (real pattern: 002939.SZ 2017 annual visible
  2018-09-17 while the 2016-annual revision it joined only became
  visible 2020-01-07).  :func:`yoy_pit` keeps every revision, resolves
  both the current and the last-year leg AS OF the current report's
  ``signal_date``, and nulls (and counts) the link when no last-year
  version was visible yet.

Input contract: columns ``symbol (str)``, ``end_date (Date)`` --
a quarter end (month 3/6/9/12) -- ``signal_date (Date)`` and the value
columns.  Rows may carry multiple revisions per (symbol, end_date)
for :func:`yoy_pit`; :func:`single_quarter_diff` requires uniqueness and
raises otherwise (deduplicate with :func:`latest_revision` first).
No calendar/freeze enforcement lives here -- callers pin the window.
"""

from __future__ import annotations

from typing import Any

import polars as pl

__all__ = [
    "FundDeriveError",
    "latest_revision",
    "single_quarter_diff",
    "yoy_pit",
]

_QUARTER_END_MONTHS = (3, 6, 9, 12)
_MONTH_LAST_DAY = {3: 31, 6: 30, 9: 30, 12: 31}


class FundDeriveError(ValueError):
    """Raised on contract violations (missing columns, duplicate keys)."""


def _deterministic_last(
    df: pl.DataFrame, keys: list[str], primary: list[str]
) -> pl.DataFrame:
    """Keep the lexicographically greatest row after explicit sorting.

    ``group_by().last()`` is only deterministic when the input order is part
    of the contract.  Raw financial files do not provide that contract, so
    equal primary keys are resolved by all remaining columns in name order.
    Exact duplicate rows therefore remain interchangeable, while different
    rows have a documented, reproducible winner.
    """
    tie = sorted(c for c in df.columns if c not in {*keys, *primary})
    order = [*keys, *primary, *tie]
    return df.sort(order, nulls_last=True).group_by(keys).last()


def _check_base(df: pl.DataFrame, extra: list[str]) -> None:
    need = ["symbol", "end_date", "signal_date"] + extra
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise FundDeriveError(f"missing column(s): {missing}")
    if df.schema["end_date"] != pl.Date or df.schema["signal_date"] != pl.Date:
        raise FundDeriveError("end_date/signal_date must have dtype Date")
    bad_month = df.filter(
        ~pl.col("end_date").dt.month().is_in(_QUARTER_END_MONTHS))
    if bad_month.height:
        raise FundDeriveError(
            f"{bad_month.height} row(s) with a non-quarter-end end_date "
            f"(e.g. {bad_month.select('symbol', 'end_date').head(3).to_dicts()})"
        )


def latest_revision(df: pl.DataFrame) -> pl.DataFrame:
    """One row per (symbol, end_date): the revision with the LATEST
    signal_date (amendments replace earlier reads).  Equal-date revisions
    use the lexicographically greatest remaining row as a deterministic
    tie-break; physical input order is never consulted."""
    return _deterministic_last(df, ["symbol", "end_date"], ["signal_date"])


def single_quarter_diff(
    df: pl.DataFrame, cols: list[str]
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Cumulative -> single-quarter values with R12 semantics.

    Q1 (end_date month 3): the cumulative IS the single quarter.  Q2/Q3/Q4:
    cumulative minus the SAME-YEAR previous quarter's cumulative, taken by
    row shift within symbol AND validated against the expected previous
    quarter-end date ((y, m-3) for months 6/9/12, (y-1, 12) for month 3
    is never subtracted).  A gap (missing quarter, delisting, first year
    of coverage) yields null and is counted, never a cross-year diff.

    Returns ``(df + '<col>'_q columns per input col, report)``.  The
    report carries n_rows / n_q1 / n_diff / n_broken_chain.
    """
    _check_base(df, cols)
    dup = df.group_by("symbol", "end_date").len().filter(pl.col("len") > 1)
    if dup.height:
        raise FundDeriveError(
            f"{dup.height} (symbol, end_date) key(s) have multiple rows; "
            "deduplicate with latest_revision() before differencing "
            f"(e.g. {dup.head(3).to_dicts()})"
        )
    out = df.sort("symbol", "end_date").with_columns(
        pl.col("end_date").dt.year().alias("_y"),
        pl.col("end_date").dt.month().alias("_m"),
        pl.col("end_date").shift(1).over("symbol").alias("_prev_end"),
    )
    # expected previous quarter end for months 6/9/12 (month 3 keeps level)
    prev_month = (pl.when(pl.col("_m") == 3).then(pl.lit(None, dtype=pl.Int32))
                  .otherwise(pl.col("_m") - 3))
    prev_year = (pl.when(pl.col("_m") == 3).then(pl.lit(None, dtype=pl.Int32))
                 .otherwise(pl.col("_y")))
    out = out.with_columns(
        pl.date(prev_year, prev_month,
                pl.when(prev_month == 3).then(pl.lit(31))
                .when(prev_month == 6).then(pl.lit(30))
                .when(prev_month == 9).then(pl.lit(30))
                .otherwise(pl.lit(31))).alias("_expected_prev_end"))
    exprs = []
    for c in cols:
        prev_val = pl.col(c).shift(1).over("symbol")
        exprs.append(
            pl.when(pl.col("_m") == 3)
            .then(pl.col(c))
            .when(pl.col("_prev_end") == pl.col("_expected_prev_end"))
            .then(pl.col(c) - prev_val)
            .otherwise(None)
            .alias(c + "_q"))
    out = out.with_columns(exprs)
    # a null prev_end (first row of a symbol) compares as null in Polars
    # -- fill to True so the gap is counted, never silently differenced
    n_broken = int(out.select(
        ((pl.col("_m") != 3)
         & (pl.col("_prev_end") != pl.col("_expected_prev_end"))
         .fill_null(True)).sum()
    ).item() or 0)
    report = {
        "n_rows": out.height,
        "n_q1": int((out["_m"] == 3).sum()),
        "n_diff": int(
            ((out["_m"] != 3)
             & (out["_prev_end"] == out["_expected_prev_end"])).sum()),
        "n_broken_chain": n_broken,
        "caliber": "Q1 keeps the cumulative level; Q2-Q4 subtract the "
                   "same-year previous quarter's cumulative; a gap yields "
                   "null (R12: the old month!=1 branch wrongly subtracted "
                   "the prior-year annual from Q1)",
    }
    return out.drop("_y", "_m", "_prev_end", "_expected_prev_end"), report


def yoy_pit(
    df: pl.DataFrame, value_cols: list[str]
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Point-in-time year-over-year join with R13 visibility.

    Input MAY carry multiple revisions per (symbol, end_date) -- keep
    them all; the revision history is exactly what makes an as-of join
    possible.  For every row (taken as "current report announced at its
    signal_date"):

    - current leg: the latest revision of the SAME (symbol, end_date)
      with ``signal_date <=`` the row's own signal_date (for single-
      revision inputs this is the row itself);
    - last-year leg: the latest revision of (symbol, end_date one year
      earlier) with ``signal_date <=`` the row's signal_date.

    The last-year value is NULL when no revision was visible yet
    (counted as ``n_yoy_blocked_unseen`` -- the exact hole the old join
    had) and when the symbol simply has no prior-year report
    (``n_yoy_missing``).  Output columns: the inputs plus
    ``<col>_ly`` per value col and ``_ly_signal_date`` (the announcement
    date of the linked last-year revision, for auditing).
    """
    _check_base(df, value_cols)
    has_ly = (
        pl.date(pl.col("end_date").dt.year() + 1,
                pl.col("end_date").dt.month(),
                pl.col("end_date").dt.day()).alias("_ly_end"))
    ly_pool = df.with_columns(has_ly).select(
        "symbol", "_ly_end",
        pl.col("signal_date").alias("_ly_asof"),
        *[pl.col(c).alias("_ly_" + c) for c in value_cols])
    # Multiple source rows can share the same as-of date.  Resolve that
    # collision before the join; otherwise the later aggregation would again
    # depend on the physical order of the input revision file.
    ly_pool = _deterministic_last(
        ly_pool, ["symbol", "_ly_end", "_ly_asof"], []
    )
    j = df.join(
        ly_pool,
        left_on=["symbol", "end_date"],
        right_on=["symbol", "_ly_end"],
        how="left",
    ).sort("symbol", "signal_date", "_ly_asof", nulls_last=True)
    visible = pl.col("_ly_asof") <= pl.col("signal_date")
    agg_exprs = []
    for c in value_cols:
        agg_exprs.append(
            pl.col("_ly_" + c).filter(visible).last().alias(c + "_ly"))
    agg_exprs += [
        pl.col("_ly_asof").filter(visible).max().alias("_ly_signal_date"),
        pl.col("_ly_asof").max().alias("_ly_any_asof"),
    ]
    ly = j.group_by("symbol", "end_date", "signal_date",
                    maintain_order=True).agg(*agg_exprs)
    out = df.join(
        ly, on=["symbol", "end_date", "signal_date"], how="left")
    blocked = out.filter(
        pl.col("_ly_signal_date").is_null() & pl.col("_ly_any_asof").is_not_null())
    missing = out.filter(pl.col("_ly_any_asof").is_null())
    report = {
        "n_current_rows": out.height,
        "n_yoy_linked": int(out["_ly_signal_date"].is_not_null().sum()),
        "n_yoy_blocked_unseen": blocked.height,
        "n_yoy_missing": missing.height,
        "caliber": "both legs resolved AS OF the current report's "
                   "signal_date over the full revision history; an "
                   "invisible last-year revision links NULL (R13: the "
                   "old join ignored last year's signal_date entirely)",
    }
    return out.drop("_ly_any_asof"), report
