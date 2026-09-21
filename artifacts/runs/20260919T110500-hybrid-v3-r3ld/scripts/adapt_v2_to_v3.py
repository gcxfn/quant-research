# -*- coding: utf-8 -*-
"""v2 -> v3 runner adaptation (exp-20260919-hybrid-family-v3).

Applies the frozen v3 differences to a byte-copy of the v2 runner
(20260919T063022-hybrid-v2-2k5b/scripts/runner_hybrid_v2.py):
- 7-config bond-weight ladder (R3-A0 anchor + R3-01..06);
- R3-A0 regression anchor vs the v2 run's ROT-05 outputs (5 frames);
- rotation displacement vs R3-A0 replaces stock displacement vs H2-A0;
- bond-ladder monotonicity disclosure replaces the ROT-04/ROT-01 block;
- v3 stop clauses (user 2026-09-19 ruling: goal-hit stops; gate-pass <10%
  continues; all-eliminated pauses); trial accounting 222->229.

Every replacement asserts the old text occurs EXACTLY ONCE; any mismatch
aborts without writing.  Output: scripts/runner_hybrid_v3.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
SRC = RUN_DIR / "tmp/runner_hybrid_v2_source.py"
DST = RUN_DIR / "scripts/runner_hybrid_v3.py"

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
    '''Copy-adapted from the v2 runner (20260919T063022-hybrid-v2-2k5b) per the v3
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
  variants are slightly pessimistic vs reality (conservative, disclosed).''')

# --- E2: path constants ------------------------------------------------------
rep('''V1_RUN = ROOT / "artifacts/runs/20260919T054649-hybrid-v1-9k2f"
PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v2-prereg.md"''',
    '''V1_RUN = ROOT / "artifacts/runs/20260919T054649-hybrid-v1-9k2f"
V2_RUN = ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b"
PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v3-prereg.md"
V2_PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v2-prereg.md"''')
rep('HYB_CONFIG = ROOT / "configs/experiments/hybrid-family-v2.json"',
    'HYB_CONFIG = ROOT / "configs/experiments/hybrid-family-v3.json"')

# --- E3: pins EXPECTED -------------------------------------------------------
rep('''    "prereg": (None, PREREG_MD),
    "v1_prereg_inherited": (None, V1_PREREG_MD),
    "hyb_config": (None, HYB_CONFIG),''',
    '''    "prereg": (None, PREREG_MD),
    "v2_prereg_inherited": (None, V2_PREREG_MD),
    "v1_prereg_inherited": (None, V1_PREREG_MD),
    "hyb_config": (None, HYB_CONFIG),
    "v2_metrics_rot05_anchor_source":
        (None, V2_RUN / "outputs/metrics_and_gates.json"),''')

# --- E4: CONFIG_IDS + CFGS ---------------------------------------------------
rep('''CONFIG_IDS = ["H2-A0", "H2-01", "H2-02", "H2-03", "H2-04",
              "ROT-03R", "ROT-04", "ROT-05"]''',
    '''CONFIG_IDS = ["R3-A0", "R3-01", "R3-02", "R3-03", "R3-04",
              "R3-05", "R3-06"]''')
rep('''# config table (v2 prereg sec 2 / config json configs; "park" column =
# sum of per-symbol leg weights, each <= 25%: S4 structure fix)''',
    '''# config table (v3 prereg sec 2 / config json configs): bond-weight
# ladder on the ROT-05 structure; every leg symbol <= 25%; R3-A0 = ROT-05
# verbatim replica used ONLY as the regression anchor''')
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
    "R3-A0": {"stock": None, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},   # = ROT-05 verbatim (anchor)
    "R3-01": {"stock": None, "legs": {"sh.511010": 0.20,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-02": {"stock": None, "legs": {"sh.511010": 0.15,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-03": {"stock": None, "legs": {"sh.511010": 0.10,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-04": {"stock": None, "legs": {"sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-05": {"stock": None, "legs": {"sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-06": {"stock": None, "legs": {"sh.511010": 0.15,
                                      "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 3, "weight": 0.20,
                           "lookback_m": 6}},
}''')

# --- E5: INPUTS branch (drop p3r2_verbatim mode) -----------------------------
rep('''    if cid == "H2-A0":
        INPUTS[cid] = {"daily": daily_c, "half": half_c, "limits": limits_c,
                       "splits": splits_c, "dividends": divs_c,
                       "instruments": instr_c, "meta": None, "events": None,
                       "mode": "p3r2_verbatim"}
    elif cfg["stock"]:''',
    '''    if cfg["stock"]:''')

# --- E6a: section-10 header --------------------------------------------------
rep('''# === 10. H2-A0 smoke: engine regression anchor ==============================
log("== 10. H2-A0 regression anchor vs P3R2 C05 ==")''',
    '''# === 10. R3-A0 regression anchor vs v2 ROT-05 ==============================
log("== 10. R3-A0 regression anchor vs v2 ROT-05 ==")''')

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
    '''# R3-A0 regression: 5-frame .equals vs the v2 run's ROT-05 outputs +
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
if not all(regression.values()):
    _fail(f"R3-A0 REGRESSION FAILURE: {regression} -- abort before remaining "
          "configs per v3 prereg stop clause (R3-A0 != v2 ROT-05)")
log("  R3-A0 regression anchor PASS (== v2 ROT-05, 5/5 frames)")''')

# v2 metrics loaded next to the other json pins (v1 metrics loader kept:
# lineage reference)
rep('''# v1 judgment table: source of the ROT-04 vs ROT-01 universe-sensitivity column
v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))''',
    '''v2_mg = json.loads((V2_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))
# v1 metrics: lineage reference only in v3 (universe-sensitivity block retired)
v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))''')

# --- E7: section 11 excludes the anchor by its new id ------------------------
rep('for cid in [c for c in CONFIG_IDS if c != "H2-A0" and c in FRAMES]:',
    'for cid in [c for c in CONFIG_IDS if c != "R3-A0" and c in FRAMES]:')

# --- E8: rotation fill profile replaces the stock fill profile ---------------
rep('''def stock_leg_fill_profile(cid: str) -> dict:
    res = results[cid]["res"]
    f = res.fills.filter(~pl.col("symbol").is_in(PANEL_SYMS)) \\
        if res.fills.height else res.fills
    if f.height:
        first_fill = str(f["date"].min())
        n_stock_fills = f.height
        n_stock_buy_fills = int((f["side"] == "buy").sum())
    else:
        first_fill, n_stock_fills, n_stock_buy_fills = None, 0, 0
    # per-intent stock fill rate (R16-mapped caliber, restricted to stocks)
    a = attr[cid]
    n_stock_intents = sum(1 for (s, _sd, _t) in a["outcomes"]
                          if s not in PANEL_SYMS)
    n_stock_intents_filled = sum(1 for (s, _sd, _t), v in
                                 a["outcomes"].items()
                                 if s not in PANEL_SYMS and v == "filled")
    return {"stock_fills": n_stock_fills,
            "stock_buy_fills": n_stock_buy_fills,
            "stock_intents": n_stock_intents,
            "stock_intents_filled": n_stock_intents_filled,
            "stock_intent_fill_rate": (n_stock_intents_filled
                                       / n_stock_intents)
                                      if n_stock_intents else None,
            "first_stock_fill_date": first_fill,
            "insufficient_cash_orders":
                res.stats["cash_friction"]["insufficient_cash_orders"],
            "limit_fill_rate_orders": (
                (res.stats["intent_layer"]["stopped_filled"]
                 / res.stats["intent_layer"]["orders_generated"])
                if res.stats["intent_layer"]["orders_generated"] else None)}''',
    '''def rotation_fill_profile(cid: str) -> dict:
    """v3: rotation-slot displacement profile (no stock configs in v3)."""
    res = results[cid]["res"]
    f = res.fills.filter(pl.col("symbol").is_in(UNI6)) \\
        if res.fills.height else res.fills
    n_rot_fills = f.height
    n_rot_buy_fills = int((f["side"] == "buy").sum()) if f.height else 0
    rot_log = ROT_LOG.get(cid) or []
    n_entries = sum(len(e["entries"]) for e in rot_log)
    n_exits = sum(len(e["exits"]) for e in rot_log)
    return {"rotation_fills": n_rot_fills,
            "rotation_buy_fills": n_rot_buy_fills,
            "rotation_entries_emitted": n_entries,
            "rotation_exits_emitted": n_exits,
            "insufficient_cash_orders":
                res.stats["cash_friction"]["insufficient_cash_orders"],
            "orders_generated":
                res.stats["intent_layer"]["orders_generated"],
            "limit_filled_orders":
                res.stats["intent_layer"]["stopped_filled"]}''')

# --- E9: displacement loop ----------------------------------------------------
rep('''        "6_stock_leg_vs_A0": None,
    }
base_profile = stock_leg_fill_profile("H2-A0")
for cid in results:
    if cid == "H2-A0" or not CFGS[cid]["stock"]:
        continue
    prof = stock_leg_fill_profile(cid)
    disclosures[cid]["6_stock_leg_vs_A0"] = {
        "h2a0": base_profile, "this": prof,
        "delta_stock_fills": prof["stock_fills"] - base_profile["stock_fills"],
        "delta_stock_fill_rate": (
            (prof["stock_intent_fill_rate"] - base_profile["stock_intent_fill_rate"])
            if prof["stock_intent_fill_rate"] is not None
            and base_profile["stock_intent_fill_rate"] is not None else None),
        "delta_first_fill_days": (
            (date.fromisoformat(prof["first_stock_fill_date"])
             - date.fromisoformat(base_profile["first_stock_fill_date"])).days
            if prof["first_stock_fill_date"]
            and base_profile["first_stock_fill_date"] else None),
        "insufficient_cash_orders_this": prof["insufficient_cash_orders"],
        "caliber": "stock displacement vs H2-A0 (v2 prereg sec 4-1): fills "
                   "count / per-intent fill rate / first-fill entry delay; "
                   "insufficient-cash voids are the park cash-competition cost"}''',
    '''        "6_rotation_vs_A0": None,
    }
base_profile = rotation_fill_profile("R3-A0")
for cid in results:
    if cid == "R3-A0":
        continue
    prof = rotation_fill_profile(cid)
    disclosures[cid]["6_rotation_vs_A0"] = {
        "r3a0": base_profile, "this": prof,
        "delta_rotation_fills":
            prof["rotation_fills"] - base_profile["rotation_fills"],
        "delta_insufficient_cash":
            prof["insufficient_cash_orders"]
            - base_profile["insufficient_cash_orders"],
        "caliber": "rotation-slot displacement vs R3-A0 (v3 prereg sec 4-2): "
                   "UNI6-symbol fills / emitted entries-exits / "
                   "insufficient-cash orders; top3 variants are expected to "
                   "compete harder for cash (disclosed, not gated)"}''')

# --- E10: bond-ladder monotonicity replaces universe sensitivity -------------
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
    '''# --- v3 disclosure: bond-weight ladder monotonicity (prereg sec 4-3) -------
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
                    "advantage_years": gates[cid]["dev"]["advantage_years"],
                    "failed_gates": gates[cid]["dev"]["failed_gates"],
                    "rotation_top_n": (CFGS[cid]["rotation"]["top_n"]
                                       if CFGS[cid]["rotation"] else None)})
disclosures["bond_ladder_monotonicity"] = {
    "ladder": _ladder,
    "note": "bond weight 0.25 -> 0 trajectory of net CAGR / maxDD; "
            "non-monotonicity means structural sensitivity, not linear "
            "opportunity cost (v3 prereg sec 4-3); R3-A0 is the 0.25 point"}''')

# --- E11: report prose --------------------------------------------------------
rep('''rep = ["# 混合族 v2 判定（exp-20260919-hybrid-family-v2）", "",''',
    '''rep = ["# 混合族 v3 判定（exp-20260919-hybrid-family-v3，降债阶梯）", "",''')
rep('''       f"- H2-A0 回归锚：fills/events/daily_equity/clips_final 与 P3R2 C05 "
       f"逐帧 polars `.equals()` 全部一致（4/4 PASS），判定链有效。",''',
    '''       f"- R3-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v2 ROT-05 输出逐帧 polars `.equals()` 全部一致（5/5 PASS），"
       f"判定链有效；R3-A0 判定以 v2 为准，不重判。",''')
rep('''       f"（{len(sig_days)} 个月末，2020-12-31 丢弃）；val 2021–2024 零消费。",''',
    '''       f"（{len(sig_days)} 个月末，2020-12-31 丢弃）；val 2021–2024 零消费"
       f"（用户 2026-09-19 裁定暂不消费，继续 dev）。",''')
rep('''       f"`{pins['prereg']['sha256'][:16]}`（已冻结，运行中零修改）；继承条款 "
       f"v1 预登记 sha256:16 `{pins['v1_prereg_inherited']['sha256'][:16]}`。",''',
    '''       f"`{pins['prereg']['sha256'][:16]}`（已冻结，运行中零修改）；继承条款 "
       f"v2 预登记 sha256:16 `{pins['v2_prereg_inherited']['sha256'][:16]}`"
       f"（其再继承 v1 sha256:16 "
       f"`{pins['v1_prereg_inherited']['sha256'][:16]}`）。",''')
rep('''    comp = d.get("6_stock_leg_vs_A0")
    comp_txt = ""
    if comp:
        rate_this = comp["this"]["stock_intent_fill_rate"]
        rate_a0 = comp["h2a0"]["stock_intent_fill_rate"]
        comp_txt = (
            f"；vs H2-A0: 股票成交 {comp['delta_stock_fills']:+d} 单, "
            f"成交率 {rate_a0*100:.1f}%→{rate_this*100:.1f}%"
            f"（Δ{(comp['delta_stock_fill_rate'] or 0)*100:+.1f}pp）, "
            f"首成交延迟 {comp['delta_first_fill_days']:+d} 日, "
            f"现金不足作废 {comp['insufficient_cash_orders_this']} 次"
            if rate_this is not None and rate_a0 is not None else
            f"；vs H2-A0: 股票成交 {comp['delta_stock_fills']:+d} 单, "
            f"首成交延迟 {comp['delta_first_fill_days']:+d} 日, "
            f"现金不足作废 {comp['insufficient_cash_orders_this']} 次")''',
    '''    comp = d.get("6_rotation_vs_A0")
    comp_txt = ""
    if comp:
        comp_txt = (
            f"；vs R3-A0: 轮动成交 {comp['delta_rotation_fills']:+d} 单, "
            f"现金不足作废 {comp['this']['insufficient_cash_orders']} 次"
            f"（锚 {comp['r3a0']['insufficient_cash_orders']} 次）")''')
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
    '''if "bond_ladder_monotonicity" in disclosures:
    rep += ["", "### 债权重阶梯单调性（v3 预登记 §4-3）", "",
            "| 配置 | 债权重 | top_n | 净CAGR | maxDD | 超额 | 优势年 | 失败门 |",
            "|---|---|---|---|---|---|---|---|"]
    for e in disclosures["bond_ladder_monotonicity"]["ladder"]:
        rep.append(
            f"| {e['id']} | {e['bond_w']:.0%} | {e['rotation_top_n']} "
            f"| {e['net_cagr']*100:+.2f}% | {e['max_drawdown']*100:.2f}% "
            f"| {e['excess_vs_b1m']*100:+.2f}pp | {e['advantage_years']}/6 "
            f"| {', '.join(e['failed_gates']) or '-'} |")
    rep += ["- 轨迹若非单调 = 结构敏感而非线性机会成本；R3-A0 即 0.25 基点。",
            "- 引擎现金零收益：R3-01..04 腾出的债权重闲置为现金，相对现实"
            "（货基收益）略悲观，保守方向如实呈现。"]''')
rep('''        "## 三、H2-A0 回归锚", "",
        f"- 4/4 帧 `.equals()` 一致：{json.dumps({k: v for k, v in regression.items()})}",
        f"- 引擎 stats：intents {results['H2-A0']['res'].stats['intent_layer']['n_intents']}"
        f"，orders {results['H2-A0']['res'].stats['intent_layer']['orders_generated']}"
        f"，filled {results['H2-A0']['res'].stats['intent_layer']['stopped_filled']}。",''',
    '''        "## 三、R3-A0 回归锚（= v2 ROT-05 复刻）", "",
        f"- 5/5 帧 `.equals()` 一致：{json.dumps({k: v for k, v in regression.items()})}",
        f"- 引擎 stats：intents {results['R3-A0']['res'].stats['intent_layer']['n_intents']}"
        f"，orders {results['R3-A0']['res'].stats['intent_layer']['orders_generated']}"
        f"，filled {results['R3-A0']['res'].stats['intent_layer']['stopped_filled']}。",''')
rep('''        f"- 试验计账：本族判定计 1 项（8 配置族）；谱系 205→214 已含 v1，"
        "v2 判定后 214→222（如台账有异以台账为准）。",''',
    '''        f"- 试验计账：本族判定计 7 项（7 配置族）；谱系 v1 205→214、"
        "v2 214→222，v3 判定后 222→229（如台账有异以台账为准）。",''')
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
        "159934 的 2020-02-26 微偏离见冻结披露（v3 不使用该符号）。"]''')

# --- E12: mg dict -------------------------------------------------------------
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
                  "ROT branch PAUSED per the v3 stop clause (direction "
                  "re-evaluation is a separate user decision); val not "
                  "consumed")

mg = {
    "experiment_id": "exp-20260919-hybrid-family-v3",''')
rep('''    "h2a0_regression_anchor": {**regression,
                               "note": "polars .equals() vs P3R2 C05 "
                                       "outputs; mismatch = abort (did not "
                                       "trigger)"},''',
    '''    "r3a0_regression_anchor": {**regression,
                               "note": "polars .equals() vs v2 run ROT-05 "
                                       "outputs (intents/fills/events/daily/"
                                       "clips_final) + net_cagr match; "
                                       "mismatch = abort (did not trigger); "
                                       "R3-A0 is NOT re-adjudicated"},''')
rep('''    "v1_prereg_inherited_sha256_16": pins["v1_prereg_inherited"]["sha256"][:16],''',
    '''    "v2_prereg_inherited_sha256_16":
        pins["v2_prereg_inherited"]["sha256"][:16],
    "v1_prereg_inherited_sha256_16": pins["v1_prereg_inherited"]["sha256"][:16],''')
rep('''    "no_rejurisdiction": "v1-judged configs (HYB-05 etc.) are NOT re-judged "
                         "under 8v3; HYB-05's gate-4 failure is unrelated to "
                         "gate 8 -- conclusions unchanged (v2 prereg sec 3)",''',
    '''    "no_rejurisdiction": "v2-judged configs (H2-01/03/04, ROT-05) are NOT "
                         "re-run or re-judged in v3; R3-A0 is a regression "
                         "anchor only (v3 prereg sec 3)",''')
rep('''    "stop_note": ("STOP before val: >=1 config passed all dev gates; val "
                  "requires separate user approval" if n_pass else
                  f"no config passed all dev gates ({n_pass}/"
                  f"{len(gates)}); hybrid line PAUSED per the v2 stop clause "
                  "(direction re-evaluation is a separate user decision); "
                  "val not consumed"),''',
    '''    "stop_note": _STOP_NOTE,''')

# --- E13: manifest -------------------------------------------------------------
rep('''    "experiment_id": "exp-20260919-hybrid-family-v2",
    "status": "completed" if not BLOCKED else "completed_with_blocked_config",''',
    '''    "experiment_id": "exp-20260919-hybrid-family-v3",
    "status": "completed" if not BLOCKED else "completed_with_blocked_config",''')
rep('''    "command": [sys.executable,
                "artifacts/runs/20260919T063022-hybrid-v2-2k5b/scripts/"
                "runner_hybrid_v2.py"],''',
    '''    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_hybrid_v3.py"],''')
rep('''    "h2a0_regression": regression,''',
    '''    "r3a0_regression": regression,''')
rep('''    "trial_accounting": {"this_round": "1 family (8 configs, all run)",
                         "cumulative_lineage": "205->214 already includes v1; "
                                               "v2 verdict -> 214->222 "
                                               "(config json trial_accounting)"},''',
    '''    "trial_accounting": {"this_round": "1 family (7 configs, all run)",
                         "cumulative_lineage": "v1 205->214; v2 214->222; "
                                               "v3 verdict -> 222->229 "
                                               "(config json trial_accounting)"},''')

DST.write_text(text, encoding="utf-8")
print(f"adapt OK: {n_edits} replacements -> {DST}")
