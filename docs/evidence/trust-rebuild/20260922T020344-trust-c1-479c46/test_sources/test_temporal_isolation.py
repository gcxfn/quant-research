# -*- coding: utf-8 -*-
"""C1 时间隔离与反证测试（合成数据，不依赖真实行情）。

覆盖主计划第 6 节"必测反证"：
- ``available_at <= decision_at < live_from`` 断言；
- 改午后行情，11:30 决策输出逐位不变（TV-B05/B06 变体）；
- 改决策后价格/未来资格，当前候选与订单不变（TV-B26）；
- 缺失/过期数据拒绝新入场但保留风险处理路径；
- 2020-12-28 事件 20 日窗跨 2021 → window_complete=false 且不入完整窗口均值（TV-B25）；
- manifest 外路径（含真实 Val 路径写法）读取失败；
- 重复公告 / 同日修订 / min=max 点值 / min>max 非法区间（TV-B27/B28）；
- 时间字段空值不得落到当天。

所有输入都是本文件构造的合成 bar 与合成公告，不加载任何真实行情文件。

运行：``PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_temporal_isolation.py``
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, "src")

from quant.data.dev_sandbox import (  # noqa: E402
    PathNotAllowedError, SandboxAccessError, SandboxRegistry)
from quant.data.temporal_contract import (  # noqa: E402
    DEV_END_DEFAULT, INTERVAL_INVALID, INTERVAL_MISSING, INTERVAL_POINT,
    INTERVAL_VALID, HalfDay, NullTimeError, TemporalContractError,
    assert_time_triplet, classify_forecast_interval, complete_window_stats,
    conservative_clock, freshness_gate, own_session_label_window, require_time,
    version_chain)

# --------------------------------------------------------------------------- #
# 合成市场：确定性小世界
# --------------------------------------------------------------------------- #
CALENDAR = [date(2020, 12, 23) + timedelta(days=k)
            for k in range(0, 25) if (date(2020, 12, 23) + timedelta(days=k)).weekday() < 5]
# 更长的合成日历：覆盖 2020-11 至 2021-02，用于标签窗边界测试
CALENDAR_2021 = [date(2020, 11, 2) + timedelta(days=k)
                 for k in range(0, 120)
                 if (date(2020, 11, 2) + timedelta(days=k)).weekday() < 5]


def seq(hd: HalfDay, n: int, calendar: list[date] = CALENDAR) -> list[HalfDay]:
    """从 hd 起的 n 个连续半日（同一天 am->pm，再进入下一交易日 am）。"""
    out: list[HalfDay] = []
    day = hd.day
    session = hd.session
    while len(out) < n:
        out.append(HalfDay(day, session))
        if session == "am":
            session = "pm"
        else:
            i = calendar.index(day)
            day = calendar[i + 1]
            session = "am"
    return out


def information_cutoff(decision: HalfDay,
                       calendar: list[date] = CALENDAR) -> HalfDay:
    """冻结合同的信息截止半日。

    - 15:00 决策（pm）：当日收盘已经结束，可用到 (D, pm)；
    - 11:30 决策（am）：只能用 D 之前已结束的行情，即 (上一交易日, pm)。
    """
    if decision.session == "pm":
        return decision
    i = calendar.index(decision.day)
    return HalfDay(calendar[i - 1], "pm")


def bar(close: float, low: float | None = None, high: float | None = None) -> dict:
    return {"open": close, "high": high if high is not None else close,
            "low": low if low is not None else close, "close": close}


class FrozenBars:
    """按信息截止半日（含端）提供已结束的合成行情。"""

    def __init__(self, bars: dict) -> None:
        self._bars = dict(bars)

    def at(self, symbol: str, hd: HalfDay) -> dict | None:
        return self._bars.get((symbol, hd))

    def usable(self, symbol: str, decision: HalfDay,
               calendar: list[date] = CALENDAR) -> list[tuple[HalfDay, dict]]:
        cutoff = information_cutoff(decision, calendar)
        items = [(hd, b) for (sym, hd), b in self._bars.items()
                 if sym == symbol and hd <= cutoff]
        return sorted(items, key=lambda kv: kv[0])

    def set(self, symbol: str, hd: HalfDay, value: dict | None) -> None:
        if value is None:
            self._bars.pop((symbol, hd), None)
        else:
            self._bars[(symbol, hd)] = value


def eligibility_at(eligibility: dict, symbol: str, decision: HalfDay,
                   history: list[HalfDay]) -> bool:
    """资格只能取自决策点当刻已知的最后一次状态。"""
    known = [eligibility[(symbol, hd)] for hd in history
             if (symbol, hd) in eligibility and hd <= decision]
    return bool(known[-1]) if known else False


def generate_orders(bars: FrozenBars, eligibility: dict, universe: list[str],
                    decision: HalfDay, calendar: list[date] = CALENDAR,
                    max_seats: int = 4) -> list[dict]:
    """确定性候选/订单生成：只使用信息截止半日之前/当刻已结束的合成行情。

    返回字典列表（排序后），可直接 JSON 序列化做逐位比较。
    """
    cutoff = information_cutoff(decision, calendar)
    live_from = seq(decision, 2, calendar)[1]  # am 决策当日下午生效；pm 决策次日 am
    assert_time_triplet(cutoff, decision, live_from)
    rows = []
    for symbol in sorted(universe):
        history = [hd for hd, _ in bars.usable(symbol, decision, calendar)]
        if not history:
            continue
        if not eligibility_at(eligibility, symbol, decision, history):
            continue
        closes = [b["close"] for _, b in bars.usable(symbol, decision, calendar)]
        anchor = closes[-1]
        rows.append({
            "symbol": symbol,
            "decision_at": decision.iso(),
            "information_cutoff": cutoff.iso(),
            "live_from": live_from.iso(),
            "anchor_price": round(anchor, 2),
            "trigger_cap": round(anchor * 1.01, 2),
            "limit_price": round(anchor, 2),
            "score": round(closes[-1] / closes[0], 6),
        })
    rows.sort(key=lambda r: (-r["score"], r["symbol"]))
    return rows[:max_seats]


def render(rows: list[dict]) -> str:
    return json.dumps(rows, sort_keys=True, ensure_ascii=False)


def try_fill_buy(order: dict, bars: FrozenBars) -> dict:
    """严格穿透：只用订单 live_from 那一个半日 bar；触价不算成交，不取更优价。"""
    hd = HalfDay(date.fromisoformat(order["live_from"][:10]),
                 order["live_from"][11:])
    session_bar = bars.at(order["symbol"], hd)
    if session_bar is None:
        return {"filled": False, "reason": "no_bar"}
    if session_bar["low"] < order["limit_price"]:
        return {"filled": True, "price": order["limit_price"], "session": hd.session}
    return {"filled": False, "reason": "not_penetrated"}


# --------------------------------------------------------------------------- #
# 1. 时间四件套
# --------------------------------------------------------------------------- #
def test_available_at_not_after_decision_and_live_after_decision():
    assert assert_time_triplet(HalfDay(date(2020, 12, 28), "pm"),
                               HalfDay(date(2020, 12, 29), "am"),
                               HalfDay(date(2020, 12, 29), "pm"))
    with pytest.raises(TemporalContractError):
        assert_time_triplet(HalfDay(date(2020, 12, 29), "am"),
                            HalfDay(date(2020, 12, 28), "pm"),
                            HalfDay(date(2020, 12, 29), "pm"))
    with pytest.raises(TemporalContractError):
        # live_from 不得等于 decision_at（同半日不可下单）
        assert_time_triplet(HalfDay(date(2020, 12, 28), "pm"),
                            HalfDay(date(2020, 12, 29), "am"),
                            HalfDay(date(2020, 12, 29), "am"))


def test_conservative_clock_next_day_am_decision():
    clock = conservative_clock(date(2020, 12, 28), CALENDAR)
    assert clock["available_at"] == HalfDay(date(2020, 12, 28), "pm")
    assert clock["decision_at"] == HalfDay(date(2020, 12, 29), "am")
    assert clock["live_from"] == HalfDay(date(2020, 12, 29), "pm")
    assert_time_triplet(clock["available_at"], clock["decision_at"], clock["live_from"])
    # 公告日已是日历末尾 → 没有下一交易日，行落在评估窗之外
    assert conservative_clock(CALENDAR[-1], CALENDAR) is None


def test_null_time_never_defaults_to_today():
    with pytest.raises(NullTimeError):
        conservative_clock(None, CALENDAR)
    with pytest.raises(NullTimeError):
        require_time(None, "ann_date")
    with pytest.raises(NullTimeError):
        own_session_label_window(CALENDAR, None)
    with pytest.raises(NullTimeError):
        freshness_gate(HalfDay(date(2020, 12, 28), "pm"), None)
    # 空时间既不是成功也不是当天：明确抛错
    today = date.today()
    try:
        conservative_clock("", CALENDAR)
    except NullTimeError:
        pass
    else:  # 空字符串也必须拒绝
        raise AssertionError("empty ann_date must be rejected, not defaulted")
    assert today != date(2020, 12, 28)


# --------------------------------------------------------------------------- #
# 2. 午后行情不得影响 11:30 输出
# --------------------------------------------------------------------------- #
def _world():
    universe = ["sh.600000", "sz.000001", "sh.600519"]
    day = CALENDAR[1]          # 2020-12-24，前一日 CALENDAR[0] 提供 am 决策所需历史
    bars = FrozenBars({})
    for symbol in universe:
        for i, hd in enumerate(seq(HalfDay(CALENDAR[0], "am"), 12)):
            close = 10.0 + i * 0.1 + (0.5 if symbol == "sh.600519" else 0.0)
            bars.set(symbol, hd, bar(close, low=close - 0.2, high=close + 0.2))
    eligibility = {(sym, hd): True for sym in universe
                   for hd in seq(HalfDay(CALENDAR[0], "am"), 12)}
    return bars, eligibility, universe, day


def test_pm_change_leaves_1130_output_identical():
    bars, eligibility, universe, day = _world()
    decision = HalfDay(day, "am")
    baseline = render(generate_orders(bars, eligibility, universe, decision))

    # 改动决策当日下午与之后所有价格
    for hd in seq(HalfDay(day, "pm"), 8):
        for symbol in universe:
            bars.set(symbol, hd, bar(99.0, low=1.0, high=100.0))
    assert render(generate_orders(bars, eligibility, universe, decision)) == baseline


def test_pm_change_does_change_1500_output_positive_control():
    """反向对照：证明上面的“不变”不是因为决策函数根本不看行情。"""
    bars, eligibility, universe, day = _world()
    decision = HalfDay(day, "pm")
    baseline = render(generate_orders(bars, eligibility, universe, decision))
    for symbol in universe:
        bars.set(symbol, HalfDay(day, "pm"), bar(99.0, low=98.0, high=100.0))
    assert render(generate_orders(bars, eligibility, universe, decision)) != baseline


def test_1130_order_cannot_use_same_day_penetration_tv_b05():
    """TV-B05：15:00 新单不得利用当天上午已发生的穿透；最早下一交易日上午。"""
    bars, eligibility, universe, day = _world()
    decision = HalfDay(day, "pm")
    orders = generate_orders(bars, eligibility, universe, decision)
    assert orders, "synthetic world must produce orders"
    order = orders[0]
    live_hd = HalfDay(date.fromisoformat(order["live_from"][:10]),
                      order["live_from"][11:])
    assert live_hd.session == "am"
    assert live_hd.day > day
    # 决策日当天上午确实穿透了限价，但那是决策前已发生的价格，不参与成交判定
    am_bar = bars.at(order["symbol"], HalfDay(day, "am"))
    assert am_bar is not None and am_bar["low"] < order["limit_price"]
    # 唯一判定半日是 live_from：设为不穿透 → 不成交
    bars.set(order["symbol"], live_hd, bar(order["limit_price"],
                                           low=order["limit_price"]))
    assert try_fill_buy(order, bars) == {"filled": False, "reason": "not_penetrated"}
    # 决策日上午的穿透本身不构成成交：成交只在 live_from 发生
    bars.set(order["symbol"], live_hd,
             bar(order["limit_price"] - 0.3, low=order["limit_price"] - 0.3))
    fill = try_fill_buy(order, bars)
    assert fill["filled"] is True and fill["session"] == "am"
    assert fill["price"] == order["limit_price"]


def test_1130_order_am_touch_pm_no_penetration_tv_b06():
    """TV-B06：11:30 新单，上午触价而下午不穿透 → 不成交；穿透才成交且不取优价。"""
    bars, eligibility, universe, day = _world()
    decision = HalfDay(day, "am")
    orders = generate_orders(bars, eligibility, universe, decision)
    order = orders[0]
    assert order["live_from"] == HalfDay(day, "pm").iso()
    # 下午最低恰等于限价 → 触价，不成交
    bars.set(order["symbol"], HalfDay(day, "pm"),
             bar(order["limit_price"], low=order["limit_price"]))
    assert try_fill_buy(order, bars) == {"filled": False, "reason": "not_penetrated"}
    # 严格低于限价 → 按限价成交，不取更优价
    bars.set(order["symbol"], HalfDay(day, "pm"),
             bar(order["limit_price"] - 0.5, low=order["limit_price"] - 0.5))
    fill = try_fill_buy(order, bars)
    assert fill["filled"] is True and fill["price"] == order["limit_price"]


# --------------------------------------------------------------------------- #
# 3. 未来价格/资格不得回流（TV-B26）
# --------------------------------------------------------------------------- #
def test_future_price_and_eligibility_do_not_change_current_orders():
    bars, eligibility, universe, day = _world()
    decision = HalfDay(day, "am")
    baseline_orders = generate_orders(bars, eligibility, universe, decision)

    future = seq(decision, 8)[1:]
    for hd in future:
        for symbol in universe:
            bars.set(symbol, hd, bar(0.01, low=0.01, high=0.02))
            eligibility[(symbol, hd)] = False
    # 未来资格全部失效、价格崩塌，也不能改变当刻候选
    assert render(generate_orders(bars, eligibility, universe, decision)) == render(
        baseline_orders)


def test_missing_or_stale_data_blocks_new_entry_but_keeps_risk_path():
    # (2020-12-29, am) 决策所需的最晚已完成半日 = 2020-12-28 pm
    required = HalfDay(date(2020, 12, 28), "pm")
    stale = freshness_gate(HalfDay(date(2020, 12, 25), "pm"), required)
    assert stale.allow_new_entry is False
    assert stale.allow_risk_actions is True
    assert stale.reason == "stale_market_data"
    missing = freshness_gate(None, required)
    assert missing.allow_new_entry is False
    assert missing.allow_risk_actions is True
    assert missing.reason == "missing_market_data"
    fresh = freshness_gate(HalfDay(date(2020, 12, 28), "pm"), required)
    assert fresh.allow_new_entry is True and fresh.reason == "ok"


# --------------------------------------------------------------------------- #
# 4. 标签窗边界（TV-B25）
# --------------------------------------------------------------------------- #
def test_20201228_window_crosses_dev_boundary_and_is_excluded():
    own = list(CALENDAR_2021)
    anchor = date(2020, 12, 28)
    window = own_session_label_window(own, anchor, 20, dev_end=DEV_END_DEFAULT,
                                      market_calendar=own)
    assert window.anchor_date == anchor
    assert window.label_end_at is not None and window.label_end_at.year == 2021
    assert window.window_complete is False
    assert window.crosses_dev_boundary is True
    assert window.n_own_sessions == 20
    assert window.n_market_sessions == 20

    # 对照：2020-11-30 起 20 个自身交易日落在 Dev 内 → 完整
    full = own_session_label_window(own, date(2020, 11, 30), 20,
                                    dev_end=DEV_END_DEFAULT, market_calendar=own)
    assert full.window_complete is True and full.crosses_dev_boundary is False
    assert full.label_end_at is not None and full.label_end_at <= DEV_END_DEFAULT

    values = [0.05, 0.07]
    stats = complete_window_stats(values, [full, window])
    assert stats["n_complete"] == 1 and stats["n_censored"] == 1
    assert stats["mean"] == pytest.approx(0.05)
    # 右删失窗口即使被塞入极端收益也不改变完整窗口均值
    stats2 = complete_window_stats([0.05, 999.0], [full, window])
    assert stats2["mean"] == pytest.approx(0.05)


def test_own_and_market_session_counts_are_separate():
    """停牌使某证券缺失自身交易日：两种口径不同，必须分别记录、不得混同。"""
    own = [d for d in CALENDAR if d not in {date(2020, 12, 30),
                                            date(2020, 12, 31)}]
    window = own_session_label_window(own, date(2020, 12, 24), 4,
                                      dev_end=DEV_END_DEFAULT,
                                      market_calendar=CALENDAR)
    assert window.n_own_sessions == 4
    assert window.n_market_sessions is not None
    assert window.n_market_sessions > window.n_own_sessions


def test_window_ended_by_panel_is_censored_with_reason():
    own = [d for d in CALENDAR[:6]]
    window = own_session_label_window(own, own[-1], 20, dev_end=DEV_END_DEFAULT)
    assert window.window_complete is False
    assert window.missing_reason == "ended_by_panel_end"
    assert window.label_end_at is None


def test_boundary_truncated_panel_marks_crossing_not_deletion():
    """Dev 沙箱里行情被 dev_end 截断：窗口不足额 = 跨边界，而不是被删除。"""
    own = [d for d in CALENDAR if d <= DEV_END_DEFAULT]
    crossing = own_session_label_window(
        own, date(2020, 12, 24), 20, dev_end=DEV_END_DEFAULT,
        market_calendar=CALENDAR, panel_truncated_at=DEV_END_DEFAULT)
    assert crossing.window_complete is False
    assert crossing.crosses_dev_boundary is True
    assert crossing.missing_reason == "crosses_dev_boundary"
    assert crossing.label_end_at is None      # 终点在 2021，不推算
    # 同一份自身交易日列表、未声明边界截断 → 归因是"面板终止"，两种归因不混同
    terminated = own_session_label_window(
        own, date(2020, 12, 24), 20, dev_end=DEV_END_DEFAULT,
        market_calendar=CALENDAR)
    assert terminated.crosses_dev_boundary is False
    assert terminated.missing_reason == "ended_by_panel_end"


# --------------------------------------------------------------------------- #
# 5. manifest 外路径一律拒绝
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("val_path", [
    "data/raw/tushare/forecast/20260909-r1/chunk_202101.csv",
    "data/raw/baostock/daily/sh.600000.csv",
    "data/processed/baostock-daily-20260917/daily_1999_2024.parquet",
    "data/processed/halfday-bars-20260918/year=2021/bars.parquet",
    "data/features/fcst-reason-struct-full-20260918/row_index.parquet",
])
def test_paths_outside_manifest_are_refused(tmp_path, val_path):
    root, registry = _make_synthetic_sandbox(tmp_path)
    with pytest.raises(PathNotAllowedError):
        registry.resolve(val_path)


def test_unknown_dataset_id_refused(tmp_path):
    root, _ = _make_synthetic_sandbox(tmp_path)
    from quant.data.dev_sandbox import UnknownDatasetError
    with pytest.raises(UnknownDatasetError):
        SandboxRegistry.load(root, dataset_id="baostock-daily-20260917")
    with pytest.raises(UnknownDatasetError):
        SandboxRegistry.load(root, dataset_id="halfday-bars-20260918")


def _make_synthetic_sandbox(tmp_path):
    """构造一个最小的 dev-sandbox 目录（合成数据），用于权限路径测试。"""
    import polars as pl
    from quant.data.dev_sandbox import SANDBOX_DATASET_ID_DEFAULT, sha256_file
    root = tmp_path / "repo"
    sandbox = root / "data/processed" / SANDBOX_DATASET_ID_DEFAULT
    sandbox.mkdir(parents=True)
    frame = pl.DataFrame({
        "symbol": ["sh.600000", "sz.000001"],
        "date": [date(2020, 12, 28), date(2020, 12, 29)],
        "close": [10.0, 10.5],
    })
    rel = "bars_daily_dev.parquet"
    repo_rel = f"data/processed/{SANDBOX_DATASET_ID_DEFAULT}/{rel}"
    frame.write_parquet(sandbox / rel)
    manifest = {
        "schema_version": "1.0",
        "dataset_id": SANDBOX_DATASET_ID_DEFAULT,
        "contract_sha256": "0" * 64,
        "datasets": [{
            "kind": "bars_daily",
            "date_column": "date",
            "symbol_column": "symbol",
            "min_allowed_date": "2015-01-05",
            "max_allowed_date": "2020-12-31",
            "purpose": "dev_performance_window",
            "semantics": "synthetic",
            "columns": ["symbol", "date", "close"],
            "units": {"close": "CNY"},
            "files": [{
                "rel_path": repo_rel,
                "sha256": sha256_file(sandbox / rel),
                "rows": frame.height,
                "date_min": "2020-12-28",
                "date_max": "2020-12-29",
            }],
        }],
    }
    (sandbox / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return root, SandboxRegistry.load(root)


# --------------------------------------------------------------------------- #
# 6. 预告区间与版本合法性（TV-B27/B28）
# --------------------------------------------------------------------------- #
def test_interval_point_vs_invalid_are_distinguished():
    assert classify_forecast_interval(100.0, 100.0) == INTERVAL_POINT
    assert classify_forecast_interval(100.0, 200.0) == INTERVAL_VALID
    assert classify_forecast_interval(200.0, 100.0) == INTERVAL_INVALID
    assert classify_forecast_interval(None, 100.0) == INTERVAL_MISSING
    assert classify_forecast_interval("", "") == INTERVAL_MISSING
    assert classify_forecast_interval(float("nan"), 1.0) == INTERVAL_MISSING


def test_version_chain_dedupes_and_orders_without_backfill():
    rows = [
        # 早期版本
        {"ts_code": "000001.SZ", "end_date": "20201231", "ann_date": "20201031",
         "update_flag": "0", "type": "预增", "net_profit_min": 100, "net_profit_max": 120},
        # 历史修订（同财务期的后续版本）
        {"ts_code": "000001.SZ", "end_date": "20201231", "ann_date": "20201215",
         "update_flag": "1", "type": "预增", "net_profit_min": 150, "net_profit_max": 180},
        # 同日多版本：update_flag 区分
        {"ts_code": "000001.SZ", "end_date": "20201231", "ann_date": "20201215",
         "update_flag": "2", "type": "预增", "net_profit_min": 160, "net_profit_max": 190},
        # 完全重复行（取数重复）
        {"ts_code": "000001.SZ", "end_date": "20201231", "ann_date": "20201215",
         "update_flag": "2", "type": "预增", "net_profit_min": 160, "net_profit_max": 190},
        # 空公告日：fail-closed 丢弃，不回填当天
        {"ts_code": "000002.SZ", "end_date": "20201231", "ann_date": None,
         "update_flag": "0", "type": "预减", "net_profit_min": 10, "net_profit_max": 5},
        # 非法区间 min>max
        {"ts_code": "000003.SZ", "end_date": "20201231", "ann_date": "20201220",
         "update_flag": "0", "type": "略增", "net_profit_min": 500, "net_profit_max": 100},
        # 点预测 min==max
        {"ts_code": "000004.SZ", "end_date": "20201231", "ann_date": "20201220",
         "update_flag": "0", "type": "扭亏", "net_profit_min": 88, "net_profit_max": 88},
    ]
    chain, stats = version_chain(rows)
    assert stats["rows_in"] == 7
    assert stats["dropped_missing_ann_date"] == 1
    assert stats["dropped_exact_duplicate_rows"] == 1
    assert stats["groups"] == 3
    assert stats["groups_with_multiple_versions"] == 1   # 000001 三个版本
    assert stats["interval_invalid"] == 1
    assert stats["interval_point"] == 1
    same_group = [v for v in chain if v.ts_code == "000001.SZ"]
    assert [v.version_key() for v in same_group] == [
        ("20201031", "0"), ("20201215", "1"), ("20201215", "2")]
    # 不回填：第一条仍是早期版本的原值
    assert same_group[0].net_profit_min == 100.0


def test_same_day_versions_reported():
    from quant.data.temporal_contract import same_day_versions
    rows = [
        {"ts_code": "000001.SZ", "end_date": "20201231", "ann_date": "20201215",
         "update_flag": "1"},
        {"ts_code": "000001.SZ", "end_date": "20201231", "ann_date": "20201215",
         "update_flag": "2"},
        {"ts_code": "000002.SZ", "end_date": "20201231", "ann_date": "20201215",
         "update_flag": "0"},
    ]
    out = same_day_versions(rows)
    assert len(out) == 1
    assert out[0]["ts_code"] == "000001.SZ"
    assert out[0]["update_flags"] == ["1", "2"]


def test_sandbox_rejects_request_beyond_dev_end(tmp_path):
    from datetime import date as _d
    from quant.data.dev_sandbox import DateRangeError
    root, registry = _make_synthetic_sandbox(tmp_path)
    with pytest.raises(DateRangeError):
        registry.read("bars_daily", end=_d(2021, 1, 4))
    with pytest.raises(SandboxAccessError):
        registry.read("bars_daily", columns=["not_a_column"])
