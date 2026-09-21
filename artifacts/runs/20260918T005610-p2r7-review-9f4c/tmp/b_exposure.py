# -*- coding: utf-8 -*-
"""P2-R7 review script B: independent exposure-path recomputation from raw
data (fund_daily + fund_adj + index_daily + fund_basic), following the frozen
config spec. Read-only."""
import json
import math
import statistics
from bisect import bisect_right
from datetime import date

import polars as pl

ROOT = "D:/量化/"
CFG = json.load(open(ROOT + "configs/experiments/p2r7-etf-exposure.json",
                     encoding="utf-8"))
RUN = ROOT + "artifacts/runs/20260918T004441-p2r7-etf-exposure-d01f4e7a/"
M = json.load(open(RUN + "metrics.json", encoding="utf-8"))
FREEZE = date(2024, 12, 31)

WL = set(CFG["u1_whitelist_frozen"])
FD = ROOT + CFG["data"]["fund_daily"]["batch"] + "/"
FA = ROOT + CFG["data"]["fund_adj"]["batch"] + "/"

# --- load daily + adj, asof-backward factor join (own implementation) -------
frames = []
for p in sorted(pl.Series(FD and __import__("os").listdir(FD)).to_list()):
    if not p.startswith("chunk_") or not p.endswith(".csv"):
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
                 pl.col("adj_factor").cast(pl.Float64, strict=False))
         .sort("_ad"))
    j = d.sort("trade_date").join_asof(a, left_on="trade_date", right_on="_ad",
                                       strategy="backward")
    frames.append(j.with_columns(pl.lit(code).alias("ts_code")))
daily = (pl.concat(frames).sort("ts_code", "trade_date")
         .filter(pl.col("trade_date") <= FREEZE))
print("rows loaded (whitelisted):", daily.height,
      "| codes:", daily["ts_code"].n_unique(),
      "| metrics load_stats:", M["load_stats"])

# --- U2 registry filter ------------------------------------------------------
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
print("registry rows after U2 filter (review impl):", keep.height)

feat = daily.join(keep.select("ts_code", "list_date", "delist_date"),
                  on="ts_code", how="inner")
feat = feat.with_columns(
    (pl.col("close") * pl.col("adj_factor")).alias("adj_close"),
    pl.int_range(pl.len()).over("ts_code").add(1).alias("row_idx"))
feat = feat.with_columns([
    pl.col("adj_close").shift(1).over("ts_code").alias("_prev_adj_allrows"),
    pl.col("amount").rolling_median(20, min_samples=20).over("ts_code")
    .alias("amount_med20")])
# own-row adjusted return on the FULL own-row series (spec wording), and the
# eligible-subset variant (implementation wording) - compare both
feat = feat.with_columns(
    (pl.col("adj_close") / pl.col("_prev_adj_allrows") - 1.0).alias("r_all"))
elig0 = feat.with_columns(
    (pl.col("adj_close") / pl.col("adj_close").shift(1).over("ts_code") - 1.0)
    .alias("r_elig_sub"))
cal = elig0.select("trade_date").unique().sort("trade_date").to_series().to_list()
cal_idx = {d: i for i, d in enumerate(cal)}
feat = elig0.join(pl.DataFrame({"trade_date": cal,
                                "cal_idx": list(range(len(cal)))}),
                  on="trade_date", how="inner")
list_bounds = (feat.select("ts_code", "list_date").unique().sort("list_date")
               .join_asof(pl.DataFrame({"_lcd": cal,
                                        "list_cal_idx": list(range(len(cal)))}),
                          left_on="list_date", right_on="_lcd", strategy="forward")
               .select("ts_code", "list_cal_idx"))
feat = feat.join(list_bounds, on="ts_code", how="inner")
LIQ = CFG["universe"]["u3_pit_rules"]["liquidity_min_units"]
feat = feat.with_columns(
    (pl.col("list_cal_idx").is_not_null()
     & ((pl.col("cal_idx") - pl.col("list_cal_idx")) >= 120)
     & (pl.col("delist_date").is_null()
        | (pl.col("trade_date") < pl.col("delist_date")))
     & (pl.col("row_idx") >= 120)
     & (pl.col("amount_med20") >= float(LIQ))
     & pl.col("adj_close").is_not_null() & pl.col("adj_close").is_finite()
     ).alias("eligible"))

elig = feat.filter(pl.col("eligible"))
print("eligible rows (review impl):", elig.height)

# --- calendar + monthly signal days -----------------------------------------
sig_days = []
last_of_month = {}
for d in cal:
    last_of_month[(d.year, d.month)] = d
for k in sorted(last_of_month):
    d = last_of_month[k]
    if d >= date(2016, 1, 1):
        sig_days.append(d)
print("signal days:", len(sig_days), "first/last:", sig_days[0], sig_days[-1])

# --- pool size cross-check vs metrics ---------------------------------------
ps_mine = {}
for d in sig_days:
    n = elig.filter(pl.col("trade_date") == d).height
    ps_mine.setdefault(d.year, []).append(n)
ps_m = M["pool_sizes"]["monthly"]
ps_bad = []
for y in sorted(ps_mine):
    v = ps_mine[y]
    st = {"min": min(v), "mean": round(sum(v) / len(v), 1), "max": max(v)}
    if st != ps_m[str(y)]:
        ps_bad.append((y, st, ps_m[str(y)]))
print("pool-size-per-year mismatches vs metrics:", ps_bad or "NONE (9/9 years)")
samp = [ps_mine[y][0] for y in sorted(ps_mine)]
print("first signal-day pool size per year (mine):", dict(
    (y, ps_mine[y][0]) for y in sorted(ps_mine)))

# --- FIX ---------------------------------------------------------------------
fix = {d: 0.75 for d in sig_days}

# --- VOLT --------------------------------------------------------------------
pr = (elig.sort("ts_code", "trade_date")
      .with_columns((pl.col("adj_close")
                     / pl.col("adj_close").shift(1).over("ts_code") - 1.0)
                    .alias("_r"))
      .group_by("trade_date").agg(pl.col("_r").mean().alias("pool_ret"))
      .sort("trade_date"))
pool_ret = {d: v for d, v in zip(pr["trade_date"].to_list(),
                                 pr["pool_ret"].to_list()) if v is not None}
pr2 = (elig.sort("ts_code", "trade_date")
       .group_by("trade_date").agg(pl.col("r_all").mean().alias("pool_ret2"))
       .sort("trade_date"))
pool_ret2 = {d: v for d, v in zip(pr2["trade_date"].to_list(),
                                  pr2["pool_ret2"].to_list())
             if v is not None and not math.isnan(v)}
print("pool-return series len (eligible-subset shift):", len(pool_ret),
      "| all-own-row shift:", len(pool_ret2),
      "| days where both exist and differ:",
      sum(1 for d in pool_ret if d in pool_ret2 and pool_ret[d] != pool_ret2[d]))


def volt(t):
    i = cal_idx[t]
    vals = [pool_ret[d] for d in cal[max(0, i - 60 + 1):i + 1] if d in pool_ret]
    vol = statistics.stdev(vals) if len(vals) >= 2 else None
    if vol is None:
        exp_ = [v for dd, v in pool_ret.items() if dd <= t]
        vol = statistics.stdev(exp_) if len(exp_) >= 2 else None
    if vol is None:
        return 0.40
    if vol <= 0.0:
        return 1.0
    ann = vol * math.sqrt(244)
    return min(1.0, max(0.40, 0.15 / ann))


volt_path = {d: volt(d) for d in sig_days}

# --- TREND -------------------------------------------------------------------
idx = (pl.read_csv(ROOT + CFG["data"]["index_daily"]["batch"] + "/"
                   + CFG["data"]["index_daily"]["trend_file"],
                   infer_schema_length=0)
       .select(pl.col("trade_date").str.to_date("%Y%m%d"),
               pl.col("close").cast(pl.Float64, strict=False))
       .sort("trade_date"))
idx = idx.with_columns(pl.col("close").rolling_mean(200, min_samples=200)
                       .alias("sma200"))
idates = idx["trade_date"].to_list()
iclose = idx["close"].to_list()
ismas = idx["sma200"].to_list()


def trend(t):
    pos = bisect_right(idates, t) - 1
    if pos < 0 or ismas[pos] is None:
        return 0.40
    return 0.90 if iclose[pos] > ismas[pos] else 0.40


trend_path = {d: trend(d) for d in sig_days}

# --- compare with archived aggregates + doc table ----------------------------
DOC_VOLT = {2016: (0.78, 8, 25, 25, 42), 2017: (1.00, 0, 0, 8, 92),
            2018: (0.86, 0, 25, 58, 17), 2019: (0.85, 0, 33, 25, 42),
            2020: (0.72, 0, 58, 33, 8), 2021: (0.84, 0, 8, 75, 17),
            2022: (0.80, 0, 33, 58, 8), 2023: (1.00, 0, 0, 0, 100),
            2024: (0.70, 17, 42, 42, 0)}
DOC_TREND = {2016: (0.61, 42, 58), 2017: (0.90, 100, 0), 2018: (0.48, 17, 83),
             2019: (0.86, 92, 8), 2020: (0.82, 83, 17), 2021: (0.65, 50, 50),
             2022: (0.40, 0, 100), 2023: (0.61, 42, 58), 2024: (0.65, 50, 50)}
print()
print("year | VOLT mean/buckets mine | metrics | doc | TREND mean/buckets mine | metrics | doc")
mv_m, mt_m = M["exposure_paths"]["VOLT"]["years"], M["exposure_paths"]["TREND"]["years"]
volt_bad = trend_bad = []
for y in range(2016, 2025):
    ds = [d for d in sig_days if d.year == y]
    vs = [volt_path[d] for d in ds]
    ts = [trend_path[d] for d in ds]
    vb = (round(100 * sum(1 for x in vs if x == 0.40) / len(vs)),
          round(100 * sum(1 for x in vs if 0.40 < x < 0.70) / len(vs)),
          round(100 * sum(1 for x in vs if 0.70 <= x < 1.0) / len(vs)),
          round(100 * sum(1 for x in vs if x == 1.0) / len(vs)))
    tb = (round(100 * sum(1 for x in ts if x == 0.90) / len(ts)),
          round(100 * sum(1 for x in ts if x == 0.40) / len(ts)))
    vm, tm = round(sum(vs) / len(vs), 2), round(sum(ts) / len(ts), 2)
    mm_v = mv_m[str(y)]
    mm_t = mt_m[str(y)]
    st_v = (round(mm_v["mean_exposure"], 2),
            round(100 * mm_v["at_0.40"]), round(100 * mm_v["b_0.40-0.70"]),
            round(100 * mm_v["b_0.70-1.00"]), round(100 * mm_v["at_1.00"]))
    st_t = (round(mm_t["mean_exposure"], 2), round(100 * mm_t["at_0.90"]),
            round(100 * mm_t["at_0.40"]))
    dv = DOC_VOLT[y]
    dt = DOC_TREND[y]
    okv = (abs(vm - dv[0]) <= 0.005 + 1e-9 and vb == dv[1:] and
           (vm, vb) == st_v[:1] + st_v[1:] if False else True)
    v_match = (abs(vm - dv[0]) < 0.05 and vb == dv[1:] and st_v == (dv[0],) + dv[1:])
    t_match = (abs(tm - dt[0]) < 0.05 and tb == dt[1:] and st_t == (dt[0],) + dt[1:])
    print(f" {y} | VOLT {vm:.2f} {vb} | stored {st_v} | doc {dv} | "
          f"TREND {tm:.2f} {tb} | stored {st_t} | doc {dt} | "
          f"V={'OK' if v_match else 'DIFF'} T={'OK' if t_match else 'DIFF'}")
    if not v_match:
        volt_bad.append(y)
    if not t_match:
        trend_bad.append(y)
print("VOLT yearly mismatches:", volt_bad or "NONE",
      "| TREND yearly mismatches:", trend_bad or "NONE")
print("FIX distinct levels:", sorted(set(fix.values())),
      "all 108 at 0.75:", all(v == 0.75 for v in fix.values()))

# --- sampled signal days (item 3 evidence) -----------------------------------
print()
print("sampled signal days (exposure recomputed from raw data):")
VOLT_SAMPLES = [date(2016, 1, 29), date(2018, 12, 28), date(2020, 2, 28),
                date(2023, 12, 29), date(2024, 4, 30)]
for d in VOLT_SAMPLES:
    i = cal_idx[d]
    vals = [pool_ret[x] for x in cal[max(0, i - 60 + 1):i + 1] if x in pool_ret]
    vol = statistics.stdev(vals)
    print(f"  VOLT {d}: n_pool={elig.filter(pl.col('trade_date') == d).height} "
          f"vol60_daily={vol:.6f} ann={vol * math.sqrt(244):.4f} "
          f"exposure={volt_path[d]:.6f} "
          f"bucket={'at40' if volt_path[d] == 0.40 else 'at100' if volt_path[d] == 1.0 else 'mid'}")
TREND_SAMPLES = [date(2018, 12, 28), date(2019, 4, 30), date(2020, 7, 31),
                 date(2021, 12, 31), date(2022, 12, 30)]
for d in TREND_SAMPLES:
    pos = bisect_right(idates, d) - 1
    print(f"  TREND {d}: index_close={iclose[pos]:.2f} sma200={ismas[pos]:.2f} "
          f"close>sma={iclose[pos] > ismas[pos]} exposure={trend_path[d]}")
FIX_SAMPLES = [date(2016, 12, 30), date(2020, 3, 31)]
for d in FIX_SAMPLES:
    print(f"  FIX {d}: exposure={fix[d]}")
