from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from quant.research.factor_eval_run import discover_f2r1_factors, run_factor_evaluation


def _inputs(root: Path) -> tuple[Path, Path]:
    dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(16)]
    panel = pl.DataFrame(
        [{"date": d, "symbol": s, "close": 10.0 + i + (s == "b"),
          "preclose": 10.0 + i - 0.1 + (s == "b"), "tradestatus": 1, "isST": 0}
         for s in ("a", "b", "c") for i, d in enumerate(dates)],
        schema_overrides={"date": pl.Date, "symbol": pl.String},
    )
    factor = pl.DataFrame(
         [{"symbol": s, "signal_date": d, "value": float(i) + (s == "c")}
         for s in ("a", "b", "c") for i, d in enumerate(dates[:5])],
        schema_overrides={"signal_date": pl.Date, "symbol": pl.String},
    )
    panel_path, factor_path = root / "panel.parquet", root / "factor.parquet"
    panel.write_parquet(panel_path)
    factor.write_parquet(factor_path)
    return panel_path, factor_path


def _repo_root(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# test\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("", encoding="utf-8")
    return tmp_path


def _config(path: Path) -> Path:
    config = path / "config.json"
    config.write_text(json.dumps({
        "experiment_id": "exp-test-factor-eval",
        "name": "factor-evaluation-test",
        "panel_end": "2020-01-10",
        "signal_end": "2020-01-05",
        "factor_eval": {"horizon_days": 2, "min_history_rows": 0},
    }), encoding="utf-8")
    return config


def test_run_creates_new_directory_and_preserves_existing(tmp_path: Path) -> None:
    root = _repo_root(tmp_path / "repo")
    panel, factor = _inputs(tmp_path / "inputs") if (tmp_path / "inputs").mkdir() is None else (None, None)
    old = root / "artifacts" / "runs" / "fixed-run"
    old.mkdir(parents=True)
    marker = old / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    config = _config(tmp_path)
    path = run_factor_evaluation(
        repo_root=root, panel_path=panel, factor_paths=[factor],
        artifacts_root=root / "artifacts", config_path=config,
    )
    assert path != old
    assert marker.read_text(encoding="utf-8") == "keep"
    assert (path / "manifest.json").is_file()
    assert json.loads((path / "factor_results.json").read_text(encoding="utf-8"))["factor"]["n_dates"] == 5


def test_rejects_2025_factor_before_run_creation(tmp_path: Path) -> None:
    root = _repo_root(tmp_path / "repo")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    panel, factor = _inputs(inputs)
    factor = pl.read_parquet(factor).with_columns(
        pl.lit(date(2025, 1, 2)).alias("signal_date")
    )
    factor.write_parquet(inputs / "future.parquet")
    with pytest.raises(ValueError, match="2025\+|frozen"):
        run_factor_evaluation(repo_root=root, panel_path=panel,
                              factor_paths=[inputs / "future.parquet"],
                              artifacts_root=root / "artifacts",
                              config_path=_config(tmp_path))
    assert not (root / "artifacts").exists()


def test_cli_runs_in_independent_process(tmp_path: Path) -> None:
    root = _repo_root(tmp_path / "repo")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    panel, factor = _inputs(inputs)
    config = _config(tmp_path)
    cli = Path(__file__).resolve().parents[2] / "src" / "quant" / "cli" / "factor_eval_run.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cli.parents[2])
    result = subprocess.run(
        [sys.executable, str(cli), "--repo-root", str(root), "--panel", str(panel),
         "--factor", str(factor), "--config", str(config),
         "--artifacts-root", str(root / "artifacts")],
        check=True, capture_output=True, text=True, env=env,
    )
    run_path = Path(result.stdout.strip())
    assert run_path.is_dir()
    assert (run_path / "factor_results.json").is_file()


def test_f2r1_discovery_is_sorted_and_excludes_side_outputs(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    for family in ("F_xsec", "A_price", "E_event"):
        (root / family).mkdir(parents=True)
    for name in ("A02.parquet", "A01.parquet"):
        (root / "A_price" / name).write_bytes(b"x")
    (root / "E_event" / "E16_dupcount_original.parquet").write_bytes(b"x")
    (root / "E_event" / "E16.parquet").write_bytes(b"x")
    (root / "F_xsec" / "F01.parquet").write_bytes(b"x")
    found = discover_f2r1_factors(root)
    assert [p.name for p in found] == ["A01.parquet", "A02.parquet", "E16.parquet", "F01.parquet"]


def test_configured_dev_end_bounds_panel_and_factor_reads(tmp_path: Path) -> None:
    root = _repo_root(tmp_path / "repo")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    panel, factor = _inputs(inputs)
    config = _config(tmp_path)
    path = run_factor_evaluation(
        repo_root=root, panel_path=panel, factor_paths=[factor],
        artifacts_root=root / "artifacts", config_path=config,
    )
    result = json.loads((path / "factor_results.json").read_text(encoding="utf-8"))
    assert result["factor"]["n_dates"] == 5
    saved = json.loads((path / "config.json").read_text(encoding="utf-8"))
    assert saved["inputs"]["panel_end"] == "2020-01-10"
    assert saved["inputs"]["signal_end"] == "2020-01-05"
