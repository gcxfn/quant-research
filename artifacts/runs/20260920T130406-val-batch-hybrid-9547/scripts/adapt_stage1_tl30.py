# -*- coding: utf-8 -*-
"""adapt v3 hybrid runner -> val runner (exp-20260919-hybrid-family-val).

Base: artifacts/runs/20260919T110500-hybrid-v3-r3ld/scripts/runner_hybrid_v3.py
(engine v1.2).  Output: runner_hybrid_val.py pinned to engine v1.3 with a
VAL_WINDOW env switch ("dev" anchor phase / "val" consumption phase).

Every replacement asserts a unique hit (or an exact expected count) and the
script aborts on any mismatch -- no silent partial adaptation.
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "runner_hybrid_v3.py")
DST = os.path.join(HERE, "runner_hybrid_val.py")

s = io.open(SRC, encoding="utf-8").read()
n0 = len(s)
reps = []


def rep(old, new, count=1):
    global s
    c = s.count(old)
    assert c == count, f"expected {count} hit(s), got {c}: {old[:80]!r}"
    s = s.replace(old, new)
    reps.append((old.splitlines()[0][:60], c))


# --- A. import os ------------------------------------------------------------
rep("import platform\n", "import os\nimport platform\n")

# --- B. engine pin v1.2 -> v1.3 ---------------------------------------------
rep('ENGINE_SHA_EXPECT_FULL = ("ceb7be6414280e4c5d5f37dc6ca1148a85e306b2de1a2161"\n'
    '                          "47f67f89cc4a746d")',
    'ENGINE_SHA_EXPECT_FULL = ("84a2443ac28fe1b87e4a18f988fd38cc67cf706d5778e"\n'
    '                          "262f11465147234082c")')

# --- C. window parametrization ----------------------------------------------
rep("DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)\n",
    '_WINDOW = os.environ.get("VAL_WINDOW", "dev")\n'
    'assert _WINDOW in ("dev", "val"), _WINDOW\n'
    '_GK = "dev" if _WINDOW == "dev" else "val"\n'
    '_PASSKEY = "dev_pass" if _WINDOW == "dev" else "val_pass"\n'
    'if _WINDOW == "val":\n'
    '    DEV_START, DEV_END = date(2021, 1, 4), date(2024, 12, 31)\n'
    'else:\n'
    '    DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)\n')

# --- D. CONFIG_IDS ------------------------------------------------------------
rep('CONFIG_IDS = ["R3-A0", "R3-01", "R3-02", "R3-03", "R3-04",\n'
    '              "R3-05", "R3-06"]',
    'CONFIG_IDS = ["R3-A0", "R3-05", "R3-06"]')

# --- E. CFGS block -> 3 val configs (R3-A0 keeps its id = ROT-05 verbatim) ---
old_cfgs = '''CFGS = {
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
}'''
new_cfgs = '''CFGS = {
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
}'''
rep(old_cfgs, new_cfgs)

# --- F. DIVIDEND_EXPECT window-conditional -----------------------------------
rep('DIVIDEND_EXPECT = {"sh.510050": 5, "sh.510300": 6, "sh.510880": 6,\n'
    '                   "sh.511010": 1}                 # frozen: 18 events in dev',
    'DIVIDEND_EXPECT = ({"sh.510050": 5, "sh.510300": 6, "sh.510880": 6,\n'
    '                    "sh.511010": 1} if _WINDOW == "dev" else   # 18 dev\n'
    '                   {"sh.510050": 4, "sh.510300": 4, "sh.510880": 4})\n'
    'DIVIDEND_EXPECT_N = 18 if _WINDOW == "dev" else 12   # val: 12 events')

# --- G. dividend count assert -------------------------------------------------
rep('if dict(counts) != DIVIDEND_EXPECT or dividend_events.height != 18:',
    'if dict(counts) != DIVIDEND_EXPECT \\\n'
    '        or dividend_events.height != DIVIDEND_EXPECT_N:')

# --- H. corporate actions block (insert after the dividend _fail) ------------
rep('    _fail(f"dividend events != frozen expectation {DIVIDEND_EXPECT}: '
    '{counts}")',
    '    _fail(f"dividend events != frozen expectation {DIVIDEND_EXPECT}: "\n'
    '          f"{counts}")\n'
    '\n'
    '# --- corporate actions (contract sec9 rev1: announced integer ratios) ---\n'
    'corp_rows = []\n'
    'for r in det8.iter_rows(named=True):\n'
    '    m = r["symbol"]\n'
    '    fmap = factor_map[m]\n'
    '    dd = dint_of(r["date"])\n'
    '    sub = etf_panel.filter(pl.col("symbol") == m)\n'
    '    prev_days = [x for x in dints(sub["date"]) if x < dd]\n'
    '    if not prev_days:\n'
    '        continue\n'
    '    d_prev = max(prev_days)\n'
    '    if dd not in fmap or d_prev not in fmap:\n'
    '        continue\n'
    '    ratio = fmap[dd] / fmap[d_prev]\n'
    '    if ratio > 1.5:\n'
    '        corp_rows.append({"symbol": m, "date": r["date"],\n'
    '                          "factor_jump": ratio})\n'
    'CA_ANNOUNCED = {"sh.513100": 5.0, "sh.513500": 2.0}\n'
    'corp_rows = [{"symbol": r["symbol"], "date": r["date"],\n'
    '              "ratio": CA_ANNOUNCED[r["symbol"]],\n'
    '              "factor_jump": r["factor_jump"]} for r in corp_rows]\n'
    'CORP_ACTIONS = pl.DataFrame(corp_rows, schema={\n'
    '    "symbol": pl.String, "date": pl.Date, "ratio": pl.Float64,\n'
    '    "factor_jump": pl.Float64}).sort("symbol", "date")\n'
    'ca_counts = Counter(CORP_ACTIONS["symbol"].to_list())\n'
    'log(f"  corporate actions built: {CORP_ACTIONS.height} {dict(ca_counts)}")\n'
    'if _WINDOW == "val":\n'
    '    expect_ca = {"sh.513100": 1, "sh.513500": 1}\n'
    '    if dict(ca_counts) != expect_ca or CORP_ACTIONS.height != 2:\n'
    '        _fail(f"corporate actions != val expectation {expect_ca}: "\n'
    '              f"{ca_counts}")\n'
    '    for r in CORP_ACTIONS.iter_rows(named=True):\n'
    '        if abs(r["factor_jump"] / r["ratio"] - 1.0) > 0.02:\n'
    '            _fail(f"factor_jump/ratio > 2% for {r}")\n'
    '        log(f"    {r[\'symbol\']} {r[\'date\']} ratio={r[\'ratio\']:.0f} "\n'
    '            f"factor_jump={r[\'factor_jump\']:.4f}")\n'
    'else:\n'
    '    if CORP_ACTIONS.height != 0:\n'
    '        _fail(f"dev window must have zero corporate actions: {ca_counts}")\n'
    'CORP_ACTIONS_ARG = CORP_ACTIONS if _WINDOW == "val" else None')

# --- I. signal window assert --------------------------------------------------
rep("assert sig_days and sig_days[-1] <= date(2020, 12, 31)",
    "assert sig_days and sig_days[-1] <= DEV_END")

# --- J. leg/membership artifact loads: empty on val ---------------------------
rep('leg_all = pl.read_parquet(R16_RUN / "leg_log.parquet").filter(\n'
    '    pl.col("plan_date").is_in(sig_days))',
    'leg_all = (pl.read_parquet(R16_RUN / "leg_log.parquet")\n'
    '           if _WINDOW == "dev" else\n'
    '           pl.DataFrame(schema={"config_id": pl.String,\n'
    '                                "plan_date": pl.Date,\n'
    '                                "symbol": pl.String,\n'
    '                                "kind": pl.String,\n'
    '                                "outcome": pl.String})).filter(\n'
    '    pl.col("plan_date").is_in(sig_days))')
rep('me = pl.read_parquet(R16_RUN / "membership_events.parquet").filter(\n'
    '    pl.col("signal").is_in(sig_days))',
    'me = (pl.read_parquet(R16_RUN / "membership_events.parquet")\n'
    '      if _WINDOW == "dev" else\n'
    '      pl.DataFrame(schema={"config_id": pl.String,\n'
    '                           "signal": pl.Date})).filter(\n'
    '    pl.col("signal").is_in(sig_days))')

# --- K. B1(m) port block replaces `del hist` ----------------------------------
rep("del hist\n",
    'if True:\n'
    '    bank_syms = sorted({s for t in sig_days\n'
    '                        for s in pools_at[t]["ranked"]})\n'
    '    bank = r16.PriceBank(hist, calendar_full, bank_syms)\n'
    '    b1_sim = r16.simulate_r16(\n'
    '        f"B1-T200-40-rate_only-{_WINDOW.upper()}", bank, calendar_full,\n'
    '        DEV_START, sig_days, pools_at, exposures, K=0, fractional=True,\n'
    '        fee_bands=r16.B1_FEE_SCHEDULE_RATE_ONLY)\n'
    '    _bm = r16.segment_metrics(b1_sim, DEV_START, DEV_END, None,\n'
    '                              fractional=True)\n'
    '    if _WINDOW == "dev":\n'
    '        for _k, _ref in (("net_cagr", B1["b1m_net_cagr"]),\n'
    '                         ("max_drawdown", B1["b1m_max_drawdown"])):\n'
    '            if abs(_bm[_k] - _ref) > 1e-9:\n'
    '                _fail(f"B1m dev port-check mismatch {_k}: "\n'
    '                      f"{_bm[_k]} vs r16_metrics {_ref}")\n'
    '        _yr_ref = {int(k): v for k, v in\n'
    '                   B1["b1m_net_return_by_year"].items()}\n'
    '        _yr_new = {int(k): v for k, v in\n'
    '                   _bm["net_return_by_year"].items()}\n'
    '        if set(_yr_ref) != set(_yr_new) or any(\n'
    '                abs(_yr_ref[k] - _yr_new[k]) > 1e-9\n'
    '                for k in _yr_ref):\n'
    '            _fail(f"B1m dev port-check by-year mismatch: "\n'
    '                  f"{_yr_new} vs {_yr_ref}")\n'
    '        log("  B1m dev port-check: reproduces r16_metrics to 1e-9 PASS")\n'
    '    else:\n'
    '        B1 = {"b1m_net_cagr": _bm["net_cagr"],\n'
    '              "b1m_max_drawdown": _bm["max_drawdown"],\n'
    '              "b1m_net_return_by_year": _bm["net_return_by_year"],\n'
    '              "b1m_variant": "rate_only (val recomputed in-runner)"}\n'
    '        log(f"  B1(m)(val): net_cagr {B1[\'b1m_net_cagr\']:+.6f}, "\n'
    '            f"mdd {B1[\'b1m_max_drawdown\']:.4f}")\n'
    'del hist\n')

# --- L. C05 frame dev-artifact check: dev only --------------------------------
rep('c05_ref = pl.read_parquet(P3R2_RUN / "outputs/C05_intents.parquet")\n'
    'if not C05_FRAME.equals(c05_ref):\n'
    '    _fail("rebuilt C05 intent frame != P3R2 C05_intents.parquet (.equals)")\n'
    'log("  C05 frame == P3R2 C05_intents.parquet (.equals) PASS")',
    'if _WINDOW == "dev":\n'
    '    c05_ref = pl.read_parquet(P3R2_RUN / "outputs/C05_intents.parquet")\n'
    '    if not C05_FRAME.equals(c05_ref):\n'
    '        _fail("rebuilt C05 intent frame != P3R2 C05_intents.parquet "\n'
    '              "(.equals)")\n'
    '    log("  C05 frame == P3R2 C05_intents.parquet (.equals) PASS")\n'
    'else:\n'
    '    log("  C05 frame check skipped (val window; anchor verified in the "\n'
    '        "dev phase of this same adapted runner)")')

# --- M. engine call: pass corporate_actions -----------------------------------
rep('        symbol_meta=inp["meta"], dividend_events=inp["events"],\n'
    '        initial_cash=200_000.0)',
    '        symbol_meta=inp["meta"], dividend_events=inp["events"],\n'
    '        corporate_actions=CORP_ACTIONS_ARG,\n'
    '        initial_cash=200_000.0)')

# --- N. anchor regression: dev-only failure gate ------------------------------
rep('if not all(regression.values()):\n'
    '    _fail(f"R3-A0 REGRESSION FAILURE: {regression} -- abort before remaining "\n'
    '          "configs per v3 prereg stop clause (R3-A0 != v2 ROT-05)")\n'
    'log("  R3-A0 regression anchor PASS (== v2 ROT-05, 5/5 frames)")',
    'if _WINDOW == "dev":\n'
    '    if not all(regression.values()):\n'
    '        _fail(f"R3-A0 REGRESSION FAILURE: {regression} -- abort before "\n'
    '              "remaining configs per val prereg sec 6 (R3-A0 != v2 "\n'
    '              "ROT-05)")\n'
    '    log("  R3-A0 regression anchor PASS (== v2 ROT-05, 5/5 frames)")\n'
    'else:\n'
    '    log("  R3-A0 anchor SKIPPED on val window (verified in the dev "\n'
    '        "phase of this same adapted runner; per val prereg sec 6)")')

# --- O. metrics dict: goal key + window + b1m_source --------------------------
rep('         "goal_dev_net_cagr_ge_10pct": net_cagr >= 0.10,',
    '         "goal_net_cagr_ge_10pct": net_cagr >= 0.10,\n'
    '         "window": _WINDOW,')
rep('         "b1m_source": "R16 metrics.json configs.C05 verbatim "\n'
    '                       "(T200-40/rate_only; family anchor)",',
    '         "b1m_source": ("R16 metrics.json configs.C05 verbatim "\n'
    '                        "(T200-40/rate_only; family anchor)"\n'
    '                        if _WINDOW == "dev" else\n'
    '                        "in-runner val recompute (T200-40/rate_only; "\n'
    '                        "val prereg sec4; dev port-checked to 1e-9)"),')

# --- P. gates dict: window-conditional ----------------------------------------
rep('    g = {"1_net_cagr_gt_0": net_cagr > 0,\n'
    '         "2_excess_vs_B1m_ge_2pp": excess >= 0.020,\n'
    '         "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,\n'
    '         "4_mdd_le_20pct_and_le_B1m":\n'
    '             abs(mdd) <= 0.20 + 1e-12\n'
    '             and abs(mdd) <= abs(B1["b1m_max_drawdown"]) + 1e-12,\n'
    '         "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,\n'
    '         "6_single_name_weight_le_40pct": wmax <= 0.40,\n'
    '         "7_vs_B3prime_plus_1pp": net_cagr >= B3P[B1_PATH_NAME] + 0.010,\n'
    '         "8v3_final_delivery_ge_99pct": g8v3["gate_pass"],\n'
    '         "advantage_years": len(adv), "dev_excess_vs_b1m": excess}',
    '    if _WINDOW == "dev":\n'
    '        g = {"1_net_cagr_gt_0": net_cagr > 0,\n'
    '             "2_excess_vs_B1m_ge_2pp": excess >= 0.020,\n'
    '             "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,\n'
    '             "4_mdd_le_20pct_and_le_B1m":\n'
    '                 abs(mdd) <= 0.20 + 1e-12\n'
    '                 and abs(mdd) <= abs(B1["b1m_max_drawdown"]) + 1e-12,\n'
    '             "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,\n'
    '             "6_single_name_weight_le_40pct": wmax <= 0.40,\n'
    '             "7_vs_B3prime_plus_1pp": net_cagr >= B3P[B1_PATH_NAME] + 0.010,\n'
    '             "8v3_final_delivery_ge_99pct": g8v3["gate_pass"],\n'
    '             "advantage_years": len(adv), "dev_excess_vs_b1m": excess}\n'
    '    else:\n'
    '        g = {"1_excess_ge_1pp": excess >= 0.010,\n'
    '             "2_advantage_years_ge_2_of_4": len(adv) >= 2 and len(b1y) == 4,\n'
    '             "3_mdd_le_20pct_and_le_B1m":\n'
    '                 abs(mdd) <= 0.20 + 1e-12\n'
    '                 and abs(mdd) <= abs(B1["b1m_max_drawdown"]) + 1e-12,\n'
    '             "advantage_years": len(adv), "val_excess_vs_b1m": excess}')

# --- Q. gates assignment + verdict --------------------------------------------
rep('    g["failed_gates"] = sorted(k for k in GATE_KEYS if not g[k])\n'
    '    g["dev_pass"] = not g["failed_gates"]\n'
    '    g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"\n'
    '    metrics[cid] = m\n'
    '    gates[cid] = {"dev": g, "verdict": g["verdict"]}',
    '    g["failed_gates"] = sorted(k for k in GATE_KEYS if not g[k])\n'
    '    if _WINDOW == "dev":\n'
    '        g["dev_pass"] = not g["failed_gates"]\n'
    '        g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"\n'
    '        gates[cid] = {"dev": g, "verdict": g["verdict"]}\n'
    '    else:\n'
    '        g["val_pass"] = not g["failed_gates"]\n'
    '        g["verdict"] = "val_pass" if g["val_pass"] else "val_eliminated"\n'
    '        gates[cid] = {"val": g, "verdict": g["verdict"]}\n'
    '    metrics[cid] = m')

# --- R/S/T/U/V. window-aware lookups in logs/report ---------------------------
rep("if g['dev_pass'] else", "if g.get(_PASSKEY) else", count=2)
rep('gates[cid]["dev"]["dev_pass"]', 'gates[cid][_GK][_PASSKEY]', count=4)
rep('"verdict": gates[cid]["dev"]["verdict"],',
    '"verdict": gates[cid][_GK]["verdict"],')
rep('m, g = metrics[cid], gates[cid]["dev"]',
    'm, g = metrics[cid], gates[cid][_GK]')
rep("f\"adv {len(adv)}/6 mdd", "f\"adv {len(adv)}/{len(b1y)} mdd")
rep("| {g['advantage_years']}/6 ", "| {g['advantage_years']}/{len(m['b1m_net_return_by_year'])} ")
rep("| {e['advantage_years']}/6 ", "| {e['advantage_years']}/{len(m['b1m_net_return_by_year'])} ")
rep('f"- 窗口 dev {DEV_START}..{DEV_END}，信号 {sig_days[0]}..{sig_days[-1]}"',
    'f"- 窗口 {_WINDOW} {DEV_START}..{DEV_END}，信号 {sig_days[0]}..{sig_days[-1]}"')

# --- W. GATE_KEYS window-conditional ------------------------------------------
rep('GATE_KEYS = ["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",\n'
    '             "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",\n'
    '             "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",\n'
    '             "7_vs_B3prime_plus_1pp", "8v3_final_delivery_ge_99pct"]',
    'GATE_KEYS = (["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",\n'
    '              "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",\n'
    '              "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",\n'
    '              "7_vs_B3prime_plus_1pp", "8v3_final_delivery_ge_99pct"]\n'
    '             if _WINDOW == "dev" else\n'
    '             ["1_excess_ge_1pp", "2_advantage_years_ge_2_of_4",\n'
    '              "3_mdd_le_20pct_and_le_B1m"])')

# --- X. gate-failure label dict: val keys + safe lookup -----------------------
rep('    return "; ".join(msgs[k] for k in f) if f else "all gates pass"',
    '    if _WINDOW == "val":\n'
    '        msgs.update({"1_excess_ge_1pp": "excess<+1pp (val gate 1)",\n'
    '                     "2_advantage_years_ge_2_of_4":\n'
    '                         "advantage years<2/4 (val gate 2)",\n'
    '                     "3_mdd_le_20pct_and_le_B1m":\n'
    '                         "maxDD breach (val gate 3)"})\n'
    '    return "; ".join(msgs.get(k, k) for k in f) if f else "all gates pass"')

# --- Y. remaining goal-key usages (log lines + report) ------------------------
rep("goal_dev_net_cagr_ge_10pct", "goal_net_cagr_ge_10pct", count=3)

# --- Z. C05 membership consistency loop: dev-only (val has no leg_log artifact)
rep('mismembers, mismev = 0, 0\n'
    'prev: list[str] = []\n'
    'for t in sig_days:',
    'mismembers, mismev = 0, 0\n'
    'prev: list[str] = []\n'
    'for t in (sig_days if _WINDOW == "dev" else []):')

# --- S-val-1: clamp expiry beyond the freeze line (final-signal intents) ------
rep('    fr = pl.DataFrame(rows, schema=INTENT_SCHEMA)\n'
    '    FRAMES[cid] = fr',
    '    fr = pl.DataFrame(rows, schema=INTENT_SCHEMA)\n'
    '    if _WINDOW == "val":\n'
    '        _n_exp = fr.filter(pl.col("expiry_date") > date(2024, 12, 31)).height\n'
    '        if _n_exp:\n'
    '            log(f"  {cid}: S-val-1 clamp {_n_exp} expiry rows -> "\n'
    '                "2024-12-31 (freeze boundary seam, prereg sec 10)")\n'
    '            fr = fr.with_columns(\n'
    '                pl.when(pl.col("expiry_date") > date(2024, 12, 31))\n'
    '                .then(pl.lit(date(2024, 12, 31)))\n'
    '                .otherwise(pl.col("expiry_date"))\n'
    '                .alias("expiry_date"))\n'
    '    FRAMES[cid] = fr')

# --- Z2. remaining live gates[cid]["dev"] refs (v1_mg artifact refs untouched)
rep('gates[cid]["dev"]', 'gates[cid][_GK]', count=3)

io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print(f"adapted OK: {len(reps)} replacement groups, {n0} -> {len(s)} chars")
for name, c in reps:
    print(f"  x{c}  {name}")
