from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest

from quant.research.factor_correlation_dedupe import (
    DedupeConfig,
    run_factor_correlation_dedupe,
)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# test\n", encoding="utf-8")
    (root / "uv.lock").write_text("", encoding="utf-8")
    return root


def _factors(tmp_path: Path) -> list[Path]:
    root = tmp_path / "factors"
    root.mkdir()
    dates = [date(2020, 1, 1) + timedelta(days=i) for i in range(4)]
    rows = [{"symbol": s, "signal_date": d, "value": float(i + (s == "b"))}
            for s in ("a", "b", "c") for i, d in enumerate(dates)]
    base = pl.DataFrame(rows, schema_overrides={"symbol": pl.String, "signal_date": pl.Date})
    paths = []
    for name, values in (("A01", base), ("A02", base.with_columns((pl.col("value") * 2).alias("value"))),
                         ("B01", base.with_columns((-pl.col("value")).alias("value")))):
        path = root / f"{name}.parquet"
        values.write_parquet(path)
        paths.append(path)
    return paths


def test_dedupe_writes_complete_outputs_and_preserves_old_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    old = repo / "artifacts" / "runs" / "old"
    old.mkdir(parents=True)
    marker = old / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    run = run_factor_correlation_dedupe(
        repo_root=repo, factor_paths=_factors(tmp_path),
        artifacts_root=repo / "artifacts", config=DedupeConfig(0.9, 2),
    )
    assert run != old
    assert marker.read_text(encoding="utf-8") == "keep"
    assert (run / "correlation_matrix.csv").is_file()
    assert (run / "exclusion_reasons.csv").is_file()
    assert (run / "retained_factors.csv").is_file()
    assert len((run / "correlation_matrix.csv").read_text(encoding="utf-8").splitlines()) == 4
    decisions = pl.read_csv(run / "exclusion_reasons.csv")
    # B01 = -A01 完全负相关，|ρ|=1 与 A01 信息冗余，按预登记的绝对值阈值语义一并排除。
    assert decisions.filter(pl.col("decision") == "excluded")["factor_id"].to_list() == ["A02", "B01"]
    assert decisions.filter(pl.col("decision") == "retained")["factor_id"].to_list() == ["A01"]


def test_rejects_post_dev_data_before_creating_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    path = _factors(tmp_path)[0]
    frame = pl.read_parquet(path).with_columns(pl.lit(date(2021, 1, 4)).alias("signal_date"))
    future = tmp_path / "future.parquet"
    frame.write_parquet(future)
    with pytest.raises(ValueError, match="post-development"):
        run_factor_correlation_dedupe(repo_root=repo, factor_paths=[future], artifacts_root=repo / "artifacts")
    assert not (repo / "artifacts").exists()


def test_cli_uses_explicit_inputs_and_prints_unique_run(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    factors = _factors(tmp_path)
    cli = Path(__file__).resolve().parents[2] / "src" / "quant" / "cli" / "factor_correlation_dedupe.py"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cli.parents[2])
    result = subprocess.run(
        [sys.executable, str(cli), "--repo-root", str(repo), "--factor", str(factors[0]),
         "--factor", str(factors[1]), "--factor", str(factors[2]),
         "--artifacts-root", str(repo / "artifacts")],
        check=True, capture_output=True, text=True, env=env,
    )
    run = Path(result.stdout.strip())
    assert run.is_dir()
    assert (run / "manifest.json").is_file()
    assert json.loads((run / "manifest.json").read_text(encoding="utf-8"))["status"] == "completed"

