# -*- coding: utf-8 -*-
"""C2 独立参考账本测试。

覆盖：
* ``05_test_vectors.md`` A 表 TV-A01..A05 的手算案例（精确到分）；
* 实施者扩展的手算案例（多次部分卖出+FIFO、分红后卖出、印花税边界）；
* C 表九类对参考实现本身的反证注入（注入后校验必须报错）；
* T+1 / 现金结算 / 可卖量 / 公司行动衔接专项；
* 固定成交序列的费用单调性（TV-B30）。

运行：``PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_reference_ledger.py``
期望值直接取 ``docs/quant_stage_plan_20260922/05_test_vectors.md`` 的手算数字，
不来自主引擎输出。
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, "src")

from quant.research.reference_ledger import (  # noqa: E402
    CashShortfallError,
    CashSignError,
    ClipOverConsumptionError,
    CoverageError,
    DayInput,
    DividendAction,
    DividendUnitError,
    DuplicateFillError,
    FeeSchedule,
    Fill,
    NotionalConsistencyError,
    PriceLegalityError,
    ReferenceLedger,
    SettlementTimingError,
    SignConventionError,
    SplitAction,
    StaleClipError,
    TemporalLeakError,
    TPlusViolationError,
    assert_drawdown_gate,
    assert_full_year_coverage,
)

D = Decimal


def q(value) -> Decimal:
    return Decimal(str(value)).quantize(D("0.01"))


def buy(fill_id, symbol, day, session, shares, price, **kw) -> Fill:
    return Fill(fill_id=fill_id, symbol=symbol, side="buy", day=day,
                session=session, shares=shares, price=D(str(price)), **kw)


def sell(fill_id, symbol, day, session, shares, price, **kw) -> Fill:
    return Fill(fill_id=fill_id, symbol=symbol, side="sell", day=day,
                session=session, shares=shares, price=D(str(price)), **kw)


def led_day(day, fills, marks, splits=(), dividends=()) -> DayInput:
    return DayInput(day=day, fills=list(fills), marks=dict(marks),
                    splits=list(splits), dividends=list(dividends))


# --------------------------------------------------------------------------- #
# A 表：手算案例
# --------------------------------------------------------------------------- #
def test_tv_a01_flat_round_trip():
    """TV-A01：5000×10 买、5000×10 卖；买佣金 5、卖佣金 5+印花 50；终值 499940。"""
    d1, d2, d3 = date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4)
    led = ReferenceLedger(500000)
    led.replay([
        # 买入当日 pm 成交；卖出次日 pm 成交（款进入待结算）
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 5000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [sell("F2", "sh.600000", d2, "pm", 5000, "10")],
                {"sh.600000": D("10")}),
        led_day(d3, [], {}),
    ])
    r1, r2, r3 = led.days
    assert q(r1.free_settled_cash) == q(449995)          # 500000 - 50000 - 5
    assert r1.equity == q(499995)
    # 卖出款进入待结算，权益包含待结算现金、不额外下降
    assert q(r2.unsettled_sale_proceeds) == q(49945)     # 50000 - 5 - 50
    assert q(r2.free_settled_cash) == q(449995)
    assert r2.equity == q(499940)
    assert q(r3.free_settled_cash) == q(499940)          # 次日 am 转为可用
    assert q(r3.equity) == q(499940)
    # 总费用 = 60
    assert q(r3.fee_cumulative) == q(60)


def test_tv_a02_up_20pct_round_trip():
    """TV-A02：买 5000×10、卖 5000×12；终值 509929，盈利 9929。"""
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(500000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 5000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [sell("F2", "sh.600000", d2, "am", 5000, "12")], {}),
        led_day(date(2020, 6, 4), [], {}),
    ])
    r2 = led.days[1]
    # 卖佣金 6、印花 60 → net 59934；am 卖出 pm 起可用
    assert q(r2.free_settled_cash) == q(449995 + 59934)
    assert q(r2.free_settled_cash) == q(509929)
    assert q(r2.fee_cumulative) == q(71)                 # 5 + 6 + 60
    assert q(r2.equity - D("500000")) == q(9929)


def test_tv_a03_stamp_tax_date_boundary():
    """TV-A03：卖出 50000 名义，2023-08-25 印花 50；2023-08-28 印花 25；佣金均 5。"""
    fees = FeeSchedule()
    before = date(2023, 8, 25)
    on_or_after = date(2023, 8, 28)
    c1, s1, _ = fees.total(before, D("50000"), side="sell")
    c2, s2, _ = fees.total(on_or_after, D("50000"), side="sell")
    assert (q(c1), q(s1)) == (q(5), q(50))
    assert (q(c2), q(s2)) == (q(5), q(25))
    # 临界日当日按 0.0005
    assert fees.stamp_sell(on_or_after, D("50000")) == D("25.00")
    assert fees.stamp_sell(date(2023, 8, 27), D("50000")) == D("50.00")


def test_tv_a04_cash_dividend_continuity():
    """TV-A04：1000 股、除息前 10 元、分红 0.50/股、除息估值 9.50。

    公司行动不双重计入：除息日 市值 9500 + 现金分红 500 = 行动前位置价值 10000。
    """
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [], {"sh.600000": D("9.5")},
                dividends=[DividendAction("sh.600000", d2, D("0.50"),
                                          cash_per_lot=D("50"), round_lot=100,
                                          prev_close=D("10"))]),
    ])
    r1, r2 = led.days
    assert q(r1.equity) == q(99995)                      # 100000 - 10000 - 5
    assert q(r2.position_mv) == q(9500)
    assert q(r2.dividend_cumulative) == q(500)
    assert q(r2.equity) == q(99995)                      # 分红与价格下降相互抵消
    # 除息日位置价值守恒：市值 + 分红 = 行动前市值
    assert q(r2.position_mv + r2.dividend_cumulative) == q(10000)


def test_tv_a05_split_two_for_one():
    """TV-A05：1000 股 ×10 元，2:1 后 2000 股 ×5 元，总价值 10000 不变。"""
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [], {"sh.600000": D("5")},
                splits=[SplitAction("sh.600000", d2, D("2"))]),
    ])
    r2 = led.days[1]
    assert r2.held_shares["sh.600000"] == 2000
    assert q(r2.position_mv) == q(10000)
    assert q(r2.equity) == q(99995)


# --------------------------------------------------------------------------- #
# 扩展手算案例
# --------------------------------------------------------------------------- #
def test_ext_multiple_partial_sells_fifo():
    """扩展 A：两批次买入后部分卖出，FIFO 消耗 + 现金/费用逐分手算。

    day1 买 1000@10（批 A），day2 买 500@12（批 B），day3 am 卖 1200@11。
    FIFO：A 1000 + B 200 消耗，剩 B 300。
    """
    d1, d2, d3 = date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [buy("F2", "sh.600000", d2, "pm", 500, "12")], {"sh.600000": D("12")}),
        led_day(d3, [sell("F3", "sh.600000", d3, "am", 1200, "11")], {"sh.600000": D("11")}),
    ])
    r3 = led.days[2]
    # day1: 100000-10000-5=89995 ; day2: 89995-6000-5=83990
    # day3 am：名义 13200、佣金 5、印花 13.20 → net 13181.80，pm 起可用
    assert q(r3.free_settled_cash) == q(83990 + 13181.80)
    assert r3.held_shares["sh.600000"] == 300
    assert q(r3.position_mv) == q(3300)
    assert q(r3.equity) == q(97171.80 + 3300)
    assert q(r3.fee_cumulative) == q(5 + 5 + 5 + 13.20)
    # FIFO：剩余的批次是 B，取得日 day2
    remaining = [c for c in led.clips["sh.600000"] if c.shares > 0]
    assert len(remaining) == 1 and remaining[0].acquired == d2 and remaining[0].shares == 300


def test_ext_dividend_then_sell():
    """扩展 B：分红后卖出，现金=买入余额+分红+卖出净额。"""
    d1, d2, d3 = date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [], {"sh.600000": D("9.5")},
                dividends=[DividendAction("sh.600000", d2, D("0.50"),
                                          cash_per_lot=D("50"), round_lot=100)]),
        led_day(d3, [sell("F2", "sh.600000", d3, "am", 1000, "9.6")], {}),
    ])
    r3 = led.days[2]
    # 90495 = 89995 + 500 ；卖出净额 = 9600 - 5 - 9.60 = 9585.40
    assert q(r3.free_settled_cash) == q(90495 + 9585.40)
    assert q(r3.dividend_cumulative) == q(500)
    assert r3.held_shares == {}


def test_ext_lot_rounding_and_sellable_after_split():
    """扩展 C：非整数比例送转 half-up、当日新增份额可卖性区分整手/零股。

    * 300 股 × 1.9848 → 595.44 → half-up 595；新增 295 股为**零股**，
      取得日=当日，当日即可卖（合同 p3 §7.3 零股例外）；
    * 1000 股 × 1.3 → 1300；新增 300 股为**整手**，取得日=当日、次日才可卖。
    """
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 300, "3")], {"sh.600000": D("3")}),
        led_day(d2, [], {"sh.600000": D("1.5")},
                splits=[SplitAction("sh.600000", d2, D("1.9848"))]),
    ])
    r2 = led.days[1]
    assert r2.held_shares["sh.600000"] == 595
    assert r2.sellable_shares["sh.600000"] == 595     # 新增 295 为零股，当日可卖
    assert q(r2.position_mv) == q(D("595") * D("1.5"))

    d3, d4 = date(2020, 6, 2), date(2020, 6, 3)
    led2 = ReferenceLedger(100000)
    led2.replay([
        led_day(d3, [buy("G1", "sh.600001", d3, "pm", 1000, "3")], {"sh.600001": D("3")}),
        led_day(d4, [], {"sh.600001": D("2")},
                splits=[SplitAction("sh.600001", d4, D("1.3"))]),
    ])
    r4 = led2.days[1]
    assert r4.held_shares["sh.600001"] == 1300
    assert r4.sellable_shares["sh.600001"] == 1000    # 新增 300 为整手，当日不可卖


# --------------------------------------------------------------------------- #
# C 表：九类反证注入
# --------------------------------------------------------------------------- #
def test_inject_duplicate_fill():
    d1 = date(2020, 6, 2)
    f = buy("F1", "sh.600000", d1, "pm", 1000, "10")
    led = ReferenceLedger(100000)
    with pytest.raises(DuplicateFillError):
        led.replay([led_day(d1, [f, f], {"sh.600000": D("10")})])


def test_inject_price_unit_x100():
    """价格×100：成交价越出当日涨跌停或与 notional 不一致，必须报错。"""
    d1 = date(2020, 6, 2)
    led = ReferenceLedger(1000000)
    with pytest.raises(PriceLegalityError):
        led.replay([led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "1000",
                                    down_limit=D("9"), up_limit=D("11"),
                                    prev_close=D("10"))],
                            {"sh.600000": D("10")})])
    # 价格×100 但 notional 未同步
    led2 = ReferenceLedger(1000000)
    with pytest.raises(NotionalConsistencyError):
        led2.replay([led_day(d1, [buy("F2", "sh.600000", d1, "pm", 1000, "1000",
                                      notional=D("1000"))],
                             {"sh.600000": D("10")})])


def test_inject_dividend_per_lot_as_per_share():
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(200000)
    with pytest.raises(DividendUnitError):
        led.replay([
            led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "100")],
                    {"sh.600000": D("100")}),
            # 每手 5 元被当成每股 5 元（round_lot=10 → 应为 0.5）
            led_day(d2, [], {"sh.600000": D("100")},
                    dividends=[DividendAction("sh.600000", d2, D("5.0"),
                                              cash_per_lot=D("5.0"), round_lot=10)]),
        ])

def test_inject_cost_sign_flip():
    d1 = date(2020, 6, 2)
    led = ReferenceLedger(100000)
    with pytest.raises(CashSignError):
        led.replay([led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10",
                                     net_cash_flow=D("10005"))],
                            {"sh.600000": D("10")})])


def test_inject_sale_proceeds_early_availability():
    """同一 session 内卖出款被用于买入 → 结算时序错误。"""
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(10020)     # 刚够买 1000@10（10005）
    with pytest.raises(SettlementTimingError):
        led.replay([
            led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")],
                    {"sh.600000": D("10")}),
            # am 卖出 1000@10（净 9945，pm 才可用）；同上午买 20000@9 依赖该款
            led_day(d2, [sell("F2", "sh.600000", d2, "am", 1000, "10"),
                         buy("F3", "sh.600001", d2, "am", 20000, "9")],
                    {"sh.600000": D("10")}),
        ])


def test_positive_control_am_proceeds_usable_at_pm():
    """正向对照：上午卖出款当日下午可用（同一安排换到 pm 即通过）。"""
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(10020)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")],
                {"sh.600000": D("10")}),
        led_day(d2, [sell("F2", "sh.600000", d2, "am", 1000, "10"),
                     buy("F3", "sh.600001", d2, "pm", 900, "9")],
                {"sh.600000": D("10"), "sh.600001": D("9")}),
    ])
    assert led.days[1].held_shares.get("sh.600001") == 900


def test_inject_stale_clip_reuse():
    """旧批次状态残留：引用已清空的批次 id 再卖，必须报错。"""
    d1, d2, d3 = date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4)
    led = ReferenceLedger(100000)
    with pytest.raises(StaleClipError):
        led.replay([
            led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10",
                             clip_id="CLIP-A")], {"sh.600000": D("10")}),
            led_day(d2, [sell("F2", "sh.600000", d2, "am", 1000, "10",
                              clip_id="CLIP-A")], {}),
            led_day(d3, [sell("F3", "sh.600000", d3, "am", 1000, "10",
                              clip_id="CLIP-A")], {}),
        ])


def test_inject_temporal_leak_am_uses_today_anchor():
    d1 = date(2020, 6, 2)
    led = ReferenceLedger(100000)
    with pytest.raises(TemporalLeakError):
        led.replay([led_day(d1, [buy("F1", "sh.600000", d1, "am", 1000, "10",
                                     decision_session="am", anchor_day=d1)],
                            {"sh.600000": D("10")})])


def test_inject_missing_first_year_return():
    """首年收益遗漏：年度覆盖不完整必须报错。"""
    returns = {2016: D("0.10"), 2017: D("0.05")}
    with pytest.raises(CoverageError):
        assert_full_year_coverage(returns, 2015, 2017)
    # 正向：完整覆盖通过
    assert_full_year_coverage({2015: D("-0.02"), 2016: D("0.10")}, 2015, 2016)


def test_inject_negative_mdd_comparison():
    """负号 MDD 误比较：−30% 幅度不得当作 '< 20%' 通过。"""
    with pytest.raises(SignConventionError):
        assert_drawdown_gate(D("-0.30"), D("0.20"))
    # 正号幅度正确参与比较
    assert_drawdown_gate(D("0.15"), D("0.20"))
    with pytest.raises(Exception):
        assert_drawdown_gate(D("0.30"), D("0.20"))


# --------------------------------------------------------------------------- #
# 专项：T+1 / 结算 / 公司行动衔接
# --------------------------------------------------------------------------- #
def test_t_plus_one_same_day_sell_rejected():
    d1 = date(2020, 6, 2)
    led = ReferenceLedger(100000)
    with pytest.raises(TPlusViolationError):
        led.replay([led_day(d1, [buy("F1", "sh.600000", d1, "am", 1000, "10"),
                                 sell("F2", "sh.600000", d1, "pm", 1000, "10")],
                            {"sh.600000": D("10")})])


def test_t_plus_one_next_day_sell_allowed():
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "am", 1000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [sell("F2", "sh.600000", d2, "am", 1000, "10")], {}),
    ])
    assert led.days[1].held_shares == {}


def test_over_sell_rejected():
    d1 = date(2020, 6, 2)
    led = ReferenceLedger(100000)
    with pytest.raises(ClipOverConsumptionError):
        led.replay([
            led_day(d1, [buy("F1", "sh.600000", d1, "am", 1000, "10")],
                    {"sh.600000": D("10")}),
            led_day(date(2020, 6, 3),
                    [sell("F2", "sh.600000", date(2020, 6, 3), "am", 1500, "10")], {}),
        ])


def test_cash_shortfall_without_same_session_sale():
    d1 = date(2020, 6, 2)
    led = ReferenceLedger(1000)
    with pytest.raises(CashShortfallError):
        led.replay([led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")],
                            {"sh.600000": D("10")})])


def test_settlement_two_stage_buckets():
    """pm 卖出款进入待结算，次一交易日 am 才转可用。"""
    d1, d2, d3 = date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [sell("F2", "sh.600000", d2, "pm", 1000, "10")], {}),
        led_day(d3, [], {}),
    ])
    r2, r3 = led.days[1], led.days[2]
    # 卖 1000@10：佣金 5、印花 10 → net 9985
    assert q(r2.unsettled_sale_proceeds) == q(9985)
    assert q(r2.free_settled_cash) == q(89995)
    assert q(r3.free_settled_cash) == q(99980)
    assert r3.unsettled_sale_proceeds == 0


def test_corporate_action_before_fills_on_ex_date():
    """除权日公司行动先于成交判定：am 买入按变换后的价格成交。"""
    d1, d2 = date(2020, 6, 2), date(2020, 6, 3)
    led = ReferenceLedger(100000)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 1000, "10")], {"sh.600000": D("10")}),
        # 除权日：split 2:1；同日 pm 再买 1000@5
        led_day(d2, [buy("F2", "sh.600000", d2, "pm", 1000, "5")], {"sh.600000": D("5")},
                splits=[SplitAction("sh.600000", d2, D("2"))]),
    ])
    r2 = led.days[1]
    assert r2.held_shares["sh.600000"] == 3000     # 2000（变换）+ 1000（当日买入）
    assert q(r2.position_mv) == q(3000 * 5)


# --------------------------------------------------------------------------- #
# TV-B30：固定成交序列的费用单调性
# --------------------------------------------------------------------------- #
def _fixed_path(fees: FeeSchedule) -> Decimal:
    d1, d2, d3 = date(2020, 6, 2), date(2020, 6, 3), date(2020, 6, 4)
    led = ReferenceLedger(500000, fees=fees)
    led.replay([
        led_day(d1, [buy("F1", "sh.600000", d1, "pm", 5000, "10")], {"sh.600000": D("10")}),
        led_day(d2, [sell("F2", "sh.600000", d2, "am", 5000, "12")], {}),
        led_day(d3, [], {}),
    ])
    return led.days[-1].equity


def test_tv_b30_fee_monotonicity_fixed_path():
    base = _fixed_path(FeeSchedule())
    higher_commission = _fixed_path(FeeSchedule(commission_rate=D("0.0005"),
                                                commission_floor=D("10.00")))
    higher_stamp = _fixed_path(FeeSchedule(stamp_sell_before=D("0.002"),
                                           stamp_sell_on_after=D("0.001")))
    assert higher_commission <= base
    assert higher_stamp <= base
    assert higher_commission < base      # 该路径买入名义 50000 触发佣金上行
    assert higher_stamp < base


def test_mdd_magnitude_positive():
    eq = [D("500000"), D("450000"), D("480000"), D("400000")]
    mdd = ReferenceLedger.max_drawdown_magnitude(eq)
    # 峰值 500000 → 谷底 400000 → 幅度 20%
    assert q(mdd) == q("0.20")
