# -*- coding: utf-8 -*-
"""Check 9b: remaining placeholder disclosures + 000300 cross-source values + coverage gaps."""
import json
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, RAW, h5_keys, result  # noqa: E402

out = {}

# 000300 bars vs raw bigquant csv (date format YYYY-MM-DD)
raw = pl.read_csv(
    "D:/量化/data/raw/bigquant/intraday-t0-20260914/000300.SH_2021-08-05_2024-12-31_bar1d.csv"
)
with h5py.File(f"{BUNDLE}/indexes.h5", "r") as f:
    b = f["000300.XSHG"][:]
days = b["datetime"] // 10**6
sample_days = [20211123, 20220228, 20220616, 20230410, 20231026]
sub = b[np.searchsorted(days, sample_days)]
checks = []
for d, r in zip(sample_days, sub):
    ds = f"{d//10000:04d}-{d//100%100:02d}-{d%100:02d}"
    q = raw.filter(pl.col("date").cast(pl.Utf8).str.contains(ds))
    if q.height:
        row = q.row(0, named=True)
        checks.append({
            "day": d,
            "bundle": {k: float(r[k]) for k in ["open", "high", "low", "close", "volume", "total_turnover"]},
            "raw": {k: float(row[k]) for k in ["open", "high", "low", "close", "volume", "amount"]},
            "exact_ohlc_equal": bool(
                all(float(r[k]) == float(row[k]) for k in ["open", "high", "low", "close"])
            ),
            "volume_equal": bool(float(r["volume"]) == float(row["volume"])),
            "turnover_equal": bool(float(r["total_turnover"]) == float(row["amount"])),
        })
    else:
        checks.append({"day": d, "raw": None})
out["cross_source_000300"] = checks
out["raw_csv_rows"] = raw.height

# futures.h5 / share_transformation / future_info
with h5py.File(f"{BUNDLE}/futures.h5", "r") as f:
    out["futures_h5_keys"] = list(f.keys())
out["share_transformation"] = json.load(open(f"{BUNDLE}/share_transformation.json", encoding="utf-8"))
out["future_info"] = json.load(open(f"{BUNDLE}/future_info.json", encoding="utf-8"))

# ETF absence from dividends / suspended / st
fund_keys = set(h5_keys("funds.h5"))
div_keys = set(h5_keys("dividends.h5"))
susp_keys = set(h5_keys("suspended_days.h5"))
st_keys = set(h5_keys("st_stock_days.h5"))
exf_keys = set(h5_keys("ex_cum_factor.h5"))
out["etf_in_dividends"] = sorted(fund_keys & div_keys)
out["etf_in_suspended"] = sorted(fund_keys & susp_keys)
out["etf_in_st"] = sorted(fund_keys & st_keys)
# 159842 identity-only check
with h5py.File(f"{BUNDLE}/ex_cum_factor.h5", "r") as f:
    a = f["159842.XSHE"][:]
out["159842_ex_cum_rows"] = [[int(r["start_date"]), float(r["ex_cum_factor"])] for r in a]
# also: does every stock/etf have an ex_cum_factor key, and INDX not?
stock_keys = set(h5_keys("stocks.h5"))
out["exf_missing_from_pool"] = sorted((stock_keys | fund_keys) - exf_keys)
out["exf_extra_beyond_pool"] = sorted(exf_keys - (stock_keys | fund_keys))

# split_factor spot check: 000001.XSHE first row vs tushare stk_div on same ex-date
with h5py.File(f"{BUNDLE}/split_factor.h5", "r") as f:
    s1 = f["000001.XSHE"][:]
out["000001_split_first3"] = [
    [int(r["ex_date"]), float(r["split_factor"])] for r in s1[:3]
]
d2015 = pl.read_csv(f"{RAW}/dividend/20260913-r2/chunk_20150413.csv", infer_schema_length=0)
row = d2015.filter((pl.col("ts_code") == "000001.SZ") & (pl.col("div_proc") == "实施"))
out["000001_raw_20150413"] = row.to_dicts()

# where does the bundle manifest disclose the 000001.XSHG probe / 000300 coverage?
bm = json.load(open(f"{BUNDLE}/manifest.json", encoding="utf-8"))
hits = []
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            walk(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            walk(v, f"{path}[{i}]")
    else:
        s = str(o)
        if any(t in s for t in ("000001.XSHG", "range_probe", "000300", "bigquant", "benchmark")):
            hits.append((path, s[:220]))
walk(bm.get("placeholders"), "placeholders")
walk(bm.get("params"), "params")
out["manifest_mentions_probe_or_benchmark"] = hits
# count of placeholders entries
out["n_placeholders_entries"] = len(bm["placeholders"])
# inputs entries for indexes
out["index_related_inputs"] = [
    {"role": i.get("role"), "path": i.get("path")}
    for i in bm["inputs"] if "index" in str(i.get("role", "")).lower() or "probe" in str(i.get("role", "")).lower()
]
result("check9b_placeholders", out)
print(out)
