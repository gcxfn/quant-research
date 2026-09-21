# -*- coding: utf-8 -*-
"""P2-R6 复核 项6+项9(部分)：三次运行月频一致性；两次作废 run 的缺陷核对。只读。
"""
import json
import polars as pl

R1 = "artifacts/runs/20260917T230609-p2r6-etf-rotation-f1f60270"   # 作废1: 边界强平
R2 = "artifacts/runs/20260917T231139-p2r6-etf-rotation-cf10be51"   # 作废2: 周频缓存键缺频率
R3 = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"   # 正式
MONTHLY = ["C01", "C02", "C05", "C06", "C09", "C10"]
WEEKLY = ["C03", "C04", "C07", "C08", "C11", "C12"]

ms = {}
for tag, r in [("f1f60270", R1), ("cf10be51", R2), ("7b72501d", R3)]:
    ms[tag] = json.load(open(f"{r}/metrics.json", encoding="utf-8"))

print("=" * 100)
print("A. 月频 6 配置 dev 指标三次运行逐位对比")
print("=" * 100)
FIELDS = ["net_cagr", "gross_cagr", "net_total_return", "b1_net_cagr", "max_drawdown", "excess_vs_b1", "execution_rate"]
allok = True
for c in MONTHLY:
    a, b, d = (ms[t]["configs"][c]["dev"] for t in ("f1f60270", "cf10be51", "7b72501d"))
    same = all(a[f] == b[f] == d[f] for f in FIELDS)
    same_years = a["net_return_by_year"] == b["net_return_by_year"] == d["net_return_by_year"] and \
                 a["excess_by_year"] == b["excess_by_year"] == d["excess_by_year"]
    same_turn = a["turnover_by_year"] == b["turnover_by_year"] == d["turnover_by_year"]
    same_conc = a["concentration"] == b["concentration"] == d["concentration"]
    n_same = ms["f1f60270"]["configs"][c]["n_trades"] == ms["cf10be51"]["configs"][c]["n_trades"] == ms["7b72501d"]["configs"][c]["n_trades"]
    allok &= same and same_years and same_turn and same_conc and n_same
    print(f"{c}: dev核心字段逐位一致={same} 逐年一致={same_years} 换手一致={same_turn} 集中度一致={same_conc} n_trades一致={n_same} (n={ms['7b72501d']['configs'][c]['n_trades']})")
print("月频全部逐位一致:", allok)

print()
print("=" * 100)
print("B. 周频 6 配置在 cf10be51(缓存键缺陷) 的表现——文档称 C04 仅 342 笔、周频只在月末会话交易")
print("=" * 100)
for c in WEEKLY:
    print(f"{c}: n_trades f1={ms['f1f60270']['configs'][c]['n_trades']} cf={ms['cf10be51']['configs'][c]['n_trades']} final={ms['7b72501d']['configs'][c]['n_trades']}"
          f" | dev_net f1={ms['f1f60270']['configs'][c]['dev']['net_cagr']*100:.2f}% cf={ms['cf10be51']['configs'][c]['dev']['net_cagr']*100:.2f}% final={ms['7b72501d']['configs'][c]['dev']['net_cagr']*100:.2f}%")

print()
print("=" * 100)
print("C. f1f60270 边界强平缺陷核对（文档称 3 只 status=L ETF 在 2020-12-31 被强平）")
print("=" * 100)
pos1 = pl.read_parquet(f"{R1}/positions.parquet")
fd = pos1.filter(pl.col("exit_kind") == "forced_delist_close")
print("forced_delist_close 行数:", fd.height)
print(fd.select(["config_id", "code", "entry_date", "exit_date", "exit_kind", "pnl"]).sort(["config_id", "code"]))
# 这些代码在最终 run 是否仍上市（status=L）——由注册表核对
fb = pl.read_csv("data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv", infer_schema_length=0)
codes = fd["code"].unique().to_list()
print(fb.filter(pl.col("ts_code").is_in(codes)).select(["ts_code", "status", "delist_date"]))
# final run 的同代码：结转而非强平
pos3 = pl.read_parquet(f"{R3}/positions.parquet")
for code in codes:
    r3 = pos3.filter((pl.col("config_id").is_in(MONTHLY + WEEKLY)) & (pl.col("code") == code))
    print(f"final run {code}: exit_kind 分布:", dict(r3.group_by("exit_kind").len().sort("exit_kind").iter_rows()))

print()
print("=" * 100)
print("D. cf10be51 周频只在月末会话交易核对（取 C04 交易会话样本）")
print("=" * 100)
tr2 = pl.read_parquet(f"{R2}/trades.parquet").filter(pl.col("config_id") == "C04")
sess = sorted(tr2["session"].unique().to_list())
print("C04(cf10be51) 交易会话数:", len(sess), "首10:", [str(s) for s in sess[:10]])
# 是否全部为月首交易日后第一个会话？（粗核：全部是某月的第1-3个交易日）
import collections
dom = collections.Counter(s.day for s in sess)
print("交易日 dom 分布:", dict(sorted(dom.items())))

print()
print("=" * 100)
print("E. 三次运行 gates 判定与 dev_pass 一致性（12/12 淘汰是否三次一致）")
print("=" * 100)
for tag in ("f1f60270", "cf10be51", "7b72501d"):
    g = ms[tag]["gates"]
    verdicts = {c: g[c]["dev"]["dev_pass"] for c in sorted(g)}
    print(f"{tag}: dev_pass_configs={ms[tag]['dev_pass_configs']} advanced={ms[tag]['advanced_to_validation']} "
          f"p3={ms[tag]['p3_candidates']} 全部dev_pass=False: {not any(verdicts.values())}")
