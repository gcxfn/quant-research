# -*- coding: utf-8 -*-
"""Check 8: instruments.pk sampled entries vs stock_basic / fund_basic raw files."""
import glob
import sys

import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import RAW, SEED, h5_keys, load_instruments, oid_to_ts, result  # noqa: E402

import numpy as np

rng = np.random.default_rng(SEED)
out = {"seed": SEED}
inst = {i["order_book_id"]: i for i in load_instruments()}
stock_keys = h5_keys("stocks.h5")
fund_keys = h5_keys("funds.h5")

stock_sample = ["000001.XSHE"] + sorted(rng.choice([k for k in stock_keys if k != "000001.XSHE"], size=2, replace=False).tolist())
fund_sample = ["510300.XSHG"] + sorted(rng.choice([k for k in fund_keys if k != "510300.XSHG"], size=1, replace=False).tolist())

import os

sb = pl.concat(
    [pl.read_csv(p) for p in sorted(glob.glob(f"{RAW}/stock_basic/20260909-r3/chunk_*.csv")) if os.path.getsize(p) > 0],
    how="vertical_relaxed",
)
fb = pl.read_csv(f"{RAW}/fund_basic/20260909-r1/chunk_market_E.csv")

records = []
for oid in stock_sample:
    ts = oid_to_ts(oid)
    i = inst[oid]
    r = sb.filter(pl.col("ts_code") == ts)
    records.append({
        "oid": oid,
        "instrument": {k: i.get(k) for k in ["order_book_id", "symbol", "type", "round_lot", "listed_date", "de_listed_date", "board_type", "market_tplus"]},
        "stock_basic_row": r.select(["ts_code", "name", "list_status", "list_date", "delist_date"]).to_dicts()[0] if r.height else None,
    })
for oid in fund_sample:
    ts = oid_to_ts(oid)
    i = inst[oid]
    r = fb.filter(pl.col("ts_code") == ts)
    row = r.select(["ts_code", "name", "found_date", "list_date", "delist_date", "market"]).to_dicts()[0] if r.height else None
    records.append({
        "oid": oid,
        "instrument": {k: i.get(k) for k in ["order_book_id", "symbol", "type", "round_lot", "listed_date", "de_listed_date", "market_tplus"]},
        "fund_basic_row": row,
    })
out["records"] = records

# type counts + INDX identity
types = {}
for i in load_instruments():
    types[i["type"]] = types.get(i["type"], 0) + 1
out["types"] = types
out["indx"] = [i for i in load_instruments() if i["type"] == "INDX"]
result("check8_instruments", out)
print(out)
