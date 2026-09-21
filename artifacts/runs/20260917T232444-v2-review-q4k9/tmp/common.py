# -*- coding: utf-8 -*-
"""Shared helpers for the v2 bundle independent review (read-only)."""
import json
import pickle

import h5py
import numpy as np

BUNDLE = "D:/量化/data/processed/rqalpha-bundle-v2-20260917"
RUN = "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9"
RAW = "D:/量化/data/raw/tushare"
SEED = 20260917


def oid_to_ts(oid: str) -> str:
    code, exch = oid.split(".")
    suffix = {"XSHG": "SH", "XSHE": "SZ"}[exch]
    return f"{code}.{suffix}"


def load_instruments():
    with open(f"{BUNDLE}/instruments.pk", "rb") as fh:
        return pickle.load(fh)


def h5_keys(name):
    with h5py.File(f"{BUNDLE}/{name}", "r") as f:
        return list(f.keys())


def result(name, payload):
    path = f"{RUN}/tmp/{name}.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)
    print(f"[saved] {path}")


def max_abs(a, b):
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    if a.size == 0:
        return 0.0
    return float(np.nanmax(np.abs(a - b)))
