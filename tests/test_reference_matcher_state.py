# -*- coding: utf-8 -*-
"""C3-A 闭环状态响应对照：独立 matcher vs 主引擎 band_engine。

主计划 8-C3-A：**固定订单一致不能替代闭环一致**。本文件用「极简确定性策略
（固定半日买/卖）+ 同一段合成半日行情」跑两条链：

1. 主引擎 ``quant.backtest.band_engine.run_band_backtest_intents``
   （``execution_clock='halfday'``，即当前主线半日时钟）；
2. 独立 matcher ``quant.research.reference_matcher.ReferenceMatcher.run``
   + 自带 ``Book``（独立费率/结算/T+1/FIFO/K=3 实现）。

订单层输入取自引擎产出的**订单级事件日志**（``order_id`` / 生效半日 /
限价 / 数量 / 意图），这是冻结合同要求订单层暴露的字段；本文件检验的是
**撮合与状态响应**是否逐半日一致，不是复述引擎的穿透判定。

逐半日对比：成交与否、股数、价格、费用、可用现金、待结算桶、每标的持股。

全部为合成行情（不读任何真实年份行情），不消费试验次数。

运行：
``PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_reference_matcher_state.py``
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from decimal import Decimal

import polars as pl
import pytest

sys.path.insert(0, "src")

from quant.backtest.band_engine import run_band_backtest_intents  # noqa: E402
from quant.research.reference_matcher import (  # noqa: E402
    Bar, BarTable, Book, LimitRow, LimitTable, Order, ReferenceMatcher,
)

D = date
SYM = "sh.600001"
SYM2 = "sz.000002"
INITIAL = 500_000.0
INTENT_SCHEMA = {
    "symbol": pl.String, "side": pl.String, "intent": pl.String,
    "decision_date": pl.Date, "decision_session": pl.String,
    "source_signal": pl.Date, "expiry_date": pl.Date,
    "priority": pl.Int64, "target_notional": pl.Float64,
    "target_weight": pl.Float64,
}


# --------------------------------------------------------------------------- #
# 合成行情
# --------------------------------------------------------------------------- #
def daily_bars(symbol, rows):
    return pl.DataFrame({
        "symbol": [symbol] * len(rows), "date": [r[0] for r in rows],
        "open": [float(r[1]) for r in rows], "high": [float(r[2]) for r in rows],
        "low": [float(r[3]) for r in rows], "close": [float(r[4]) for r in rows],
        "tradestatus": [1.0] * len(rows)})


def half_bars(symbol, rows):
    return pl.DataFrame({
        "symbol": [symbol] * len(rows), "trade_date": [r[0] for r in rows],
        "session": [r[1] for r in rows],
        "open": [float(r[2]) for r in rows], "high": [float(r[3]) for r in rows],
        "low": [float(r[4]) for r in rows], "close": [float(r[5]) for r in rows]})


def limit_rows(daily, missing=()):
    df = daily.select(
        "symbol", "date",
        (pl.col("close") * 1.1).alias("limit_up"),
        (pl.col("close") * 0.9).alias("limit_down"))
    if missing:
        df = df.filter(~pl.col("date").is_in(list(missing)))
    return df


def intent_row(symbol, side, first_day, first_sess, source, *, intent=None,
               priority=1, target=None, weight=None, expiry=None):
    return {"symbol": symbol, "side": side, "intent": intent,
            "decision_date": first_day, "decision_session": first_sess,
            "source_signal": source, "expiry_date": expiry,
            "priority": priority, "target_notional": target,
            "target_weight": weight}


# --------------------------------------------------------------------------- #
# 引擎事件 → 独立 matcher 订单
# --------------------------------------------------------------------------- #
def matcher_orders_from_engine(res, *, source_of=None):
    """把引擎的订单级事件日志转成 matcher 的 ``Order`` 列表。

    * ``order_id`` 形如 ``{sym}-{side}[/{intent}]-{decision_day}-{sess}``；
    * ``shares`` 只在成交事件上有值；未成交买用该 intent 的最终成交量作为
      该 intent 的请求量（引擎的 fill-stop 保证每个 intent 只有一笔成交），
      并以 ``intent_requested_shares`` 表达——不臆造数量。
    * 风险卖单的 ``source``：合成 intent 帧里每个 (symbol, risk) 只有一个来源，
      故用 ``sym|risk`` 常数，使连续重挂的 K 计数连续（M1）。
    """
    fills = res.fills
    intent_fill_shares: dict[tuple[str, str, str], int] = {}
    for r in fills.iter_rows(named=True):
        key = (r["symbol"], r["side"], r["intent"] or "")
        intent_fill_shares.setdefault(key, int(r["shares"]))
    events = res.events
    rows = events.filter(pl.col("order_id").is_not_null()
                         & pl.col("limit_price").is_not_null())
    out: list[Order] = []
    for r in rows.iter_rows(named=True):
        sym, side, intent, ddate, dsess = parse_order_id(r["order_id"])
        key = (sym, side, intent)
        recorded = None
        if r["event"].startswith("filled"):
            recorded = intent_fill_shares.get(key)
        src = (source_of(r) if source_of is not None
               else (f"{sym}|risk" if intent == "risk" else ""))
        o = Order(
            order_id=r["order_id"], symbol=sym, side=side,
            decision_date=ddate, decision_session=dsess,
            live_date=r["date"], live_session=r["session"],
            limit_price=float(r["limit_price"]),
            shares=recorded if side == "buy" else (
                None if recorded is None else recorded),
            intent=intent, source=src,
            intent_id=f"{sym}|{side}|{intent}",
            intent_requested_shares=(
                intent_fill_shares.get(key) if side == "buy" else None),
            priority=int(r["priority"] or 0),
        )
        out.append(o)
    return out


OID_RE = re.compile(
    r"^(?P<sym>.+)-(?P<side>buy|sell)(?:/(?P<intent>risk|profit))?"
    r"-(?P<day>\d{4}-\d{2}-\d{2})-(?P<sess>am|pm)$")


def parse_order_id(order_id: str) -> tuple[str, str, str, date, str]:
    """解析引擎订单号 → (symbol, side, intent, decision_day, decision_sess)。"""
    m = OID_RE.match(order_id)
    if m is None:
        raise ValueError(f"unparsable order_id {order_id!r}")
    g = m.groupdict()
    return g["sym"], g["side"], g["intent"] or "",         date.fromisoformat(g["day"]), g["sess"]


# --------------------------------------------------------------------------- #
# matcher 侧闭环
# --------------------------------------------------------------------------- #
def run_matcher(orders, daily, half, limits, *, etf=(), t0=()):
    bars = [Bar(r["symbol"], r["trade_date"], r["session"], r["open"],
                r["high"], r["low"], r["close"])
            for r in half.iter_rows(named=True)]
    lim = [LimitRow(r["symbol"], r["date"], r["limit_up"], r["limit_down"])
           for r in limits.iter_rows(named=True)]
    book = Book(Decimal(str(INITIAL)), is_t0=t0, etf=etf)
    m = ReferenceMatcher(BarTable(bars), LimitTable(lim), book=book)
    cal = sorted({(r["trade_date"], r["session"])
                  for r in half.iter_rows(named=True)},
                 key=lambda k: (k[0], 0 if k[1] == "am" else 1))
    verdicts = m.run(orders, cal)
    return m, book, verdicts


def engine_sessions(res):
    """引擎逐半日的末状态（现金/待结算/持股）。"""
    daily = res.daily
    return {r["date"]: r for r in daily.iter_rows(named=True)}


# --------------------------------------------------------------------------- #
# 场景 1：买当日成交 + 半日时钟 + T+1 + 卖出重锚
# --------------------------------------------------------------------------- #
D1, D2, D3, D4 = (D(2020, 1, d) for d in (2, 3, 6, 7))
DAILY_1 = pl.concat([
    daily_bars(SYM, [(D1, 10.0, 10.3, 9.5, 10.0), (D2, 10.1, 10.4, 10.0, 10.2),
                     (D3, 10.2, 10.6, 10.1, 10.5), (D4, 10.5, 11.0, 10.4, 10.9)]),
    daily_bars(SYM2, [(D1, 5.0, 5.2, 4.6, 5.0), (D2, 5.0, 5.1, 4.9, 5.0),
                      (D3, 5.0, 5.3, 4.9, 5.2), (D4, 5.2, 5.5, 5.1, 5.4)]),
])
HALF_1 = pl.concat([
    half_bars(SYM, [(D1, "am", 10.0, 10.1, 9.8, 10.0),
                    (D1, "pm", 10.0, 10.2, 9.5, 9.9),
                    (D2, "am", 10.1, 10.3, 10.0, 10.2),
                    (D2, "pm", 10.2, 10.4, 10.1, 10.3),
                    (D3, "am", 10.3, 10.6, 10.2, 10.5),
                    (D3, "pm", 10.5, 10.8, 10.4, 10.7),
                    (D4, "am", 10.7, 11.5, 10.6, 11.2),
                    (D4, "pm", 11.2, 11.6, 11.0, 11.4)]),
    half_bars(SYM2, [(D1, "am", 5.0, 5.1, 4.8, 5.0),
                     (D1, "pm", 5.0, 5.1, 4.6, 4.9),
                     (D2, "am", 4.9, 5.0, 4.85, 4.95),
                     (D2, "pm", 4.95, 5.05, 4.9, 5.0),
                     (D3, "am", 5.0, 5.1, 4.95, 5.05),
                     (D3, "pm", 5.05, 5.2, 5.0, 5.15),
                     (D4, "am", 5.15, 5.4, 5.1, 5.35),
                     (D4, "pm", 5.35, 5.6, 5.3, 5.55)]),
])


def test_state_transition_scenario1_buys_then_reanchor_sell():
    """场景 1：两笔买入当日 pm 成交；一笔 profit 卖出到期未穿透后重锚成交。

    对照 ①引擎 ②matcher 的逐半日持仓/现金/费用/成交价。
    """
    intents = pl.DataFrame([
        intent_row(SYM, "buy", D1, "am", D1, target=50_000.0, priority=1),
        intent_row(SYM2, "buy", D1, "am", D1, target=50_000.0, priority=2),
        intent_row(SYM, "sell", D3, "am", D3, intent="profit",
                   target=50_000.0, priority=500_001),
    ], schema=INTENT_SCHEMA)
    limits = limit_rows(DAILY_1)
    res = run_band_backtest_intents(intents, DAILY_1, HALF_1, limits,
                                    initial_cash=INITIAL,
                                    execution_clock="halfday")
    orders = matcher_orders_from_engine(res)
    m, book, verdicts = run_matcher(orders, DAILY_1, HALF_1, limits)

    # --- 逐订单：成交与否/股数/价格/费用 与引擎 fills 一致 ---
    ef = {(r["order_id"]): r for r in res.fills.iter_rows(named=True)}
    mv = {v.order_id: v for v in verdicts}
    for oid, f in ef.items():
        v = mv.get(oid)
        assert v is not None, f"matcher never judged {oid}"
        assert v.filled, f"matcher did not fill {oid} (engine filled)"
        assert int(v.shares) == int(f["shares"]), oid
        assert abs(float(v.price) - float(f["price"])) < 1e-9, oid
        assert abs(float(v.fees_total) - float(f["fees_total"])) < 1e-9, oid
        assert v.fill_date == f["date"] and v.fill_session == f["session"], oid
    # 引擎未成交的订单，matcher 也必须未成交
    terminal = res.events.filter(pl.col("order_id").is_not_null()
                                 & pl.col("limit_price").is_not_null())
    for r in terminal.iter_rows(named=True):
        v = mv[r["order_id"]]
        if not r["event"].startswith("filled"):
            assert not v.filled, (r["order_id"], v.reason)
    # --- 期末：持股与现金 ---
    eng_daily = res.daily.sort("date")
    eng_last = eng_daily.row(-1, named=True)
    eng_shares = {}
    for r in res.clips_final.iter_rows(named=True):
        eng_shares[r["symbol"]] = eng_shares.get(r["symbol"], 0) + int(r["shares"])
    for sym in set(eng_shares) | {SYM, SYM2}:
        assert book.total_shares(sym) == eng_shares.get(sym, 0), sym
    engine_cash = (float(eng_last["settled_cash"])
                   + float(eng_last["pending_am_to_pm"])
                   + float(eng_last["pending_next_day"]))
    ours_cash = float(book.cash + book.pend_am_to_pm + book.pend_next_day)
    assert abs(ours_cash - engine_cash) < 0.05, (ours_cash, engine_cash)


def test_state_transition_scenario2_k3_fallback_and_suspension():
    """场景 2：风险卖出连续 3 个未成交半日 → 下一个许可半日开盘兜底；
    中间夹一个停牌日（**该标的无 bar、也无日线行**）冻结 K 计数。

    对照 ①引擎 ②matcher 的兜底半日、兜底价（session 开盘）、股数、费用与期末持股。
    第二个标的（SYM2）只为把停牌日留在市场半日日历里。
    """
    days = [D(2020, 1, d) for d in (2, 3, 6, 7, 8, 9)]
    suspended = days[1]
    sym_daily = [(days[0], 10.0, 10.4, 9.5, 10.0)] + [
        (d, 9.9, 10.0, 9.4, 9.6) for d in days[2:]]
    other_daily = [(d, 5.0, 5.1, 4.9, 5.0) for d in days]
    daily = pl.concat([daily_bars(SYM, sym_daily),
                       daily_bars(SYM2, other_daily)])
    half_rows = [(days[0], "am", 10.0, 10.2, 9.6, 9.8),
                 (days[0], "pm", 9.8, 9.9, 9.5, 9.6)]
    # suspended 日：SYM 完全没有半日 bar（停牌），SYM2 正常 → 日历仍含该日
    half_rows += [(days[2], "am", 9.7, 9.85, 9.5, 9.6),
                  (days[2], "pm", 9.6, 9.7, 9.4, 9.5),
                  (days[3], "am", 9.5, 9.6, 9.3, 9.4),
                  (days[3], "pm", 9.4, 9.5, 9.2, 9.3),
                  (days[4], "am", 9.35, 9.45, 9.25, 9.3),
                  (days[4], "pm", 9.3, 9.4, 9.2, 9.25)]
    other_half = [(d, s, 5.0, 5.05, 4.95, 5.0) for d in days
                  for s in ("am", "pm")]
    half = pl.concat([half_bars(SYM, half_rows),
                      half_bars(SYM2, other_half)])
    limits = limit_rows(daily)
    intents = pl.DataFrame([
        intent_row(SYM, "buy", days[0], "am", days[0], target=50_000.0),
        intent_row(SYM, "sell", days[2], "am", days[1], intent="risk",
                   target=0.0, priority=1_000_000),
    ], schema=INTENT_SCHEMA)
    res = run_band_backtest_intents(intents, daily, half, limits,
                                    initial_cash=INITIAL,
                                    execution_clock="halfday")
    orders = matcher_orders_from_engine(res)
    m, book, verdicts = run_matcher(orders, daily, half, limits)

    fb_engine = res.fills.filter(pl.col("fill_type") == "market_fallback")
    fb_mine = [v for v in verdicts if v.fill_type == "market_fallback"]
    assert fb_engine.height == len(fb_mine), (fb_engine.height, len(fb_mine))
    if fb_engine.height:
        f = fb_engine.row(0, named=True)
        v = fb_mine[0]
        assert v.fill_date == f["date"] and v.fill_session == f["session"]
        assert abs(float(v.price) - float(f["price"])) < 1e-9
        assert int(v.shares) == int(f["shares"])
        assert abs(float(v.fees_total) - float(f["fees_total"])) < 1e-9
        bar = [r for r in half_rows if (r[0], r[1]) == (f["date"], f["session"])][0]
        assert abs(float(v.price) - bar[2]) < 1e-9      # 兜底价 = session 开盘
    eng_shares = {}
    for r in res.clips_final.iter_rows(named=True):
        eng_shares[r["symbol"]] = eng_shares.get(r["symbol"], 0) + int(r["shares"])
    for sym in set(eng_shares) | {SYM, SYM2}:
        assert book.total_shares(sym) == eng_shares.get(sym, 0), sym
    eng_last = res.daily.sort("date").row(-1, named=True)
    engine_cash = (float(eng_last["settled_cash"])
                   + float(eng_last["pending_am_to_pm"])
                   + float(eng_last["pending_next_day"]))
    ours_cash = float(book.cash + book.pend_am_to_pm + book.pend_next_day)
    assert abs(ours_cash - engine_cash) < 0.05, (ours_cash, engine_cash)
