"""Run factor evaluation from explicit parquet inputs.

Example:
  python src/quant/cli/factor_eval_run.py --panel panel.parquet \
      --factor A01.parquet --artifacts-root artifacts
"""
from __future__ import annotations

import argparse
from pathlib import Path

from quant.research.factor_eval_run import discover_f2r1_factors, run_factor_evaluation
from quant.research.runs import find_repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="run an auditable factor evaluation")
    parser.add_argument("--panel", type=Path, required=True)
    factor_group = parser.add_mutually_exclusive_group(required=True)
    factor_group.add_argument("--factor", type=Path, action="append")
    factor_group.add_argument(
        "--factor-root", type=Path,
        help="F2R1 outputs root containing A_price/B_value/C_micro/D_fund/E_event/F_xsec",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    args = parser.parse_args(argv)
    factors = args.factor or discover_f2r1_factors(args.factor_root)
    repo_root = (args.repo_root or find_repo_root()).resolve()
    path = run_factor_evaluation(
        repo_root=repo_root,
        panel_path=args.panel,
        factor_paths=factors,
        artifacts_root=args.artifacts_root,
        config_path=args.config,
    )
    # Run prints the immutable run path when it closes; avoid printing it a
    # second time so shell callers receive one machine-readable line.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
