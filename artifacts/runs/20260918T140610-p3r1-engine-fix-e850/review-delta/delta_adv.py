# -*- coding: utf-8 -*-
"""增量复审 · 对抗复验（只读仓库；TEMP 仅放自建合成 h5）。

 a) 真实 sh.600000 2022-07-21 纯派息日（真实日线 bar + 真实 split/dividend 行）：
    份额不变、现金 = 0.41 x 1000、权益恒等式（权益变动 = 分红 + 市值变动，无重复计入）；
 b) 真实 sh.600000 2017-05-25 送转 x1.3 + 分红同日：份额 x1.3、分红按除权前 1000 股
    = 200.00、无权益双重计入；并对照 ex_cum_factor 同日比值 1.3166（记录修复依据）；
 c) 50 只样本扫描：split/dividend 行数与 h5 原行一致性；split 值分布（<1 / ==1 /
    同日重复）；round_lot 分布；锚点行数；
 d) F2 loader 回归（自建合成 h5，锚点丢弃、首事件按行值直接生效）；
 e) F5：显式非整手卖出被拒 + 公司行动零股一次性卖出 + odd_lot_exits 计数；
 f) F6：stats 中 deferred_limitdown 定义字段存在；
 g) 防御性：把 ex_cum_factor 帧误传为 splits 必须被列名校验拒绝。
"""
from __future__ import annotations

import sys
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(r"D:\量化")
BUNDLE = ROOT / "data" / "processed" / "rqalpha-bundle-v2-1-20260918"
sys.path.insert(0, str(ROOT / "src"))

import h5py  # noqa: E402

from quant.backtest.band_engine import (  # noqa: E402
    BandContractError, load_dividends_h5, load_split_factor_h5, run_band_backtest)

D = date
SIG = {"symbol": pl.String, "signal_date": pl.Date, "side": pl.String,
       "anchor_price": pl.Float64, "priority": pl.Int64,
       "target_notional": pl.Float64, "shares": pl.Int64, "expiry_date": pl.Date}
FAILS: list[str] = []
PASS = 0


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK ] {label}")
    else:
        FAILS.append(label)
        print(f"  [FAIL] {label}")


def sig(symbol, sd, side, anchor, priority=1, target=None, shares=None):
    return {"symbol": symbol, "signal_date": sd, "side": side,
            "anchor_price": float(anchor), "priority": priority,
            "target_notional": None if target is None else float(target),
            "shares": shares, "expiry_date": None}


def real_bars(symbol, d1, d2):
    return (pl.scan_parquet(ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet")
            .filter((pl.col("symbol") == symbol) & (pl.col("date") >= d1) & (pl.col("date") <= d2))
            .select("symbol", "date", "open", "high", "low", "close", "tradestatus")
            .sort("date").collect())


def run(signals, daily, limits, splits=None, divs=None, cash=200_000.0):
    return run_band_backtest(pl.DataFrame(signals, schema=SIG), daily, limits,
                             splits, divs, initial_cash=cash)


def auto_lim(daily):
    return daily.select("symbol", "date",
                        (pl.col("close") * 1.1).alias("limit_up"),
                        (pl.col("close") * 0.9).alias("limit_down"))


# --- 真实行值 ----------------------------------------------------------------
splits_all, smeta = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, dmeta = load_dividends_h5(BUNDLE / "dividends.h5")
print(f"== loaders on real bundle: split keys={smeta['keys']} rows={smeta['rows']} "
      f"anchors_dropped={smeta['anchor_rows_dropped']}; "
      f"dividends keys={dmeta['keys']} rows={dmeta['rows']} ==")

with h5py.File(BUNDLE / "split_factor.h5", "r") as h:
    print(f"    split_factor dtype names: {h['600000.XSHG'].dtype.names}")
with h5py.File(BUNDLE / "dividends.h5", "r") as h:
    print(f"    dividends dtype names: {h['600000.XSHG'].dtype.names}")
    arr = h["600000.XSHG"][:]
    ex = arr["ex_dividend_date"].astype(np.int64)   # 8 位 YYYYMMDD（决策文档 unit-008）
    cashv = arr["dividend_cash_before_tax"].astype(np.float64)
    lot = arr["round_lot"].astype(np.int64)
    for target in (20220721, 20170525):
        hits = np.where(ex == target)[0]
        if len(hits) == 0:
            print(f"    sh.600000 {target}: 无 dividends 行!")
        else:
            i = int(hits[0])
            print(f"    sh.600000 {target}: cash_per_lot {cashv[i]} round_lot {lot[i]}")

sp6 = splits_all.filter(pl.col("symbol") == "sh.600000").sort("ex_date")
print(f"    sh.600000 split rows: {sp6.rows()}")

# =============================================================================
print("== (a) 真实 600000 2022-07-21 纯派息：份额不变 + 0.41 x 1000 + 权益恒等 ==")
daily = real_bars("sh.600000", D(2022, 7, 18), D(2022, 7, 25))
print(daily)
limits = auto_lim(daily)
signals = [sig("sh.600000", D(2022, 7, 19), "buy", 7.81, 1, shares=1000),
           sig("sh.600000", D(2022, 7, 20), "sell", 7.79)]
res = run(signals, daily, limits, splits=splits_all, divs=divs_all)
bf = res.fills.filter(pl.col("side") == "buy").row(0, named=True)
check((bf["date"], bf["shares"], bf["price"]) == (D(2022, 7, 20), 1000, 7.81),
      f"07-20 买入 1000@7.81: {(bf['date'], bf['shares'], bf['price'])}")
check(res.events.filter(pl.col("event") == "corp_action_split").height == 0,
      "纯派息日无份额变更事件")
dv = res.events.filter(pl.col("event") == "corp_action_dividend").row(0, named=True)
check(dv["date"] == D(2022, 7, 21) and abs(dv["cash_amount"] - 410.0) < 1e-9,
      f"07-21 分红 41.0/100 x 1000(除权前股数) = 410.00: {(dv['date'], dv['cash_amount'])}")
sf = res.fills.filter(pl.col("side") == "sell").row(0, named=True)
check((sf["date"], sf["shares"], sf["price"]) == (D(2022, 7, 22), 1000, 7.33),
      f"07-22 卖出份额仍为 1000（派息不改股数）@7.33: {(sf['date'], sf['shares'], sf['price'])}")
e20 = res.daily.filter(pl.col("date") == D(2022, 7, 20)).row(0, named=True)["equity"]
e21 = res.daily.filter(pl.col("date") == D(2022, 7, 21)).row(0, named=True)["equity"]
lhs = e21 - e20
rhs = 410.0 + 1000 * (7.33 - 7.79)
check(abs(lhs - rhs) < 1e-6,
      f"权益恒等: Δequity {lhs:.6f} = 分红410 + 市值变动{1000 * (7.33 - 7.79):.2f} = {rhs:.6f}"
      "（无重复计入）")

# =============================================================================
print("== (b) 真实 600000 2017-05-25 送转x1.3 + 分红同日 ==")
daily = real_bars("sh.600000", D(2017, 5, 23), D(2017, 6, 2))
print(daily)
close_prev = daily.filter(pl.col("date") == D(2017, 5, 24))["close"][0]
close_ex = daily.filter(pl.col("date") == D(2017, 5, 25))["close"][0]
low_24 = daily.filter(pl.col("date") == D(2017, 5, 24))["low"][0]
anchor = float(daily.filter(pl.col("date") == D(2017, 5, 23))["close"][0])
assert low_24 < anchor, "需 05-24 low < 05-23 close 才能建仓；若不满足请调锚"
limits = auto_lim(daily)
signals = [sig("sh.600000", D(2017, 5, 23), "buy", anchor, 1, shares=1000)]
res = run(signals, daily, limits, splits=splits_all, divs=divs_all)
bf = res.fills.filter(pl.col("side") == "buy").row(0, named=True)
check((bf["date"], bf["shares"]) == (D(2017, 5, 24), 1000), f"05-24 建仓 1000 股: {bf['date']}")
sp = res.events.filter(pl.col("event") == "corp_action_split").row(0, named=True)
check(sp["date"] == D(2017, 5, 25) and sp["ratio"] == 1.3 and sp["shares"] == 1300,
      f"05-25 送转 x1.3: 1000 -> 1300（行值直接生效，非累计因子）: {(sp['ratio'], sp['shares'])}")
dv = res.events.filter(pl.col("event") == "corp_action_dividend").row(0, named=True)
check(dv["date"] == D(2017, 5, 25) and abs(dv["cash_amount"] - 200.0) < 1e-9,
      f"分红 20.0/100 = 0.2 x 1000(除权前股数) = 200.00: {(dv['date'], dv['cash_amount'])}")
pf = res.positions_final.filter(pl.col("symbol") == "sh.600000")["shares"][0]
check(pf == 1300, f"期末持仓 1300 股（真实可执行量）: {pf}")
e24 = res.daily.filter(pl.col("date") == D(2017, 5, 24)).row(0, named=True)["equity"]
e25 = res.daily.filter(pl.col("date") == D(2017, 5, 25)).row(0, named=True)["equity"]
lhs = e25 - e24
rhs = 200.0 + (1300 * float(close_ex) - 1000 * float(close_prev))
check(abs(lhs - rhs) < 1e-6,
      f"权益恒等: Δequity {lhs:.4f} = 分红200 + (1300x{close_ex} - 1000x{close_prev}) = {rhs:.4f}"
      "（无双重计入）")
# 记录修复依据：ex_cum_factor 同日比值 != split_factor 行值
i = sp6["ex_date"].to_list().index(D(2017, 5, 25))
print(f"    对照：ex_cum_factor 2017-05-25 前后比值 ≈ 1.3166（含分红价格链），"
      f"split_factor 行值 = {sp6['split_factor'][i]} —— 修复取后者 ✓")

# =============================================================================
print("== (c) 50 只样本扫描：行数/值一致性与分布 ==")
import random  # noqa: E402
with h5py.File(BUNDLE / "split_factor.h5", "r") as h:
    sp_keys = sorted(h)
with h5py.File(BUNDLE / "dividends.h5", "r") as h:
    dv_keys = sorted(h)
rng = random.Random(20260918)
sp_sample = rng.sample(sp_keys, min(50, len(sp_keys)))
dv_sample = rng.sample(dv_keys, min(50, len(dv_keys)))


def oid_sym(oid):
    code, exch = oid.split(".")
    return {"XSHG": "sh", "XSHE": "sz"}.get(exch, exch[:2].lower()) + "." + code


mismatch = 0
for oid in sp_sample:
    with h5py.File(BUNDLE / "split_factor.h5", "r") as h:
        arr = h[oid][:]
        ds = arr["ex_date"].astype(np.int64)
        vs = arr["split_factor"].astype(np.float64)
    keep = ds > 0
    ds, vs = ds[keep], vs[keep]
    ds = ds[ds // 1_000_000 <= 20241231]
    vs = vs[:len(ds)]
    got = splits_all.filter(pl.col("symbol") == oid_sym(oid)).sort("ex_date")
    if got.height != len(ds):
        mismatch += 1
        continue
    want_dates = sorted(int(x) // 1_000_000 for x in ds)
    got_dates = sorted(d.year * 10000 + d.month * 100 + d.day for d in got["ex_date"].to_list())
    got_vals = [v for _, v in sorted(zip(got["ex_date"].to_list(), got["split_factor"].to_list()))]
    want_vals = [v for _, v in sorted(zip((int(x) // 1_000_000 for x in ds), vs))]
    if got_dates != want_dates or any(abs(a - b) > 1e-12 for a, b in zip(got_vals, want_vals)):
        mismatch += 1
check(mismatch == 0, f"split 样本 50 只：loader 行数/日期/值与 h5 原行一致（mismatch={mismatch}）")

mismatch = 0
for oid in dv_sample:
    with h5py.File(BUNDLE / "dividends.h5", "r") as h:
        arr = h[oid][:]
        ex = arr["ex_dividend_date"].astype(np.int64)   # 8 位 YYYYMMDD
        cash = arr["dividend_cash_before_tax"].astype(np.float64)
        lot = arr["round_lot"].astype(np.int64)
    keep = ex > 0
    ex, cash, lot = ex[keep], cash[keep], lot[keep]
    m = ex <= 20241231
    ex, cash, lot = ex[m], cash[m], lot[m]
    got = divs_all.filter(pl.col("symbol") == oid_sym(oid)).sort("ex_date")
    if got.height != len(ex):
        mismatch += 1
        continue
    ok = True
    for r in got.iter_rows(named=True):
        dint = r["ex_date"].year * 10000 + r["ex_date"].month * 100 + r["ex_date"].day
        i = int(np.where(ex == dint)[0][0])
        if abs(r["cash_per_lot_pre_tax"] - cash[i]) > 1e-9 or int(r["round_lot"]) != int(lot[i]):
            ok = False
    if not ok:
        mismatch += 1
check(mismatch == 0, f"dividends 样本 50 只：行数/每手税前/round_lot 与 h5 原行一致（mismatch={mismatch}）")

sf_vals = splits_all["split_factor"]
n_lt1 = int((sf_vals < 1.0).sum())
n_eq1 = int((sf_vals == 1.0).sum())
dups = (splits_all.group_by("symbol", "ex_date").len().filter(pl.col("len") > 1).height)
print(f"    split 值域: min {sf_vals.min()} max {sf_vals.max()}; <1.0: {n_lt1} 行; ==1.0: {n_eq1} 行; "
      f"同日重复行: {dups} 组（引擎按乘积复合）")
check(int((sf_vals <= 0).sum()) == 0, "split 无非正值")
lots = divs_all["round_lot"].value_counts().sort("round_lot")
print(f"    round_lot 分布: {lots.rows()[:5]} …")
zero_cash = int((divs_all["cash_per_lot_pre_tax"] == 0).sum())
print(f"    cash==0 分红行: {zero_cash}（引擎 if div 跳过 0 额）")

# =============================================================================
print("== (d) F2 loader 回归：自建合成 h5 ==")
split_dtype = np.dtype([("ex_date", np.int64), ("split_factor", np.float64)])
arr = np.zeros(3, dtype=split_dtype)
arr[0] = (0, 1.0)                    # 锚点
arr[1] = (20150105000000, 1.05)      # 首个真实事件（若源是坏数据 7.82 也应原样保留）
arr[2] = (20160623000000, 1.1)
path = Path(tempfile.gettempdir()) / "review_delta_splits_probe.h5"
with h5py.File(path, "w") as f:
    f.create_dataset("600000.XSHG", data=arr)
try:
    frame, meta = load_split_factor_h5(path)
    check(meta["anchor_rows_dropped"] == 1 and meta["rows"] == 2,
          f"锚点行丢弃、事件行保留: anchors_dropped={meta['anchor_rows_dropped']} rows={meta['rows']}")
    check(frame["split_factor"].to_list() == [1.05, 1.1],
          f"逐事件值原样保留（无差分、无累计）: {frame['split_factor'].to_list()}")
    # 引擎行为：跨首事件持仓 x1.05（不是差分 1.05/1.0 的歧义，也不是累计 1.155）
    daily = pl.DataFrame({
        "symbol": ["sh.600000"] * 6,
        "date": [D(2014, 12, 31), D(2015, 1, 5), D(2015, 1, 6),
                 D(2016, 6, 22), D(2016, 6, 23), D(2016, 6, 24)],
        "open": [10.2, 10.0, 10.0, 10.0, 10.0, 10.1],
        "high": [10.3, 10.1, 10.1, 10.1, 10.1, 10.2],
        "low": [9.95, 9.9, 9.9, 9.9, 9.9, 10.0],
        "close": [10.0, 10.0, 10.05, 10.05, 10.05, 10.15],
        "tradestatus": [1.0] * 6})
    limits = auto_lim(daily)
    res = run([sig("sh.600000", D(2014, 12, 30), "buy", 10.0, 1, shares=100)],
              daily, limits, splits=frame)
    sps = res.events.filter(pl.col("event") == "corp_action_split").sort("date")
    check(sps["ratio"].to_list() == [1.05, 1.1]
          and sps["shares"].to_list() == [105, 116],
          f"跨首事件 x1.05=105（F2：非累计 7.82 类），跨第二事件 x1.1 -> floor(115.5+0.5)=116: "
          f"{list(zip(sps['ratio'].to_list(), sps['shares'].to_list()))}")
finally:
    path.unlink(missing_ok=True)

# =============================================================================
print("== (e) F5：零股一次性卖出 + 买入整手断言 ==")
try:
    d_one = pl.DataFrame({"symbol": ["X"], "date": [D(2024, 1, 2)], "open": [10.0],
                          "high": [10.1], "low": [9.9], "close": [10.0],
                          "tradestatus": [1.0]})
    run([sig("X", D(2024, 1, 1), "sell", 10.0, 1, shares=250)], d_one, auto_lim(d_one))
    check(False, "显式非整手卖出应被拒绝")
except BandContractError as e:
    check("multiple of 100" in str(e), f"显式非整手卖出被拒: {str(e)[:60]}…")

daily = pl.DataFrame({
    "symbol": ["Y"] * 5,
    "date": [D(2024, 2, 5), D(2024, 2, 6), D(2024, 2, 7), D(2024, 2, 8), D(2024, 2, 9)],
    "open": [10.2, 10.0, 10.0, 10.1, 10.1], "high": [10.3, 10.1, 10.1, 10.2, 10.2],
    "low": [9.95, 9.9, 9.9, 10.0, 10.0], "close": [10.0, 10.0, 10.05, 10.1, 10.15],
    "tradestatus": [1.0] * 5})
splits = pl.DataFrame({"symbol": ["Y", "Y"], "ex_date": [D(2024, 2, 6), D(2024, 2, 7)],
                       "split_factor": [1.3, 1.0]})
res = run([sig("Y", D(2024, 2, 4), "buy", 10.0, 1, shares=300),
           sig("Y", D(2024, 2, 5), "sell", 10.0)], daily, auto_lim(daily), splits=splits)
sell = res.fills.filter(pl.col("side") == "sell")
check(sell.height == 1 and sell["shares"][0] == 390 and "odd_lot_exit" in sell["detail"][0],
      f"300 x1.3 = 390 零股一次性卖出: shares={sell['shares'][0]}")
check(res.stats["odd_lot_exits"]["count"] == 1
      and "definition" in res.stats["odd_lot_exits"],
      "odd_lot_exits 计数与定义存在")
check((res.fills.filter(pl.col("side") == "buy")["shares"] % 100 == 0).all(),
      "所有买入成交均为整手")

# =============================================================================
print("== (f) F6：deferred_limitdown 定义字段 ==")
d_z = pl.DataFrame({"symbol": ["Z"], "date": [D(2024, 3, 4)], "open": [10.2],
                    "high": [10.3], "low": [9.9], "close": [10.0],
                    "tradestatus": [1.0]})
res_z = run([sig("Z", D(2024, 3, 1), "buy", 10.0, 1, target=10_000)], d_z, auto_lim(d_z))
check("deferred_limitdown_definition" in res_z.stats["k3_fallback"],
      "stats.k3_fallback.deferred_limitdown_definition 存在（双记口径说明）")

# =============================================================================
print("== (g) 防御性：ex_cum_factor 帧误传为 splits 必须被拒 ==")
exf_frame = pl.DataFrame({"symbol": ["sh.600000"],
                          "ex_date": [D(2015, 1, 5)],
                          "cum_factor": [7.82]})
d_g = pl.DataFrame({"symbol": ["sh.600000"], "date": [D(2014, 12, 31)],
                    "open": [10.2], "high": [10.3], "low": [9.9], "close": [10.0],
                    "tradestatus": [1.0]})
try:
    run([sig("sh.600000", D(2014, 12, 30), "buy", 10.0, 1, target=10_000)],
        d_g, auto_lim(d_g), splits=exf_frame)
    check(False, "ex_cum_factor 帧（缺 split_factor 列）应被列名校验拒绝")
except BandContractError as e:
    check("missing required column 'split_factor'" in str(e),
          f"ex_cum_factor 帧被拒绝（列名不匹配）: {str(e)[:60]}…")

# =============================================================================
print("== (h) 附加探针：split_factor < 1.0 的行分类核实 ==")
lt1 = splits_all.filter(pl.col("split_factor") < 1.0).sort("symbol", "ex_date")
print(lt1)
import datetime as _dt  # noqa: E402
for r in lt1.head(4).iter_rows(named=True):
    bar = (pl.scan_parquet(ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet")
           .filter((pl.col("symbol") == r["symbol"])
                   & (pl.col("date") >= r["ex_date"] - _dt.timedelta(days=10))
                   & (pl.col("date") <= r["ex_date"] + _dt.timedelta(days=3)))
           .select("date", "open", "close").sort("date").collect())
    if bar.height >= 2:
        pc, o = float(bar["close"][-2]), float(bar["open"][-1])
        print(f"    {r['symbol']} {r['ex_date']} ratio {r['split_factor']:.4f}: "
              f"前收 {pc:.2f} -> 除权日开 {o:.2f}（跳空 {(o / pc - 1) * 100:+.2f}%）")

# =============================================================================
print()
print(f"增量对抗断言: {PASS} passed, {len(FAILS)} failed")
if FAILS:
    for f in FAILS:
        print("  FAILED:", f)
    sys.exit(1)
print("ALL DELTA ADVERSARIAL CHECKS PASSED")
