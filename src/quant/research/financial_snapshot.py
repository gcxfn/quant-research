"""Read-only development snapshots for mixed financial inputs."""
from __future__ import annotations

from datetime import date

import polars as pl

FREEZE_END = date(2024, 12, 31)


class FinancialSnapshotError(ValueError):
    """Raised when financial input violates the freeze boundary."""


def _date_column(frame: pl.DataFrame, name: str) -> pl.Expr:
    if frame.schema[name] == pl.Date:
        return pl.col(name)
    text = pl.col(name).cast(pl.String).str.strip_chars()
    return pl.coalesce(
        text.str.to_date("%Y%m%d", strict=False),
        text.str.to_date("%Y-%m-%d", strict=False),
    )


def development_snapshot(
    frame: pl.DataFrame,
    *,
    dev_end: date = date(2020, 12, 31),
    label: str = "financial",
) -> tuple[pl.DataFrame, dict[str, int | str]]:
    """Return a PIT development snapshot without mutating ``frame``.

    ``signal_date`` is used when present.  Otherwise it is derived from
    ``f_ann_date``, ``ann_date`` and finally ``end_date + 90 days``.  All
    source rows outside the research freeze are discarded and counted; they
    never enter the returned development frame.
    """
    if dev_end > FREEZE_END:
        raise FinancialSnapshotError("dev_end is after the research freeze")
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("frame must be a polars DataFrame")
    date_names = [name for name in ("signal_date", "f_ann_date", "ann_date", "end_date")
                  if name in frame.columns]
    if not date_names:
        raise FinancialSnapshotError(
            f"{label} input needs signal_date or f_ann_date/ann_date/end_date"
        )
    normalized = frame.with_columns([
        _date_column(frame, name).alias(name) for name in date_names
    ])
    if "signal_date" not in normalized.columns:
        if "end_date" not in normalized.columns:
            raise FinancialSnapshotError(
                f"{label} input without signal_date needs end_date"
            )
        visible = [name for name in ("f_ann_date", "ann_date")
                   if name in normalized.columns]
        expressions = [pl.col(name) for name in visible]
        expressions.append(pl.col("end_date") + pl.duration(days=90))
        normalized = normalized.with_columns(
            pl.coalesce(expressions).alias("signal_date")
        )

    total = normalized.height
    missing = normalized.filter(pl.col("signal_date").is_null()).height
    dropped_after_freeze = normalized.filter(
        pl.any_horizontal([
            pl.col(name) > pl.lit(FREEZE_END)
            for name in date_names + ["signal_date"]
        ])
    ).height
    after_dev = normalized.filter(pl.col("signal_date") > pl.lit(dev_end)).height
    kept = normalized.filter(
        pl.col("signal_date").is_not_null()
        & pl.all_horizontal([
            pl.col(name) <= pl.lit(FREEZE_END)
            for name in date_names + ["signal_date"]
        ])
        & (pl.col("signal_date") <= pl.lit(dev_end))
    )
    return kept, {
        "label": label,
        "total_rows": total,
        "kept_rows": kept.height,
        "dropped_rows": total - kept.height,
        "dropped_missing_signal_date": missing,
        "dropped_after_dev_end": after_dev,
        "dropped_after_freeze_end": dropped_after_freeze,
        "dev_end": str(dev_end),
        "freeze_end": str(FREEZE_END),
    }
