# -*- coding: utf-8 -*-
"""真实 ex_cum_factor.h5 因子比检验（双签审阅 · 真实数据风险探针）。

引擎把 ex_cum_factor 的相邻比值当作"份额乘数"在除权日缩放持股（band_engine.py
step 1: corp_action_split）。若该 bundle 的因子实际是"价格复权因子"（含现金分红
调整），则在纯除息日 ratio != 1 会错误缩股 + 叠加现金分红双重计入。

只读检验：
 1) 600000.XSHG 2022-07-21（manifest 注明的除息变更点）前后因子值与比值；
 2) 全体变更点的比值分布（识别"接近 1 但不为 1"的分红型比值）；
 3) 抽样变更点与日线面板对照：比值 vs 次日价格跳变的构成。
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import date

import numpy as np

ROOT = r"D:\量化"
sys.path.insert(0, ROOT + r"\src")

import h5py  # noqa: E402
import polars as pl  # noqa: E402

H5 = ROOT + r"\data\processed\rqalpha-bundle-v2-1-20260918\ex_cum_factor.h5"
DAILY = ROOT + r"\data\processed\baostock-daily-20260917\daily_1999_2024.parquet"

# --- 1) 600000.XSHG ----------------------------------------------------------
with h5py.File(H5, "r") as h5:
    print("== 600000.XSHG 全部变更点（尾部 12 行）==")
    arr = h5["600000.XSHG"][:]
    print(f"    columns: {arr.dtype.names}")
    starts = arr["start_date"].astype(np.int64)
    vals = arr["ex_cum_factor"].astype(np.float64)
    tail = list(zip(starts, vals))[-12:]
    prev_v = None
    for s, v in tail:
        ratio = (v / prev_v) if prev_v not in (None, 0) else float("nan")
        print(f"    start_date {s}  ex_cum_factor {v:.10f}  ratio_vs_prev {ratio:.10f}")
        prev_v = v
    # 2022-07-21 = 20220721
    idx = int(np.searchsorted(starts, 20220721))
    if idx < len(starts) and starts[idx] == 20220721:
        r = vals[idx] / vals[idx - 1] if idx > 0 else float("nan")
        print(f"    2022-07-21 存在变更点: factor {vals[idx]:.10f}, prev {vals[idx-1]:.10f}, "
              f"ratio {r:.10f}")
    else:
        near = starts[max(0, idx - 2): idx + 2]
        print(f"    2022-07-21 无精确变更点；邻近: {near}")

# --- 2) 全体比值分布 ---------------------------------------------------------
ratios_all: list[float] = []
near1 = Counter()
with h5py.File(H5, "r") as h5:
    for oid in h5:
        a = h5[oid][:]
        v = a["ex_cum_factor"].astype(np.float64)
        if len(v) < 2:
            continue
        r = v[1:] / v[:-1]
        ratios_all.append(r)
ratios = np.concatenate(ratios_all)
print("\n== 全体相邻比值分布（n={}）==".format(len(ratios)))
print(f"    min {ratios.min():.6f}  max {ratios.max():.6f}")
for lo, hi, label in [(0.0, 0.5, "<0.5"), (0.5, 0.9, "0.5-0.9"), (0.9, 0.99, "0.9-0.99"),
                      (0.99, 0.999, "0.99-0.999"), (0.999, 1.001, "≈1.0(±0.001)"),
                      (1.001, 1.01, "1.001-1.01"), (1.01, 1.1, "1.01-1.1"),
                      (1.1, 2.0, "1.1-2.0"), (2.0, 100.0, ">2.0")]:
    n = int(((ratios >= lo) & (ratios < hi)).sum())
    print(f"    [{label:14s}] {n:6d}  ({n / len(ratios) * 100:5.2f}%)")

# --- 3) 与日线面板对照：600000 2022-07-21 价格跳变构成 ----------------------
daily = pl.scan_parquet(DAILY).filter(
    (pl.col("symbol") == "sh.600000")
    & (pl.col("date") >= date(2022, 7, 18))
    & (pl.col("date") <= date(2022, 7, 22))).select(
    "date", "open", "high", "low", "close", "tradestatus").collect()
print("\n== sh.600000 2022-07-18..22 日线（未复权口径应显示除息跳空）==")
print(daily)

# 对照：已知送转样例 —— 找一个比值 ≈ 1.5/2.0 的变更点看其日线跳变
print("\n== 抽查 3 个大比值(≈送转)与 3 个近 1 比值变更点的价格行为 ==")
with h5py.File(H5, "r") as h5:
    big_samples, near1_samples = [], []
    for oid in sorted(h5):
        if len(big_samples) >= 3 and len(near1_samples) >= 3:
            break
        a = h5[oid][:]
        if len(a) < 2:
            continue
        s = a["start_date"].astype(np.int64)
        v = a["ex_cum_factor"].astype(np.float64)
        r = v[1:] / v[:-1]
        for j, rr in enumerate(r):
            sd = int(s[j + 1])
            if not (19990101 <= sd <= 20241231):
                continue
            if rr > 1.4 and len(big_samples) < 3:
                big_samples.append((oid, sd, float(v[j]), float(v[j + 1]), float(rr)))
            elif 0.99 < rr < 1.01 and len(near1_samples) < 3:
                near1_samples.append((oid, sd, float(v[j]), float(v[j + 1]), float(rr)))
    for tag, samples in (("送转型", big_samples), ("近1型", near1_samples)):
        for oid, sd, v0, v1, rr in samples:
            code, exch = oid.split(".")
            mkt = {"XSHG": "sh", "XSHE": "sz"}.get(exch, "??")
            sym = f"{mkt}.{code}"
            y, m, dd = sd // 10000, sd // 100 % 100, sd % 100
            row = (pl.scan_parquet(DAILY)
                   .filter((pl.col("symbol") == sym)
                           & (pl.col("date") >= date(y, m, dd) - __import__("datetime").timedelta(days=10))
                           & (pl.col("date") <= date(y, m, dd)))
                   .select("date", "open", "close").sort("date").collect())
            if row.height >= 2:
                pc = row["close"][-2]
                o = row["open"][-1]
                gap = o / pc - 1
                print(f"    [{tag}] {oid} {sd} ratio {rr:.6f}: 前收 {pc:.2f} -> 当日开 {o:.2f} "
                      f"跳空 {gap * 100:+.2f}%")
