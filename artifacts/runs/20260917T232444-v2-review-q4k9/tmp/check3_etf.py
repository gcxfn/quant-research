# -*- coding: utf-8 -*-
"""Check 3: ETF bar fidelity vs tushare fund_daily + numeric unit-conversion proof."""
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, RAW, SEED, max_abs, oid_to_ts, result  # noqa: E402

rng = np.random.default_rng(SEED)
out = {"seed": SEED}
CHUNK_DIR = f"{RAW}/fund_daily/20260917-r1"

fund_keys = None
with h5py.File(f"{BUNDLE}/funds.h5", "r") as f:
    fund_keys = sorted(f.keys())
    sample = ["510300.XSHG"] + sorted(rng.choice([k for k in fund_keys if k != "510300.XSHG"], size=2, replace=False))
    out["sampled_etfs"] = sample
    per = []
    for oid in sample:
        ts = oid_to_ts(oid)
        raw = pl.read_csv(f"{CHUNK_DIR}/chunk_{ts}.csv", schema_overrides={"trade_date": pl.Int64})
        arr = f[oid][:]
        days = arr["datetime"] // 10**6
        common = np.intersect1d(days, raw["trade_date"].to_numpy())
        pick = sorted(rng.choice(common, size=5, replace=False))
        rows_raw = raw.filter(pl.col("trade_date").is_in(pick)).sort("trade_date")
        idx = np.searchsorted(days, pick)
        sub = arr[idx]
        rec = {"oid": oid, "ts": ts, "dates": [int(d) for d in pick], "fields": {}}
        for field, src in [
            ("open", "open"), ("high", "high"), ("low", "low"), ("close", "close"),
        ]:
            b = sub[field]
            r = rows_raw[src].to_numpy()
            rec["fields"][field] = {
                "bundle": [float(x) for x in b],
                "raw": [float(x) for x in r],
                "exact_equal": bool(np.array_equal(b, r)),
                "max_abs_diff": max_abs(b, r),
            }
        vol_b = sub["volume"]
        vol_raw = rows_raw["vol"].to_numpy()
        rec["fields"]["volume"] = {
            "bundle": [float(x) for x in vol_b],
            "raw_vol_shou": [float(x) for x in vol_raw],
            "exact_equal_to_vol_times_100": bool(np.array_equal(vol_b, vol_raw * 100.0)),
            "max_abs_diff_vs_vol_x100": max_abs(vol_b, vol_raw * 100.0),
            "ratios": [float(b / r) if r else None for b, r in zip(vol_b, vol_raw)],
        }
        to_b = sub["total_turnover"]
        amt_raw = rows_raw["amount"].to_numpy()
        rec["fields"]["total_turnover"] = {
            "bundle": [float(x) for x in to_b],
            "raw_amount_qianyuan": [float(x) for x in amt_raw],
            "exact_equal_to_amount_times_1000": bool(np.array_equal(to_b, amt_raw * 1000.0)),
            "max_abs_diff_vs_amount_x1000": max_abs(to_b, amt_raw * 1000.0),
            "ratios": [float(b / r) if r else None for b, r in zip(to_b, amt_raw)],
        }
        lu = sub["limit_up"]
        ld = sub["limit_down"]
        rec["limits_all_nan_in_sample"] = bool(np.all(np.isnan(lu)) and np.all(np.isnan(ld)))
        per.append(rec)
    out["per_etf"] = per
    # fund-wide limit NaN check
    nan_lu = 0
    tot_rows = 0
    for k in fund_keys:
        a = f[k][:]
        tot_rows += a.shape[0]
        nan_lu += int(np.isnan(a["limit_up"]).sum())
    out["fund_limit_nan_rows"] = {"nan_limit_up_rows": nan_lu, "total_rows": tot_rows}

# ---- global numeric unit proof over ALL fund_daily rows ----
allf = pl.read_csv(
    f"{CHUNK_DIR}/chunk_*.csv", schema_overrides={"trade_date": pl.Int64}
)
n = allf.height
vwap = (allf["amount"].to_numpy() * 1000.0) / (allf["vol"].to_numpy() * 100.0)
low = allf["low"].to_numpy()
high = allf["high"].to_numpy()
ok = (vwap >= low * (1 - 1e-9)) & (vwap <= high * (1 + 1e-9))
tiny = allf["amount"].to_numpy() * 1000.0 < 1000.0
out["unit_proof_all_rows"] = {
    "rows": int(n),
    "vwap_in_low_high": int(ok.sum()),
    "vwap_outside": int((~ok).sum()),
    "outside_with_amount_lt_1000yuan": int((~ok & tiny).sum()),
    "outside_amount_ge_1000_max_rel_dev": float(
        np.nanmax(
            np.abs(vwap[~ok & ~tiny] / ((low[~ok & ~tiny] + high[~ok & ~tiny]) / 2) - 1)
        )
    ) if int((~ok & ~tiny).sum()) else 0.0,
    "outside_non_tiny_count": int((~ok & ~tiny).sum()),
}
result("check3_etf_fidelity", out)
print(out)
