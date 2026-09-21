# F2R1 A 族（量价 25 因子）——主对话接管实施（两次代理派发死于基建后）
# 冻结依据：docs/research/exp-20260919-factor-round-f2r1-prereg.md §1/§2/§3-A
# 口径：仅 tradestatus==1 行序；day_ret=close/preclose−1（复权链，公司行动内含）；
#       窗口按 symbol 自身交易日行；月末时点只用 ≤t 数据；std ddof=1；因子帧不做剔除
#       （池过滤留给 harness），signal_date ≤2020-12-31，h=20 标签跨年由 harness 截断。
import hashlib
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")

# =============================================================================
# V2 val-batch window parametrization (exp-20260920-val-batch, F line).
# dev = the F2R1 frozen window (port check: rebuild must be byte-identical);
# val = signal months 2021-01-01..2024-11-30.
# ONLY the window parameters below are new; every formula / rolling window /
# filter expression is the F2R1 implementation verbatim.
# =============================================================================
import os as _os
_WINDOW = _os.environ.get("VAL_WINDOW", "dev")
assert _WINDOW in ("dev", "val"), _WINDOW
_OUT_ROOT = Path(__file__).resolve().parents[2] / "outputs"
WINDOW_END = date(2024, 12, 31) if _WINDOW == "val" else date(2020, 12, 31)


def sig_cap(fr, hi):
    """Signal-month cap: F2R1's own cap in dev (identity to the frozen
    implementation); the val signal-month window [2021-01-01, 2024-11-30]
    in val mode."""
    if _WINDOW == "val":
        return fr.filter(pl.col("signal_date").is_between(
            date(2021, 1, 1), date(2024, 11, 30)))
    return fr.filter(pl.col("signal_date") <= hi)

sys.path.insert(0, str(ROOT / "src"))
from quant.factors.eval import FactorEvalConfig, evaluate_factor  # noqa: E402

OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "A_price"
OUT.mkdir(parents=True, exist_ok=True)
PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
PANEL_SHA = hashlib.sha256(PANEL.read_bytes()).hexdigest()
CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
FORMULAS = {
    "A01": ("mom_20", "adj_ret(t-20,t)，复权链 cum_prod"),
    "A02": ("mom_60", "adj_ret(t-60,t)"),
    "A03": ("mom_120", "adj_ret(t-120,t)"),
    "A04": ("mom_240", "adj_ret(t-240,t)"),
    "A05": ("mom_20sk5", "adj_ret(t-20,t-5)"),
    "A06": ("mom_60sk20", "adj_ret(t-60,t-20)"),
    "A07": ("mom_12_1", "adj_ret(t-240,t-20)"),
    "A08": ("rev_1", "adj_ret(t-1,t)"),
    "A09": ("rev_5", "adj_ret(t-5,t)"),
    "A10": ("rev_10", "adj_ret(t-10,t)"),
    "A11": ("vol_20", "std(day_ret,20) ddof=1"),
    "A12": ("vol_60", "std(day_ret,60)"),
    "A13": ("vol_ratio", "std(20)/std(120)"),
    "A14": ("amp_20", "mean((H-L)/C,20)"),
    "A15": ("range_pos_60", "(C-min60)/(max60-min60)"),
    "A16": ("dist_52wH", "C/max(C,252)-1"),
    "A17": ("liq_amt20", "ln(mean(amount,20))"),
    "A18": ("liq_ratio", "mean(amount,5)/mean(amount,60)"),
    "A19": ("amihud_20", "mean(|day_ret|/amount,20)*1e9"),
    "A20": ("pv_corr_20", "corr(C,volume,20)（矩形式）"),
    "A21": ("vol_updown", "sum(vol,ret>0,20)/sum(vol,ret<0,20)"),
    "A22": ("vol_trend", "mean(volume,5)/mean(volume,60)"),
    "A23": ("sma20_gap", "C/SMA20-1"),
    "A24": ("sma60_gap", "C/SMA60-1"),
    "A25": ("days_hi60", "t-argmax(C,60)（距 60 日高点天数）"),
}

t0 = time.time()
panel_all = pl.read_parquet(PANEL)
panel = (panel_all.filter(pl.col("tradestatus") == 1)
         .filter(pl.col("date") <= WINDOW_END)
         .sort("symbol", "date"))

me = (panel.group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
      .agg(pl.col("date").max().alias("signal_date")).sort("signal_date"))
ME = me["signal_date"].to_list()
print(f"[{time.time()-t0:6.1f}s] 面板 {panel.height} 行，月末网格 {len(ME)} 期 {ME[0]}..{ME[-1]}")

# ---- 中间列（全部 over symbol，backward only）----
g = panel.with_columns(
    (pl.col("close") / pl.col("preclose") - 1.0).alias("ret"),
    ((pl.col("high") - pl.col("low")) / pl.col("close")).alias("amp"),
).with_columns(
    (1.0 + pl.col("ret")).cum_prod().over("symbol").alias("cump"),
)
g = g.with_columns(
    pl.col("ret").rolling_std(20, min_samples=20).over("symbol").alias("sd20"),
    pl.col("ret").rolling_std(60, min_samples=60).over("symbol").alias("sd60"),
    pl.col("ret").rolling_std(120, min_samples=120).over("symbol").alias("sd120"),
    pl.col("amp").rolling_mean(20, min_samples=20).over("symbol").alias("amp20"),
    pl.col("close").rolling_min(60, min_samples=60).over("symbol").alias("min60"),
    pl.col("close").rolling_max(60, min_samples=60).over("symbol").alias("max60"),
    pl.col("close").rolling_max(252, min_samples=252).over("symbol").alias("max252"),
    pl.col("amount").rolling_mean(5, min_samples=5).over("symbol").alias("amt5"),
    pl.col("amount").rolling_mean(20, min_samples=20).over("symbol").alias("amt20"),
    pl.col("amount").rolling_mean(60, min_samples=60).over("symbol").alias("amt60"),
    (pl.col("ret").abs() / pl.col("amount")).rolling_mean(20, min_samples=20).over("symbol").alias("ami20"),
    pl.col("close").rolling_mean(20, min_samples=20).over("symbol").alias("sma20"),
    pl.col("close").rolling_mean(60, min_samples=60).over("symbol").alias("sma60"),
    pl.col("volume").rolling_mean(5, min_samples=5).over("symbol").alias("v5"),
    pl.col("volume").rolling_mean(60, min_samples=60).over("symbol").alias("v60"),
    # corr(C, vol, 20)：矩形式
    (pl.col("close") * pl.col("volume")).rolling_mean(20, min_samples=20).over("symbol").alias("_cv"),
    pl.col("close").rolling_mean(20, min_samples=20).over("symbol").alias("_mc"),
    pl.col("volume").rolling_mean(20, min_samples=20).over("symbol").alias("_mv"),
    pl.col("close").rolling_std(20, min_samples=20).over("symbol").alias("_sc"),
    pl.col("volume").rolling_std(20, min_samples=20).over("symbol").alias("_sv"),
    # 涨跌日量能
    pl.when(pl.col("ret") > 0).then(pl.col("volume")).otherwise(0.0)
     .rolling_sum(20, min_samples=20).over("symbol").alias("_vu"),
    pl.when(pl.col("ret") < 0).then(pl.col("volume")).otherwise(0.0)
     .rolling_sum(20, min_samples=20).over("symbol").alias("_vd"),
    pl.int_range(pl.len()).over("symbol").alias("_idx"),
)
g = g.with_columns(
    # 距 60 日高点天数：最近一次 close==rolling_max60 距今行数
    (pl.col("close") == pl.col("max60")).cast(pl.Int64).alias("_ismax"),
)
g = g.with_columns(
    pl.when(pl.col("_ismax") == 1).then(pl.col("_idx")).otherwise(None)
     .forward_fill().over("symbol").alias("_lastmax_idx"),
)
print(f"[{time.time()-t0:6.1f}s] 中间列完成")


def cr(k):  # cump ratio: adj_ret(t-k, t)
    return pl.col("cump") / pl.col("cump").shift(k).over("symbol") - 1.0


FACTORS = {
    "A01": cr(20), "A02": cr(60), "A03": cr(120), "A04": cr(240),
    "A05": pl.col("cump").shift(5).over("symbol") / pl.col("cump").shift(20).over("symbol") - 1.0,
    "A06": pl.col("cump").shift(20).over("symbol") / pl.col("cump").shift(60).over("symbol") - 1.0,
    "A07": pl.col("cump").shift(20).over("symbol") / pl.col("cump").shift(240).over("symbol") - 1.0,
    "A08": cr(1), "A09": cr(5), "A10": cr(10),
    "A11": pl.col("sd20"), "A12": pl.col("sd60"), "A13": pl.col("sd20") / pl.col("sd120"),
    "A14": pl.col("amp20"),
    "A15": (pl.col("close") - pl.col("min60")) / (pl.col("max60") - pl.col("min60")),
    "A16": pl.col("close") / pl.col("max252") - 1.0,
    "A17": pl.col("amt20").log(), "A18": pl.col("amt5") / pl.col("amt60"),
    "A19": pl.col("ami20") * 1e9,
    "A20": ((pl.col("_cv") - pl.col("_mc") * pl.col("_mv"))
            / (pl.col("_sc") * pl.col("_sv"))),
    "A21": pl.col("_vu") / pl.col("_vd"),
    "A22": pl.col("v5") / pl.col("v60"),
    "A23": pl.col("close") / pl.col("sma20") - 1.0,
    "A24": pl.col("close") / pl.col("sma60") - 1.0,
    "A25": (pl.col("_idx") - pl.col("_lastmax_idx")).cast(pl.Float64),
}

g = g.with_columns([e.alias(f"_{fid}") for fid, e in sorted(FACTORS.items())])
print(f"[{time.time()-t0:6.1f}s] 因子列（日频）计算完成")

month_end = g.filter(pl.col("date").is_in(pl.Series(ME)))
results = {}
for fid in sorted(FACTORS):
    ts = time.time()
    f = month_end.select(
        pl.col("symbol"), signal_date=pl.col("date"), value=pl.col(f"_{fid}")
    ).drop_nulls("value")
    f = sig_cap(f, date(2020, 12, 31))
    assert f["signal_date"].max() <= WINDOW_END
    dup = f.group_by(["symbol", "signal_date"]).len().filter(pl.col("len") > 1).height
    assert dup == 0
    res = evaluate_factor(f, panel_all, CFG)
    t = res["ic_mean"] / res["ic_std"] * math.sqrt(res["n_dates"]) if res["ic_std"] else float("nan")
    icm, mono, cov = res["ic_mean"], res["monotonicity"], res["coverage_mean_symbols"]
    ic15 = res.get("ic_by_year", {}).get("2015")
    c1 = abs(t) >= 2.0
    c2 = (mono > 0) == (icm > 0) and abs(mono) >= 0.3
    c3 = (ic15 is None) or not ((ic15 > 0) != (icm > 0) and abs(ic15) > 0.03)
    surv = c1 and c2 and c3  # c4 族级统一判
    results[fid] = dict(res=res, t=t, c1=c1, c2=c2, c3=c3, cov=cov, surv=surv, n=f.height)
    print(f"[{time.time()-t0:6.1f}s] {fid} {FORMULAS[fid][0]:<12} ic={icm:+.4f} t={t:+.2f} "
          f"mono={mono:+.2f} ic15={'n/a' if ic15 is None else format(ic15,'+.4f')} "
          f"cov={cov:.0f} n={f.height} {'存活' if surv else ''} ({time.time()-ts:.1f}s)")
    f.write_parquet(OUT / f"{fid}.parquet")

# ---- 族级池中位（与 harness 池过滤逐字一致：非 ST、交易中、剔 sh.688/bj.*）----
poolm = (panel_all.filter(pl.col("date") <= WINDOW_END)
         .filter(pl.col("isST").cast(pl.Int64) == 0)
         .filter(pl.col("tradestatus").cast(pl.Int64) == 1)
         .filter(~pl.col("symbol").str.starts_with("sh.688") & ~pl.col("symbol").str.starts_with("bj."))
         .filter(pl.col("date").is_in(pl.Series(ME)))
         .group_by("date").len()["len"].median())
print(f"池月度中位符号数 = {poolm}")

# ---- JSON 交付（结构与其他族统一）----
for fid, r in results.items():
    cov_ratio = r["cov"] / poolm
    surv = r["surv"] and cov_ratio >= 0.5
    doc = {
        "factor_id": fid, "name": FORMULAS[fid][0], "family": "A 量价",
        "prereg": "exp-20260919-factor-round-f2r1 §3-A",
        "formula": FORMULAS[fid][1],
        "panel_sha256": PANEL_SHA, "eval_panel_end": "2020-12-31",
        "implementer": "主对话接管（两次代理派发死于基建后）",
        "screen": {"t_ic": r["t"], "crit1_abs_t_ge2": r["c1"], "crit2_mono": r["c2"],
                   "ic_2015": r["res"].get("ic_by_year", {}).get("2015"),
                   "crit3_2015_ok": r["c3"], "pool_median_symbols": poolm,
                   "coverage_ratio": cov_ratio, "crit4_coverage": cov_ratio >= 0.5,
                   "screen_pass": surv},
        "eval": r["res"], "n_rows": r["n"],
    }
    (OUT / f"{fid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")

n_pass = sum(1 for fid, r in results.items()
             if r["surv"] and r["cov"] / poolm >= 0.5)
print(f"\n== A 族完成：25/25 计算，终裁存活 {n_pass} 个；总耗时 {time.time()-t0:.0f}s ==")
print("存活:", [f"{fid}({FORMULAS[fid][0]})" for fid, r in sorted(results.items())
               if r["surv"] and r["cov"] / poolm >= 0.5])
