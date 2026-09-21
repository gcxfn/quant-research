# -*- coding: utf-8 -*-
"""双签审阅 · 对抗用例（审阅项 3/4/7）。

引擎作者与既有测试未覆盖的场景，全部内联合成数据，只读仓库：
  a) 同日多买单现金只够高优先级 -> 低优先级作废、次日重挂成交（资金来自 T+1 解冻）；
  b) 买入成交日即有同名义卖单（T+1 边界）-> 顺延日计入 K 计数，第 4 个挂单日市价兜底；
  c) 除权日 x 卖出重锚：
     c1 纯现金分红除息日：q 取除息前收盘、次日重锚除息后收盘；
     c2 10 送 5：除权日 q=除权前收盘越界作废（真实口径涨跌停），次日按除权后收盘成交；
     c3 反向拆分 1:2：真实口径涨跌停 -> 越界作废（保护）；naive 涨跌停 -> 按除权前锚价
        成交于除权后市场（数据质量依赖性演示）；
  d) 武装市价兜底后连续 5 日开盘跌停 -> 反复顺延、限价单并行工作、首个非跌停开盘退出；
  e1) 佣金 guard 恰在 5 万名义边界（不报警 / 越界报警）；
  e2) 份额调整 half-up 取整方向（100 x 1.035 -> 104，截断会得 103）+ 整手不变量-letter 冲突；
  e3) 武装市价单遇长期停牌 -> 停牌冻结 K、复牌跌停顺延、再下一日退出（无死锁）；
  e5) 已有持仓 + 当日同名义买单成交 -> 卖单整体顺延（保守），次日全额退出；
  e7) 武装执行日涨跌停数据缺失 -> 市价兜底照常执行（裁定 #2）。
"""
from __future__ import annotations

import math
import sys
from datetime import date

import polars as pl

ROOT = r"D:\量化"
sys.path.insert(0, ROOT + r"\src")

from quant.backtest.band_engine import run_band_backtest  # noqa: E402

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


def sig(symbol, sd, side, anchor, priority=1, target=None, shares=None):
    return {"symbol": symbol, "signal_date": sd, "side": side,
            "anchor_price": float(anchor), "priority": priority,
            "target_notional": None if target is None else float(target),
            "shares": shares, "expiry_date": None}


def bars(symbol, rows, suspended=()):
    """rows: (date, o, h, l, c); suspended dates get a tradestatus=0 bar."""
    out = {"symbol": [], "date": [], "open": [], "high": [], "low": [],
           "close": [], "tradestatus": []}
    for r in rows:
        out["symbol"].append(symbol)
        out["date"].append(r[0])
        out["open"].append(float(r[1]))
        out["high"].append(float(r[2]))
        out["low"].append(float(r[3]))
        out["close"].append(float(r[4]))
        out["tradestatus"].append(0.0 if r[0] in suspended else 1.0)
    return pl.DataFrame(out)


def lim_rows(rows):
    """rows: (symbol, date, up, down)."""
    return pl.DataFrame({"symbol": [r[0] for r in rows],
                         "date": [r[1] for r in rows],
                         "limit_up": [float(r[2]) for r in rows],
                         "limit_down": [float(r[3]) for r in rows]})


def auto_lim(daily):
    return daily.select("symbol", "date",
                        (pl.col("close") * 1.1).alias("limit_up"),
                        (pl.col("close") * 0.9).alias("limit_down"))


def run(signals, daily, limits, exf=None, divs=None, cash=200_000.0):
    return run_band_backtest(pl.DataFrame(signals, schema=SIG), daily, limits,
                             exf, divs, initial_cash=cash)


def ev(res, event, symbol=None):
    f = res.events.filter(pl.col("event") == event)
    if symbol:
        f = f.filter(pl.col("symbol") == symbol)
    return f


# =============================================================================
print("== case a: 同日多买单现金只够高优先级；低优先级作废后次日（T+1 解冻资金）成交 ==")
D1, D2, D3, D4 = D(2024, 1, 2), D(2024, 1, 3), D(2024, 1, 4), D(2024, 1, 5)
daily = pl.concat([
    bars("A0", [(D1, 100.2, 100.5, 99.9, 100.0),
                (D2, 100.0, 100.5, 99.8, 100.2),
                (D3, 100.3, 100.6, 100.1, 100.4),
                (D4, 100.5, 100.8, 100.3, 100.6)]),
    bars("P1", [(D2, 50.2, 50.5, 49.9, 50.0),
                (D3, 50.1, 50.4, 50.0, 50.2),
                (D4, 50.2, 50.5, 50.1, 50.3)]),
    bars("P2", [(D2, 100.2, 100.5, 99.9, 100.0),
                (D3, 100.1, 100.4, 99.95, 100.2),
                (D4, 100.2, 100.5, 100.1, 100.3)]),
])
signals = [
    sig("A0", D(2024, 1, 1), "buy", 100.0, 0, shares=500),
    sig("A0", D1, "sell", 100.0, 0),
    sig("P1", D1, "buy", 50.0, 1, target=150_000),
    sig("P2", D1, "buy", 100.0, 2, target=40_000),
]
res = run(signals, daily, auto_lim(daily), cash=210_000.0)
p2_void = res.events.filter((pl.col("symbol") == "P2") & (pl.col("date") == D2))
check(p2_void["event"].to_list() == ["void_insufficient_cash"],
      f"P2 在 D2 因现金不足作废: {p2_void['event'].to_list()}")
p2 = res.fills.filter((pl.col("symbol") == "P2")).row(0, named=True)
check((p2["date"], p2["shares"], p2["price"]) == (D3, 400, 100.0),
      f"P2 次日重挂并成交 D3 400@100: {(p2['date'], p2['shares'], p2['price'])}")
a0s = res.fills.filter((pl.col("symbol") == "A0") & (pl.col("side") == "sell")).row(0, named=True)
check((a0s["date"], a0s["price"]) == (D2, 100.0), f"A0 卖出 D2@100: {(a0s['date'], a0s['price'])}")
# 2024 印花 0.05%: 净回笼 = 50,000 - 5 - 25 = 49,970
check(abs(a0s["net_cash_flow"] - 49_970.0) < 1e-9,
      f"A0 净回笼 = 50,000-5-25(印花0.05%) = 49,970: {a0s['net_cash_flow']}")
d2 = res.daily.filter(pl.col("date") == D2).row(0, named=True)
check(abs(d2["settled_cash"] - 9_980.0) < 1e-9 and abs(d2["pending_settlement"] - 49_970.0) < 1e-9,
      f"D2 结算现金 9,980 / pending 49,970: {(d2['settled_cash'], d2['pending_settlement'])}")
d3 = res.daily.filter(pl.col("date") == D3).row(0, named=True)
check(abs(d3["settled_cash"] - 19_945.0) < 1e-9,
      f"D3 = 9,980 + 49,970 - 40,005 = 19,945: {d3['settled_cash']}")
check((res.daily["settled_cash"] >= 0).all(), "全程现金非负")
check(res.stats["cash_friction"]["insufficient_cash_days"] == 1, "insufficient_cash_days == 1")
check(res.stats["commission_warnings"] == 1, f"P1 名义 15 万触发 guard 恰 1 次: {res.stats['commission_warnings']}")

# =============================================================================
print("== case b: 买入成交日即有同名义卖单（T+1 边界），顺延日计入 K -> 第 4 挂单日兜底 ==")
B1, B2, B3, B4 = D(2024, 2, 5), D(2024, 2, 6), D(2024, 2, 7), D(2024, 2, 8)
daily = bars("S", [(B1, 9.9, 10.0, 9.85, 9.8),
                   (B2, 9.7, 9.7, 9.3, 9.4),
                   (B3, 9.3, 9.3, 8.9, 9.0),
                   (B4, 8.5, 8.6, 8.4, 8.55)])
res = run([sig("S", D(2024, 2, 4), "buy", 10.0, 1, target=20_000),
           sig("S", D(2024, 2, 4), "sell", 10.0, 1)], daily, auto_lim(daily))
t1 = ev(res, "t1_deferred").row(0, named=True)
check(t1["date"] == B1, f"卖出在买入成交日 B1 整体顺延: {t1['date']}")
streaks = ev(res, "not_penetrated").sort("date")
check(streaks["date"].to_list() == [B2, B3], f"未穿透日 B2,B3: {streaks['date'].to_list()}")
sf = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((sf["fill_type"], sf["date"], sf["price"], sf["shares"]) ==
      ("market_fallback", B4, 8.5, 2000),
      f"第 4 个挂单日市价兜底 B4@8.5 x2000: {(sf['fill_type'], sf['date'], sf['price'], sf['shares'])}")
check(res.stats["k3_fallback"]["scheduled"] == 1 and res.stats["k3_fallback"]["executed"] == 1,
      "K scheduled/executed = 1/1（t1 顺延日计入 K：否则兜底会推到 B5）")
check(res.stats["same_bar_deferred_sells"] == 1, "same_bar_deferred == 1")
bdays = set(res.fills.filter(pl.col("side") == "buy")["date"].to_list())
sdays = set(res.fills.filter(pl.col("side") == "sell")["date"].to_list())
check(not (bdays & sdays), "T+1 零违例扫描：无同日买卖成交对")

# =============================================================================
print("== case c1: 纯现金分红除息日 x 卖出重锚 ==")
C1, C2, C3 = D(2024, 3, 4), D(2024, 3, 5), D(2024, 3, 6)
daily = bars("CD", [(C1, 10.2, 10.3, 9.95, 10.0),
                    (C2, 9.5, 9.6, 9.4, 9.5),      # 除息日
                    (C3, 9.55, 9.7, 9.5, 9.65)])
divs = pl.DataFrame({"symbol": ["CD"], "ex_date": [C2],
                     "cash_per_share_pre_tax": [0.5]})
limits = lim_rows([("CD", C1, 11.0, 9.0),
                   ("CD", C2, 10.45, 8.55),   # 真实口径：按除息参考价 9.5 +-10%
                   ("CD", C3, 10.45, 8.55)])
res = run([sig("CD", D(2024, 3, 3), "buy", 10.0, 1, target=10_000),
           sig("CD", C1, "sell", 10.0, 1)], daily, limits, divs=divs)
dv = ev(res, "corp_action_dividend").row(0, named=True)
check(dv["date"] == C2 and abs(dv["cash_amount"] - 500.0) < 1e-9,
      f"除息日现金分红 0.5 x 1000 股 = 500: {(dv['date'], dv['cash_amount'])}")
c2ev = res.events.filter((pl.col("date") == C2) & (pl.col("symbol") == "CD")).row(0, named=True)
check(c2ev["event"] == "not_penetrated" and c2ev["limit_price"] == 10.0,
      f"除息日卖单锚 = 除息前收盘 10.0（当日无除息后收盘可取）: {(c2ev['event'], c2ev['limit_price'])}")
sf = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((sf["date"], sf["price"], sf["shares"]) == (C3, 9.5, 1000),
      f"次日重锚除息后收盘 9.5 并成交: {(sf['date'], sf['price'], sf['shares'])}")

# =============================================================================
print("== case c2: 10 送 5 除权日 x 卖出重锚（真实口径涨跌停） ==")
K1, K2, K3 = D(2024, 4, 8), D(2024, 4, 9), D(2024, 4, 10)
daily = bars("SP", [(K1, 10.2, 10.3, 9.95, 10.0),
                    (K2, 6.7, 6.75, 6.6, 6.7),     # 除权日（10 送 5）
                    (K3, 6.7, 6.8, 6.65, 6.75)])
exf = pl.DataFrame({"symbol": ["SP"], "ex_date": [K2], "cum_factor": [1.5]})
limits = lim_rows([("SP", K1, 11.0, 9.0),
                   ("SP", K2, 7.333, 6.0),    # 真实口径：除权参考价 6.667 +-10%
                   ("SP", K3, 7.37, 6.03)])
res = run([sig("SP", D(2024, 4, 7), "buy", 10.0, 1, target=10_000),
           sig("SP", K1, "sell", 10.0, 1)], daily, limits, exf=exf)
k2ev = res.events.filter((pl.col("date") == K2) & (pl.col("symbol") == "SP")).row(0, named=True)
check(k2ev["event"] == "void_limit_out_of_range" and k2ev["limit_price"] == 10.0,
      f"除权日 q=除权前收盘 10.0 > limit_up 7.333 -> 越界作废（未按错误价格成交）: "
      f"{(k2ev['event'], k2ev['limit_price'])}")
sp = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((sp["date"], sp["price"], sp["shares"]) == (K3, 6.7, 1500),
      f"次日 q=除权后最新收盘 6.7，按调整后 1500 股成交: {(sp['date'], sp['price'], sp['shares'])}")

# =============================================================================
print("== case c3: 反向拆分 1:2 —— 真实 vs naive 涨跌停数据 ==")
R1, R2, R3 = D(2024, 5, 6), D(2024, 5, 7), D(2024, 5, 8)
daily_c3 = bars("RS", [(R1, 10.2, 10.3, 9.95, 10.0),
                       (R2, 20.0, 20.4, 19.8, 20.0),   # 反向拆分日（2 股并 1 股）
                       (R3, 20.1, 20.5, 19.9, 20.3)])
exf_c3 = pl.DataFrame({"symbol": ["RS"], "ex_date": [R2], "cum_factor": [0.5]})
sig_c3 = [sig("RS", D(2024, 5, 5), "buy", 10.0, 1, target=10_000),
          sig("RS", R1, "sell", 10.0, 1)]
lim_real = lim_rows([("RS", R1, 11.0, 9.0),
                     ("RS", R2, 22.0, 18.0),    # 真实口径：除权参考价 20 +-10%
                     ("RS", R3, 22.0, 18.0)])
res = run(sig_c3, daily_c3, lim_real, exf=exf_c3)
r2ev = res.events.filter((pl.col("date") == R2) & (pl.col("symbol") == "RS")).row(0, named=True)
check(r2ev["event"] == "void_limit_out_of_range",
      f"真实口径：q=10 < limit_down 18 -> 作废保护: {r2ev['event']}")
rs = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((rs["date"], rs["price"], rs["shares"]) == (R3, 20.0, 500),
      f"次日按除权后收盘 20.0 x 500 股成交: {(rs['date'], rs['price'], rs['shares'])}")
lim_naive = lim_rows([("RS", R1, 11.0, 9.0),
                      ("RS", R2, 11.0, 9.0),     # naive：未按除权调整（坏数据）
                      ("RS", R3, 22.0, 18.0)])
res2 = run(sig_c3, daily_c3, lim_naive, exf=exf_c3)
rs2 = res2.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((rs2["date"], rs2["price"]) == (R2, 10.0),
      f"naive 数据：除权日按除权前锚 10.0 成交（市价 ~20，损失 ~50%）—— 保护完全依赖 stk_limit 质量: "
      f"{(rs2['date'], rs2['price'])}")

# =============================================================================
print("== case d: 武装兜底后连续 5 日开盘跌停；限价并行；首个非跌停开盘退出 ==")
import datetime as _dt  # noqa: E402
E = [D(2024, 6, d) for d in (3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 17)]
# E0 买日; 卖 live E1,E2,E3（streak 1-3 -> 武装）; E4..E8 连续 5 日开盘跌停（顺延）;
# E9 首个非跌停开盘 -> KB 市价退出; KC 在 E6 顺延日由并行限价单成交
opens  = [30.2, 29.8, 29.4, 28.9, 25.65, 22.95, 20.52, 18.36, 16.38, 16.5, 16.6]
highs  = [30.3, 29.9, 29.4, 28.9, 25.7, 25.4, 20.6, 18.4, 16.4, 16.7, 16.8]
lows_  = [29.9, 29.0, 28.6, 28.2, 25.0, 22.3, 20.0, 18.0, 16.0, 16.1, 16.3]
closes = [30.0, 29.5, 29.0, 28.5, 25.5, 22.8, 20.4, 18.2, 16.2, 16.6, 16.7]
daily_kb = bars("KB", [(E[i], opens[i], highs[i], lows_[i], closes[i])
                       for i in range(len(E))])
kc_highs = list(highs)
kc_highs[6] = 22.9      # E6: high > q(=22.8) -> 顺延日限价成交
kc_highs[5] = 22.8      # E5: 恰不穿透（<= q 25.5）
kc_closes = list(closes)
kc_closes[6] = 22.7
daily_kc = bars("KC", [(E[i], opens[i], kc_highs[i], lows_[i], kc_closes[i])
                       for i in range(len(E))])
daily = pl.concat([daily_kb, daily_kc])
lrows = [("KB", E[0], 33.0, 27.0), ("KC", E[0], 33.0, 27.0)]
for i in range(1, len(E)):
    prev_c = closes[i - 1]
    lrows.append(("KB", E[i], prev_c * 1.1, prev_c * 0.9))
    lrows.append(("KC", E[i], prev_c * 1.1, prev_c * 0.9))
limits = lim_rows(lrows)
signals = []
for symname in ("KB", "KC"):
    signals += [sig(symname, E[0] - _dt.timedelta(days=1), "buy", 30.0, 1, target=30_000),
                sig(symname, E[0], "sell", 30.0, 1)]
res = run(signals, daily, limits)
kb_def = ev(res, "market_exit_deferred_limitdown", "KB")
check(kb_def["date"].to_list() == E[4:9],
      f"KB 跌停开盘顺延 5 日 {E[4]}..{E[8]}: {kb_def['date'].to_list()}")
kbf = res.fills.filter((pl.col("symbol") == "KB") & (pl.col("side") == "sell")).row(0, named=True)
check((kbf["fill_type"], kbf["date"], kbf["price"]) == ("market_fallback", E[9], 16.5),
      f"KB 首个非跌停开盘市价退出 {E[9]}@16.5: {(kbf['fill_type'], kbf['date'], kbf['price'])}")
kc = res.fills.filter((pl.col("symbol") == "KC") & (pl.col("side") == "sell")).row(0, named=True)
check((kc["fill_type"], kc["date"], kc["price"]) == ("limit", E[6], 22.8),
      f"KC 顺延日限价并行成交 {E[6]}@q=22.8（不取更优 open 20.52）: {(kc['fill_type'], kc['date'], kc['price'])}")
check(ev(res, "market_exit_deferred_limitdown", "KC")["date"].to_list() == E[4:7],
      "KC 顺延 3 日事件（E6 当日先顺延后由限价成交，顺延事件照记）")
k3 = res.stats["k3_fallback"]
check(k3["scheduled"] == 2 and k3["executed"] == 1 and k3["deferred_limitdown_days"] == 8,
      f"K3 统计 scheduled=2 executed=1 deferred=8（KB5+KC3，E6 双记）: "
      f"{(k3['scheduled'], k3['executed'], k3['deferred_limitdown_days'])}")
# 口径核对（审阅项 6）：卖侧 live_tradable = KB 9 日(E1..E9) + KC 6 日(E1..E6) = 15
check(res.stats["live_tradable_order_days"]["sell"] == 15,
      f"卖侧挂单日(有交易 bar) = 15: {res.stats['live_tradable_order_days']['sell']}")
check(abs(res.stats["fill_rate_order_day"]["sell"] - 2 / 15) < 1e-12,
      f"fill_rate_order_day.sell = 2/15: {res.stats['fill_rate_order_day']['sell']}")
check(res.stats["order_fill_rate"]["sell"] == 1.0, "order_fill_rate.sell = 2/2 = 1.0")

# =============================================================================
print("== case e1: 佣金 guard 的 5 万名义边界 ==")
g1 = run([sig("G", D(2024, 7, 1), "buy", 50.0, 1, shares=1000)],
         bars("G", [(D(2024, 7, 2), 50.2, 50.3, 49.9, 50.0)]),
         lim_rows([("G", D(2024, 7, 2), 55.0, 45.0)]))
check(g1.stats["commission_warnings"] == 0,
      f"名义恰 50,000 -> 不报警: {g1.stats['commission_warnings']}")
check(g1.fills.row(0, named=True)["commission"] == 5.0, "50,000 x 万1 = 5.0 = min -> 5.0")
g2 = run([sig("G", D(2024, 7, 1), "buy", 50.02, 1, shares=1000)],
         bars("G", [(D(2024, 7, 2), 50.2, 50.3, 49.9, 50.1)]),
         lim_rows([("G", D(2024, 7, 2), 55.0, 45.0)]))
check(g2.stats["commission_warnings"] == 1,
      f"名义 50,020 -> 报警 1 次: {g2.stats['commission_warnings']}")

# =============================================================================
print("== case e2: 份额调整 half-up 取整（精确边界 187.5）+ 整手-letter 冲突 ==")
H1, H2, H3, H4 = D(2024, 8, 5), D(2024, 8, 6), D(2024, 8, 7), D(2024, 8, 8)
daily = bars("R", [(H1, 10.2, 10.3, 9.95, 10.0),
                   (H2, 6.7, 6.8, 6.6, 6.7),     # 除权日1: 10 送 5 (cum 1.0->1.5)
                   (H3, 5.4, 5.4, 5.3, 5.35),    # 除权日2: 1.25 (cum 1.5->1.875)
                   (H4, 5.4, 5.5, 5.3, 5.45)])
exf = pl.DataFrame({"symbol": ["R", "R"], "ex_date": [H2, H3],
                    "cum_factor": [1.5, 1.875]})
limits = lim_rows([("R", H1, 11.0, 9.0),
                   ("R", H2, 10.1, 9.9),    # 合成宽松边界：q=10 合法（聚焦取整）
                   ("R", H3, 6.8, 6.6),     # q=6.7 合法
                   ("R", H4, 5.6, 5.2)])    # q=5.35 合法
res = run([sig("R", D(2024, 8, 4), "buy", 10.0, 1, shares=100),
           sig("R", H1, "sell", 10.0, 1)], daily, limits, exf=exf)
splits = ev(res, "corp_action_split").sort("date")
print(f"    150 x 1.25 = {150 * 1.25!r}; half-up -> {math.floor(150 * 1.25 + 0.5)}, "
      f"截断 -> {int(150 * 1.25)}")
check(splits["shares"].to_list() == [150, 188],
      f"两级拆分 100 -> 150 -> 188（187.5 half-up；截断应得 187）: {splits['shares'].to_list()}")
sf = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check(sf["shares"] == 188 and sf["shares"] % 100 != 0,
      f"验收项 3 字面（所有成交为 100 倍数）在公司行动后可被打破: 卖出 {sf['shares']} 股")

# =============================================================================
print("== case e3: 武装市价单遇长期停牌（死锁探测） ==")
S = [D(2024, 9, d) for d in (2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 16)]
# S0 买; 卖 live S1,S2,S3 (streak1-3 ->武装); S4..S8 停牌 5 日; S9 复牌跌停开盘; S10 退出
m_rows = [(S[i], 10.0, 10.1, 9.9, 10.0) for i in range(len(S))]
daily = pl.concat([
    bars("H", [(S[0], 10.2, 10.3, 9.9, 10.0),
               (S[1], 9.9, 9.9, 9.7, 9.8),
               (S[2], 9.7, 9.7, 9.3, 9.4),
               (S[3], 9.3, 9.3, 8.9, 9.0),
               (S[9], 8.1, 8.1, 7.9, 8.0),     # 复牌日：开盘 8.1 = 跌停(9.0*0.9)
               (S[10], 8.05, 8.2, 8.0, 8.1)]),  # 首个非跌停开盘
    bars("M", m_rows),                            # 日历标记：强制停牌日存在
])
limits = pl.concat([
    lim_rows([("H", S[0], 11.0, 9.0), ("H", S[1], 10.9, 8.9),
              ("H", S[2], 10.8, 8.8), ("H", S[3], 10.7, 8.7),
              ("H", S[9], 9.9, 8.1), ("H", S[10], 8.8, 7.2)]),
    auto_lim(daily.filter(pl.col("symbol") == "M")),
])
res = run([sig("H", D(2024, 8, 30), "buy", 10.0, 1, target=10_000),
           sig("H", S[0], "sell", 10.0, 1)], daily, limits)
sus = ev(res, "void_suspended", "H")
check(sus["date"].to_list() == S[4:9],
      f"武装后停牌 5 日（S4..S8）单据冻结未死锁: {sus['date'].to_list()}")
h_notp = res.events.filter((pl.col("symbol") == "H") & (pl.col("event") == "not_penetrated"))
check(h_notp["detail"].to_list()[-1].find("K streak 4") >= 0,
      f"复牌日 streak 从 4 继续（停牌日未计入 K）: {h_notp['detail'].to_list()[-1]}")
hd = ev(res, "market_exit_deferred_limitdown", "H")
check(hd["date"].to_list() == [S[9]], f"复牌日跌停开盘顺延: {hd['date'].to_list()}")
hf = res.fills.filter((pl.col("symbol") == "H") & (pl.col("side") == "sell")).row(0, named=True)
check((hf["fill_type"], hf["date"], hf["price"]) == ("market_fallback", S[10], 8.05),
      f"下一可交易日开盘退出 {S[10]}@8.05: {(hf['fill_type'], hf['date'], hf['price'])}")

# =============================================================================
print("== case e5: 已有持仓 + 当日同名义新买单成交 -> 卖单整体顺延，次日全额退出 ==")
W = [D(2024, 10, 14), D(2024, 10, 15), D(2024, 10, 16), D(2024, 10, 17)]
daily = bars("W", [(W[0], 10.2, 10.3, 9.95, 10.0),
                   (W[1], 10.0, 10.1, 9.9, 10.0),
                   (W[2], 9.6, 9.6, 9.3, 9.4),
                   (W[3], 9.5, 9.7, 9.4, 9.6)])
res = run([sig("W", D(2024, 10, 11), "buy", 10.0, 1, target=10_000),   # W0 买 1000
           sig("W", W[1], "sell", 10.0, 1),                            # live W2
           sig("W", W[1], "buy", 9.5, 1, target=5_000)],               # live W2 补仓 500
          daily, auto_lim(daily))
t1 = ev(res, "t1_deferred").row(0, named=True)
check(t1["date"] == W[2], f"已有 1000 股旧仓，卖单仍在补仓成交日整体顺延: {t1['date']}")
wf = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((wf["date"], wf["shares"]) == (W[3], 1500),
      f"次日退出全部 1500 股（含前一日新买 500，T+1 合法）: {(wf['date'], wf['shares'])}")
bd = set(res.fills.filter(pl.col("side") == "buy")["date"].to_list())
sd = set(res.fills.filter(pl.col("side") == "sell")["date"].to_list())
check(not (bd & sd), "T+1 零违例复扫")

# =============================================================================
print("== case e7: 武装执行日涨跌停数据缺失 -> 市价兜底照常执行（裁定 #2） ==")
V = [D(2024, 11, 4), D(2024, 11, 5), D(2024, 11, 6), D(2024, 11, 7), D(2024, 11, 8)]
daily = bars("V", [(V[0], 10.2, 10.3, 9.9, 10.0),
                   (V[1], 9.9, 9.9, 9.5, 9.6),
                   (V[2], 9.5, 9.5, 9.1, 9.2),
                   (V[3], 9.1, 9.1, 8.7, 8.8),
                   (V[4], 8.5, 8.6, 8.4, 8.5)])
limits = lim_rows([("V", V[0], 11.0, 9.0),      # V1..V3 涨跌停行缺失
                   ("V", V[4], 9.7, 7.9)])
res = run([sig("V", D(2024, 11, 1), "buy", 10.0, 1, target=10_000),
           sig("V", V[0], "sell", 10.0, 1)], daily, limits)
vg = ev(res, "void_no_limit_info", "V")
check(vg["date"].to_list() == [V[1], V[2], V[3]],
      f"缺涨跌停数据 3 日作废（计入 K）: {vg['date'].to_list()}")
vf = res.fills.filter((pl.col("symbol") == "V") & (pl.col("side") == "sell")).row(0, named=True)
check((vf["fill_type"], vf["date"], vf["price"]) == ("market_fallback", V[4], 8.5),
      f"第 4 挂单日无涨跌停数据仍市价兜底退出: {(vf['fill_type'], vf['date'], vf['price'])}")
check(res.stats["k3_fallback"]["executed"] == 1, "k3 executed == 1")

# =============================================================================
print()
print(f"对抗用例断言: {PASS} passed, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print("  FAILED:", f)
    sys.exit(1)
print("ALL ADVERSARIAL CASES BEHAVED AS DOCUMENTED ABOVE")
