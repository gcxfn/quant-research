# -*- coding: utf-8 -*-
"""Diagnostic (tmp): why does the dev-window C05 port differ from the R16 run
metrics by ~1.5e-4 while every leg_log row is byte-identical?"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src"))

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)

cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days_dev = all_mes["s"].to_list()
sig_days = [d for d in sig_days_dev
            if idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
print("signals", len(sig_days), sig_days[0], sig_days[-1])

index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
exposures = r16.t200_month_end_exposures(index_close, calendar_full, sig_days)
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
bank_syms = sorted({s for t in sig_days for s in pools_at[t]["ranked"]})
bank = r16.PriceBank(hist, calendar_full, bank_syms)
print("bank symbols", len(bank_syms))

spec = json.loads((ROOT / "configs/experiments/p2r16-trend-dispersion.json")
                  .read_text(encoding="utf-8"))["configs"]["C05"]
K = int(spec["K"])
res = r16.simulate_r16("probe-C05", bank, calendar_full, DEV_START, sig_days,
                       pools_at, exposures, K=K,
                       membership_fn=lambda p, r, q, rng:
                       r16.buffer_membership(p, r, q, K,
                                             spec["filter"] == "on"))
m = r16.segment_metrics(res, DEV_START, DEV_END, None)
ref = json.loads((R16_RUN / "metrics.json").read_text(
    encoding="utf-8"))["configs"]["C05"]
print("--- metric diffs (mine - r16) ---")
for k in sorted(set(m) & set(ref)):
    a, b = m[k], ref[k]
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        print(f"  {k:34s} mine={a!r:24s} r16={b!r:24s} diff={a - b:.6e}")
for k in ("net_return_by_year", "turnover_by_year"):
    if k in m and k in ref:
        for y in ref[k]:
            a, b = m[k].get(y), ref[k].get(y)
            if isinstance(b, dict):
                for kk in b:
                    d = (a[kk] - b[kk]) if (a and a[kk] is not None
                                            and b[kk] is not None) else None
                    print(f"  {k}[{y}][{kk}] diff={d}")
            else:
                print(f"  {k}[{y}] diff={(a - b) if (a is not None and b is not None) else None}")

# equity comparison against the published curve
cur = pl.read_parquet(R16_RUN / "equity_curves.parquet").filter(
    pl.col("config_id") == "C05").sort("session")
mine = pl.DataFrame({"session": res.sessions, "equity_net": res.equity})
j = mine.join(cur, on="session", how="inner", suffix="_r16")
j = j.with_columns((pl.col("equity_net") - pl.col("equity_net_r16"))
                   .alias("d"))
nonz = j.filter(pl.col("d").abs() > 1e-9)
print("equity rows joined", j.height, "differing", nonz.height)
if nonz.height:
    print(nonz.head(5))
    print(nonz.tail(5))
    print("max|d|", nonz["d"].abs().max())
