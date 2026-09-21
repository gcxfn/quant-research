# -*- coding: utf-8 -*-
"""exp-20260920-factor-round-f3r4 -- independent verification (recomputation
from raw artifacts with separate implementations).

Checks (each recomputed WITHOUT the producer's code path):
 V1 event flags: recomputed by iterating each event FORWARD over the calendar
    (mark every session in [ann_date, ann_date+60] that is a signal day) and
    compared as a set to outputs/events_flag.parquet -- catches window/off-by-
    one direction errors.
 V2 composite adjustment identity: for every row of composite_A/B/C,
    value_A - value_base must equal exactly 0 or +/- b with the sign matching
    the flag class, and value_B must be exactly -10 for price_up flags and
    bit-equal to the base otherwise.
 V3 sleeve membership: rebuilt independently from each arm composite parquet
    (ranking + K=10 buffer + L1 industry cap <= 2) and compared with the
    sleeve log inside tmp/subruns/<tag>/stats.json.
 V4 headline metrics: net CAGR and max drawdown recomputed from
    tmp/subruns/<tag>/daily_equity.parquet with an independent formula and
    compared to the arm metrics (tolerance 1e-12).
 V5 adjudication arithmetic: the frozen line/floor and each arm's pass/fail
    recomputed from the committed metrics.

Reads only; writes tmp/verify_independent.json.  No RNG.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, timedelta
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

BASE_COMPOSITE = (ROOT / "artifacts/runs/20260919T191524-f3r1-factor-combo-c212"
                  / "outputs/F3-EW_composite.parquet")
EVENT_TABLE = (ROOT / "artifacts/runs/20260920T113527-t1-reason-event-b690"
               / "outputs/events_dev.parquet")
INDUSTRY_CSV = ROOT / "data/raw/tushare/index_member_all/20260909-r1/chunk_all.csv"
DAILY_CAL = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
SUBRUNS = RUN_DIR / "tmp/subruns"
ARMS = ["F3R4-A", "F3R4-B", "F3R4-C"]
BASE_CAGR = 0.04877310918741218
BASE_MDD = -0.17848532843799414
FROZEN_B = 0.10164738676824621
WINDOW = 60
SLEEVE_K, IND_CAP = 10, 2

out: dict = {"status": "running"}
base = pl.read_parquet(BASE_COMPOSITE)
base_map = {(r["signal_date"], r["symbol"]): float(r["value"])
            for r in base.iter_rows(named=True)}
sig_days = sorted({t for (t, _s) in base_map})
anchor_stats = json.loads((SUBRUNS / "F3R4-LZO/stats.json")
                          .read_text(encoding="utf-8"))
assert anchor_stats["anchor_compare"]["net_cagr_matches_chassis"]
B_FROZEN = FROZEN_B

# --- V1 flags recomputed forward from the event table ----------------------
cal = r16.market_calendar(DAILY_CAL)
cal_list = cal["date"].to_list()
idx = {d: i for i, d in enumerate(cal_list)}
sig_set = set(sig_days)
comp_of: dict[date, set[str]] = {}
for (t, s) in base_map:
    comp_of.setdefault(t, set()).add(s)
ev = pl.read_parquet(EVENT_TABLE).filter(
    pl.col("primary_code").is_in(["impairment", "price_up"]))
recomputed: dict[tuple[date, str], list[tuple[date, str]]] = {}
excluded_occurrences = 0
for r in ev.iter_rows(named=True):
    i0 = idx[r["ann_date"]]
    for j in range(i0, min(i0 + WINDOW, len(cal_list) - 1) + 1):
        d = cal_list[j]
        if d not in sig_set:
            continue
        if r["symbol"] not in comp_of[d]:
            # out-of-composite occurrences (the producer's diagnostic unit)
            excluded_occurrences += 1
            continue
        recomputed.setdefault((d, r["symbol"]), []).append(
            (r["ann_date"], r["primary_code"]))
consumed = pl.read_parquet(RUN_DIR / "outputs/events_flag.parquet")
diag = json.loads((RUN_DIR / "tmp/composites_summary.json")
                  .read_text(encoding="utf-8"))[
                      "event_flags"]["diagnostics"][
                          "events_in_window_symbol_out_of_composite"]
# the producer keeps one class per pair (nearest / later-wins); compare the
# pair key set and, per pair, that the producer's ann_date is the class'
# nearest announcement inside the window
key_mismatch = []
ann_mismatch = []
prod = {(r["signal_date"], r["symbol"]): (r["class"], r["ann_date"],
                                          r["dist_sessions"])
        for r in consumed.iter_rows(named=True)}
for k, evs in recomputed.items():
    if k not in prod:
        key_mismatch.append({"pair": [str(k[0]), k[1]], "why": "missing in "
                             "output", "events": [[str(a), c] for a, c in evs]})
        continue
    cls, ann, dist = prod[k]
    same_class = [(a, c) for a, c in evs if c == cls]
    if not same_class:
        ann_mismatch.append({"pair": [str(k[0]), k[1]], "why": "class not in "
                             "window events", "expected": cls,
                             "events": [[str(a), c] for a, c in evs]})
        continue
    nearest = max(a for a, _c in same_class)
    if nearest != ann or dist != idx[k[0]] - idx[ann]:
        ann_mismatch.append({"pair": [str(k[0]), k[1]], "expected_ann":
                             str(nearest), "got_ann": str(ann),
                             "expected_dist": idx[k[0]] - idx[nearest],
                             "got_dist": dist})
extra = [{"pair": [str(t), s], "class": c} for (t, s), (c, _a, _d) in
         prod.items() if (t, s) not in recomputed]
out["V1_flags_forward_recomputation"] = {
    "pairs_producer": len(prod), "pairs_recomputed_in_composite":
        len(recomputed),
    "pairs_missing_in_output": len(key_mismatch),
    "pairs_with_ann_mismatch": len(ann_mismatch),
    "pairs_extra_in_output_not_reachable": len(extra),
    "out_of_composite_occurrences_recomputed": excluded_occurrences,
    "out_of_composite_occurrences_producer_diagnostic": diag,
    "out_of_composite_matches": excluded_occurrences == diag,
    "examples": (key_mismatch + ann_mismatch + extra)[:5],
    "pass": (not key_mismatch and not ann_mismatch and not extra
             and excluded_occurrences == diag)}
print("V1", json.dumps({k: v for k, v in
                        out["V1_flags_forward_recomputation"].items()
                        if k != "examples"}))

# --- V2 composite adjustment identity --------------------------------------
cA = pl.read_parquet(RUN_DIR / "outputs/composite_A.parquet")
cB = pl.read_parquet(RUN_DIR / "outputs/composite_B.parquet")
cC = pl.read_parquet(RUN_DIR / "outputs/composite_C.parquet")
flags = {(r["signal_date"], r["symbol"]): r["class"]
         for r in consumed.iter_rows(named=True)}
badA, badB, bad_key = [], [], []
seen = set()
for df in (cA, cB, cC):
    if set(df.columns) != {"symbol", "signal_date", "value"}:
        bad_key.append(f"schema {df.columns}")
for r in cA.iter_rows(named=True):
    k = (r["signal_date"], r["symbol"])
    v, vb = float(r["value"]), base_map.get(k)
    if vb is None:
        bad_key.append(k)
        continue
    cls = flags.get(k)
    want = {"impairment": FROZEN_B, "price_up": -FROZEN_B}.get(cls, 0.0)
    if abs((v - vb) - want) > 1e-15:
        badA.append({"pair": [str(k[0]), k[1]], "delta": v - vb, "want": want,
                     "class": cls})
for r in cB.iter_rows(named=True):
    k = (r["signal_date"], r["symbol"])
    v, vb = float(r["value"]), base_map.get(k)
    if vb is None:
        bad_key.append(k)
        continue
    if flags.get(k) == "price_up":
        if v != -10.0:
            badB.append({"pair": [str(k[0]), k[1]], "value": v})
    elif v != vb:
        badB.append({"pair": [str(k[0]), k[1]], "value": v, "base": vb,
                     "class": flags.get(k)})
n_flag_rows = sum(1 for k in [(r["signal_date"], r["symbol"])
                              for r in cA.iter_rows(named=True)]
                  if k in flags)
out["V2_composite_adjustment"] = {
    "rows": cA.height, "flagged_rows_from_output": n_flag_rows,
    "key_or_schema_problems": len(bad_key),
    "A_rows_violating_value_plus_b": len(badA),
    "B_rows_violating_suppression": len(badB),
    "examples": (badA[:3] + badB[:3]),
    "pass": not bad_key and not badA and not badB}
print("V2", json.dumps({k: v for k, v in
                        out["V2_composite_adjustment"].items()
                        if k != "examples"}))

# --- V3 sleeve membership rebuilt independently ----------------------------
_ind = pl.read_csv(INDUSTRY_CSV)
_ind = _ind.with_columns(
    (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
     + "." + pl.col("ts_code").str.split(".").list.first()).alias("sym"))
IND = dict(zip(_ind["sym"].to_list(), _ind["l1_name"].to_list()))
ind_of = lambda s: IND.get(s, "UNMAPPED")  # noqa: E731
v3 = {}
for tag in ARMS:
    df = pl.read_parquet(Path(json.loads((SUBRUNS / tag / "stats.json")
                                         .read_text(encoding="utf-8"))
                              ["composite"]["path"]))
    by_day: dict[date, dict[str, float]] = {}
    for r in df.iter_rows(named=True):
        by_day.setdefault(r["signal_date"], {})[r["symbol"]] = float(r["value"])
    ranked = {t: sorted(by_day[t], key=lambda s: (-by_day[t][s], s))
              for t in sig_days}
    members: list[str] = []
    log_ = json.loads((SUBRUNS / tag / "stats.json")
                      .read_text(encoding="utf-8"))["sleeve"]["log"]
    by_month = {date.fromisoformat(e["month"]): e for e in log_}
    bad = []
    for t in sig_days:
        rm = {s: i + 1 for i, s in enumerate(ranked[t])}
        kept = [m for m in members if m in rm and rm[m] <= 2 * SLEEVE_K]
        cnt: dict[str, int] = {}
        for m in kept:
            cnt[ind_of(m)] = cnt.get(ind_of(m), 0) + 1
        seats, entrants = SLEEVE_K - len(kept), []
        for c in ranked[t][:SLEEVE_K]:
            if seats <= 0:
                break
            if c in kept or c in entrants:
                continue
            if cnt.get(ind_of(c), 0) >= IND_CAP:
                continue
            entrants.append(c)
            cnt[ind_of(c)] = cnt.get(ind_of(c), 0) + 1
            seats -= 1
        new = kept + entrants
        if sorted(new) != sorted(by_month[t]["members"]):
            bad.append({"month": str(t),
                        "recomputed": sorted(new),
                        "logged": sorted(by_month[t]["members"])})
        members = list(new)
    v3[tag] = {"months": len(sig_days), "months_mismatching": len(bad),
               "examples": bad[:3], "pass": not bad}
    print("V3", tag, json.dumps({k: v for k, v in v3[tag].items()
                                 if k != "examples"}))
out["V3_sleeve_membership"] = v3

# --- V4 headline metrics recomputed from the equity curve ------------------
v4 = {}
for tag in ARMS + ["F3R4-LZO"]:
    st = json.loads((SUBRUNS / tag / "stats.json").read_text(encoding="utf-8"))
    eq = pl.read_parquet(SUBRUNS / tag / "daily_equity.parquet")
    rows = [(d, float(v)) for d, v in zip(eq["date"].to_list(),
                                          eq["equity"].to_list())
            if date(2015, 1, 5) <= d <= date(2020, 12, 31)]
    d0, v0 = rows[0]
    d1, v1 = rows[-1]
    years = (d1 - d0).days / 365.25
    cagr = (v1 / v0) ** (1.0 / years) - 1.0
    peak, mdd = v0, 0.0
    for _d, v in rows:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    m = st["metrics"]
    v4[tag] = {
        "cagr_recomputed": cagr, "cagr_metric": m["net_cagr"],
        "cagr_abs_diff": abs(cagr - m["net_cagr"]),
        "mdd_recomputed": mdd, "mdd_metric": m["max_drawdown"],
        "mdd_abs_diff": abs(mdd - m["max_drawdown"]),
        "rows": len(rows),
        "pass": abs(cagr - m["net_cagr"]) < 1e-12
                and abs(mdd - m["max_drawdown"]) < 1e-12}
    print("V4", tag, json.dumps({k: v for k, v in v4[tag].items()}))
out["V4_headline_metrics"] = v4

# --- V5 adjudication arithmetic --------------------------------------------
line, floor = BASE_CAGR + 0.003, BASE_MDD - 0.01
v5 = {}
for tag in ARMS:
    m = json.loads((SUBRUNS / tag / "stats.json")
                   .read_text(encoding="utf-8"))["metrics"]
    v5[tag] = {"net_cagr": m["net_cagr"], "max_drawdown": m["max_drawdown"],
               "cagr_ge_line": m["net_cagr"] >= line,
               "mdd_ge_floor": m["max_drawdown"] >= floor,
               "pass": bool(m["net_cagr"] >= line
                            and m["max_drawdown"] >= floor)}
out["V5_adjudication_arithmetic"] = {"line": line, "floor": floor, "arms": v5,
                                     "any_pass": any(x["pass"]
                                                     for x in v5.values())}
print("V5", json.dumps(v5))
out["verdict"] = {"all_checks_pass": all(
    [out["V1_flags_forward_recomputation"]["pass"],
     out["V2_composite_adjustment"]["pass"],
     *[v3[t]["pass"] for t in ARMS], *[v4[t]["pass"] for t in v4],
     any(x["pass"] for x in v5.values())]),
    "V1": out["V1_flags_forward_recomputation"]["pass"],
    "V2": out["V2_composite_adjustment"]["pass"],
    "V3": all(v3[t]["pass"] for t in ARMS),
    "V4": all(v4[t]["pass"] for t in v4),
    "V5_any_arm_passes": any(x["pass"] for x in v5.values())}
out["status"] = "completed"
(RUN_DIR / "tmp/verify_independent.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8", newline="\n")
print("VERDICT", json.dumps(out["verdict"]))
