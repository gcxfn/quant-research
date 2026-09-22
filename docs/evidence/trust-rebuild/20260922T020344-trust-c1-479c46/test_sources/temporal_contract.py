"""时间四件套与标签窗合同（C1 冻结接口，纯函数）。

主计划第 6 节要求每个数据表至少有 ``event_at / available_at /
label_end_at`` 加决策点 ``decision_at``，并且决策可用性必须满足

    available_at <= decision_at < live_from

只有披露日期、没有时分时，沿既有保守时钟：公告当日收盘后视为可得，
下一交易日 11:30 是最早决策点，下一交易日下午才可生效。

本模块只用标准库，不导入行情/研究代码，便于 C2/C3 独立实现直接复用。
窗口语义与 ``quant.research.attribution_lib.tr_window``（v2 边界感知口径）
一致：固定 20 个自身交易日、显式终点、跨 Dev 边界标不完整；差异点在于
本模块同时给出固定市场交易日口径 ``n_market_sessions``，两者不得混同。
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Mapping, Sequence

SESSIONS: tuple[str, str] = ("am", "pm")
_SESSION_INDEX = {"am": 0, "pm": 1}
DEV_END_DEFAULT = date(2020, 12, 31)
LABEL_SESSIONS_DEFAULT = 20


class TemporalContractError(ValueError):
    """时间关系被违反，例如 ``available_at`` 晚于 ``decision_at``。"""


class NullTimeError(TemporalContractError):
    """时间字段为空；禁止回填为运行当天或任何其他默认值。"""


@dataclass(frozen=True, order=True)
class HalfDay:
    """一个半日时点；(day, session) 的升序即为时间序（am 早于 pm）。"""

    day: date
    session: str

    def __post_init__(self) -> None:
        if self.session not in _SESSION_INDEX:
            raise TemporalContractError(f"unknown session: {self.session!r}")
        if not isinstance(self.day, date):
            raise TemporalContractError(f"day must be datetime.date, got {type(self.day)!r}")

    def iso(self) -> str:
        return f"{self.day.isoformat()}T{self.session}"


# --------------------------------------------------------------------------- #
# 时间四件套
# --------------------------------------------------------------------------- #
def require_time(value: object, field_name: str) -> object:
    """空时间字段直接报错，绝不落到当天。

    ``None``、空字符串与纯空白都视为空值；禁止 ``or date.today()`` 之类回填。
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise NullTimeError(
            f"{field_name} is null; null times must never default to today")
    return value


def assert_available_not_after_decision(
    available_at: HalfDay, decision_at: HalfDay, *, subject: str = ""
) -> bool:
    if not available_at <= decision_at:
        raise TemporalContractError(
            f"{subject} available_at={available_at.iso()} is after "
            f"decision_at={decision_at.iso()} (future information at the decision point)"
        )
    return True


def assert_decision_before_live(
    decision_at: HalfDay, live_from: HalfDay, *, subject: str = ""
) -> bool:
    if not decision_at < live_from:
        raise TemporalContractError(
            f"{subject} decision_at={decision_at.iso()} is not strictly before "
            f"live_from={live_from.iso()} (an order cannot trade in the decision half-day)"
        )
    return True


def assert_time_triplet(
    available_at: HalfDay, decision_at: HalfDay, live_from: HalfDay, *, subject: str = ""
) -> bool:
    """冻结断言：``available_at <= decision_at < live_from``。"""
    assert_available_not_after_decision(available_at, decision_at, subject=subject)
    assert_decision_before_live(decision_at, live_from, subject=subject)
    return True


def conservative_clock(ann_date: date | None, calendar: Sequence[date]) -> dict | None:
    """只有公告日期时的保守时钟。

    返回 ``{'available_at','decision_at','live_from'}``；若公告日期已到
    日历末端（没有下一个交易日）返回 ``None``（该行落在评估窗之外）。
    公告日期为空时抛 ``NullTimeError``，不默认成当天。
    """
    require_time(ann_date, "ann_date")
    assert isinstance(ann_date, date)
    i = bisect_right(calendar, ann_date)
    if i >= len(calendar):
        return None
    nxt = calendar[i]
    return {
        "available_at": HalfDay(ann_date, "pm"),
        "decision_at": HalfDay(nxt, "am"),
        "live_from": HalfDay(nxt, "pm"),
    }


# --------------------------------------------------------------------------- #
# 标签窗口（固定自身交易日 + 显式终点 + 边界标记）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LabelWindow:
    anchor_date: date | None
    label_end_at: date | None
    n_own_sessions: int
    n_market_sessions: int | None
    window_complete: bool
    crosses_dev_boundary: bool
    missing_reason: str | None


def own_session_label_window(
    own_dates: Sequence[date],
    anchor: date | None,
    n_sessions: int = LABEL_SESSIONS_DEFAULT,
    *,
    dev_end: date = DEV_END_DEFAULT,
    market_calendar: Sequence[date] | None = None,
    panel_truncated_at: date | None = None,
) -> LabelWindow:
    """锚定日收盘起 ``n_sessions`` 个自身交易日的收益窗边界。

    ``own_dates`` 为该证券升序的自身可评价交易日（停牌日不一定有行）。
    锚定日停牌时沿 ``tr_window`` 口径取锚定日前最后一个自身交易日。
    ``window_complete`` 同时要求窗内自身交易日足额且终点不晚于 ``dev_end``：
    跨 Dev 边界的窗口保留、标记，但不进入完整窗口均值。

    ``panel_truncated_at``：当被喂进来的显然只是"在 Dev 边界处被截断"的
    自身交易日列表（证券在 Dev 末端仍在交易）时传该日期；此时窗口不足额
    即意味着窗口终点落在 Dev 之后，标 ``crosses_dev_boundary=True``。
    证券在 Dev 内退市/终止（补充数据里也确实没有后续报价）时传 ``None``，
    窗口不足额标 ``ended_by_panel_end``。二者都不完整，但归因不同，
    且都禁止用后来年份报价强行结算。
    """
    require_time(anchor, "anchor")
    assert isinstance(anchor, date)
    if n_sessions <= 0:
        raise TemporalContractError("n_sessions must be positive")
    ordinals = sorted(d.toordinal() for d in own_dates)
    if not ordinals:
        return LabelWindow(None, None, 0, None, False, False, "no_own_panel")
    a0 = anchor.toordinal()
    i = bisect_left(ordinals, a0)
    if i >= len(ordinals) or ordinals[i] != a0:
        i -= 1
    if i < 0:
        return LabelWindow(None, None, 0, None, False, False, "anchor_before_panel")
    anchor_eff = date.fromordinal(ordinals[i])
    j = i + n_sessions
    if j >= len(ordinals):
        if panel_truncated_at is not None and panel_truncated_at >= anchor_eff:
            return LabelWindow(anchor_eff, None, len(ordinals) - i - 1, None,
                               False, True, "crosses_dev_boundary")
        return LabelWindow(anchor_eff, None, len(ordinals) - i - 1, None, False,
                           False, "ended_by_panel_end")
    end = date.fromordinal(ordinals[j])
    n_market = None
    if market_calendar is not None:
        lo = bisect_right(market_calendar, anchor_eff)
        hi = bisect_right(market_calendar, end)
        n_market = hi - lo
    return LabelWindow(
        anchor_date=anchor_eff,
        label_end_at=end,
        n_own_sessions=n_sessions,
        n_market_sessions=n_market,
        window_complete=end <= dev_end,
        crosses_dev_boundary=end > dev_end,
        missing_reason=None,
    )


def complete_window_stats(
    values: Sequence[float | None],
    windows: Sequence[LabelWindow],
) -> dict:
    """只统计完整窗口；右删失窗口保留计数、不混入均值。"""
    if len(values) != len(windows):
        raise TemporalContractError("values and windows must have equal length")
    complete = [v for v, w in zip(values, windows)
                if w.window_complete and v is not None]
    censored = [w for w in windows if not w.window_complete]
    out: dict = {
        "n_total": len(windows),
        "n_complete": len(complete),
        "n_censored": len(censored),
        "n_complete_with_value": len(complete),
    }
    if complete:
        s = sorted(complete)
        mid = len(s) // 2
        median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0
        out.update(mean=sum(complete) / len(complete), median=median,
                   win_rate=sum(1 for v in complete if v > 0) / len(complete))
    else:
        out.update(mean=None, median=None, win_rate=None)
    return out


# --------------------------------------------------------------------------- #
# 预告区间与版本合法性
# --------------------------------------------------------------------------- #
INTERVAL_MISSING = "missing"
INTERVAL_POINT = "point"
INTERVAL_VALID = "valid"
INTERVAL_INVALID = "invalid"


def _as_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def classify_forecast_interval(min_value: object, max_value: object) -> str:
    """业绩预告净利润区间分类。

    ``min==max`` 是合法的点预测（``point``），不是错误；
    ``min>max`` 才是非法区间（``invalid``）。不能把两者一起丢掉。
    """
    lo = _as_float(min_value)
    hi = _as_float(max_value)
    if lo is None or hi is None:
        return INTERVAL_MISSING
    if lo > hi:
        return INTERVAL_INVALID
    if lo == hi:
        return INTERVAL_POINT
    return INTERVAL_VALID


@dataclass(frozen=True)
class AnnouncementVersion:
    """同 (ts_code, end_date) 的一条公告版本。"""

    ts_code: str
    end_date: str
    ann_date: str
    update_flag: str
    type_value: str = ""
    net_profit_min: float | None = None
    net_profit_max: float | None = None
    interval_class: str = INTERVAL_MISSING

    def version_key(self) -> tuple[str, str]:
        return (self.ann_date, self.update_flag or "0")


def version_chain(
    rows: Iterable[Mapping[str, object]],
) -> tuple[list[AnnouncementVersion], dict]:
    """把预告行整理成逐 (ts_code, end_date) 的版本链。

    - ``ann_date`` 为空的行 fail-closed 丢弃并计数（不回填当天）；
    - 同一 ``(ann_date, update_flag)`` 的完全重复行视为取数重复，保留首行并计数；
    - 按 ``(ann_date, update_flag)`` 升序排序，得到当时的版本顺序；
      不使用 vendor 的最终版回写早期版本。
    """
    stats = {
        "rows_in": 0,
        "dropped_missing_ann_date": 0,
        "dropped_exact_duplicate_rows": 0,
        "groups": 0,
        "groups_with_multiple_versions": 0,
        "interval_point": 0,
        "interval_valid": 0,
        "interval_invalid": 0,
        "interval_missing": 0,
    }
    grouped: dict[tuple[str, str], list[AnnouncementVersion]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        stats["rows_in"] += 1
        ann_date = row.get("ann_date")
        if ann_date is None or ann_date == "":
            stats["dropped_missing_ann_date"] += 1
            continue
        code = str(row.get("ts_code", ""))
        end_date = str(row.get("end_date", ""))
        flag = str(row.get("update_flag") or "0")
        dedupe_key = (code, end_date, str(ann_date), flag)
        if dedupe_key in seen:
            stats["dropped_exact_duplicate_rows"] += 1
            continue
        seen.add(dedupe_key)
        klass = classify_forecast_interval(row.get("net_profit_min"),
                                           row.get("net_profit_max"))
        stats[f"interval_{klass}"] += 1
        version = AnnouncementVersion(
            ts_code=code, end_date=end_date, ann_date=str(ann_date),
            update_flag=flag, type_value=str(row.get("type", "")),
            net_profit_min=_as_float(row.get("net_profit_min")),
            net_profit_max=_as_float(row.get("net_profit_max")),
            interval_class=klass,
        )
        grouped.setdefault((code, end_date), []).append(version)
    chains: list[AnnouncementVersion] = []
    for key in sorted(grouped):
        versions = sorted(grouped[key], key=lambda v: v.version_key())
        if len(versions) > 1:
            stats["groups_with_multiple_versions"] += 1
        chains.extend(versions)
    stats["groups"] = len(grouped)
    return chains, stats


def same_day_versions(rows: Iterable[Mapping[str, object]]) -> list[dict]:
    """同一 (ts_code, end_date, ann_date) 出现多个 ``update_flag`` 的清单。"""
    buckets: dict[tuple[str, str, str], set[str]] = {}
    for row in rows:
        if row.get("ann_date") in (None, ""):
            continue
        key = (str(row.get("ts_code", "")), str(row.get("end_date", "")),
               str(row.get("ann_date")))
        buckets.setdefault(key, set()).add(str(row.get("update_flag") or "0"))
    return [
        {"ts_code": k[0], "end_date": k[1], "ann_date": k[2],
         "update_flags": sorted(v), "n_versions": len(v)}
        for k, v in sorted(buckets.items()) if len(v) > 1
    ]


# --------------------------------------------------------------------------- #
# 数据新鲜度门
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FreshnessDecision:
    allow_new_entry: bool
    allow_risk_actions: bool
    reason: str


def freshness_gate(
    last_available_session: HalfDay | None,
    required_session: HalfDay,
    *,
    risk_actions_always_allowed: bool = True,
) -> FreshnessDecision:
    """行情缺失或过期时拒绝新入场，但保留风险处置路径。

    ``required_session`` 是该决策点必须已经结束的最晚半日（即
    ``information_cutoff``）：11:30 决策为上一交易日 pm，15:00 决策为当日 pm。
    ``last_available_session`` 晚于或等于它才算新鲜。
    """
    require_time(required_session, "required_session")
    if last_available_session is None:
        return FreshnessDecision(False, risk_actions_always_allowed,
                                 "missing_market_data")
    if last_available_session < required_session:
        return FreshnessDecision(False, risk_actions_always_allowed,
                                 "stale_market_data")
    return FreshnessDecision(True, risk_actions_always_allowed, "ok")
