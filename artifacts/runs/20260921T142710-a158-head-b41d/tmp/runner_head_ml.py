# -*- coding: utf-8 -*-
"""Alpha158 HEAD-optimised ML (prereg exp-20260921-a158-head-ml).

Identical to runner_alpha158.py (20260921T125117) EXCEPT the four frozen
changes in the prereg:
1. label: per-month cross-section y = 1 if FWD >= 80th percentile else 0
   (training only; continuous FWD kept for Rank-IC diagnostics);
2. LightGBM objective 'binary', LGBMClassifier;
3. ml_scores.json holds predict_proba[:,1];
4. new report-only metrics: top4 hit rate vs cross-section median and
   top4 mean monthly return minus pool equal-weight.
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
import lightgbm as lgb  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.alpha158 import alpha158_cross_section  # noqa: E402

DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
DEV_END = date(2020, 12, 31)

T0 = time.perf_counter()
LOG = (RUN_DIR / "logs" / "runner.log").open("a", encoding="utf-8")


def log(m):
    line = f"[{time.perf_counter()-T0:6.1f}s] {m}"
    LOG.write(line + "\n")
    LOG.flush()
    print(line, flush=True)


# --- calendar & pool -------------------------------------------------------
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
                                        "low", "close", "volume", "amount"])
panel = (panel.filter(pl.col("symbol").is_in(pool_syms))
         .filter(pl.col("date") >= date(2014, 9, 1))
         .filter(pl.col("date") <= DEV_END).sort("symbol", "date"))
log(f"panel rows {panel.height}; building per-symbol series")


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
        "v": g["volume"].to_numpy().astype(np.float64),
        "a": g["amount"].to_numpy().astype(np.float64),
    }
log(f"{len(series)} symbol series built")

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
log("features done")

# --- forward returns (unchanged) -------------------------------------------
CLOSE_AT: dict[str, dict[str, float]] = {}
for t in sig:
    key = t.year * 10_000 + t.month * 100 + t.day
    d = {}
    for sym in FEATURES[t]:
        s = series[sym]
        j = int(np.searchsorted(s["dint"], key, side="right")) - 1
        if j >= 0:
            d[sym] = float(s["c"][j])
    CLOSE_AT[t] = d
FWD: dict[str, dict[str, float]] = {}
for i, t in enumerate(sig[:-1]):
    t1 = sig[i + 1]
    FWD[t] = {sym: CLOSE_AT[t1][sym] / px - 1.0
              for sym, px in CLOSE_AT[t].items() if sym in CLOSE_AT[t1]}


def spearman(x, y):
    if len(x) < 10:
        return None
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else None


from quant.research.alpha158 import N_FEATURES  # noqa: E402
names = sorted(next(iter(FEATURES[sig[20]].values())).keys())
assert len(names) == 158

# --- step 1 (unchanged full-set evaluation) ---------------------------------
rows_eval = []
for fi, name in enumerate(names):
    ics = []
    mono_n = 0
    mono_tot = 0
    for t in sig[:-1]:
        syms = [s for s in FEATURES[t] if s in FWD.get(t, {})
                and FEATURES[t][s].get(name) is not None]
        if len(syms) < 30:
            continue
        x = np.array([FEATURES[t][s][name] for s in syms])
        y = np.array([FWD[t][s] for s in syms])
        ic = spearman(x, y)
        if ic is not None:
            ics.append(ic)
        med = np.median(x)
        top = y[x > med].mean() if (x > med).sum() > 5 else None
        bot = y[x <= med].mean() if (x <= med).sum() > 5 else None
        if top is not None and bot is not None:
            mono_tot += 1
            if abs(top - bot) > 0:
                mono_n += (np.sign(top - bot) == np.sign(np.mean(ics or [1])))
    if len(ics) >= 12:
        arr = np.array(ics)
        t_ic = arr.mean() / (arr.std() + 1e-12) * np.sqrt(len(arr))
        rows_eval.append({"feature": name, "ic_mean": float(arr.mean()),
                          "t_ic": float(t_ic),
                          "mono": mono_n / max(mono_tot, 1),
                          "n_months": len(ics)})
    else:
        rows_eval.append({"feature": name, "ic_mean": None, "t_ic": None,
                          "mono": None, "n_months": len(ics)})
ev = pl.DataFrame(rows_eval).sort("t_ic", descending=True, nulls_last=True)
ev.write_csv(RUN_DIR / "outputs" / "alpha158_eval.csv")
ok = ev.filter(pl.col("t_ic").is_not_null())
strong = ok.filter(pl.col("t_ic").abs() >= 2)
log(f"step1: {ok.height} features evaluated; |t|>=2: {strong.height}")

# --- step 2: binary head-labelled LightGBM ----------------------------------
X: dict[str, dict] = {}
for t in sig[:-1]:
    if t not in FWD or not FWD[t]:
        continue
    syms = sorted(FWD[t])
    mat = []
    keep = []
    for s_ in syms:
        f = FEATURES[t].get(s_)
        if f is None:
            continue
        vec = [f[n] if f.get(n) is not None else 0.0 for n in names]
        mat.append(vec)
        keep.append(s_)
    if len(keep) < 100:
        continue
    m = np.array(mat)
    for k_ in range(m.shape[1]):
        col = m[:, k_]
        order = np.argsort(np.argsort(col))
        m[:, k_] = order / max(len(col) - 1, 1)
    y_cont = np.array([FWD[t][s_] for s_ in keep])
    # CHANGE 1: per-month top-20% binary label
    thr = np.quantile(y_cont, 0.80)
    y_bin = (y_cont >= thr).astype(np.int32)
    X[t] = {"syms": np.array(keep), "x": m, "y": y_cont, "y_bin": y_bin}
ordered = sorted(X)
log(f"step2: {len(ordered)} monthly sections "
    f"({ordered[0]}..{ordered[-1]}), dim {len(names)}")

# CHANGE 2: binary objective + classifier
PARAMS = dict(objective="binary", n_estimators=300, learning_rate=0.05,
              num_leaves=31, min_child_samples=100, feature_fraction=0.8,
              random_state=7, verbose=-1)
ic_series = []
importances = np.zeros(len(names))
n_models = 0
PRED: dict[str, dict[str, float]] = {}
for i in range(1, len(ordered)):
    t = ordered[i]                     # predict month t
    train_ts = [u for u in ordered[:i] if u < t][:24]  # y known <= t-1
    train_ts = [u for u in train_ts if ordered.index(u) < i]
    if len(train_ts) < 12:
        continue
    xt = np.vstack([X[u]["x"] for u in train_ts])
    yt = np.concatenate([X[u]["y_bin"] for u in train_ts])
    model = lgb.LGBMClassifier(**PARAMS)
    model.fit(xt, yt)
    # CHANGE 3: probability output
    proba = model.predict_proba(X[t]["x"])[:, 1]
    importances += model.feature_importances_
    n_models += 1
    ic = spearman(proba, X[t]["y"])
    if ic is not None:
        ic_series.append({"t": str(t), "rank_ic": ic})
    PRED[t] = {str(s_): float(p) for s_, p in zip(X[t]["syms"], proba)}
    if n_models % 12 == 0:
        log(f"  {n_models} models; last IC {ic:.4f}")
ics = np.array([r["rank_ic"] for r in ic_series])
mean_ic = float(ics.mean()) if len(ics) else float("nan")
t_ic_ml = float(mean_ic / (ics.std() + 1e-12) * np.sqrt(len(ics))) \
    if len(ics) else float("nan")
by_year = {}
for r in ic_series:
    by_year.setdefault(r["t"][:4], []).append(r["rank_ic"])
by_year = {y: float(np.mean(v)) for y, v in by_year.items()}
top_idx = np.argsort(importances)[::-1][:10]
top_feats = {names[i]: float(importances[i]) for i in top_idx}
log(f"step2: {n_models} models, {len(ics)} IC months; "
    f"rank_ic mean {mean_ic:.4f} t {t_ic_ml:.2f}; by_year {by_year}")

# CHANGE 4: report-only head metrics (top4 by probability)
hits, hit_n = 0, 0
excess_rows = []
for t, scores in PRED.items():
    if t not in FWD:
        continue
    top4 = sorted(scores, key=lambda s: -scores[s])[:4]
    fwd_t = FWD[t]
    top4 = [s for s in top4 if s in fwd_t]
    if len(top4) < 4:
        continue
    med = np.median([fwd_t[s] for s in fwd_t])
    hits += sum(1 for s in top4 if fwd_t[s] > med)
    hit_n += len(top4)
    top4_mean = float(np.mean([fwd_t[s] for s in top4]))
    pool_mean = float(np.mean([fwd_t[s] for s in fwd_t]))
    excess_rows.append({"t": t, "top4": top4_mean, "pool": pool_mean,
                        "excess": top4_mean - pool_mean})
hit_rate = hits / hit_n if hit_n else float("nan")
exc_mean = float(np.mean([r["excess"] for r in excess_rows])) \
    if excess_rows else float("nan")
exc_pos = float(np.mean([1.0 if r["excess"] > 0 else 0.0
                         for r in excess_rows])) if excess_rows else 0.0
log(f"head metrics: top4 hit-rate vs median {hit_rate:.3f} "
    f"({hit_n} picks over {len(excess_rows)} months); "
    f"mean monthly excess vs pool {exc_mean*100:+.2f}pp "
    f"(positive months {exc_pos*100:.0f}%)")

pl.DataFrame(ic_series).write_csv(RUN_DIR / "outputs" / "ml_rank_ic.csv")
pl.DataFrame(excess_rows).write_csv(RUN_DIR / "outputs" / "ml_head_excess.csv")
pl.DataFrame({"feature": names, "importance": importances}).sort(
    "importance", descending=True).write_csv(
    RUN_DIR / "outputs" / "ml_feature_importance.csv")
with (RUN_DIR / "outputs" / "ml_scores.json").open("w", encoding="utf-8") as fh:
    json.dump({str(t): PRED[t] for t in PRED}, fh)

manifest = {
    "run_id": RUN_DIR.name, "experiment_id": "exp-20260921-a158-head-ml",
    "status": "completed",
    "started_at_utc": datetime.now(timezone.utc).isoformat(),
    "base_run": "20260921T125117-alpha158-90aa2",
    "frozen_changes": [
        "label: per-month top-20% binary (80th pct threshold)",
        "objective binary + LGBMClassifier",
        "ml_scores.json = predict_proba[:,1]",
        "report-only: top4 hit rate vs median, top4-vs-pool excess"],
    "step1": {"features_evaluated": ok.height,
              "abs_t_ge_2": strong.height},
    "step2": {"models": n_models, "ic_months": len(ics),
              "rank_ic_mean": mean_ic, "rank_ic_t": t_ic_ml,
              "by_year": by_year, "top_features": top_feats},
    "head_report_only": {"top4_hit_rate_vs_median": hit_rate,
                         "picks": hit_n, "months": len(excess_rows),
                         "mean_monthly_excess_vs_pool": exc_mean,
                         "positive_excess_months": exc_pos},
    "files": {p.relative_to(RUN_DIR).as_posix(): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in
        sorted((RUN_DIR / "outputs").rglob("*")) if p.is_file()},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log("done")
