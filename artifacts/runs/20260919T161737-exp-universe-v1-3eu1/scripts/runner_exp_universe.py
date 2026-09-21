# -*- coding: utf-8 -*-
"""exp-20260919-expanded-universe-v1 runner -- engine v1.3 (pin unchanged),
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
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, assert_frozen, batch_aggregate_sha256, load_daily_panel,
    load_dividends_h5, load_halfday_bars, load_split_factor_h5,
    load_stk_limit_batch, run_band_backtest_intents)

P3R2_RUN = ROOT / "artifacts/runs/20260919T030640-p3r2-dev-ad9e"
R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
V1_RUN = ROOT / "artifacts/runs/20260919T054649-hybrid-v1-9k2f"
V3_RUN = ROOT / "artifacts/runs/20260919T110500-hybrid-v3-r3ld"
PREREG_MD = ROOT / "docs/research/exp-20260919-expanded-universe-v1-prereg.md"
V2_PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v2-prereg.md"
V1_PREREG_MD = ROOT / "docs/research/exp-20260919-hybrid-family-v1-prereg.md"
HYB_CONFIG = ROOT / "configs/experiments/expanded-universe-v1.json"
V1_CONFIG = ROOT / "configs/experiments/hybrid-family-v1.json"
V1_METRICS = V1_RUN / "outputs/metrics_and_gates.json"
P3R2_CONFIG = ROOT / "configs/experiments/p3r2-band-v1-readjudication.json"
R16_CONFIG = ROOT / "configs/experiments/p2r16-trend-dispersion.json"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
ETF_DIR = ROOT / "data/processed/etf-daily-20260919"
ETF_DAILY = ETF_DIR / "daily_2015_2024.parquet"
ETF_MANIFEST = ETF_DIR / "manifest.json"
FUND_ADJ_DIR = ROOT / "data/raw/tushare/fund_adj/20260917-r1"
MISMATCH_CSV = ETF_DIR / "preclose_mismatch_detail.csv"
TRADECAL_DIR = ROOT / "data/raw/xiaodefa/trade_cal/20260913-bulk1"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
ENGINE_SHA_EXPECT_FULL = ("84a2443ac28fe1b87e4a18f988fd38cc67cf706d5778e"
                          "262f11465147234082c")
# EU_SMOKE=1 restricts to the smoke pair (runner-level test only; the
# official run leaves it unset; smoke results are NOT the frozen run)
_SMOKE = os.environ.get("EU_SMOKE", "") == "1"
_ALL_CONFIG_IDS = ["EU-A0", "EU-01", "EU-02", "EU-03", "EU-04", "EU-05",
                   "EU-06", "EU-07", "EU-08", "EU-09", "EU-10"]
CONFIG_IDS = ["EU-A0", "EU-01"] if _SMOKE else _ALL_CONFIG_IDS
# frozen universe (v1 prereg sec 2, inherited verbatim; table order)
MEMBERS = ["sh.511010", "sh.518880", "sh.510050", "sh.510300", "sz.159915",
           "sh.510880", "sh.513100", "sh.513500"]
# v2 new leg-only symbol (config json new_leg_symbol): gold ETF, band 0.10,
# t_plus 0, commission identical to the other ETFs; NOT in the ranking
# universe (the 8-member rotation universe is unchanged from v1)
LEG_ONLY = ["sz.159934"]
PANEL_SYMS = MEMBERS + LEG_ONLY                       # ETF data panel = 9
MEMBER_BAND = {m: 0.10 for m in PANEL_SYMS}           # frozen per-member bands
# config matrix (EU prereg sec 2 / configs/experiments/expanded-universe-v1.json,
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
}
DIVIDEND_EXPECT = {"sh.510050": 5, "sh.510300": 6, "sh.510880": 6,
                   "sh.511010": 1}                 # frozen: 18 events in dev
GATE_KEYS = ["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",
             "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",
             "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",
             "7_vs_B3prime_plus_1pp", "8v3_final_delivery_ge_99pct"]
INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "priority": pl.Int64,
    "expiry_date": pl.Date, "target_weight": pl.Float64,
}
PARK_SOURCE = date(2015, 1, 30)   # spec seam S1: engine requires a DATE-typed
# source_signal; the pinned literal "park_init" is un-runnable (engine
# _as_date hard-rejects strings).  Resolved to the park decision date.
# Listed in report pending adjudication; does not affect K (buys have no
# fallback) and does not collide (buy vs monthly sells differ in side/date).

T0 = time.perf_counter()
BUDGET_S = 2700.0   # 12 configs (EU adaptation)
PEAK_RSS = 0.0
LOG_PATH = RUN_DIR / "logs" / "runner.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_LINES: list[str] = []
_logf = LOG_PATH.open("a", encoding="utf-8")


def log(msg: object) -> None:
    global PEAK_RSS
    line = f"[{time.perf_counter() - T0:7.1f}s] {msg}"
    LOG_LINES.append(str(line))
    _logf.write(line + "\n")
    _logf.flush()
    try:
        print(line, flush=True)
    except Exception:
        pass


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rss_gb() -> float:
    global PEAK_RSS
    try:
        import psutil
        v = psutil.Process().memory_info().rss / 1e9
        PEAK_RSS = max(PEAK_RSS, v)
        return v
    except Exception:
        return float("nan")


def check_budget(what: str) -> None:
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name,
        "experiment_id": "exp-20260919-expanded-universe-v1",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


def dints(col: pl.Series) -> np.ndarray:
    # Int64 arithmetic (9cc4 int8-overflow fix -- month() is Int8 in polars)
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


# === 0. identity pins ========================================================
log("== 0. identity pins (engine v1.2 frozen, prereg frozen) ==")
pins: dict = {}
EXPECTED = {
    "engine": (ENGINE_SHA_EXPECT_FULL, ENGINE_PY),
    "p3r2_config": ("b49025b44c719685", P3R2_CONFIG),
    "r16_config": ("27f846a7330919a4", R16_CONFIG),
    "daily": ("d9a63f4cc3032926", DAILY_PARQUET),
    "halfday_manifest": ("2a414174b5df2eee", HALFDAY_DIR / "manifest.json"),
    "split_factor": ("2f436b2f13d09a9b", BUNDLE / "split_factor.h5"),
    "dividends": ("46121c09cddde72e", BUNDLE / "dividends.h5"),
    "index_000300": ("05aaa8183a11c674", INDEX_CHUNK),
    "p3r2_c05_fills": (None, P3R2_RUN / "outputs/C05_fills.parquet"),
    "p3r2_c05_events": (None, P3R2_RUN / "outputs/C05_events.parquet"),
    "p3r2_c05_daily": (None, P3R2_RUN / "outputs/C05_daily_equity.parquet"),
    "p3r2_c05_clips": (None, P3R2_RUN / "outputs/C05_clips_final.parquet"),
    "p3r2_c05_intents": (None, P3R2_RUN / "outputs/C05_intents.parquet"),
    "prereg": (None, PREREG_MD),
    "v2_prereg_inherited": (None, V2_PREREG_MD),
    "v1_prereg_inherited": (None, V1_PREREG_MD),
    "hyb_config": (None, HYB_CONFIG),
    "etf_daily_input": ("b7225d50523106f5", ETF_DAILY),
    "v3_metrics_r306_anchor_source":
        (None, V3_RUN / "outputs/metrics_and_gates.json"),
    "v3_r306_intents": (None, V3_RUN / "outputs/R3-06_intents.parquet"),
    "v3_r306_fills": (None, V3_RUN / "outputs/R3-06_fills.parquet"),
    "v3_r306_events": (None, V3_RUN / "outputs/R3-06_events.parquet"),
    "v3_r306_daily": (None, V3_RUN / "outputs/R3-06_daily_equity.parquet"),
    "v3_r306_clips": (None, V3_RUN / "outputs/R3-06_clips_final.parquet"),
    "v1_config_reference": (None, V1_CONFIG),
    "v1_metrics_rot01_source": (None, V1_METRICS),
    "r16_metrics": (None, R16_RUN / "metrics.json"),
    "p3r2_runner": (None, P3R2_RUN / "tmp/runner_p3r2_intents.py"),
    "etf_manifest": (None, ETF_MANIFEST),
}
for name, (expect, path) in EXPECTED.items():
    got = sha256_file(Path(path))
    ok = True if expect is None else got.startswith(expect)
    pins[name] = {"path": str(path), "sha256": got, "expected": expect,
                  "match": ok}
    log(f"  {name}: {got[:16]} expect {expect} match={ok}")
    if not ok:
        _fail(f"identity pin mismatch: {name}")
ENGINE_SHA_AT_START = pins["engine"]["sha256"]

stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {
    "path": str(STK_DIR), **stk_agg, "expected": "3c53abf3b0c39b42",
    "match": stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit aggregate pin mismatch")
etf_agg = batch_aggregate_sha256(ETF_DIR)
cal_agg = batch_aggregate_sha256(TRADECAL_DIR)
etf_manifest_json = json.loads(ETF_MANIFEST.read_text(encoding="utf-8"))
# etf manifest declares the raw-batch aggregate as
# sha256("\n".join(f"{chunk}:{per_file_sha256}" for sorted chunks)) where the
# per-file hashes come from the RAW batch manifest -- reproduce that rule:
FUND_ADJ_MANIFEST = FUND_ADJ_DIR / "manifest.json"
pins["fund_adj_batch_manifest"] = {
    "path": str(FUND_ADJ_MANIFEST), "sha256": sha256_file(FUND_ADJ_MANIFEST)}
adj_batch_manifest = json.loads(FUND_ADJ_MANIFEST.read_text(encoding="utf-8"))
adj_chunks = adj_batch_manifest.get("chunks", {})
adj_rehash_mismatch = []
for cname, centry in sorted(adj_chunks.items()):
    cpath = FUND_ADJ_DIR / cname
    if not cpath.exists() or sha256_file(cpath) != centry.get("sha256"):
        adj_rehash_mismatch.append(cname)
declared_adj = etf_manifest_json["source"]["fund_adj"]["identity"][
    "aggregate_sha256_of_sorted_per_file_hashes"]
declared_fund_daily = etf_manifest_json["source"]["fund_daily"]["identity"][
    "aggregate_sha256_of_sorted_per_file_hashes"]
adj_agg_recomputed = hashlib.sha256("\n".join(
    f"{k}:{v['sha256']}" for k, v in sorted(adj_chunks.items()))
    .encode("utf-8")).hexdigest()
pins["fund_adj_aggregate"] = {
    "rule": "sha256 of sorted '<chunk>:<per_file_sha256>' lines per the etf "
            "standardization agg_hash; per-file hashes re-verified against "
            "the raw batch manifest",
    "recomputed": adj_agg_recomputed,
    "expected_declared_in_etf_manifest": declared_adj,
    "chunks_in_batch_manifest": len(adj_chunks),
    "rehash_mismatches": adj_rehash_mismatch,
    "match": (adj_agg_recomputed == declared_adj
              and not adj_rehash_mismatch)}
pins["etf_processed_aggregate"] = {**etf_agg, "expected": None, "match": True}
pins["trade_cal_aggregate"] = {**cal_agg, "expected": None, "match": True}
pins["etf_manifest_declared_fund_daily_aggregate"] = declared_fund_daily
if not pins["fund_adj_aggregate"]["match"]:
    _fail(f"fund_adj identity check failed: recomputed "
          f"{adj_agg_recomputed[:16]} vs declared {declared_adj[:16]}, "
          f"rehash mismatches {adj_rehash_mismatch[:5]}")
log(f"  etf processed dir aggregate: {etf_agg['aggregate_sha256'][:16]} "
    f"({etf_agg['files']} files); fund_adj batch re-verified "
    f"({len(adj_chunks)} chunks, 0 mismatches) aggregate matches manifest: "
    f"{pins['fund_adj_aggregate']['match']}")
log(f"  python {platform.python_version()} | polars {pl.__version__} | "
    f"numpy {np.__version__} | rss {rss_gb():.2f} GB")
ENV_VERSIONS = {"python": platform.python_version(),
                "platform": platform.platform(),
                "polars": pl.__version__, "numpy": np.__version__}

r16_config = json.loads(R16_CONFIG.read_text(encoding="utf-8"))
r16_metrics = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
p3r2_mg = json.loads((P3R2_RUN / "outputs/metrics_and_gates.json")
                     .read_text(encoding="utf-8"))
v3_mg = json.loads((V3_RUN / "outputs/metrics_and_gates.json")
                   .read_text(encoding="utf-8"))
# v1 metrics: lineage reference only in v3 (universe-sensitivity block retired)
v1_mg = json.loads(V1_METRICS.read_text(encoding="utf-8"))
V1_ROT01 = {"net_cagr": v1_mg["metrics"]["ROT-01"]["net_cagr"],
            "max_drawdown": v1_mg["metrics"]["ROT-01"]["max_drawdown"],
            "excess_vs_b1m": v1_mg["metrics"]["ROT-01"]["excess_vs_b1m"],
            "advantage_years":
                v1_mg["gates"]["ROT-01"]["dev"]["advantage_years"],
            "max_one_side_turnover":
                v1_mg["metrics"]["ROT-01"]["max_one_side_turnover"],
            "max_single_name_weight":
                v1_mg["metrics"]["ROT-01"]["max_single_name_weight"],
            "failed_gates": v1_mg["gates"]["ROT-01"]["dev"]["failed_gates"],
            "source": "v1 run 20260919T054649-hybrid-v1-9k2f "
                      "metrics_and_gates.json verbatim"}
B3P = {"T200-40": r16_metrics["B3prime_dev_mean_net_cagr"]["T200-40"],
       "FIX75": r16_metrics["B3prime_dev_mean_net_cagr"]["FIX75"]}
# B1(m) benchmark: family anchor = C05 (T200-40 / rate_only) for ALL hybrid
# configs.  Seam S3 for the ROT arms (no stock path exists): the prereg pins
# "R16 metrics verbatim" without a ROT-specific mapping; T200-40 is the
# prereg's own family anchor.  Listed in report as pending adjudication.
B1 = r16_metrics["configs"]["C05"]
B1_PATH_NAME = r16_config["configs"]["C05"]["path"]
assert B1["b1m_variant"].startswith("rate_only"), B1["b1m_variant"]

# === 1. calendar & signal days (P3R2 verbatim) ===============================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()   # includes 2020-12-31 (expiry anchor)
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
assert sig_days and sig_days[-1] <= date(2020, 12, 31)
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]}; "
    "2020-12-31 dropped as signal, kept as expiry anchor)")
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}

# === 2. exposures (r16 verbatim, C05 path only) ==============================
log("== 2. exposures (T200-40) ==")
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
anchor_check = r16.t200_behavioral_anchor_check(index_close, calendar_full)
log(f"  t200 behavioral anchor check: {json.dumps(anchor_check)[:120]}")
exposures = r16.t200_month_end_exposures(index_close, calendar_full, sig_days)
log(f"  exposures[{sig_days[0]}]={exposures[sig_days[0]]:.2f} "
    f"[{sig_days[-1]}]={exposures[sig_days[-1]]:.2f}")

# === 3. pools (r16 verbatim) =================================================
log("== 3. pools (r16 build_history + signal_pools) ==")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
if True:
    bank_syms = sorted({s for t in sig_days
                        for s in pools_at[t]["ranked"]})
    bank = r16.PriceBank(hist, calendar_full, bank_syms)
    b1_sim = r16.simulate_r16(
        "B1-T200-40-rate_only-DEV", bank, calendar_full,
        DEV_START, sig_days, pools_at, exposures, K=0, fractional=True,
        fee_bands=r16.B1_FEE_SCHEDULE_RATE_ONLY)
    _bm = r16.segment_metrics(b1_sim, DEV_START, DEV_END, None,
                              fractional=True)
    if abs(_bm["net_cagr"] - B1["b1m_net_cagr"]) > 1e-9:
        _fail(f"B1m dev port-check mismatch net_cagr: {_bm['net_cagr']}"
              f" vs r16_metrics {B1['b1m_net_cagr']}")
    if abs(_bm["max_drawdown"] - B1["b1m_max_drawdown"]) > 1e-9:
        _fail(f"B1m dev port-check mismatch max_drawdown: "
              f"{_bm['max_drawdown']} vs r16_metrics "
              f"{B1['b1m_max_drawdown']}")
    _yr_ref = {int(k): v for k, v in
               B1["b1m_net_return_by_year"].items()}
    _yr_new = {int(k): v for k, v in
               _bm["net_return_by_year"].items()}
    if set(_yr_ref) != set(_yr_new) or any(
            abs(_yr_ref[k] - _yr_new[k]) > 1e-9
            for k in _yr_ref):
        _fail(f"B1m dev port-check by-year mismatch: "
              f"{_yr_new} vs {_yr_ref}")
    # known dev values pin (EU task spec): net +0.60% / maxDD -39.82%
    if round(_bm["net_cagr"], 4) != 0.0060 \
            or round(_bm["max_drawdown"], 4) != -0.3982:
        _fail(f"B1m dev known-value pin FAILED: "
              f"{_bm['net_cagr']}, {_bm['max_drawdown']}")
    log(f"  B1m dev port-check: reproduces r16_metrics to 1e-9 PASS; "
        f"known values +0.60%/-39.82% PIN PASS "
        f"({_bm['net_cagr']:+.6f}, {_bm['max_drawdown']:.6f})")
del hist
rank_of = {t: {s: i + 1 for i, s in enumerate(pools_at[t]["ranked"])}
           for t in sig_days}
panel_symbols = sorted({s for t in sig_days for s in pools_at[t]["ranked"]})
log(f"  pools at {sig_days[0]}: n={pools_at[sig_days[0]]['n']}; "
    f"union of ranked symbols: {len(panel_symbols)}")
check_budget("pools")

# === 4. C05 leg_log + consistency (P3R2 verbatim, C05 only) ==================
log("== 4. C05 leg_log + membership consistency ==")
leg_all = pl.read_parquet(R16_RUN / "leg_log.parquet").filter(
    pl.col("plan_date").is_in(sig_days))
dup = (leg_all.filter(pl.col("config_id") == "C05")
       .group_by("config_id", "plan_date", "symbol").len()
       .filter(pl.col("len") > 1))
if dup.height:
    _fail(f"leg_log C05 has duplicate (config, plan_date, symbol): {dup.head(3)}")
me = pl.read_parquet(R16_RUN / "membership_events.parquet").filter(
    pl.col("signal").is_in(sig_days))
LEGS: dict = {}
OUTCOME: dict = {}
PANEL_C05: set = set()
for _k, _g in leg_all.filter(pl.col("config_id") == "C05") \
        .partition_by(["config_id", "plan_date"], as_dict=True).items():
    LEGS[_k[1]] = _g
    PANEL_C05.update(_g["symbol"].to_list())
    for _s, _o in zip(_g["symbol"].to_list(), _g["outcome"].to_list()):
        OUTCOME[(_k[1], _s)] = _o
me_by = {(r["config_id"], r["signal"]): r for r in me.iter_rows(named=True)
         if r["config_id"] == "C05"}
spec_c05 = r16_config["configs"]["C05"]
K_C05 = int(spec_c05["K"])
mismembers, mismev = 0, 0
prev: list[str] = []
for t in sig_days:
    g = LEGS.get(t)
    kinds = {} if g is None else dict(zip(g["symbol"].to_list(),
                                          g["kind"].to_list()))
    members = sorted(s for s, k in kinds.items()
                     if k in ("buy_open", "rescale"))
    exp_members, info = r16.buffer_membership(
        prev, pools_at[t]["ranked"], pools_at[t]["q5"],
        K_C05, spec_c05["filter"] == "on")
    if members != sorted(exp_members):
        mismembers += 1
    ev = me_by.get(t)
    if ev is not None:
        if (ev["n_kept"] != info["n_kept"] or ev["n_entrants"] != info["n_entrants"]
                or ev["n_prev"] != info["n_prev"] or ev["n_left"] != info["n_left"]
                or ev["n_cash_seats"] != info["n_cash_seats"]):
            mismev += 1
    prev = list(exp_members)
consistency_c05 = {"membership_mismatches": mismembers,
                   "membership_events_mismatches": mismev,
                   "n_signal_days": len(sig_days)}
log(f"  C05: membership mismatches={mismembers}, events mismatches={mismev} "
    f"/ {len(sig_days)}")
if mismembers or mismev:
    _fail(f"C05 consistency FAILED: {consistency_c05}")
check_budget("consistency")

# === 5. market frames (P3R2 verbatim) ========================================
log("== 5. market frames ==")
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
pins["daily"].update({"rows_total": daily_meta["rows_total"],
                      "rows_after_freeze_filter": daily_meta["rows_after_freeze_filter"]})
daily = (daily_full.filter(pl.col("symbol").is_in(panel_symbols))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .select("symbol", "date", "open", "high", "low", "close", "tradestatus")
         .sort("symbol", "date"))
del daily_full
assert_frozen(daily, "date", "daily")
log(f"  daily panel: {daily.height} rows, {daily['symbol'].n_unique()} symbols")

parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
if not parts:
    _fail("no halfday partitions")
half_parts, half_rows_total = [], 0
for part in parts:
    f = pl.read_parquet(part)
    half_rows_total += f.height
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= DEV_START)
                 & (pl.col("trade_date") <= DEV_END))
    f = f.filter(pl.col("symbol").is_in(panel_symbols))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame()
del half_parts
assert_frozen(half, "trade_date", "halfday")
pins["halfday_rows_total"] = half_rows_total
if half_rows_total != 18_486_939:
    _fail(f"halfday rows {half_rows_total} != pinned 18,486,939")
log(f"  halfday: {half.height} rows kept of {half_rows_total} total "
    f"(panel x dev), {half['symbol'].n_unique()} symbols")

limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})  # ENGINE-2 bridge
limits = (limits_full.filter(pl.col("symbol").is_in(panel_symbols))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
          .sort("symbol", "date"))
LIMIT_DAYS = set(zip(limits["symbol"].to_list(), dints(limits["date"])))
del limits_full
log(f"  limits: {limits.height} rows (dev x panel)")
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(panel_symbols))
dividends = divs_all.filter(pl.col("symbol").is_in(panel_symbols))
log(f"  splits {splits.height} rows, dividends {dividends.height} rows (panel)")
instruments = pl.DataFrame({
    "symbol": panel_symbols, "is_etf": [False] * len(panel_symbols),
    "is_t0": [False] * len(panel_symbols)})
check_budget("market frames")
log(f"  rss after frames: {rss_gb():.2f} GB")

# === 6. ETF assets (panel / factors / dividends / meta / synthetic bars) =====
log("== 6. ETF assets ==")
etf_panel_full = pl.read_parquet(ETF_DAILY)
etf_panel = (etf_panel_full.filter(pl.col("symbol").is_in(PANEL_SYMS))
             .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
             .sort("symbol", "date"))
etf_panel45 = (etf_panel_full.filter(pl.col("symbol").is_in(EU45_SYMS))
               .filter((pl.col("date") >= DEV_START)
                       & (pl.col("date") <= DEV_END))
               .sort("symbol", "date"))
_n2025 = etf_panel_full.filter(pl.col("date") >= date(2025, 1, 1)).height
if _n2025:
    _fail(f"input parquet has {_n2025} rows on/after 2025-01-01 "
          "(2025+ freeze breach)")
log(f"  input parquet 2025+ rows: {_n2025} (freeze check PASS)")
del etf_panel_full
assert_frozen(etf_panel, "date", "etf_daily")
per_member = {r["symbol"]: r["len"] for r in
              etf_panel.group_by("symbol").len().iter_rows(named=True)}
log(f"  etf panel dev rows: {etf_panel.height} per member {per_member}")
if set(per_member) != set(PANEL_SYMS):
    _fail(f"etf panel member coverage broken: {sorted(per_member)}")

# --- pre-run assertion (ii): precover nulls -------------------------------
n_null_preclose = int(etf_panel.filter(pl.col("preclose").is_null()).height)
ASSERT_II_NULLS = n_null_preclose
log(f"  assertion (ii) preclose nulls: {n_null_preclose}")
if n_null_preclose:
    _fail("runner assertion (ii) FAILED: preclose nulls in member-dev panel")
n_zero_vol = int(etf_panel.filter(pl.col("volume") <= 0).height)
log(f"  disclosure: member-dev rows with volume<=0: {n_zero_vol}")

# --- pre-run assertion (iii): pure-ETF panel dates == SSE calendar --------
cal_tc = pl.read_csv(
    sorted(TRADECAL_DIR.glob("chunk_exchange-SSE_*.csv"))[0])
cal_tc = cal_tc.filter((pl.col("is_open") == 1)
                       & (pl.col("cal_date") >= int(DEV_START.strftime("%Y%m%d")))
                       & (pl.col("cal_date") <= int(DEV_END.strftime("%Y%m%d"))))
sse_days = set(cal_tc["cal_date"].to_list())
panel_days = set(dints(etf_panel["date"]).tolist())
miss = sorted(sse_days - panel_days)
extra = sorted(panel_days - sse_days)
log(f"  assertion (iii): sse {len(sse_days)} days, panel union "
    f"{len(panel_days)} days, missing {miss[:5]}, extra {extra[:5]}")
ASSERT_III_TEXT = f"PASS ({len(panel_days)} == {len(sse_days)})"
if miss or extra:
    _fail(f"runner assertion (iii) FAILED: missing {miss[:5]} extra {extra[:5]}")

# --- adj factor join per panel symbol (momentum members + leg 159934) -------
factor_map: dict[str, dict[int, float]] = {}
factor_gaps: dict[str, int] = {}
for m in PANEL_SYMS:
    code = m.split(".")[1] + "." + m.split(".")[0].upper()
    chunk = FUND_ADJ_DIR / f"chunk_{code}.csv"
    if not chunk.exists():
        _fail(f"fund_adj chunk missing for {m}: {chunk}")
    f = pl.read_csv(chunk, schema_overrides={"trade_date": pl.Int64,
                                             "adj_factor": pl.Float64})
    f = f.filter((pl.col("trade_date") >= dint_of(DEV_START))
                 & (pl.col("trade_date") <= dint_of(DEV_END))).sort("trade_date")
    factor_map[m] = dict(zip(f["trade_date"].to_list(),
                             f["adj_factor"].to_list()))
    need = set(int(x) for x in dints(etf_panel.filter(
        pl.col("symbol") == m)["date"]))
    factor_gaps[m] = len(need - set(factor_map[m]))
log(f"  factor coverage gaps per member: {factor_gaps}")
if any(v for v in factor_gaps.values()):
    _fail(f"fund_adj does not cover every member-dev panel day: {factor_gaps}")

# --- dividend events (frozen rule; assert == 18) ----------------------------
det = pl.read_csv(MISMATCH_CSV)
if det.schema["date"] != pl.Date:
    det = det.with_columns(pl.col("date").str.to_date("%Y-%m-%d"))
det8 = det.filter(pl.col("symbol").is_in(MEMBERS)).filter(
    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
div_rows = []
for r in det8.iter_rows(named=True):
    m = r["symbol"]
    fmap = factor_map[m]
    dd = dint_of(r["date"])
    # factor ratio vs the previous TRADED session of that member
    sub = etf_panel.filter(pl.col("symbol") == m)
    prev_days = [x for x in dints(sub["date"]) if x < dd]
    if not prev_days:
        continue
    d_prev = max(prev_days)
    if dd not in fmap or d_prev not in fmap:
        continue
    ratio = fmap[dd] / fmap[d_prev]
    if (r["preclose"] < r["prev_close"]) and (1.0 < ratio <= 1.06):
        div_rows.append({"symbol": m, "date": r["date"],
                         "div_per_share": float(r["prev_close"]) - float(r["preclose"]),
                         "factor_ratio": ratio})
dividend_events = pl.DataFrame(div_rows, schema={
    "symbol": pl.String, "date": pl.Date, "div_per_share": pl.Float64,
    "factor_ratio": pl.Float64}).drop("factor_ratio").sort("symbol", "date")
counts = Counter(dividend_events["symbol"].to_list())
log(f"  dividend events built: {dividend_events.height} {dict(counts)}")
for r in dividend_events.iter_rows(named=True):
    log(f"    {r['symbol']} {r['date']} div/share={r['div_per_share']:.3f}")
if dict(counts) != DIVIDEND_EXPECT or dividend_events.height != 18:
    _fail(f"dividend events != frozen expectation {DIVIDEND_EXPECT}: {counts}")

# --- 159934 (v2 leg-only): dividend rule scan + frozen non-modeling check ---
# Frozen v2 spec: 159934 has NO modeled corporate action in dev; its single
# known event is the 2020-02-26 no-jump micro deviation (-0.22%), disclosed.
leg_div_rows = []
leg_scan = det.filter(pl.col("symbol") == "sz.159934").filter(
    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
LEG_DEVIATIONS: list[dict] = []
for r in leg_scan.iter_rows(named=True):
    m = r["symbol"]
    fmap = factor_map[m]
    dd = dint_of(r["date"])
    sub = etf_panel.filter(pl.col("symbol") == m)
    prev_days = [x for x in dints(sub["date"]) if x < dd]
    if not prev_days:
        continue
    d_prev = max(prev_days)
    if dd not in fmap or d_prev not in fmap:
        continue
    ratio = fmap[dd] / fmap[d_prev]
    rel = float(r["preclose"]) / float(r["prev_close"]) - 1.0
    LEG_DEVIATIONS.append({"symbol": m, "date": str(r["date"]),
                           "preclose": float(r["preclose"]),
                           "prev_close": float(r["prev_close"]),
                           "rel_diff": rel, "factor_ratio": ratio})
    if (r["preclose"] < r["prev_close"]) and (1.0 < ratio <= 1.06):
        leg_div_rows.append(r)
if leg_div_rows:
    _fail(f"159934 dividend-rule events found in dev ({len(leg_div_rows)}) "
          "-- contradicts the frozen spec (0 modeled events); STOP, spec seam")
log(f"  159934 dev mismatch rows: {len(LEG_DEVIATIONS)} "
    f"{json.dumps(LEG_DEVIATIONS)}; dividend-rule events: 0 (frozen)")

# --- EU45 panel identity: 45-symbol data panel for EU-01..10 ---------------
EU45_NULLS = int(etf_panel45.filter(pl.col("preclose").is_null()).height)
log(f"  EU45 panel: {etf_panel45.height} dev rows, "
    f"{etf_panel45['symbol'].n_unique()} symbols; preclose nulls "
    f"{EU45_NULLS}")
if EU45_NULLS:
    _fail("EU45 panel has preclose nulls")
per45 = {r["symbol"]: r["len"] for r in
         etf_panel45.group_by("symbol").len().iter_rows(named=True)}
if set(per45) != set(EU45_SYMS):
    _fail(f"EU45 panel member coverage broken: missing "
          f"{sorted(set(EU45_SYMS) - set(per45))}")
panel_days45 = set(dints(etf_panel45["date"]).tolist())
miss45 = sorted(sse_days - panel_days45)
extra45 = sorted(panel_days45 - sse_days)
if miss45 or extra45:
    _fail(f"EU45 calendar assertion FAILED: missing {miss45[:5]} "
          f"extra {extra45[:5]}")
log(f"  EU45 calendar union == SSE dev calendar "
    f"({len(panel_days45)} days) PASS")

factor_map45: dict[str, dict[int, float]] = {}
factor_gaps45: dict[str, int] = {}
for m in EU45_SYMS:
    code = m.split(".")[1] + "." + m.split(".")[0].upper()
    chunk = FUND_ADJ_DIR / f"chunk_{code}.csv"
    if not chunk.exists():
        _fail(f"fund_adj chunk missing for EU45 {m}: {chunk}")
    f = pl.read_csv(chunk, schema_overrides={"trade_date": pl.Int64,
                                             "adj_factor": pl.Float64})
    f = f.filter((pl.col("trade_date") >= dint_of(DEV_START))
                 & (pl.col("trade_date") <= dint_of(DEV_END)))
    f = f.sort("trade_date")
    factor_map45[m] = dict(zip(f["trade_date"].to_list(),
                               f["adj_factor"].to_list()))
    need = set(int(x) for x in dints(etf_panel45.filter(
        pl.col("symbol") == m)["date"]))
    factor_gaps45[m] = len(need - set(factor_map45[m]))
if any(v for v in factor_gaps45.values()):
    _fail(f"fund_adj does not cover every EU45 member-dev panel day: "
          f"{factor_gaps45}")
log(f"  EU45 factor coverage: zero gaps over {len(EU45_SYMS)} symbols PASS")

# EU45 dividend events: v3 frozen extraction rule applied verbatim to 45
det45 = det.filter(pl.col("symbol").is_in(EU45_SYMS)).filter(
    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
div_rows45 = []
for r in det45.iter_rows(named=True):
    m = r["symbol"]
    fmap = factor_map45[m]
    dd = dint_of(r["date"])
    sub = etf_panel45.filter(pl.col("symbol") == m)
    prev_days = [x for x in dints(sub["date"]) if x < dd]
    if not prev_days:
        continue
    d_prev = max(prev_days)
    if dd not in fmap or d_prev not in fmap:
        continue
    ratio = fmap[dd] / fmap[d_prev]
    if (r["preclose"] < r["prev_close"]) and (1.0 < ratio <= 1.06):
        div_rows45.append({"symbol": m, "date": r["date"],
                           "div_per_share": float(r["prev_close"])
                                            - float(r["preclose"]),
                           "factor_ratio": ratio})
dividend_events45 = pl.DataFrame(div_rows45, schema={
    "symbol": pl.String, "date": pl.Date, "div_per_share": pl.Float64,
    "factor_ratio": pl.Float64}).drop("factor_ratio").sort("symbol", "date")
counts45 = Counter(dividend_events45["symbol"].to_list())
EU45_NEW_DIV = {s: c for s, c in counts45.items() if s not in MEMBERS}
log(f"  EU45 dividend events: {dividend_events45.height} total; "
    f"new-member counts {EU45_NEW_DIV}")
_eu_anchor_subset = dividend_events45.filter(
    pl.col("symbol").is_in(MEMBERS))
if not _eu_anchor_subset.equals(dividend_events):
    _fail("EU45 dividend subset(MEMBERS) != frozen anchor 18 events")

SYMBOL_META45 = {m: {"asset_class": "etf", "band": 0.10, "t_plus": 0}
                 for m in EU45_SYMS}
assert all(v["band"] == 0.10 and v["t_plus"] == 0
           for v in SYMBOL_META45.values())

# --- symbol_meta (explicit bands for ALL 9; assertion (i) basis) ------------
SYMBOL_META = {m: {"asset_class": "etf", "band": MEMBER_BAND[m],
                   "t_plus": 0} for m in PANEL_SYMS}
assert all("band" in v for v in SYMBOL_META.values())
log("  symbol_meta: 9 symbols (8 members + sz.159934), explicit band 0.10, "
    "t_plus 0 (assertion (i) basis)")

# --- synthetic single-pm-session bars (contract sec 8.1; test h1 convention)
def etf_pm_bars(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("symbol"), pl.col("date").alias("trade_date"),
        pl.lit("pm", dtype=pl.String).alias("session"),
        pl.col("open"), pl.col("high"), pl.col("low"), pl.col("close"))

check_budget("etf assets")

# === 7. momentum & rotation ranking (adj closes, frozen lookbacks) ===========
log("== 7. momentum ranking (adj close, month-end) ==")
adj_close: dict[str, dict[int, float]] = {}
for m in MEMBERS:
    fmap = factor_map[m]
    sub = etf_panel.filter(pl.col("symbol") == m)
    ac = {}
    rows = sub.select(
        (pl.col("date").dt.year().cast(pl.Int64) * 10_000
         + pl.col("date").dt.month().cast(pl.Int64) * 100
         + pl.col("date").dt.day().cast(pl.Int64)).alias("dint"),
        "close")
    for r in rows.iter_rows(named=True):
        ac[int(r["dint"])] = float(r["close"]) * fmap[int(r["dint"])]
    adj_close[m] = ac


for m in EU45_SYMS:
    if m in adj_close:
        continue
    fmap = factor_map45[m]
    sub = etf_panel45.filter(pl.col("symbol") == m)
    ac = {}
    rows = sub.select(
        (pl.col("date").dt.year().cast(pl.Int64) * 10_000
         + pl.col("date").dt.month().cast(pl.Int64) * 100
         + pl.col("date").dt.day().cast(pl.Int64)).alias("dint"),
        "close")
    for r in rows.iter_rows(named=True):
        ac[int(r["dint"])] = float(r["close"]) * fmap[int(r["dint"])]
    adj_close[m] = ac
log(f"  adj_close extended to EU45 ({len(adj_close)} symbols)")


def month_shift(d: date, k: int) -> date | None:
    y, mo = d.year, d.month - k
    while mo <= 0:
        mo += 12
        y -= 1
    c = [x for x in sig_days_dev if (x.year, x.month) == (y, mo)]
    return c[0] if c else None


# v2 S2 fix: ranking universes are PER-CONFIG (leg symbols removed); the
# frozen 8-member set itself is unchanged.  RANKING_UNI[(lb, uni_key)] holds
# the monthly ranking for each distinct (lookback, universe) pair.
RANKING_UNI: dict[tuple[int, str], dict[date, list[str]]] = {}


def ranking_for(lb: int, universe: list[str]) -> dict[date, list[str]]:
    key = (lb, "+".join(universe))
    if key in RANKING_UNI:
        return RANKING_UNI[key]
    hist_lb: dict[date, list[str]] = {}
    for T in sig_days:
        T0d = month_shift(T, lb)
        if T0d is None:
            continue            # first `lookback` months: no rotation (pinned)
        scores = {}
        for m in universe:
            a0 = adj_close[m].get(dint_of(T0d))
            a1 = adj_close[m].get(dint_of(T))
            if not a0 or not a1:
                scores = None
                break
            scores[m] = a1 / a0 - 1.0
        if scores is None:
            continue
        hist_lb[T] = sorted(scores, key=lambda m: (-scores[m], m))
    RANKING_UNI[key] = hist_lb
    return hist_lb


for lb in sorted({int(c["rotation"]["lookback_m"]) for c in CFGS.values()
                  if c["rotation"]}):
    uni_keys = {"+".join(c["rotation"]["universe"]) for c in CFGS.values()
                if c["rotation"] and int(c["rotation"]["lookback_m"]) == lb}
    for uk in uni_keys:
        h = ranking_for(lb, uk.split("+"))
        log(f"  lookback {lb}m universe[{uk}]: {len(h)} ranking months "
            f"({min(h)}..{max(h)})" if h else
            f"  lookback {lb}m universe[{uk}]: EMPTY")
if not RANKING_UNI:
    _fail("momentum ranking empty")

# === 8. static intent frames =================================================
log("== 8. static intent frames ==")
N_SKIPPED: dict = {}


def build_c05_frame() -> pl.DataFrame:
    """P3R2 build_intent_frame('C05') rebuilt verbatim (semantics unchanged)."""
    rows: list[dict] = []
    skipped = {"r16_at_target": 0, "r16_feemin_skipped": 0}
    for T in sig_days:
        g = LEGS.get(T)
        if g is None:
            continue
        w_T = float(exposures[T]) / K_C05
        Tp = next_sig.get(T)
        expiry = (date(Tp.year, Tp.month, Tp.day) if Tp is None else
                  date.fromordinal(Tp.toordinal() + 1))
        for sym, kind in zip(g["symbol"].to_list(), g["kind"].to_list()):
            oc = OUTCOME.get((T, sym))
            if kind == "rescale" and oc in ("at_target", "feemin_skipped"):
                skipped["r16_at_target" if oc == "at_target"
                        else "r16_feemin_skipped"] += 1
                continue
            rank = rank_of[T].get(sym, 10 ** 6)
            if kind == "sell_full":
                rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": rank,
                             "expiry_date": expiry, "target_weight": None})
            elif kind == "buy_open":
                rows.append({"symbol": sym, "side": "buy", "intent": "",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": rank,
                             "expiry_date": expiry, "target_weight": w_T})
            else:  # rescale -> standing reduce-to-target risk sell
                rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": rank,
                             "expiry_date": expiry, "target_weight": w_T})
    N_SKIPPED["C05"] = skipped
    return pl.DataFrame(rows, schema=INTENT_SCHEMA)


def leg_intent_rows(legs: dict[str, float]) -> list[dict]:
    """Pinned leg conventions: initial park buy at the FIRST signal day
    (expiry = 4th signal day + 1), monthly reduce-to-target risk sells from
    the second signal day (expiry = next signal day + 1; same-name monthly
    override resets K).  Seam S1: source_signal of the park buy is the park
    decision date (engine requires date-typed source)."""
    rows: list[dict] = []
    park_T = sig_days[0]
    park_expiry = date.fromordinal(sig_days[3].toordinal() + 1)
    for sym, w in legs.items():
        rows.append({"symbol": sym, "side": "buy", "intent": "",
                     "decision_date": park_T, "decision_session": "pm",
                     "source_signal": PARK_SOURCE, "priority": 10 ** 6,
                     "expiry_date": park_expiry, "target_weight": float(w)})
        for T in sig_days[1:]:
            Tp = next_sig.get(T)
            expiry = date.fromordinal(Tp.toordinal() + 1)
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": 10 ** 6,
                         "expiry_date": expiry, "target_weight": float(w)})
    return rows


def rotation_intent_rows(cid: str, rot: dict) -> tuple[list[dict], list[dict]]:
    """Pinned rotation conventions (v2 S2 fix): month-end T momentum ranking
    over the CONFIG'S universe (leg symbols REMOVED; 7 or 6 members; the
    frozen member set and band table are unchanged); exits =
    topN(prev)\\topN(T) sell_full risk; entries = topN(T)\\topN(prev) buy clip
    weight 0.25; expiry = next signal day + 1.  Stateless (ranking sets, not
    filled positions)."""
    lb = int(rot["lookback_m"])
    top_n = int(rot["top_n"])
    w = float(rot["weight"])
    universe = list(rot["universe"])
    assert len(set(universe)) == len(universe)
    assert not (set(universe) & set(CFGS[cid]["legs"])), \
        f"{cid}: S2 fix violated -- leg symbol inside ranking universe"
    hist_lb = ranking_for(lb, universe)
    months = sorted(hist_lb)
    rows: list[dict] = []
    rot_log = []
    prev_top: set | None = None
    for T in months:
        top = set(hist_lb[T][:top_n])
        Tp = next_sig.get(T)
        expiry = date.fromordinal(Tp.toordinal() + 1) if Tp else T
        if prev_top is not None:
            for sym in sorted(prev_top - top):
                rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": 10 ** 6,
                             "expiry_date": expiry, "target_weight": None})
            rank_in_top = {s: i + 1 for i, s in enumerate(hist_lb[T][:top_n])}
            for sym in sorted(top - prev_top):
                rows.append({"symbol": sym, "side": "buy", "intent": "",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T,
                             "priority": 10 ** 6 + rank_in_top[sym],
                             "expiry_date": expiry, "target_weight": w})
        rot_log.append({"month": str(T), "top": sorted(top),
                        "entries": sorted(top - (prev_top or set())),
                        "exits": sorted((prev_top or set()) - top)})
        prev_top = top
    # S2 fix verification: leg symbols must never enter/exit the rotation
    leg_touch = sorted({s for e in rot_log
                        for s in e["entries"] + e["exits"]
                        if s in CFGS[cid]["legs"]})
    if leg_touch:
        _fail(f"{cid}: S2 fix violated -- leg symbols {leg_touch} appear in "
              "rotation entries/exits")
    return rows, rot_log


ROT_LOG: dict = {}
FRAMES: dict = {}
BLOCKED: dict = {}
frame_report: dict = {}


def assert_frame_unique(cid: str, rows: list[dict]) -> dict:
    """m5-b: (symbol, side, source) uniqueness; PLUS the engine's own
    first-decision (symbol, d, s) uniqueness (any same-symbol pair with the
    identical first decision point is rejected by _validate_intents).
    Violations are NOT silently resolved: they block the config (seam S2)."""
    keys = [(r["symbol"], r["side"], r["source_signal"]) for r in rows]
    dup_m5b = sorted({k for k in keys if keys.count(k) > 1})
    firsts = [(r["symbol"], r["decision_date"], r["decision_session"])
              for r in rows]
    dup_first = sorted({k for k in firsts if firsts.count(k) > 1})
    return {"m5b_duplicates": dup_m5b, "first_decision_duplicates": dup_first}


C05_FRAME = build_c05_frame()
FRAMES["C05"] = C05_FRAME
log(f"  C05 (stock leg): intents {C05_FRAME.height}; R16 skips {N_SKIPPED['C05']}")
# verbatim fidelity check against the P3R2 C05 intents artifact
c05_ref = pl.read_parquet(P3R2_RUN / "outputs/C05_intents.parquet")
if not C05_FRAME.equals(c05_ref):
    _fail("rebuilt C05 intent frame != P3R2 C05_intents.parquet (.equals)")
log("  C05 frame == P3R2 C05_intents.parquet (.equals) PASS")

for cid in CONFIG_IDS:
    cfg = CFGS[cid]
    rows: list[dict] = []
    if cfg["stock"]:
        rows.extend(C05_FRAME.to_dicts())
    rows.extend(leg_intent_rows(cfg["legs"]))
    rot_log = None
    if cfg["rotation"]:
        r_rows, rot_log = rotation_intent_rows(cid, cfg["rotation"])
        rows.extend(r_rows)
    chk = assert_frame_unique(cid, rows)
    if chk["m5b_duplicates"] or chk["first_decision_duplicates"]:
        # v2 prereg: the S2 fix (leg symbols outside the ranking universe)
        # makes the collision STRUCTURALLY impossible; a duplicate here means
        # the frozen spec's fix claim is wrong -- STOP, no silent resolution.
        _fail(f"{cid}: m5-b/first-decision duplicates after the frozen S2 fix "
              f"-- spec seam, STOP for adjudication: {chk}")
    fr = pl.DataFrame(rows, schema=INTENT_SCHEMA)
    FRAMES[cid] = fr
    n_leg = int(fr.filter(pl.col("symbol").is_in(PANEL_SYMS)).height)
    frame_report[cid] = {"intents": fr.height, "etf_intents": n_leg,
                         "stock_intents": fr.height - n_leg}
    ROT_LOG[cid] = rot_log
    log(f"  {cid}: intents {fr.height} (etf {n_leg}, stock {fr.height - n_leg});"
        " m5-b + first-decision uniqueness PASS; S2 disjointness PASS")
check_budget("intent frames")

# === 9. pre-run assertions summary + config input frames =====================
log("== 9. per-config engine input frames ==")
EMPTY_LIMITS = pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                                    "limit_up": pl.Float64,
                                    "limit_down": pl.Float64})
EMPTY_SPLITS = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                                    "split_factor": pl.Float64})
EMPTY_DIVS = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                                  "cash_per_lot_pre_tax": pl.Float64,
                                  "round_lot": pl.Int64})
EMPTY_INSTR = pl.DataFrame(schema={"symbol": pl.String, "is_etf": pl.Boolean,
                                   "is_t0": pl.Boolean})

cfg_syms_stock = sorted(PANEL_C05)
daily_c = (daily.filter(pl.col("symbol").is_in(cfg_syms_stock))
           .filter(pl.col("date") <= DEV_END))
half_c = (half.filter(pl.col("symbol").is_in(cfg_syms_stock))
          .filter(pl.col("trade_date") <= DEV_END))
limits_c = (limits.filter(pl.col("symbol").is_in(cfg_syms_stock))
            .filter(pl.col("date") <= DEV_END))
splits_c = splits.filter(pl.col("symbol").is_in(cfg_syms_stock))
divs_c = dividends.filter(pl.col("symbol").is_in(cfg_syms_stock))
instr_c = instruments.filter(pl.col("symbol").is_in(cfg_syms_stock))
log(f"  stock frames (C05 universe): daily {daily_c.height}, half "
    f"{half_c.height}, limits {limits_c.height}")

# hybrid stock+ETF panel: stock rows gain a null preclose column; ETF rows
# gain tradestatus=1.0 (dtype-matched).  H2-A0 itself uses the PURE P3R2
# frames above (byte-level anchor -- no added columns).
stock_preclose = daily_c.with_columns(
    pl.lit(None, dtype=pl.Float64).alias("preclose"))
etf_ts_dtype = daily_c.schema["tradestatus"]
etf_panel_ts = etf_panel.with_columns(
    pl.lit(1.0, dtype=etf_ts_dtype).alias("tradestatus"))
etf_bars = etf_pm_bars(etf_panel_ts)
etf_panel45_ts = etf_panel45.with_columns(
    pl.lit(1.0, dtype=etf_ts_dtype).alias("tradestatus"))
etf_bars45 = etf_pm_bars(etf_panel45_ts)


HALF_COLS = ["symbol", "trade_date", "session", "open", "high", "low", "close"]


def mixed_frames(used: set[str]) -> dict:
    etf_p = etf_panel_ts.filter(pl.col("symbol").is_in(used))
    mix_daily = (pl.concat([
        stock_preclose.select("symbol", "date", "open", "high", "low",
                              "close", "tradestatus", "preclose"),
        etf_p.select("symbol", "date", "open", "high", "low", "close",
                     "tradestatus", "preclose")])
        .sort("symbol", "date"))
    mix_half = pl.concat([half_c.select(HALF_COLS),
                          etf_pm_bars(etf_p).select(HALF_COLS)],
                         how="vertical")
    return {"daily": mix_daily, "half": mix_half, "limits": limits_c,
            "splits": splits_c, "dividends": divs_c, "instruments": instr_c}


def etf_only_frames() -> dict:
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
            "instruments": EMPTY_INSTR}


INPUTS: dict = {}
for cid in CONFIG_IDS:
    if cid not in FRAMES:
        continue
    cfg = CFGS[cid]
    if cfg["stock"]:
        used = set(cfg["legs"])
        INPUTS[cid] = {**mixed_frames(used), "meta": SYMBOL_META,
                       "events": dividend_events, "mode": "mixed"}
    else:
        if cid == "EU-A0":
            _fr, _mt, _dv = etf_only_frames(), SYMBOL_META, dividend_events
        else:
            assert set(CFGS[cid]["rotation"]["universe"]) <= set(EU45_SYMS), cid
            _fr, _mt, _dv = (etf_only_frames45(), SYMBOL_META45,
                             dividend_events45)
        INPUTS[cid] = {**_fr, "meta": _mt, "events": _dv,
                       "mode": "etf_only"}

# === 10. EU-A0 regression anchor vs v3 R3-06 ===============================
log("== 10. EU-A0 regression anchor vs v3 R3-06 ==")
results: dict = {}


def run_one(cid: str) -> dict:
    inp = INPUTS[cid]
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(
        FRAMES[cid], inp["daily"], inp["half"], inp["limits"],
        inp["splits"], inp["dividends"], inp["instruments"],
        symbol_meta=inp["meta"], dividend_events=inp["events"],
        initial_cash=200_000.0)
    wall = time.perf_counter() - t_cfg
    il = res.stats.get("intent_layer") or {}
    log(f"  {cid}: engine {wall:.1f}s, intents {il.get('n_intents')} "
        f"orders {il.get('orders_generated')} filled {il.get('stopped_filled')} "
        f"cap {il.get('terminated_cap')} | rss {rss_gb():.2f} GB")
    # assertion (i): explicit-band meta -> no defaulted band symbols
    if inp["meta"] is not None:
        defaulted = res.stats["etf_leg"]["etf_default_band_symbols"]
        if defaulted:
            _fail(f"runner assertion (i) FAILED for {cid}: "
                  f"etf_default_band_symbols = {defaulted}")
    check_budget(f"{cid} engine run")
    return {"res": res, "wall_s": wall, "warnings": list(res.warnings)}


# EU-A0 regression: 5-frame .equals vs the v3 run's R3-06 outputs +
# net_cagr must equal the v3 metric (EU-A0 is NOT re-adjudicated);
# engine v1.3 fail-closed guards (e.g. dividend misclassification) stop
# the round -- no data repair (EU prereg sec 4-3)
try:
    results["EU-A0"] = run_one("EU-A0")
except Exception as _e:
    _fail(f"EU-A0: engine raised {_e.__class__.__name__}: {_e} "
          "(engine v1.3 fail-closed guard; no data repair)")
r0 = results["EU-A0"]["res"]
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
for name, mine in (("intents", FRAMES["EU-A0"]), ("fills", r0.fills),
                   ("events", r0.events), ("daily", r0.daily),
                   ("clips_final", r0.clips_final)):
    same = mine.equals(ref[name])
    regression[name] = same
    log(f"  EU-A0 {name}.equals(v3 R3-06 {name}) = {same} "
        f"(mine {mine.height} rows / ref {ref[name].height} rows)")
regression["net_cagr_matches_v3_metrics"] = \
    abs(_cagr0 - v3_r306["net_cagr"]) <= 1e-12
log(f"  EU-A0 net_cagr {_cagr0:.10f} vs v3 R3-06 "
    f"{v3_r306['net_cagr']:.10f} -> "
    f"{regression['net_cagr_matches_v3_metrics']}")
if not all(regression.values()):
    _fail(f"EU-A0 REGRESSION FAILURE: {regression} -- abort the whole round "
          "with zero conclusions per EU prereg sec 4-1 (EU-A0 != v3 R3-06)")
log("  EU-A0 regression anchor PASS (== v3 R3-06, 5/5 frames .equals)")

# === 11. remaining configs ====================================================
log("== 11. remaining configs ==")
for cid in [c for c in CONFIG_IDS if c != "EU-A0" and c in FRAMES]:
    try:
        results[cid] = run_one(cid)
    except Exception as _e:
        _fail(f"{cid}: engine raised {_e.__class__.__name__}: {_e} "
              "(engine v1.3 fail-closed guard; no data repair)")
check_budget("all engine runs")

# leg structural check (v2 S4 fix verification): every leg intent must be
# cap-clean (all legs <= 25%, so a construction-cap void would contradict the
# frozen spec -> STOP).  Leg weight drift breaches are engine-recorded only
# (never trimmed) and stay a disclosure.
leg_struct_check: dict = {}
for cid in [c for c in CONFIG_IDS if CFGS[c]["legs"] and c in results]:
    res = results[cid]["res"]
    leg_syms = set(CFGS[cid]["legs"])
    lc = res.stats["intent_layer"]["terminated_cap"]
    # which intents were cap-terminated (from lifecycle events)?
    cap_syms: set = set()
    for r in res.events.filter(pl.col("event") == "intent_lifecycle") \
                       .iter_rows(named=True):
        if ": cap_single_name" in (r["detail"] or ""):
            cap_syms.add((r["detail"].split("/", 1)[0],
                          r["detail"].split(" source ")[1].split(":")[0]))
    leg_cap = [k for k in cap_syms if k[0] in leg_syms]
    leg_struct_check[cid] = {"leg_cap_terminated": sorted(leg_cap),
                             "total_cap_terminated": lc,
                             "drift_breaches":
                                 res.stats["caps"]["single_name_drift_breaches"]}
    if leg_cap:
        _fail(f"{cid}: leg intents cap-voided {leg_cap} despite all legs "
              "<= 25% (frozen S4 fix) -- spec seam, STOP for adjudication")
    log(f"  {cid}: leg cap-voids 0 (OK); drift breaches "
        f"{leg_struct_check[cid]['drift_breaches']} (recorded-only)")

# === 12. per-intent attribution & execution columns (P3R2 verbatim) ==========
log("== 12. per-intent attribution ==")


def close_le_map(sym: str) -> tuple[np.ndarray, np.ndarray]:
    if sym in EU45_SYMS:
        rows = etf_panel45.filter(pl.col("symbol") == sym)
    elif sym in PANEL_SYMS:
        rows = etf_panel.filter(pl.col("symbol") == sym)
    else:
        rows = daily_c.filter((pl.col("symbol") == sym)
                              & (pl.col("tradestatus") != 0))  # P3R2 caliber
    return dints(rows["date"]), rows["close"].to_numpy().astype(np.float64)


CLOSE_ARR: dict = {}
for sym in set(cfg_syms_stock) | set(PANEL_SYMS) | set(EU45_SYMS):
    CLOSE_ARR[sym] = close_le_map(sym)


def close_le(sym: str, d: date) -> float | None:
    arr = CLOSE_ARR.get(sym)
    if arr is None:
        return None
    dint_a, cls = arr
    i = int(np.searchsorted(dint_a, dint_of(d), side="right")) - 1
    return float(cls[i]) if i >= 0 else None


split_events: dict[str, list[tuple[date, float]]] = {}
for r in splits.filter(pl.col("ex_date") <= DEV_END).iter_rows(named=True):
    split_events.setdefault(r["symbol"], []).append(
        (r["ex_date"], float(r["split_factor"])))
for v in split_events.values():
    v.sort()

RULE_OK = {"below_min_lot", "void_no_position", "void_insufficient_cash"}


def sidestr_class(sidestr: str) -> str:
    return "buy" if sidestr.startswith("buy") else "sell"


def attribute(cid: str) -> dict:
    res = results[cid]["res"]
    fr = FRAMES[cid]
    sources_by: dict = {}
    for r in fr.iter_rows(named=True):
        sources_by.setdefault((r["symbol"], r["side"]), []).append(
            (r["source_signal"], r["decision_session"]))
    src_cache: dict = {}

    def src_of(sym: str, side: str, d, s: str):
        key = (sym, side, dint_of(d), s)
        if key in src_cache:
            return src_cache[key]
        lst = sources_by.get((sym, side), [])
        best = None
        for T, first_s in lst:
            if T < d or (T == d and first_s == "pm" and s == "pm"):
                if best is None or T > best:
                    best = T
        src_cache[key] = best
        return best

    lifecycle: dict = {}
    for r in res.events.filter(pl.col("event") == "intent_lifecycle") \
                       .iter_rows(named=True):
        try:
            left, rest = r["detail"].split(" source ", 1)
            iso, reason = rest.split(": ", 1)
            src = date.fromisoformat(iso)
        except Exception:
            _fail(f"{cid}: unparsable intent_lifecycle detail {r['detail']!r}")
        sym, sidestr = left.split("/", 1)[0], left.split("/", 1)[1]
        lifecycle[(sym, sidestr_class(sidestr), src)] = reason
    ev_orders = res.events.filter(pl.col("order_id") != "")
    per_intent_events: dict = {}
    for r in ev_orders.iter_rows(named=True):
        parts = r["order_id"].rsplit("-", 4)
        if len(parts) != 5:
            _fail(f"{cid}: unparsable order_id {r['order_id']!r}")
        prefix, y, mo, dy, sess = parts
        d = date(int(y), int(mo), int(dy))
        sym, sidestr = (prefix.split("-", 1) if "-" in prefix
                        else (prefix, ""))
        sclass = sidestr_class(sidestr)
        T = src_of(sym, sclass, d, sess)
        if T is None:
            _fail(f"{cid}: event order {r['order_id']} has no source intent")
        per_intent_events.setdefault((sym, sclass, T), []).append(r["event"])
    fills = res.fills
    fill_by_intent: dict = {}
    if fills.height:
        for r in fills.select("symbol", "side", "decision_date",
                              "decision_session").iter_rows(named=True):
            sclass = "buy" if r["side"] == "buy" else "sell"
            T = src_of(r["symbol"], sclass, r["decision_date"],
                       r["decision_session"])
            if T is not None:
                fill_by_intent.setdefault((r["symbol"], sclass, T), 0)
                fill_by_intent[(r["symbol"], sclass, T)] += 1
    outcomes: dict = {}
    term = {"expiry": 0, "override_same_name": 0, "cap_void": 0,
            "suspension_abandon": 0}
    expiry_at_target_noop = 0
    rule_blocked = {"below_min_lot": 0, "void_no_position": 0,
                    "void_insufficient_cash": 0}
    for r in fr.iter_rows(named=True):
        k = (r["symbol"], r["side"], r["source_signal"])
        eng = lifecycle.get(k, "still_active(no lifecycle event)")
        evs = per_intent_events.get(k, [])
        if fill_by_intent.get(k, 0) > 0:
            host = "filled"
        elif evs and all(e == "void_suspended" for e in evs):
            host = "terminated:suspension_abandon"
        elif evs and all(e in RULE_OK for e in evs):
            host = "executed_rule_blocked:" + evs[-1]
            rule_blocked[evs[-1]] += 1
        elif eng.startswith("cap_single_name"):
            host = "terminated:cap_void"
        elif eng.startswith("overridden"):
            host = "terminated:override_same_name"
        elif eng.startswith("expired") or eng.startswith("still_active"):
            if not evs:
                # zero-emission expired: suspended the whole window OR a
                # reduce-to-target intent at/below target at every decision
                # point (engine at_target skips emit nothing); distinguish
                # via whether the symbol traded in-window (P3R2 verbatim)
                noop = False
                if r["side"] == "sell" and r["target_weight"] is not None:
                    arr = CLOSE_ARR.get(r["symbol"])
                    if arr is not None:
                        dint_a, _ = arr
                        lo, hi = dint_of(r["source_signal"]), \
                            dint_of(r["expiry_date"])
                        j = int(np.searchsorted(dint_a, lo))
                        noop = j < len(dint_a) and dint_a[j] < hi
                if noop:
                    host = "terminated:expired_at_target_noop"
                    expiry_at_target_noop += 1
                else:
                    host = "terminated:suspension_abandon"
            else:
                host = "terminated:expiry"
        else:
            host = f"terminated:expiry(eng={eng})"
        outcomes[k] = (host, eng, len(evs))
        if host.startswith("terminated:"):
            reason = host.split(":", 1)[1]
            if reason == "suspension_abandon":
                term["suspension_abandon"] += 1
            elif reason == "override_same_name":
                term["override_same_name"] += 1
            elif reason == "cap_void":
                term["cap_void"] += 1
            else:
                term["expiry"] += 1
    n_filled = sum(1 for v in outcomes.values() if v[0] == "filled")
    n_rule = sum(1 for v in outcomes.values()
                 if v[0].startswith("executed_rule_blocked"))
    n_term = sum(1 for v in outcomes.values()
                 if v[0].startswith("terminated:"))
    mapped = ((n_filled + n_rule) / (n_filled + n_rule + n_term)
              if (n_filled + n_rule + n_term) else None)
    il = res.stats["intent_layer"]
    if n_filled != il["stopped_filled"]:
        _fail(f"{cid}: host filled {n_filled} != engine stopped_filled "
              f"{il['stopped_filled']}")
    return {"outcomes": {k: v[0] for k, v in outcomes.items()},
            "termination": term, "mapped_rate": mapped,
            "n_filled": n_filled, "n_rule_blocked": n_rule,
            "n_terminated": n_term,
            "expiry_at_target_noop": expiry_at_target_noop,
            "zero_emission_intents": sum(
                1 for v in outcomes.values() if v[2] == 0)}


attr: dict = {}
for cid in results:
    attr[cid] = attribute(cid)
    a = attr[cid]
    log(f"  {cid}: R16-mapped exec {((a['mapped_rate'] or 0) * 100):.1f}% "
        f"(filled {a['n_filled']}, rule-blocked {a['n_rule_blocked']}, "
        f"terminated {a['n_terminated']}); term {a['termination']}")

# === 13. metrics & gates ======================================================
log("== 13. metrics & gates ==")


def gate8_v3(cid: str) -> dict:
    """Gate 8 v3 (v2 prereg sec 3, frozen): final delivery = (market-fallback
    fills + armed-then-limit-self fills) / armed fallbacks >= 99%; end-of-run
    armed stuck positions == 0 (hard assert, checked by the caller).

    Caliber (from events/stats, as the prereg mandates):
    - armed  = engine stats k3_fallback.armed (ground truth for arming count);
    - mkt    = engine stats k3_fallback.executed (market_exit_filled events,
               cross-checked 1:1 against fill_type=market_fallback fills per
               (date, session));
    - limit_self = filled_limit_sell events occurring while the symbol's
               fallback was ARMED per the event stream (the v1 sh.600518
               2019-06 pattern: armed -> limit-down deferrals -> the standing
               limit sell itself fills; the engine pops the armed state at the
               fill without a dedicated event, so this is reconstructed);
    - no_pos = market_exit_void_no_position events (armed, nothing held);
    - stuck  = symbols still armed at the end of the event stream;
    - residual = armed - mkt - limit_self - no_pos - stuck (arming states
               superseded by a newer same-name source -- the engine resets
               those silently; disclosed)."""
    res = results[cid]["res"]
    k3 = res.stats["k3_fallback"]
    armed, mkt = int(k3["armed"]), int(k3["executed"])
    ev, fills = res.events, res.fills
    # market_exit_filled events carry no symbol column: zip them with the
    # market_fallback fills of the same (date, session) in emission order
    fb_by: dict = {}
    if fills.height:
        for r in fills.filter(pl.col("fill_type") == "market_fallback") \
                      .iter_rows(named=True):
            fb_by.setdefault((r["date"], r["session"]), []).append(r["symbol"])
    mkt_seen: dict = {}
    seq: list[dict] = []
    for i, r in enumerate(ev.iter_rows(named=True)):
        r = dict(r)
        r["_i"] = i
        e = r["event"]
        s = r["symbol"]
        if e == "market_exit_filled":
            k = (r["date"], r["session"])
            mkt_seen[k] = mkt_seen.get(k, 0) + 1
            lst = fb_by.get(k, [])
            if mkt_seen[k] > len(lst):
                _fail(f"{cid}: market_exit_filled events exceed "
                      f"market_fallback fills at {k}")
            r["_sym"] = lst[mkt_seen[k] - 1]
        elif s is None or s == "":
            # fallback lifecycle events: symbol is the detail prefix
            if e.startswith("market_exit_deferred") \
                    or e == "market_exit_void_no_position":
                r["_sym"] = (r["detail"] or "").split(":", 1)[0]
            else:
                continue                      # not fallback-relevant
        else:
            r["_sym"] = s
        seq.append(r)
    state: dict = {}
    tot = {"armed_events": 0, "market_filled": 0, "limit_self_filled": 0,
           "no_position_cleared": 0}
    lim_cases: list[dict] = []
    for r in seq:
        e, s = r["event"], r["_sym"]
        st = state.setdefault(s, {"armed": False})
        if e == "not_penetrated" \
                and "market fallback armed for next session" in (r["detail"] or ""):
            if not st["armed"]:
                tot["armed_events"] += 1
            st["armed"] = True
        elif e.startswith("market_exit_deferred"):
            st["armed"] = True
        elif e == "market_exit_filled":
            tot["market_filled"] += 1
            st["armed"] = False
        elif e == "market_exit_void_no_position":
            tot["no_position_cleared"] += 1
            st["armed"] = False
        elif e == "filled_limit_sell" and st["armed"]:
            tot["limit_self_filled"] += 1
            st["armed"] = False
            lim_cases.append({"symbol": s, "date": str(r["date"]),
                              "order_id": r["order_id"]})
    stuck = sorted(s for s, st in state.items() if st["armed"])
    if tot["market_filled"] != mkt:
        _fail(f"{cid}: reconstructed market fills {tot['market_filled']} != "
              f"engine k3_executed {mkt}")
    residual = armed - mkt - tot["limit_self_filled"] \
        - tot["no_position_cleared"] - len(stuck)
    delivered = mkt + tot["limit_self_filled"]
    delivery = (delivered / armed) if armed else None
    return {"armed": armed, "market_fallback_fills": mkt,
            "armed_then_limit_self_fills": tot["limit_self_filled"],
            "limit_self_cases": lim_cases,
            "no_position_cleared": tot["no_position_cleared"],
            "stuck_final": stuck, "superseded_residual": residual,
            "final_delivery_rate": delivery,
            "gate_pass": (True if armed == 0 else delivery >= 0.99),
            "caliber": "final delivery = (market-fallback fills + armed-"
                       "then-limit-self fills) / armed fallbacks, >= 99%; "
                       "end-of-run armed stuck positions == 0 hard assert; "
                       "v2 prereg sec 3; residual = silently superseded "
                       "arming states (engine resets them without an event)"}



def daily_max_single_name_weight(res) -> float:
    dates = res.daily["date"].to_list()
    eq_list = res.daily["equity"].to_list()
    per: dict = {}
    for r in res.fills.select("symbol", "date", "side", "shares") \
                     .iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    sp_by = {sym: sorted((dint_of(ed), f) for ed, f in evs)
             for sym, evs in split_events.items()}
    state: dict = {}
    wmax = 0.0
    for d, e in zip(dates, eq_list):
        td = dint_of(d)
        if e <= 0:
            continue
        for sym, evs in per.items():
            st = state.get(sym)
            if st is None:
                st = [0, 0, 0]
                state[sym] = st
            pos, i, si = st
            sp = sp_by.get(sym, [])
            while si < len(sp) and sp[si][0] <= td:
                pos = int(math.floor(pos * sp[si][1] + 0.5))
                si += 1
            while i < len(evs) and evs[i][0] <= td:
                ev = evs[i]
                while si < len(sp) and sp[si][0] <= ev[0]:
                    pos = int(math.floor(pos * sp[si][1] + 0.5))
                    si += 1
                pos += ev[2] if ev[1] == "buy" else -ev[2]
                i += 1
            st[0], st[1], st[2] = pos, i, si
            if pos > 0:
                px = close_le(sym, d)
                if px and px > 0 and pos * px / e > wmax:
                    wmax = pos * px / e
    return wmax


metrics: dict = {}
gates: dict = {}
for cid in CONFIG_IDS:
    if cid not in results:
        continue
    res = results[cid]["res"]
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(),
                            DEV_START, DEV_END)
    net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd = er.max_drawdown(sd, sv)["max_drawdown"]
    yr = er.year_returns(sd, sv)
    b1y = {int(k): v for k, v in B1["b1m_net_return_by_year"].items()}
    adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
    excess = net_cagr - B1["b1m_net_cagr"]
    df = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
    mean_eq = {int(r["yy"]): r["equity"] for r in
               df.group_by("yy").agg(pl.col("equity").mean()).iter_rows(named=True)}
    buy_by = {}
    if res.fills.height:
        buy_by = {int(r["yy"]): r["n"] for r in
                  res.fills.filter(pl.col("side") == "buy")
                  .with_columns(pl.col("date").dt.year().alias("yy"))
                  .group_by("yy").agg(pl.col("notional").sum().alias("n"))
                  .iter_rows(named=True)}
    tby = {y: {"buy_notional": buy_by.get(y, 0.0), "mean_equity": mean_eq[y],
               "one_side_turnover": buy_by.get(y, 0.0) / mean_eq[y]}
           for y in sorted(mean_eq)}
    wmax = daily_max_single_name_weight(res)
    a = attr[cid]
    k3 = res.stats["k3_fallback"]
    # gate 8 v3 (frozen v2): final delivery from events/stats
    g8v3 = gate8_v3(cid)
    if g8v3["stuck_final"]:
        _fail(f"{cid}: gate 8 v3 HARD ASSERTION FAILED -- end-of-run armed "
              f"stuck positions {g8v3['stuck_final']} (prereg sec 3)")
    # gate 8 v2 (v1 caliber) kept as a comparison column, NOT re-judged
    armed, executed = int(k3["armed"]), int(k3["executed"])
    delivery_v2 = (executed / armed) if armed else None
    m = {"net_cagr": net_cagr,
         "net_total_return": sv[-1] / sv[0] - 1.0,
         "max_drawdown": mdd,
         "b1m_net_cagr": B1["b1m_net_cagr"],
         "b1m_max_drawdown": B1["b1m_max_drawdown"],
         "b1m_net_return_by_year": B1["b1m_net_return_by_year"],
         "b1m_source": "R16 metrics.json configs.C05 verbatim "
                       "(T200-40/rate_only; family anchor)",
         "b3prime_path": B1_PATH_NAME,
         "excess_vs_b1m": excess,
         "net_return_by_year": {int(k): v for k, v in yr.items()},
         "advantage_years_list": [int(y) for y in adv],
         "turnover_by_year": tby,
         "max_one_side_turnover": max(v["one_side_turnover"]
                                      for v in tby.values()),
         "max_single_name_weight": wmax,
         "goal_dev_net_cagr_ge_10pct": net_cagr >= 0.10,
         "gate8_v3_final_delivery": g8v3,
         "gate8_v2_comparison": {"armed": armed, "executed": executed,
                                 "delivery_rate": delivery_v2,
                                 "deferred_limitdown":
                                     k3["deferred_limitdown_sessions"],
                                 "deferred_suspended":
                                     k3["deferred_suspended"],
                                 "deferred_t1locked":
                                     k3["deferred_t1locked"],
                                 "caliber": "v1 8v2 (market-fallback "
                                            "executions / armed only); "
                                            "comparison column, NOT a gate "
                                            "in v2"},
         "r16_execution_rate_comparison": {
             "value": a["mapped_rate"],
             "mapping": "filled + rule-blocked / (filled + rule-blocked + "
                        "terminated); R16 original 95% caliber, NOT a gate "
                        "here (structural, disclosed)"}}
    g = {"1_net_cagr_gt_0": net_cagr > 0,
         "2_excess_vs_B1m_ge_2pp": excess >= 0.020,
         "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
         "4_mdd_le_20pct_and_le_B1m":
             abs(mdd) <= 0.20 + 1e-12
             and abs(mdd) <= abs(B1["b1m_max_drawdown"]) + 1e-12,
         "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,
         "6_single_name_weight_le_40pct": wmax <= 0.40,
         "7_vs_B3prime_plus_1pp": net_cagr >= B3P[B1_PATH_NAME] + 0.010,
         "8v3_final_delivery_ge_99pct": g8v3["gate_pass"],
         "advantage_years": len(adv), "dev_excess_vs_b1m": excess}
    g["failed_gates"] = sorted(k for k in GATE_KEYS if not g[k])
    g["dev_pass"] = not g["failed_gates"]
    g["roster_eligible"] = bool(g["dev_pass"]
                                and m["goal_dev_net_cagr_ge_10pct"])
    g["verdict"] = ("roster_eligible" if g["roster_eligible"]
                    else "dev_pass" if g["dev_pass"] else "eliminated")
    metrics[cid] = m
    gates[cid] = {"dev": g, "verdict": g["verdict"]}
    d3 = g8v3
    d3v = "n/a(0 armed)" if d3["final_delivery_rate"] is None \
        else f"{d3['final_delivery_rate']*100:.1f}%"
    d2v = "n/a(0 armed)" if delivery_v2 is None \
        else f"{delivery_v2*100:.1f}%"
    log(f"  {cid}: net {net_cagr*100:+.2f}% excess {excess*100:+.2f}pp "
        f"adv {len(adv)}/6 mdd {mdd*100:.2f}% turn "
        f"{m['max_one_side_turnover']:.2f} w {wmax*100:.1f}% g8v3 "
        f"{d3['market_fallback_fills']}+{d3['armed_then_limit_self_fills']}"
        f"/{d3['armed']}={d3v} (8v2对照 {executed}/{armed}={d2v}) "
        f"goal10 {m['goal_dev_net_cagr_ge_10pct']} -> "
        f"{'PASS' if g['dev_pass'] else 'eliminated ' + str(g['failed_gates'])}")

n_pass = sum(1 for cid in gates if gates[cid]["dev"]["dev_pass"])
log(f"== gates: {n_pass}/{len(gates)} dev_pass ==")
check_budget("metrics & gates")

# === 14. disclosures (prereg sec 8 item 10 + 3/6) =============================
log("== 14. disclosures ==")


def equity_decomposition(cid: str) -> dict:
    """Daily stock-MV / etf-MV / cash split from fills x official closes;
    max-DD window attribution + full-period level decomposition + leg weights."""
    res = results[cid]["res"]
    dates = res.daily["date"].to_list()
    per: dict = {}
    for r in res.fills.select("symbol", "date", "side", "shares") \
                     .iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    mv_st, mv_et, cash, eq = [], [], [], []
    mv_leg: dict[str, list[float]] = {s: [] for s in CFGS[cid]["legs"]}
    state: dict = {}
    for d, row in zip(dates, res.daily.iter_rows(named=True)):
        td = dint_of(d)
        s_st = s_et = 0.0
        day_leg = {s: 0.0 for s in mv_leg}
        for sym, evs in per.items():
            st = state.get(sym)
            if st is None:
                st = [0, 0]
                state[sym] = st
            pos, i = st
            while i < len(evs) and evs[i][0] <= td:
                pos += evs[i][2] if evs[i][1] == "buy" else -evs[i][2]
                i += 1
            st[0], st[1] = pos, i
            if pos > 0:
                px = close_le(sym, d)
                if px:
                    mv = pos * px
                    if sym in PANEL_SYMS:
                        s_et += mv
                        if sym in day_leg:
                            day_leg[sym] = mv
                    else:
                        s_st += mv
        mv_st.append(s_st)
        mv_et.append(s_et)
        for s in mv_leg:
            mv_leg[s].append(day_leg[s])
        cash.append(row["settled_cash"] + row["pending_am_to_pm"]
                    + row["pending_next_day"])
        eq.append(row["equity"])
    ddw = er.max_drawdown(dates, eq)
    peak = (date.fromisoformat(ddw["peak_date"])
            if ddw.get("peak_date") else None)
    trough = (date.fromisoformat(ddw["trough_date"])
              if ddw.get("trough_date") else None)
    out = {"mdd_window": {"peak_date": str(peak), "trough_date": str(trough),
                          "max_drawdown": ddw["max_drawdown"]}}
    if peak in dates and trough in dates:
        i0, i1 = dates.index(peak), dates.index(trough)
        de = eq[i0] - eq[i1]
        if abs(de) > 1e-9:
            out["mdd_window_attribution"] = {
                "equity_change": de,
                "stock_leg_share": (mv_st[i0] - mv_st[i1]) / de,
                "etf_leg_share": (mv_et[i0] - mv_et[i1]) / de,
                "cash_share": (cash[i0] - cash[i1]) / de}
    out["full_period_level_change"] = {
        "equity": eq[-1] - eq[0],
        "stock_leg": mv_st[-1] - mv_st[0],
        "etf_leg": mv_et[-1] - mv_et[0],
        "cash": cash[-1] - cash[0]}
    legs = CFGS[cid]["legs"]
    leg_w = {}
    for sym, series in mv_leg.items():
        ws = [m / e for m, e in zip(series, eq) if e > 0]
        leg_w[sym] = {"mean_weight": float(np.mean(ws)) if ws else None,
                      "max_weight": float(np.max(ws)) if ws else None,
                      "park_w": legs[sym]}
    if legs:
        tot = [m / e for m, e in zip(mv_et, eq) if e > 0]
        leg_w["_total_etf"] = {"mean_weight": float(np.mean(tot)) if tot else None,
                               "max_weight": float(np.max(tot)) if tot else None,
                               "park_w": sum(legs.values())}
    out["leg_weights"] = leg_w
    return out


def slippage_stats(cid: str) -> dict:
    """Avg slippage of fills vs the intent's source-signal-day official close
    (buys: price/src-1; sells: src/price-1; >0 = worse than the anchor)."""
    res = results[cid]["res"]
    fr = FRAMES[cid]
    sources_by: dict = {}
    for r in fr.iter_rows(named=True):
        sclass = "buy" if r["side"] == "buy" else "sell"
        sources_by.setdefault((r["symbol"], sclass), []).append(
            (r["source_signal"], r["decision_session"]))
    src_cache: dict = {}

    def src_of(sym: str, sclass: str, d, s: str):
        key = (sym, sclass, dint_of(d), s)
        if key in src_cache:
            return src_cache[key]
        best = None
        for T, first_s in sources_by.get((sym, sclass), []):
            if T < d or (T == d and first_s == "pm" and s == "pm"):
                if best is None or T > best:
                    best = T
        src_cache[key] = best
        return best

    def src_close(sym: str, T: date) -> float | None:
        arr = CLOSE_ARR.get(sym)
        if arr is None or T is None:
            return None
        dint_a, cls = arr
        i = int(np.searchsorted(dint_a, dint_of(T), side="right")) - 1
        return float(cls[i]) if i >= 0 else None

    slips = {"buy": [], "sell": []}
    fb_slips = {"buy": [], "sell": []}
    if res.fills.height:
        for r in res.fills.iter_rows(named=True):
            sclass = "buy" if r["side"] == "buy" else "sell"
            T = src_of(r["symbol"], sclass, r["decision_date"],
                       r["decision_session"])
            px0 = src_close(r["symbol"], T)
            if not px0:
                continue
            s = (r["price"] / px0 - 1.0 if sclass == "buy"
                 else px0 / r["price"] - 1.0)
            slips[sclass].append(s)
            if r["fill_type"] == "market_fallback":
                fb_slips[sclass].append(s)
    return {
        "caliber": "fill price vs official close of the intent's "
                   "source_signal day; buys price/src-1, sells src/price-1 "
                   "(>0 = worse than the decision anchor); limit fills "
                   "re-anchored at every decision point, so this measures "
                   "entry/exit LAG cost vs the first decision",
        "buy_mean": float(np.mean(slips["buy"])) if slips["buy"] else None,
        "sell_mean": float(np.mean(slips["sell"])) if slips["sell"] else None,
        "buy_n": len(slips["buy"]), "sell_n": len(slips["sell"]),
        "fallback_buy_mean": (float(np.mean(fb_slips["buy"]))
                              if fb_slips["buy"] else None),
        "fallback_sell_mean": (float(np.mean(fb_slips["sell"]))
                               if fb_slips["sell"] else None)}


def rotation_fill_profile(cid: str) -> dict:
    """v3: rotation-slot displacement profile (no stock configs in v3)."""
    res = results[cid]["res"]
    _uni = CFGS[cid]["rotation"]["universe"] if CFGS[cid]["rotation"] else UNI6
    f = res.fills.filter(pl.col("symbol").is_in(_uni)) \
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
                res.stats["intent_layer"]["stopped_filled"]}


disclosures: dict = {}
for cid in results:
    res = results[cid]["res"]
    st = res.stats
    a = attr[cid]
    m = metrics[cid]
    il = st["intent_layer"]
    n_risk_intents = int((FRAMES[cid]["side"] == "sell").sum())
    k3 = st["k3_fallback"]
    disclosures[cid] = {
        "verdict": gates[cid]["dev"]["verdict"],
        "1_execution": {
            "gate8_v3_final_delivery": m["gate8_v3_final_delivery"],
            "gate8_v2_comparison": m["gate8_v2_comparison"],
            "k3_trigger_rate_armed_per_risk_intent": (
                k3["armed"] / n_risk_intents if n_risk_intents else None),
            "risk_intents_in_frame": n_risk_intents,
            "r16_execution_rate_comparison": m["r16_execution_rate_comparison"],
            "limit_direct_fill_rate_orders": {
                "value": (il["stopped_filled"] / il["orders_generated"])
                if il["orders_generated"] else None,
                "caliber": "limit-filled orders / generated orders "
                           "(order-session level; disclosure, not a gate)"},
            "termination_reasons": a["termination"],
            "expired_at_target_noop": a["expiry_at_target_noop"],
            "rule_blocked": a["n_rule_blocked"],
            "zero_emission_intents": a["zero_emission_intents"],
            "slippage_vs_source_close": slippage_stats(cid)},
        "2_turnover_fees": {
            "buy_notional_total": st["turnover"]["buy_notional_total"],
            "sell_notional_total": st["turnover"]["sell_notional_total"],
            "fees_total": (float(res.fills["fees_total"].sum())
                           if res.fills.height else 0.0),
            "max_one_side_turnover": m["max_one_side_turnover"]},
        "3_mdd_attribution": equity_decomposition(cid),
        "5_increments": {
            "intent_layer": {k: il[k] for k in
                             ("n_intents", "activated", "orders_generated",
                              "stopped_filled", "terminated_override",
                              "terminated_expired", "terminated_cap",
                              "at_target_skips",
                              "emissions_skipped_no_anchor",
                              "emissions_skipped_no_live_session")},
            "caps": st["caps"], "cash_friction": st["cash_friction"],
            "void_days": st["void_days"],
            "etf_leg_stats": st["etf_leg"],
            "dividend_events_cash": st["etf_leg"]["dividend_events_cash"],
            "corp_actions": st["corp_actions"],
            "leg_structure_check": leg_struct_check.get(cid),
            "engine_warnings_n": len(results[cid]["warnings"]),
            "engine_warnings_sample": results[cid]["warnings"][:3],
            "final": st["final"]},
        "6_rotation_vs_A0": None,
    }
base_profile = rotation_fill_profile("EU-A0")
for cid in results:
    if cid == "EU-A0":
        continue
    prof = rotation_fill_profile(cid)
    disclosures[cid]["6_rotation_vs_A0"] = {
        "r3a0": base_profile, "this": prof,
        "delta_rotation_fills":
            prof["rotation_fills"] - base_profile["rotation_fills"],
        "delta_insufficient_cash":
            prof["insufficient_cash_orders"]
            - base_profile["insufficient_cash_orders"],
        "caliber": "rotation-slot displacement vs EU-A0 (v3 prereg sec 4-2, "
                   "universe = each config's own rotation universe): "
                   "config-universe fills / emitted entries-exits / "
                   "insufficient-cash orders; top3 variants are expected to "
                   "compete harder for cash (disclosed, not gated)"}

# --- EU disclosure: frozen config matrix (prereg sec 2) --------------------
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
            "weight <= 25% (S-rob-1 lesson); EU-A0 is the anchor, not a trial"}

# --- v2 disclosure: 159934 frozen non-modeling deviation --------------------
disclosures["sz159934_frozen_disclosure"] = {
    "dev_mismatch_rows": LEG_DEVIATIONS,
    "dividend_rule_events_dev": 0,
    "note": "sz.159934 dev preclose deviation(s) with factor ratio 1.0 "
            "(no share jump) are NOT modeled, per the frozen v2 prereg sec 2; "
            "same class as v1's sz.159915 2020-02-26 disclosure",
    "config": {"band": 0.10, "t_plus": 0, "commission": "same as other ETFs"}}
disclosures["eu45_dividend_events"] = {
    "rule": "v3 frozen dividend extraction rule applied verbatim to the "
            "45-symbol EU45 panel (dev window)",
    "n_events_dev": dividend_events45.height,
    "counts_by_symbol": dict(
        Counter(dividend_events45["symbol"].to_list())),
    "new_member_counts_vs_v3_panel": EU45_NEW_DIV,
    "members_subset_equals_anchor_18": True,
    "engine_guard": "engine v1.3 anti-misclassification guard armed "
                    "(dividend implied return > 10% -> hard error; "
                    "fail-closed, no data repair)",
    "events": [{"symbol": r["symbol"], "date": str(r["date"]),
                "div_per_share": r["div_per_share"]}
               for r in dividend_events45.iter_rows(named=True)]}
check_budget("disclosures")

# === 15. outputs / report / manifest =========================================
log("== 15. outputs ==")
out_dir = RUN_DIR / "outputs"
out_dir.mkdir(parents=True, exist_ok=True)
for cid in results:
    st = results[cid]
    FRAMES[cid].write_parquet(out_dir / f"{cid}_intents.parquet")
    st["res"].fills.write_parquet(out_dir / f"{cid}_fills.parquet")
    st["res"].events.write_parquet(out_dir / f"{cid}_events.parquet")
    st["res"].daily.write_parquet(out_dir / f"{cid}_daily_equity.parquet")
    st["res"].clips_final.write_parquet(out_dir / f"{cid}_clips_final.parquet")
    (out_dir / f"{cid}_stats.json").write_text(json.dumps(
        {"stats": st["res"].stats, "warnings": st["warnings"],
         "wall_s": st["wall_s"]}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
if ROT_LOG:
    (out_dir / "rotation_monthly_log.json").write_text(json.dumps(
        ROT_LOG, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
(out_dir / "dividend_events.csv").write_text(
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
    f"{regression['parquet_bytes_equal_vs_v3']} {_byte_eq}")

_roster = sorted(cid for cid in gates
                 if gates[cid]["dev"]["roster_eligible"])
_STOP_NOTE = (
    "expanded-universe exploration round v1 (EU prereg sec 0/5): all 12 "
    "config results reported at once, no mid-run selection, no champion "
    "change, R3-05/R3-06 in-library status unchanged; roster eligibility "
    "(second-pass protocol = dev 8 gates AND net CAGR >= 10%) -> "
    + (", ".join(_roster) if _roster else "none")
    + f"; {n_pass}/{len(gates)} pass all 8 dev gates; ALL results "
      "exploration-grade; trials +10 (252->262, anchor not counted); "
      "val not consumed")

mg = {
    "experiment_id": "exp-20260919-expanded-universe-v1",
    "engine_sha256_16": ENGINE_SHA_AT_START[:16],
    "prereg_sha256_16": pins["prereg"]["sha256"][:16],
    "v2_prereg_inherited_sha256_16":
        pins["v2_prereg_inherited"]["sha256"][:16],
    "v1_prereg_inherited_sha256_16": pins["v1_prereg_inherited"]["sha256"][:16],
    "hyb_config_sha256_16": pins["hyb_config"]["sha256"][:16],
    "eu_a0_regression_anchor": {**regression,
                                "note": "polars .equals() vs the v3 run's "
                                        "(20260919T110500-hybrid-v3-r3ld) "
                                        "R3-06 outputs (intents/fills/events/"
                                        "daily/clips_final) + net_cagr 1e-12 "
                                        "match + parquet byte comparison "
                                        "(bytes_equal_vs_v3); mismatch = "
                                        "abort with zero conclusions; EU-A0 "
                                        "is NOT re-adjudicated"},
    "runner_assertions": {
        "i_explicit_bands_no_defaults": "PASS (etf_default_band_symbols "
                                        "empty on every meta config)",
        "ii_preclose_no_nulls": f"PASS ({ASSERT_II_NULLS} nulls, 9-symbol "
                                f"anchor dev panel; EU45 panel nulls "
                                f"{EU45_NULLS})",
        "iii_panel_dates_eq_sse_cal": ASSERT_III_TEXT},
    "metrics": metrics, "gates": gates, "disclosures": disclosures,
    "b3prime_dev_mean_net_cagr": B3P,
    "b3prime_source": "R16 metrics.json verbatim",
    "goal_column": "dev net CAGR >= 10% (user session target, NOT a gate)",
    "gate8_evolution": "R16 95% (market semantics) -> v1 8v2 (market "
                       "fallback only) -> v2 8v3 (final delivery incl. "
                       "armed-then-limit self-fills + stuck==0 hard assert); "
                       "8v2 and R16 kept as comparison columns; every change "
                       "logged in the ledger and results docs",
    "no_rejurisdiction": "v3-judged configs (R3-05/R3-06) are NOT re-run or "
                         "re-judged here; EU-A0 is a byte-level regression "
                         "anchor only (EU prereg sec 0); roster eligibility "
                         "under the second-pass protocol is NOT a champion "
                         "claim",
    "benchmark_seam_S3": "ROT arms have no stock exposure path; benchmarked "
                         "against the family anchor B1m/C05 (T200-40, "
                         "rate_only) + B3prime[T200-40]; carried over from v1 "
                         "unresolved; pending adjudication",
    "spec_seams": {
        "S1_park_init_source": "engine requires date-typed source_signal; "
                               "pinned 'park_init' literal is un-runnable; "
                               "resolved to the park decision date "
                               "2015-01-30 (no K impact: buys have no "
                               "fallback); carried over from v1 unresolved; "
                               "pending adjudication",
        "S2_leg_rotation_collision": "RESOLVED by the frozen v2 spec: leg "
                                     "symbols are removed from the ranking "
                                     "universe (ROT-03R/ROT-04: 7 members, "
                                     "ROT-05: 6 members); runner verifies "
                                     "disjointness at frame construction and "
                                     "that no entry/exit ever names a leg "
                                     "symbol; no duplicate first-decision "
                                     "points occurred",
        "S4_parkw_vs_cap25": "RESOLVED by the frozen v2 spec: multi-leg "
                             "structures with every symbol <= 25% (park "
                             "40-60%); runner hard-checks that no leg intent "
                             "is cap-voided (a cap-void would contradict the "
                             "frozen structure and abort)"},
    "consistency_c05": consistency_c05,
    "leg_struct_check": leg_struct_check,
    "sz159934_disclosure": disclosures["sz159934_frozen_disclosure"],
    "notes": [
        "gate8 v3 caliber: the numerator counts market-fallback executions "
        "(engine k3_executed) plus limit-sell self-fills that occurred while "
        "the symbol's fallback was armed per the event stream (reconstructed; "
        "the engine pops the armed state at such fills without a dedicated "
        "event). The v1 sh.600518 2019-06 case (8 limit-down deferrals, then "
        "the standing limit sell filled 2019-06-12, no stuck position) "
        "reconstructs exactly: v1 HYB configs armed=7 = 6 market + 1 "
        "limit-self, residual 0, stuck 0.",
        "8v3 delivery = n/a(0 armed) counts as a vacuous pass (documented "
        "convention, same as v1).",
        "v1-judged configs are not re-judged: 8v3 only affects gate 8; v1 "
        "verdicts (all eliminated, gate 3/4 dominated) stand.",
        "limit_direct_fill_rate is PER-EMISSION (filled orders / generated "
        "orders; intents re-emit at every decision point until done), while "
        "the R16 comparison column is PER-INTENT -- the two calibers are not "
        "comparable to each other; both are disclosed."],
    "advanced_to_validation": False, "val_consumed": False,
    "stop_note": _STOP_NOTE,
}
(out_dir / "metrics_and_gates.json").write_text(
    json.dumps(mg, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")


def death_line(cid: str) -> str:
    f = gates[cid]["dev"]["failed_gates"]
    msgs = {"1_net_cagr_gt_0": "net CAGR<=0 (gate 1)",
            "2_excess_vs_B1m_ge_2pp": "excess<+2pp (gate 2)",
            "3_advantage_years_ge_5_of_6": "advantage years<5/6 (gate 3)",
            "4_mdd_le_20pct_and_le_B1m": "maxDD breach (gate 4)",
            "5_one_side_turnover_le_6": "turnover>6 (gate 5)",
            "6_single_name_weight_le_40pct": "single-name weight>40% (gate 6)",
            "7_vs_B3prime_plus_1pp": "<B3'+1pp (gate 7)",
            "8v3_final_delivery_ge_99pct": "final delivery<99% (gate 8v3)"}
    return "; ".join(msgs[k] for k in f) if f else "all gates pass"


rep = ["# 扩展宇宙探索轮 v1 判定（exp-20260919-expanded-universe-v1，EU-A0 锚 + EU-01..10）", "",
       f"- 运行 `{RUN_DIR.name}`；引擎 v1.2 sha256:16 `{ENGINE_SHA_AT_START[:16]}`"
       f"（运行前后一致，v2 prereg §5 pin 零改动）；预登记 sha256:16 "
       f"`{pins['prereg']['sha256'][:16]}`（已冻结，运行中零修改）；继承条款 "
       f"v2 预登记 sha256:16 `{pins['v2_prereg_inherited']['sha256'][:16]}`"
       f"（其再继承 v1 sha256:16 "
       f"`{pins['v1_prereg_inherited']['sha256'][:16]}`）。",
       f"- 窗口 dev {DEV_START}..{DEV_END}，信号 {sig_days[0]}..{sig_days[-1]}"
       f"（{len(sig_days)} 个月末，2020-12-31 丢弃）；val 2021–2024 零消费"
       f"（用户 2026-09-19 裁定暂不消费，继续 dev）。",
       f"- EU-A0 回归锚：intents/fills/events/daily_equity/clips_final "
       f"与 v3 run（20260919T110500-hybrid-v3-r3ld）R3-06 产物逐帧 polars "
       f"`.equals()` 全部一致（5/5 PASS）+ net_cagr 1e-12 一致 + parquet "
       f"字节比对（见 manifest eu_a0_regression）；锚失败即中止整轮零结论；"
       f"锚不重判。",
       "- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。", "",
       "## 〇、规格接缝状态（未静默裁定）", "",
       f"- **S2（腿-轮动键冲突）**：{mg['spec_seams']['S2_leg_rotation_collision']}",
       f"- **S4（ParkW vs 25% 上限）**：{mg['spec_seams']['S4_parkw_vs_cap25']}",
       f"- **S1（park_init 源标记，v1 遗留未决）**：{mg['spec_seams']['S1_park_init_source']}",
       f"- **S3（ROT 基准映射，v1 遗留未决）**：{mg['benchmark_seam_S3']}", "",
       "## 一、判定表（八门，门 8 = v3 + 8v2/R16 对照列 + 目标列）", "",
       "| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | "
       "单票max权重 | 门8v3 最终交付(市价+限价自成交/武装) | 8v2对照 | "
       "R16原口径(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |",
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for cid in CONFIG_IDS:
    if cid not in metrics:
        continue
    m, g = metrics[cid], gates[cid]["dev"]
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
        f"| {m['excess_vs_b1m']*100:+.2f}pp | {g['advantage_years']}/6 "
        f"| {m['max_drawdown']*100:.2f}% "
        f"| {m['max_one_side_turnover']:.2f} "
        f"| {m['max_single_name_weight']*100:.1f}% "
        f"| {d3txt} "
        f"| {d2txt} "
        f"| {(m['r16_execution_rate_comparison']['value'] or 0)*100:.1f}% "
        f"| {'Y' if m['goal_dev_net_cagr_ge_10pct'] else 'N'} "
        f"| {8 - len(g['failed_gates'])} "
        f"| {', '.join(g['failed_gates']) or '-'} "
        f"| {'**dev_pass**' if g['dev_pass'] else 'eliminated'} |")
rep += ["", "### 一句话死因", ""]
for cid in CONFIG_IDS:
    if cid in gates and not gates[cid]["dev"]["dev_pass"]:
        extra = ""
        if CFGS[cid]["legs"]:
            legnote = "; ".join(
                f"{s} {w:.0%}" for s, w in CFGS[cid]["legs"].items())
            park = sum(CFGS[cid]["legs"].values())
            extra = f"（腿 {legnote}，park {park:.0%}）"
        rep.append(f"- **{cid}**: {death_line(cid)}{extra}")
rep += ["", "## 二、强制披露（v2 prereg §4 + v1 §8-10 继承项）", ""]
for cid in results:
    d = disclosures[cid]
    m = metrics[cid]
    sl = d["1_execution"]["slippage_vs_source_close"]
    dm = d["3_mdd_attribution"]
    d3 = m["gate8_v3_final_delivery"]
    lw = dm.get("leg_weights", {})
    lwtxt = "; ".join(
        f"{s}: 实际均重 {v['mean_weight']*100:.1f}%/max {v['max_weight']*100:.1f}%"
        f" (目标 {v['park_w']*100:.0f}%)"
        for s, v in lw.items() if not s.startswith("_"))
    attr_txt = ""
    if "mdd_window_attribution" in dm:
        aw = dm["mdd_window_attribution"]
        attr_txt = (f"DD窗({dm['mdd_window']['peak_date']}→"
                    f"{dm['mdd_window']['trough_date']}) 归因: 股票腿 "
                    f"{aw['stock_leg_share']*100:.1f}% / ETF腿 "
                    f"{aw['etf_leg_share']*100:.1f}% / 现金 "
                    f"{aw['cash_share']*100:.1f}%")
    comp = d.get("6_rotation_vs_A0")
    comp_txt = ""
    if comp:
        comp_txt = (
            f"；vs EU-A0: 轮动成交 {comp['delta_rotation_fills']:+d} 单, "
            f"现金不足作废 {comp['this']['insufficient_cash_orders']} 次"
            f"（锚 {comp['r3a0']['insufficient_cash_orders']} 次）")
    d3txt = ("n/a(0 armed)" if d3["final_delivery_rate"] is None
             else f"{d3['market_fallback_fills']}+"
                  f"{d3['armed_then_limit_self_fills']}/{d3['armed']}"
                  f"={d3['final_delivery_rate']*100:.1f}%")
    res_txt = ""
    if d3.get("superseded_residual"):
        res_txt = f"（超继残差 {d3['superseded_residual']}，已披露口径）"
    lim_txt = ""
    if d3.get("limit_self_cases"):
        lim_txt = "；限价自成交 " + ", ".join(
            f"{c['symbol']} {c['date']}" for c in d3["limit_self_cases"])
    rep.append(
        f"- **{cid}**: 门8v3 最终交付 {d3txt}{res_txt}{lim_txt}"
        f"；限价直接成交率 "
        f"{(d['1_execution']['limit_direct_fill_rate_orders']['value'] or 0)*100:.1f}%"
        f"；滑点(vs源信号收盘) 买 "
        f"{(sl['buy_mean'] or 0)*100:+.3f}% 卖 {(sl['sell_mean'] or 0)*100:+.3f}%"
        f"；分年 {json.dumps({str(k): round(v, 4) for k, v in m['net_return_by_year'].items()})}"
        f"；终止 {json.dumps(d['1_execution']['termination_reasons'])}"
        f"；{attr_txt}；{lwtxt}{comp_txt}")
if "eu_config_matrix" in disclosures:
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
            "outputs/dividend_events45.csv。"]
rep += ["", "### 159934 冻结披露", "",
        f"- sz.159934（黄金ETF）dev 内 preclose 无跳变微偏离 "
        f"{json.dumps(LEG_DEVIATIONS)}——因子 ratio=1.0（无份额变动），"
        "按 v2 预登记 §2 不建模，仅披露（与 v1 159915 同类）；"
        "分红规则扫描 0 事件。", "",
        "## 三、EU-A0 回归锚（= v3 R3-06 复刻）", "",
        f"- 5/5 帧 `.equals()` 一致：{json.dumps({k: v for k, v in regression.items()})}",
        f"- 引擎 stats：intents {results['EU-A0']['res'].stats['intent_layer']['n_intents']}"
        f"，orders {results['EU-A0']['res'].stats['intent_layer']['orders_generated']}"
        f"，filled {results['EU-A0']['res'].stats['intent_layer']['stopped_filled']}。",
        "", "## 四、运行身份", "",
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
        f"- 时间划分：dev {DEV_START}..{DEV_END}；val 未消费；判定只对 dev。",
        f"- 试验计账：本轮 +10 探索试验（EU 预登记 §2/§5：252→262），"
        "锚 EU-A0 不计试验；谱系 v1 205→214、v2 214→222、v3 222→229、"
        "val 229→241、rob 241→252（如台账有异以台账为准）。",
        f"- 判定：{mg['stop_note']}"]
rep += ["", "## 五、关键发现与口径说明", "",
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
        "覆盖）全部通过（计数与明细见披露与 outputs/）。"]
(RUN_DIR / "delivery_report.md").write_text("\n".join(rep),
                                               encoding="utf-8")

ENGINE_SHA_AT_END = sha256_file(ENGINE_PY)
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json", "runner.log"):
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260919-expanded-universe-v1",
    "status": "completed" if not BLOCKED else "completed_with_blocked_config",
    "started_at_utc": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_exp_universe.py"],
    "random_seed": None,
    "determinism": "no RNG in runner or engine; static intent frames; "
                   "engine-owned deterministic lifecycle",
    "engine": {"path": str(ENGINE_PY),
               "sha256_at_start": ENGINE_SHA_AT_START,
               "sha256_at_end": ENGINE_SHA_AT_END,
               "bytes_modified_by_this_run":
                   ENGINE_SHA_AT_START != ENGINE_SHA_AT_END,
               "version": "v1.3 (sha256 pin 84a2443a...082c; EU prereg sec 0)"},
    "pins": pins,
    "env_versions": ENV_VERSIONS,
    "window": {"dev": f"{DEV_START}..{DEV_END}",
               "signals": f"{sig_days[0]}..{sig_days[-1]} ({len(sig_days)})",
               "val_consumed": False},
    "stage_timings_s": {ln.split("]")[0].strip("[")
                        .replace("s", ""): ln.split("==")[1].strip(" =")
                        for ln in LOG_LINES if "== " in ln and ln.startswith("[")},
    "configs_run": list(results), "configs_blocked": sorted(BLOCKED),
    "consistency_c05": consistency_c05,
    "eu_a0_regression": regression,
    "leg_struct_check": leg_struct_check,
    "spec_seams": mg["spec_seams"],
    "benchmark_seam_S3": mg["benchmark_seam_S3"],
    "dividend_events_built": dividend_events.height,
    "eu45_panel_inventory": {
        "symbols": EU45_SYMS,
        "n": len(EU45_SYMS),
        "anchor_panel_9": list(PANEL_SYMS),
        "dividend_events45_dev": dividend_events45.height,
        "new_member_dividend_counts": EU45_NEW_DIV},
    "input_parquet": {"path": str(ETF_DAILY),
                      "sha256_16": pins["etf_daily_input"]["sha256"][:16],
                      "expected_prefix": "b7225d50523106f5",
                      "rows_2025_plus": 0},
    "trial_accounting": {"this_round":
                             "+10 exploration trials (12 configs run; "
                             "anchor EU-A0 not counted per EU prereg sec 2)",
                         "cumulative_lineage": "per EU prereg sec 2/5: "
                                               "252 -> 262"},
    "gates_dev_pass": [cid for cid in gates if gates[cid]["dev"]["dev_pass"]],
    "advanced_to_validation": False,
    "val_consumed": False,
    "stop_note": mg["stop_note"],
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== manifest + report written; wall {time.perf_counter() - T0:.0f}s, "
    f"peak rss {PEAK_RSS:.2f} GB ==")
log(f"== VERDICT: {n_pass}/{len(gates)} dev_pass; blocked={sorted(BLOCKED)}; "
    f"{mg['stop_note']}")
_logf.close()
