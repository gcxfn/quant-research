# -*- coding: utf-8 -*-
"""C1-06 预告历史版本与字段合法性审计（读 Dev 沙箱，不跑策略）。

产出：
- ``announcement_version_audit.csv``：B 家族预告源在 Dev 窗口内
  （ann_date 2018-09-04..2020-12-31）逐版本行的字段与合法性审计；
- ``b1_102_field_spotcheck.csv``：对归档归因 run 的 B1 全部 102 事件
  逐条做字段抽核（身份匹配 + 用冻结合同规则独立重算 type_upgrade /
  numeric_revision 并与归档标志比较）。

结论写进 CSV 的两列 ``version_evidence_class`` 与 ``pit_conclusion``，
并在 stdout 打印汇总；不在脚本里改写任何源数据。

运行：.venv/Scripts/python.exe docs/evidence/trust-rebuild/<C1-run>/announcement_version_audit.py
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = next(p for p in [HERE.parent, *HERE.parents]
            if (p / "src" / "quant").is_dir() and (p / "data").is_dir())
sys.path.insert(0, str(REPO / "src"))

import polars as pl  # noqa: E402

from quant.data.dev_sandbox import SandboxRegistry  # noqa: E402
from quant.data.dev_sandbox_export import ts_code_to_symbol  # noqa: E402
from quant.data.temporal_contract import (  # noqa: E402
    INTERVAL_INVALID, INTERVAL_MISSING, INTERVAL_POINT, INTERVAL_VALID,
    classify_forecast_interval)

B1_FUNNEL = REPO / ("artifacts/runs/20260922T002611-eventfam-attrib2-eed5cf"
                    "/outputs/B1_event_funnel.csv")
B_DEV_FIRST, B_DEV_LAST = date(2018, 9, 4), date(2020, 12, 31)
OUT_AUDIT = HERE.parent / "announcement_version_audit.csv"
OUT_SPOT = HERE.parent / "b1_102_field_spotcheck.csv"

# 与 src/quant/research/event_family_signals.py 的冻结全序一致的本地副本；
# 启动时与源模块交叉核对，不一致就报错（防止审计静默偏离已冻结排序）。
TYPE_ORDER_LOCAL = {
    "首亏": -4, "续亏": -3, "预减": -2, "略减": -1, "不确定": 0,
    "续盈": 1, "略增": 2, "扭亏": 3, "预增": 4,
}


def main() -> int:
    from quant.research.event_family_signals import TYPE_ORDER
    if dict(TYPE_ORDER) != TYPE_ORDER_LOCAL:
        raise SystemExit("TYPE_ORDER in research module differs from the frozen "
                         "audit copy; register the conflict instead of guessing")

    registry = SandboxRegistry.load(REPO)
    fc = registry.read("forecast_event")
    manifest_src = json.loads(
        (REPO / "data/raw/tushare/forecast/20260909-r1/manifest.json")
        .read_text(encoding="utf-8"))

    rows = fc.to_dicts()
    for r in rows:
        r["symbol"] = ts_code_to_symbol(r["ts_code"])
        r["interval_class"] = classify_forecast_interval(r["net_profit_min"],
                                                         r["net_profit_max"])
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["symbol"] is None:
            continue
        groups[(r["symbol"], str(r["end_date"]))].append(r)

    interval_counts = Counter(r["interval_class"] for r in rows)
    same_day = Counter()
    multi_version_groups = 0
    version_rows: list[dict] = []
    version_index: dict[tuple, dict] = {}
    for (symbol, end_date) in sorted(groups):
        versions = sorted(groups[(symbol, end_date)],
                          key=lambda r: (str(r["ann_date"]),
                                         str(r["update_flag"] or "0")))
        if len(versions) > 1:
            multi_version_groups += 1
        per_day = Counter(str(v["ann_date"]) for v in versions)
        for d, n in per_day.items():
            if n > 1:
                same_day[(symbol, end_date, d)] = n
        for idx, v in enumerate(versions):
            prev = versions[idx - 1] if idx > 0 else None
            key = (symbol, end_date, str(v["ann_date"]),
                   str(v["update_flag"] or "0"))
            version_index[key] = {"version_index": idx + 1,
                                  "n_versions": len(versions),
                                  "prev": prev}
            cls = ("multi_version_snapshot"
                   if len(versions) > 1 else "single_version_snapshot")
            if len(versions) == 1:
                pit = ("no_comparable_history_in_snapshot；该财务期只有一行，"
                       "不能据快照作修订结论，也不得假设该唯一版本在公告当时可得")
            else:
                pit = ("as_fetched_version_chain_available；快照保留了多版本行"
                       "（ann_date/update_flag 排序可复现），可作修订比较的线索；"
                       "但快照抓取于 2026-09-09，字段值是否为公告当时原值无独立证据，"
                       "因此该组只具『版本存在性与顺序』证据，不具完整 PIT 证据")
            version_rows.append({
                "ts_code": v["ts_code"],
                "symbol": symbol,
                "end_date": str(v["end_date"]),
                "ann_date": str(v["ann_date"]),
                "update_flag": str(v["update_flag"] or ""),
                "version_index": idx + 1,
                "n_versions_in_period": len(versions),
                "same_day_version_count": per_day[str(v["ann_date"])],
                "type": v["type"],
                "type_order": TYPE_ORDER_LOCAL.get(v["type"], 0),
                "p_change_min": v["p_change_min"],
                "p_change_max": v["p_change_max"],
                "net_profit_min": v["net_profit_min"],
                "net_profit_max": v["net_profit_max"],
                "interval_class": v["interval_class"],
                "first_ann_date": str(v["first_ann_date"]),
                "prev_ann_date": str(prev["ann_date"]) if prev else "",
                "prev_update_flag": str(prev["update_flag"] or "") if prev else "",
                "prev_type": prev["type"] if prev else "",
                "has_later_version": idx + 1 < len(versions),
                "source_fetched_at": manifest_src.get("created_at", ""),
                "version_evidence_class": cls,
                "pit_conclusion": pit,
            })

    fieldnames = list(version_rows[0].keys())
    with OUT_AUDIT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(version_rows)

    # ---- B1 102 事件字段抽核 ------------------------------------------------- #
    funnel = pl.read_csv(B1_FUNNEL).to_dicts()
    spot_rows = []
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["symbol"] is None:
            continue
        by_key[(r["symbol"], str(r["end_date"]))].append(r)
    for ev in funnel:
        symbol = ev["symbol"]
        end_date, _, uflag = str(ev["announcement_version"]).partition("#u")
        update_flag = uflag or "0"
        ann_date = str(ev["ann_date"])
        candidates = [r for r in by_key.get((symbol, end_date), [])
                      if str(r["ann_date"]) == ann_date
                      and str(r["update_flag"] or "0") == update_flag]
        versions = sorted(by_key.get((symbol, end_date), []),
                          key=lambda r: (str(r["ann_date"]),
                                         str(r["update_flag"] or "0")))
        idx = next((i for i, v in enumerate(versions)
                    if str(v["ann_date"]) == ann_date
                    and str(v["update_flag"] or "0") == update_flag), None)
        cur = versions[idx] if idx is not None else None
        prev = versions[idx - 1] if idx not in (None, 0) else None
        re_type = re_num = re_avail = ""
        if cur is not None and prev is not None:
            re_type = (TYPE_ORDER_LOCAL.get(cur["type"], 0)
                       > TYPE_ORDER_LOCAL.get(prev["type"], 0))
            try:
                pmin, pmax = float(prev["net_profit_min"]), float(prev["net_profit_max"])
                cmin, cmax = float(cur["net_profit_min"]), float(cur["net_profit_max"])
                assert pmax > pmin and cmax > cmin
                re_avail = True
                re_num = ((pmin + pmax) / 2 < (cmin + cmax) / 2) and (cmin >= pmin)
            except (TypeError, ValueError, AssertionError):
                re_avail = False
                re_num = False
        spot_rows.append({
            "event_id": ev["event_id"],
            "symbol": symbol,
            "end_date": end_date,
            "ann_date": ann_date,
            "update_flag": update_flag,
            "source_rows_matched": len(candidates),
            "has_previous_version": prev is not None,
            "funnel_type_upgrade": bool(ev["type_upgrade"]),
            "recomputed_type_upgrade": re_type,
            "type_upgrade_match": str(bool(ev["type_upgrade"])) == str(re_type),
            "funnel_numeric_revision": bool(ev["numeric_revision"]),
            "recomputed_numeric_revision": re_num,
            "numeric_revision_match": str(bool(ev["numeric_revision"])) == str(re_num),
            "funnel_numeric_available": bool(ev["numeric_available"]),
            "recomputed_numeric_available": re_avail,
            "numeric_available_match": str(bool(ev["numeric_available"])) == str(re_avail),
            "current_type": cur["type"] if cur else "",
            "previous_type": prev["type"] if prev else "",
            "current_net_profit_min": cur["net_profit_min"] if cur else "",
            "current_net_profit_max": cur["net_profit_max"] if cur else "",
            "previous_net_profit_min": prev["net_profit_min"] if prev else "",
            "previous_net_profit_max": prev["net_profit_max"] if prev else "",
        })
    with OUT_SPOT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(spot_rows[0].keys()))
        writer.writeheader()
        writer.writerows(spot_rows)

    summary = {
        "forecast_rows_in_source_window": len(rows),
        "financial_period_groups": len(groups),
        "groups_with_multiple_versions": multi_version_groups,
        "groups_with_same_day_multiple_versions": len(same_day),
        "interval_class_counts": dict(interval_counts),
        "non_standard_codes_dropped": sum(1 for r in rows if r["symbol"] is None),
        "source_batch": "tushare forecast 20260909-r1",
        "source_fetched_at": manifest_src.get("created_at"),
        "b1_events_audited": len(spot_rows),
        "b1_source_rows_matched_all": all(r["source_rows_matched"] == 1 for r in spot_rows),
        "b1_type_upgrade_mismatches": sum(1 for r in spot_rows if not r["type_upgrade_match"]),
        "b1_numeric_revision_mismatches": sum(1 for r in spot_rows if not r["numeric_revision_match"]),
        "b1_numeric_available_mismatches": sum(1 for r in spot_rows if not r["numeric_available_match"]),
        "b1_events_without_previous_version": sum(1 for r in spot_rows if not r["has_previous_version"]),
        "out_audit": str(OUT_AUDIT.relative_to(REPO)).replace("\\", "/"),
        "out_spotcheck": str(OUT_SPOT.relative_to(REPO)).replace("\\", "/"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
