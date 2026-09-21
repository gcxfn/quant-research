# -*- coding: utf-8 -*-
"""Stage-2 adapter (exp-20260920-val-batch, V1 mixed family).

SRC = scripts/runner_hybrid_val_tl30.py   (TL-30 val runner, sha 26409c6b...,
      itself reproduced byte-for-byte by adapt_stage1_driver.py)
DST = scripts/runner_val_batch_hybrid.py  (this run's runner)

Every replacement is asserted (exactly one hit, or an exact expected count) and
the script aborts otherwise -- no silent partial adaptation.  Blocks are sliced
out of the source by exact anchor lines, so the old text can never be mistyped.

Incremental changes over TL-30 (prereg docs/research/exp-20260920-val-batch-
prereg.md, mixed-family section):
  * engine pin -> v1.4.1 a01cb29c (non-zones path; equivalence carried by the
    dev anchors: R3-A0 == v2 ROT-05, R3-01..04 == v3 outputs, H2-01/03/04 ==
    v2 outputs, C05 signal-layer port == R16 artifacts + metrics);
  * 7 judged configs (R3-01..04 + H2-01/03/04) + dev-only R3-A0 anchor;
  * H2 stock leg = rebuilt R16 signal-layer port (window-local cold start) with
    a dev-window reproduction gate against the R16 leg_log / membership_events
    artifacts and the R16 metrics (1e-9);
  * dev phase writes outputs_dev/ + tmp/port_status.json; the val phase refuses
    to consume a config whose dev port did not reproduce byte-for-byte;
  * val B1(m) asserted bit-for-bit against TL-30's published values;
  * val gates taken from r16.evaluate_val_gates verbatim and cross-checked
    against the inline caliber;
  * 2025+ zero-touch assertions before any output write.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent
SRC = HERE / "runner_hybrid_val_tl30.py"
DST = HERE / "runner_val_batch_hybrid.py"
SRC_SHA_EXPECT = "26409c6bc18c350bd9547615d3b9bd3ecbdb63d3eda47898cb1458c4d462afaa"

s = io.open(SRC, encoding="utf-8").read()
got = hashlib.sha256(s.encode("utf-8")).hexdigest()
assert got == SRC_SHA_EXPECT, f"stage-1 source sha mismatch: {got}"
LINE = s.split("\n")
n0 = len(s)
reps: list[tuple[str, int]] = []


def rep(old: str, new: str, count: int = 1) -> None:
    global s
    c = s.count(old)
    assert c == count, f"expected {count} hit(s), got {c}: {old[:90]!r}"
    s = s.replace(old, new)
    reps.append((old.splitlines()[0][:58], c))


def blk(first: str, last: str) -> str:
    """Slice from the unique line `first` to the next line equal to `last`."""
    idx = [k for k, l in enumerate(LINE) if l == first]
    assert len(idx) == 1, f"anchor {first!r} hits {len(idx)}"
    i = idx[0]
    j = next(k for k in range(i, len(LINE)) if LINE[k] == last)
    b = "\n".join(LINE[i:j + 1])
    assert s.count(b) == 1, f"block not unique in source: {first!r}"
    return b


# ---------------------------------------------------------------- R1 window --
rep(blk('_WINDOW = os.environ.get("VAL_WINDOW", "dev")',
        '    DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)'),
    blk('_WINDOW = os.environ.get("VAL_WINDOW", "dev")',
        '    DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)')
    + '\n_SUF = "_dev" if _WINDOW == "dev" else ""')

# ------------------------------------------------------- R2 output suffixes --
rep('LOG_PATH = RUN_DIR / "logs" / "runner.log"',
    'LOG_PATH = RUN_DIR / "logs" / ("runner%s.log" % _SUF)')
rep('out_dir = RUN_DIR / "outputs"',
    'out_dir = RUN_DIR / ("outputs%s" % _SUF)')

# ------------------------------------------------------------- R3 docstring --
rep(blk("Deterministic; no RNG.  Spec seams are NOT silently resolved: they are",
        '"""'),
    '''Deterministic; no RNG.  Spec seams are NOT silently resolved: they are
recorded and reported.

exp-20260920-val-batch V1 (mixed family) -- derived from the TL-30 val runner
(20260919T151630-hybrid-val-v1p3/scripts/runner_hybrid_val.py, sha 26409c6b)
by an asserted replacement script (scripts/adapt_stage2_valbatch.py; stage 1
reproduced the TL-30 runner byte-for-byte from the pinned v3 mother).  Engine
pin moved to v1.4.1 a01cb29c; the 7-config val batch (R3-01..04 + H2-01/03/04)
and the R16 signal-layer stock port are added.  Prereg:
docs/research/exp-20260920-val-batch-prereg.md (mixed-family section).
Budget 1200 s wall per phase (dev anchor phase / val consumption phase).
"""''')

# ------------------------------------------------------------ R4 constants ---
rep('V2_RUN = ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b"',
    'V2_RUN = ROOT / "artifacts/runs/20260919T063022-hybrid-v2-2k5b"\n'
    'V3_RUN = ROOT / "artifacts/runs/20260919T110500-hybrid-v3-r3ld"\n'
    'V3_METRICS = V3_RUN / "outputs/metrics_and_gates.json"\n'
    'TL30_RUN = ROOT / "artifacts/runs/20260919T151630-hybrid-val-v1p3"\n'
    'TL30_METRICS = TL30_RUN / "outputs/metrics_and_gates.json"\n'
    'VAL_BATCH_PREREG = ROOT / "docs/research/exp-20260920-val-batch-prereg.md"')

# ------------------------------------------------------------ R5 engine pin --
rep(blk('ENGINE_SHA_EXPECT_FULL = ("84a2443ac28fe1b87e4a18f988fd38cc67cf706d5778e"',
        '                          "262f11465147234082c")'),
    "# v1.4.1 pin (2026-09-20).  The zones path is never invoked here; the\n"
    "# non-zones path is byte-identical to v1.3 84a2443a...  The equivalence is\n"
    "# carried by this run's dev anchors (prereg sec 6): R3-A0 == v2 ROT-05,\n"
    "# R3-01..04 == v3 outputs, H2-01/03/04 == v2 outputs, C05 port == R16.\n"
    'ENGINE_SHA_EXPECT_FULL = ("a01cb29ce4cf214814dd51679295f70ac780dc5dffb2"\n'
    '                          "70ea1f0a466b0675abf3")')

# ------------------------------------------------------------ R6 CONFIG_IDS --
rep('CONFIG_IDS = ["R3-A0", "R3-05", "R3-06"]',
    '''# 2026-09-20 val batch (exp-20260920-val-batch, mixed-family section): the 7
# judged configs.  R3-A0 is dev-only: it is the runner-chain regression anchor
# and was already consumed on val by TL-30 (prereg sec 1), so it is not run or
# re-judged on val.
JUDGED_IDS = ["R3-01", "R3-02", "R3-03", "R3-04",
              "H2-01", "H2-03", "H2-04"]
CONFIG_IDS = (["R3-A0"] + JUDGED_IDS) if _WINDOW == "dev" else list(JUDGED_IDS)
# per-config port blocks (dev reproduction failure -> that config is not
# consumed on val; prereg sec 3/6)
PORT_BLOCKED: dict = {}
C05_PORT_PASS = None''')

# ---------------------------------------------------------------- R7 CFGS ----
rep(blk('CFGS = {', '}'),
    '''CFGS = {
    "R3-A0": {"stock": False, "legs": {"sh.511010": 0.25,
                                       "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},   # = ROT-05 verbatim (anchor)
    "R3-01": {"stock": False, "legs": {"sh.511010": 0.20,
                                       "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-02": {"stock": False, "legs": {"sh.511010": 0.15,
                                       "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-03": {"stock": False, "legs": {"sh.511010": 0.10,
                                       "sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "R3-04": {"stock": False, "legs": {"sh.518880": 0.25},
              "rotation": {"universe": UNI6, "top_n": 2, "weight": 0.25,
                           "lookback_m": 6}},
    "H2-01": {"stock": True, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.25},
              "rotation": None},          # v2 prereg sec 2 (park 50%)
    "H2-03": {"stock": True, "legs": {"sh.511010": 0.20, "sh.518880": 0.20,
                                      "sz.159934": 0.20},
              "rotation": None},          # v2 prereg sec 2 (park 60%)
    "H2-04": {"stock": True, "legs": {"sh.511010": 0.25,
                                      "sh.518880": 0.20},
              "rotation": None},          # v2 prereg sec 2 (park 45%)
}''')

# ------------------------------------------------- R8 pins: new identities ----
rep('    "etf_manifest": (None, ETF_MANIFEST),',
    '''    "etf_manifest": (None, ETF_MANIFEST),
    "val_batch_prereg": (None, VAL_BATCH_PREREG),
    "v3_metrics": (None, V3_METRICS),
    "tl30_val_metrics": (None, TL30_METRICS),
    "tl30_val_runner": (None, TL30_RUN / "scripts/runner_hybrid_val.py"),
    "r16_module": (None, ROOT / "src/quant/research/p2r16_trend_dispersion.py"),
    "r16_leg_log": (None, R16_RUN / "leg_log.parquet"),
    "r16_membership_events": (None, R16_RUN / "membership_events.parquet"),''')

# --------------------------------------------- R9 B1(m)(val) TL-30 assertion -
rep(blk('        B1 = {"b1m_net_cagr": _bm["net_cagr"],',
        '            f"mdd {B1[\'b1m_max_drawdown\']:.4f}")'),
    '''        B1 = {"b1m_net_cagr": _bm["net_cagr"],
              "b1m_max_drawdown": _bm["max_drawdown"],
              "b1m_net_return_by_year": _bm["net_return_by_year"],
              "b1m_variant": "rate_only (val recomputed in-runner)"}
        log(f"  B1(m)(val): net_cagr {B1['b1m_net_cagr']:+.6f}, "
            f"mdd {B1['b1m_max_drawdown']:.4f}")
        # prereg sec 3: TL-30 published -0.148%/-23.44%; a bit-for-bit
        # mismatch means the val baseline port drifted -> STOP before any
        # config is judged (the whole val gate set is relative to this).
        _T30 = {"net_cagr": -0.00148060230384095,
                "max_drawdown": -0.23441429674947534,
                "by_year": {"2021": 0.14274922609277585,
                            "2022": -0.05202635253338672,
                            "2023": -0.061879245529232296,
                            "2024": -0.021801197364535896}}
        _t30m = tl30_mg["metrics"]["R3-05"]
        assert _T30["net_cagr"] == _t30m["b1m_net_cagr"] \\
            and _T30["max_drawdown"] == _t30m["b1m_max_drawdown"] \\
            and _T30["by_year"] == _t30m["b1m_net_return_by_year"], \\
            "hardcoded TL-30 B1(m) values disagree with the TL-30 metrics file"
        _b1m_diff = {"net_cagr": B1["b1m_net_cagr"] - _T30["net_cagr"],
                     "max_drawdown": (B1["b1m_max_drawdown"]
                                      - _T30["max_drawdown"])}
        for _y, _v in _T30["by_year"].items():
            _b1m_diff["yr" + _y] = B1["b1m_net_return_by_year"][_y] - _v
        _b1m_maxdiff = max(abs(v) for v in _b1m_diff.values())
        B1M_TL30_MATCH = _b1m_maxdiff == 0.0
        log(f"  B1(m)(val) vs TL-30 published: max|diff|={_b1m_maxdiff:.3e} "
            f"-> {'bit-for-bit' if B1M_TL30_MATCH else 'MISMATCH'} "
            f"({json.dumps(_b1m_diff)})")
        if not B1M_TL30_MATCH:
            _fail("B1(m)(val) port drift vs TL-30 published values: "
                  f"{_b1m_diff} -- prereg sec 3 stop clause")''')

# ---------------------------------------------- R10 R16 signal-layer port ----
rep(blk('leg_all = (pl.read_parquet(R16_RUN / "leg_log.parquet")',
        '    pl.col("plan_date").is_in(sig_days))'),
    '''# --- R16 signal-layer port (H2 stock leg) --------------------------------
# Window-local cold start: the R16 C05 strategy simulation is re-run on THIS
# window's signal days (start = window start; the calendar still runs to
# FREEZE_LAST).  Window-local re-derivation is the TL-30 rotation cold-start
# precedent and is what makes the port structurally identical on both windows
# (first signal = all buy_open).  Slicing the R16 run's continuous 2015-2024
# C05 curve instead would inject dev-carried positions into an engine run that
# starts flat, turning incumbent rescale rows into void_no_position sells; the
# imported v2 arm used the window-local construction on dev, which is exactly
# what the prereg requires this port to reproduce (prereg sec 3).
_c05_spec = r16_config["configs"]["C05"]
K_C05 = int(_c05_spec["K"])
_c05_q5 = _c05_spec["filter"] == "on"
_c05_port = r16.simulate_r16(
    f"C05-port-{_WINDOW.upper()}", bank, calendar_full, DEV_START, sig_days,
    pools_at, exposures, K=K_C05,
    membership_fn=lambda prev, ranked, q5, rng: r16.buffer_membership(
        prev, ranked, q5, K_C05, _c05_q5))
_LEG_SCHEMA = {"config_id": pl.String, "plan_date": pl.Date,
               "symbol": pl.String, "kind": pl.String, "target": pl.Float64,
               "outcome": pl.String, "exec_date": pl.Date,
               "notional": pl.Float64, "fee": pl.Float64}
leg_all = pl.DataFrame(
    [{"config_id": "C05",
      **{k: r[k] for k in _LEG_SCHEMA if k != "config_id"}}
     for r in _c05_port.leg_log],
    schema=_LEG_SCHEMA).filter(pl.col("plan_date").is_in(sig_days))
_ME_SCHEMA = {"config_id": pl.String, "signal": pl.Date, "n_kept": pl.Int64,
              "n_entrants": pl.Int64, "n_prev": pl.Int64, "n_left": pl.Int64,
              "n_cash_seats": pl.Int64}
me = pl.DataFrame(
    [{"config_id": "C05", **e} for e in _c05_port.membership_events],
    schema=_ME_SCHEMA).filter(pl.col("signal").is_in(sig_days))
_c05_m = r16.segment_metrics(_c05_port, DEV_START, DEV_END, None)
PORT = {"window": _WINDOW,
        "construction": "window-local rerun of r16.simulate_r16(C05) "
                        "(K=%d, filter=%s) on this window's signal days; leg "
                        "rows/outcomes imported verbatim from that run"
                        % (K_C05, _c05_spec["filter"]),
        "n_leg_rows": leg_all.height, "n_signals": len(sig_days),
        "first_signal": str(sig_days[0]),
        "first_signal_kind_counts": dict(Counter(
            leg_all.filter(pl.col("plan_date") == sig_days[0])["kind"]
            .to_list())),
        "c05_window_metrics": {k: _c05_m[k] for k in
                               ("net_cagr", "max_drawdown",
                                "net_return_by_year", "max_single_name_weight",
                                "execution_rate", "max_one_side_turnover")},
        "membership_events": me.height}
if _WINDOW == "dev":
    _ref_leg = (pl.read_parquet(R16_RUN / "leg_log.parquet")
                .filter(pl.col("config_id") == "C05")
                .filter(pl.col("plan_date").is_in(sig_days)))
    _leg_same = leg_all.equals(_ref_leg)
    _leg_sorted = leg_all.sort("plan_date", "symbol", "kind").equals(
        _ref_leg.sort("plan_date", "symbol", "kind"))
    _ref_me = (pl.read_parquet(R16_RUN / "membership_events.parquet")
               .filter(pl.col("config_id") == "C05")
               .filter(pl.col("signal").is_in(sig_days)))
    _me_same = me.equals(_ref_me)
    _ref_m = r16_metrics["configs"]["C05"]
    _md = {}
    for _k in ("net_cagr", "max_drawdown", "max_single_name_weight",
               "max_one_side_turnover"):
        _md[_k] = abs(_c05_m[_k] - _ref_m[_k])
    for _y, _v in _ref_m["net_return_by_year"].items():
        _md["yr" + _y] = abs(_c05_m["net_return_by_year"][_y] - _v)
    # execution_rate caliber: the R16 CLI's dev window includes the legs PLANNED
    # at the 2020-12-31 boundary signal (executed 2021-01-04, i.e. outside the
    # dev window); the v2/v3 imports (and this port) use window-local signals
    # and therefore exclude them.  The port check compares the rate on the
    # IDENTICAL planned-row set and requires the difference to be exactly the
    # boundary legs -- no tolerance is granted to the rate itself.
    _ref_leg_all = (pl.read_parquet(R16_RUN / "leg_log.parquet")
                    .filter(pl.col("config_id") == "C05").to_dicts())
    _rate_full = r16.window_execution_rate(_ref_leg_all, DEV_START, DEV_END)
    _rate_rest = r16.window_execution_rate(
        [r for r in _ref_leg_all if r["plan_date"] <= sig_days[-1]],
        DEV_START, DEV_END)
    _rate_ok = bool(
        abs(_c05_m["execution_rate"] - _rate_rest["execution_rate"]) <= 1e-12
        and _rate_full["legs_planned"] - _rate_rest["legs_planned"]
        == _rate_full["legs_executed"] - _rate_rest["legs_executed"])
    _port_ok = bool(_leg_same and _me_same and max(_md.values()) <= 1e-9
                    and _rate_ok)
    C05_PORT_PASS = _port_ok
    PORT["dev_reproduction"] = {
        "leg_log_equals_r16_artifact": _leg_same,
        "leg_log_equals_r16_artifact_sorted": _leg_sorted,
        "membership_events_equals_r16_artifact": _me_same,
        "metrics_tolerance": 1e-9,
        "metrics_max_abs_diff": max(_md.values()),
        "metrics_diffs": _md,
        "execution_rate_caliber": {
            "mine": _c05_m["execution_rate"],
            "r16_published": _ref_m["execution_rate"],
            "r16_restricted_to_window_signals": _rate_rest["execution_rate"],
            "rate_match_1e-12": abs(_c05_m["execution_rate"]
                                    - _rate_rest["execution_rate"]) <= 1e-12,
            "boundary_legs_planned": (_rate_full["legs_planned"]
                                      - _rate_rest["legs_planned"]),
            "boundary_legs_executed": (_rate_full["legs_executed"]
                                       - _rate_rest["legs_executed"]),
            "note": "the R16 dev caliber counts legs planned at the 2020-12-31 "
                    "boundary signal (executed 2021-01-04); window-local "
                    "construction excludes them, so the rate is compared on "
                    "the identical planned-row set and the difference must be "
                    "exactly those boundary legs"},
        "reference": "R16 run 20260918T083650 leg_log/membership_events "
                     "config_id=C05 + metrics.json configs.C05",
        "port_pass": bool(_port_ok)}
    log(f"  C05 port(dev): leg_log .equals={_leg_same} "
        f"(sorted {_leg_sorted}, {leg_all.height} rows), membership "
        f".equals={_me_same}, metrics max|diff|={max(_md.values()):.3e}, "
        f"execution_rate {_c05_m['execution_rate']:.10f} vs restricted "
        f"{_rate_rest['execution_rate']:.10f} (boundary legs "
        f"{_rate_full['legs_planned'] - _rate_rest['legs_planned']} planned / "
        f"{_rate_full['legs_executed'] - _rate_rest['legs_executed']} "
        f"executed) -> {'PASS' if _port_ok else 'FAIL'}")
    if not _port_ok:
        for _c in ("H2-01", "H2-03", "H2-04"):
            PORT_BLOCKED[_c] = ("C05 signal-layer port did not reproduce the "
                                "R16 dev artifacts/metrics")
        log("  !! C05 PORT FAILURE -> H2-01/H2-03/H2-04 blocked (prereg sec 6: "
            "that config stops and is reported; the R3 arms continue)")
else:
    log(f"  C05 port(val): {leg_all.height} leg rows over {len(sig_days)} "
        f"signals, first signal {sig_days[0]} kinds "
        f"{PORT['first_signal_kind_counts']} (dev-validated port)")''')

# --------------------------------------------------------- R11 drop old me ---
rep(blk('me = (pl.read_parquet(R16_RUN / "membership_events.parquet")',
        '    pl.col("signal").is_in(sig_days))'),
    '# membership_events come from the same port run (see above).')

# -------------------------- R11b corporate actions: per-config panel filter ---
rep('CORP_ACTIONS_ARG = CORP_ACTIONS if _WINDOW == "val" else None',
    '''CORP_ACTIONS_ARG = CORP_ACTIONS if _WINDOW == "val" else None


def _ca_for(inp: dict):
    """v1.3 share changes filtered to THIS config's daily panel.

    The engine fails closed on a corporate action naming a symbol absent from
    the daily frame, and a share change for a symbol a config can never hold is
    outside that config's world.  The R3 arms carry the full 9-symbol ETF panel
    (both val rows -> identical to TL-30); the H2 mixed arms carry only their
    own leg ETFs, so 513100/513500 share changes do not apply to them (they
    hold neither).  Dev is unaffected (CORP_ACTIONS_ARG is None there), which is
    why the dev byte-reproduction anchors are unchanged by this filter.
    """
    if CORP_ACTIONS_ARG is None:
        return None
    keep = set(inp["daily"]["symbol"].unique().to_list())
    return CORP_ACTIONS_ARG.filter(pl.col("symbol").is_in(keep))''')
rep('def run_one(cid: str) -> dict:\n'
    '    inp = INPUTS[cid]\n'
    '    t_cfg = time.perf_counter()\n'
    '    res = run_band_backtest_intents(',
    '''def run_one(cid: str) -> dict:
    inp = INPUTS[cid]
    _ca_arg = _ca_for(inp)
    if _ca_arg is not None:
        log(f"  {cid}: corporate_actions applicable {_ca_arg.height} row(s) "
            f"{_ca_arg['symbol'].to_list()}")
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(''')
rep('        corporate_actions=CORP_ACTIONS_ARG,',
    '        corporate_actions=_ca_arg,')

# ------------------------------------- R12 consistency loop: run on both -----
rep('for t in (sig_days if _WINDOW == "dev" else []):', 'for t in sig_days:')

# --------------------------------------------- R13 gate8 stuck: dev-only -----
rep(blk('    if g8v3["stuck_final"]:',
        '              f"stuck positions {g8v3[\'stuck_final\']} (prereg sec 3)")'),
    '''    if g8v3["stuck_final"]:
        if _WINDOW == "dev":
            _fail(f"{cid}: gate 8 v3 HARD ASSERTION FAILED -- end-of-run armed "
                  f"stuck positions {g8v3['stuck_final']} (prereg sec 3)")
        else:
            log(f"  WARN {cid}: gate 8 v3 armed-stuck positions at val end "
                f"{g8v3['stuck_final']} -- NON-GATE disclosure on val "
                "(the 3 R16 val gates are the only judgement; not a stop)")''')

# ------------------------------------ R14 val gates via r16.evaluate_val_gates
rep(blk('        g = {"1_excess_ge_1pp": excess >= 0.010,',
        '             "advantage_years": len(adv), "val_excess_vs_b1m": excess}'),
    '''        g = {"1_excess_ge_1pp": excess >= 0.010,
             "2_advantage_years_ge_2_of_4": len(adv) >= 2 and len(b1y) == 4,
             "3_mdd_le_20pct_and_le_B1m":
                 abs(mdd) <= 0.20 + 1e-12
                 and abs(mdd) <= abs(B1["b1m_max_drawdown"]) + 1e-12,
             "advantage_years": len(adv), "val_excess_vs_b1m": excess}
        # prereg sec 2: the frozen val rule IS r16.evaluate_val_gates; the
        # inline caliber above is the report column and must agree.
        _vmod_in = {
            "excess_vs_b1m": excess,
            "excess_by_year": {str(y): (yr[y] - b1y[y])
                               for y in yr if y in b1y},
            "max_drawdown": mdd,
            "b1m_max_drawdown": B1["b1m_max_drawdown"]}
        _vmod = r16.evaluate_val_gates(_vmod_in)
        _vinline = sorted(k for k in ("1_excess_ge_1pp",
                                      "2_advantage_years_ge_2_of_4",
                                      "3_mdd_le_20pct_and_le_B1m")
                          if not g[k])
        if _vmod["failed_gates"] != _vinline \\
                or _vmod["advantage_years"] != len(adv):
            _fail(f"{cid}: inline val gates != r16.evaluate_val_gates: "
                  f"{_vmod} vs {_vinline}/{len(adv)}")
        m["val_gates_module"] = _vmod
        m["val_gate_input"] = _vmod_in''')

# ------------------------------------------------ R15 R3-A0 dev-only anchor --
rep(blk('# R3-A0 regression: 5-frame .equals vs the v2 run\'s ROT-05 outputs +',
        '        "phase of this same adapted runner; per val prereg sec 6)")'),
    '''# R3-A0 regression anchor (dev only): 5-frame .equals vs the v2 run's
# ROT-05 outputs + net_cagr must equal the v2 metric.  R3-A0 is NOT
# re-adjudicated and is not run on val (TL-30 consumed it; prereg sec 1).
regression: dict = {}
if _WINDOW == "dev":
    results["R3-A0"] = run_one("R3-A0")
    r0 = results["R3-A0"]["res"]
    _sd, _sv = er.slice_curve(r0.daily["date"].to_list(),
                              r0.daily["equity"].to_list(),
                              DEV_START, DEV_END)
    _cagr0 = er.cagr(_sv[0], _sv[-1], _sd[0], _sd[-1])
    v2_rot05 = v2_mg["metrics"]["ROT-05"]
    ref = {name: pl.read_parquet(V2_RUN / "outputs" / fn) for name, fn in
           (("intents", "ROT-05_intents.parquet"),
            ("fills", "ROT-05_fills.parquet"),
            ("events", "ROT-05_events.parquet"),
            ("daily", "ROT-05_daily_equity.parquet"),
            ("clips_final", "ROT-05_clips_final.parquet"))}
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
        _fail(f"R3-A0 REGRESSION FAILURE: {regression} -- abort before "
              "remaining configs per val prereg sec 6 (R3-A0 != v2 ROT-05)")
    log("  R3-A0 regression anchor PASS (== v2 ROT-05, 5/5 frames)")
else:
    log("  R3-A0 anchor NOT RUN on val (TL-30 already consumed it; prereg "
        "sec 1 excludes it from the batch)")''')

# ------------------------------------ R16 dev reproduction of the 7 arms -----
rep(blk('for cid in [c for c in CONFIG_IDS if c != "R3-A0" and c in FRAMES]:',
        'check_budget("all engine runs")'),
    blk('for cid in [c for c in CONFIG_IDS if c != "R3-A0" and c in FRAMES]:',
        'check_budget("all engine runs")') + '''

# === 11b. dev reproduction of the batch arms (v3 / v2 output bytes) ==========
# prereg sec 3: no config is consumed on val before its dev-window port output
# reproduces the source run frame-for-frame.  R3-01..04 -> v3 dev outputs;
# H2-01/03/04 -> v2 dev outputs; 5 frames + net_cagr per arm.
DEV_REPRO: dict = {}
if _WINDOW == "dev":
    _refrun = {"R3-01": V3_RUN, "R3-02": V3_RUN, "R3-03": V3_RUN,
               "R3-04": V3_RUN, "H2-01": V2_RUN, "H2-03": V2_RUN,
               "H2-04": V2_RUN}
    _v3mg = json.loads(V3_METRICS.read_text(encoding="utf-8"))
    for cid in JUDGED_IDS:
        if cid not in results:
            continue
        rr = results[cid]["res"]
        _rd = _refrun[cid] / "outputs"
        got = {"intents": FRAMES[cid], "fills": rr.fills, "events": rr.events,
               "daily": rr.daily, "clips_final": rr.clips_final}
        _sfx = {"intents": "intents", "fills": "fills", "events": "events",
                "daily": "daily_equity", "clips_final": "clips_final"}
        ref = {k: pl.read_parquet(_rd / f"{cid}_{_sfx[k]}.parquet")
               for k in got}
        per = {k: got[k].equals(ref[k]) for k in got}
        _sd2, _sv2 = er.slice_curve(rr.daily["date"].to_list(),
                                    rr.daily["equity"].to_list(),
                                    DEV_START, DEV_END)
        _cg2 = er.cagr(_sv2[0], _sv2[-1], _sd2[0], _sd2[-1])
        _ref_cagr = (_v3mg if _refrun[cid] == V3_RUN
                     else v2_mg)["metrics"][cid]["net_cagr"]
        per["net_cagr_matches_metrics"] = abs(_cg2 - _ref_cagr) <= 1e-12
        _rows = {k: v.height for k, v in got.items()}
        DEV_REPRO[cid] = {**per, "net_cagr": _cg2, "ref_net_cagr": _ref_cagr,
                          "ref_run": _refrun[cid].name, "frame_rows": _rows}
        log(f"  dev repro {cid} vs {_refrun[cid].name}: "
            + " ".join(f"{k}={per[k]}" for k in per)
            + f" | rows {json.dumps(_rows)}")
        if not all(per.values()):
            PORT_BLOCKED[cid] = (f"dev output does not reproduce "
                                 f"{_refrun[cid].name}: "
                                 f"{json.dumps({k: v for k, v in per.items() if not v})}")
    log(f"  dev reproduction blocked configs: {sorted(PORT_BLOCKED) or 'none'}")''')

# ------------------------------------------ R17 disclosures base_profile -----
rep(blk('base_profile = rotation_fill_profile("R3-A0")',
        '        continue'),
    '''base_profile = (rotation_fill_profile("R3-A0") if "R3-A0" in results
                else None)
for cid in results:
    if cid == "R3-A0" or base_profile is None:
        continue''')

# ------------------------------------------------ R18 stop note windowed -----
rep(blk('_goal_hit = [cid for cid in gates',
        '                  "consumed")'),
    '''_goal_hit = [cid for cid in gates
             if gates[cid][_GK][_PASSKEY]
             and metrics[cid]["goal_net_cagr_ge_10pct"]]
if _WINDOW == "val":
    _val_pass = sorted(c for c in gates if gates[c][_GK][_PASSKEY])
    _STOP_NOTE = (
        "VAL CONSUMED (one-shot, exp-20260920-val-batch mixed family): "
        f"{len(_val_pass)}/{len(gates)} of the 7 configs pass all 3 frozen "
        f"val gates ({', '.join(_val_pass) or 'none'}); goal column (net CAGR "
        f">= 10%) hit by {', '.join(_goal_hit) or 'none'}; port-blocked "
        f"configs {sorted(PORT_BLOCKED) or 'none'}.  No re-run, no added "
        "config; any post-hoc change demotes these results to exploratory.")
elif _goal_hit:
    _STOP_NOTE = ("GOAL HIT (dev): " + ", ".join(_goal_hit)
                  + " pass all 8 gates AND net CAGR >= 10% -> STOP and "
                    "report user; val application is a separate user "
                    "decision")
elif n_pass:
    _STOP_NOTE = (f"{n_pass}/{len(gates)} configs pass all dev gates but "
                  "none reaches the 10% goal column -> bookkeep and "
                  "CONTINUE dev exploration per the user's 2026-09-19 ruling")
else:
    _STOP_NOTE = (f"no config passed all dev gates ({n_pass}/{len(gates)}); "
                  "ROT branch PAUSED per the v3 stop clause (direction "
                  "re-evaluation is a separate user decision)")''')
rep('log(f"== gates: {n_pass}/{len(gates)} dev_pass ==")',
    'log(f"== gates: {n_pass}/{len(gates)} {_PASSKEY} ==")')

# --------------------------------------------- R19 2025+ zero-touch gate -----
rep('(out_dir / "dividend_events.csv").write_text(',
    '''_FREEZE_VIOL = []
# the zero-touch line is 2025-01-01: the dev window's own boundary seam
# (intents expiring 2021-01-01) is inside the freeze-respecting data range and
# is NOT a violation; on val DEV_END == FREEZE_END exactly.
_MAXD = DEV_END if _WINDOW == "val" else FREEZE_END
if _WINDOW == "val" and _MAXD != FREEZE_END:
    _fail("val phase boundary must be the freeze line 2024-12-31")
for _cid in results:
    _res = results[_cid]["res"]
    _chk = {"intents.decision": FRAMES[_cid]["decision_date"].max(),
            "intents.expiry": FRAMES[_cid]["expiry_date"].max(),
            "daily.date": _res.daily["date"].max(),
            "fills.date": (_res.fills["date"].max()
                           if _res.fills.height else None),
            "events.date": (_res.events["date"].max()
                            if _res.events.height else None)}
    for _nm, _v in _chk.items():
        if _v is not None and _v > _MAXD:
            _FREEZE_VIOL.append(f"{_cid}:{_nm}={_v}")
for _cid in set(INPUTS):
    for _a in ("daily", "half", "limits"):
        _d = INPUTS[_cid][_a]
        if _d.height:
            _c = "trade_date" if "trade_date" in _d.columns else "date"
            _v = _d[_c].max()
            if _v is not None and _v > _MAXD:
                _FREEZE_VIOL.append(f"{_cid}:input.{_a}={_v}")
log(f"  freeze boundary check (<= {_MAXD}; 2025-01-01 zero-touch): "
    f"{'PASS' if not _FREEZE_VIOL else _FREEZE_VIOL[:5]}")
if _FREEZE_VIOL:
    _fail(f"2025+ ZERO-TOUCH VIOLATION: {_FREEZE_VIOL[:5]}")

# val deliverables: baseline record + three-gate table ----------------------
if _WINDOW == "val":
    (out_dir / "b1m_val.json").write_text(json.dumps({
        "benchmark": "B1(m)(val)",
        "definition": "r16.simulate_r16(fractional=True, K=0, T200-40, "
                      "fee_bands=B1_FEE_SCHEDULE_RATE_ONLY) on the val "
                      "window, computed in-runner (prereg sec 3)",
        "net_cagr": B1["b1m_net_cagr"],
        "max_drawdown": B1["b1m_max_drawdown"],
        "net_return_by_year": B1["b1m_net_return_by_year"],
        "tl30_published": {"net_cagr": -0.00148060230384095,
                           "max_drawdown": -0.23441429674947534,
                           "net_return_by_year": {
                               "2021": 0.14274922609277585,
                               "2022": -0.05202635253338672,
                               "2023": -0.061879245529232296,
                               "2024": -0.021801197364535896}},
        "tl30_match_bit_for_bit": bool(B1M_TL30_MATCH),
        "dev_port_check": "the same assembly on the dev window reproduces "
                          "R16 metrics.json configs.C05 b1m_net_cagr / "
                          "b1m_max_drawdown / b1m_net_return_by_year to 1e-9 "
                          "(dev phase of this run)",
        "per_year_pool_and_exposure": {
            str(y): {
                "mean_exposure": (sum(exposures[t] for t in sig_days
                                      if t.year == y)
                                  / max(1, sum(1 for t in sig_days
                                               if t.year == y))),
                "mean_pool_size": (sum(pools_at[t]["n"] for t in sig_days
                                       if t.year == y)
                                   / max(1, sum(1 for t in sig_days
                                                if t.year == y))),
                "n_signals": sum(1 for t in sig_days if t.year == y)}
            for y in sorted({t.year for t in sig_days})}},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    _vtab = []
    for cid in JUDGED_IDS:
        if cid in PORT_BLOCKED:
            _vtab.append({"config": cid, "verdict": "port_blocked_aborted",
                          "blocked_reason": PORT_BLOCKED[cid]})
            continue
        if cid not in metrics:
            continue
        m, g = metrics[cid], gates[cid][_GK]
        _vtab.append({
            "config": cid, "verdict": g["verdict"],
            "net_cagr": m["net_cagr"], "excess_vs_b1m": m["excess_vs_b1m"],
            "advantage_years": g["advantage_years"],
            "n_years": len(m["b1m_net_return_by_year"]),
            "max_drawdown": m["max_drawdown"],
            "b1m_max_drawdown": m["b1m_max_drawdown"],
            "gates_passed": len(GATE_KEYS) - len(g["failed_gates"]),
            "failed_gates": g["failed_gates"],
            "goal_net_cagr_ge_10pct": bool(m["goal_net_cagr_ge_10pct"]),
            "max_one_side_turnover": m["max_one_side_turnover"],
            "max_single_name_weight": m["max_single_name_weight"],
            "net_return_by_year": m["net_return_by_year"],
            "r16_evaluate_val_gates": {
                k: (v if isinstance(v, (str, list, int, float)) else bool(v))
                for k, v in m["val_gates_module"].items()}})
    (out_dir / "val_gates_table.json").write_text(json.dumps({
        "experiment_id": "exp-20260920-val-batch",
        "window": f"val {DEV_START}..{DEV_END}",
        "rule": "R16 evaluate_val_gates verbatim (prereg sec 2): "
                "1 excess vs B1(m)(val) >= +1pp; 2 advantage years >= 2/4; "
                "3 maxDD <= 20% AND <= |B1(m)(val) maxDD|",
        "b1m_val": {"net_cagr": B1["b1m_net_cagr"],
                    "max_drawdown": B1["b1m_max_drawdown"],
                    "net_return_by_year": B1["b1m_net_return_by_year"]},
        "configs": _vtab},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")

(out_dir / "dividend_events.csv").write_text(''')

# ------------------------------------------------- R20 manifest identities ---
rep('    "run_id": RUN_DIR.name,\n'
    '    "experiment_id": "exp-20260919-hybrid-family-v3",',
    '    "run_id": RUN_DIR.name,\n'
    '    "experiment_id": "exp-20260920-val-batch (mixed family, V1 run)",\n'
    '    "phase_window": _WINDOW,\n'
    '    "configs_requested": JUDGED_IDS,\n'
    '    "configs_blocked_port": PORT_BLOCKED,\n'
    '    "ports": {"b1m_dev_port_check": "PASS (1e-9 vs R16 metrics C05)",\n'
    '              "b1m_val_tl30_match": True,\n'
    '              "c05_signal_layer_port": PORT,\n'
    '              "dev_reproduction": DEV_REPRO},')
rep('    "status": "completed" if not BLOCKED else "completed_with_blocked_config",',
    '    "status": ("completed" if not PORT_BLOCKED else\n'
    '               "completed_with_blocked_configs"),')
rep('               "version": "v1.2 (frozen, unchanged from v1; v2 prereg sec 5)"},',
    '               "version": "v1.4.1 (pin a01cb29c; zones path not used; '
    'non-zones path byte-identical to v1.3 84a2443a, anchored by this run\'s '
    'dev arms + the C05 port)"},')
rep(blk('    "window": {"dev": f"{DEV_START}..{DEV_END}",',
        '               "val_consumed": False},'),
    '''    "window": {"phase": _WINDOW,
               "range": f"{DEV_START}..{DEV_END}",
               "signals": f"{sig_days[0]}..{sig_days[-1]} ({len(sig_days)})",
               "freeze_check": "PASS (no frame date > 2024-12-31)",
               "expiry_clamp_S_val_1": True,
               "val_consumed": _WINDOW == "val"},''')
rep(blk('    "trial_accounting": {"this_round": "1 family (7 configs, all run)",',
        '                                               "(config json trial_accounting)"},'),
    '''    "trial_accounting": {
        "this_round": "V1 mixed family: 7 val configs (R3-01..04, "
                      "H2-01/03/04); batch total 12 configs (V1+V2) "
                      "296->308",
        "lineage": "hybrid v1 205->214; v2 214->222; v3 222->229; TL-30 "
                   "238->241; val batch 296->308 (ledger maintained by the "
                   "main dialogue)"},''')
rep(blk('    "gates_dev_pass": [cid for cid in gates if gates[cid][_GK][_PASSKEY]],',
        '    "val_consumed": False,'),
    '''    "gates_pass": [cid for cid in gates if gates[cid][_GK][_PASSKEY]],
    "gates_pass_key": _PASSKEY,
    "advanced_to_validation": _WINDOW == "val",
    "val_gates_rule": "R16 evaluate_val_gates verbatim (prereg sec 2)",''')
rep('    if p.is_file() and p.name not in ("manifest.json", "runner.log"):',
    '    if p.is_file() and not p.name.startswith("manifest") \\\n'
    '            and p.suffix != ".log":')
rep('    "command": [sys.executable,\n'
    '                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_hybrid_v3.py"],',
    '    "command": [sys.executable,\n'
    '                f"artifacts/runs/{RUN_DIR.name}/scripts/'
    'runner_val_batch_hybrid.py"],\n'
    '    "runner_sha256": sha256_file(Path(__file__).resolve()),')

# ---------------------------------------------------- R21 mg identity fields -
rep('    "experiment_id": "exp-20260919-hybrid-family-v3",\n'
    '    "engine_sha256_16": ENGINE_SHA_AT_START[:16],',
    '    "experiment_id": "exp-20260920-val-batch (mixed family, V1 run)",\n'
    '    "phase_window": _WINDOW,\n'
    '    "engine_sha256_16": ENGINE_SHA_AT_START[:16],')
rep('    "advanced_to_validation": False, "val_consumed": False,',
    '    "advanced_to_validation": _WINDOW == "val",\n'
    '    "val_consumed": _WINDOW == "val",\n'
    '    "batch": "exp-20260920-val-batch (mixed family, V1 run)",\n'
    '    "phase_window": _WINDOW,\n'
    '    "judged_configs": JUDGED_IDS,\n'
    '    "port_blocked": PORT_BLOCKED,\n'
    '    "ports": {"b1m_dev_port": "1e-9 vs R16 metrics C05",\n'
    '              "b1m_val_tl30_bit_for_bit": True,\n'
    '              "c05_signal_layer_port": PORT,\n'
    '              "dev_reproduction": DEV_REPRO},')

# ------------------------------------------------ R22 _fail manifest suffix --
rep('def _fail(reason: str) -> None:\n    log(f"!! FAIL: {reason}")',
    '''def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    try:
        with (RUN_DIR / "tmp" / "stop_report.md").open(
                "a", encoding="utf-8", newline="\\n") as _sr:
            _sr.write(
                f"\\n## STOP ({_WINDOW} phase) "
                f"{datetime.now(timezone.utc).isoformat()}\\n\\n"
                f"- reason: {reason}\\n"
                f"- wall_s: {time.perf_counter() - T0:.1f}\\n"
                f"- port_blocked: {json.dumps(PORT_BLOCKED, ensure_ascii=False)}\\n"
                f"- dev_repro: {json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'frame_rows'} for k, v in DEV_REPRO.items()}, ensure_ascii=False)}\\n"
                f"- log_tail:\\n\\n```\\n"
                + "\\n".join(LOG_LINES[-30:]) + "\\n```\\n")
    except Exception as _e:      # the stop report must never mask the stop
        print(f"stop_report write failed: {_e!r}", flush=True)''')
rep('    (RUN_DIR / "manifest.json").write_text(json.dumps({',
    '    (RUN_DIR / f"manifest{_SUF}.json").write_text(json.dumps({\n')
rep('        "experiment_id": "exp-20260919-hybrid-family-v2",\n'
    '        "status": "failed", "failure_reason": reason,',
    '        "experiment_id": "exp-20260920-val-batch (mixed family, V1 run)",\n'
    '        "phase_window": _WINDOW,\n'
    '        "status": "failed", "failure_reason": reason,')

# ------------------------------------------------- R23 load v3/TL-30 metrics -
rep('v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))',
    'v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))\n'
    'v3_mg = json.loads(V3_METRICS.read_text(encoding="utf-8"))\n'
    'tl30_mg = json.loads(TL30_METRICS.read_text(encoding="utf-8"))')

# --------------------------------- R24 val phase: dev-first port discipline --
rep('ENGINE_SHA_AT_START = pins["engine"]["sha256"]',
    '''ENGINE_SHA_AT_START = pins["engine"]["sha256"]

# dev-first port discipline (prereg sec 3): the val phase may not consume a
# config whose dev-window port output did not reproduce the source run.
PORT_STATUS_FILE = RUN_DIR / "tmp" / "port_status.json"
if _WINDOW == "val":
    if not PORT_STATUS_FILE.exists():
        _fail("val phase requires tmp/port_status.json written by the dev "
              "phase (dev-first port discipline, prereg sec 3)")
    PORT_STATUS = json.loads(PORT_STATUS_FILE.read_text(encoding="utf-8"))
    pins["dev_phase_port_status"] = {
        "path": str(PORT_STATUS_FILE),
        "sha256": sha256_file(PORT_STATUS_FILE),
        "all_ports_pass": PORT_STATUS.get("all_ports_pass")}
    log(f"  dev-phase port status: all_ports_pass="
        f"{PORT_STATUS.get('all_ports_pass')} blocked="
        f"{PORT_STATUS.get('blocked') or 'none'}")
    if PORT_STATUS.get("b1m_dev_port_pass") is not True:
        _fail("dev phase did not record a passing B1(m) dev port check")
    for _c in PORT_STATUS.get("blocked", []):
        PORT_BLOCKED[_c] = ("dev phase port reproduction failed: "
                            + json.dumps(PORT_STATUS.get("detail", {})
                                         .get(_c, "see manifest_dev.json"),
                                         ensure_ascii=False))
    if PORT_BLOCKED:
        CONFIG_IDS = [c for c in CONFIG_IDS if c not in PORT_BLOCKED]
        log(f"  val consumption restricted to {CONFIG_IDS} "
            f"(port-blocked {sorted(PORT_BLOCKED)} reported as aborted, "
            "prereg sec 6)")''')

# ------------------------------------- R25 dev phase: record port status -----
rep('    "outputs": outs,',
    '''    "outputs": outs,
    "outputs_dir": out_dir.name,
    "dev_reproduction": DEV_REPRO,''')

# --------------------------------------------------- R26 report: opening -----
rep(blk('rep = ["# 混合族 v3 判定（exp-20260919-hybrid-family-v3，降债阶梯）", "",',
        '       "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]'),
    '''_repro_txt = {k: {kk: vv for kk, vv in v.items() if kk != "frame_rows"}
              for k, v in DEV_REPRO.items()}
_hdr = ("| 配置 | val净CAGR | 超额vs B1(m)(val) | 优势年 | maxDD | "
        "B1(m)val maxDD | 单边换手 | 单票max权重 | 目标≥10% | 过/3 | 失败门 "
        "| 判定 |" if _WINDOW == "val" else
        "| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | "
        "单票max权重 | 门8v3 最终交付 | 8v2对照 | R16原口径 | 目标≥10% | 过/8 "
        "| 失败门 | 判定 |")
_sep = ("|---|---|---|---|---|---|---|---|---|---|---|---|" if _WINDOW == "val"
        else "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
rep = [f"# exp-20260920-val-batch V1 判定（混合族 7 配置）-- {_WINDOW} 阶段", "",
       f"- 运行 `{RUN_DIR.name}`（阶段 {_WINDOW}）；引擎 v1.4.1 sha256:16 "
       f"`{ENGINE_SHA_AT_START[:16]}`（运行前后一致；非 zones 路径与 v1.3 "
       f"84a2443a 的等价由本轮 dev 锚实证）；统管预登记 sha256:16 "
       f"`{pins['val_batch_prereg']['sha256'][:16]}`；配置来源 v3 预登记 sha256:16 "
       f"`{pins['prereg']['sha256'][:16]}`（已冻结，运行中零修改）。",
       f"- 窗口 {_WINDOW} {DEV_START}..{DEV_END}，信号 {sig_days[0]}.."
       f"{sig_days[-1]}（{len(sig_days)} 个月末；末月信号因执行日越界丢弃，"
       f"S-val-1 expiry 钳位见 metrics_and_gates.json）。",
       "- 端口验证：B1(m) 于 dev 窗 1e-9 复现 R16 metrics C05；H2 股票腿 = "
       "R16 信号层 val 端口（dev 复现 R16 leg_log/membership_events/metrics）；"
       "各臂 dev 输出逐帧复现 v2/v3 源 run。",
       "- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。", "",
       "## 〇、端口与复现记录", "",
       f"- C05 信号层端口（{PORT['window']}）：{json.dumps(PORT['first_signal_kind_counts'], ensure_ascii=False)}"
       f"，{PORT['n_leg_rows']} 行腿记录 / {PORT['n_signals']} 信号。",
       f"- dev 逐臂复现：{json.dumps(_repro_txt, ensure_ascii=False)}",
       f"- R3-A0 回归锚（dev）= v2 ROT-05：{json.dumps(regression)}",
       "- 端口阻塞分配置：" + (json.dumps(PORT_BLOCKED, ensure_ascii=False)
                              if PORT_BLOCKED else "无"), "",
       "## 一、判定表", "", _hdr, _sep]''')

# ------------------------------------------------ R27 report: table rows -----
rep(blk('    m, g = metrics[cid], gates[cid][_GK]',
        "        f\"| {'**dev_pass**' if g.get(_PASSKEY) else 'eliminated'} |\")"),
    '''    m, g = metrics[cid], gates[cid][_GK]
    if _WINDOW == "val":
        rep.append(
            f"| {cid} | {m['net_cagr']*100:+.2f}% "
            f"| {m['excess_vs_b1m']*100:+.2f}pp "
            f"| {g['advantage_years']}/{len(m['b1m_net_return_by_year'])} "
            f"| {m['max_drawdown']*100:.2f}% "
            f"| {m['b1m_max_drawdown']*100:.2f}% "
            f"| {m['max_one_side_turnover']:.2f} "
            f"| {m['max_single_name_weight']*100:.1f}% "
            f"| {'Y' if m['goal_net_cagr_ge_10pct'] else 'N'} "
            f"| {len(GATE_KEYS) - len(g['failed_gates'])} "
            f"| {', '.join(g['failed_gates']) or '-'} "
            f"| {'**val_pass**' if g.get(_PASSKEY) else 'val_eliminated'} |")
        continue
    d3 = m["gate8_v3_final_delivery"]
    d3txt = ("n/a(0 armed)"
             if d3["final_delivery_rate"] is None
             else f"{d3['market_fallback_fills']}+"
                  f"{d3['armed_then_limit_self_fills']}/{d3['armed']}"
                  f"={d3['final_delivery_rate']*100:.1f}%")
    d2 = m["gate8_v2_comparison"]
    d2txt = ("n/a(0 armed)" if d2["delivery_rate"] is None
             else f"{d2['executed']}/{d2['armed']}"
                  f"={d2['delivery_rate']*100:.1f}%")
    rep.append(
        f"| {cid} | {m['net_cagr']*100:+.2f}% "
        f"| {m['b1m_net_cagr']*100:+.2f}% "
        f"| {m['excess_vs_b1m']*100:+.2f}pp | {g['advantage_years']}/{len(m['b1m_net_return_by_year'])} "
        f"| {m['max_drawdown']*100:.2f}% "
        f"| {m['max_one_side_turnover']:.2f} "
        f"| {m['max_single_name_weight']*100:.1f}% "
        f"| {d3txt} "
        f"| {d2txt} "
        f"| {(m['r16_execution_rate_comparison']['value'] or 0)*100:.1f}% "
        f"| {'Y' if m['goal_net_cagr_ge_10pct'] else 'N'} "
        f"| {8 - len(g['failed_gates'])} "
        f"| {', '.join(g['failed_gates']) or '-'} "
        f"| {'**dev_pass**' if g.get(_PASSKEY) else 'eliminated'} |")''')

# --------------------------------------- R28 report: ladder note + tail ------
rep('    rep += ["- 轨迹若非单调 = 结构敏感而非线性机会成本；R3-A0 即 0.25 基点。",',
    '    rep += [("- 轨迹若非单调 = 结构敏感而非线性机会成本；R3-A0 = 0.25 '
    '基点" + ("（val 阶段未运行 R3-A0）" if _WINDOW == "val" else "。")),')
rep(blk('        "## 三、R3-A0 回归锚（= v2 ROT-05 复刻）", "",',
        '        "159934 的 2020-02-26 微偏离见冻结披露（v3 不使用该符号）。"]'),
    '''        "## 三、dev 锚与运行身份", "",
        "- R3-A0 回归锚（dev，= v2 ROT-05 复刻）："
        + (json.dumps(regression) if _WINDOW == "dev"
           else "val 阶段未运行（TL-30 已消费，预登记 §1 排除）") + "。",
        "- 逐臂 dev 复现（v3 源 run / v2 源 run，5 帧 + net_cagr）："
        + json.dumps(_repro_txt, ensure_ascii=False) + "。",
        f"- C05 信号层端口：{json.dumps({k: v for k, v in PORT.items() if k != 'c05_window_metrics'}, ensure_ascii=False)}",
        f"- 阶段：{_WINDOW}；输出目录 `{out_dir.name}`。",
        f"- 输入身份：daily {pins['daily']['sha256'][:16]}、halfday manifest "
        f"{pins['halfday_manifest']['sha256'][:16]}、stk_limit agg "
        f"{pins['stk_limit_aggregate']['aggregate_sha256'][:16]}、etf-daily "
        f"目录聚合 {pins['etf_processed_aggregate']['aggregate_sha256'][:16]}"
        f"、fund_adj 聚合 {pins['fund_adj_aggregate']['recomputed'][:16]}"
        f"（=etf manifest 声明值）、trade_cal 聚合 "
        f"{pins['trade_cal_aggregate']['aggregate_sha256'][:16]}。",
        f"- 环境：python {ENV_VERSIONS['python']} / polars "
        f"{ENV_VERSIONS['polars']} / numpy {ENV_VERSIONS['numpy']}；随机种子："
        f"none（runner 与引擎均无 RNG）。",
        f"- 时间划分：{_WINDOW} {DEV_START}..{DEV_END}；2025+ 零接触（冻结区"
        f"断言 PASS）。",
        "- 试验计账：本 run 7 配置（R3-01..04、H2-01/03/04）；统管预登记声明"
        "策略线 296→308（12 个 val 配置，含 V2 的 F 线 5 个）；台账由主对话收口。",
        f"- 判定：{mg['stop_note']}"]
rep += ["", "## 五、关键发现与口径说明", "",
        "- **判据逐字**：val 判定即 R16 `evaluate_val_gates` 三门（超额 vs "
        "B1(m)(val) ≥+1pp、优势年 ≥2/4、maxDD ≤20% 且 ≤|B1(m)(val) maxDD|）；"
        "runner 内联口径与模块函数逐配置比对一致。",
        "- **基准口径**：B1(m) = 同池等权 + 同曝光路径（T200-40）、"
        "rate_only 费率（无每单 5 元下限，R16 deviation 2）；val 值由 runner "
        "现算并与 TL-30 公布值逐位一致。",
        "- **H2 股票腿**：R16 C05 信号层在本窗冷启动重算（窗内月末信号 + "
        "buffer band K=30 + Q5 过滤），腿记录逐行取自该次模拟；dev 窗同装配"
        "逐帧复现 v2 臂后方展开 val。",
        "- **S-val-1**：末日信号意图 expiry 由 2025-01-01 钳位至 2024-12-31"
        "（逐配置计数见 manifest），行为影响 = 最后交易日在途单存活，"
        "沿 TL-30 披露。",
        "- **引擎 v1.4.1**：zones 路径未启用；非 zones 路径与 v1.3 逐字节等价"
        "由本轮 dev 锚（R3-A0/R3-01..04/H2-01/03/04/C05 端口）实证。",
        "- **冻结区**：2025-01-01 起零接触（本 runner 输出帧全部 ≤ 2024-12-31，"
        "写入前断言）。",
        "- **一次性**：本批次 val 判定一次，不重跑、不加配置；任何据 val 结果"
        "回 dev 的调整都会把这些结果降级为探索样本。"]''')

# ------------------------------------------- R29 final manifest + port file --
rep('(RUN_DIR / "manifest.json").write_text(\n'
    '    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),\n'
    '    encoding="utf-8")',
    '''(RUN_DIR / f"manifest{_SUF}.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
if _WINDOW == "dev":
    (RUN_DIR / "tmp" / "port_status.json").write_text(json.dumps({
        "phase": "dev",
        "all_ports_pass": not PORT_BLOCKED,
        "b1m_dev_port_pass": True,
        "c05_port_pass": C05_PORT_PASS,
        "c05_port": PORT,
        "blocked": sorted(PORT_BLOCKED),
        "detail": PORT_BLOCKED,
        "dev_repro": DEV_REPRO,
        "r3a0_regression": regression,
        "manifest": f"manifest{_SUF}.json",
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "timestamp": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=1), encoding="utf-8")
    log("  tmp/port_status.json written (val phase gate)")

# stop_report: cleared-and-marked for a clean phase ------------------------
with (RUN_DIR / "tmp" / "stop_report.md").open(
        "a", encoding="utf-8", newline="\\n") as _sr2:
    _sr2.write(f"\\n## {_WINDOW} phase finished without stop "
               f"{datetime.now(timezone.utc).isoformat()} "
               f"(status={manifest['status']}, "
               f"blocked={sorted(PORT_BLOCKED) or 'none'})\\n")''')

io.open(DST, "w", encoding="utf-8", newline="\n").write(s)
print(f"stage2 adapted OK: {len(reps)} replacement groups, "
      f"{n0} -> {len(s)} chars")
for name, c in reps:
    print(f"  x{c}  {name}")
print("DST sha256:", hashlib.sha256(s.encode("utf-8")).hexdigest())
