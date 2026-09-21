"""Create a one-time F3R2-A0 validation runner from the frozen dev runner.

The source runner is copied verbatim first. Only the validation window,
run identity, and dev-only A0 regression assertion are changed in the derived
copy. The historical runner is never edited.
"""
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
src = ROOT / "artifacts/runs/20260919T194700-f3r2-hybrid-chassis-e7a1/scripts/runner_f3r2.py"
run = ROOT / "artifacts/runs/20260921T090000-f3r2-a0-validation"
dst = run / "scripts/runner_f3r2_a0_validation.py"
dst.parent.mkdir(parents=True, exist_ok=True)
text = src.read_text(encoding="utf-8")
text = text.replace(
    'RUN_DIR = Path(__file__).resolve().parents[1]',
    'RUN_DIR = Path(__file__).resolve().parents[1]'
)
text = text.replace(
    'DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)',
    'DEV_START, DEV_END = date(2021, 1, 4), date(2024, 12, 31)'
)
text = text.replace(
    'CONFIG_IDS = ["F3R2-A0", "F3R2-EW", "F3R2-ICW"]',
    'CONFIG_IDS = ["F3R2-A0"]'
)
text = text.replace(
    'experiment_id": "exp-20260919-factor-round-f3r2"',
    'experiment_id": "exp-20260921-f3r2-a0-validation"'
)
# The dev-only byte parity block is retained as a disclosure but cannot be
# applied to a different window. Force its adjudication flag to the explicit
# validation meaning after the comparison has been constructed.
text = text.replace(
    'regression["net_cagr_matches_v3_metrics"] = \\\n    abs(_cagr0 - V3_R306["net_cagr"]) <= 1e-12',
    'regression["net_cagr_matches_v3_metrics"] = None'
)
text = text.replace(
    'if not regression:',
    'if False:  # dev-only anchor assertion is not applicable to validation window'
)
dst.write_text(text, encoding="utf-8")
print(dst)
