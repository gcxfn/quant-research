# -*- coding: utf-8 -*-
"""冻结线读入层独立验证（双签审阅项 5）。

自建含 2025 行的合成 parquet / stk_limit chunk CSV（全部放系统 TEMP），
走引擎的 loader 与 assert_frozen / run_band_backtest，验证：
 1) load_daily_panel 过滤 2025 行并在 meta 中如实报告；
 2) load_stk_limit_batch 处理 CRLF 列名 + 过滤 2025 行；
 3) 混入 2025 行的 daily 直接进 run_band_backtest 必须在计算前中止；
 4) signals/expiry 含 2025 日期同样中止。
只读仓库；全部临时文件写 TEMP。
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(r"D:\量化")
sys.path.insert(0, str(ROOT / "src"))

import polars as pl

from quant.backtest.band_engine import (
    BandContractError, assert_frozen, load_daily_panel, load_stk_limit_batch,
    run_band_backtest)

D = date
tmp = Path(tempfile.mkdtemp(prefix="p3r1_review_freeze_"))
results: list[tuple[bool, str]] = []


def record(ok: bool, label: str) -> None:
    results.append((ok, label))
    print(f"[{'OK ' if ok else 'FAIL'}] {label}")


def bars(symbol, rows):
    return pl.DataFrame({
        "symbol": [symbol] * len(rows), "date": [r[0] for r in rows],
        "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
        "tradestatus": [1.0] * len(rows)})


# 1) mixed-year parquet through load_daily_panel -----------------------------
mixed = pl.concat([
    bars("Z1", [(D(2024, 12, 30), 10.0, 10.2, 9.9, 10.0)]),
    bars("Z1", [(D(2025, 1, 2), 10.0, 10.2, 9.9, 10.0)]),
    bars("Z1", [(D(2025, 6, 30), 11.0, 11.2, 10.9, 11.0)]),
])
pq = tmp / "mixed.parquet"
mixed.write_parquet(pq)
frame, meta = load_daily_panel(pq)
record(frame["date"].max() == D(2024, 12, 30),
       f"load_daily_panel max date {frame['date'].max()} == 2024-12-30")
record(meta["rows_total"] == 3 and meta["rows_dropped_by_freeze"] == 2,
       f"load_daily_panel meta: total={meta['rows_total']} dropped={meta['rows_dropped_by_freeze']} (want 3/2)")

# 2) stk_limit batch with CRLF headers and a 2025 row ------------------------
batch = tmp / "stk_batch"
batch.mkdir()
(batch / "chunk_000.csv").write_bytes(
    b"ts_code,trade_date,up_limit,down_limit\r\n"
    b"000001.SZ,20241230,11.0,9.0\r\n"
    b"000001.SZ,20250102,11.0,9.0\r\n")   # one 2025 row
(batch / "chunk_001.csv").write_bytes(
    b"ts_code,trade_date,up_limit,down_limit\r\n"
    b"600000.SH,20241231,11.5,9.5\r\n")
lim, lmeta = load_stk_limit_batch(batch)
record(lim["date"].max() == D(2024, 12, 31),
       f"load_stk_limit_batch max date {lim['date'].max()} == 2024-12-31")
record(set(lim["symbol"].to_list()) == {"sz.000001", "sh.600000"},
       f"CRLF column handling + ts_code mapping -> {sorted(set(lim['symbol'].to_list()))}")
record(lmeta["rows_after_freeze_filter"] == 2 and lmeta["chunks"] == 2,
       f"stk_limit meta: chunks={lmeta['chunks']} rows_after={lmeta['rows_after_freeze_filter']} (want 2/2)")

# 3) daily frame containing a 2025 row must abort run_band_backtest ----------
try:
    sig_frame = pl.DataFrame([{
        "symbol": "Z1", "signal_date": D(2024, 12, 30), "side": "buy",
        "anchor_price": 10.0, "priority": 1, "target_notional": 10_000.0,
        "shares": None, "expiry_date": None}])
    run_band_backtest(sig_frame, mixed, lim.drop("date").head(0) if False else
                      pl.DataFrame({"symbol": ["Z1"], "date": [D(2024, 12, 30)],
                                    "limit_up": [11.0], "limit_down": [9.0]}))
    record(False, "run_band_backtest with 2025 daily row: DID NOT ABORT")
except BandContractError as e:
    record("freeze violation" in str(e),
           f"run_band_backtest aborts on 2025 daily row: {str(e)[:60]}…")

# 4) signals with a 2025 signal_date must abort ------------------------------
try:
    bad_sig = pl.DataFrame([{
        "symbol": "Z1", "signal_date": D(2025, 1, 2), "side": "buy",
        "anchor_price": 10.0, "priority": 1, "target_notional": 10_000.0,
        "shares": None, "expiry_date": None}])
    ok_daily = bars("Z1", [(D(2024, 12, 30), 10.0, 10.2, 9.9, 10.0)])
    run_band_backtest(bad_sig, ok_daily,
                      pl.DataFrame({"symbol": ["Z1"], "date": [D(2024, 12, 30)],
                                    "limit_up": [11.0], "limit_down": [9.0]}))
    record(False, "run_band_backtest with 2025 signal_date: DID NOT ABORT")
except BandContractError as e:
    record("freeze violation" in str(e),
           f"run_band_backtest aborts on 2025 signal_date: {str(e)[:60]}…")

# 5) 2025 expiry_date must abort ---------------------------------------------
try:
    exp_sig = pl.DataFrame([{
        "symbol": "Z1", "signal_date": D(2024, 12, 30), "side": "buy",
        "anchor_price": 10.0, "priority": 1, "target_notional": 10_000.0,
        "shares": None, "expiry_date": D(2025, 3, 1)}])
    run_band_backtest(exp_sig, ok_daily,
                      pl.DataFrame({"symbol": ["Z1"], "date": [D(2024, 12, 30)],
                                    "limit_up": [11.0], "limit_down": [9.0]}))
    record(False, "run_band_backtest with 2025 expiry_date: DID NOT ABORT")
except BandContractError as e:
    record("freeze violation" in str(e),
           f"run_band_backtest aborts on 2025 expiry_date: {str(e)[:60]}…")

# 6) assert_frozen rejects 2025 with row count in the message ----------------
try:
    assert_frozen(mixed, "date", "daily")
    record(False, "assert_frozen accepted 2025 rows")
except BandContractError as e:
    record("2025-06-30" in str(e) and "(2 rows)" in str(e),
           f"assert_frozen message cites max date and bad-row count: {str(e)[:110]}…")

print()
n_fail = sum(1 for ok, _ in results if not ok)
print(f"RESULT: {len(results) - n_fail}/{len(results)} freeze checks passed; tmp={tmp}")
sys.exit(1 if n_fail else 0)
