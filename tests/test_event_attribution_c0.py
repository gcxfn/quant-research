# -*- coding: utf-8 -*-
"""C0 归因修正测试（复审 2026-09-21 §四/§六/§八 要求的三项必测）。

被测对象：
- ``quant.research.attribution_lib``：边界感知收益窗、漏斗分类、
  成交成本收益、FIFO 净损益；
- ``quant.research.event_family_signals``：B1 严格数值臂。

运行：``PYTHONPATH=src python -m pytest tests/test_event_attribution_c0.py``
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

import numpy as np
import pytest

sys.path.insert(0, "src")

from quant.research.attribution_lib import (  # noqa: E402
    BuyLot, DividendCash, SellFill, classify_admission, complete_stats,
    fill_cost_return, fifo_event_pnl, tr_window)
from quant.research.event_family_signals import (  # noqa: E402
    FamilyParams, b1_revision_events)

DEV_END = date(2020, 12, 31)


def _sessions(start: date, n: int, step_days: int = 1):
    return [start + timedelta(days=step_days * i) for i in range(n)]


def _mk_series(values, start=date(2020, 6, 1)):
    ds = _sessions(start, len(values))
    return ([d.toordinal() for d in ds], np.asarray(values, float), ds)


# --- 复审必测 1：2020-12-28 事件在 Dev 模式不能产生完整 20 日标签 ---------

def test_boundary_event_20201228_has_no_complete_label():
    # 2020-12-29 决策（公告 2020-12-28 的次一交易日），+20 自身交易日
    # 落在 2021-01；Dev 模式下必须判为不完整（右删失），不得进入
    # 完整窗口统计。
    ords, vals, ds = _mk_series(
        [100.0] * 214 + [101.0] * 20, start=date(2020, 11, 2))
    anchor = date(2020, 12, 29)
    assert anchor.toordinal() in ords
    w = tr_window(ords, vals, anchor, 20, DEV_END)
    assert w.window_complete is False
    assert w.crosses_dev_boundary is True
    assert w.end_date is not None and w.end_date > DEV_END
    assert complete_stats([w.factor], [w.window_complete]) is None
    assert fill_cost_return(w, 100.0, 101.0) is None


def test_pre_boundary_window_is_complete():
    ords, vals, _ = _mk_series([100.0] * 200, start=date(2020, 6, 1))
    w = tr_window(ords, vals, date(2020, 11, 2), 20, DEV_END)
    assert w.window_complete is True and w.crosses_dev_boundary is False
    st = complete_stats([w.factor], [w.window_complete])
    assert st["n"] == 1


def test_suspension_anchor_falls_back_to_last_session():
    ds = [date(2020, 6, 1), date(2020, 6, 2), date(2020, 6, 3),
          date(2020, 6, 5), date(2020, 6, 8)]     # 6-4/6-6/6-7 停牌
    ords = [d.toordinal() for d in ds]
    vals = np.linspace(100, 120, 5)
    w = tr_window(ords, vals, date(2020, 6, 3), 1, DEV_END)
    assert w.anchor_date == date(2020, 6, 3)
    w2 = tr_window(ords, vals, date(2020, 6, 4), 1, DEV_END)
    assert w2.anchor_date == date(2020, 6, 3)   # 停牌回退到前一交易日


# --- 复审必测 2：2021 年后价格任意改写，Dev 完整窗口统计必须不变 ---------

def test_post_dev_rewrite_leaves_complete_stats_unchanged():
    ds = _sessions(date(2020, 7, 1), 220)          # 覆盖到 2021-02
    ords = [d.toordinal() for d in ds]
    rng = np.random.default_rng(7)
    vals = 100.0 * np.cumprod(1.0 + rng.normal(0, 0.02, 220))
    anchors = [date(2020, 11, 2), date(2020, 11, 16), date(2020, 12, 15)]

    def stats(v):
        fs, ok = [], []
        for a in anchors:
            w = tr_window(ords, v, a, 20, DEV_END)
            fs.append(w.factor if w.window_complete else None)
            ok.append(w.window_complete)
        return complete_stats(fs, ok)

    before = stats(vals)
    assert before is not None and before["n"] == 2  # 12-15 越界被排除
    vals2 = vals.copy()
    for i, o in enumerate(ords):
        if date.fromordinal(o) > DEV_END:
            vals2[i] *= 7.31                        # 任意改写 2021+ 价格
    after = stats(vals2)
    assert after == before


# --- 复审必测 3：type 改善但净利润区间下限下降，严格数值臂必须不触发 -----

def _row(sym, end, ann, flag, typ, nmin, nmax):
    return {"symbol": sym, "end_date": end, "ann_date": ann,
            "update_flag": flag, "type": typ, "primary_code": "orders",
            "net_profit_min": nmin, "net_profit_max": nmax}


ROWS = [
    # sym A：type 预减→略增（改善），但区间下限 100→50 下降、中位数上移
    _row("sz.000001", "20200930", "20201010", "0", "预减", 100.0, 200.0),
    _row("sz.000001", "20200930", "20201020", "1", "略增", 50.0, 300.0),
    # sym B：type 不变，中位数上移且下限上移（纯数值上修）
    _row("sz.000002", "20200930", "20201010", "0", "预增", 100.0, 200.0),
    _row("sz.000002", "20200930", "20201020", "1", "预增", 150.0, 260.0),
    # sym C：type 改善但净利润区间缺失
    _row("sz.000003", "20200930", "20201010", "0", "续亏", None, None),
    _row("sz.000003", "20200930", "20201020", "1", "扭亏", None, None),
]

P_DEFAULT = FamilyParams("B1")
P_STRICT = FamilyParams("B1", b1_strict_numeric=True)


def _fire(p):
    evs = b1_revision_events(ROWS, {}, lambda s, d: True,
                             lambda d: d + timedelta(days=1), p)
    return {e.symbol: e for e in evs}


def test_strict_numeric_arm_type_upgrade_with_floor_down_not_firing():
    fired_default = _fire(P_DEFAULT)
    fired_strict = _fire(P_STRICT)
    # 默认臂（type OR 数值）：A/C 走 type 分支触发，B 走数值分支触发
    assert set(fired_default) == {"sz.000001", "sz.000002", "sz.000003"}
    assert fired_default["sz.000001"].type_upgrade is True
    assert fired_default["sz.000001"].numeric_revision is False
    assert fired_default["sz.000002"].type_upgrade is False
    assert fired_default["sz.000002"].numeric_revision is True
    assert fired_default["sz.000002"].numeric_available is True
    assert fired_default["sz.000003"].numeric_available is False
    # 严格数值臂：A（下限下降）与 C（数值缺失）必须不触发
    assert set(fired_strict) == {"sz.000002"}
    assert fired_strict["sz.000002"].numeric_revision is True


# --- 漏斗分类：按 provider 判定顺序，含同决策点席位竞争 -------------------

class _Ev:
    def __init__(self, sym, cap=None):
        self.symbol = sym
        self.cap_price = cap


def test_classify_admission_order_and_seat_competition():
    evs = [_Ev("a"), _Ev("b"), _Ev("c"), _Ev("d"), _Ev("e")]
    out, counts = classify_admission(
        evs, held={"x", "y"}, pending_survived={"z"}, entry_allowed=True,
        anchor_of=lambda s: 10.0, cap_of=lambda e: None, max_seats=4,
        risk_state="normal")
    # 2 held + 1 pending = 3 席，第 4 席给 a；b 起席位满
    assert [o.category for o in out] == [
        "issued", "slot_full", "slot_full", "slot_full", "slot_full"]
    assert counts == {"issued": 1, "slot_full": 4}
    assert out[0].pending_seats == 1      # 自己占用前（仅挂单席位）
    assert out[0].held_seats == 2
    assert out[1].pending_seats == 2      # 含同点先发的 a


def test_classify_admission_risk_gate_first():
    out, counts = classify_admission(
        [_Ev("a")], held=set(), pending_survived=set(), entry_allowed=False,
        anchor_of=lambda s: 10.0, cap_of=lambda e: None, max_seats=4,
        risk_state="cooldown")
    assert out[0].category == "risk_blocked"
    assert out[0].risk_state == "cooldown"


# --- FIFO 净损益 ------------------------------------------------------------

def test_fifo_event_pnl_partial_sells_and_dividend():
    lots = [
        BuyLot("E1", "sz.1", 100, -1010.0, date(2020, 1, 1), 1),
        BuyLot("E2", "sz.1", 100, -2020.0, date(2020, 2, 1), 2),
    ]
    sells = [SellFill("sz.1", 150, 1650.0, date(2020, 3, 1))]
    divs = [DividendCash("sz.1", 100.0, date(2020, 2, 15))]
    res = fifo_event_pnl(lots, sells, divs)
    # 卖出 150 股按 FIFO：E1 全部 100 股 + E2 的 50 股
    e1, e2 = res["E1"], res["E2"]
    assert e1.sold_shares == 100 and e2.sold_shares == 50
    assert e1.sell_proceeds == pytest.approx(1100.0)
    assert e2.sell_proceeds == pytest.approx(550.0)
    # 2020-02-15 分红时 E1 持有 100 股、E2 持有 100 股 → 平分
    assert e1.dividend_cash == pytest.approx(50.0)
    assert e2.dividend_cash == pytest.approx(50.0)
    assert e1.realized_net_pnl == pytest.approx(-1010.0 + 1100.0 + 50.0)
    assert e2.realized_net_pnl == pytest.approx(-2020.0 + 550.0 + 50.0)
    assert e2.open_shares == 50


def test_fifo_event_pnl_marking_open_lot():
    lots = [BuyLot("E1", "sz.1", 100, -1000.0, date(2020, 1, 1), 1)]
    res = fifo_event_pnl(lots, [], [], last_close_of=lambda s: 12.0)
    assert res["E1"].open_shares == 100
    assert res["E1"].open_value_marked == pytest.approx(1200.0)
    assert res["E1"].realized_net_pnl == pytest.approx(-1000.0)


def test_fill_cost_return_math():
    class W:  # 最小窗口替身
        window_complete = True
        factor = 1.10
    assert fill_cost_return(W(), 10.0, 9.9) == pytest.approx(
        1.10 * 9.9 / 10.0 - 1.0)
    W.window_complete = False
    assert fill_cost_return(W(), 10.0, 9.9) is None
