# -*- coding: utf-8 -*-
"""C0 归因修正的可测试核心（复审 2026-09-21 §三/§四/§八-C0）。

上一轮归因（run 20260921T230639）的三个缺陷在此修复：
1. 收益窗终点不受 DEV_END 约束——``tr_window`` 显式给出窗口终点、
   完整性与跨界标记，聚合统计只纳入完整窗口；
2. "未成交"把席位跳过和挂单未成交混为一谈——``classify_admission``
   按 provider 的判定顺序逐事件给出接纳/跳过类别；
3. 收益起点不用实际成交价——``fill_cost_return`` 以真实成交成本
   （成交价 × 复权增长 × 当日收盘校准）起算。

全部函数为纯函数，测试用它们证明：Dev 完整窗口的统计在 2021 年
之后价格被任意改写时不变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Mapping, NamedTuple, Sequence

import numpy as np

DEV_END_DEFAULT = date(2020, 12, 31)


class TRWindow(NamedTuple):
    """一个 n 自身交易日总收益窗的边界感知结果。

    factor 仅为诊断值；右删失窗口（window_complete=False）的 factor
    可以读取边界后价格，但聚合统计必须排除（见 ``complete_stats``）。
    """

    factor: float | None
    anchor_date: date | None
    end_date: date | None
    window_complete: bool
    crosses_dev_boundary: bool
    no_data: bool              # 数据不足，连窗口终点都不存在


def tr_window(ordinals: Sequence[int], values: np.ndarray,
              anchor: date, n_sessions: int,
              dev_end: date = DEV_END_DEFAULT) -> TRWindow:
    """anchor 收盘（停牌则取 anchor 前最后一个自身交易日）起 n 个
    自身交易日的总收益窗。ordinals 为升序 date.toordinal() 序列，
    values 为同一顺序的复权价。"""
    a0 = anchor.toordinal()
    i = int(np.searchsorted(ordinals, a0))
    if i >= len(ordinals) or ordinals[i] != a0:
        i -= 1                   # 停牌：锚定 anchor 前最后一个交易日
    if i < 0 or values[i] <= 0:
        return TRWindow(None, None, None, False, False, True)
    anchor_eff = date.fromordinal(int(ordinals[i]))
    j = i + n_sessions
    if j >= len(ordinals):
        return TRWindow(None, anchor_eff, None, False, False, True)
    end = date.fromordinal(int(ordinals[j]))
    factor = float(values[j] / values[i])
    complete = end <= dev_end
    return TRWindow(factor, anchor_eff, end, complete, end > dev_end, False)


def complete_stats(factors: Sequence[float | None],
                   complete_flags: Sequence[bool]) -> dict | None:
    """仅完整窗口进入统计；右删失窗口保留在别处，不混算。"""
    vals = [f for f, ok in zip(factors, complete_flags)
            if ok and f is not None]
    if not vals:
        return None
    a = np.asarray(vals, dtype=np.float64)
    return {"n": int(a.size), "mean": float(a.mean()),
            "median": float(np.median(a)), "win": float((a > 0).mean())}


def fill_cost_return(win: TRWindow, fill_price: float,
                     raw_close_on_fill_day: float) -> float | None:
    """真实成交成本起的窗口收益：成交价持有到期末 = 成交价 × 复权
    增长 × （期末按当日收盘校准的日内入场偏移）。仅完整窗口给出。"""
    if not win.window_complete or win.factor is None:
        return None
    if fill_price <= 0 or raw_close_on_fill_day <= 0:
        return None
    return float(win.factor * raw_close_on_fill_day / fill_price - 1.0)


def decision_to_fill_return(fill_price: float,
                            decision_anchor: float) -> float | None:
    """决策锚价（B1 为决策日 am 半日收盘）到实际成交价的收益。"""
    if decision_anchor is None or decision_anchor <= 0 or fill_price <= 0:
        return None
    return float(fill_price / decision_anchor - 1.0)


# --- 事件接纳漏斗 ---------------------------------------------------------

CATEGORY_ISSUED = "issued"
CATEGORY_RISK_BLOCKED = "risk_blocked"      # 账户级风控不允许新进攻仓位
CATEGORY_HELD_PENDING = "held_or_pending"   # 已持有或已有挂单
CATEGORY_SLOT_FULL = "slot_full"            # 4 席满员
CATEGORY_NO_PRICE = "no_price"              # 决策点无行情锚价
CATEGORY_CAP = "cap"                        # A 家族：锚价越过追价上限


@dataclass
class AdmissionOutcome:
    symbol: str
    rank: int                  # 同一决策点事件表内的序位（1 起）
    category: str
    held_seats: int            # 该事件评估时已持有席位数
    pending_seats: int         # 该事件评估时已挂单席位数（含同点先发）
    risk_state: str
    anchor_price: float | None
    cap_price: float | None


def classify_admission(
        events: Sequence[object], held: set[str],
        pending_survived: set[str], entry_allowed: bool,
        anchor_of: Callable[[str], float | None],
        cap_of: Callable[[object], float | None],
        max_seats: int,
        risk_state: str = "") -> tuple[list[AdmissionOutcome], dict[str, int]]:
    """按 EventFamilyProvider.provider 第 3 步的判定顺序复刻逐事件
    接纳结果：entry_allowed 门在最外层，然后 held/pending → 席位 →
    锚价 → 追价上限。返回逐事件结果与计数（用于与 provider 自身的
    trigger_stats 逐项核对，不一致即实现分歧）。"""
    out: list[AdmissionOutcome] = []
    counts: dict[str, int] = {}
    pending_at = set(pending_survived)
    for rank, ev in enumerate(events, start=1):
        sym = str(ev.symbol)
        anchor = anchor_of(sym)
        cap = cap_of(ev)
        if not entry_allowed:
            cat = CATEGORY_RISK_BLOCKED
        elif sym in held or sym in pending_at:
            cat = CATEGORY_HELD_PENDING
        elif len(held) + len(pending_at) + 1 > max_seats:
            cat = CATEGORY_SLOT_FULL
        elif anchor is None or anchor <= 0:
            cat = CATEGORY_NO_PRICE
        elif cap is not None and anchor > cap:
            cat = CATEGORY_CAP
        else:
            cat = CATEGORY_ISSUED
            pending_at.add(sym)
        out.append(AdmissionOutcome(
            symbol=sym, rank=rank, category=cat, held_seats=len(held),
            pending_seats=len(pending_at) - (1 if cat == CATEGORY_ISSUED else 0),
            risk_state=risk_state, anchor_price=anchor, cap_price=cap))
        counts[cat] = counts.get(cat, 0) + 1
    return out, counts


# --- 按事件的 FIFO 实际净损益 ----------------------------------------------

@dataclass
class BuyLot:
    event_id: str
    symbol: str
    shares: int
    net_cash_flow: float        # 买入为负（含费用）
    date: date
    seq: int                    # 全局成交顺序（FIFO 平手序）


@dataclass
class SellFill:
    symbol: str
    shares: int
    net_cash_flow: float        # 卖出为正（已扣费用）
    date: date


@dataclass
class DividendCash:
    symbol: str
    cash: float
    date: date


@dataclass
class EventPnL:
    event_id: str
    bought_shares: int = 0
    sold_shares: int = 0
    open_shares: int = 0
    buy_cost: float = 0.0       # -net_cash_flow 之和（正数成本）
    sell_proceeds: float = 0.0
    dividend_cash: float = 0.0
    realized_net_pnl: float = 0.0
    open_value_marked: float | None = None


def fifo_event_pnl(lots: Sequence[BuyLot], sells: Sequence[SellFill],
                   dividends: Sequence[DividendCash] = (),
                   last_close_of: Callable[[str], float | None] | None = None,
                   ) -> dict[str, EventPnL]:
    """按 symbol 的 FIFO 把卖出与分红现金分摊到买入批次（每笔买入
    成交即一个批次，对应一个事件）。期末未平仓份额按 ``last_close_of``
    估值标记（不并入 realized）。"""
    res: dict[str, EventPnL] = {}
    for lot in lots:
        res.setdefault(lot.event_id, EventPnL(lot.event_id))
        e = res[lot.event_id]
        e.bought_shares += lot.shares
        e.buy_cost += -lot.net_cash_flow
        e.realized_net_pnl += lot.net_cash_flow

    by_sym: dict[str, list[BuyLot]] = {}
    for lot in sorted(lots, key=lambda x: x.seq):
        by_sym.setdefault(lot.symbol, []).append(lot)

    # 卖出与分红按时间顺序穿插处理：分红只分摊给除息日仍持有的份额
    events_chrono = sorted(
        [("sell", s.date.toordinal(), s) for s in sells]
        + [("div", d.date.toordinal(), d) for d in dividends],
        key=lambda x: (x[1], x[0]))
    for kind, _, item in events_chrono:
        if kind == "sell":
            sell = item
            queue = by_sym.get(sell.symbol, [])
            remaining = sell.shares
            while remaining > 0 and queue:
                lot = queue[0]
                take = min(remaining, lot.shares)
                alloc = sell.net_cash_flow * take / sell.shares
                e = res[lot.event_id]
                e.sell_proceeds += alloc
                e.realized_net_pnl += alloc
                e.sold_shares += take
                remaining -= take
                lot.shares -= take
                if lot.shares == 0:
                    queue.pop(0)
            if remaining != 0:
                raise ValueError(
                    f"FIFO 无法分摊卖出 {sell.symbol} {sell.date} "
                    f"剩余 {remaining} 股（买入台账不足）")
        else:
            div = item
            held_by_event: dict[str, int] = {}
            total = 0
            for lot in by_sym.get(div.symbol, []):
                if lot.shares > 0 and lot.date <= div.date:
                    held_by_event[lot.event_id] = held_by_event.get(
                        lot.event_id, 0) + lot.shares
                    total += lot.shares
            if total <= 0:
                continue
            for eid, sh in held_by_event.items():
                part = div.cash * sh / total
                res[eid].dividend_cash += part
                res[eid].realized_net_pnl += part

    for sym, queue in by_sym.items():
        for lot in queue:
            if lot.shares > 0:
                e = res[lot.event_id]
                e.open_shares += lot.shares
                if last_close_of is not None:
                    px = last_close_of(sym)
                    if px is not None:
                        mark = (e.open_value_marked or 0.0) + lot.shares * px
                        e.open_value_marked = mark
    return res
