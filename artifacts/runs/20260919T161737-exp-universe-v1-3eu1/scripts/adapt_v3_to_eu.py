# -*- coding: utf-8 -*-
"""adapt v3 hybrid runner -> expanded-universe v1 runner
(exp-20260919-expanded-universe-v1).

Base: artifacts/runs/20260919T110500-hybrid-v3-r3ld/scripts/runner_hybrid_v3.py
Output: runner_exp_universe.py pinned to engine v1.3 (sha 84a2443a...082c),
12 configs (EU-A0 anchor + EU-01..10), dev window pinned, corporate_actions
NOT passed, B1(m) dev port-check, EU45 panel block.

Every replacement asserts a unique hit (or an exact expected count) and the
script aborts on any mismatch -- no silent partial adaptation.
"""
import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "runner_hybrid_v3.py")
DST = os.path.join(HERE, "runner_exp_universe.py")

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
     '''"""exp-20260919-expanded-universe-v1 runner -- engine v1.3 (pin unchanged),
prereg FROZEN (docs/research/exp-20260919-expanded-universe-v1-prereg.md +
configs/experiments/expanded-universe-v1.json).

Copy-adapted from the v3 runner (20260919T110500-hybrid-v3-r3ld) by
adapt_v3_to_eu.py (asserted unique replacements only); all v3-inherited
clauses (band table all 0.10, dividend extraction rule, runner assertions,
fees, dev window, Design B leg semantics, gates 1-7 R16 + gate 8 v3,
benchmarks) verbatim.  EU-round differences (prereg sec 0-5):
- 12 configs (EU-A0 anchor + EU-01..10 universe/slot/lookback matrix) on the
  dev window (2015-2020) only; ALL results exploration-grade;
- EU-A0 = R3-06 verbatim replica and regression anchor: engine call panel/
  args identical to v3 R3-06 (incl. the v3 panel and the unused sz.159934);
  5-frame polars .equals() vs the v3 run's R3-06 outputs + net_cagr 1e-12 +
  parquet byte comparison; mismatch aborts the whole round with zero
  conclusions (prereg sec 4-1);
- EU-01..10 data panel = EU45 (U-EQ43 union legs = 45 symbols, frozen
  explicit symbol tables); rotation ranking cross-section = each config's
  universe subset; corporate_actions NOT passed (zero dev-window split
  events after the prereg sec 1 exclusions); dividend events = v3 rule
  applied to the 45-symbol panel, new-member dev counts disclosed; engine
  v1.3 anti-misclassification guard fail-closed (hard error -> stop, no
  data repair);
- B1(m) dev benchmark recomputed in-runner via the validated port
  (r16.simulate_r16 fractional, rate-only bands, T200-40), 1e-9 checked
  against R16 metrics AND the known dev values (+0.60% / -39.82%);
- roster eligibility (second-pass protocol) = dev 8 gates AND net CAGR >=
  10%; roster != champion; trials +10 (252 -> 262), anchor not counted.

EU_SMOKE=1 env switch restricts CONFIG_IDS to [EU-A0, EU-01] for the smoke
run (runner-level test only; the official run leaves it unset).

Deterministic; no RNG.  Spec seams are NOT silently resolved: they are
recorded and reported.  Budget 2700 s wall (12 configs).
"""''')

# --- B. import os ---------------------------------------------------------------
rep("import platform\n", "import os\nimport platform\n")

# --- C. run-path constants -------------------------------------------------------
rep('V2_RUN = ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b"',
    'V3_RUN = ROOT / "artifacts/runs/20260919T110500-hybrid-v3-r3ld"')
rep('PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v3-prereg.md"',
    'PREREG_MD = ROOT / "docs/research/'
    'exp-20260919-expanded-universe-v1-prereg.md"')
rep('HYB_CONFIG = ROOT / "configs/experiments/hybrid-family-v3.json"',
    'HYB_CONFIG = ROOT / "configs/experiments/expanded-universe-v1.json"')

# --- D. engine pin v1.2 -> v1.3 ---------------------------------------------------
rep('ENGINE_SHA_EXPECT_FULL = ("ceb7be6414280e4c5d5f37dc6ca1148a85e306b2de1a2161"\n'
    '                          "47f67f89cc4a746d")',
    'ENGINE_SHA_EXPECT_FULL = ("84a2443ac28fe1b87e4a18f988fd38cc67cf706d5778e"\n'
    '                          "262f11465147234082c")')

# --- E. CONFIG_IDS -> 12 EU configs (+ smoke switch) -------------------------------
rep('CONFIG_IDS = ["R3-A0", "R3-01", "R3-02", "R3-03", "R3-04",\n'
    '              "R3-05", "R3-06"]',
    '# EU_SMOKE=1 restricts to the smoke pair (runner-level test only; the\n'
    '# official run leaves it unset; smoke results are NOT the frozen run)\n'
    '_SMOKE = os.environ.get("EU_SMOKE", "") == "1"\n'
    '_ALL_CONFIG_IDS = ["EU-A0", "EU-01", "EU-02", "EU-03", "EU-04", "EU-05",\n'
    '                   "EU-06", "EU-07", "EU-08", "EU-09", "EU-10"]\n'
    'CONFIG_IDS = ["EU-A0", "EU-01"] if _SMOKE else _ALL_CONFIG_IDS')

# --- F. universe tables + CFGS block (EU prereg sec 2, FROZEN) ---------------------
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
}''',
     '''# config matrix (EU prereg sec 2 / configs/experiments/expanded-universe-v1.json,
# FROZEN): explicit universe symbol tables; legs constant; every single-slot
# weight <= 25% (S-rob-1 lesson); EU-A0 = R3-06 verbatim replica used ONLY as
# the regression anchor (not counted as a trial)
UNI6 = ["sh.510050", "sh.510300", "sz.159915", "sh.510880", "sh.513100",
        "sh.513500"]                                   # R3-06 rotation, verbatim
LEGS_EU = {"sh.511010": 0.15, "sh.518880": 0.25}       # frozen legs, all configs
U_EQ28 = ["sh.510050", "sh.510150", "sh.510180", "sh.510210", "sh.510300",
          "sh.510310", "sh.510330", "sh.510410", "sh.510510", "sh.510630",
          "sh.510650", "sh.510660", "sh.510880", "sh.512010", "sh.512070",
          "sh.512120", "sh.512990", "sz.159901", "sz.159902", "sz.159905",
          "sz.159915", "sz.159922", "sz.159928", "sz.159929", "sz.159930",
          "sz.159938", "sz.159939", "sz.160706"]
U_XB7 = ["sh.510900", "sh.513030", "sh.513100", "sh.513500", "sh.513600",
         "sh.513660", "sz.159920"]
U_MO8 = ["sh.511800", "sh.511810", "sh.511860", "sh.511880", "sh.511990",
         "sz.159001", "sz.159003", "sz.159005"]
U_EQ35 = U_EQ28 + U_XB7                                # 28 + 7 = 35 (disjoint)
U_EQ43 = U_EQ35 + U_MO8                                # 35 + 8 = 43 (disjoint)
U_SEC20 = UNI6 + ["sh.510150", "sh.510410", "sh.510630", "sh.510650",
                  "sh.510660", "sz.159905", "sz.159928", "sz.159929",
                  "sz.159930", "sz.159938", "sz.159939", "sh.512010",
                  "sh.512070", "sh.512120"]            # 6 + 14 = 20
U_BROAD15 = UNI6 + ["sh.510180", "sh.510310", "sh.510330", "sh.510510",
                    "sh.512990", "sz.159901", "sz.159902", "sz.159922",
                    "sz.160706"]                       # 6 + 9 = 15
U_SECXB25 = U_SEC20 + ["sh.510900", "sh.513030", "sh.513600", "sh.513660",
                       "sz.159920"]                    # 20 + 5 = 25 (disjoint)
assert len(set(U_EQ28)) == 28 and len(set(U_EQ35)) == 35
assert len(set(U_EQ43)) == 43 and len(set(U_SEC20)) == 20
assert len(set(U_BROAD15)) == 15 and len(set(U_SECXB25)) == 25
assert not (set(U_EQ43) & set(LEGS_EU))                # S2 disjointness, frozen
EU45_SYMS = sorted(set(U_EQ43) | set(LEGS_EU))         # data panel: 43 + 2 legs
assert len(EU45_SYMS) == 45, len(EU45_SYMS)
CFGS = {
    # anchor: R3-06 verbatim (legs 0.15+0.25, top3 x 0.20, 6m, UNI6)
    "EU-A0": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": UNI6, "universe_name": "UNI6",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
    # universe breadth (prereg sec 2 axis): A-share equity
    "EU-01": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ28, "universe_name": "EQ28",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
    "EU-02": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ35, "universe_name": "EQ35",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
    "EU-03": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ43, "universe_name": "EQ43",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
    # slot axis (EQ35)
    "EU-04": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ35, "universe_name": "EQ35",
                           "top_n": 4, "weight": 0.15, "lookback_m": 6}},
    "EU-05": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ35, "universe_name": "EQ35",
                           "top_n": 5, "weight": 0.12, "lookback_m": 6}},
    # lookback axis (EQ35)
    "EU-06": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ35, "universe_name": "EQ35",
                           "top_n": 3, "weight": 0.20, "lookback_m": 4}},
    "EU-07": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_EQ35, "universe_name": "EQ35",
                           "top_n": 3, "weight": 0.20, "lookback_m": 9}},
    # breadth variants (prereg sec 1 layered tables)
    "EU-08": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_SEC20, "universe_name": "SEC20",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
    "EU-09": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_BROAD15, "universe_name": "BROAD15",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
    "EU-10": {"stock": None, "legs": LEGS_EU,
              "rotation": {"universe": U_SECXB25, "universe_name": "SECXB25",
                           "top_n": 3, "weight": 0.20, "lookback_m": 6}},
}''')

# --- G. budget + identity pins -----------------------------------------------------
rep("BUDGET_S = 1200.0", "BUDGET_S = 2700.0   # 12 configs (EU adaptation)")
rep('''    "v2_metrics_rot05_anchor_source":
        (None, V2_RUN / "outputs/metrics_and_gates.json"),''',
     '''    "etf_daily_input": ("b7225d50523106f5", ETF_DAILY),
    "v3_metrics_r306_anchor_source":
        (None, V3_RUN / "outputs/metrics_and_gates.json"),
    "v3_r306_intents": (None, V3_RUN / "outputs/R3-06_intents.parquet"),
    "v3_r306_fills": (None, V3_RUN / "outputs/R3-06_fills.parquet"),
    "v3_r306_events": (None, V3_RUN / "outputs/R3-06_events.parquet"),
    "v3_r306_daily": (None, V3_RUN / "outputs/R3-06_daily_equity.parquet"),
    "v3_r306_clips": (None, V3_RUN / "outputs/R3-06_clips_final.parquet"),''')

# --- H. v3 metrics read (anchor reference) ------------------------------------------
rep('''v2_mg = json.loads((V2_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))''',
     '''v3_mg = json.loads((V3_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))''')

# --- I. EU45 panel build + 2025+ zero-row check (replaces `del etf_panel_full`) -----
rep("del etf_panel_full\n",
    'etf_panel45 = (etf_panel_full.filter(pl.col("symbol").is_in(EU45_SYMS))\n'
    '               .filter((pl.col("date") >= DEV_START)\n'
    '                       & (pl.col("date") <= DEV_END))\n'
    '               .sort("symbol", "date"))\n'
    '_n2025 = etf_panel_full.filter(pl.col("date") >= date(2025, 1, 1)).height\n'
    'if _n2025:\n'
    '    _fail(f"input parquet has {_n2025} rows on/after 2025-01-01 "\n'
    '          "(2025+ freeze breach)")\n'
    'log(f"  input parquet 2025+ rows: {_n2025} (freeze check PASS)")\n'
    'del etf_panel_full\n')

# --- J. B1(m) dev port-check block (replaces `del hist`; val-adapter port verbatim) --
rep("del hist\n",
    'if True:\n'
    '    bank_syms = sorted({s for t in sig_days\n'
    '                        for s in pools_at[t]["ranked"]})\n'
    '    bank = r16.PriceBank(hist, calendar_full, bank_syms)\n'
    '    b1_sim = r16.simulate_r16(\n'
    '        "B1-T200-40-rate_only-DEV", bank, calendar_full,\n'
    '        DEV_START, sig_days, pools_at, exposures, K=0, fractional=True,\n'
    '        fee_bands=r16.B1_FEE_SCHEDULE_RATE_ONLY)\n'
    '    _bm = r16.segment_metrics(b1_sim, DEV_START, DEV_END, None,\n'
    '                              fractional=True)\n'
    '    if abs(_bm["net_cagr"] - B1["b1m_net_cagr"]) > 1e-9:\n'
    '        _fail(f"B1m dev port-check mismatch net_cagr: {_bm[\'net_cagr\']}"\n'
    '              f" vs r16_metrics {B1[\'b1m_net_cagr\']}")\n'
    '    if abs(_bm["max_drawdown"] - B1["b1m_max_drawdown"]) > 1e-9:\n'
    '        _fail(f"B1m dev port-check mismatch max_drawdown: "\n'
    '              f"{_bm[\'max_drawdown\']} vs r16_metrics "\n'
    '              f"{B1[\'b1m_max_drawdown\']}")\n'
    '    _yr_ref = {int(k): v for k, v in\n'
    '               B1["b1m_net_return_by_year"].items()}\n'
    '    _yr_new = {int(k): v for k, v in\n'
    '               _bm["net_return_by_year"].items()}\n'
    '    if set(_yr_ref) != set(_yr_new) or any(\n'
    '            abs(_yr_ref[k] - _yr_new[k]) > 1e-9\n'
    '            for k in _yr_ref):\n'
    '        _fail(f"B1m dev port-check by-year mismatch: "\n'
    '              f"{_yr_new} vs {_yr_ref}")\n'
    '    # known dev values pin (EU task spec): net +0.60% / maxDD -39.82%\n'
    '    if round(_bm["net_cagr"], 4) != 0.0060 \\\n'
    '            or round(_bm["max_drawdown"], 4) != -0.3982:\n'
    '        _fail(f"B1m dev known-value pin FAILED: "\n'
    '              f"{_bm[\'net_cagr\']}, {_bm[\'max_drawdown\']}")\n'
    '    log(f"  B1m dev port-check: reproduces r16_metrics to 1e-9 PASS; "\n'
    '        f"known values +0.60%/-39.82% PIN PASS "\n'
    '        f"({_bm[\'net_cagr\']:+.6f}, {_bm[\'max_drawdown\']:.6f})")\n'
    'del hist\n')

# --- K. EU45 assertions + factor map + dividend events + meta (before symbol_meta) --
rep('# --- symbol_meta (explicit bands for ALL 9; assertion (i) basis) ------------',
    '# --- EU45 panel identity: 45-symbol data panel for EU-01..10 ---------------\n'
    'EU45_NULLS = int(etf_panel45.filter(pl.col("preclose").is_null()).height)\n'
    'log(f"  EU45 panel: {etf_panel45.height} dev rows, "\n'
    '    f"{etf_panel45[\'symbol\'].n_unique()} symbols; preclose nulls "\n'
    '    f"{EU45_NULLS}")\n'
    'if EU45_NULLS:\n'
    '    _fail("EU45 panel has preclose nulls")\n'
    'per45 = {r["symbol"]: r["len"] for r in\n'
    '         etf_panel45.group_by("symbol").len().iter_rows(named=True)}\n'
    'if set(per45) != set(EU45_SYMS):\n'
    '    _fail(f"EU45 panel member coverage broken: missing "\n'
    '          f"{sorted(set(EU45_SYMS) - set(per45))}")\n'
    'panel_days45 = set(dints(etf_panel45["date"]).tolist())\n'
    'miss45 = sorted(sse_days - panel_days45)\n'
    'extra45 = sorted(panel_days45 - sse_days)\n'
    'if miss45 or extra45:\n'
    '    _fail(f"EU45 calendar assertion FAILED: missing {miss45[:5]} "\n'
    '          f"extra {extra45[:5]}")\n'
    'log(f"  EU45 calendar union == SSE dev calendar "\n'
    '    f"({len(panel_days45)} days) PASS")\n'
    '\n'
    'factor_map45: dict[str, dict[int, float]] = {}\n'
    'factor_gaps45: dict[str, int] = {}\n'
    'for m in EU45_SYMS:\n'
    '    code = m.split(".")[1] + "." + m.split(".")[0].upper()\n'
    '    chunk = FUND_ADJ_DIR / f"chunk_{code}.csv"\n'
    '    if not chunk.exists():\n'
    '        _fail(f"fund_adj chunk missing for EU45 {m}: {chunk}")\n'
    '    f = pl.read_csv(chunk, schema_overrides={"trade_date": pl.Int64,\n'
    '                                             "adj_factor": pl.Float64})\n'
    '    f = f.filter((pl.col("trade_date") >= dint_of(DEV_START))\n'
    '                 & (pl.col("trade_date") <= dint_of(DEV_END)))\n'
    '    f = f.sort("trade_date")\n'
    '    factor_map45[m] = dict(zip(f["trade_date"].to_list(),\n'
    '                               f["adj_factor"].to_list()))\n'
    '    need = set(int(x) for x in dints(etf_panel45.filter(\n'
    '        pl.col("symbol") == m)["date"]))\n'
    '    factor_gaps45[m] = len(need - set(factor_map45[m]))\n'
    'if any(v for v in factor_gaps45.values()):\n'
    '    _fail(f"fund_adj does not cover every EU45 member-dev panel day: "\n'
    '          f"{factor_gaps45}")\n'
    'log(f"  EU45 factor coverage: zero gaps over {len(EU45_SYMS)} symbols PASS")\n'
    '\n'
    '# EU45 dividend events: v3 frozen extraction rule applied verbatim to 45\n'
    'det45 = det.filter(pl.col("symbol").is_in(EU45_SYMS)).filter(\n'
    '    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))\n'
    'div_rows45 = []\n'
    'for r in det45.iter_rows(named=True):\n'
    '    m = r["symbol"]\n'
    '    fmap = factor_map45[m]\n'
    '    dd = dint_of(r["date"])\n'
    '    sub = etf_panel45.filter(pl.col("symbol") == m)\n'
    '    prev_days = [x for x in dints(sub["date"]) if x < dd]\n'
    '    if not prev_days:\n'
    '        continue\n'
    '    d_prev = max(prev_days)\n'
    '    if dd not in fmap or d_prev not in fmap:\n'
    '        continue\n'
    '    ratio = fmap[dd] / fmap[d_prev]\n'
    '    if (r["preclose"] < r["prev_close"]) and (1.0 < ratio <= 1.06):\n'
    '        div_rows45.append({"symbol": m, "date": r["date"],\n'
    '                           "div_per_share": float(r["prev_close"])\n'
    '                                            - float(r["preclose"]),\n'
    '                           "factor_ratio": ratio})\n'
    'dividend_events45 = pl.DataFrame(div_rows45, schema={\n'
    '    "symbol": pl.String, "date": pl.Date, "div_per_share": pl.Float64,\n'
    '    "factor_ratio": pl.Float64}).drop("factor_ratio").sort("symbol", "date")\n'
    'counts45 = Counter(dividend_events45["symbol"].to_list())\n'
    'EU45_NEW_DIV = {s: c for s, c in counts45.items() if s not in MEMBERS}\n'
    'log(f"  EU45 dividend events: {dividend_events45.height} total; "\n'
    '    f"new-member counts {EU45_NEW_DIV}")\n'
    '_eu_anchor_subset = dividend_events45.filter(\n'
    '    pl.col("symbol").is_in(MEMBERS))\n'
    'if not _eu_anchor_subset.equals(dividend_events):\n'
    '    _fail("EU45 dividend subset(MEMBERS) != frozen anchor 18 events")\n'
    '\n'
    'SYMBOL_META45 = {m: {"asset_class": "etf", "band": 0.10, "t_plus": 0}\n'
    '                 for m in EU45_SYMS}\n'
    'assert all(v["band"] == 0.10 and v["t_plus"] == 0\n'
    '           for v in SYMBOL_META45.values())\n'
    '\n'
    '# --- symbol_meta (explicit bands for ALL 9; assertion (i) basis) ------------')

# --- L. etf_only_frames45 + 45-symbol ts/bars ---------------------------------------
rep('''def etf_only_frames() -> dict:
    return {"daily": etf_panel_ts.select("symbol", "date", "open", "high",
                                         "low", "close", "tradestatus",
                                         "preclose").sort("symbol", "date"),
            "half": etf_bars, "limits": EMPTY_LIMITS,
            "splits": EMPTY_SPLITS, "dividends": EMPTY_DIVS,
            "instruments": EMPTY_INSTR}''',
     '''def etf_only_frames() -> dict:
    return {"daily": etf_panel_ts.select("symbol", "date", "open", "high",
                                         "low", "close", "tradestatus",
                                         "preclose").sort("symbol", "date"),
            "half": etf_bars, "limits": EMPTY_LIMITS,
            "splits": EMPTY_SPLITS, "dividends": EMPTY_DIVS,
            "instruments": EMPTY_INSTR}


def etf_only_frames45() -> dict:
    return {"daily": etf_panel45_ts.select("symbol", "date", "open", "high",
                                           "low", "close", "tradestatus",
                                           "preclose").sort("symbol", "date"),
            "half": etf_bars45, "limits": EMPTY_LIMITS,
            "splits": EMPTY_SPLITS, "dividends": EMPTY_DIVS,
            "instruments": EMPTY_INSTR}''')
rep("etf_bars = etf_pm_bars(etf_panel_ts)\n",
    "etf_bars = etf_pm_bars(etf_panel_ts)\n"
    "etf_panel45_ts = etf_panel45.with_columns(\n"
    "    pl.lit(1.0, dtype=etf_ts_dtype).alias(\"tradestatus\"))\n"
    "etf_bars45 = etf_pm_bars(etf_panel45_ts)\n")

# --- M. adj_close extension to EU45 (before month_shift def) -------------------------
rep("def month_shift(d: date, k: int) -> date | None:",
    "for m in EU45_SYMS:\n"
    "    if m in adj_close:\n"
    "        continue\n"
    "    fmap = factor_map45[m]\n"
    "    sub = etf_panel45.filter(pl.col(\"symbol\") == m)\n"
    "    ac = {}\n"
    "    rows = sub.select(\n"
    "        (pl.col(\"date\").dt.year().cast(pl.Int64) * 10_000\n"
    "         + pl.col(\"date\").dt.month().cast(pl.Int64) * 100\n"
    "         + pl.col(\"date\").dt.day().cast(pl.Int64)).alias(\"dint\"),\n"
    "        \"close\")\n"
    "    for r in rows.iter_rows(named=True):\n"
    "        ac[int(r[\"dint\"])] = float(r[\"close\"]) * fmap[int(r[\"dint\"])]\n"
    "    adj_close[m] = ac\n"
    "log(f\"  adj_close extended to EU45 ({len(adj_close)} symbols)\")\n"
    "\n"
    "\n"
    "def month_shift(d: date, k: int) -> date | None:")

# --- N. INPUTS else-branch: anchor vs EU45 frames ------------------------------------
rep('''    else:
        INPUTS[cid] = {**etf_only_frames(), "meta": SYMBOL_META,
                       "events": dividend_events, "mode": "etf_only"}''',
     '''    else:
        if cid == "EU-A0":
            _fr, _mt, _dv = etf_only_frames(), SYMBOL_META, dividend_events
        else:
            assert set(CFGS[cid]["rotation"]["universe"]) <= set(EU45_SYMS), cid
            _fr, _mt, _dv = (etf_only_frames45(), SYMBOL_META45,
                             dividend_events45)
        INPUTS[cid] = {**_fr, "meta": _mt, "events": _dv,
                       "mode": "etf_only"}''')

# --- O0. anchor metric reference line ------------------------------------------------
rep('v2_rot05 = v2_mg["metrics"]["ROT-05"]',
    'v3_r306 = v3_mg["metrics"]["R3-06"]')

# --- O. section-10 anchor block: EU-A0 vs v3 R3-06 (fail-closed engine wrap) ---------
rep('''# === 10. R3-A0 regression anchor vs v2 ROT-05 ==============================
log("== 10. R3-A0 regression anchor vs v2 ROT-05 ==")''',
     '''# === 10. EU-A0 regression anchor vs v3 R3-06 ===============================
log("== 10. EU-A0 regression anchor vs v3 R3-06 ==")''')
rep('''# R3-A0 regression: 5-frame .equals vs the v2 run's ROT-05 outputs +
# net_cagr must equal the v2 metric (R3-A0 is NOT re-adjudicated)
results["R3-A0"] = run_one("R3-A0")
r0 = results["R3-A0"]["res"]''',
     '''# EU-A0 regression: 5-frame .equals vs the v3 run's R3-06 outputs +
# net_cagr must equal the v3 metric (EU-A0 is NOT re-adjudicated);
# engine v1.3 fail-closed guards (e.g. dividend misclassification) stop
# the round -- no data repair (EU prereg sec 4-3)
try:
    results["EU-A0"] = run_one("EU-A0")
except Exception as _e:
    _fail(f"EU-A0: engine raised {_e.__class__.__name__}: {_e} "
          "(engine v1.3 fail-closed guard; no data repair)")
r0 = results["EU-A0"]["res"]''')
rep('''ref = {name: pl.read_parquet(V2_RUN / "outputs" / fn) for name, fn in
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
log("  R3-A0 regression anchor PASS (== v2 ROT-05, 5/5 frames)")''',
     '''ref = {name: pl.read_parquet(V3_RUN / "outputs" / fn) for name, fn in
       (("intents", "R3-06_intents.parquet"),
        ("fills", "R3-06_fills.parquet"), ("events", "R3-06_events.parquet"),
        ("daily", "R3-06_daily_equity.parquet"),
        ("clips_final", "R3-06_clips_final.parquet"))}
regression = {}
for name, mine in (("intents", FRAMES["EU-A0"]), ("fills", r0.fills),
                   ("events", r0.events), ("daily", r0.daily),
                   ("clips_final", r0.clips_final)):
    same = mine.equals(ref[name])
    regression[name] = same
    log(f"  EU-A0 {name}.equals(v3 R3-06 {name}) = {same} "
        f"(mine {mine.height} rows / ref {ref[name].height} rows)")
regression["net_cagr_matches_v3_metrics"] = \\
    abs(_cagr0 - v3_r306["net_cagr"]) <= 1e-12
log(f"  EU-A0 net_cagr {_cagr0:.10f} vs v3 R3-06 "
    f"{v3_r306['net_cagr']:.10f} -> "
    f"{regression['net_cagr_matches_v3_metrics']}")
if not all(regression.values()):
    _fail(f"EU-A0 REGRESSION FAILURE: {regression} -- abort the whole round "
          "with zero conclusions per EU prereg sec 4-1 (EU-A0 != v3 R3-06)")
log("  EU-A0 regression anchor PASS (== v3 R3-06, 5/5 frames .equals)")''')

# --- P. remaining-configs loop with fail-closed engine wrap --------------------------
rep('''for cid in [c for c in CONFIG_IDS if c != "R3-A0" and c in FRAMES]:
    results[cid] = run_one(cid)
check_budget("all engine runs")''',
     '''for cid in [c for c in CONFIG_IDS if c != "EU-A0" and c in FRAMES]:
    try:
        results[cid] = run_one(cid)
    except Exception as _e:
        _fail(f"{cid}: engine raised {_e.__class__.__name__}: {_e} "
              "(engine v1.3 fail-closed guard; no data repair)")
check_budget("all engine runs")''')

# --- Q. rotation_fill_profile: per-config universe ------------------------------------
rep('''    res = results[cid]["res"]
    f = res.fills.filter(pl.col("symbol").is_in(UNI6)) \\
        if res.fills.height else res.fills''',
     '''    res = results[cid]["res"]
    _uni = CFGS[cid]["rotation"]["universe"] if CFGS[cid]["rotation"] else UNI6
    f = res.fills.filter(pl.col("symbol").is_in(_uni)) \\
        if res.fills.height else res.fills''')
rep('"caliber": "rotation-slot displacement vs R3-A0 (v3 prereg sec 4-2): "\n'
    '                   "UNI6-symbol fills / emitted entries-exits / "',
    '"caliber": "rotation-slot displacement vs EU-A0 (v3 prereg sec 4-2, "\n'
    '                   "universe = each config\'s own rotation universe): "\n'
    '                   "config-universe fills / emitted entries-exits / "')

# --- R. CLOSE_ARR over EU45 ------------------------------------------------------------
rep("for sym in set(cfg_syms_stock) | set(PANEL_SYMS):\n"
    "    CLOSE_ARR[sym] = close_le_map(sym)",
    "for sym in set(cfg_syms_stock) | set(PANEL_SYMS) | set(EU45_SYMS):\n"
    "    CLOSE_ARR[sym] = close_le_map(sym)")
rep('''    if sym in PANEL_SYMS:
        rows = etf_panel.filter(pl.col("symbol") == sym)
    else:''',
     '''    if sym in EU45_SYMS:
        rows = etf_panel45.filter(pl.col("symbol") == sym)
    elif sym in PANEL_SYMS:
        rows = etf_panel.filter(pl.col("symbol") == sym)
    else:''')

# --- S. roster eligibility line ----------------------------------------------------------
rep('''    g["failed_gates"] = sorted(k for k in GATE_KEYS if not g[k])
    g["dev_pass"] = not g["failed_gates"]
    g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"''',
     '''    g["failed_gates"] = sorted(k for k in GATE_KEYS if not g[k])
    g["dev_pass"] = not g["failed_gates"]
    g["roster_eligible"] = bool(g["dev_pass"]
                                and m["goal_dev_net_cagr_ge_10pct"])
    g["verdict"] = ("roster_eligible" if g["roster_eligible"]
                    else "dev_pass" if g["dev_pass"] else "eliminated")''')

# --- T. stop-note -> EU readout ------------------------------------------------------------
rep('''_goal_hit = [cid for cid in gates
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
                  "consumed")''',
     '''_roster = sorted(cid for cid in gates
                 if gates[cid]["dev"]["roster_eligible"])
_STOP_NOTE = (
    "expanded-universe exploration round v1 (EU prereg sec 0/5): all 12 "
    "config results reported at once, no mid-run selection, no champion "
    "change, R3-05/R3-06 in-library status unchanged; roster eligibility "
    "(second-pass protocol = dev 8 gates AND net CAGR >= 10%) -> "
    + (", ".join(_roster) if _roster else "none")
    + f"; {n_pass}/{len(gates)} pass all 8 dev gates; ALL results "
      "exploration-grade; trials +10 (252->262, anchor not counted); "
      "val not consumed")''')

# --- U1. bond-ladder disclosure -> EU config matrix -----------------------------------------
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
                    "advantage_years": gates[cid]["dev"]["advantage_years"],
                    "failed_gates": gates[cid]["dev"]["failed_gates"],
                    "rotation_top_n": (CFGS[cid]["rotation"]["top_n"]
                                       if CFGS[cid]["rotation"] else None)})
disclosures["bond_ladder_monotonicity"] = {
    "ladder": _ladder,
    "note": "bond weight 0.25 -> 0 trajectory of net CAGR / maxDD; "
            "non-monotonicity means structural sensitivity, not linear "
            "opportunity cost (v3 prereg sec 4-3); R3-A0 is the 0.25 point"}''',
     '''# --- EU disclosure: frozen config matrix (prereg sec 2) --------------------
_matrix = []
for cid in CONFIG_IDS:
    if cid not in metrics:
        continue
    m = metrics[cid]
    r = CFGS[cid]["rotation"]
    _matrix.append({"id": cid,
                    "universe_name": r["universe_name"],
                    "n_universe": len(r["universe"]),
                    "top_n": r["top_n"], "slot_weight": r["weight"],
                    "lookback_m": r["lookback_m"],
                    "net_cagr": m["net_cagr"],
                    "max_drawdown": m["max_drawdown"],
                    "excess_vs_b1m": m["excess_vs_b1m"],
                    "advantage_years": gates[cid]["dev"]["advantage_years"],
                    "failed_gates": gates[cid]["dev"]["failed_gates"],
                    "roster_eligible": gates[cid]["dev"]["roster_eligible"]})
disclosures["eu_config_matrix"] = {
    "matrix": _matrix,
    "note": "EU prereg sec 2 frozen matrix; UNI6 members are contained in "
            "every exploration universe (extension not replacement); legs "
            "constant sh.511010@0.15 + sh.518880@0.25; every single-slot "
            "weight <= 25% (S-rob-1 lesson); EU-A0 is the anchor, not a trial"}''')

# --- U2. EU45 dividend disclosure (before disclosures budget check) --------------------------
rep('check_budget("disclosures")',
    'disclosures["eu45_dividend_events"] = {\n'
    '    "rule": "v3 frozen dividend extraction rule applied verbatim to the "\n'
    '            "45-symbol EU45 panel (dev window)",\n'
    '    "n_events_dev": dividend_events45.height,\n'
    '    "counts_by_symbol": dict(\n'
    '        Counter(dividend_events45["symbol"].to_list())),\n'
    '    "new_member_counts_vs_v3_panel": EU45_NEW_DIV,\n'
    '    "members_subset_equals_anchor_18": True,\n'
    '    "engine_guard": "engine v1.3 anti-misclassification guard armed "\n'
    '                    "(dividend implied return > 10% -> hard error; "\n'
    '                    "fail-closed, no data repair)",\n'
    '    "events": [{"symbol": r["symbol"], "date": str(r["date"]),\n'
    '                "div_per_share": r["div_per_share"]}\n'
    '               for r in dividend_events45.iter_rows(named=True)]}\n'
    'check_budget("disclosures")')

# --- V. outputs: dividend_events45.csv + anchor parquet byte comparison ----------------------
rep('''(out_dir / "dividend_events.csv").write_text(
    dividend_events.write_csv(), encoding="utf-8")''',
     '''(out_dir / "dividend_events.csv").write_text(
    dividend_events.write_csv(), encoding="utf-8")
(out_dir / "dividend_events45.csv").write_text(
    dividend_events45.write_csv(), encoding="utf-8")
_byte_eq = {fn: (sha256_file(out_dir / f"EU-A0_{fn}")
                 == sha256_file(V3_RUN / "outputs" / f"R3-06_{fn}"))
            for fn in ("intents.parquet", "fills.parquet", "events.parquet",
                       "daily_equity.parquet", "clips_final.parquet")}
regression["parquet_bytes_equal_vs_v3"] = all(_byte_eq.values())
regression["parquet_bytes_detail"] = _byte_eq
log(f"  EU-A0 parquet byte-equality vs v3 R3-06 files: "
    f"{regression['parquet_bytes_equal_vs_v3']} {_byte_eq}")''')

# --- W1. metrics_and_gates anchor note --------------------------------------------------------
rep('''    "r3a0_regression_anchor": {**regression,
                               "note": "polars .equals() vs v2 run ROT-05 "
                                       "outputs (intents/fills/events/daily/"
                                       "clips_final) + net_cagr match; "
                                       "mismatch = abort (did not trigger); "
                                       "R3-A0 is NOT re-adjudicated"},''',
     '''    "eu_a0_regression_anchor": {**regression,
                                "note": "polars .equals() vs the v3 run's "
                                        "(20260919T110500-hybrid-v3-r3ld) "
                                        "R3-06 outputs (intents/fills/events/"
                                        "daily/clips_final) + net_cagr 1e-12 "
                                        "match + parquet byte comparison "
                                        "(bytes_equal_vs_v3); mismatch = "
                                        "abort with zero conclusions; EU-A0 "
                                        "is NOT re-adjudicated"},''')
rep('''        "ii_preclose_no_nulls": f"PASS ({ASSERT_II_NULLS} nulls, "
                                "9-symbol dev panel)",''',
     '''        "ii_preclose_no_nulls": f"PASS ({ASSERT_II_NULLS} nulls, 9-symbol "
                                f"anchor dev panel; EU45 panel nulls "
                                f"{EU45_NULLS})",''')

# --- W2. manifest panel inventory + input parquet identity ------------------------------------
rep('    "dividend_events_built": dividend_events.height,',
    '    "dividend_events_built": dividend_events.height,\n'
    '    "eu45_panel_inventory": {\n'
    '        "symbols": EU45_SYMS,\n'
    '        "n": len(EU45_SYMS),\n'
    '        "anchor_panel_9": list(PANEL_SYMS),\n'
    '        "dividend_events45_dev": dividend_events45.height,\n'
    '        "new_member_dividend_counts": EU45_NEW_DIV},\n'
    '    "input_parquet": {"path": str(ETF_DAILY),\n'
    '                      "sha256_16": pins["etf_daily_input"]["sha256"][:16],\n'
    '                      "expected_prefix": "b7225d50523106f5",\n'
    '                      "rows_2025_plus": 0},')

# --- X. no_rejurisdiction note -----------------------------------------------------------------
rep('''    "no_rejurisdiction": "v2-judged configs (H2-01/03/04, ROT-05) are NOT "
                         "re-run or re-judged in v3; R3-A0 is a regression "
                         "anchor only (v3 prereg sec 3)",''',
     '''    "no_rejurisdiction": "v3-judged configs (R3-05/R3-06) are NOT re-run or "
                         "re-judged here; EU-A0 is a byte-level regression "
                         "anchor only (EU prereg sec 0); roster eligibility "
                         "under the second-pass protocol is NOT a champion "
                         "claim",''')

# --- Y1. report title / anchor bullet ------------------------------------------------------------
rep('rep = ["# 混合族 v3 判定（exp-20260919-hybrid-family-v3，降债阶梯）", "",',
    'rep = ["# 扩展宇宙探索轮 v1 判定（exp-20260919-expanded-universe-v1，'
    'EU-A0 锚 + EU-01..10）", "",')
rep('''       f"- R3-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v2 ROT-05 输出逐帧 polars `.equals()` 全部一致（5/5 PASS），"
       f"判定链有效；R3-A0 判定以 v2 为准，不重判。",''',
     '''       f"- EU-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v3 run（20260919T110500-hybrid-v3-r3ld）R3-06 产物逐帧 polars "
       f"`.equals()` 全部一致（5/5 PASS）+ net_cagr 1e-12 一致 + parquet "
       f"字节比对（见 manifest eu_a0_regression）；锚失败即中止整轮零结论；"
       f"锚不重判。",''')

# --- Y2. matrix + EU45 dividend rendering replaces ladder rendering -------------------------------
rep('''if "bond_ladder_monotonicity" in disclosures:
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
            "（货基收益）略悲观，保守方向如实呈现。"]''',
     '''if "eu_config_matrix" in disclosures:
    rep += ["", "### 配置矩阵（EU 预登记 §2 冻结）", "",
            "| 配置 | 宇宙 | n | top_n×权重 | 回看 | 净CAGR | maxDD | 超额 "
            "| 优势年 | 入册资格 | 失败门 |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in disclosures["eu_config_matrix"]["matrix"]:
        rep.append(
            f"| {e['id']} | {e['universe_name']} | {e['n_universe']} "
            f"| {e['top_n']}×{e['slot_weight']:.2f} | {e['lookback_m']}m "
            f"| {e['net_cagr']*100:+.2f}% | {e['max_drawdown']*100:.2f}% "
            f"| {e['excess_vs_b1m']*100:+.2f}pp | {e['advantage_years']}/6 "
            f"| {'Y' if e['roster_eligible'] else 'N'} "
            f"| {', '.join(e['failed_gates']) or '-'} |")
    rep += ["- 入册资格 = dev 八门全过 且 净年化 ≥10%（二次过手协议）；"
            "入册 ≠ 冠军，Phase B 前不改 R3-05/R3-06 在库地位。",
            "- UNI6 成员包含于所有探索宇宙（扩展而非替换）；腿恒 "
            "sh.511010@15% + sh.518880@25%；单槽权重 ≤25%。",
            "- 引擎现金零收益（无货基收益建模），相对现实略悲观（保守方向）。"]
if "eu45_dividend_events" in disclosures:
    _dd = disclosures["eu45_dividend_events"]
    rep += ["", "### EU45 面板 dev 分红事件披露（EU 预登记 §4-3）", "",
            f"- 45 符号面板共 {_dd['n_events_dev']} 个 dev 分红事件"
            f"（其中锚面板 9 符号的 18 事件为其子集，已逐帧断言一致）。",
            f"- 相对 v3 面板的新增成员事件计数："
            f"{json.dumps(_dd['new_member_counts_vs_v3_panel'], ensure_ascii=False)}。",
            "- 引擎 v1.3 防误分类护栏已武装（分红隐含收益率 >10% 硬报错，"
            "fail-closed，不修数据绕过）；事件明细见 "
            "outputs/dividend_events45.csv。"]''')

# --- Y3. section-3 heading -------------------------------------------------------------------------
rep('        "## 三、R3-A0 回归锚（= v2 ROT-05 复刻）", "",',
    '        "## 三、EU-A0 回归锚（= v3 R3-06 复刻）", "",')

# --- Y4. trial accounting (report) -------------------------------------------------------------------
rep('''        f"- 试验计账：本族判定计 7 项（7 配置族）；谱系 v1 205→214、"
        "v2 214→222，v3 判定后 222→229（如台账有异以台账为准）。",''',
     '''        f"- 试验计账：本轮 +10 探索试验（EU 预登记 §2/§5：252→262），"
        "锚 EU-A0 不计试验；谱系 v1 205→214、v2 214→222、v3 222→229、"
        "val 229→241、rob 241→252（如台账有异以台账为准）。",''')

# --- Y5. key-findings section 五 ------------------------------------------------------------------------
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
        "- **本轮性质**：扩展宇宙探索轮 v1（二次过手协议 Phase A 线 1）；"
        "全部 dev 窗（2015–2020）；全部结果 exploration-grade；不产生冠军"
        "声明、不写可实盘、不改 R3-05/R3-06 在库地位；试验 252→262。",
        "- **锚口径**：EU-A0 = v3 R3-06 逐字（含 v3 原面板与未使用的 "
        "sz.159934）；五帧产物与 v3 run R3-06 `.equals()` 逐帧一致 + "
        "net_cagr 1e-12 + parquet 字节比对；失败即中止整轮零结论。",
        "- **corporate_actions 不传**：预登记 §1 排除后各宇宙 dev 窗零拆分"
        "事件（筛查事件表核验）；dividend_events 沿 v3 抽取规则应用于 "
        "45 符号面板；引擎 v1.3 防误分类护栏 fail-closed。",
        "- **B1(m) dev 基准**：现算沿用已验证端口（r16.simulate_r16 "
        "fractional、rate-only bands、T200-40），对 R16 metrics 1e-9 校验，"
        "已知 dev 值（净年化 +0.60%/maxDD −39.82%）pin 通过。",
        "- **门 8 v3 口径逐字**：最终交付 ≥99% + 期末滞留=0 硬断言；"
        "8v2 与 R16 原口径仅作对照列。",
        "- **货币 ETF 语义（预登记 §4-4）**：货币近零动量在全市场弱势时"
        "占据 top 槽 = EU-03 防御停靠假设本身的检验；其分红/净值累计口径"
        "经因子调整后与其他成员同规则。",
        "- **指数重复风险（预登记 §6-3）**：U-EQ28/35/43 内同指数多基金，"
        "动量排名并列时同信号多槽集中；U-SECXB25 为对照设计。",
        "- **ETF 数据质量**：锚 9 符号面板 preclose 零空值、因子全覆盖、"
        "分红 18 事件全落带；EU45 面板断言（preclose 空值/日历并集/因子"
        "覆盖）全部通过（计数与明细见披露与 outputs/）。"]''')

# --- Y6. report target file ------------------------------------------------------------------------------
rep('(RUN_DIR / "report.md").write_text("\\n".join(rep), encoding="utf-8")',
    '(RUN_DIR / "delivery_report.md").write_text("\\n".join(rep),\n'
    '                                               encoding="utf-8")')

# --- Z1. experiment ids ------------------------------------------------------------------------------------
rep('"experiment_id": "exp-20260919-hybrid-family-v2",',
    '"experiment_id": "exp-20260919-expanded-universe-v1",')
rep('    "experiment_id": "exp-20260919-hybrid-family-v3",\n'
    '    "engine_sha256_16"',
    '    "experiment_id": "exp-20260919-expanded-universe-v1",\n'
    '    "engine_sha256_16"')
rep('    "experiment_id": "exp-20260919-hybrid-family-v3",\n'
    '    "status"',
    '    "experiment_id": "exp-20260919-expanded-universe-v1",\n'
    '    "status"')

# --- Z2. manifest engine label / command / trial accounting / regression key --------------------------------
rep('               "version": "v1.2 (frozen, unchanged from v1; v2 prereg sec 5)"},',
    '               "version": "v1.3 (sha256 pin 84a2443a...082c; EU '
    'prereg sec 0)"},')
rep('                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_hybrid_v3.py"],',
    '                f"artifacts/runs/{RUN_DIR.name}/scripts/'
    'runner_exp_universe.py"],')
rep('''    "trial_accounting": {"this_round": "1 family (7 configs, all run)",
                         "cumulative_lineage": "v1 205->214; v2 214->222; "
                                               "v3 verdict -> 222->229 "
                                               "(config json trial_accounting)"},''',
     '''    "trial_accounting": {"this_round":
                             "+10 exploration trials (12 configs run; "
                             "anchor EU-A0 not counted per EU prereg sec 2)",
                         "cumulative_lineage": "per EU prereg sec 2/5: "
                                               "252 -> 262"},''')
rep('    "r3a0_regression": regression,',
    '    "eu_a0_regression": regression,')

# --- final sweep: remaining R3-A0 identifier refs (7 expected) --------------------------------
_n_left = s.count("R3-A0")
# expected residuals: base_profile + cid== loop + comp_txt + report engine
# stats x3 = 6 benign identifier usages
assert _n_left == 6, f"expected 6 remaining R3-A0 refs before sweep, got {_n_left}"
s = s.replace("R3-A0", "EU-A0")
reps.append(("R3-A0 -> EU-A0 (final sweep: section-11 skip, base_profile, "
             "comp loop, report engine-stats x3)", _n_left))

# --- residual sanity -----------------------------------------------------------------------------
for bad in ("V2_RUN", "v2_mg", "v2_rot05", "R3-A0", "bond_ladder"):
    assert bad not in s, f"residual {bad!r} still present"
# V2_PREREG_MD / v1 prereg paths are legitimate lineage pins -- kept.
# the _fail manifest experiment_id must be the EU id:
assert '"experiment_id": "exp-20260919-expanded-universe-v1",' in s
assert '"experiment_id": "exp-20260919-hybrid-family' not in s
assert "runner_exp_universe.py" in s
assert s.count("EU45_SYMS") >= 10
assert "corporate_actions" not in s.replace("corporate_actions NOT passed", "") \
    or True   # corporate_actions must NOT be passed to the engine call
_call = s[s.index("res = run_band_backtest_intents("):s.index("initial_cash")]
assert "corporate_actions" not in _call, "engine call must NOT pass corporate_actions"

io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print(f"adapted OK: {len(reps)} replacement groups, {n0} -> {len(s)} chars")
for name, c in reps:
    print(f"  x{c}  {name}")
