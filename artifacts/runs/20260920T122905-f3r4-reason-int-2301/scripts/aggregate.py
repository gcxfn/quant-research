# -*- coding: utf-8 -*-
"""exp-20260920-factor-round-f3r4 -- stage B/C aggregation.

Reads the per-arm subruns written by scripts/runner_f3r4.py
(tmp/subruns/<tag>/{5 frames, stats.json}) plus the stage-A pre-generation
summary (tmp/composites_summary.json) and produces:

- the mechanical primary adjudication (prereg sec 5):
  net CAGR >= baseline + 0.003 AND max_drawdown >= baseline - 0.01;
  any arm passing -> H1, none -> H0; a value within 1e-4 of either line is an
  EDGE CASE -> stop and report;
- the eight-gate secondary table (F3R3 structure, not a judgement);
- holdings differences vs the F3R3-EW baseline sleeve (months whose member set
  differs; how often impairment/price_up flagged names were actually seated,
  entered or exited);
- outputs/sensitivity.json (A arm windows 20/40 + the b68 seam check);
- outputs/metrics_and_gates.json, outputs/sleeve_diff_<arm>.json;
- manifest.json (full identity, all numbers, status).

Deterministic; no RNG.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import platform
import sys
import time
from datetime import date
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

CHASSIS_RUN = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F2R1_RUN = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
T1_RUN = ROOT / "artifacts/runs/20260920T113527-t1-reason-event-b690"
RUNNER_F3R3 = CHASSIS_RUN / "scripts/runner_f3r3.py"
RUNNER_F3R4 = RUN_DIR / "scripts/runner_f3r4.py"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
PREREG_MD = ROOT / "docs/research/exp-20260920-factor-round-f3r4-prereg.md"
CONFIG_JSON = ROOT / "configs/experiments/f3r4-reason-integration.json"
BASE_COMPOSITE = F3R1_RUN / "outputs/F3-EW_composite.parquet"
EVENT_TABLE = T1_RUN / "outputs/events_dev.parquet"
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}
SUBRUNS = RUN_DIR / "tmp/subruns"
ARMS = ["F3R4-A", "F3R4-B", "F3R4-C"]
ANCHOR = "F3R4-LZO"
SENS = ["F3R4-A-w20", "F3R4-A-w40"]
B68 = "F3R4-A-b68"
BASE_CAGR = 0.04877310918741218
BASE_MDD = -0.17848532843799414
CAGR_ADD = 0.003
MDD_TOL = 0.01
EDGE = 1e-4
T0 = time.perf_counter()


def log(msg: object) -> None:
    print(f"[{time.perf_counter() - T0:7.1f}s] {msg}", flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stop(reason: str, detail: dict | None = None) -> None:
    log(f"!! STOP: {reason}")
    (RUN_DIR / "tmp" / "stop_report.md").write_text(
        "# STOP REPORT -- exp-20260920-factor-round-f3r4 (aggregation)\n\n"
        f"- stopped_at_stage: B/C aggregation\n- reason: {reason}\n"
        f"- detail: {json.dumps(detail or {}, ensure_ascii=False)}\n"
        f"- elapsed_s: {time.perf_counter() - T0:.1f}\n"
        "- no downgrade, no re-tuning; adjudication belongs to the main "
        "conversation.\n",
        encoding="utf-8", newline="\n")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name, "experiment_id":
            "exp-20260920-factor-round-f3r4", "status": "aborted",
        "stop_reason": reason, "stop_detail": detail},
        ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    sys.exit(2)


# === 0. inputs ==============================================================
log("== 0. load stage-A summary + subruns ==")
prep = json.loads((RUN_DIR / "tmp/composites_summary.json")
                  .read_text(encoding="utf-8"))
if prep["status"] != "completed":
    stop(f"stage A summary status = {prep['status']}")
runner_state = json.loads((RUN_DIR / "tmp/runner_f3r4_state.json")
                          .read_text(encoding="utf-8"))
if runner_state["status"] != "completed":
    stop(f"runner state status = {runner_state['status']}")
VERIFY_PATH = RUN_DIR / "tmp/verify_independent.json"
VERIFY = (json.loads(VERIFY_PATH.read_text(encoding="utf-8"))
          if VERIFY_PATH.exists() else None)
if VERIFY is not None and not VERIFY["verdict"]["all_checks_pass"]:
    stop("independent verification did not pass", VERIFY["verdict"])
log(f"  independent verification: "
    f"{'all checks pass' if VERIFY else 'not run yet'}")
# runner wall time: sum every invocation recorded in the runner log
RUNNER_WALLS = [float(ln.split("wall ")[1].split("s")[0])
                for ln in (RUN_DIR / "logs/runner_f3r4.log")
                .read_text(encoding="utf-8").splitlines()
                if "arm loop complete" in ln and "wall " in ln]
log(f"  runner invocations logged: {len(RUNNER_WALLS)} "
    f"(walls {RUNNER_WALLS}, total {sum(RUNNER_WALLS):.1f}s)")
# A superseded stage-A stop report from the first attempt is removed here: it
# recorded a bug in this run's OWN reversibility assertion (arm B changes only
# the price_up pairs, not every flagged pair), not a prereg/engine/spec seam;
# the corrected run completed.  Disclosure kept in the manifest.
DEV_STOPS = [{
    "stage": "A (event flags / composite pre-generation), first attempt",
    "reason": "F3R4-B: 1248 flagged (symbol, month) pairs but 451 rows changed "
              "value",
    "class": "own-check bug: the reversibility assertion demanded that EVERY "
             "flagged pair change value, but arm B suppresses only price_up; "
             "fixed by expecting the price_up pair count for B (451)",
    "impact": "none -- the run was re-executed from the start after the fix; "
              "2021+ never touched; no adjudication involved",
    "superseded_stop_report_removed": True}]
_stop = RUN_DIR / "tmp" / "stop_report.md"
if _stop.exists():
    _stop.unlink()
    log("  removed the superseded stage-A stop report (own-check bug, see "
        "manifest dev_stop_events)")

STATS: dict[str, dict] = {}
for tag in [ANCHOR] + ARMS + SENS + [B68]:
    p = SUBRUNS / tag / "stats.json"
    if not p.exists():
        stop(f"missing subrun stats for {tag}")
    STATS[tag] = json.loads(p.read_text(encoding="utf-8"))
    log(f"  {tag}: net {STATS[tag]['metrics']['net_cagr']!r} "
        f"mdd {STATS[tag]['metrics']['max_drawdown']!r}")
anchor = STATS[ANCHOR]["anchor_compare"]
if not (anchor and all(anchor[k] for k in
                       ("intents", "fills", "events", "daily", "clips_final",
                        "net_cagr_matches_chassis",
                        "max_drawdown_matches_chassis"))):
    stop("leave-zero-out anchor is not complete/passing", anchor)
log(f"  anchor gate: 5/5 frames .equals + net_cagr/maxDD bit-equal "
    f"({anchor['net_cagr']!r})")

flags = pl.read_parquet(RUN_DIR / "outputs/events_flag.parquet")
base_comp = pl.read_parquet(BASE_COMPOSITE)
base_log = json.loads((CHASSIS_RUN / "outputs/sleeve_monthly_log.json")
                      .read_text(encoding="utf-8"))["EW"]
base_members = {date.fromisoformat(e["month"]): set(e["members"])
                for e in base_log}
base_entries = {date.fromisoformat(e["month"]): set(e["entries"])
                for e in base_log}
base_exits = {date.fromisoformat(e["month"]): set(e["exits"])
              for e in base_log}
sig_days = sorted(base_members)
FLAG = {(r["signal_date"], r["symbol"]): r["class"]
        for r in flags.iter_rows(named=True)}
FLAGGED_SYMS = sorted({r["symbol"] for r in flags.iter_rows(named=True)})
log(f"  flags {flags.height} pairs, {len(FLAGGED_SYMS)} distinct symbols; "
    f"baseline sleeve log {len(base_log)} months")
if max(sig_days) > date(2020, 12, 31):
    stop(f"baseline sleeve log reaches {max(sig_days)} (freeze cut breach)")

# === 1. primary adjudication (mechanical, prereg sec 5) =====================
log("== 1. primary adjudication ==")
line = BASE_CAGR + CAGR_ADD
floor = BASE_MDD - MDD_TOL
main_rows = []
edges = []
for tag in ARMS:
    m = STATS[tag]["metrics"]
    net, mdd = m["net_cagr"], m["max_drawdown"]
    d_cagr, d_mdd = net - line, mdd - floor
    row = {"arm": tag, "net_cagr": net, "max_drawdown": mdd,
           "delta_vs_baseline": net - BASE_CAGR,
           "delta_vs_baseline_pp": (net - BASE_CAGR) * 100,
           "cagr_line": line, "cagr_margin": d_cagr,
           "mdd_floor": floor, "mdd_margin": d_mdd,
           "passes_cagr_line": net >= line,
           "passes_mdd_line": mdd >= floor,
           "pass": bool(net >= line and mdd >= floor)}
    for nm, dv in (("cagr", d_cagr), ("mdd", d_mdd)):
        if abs(dv) < EDGE:
            edges.append({"arm": tag, "criterion": nm, "margin": dv})
    main_rows.append(row)
    log(f"  {tag}: net {net*100:+.4f}% (delta {row['delta_vs_baseline_pp']:+.4f}pp"
        f", margin {d_cagr*100:+.4f}pp) mdd {mdd*100:.4f}% (margin "
        f"{d_mdd*100:+.4f}pp) -> "
        f"{'PASS' if row['pass'] else 'fail'}")
if edges:
    stop(f"EDGE CASE: {len(edges)} arm/criterion margin(s) within {EDGE} of the "
         f"frozen line -- hand to the main conversation", edges)
n_pass = sum(1 for r in main_rows if r["pass"])
h1 = n_pass > 0
verdict = "H1" if h1 else "H0"
passing = [r["arm"] for r in main_rows if r["pass"]]
log(f"  VERDICT: {verdict} ({n_pass}/{len(ARMS)} arms pass; passing "
    f"{passing or '-'})")

# === 2. eight gates (secondary, not a judgement) ============================
log("== 2. eight gates (F3R3 structure, secondary report) ==")
GATE_ROWS = [
    ("1_net_cagr_gt_0", "门1 净CAGR>0"), ("2_excess_vs_B1m_ge_2pp", "门2 超额≥2pp"),
    ("3_advantage_years_ge_5_of_6", "门3 优势年≥5/6"),
    ("4_mdd_le_20pct_and_le_B1m", "门4 maxDD≤20%且≤B1"),
    ("5_one_side_turnover_le_6", "门5 单边换手≤6"),
    ("6_single_name_weight_le_40pct", "门6 单票≤40%"),
    ("7_vs_B3prime_plus_1pp", "门7 ≥B3'+1pp"),
    ("8v3_final_delivery_ge_99pct", "门8v3 交付≥99%")]
gate_table = {}
for tag in ARMS + [ANCHOR]:
    g = STATS[tag]["gates"]["dev"]
    m = STATS[tag]["metrics"]
    gate_table[tag] = {
        "net_cagr": m["net_cagr"], "max_drawdown": m["max_drawdown"],
        "excess_vs_b1m": m["excess_vs_b1m"],
        "advantage_years": g["advantage_years"],
        "max_one_side_turnover": m["max_one_side_turnover"],
        "max_single_name_weight": m["max_single_name_weight"],
        "gate8v3": m["gate8_v3_final_delivery"],
        "failed_gates": g["failed_gates"], "dev_pass": g["dev_pass"],
        "by_key": {k: g[k] for k, _ in GATE_ROWS}}
    log(f"  {tag}: failed {g['failed_gates']}")

# === 3. holdings differences vs the baseline sleeve =========================
log("== 3. holdings differences vs F3R3-EW baseline ==")


def composite_ranked(path: Path) -> dict[date, list[str]]:
    df = pl.read_parquet(path)
    by_day: dict[date, dict[str, float]] = {}
    for r in df.iter_rows(named=True):
        by_day.setdefault(r["signal_date"], {})[r["symbol"]] = float(r["value"])
    return {t: sorted(by_day[t], key=lambda s: (-by_day[t][s], s))
            for t in sig_days}


ranked = {tag: composite_ranked(Path(STATS[tag]["composite"]["path"]))
          for tag in ARMS}
BASE_RANKED = composite_ranked(BASE_COMPOSITE)


def base_ranked_top10(t: date) -> list[str]:
    return BASE_RANKED[t][:10]


sleeve_diffs: dict = {}
for tag in ARMS:
    log_ = STATS[tag]["sleeve"]["log"]
    diffs_months, member_delta, entered, exited = [], 0, 0, 0
    flagged_seats = {"impairment": 0, "price_up": 0}
    flagged_entries = {"impairment": 0, "price_up": 0}
    flagged_exits = {"impairment": 0, "price_up": 0}
    flagged_months = {"impairment": 0, "price_up": 0}
    base_flagged_seats = {"impairment": 0, "price_up": 0}
    flagged_topk = {"impairment": 0, "price_up": 0}
    flagged_topk_baseline = {"impairment": 0, "price_up": 0}
    monthly_rows = []
    for e in log_:
        t = date.fromisoformat(e["month"])
        mem, bmem = set(e["members"]), base_members[t]
        if mem != bmem:
            diffs_months.append(str(t))
            member_delta += len(mem ^ bmem)
        entered += len(set(e["entries"]) - base_entries[t])
        exited += len(set(e["exits"]) - base_exits[t])
        fm = {"impairment": 0, "price_up": 0}
        bfm = {"impairment": 0, "price_up": 0}
        for s in e["members"]:
            c = FLAG.get((t, s))
            if c:
                fm[c] += 1
        for s in bmem:
            c = FLAG.get((t, s))
            if c:
                bfm[c] += 1
        for c in fm:
            flagged_seats[c] += fm[c]
            base_flagged_seats[c] += bfm[c]
            if fm[c]:
                flagged_months[c] += 1
        for s in e["entries"]:
            c = FLAG.get((t, s))
            if c:
                flagged_entries[c] += 1
        for s in e["exits"]:
            c = FLAG.get((t, s))
            if c:
                flagged_exits[c] += 1
        rk = ranked[tag][t]
        for i, s in enumerate(rk[:10]):
            c = FLAG.get((t, s))
            if c:
                flagged_topk[c] += 1
        month_rows_entry = {
            "month": str(t), "members_equal_baseline": mem == bmem,
            "n_members_symmetric_diff": len(mem ^ bmem),
            "flagged_seats": {c: fm[c] for c in fm if fm[c]},
            "baseline_flagged_seats": {c: bfm[c] for c in bfm if bfm[c]},
            "entries_not_in_baseline_entries":
                sorted(set(e["entries"]) - base_entries[t]),
            "exits_not_in_baseline_exits":
                sorted(set(e["exits"]) - base_exits[t])}
        monthly_rows.append(month_rows_entry)
    # top-10 flagged candidates under the BASELINE ranking (comparison basis)
    for t in sig_days:
        for s in base_ranked_top10(t):
            c = FLAG.get((t, s))
            if c:
                flagged_topk_baseline[c] += 1
    sleeve_diffs[tag] = {
        "months": len(log_),
        "months_with_different_member_set": len(diffs_months),
        "months_with_different_member_set_list": diffs_months,
        "member_set_symmetric_difference_sum": member_delta,
        "entries_not_in_baseline_entry_set": entered,
        "exits_not_in_baseline_exit_set": exited,
        "flagged_seat_months": flagged_seats,
        "baseline_flagged_seat_months": base_flagged_seats,
        "flagged_seat_months_delta": {c: flagged_seats[c]
                                      - base_flagged_seats[c] for c in flagged_seats},
        "flagged_months_present": flagged_months,
        "flagged_entries": flagged_entries,
        "flagged_exits": flagged_exits,
        "flagged_in_top10_of_arm_ranking": flagged_topk,
        "flagged_in_top10_of_baseline_ranking": flagged_topk_baseline,
        "monthly": monthly_rows}
    log(f"  {tag}: member-set differs in "
        f"{len(diffs_months)}/{len(log_)} months (sym-diff {member_delta}); "
        f"flagged seats impairment {flagged_seats['impairment']} (baseline "
        f"{base_flagged_seats['impairment']}), price_up "
        f"{flagged_seats['price_up']} (baseline "
        f"{base_flagged_seats['price_up']}); flagged entries "
        f"imp {flagged_entries['impairment']}/pu {flagged_entries['price_up']},"
        f" exits imp {flagged_exits['impairment']}/pu "
        f"{flagged_exits['price_up']}")


def base_ranked_top10(t: date) -> list[str]:
    return BASE_RANKED[t][:10]


BASE_RANKED = composite_ranked(BASE_COMPOSITE)
for tag in ARMS:
    (RUN_DIR / "outputs" / f"sleeve_diff_{tag.split('-')[-1]}.json").write_text(
        json.dumps(sleeve_diffs[tag], ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")

# === 4. sensitivity (disclosure only) =======================================
log("== 4. sensitivity + b68 seam check ==")
sens = {"role": "disclosure only; never changes the primary adjudication",
        "windows": {}, "b68": {}}
for tag in SENS:
    m = STATS[tag]["metrics"]
    w = tag.rsplit("-w", 1)[1]
    sens["windows"][f"w{w}"] = {
        "arm": tag, "net_cagr": m["net_cagr"],
        "max_drawdown": m["max_drawdown"],
        "delta_vs_baseline_pp": (m["net_cagr"] - BASE_CAGR) * 100,
        "passes_cagr_line": m["net_cagr"] >= line,
        "passes_mdd_line": m["max_drawdown"] >= floor,
        "failed_gates": STATS[tag]["gates"]["dev"]["failed_gates"]}
    log(f"  {tag}: net {m['net_cagr']*100:+.4f}% (delta "
        f"{(m['net_cagr']-BASE_CAGR)*100:+.4f}pp) mdd {m['max_drawdown']*100:.4f}%")
m68 = STATS[B68]["metrics"]
sens["b68"] = {
    "arm": B68, "b": prep["tf_s3"]["b_68_month_variant"],
    "net_cagr": m68["net_cagr"], "max_drawdown": m68["max_drawdown"],
    "delta_vs_baseline_pp": (m68["net_cagr"] - BASE_CAGR) * 100,
    "passes_cagr_line": m68["net_cagr"] >= line,
    "delta_vs_frozen_b_arm_pp": (m68["net_cagr"]
                                 - STATS["F3R4-A"]["metrics"]["net_cagr"]) * 100,
    "same_failed_gates_as_frozen": (STATS[B68]["gates"]["dev"]["failed_gates"]
                                    == STATS["F3R4-A"]["gates"]["dev"]
                                    ["failed_gates"]),
    "note": "the prereg writes 'median over 68 signal months' for b; the "
            "composite parquet holds 71 signal months.  The frozen arm "
            "parameter is the 71-month median; this row is the 68-month "
            "variant (2015-04-30..2020-11-30, the attribution run's "
            "forward-return coverage) run for disclosure only."}
log(f"  {B68}: b {sens['b68']['b']!r} net {m68['net_cagr']*100:+.4f}% "
    f"(vs frozen A {sens['b68']['delta_vs_frozen_b_arm_pp']:+.4f}pp)")
(RUN_DIR / "outputs/sensitivity.json").write_text(
    json.dumps(sens, ensure_ascii=False, indent=1), encoding="utf-8",
    newline="\n")

# === 5. runner diff (TF-S2) =================================================
log("== 5. derived-runner diff vs F3R3 original (TF-S2) ==")
a = RUNNER_F3R3.read_text(encoding="utf-8").splitlines()
b = RUNNER_F3R4.read_text(encoding="utf-8").splitlines()
diff = list(difflib.unified_diff(a, b, fromfile=str(RUNNER_F3R3),
                                 tofile=str(RUNNER_F3R4), lineterm="",
                                 n=2))
(RUN_DIR / "tmp/runner_f3r4_vs_f3r3.diff").write_text(
    "\n".join(diff) + "\n", encoding="utf-8", newline="\n")
added = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
removed = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
diff_meta = {
    "file": "tmp/runner_f3r4_vs_f3r3.diff",
    "sha256": sha256_file(RUN_DIR / "tmp/runner_f3r4_vs_f3r3.diff"),
    "lines_added": added, "lines_removed": removed,
    "source": str(RUNNER_F3R3), "source_sha256": sha256_file(RUNNER_F3R3),
    "derived": str(RUNNER_F3R4), "derived_sha256": sha256_file(RUNNER_F3R4),
    "declared_changes": [
        "composite input path (arm parquet from the command line instead of "
        "the F3R1 EW/ICW parquets)",
        "arm id / output prefix (argv tag -> tmp/subruns/<tag>/)",
        "engine pin (F3R3's v1.3 84a2443a -> the workspace v1.4.1 a01cb29c; "
        "precedent: the attribution run took the same step)",
        "dropped the F3R3-A0 rotation anchor config, the ICW arm, the "
        "momentum/rotation intent builder, the A0-vs-v3 regression block and "
        "the F3R3 report/manifest text (no arm number depends on them)",
    ],
    "verbatim": [
        "chassis legs sh.511010 15% + sh.518880 25%",
        "sleeve K=10 buffer membership (enter top-10, stay rank<=20)",
        "entry-side shenwan-L1 industry cap <= 2",
        "w_T = e_T*(0.06/0.90), 500,000 initial cash",
        "expiry/priority conventions and the engine call signature (no zones "
        "argument = v1.3 semantics)",
        "per-intent attribution, the eight gates (incl. gate 8 v3), the "
        "disclosures, the identity pins",
    ],
    "why_this_is_not_a_semantic_change": "the leave-zero-out anchor runs the "
        "SAME derived runner on the UNCHANGED F3-EW composite and reproduces "
        "the F3R3-EW outputs byte-for-byte (5/5 frames) with identical "
        "net_cagr/maxDD; every arm differs from the anchor only through its "
        "composite parquet",
}
log(f"  diff: +{added}/-{removed} lines, sha "
    f"{diff_meta['sha256'][:16]}; anchor evidence proves the delta is not "
    "semantic")

# === 6. outputs/metrics_and_gates.json ======================================
log("== 6. write metrics_and_gates.json ==")
mg = {
    "experiment_id": "exp-20260920-factor-round-f3r4",
    "engine_sha256": sha256_file(ENGINE_PY),
    "engine_sha256_16": sha256_file(ENGINE_PY)[:16],
    "prereg_sha256_16": sha256_file(PREREG_MD)[:16],
    "config_sha256_16": sha256_file(CONFIG_JSON)[:16],
    "event_table": {"path": str(EVENT_TABLE),
                    "sha256": sha256_file(EVENT_TABLE)},
    "base_composite": {"path": str(BASE_COMPOSITE),
                       "sha256": sha256_file(BASE_COMPOSITE)},
    "baseline": {"arm": "F3R3-EW (chassis verbatim)",
                 "net_cagr": BASE_CAGR, "max_drawdown": BASE_MDD,
                 "source": "F3R3 run outputs/metrics_and_gates.json verbatim"},
    "b": {"value": prep["tf_s3"]["b"], "months": prep["tf_s3"]["b_months_n"],
          "rule": prep["tf_s3"]["caliber"],
          "seam_note": prep["tf_s3"]["note"]},
    "leave_zero_out_anchor": {
        "tag": ANCHOR, "composite": str(BASE_COMPOSITE),
        "compare": {k: STATS[ANCHOR]["anchor_compare"][k] for k in
                    ("intents", "fills", "events", "daily", "clips_final",
                     "net_cagr_matches_chassis",
                     "max_drawdown_matches_chassis")},
        "net_cagr": STATS[ANCHOR]["metrics"]["net_cagr"],
        "max_drawdown": STATS[ANCHOR]["metrics"]["max_drawdown"],
        "verdict": "PASS (5/5 frames .equals + net_cagr/maxDD bit-equal)"},
    "adjudication": {
        "rule": "net CAGR >= baseline + 0.003 AND max_drawdown >= baseline "
                "- 0.01 (prereg sec 5)",
        "cagr_line": line, "mdd_floor": floor,
        "edge_band": EDGE, "edge_cases": edges,
        "arms": main_rows, "n_pass": n_pass, "verdict": verdict,
        "passing_arms": passing,
        "conclusion": ("H1 (exploratory): the event information is extractable "
                       "at the portfolio level in at least one arm"
                       if h1 else
                       "H0: all three arms fall short; the reason-category "
                       "line closes inside the F3 pipeline")},
    "gates": {tag: {"dev": STATS[tag]["gates"]["dev"]} for tag in ARMS},
    "gate_table": gate_table,
    "sleeve_diffs_vs_baseline": {tag: {k: v for k, v in
                                       sleeve_diffs[tag].items()
                                       if k != "monthly"} for tag in ARMS},
    "sensitivity": sens,
    "runner_derivation": diff_meta,
    "independent_verification": VERIFY,
    "spec_seams": {
        "TF-S1_parquet_equivalent_of_veto": "arm B suppresses price_up names "
            "to -10 at the composite layer, which is a parquet-level "
            "equivalent of a veto, not the engine's veto primitive: if every "
            "candidate of a month were suppressed a suppressed name could "
            "still be seated.  price_up pairs range "
            f"{min(r['n_price_up'] for r in prep['event_flags']['per_month'])}"
            f"..{max(r['n_price_up'] for r in prep['event_flags']['per_month'])}"
            " per month against an eligible set of >= 810 names, so the "
            "condition never fired (disclosed, expected probability ~0).",
        "TF-S2_runner_derivation": "see runner_derivation: composite input "
            "path + output prefix + engine pin only; the leave-zero-out anchor "
            "reproduces the F3R3-EW outputs byte-for-byte on this runner.",
        "TF-S3_b_and_z_event": "b, the monthly std series and the per-month "
            "z_event distributions are registered in manifest.json for "
            "independent recomputation; the 68-vs-71-month b ambiguity is "
            "disclosed and the frozen choice is the 71-month median.",
        "TF-S4_event_conflicts": "conflict rule executed mechanically: "
            f"{prep['event_flags']['diagnostics']['conflicts_resolved_later_wins']}"
            " (symbol, month) pairs had both classes within the window and "
            "were resolved by the later announcement; equal-ann_date ties: "
            f"{len(prep['event_flags']['diagnostics']['conflict_ties'])}.",
    },
    "val_consumed": False, "advanced_to_validation": False,
    "trial_accounting": {"this_round": 3, "arms": ARMS,
                         "anchor_not_counted": True,
                         "strategy_line": "293->296"},
    "grade": "exploratory only: the event study already consumed the dev "
             "sample and this experiment re-uses the same window; no "
             "out-of-sample claim; val (frozen) untouched",
}
(RUN_DIR / "outputs/metrics_and_gates.json").write_text(
    json.dumps(mg, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")

# === 7. manifest.json =======================================================
log("== 7. write manifest.json ==")
pins = {name: {"path": str(p), "sha256": sha256_file(p)}
        for name, p in [
            ("engine", ENGINE_PY), ("prereg", PREREG_MD),
            ("config", CONFIG_JSON), ("events_dev", EVENT_TABLE),
            ("base_composite", BASE_COMPOSITE),
            ("runner_f3r4", RUNNER_F3R4), ("runner_f3r3_source", RUNNER_F3R3),
            ("chassis_metrics", CHASSIS_RUN / "outputs/metrics_and_gates.json"),
            ("chassis_sleeve_log", CHASSIS_RUN / "outputs/sleeve_monthly_log.json"),
            ("dedup_clusters", F3R1_RUN / "outputs/dedup_clusters.csv"),
            ("f2r1_all120", F2R1_RUN / "outputs/f2r1_all120.csv")]}
pins["engine"]["version"] = "v1.4.1 (non-zones path = v1.3 semantics)"
pins["engine"]["sha256_at_run_start"] = runner_state["engine_sha_at_start"]
pins["engine"]["sha256_at_run_end"] = runner_state["engine_sha_at_end"]
pins["engine"]["bytes_modified_by_this_run"] = \
    runner_state["bytes_modified_by_this_run"]
reps = sorted(pl.read_csv(F3R1_RUN / "outputs/dedup_clusters.csv")
              ["representative"].to_list())
for fid in reps:
    p = F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]] / f"{fid}.parquet"
    pins[f"rep_{fid}"] = {"path": str(p), "sha256": sha256_file(p)}
for tag in [ANCHOR] + ARMS + SENS + [B68]:
    pins[f"subrun_{tag}_stats"] = {
        "path": str(SUBRUNS / tag / "stats.json"),
        "sha256": sha256_file(SUBRUNS / tag / "stats.json")}
out_files = {p.name: {"sha256": sha256_file(p), "bytes": p.stat().st_size}
             for p in sorted((RUN_DIR / "outputs").iterdir()) if p.is_file()}
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260920-factor-round-f3r4",
    "title": "F3R4 归因事件信息并入 F3 组合（三臂）",
    "status": "completed",
    "started_at": prep["started_at"],
    "ended_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "wall_seconds": prep["wall_seconds"] + sum(RUNNER_WALLS)
                    + (time.perf_counter() - T0),
    "wall_breakdown_s": {"stage_a_pre_generation": prep["wall_seconds"],
                         "runner_invocations": RUNNER_WALLS,
                         "runner_total": sum(RUNNER_WALLS),
                         "aggregation": time.perf_counter() - T0},
    "peak_rss_gb": runner_state["peak_rss_gb"],
    "env_versions": {**prep["env"], "runner": runner_state["env_versions"]},
    "random_seed": None,
    "determinism": "no RNG in the pre-generation, the runner or the engine; "
                   "the arms differ only through their composite parquet",
    "pins": pins,
    "window": {"dev": "2015-01-05..2020-12-31",
               "signals": f"{sig_days[0]}..{sig_days[-1]} ({len(sig_days)})",
               "val_consumed": False},
    "stage_timings_s": {"pre_generation": prep["stages_s"],
                        "runner": runner_state["stages_s"]},
    "b_and_tf_s3": prep["tf_s3"],
    "event_flags": prep["event_flags"],
    "event_flag_files": prep["event_flag_files"],
    "reversibility": prep["reversibility"],
    "fa_s2_alignment": prep["fa_s2"],
    "c_alignment": prep["c_alignment"],
    "z_event": prep["z_event"],
    "composite_files": prep["composite_files"],
    "arm_parameters": prep["arm_parameters"],
    "leave_zero_out_anchor": STATS[ANCHOR]["anchor_compare"],
    "arms": {tag: {"metrics": STATS[tag]["metrics"],
                   "gates": STATS[tag]["gates"],
                   "composite": STATS[tag]["composite"],
                   "sleeve_diag": {k: v for k, v in
                                   STATS[tag]["sleeve"]["diag"].items()},
                   "engine_wall_s": STATS[tag]["engine_wall_s"],
                   "arm_wall_s": STATS[tag]["arm_wall_s"],
                   "disclosures": STATS[tag]["disclosures"]}
             for tag in ARMS},
    "sensitivity": sens,
    "adjudication": mg["adjudication"],
    "runner_derivation": diff_meta,
    "independent_verification": VERIFY,
    "spec_seams": mg["spec_seams"],
    "grade": mg["grade"],
    "trial_accounting": mg["trial_accounting"],
    "outputs": out_files,
    "stop_report_written": False,
    "dev_stop_events": DEV_STOPS,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")
log(f"== aggregation complete: verdict {verdict}, manifest written, wall "
    f"{time.perf_counter() - T0:.0f}s ==")
