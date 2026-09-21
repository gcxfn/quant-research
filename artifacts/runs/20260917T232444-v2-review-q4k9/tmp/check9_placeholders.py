# -*- coding: utf-8 -*-
"""Check 9: placeholders — indexes.h5 (000001.XSHG probe, 000300.XSHG real) and yield_curve."""
import glob
import json
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, SEED, result  # noqa: E402

rng = np.random.default_rng(SEED)
out = {"seed": SEED}

bm = json.load(open(f"{BUNDLE}/manifest.json", encoding="utf-8"))
out["disclosed_placeholders"] = bm["placeholders"]

with h5py.File(f"{BUNDLE}/indexes.h5", "r") as f:
    idx_keys = list(f.keys())
    out["index_keys"] = idx_keys
    a = f["000001.XSHG"][:]
    out["000001_probe"] = {
        "n_rows": int(a.shape[0]),
        "first_day": int(a["datetime"][0] // 10**6),
        "last_day": int(a["datetime"][-1] // 10**6),
        "all_ohlc_nan": bool(
            np.all(np.isnan(a["open"])) and np.all(np.isnan(a["close"]))
            and np.all(np.isnan(a["high"])) and np.all(np.isnan(a["low"]))
        ),
        "all_volume_zero": bool(np.all(a["volume"] == 0.0)),
        "all_turnover_nan": bool(np.all(np.isnan(a["total_turnover"]))),
    }
    b = f["000300.XSHG"][:]
    days = b["datetime"] // 10**6
    out["000300"] = {
        "n_rows": int(b.shape[0]),
        "first_day": int(days[0]),
        "last_day": int(days[-1]),
        "nan_counts": {k: int(np.isnan(b[k]).sum()) for k in ["open", "close", "high", "low", "volume", "total_turnover"]},
        "first_row": [int(days[0])] + [float(b[k][0]) for k in ["open", "close", "high", "low", "volume", "total_turnover"]],
        "last_row": [int(days[-1])] + [float(b[k][-1]) for k in ["open", "close", "high", "low", "volume", "total_turnover"]],
    }
    # sample 5 days for cross-source comparison
    pick = sorted(rng.choice(days, size=5, replace=False))
    sub = b[np.searchsorted(days, pick)]
    out["000300_sample"] = [
        {
            "day": int(d),
            "open": float(r["open"]), "close": float(r["close"]),
            "high": float(r["high"]), "low": float(r["low"]),
            "volume": float(r["volume"]), "total_turnover": float(r["total_turnover"]),
        }
        for d, r in zip(pick, sub)
    ]

# find the raw index source used by the builder
idx_inputs = [i for i in bm["inputs"] if "index" in str(i.get("role", "")).lower()]
out["index_inputs"] = [
    {k: i.get(k) for k in ["role", "path", "sha256"]} for i in idx_inputs
]

# cross-check sampled bars against the raw source file if readable
if idx_inputs:
    src = "D:/量化/" + idx_inputs[0]["path"].replace("\\", "/")
    try:
        raw = pl.read_csv(src)
        out["raw_source_columns"] = raw.columns[:12]
        dcol = [c for c in raw.columns if "date" in c.lower()]
        ccol = [c for c in raw.columns if "code" in c.lower()]
        checks = []
        for s in out["000300_sample"]:
            q = raw
            if ccol:
                q = q.filter(pl.col(ccol[0]).cast(pl.Utf8).str.contains("000300"))
            if dcol:
                q = q.filter(pl.col(dcol[0]).cast(pl.Utf8).str.contains(str(s["day"])))
            if q.height:
                row = q.row(0, named=True)
                close_candidates = {
                    k: float(v) for k, v in row.items()
                    if k.lower() in ("close", "closeindex", "close_point", "收盘价") and v is not None
                }
                checks.append({"day": s["day"], "bundle_close": s["close"], "raw_close": close_candidates})
            else:
                checks.append({"day": s["day"], "bundle_close": s["close"], "raw_close": None})
        out["cross_source_checks"] = checks
    except Exception as e:  # noqa: BLE001
        out["cross_source_error"] = repr(e)

with h5py.File(f"{BUNDLE}/yield_curve.h5", "r") as f:
    y = f["data"][:]
    tenors = [n for n in y.dtype.names if n != "date"]
    mat = np.column_stack([y[t] for t in tenors])
    out["yield_curve"] = {
        "n_rows": int(y.shape[0]),
        "tenors": tenors,
        "all_zero": bool(np.all(mat == 0.0)),
        "date_first": int(y["date"][0]),
        "date_last": int(y["date"][-1]),
    }
    td = np.load(f"{BUNDLE}/trading_dates.npy")
    out["yield_curve"]["dates_match_calendar"] = bool(np.array_equal(y["date"], td))

result("check9_placeholders", out)
print(out)
