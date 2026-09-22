# -*- coding: utf-8 -*-
"""C3-A 独立撮合参考实现测试。

覆盖 ``docs/quant_stage_plan_20260922/05_test_vectors.md`` B 表
TV-B01..TV-B14 全部场景，外加 C3-B 的优先级合成反证 TV-B18/B22/B23 与
独立性硬约束（C3-01）的自检。全部为合成行情（不读任何真实行情年份），
每个场景的期望值来自**冻结合同文字**的手工推导，写在每个测试的 docstring 里。

运行：
``PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_reference_matcher.py``

junit（C3 证据）：``... --junitxml=docs/evidence/.../order_tests.xml``
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, "src")

from quant.research.reference_matcher import (  # noqa: E402
    Bar, BarTable, Book, JudgeState, LimitRow, LimitTable, Order,
    ReferenceMatcher,
)

D = date
SYM = "sh.600001"
OTHER = "sz.000002"


# --------------------------------------------------------------------------- #
# 合成构造工具
# --------------------------------------------------------------------------- #
def bar(sym, day, sess, o, h, l, c):          # noqa: E741
    return Bar(sym, day, sess, float(o), float(h), float(l), float(c))


def limits(sym, days, up, down):
    return [LimitRow(sym, d, float(up), float(down)) for d in days]


class Case:
    """一个开环/闭环场景的容器。"""

    def __init__(self, bars, limit_rows, *, cash=Decimal("500000.00"),
                 is_t0=(), etf=(), prev_close=None):
        self.bars = BarTable(bars)
        self.limits = LimitTable(limit_rows)
        self.book = Book(cash, is_t0=is_t0, etf=etf)
        self.m = ReferenceMatcher(self.bars, self.limits, book=self.book,
                                  prev_close=prev_close)

    def run(self, orders, calendar):
        return self.m.run(orders, calendar)

    def judge(self, order, state=None):
        return self.m.judge_session(order, state)


def order(sym, side, live_day, live_sess, limit_price, *, shares=None,
          decide_day=None, decide_sess="am", intent="", source="",
          target_notional=None, snapshot_equity=None, **kw):
    decide_day = decide_day or live_day
    return Order(
        order_id=kw.pop("order_id", f"{sym}-{side}-{live_day.isoformat()}-{live_sess}"),
        symbol=sym, side=side, decision_date=decide_day,
        decision_session=decide_sess, live_date=live_day, live_session=live_sess,
        limit_price=None if limit_price is None else float(limit_price),
        shares=shares, intent=intent, source=source,
        target_notional=target_notional, snapshot_equity=snapshot_equity, **kw)


# =========================================================================== #
# TV-B01..B04：严格穿透 / 跳空按限价
# =========================================================================== #
def test_tvb01_buy_touch_equals_no_fill():
    """TV-B01：买限价 10，半日最低恰 10 → 不成交（触价不成交）。"""
    d = D(2020, 1, 2)
    c = Case([bar(SYM, d, "pm", 10.2, 10.3, 10.0, 10.1)], limits(SYM, [d], 11, 9))
    v = c.judge(order(SYM, "buy", d, "pm", 10.0, shares=1000,
                      decide_day=D(2020, 1, 1), decide_sess="pm"),
                JudgeState(available_cash=Decimal("500000")))
    assert v.filled is False
    assert v.reason == "never_crossed"
    assert v.status == "expired"
    assert v.bar_seen is True and v.limit_seen is True


def test_tvb02_buy_strict_penetration_fills_at_limit():
    """TV-B02：买限价 10，最低 9.99 → 按 10 成交，不取 9.99。"""
    d = D(2020, 1, 2)
    c = Case([bar(SYM, d, "pm", 10.2, 10.3, 9.99, 10.1)], limits(SYM, [d], 11, 9))
    v = c.judge(order(SYM, "buy", d, "pm", 10.0, shares=1000,
                      decide_day=D(2020, 1, 1), decide_sess="pm"),
                JudgeState(available_cash=Decimal("500000")))
    assert v.filled is True
    assert v.price == Decimal("10.00")
    assert v.gross_notional == Decimal("10000.00")
    assert v.commission == Decimal("5.00")      # 万1=1元 < 5元下限
    assert v.stamp_tax == Decimal("0.00")       # 买入免印花


def test_tvb03_sell_side_symmetric():
    """TV-B03：卖限价 10，最高恰 10 不成；最高 10.01 按 10 成。"""
    d = D(2020, 1, 2)
    c = Case([bar(SYM, d, "pm", 9.9, 10.0, 9.8, 9.95)], limits(SYM, [d], 11, 9))
    o = order(SYM, "sell", d, "pm", 10.0, shares=1000, intent="profit")
    v = c.judge(o, JudgeState(sellable_shares=1000, position_shares=1000))
    assert v.filled is False and v.reason == "never_crossed"

    c2 = Case([bar(SYM, d, "pm", 9.9, 10.01, 9.8, 10.0)], limits(SYM, [d], 11, 9))
    v2 = c2.judge(order(SYM, "sell", d, "pm", 10.0, shares=1000, intent="profit"),
                  JudgeState(sellable_shares=1000, position_shares=1000))
    assert v2.filled is True and v2.price == Decimal("10.00")
    assert v2.stamp_tax == Decimal("10.00")     # 2020 印花 0.1% × 10000
    assert v2.commission == Decimal("5.00")
    assert v2.fees_total == Decimal("15.00")


def test_tvb04_gap_fills_at_limit_not_better():
    """TV-B04：跳空优于限价 → 按限价成交，不偷偷取优（模拟假设，非交易所真相）。"""
    d = D(2020, 1, 2)
    c = Case([bar(SYM, d, "pm", 9.0, 9.2, 8.8, 9.1)], limits(SYM, [d], 11, 8))
    v = c.judge(order(SYM, "buy", d, "pm", 10.0, shares=1000,
                      decide_day=D(2020, 1, 1), decide_sess="pm"),
                JudgeState(available_cash=Decimal("500000")))
    assert v.filled is True
    assert v.price == Decimal("10.00")          # 不是 9.0 / 9.2
    c2 = Case([bar(SYM, d, "pm", 11.0, 11.5, 10.8, 11.2)], limits(SYM, [d], 12, 9))
    v2 = c2.judge(order(SYM, "sell", d, "pm", 10.0, shares=1000, intent="profit"),
                  JudgeState(sellable_shares=1000, position_shares=1000))
    assert v2.filled is True and v2.price == Decimal("10.00")   # 不是 11.x


# =========================================================================== #
# TV-B05..B06：决策点 → 生效半日不得越界
# =========================================================================== #
def test_tvb05_pm_decision_cannot_use_same_day_morning_penetration():
    """TV-B05：15:00 新单 → 次日 am；不得利用当天上午已发生的穿透。

    构造：决策日前一日 pm 决策 → 生效 d2 am。d1 am 已有穿透（低 9.5<10），
    d2 am 不穿透（低 10.2）→ 必须不成交。对照：把 d1 am 的穿透改掉，结果不变，
    证明 d1 的行情没有被读取。
    """
    d1, d2 = D(2020, 1, 2), D(2020, 1, 3)
    bars = [bar(SYM, d1, "am", 10.0, 10.2, 9.5, 9.8),
            bar(SYM, d2, "am", 10.3, 10.5, 10.2, 10.4)]
    lr = limits(SYM, [d1, d2], 11, 9)
    o = order(SYM, "buy", d2, "am", 10.0, shares=1000,
              decide_day=d1, decide_sess="pm", order_id="O-d2am")
    v = Case(bars, lr).judge(o, JudgeState(available_cash=Decimal("500000")))
    assert v.filled is False and v.reason == "never_crossed"
    assert v.fill_date is None

    # 对照：即使 d1 am 完全没有穿透，结论逐位不变（未读取 d1）
    bars2 = [bar(SYM, d1, "am", 10.3, 10.5, 10.21, 10.4),
             bar(SYM, d2, "am", 10.3, 10.5, 10.2, 10.4)]
    v2 = Case(bars2, lr).judge(o, JudgeState(available_cash=Decimal("500000")))
    assert (v2.filled, v2.reason) == (v.filled, v.reason)

    # 正向：d2 am 真穿透 → 成交在 d2 am（生效半日）
    bars3 = [bar(SYM, d1, "am", 10.0, 10.2, 9.5, 9.8),
             bar(SYM, d2, "am", 10.3, 10.5, 9.97, 10.0)]
    v3 = Case(bars3, lr).judge(o, JudgeState(available_cash=Decimal("500000")))
    assert v3.filled is True and v3.fill_date == d2 and v3.fill_session == "am"


def test_tvb06_1130_order_touched_in_am_not_penetrated_in_pm():
    """TV-B06：11:30 新单 → 当日 pm；上午触价而下午不穿透 → 不成交。"""
    d = D(2020, 1, 2)
    bars = [bar(SYM, d, "am", 9.9, 10.0, 9.8, 10.0),      # 上午最高恰 10（触价）
            bar(SYM, d, "pm", 10.1, 10.4, 10.05, 10.3)]    # 下午最低 10.05 > 10
    c = Case(bars, limits(SYM, [d], 11, 9))
    v = c.judge(order(SYM, "buy", d, "pm", 10.0, shares=1000,
                      decide_day=d, decide_sess="am", order_id="O-pm"),
                JudgeState(available_cash=Decimal("500000")))
    assert v.filled is False and v.reason == "never_crossed"
    assert v.live_session == "pm"


# =========================================================================== #
# TV-B07..B08：T+1 与同半日资金
# =========================================================================== #
def test_tvb07_t1_same_day_buy_not_sellable():
    """TV-B07：T 日上午买，T 日下午想卖 → 当日新股不可卖；次日上午可卖。"""
    d1, d2 = D(2020, 1, 2), D(2020, 1, 3)
    bars = [bar(SYM, d1, "am", 10.0, 10.2, 9.8, 10.1),
            bar(SYM, d1, "pm", 10.2, 10.9, 10.1, 10.6),
            bar(SYM, d2, "am", 10.6, 11.0, 10.5, 10.9)]
    c = Case(bars, limits(SYM, [d1, d2], 11.2, 9.5))
    cal = [(d1, "am"), (d1, "pm"), (d2, "am")]
    buy = order(SYM, "buy", d1, "am", 10.0, shares=1000,
                decide_day=D(2020, 1, 1), decide_sess="pm", order_id="B1")
    s_pm = order(SYM, "sell", d1, "pm", 10.5, shares=1000, intent="risk",
                 source="sig1", decide_day=d1, decide_sess="am", order_id="S1")
    s_am = order(SYM, "sell", d2, "am", 10.5, shares=1000, intent="risk",
                 source="sig1", decide_day=d1, decide_sess="pm", order_id="S2")
    vs = {v.order_id: v for v in c.run([buy, s_pm, s_am], cal)}
    assert vs["B1"].filled is True and vs["B1"].shares == 1000
    assert vs["S1"].filled is False and vs["S1"].reason == "t1_locked"
    assert vs["S2"].filled is True and vs["S2"].fill_date == d2
    assert vs["S2"].price == Decimal("10.50")
    assert c.book.total_shares(SYM) == 0


def test_tvb08_same_session_sale_proceeds_not_usable():
    """TV-B08：上午卖出与上午买入同半日 → 不得用本半日出卖款；下午才可用。

    初始现金 0；d1 am 卖 1000@10（净 9985）+ 买 900@10（需 9005）：
    am 买入因现金不足拒绝；d1 pm 同一买入因上午卖款已转可用而成交。
    """
    d1, d0 = D(2020, 1, 2), D(2019, 12, 31)
    bars = [bar(SYM, d1, "am", 10.0, 10.2, 9.8, 10.0),
            bar(SYM, d1, "pm", 10.0, 10.2, 9.9, 10.0)]
    c = Case(bars, limits(SYM, [d1], 11, 9), cash=Decimal("0.00"))
    # 先建一笔 2020 年之前取得的持仓（唯一合法来源：跨年之前的成交）
    c.book.clips[SYM] = []
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("10.00"), seq=1)]
    sell_am = order(SYM, "sell", d1, "am", 10.0, shares=1000, intent="profit",
                    decide_day=d0, decide_sess="pm", order_id="S-AM")
    buy_am = order(SYM, "buy", d1, "am", 10.0, shares=900,
                   decide_day=d1, decide_sess="am", order_id="B-AM")
    buy_pm = order(SYM, "buy", d1, "pm", 10.0, shares=900,
                   decide_day=d1, decide_sess="am", order_id="B-PM")
    cal = [(d1, "am"), (d1, "pm")]
    vs = {v.order_id: v for v in c.run([sell_am, buy_am, buy_pm], cal)}
    assert vs["S-AM"].filled is True
    assert vs["S-AM"].net_cash_flow == Decimal("9985.00")   # 10000 − 5 − 10
    assert vs["B-AM"].filled is False and vs["B-AM"].reason == "cash_short"
    assert vs["B-PM"].filled is True                        # 上午卖款已转可用
    assert c.book.pend_am_to_pm == Decimal("0.00")


# =========================================================================== #
# TV-B09：停牌/缺 bar、缺涨跌停行、非法限价
# =========================================================================== #
def test_tvb09_suspension_missing_limit_and_illegal_limit():
    """TV-B09：三类原因必须分准确——不凭空成交，原因类别正确。"""
    d = D(2020, 1, 2)
    lr = limits(SYM, [d], 11, 9)
    # (1) 无该半日 bar → suspended
    v = Case([], lr).judge(order(SYM, "buy", d, "pm", 10.0, shares=1000,
                                 decide_day=D(2020, 1, 1), decide_sess="pm"),
                           JudgeState(available_cash=Decimal("500000")))
    assert v.filled is False and v.reason == "suspended" and v.bar_seen is False
    # (2) 有 bar 但涨跌停表缺行 → limit_missing（C1 数据卡：2017-03-07..09 整缺）
    c = Case([bar(SYM, d, "pm", 10.0, 10.5, 9.5, 10.0)], [])
    v2 = c.judge(order(SYM, "buy", d, "pm", 10.0, shares=1000,
                       decide_day=D(2020, 1, 1), decide_sess="pm"),
                 JudgeState(available_cash=Decimal("500000")))
    assert v2.filled is False and v2.reason == "limit_missing"
    assert v2.limit_legality == "missing"
    # (3) 限价高于当日涨停 → limit_illegal
    c2 = Case([bar(SYM, d, "pm", 10.0, 10.5, 9.5, 10.0)], lr)
    v3 = c2.judge(order(SYM, "buy", d, "pm", 11.5, shares=1000,
                        decide_day=D(2020, 1, 1), decide_sess="pm"),
                  JudgeState(available_cash=Decimal("500000")))
    assert v3.filled is False and v3.reason == "limit_illegal"
    assert v3.limit_legality == "illegal"
    # (4) 限价低于当日跌停（卖单） → limit_illegal
    v4 = c2.judge(order(SYM, "sell", d, "pm", 8.5, shares=1000, intent="profit"),
                  JudgeState(sellable_shares=1000, position_shares=1000))
    assert v4.filled is False and v4.reason == "limit_illegal"


# =========================================================================== #
# TV-B10..B12：风险 K=3 兜底 / 止盈无兜底 / 重锚计数连续
# =========================================================================== #
def _risk_reissues(days, source="sig1", limit=10.5, sym=SYM):
    """连续 len(days) 个 session 重发同一来源的风险卖单。

    每个 session 的决策点 = 前一个自然日 pm（沿合同 (D,'pm')→(D+1,'am')；
    日历由调用方提供，本工具只构造订单）。
    """
    out: list[Order] = []
    for i, d in enumerate(days):
        dd = (D.fromordinal(days[0].toordinal() - 1) if i == 0
              else days[i - 1])
        out.append(order(sym, "sell", d, "am", limit, shares=1000,
                         intent="risk", source=source, decide_day=dd,
                         decide_sess="pm", order_id=f"S{i}"))
    return out


def test_tvb10a_three_unfilled_sessions_arm_market_fallback():
    """TV-B10a：连续 3 个许可半日未成交 → 第 4 个许可半日开盘市价兜底。"""
    days = [D(2020, 1, 2), D(2020, 1, 3), D(2020, 1, 6), D(2020, 1, 7)]
    bars, lr = [], []
    for d in days:
        bars.append(bar(SYM, d, "am", 10.0, 10.4, 9.9, 10.2))   # high<10.5 不穿透
        lr += limits(SYM, [d], 11, 9)
    # 第 4 日开盘 10.1（未跌停）→ 市价兜底成交于开盘价
    bars[3] = bar(SYM, days[3], "am", 10.1, 10.4, 9.9, 10.2)
    c = Case(bars, lr, cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    vs = c.run(_risk_reissues(days), [(d, "am") for d in days])
    by_id = {v.order_id: v for v in vs}
    assert by_id["S0"].reason == "never_crossed"
    assert by_id["S1"].reason == "never_crossed"
    assert by_id["S2"].reason == "never_crossed"
    fb = [v for v in vs if v.fill_type == "market_fallback"]
    assert len(fb) == 1
    assert fb[0].price == Decimal("10.10")      # 开盘价，不是限价
    assert fb[0].fill_date == days[3]
    assert c.m.k3_armed_events == 1 and c.m.k3_executed == 1


def test_tvb10b_suspension_freezes_risk_streak():
    """TV-B10b：停牌（缺 bar）session 冻结 K 计数，不顺延也不清零。"""
    days = [D(2020, 1, 2), D(2020, 1, 3), D(2020, 1, 6), D(2020, 1, 7),
            D(2020, 1, 8)]
    bars = [bar(SYM, d, "am", 10.0, 10.4, 9.9, 10.2) for d in days]
    bars[1] = None                               # d2 停牌：无 bar
    lr = []
    for d in days:
        lr += limits(SYM, [d], 11, 9)
    c = Case([b for b in bars if b is not None], lr, cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    vs = c.run(_risk_reissues(days), [(d, "am") for d in days])
    by_id = {v.order_id: v for v in vs}
    assert by_id["S1"].reason == "suspended"
    # d2 冻结：d1,d3,d4 三次计数 → d5 兜底；d2 不计
    assert by_id["S2"].reason == "never_crossed"
    assert by_id["S3"].reason == "never_crossed"
    fb = [v for v in vs if v.fill_type == "market_fallback"]
    assert len(fb) == 1 and fb[0].fill_date == days[4]
    assert c.m.k3_armed_events == 1


def test_tvb10c_limitdown_defers_fallback():
    """TV-B10c：武装后开盘跌停 → 顺延；下一 session 再兜底。"""
    days = [D(2020, 1, 2), D(2020, 1, 3), D(2020, 1, 6), D(2020, 1, 7),
            D(2020, 1, 8)]
    bars = [bar(SYM, d, "am", 10.0, 10.4, 9.9, 10.2) for d in days]
    bars[3] = bar(SYM, days[3], "am", 9.0, 9.0, 9.0, 9.0)   # 开盘=跌停 9.0
    bars[4] = bar(SYM, days[4], "am", 9.2, 9.6, 9.1, 9.5)
    lr = []
    for d in days:
        lr += limits(SYM, [d], 11, 9)
    c = Case(bars, lr, cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    vs = c.run(_risk_reissues(days), [(d, "am") for d in days])
    fb = [v for v in vs if v.fill_type == "market_fallback"]
    assert len(fb) == 1 and fb[0].fill_date == days[4]
    assert fb[0].price == Decimal("9.20")
    assert c.m.k3_deferred["limitdown"] == 1


def test_tvb11_profit_orders_get_no_fallback():
    """TV-B11：同样序列改为 profit 类 → 不得获得 K=3 兜底（到期静默失效）。"""
    days = [D(2020, 1, 2), D(2020, 1, 3), D(2020, 1, 6), D(2020, 1, 7)]
    bars = [bar(SYM, d, "am", 10.0, 10.4, 9.9, 10.2) for d in days]
    lr = []
    for d in days:
        lr += limits(SYM, [d], 11, 9)
    c = Case(bars, lr, cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    os_ = [order(SYM, "sell", d, "am", 10.5, shares=1000, intent="profit",
                 source="p1", decide_day=d, decide_sess="am", order_id=f"P{i}")
          for i, d in enumerate(days)]
    vs = c.run(os_, [(d, "am") for d in days])
    assert all(v.filled is False for v in vs)
    assert all(v.reason == "never_crossed" for v in vs)
    assert not any(v.fill_type == "market_fallback" for v in vs)
    assert c.m.k3_armed_events == 0 and c.m.k3_executed == 0
    assert c.book.total_shares(SYM) == 1000     # 未假设必然成交


def test_tvb12_reanchor_same_source_keeps_streak_new_source_resets():
    """TV-B12：重挂同一风险意图（锚价变动）→ 同源计数连续；换期新信号重置。"""
    days = [D(2020, 1, 2), D(2020, 1, 3), D(2020, 1, 6), D(2020, 1, 7)]
    bars = [bar(SYM, d, "am", 10.0, 10.4, 9.9, 10.2) for d in days]
    lr = []
    for d in days:
        lr += limits(SYM, [d], 11, 9)
    # 锚价每日变动（10.5/10.55/10.6/10.65），来源不变 → 第 4 日兜底
    os_ = [order(SYM, "sell", d, "am", 10.5 + 0.05 * i, shares=1000,
                 intent="risk", source="sig1", decide_day=d, decide_sess="am",
                 order_id=f"R{i}") for i, d in enumerate(days)]
    c = Case(bars, lr, cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    vs = c.run(os_, [(d, "am") for d in days])
    assert len([v for v in vs if v.fill_type == "market_fallback"]) == 1

    # 换期新信号（source 改变）→ 计数重置，第 4 日不兜底
    os2 = [order(SYM, "sell", d, "am", 10.5 + 0.05 * i, shares=1000,
                 intent="risk", source=("sig1" if i < 2 else "sig2"),
                 decide_day=d, decide_sess="am", order_id=f"Q{i}")
           for i, d in enumerate(days)]
    c2 = Case(bars, lr, cash=Decimal("0.00"))
    c2.book.clips[SYM] = [Clip(shares=1000, acquired=D(2019, 12, 30),
                               session="am", price=Decimal("9.00"), seq=1)]
    vs2 = c2.run(os2, [(d, "am") for d in days])
    assert not any(v.fill_type == "market_fallback" for v in vs2)
    assert c2.m.k3_armed_events == 0


# =========================================================================== #
# TV-B13..B14：过期/替代不得复活；部分成交后只处理剩余
# =========================================================================== #
def test_tvb13_expired_and_replaced_orders_never_revive():
    """TV-B13：过期订单延迟放行不复活；同半日重复挂单登记为 replaced。"""
    d1, d2 = D(2020, 1, 2), D(2020, 1, 3)
    bars = [bar(SYM, d1, "pm", 10.0, 10.5, 9.5, 10.1),
            bar(SYM, d2, "am", 10.0, 10.5, 9.5, 10.1)]
    c = Case(bars, limits(SYM, [d1, d2], 11, 9))
    # (1) expires_at = d1，但 live 在 d2 am（延迟 wrapper）→ 不得成交
    stale = order(SYM, "buy", d2, "am", 10.0, shares=1000,
                  decide_day=D(2020, 1, 1), decide_sess="pm",
                  order_id="STALE", expires_at=d1)
    v = c.judge(stale, JudgeState(available_cash=Decimal("500000")))
    assert v.filled is False and v.reason == "expired"
    assert "past expires_at" in v.note
    # (2) 同一 intent 在同一生效半日两张单 → 只处理决策点更晚的一张
    old = order(SYM, "buy", d2, "am", 10.0, shares=1000, decide_day=d1,
                decide_sess="am", order_id="OLD", intent_id="I1")
    new = order(SYM, "buy", d2, "am", 10.0, shares=1000, decide_day=d1,
                decide_sess="pm", order_id="NEW", intent_id="I1")
    c2 = Case(bars, limits(SYM, [d1, d2], 11, 9))
    vs = {v.order_id: v for v in c2.run([old, new],
                                        [(d1, "pm"), (d2, "am")])}
    assert vs["OLD"].reason == "replaced" and vs["OLD"].filled is False
    assert vs["NEW"].filled is True


def test_tvb14_partial_fill_then_reissue_only_handles_remainder():
    """TV-B14：同 intent 部分成交后重挂 → 仅处理剩余数量，不再买满一次。"""
    d1, d2 = D(2020, 1, 2), D(2020, 1, 3)
    bars = [bar(SYM, d1, "pm", 10.0, 10.5, 9.8, 10.1),
            bar(SYM, d2, "am", 10.0, 10.5, 9.8, 10.1)]
    c = Case(bars, limits(SYM, [d1, d2], 11, 9), cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=600, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    o1 = order(SYM, "sell", d1, "pm", 10.0, shares=1000, intent="profit",
               intent_id="T1", intent_requested_shares=1000,
               decide_day=d1, decide_sess="am", order_id="T-1")
    o2 = order(SYM, "sell", d2, "am", None, shares=None, intent="profit",
               intent_id="T1", intent_requested_shares=1000,
               decide_day=d1, decide_sess="pm", order_id="T-2")
    vs = {v.order_id: v for v in c.run([o1, o2], [(d1, "pm"), (d2, "am")])}
    assert vs["T-1"].filled is True and vs["T-1"].shares == 600
    assert vs["T-1"].reason == "partial_fill"
    assert vs["T-1"].status == "partial_fill"
    assert vs["T-1"].remaining_shares == 400
    # 重挂只请求剩余 400（不是 1000），且已无货可卖 → no_position
    assert vs["T-2"].filled is False
    assert c.m.intent_filled["T1"] == 600


# =========================================================================== #
# C3-B 合成反证：TV-B18 / B22 / B23 与 matcher 侧的一致性
# =========================================================================== #
def test_tvb18_same_point_conflict_no_oversell_no_same_point_buyback():
    """TV-B18：同证券同点风险卖出与买入并存 → 无超卖、无同点买回、止盈不升级风险单。

    卖出按可卖量上限成交（不超卖）；买入不得由同一半日的卖出款支付（同点买回
    被资金时序自然阻断）；止盈单即使在其第 4 个存活半日也不产生兜底。
    """
    d = D(2020, 1, 2)
    bars = [bar(SYM, d, "am", 10.0, 10.6, 9.7, 10.4),
            bar(SYM, d, "pm", 10.4, 11.0, 10.3, 10.8)]
    c = Case(bars, limits(SYM, [d], 11.5, 9), cash=Decimal("0.00"))
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=500, acquired=D(2019, 12, 30),
                              session="am", price=Decimal("9.00"), seq=1)]
    sell = order(SYM, "sell", d, "am", 10.5, shares=1000, intent="risk",
                 source="sig1", decide_day=D(2020, 1, 1), decide_sess="pm",
                 order_id="SELL")
    buy = order(SYM, "buy", d, "am", 9.80, shares=100, decide_day=d,
                decide_sess="am", order_id="BUY")
    vs = {v.order_id: v for v in c.run([sell, buy], [(d, "am"), (d, "pm")])}
    assert vs["SELL"].filled is True
    assert vs["SELL"].shares == 500                     # 不超卖（持仓只有 500）
    assert vs["SELL"].remaining_shares == 500           # 剩余登记，不静默吞掉
    assert vs["BUY"].filled is False and vs["BUY"].reason == "cash_short"
    assert c.book.total_shares(SYM) == 0
    assert c.m.k3_armed_events == 0
    # 止盈单在它的第 4 个存活半日仍无兜底（不升级为风险单）
    d2 = D(2020, 1, 3)
    c2 = Case([bar(SYM, d2, "am", 10.0, 10.2, 9.9, 10.0)],
              limits(SYM, [d2], 11, 9), cash=Decimal("0.00"))
    c2.book.clips[SYM] = [Clip(shares=100, acquired=D(2019, 12, 30),
                               session="am", price=Decimal("9.00"), seq=1)]
    po = order(SYM, "sell", d2, "am", 10.5, shares=100, intent="profit",
               source="sig1", decide_day=d2, decide_sess="am", order_id="P")
    vs2 = c2.run([po], [(d2, "am")])
    assert vs2[0].reason == "never_crossed" and vs2[0].status == "expired"


def test_tvb22_passive_drift_disclosed_not_forced_liquidation():
    """TV-B22：价格上涨使已有持仓市值超过 25% → 被动漂移只披露，不强制清仓。

    matcher 侧可检验的形态：既有持仓已在帽上方时，**别的标的**的新单照常判定；
    该标的自身的新买因构建时帽越限整单作废；不生成任何强制减仓订单。
    """
    d = D(2020, 1, 2)
    d_prev = D(2019, 12, 31)
    bars = [bar(SYM, d, "pm", 10.0, 10.5, 9.8, 10.1),
            bar(OTHER, d, "pm", 5.0, 5.2, 4.9, 5.1)]
    c = Case(bars, limits(SYM, [d], 11, 9) + limits(OTHER, [d], 6, 4),
             cash=Decimal("1000000.00"))
    # 既有持仓 30000 股 × 前收 10 = 30 万 > 25% × 100 万 = 25 万（被动漂移）
    c.book.clips[SYM] = []
    from quant.research.reference_matcher import Clip
    c.book.clips[SYM] = [Clip(shares=30000, acquired=D(2019, 12, 1),
                              session="am", price=Decimal("5.00"), seq=1)]
    pc = lambda s, dd: 10.0 if s == SYM else 5.0     # noqa: E731
    c.m.prev_close = pc
    over = order(SYM, "buy", d, "pm", 10.0, shares=100,
                 decide_day=d_prev, decide_sess="pm", order_id="OVER",
                 snapshot_equity=1000000.0)
    other = order(OTHER, "buy", d, "pm", 5.0, shares=1000,
                  decide_day=d_prev, decide_sess="pm", order_id="OTHER",
                  snapshot_equity=1000000.0)
    vs = {v.order_id: v for v in c.run([over, other], [(d, "pm")])}
    assert vs["OVER"].reason == "cancelled_cap"        # 整单作废，不缩量
    assert vs["OVER"].shares is None
    assert vs["OTHER"].filled is True                  # 别的标的照常
    # 没有为既有超帽持仓生成任何卖出判定
    assert all(v.side == "buy" for v in c.m.verdicts)
    assert c.book.total_shares(SYM) == 30000           # 未强制清仓


def test_tvb23_cap_and_cash_reject_without_resizing():
    """TV-B23：目标超单名帽 / 现金不足 → 按合同拒绝，不为达标自动缩单或借款。"""
    d = D(2020, 1, 2)
    bars = [bar(SYM, d, "pm", 10.0, 10.5, 9.8, 10.1)]
    c = Case(bars, limits(SYM, [d], 11, 9), cash=Decimal("500000.00"))
    big = order(SYM, "buy", d, "pm", 10.0, shares=30000,     # 30 万 > 25%×100 万
                decide_day=D(2020, 1, 1), decide_sess="pm", order_id="CAP",
                snapshot_equity=1000000.0)
    v = c.judge(big, JudgeState(available_cash=Decimal("500000"),
                                projected_mv=Decimal("0"),
                                snapshot_equity=Decimal("1000000")))
    assert v.reason == "cancelled_cap" and v.shares is None
    poor = order(SYM, "buy", d, "pm", 10.0, shares=1000,
                 decide_day=D(2020, 1, 1), decide_sess="pm", order_id="POOR")
    v2 = c.judge(poor, JudgeState(available_cash=Decimal("100.00")))
    assert v2.reason == "cash_short" and v2.shares is None

    # 闭环同样不缩量：现金不足时该单整张不成交，账面现金不变
    c2 = Case(bars, limits(SYM, [d], 11, 9), cash=Decimal("100.00"))
    vs = c2.run([poor], [(d, "pm")])
    assert vs[0].reason == "cash_short"
    assert c2.book.cash == Decimal("100.00")
    assert c2.book.total_shares(SYM) == 0


# =========================================================================== #
# 结构性自检
# =========================================================================== #
def test_matcher_has_no_backtest_or_portfolio_import():
    """C3-01：matcher 及其依赖不得 import quant.backtest / quant.portfolio。"""
    import ast
    import pathlib
    src = pathlib.Path("src/quant/research/reference_matcher.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            mods.append(node.module or "")
    banned = [m for m in mods if m.startswith(("quant.backtest", "quant.portfolio"))]
    assert banned == [], f"forbidden imports: {banned}"
    assert all(m.startswith(("quant.research.reference_ledger", "decimal",
                             "dataclasses", "datetime", "typing", "__future__"))
               for m in mods), f"unexpected external imports: {mods}"


def test_run_requires_explicit_calendar():
    """A10 修复回归：闭环必须显式给日历，不得从 bar 表隐式推断。"""
    d = D(2020, 1, 2)
    c = Case([bar(SYM, d, "pm", 10, 10.5, 9.5, 10)],
             limits(SYM, [d], 11, 9))
    with pytest.raises(ValueError, match="explicit"):
        c.m.run([])


def test_sell_without_state_fails_closed():
    """A1 修复回归：开环卖单缺账本状态必须 fail-closed，不臆造数量。"""
    d = D(2020, 1, 2)
    c = Case([bar(SYM, d, "pm", 10, 10.9, 9.9, 10.5)], limits(SYM, [d], 11, 9))
    o = order(SYM, "sell", d, "pm", 10.5, shares=1000, intent="profit")
    with pytest.raises(ValueError, match="needs the position state"):
        c.m.judge_open([o], None)
