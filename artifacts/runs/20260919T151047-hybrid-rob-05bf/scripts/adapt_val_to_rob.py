# -*- coding: utf-8 -*-
"""adapt val hybrid runner -> robustness-round runner (exp-20260919-hybrid-robustness).

Base: artifacts/runs/20260919T151630-hybrid-val-v1p3/scripts/runner_hybrid_val.py
(engine v1.3 pin 84a2443a...082c, VAL_WINDOW switch, corporate_actions dev
branch, B1m dev port-check all already present).  Output: runner_hybrid_rob.py.

Prereg (docs/research/exp-20260919-hybrid-robustness-prereg.md, FROZEN):
12 configs (RB-A0 anchor = R3-06 verbatim + 11 neighborhood probes), dev
window pinned (no val), anchor compares against the v3 run's R3-06 outputs
(5 frames byte-equal + net_cagr 1e-12), NO selection semantics (prereg sec
0/2: exploration-grade only), trial accounting +11 (241->252, anchor not
counted).

Every replacement asserts a unique hit (or an exact expected count) and the
script aborts on any mismatch -- no silent partial adaptation.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "runner_hybrid_val.py")
DST = os.path.join(HERE, "runner_hybrid_rob.py")

s = io.open(SRC, encoding="utf-8").read()
n0 = len(s)
reps = []


def rep(old, new, count=1):
    global s
    c = s.count(old)
    assert c == count, f"expected {count} hit(s), got {c}: {old[:80]!r}"
    s = s.replace(old, new)
    reps.append((old.splitlines()[0][:60], c))


# --- A. docstring --------------------------------------------------------------
rep('''"""exp-20260919-hybrid-family-v2 runner -- engine v1.2 (pin unchanged), prereg FROZEN.

Copy-adapted from the v2 runner (20260919T063022-hybrid-v2-2k5b) per the v3
prereg (docs/research/exp-20260919-hybrid-family-v3-prereg.md +
configs/experiments/hybrid-family-v3.json); v2-prereg clauses (universe,
band table, dividend rule, runner assertions, fees, window, Design B leg
semantics, gates 1-7 R16 + gate 8 v3, benchmarks) inherited verbatim.
v3 differences only (user hypothesis: lower the bond weight in ROT-05):
- 7 configs (R3-A0 anchor + R3-01..06 bond-weight ladder): bond 0.25 ->
  0.20/0.15/0.10/0, the freed weight either idle cash (R3-01..04) or a
  third rotation slot (R3-05 top3x0.25, R3-06 top3x0.20);
- R3-A0 = ROT-05 verbatim replica and regression anchor: 5-frame polars
  .equals() vs the v2 run's ROT-05 outputs (intents/fills/events/daily/
  clips_final) + net_cagr match; mismatch aborts before other configs;
- no stock-engine configs: displacement disclosure is ROTATION fills vs
  R3-A0; bond-ladder monotonicity disclosure replaces the v2 ROT-04/ROT-01
  universe-sensitivity block (v3 prereg sec 4-3);
- stop clauses per the user's 2026-09-19 ruling: pass + >=10% -> STOP and
  report (goal hit); pass but <10% -> bookkeep and CONTINUE dev; all
  eliminated -> ROT branch paused.  val stays unconsumed.
- cash earns zero in the engine (no money-market yield): cash-redeploy
  variants are slightly pessimistic vs reality (conservative, disclosed).

Deterministic; no RNG.  Spec seams are NOT silently resolved: they are
recorded and reported.  Budget 1200 s wall (prereg sec 6).
"""''',
     '''"""exp-20260919-hybrid-robustness runner -- engine v1.3 (pin unchanged),
prereg FROZEN (docs/research/exp-20260919-hybrid-robustness-prereg.md).

Copy-adapted from the val runner (20260919T151630-hybrid-val-v1p3) by
adapt_val_to_rob.py (asserted unique replacements only); all v3-inherited
clauses (universe, band table, dividend rule, runner assertions, fees,
Design B leg semantics, gates 1-7 R16 + gate 8 v3, benchmarks) verbatim.
Robustness-round differences (prereg sec 0-4; robustness NOT selection):
- 12 configs (RB-A0 anchor + 11 neighborhood probes) on the dev window
  (2015-2020) only; VAL_WINDOW ignored, dev pinned (prereg sec 0/1);
- RB-A0 = R3-06 verbatim replica and regression anchor: 5-frame polars
  .equals() vs the v3 run's (20260919T110500-hybrid-v3-r3ld) R3-06 outputs
  (intents/fills/events/daily/clips_final) + net_cagr 1e-12 vs v3 metrics;
  mismatch aborts before other configs (prereg sec 4);
- neighborhoods (prereg sec 1): RB-01/02 = R3-06 lookback 4m/9m; RB-03/04 =
  R3-06 slots 2x0.30 / 4x0.15 (rotation weight constant 60%); RB-05/06 =
  R3-05 lookback 4m/9m; RB-07/08 = R3-05 slots 2x0.375 / 4x0.1875 (75%);
  RB-09/10/11 = R3-06 universe minus 513100 / 513500 / 159915;
- NO selection (prereg sec 0): every neighborhood result is
  exploration-grade (dev-only, post-val, meta-overfitting discount); no new
  champion, no ledger elimination semantics; prereg sec 2 readout is three
  descriptive ratios (all-8-gate pass, excess within champion +/-1pp,
  maxDD <= 20%); trial accounting +11 (241->252), anchor not counted;
- corporate_actions dev branch (0 events, arg None) and dividend expect
  (18 dev events) unchanged; engine v1.3 sha 84a2443a...082c pinned
  (checked at start and end); val not consumed.

Deterministic; no RNG.  Spec seams are NOT silently resolved: they are
recorded and reported.  Budget 2700 s wall (12 configs).
"""''')

# --- B. run-path constants: V2_RUN -> V3_RUN, prereg file ----------------------
rep('V2_RUN = ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b"',
    'V3_RUN = ROOT / "artifacts/runs/20260919T110500-hybrid-v3-r3ld"')
rep('PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v3-prereg.md"',
    'PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-robustness-prereg.md"')

# --- C. window: dev pinned (VAL_WINDOW ignored) --------------------------------
rep('_WINDOW = os.environ.get("VAL_WINDOW", "dev")',
    '_WINDOW = "dev"   # rob round: window pinned to dev (prereg sec 0); '
    'VAL_WINDOW ignored')

# --- D. CONFIG_IDS -> 12 rob configs -------------------------------------------
rep('CONFIG_IDS = ["R3-A0", "R3-05", "R3-06"]',
    'CONFIG_IDS = ["RB-A0", "RB-01", "RB-02", "RB-03", "RB-04", "RB-05",\n'
    '              "RB-06", "RB-07", "RB-08", "RB-09", "RB-10", "RB-11"]')

# --- E. CFGS block -> prereg sec 1 matrix (12 = 1 anchor + 11 neighborhoods) ---
rep('''# config table (v3 prereg sec 2 / config json configs): bond-weight
# ladder on the ROT-05 structure; every leg symbol <= 25%; R3-A0 = ROT-05
# verbatim replica used ONLY as the regression anchor
UNI7 = [m for m in MEMBERS if m != "sh.511010"]          # 8 - leg 511010
UNI6 = [m for m in MEMBERS
        if m not in ("sh.511010", "sh.518880")]          # 8 - both legs
CFGS = {
    "R3-A0": {"stock": None, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},   # = ROT-05 verbatim
    "R3-05": {"stock": None, "legs": {"sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-06": {"stock": None, "legs": {"sh.511010": 0.15,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.20,
                           "lookback_m": 6}},
}''',
     '''# config table (rob prereg sec 1, FROZEN): 1 anchor + 11 neighborhood
# probes on the R3-06 / R3-05 structures; every leg symbol <= 25%;
# RB-A0 = R3-06 verbatim replica used ONLY as the regression anchor
UNI7 = [m for m in MEMBERS if m != "sh.511010"]          # 8 - leg 511010
UNI6 = [m for m in MEMBERS
        if m not in ("sh.511010", "sh.518880")]          # 8 - both legs
UNI6_NO_513100 = [m for m in UNI6 if m != "sh.513100"]   # RB-09
UNI6_NO_513500 = [m for m in UNI6 if m != "sh.513500"]   # RB-10
UNI6_NO_159915 = [m for m in UNI6 if m != "sz.159915"]   # RB-11
_LEGS_R306 = {"sh.511010": 0.15, "sh.518880": 0.25}      # R3-06 legs verbatim
_LEGS_R305 = {"sh.518880": 0.25}                         # R3-05 legs verbatim
CFGS = {
    # anchor: R3-06 verbatim (bond 0.15 + gold 0.25 legs, top3 x 0.20, 6m)
    "RB-A0": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.20,
                           "lookback_m": 6}},   # = R3-06 verbatim
    # lookback neighborhood (R3-06 base)
    "RB-01": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.20,
                           "lookback_m": 4}},
    "RB-02": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.20,
                           "lookback_m": 9}},
    # slot neighborhood (R3-06 base; rotation total weight constant 60%)
    "RB-03": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.30,
                           "lookback_m": 6}},
    "RB-04": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6, "top_n": 4, "weight": 0.15,
                           "lookback_m": 6}},
    # lookback neighborhood (R3-05 base)
    "RB-05": {"stock": None, "legs": _LEGS_R305,
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.25,
                           "lookback_m": 4}},
    "RB-06": {"stock": None, "legs": _LEGS_R305,
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.25,
                           "lookback_m": 9}},
    # slot neighborhood (R3-05 base; rotation total weight constant 75%)
    "RB-07": {"stock": None, "legs": _LEGS_R305,
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.375,
                           "lookback_m": 6}},
    "RB-08": {"stock": None, "legs": _LEGS_R305,
              "rotation": {"universe": UNI6, "top_n": 4, "weight": 0.1875,
                           "lookback_m": 6}},
    # per-member universe drops (R3-06 base)
    "RB-09": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6_NO_513100, "top_n": 3,
                           "weight": 0.20, "lookback_m": 6}},
    "RB-10": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6_NO_513500, "top_n": 3,
                           "weight": 0.20, "lookback_m": 6}},
    "RB-11": {"stock": None, "legs": _LEGS_R306,
              "rotation": {"universe": UNI6_NO_159915, "top_n": 3,
                           "weight": 0.20, "lookback_m": 6}},
}''')

# --- F. budget: 12 configs ------------------------------------------------------
rep("BUDGET_S = 1200.0", "BUDGET_S = 2700.0   # 12 configs (rob adaptation)")

# --- G. identity pins: v3 anchor artifacts --------------------------------------
rep('''    "v2_metrics_rot05_anchor_source":
        (None, V2_RUN / "outputs/metrics_and_gates.json"),''',
     '''    "v3_metrics_r306_anchor_source":
        (None, V3_RUN / "outputs/metrics_and_gates.json"),
    "v3_r306_intents": (None, V3_RUN / "outputs/R3-06_intents.parquet"),
    "v3_r306_fills": (None, V3_RUN / "outputs/R3-06_fills.parquet"),
    "v3_r306_events": (None, V3_RUN / "outputs/R3-06_events.parquet"),
    "v3_r306_daily": (None, V3_RUN / "outputs/R3-06_daily_equity.parquet"),
    "v3_r306_clips": (None, V3_RUN / "outputs/R3-06_clips_final.parquet"),''')

# --- H. v3 metrics read (anchor reference) --------------------------------------
rep('''v2_mg = json.loads((V2_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))''',
     '''v3_mg = json.loads((V3_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))''')

# --- I. section-10 header ---------------------------------------------------------
rep('''# === 10. R3-A0 regression anchor vs v2 ROT-05 ==============================
log("== 10. R3-A0 regression anchor vs v2 ROT-05 ==")''',
     '''# === 10. RB-A0 regression anchor vs v3 R3-06 ===============================
log("== 10. RB-A0 regression anchor vs v3 R3-06 ==")''')

# --- J. anchor regression block: compare v3 R3-06 --------------------------------
rep('''# R3-A0 regression: 5-frame .equals vs the v2 run's ROT-05 outputs +
# net_cagr must equal the v2 metric (R3-A0 is NOT re-adjudicated)
results["R3-A0"] = run_one("R3-A0")
r0 = results["R3-A0"]["res"]
_sd, _sv = er.slice_curve(r0.daily["date"].to_list(),
                          r0.daily["equity"].to_list(), DEV_START, DEV_END)
_cagr0 = er.cagr(_sv[0], _sv[-1], _sd[0], _sd[-1])
v2_rot05 = v2_mg["metrics"]["ROT-05"]
ref = {name: pl.read_parquet(V2_RUN / "outputs" / fn) for name, fn in
       (("intents", "ROT-05_intents.parquet"),
        ("fills", "ROT-05_fills.parquet"), ("events", "ROT-05_events.parquet"),
        ("daily", "ROT-05_daily_equity.parquet"),
        ("clips_final", "ROT-05_clips_final.parquet"))}
regression = {}
for name, mine in (("intents", FRAMES["R3-A0"]), ("fills", r0.fills),
                   ("events", r0.events), ("daily", r0.daily),
                   ("clips_final", r0.clips_final)):
    same = mine.equals(ref[name])
    regression[name] = same
    log(f"  R3-A0 {name}.equals(v2 ROT-05 {name}) = {same} "
        f"(mine {mine.height} rows / ref {ref[name].height} rows)")
regression["net_cagr_matches_v2_metrics"] = \\
    abs(_cagr0 - v2_rot05["net_cagr"]) <= 1e-12
log(f"  R3-A0 net_cagr {_cagr0:.10f} vs v2 ROT-05 "
    f"{v2_rot05['net_cagr']:.10f} -> "
    f"{regression['net_cagr_matches_v2_metrics']}")
if _WINDOW == "dev":
    if not all(regression.values()):
        _fail(f"R3-A0 REGRESSION FAILURE: {regression} -- abort before "
              "remaining configs per val prereg sec 6 (R3-A0 != v2 "
              "ROT-05)")
    log("  R3-A0 regression anchor PASS (== v2 ROT-05, 5/5 frames)")
else:
    log("  R3-A0 anchor SKIPPED on val window (verified in the dev "
        "phase of this same adapted runner; per val prereg sec 6)")''',
     '''# RB-A0 regression: 5-frame .equals vs the v3 run's R3-06 outputs +
# net_cagr must equal the v3 metric (RB-A0 is NOT re-adjudicated)
results["RB-A0"] = run_one("RB-A0")
r0 = results["RB-A0"]["res"]
_sd, _sv = er.slice_curve(r0.daily["date"].to_list(),
                          r0.daily["equity"].to_list(), DEV_START, DEV_END)
_cagr0 = er.cagr(_sv[0], _sv[-1], _sd[0], _sd[-1])
v3_r306 = v3_mg["metrics"]["R3-06"]
ref = {name: pl.read_parquet(V3_RUN / "outputs" / fn) for name, fn in
       (("intents", "R3-06_intents.parquet"),
        ("fills", "R3-06_fills.parquet"), ("events", "R3-06_events.parquet"),
        ("daily", "R3-06_daily_equity.parquet"),
        ("clips_final", "R3-06_clips_final.parquet"))}
regression = {}
for name, mine in (("intents", FRAMES["RB-A0"]), ("fills", r0.fills),
                   ("events", r0.events), ("daily", r0.daily),
                   ("clips_final", r0.clips_final)):
    same = mine.equals(ref[name])
    regression[name] = same
    log(f"  RB-A0 {name}.equals(v3 R3-06 {name}) = {same} "
        f"(mine {mine.height} rows / ref {ref[name].height} rows)")
regression["net_cagr_matches_v3_metrics"] = \\
    abs(_cagr0 - v3_r306["net_cagr"]) <= 1e-12
log(f"  RB-A0 net_cagr {_cagr0:.10f} vs v3 R3-06 "
    f"{v3_r306['net_cagr']:.10f} -> "
    f"{regression['net_cagr_matches_v3_metrics']}")
if not all(regression.values()):
    _fail(f"RB-A0 REGRESSION FAILURE: {regression} -- abort before "
          "remaining configs per rob prereg sec 4 (RB-A0 != v3 R3-06)")
log("  RB-A0 regression anchor PASS (== v3 R3-06, 5/5 frames)")''')

# --- K. verdict semantics: no pass/eliminate from this round (prereg sec 0) -----
rep('        g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"',
    '        # rob prereg sec 0: this round produces NO pass/eliminate verdicts\n'
    '        g["verdict"] = ("regression_anchor_not_readjudicated"\n'
    '                        if cid == "RB-A0"\n'
    '                        else "exploration_grade_no_verdict")')

# --- L. stop-note block -> rob readout (descriptive only) ------------------------
rep('''_goal_hit = [cid for cid in gates
             if gates[cid][_GK][_PASSKEY]
             and metrics[cid]["goal_net_cagr_ge_10pct"]]
if _goal_hit:
    _STOP_NOTE = ("GOAL HIT (dev): " + ", ".join(_goal_hit)
                  + " pass all 8 gates AND net CAGR >= 10% -> STOP and "
                    "report user; val application is a separate user "
                    "decision; val not consumed")
elif n_pass:
    _STOP_NOTE = (f"{n_pass}/{len(gates)} configs pass all dev gates but "
                  "none reaches the 10% goal column -> bookkeep and "
                  "CONTINUE dev exploration per the user's 2026-09-19 "
                  "ruling (val held); val not consumed")
else:
    _STOP_NOTE = (f"no config passed all dev gates ({n_pass}/{len(gates)}); "
                  "ROT branch PAUSED per the v3 stop clause (direction "
                  "re-evaluation is a separate user decision); val not "
                  "consumed")''',
     '''_STOP_NOTE = (
    "robustness round (prereg exp-20260919-hybrid-robustness sec 0/2/4): "
    "anchor RB-A0 regression "
    + ("PASS" if all(regression.values()) else "FAIL")
    + f"; {n_pass}/{len(gates)} configs pass all 8 dev gates (descriptive "
    "count only); ALL neighborhood results are exploration-grade (dev-only, "
    "post-val, meta-overfitting discount) -- NO selection, NO champion "
    "change, NO ledger elimination semantics; val not consumed")''')

# --- M. neighborhood distribution stats replace the v3 bond-ladder disclosure ---
rep('''# --- v3 disclosure: bond-weight ladder monotonicity (prereg sec 4-3) -------
_ladder = []
for cid in CONFIG_IDS:
    if cid not in metrics:
        continue
    m = metrics[cid]
    _ladder.append({"id": cid,
                    "bond_w": CFGS[cid]["legs"].get("sh.511010", 0.0),
                    "net_cagr": m["net_cagr"],
                    "max_drawdown": m["max_drawdown"],
                    "excess_vs_b1m": m["excess_vs_b1m"],
                    "advantage_years": gates[cid][_GK]["advantage_years"],
                    "failed_gates": gates[cid][_GK]["failed_gates"],
                    "rotation_top_n": (CFGS[cid]["rotation"]["top_n"]
                                       if CFGS[cid]["rotation"] else None)})
disclosures["bond_ladder_monotonicity"] = {
    "ladder": _ladder,
    "note": "bond weight 0.25 -> 0 trajectory of net CAGR / maxDD; "
            "non-monotonicity means structural sensitivity, not linear "
            "opportunity cost (v3 prereg sec 4-3); R3-A0 is the 0.25 point"}''',
     '''# --- rob disclosure: neighborhood distribution stats (prereg sec 2) --------
_neigh = [c for c in CONFIG_IDS if c != "RB-A0" and c in metrics]
_champ = metrics["RB-A0"]
_neigh_pass = [c for c in _neigh if not gates[c][_GK]["failed_gates"]]
_neigh_band = [c for c in _neigh
               if abs(metrics[c]["excess_vs_b1m"]
                      - _champ["excess_vs_b1m"]) <= 0.010]
_neigh_mdd = [c for c in _neigh
              if abs(metrics[c]["max_drawdown"]) <= 0.20 + 1e-12]
disclosures["neighborhood_robustness_stats"] = {
    "n_neighborhood": len(_neigh),
    "anchor_reference": "RB-A0 (= R3-06 verbatim; byte-anchored)",
    "gate_pass_counts_among_neighborhood": {
        k: sum(1 for c in _neigh if gates[c][_GK][k]) for k in GATE_KEYS},
    "all_8_gates_pass_ratio": (len(_neigh_pass) / len(_neigh)
                               if _neigh else None),
    "excess_within_champion_pm1pp_ratio": (len(_neigh_band) / len(_neigh)
                                           if _neigh else None),
    "maxdd_le_20pct_ratio": (len(_neigh_mdd) / len(_neigh)
                             if _neigh else None),
    "detail": [{"id": c,
                "net_cagr": metrics[c]["net_cagr"],
                "excess_vs_b1m": metrics[c]["excess_vs_b1m"],
                "delta_excess_vs_anchor": (metrics[c]["excess_vs_b1m"]
                                           - _champ["excess_vs_b1m"]),
                "max_drawdown": metrics[c]["max_drawdown"],
                "advantage_years": gates[c][_GK]["advantage_years"],
                "failed_gates": gates[c][_GK]["failed_gates"]}
               for c in _neigh],
    "note": "prereg sec 2 frozen readout: three descriptive ratios answering "
            "'plateau or spike' -- all-8-gate pass ratio, excess within "
            "champion +/-1pp ratio, maxDD <= 20% ratio; NO pass/eliminate "
            "verdicts, NO ledger elimination semantics; exploration-grade "
            "(dev-only, post-val, meta-overfitting discount)"}''')

# --- N. metrics_and_gates anchor note --------------------------------------------
rep('''    "r3a0_regression_anchor": {**regression,
                               "note": "polars .equals() vs v2 run ROT-05 "
                                       "outputs (intents/fills/events/daily/"
                                       "clips_final) + net_cagr match; "
                                       "mismatch = abort (did not trigger); "
                                       "R3-A0 is NOT re-adjudicated"},''',
     '''    "rb_a0_regression_anchor": {**regression,
                                "note": "polars .equals() vs the v3 run's "
                                        "(20260919T110500-hybrid-v3-r3ld) "
                                        "R3-06 outputs (intents/fills/events/"
                                        "daily/clips_final) + net_cagr 1e-12 "
                                        "match; mismatch = abort (did not "
                                        "trigger); RB-A0 is NOT "
                                        "re-adjudicated"},''')

# --- O. no-rejurisdiction note -----------------------------------------------------
rep('''    "no_rejurisdiction": "v2-judged configs (H2-01/03/04, ROT-05) are NOT "
                         "re-run or re-judged in v3; R3-A0 is a regression "
                         "anchor only (v3 prereg sec 3)",''',
     '''    "no_rejurisdiction": "v3-judged configs (R3-05/R3-06) are NOT re-run "
                         "for adjudication here; RB-A0 is a byte-level "
                         "regression anchor only (rob prereg sec 0/1); all "
                         "neighborhood configs are exploration-grade and "
                         "never adjudicated",''')

# --- P. report title + anchor bullet ------------------------------------------------
rep('rep = ["# 混合族 v3 判定（exp-20260919-hybrid-family-v3，降债阶梯）", "",',
    'rep = ["# 混合族稳健性验证轮（exp-20260919-hybrid-robustness，邻域描述性）", "",')
rep('''       f"- R3-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v2 ROT-05 输出逐帧 polars `.equals()` 全部一致（5/5 PASS），"
       f"判定链有效；R3-A0 判定以 v2 为准，不重判。",''',
     '''       f"- RB-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v3 run（20260919T110500-hybrid-v3-r3ld）R3-06 产物逐帧 polars "
       f"`.equals()` 全部一致（5/5 PASS）+ net_cagr 1e-12 一致；"
       f"判定链有效；锚不重判。",''')

# --- Q. neighborhood stats rendering replaces the ladder rendering ------------------
rep('''if "bond_ladder_monotonicity" in disclosures:
    rep += ["", "### 债权重阶梯单调性（v3 预登记 §4-3）", "",
            "| 配置 | 债权重 | top_n | 净CAGR | maxDD | 超额 | 优势年 | 失败门 |",
            "|---|---|---|---|---|---|---|---|"]
    for e in disclosures["bond_ladder_monotonicity"]["ladder"]:
        rep.append(
            f"| {e['id']} | {e['bond_w']:.0%} | {e['rotation_top_n']} "
            f"| {e['net_cagr']*100:+.2f}% | {e['max_drawdown']*100:.2f}% "
            f"| {e['excess_vs_b1m']*100:+.2f}pp | {e['advantage_years']}/{len(m['b1m_net_return_by_year'])} "
            f"| {', '.join(e['failed_gates']) or '-'} |")
    rep += ["- 轨迹若非单调 = 结构敏感而非线性机会成本；R3-A0 即 0.25 基点。",
            "- 引擎现金零收益：R3-01..04 腾出的债权重闲置为现金，相对现实"
            "（货基收益）略悲观，保守方向如实呈现。"]''',
     '''if "neighborhood_robustness_stats" in disclosures:
    _st = disclosures["neighborhood_robustness_stats"]
    rep += ["", "### 邻域分布统计（预登记 §2 冻结口径；描述性，非判定）", "",
            f"- 邻域 n={_st['n_neighborhood']}；八门全过比例 "
            f"{_st['all_8_gates_pass_ratio']*100:.0f}%；超额落在锚 ±1pp 内"
            f"比例 {_st['excess_within_champion_pm1pp_ratio']*100:.0f}%；"
            f"maxDD≤20% 比例 {_st['maxdd_le_20pct_ratio']*100:.0f}%。",
            "- 逐门通过数（11 邻域中）："
            + json.dumps(_st["gate_pass_counts_among_neighborhood"]),
            "", "| 配置 | 净CAGR | 超额 | Δ超额vs锚 | maxDD | 优势年 | 失败门 |",
            "|---|---|---|---|---|---|---|"]
    for e in _st["detail"]:
        rep.append(
            f"| {e['id']} | {e['net_cagr']*100:+.2f}% "
            f"| {e['excess_vs_b1m']*100:+.2f}pp "
            f"| {e['delta_excess_vs_anchor']*100:+.2f}pp "
            f"| {e['max_drawdown']*100:.2f}% "
            f"| {e['advantage_years']}/{len(m['b1m_net_return_by_year'])} "
            f"| {', '.join(e['failed_gates']) or '-'} |")
    rep += ["- 全部为 exploration-grade（dev-only、post-val、元过拟合折扣）；"
            "不产生过/灭判定，不改变 R3-05/R3-06 在库地位。"]''')

# --- R. report section-3 heading ------------------------------------------------------
rep('        "## 三、R3-A0 回归锚（= v2 ROT-05 复刻）", "",',
    '        "## 三、RB-A0 回归锚（= v3 R3-06 复刻）", "",')

# --- S. trial accounting (manifest + report) ------------------------------------------
rep('''    "trial_accounting": {"this_round": "1 family (7 configs, all run)",
                         "cumulative_lineage": "v1 205->214; v2 214->222; "
                                               "v3 verdict -> 222->229 "
                                               "(config json trial_accounting)"},''',
     '''    "trial_accounting": {"this_round":
                             "+11 neighborhood trials (12 configs run; "
                             "anchor RB-A0 not counted per prereg sec 4)",
                         "cumulative_lineage": "per prereg sec 4: "
                                               "241 -> 252"},''')
rep('''        f"- 试验计账：本族判定计 7 项（7 配置族）；谱系 v1 205→214、"
        "v2 214→222，v3 判定后 222→229（如台账有异以台账为准）。",''',
     '''        f"- 试验计账：本轮 +11 邻域试验（预登记 §4：241→252），锚 RB-A0 "
        "不计；谱系 v1 205→214、v2 214→222、v3 222→229"
        "（如台账有异以台账为准）。",''')

# --- T. report key-findings section -> rob semantics ----------------------------------
rep('''rep += ["", "## 五、关键发现与口径说明", "",
        "- **降债阶梯口径**：债权重 0.25→0，腾出的权重或闲置为现金"
        "（R3-01..04）或给第三轮动槽（R3-05 top3×25%、R3-06 top3×20%）；"
        "引擎现金零收益（无货基收益建模），现金变体相对现实略悲观"
        "（保守方向，不修补）。",
        "- **门 8 v3 口径与 v2 逐字**：最终交付 =（市价兜底成交 + 武装后限价"
        "自身成交）/兜底武装单数 ≥99%，期末滞留=0 硬断言；8v2 与 R16 原口径"
        "仅作对照列。",
        "- **停止条款（用户 2026-09-19 裁定编码）**：过门且 ≥10% → 停止并报告"
        "（目标列首达）；过门但 <10% → 记账后继续 dev；全淘汰 → ROT 支线暂停。"
        "val 保持未消费。",
        "- **v2 已判配置不重跑不重判**：H2-01/03/04、ROT-05 的 dev 判定以 v2 "
        "为准；R3-A0 仅为回归锚。",
        "- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、"
        "分红 18 事件全落带（明细见 outputs/dividend_events.csv）；"
        "159934 的 2020-02-26 微偏离见冻结披露（v3 不使用该符号）。"]''',
     '''rep += ["", "## 五、关键发现与口径说明", "",
        "- **本轮性质**：R3-05/R3-06 邻域稳健性验证（robustness, NOT "
        "selection）；全部 dev 窗（2015–2020），无新样本外证据；邻域结果一律 "
        "exploration-grade（dev-only、post-val、元过拟合折扣），不产生新冠军、"
        "不改变 R3-05/R3-06 在库地位。",
        "- **锚口径**：RB-A0 = R3-06 逐字；5 帧产物（intents/fills/events/"
        "daily_equity/clips_final）与 v3 run R3-06 逐字节 `.equals()` + "
        "net_cagr 1e-12 一致；锚失败即中止零结论（未触发则记 PASS）。",
        "- **门 8 v3 口径逐字保留**：最终交付 =（市价兜底成交 + 武装后限价"
        "自身成交）/兜底武装单数 ≥99%，期末滞留=0 硬断言；8v2 与 R16 原口径"
        "仅作对照列。",
        "- **试验计账（预登记 §4）**：+11 邻域试验（241→252），锚不计；"
        "val 保持未消费。",
        "- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、"
        "分红 18 事件全落带（明细见 outputs/dividend_events.csv）；"
        "159934 的 2020-02-26 微偏离见冻结披露（本轮不使用该符号）。"]''')

# --- U. manifest engine label / command / experiment ids -------------------------------
rep('               "version": "v1.2 (frozen, unchanged from v1; v2 prereg sec 5)"},',
    '               "version": "v1.3 (sha256 pin 84a2443a...082c; rob '
    'prereg sec 1)"},')
rep('                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_hybrid_v3.py"],',
    '                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_hybrid_rob.py"],')
rep('"experiment_id": "exp-20260919-hybrid-family-v2",',
    '"experiment_id": "exp-20260919-hybrid-robustness",')
rep('"experiment_id": "exp-20260919-hybrid-family-v3",',
    '"experiment_id": "exp-20260919-hybrid-robustness",', count=2)
rep('    "r3a0_regression": regression,',
    '    "rb_a0_regression": regression,')

# --- V. final sweep: remaining R3-A0 identifiers -> RB-A0 -------------------------------
_n_left = s.count("R3-A0")
# remaining refs (all benign identifier usages): report section-11 skip list,
# rotation_fill_profile base x3, comp_txt, and report section-3 engine stats x3
assert _n_left == 8, f"expected 8 remaining R3-A0 refs before sweep, got {_n_left}"
s = s.replace("R3-A0", "RB-A0")
reps.append(("R3-A0 -> RB-A0 (final sweep)", _n_left))

# --- W. residual sanity ------------------------------------------------------------------
for bad in ("R3-A0", "V2_RUN", "v2_mg", "v2_rot05", "v2 ROT-05",
            "hybrid-family-v2 runner", "bond_ladder_monotonicity"):
    assert bad not in s, f"residual {bad!r} still present"
assert 'runner_hybrid_rob.py' in s
assert s.count("RB-A0") == s.count("RB-A0")  # trivial; kept for symmetry

io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print(f"adapted OK: {len(reps)} replacement groups, {n0} -> {len(s)} chars")
for name, c in reps:
    print(f"  x{c}  {name}")
