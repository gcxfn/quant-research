# -*- coding: utf-8 -*-
"""exp-20260920-factor-round-f3r4 -- derived chassis runner (one arm per
subrun).  Copy-derived from the F3R3 chassis runner
artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/scripts/runner_f3r3.py
(precedent for the derivation pattern: the attribution run's runner_attrib.py).

Differences from runner_f3r3.py -- the ONLY permitted changes are the
composite input path, the arm id / output name prefix, and the engine pin
(prereg sec 7 TF-S2):

1. composite input: the arm composite parquet is loaded from the path given on
   the command line (schema symbol/signal_date/value, same as
   outputs/F3-EW_composite.parquet) instead of the F3R1 EW/ICW parquets;
2. arm id / output prefix: argv --arms '[{"tag": ..., "composite": ...}]'
   selects the tag (F3R4-LZO / F3R4-A / F3R4-B / F3R4-C / F3R4-A-w20 /
   F3R4-A-w40 / F3R4-A-b68); frames are written to tmp/subruns/<tag>/;
3. engine pin = workspace v1.4.1 a01cb29c...75abf3 (the workspace engine moved
   after F3R3; the attribution run took the same step and the leave-zero-out
   anchor re-verifies byte-identical output on this path);
4. the F3R3-specific parts that do not bear on an arm's numbers are dropped:
   the F3R3-A0 rotation anchor config, the ICW arm, the momentum/rotation
   intent builder (no rotation arm here), the F3R3-A0-vs-v3 regression block,
   and the F3R3 report/manifest text (this run's identity lives in the
   aggregate manifest.json).

EVERYTHING ELSE IS VERBATIM: chassis legs (sh.511010 15% + sh.518880 25%),
K=10 buffer membership (enter top-10, stay rank<=20), entry-side industry cap
(shenwan L1, <=2, incumbents never force-exited), w_T = e_T*(0.06/0.90),
500,000 initial cash, expiry/priority conventions, the engine call signature
(no zones argument = v1.3 semantics), the per-intent attribution, the eight
gates (incl. gate 8 v3), the disclosures and the identity pins.

The leave-zero-out anchor (tag F3R4-LZO, composite = the F3R1
F3-EW_composite.parquet) re-verifies the five frames via polars .equals() and
net_cagr equality against the F3R3-EW chassis outputs; any mismatch -> STOP
(exit 3), no downgrade (prereg sec 4/8).

Usage: python runner_f3r4.py --arms <json>
Deterministic; no RNG.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import math
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

CHASSIS_RUN = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F2R1_RUN = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
PREREG_MD = ROOT / "docs/research/exp-20260920-factor-round-f3r4-prereg.md"
F3R4_CONFIG = ROOT / "configs/experiments/f3r4-reason-integration.json"
INDUSTRY_CSV = ROOT / "data/raw/tushare/index_member_all/20260909-r1/chunk_all.csv"
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
# workspace engine v1.4.1 pin (prereg sec 4); passed NO zones argument, so the
# v1.3 code path runs byte-identically (engine module doc, v1.4 note)
ENGINE_SHA_EXPECT_FULL = ("a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1"
                          "f0a466b0675abf3")
MEMBERS = ["sh.511010", "sh.518880", "sh.510050", "sh.510300", "sz.159915",
           "sh.510880", "sh.513100", "sh.513500"]
LEG_ONLY = ["sz.159934"]
PANEL_SYMS = MEMBERS + LEG_ONLY
MEMBER_BAND = {m: 0.10 for m in PANEL_SYMS}
CHASSIS_LEGS = {"sh.511010": 0.15, "sh.518880": 0.25}
SLEEVE_K = 10                # F3R1 caliber: enter top-10, stay rank<=20
SLEEVE_W_ON = 0.06           # per-name target at e_T = 0.90 (sleeve 60%)
SLEEVE_E_REF = 0.90          # w_T = e_T * (SLEEVE_W_ON / SLEEVE_E_REF)
IND_CAP = 2                  # max members per shenwan-L1 industry (incl. UNMAPPED)
DIVIDEND_EXPECT = {"sh.510050": 5, "sh.510300": 6, "sh.510880": 6,
                   "sh.511010": 1}
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
PARK_SOURCE = date(2015, 1, 30)   # spec seam S1 (chassis verbatim)

T0 = time.perf_counter()
BUDGET_S = 6600.0
PEAK_RSS = 0.0
STAGES: dict[str, float] = {}
LOG_PATH = RUN_DIR / "logs" / "runner_f3r4.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_LINES: list[str] = []
_logf = LOG_PATH.open("a", encoding="utf-8")


def log(msg: object) -> None:
    global PEAK_RSS
    try:
        import psutil
        PEAK_RSS = max(PEAK_RSS, psutil.Process().memory_info().rss / 1e9)
    except Exception:
        pass
    line = f"[{time.perf_counter() - T0:7.1f}s] {msg}"
    LOG_LINES.append(line)
    _logf.write(line + "\n")
    _logf.flush()
    print(line, flush=True)


def stage(name: str) -> None:
    STAGES[name] = time.perf_counter() - T0
    log(f"== stage done: {name} ({STAGES[name]:.1f}s) ==")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rss_gb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1e9
    except Exception:
        return float("nan")


def check_budget(what: str) -> None:
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


STATE_PATH = RUN_DIR / "tmp" / "runner_f3r4_state.json"


def _fail(reason: str, code: int = 1) -> None:
    log(f"!! FAIL: {reason}")
    STATE_PATH.write_text(json.dumps({
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "stages_s": STAGES, "peak_rss_gb": PEAK_RSS,
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    _logf.close()
    sys.exit(code)


def stop_anchor_mismatch(detail: dict) -> None:
    """prereg sec 4/8: leave-zero-out anchor mismatch -> STOP, no downgrade."""
    (RUN_DIR / "tmp" / "stop_report.md").write_text(
        "# STOP REPORT -- exp-20260920-factor-round-f3r4 (anchor)\n\n"
        "- stopped_at_stage: leave-zero-out anchor\n"
        "- reason: anchor mismatch vs chassis F3R3-EW outputs (prereg sec 4: "
        "five frames polars .equals() and net_cagr must agree)\n"
        f"- detail: {json.dumps(detail, ensure_ascii=False)}\n"
        f"- elapsed_s: {time.perf_counter() - T0:.1f}\n"
        "- artifacts: tmp/subruns/ and this file; adjudication belongs to the "
        "main conversation, no downgrade, no engine edit.\n",
        encoding="utf-8", newline="\n")
    STATE_PATH.write_text(json.dumps({
        "status": "aborted", "failure_reason": "leave-zero-out anchor mismatch",
        "detail": detail, "ended_at": datetime.now(timezone.utc).isoformat(),
        "stages_s": STAGES, "peak_rss_gb": PEAK_RSS,
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=1),
        encoding="utf-8", newline="\n")
    _logf.close()
    sys.exit(3)


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


def dints(col: pl.Series) -> np.ndarray:
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


# === CLI ====================================================================
ap = argparse.ArgumentParser()
ap.add_argument("--arms", required=True,
                help='[{"tag": "...", "composite": "...", "anchor": false}]')
ARGS = ap.parse_args()
ARMS_SPEC = json.loads(Path(ARGS.arms).read_text(encoding="utf-8"))
log(f"== arms requested: {[a['tag'] for a in ARMS_SPEC]} ==")

# === 0. identity pins ========================================================
log("== 0. identity pins (engine v1.4.1 pin, chassis config verbatim) ==")
pins: dict = {}
EXPECTED = {
    "engine": (ENGINE_SHA_EXPECT_FULL, ENGINE_PY),
    "r16_config": ("27f846a7330919a4", R16_CONFIG),
    "daily": ("d9a63f4cc3032926", DAILY_PARQUET),
    "halfday_manifest": ("2a414174b5df2eee", HALFDAY_DIR / "manifest.json"),
    "split_factor": ("2f436b2f13d09a9b", BUNDLE / "split_factor.h5"),
    "dividends": ("46121c09cddde72e", BUNDLE / "dividends.h5"),
    "index_000300": ("05aaa8183a11c674", INDEX_CHUNK),
    "f3r1_ew_composite": (None, F3R1_RUN / "outputs/F3-EW_composite.parquet"),
    "f3r1_dedup_clusters": (None, F3R1_RUN / "outputs/dedup_clusters.csv"),
    "f2r1_all120": (None, F2R1_RUN / "outputs/f2r1_all120.csv"),
    "prereg": (None, PREREG_MD),
    "f3r4_config": (None, F3R4_CONFIG),
    "industry_l1": ("4edffc3994fb527a", INDUSTRY_CSV),
    "chassis_sleeve_log": (None, CHASSIS_RUN / "outputs/sleeve_monthly_log.json"),
    "chassis_metrics": (None, CHASSIS_RUN / "outputs/metrics_and_gates.json"),
    "chassis_ew_intents": (None, CHASSIS_RUN / "outputs/F3R3-EW_intents.parquet"),
    "chassis_ew_fills": (None, CHASSIS_RUN / "outputs/F3R3-EW_fills.parquet"),
    "chassis_ew_events": (None, CHASSIS_RUN / "outputs/F3R3-EW_events.parquet"),
    "chassis_ew_daily": (None, CHASSIS_RUN / "outputs/F3R3-EW_daily_equity.parquet"),
    "chassis_ew_clips": (None, CHASSIS_RUN / "outputs/F3R3-EW_clips_final.parquet"),
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

for spec in ARMS_SPEC:
    p = Path(spec["composite"])
    pins[f"composite_{spec['tag']}"] = {"path": str(p), "sha256": sha256_file(p)}

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
    "recomputed": adj_agg_recomputed,
    "expected_declared_in_etf_manifest": declared_adj,
    "rehash_mismatches": adj_rehash_mismatch,
    "match": (adj_agg_recomputed == declared_adj and not adj_rehash_mismatch)}
pins["etf_processed_aggregate"] = {**etf_agg, "expected": None, "match": True}
pins["trade_cal_aggregate"] = {**cal_agg, "expected": None, "match": True}
if not pins["fund_adj_aggregate"]["match"]:
    _fail("fund_adj identity check failed")
log(f"  aggregates OK (etf {etf_agg['aggregate_sha256'][:16]}, fund_adj "
    f"{adj_agg_recomputed[:16]}, trade_cal {cal_agg['aggregate_sha256'][:16]})")

r16_config = json.loads(R16_CONFIG.read_text(encoding="utf-8"))
r16_metrics = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
chassis_mg = json.loads((CHASSIS_RUN / "outputs/metrics_and_gates.json")
                        .read_text(encoding="utf-8"))
ANCHOR_CAGR = chassis_mg["metrics"]["F3R3-EW"]["net_cagr"]
ANCHOR_MDD = chassis_mg["metrics"]["F3R3-EW"]["max_drawdown"]
B3P = {"T200-40": r16_metrics["B3prime_dev_mean_net_cagr"]["T200-40"],
       "FIX75": r16_metrics["B3prime_dev_mean_net_cagr"]["FIX75"]}
B1 = r16_metrics["configs"]["C05"]
B1_PATH_NAME = r16_config["configs"]["C05"]["path"]
assert B1["b1m_variant"].startswith("rate_only"), B1["b1m_variant"]
log(f"  chassis anchor net_cagr {ANCHOR_CAGR!r} maxDD {ANCHOR_MDD!r}")
ENV_VERSIONS = {"python": platform.python_version(),
                "platform": platform.platform(),
                "polars": pl.__version__, "numpy": np.__version__}

# === 1. calendar & signal days (P3R2 verbatim) ===============================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
assert sig_days and sig_days[-1] <= date(2020, 12, 31)
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})")
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}
stage("calendar")

# === 2. exposures (r16 verbatim, C05 path only) ==============================
log("== 2. exposures (T200-40) ==")
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
exposures = r16.t200_month_end_exposures(index_close, calendar_full, sig_days)
log(f"  exposures[{sig_days[0]}]={exposures[sig_days[0]]:.2f} "
    f"[{sig_days[-1]}]={exposures[sig_days[-1]]:.2f}")
stage("exposures")

# === 3. pools (r16 verbatim) =================================================
log("== 3. pools (r16 build_history + signal_pools) ==")
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
del hist
panel_symbols = sorted({s for t in sig_days for s in pools_at[t]["ranked"]})
log(f"  pools at {sig_days[0]}: n={pools_at[sig_days[0]]['n']}; union of "
    f"ranked symbols: {len(panel_symbols)}")
check_budget("pools")
stage("pools")

# === 4. arm composite (parquet input -- the one input-path change) ==========
_ind = pl.read_csv(INDUSTRY_CSV)
_ind = _ind.with_columns(
    (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
     + "." + pl.col("ts_code").str.split(".").list.first()).alias("sym"))
INDUSTRY_L1: dict[str, str] = dict(zip(_ind["sym"].to_list(),
                                       _ind["l1_name"].to_list()))
IND_OF = lambda sym: INDUSTRY_L1.get(sym, "UNMAPPED")  # noqa: E731


def build_arm(composite_path: Path, tag: str) -> tuple[pl.DataFrame, dict, dict]:
    """Sleeve membership (buffer K=10 + entry-side industry cap) and the
    static intent frame, chassis sec 4/8 verbatim; the composite comes from
    the arm parquet (schema symbol/signal_date/value)."""
    log(f"== 4. arm composite load ({tag}) ==")
    df = pl.read_parquet(composite_path)
    if set(df.columns) != {"symbol", "signal_date", "value"}:
        _fail(f"{tag}: composite schema {df.columns}")
    days = sorted(set(df["signal_date"].to_list()))
    if days != sorted(sig_days):
        _fail(f"{tag}: composite signal days != runner sig_days "
              f"({days[:2]}..{days[-2:]} vs {sig_days[0]}..{sig_days[-1]})")
    if df.group_by("symbol", "signal_date").len().filter(
            pl.col("len") > 1).height:
        _fail(f"{tag}: composite (symbol, signal_date) not unique")
    by_day: dict[date, dict[str, float]] = {}
    for r in df.iter_rows(named=True):
        by_day.setdefault(r["signal_date"], {})[r["symbol"]] = float(r["value"])
    sizes = [len(by_day[t]) for t in sig_days]
    log(f"  composite {tag}: {len(sig_days)} days, eligible min {min(sizes)} "
        f"median {int(np.median(sizes))} max {max(sizes)}")
    ranked = {t: sorted(by_day[t], key=lambda s: (-by_day[t][s], s))
              for t in sig_days}
    all_syms = sorted({s for t in sig_days for s in by_day[t]})
    unmapped = [s for s in all_syms if s not in INDUSTRY_L1]
    log(f"  industry L1 map: {len(INDUSTRY_L1)} stocks; composite-candidate "
        f"unmapped {len(unmapped)} -> UNMAPPED bucket (same cap)")

    members: list[str] = []
    sleeve_members: dict[date, list[str]] = {}
    sleeve_log: list[dict] = []
    panel_f3: set = set()
    ind_blocked_total = 0
    cash_seats_total = 0
    for t in sig_days:
        rank_of_m = {s: i + 1 for i, s in enumerate(ranked[t])}
        kept = [m for m in members
                if m in rank_of_m and rank_of_m[m] <= 2 * SLEEVE_K]
        kept_set = set(kept)
        ind_count: dict[str, int] = {}
        for m in kept:
            ind_count[IND_OF(m)] = ind_count.get(IND_OF(m), 0) + 1
        seats = SLEEVE_K - len(kept)
        entrants: list[str] = []
        blocked: list[str] = []
        for c in ranked[t][:SLEEVE_K]:
            if seats <= 0:
                break
            if c in kept_set or c in entrants:
                continue
            ind = IND_OF(c)
            if ind_count.get(ind, 0) >= IND_CAP:
                blocked.append(c)
                continue
            entrants.append(c)
            ind_count[ind] = ind_count.get(ind, 0) + 1
            seats -= 1
        new_members = kept + entrants
        entries = list(entrants)
        exits = [s for s in members if s not in new_members]
        cash_seats = SLEEVE_K - len(new_members)
        ind_blocked_total += len(blocked)
        cash_seats_total += cash_seats
        sleeve_members[t] = list(new_members)
        sleeve_log.append(
            {"month": str(t), "members": sorted(new_members),
             "entries": sorted(entries), "exits": sorted(exits),
             "e_T": float(exposures[t]),
             "w_T": float(exposures[t]) * (SLEEVE_W_ON / SLEEVE_E_REF),
             "ranks": {s: rank_of_m[s] for s in new_members},
             "industries": {s: IND_OF(s) for s in new_members},
             "ind_blocked": sorted(blocked), "cash_seats": cash_seats,
             "n_kept": len(kept), "n_prev": len(members),
             "n_left": len(members) - len(kept)})
        panel_f3.update(new_members)
        members = list(new_members)
    max_m = max(len(m) for m in sleeve_members.values())
    max_ind = max((sum(1 for s in m if IND_OF(s) == i)
                   for m in sleeve_members.values()
                   for i in {IND_OF(s) for s in m}), default=0)
    if max_m > SLEEVE_K:
        _fail(f"{tag}: membership exceeded K={SLEEVE_K}")
    n_churn = sum(len(e["entries"]) for e in sleeve_log)
    log(f"  sleeve {tag}: max members/month {max_m} (<= {SLEEVE_K} req), "
        f"entries {n_churn} over {len(sig_days)} months, industry-blocked "
        f"{ind_blocked_total}, cash seats {cash_seats_total}, max industry "
        f"count {max_ind}, panel symbols {len(panel_f3)}")

    def prev_members_of(T: date) -> set[str]:
        i = sig_days.index(T)
        return set(sleeve_members[sig_days[i - 1]]) if i > 0 else set()

    rows: list[dict] = []
    for T in sig_days:
        mem = sleeve_members[T]
        rank_map = {s: i + 1 for i, s in enumerate(ranked[T])}
        w_T = float(exposures[T]) * (SLEEVE_W_ON / SLEEVE_E_REF)
        Tp = next_sig.get(T)
        expiry = (date.fromordinal(Tp.toordinal() + 1) if Tp is not None
                  else date.fromordinal(T.toordinal() + 1))
        entries = [s for s in mem if s not in prev_members_of(T)]
        exits = [s for s in prev_members_of(T) if s not in mem]
        for sym in sorted(exits):
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T,
                         "priority": rank_map.get(sym, 10 ** 6),
                         "expiry_date": expiry, "target_weight": None})
        for sym in sorted(entries):
            rows.append({"symbol": sym, "side": "buy", "intent": "",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": rank_map[sym],
                         "expiry_date": expiry, "target_weight": w_T})
        for sym in sorted(s for s in mem if s not in entries):
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": rank_map[sym],
                         "expiry_date": expiry, "target_weight": w_T})
    # chassis legs (verbatim conventions)
    park_T = sig_days[0]
    park_expiry = date.fromordinal(sig_days[3].toordinal() + 1)
    for sym, w in CHASSIS_LEGS.items():
        rows.append({"symbol": sym, "side": "buy", "intent": "",
                     "decision_date": park_T, "decision_session": "pm",
                     "source_signal": PARK_SOURCE, "priority": 10 ** 6,
                     "expiry_date": park_expiry,
                     "target_weight": float(w)})
        for T in sig_days[1:]:
            Tp = next_sig.get(T)
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": 10 ** 6,
                         "expiry_date": date.fromordinal(Tp.toordinal() + 1),
                         "target_weight": float(w)})
    keys = [(r["symbol"], r["side"], r["source_signal"]) for r in rows]
    dup_m5b = sorted({k for k in keys if keys.count(k) > 1})
    firsts = [(r["symbol"], r["decision_date"], r["decision_session"])
              for r in rows]
    dup_first = sorted({k for k in firsts if firsts.count(k) > 1})
    if dup_m5b or dup_first:
        _fail(f"{tag}: m5-b/first-decision duplicates {dup_m5b[:3]} "
              f"{dup_first[:3]}")
    frame = pl.DataFrame(rows, schema=INTENT_SCHEMA)
    diag = {"panel_f3": sorted(panel_f3), "max_members": max_m,
            "entries": n_churn, "ind_blocked": ind_blocked_total,
            "cash_seats": cash_seats_total, "max_industry_count": max_ind,
            "unmapped_candidates": unmapped, "eligible_min": min(sizes),
            "eligible_median": int(np.median(sizes)),
            "eligible_max": max(sizes)}
    return frame, {"sleeve_log": sleeve_log, "sleeve_members":
                   {str(k): v for k, v in sleeve_members.items()}}, diag


# === 5. market frames (P3R2 verbatim) ========================================
log("== 5. market frames ==")
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
pins["daily"].update({"rows_total": daily_meta["rows_total"],
                      "rows_after_freeze_filter":
                          daily_meta["rows_after_freeze_filter"]})
daily = (daily_full.filter(pl.col("symbol").is_in(panel_symbols))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .select("symbol", "date", "open", "high", "low", "close",
                 "tradestatus").sort("symbol", "date"))
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
log(f"  halfday: {half.height} rows kept of {half_rows_total} total")

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
stage("market_frames")

# === 6. ETF assets (chassis verbatim) ========================================
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
if n_null_preclose:
    _fail("runner assertion (ii) FAILED: preclose nulls in member-dev panel")
cal_tc = pl.read_csv(sorted(TRADECAL_DIR.glob("chunk_exchange-SSE_*.csv"))[0])
cal_tc = cal_tc.filter((pl.col("is_open") == 1)
                       & (pl.col("cal_date") >= int(DEV_START.strftime("%Y%m%d")))
                       & (pl.col("cal_date") <= int(DEV_END.strftime("%Y%m%d"))))
sse_days = set(cal_tc["cal_date"].to_list())
panel_days = set(dints(etf_panel["date"]).tolist())
if sse_days != panel_days:
    _fail(f"runner assertion (iii) FAILED: panel dates != sse calendar "
          f"(missing {sorted(sse_days - panel_days)[:5]} extra "
          f"{sorted(panel_days - sse_days)[:5]})")
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
if any(v for v in factor_gaps.values()):
    _fail(f"fund_adj does not cover every member-dev panel day: {factor_gaps}")
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
                         "div_per_share": float(r["prev_close"])
                         - float(r["preclose"]), "factor_ratio": ratio})
dividend_events = pl.DataFrame(div_rows, schema={
    "symbol": pl.String, "date": pl.Date, "div_per_share": pl.Float64,
    "factor_ratio": pl.Float64}).drop("factor_ratio").sort("symbol", "date")
counts = Counter(dividend_events["symbol"].to_list())
if dict(counts) != DIVIDEND_EXPECT or dividend_events.height != 18:
    _fail(f"dividend events != frozen expectation {DIVIDEND_EXPECT}: {counts}")
log(f"  dividend events: {dividend_events.height} {dict(counts)}")
SYMBOL_META = {m: {"asset_class": "etf", "band": MEMBER_BAND[m], "t_plus": 0}
               for m in PANEL_SYMS}
check_budget("etf assets")
stage("etf_assets")


def etf_pm_bars(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("symbol"), pl.col("date").alias("trade_date"),
        pl.lit("pm", dtype=pl.String).alias("session"),
        pl.col("open"), pl.col("high"), pl.col("low"), pl.col("close"))


# === 7. shared engine-input frames (chassis sec 9 verbatim, mixed mode) =====
log("== 7. shared engine input frames (mixed mode) ==")
HALF_COLS = ["symbol", "trade_date", "session", "open", "high", "low", "close"]
etf_ts_dtype = daily.schema["tradestatus"]
etf_panel_ts = etf_panel.with_columns(
    pl.lit(1.0, dtype=etf_ts_dtype).alias("tradestatus"))
stage("engine_input_frames")

# === 8. arm loop =============================================================
OUT_ROOT = RUN_DIR / "tmp" / "subruns"
state = {"status": "running", "arms": ARMS_SPEC, "arms_done": [],
         "stages_s": STAGES}
STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                      encoding="utf-8", newline="\n")
REF_FRAMES = {name: pl.read_parquet(CHASSIS_RUN / "outputs" / fn)
              for name, fn in (("intents", "F3R3-EW_intents.parquet"),
                               ("fills", "F3R3-EW_fills.parquet"),
                               ("events", "F3R3-EW_events.parquet"),
                               ("daily", "F3R3-EW_daily_equity.parquet"),
                               ("clips_final", "F3R3-EW_clips_final.parquet"))}
CID = None
results: dict = {}


# === 12/13a. per-intent attribution + gate helpers (F3R3 verbatim) ==========
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
        lifecycle[(sym, "buy" if sidestr.startswith("buy") else "sell", src)] \
            = reason
    per_intent_events: dict = {}
    for r in res.events.filter(pl.col("order_id") != "").iter_rows(named=True):
        parts = r["order_id"].rsplit("-", 4)
        if len(parts) != 5:
            _fail(f"{cid}: unparsable order_id {r['order_id']!r}")
        prefix, y, mo, dy, sess = parts
        d = date(int(y), int(mo), int(dy))
        sym, sidestr = (prefix.split("-", 1) if "-" in prefix
                        else (prefix, ""))
        sclass = "buy" if sidestr.startswith("buy") else "sell"
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
                fill_by_intent[(r["symbol"], sclass, T)] = \
                    fill_by_intent.get((r["symbol"], sclass, T), 0) + 1
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
        elif evs and all(e in {"below_min_lot", "void_no_position",
                               "void_insufficient_cash"} for e in evs):
            host = "executed_rule_blocked:" + evs[-1]
            rule_blocked[evs[-1]] += 1
        elif eng.startswith("cap_single_name"):
            host = "terminated:cap_void"
        elif eng.startswith("overridden"):
            host = "terminated:override_same_name"
        elif eng.startswith("expired") or eng.startswith("still_active"):
            if not evs:
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
    n_term = sum(1 for v in outcomes.values() if v[0].startswith("terminated:"))
    mapped = ((n_filled + n_rule) / (n_filled + n_rule + n_term)
              if (n_filled + n_rule + n_term) else None)
    il = res.stats["intent_layer"]
    if n_filled != il["stopped_filled"]:
        _fail(f"{cid}: host filled {n_filled} != engine stopped_filled "
              f"{il['stopped_filled']}")
    return {"outcomes": {k: v[0] for k, v in outcomes.items()},
            "termination": term, "mapped_rate": mapped, "n_filled": n_filled,
            "n_rule_blocked": n_rule, "n_terminated": n_term,
            "expiry_at_target_noop": expiry_at_target_noop,
            "zero_emission_intents": sum(1 for v in outcomes.values()
                                         if v[2] == 0)}


def gate8_v3(cid: str) -> dict:
    """Gate 8 v3 (F3R3/v2 caliber, verbatim)."""
    res = results[cid]["res"]
    k3 = res.stats["k3_fallback"]
    armed, mkt = int(k3["armed"]), int(k3["executed"])
    ev, fills = res.events, res.fills
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
            if e.startswith("market_exit_deferred") \
                    or e == "market_exit_void_no_position":
                r["_sym"] = (r["detail"] or "").split(":", 1)[0]
            else:
                continue
        else:
            r["_sym"] = s
        seq.append(r)
    state_: dict = {}
    tot = {"armed_events": 0, "market_filled": 0, "limit_self_filled": 0,
           "no_position_cleared": 0}
    lim_cases: list[dict] = []
    for r in seq:
        e, s = r["event"], r["_sym"]
        st = state_.setdefault(s, {"armed": False})
        if e == "not_penetrated" and ("market fallback armed for next "
                                      "session" in (r["detail"] or "")):
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
    stuck = sorted(s for s, st in state_.items() if st["armed"])
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
            "caliber": "final delivery = (market-fallback fills + armed-then-"
                       "limit-self fills) / armed fallbacks, >= 99%; "
                       "end-of-run armed stuck positions == 0 hard assert "
                       "(F3R3 caliber verbatim)"}


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
    state_: dict = {}
    wmax = 0.0
    for d, e in zip(dates, eq_list):
        td = dint_of(d)
        if e <= 0:
            continue
        for sym, evs in per.items():
            st = state_.get(sym)
            if st is None:
                st = [0, 0, 0]
                state_[sym] = st
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


def close_le_map(sym: str) -> tuple[np.ndarray, np.ndarray]:
    if sym in PANEL_SYMS:
        rows = etf_panel.filter(pl.col("symbol") == sym)
    else:
        rows = daily_c.filter((pl.col("symbol") == sym)
                              & (pl.col("tradestatus") != 0))  # P3R2 caliber
    return dints(rows["date"]), rows["close"].to_numpy().astype(np.float64)


def close_le(sym: str, d: date) -> float | None:
    arr = CLOSE_ARR.get(sym)
    if arr is None:
        return None
    dint_a, cls = arr
    i = int(np.searchsorted(dint_a, dint_of(d), side="right")) - 1
    return float(cls[i]) if i >= 0 else None


def equity_decomposition(cid: str) -> dict:
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
    mv_leg: dict[str, list[float]] = {s: [] for s in CHASSIS_LEGS}
    state_: dict = {}
    for d, row in zip(dates, res.daily.iter_rows(named=True)):
        td = dint_of(d)
        s_st = s_et = 0.0
        day_leg = {s: 0.0 for s in mv_leg}
        for sym, evs in per.items():
            st = state_.get(sym)
            if st is None:
                st = [0, 0]
                state_[sym] = st
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
    out["full_period_level_change"] = {"equity": eq[-1] - eq[0],
                                       "stock_leg": mv_st[-1] - mv_st[0],
                                       "etf_leg": mv_et[-1] - mv_et[0],
                                       "cash": cash[-1] - cash[0]}
    leg_w = {}
    for sym, series in mv_leg.items():
        ws = [m / e for m, e in zip(series, eq) if e > 0]
        leg_w[sym] = {"mean_weight": float(np.mean(ws)) if ws else None,
                      "max_weight": float(np.max(ws)) if ws else None,
                      "park_w": CHASSIS_LEGS[sym]}
    tot = [m / e for m, e in zip(mv_et, eq) if e > 0]
    leg_w["_total_etf"] = {"mean_weight": float(np.mean(tot)) if tot else None,
                           "max_weight": float(np.max(tot)) if tot else None,
                           "park_w": sum(CHASSIS_LEGS.values())}
    out["leg_weights"] = leg_w
    return out


def sleeve_fill_profile(cid: str) -> dict:
    res = results[cid]["res"]
    syms = {s for t in sig_days for s in SLEEVE_MEMBERS[cid][t]}
    f = (res.fills.filter(pl.col("symbol").is_in(sorted(syms)))
         if res.fills.height else res.fills)
    return {"sleeve_symbols": len(syms), "sleeve_fills": f.height,
            "sleeve_buy_fills": int((f["side"] == "buy").sum())
            if f.height else 0,
            "sleeve_entries_emitted":
                sum(len(e["entries"]) for e in SLEEVE_LOG[cid]),
            "sleeve_exits_emitted":
                sum(len(e["exits"]) for e in SLEEVE_LOG[cid]),
            "insufficient_cash_orders":
                res.stats["cash_friction"]["insufficient_cash_orders"],
            "orders_generated": res.stats["intent_layer"]["orders_generated"],
            "limit_filled_orders": res.stats["intent_layer"]["stopped_filled"]}


for spec in ARMS_SPEC:
    tag = spec["tag"]
    comp_path = Path(spec["composite"])
    t_arm = time.perf_counter()
    log(f"===== arm {tag} (composite {comp_path.name}) =====")
    FRAMES: dict = {}
    SLEEVE_MEMBERS: dict = {}
    SLEEVE_LOG: dict = {}
    SLEEVE_DIAG: dict = {}
    CID = tag
    results = {}
    frame, sleeve, diag = build_arm(comp_path, tag)
    FRAMES[tag] = frame
    SLEEVE_LOG[tag] = sleeve["sleeve_log"]
    SLEEVE_MEMBERS[tag] = {}
    for entry in sleeve["sleeve_log"]:
        SLEEVE_MEMBERS[tag][date.fromisoformat(entry["month"])] = \
            entry["members"]
    SLEEVE_DIAG[tag] = diag
    assert len(SLEEVE_MEMBERS[tag]) == len(sig_days)
    stage(f"{tag}_sleeve")
    del frame, sleeve

    cfg_syms_stock = sorted(diag["panel_f3"])
    daily_c = (daily.filter(pl.col("symbol").is_in(cfg_syms_stock))
               .filter(pl.col("date") <= DEV_END))
    half_c = (half.filter(pl.col("symbol").is_in(cfg_syms_stock))
              .filter(pl.col("trade_date") <= DEV_END))
    limits_c = (limits.filter(pl.col("symbol").is_in(cfg_syms_stock))
                .filter(pl.col("date") <= DEV_END))
    splits_c = splits.filter(pl.col("symbol").is_in(cfg_syms_stock))
    divs_c = dividends.filter(pl.col("symbol").is_in(cfg_syms_stock))
    instr_c = instruments.filter(pl.col("symbol").is_in(cfg_syms_stock))
    log(f"  stock frames ({len(cfg_syms_stock)} syms): daily {daily_c.height}, "
        f"half {half_c.height}, limits {limits_c.height}")
    stock_preclose = daily_c.with_columns(
        pl.lit(None, dtype=pl.Float64).alias("preclose"))
    etf_p_used = etf_panel_ts.filter(pl.col("symbol").is_in(set(CHASSIS_LEGS)))
    mix_daily = pl.concat([
        stock_preclose.select("symbol", "date", "open", "high", "low", "close",
                              "tradestatus", "preclose"),
        etf_p_used.select("symbol", "date", "open", "high", "low", "close",
                          "tradestatus", "preclose")]).sort("symbol", "date")
    mix_half = pl.concat([half_c.select(HALF_COLS),
                          etf_pm_bars(etf_p_used).select(HALF_COLS)],
                         how="vertical")
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(
        FRAMES[tag], mix_daily, mix_half, limits_c, splits_c, divs_c, instr_c,
        symbol_meta=SYMBOL_META, dividend_events=dividend_events,
        initial_cash=500_000.0)
    wall = time.perf_counter() - t_cfg
    il = res.stats.get("intent_layer") or {}
    log(f"  {tag}: engine {wall:.1f}s, intents {il.get('n_intents')} orders "
        f"{il.get('orders_generated')} filled {il.get('stopped_filled')} cap "
        f"{il.get('terminated_cap')} | rss {rss_gb():.2f} GB")
    defaulted = res.stats["etf_leg"]["etf_default_band_symbols"]
    if defaulted:
        _fail(f"runner assertion (i) FAILED for {tag}: "
              f"etf_default_band_symbols = {defaulted}")
    results[tag] = {"res": res, "wall_s": wall, "warnings": list(res.warnings)}

    # --- attribution + close lookup (P3R2 caliber) -------------------------
    split_events: dict[str, list[tuple[date, float]]] = {}
    for r in splits.filter(pl.col("ex_date") <= DEV_END).iter_rows(named=True):
        split_events.setdefault(r["symbol"], []).append(
            (r["ex_date"], float(r["split_factor"])))
    for v in split_events.values():
        v.sort()
    CLOSE_ARR: dict = {}
    for sym in set(cfg_syms_stock) | set(PANEL_SYMS):
        CLOSE_ARR[sym] = close_le_map(sym)
    attr = {tag: attribute(tag)}
    log(f"  {tag}: R16-mapped exec "
        f"{((attr[tag]['mapped_rate'] or 0) * 100):.1f}% (filled "
        f"{attr[tag]['n_filled']}, rule-blocked "
        f"{attr[tag]['n_rule_blocked']}, terminated "
        f"{attr[tag]['n_terminated']}); term "
        f"{attr[tag]['termination']}")

    # --- metrics & gates (F3R3 verbatim) -----------------------------------
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(), DEV_START, DEV_END)
    net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd = er.max_drawdown(sd, sv)["max_drawdown"]
    yr = er.year_returns(sd, sv)
    b1y = {int(k): v for k, v in B1["b1m_net_return_by_year"].items()}
    adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
    excess = net_cagr - B1["b1m_net_cagr"]
    df = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
    mean_eq = {int(r["yy"]): r["equity"] for r in
               df.group_by("yy").agg(pl.col("equity").mean())
               .iter_rows(named=True)}
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
    a = attr[tag]
    k3 = res.stats["k3_fallback"]
    g8v3 = gate8_v3(tag)
    if g8v3["stuck_final"]:
        _fail(f"{tag}: gate 8 v3 HARD ASSERTION FAILED -- end-of-run armed "
              f"stuck positions {g8v3['stuck_final']}")
    armed, executed = int(k3["armed"]), int(k3["executed"])
    delivery_v2 = (executed / armed) if armed else None
    m = {"net_cagr": net_cagr, "net_total_return": sv[-1] / sv[0] - 1.0,
         "max_drawdown": mdd, "b1m_net_cagr": B1["b1m_net_cagr"],
         "b1m_max_drawdown": B1["b1m_max_drawdown"],
         "b1m_net_return_by_year": B1["b1m_net_return_by_year"],
         "b1m_source": "R16 metrics.json configs.C05 verbatim "
                       "(T200-40/rate_only; family anchor)",
         "b3prime_path": B1_PATH_NAME, "excess_vs_b1m": excess,
         "net_return_by_year": {int(k): v for k, v in yr.items()},
         "advantage_years_list": [int(y) for y in adv],
         "turnover_by_year": tby,
         "max_one_side_turnover": max(v["one_side_turnover"]
                                      for v in tby.values()),
         "max_single_name_weight": wmax,
         "goal_dev_net_cagr_ge_10pct": net_cagr >= 0.10,
         "gate8_v3_final_delivery": g8v3,
         "gate8_v2_comparison": {
             "armed": armed, "executed": executed,
             "delivery_rate": delivery_v2,
             "deferred_limitdown": k3["deferred_limitdown_sessions"],
             "deferred_suspended": k3["deferred_suspended"],
             "deferred_t1locked": k3["deferred_t1locked"],
             "caliber": "v1 8v2 (market-fallback executions / armed only); "
                        "comparison column, not a gate"},
         "r16_execution_rate_comparison": {
             "value": a["mapped_rate"],
             "mapping": "filled + rule-blocked / (filled + rule-blocked + "
                        "terminated); R16 original 95% caliber, not a gate"}}
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
    g["verdict"] = "dev_pass" if g["dev_pass"] else "eliminated"
    m["goal_criterion_dev_cagr_ge_10pct"] = m["goal_dev_net_cagr_ge_10pct"]
    g["goal_met"] = bool(g["dev_pass"] and m["goal_dev_net_cagr_ge_10pct"])
    d3 = g8v3
    d3v = "n/a(0 armed)" if d3["final_delivery_rate"] is None \
        else f"{d3['final_delivery_rate']*100:.1f}%"
    log(f"  {tag}: net {net_cagr*100:+.2f}% excess {excess*100:+.2f}pp adv "
        f"{len(adv)}/6 mdd {mdd*100:.2f}% turn "
        f"{m['max_one_side_turnover']:.2f} w {wmax*100:.1f}% g8v3 "
        f"{d3['market_fallback_fills']}+{d3['armed_then_limit_self_fills']}"
        f"/{d3['armed']}={d3v} failed {g['failed_gates']}")
    eqd = equity_decomposition(tag)
    prof = sleeve_fill_profile(tag)
    arm_meta = {"chassis_legs": CHASSIS_LEGS, "K": SLEEVE_K,
                "w_on": SLEEVE_W_ON, "e_ref": SLEEVE_E_REF,
                "ind_cap": IND_CAP, "cash": 500_000.0}

    # --- anchor comparison (leave-zero-out tag only) -----------------------
    anchor_detail = None
    if spec.get("anchor"):
        log("  LEAVE-ZERO-OUT ANCHOR: 5-frame .equals() vs chassis F3R3-EW")
        comparison = {}
        for name, mine in (("intents", FRAMES[tag]), ("fills", res.fills),
                           ("events", res.events), ("daily", res.daily),
                           ("clips_final", res.clips_final)):
            same = mine.equals(REF_FRAMES[name])
            comparison[name] = same
            log(f"    {name}.equals(chassis) = {same} (mine {mine.height} / "
                f"ref {REF_FRAMES[name].height})")
        cagr_ok = abs(net_cagr - ANCHOR_CAGR) <= 1e-12
        mdd_ok = abs(mdd - ANCHOR_MDD) <= 1e-12
        comparison["net_cagr_matches_chassis"] = cagr_ok
        comparison["max_drawdown_matches_chassis"] = mdd_ok
        comparison["net_cagr"] = net_cagr
        comparison["chassis_net_cagr"] = ANCHOR_CAGR
        log(f"    net_cagr {net_cagr!r} vs chassis {ANCHOR_CAGR!r} -> "
            f"{cagr_ok}; maxDD {mdd!r} vs {ANCHOR_MDD!r} -> {mdd_ok}")
        anchor_detail = comparison
        if not all(comparison[k] for k in
                   ("intents", "fills", "events", "daily", "clips_final",
                    "net_cagr_matches_chassis", "max_drawdown_matches_chassis")):
            stop_anchor_mismatch(comparison)
        log("  LEAVE-ZERO-OUT ANCHOR PASS (5/5 frames + net_cagr + maxDD)")

    out_dir = OUT_ROOT / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    FRAMES[tag].write_parquet(out_dir / "intents.parquet")
    res.fills.write_parquet(out_dir / "fills.parquet")
    res.events.write_parquet(out_dir / "events.parquet")
    res.daily.write_parquet(out_dir / "daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / "clips_final.parquet")
    (out_dir / "stats.json").write_text(json.dumps({
        "tag": tag, "arm_meta": arm_meta,
        "composite": {"path": str(comp_path),
                      "sha256": pins[f"composite_{tag}"]["sha256"]},
        "metrics": m, "gates": {"dev": g, "verdict": g["verdict"]},
        "disclosures": {
            "execution": {"termination_reasons": a["termination"],
                          "expired_at_target_noop": a["expiry_at_target_noop"],
                          "rule_blocked": a["n_rule_blocked"],
                          "zero_emission_intents": a["zero_emission_intents"],
                          "risk_intents_in_frame":
                              int((FRAMES[tag]["side"] == "sell").sum()),
                          "k3_trigger_rate_armed_per_risk_intent":
                              (k3["armed"] / int((FRAMES[tag]["side"] == "sell")
                                                 .sum()))},
            "turnover_fees": {
                "buy_notional_total": res.stats["turnover"]["buy_notional_total"],
                "sell_notional_total":
                    res.stats["turnover"]["sell_notional_total"],
                "fees_total": (float(res.fills["fees_total"].sum())
                               if res.fills.height else 0.0),
                "max_one_side_turnover": m["max_one_side_turnover"]},
            "mdd_attribution": eqd, "sleeve_profile": prof},
        "sleeve": {"log": SLEEVE_LOG[tag], "diag": diag},
        "stats_engine": res.stats, "engine_warnings": list(res.warnings),
        "engine_wall_s": wall, "arm_wall_s": time.perf_counter() - t_arm,
        "anchor_compare": anchor_detail},
        ensure_ascii=False, indent=1, default=str),
        encoding="utf-8", newline="\n")
    state["arms_done"].append({"tag": tag, "net_cagr": net_cagr,
                               "max_drawdown": mdd,
                               "failed_gates": g["failed_gates"],
                               "anchor_compare": anchor_detail})
    state["stages_s"] = STAGES
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1,
                                     default=str),
                          encoding="utf-8", newline="\n")
    log(f"  {tag}: subrun written to tmp/subruns/{tag}/")
    del res, daily_c, half_c, mix_daily, mix_half, limits_c, splits_c, divs_c
    del instr_c, CLOSE_ARR
    gc.collect()
    check_budget(f"arm {tag}")

ENGINE_SHA_AT_END = sha256_file(ENGINE_PY)
state["status"] = "completed"
state["engine_sha_at_start"] = ENGINE_SHA_AT_START
state["engine_sha_at_end"] = ENGINE_SHA_AT_END
state["bytes_modified_by_this_run"] = ENGINE_SHA_AT_START != ENGINE_SHA_AT_END
state["peak_rss_gb"] = PEAK_RSS
state["wall_seconds"] = time.perf_counter() - T0
state["stages_s"] = STAGES
state["env_versions"] = ENV_VERSIONS
state["pins"] = pins
state["ended_at"] = datetime.now(timezone.utc).isoformat()
STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1,
                                 default=str),
                      encoding="utf-8", newline="\n")
log(f"== arm loop complete: {len(state['arms_done'])} arms, wall "
    f"{state['wall_seconds']:.0f}s, peak rss {PEAK_RSS:.2f} GB ==")
_logf.close()
