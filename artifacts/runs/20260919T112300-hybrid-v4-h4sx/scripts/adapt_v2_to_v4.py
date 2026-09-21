# -*- coding: utf-8 -*-
"""v2 -> v4 runner adaptation (exp-20260919-hybrid-family-v4).

Applies the frozen v4 differences to a byte-copy of the v2 runner
(20260919T063022-hybrid-v2-2k5b/scripts/runner_hybrid_v2.py):
- 9 configs (H4-A0 anchor + 3-axis matrix: bond->stock ladder H4-01..03,
  bond->dividend swap H4-04..06, gold-in-rotation arms H4-07/08);
- SEMANTIC FIX (documented): v2 mixed_frames included ONLY leg symbols in
  the ETF panel; v4's H4-07/08 rotate non-leg symbols, so the stock-config
  panel is legs UNION rotation universe (engine needs daily rows to
  anchor/route any intent symbol);
- H4-A0 = H2-01 verbatim replica: 5-frame .equals() vs the v2 run's
  H2-01 outputs + net_cagr match; mismatch aborts;
- universe sensitivity block retired -> v4 3-axis attribution disclosure;
- stop clauses per user ruling (pass+>=10% stop / pass<10% continue /
  all-eliminated pause); trial accounting 229->238.

Every replacement asserts the old text occurs EXACTLY ONCE; mismatch
aborts without writing.  Output: scripts/runner_hybrid_v4.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
SRC = RUN_DIR / "tmp/runner_hybrid_v2_source.py"
DST = RUN_DIR / "scripts/runner_hybrid_v4.py"

text = SRC.read_text(encoding="utf-8")
n_edits = 0


def rep(old: str, new: str) -> None:
    global text, n_edits
    n = text.count(old)
    if n != 1:
        sys.exit(f"ABORT: pattern occurs {n}x (want 1): {old[:90]!r}")
    text = text.replace(old, new)
    n_edits += 1


# --- E1: docstring -----------------------------------------------------------
rep('''Copy-adapted from the v1 runner (20260919T054649-hybrid-v1-9k2f) per the v2
prereg (docs/research/exp-20260919-hybrid-family-v2-prereg.md +
configs/experiments/hybrid-family-v2.json); v1-prereg clauses (universe,
band table, dividend rule, runner assertions, fees, window, Design B leg
semantics, benchmarks) inherited verbatim.  v2 differences only:
- 8 configs (H2-A0 anchor + H2-01..04 multi-leg parks + ROT-03R/04/05);
  every leg symbol <= 25% (S4 structure fix); new leg symbol sz.159934;
- S2 fix: leg symbols are REMOVED from the rotation ranking universe
  (ROT-03R/ROT-04: 7 members; ROT-05: 6 members) -- collision impossible;
- gate 8 v3 (criteria naturalization v2): final delivery = (market-fallback
  fills + armed-then-limit-self fills) / armed >= 99%, end-of-run armed
  stuck positions == 0 hard assert; 8v2 and R16 calibers kept as columns;
- disclosures: actual leg mean weight vs target, stock-leg displacement vs
  H2-A0 (fills / fill rate / entry delay), insufficient-cash void counts,
  ROT-04 vs v1 ROT-01 universe sensitivity, 159934 2020-02-26 deviation.
- H2-A0 anchor first: 4-frame polars .equals() vs P3R2 C05, mismatch abort.''',
    '''Copy-adapted from the v2 runner (20260919T063022-hybrid-v2-2k5b) per the
v4 prereg (docs/research/exp-20260919-hybrid-family-v4-prereg.md +
configs/experiments/hybrid-family-v4.json); v2/v3-prereg clauses (universe,
band table, dividend rule, runner assertions, fees, window, Design B leg
semantics, gates 1-7 R16 + gate 8 v3, benchmarks) inherited verbatim.
v4 differences only (user directives 2026-09-19):
- 9 configs, 3 axes on the H2-01 parent (stock C05 + legs):
  A bond->stock ladder H4-01..03 (bond 25 -> 15/10/0, freed weight reaches
  the stock engine via the m7 cash-competition channel only -- C05 target
  weights are signal-driven and do NOT scale with cash);
  B bond->dividend swap H4-04..06 (510880 replaces 511010; equity beta,
  dev own maxDD -46.56% -- risk stated in the prereg);
  C gold-in-rotation arms H4-07/08 (gold 518880 rankable in UNI6G top1/top2
  slots vs static gold legs in H4-05/06);
- SEMANTIC FIX (v4 prereg sec 2): v2 mixed_frames put ONLY leg symbols in
  the ETF panel; stock configs WITH rotation (H4-07/08) need legs UNION
  rotation-universe symbols in the panel;
- H4-A0 = H2-01 verbatim replica and regression anchor: 5-frame polars
  .equals() vs the v2 run's H2-01 outputs + net_cagr match; abort on
  mismatch; NOT re-adjudicated;
- universe-sensitivity block retired -> v4 3-axis attribution disclosure;
- stop clauses per the user's 2026-09-19 ruling: pass + >=10% -> STOP and
  report; pass but <10% -> CONTINUE dev; all eliminated -> family
  direction re-evaluated with user.  val stays unconsumed.''')

# --- E2: path constants ------------------------------------------------------
rep('''V1_RUN = ROOT / "artifacts/runs/20260919T054649-hybrid-v1-9k2f"
PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v2-prereg.md"''',
    '''V1_RUN = ROOT / "artifacts/runs/20260919T054649-hybrid-v1-9k2f"
V2_RUN = ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b"
PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v4-prereg.md"
V2_PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v2-prereg.md"''')
rep('HYB_CONFIG = ROOT / "configs/experiments/hybrid-family-v2.json"',
    'HYB_CONFIG = ROOT / "configs/experiments/hybrid-family-v4.json"')

# --- E3: pins EXPECTED -------------------------------------------------------
rep('''    "prereg": (None, PREREG_MD),
    "v1_prereg_inherited": (None, V1_PREREG_MD),
    "hyb_config": (None, HYB_CONFIG),''',
    '''    "prereg": (None, PREREG_MD),
    "v2_prereg_inherited": (None, V2_PREREG_MD),
    "v1_prereg_inherited": (None, V1_PREREG_MD),
    "hyb_config": (None, HYB_CONFIG),
    "v2_metrics_h2a01_anchor_source":
        (None, V2_RUN / "outputs/metrics_and_gates.json"),''')

# --- E4: CONFIG_IDS + CFGS + universe ----------------------------------------
rep('''CONFIG_IDS = ["H2-A0", "H2-01", "H2-02", "H2-03", "H2-04",
              "ROT-03R", "ROT-04", "ROT-05"]''',
    '''CONFIG_IDS = ["H4-A0", "H4-01", "H4-02", "H4-03",
              "H4-04", "H4-05", "H4-06", "H4-07", "H4-08"]''')
rep('''# config table (v2 prereg sec 2 / config json configs; "park" column =
# sum of per-symbol leg weights, each <= 25%: S4 structure fix)
UNI7 = [m for m in MEMBERS if m != "sh.511010"]          # 8 - leg 511010
UNI6 = [m for m in MEMBERS
        if m not in ("sh.511010", "sh.518880")]          # 8 - both legs''',
    '''# config table (v4 prereg sec 2): 3-axis matrix on the H2-01 parent;
# every leg symbol <= 25%; UNI6G = 8 members minus {bond, dividend-leg}
# -> gold 518880 IS rankable (v4 axis C)
UNI6G = [m for m in MEMBERS
         if m not in ("sh.511010", "sh.510880")]         # 6 members''')
rep('''CFGS = {
    "H2-A0": {"stock": True, "legs": {}, "rotation": None},
    "H2-01": {"stock": True, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.25}, "rotation": None},
    "H2-02": {"stock": True, "legs": {"sh.518880": 0.20,
                                      "sz.159934": 0.20}, "rotation": None},
    "H2-03": {"stock": True, "legs": {"sh.511010": 0.20, "sh.518880": 0.20,
                                      "sz.159934": 0.20}, "rotation": None},
    "H2-04": {"stock": True, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.20}, "rotation": None},
    "ROT-03R": {"stock": False, "legs": {"sh.511010": 0.25},
                "rotation": {"universe": UNI7, "top_n": 3, "weight": 0.25,
                             "lookback_m": 6}},
    "ROT-04": {"stock": False, "legs": {},
               "rotation": {"universe": UNI7, "top_n": 4, "weight": 0.25,
                            "lookback_m": 6}},
    "ROT-05": {"stock": False, "legs": {"sh.511010": 0.25,
                                        "sh.518880": 0.25},
               "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                            "lookback_m": 6}},
}''',
    '''CFGS = {
    "H4-A0": {"stock": True, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.25}, "rotation": None},
    "H4-01": {"stock": True, "legs": {"sh.511010": 0.15,
                                      "sh.518880": 0.25}, "rotation": None},
    "H4-02": {"stock": True, "legs": {"sh.511010": 0.10,
                                      "sh.518880": 0.25}, "rotation": None},
    "H4-03": {"stock": True, "legs": {"sh.518880": 0.25}, "rotation": None},
    "H4-04": {"stock": True, "legs": {"sh.510880": 0.15,
                                      "sh.518880": 0.25}, "rotation": None},
    "H4-05": {"stock": True, "legs": {"sh.510880": 0.25,
                                      "sh.518880": 0.25}, "rotation": None},
    "H4-06": {"stock": True, "legs": {"sh.510880": 0.25}, "rotation": None},
    "H4-07": {"stock": True, "legs": {"sh.510880": 0.25},
              "rotation": {"universe": UNI6G, "top_n": 1, "weight": 0.25,
                           "lookback_m": 6}},
    "H4-08": {"stock": True, "legs": {"sh.510880": 0.25},
              "rotation": {"universe": UNI6G, "top_n": 2, "weight": 0.20,
                           "lookback_m": 6}},
}''')

# --- E5: INPUTS (drop pure anchor branch; legs UNION rotation universe) ------
rep('''    if cid == "H2-A0":
        INPUTS[cid] = {"daily": daily_c, "half": half_c, "limits": limits_c,
                       "splits": splits_c, "dividends": divs_c,
                       "instruments": instr_c, "meta": None, "events": None,
                       "mode": "p3r2_verbatim"}
    elif cfg["stock"]:
        used = set(cfg["legs"])
        INPUTS[cid] = {**mixed_frames(used), "meta": SYMBOL_META,
                       "events": dividend_events, "mode": "mixed"}''',
    '''    if cfg["stock"]:
        # v4 semantic fix (prereg sec 2): the ETF panel for a stock config
        # must include its rotation-universe symbols too (H4-07/08 rotate
        # non-leg members); v2 only ever mixed leg symbols (no stock+rotation
        # config existed there).
        used = set(cfg["legs"])
        if cfg["rotation"]:
            used |= set(cfg["rotation"]["universe"])
        INPUTS[cid] = {**mixed_frames(used), "meta": SYMBOL_META,
                       "events": dividend_events, "mode": "mixed"}''')
rep('''# gain tradestatus=1.0 (dtype-matched).  H2-A0 itself uses the PURE P3R2
# frames above (byte-level anchor -- no added columns).''',
    '''# gain tradestatus=1.0 (dtype-matched).  v4 has no pure-stock config;
# the pure frames remain the base for mixed_frames construction.''')

# --- E6a: section-10 header --------------------------------------------------
rep('''# === 10. H2-A0 smoke: engine regression anchor ==============================
log("== 10. H2-A0 regression anchor vs P3R2 C05 ==")''',
    '''# === 10. H4-A0 regression anchor vs v2 H2-01 ==============================
log("== 10. H4-A0 regression anchor vs v2 H2-01 ==")''')

# --- E6b: anchor block -------------------------------------------------------
rep('''# H2-A0 regression: 4-frame .equals + net_cagr must equal the P3R2 metric
results["H2-A0"] = run_one("H2-A0")
r0 = results["H2-A0"]["res"]
_sd, _sv = er.slice_curve(r0.daily["date"].to_list(),
                          r0.daily["equity"].to_list(), DEV_START, DEV_END)
_cagr0 = er.cagr(_sv[0], _sv[-1], _sd[0], _sd[-1])
p3r2_c05 = p3r2_mg["metrics"]["C05"]
ref = {name: pl.read_parquet(P3R2_RUN / "outputs" / fn) for name, fn in
       (("fills", "C05_fills.parquet"), ("events", "C05_events.parquet"),
        ("daily", "C05_daily_equity.parquet"),
        ("clips_final", "C05_clips_final.parquet"))}
regression = {}
for name, mine in (("fills", r0.fills), ("events", r0.events),
                   ("daily", r0.daily), ("clips_final", r0.clips_final)):
    same = mine.equals(ref[name])
    regression[name] = same
    log(f"  H2-A0 {name}.equals(P3R2 C05 {name}) = {same} "
        f"(mine {mine.height} rows / ref {ref[name].height} rows)")
regression["net_cagr_matches_p3r2_metrics"] = \\
    abs(_cagr0 - p3r2_c05["net_cagr"]) <= 1e-12
log(f"  H2-A0 net_cagr {_cagr0:.10f} vs P3R2 C05 "
    f"{p3r2_c05['net_cagr']:.10f} -> "
    f"{regression['net_cagr_matches_p3r2_metrics']}")
if not all(regression.values()):
    _fail(f"H2-A0 REGRESSION FAILURE (engine regression): {regression} -- "
          "abort before remaining configs per prereg stop clause")
log("  H2-A0 regression anchor PASS")''',
    '''# H4-A0 regression: 5-frame .equals vs the v2 run's H2-01 outputs +
# net_cagr must equal the v2 metric (H4-A0 is NOT re-adjudicated)
results["H4-A0"] = run_one("H4-A0")
r0 = results["H4-A0"]["res"]
_sd, _sv = er.slice_curve(r0.daily["date"].to_list(),
                          r0.daily["equity"].to_list(), DEV_START, DEV_END)
_cagr0 = er.cagr(_sv[0], _sv[-1], _sd[0], _sd[-1])
v2_h2a01 = v2_mg["metrics"]["H2-01"]
ref = {name: pl.read_parquet(V2_RUN / "outputs" / fn) for name, fn in
       (("intents", "H2-01_intents.parquet"),
        ("fills", "H2-01_fills.parquet"), ("events", "H2-01_events.parquet"),
        ("daily", "H2-01_daily_equity.parquet"),
        ("clips_final", "H2-01_clips_final.parquet"))}
regression = {}
for name, mine in (("intents", FRAMES["H4-A0"]), ("fills", r0.fills),
                   ("events", r0.events), ("daily", r0.daily),
                   ("clips_final", r0.clips_final)):
    same = mine.equals(ref[name])
    regression[name] = same
    log(f"  H4-A0 {name}.equals(v2 H2-01 {name}) = {same} "
        f"(mine {mine.height} rows / ref {ref[name].height} rows)")
regression["net_cagr_matches_v2_metrics"] = \\
    abs(_cagr0 - v2_h2a01["net_cagr"]) <= 1e-12
log(f"  H4-A0 net_cagr {_cagr0:.10f} vs v2 H2-01 "
    f"{v2_h2a01['net_cagr']:.10f} -> "
    f"{regression['net_cagr_matches_v2_metrics']}")
if not all(regression.values()):
    _fail(f"H4-A0 REGRESSION FAILURE: {regression} -- abort before remaining "
          "configs per v4 prereg stop clause (H4-A0 != v2 H2-01)")
log("  H4-A0 regression anchor PASS (== v2 H2-01, 5/5 frames)")''')

# v2 metrics loaded next to the other json pins
rep('''# v1 judgment table: source of the ROT-04 vs ROT-01 universe-sensitivity column
v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))''',
    '''v2_mg = json.loads((V2_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))
# v1 metrics: lineage reference only in v4 (universe-sensitivity block retired)
v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))''')

# --- E7: section 11 excludes the anchor by its new id ------------------------
rep('for cid in [c for c in CONFIG_IDS if c != "H2-A0" and c in FRAMES]:',
    'for cid in [c for c in CONFIG_IDS if c != "H4-A0" and c in FRAMES]:')

# --- E8: stock displacement vs the new anchor --------------------------------
rep('''base_profile = stock_leg_fill_profile("H2-A0")
for cid in results:
    if cid == "H2-A0" or not CFGS[cid]["stock"]:
        continue
    prof = stock_leg_fill_profile(cid)
    disclosures[cid]["6_stock_leg_vs_A0"] = {
        "h2a0": base_profile, "this": prof,''',
    '''base_profile = stock_leg_fill_profile("H4-A0")
for cid in results:
    if cid == "H4-A0" or not CFGS[cid]["stock"]:
        continue
    prof = stock_leg_fill_profile(cid)
    disclosures[cid]["6_stock_leg_vs_A0"] = {
        "h4a0": base_profile, "this": prof,''')
rep('''        "caliber": "stock displacement vs H2-A0 (v2 prereg sec 4-1): fills "
                   "count / per-intent fill rate / first-fill entry delay; "
                   "insufficient-cash voids are the park cash-competition cost"}''',
    '''        "caliber": "stock displacement vs H4-A0 (v4 prereg sec 4-2): fills "
                   "count / per-intent fill rate / first-fill entry delay; "
                   "insufficient-cash voids are the park cash-competition cost; "
                   "the freed bond weight reaches stocks ONLY through this "
                   "channel (C05 target weights are signal-driven)"}''')

# --- E9: 3-axis attribution replaces universe sensitivity --------------------
rep('''# --- v2 disclosure: ROT-04 vs v1 ROT-01 universe sensitivity (7 vs 8) -------
if "ROT-04" in metrics:
    r4 = metrics["ROT-04"]
    disclosures["universe_sensitivity_ROT04_vs_v1_ROT01"] = {
        "rot04_7member": {
            "net_cagr": r4["net_cagr"], "max_drawdown": r4["max_drawdown"],
            "excess_vs_b1m": r4["excess_vs_b1m"],
            "advantage_years": gates["ROT-04"]["dev"]["advantage_years"],
            "max_one_side_turnover": r4["max_one_side_turnover"],
            "max_single_name_weight": r4["max_single_name_weight"],
            "failed_gates": gates["ROT-04"]["dev"]["failed_gates"]},
        "rot01_8member_v1": V1_ROT01,
        "delta": {k: r4[k] - V1_ROT01[k]
                  for k in ("net_cagr", "max_drawdown", "excess_vs_b1m",
                            "max_one_side_turnover",
                            "max_single_name_weight")},
        "note": "identical top4 x 25% K6m rules; ranking universe 7 members "
                "(8 - leg 511010) vs v1's 8 members"}''',
    '''# --- v4 disclosure: 3-axis attribution (prereg sec 4-2) --------------------
def _ax(cid):
    m = metrics[cid]
    d = disclosures[cid]["6_stock_leg_vs_A0"]
    return {"net_cagr": m["net_cagr"], "max_drawdown": m["max_drawdown"],
            "excess_vs_b1m": m["excess_vs_b1m"],
            "advantage_years": gates[cid]["dev"]["advantage_years"],
            "failed_gates": gates[cid]["dev"]["failed_gates"],
            "stock_intent_fill_rate":
                d["this"]["stock_intent_fill_rate"]
                if d else None,
            "insufficient_cash":
                d["this"]["insufficient_cash_orders"] if d else None}

axes = {"axis_A_bond_to_stock": {
    "note": "bond 25 -> 15/10/0 ladder on stock+gold parent; freed weight "
            "reaches stocks via cash competition only",
    "trajectory": {c: _ax(c) for c in
                   ("H4-A0", "H4-01", "H4-02", "H4-03") if c in metrics}},
    "axis_B_bond_to_dividend": {
    "note": "510880 replaces 511010 (equity beta; dev own maxDD -46.56%)",
    "H4_05_vs_H4_A0": ({k: metrics["H4-05"][k] - metrics["H4-A0"][k]
                        for k in ("net_cagr", "max_drawdown",
                                  "excess_vs_b1m")}
                       if "H4-05" in metrics and "H4-A0" in metrics else None),
    "H4_04_vs_H4_01": ({k: metrics["H4-04"][k] - metrics["H4-01"][k]
                        for k in ("net_cagr", "max_drawdown",
                                  "excess_vs_b1m")}
                       if "H4-04" in metrics and "H4-01" in metrics else None),
    "profiles": {c: _ax(c) for c in ("H4-04", "H4-05", "H4-06")
                 if c in metrics}},
    "axis_C_gold_band": {
    "note": "gold rankable in UNI6G (top1/top2 slots) vs static gold legs",
    "profiles": {c: _ax(c) for c in ("H4-05", "H4-06", "H4-07", "H4-08")
                 if c in metrics}}}
# gold holding months from the rotation logs (axis C)
for cid in ("H4-07", "H4-08"):
    rot_log = ROT_LOG.get(cid) or []
    if rot_log:
        held = [e["month"] for e in rot_log if "sh.518880" in e["top"]]
        axes["axis_C_gold_band"][f"{cid}_gold_months"] = {
            "months_held": len(held), "months_total": len(rot_log),
            "hold_rate": len(held) / len(rot_log)}
disclosures["v4_axes"] = axes''')

# --- E10: report prose --------------------------------------------------------
rep('''rep = ["# 混合族 v2 判定（exp-20260919-hybrid-family-v2）", "",''',
    '''rep = ["# 混合族 v4 判定（exp-20260919-hybrid-family-v4，降债腾股票+债改红利+金波段）", "",''')
rep('''       f"- H2-A0 回归锚：fills/events/daily_equity/clips_final 与 P3R2 C05 "
       f"逐帧 polars `.equals()` 全部一致（4/4 PASS），判定链有效。",''',
    '''       f"- H4-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v2 H2-01 输出逐帧 polars `.equals()` 全部一致（5/5 PASS），"
       f"判定链有效；H4-A0 判定以 v2 为准，不重判。",''')
rep('''       f"（{len(sig_days)} 个月末，2020-12-31 丢弃）；val 2021–2024 零消费。",''',
    '''       f"（{len(sig_days)} 个月末，2020-12-31 丢弃）；val 2021–2024 零消费"
       f"（用户裁定维持）。",''')
rep('''       f"`{pins['prereg']['sha256'][:16]}`（已冻结，运行中零修改）；继承条款 "
       f"v1 预登记 sha256:16 `{pins['v1_prereg_inherited']['sha256'][:16]}`。",''',
    '''       f"`{pins['prereg']['sha256'][:16]}`（已冻结，运行中零修改）；继承条款 "
       f"v2 预登记 sha256:16 `{pins['v2_prereg_inherited']['sha256'][:16]}`"
       f"（其再继承 v1 sha256:16 "
       f"`{pins['v1_prereg_inherited']['sha256'][:16]}`）。",''')
rep('''        rate_this = comp["this"]["stock_intent_fill_rate"]
        rate_a0 = comp["h2a0"]["stock_intent_fill_rate"]''',
    '''        rate_this = comp["this"]["stock_intent_fill_rate"]
        rate_a0 = comp["h4a0"]["stock_intent_fill_rate"]''')
rep('''            f"；vs H2-A0: 股票成交 {comp['delta_stock_fills']:+d} 单, "
            f"成交率 {rate_a0*100:.1f}%→{rate_this*100:.1f}%"
            f"（Δ{(comp['delta_stock_fill_rate'] or 0)*100:+.1f}pp）, "
            f"首成交延迟 {comp['delta_first_fill_days']:+d} 日, "
            f"现金不足作废 {comp['insufficient_cash_orders_this']} 次"
            if rate_this is not None and rate_a0 is not None else
            f"；vs H2-A0: 股票成交 {comp['delta_stock_fills']:+d} 单, "
            f"首成交延迟 {comp['delta_first_fill_days']:+d} 日, "
            f"现金不足作废 {comp['insufficient_cash_orders_this']} 次")''',
    '''            f"；vs H4-A0: 股票成交 {comp['delta_stock_fills']:+d} 单, "
            f"成交率 {rate_a0*100:.1f}%→{rate_this*100:.1f}%"
            f"（Δ{(comp['delta_stock_fill_rate'] or 0)*100:+.1f}pp）, "
            f"首成交延迟 {comp['delta_first_fill_days']:+d} 日, "
            f"现金不足作废 {comp['insufficient_cash_orders_this']} 次"
            if rate_this is not None and rate_a0 is not None else
            f"；vs H4-A0: 股票成交 {comp['delta_stock_fills']:+d} 单, "
            f"首成交延迟 {comp['delta_first_fill_days']:+d} 日, "
            f"现金不足作废 {comp['insufficient_cash_orders_this']} 次")''')
rep('''if "universe_sensitivity_ROT04_vs_v1_ROT01" in disclosures:
    us = disclosures["universe_sensitivity_ROT04_vs_v1_ROT01"]
    dlt = us["delta"]
    rep += ["", "### 宇宙敏感性：ROT-04（7 成员）vs v1 ROT-01（8 成员）", "",
            f"- 同规则 top4×25% K6m，仅排名宇宙剔除腿符号 511010：净CAGR "
            f"{us['rot01_8member_v1']['net_cagr']*100:+.2f}% → "
            f"{us['rot04_7member']['net_cagr']*100:+.2f}%"
            f"（Δ{dlt['net_cagr']*100:+.2f}pp）；maxDD "
            f"{us['rot01_8member_v1']['max_drawdown']*100:.2f}% → "
            f"{us['rot04_7member']['max_drawdown']*100:.2f}%"
            f"（Δ{dlt['max_drawdown']*100:+.2f}pp）；超额 "
            f"{us['rot01_8member_v1']['excess_vs_b1m']*100:+.2f}pp → "
            f"{us['rot04_7member']['excess_vs_b1m']*100:+.2f}pp；优势年 "
            f"{us['rot01_8member_v1']['advantage_years']}/6 → "
            f"{us['rot04_7member']['advantage_years']}/6；单票max权重 "
            f"{us['rot01_8member_v1']['max_single_name_weight']*100:.1f}% → "
            f"{us['rot04_7member']['max_single_name_weight']*100:.1f}%。",
            "- 结论方向如实呈现：宇宙敏感性差异即腿剔除对轮动臂的影响幅度。"]''',
    '''if "v4_axes" in disclosures:
    ax = disclosures["v4_axes"]
    rep += ["", "### 三轴归因（v4 预登记 §4-2）", "",
            "**轴 A：债→股票阶梯**（腾出权重只经现金竞争通道起作用）", "",
            "| 配置 | 债权重 | 净CAGR | maxDD | 股票意图成交率 | 现金不足作废 | 失败门 |",
            "|---|---|---|---|---|---|---|"]
    for c, e in ax["axis_A_bond_to_stock"]["trajectory"].items():
        bond_w = {"H4-A0": "25%", "H4-01": "15%", "H4-02": "10%",
                  "H4-03": "0%"}[c]
        fr = e["stock_intent_fill_rate"]
        rep.append(
            f"| {c} | {bond_w} | {e['net_cagr']*100:+.2f}% "
            f"| {e['max_drawdown']*100:.2f}% "
            f"| {fr*100:.1f}% " if fr is not None else
            f"| {c} | {bond_w} | {e['net_cagr']*100:+.2f}% "
            f"| {e['max_drawdown']*100:.2f}% | n/a ")
        rep[-1] += (f"| {e['insufficient_cash']} "
                    f"| {', '.join(e['failed_gates']) or '-'} |")
    b = ax["axis_B_bond_to_dividend"]
    rep += ["", "**轴 B：债→红利（510880 股票贝塔，dev 自身 maxDD −46.56%）**", ""]
    for k, lbl in (("H4_05_vs_H4_A0", "H4-05（红利25）vs H4-A0（债25）"),
                   ("H4_04_vs_H4_01", "H4-04（红利15）vs H4-01（债15）")):
        if b.get(k):
            rep.append(f"- {lbl}: 净CAGR Δ{b[k]['net_cagr']*100:+.2f}pp、"
                       f"maxDD Δ{b[k]['max_drawdown']*100:+.2f}pp、"
                       f"超额 Δ{b[k]['excess_vs_b1m']*100:+.2f}pp。")
    c_ax = ax["axis_C_gold_band"]
    rep += ["", "**轴 C：金波段（入轮动）vs 金静态腿**", ""]
    for c, e in c_ax["profiles"].items():
        rep.append(f"- {c}: 净CAGR {e['net_cagr']*100:+.2f}%、"
                   f"maxDD {e['max_drawdown']*100:.2f}%、"
                   f"失败门 {', '.join(e['failed_gates']) or '无'}。")
    for cid in ("H4-07", "H4-08"):
        gm = c_ax.get(f"{cid}_gold_months")
        if gm:
            rep.append(f"- {cid} 金实际持有 {gm['months_held']}/"
                       f"{gm['months_total']} 月（{gm['hold_rate']*100:.0f}%）"
                       "——静态腿为 100%。")
    rep.append("- 基线数据：金 6 月动量排名 top1 17%/top2 23% 月份、38% 月份"
               "动量为负（主对话 2026-09-19 计算，入预登记 §1）。")''')
rep('''        "## 三、H2-A0 回归锚", "",
        f"- 4/4 帧 `.equals()` 一致：{json.dumps({k: v for k, v in regression.items()})}",
        f"- 引擎 stats：intents {results['H2-A0']['res'].stats['intent_layer']['n_intents']}"
        f"，orders {results['H2-A0']['res'].stats['intent_layer']['orders_generated']}"
        f"，filled {results['H2-A0']['res'].stats['intent_layer']['stopped_filled']}。",''',
    '''        "## 三、H4-A0 回归锚（= v2 H2-01 复刻）", "",
        f"- 5/5 帧 `.equals()` 一致：{json.dumps({k: v for k, v in regression.items()})}",
        f"- 引擎 stats：intents {results['H4-A0']['res'].stats['intent_layer']['n_intents']}"
        f"，orders {results['H4-A0']['res'].stats['intent_layer']['orders_generated']}"
        f"，filled {results['H4-A0']['res'].stats['intent_layer']['stopped_filled']}。",''')
rep('''        f"- 试验计账：本族判定计 1 项（8 配置族）；谱系 205→214 已含 v1，"
        "v2 判定后 214→222（如台账有异以台账为准）。",''',
    '''        f"- 试验计账：本族判定计 9 项（9 配置族）；谱系 v1 205→214、"
        "v2 214→222、v3 222→229，v4 判定后 229→238（如台账有异以台账为准）。",''')
rep('''rep += ["", "## 五、关键发现与口径说明", "",
        "- **门 8 v3 口径**：最终交付 =（市价兜底成交 + 武装后限价自身成交）"
        "/兜底武装单数 ≥99%，期末武装后滞留持仓=0 硬断言；两分子分列于判定表，"
        "8v2 与 R16 原口径仅作对照列。v1 的 sh.600518（2019-06，8 时段跌停顺延"
        "后限价自成交、无滞留）在本口径下重建精确（armed=7=6+1，残差 0）。"
        "v1 已判配置不因 8v3 重判（HYB-05 门 4 失败与门 8 无关）。",
        "- **S4 结构修复生效**：v1 的 HYB-01..04 因 ParkW>25% 首发射即被上限"
        "作废（退化=C05+现金）；v2 多腿结构逐符号 ≤25%，腿真实建仓（本表各配置"
        "腿实际均重 vs 目标列可对照），现金竞争代价体现在 insufficient-cash "
        "作废与股票 displacement（vs H2-A0 差值列）。",
        "- **park 50/60 的代价**：H2-01（50%）/H2-03（60%）相对 H2-A0 的股票"
        "成交差、成交率差与入场延迟见判定披露二；若 displacement 侵蚀了腿收益"
        "带来的超额，以净数字为准如实呈现。",
        "- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、"
        "分红 18 事件全落带（明细见 outputs/dividend_events.csv）；"
        "159934 的 2020-02-26 微偏离见冻结披露。"]''',
    '''rep += ["", "## 五、关键发现与口径说明", "",
        "- **腾给股票的机制口径（预登记 §0）**：C05 股票引擎目标权重由冻结"
        "信号决定，不随现金放大；降债的作用通道 = insufficient-cash 作废减少、"
        "成交率上升——股票敞口向 C05 信号意图靠拢，非按腾出比例放大。",
        "- **红利=股票贝塔**：510880 dev 自身 maxDD −46.56%（债 −4.92%），"
        "与股票引擎崩盘窗同向；若轴 B 使混合 maxDD 恶化，如实判定不修补。",
        "- **金波段基线**：6 月动量排名 top1 17%/top2 23% 月份——横截面轮动"
        "在 ~77% 月份不持金；轴 C 用实测对照判定波段是否优于静态。",
        "- **门 8 v3 口径与 v2 逐字**；v2/v3 已判配置不重跑不重判。",
        "- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、"
        "分红 18 事件全落带（510880×6 随红利腿自动入账，明细见 "
        "outputs/dividend_events.csv）；159934 的 2020-02-26 微偏离见冻结披露"
        "（v4 未使用该符号）。"]''')

# --- E11: mg dict -------------------------------------------------------------
rep('''mg = {
    "experiment_id": "exp-20260919-hybrid-family-v2",''',
    '''_goal_hit = [cid for cid in gates
             if gates[cid]["dev"]["dev_pass"]
             and metrics[cid]["goal_dev_net_cagr_ge_10pct"]]
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
                  "family direction re-evaluated WITH the user per the v4 "
                  "stop clause; val not consumed")

mg = {
    "experiment_id": "exp-20260919-hybrid-family-v4",''')
rep('''    "h2a0_regression_anchor": {**regression,
                               "note": "polars .equals() vs P3R2 C05 "
                                       "outputs; mismatch = abort (did not "
                                       "trigger)"},''',
    '''    "h4a0_regression_anchor": {**regression,
                               "note": "polars .equals() vs v2 run H2-01 "
                                       "outputs (intents/fills/events/daily/"
                                       "clips_final) + net_cagr match; "
                                       "mismatch = abort (did not trigger); "
                                       "H4-A0 is NOT re-adjudicated"},''')
rep('''    "v1_prereg_inherited_sha256_16": pins["v1_prereg_inherited"]["sha256"][:16],''',
    '''    "v2_prereg_inherited_sha256_16":
        pins["v2_prereg_inherited"]["sha256"][:16],
    "v1_prereg_inherited_sha256_16": pins["v1_prereg_inherited"]["sha256"][:16],''')
rep('''    "no_rejurisdiction": "v1-judged configs (HYB-05 etc.) are NOT re-judged "
                         "under 8v3; HYB-05's gate-4 failure is unrelated to "
                         "gate 8 -- conclusions unchanged (v2 prereg sec 3)",''',
    '''    "no_rejurisdiction": "v2/v3-judged configs (H2-01/03/04, ROT-05, "
                         "R3-01..06) are NOT re-run or re-judged in v4; "
                         "H4-A0 is a regression anchor only (v4 prereg "
                         "sec 3)",''')
rep('''    "stop_note": ("STOP before val: >=1 config passed all dev gates; val "
                  "requires separate user approval" if n_pass else
                  f"no config passed all dev gates ({n_pass}/"
                  f"{len(gates)}); hybrid line PAUSED per the v2 stop clause "
                  "(direction re-evaluation is a separate user decision); "
                  "val not consumed"),''',
    '''    "stop_note": _STOP_NOTE,''')

# --- E12: manifest -------------------------------------------------------------
rep('''    "experiment_id": "exp-20260919-hybrid-family-v2",
    "status": "completed" if not BLOCKED else "completed_with_blocked_config",''',
    '''    "experiment_id": "exp-20260919-hybrid-family-v4",
    "status": "completed" if not BLOCKED else "completed_with_blocked_config",''')
rep('''    "command": [sys.executable,
                "artifacts/runs/20260919T063022-hybrid-v2-2k5b/scripts/"
                "runner_hybrid_v2.py"],''',
    '''    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_hybrid_v4.py"],''')
rep('''    "h2a0_regression": regression,''',
    '''    "h4a0_regression": regression,''')
rep('''    "trial_accounting": {"this_round": "1 family (8 configs, all run)",
                         "cumulative_lineage": "205->214 already includes v1; "
                                               "v2 verdict -> 214->222 "
                                               "(config json trial_accounting)"},''',
    '''    "trial_accounting": {"this_round": "1 family (9 configs, all run)",
                         "cumulative_lineage": "v1 205->214; v2 214->222; "
                                               "v3 222->229; v4 verdict -> "
                                               "229->238 (config json "
                                               "trial_accounting)"},''')

DST.write_text(text, encoding="utf-8")
print(f"adapt OK: {n_edits} replacements -> {DST}")
