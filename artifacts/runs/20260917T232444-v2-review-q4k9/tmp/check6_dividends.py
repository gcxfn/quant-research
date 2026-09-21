# -*- coding: utf-8 -*-
"""Check 6: dividends — 000001.XSHE history, 2020 row vs tushare cash_div, r2/r3 splice."""
import glob
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, RAW, result  # noqa: E402

out = {}

with h5py.File(f"{BUNDLE}/dividends.h5", "r") as f:
    rows = f["000001.XSHE"][:]
bundle_years = (rows["ex_dividend_date"] // 10000)
out["000001XSHE"] = {
    "n_rows_total": int(rows.shape[0]),
    "rows_in_2015_2024": int(((bundle_years >= 2015) & (bundle_years <= 2024)).sum()),
    "ex_dates": sorted(int(x) for x in rows["ex_dividend_date"]),
    "rows_2020": [
        {
            "book_closure_date": int(r["book_closure_date"]),
            "dividend_cash_before_tax": float(r["dividend_cash_before_tax"]),
            "ex_dividend_date": int(r["ex_dividend_date"]),
            "payable_date": int(r["payable_date"]),
            "round_lot": int(r["round_lot"]),
        }
        for r in rows if 20200101 <= r["ex_dividend_date"] <= 20201231
    ],
}

# raw tushare dividend rows for 000001.SZ div_proc=实施
raw_paths = [
    p for p in sorted(glob.glob(f"{RAW}/dividend/20260913-r2/chunk_*.csv"))
    + sorted(glob.glob(f"{RAW}/dividend/20260909-r3/chunk_*.csv"))
    if __import__("os").path.getsize(p) > 0
]
out["nonempty_chunks"] = len(raw_paths)
frames = []
for p in raw_paths:
    df = pl.read_csv(p, infer_schema_length=0)  # all strings; mixed dtypes across chunks
    frames.append(df)
raw = pl.concat(frames, how="vertical_relaxed")
for c, t in [("cash_div", pl.Float64), ("cash_div_tax", pl.Float64), ("stk_div", pl.Float64), ("ex_date", pl.Int64), ("end_date", pl.Int64)]:
    raw = raw.with_columns(pl.col(c).cast(t, strict=False))
out["raw_total_rows_all_proc"] = raw.height
impl = raw.filter(pl.col("div_proc") == "实施")
out["raw_shishi_rows"] = impl.height
per_year = impl.group_by((pl.col("ex_date") // 10000).alias("yr")).len().sort("yr")
out["raw_shishi_rows_per_year"] = {str(yr): int(n) for yr, n in per_year.iter_rows()}

r1 = impl.filter(
    (pl.col("ts_code") == "000001.SZ")
    & (pl.col("ex_date") >= 20200101) & (pl.col("ex_date") <= 20201231)
)
out["raw_000001_2020"] = r1.select(
    ["ts_code", "end_date", "div_proc", "cash_div", "cash_div_tax", "record_date", "ex_date", "pay_date"]
).to_dicts()
# compare with bundle rows on same ex-date
for b in out["000001XSHE"]["rows_2020"]:
    match = [r for r in out["raw_000001_2020"] if int(r["ex_date"]) == b["ex_dividend_date"]]
    if match:
        b["raw_cash_div_per_share"] = match[0]["cash_div"]
        b["cash_div_x_round_lot"] = float(match[0]["cash_div"]) * b["round_lot"]
        b["exact_equal"] = bool(b["dividend_cash_before_tax"] == b["cash_div_x_round_lot"])
        b["raw_pay_date"] = match[0]["pay_date"]
        b["raw_record_date"] = match[0]["record_date"]

# bundle-wide per-year distribution vs raw (continuity across the 2017/2018 splice)
with h5py.File(f"{BUNDLE}/dividends.h5", "r") as f:
    keys = sorted(f.keys())
    all_rows = []
    for k in keys:
        all_rows.append(f[k][:])
    allb = np.concatenate(all_rows)
by = (allb["ex_dividend_date"] // 10000)
uy, uc = np.unique(by, return_counts=True)
out["bundle_rows_per_year"] = {str(int(a)): int(b) for a, b in zip(uy, uc) if 2015 <= a <= 2024}
out["bundle_total_rows"] = int(allb.shape[0])
out["bundle_codes"] = len(keys)

# splice boundary evidence: last r2 chunk / first r3 chunk dates
out["splice"] = {
    "r2_last_chunk": "20171229",
    "r3_first_chunk": "20180102",
    "raw_2017_rows": out["raw_shishi_rows_per_year"].get("2017"),
    "raw_2018_rows": out["raw_shishi_rows_per_year"].get("2018"),
}

result("check6_dividends", out)
print(out)
