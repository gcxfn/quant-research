"""C2 独立参考账本（独立于主引擎的第二套资金/持仓核算实现）。

设计目标（主计划第 7 节 C2）：给定**同一批成交、公司行动与官方估值价格**，
用与主引擎完全独立的代码算出现金（可用/待结算分离）、持股、可卖股数与权益，
并对每一步做可证伪的校验。

独立性约束
----------
本模块**只用标准库**（``decimal`` / ``datetime`` / ``dataclasses``），
**不得** import ``quant.backtest`` 或 ``quant.portfolio``，也不调用主引擎的
费用、公司行动、现金结算、FIFO、估值或收益函数。它与主引擎只共享：

* 数据格式（成交/公司行动的字段含义），
* 冻结合同文字（费用公式、结算时序、T+1、公司行动口径、估值口径）。

合同来源（实现逐项引用，不复制代码）
------------------------------------
* 事件排序：半日开始前公司行动（份额变换在 pm 开市前、成交判定与估值之前）→
  结算 → 许可成交 → 半日估值（官方日线 close 为 mark）；来源
  ``docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/contract_snapshot.json``
  的 ``valuation`` / ``corporate_action_policy`` / ``settlement_delay`` 字段。
* 现金三分离：``free_settled`` / ``am_to_pm`` / ``unsettled_sale_proceeds``；
  权益 = 现金合计 + 持仓市值，任何字段不重复相加；来源 C0 ``valuation.daily_equity``
  与 C1 ``interface_contract.json`` 的 ``ledger_snapshots.identity``。
* 费用：买 = ``max(名义×0.0001, 5.00)``；卖 = 佣金同式 + 印花税
  （2023-08-28 前 0.001、当日及以后 0.0005，仅卖出，ETF 免）；来源 C1
  ``fee_schema``。
* 舍入：每笔现金变动处 ``Decimal`` ROUND_HALF_UP 到 0.01 元、零容差；来源
  C1 ``fee_schema.rounding_rule``（审阅者默认裁定，待用户追认）。
* 结算时序：am 成交的卖出款当日 pm 起可用；pm 成交的卖出款次一交易日 am 起可用；
  同一 session 内先卖后买不可观测、禁用；来源 C0 ``settlement_delay`` 与
  ``docs/plans/p3-band-contract.md`` §7.2。
* T+1：股票当日买入份额当日不可卖（逐 clip 按取得半日）；来源 C0
  ``t_plus_and_round_lot``。
* 公司行动：送转 = ``split_factor`` 真实比例逐 clip half-up 变换；现金分红 =
  每手税前金额 ÷ ``round_lot`` × 除息日前持股，除息日计已结算现金；禁止把含分红
  复权因子当输入；来源 C0 ``corporate_action_policy`` 与 p3 §1.3。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
LOT = 100
STAMP_BOUNDARY = date(2023, 8, 28)
COMMISSION_RATE = Decimal("0.0001")
COMMISSION_FLOOR = Decimal("5.00")
STAMP_BEFORE = Decimal("0.001")
STAMP_ON_AFTER = Decimal("0.0005")


def cent(value: Decimal) -> Decimal:
    """按合同统一到分（ROUND_HALF_UP）；仅用于**比较**，不受舍入位置开关影响。"""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- #
# 错误类型：每一项对应一个可注入的缺陷类，注入后必须报错
# --------------------------------------------------------------------------- #
class LedgerError(RuntimeError):
    """参考账本校验失败的基类。"""


class DuplicateFillError(LedgerError):
    """同一 fill_id 出现两次（重复成交注入）。"""


class NotionalConsistencyError(LedgerError):
    """名义金额与 价格×股数 不一致（价格单位/数量单位注入）。"""


class PriceLegalityError(LedgerError):
    """成交价不在当日涨跌停区间内或不在价格 tick 上（价格×100 注入）。"""


class DividendUnitError(LedgerError):
    """分红每手金额被当成每股金额（每手/每股口径注入）。"""


class CashSignError(LedgerError):
    """买入/卖出的现金流方向与 side 不符（成本符号反转注入）。"""


class SettlementTimingError(LedgerError):
    """用了同一 session 内尚未可用的卖出款（卖出款提前可用注入）。"""


class CashShortfallError(LedgerError):
    """买入所需资金超过可用现金。"""


class CashNegativeError(LedgerError):
    """任意时点现金为负。"""


class ClipOverConsumptionError(LedgerError):
    """卖出消耗超过该批次（clip）剩余股数。"""


class StaleClipError(LedgerError):
    """卖出引用了已清空的历史批次（旧批次状态残留注入）。"""


class TPlusViolationError(LedgerError):
    """当日买入份额当日卖出（T+1 违规）。"""


class TemporalLeakError(LedgerError):
    """决策锚使用了当时不可得的未来价（未来价替代上午价注入）。"""


class CoverageError(LedgerError):
    """年度收益覆盖不完整（首年收益遗漏注入）。"""


class SignConventionError(LedgerError):
    """回撤幅度用了负号参与比较（负号 MDD 误比较注入）。"""


class EquityIdentityError(LedgerError):
    """权益恒等式被破坏。"""


# --------------------------------------------------------------------------- #
# 费用（独立实现）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FeeSchedule:
    """冻结费率。默认沿项目合同；测试可上调用于固定路径单调性检查。"""

    commission_rate: Decimal = COMMISSION_RATE
    commission_floor: Decimal = COMMISSION_FLOOR
    stamp_sell_before: Decimal = STAMP_BEFORE
    stamp_sell_on_after: Decimal = STAMP_ON_AFTER
    stamp_boundary: date = STAMP_BOUNDARY
    round_per_movement: bool = True

    def _q(self, value: Decimal) -> Decimal:
        if not self.round_per_movement:
            return value
        return value.quantize(CENT, rounding=ROUND_HALF_UP)

    def commission(self, notional: Decimal) -> Decimal:
        raw = notional * self.commission_rate
        return self._q(max(raw, self.commission_floor))

    def stamp_sell(self, day: date, notional: Decimal, *, is_etf: bool = False) -> Decimal:
        if is_etf:
            return ZERO
        rate = (self.stamp_sell_before if day < self.stamp_boundary
                else self.stamp_sell_on_after)
        return self._q(notional * rate)

    def total(self, day: date, notional: Decimal, *, side: str,
              is_etf: bool = False) -> tuple[Decimal, Decimal, Decimal]:
        """返回 (commission, stamp_tax, fees_total)。"""
        commission = self.commission(notional)
        stamp = self.stamp_sell(day, notional, is_etf=is_etf) if side == "sell" else ZERO
        return commission, stamp, self._q(commission + stamp)


# --------------------------------------------------------------------------- #
# 输入记录（与主引擎产物字段同义，但为独立数据类，不复用引擎类型）
# --------------------------------------------------------------------------- #
def _dec(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    return Decimal(str(value))


@dataclass(frozen=True)
class Fill:
    """一笔成交。``clip_id`` 仅买入有意义（该成交创建的新批次）。"""

    fill_id: str
    symbol: str
    side: str                       # "buy" | "sell"
    day: date
    session: str                    # "am" | "pm"
    shares: int
    price: Decimal
    notional: Decimal | None = None
    commission: Decimal | None = None   # 主引擎记录值（对账用，不用作输入）
    stamp_tax: Decimal | None = None
    net_cash_flow: Decimal | None = None  # 主引擎记录值（符号校验用）
    intent: str = ""
    fill_type: str = "limit"
    is_etf: bool = False
    clip_id: str | None = None
    decision_day: date | None = None
    decision_session: str | None = None
    anchor_day: date | None = None      # 决策锚所属交易日（时间泄漏校验用）
    down_limit: Decimal | None = None   # 当日跌停价（合法性校验）
    up_limit: Decimal | None = None     # 当日涨停价
    prev_close: Decimal | None = None   # 上一交易日官方收盘（调整后）

    def price_on_tick(self) -> bool:
        tick = Decimal("0.001") if self.is_etf else Decimal("0.01")
        return (self.price / tick) == (self.price / tick).to_integral_value()


@dataclass(frozen=True)
class SplitAction:
    """送转/份额变换：除息日按 ``ratio`` 逐 clip 变换股数。"""

    symbol: str
    ex_date: date
    ratio: Decimal


@dataclass(frozen=True)
class DividendAction:
    """现金分红。

    ``cash_per_lot`` 与 ``round_lot`` 是源数据的每手口径；``source_units``
    声明原始单位。参考实现在此**自行**换算为每股口径，并交叉校验调用方传入的
    ``per_share``（用于捕获"每手误当每股"）。
    """

    symbol: str
    ex_date: date
    per_share: Decimal
    cash_per_lot: Decimal | None = None
    round_lot: int | None = None
    source_units: str = "per_lot"
    prev_close: Decimal | None = None  # 除息前收盘，用于隐含收益率护栏


@dataclass
class DayInput:
    """一个交易日的全部输入。``fills`` 需按 am→pm、各自内部时间序排列。"""

    day: date
    splits: Sequence[SplitAction] = ()
    dividends: Sequence[DividendAction] = ()
    fills: Sequence[Fill] = ()
    marks: Mapping[str, Decimal] = field(default_factory=dict)


@dataclass
class Clip:
    """持仓批次（成本/可卖数量的最小单位）。"""

    clip_id: str
    symbol: str
    shares: int
    acquired: date
    price: Decimal = ZERO
    session: str = "am"
    closed: bool = False


@dataclass
class DailyRecord:
    day: date
    free_settled_cash: Decimal
    unsettled_sale_proceeds: Decimal
    am_to_pm_proceeds: Decimal
    cash_total: Decimal
    position_mv: Decimal
    equity: Decimal
    fee_cumulative: Decimal
    dividend_cumulative: Decimal
    n_positions: int
    stale_mark_symbols: tuple[str, ...]
    held_shares: dict[str, int]
    sellable_shares: dict[str, int]


# --------------------------------------------------------------------------- #
# 参考账本
# --------------------------------------------------------------------------- #
class ReferenceLedger:
    """逐日重放成交/公司行动/估值，独立核算现金与持仓。"""

    def __init__(
        self,
        initial_cash: Decimal | int | str = Decimal("500000.00"),
        *,
        fees: FeeSchedule | None = None,
        strict: bool = True,
        etf_t0: Iterable[str] = (),
        max_dividend_yield: Decimal = Decimal("0.25"),
    ) -> None:
        self.initial_cash = _dec(initial_cash).quantize(CENT, rounding=ROUND_HALF_UP)
        self.fees = fees or FeeSchedule()
        self.strict = strict
        self.etf_t0 = frozenset(etf_t0)
        self.max_dividend_yield = max_dividend_yield

        self.free_settled_cash = self.initial_cash
        self.am_to_pm_proceeds = ZERO
        self.unsettled_sale_proceeds = ZERO
        self.clips: dict[str, list[Clip]] = {}
        self.fee_cumulative = ZERO
        self.dividend_cumulative = ZERO
        self.days: list[DailyRecord] = []
        self._seen_fill_ids: set[str] = set()
        self._clip_registry: dict[str, Clip] = {}
        self.equity_series: list[Decimal] = []
        # 参考实现独立算出的费用与主引擎记录值的差异（不抛错、由驱动层汇总）
        self.fee_mismatches: list[dict] = []
        self._session_fills: list[Fill] = []
        # 送转变换后（当日成交之前）的股数：(symbol, day) -> shares
        self.split_results: dict[tuple[str, object], int] = {}

    # -- 校验工具 ------------------------------------------------------------ #
    def _fail(self, exc: type[LedgerError], message: str) -> None:
        if self.strict:
            raise exc(message)

    # -- 主循环 -------------------------------------------------------------- #
    def replay(self, days: Iterable[DayInput]) -> list[DailyRecord]:
        for day_input in days:
            self._replay_day(day_input)
        return self.days

    def _replay_day(self, din: DayInput) -> None:
        day = din.day

        # 1) 期初结算：前一交易日 pm 的卖出款到今日 am 可用
        self.free_settled_cash += self.unsettled_sale_proceeds
        self.unsettled_sale_proceeds = ZERO

        # 2) 公司行动：份额变换在前（除权日 pm 开市前），分红于除息日计已结算现金
        pre_ex_shares = {s: sum(c.shares for c in cs)
                         for s, cs in self.clips.items() if cs}
        for split in sorted(din.splits, key=lambda a: a.symbol):
            self._apply_split(split, day)
        for div in sorted(din.dividends, key=lambda a: a.symbol):
            self._apply_dividend(div, pre_ex_shares.get(div.symbol, 0))

        # 3) 许可成交：am 会话（买入可用现金 = session 开始时的已结算现金；
        #    同一 session 的卖出款尚未可用，与合同 settlement_delay 一致）
        am_fills = [f for f in din.fills if f.session == "am"]
        self._session_fills = am_fills
        am_avail = self.free_settled_cash
        for fill in self._ordered(am_fills):
            am_avail = self._book_fill(fill, day, am_avail)
        # am 卖出款自当日 pm 起可用
        self.free_settled_cash += self.am_to_pm_proceeds
        self.am_to_pm_proceeds = ZERO

        # 4) 许可成交：pm 会话
        pm_fills = [f for f in din.fills if f.session == "pm"]
        self._session_fills = pm_fills
        pm_avail = self.free_settled_cash
        for fill in self._ordered(pm_fills):
            pm_avail = self._book_fill(fill, day, pm_avail)
        self._session_fills = []

        # 5) 半日估值（官方日线 close 为 mark）
        mv = ZERO
        stale: list[str] = []
        held: dict[str, int] = {}
        sellable: dict[str, int] = {}
        for symbol in sorted(self.clips):
            cs = [c for c in self.clips[symbol] if c.shares > 0]
            if not cs:
                continue
            total = sum(c.shares for c in cs)
            held[symbol] = total
            sellable[symbol] = sum(c.shares for c in cs
                                  if self._sellable(c, day, "pm"))
            mark = din.marks.get(symbol)
            if mark is None:
                stale.append(symbol)          # 停牌/无 bar：与主引擎一致，不计市值
                continue
            mv += _dec(mark) * total

        cash_total = self.free_settled_cash + self.am_to_pm_proceeds \
            + self.unsettled_sale_proceeds
        equity = cash_total + mv
        # 现金三分离不得重复相加 + 权益恒等式
        if self.free_settled_cash < ZERO or self.unsettled_sale_proceeds < ZERO:
            self._fail(CashNegativeError,
                       f"{day}: negative cash bucket settled={self.free_settled_cash} "
                       f"unsettled={self.unsettled_sale_proceeds}")
        record = DailyRecord(
            day=day,
            free_settled_cash=self.free_settled_cash,
            unsettled_sale_proceeds=self.unsettled_sale_proceeds,
            am_to_pm_proceeds=self.am_to_pm_proceeds,
            cash_total=cash_total,
            position_mv=mv,
            equity=equity,
            fee_cumulative=self.fee_cumulative,
            dividend_cumulative=self.dividend_cumulative,
            n_positions=len(held),
            stale_mark_symbols=tuple(stale),
            held_shares=held,
            sellable_shares=sellable,
        )
        self.days.append(record)
        self.equity_series.append(equity)

    # -- 公司行动 ------------------------------------------------------------ #
    def _apply_split(self, split: SplitAction, day: date) -> None:
        cs = self.clips.get(split.symbol)
        if not cs:
            return
        ratio = split.ratio
        new_clips: list[Clip] = []
        added_seq = 0
        for c in cs:
            # half-up 取整（等价 floor(shares×ratio + 0.5)，与合同 per-clip 口径一致）
            new_total = int((Decimal(c.shares) * ratio).to_integral_value(
                rounding=ROUND_HALF_UP))
            keep = min(c.shares, new_total)
            extra = new_total - keep
            if keep > 0:
                new_clips.append(c)
                c.shares = keep
            if extra > 0:
                cid = f"{split.symbol}#split#{day.isoformat()}#{added_seq}"
                added_seq += 1
                new_clips.append(Clip(clip_id=cid, symbol=split.symbol,
                                      shares=extra, acquired=day, price=c.price,
                                      session="am"))
        self.clips[split.symbol] = new_clips
        self.split_results[(split.symbol, day)] = sum(c.shares for c in new_clips)

    def _apply_dividend(self, div: DividendAction, pre_ex_shares: int) -> None:
        if pre_ex_shares <= 0:
            return
        # 独立换算每手 -> 每股，并交叉校验调用方给出的每股值
        if div.cash_per_lot is not None and div.round_lot:
            if div.round_lot <= 0:
                self._fail(DividendUnitError,
                           f"{div.symbol} {div.ex_date}: round_lot <= 0")
            expected = _dec(div.cash_per_lot) / Decimal(div.round_lot)
            if expected != div.per_share:
                self._fail(
                    DividendUnitError,
                    f"{div.symbol} {div.ex_date}: per-share {div.per_share} != "
                    f"per-lot {div.cash_per_lot} / round_lot {div.round_lot} = "
                    f"{expected}; source_units={div.source_units!r}")
        # 隐含收益率护栏（防把每手值当每股：幅度异常）
        if div.prev_close and div.prev_close > 0:
            if div.per_share > self.max_dividend_yield * _dec(div.prev_close):
                self._fail(
                    DividendUnitError,
                    f"{div.symbol} {div.ex_date}: per-share dividend {div.per_share} "
                    f"implies yield > {self.max_dividend_yield} of prev_close "
                    f"{div.prev_close}")
        amount = self.fees._q(div.per_share * Decimal(pre_ex_shares))
        self.free_settled_cash += amount
        self.dividend_cumulative += amount

    # -- 成交 ---------------------------------------------------------------- #
    def _sellable(self, clip: Clip, day: date, session: str) -> bool:
        """可卖判定（合同：C0 ``t_plus_and_round_lot`` + p3 §7.3 零股例外）。

        * 股票 T+1：当日买入份额当日不可卖；
        * 公司行动产生的**零股**（当日新增且非整手）当日可卖、一次性卖出；
        * T+0 品种：当日买入、但取得 session 早于当前 session 的可卖。
        """
        if clip.acquired < day:
            return True
        if clip.shares % LOT != 0:
            return True                      # 当日新增零股（公司行动）
        if clip.symbol in self.etf_t0:
            return clip.session != session
        return False

    def _book_fill(self, fill: Fill, day: date, available: Decimal) -> Decimal:
        """记一笔成交；``available`` 为该 session 开始时可用于买入的已结算现金。

        卖出的卖出款进入待结算桶，**不**增加本 session 的可用现金。
        返回更新后的可用现金（供同一 session 后续买入继续扣减）。
        """
        # 时间泄漏：am 决策不得使用当日信息
        if fill.decision_session == "am" and fill.anchor_day is not None \
                and fill.anchor_day >= day:
            self._fail(TemporalLeakError,
                       f"{fill.fill_id}: am decision on {day} uses anchor_day "
                       f"{fill.anchor_day} (same or later day)")
        # 重复成交
        if fill.fill_id in self._seen_fill_ids:
            self._fail(DuplicateFillError, f"duplicate fill_id {fill.fill_id!r}")
        self._seen_fill_ids.add(fill.fill_id)

        self._validate_fill(fill, day)

        notional = _dec(fill.price) * Decimal(fill.shares)
        if fill.notional is not None and cent(_dec(fill.notional)) \
                != cent(notional):
            self._fail(NotionalConsistencyError,
                       f"{fill.fill_id}: recorded notional {fill.notional} != "
                       f"price*shares {notional}")

        commission, stamp, fees_total = self.fees.total(
            day, notional, side=fill.side, is_etf=fill.is_etf)
        self._check_recorded_fees(fill, commission, stamp)
        self.fee_cumulative += fees_total

        if fill.side == "buy":
            cost = self.fees._q(notional + fees_total)
            if cost > available + Decimal("0.000001"):
                same_session_sale = any(
                    f.session == fill.session and f.side == "sell"
                    for f in self._session_fills)
                if same_session_sale:
                    self._fail(
                        SettlementTimingError,
                        f"{fill.fill_id}: buy on {day} {fill.session} needs "
                        f"{cost} but only {available} settled is available; "
                        f"same-session sale proceeds are not usable yet")
                self._fail(CashShortfallError,
                           f"{fill.fill_id}: buy cost {cost} > settled cash "
                           f"{available} on {day} {fill.session}")
            self.free_settled_cash -= cost
            available -= cost
            self._open_clip(fill, day)
        elif fill.side == "sell":
            net = self.fees._q(notional - fees_total)
            if net <= 0:
                self._fail(CashSignError,
                           f"{fill.fill_id}: sell net proceeds {net} <= 0")
            self._consume_fifo(fill, day, fill.session)
            if fill.session == "am":
                self.am_to_pm_proceeds += net
            else:
                self.unsettled_sale_proceeds += net
        else:
            raise LedgerError(f"unknown side {fill.side!r}")
        return available

    def _ordered(self, fills: Sequence[Fill]) -> list[Fill]:
        """同一 session 内先记卖出再记买入（沿引擎 section D 在卖出后记账）。"""
        return [f for f in fills if f.side == "sell"] + \
               [f for f in fills if f.side == "buy"]

    def _check_recorded_fees(self, fill: Fill, commission: Decimal,
                             stamp: Decimal) -> None:
        """把参考实现独立算出的费用与主引擎记录值对比；不抛错，仅登记。"""
        rec_c = cent(_dec(fill.commission)) if fill.commission is not None else None
        rec_s = cent(_dec(fill.stamp_tax)) if fill.stamp_tax is not None else None
        ref_c = cent(commission)
        ref_s = cent(stamp)
        if (rec_c is not None and rec_c != ref_c) or \
                (rec_s is not None and rec_s != ref_s):
            self.fee_mismatches.append({
                "fill_id": fill.fill_id, "symbol": fill.symbol,
                "side": fill.side, "day": fill.day.isoformat(),
                "session": fill.session,
                "ref_commission": str(ref_c), "engine_commission": str(rec_c),
                "ref_stamp": str(ref_s), "engine_stamp": str(rec_s),
            })


    def _validate_fill(self, fill: Fill, day: date) -> None:
        if fill.shares <= 0:
            raise LedgerError(f"{fill.fill_id}: non-positive shares {fill.shares}")
        if fill.price <= 0:
            self._fail(NotionalConsistencyError,
                       f"{fill.fill_id}: non-positive price {fill.price}")
        if not fill.price_on_tick():
            self._fail(PriceLegalityError,
                       f"{fill.fill_id}: price {fill.price} is not on tick")
        if fill.down_limit is not None and fill.up_limit is not None:
            if not (fill.down_limit <= fill.price <= fill.up_limit):
                self._fail(
                    PriceLegalityError,
                    f"{fill.fill_id}: price {fill.price} outside day limits "
                    f"[{fill.down_limit}, {fill.up_limit}]")
        if fill.prev_close is not None and fill.prev_close > 0 and fill.is_etf is False:
            ratio = fill.price / fill.prev_close
            if ratio > Decimal("3") or ratio < Decimal("0.34"):
                self._fail(
                    PriceLegalityError,
                    f"{fill.fill_id}: price {fill.price} vs prev_close "
                    f"{fill.prev_close} ratio {ratio} implausible (unit error?)")
        if fill.side == "buy" and fill.shares % LOT != 0:
            # 整手：买入必须为 100 倍数（公司行动零股只在卖出侧）
            self._fail(NotionalConsistencyError,
                       f"{fill.fill_id}: buy shares {fill.shares} not a lot multiple")
        # 现金流符号必须与 side 一致（成本符号反转注入）
        if fill.net_cash_flow is not None:
            ncf = _dec(fill.net_cash_flow)
            if fill.side == "buy" and ncf >= 0:
                self._fail(CashSignError,
                           f"{fill.fill_id}: buy net_cash_flow {ncf} is not an "
                           f"outflow (cost sign flipped)")
            if fill.side == "sell" and ncf <= 0:
                self._fail(CashSignError,
                           f"{fill.fill_id}: sell net_cash_flow {ncf} is not an "
                           f"inflow")

    def _open_clip(self, fill: Fill, day: date) -> None:
        cid = fill.clip_id or fill.fill_id
        if cid in self._clip_registry and not self._clip_registry[cid].closed:
            self._fail(DuplicateFillError, f"clip {cid!r} opened twice")
        clip = Clip(clip_id=cid, symbol=fill.symbol, shares=fill.shares,
                    acquired=day, price=_dec(fill.price), session=fill.session)
        self._clip_registry[cid] = clip
        self.clips.setdefault(fill.symbol, []).append(clip)

    def _consume_fifo(self, fill: Fill, day: date, session: str) -> None:
        cs = self.clips.get(fill.symbol)
        # 旧批次状态残留：引用一个已清空/不存在的批次
        if fill.clip_id is not None:
            target = self._clip_registry.get(fill.clip_id)
            if target is None:
                self._fail(StaleClipError,
                           f"{fill.fill_id}: references unknown clip {fill.clip_id!r}")
            if target.closed or target.shares <= 0:
                self._fail(StaleClipError,
                           f"{fill.fill_id}: references closed/stale clip "
                           f"{fill.clip_id!r}")
        if not cs:
            self._fail(ClipOverConsumptionError,
                       f"{fill.fill_id}: sell {fill.symbol} with no holdings")
        total = sum(c.shares for c in cs)
        if fill.shares > total:
            self._fail(ClipOverConsumptionError,
                       f"{fill.fill_id}: sell {fill.shares} > held {total} "
                       f"of {fill.symbol}")
        sellable = sum(c.shares for c in cs if self._sellable(c, day, session))
        if fill.shares > sellable:
            self._fail(TPlusViolationError,
                       f"{fill.fill_id}: sell {fill.shares} > sellable {sellable} "
                       f"on {day} (T+1)")
        remaining = fill.shares
        for c in cs:
            if remaining <= 0:
                break
            if c.shares <= 0:
                continue
            take = min(c.shares, remaining)
            c.shares -= take
            remaining -= take
            if c.shares == 0:
                c.closed = True
        self.clips[fill.symbol] = [c for c in cs if c.shares > 0]

    # -- 分析（供 TV-B29/B30 与注入测试） ----------------------------------- #
    def annual_returns(self) -> dict[int, Decimal]:
        """逐自然年收益：首年 = 首年末权益/初始权益 − 1，后续 = 当年末/上年末 − 1。"""
        if not self.days:
            return {}
        by_year: dict[int, Decimal] = {}
        for rec in self.days:
            by_year[rec.day.year] = rec.equity
        returns: dict[int, Decimal] = {}
        years = sorted(by_year)
        prev = self.initial_cash
        for y in years:
            returns[y] = by_year[y] / prev - Decimal(1)
            prev = by_year[y]
        return returns

    @staticmethod
    def max_drawdown_magnitude(equities: Sequence[Decimal]) -> Decimal:
        """最大回撤**正幅度** max_t(1 - E_t / max_{s<=t} E_s)。"""
        peak = None
        mdd = Decimal(0)
        for e in equities:
            if peak is None or e > peak:
                peak = e
            if peak and peak > 0:
                dd = Decimal(1) - e / peak
                if dd > mdd:
                    mdd = dd
        return mdd


# --------------------------------------------------------------------------- #
# 独立校验/分析函数（供注入测试直接调用）
# --------------------------------------------------------------------------- #
def assert_full_year_coverage(returns: Mapping[int, Decimal],
                              first_year: int, last_year: int) -> None:
    """年度收益必须覆盖每一自然年（首年收益遗漏检查）。"""
    expected = set(range(first_year, last_year + 1))
    missing = sorted(expected - set(returns))
    if missing:
        raise CoverageError(f"annual returns missing years {missing}")


def assert_drawdown_gate(mdd_reported: Decimal, limit: Decimal) -> None:
    """账户回撤门：幅度必须为正号（负号 MDD 误比较检查）。"""
    if mdd_reported < 0:
        raise SignConventionError(
            f"drawdown magnitude {mdd_reported} is negative; a −X% magnitude "
            f"compared as '< {limit}' would wrongly pass")
    if mdd_reported >= limit:
        raise LedgerError(f"drawdown {mdd_reported} >= limit {limit}")


def assert_equity_identity(cash_total: Decimal, position_mv: Decimal,
                           equity: Decimal) -> None:
    if abs(cash_total + position_mv - equity) > Decimal("0.005"):
        raise EquityIdentityError(
            f"equity {equity} != cash {cash_total} + mv {position_mv}")
