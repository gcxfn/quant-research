# -*- coding: utf-8 -*-
"""Baseline-rebuild training (prereg exp-20260921-baseline-rebuild).

Reproduces the archived Alpha158 pipeline (20260921T125117 regression /
20260921T142710 head-binary) with the 2026-09-21 audit fixes, via the
shared library src/quant/research/alpha158_ml.py:

  C1  rolling window = the MOST RECENT 24 label-complete sections
      (archived: earliest 24 forever); per-month diagnostics emitted;
  C2  prediction universe = t-time features only (archived: keyed on
      the forward-return dict bounded by next month's pool); labels use
      the liquidation calibre (first own close at/after the next signal
      day); suspended/delisted names stay in the universe, label-missing
      counts disclosed;
  Q2  labels compounded through the close/preclose bridge (adj calibre);
      raw calibre computed for IC-level difference attribution only.

One feature build, two objectives (reg + bin). Outputs ml_scores for the
replay run + diagnostics + IC comparison. No strategy consumption here.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research import alpha158_ml as aml  # noqa: E402
from quant.research.alpha158 import alpha158_cross_section  # noqa: E402

DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
DEV_END = date(2020, 12, 31)
LABEL_MODE = "adj"          # prereg §2: adj is the rebuilt calibre
BUDGET_S = 1500.0

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
LOG = (RUN_DIR / "logs" / "runner.log")
LOG.parent.mkdir(parents=True, exist_ok=True)
_lf = LOG.open("a", encoding="utf-8")


def log(m):
    line = f"[{time.perf_counter()-T0:6.1f}s] {m}"
    _lf.write(line + "\n")
    _lf.flush()
    print(line, flush=True)


def _fail(reason):
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name,
        "experiment_id": "exp-20260921-baseline-rebuild",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    _lf.close()
    sys.exit(1)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# === 0. pins ================================================================
daily_sha = sha256_file(DAILY)
prereg = ROOT / "docs/research/exp-20260921-baseline-rebuild-prereg.md"
lib_sha = sha256_file(ROOT / "src/quant/research/alpha158_ml.py")
log(f"pins: daily {daily_sha[:16]}; alpha158_ml {lib_sha[:16]}; "
    f"prereg {sha256_file(prereg)[:16]}")

# === 1. calendar & pools (unchanged archived construction) =================
cal = r16.market_calendar(DAILY)
all_mes = r16.month_end_sessions(cal).filter(pl.col("s") <= DEV_END)
sig = [d for d in all_mes["s"].to_list() if d.year >= 2015]
log(f"{len(sig)} signal days {sig[0]}..{sig[-1]}")
hist = r16.build_history_r16(DAILY, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig}))
pools_at = r16.pools_by_signal(pool_frame)
pool_syms = sorted({s for t in sig for s in pools_at[t]["ranked"]})
log(f"pool union {len(pool_syms)} symbols")

panel = pl.read_parquet(DAILY, columns=["symbol", "date", "open", "high",
                                        "low", "close", "preclose",
                                        "volume", "amount"])
panel = (panel.filter(pl.col("symbol").is_in(pool_syms))
         .filter(pl.col("date") >= date(2014, 9, 1))
         .filter(pl.col("date") <= DEV_END).sort("symbol", "date"))
log(f"panel rows {panel.height}")


def dint_col(s):
    return (s.dt.year().cast(pl.Int64) * 10_000 + s.dt.month().cast(pl.Int64)
            * 100 + s.dt.day().cast(pl.Int64)).to_numpy()


series: dict[str, dict] = {}
for (sym,), g in panel.partition_by("symbol", as_dict=True).items():
    series[str(sym)] = {
        "dint": dint_col(g["date"]),
        "o": g["open"].to_numpy().astype(np.float64),
        "h": g["high"].to_numpy().astype(np.float64),
        "l": g["low"].to_numpy().astype(np.float64),
        "c": g["close"].to_numpy().astype(np.float64),
        "pc": g["preclose"].to_numpy().astype(np.float64),
        "v": g["volume"].to_numpy().astype(np.float64),
        "a": g["amount"].to_numpy().astype(np.float64),
    }
log(f"{len(series)} symbol series built")


def check_budget(what):
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


# === 2. features per (signal day, pooled symbol) — archived path ==========
FEATURES: dict[str, dict[str, dict]] = {t: {} for t in sig}
for si, t in enumerate(sig):
    key = t.year * 10_000 + t.month * 100 + t.day
    for sym in pools_at[t]["ranked"]:
        s = series.get(sym)
        if s is None:
            continue
        j = int(np.searchsorted(s["dint"], key, side="right"))
        if j < 62:
            continue
        lo = j - 62
        f = alpha158_cross_section(pl.DataFrame({
            "date": range(62), "open": s["o"][lo:j], "high": s["h"][lo:j],
            "low": s["l"][lo:j], "close": s["c"][lo:j],
            "volume": s["v"][lo:j], "amount": s["a"][lo:j]}))
        if f:
            FEATURES[t][sym] = f
    if si % 18 == 0 or si == len(sig) - 1:
        log(f"  features {t}: {len(FEATURES[t])} symbols")
        check_budget("features")
log("features done")

from quant.research.alpha158 import N_FEATURES  # noqa: E402
names = sorted(next(iter(FEATURES[sig[20]].values())).keys())
assert len(names) == N_FEATURES

# === 3. sections: C2 separation + adj labels ===============================
sections_adj = aml.build_ml_sections(
    FEATURES, series, sig, feature_names=names,
    label_mode="adj", min_section_names=100)
sections_raw = aml.build_ml_sections(
    FEATURES, series, sig, feature_names=names,
    label_mode="raw", min_section_names=100)
n_missing = sum(s.n_label_missing for s in sections_adj.values())
n_total = sum(len(s.syms) for s in sections_adj.values())
log(f"sections: {len(sections_adj)}; universe rows {n_total}; "
    f"label-missing rows {n_missing} ({n_missing/max(n_total,1)*100:.2f}%)")
check_budget("sections")

# C2 population check: prediction universe must equal t-time features
for t in sections_adj:
    assert sections_adj[t].syms == sorted(FEATURES[t]), t

# === 4. rolling fit/predict, two objectives =================================
results = {}
for obj in ("reg", "bin"):
    res = aml.rolling_fit_predict(
        sections_adj, objective=("regression" if obj == "reg" else "binary"),
        log=lambda m, _o=obj: log(f"  [{_o}] {m}"))
    ics = np.array([r["rank_ic"] for r in res.ic_series])
    mean_ic = float(ics.mean()) if len(ics) else float("nan")
    t_ic = (float(mean_ic / (ics.std() + 1e-12) * np.sqrt(len(ics)))
            if len(ics) else float("nan"))
    by_year = {}
    for r in res.ic_series:
        by_year.setdefault(r["t"][:4], []).append(r["rank_ic"])
    by_year = {y: float(np.mean(v)) for y, v in by_year.items()}
    results[obj] = {"res": res, "mean_ic": mean_ic, "t_ic": t_ic,
                    "by_year": by_year}
    log(f"[{obj}] models {len(res.diagnostics)}; IC mean {mean_ic:.4f} "
        f"t {t_ic:.2f}; by_year {by_year}")
    check_budget(f"fit-{obj}")

# raw-calibre IC difference attribution (reg objective only, Q2/H2)
res_raw = aml.rolling_fit_predict(sections_raw, objective="regression")
ics_raw = np.array([r["rank_ic"] for r in res_raw.ic_series])
log(f"[reg][raw] IC mean {ics_raw.mean():.4f} vs adj "
    f"{results['reg']['mean_ic']:.4f} "
    f"(diff {results['reg']['mean_ic'] - float(ics_raw.mean()):+.4f})")
check_budget("fit-raw")

# === 5. head metrics on the FIXED universe (report-only) ===================
def head_metrics(pred, sections):
    hits, hit_n, exc_rows = 0, 0, []
    for t, scores in pred.items():
        sec = sections.get(t)
        if sec is None:
            continue
        ok = sec.label_ok
        if ok.sum() < 30:
            continue
        top4 = sorted(scores, key=lambda s: -scores[s])[:4]
        lab = dict(zip(sec.syms, sec.y_cont))
        med = float(np.median([v for v in sec.y_cont[ok]]))
        picked = [s for s in top4 if s in lab and np.isfinite(lab[s])]
        if len(picked) < 4:
            continue
        hits += sum(1 for s in picked if lab[s] > med)
        hit_n += len(picked)
        top4_mean = float(np.mean([lab[s] for s in picked]))
        pool_mean = float(np.mean(sec.y_cont[ok]))
        exc_rows.append({"t": str(t), "top4": top4_mean, "pool": pool_mean,
                         "excess": top4_mean - pool_mean})
    hit_rate = hits / hit_n if hit_n else float("nan")
    exc_mean = float(np.mean([r["excess"] for r in exc_rows])) \
        if exc_rows else float("nan")
    exc_pos = float(np.mean([1.0 if r["excess"] > 0 else 0.0
                             for r in exc_rows])) if exc_rows else 0.0
    return {"top4_hit_rate_vs_median": hit_rate, "picks": hit_n,
            "months": len(exc_rows),
            "mean_monthly_excess_vs_pool": exc_mean,
            "positive_excess_months": exc_pos}, exc_rows


head_bin, exc_bin = head_metrics(results["bin"]["res"].pred, sections_adj)
log(f"[bin] head metrics: hit {head_bin['top4_hit_rate_vs_median']:.3f} "
    f"({head_bin['picks']} picks / {head_bin['months']} months); "
    f"excess {head_bin['mean_monthly_excess_vs_pool']*100:+.2f}pp "
    f"({head_bin['positive_excess_months']*100:.0f}% pos)")

# === 6. outputs =============================================================
out = RUN_DIR / "outputs"
out.mkdir(parents=True, exist_ok=True)
for obj in ("reg", "bin"):
    res = results[obj]["res"]
    with (out / f"ml_scores_{obj}.json").open("w", encoding="utf-8") as fh:
        json.dump({str(t): res.pred[t] for t in sorted(res.pred)}, fh)
    pl.DataFrame(res.ic_series).write_csv(out / f"ml_rank_ic_{obj}.csv")
    pl.DataFrame([d.as_dict() for d in res.diagnostics]).write_csv(
        out / f"train_window_diag_{obj}.csv")
pl.DataFrame(exc_bin).write_csv(out / "ml_head_excess_bin.csv")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-baseline-rebuild",
    "status": "completed",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "command": [sys.executable, f"artifacts/runs/{RUN_DIR.name}"
                f"/tmp/runner_train.py"],
    "fixes": {
        "C1": "rolling window = most recent 24 label-complete sections "
              "(alpha158_ml.select_train_sections)",
        "C2": "prediction universe = t-time features; liquidation-calibre "
              "labels; suspended/delisted stay in universe",
        "Q2_label": f"label_mode={LABEL_MODE} (close/preclose bridge); "
              "raw computed for IC attribution only"},
    "pins": {"daily_parquet": daily_sha, "alpha158_ml": lib_sha,
             "prereg": sha256_file(prereg),
             "python": sys.version.split()[0]},
    "sections": {"n_sections": len(sections_adj),
                 "universe_rows": n_total,
                 "label_missing_rows": n_missing},
    "reg": {"ic_mean": results["reg"]["mean_ic"],
            "ic_t": results["reg"]["t_ic"],
            "by_year": results["reg"]["by_year"]},
    "bin": {"ic_mean": results["bin"]["mean_ic"],
            "ic_t": results["bin"]["t_ic"],
            "by_year": results["bin"]["by_year"],
            "head_report_only": head_bin},
    "raw_ic_attribution": {"reg_ic_mean_raw": float(ics_raw.mean()),
                           "reg_ic_mean_adj": results["reg"]["mean_ic"]},
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(out.rglob("*")) if p.is_file()},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter()-T0:.0f}s ==")
_lf.close()
