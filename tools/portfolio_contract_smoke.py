#!/usr/bin/env python
"""组合层契约集成冒烟：``risk_overlay`` -> ``strategy_plan`` -> ``RecommendationPlan``。

把三种账户级风险配置（C0/C1/C2）与三类决策点（Day0 收盘 / 11:30 / 15:00）串成一条可重复
的合成链路，对 13 组契约行为逐条断言，并把每条结论打印成 ``PASS``/``FAIL`` 与稳定的原因
代码。

纪律（AGENTS.md 3 / 6）：

* **只用合成数据**。本文件不读 ``data/``、``artifacts/``、真实账户快照，也不联网；默认不写
  任何文件（``--out`` 显式指定时才写剧本之外的 JSON，且拒绝落在 ``artifacts/`` 下）。
* 2026-09-xx 只是与 ``tests/unit/test_strategy_plan.py`` 一致的**时钟标签**，不是数据观测：
  指数与权益序列全部由本文件现造，合成日历由 ``date`` 递推生成，台账里没有这些日期的行情。

运行：

    python tools/portfolio_contract_smoke.py                  # 全部剧本
    python tools/portfolio_contract_smoke.py --list
    python tools/portfolio_contract_smoke.py --only limits    # 单个剧本（可重复）
    python tools/portfolio_contract_smoke.py --out report.json

同一组剧本也是集成测试：``pytest -q tools/portfolio_contract_smoke.py``（pytest 收集本文件
里的 ``test_*``）。导入 ``quant`` 之前会把仓库 ``src/`` 放到 ``sys.path`` 最前，并断言三个
模块确实解析到 ``src/`` 下的当前源码，避免非 editable 安装的旧 wheel 静默通过。
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
for _boot in (str(REPO_ROOT), str(SRC)):
    if _boot not in sys.path:
        sys.path.insert(0, _boot)

from quant.portfolio import recommendations as rec  # noqa: E402
from quant.portfolio import risk_overlay as ro  # noqa: E402
from quant.portfolio import strategy_plan as sp  # noqa: E402

MODULES = (ro, sp, rec)

# --------------------------------------------------------------------------- #
# 合成台账：时钟、账户、候选
# --------------------------------------------------------------------------- #
EQUITY = 200_000.0
CASH = 80_000.0
STRATEGY = "strat-smoke-20260918"
DAY0 = dt.date(2026, 9, 21)
DAY1 = dt.date(2026, 9, 22)
DAY2 = dt.date(2026, 9, 23)
DAY0_CLOSE = dt.datetime(2026, 9, 21, 15, 0)
AM_1130 = dt.datetime(2026, 9, 22, 11, 30)
PM_1500 = dt.datetime(2026, 9, 22, 15, 0)
TOL = 1e-9
LOT = 100

#: 决策点 -> (决策时钟, 所属交易日, 下一交易日或 None)。
POINTS: dict[rec.DecisionPoint, tuple[dt.datetime, dt.date, dt.date | None]] = {
    rec.DecisionPoint.DAY0_CLOSE: (DAY0_CLOSE, DAY0, DAY1),
    rec.DecisionPoint.AM_1130: (AM_1130, DAY1, None),
    rec.DecisionPoint.PM_1500: (PM_1500, DAY1, DAY2),
}

#: 每个决策点可以读到的**已完成**收盘日：11:30 只读前一交易日（risk_overlay 模块头）。
EXPECTED_ASOF = {
    rec.DecisionPoint.DAY0_CLOSE: DAY0,
    rec.DecisionPoint.AM_1130: DAY0,
    rec.DecisionPoint.PM_1500: DAY1,
}


def _weekdays(count: int, *, end: dt.date) -> list[dt.date]:
    days: list[dt.date] = []
    day = end
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day -= dt.timedelta(days=1)
    return list(reversed(days))


#: 240 个合成交易日（含 DAY2），保证 C1 的 200 日均线有足够前置样本。
SESSIONS = _weekdays(240, end=DAY2)
BEFORE_DAY0 = SESSIONS[-4]


def benchmark_series(arm: str) -> list[tuple[dt.date, float]]:
    """合成 000300 收盘序列：``normal`` 站上均线，``reduced`` 跌破均线。"""
    last = (
        {DAY0: 101.0, DAY1: 103.0, DAY2: 105.0}
        if arm == "normal"
        else {DAY0: 90.0, DAY1: 90.0, DAY2: 90.0}
    )
    return [(day, last.get(day, 100.0)) for day in SESSIONS]


def equity_series(arm: str) -> list[tuple[dt.date, float]]:
    """合成账户权益序列：``normal`` 不断新高，``reduced`` 距高水位回撤 18.2%。"""
    if arm == "normal":
        return [(BEFORE_DAY0, 100_000.0), (DAY0, 105_000.0), (DAY1, 108_000.0)]
    return [(BEFORE_DAY0, 110_000.0), (DAY0, 90_000.0), (DAY1, 90_000.0)]


def benchmark_warmup() -> list[tuple[dt.date, float]]:
    """样本不足的指数序列：C1 只能 FAIL_CLOSED（``INSUFFICIENT_DATA``）。"""
    return [(day, 100.0) for day in SESSIONS[-10:]]


def position(
    symbol: str,
    quantity: int,
    sleeve: rec.Sleeve,
    price: float,
    *,
    sellable: int | None = None,
) -> rec.Position:
    return rec.Position(
        symbol,
        symbol,
        sleeve,
        quantity,
        quantity if sellable is None else sellable,
        price,
        price,
    )


#: 合成持仓：进攻 600000/000001，防御 510300/511010（毛利 12 万，现金 8 万）。
BOOK = (
    position("600000", 2000, rec.Sleeve.ATTACK, 10.0),
    position("000001", 2000, rec.Sleeve.ATTACK, 5.0),
    position("510300", 10_000, rec.Sleeve.DEFENSE, 4.0),
    position("511010", 5_000, rec.Sleeve.DEFENSE, 10.0),
)
ATTACK_HOLDING, ATTACK_CARRIER = "600000", "000001"
DEFENSE_HOLDING, DEFENSE_CARRIER = "510300", "511010"
ATTACK_ENTRIES = ("600036", "601899")
DEFENSE_ENTRY = "159915"


def attack_candidate(
    symbol: str,
    base: float,
    *,
    price: float = 10.0,
    stop: float = 9.0,
    action: rec.Action = rec.Action.NEW,
    previous: rec.Action | None = None,
    band: bool = True,
) -> sp.AttackCandidate:
    lower, upper = (round(price * 0.99, 3), price) if band else (None, None)
    return sp.AttackCandidate(
        symbol,
        symbol,
        base,
        f"{symbol} 触发：收盘放量站上均线",
        f"{symbol} 失效：跌破止损或趋势转弱",
        stop,
        price,
        lower,
        upper,
        action,
        previous,
        f"{symbol} 本版变化",
    )


def defense_candidate(
    symbol: str,
    target: float,
    *,
    price: float = 4.0,
    action: rec.Action = rec.Action.NEW,
    band: bool = True,
) -> sp.DefenseCandidate:
    lower, upper = (round(price * 0.99, 3), price) if band else (None, None)
    return sp.DefenseCandidate(
        symbol,
        symbol,
        target,
        f"{symbol} 触发：趋势向上",
        f"{symbol} 失效：趋势转弱",
        price,
        lower,
        upper,
        action,
        None,
        f"{symbol} 本版变化",
    )


#: 标准候选篮子：进攻补仓 + 两个进攻新开 + 防御底盘维持 + 一个防御新开。
BASE_ATTACKS = (
    attack_candidate("600000", 0.20, action=rec.Action.ADD, previous=rec.Action.NEW),
    attack_candidate("600036", 0.10),
    attack_candidate("601899", 0.06, price=20.0, stop=18.0),
)
BASE_DEFENSES = (
    defense_candidate("510300", 0.20, action=rec.Action.HOLD, band=False),
    defense_candidate("159915", 0.05, price=3.0),
)

#: 合成结果（手算，装配层只做整手取整）：
#: 新开 qty = floor(base * E_t * 200000 / price / 100) * 100，目标权重 = qty * price / 200000。
EXPECTED: dict[str, dict[str, tuple[int, float]]] = {
    "normal": {
        "600036": (1800, 0.09),  # 0.10 * 0.90 * 200000 / 10
        "601899": (500, 0.05),  # 0.06 * 0.90 * 200000 / 20 = 540 股 -> 5 手
        "600000": (1600, 0.18),  # ADD：0.20 * 0.90 -> 3600 股，减已持 2000
        "159915": (3300, 0.0495),  # 防御不缩放
    },
    "reduced": {
        "600036": (800, 0.04),  # 0.10 * 0.40 * 200000 / 10
        "601899": (200, 0.02),  # 240 股 -> 2 手
        "600000": (400, 0.08),  # ACCOUNT_DELEVER：2000 - 1600
        "159915": (3300, 0.0495),  # 与 normal 臂逐字段相同
    },
}
EXPECTED_DEFENSE_HELD = {"510300": (0, 0.20), "511010": (0, 0.25)}

#: 注册上限（AGENTS.md 1）：单标的 25%、总仓位 100%、进攻 4 / 防御 3 / 合计 7、Day0 新开 3。
LIMITS = {"symbol": 0.25, "total": 1.0, "attack_slots": 4, "defense_slots": 3, "total_slots": 7}
NEW_ENTRY_CAP = 3


def snapshot(
    version: str,
    point: rec.DecisionPoint,
    *,
    positions: Sequence[rec.Position] = (),
    cash: float = CASH,
    equity: float = EQUITY,
    as_of: dt.datetime | None = None,
    market_as_of: dt.datetime | None = None,
    strategy_version: str = STRATEGY,
) -> rec.AccountSnapshot:
    moment = POINTS[point][0]
    return rec.AccountSnapshot(
        f"acct-{version}",
        moment if as_of is None else as_of,
        strategy_version,
        moment if market_as_of is None else market_as_of,
        equity,
        cash,
        tuple(positions),
    )


def overlay_row(
    config_id: str,
    point: rec.DecisionPoint,
    arm: str = "normal",
    *,
    warmup: bool = False,
) -> ro.OverlayDecision:
    """冻结点行：C0 常量系数，C1 指数均线，C2 账户回撤。"""
    moment = POINTS[point][0]
    extra: dict[str, Any] = {}
    if config_id == ro.C1:
        extra["benchmark_close"] = benchmark_warmup() if warmup else benchmark_series(arm)
    elif config_id == ro.C2:
        extra["equity"] = equity_series(arm)
    return ro.resolve_overlay(
        [moment], config_id=config_id, decision_points=[point], **extra
    )[0]


def assemble(
    account: rec.AccountSnapshot,
    version: str,
    row: ro.OverlayDecision,
    *,
    point: rec.DecisionPoint,
    attacks: Sequence[sp.AttackCandidate] = BASE_ATTACKS,
    defenses: Sequence[sp.DefenseCandidate] = BASE_DEFENSES,
    carried_stops: dict[str, float] | None = None,
    generated_at: dt.datetime | None = None,
) -> rec.RecommendationPlan:
    _, trading_day, next_day = POINTS[point]
    return sp.assemble_plan(
        decision_point=point,
        trading_day=trading_day,
        generated_at=POINTS[point][0] if generated_at is None else generated_at,
        account=account,
        overlay=row,
        recommendation_version=version,
        attack_candidates=tuple(attacks),
        defense_candidates=tuple(defenses),
        carried_stops=carried_stops,
        next_trading_day=next_day,
    )


def build_case(
    point: rec.DecisionPoint,
    row: ro.OverlayDecision,
    version: str,
    *,
    positions: Sequence[rec.Position] = BOOK,
    cash: float = CASH,
    attacks: Sequence[sp.AttackCandidate] = BASE_ATTACKS,
    defenses: Sequence[sp.DefenseCandidate] = BASE_DEFENSES,
    **snapshot_kwargs: Any,
) -> tuple[rec.AccountSnapshot, rec.RecommendationPlan]:
    """一个完整半日场景：合成快照 + 同一身份装配出的计划（可直接进台账）。"""
    account = snapshot(version, point, positions=positions, cash=cash, **snapshot_kwargs)
    return account, assemble(
        account, version, row, point=point, attacks=attacks, defenses=defenses
    )


# --------------------------------------------------------------------------- #
# 断言与报告
# --------------------------------------------------------------------------- #
class SmokeFailure(Exception):
    """契约不符：携带稳定原因代码与具体证据。"""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


_ASSERTIONS = 0


def check(condition: bool, code: str, detail: str) -> None:
    global _ASSERTIONS
    _ASSERTIONS += 1
    if not condition:
        raise SmokeFailure(code, detail)


def near(actual: float, expected: float, code: str, detail: str) -> None:
    check(
        math.isclose(actual, expected, rel_tol=0.0, abs_tol=TOL),
        code,
        f"{detail}（期望 {expected!r}，实际 {actual!r}）",
    )


def item_of(plan: rec.RecommendationPlan, symbol: str) -> rec.RecommendationItem:
    item = plan.item(symbol)
    check(item is not None, "MISSING_POSITION_ITEM", f"{symbol}: 版本缺少该标的条目")
    assert item is not None
    return item


def notes(plan: rec.RecommendationPlan) -> dict[str, tuple[str, ...]]:
    return sp.parse_notes(plan.note)


def note_symbols(plan: rec.RecommendationPlan, token: str) -> tuple[str, ...]:
    return notes(plan).get(token, ())


def expect_error(code: str, label: str, thunk: Callable[[], Any]) -> None:
    """失败关闭断言：``thunk`` 必须抛出 ``reason.name == code`` 的领域错误。"""
    global _ASSERTIONS
    _ASSERTIONS += 1
    try:
        thunk()
    except (rec.RecommendationError, ro.RiskOverlayError, sp.StrategyPlanError) as exc:
        got = getattr(getattr(exc, "reason", None), "name", None)
        if got != code:
            raise SmokeFailure(
                "WRONG_REASON_CODE", f"{label}: 期望 {code}，实际 {got}（{exc}）"
            ) from exc
        return
    except Exception as exc:  # 非领域错误即契约外行为
        raise SmokeFailure(
            "UNEXPECTED_EXCEPTION",
            f"{label}: 期望 {code}，实际抛出 {type(exc).__name__}: {exc}",
        ) from exc
    raise SmokeFailure("NO_ERROR_RAISED", f"{label}: 期望 {code}，但没有任何拒绝")


def _fields(account: rec.AccountSnapshot) -> dict[str, Any]:
    return dataclasses.asdict(account)


# --------------------------------------------------------------------------- #
# 剧本
# --------------------------------------------------------------------------- #
def s_frozen_configs() -> str:
    """三档固定风险配置与状态映射（预登记常量，不允许事后调参）。"""
    check(
        set(ro.POLICIES) == {ro.C0, ro.C1, ro.C2},
        "CONFIG_SET",
        f"注册配置集合异常：{sorted(ro.POLICIES)}",
    )
    c0, c1, c2 = (ro.policy_for(c) for c in (ro.C0, ro.C1, ro.C2))
    check(
        c0.mechanism is ro.GateMechanism.CONSTANT
        and c0.level_on == 0.90
        and c1.mechanism is ro.GateMechanism.INDEX_SMA
        and c1.sma_sessions == 200
        and c2.mechanism is ro.GateMechanism.ACCOUNT_DRAWDOWN
        and math.isclose(c2.drawdown_threshold, 0.10),
        "CONFIG_FROZEN_VALUES",
        f"配置冻结点被改动：C0={c0.mechanism}/C1={c1.mechanism}/{c1.sma_sessions}/"
        f"C2={c2.mechanism}/{c2.drawdown_threshold}",
    )
    check(
        ro.LEVEL_ON == 0.90
        and ro.LEVEL_OFF == 0.40
        and ro.RECOVERY_CONFIRMATIONS == 2
        and ro.COOLDOWN_SESSIONS == 3,
        "CONFIG_FROZEN_CONSTANTS",
        f"系数/确认/冷却被改动：{ro.LEVEL_ON}/{ro.LEVEL_OFF}/"
        f"{ro.RECOVERY_CONFIRMATIONS}/{ro.COOLDOWN_SESSIONS}",
    )
    check(
        c0.hard_stop_drawdown is None and c2.hard_stop_drawdown is None,
        "CONFIG_BLOCKED_REACHABLE",
        "冻结配置出现 hard_stop_drawdown：BLOCKED 不再是配置外状态",
    )
    expect_error("UNKNOWN_CONFIG", "未知配置", lambda: ro.policy_for("C9"))
    for state, allowed in (
        (ro.OverlayState.NORMAL, True),
        (ro.OverlayState.REDUCED, True),
        (ro.OverlayState.BLOCKED, False),
        (ro.OverlayState.INSUFFICIENT_DATA, False),
    ):
        check(
            ro.attack_entry_allowed(state) is allowed,
            "ENTRY_GATE_MAPPING",
            f"{state.name}: attack_entry_allowed 期望 {allowed}",
        )
    check(
        ro.to_plan_risk_state(ro.OverlayState.NORMAL) is rec.RiskState.NORMAL
        and ro.to_plan_risk_state(ro.OverlayState.REDUCED) is rec.RiskState.CAUTION
        and ro.to_plan_risk_state(ro.OverlayState.BLOCKED) is rec.RiskState.RISK_OFF
        and ro.to_plan_risk_state(ro.OverlayState.INSUFFICIENT_DATA)
        is rec.RiskState.RISK_OFF,
        "RISK_STATE_MAPPING",
        "覆盖层状态到计划风险状态的映射被改动",
    )
    check(
        all(
            ro.to_plan_account_action(action) is rec.Action.NO_ACTION
            for action in (
                ro.OverlayAction.HOLD,
                ro.OverlayAction.REDUCE_ATTACK,
                ro.OverlayAction.RESTORE_ATTACK,
            )
        )
        and ro.to_plan_account_action(ro.OverlayAction.BLOCK_NEW_ATTACK)
        is rec.Action.ACCOUNT_DELEVER
        and ro.to_plan_account_action(ro.OverlayAction.FAIL_CLOSED)
        is rec.Action.ACCOUNT_DELEVER,
        "ACCOUNT_ACTION_MAPPING",
        "覆盖层动作到账户动作的映射被改动",
    )
    return (
        "C0=常量 0.90/0.40、C1=200 日均线、C2=回撤 10% 冻结；确认 2 / 冷却 3；"
        "BLOCKED 仅配置外可达；state/action 映射与 attack_entry_allowed 一致"
    )


def s_matrix() -> str:
    """3 个决策点 × 3 个风险配置：半日窗口、身份、系数、上限、资金覆盖。"""
    plans = 0
    for point in POINTS:
        for config_id in (ro.C0, ro.C1, ro.C2):
            arms = ("normal",) if config_id == ro.C0 else ("normal", "reduced")
            for arm in arms:
                row = overlay_row(config_id, point, arm)
                rate = row.exposure_multiplier
                account, plan = build_case(
                    point, row, f"rec-matrix-{config_id}-{point.value}-{arm}"
                )
                exposure = rec.validate_plan(plan, account=account)
                plans += 1
                label = f"{config_id}/{point.value}/{arm}"

                _, trading_day, next_day = POINTS[point]
                window = rec.session_window(
                    point, trading_day=trading_day, next_trading_day=next_day
                )
                check(
                    (plan.valid_from, plan.valid_until) == window,
                    "WRONG_SESSION_WINDOW",
                    f"{label}: 有效期 {plan.valid_from}~{plan.valid_until} 不是注册半日 {window}",
                )
                check(
                    all(item.valid_until == plan.valid_until for item in plan.items),
                    "ITEM_WINDOW_MISMATCH",
                    f"{label}: 存在条目有效期与版本半日不一致",
                )
                check(
                    plan.market_as_of == account.market_as_of == POINTS[point][0],
                    "MARKET_AS_OF_MISMATCH",
                    f"{label}: 版本行情截止与账户/决策时钟不一致",
                )
                check(
                    plan.strategy_version == STRATEGY
                    and plan.account_snapshot_version == account.snapshot_version,
                    "ACCOUNT_SNAPSHOT_MISMATCH",
                    f"{label}: 版本身份与账户快照不一致",
                )
                check(
                    (plan.equity, plan.cash) == (account.equity, account.cash),
                    "ACCOUNT_HEADER_MISMATCH",
                    f"{label}: 版本权益/现金与账户快照不一致",
                )
                if row.risk_state is ro.OverlayState.NORMAL:
                    check(
                        plan.risk_state is rec.RiskState.NORMAL
                        and plan.account_action is rec.Action.NO_ACTION
                        and not plan.entry_paused,
                        "RISK_STATE_MAPPING",
                        f"{label}: 正常行未映射为 NORMAL/NO_ACTION 且闸门开启",
                    )
                    near(rate, 0.90, "EXPOSURE_MULTIPLIER", f"{label}: 正常行系数")
                else:
                    check(
                        plan.risk_state is rec.RiskState.CAUTION
                        and plan.account_action is rec.Action.NO_ACTION
                        and not plan.entry_paused,
                        "RISK_STATE_MAPPING",
                        f"{label}: 降仓行未映射为 CAUTION/NO_ACTION（进攻仍可入场）",
                    )
                    near(rate, 0.40, "EXPOSURE_MULTIPLIER", f"{label}: 降仓系数")

                check(exposure.ok, "EXPOSURE_NOT_OK", f"{label}: 暴露核算未通过")
                check(
                    exposure.attack_symbols == LIMITS["attack_slots"]
                    and exposure.defense_symbols == LIMITS["defense_slots"]
                    and exposure.total_symbols == LIMITS["total_slots"],
                    "SLOT_MISMATCH",
                    f"{label}: 席位 {exposure.attack_symbols}/{exposure.defense_symbols}/"
                    f"{exposure.total_symbols} 不等于 4/3/7",
                )
                check(
                    exposure.new_entries == NEW_ENTRY_CAP,
                    "NEW_ENTRY_CAP_MISMATCH",
                    f"{label}: 新开 {exposure.new_entries} 不等于 {NEW_ENTRY_CAP}",
                )
                check(
                    exposure.total_weight <= LIMITS["total"] + TOL,
                    "GROSS_EXPOSURE_LIMIT",
                    f"{label}: 总仓位 {exposure.total_weight} 超过 100%",
                )
                check(
                    exposure.symbol_limit_breaches == ()
                    and exposure.uncovered_positions == (),
                    "WEIGHT_OR_COVERAGE_BREACH",
                    f"{label}: 单标的超限 {exposure.symbol_limit_breaches} 或未覆盖持仓 "
                    f"{exposure.uncovered_positions}",
                )
                check(
                    exposure.buy_notional + exposure.buy_fees <= plan.cash + TOL,
                    "INSUFFICIENT_CASH",
                    f"{label}: 买单名义 {exposure.buy_notional} + 费用 {exposure.buy_fees} "
                    f"超过现金 {plan.cash}",
                )
                check(
                    exposure == rec.exposure_of(plan, account=account),
                    "EXPOSURE_MIRROR_MISMATCH",
                    f"{label}: validate_plan 与 exposure_of 核算不一致",
                )
                for item in plan.items:
                    if item.action in rec.BUY_ACTIONS or item.action in rec.SELL_ACTIONS:
                        check(
                            item.recommended_quantity % LOT == 0,
                            "INVALID_LOT",
                            f"{label}/{item.symbol}: 订单 {item.recommended_quantity} 不是整手",
                        )
                for symbol, (qty, weight) in EXPECTED[arm].items():
                    item = item_of(plan, symbol)
                    check(
                        item.recommended_quantity == qty,
                        "SCALED_SIZE",
                        f"{label}/{symbol}: 数量 {item.recommended_quantity} != {qty}",
                    )
                    near(
                        item.target_weight,
                        weight,
                        "SCALED_TARGET",
                        f"{label}/{symbol}: 目标仓位",
                    )
                check(
                    {p.symbol for p in BOOK} <= {item.symbol for item in plan.items},
                    "COVERAGE_LOST",
                    f"{label}: 持仓覆盖不完整：{[i.symbol for i in plan.items]}",
                )
                for held in BOOK:
                    item = item_of(plan, held.symbol)
                    check(
                        item.current_quantity == held.quantity,
                        "POSITION_QUANTITY_DRIFT",
                        f"{label}/{held.symbol}: 条目当前数量 {item.current_quantity} != "
                        f"账户 {held.quantity}",
                    )
    return (
        f"{plans} 版计划（3 决策点 × 3 配置 × 各自有效臂）：半日窗口、身份、系数、"
        f"4/3/7 席位、{NEW_ENTRY_CAP} 新开、100% 总仓位、费用覆盖与整手全部一致"
    )


def s_attack_scaling_only() -> str:
    """风险降档只缩进攻袖套：防御条目逐字段不变，进攻严格缩小。"""
    seen: list[str] = []
    for point in POINTS:
        for config_id in (ro.C1, ro.C2):
            on_account, on = build_case(
                point,
                overlay_row(config_id, point, "normal"),
                f"rec-scale-{config_id}-on-{point.value}",
            )
            off_account, off = build_case(
                point,
                overlay_row(config_id, point, "reduced"),
                f"rec-scale-{config_id}-off-{point.value}",
            )
            on_exposure = rec.validate_plan(on, account=on_account)
            off_exposure = rec.validate_plan(off, account=off_account)
            label = f"{config_id}/{point.value}"

            check(
                on.risk_state is rec.RiskState.NORMAL
                and off.risk_state is rec.RiskState.CAUTION
                and not off.entry_paused,
                "RISK_STATE_MAPPING",
                f"{label}: 正常/降仓两侧未映射为 NORMAL/CAUTION 或降仓侧停发进攻",
            )
            for symbol in (DEFENSE_HOLDING, DEFENSE_CARRIER, DEFENSE_ENTRY):
                left, right = item_of(on, symbol), item_of(off, symbol)
                check(
                    left == right,
                    "DEFENSE_ITEM_CHANGED",
                    f"{label}/{symbol}: 降仓改动了防御条目（{left.action.name} "
                    f"{left.recommended_quantity}@{left.target_weight} vs {right.action.name} "
                    f"{right.recommended_quantity}@{right.target_weight}）",
                )
                expected_qty, expected_weight = (
                    EXPECTED_DEFENSE_HELD[symbol]
                    if symbol in EXPECTED_DEFENSE_HELD
                    else EXPECTED["normal"][symbol]
                )
                check(
                    left.recommended_quantity == expected_qty,
                    "DEFENSE_SIZE",
                    f"{label}/{symbol}: 防御数量 {left.recommended_quantity} != {expected_qty}",
                )
                near(
                    left.target_weight,
                    expected_weight,
                    "DEFENSE_TARGET",
                    f"{label}/{symbol}: 防御目标仓位",
                )
            check(
                off.new_entry_items != () and off.item(DEFENSE_ENTRY) is not None,
                "DEFENSE_ENTRY_DROPPED",
                f"{label}: 降仓后防御新开被丢弃",
            )
            for symbol in ATTACK_ENTRIES:
                on_qty, on_weight = EXPECTED["normal"][symbol]
                off_qty, off_weight = EXPECTED["reduced"][symbol]
                left, right = item_of(on, symbol), item_of(off, symbol)
                check(
                    (left.recommended_quantity, right.recommended_quantity)
                    == (on_qty, off_qty),
                    "ATTACK_SIZE",
                    f"{label}/{symbol}: 进攻数量 {left.recommended_quantity}/"
                    f"{right.recommended_quantity} != {on_qty}/{off_qty}",
                )
                near(left.target_weight, on_weight, "ATTACK_TARGET", f"{label}/{symbol}: 正常臂")
                near(right.target_weight, off_weight, "ATTACK_TARGET", f"{label}/{symbol}: 降仓臂")
                check(
                    right.target_weight < left.target_weight,
                    "ATTACK_NOT_SCALED",
                    f"{label}/{symbol}: 降仓臂目标未低于正常臂",
                )
            held_on, held_off = item_of(on, ATTACK_HOLDING), item_of(off, ATTACK_HOLDING)
            check(
                held_on.action is rec.Action.ADD
                and held_off.action is rec.Action.ACCOUNT_DELEVER
                and (held_on.recommended_quantity, held_off.recommended_quantity)
                == (
                    EXPECTED["normal"][ATTACK_HOLDING][0],
                    EXPECTED["reduced"][ATTACK_HOLDING][0],
                ),
                "ATTACK_ACTION",
                f"{label}/{ATTACK_HOLDING}: 补仓/降仓不符（{held_on.action.name} "
                f"{held_on.recommended_quantity} vs {held_off.action.name} "
                f"{held_off.recommended_quantity}）",
            )
            carried = BOOK[0].quantity * BOOK[0].last_price / EQUITY
            check(
                held_off.target_weight < carried < held_on.target_weight,
                "ATTACK_NOT_SCALED",
                f"{label}/{ATTACK_HOLDING}: 缩放未跨越已持权重 {carried}（"
                f"{held_off.target_weight} / {held_on.target_weight}）",
            )
            check(
                off_exposure.attack_weight < on_exposure.attack_weight
                and off_exposure.defense_weight == on_exposure.defense_weight,
                "SLEEVE_ISOLATION",
                f"{label}: 进攻 {on_exposure.attack_weight}->{off_exposure.attack_weight}、"
                f"防御 {on_exposure.defense_weight}->{off_exposure.defense_weight}",
            )
            seen.append(
                f"{label} 进攻 {on_exposure.attack_weight:.4f}->{off_exposure.attack_weight:.4f}，"
                f"防御 {on_exposure.defense_weight:.4f} 不变"
            )
    return "；".join(seen)


def s_insufficient_data_blocks_entries() -> str:
    """样本缺失（FAIL_CLOSED）闸门关闭：不新增任何袖套，持仓仍逐个带条目。"""
    row = overlay_row(ro.C1, rec.DecisionPoint.DAY0_CLOSE, warmup=True)
    check(
        row.risk_state is ro.OverlayState.INSUFFICIENT_DATA
        and row.action is ro.OverlayAction.FAIL_CLOSED,
        "OVERLAY_NOT_FAIL_CLOSED",
        f"样本不足行未 FAIL_CLOSED（实际 {row.risk_state.name}/{row.action.name}）",
    )
    near(row.exposure_multiplier, 0.40, "EXPOSURE_MULTIPLIER", "FAIL_CLOSED 系数")
    account, plan = build_case(rec.DecisionPoint.DAY0_CLOSE, row, "rec-gap-full")
    exposure = rec.validate_plan(plan, account=account)
    check(
        plan.risk_state is rec.RiskState.RISK_OFF
        and plan.account_action is rec.Action.ACCOUNT_DELEVER,
        "RISK_STATE_MAPPING",
        f"数据缺口未映射为 RISK_OFF/ACCOUNT_DELEVER（实际 {plan.risk_state.name}/"
        f"{plan.account_action.name}）",
    )
    check(
        plan.new_entry_items == () and plan.entry_paused,
        "ENTRY_NOT_PAUSED",
        f"数据缺口下仍有新开 {[i.symbol for i in plan.new_entry_items]}",
    )
    check(
        not any(item.action in rec.BUY_ACTIONS for item in plan.items),
        "BUY_IN_GAP",
        f"数据缺口下仍有买单 {[(i.symbol, i.action.name) for i in plan.items]}",
    )
    blocked = set(note_symbols(plan, sp.ENTRY_BLOCKED))
    check(
        blocked == {*ATTACK_ENTRIES, DEFENSE_ENTRY},
        "ENTRY_BLOCKED_NOT_DISCLOSED",
        f"entry_blocked 未逐条披露：{sorted(blocked)}",
    )
    check(
        {p.symbol for p in BOOK} <= {item.symbol for item in plan.items},
        "COVERAGE_LOST",
        f"数据缺口下持仓覆盖不完整：{[i.symbol for i in plan.items]}",
    )
    held = item_of(plan, ATTACK_HOLDING)
    check(
        held.action is rec.Action.ACCOUNT_DELEVER
        and held.recommended_quantity == BOOK[0].quantity - 1600,
        "RISK_EXIT_UNAVAILABLE",
        f"数据缺口下账户级降仓未执行：{held.action.name} {held.recommended_quantity}",
    )
    check(
        exposure.buy_notional == 0.0 and plan.cash == account.cash,
        "CASH_MOVED",
        "数据缺口下仍占用或改动现金",
    )
    small = (position(ATTACK_HOLDING, 400, rec.Sleeve.ATTACK, 10.0),)
    small_account, small_plan = build_case(
        rec.DecisionPoint.DAY0_CLOSE,
        row,
        "rec-gap-small",
        positions=small,
        attacks=(
            attack_candidate(
                ATTACK_HOLDING, 0.10, action=rec.Action.ADD, previous=rec.Action.NEW
            ),
        ),
        defenses=(),
    )
    rec.validate_plan(small_plan, account=small_account)
    degraded = item_of(small_plan, ATTACK_HOLDING)
    check(
        degraded.action is rec.Action.HOLD
        and degraded.recommended_quantity == 0
        and note_symbols(small_plan, sp.ENTRY_BLOCKED) == (ATTACK_HOLDING,),
        "BLOCKED_BUY_NOT_DEGRADED",
        f"被压掉的补仓未降级为持有：{degraded.action.name} {degraded.recommended_quantity}",
    )
    check(
        degraded.stop_price is not None and degraded.risk_r is not None,
        "STOP_LOST_IN_GAP",
        "降级后的持仓丢了止损与风险 R",
    )
    return (
        f"FAIL_CLOSED -> RISK_OFF/ACCOUNT_DELEVER：新开 0、买单 0、entry_blocked="
        f"{sorted(blocked)}；降级持仓 {degraded.action.name} 带止损 {degraded.stop_price}"
    )


def s_entry_gate_attack_scoped() -> str:
    """风控闸门按袖套分治：只压进攻买单，防御买单不因账户级状态被压。"""
    point = rec.DecisionPoint.DAY0_CLOSE
    account, plan = build_case(
        point,
        overlay_row(ro.C0, point),
        "rec-gate",
        positions=(),
        attacks=(attack_candidate(ATTACK_ENTRIES[0], 0.10),),
        defenses=(defense_candidate(DEFENSE_ENTRY, 0.05, price=3.0),),
    )
    rec.validate_plan(plan, account=account)
    identity = rec.PlanIdentity(
        plan.strategy_version, plan.market_as_of, plan.account_snapshot_version
    )

    def rebuild(
        items: Sequence[rec.RecommendationItem],
        risk_state: rec.RiskState,
        account_action: rec.Action,
        version: str,
    ) -> rec.RecommendationPlan:
        return rec.build_plan(
            decision_point=point,
            generated_at=plan.generated_at,
            identity=identity,
            account=account,
            recommendation_version=version,
            valid_from=plan.valid_from,
            valid_until=plan.valid_until,
            items=items,
            risk_state=risk_state,
            account_action=account_action,
        )

    attack_buy = item_of(plan, ATTACK_ENTRIES[0])
    defense_buy = item_of(plan, DEFENSE_ENTRY)
    control = rebuild(
        (attack_buy, defense_buy), rec.RiskState.NORMAL, rec.Action.NO_ACTION, "rec-gate-ctrl"
    )
    check(
        rec.validate_plan(control, account=account).ok,
        "CONTROL_PLAN_INVALID",
        "对照组（NORMAL/NO_ACTION + 两个买单）未通过校验",
    )
    expect_error(
        "ENTRY_BLOCKED_BY_RISK_STATE",
        "RISK_OFF + 进攻买单",
        lambda: rebuild(
            (attack_buy,), rec.RiskState.RISK_OFF, rec.Action.NO_ACTION, "rec-gate-ro"
        ),
    )
    expect_error(
        "ENTRY_BLOCKED_BY_RISK_STATE",
        "ACCOUNT_DELEVER + 进攻买单",
        lambda: rebuild(
            (attack_buy,), rec.RiskState.NORMAL, rec.Action.ACCOUNT_DELEVER, "rec-gate-dl"
        ),
    )
    for state, action, label in (
        (rec.RiskState.RISK_OFF, rec.Action.ACCOUNT_DELEVER, "RISK_OFF"),
        (rec.RiskState.CAUTION, rec.Action.NO_ACTION, "CAUTION"),
    ):
        defense_only = rebuild((defense_buy,), state, action, f"rec-gate-def-{label}")
        check(
            defense_only.item(DEFENSE_ENTRY) is not None
            and rec.validate_plan(defense_only, account=account).ok,
            "DEFENSE_BUY_BLOCKED_BY_ATTACK_GATE",
            f"{label} 下防御买单被账户级闸门误压（闸门必须按袖套分治）",
        )
    return (
        "NORMAL 对照组放行；RISK_OFF 与 ACCOUNT_DELEVER 在进攻买单上各抛 "
        "ENTRY_BLOCKED_BY_RISK_STATE；同状态下防御买单不抛，闸门按袖套分治"
    )


def _ledger_v1(version: str) -> tuple[rec.AccountSnapshot, rec.RecommendationPlan]:
    return build_case(
        rec.DecisionPoint.DAY0_CLOSE,
        overlay_row(ro.C0, rec.DecisionPoint.DAY0_CLOSE),
        version,
    )


def _fill_account(
    version: str,
    *,
    as_of: dt.datetime,
    cash: float,
    positions: Sequence[rec.Position],
) -> rec.AccountSnapshot:
    return snapshot(
        version,
        rec.DecisionPoint.AM_1130,
        positions=positions,
        cash=cash,
        as_of=as_of,
        market_as_of=AM_1130,
    )


def s_supersede_unfilled_intents() -> str:
    """新版本覆盖未成交旧建议：半日未结束时记 CANCELLED，到点记 EXPIRED。"""
    outcomes: list[str] = []
    for as_of, kind in (
        (dt.datetime(2026, 9, 22, 11, 0), rec.IntentOutcomeKind.CANCELLED),
        (AM_1130, rec.IntentOutcomeKind.EXPIRED),
    ):
        v1_account, v1 = _ledger_v1(f"rec-sup-{kind.value}")
        ledger = rec.RecommendationLedger()
        first = ledger.publish(v1, account=v1_account)
        check(
            first.superseded_version is None and first.outcomes == (),
            "FIRST_PUBLISH_OUTCOMES",
            "首版发布不应有被覆盖记录",
        )
        check(
            len(ledger.pending_intents()) == len(v1.order_items),
            "PENDING_MISMATCH",
            f"未成交意图 {len(ledger.pending_intents())} != 订单条目 {len(v1.order_items)}",
        )
        v2_account = _fill_account(
            f"led-{kind.value}", as_of=as_of, cash=CASH, positions=BOOK
        )
        v2 = assemble(
            v2_account,
            f"rec-sup-v2-{kind.value}",
            overlay_row(ro.C0, rec.DecisionPoint.AM_1130),
            point=rec.DecisionPoint.AM_1130,
        )
        expect_error(
            "DUPLICATE_VERSION",
            f"{kind.value}: 同版本重复发布",
            lambda: ledger.publish(v1, account=v1_account),
        )
        report = ledger.publish(v2, account=v2_account)
        check(
            report.superseded_version == v1.recommendation_version
            and report.superseded_valid_until == v1.valid_until,
            "SUPERSEDE_HEADER",
            f"覆盖记录未指向旧版本：{report.superseded_version}/"
            f"{report.superseded_valid_until}",
        )
        kinds = {outcome.symbol: outcome.kind for outcome in report.outcomes}
        check(
            set(kinds) == {item.symbol for item in v1.order_items},
            "OUTCOME_COVERAGE",
            f"被覆盖意图未逐条归档：{sorted(kinds)}",
        )
        check(
            set(kinds.values()) == {kind},
            "OUTCOME_KIND",
            f"as_of={as_of} 期望全部 {kind.name}，实际 "
            f"{ {s: k.name for s, k in kinds.items()} }",
        )
        check(
            ledger.active_plan is v2 and ledger.pending_intents(as_of=v2.valid_from) != (),
            "ACTIVE_PLAN",
            "新版本未成为活动版本或新版本无可执行意图",
        )
        outcomes.append(f"{as_of:%H:%M}->{kind.name}")
    return (
        "未成交旧建议被覆盖时：半日未结束记 CANCELLED、已到点记 EXPIRED；同版本重复发布抛 "
        f"DUPLICATE_VERSION（{', '.join(outcomes)}）"
    )


def s_filled_intents_protected() -> str:
    """已成交部分受保护：数量以账户快照为准，新版本必须确认上一版动作。"""
    v1_account, v1 = _ledger_v1("rec-fill-v1")
    fill = rec.FillRecord(
        ATTACK_ENTRIES[0], rec.Side.BUY, 900, 10.0, 5.0, dt.datetime(2026, 9, 22, 10, 0)
    )
    filled_positions = (
        position(ATTACK_HOLDING, 2000, rec.Sleeve.ATTACK, 10.0),
        position(ATTACK_CARRIER, 2000, rec.Sleeve.ATTACK, 5.0),
        position(ATTACK_ENTRIES[0], 900, rec.Sleeve.ATTACK, 10.0, sellable=0),
        BOOK[2],
        BOOK[3],
    )
    v2_account = _fill_account(
        "fill-v2",
        as_of=dt.datetime(2026, 9, 22, 11, 0),
        cash=CASH - 9005.0,
        positions=filled_positions,
    )
    v2_attacks = (
        attack_candidate(ATTACK_HOLDING, 0.20, action=rec.Action.ADD, previous=rec.Action.NEW),
        attack_candidate(ATTACK_ENTRIES[0], 0.10, action=rec.Action.ADD, previous=rec.Action.NEW),
        attack_candidate(ATTACK_ENTRIES[1], 0.06, price=20.0, stop=18.0),
    )
    ledger = rec.RecommendationLedger()
    ledger.publish(v1, account=v1_account)
    before_v1 = _fields(v1_account)
    before_fill = _fields(v2_account)
    ledger.record_fills([fill], account=v2_account)
    check(
        any(
            item.symbol == ATTACK_ENTRIES[0]
            for item in ledger.pending_intents(as_of=v1.valid_from)
        ),
        "PARTIAL_FILL_PENDING",
        "部分成交后剩余意图未继续挂单",
    )
    check(
        ledger.account_truth is v1_account
        and _fields(v1_account) == before_v1
        and _fields(v2_account) == before_fill,
        "ACCOUNT_TRUTH",
        "回填成交改动了账户真相，或台账未持有发布时的账户快照对象",
    )
    expect_error(
        "FILL_WITHOUT_INTENT",
        "没有对应意图的成交",
        lambda: ledger.record_fills(
            [
                rec.FillRecord(
                    "600777", rec.Side.BUY, 100, 10.0, 5.0, dt.datetime(2026, 9, 22, 10, 0)
                )
            ],
            account=v2_account,
        ),
    )
    expect_error(
        "FILL_EXCEEDS_INTENT",
        "成交超过建议数量",
        lambda: ledger.record_fills(
            [
                rec.FillRecord(
                    ATTACK_ENTRIES[0],
                    rec.Side.BUY,
                    2000,
                    10.0,
                    5.0,
                    dt.datetime(2026, 9, 22, 10, 0),
                )
            ],
            account=v2_account,
        ),
    )
    expect_error(
        "INVALID_LOT",
        "买入成交不是整手",
        lambda: ledger.record_fills(
            [
                rec.FillRecord(
                    ATTACK_ENTRIES[0], rec.Side.BUY, 50, 10.0, 5.0, dt.datetime(2026, 9, 22, 10, 0)
                )
            ],
            account=v2_account,
        ),
    )
    expect_error(
        "FILL_AFTER_ACCOUNT_SNAPSHOT",
        "成交晚于账户快照",
        lambda: ledger.record_fills(
            [
                rec.FillRecord(
                    ATTACK_ENTRIES[0],
                    rec.Side.BUY,
                    100,
                    10.0,
                    5.0,
                    dt.datetime(2026, 9, 22, 12, 0),
                )
            ],
            account=v2_account,
        ),
    )
    unacknowledged = assemble(
        v2_account,
        "rec-fill-unack",
        overlay_row(ro.C0, rec.DecisionPoint.AM_1130),
        point=rec.DecisionPoint.AM_1130,
        attacks=(
            attack_candidate(ATTACK_HOLDING, 0.20, action=rec.Action.ADD, previous=rec.Action.NEW),
            attack_candidate(ATTACK_ENTRIES[1], 0.06, price=20.0, stop=18.0),
        ),
    )
    expect_error(
        "FILLED_INTENT_NOT_ACKNOWLEDGED",
        "新版本漏掉已成交标的",
        lambda: ledger.publish(unacknowledged, account=v2_account),
    )
    before_publish = _fields(v2_account)
    v2 = assemble(
        v2_account,
        "rec-fill-v2",
        overlay_row(ro.C0, rec.DecisionPoint.AM_1130),
        point=rec.DecisionPoint.AM_1130,
        attacks=v2_attacks,
    )
    report = ledger.publish(v2, account=v2_account)
    outcome = next(o for o in report.outcomes if o.symbol == ATTACK_ENTRIES[0])
    check(
        outcome.kind is rec.IntentOutcomeKind.FILLED_PARTIAL
        and outcome.recommended_quantity == 1800
        and outcome.filled_quantity == 900
        and outcome.account_quantity == 900
        and outcome.protected,
        "FILLED_OUTCOME",
        f"已成交归档不符：{outcome.kind.name} 建议 {outcome.recommended_quantity} 成交 "
        f"{outcome.filled_quantity} 账户 {outcome.account_quantity} 保护 {outcome.protected}",
    )
    check(
        item_of(v2, ATTACK_ENTRIES[0]).previous_action is rec.Action.NEW,
        "PREVIOUS_ACTION",
        "新版本未以 previous_action 接续上一版动作",
    )
    check(
        _fields(v2_account) == before_publish,
        "ACCOUNT_MUTATED_BY_LEDGER",
        "台账把建议写进了账户快照",
    )
    reduced = assemble(
        v2_account,
        "rec-fill-t1",
        overlay_row(ro.C1, rec.DecisionPoint.AM_1130, "reduced"),
        point=rec.DecisionPoint.AM_1130,
        attacks=v2_attacks,
    )
    rec.validate_plan(reduced, account=v2_account)
    t1_item = item_of(reduced, ATTACK_ENTRIES[0])
    check(
        t1_item.action is rec.Action.HOLD
        and t1_item.recommended_quantity == 0
        and "可卖数量不足" in t1_item.change_reason,
        "T1_SELL_ASSUMED",
        f"当日买入份额被当成可卖：{t1_item.action.name} {t1_item.recommended_quantity}",
    )
    return (
        "部分成交 900/1800 以账户快照为准并受保护；漏确认/超额/非整手/串时点成交全部被拒；"
        "T+1 冻结份额的减仓降级为持有"
    )


def s_post_session_unusable() -> str:
    """半日结束后计划不可用：不挂单、不发布，到点归档为 EXPIRED。"""
    account, plan = _ledger_v1("rec-exp")
    check(
        not plan.is_expired(dt.datetime(2026, 9, 22, 10, 0))
        and plan.is_live(dt.datetime(2026, 9, 22, 10, 0)),
        "LIVE_WINDOW",
        "半日内的计划被判定为不可用",
    )
    check(
        plan.is_expired(AM_1130) and not plan.is_live(AM_1130),
        "EXPIRY_BOUNDARY",
        f"valid_until={plan.valid_until} 未按半日边界失效",
    )
    ledger = rec.RecommendationLedger()
    ledger.publish(plan, account=account)
    late = snapshot(
        "rec-exp",
        rec.DecisionPoint.DAY0_CLOSE,
        positions=BOOK,
        as_of=AM_1130,
        market_as_of=DAY0_CLOSE,
    )
    expect_error("PLAN_EXPIRED", "过点发布", lambda: ledger.publish(plan, account=late))
    check(
        ledger.pending_intents(as_of=AM_1130) == (),
        "PENDING_AFTER_EXPIRY",
        "过点后仍报告可挂单意图",
    )
    before = _fields(account)
    expired = ledger.expire(AM_1130)
    check(
        {o.symbol for o in expired} == {item.symbol for item in plan.order_items}
        and all(o.kind is rec.IntentOutcomeKind.EXPIRED for o in expired),
        "EXPIRE_OUTCOMES",
        "到点未把未成交意图全部归档为 EXPIRED",
    )
    check(
        ledger.active_plan is None and ledger.pending_intents() == (),
        "EXPIRED_PLAN_STILL_ACTIVE",
        "到点后版本仍处于活动状态",
    )
    check(
        _fields(ledger.account_truth) == before,
        "ACCOUNT_MUTATED_ON_EXPIRY",
        "到点归档改动了账户真相",
    )
    return (
        f"半日窗口 {plan.valid_from:%H:%M}~{plan.valid_until:%H:%M}：过点发布抛 PLAN_EXPIRED，"
        f"expire() 归档 {len(expired)} 条 EXPIRED 且不动账户"
    )


def s_no_future_data_at_1130() -> str:
    """11:30 决策不使用未来数据：只读上一交易日收盘，后一时段行情影响不了它。"""
    close_row = overlay_row(ro.C1, rec.DecisionPoint.DAY0_CLOSE, "normal")
    am_row = overlay_row(ro.C1, rec.DecisionPoint.AM_1130, "normal")
    check(
        am_row.benchmark_as_of
        == close_row.benchmark_as_of
        == EXPECTED_ASOF[rec.DecisionPoint.DAY0_CLOSE],
        "FUTURE_ASOF",
        f"11:30 行读到 {am_row.benchmark_as_of}，应为前一交易日 "
        f"{EXPECTED_ASOF[rec.DecisionPoint.AM_1130]}",
    )
    check(
        (am_row.risk_state, am_row.exposure_multiplier, am_row.benchmark_sma)
        == (close_row.risk_state, close_row.exposure_multiplier, close_row.benchmark_sma),
        "FUTURE_STATE_DRIFT",
        "11:30 行与前一收盘行状态不一致（它只应重发建议，不移动风控）",
    )
    c2_am = overlay_row(ro.C2, rec.DecisionPoint.AM_1130, "normal")
    check(
        c2_am.equity_as_of == EXPECTED_ASOF[rec.DecisionPoint.AM_1130],
        "FUTURE_ASOF",
        f"C2 的 11:30 行读到权益日 {c2_am.equity_as_of}",
    )
    spike = [(day, 100.0) for day in SESSIONS[:-3]] + [
        (DAY0, 101.0),
        (DAY1, 103.0),
        (DAY2, 20.0),
    ]
    for point in POINTS:
        row = ro.resolve_overlay(
            [POINTS[point][0]],
            config_id=ro.C1,
            decision_points=[point],
            benchmark_close=spike,
        )[0]
        check(
            row.benchmark_as_of == EXPECTED_ASOF[point]
            and row.risk_state is ro.OverlayState.NORMAL
            and row.exposure_multiplier == 0.90,
            "FUTURE_LEAK",
            f"{point.value}: 决策后行情改变了行（asof={row.benchmark_as_of} "
            f"{row.risk_state.name} {row.exposure_multiplier}）",
        )
    late_account = snapshot(
        "future",
        rec.DecisionPoint.PM_1500,
        positions=BOOK,
        as_of=AM_1130,
        market_as_of=PM_1500,
    )
    expect_error(
        "FUTURE_INPUT",
        "行情截止晚于生成时刻",
        lambda: assemble(
            late_account,
            "rec-future",
            overlay_row(ro.C0, rec.DecisionPoint.PM_1500),
            point=rec.DecisionPoint.PM_1500,
            generated_at=AM_1130,
        ),
    )
    for point, expected in (
        (rec.DecisionPoint.AM_1130, (dt.datetime(2026, 9, 22, 13, 0), PM_1500)),
        (
            rec.DecisionPoint.PM_1500,
            (dt.datetime(2026, 9, 23, 9, 30), dt.datetime(2026, 9, 23, 11, 30)),
        ),
    ):
        account, plan = build_case(point, overlay_row(ro.C0, point), f"rec-win-{point.value}")
        rec.validate_plan(plan, account=account)
        check(
            (plan.valid_from, plan.valid_until) == expected
            and plan.market_as_of == POINTS[point][0],
            "WRONG_SESSION_WINDOW",
            f"{point.value}: 窗口 {plan.valid_from}~{plan.valid_until} 行情截止 "
            f"{plan.market_as_of}",
        )
    return (
        "11:30 行的 asof/状态/系数与前一收盘行逐字段相同；注入 DAY2=20 的决策后极端收盘不改变"
        "任何决策点；行情截止晚于生成时刻抛 FUTURE_INPUT；11:30 版只服务当日午盘"
    )


def s_unfilled_keeps_account() -> str:
    """未成交订单不动现金、持仓与建议数量；建议层与账户真相分离。"""
    account, plan = build_case(
        rec.DecisionPoint.DAY0_CLOSE,
        overlay_row(ro.C1, rec.DecisionPoint.DAY0_CLOSE, "reduced"),
        "rec-inv",
    )
    exposure = rec.validate_plan(plan, account=account)
    before = _fields(account)
    check(
        (plan.cash, plan.equity) == (account.cash, account.equity),
        "PLAN_HEADER_DRIFT",
        f"版本现金/权益 {plan.cash}/{plan.equity} != 账户 {account.cash}/{account.equity}",
    )
    ledger = rec.RecommendationLedger()
    ledger.publish(plan, account=account)
    pending = ledger.pending_intents(as_of=plan.valid_from)
    check(
        tuple(item.symbol for item in pending) == tuple(item.symbol for item in plan.order_items),
        "PENDING_MISMATCH",
        "挂单意图与订单条目不一致",
    )
    check(
        _fields(account) == before and ledger.account_truth is account,
        "ACCOUNT_MUTATED_BY_UNFILLED",
        "未成交订单改动了账户快照",
    )
    buys = [item for item in plan.order_items if item.action in rec.BUY_ACTIONS]
    sells = [item for item in plan.order_items if item.action in rec.SELL_ACTIONS]
    check(
        bool(buys) and bool(sells),
        "NO_ORDER_ITEMS",
        f"降仓臂未同时产生买单与减仓：{[(i.symbol, i.action.name) for i in plan.order_items]}",
    )
    cash_out = 0.0
    for item in buys:
        limit = item.price_upper or 0.0
        held = account.position(item.symbol)
        held_qty = 0 if held is None else held.quantity
        check(
            abs(
                (held_qty + item.recommended_quantity) * limit
                - item.target_weight * plan.equity
            )
            < LOT * limit,
            "BUY_TARGET_MISMATCH",
            f"{item.symbol}: 订单后数量 {(held_qty + item.recommended_quantity) * limit} "
            f"与目标权重 {item.target_weight * plan.equity} 不一致",
        )
        cash_out += item.recommended_quantity * limit + rec.estimate_fees(
            rec.Side.BUY,
            item.recommended_quantity,
            limit,
            sleeve=item.sleeve,
            trade_date=plan.valid_from.date(),
        )
    near(cash_out, exposure.buy_notional + exposure.buy_fees, "BUY_COST_MIRROR", "买单成本重算")
    check(
        cash_out <= plan.cash + TOL,
        "INSUFFICIENT_CASH",
        f"买单成本 {cash_out} 超过现金 {plan.cash}",
    )
    cash_in = 0.0
    for item in sells:
        held = account.position(item.symbol)
        check(
            held is not None and item.recommended_quantity <= held.sellable_quantity,
            "SELLABLE_QUANTITY_EXCEEDED",
            f"{item.symbol}: 卖出 {item.recommended_quantity} 超过可卖 "
            f"{0 if held is None else held.sellable_quantity}",
        )
        assert held is not None
        check(
            abs(
                (held.quantity - item.recommended_quantity) * held.last_price
                - item.target_weight * plan.equity
            )
            < LOT * held.last_price,
            "SELL_TARGET_MISMATCH",
            f"{item.symbol}: 减仓后剩 {held.quantity - item.recommended_quantity} 股与目标权重 "
            f"{item.target_weight} 不一致",
        )
        check(
            item.target_weight < held.weight(plan.equity),
            "SELL_NOT_REDUCING",
            f"{item.symbol}: 减仓目标未低于已持权重",
        )
        cash_in += item.recommended_quantity * (item.price_lower or 0.0)
    check(
        plan.cash - cash_out + cash_in >= -TOL,
        "NEGATIVE_CASH",
        f"全部成交后现金为负：{plan.cash} - {cash_out} + {cash_in}",
    )
    return (
        f"发布后账户快照逐字段不变（现金 {account.cash:.2f}），挂单 {len(pending)} 条；"
        f"买单最坏成本 {cash_out:.2f} 与核算一致且不超现金，减仓 {sells[0].symbol} "
        f"{sells[0].recommended_quantity} 股不超过可卖数量"
    )


def s_fee_reserve() -> str:
    """费用预留：预算不足不加仓，验证层独立拒绝透支的版本。"""
    point = rec.DecisionPoint.DAY0_CLOSE
    row = overlay_row(ro.C0, point)
    attack = attack_candidate("600036", 0.05)
    cheap_account, cheap = build_case(
        point, row, "rec-fee-cheap", positions=(), cash=9003.0, attacks=(attack,), defenses=()
    )
    check(
        cheap.items == () and note_symbols(cheap, sp.CASH_EXHAUSTED) == ("600036",),
        "CASH_EXHAUSTED_NOT_DISCLOSED",
        f"现金 9003 时仍下单或未披露：{[(i.symbol, i.action.name) for i in cheap.items]}",
    )
    check(
        cheap.cash == cheap_account.cash,
        "PLAN_HEADER_DRIFT",
        "被压掉的买单改动了版本现金",
    )
    exact_account, exact = build_case(
        point, row, "rec-fee-exact", positions=(), cash=9005.0, attacks=(attack,), defenses=()
    )
    item = item_of(exact, "600036")
    exposure = rec.validate_plan(exact, account=exact_account)
    check(
        item.recommended_quantity == 900 and exposure.buy_fees > 0.0,
        "FEE_NOT_RESERVED",
        f"恰好够用的现金未计入费用：数量 {item.recommended_quantity} 费用 {exposure.buy_fees}",
    )
    check(
        exposure.buy_notional + exposure.buy_fees <= exact.cash + TOL,
        "INSUFFICIENT_CASH",
        "恰好够用时仍超出预算",
    )
    identity = rec.PlanIdentity(
        exact.strategy_version, exact.market_as_of, exact.account_snapshot_version
    )
    overdraft = rec.build_plan(
        decision_point=point,
        generated_at=exact.generated_at,
        identity=identity,
        account=exact_account,
        recommendation_version="rec-fee-overdraft",
        valid_from=exact.valid_from,
        valid_until=exact.valid_until,
        items=(item,),
    )
    check(
        rec.validate_plan(overdraft, account=exact_account).ok,
        "CONTROL_PLAN_INVALID",
        "恰好够用的版本未通过独立校验",
    )
    one_yuan_short = dataclasses.replace(exact_account, cash=9004.0)
    expect_error(
        "INSUFFICIENT_CASH",
        "现金少 1 元的同一版本",
        lambda: rec.validate_plan(
            dataclasses.replace(overdraft, cash=9004.0), account=one_yuan_short
        ),
    )
    return (
        "现金 9003 -> cash_exhausted 且不下单；现金 9005 -> 900 股（9000 名义 + 5 元费用）通过；"
        "同一版本放到 9004 元账户上被 INSUFFICIENT_CASH 拒绝"
    )


def s_limits() -> str:
    """注册上限：25% 单标的、4/3/7 席位、100% 总仓位、3 个新开与整手。"""
    point = rec.DecisionPoint.DAY0_CLOSE
    row = overlay_row(ro.C0, point)
    empty = snapshot("lim", point, positions=(), cash=200_000.0)
    over = assemble(
        empty,
        "rec-lim-over",
        row,
        point=point,
        attacks=(attack_candidate("600036", 0.30),),
        defenses=(),
    )
    check(
        over.item("600036") is None
        and note_symbols(over, sp.WEIGHT_CAP_VOIDED) == ("600036",),
        "OVER_CAP_NOT_VOIDED",
        "单标的超过 25% 的买单未被整笔作废并披露",
    )
    rec.validate_plan(over, account=empty)
    five = tuple(attack_candidate(f"6001{i:02d}", 0.02) for i in range(5))
    capped = assemble(empty, "rec-lim-new", row, point=point, attacks=five, defenses=())
    rec.validate_plan(capped, account=empty)
    check(
        len(capped.new_entry_items) == NEW_ENTRY_CAP
        and set(note_symbols(capped, sp.NEW_ENTRY_CAP_VOIDED)) == {"600103", "600104"},
        "NEW_ENTRY_CAP",
        f"新开上限未生效：{len(capped.new_entry_items)} 个新开，作废 "
        f"{note_symbols(capped, sp.NEW_ENTRY_CAP_VOIDED)}",
    )
    sub_lot = assemble(
        empty,
        "rec-lim-lot",
        row,
        point=point,
        attacks=(attack_candidate("600036", 0.0045, price=900.0),),
        defenses=(),
    )
    check(
        sub_lot.items == () and note_symbols(sub_lot, sp.SUB_LOT_SKIPPED) == ("600036",),
        "SUB_LOT_NOT_SKIPPED",
        "不足一手的候选未被跳过并披露",
    )
    attack_slots = snapshot(
        "lim-a",
        point,
        positions=tuple(
            position(f"60000{i}", 2000, rec.Sleeve.ATTACK, 10.0) for i in range(5)
        ),
        cash=200_000.0,
    )
    expect_error(
        "ATTACK_SLOT_LIMIT",
        "5 个进攻标的",
        lambda: assemble(attack_slots, "rec-lim-a", row, point=point, attacks=(), defenses=()),
    )
    defense_slots = snapshot(
        "lim-d",
        point,
        positions=tuple(
            position(f"51{i:04d}", 2000, rec.Sleeve.DEFENSE, 10.0) for i in range(4)
        ),
        cash=200_000.0,
    )
    expect_error(
        "DEFENSE_SLOT_LIMIT",
        "4 个防御标的",
        lambda: assemble(defense_slots, "rec-lim-d", row, point=point, attacks=(), defenses=()),
    )
    gross = snapshot(
        "lim-g",
        point,
        positions=tuple(
            position(f"60000{i}", 4800, rec.Sleeve.ATTACK, 10.0) for i in range(4)
        )
        + (position("511010", 2000, rec.Sleeve.DEFENSE, 10.0),),
        cash=200_000.0,
    )
    expect_error(
        "GROSS_EXPOSURE_LIMIT",
        "总仓位 106%",
        lambda: assemble(gross, "rec-lim-g", row, point=point, attacks=(), defenses=()),
    )
    drifted = snapshot(
        "lim-s",
        point,
        positions=(position("600000", 6000, rec.Sleeve.ATTACK, 10.0),),
        cash=200_000.0,
    )
    expect_error(
        "SYMBOL_WEIGHT_LIMIT",
        "漂移到 30% 且无候选的持仓",
        lambda: assemble(drifted, "rec-lim-s", row, point=point, attacks=(), defenses=()),
    )
    legal = assemble(
        drifted,
        "rec-lim-rescale",
        row,
        point=point,
        attacks=(
            attack_candidate("600000", 0.20, action=rec.Action.REDUCE, previous=rec.Action.HOLD),
        ),
        defenses=(),
    )
    rescale = item_of(legal, "600000")
    check(
        rescale.action is rec.Action.REDUCE
        and rescale.recommended_quantity == 6000 - 3600
        and rescale.target_weight < LIMITS["symbol"],
        "RESCALE_NOT_HONOURED",
        f"显式减仓未把漂移持仓压回上限内：{rescale.action.name} "
        f"{rescale.recommended_quantity}@{rescale.target_weight}",
    )
    check(
        rec.validate_plan(legal, account=drifted).ok,
        "RESCALE_PLAN_INVALID",
        "显式减仓版本未通过校验",
    )
    return (
        "30% 新开被整笔作废（weight_cap_voided）、第 4 个新开被作废（new_entry_cap_voided）、"
        "不足一手被跳过；5 进攻/4 防御/106% 总仓位/30% 单标的分别抛 "
        "ATTACK_SLOT_LIMIT/DEFENSE_SLOT_LIMIT/GROSS_EXPOSURE_LIMIT/SYMBOL_WEIGHT_LIMIT；"
        "显式减仓可把漂移持仓压回上限"
    )


def s_identity_freshness() -> str:
    """身份与新鲜度失败关闭：错身份、错半日、过期、陈旧数据都拒绝而不是降级。"""
    point = rec.DecisionPoint.DAY0_CLOSE
    row = overlay_row(ro.C0, point)
    account, plan = build_case(point, row, "rec-id")
    rec.validate_plan(plan, account=account)
    for label, mutated in (
        ("策略版本", dataclasses.replace(plan, strategy_version="other-strategy")),
        ("行情截止", dataclasses.replace(plan, market_as_of=AM_1130)),
        ("账户快照版本", dataclasses.replace(plan, account_snapshot_version="other-account")),
        ("权益", dataclasses.replace(plan, equity=EQUITY + 1.0)),
        ("现金", dataclasses.replace(plan, cash=CASH + 1.0)),
    ):
        expect_error(
            {
                "策略版本": "STRATEGY_VERSION_MISMATCH",
                "行情截止": "MARKET_AS_OF_MISMATCH",
                "账户快照版本": "ACCOUNT_SNAPSHOT_MISMATCH",
                "权益": "EQUITY_MISMATCH",
                "现金": "CASH_MISMATCH",
            }[label],
            f"{label}不一致",
            lambda mutated=mutated: rec.validate_plan(mutated, account=account),
        )
    beyond = dataclasses.replace(
        plan,
        items=tuple(
            dataclasses.replace(item, valid_until=plan.valid_until + dt.timedelta(hours=1))
            for item in plan.items
        ),
    )
    expect_error(
        "INVALID_FIELD",
        "条目有效期越出半日",
        lambda: rec.validate_plan(beyond, account=account),
    )
    expect_error(
        "MISSING_POSITION_ITEM",
        "持仓缺少条目",
        lambda: rec.validate_plan(
            dataclasses.replace(plan, items=plan.items[:-1]), account=account
        ),
    )
    expect_error(
        "DUPLICATE_SYMBOL",
        "同标的重复条目",
        lambda: rec.validate_plan(
            dataclasses.replace(plan, items=plan.items + (plan.items[0],)), account=account
        ),
    )
    expect_error(
        "OVERLAY_MARKET_MISMATCH",
        "风控行不属于本决策点",
        lambda: assemble(
            account,
            "rec-id-ovl",
            overlay_row(ro.C0, rec.DecisionPoint.AM_1130),
            point=point,
        ),
    )
    expect_error(
        "DECISION_TIME_MISMATCH",
        "风控行不属于本交易日",
        lambda: sp.assemble_plan(
            decision_point=point,
            trading_day=DAY1,
            generated_at=DAY0_CLOSE,
            account=account,
            overlay=row,
            recommendation_version="rec-id-day",
        ),
    )
    expect_error(
        "MARKET_DATA_STALE",
        "行情陈旧 7 小时",
        lambda: assemble(
            account,
            "rec-id-stale",
            row,
            point=point,
            generated_at=DAY0_CLOSE + dt.timedelta(hours=7),
        ),
    )
    expect_error(
        "ACCOUNT_SNAPSHOT_STALE",
        "账户快照陈旧 7 小时",
        lambda: assemble(
            snapshot(
                "stale-account",
                point,
                positions=BOOK,
                as_of=DAY0_CLOSE - dt.timedelta(hours=7),
            ),
            "rec-id-stale-account",
            row,
            point=point,
        ),
    )
    expect_error(
        "PLAN_EXPIRED",
        "生成时刻等于半日结束",
        lambda: assemble(
            snapshot("expired-build", point, positions=BOOK, as_of=dt.datetime(2026, 9, 22, 0, 0)),
            "rec-id-expired",
            row,
            point=point,
            generated_at=dt.datetime(2026, 9, 22, 11, 30),
        ),
    )
    expect_error(
        "MISSING_NEXT_SESSION",
        "Day0 收盘缺失下一交易日",
        lambda: rec.session_window(rec.DecisionPoint.DAY0_CLOSE, trading_day=DAY0),
    )
    return (
        "策略/行情/快照/权益/现金错身份、条目越窗、缺条目、重复标的、错决策点行、错交易日行、"
        "行情与账户陈旧、过期生成、缺下一交易日：全部按注册原因代码拒绝"
    )


# --------------------------------------------------------------------------- #
# 剧本登记与契约条款
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Outcome:
    """一个剧本的结论：``ok`` 与稳定原因代码（``OK`` 表示通过）。"""

    name: str
    ok: bool
    code: str
    detail: str

    def to_mapping(self) -> dict[str, Any]:
        return {
            "scenario": self.name,
            "ok": self.ok,
            "code": self.code,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Scenario:
    name: str
    criteria: tuple[str, ...]
    run: Callable[[], str]


#: 契约条款 -> 人话标题。集成测试逐条对应一份。
CRITERION_TITLES = {
    "configs": "三个决策点 × 三个固定风险配置的完整链路",
    "scaling": "风险降档只缩进攻袖套，防御底盘不缩放、不被删",
    "entry_gate": "缺失数据/禁止新增时失败关闭，且闸门按袖套分治",
    "supersede": "新版本覆盖未成交旧建议，已成交部分受保护且以账户快照为准",
    "window": "半日有效期与过期不可用，11:30 不使用未来数据",
    "invariance": "未成交订单不动现金/持仓/建议数量，费用预留不出现负现金",
    "limits": "25%/4/3/7/100%/3 新开与身份、新鲜度失败关闭",
}

SCENARIOS: tuple[Scenario, ...] = (
    Scenario("frozen_configs", ("configs",), s_frozen_configs),
    Scenario("matrix", ("configs", "scaling"), s_matrix),
    Scenario("attack_scaling_only", ("scaling",), s_attack_scaling_only),
    Scenario("insufficient_data_blocks_entries", ("entry_gate",), s_insufficient_data_blocks_entries),
    Scenario("entry_gate_attack_scoped", ("entry_gate",), s_entry_gate_attack_scoped),
    Scenario("supersede_unfilled_intents", ("supersede",), s_supersede_unfilled_intents),
    Scenario("filled_intents_protected", ("supersede", "invariance"), s_filled_intents_protected),
    Scenario("post_session_unusable", ("window",), s_post_session_unusable),
    Scenario("no_future_data_at_1130", ("window",), s_no_future_data_at_1130),
    Scenario("unfilled_keeps_account", ("invariance",), s_unfilled_keeps_account),
    Scenario("fee_reserve", ("invariance", "limits"), s_fee_reserve),
    Scenario("limits", ("limits",), s_limits),
    Scenario("identity_freshness", ("limits",), s_identity_freshness),
)
SCENARIO_NAMES = tuple(scenario.name for scenario in SCENARIOS)
CRITERIA = {
    key: tuple(scenario.name for scenario in SCENARIOS if key in scenario.criteria)
    for key in CRITERION_TITLES
}
_BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}


def run_scenario(name: str) -> Outcome:
    """跑一个剧本；领域错误与意外异常都收敛成 ``Outcome``，不向调用方抛。"""
    scenario = _BY_NAME[name]
    before = _ASSERTIONS
    try:
        detail = scenario.run()
    except SmokeFailure as exc:
        return Outcome(name, False, exc.code, exc.detail)
    except Exception as exc:  # 任何非 SmokeFailure 的异常都是契约外行为
        return Outcome(name, False, "UNEXPECTED_EXCEPTION", f"{type(exc).__name__}: {exc}")
    return Outcome(name, True, "OK", f"{detail}（断言 {_ASSERTIONS - before} 条）")


def run_all(names: Sequence[str] | None = None) -> list[Outcome]:
    return [run_scenario(name) for name in (names or SCENARIO_NAMES)]


def check_modules() -> tuple[tuple[str, str], ...]:
    """三个模块必须解析到仓库 ``src/`` 下的当前源码（防旧 wheel 静默通过）。"""
    resolved: list[tuple[str, str]] = []
    root = SRC.resolve()
    for module in MODULES:
        path = Path(module.__file__).resolve()
        check(
            root in path.parents,
            "STALE_MODULE_SOURCE",
            f"{module.__name__} 解析到 {path}，不是仓库 src/ 下的当前源码",
        )
        resolved.append((module.__name__, str(path)))
    return tuple(resolved)


def _output_path(raw: str) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    path = path.resolve()
    artifacts = (REPO_ROOT / "artifacts").resolve()
    if path == artifacts or artifacts in path.parents:
        raise SmokeFailure(
            "ARTIFACT_OVERWRITE_REFUSED",
            f"{path} 落在 artifacts/ 下：冒烟不碰历史产物，请换一个目录",
        )
    if path.exists():
        raise SmokeFailure("OUTPUT_EXISTS", f"{path} 已存在：冒烟只新增、不覆盖")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="portfolio_contract_smoke",
        description="组合层契约集成冒烟（合成数据，不读行情/账户/网络）",
    )
    parser.add_argument("--only", action="append", default=[], metavar="NAME", help="只跑指定剧本（可重复）")
    parser.add_argument("--list", action="store_true", help="列出剧本与契约条款")
    parser.add_argument("--out", metavar="PATH", help="额外写一份 JSON 报告（拒绝 artifacts/ 与覆盖）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list:
        print("剧本：")
        for scenario in SCENARIOS:
            print(f"  {scenario.name:34s} {'/'.join(scenario.criteria)}")
        print("契约条款：")
        for key, title in CRITERION_TITLES.items():
            print(f"  {key:10s} {title} -> {', '.join(CRITERIA[key])}")
        return 0

    selected = SCENARIO_NAMES if not args.only else tuple(args.only)
    unknown = [name for name in selected if name not in _BY_NAME]
    if unknown:
        print(f"未知剧本 {unknown}；可用：{list(SCENARIO_NAMES)}")
        return 2

    print("组合层契约冒烟（合成数据；不读行情/账户/网络，默认不写文件）")
    print(f"仓库: {REPO_ROOT}")
    try:
        sources = check_modules()
    except SmokeFailure as exc:
        print(f"FAIL modules [{exc.code}] {exc.detail}")
        return 1
    for name, path in sources:
        print(f"  源码: {name} -> {path}")
    print(
        f"合成日历: {SESSIONS[0]} ~ {SESSIONS[-1]}（{len(SESSIONS)} 个 weekday，全部现造）"
    )
    print(f"合成账户: 权益 {EQUITY:,.0f} 元，现金 {CASH:,.0f} 元，持仓 {len(BOOK)} 只")
    print("-" * 88)
    outcomes = run_all(selected)
    for outcome in outcomes:
        print(
            f"{'PASS' if outcome.ok else 'FAIL'} {outcome.name:34s} "
            f"[{outcome.code}] {outcome.detail}"
        )
    print("-" * 88)
    failed = [outcome for outcome in outcomes if not outcome.ok]
    print(f"剧本 {len(outcomes) - len(failed)}/{len(outcomes)} 通过，断言 {_ASSERTIONS} 条")
    if args.out:
        try:
            path = _output_path(args.out)
        except SmokeFailure as exc:
            print(f"FAIL report [{exc.code}] {exc.detail}")
            return 1
        payload = {
            "synthetic": True,
            "repo_root": str(REPO_ROOT),
            "modules": {name: path for name, path in sources},
            "sessions": [SESSIONS[0].isoformat(), SESSIONS[-1].isoformat()],
            "assertions": _ASSERTIONS,
            "passed": len(outcomes) - len(failed),
            "total": len(outcomes),
            "scenarios": [outcome.to_mapping() for outcome in outcomes],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"报告: {path}")
    return 1 if failed else 0


# --------------------------------------------------------------------------- #
# 集成测试入口（pytest 直接收集本文件）
# --------------------------------------------------------------------------- #
def _assert_scenarios(names: Sequence[str]) -> None:
    failures = [
        f"{outcome.name} [{outcome.code}] {outcome.detail}"
        for outcome in run_all(names)
        if not outcome.ok
    ]
    assert not failures, "；".join(failures)


def test_module_source_is_current() -> None:
    check_modules()


def test_all_scenarios() -> None:
    _assert_scenarios(SCENARIO_NAMES)


def test_criterion_decision_points_and_configs() -> None:
    _assert_scenarios(CRITERIA["configs"])


def test_criterion_attack_scaling_only() -> None:
    _assert_scenarios(CRITERIA["scaling"])


def test_criterion_entry_gate_fail_closed() -> None:
    _assert_scenarios(CRITERIA["entry_gate"])


def test_criterion_version_supersede_and_protection() -> None:
    _assert_scenarios(CRITERIA["supersede"])


def test_criterion_session_window_and_expiry() -> None:
    _assert_scenarios(CRITERIA["window"])


def test_criterion_cash_and_position_invariance() -> None:
    _assert_scenarios(CRITERIA["invariance"])


def test_criterion_limits_and_identity_fail_closed() -> None:
    _assert_scenarios(CRITERIA["limits"])


def test_registry_covers_every_clause() -> None:
    check(
        set(CRITERIA) == set(CRITERION_TITLES),
        "REGISTRY_MISMATCH",
        "契约条款集合与剧本登记不一致",
    )
    covered = {name for names in CRITERIA.values() for name in names}
    check(
        covered == set(SCENARIO_NAMES) and all(CRITERIA.values()),
        "REGISTRY_COVERAGE",
        f"未被任何条款引用的剧本：{sorted(set(SCENARIO_NAMES) - covered)}",
    )


def test_cli_reports_pass_to_stdout(capsys: Any) -> None:
    assert main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    check(
        "剧本 13/13 通过" in "\n".join(lines)
        and not any(line.startswith("FAIL ") for line in lines),
        "CLI_REPORT",
        "命令行报告未全部通过或存在 FAIL 行",
    )
    check(
        sum(1 for line in lines if line.startswith("PASS ")) == len(SCENARIO_NAMES),
        "CLI_REPORT",
        f"PASS 行数不等于剧本数 {len(SCENARIO_NAMES)}",
    )


def test_cli_rejects_unknown_scenario() -> None:
    check(main(["--only", "no_such_scenario"]) == 2, "CLI_UNKNOWN", "未知剧本未返回退出码 2")


if __name__ == "__main__":
    raise SystemExit(main())
