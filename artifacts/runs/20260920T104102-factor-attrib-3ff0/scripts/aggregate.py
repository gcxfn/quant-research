# -*- coding: utf-8 -*-
"""exp-20260920-factor-attribution -- aggregation + frozen verdict lines.

Mechanical application of prereg sec 5 (no narrative judgment):
- sec 5.1 suspect line already applied by attribution.py (outputs/suspects.json)
- sec 5.2 condemnation line per suspect: drop-i net CAGR >= baseline + 0.30pp
  AND maxDD deterioration <= 1.0pp -> confirm removal; else retain (observe)
- sec 5.3 adoption line for the clean combo (only if S non-empty)
- sec 5.4 empty suspect list -> H1 falsified, F3 combo keeps 17 factors
Baseline = chassis metrics F3R3-EW (net_cagr, max_drawdown) verbatim.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
CHASSIS_MG = json.loads((ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
                         / "outputs/metrics_and_gates.json").read_text(encoding="utf-8"))
BASE_CAGR = CHASSIS_MG["metrics"]["F3R3-EW"]["net_cagr"]
BASE_MDD = CHASSIS_MG["metrics"]["F3R3-EW"]["max_drawdown"]

suspects_doc = json.loads((RUN_DIR / "outputs" / "suspects.json")
                          .read_text(encoding="utf-8"))
SUSPECTS = [r["factor"] for r in suspects_doc["suspects"]]

sub_dir = RUN_DIR / "tmp" / "subruns"


def stats_of(tag: str) -> dict:
    return json.loads((sub_dir / tag / "stats.json").read_text(encoding="utf-8"))


anchor = stats_of("leave_zero_out")
assert not anchor["drop"]
anchor_ok = bool(anchor["anchor_compare"]) and all(anchor["anchor_compare"].values())

rows = []
loo: dict[str, dict] = {}
for f in sorted(p.name for p in sub_dir.iterdir() if p.is_dir()):
    if f == "leave_zero_out":
        continue
    st = stats_of(f)
    fid = st["drop"][0]
    loo[fid] = st
    rows.append({
        "factor": fid,
        "net_cagr": st["net_cagr"],
        "max_drawdown": st["max_drawdown"],
        "delta_cagr_vs_baseline": st["net_cagr"] - BASE_CAGR,
        "dd_deterioration_pp": st["max_drawdown"] - BASE_MDD,
        "advantage_years": st["advantage_years"],
        "max_one_side_turnover": st["max_one_side_turnover"]})

cols = ["factor", "net_cagr", "max_drawdown", "delta_cagr_vs_baseline",
        "dd_deterioration_pp", "advantage_years", "max_one_side_turnover"]
import polars as pl  # noqa: E402
pl.DataFrame(rows).select(cols).write_csv(RUN_DIR / "outputs" / "loo_matrix.csv")

# --- sec 5.2 condemnation (mechanical, suspects only) ------------------------
condemned, retained = [], []
for fid in SUSPECTS:
    st = loo.get(fid)
    if st is None:
        raise SystemExit(f"suspect {fid} has no LOO run -- inconsistent state")
    d_cagr = st["net_cagr"] - BASE_CAGR
    d_mdd = st["max_drawdown"] - BASE_MDD
    if d_cagr >= 0.0030 and d_mdd >= -0.010:
        condemned.append({"factor": fid, "delta_cagr": d_cagr,
                          "dd_deterioration": d_mdd})
    else:
        retained.append({"factor": fid, "delta_cagr": d_cagr,
                         "dd_deterioration": d_mdd})

# --- verdict (sec 5.4 / 1) ---------------------------------------------------
if not SUSPECTS:
    verdict = {
        "H1": "falsified",
        "H0": "confirmed",
        "reason": "prereg sec 5.4: suspect list EMPTY -> H1 falsified, F3 "
                  "combo keeps the 17-factor composite unchanged; sec 5.2 "
                  "condemnation and sec 5.3 clean-combo steps are vacuous "
                  "(no suspects to judge, nothing to adopt)",
        "suspects": [], "condemned": [], "retained_observe": [],
        "clean_combo_run": False,
        "baseline": {"net_cagr": BASE_CAGR, "max_drawdown": BASE_MDD}}
else:
    verdict = {
        "H1": ("confirmed" if condemned else "falsified"),
        "H0": ("falsified" if condemned else "confirmed"),
        "suspects": SUSPECTS, "condemned": condemned,
        "retained_observe": retained,
        "clean_combo_run": bool(condemned),
        "baseline": {"net_cagr": BASE_CAGR, "max_drawdown": BASE_MDD}}
    if not condemned:
        verdict["reason"] = ("suspects exist but none passes the sec 5.2 "
                             "condemnation line -> H1 falsified (sec 5.4 "
                             "second arm: '全部嫌疑因子剔除后组合不满足定罪线' "
                             "degenerate case: nothing to remove)")
verdict["leave_zero_out_anchor"] = {
    "pass": anchor_ok,
    "frames": anchor["anchor_compare"],
    "net_cagr": anchor["net_cagr"]}
verdict["loo_max_delta_cagr"] = (
    max((r["delta_cagr_vs_baseline"] for r in rows), default=None))
(RUN_DIR / "outputs" / "verdict.json").write_text(
    json.dumps(verdict, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({"anchor_pass": anchor_ok, "n_loo": len(rows),
                  "suspects": SUSPECTS, "condemned": [c["factor"] for c in condemned],
                  "H1": verdict["H1"],
                  "loo_max_delta_cagr_pp": (None if verdict["loo_max_delta_cagr"] is None
                                            else verdict["loo_max_delta_cagr"] * 100)},
                 ensure_ascii=False))
