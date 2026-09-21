"""Run the reproducible F3 factor correlation deduplication preparation."""
from __future__ import annotations

import argparse
from pathlib import Path

from quant.research.factor_correlation_dedupe import (
    DedupeConfig,
    discover_survivor_factors,
    run_factor_correlation_dedupe,
)
from quant.research.runs import find_repo_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prepare F3 factor correlation deduplication")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--factor", type=Path, action="append")
    group.add_argument("--factor-root", type=Path)
    parser.add_argument("--survivors", type=Path, help="CSV containing a factor_id column")
    parser.add_argument("--threshold", type=float, default=0.60)
    parser.add_argument("--min-pair-dates", type=int, default=2)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--artifacts-root", type=Path, required=True)
    parser.add_argument("--experiment-id", default="exp-20260920-f3-correlation")
    args = parser.parse_args(argv)
    factors = args.factor or discover_survivor_factors(args.factor_root, args.survivors)
    run_factor_correlation_dedupe(
        repo_root=(args.repo_root or find_repo_root()).resolve(),
        factor_paths=factors,
        artifacts_root=args.artifacts_root,
        config=DedupeConfig(args.threshold, args.min_pair_dates),
        experiment_id=args.experiment_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

