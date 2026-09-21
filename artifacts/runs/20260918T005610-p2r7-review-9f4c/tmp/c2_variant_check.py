# -*- coding: utf-8 -*-
"""Variant check: VOLT exposure under 'shift over all own rows' vs
'shift within eligible subset' (implementation reading)."""
import json
import math
import os
import statistics
from datetime import date

import polars as pl

ROOT = "D:/量化/"
CFG = json.load(open(ROOT + "configs/experiments/p2r7-etf-exposure.json", encoding="utf-8"))
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
    frames.append(d.sort("trade_date").join_asof(
        a, left_on="trade_date", right_on="_ad", strategy="backward")
        .with_columns(pl.lit(code).alias("ts_code")))
daily = (pl.concat(frames).sort("ts_code", "trade_date")
         .filter(pl.col("trade_date") <= date(2024, 12, 31)))
reg = (pl.read_csv(ROOT + CFG["data"]["fund_basic"]["batch"] + "/"
                   + CFG["data"]["fund_basic"]["file"], infer_schema_length=0)
       .select("ts_code", "name", "fund_type",
               pl.col("list_date").str.to_date("%Y%m%d", strict=False),
               pl.col("delist_date").str.to_date("%Y%m%d", strict=False))
       .filter(pl.col("ts_code").is_in(sorted(WL))))
nm = pl.col("name").fill_null("")
keep = reg.filter(pl.col("fund_type").is_in(CFG["universe"]["u2_category"]["fund_type_in"])
                  & ~pl.any_horizontal([nm.str.contains(k, literal=True)
                                        for k in CFG["universe"]["u2_qdii_keywords_frozen"]]))
feat = daily.join(keep.select("ts_code", "list_date", "delist_date"),
                  on="ts_code", how="inner")
feat = feat.with_columns((pl.col("close") * pl.col("adj_factor")).alias("adj_close"),
                         pl.int_range(pl.len()).over("ts_code").add(1).alias("row_idx"))
feat = feat.with_columns(pl.col("amount").rolling_median(20, min_samples=20)
                         .over("ts_code").alias("am20"))
feat = feat.with_columns((pl.col("adj_close")
                          / pl.col("adj_close").shift(1).over("ts_code") - 1.0)
                         .alias("r_all"))
cal = feat.select("trade_date").unique().sort("trade_date").to_series().to_list()
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
pr2 = (feat.filter(pl.col("eligible")).group_by("trade_date")
       .agg(pl.col("r_all").mean().alias("pr")).sort("trade_date"))
pool2 = {d: v for d, v in zip(pr2["trade_date"].to_list(), pr2["pr"].to_list())
         if v is not None}
fe = (feat.filter(pl.col("eligible")).sort("ts_code", "trade_date")
      .with_columns((pl.col("adj_close")
                     / pl.col("adj_close").shift(1).over("ts_code") - 1.0).alias("_r")))
pr1 = fe.group_by("trade_date").agg(pl.col("_r").mean().alias("pr")).sort("trade_date")
pool1 = {d: v for d, v in zip(pr1["trade_date"].to_list(), pr1["pr"].to_list())
         if v is not None}
lom = {}
for d in cal:
    lom[(d.year, d.month)] = d
sigs = sorted(d for d in lom.values() if d >= date(2016, 1, 1))


def expo_of(pool, t):
    i = cal.index(t)
    vals = [pool[x] for x in cal[max(0, i - 59):i + 1] if x in pool]
    return min(1.0, max(0.40, 0.15 / (statistics.stdev(vals) * math.sqrt(244))))


ex1 = {t: expo_of(pool1, t) for t in sigs}
ex2 = {t: expo_of(pool2, t) for t in sigs}
diffs = sorted(((t, ex1[t], ex2[t], abs(ex1[t] - ex2[t])) for t in sigs
                if ex1[t] != ex2[t]), key=lambda x: -x[3])
print("n signal days differing:", len(diffs),
      "| max abs exposure diff:", round(diffs[0][3], 6) if diffs else 0)
print("top5 diffs (day, impl-reading, alt-reading):",
      [(str(t), round(a, 4), round(b, 4)) for t, a, b, _ in diffs[:5]])
DOC_VOLT = {2016: (0.78, 8, 25, 25, 42), 2017: (1.00, 0, 0, 8, 92),
            2018: (0.86, 0, 25, 58, 17), 2019: (0.85, 0, 33, 25, 42),
            2020: (0.72, 0, 58, 33, 8), 2021: (0.84, 0, 8, 75, 17),
            2022: (0.80, 0, 33, 58, 8), 2023: (1.00, 0, 0, 0, 100),
            2024: (0.70, 17, 42, 42, 0)}
print("variant-2 ('prev all own rows') yearly aggregates vs doc:")
for y in range(2016, 2025):
    vs = [ex2[d] for d in sigs if d.year == y]
    vm = round(sum(vs) / len(vs), 2)
    vb = (round(100 * sum(1 for x in vs if x == 0.40) / len(vs)),
          round(100 * sum(1 for x in vs if 0.40 < x < 0.70) / len(vs)),
          round(100 * sum(1 for x in vs if 0.70 <= x < 1.0) / len(vs)),
          round(100 * sum(1 for x in vs if x == 1.0) / len(vs)))
    ok = (vm, vb) == DOC_VOLT[y]
    print(f"  {y}: mean={vm} buckets={vb} | doc={DOC_VOLT[y]} | "
          f"{'OK' if ok else 'DIFF'}")
