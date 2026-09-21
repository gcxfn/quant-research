# -*- coding: utf-8 -*-
"""F2-R1 F 族（横截面/组合特征，10 因子）实施脚本。

冻结依据：docs/research/exp-20260919-factor-round-f2r1-prereg.md §1/§2/§3-F。
- 评估窗 dev 2015–2020：评估面板硬截断至 2020-12-31，2021+（val 保留窗）零接触，
  包括前向标签（2020-12 信号因标签跨入 2021 被自动截断，实际 71 期，与预登记一致）。
- 基准：上证综指 000001.SH（tushare index_daily 20260917-r1，2431 交易日全覆盖，
  manifest 已对 trade_cal 核验），日收益 = close/pre_close − 1。
- OLS 口径：有截距 OLS，beta = cov(ri,rm)/var(rm)（斜率估计；截距 alpha 仅用于
  残差构造，不进入 beta）。月末时点只用 <= 当日的 trailing 窗口数据。
- 因子值不做去极值/标准化（评估为秩相关，天然稳健）；滚动窗口按各 symbol 自身
  交易日行序列（仅 tradestatus==1 行）。

输出：outputs/F_xsec/F<NN>.parquet + F<NN>.json（含 §2 初判存活判定）。
"""

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))

from quant.factors.eval import (  # noqa: E402
    FREEZE_END,
    FactorEvalConfig,
    _prepare_panel,
    evaluate_factor,
)

RUN = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
OUT = RUN / "outputs/F_xsec"
OUT.mkdir(parents=True, exist_ok=True)

PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
IDX = ROOT / "data/raw/tushare/index_daily/20260917-r1/chunk_000001.SH.csv"

DEV_PANEL_END = date(2020, 12, 31)   # 评估面板硬截断（val 2021-2024 零接触）
SIG_END = date(2020, 12, 31)         # 因子 signal_date 上限（断言 <= 2024-12-31）

CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


t_start = time.time()
panel_sha = sha256_of(PANEL)
idx_sha = sha256_of(IDX)
print(f"panel sha256={panel_sha[:16]}... idx sha256={idx_sha[:16]}...")

# ---------------------------------------------------------------------------
# 数据装载
# ---------------------------------------------------------------------------

panel = pl.read_parquet(
    PANEL, columns=["date", "symbol", "open", "close", "preclose", "tradestatus", "isST"]
)
assert panel["date"].max() <= FREEZE_END, "面板含 2025+ 日期"

idx = pl.read_csv(IDX).select(
    pl.col("trade_date").cast(pl.Utf8).str.to_date("%Y%m%d").alias("date"),
    (pl.col("close") / pl.col("pre_close") - 1.0).alias("mret"),
)
n_idx_dates = idx.height
missing = panel.select("date").unique().join(idx.select("date"), on="date", how="anti")
print(f"基准覆盖核验: 指数行数={n_idx_dates}, 面板日期缺指数={missing.height}")
if missing.height:
    print(missing)

month_ends_all = (
    panel.select("date").unique()
    .with_columns(pl.col("date").dt.truncate("1mo").alias("_m"))
    .group_by("_m").agg(pl.col("date").max().alias("me"))
    .sort("me")
)
me_sig = month_ends_all.filter(pl.col("me") <= SIG_END)["me"].to_list()
print(f"月末信号日: {len(me_sig)} 期 ({me_sig[0]} .. {me_sig[-1]})")

# 交易日行（tradestatus==1），剔科创板/北交所；ST 留给评估池过滤
tr = (
    panel.filter(pl.col("tradestatus") == 1)
    .filter(~pl.col("symbol").str.starts_with("sh.688"))
    .filter(~pl.col("symbol").str.starts_with("bj."))
    .join(idx, on="date", how="inner")
    .sort("symbol", "date")
)
print(f"交易日行(剔板后)={tr.height}, symbols={tr['symbol'].n_unique()}")

tr = tr.with_columns(
    (pl.col("close") / pl.col("preclose") - 1.0).alias("ri"),
    (pl.col("open") / pl.col("preclose") - 1.0).alias("om"),
    ((pl.col("close") - pl.col("open")) / pl.col("preclose")).alias("idr"),
).select("date", "symbol", "ri", "om", "idr", "mret").rename({"mret": "rm"})

# F05 用：逐 symbol 对数收益累计（在其自身交易日行序列上）
tr = tr.with_columns(pl.col("ri").log1p().cum_sum().over("symbol").alias("L"))

# ---------------------------------------------------------------------------
# F01/F02/F03/F04/F06/F07/F08/F09/F10 —— 滚动窗口表达式
# ---------------------------------------------------------------------------

neg_ri = pl.when(pl.col("ri") < 0).then(pl.col("ri")).otherwise(None)

f = tr.with_columns(
    pl.col("ri").rolling_mean(60).over("symbol").alias("m_ri60"),
    pl.col("rm").rolling_mean(60).over("symbol").alias("m_rm60"),
    (pl.col("ri") * pl.col("rm")).rolling_mean(60).over("symbol").alias("m_rirm60"),
    (pl.col("rm") ** 2).rolling_mean(60).over("symbol").alias("m_rm2_60"),
    (pl.col("ri") ** 2).rolling_mean(60).over("symbol").alias("m_ri2_60"),
    (pl.col("ri") ** 3).rolling_mean(60).over("symbol").alias("m_ri3_60"),
    (pl.col("ri") ** 4).rolling_mean(60).over("symbol").alias("m_ri4_60"),
    pl.col("om").rolling_mean(20).over("symbol").alias("F08"),
    pl.col("idr").rolling_mean(20).over("symbol").alias("F09"),
    neg_ri.rolling_std(60, min_samples=10).over("symbol").alias("F04"),  # >=10 个负日
)

# 60d OLS（有截距）：beta = cov/var, alpha = m_ri - beta*m_rm
f = f.with_columns(
    pl.when(pl.col("m_rm2_60") - pl.col("m_rm60") ** 2 > 0)
    .then((pl.col("m_rirm60") - pl.col("m_ri60") * pl.col("m_rm60"))
          / (pl.col("m_rm2_60") - pl.col("m_rm60") ** 2))
    .otherwise(None).alias("beta60")
)
f = f.with_columns(
    (pl.col("m_ri60") - pl.col("beta60") * pl.col("m_rm60")).alias("alpha60")
)
f = f.with_columns(
    (pl.col("ri") - pl.col("alpha60") - pl.col("beta60") * pl.col("rm")).alias("resid60")
)
f = f.with_columns(
    pl.col("beta60").alias("F01"),
    pl.col("resid60").rolling_std(60).over("symbol").alias("F10"),
    # 60d 三/四阶中心矩 -> 偏度 g1 / 超额峰度 g2（总体矩，未做样本调整）
    (pl.col("m_ri2_60") - pl.col("m_ri60") ** 2).alias("m2_60"),
    (pl.col("m_ri3_60") - 3 * pl.col("m_ri60") * pl.col("m_ri2_60")
     + 2 * pl.col("m_ri60") ** 3).alias("m3_60"),
    (pl.col("m_ri4_60") - 4 * pl.col("m_ri60") * pl.col("m_ri3_60")
     + 6 * pl.col("m_ri60") ** 2 * pl.col("m_ri2_60")
     - 3 * pl.col("m_ri60") ** 4).alias("m4_60"),
)
f = f.with_columns(
    pl.when(pl.col("m2_60") > 0)
    .then(pl.col("m3_60") / pl.col("m2_60") ** 1.5).otherwise(None).alias("F06"),
    pl.when(pl.col("m2_60") > 0)
    .then(pl.col("m4_60") / pl.col("m2_60") ** 2 - 3.0).otherwise(None).alias("F07"),
)
f = f.select(
    "date", "symbol",
    "F01", "F04", "F06", "F07", "F08", "F09", "F10",
    "ri", "rm",
)

# 240d OLS -> F02；残差(240d 系数, 逐行) 120d 累计 -> F03
f = f.with_columns(
    pl.col("ri").rolling_mean(240).over("symbol").alias("m_ri240"),
    pl.col("rm").rolling_mean(240).over("symbol").alias("m_rm240"),
    (pl.col("ri") * pl.col("rm")).rolling_mean(240).over("symbol").alias("m_rirm240"),
    (pl.col("rm") ** 2).rolling_mean(240).over("symbol").alias("m_rm2_240"),
)
f = f.with_columns(
    pl.when(pl.col("m_rm2_240") - pl.col("m_rm240") ** 2 > 0)
    .then((pl.col("m_rirm240") - pl.col("m_ri240") * pl.col("m_rm240"))
          / (pl.col("m_rm2_240") - pl.col("m_rm240") ** 2))
    .otherwise(None).alias("F02"),
)
f = f.with_columns(
    (pl.col("m_ri240") - pl.col("F02") * pl.col("m_rm240")).alias("alpha240")
)
f = f.with_columns(
    (pl.col("ri") - pl.col("alpha240") - pl.col("F02") * pl.col("rm")).alias("resid240")
)
f = f.with_columns(
    pl.col("resid240").clip(-0.9999, None).log1p()
    .rolling_sum(120).over("symbol").exp().alias("_f03_gross")
)
f = f.with_columns((pl.col("_f03_gross") - 1.0).alias("F03"))
f = f.select("date", "symbol", "F01", "F02", "F03", "F04", "F06", "F07", "F08", "F09", "F10")
f = f.filter(pl.col("date").is_in(me_sig))
print(f"月末行={f.height}; 耗时 {time.time()-t_start:.0f}s")

# ---------------------------------------------------------------------------
# F05 mdd_120 —— 精确窗口最大回撤（逐月末循环；每 symbol 取 <=月末的最后 120 个交易日行）
# ---------------------------------------------------------------------------

rows = []
for t in me_sig:
    sub = tr.filter(pl.col("date") <= t).select("symbol", "date", "L")
    w = sub.group_by("symbol").tail(120).sort("symbol", "date")
    w = w.with_columns(pl.col("L").cum_max().over("symbol").alias("P"))
    dd = (
        w.with_columns((pl.col("P") - pl.col("L")).alias("d"))
        .group_by("symbol").agg(pl.col("d").max().alias("mdd_log"))
    )
    at_t = tr.filter(pl.col("date") == t).select("symbol")
    rows.append(
        at_t.join(dd, on="symbol", how="inner")
        .select(
            pl.lit(t).alias("signal_date"),
            "symbol",
            ((-pl.col("mdd_log")).exp() - 1.0).alias("value"),  # <=0, 越负回撤越深
        )
    )
F05_frame = pl.concat(rows)
print(f"F05 完成: {F05_frame.height} 行; 耗时 {time.time()-t_start:.0f}s")

# ---------------------------------------------------------------------------
# 组装 10 个因子表 (symbol, signal_date, value)
# ---------------------------------------------------------------------------

FACTOR_NAMES = {
    "F01": "beta_60", "F02": "beta_240", "F03": "resid_mom120", "F04": "dvol_60",
    "F05": "mdd_120", "F06": "skew_60", "F07": "kurt_60", "F08": "overnight20",
    "F09": "intraday20", "F10": "idio_vol60",
}

frames: dict[str, pl.DataFrame] = {}
for fid in FACTOR_NAMES:
    if fid == "F05":
        fr = F05_frame
    else:
        fr = f.select(
            pl.col("symbol"),
            pl.col("date").alias("signal_date"),
            pl.col(fid).cast(pl.Float64).alias("value"),
        )
    fr = fr.filter(pl.col("value").is_not_null()).unique(["symbol", "signal_date"])
    mx = fr["signal_date"].max()
    assert mx <= SIG_END, f"{fid} signal_date 越界: {mx}"
    assert mx <= FREEZE_END, f"{fid} 冻结越界: {mx}"
    frames[fid] = fr
    print(f"{fid} {FACTOR_NAMES[fid]}: {fr.height} 行, 信号日 {fr['signal_date'].min()}..{mx}")

# ---------------------------------------------------------------------------
# 评估（面板硬截断至 2020-12-31：val 零接触；2020-12 信号因标签跨年自动截断）
# ---------------------------------------------------------------------------

eval_panel = panel.filter(pl.col("date") <= DEV_PANEL_END)
assert eval_panel["date"].max() <= DEV_PANEL_END

# 合格池月度中位符号数（§2 淘汰标准 4 的基准）
ready = _prepare_panel(eval_panel, CFG)
me_eval_dates = (
    eval_panel.select("date").unique()
    .with_columns(pl.col("date").dt.truncate("1mo").alias("_m"))
    .group_by("_m").agg(pl.col("date").max().alias("me"))
    .filter(pl.col("me") < date(2020, 12, 1))  # 2020-12 信号标签跨年不入评估
    .sort("me")
)
pool_cnt = (
    ready.join(me_eval_dates.select("me"), left_on="date", right_on="me", how="semi")
    .group_by("date").agg(pl.len().alias("n")).sort("date")
)
pool_median = float(pool_cnt["n"].median())
print(f"合格池: 评估月末 {pool_cnt.height} 期, 月度符号数中位={pool_median:.0f}, "
      f"min={pool_cnt['n'].min()}, max={pool_cnt['n'].max()}")

results = {}
for fid, fr in frames.items():
    t0 = time.time()
    others = {k: v for k, v in frames.items() if k != fid}
    res = evaluate_factor(fr, eval_panel, CFG, others=others)

    # §2 初判存活（四条全过才 True；判据冻结于预登记，看结果后不得改）
    n = res["n_dates"]
    ic_std = res["ic_std"]
    t_val = (res["ic_mean"] / ic_std * n ** 0.5) if ic_std and ic_std > 0 else float("inf")
    ic_mean = res["ic_mean"]
    mono = res["monotonicity"]
    ic2015 = res["ic_by_year"].get(2015)
    crit1 = abs(t_val) >= 2.0
    crit2 = (mono == mono) and abs(mono) >= 0.3 and (mono > 0) == (ic_mean > 0)
    if ic2015 is None:
        crit3 = False
    else:
        crit3 = not ((ic2015 > 0) != (ic_mean > 0) and abs(ic2015) > 0.03)
    crit4 = res["coverage_mean_symbols"] >= 0.5 * pool_median
    screen = {
        "t_ic": t_val, "crit1_abs_t_ge2": crit1, "crit2_mono": crit2,
        "ic_2015": ic2015, "crit3_2015_ok": crit3,
        "pool_median_symbols": pool_median, "crit4_coverage": crit4,
        "screen_pass": bool(crit1 and crit2 and crit3 and crit4),
    }
    meta = {
        "factor_id": fid,
        "name": FACTOR_NAMES[fid],
        "family": "F 横截面/组合特征",
        "prereg": "exp-20260919-factor-round-f2r1 §3-F",
        "benchmark": "000001.SH 上证综指 (tushare index_daily 20260917-r1, "
                     f"{n_idx_dates} 日全覆盖 20150105-20241231), mret=close/pre_close-1",
        "ols_caliber": "有截距 OLS; beta=cov(ri,rm)/var(rm); alpha 仅用于残差; "
                       "月末时点仅用 <=当日 trailing 窗口(各 symbol 自身交易日行)",
        "panel_sha256": panel_sha,
        "index_sha256": idx_sha,
        "eval_panel_end": str(DEV_PANEL_END),
        "screen": screen,
        "eval": res,
    }
    (OUT / f"{fid}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    fr.write_parquet(OUT / f"{fid}.parquet")
    results[fid] = meta
    print(f"{fid} 评估完成 {time.time()-t0:.0f}s | IC={ic_mean:+.4f} t={t_val:+.2f} "
          f"mono={mono:+.2f} IC2015={ic2015 if ic2015 is None else round(ic2015,4)} "
          f"cov={res['coverage_mean_symbols']:.0f} pass={screen['screen_pass']}")

summary = {
    "run": "20260919T180000-f2r1-factor-batch / F_xsec",
    "config": CFG.canonical(),
    "pool_median_symbols": pool_median,
    "n_eval_dates_expected": 71,
    "factors": {
        fid: {
            "name": m["name"],
            "ic_mean": m["eval"]["ic_mean"],
            "t_ic": m["screen"]["t_ic"],
            "monotonicity": m["eval"]["monotonicity"],
            "long_short_mean": m["eval"]["long_short_mean"],
            "ic_2015": m["screen"]["ic_2015"],
            "coverage": m["eval"]["coverage_mean_symbols"],
            "turnover": m["eval"]["turnover_top_group"],
            "screen_pass": m["screen"]["screen_pass"],
        }
        for fid, m in results.items()
    },
}
(RUN / "f_xsec_summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
)
print(f"全部完成, 总耗时 {time.time()-t_start:.0f}s")
