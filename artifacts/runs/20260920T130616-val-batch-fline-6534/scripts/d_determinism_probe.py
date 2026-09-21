# -*- coding: utf-8 -*-
"""V2 (F line) -- D-family pipeline determinism probe (no window consumed).

The F2R1 frozen D_fund parquets (build_d_fund_main.py, run 2026-09-19 18:19)
cannot be reproduced by a fresh run of the shipped script: 7 of the 17
representative factors differ in value and in key set, and one §2 survivor
verdict flips (D12 t 2.07 -> 2.00).  The raw inputs are byte-identical to the
2026-09-17 deep-scan baseline (23,622 files re-hashed, 0 mismatches), so the
difference is not a data change.

This probe isolates the suspect: pit_full()'s

    df.sort("ann_date", nulls_last=True).group_by(ts_code, end_date).last()

whose within-group order is not specified by polars (group_by has
maintain_order=False).  It compares that expression with its explicitly
ordered equivalent on the same frame, and repeats the whole pit_full pass to
test run-to-run stability.  Read-only; nothing is written except the report.
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys
import time
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
RUN_DIR = Path(__file__).resolve().parents[1]
TS = ROOT / "data/raw/tushare"
NUM_FINA = ["eps", "bps", "roe", "roa", "grossprofit_margin", "netprofit_margin",
            "debt_to_assets", "current_ratio", "netprofit_yoy", "tr_yoy",
            "ocf_yoy", "assets_turn", "q_sales_yoy", "q_roe", "profit_dedt",
            "ocfps"]
KEYS = ["ts_code", "ann_date", "f_ann_date", "end_date"]


def read_fina(dataset, cols):
    frames = []
    for p in sorted(TS.glob(f"{dataset}/*/chunk_*.csv")):
        if p.stat().st_size <= 100:
            continue
        df = pl.read_csv(p, infer_schema_length=20000)
        if df.height:
            have = ([c for c in KEYS if c in df.columns]
                    + [c for c in cols if c in df.columns])
            df = df.select(have).with_columns(
                [pl.col(c).cast(pl.Float64, strict=False) for c in cols
                 if c in df.columns])
            frames.append(df)
    return pl.concat(frames, how="diagonal")


def prep(df):
    for col in ("ann_date", "f_ann_date"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.String).alias(col))
    return df.with_columns(
        pl.col("ann_date").cast(pl.String).str.strip_chars()
        .str.to_date("%Y%m%d", strict=False),
        pl.col("f_ann_date").cast(pl.String).str.strip_chars()
        .str.to_date("%Y%m%d", strict=False),
        pl.col("end_date").cast(pl.String).str.strip_chars()
        .str.to_date("%Y%m%d", strict=False),
    )


t0 = time.time()
raw = prep(read_fina("fina_indicator", NUM_FINA))
print(f"[{time.time()-t0:6.1f}s] fina rows {raw.height}", flush=True)

out: dict = {"stage": "d_pipeline_determinism_probe",
             "question": ("is the frozen D pipeline's (ts_code,end_date) "
                          "revision tie-break reproducible?"),
             "probe_frame": "tushare/fina_indicator (dev window inputs)",
             "rows_raw": raw.height}

# --- A. the frozen expression, twice in one process -------------------------
hashes = []
frames = []
for i in range(2):
    f = (raw.sort("ann_date", nulls_last=True)
         .group_by("ts_code", "end_date").last())
    frames.append(f)
    h = hashlib.sha256(
        f.sort("ts_code", "end_date").select(
            ["ts_code", "end_date", "ann_date"]).write_csv(None).encode()
    ).hexdigest()
    hashes.append(h)
out["A_frozen_expression_repeat_stable"] = hashes[0] == hashes[1]
out["A_hashes"] = hashes
print(f"  A frozen expression twice identical: "
      f"{out['A_frozen_expression_repeat_stable']}", flush=True)

# --- B. frozen expression vs explicitly ordered equivalent ------------------
frozen = frames[0].select(["ts_code", "end_date", "ann_date", "f_ann_date"])
explicit = (raw.sort(["ts_code", "end_date", "ann_date"], nulls_last=True)
            .group_by("ts_code", "end_date", maintain_order=True).last()
            .select(["ts_code", "end_date", "ann_date", "f_ann_date"]))
j = frozen.join(explicit, on=["ts_code", "end_date"], how="inner",
                suffix="_ex")
d_ann = j.filter(
    (pl.col("ann_date") != pl.col("ann_date_ex"))
    | (pl.col("ann_date").is_null() != pl.col("ann_date_ex").is_null()))
out["B_rows_frozen"] = frozen.height
out["B_rows_explicit"] = explicit.height
out["B_rows_differing_ann_date"] = d_ann.height
# also compare against the documented rule's output value-wise for a numeric col
frozen_v = (raw.sort("ann_date", nulls_last=True)
            .group_by("ts_code", "end_date").last()
            .select(["ts_code", "end_date", "bps"]))
explicit_v = (raw.sort(["ts_code", "end_date", "ann_date"], nulls_last=True)
              .group_by("ts_code", "end_date", maintain_order=True).last()
              .select(["ts_code", "end_date", "bps"]))
jv = frozen_v.join(explicit_v, on=["ts_code", "end_date"], how="inner",
                   suffix="_ex")
b_bps = jv.filter(
    (pl.col("bps") - pl.col("bps_ex")).abs().fill_null(0) > 0).height
out["B_rows_differing_bps"] = b_bps
print(f"  B frozen vs explicitly-ordered: rows {frozen.height}/{explicit.height}"
      f"; differing ann_date {d_ann.height}; differing bps {b_bps}", flush=True)

# --- C. does raw contain 2025+ announcements inside the dev end_date range? --
if "end_date" in raw.columns:
    late = raw.filter(pl.col("ann_date") > pl.date(2024, 12, 31))
    late_devend = raw.filter(
        (pl.col("ann_date") > pl.date(2024, 12, 31))
        & (pl.col("end_date") <= pl.date(2020, 12, 31)))
    out["C_rows_ann_after_2024"] = late.height
    out["C_rows_ann_after_2024_with_end_date_le_2020"] = late_devend.height
    out["C_ann_date_max"] = str(raw["ann_date"].max())
    print(f"  C fina rows with ann_date > 2024-12-31: {late.height}; of which "
          f"end_date <= 2020-12-31: {late_devend.height}; max ann_date "
          f"{out['C_ann_date_max']}", flush=True)

out["wall_seconds"] = time.time() - t0
(RUN_DIR / "outputs" / "d_pipeline_determinism_probe.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8",
    newline="\n")
print(f"== probe done in {out['wall_seconds']:.0f}s ==", flush=True)
