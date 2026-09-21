# -*- coding: utf-8 -*-
"""exp-20260920-zone-sheet-f4r2 (F4R2 stop-only ablation) FULL-DEV runner --
engine v1.4.1 (pin a01cb29c..., zones mode, tp1 optional per contract sec
10.8), prereg FROZEN (docs/research/exp-20260920-zone-sheet-f4r2-prereg.md
+ configs/experiments/f4r2-zone-sheet-notp.json).

Copy-adapted from the ACCEPTED F4R1 full-dev runner
(artifacts/runs/20260920T020201-f4r1-full-a3b7/scripts/runner_f4r1_full.py):
the chassis, ICW sleeve construction, A0 anchor, data pins and the gate
layer are carried verbatim; ONLY the arm set (3 arms -> F4R2-D1/D2), the
take-profit injection (D1 = zero-tier via NULL tp1/tp2 per the adjudicated
seam F4R2-S1; D2 = config zones_D2 widening 4sigma/50% + 5sigma/100%), the
identity strings and the trial accounting changed.  The T200-40 exposures
section was dropped because no F4R2 arm path-scales w_T (both arms use the
constant 0.06; disclosed in the manifest).

Engine seam history (this run directory): the first implementation pass
ABORTED at the F4R2-S1 feasibility check because the pinned v1.4 engine
fail-closed rejected every frame-level tp-disable form (evidence:
tmp/s1_tp_disable_probe.py + s1_tp_disable_probe_result_v14.json).  The
main conversation dual-signed the minimal v1.4.1 extension (tp1/tp2
columns optional; null/absent => ZERO-TIER take-profit, no profit intent
emitted; supplied values keep every v1.4 fail-closed assert; new guardrail
tp1-null-with-tp2-set rejected) and re-pinned the engine.  The v1.4.1
behavior was re-verified before this run
(tmp/s1_tp_disable_probe_v141.py + s1_tp_disable_probe_result_v141.json).
The aborted manifest is archived at tmp/manifest_aborted_v1.json; no arm
had run and no trial was consumed in the aborted pass.

Gates (frozen F4R1 prereg sec 2 carried verbatim per F4R2 prereg sec 2;
zero search):
- gates 1-7 carried VERBATIM from the F3R3 runner gate code; anchors
  B1(m) = R16 C05 T200-40 rate-only (net +0.60%, maxDD -39.82%, loaded
  from R16 metrics.json configs.C05 verbatim and asserted against the
  frozen 4-dp values), B3' = -0.0199.
- gate 8 = v1.4 caliber (contract sec 10.1-5 restated): armed = stop-loss
  triggerings that left shares stuck (T+1 / suspension carryover),
  numerator = K=3 fallback fills + armed-then-self fills, delivery >= 99%,
  stuck == 0 hard assert; TP / buy expiries counted SEPARATELY (not in the
  denominator).
- goal column = dev net CAGR >= 10%; goal_met = dev_pass AND goal column.

Stop rules (F4R2 prereg sec 7): A0 anchor byte mismatch -> STOP before the
arms (no trial consumed).  Any arm dev_pass AND >= 10% -> rare case, STOP
and present to user.  D1 net CAGR >= +3% AND gate 4 passed -> H1 zone,
report the dose-response gradient and present to user.  D1 net CAGR < +2%
-> H0 zone, F-line execution-layer conclusion closed, STOP.  In between
(or gate 4 broken with CAGR >= +2%) -> middle zone, attribution report to
the user.  No F4R3 is opened autonomously; val (2021-2024) zero contact.

Trial accounting: strategy line 273 -> 275 booked at THIS run (two arm
trials; registered in the main-conversation ledger; the F4R2-A0 anchor
consumes no trial).  Factor line FT01=120 unchanged.

Val discipline: 2021-2024 zero contact -- every data frame is hard-filtered
to dev bounds and engine-side assert_frozen re-checks.

Deterministic; no RNG.  Budget 900 s wall, peak RSS 8 GB.
"""
from __future__ import annotations

import filecmp
import hashlib
import json
import math
import platform
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    assert_frozen, batch_aggregate_sha256,
    load_stk_limit_batch, load_dividends_h5, load_split_factor_h5,
    run_band_backtest_intents, run_band_backtest_zones, BandContractError)

# === frozen identity =========================================================
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F3R3_RUN = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F3R3_REF_OUT = F3R3_RUN / "outputs"
F4R1_FULL_RUN = ROOT / "artifacts/runs/20260920T020201-f4r1-full-a3b7"
R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
R16_CONFIG = ROOT / "configs/experiments/p2r16-trend-dispersion.json"
PREREG_MD = ROOT / "docs/research/exp-20260920-zone-sheet-f4r2-prereg.md"
F4R2_CONFIG = ROOT / "configs/experiments/f4r2-zone-sheet-notp.json"
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
INDUSTRY_CSV = ROOT / "data/raw/tushare/index_member_all/20260909-r1/chunk_all.csv"
V3_RUN = ROOT / "artifacts/runs/20260919T110500-hybrid-v3-r3ld"

# engine v1.4.1 pin (dual-signed re-pin after the F4R2-S1 adjudication;
# contract sec 10.8: zones tp1/tp2 columns optional, null = zero-tier TP)
ENGINE_SHA_EXPECT_FULL = ("a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1"
                          "f0a466b0675abf3")
ENGINE_V13_SHA16 = "84a2443ac28fe1b8"   # the F3R1 composite was built under v1.3
ENGINE_VERSION_NOTE = ("v1.4.1 (pin a01cb29c...; zones mode, tp1 optional "
                       "per contract sec 10.8)")

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
ARMS = ["F4R2-D1", "F4R2-D2"]

# F4R2 frozen sleeve parameters (F4R2 prereg sec 3; F4R1-A chassis verbatim
# minus take-profit; zero grid)
SLEEVE_K = 10
TOP_2K = 20                # candidate list = top 2K per signal month
SLEEVE_W_ON = 0.06         # both F4R2 arms: constant per-name target weight
IND_CAP = 2
BUFFER_MULT = 2
STOP_MULT = 3.0
INVALID_MULT = 3.5
LADDER_OFFSETS = "0.5,1.5,2.5"
LADDER_FRACS = "0.4,0.4,0.2"
SIGMA_LOOKBACK = 20        # close-to-close log returns
SIGMA_DDOF = 1             # sample stdev (runner convention, disclosed)
# F4R2-D2 take-profit tiers (config zones_D2; F4R2-S2: designed 2x widening
# of the F4R1 tiers, NOT historical tuning)
D2_TP1_MULT, D2_TP1_FRAC = 4.0, 0.5
D2_TP2_MULT, D2_TP2_FRAC = 5.0, 1.0
ANCHOR_INITIAL_CASH = 200_000.0
ARMS_INITIAL_CASH = 500_000.0
ZONE_PRIORITY_BASE = 1000
LEG_PRIORITY = 999         # adaptation F4R1-S1: BR-1 requires priority < base

# frozen gates (prereg sec 2; anchors asserted against the frozen numbers)
GATE_KEYS = ["1_net_cagr_gt_0", "2_excess_vs_B1m_ge_2pp",
             "3_advantage_years_ge_5_of_6", "4_mdd_le_20pct_and_le_B1m",
             "5_one_side_turnover_le_6", "6_single_name_weight_le_40pct",
             "7_vs_B3prime_plus_1pp", "8_final_delivery_ge_99pct_v14"]
B1M_NET_CAGR_FROZEN = 0.0060          # R16 C05 T200-40 rate-only, 4 dp
B1M_MAXDD_FROZEN = -0.3982
B3P_T20040_FROZEN = -0.0199
GOAL_CAGR = 0.10

# frozen universe / chassis (F3R3 verbatim)
MEMBERS = ["sh.511010", "sh.518880", "sh.510050", "sh.510300", "sz.159915",
           "sh.510880", "sh.513100", "sh.513500"]
LEG_ONLY = ["sz.159934"]
PANEL_SYMS = MEMBERS + LEG_ONLY
MEMBER_BAND = {m: 0.10 for m in PANEL_SYMS}
UNI6 = [m for m in MEMBERS if m not in ("sh.511010", "sh.518880")]
CHASSIS_LEGS = {"sh.511010": 0.15, "sh.518880": 0.25}
DIVIDEND_EXPECT = {"sh.510050": 5, "sh.510300": 6, "sh.510880": 6,
                   "sh.511010": 1}

INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "priority": pl.Int64,
    "expiry_date": pl.Date, "target_weight": pl.Float64,
}
ZONES_INPUT_SCHEMA = {
    "signal_date": pl.Date, "symbol": pl.String, "rank": pl.Int64,
    "industry": pl.String, "sigma0": pl.Float64, "p0": pl.Float64,
    "w_t": pl.Float64, "ladder_offsets": pl.String, "ladder_fracs": pl.String,
    "tp1_mult": pl.Float64, "tp1_frac": pl.Float64,
    "tp2_mult": pl.Float64, "tp2_frac": pl.Float64,
    "stop_mult": pl.Float64, "invalid_mult": pl.Float64,
    "k_seats": pl.Int64, "ind_cap": pl.Int64, "buffer_mult": pl.Int64,
}
HALF_COLS = ["symbol", "trade_date", "session", "open", "high", "low", "close"]

T0 = time.perf_counter()
BUDGET_S = 900.0
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
        "experiment_id": "exp-20260920-zone-sheet-f4r2",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


def dints(col: pl.Series) -> np.ndarray:
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


def sess_key(d: date, s: str) -> int:
    return (d.year * 10_000 + d.month * 100 + d.day) * 2 + (0 if s == "am" else 1)


def key_to_ds(key: int) -> tuple[date, str]:
    d, r = divmod(key, 2)
    y, rem = divmod(d, 10_000)
    mo, dy = divmod(rem, 100)
    return date(y, mo, dy), ("am" if r == 0 else "pm")


# === 0. identity pins ========================================================
log("== 0. identity pins (engine v1.4 frozen, prereg frozen; full-dev run) ==")
pins: dict = {}
EXPECTED = {
    "engine": (ENGINE_SHA_EXPECT_FULL, ENGINE_PY),
    "daily": ("d9a63f4cc3032926", DAILY_PARQUET),
    "halfday_manifest": ("2a414174b5df2eee", HALFDAY_DIR / "manifest.json"),
    "split_factor": ("2f436b2f13d09a9b", BUNDLE / "split_factor.h5"),
    "dividends": ("46121c09cddde72e", BUNDLE / "dividends.h5"),
    "index_000300": ("05aaa8183a11c674", INDEX_CHUNK),
    "f3r1_icw_composite": ("b09242ee542cf675",
                           F3R1_RUN / "outputs/F3-ICW_composite.parquet"),
    "f3r1_manifest": (None, F3R1_RUN / "manifest.json"),
    "f3r1_metrics": (None, F3R1_RUN / "outputs/metrics_and_gates.json"),
    "industry_l1": ("4edffc3994fb527a", INDUSTRY_CSV),
    "r16_config": ("27f846a7330919a4", R16_CONFIG),
    "r16_metrics": (None, R16_RUN / "metrics.json"),
    "prereg": (None, PREREG_MD),
    "f4r2_config": (None, F4R2_CONFIG),
    "f4r1_full_manifest": (None, F4R1_FULL_RUN / "manifest.json"),
    "f4r1_full_metrics": (None,
                          F4R1_FULL_RUN / "outputs/metrics_and_gates.json"),
    "f4r1_full_runner_source": (None, F4R1_FULL_RUN
                                / "scripts/runner_f4r1_full.py"),
    "f4r2_aborted_manifest_v1": (None, RUN_DIR
                                 / "tmp/manifest_aborted_v1.json"),
    "f3r3_runner_source": (None, F3R3_RUN / "scripts/runner_f3r3.py"),
    "f3r3_manifest": (None, F3R3_RUN / "manifest.json"),
    "v3_metrics_r306_anchor_source": (None,
                                      V3_RUN / "outputs/metrics_and_gates.json"),
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

# frozen config sanity: the config json is the only parameter source
cfg_json = json.loads(F4R2_CONFIG.read_text(encoding="utf-8"))
assert cfg_json["arms"]["F4R2-D1"]["w_T"] == SLEEVE_W_ON
assert cfg_json["arms"]["F4R2-D2"]["w_T"] == SLEEVE_W_ON
assert cfg_json["stock_sleeve"]["membership"]["max_members"] == SLEEVE_K
assert cfg_json["stock_sleeve"]["membership"]["industry_cap_per_l1"] == IND_CAP
_zd2 = cfg_json["zones_D2"]
assert (_zd2["b1"]["mult"], _zd2["b1"]["frac"]) == (D2_TP1_MULT, D2_TP1_FRAC)
assert (_zd2["b2"]["mult"], _zd2["b2"]["frac"]) == (D2_TP2_MULT, D2_TP2_FRAC)
assert cfg_json["zones"]["b1"]["mult"] is None \
    and cfg_json["zones"]["b2"]["mult"] is None   # D1 zero-tier form

# F3R1 composite provenance: produced under the pinned v1.3 engine
f3r1_mg = json.loads((F3R1_RUN / "outputs/metrics_and_gates.json")
                     .read_text(encoding="utf-8"))
if f3r1_mg["engine_sha256_16"] != ENGINE_V13_SHA16:
    _fail("F3R1 composite was not produced under the pinned v1.3 engine")
pins["f3r1_engine_provenance"] = {"engine_sha256_16": f3r1_mg["engine_sha256_16"],
                                  "match": True}

# frozen gate anchors: loaded from R16 metrics.json configs.C05 verbatim
# (F3R3 convention) and asserted against the prereg frozen numbers
r16_config = json.loads(R16_CONFIG.read_text(encoding="utf-8"))
r16_metrics = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
B1 = r16_metrics["configs"]["C05"]
B1_PATH_NAME = r16_config["configs"]["C05"]["path"]
assert B1["b1m_variant"].startswith("rate_only"), B1["b1m_variant"]
B3P = {"T200-40": r16_metrics["B3prime_dev_mean_net_cagr"]["T200-40"],
       "FIX75": r16_metrics["B3prime_dev_mean_net_cagr"]["FIX75"]}
if abs(B1["b1m_net_cagr"] - B1M_NET_CAGR_FROZEN) > 1e-4 \
        or abs(B1["b1m_max_drawdown"] - B1M_MAXDD_FROZEN) > 1e-4 \
        or abs(B3P["T200-40"] - B3P_T20040_FROZEN) > 1e-4:
    _fail("frozen gate anchor mismatch vs prereg sec 2 "
          f"(B1m {B1['b1m_net_cagr']}/{B1['b1m_max_drawdown']}, "
          f"B3' {B3P['T200-40']})")
pins["gate_anchors"] = {
    "b1m_net_cagr": B1["b1m_net_cagr"], "b1m_max_drawdown": B1["b1m_max_drawdown"],
    "b3prime_t20040": B3P["T200-40"], "b1m_path": B1_PATH_NAME,
    "match_vs_frozen": True,
    "source": "R16 metrics.json configs.C05 verbatim (F3R3 convention)"}
log(f"  gate anchors: B1(m) net {B1['b1m_net_cagr'] * 100:+.2f}% mdd "
    f"{B1['b1m_max_drawdown'] * 100:.2f}%; B3' {B3P['T200-40']:.4f} "
    "(== prereg sec 2 frozen values)")

# halfday batch identity: manifest sha pinned above; the prereg sec 10
# corrected identity also pins the ROW COUNT 18,486,939 (F3R3 verified pin)
_half_parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
if not _half_parts:
    _fail("no halfday partitions")
HALFDAY_ROWS_TOTAL = 0
for _p in _half_parts:
    HALFDAY_ROWS_TOTAL += int(pl.scan_parquet(str(_p)).select(
        pl.len()).collect().item())
pins["halfday_rows_total"] = {"rows": HALFDAY_ROWS_TOTAL, "expected": 18_486_939,
                              "match": HALFDAY_ROWS_TOTAL == 18_486_939}
log(f"  halfday rows total: {HALFDAY_ROWS_TOTAL} (pin 18,486,939)")
if HALFDAY_ROWS_TOTAL != 18_486_939:
    _fail("halfday row-count pin mismatch (prereg sec 10 corrected identity)")

stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {
    "path": str(STK_DIR), **stk_agg, "expected": "3c53abf3b0c39b42",
    "match": stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit aggregate pin mismatch")
etf_agg = batch_aggregate_sha256(ETF_DIR)
cal_agg = batch_aggregate_sha256(TRADECAL_DIR)
etf_manifest_json = json.loads(ETF_MANIFEST.read_text(encoding="utf-8"))
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
    "match": (adj_agg_recomputed == declared_adj and not adj_rehash_mismatch)}
pins["etf_processed_aggregate"] = {**etf_agg, "expected": None, "match": True}
pins["trade_cal_aggregate"] = {**cal_agg, "expected": None, "match": True}
if not pins["fund_adj_aggregate"]["match"]:
    _fail(f"fund_adj identity check failed: {pins['fund_adj_aggregate']}")
log(f"  etf processed dir aggregate: {etf_agg['aggregate_sha256'][:16]} "
    f"({etf_agg['files']} files); fund_adj batch re-verified "
    f"({len(adj_chunks)} chunks, 0 mismatches)")
log(f"  python {platform.python_version()} | polars {pl.__version__} | "
    f"numpy {np.__version__} | rss {rss_gb():.2f} GB")
ENV_VERSIONS = {"python": platform.python_version(),
                "platform": platform.platform(),
                "polars": pl.__version__, "numpy": np.__version__}

# === 1. calendar & signal days (full dev; smoke/F3R3 construction verbatim) ==
log("== 1. calendar & signal days (full dev) ==")
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
log(f"  {len(sig_days)} full-dev signal days ({sig_days[0]}..{sig_days[-1]}; "
    "2020-12-31 dropped as signal, kept as expiry anchor)")
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}

# === 2. (T200-40 exposures NOT computed) =====================================
# F4R2 has no path-scaled arm: both F4R2-D1/D2 use the constant w_T = 0.06
# (config arms.*.w_T asserted above).  The F4R1 runner computed the R16
# T200-40 month-end exposures only for its arm B (w_T = e_T x 0.06/0.90);
# that section is therefore dropped in this derivation (disclosed in the
# manifest under runner_adaptations_disclosed).


# === 3. ICW composite (F3R3 verbatim checks) =================================
log("== 3. F3R1 ICW composite + candidate tables ==")
_comp = pl.read_parquet(F3R1_RUN / "outputs/F3-ICW_composite.parquet")
if set(_comp.columns) != {"symbol", "signal_date", "value"}:
    _fail(f"composite ICW: unexpected schema {_comp.columns}")
_days = sorted(set(_comp["signal_date"].to_list()))
if _days != sorted(sig_days):
    _fail("composite ICW: signal days != runner sig_days")
if _comp.group_by("symbol", "signal_date").len().filter(
        pl.col("len") > 1).height:
    _fail("composite ICW: (symbol, signal_date) not unique")
COMPOSITE: dict[date, dict[str, float]] = {}
for r in _comp.iter_rows(named=True):
    COMPOSITE.setdefault(r["signal_date"], {})[r["symbol"]] = float(r["value"])
del _comp

# monthly candidate table: top 2K = 20 by value desc, symbol asc tie-break;
# rank = 1..20 assigned on this order (sigma exclusions drop rows but do not
# renumber survivors -- the rank is the composite rank, disclosed)
CANDIDATES: dict[date, list[str]] = {}
for t in sig_days:
    ranked = sorted(COMPOSITE[t], key=lambda s: (-COMPOSITE[t][s], s))
    CANDIDATES[t] = ranked[:TOP_2K]
CAND_ALL_SYMS = sorted({s for t in sig_days for s in CANDIDATES[t]})
log(f"  candidates: top-{TOP_2K} per signal month; full-dev union "
    f"{len(CAND_ALL_SYMS)} symbols over {len(sig_days)} signal days")

# === 4. closes for sigma0/p0 (full official calendar, raw official close) ====
log("== 4. candidate closes (sigma0 / p0 lookups) ==")
_look0 = DEV_START - timedelta(days=200)
_cdf = (pl.scan_parquet(str(DAILY_PARQUET))
        .filter(pl.col("symbol").is_in(CAND_ALL_SYMS))
        .filter((pl.col("date") >= _look0) & (pl.col("date") <= DEV_END))
        .select("symbol", "date", "close", "tradestatus").collect())
CLOSE: dict[tuple[str, int], float] = {}
for r in _cdf.iter_rows(named=True):
    if r["tradestatus"] != 0 and r["close"] is not None and r["close"] > 0:
        CLOSE[(r["symbol"], dint_of(r["date"]))] = float(r["close"])
del _cdf
log(f"  close lookups: {len(CLOSE)} traded (symbol, session) points "
    f"for {len(CAND_ALL_SYMS)} candidates")


def sigma_p0(sym: str, T: date) -> tuple[float, float] | tuple[None, str]:
    """S-v14-1 runner caliber (pinned at the smoke run, prereg sec 11):
    sigma0 = std(20 last close-to-close log returns, sample ddof=1) x P0;
    P0 = signal-day official close.  The 20 returns END at the signal day
    (21 closes incl. P0).  Exclusion reasons: 'signal_day_no_close' (P0
    missing), 'lookback_gap' (a suspended session inside the 21-close
    window), 'short_history' (<20 returns available)."""
    i = idx_of_full[T]
    if i < SIGMA_LOOKBACK:
        return None, "short_history"
    sessions = calendar_full[i - SIGMA_LOOKBACK: i + 1]
    p0 = CLOSE.get((sym, dint_of(T)))
    if p0 is None:
        return None, "signal_day_no_close"
    closes = [p0]
    for d in reversed(sessions[:-1]):
        c = CLOSE.get((sym, dint_of(d)))
        if c is None:
            return None, "lookback_gap"
        closes.append(c)
    closes.reverse()
    rets = [math.log(closes[k] / closes[k - 1])
            for k in range(1, len(closes))]
    sigma0 = float(np.std(rets, ddof=SIGMA_DDOF)) * p0
    return sigma0, p0


# === 5. industry map (F3R3 verbatim: shenwan L1 2026 single snapshot) ========
log("== 5. industry map (shenwan L1, 2026 single snapshot) ==")
_ind = pl.read_csv(INDUSTRY_CSV)
_ind = _ind.with_columns(
    (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
     + "." + pl.col("ts_code").str.split(".").list.first()).alias("sym"))
INDUSTRY_L1: dict[str, str] = dict(zip(_ind["sym"].to_list(),
                                       _ind["l1_name"].to_list()))
_unmapped = [s for s in CAND_ALL_SYMS if s not in INDUSTRY_L1]
log(f"  industry L1 map: {len(INDUSTRY_L1)} stocks, "
    f"{_ind['l1_name'].n_unique()} industries; full-dev candidates unmapped "
    f"{len(_unmapped)} -> UNMAPPED bucket (same cap); 2026 single-snapshot "
    "lookahead disclosed in prereg sec 3")


def IND_OF(sym: str) -> str:
    return INDUSTRY_L1.get(sym, "UNMAPPED")


def build_zones_frame(arm: str) -> tuple[pl.DataFrame, dict]:
    """Per-arm full-dev zones frame (F4R2 prereg sec 3; F4R1-A chassis
    minus the take-profit tier injection below)."""
    rows: list[dict] = []
    excl: Counter = Counter()
    for T in sig_days:
        for rank, sym in enumerate(CANDIDATES[T], start=1):
            sigma0, p0 = sigma_p0(sym, T)
            if sigma0 is None:
                excl[p0 if isinstance(p0, str) else "other"] += 1
                continue
            w_t = SLEEVE_W_ON
            if arm == "F4R2-D1":
                # F4R2-S1 adjudicated form: NULL tp1/tp2 = the v1.4.1
                # ZERO-TIER take-profit (no profit intent emitted; engine
                # re-verified in tmp/s1_tp_disable_probe_v141.py).  Not the
                # NaN form (fail-closed rejected) and not an oversized-mult
                # hack (prereg sec 6 forbids it).
                tp1_mult = tp1_frac = None
                tp2_mult = tp2_frac = None
            else:   # F4R2-D2: config zones_D2 (F4R2-S2 designed widening)
                tp1_mult, tp1_frac = D2_TP1_MULT, D2_TP1_FRAC
                tp2_mult, tp2_frac = D2_TP2_MULT, D2_TP2_FRAC
            rows.append({
                "signal_date": T, "symbol": sym, "rank": rank,
                "industry": IND_OF(sym), "sigma0": sigma0, "p0": p0,
                "w_t": w_t, "ladder_offsets": LADDER_OFFSETS,
                "ladder_fracs": LADDER_FRACS, "tp1_mult": tp1_mult,
                "tp1_frac": tp1_frac, "tp2_mult": tp2_mult,
                "tp2_frac": tp2_frac, "stop_mult": STOP_MULT,
                "invalid_mult": INVALID_MULT, "k_seats": SLEEVE_K,
                "ind_cap": IND_CAP, "buffer_mult": BUFFER_MULT})
    meta = {"rows": len(rows), "sigma_excluded": dict(excl),
            "sigma_excluded_total": sum(excl.values()),
            "candidates_before_filter": sum(len(CANDIDATES[T])
                                            for T in sig_days)}
    return pl.DataFrame(rows, schema=ZONES_INPUT_SCHEMA), meta


ZONES_FRAMES: dict[str, pl.DataFrame] = {}
ZONES_META: dict[str, dict] = {}
for _arm in ARMS:
    zf_, zm_ = build_zones_frame(_arm)
    ZONES_FRAMES[_arm] = zf_
    ZONES_META[_arm] = zm_
    log(f"  zones frame {_arm}: {zf_.height} rows "
        f"(of {zm_['candidates_before_filter']} candidates; sigma excluded "
        f"{zm_['sigma_excluded']})")
check_budget("zones frames")

# === 6. ETF assets (F3R3 verbatim) ===========================================
log("== 6. ETF assets ==")
etf_panel_full = pl.read_parquet(ETF_DAILY)
etf_panel = (etf_panel_full.filter(pl.col("symbol").is_in(PANEL_SYMS))
             .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
             .sort("symbol", "date"))
del etf_panel_full
assert_frozen(etf_panel, "date", "etf_daily")
per_member = {r["symbol"]: r["len"] for r in
              etf_panel.group_by("symbol").len().iter_rows(named=True)}
log(f"  etf panel dev rows: {etf_panel.height} per member {per_member}")
if set(per_member) != set(PANEL_SYMS):
    _fail(f"etf panel member coverage broken: {sorted(per_member)}")

n_null_preclose = int(etf_panel.filter(pl.col("preclose").is_null()).height)
log(f"  assertion (ii) preclose nulls: {n_null_preclose}")
if n_null_preclose:
    _fail("runner assertion (ii) FAILED: preclose nulls in member-dev panel")

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
if miss or extra:
    _fail(f"runner assertion (iii) FAILED: missing {miss[:5]} extra {extra[:5]}")

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

# dividend events (frozen rule; assert == 18) -- F3R3 verbatim
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
if dict(counts) != DIVIDEND_EXPECT or dividend_events.height != 18:
    _fail(f"dividend events != frozen expectation {DIVIDEND_EXPECT}: {counts}")

# 159934 frozen non-modeling check (F3R3 verbatim)
leg_scan = det.filter(pl.col("symbol") == "sz.159934").filter(
    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
LEG_DEVIATIONS: list[dict] = []
leg_div_rows = []
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
                           "rel_diff": rel, "factor_ratio": ratio})
    if (r["preclose"] < r["prev_close"]) and (1.0 < ratio <= 1.06):
        leg_div_rows.append(r)
if leg_div_rows:
    _fail(f"159934 dividend-rule events found in dev ({len(leg_div_rows)}) "
          "-- contradicts the frozen spec (0 modeled events); STOP, spec seam")
log(f"  159934 dev mismatch rows: {len(LEG_DEVIATIONS)}; "
    "dividend-rule events: 0 (frozen)")

SYMBOL_META = {m: {"asset_class": "etf", "band": MEMBER_BAND[m],
                   "t_plus": 0} for m in PANEL_SYMS}


def etf_pm_bars(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("symbol"), pl.col("date").alias("trade_date"),
        pl.lit("pm", dtype=pl.String).alias("session"),
        pl.col("open"), pl.col("high"), pl.col("low"), pl.col("close"))


check_budget("etf assets")

# === 7. market frames (limits / splits / dividends loaded once) ==============
log("== 7. market frames (shared loaders) ==")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})  # ENGINE-2 bridge
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
log(f"  limits {limits_full.height} rows, splits {splits_all.height}, "
    f"dividends {divs_all.height} (full files; dev-filtered per run)")
DAILY_TS_DTYPE = pl.Float64   # daily parquet tradestatus dtype (verified)

# === 8. F4R2-A0 anchor: R3-06 verbatim at 200k, byte reproduction ============
# (F4R1-A0 construction verbatim; F3R3-A0 remains the byte reference -- it
# gates the arms per F4R2 prereg sec 4, no trial consumed)
log("== 8. F4R2-A0 anchor (R3-06 verbatim, byte reproduction) ==")


def leg_intent_rows_a0() -> list[dict]:
    """F3R3 verbatim (priority 10**6; park expiry = 4th signal day + 1)."""
    rows: list[dict] = []
    park_T = sig_days[0]
    park_expiry = date.fromordinal(sig_days[3].toordinal() + 1)
    for sym, w in CHASSIS_LEGS.items():
        rows.append({"symbol": sym, "side": "buy", "intent": "",
                     "decision_date": park_T, "decision_session": "pm",
                     "source_signal": park_T, "priority": 10 ** 6,
                     "expiry_date": park_expiry, "target_weight": float(w)})
        for T in sig_days[1:]:
            Tp = next_sig.get(T)
            expiry = date.fromordinal(Tp.toordinal() + 1)
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": 10 ** 6,
                         "expiry_date": expiry, "target_weight": float(w)})
    return rows


def rotation_intent_rows_a0() -> list[dict]:
    """F3R3 verbatim (R3-06: UNI6, top_n 3, weight 0.20, lookback 6m)."""
    lb, top_n, w = 6, 3, 0.20
    adj_close: dict[str, dict[int, float]] = {}
    for m in MEMBERS:
        fmap = factor_map[m]
        sub = etf_panel.filter(pl.col("symbol") == m)
        rows = sub.select(
            (pl.col("date").dt.year().cast(pl.Int64) * 10_000
             + pl.col("date").dt.month().cast(pl.Int64) * 100
             + pl.col("date").dt.day().cast(pl.Int64)).alias("dint"),
            "close")
        adj_close[m] = {int(r["dint"]):
                        float(r["close"]) * fmap[int(r["dint"])]
                        for r in rows.iter_rows(named=True)}

    def month_shift(d: date, k: int) -> date | None:
        y, mo = d.year, d.month - k
        while mo <= 0:
            mo += 12
            y -= 1
        c = [x for x in sig_days_dev if (x.year, x.month) == (y, mo)]
        return c[0] if c else None

    hist_lb: dict[date, list[str]] = {}
    for T in sig_days:
        T0d = month_shift(T, lb)
        if T0d is None:
            continue
        scores = {}
        for m in UNI6:
            a0 = adj_close[m].get(dint_of(T0d))
            a1 = adj_close[m].get(dint_of(T))
            if not a0 or not a1:
                scores = None
                break
            scores[m] = a1 / a0 - 1.0
        if scores is None:
            continue
        hist_lb[T] = sorted(scores, key=lambda mm: (-scores[mm], mm))
    rows: list[dict] = []
    prev_top: set | None = None
    for T in sorted(hist_lb):
        top = set(hist_lb[T][:top_n])
        Tp = next_sig.get(T)
        expiry = date.fromordinal(Tp.toordinal() + 1) if Tp else T
        if prev_top is not None:
            for sym in sorted(prev_top - top):
                rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T, "priority": 10 ** 6,
                             "expiry_date": expiry, "target_weight": None})
            rank_in_top = {s: i + 1 for i, s in
                           enumerate(hist_lb[T][:top_n])}
            for sym in sorted(top - prev_top):
                rows.append({"symbol": sym, "side": "buy", "intent": "",
                             "decision_date": T, "decision_session": "pm",
                             "source_signal": T,
                             "priority": 10 ** 6 + rank_in_top[sym],
                             "expiry_date": expiry, "target_weight": w})
        prev_top = top
    return rows


a0_rows = leg_intent_rows_a0() + rotation_intent_rows_a0()
_a0_syms = set(PANEL_SYMS)
assert not ({r["symbol"] for r in a0_rows} - _a0_syms)
FRAME_A0 = pl.DataFrame(a0_rows, schema=INTENT_SCHEMA)
etf_panel_ts = etf_panel.with_columns(
    pl.lit(1.0, dtype=DAILY_TS_DTYPE).alias("tradestatus"))
etf_bars = etf_pm_bars(etf_panel_ts)
t_cfg = time.perf_counter()
res_a0 = run_band_backtest_intents(
    FRAME_A0,
    etf_panel_ts.select("symbol", "date", "open", "high", "low", "close",
                        "tradestatus", "preclose").sort("symbol", "date"),
    etf_bars,
    pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                         "limit_up": pl.Float64, "limit_down": pl.Float64}),
    pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                         "split_factor": pl.Float64}),
    pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                         "cash_per_lot_pre_tax": pl.Float64,
                         "round_lot": pl.Int64}),
    pl.DataFrame(schema={"symbol": pl.String, "is_etf": pl.Boolean,
                         "is_t0": pl.Boolean}),
    symbol_meta=SYMBOL_META, dividend_events=dividend_events,
    initial_cash=ANCHOR_INITIAL_CASH)
log(f"  A0 engine run {time.perf_counter() - t_cfg:.1f}s, "
    f"intents {res_a0.stats.get('intent_layer', {}).get('n_intents')} | "
    f"rss {rss_gb():.2f} GB")
out_dir = RUN_DIR / "outputs"
out_dir.mkdir(parents=True, exist_ok=True)
A0_REF = {"intents": "F3R3-A0_intents.parquet",
          "fills": "F3R3-A0_fills.parquet",
          "events": "F3R3-A0_events.parquet",
          "daily_equity": "F3R3-A0_daily_equity.parquet",
          "clips_final": "F3R3-A0_clips_final.parquet"}
A0_MINE = {"intents": FRAME_A0,
           "fills": res_a0.fills, "events": res_a0.events,
           "daily_equity": res_a0.daily, "clips_final": res_a0.clips_final}
A0_CMP: dict[str, dict] = {}
for name, ref_fn in A0_REF.items():
    mine_p = out_dir / f"F4R2-A0_{name}.parquet"
    A0_MINE[name].write_parquet(mine_p)
    ref_p = F3R3_REF_OUT / ref_fn
    same_bytes = filecmp.cmp(str(mine_p), str(ref_p), shallow=False)
    same_rows = A0_MINE[name].height == pl.read_parquet(ref_p).height
    A0_CMP[name] = {"mine": str(mine_p.relative_to(RUN_DIR)),
                    "ref": str(ref_p.relative_to(ROOT)),
                    "byte_equal": bool(same_bytes), "rows_equal": same_rows}
    log(f"  A0 {name}: byte_equal={same_bytes} rows_equal={same_rows}")
if not all(v["byte_equal"] for v in A0_CMP.values()):
    _fail(f"F4R2-A0 ANCHOR MISMATCH (F4R2 prereg sec 4 stop rule, no trial "
          f"consumed): {json.dumps(A0_CMP)}")
log("  F4R2-A0 anchor PASS (5/5 frames byte-equal to F3R3-A0)")
check_budget("A0 anchor")

# === 9. dev frames (stock + ETF mixed panel, full period) ====================
log("== 9. dev frames (full-period mixed panel) ==")
stock_syms = sorted({s for t in sig_days
                     for s in ZONES_FRAMES[ARMS[0]]["symbol"].to_list()})
for arm in ARMS[1:]:
    zsyms = set(ZONES_FRAMES[arm]["symbol"].to_list())
    assert zsyms == set(stock_syms), \
        f"{arm}: candidate symbol set differs across arms"
used_legs = sorted(set(CHASSIS_LEGS))
daily_stock = (pl.scan_parquet(str(DAILY_PARQUET))
               .filter(pl.col("symbol").is_in(stock_syms))
               .filter((pl.col("date") >= DEV_START)
                       & (pl.col("date") <= DEV_END))
               .select("symbol", "date", "open", "high", "low", "close",
                       "tradestatus").collect()
               .with_columns(pl.lit(None, dtype=pl.Float64)
                             .alias("preclose")))
etf_p = (etf_panel_ts.filter(pl.col("symbol").is_in(used_legs))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END)))
mix_daily = pl.concat([
    daily_stock.select("symbol", "date", "open", "high", "low", "close",
                       "tradestatus", "preclose"),
    etf_p.select("symbol", "date", "open", "high", "low", "close",
                 "tradestatus", "preclose")]).sort("symbol", "date")
parts = []
for part in sorted(HALFDAY_DIR.glob("year=*/bars.parquet")):
    f = pl.read_parquet(part)
    f = (f.filter((pl.col("trade_date") >= DEV_START)
                  & (pl.col("trade_date") <= DEV_END))
         .filter(pl.col("symbol").is_in(stock_syms)))
    if f.height:
        parts.append(f)
half_stock = (pl.concat(parts, how="vertical").select(HALF_COLS)
              if parts else pl.DataFrame(schema={
                  "symbol": pl.String, "trade_date": pl.Date,
                  "session": pl.String, "open": pl.Float64,
                  "high": pl.Float64, "low": pl.Float64,
                  "close": pl.Float64}))
mix_half = pl.concat([half_stock,
                      etf_pm_bars(etf_p).select(HALF_COLS)],
                     how="vertical")
limits_dev = (limits_full.filter(pl.col("symbol").is_in(stock_syms))
              .filter((pl.col("date") >= DEV_START)
                      & (pl.col("date") <= DEV_END))
              .sort("symbol", "date"))
splits_dev = splits_all.filter(pl.col("symbol").is_in(stock_syms))
cashdiv_dev = divs_all.filter(pl.col("symbol").is_in(stock_syms))
instr_dev = pl.DataFrame({
    "symbol": stock_syms, "is_etf": [False] * len(stock_syms),
    "is_t0": [False] * len(stock_syms)})
assert_frozen(mix_daily, "date", "daily")
assert_frozen(mix_half, "trade_date", "halfday")
FRAMES = {"daily": mix_daily, "half": mix_half, "limits": limits_dev,
          "splits": splits_dev, "cash_dividends": cashdiv_dev,
          "instruments": instr_dev}
log(f"  dev panel: daily {mix_daily.height} rows, half {mix_half.height}, "
    f"limits {limits_dev.height}, stocks {len(stock_syms)} | "
    f"rss {rss_gb():.2f} GB")
check_budget("dev frames")

# === 10. arm runs (zones + ETF intents, one ledger) ==========================
log("== 10. arm runs: 2 arms x full dev ==")


def leg_intent_rows_full() -> list[dict]:
    """F3R3 leg conventions on the full-dev signal days: park buy at the
    first signal day with the frozen '4th signal day + 1' expiry; monthly
    reduce-to-target risk sells afterwards (expiry = next signal day + 1).
    ADAPTED (disclosed, F4R1-S1): priority 999 (BR-1 cross-layer guard:
    intent priority must be < zone_priority_base) instead of F3R3's 10**6;
    999 keeps the leg the lowest layer below every zone order."""
    rows: list[dict] = []
    park_T = sig_days[0]
    park_expiry = date.fromordinal(sig_days[3].toordinal() + 1)
    for sym, w in CHASSIS_LEGS.items():
        rows.append({"symbol": sym, "side": "buy", "intent": "",
                     "decision_date": park_T, "decision_session": "pm",
                     "source_signal": park_T, "priority": LEG_PRIORITY,
                     "expiry_date": park_expiry, "target_weight": float(w)})
        for T in sig_days[1:]:
            Tp = next_sig.get(T)
            expiry = (date.fromordinal(Tp.toordinal() + 1) if Tp is not None
                      else park_expiry)
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": LEG_PRIORITY,
                         "expiry_date": expiry, "target_weight": float(w)})
    return rows


LEG_ROWS = leg_intent_rows_full()
_chk = [(r["symbol"], r["side"], r["source_signal"]) for r in LEG_ROWS]
if len(_chk) != len(set(_chk)):
    _fail("leg intent duplicates")
LEG_FRAME = pl.DataFrame(LEG_ROWS, schema=INTENT_SCHEMA)

# decision anchors for the checks (am -> halfday am.close, pm -> daily close);
# suspended sessions carry a NULL close (no official close) -> no anchor
ANCHORS: dict[tuple[str, int], float] = {}
for r in mix_daily.select("symbol", "date", "close").iter_rows(named=True):
    if r["close"] is None:
        continue
    ANCHORS[(r["symbol"], sess_key(r["date"], "pm"))] = float(r["close"])
for r in mix_half.filter(pl.col("session") == "am") \
                 .select("symbol", "trade_date", "close").iter_rows(named=True):
    if r["close"] is None:
        continue
    ANCHORS[(r["symbol"], sess_key(r["trade_date"], "am"))] = float(r["close"])
ANCHORS_BY_SYM: dict[str, list[tuple[int, float]]] = {}
for (sym, k), a in ANCHORS.items():
    ANCHORS_BY_SYM.setdefault(sym, []).append((k, a))
for _v in ANCHORS_BY_SYM.values():
    _v.sort()
HALF_OPENS: dict[tuple[str, int], tuple[float, float]] = {}
for r in mix_half.select("symbol", "trade_date", "session", "open",
                         "low").iter_rows(named=True):
    if r["open"] is None or r["low"] is None:
        continue
    HALF_OPENS[(r["symbol"], sess_key(r["trade_date"], r["session"]))] = \
        (float(r["open"]), float(r["low"]))
LIMIT_DOWN = {(r["symbol"], dint_of(r["date"])): float(r["limit_down"])
              for r in limits_dev.iter_rows(named=True)}

# close lookups for single-name weights (F3R3 close_le convention)
CLOSE_ARR: dict[str, tuple[np.ndarray, np.ndarray]] = {}
for _sym in stock_syms + PANEL_SYMS:
    if _sym in PANEL_SYMS:
        rows_ = etf_panel.filter(pl.col("symbol") == _sym)
    else:
        rows_ = mix_daily.filter((pl.col("symbol") == _sym)
                                 & (pl.col("tradestatus") != 0))
    CLOSE_ARR[_sym] = (dints(rows_["date"]),
                       rows_["close"].to_numpy().astype(np.float64))


def close_le(sym: str, d: date) -> float | None:
    arr = CLOSE_ARR.get(sym)
    if arr is None:
        return None
    dint_a, cls = arr
    i = int(np.searchsorted(dint_a, dint_of(d), side="right")) - 1
    return float(cls[i]) if i >= 0 else None


SPLIT_EVENTS: dict[str, list[tuple[date, float]]] = {}
for r in splits_dev.filter(pl.col("ex_date") <= DEV_END).iter_rows(named=True):
    SPLIT_EVENTS.setdefault(r["symbol"], []).append(
        (r["ex_date"], float(r["split_factor"])))
for v in SPLIT_EVENTS.values():
    v.sort()


# terminal zone events per symbol (any of these ends the zone's WAC history
# and bounds the stop-line walk): cooling / done / boundary exit.  Note the
# zone_exiting_boundary detail carries NO "(signal ...)" part, so the symbol
# is parsed from the detail prefix for all three.
TERM_EVENTS = ["zone_cooling", "zone_done", "zone_exiting_boundary"]


def build_term_keys(events: pl.DataFrame) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for r in events.filter(pl.col("event").is_in(TERM_EVENTS)) \
                   .iter_rows(named=True):
        d = r["detail"] or ""
        sym_t = d.split(" (", 1)[0].split(":", 1)[0].strip()
        if not sym_t:
            continue
        out.setdefault(sym_t, []).append(sess_key(r["date"], r["session"]))
    for v in out.values():
        v.sort()
    return out


def reconstruct_wac_path(fills: pl.DataFrame,
                         zones_in: pl.DataFrame,
                         term_keys: dict[str, list[int]]) -> dict[str, dict]:
    """Per symbol: chronological WAC path from zladder buy fills in ENGINE
    booking order (BR-4a: sells NEVER touch the WAC -- the engine's zone WAC
    is cumulative buy cost / cumulative buy shares since the zone opened,
    verified per-fill against TP prices and against zones_res wac_final).
    The accumulator RESETS after each terminal zone event of the symbol
    (cooling / done / boundary exit): the next zone starts a fresh WAC; a
    CONTINUED zone keeps its WAC (continuation emits no terminal event).
    Snapshots are taken after every buy fill; a TP limit price is fixed at
    EMISSION time, so a TP fill is verified against the WAC snapshot at its
    DECISION key (a tier filling in the same session as the TP does not
    change the TP price)."""
    state: dict[str, dict] = {}
    end_idx: dict[str, int] = {}
    out: dict[str, dict] = {}
    for i, r in enumerate(fills.iter_rows(named=True)):
        sym = r["symbol"]
        k = sess_key(r["date"], r["session"])
        ends = term_keys.get(sym)
        if ends:
            ei = end_idx.get(sym, 0)
            while ei < len(ends) and ends[ei] < k:
                ei += 1
                state.pop(sym, None)   # crossed a zone end -> fresh WAC
            end_idx[sym] = ei
        if r["side"] == "buy":
            st = state.setdefault(sym, {"amt": 0.0, "sh": 0})
            st["amt"] += float(r["price"]) * int(r["shares"])
            st["sh"] += int(r["shares"])
            out.setdefault(sym, {"path": []})["path"].append({
                "i": i, "date": r["date"], "session": r["session"],
                "decision_date": r["decision_date"],
                "wac": st["amt"] / st["sh"]})
    return out


def check_arm(arm: str, res, zones_in: pl.DataFrame, zmeta: dict) -> dict:
    """Correctness checks for one full-dev arm run (smoke caliber)."""
    checks: dict = {"arm": arm, "fail": []}
    fills, events, daily = res.fills, res.events, res.daily
    zones_res = res.zones
    st = res.stats["zones"]

    def bad(msg: str) -> None:
        checks["fail"].append(msg)
        log(f"    !! [{arm}] CHECK FAIL: {msg}")

    # -- (1) counts ----------------------------------------------------------
    checks["zones_rows"] = int(zones_in.height)
    checks["zones_meta"] = zmeta
    checks["stats_zones"] = {k: v for k, v in st.items() if k != "definitions"}
    if st["n_candidates"] != zones_in.height:
        bad(f"stats n_candidates {st['n_candidates']} != frame rows "
            f"{zones_in.height}")
    if st["n_zones"] != zones_res.height:
        bad(f"stats n_zones {st['n_zones']} != result zones rows "
            f"{zones_res.height}")
    adm = zones_res.filter(pl.col("admitted_key").is_not_null())
    if st["n_admitted"] != adm.height:
        bad(f"stats n_admitted {st['n_admitted']} != zones rows with "
            f"admitted_key {adm.height}")
    pc = Counter(zones_res["phase_final"].to_list())
    if dict(pc) != {k: v for k, v in st["phase_counts"].items()}:
        bad(f"phase_counts mismatch: engine {st['phase_counts']} vs frame "
            f"{dict(pc)}")
    adm_ev = events.filter(pl.col("event") == "zone_admitted")

    def parse_adm(detail: str) -> tuple[str, date, int]:
        head = detail.split(" (signal ", 1)
        rest = head[1].split(")", 1)
        return head[0], date.fromisoformat(rest[0]), int(
            rest[1].split("rank ", 1)[1].split(" ", 1)[0])

    adm_ev_rows = []
    for r in adm_ev.iter_rows(named=True):
        sym_a, sd_a, rank_a = parse_adm(r["detail"])
        adm_ev_rows.append({"symbol": sym_a, "signal": sd_a, "rank": rank_a,
                            "date": r["date"], "session": r["session"]})
    if len(adm_ev_rows) != st["n_admitted"]:
        bad(f"zone_admitted events {len(adm_ev_rows)} != stats n_admitted "
            f"{st['n_admitted']}")
    adm_by_month: dict[date, int] = Counter(e["signal"] for e in adm_ev_rows)
    per_scan_max: dict[tuple[date, str], int] = Counter(
        (e["date"], e["session"]) for e in adm_ev_rows)
    for (dd_s, ss_s), n in per_scan_max.items():
        if n > SLEEVE_K:
            bad(f"scan ({dd_s},{ss_s}): {n} admissions > K={SLEEVE_K}")
    first_scan_adm: dict[date, set] = {
        T: {e["symbol"] for e in adm_ev_rows
            if e["signal"] == T and e["date"] == T and e["session"] == "pm"}
        for T in sig_days}
    cont_zones: dict[date, set] = {T: set() for T in sig_days}
    for r in adm.iter_rows(named=True):
        ad_d, _ = key_to_ds(r["admitted_key"])
        if r["signal_date"] in cont_zones and ad_d < r["signal_date"]:
            cont_zones[r["signal_date"]].add(r["symbol"])
    checks["admissions_by_month"] = {str(k): int(v) for k, v
                                     in sorted(adm_by_month.items())}
    checks["admissions_first_scan"] = {str(T): len(first_scan_adm[T])
                                       for T in sig_days}
    checks["continuations_by_month"] = {str(k): len(v) for k, v
                                        in sorted(cont_zones.items())}

    # industry-blocked reconstruction (runner-side caliber, disclosed)
    ind_blocked: list[dict] = []
    month_admitted: dict[date, set] = {}
    for e in adm_ev_rows:
        month_admitted.setdefault(e["signal"], set()).add(e["symbol"])
    for Ti, T in enumerate(sig_days):
        rows_m = zones_in.filter(pl.col("signal_date") == T).sort("rank")
        adm_m = month_admitted.get(T, set())
        cont_m = cont_zones.get(T, set())
        if Ti == 0:
            exp_syms: list[str] = []
            blocked_m: list[dict] = []
            ind_ct: Counter = Counter()
            for r in rows_m.iter_rows(named=True):
                if len(exp_syms) >= SLEEVE_K:
                    break
                if ind_ct.get(r["industry"], 0) >= IND_CAP:
                    blocked_m.append({"signal_date": str(T), "symbol":
                                      r["symbol"], "rank": int(r["rank"]),
                                      "industry": r["industry"]})
                    continue
                total = int(math.floor(r["w_t"] * ARMS_INITIAL_CASH
                                       / r["p0"] / 100)) * 100
                fracs = [float(x) for x in
                         str(r["ladder_fracs"]).split(",") if x.strip()]
                tiers_ok = False
                if total >= 100:
                    tiers_ok = any(
                        int(math.floor(f * total / 100)) * 100 >= 100
                        for f in fracs)
                if total < 100 or not tiers_ok:
                    continue
                exp_syms.append(r["symbol"])
                ind_ct[r["industry"]] += 1
            act = first_scan_adm[T]
            if set(exp_syms) != act:
                bad(f"month {T} first-scan admissions mismatch: expected "
                    f"{sorted(exp_syms)} engine {sorted(act)}")
            mid = adm_m - act
            if mid:
                log(f"    [{arm}] month {T}: mid-month admissions "
                    f"{len(mid)} (seats recycled intra-month)")
            ind_blocked.extend(blocked_m)
        else:
            ind_ct: Counter = Counter()
            for r in zones_res.filter(pl.col("signal_date") == T) \
                              .iter_rows(named=True):
                if r["symbol"] in adm_m:
                    ind_ct[r["industry"]] += 1
            seats = len(adm_m)
            for r in rows_m.iter_rows(named=True):
                sym = r["symbol"]
                if sym in adm_m:
                    continue
                if seats >= SLEEVE_K:
                    break          # seat-starved, not industry-blocked
                if ind_ct.get(r["industry"], 0) >= IND_CAP:
                    ind_blocked.append({"signal_date": str(T), "symbol": sym,
                                        "rank": int(r["rank"]),
                                        "industry": r["industry"]})
                    continue
                ind_ct[r["industry"]] += 1
                seats += 1
    checks["industry_blocked_reconstructed_n"] = len(ind_blocked)

    # -- (2) fills routing / limits / lots / fill-stop / TP prices ----------
    sds_by_sym: dict[str, list[date]] = {}
    for r in zones_in.iter_rows(named=True):
        sds_by_sym.setdefault(r["symbol"], []).append(r["signal_date"])
    sigma_by_sym_sd: dict[tuple[str, date], dict] = {}
    for r in zones_in.iter_rows(named=True):
        sigma_by_sym_sd[(r["symbol"], r["signal_date"])] = r

    def cur_row(sym: str, d: date, s: str | None = None) -> dict | None:
        """Zone row applicable at a decision key.  The month boundary for
        signal day T happens at the (T, pm) decision, so an (T, am) decision
        still runs on the PREVIOUS month's row (a zone continued at (T, pm)
        keeps its old sigma0 through that day's am session; the BR-7 refresh
        is a pm-boundary action).  s=None falls back to the old max <= d."""
        if s is None:
            cands = [sd for sd in sds_by_sym.get(sym, []) if sd <= d]
        else:
            cands = [sd for sd in sds_by_sym.get(sym, [])
                     if sd < d or (sd == d and s == "pm")]
        if not cands:
            return None
        return sigma_by_sym_sd[(sym, max(cands))]

    n_route = n_ladder_checked = n_tp_checked = 0
    tier_fills: Counter = Counter()
    wac_path = reconstruct_wac_path(fills, zones_in, build_term_keys(events))
    whipsaw_ladder_after_tp = 0
    tp_seen: set[tuple[str, str]] = set()   # (symbol, zone signal) with a TP fill
    for r in fills.iter_rows(named=True):     # engine booking order
        oid = r["order_id"]
        is_ladder = "-zladder-" in oid
        is_tp = "-ztp" in oid
        is_etf = bool(r["is_etf"])
        dd, dss = r["decision_date"], r["decision_session"]
        fd, fs = r["date"], r["session"]
        if r["fill_type"] in ("stop", "market_fallback"):
            continue          # different decision routing (BR-5 / B segment)
        if dss == "am":
            if is_etf or not (fs == "pm" and fd == dd):
                bad(f"routing {oid}: am decision -> ({fd},{fs})")
        else:
            if is_etf:
                if not (fs == "pm" and fd > dd):
                    bad(f"routing {oid}: ETF pm decision -> ({fd},{fs})")
            elif not (fs == "am" and fd > dd):
                bad(f"routing {oid}: pm decision -> ({fd},{fs})")
        n_route += 1
        if is_ladder:
            zr = cur_row(r["symbol"], dd, dss)
            a = ANCHORS.get((r["symbol"], sess_key(dd, dss)))
            if zr is None or a is None:
                bad(f"ladder fill {oid}: missing zone row / anchor")
                continue
            ti = int(oid.rsplit("-t", 1)[1])
            tier_fills[(r["symbol"], zr["signal_date"].isoformat(),
                        ti)] += 1
            off = [0.5, 1.5, 2.5][ti]
            want = a - off * float(zr["sigma0"])
            if abs(float(r["price"]) - want) > 1e-9:
                bad(f"ladder fill {oid}: price {r['price']} != anchor {a} "
                    f"- {off}*sigma0({zr['sigma0']}) = {want}")
            n_ladder_checked += 1
            if (r["symbol"], zr["signal_date"].isoformat()) in tp_seen:
                whipsaw_ladder_after_tp += 1
        if is_tp:
            zr = cur_row(r["symbol"], dd, dss)
            wp = wac_path.get(r["symbol"])
            if zr is None or wp is None or not wp["path"]:
                bad(f"tp fill {oid}: no WAC path / zone row to verify")
                continue
            # the TP limit price is fixed at EMISSION time: it uses the WAC
            # as known at the emitting decision point (verified per-fill:
            # e.g. a tier filling in the same session as the TP does NOT
            # change the TP price), so the snapshot is taken at the
            # DECISION key, not at the fill key
            wac_at = None
            for p in wp["path"]:
                if (p["date"], p["session"]) <= (dd, dss):
                    wac_at = p["wac"]
            if wac_at is None:
                bad(f"tp fill {oid}: no WAC snapshot at or before decision")
                continue
            sigma0 = float(zr["sigma0"])
            mults = ([float(zr["tp1_mult"]), float(zr["tp2_mult"])]
                     if zr["tp2_mult"] is not None else
                     [float(zr["tp1_mult"])])
            cands = [wac_at + mm * sigma0 for mm in mults]
            if not any(abs(float(r["price"]) - c) <= 1e-9 for c in cands):
                bad(f"tp fill {oid}: price {r['price']} not WAC+mult*sigma0 "
                    f"(WAC {wac_at}, sigma0 {sigma0}, cands {cands})")
            n_tp_checked += 1
            tp_seen.add((r["symbol"], zr["signal_date"].isoformat()))
    checks["fills_checked"] = {"routed": n_route,
                               "ladder_price": n_ladder_checked,
                               "tp_price": n_tp_checked}
    multi = {k: v for k, v in tier_fills.items() if v > 1}
    if multi:
        bad(f"tier fill-stop violated: {multi}")
    for r in zones_res.iter_rows(named=True):
        tfs = ([int(x) for x in r["tier_filled_shares"].split(",")]
               if r["tier_filled_shares"] else [])
        if sum(tfs) != r["shares_bought"]:
            bad(f"zone {r['symbol']} {r['signal_date']}: tier_filled sum "
                f"{sum(tfs)} != shares_bought {r['shares_bought']}")
    checks["whipsaw_ladder_fills_after_tp"] = whipsaw_ladder_after_tp

    # -- (3) cash conservation ----------------------------------------------
    fills_cash: dict[date, float] = {}
    for r in fills.iter_rows(named=True):
        fills_cash[r["date"]] = fills_cash.get(r["date"], 0.0) + \
            float(r["net_cash_flow"])
    ev_cash: dict[date, float] = {}
    for r in events.filter(pl.col("cash_amount").is_not_null()) \
                   .iter_rows(named=True):
        ev_cash[r["date"]] = ev_cash.get(r["date"], 0.0) + \
            float(r["cash_amount"])
    dates = daily["date"].to_list()
    cash_tot = (daily["settled_cash"] + daily["pending_am_to_pm"]
                + daily["pending_next_day"]).to_list()
    eq = daily["equity"].to_list()
    pv = daily["positions_value"].to_list()
    worst_cash = worst_eq = 0.0
    prev = ARMS_INITIAL_CASH
    for i, d in enumerate(dates):
        delta = cash_tot[i] - prev
        want = fills_cash.get(d, 0.0) + ev_cash.get(d, 0.0)
        worst_cash = max(worst_cash, abs(delta - want))
        if abs(delta - want) > 1e-6:
            bad(f"cash conservation {d}: daily delta {delta:.6f} != fills "
                f"{fills_cash.get(d, 0.0):.6f} + events "
                f"{ev_cash.get(d, 0.0):.6f}")
        prev = cash_tot[i]
        worst_eq = max(worst_eq, abs(eq[i] - (cash_tot[i] + pv[i])))
        if abs(eq[i] - (cash_tot[i] + pv[i])) > 1e-6:
            bad(f"equity identity {d}: equity {eq[i]} != cash {cash_tot[i]} "
                f"+ positions {pv[i]}")
    checks["cash_conservation_max_abs_err"] = worst_cash
    checks["equity_identity_max_abs_err"] = worst_eq

    # -- (4) stop-loss fills (line reconstruction, ratchet) ------------------
    stop_n = 0
    stop_open_at_limitdown = 0
    for r in fills.filter(pl.col("fill_type") == "stop").iter_rows(named=True):
        sym = r["symbol"]
        trig_key = sess_key(r["date"], r["session"])
        zrow_at_trig = cur_row(sym, r["decision_date"],
                               r["decision_session"])
        zres = zones_res.filter((pl.col("symbol") == sym)
                                & (pl.col("signal_date")
                                   == (zrow_at_trig["signal_date"]
                                       if zrow_at_trig else None)))
        ffk = (zres["first_fill_key"][0]
               if zres.height and zres["first_fill_key"][0] is not None
               else None)
        if zrow_at_trig is None or ffk is None:
            bad(f"stop fill {sym} {r['date']}: no zone row / first_fill_key")
            continue
        line = None
        hwm = None
        for k, a in ANCHORS_BY_SYM.get(sym, []):
            if k < ffk or k >= trig_key:
                continue
            # BR-5/S-v14-4 with the BR-7 continuation seam: the line is
            # ratcheted as max(HWM - stop_mult x sigma0) where HWM is the
            # running max of DECISION prices (kept across continuations)
            # and sigma0 is the zone row applicable at that decision date
            # (refreshed at continuation).  With a constant sigma0 this
            # reduces to the smoke-window formula max(a - mult x sigma0).
            hwm = a if hwm is None else max(hwm, a)
            ad_d, ad_s = key_to_ds(k)
            zr_k = cur_row(sym, ad_d, ad_s)
            if zr_k is None:
                continue
            cand = hwm - STOP_MULT * float(zr_k["sigma0"])
            line = cand if line is None else max(line, cand)
        op, low = HALF_OPENS.get((sym, trig_key), (None, None))
        if line is None or op is None:
            bad(f"stop fill {sym} {r['date']}: cannot reconstruct line/open")
            continue
        want = min(line, op)
        if abs(float(r["price"]) - want) > 1e-9:
            bad(f"stop fill {sym} {r['date']}: price {r['price']} != "
                f"min(line {line}, open {op}) = {want}")
        stop_n += 1
        if LIMIT_DOWN.get((sym, dint_of(r["date"]))) is not None \
                and op <= LIMIT_DOWN[(sym, dint_of(r["date"]))] + 1e-9:
            stop_open_at_limitdown += 1
    checks["stop_fills_checked"] = stop_n
    checks["stop_fills_open_at_limit_down"] = stop_open_at_limitdown

    # -- (4b) full-coverage stop-line cross-check vs zones_res ----------------
    # every zone's final ratcheted line = max(HWM_k - stop_mult x sigma0_k)
    # over decision anchors [first_fill_key, zone terminal event), with
    # sigma0 per the zone row applicable at each anchor (refreshed at
    # continuation).  The bound is the symbol's FIRST terminal event key
    # >= first_fill_key: one live zone per symbol, so that event belongs to
    # this zone (this also catches zone_exiting_boundary, whose detail
    # carries no "(signal ...)" part and which flips the zone out of the
    # "holding" phase BEFORE the same decision's HWM refresh).
    term_keys_all = build_term_keys(events)
    line_checked = line_bad = hwm_bad = 0
    for r in zones_res.iter_rows(named=True):
        if r["stop_line_final"] is None or r["first_fill_key"] is None:
            continue
        sym = r["symbol"]
        ffk = r["first_fill_key"]
        bound = None
        for k_t in term_keys_all.get(sym, []):
            if k_t >= ffk:
                bound = k_t
                break
        line = hwm = None
        for k, a in ANCHORS_BY_SYM.get(sym, []):
            if k < ffk or (bound is not None and k >= bound):
                continue
            hwm = a if hwm is None else max(hwm, a)
            ad_d, ad_s = key_to_ds(k)
            zr_k = cur_row(sym, ad_d, ad_s)
            if zr_k is None:
                continue
            cand = hwm - STOP_MULT * float(zr_k["sigma0"])
            line = cand if line is None else max(line, cand)
        line_checked += 1
        if line is None or abs(float(r["stop_line_final"]) - line) > 1e-9:
            line_bad += 1
            if line_bad <= 5:
                bad(f"stop_line_final {sym} {r['signal_date']}: engine "
                    f"{r['stop_line_final']} != reconstructed {line} "
                    f"(bound {bound})")
        if r["hwm_final"] is not None and (hwm is None
                                           or abs(float(r["hwm_final"])
                                                  - hwm) > 1e-9):
            hwm_bad += 1
            if hwm_bad <= 5:
                bad(f"hwm_final {sym} {r['signal_date']}: engine "
                    f"{r['hwm_final']} != reconstructed {hwm}")
    checks["stop_line_crosscheck"] = {"zones_checked": line_checked,
                                      "line_bad": line_bad,
                                      "hwm_bad": hwm_bad}

    # -- (5) gate 8 v1.4 structure -------------------------------------------
    zsa = events.filter(pl.col("event") == "zone_stop_armed").height
    if zsa != st["stop_armed_events"]:
        bad(f"zone_stop_armed events {zsa} != stats stop_armed_events "
            f"{st['stop_armed_events']}")
    ledger_n = (st["stop_armed_resolved_fallback"]
                + st["stop_armed_resolved_other"] + st["stop_armed_stuck_end"])
    if ledger_n != st["stop_armed_events"]:
        bad(f"armed ledger: events {st['stop_armed_events']} != fallback "
            f"{st['stop_armed_resolved_fallback']} + other "
            f"{st['stop_armed_resolved_other']} + stuck "
            f"{st['stop_armed_stuck_end']}")
    if st["stop_armed_stuck_end"] != 0:
        bad(f"STUCK != 0 hard assert: {st['stop_armed_stuck_end']}")
    deferral_ct = Counter(
        events.filter(pl.col("event").str.starts_with("market_exit_deferred"))
        ["event"].to_list())
    checks["gate8"] = {
        "armed_events": st["stop_armed_events"],
        "resolved_fallback": st["stop_armed_resolved_fallback"],
        "resolved_other": st["stop_armed_resolved_other"],
        "stuck_end": st["stop_armed_stuck_end"],
        "zone_stop_armed_events": zsa,
        "market_exit_deferred": dict(deferral_ct),
        "k3_armed_total": res.stats["k3_fallback"]["armed"],
        "k3_executed_total": res.stats["k3_fallback"]["executed"],
        "tp_expired_sessions": st["tp_expired_sessions"],
        "tier_expired": st["tier_expired"],
        "tier_invalidated": st["tier_invalidated"],
        "tier_below_min_lot": st["tier_below_min_lot"],
        "tier_cap_voided": st["tier_cap_voided"],
        "tp_below_min_lot": st["tp_below_min_lot"]}

    # -- (6) zone lifecycle events inventory ---------------------------------
    checks["zone_events"] = dict(Counter(
        events.filter(pl.col("event").str.starts_with("zone_"))
        ["event"].to_list()))
    checks["n_fills"] = fills.height
    checks["warnings_n"] = len(res.warnings)
    checks["warnings_sample"] = list(res.warnings)[:5]
    # dev freeze discipline: no fill outside the dev window
    oob = fills.filter((pl.col("date") < DEV_START) | (pl.col("date") > DEV_END))
    if oob.height:
        bad(f"{oob.height} fills outside the dev window")
    return checks


RESULTS: dict[str, dict] = {}
for arm in ARMS:
    zones_in = ZONES_FRAMES[arm]
    t_cfg = time.perf_counter()
    try:
        res = run_band_backtest_zones(
            zones_in, FRAMES["daily"], FRAMES["half"], FRAMES["limits"],
            FRAMES["splits"], FRAMES["cash_dividends"],
            FRAMES["instruments"], symbol_meta=SYMBOL_META,
            dividend_events=dividend_events, intents=LEG_FRAME,
            initial_cash=ARMS_INITIAL_CASH,
            zone_priority_base=ZONE_PRIORITY_BASE)
    except BandContractError as exc:
        _fail(f"{arm}: engine rejected inputs: {exc}")
    wall = time.perf_counter() - t_cfg
    log(f"  [{arm}] engine {wall:.1f}s, fills {res.fills.height}, "
        f"zones {res.zones.height}, admitted "
        f"{res.stats['zones']['n_admitted']} | rss {rss_gb():.2f} GB")
    checks = check_arm(arm, res, zones_in, ZONES_META[arm])
    checks["wall_s"] = wall
    RESULTS[arm] = {"checks": checks, "res": res}
    res.zones.write_parquet(out_dir / f"{arm}_zones.parquet")
    res.fills.write_parquet(out_dir / f"{arm}_fills.parquet")
    res.events.write_parquet(out_dir / f"{arm}_events.parquet")
    res.daily.write_parquet(out_dir / f"{arm}_daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / f"{arm}_clips_final.parquet")
    LEG_FRAME.write_parquet(out_dir / f"{arm}_intents.parquet")
    zones_in.write_parquet(out_dir / f"{arm}_zones_input.parquet")
    (out_dir / f"{arm}_stats.json").write_text(json.dumps(
        {"stats": res.stats, "warnings": list(res.warnings),
         "wall_s": wall}, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    check_budget(arm)
check_budget("all arm runs")

# === 11. metrics & gates ======================================================
log("== 11. metrics & gates (gates 1-7 R16 verbatim; gate 8 v1.4 caliber) ==")


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
             for sym, evs in SPLIT_EVENTS.items()}
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


def gate8_v14(arm: str) -> dict:
    """Gate 8, v1.4 caliber (frozen prereg sec 2; contract sec 10.1-5):
    armed = zone stop-loss triggerings that left shares unsellable
    (T+1 lock / suspension carryover; engine stats stop_armed_events);
    numerator = armed residuals resolved by the K=3 open-market fallback
    (stop_armed_resolved_fallback) + armed-then-self fills
    (stop_armed_resolved_other); delivery = numerator / armed >= 99%;
    stuck (still armed at data end) == 0 HARD ASSERT; TP expiries and
    buy-tier expiries are counted SEPARATELY and are NOT in the
    denominator."""
    res = RESULTS[arm]["res"]
    st = res.stats["zones"]
    armed = int(st["stop_armed_events"])
    fb = int(st["stop_armed_resolved_fallback"])
    other = int(st["stop_armed_resolved_other"])
    stuck = int(st["stop_armed_stuck_end"])
    problems = []
    if armed != fb + other + stuck:
        problems.append(f"armed ledger identity violated: {armed} != "
                        f"{fb}+{other}+{stuck}")
    if stuck != 0:
        problems.append(f"stuck != 0 hard assert: {stuck}")
    delivery = (fb + other) / armed if armed else None
    gate_pass = (stuck == 0) and (armed == 0 or delivery >= 0.99)
    # per-case ledger reconstructed from the event stream (attribution)
    ev, fills = res.events, res.fills
    fb_by: dict = {}
    for r in fills.filter(pl.col("fill_type") == "market_fallback") \
                  .iter_rows(named=True):
        fb_by.setdefault((r["date"], r["session"]), []).append(r["symbol"])
    mkt_seen: dict = {}
    open_cases: dict[str, dict] = {}
    ledger: list[dict] = []
    for r in ev.iter_rows(named=True):
        e = r["event"]
        d = r["detail"] or ""
        if e == "zone_stop_armed":
            sym = d.split(":", 1)[0]
            case = {"symbol": sym, "armed_at": f"{r['date']} {r['session']}",
                    "detail": d, "deferred": [], "resolved": None}
            open_cases[sym] = case
            ledger.append(case)
        elif e.startswith("market_exit_deferred"):
            sym = d.split(":", 1)[0]
            if sym in open_cases:
                open_cases[sym]["deferred"].append(
                    f"{e}@{r['date']} {r['session']}")
        elif e == "market_exit_filled":
            k = (r["date"], r["session"])
            mkt_seen[k] = mkt_seen.get(k, 0) + 1
            lst = fb_by.get(k, [])
            sym = lst[mkt_seen[k] - 1] if mkt_seen[k] <= len(lst) else "?"
            if sym in open_cases:
                open_cases[sym]["resolved"] = \
                    f"k3_fallback@{r['date']} {r['session']}"
                open_cases.pop(sym)
        elif e == "market_exit_void_no_position":
            sym = d.split(":", 1)[0]
            if sym in open_cases:
                open_cases[sym]["resolved"] = \
                    f"void_no_position@{r['date']} {r['session']}"
                open_cases.pop(sym)
        elif e == "zone_cooling" and "fully cleared" in d:
            sym = d.split(" (signal", 1)[0]
            if sym in open_cases:
                reason = d.split("fully cleared (", 1)[1].split(")", 1)[0]
                open_cases[sym]["resolved"] = \
                    f"self_cleared({reason})@{r['date']} {r['session']}"
                open_cases.pop(sym)
    walk_fb = sum(1 for c in ledger
                  if c["resolved"] and c["resolved"].startswith("k3_fallback"))
    walk_other = sum(1 for c in ledger
                     if c["resolved"] and c["resolved"].startswith("self"))
    walk_stuck = [c for c in ledger if c["resolved"] is None]
    if walk_fb != fb or walk_other != other or len(walk_stuck) != stuck:
        problems.append(f"event-walk ledger vs engine stats mismatch: "
                        f"fallback {walk_fb}vs{fb}, other {walk_other}vs{other},"
                        f" stuck {len(walk_stuck)}vs{stuck}")
    return {"armed": armed, "k3_fallback_fills": fb,
            "armed_then_self_fills": other, "stuck_final": stuck,
            "final_delivery_rate": delivery,
            "delivered": fb + other,
            "gate_pass": gate_pass,
            "problems": problems,
            "ledger_walk": {"cases": len(ledger), "fallback": walk_fb,
                            "self": walk_other, "stuck": len(walk_stuck)},
            "ledger_cases": ledger,
            "excluded_from_denominator": {
                "tp_expired_sessions": int(st["tp_expired_sessions"]),
                "tier_expired": int(st["tier_expired"]),
                "tier_invalidated": int(st["tier_invalidated"])},
            "caliber": "v1.4 (contract sec 10.1-5): armed = stop triggered "
                       "but unfilled carryovers (T+1/suspension); numerator "
                       "= k3 fallback fills + armed-then-self fills; >=99%; "
                       "stuck==0 hard assert; TP/buy expiries excluded"}


def equity_decomposition(arm: str) -> dict:
    """Daily stock-MV / etf-MV / cash split from fills x official closes;
    max-DD window attribution + component changes across the window
    (F3R3 equity_decomposition caliber)."""
    res = RESULTS[arm]["res"]
    dates = res.daily["date"].to_list()
    per: dict = {}
    for r in res.fills.select("symbol", "date", "side", "shares") \
                     .iter_rows(named=True):
        per.setdefault(r["symbol"], []).append(
            (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    mv_st, mv_et, cash, eq = [], [], [], []
    state: dict = {}
    for d, row in zip(dates, res.daily.iter_rows(named=True)):
        td = dint_of(d)
        s_st = s_et = 0.0
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
                    else:
                        s_st += mv
        mv_st.append(s_st)
        mv_et.append(s_et)
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
        out["window_decomposition"] = {
            "equity_change": eq[i1] - eq[i0],
            "stock_mv_change": mv_st[i1] - mv_st[i0],
            "etf_mv_change": mv_et[i1] - mv_et[i0],
            "cash_change": cash[i1] - cash[i0],
            "levels_at_peak": {"stock_mv": mv_st[i0], "etf_mv": mv_et[i0],
                               "cash": cash[i0], "equity": eq[i0]},
            "levels_at_trough": {"stock_mv": mv_st[i1], "etf_mv": mv_et[i1],
                                 "cash": cash[i1], "equity": eq[i1]}}
        # stop activity inside the window (gate-4 death attribution:
        # stop-loss exits vs path)
        wsel = res.fills.filter((pl.col("date") >= peak)
                                & (pl.col("date") <= trough))
        out["window_activity"] = {
            "stop_fills_n": int((wsel["fill_type"] == "stop").sum()),
            "stop_sell_notional": float(wsel.filter(
                pl.col("fill_type") == "stop")["notional"].sum()
                if wsel.height else 0.0),
            "market_fallback_fills_n": int(
                (wsel["fill_type"] == "market_fallback").sum()),
            "tp_fills_n": int(wsel.filter(
                pl.col("order_id").str.contains("-ztp")).height),
            "ladder_buy_fills_n": int(wsel.filter(
                pl.col("order_id").str.contains("-zladder-")).height)}
    return out


def tp_whipsaw_counts(arm: str) -> dict:
    """Gate-5 whipsaw bookkeeping (prereg sec 7): TP fills, tp_cleared
    zones, and same-symbol re-admissions after a TP clear; plus tier
    expiries (buy-side churn)."""
    res = RESULTS[arm]["res"]
    ev = res.events
    tp_fills = res.fills.filter(pl.col("order_id").str.contains("-ztp"))
    n_tp_fills = tp_fills.height
    tp_cleared = 0
    readmit_after_tp = 0
    had_tp: set[str] = set()
    for r in ev.iter_rows(named=True):
        e = r["event"]
        if e == "zone_cooling":
            d = r["detail"] or ""
            if "(tp_cleared)" in d:
                tp_cleared += 1
                had_tp.add(d.split(" (signal", 1)[0])
        elif e == "zone_admitted":
            d = r["detail"] or ""
            sym = d.split(" (signal", 1)[0]
            if sym in had_tp:
                readmit_after_tp += 1
    return {"tp_fills_n": int(n_tp_fills),
            "tp_sell_notional": float(tp_fills["notional"].sum()
                                      if n_tp_fills else 0.0),
            "tp_cleared_zones": tp_cleared,
            "re_admissions_after_tp_same_symbol": readmit_after_tp,
            "ladder_fills_after_tp_whipsaw":
                RESULTS[arm]["checks"]["whipsaw_ladder_fills_after_tp"],
            "tier_expired": int(res.stats["zones"]["tier_expired"]),
            "tier_invalidated": int(res.stats["zones"]["tier_invalidated"])}


metrics: dict = {}
gates: dict = {}
for arm in ARMS:
    res = RESULTS[arm]["res"]
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
    g8 = gate8_v14(arm)
    for p in g8["problems"]:
        RESULTS[arm]["checks"]["fail"].append(f"gate8: {p}")
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
         "goal_dev_net_cagr_ge_10pct": net_cagr >= GOAL_CAGR,
         "gate8_v14_final_delivery": g8,
         "k3_fallback_comparison": {
             "armed_total": int(res.stats["k3_fallback"]["armed"]),
             "executed_total": int(res.stats["k3_fallback"]["executed"]),
             "note": "engine-wide K=3 counter incl. ETF-leg risk rows; "
                     "gate 8 v1.4 uses the ZONE stop counters only"}}
    g = {"1_net_cagr_gt_0": net_cagr > 0,
         "2_excess_vs_B1m_ge_2pp": excess >= 0.020,
         "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
         "4_mdd_le_20pct_and_le_B1m":
             abs(mdd) <= 0.20 + 1e-12
             and abs(mdd) <= abs(B1["b1m_max_drawdown"]) + 1e-12,
         "5_one_side_turnover_le_6": m["max_one_side_turnover"] <= 6.0,
         "6_single_name_weight_le_40pct": wmax <= 0.40,
         "7_vs_B3prime_plus_1pp": net_cagr >= B3P[B1_PATH_NAME] + 0.010,
         "8_final_delivery_ge_99pct_v14": g8["gate_pass"],
         "advantage_years": len(adv), "dev_excess_vs_b1m": excess}
    g["failed_gates"] = sorted(k for k in GATE_KEYS if not g[k])
    g["dev_pass"] = not g["failed_gates"]
    g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"
    g["goal_criterion_dev_cagr_ge_10pct"] = m["goal_dev_net_cagr_ge_10pct"]
    g["goal_met"] = bool(g["dev_pass"] and m["goal_dev_net_cagr_ge_10pct"])
    g["checks_pass"] = not RESULTS[arm]["checks"]["fail"]
    metrics[arm] = m
    gates[arm] = {"dev": g, "verdict": g["verdict"]}
    d8v = "n/a(0 armed)" if g8["final_delivery_rate"] is None \
        else f"{g8['final_delivery_rate'] * 100:.1f}%"
    log(f"  {arm}: net {net_cagr * 100:+.2f}% excess {excess * 100:+.2f}pp "
        f"adv {len(adv)}/6 mdd {mdd * 100:.2f}% turn "
        f"{m['max_one_side_turnover']:.2f} w {wmax * 100:.1f}% g8 "
        f"{g8['k3_fallback_fills']}+{g8['armed_then_self_fills']}/"
        f"{g8['armed']}={d8v} stuck {g8['stuck_final']} "
        f"goal10 {m['goal_dev_net_cagr_ge_10pct']} -> "
        f"{'PASS' if g['dev_pass'] else 'eliminated ' + str(g['failed_gates'])}")
check_budget("metrics & gates")

# === 12. death attribution (per arm; prereg sec 7 focus gates 3/4/5/8) =======
log("== 12. death attribution ==")
ATTRIBUTION: dict[str, dict] = {}
for arm in ARMS:
    g = gates[arm]["dev"]
    m = metrics[arm]
    attr: dict = {"failed_gates": g["failed_gates"]}
    if "3_advantage_years_ge_5_of_6" in g["failed_gates"]:
        attr["gate3_years"] = {
            str(y): {"arm": m["net_return_by_year"].get(y),
                     "b1m": {int(k): v for k, v in
                             B1["b1m_net_return_by_year"].items()}.get(y),
                     "advantage": y in m["advantage_years_list"]}
            for y in sorted(m["net_return_by_year"])}
    if "4_mdd_le_20pct_and_le_B1m" in g["failed_gates"]:
        attr["gate4_drawdown"] = equity_decomposition(arm)
    if "5_one_side_turnover_le_6" in g["failed_gates"]:
        attr["gate5_turnover"] = {
            "max_one_side_turnover": m["max_one_side_turnover"],
            "by_year": {str(y): round(v["one_side_turnover"], 3)
                        for y, v in m["turnover_by_year"].items()},
            "whipsaw": tp_whipsaw_counts(arm)}
    if "8_final_delivery_ge_99pct_v14" in g["failed_gates"]:
        attr["gate8_armed_ledger"] = {
            "summary": {k: metrics[arm]["gate8_v14_final_delivery"][k]
                        for k in ("armed", "k3_fallback_fills",
                                  "armed_then_self_fills", "stuck_final",
                                  "final_delivery_rate")},
            "unresolved_cases": [c for c in
                                 metrics[arm]["gate8_v14_final_delivery"]
                                 ["ledger_cases"] if c["resolved"] is None],
            "deferred_repeats": Counter(
                d for c in metrics[arm]["gate8_v14_final_delivery"]
                ["ledger_cases"] for d in c["deferred"])}
    ATTRIBUTION[arm] = attr
    log(f"  {arm}: attribution {list(attr)}")

# === 13. stop-rule verdict (F4R2 prereg sec 7) + dose-response ===============
log("== 13. stop-rule verdict (F4R2 prereg sec 7) + dose-response ==")
n_pass = sum(1 for arm in ARMS if gates[arm]["dev"]["dev_pass"])
n_goal = sum(1 for arm in ARMS if gates[arm]["dev"]["goal_met"])
winner = [arm for arm in ARMS if gates[arm]["dev"]["goal_met"]]

# dose-response gradient (F4R2 prereg sec 1): TP tiers weak -> strong
# C (2sigma one-shot) < A (2sigma/50% + 3sigma/clear) < D2 (4sigma/50%
# + 5sigma/clear) < D1 (none); monotone net-CAGR ordering strengthens the
# H1 causal reading, disorder means the TP tier is not the only factor.
f4r1_mg = json.loads((F4R1_FULL_RUN / "outputs/metrics_and_gates.json")
                     .read_text(encoding="utf-8"))
DOSE_TP_FORM = {
    "F4R1-C": "2.0sigma one-shot full sell (tp1 2.0/1.0, tp2 null)",
    "F4R1-A": "2.0sigma sell 50% + 3.0sigma clear (tp1 2.0/0.5, tp2 3.0/1.0)",
    "F4R2-D2": "4.0sigma sell 50% + 5.0sigma clear (config zones_D2; "
               "F4R2-S2 designed 2x widening, not historical tuning)",
    "F4R2-D1": "DISABLED (v1.4.1 zero-tier: null tp1/tp2; exits = 3-sigma "
               "ratchet stop + 3.5-sigma invalidation only)",
}
DOSE_ORDER = ["F4R1-C", "F4R1-A", "F4R2-D2", "F4R2-D1"]


def _dose_entry(src_arm: str) -> dict:
    if src_arm in metrics:
        m, g = metrics[src_arm], gates[src_arm]["dev"]
    else:                       # F4R1 comparator arms (frozen upstream run)
        m, g = f4r1_mg["metrics"][src_arm], f4r1_mg["gates"][src_arm]["dev"]
    return {"tp_form": DOSE_TP_FORM[src_arm],
            "net_cagr": m["net_cagr"],
            "net_total_return": m["net_total_return"],
            "max_drawdown": m["max_drawdown"],
            "net_return_by_year": {int(k): v for k, v in
                                   m["net_return_by_year"].items()},
            "advantage_years": int(g["advantage_years"]),
            "advantage_years_list": m["advantage_years_list"],
            "max_one_side_turnover": m["max_one_side_turnover"],
            "failed_gates": g["failed_gates"],
            "source_run": RUN_DIR.name if src_arm in metrics
            else F4R1_FULL_RUN.name}


DOSE_RESPONSE = {
    "hypothesis_gradient_weak_to_strong_tp": DOSE_ORDER,
    "entries": {a: _dose_entry(a) for a in DOSE_ORDER},
    "net_cagr_monotonic_C_lt_A_lt_D2_lt_D1": bool(
        _dose_entry("F4R1-C")["net_cagr"] < _dose_entry("F4R1-A")["net_cagr"]
        < _dose_entry("F4R2-D2")["net_cagr"]
        < _dose_entry("F4R2-D1")["net_cagr"]),
}
log("  dose-response net CAGR: " + " | ".join(
    f"{a} {_dose_entry(a)['net_cagr'] * 100:+.2f}%" for a in DOSE_ORDER)
    + f" -> monotonic={DOSE_RESPONSE['net_cagr_monotonic_C_lt_A_lt_D2_lt_D1']}")

# stop-rule zone verdict on D1 (F4R2 prereg sec 7; CAGR caliber per prereg
# sec 1: H1 zone >= +3%, H0 zone < +2%, in between = middle zone; D1 gate 4
# must also survive for the H1 zone)
d1_cagr = metrics["F4R2-D1"]["net_cagr"]
d1_gate4_ok = gates["F4R2-D1"]["dev"]["4_mdd_le_20pct_and_le_B1m"]
if winner:
    STOP_NOTE = (f"RARE CASE per F4R2 prereg sec 7: {len(winner)}/{len(ARMS)} "
                 f"arm(s) dev_pass AND dev net CAGR >= 10% "
                 f"({', '.join(winner)}): STOP and present to user; val "
                 "(2021-2024) consumption requires explicit user approval.")
elif d1_cagr >= 0.03 and d1_gate4_ok:
    STOP_NOTE = (f"H1 ZONE: D1 net CAGR {d1_cagr * 100:+.2f}% >= +3% and D1 "
                 "gate 4 passed (the ratchet stop carries drawdown control "
                 "alone): report the dose-response gradient and present to "
                 "user; folding into the R3-06 enhancement sleeve vs further "
                 "tuning is the user's decision; no F4R3, val zero contact.")
elif d1_cagr < 0.02:
    STOP_NOTE = (f"H0 ZONE: D1 net CAGR {d1_cagr * 100:+.2f}% < +2% (no "
                 "material difference from F4R1-A +0.02%): the return "
                 "collapse comes from the stop/ladder/recycling execution "
                 "components themselves, not from the fixed take-profit -> "
                 "F-line execution-layer conclusion CLOSED; present to user; "
                 "no F4R3, val zero contact.")
else:
    STOP_NOTE = (f"MIDDLE ZONE: D1 net CAGR {d1_cagr * 100:+.2f}% in "
                 "[+2%, +3%) or D1 gate 4 broken: attribution report to "
                 "user; no F4R3, val zero contact.")
log("  " + STOP_NOTE)

DISCLOSURES = [
    "行业成员使用申万 L1 2026 单快照（前视，沿 F3R3 披露；prereg sec 3）。",
    "σ0 月内冻结不重估（信号日 21 个官方收盘含当日，20 个 close-to-close "
    "对数收益样本标准差 ddof=1，原始未复权收盘；次新不足或停牌缺收盘剔除"
    "并计数）。",
    "止损同 session 先于止盈判定（保守；引擎 BR-5 在 A/B/C 段之前执行 "
    "stop 段并取消同 session 阶梯与止盈单；D1 无止盈层，该序仅涉 D2 与"
    "失效/阶梯的取消关系）。",
    "止盈成交不撤在途买入档（TP 不撤 ladder；鞭打风险按门 5 计数裁定；"
    "D1 无止盈层，无此来源的鞭打）。",
    "HWM 用决策价（am.close / 官方收盘）而非日内 high（更晚触发，保守）。",
    "买入近沿成交（P-0.5/1.5/2.5σ0 限价，不取区内更优价，保守）。",
    "门 8 分母只含止损触发未成交留滞（TP 到期/买入档到期单独计数，"
    "不计入交付率分母）。",
    "F4R1-S1 接缝（预登记 §11 裁定接受，全期沿冒烟口径）：ETF 腿意图优先级 "
    "10^6 → 999（引擎 BR-1 护栏要求意图优先级 < zone_priority_base=1000）；"
    "语义影响 = 同决策点现金竞争中 ETF 底盘腿先于个股阶梯拿资金（F3R3 中"
    "相反，但 F3R3 无 zones 层，不构成同口径对照差异）。",
    "F4R1-S2 不适用于 F4R2：本运行无路径缩放臂（两臂 w_T 恒 0.06），"
    "月末减仓原语缺失问题不涉及（F4R2 预登记 §6 沿承披露）。",
    "F3 复合因子身份沿承：F3R1 冻结输出（v1.3 引擎 pin 84a2443a 产出，"
    "本运行亲验 provenance）；本运行不重算因子。",
    "dev 样本内结果（2015-01-05..2020-12-31）；历史样本已被旧项目反复查看，"
    "不构成全新样本外；不构成任何盈利承诺。",
    "F4R2-S1 裁定落地（引擎变更披露）：v1.4 对帧层止盈禁用三种形式全部 "
    "fail-closed 拒绝（本 run 目录首轮实施因此停机，证据 tmp/"
    "s1_tp_disable_probe_result_v14.json）；主对话双签最小扩展 v1.4.1"
    "（tp1/tp2 列可选，null/缺列 = 零档止盈、无止盈意图发射，供值时全部 "
    "v1.4 断言原样保留，新护栏 tp1 null + tp2 供值拒绝）并重 pin "
    "a01cb29c…；本运行启动/结束均亲验该 pin，v1.4.1 行为先行复验"
    "（tmp/s1_tp_disable_probe_result_v141.json）。D1 采用 null 形式；"
    "NaN 形式不可用（按供值非法拒绝）；未使用超大 mult hack。",
    "F4R2-S2：D2 档位 b1=+4σ 卖 50%、b2=+5σ 清仓为设计选择（F4R1 档位 "
    "2σ/3σ 的等比放宽），非历史调参；成本锚定 WAC、不重锚、无兜底。",
    "剂量梯度对照臂 F4R1-C/F4R1-A 数字取自 F4R1 冻结全期运行"
    "（20260920T020201-f4r1-full-a3b7 metrics_and_gates.json），未重跑。",
]

# === 14. report + metrics_and_gates.json + manifest ==========================
log("== 14. report + metrics_and_gates.json + manifest ==")
ENGINE_SHA_AT_END = sha256_file(ENGINE_PY)

mg = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260920-zone-sheet-f4r2",
    "scope": "FULL DEV 2015-01-05..2020-12-31, two arms (F4R2-D1 stop-only, "
             "F4R2-D2 widened 4/5-sigma TP) + F4R2-A0 anchor; eight frozen "
             "gates carried verbatim from F4R1 prereg sec 2 (per F4R2 "
             "prereg sec 2)",
    "started_at_utc": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "engine": {"path": str(ENGINE_PY),
               "sha256_at_start": ENGINE_SHA_AT_START,
               "sha256_at_end": ENGINE_SHA_AT_END,
               "sha256_pin_expected": ENGINE_SHA_EXPECT_FULL,
               "bytes_modified_by_this_run":
                   ENGINE_SHA_AT_START != ENGINE_SHA_AT_END,
               "version": ENGINE_VERSION_NOTE},
    "dev_window": {"start": str(DEV_START), "end": str(DEV_END),
                   "signal_days": len(sig_days),
                   "val_policy": "2021-2024 zero contact (hard filters)"},
    "anchors": pins["gate_anchors"],
    "gate_definitions": {
        "1": "net CAGR > 0", "2": "excess vs B1(m) >= +2pp",
        "3": "advantage years >= 5 of 6 (vs B1(m) year returns)",
        "4": "|maxDD| <= 20% AND <= |B1(m) maxDD|",
        "5": "max one-side turnover <= 6 (buy notional / mean equity, per year)",
        "6": "max single-name weight <= 40% (daily, official closes)",
        "7": "net CAGR >= B3'(T200-40) + 1pp",
        "8": "v1.4 delivery: (k3 fallback fills + armed-then-self fills) / "
             "armed >= 99%; stuck == 0 hard assert; TP/buy expiries excluded"},
    "parameters": {"K": SLEEVE_K, "top_2k": TOP_2K, "ind_cap": IND_CAP,
                   "buffer_mult": BUFFER_MULT, "stop_mult": STOP_MULT,
                   "invalid_mult": INVALID_MULT,
                   "ladder_offsets": LADDER_OFFSETS,
                   "ladder_fracs": LADDER_FRACS,
                   "tp_D1": "DISABLED (zero-tier: null tp1/tp2, v1.4.1 "
                            "contract sec 10.8; F4R2-S1 adjudicated form)",
                   "tp_D2": "tp1 4.0/0.5 + tp2 5.0/1.0 (config zones_D2; "
                            "F4R2-S2 designed 2x widening)",
                   "w_T_both_arms": SLEEVE_W_ON,
                   "initial_cash_arms": ARMS_INITIAL_CASH,
                   "initial_cash_anchor": ANCHOR_INITIAL_CASH,
                   "zone_priority_base": ZONE_PRIORITY_BASE,
                   "sigma_lookback_returns": SIGMA_LOOKBACK,
                   "sigma_ddof": SIGMA_DDOF,
                   "sigma_closes": "21 official closes incl. signal day"},
    "metrics": metrics,
    "gates": gates,
    "attribution": ATTRIBUTION,
    "dose_response": DOSE_RESPONSE,
    "s1_seam_adjudication": {
        "seam": "F4R2-S1 (tp-disable expression)",
        "v14_probe_result": "frame-level infeasible (null -> TypeError, "
                            "NaN/absent -> BandContractError); aborted pass "
                            "evidence tmp/s1_tp_disable_probe_result_v14.json",
        "resolution": "main-conversation dual-sign minimal engine extension "
                      "v1.4.1 (tp1/tp2 optional; null/absent = zero-tier TP, "
                      "no profit intent; supplied-value asserts kept; new "
                      "guardrail tp1-null-with-tp2 rejected) + re-pin",
        "engine_pin_v141": ENGINE_SHA_EXPECT_FULL,
        "v141_reverification": "tmp/s1_tp_disable_probe_result_v141.json "
                               "(adjudicated_form_ok=true; null vs "
                               "column-absent outputs field-equal on all "
                               "five frames)",
        "d1_form_used": "NULL tp1/tp2 (NaN form unusable; oversized-mult "
                        "hack forbidden by prereg sec 6)"},
    "trial_accounting": {
        "strategy_line": "273 -> 275 booked at THIS run (two arm trials; "
                         "F4R2-A0 anchor consumes no trial)",
        "registered_in": "main-conversation trial ledger",
        "factor_line_FT01": 120,
        "aborted_first_pass": "F4R2-S1 stop happened BEFORE any arm ran; "
                              "zero trials consumed in the aborted pass"},
    "disclosures": DISCLOSURES,
    "stop_rule": {"note": STOP_NOTE,
                  "zone_verdict_d1": (
                      "rare_case" if winner else
                      "H1_zone" if d1_cagr >= 0.03 and d1_gate4_ok else
                      "H0_zone" if d1_cagr < 0.02 else "middle_zone"),
                  "d1_net_cagr": d1_cagr,
                  "d1_gate4_pass": d1_gate4_ok,
                  "any_arm_goal_met": bool(winner),
                  "arms_dev_pass": n_pass,
                  "advanced_to_validation": False,
                  "val_consumed": False,
                  "f4r3_opened": False},
    "f4r2_a0_anchor": {**{k: v for k, v in A0_CMP.items()},
                       "rule": "filecmp byte comparison vs F3R3-A0 outputs; "
                               "mismatch = STOP before arms (F4R2 prereg "
                               "sec 4)"},
}
(out_dir / "metrics_and_gates.json").write_text(
    json.dumps(mg, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")

# ---- report ---------------------------------------------------------------
lines = ["# F4R2 纯止损消融全期运行报告（exp-20260920-zone-sheet-f4r2，"
         "dev 2015–2020）", "",
         f"- 运行 `{RUN_DIR.name}`；引擎 v1.4.1 sha256:16 "
         f"`{ENGINE_SHA_AT_START[:16]}`（运行前后一致，双签 pin "
         f"`{ENGINE_SHA_EXPECT_FULL[:16]}`，F4R2-S1 裁定落地）；预登记 "
         f"sha256:16 `{pins['prereg']['sha256'][:16]}`；配置 sha256:16 "
         f"`{pins['f4r2_config']['sha256'][:16]}`（冻结，唯一参数来源）。",
         f"- 臂定义：F4R2-D1 = 止盈禁用（v1.4.1 零档 null tp1/tp2，无止盈"
         "意图发射）；F4R2-D2 = 宽档止盈 b1=+4σ 卖 50%、b2=+5σ 清仓"
         "（zones_D2，F4R2-S2 设计放宽）。其余全部沿 F4R1-A 底盘逐字。",
         f"- 窗口：dev {DEV_START}..{DEV_END}，{len(sig_days)} 个信号日；"
         "2021–2024 val 零接触（全部数据帧硬过滤 dev 边界 + 引擎 assert_frozen）。",
         "- **性质声明：dev 样本内结果，不构成任何盈利承诺；val 未消费；"
         "历史样本已被旧项目反复查看，不构成全新样本外。**",
         "- A0 锚：R3-06 逐字（200k，rotation UNI6），五帧 filecmp 逐字节"
         "比对 F3R3-A0 输出（前置门槛，不符即中止）。", "",
         "## 一、A0 锚比对（filecmp 逐字节）", "",
         "| 帧 | 逐字节相等 | 行数相等 |", "|---|---|---|"]
for name, v in A0_CMP.items():
    lines.append(f"| {name} | {'PASS' if v['byte_equal'] else 'FAIL'} "
                 f"| {'PASS' if v['rows_equal'] else 'FAIL'} |")
lines += ["", "## 二、八门判定总表（判据冻结于预登记 §2）", "",
          "锚点：B1(m) = R16 C05 T200-40 rate-only 净 "
          f"{B1['b1m_net_cagr'] * 100:+.2f}%、maxDD "
          f"{B1['b1m_max_drawdown'] * 100:.2f}%；B3′(T200-40) = "
          f"{B3P['T200-40']:.4f}。目标列 = dev 净 CAGR ≥ 10%；"
          "goal_met = dev_pass ∧ 目标列。", "",
          "| 门 | 判据 | " + " | ".join(ARMS) + " |",
          "|---|---|" + "---|" * len(ARMS)]


def fmt_pct(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x * 100:+.{digits}f}%"


for gi, (gk, gtxt) in enumerate([
        ("1_net_cagr_gt_0", "净 CAGR > 0"),
        ("2_excess_vs_B1m_ge_2pp", "超额 vs B1(m) ≥ +2pp"),
        ("3_advantage_years_ge_5_of_6", "优势年 ≥ 5/6"),
        ("4_mdd_le_20pct_and_le_B1m", "|maxDD| ≤ 20% 且 ≤ |B1(m)|"),
        ("5_one_side_turnover_le_6", "单边换手 ≤ 6"),
        ("6_single_name_weight_le_40pct", "单票权重 ≤ 40%"),
        ("7_vs_B3prime_plus_1pp", "净 CAGR ≥ B3′+1pp"),
        ("8_final_delivery_ge_99pct_v14", "门8 交付率 ≥ 99%（v1.4）")], 1):
    cells = []
    for arm in ARMS:
        g = gates[arm]["dev"]
        ok = g[gk]
        detail = ""
        m = metrics[arm]
        if gi == 1:
            detail = f"（{fmt_pct(m['net_cagr'])}）"
        elif gi == 2:
            detail = f"（{fmt_pct(m['excess_vs_b1m'])}）"
        elif gi == 3:
            detail = f"（{g['advantage_years']}/6）"
        elif gi == 4:
            detail = f"（{m['max_drawdown'] * 100:.2f}%）"
        elif gi == 5:
            detail = f"（{m['max_one_side_turnover']:.2f}）"
        elif gi == 6:
            detail = f"（{m['max_single_name_weight'] * 100:.1f}%）"
        elif gi == 7:
            detail = (f"（{fmt_pct(m['net_cagr'])} vs "
                      f"{fmt_pct(B3P[B1_PATH_NAME] + 0.010)}）")
        elif gi == 8:
            g8 = m["gate8_v14_final_delivery"]
            detail = (f"（{g8['delivered']}/{g8['armed']}="
                      f"{'n/a' if g8['final_delivery_rate'] is None else format(g8['final_delivery_rate'] * 100, '.1f') + '%'}"
                      f"，stuck {g8['stuck_final']}）")
        cells.append(f"{'PASS' if ok else 'FAIL'}{detail}")
    lines.append(f"| 门{gi} | {gtxt} | " + " | ".join(cells) + " |")
lines.append("| 目标列 | dev 净 CAGR ≥ 10% | "
             + " | ".join(f"{fmt_pct(metrics[a]['net_cagr'])}"
                          f"{'（达标）' if metrics[a]['goal_dev_net_cagr_ge_10pct'] else ''}"
                          for a in ARMS) + " |")
lines.append("| **dev_pass** | 八门全过 | "
             + " | ".join(("**PASS**" if gates[a]["dev"]["dev_pass"]
                           else "eliminated " + str(gates[a]["dev"]["failed_gates"]))
                          for a in ARMS) + " |")
lines.append("| **goal_met** | dev_pass ∧ ≥10% | "
             + " | ".join(("**YES**" if gates[a]["dev"]["goal_met"] else "no")
                          for a in ARMS) + " |")
lines += ["", "### 汇总指标", "",
          "| 指标 | " + " | ".join(ARMS) + " |",
          "|---|" + "---|" * len(ARMS)]
for label, fn in [
        ("净 CAGR", lambda a: fmt_pct(metrics[a]["net_cagr"])),
        ("净总收益", lambda a: fmt_pct(metrics[a]["net_total_return"])),
        ("maxDD", lambda a: f"{metrics[a]['max_drawdown'] * 100:.2f}%"),
        ("超额 vs B1(m)", lambda a: fmt_pct(metrics[a]["excess_vs_b1m"])),
        ("优势年", lambda a: f"{gates[a]['dev']['advantage_years']}/6 "
                             f"{metrics[a]['advantage_years_list']}"),
        ("最大单边换手", lambda a: f"{metrics[a]['max_one_side_turnover']:.2f}"),
        ("最大单票权重", lambda a: f"{metrics[a]['max_single_name_weight'] * 100:.1f}%"),
        ("门8 交付率", lambda a: (
            "n/a(0 armed)" if metrics[a]["gate8_v14_final_delivery"]["final_delivery_rate"] is None
            else f"{metrics[a]['gate8_v14_final_delivery']['final_delivery_rate'] * 100:.1f}%"
                 f"（{metrics[a]['gate8_v14_final_delivery']['k3_fallback_fills']} k3 + "
                 f"{metrics[a]['gate8_v14_final_delivery']['armed_then_self_fills']} self / "
                 f"armed {metrics[a]['gate8_v14_final_delivery']['armed']}，"
                 f"stuck {metrics[a]['gate8_v14_final_delivery']['stuck_final']}）")),
        ("止盈成交笔数", lambda a: str(tp_whipsaw_counts(a)["tp_fills_n"])),
        ("runner 核对", lambda a: "PASS" if gates[a]["dev"]["checks_pass"]
         else "FAIL: " + str(RESULTS[a]["checks"]["fail"][:3]))]:
    lines.append(f"| {label} | " + " | ".join(fn(a) for a in ARMS) + " |")

lines += ["", "### 分年净收益（vs B1(m)，优势年加 *）", "",
          "| 年 | " + " | ".join(ARMS) + " | B1(m) |", "|---|" + "---|" * (len(ARMS) + 1)]
b1y_all = {int(k): v for k, v in B1["b1m_net_return_by_year"].items()}
for y in sorted(b1y_all):
    row = [str(y)]
    for a in ARMS:
        v = metrics[a]["net_return_by_year"].get(y)
        star = "*" if y in metrics[a]["advantage_years_list"] else ""
        row.append(fmt_pct(v) + star)
    row.append(fmt_pct(b1y_all[y]))
    lines.append("| " + " | ".join(row) + " |")

lines += ["", "## 三、死因归因与剂量梯度（F4R2 预登记 §7 重点门 3/4/5/8）", ""]
for arm in ARMS:
    attr = ATTRIBUTION[arm]
    if not attr["failed_gates"] and gates[arm]["dev"]["checks_pass"]:
        lines.append(f"### {arm} —— 全门通过", "")
        continue
    lines.append(f"### {arm} —— 淘汰门 {attr['failed_gates']}"
                 + ("" if gates[arm]["dev"]["checks_pass"]
                    else "（另有 runner 核对 FAIL，见下）"))
    lines.append("")
    if "gate3_years" in attr:
        lines += ["- 门 3 分年：",
                  "  | 年 | 臂 | B1(m) | 优势 |",
                  "  |---|---|---|---|"]
        for y, v in attr["gate3_years"].items():
            lines.append(f"  | {y} | {fmt_pct(v['arm'])} | {fmt_pct(v['b1m'])} "
                         f"| {'是' if v['advantage'] else '否'} |")
    if "gate4_drawdown" in attr:
        gd = attr["gate4_drawdown"]
        lines.append(f"- 门 4 回撤：maxDD {gd['mdd_window']['max_drawdown'] * 100:.2f}%，"
                     f"窗口 {gd['mdd_window']['peak_date']} → "
                     f"{gd['mdd_window']['trough_date']}。")
        if "window_decomposition" in gd:
            w = gd["window_decomposition"]
            lines.append(f"  - 窗口分解：权益变动 {w['equity_change']:+,.0f} = "
                         f"股票市值 {w['stock_mv_change']:+,.0f} + ETF 市值 "
                         f"{w['etf_mv_change']:+,.0f} + 现金 {w['cash_change']:+,.0f}"
                         f"（臂内无 T200-40 路径原语，回撤来自股票袖珍；"
                         "止损活动见下）。")
        if "window_activity" in gd:
            wa = gd["window_activity"]
            lines.append(f"  - 窗口内止损成交 {wa['stop_fills_n']} 笔"
                         f"（卖出额 {wa['stop_sell_notional']:,.0f}），"
                         f"k3 兜底 {wa['market_fallback_fills_n']} 笔，"
                         f"止盈 {wa['tp_fills_n']} 笔，阶梯买入 "
                         f"{wa['ladder_buy_fills_n']} 笔。")
    if "gate5_turnover" in attr:
        gt = attr["gate5_turnover"]
        lines.append(f"- 门 5 换手：最大单边换手 {gt['max_one_side_turnover']:.2f}"
                     f"（分年 {gt['by_year']}）。鞭打计数：止盈成交 "
                     f"{gt['whipsaw']['tp_fills_n']} 笔"
                     f"（{gt['whipsaw']['tp_sell_notional']:,.0f}），"
                     f"tp_cleared 区 {gt['whipsaw']['tp_cleared_zones']} 个，"
                     f"同票止盈后再准入 {gt['whipsaw']['re_admissions_after_tp_same_symbol']} 次，"
                     f"止盈后阶梯继续成交 {gt['whipsaw']['ladder_fills_after_tp_whipsaw']} 笔，"
                     f"买入档到期 {gt['whipsaw']['tier_expired']}、失效 "
                     f"{gt['whipsaw']['tier_invalidated']}。")
    if "gate8_armed_ledger" in attr:
        ga = attr["gate8_armed_ledger"]
        s = ga["summary"]
        lines.append(f"- 门 8 armed 台账：armed {s['armed']}，k3 兜底 "
                     f"{s['k3_fallback_fills']}，armed 后自行成交 "
                     f"{s['armed_then_self_fills']}，滞留 {s['stuck_final']}，"
                     f"交付率 {fmt_pct(s['final_delivery_rate'])}。")
        if ga["unresolved_cases"]:
            lines.append("  - 未解决案例：")
            for c in ga["unresolved_cases"][:20]:
                lines.append(f"    - {c['symbol']} armed@{c['armed_at']}: "
                             f"{c['detail']}")
    if not gates[arm]["dev"]["checks_pass"]:
        lines.append("- runner 核对 FAIL：")
        for msg in RESULTS[arm]["checks"]["fail"][:20]:
            lines.append(f"  - {msg}")
    lines.append("")

lines += ["", "### 剂量-响应梯度（止盈档位弱 → 强：C < A < D2 < D1）", "",
          "对照臂 F4R1-C/F4R1-A 数字取自 F4R1 冻结全期运行 "
          "`20260920T020201-f4r1-full-a3b7`（未重跑）；优势年 = vs B1(m) "
          "分年净收益；* = 优势年。", "",
          "| 臂 | 止盈形式 | 净 CAGR | maxDD | 优势年 | 2015 | 2016 | 2017 "
          "| 2018 | 2019 | 2020 | 淘汰门 |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
b1y_dose = {int(k): v for k, v in B1["b1m_net_return_by_year"].items()}
for a in DOSE_ORDER:
    e = DOSE_RESPONSE["entries"][a]
    yrs = " | ".join(
        fmt_pct(e["net_return_by_year"].get(y))
        + ("*" if y in e["advantage_years_list"] else "")
        for y in sorted(b1y_dose))
    lines.append(
        f"| {a} | {e['tp_form']} | {fmt_pct(e['net_cagr'])} | "
        f"{e['max_drawdown'] * 100:.2f}% | {e['advantage_years']}/6 "
        f"| {yrs} | "
        + (", ".join(e["failed_gates"]) if e["failed_gates"] else "—")
        + " |")
lines.append("")
lines.append(
    "净 CAGR 单调性 C < A < D2 < D1：**"
    + ("成立（H1 因果解释增强：止盈越紧，强年 alpha 载体被截断越多）"
       if DOSE_RESPONSE["net_cagr_monotonic_C_lt_A_lt_D2_lt_D1"]
       else "不成立（乱序：止盈档位非唯一因素，须结合门 3/4/5 归因分解）")
    + "**。")
lines.append("")

lines += ["## 四、停止规则结论", "", f"- {STOP_NOTE}", "",
          f"- 对照：F3R3（ICW 净 +4.88% / EW +3.42%，均淘汰）、R3-06"
          f"（+11.06%，v3 dev_pass）、F4R1-A "
          f"{fmt_pct(DOSE_RESPONSE['entries']['F4R1-A']['net_cagr'])}、"
          f"F4R1-C {fmt_pct(DOSE_RESPONSE['entries']['F4R1-C']['net_cagr'])}"
          "（均淘汰）。F4R2 两臂净 CAGR = "
          + "、".join(f"{a} {fmt_pct(metrics[a]['net_cagr'])}" for a in ARMS)
          + "。", "",
          "## 五、披露（F4R1 预登记 §9 六条沿承 + F4R2 接缝裁定 + 运行层"
          "口径）", ""]
for d in DISCLOSURES:
    lines.append(f"- {d}")

lines += ["", "## 六、运行身份与预算", "",
          f"- 输入身份：daily {pins['daily']['sha256'][:16]}、halfday "
          f"manifest {pins['halfday_manifest']['sha256'][:16]} + "
          f"{HALFDAY_ROWS_TOTAL} 行、ICW 组合 "
          f"{pins['f3r1_icw_composite']['sha256'][:16]}、行业 "
          f"{pins['industry_l1']['sha256'][:16]}、stk_limit 聚合 "
          f"{pins['stk_limit_aggregate']['aggregate_sha256'][:16]}、ETF 目录"
          f"聚合 {pins['etf_processed_aggregate']['aggregate_sha256'][:16]}、"
          f"R16 metrics {pins['r16_metrics']['sha256'][:16]}。",
          f"- 环境：python {ENV_VERSIONS['python']} / polars "
          f"{ENV_VERSIONS['polars']} / numpy {ENV_VERSIONS['numpy']}；"
          "随机种子：none（runner 与引擎均无 RNG）。",
          f"- 墙钟 {time.perf_counter() - T0:.0f}s（预算 {BUDGET_S:.0f}s）；"
          f"峰值 RSS {PEAK_RSS:.2f} GB（上限 8 GB）。",
          "- 试验计账：策略线 273 → 275（两臂，本次全期运行入账，主对话"
          "登记台账）；F4R2-A0 锚不耗试验；首轮 F4R2-S1 停机发生在两臂运行"
          "之前，零消耗；因子线 FT01=120 不变。",
          "- runner 核对口径（沿 F4R1 全期）：逐月首扫准入重放（2015-01）、"
          "行业受阻重建、fills 路由/阶梯/止盈/止损价逐分核对（D1 无止盈 "
          "fill，止盈核对自动空转）、现金守恒与权益恒等式、zones 统计自洽、"
          "门 8 结构与台账。"]
(out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
log("  report.md + metrics_and_gates.json written")

# ---- manifest ---------------------------------------------------------------
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json", "runner.log"):
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
all_checks_ok = all(gates[a]["dev"]["checks_pass"] for a in ARMS)
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260920-zone-sheet-f4r2",
    "status": ("completed" if all_checks_ok
               else "completed_with_check_failures"),
    "scope": "FULL DEV 2015-01-05..2020-12-31, two arms (F4R2-D1 stop-only, "
             "F4R2-D2 widened 4/5-sigma TP) + F4R2-A0 anchor; eight frozen "
             "gates (F4R1 prereg sec 2 verbatim per F4R2 prereg sec 2)",
    "resume_from_aborted": {
        "first_pass_status": "aborted at the F4R2-S1 feasibility check "
                             "(engine v1.4 fail-closed rejected every "
                             "frame-level tp-disable form) BEFORE the A0 "
                             "gate and any arm run; zero trials consumed",
        "archived_aborted_manifest": "tmp/manifest_aborted_v1.json",
        "resolution": "main-conversation dual-signed engine v1.4.1 "
                      "(tp1/tp2 optional, null = zero-tier TP) + re-pin; "
                      "behavior re-verified (tmp/"
                      "s1_tp_disable_probe_result_v141.json); this pass "
                      "reran everything from identity pins"},
    "started_at_utc": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_f4r2_notp.py"],
    "random_seed": None,
    "determinism": "no RNG in runner or engine; static zones/intent frames; "
                   "engine-owned deterministic lifecycle",
    "engine": {"path": str(ENGINE_PY),
               "sha256_at_start": ENGINE_SHA_AT_START,
               "sha256_at_end": ENGINE_SHA_AT_END,
               "sha256_pin_expected": ENGINE_SHA_EXPECT_FULL,
               "bytes_modified_by_this_run":
                   ENGINE_SHA_AT_START != ENGINE_SHA_AT_END,
               "version": ENGINE_VERSION_NOTE},
    "pins": pins,
    "env_versions": ENV_VERSIONS,
    "dev_window": {"start": str(DEV_START), "end": str(DEV_END),
                   "signal_days": [d.isoformat() for d in sig_days]},
    "val_contact": {"consumed": False,
                    "policy": "2021-2024 zero contact; hard filters at "
                              "DEV_END everywhere + engine assert_frozen"},
    "a0_anchor": {"result": "PASS" if all(v["byte_equal"] for v in
                                          A0_CMP.values()) else "FAIL",
                  "detail": A0_CMP,
                  "stop_rule": "mismatch => STOP before arms, no trial "
                               "consumed (F4R2 prereg sec 4)"},
    "arms_summary": {a: {"verdict": gates[a]["verdict"],
                         "failed_gates": gates[a]["dev"]["failed_gates"],
                         "net_cagr": metrics[a]["net_cagr"],
                         "max_drawdown": metrics[a]["max_drawdown"],
                         "excess_vs_b1m": metrics[a]["excess_vs_b1m"],
                         "advantage_years":
                             gates[a]["dev"]["advantage_years"],
                         "max_one_side_turnover":
                             metrics[a]["max_one_side_turnover"],
                         "max_single_name_weight":
                             metrics[a]["max_single_name_weight"],
                         "goal_met": gates[a]["dev"]["goal_met"],
                         "gate8": {k: metrics[a]["gate8_v14_final_delivery"][k]
                                   for k in ("armed", "k3_fallback_fills",
                                             "armed_then_self_fills",
                                             "stuck_final",
                                             "final_delivery_rate",
                                             "gate_pass")},
                         "checks_pass": gates[a]["dev"]["checks_pass"],
                         "wall_s": RESULTS[a]["checks"]["wall_s"]}
                     for a in ARMS},
    "stop_rule": mg["stop_rule"],
    "dose_response": DOSE_RESPONSE,
    "s1_seam_adjudication": mg["s1_seam_adjudication"],
    "trial_accounting": mg["trial_accounting"],
    "runner_adaptations_disclosed": {
        "derived_from": "the ACCEPTED F4R1 full-dev runner "
                        + F4R1_FULL_RUN.name
                        + "/scripts/runner_f4r1_full.py; chassis, sleeve "
                          "construction, A0 anchor, data pins and the gate "
                          "layer carried verbatim",
        "arm_set_and_tp_injection": "3 arms -> F4R2-D1/D2; D1 = NULL "
                                    "tp1/tp2 (F4R2-S1 adjudicated zero-tier "
                                    "form, v1.4.1); D2 = config zones_D2 "
                                    "4.0/0.5 + 5.0/1.0 (F4R2-S2 designed "
                                    "widening, not historical tuning)",
        "t20040_exposures_dropped": "no F4R2 arm path-scales w_T (both "
                                    "constant 0.06); the F4R1 exposures "
                                    "section existed only for arm B",
        "leg_intent_priority_999": "F4R1-S1 (prereg sec 11 adjudicated, "
                                   "carried): BR-1 guard requires intent "
                                   "priority < zone_priority_base(1000); "
                                   "the ETF leg is funded BEFORE stock "
                                   "ladders in same-decision cash "
                                   "competition.",
        "sigma_estimator": "sample stdev ddof=1 over the last 20 close-to-"
                           "close log returns ending at the signal day (21 "
                           "closes incl. P0); raw official closes; excluded "
                           "candidates counted by reason.",
        "rank_not_renumbered": "sigma-excluded candidates keep their "
                               "composite rank vacated.",
        "industry_blocked_caliber": "runner-side reconstruction per month.",
        "f4r1_comparators": "dose-response F4R1-A/C numbers read from the "
                            "frozen F4R1 metrics_and_gates.json (pin "
                            "f4r1_full_metrics), NOT rerun."},
    "halfday_identity_correction": "prereg sec 10 (F4R1, carried): effective "
                                   "identity = manifest.json sha256_16 "
                                   "2a414174b5df2eee + 18,486,939 rows "
                                   "(registered above)",
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== manifest written; wall {time.perf_counter() - T0:.0f}s, "
    f"peak rss {PEAK_RSS:.2f} GB ==")
log(f"== VERDICT: {n_pass}/{len(ARMS)} arms dev_pass, {n_goal} goal_met; "
    f"{STOP_NOTE}")
_logf.close()
