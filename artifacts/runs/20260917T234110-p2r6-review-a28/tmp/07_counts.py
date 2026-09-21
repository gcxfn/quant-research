# -*- coding: utf-8 -*-
"""P2-R6 复核 项7+项8+项10：trades 计数、test 段使用、执行统计、现金口径。只读。
"""
import json
import polars as pl

RUN = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"
m = json.load(open(f"{RUN}/metrics.json", encoding="utf-8"))
CS = ["C%02d" % i for i in range(1, 13)]
tr = pl.read_parquet(f"{RUN}/trades.parquet")
pos = pl.read_parquet(f"{RUN}/positions.parquet")
ctr = tr.filter(pl.col("config_id").str.starts_with("C"))

print("=" * 100)
print("A. exec_stats 12 配置合计 vs 文档 §4")
print("=" * 100)
keys = ["planned_buy_legs", "buys_filled", "buys_no_candidate", "buys_cancelled_slot_busy",
        "planned_sell_legs", "sells_filled", "sells_postponed_then_filled", "sells_forced_delist",
        "sells_pending_at_end", "entry_limit_blocked", "exit_limit_blocked", "entry_suspended",
        "exit_suspended", "legs_executed", "legs_planned"]
tot = {}
for c in CS:
    st = m["configs"][c]["exec_stats"]
    for k in keys:
        tot[k] = tot.get(k, 0) + st[k]
for k in keys:
    print(f"  {k:28s} = {tot[k]}")
DOC = {"planned_buy_legs": 23752, "buys_filled": 23690, "buys_no_candidate": 1655,
       "buys_cancelled_slot_busy": 8, "planned_sell_legs": 4203, "sells_filled": 4139,
       "sells_postponed_then_filled": 10, "sells_forced_delist": 0,
       "entry_limit_blocked": 1004, "exit_limit_blocked": 10}
print("\n  文档对照:")
for k, dv in DOC.items():
    print(f"  {k:28s} 我方合计={tot[k]:6d}  文档={dv:6d}  {'一致' if tot[k]==dv else '<-- 不一致'}")
# 执行率复核（合计口径与逐配置口径）
print("\n  逐配置 execution_rate 范围:", min(m['configs'][c]['dev']['execution_rate'] for c in CS),
      "~", max(m['configs'][c]['dev']['execution_rate'] for c in CS))
gateon = [m["configs"][c]["exec_stats"]["buys_no_candidate"] for c in CS if m["configs"][c]["gate"]]
gateoff = [m["configs"][c]["exec_stats"]["buys_no_candidate"] for c in CS if not m["configs"][c]["gate"]]
print("  无候选空槽: 门开配置合计", sum(gateon), "(范围", min(gateon), "-", max(gateon), ") 门关配置合计", sum(gateoff))

print()
print("=" * 100)
print("B. trades.parquet 计数（文档称 33,879 笔）")
print("=" * 100)
print("  文件总行数:", tr.height)
print("  C01..C12 行数:", ctr.height, "  B3 种子行数:", tr.height - ctr.height)
b3m = tr.filter(pl.col("config_id").str.starts_with("B3-monthly"))
b3w = tr.filter(pl.col("config_id").str.starts_with("B3-weekly"))
print("  其中 B3-monthly:", b3m.height, " B3-weekly:", b3w.height)
print("  C+B3月频 =", ctr.height + b3m.height, " C+B3周频 =", ctr.height + b3w.height)
n_trades_sum = sum(m["configs"][c]["n_trades"] for c in CS)
print("  metrics n_trades 合计:", n_trades_sum)
per_file = dict(ctr.group_by("config_id").len().sort("config_id").iter_rows())
mismatch = [(c, per_file[c], m["configs"][c]["n_trades"]) for c in CS if per_file.get(c) != m["configs"][c]["n_trades"]]
print("  逐配置 trades 行数 vs metrics n_trades 不一致:", mismatch if mismatch else "无")

print()
print("=" * 100)
print("C. C 配置买卖腿构成（对照文档 4,203/4,139/10/36）")
print("=" * 100)
print("  buy 行:", ctr.filter(pl.col("side") == "buy").height)
print("  sell 行:", ctr.filter(pl.col("side") == "sell").height, " 其中 kind 分布:",
      dict(ctr.filter(pl.col("side") == "sell").group_by("kind").len().iter_rows()))
carry = pos.filter(pl.col("exit_kind").is_null())
print("  期末结转持仓:", carry.height, "(12×3 =", 12*3, ")  其中 exit_date 全空:", carry["exit_date"].null_count() == carry.height)
# 结转持仓是否有对应卖出腿
sold_codes = set(zip(ctr.filter(pl.col("side") == "sell")["config_id"].to_list(),
                     ctr.filter(pl.col("side") == "sell")["code"].to_list(),
                     ctr.filter(pl.col("side") == "sell")["entry_date"].to_list()))
carry_pair = [(r["config_id"], r["code"], r["entry_date"]) in sold_codes for r in carry.iter_rows(named=True)]
print("  结转持仓中出现卖出腿的个数:", sum(carry_pair), "/", carry.height)

print()
print("=" * 100)
print("D. test 段使用核验（2023-01-01 之后信号驱动的开仓）")
print("=" * 100)
late_buy = ctr.filter((pl.col("session") >= pl.date(2023, 1, 1)) & (pl.col("side") == "buy"))
late_sell = ctr.filter((pl.col("session") >= pl.date(2023, 1, 1)) & (pl.col("side") == "sell"))
print("  C 配置 2023-01-01 后 buy 行:", late_buy.height, " sell 行:", late_sell.height)
print("  按配置:", dict(late_buy.group_by("config_id").len().sort("config_id").iter_rows()))
last_sess = ctr.group_by("config_id").agg(pl.col("session").max()).sort("config_id")
print(last_sess)
# 决策消费：gates 只含 dev；dev_pass 为空；advanced/p3 为空
print("  gates 段各配置键:", sorted(next(iter(m['gates'].values())).keys()))
print("  dev_pass_configs:", m["dev_pass_configs"], "| advanced_to_validation:", m["advanced_to_validation"],
      "| p3_candidates:", m["p3_candidates"])
# val/test 段指标存在（披露）——报告文档是否只作披露
print("  metrics 含 validation/test 段指标:", "validation" in m["configs"]["C01"] and "test" in m["configs"]["C01"])

print()
print("=" * 100)
print("E. 槽内现金最深负值（metrics.max_negative_cash，全窗）")
print("=" * 100)
vals = {c: m["configs"][c]["max_negative_cash"] for c in CS}
for c in CS:
    print(f"  {c}: {vals[c]:12.2f}")
shallow = min(vals, key=vals.get); deep = max(vals, key=vals.get)
print(f"  最浅: {shallow} {vals[shallow]:.2f}  最深: {deep} {vals[deep]:.2f}")
print(f"  文档对照: C10 = {vals['C10']:.2f} (文档 -11,302) ; C12 = {vals['C12']:.2f} (文档 -40,344) ; C12/20万 = {vals['C12']/200000*100:.1f}%")
print(f"  文档'全窗最深 -11,302(C10) 至 -40,344(C12)'是否为全部12配置的范围: {abs(vals[shallow]) <= 11302.5}")
