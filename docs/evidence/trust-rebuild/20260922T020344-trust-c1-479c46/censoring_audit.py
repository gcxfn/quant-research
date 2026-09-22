# -*- coding: utf-8 -*-
"""C1-08 边界与缺失样本审计：保留 + 标记，而不是删除。

产出 ``censoring_audit.csv``（带 ``record_type`` 判别列的审计长表）：
- ``b1_event_window``：B1 全部 102 事件，用 Dev 沙箱日线独立重算 20 自身
  交易日窗终点，与归档漏斗的 label_end_decision 交叉核对；
- ``boundary_anchor``：每个事件证券的"首个跨 Dev 边界的锚定日"及其实际终点；
- ``delisted_symbol``：Dev 窗口内行情提前终止的证券清单与处理方式；
- ``summary``：边界/缺失样本计数，证明没有删除样本。

运行：.venv/Scripts/python.exe docs/evidence/trust-rebuild/<C1-run>/censoring_audit.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = next(p for p in [HERE.parent, *HERE.parents]
            if (p / "src" / "quant").is_dir() and (p / "data").is_dir())
sys.path.insert(0, str(REPO / "src"))

import polars as pl  # noqa: E402

from quant.data.dev_sandbox import SandboxRegistry  # noqa: E402
from quant.data.temporal_contract import (  # noqa: E402
    DEV_END_DEFAULT, own_session_label_window)

B1_FUNNEL = REPO / ("artifacts/runs/20260922T002611-eventfam-attrib2-eed5cf"
                    "/outputs/B1_event_funnel.csv")
HORIZON = 20
OUT = HERE.parent / "censoring_audit.csv"
DEV_END = DEV_END_DEFAULT
TERMINAL_CUTOFF = date(2020, 12, 24)   # 晚于此仍有行情才算"活到 Dev 末附近"

COLUMNS = ["record_type", "key", "symbol", "family", "anchor_date",
           "label_end_at", "n_own_sessions", "n_market_sessions",
           "window_complete", "crosses_dev_boundary", "censoring_reason",
           "retained", "deleted", "funnel_label_end_decision",
           "label_end_match", "note"]


def main() -> int:
    registry = SandboxRegistry.load(REPO)
    daily = registry.read("bars_daily",
                          columns=["symbol", "date", "close", "tradestatus"])
    tradable = daily.filter(pl.col("tradestatus") == 1.0)
    own_by_symbol: dict[str, list[date]] = {}
    last_date_by_symbol: dict[str, date] = {}
    for (sym,), g in tradable.partition_by("symbol", as_dict=True).items():
        own_by_symbol[str(sym)] = g["date"].sort().to_list()
    for (sym,), g in daily.partition_by("symbol", as_dict=True).items():
        last_date_by_symbol[str(sym)] = g["date"].max()
    market_calendar = sorted(set(tradable["date"].to_list()))
    last_market = market_calendar[-1]

    last_week = set(market_calendar[-5:])

    def truncated_at(symbol: str):
        """Dev 末端仍在交易（最后一行日线落在 Dev 最后一周）→ 面板被边界截断。"""
        return DEV_END if last_date_by_symbol.get(symbol) in last_week else None

    funnel = pl.read_csv(B1_FUNNEL).to_dicts()
    rows: list[dict] = []
    censored = 0
    mismatched = 0
    dec_events = []
    for ev in funnel:
        symbol = ev["symbol"]
        anchor = date.fromisoformat(str(ev["decision_time"])[:10])
        window = own_session_label_window(
            own_by_symbol.get(symbol, []), anchor, HORIZON,
            dev_end=DEV_END, market_calendar=market_calendar,
            panel_truncated_at=truncated_at(symbol))
        funnel_end = date.fromisoformat(str(ev["label_end_decision"]))
        match = window.label_end_at == funnel_end
        if not match:
            mismatched += 1
        if not window.window_complete:
            censored += 1
        if anchor.year == 2020 and anchor.month == 12:
            dec_events.append((ev["event_id"], anchor, window))
        rows.append({
            "record_type": "b1_event_window",
            "key": ev["event_id"],
            "symbol": symbol,
            "family": "B1",
            "anchor_date": anchor.isoformat(),
            "label_end_at": window.label_end_at.isoformat() if window.label_end_at else "",
            "n_own_sessions": window.n_own_sessions,
            "n_market_sessions": window.n_market_sessions,
            "window_complete": window.window_complete,
            "crosses_dev_boundary": window.crosses_dev_boundary,
            "censoring_reason": window.missing_reason or (
                "crosses_dev_boundary" if window.crosses_dev_boundary else ""),
            "retained": True,
            "deleted": False,
            "funnel_label_end_decision": funnel_end.isoformat(),
            "label_end_match": match,
            "note": "窗口不完整/跨界时保留并标记，不进入完整窗口均值",
        })

    # ---- 每个事件证券的首个跨界锚定日 ---------------------------------------- #
    symbols = sorted({ev["symbol"] for ev in funnel})
    boundary_rows = 0
    for symbol in symbols:
        own = own_by_symbol.get(symbol, [])
        first_cross = None
        for anchor in own:
            if anchor < date(2020, 1, 1):
                continue
            w = own_session_label_window(own, anchor, HORIZON, dev_end=DEV_END,
                                         market_calendar=market_calendar,
                                         panel_truncated_at=truncated_at(symbol))
            if w.crosses_dev_boundary or (
                    w.label_end_at is not None and w.label_end_at > DEV_END):
                first_cross = (anchor, w)
                break
        if first_cross is None:
            continue
        boundary_rows += 1
        anchor, w = first_cross
        rows.append({
            "record_type": "boundary_anchor",
            "key": f"{symbol}:{anchor.isoformat()}",
            "symbol": symbol,
            "family": "B1",
            "anchor_date": anchor.isoformat(),
            "label_end_at": w.label_end_at.isoformat() if w.label_end_at else "",
            "n_own_sessions": w.n_own_sessions,
            "n_market_sessions": w.n_market_sessions,
            "window_complete": w.window_complete,
            "crosses_dev_boundary": w.crosses_dev_boundary,
            "censoring_reason": "crosses_dev_boundary",
            "retained": True,
            "deleted": False,
            "funnel_label_end_decision": "",
            "label_end_match": "",
            "note": ("该证券自该日起的 20 自身交易日窗跨入 2021：窗口不完整、保留并标记；"
                     "实际终点落在 2021，需单独授权读取后才能确定，本审计不推算、"
                     f"已实现 {w.n_own_sessions}/20 个自身交易日"),
        })

    # ---- 行情在 Dev 内提前终止的证券 ----------------------------------------- #
    terminated = {s: d for s, d in last_date_by_symbol.items()
                  if d < TERMINAL_CUTOFF and len(own_by_symbol.get(s, [])) > 0}
    for symbol, last in sorted(terminated.items()):
        own = own_by_symbol.get(symbol, [])
        w = own_session_label_window(own, last, HORIZON, dev_end=DEV_END,
                                     market_calendar=market_calendar,
                                     panel_truncated_at=None)
        rows.append({
            "record_type": "delisted_symbol",
            "key": f"{symbol}:{last.isoformat()}",
            "symbol": symbol,
            "family": "B1",
            "anchor_date": last.isoformat(),
            "label_end_at": w.label_end_at.isoformat() if w.label_end_at else "",
            "n_own_sessions": w.n_own_sessions,
            "n_market_sessions": w.n_market_sessions,
            "window_complete": w.window_complete,
            "crosses_dev_boundary": w.crosses_dev_boundary,
            "censoring_reason": "terminated_no_recovery_quote",
            "retained": True,
            "deleted": False,
            "funnel_label_end_decision": "",
            "label_end_match": "",
            "note": ("Dev 面板在该日之后无该证券行情：沙箱物理上不含其后续报价，"
                     "禁止用后来年份报价强行结算；样本保留、标记不可评价"),
        })

    # ---- 汇总 ---------------------------------------------------------------- #
    n_b1 = len(funnel)
    market_anchor_cross = sum(
        1 for anchor in market_calendar
        if (lambda w: w.crosses_dev_boundary)(
            own_session_label_window(market_calendar, anchor, HORIZON,
                                     dev_end=DEV_END,
                                     market_calendar=market_calendar,
                                     panel_truncated_at=DEV_END)))
    summary = {
        "b1_events_total": n_b1,
        "market_sessions_with_window_crossing_dev_boundary": market_anchor_cross,
        "b1_windows_complete": n_b1 - censored,
        "b1_windows_censored": censored,
        "b1_windows_crossing_dev_boundary": sum(
            1 for r in rows if r["record_type"] == "b1_event_window"
            and r["crosses_dev_boundary"]),
        "b1_windows_ended_by_panel_end": sum(
            1 for r in rows if r["record_type"] == "b1_event_window"
            and r["censoring_reason"] == "ended_by_panel_end"),
        "b1_windows_missing_label": sum(
            1 for r in rows if r["record_type"] == "b1_event_window"
            and not r["label_end_at"]),
        "b1_label_end_mismatch_vs_archived": mismatched,
        "b1_events_anchored_2020_12": len(dec_events),
        "b1_2020_12_events_actual_ends": sorted({
            w.label_end_at.isoformat() for _, _, w in dec_events
            if w.label_end_at is not None}),
        "boundary_anchor_symbols": boundary_rows,
        "dev_market_sessions": len(market_calendar),
        "delisted_symbols_in_dev": len(terminated),
        "dev_daily_symbols": len(last_date_by_symbol),
        "last_dev_market_session": last_market.isoformat(),
        "deleted_samples": 0,
        "out": str(OUT.relative_to(REPO)).replace("\\", "/"),
    }
    for name, value in summary.items():
        if isinstance(value, (int, str)):
            rows.append({
                "record_type": "summary", "key": name, "symbol": "", "family": "",
                "anchor_date": "", "label_end_at": str(value),
                "n_own_sessions": "", "n_market_sessions": "", "window_complete": "",
                "crosses_dev_boundary": "", "censoring_reason": "", "retained": "",
                "deleted": "", "funnel_label_end_decision": "",
                "label_end_match": "", "note": "summary",
            })

    with OUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
