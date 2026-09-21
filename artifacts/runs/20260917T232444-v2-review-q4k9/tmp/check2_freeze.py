# -*- coding: utf-8 -*-
"""Check 2: freeze boundary — per-security max datetime (sampled) + full-library scan."""
import sys

import h5py
import numpy as np

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, SEED, h5_keys, oid_to_ts, result  # noqa: E402

rng = np.random.default_rng(SEED)
out = {"seed": SEED}
FREEZE = 20241231

stock_keys = h5_keys("stocks.h5")
fund_keys = h5_keys("funds.h5")

sample_stocks = sorted(rng.choice(stock_keys, size=5, replace=False))
sample_etfs_raw = sorted(rng.choice(fund_keys, size=5, replace=False))
# force-include named securities for determinism of the deliverable evidence
sample_stocks[0] = "000001.XSHE"
sample_etfs_raw[0] = "510300.XSHG"

out["sampled_stock_max"] = {}
with h5py.File(f"{BUNDLE}/stocks.h5", "r") as f:
    for k in sample_stocks:
        dts = f[k]["datetime"][:]
        out["sampled_stock_max"][k] = {
            "max_datetime": int(dts.max()),
            "max_day": int(dts.max() // 10**6),
            "n_rows": int(dts.shape[0]),
        }

out["sampled_etf_max"] = {}
with h5py.File(f"{BUNDLE}/funds.h5", "r") as f:
    for k in sample_etfs_raw:
        dts = f[k]["datetime"][:]
        out["sampled_etf_max"][k] = {
            "max_datetime": int(dts.max()),
            "max_day": int(dts.max() // 10**6),
            "n_rows": int(dts.shape[0]),
        }

# full-library scan: read only the datetime field of every key
global_max = 0
n_over = 0
over_examples = []
with h5py.File(f"{BUNDLE}/stocks.h5", "r") as f:
    for k in stock_keys:
        m = int(f[k]["datetime"][:].max())
        if m > global_max:
            global_max = m
        if m // 10**6 > FREEZE:
            n_over += 1
            over_examples.append(("stocks", k, m))
with h5py.File(f"{BUNDLE}/funds.h5", "r") as f:
    for k in fund_keys:
        m = int(f[k]["datetime"][:].max())
        if m > global_max:
            global_max = m
        if m // 10**6 > FREEZE:
            n_over += 1
            over_examples.append(("funds", k, m))

out["full_scan"] = {
    "securities_scanned": len(stock_keys) + len(fund_keys),
    "global_max_datetime": global_max,
    "global_max_day": global_max // 10**6,
    "securities_with_bar_after_20241231": n_over,
    "examples": over_examples[:10],
}

result("check2_freeze", out)
print(out)
