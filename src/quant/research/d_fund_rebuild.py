"""Source-first PIT financial intermediate rebuild for F2R1."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Iterable

import polars as pl

from quant.factors.fund_derive import latest_revision, single_quarter_diff, yoy_pit
from quant.research.financial_snapshot import development_snapshot


class DFundRebuildError(ValueError):
    pass


KEYS = ["ts_code", "ann_date", "f_ann_date", "end_date"]


def read_tushare_chunks(root: Path, dataset: str, columns: Iterable[str]) -> pl.DataFrame:
    frames: list[pl.DataFrame] = []
    wanted = list(columns)
    for path in sorted((root / dataset).glob("*/chunk_*.csv")):
        if path.stat().st_size <= 100:
            continue
        frame = pl.read_csv(path, infer_schema_length=20000)
        keep = [c for c in [*KEYS, *wanted] if c in frame.columns]
        if not keep:
            continue
        frame = frame.select(keep)
        numeric = [c for c in wanted if c in frame.columns]
        if numeric:
            frame = frame.with_columns(
                [pl.col(c).cast(pl.Float64, strict=False) for c in numeric]
            )
        frames.append(frame)
    if not frames:
        raise DFundRebuildError(f"no input chunks found for {dataset}")
    return pl.concat(frames, how="diagonal")


def _dates(frame: pl.DataFrame) -> pl.DataFrame:
    exprs = []
    for c in ("ann_date", "f_ann_date", "end_date"):
        if c in frame.columns:
            if frame.schema[c] == pl.Date:
                exprs.append(pl.col(c))
            else:
                s = pl.col(c).cast(pl.String).str.strip_chars()
                exprs.append(
                    pl.coalesce(
                        s.str.to_date("%Y%m%d", strict=False),
                        s.str.to_date("%Y-%m-%d", strict=False),
                    ).alias(c)
                )
    return frame.with_columns(exprs)


def _pit(frame: pl.DataFrame, dev_end: date) -> pl.DataFrame:
    frame = _dates(frame)
    if "ts_code" not in frame.columns or "end_date" not in frame.columns:
        raise DFundRebuildError("financial input needs ts_code and end_date")
    frame = frame.with_columns(
        pl.concat_str(
            pl.col("ts_code").str.split(".").list.last().str.to_lowercase(),
            pl.lit("."),
            pl.col("ts_code").str.split(".").list.first(),
        ).alias("symbol")
    )
    snap, report = development_snapshot(frame, dev_end=dev_end)
    if snap.is_empty():
        raise DFundRebuildError("development snapshot is empty")
    if "f_ann_date" not in snap.columns:
        snap = snap.with_columns(pl.lit(None, dtype=pl.Date).alias("f_ann_date"))
    if "ann_date" not in snap.columns:
        snap = snap.with_columns(pl.lit(None, dtype=pl.Date).alias("ann_date"))
    snap = snap.with_columns(
        pl.coalesce(
            pl.col("f_ann_date"), pl.col("ann_date"),
            pl.col("end_date") + pl.duration(days=90),
        ).alias("signal_date")
    )
    snap = latest_revision(snap)
    return snap, report


def rebuild_intermediate(
    *, raw_root: Path, dev_end: date = date(2020, 12, 31)
) -> tuple[pl.DataFrame, dict]:
    specs = {
        "fina_indicator": ["eps", "bps", "roe", "roa", "grossprofit_margin",
                           "netprofit_margin", "debt_to_assets", "current_ratio",
                           "netprofit_yoy", "tr_yoy", "ocf_yoy", "assets_turn",
                           "q_sales_yoy", "q_roe", "profit_dedt", "ocfps"],
        "income": ["revenue", "n_income_attr_p", "sell_exp", "admin_exp"],
        "balancesheet": ["total_assets", "total_hldr_eqy_exc_min_int", "intan_assets",
                          "goodwill", "total_share"],
        "cashflow": ["n_cashflow_act"],
    }
    pit: dict[str, pl.DataFrame] = {}
    reports = {}
    for name, cols in specs.items():
        raw = read_tushare_chunks(raw_root, name, cols)
        pit[name], reports[name] = _pit(raw, dev_end)
    base = pit["fina_indicator"]
    for name in ("income", "balancesheet", "cashflow"):
        other = pit[name]
        value_cols = [c for c in other.columns if c not in
                      {"ts_code", "symbol", "ann_date", "f_ann_date", "end_date", "signal_date"}]
        base = base.join(
            other.select("symbol", "end_date", "signal_date", *value_cols)
            .rename({"signal_date": f"signal_date_{name}"}),
            on=["symbol", "end_date"], how="left",
        )
    signal_cols = [c for c in base.columns if c.startswith("signal_date")]
    base = base.with_columns(pl.max_horizontal(signal_cols).alias("signal_date"))
    bad_periods = base.filter(~pl.col("end_date").dt.month().is_in([3, 6, 9, 12])).height
    base = base.filter(pl.col("end_date").dt.month().is_in([3, 6, 9, 12]))
    cumulative = [c for c in ["revenue", "n_income_attr_p"] if c in base.columns]
    base, quarter = single_quarter_diff(base, cumulative) if cumulative else (base, {})
    yoy_cols = [c for c in ["roe", "grossprofit_margin", "debt_to_assets", "eps"] if c in base.columns]
    base, yoy = yoy_pit(base, yoy_cols) if yoy_cols else (base, {})
    return base, {"sources": reports, "non_quarter_rows_dropped": bad_periods,
                  "quarter": quarter, "yoy": yoy}
