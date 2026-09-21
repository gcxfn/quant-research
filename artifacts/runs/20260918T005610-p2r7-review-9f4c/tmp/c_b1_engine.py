# -*- coding: utf-8 -*-
"""P2-R7 review script C: B1(m) engine carry-over check + voided-run
collapse signature. Read-only."""
import json
import math
import os
import statistics
from datetime import date

import polars as pl

ROOT = "D:/量化/"
RUN = ROOT + "artifacts/runs/20260918T004441-p2r7-etf-exposure-d01f4e7a/"
VOID = ROOT + "artifacts/runs/20260918T003816-p2r7-etf-exposure-93d0523e/"
CFG = json.load(open(ROOT + "configs/experiments/p2r7-etf-exposure.json", encoding="utf-8"))
M = json.load(open(RUN + "metrics.json", encoding="utf-8"))
MV = json.load(open(VOID + "metrics.json", encoding="utf-8"))

EQ = pl.read_parquet(RUN + "equity_curves.parquet")
EQV = pl.read_parquet(VOID + "equity_curves.parquet")


def curve(df, cid, col="equity_net"):
    d = df.filter(pl.col("config_id") == cid).sort("session")
    return d["session"].to_list(), d[col].to_list()


# --- rebuild pool returns (same independent chain as script B, condensed) ----
WL = set(CFG["u1_whitelist_frozen"])
FD = ROOT + CFG["data"]["fund_daily"]["batch"] + "/"
FA = ROOT + CFG["data"]["fund_adj"]["batch"] + "/"
frames = []
for p in sorted(os.listdir(FD)):
    if not (p.startswith("chunk_") and p.endswith(".csv")):
        continue
    code = p.removeprefix("chunk_").removesuffix(".csv")
    if code not in WL:
        continue
    d = (pl.read_csv(FD + p, infer_schema_length=0)
         .select("trade_date", "close", "amount")
         .with_columns(pl.col("trade_date").str.to_date("%Y%m%d"),
                       pl.col("close").cast(pl.Float64, strict=False),
                       pl.col("amount").cast(pl.Float64, strict=False)))
    a = (pl.read_csv(FA + p, infer_schema_length=0)
         .select(pl.col("trade_date").str.to_date("%Y%m%d").alias("_ad"),
                 pl.col("adj_factor").cast(pl.Float64, strict=False)).sort("_ad"))
    frames.append(d.sort("trade_date").join_asof(a, left_on="trade_date",
                                                 right_on="_ad", strategy="backward")
                  .with_columns(pl.lit(code).alias("ts_code")))
daily = (pl.concat(frames).sort("ts_code", "trade_date")
         .filter(pl.col("trade_date") <= date(2024, 12, 31)))
reg = (pl.read_csv(ROOT + CFG["data"]["fund_basic"]["batch"] + "/"
                   + CFG["data"]["fund_basic"]["file"], infer_schema_length=0)
       .select("ts_code", "name", "fund_type",
               pl.col("list_date").str.to_date("%Y%m%d", strict=False),
               pl.col("delist_date").str.to_date("%Y%m%d", strict=False))
       .filter(pl.col("ts_code").is_in(sorted(WL))))
name = pl.col("name").fill_null("")
keep = reg.filter(pl.col("fund_type").is_in(CFG["universe"]["u2_category"]["fund_type_in"])
                  & ~pl.any_horizontal([name.str.contains(k, literal=True)
                                        for k in CFG["universe"]["u2_qdii_keywords_frozen"]]))
feat = daily.join(keep.select("ts_code", "list_date", "delist_date"),
                  on="ts_code", how="inner")
feat = feat.with_columns((pl.col("close") * pl.col("adj_factor")).alias("adj_close"),
                         pl.int_range(pl.len()).over("ts_code").add(1).alias("row_idx"))
feat = feat.with_columns(pl.col("amount").rolling_median(20, min_samples=20)
                         .over("ts_code").alias("am20"))
cal = feat.select("trade_date").unique().sort("trade_date").to_series().to_list()
cal_idx = {d: i for i, d in enumerate(cal)}
feat = feat.join(pl.DataFrame({"trade_date": cal,
                               "cal_idx": list(range(len(cal)))}),
                 on="trade_date", how="inner")
lb = (feat.select("ts_code", "list_date").unique().sort("list_date")
      .join_asof(pl.DataFrame({"_lcd": cal, "lci": list(range(len(cal)))}),
                 left_on="list_date", right_on="_lcd", strategy="forward")
      .select("ts_code", "lci"))
feat = feat.join(lb, on="ts_code", how="inner")
feat = feat.with_columns(
    (pl.col("lci").is_not_null() & ((pl.col("cal_idx") - pl.col("lci")) >= 120)
     & (pl.col("delist_date").is_null() | (pl.col("trade_date") < pl.col("delist_date")))
     & (pl.col("row_idx") >= 120) & (pl.col("am20") >= 50000.0)
     & pl.col("adj_close").is_not_null()).alias("eligible"))
pr = (feat.filter(pl.col("eligible")).sort("ts_code", "trade_date")
      .with_columns((pl.col("adj_close")
                     / pl.col("adj_close").shift(1).over("ts_code") - 1.0).alias("_r"))
      .group_by("trade_date").agg(pl.col("_r").mean().alias("pr"))
      .sort("trade_date"))
pool_ret = {d: v for d, v in zip(pr["trade_date"].to_list(), pr["pr"].to_list())
            if v is not None}

# VOLT exposures at every signal day (per script B; matches archived)
sig_days = []
lom = {}
for d in cal:
    lom[(d.year, d.month)] = d
sig_days = sorted(d for d in lom.values() if d >= date(2016, 1, 1))
expo = {}
for t in sig_days:
    i = cal_idx[t]
    vals = [pool_ret[x] for x in cal[max(0, i - 60 + 1):i + 1] if x in pool_ret]
    vol = statistics.stdev(vals)
    expo[t] = min(1.0, max(0.40, 0.15 / (vol * math.sqrt(244))))

# per-day exposure identity across the two shift variants (robustness)
pr2 = (feat.filter(pl.col("eligible")).sort("ts_code", "trade_date")
       .with_columns((pl.col("adj_close")
                      / pl.col("adj_close").shift(1).over("ts_code") - 1.0).alias("_r")))
feat2 = feat.with_columns((pl.col("adj_close")
                           / pl.col("adj_close").shift(1).over("ts_code") - 1.0).alias("r2"))
pr2 = (feat2.filter(pl.col("eligible")).group_by("trade_date")
       .agg(pl.col("r2").mean().alias("pr")).sort("trade_date"))
pool_ret2 = {d: v for d, v in zip(pr2["trade_date"].to_list(), pr2["pr"].to_list())
             if v is not None}
diff_days = 0
for t in sig_days:
    i = cal_idx[t]
    vals2 = [pool_ret2[x] for x in cal[max(0, i - 60 + 1):i + 1] if x in pool_ret2]
    e2 = min(1.0, max(0.40, 0.15 / (statistics.stdev(vals2) * math.sqrt(244))))
    if e2 != expo[t]:
        diff_days += 1
print("VOLT signal-day exposures differing between shift variants:",
      diff_days, "of", len(sig_days))

# --- B1(m) equity continuity at rebalance executions (t+1 sessions) ----------
# execution session = next calendar session after the signal day
next_sess = {}
for i, d in enumerate(cal[:-1]):
    next_sess[d] = cal[i + 1]
rebal_exec = [next_sess[t] for t in sig_days if next_sess.get(t)]


def day_ratios(sessions, values, targets):
    pos = {d: i for i, d in enumerate(sessions)}
    out = {}
    for t in targets:
        i = pos.get(t)
        if i and i > 0:
            out[t] = values[i] / values[i - 1] - 1.0
    return out


print()
print("== B1(VOLT) expected vs actual day-over-day equity change at sampled "
      "rebalance executions ==")
s_v, v_v = curve(EQ, "B1-VOLT")
s_f, v_f = curve(EQ, "B1-FIX")
s_t, v_t = curve(EQ, "B1-TREND")
SAMPLES = [date(2016, 2, 1), date(2024, 5, 6)]  # exec days after low-exposure signals
for ex in SAMPLES:
    sig = cal[cal_idx[ex] - 1]
    e = expo[sig]
    i = cal_idx[ex]
    pr_next = pool_ret.get(ex)
    exp_ratio = e * (1 + pr_next) + (1 - e) if pr_next is not None else None
    act = day_ratios(s_v, v_v, [ex])[ex]
    print(f"  exec {ex} (signal {sig}, exposure {e:.4f}): "
          f"expected ~{exp_ratio - 1:+.4%} (close-to-close approx), "
          f"actual {act:+.4%}, gap {act - (exp_ratio - 1):+.4%}")

allr = day_ratios(s_v, v_v, rebal_exec)
worst = sorted(allr.items(), key=lambda kv: kv[1])[:5]
print("  B1(VOLT) worst 5 rebalance-execution day returns (all 108 scanned):")
for d, r in worst:
    print(f"    {d}: {r:+.4%}")
print("  B1(FIX) worst:", min(day_ratios(s_f, v_f, rebal_exec).values()))
print("  B1(TREND) worst:", min(day_ratios(s_t, v_t, rebal_exec).values()))

# --- voided-run collapse signature -------------------------------------------
print()
print("== voided run 93d0523e B1(m) curves: rebalance-day collapse signature ==")
sv_v, vv_v = curve(EQV, "B1-VOLT")
rv = day_ratios(sv_v, vv_v, rebal_exec)
wv = sorted(rv.items(), key=lambda kv: kv[1])[:5]
for d, r in wv:
    print(f"  voided B1(VOLT) {d}: {r:+.4%}")
print("  voided B1(VOLT) dev net_cagr:", MV["benchmarks"]["B1"]["VOLT"]["dev"]["net_cagr"])
print("  final  B1(VOLT) dev net_cagr:", M["benchmarks"]["B1"]["VOLT"]["dev"]["net_cagr"])

# final B1 curves monotone sanity: no day-over-day drop worse than -12%
s100, v100 = curve(EQ, "B1-100")
r_all = day_ratios(s100, v100, s100[1:])
print("  final B1@100 worst single-day:", min(r_all.values()))

# --- B1@100 vs P2-R6 published (already exact in A9); dev slice summary ------
b = M["benchmarks"]["B1"]["100"]["dev"]
print()
print("B1@100 dev: net_cagr", b["net_cagr"], "total", b["net_total_return"],
      "mdd", b["max_drawdown"], "-> 10.40% / +63.9% / -27.5% at published precision")
