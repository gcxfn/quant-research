"""Reproducible F3 factor correlation and deterministic deduplication.

This module prepares the factor set for F3.  It does not build a portfolio or
run a strategy backtest.  The development window is fixed to 2015--2020;
later observations are rejected before they can enter the correlation data.
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import polars as pl

from quant.factors.eval import FREEZE_END
from quant.research.runs import Run, sha256, write_json

DEV_START = date(2015, 1, 1)
DEV_END = date(2020, 12, 31)


@dataclass(frozen=True)
class DedupeConfig:
    correlation_threshold: float = 0.60
    min_pair_dates: int = 2

    def __post_init__(self) -> None:
        if not 0 < self.correlation_threshold <= 1:
            raise ValueError("correlation_threshold must be in (0, 1]")
        if self.min_pair_dates < 1:
            raise ValueError("min_pair_dates must be >= 1")

    def canonical(self) -> dict[str, object]:
        return {
            "dev_start": str(DEV_START),
            "dev_end": str(DEV_END),
            "correlation_threshold": self.correlation_threshold,
            "min_pair_dates": self.min_pair_dates,
            "correlation": "mean daily cross-sectional Spearman rho",
            "dedupe_order": "ascending factor_id; first factor is retained",
        }


def _factor_id(path: Path, frame: pl.DataFrame) -> str:
    if "factor_id" in frame.columns:
        ids = frame["factor_id"].drop_nulls().unique().sort().to_list()
        if len(ids) == 1:
            return str(ids[0])
    return path.stem


def _load_factor(path: Path) -> tuple[str, pl.DataFrame]:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pl.read_parquet(path)
    required = {"symbol", "signal_date", "value"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    if frame.schema["signal_date"] != pl.Date:
        raise ValueError(f"{path} signal_date must have Date dtype")
    latest = frame["signal_date"].max()
    if latest is not None and latest > DEV_END:
        raise ValueError(
            f"{path} contains post-development data {latest}; "
            f"F3 is limited to {DEV_START}..{DEV_END}"
        )
    if frame.schema["symbol"] != pl.String:
        raise ValueError(f"{path} symbol must have String dtype")
    if frame.group_by("symbol", "signal_date").len().filter(pl.col("len") > 1).height:
        raise ValueError(f"{path} has duplicate (symbol, signal_date) keys")
    frame = frame.filter(
        (pl.col("signal_date") >= pl.lit(DEV_START))
        & (pl.col("signal_date") <= pl.lit(DEV_END))
        & pl.col("value").is_not_null()
    )
    return _factor_id(path, frame), frame.select("symbol", "signal_date", "value")


def discover_survivor_factors(root: Path, survivors_csv: Path | None = None) -> list[Path]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    paths = sorted(
        p for p in root.rglob("*.parquet")
        if p.stem[:1] in "ABCDEF" and len(p.stem) == 3 and p.stem[1:].isdigit()
    )
    if survivors_csv is None:
        return paths
    wanted = {
        row["factor_id"]
        for row in csv.DictReader(Path(survivors_csv).open(encoding="utf-8", newline=""))
        if row.get("factor_id")
    }
    found = {p.stem: p for p in paths}
    missing = sorted(wanted - found.keys())
    if missing:
        raise FileNotFoundError(f"survivor factors missing: {missing}")
    return [found[fid] for fid in sorted(wanted)]


def _mean_daily_spearman(left: pl.DataFrame, right: pl.DataFrame, min_pair_dates: int) -> float | None:
    joined = left.join(right, on=["symbol", "signal_date"], how="inner", suffix="_right")
    if joined.height == 0:
        return None
    daily = (
        joined.with_columns(
            pl.col("value").rank("average").over("signal_date").alias("left_rank"),
            pl.col("value_right").rank("average").over("signal_date").alias("right_rank"),
        )
        .group_by("signal_date")
        .agg(pl.corr("left_rank", "right_rank").alias("rho"))
        .filter(pl.col("rho").is_not_null())
    )
    if daily.height < min_pair_dates:
        return None
    value = daily["rho"].mean()
    return float(value) if value is not None and math.isfinite(float(value)) else None


def _correlation_matrix(factors: list[tuple[str, pl.DataFrame]], cfg: DedupeConfig) -> pl.DataFrame:
    names = [name for name, _ in factors]
    values: dict[str, list[float | None]] = {name: [None] * len(names) for name in names}
    for i, (left_name, left) in enumerate(factors):
        values[left_name][i] = 1.0
        for j in range(i + 1, len(factors)):
            right_name, right = factors[j]
            rho = _mean_daily_spearman(left, right, cfg.min_pair_dates)
            values[left_name][j] = rho
            values[right_name][i] = rho
    return pl.DataFrame({"factor_id": names, **values})


def _dedupe(matrix: pl.DataFrame, cfg: DedupeConfig) -> pl.DataFrame:
    names = matrix["factor_id"].to_list()
    rows: list[dict[str, object]] = []
    kept: list[str] = []
    for i, name in enumerate(names):
        blockers = []
        for prior in kept:
            rho = matrix.filter(pl.col("factor_id") == prior).select(name).item()
            if rho is not None and abs(float(rho)) >= cfg.correlation_threshold:
                blockers.append((prior, float(rho)))
        if blockers:
            blocker, rho = max(blockers, key=lambda x: (abs(x[1]), x[0]))
            rows.append({
                "factor_id": name, "decision": "excluded",
                "reason": "high_correlation_with_retained_factor",
                "blocking_factor": blocker, "correlation": rho,
            })
        else:
            kept.append(name)
            rows.append({
                "factor_id": name, "decision": "retained",
                "reason": "first_in_deterministic_order_or_below_threshold",
                "blocking_factor": None, "correlation": None,
            })
    return pl.DataFrame(rows).sort("factor_id")


def run_factor_correlation_dedupe(
    *, repo_root: Path, factor_paths: Iterable[Path], artifacts_root: Path,
    config: DedupeConfig | None = None, experiment_id: str = "exp-20260920-f3-correlation",
) -> Path:
    cfg = config or DedupeConfig()
    paths = sorted({Path(p).resolve() for p in factor_paths}, key=lambda p: p.stem)
    if not paths:
        raise ValueError("at least one factor is required")
    loaded = [_load_factor(path) for path in paths]
    names = [name for name, _ in loaded]
    if len(set(names)) != len(names):
        raise ValueError("factor IDs must be unique")
    loaded.sort(key=lambda item: item[0])
    matrix = _correlation_matrix(loaded, cfg)
    decisions = _dedupe(matrix, cfg)
    config = {
        "experiment_id": experiment_id,
        "name": "f3-correlation-dedupe",
        "start": str(DEV_START), "end": str(DEV_END),
        "factor_count": len(loaded), "factor_ids": [name for name, _ in loaded],
        "dedupe": cfg.canonical(),
    }
    with Run(Path(repo_root).resolve(), "f3-correlation-dedupe", config,
             artifacts_root=Path(artifacts_root).resolve()) as run:
        run.manifest["inputs"] = [
            {"path": str(path), "sha256": sha256(path), "role": "factor", "factor_id": name,
             "rows_used": frame.height}
            for path, (name, frame) in zip(paths, loaded)
        ]
        matrix.write_csv(run.path / "correlation_matrix.csv")
        decisions.write_csv(run.path / "exclusion_reasons.csv")
        decisions.filter(pl.col("decision") == "retained").select("factor_id").write_csv(
            run.path / "retained_factors.csv"
        )
        matrix.filter(pl.col("factor_id").is_in(
            decisions.filter(pl.col("decision") == "retained")["factor_id"].to_list()
        )).write_csv(run.path / "retained_correlation_matrix.csv")
        run.metrics = {
            "input_factor_count": len(loaded),
            "retained_factor_count": decisions.filter(pl.col("decision") == "retained").height,
            "excluded_factor_count": decisions.filter(pl.col("decision") == "excluded").height,
            "threshold": cfg.correlation_threshold,
        }
        write_json(run.path / "dedupe_config.json", cfg.canonical())
        (run.path / "report.md").write_text(
            "# F3 相关性去重准备\n\n"
            f"- 开发集：{DEV_START} 至 {DEV_END}\n"
            f"- 输入因子：{len(loaded)}\n"
            f"- 保留因子：{run.metrics['retained_factor_count']}\n"
            f"- 淘汰因子：{run.metrics['excluded_factor_count']}\n"
            f"- 阈值：|平均日内 Spearman ρ| >= {cfg.correlation_threshold}\n"
            "- 本运行只准备因子去重结果，不包含策略回测。\n",
            encoding="utf-8",
        )
    return run.path

