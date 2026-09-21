"""Independent integration entry point for the synthetic portfolio smoke suite."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import portfolio_contract_smoke as smoke  # noqa: E402


def test_all_synthetic_portfolio_scenarios_pass() -> None:
    outcomes = smoke.run_all()
    assert len(outcomes) == len(smoke.SCENARIO_NAMES)
    assert all(outcome.ok for outcome in outcomes), [
        outcome.to_mapping() for outcome in outcomes if not outcome.ok
    ]


def test_each_registered_criterion_has_a_passing_scenario() -> None:
    for criterion, names in smoke.CRITERIA.items():
        outcomes = smoke.run_all(names)
        assert outcomes, criterion
        assert all(outcome.ok for outcome in outcomes), {
            criterion: [outcome.to_mapping() for outcome in outcomes]
        }


def test_smoke_rejects_unknown_scenario_without_running_data() -> None:
    assert smoke.main(["--only", "does_not_exist"]) == 2
