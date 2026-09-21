# -*- coding: utf-8 -*-
"""Check 7: stock bar fidelity vs baostock parquet (2 stocks x 3 dates)."""
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, SEED, h5_keys, max_abs, result  # noqa: E402


def oid_to_baostock(oid: str) -> str:
    code, exch = oid.split(".")
    return f"{'sh' if exch == 'XSHG' else 'sz'}.{code}"


rng = np.random.default_rng(SEED)
out = {"seed": SEED}
stock_keys = h5_keys("stocks.h5")
sample = ["600036.XSHG", "000651.XSHE"] + sorted(
    rng.choice([k for k in stock_keys if k not in ("600036.XSHG", "000651.XSHE")], size=1, replace=False).tolist()
)[:1]
sample = list(dict.fromkeys(sample))[:3]
out["sampled"] = sample

pdf = pl.scan_parquet("D:/量化/data/processed/baostock-daily-20260917/daily_2015_2024.parquet")
with h5py.File(f"{BUNDLE}/stocks.h5", "r") as f:
    per = []
    for oid in sample[:2]:
        arr = f[oid][:]
        days = arr["datetime"] // 10**6
        pick = sorted(rng.choice(days, size=3, replace=False))
        sym = oid_to_baostock(oid)
        date_objs = [
            __import__("datetime").date(d // 10000, d // 100 % 100, d % 100) for d in pick
        ]
        raw = (
            pdf.filter((pl.col("symbol") == sym) & pl.col("date").is_in(date_objs))
            .collect()
            .sort("date")
        )
        idx = np.searchsorted(days, pick)
        sub = arr[idx]
        rec = {"oid": oid, "baostock_symbol": sym, "dates": [int(d) for d in pick], "fields": {}}
        for field, src in [("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"),
                           ("volume", "volume"), ("total_turnover", "amount")]:
            b = sub[field]
            r = raw[src].to_numpy()
            rec["fields"][field] = {
                "bundle": [float(x) for x in b],
                "raw": [float(x) for x in r],
                "exact_equal": bool(np.array_equal(b, r)),
                "max_abs_diff": max_abs(b, r),
            }
        rec["adjustflag_raw"] = raw["adjustflag"].to_list()
        rec["tradestatus_raw"] = raw["tradestatus"].to_list()
        per.append(rec)
out["per_stock"] = per
result("check7_stock_fidelity", out)
print(out)
