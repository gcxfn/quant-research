# -*- coding: utf-8 -*-
"""Exit-layer attribution across baseline replay versions (post-run
analysis, second-review item: the v2->v3 exit-layer move of about
-0.27pp CAGR was unexplained; the review hypothesised K=3 re-arming
forced exits -- test that against the fill ledgers).

Compares FULL-bin sell fills of two runs on (symbol, date, session,
shares):
  * sells by fill_type and intent (fallback story);
  * sells only in the NEW run / only in the OLD run, attributed to exit
    reasons via the NEW run's provider reason log (event-merged: newest
    source <= the fill's decision date), and via fill_type for the OLD
    run (no reason log there);
  * notional totals per reason bucket;
  * exit-layer pp recomputed from each run's FULL / NOSNR daily equity.

Usage: attribution_exit_layer.py <old_run_dir> <new_run_dir> [label]
Writes attribution_<label>.csv next to stdout; all numbers printed as
JSON for the report.  Read-only on the archived runs.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]


def cagr(sessions, equity):
    if len(sessions) < 2 or equity[0] <= 0:
        return float("nan")
    days = (sessions[-1] - sessions[0]).days
    return (equity[-1] / equity[0]) ** (365.25 / max(days, 1)) - 1.0


def load(run: Path, curve: str):
    fills = pl.read_parquet(run / "outputs" / f"{curve}_fills.parquet")
    daily = pl.read_parquet(run / "outputs" / f"{curve}_daily_equity.parquet")
    return fills, daily


def reason_events(run: Path, curve: str):
    """(symbol -> sorted [(source_date, reason, first_key)]) from the
    provider reason log; returns {} when the run has no log (v2)."""
    p = run / "outputs" / f"{curve}_exit_reason_log.csv"
    if not p.exists():
        return {}
    log = pl.read_csv(p)
    events: dict[str, list] = {}
    for r in log.iter_rows(named=True):
        events.setdefault(r["symbol"], []).append(
            (date.fromisoformat(r["source"]), r["reason"],
             r["day"] + r["sess"]))
    for v in events.values():
        v.sort()
    return events


def attribute(events, symbol, decision_date):
    best = None
    for src_d, rsn, first_key in events.get(symbol, []):
        if src_d <= decision_date:
            if best is None or (src_d, first_key) > (best[0], best[2]):
                best = (src_d, rsn, first_key)
    return best[1] if best else "unattributed"


def main(old_dir: str, new_dir: str, label: str) -> None:
    old_run, new_run = ROOT / old_dir, ROOT / new_dir
    old_f, old_d = load(old_run, "FULL-bin")
    new_f, new_d = load(new_run, "FULL-bin")
    ev_new = reason_events(new_run, "FULL-bin")

    def sells_by(f):
        return (f.filter(pl.col("side") == "sell")
                .select("symbol", "date", "session", "shares", "price",
                        "fill_type", "intent", "decision_date")
                .with_columns((
                    pl.col("symbol") + "|" + pl.col("date").cast(pl.String)
                    + "|" + pl.col("session") + "|"
                    + pl.col("shares").cast(pl.String)).alias("key")))

    so, sn = sells_by(old_f), sells_by(new_f)
    old_keys = set(so["key"].to_list())
    new_keys = set(sn["key"].to_list())
    only_new = sn.filter(~pl.col("key").is_in(list(old_keys)))
    only_old = so.filter(~pl.col("key").is_in(list(new_keys)))
    common = len(new_keys & old_keys)

    def bucket(df, use_events):
        rows = []
        for r in df.iter_rows(named=True):
            reason = (attribute(ev_new, r["symbol"], r["decision_date"])
                      if use_events else r["fill_type"])
            rows.append({"reason": reason, "fill_type": r["fill_type"],
                         "intent": r["intent"], "shares": r["shares"],
                         "notional": r["shares"] * r["price"]})
        out: dict = {}
        for r in rows:
            k = f"{r['reason']}/{r['fill_type']}"
            o = out.setdefault(k, {"n": 0, "shares": 0, "notional": 0.0})
            o["n"] += 1
            o["shares"] += r["shares"]
            o["notional"] += r["notional"]
        return out

    # exit-layer pp from each run's own FULL / NOSNR equity paths
    layers = {}
    for tag, run in (("old", old_run), ("new", new_run)):
        _, full_d = load(run, "FULL-bin")
        _, nosnr_d = load(run, "NOSNR-bin")
        f_net = cagr(full_d["date"].to_list(), full_d["equity"].to_list())
        n_net = cagr(nosnr_d["date"].to_list(), nosnr_d["equity"].to_list())
        layers[tag] = {"full_net_cagr": f_net, "nosnr_net_cagr": n_net,
                       "exit_layer_pp": (f_net - n_net) * 100}

    summary = {
        "label": label,
        "old_run": old_dir, "new_run": new_dir,
        "sells": {"old": so.height, "new": sn.height,
                  "common_exact": common,
                  "only_new": only_new.height, "only_old": only_old.height},
        "sells_by_fill_type": {
            "old": (so.group_by("fill_type").len()
                    .sort("fill_type").to_dicts()),
            "new": (sn.group_by("fill_type").len()
                    .sort("fill_type").to_dicts())},
        "sells_by_intent": {
            "old": (so.group_by("intent").len()
                    .sort("intent").to_dicts()),
            "new": (sn.group_by("intent").len()
                    .sort("intent").to_dicts())},
        "only_new_by_reason": bucket(only_new, True),
        "only_old_by_filltype": bucket(only_old, False),
        "only_new_notional_total": float(
            (only_new["shares"] * only_new["price"]).sum()),
        "only_old_notional_total": float(
            (only_old["shares"] * only_old["price"]).sum()),
        "exit_layer": layers,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
    out_csv = new_run / "outputs" / f"attribution_{label}.csv"
    pl.DataFrame([
        {"bucket": k, **v} for k, v in summary["only_new_by_reason"].items()
    ] + [{"bucket": f"OLD-ONLY/{k}", **v} for k, v
          in summary["only_old_by_filltype"].items()]
    ).write_csv(out_csv)
    print("csv:", out_csv)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "x")
