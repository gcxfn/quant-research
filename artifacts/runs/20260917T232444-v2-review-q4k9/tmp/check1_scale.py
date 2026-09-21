# -*- coding: utf-8 -*-
"""Check 1: scale & coverage — h5 key counts, trading calendar, pool consistency."""
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, result  # noqa: E402

out = {}

with h5py.File(f"{BUNDLE}/stocks.h5", "r") as f:
    stock_keys = sorted(f.keys())
with h5py.File(f"{BUNDLE}/funds.h5", "r") as f:
    fund_keys = sorted(f.keys())

out["stocks_key_count"] = len(stock_keys)
out["funds_key_count"] = len(fund_keys)
out["stocks_first5"] = stock_keys[:5]
out["funds_first5"] = fund_keys[:5]
out["key_overlap"] = sorted(set(stock_keys) & set(fund_keys))

td = np.load(f"{BUNDLE}/trading_dates.npy")
out["calendar"] = {
    "dtype": str(td.dtype),
    "n": int(td.shape[0]),
    "first": int(td[0]),
    "last": int(td[-1]),
    "strictly_increasing": bool(np.all(np.diff(td) > 0)),
    "has_20170307": bool((td == 20170307).any()),
    "has_20241202": bool((td == 20241202).any()),
}

# instruments counts by type
from common import load_instruments  # noqa: E402

inst = load_instruments()
types = {}
for i in inst:
    types[i["type"]] = types.get(i["type"], 0) + 1
out["instruments_count_by_type"] = types
out["instruments_total"] = len(inst)

# pool consistency: unique symbols in baostock parquet
pdf = (
    pl.scan_parquet("D:/量化/data/processed/baostock-daily-20260917/daily_2015_2024.parquet")
    .select(pl.col("symbol").n_unique().alias("n_sym"))
    .collect()
)
out["baostock_unique_symbols"] = int(pdf["n_sym"][0])

# board composition of stock keys (exclusion check)
prefixes = {}
for k in stock_keys:
    p = k[:3]
    prefixes[p] = prefixes.get(p, 0) + 1
out["stock_key_prefix_counts"] = dict(sorted(prefixes.items()))
out["has_688_or_689_or_bj"] = [k for k in stock_keys if k[:3] in ("688", "689")] + [
    k for k in stock_keys if k.endswith(".BJ")
]

result("check1_scale", out)
print(out)
