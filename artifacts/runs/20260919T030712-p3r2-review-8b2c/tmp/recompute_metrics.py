# -*- coding: utf-8 -*-
"""Independent recompute of P3R2 run metrics + gate re-judgment.
Reads ONLY: outputs/<cid>_daily_equity.parquet, outputs/<cid>_fills.parquet,
R16 metrics.json (B1/B3' citation source), P3R1 fills (fee delta check),
run metrics_and_gates.json (comparison target).
No run artifact is modified.  Writes result JSON next to this script.
"""
import json
import math
from datetime import date
from pathlib import Path

import polars as pl

RUN = Path(r"D:\量化\artifacts\runs\20260919T030640-p3r2-dev-ad9e")
REVIEW = Path(__file__).resolve().parents[1]
R16_RUN = Path(r"D:\量化\artifacts\runs\20260918T083650-p2r16-trend-dispersion-afab466f")
P3R1_RUN = Path(r"D:\量化\artifacts\runs\20260918T145900-p3r1-dev-262f")
CIDS = [f"C{i:02d}" for i in range(1, 9)]
B3P_PATH = {"C01": "T200-40", "C02": "T200-40", "C03": "FIX75", "C04": "FIX75",
            "C05": "T200-40", "C06": "T200-40", "C07": "FIX75", "C08": "FIX75"}

r16 = json.loads((R16_RUN / "metrics.json").read_text(encoding="utf-8"))
B3P = r16["B3prime_dev_mean_net_cagr"]
mg = json.loads((RUN / "outputs" / "metrics_and_gates.json").read_text(encoding="utf-8"))

out = {}
for cid in CIDS:
    de = pl.read_parquet(RUN / "outputs" / f"{cid}_daily_equity.parquet").sort("date")
    fills = pl.read_parquet(RUN / "outputs" / f"{cid}_fills.parquet")
    d = de["date"].to_list()
    v = de["equity"].to_list()
    assert d == sorted(d) and len(d) == len(set(d)), "equity not strictly increasing by date"
    v0, v1 = v[0], v[-1]
    d0, d1 = d[0], d[-1]
    total_ret = v1 / v0 - 1.0
    days = (d1 - d0).days
    cagr_36525 = (v1 / v0) ** (365.25 / days) - 1.0
    cagr_365 = (v1 / v0) ** (365.0 / days) - 1.0
    n_sess = len(v)
    # trading-day annualization variants (report only if compared)
    cagr_244 = (v1 / v0) ** (244.0 / n_sess) - 1.0
    cagr_252 = (v1 / v0) ** (252.0 / n_sess) - 1.0
    # max drawdown on daily close equity
    peak = -1.0
    mdd = 0.0
    for x in v:
        if x > peak:
            peak = x
        dd = x / peak - 1.0
        if dd < mdd:
            mdd = dd
    # yearly returns (first year starts at first curve value -- same convention
    # as er.year_runs / er.year_returns in the run; independent re-impl)
    marks = {}
    for di, vi in zip(d, v):
        marks[di.year] = vi
    yr = {}
    prev = v0
    for y in sorted(marks):
        yr[y] = marks[y] / prev - 1.0
        prev = marks[y]
    # turnover: buy notional by year / mean daily equity of that year
    yy = de.with_columns(pl.col("date").dt.year().alias("y"))
    mean_eq = {int(r["y"]): float(r["e"]) for r in yy.group_by("y")
               .agg(pl.col("equity").mean().alias("e")).iter_rows(named=True)}
    buy_by = {int(r["y"]): float(r["n"]) for r in fills.filter(pl.col("side") == "buy")
              .with_columns(pl.col("date").dt.year().alias("y"))
              .group_by("y").agg(pl.col("notional").sum().alias("n"))
              .iter_rows(named=True)}
    sell_by = {int(r["y"]): float(r["n"]) for r in fills.filter(pl.col("side") == "sell")
               .with_columns(pl.col("date").dt.year().alias("y"))
               .group_by("y").agg(pl.col("notional").sum().alias("n"))
               .iter_rows(named=True)}
    turnover = {y: {"buy_notional": buy_by.get(y, 0.0), "mean_equity": mean_eq[y],
                    "one_side_turnover": buy_by.get(y, 0.0) / mean_eq[y]}
                for y in sorted(mean_eq)}
    max_turn = max(t["one_side_turnover"] for t in turnover.values())
    # fees from fills
    fee = fills.select(
        pl.col("commission").sum().alias("commission"),
        pl.col("stamp_tax").sum().alias("stamp"),
        pl.col("fees_total").sum().alias("fees_total"),
        pl.col("notional").sum().alias("notional_all"),
    ).row(0, named=True)
    buy_notional_total = float(fills.filter(pl.col("side") == "buy")["notional"].sum())
    sell_notional_total = float(fills.filter(pl.col("side") == "sell")["notional"].sum())
    n_fills = fills.height
    # B1 / B3 citations
    b1m = r16["configs"][cid]
    b1y = {int(k): vv for k, vv in b1m["b1m_net_return_by_year"].items()}
    adv = sorted(y for y in yr if y in b1y and yr[y] > b1y[y])
    b1_cagr = b1m["b1m_net_cagr"]
    b1_mdd = b1m["b1m_max_drawdown"]
    excess = cagr_36525 - b1_cagr
    b3 = B3P[B3P_PATH[cid]]
    # gate re-judgment
    g = {
        "1_net_cagr_gt_0": cagr_36525 > 0.0,
        "2_excess_vs_B1m_ge_2pp": excess >= 0.020,
        "3_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
        "4_mdd_le_20pct_and_le_B1m": (abs(mdd) <= 0.20 + 1e-12
                                      and abs(mdd) <= abs(b1_mdd) + 1e-12),
        "5_one_side_turnover_le_6": max_turn <= 6.0,
        "6_single_name_weight_le_40pct": None,  # filled separately (needs closes)
        "7_vs_B3prime_plus_1pp": cagr_36525 >= b3 + 0.010,
    }
    out[cid] = {
        "equity_rows": n_sess, "first_date": d0.isoformat(), "last_date": d1.isoformat(),
        "initial_equity": v0, "final_equity": v1,
        "net_total_return": total_ret,
        "net_cagr_365.25": cagr_36525, "net_cagr_365": cagr_365,
        "net_cagr_244sess": cagr_244, "net_cagr_252sess": cagr_252,
        "max_drawdown": mdd,
        "net_return_by_year": {str(k): yr[k] for k in yr},
        "advantage_years": [int(y) for y in adv],
        "turnover_by_year": {str(y): turnover[y] for y in turnover},
        "max_one_side_turnover": max_turn,
        "fees": {"n_fills": n_fills, "commission": float(fee["commission"]),
                 "stamp": float(fee["stamp"]), "fees_total": float(fee["fees_total"]),
                 "buy_notional_total": buy_notional_total,
                 "sell_notional_total": sell_notional_total},
        "b1_cited": {"net_cagr": b1_cagr, "mdd": b1_mdd,
                     "by_year": {str(k): b1y[k] for k in b1y}},
        "b3prime_cited": b3,
        "excess_vs_b1m": excess,
        "gates_partial": {k: g[k] for k in g if g[k] is not None},
    }

    # comparison vs run claims (bit-level for recomputables)
    mc = mg["metrics"][cid]
    cmp = {
        "net_cagr_match": (cagr_36525 == mc["net_cagr"]),
        "net_cagr_absdiff": cagr_36525 - mc["net_cagr"],
        "net_total_return_match": (total_ret == mc["net_total_return"]),
        "max_drawdown_match": (mdd == mc["max_drawdown"]),
        "excess_match": (excess == mc["excess_vs_b1m"]),
        "year_returns_match": ({str(k): yr[k] for k in yr} ==
                               {str(int(k)): vv for k, vv in mc["net_return_by_year"].items()}),
        "turnover_by_year_match": (all(
            turnover[y]["buy_notional"] == mc["turnover_by_year"][str(y)]["buy_notional"]
            and turnover[y]["mean_equity"] == mc["turnover_by_year"][str(y)]["mean_equity"]
            for y in turnover)),
        "max_one_side_turnover_match": (max_turn == mc["max_one_side_turnover"]),
        "b1m_net_cagr_match": (b1_cagr == mc["b1m_net_cagr"]),
        "b1m_mdd_match": (b1_mdd == mc["b1m_max_drawdown"]),
        "advantage_years_match": ([int(y) for y in adv] ==
                                  [int(y) for y in mc["advantage_years_list"]]),
    }
    out[cid]["comparison"] = cmp
    # P3R1 fee delta check
    f1 = pl.read_parquet(P3R1_RUN / "outputs" / f"{cid}_fills.parquet")
    out[cid]["p3r1_fees_total"] = float(f1["fees_total"].sum())
    out[cid]["p3r1_fees_delta"] = float(fee["fees_total"]) - float(f1["fees_total"].sum())

(REVIEW / "tmp" / "recomputed_metrics.json").write_text(
    json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")

# console summary
print(f"{'cid':4} {'netCAGR':>9} {'runCAGR':>9} {'mdd':>9} {'runMDD':>9} "
      f"{'adv':>4} {'turn':>5} {'fees':>10} {'allmatch':>8}")
for cid in CIDS:
    o = out[cid]
    mc = mg["metrics"][cid]
    am = all(o["comparison"][k] for k in o["comparison"] if k.endswith("match"))
    print(f"{cid:4} {o['net_cagr_365.25']*100:8.4f}% {mc['net_cagr']*100:8.4f}% "
          f"{o['max_drawdown']*100:8.4f}% {mc['max_drawdown']*100:8.4f}% "
          f"{len(o['advantage_years']):3d}/6 {o['max_one_side_turnover']:5.2f} "
          f"{o['fees']['fees_total']:10.2f} {str(am):>8}")
print()
print("gate re-judgment (without gate 6 and 8, recomputed separately):")
hdr = ["1", "2", "3", "4", "5", "7"]
print(f"{'cid':4} " + " ".join(f"g{h}" for h in hdr))
for cid in CIDS:
    gp = out[cid]["gates_partial"]
    print(f"{cid:4} " + " ".join(("P" if gp[f"{h}_net_cagr_gt_0" if h == "1" else
          f"{h}_excess_vs_B1m_ge_2pp" if h == "2" else
          f"{h}_advantage_years_ge_5_of_6" if h == "3" else
          f"{h}_mdd_le_20pct_and_le_B1m" if h == "4" else
          f"{h}_one_side_turnover_le_6" if h == "5" else
          f"{h}_vs_B3prime_plus_1pp"] else "F") for h in hdr))
