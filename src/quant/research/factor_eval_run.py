"""Small, auditable entry point for the next factor evaluation round.

The factor builders remain separate from this module.  This module only owns
the reusable run boundary: explicit parquet inputs, frozen evaluation config,
input identities, and a new non-overwriting ``Run`` directory.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from quant.factors.eval import FREEZE_END, FactorEvalConfig, evaluate_factor
from quant.research.runs import Run, sha256, write_json


def _read_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"experiment_id": "exp-factor-evaluation", "name": "factor-evaluation"}
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or "experiment_id" not in config:
        raise ValueError("config must be an object containing experiment_id")
    return config


def _config_date(config: dict[str, Any], key: str, default: date) -> date:
    raw = config.get(key)
    if raw is None:
        return default
    try:
        value = date.fromisoformat(str(raw))
    except ValueError as exc:
        raise ValueError(f"{key} must be an ISO date (YYYY-MM-DD), got {raw!r}") from exc
    if value > FREEZE_END:
        raise ValueError(f"{key} cannot exceed frozen research end {FREEZE_END}")
    return value


def discover_f2r1_factors(root: Path) -> list[Path]:
    """Discover the six F2R1 family outputs in deterministic order.

    Only files named ``A01`` ... ``F99`` are accepted.  This intentionally
    excludes historical side outputs such as ``E16_dupcount_original``.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    pattern = re.compile(r"^[A-F]\d{2}\.parquet$")
    direct = [path for path in root.glob("*.parquet") if pattern.fullmatch(path.name)]
    nested = [path for family in root.glob("*") if family.is_dir()
              for path in sorted(family.glob("*.parquet"))
              if pattern.fullmatch(path.name)]
    paths = sorted(direct + nested)
    if not paths:
        raise ValueError(f"no F2R1 factor parquet files found under {root}")
    return paths


def _eval_config(config: dict[str, Any]) -> FactorEvalConfig:
    values = config.get("factor_eval", config.get("evaluation", {}))
    if not isinstance(values, dict):
        raise ValueError("factor_eval/evaluation must be an object")
    return FactorEvalConfig(**{k: values[k] for k in FactorEvalConfig.__dataclass_fields__ if k in values})


def _check_date_limit(frame: pl.DataFrame, column: str, label: str) -> None:
    if column not in frame.columns:
        raise ValueError(f"{label} missing required column {column!r}")
    maximum = frame[column].max()
    if maximum is not None and maximum > FREEZE_END:
        raise ValueError(
            f"{label} contains frozen data after {FREEZE_END}: {maximum}; "
            "2025+ research data is not allowed"
        )


def _factor_name(path: Path, frame: pl.DataFrame) -> str:
    if "factor_id" in frame.columns:
        values = frame["factor_id"].drop_nulls().unique().to_list()
        if len(values) == 1:
            return str(values[0])
    return path.stem


def _json_safe(value: Any) -> Any:
    """Convert undefined statistics to JSON null, never non-standard NaN."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def run_factor_evaluation(
    *,
    repo_root: Path,
    panel_path: Path,
    factor_paths: Iterable[Path],
    artifacts_root: Path,
    config_path: Path | None = None,
) -> Path:
    """Evaluate explicit factor parquet files into a fresh run directory.

    ``factor_paths`` must contain frames with ``symbol``, ``signal_date`` and
    ``value``.  No output path is accepted: ``Run`` owns a unique child path
    and refuses an existing directory.
    """
    repo_root = repo_root.resolve()
    panel_path = panel_path.resolve()
    factors = [Path(path).resolve() for path in factor_paths]
    if not factors:
        raise ValueError("at least one factor parquet is required")
    if not panel_path.is_file():
        raise FileNotFoundError(panel_path)
    if any(not path.is_file() for path in factors):
        missing = [str(path) for path in factors if not path.is_file()]
        raise FileNotFoundError(", ".join(missing))
    if len(set(factors)) != len(factors):
        raise ValueError("factor paths must be unique")

    config = _read_config(config_path)
    eval_cfg = _eval_config(config)
    panel_end = _config_date(config, "panel_end", FREEZE_END)
    signal_end = _config_date(config, "signal_end", panel_end)
    if signal_end > panel_end:
        raise ValueError("signal_end cannot be later than panel_end")
    # Bound the read itself.  This keeps a mixed 2015-2024 source from
    # supplying validation-period forward labels to a dev-only F2R1 run.
    panel = (
        pl.scan_parquet(panel_path)
        .filter(pl.col("date") <= pl.lit(panel_end))
        .collect()
    )
    _check_date_limit(panel, "date", "panel")

    loaded: list[tuple[str, Path, pl.DataFrame]] = []
    names: set[str] = set()
    for path in factors:
        raw_frame = pl.scan_parquet(path).collect()
        _check_date_limit(raw_frame, "signal_date", str(path))
        frame = (
            raw_frame.lazy()
            .filter(pl.col("signal_date") <= pl.lit(signal_end))
            .collect()
        )
        name = _factor_name(path, frame)
        if name in names:
            raise ValueError(f"duplicate factor name: {name}")
        names.add(name)
        loaded.append((name, path, frame))

    run_name = str(config.get("name", "factor-evaluation"))
    config = dict(config)
    config["factor_eval"] = eval_cfg.canonical()
    config["inputs"] = {
        "panel": str(panel_path),
        "factors": [str(path) for _, path, _ in loaded],
        "panel_end": str(panel_end),
        "signal_end": str(signal_end),
        "freeze_end": str(FREEZE_END),
    }
    with Run(repo_root, run_name, config, artifacts_root=artifacts_root) as run:
        run.manifest["inputs"] = [
            {"path": str(panel_path), "sha256": sha256(panel_path), "rows": panel.height, "role": "panel"},
            *[
                {"path": str(path), "sha256": sha256(path), "rows": frame.height, "role": "factor", "name": name}
                for name, path, frame in loaded
            ],
        ]
        results: dict[str, dict[str, Any]] = {}
        for name, _, frame in loaded:
            results[name] = evaluate_factor(frame, panel, eval_cfg)
        run.metrics = {
            "factor_count": len(results),
            "factors": {name: {"n_dates": value["n_dates"], "ic_mean": value["ic_mean"]}
                        for name, value in results.items()},
        }
        write_json(run.path / "factor_results.json", _json_safe(results))
        (run.path / "report.md").write_text(
            "# 因子评估运行\n\n"
            f"- 因子数量：{len(results)}\n"
            f"- 面板行数：{panel.height}\n"
            f"- 评估配置：`{json.dumps(eval_cfg.canonical(), ensure_ascii=False, sort_keys=True)}`\n"
            "- 数据边界：不允许使用 2025-01-01 及以后数据。\n",
            encoding="utf-8",
        )
    return run.path
