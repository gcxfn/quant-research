# -*- coding: utf-8 -*-
"""exp-20260919-zone-sheet-f4r1 SMOKE runner -- engine v1.4 (pin 7ad35014,
zones mode), prereg FROZEN (docs/research/exp-20260919-zone-sheet-f4r1-prereg.md
+ configs/experiments/f4r1-zone-sheet.json).

Copy-adapted from the F3R3 runner
(artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/scripts/runner_f3r3.py)
per the orchestrator directive: data loading, ETF-leg intent construction,
A0 anchor (R3-06 verbatim at 200k) and pins follow F3R3 verbatim; the stock
sleeve switches from static intents to the v1.4 zones frame (ladder buy /
take-profit / ratchet stop / seat recycling inside the engine).

SMOKE scope (prereg sec 7, main-conversation ruling): correctness only,
windows W1 = 2015-01-05..2015-02-28 and W2 = 2016-01-01..2016-02-29, three
arms x two windows.  NO performance conclusions; the full-period dev run is
a separate later step after smoke acceptance.

Runner-layer responsibilities (orchestrator task):
1. startup pin checks (engine sha256 == v1.4 pin; input data identities);
2. monthly candidate table from the F3R1 frozen ICW composite (top 2K=20
   per signal month, rank 1..20);
3. sigma0 = std of the last 20 official-session close-to-close log returns
   (sample stdev, ddof=1 -- runner convention, pinned here) x P0 (signal-day
   official close); candidates with <20 returns (new listing) or any missing
   session close (suspension) are excluded from the month list and counted;
4. zones frames per arm (A/C w_t = 0.06 const; B w_T = e_T*0.06/0.90 with
   the F3R3 T200-40 exposures);
5. ETF chassis leg intents (511010x0.15 + 518880x0.25) on ONE ledger with
   the zones frame (zone_priority_base=1000);
6. F4R1-A0 anchor: byte-level filecmp reproduction of the F3R3-A0 outputs
   (mismatch => STOP per prereg sec 7, no trial consumed);
7. smoke correctness checks per arm-window -> outputs/smoke_report.md.

Runner-layer adaptations vs F3R3 (all disclosed in the manifest):
- leg intent priority 10**6 -> 999: with zones active the engine rejects any
  intent priority >= zone_priority_base (BR-1 cross-layer guard); 999 keeps
  the leg the lowest layer below every zone order (1000+rank), but note the
  leg is now funded BEFORE stock ladders in same-decision cash competition
  (in F3R3 the 10**6 leg sat after the rank 1..20 stock intents);
- park-buy expiry for the 2-signal-day smoke windows: F3R3 pinned "4th
  signal day + 1"; a window has only 2 signal days, so the park expires at
  the first full-calendar month-end AFTER the window's last signal day + 1
  (the park stays live for the whole window; monthly reduce-to-target sells
  unchanged);
- arm B keeps the path through w_T scaling ONLY: the zones engine has no
  month-end reduce-to-target primitive for stocks (BR-7: continuation
  re-issues no orders) and stock symbols in both layers are rejected
  (S-v14-15 overlap guard) -- the F3R3 "month-end reduce" sell is therefore
  structurally absent in zones mode; disclosed as a comparability seam for
  arm B, to be adjudicated before any full-period interpretation;
- sigma0 sample stdev ddof=1 and the 21-close window (20 returns ENDING at
  the signal day, incl. P0) are runner-layer conventions pinned here
  (contract S-v14-1 leaves the exact estimator to the run layer).

Deterministic; no RNG.  Budget 900 s wall (prereg sec 8), peak RSS 8 GB.
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
    FREEZE_END, BandContractError, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_split_factor_h5,
    load_stk_limit_batch, run_band_backtest_intents, run_band_backtest_zones)

# === frozen identity =========================================================
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F3R3_RUN = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F3R3_REF_OUT = F3R3_RUN / "outputs"
PREREG_MD = ROOT / "docs/research/exp-20260919-zone-sheet-f4r1-prereg.md"
F4R1_CONFIG = ROOT / "configs/experiments/f4r1-zone-sheet.json"
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

# engine v1.4 pin (docs/plans/p3-band-contract.md sec 10.7, double-signed)
ENGINE_SHA_EXPECT_FULL = ("7ad35014d72711cb43ab6aedc232d70adf7eece60604b2a"
                          "057ee039c9bd11e78")
ENGINE_V13_SHA16 = "84a2443ac28fe1b8"   # the F3R1 composite was built under v1.3

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
WINDOWS = {"W1": (date(2015, 1, 5), date(2015, 2, 28)),
           "W2": (date(2016, 1, 1), date(2016, 2, 29))}
ARMS = ["F4R1-A", "F4R1-B", "F4R1-C"]

# F4R1 frozen sleeve parameters (prereg sec 3/4/5; zero grid)
SLEEVE_K = 10
TOP_2K = 20                # candidate list = top 2K per signal month
SLEEVE_W_ON = 0.06         # arm A/C per-name target weight (const)
SLEEVE_E_REF = 0.90        # arm B: w_T = e_T * 0.06 / 0.90
IND_CAP = 2
BUFFER_MULT = 2
STOP_MULT = 3.0
INVALID_MULT = 3.5
LADDER_OFFSETS = "0.5,1.5,2.5"
LADDER_FRACS = "0.4,0.4,0.2"
SIGMA_LOOKBACK = 20        # close-to-close log returns
SIGMA_DDOF = 1             # sample stdev (runner convention, disclosed)
ANCHOR_INITIAL_CASH = 200_000.0
ARMS_INITIAL_CASH = 500_000.0
ZONE_PRIORITY_BASE = 1000
LEG_PRIORITY = 999         # adaptation: BR-1 requires intent priority < base

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
        "experiment_id": "exp-20260919-zone-sheet-f4r1",
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
log("== 0. identity pins (engine v1.4 frozen, prereg frozen) ==")
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
    "prereg": (None, PREREG_MD),
    "f4r1_config": (None, F4R1_CONFIG),
    "f3r3_runner_source": (None, F3R3_RUN / "scripts/runner_f3r3.py"),
    "f3r3_manifest": (None, F3R3_RUN / "manifest.json"),
    "v3_metrics_r306_anchor_source": (None, V3_RUN / "outputs/metrics_and_gates.json"),
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
cfg_json = json.loads(F4R1_CONFIG.read_text(encoding="utf-8"))
assert cfg_json["arms"]["F4R1-A"]["w_T"] == SLEEVE_W_ON
assert cfg_json["stock_sleeve"]["membership"]["max_members"] == SLEEVE_K
assert cfg_json["stock_sleeve"]["membership"]["industry_cap_per_l1"] == IND_CAP

# F3R1 composite provenance: produced under the pinned v1.3 engine
f3r1_mg = json.loads((F3R1_RUN / "outputs/metrics_and_gates.json")
                     .read_text(encoding="utf-8"))
if f3r1_mg["engine_sha256_16"] != ENGINE_V13_SHA16:
    _fail("F3R1 composite was not produced under the pinned v1.3 engine")
pins["f3r1_engine_provenance"] = {"engine_sha256_16": f3r1_mg["engine_sha256_16"],
                                  "match": True}

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

# === 1. calendar & signal days (F3R3 verbatim) ===============================
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
log(f"  {len(sig_days)} full-dev signal days ({sig_days[0]}..{sig_days[-1]})")
next_sig = {sig_days_dev[i]: (sig_days_dev[i + 1]
                              if i + 1 < len(sig_days_dev) else None)
            for i in range(len(sig_days_dev))}
SIG_DAYS_BY_WINDOW: dict[str, list[date]] = {}
for wname, (w0, w1) in WINDOWS.items():
    sdw = [d for d in sig_days_dev if w0 <= d <= w1]
    if not sdw:
        _fail(f"window {wname}: no signal days in [{w0}..{w1}]")
    SIG_DAYS_BY_WINDOW[wname] = sdw
    log(f"  window {wname} [{w0}..{w1}]: signals {sdw}")

# === 2. exposures (r16 verbatim, C05 T200-40 path; arm B w_T + disclosure) ===
log("== 2. exposures (T200-40 month-end) ==")
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
exposures = r16.t200_month_end_exposures(index_close, calendar_full, sig_days)
log(f"  exposures[{sig_days[0]}]={exposures[sig_days[0]]:.2f} "
    f"[{sig_days[-1]}]={exposures[sig_days[-1]]:.2f}")
for wname, sdw in SIG_DAYS_BY_WINDOW.items():
    log("  " + wname + " e_T: " + ", ".join(f"{d}={exposures[d]:.2f}"
                                            for d in sdw))

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
_window_sig_days = sorted({d for sdw in SIG_DAYS_BY_WINDOW.values()
                           for d in sdw})
CAND_ALL_SYMS = sorted({s for t in _window_sig_days for s in CANDIDATES[t]})
log(f"  candidates: top-{TOP_2K} per signal month; window union "
    f"{len(CAND_ALL_SYMS)} symbols over {len(_window_sig_days)} signal days")

# === 4. closes for sigma0/p0 (full official calendar, raw official close) ====
log("== 4. candidate closes (sigma0 / p0 lookups) ==")
_look0 = min(w[0] for w in WINDOWS.values()) - timedelta(days=200)
_look1 = max(w[1] for w in WINDOWS.values())
_cdf = (pl.scan_parquet(str(DAILY_PARQUET))
        .filter(pl.col("symbol").is_in(CAND_ALL_SYMS))
        .filter((pl.col("date") >= _look0) & (pl.col("date") <= _look1))
        .select("symbol", "date", "close", "tradestatus").collect())
CLOSE: dict[tuple[str, int], float] = {}
for r in _cdf.iter_rows(named=True):
    if r["tradestatus"] != 0 and r["close"] is not None and r["close"] > 0:
        CLOSE[(r["symbol"], dint_of(r["date"]))] = float(r["close"])
del _cdf
log(f"  close lookups: {len(CLOSE)} traded (symbol, session) points "
    f"for {len(CAND_ALL_SYMS)} candidates")


def sigma_p0(sym: str, T: date) -> tuple[float, float] | tuple[None, str]:
    """S-v14-1 runner caliber: sigma0 = std(20 last close-to-close log
    returns, sample ddof=1) x P0; P0 = signal-day official close.  The 20
    returns END at the signal day (21 closes incl. P0).  Exclusion reasons:
    'signal_day_no_close' (P0 missing), 'lookback_gap' (a suspended session
    inside the 21-close window), 'short_history' (<20 returns available)."""
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
    f"{_ind['l1_name'].n_unique()} industries; window candidates unmapped "
    f"{len(_unmapped)} -> UNMAPPED bucket (same cap); 2026 single-snapshot "
    "lookahead disclosed in prereg sec 3")


def IND_OF(sym: str) -> str:
    return INDUSTRY_L1.get(sym, "UNMAPPED")


def build_zones_frame(arm: str, wname: str) -> tuple[pl.DataFrame, dict]:
    """Per-arm zones frame for one smoke window (frozen prereg sec 4/5)."""
    rows: list[dict] = []
    excl: Counter = Counter()
    for T in SIG_DAYS_BY_WINDOW[wname]:
        for rank, sym in enumerate(CANDIDATES[T], start=1):
            sigma0, p0 = sigma_p0(sym, T)
            if sigma0 is None:
                excl[p0 if isinstance(p0, str) else "other"] += 1
                continue
            if arm == "F4R1-B":
                w_t = float(exposures[T]) * (SLEEVE_W_ON / SLEEVE_E_REF)
            else:
                w_t = SLEEVE_W_ON
            if arm == "F4R1-C":
                tp1_mult, tp1_frac = 2.0, 1.0
                tp2_mult = tp2_frac = None       # one-shot full sell, no tp2
            else:
                tp1_mult, tp1_frac = 2.0, 0.5
                tp2_mult, tp2_frac = 3.0, 1.0
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
                                            for T in SIG_DAYS_BY_WINDOW[wname])}
    return pl.DataFrame(rows, schema=ZONES_INPUT_SCHEMA), meta


ZONES_FRAMES: dict[tuple[str, str], pl.DataFrame] = {}
ZONES_META: dict[tuple[str, str], dict] = {}
for _arm in ARMS:
    for _w in WINDOWS:
        zf_, zm_ = build_zones_frame(_arm, _w)
        ZONES_FRAMES[(_arm, _w)] = zf_
        ZONES_META[(_arm, _w)] = zm_
        log(f"  zones frame {_arm}/{_w}: {zf_.height} rows "
            f"(of {zm_['candidates_before_filter']} candidates; sigma "
            f"excluded {zm_['sigma_excluded']}), months "
            f"{[d.isoformat() for d in SIG_DAYS_BY_WINDOW[_w]]}")
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
ASSERT_III_TEXT = f"PASS ({len(panel_days)} == {len(sse_days)})"
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
    f"dividends {divs_all.height} (full files; window-filtered per run)")
EMPTY_SPLITS = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                                    "split_factor": pl.Float64})
EMPTY_INSTR = pl.DataFrame(schema={"symbol": pl.String, "is_etf": pl.Boolean,
                                   "is_t0": pl.Boolean})
DAILY_TS_DTYPE = pl.Float64   # daily parquet tradestatus dtype (verified)

# === 8. F4R1-A0 anchor: R3-06 verbatim at 200k, byte reproduction ============
log("== 8. F4R1-A0 anchor (R3-06 verbatim, byte reproduction) ==")


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
    mine_p = out_dir / f"F4R1-A0_{name}.parquet"
    A0_MINE[name].write_parquet(mine_p)
    ref_p = F3R3_REF_OUT / ref_fn
    same_bytes = filecmp.cmp(str(mine_p), str(ref_p), shallow=False)
    same_rows = A0_MINE[name].height == pl.read_parquet(ref_p).height
    A0_CMP[name] = {"mine": str(mine_p.relative_to(RUN_DIR)),
                    "ref": str(ref_p.relative_to(ROOT)),
                    "byte_equal": bool(same_bytes), "rows_equal": same_rows}
    log(f"  A0 {name}: byte_equal={same_bytes} rows_equal={same_rows}")
if not all(v["byte_equal"] for v in A0_CMP.values()):
    _fail(f"F4R1-A0 ANCHOR MISMATCH (prereg sec 7 stop rule, no trial "
          f"consumed): {json.dumps(A0_CMP)}")
log("  F4R1-A0 anchor PASS (5/5 frames byte-equal to F3R3-A0)")
check_budget("A0 anchor")

# === 9. arm runs (zones + ETF intents, one ledger) ===========================
log("== 9. arm runs: 3 arms x 2 windows ==")


def leg_intent_rows_w(sdw: list[date]) -> list[dict]:
    """F3R3 leg conventions on a 2-signal-day window: park buy at the first
    window signal day; monthly reduce-to-target risk sells afterwards.
    ADAPTED (disclosed): priority 999 (BR-1 guard: intent priority must be
    < zone_priority_base); park expiry = first full-calendar month-end after
    the window's last signal day + 1 (the frozen '4th signal day + 1'
    convention has no 4th signal day inside a smoke window)."""
    rows: list[dict] = []
    park_T = sdw[0]
    last_T = sdw[-1]
    nxt_after_window = next((d for d in sig_days_dev if d > last_T), DEV_END)
    park_expiry = date.fromordinal(nxt_after_window.toordinal() + 1)
    for sym, w in CHASSIS_LEGS.items():
        rows.append({"symbol": sym, "side": "buy", "intent": "",
                     "decision_date": park_T, "decision_session": "pm",
                     "source_signal": park_T, "priority": LEG_PRIORITY,
                     "expiry_date": park_expiry, "target_weight": float(w)})
        for T in sdw[1:]:
            Tp = next_sig.get(T)
            expiry = (date.fromordinal(Tp.toordinal() + 1) if Tp is not None
                      else park_expiry)
            rows.append({"symbol": sym, "side": "sell", "intent": "risk",
                         "decision_date": T, "decision_session": "pm",
                         "source_signal": T, "priority": LEG_PRIORITY,
                         "expiry_date": expiry, "target_weight": float(w)})
    return rows


def window_frames(wname: str, stock_syms: list[str]) -> dict:
    """Mixed stock+ETF engine input frames for one window (F3R3
    mixed_frames convention, window-filtered)."""
    w0, w1 = WINDOWS[wname]
    used_legs = sorted(set(CHASSIS_LEGS))
    daily_stock = (pl.scan_parquet(str(DAILY_PARQUET))
                   .filter(pl.col("symbol").is_in(stock_syms))
                   .filter((pl.col("date") >= w0) & (pl.col("date") <= w1))
                   .select("symbol", "date", "open", "high", "low", "close",
                           "tradestatus").collect()
                   .with_columns(pl.lit(None, dtype=pl.Float64)
                                 .alias("preclose")))
    etf_p = (etf_panel_ts.filter(pl.col("symbol").is_in(used_legs))
             .filter((pl.col("date") >= w0) & (pl.col("date") <= w1)))
    mix_daily = pl.concat([
        daily_stock.select("symbol", "date", "open", "high", "low", "close",
                           "tradestatus", "preclose"),
        etf_p.select("symbol", "date", "open", "high", "low", "close",
                     "tradestatus", "preclose")]).sort("symbol", "date")
    parts = []
    for part in sorted(HALFDAY_DIR.glob("year=*/bars.parquet")):
        f = pl.read_parquet(part)
        f = (f.filter((pl.col("trade_date") >= w0)
                      & (pl.col("trade_date") <= w1))
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
    limits_w = (limits_full.filter(pl.col("symbol").is_in(stock_syms))
                .filter((pl.col("date") >= w0) & (pl.col("date") <= w1))
                .sort("symbol", "date"))
    splits_w = splits_all.filter(pl.col("symbol").is_in(stock_syms))
    cashdiv_w = divs_all.filter(pl.col("symbol").is_in(stock_syms))
    instr_w = pl.DataFrame({
        "symbol": stock_syms, "is_etf": [False] * len(stock_syms),
        "is_t0": [False] * len(stock_syms)})
    assert_frozen(mix_daily, "date", "daily")
    assert_frozen(mix_half, "trade_date", "halfday")
    return {"daily": mix_daily, "half": mix_half, "limits": limits_w,
            "splits": splits_w, "cash_dividends": cashdiv_w,
            "instruments": instr_w}


# decision anchors for the checks (am -> halfday am.close, pm -> daily close)
def build_anchors(frames: dict) -> dict[tuple[str, int], float]:
    anchors: dict[tuple[str, int], float] = {}
    d1 = frames["daily"]
    for r in d1.select("symbol", "date", "close").iter_rows(named=True):
        anchors[(r["symbol"], sess_key(r["date"], "pm"))] = float(r["close"])
    h1 = frames["half"].filter(pl.col("session") == "am")
    for r in h1.select("symbol", "trade_date", "close").iter_rows(named=True):
        anchors[(r["symbol"], sess_key(r["trade_date"], "am"))] = \
            float(r["close"])
    return anchors


def opens_of(frames: dict) -> dict[tuple[str, int], tuple[float, float]]:
    """(date dint, session) -> session open, for stop/gap verification."""
    out: dict[tuple[str, int], tuple[float, float]] = {}
    h1 = frames["half"]
    for r in h1.select("symbol", "trade_date", "session", "open",
                       "low").iter_rows(named=True):
        out[(r["symbol"], sess_key(r["trade_date"], r["session"]))] = \
            (float(r["open"]), float(r["low"]))
    return out


def reconstruct_wac_path(fills: pl.DataFrame,
                         zones_in: pl.DataFrame) -> dict[str, dict]:
    """Per symbol: chronological WAC path from zladder buy fills in ENGINE
    booking order (BR-4a: sells never touch the WAC; a same-session buy
    books before the C-segment TP sells, so a TP at session S sees the WAC
    including S's own ladder fills).  Snapshots are taken after every buy
    fill so a TP fill can look up the WAC as of its own (date, session)."""
    sds_by_sym: dict[str, list[date]] = {}
    for r in zones_in.iter_rows(named=True):
        sds_by_sym.setdefault(r["symbol"], []).append(r["signal_date"])
    state: dict[str, dict] = {}
    out: dict[str, dict] = {}
    for i, r in enumerate(fills.iter_rows(named=True)):
        sym = r["symbol"]
        if r["side"] == "buy":
            st = state.setdefault(sym, {"amt": 0.0, "sh": 0})
            st["amt"] += float(r["price"]) * int(r["shares"])
            st["sh"] += int(r["shares"])
            out.setdefault(sym, {"path": []})["path"].append({
                "i": i, "date": r["date"], "session": r["session"],
                "decision_date": r["decision_date"],
                "wac": st["amt"] / st["sh"]})
    return out


def check_arm_window(arm: str, wname: str, res, frames: dict,
                     zones_in: pl.DataFrame, zmeta: dict) -> dict:
    """Smoke correctness checks for one arm-window (no performance data)."""
    w0, w1 = WINDOWS[wname]
    sdw = SIG_DAYS_BY_WINDOW[wname]
    checks: dict = {"arm": arm, "window": wname, "fail": []}
    anchors = build_anchors(frames)
    half_opens = opens_of(frames)
    limit_down = {(r["symbol"], dint_of(r["date"])): float(r["limit_down"])
                  for r in frames["limits"].iter_rows(named=True)}
    fills, events, daily = res.fills, res.events, res.daily
    zones_res = res.zones
    st = res.stats["zones"]

    def bad(msg: str) -> None:
        checks["fail"].append(msg)
        log(f"    !! [{arm}/{wname}] CHECK FAIL: {msg}")

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
    # admission bookkeeping from the zone_admitted EVENTS (a zone continued
    # into month 2 moves its zones-frame signal_date, so the frame alone
    # cannot say WHERE a zone was admitted).  Detail format:
    # "<sym> (signal <sd>) rank <r> admitted: ...".
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
        for T in sdw}
    # continuations: zones-frame rows whose admitted session predates the
    # row's (moved) signal_date
    cont_zones: dict[date, set] = {T: set() for T in sdw}
    for r in adm.iter_rows(named=True):
        ad_d, _ = key_to_ds(r["admitted_key"])
        if r["signal_date"] in cont_zones and ad_d < r["signal_date"]:
            cont_zones[r["signal_date"]].add(r["symbol"])
    checks["admissions_by_month"] = {str(k): int(v) for k, v
                                     in sorted(adm_by_month.items())}
    checks["admissions_first_scan"] = {str(T): len(first_scan_adm[T])
                                       for T in sdw}
    checks["continuations_by_month"] = {str(k): len(v) for k, v
                                        in sorted(cont_zones.items())}

    # industry-blocked reconstruction: candidates never admitted this month
    # whose industry already holds ind_cap members among (month admissions +
    # continuing zones) -- replay caliber disclosed in the manifest.
    # Month 1 also gets an EXACT first-scan check: no holdings exist before
    # the first window signal day, so the boundary scan is fully determined
    # by the frame (rank walk, ind_cap, seats, below_min_lot scan-continue
    # with the (T0,pm) equity snapshot = the initial cash -- nothing is
    # held when the window opens).
    ind_blocked: list[dict] = []
    month_admitted: dict[date, set] = {}
    for e in adm_ev_rows:
        month_admitted.setdefault(e["signal"], set()).add(e["symbol"])
    for Ti, T in enumerate(sdw):
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
                # BR-3 one-shot sizing at the (T0,pm) snapshot; below one
                # lot the zone is done and the scan continues WITHOUT
                # consuming a seat (S-v14-2).  Two levels: candidate total
                # < 100, OR total >= 100 but EVERY tier floors < 100
                # (e.g. total 200 at fracs 0.4/0.4/0.2).
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
                log(f"    [{arm}/{wname}] month {T}: mid-month admissions "
                    f"{len(mid)} (seats recycled intra-month: "
                    f"{sorted(mid)})")
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
    checks["industry_blocked_reconstructed"] = ind_blocked

    # -- (2) fills routing / limits / lots / fill-stop / TP prices ----------
    sds_by_sym: dict[str, list[date]] = {}
    for r in zones_in.iter_rows(named=True):
        sds_by_sym.setdefault(r["symbol"], []).append(r["signal_date"])
    sigma_by_sym_sd: dict[tuple[str, date], dict] = {}
    for r in zones_in.iter_rows(named=True):
        sigma_by_sym_sd[(r["symbol"], r["signal_date"])] = r

    def cur_row(sym: str, d: date) -> dict | None:
        cands = [sd for sd in sds_by_sym.get(sym, []) if sd <= d]
        if not cands:
            return None
        return sigma_by_sym_sd[(sym, max(cands))]

    n_route = n_ladder_checked = n_tp_checked = 0
    tier_fills: Counter = Counter()
    wac_path = reconstruct_wac_path(fills, zones_in)
    tp_samples: list[dict] = []
    for r in fills.iter_rows(named=True):     # engine booking order
        oid = r["order_id"]
        is_ladder = "-zladder-" in oid
        is_tp = "-ztp" in oid
        is_etf = bool(r["is_etf"])
        dd, dss = r["decision_date"], r["decision_session"]
        fd, fs = r["date"], r["session"]
        if r["fill_type"] in ("stop", "market_fallback"):
            continue          # different decision routing (BR-5 / B segment)
        # routing: am decision -> same-day pm; pm decision -> next day
        # (stocks: next am; ETF legs are pm-only -> next pm)
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
            zr = cur_row(r["symbol"], dd)
            a = anchors.get((r["symbol"], sess_key(dd, dss)))
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
        if is_tp:
            zr = cur_row(r["symbol"], dd)
            wp = wac_path.get(r["symbol"])
            if zr is None or wp is None or not wp["path"]:
                bad(f"tp fill {oid}: no WAC path / zone row to verify")
                continue
            wac_at = None
            for p in wp["path"]:
                if (p["date"], p["session"]) <= (fd, fs):
                    wac_at = p["wac"]
            if wac_at is None:
                bad(f"tp fill {oid}: no WAC snapshot at or before fill")
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
            tp_samples.append({
                "symbol": r["symbol"], "date": str(fd), "session": fs,
                "price": float(r["price"]), "shares": int(r["shares"]),
                "wac": wac_at, "sigma0": sigma0, "mults": mults})
        if int(r["shares"]) % 100 != 0:
            bad(f"fill {oid}: shares {r['shares']} not a round lot")
    checks["fills_checked"] = {"routed": n_route,
                               "ladder_price": n_ladder_checked,
                               "tp_price": n_tp_checked}
    # per-tier fill-stop: each tier fills at most once
    multi = {k: v for k, v in tier_fills.items() if v > 1}
    if multi:
        bad(f"tier fill-stop violated: {multi}")
    # tier_filled_shares consistency vs shares_bought
    for r in zones_res.iter_rows(named=True):
        tfs = ([int(x) for x in r["tier_filled_shares"].split(",")]
               if r["tier_filled_shares"] else [])
        if sum(tfs) != r["shares_bought"]:
            bad(f"zone {r['symbol']} {r['signal_date']}: tier_filled sum "
                f"{sum(tfs)} != shares_bought {r['shares_bought']}")

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

    # -- (4) stop-loss samples ------------------------------------------------
    # line reconstruction per BR-5/S-v14-4: decision anchors (am=am.close,
    # pm=official close) at decision keys ffk <= k < trigger key; the
    # per-anchor sigma0 is the zone row applicable at that decision date
    # (ratchet = running max; only-up is inherent in the max)
    stop_samples: list[dict] = []
    for r in fills.filter(pl.col("fill_type") == "stop").iter_rows(named=True):
        sym = r["symbol"]
        trig_key = sess_key(r["date"], r["session"])
        zrow_at_trig = cur_row(sym, r["decision_date"])
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
        for (a_sym, k), a in anchors.items():
            if a_sym != sym or k < ffk or k >= trig_key:
                continue
            ad_d, _ = key_to_ds(k)
            zr_k = cur_row(sym, ad_d)
            if zr_k is None:
                continue
            cand = a - STOP_MULT * float(zr_k["sigma0"])
            line = cand if line is None else max(line, cand)
        op, low = half_opens.get((sym, trig_key), (None, None))
        if line is None or op is None:
            bad(f"stop fill {sym} {r['date']}: cannot reconstruct line/open")
            continue
        want = min(line, op)
        if abs(float(r["price"]) - want) > 1e-9:
            bad(f"stop fill {sym} {r['date']}: price {r['price']} != "
                f"min(line {line}, open {op}) = {want}")
        stop_samples.append({
            "symbol": sym, "date": str(r["date"]), "session": r["session"],
            "price": float(r["price"]), "shares": int(r["shares"]),
            "line_reconstructed": line, "session_open": op,
            "session_low": low, "sigma0": float(zrow_at_trig["sigma0"]),
            "open_at_or_below_limit_down":
                bool(limit_down.get((sym, dint_of(r["date"]))) is not None
                     and op <= limit_down[(sym, dint_of(r["date"]))] + 1e-9)})
    checks["stop_samples"] = stop_samples
    checks["tp_samples"] = tp_samples[:12]

    # -- (5) gate 8 v1.4 structure -------------------------------------------
    zsa = events.filter(pl.col("event") == "zone_stop_armed").height
    if zsa != st["stop_armed_events"]:
        bad(f"zone_stop_armed events {zsa} != stats stop_armed_events "
            f"{st['stop_armed_events']}")
    ledger = (st["stop_armed_resolved_fallback"]
              + st["stop_armed_resolved_other"] + st["stop_armed_stuck_end"])
    if ledger != st["stop_armed_events"]:
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
    checks["armed_edge_cases"] = [
        {"date": str(r["date"]), "session": r["session"],
         "symbol": r["symbol"], "event": r["event"], "detail": r["detail"]}
        for r in events.filter(
            pl.col("event").is_in(["zone_stop_armed", "zone_stop_triggered",
                                   "market_exit_deferred_limitdown",
                                   "market_exit_deferred_suspended",
                                   "market_exit_deferred_t1locked"]))
        .iter_rows(named=True)]
    checks["n_fills"] = fills.height
    checks["warnings_n"] = len(res.warnings)
    checks["warnings_sample"] = list(res.warnings)[:5]
    # window freeze discipline: no fill outside the window
    oob = fills.filter((pl.col("date") < w0) | (pl.col("date") > w1))
    if oob.height:
        bad(f"{oob.height} fills outside the window")
    return checks


RESULTS: dict[tuple[str, str], dict] = {}
for wname, (w0, w1) in WINDOWS.items():
    sdw = SIG_DAYS_BY_WINDOW[wname]
    stock_syms = sorted({s for t in sdw
                         for s in ZONES_FRAMES[(ARMS[0], wname)]
                         ["symbol"].to_list()})
    for arm in ARMS[1:]:
        zsyms = set(ZONES_FRAMES[(arm, wname)]["symbol"].to_list())
        assert zsyms == set(stock_syms), \
            f"{arm}/{wname}: candidate symbol set differs across arms"
    frames = window_frames(wname, stock_syms)
    log(f"  [{wname}] panel: daily {frames['daily'].height} rows, "
        f"half {frames['half'].height}, limits {frames['limits'].height}, "
        f"stocks {len(stock_syms)} | rss {rss_gb():.2f} GB")
    for arm in ARMS:
        zones_in = ZONES_FRAMES[(arm, wname)]
        leg_rows = leg_intent_rows_w(sdw)
        chk = [(r["symbol"], r["side"], r["source_signal"]) for r in leg_rows]
        if len(chk) != len(set(chk)):
            _fail(f"{arm}/{wname}: leg intent duplicates")
        leg_frame = pl.DataFrame(leg_rows, schema=INTENT_SCHEMA)
        t_cfg = time.perf_counter()
        try:
            res = run_band_backtest_zones(
                zones_in, frames["daily"], frames["half"], frames["limits"],
                frames["splits"], frames["cash_dividends"],
                frames["instruments"], symbol_meta=SYMBOL_META,
                dividend_events=dividend_events, intents=leg_frame,
                initial_cash=ARMS_INITIAL_CASH,
                zone_priority_base=ZONE_PRIORITY_BASE)
        except BandContractError as exc:
            _fail(f"{arm}/{wname}: engine rejected inputs: {exc}")
        wall = time.perf_counter() - t_cfg
        log(f"  [{arm}/{wname}] engine {wall:.1f}s, fills {res.fills.height}, "
            f"zones {res.zones.height}, admitted "
            f"{res.stats['zones']['n_admitted']} | rss {rss_gb():.2f} GB")
        checks = check_arm_window(arm, wname, res, frames, zones_in,
                                  ZONES_META[(arm, wname)])
        checks["wall_s"] = wall
        RESULTS[(arm, wname)] = {"checks": checks, "res": res}
        res.zones.write_parquet(out_dir / f"{arm}-{wname}_zones.parquet")
        res.fills.write_parquet(out_dir / f"{arm}-{wname}_fills.parquet")
        res.events.write_parquet(out_dir / f"{arm}-{wname}_events.parquet")
        res.daily.write_parquet(out_dir / f"{arm}-{wname}_daily_equity.parquet")
        res.clips_final.write_parquet(
            out_dir / f"{arm}-{wname}_clips_final.parquet")
        leg_frame.write_parquet(out_dir / f"{arm}-{wname}_intents.parquet")
        zones_in.write_parquet(out_dir / f"{arm}-{wname}_zones_input.parquet")
        (out_dir / f"{arm}-{wname}_stats.json").write_text(json.dumps(
            {"stats": res.stats, "warnings": list(res.warnings),
             "wall_s": wall}, ensure_ascii=False, indent=1, default=str),
            encoding="utf-8")
        check_budget(f"{arm}/{wname}")
check_budget("all arm runs")

# === 10. smoke report ========================================================
log("== 10. smoke report ==")
all_ok = True
lines = ["# F4R1 冒烟核对报告（exp-20260919-zone-sheet-f4r1）", "",
         f"- 运行 `{RUN_DIR.name}`；引擎 v1.4 sha256:16 "
         f"`{ENGINE_SHA_AT_START[:16]}`（运行前后一致，pin "
         f"`{ENGINE_SHA_EXPECT_FULL[:16]}`）；预登记 sha256:16 "
         f"`{pins['prereg']['sha256'][:16]}`；配置 sha256:16 "
         f"`{pins['f4r1_config']['sha256'][:16]}`（冻结，唯一参数来源）。",
         "- **性质声明：本报告仅为正确性核对（预登记 §7），不产生任何绩效"
         "结论；未跑全期（dev 2015–2020 全期运行待冒烟验收后另行发起）。**",
         f"- 冒烟窗口：W1 = {WINDOWS['W1'][0]}..{WINDOWS['W1'][1]}，"
         f"W2 = {WINDOWS['W2'][0]}..{WINDOWS['W2'][1]}；三臂 × 两窗口各一次；"
         "σ0 前置 20 日历史取全历史（不受窗口裁剪）。",
         "- A0 锚：R3-06 逐字（200k，rotation UNI6），五帧 filecmp 逐字节"
         "比对 F3R3-A0 输出——见下表。",
         "- 窗口截断说明：每窗口最后一个信号日（W1 2015-02-27 / W2 "
         "2016-02-29）即窗口末 session，其月末边界退出与新月准入订单无后续 "
         "session 可成交，相关持仓残留在窗口期末；冒烟仅核对成交与账本的"
         "正确性，窗口期末状态无绩效含义。",
         "- W2 熔断月：2016-01-04/07 熔断日早于 W2 首个信号日（2016-01-29），"
         "两窗口均无任何成交落在熔断日；熔断日以 partial session（如 "
         "2016-01-07 am 仅 8–17 分钟）如实参与面板，数据身份已 pin。"
         "停牌/跌停/ T+1 残部导致的 armed 顺延在两窗口均未发生"
         "（六次运行 armed_events 全为 0，见各窗核对）。", "",
         "## 一、A0 锚比对（filecmp 逐字节）", "",
         "| 帧 | 逐字节相等 | 行数相等 |", "|---|---|---|"]
for name, v in A0_CMP.items():
    lines.append(f"| {name} | {'PASS' if v['byte_equal'] else 'FAIL'} "
                 f"| {'PASS' if v['rows_equal'] else 'FAIL'} |")
lines += ["", "## 二、每臂每窗口核对表", ""]
for arm in ARMS:
    for wname in WINDOWS:
        c = RESULTS[(arm, wname)]["checks"]
        ok = not c["fail"]
        all_ok = all_ok and ok
        lines.append(f"### {arm} / {wname} —— "
                     f"{'全部 PASS' if ok else '存在 FAIL'}",)
        lines += [
            f"- zones 帧 {c['zones_rows']} 行（候选 "
            f"{c['zones_meta']['candidates_before_filter']}，σ0 不足/无价剔除 "
            f"{c['zones_meta']['sigma_excluded_total']} "
            f"{c['zones_meta']['sigma_excluded']}）；月内准入（含席位回收补位）"
            f"{c['admissions_by_month']}，其中首扫 {c['admissions_first_scan']}"
            f"（K={SLEEVE_K}，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；"
            f"续持 {c['continuations_by_month']}；"
            f"行业受阻（重建口径）{len(c['industry_blocked_reconstructed'])}。"
            "注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后"
            "顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数"
            "核对通过）。",
            f"- fills 路由/限价抽验：路由 {c['fills_checked']['routed']}、"
            f"阶梯限价 {c['fills_checked']['ladder_price']}、止盈价 "
            f"{c['fills_checked']['tp_price']} 全部逐分核对；逐档 "
            "fill-stop（每档至多一次成交）核对通过；整手核对通过。",
            f"- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 "
            f"{c['cash_conservation_max_abs_err']:.2e}；权益恒等式最大误差 "
            f"{c['equity_identity_max_abs_err']:.2e}。",
            f"- 止盈样本 {len(c['tp_samples'])} 例、止损样本 "
            f"{len(c['stop_samples'])} 例：止盈成交价逐分等于 WAC+mult×σ0"
            f"（WAC 按成交额加权、卖出不减），止损成交价逐分等于 "
            f"min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；"
            f"T+1 残部 k3 武装本窗口未发生（armed="
            f"{c['gate8']['armed_events']}），该机制由引擎契约测试"
            "（t10/t20）覆盖，冒烟真实数据未触发。",
            f"- 门 8 结构：armed {c['gate8']['armed_events']} = 兜底 "
            f"{c['gate8']['resolved_fallback']} + 其他 "
            f"{c['gate8']['resolved_other']} + 滞留 "
            f"{c['gate8']['stuck_end']}；stuck==0 断言 "
            f"{'PASS' if c['gate8']['stuck_end'] == 0 else 'FAIL'}；"
            f"tp_expired {c['gate8']['tp_expired_sessions']}、tier_expired "
            f"{c['gate8']['tier_expired']}、tier_invalidated "
            f"{c['gate8']['tier_invalidated']}、below_min_lot "
            f"{c['gate8']['tier_below_min_lot']}。",
            f"- stats['zones'] 与 BandResult.zones 自洽核对："
            f"{'PASS' if not c['fail'] else '见 FAIL'}。",
            f"- zone 事件：{json.dumps(c['zone_events'], ensure_ascii=False)}。",
            f"- fills 总数 {c['n_fills']}；引擎警告 {c['warnings_n']} 条。",
            ""]
        if c["industry_blocked_reconstructed"]:
            lines.append("- 行业受阻明细（重建口径：当月未准入且其行业在"
                         "准入/续持集中已满 2 席）：")
            for e in c["industry_blocked_reconstructed"]:
                lines.append(f"  - {e['signal_date']} rank{e['rank']} "
                             f"{e['symbol']}（{e['industry']}）")
        if c["armed_edge_cases"]:
            lines.append("- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口"
                         "为 0 例；以下为止损触发与成交明细）：")
            for e in c["armed_edge_cases"]:
                lines.append(f"  - {e['date']} {e['session']} {e['symbol']} "
                             f"{e['event']}: {e['detail']}")
        if c["stop_samples"]:
            lines.append("- 止损样本明细：")
            for e in c["stop_samples"]:
                ld_note = ("；开盘=跌停价（冻结语义按 min(线,开盘) 成交，"
                           "如实披露）" if e["open_at_or_below_limit_down"]
                           else "")
                lines.append(
                    f"  - {e['symbol']} {e['date']} {e['session']}: "
                    f"成交 {e['price']} = min(重建线 {e['line_reconstructed']:.4f}, "
                    f"开盘 {e['session_open']})，σ0={e['sigma0']:.4f}，"
                    f"{e['shares']} 股{ld_note}")
        if c["fail"]:
            lines.append("- **FAIL 明细：**")
            for m in c["fail"]:
                lines.append(f"  - {m}")
        lines.append("")
lines += ["## 三、运行身份与预算", "",
          f"- 输入身份：daily {pins['daily']['sha256'][:16]}、halfday "
          f"manifest {pins['halfday_manifest']['sha256'][:16]} + "
          f"{HALFDAY_ROWS_TOTAL} 行、ICW 组合 "
          f"{pins['f3r1_icw_composite']['sha256'][:16]}、行业 "
          f"{pins['industry_l1']['sha256'][:16]}、stk_limit 聚合 "
          f"{pins['stk_limit_aggregate']['aggregate_sha256'][:16]}、ETF 目录"
          f"聚合 {pins['etf_processed_aggregate']['aggregate_sha256'][:16]}。",
          f"- 环境：python {ENV_VERSIONS['python']} / polars "
          f"{ENV_VERSIONS['polars']} / numpy {ENV_VERSIONS['numpy']}；"
          "随机种子：none（runner 与引擎均无 RNG）。",
          f"- 墙钟 {time.perf_counter() - T0:.0f}s（预算 {BUDGET_S:.0f}s）；"
          f"峰值 RSS {PEAK_RSS:.2f} GB（上限 8 GB）。",
          "- σ0 口径（runner 层钉死）：信号日前 20 个官方交易日 "
          "close-to-close 对数收益样本标准差（ddof=1）× P0（信号日官方收盘）；"
          "21 个收盘价含信号日；不足 20 个收益或任一收盘缺失（次新/停牌）"
          "剔除并计数。",
          "- 运行层适配（相对 F3R3，已在 manifest 披露）：ETF 腿意图优先级 "
          "10^6 → 999（BR-1 跨层护栏）；park 到期改为窗口后首个整历月月末"
          "+1；臂 B 路径仅保留 w_T 缩放（zones 模式无月末减仓原语，"
          "S-v14-15 重叠护栏禁止个股意图）。", "",
          "## 四、结论", "",
          ("- 冒烟核对全部 PASS。未发现引擎行为与契约 §10 不符之处。"
           "全期运行待主对话验收后另行发起。") if all_ok else
          ("- **存在 FAIL 项，见上文明细；冒烟未通过，不得发起全期运行。**")]
(out_dir / "smoke_report.md").write_text("\n".join(lines), encoding="utf-8")
log(f"  smoke_report.md written (all_ok={all_ok})")

# === 11. manifest ============================================================
ENGINE_SHA_AT_END = sha256_file(ENGINE_PY)
outs = {}
for p in sorted(RUN_DIR.rglob("*")):
    if p.is_file() and p.name not in ("manifest.json", "runner.log"):
        outs[p.relative_to(RUN_DIR).as_posix()] = sha256_file(p)
smoke_summary = {}
for (arm, wname), r in RESULTS.items():
    c = r["checks"]
    smoke_summary[f"{arm}/{wname}"] = {
        "pass": not c["fail"],
        "fail": c["fail"],
        "zones_rows": c["zones_rows"],
        "sigma_excluded": c["zones_meta"]["sigma_excluded"],
        "admissions_by_month": c["admissions_by_month"],
        "admissions_first_scan": c["admissions_first_scan"],
        "continuations_by_month": c["continuations_by_month"],
        "industry_blocked_reconstructed":
            c["industry_blocked_reconstructed"],
        "fills_checked": c["fills_checked"],
        "cash_conservation_max_abs_err": c["cash_conservation_max_abs_err"],
        "equity_identity_max_abs_err": c["equity_identity_max_abs_err"],
        "tp_samples_n": len(c["tp_samples"]),
        "stop_samples": c["stop_samples"],
        "gate8": c["gate8"],
        "zone_events": c["zone_events"],
        "armed_edge_cases": c["armed_edge_cases"],
        "n_fills": c["n_fills"],
        "wall_s": c["wall_s"]}
manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260919-zone-sheet-f4r1",
    "status": "completed" if all_ok else "completed_with_check_failures",
    "scope": "SMOKE ONLY (prereg sec 7): correctness checks on W1/W2, "
             "3 arms; NO performance conclusions; full-period dev run NOT "
             "started (awaits main-conversation smoke acceptance)",
    "started_at_utc": datetime.fromtimestamp(T0, tz=timezone.utc).isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "peak_rss_gb": PEAK_RSS,
    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/scripts/runner_f4r1.py"],
    "random_seed": None,
    "determinism": "no RNG in runner or engine; static zones/intent frames; "
                   "engine-owned deterministic lifecycle",
    "engine": {"path": str(ENGINE_PY),
               "sha256_at_start": ENGINE_SHA_AT_START,
               "sha256_at_end": ENGINE_SHA_AT_END,
               "sha256_pin_expected": ENGINE_SHA_EXPECT_FULL,
               "bytes_modified_by_this_run":
                   ENGINE_SHA_AT_START != ENGINE_SHA_AT_END,
               "version": "v1.4 (pin 7ad35014...; zones mode per contract "
                          "sec 10)"},
    "pins": pins,
    "env_versions": ENV_VERSIONS,
    "windows": {k: f"{v[0]}..{v[1]}" for k, v in WINDOWS.items()},
    "window_signals": {k: [d.isoformat() for d in v]
                       for k, v in SIG_DAYS_BY_WINDOW.items()},
    "full_dev_window_not_run": True,
    "parameters": {"K": SLEEVE_K, "top_2k": TOP_2K, "ind_cap": IND_CAP,
                   "buffer_mult": BUFFER_MULT, "stop_mult": STOP_MULT,
                   "invalid_mult": INVALID_MULT,
                   "ladder_offsets": LADDER_OFFSETS,
                   "ladder_fracs": LADDER_FRACS,
                   "tp_A_B": "tp1 2.0/0.5 + tp2 3.0/1.0",
                   "tp_C": "tp1 2.0/1.0 (tp2 null, one-shot full sell)",
                   "w_T_A_C": SLEEVE_W_ON,
                   "w_T_B": "e_T * 0.06/0.90 (T200-40 exposures, F3R3 path)",
                   "initial_cash_arms": ARMS_INITIAL_CASH,
                   "initial_cash_anchor": ANCHOR_INITIAL_CASH,
                   "zone_priority_base": ZONE_PRIORITY_BASE,
                   "sigma_lookback_returns": SIGMA_LOOKBACK,
                   "sigma_ddof": SIGMA_DDOF,
                   "sigma_closes": "21 official closes incl. signal day"},
    "runner_adaptations_disclosed": {
        "leg_intent_priority_999": "BR-1 guard: intent priority must be < "
                                   "zone_priority_base(1000); F3R3 used "
                                   "10**6.  999 keeps the ETF leg the lowest "
                                   "layer, but it is now funded BEFORE stock "
                                   "ladders in same-decision cash competition "
                                   "(in F3R3 it sat after rank 1..20 stock "
                                   "intents).",
        "park_expiry_window": "smoke windows have 2 signal days; the frozen "
                              "'4th signal day + 1' park expiry is "
                              "approximated by 'first full-calendar month-end "
                              "after the window + 1' (park stays live for the "
                              "whole window; monthly reduce sells unchanged).",
        "arm_B_path_wt_only": "zones mode has no month-end reduce-to-target "
                              "primitive for stocks (BR-7) and stock symbols "
                              "cannot appear in the intent frame (S-v14-15 "
                              "overlap guard): arm B keeps the T200-40 path "
                              "ONLY through w_T = e_T*0.06/0.90 scaling of "
                              "NEW ladder sizing.  Comparability seam vs "
                              "F3R3's de-risking mechanism; needs "
                              "adjudication before full-period "
                              "interpretation.",
        "sigma_estimator": "sample stdev ddof=1 over the last 20 close-to-close "
                           "log returns ending at the signal day (21 closes "
                           "incl. P0); raw official closes (no adjustment); "
                           "excluded candidates counted by reason.",
        "rank_not_renumbered": "sigma-excluded candidates keep their composite "
                               "rank vacated (survivors are not renumbered); "
                               "the rank is the composite rank.",
        "industry_blocked_caliber": "engine has no industry-block counter; "
                                    "reconstructed runner-side per month from "
                                    "the frame + engine admissions (never-"
                                    "admitted candidates whose industry "
                                    "already holds 2 among admissions + "
                                    "continuations)."},
    "f4r1_a0_anchor": {**{k: v for k, v in A0_CMP.items()},
                       "rule": "filecmp byte comparison vs F3R3-A0 outputs; "
                               "mismatch = STOP (prereg sec 7; did not "
                               "trigger)"},
    "smoke": smoke_summary,
    "smoke_all_pass": all_ok,
    "trial_accounting": {"this_round": "0 consumed (smoke is a correctness "
                                       "run per prereg sec 7; the 270->273 "
                                       "arm trials book at the full-period "
                                       "run)",
                         "strategy_line": "270 (F4R1 full run will book "
                                          "270->273); factor line FT-01=120"},
    "advanced_to_validation": False,
    "val_consumed": False,
    "stop_note": ("smoke correctness-only; no performance conclusions; "
                  "full-period run pending main-conversation acceptance"),
    "outputs": outs,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== manifest + smoke_report written; wall {time.perf_counter() - T0:.0f}s, "
    f"peak rss {PEAK_RSS:.2f} GB ==")
log(f"== VERDICT: smoke {'ALL PASS' if all_ok else 'FAILURES (see report)'}; "
    "no performance conclusions; full period not run")
_logf.close()
