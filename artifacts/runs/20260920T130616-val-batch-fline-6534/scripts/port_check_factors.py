# -*- coding: utf-8 -*-
"""V2 (F line) -- factor dev port check.

Rebuild of the 17 representative factor frames in VAL_WINDOW=dev mode must be
byte-identical to the F2R1 run's frozen outputs
(artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/<FAM>/<ID>.parquet).

Compared two ways: polars .equals() and sha256 of the written parquet.  Any
mismatch -> non-zero exit (prereg exp-20260920-val-batch sec 3: dev port must
pass before val is expanded; FA-S2 precedent).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import polars as pl

RUN_DIR = Path(__file__).resolve().parents[1]
F2R1 = RUN_DIR.parent / "20260919T180000-f2r1-factor-batch"
DEVDIR = RUN_DIR / "outputs" / "factor_dev"
FAMILY_DIR = {"A": "A_price", "B": "B_value", "C": "C_micro",
              "D": "D_fund", "E": "E_event", "F": "F_xsec"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


reps = sorted(pl.read_csv(
    RUN_DIR.parent / "20260919T191524-f3r1-factor-combo-c212"
    / "outputs/dedup_clusters.csv")["representative"].to_list())
assert len(reps) == 17, reps

rows = []
ok_all = True
for fid in reps:
    fam = FAMILY_DIR[fid[0]]
    ref = F2R1 / "outputs" / fam / f"{fid}.parquet"
    new = DEVDIR / fam / f"{fid}.parquet"
    if not new.exists():
        print(f"MISSING {new}")
        ok_all = False
        continue
    r, n = pl.read_parquet(ref), pl.read_parquet(new)
    eq = r.equals(n)
    sr, sn = sha256_file(ref), sha256_file(new)
    same_bytes = sr == sn
    # value-level check independent of file encoding
    j = r.join(n, on=["symbol", "signal_date"], how="full", coalesce=True,
               suffix="_new")
    max_diff = None
    if j.height:
        d = (j["value"] - j["value_new"]).abs().max()
        max_diff = None if d is None else float(d)
    rows.append({"factor": fid, "family": fam, "equals": bool(eq),
                 "sha256_ref": sr, "sha256_new": sn,
                 "bytes_identical": bool(same_bytes),
                 "rows_ref": r.height, "rows_new": n.height,
                 "max_abs_value_diff": max_diff})
    flag = "PASS" if (eq and same_bytes) else "FAIL"
    if flag == "FAIL":
        ok_all = False
    print(f"  {fid} {fam:<8} rows {r.height:>7} -> {n.height:>7} "
          f"equals={eq} bytes={same_bytes} maxdiff={max_diff} {flag}")

(RUN_DIR / "outputs" / "port_check_factors_dev.json").write_text(
    json.dumps({"stage": "factor_dev_port_check",
                "reference": str(F2R1 / "outputs"),
                "tolerance": "exact (polars .equals + parquet sha256)",
                "n_factors": len(rows),
                "all_pass": ok_all, "factors": rows},
               ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
print(f"\n== factor dev port check: {sum(1 for r in rows if r['equals'] and r['bytes_identical'])}"
      f"/{len(rows)} byte-identical ==")
sys.exit(0 if ok_all else 1)
