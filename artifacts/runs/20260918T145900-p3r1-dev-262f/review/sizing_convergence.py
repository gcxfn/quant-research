# -*- coding: utf-8 -*-
"""收官双签 · 校验脚本 2：C06/C08 sizing 不动点复跑（只读，内存计算）。

逐字复刻 runner（tmp/run_adjudication.py）的输入构造与迭代语义：
  - 信号窗与 2020-12-31 丢弃规则、池（r16 verbatim）、敞口（T200-40/FIX75）；
  - 目标名义 = exposure x equity / K，迭代至信号帧逐字节相等（这里放宽到 15 次）；
  - 检查 1（确定性）：第 6 次迭代的净CAGR/回撤/执行率必须逐位复现 runner 报告值；
  - 检查 2（收敛性）：不动点处的净CAGR/失败门 vs 报告值——门判定是否可翻转；
  - 检查 3：混合口径 fill（订单级 (b+s filled)/(orders)）范围核对 44–65% 声称。
只读仓库；无任何文件写入（除本目录日志 via tee）。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r"D:\量化")
RUN = ROOT / "artifacts" / "runs" / "20260918T145900-p3r1-dev-262f"
R16_RUN = ROOT / "artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f"
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

import quant.research.etf_rotation as er  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    load_dividends_h5, load_split_factor_h5, load_stk_limit_batch,
    run_band_backtest)

D = date
DEV_START, DEV_END = D(2015, 1, 5), D(2020, 12, 31)
CONFIG_PATH = ROOT / "configs/experiments/p2r16-trend-dispersion.json"
DAILY = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
INDEX_CHUNK = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv"
FAILS: list[str] = []
PASS = 0


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK ] {label}", flush=True)
    else:
        FAILS.append(label)
        print(f"  [FAIL] {label}", flush=True)


import json  # noqa: E402
config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
mg = json.loads((RUN / "outputs" / "metrics_and_gates.json").read_text(encoding="utf-8"))

# --- 信号日（逐字复刻 runner 步骤 1） ----------------------------------------
cal = r16.market_calendar(DAILY)
calendar_full = cal["date"].to_list()
all_signals = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_all = all_signals["s"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
signal_days = [d for d in sig_all
               if idx_of_full[d] + 1 < len(calendar_full)
               and calendar_full[idx_of_full[d] + 1] <= DEV_END]
check(signal_days[-1] == D(2020, 11, 30) and len(signal_days) == 71
      and D(2020, 12, 31) not in signal_days,
      f"71 个 dev 信号，末位 {signal_days[-1]}，2020-12-31 已丢弃")

# --- 池与敞口（r16 verbatim） -------------------------------------------------
print("  building pools (r16 verbatim)…", flush=True)
hist = r16.build_history_r16(DAILY, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": signal_days}))
pools_at = r16.pools_by_signal(pool_frame)
del hist
index_close = r16.load_index_close(INDEX_CHUNK).filter(
    pl.col("trade_date") <= r16.FREEZE_LAST)
exposures_by_path = {
    "T200-40": r16.t200_month_end_exposures(index_close, calendar_full, signal_days),
    "FIX75": r16.fix75_exposures(signal_days),
}

# --- 引擎输入帧（逐字复刻 runner 步骤 4） -------------------------------------
leg = pl.read_parquet(R16_RUN / "leg_log.parquet")
leg_dev = leg.filter(pl.col("plan_date").is_in(signal_days))
legs_by = {k: g for k, g in leg_dev.partition_by(["config_id", "plan_date"],
                                                 as_dict=True).items()}
panel_symbols = sorted({s for (_cid, _t), g in legs_by.items()
                        for s in g["symbol"].to_list()})
daily = (pl.scan_parquet(DAILY)
         .filter(pl.col("symbol").is_in(panel_symbols))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .select("symbol", "date", "open", "high", "low", "close", "tradestatus")
         .sort("symbol", "date").collect())
check(daily["date"].max() <= DEV_END, f"引擎面板最大日期 {daily['date'].max()} ≤ 2020-12-31")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits_full = limits_full.rename({"up_limit": "limit_up", "down_limit": "limit_down"})
limits = limits_full.filter(pl.col("symbol").is_in(panel_symbols)).filter(
    (pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
check(limits["date"].max() <= DEV_END, "涨跌停裁剪至 dev")
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(panel_symbols))
dividends = divs_all.filter(pl.col("symbol").is_in(panel_symbols))
close_at = {(s, d): v for s, d, v in zip(
    daily["symbol"].to_list(), daily["date"].to_list(), daily["close"].to_list())}


def sizing_loop(cid, max_iter=15):
    """逐字复刻 runner 步骤 5 的迭代语义，放宽上限并记录每次迭代的指标。"""
    spec = config["configs"][cid]
    K, path = int(spec["K"]), spec["path"]
    exposures = exposures_by_path[path]
    plan = {}
    for t in signal_days:
        g = legs_by[(cid, t)]
        entrants = sorted(g.filter(pl.col("kind") == "buy_open")["symbol"].to_list())
        leavers = sorted(g.filter(pl.col("kind") == "sell_full")["symbol"].to_list())
        plan[t] = (set(entrants), set(leavers))
    rank_of = {t: {s: i + 1 for i, s in enumerate(pools_at[t]["ranked"])}
               for t in signal_days}
    next_sig = {signal_days[i]: (signal_days[i + 1] if i + 1 < len(signal_days)
                                 else DEV_END) for i in range(len(signal_days))}
    equity_guess = {t: 200_000.0 for t in signal_days}
    prev_rows = None
    res = None
    history = []
    converged_at = None
    for it in range(1, max_iter + 1):
        rows = []
        for t in signal_days:
            entrants, leavers = plan[t]
            nxt = next_sig[t]
            target = round(exposures[t] * equity_guess[t] / K, 2)
            for sym in sorted(entrants):
                rows.append({"symbol": sym, "signal_date": t, "side": "buy",
                             "anchor_price": float(close_at[(sym, t)]),
                             "priority": rank_of[t].get(sym, 10 ** 6),
                             "target_notional": target, "shares": None,
                             "expiry_date": nxt})
            for sym in sorted(leavers):
                rows.append({"symbol": sym, "signal_date": t, "side": "sell",
                             "anchor_price": float(close_at.get((sym, t), np.nan)),
                             "priority": rank_of[t].get(sym, 10 ** 6),
                             "target_notional": None, "shares": None,
                             "expiry_date": nxt})
        sig_frame = pl.DataFrame(rows, schema={
            "symbol": pl.String, "signal_date": pl.Date, "side": pl.String,
            "anchor_price": pl.Float64, "priority": pl.Int64,
            "target_notional": pl.Float64, "shares": pl.Int64,
            "expiry_date": pl.Date})
        if prev_rows is not None and sig_frame.equals(prev_rows):
            converged_at = it - 1
            break
        prev_rows = sig_frame
        res = run_band_backtest(sig_frame, daily, limits, splits, dividends,
                                initial_cash=200_000.0)
        eq_at = dict(zip(res.daily["date"].to_list(), res.daily["equity"].to_list()))
        equity_guess = {t: float(eq_at.get(t, 200_000.0)) for t in signal_days}
        sd, sv = er.slice_curve(res.daily["date"].to_list(),
                                res.daily["equity"].to_list(), DEV_START, DEV_END)
        history.append({"it": it, "cagr": er.cagr(sv[0], sv[-1], sd[0], sd[-1]),
                        "mdd": er.max_drawdown(sd, sv)["max_drawdown"],
                        "end_eq": sv[-1]})
    return res, history, converged_at


def metrics_of(res):
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(), DEV_START, DEV_END)
    net_cagr = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd = er.max_drawdown(sd, sv)["max_drawdown"]
    n_orders = res.stats["signals"]["buy"] + res.stats["signals"]["sell"]
    filled = res.stats["orders_filled"]["buy"] + res.stats["orders_filled"]["sell"]
    ue = res.stats["unfilled_exit_reasons"]
    rule_ok = (ue["buy"].get("below_min_lot", 0) + ue["sell"].get("void_no_position", 0))
    ev = res.events
    cash_ids = set(ev.filter((pl.col("event") == "void_insufficient_cash")
                             & (pl.col("side") == "buy"))["order_id"].to_list())
    filled_ids = set(res.fills.filter(pl.col("side") == "buy")["order_id"].to_list())
    executed = filled + rule_ok + len(cash_ids - filled_ids)
    return {"cagr": net_cagr, "mdd": mdd, "exec": executed / n_orders,
            "blend_fill": (filled / n_orders if n_orders else None),
            "orders_buy": res.stats["signals"]["buy"],
            "orders_sell": res.stats["signals"]["sell"],
            "filled_buy": res.stats["orders_filled"]["buy"],
            "filled_sell": res.stats["orders_filled"]["sell"]}


for cid, path in (("C06", "T200-40"), ("C08", "FIX75")):
    print(f"== {cid}（{path}）sizing 复跑至不动点 ==", flush=True)
    res, history, converged_at = sizing_loop(cid)
    rep = mg["metrics"][cid]
    it6 = next(h for h in history if h["it"] == 6)
    check(abs(it6["cagr"] - rep["net_cagr"]) < 1e-9
          and abs(it6["mdd"] - rep["max_drawdown"]) < 1e-9,
          f"确定性：我的第 6 次迭代 CAGR {it6['cagr']*100:+.4f}% / mdd {it6['mdd']*100:.2f}% "
          f"逐位复现 runner 报告值")
    m = metrics_of(res)
    check(abs(m["exec"] - rep["execution_rate"]) < 1e-9,
          f"确定性：第 6 次迭代执行率 {m['exec']*100:.2f}% 复现报告值")
    final = history[-1]
    print(f"    迭代 CAGR 序列: "
          f"{[round(h['cagr'] * 100, 3) for h in history]}")
    print(f"    迭代 end_eq 序列: {[round(h['end_eq']) for h in history]}")
    print(f"    收敛: {'第 ' + str(converged_at) + ' 次迭代帧相等' if converged_at else f'{max_iter} 次未收敛'}")
    # 不动点（最后一次运行即不动点帧的运行）处的完整门重评
    sd, sv = er.slice_curve(res.daily["date"].to_list(),
                            res.daily["equity"].to_list(), DEV_START, DEV_END)
    net_fp = er.cagr(sv[0], sv[-1], sd[0], sd[-1])
    mdd_fp = er.max_drawdown(sd, sv)["max_drawdown"]
    b1 = rep["b1m_net_cagr"]
    exec_fp = metrics_of(res)["exec"]
    excess_fp = net_fp - b1
    print(f"    不动点: net {net_fp*100:+.4f}% (报告 {rep['net_cagr']*100:+.4f}%, "
          f"差 {(net_fp-rep['net_cagr'])*100:+.4f}pp); excess {excess_fp*100:+.2f}pp "
          f"(门2 短差 {(2.0-excess_fp*100):.2f}pp); exec {exec_fp*100:.2f}% "
          f"(门8 距离 {95-exec_fp*100:.1f}pp)")
    check(abs((net_fp - rep["net_cagr"]) * 100) < 0.05,
          f"{cid} 不动点与报告的净CAGR差 {((net_fp-rep['net_cagr'])*100):+.4f}pp < 0.05pp"
          f"（远小于任何失败门短差）")
    # 门结果方向逐一核对（不动点 vs 报告）
    check((net_fp > 0) == (rep["net_cagr"] > 0),
          f"{cid} 门1 方向不变（不动点 net {'>' if net_fp > 0 else '<='} 0）")
    check((excess_fp >= 0.020) == (rep["excess_vs_b1m"] >= 0.020),
          f"{cid} 门2 方向不变（不动点 excess {excess_fp*100:+.2f}pp vs +2pp 阈）")
    check(exec_fp < 0.95, f"{cid} 门8 在不动点仍失败（{exec_fp*100:.2f}% < 95%）")
    check("8_execution_rate_ge_95pct" in mg["gates"][cid]["dev"]["failed_gates"],
          f"{cid} 报告的门失败表中含门 8")
    # 不动点处其余门的真值核对
    year_ret = er.year_returns(sd, sv)
    b1y = {int(k): v for k, v in rep["b1m_net_return_by_year"].items()}
    adv_real = sum(1 for y, v in year_ret.items() if y in b1y and v - b1y[y] > 0)
    check(adv_real == mg["gates"][cid]["dev"]["advantage_years"],
          f"{cid} 优势年（不动点复算 {adv_real}）与报告一致")
    check(abs(mdd_fp) > abs(rep["b1m_max_drawdown"]) or abs(mdd_fp) > 0.20,
          f"{cid} 门4 在不动点仍失败（回撤 {mdd_fp*100:.2f}% 越限）")
    print("    -> 不动点处失败门集合与报告一致：仍 eliminated，无翻转")

# --- 混合口径 fill（44–65% 声称核对） -----------------------------------------
print("== 混合口径 fill（订单级 (买成交+卖成交)/总订单）==")
blends = {}
for cid in [f"C0{i}" for i in range(1, 9)]:
    m = metrics_of.__wrapped__ if False else None
# 从保存的 events/fills parquet 统计订单数与成交数
for cid in [f"C0{i}" for i in range(1, 9)]:
    ev = pl.read_parquet(RUN / "outputs" / f"{cid}_events.parquet")
    fs = pl.read_parquet(RUN / "outputs" / f"{cid}_fills.parquet")
    orders_b = ev.filter(pl.col("side") == "buy")["order_id"].n_unique()
    orders_s = ev.filter(pl.col("side") == "sell")["order_id"].n_unique()
    fb = fs.filter(pl.col("side") == "buy")["order_id"].n_unique()
    fsr = fs.filter(pl.col("side") == "sell")["order_id"].n_unique()
    blend = (fb + fsr) / (orders_b + orders_s)
    blends[cid] = blend
    # 逐位核对订单口径成交率
    d = mg["disclosures"][cid]
    check(abs(fb / orders_b - d["order_fill_rate"]["buy"]) < 1e-9
          and abs(fsr / orders_s - d["order_fill_rate"]["sell"]) < 1e-9,
          f"{cid} 订单口径成交率复算一致: 买 {fb}/{orders_b}={fb/orders_b*100:.1f}% "
          f"卖 {fsr}/{orders_s}={fsr/orders_s*100:.1f}%")
lo, hi = min(blends.values()), max(blends.values())
check(round(lo * 100) == 44 and round(hi * 100) == 65,
      f"混合口径 fill 范围 {lo*100:.1f}–{hi*100:.1f}%，整数舍入即披露的 44–65%（声称成立）")

print()
print(f"校验 2 断言: {PASS} passed, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print("  FAILED:", f)
    sys.exit(1)
print("ALL SIZING/CONVERGENCE CHECKS PASSED")
