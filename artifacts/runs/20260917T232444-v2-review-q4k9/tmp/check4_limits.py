# -*- coding: utf-8 -*-
"""Check 4: stock limit_up/limit_down vs tushare stk_limit raw chunks."""
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, RAW, SEED, h5_keys, oid_to_ts, result  # noqa: E402

rng = np.random.default_rng(SEED)
out = {"seed": SEED}
CHUNK_DIR = f"{RAW}/stk_limit/20260917-r1"

with h5py.File(f"{BUNDLE}/stocks.h5", "r") as f:
    stock_keys = sorted(f.keys())
    # forced pair: 000001.XSHE on a 2024-12 trading day
    day1 = 20241202
    pairs = [("000001.XSHE", day1)]
    dates_avail = None
    arr0 = f["000001.XSHE"][:]
    days0 = arr0["datetime"] // 10**6
    assert day1 in set(days0.tolist())
    # 4 more seeded random (stock, date) pairs
    for _ in range(4):
        while True:
            k = str(rng.choice(stock_keys))
            a = f[k][:]
            d = a["datetime"] // 10**6
            if a.shape[0] > 50:
                pairs.append((k, int(rng.choice(d))))
                break
    recs = []
    for oid, day in pairs:
        ts = oid_to_ts(oid)
        raw = pl.read_csv(f"{CHUNK_DIR}/chunk_{day}.csv", schema_overrides={"trade_date": pl.Int64})
        row = raw.filter(pl.col("ts_code") == ts)
        a = f[oid][:]
        days = a["datetime"] // 10**6
        i = int(np.searchsorted(days, day))
        rec = {
            "oid": oid, "date": int(day),
            "bundle_limit_up": float(a["limit_up"][i]),
            "bundle_limit_down": float(a["limit_down"][i]),
            "raw_up_limit": float(row["up_limit"][0]) if row.height else None,
            "raw_down_limit": float(row["down_limit"][0]) if row.height else None,
        }
        rec["exact_equal_up"] = (
            rec["bundle_limit_up"] == rec["raw_up_limit"]
            if rec["raw_up_limit"] is not None else False
        )
        rec["exact_equal_down"] = (
            rec["bundle_limit_down"] == rec["raw_down_limit"]
            if rec["raw_down_limit"] is not None else False
        )
        rec["raw_chunk_rows_that_day"] = raw.height
        recs.append(rec)
    out["pairs"] = recs

    # NaN rule on the 5 header-only chunk days
    nan_days = {}
    for day in [20170307, 20170308, 20170309, 20220726, 20230421]:
        raw = pl.read_csv(f"{CHUNK_DIR}/chunk_{day}.csv")
        nan_cnt = 0
        rows_that_day = 0
        for k in stock_keys:
            a = f[k][:]
            days = a["datetime"] // 10**6
            idx = np.where(days == day)[0]
            if idx.size:
                rows_that_day += 1
                nan_cnt += int(np.isnan(a["limit_up"][idx[0]]))
        nan_days[str(day)] = {
            "raw_chunk_rows": raw.height,
            "bundle_bars_that_day": rows_that_day,
            "bundle_nan_limit_up": nan_cnt,
        }
    out["nan_rule_days"] = nan_days

result("check4_limits", out)
print(out)
