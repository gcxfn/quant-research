# -*- coding: utf-8 -*-
"""P2-R7 review script A: gate re-implementation, key recalcs, tradeoff,
negative cash, voided-run comparison, val/test non-consumption, doc stats.
Read-only; writes nothing outside tmp output to stdout."""
import json
from datetime import date

import polars as pl

RUN = "artifacts/runs/20260918T004441-p2r7-etf-exposure-d01f4e7a/"
VOID = "artifacts/runs/20260918T003816-p2r7-etf-exposure-93d0523e/"
P2R6 = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d/"
DEV0, DEV1 = date(2016, 1, 1), date(2020, 12, 31)

M = json.load(open(RUN + "metrics.json", encoding="utf-8"))
MV = json.load(open(VOID + "metrics.json", encoding="utf-8"))
M6 = json.load(open(P2R6 + "metrics.json", encoding="utf-8"))
EQ = pl.read_parquet(RUN + "equity_curves.parquet")
TR = pl.read_parquet(RUN + "trades.parquet")
PO = pl.read_parquet(RUN + "positions.parquet")

CFGS = [f"C{i:02d}" for i in range(1, 13)]
MECH = {c: M["configs"][c]["mech"] for c in CFGS}
NN = {c: M["configs"][c]["N"] for c in CFGS}
B1M_DEV = {m: M["benchmarks"]["B1"][m]["dev"] for m in ("FIX", "VOLT", "TREND")}

# doc table (exp-20260917-p2r7-etf-exposure.md section 3), hard-coded claims:
# (gross%, net%, b1m%, exc_pp, gross_exc_pp, pos_years, mdd%, b1m_mdd%, tomax%,
#  top1, top3, top5, pass_count, failed_set)
DOC = {
 "C01": (13.7, 13.6, 7.7, 5.9, 5.0, 5, -25.3, -21.4, 561, .22, .53, .74, 7, {4}),
 "C02": (11.7, 11.6, 8.1, 3.5, 2.6, 4, -24.8, -26.3, 528, .17, .48, .71, 7, {4}),
 "C03": (10.8, 10.7, 6.7, 4.0, 3.2, 5, -25.3, -15.0, 521, .22, .50, .70, 7, {4}),
 "C04": (9.0, 8.9, 7.7, 1.2, 0.3, 3, -22.3, -21.4, 621, .20, .51, .77, 4, {2, 3, 4, 5}),
 "C05": (8.3, 8.2, 8.1, 0.1, -0.7, 3, -26.1, -26.3, 577, .20, .54, .77, 4, {2, 3, 4, 7}),
 "C06": (7.8, 7.7, 6.7, 1.0, 0.1, 4, -25.8, -15.0, 670, .21, .58, .82, 4, {2, 4, 5, 7}),
 "C07": (15.4, 15.3, 7.7, 7.6, 6.7, 3, -25.6, -21.4, 519, .21, .55, .81, 6, {3, 4}),
 "C08": (13.2, 13.1, 8.1, 5.1, 4.2, 4, -24.8, -26.3, 491, .20, .51, .76, 7, {4}),
 "C09": (14.2, 14.1, 6.7, 7.4, 6.5, 4, -25.6, -15.0, 477, .22, .55, .78, 7, {4}),
 "C10": (13.0, 12.9, 7.7, 5.2, 4.3, 3, -22.5, -21.4, 420, .15, .39, .59, 6, {3, 4}),
 "C11": (11.3, 11.2, 8.1, 3.1, 2.2, 3, -26.5, -26.3, 455, .14, .36, .56, 6, {3, 4}),
 "C12": (12.7, 12.6, 6.7, 5.9, 5.0, 4, -25.9, -15.0, 494, .18, .45, .67, 7, {4}),
}
CTRL = {"C02": "C01", "C03": "C01", "C05": "C04", "C06": "C04",
        "C08": "C07", "C09": "C07", "C11": "C10", "C12": "C10"}

print("=" * 30, "A1 curve-derived metrics vs metrics.json", "=" * 30)


def curve(cid):
    d = EQ.filter(pl.col("config_id") == cid).sort("session")
    return (d["session"].to_list(), d["equity_net"].to_list(),
            d["equity_gross"].to_list())


def cagr(v0, v1, d0, d1):
    if v0 <= 0 or v1 <= 0:
        return -1.0
    yrs = (d1 - d0).days / 365.25
    return (v1 / v0) ** (1.0 / yrs) - 1.0


def mdd(vals):
    peak = vals[0]
    m = 0.0
    pi = ti = 0
    for i, v in enumerate(vals):
        if v > peak:
            peak = v
            pi = i
        dd = v / peak - 1.0 if peak > 0 else 0.0
        if dd < m:
            m, pi, ti = dd, pi, i
    return m


def yr_rets(sessions, vals, y0, y1):
    marks = {}
    for d, v in zip(sessions, vals):
        if y0 <= d.year <= y1:
            marks[d.year] = v
    out, prev = {}, vals[[i for i, d in enumerate(sessions)
                          if d.year <= y1][0]]
    prev_idx = min(i for i, d in enumerate(sessions) if d.year >= y0) - 1
    prev = vals[prev_idx]
    for y in sorted(marks):
        out[y] = marks[y] / prev - 1.0
        prev = marks[y]
    return out


curve_issues = []
recomp = {}
for c in CFGS + ["B1-FIX", "B1-VOLT", "B1-TREND", "B1-100", "B1-FIX-gross",
                 "B1-VOLT-gross", "B1-TREND-gross", "B1-100-gross"]:
    s, vn, vg = curve(c)
    is_b1g = c.endswith("-gross")
    cid_key = "B1-" + c.split("-")[1] if is_b1g else c
    if is_b1g and vg[0] is None:
        curve_issues.append((c, "gross_curve_all_null"))
        continue
    assert len(s) == 2187 and s[0] == date(2016, 1, 4) and s[-1] == date(2024, 12, 31)
    dev_i = [i for i, d in enumerate(s) if DEV0 <= d <= DEV1]
    i0, i1 = dev_i[0], dev_i[-1]
    if is_b1g:  # gross curve is carried in equity_net of the -gross series
        gv = vn
        rec = {"net_cagr": None,
               "gross_cagr": cagr(gv[i0], gv[i1], s[i0], s[i1]),
               "net_total": None, "mdd": None}
    else:
        rec = {"net_cagr": cagr(vn[i0], vn[i1], s[i0], s[i1]),
               "gross_cagr": (cagr(vg[i0], vg[i1], s[i0], s[i1])
                              if vg[i0] is not None else None),
               "net_total": vn[i1] / vn[i0] - 1.0,
               "mdd": mdd(vn[i0:i1 + 1])}
    recomp[c] = rec
    if c in CFGS:
        mm = M["configs"][c]["dev"]
        for k, rk in (("net_cagr", "net_cagr"), ("gross_cagr", "gross_cagr"),
                      ("max_drawdown", "mdd")):
            if mm[k] != rec[rk]:
                curve_issues.append((c, k, mm[k], rec[rk]))
        if mm["net_total_return"] != rec["net_total"]:
            curve_issues.append((c, "net_total_return", mm["net_total_return"],
                                 rec["net_total"]))
    else:
        mname = c.replace("B1-", "")
        base = mname[:-6] if is_b1g else mname
        mm = (B1M_DEV[base] if base != "100"
              else M["benchmarks"]["B1"]["100"]["dev"])
        if is_b1g:
            pairs = (("gross_cagr", "gross_cagr"),)
        else:
            pairs = (("net_cagr", "net_cagr"), ("max_drawdown", "mdd"))
        for k, rk in pairs:
            if abs(mm[k] - rec[rk]) > 1e-12:
                curve_issues.append((c, k, mm[k], rec[rk]))
        if not is_b1g and abs(mm["net_total_return"] - rec["net_total"]) > 1e-12:
            curve_issues.append((c, "net_total_return", mm["net_total_return"],
                                 rec["net_total"]))
print("curve recompute mismatches (metrics vs curve):", curve_issues or "NONE")

print()
print("=" * 30, "A2 independent 8-gate eval, all 12 configs", "=" * 30)
# B3prime mean recomputed from per_seed list
b3_mean = {}
for k, v in M.items():
    if k.startswith("B3prime_"):
        mech, n = k.split("_")[1], int(k.split("_N")[1])
        seeds = v["per_seed"]
        vals = [seeds[s]["dev_net_cagr"] if isinstance(seeds[s], dict)
                else seeds[s] for s in seeds]
        m_calc = sum(vals) / len(vals)
        b3_mean[(mech, n)] = (m_calc, v["mean_net_cagr"])
        flag = "OK" if abs(m_calc - v["mean_net_cagr"]) < 1e-12 else "MISMATCH"
        print(f"B3prime {mech} N{n}: recomputed mean {m_calc:.6f} vs stored "
              f"{v['mean_net_cagr']:.6f} [{flag}] n={len(vals)}")

doc_gate_issues = []
store_gate_issues = []
summary = {}
for c in CFGS:
    d = M["configs"][c]["dev"]
    mech, n = MECH[c], NN[c]
    b1 = B1M_DEV[mech]
    g = {}
    g[1] = d["net_cagr"] > 0.0
    g[2] = (d["net_cagr"] - b1["net_cagr"]) >= 0.020
    pos_years = sum(1 for y, x in d["excess_by_year"].items() if x > 0)
    g[3] = pos_years >= 4
    g[4] = (d["max_drawdown"] >= -0.20) and (d["max_drawdown"] >= b1["max_drawdown"])
    g[5] = d["max_one_side_turnover"] <= 12.0 and d["max_one_side_turnover"] <= 6.0
    g[6] = d["concentration"]["top1_share"] <= 0.40 and \
        d["concentration"]["top3_share"] <= 0.70
    g[7] = d["net_cagr"] >= b3_mean[(mech, n)][0] + 0.010
    g[8] = d["execution_rate_dev_window"]["execution_rate"] >= 0.95
    failed = {k for k in range(1, 9) if not g[k]}
    npass = 8 - len(failed)
    summary[c] = (npass, failed)
    # vs metrics gates block
    mg = M["gates"][c]["dev"]
    stored_failed = {int(k.split("_")[0]) for k, v in mg.items()
                     if k[0].isdigit() and v is False}
    if stored_failed != failed:
        store_gate_issues.append((c, "failed_set", failed, stored_failed))
    if mg["dev_excess_vs_b1"] != d["net_cagr"] - b1["net_cagr"]:
        store_gate_issues.append((c, "dev_excess", d["net_cagr"] - b1["net_cagr"],
                                  mg["dev_excess_vs_b1"]))
    if mg["positive_years"] != pos_years:
        store_gate_issues.append((c, "pos_years", pos_years, mg["positive_years"]))
    if bool(mg["dev_pass"]) != (len(failed) == 0):
        store_gate_issues.append((c, "dev_pass_flag"))
    # vs doc table
    dc = DOC[c]
    if dc[12] != npass or dc[13] != failed:
        doc_gate_issues.append((c, "doc", npass, failed, dc[12], dc[13]))
    if abs(dc[3] - (d["net_cagr"] - b1["net_cagr"]) * 100) > 0.05:
        doc_gate_issues.append((c, "doc_excess_pp", d["net_cagr"] - b1["net_cagr"] * 1, dc[3]))
    if dc[5] != pos_years:
        doc_gate_issues.append((c, "doc_pos_years", pos_years, dc[5]))
    if abs(dc[6] - d["max_drawdown"] * 100) > 0.05:
        doc_gate_issues.append((c, "doc_mdd", d["max_drawdown"], dc[6]))
    if abs(dc[7] - b1["max_drawdown"] * 100) > 0.05:
        doc_gate_issues.append((c, "doc_b1_mdd", b1["max_drawdown"], dc[7]))
    if abs(dc[8] - d["max_one_side_turnover"] * 100) > 0.5:
        doc_gate_issues.append((c, "doc_turnover", d["max_one_side_turnover"], dc[8]))
    if abs(dc[0] - d["gross_cagr"] * 100) > 0.05 or abs(dc[1] - d["net_cagr"] * 100) > 0.05:
        doc_gate_issues.append((c, "doc_cagr", d["net_cagr"], d["gross_cagr"], dc[0], dc[1]))
    if abs(dc[2] - b1["net_cagr"] * 100) > 0.05:
        doc_gate_issues.append((c, "doc_b1m_net", b1["net_cagr"], dc[2]))
    if abs(dc[9] - d["concentration"]["top1_share"]) > 0.005 or \
       abs(dc[10] - d["concentration"]["top3_share"]) > 0.005:
        doc_gate_issues.append((c, "doc_conc", d["concentration"], dc[9], dc[10]))
    if abs(dc[4] - (d["gross_cagr"] - b1["gross_cagr"]) * 100) > 0.05:
        doc_gate_issues.append((c, "doc_gross_exc", d["gross_cagr"] - b1["gross_cagr"], dc[4]))

print("my 12 verdicts (pass_count, failed_set):")
for c in CFGS:
    print(f"  {c}: {summary[c][0]}/8 fails={sorted(summary[c][1])}")
print("metrics-stored gate discrepancies:", store_gate_issues or "NONE")
print("doc-table discrepancies:", doc_gate_issues or "NONE")

print()
print("=" * 30, "A3 gate-7 margins (net_cagr - b3_mean - 0.01)", "=" * 30)
for c in CFGS:
    d = M["configs"][c]["dev"]
    mech, n = MECH[c], NN[c]
    bm = b3_mean[(mech, n)][0]
    print(f"  {c} ({mech},N{n}): net={d['net_cagr']:.6f} b3m={bm:.6f} "
          f"margin={d['net_cagr'] - bm - 0.010:+.6f} ({(d['net_cagr'] - bm - 0.010)*100:+.4f}pp) "
          f"gate7={'PASS' if d['net_cagr'] >= bm + 0.010 else 'FAIL'}")

print()
print("=" * 30, "A4 C01 key numbers", "=" * 30)
c = "C01"
d = M["configs"][c]["dev"]
print(json.dumps({k: d[k] for k in ("net_cagr", "gross_cagr", "b1m_net_cagr",
      "excess_vs_b1m", "gross_excess_vs_b1m", "max_drawdown", "mdd_window",
      "b1m_max_drawdown", "execution_rate_dev_window", "execution_rate_full_window",
      "max_one_side_turnover", "concentration", "monthly_top_decile")},
      ensure_ascii=False, indent=1))
print("excess_by_year C01:", d["excess_by_year"])
print("net_return_by_year C01:", d["net_return_by_year"])

print()
print("=" * 30, "A5 tradeoff saved/lost recompute", "=" * 30)
tol_issues = []
for row in M["mechanism_tradeoff_vs_fix"]:
    mech, cid, ctrl = row["mech"], row["config_id"], CTRL[row["config_id"]]
    # registered convention: positive saved = shallower than FIX control
    saved = (M["configs"][cid]["dev"]["max_drawdown"]
             - M["configs"][ctrl]["dev"]["max_drawdown"]) * 100
    lost = (M["configs"][ctrl]["dev"]["net_cagr"]
            - M["configs"][cid]["dev"]["net_cagr"]) * 100
    ratio = saved / lost if lost else float("nan")
    ok1 = abs(saved - row["saved_drawdown_pp"]) < 0.005
    ok2 = abs(lost - row["lost_net_cagr_pp"]) < 0.005
    print(f"  {row['pair']} {mech} ({cid} vs {ctrl}): saved {saved:+.2f}pp "
          f"(stored {row['saved_drawdown_pp']:+.2f}) lost {lost:+.2f}pp "
          f"(stored {row['lost_net_cagr_pp']:+.2f}) ratio {ratio:+.3f} "
          f"(stored {row['saved_per_lost']:+.3f})")
    if not (ok1 and ok2):
        tol_issues.append(cid)
print("tradeoff recompute mismatches:", tol_issues or "NONE")
ratios = [(r["config_id"], r["saved_per_lost"]) for r in M["mechanism_tradeoff_vs_fix"]]
pos = [r for _, r in ratios if r > 0]
print("all ratios <= 0.34 or negative:",
      all(r <= 0.344 for _, r in ratios),
      "| max positive ratio:", max(pos))
n5 = [r["saved_drawdown_pp"] for r in M["mechanism_tradeoff_vs_fix"]
      if r["pair"].endswith("N5")]
print("N=5 deeper-than-FIX pp:", n5, "in 3.3..4.0 band:",
      all(-4.05 <= x <= -3.25 for x in n5))

print()
print("=" * 30, "A6 negative cash / cash-capped", "=" * 30)
bad = []
for c in CFGS:
    cm = M["configs"][c]
    es = cm["exec_stats"]
    if cm["max_negative_cash"] != 0.0 or es["buys_cash_capped"] != 0:
        bad.append((c, cm["max_negative_cash"], es["buys_cash_capped"]))
    t = TR.filter(pl.col("config_id") == c)
    assert t["status"].unique().to_list() == ["filled"], c
print("max_negative_cash!=0 or capped>0:", bad or "NONE (all 12 zero)")
print("trade statuses all 'filled'; total rows:",
      TR.height, "| cash-cap-like kind values:", TR["kind"].unique().to_list())

print()
print("=" * 30, "A7 voided 93d0523e vs final d01f4e7a (strategy side)", "=" * 30)
mism = []
for c in CFGS:
    a, b = MV["configs"][c], M["configs"][c]
    for k in ("net_cagr", "gross_cagr", "net_total_return", "gross_total_return",
              "max_drawdown", "net_return_by_year", "gross_return_by_year",
              "max_one_side_turnover", "concentration"):
        if a["dev"][k] != b["dev"][k]:
            mism.append((c, k))
    for k in ("n_trades", "max_negative_cash", "freq", "W", "N", "mech"):
        if a[k] != b[k]:
            mism.append((c, k))
print("strategy-side mismatches (voided vs final):", mism or
      "NONE - 12 configs bit-identical on dev net/gross CAGR, mdd, yearly, "
      "turnover, concentration, n_trades")
print("gate-3 flags voided vs final (consumes B1(m) yearly excess):")
for c in CFGS:
    mv_ = MV["gates"][c]["dev"]["3_positive_years_ge_4_of_5"]
    mf_ = M["gates"][c]["dev"]["3_positive_years_ge_4_of_5"]
    if mv_ != mf_:
        print(f"  {c}: voided {mv_} -> final {mf_}")
print("B1(m) dev net_cagr voided vs final:")
for mech in ("FIX", "VOLT", "TREND"):
    print(f"  {mech}: voided {MV['benchmarks']['B1'][mech]['dev']['net_cagr']:+.4f} "
          f"-> final {M['benchmarks']['B1'][mech]['dev']['net_cagr']:+.4f}")
# gross trade series parity with voided trades (bit-identical strategy side)
TV = pl.read_parquet(VOID + "trades.parquet")
same = TR.filter(pl.col("config_id").is_in(CFGS)).equals(
    TV.filter(pl.col("config_id").is_in(CFGS)).sort(TR.columns)
    if TV.filter(pl.col("config_id").is_in(CFGS)).shape != TR.filter(
        pl.col("config_id").is_in(CFGS)).shape or not
    TR.filter(pl.col("config_id").is_in(CFGS)).equals(
        TV.filter(pl.col("config_id").is_in(CFGS)))
    else TV.filter(pl.col("config_id").is_in(CFGS)))
print("trades.parquet C01-C12 frames bit-identical:", same)
PV = pl.read_parquet(VOID + "positions.parquet")
sameP = PO.filter(pl.col("config_id").is_in(CFGS)).equals(
    PV.filter(pl.col("config_id").is_in(CFGS)))
print("positions.parquet C01-C12 frames bit-identical:", sameP)

print()
print("=" * 30, "A8 val/test non-consumption", "=" * 30)
print("gates keys per config:", sorted(M["gates"]["C01"].keys()),
      "| any val/test gate block:",
      any(k != "dev" for c in CFGS for k in M["gates"][c]))
print("dev_pass_configs:", M["dev_pass_configs"],
      "| advanced_to_validation:", M["advanced_to_validation"],
      "| p3_candidates:", M["p3_candidates"])
has_val_blocks = {c: sorted(M["configs"][c]["validation"].keys()) == sorted(
    M["configs"][c]["test"].keys()) for c in CFGS}
print("val/test blocks computed-and-archived (per disclosure): all 12:",
      all(has_val_blocks.values()))
# equity/trades contain 2021+ rows (continuous sim) but no decision fields
n2021_tr = TR.filter(pl.col("session") >= date(2021, 1, 1)).height
print(f"trades rows 2021+ (archived, continuous sim): {n2021_tr}; "
      "decision records (gates/advancement) reference dev only")

print()
print("=" * 30, "A9 doc statistics trace", "=" * 30)
mdds = [M["configs"][c]["dev"]["max_drawdown"] for c in CFGS]
print(f"S1 dev mdd range: {min(mdds)*100:.1f}% .. {max(mdds)*100:.1f}% "
      "(doc: -22.3%..-26.5%)")
wins = {(M["configs"][c]["dev"]["mdd_window"]["peak_date"],
         M["configs"][c]["dev"]["mdd_window"]["trough_date"]) for c in CFGS}
print(f"S2 mdd windows all 2020-02-25->2020-04-01: {wins}")
ers = [M["configs"][c]["dev"]["execution_rate_dev_window"]["execution_rate"] for c in CFGS]
print(f"S3 dev-window exec rate: {min(ers):.4f}..{max(ers):.4f} (doc 0.992-0.995)")
lp_dev = [M["configs"][c]["dev"]["execution_rate_dev_window"]["legs_planned"] for c in CFGS]
le_dev = [M["configs"][c]["dev"]["execution_rate_dev_window"]["legs_executed"] for c in CFGS]
notex = [p_ - e_ for p_, e_ in zip(lp_dev, le_dev)]
print(f"S3b dev-window planned legs {min(lp_dev)}..{max(lp_dev)} (doc 160-261); "
      f"not-executed {min(notex)}..{max(notex)} (doc 1-2)")
ers_f = [M["configs"][c]["dev"]["execution_rate_full_window"] for c in CFGS]
print(f"    full-window exec rate: {min(ers_f):.4f}..{max(ers_f):.4f} (doc 0.997-0.998)")
lp = [M["configs"][c]["exec_stats"]["legs_planned"] for c in CFGS]
print(f"S4 full-window legs_planned (exec_stats): {min(lp)}..{max(lp)}")
print(f"S5 parity 12/12:", all(M["net_gross_parity"][c] is True for c in CFGS),
      M["net_gross_parity"])
eb = [M["configs"][c]["exec_stats"]["entry_limit_blocked"] for c in CFGS]
xb = [M["configs"][c]["exec_stats"]["exit_limit_blocked"] for c in CFGS]
print(f"S6 limit blocked buys {min(eb)}..{max(eb)} (doc 87-93), sells {min(xb)}..{max(xb)} (doc 1-2)")
fd = [M["configs"][c]["exec_stats"]["sells_forced_delist"] for c in CFGS]
print(f"S7 forced delist exits: {set(fd)} (doc 0)")
open_end = (PO.filter(pl.col("config_id").is_in(CFGS))
            .group_by("config_id").agg(pl.col("exit_date").null_count().alias("n"))
            .sort("config_id"))
print("S8 open-at-end positions per config (doc: 3 for N=3, 5 for N=5):")
print(open_end)
td = [M["configs"][c]["dev"]["monthly_top_decile"]["top_decile_share"] for c in CFGS]
print(f"S9 monthly top-decile share: {min(td):.3f}..{max(td):.3f} (doc 1.02-1.41)")
ys = M["exposure_paths"]["VOLT"]["years"]
tot = sum(v["n_signal_days"] for v in ys.values())
print(f"S10 total monthly signal days 2016-2024: {tot} (doc 108); "
      "per year:", {y: ys[y]["n_signal_days"] for y in sorted(ys)})
print("S11 B1@100 dev:", M["benchmarks"]["B1"]["100"]["dev"])
print("    P2-R6 B1 monthly dev:", M6["benchmarks"]["B1"]["monthly"]["dev"])
b100, b6 = M["benchmarks"]["B1"]["100"]["dev"], M6["benchmarks"]["B1"]["monthly"]["dev"]
print("    exact-equal net_cagr:", b100["net_cagr"] == b6["net_cagr"],
      "| mdd:", b100["max_drawdown"] == b6["max_drawdown"],
      "| total:", b100["net_total_return"] == b6["net_total_return"],
      "| ulp-level (1e-12):", all(abs(b100[k] - b6[k]) < 1e-12 for k in
      ("net_cagr", "net_total_return", "max_drawdown")))
print("S12 B2 dev net_total:", M["benchmarks"]["B2"]["dev"]["net_total_return"],
      "cagr:", M["benchmarks"]["B2"]["dev"]["net_cagr"],
      "(doc +51.2% / +8.64%) vs P2-R6:",
      M6["benchmarks"]["B2"]["dev"]["net_total_return"])

print()
print("=" * 30, "A10 dev-window planned legs recount from trades+stats", "=" * 30)
# dev-window planned legs = dev signals * N minus buy-no-candidate adjustments;
# executed per stored exec stats; recompute rate = legs_executed/legs_planned
for c in CFGS:
    es = M["configs"][c]["exec_stats"]
    d = M["configs"][c]["dev"]
    print(f"  {c}: planned={es['legs_planned']} executed={es['legs_executed']} "
          f"rate={es['execution_rate']:.4f} "
          f"cancel_busy={es['buys_cancelled_slot_busy']} no_cand={es['buys_no_candidate']} "
          f"pending_end={es['sells_pending_at_end']}")
