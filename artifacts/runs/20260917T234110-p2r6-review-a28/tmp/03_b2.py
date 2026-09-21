# -*- coding: utf-8 -*-
"""P2-R6 复核 项3 v2：从 fund_daily + fund_adj 原始数据独立重算 B2（510300.SH 买入持有）。
市值计价用调整价（含分红总回报）；同时给出不复权口径对照。只读。
"""
import json
from datetime import date
import polars as pl

RUN = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"
m = json.load(open(f"{RUN}/metrics.json", encoding="utf-8"))

px = pl.read_csv("data/raw/tushare/fund_daily/20260917-r1/chunk_510300.SH.csv", infer_schema_length=0)
adj = pl.read_csv("data/raw/tushare/fund_adj/20260917-r1/chunk_510300.SH.csv", infer_schema_length=0)
px = px.with_columns([pl.col("trade_date").str.to_date("%Y%m%d"), pl.col("open").cast(pl.Float64),
                      pl.col("close").cast(pl.Float64)]).sort("trade_date")
adj = adj.with_columns([pl.col("trade_date").str.to_date("%Y%m%d"), pl.col("adj_factor").cast(pl.Float64)]).sort("trade_date")
df = px.join(adj.select(["trade_date", "adj_factor"]), on="trade_date", how="left").with_columns(
    pl.col("adj_factor").fill_null(strategy="forward"))
print("nulls in adj after ffill:", df["adj_factor"].null_count(), " span:", df["trade_date"].min(), "->", df["trade_date"].max())

CAP, COM, MIN5 = 200000.0, 0.0001, 5.0

def seg(entry: str, exit_: str):
    d0 = date(*map(int, entry.split("-"))); d1 = date(*map(int, exit_.split("-")))
    e = df.filter(pl.col("trade_date") == d0); x = df.filter(pl.col("trade_date") == d1)
    po, pxo, fa0 = e["open"][0], e["open"][0], e["adj_factor"][0]
    pc, f1 = x["close"][0], x["adj_factor"][0]
    units = CAP / po
    fee_buy = max(CAP * COM, MIN5)
    proceeds_raw = units * pc                      # 不复权卖出款
    fee_sell_raw = max(proceeds_raw * COM, MIN5)
    net_raw = (proceeds_raw - fee_sell_raw) / (CAP + fee_buy) - 1
    # 调整价口径：买入价 open*f0、卖出市值 close*f1（分红保留在净值内）
    adj_ret = (pc * f1) / (po * fa0) - 1
    proceeds_adj = CAP * (1 + adj_ret)
    fee_sell_adj = max(proceeds_adj * COM, MIN5)
    net_adj = (proceeds_adj - fee_sell_adj) / (CAP + fee_buy) - 1
    return dict(open=po, close=pc, f0=fa0, f1=f1, gross_raw=proceeds_raw / CAP - 1, net_raw=net_raw,
                gross_adj=adj_ret, net_adj=net_adj, fee_buy=fee_buy, fee_sell_adj=fee_sell_adj,
                days=(d1 - d0).days)

for label, ent, ext in [("dev", "2016-01-04", "2020-12-31"),
                        ("validation", "2021-01-04", "2022-12-30"),
                        ("test", "2023-01-03", "2024-12-31")]:
    r = seg(ent, ext)
    mb = m["benchmarks"]["B2"][label]
    print(f"\n[{label}] 重算(调整价): open={r['open']} f0={r['f0']} close={r['close']} f1={r['f1']}")
    print(f"  gross_adj={r['gross_adj']*100:.4f}% net_adj={r['net_adj']*100:.4f}% fee_sell={r['fee_sell_adj']:.4f}")
    print(f"  metrics   : gross={mb['gross_total_return']*100:.4f}% net={mb['net_total_return']*100:.4f}% fee_sell={mb['fees']['sell']:.4f}")
    print(f"  net 逐位一致: {r['net_adj'] == mb['net_total_return']} | gross 逐位一致: {r['gross_adj'] == mb['gross_total_return']} | fee_sell 一致: {abs(r['fee_sell_adj']-mb['fees']['sell'])<1e-9}")
    print(f"  [对照]不复权口径: gross_raw={r['gross_raw']*100:.4f}% net_raw={r['net_raw']*100:.4f}%")
    yf = r["days"] / 365.25
    print(f"  年化(days/365.25): 重算 {((1+r['net_adj'])**(1/yf)-1)*100:.4f}% vs metrics {mb['net_cagr']*100:.4f}%")

r = seg("2016-01-04", "2020-12-31")
print(f"\n文档对照: dev 累计 net {r['net_adj']*100:.2f}%（文档 +51.2%）；费用合计 {r['fee_buy']+r['fee_sell_adj']:.2f} 元（文档 50.24）；年化 {((1+r['net_adj'])**(365.25/r['days'])-1)*100:.3f}%（文档 +8.64%）")
