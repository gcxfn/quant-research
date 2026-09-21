#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主对话独立验收：T1 事件研究主判定与类别级数字自写重算。

独立边界：adj_h20（月份调整收益）与 y_wd（type 内去均值）直接用 run 产物列，
但两者的构造口径各抽点复核；ANOVA/类别级 t/BH 全部自写重算对比 anova_main.json
与 primary_within_type.csv。
"""
import json

import numpy as np
import polars as pl
from scipy import stats

RUN = r"D:/量化/artifacts/runs/20260920T113527-t1-reason-event-b690"
df = pl.read_parquet(RUN + r"/outputs/events_dev.parquet")
a = json.load(open(RUN + r"/outputs/anova_main.json", encoding="utf-8"))

# --- 1. adj_h20 与 y_wd 构造复核（抽点） -----------------------------------
by_month = df.group_by("month").agg(pl.col("fwd_h20").mean().alias("m_mean"),
                                     pl.len().alias("m_n"))
j = df.join(by_month, on="month")
d_adj = (j["fwd_h20"] - j["m_mean"] - j["adj_h20"]).abs().max()
by_type = df.group_by("type").agg(pl.col("adj_h20").mean().alias("t_mean"))
k = df.join(by_type, on="type")
d_ywd = (k["adj_h20"] - k["t_mean"] - k["y_wd"]).abs().max()
print(f"adj_h20 rebuild max|diff| = {d_adj:.2e}   y_wd rebuild max|diff| = {d_ywd:.2e}")

# --- 2. ANOVA 自写重算 -------------------------------------------------------
y = df["y_wd"].to_numpy()
g = df["primary_code"].to_numpy().astype(object)
# prereg: classes with n<100 merged into 'other' (report merged accounting/fx)
import collections
cnt = collections.Counter(g)
for name in list(cnt):
    if cnt[name] < 100 and name != 'other':
        g[g == name] = 'other'
        cnt['other'] = cnt.get('other', 0) + cnt.pop(name)
groups = sorted(set(g))
k_n, n = len(groups), len(y)
ss_b = sum(len(y[g == name]) * (y[g == name].mean() - y.mean()) ** 2 for name in groups)
ss_w = sum(((y[g == name] - y[g == name].mean()) ** 2).sum() for name in groups)
F = (ss_b / (k_n - 1)) / (ss_w / (n - k_n))
p = stats.f.sf(F, k_n - 1, n - k_n)
print(f"ANOVA: F={F:.10f} (rep {a['F']:.10f})  p={p:.3e} (rep {a['p']:.3e})  "
      f"k={k_n}/{a['k']}  n={n}/{a['n']}  eta2={ss_b/(ss_b+ss_w):.6f} (rep {a['eta_squared']:.6f})")

# --- 3. 类别级 Welch t + BH 自写重算（每类 vs 同 type 其余） ------------------
rows = []
for name in groups:
    m = g == name
    yi = y[m]
    rest_mask = (~m) & np.isin(
        df["type"].to_numpy(),
        sorted(set(df["type"].to_numpy()[m])))  # same-type others only
    yr_ = y[rest_mask]
    t, pv = stats.ttest_ind(yi, yr_, equal_var=False)
    rows.append({"primary": name, "n": int(m.sum()), "t": t, "p": pv,
                 "mean": yi.mean(), "rest_mean": yr_.mean()})
res = pl.DataFrame(rows).sort("p")
ps = res["p"].to_numpy()
order = np.argsort(ps)
m_ = len(ps)
bh = np.minimum.accumulate((ps[order] * m_ / (np.arange(m_) + 1))[::-1])[::-1]
p_bh_map = {str(groups_key): 0.0 for groups_key in [None]}
p_bh_col = [0.0] * m_
for rank, idx in enumerate(order):
    p_bh_col[idx] = bh[rank]
res = res.with_columns(pl.Series("p_bh", p_bh_col))
sig = res.filter(pl.col("p_bh") < 0.05)
print("BH-significant classes (independent):")
print(sig.to_pandas().to_string())

rep = pl.read_csv(RUN + r"/outputs/primary_within_type.csv")
print()
print("reported BH-significant:")
print(rep.filter(pl.col("p_bh") < 0.05).to_pandas().to_string())
for name in sig["primary"].to_list():
    r_ = rep.filter(pl.col("primary") == name)
    if r_.height:
        print(f"{name}: t indep={float(sig.filter(pl.col('primary')==name)['t'][0]):.4f} "
              f"rep={float(r_['t'][0]):.4f} | p_bh indep={float(sig.filter(pl.col('primary')==name)['p_bh'][0]):.4f} "
              f"rep={float(r_['p_bh'][0]):.4f}")

# --- 4. epidemic 全 2020 与 impairment 分年验证 ------------------------------
ev = df.filter(pl.col("primary_code") == "epidemic_shock")
print(f"\nepidemic_shock: n={ev.height}, years={sorted(set(ev['ann_date'].dt.year().to_list()))}")
imp = df.filter(pl.col("primary_code") == "impairment")
yr_imp = imp.group_by(pl.col("ann_date").dt.year().alias("yr")).agg(
    pl.col("y_wd").mean().alias("mean_ywd"), pl.len().alias("n")).sort("yr")
print("impairment by year (y_wd mean):")
print(yr_imp.to_pandas().to_string())
