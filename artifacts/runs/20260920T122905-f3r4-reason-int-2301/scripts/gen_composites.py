# -*- coding: utf-8 -*-
"""exp-20260920-factor-round-f3r4 -- stage A: event flags + the three arm
composites (prereg docs/research/exp-20260920-factor-round-f3r4-prereg.md
sec 2/3/5/8; configs/experiments/f3r4-reason-integration.json).

What this script does (all mechanical, no fitting, no RNG):

1. identity pins (events table / F3-EW composite / 17 F2R1 representative
   factor parquets / all120 / dedup clusters / daily panel / engine);
   val-freeze assertions (max ann_date <= 2020-12-31; the composite carries no
   2021+ signal month).
2. TF-S3: b = median over the signal months of the F3-EW composite
   cross-sectional std, computed on the parquet's own month set (71 months);
   the 68-month variant (2015-04-30..2020-11-30 = the attribution run's
   forward-return coverage, which is where the prereg's "68" comes from) is
   registered too and drives one disclosed A-arm repeat.  Every monthly std is
   registered verbatim for independent recomputation.
3. event flags: for each signal_date t and each composite-row symbol,
   class = impairment / price_up from the T1 event table when
   signal_date >= ann_date and the session distance is in [0, W]
   (W = 60 frozen; 20/40 for the sensitivity only).  Same class -> nearest
   announcement; impairment vs price_up conflict -> the later announcement
   decides; equal ann_date -> STOP and report the count (TF-S4).
4. arm composites:
   A: value + b*(+1 impairment / -1 price_up / 0)
   B: price_up -> -10 (suppressed), impairment untouched
   C: 18-factor EW mean = mean(17 z_i, z_event), the 17-factor z rebuilt along
      the attribution run's path (R16 pool + F3R1 sec 4 construction, FA-S2
      alignment gate re-run against outputs/F3-EW_composite.parquet), and
      z_event = (rank_pct - 0.5)*(+1) over that eligible set on a 0/+1/-1
      event column.
   Reversibility (prereg sec 8): in every flag-free signal month the A and B
   values must be BIT-identical to the base, and C must equal the 17-factor
   composite (its z_event column is a degenerate all-zero column there) --
   any failure -> STOP.
5. sensitivity composites for the A arm (windows 20/40) + the b-variant.

Outputs: outputs/composite_{A,B,C}.parquet, outputs/events_flag.parquet
(+ events_flag_w20/w40), outputs/composite_A_w20/w40.parquet,
outputs/composite_A_b68.parquet, tmp/composites_summary.json.
Deterministic; no RNG.
"""
from __future__ import annotations

import hashlib
import json
import platform
import struct
import sys
import time
from datetime import date
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

EVENT_RUN = ROOT / "artifacts/runs/20260920T113527-t1-reason-event-b690"
EVENT_TABLE = EVENT_RUN / "outputs/events_dev.parquet"
F3R1_RUN = ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
F2R1_RUN = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
BASE_COMPOSITE = F3R1_RUN / "outputs/F3-EW_composite.parquet"
PREREG_MD = ROOT / "docs/research/exp-20260920-factor-round-f3r4-prereg.md"
CONFIG_JSON = ROOT / "configs/experiments/f3r4-reason-integration.json"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
DAILY_CAL = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}

ENGINE_SHA_EXPECT = "a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1f0a466b0675abf3"
DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
FREEZE_CUT = date(2020, 12, 31)          # val 2021-2024: zero contact
CLASSES = ("impairment", "price_up")
DIRECTION = {"impairment": 1.0, "price_up": -1.0}
WINDOW_FROZEN = 60
WINDOW_SENS = (20, 40)
SUPPRESS_VALUE = -10.0
B68_FIRST_MONTH = date(2015, 4, 30)      # attribution run r-coverage caliber

T0 = time.perf_counter()
STAGES: dict[str, float] = {}
summary: dict = {"experiment_id": "exp-20260920-factor-round-f3r4",
                 "stage": "A_event_flags_and_composites", "status": "running",
                 "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "stages_s": STAGES}


def log(msg: object) -> None:
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
    """STOP discipline (prereg sec 8): stop report + aborted summary, exit 2."""
    log(f"!! STOP: {reason}")
    (RUN_DIR / "tmp" / "stop_report.md").write_text(
        "# STOP REPORT -- exp-20260920-factor-round-f3r4 (stage A)\n\n"
        "- stopped_at_stage: A (event flags / composite pre-generation)\n"
        f"- reason: {reason}\n"
        f"- elapsed_s: {time.perf_counter() - T0:.1f}\n"
        "- artifacts completed before the stop: see outputs/ and "
        "tmp/composites_summary.json\n"
        "- no downgrade, no re-tuning; adjudication belongs to the main "
        "conversation.\n",
        encoding="utf-8", newline="\n")
    summary["status"] = "aborted"
    summary["stop_reason"] = reason
    (RUN_DIR / "tmp" / "composites_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8", newline="\n")
    sys.exit(2)


def bits(x: float) -> bytes:
    """IEEE-754 bit pattern of a float (bit-level identity checks)."""
    return struct.pack("<d", float(x))


def same_bits(x: float, y: float) -> bool:
    """Bit-level identity; +0.0 and -0.0 count as identical (IEEE ==)."""
    if bits(x) == bits(y):
        return True
    return float(x) == 0.0 and float(y) == 0.0


# === 0. identity pins ========================================================
log("== 0. identity pins ==")
pins: dict = {}
ENGINE_GOT = sha256_file(ENGINE_PY)
pins["engine"] = {"path": str(ENGINE_PY), "sha256": ENGINE_GOT,
                  "expected": ENGINE_SHA_EXPECT,
                  "match": ENGINE_GOT == ENGINE_SHA_EXPECT,
                  "version": "v1.4.1 (non-zones path = v1.3 semantics)"}
if not pins["engine"]["match"]:
    stop(f"engine pin mismatch: {ENGINE_GOT}")
for name, p in [("prereg", PREREG_MD), ("config", CONFIG_JSON),
                ("events_dev", EVENT_TABLE), ("base_composite", BASE_COMPOSITE),
                ("daily_calendar", DAILY_CAL),
                ("f2r1_all120", F2R1_RUN / "outputs/f2r1_all120.csv"),
                ("dedup_clusters", F3R1_RUN / "outputs/dedup_clusters.csv")]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
    log(f"  {name}: {pins[name]['sha256'][:16]}")

REPS = sorted(pl.read_csv(F3R1_RUN / "outputs/dedup_clusters.csv")
              ["representative"].to_list())
assert len(REPS) == 17, f"expected 17 representatives, got {REPS}"
M = len(REPS)
MIN_COV = -(-M // 2)          # ceil(M/2) = 9, F3R1 verbatim
for fid in REPS:
    p = F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]] / f"{fid}.parquet"
    pins[f"rep_{fid}"] = {"path": str(p), "sha256": sha256_file(p)}
all120 = pl.read_csv(F2R1_RUN / "outputs/f2r1_all120.csv")
stats120 = {r["factor_id"]: r for r in all120.iter_rows(named=True)}
SIGNS = {fid: (1.0 if float(stats120[fid]["ic_mean"]) > 0 else -1.0)
         for fid in REPS}
log(f"  17 representatives; coverage rule >= {MIN_COV}/{M} non-null")
log(f"  signs {json.dumps(SIGNS)}")
summary["pins"] = pins
summary["env"] = {"python": platform.python_version(), "polars": pl.__version__,
                  "numpy": np.__version__, "platform": platform.platform()}
stage("pins")

# === 1. calendar, signal days, val-freeze assertions ========================
log("== 1. calendar + signal days + val-freeze assertions ==")
base = pl.read_parquet(BASE_COMPOSITE)
if set(base.columns) != {"symbol", "signal_date", "value"}:
    stop(f"base composite unexpected schema {base.columns}")
if base["value"].null_count() or not np.isfinite(
        base["value"].to_numpy()).all():
    stop("base composite has null/non-finite values")
if base.group_by("symbol", "signal_date").len().filter(pl.col("len") > 1).height:
    stop("base composite (symbol, signal_date) is not unique")
base_months = sorted(set(base["signal_date"].to_list()))
if max(base_months) > FREEZE_CUT:
    stop(f"base composite has a signal month beyond the freeze cut: "
         f"{max(base_months)}")

cal = r16.market_calendar(DAILY_CAL)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
if sig_days != base_months:
    stop(f"runner signal days != composite months ({len(sig_days)} vs "
         f"{len(base_months)}; extra in sig_days "
         f"{[x for x in sig_days if x not in set(base_months)][:3]}; extra in "
         f"composite {[x for x in base_months if x not in set(sig_days)][:3]})")
log(f"  {len(sig_days)} signal days {sig_days[0]}..{sig_days[-1]} == composite "
    f"months; freeze cut {FREEZE_CUT} respected")
summary["signal_days"] = {"n": len(sig_days), "first": str(sig_days[0]),
                          "last": str(sig_days[-1])}

emp = pl.read_parquet(EVENT_TABLE)
ann_max = emp["ann_date"].max()
if ann_max > FREEZE_CUT:
    stop(f"event table max(ann_date) = {ann_max} > {FREEZE_CUT}")
ev = (emp.filter(pl.col("primary_code").is_in(list(CLASSES)))
      .select("symbol", "ann_date", "primary_code"))
bad_dates = sorted({d for d in ev["ann_date"].to_list() if d not in idx_of_full})
if bad_dates:
    stop(f"{len(bad_dates)} event ann_date(s) are not calendar sessions: "
         f"{bad_dates[:5]}")
cnt_by_class = {c: int((ev["primary_code"] == c).sum()) for c in CLASSES}
log(f"  events_dev {emp.height} rows; impairment {cnt_by_class['impairment']},"
    f" price_up {cnt_by_class['price_up']}; ann_date "
    f"{ev['ann_date'].min()}..{ann_max}")
summary["event_table"] = {
    "rows_total": emp.height, "rows_two_classes": ev.height,
    "ann_date_min": str(ev["ann_date"].min()),
    "ann_date_max": str(ann_max),
    "counts_by_class": cnt_by_class,
    "note": "the prereg quotes 6,664 pool-filtered events; the written "
            "analysis table holds 6,656 rows (the T1 analysis-group filter "
            "drops 8 rows without a usable forward window).  Flag construction "
            "uses the table as written and only needs symbol/ann_date/"
            "primary_code.",
}
stage("calendar")

# === 2. TF-S3: b = median cross-sectional std ===============================
log("== 2. TF-S3: b = median over signal months of the composite x-sec std ==")
std_rows = []
for t in sig_days:
    v = base.filter(pl.col("signal_date") == t)["value"].to_numpy()
    std_rows.append({"month": str(t), "n": int(v.size),
                     "std": float(np.std(v, ddof=1))})
b_median_all = float(np.median([r["std"] for r in std_rows]))
n68 = sum(1 for r in std_rows if date.fromisoformat(r["month"]) >= B68_FIRST_MONTH)
b_median_68 = float(np.median([r["std"] for r in std_rows
                               if date.fromisoformat(r["month"])
                               >= B68_FIRST_MONTH]))
log(f"  b(median over {len(std_rows)} months) = {b_median_all!r}")
log(f"  b(median over the {n68} months from {B68_FIRST_MONTH}) = "
    f"{b_median_68!r}")
summary["tf_s3"] = {
    "caliber": "b = median over signal months of the F3-EW composite "
               "cross-sectional std (ddof=1), mechanical, no fitting",
    "b": b_median_all, "b_months_n": len(std_rows),
    "b_68_month_variant": b_median_68, "b_68_month_variant_n": n68,
    "note": "the prereg writes 'median over 68 signal months'; the parquet "
            "holds 71 signal months (2015-01-30..2020-11-30, the F3R3 "
            "caliber).  68 is the attribution run's forward-return coverage "
            "(2015-04-30..2020-11-30; min_history_rows=60 drops 2015 Q1).  The "
            "frozen arm parameter is the 71-month median (every month the "
            "runner consumes); the 68-month value drives one disclosed A-arm "
            "repeat registered in the manifest as a TF-S3 seam check.",
    "monthly_std": std_rows,
}
stage("b_value")

# === 3. event flags =========================================================
log("== 3. event flags (window rule per prereg sec 2) ==")
by_sym: dict[str, list[tuple[int, date, str]]] = {}
for r in ev.iter_rows(named=True):
    by_sym.setdefault(r["symbol"], []).append(
        (idx_of_full[r["ann_date"]], r["ann_date"], r["primary_code"]))
for v in by_sym.values():
    v.sort()
base_by_day: dict[date, set[str]] = {}
for t in sig_days:
    base_by_day[t] = set(base.filter(pl.col("signal_date") == t)
                         ["symbol"].to_list())


def build_flags(window: int) -> dict:
    """{t: {symbol: (cls, ann_date, dist)}} + conflict diagnostics."""
    flags: dict[date, dict[str, tuple[str, date, int]]] = {}
    diag = {"conflicts_resolved_later_wins": 0, "conflict_ties": [],
            "events_in_window_symbol_in_composite": 0,
            "events_in_window_symbol_out_of_composite": 0,
            "impairment_same_class_nearest_drops": 0,
            "price_up_same_class_nearest_drops": 0}
    for t in sig_days:
        i_s = idx_of_full[t]
        comp = base_by_day[t]
        month: dict[str, tuple[str, date, int]] = {}
        for sym, evs in by_sym.items():
            win = [e for e in evs if i_s - window <= e[0] <= i_s]
            if not win:
                continue
            if sym not in comp:
                diag["events_in_window_symbol_out_of_composite"] += len(win)
                continue
            diag["events_in_window_symbol_in_composite"] += len(win)
            nearest: dict[str, tuple[int, date]] = {}
            for i_a, d_a, cls in win:
                cur = nearest.get(cls)
                if cur is None:
                    nearest[cls] = (i_a, d_a)
                elif d_a > cur[1]:
                    diag[f"{cls}_same_class_nearest_drops"] += 1
                    nearest[cls] = (i_a, d_a)
                else:
                    diag[f"{cls}_same_class_nearest_drops"] += 1
            if len(nearest) == 1:
                cls, (i_a, d_a) = next(iter(nearest.items()))
            else:
                imp, pu = nearest["impairment"], nearest["price_up"]
                if imp[1] == pu[1]:
                    diag["conflict_ties"].append(
                        {"month": str(t), "symbol": sym,
                         "ann_date": str(imp[1])})
                    continue
                cls, (i_a, d_a) = (("impairment", imp) if imp[1] > pu[1]
                                   else ("price_up", pu))
                diag["conflicts_resolved_later_wins"] += 1
            month[sym] = (cls, d_a, i_s - i_a)
        flags[t] = month
    return {"flags": flags, "diag": diag}


FLAG_BUILD = {w: build_flags(w) for w in (WINDOW_FROZEN, *WINDOW_SENS)}
FLAGS = FLAG_BUILD[WINDOW_FROZEN]["flags"]
FLAG_DIAG = FLAG_BUILD[WINDOW_FROZEN]["diag"]
if FLAG_DIAG["conflict_ties"]:
    stop(f"impairment/price_up conflict with EQUAL ann_date on "
         f"{len(FLAG_DIAG['conflict_ties'])} (symbol, month) pairs -- prereg "
         f"sec 2/7 (TF-S4) requires stopping and reporting the count: "
         f"{FLAG_DIAG['conflict_ties'][:5]}")
flag_months = [t for t in sig_days if FLAGS[t]]
first_flag_month = flag_months[0] if flag_months else None
per_month = []
for t in sig_days:
    m = FLAGS[t]
    per_month.append({
        "month": str(t), "n_eligible": len(base_by_day[t]),
        "n_flagged": len(m),
        "n_impairment": sum(1 for v in m.values() if v[0] == "impairment"),
        "n_price_up": sum(1 for v in m.values() if v[0] == "price_up"),
        "max_dist": max((v[2] for v in m.values()), default=None)})
n_pairs = sum(len(FLAGS[t]) for t in sig_days)
log(f"  flags: {len(flag_months)}/{len(sig_days)} months carry a flag; first "
    f"{first_flag_month}; pairs {n_pairs} "
    f"(impairment {sum(1 for t in sig_days for v in FLAGS[t].values() if v[0] == 'impairment')}, "
    f"price_up {sum(1 for t in sig_days for v in FLAGS[t].values() if v[0] == 'price_up')})")
log(f"  conflicts resolved by the later announcement "
    f"{FLAG_DIAG['conflicts_resolved_later_wins']}; equal-date ties "
    f"{len(FLAG_DIAG['conflict_ties'])}; in-window events on symbols outside "
    f"the composite at t {FLAG_DIAG['events_in_window_symbol_out_of_composite']}")
for w in WINDOW_SENS:
    d = FLAG_BUILD[w]
    log(f"  window {w}: months with flags "
        f"{sum(1 for t in sig_days if d['flags'][t])}, pairs "
        f"{sum(len(d['flags'][t]) for t in sig_days)}")
summary["event_flags"] = {
    "window_sessions_frozen": WINDOW_FROZEN,
    "caliber": "signal_date >= ann_date and session distance (shared r16 "
               "market_calendar) in [0, W]; same class -> nearest ann_date; "
               "impairment vs price_up -> later announcement wins; equal "
               "ann_date -> STOP",
    "months_total": len(sig_days), "months_with_flags": len(flag_months),
    "first_month_with_flags": str(first_flag_month),
    "flag_free_months": [str(t) for t in sig_days if not FLAGS[t]],
    "pairs": n_pairs,
    "pairs_impairment": sum(1 for t in sig_days for v in FLAGS[t].values()
                            if v[0] == "impairment"),
    "pairs_price_up": sum(1 for t in sig_days for v in FLAGS[t].values()
                          if v[0] == "price_up"),
    "diagnostics": FLAG_DIAG,
    "per_month": per_month,
    "sensitivity_windows": {
        str(w): {"months_with_flags":
                 sum(1 for t in sig_days if FLAG_BUILD[w]["flags"][t]),
                 "pairs": sum(len(FLAG_BUILD[w]["flags"][t])
                              for t in sig_days)}
        for w in WINDOW_SENS},
}
stage("event_flags")


def flag_frame(flags: dict) -> pl.DataFrame:
    rows = [{"symbol": s, "signal_date": t, "class": v[0],
             "ann_date": v[1], "dist_sessions": v[2]}
            for t in sig_days for s, v in sorted(flags[t].items())]
    if not rows:
        return pl.DataFrame(schema={"symbol": pl.String,
                                    "signal_date": pl.Date,
                                    "class": pl.String, "ann_date": pl.Date,
                                    "dist_sessions": pl.Int64})
    return (pl.DataFrame(rows)
            .select("symbol", "signal_date", "class", "ann_date",
                    "dist_sessions")
            .sort("signal_date", "symbol"))


for w, tag in [(WINDOW_FROZEN, "")] + [(w, f"_w{w}") for w in WINDOW_SENS]:
    flag_frame(FLAG_BUILD[w]["flags"]).write_parquet(
        RUN_DIR / "outputs" / f"events_flag{tag}.parquet")
summary["event_flag_files"] = {f"events_flag{tag}.parquet":
                               sha256_file(RUN_DIR / "outputs"
                                           / f"events_flag{tag}.parquet")
                               for tag in ("", "_w20", "_w40")}

# === 4. arm composites ======================================================
log("== 4. arm composites (A / B / C) ==")


def apply_flag_value(frame: pl.DataFrame, b: float | None,
                     flags: dict) -> pl.DataFrame:
    """Additive arm (b not None) or suppression arm (b None).  Unflagged rows
    keep the base value UNTOUCHED (bit-identical, prereg sec 8)."""
    cls_map = {(t, s): v[0] for t in sig_days for s, v in flags[t].items()}
    keys = list(zip(frame["signal_date"].to_list(), frame["symbol"].to_list()))
    vals = frame["value"].to_list()
    if b is None:
        new = [SUPPRESS_VALUE if cls_map.get(k) == "price_up" else v
               for k, v in zip(keys, vals)]
    else:
        new = [v + DIRECTION[cls_map[k]] * b if k in cls_map else v
               for k, v in zip(keys, vals)]
    return frame.with_columns(pl.Series("value", new, dtype=pl.Float64))


comp_A = apply_flag_value(base, b_median_all, FLAGS)
comp_B = apply_flag_value(base, None, FLAGS)
comp_A_b68 = apply_flag_value(base, b_median_68, FLAGS)
comp_A_w = {w: apply_flag_value(base, b_median_all, FLAG_BUILD[w]["flags"])
            for w in WINDOW_SENS}

# ---- reversibility (prereg sec 8) -----------------------------------------
log("== 4b. reversibility: flag-free months bit-identical to the base ==")
BASE_MAP = {(t, s): float(v) for t, s, v in
            zip(base["signal_date"].to_list(), base["symbol"].to_list(),
                base["value"].to_list())}
FLAG_FREE = [t for t in sig_days if not FLAGS[t]]
CLS_PAIRS_ALL = {(t, s) for t in sig_days for s in FLAGS[t]}
CLS_PAIRS = {"F3R4-A": CLS_PAIRS_ALL,
             "F3R4-B": {(t, s) for t in sig_days for s in FLAGS[t]
                        if FLAGS[t][s][0] == "price_up"}}


def reversibility(arm: str, frame: pl.DataFrame) -> dict:
    exp_pairs = CLS_PAIRS[arm]
    got = {(t, s): float(v) for t, s, v in
           zip(frame["signal_date"].to_list(), frame["symbol"].to_list(),
               frame["value"].to_list())}
    if set(got) != set(BASE_MAP):
        stop(f"{arm}: key set differs from the base composite "
             f"(mine-only {len(set(got) - set(BASE_MAP))}, base-only "
             f"{len(set(BASE_MAP) - set(got))})")
    diffs = sorted(k for k in BASE_MAP
                   if not same_bits(got[k], BASE_MAP[k]))
    diffs_unflagged = [k for k in diffs if k not in CLS_PAIRS_ALL]
    diffs_free = [k for k in diffs if k[0] in set(FLAG_FREE)]
    ok = not diffs_unflagged and not diffs_free
    log(f"  {arm}: rows {len(got)}; bit-differing {len(diffs)} "
        f"(expected flagged pairs {len(exp_pairs)}; unflagged differing "
        f"{len(diffs_unflagged)}); flag-free months {len(FLAG_FREE)} -> "
        f"differing rows {len(diffs_free)}; PASS={ok}")
    if not ok:
        stop(f"{arm}: reversibility FAILED -- unflagged rows differing "
             f"{len(diffs_unflagged)} (e.g. {diffs_unflagged[:3]}); flag-free "
             f"month rows differing {len(diffs_free)} (e.g. {diffs_free[:3]})")
    if len(diffs) != len(exp_pairs):
        stop(f"{arm}: {len(exp_pairs)} flagged (symbol, month) pairs must "
             f"change value but {len(diffs)} rows differ")
    return {"pass": True, "rows": len(got), "rows_bit_differing": len(diffs),
            "rows_bit_differing_are_exactly_the_flagged_pairs": True,
            "flagged_pairs_changed": len(exp_pairs),
            "flagged_pairs_all_classes": len(CLS_PAIRS_ALL),
            "flag_free_months": len(FLAG_FREE),
            "flag_free_month_rows_differing": 0,
            "note": "flag-free months: the arm mask is empty there, so the base "
                    "value column passes through untouched (bit-identical)"}


rev_A = reversibility("F3R4-A", comp_A)
rev_B = reversibility("F3R4-B", comp_B)
summary["reversibility"] = {"F3R4-A": rev_A, "F3R4-B": rev_B}
stage("comps_AB")

# ---- C arm: 17-factor z rebuild (attribution run path verbatim) ------------
log("== 4c. C arm: 17-factor z rebuild (R16 pool + F3R1 sec 4) ==")
hist = r16.build_history_r16(DAILY_CAL, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
del hist
pool_set = {t: set(pools_at[t]["ranked"]) for t in sig_days}
log(f"  R16 pool n: min {min(len(v) for v in pool_set.values())} "
    f"max {max(len(v) for v in pool_set.values())}")

wide = None
for fid in REPS:
    f = (pl.read_parquet(F2R1_RUN / "outputs" / FAMILY_DIR[fid[0]]
                         / f"{fid}.parquet")
         .filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
         .rename({"value": fid}))
    wide = f if wide is None else wide.join(f, on=["symbol", "signal_date"],
                                            how="full", coalesce=True)
wide = wide.filter(pl.col("signal_date").is_in(pl.Series(sig_days)))
log(f"  wide frame {wide.height} rows, {wide['symbol'].n_unique()} symbols")

elig: dict[date, list[str]] = {}
comp17: dict[date, dict[str, float]] = {}
parts: dict[date, dict[str, dict[str, float]]] = {}
for t in sig_days:
    g = wide.filter(pl.col("signal_date") == t)
    have = g.with_columns(
        sum(pl.col(f).is_not_null().cast(pl.Int8) for f in REPS).alias("_n"))
    have = (have.filter(pl.col("symbol").is_in(pl.Series(sorted(pool_set[t]))))
            .filter(pl.col("_n") >= MIN_COV))
    elig[t] = sorted(have["symbol"].to_list())
    with_parts = have
    for fid in REPS:
        with_parts = with_parts.with_columns(
            ((pl.col(fid).rank(method="average") - 1.0)
             / pl.max_horizontal(pl.col(fid).count() - 1.0, 1))
            .alias(f"_p_{fid}"))
    parts[t], ew_t = {}, {}
    for r in with_parts.select(["symbol"] + [f"_p_{f}" for f in REPS]) \
                       .iter_rows(named=True):
        zs = {fid: (r[f"_p_{fid}"] - 0.5) * SIGNS[fid] for fid in REPS
              if r[f"_p_{fid}"] is not None}
        parts[t][r["symbol"]] = zs
        if zs:
            ew_t[r["symbol"]] = sum(zs.values()) / len(zs)
    comp17[t] = ew_t
log(f"  eligible sizes: min {min(len(v) for v in elig.values())} "
    f"median {int(np.median([len(v) for v in elig.values()]))} "
    f"max {max(len(v) for v in elig.values())}")
stage("composite17_rebuild")

# ---- FA-S2 alignment gate (attribution run caliber, re-run here) ----------
log("== 4d. FA-S2 gate: rebuilt 17-factor composite vs F3-EW_composite ==")
ref_map = {(r["signal_date"], r["symbol"]): float(r["value"])
           for r in base.iter_rows(named=True)}
reb_map = {(t, s): v for t in sig_days for s, v in comp17[t].items()}
if set(ref_map) != set(reb_map):
    stop(f"FA-S2 key-set mismatch: ref-only {len(set(ref_map) - set(reb_map))} "
         f"{sorted(set(ref_map) - set(reb_map))[:3]}, rebuilt-only "
         f"{len(set(reb_map) - set(ref_map))} "
         f"{sorted(set(reb_map) - set(ref_map))[:3]}")
global_max = max(abs(reb_map[k] - ref_map[k]) for k in ref_map)
if global_max > 1e-9:
    stop(f"FA-S2 value mismatch: global max |diff| {global_max:.3e} > 1e-9")
log(f"  FA-S2 PASS: {len(ref_map)} keys equal, global max |diff| "
    f"{global_max:.3e}")
summary["fa_s2"] = {"pass": True, "keys": len(ref_map), "keys_equal": True,
                    "max_abs_diff_global": global_max, "tolerance": 1e-9,
                    "caliber": "rebuilt 17-factor EW composite (R16 pool + "
                               "F3R1 sec 4 construction, mean of available "
                               "components) vs outputs/F3-EW_composite.parquet"}

# ---- z_event + the 18-factor mean -----------------------------------------
log("== 4e. z_event + the 18-factor composite (C) ==")
zev_stats = []
comp_C_vals: dict[date, dict[str, float]] = {}
for t in sig_days:
    es = elig[t]
    n_imp = sum(1 for s in es if FLAGS[t].get(s, ("",))[0] == "impairment")
    n_pu = sum(1 for s in es if FLAGS[t].get(s, ("",))[0] == "price_up")
    if n_imp == 0 and n_pu == 0:
        comp_C_vals[t] = dict(comp17[t])
        zev_stats.append({"month": str(t), "n_eligible": len(es),
                          "n_impairment": 0, "n_price_up": 0,
                          "degenerate": True, "z_event": None})
        continue
    evv = pl.DataFrame({
        "symbol": es,
        "e": [DIRECTION[FLAGS[t][s][0]] if s in FLAGS[t] else 0.0
              for s in es]})
    evv = evv.with_columns(
        (((pl.col("e").rank(method="average") - 1.0)
          / pl.max_horizontal(pl.col("e").count() - 1.0, 1)) - 0.5)
        .alias("z_event"))
    zmap = dict(zip(evv["symbol"].to_list(), evv["z_event"].to_list()))
    comp_C_vals[t] = {s: (sum(parts[t][s].values()) + zmap[s])
                      / (len(parts[t][s]) + 1) for s in es}
    zz = [zmap[s] for s in es]
    zev_stats.append({"month": str(t), "n_eligible": len(es),
                      "n_impairment": n_imp, "n_price_up": n_pu,
                      "degenerate": False,
                      "z_event": {"min": float(min(zz)), "max": float(max(zz)),
                                  "mean": float(np.mean(zz)),
                                  "std": float(np.std(zz, ddof=1))},
                      "z_event_zero_count": int(sum(1 for z in zz
                                                   if z == 0.0))})
comp_C = pl.DataFrame({
    "symbol": [s for t in sig_days for s in sorted(comp_C_vals[t])],
    "signal_date": [t for t in sig_days for s in sorted(comp_C_vals[t])],
    "value": [comp_C_vals[t][s] for t in sig_days
              for s in sorted(comp_C_vals[t])]},
    schema={"symbol": pl.String, "signal_date": pl.Date, "value": pl.Float64})
deg = [r for r in zev_stats if r["degenerate"]]
log(f"  z_event: {len(zev_stats) - len(deg)} informative months, "
    f"{len(deg)} degenerate (flag-free -> z_event null -> C == the 17-factor "
    f"composite)")
summary["z_event"] = {
    "informative_months": len(zev_stats) - len(deg),
    "degenerate_months": len(deg),
    "degenerate_month_list": [r["month"] for r in deg],
    "per_month": zev_stats,
    "caliber": "z_event = (rank_pct - 0.5) * (+1) over the ELIGIBLE set (R16 "
               "pool INTERSECTION >= 9/17 non-null = the F3R1 caliber), event "
               "column 0/+1 impairment/-1 price_up, average-rank ties, "
               "normalised by the non-null count; a flag-free month has a "
               "degenerate all-zero column -> z_event null -> the C composite "
               "equals the 17-factor composite.  Alternative literal reading "
               "(keep the 0 in the mean): a uniform 17/18 scale in flag-free "
               "months, order-preserving, so the sleeve membership and every "
               "backtest number are identical (disclosed)."}

# ---- C alignment + reversibility ------------------------------------------
gotC = {(t, s): float(v) for t, s, v in
        zip(comp_C["signal_date"].to_list(), comp_C["symbol"].to_list(),
            comp_C["value"].to_list())}
if set(gotC) != set(BASE_MAP):
    stop(f"F3R4-C: key set differs from the base composite "
         f"(mine-only {len(set(gotC) - set(BASE_MAP))}, base-only "
         f"{len(set(BASE_MAP) - set(gotC))})")
c_diffs = sorted(k for k in BASE_MAP if not same_bits(gotC[k], BASE_MAP[k]))
c_diffs_free = [k for k in c_diffs if k[0] in set(FLAG_FREE)]
c_diffs_info = [k for k in c_diffs if k[0] not in set(FLAG_FREE)]
if c_diffs_free:
    stop(f"F3R4-C: {len(c_diffs_free)} rows differ from the 17-factor "
         f"composite in flag-free months (alignment gate) e.g. "
         f"{c_diffs_free[:3]}")
log(f"  C alignment PASS: {len(FLAG_FREE)} flag-free months bit-identical to "
    f"the 17-factor composite; {len(c_diffs_info)} rows differ in the "
    f"{len(sig_days) - len(FLAG_FREE)} informative months")
summary["c_alignment"] = {"pass": True, "flag_free_months": len(FLAG_FREE),
                          "flag_free_month_rows_differing": 0,
                          "informative_month_rows_differing":
                              len(c_diffs_info),
                          "keys_equal_to_base": True}
stage("composite_C")

# === 5. write composites ====================================================
log("== 5. write composite parquets ==")
outs = {"composite_A.parquet": comp_A, "composite_B.parquet": comp_B,
        "composite_C.parquet": comp_C, "composite_A_b68.parquet": comp_A_b68}
for w in WINDOW_SENS:
    outs[f"composite_A_w{w}.parquet"] = comp_A_w[w]
for name, frame in outs.items():
    frame.write_parquet(RUN_DIR / "outputs" / name)
    log(f"  {name}: {frame.height} rows, "
        f"{frame['signal_date'].n_unique()} months, value "
        f"[{frame['value'].min():.4f}, {frame['value'].max():.4f}]")
summary["composite_files"] = {n: {"rows": f.height,
                                  "sha256": sha256_file(RUN_DIR / "outputs" / n),
                                  "value_min": float(f["value"].min()),
                                  "value_max": float(f["value"].max())}
                              for n, f in outs.items()}
summary["arm_parameters"] = {"b": b_median_all,
                             "suppress_value": SUPPRESS_VALUE,
                             "window_sessions": WINDOW_FROZEN}
summary["status"] = "completed"
summary["wall_seconds"] = time.perf_counter() - T0
summary["stages_s"] = dict(STAGES)
(RUN_DIR / "tmp" / "composites_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")
log(f"== stage A complete: b={b_median_all!r}, {len(flag_months)} flagged "
    f"months, wall {summary['wall_seconds']:.0f}s ==")
