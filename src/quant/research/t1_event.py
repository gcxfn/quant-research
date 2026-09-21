"""T1 event-study label & statistics layer (R1/R2 fixes, 2026-09-20 review).

Repairs two defects found in the artifact-era ``run_t1_event.py`` (kept
read-only under artifacts/runs/) and moves the corrected logic into the
shared package per the review's R4 recommendation:

- R1 -- label-window honesty.  The old run filtered ANNOUNCEMENT dates to
  the dev window (<= 2020-12-31) but chained forward returns to 2024, so
  53 of 6,656 analysis events carried labels ending past the boundary
  (max 2024-09-10) while the study claimed "zero validation-period
  contact".  :func:`label_window` makes the window EXPLICIT
  (``label_start`` / ``label_end`` per event over a caller-supplied
  trading chain) and :func:`drop_label_breach` removes any event whose
  label end crosses the boundary -- no suspension carve-out: the chain
  holds trading rows only, so a year-crossing suspension window simply
  ends later and is dropped the same way.

- R2 -- simultaneous control.  The old run subtracted month means, then
  type means (re-introducing month differences; residual month means up
  to ~0.9pp) and ran a plain one-way ANOVA with n-k degrees of freedom.
  :func:`nested_f_test` compares two NESTED least-squares models --
  reduced ``y ~ blocks`` vs full ``y ~ blocks + test`` -- with degrees
  of freedom taken from the ACTUAL design-matrix ranks, giving the
  incremental F for the test factor after the blocks are controlled
  simultaneously.

No data access lives here -- pure frame/array logic, synthetic-testable.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from scipy import stats

__all__ = ["label_window", "drop_label_breach", "nested_f_test"]


# ---------------------------------------------------------------------------
# R1: explicit label windows
# ---------------------------------------------------------------------------

def label_window(
    events: pl.DataFrame,
    chain: pl.DataFrame,
    horizon: int,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """Attach ``label_start`` / ``label_end`` to each event.

    ``events`` needs ``symbol`` + a signal-date column (``signal_col``,
    default ``signal_date``).  ``chain`` is the realized-return chain the
    study defines (any filter policy -- trading rows, non-ST rows, the
    caller's own universe) with columns ``symbol``/``date`` and one row
    per chain step.  The label window is the ``horizon`` chain rows
    STRICTLY AFTER the signal date: ``label_start`` = the first, and
    ``label_end`` = the h-th (its return is the last leg of the label).
    An event with no signal-date row in the chain, or fewer than h
    remaining rows, gets nulls (counted, never silently dropped or
    filled).
    """
    signal_col = "signal_date"
    for c in ("symbol", signal_col):
        if c not in events.columns:
            raise ValueError(f"events missing column {c!r}")
    if not {"symbol", "date"} <= set(chain.columns):
        raise ValueError("chain needs columns symbol/date")
    if horizon < 1:
        raise ValueError(f"horizon must be >= 1, got {horizon}")

    rows = chain.select("symbol", "date").sort("symbol", "date")
    idx = rows.with_columns(
        pl.int_range(pl.len()).over("symbol").alias("_i"))
    sig = events.select(
        "symbol", signal_col,
        pl.lit(True).alias("_sig_exists")).unique(
        subset=["symbol", signal_col], keep="first")
    # map signal date -> its chain index; events whose signal date is not
    # a chain row cannot define a window under this chain policy
    pos = idx.join(sig, left_on=["symbol", "date"],
                   right_on=["symbol", signal_col], how="semi")
    key = pos.select("symbol", "date", "_i")
    joined = events.join(key, left_on=["symbol", signal_col],
                         right_on=["symbol", "date"], how="left")
    lookup = idx.select(
        "symbol", "_i",
        pl.col("date").shift(-1).over("symbol").alias("_w_start"),
        pl.col("date").shift(-horizon).over("symbol").alias("_w_end"),
        pl.col("date").shift(-horizon).over("symbol").is_not_null()
        .alias("_w_full"))
    out = joined.join(lookup, on=["symbol", "_i"], how="left")
    n_no_sig = int(out["_i"].is_null().sum())
    out = out.with_columns(
        pl.col("_w_start").alias("label_start"),
        pl.when(pl.col("_w_full")).then(pl.col("_w_end"))
        .otherwise(None).alias("label_end"))
    n_trunc = int(
        (out["_i"].is_not_null() & out["label_end"].is_null()).sum())
    out = out.drop("_i", "_w_start", "_w_end", "_w_full")
    report = {
        "n_events": events.height,
        "horizon": horizon,
        "n_no_signal_row": n_no_sig,
        "n_truncated_window": n_trunc,
        "caliber": "label window = the h chain rows strictly after the "
                   "signal date; label_start/label_end are the first/last "
                   "leg dates; label_end is null when fewer than h rows "
                   "remain (truncation is dropped by drop_label_breach, "
                   "never filled)",
    }
    return out, report


def drop_label_breach(
    events: pl.DataFrame,
    boundary,
) -> tuple[pl.DataFrame, dict[str, Any]]:
    """R1 gate: keep only events fully inside ``boundary``.

    Drops rows where ``signal_date > boundary`` or ``label_end >
    boundary`` (an explicit window is required -- run
    :func:`label_window` first; a null label_end also fails the gate:
    an unverifiable label must not enter a dev-window sample).  Nothing
    is mutated in place; the report carries the counts and, for audit,
    the max surviving label_end and the max dropped one.
    """
    if "label_end" not in events.columns:
        raise ValueError("events missing label_end; run label_window first")
    b = boundary
    ok = (
        (pl.col("signal_date") <= b)
        & pl.col("label_end").is_not_null()
        & (pl.col("label_end") <= b)
    )
    kept = events.filter(ok)
    dropped = events.filter(~ok)
    max_kept = kept["label_end"].max() if kept.height else None
    max_dropped_sig = dropped["signal_date"].max() if dropped.height else None
    n_sig_late = int((events["signal_date"] > b).sum()) if events.height else 0
    n_label_bad = int(events.select((
        (pl.col("signal_date") <= b)
        & (pl.col("label_end").is_null() | (pl.col("label_end") > b))
    ).sum()).item() or 0) if events.height else 0
    report = {
        "boundary": str(b),
        "n_in": events.height,
        "n_kept": kept.height,
        "n_dropped": dropped.height,
        "n_dropped_signal_after": n_sig_late,
        "n_dropped_label_after_or_missing": n_label_bad,
        "max_label_end_kept": str(max_kept) if max_kept else None,
        "max_signal_date_dropped": (str(max_dropped_sig)
                                    if max_dropped_sig else None),
    }
    return kept, report


# ---------------------------------------------------------------------------
# R2: nested-model incremental F test
# ---------------------------------------------------------------------------

def _design(blocks: list[np.ndarray]) -> np.ndarray:
    """Intercept + full one-hot dummies per block (no drop-first: rank
    handling absorbs the collinearity, which keeps df bookkeeping
    faithful to the actual design)."""
    n = len(blocks[0]) if blocks else 0
    cols = [np.ones((n, 1))]
    for b in blocks:
        levels, coded = np.unique(b, return_inverse=True)
        d = np.zeros((n, len(levels)))
        d[np.arange(n), coded] = 1.0
        cols.append(d)
    return np.hstack(cols)


def _rss(y: np.ndarray, x: np.ndarray) -> tuple[float, int]:
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    return float(resid @ resid), int(np.linalg.matrix_rank(x))


def nested_f_test(
    y: np.ndarray,
    blocks: list[np.ndarray],
    test: np.ndarray,
) -> dict[str, Any]:
    """Incremental F for ``test`` after controlling ``blocks`` jointly.

    Compares the nested OLS models ``y ~ blocks`` (reduced) and
    ``y ~ blocks + test`` (full).  Degrees of freedom come from the
    actual matrix ranks (df1 = rank(full) - rank(reduced), df2 =
    n - rank(full)), NOT from level counts -- an unbalanced or
    collinear design reports its true size.  This replaces the
    sequential-demeaning + plain ANOVA pipeline (R2) whose second
    demeaning re-introduced the first factor's variation.
    """
    y = np.asarray(y, dtype=float).ravel()
    if y.ndim != 1:
        raise ValueError("y must be 1-D")
    n = y.size
    t = np.asarray(test).ravel()
    if t.size != n:
        raise ValueError(f"test length {t.size} != y length {n}")
    for b in blocks:
        if len(b) != n:
            raise ValueError(f"block length {len(b)} != y length {n}")
    x_r = _design(blocks)
    x_f = _design(blocks + [t])
    ssr_r, rank_r = _rss(y, x_r)
    ssr_f, rank_f = _rss(y, x_f)
    df1 = rank_f - rank_r
    df2 = n - rank_f
    if df1 < 1 or df2 < 1:
        raise ValueError(
            f"degenerate comparison: df1={df1} df2={df2} "
            f"(rank_r={rank_r}, rank_f={rank_f}, n={n}) -- the test factor "
            "adds no rank or the model saturates the sample")
    f_stat = ((ssr_r - ssr_f) / df1) / (ssr_f / df2)
    p = float(stats.f.sf(f_stat, df1, df2))
    return {
        "F": float(f_stat), "p": p, "df1": int(df1), "df2": int(df2),
        "ssr_reduced": ssr_r, "ssr_full": ssr_f,
        "rank_reduced": rank_r, "rank_full": rank_f, "n": int(n),
        "eta_squared_partial": (
            (ssr_r - ssr_f) / (ssr_r - ssr_f + ssr_f)
            if (ssr_r - ssr_f + ssr_f) > 0 else None),
        "caliber": "incremental F of the test factor after joint "
                   "least-squares control of the blocks; df from actual "
                   "matrix ranks (R2)",
    }
