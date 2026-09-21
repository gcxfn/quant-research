# -*- coding: utf-8 -*-
"""exp-20260920-factor-attribution -- stage B: leave-zero-out anchor +
leave-one-out runs (prereg docs/research/exp-20260920-factor-attribution-prereg.md
sec 4), copy-derived from the F3R3 chassis runner
artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/scripts/runner_f3r3.py.

Differences from runner_f3r3.py (everything else verbatim):
- ONLY the F3R3-EW arm runs (same chassis: K=10, industry cap <=2 on entries,
  500k initial cash, legs sh.511010 15% + sh.518880 25%, w_T = e_T*(0.06/0.90),
  v1.3 semantics = no zones argument, zero RNG);
- the F3 composite is REBUILT from the F2R1 per-factor score parquets for a
  SUBSET of the 17 representatives (F3R1 sec 4 construction verbatim:
  eligible = R16 pool INTERSECTION >= ceil(M'/2) reps non-null, component =
  (rank_pct-0.5)*sign(ic_mean), EW = mean of available components), where
  M' = |subset|; signs from f2r1_all120.csv (frozen F2R1 evaluation);
- engine pin = workspace v1.4.1 a01cb29c...75abf3 (prereg sec 2/FA-S1);
- the A0 rotation anchor and the gates/disclosure blocks are not needed here
  and are removed; a compact metrics block (net CAGR, maxDD, year returns,
  advantage years vs B1(m)=C05, one-side turnover) feeds the LOO matrix;
- leave-zero-out anchor (drop=[]): the five frames
  (intents/fills/events/daily_equity/clips_final) must equal the chassis
  F3R3-EW outputs via polars .equals() and net_cagr must equal the chassis
  metric -- any mismatch -> STOP (exit 3), no downgrade (prereg sec 4/FA-S1).

Usage: runner_attrib.py --subsets <json>
  json = [{"tag": "leave_zero_out", "drop": []},
          {"tag": "loo_F09", "drop": ["F09"]}, ...]
Each subset writes tmp/subruns/<tag>/{5 frames, stats.json}.  Deterministic;
no RNG.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import sys
import time
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
PREREG_MD = ROOT / "docs/research/exp-20260920-factor-attribution-prereg.md"
F3R3_CONFIG = ROOT / "configs/experiments/f3r3-industry-cap.json"
INDUSTRY_CSV = ROOT / "data/raw/tushare/index_member_all/20260909-r1/chunk_all.csv"
R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
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
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
# workspace engine v1.4.1 pin (prereg sec 2; FA-S1); v1.3 semantics = the
# runner passes NO zones argument (same call signature as the v1.3 chassis)
ENGINE_SHA_EXPECT_FULL = ("a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1"
                          "f0a466b0675abf3")
CID = "F3R3-EW"
# frozen universe (hybrid v1 prereg sec 2, inherited verbatim; table order)
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
INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "priority": pl.Int64,
    "expiry_date": pl.Date, "target_weight": pl.Float64,
}
PARK_SOURCE = date(2015, 1, 30)   # spec seam S1 (chassis verbatim)

T0 = time.perf_counter()
BUDGET_S = 6600.0   # prereg wall-clock cap 2h, safety margin for manifest
PEAK_RSS = 0.0
STAGES: dict[str, float] = {}
LOG_PATH = RUN_DIR / "logs" / "runner_attrib.log"
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


def _fail(reason: str, code: int = 1) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "tmp" / "runner_attrib_state.json").write_text(json.dumps({
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "stages_s": STAGES, "peak_rss_gb": PEAK_RSS,
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    _logf.close()
    sys.exit(code)


def stop_anchor_mismatch(detail: dict) -> None:
    """Prereg sec 4 / FA-S1: leave-zero-out anchor mismatch -> STOP, no
    downgrade, adjudication belongs to the main conversation."""
    (RUN_DIR / "tmp" / "stop_report.md").write_text(
        "# STOP REPORT -- exp-20260920-factor-attribution (stage B)\n\n"
        "- stopped_at_stage: leave-zero-out anchor\n"
        "- reason: anchor mismatch vs chassis F3R3-EW outputs "
        "(prereg sec 4: 五帧 polars .equals() 任一不齐或 net_cagr 不等)\n"
        f"- detail: {json.dumps(detail, ensure_ascii=False)}\n"
        f"- elapsed_s: {time.perf_counter() - T0:.1f}\n"
        "- 已完成产物：tmp/subruns/ 与本文件；等待主对话裁定（FA-S1），"
        "不降级、不放宽、不自行修引擎。\n",
        encoding="utf-8")
    (RUN_DIR / "tmp" / "runner_attrib_state.json").write_text(json.dumps({
        "status": "aborted", "failure_reason": "leave-zero-out anchor mismatch",
        "detail": detail,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "stages_s": STAGES, "peak_rss_gb": PEAK_RSS,
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    _logf.close()
    sys.exit(3)


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


def dints(col: pl.Series) -> np.ndarray:
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


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
    "f3r3_config": (None, F3R3_CONFIG),
    "prereg": (None, PREREG_MD),
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

REPS_ALL = sorted(pl.read_csv(
    F3R1_RUN / "outputs/dedup_clusters.csv")["representative"].to_list())
assert len(REPS_ALL) == 17, f"expected 17 reps, got {REPS_ALL}"
all120 = pl.read_csv(F2R1_RUN / "outputs/f2r1_all120.csv")
stats120 = {r["factor_id"]: r for r in all120.iter_rows(named=True)}
SIGNS = {fid: (1.0 if float(stats120[fid]["ic_mean"]) > 0 else -1.0)
         for fid in REPS_ALL}
for fid in REPS_ALL:
    p = F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]] / f"{fid}.parquet"
    pins[f"rep_{fid}"] = {"path": str(p), "sha256": sha256_file(p)}
FACTOR_FRAMES = {}
for fid in REPS_ALL:
    FACTOR_FRAMES[fid] = (
        pl.read_parquet(F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]]
                        / f"{fid}.parquet"))
log(f"  17 factor frames loaded; signs {json.dumps(SIGNS)}")

r16_config = json.loads(R16_CONFIG.read_text(encoding="utf-8"))
r16_metrics = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
chassis_mg = json.loads((CHASSIS_RUN / "outputs/metrics_and_gates.json")
                        .read_text(encoding="utf-8"))
ANCHOR_CAGR = chassis_mg["metrics"]["F3R3-EW"]["net_cagr"]
B1 = r16_metrics["configs"]["C05"]
B1_PATH_NAME = r16_config["configs"]["C05"]["path"]
assert B1["b1m_variant"].startswith("rate_only"), B1["b1m_variant"]
log(f"  anchor net_cagr = {ANCHOR_CAGR!r} (chassis metrics verbatim)")
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
sig_days_dev = all_mes["s"].to_list()   # includes 2020-12-31 (expiry anchor)
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
rank_of_pool = {t: {s: i + 1 for i, s in enumerate(pools_at[t]["ranked"])}
                for t in sig_days}
panel_symbols = sorted({s for t in sig_days for s in pools_at[t]["ranked"]})
log(f"  pools at {sig_days[0]}: n={pools_at[sig_days[0]]['n']}; "
    f"union of ranked symbols: {len(panel_symbols)}")
check_budget("pools")
stage("pools")

# === 4. composite subset rebuild (F3R1 sec 4 verbatim) =======================
log("== 4. composite subset rebuild (F3R1 construction verbatim) ==")


def rebuild_composite(reps: list[str]) -> dict[date, dict[str, float]]:
    """EW composite for a subset of representatives, F3R1 runner sec 4 code
    path verbatim: eligible = R16 pool INTERSECTION (>= ceil(M'/2) reps
    non-null); component = (rank_pct-0.5)*sign(ic_mean) within eligible;
    composite = mean of available components."""
    m = len(reps)
    min_cov = -(-m // 2)
    wide = None
    for fid in reps:
        f = (FACTOR_FRAMES[fid]
             .filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
             .rename({"value": fid}))
        wide = f if wide is None else wide.join(f, on=["symbol", "signal_date"],
                                                how="full", coalesce=True)
    wide = wide.filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
    comp: dict[date, dict[str, float]] = {}
    sizes = []
    for t in sig_days:
        g = wide.filter(pl.col("signal_date") == t)
        have = g.with_columns(
            sum(pl.col(f).is_not_null().cast(pl.Int8) for f in reps).alias("_n"))
        have = (have.filter(pl.col("symbol").is_in(pl.Series(sorted(
            set(pools_at[t]["ranked"])))))
            .filter(pl.col("_n") >= min_cov))
        with_parts = have
        for fid in reps:
            with_parts = with_parts.with_columns(
                ((pl.col(fid).rank(method="average") - 1.0)
                 / pl.max_horizontal(pl.col(fid).count() - 1.0, 1))
                .alias(f"_p_{fid}"))
        tmap: dict[str, float] = {}
        for r in with_parts.iter_rows(named=True):
            zs = [ (r[f"_p_{fid}"] - 0.5) * SIGNS[fid]
                   for fid in reps if r[f"_p_{fid}"] is not None ]
            if zs:
                tmap[r["symbol"]] = sum(zs) / len(zs)
        comp[t] = tmap
        sizes.append(len(tmap))
    log(f"  subset M'={m} min_cov>={min_cov}: eligible min {min(sizes)} "
        f"median {int(np.median(sizes))} max {max(sizes)}")
    return comp


# industry map (chassis verbatim)
_ind = pl.read_csv(INDUSTRY_CSV)
_ind = _ind.with_columns(
    (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
     + "." + pl.col("ts_code").str.split(".").list.first()).alias("sym"))
INDUSTRY_L1: dict[str, str] = dict(zip(_ind["sym"].to_list(),
                                       _ind["l1_name"].to_list()))
IND_OF = lambda sym: INDUSTRY_L1.get(sym, "UNMAPPED")  # noqa: E731
stage("composite_setup")


def build_arm(reps: list[str], tag: str) -> tuple[pl.DataFrame, dict, dict]:
    """Sleeve membership + industry cap + static intents (chassis sec 4/8
    verbatim, EW only).  Returns (intents frame, sleeve log, diagnostics)."""
    comp = rebuild_composite(reps)
    RANKED = {t: sorted(comp[t], key=lambda s: (-comp[t][s], s))
              for t in sig_days}
    members: list[str] = []
    SLEEVE_MEMBERS: dict[date, list[str]] = {}
    SLEEVE_LOG: list[dict] = []
    panel_f3: set = set()
    for t in sig_days:
        ranked = RANKED[t]
        rank_of_m = {s: i + 1 for i, s in enumerate(ranked)}
        kept = [m_ for m_ in members
                if m_ in rank_of_m and rank_of_m[m_] <= 2 * SLEEVE_K]
        kept_set = set(kept)
        ind_count: dict[str, int] = {}
        for m_ in kept:
            ind_count[IND_OF(m_)] = ind_count.get(IND_OF(m_), 0) + 1
        seats = SLEEVE_K - len(kept)
        entrants: list[str] = []
        blocked: list[str] = []
        for c in ranked[:SLEEVE_K]:
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
        SLEEVE_MEMBERS[t] = list(new_members)
        SLEEVE_LOG.append(
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
    max_m = max(len(m_) for m_ in SLEEVE_MEMBERS.values())
    if max_m > SLEEVE_K:
        _fail(f"sleeve {tag}: membership exceeded K={SLEEVE_K}")
    log(f"  sleeve {tag}: max members/month {max_m}, panel symbols "
        f"{len(panel_f3)}")

    def _prev_members_of(T: date) -> set[str]:
        i = sig_days.index(T)
        return set(SLEEVE_MEMBERS[sig_days[i - 1]]) if i > 0 else set()

    rows: list[dict] = []
    for T in sig_days:
        m_ = SLEEVE_MEMBERS[T]
        rank_map = {s: i + 1 for i, s in enumerate(RANKED[T])}
        w_T = float(exposures[T]) * (SLEEVE_W_ON / SLEEVE_E_REF)
        Tp = next_sig.get(T)
        expiry = (date.fromordinal(Tp.toordinal() + 1) if Tp is not None
                  else date.fromordinal(T.toordinal() + 1))
        entries = [s for s in m_ if s not in _prev_members_of(T)]
        exits = [s for s in _prev_members_of(T) if s not in m_]
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
        for sym in sorted(s for s in m_ if s not in entries):
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": rank_map[sym],
                         "expiry_date": expiry, "target_weight": w_T})
    # leg intents (chassis verbatim)
    park_T = sig_days[0]
    park_expiry = date.fromordinal(sig_days[3].toordinal() + 1)
    for sym, w in CHASSIS_LEGS.items():
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
    keys = [(r["symbol"], r["side"], r["source_signal"]) for r in rows]
    dup_m5b = sorted({k for k in keys if keys.count(k) > 1})
    firsts = [(r["symbol"], r["decision_date"], r["decision_session"])
              for r in rows]
    dup_first = sorted({k for k in firsts if firsts.count(k) > 1})
    if dup_m5b or dup_first:
        _fail(f"{tag}: m5-b/first-decision duplicates {dup_m5b[:3]} "
              f"{dup_first[:3]}")
    frame = pl.DataFrame(rows, schema=INTENT_SCHEMA)
    return frame, SLEEVE_LOG, {"panel_f3": sorted(panel_f3),
                               "max_members": max_m,
                               "sleeve_log": SLEEVE_LOG}


stage("composite_setup_done")

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
log(f"  halfday: {half.height} rows kept of {half_rows_total} total")

limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up",
                                  "down_limit": "limit_down"})  # ENGINE-2 bridge
limits = (limits_full.filter(pl.col("symbol").is_in(panel_symbols))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
          .sort("symbol", "date"))
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
    _fail(f"preclose nulls in member-dev panel: {n_null_preclose}")
cal_tc = pl.read_csv(
    sorted(TRADECAL_DIR.glob("chunk_exchange-SSE_*.csv"))[0])
cal_tc = cal_tc.filter((pl.col("is_open") == 1)
                       & (pl.col("cal_date") >= int(DEV_START.strftime("%Y%m%d")))
                       & (pl.col("cal_date") <= int(DEV_END.strftime("%Y%m%d"))))
sse_days = set(cal_tc["cal_date"].to_list())
panel_days = set(dints(etf_panel["date"]).tolist())
if sse_days != panel_days:
    _fail(f"panel dates != sse calendar: missing "
          f"{sorted(sse_days - panel_days)[:5]} extra "
          f"{sorted(panel_days - sse_days)[:5]}")
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
from collections import Counter  # noqa: E402
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
if dict(counts) != DIVIDEND_EXPECT or dividend_events.height != 18:
    _fail(f"dividend events != frozen expectation {DIVIDEND_EXPECT}: {counts}")
log(f"  dividend events: {dividend_events.height} {dict(counts)}")
SYMBOL_META = {m: {"asset_class": "etf", "band": MEMBER_BAND[m],
                   "t_plus": 0} for m in PANEL_SYMS}


def etf_pm_bars(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(
        pl.col("symbol"), pl.col("date").alias("trade_date"),
        pl.lit("pm", dtype=pl.String).alias("session"),
        pl.col("open"), pl.col("high"), pl.col("low"), pl.col("close"))


check_budget("etf assets")
stage("etf_assets")

# === 7. shared engine-input frames (chassis sec 9 verbatim, mixed mode) =====
log("== 7. shared engine input frames (mixed mode, legs only) ==")
used = set(CHASSIS_LEGS)
etf_ts_dtype = daily.schema["tradestatus"]
etf_panel_ts = etf_panel.with_columns(
    pl.lit(1.0, dtype=etf_ts_dtype).alias("tradestatus"))
HALF_COLS = ["symbol", "trade_date", "session", "open", "high", "low", "close"]
etf_p_used = etf_panel_ts.filter(pl.col("symbol").is_in(used))
stage("engine_input_frames")

# === 8. subset loop ==========================================================
ap = argparse.ArgumentParser()
ap.add_argument("--subsets", required=True)
ARGS = ap.parse_args()
SUBSETS = json.loads(Path(ARGS.subsets).read_text(encoding="utf-8"))
log(f"== 8. subset loop: {len(SUBSETS)} subsets ==")

OUT_ROOT = RUN_DIR / "tmp" / "subruns"
state = {"status": "running", "subsets_done": [], "subsets": SUBSETS,
         "stages_s": STAGES}
(RUN_DIR / "tmp" / "runner_attrib_state.json").write_text(
    json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

REF_FRAMES = {name: pl.read_parquet(CHASSIS_RUN / "outputs" / fn)
              for name, fn in (("intents", "F3R3-EW_intents.parquet"),
                               ("fills", "F3R3-EW_fills.parquet"),
                               ("events", "F3R3-EW_events.parquet"),
                               ("daily", "F3R3-EW_daily_equity.parquet"),
                               ("clips_final", "F3R3-EW_clips_final.parquet"))}

for sub in SUBSETS:
    tag, drop = sub["tag"], list(sub.get("drop", []))
    t_sub = time.perf_counter()
    reps = [f for f in REPS_ALL if f not in drop]
    assert len(set(drop) & set(REPS_ALL)) == len(drop)
    log(f"== subset {tag}: drop={drop}, {len(reps)} reps ==")
    fr, sleeve_log, diag = build_arm(reps, tag)
    # per-subset engine frames: stock rows filtered to THIS subset's panel
    # (chassis mixed_frames verbatim: stock rows gain null preclose, ETF rows
    # gain tradestatus=1.0; concat stocks-then-ETFs, sort daily only)
    cfg_syms = diag["panel_f3"]
    daily_c = (daily.filter(pl.col("symbol").is_in(cfg_syms))
               .filter(pl.col("date") <= DEV_END))
    mix_daily = pl.concat([
        daily_c.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("preclose"))
        .select("symbol", "date", "open", "high", "low", "close",
                "tradestatus", "preclose"),
        etf_p_used.select("symbol", "date", "open", "high", "low", "close",
                          "tradestatus", "preclose")]).sort("symbol", "date")
    mix_half = pl.concat([
        half.filter(pl.col("symbol").is_in(cfg_syms))
        .filter(pl.col("trade_date") <= DEV_END).select(HALF_COLS),
        etf_pm_bars(etf_p_used).select(HALF_COLS)], how="vertical")
    limits_c = (limits.filter(pl.col("symbol").is_in(cfg_syms))
                .filter(pl.col("date") <= DEV_END))
    splits_c = splits.filter(pl.col("symbol").is_in(cfg_syms))
    divs_c = dividends.filter(pl.col("symbol").is_in(cfg_syms))
    instr_c = instruments.filter(pl.col("symbol").is_in(cfg_syms))
    t_cfg = time.perf_counter()
    res = run_band_backtest_intents(
        fr, mix_daily, mix_half, limits_c, splits_c, divs_c, instr_c,
        symbol_meta=SYMBOL_META, dividend_events=dividend_events,
        initial_cash=500_000.0)
    wall = time.perf_counter() - t_cfg
    il = res.stats.get("intent_layer") or {}
    log(f"  {tag}: engine {wall:.1f}s, intents {il.get('n_intents')} "
        f"orders {il.get('orders_generated')} filled {il.get('stopped_filled')} "
        f"| rss {rss_gb():.2f} GB")

    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(), DEV_START, DEV_END)
    net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd = er.max_drawdown(sd, sv)["max_drawdown"]
    yr = er.year_returns(sd, sv)
    b1y = {int(k): v for k, v in B1["b1m_net_return_by_year"].items()}
    adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
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
    max_turn = max(v["one_side_turnover"] for v in tby.values())

    anchor_detail = None
    if not drop:
        log("  LEAVE-ZERO-OUT ANCHOR: 5-frame .equals() vs chassis F3R3-EW")
        comparison = {}
        for name, mine in (("intents", fr), ("fills", res.fills),
                           ("events", res.events), ("daily", res.daily),
                           ("clips_final", res.clips_final)):
            same = mine.equals(REF_FRAMES[name])
            comparison[name] = same
            log(f"    {name}.equals(chassis) = {same} "
                f"(mine {mine.height} / ref {REF_FRAMES[name].height})")
        cagr_ok = abs(net_cagr - ANCHOR_CAGR) <= 1e-12
        comparison["net_cagr_matches_chassis"] = cagr_ok
        log(f"    net_cagr {net_cagr!r} vs chassis {ANCHOR_CAGR!r} -> {cagr_ok}")
        anchor_detail = comparison
        if not all(comparison.values()):
            stop_anchor_mismatch(comparison)
        log("  LEAVE-ZERO-OUT ANCHOR PASS (5/5 frames + net_cagr)")

    out_dir = OUT_ROOT / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    fr.write_parquet(out_dir / "intents.parquet")
    res.fills.write_parquet(out_dir / "fills.parquet")
    res.events.write_parquet(out_dir / "events.parquet")
    res.daily.write_parquet(out_dir / "daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / "clips_final.parquet")
    (out_dir / "stats.json").write_text(json.dumps({
        "tag": tag, "drop": drop, "reps": reps,
        "net_cagr": net_cagr, "max_drawdown": mdd,
        "net_return_by_year": {int(k): v for k, v in yr.items()},
        "advantage_years_list": [int(y) for y in adv],
        "advantage_years": len(adv),
        "max_one_side_turnover": max_turn,
        "engine_wall_s": wall, "subset_wall_s": time.perf_counter() - t_sub,
        "anchor_compare": anchor_detail,
        "max_members": diag["max_members"]},
        ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    state["subsets_done"].append({"tag": tag, "net_cagr": net_cagr,
                                  "max_drawdown": mdd})
    (RUN_DIR / "tmp" / "runner_attrib_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    log(f"  {tag}: net {net_cagr * 100:+.2f}% mdd {mdd * 100:.2f}% "
        f"adv {len(adv)}/6 turn {max_turn:.2f}")
    del res, fr, daily_c, mix_daily, mix_half, limits_c
    del splits_c, divs_c, instr_c, sleeve_log, diag
    gc.collect()
    check_budget(f"subset {tag}")

ENGINE_SHA_AT_END = sha256_file(ENGINE_PY)
state["status"] = "completed"
state["engine_sha_at_start"] = ENGINE_SHA_AT_START
state["engine_sha_at_end"] = ENGINE_SHA_AT_END
state["bytes_modified_by_this_run"] = ENGINE_SHA_AT_START != ENGINE_SHA_AT_END
state["peak_rss_gb"] = PEAK_RSS
state["wall_seconds"] = time.perf_counter() - T0
state["stages_s"] = STAGES
state["env_versions"] = ENV_VERSIONS
state["ended_at"] = datetime.now(timezone.utc).isoformat()
(RUN_DIR / "tmp" / "runner_attrib_state.json").write_text(
    json.dumps(state, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== subset loop complete: {len(state['subsets_done'])} subsets, "
    f"wall {state['wall_seconds']:.0f}s, peak rss {PEAK_RSS:.2f} GB ==")
_logf.close()
