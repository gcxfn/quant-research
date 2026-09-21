# -*- coding: utf-8 -*-
"""手算样例独立复算（双签审阅项 9/10）。

按 hand-calc-samples.md 的场景 A/B/C 逐数复算（断言为本审阅独立编写，
与 tmp/build_artifacts.py 无共享代码），并核对该文档中每个手算数字。
另附：真实数据读入层冒烟复跑（审阅项 5 的实数据部分）。
"""
from __future__ import annotations

import sys
from datetime import date

import polars as pl

ROOT = r"D:\量化"
sys.path.insert(0, ROOT + r"\src")

from quant.backtest.band_engine import (  # noqa: E402
    load_daily_panel, load_ex_cum_factor_h5, load_stk_limit_batch,
    run_band_backtest)

D = date
SIG = {"symbol": pl.String, "signal_date": pl.Date, "side": pl.String,
       "anchor_price": pl.Float64, "priority": pl.Int64,
       "target_notional": pl.Float64, "shares": pl.Int64, "expiry_date": pl.Date}
FAILS: list[str] = []
PASS = 0


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK ] {label}")
    else:
        FAILS.append(label)
        print(f"  [FAIL] {label}")


def bars(symbol, rows):
    return pl.DataFrame({
        "symbol": [symbol] * len(rows), "date": [r[0] for r in rows],
        "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
        "tradestatus": [1.0] * len(rows)})


def auto_lim(daily):
    return daily.select("symbol", "date",
                        (pl.col("close") * 1.1).alias("limit_up"),
                        (pl.col("close") * 0.9).alias("limit_down"))


def sig(symbol, sd, side, anchor, priority=1, target=None):
    return {"symbol": symbol, "signal_date": sd, "side": side,
            "anchor_price": float(anchor), "priority": priority,
            "target_notional": None if target is None else float(target),
            "shares": None, "expiry_date": None}


print("== 样例 A（买入：触价不成交、穿透按锚价、滞后 2 日）==")
daily_a = bars("S1", [(D(2023, 8, 23), 10.30, 10.40, 10.00, 10.10),
                      (D(2023, 8, 24), 10.05, 10.20, 9.90, 10.15),
                      (D(2023, 8, 25), 10.20, 10.30, 10.05, 10.25)])
res = run_band_backtest(pl.DataFrame(
    [sig("S1", D(2023, 8, 22), "buy", 10.00, 1, 15_000)], schema=SIG),
    daily_a, auto_lim(daily_a))
check(res.events.filter((pl.col("date") == D(2023, 8, 23))
                        & (pl.col("event") == "not_penetrated")).height == 1,
      "08-23 low==p 触价 -> not_penetrated（不成交）")
fa = res.fills.row(0, named=True)
check((fa["date"], fa["shares"], fa["price"]) == (D(2023, 8, 24), 1500, 10.0),
      "08-24 穿透 -> 1500 股 @ 10.00（不取 9.90 更优价）")
check(fa["commission"] == 5.0, "佣金 max(1.5, 5) = 5.00")
check(abs(res.daily.row(1, named=True)["settled_cash"] - 184_995.0) < 1e-9,
      "现金 200,000-15,000-5 = 184,995.00")
check(fa["lag_trading_days"] == 2, "滞后 = 2 个交易日")

print("== 样例 B（卖出：重锚、双费、T+1 资金）==")
daily_b = bars("S2", [(D(2023, 8, 23), 20.10, 20.20, 19.50, 20.00),
                      (D(2023, 8, 24), 20.00, 20.30, 19.95, 20.50),
                      (D(2023, 8, 25), 20.50, 20.80, 20.40, 20.60),
                      (D(2023, 8, 28), 20.60, 20.90, 20.50, 20.70)])
res = run_band_backtest(pl.DataFrame(
    [sig("S2", D(2023, 8, 22), "buy", 20.00, 1, 20_000),
     sig("S2", D(2023, 8, 24), "sell", 20.5)], schema=SIG),
    daily_b, auto_lim(daily_b))
sb = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((sb["date"], sb["price"], sb["shares"]) == (D(2023, 8, 25), 20.5, 1000),
      "08-25 重锚 q=前收 20.50，high 20.80>q -> @20.50")
check(sb["commission"] == 5.0 and abs(sb["stamp_tax"] - 20.5) < 1e-9,
      "佣金 5.00；印花 0.1%x20,500 = 20.50（08-25 < 08-28）")
check(abs(sb["net_cash_flow"] - 20_474.5) < 1e-9, "净回笼 20,474.50")
d25 = res.daily.filter(pl.col("date") == D(2023, 8, 25)).row(0, named=True)
d28 = res.daily.filter(pl.col("date") == D(2023, 8, 28)).row(0, named=True)
check(abs(d25["settled_cash"] - 179_995.0) < 1e-9
      and abs(d25["pending_settlement"] - 20_474.5) < 1e-9,
      "08-25: settled 179,995 / pending 20,474.50")
check(abs(d28["settled_cash"] - 200_469.50) < 1e-9, "08-28 解冻后现金 200,469.50")

print("== 样例 C（K=3 兜底）+ 文档 limit_down 数字核对 ==")
daily_c = bars("KA", [(D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),
                      (D(2016, 6, 2), 29.8, 29.9, 29.0, 29.5),
                      (D(2016, 6, 3), 29.4, 29.4, 28.6, 29.0),
                      (D(2016, 6, 6), 28.9, 28.9, 28.2, 28.5),
                      (D(2016, 6, 7), 27.5, 27.6, 27.0, 27.4)])
res = run_band_backtest(pl.DataFrame(
    [sig("KA", D(2016, 5, 31), "buy", 30.00, 1, 30_000),
     sig("KA", D(2016, 6, 1), "sell", 30.0)], schema=SIG),
    daily_c, auto_lim(daily_c))
streaks = res.events.filter(pl.col("event") == "not_penetrated").sort("date")
check(streaks["limit_price"].to_list() == [30.0, 29.5, 29.0],
      "逐日重锚 30.0/29.5/29.0，3 日未成交")
fc = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((fc["fill_type"], fc["date"], fc["price"], fc["shares"]) ==
      ("market_fallback", D(2016, 6, 7), 27.5, 1000), "第 4 挂单日开盘 27.50 市价退出")
check(abs(fc["net_cash_flow"] - 27_467.5) < 1e-9,
      "净回笼 27,500-5-27.5 = 27,467.50")
k3 = res.stats["k3_fallback"]
check(abs(k3["pnl_contribution_total"] - (-1_032.50)) < 1e-9,
      "兜底损益 = 27,467.5 - 1000x28.5 = -1,032.50")
# 文档核对：hand-calc-samples.md 写 "limit_down 25.65x(1+1e-4)"；
# 实际合成 limits = 当日收盘 x0.9 = 27.4x0.9 = 24.66（25.65 = 前收 28.5x0.9，非喂入值）
fed_down = 27.4 * 0.9
print(f"    文档所写 limit_down = 25.65；实际喂入引擎的 06-07 limit_down = {fed_down:.2f}")
check(abs(fed_down - 24.66) < 1e-9 and fed_down != 25.65,
      "文档样例 C 的 limit_down 数字(25.65)与实际喂入值(24.66)不符（结论不受影响）")

print()
print(f"手算复算断言: {PASS} passed, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print("  FAILED:", f)

# --- 真实数据读入层冒烟（只读，复核 manifest read_layer_smoke） --------------
if "--real" in sys.argv:
    print("\n== 真实数据读入层冒烟复跑（只读）==")
    frame, meta = load_daily_panel(ROOT + r"\data\processed\baostock-daily-20260917\daily_1999_2024.parquet")
    print(f"  daily: {meta['rows_total']} -> {meta['rows_after_freeze_filter']} rows, "
          f"max {frame['date'].max()}, dropped {meta['rows_dropped_by_freeze']}")
    ok1 = (meta["rows_after_freeze_filter"] == 16_344_349
           and str(frame["date"].max()) == "2024-12-31"
           and meta["rows_dropped_by_freeze"] == 0)
    lim, lm = load_stk_limit_batch(ROOT + r"\data\raw\tushare\stk_limit\20260917-r1")
    print(f"  stk_limit: {lm['chunks']} chunks -> {lm['rows_after_freeze_filter']} rows, "
          f"{lim['symbol'].n_unique()} symbols, max {lim['date'].max()}")
    ok2 = (lm["chunks"] == 2431 and lm["rows_after_freeze_filter"] == 9_705_448
           and str(lim["date"].max()) == "2024-12-31")
    exf, em = load_ex_cum_factor_h5(ROOT + r"\data\processed\rqalpha-bundle-v2-1-20260918\ex_cum_factor.h5")
    print(f"  ex_cum_factor: {em['keys']} keys -> {em['rows']} rows, max {exf['ex_date'].max()}")
    ok3 = (em["keys"] == 5914 and em["rows"] == 33_933
           and str(exf["ex_date"].max()) == "2024-12-31")
    print(f"  read-layer smoke vs manifest: daily {'OK' if ok1 else 'MISMATCH'}, "
          f"stk_limit {'OK' if ok2 else 'MISMATCH'}, exf {'OK' if ok3 else 'MISMATCH'}")
    if not (ok1 and ok2 and ok3):
        sys.exit(1)
sys.exit(1 if FAILS else 0)
