# -*- coding: utf-8 -*-
"""C3 独立撮合参考实现（第二套成交判定）。

使命：**给定同一份具体订单，独立回答「为何会成交」**。本模块是 C3-A 的
独立 matcher，只吃四类输入：

1. ``order_id`` 级订单（证券/方向/数量/限价/决策点/生效半日/意图/来源/
   替代关系）；
2. 许可半日 bar（OHLC；调用方经 ``quant.data.dev_sandbox`` 载入后以
   ``Bar`` 传入）；
3. 历史涨跌停表（当日 up/down；**缺行=数据缺口，按保守口径拒绝**）；
4. 同一份资金合同（``quant.research.reference_ledger.FeeSchedule``：
   万1 佣金 + 5 元下限、卖出印花税 2023-08-28 分段、ETF 免印花；
   每笔现金变动 ROUND_HALF_UP 到分）。

独立性硬约束（C3-01）：本模块**不 import 也不调用 ``quant.backtest`` 与
``quant.portfolio``**，不复制 band_engine 的穿透/价格合法性/生命周期函数，
不调用策略选股。所有判定用 ``Decimal`` 与显式比较重写；语义来源是冻结
合同（``docs/plans/p3-band-contract.md`` §7/§8）与 C0/C1 合同快照
（``contract_snapshot.json`` 的 strict_crossing / gap_fill_policy /
settlement_delay / t_plus_and_round_lot / risk_fallback；
``interface_contract.json`` 的 order_status / entry_price_dual_track），
不是主引擎代码。

判定语义（与冻结合同一一对应）：

* 严格穿透：买 ``session low < 限价`` 成交于限价；卖 ``session high > 限价``
  成交于限价；触价（==）不成交；跳空按限价、不取更优价。
* 价格合法性：限价必须落在当日 ``[down, up]`` 内；缺涨跌停行即拒绝
  （C1 数据卡第 4 卡：2017-03-07..09 三日整缺）。
* 无 bar（停牌/缺半日行）→ 该半日不可成交；风险卖单计数冻结。
* T+1 逐 clip：当日取得的份额当日不可卖；T+0 品种在**更晚**的 session
  可卖（同一 session 内先买后卖不可观测，禁用）；公司行动零股当日可卖。
* 卖出资金晚一个 session 到账：am 成交当日 pm 可用，pm 成交次日 am 可用；
  同一 session 内先卖后买的路径禁用。
* K=3 兜底：风险类卖单连续 3 个成交机会未成交 → 下一 session 开盘市价退出；
  开盘跌停顺延；停牌冻结计数；止盈类到期静默失效、无兜底。
* 单只上限 25%（决策点权益快照，构建时整单作废、不缩量）与总资金约束。
* ``expires_at`` 已过则不再判定（防止过期/被替代订单被延迟 wrapper 复活）。

本模块不假设任何日内路径：一个半日只有一个 bar，``low < p`` 与 ``high > q``
是该半日内可达的最保守陈述。

接管审查（2026-09-22，C3 实施）：本文件在被接管时已有 758 行草稿。逐项核验
后**修复**的缺陷（原草稿未经过任何测试）：

* A1 ``match_open`` 对卖单一律抛 ``ValueError``——开环主路径实际不可用（桩）。
  改为显式状态契约：``judge_open(orders, states)`` 必须给卖单状态，缺失则
  fail-closed 报错（不臆造数量，也不静默跳过）。
* A2 ``judge_session`` 卖单费率调用漏传 ``symbol``，ETF 卖出被错加印花税。
* A3 ``Book.book_sell`` 用 ``list.index(clip)`` 定位批次——``Clip`` 是值相等
  的 frozen dataclass，同值批次会改错对象（重复成本批次场景）。改为按
  ``id(lead)`` 精确消耗。
* A4 无 ``expires_at`` 守卫，过期订单只要被放进 ``run()`` 就会被判定成交。
* A5 无 ``replaces_order_id``/同 intent 覆盖规则，"被替代"订单可与替代单同时
  成交（TV-B13/TV-B14 不可表达）。
* A6 无部分成交语义：卖单超可卖量时静默按可卖量成交，但不区分
  ``partial_fill``/``full_fill`` 末状态，也不登记剩余股数（TV-B14）。
* A7 风险单 K 计数在 ``limit_illegal``/``limit_missing`` 之外的
  ``cash_short``/``below_lot`` 等本不该出现的卖单原因上也会累加；
  现集中为白名单（沿 m1：停牌冻结、缺涨跌停计入、T+1 锁定计入）。
* A8 无公司行动份额变换 → 除权日后的可卖量与 K3 兜底数量会错。
* A9 ``Verdict.status`` 缺 ``partial_fill``，且 ``at_target`` 等映射未经合同
  枚举核对。
* A10 ``BarTable.session_pairs`` 只覆盖“有 bar 的半日”，日历须由调用方显式
  传入（原 docstring 已提示，现改为强制：``run`` 缺 calendar 时拒绝）。

以上均在 ``docs/evidence/trust-rebuild/20260922T*-trust-c3-*/c3_case_report.md``
的「接管审查发现」一节登记。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from quant.research.reference_ledger import FeeSchedule, cent

__all__ = [
    "LOT", "CAP_SINGLE_NAME", "K_FALLBACK_SESSIONS", "LIMIT_DOWN_TOL",
    "BUY", "SELL", "INTENT_ENTRY", "INTENT_RISK", "INTENT_PROFIT",
    "REASONS", "SESSIONS", "Bar", "LimitRow", "Order", "Verdict", "Clip",
    "JudgeState", "Book", "BarTable", "LimitTable", "ReferenceMatcher",
    "price_legal", "live_slot_for",
]

# --- 冻结合同常量（独立重述，不从 quant.backtest 导入） --------------------
LOT = 100
CAP_SINGLE_NAME = Decimal("0.25")        # 单只 ≤25% 决策点权益
K_FALLBACK_SESSIONS = 3                  # 风险卖单连续 3 个成交机会未成交
LIMIT_DOWN_TOL = Decimal("0.0001")       # 开盘跌停判定容差（m5 语义）
_FLOAT_TOL = Decimal("0.000000001")

BUY, SELL = "buy", "sell"
SESSIONS = ("am", "pm")
INTENT_ENTRY, INTENT_RISK, INTENT_PROFIT = "", "risk", "profit"

#: 未成交/终止原因枚举（与 interface_contract.event_order_lifecycle 对齐）。
REASONS = (
    "filled",
    "partial_fill",
    "never_crossed",        # 严格穿透未成立（触价不成）
    "suspended",            # 无 bar：停牌或缺半日行
    "limit_illegal",        # 限价越界
    "limit_missing",        # 涨跌停表缺行（含 2017-03-07..09 整日缺口）
    "expired",              # 半日单到期 / 超过 expires_at
    "cancelled_cap",        # 单只上限整单作废
    "cancelled_signal",     # 被替代/来源失效
    "replaced",             # 被同 intent 的新单覆盖
    "cash_short",           # 资金不足
    "below_lot",            # 不足一手
    "t1_locked",            # 全部份额当日买入（T+1 锁定）
    "no_position",          # 无可卖持仓
    "at_target",            # 已到目标仓位，不签发
)

#: 末状态映射（C1 interface_contract.tables.orders.order_status 枚举）。
_STATUS_BY_REASON = {
    "filled": "full_fill",
    "partial_fill": "partial_fill",
    "never_crossed": "expired",
    "expired": "expired",
    "suspended": "expired",
    "t1_locked": "expired",
    "limit_illegal": "rejected",
    "limit_missing": "rejected",
    "cash_short": "rejected",
    "below_lot": "rejected",
    "cancelled_cap": "cancelled_cap",
    "cancelled_signal": "cancelled_signal",
    "no_position": "cancelled_signal",
    "at_target": "cancelled_signal",
    "replaced": "replaced",
}


def live_slot_for(decision_date: date, decision_session: str
                  ) -> tuple[date, str]:
    """冻结合同的半日路由（C0 ``decision_schedule.order_live_mapping``）：
    ``(D,'am') -> (D,'pm')``；``(D,'pm') -> (下一交易日,'am')``。

    下一交易日需要真实日历，本函数只处理同日部分；跨日路由由调用方用
    日历时序推得（matcher 不内置交易日历）。
    """
    if decision_session not in SESSIONS:
        raise ValueError(f"decision_session must be am/pm, got {decision_session!r}")
    if decision_session == "am":
        return decision_date, "pm"
    raise ValueError("a pm decision lives in the NEXT trading day's am session; "
                     "the caller must supply the calendar")


# --------------------------------------------------------------------------- #
# 输入数据结构
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Bar:
    """一条半日 bar（不复权价，元）。``session`` ∈ {'am','pm'}。"""

    symbol: str
    day: date
    session: str
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if self.session not in SESSIONS:
            raise ValueError(f"session must be am/pm, got {self.session!r}")
        if not (self.low <= min(self.open, self.close)
                <= max(self.open, self.close) <= self.high):
            raise ValueError(
                f"inconsistent bar {self.symbol} {self.day} {self.session}: "
                f"o={self.open} h={self.high} l={self.low} c={self.close}")


@dataclass(frozen=True)
class LimitRow:
    """当日涨跌停价（元）。``up``/``down`` 为 None 表示该字段缺失。"""

    symbol: str
    day: date
    up: float | None
    down: float | None


@dataclass(frozen=True)
class Order:
    """``order_id`` 级具体订单（C3 的输入单位）。

    只有 ``target_weight`` 而没有解算后的限价/数量，不构成本阶段合法输入：
    调用方必须以 ``sizing_note`` 明确登记，不得由 matcher 代为解算策略意图。
    """

    order_id: str
    symbol: str
    side: str
    decision_date: date
    decision_session: str
    live_date: date
    live_session: str
    limit_price: float | None
    intent: str = INTENT_ENTRY
    shares: int | None = None               # 显式股数；None = 按 target_notional 解算
    requested_shares: int | None = None     # 合同字段 requested_shares（回放核对用）
    target_notional: float | None = None
    target_weight: float | None = None
    snapshot_equity: float | None = None    # 决策点权益快照（上限/权重解算）
    trigger_cap: float | None = None        # 签发门槛（≠ 限价，C-05 两轨）
    priority: int = 0
    source: str = ""                        # 来源信号身份（K 计数键的一部分）
    intent_id: str = ""                     # 同一经济意图跨重挂的身份
    intent_requested_shares: int | None = None   # 该意图合计请求股数（TV-B14）
    replaces_order_id: str | None = None
    created_at: datetime | None = None
    expires_at: date | None = None
    sizing_note: str = ""
    recorded_status: str = ""               # run 产物登记的末状态（核对用）
    recorded_reason: str = ""               # run 产物登记的原因（核对用）
    recorded_event: str = ""                # run 产物登记的事件名（核对用）

    def __post_init__(self) -> None:
        if self.side not in (BUY, SELL):
            raise ValueError(f"side must be buy/sell, got {self.side!r}")
        if self.intent not in (INTENT_ENTRY, INTENT_RISK, INTENT_PROFIT):
            raise ValueError(f"unknown intent {self.intent!r}")
        if self.side == BUY and self.intent != INTENT_ENTRY:
            raise ValueError("buy orders carry no exit intent")
        if self.side == SELL and self.intent == INTENT_ENTRY:
            raise ValueError("sell orders must declare intent risk/profit")
        if self.decision_session not in SESSIONS or self.live_session not in SESSIONS:
            raise ValueError("decision_session/live_session must be am/pm")
        if self.shares is not None and self.shares <= 0:
            raise ValueError("explicit shares must be positive")
        if (self.side == BUY and self.shares is not None
                and self.shares % LOT != 0):
            # 合同：买入 clip 必须整手；卖出允许公司行动产生的零股一次性卖出
            raise ValueError(f"explicit buy shares must be a multiple of {LOT}")


@dataclass
class Clip:
    """一个取得批次（成本 / 可卖量的最小单位）。

    ``seq`` 是批次的创建序号，用于按身份（而非值相等）消耗。
    """

    shares: int
    acquired: date
    session: str
    price: Decimal
    seq: int = 0


@dataclass
class JudgeState:
    """开环判定所需的账本状态（由调用方从**独立**证据导出，不由 matcher 猜）。"""

    available_cash: Decimal | None = None
    sellable_shares: int | None = None
    position_shares: int | None = None
    projected_mv: Decimal | None = None
    snapshot_equity: Decimal | None = None


@dataclass
class Verdict:
    """matcher 对一张订单在它的生效半日的独立判定。"""

    order_id: str
    symbol: str
    side: str
    intent: str
    live_date: date
    live_session: str
    filled: bool
    reason: str
    fill_type: str = ""            # 'limit' | 'market_fallback' | ''
    fill_date: date | None = None
    fill_session: str = ""
    shares: int | None = None      # 本次成交股数
    remaining_shares: int | None = None   # 本次之后的剩余请求股数
    price: Decimal | None = None
    gross_notional: Decimal | None = None
    commission: Decimal | None = None
    stamp_tax: Decimal | None = None
    fees_total: Decimal | None = None
    net_cash_flow: Decimal | None = None
    requested_shares: int | None = None
    bar_seen: bool = False
    limit_seen: bool = False
    limit_legality: str = ""       # 'ok' | 'illegal' | 'missing'
    note: str = ""

    @property
    def status(self) -> str:
        """interface_contract.order_status 口径的末状态。"""
        return _STATUS_BY_REASON.get(self.reason, "expired")


# --------------------------------------------------------------------------- #
# 行情与涨跌停索引
# --------------------------------------------------------------------------- #
def _dint(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


class BarTable:
    """半日 bar 索引：``(symbol, day, session) -> Bar``。"""

    def __init__(self, bars: Iterable[Bar]) -> None:
        self._by: dict[tuple[str, int, str], Bar] = {}
        for b in bars:
            key = (b.symbol, _dint(b.day), b.session)
            if key in self._by:
                raise ValueError(f"duplicate half-day bar {key}")
            self._by[key] = b

    def get(self, symbol: str, day: date, session: str) -> Bar | None:
        return self._by.get((symbol, _dint(day), session))

    def session_pairs(self) -> list[tuple[date, str]]:
        out = {(b.day, b.session) for b in self._by.values()}
        return sorted(out, key=lambda x: (_dint(x[0]), 0 if x[1] == "am" else 1))

    def symbols(self) -> set[str]:
        return {k[0] for k in self._by}

    def __len__(self) -> int:
        return len(self._by)


class LimitTable:
    """涨跌停表索引：``(symbol, day) -> (up, down)``；缺行返回 None。"""

    def __init__(self, rows: Iterable[LimitRow]) -> None:
        self._by: dict[tuple[str, int], tuple[float | None, float | None]] = {}
        for r in rows:
            key = (r.symbol, _dint(r.day))
            if key in self._by:
                raise ValueError(f"duplicate limit row {key}")
            self._by[key] = (r.up, r.down)

    def get(self, symbol: str, day: date) -> tuple[float | None, float | None] | None:
        """``None`` = 表内没有该 (symbol, day) 行（数据缺口，须保守拒绝）。"""
        return self._by.get((symbol, _dint(day)))

    def __len__(self) -> int:
        return len(self._by)


def price_legal(price: float | None, up: float | None,
                down: float | None) -> str:
    """限价合法性：'ok' | 'illegal' | 'missing'（缺表行=不可判定=拒绝）。"""
    if up is None and down is None:
        return "missing"
    if price is None:
        return "illegal"
    p = Decimal(str(price))
    if up is not None and p > Decimal(str(up)) + _FLOAT_TOL:
        return "illegal"
    if down is not None and p < Decimal(str(down)) - _FLOAT_TOL:
        return "illegal"
    return "ok"


# --------------------------------------------------------------------------- #
# 迷你账本（独立实现；只服务 matcher 的闭环状态响应）
# --------------------------------------------------------------------------- #
class Book:
    """最小独立账本：现金三分离 + 逐 clip T+1 可卖量 + FIFO 消耗。

    只实现 matcher 判定成交所必需的部分；权益曲线/年度口径由 C2 参考账本
    负责，不在本模块重做。
    """

    def __init__(self, cash: Decimal, *, is_t0: Iterable[str] | None = None,
                 etf: Iterable[str] | None = None,
                 round_per_movement: bool = True) -> None:
        self.cash = Decimal(cash)
        self.pend_am_to_pm = Decimal("0.00")
        self.pend_next_day = Decimal("0.00")
        self.clips: dict[str, list[Clip]] = {}
        self.is_t0 = set(is_t0 or ())
        self.etf = set(etf or ())
        self.fees = FeeSchedule(round_per_movement=round_per_movement)
        self._seq = 0

    # -- 半日结算 ---------------------------------------------------------- #
    def open_am(self) -> None:
        """前一 pm 卖出款在当日 am 转可用。"""
        self.cash += self.pend_next_day
        self.pend_next_day = Decimal("0.00")

    def open_pm(self) -> None:
        """当日 am 卖出款在当日 pm 转可用。"""
        self.cash += self.pend_am_to_pm
        self.pend_am_to_pm = Decimal("0.00")

    # -- 持仓 -------------------------------------------------------------- #
    def total_shares(self, symbol: str) -> int:
        return sum(c.shares for c in self.clips.get(symbol, []))

    def sellable(self, symbol: str, day: date,
                 session: str) -> tuple[int, list[Clip]]:
        """FIFO 序的可卖批次：取得日早于今日；T+0 品种可在更晚 session 卖；
        公司行动零股当日可一次性卖出。"""
        t0 = symbol in self.is_t0
        out: list[Clip] = []
        for c in self.clips.get(symbol, []):
            if c.acquired < day:
                out.append(c)
            elif c.shares % LOT != 0:
                out.append(c)
            elif t0 and c.session != session:
                out.append(c)
        return sum(c.shares for c in out), out

    # -- 公司行动（m4：整手送转新增份额取得日记为当日、次日可卖） ---------- #
    def apply_split(self, symbol: str, day: date, ratio: Decimal) -> None:
        """除权日逐 clip 变换股数（half-up 到整股）。新增份额记为当日取得。"""
        cs = self.clips.get(symbol)
        if not cs:
            return
        new: list[Clip] = []
        for c in cs:
            total = int((Decimal(c.shares) * Decimal(ratio)).to_integral_value(
                rounding="ROUND_HALF_UP"))
            keep = min(c.shares, total)
            extra = total - keep
            if keep > 0:
                new.append(replace(c, shares=keep))
            if extra > 0:
                self._seq += 1
                new.append(Clip(shares=extra, acquired=day, session="am",
                                price=c.price, seq=self._seq))
        self.clips[symbol] = new

    # -- 记账 -------------------------------------------------------------- #
    def book_buy(self, symbol: str, day: date, session: str,
                 shares: int, price: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        notional = price * shares
        commission, stamp, total = self.fees.total(day, notional, side=BUY)
        self.cash -= (notional + total)
        self._seq += 1
        self.clips.setdefault(symbol, []).append(
            Clip(shares=int(shares), acquired=day, session=session, price=price,
                 seq=self._seq))
        return commission, stamp, total

    def book_sell(self, symbol: str, day: date, session: str, shares: int,
                  price: Decimal, consume: Sequence[tuple[Clip, int]]
                  ) -> tuple[Decimal, Decimal, Decimal]:
        notional = price * shares
        commission, stamp, total = self.fees.total(
            day, notional, side=SELL, is_etf=symbol in self.etf)
        net = notional - total
        if session == "am":
            self.pend_am_to_pm += net
        else:
            self.pend_next_day += net
        # 按批次身份（seq）精确消耗，不用值相等定位（同值批次会改错对象）。
        take_by_seq = {c.seq: t for c, t in consume}
        rebuilt: list[Clip] = []
        for c in self.clips.get(symbol, []):
            take = take_by_seq.get(c.seq, 0)
            if take <= 0:
                rebuilt.append(c)
            elif take < c.shares:
                rebuilt.append(replace(c, shares=c.shares - take))
        self.clips[symbol] = rebuilt
        return commission, stamp, total

    def consume_plan(self, symbol: str, day: date, session: str,
                     shares: int) -> list[tuple[Clip, int]]:
        _n, sell_list = self.sellable(symbol, day, session)
        out: list[tuple[Clip, int]] = []
        remaining = shares
        for c in sell_list:
            if remaining <= 0:
                break
            take = min(c.shares, remaining)
            out.append((c, take))
            remaining -= take
        return out


# --------------------------------------------------------------------------- #
# 独立 matcher
# --------------------------------------------------------------------------- #
@dataclass
class _RiskState:
    source: str
    last_refresh_key: int = -1
    streak: int = 0
    armed: bool = False
    shares: int | None = None
    priority: int = 0


#: 计入风险 K 计数的“成交机会”原因白名单（m1：停牌冻结；缺涨跌停数据计入；
#: T+1 锁定计入；限价越界计入）。不在此表内的原因不改变计数。
_RISK_COUNTED_REASONS = frozenset({
    "never_crossed", "limit_illegal", "limit_missing", "t1_locked",
})


class ReferenceMatcher:
    """独立撮合：开环单张判定 + 闭环半日状态循环。"""

    def __init__(self, bars: BarTable, limits: LimitTable,
                 *, book: Book | None = None,
                 prev_close: Callable[[str, date], float | None] | None = None
                 ) -> None:
        self.bars = bars
        self.limits = limits
        self.book = book
        #: 决策点权益快照里既有持仓的 mark（合同=严格前一交易日官方收盘）。
        #: 只有闭环的上限判定需要；开环不传。
        self.prev_close = prev_close
        self.verdicts: list[Verdict] = []
        self.risk_state: dict[tuple[str, str], _RiskState] = {}
        self.k3_armed_events = 0
        self.k3_executed = 0
        self.k3_deferred = {"suspended": 0, "limitdown": 0, "t1locked": 0}
        self.voids: dict[str, int] = {}
        #: 同一 intent 的累计已成交股数（TV-B14：重挂只处理剩余）。
        self.intent_filled: dict[str, int] = {}
        self.replacements: dict[str, str] = {}

    # -- 单一半日价格判定（开环核心） -------------------------------------- #
    def judge_session(self, order: Order, state: JudgeState | None = None,
                      **kwargs: object) -> Verdict:
        """判定订单在它 ``live_date/live_session`` 的结果（不改账本）。

        ``state`` 为账本状态；卖单**必须**提供 ``sellable_shares``（由调用方从
        独立证据导出）。缺失状态时 fail-closed，不臆造数量。
        兼容旧调用：``available_cash``/``sellable_shares``/``position_shares``/
        ``projected_mv``/``snapshot_equity`` 关键字参数同样接受。
        """
        st = state or JudgeState(
            available_cash=kwargs.get("available_cash"),      # type: ignore[arg-type]
            sellable_shares=kwargs.get("sellable_shares"),    # type: ignore[arg-type]
            position_shares=kwargs.get("position_shares"),    # type: ignore[arg-type]
            projected_mv=kwargs.get("projected_mv"),          # type: ignore[arg-type]
            snapshot_equity=kwargs.get("snapshot_equity"),    # type: ignore[arg-type]
        )
        day, sess = order.live_date, order.live_session
        base = dict(order_id=order.order_id, symbol=order.symbol,
                    side=order.side, intent=order.intent,
                    live_date=day, live_session=sess,
                    requested_shares=order.shares)
        # 到期守卫（TV-B13：过期订单即使被延迟 wrapper 放行也不得复活）
        if order.expires_at is not None and day > order.expires_at:
            return Verdict(filled=False, reason="expired", bar_seen=False,
                           note=f"live_date {day} is past expires_at "
                                f"{order.expires_at}; order must not revive",
                           **base)
        bar = self.bars.get(order.symbol, day, sess)
        if bar is None:
            return Verdict(filled=False, reason="suspended", bar_seen=False,
                           note="no half-day bar this session (suspension / "
                                "missing half-day row)", **base)
        if order.side == SELL:
            if st.position_shares is not None and st.position_shares == 0:
                return Verdict(filled=False, reason="no_position", bar_seen=True,
                               note="nothing held; order void", **base)
            if st.sellable_shares is None:
                raise ValueError(
                    f"{order.order_id}: a sell verdict needs the position state; "
                    "the caller must pass sellable_shares/position_shares from an "
                    "independent source (fabricating a quantity would be a silent "
                    "false result)")
            if st.sellable_shares <= 0:
                return Verdict(filled=False, reason="t1_locked", bar_seen=True,
                               note="all shares acquired today (T+1)", **base)
        elif order.shares is None and order.target_notional is None:
            return Verdict(filled=False, reason="at_target", bar_seen=True,
                           note="no solved shares/target_notional (only "
                                "target_weight) -> not a valid matcher input",
                           **base)
        # ---- 价格合法性 ----
        lim = self.limits.get(order.symbol, day)
        if lim is None:
            return Verdict(filled=False, reason="limit_missing", bar_seen=True,
                           limit_seen=False, limit_legality="missing",
                           note="no price-limit row for this (symbol, day); "
                                "conservative reject (data gap)", **base)
        up, down = lim
        legality = price_legal(order.limit_price, up, down)
        if legality != "ok":
            return Verdict(filled=False,
                           reason=("limit_missing" if legality == "missing"
                                   else "limit_illegal"),
                           bar_seen=True, limit_seen=True,
                           limit_legality=legality,
                           note=f"day limits [down={down}, up={up}]", **base)
        assert order.limit_price is not None
        price = Decimal(str(order.limit_price))
        # ---- 严格穿透 ----
        if order.side == BUY:
            if not Decimal(str(bar.low)) < price:
                return Verdict(filled=False, reason="never_crossed",
                               bar_seen=True, limit_seen=True,
                               limit_legality="ok",
                               note="strict penetration required: session "
                                    "low < p (touch does not fill)", **base)
        else:
            if not Decimal(str(bar.high)) > price:
                return Verdict(filled=False, reason="never_crossed",
                               bar_seen=True, limit_seen=True,
                               limit_legality="ok",
                               note="strict penetration required: session "
                                    "high > q (touch does not fill)", **base)
        # ---- 数量与资金 ----
        if order.side == BUY:
            want = order.shares
            if want is None:
                tn = Decimal(str(order.target_notional))
                want = int((tn / price).to_integral_value(rounding="ROUND_FLOOR"))
                want = want // LOT * LOT
                if want < LOT:
                    return Verdict(filled=False, reason="below_lot",
                                   bar_seen=True, limit_seen=True,
                                   limit_legality="ok",
                                   note="target notional affords < 1 lot",
                                   **base)
            gross = price * want
            commission, stamp, fees = self._buy_fees(gross)
            if st.available_cash is not None and gross + fees > st.available_cash + _FLOAT_TOL:
                return Verdict(filled=False, reason="cash_short",
                               bar_seen=True, limit_seen=True,
                               limit_legality="ok",
                               note=f"need {gross + fees} > available "
                                    f"{st.available_cash}", **base)
            if (st.projected_mv is not None and st.snapshot_equity is not None
                    and st.projected_mv + gross
                    > CAP_SINGLE_NAME * st.snapshot_equity + _FLOAT_TOL):
                return Verdict(filled=False, reason="cancelled_cap",
                               bar_seen=True, limit_seen=True,
                               limit_legality="ok",
                               note="single-name 25% cap of the decision-point "
                                    "equity snapshot; whole order void", **base)
            return Verdict(filled=True, reason="filled", fill_type="limit",
                           fill_date=day, fill_session=sess, shares=want,
                           remaining_shares=0, price=price, gross_notional=gross,
                           commission=commission, stamp_tax=stamp,
                           fees_total=fees, net_cash_flow=-(gross + fees),
                           bar_seen=True, limit_seen=True, limit_legality="ok",
                           note="strict penetration: session low < p; fill at p",
                           **base)
        # 卖单
        qty = st.sellable_shares if order.shares is None \
            else min(order.shares, st.sellable_shares)
        if qty <= 0:
            return Verdict(filled=False, reason="no_position", bar_seen=True,
                           limit_seen=True, limit_legality="ok", **base)
        gross = price * qty
        commission, stamp, fees = self._sell_fees(day, gross, order.symbol)
        want = order.shares if order.shares is not None else qty
        remaining = max(0, want - qty)
        partial = remaining > 0
        return Verdict(filled=True,
                       reason="partial_fill" if partial else "filled",
                       fill_type="limit", fill_date=day, fill_session=sess,
                       shares=qty, remaining_shares=remaining, price=price,
                       gross_notional=gross, commission=commission,
                       stamp_tax=stamp, fees_total=fees,
                       net_cash_flow=gross - fees, bar_seen=True,
                       limit_seen=True, limit_legality="ok",
                       note="strict penetration: session high > q; fill at q"
                            + (f"; partial: {remaining} share(s) remain"
                               if partial else ""),
                       **base)

    # -- 费率（复用 C2 独立参考账本的费率表；未调用主引擎 FeeModel） -------- #
    def _schedule(self) -> FeeSchedule:
        return self.book.fees if self.book is not None else FeeSchedule()

    def _buy_fees(self, gross: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        commission = self._schedule().commission(gross)
        stamp = Decimal("0.00")                 # 股票买入无印花
        return commission, stamp, cent(commission + stamp)

    def _sell_fees(self, day: date, gross: Decimal,
                   symbol: str = "") -> tuple[Decimal, Decimal, Decimal]:
        schedule = self._schedule()
        is_etf = ((self.book is not None and symbol in self.book.etf)
                  or (symbol in getattr(self, "_etf_symbols", ())))
        commission = schedule.commission(gross)
        stamp = schedule.stamp_sell(day, gross, is_etf=is_etf)
        return commission, stamp, cent(commission + stamp)

    #: 调用方可注入的 ETF 名录（开环模式下没有 Book 时也要免印花）。
    _etf_symbols: frozenset[str] = frozenset()

    def set_etf_symbols(self, symbols: Iterable[str]) -> None:
        self._etf_symbols = frozenset(symbols)

    # -- 开环批量 ---------------------------------------------------------- #
    def judge_open(self, orders: Sequence[Order],
                   states: Mapping[str, JudgeState]
                   | Callable[[Order], JudgeState] | None = None
                   ) -> list[Verdict]:
        """开环：对固定订单逐张独立判定（无账本、无跨订单竞争）。

        ``states`` 给订单提供账本状态（卖单必需）。映射按 ``order_id`` 取值；
        可调用对象按订单求值。缺状态时卖单 fail-closed 报错。
        """
        out: list[Verdict] = []
        for o in orders:
            if callable(states):
                st = states(o)
            elif states is not None:
                st = states.get(o.order_id)
            else:
                st = None
            v = self.judge_session(o, st)
            out.append(v)
            self._record(v)
        return out

    #: 旧名保留（C3 交付前的调用方可能仍在用）；行为与 judge_open 相同但要求
    #: 显式状态，不再对卖单抛裸 ValueError。
    def match_open(self, orders: Sequence[Order],
                   states: Mapping[str, JudgeState]
                   | Callable[[Order], JudgeState] | None = None
                   ) -> list[Verdict]:
        return self.judge_open(orders, states)

    # -- 闭环：半日状态循环 ------------------------------------------------- #
    def run(self, orders: Sequence[Order],
            calendar: Sequence[tuple[date, str]] | None = None) -> list[Verdict]:
        """闭环：按半日顺序撮合一组订单，维护账本、T+1 与 K=3 兜底。

        ``calendar`` 为 (day, session) 升序序列。缺省取 bar 表内的半日对并集，
        但调用方应显式传入以避免停牌日缺席导致的次序错位；显式日历是唯一
        可审计的做法（``allow_inferred_calendar=True`` 才允许推断）。
        """
        if self.book is None:
            raise ValueError("closed-loop run requires a Book")
        if calendar is None:
            raise ValueError(
                "run() requires an explicit (day, session) calendar; inferring it "
                "from the bar table would silently drop fully suspended sessions "
                "(conservative rules would then be untestable)")
        cal_key = {k: i for i, k in enumerate(calendar)}
        # 替代关系（TV-B13）：同一 intent 在**同一个生效半日**出现多张单即
        # 「同半日改单」（合同 same_session_amendment=false）——只保留决策点最新
        # 的一张，其余登记为 replaced。跨半日的顺序重挂是合法生命周期（TV-B14），
        # 不在此列；过期重放的守卫由 expires_at 承担。
        slots: dict[tuple[str, date, str], list[Order]] = {}
        for o in orders:
            key = o.intent_id or o.order_id
            slots.setdefault((key, o.live_date, o.live_session), []).append(o)
        replaced: set[str] = set()
        for group in slots.values():
            if len(group) < 2:
                continue
            winner = max(group, key=lambda o: (o.decision_date, o.decision_session))
            for o in group:
                if o.order_id != winner.order_id:
                    replaced.add(o.order_id)
        by_live: dict[tuple[date, str], list[Order]] = {}
        for o in orders:
            by_live.setdefault((o.live_date, o.live_session), []).append(o)
        processed: set[str] = set()
        for day, sess in calendar:
            self._advance(day, sess)
            live = by_live.get((day, sess), [])
            buys = sorted([o for o in live if o.side == BUY],
                          key=lambda o: (o.priority, o.symbol))
            sells = [o for o in live if o.side == SELL]
            # A. 买单：按优先级占用现金，成交统一在卖单之后入账
            booked: list[tuple[Order, Verdict]] = []
            reserved = Decimal("0.00")
            for o in buys:
                if o.order_id in replaced:
                    self._record(Verdict(
                        order_id=o.order_id, symbol=o.symbol, side=o.side,
                        intent=o.intent, live_date=o.live_date,
                        live_session=o.live_session, filled=False,
                        reason="replaced", requested_shares=o.shares,
                        note="superseded by a later order of the same intent"))
                    processed.add(o.order_id)
                    continue
                want = self._intent_remaining(o)
                if want is not None and want <= 0:
                    self._record(Verdict(
                        order_id=o.order_id, symbol=o.symbol, side=o.side,
                        intent=o.intent, live_date=o.live_date,
                        live_session=o.live_session, filled=False,
                        reason="at_target", requested_shares=o.shares,
                        note="this intent's remaining shares are already filled; "
                             "a re-issue must not buy the full size again"))
                    processed.add(o.order_id)
                    continue
                v = self._judge_with_book(o, reserved, want=want)
                if v.filled:
                    reserved += (v.gross_notional or Decimal("0")) + \
                        (v.fees_total or Decimal("0"))
                    booked.append((o, v))
                self._record(v)
                processed.add(o.order_id)
                if v.filled:
                    self._note_intent_fill(o, v)
            # B. 已武装的 K=3 兜底（在卖单限价单之前执行）
            consumed: set[tuple[str, str]] = set()
            for key in sorted(self.risk_state):
                st = self.risk_state[key]
                if not st.armed:
                    continue
                v = self._try_fallback(key[0], key[1], st, day, sess)
                if v is not None:
                    self._record(v)
                    if v.filled:
                        consumed.add(key)   # 本 session 的限价单不再重复判定
            # C. 卖单限价单
            for o in sells:
                if o.order_id in replaced:
                    self._record(Verdict(
                        order_id=o.order_id, symbol=o.symbol, side=o.side,
                        intent=o.intent, live_date=o.live_date,
                        live_session=o.live_session, filled=False,
                        reason="replaced", requested_shares=o.shares,
                        note="superseded by a later order of the same intent"))
                    processed.add(o.order_id)
                    continue
                if o.intent == INTENT_RISK and (o.symbol, o.source) in consumed:
                    continue
                self._refresh_risk(o, day, sess, cal_key)
                want_s = self._intent_remaining(o)
                if want_s is not None and want_s <= 0:
                    self._record(Verdict(
                        order_id=o.order_id, symbol=o.symbol, side=o.side,
                        intent=o.intent, live_date=o.live_date,
                        live_session=o.live_session, filled=False,
                        reason="at_target", requested_shares=o.shares,
                        note="this intent's remaining shares are already filled"))
                    processed.add(o.order_id)
                    continue
                v = self._judge_with_book(o, Decimal("0.00"), want=want_s)
                self._record(v)
                processed.add(o.order_id)
                if v.filled:
                    self._book_sell(o, v)
                    if v.remaining_shares == 0:
                        self.risk_state.pop((o.symbol, o.source), None)
                    self._note_intent_fill(o, v)
                else:
                    self._after_unfilled_sell(o, v)
            # D. 买单入账
            for o, v in booked:
                assert self.book is not None
                self.book.book_buy(o.symbol, day, sess, int(v.shares or 0),
                                   v.price)  # type: ignore[arg-type]
        # 不在日历内的订单不得静默丢弃：逐张登记为过期（无成交机会）。
        for o in orders:
            if o.order_id in processed:
                continue
            self._record(Verdict(
                order_id=o.order_id, symbol=o.symbol, side=o.side,
                intent=o.intent, live_date=o.live_date,
                live_session=o.live_session, filled=False, reason="expired",
                requested_shares=o.shares,
                note="live slot is not in the supplied calendar; no fill "
                     "opportunity (order must be re-issued at a decision point)"))
        return self.verdicts

    # -- K=3 兜底的只读判定（供开环核对真实 run 的 market_exit_* 事件） ------ #
    def judge_fallback(self, symbol: str, day: date, session: str,
                       shares: int | None = None) -> Verdict:
        """对“已武装的 K=3 兜底在本 session 的尝试”做只读判定（不改账本/状态）。

        与 ``_try_fallback`` 同语义：无 bar→停牌冻结顺延；无可卖→T+1 顺延或
        清状态；开盘跌停（``open <= down*(1+tol)``）→顺延；否则按 **session 开盘价**
        市价成交。
        """
        base = dict(order_id=f"{symbol}-sell/risk-K3FB-{day.isoformat()}-{session}",
                    symbol=symbol, side=SELL, intent=INTENT_RISK,
                    live_date=day, live_session=session,
                    requested_shares=shares)
        bar = self.bars.get(symbol, day, session)
        if bar is None:
            return Verdict(filled=False, reason="suspended", bar_seen=False,
                           note="K=3 fallback: no bar; stays armed", **base)
        if self.book is None:
            raise ValueError("judge_fallback needs a Book for the position state")
        pos = self.book.total_shares(symbol)
        sell_sh, _lst = self.book.sellable(symbol, day, session)
        if sell_sh <= 0:
            if pos > 0:
                return Verdict(filled=False, reason="t1_locked", bar_seen=True,
                               note="K=3 fallback: all shares acquired today "
                                    "(T+1); stays armed", **base)
            return Verdict(filled=False, reason="no_position", bar_seen=True,
                           note="K=3 fallback: nothing held; state cleared",
                           **base)
        lim = self.limits.get(symbol, day)
        down = None if lim is None else lim[1]
        open_px = Decimal(str(bar.open))
        if down is not None and open_px <= Decimal(str(down)) * (1 + LIMIT_DOWN_TOL):
            return Verdict(filled=False, reason="limit_illegal", bar_seen=True,
                           limit_seen=True, limit_legality="ok",
                           note="K=3 fallback: open at limit-down; deferred",
                           **base)
        qty = sell_sh if shares is None else min(shares, sell_sh)
        gross = open_px * qty
        commission, stamp, fees = self._sell_fees(day, gross, symbol)
        return Verdict(filled=True, reason="filled", fill_type="market_fallback",
                       fill_date=day, fill_session=session, shares=qty,
                       remaining_shares=0, price=open_px, gross_notional=gross,
                       commission=commission, stamp_tax=stamp, fees_total=fees,
                       net_cash_flow=gross - fees, bar_seen=True, limit_seen=True,
                       limit_legality="ok",
                       note="K=3 market fallback at session open", **base)

    # -- 内部 -------------------------------------------------------------- #
    def _record(self, v: Verdict) -> None:
        self.verdicts.append(v)
        if not v.filled:
            self.voids[v.reason] = self.voids.get(v.reason, 0) + 1

    def _intent_remaining(self, order: Order) -> int | None:
        """TV-B14：同一 intent 重挂时只请求尚未成交的剩余股数。"""
        if order.intent_requested_shares is None:
            return order.shares
        filled = self.intent_filled.get(order.intent_id or order.order_id, 0)
        left = order.intent_requested_shares - filled
        if left <= 0:
            return 0
        if order.shares is None:
            return left
        return min(order.shares, left)

    def _note_intent_fill(self, order: Order, v: Verdict) -> None:
        if order.intent_requested_shares is None:
            return
        key = order.intent_id or order.order_id
        self.intent_filled[key] = self.intent_filled.get(key, 0) + int(v.shares or 0)

    def _advance(self, day: date, sess: str) -> None:
        assert self.book is not None
        if sess == "am":
            self.book.open_am()
        else:
            self.book.open_pm()

    def _judge_with_book(self, order: Order, reserved: Decimal,
                         want: int | None = None) -> Verdict:
        book = self.book
        assert book is not None
        if want is not None:
            order = replace(order, shares=want)
        if order.side == SELL:
            pos = book.total_shares(order.symbol)
            sell_sh, _lst = book.sellable(order.symbol, order.live_date,
                                          order.live_session)
            return self.judge_session(order, sellable_shares=sell_sh,
                                      position_shares=pos)
        held = book.total_shares(order.symbol)
        proj_mv = None
        if held and self.prev_close is not None:
            px = self.prev_close(order.symbol, order.live_date)
            if px is not None:
                proj_mv = Decimal(str(px)) * held
        return self.judge_session(
            order,
            available_cash=book.cash - reserved,
            projected_mv=proj_mv,
            snapshot_equity=(None if order.snapshot_equity is None
                             else Decimal(str(order.snapshot_equity))))

    def _refresh_risk(self, order: Order, day: date, sess: str,
                      cal_key: Mapping[tuple[date, str], int]) -> None:
        """风险站立单的 K 计数刷新（M1）：同源机械重锚保持 streak，
        一次不重发即撤销并重置。"""
        if order.intent != INTENT_RISK:
            return
        key = (order.symbol, order.source)
        k = cal_key.get((day, sess))
        st = self.risk_state.get(key)
        if st is None:
            self.risk_state[key] = _RiskState(
                source=order.source, last_refresh_key=-1 if k is None else k,
                shares=order.shares, priority=order.priority)
            return
        if not (k is not None and st.last_refresh_key == k - 1):
            st.streak = 0
            st.armed = False
        st.last_refresh_key = -1 if k is None else k
        st.shares = order.shares
        st.priority = order.priority

    def _after_unfilled_sell(self, order: Order, v: Verdict) -> None:
        if order.intent != INTENT_RISK:
            return
        key = (order.symbol, order.source)
        st = self.risk_state.get(key)
        if st is None:
            return
        if v.reason == "suspended":
            return                      # m3：停牌 session 计数冻结
        if v.reason == "no_position":
            self.risk_state.pop(key, None)
            return
        if v.reason not in _RISK_COUNTED_REASONS:
            return                      # 不相关的拒绝原因不改变 K 计数
        st.streak += 1
        if st.streak >= K_FALLBACK_SESSIONS and not st.armed:
            st.armed = True
            self.k3_armed_events += 1

    def _try_fallback(self, sym: str, src: str, st: _RiskState, day: date,
                      sess: str) -> Verdict | None:
        assert self.book is not None
        base = dict(order_id=f"{sym}-sell/risk-K3FB-{day.isoformat()}-{sess}",
                    symbol=sym, side=SELL, intent=INTENT_RISK,
                    live_date=day, live_session=sess)
        bar = self.bars.get(sym, day, sess)
        if bar is None:
            self.k3_deferred["suspended"] += 1
            return Verdict(filled=False, reason="suspended", bar_seen=False,
                           note="K=3 fallback: no bar; stays armed", **base)
        pos = self.book.total_shares(sym)
        sell_sh, _lst = self.book.sellable(sym, day, sess)
        if sell_sh <= 0:
            if pos > 0:
                self.k3_deferred["t1locked"] += 1
                return Verdict(filled=False, reason="t1_locked", bar_seen=True,
                               note="K=3 fallback: all shares acquired today "
                                    "(T+1); stays armed", **base)
            self.risk_state.pop((sym, src), None)
            return Verdict(filled=False, reason="no_position", bar_seen=True,
                           note="K=3 fallback: nothing held; state cleared",
                           **base)
        lim = self.limits.get(sym, day)
        down = None if lim is None else lim[1]
        open_px = Decimal(str(bar.open))
        if down is not None and open_px <= Decimal(str(down)) * (1 + LIMIT_DOWN_TOL):
            self.k3_deferred["limitdown"] += 1
            return Verdict(filled=False, reason="limit_illegal", bar_seen=True,
                           limit_seen=True, limit_legality="ok",
                           note="K=3 fallback: open at limit-down; deferred",
                           **base)
        qty = sell_sh if st.shares is None else min(st.shares, sell_sh)
        gross = open_px * qty
        commission, stamp, fees = self._sell_fees(day, gross, sym)
        self.k3_executed += 1
        self.risk_state.pop((sym, src), None)
        v = Verdict(filled=True, reason="filled", fill_type="market_fallback",
                    fill_date=day, fill_session=sess, shares=qty,
                    remaining_shares=0, price=open_px, gross_notional=gross,
                    commission=commission, stamp_tax=stamp, fees_total=fees,
                    net_cash_flow=gross - fees, bar_seen=True, limit_seen=True,
                    limit_legality="ok",
                    note="K=3 market fallback at session open", **base)
        consume = self.book.consume_plan(sym, day, sess, qty)
        self.book.book_sell(sym, day, sess, qty, open_px, consume)
        return v

    def _book_sell(self, order: Order, v: Verdict) -> None:
        assert self.book is not None
        assert v.shares is not None and v.price is not None
        consume = self.book.consume_plan(order.symbol, order.live_date,
                                         order.live_session, int(v.shares))
        self.book.book_sell(order.symbol, order.live_date, order.live_session,
                            int(v.shares), v.price, consume)
