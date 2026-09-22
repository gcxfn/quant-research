"""C4-DEF-01 证据：FIFO 消耗 vs 逐批风险意图错配的独立调查。

只读 B1 主 run 的既有产物与策略源码文本，不重跑回测、不改任何代码。
产出（stdout）：
  1. 策略侧风险退出（stop/protection）的委托数量口径（源码文本证据）
  2. 真实 B1 成交里每一笔卖出的 held_before / shares，按 exit_reason 分组
  3. 是否存在「risk 类部分卖出」（唯一可能暴露逐批风险错配经济影响的情形）
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
RUN = ROOT / "artifacts/runs/20260921T223157-eventfam-main-cb4cff/outputs"
SRC = ROOT / "src/quant/research/single_name_rules.py"


def main() -> int:
    out: dict = {}
    # ---- 1. 源码文本证据：risk 类（stop/protection）row 不带数量字段 ----
    text = SRC.read_text(encoding="utf-8")
    rules_row_start = text.index("def _row(symbol: str, side: str")
    row_body = text[rules_row_start:rules_row_start + 900]
    # stop/protection 走 intent="risk"，调用点固定不传 target_weight/notional
    risk_calls = [
        ln.strip() for ln in text.splitlines()
        if 'intent="risk"' in ln
    ]
    out["source_risk_call_sites"] = risk_calls
    out["source_row_defaults_quantity"] = (
        'target_weight' in row_body and 'target_notional' in row_body
    )
    # whole-exit 判定：ANY clip 触发 → 整仓退出
    out["whole_exit_comment"] = (
        "exits:  P <= stop_i -> stop (conservative: ANY clip triggering "
        "stop / protection exits the whole symbol)" in text
    )
    out["fifo_disclosure_present"] = (
        "consumes clips FIFO" in text
    )

    # ---- 2. 真实成交：逐笔卖出 vs 当时持仓 ----
    fills = pl.read_parquet(RUN / "B1_fills.parquet").sort(
        ["date", "session", "fill_id"])
    held: dict[str, int] = defaultdict(int)
    sell_rows = []
    buy_rows = 0
    for r in fills.iter_rows(named=True):
        sym = str(r["symbol"])
        sh = int(r["shares"])
        if r["side"] == "buy":
            held[sym] += sh
            buy_rows += 1
        else:
            hb = held[sym]
            sell_rows.append({
                "fill_id": r["fill_id"], "date": str(r["date"]),
                "session": r["session"], "symbol": sym,
                "intent": r["intent"], "shares": sh,
                "held_before": hb, "whole": (sh == hb),
                "oversell": sh > hb,
            })
            held[sym] -= sh
    out["n_buy_fills"] = buy_rows
    out["n_sell_fills"] = len(sell_rows)
    out["oversell_count"] = sum(1 for r in sell_rows if r["oversell"])

    # exit_reason 来自 reason log（按 day/sess/symbol 关联）
    reason = {}
    with (RUN / "B1_exit_reason_log.csv").open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            reason[(r["day"], r["sess"], r["symbol"])] = r["reason"]
    for r in sell_rows:
        r["exit_reason"] = reason.get(
            (r["date"], r["session"], r["symbol"]), "unmapped")

    by_reason = defaultdict(lambda: {"n": 0, "partial": 0, "whole": 0})
    for r in sell_rows:
        g = by_reason[r["exit_reason"]]
        g["n"] += 1
        g["partial" if not r["whole"] else "whole"] += 1
    out["sell_by_exit_reason"] = {k: dict(v) for k, v in sorted(by_reason.items())}

    # 唯一可能暴露逐批风险错配的情形：risk 类且部分卖出
    risk_partial = [r for r in sell_rows
                    if r["intent"] == "risk" and not r["whole"]]
    out["risk_partial_sells"] = risk_partial
    out["risk_partial_count"] = len(risk_partial)

    # risk 类全部卖出明细
    out["risk_sell_detail"] = [r for r in sell_rows if r["intent"] == "risk"]

    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
