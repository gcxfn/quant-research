# -*- coding: utf-8 -*-
"""P2-R6 复核 项5：换手定义复核。年单边=年买入名义/年均权益（dev 年取最大）。
从 trades.parquet 求和年买入名义，从 equity_curves.parquet 求年均权益；对照 metrics 与文档（C10=587%）。
只读。
"""
import json
import polars as pl

RUN = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"
m = json.load(open(f"{RUN}/metrics.json", encoding="utf-8"))
tr = pl.read_parquet(f"{RUN}/trades.parquet").filter(pl.col("config_id").str.starts_with("C"))
eq = pl.read_parquet(f"{RUN}/equity_curves.parquet")

print(f"{'cfg':4s} {'year':4s} {'buy_notional(trades)':>22s} {'buy_notional(metrics)':>22s} {'mean_eq(curve)':>16s} {'mean_eq(metrics)':>16s} {'to(重算)':>9s} {'to(metrics)':>11s}")
diffs = []
for c in sorted(tr["config_id"].unique().to_list()):
    dev = m["configs"][c]["dev"]
    for y in ["2016", "2017", "2018", "2019", "2020"]:
        buys = tr.filter((pl.col("config_id") == c) & (pl.col("side") == "buy") &
                         (pl.col("session").dt.year() == int(y)))
        bn = buys["notional"].sum()
        curve = eq.filter((pl.col("config_id") == c) & (pl.col("session").dt.year() == int(y)))
        me = curve["equity_net"].mean()
        to = bn / me
        mt = dev["turnover_by_year"][y]
        flag = "" if abs(bn - mt["buy_notional"]) < 1e-6 and abs(me - mt["mean_equity"]) < 1e-6 else "  <-- DIFF"
        if flag:
            diffs.append((c, y, bn, mt["buy_notional"], me, mt["mean_equity"], to, mt["one_side_turnover"]))
        if y in ("2016", "2020") or flag or c in ("C10", "C03", "C11"):
            print(f"{c:4s} {y:4s} {bn:22.4f} {mt['buy_notional']:22.4f} {me:16.2f} {mt['mean_equity']:16.2f} {to*100:8.2f}% {mt['one_side_turnover']*100:10.2f}%{flag}")
print("\n重算 vs metrics 不一致项:", diffs if diffs else "无")

print("\n各配置 dev 年最大单边换手（重算）:")
for c in sorted(m["configs"].keys()):
    dev = m["configs"][c]["dev"]
    vals = {}
    for y in ["2016", "2017", "2018", "2019", "2020"]:
        buys = tr.filter((pl.col("config_id") == c) & (pl.col("side") == "buy") &
                         (pl.col("session").dt.year() == int(y)))
        bn = buys["notional"].sum()
        me = eq.filter((pl.col("config_id") == c) & (pl.col("session").dt.year() == int(y)))["equity_net"].mean()
        vals[y] = bn / me
    mymax = max(vals, key=vals.get)
    print(f"{c}: max={vals[mymax]*100:7.2f}% ({mymax})  metrics={dev['max_one_side_turnover']*100:7.2f}% 逐年=" +
          ", ".join(f"{y}:{v*100:.0f}%" for y, v in vals.items()))

# C10 明细 vs 文档 587%
c10 = m["configs"]["C10"]["dev"]["turnover_by_year"]
print("\nC10 metrics 逐年:", {y: round(v['one_side_turnover']*100, 1) for y, v in c10.items()},
      "-> max", round(m["configs"]["C10"]["dev"]["max_one_side_turnover"]*100, 1), "% (文档 587%)")
