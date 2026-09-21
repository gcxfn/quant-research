# -*- coding: utf-8 -*-
"""Phase-B failure attribution from EXISTING artifacts (no new backtests).

Answers the three advisor questions on the registered phase-B outputs:
1. Three-stage return decomposition per family:
     signal -> legal order -> FILL -> (20-own-session window) -> account
     (a) signal-window TR return for EVERY triggered event
     (b) post-fill TR return from the ACTUAL fill price (filled events)
     (c) account net CAGR incl. idle cash (from the run manifests)
2. Matched-control increment: event returns vs the same-day pool cross
   section (and for A, vs random members of the SAME monthly eligible
   set) over the same window.
3. Failure classification inputs: per-event execution categories
   (filled / attempted-unfilled / slot-skipped) with return stats.

Identity check: rebuilt event lists must match the phase-B main run's
manifest counts exactly (216/136/102/767) -- same code, same pinned
inputs, deterministic construction.  Zero strategy trials consumed.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
import psutil  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.event_family_signals import (  # noqa: E402
    FamilyParams, a_family_eligibility, b1_revision_events,
    b2_announcement_events, scan_a_triggers)
from quant.research.fixed_scheme_lib import build_atr20  # noqa: E402

MAIN_RUN = ROOT / "artifacts/runs/20260921T223157-eventfam-main-cb4cff"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
T1_DIR = ROOT / "data/features/fcst-reason-struct-full-20260918"
FCST_RAW_DIR = ROOT / "data/raw/tushare/forecast/20260909-r1"
EFS_PY = ROOT / "src/quant/research/event_family_signals.py"
DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
B_DEV_FIRST, B_DEV_LAST = "20180904", "20201231"
WIN_SESSIONS = 20          # prereg evaluation window (own sessions)

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
LOG_LINES: list[str] = []
_logf = (RUN_DIR / "logs" / "runner.log").open("a", encoding="utf-8")


def log(m: object) -> None:
    line = f"[{time.perf_counter() - T0:6.1f}s] {m}"
    LOG_LINES.append(line)
    _logf.write(line + "\n")
    _logf.flush()
    print(line, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


SELF_SHA_START = sha256_file(Path(__file__).resolve())
_r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                    capture_output=True, text=True)
GIT_HEAD = _r.stdout.strip()

# === 1. rebuild pools / series / events (same code path as the run) ========
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days = [d for d in all_mes["s"].to_list() if
            idx_of_full.get(d, 10**9) + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_by_month = [(t, pools_at[t]["ranked"]) for t in sig_days]
pool_set = {t: set(pools_at[t]["ranked"]) for t in sig_days}
pool_union = sorted(set().union(*pool_set.values()))
log(f"pools: {len(sig_days)} months, union {len(pool_union)}")

# total-return (c_adj) close lookup per symbol
cadj: dict[str, tuple] = {}
for (s,), g in (hist.filter(pl.col("date") >= date(2014, 6, 1))
                .partition_by("symbol", as_dict=True)).items():
    cadj[str(s)] = (
        [d.toordinal() for d in g["date"].to_list()],
        g["c_adj"].to_numpy().astype(np.float64))


def tr_factor(sym: str, d0: date, n_sessions: int) -> float | None:
    """Total-return factor over the n own sessions following d0."""
    a = cadj.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], d0.toordinal()))
    if i >= len(a[0]) or a[0][i] != d0.toordinal():
        i -= 1                      # suspension: anchor at last session <= d0
    j = i + n_sessions
    if i < 0 or j >= len(a[0]) or a[1][i] <= 0:
        return None
    return float(a[1][j] / a[1][i])


pool_daily = (
    pl.scan_parquet(DAILY_PARQUET)
    .filter((pl.col("tradestatus") == 1.0)
            & pl.col("symbol").is_in(pool_union)
            & (pl.col("date") >= date(2014, 3, 1))
            & (pl.col("date") <= DEV_END))
    .select("symbol", "date", "high", "low", "close", "volume")
    .collect())
series = {}
for (sym,), g in pool_daily.sort("symbol", "date").partition_by(
        "symbol", as_dict=True).items():
    from quant.research.event_family_signals import SymbolSeries
    series[str(sym)] = SymbolSeries(
        str(sym), g["date"].to_list(),
        g["close"].to_numpy().astype(np.float64),
        g["high"].to_numpy().astype(np.float64),
        g["low"].to_numpy().astype(np.float64),
        g["volume"].to_numpy().astype(np.float64))
del pool_daily
atr_tbl = build_atr20(
    pl.scan_parquet(DAILY_PARQUET)
    .filter(pl.col("symbol").is_in(pool_union)
            & (pl.col("date") >= date(2014, 3, 1)) & (pl.col("date") <= DEV_END))
    .select("symbol", "date", "high", "low", "close").collect())
atr_of = lambda s, d: atr_tbl.atr(s, d)  # noqa: E731
log(f"series ready: {len(series)}")

month_ends = [t for t, _ in pool_by_month]
from bisect import bisect_right  # noqa: E402


def _pool_member(sym, d):
    j = bisect_right(month_ends, d)
    return j > 0 and sym in pool_set.get(month_ends[j - 1], set())


def _tda(d):
    j = bisect_right(calendar_full, d)
    return calendar_full[j] if j < len(calendar_full) else d


# B rows
ri = pl.read_parquet(T1_DIR / "row_index.parquet").filter(
    (pl.col("ann_date") >= B_DEV_FIRST) & (pl.col("ann_date") <= B_DEV_LAST))
ann_rows = []
for p in sorted(T1_DIR.glob("batch_*.jsonl")):
    with p.open("r", encoding="utf-8") as f:
        ann_rows.extend(json.loads(x) for x in f)
ann = pl.DataFrame(ann_rows)
KEY = ["ts_code", "end_date", "ann_date", "update_flag"]
merged = ri.join(ann.select(KEY + ["primary_code"]), on=KEY, how="inner")
raw = pl.concat(
    [pl.read_csv(p) for p in sorted(FCST_RAW_DIR.glob("chunk_*.csv"))
     if B_DEV_FIRST[:6] <= p.stem.replace("chunk_", "") <= B_DEV_LAST[:6]],
    how="vertical").with_columns(
    pl.col("end_date").cast(pl.String), pl.col("ann_date").cast(pl.String),
    pl.col("update_flag").cast(pl.String))
merged = merged.join(raw.select(KEY + ["net_profit_min", "net_profit_max"]),
                     on=KEY, how="left")


def _ts(sym_ts):
    try:
        code, suf = sym_ts.split(".")
        return ("sh." if suf == "SH" else "sz.") + code if len(code) == 6 \
            and suf in ("SH", "SZ") else None
    except ValueError:
        return None


b_rows = [{"symbol": s, "end_date": r["end_date"], "ann_date": r["ann_date"],
           "update_flag": r["update_flag"], "type": r["type"],
           "primary_code": r["primary_code"],
           "net_profit_min": r["net_profit_min"],
           "net_profit_max": r["net_profit_max"]}
          for r in merged.iter_rows(named=True)
          if (s := _ts(r["ts_code"])) is not None]
log(f"B rows: {len(b_rows)}")

P = {"A1": FamilyParams("A1"), "A2": FamilyParams("A2"),
     "B1": FamilyParams("B1"), "B2": FamilyParams("B2")}
events = {"A1": scan_a_triggers(pool_by_month, series, atr_of, P["A1"]),
          "A2": scan_a_triggers(pool_by_month, series, atr_of, P["A2"]),
          "B1": b1_revision_events(b_rows, series, _pool_member, _tda, P["B1"]),
          "B2": b2_announcement_events(b_rows, series, pool_by_month,
                                       _pool_member, P["B2"])}
# identity check vs the main run manifest
main_mf = json.loads((MAIN_RUN / "manifest.json").read_text(encoding="utf-8"))
for k in P:
    n_run = main_mf["arms"][k]["n_events"]
    assert len(events[k]) == n_run, \
        f"{k}: rebuilt {len(events[k])} != run {n_run}"
    log(f"events[{k}] = {len(events[k])} == run manifest (identity OK)")

# === 2. join fills / per-event categories ===================================
rng = np.random.default_rng(20260921)
pool_returns_cache: dict[date, list[float]] = {}
elig_cache: dict[str, dict[date, set[str]]] = {}
for fam in ("A1", "A2"):
    elig_cache[fam] = {}
    for t, pool in pool_by_month:
        _e, _st = a_family_eligibility(pool, series, t, P[fam])
        elig_cache[fam][t] = _e


def pool_ret_list(d: date) -> list[float]:
    if d not in pool_returns_cache:
        j = bisect_right(month_ends, d)
        t = month_ends[j - 1] if j > 0 else month_ends[0]
        out = []
        for s2 in pool_set[t]:
            f = tr_factor(s2, d, WIN_SESSIONS)
            if f is not None:
                out.append(f - 1.0)
        pool_returns_cache[d] = out
    return pool_returns_cache[d]


def own_sessions_between(sym: str, d0: date, d1: date) -> int:
    a = cadj.get(sym)
    if a is None:
        return -1
    i = int(np.searchsorted(a[0], d0.toordinal(), side="right")) - 1
    j = int(np.searchsorted(a[0], d1.toordinal(), side="right")) - 1
    return j - i


rows_out: list[dict] = []
for fam in ("A1", "A2", "B1", "B2"):
    fills = pl.read_parquet(MAIN_RUN / "outputs" / f"{fam}_fills.parquet")
    buys = (fills.filter(pl.col("side") == "buy")
            .select("symbol", "date", "decision_date", "price")
            .sort("date"))
    buy_map: dict[str, list] = {}
    for r in buys.iter_rows(named=True):
        buy_map.setdefault(r["symbol"], []).append(
            (r["decision_date"], r["date"], float(r["price"])))
    ts = main_mf["metrics"][fam]["trigger_stats"]
    n_issued, n_filled = ts["issued"], ts["filled"]
    filled_matched = 0
    for ev in events[fam]:
        sym = ev.symbol
        tday = ev.trigger_day if fam in ("A1", "A2") else ev.decision_day
        sig_ret = tr_factor(sym, tday, WIN_SESSIONS)
        sig_ret = sig_ret - 1.0 if sig_ret is not None else None
        # matched control: pool cross-section same day
        pr = pool_ret_list(tday)
        pool_med = float(np.median(pr)) if pr else None
        pool_mean = float(np.mean(pr)) if pr else None
        # matched control: random same-eligible-set member (A families)
        elig_ret = None
        if fam in ("A1", "A2"):
            j = bisect_right(month_ends, tday)
            t = month_ends[j - 1] if j > 0 else month_ends[0]
            cands = sorted(elig_cache[fam][t] - {sym})
            if cands:
                picks = rng.choice(len(cands), size=min(5, len(cands)),
                                   replace=False)
                vals = [tr_factor(cands[int(k)], tday, WIN_SESSIONS) - 1.0
                        for k in picks]
                vals = [v for v in vals if v is not None]
                if vals:
                    elig_ret = float(np.mean(vals))
        # fill match: first buy of this symbol issued within 3 sessions
        fill = None
        for dec, fdate, price in buy_map.get(sym, []):
            if 0 <= own_sessions_between(sym, tday, dec) <= 3:
                fill = (fdate, price)
                break
        post_fill = None
        trig_to_fill = None
        if fill is not None:
            filled_matched += 1
            f_date = fill[0]
            f2 = tr_factor(sym, f_date, WIN_SESSIONS)
            if f2 is not None:
                post_fill = f2 - 1.0        # forward TR from the fill DAY
            gap_sessions = own_sessions_between(sym, tday, f_date)
            if 0 <= gap_sessions <= 6:
                f0 = tr_factor(sym, tday, gap_sessions)
                if f0 is not None:
                    trig_to_fill = f0 - 1.0  # drift while waiting to fill
        rows_out.append({
            "family": fam, "symbol": sym,
            "day": tday.isoformat(),
            "category": ("filled" if fill is not None else "unmatched"),
            "sig_ret_20": sig_ret,
            "pool_med_20": pool_med, "pool_mean_20": pool_mean,
            "elig_ctrl_20": elig_ret,
            "fill_day": fill[0].isoformat() if fill else None,
            "trig_to_fill": trig_to_fill,
            "post_fill_ret_20": post_fill})
    log(f"{fam}: events {len(events[fam])}, fill-matched {filled_matched} "
        f"(run trig filled {n_filled})")

out_dir = RUN_DIR / "outputs"
pl.DataFrame(rows_out).write_parquet(out_dir / "event_attribution.parquet")
pl.DataFrame(rows_out).write_csv(out_dir / "event_attribution.csv")

# === 3. aggregates ==========================================================
agg: dict[str, dict] = {}
for fam in ("A1", "A2", "B1", "B2"):
    df = pl.DataFrame([r for r in rows_out if r["family"] == fam])
    filled = df.filter(pl.col("category") == "filled")
    unfilled = df.filter(pl.col("category") == "unmatched")


    def _stats(col, frame):
        v = frame[col].drop_nulls()
        if v.len() == 0:
            return None
        a = v.to_numpy()
        return {"n": int(v.len()), "mean": float(a.mean()),
                "median": float(np.median(a)), "win": float((a > 0).mean())}


    agg[fam] = {
        "n_events": df.height,
        "signal_window": _stats("sig_ret_20", df),
        "signal_window_filled": _stats("sig_ret_20", filled),
        "signal_window_unfilled": _stats("sig_ret_20", unfilled),
        "trig_to_fill": _stats("trig_to_fill", filled),
        "post_fill": _stats("post_fill_ret_20", filled),
        "pool_median": _stats("pool_med_20", df),
        "pool_mean": _stats("pool_mean_20", df),
        "elig_control": _stats("elig_ctrl_20", df),
        "increment_vs_pool_med": (
            float((df["sig_ret_20"] - df["pool_med_20"]).drop_nulls()
                  .mean())),
        "increment_vs_elig": (
            float((df["sig_ret_20"] - df["elig_ctrl_20"]).drop_nulls()
                  .mean())
            if df["elig_ctrl_20"].drop_nulls().len() else None),
        # do fills systematically select WEAKER events? (filled minus all)
        "fill_selection_gap": (
            float(filled["sig_ret_20"].drop_nulls().mean()
                  - df["sig_ret_20"].drop_nulls().mean())
            if filled.height and df["sig_ret_20"].drop_nulls().len() else None),
    }
    log(f"{fam}: sig(mean) {agg[fam]['signal_window']['mean']*100:+.2f}% "
        f"post-fill {agg[fam]['post_fill']}"
        f" | inc vs pool_med "
        f"{agg[fam]['increment_vs_pool_med']*100:+.2f}pp")

# === 3b. drift TIMELINE: when does the event drift happen? ================
# mean cumulative TR of ALL events at sessions 2/5/10/20 (and the filled
# subset): if the drift is concentrated in the first 1-2 sessions (before
# any legal entry under the conservative clock), no registered entry
# structure could have captured it.
timeline: dict[str, dict] = {}
for fam in ("A1", "A2", "B1", "B2"):
    df = pl.DataFrame([r for r in rows_out if r["family"] == fam])
    filled_syms = {(r["symbol"], r["day"]) for r in rows_out
                   if r["family"] == fam and r["category"] == "filled"}
    checkpoints = (2, 5, 10, WIN_SESSIONS)
    entry = {}
    for ev in events[fam]:
        sym = ev.symbol
        tday = ev.trigger_day if fam in ("A1", "A2") else ev.decision_day
        is_fill = (sym, tday.isoformat()) in filled_syms
        for cp in checkpoints:
            f = tr_factor(sym, tday, cp)
            if f is None:
                continue
            entry.setdefault(cp, []).append((f - 1.0, is_fill))
    timeline[fam] = {
        f"sessions_1_{cp}": {
            "all_mean": float(np.mean([v for v, _ in vals])),
            "filled_mean": float(np.mean([v for v, f_ in vals if f_] or [np.nan]))
            if any(f_ for _, f_ in vals) else None,
            "n": len(vals)}
        for cp, vals in entry.items()}
    log(f"{fam} timeline: " + " ".join(
        f"s1-{cp}: {timeline[fam][f'sessions_1_{cp}']['all_mean']*100:+.2f}%"
        for cp in checkpoints))

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-eventfam-attribution",
    "status": "completed",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "runner_self": {"sha256_at_start": SELF_SHA_START,
                    "sha256_at_end": sha256_file(Path(__file__).resolve())},
    "git_head": GIT_HEAD,
    "peak_memory_mb": psutil.Process().memory_info().peak_wset / (1 << 20),
    "inputs": {"main_run": str(MAIN_RUN.relative_to(ROOT)),
               "main_run_manifest_sha": sha256_file(
                   MAIN_RUN / "manifest.json"),
               "event_family_signals_sha": sha256_file(EFS_PY),
               "daily_sha": sha256_file(DAILY_PARQUET),
               "t1_row_index_sha": sha256_file(T1_DIR / "row_index.parquet")},
    "identity_check": "rebuilt event counts equal the main-run manifest "
                      "(asserted in-script)",
    "trials_consumed": 0,
    "aggregates": agg,
    "drift_timeline": timeline,
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(out_dir.rglob("*")) if p.is_file()},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter()-T0:.0f}s ==")
_logf.close()
