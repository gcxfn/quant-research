"""Close-time boolean signals derived from the factor layer.

Signals are decision flags that are already known when the daily bar closes:
they only compare the current close against a backward-looking average and a
backward-looking return.  Later bars never change an earlier signal value.

A signal is ``null`` while its inputs are unavailable (warm-up), ``False``
when at least one input is known and the condition fails, and ``True`` only
when both inputs are known and true.  Nulls are intentionally not replaced by
``False``: downstream screening must treat "unknown" differently from "no".
"""

from __future__ import annotations

from typing import Final

import polars as pl

from .core import validate_daily_frame

__all__ = ["DEFAULT_SIGNAL_COLUMN", "build_signals"]

#: Name of the combined boolean signal column.
DEFAULT_SIGNAL_COLUMN: Final[str] = "signal"


def build_signals(
    df: pl.DataFrame,
    *,
    sma_window: int = 20,
    ret_window: int = 5,
    signal_column: str = DEFAULT_SIGNAL_COLUMN,
) -> pl.DataFrame:
    """Return ``df`` plus boolean signal columns known at the close.

    Columns added (when absent they are computed with the same backward
    windows as :func:`~quant.factors.core.compute_factors`)::

        sma_<sma_window>          rolling close mean, per symbol
        ret_<ret_window>          close / close.shift(ret_window) - 1, per symbol
        above_sma_<sma_window>    close > sma
        ret_<ret_window>_positive ret > 0
        signal                    above_sma & ret_positive

    ``signal_column`` defaults to ``"signal"``.  Warm-up rows stay ``null``.
    """

    validate_daily_frame(df)
    if sma_window < 1 or ret_window < 1:
        raise ValueError("sma_window and ret_window must be >= 1")
    if not signal_column or not isinstance(signal_column, str):
        raise ValueError("signal_column must be a non-empty string")

    sma_name = f"sma_{sma_window}"
    ret_name = f"ret_{ret_window}"
    close = pl.col("close").cast(pl.Float64)

    additions: list[pl.Expr] = []
    if sma_name not in df.columns:
        additions.append(
            close.rolling_mean(sma_window, min_samples=sma_window)
            .over("symbol")
            .alias(sma_name)
        )
    if ret_name not in df.columns:
        additions.append(
            (close / close.shift(ret_window).over("symbol") - 1.0).alias(ret_name)
        )
    base = df.with_columns(additions) if additions else df

    above = close > pl.col(sma_name).cast(pl.Float64)
    positive = pl.col(ret_name).cast(pl.Float64) > 0.0
    result = base.with_columns(
        [
            above.alias(f"above_sma_{sma_window}"),
            positive.alias(f"ret_{ret_window}_positive"),
            (above & positive).alias(signal_column),
        ]
    )

    added = [name for name in (sma_name, ret_name) if name not in df.columns]
    signal_cols = [f"above_sma_{sma_window}", f"ret_{ret_window}_positive", signal_column]
    moved = set(added) | set(signal_cols)
    ordered = [name for name in df.columns if name not in moved] + added + signal_cols
    return result.select(ordered)
