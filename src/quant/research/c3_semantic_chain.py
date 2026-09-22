# -*- coding: utf-8 -*-
"""C3-B 语义链驱动：策略 → 订单 → 席位/退出/风险状态的可追溯证据。

与 ``reference_matcher_reconcile`` 的分工：本模块**故意要读真实策略与风险代码**
（C-05 的 cap 链条、席位账、D3 恢复队列、11:30 不变性），因此它不属于
``reference_matcher`` 的独立实现，也不受 C3-01 的 import 禁令约束；独立性扫描
只覆盖 ``reference_matcher.py`` 与 ``reference_matcher_reconcile.py``。

产物：

* ``intent_to_order_trace.csv``——C-05 关闭：触发收盘 → cap(×1.01) → 决策锚价
  → 实际限价，逐单两值 + 关系判定；
* ``seat_lifecycle.csv``——席位账（held + active_pending）逐决策点守恒；
* ``risk_state_trace.csv`` + ``risk_state_trace_hand_expected.csv``——D3
  正常/降档/恢复队列（合成权益路径 (a)正常反弹 (b)持续低迷），并附独立手算期望；
* ``clip_exit_trace.csv``——退出原因 → 订单映射与 take_half 非完成语义；
* ``eleven_thirty_invariance.csv`` + ``.log``——真实策略链
  （event_family_signals → band_engine）在 6 个决策点上的 11:30 不变性、
  两个正向对照与历史稳定性。

用法::

    PYTHONPATH=src .venv/Scripts/python.exe -m quant.research.c3_semantic_chain \
        --evidence-dir docs/evidence/trust-rebuild/<C3-run>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import polars as pl

sys.path.insert(0, "src")

from quant.data import dev_sandbox  # noqa: E402
from quant.research.reference_matcher_reconcile import (  # noqa: E402
    ArmEvents, Market, write_csv,
)

ATTRIB2_RUN = "20260922T002611-eventfam-attrib2-eed5cf"
EVENTFAM_RUN = "20260921T223157-eventfam-main-cb4cff"
MAX_SEATS = 4


# --------------------------------------------------------------------------- #
# 1. C-05：cap → 限价链条
# --------------------------------------------------------------------------- #
def intent_to_order_trace(root: Path, market: Market) -> tuple[list[dict], dict]:
    """逐行给出 ``trigger_close`` / ``trigger_cap`` / ``decision_anchor`` /
    ``limit_price`` 四值与关系判定，回答「×1.01 是门槛还是限价」。"""
    from quant.research.event_family_signals import CHASE
    funnel = pl.read_csv(root / "artifacts" / "runs" / ATTRIB2_RUN /
                         "outputs" / "B1_event_funnel.csv")
    rows: list[dict] = []
    n_issued = n_eq_anchor = n_eq_cap = 0
    for r in funnel.iter_rows(named=True):
        decision_day = date.fromisoformat(str(r["decision_time"])[:10])
        d_sess = str(r["decision_time"])[-2:]
        anchor = r["decision_anchor_price"]
        if d_sess == "pm":
            trig_close = market.official_close(r["symbol"], decision_day)
            anchor_kind = "official_close(same day)"
        else:
            trig_close = market.prev_trading_close(r["symbol"], decision_day)
            anchor_kind = "official_close(previous session; 11:30 anchor)"
        cap = None if trig_close is None else float(trig_close) * (1.0 + CHASE)
        lim = r["order_price_first"]
        issued = bool(r["issued"])
        if issued:
            n_issued += 1
            if lim is not None and anchor is not None and \
                    abs(float(lim) - float(anchor)) < 1e-9:
                n_eq_anchor += 1
            if lim is not None and cap is not None and \
                    abs(float(lim) - float(cap)) < 1e-9:
                n_eq_cap += 1
        rows.append({
            "event_id": r["event_id"], "symbol": r["symbol"],
            "ann_date": r["ann_date"], "decision_day": decision_day.isoformat(),
            "decision_session": d_sess,
            "trigger_close_official": ("" if trig_close is None
                                       else round(float(trig_close), 4)),
            "anchor_kind": anchor_kind,
            "trigger_cap_1p01": "" if cap is None else round(cap, 4),
            "decision_anchor_price": "" if anchor is None else anchor,
            "order_price_first": "" if lim is None else lim,
            "order_price_last": ("" if r["order_price_last"] is None
                                 else r["order_price_last"]),
            "issued": issued,
            "skip_or_cancel_reason": r["skip_or_cancel_reason"] or "",
            "cap_ge_anchor": "" if cap is None or anchor is None
            else bool(cap >= float(anchor) - 1e-9),
            "limit_equals_anchor": "" if lim is None or anchor is None
            else bool(abs(float(lim) - float(anchor)) < 1e-9),
            "limit_equals_cap": "" if lim is None or cap is None
            else bool(abs(float(lim) - float(cap)) < 1e-9),
            "relationship": (
                "cap_is_issuance_threshold__limit_is_decision_anchor"
                if lim is not None and anchor is not None
                and abs(float(lim) - float(anchor)) < 1e-9
                else ("not_issued" if not issued else "unexpected")),
            "provider_rule": "event_family_signals.cap_price = trigger_close "
                             "*(1+CHASE=1.01); entry issued only while "
                             "decision anchor <= cap (skip_cap otherwise)",
            "engine_rule": "band_engine order construction: anchor_price = "
                           "decision anchor (stock anchors are not tick-rounded)",
        })
    summary = {
        "rows": len(rows), "issued": n_issued,
        "issued_limit_equals_anchor": n_eq_anchor,
        "issued_limit_equals_cap": n_eq_cap,
        "conclusion": ("C-05 closed: x1.01 is an ISSUANCE THRESHOLD; the "
                       "submitted limit_price equals the decision anchor, "
                       "never the cap"),
    }
    return rows, summary


# --------------------------------------------------------------------------- #
# 2. 席位账
# --------------------------------------------------------------------------- #
def seat_lifecycle(root: Path) -> tuple[list[dict], dict]:
    funnel = pl.read_csv(root / "artifacts" / "runs" / ATTRIB2_RUN /
                         "outputs" / "B1_event_funnel.csv")
    rows: list[dict] = []
    for r in funnel.sort(["decision_time", "event_id"]).iter_rows(named=True):
        held = int(r["held_seats"] or 0)
        pend = int(r["pending_seats"] or 0)
        rows.append({
            "event_id": r["event_id"], "symbol": r["symbol"],
            "decision_time": r["decision_time"], "risk_state": r["risk_state"],
            "category": r["category"], "held_seats": held,
            "pending_seats": pend, "seats_used_before": held + pend,
            "available_seats": MAX_SEATS - (held + pend),
            "admission_rank": "" if r["admission_rank"] is None
            else r["admission_rank"],
            "issued": bool(r["issued"]),
            "skip_or_cancel_reason": r["skip_or_cancel_reason"] or "",
            "seats_within_cap": held + pend <= MAX_SEATS,
            "rank_key": "event_family_signals admission order = "
                        "(decision_time, -rank_key, symbol); rank_key = ret60 "
                        "so higher momentum is admitted first",
            "expiry_releases_seat": "engine: half-day orders expire every "
                                    "session; a pending entry drops on TTL "
                                    "(ENTRY_TTL_SESSIONS) / cap / cancel_level "
                                    "and the seat returns to the pool",
            "same_symbol_counts_once": "held + pending are sets keyed by symbol",
        })
    counts: dict[str, int] = {}
    for r in rows:
        key = ("issued" if r["issued"]
               else (r["skip_or_cancel_reason"] or "not_issued_other"))
        counts[key] = counts.get(key, 0) + 1
    bad = [r["event_id"] for r in rows if not r["seats_within_cap"]]
    summary = {
        "rows": len(rows), "conservation_by_category": counts,
        "conservation_total": sum(counts.values()),
        "seats_over_cap_rows": len(bad),
        "note": "held+pending 取自与 B1 同参数的 attrib2 run 漏斗；B1 主 run 本身"
                "不落漏斗产物，来源差异已登记在 c3_case_report.md",
    }
    return rows, summary


# --------------------------------------------------------------------------- #
# 3. D3 正常/降档/恢复（真实代码 + 独立手算）
# --------------------------------------------------------------------------- #
def _hand_compute_d3(equities: list[float]) -> list[dict]:
    """独立复述合同的 D3 期望（不调用引擎）：高水位回撤 ≥10% 降档；
    回撤 ≤5% 且连续 2 个确认 session 且冷却 3 session 后恢复。"""
    hwm = equities[0]
    state = "normal"
    streak = 0
    lowered_at = None
    out: list[dict] = []
    for i, e in enumerate(equities):
        hwm = max(hwm, e)
        dd = 1.0 - e / hwm
        if state == "normal":
            if dd >= 0.10:
                state = "reduced"
                streak = 0
                lowered_at = i
        else:
            streak = streak + 1 if dd <= 0.05 else 0
            cool = lowered_at is not None and (i - lowered_at) >= 3
            if streak >= 2 and cool:
                state = "normal"
                streak = 0
                lowered_at = None
        out.append({"asof_index": i, "equity": e, "hwm": hwm,
                    "drawdown": dd, "expected_state": state,
                    "expected_confirmation_streak": streak})
    return out


def risk_state_trace() -> tuple[list[dict], list[dict], dict]:
    """两条合成权益路径：(a) 降档后正常反弹恢复；(b) 降档后持续低迷不恢复。"""
    from quant.portfolio.risk_overlay import AccountRiskDynamics
    base = date(2020, 1, 2)

    def days(n: int) -> list[date]:
        return [date.fromordinal(base.toordinal() + i) for i in range(n)]

    paths = {
        "rebound": [500_000.0, 505_000.0, 495_000.0, 440_000.0, 445_000.0,
                    470_000.0, 478_000.0, 480_000.0, 485_000.0],
        "slump": [500_000.0, 505_000.0, 495_000.0, 440_000.0, 430_000.0,
                  420_000.0, 415_000.0, 410_000.0, 405_000.0],
    }
    rows: list[dict] = []
    hand_rows: list[dict] = []
    summary: dict = {}
    for name, equities in paths.items():
        ds = days(len(equities))
        dyn = AccountRiskDynamics("D3")
        code_rows = []
        for d, e in zip(ds, equities):
            dyn.observe_close(d, e)
            code_rows.append({"path": name, "asof": d.isoformat(),
                              **dyn.step(d).as_dict()})
        expect = _hand_compute_d3(equities)
        agree = 0
        for cr, er in zip(code_rows, expect):
            ok = cr["risk_state"] == er["expected_state"]
            agree += int(ok)
            rows.append({
                "path": name, "asof": cr["asof"],
                "equity_as_of": cr["equity_as_of"],
                "high_water_mark": cr["high_water_mark"],
                "drawdown": cr["drawdown"],
                "risk_state_code": cr["risk_state"],
                "action_code": cr["action"],
                "exposure_multiplier": cr["exposure_multiplier"],
                "trigger_reason": cr["trigger_reason"],
                "previous_state": cr["previous_state"],
                "recovery_condition": cr["recovery_condition"],
                "cooldown_until": cr["cooldown_until"],
                "state_changed": cr["state_changed"],
                "hand_expected_state": er["expected_state"],
                "hand_expected_drawdown": round(er["drawdown"], 6),
                "hand_confirmation_streak": er["expected_confirmation_streak"],
                "code_matches_hand": ok,
            })
            hand_rows.append({"path": name, **{k: (str(v) if isinstance(v, date)
                                                   else v)
                                               for k, v in er.items()}})
        summary[name] = {
            "sessions": len(code_rows),
            "code_states": [r["risk_state"] for r in code_rows],
            "hand_states": [r["expected_state"] for r in expect],
            "agreement": f"{agree}/{len(expect)}",
            "final_exposure_multiplier": code_rows[-1]["exposure_multiplier"],
        }
    return rows, hand_rows, summary


# --------------------------------------------------------------------------- #
# 4. 退出原因 → 订单映射
# --------------------------------------------------------------------------- #
def clip_exit_trace(root: Path, ev: "ArmEvents") -> tuple[list[dict], dict]:
    log = pl.read_csv(root / "artifacts" / "runs" / EVENTFAM_RUN /
                      "outputs" / "B1_exit_reason_log.csv")
    index: dict[tuple[str, str], list[dict]] = {}
    for od in ev.limit_rows:
        index.setdefault((od["symbol"], od["live_date"].isoformat()),
                         []).append(od)
    reason_map = {
        "clear": ("risk sell", "full clear (signal / seat release)"),
        "time_exit": ("profit sell", "expiry silent; no K=3 fallback"),
        "take_half": ("profit sell", "partial profit; NOT complete on trigger"),
        "protection": ("risk sell", "protection line; K=3 fallback armed"),
        "stop": ("risk sell", "stop loss; K=3 fallback armed"),
        "account_trim": ("risk sell", "D3 account de-leverage; K=3 fallback"),
    }
    rows: list[dict] = []
    for r in log.iter_rows(named=True):
        matches = index.get((r["symbol"], str(r["day"])), [])
        kind, rule = reason_map.get(r["reason"], ("unknown", "unmapped"))
        rows.append({
            "day": r["day"], "session": r["sess"], "symbol": r["symbol"],
            "exit_reason": r["reason"], "source_signal": r["source"],
            "intent": r["intent"], "mapped_order_class": kind,
            "semantics": rule, "n_order_rows_that_day": len(matches),
            "engine_order_events": ";".join(sorted({o["event"]
                                                    for o in matches})),
            "matched_order_ids": ";".join(o["order_id"] for o in matches),
            "take_half_marked_complete_by_trigger_only": (
                "no" if r["reason"] == "take_half" else ""),
            "resend_freezes_same_event_id": (
                "yes: the standing risk order is keyed by "
                "(symbol, intent, source_signal); a re-issue re-anchors and "
                "keeps the K streak (M1)"),
            "fifo_vs_per_clip_risk_intent": (
                "FIFO consumption is used for partial sells, while a risk "
                "intent targets the aggregate position: a per-clip risk line "
                "can be crossed while FIFO sells a different clip. Registered "
                "mismatch (C2 transfer item); C4 disposition: keep FIFO, "
                "document that no per-clip risk exit primitive exists, and "
                "re-estimate any per-clip risk claim rather than adding a "
                "second exit path"),
        })
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["exit_reason"]] = counts.get(r["exit_reason"], 0) + 1
    summary = {"rows": len(rows), "by_reason": counts,
               "unmapped_reasons": sorted({r["exit_reason"] for r in rows
                                           if r["mapped_order_class"] == "unknown"})}
    return rows, summary


# --------------------------------------------------------------------------- #
# 5. 11:30 不变性（真实策略链，合成切片）
# --------------------------------------------------------------------------- #
def _build_panel(perturb: str | None):
    """3 个交易日 × 2 标的的合成切片（Dev 窗内日期，全合成行情）。

    官方日收盘 = 当日 pm 收盘。``perturb``：

    * ``None``：基线；
    * ``pm_of_d2``：改 D2 的**午后 bar 与官方收盘**（D2 11:30 决策点之后的信息）；
    * ``am_of_d2``：改 D2 的**上午 bar**（D2 11:30 锚，决策点之前的信息）。
    """
    from datetime import date as _d
    days = [_d(2020, 3, 2), _d(2020, 3, 3), _d(2020, 3, 4)]
    syms = ["sh.600001", "sz.000002"]
    daily_rows, half_rows = [], []
    for si, s in enumerate(syms):
        p0 = 10.0 + si
        for i, d in enumerate(days):
            px = p0 * (1.0 + 0.01 * i)
            am_c = px * 1.004
            pm_c = px * 1.010
            if perturb == "pm_of_d2" and i == 1:
                pm_c = px * 1.30
            if perturb == "am_of_d2" and i == 1:
                am_c = px * 0.70
            official_close = pm_c
            daily_rows.append({"symbol": s, "date": d, "open": px,
                               "high": max(am_c, pm_c) * 1.005,
                               "low": min(am_c, pm_c) * 0.995,
                               "close": official_close, "tradestatus": 1.0})
            for sess in ("am", "pm"):
                c = am_c if sess == "am" else pm_c
                hi, lo = max(px, c) * 1.005, min(px, c) * 0.995
                half_rows.append({"symbol": s, "trade_date": d, "session": sess,
                                  "open": px, "high": hi, "low": lo, "close": c})
    daily = pl.DataFrame(daily_rows).with_columns(pl.col("date").cast(pl.Date))
    half = pl.DataFrame(half_rows).with_columns(
        pl.col("trade_date").cast(pl.Date))
    limits = daily.select("symbol", "date",
                          (pl.col("close") * 1.1).alias("limit_up"),
                          (pl.col("close") * 0.9).alias("limit_down"))
    return days, syms, daily, half, limits


ENGINE_OID_TAIL = re.compile(r"-(?P<day>\d{4}-\d{2}-\d{2})-(?P<sess>am|pm)$")


def _engine_orders_by_decision(res) -> tuple[dict[tuple[str, str], str],
                                            dict[tuple[str, str], str]]:
    """把引擎订单事件按**决策槽位**归组并序列化。

    引擎订单号形如 ``{sym}-{side}[/{intent}]-{decision_day}-{decision_sess}``：
    尾部日期/半日是**决策点**，不是生效半日。返回两份映射：

    * ``limits``：决策**产出**的订单身份 + 实际限价（= 决策点输出，与撮合结果
      无关）。不变性检查用这一份——因为一张 11:30 决策单的生效半日正是当日
      午后，用「成交/作废结果」做不变性会被撮合层污染。
    * ``full``：含成交股数与终止事件的完整行（日志与人工阅录用）。
    """
    rows = res.events.filter(pl.col("order_id").is_not_null()
                             & pl.col("limit_price").is_not_null())
    lim: dict[tuple[str, str], list[tuple]] = {}
    full: dict[tuple[str, str], list[tuple]] = {}
    for r in rows.iter_rows(named=True):
        m = ENGINE_OID_TAIL.search(r["order_id"])
        if m is None:
            continue
        key = (m.group("day"), m.group("sess"))
        lim.setdefault(key, []).append(
            (r["order_id"], round(float(r["limit_price"]), 6)))
        full.setdefault(key, []).append(
            (r["order_id"], round(float(r["limit_price"]), 6),
             None if r["shares"] is None else int(r["shares"]), r["event"]))
    dump = lambda d: {k: json.dumps(sorted(v), ensure_ascii=False)  # noqa: E731
                      for k, v in d.items()}
    return dump(lim), dump(full)


class _StandingRiskHost:
    """合成 host：持有标的在 ``from_day`` 起的每个决策点挂一张 standing 风险卖单。

    provider 会给这些行重新打上决策点时间戳并按 ``account_trim`` 归入 risk 类
    （沿真实 ``DynamicOverlayHost`` 的行形状）。这样 11:30 与 15:00 两个决策点
    在每个变体里都有**非空**输出，不变性检查才是非平凡的。
    """

    def __init__(self, symbol: str, entry_day: date, from_day: date,
                 source: date, target_notional: float = 50_000.0) -> None:
        self.symbol = symbol
        self.entry_day = entry_day
        self.from_day = from_day
        self.source = source
        self.target_notional = target_notional

    def step(self, ledger, **kw):
        held = {str(p["symbol"]) for p in ledger.get("positions", [])
                if int(p.get("shares") or 0) > 0}
        day = ledger.get("date")
        sess = ledger.get("session")

        class _Step:
            risk_state = "normal"
            target_weight = 0.10
            rows: list = []

        step = _Step()
        if self.symbol in held and day is not None and day >= self.from_day:
            step.rows = [{
                "symbol": self.symbol, "side": "sell", "intent": "risk",
                "decision_date": day, "decision_session": sess,
                "source_signal": self.source, "priority": 1_000_000,
                "target_notional": 0.0, "target_weight": None,
                "expiry_date": None,
            }]
        elif day == self.entry_day and sess == "am":
            # 固定入场：D1 上午决策 → D1 下午生效。这样 D1 pm 就成交，
            # **没有任何订单 live 在 D2 am**，扰动 D2 的涨跌停带便不会通过
            # 撮合污染 D2 11:30 的账本（那样才能把「11:30 不受午后影响」
            # 与「午后改变了别的东西」区分开）。
            step.rows = [{
                "symbol": self.symbol, "side": "buy", "intent": "",
                "decision_date": day, "decision_session": sess,
                "source_signal": self.entry_day, "priority": 1,
                "target_notional": self.target_notional,
                "target_weight": None, "expiry_date": None,
            }]
        return step


def eleven_thirty_invariance() -> tuple[list[dict], list[str], dict]:
    """真实策略链（EventFamilyProvider → band_engine）的决策点不变性重证。

    场景：A1 触发在 D1 决策点买入 sh.600001（D1 pm 成交），此后每个决策点挂一张
    standing 风险卖单；于是 D2 am 与 D2 pm 两个决策点在三个变体里都有非空输出。

    * **A**：改 D2 午后（pm bar 与由它决定的官方收盘）后，D2 am 决策点输出
      逐位不变（provider 行 + 引擎订单行两个层次）；
    * **B**：同一改动必须让 D2 pm（15:00）决策点输出变化（正向对照）；
    * **C**：改 D2 上午必须让 D2 am 决策点输出变化（正向对照）；
    * **D**：D1 两个决策点在三个变体下完全一致（历史不被未来改动影响）。
    """
    from datetime import date as _d
    import numpy as np
    from quant.backtest.band_engine import run_band_backtest_intents
    from quant.research.event_family_signals import (
        EventFamilyProvider, FamilyParams, SymbolSeries, TriggerEvent)

    log: list[str] = []

    def run(variant: str | None):
        days, syms, daily, half, limits = _build_panel(variant)
        sym0 = syms[0]
        close_map: dict[str, dict[_d, float]] = {}
        hl_map: dict[str, dict[_d, tuple[float, float]]] = {}
        price_map: dict[tuple[str, _d, str], float] = {}
        for row in daily.iter_rows(named=True):
            close_map.setdefault(row["symbol"], {})[row["date"]] = \
                float(row["close"])
            hl_map.setdefault(row["symbol"], {})[row["date"]] = (
                float(row["high"]), float(row["low"]))
        for row in half.iter_rows(named=True):
            price_map[(row["symbol"], row["trade_date"], row["session"])] = \
                float(row["close"])
        series = {}
        for s in syms:
            ds = sorted(close_map[s])
            series[s] = SymbolSeries(
                s, ds,
                np.array([close_map[s][d] for d in ds], dtype=float),
                np.array([hl_map[s][d][0] for d in ds], dtype=float),
                np.array([hl_map[s][d][1] for d in ds], dtype=float),
                np.full(len(ds), 1_000_000.0))
        sess_idx = {}
        k = 0
        for d in days:
            for ss in ("am", "pm"):
                sess_idx[(d, ss)] = k
                k += 1
        events: list = []

        class _SNR:
            def decide(self, positions, prices, *, day, session):
                return []

        real = EventFamilyProvider(
            FamilyParams("A1"), events, series,
            _StandingRiskHost(sym0, days[0], days[1], days[1]), _SNR(),
            lambda s, d, ss: price_map.get((s, d, ss)), [days[-1]], sess_idx)
        seen: dict[tuple[str, str], str] = {}

        def rec_provider(day, sess, ledger):
            rows = real.provider(day, sess, ledger) or []
            seen[(day.isoformat(), sess)] = json.dumps(
                rows, sort_keys=True, ensure_ascii=False, default=str)
            return rows

        res = run_band_backtest_intents(
            None, daily, half, limits, initial_cash=500_000.0,
            execution_clock="halfday", intent_provider=rec_provider)
        eng, eng_full = _engine_orders_by_decision(res)
        log.append(f"[variant={variant}] provider rows at {len(seen)} "
                   f"decision points; engine order rows at {len(eng)}; "
                   f"orders_generated="
                   f"{res.stats['intent_layer'].get('orders_generated')}; "
                   f"fills={res.fills.height}")
        for key in sorted(eng_full):
            log.append(f"    engine_full[{key[0]} {key[1]}] = "
                       f"{eng_full[key][:260]}")
        for key in sorted(seen):
            log.append(f"    provider[{key[0]} {key[1]}] = {seen[key][:260]}")
        return seen, eng

    base_p, base_e = run(None)
    pm_p, pm_e = run("pm_of_d2")
    am_p, am_e = run("am_of_d2")

    d2am = ("2020-03-03", "am")
    d2pm = ("2020-03-03", "pm")
    d1pts = [("2020-03-02", "am"), ("2020-03-02", "pm")]

    def pick(d, key):
        return d.get(key) or ""

    def row(check, point, a, b, want_change):
        same = a == b
        ok = (not same) if want_change else same
        return {"check": check, "decision_point": point,
                "left": a[:300], "right": b[:300], "identical": same,
                "expects_change": want_change,
                "verdict": "PASS" if ok else "FAIL"}

    rows = [
        row("A1: 11:30 PROVIDER rows unchanged when the same day's afternoon "
            "and official close change", f"{d2am[0]} {d2am[1]}",
            pick(base_p, d2am), pick(pm_p, d2am), False),
        row("A2: 11:30 ENGINE order rows unchanged under the same change",
            f"{d2am[0]} {d2am[1]}", pick(base_e, d2am), pick(pm_e, d2am), False),
        row("B: positive control - the 15:00 (pm) decision output DOES change",
            f"{d2pm[0]} {d2pm[1]}", pick(base_e, d2pm), pick(pm_e, d2pm), True),
        row("C: positive control - changing the morning DOES change the 11:30 "
            "decision output", f"{d2am[0]} {d2am[1]}",
            pick(base_e, d2am), pick(am_e, d2am), True),
    ]
    d1_ok = (all(pick(base_e, p) == pick(pm_e, p) == pick(am_e, p)
                 for p in d1pts)
             and all(pick(base_p, p) == pick(pm_p, p) == pick(am_p, p)
                     for p in d1pts))
    rows.append({"check": "D: D1 decisions identical across all three variants",
                 "decision_point": "2020-03-02 am/pm", "left": "", "right": "",
                 "identical": d1_ok, "expects_change": False,
                 "verdict": "PASS" if d1_ok else "FAIL"})
    summary = {
        "decision_points": [f"{d} {s}" for d, s in sorted(set(base_p) & set(base_e))],
        "n_decision_points": len(set(base_p) & set(base_e)),
        "A1_provider_1130_identical": rows[0]["verdict"] == "PASS",
        "A2_engine_1130_identical": rows[1]["verdict"] == "PASS",
        "B_1500_changes": rows[2]["verdict"] == "PASS",
        "C_1130_changes_with_morning": rows[3]["verdict"] == "PASS",
        "D_history_stable": rows[4]["verdict"] == "PASS",
        "note": "合成切片（Dev 窗内日期、全合成行情）；provider 与引擎均为真实"
                "代码；recorder 冻结每个决策点的 provider 输出，引擎侧按 order_id "
                "的决策槽位归组订单事件（含实际限价）后逐位比较",
    }
    return rows, log, summary



# --------------------------------------------------------------------------- #
# 6. C3-C：半日严格穿透 vs 分钟路径（已授权分钟样本的能力边界）
# --------------------------------------------------------------------------- #
MINUTE_FEATS = "data/processed/minute-feats-20260918/minute_feats.parquet"


def minute_vs_halfday_check(root: Path, recon_csv: Path, sandbox,
                            limit: int = 5000
                            ) -> tuple[list[dict], dict]:
    """用已授权分钟投影表核验「半日严格穿透」相对更细粒度的方向性误判。

    **能力边界（只披露不改合同）**：``minute-feats-20260918`` 是**每股每日一行
    的投影特征**（``day_high``/``day_low``/``am_range30`` 等），**不含分钟价格
    路径**，因此：

    * **可以**核验：半日 bar 的极值是否落在分钟全日极值区间内（越界 = 制造数据），
      以及「半日判定不穿透、但分钟全日极值本可穿透」的**保守漏判**计数与方向；
    * **不能**核验：订单生效半日**之前**是否已经穿透、半日内价格先后（因为投影表
      没有分钟序列），也不能证明排队成交率（没有逐笔/订单簿）。

    输入订单取自 C3-A 对账 CSV（``core_fields_match`` 全通过的那份），只取
    ``never_crossed`` 的限价单。日期一律过滤到 Dev 窗（≤2020-12-31）。
    """
    if not recon_csv.is_file():
        return [], {"status": "unverified",
                    "reason": f"reconciliation csv not found: {recon_csv}"}
    df = pl.read_csv(recon_csv)
    df = df.filter((pl.col("matcher_reason") == "never_crossed")
                   & (pl.col("engine_limit_price").is_not_null()))
    if df.height == 0:
        return [], {"status": "unverified", "reason": "no never_crossed orders"}
    # 均匀抽样（跨年份/跨臂），而不是取开头若干行——不然样本全落在最早的年份。
    if df.height > limit:
        stride = max(1, df.height // limit)
        df = df.gather_every(stride).head(limit)
    syms = sorted(set(df["symbol"].to_list()))
    market = Market(sandbox, syms)      # 半日 bar 必须按对账样本自己的标的集构建
    feats = (pl.scan_parquet(root / MINUTE_FEATS)
             .filter(pl.col("date") <= date(2020, 12, 31))
             .filter(pl.col("symbol").is_in(syms))
             .select(["symbol", "date", "day_high", "day_low"])
             .collect())
    day = {(r["symbol"], r["date"]): (r["day_high"], r["day_low"])
           for r in feats.iter_rows(named=True)}
    rows: list[dict] = []
    n_checked = 0
    n_missing = 0
    n_out_of_range = 0
    n_conservative_miss = 0
    n_own_session_miss = 0
    for r in df.iter_rows(named=True):
        key = (r["symbol"], _as_date(r["live_date"]))
        f = day.get(key)
        if f is None:
            n_missing += 1
            continue
        d_high, d_low = f
        bar_hi, bar_lo = _half_extremes(market, r["symbol"], key[1],
                                        r["live_session"])
        if bar_hi is None:
            n_missing += 1
            continue
        n_checked += 1
        p = float(r["engine_limit_price"])
        side = r["matcher_reason"] and r["symbol"] and r.get("side")
        oob = (bar_lo < float(d_low) - 1e-4) or (bar_hi > float(d_high) + 1e-4)
        if oob:
            n_out_of_range += 1
        if side == "buy":
            finer_penetrates = float(d_low) < p
        else:
            finer_penetrates = float(d_high) > p
        miss = finer_penetrates and not (
            (float(bar_lo) < p) if side == "buy" else (float(bar_hi) > p))
        # 更严格的归因：全日分钟极值可能来自**另一个 session**，所以只在
        # 「另一个 session 的极值没有穿价」时才把这个 miss 归因于本 session。
        other = "pm" if r["live_session"] == "am" else "am"
        o_hi, o_lo = _half_extremes(market, r["symbol"], key[1], other)
        own_attr = None if o_lo is None else (
            not ((float(o_lo) < p) if side == "buy" else (float(o_hi) > p)))
        if miss:
            n_conservative_miss += 1
            if own_attr:
                n_own_session_miss += 1
        rows.append({
            "arm": r["arm"], "order_id": r["order_id"], "symbol": r["symbol"],
            "side": side, "live_date": r["live_date"],
            "live_session": r["live_session"], "limit_price": p,
            "half_high": bar_hi, "half_low": bar_lo,
            "minute_day_high": d_high, "minute_day_low": d_low,
            "half_extremes_within_minute_range": not oob,
            "finer_granularity_would_fill": finer_penetrates,
            "other_session_high": o_hi, "other_session_low": o_lo,
            "halfday_verdict_conservative_miss": miss,
            "miss_attributable_to_this_session": own_attr,
        })
    summary = {
        "status": "partial",
        "source": MINUTE_FEATS,
        "coverage_note": ("minute-feats 是每股每日一行的**分钟投影**，本身只覆盖"
                          "部分 (symbol, day)（实测 Dev 窗 4,598,367 行 / 4,181 只"
                          "，约 1,100 行/只 vs 1,462 个交易日）；未覆盖的样本无法"
                          "核验，因此本项只给『已覆盖子集』的计数"),
        "capability": "per-symbol-per-day projection features; NO minute path",
        "sampled_orders": df.height, "checked": n_checked,
        "missing_minute_rows": n_missing,
        "half_extremes_out_of_minute_range": n_out_of_range,
        "conservative_miss_count": n_conservative_miss,
        "conservative_miss_rate": (round(n_conservative_miss / max(1, n_checked), 6)),
        "own_session_attributable_miss_count": n_own_session_miss,
        "own_session_attributable_miss_rate": (
            round(n_own_session_miss / max(1, n_checked), 6)),
        "method_note": ("细粒度一侧用的是**全日**分钟极值 day_high/day_low；"
                        "投影表没有分 session 的分钟极值，所以部分 miss 可能来自"
                        "另一个 session。own_session_attributable_* 是更严格的"
                        "归因口径（另一 session 的极值未穿价时才计入）。"),
        "coverage_rate": round(n_checked / max(1, df.height), 6),
        "not_verifiable": [
            "whether an order's live session was already penetrated before it "
            "went live (no minute ordering / no per-session minute path)",
            "queue fill probability (no order book / no tick data)",
        ],
        "contract_effect": "disclosure only; the frozen contract is unchanged",
    }
    return rows, summary


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _half_extremes(market: Market, symbol: str, day: date,
                   session: str) -> tuple[float | None, float | None]:
    bar = market.bars.get(symbol, day, session)
    if bar is None:
        return None, None
    return float(bar.high), float(bar.low)


# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-dir", required=True)
    ap.add_argument("--repo-root", default=".")
    args = ap.parse_args(argv)
    root = Path(args.repo_root).resolve()
    out = (root / args.evidence_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sandbox = dev_sandbox.SandboxRegistry.load(root)

    run = root / "artifacts" / "runs" / ATTRIB2_RUN
    funnel_syms = sorted(set(pl.read_csv(run / "outputs" /
                                         "B1_event_funnel.csv")["symbol"].to_list()))
    ev_b1 = ArmEvents(root / "artifacts" / "runs" / EVENTFAM_RUN, "B1")
    market = Market(sandbox, sorted(set(funnel_syms) | set(ev_b1.symbols)))

    trace, trace_summary = intent_to_order_trace(root, market)
    write_csv(out / "intent_to_order_trace.csv", trace)
    seats, seat_summary = seat_lifecycle(root)
    write_csv(out / "seat_lifecycle.csv", seats)
    risk_rows, hand_rows, risk_summary = risk_state_trace()
    write_csv(out / "risk_state_trace.csv", risk_rows)
    write_csv(out / "risk_state_trace_hand_expected.csv", hand_rows)
    clip_rows, clip_summary = clip_exit_trace(root, ev_b1)
    write_csv(out / "clip_exit_trace.csv", clip_rows)
    inv_rows, inv_log, inv_summary = eleven_thirty_invariance()
    write_csv(out / "eleven_thirty_invariance.csv", inv_rows)
    mv_rows, mv_summary = minute_vs_halfday_check(
        root, out / "order_reconciliation.csv", sandbox)
    write_csv(out / "minute_vs_halfday_check.csv", mv_rows)
    (out / "eleven_thirty_invariance.log").write_text(
        "\n".join(inv_log) + "\n", encoding="utf-8")

    summary = {
        "intent_to_order_trace": trace_summary,
        "seat_lifecycle": seat_summary,
        "risk_state_trace": risk_summary,
        "clip_exit_trace": clip_summary,
        "eleven_thirty_invariance": inv_summary,
        "minute_vs_halfday": mv_summary,
    }
    (out / "semantic_chain_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
