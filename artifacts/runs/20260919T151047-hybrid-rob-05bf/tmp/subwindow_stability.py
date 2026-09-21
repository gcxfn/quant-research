# -*- coding: utf-8 -*-
"""Zero-cost sub-window stability analysis (rob prereg sec 3; no new trials).

Slices EXISTING artifacts only:
- v3 run 20260919T110500-hybrid-v3-r3ld/outputs/R3-05_daily_equity.parquet
  and R3-06_daily_equity.parquet (dev equity curves, 2015-2020);
- R16 run 20260918T083650-p2r16-trend-dispersion-afab466f/equity_curves.parquet,
  config B1-T200-40-rate_only (the family B1(m) benchmark).

Readout: two-year blocks (2015-16 / 2017-18 / 2019-20) block return, block
maxDD, block CAGR; per-year net returns and per-year excess vs B1m.  Metric
semantics replicate the runner helpers (etf_rotation.cagr / max_drawdown /
year_returns).  Output: outputs/subwindow_stability.json.
"""
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]           # run dir
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402
import quant.research.etf_rotation as er  # noqa: E402

V3_RUN = ROOT / "artifacts/runs/20260919T110500-hybrid-v3-r3ld"
R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
B1_NAME = "B1-T200-40-rate_only"
DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
BLOCKS = [("2015-16", date(2015, 1, 1), date(2016, 12, 31)),
          ("2017-18", date(2017, 1, 1), date(2018, 12, 31)),
          ("2019-20", date(2019, 1, 1), date(2020, 12, 31))]


def sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


curves: dict[str, tuple[list, list]] = {}
src_identity: dict[str, dict] = {}
for cid, path in (("R3-05", V3_RUN / "outputs/R3-05_daily_equity.parquet"),
                  ("R3-06", V3_RUN / "outputs/R3-06_daily_equity.parquet")):
    df = pl.read_parquet(path)
    sub = df.filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
    curves[cid] = (sub["date"].to_list(), sub["equity"].to_list())
    src_identity[cid] = {"path": str(path), "sha256_16": sha16(path),
                         "rows": df.height}
eq = pl.read_parquet(R16_RUN / "equity_curves.parquet")
b1 = eq.filter(pl.col("config_id") == B1_NAME).sort("session")
b1 = b1.filter((pl.col("session") >= DEV_START)
               & (pl.col("session") <= DEV_END))
curves["B1m"] = (b1["session"].to_list(), b1["equity_net"].to_list())
src_identity["B1m"] = {"path": str(R16_RUN / "equity_curves.parquet"),
                       "sha256_16": sha16(R16_RUN / "equity_curves.parquet"),
                       "rows": eq.height, "config_id": B1_NAME}

out: dict = {"experiment_id": "exp-20260919-hybrid-robustness",
             "purpose": "rob prereg sec 3 zero-cost sub-window analysis "
                        "(existing artifacts only; no new trials)",
             "metric_semantics": "etf_rotation.cagr / max_drawdown / "
                                 "year_returns verbatim (runner helpers)",
             "sources": src_identity, "configs": {}}

years_all = sorted({d.year for d, _ in zip(*curves["B1m"])})
for cid, (ds, vs) in curves.items():
    yr = er.year_returns(ds, vs)
    blocks = {}
    prev_mark = vs[0]
    prev_mark_d = ds[0]
    for bname, b0, b1e in BLOCKS:
        bd = [d for d in ds if b0 <= d <= b1e]
        bv = [v for d, v in zip(ds, vs) if b0 <= d <= b1e]
        blk = {"block_return": bv[-1] / prev_mark - 1.0,
               "max_drawdown": er.max_drawdown(bd, bv)["max_drawdown"],
               "cagr": er.cagr(prev_mark, bv[-1], prev_mark_d, bd[-1])}
        blocks[bname] = blk
        prev_mark, prev_mark_d = bv[-1], bd[-1]
    out["configs"][cid] = {"net_return_by_year": {int(k): v for k, v
                                                  in yr.items()},
                           "blocks": blocks,
                           "full_dev_cagr": er.cagr(vs[0], vs[-1],
                                                    ds[0], ds[-1]),
                           "full_dev_max_drawdown":
                               er.max_drawdown(ds, vs)["max_drawdown"]}

for cid in ("R3-05", "R3-06"):
    b1y = out["configs"]["B1m"]["net_return_by_year"]
    out["configs"][cid]["excess_by_year_vs_B1m"] = {
        y: out["configs"][cid]["net_return_by_year"][y] - b1y[y]
        for y in sorted(b1y)}
    out["configs"][cid]["excess_by_block_vs_B1m"] = {
        b: out["configs"][cid]["blocks"][b]["block_return"]
        - out["configs"]["B1m"]["blocks"][b]["block_return"]
        for b, _, _ in BLOCKS}

dst = HERE / "outputs" / "subwindow_stability.json"
dst.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str),
               encoding="utf-8")
print(f"written {dst}")
for cid in ("R3-05", "R3-06", "B1m"):
    c = out["configs"][cid]
    yrs = {k: round(v, 4) for k, v in c["net_return_by_year"].items()}
    blks = {b: {"ret": round(v["block_return"], 4),
                "mdd": round(v["max_drawdown"], 4)}
            for b, v in c["blocks"].items()}
    print(cid, "years", yrs, "blocks", blks)
