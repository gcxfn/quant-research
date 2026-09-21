"""Small, source-first F2R1 rebuild primitives.

This module deliberately stops before the full D01-D30 formula layer.  It
only wires the corrected financial derivation functions and the corrected E16
event aggregation into explicit, testable inputs.  Callers must provide
frames; this module never discovers or mutates historical artifact paths.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping

import polars as pl

from quant.factors import fund_derive
from quant.research.runs import Run

FREEZE_END = date(2024, 12, 31)


class F2R1RebuildError(ValueError):
    """Raised when a rebuild input violates the small-run contract."""


def _reject_future(frame: pl.DataFrame, columns: Iterable[str], label: str) -> None:
    for column in columns:
        if column not in frame.columns:
            continue
        maximum = frame[column].max()
        if maximum is not None and maximum > FREEZE_END:
            raise F2R1RebuildError(
                f"{label}.{column} contains {maximum}; data after "
                f"{FREEZE_END} is forbidden"
            )


def _as_date(frame: pl.DataFrame, columns: Iterable[str]) -> pl.DataFrame:
    expressions = []
    for column in columns:
        if column in frame.columns:
            if frame.schema[column] == pl.Date:
                expressions.append(pl.col(column))
                continue
            expressions.append(
                pl.col(column).cast(pl.String).str.to_date("%Y%m%d", strict=False)
                .fill_null(pl.col(column).cast(pl.String).str.to_date("%Y-%m-%d", strict=False))
                .alias(column)
            )
    return frame.with_columns(expressions) if expressions else frame


def _symbolize(frame: pl.DataFrame) -> pl.DataFrame:
    if "symbol" in frame.columns:
        return frame
    if "ts_code" not in frame.columns:
        raise F2R1RebuildError("financial input needs symbol or ts_code")
    return frame.with_columns(
        pl.concat_str(
            pl.col("ts_code").str.split(".").list.last().str.to_lowercase(),
            pl.lit("."),
            pl.col("ts_code").str.split(".").list.first(),
        ).alias("symbol")
    )


def _financial_pit(raw: pl.DataFrame) -> pl.DataFrame:
    required = {"end_date"}
    missing = sorted(required - set(raw.columns))
    if missing:
        raise F2R1RebuildError(f"financial input missing {missing}")
    frame = _symbolize(_as_date(raw, ("ann_date", "f_ann_date", "end_date")))
    _reject_future(frame, ("ann_date", "f_ann_date", "end_date"), "financial")
    for column in ("ann_date", "f_ann_date"):
        if column not in frame.columns:
            frame = frame.with_columns(pl.lit(None, dtype=pl.Date).alias(column))
    frame = frame.with_columns(
        pl.coalesce(
            pl.col("f_ann_date"),
            pl.col("ann_date"),
            pl.col("end_date") + pl.duration(days=90),
        ).alias("signal_date")
    )
    _reject_future(frame, ("signal_date",), "financial")
    return fund_derive.latest_revision(frame)


def rebuild_financial_derivation(
    sources: Mapping[str, pl.DataFrame],
    *,
    cumulative_columns: list[str],
    yoy_columns: list[str],
    signal_end: date = FREEZE_END,
) -> tuple[pl.DataFrame, dict]:
    """Connect raw financial frames to the corrected shared derivation layer.

    ``sources`` is normally a small selection of fina/income/balance/cashflow
    frames.  Values are joined by ``(symbol, end_date)``.  The returned frame
    is intentionally an intermediate D frame, not the complete D01-D30 set.
    """
    if signal_end > FREEZE_END:
        raise F2R1RebuildError("signal_end is after the research freeze")
    if not sources:
        raise F2R1RebuildError("at least one financial source is required")
    pit_frames = [_financial_pit(frame) for frame in sources.values()]
    merged = pit_frames[0]
    for frame in pit_frames[1:]:
        value_cols = [c for c in frame.columns if c not in
                      {"symbol", "end_date", "signal_date", "ann_date", "f_ann_date"}]
        merged = merged.join(
            frame.select("symbol", "end_date", "signal_date", *value_cols)
            .rename({"signal_date": f"signal_date_{len(value_cols)}"}),
            on=["symbol", "end_date"], how="outer_coalesce",
        )
    signal_columns = [c for c in merged.columns if c.startswith("signal_date")]
    merged = merged.with_columns(pl.max_horizontal(signal_columns).alias("signal_date"))
    merged = merged.filter(pl.col("signal_date") <= pl.lit(signal_end))

    available_cum = [c for c in cumulative_columns if c in merged.columns]
    available_yoy = [c for c in yoy_columns if c in merged.columns]
    if available_cum:
        merged, quarter_report = fund_derive.single_quarter_diff(merged, available_cum)
    else:
        quarter_report = {"n_rows": merged.height, "n_diff": 0}
    if available_yoy:
        merged, yoy_report = fund_derive.yoy_pit(merged, available_yoy)
    else:
        yoy_report = {"n_current_rows": merged.height, "n_yoy_linked": 0}
    return merged, {
        "sources": list(sources),
        "cumulative_columns_used": available_cum,
        "yoy_columns_used": available_yoy,
        "quarter": quarter_report,
        "yoy": yoy_report,
    }


def rebuild_e16(
    dividend: pl.DataFrame,
    panel: pl.DataFrame,
    *,
    signal_end: date = FREEZE_END,
) -> tuple[pl.DataFrame, dict]:
    """Build the corrected E16 frame from dividend events and a daily panel."""
    dividend = _as_date(dividend, ("ann_date", "ex_date"))
    dividend = _symbolize(dividend)
    needed = {"symbol", "ex_date", "cash_div"}
    missing = sorted(needed - set(dividend.columns))
    if missing:
        raise F2R1RebuildError(f"dividend input missing {missing}")
    if "date" not in panel.columns or "symbol" not in panel.columns or "close" not in panel.columns:
        raise F2R1RebuildError("panel needs date, symbol and close")
    _reject_future(dividend, ("ann_date", "ex_date"), "dividend")
    _reject_future(panel, ("date",), "panel")
    if signal_end > FREEZE_END:
        raise F2R1RebuildError("signal_end is after the research freeze")
    dividend = dividend.with_columns(pl.col("cash_div").cast(pl.Float64, strict=False).fill_null(0.0))
    conflicting = (dividend.group_by("symbol", "ex_date")
                   .agg(pl.col("cash_div").drop_nulls().n_unique().alias("n_values"))
                   .filter(pl.col("n_values") > 1))
    if "ann_date" not in dividend.columns:
        dividend = dividend.with_columns(pl.lit(None, dtype=pl.Date).alias("ann_date"))
    # A later announcement is the deterministic correction for an event;
    # same-day ties use cash_div as an explicit stable tie-break.
    dedup = (dividend.sort(["symbol", "ex_date", "ann_date", "cash_div"], nulls_last=True)
             .group_by("symbol", "ex_date").last())
    dates = (panel.filter(pl.col("date") <= pl.lit(signal_end))
             .group_by(pl.col("date").dt.year().alias("_year"),
                       pl.col("date").dt.month().alias("_month"))
             .agg(pl.col("date").max().alias("signal_date"))
             .sort("signal_date")["signal_date"].to_list())
    rows = []
    for signal_date in dates:
        events = dedup.filter(
            (pl.col("ex_date") > signal_date - timedelta(days=365))
            & (pl.col("ex_date") <= signal_date)
        ).group_by("symbol").agg(pl.col("cash_div").sum().alias("cash_div_365"))
        close = panel.filter(pl.col("date") == signal_date).select("symbol", "close")
        rows.append(events.join(close, on="symbol", how="inner").with_columns(
            (pl.col("cash_div_365") / pl.col("close")).alias("value"),
            pl.lit(signal_date).alias("signal_date"),
        ).select("symbol", "signal_date", "value"))
    result = pl.concat(rows) if rows else pl.DataFrame(schema={
        "symbol": pl.String, "signal_date": pl.Date, "value": pl.Float64})
    return result.sort("symbol", "signal_date"), {
        "input_rows": dividend.height,
        "deduplicated_events": dedup.height,
        "conflicting_events_resolved": conflicting.height,
        "signal_dates": len(dates),
    }


def write_rebuild_run(
    *, repo_root: Path, artifacts_root: Path, config: dict,
    d_frame: pl.DataFrame | None = None, e16_frame: pl.DataFrame | None = None,
) -> Path:
    """Write a small rebuild result to a unique new run directory."""
    if "experiment_id" not in config:
        raise F2R1RebuildError("config needs experiment_id")
    with Run(repo_root.resolve(), "f2r1-rebuild", config, artifacts_root=artifacts_root.resolve()) as run:
        if d_frame is not None:
            d_frame.write_parquet(run.path / "d_derivation.parquet")
        if e16_frame is not None:
            e16_frame.write_parquet(run.path / "e16.parquet")
        run.metrics = {"d_rows": d_frame.height if d_frame is not None else 0,
                       "e16_rows": e16_frame.height if e16_frame is not None else 0}
    return run.path
