# -*- coding: utf-8 -*-
"""exp-20260920-factor-attribution -- stage A.

FA-S2 z-source verification + factor contribution attribution (prereg
docs/research/exp-20260920-factor-attribution-prereg.md sec 3) + sanity
(sec 8) + mechanical suspect screening (sec 5.1).

Frozen calibers (prereg verbatim, no local reinterpretation):
- z_i,s,t = the F3R1 composite component: (rank_pct - 0.5) * sign(ic_mean_i),
  ranked within eligible[t] = R16 pool INTERSECTION (>= ceil(17/2) reps
  non-null); code path copied verbatim from the F3R1 runner sec 4
  (artifacts/runs/20260919T191524-f3r1-factor-combo-c212/tmp/runner_f3r1.py).
  FA-S2: the rebuilt F3-EW composite must match
  F3R1 outputs/F3-EW_composite.parquet on 3 sampled signal dates x sampled
  symbols within 1e-9, else STOP.
- r_s,t+1 = F2R1 eval harness forward return: compound of close/preclose - 1
  over the 20 trading days AFTER signal_date, from
  data/processed/baostock-daily-20260917/daily_2015_2024.parquet (the exact
  panel the F2R1 factor builds passed to evaluate_factor) truncated at
  2020-12-31 BEFORE the harness sees it.  Truncation only removes trailing
  rows: hist_depth and every sleeve-month forward value are identical to the
  F2R1 run, and 2021+ is never touched.  Harness internals
  (quant.factors.eval._prepare_panel/_forward_return_grid) reused verbatim.
- w_s,t = per-seat w_T from the F3R3 chassis sleeve_monthly_log.json
  (w_T = e_T * (0.06/0.90) expanded to each seated name; cash seats = 0)
  -- FA-S4, no equal-weight surrogate.
- atoms a_i,s,t = z_i,s,t * r_s,t+1 over seated members with BOTH present;
  missing atoms are dropped (documented harness truncation), never filled.

FA-S3 approximation declaration (prereg sec 3, verbatim):
  "排名选股非线性，故 Σ_i weight_i × c_i,t 不等于组合月收益；归因表只用于
   因子间横向对比与符号判定，禁止解读为绝对收益归因。留一为金标准，归因只
   圈嫌疑人。"

Deterministic; no RNG.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import date
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from quant.factors.eval import (  # noqa: E402
    FactorEvalConfig, _forward_return_grid, _prepare_panel, _validate_panel)
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

CHASSIS_RUN = ROOT / "artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e"
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F2R1_RUN = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
PREREG_MD = ROOT / "docs/research/exp-20260920-factor-attribution-prereg.md"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
DAILY_CAL = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
DAILY_EVAL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
ENGINE_SHA_EXPECT = "a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1f0a466b0675abf3"
# F2R1 frozen eval config (build_*_main.py CFG verbatim)
EVAL_CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M",
                            min_history_rows=60)
YEARS = [2015, 2016, 2017, 2018, 2019, 2020]

T0 = time.perf_counter()
PEAK_RSS = 0.0
STAGES: dict[str, float] = {}


def log(msg: object) -> None:
    global PEAK_RSS
    try:
        import psutil
        PEAK_RSS = max(PEAK_RSS, psutil.Process().memory_info().rss / 1e9)
    except Exception:
        pass
    print(f"[{time.perf_counter() - T0:7.1f}s] {msg}", flush=True)


def stage(name: str) -> None:
    STAGES[name] = time.perf_counter() - T0
    log(f"== stage done: {name} ({STAGES[name]:.1f}s) ==")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stop(reason: str) -> None:
    """STOP discipline (prereg sec 7/8): write stop report + summary, exit 2."""
    log(f"!! STOP: {reason}")
    (RUN_DIR / "tmp" / "stop_report.md").write_text(
        "# STOP REPORT -- exp-20260920-factor-attribution (stage A)\n\n"
        f"- stopped_at_stage: attribution stage A\n"
        f"- reason: {reason}\n"
        f"- elapsed_s: {time.perf_counter() - T0:.1f}\n"
        "- completed_artifacts_before_stop: see outputs/ and "
        "tmp/attribution_summary.json (written only if the failure point "
        "allowed them)\n",
        encoding="utf-8")
    summary["status"] = "aborted"
    summary["stop_reason"] = reason
    (RUN_DIR / "tmp" / "attribution_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")
    sys.exit(2)


summary: dict = {"experiment_id": "exp-20260920-factor-attribution",
                 "stage": "A_attribution", "status": "running",
                 "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "stages_s": STAGES}

# === 0. identity pins ========================================================
log("== 0. identity pins ==")
pins: dict = {}
ENGINE_GOT = sha256_file(ENGINE_PY)
pins["engine"] = {"path": str(ENGINE_PY), "sha256": ENGINE_GOT,
                  "expected": ENGINE_SHA_EXPECT,
                  "match": ENGINE_GOT == ENGINE_SHA_EXPECT}
if not pins["engine"]["match"]:
    stop(f"engine pin mismatch: {ENGINE_GOT}")
for name, p in [("prereg", PREREG_MD),
                ("daily_calendar_pools", DAILY_CAL),
                ("daily_eval_panel", DAILY_EVAL),
                ("sleeve_monthly_log", CHASSIS_RUN / "outputs/sleeve_monthly_log.json"),
                ("chassis_metrics_and_gates", CHASSIS_RUN / "outputs/metrics_and_gates.json"),
                ("f3r1_ew_composite", F3R1_RUN / "outputs/F3-EW_composite.parquet"),
                ("dedup_clusters", F3R1_RUN / "outputs/dedup_clusters.csv"),
                ("f2r1_all120", F2R1_RUN / "outputs/f2r1_all120.csv")]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
    log(f"  {name}: {pins[name]['sha256'][:16]}")

dedup = pl.read_csv(F3R1_RUN / "outputs/dedup_clusters.csv")
REPS = sorted(dedup["representative"].to_list())
assert len(REPS) == 17, f"expected 17 representatives, got {len(REPS)}: {REPS}"
M = len(REPS)
MIN_COV = -(-M // 2)  # ceil(M/2), F3R1 verbatim
log(f"  17 representatives: {REPS}; coverage rule >= {MIN_COV}/{M} non-null")
for fid in REPS:
    p = F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]] / f"{fid}.parquet"
    pins[f"rep_{fid}"] = {"path": str(p), "sha256": sha256_file(p)}
summary["pins"] = pins
summary["env"] = {"python": platform.python_version(),
                  "polars": pl.__version__, "numpy": np.__version__,
                  "platform": platform.platform()}

# === 1. calendar & signal days (F3R1/F3R3 runner verbatim) ===================
log("== 1. calendar & signal days ==")
cal = r16.market_calendar(DAILY_CAL)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
SIG_DAYS = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
assert SIG_DAYS and SIG_DAYS[-1] <= date(2020, 11, 30)
log(f"  {len(SIG_DAYS)} signal days {SIG_DAYS[0]}..{SIG_DAYS[-1]}")
summary["sig_days"] = f"{SIG_DAYS[0]}..{SIG_DAYS[-1]} ({len(SIG_DAYS)})"
stage("calendar")

# === 2. R16 pool (verbatim) ==================================================
log("== 2. R16 pool (build_history + signal_pools, verbatim) ==")
hist = r16.build_history_r16(DAILY_CAL, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": SIG_DAYS}))
pools_at = r16.pools_by_signal(pool_frame)
pool_set = {t: set(pools_at[t]["ranked"]) for t in SIG_DAYS}
del hist
log(f"  pool n: min {min(len(v) for v in pool_set.values())} "
    f"max {max(len(v) for v in pool_set.values())}")
stage("pools")

# === 3. FA-S2: rebuild composite from F2R1 score parquets ====================
log("== 3. FA-S2 rebuild composite (F3R1 sec 4 code verbatim, 17 reps) ==")
all120 = pl.read_csv(F2R1_RUN / "outputs/f2r1_all120.csv")
stats = {r["factor_id"]: r for r in all120.iter_rows(named=True)}
signs = {fid: (1.0 if float(stats[fid]["ic_mean"]) > 0 else -1.0)
         for fid in REPS}
# F3R1 cross-check: all120 t_ic vs family JSON t_ic (all120 rounds to 2dp)
for fid in REPS:
    jp = F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]] / f"{fid}.json"
    j = json.loads(jp.read_text(encoding="utf-8"))
    # F3R1 verbatim guard: all120 rounds t_ic to 2dp -> half-step tolerance;
    # family JSONs without a screen block skip the cross-check (F3R1 did too)
    t_json = (j.get("screen") or {}).get("t_ic")
    if t_json is not None and abs(t_json - float(stats[fid]["t_ic"])) > 5.001e-3:
        stop(f"{fid}: t_ic mismatch json {t_json} vs all120 {stats[fid]['t_ic']}")
    pins[f"rep_{fid}"]["ic_mean"] = float(stats[fid]["ic_mean"])
    pins[f"rep_{fid}"]["sign"] = signs[fid]

wide = None
for fid in REPS:
    f = (pl.read_parquet(F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]]
                         / f"{fid}.parquet")
         .filter(pl.col("signal_date").is_in(pl.Series(SIG_DAYS)))
         .rename({"value": fid}))
    wide = f if wide is None else wide.join(f, on=["symbol", "signal_date"],
                                            how="full", coalesce=True)
wide = wide.filter(pl.col("signal_date").is_in(pl.Series(SIG_DAYS)))
log(f"  wide frame {wide.height} rows, {wide['symbol'].n_unique()} symbols")

eligible: dict[date, list[str]] = {}
comp_ew: dict[date, dict[str, float]] = {}     # rebuilt F3-EW composite
comp_parts: dict[date, dict[str, dict[str, float]]] = {}  # per-factor z
for t in SIG_DAYS:
    g = wide.filter(pl.col("signal_date") == t)
    have = g.with_columns(
        sum(pl.col(f).is_not_null().cast(pl.Int8) for f in REPS).alias("_n"))
    have = (have.filter(pl.col("symbol").is_in(pl.Series(sorted(pool_set[t]))))
            .filter(pl.col("_n") >= MIN_COV))
    elig = sorted(have["symbol"].to_list())
    eligible[t] = elig
    with_parts = have
    for fid in REPS:
        with_parts = with_parts.with_columns(
            ((pl.col(fid).rank(method="average") - 1.0)
             / pl.max_horizontal(pl.col(fid).count() - 1.0, 1))
            .alias(f"_p_{fid}"))
    rows = with_parts.select(["symbol"] + [f"_p_{f}" for f in REPS]) \
        .iter_rows(named=True)
    parts_t: dict[str, dict[str, float]] = {}
    ew_t: dict[str, float] = {}
    for r in rows:
        sym = r["symbol"]
        zs: dict[str, float] = {}
        for fid in REPS:
            p = r[f"_p_{fid}"]
            if p is not None:
                zs[fid] = (p - 0.5) * signs[fid]
        parts_t[sym] = zs
        if zs:
            ew_t[sym] = sum(zs.values()) / len(zs)
    comp_parts[t] = parts_t
    comp_ew[t] = ew_t
log(f"  eligible sizes: min {min(len(v) for v in eligible.values())} "
    f"median {int(np.median([len(v) for v in eligible.values()]))} "
    f"max {max(len(v) for v in eligible.values())}")
stage("composite_rebuild")

# --- FA-S2 gate: rebuilt vs F3R1 parquet -------------------------------------
log("== 3b. FA-S2 gate: rebuilt EW composite vs F3-EW_composite.parquet ==")
ref = pl.read_parquet(F3R1_RUN / "outputs/F3-EW_composite.parquet")
ref_map: dict[tuple[date, str], float] = {
    (r["signal_date"], r["symbol"]): float(r["value"])
    for r in ref.iter_rows(named=True)}
rebuilt_map: dict[tuple[date, str], float] = {
    (t, s): v for t in SIG_DAYS for s, v in comp_ew[t].items()}
keys_ref = set(ref_map)
keys_re = set(rebuilt_map)
if keys_ref != keys_re:
    only_ref = sorted(keys_ref - keys_re)[:5]
    only_re = sorted(keys_re - keys_ref)[:5]
    log(f"  KEY MISMATCH: ref-only {len(keys_ref - keys_re)} {only_ref}; "
        f"rebuilt-only {len(keys_re - keys_ref)} {only_re}")
# sampled check (prereg): 3 signal dates x sampled symbols, tol 1e-9
sample_dates = [SIG_DAYS[0], SIG_DAYS[len(SIG_DAYS) // 2], SIG_DAYS[-1]]
sample_rows = []
for t in sample_dates:
    syms_ref = sorted(s for (tt, s) in keys_ref if tt == t)
    step = max(1, len(syms_ref) // 25)
    for s in syms_ref[::step][:25]:
        if (t, s) in rebuilt_map:
            sample_rows.append({"signal_date": str(t), "symbol": s,
                                "rebuilt": rebuilt_map[(t, s)],
                                "reference": ref_map[(t, s)],
                                "abs_diff": abs(rebuilt_map[(t, s)]
                                                - ref_map[(t, s)])})
n_checked = len(sample_rows)
max_diff_sample = max((r["abs_diff"] for r in sample_rows), default=1e9)
fa_s2_pass = (n_checked >= 30 and max_diff_sample <= 1e-9
              and keys_ref == keys_re)
global_max = max((abs(rebuilt_map[k] - ref_map[k])
                  for k in keys_ref & keys_re), default=float("inf"))
log(f"  FA-S2: sampled {n_checked} points on {sample_dates}, "
    f"max|diff| {max_diff_sample:.3e} (global max {global_max:.3e}); "
    f"key sets equal: {keys_ref == keys_re} -> PASS={fa_s2_pass}")
summary["fa_s2"] = {"pass": fa_s2_pass, "n_sampled": n_checked,
                    "sample_dates": [str(t) for t in sample_dates],
                    "max_abs_diff_sampled": max_diff_sample,
                    "max_abs_diff_global": global_max,
                    "key_sets_equal": keys_ref == keys_re,
                    "tolerance": 1e-9}
summary["fa_s2_sample"] = sample_rows[:10]
if not fa_s2_pass:
    if keys_ref != keys_re:
        stop(f"FA-S2 key-set mismatch: ref-only {len(keys_ref - keys_re)} "
             f"(e.g. {sorted(keys_ref - keys_re)[:3]}), rebuilt-only "
             f"{len(keys_re - keys_ref)} (e.g. {sorted(keys_re - keys_ref)[:3]})")
    bad = [r for r in sample_rows if r["abs_diff"] > 1e-9][:5]
    stop(f"FA-S2 value mismatch beyond 1e-9 on sampled points; worst "
         f"{max_diff_sample:.3e}; examples {json.dumps(bad)}")
stage("fa_s2_gate")

# === 4. forward returns r (F2R1 eval harness verbatim) =======================
log("== 4. r: F2R1 eval harness, h=20, panel truncated <= 2020-12-31 ==")
panel_all = pl.read_parquet(DAILY_EVAL)
# freeze discipline: truncate BEFORE the harness; trailing-row removal does
# not change hist_depth or any sleeve-month forward value (see module doc)
panel_eval = panel_all.filter(pl.col("date") <= DEV_END)
del panel_all
_validate_panel(panel_eval)
ready = _prepare_panel(panel_eval, EVAL_CFG)
fwd = _forward_return_grid(ready, EVAL_CFG.horizon_days)
del ready, panel_eval
fwd_sig = fwd.filter(pl.col("date").is_in(pl.Series(SIG_DAYS)))
R_MAP: dict[tuple[date, str], float] = {
    (r["date"], r["symbol"]): float(r["fwd_ret"])
    for r in fwd_sig.iter_rows(named=True)}
months_with_r = sorted({t for (t, _s) in R_MAP})
log(f"  fwd grid: {fwd.height} rows; sleeve-month coverage "
    f"{len(months_with_r)}/{len(SIG_DAYS)} months "
    f"({months_with_r[0]}..{months_with_r[-1]}); "
    f"first r month {months_with_r[0]} (F2R1 harness truncation: "
    "min_history_rows=60 drops 2015 Q1 signals)")
summary["r_months"] = {"n": len(months_with_r),
                       "first": str(months_with_r[0]),
                       "last": str(months_with_r[-1]),
                       "horizon_days": EVAL_CFG.horizon_days,
                       "panel": str(DAILY_EVAL),
                       "panel_sha256": pins["daily_eval_panel"]["sha256"],
                       "panel_truncated_le": str(DEV_END)}
stage("forward_returns")

# === 5. atoms & monthly contributions per arm ================================
log("== 5. monthly contributions c_i,t (sleeve log seats, FA-S4 weights) ==")
sleeve_log = json.loads((CHASSIS_RUN / "outputs/sleeve_monthly_log.json")
                        .read_text(encoding="utf-8"))


def arm_contributions(arm: str) -> tuple[dict[str, dict[date, float]],
                                         dict[date, dict[str, float]],
                                         dict]:
    """c_i,t = sum_s w_s,t * z_i,s,t * r_s,t+1 over seated members.

    Returns (contrib[i][t], realized[t] = sum_s w_T*r over seated members
    with r, diagnostics)."""
    contrib: dict[str, dict[date, float]] = {fid: {} for fid in REPS}
    realized: dict[date, float] = {}
    diag = {"months_no_r": [], "atoms_total": 0, "atoms_dropped_no_r": 0,
            "atoms_dropped_no_z": 0}
    for entry in sleeve_log[arm]:
        t = date.fromisoformat(entry["month"])
        w_t = float(entry["w_T"])
        rsum, rnames = 0.0, 0
        for s in entry["members"]:
            r = R_MAP.get((t, s))
            zs = comp_parts.get(t, {}).get(s)
            if r is None:
                diag["atoms_dropped_no_r"] += 1
                continue
            rsum += w_t * r
            rnames += 1
            if zs is None:
                diag["atoms_dropped_no_z"] += 1
                continue
            diag["atoms_total"] += 1
            for fid, z in zs.items():
                contrib[fid][t] = contrib[fid].get(t, 0.0) + w_t * z * r
        realized[t] = rsum if rnames > 0 else None
        if rnames == 0:
            diag["months_no_r"].append(str(t))
    return contrib, realized, diag


def contrib_stats(contrib: dict[str, dict[date, float]]) -> list[dict]:
    out = []
    for fid in REPS:
        series = contrib[fid]
        months = sorted(series)
        vals = np.array([series[t] for t in months], dtype=float)
        n = len(vals)
        mean = float(vals.mean()) if n else float("nan")
        if n > 1:
            se = float(vals.std(ddof=1) / np.sqrt(n))
            tstat = mean / se if se > 0 else float("nan")
        else:
            tstat = float("nan")
        yr = {y: float(sum(v for t, v in series.items() if t.year == y))
              for y in YEARS}
        n_pos = sum(1 for v in yr.values() if v > 0)
        n_neg = sum(1 for v in yr.values() if v < 0)
        out.append({"factor": fid,
                    "cum_contribution": float(vals.sum()) if n else float("nan"),
                    "mean_monthly": mean, "t_stat": tstat, "n_months": n,
                    "by_year": yr, "n_pos_years": n_pos,
                    "n_neg_years": n_neg})
    return out


RESULTS: dict[str, dict] = {}
for arm in ("EW", "ICW"):
    log(f"  arm {arm}: building atoms")
    contrib, realized, diag = arm_contributions(arm)
    stats_arm = contrib_stats(contrib)
    # sanity (prereg sec 8): lin_t = sum_i (1/M)*c_i,t vs realized_t
    lin: dict[date, float] = {}
    for t in sorted(realized):
        if realized[t] is None:
            continue
        if all((t in contrib[fid]) for fid in REPS):
            lin[t] = sum((contrib[fid][t] for fid in REPS), 0.0) / M
    common = sorted(set(lin) & {t for t in realized if realized[t] is not None})
    xs = np.array([lin[t] for t in common])
    ys = np.array([realized[t] for t in common])
    corr = float(np.corrcoef(xs, ys)[0, 1]) if len(common) > 1 else float("nan")
    agree = float(np.mean(np.sign(xs) == np.sign(ys))) if len(common) else float("nan")
    log(f"  arm {arm}: sanity months {len(common)}, corr {corr:.4f}, "
        f"sign agreement {agree * 100:.1f}% (gates: >=0.8 / >=70%)")
    RESULTS[arm] = {"contrib": contrib, "realized": realized,
                    "stats": stats_arm, "diag": diag,
                    "sanity": {"months": len(common), "corr": corr,
                               "sign_agreement": agree}}
    cols = ["factor", "cum_contribution", "mean_monthly", "t_stat",
            "n_months"] + [f"contrib_{y}" for y in YEARS] + \
        ["n_pos_years", "n_neg_years"]
    out_df = pl.DataFrame([{
        "factor": r["factor"], "cum_contribution": r["cum_contribution"],
        "mean_monthly": r["mean_monthly"], "t_stat": r["t_stat"],
        "n_months": r["n_months"],
        **{f"contrib_{y}": r["by_year"][y] for y in YEARS},
        "n_pos_years": r["n_pos_years"], "n_neg_years": r["n_neg_years"]}
        for r in stats_arm]).select(cols)
    out_df.write_csv(RUN_DIR / "outputs" / f"attribution_{arm.lower()}.csv")
    RESULTS[arm]["sanity_series"] = {
        str(t): {"linear": lin[t], "realized": realized[t]} for t in common}

# sanity gate on the EW main table only (prereg sec 3: judgments act on EW)
san_ew = RESULTS["EW"]["sanity"]
summary["sanity"] = {arm: {"months": RESULTS[arm]["sanity"]["months"],
                           "corr": RESULTS[arm]["sanity"]["corr"],
                           "sign_agreement": RESULTS[arm]["sanity"]["sign_agreement"],
                           "gated": arm == "EW"} for arm in RESULTS}
if not (san_ew["corr"] >= 0.8 and san_ew["sign_agreement"] >= 0.70):
    stop(f"sanity FAILED on EW: corr {san_ew['corr']:.4f} (<0.8?) "
         f"sign agreement {san_ew['sign_agreement'] * 100:.1f}% (<70%?) "
         "-- approximation-suspect, prereg sec 8 stop rule")
stage("attribution_tables")

# === 6. contribution correlation matrix (17x17, pairwise-complete) ===========
log("== 6. contribution correlation matrix (EW) ==")
series = {fid: RESULTS["EW"]["contrib"][fid] for fid in REPS}


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / n
    vx = sum((a - mx) ** 2 for a in xs) / n
    vy = sum((b - my) ** 2 for b in ys) / n
    den = (vx * vy) ** 0.5
    return cov / den if den > 0 else float("nan")


corr_rows = []
for i, fi in enumerate(REPS):
    row = {"factor": fi}
    for fj in REPS:
        common_t = sorted(set(series[fi]) & set(series[fj]))
        row[fj] = pearson([series[fi][t] for t in common_t],
                          [series[fj][t] for t in common_t])
    corr_rows.append(row)
pl.DataFrame(corr_rows).write_csv(RUN_DIR / "outputs" / "contribution_corr.csv")
stage("contribution_corr")

# === 7. suspect screening (prereg sec 5.1, mechanical, EW main table) ========
log("== 7. suspect rule: t < 0 AND n_neg_years >= 4 (EW main table) ==")
suspects = []
for r in RESULTS["EW"]["stats"]:
    if r["t_stat"] < 0 and r["n_neg_years"] >= 4:
        suspects.append(r)
        log(f"  SUSPECT {r['factor']}: t {r['t_stat']:.3f}, "
            f"neg years {r['n_neg_years']}/6")
if not suspects:
    log("  suspect list EMPTY (H1 falsification path, legal outcome)")
(RUN_DIR / "outputs" / "suspects.json").write_text(json.dumps({
    "rule": "prereg sec 5.1: monthly contribution t < 0 AND negative-year "
            "count >= 4 (of 2015..2020), EW main table only, mechanical",
    "arm": "EW",
    "n_suspects": len(suspects),
    "suspects": suspects,
    "all_factors_stats": RESULTS["EW"]["stats"],
}, ensure_ascii=False, indent=1), encoding="utf-8")
summary["suspects"] = [r["factor"] for r in suspects]
stage("suspects")

# === 8. summary ===============================================================
summary["status"] = "completed"
summary["wall_seconds"] = time.perf_counter() - T0
summary["peak_rss_gb"] = PEAK_RSS
summary["stages_s"] = dict(STAGES)
summary["outputs"] = {
    name: sha256_file(RUN_DIR / "outputs" / name) for name in
    ("attribution_ew.csv", "attribution_icw.csv", "contribution_corr.csv",
     "suspects.json")}
summary["arm_diagnostics"] = {arm: {
    "atoms_total": RESULTS[arm]["diag"]["atoms_total"],
    "atoms_dropped_no_z": RESULTS[arm]["diag"]["atoms_dropped_no_z"],
    "months_no_r": RESULTS[arm]["diag"]["months_no_r"]} for arm in RESULTS}
(RUN_DIR / "tmp" / "attribution_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== stage A complete: suspects={summary['suspects']}, "
    f"wall {summary['wall_seconds']:.0f}s, rss {PEAK_RSS:.2f} GB ==")
