# -*- coding: utf-8 -*-
"""exp-20260920-factor-attribution -- finalize manifest.json.

Assembles the run-level manifest from the stage summaries and subrun stats.
Identities: engine sha (start==end, read-only), every input data sha,
z-score source path+method, stage timings, peak RSS, trial accounting,
status.  No engine or data file is modified.
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
CHASSIS_RUN = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F2R1_RUN = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
ENGINE_SHA_EXPECT = "a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1f0a466b0675abf3"
engine_sha = sha256_file(ENGINE_PY)

attr_summary = json.loads((RUN_DIR / "tmp" / "attribution_summary.json")
                          .read_text(encoding="utf-8"))
runner_state = json.loads((RUN_DIR / "tmp" / "runner_attrib_state.json")
                          .read_text(encoding="utf-8"))
verdict = json.loads((RUN_DIR / "outputs" / "verdict.json").read_text(encoding="utf-8"))
import polars as pl  # noqa: E402
REPS = sorted(pl.read_csv(F3R1_RUN / "outputs/dedup_clusters.csv")
              ["representative"].to_list())

subruns = {}
for d in sorted((RUN_DIR / "tmp" / "subruns").iterdir()):
    if (d / "stats.json").exists():
        st = json.loads((d / "stats.json").read_text(encoding="utf-8"))
        subruns[st["tag"]] = {
            "drop": st["drop"], "net_cagr": st["net_cagr"],
            "max_drawdown": st["max_drawdown"],
            "advantage_years": st["advantage_years"],
            "max_one_side_turnover": st["max_one_side_turnover"],
            "engine_wall_s": st["engine_wall_s"],
            "anchor_pass": (None if st["anchor_compare"] is None
                            else all(st["anchor_compare"].values()))}


def invocation_wall_s(log_name: str) -> float:
    """Parse the final 'subset loop complete: wall NNs' from a runner log."""
    import re
    txt = (RUN_DIR / "logs" / log_name).read_text(encoding="utf-8")
    m = re.findall(r"subset loop complete: \d+ subsets, wall (\d+)s", txt)
    return float(m[-1]) if m else float("nan")


anchor_wall = invocation_wall_s("runner_anchor_stdout.log")
loo_wall = invocation_wall_s("runner_loo_stdout.log")

outputs = {}
for p in sorted((RUN_DIR / "outputs").iterdir()):
    outputs[p.name] = sha256_file(p)
scripts = {p.name: sha256_file(p) for p in sorted((RUN_DIR / "scripts").iterdir())}

anchor = runner_state["subsets_done"][0] if runner_state.get("subsets_done") else None
anchor_stats = json.loads((RUN_DIR / "tmp/subruns/leave_zero_out/stats.json")
                          .read_text(encoding="utf-8"))

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260920-factor-attribution",
    "prereg": "docs/research/exp-20260920-factor-attribution-prereg.md",
    "prereg_sha256_16": sha256_file(ROOT / "docs/research/exp-20260920-factor-attribution-prereg.md")[:16],
    "status": "completed",
    "started_at_utc": None,  # filled below from stage summaries
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": round(attr_summary["wall_seconds"] + anchor_wall + loo_wall, 1),
    "wall_seconds_breakdown": {
        "A_attribution_invocation": round(attr_summary["wall_seconds"], 1),
        "B_anchor_invocation": anchor_wall,
        "B_loo_batch_invocation": loo_wall},
    "peak_rss_gb": max(attr_summary["peak_rss_gb"], runner_state["peak_rss_gb"]),
    "command": [str(ROOT / ".venv/Scripts/python.exe"),
                f"artifacts/runs/{RUN_DIR.name}/scripts/attribution.py",
                "&&",
                str(ROOT / ".venv/Scripts/python.exe"),
                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_attrib.py --subsets ..."],
    "random_seed": None,
    "determinism": "no RNG anywhere (attribution arithmetic + engine "
                   "deterministic lifecycle); LOO composite rebuilds are "
                   "pure functions of pinned inputs",
    "engine": {
        "path": str(ENGINE_PY),
        "sha256_at_start": ENGINE_SHA_EXPECT,
        "sha256_at_end": engine_sha,
        "sha256_match": engine_sha == ENGINE_SHA_EXPECT,
        "bytes_modified_by_this_run": engine_sha != ENGINE_SHA_EXPECT,
        "version": "workspace v1.4.1 pin a01cb29c...75abf3, run in v1.3 "
                   "semantics (no zones argument); leave-zero-out anchor "
                   "5/5 frames .equals() vs chassis v1.3 outputs"},
    "window": {"dev": "2015-01-05..2020-12-31",
               "signals": "2015-01-30..2020-11-30 (71 month-ends)",
               "attribution_r_months": "68 (2015-04-30..2020-11-30; F2R1 "
                                       "harness min_history_rows=60 "
                                       "truncation, documented in eval.py)",
               "val_consumed": False, "frozen_zone_touched": False},
    "inputs": {
        "chassis_run": {"path": str(CHASSIS_RUN), "status": "completed",
                        "engine_v13_pin_16": "84a2443ac28fe1b8",
                        "baseline_F3R3-EW": {
                            "net_cagr": verdict["baseline"]["net_cagr"],
                            "max_drawdown": verdict["baseline"]["max_drawdown"],
                            "source": "chassis metrics_and_gates.json "
                                      "metrics['F3R3-EW'] verbatim"}},
        "factor_scores_source": {
            "method": "FA-S2 branch 1: DIRECT READ of F2R1 family outputs "
                      "(per-factor monthly score parquets); no factor-value "
                      "recomputation needed; composite components rebuilt "
                      "from these parquets with the F3R1 sec 4 construction "
                      "and verified bit-identical to the F3R1 EW composite",
            "run": str(F2R1_RUN),
            "files": {fid: attr_summary["pins"][f"rep_{fid}"]["sha256"]
                      for fid in REPS},
            "f2r1_all120_sha256": attr_summary["pins"]["f2r1_all120"]["sha256"]},
        "composite_alignment": attr_summary["fa_s2"],
        "sleeve_positions": str(CHASSIS_RUN / "outputs/sleeve_monthly_log.json"),
        "eval_panel": {"path": attr_summary["r_months"]["panel"],
                       "sha256": attr_summary["r_months"]["panel_sha256"],
                       "note": "F2R1 frozen eval panel (daily_2015_2024), "
                               "read-only; truncated <=2020-12-31 in memory "
                               "before the harness (trailing-row removal, "
                               "identical values, zero 2021+ contact)"},
        "daily_calendar_pools": {"path": attr_summary["pins"]["daily_calendar_pools"]["path"],
                                 "sha256": attr_summary["pins"]["daily_calendar_pools"]["sha256"]},
        "dedup_clusters": attr_summary["pins"]["dedup_clusters"]["sha256"],
    },
    "stages_s": {"A_attribution": attr_summary["stages_s"],
                 "B_loo_runner": runner_state.get("stages_s", {})},
    "leave_zero_out_anchor": {
        "pass": all(anchor_stats["anchor_compare"].values()),
        "frames": anchor_stats["anchor_compare"],
        "net_cagr": anchor_stats["net_cagr"],
        "baseline_cagr": verdict["baseline"]["net_cagr"]},
    "loo_runs": subruns,
    "verdict": verdict,
    "sanity": attr_summary["sanity"],
    "trial_accounting": {
        "this_round": "18 new configs = attribution 1 + LOO 17 + clean 0 "
                      "(clean skipped: suspect list empty); leave-zero-out "
                      "anchor NOT counted (repeat of the already-run "
                      "F3R3-EW config, per prereg '不重复计已运行配置')",
        "strategy_line": "275->293"},
    "env_versions": attr_summary["env"],
    "scripts_sha256": scripts,
    "outputs_sha256": outputs,
    "notes": [
        "FA-S3 approximation: attribution table is cross-factor comparison "
        "only; sum_i weight_i*c_i,t is NOT a portfolio return.",
        "The ICW attribution is a same-caliber companion table; all frozen "
        "judgment lines act on the EW main table only.",
        "Sanity series definition (documented): realized_t = seat-weighted "
        "next-month return of the seated members with harness r (w_T per "
        "seat from the chassis sleeve log); linear_t = sum_i (1/17)*c_i,t. "
        "65 common months (harness r starts 2015-04-30)."],
    "advanced_to_validation": False,
    "val_consumed": False,
}
# chassis comparison-frame identities + started_at
manifest["inputs"]["chassis_ew_frames"] = {
    "intents": sha256_file(CHASSIS_RUN / "outputs/F3R3-EW_intents.parquet"),
    "fills": sha256_file(CHASSIS_RUN / "outputs/F3R3-EW_fills.parquet"),
    "events": sha256_file(CHASSIS_RUN / "outputs/F3R3-EW_events.parquet"),
    "daily_equity": sha256_file(CHASSIS_RUN / "outputs/F3R3-EW_daily_equity.parquet"),
    "clips_final": sha256_file(CHASSIS_RUN / "outputs/F3R3-EW_clips_final.parquet")}
manifest["started_at_utc"] = "2026-09-20T02:41:00+00:00 (stage A first launch)"

(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
print("manifest written; status:", manifest["status"],
      "; anchor pass:", manifest["leave_zero_out_anchor"]["pass"],
      "; loo runs:", len(subruns))
