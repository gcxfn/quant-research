# E16 双计缺陷修复：代理全行 unique 未合并 (symbol,ex_date,cash_div) 相同、其他列不同的
# 重复分红行 → 300 个符号的 12m 股利被双计（验收 rel=1.0 即 del=2×ref 的根因）。
# 修复：按 (symbol, ex_date) 每次除息只计一次 cash_div；重算因子帧并重跑 evaluate_factor。
# 交付物处置：修复版覆盖 E16.parquet / E16.json（F3 权威）；代理原版留档
# E16_dupcount_original.parquet / .json；全过程写入 family_report 披露。
import json
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))
from quant.factors.eval import FactorEvalConfig, evaluate_factor  # noqa: E402

OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/E_event"
PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
TS = ROOT / "data/raw/tushare"
LAST_SIGNAL = date(2020, 11, 30)

# ---- 与验收脚本同源的 dividend 加载（5 列 + 类型统一 + 文件名日期过滤）----
import glob


def read_chunks(pattern, name_lo, name_hi):
    frames = []
    for p in sorted(glob.glob(str(pattern))):
        base = Path(p).name
        key = base.replace("chunk_period_", "chunk_").replace("chunk_", "").replace(".csv", "")
        if not (name_lo <= key <= name_hi):
            continue
        if Path(p).stat().st_size <= 100:
            continue
        df = pl.read_csv(p, infer_schema_length=10000)
        if df.height:
            cols = [c for c in ["ts_code", "div_proc", "ann_date", "ex_date", "cash_div"] if c in df.columns]
            df = df.select(cols).with_columns(
                [pl.col(c).cast(pl.Float64, strict=False) for c in ("cash_div",) if c in df.columns]
            )
            frames.append(df)
    return pl.concat(frames, how="diagonal")


V = pl.concat([
    read_chunks(TS / "dividend/20260913-r2/chunk_*.csv", "20150101", "20171231"),
    read_chunks(TS / "dividend/20260909-r3/chunk_*.csv", "20180101", "20201231"),
], how="diagonal")
V = V.with_columns(pl.col("cash_div").cast(pl.Float64, strict=False).fill_null(0.0))
V = V.with_columns(
    pl.col("ann_date").cast(pl.String).str.to_date("%Y%m%d"),
    pl.col("ex_date").cast(pl.String).str.to_date("%Y%m%d"),
)
V = (V.filter(pl.col("ts_code").str.contains("."))
     .with_columns((pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
                    + "." + pl.col("ts_code").str.split(".").list.first()).alias("symbol"))
     .filter(pl.col("div_proc") == "实施")
     .filter(pl.col("ex_date").is_not_null())
     .filter(pl.col("ex_date") <= LAST_SIGNAL))
# 【修复核心】每次除息 (symbol, ex_date) 只计一笔 cash_div（同额重复行/多公告行不累加）
Vfix = V.unique(subset=["symbol", "ex_date", "cash_div"]).unique(subset=["symbol", "ex_date"], keep="first")
n_dup_groups = V.height - Vfix.height
print(f"去重合并 {n_dup_groups} 行重复分红（全行 {V.height} → 事件 {Vfix.height}）")

panel = pl.read_parquet(PANEL)
me = (panel.filter(pl.col("date") <= LAST_SIGNAL)
      .group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
      .agg(pl.col("date").max().alias("signal_date")).sort("signal_date"))
ME = [d for d in me["signal_date"].to_list() if d <= LAST_SIGNAL]
me_close = panel.filter(pl.col("date").is_in(pl.Series(ME))).select("symbol", "date", "close")

rows = []
for t in ME:
    w = Vfix.filter((pl.col("ex_date") > t - timedelta(days=365)) & (pl.col("ex_date") <= t))
    dv = w.group_by("symbol").agg(pl.col("cash_div").sum().alias("_d"))
    cl = me_close.filter(pl.col("date") == t).select("symbol", "close")
    rows.append(dv.join(cl, on="symbol").with_columns(
        (pl.col("_d") / pl.col("close")).alias("value"), pl.lit(t).alias("signal_date"),
    ).select("symbol", "signal_date", "value"))
e16_fix = pl.concat(rows).sort("symbol", "signal_date")
print(f"修复版 E16 帧 {e16_fix.height} 行（代理原版 158173）")

# ---- 重评估 ----
cfg = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
res = evaluate_factor(e16_fix, panel, cfg)
import math
res_t = res["ic_mean"] / res["ic_std"] * math.sqrt(res["n_dates"])
print("修复版 eval:", {k: v for k, v in res.items() if k in
      ("n_dates", "ic_mean", "icir", "monotonicity", "turnover_top_group")}, "t =", round(res_t, 4))

# 与原版对比 + §2 终裁
old = json.loads((OUT / "E16.json").read_text(encoding="utf-8"))
icm, mono, cov = res["ic_mean"], res["monotonicity"], res["coverage_mean_symbols"]
pool_med = old["pool_median_symbols"]
c1 = abs(res_t) >= 2.0
c2 = (mono > 0) == (icm > 0) and abs(mono) >= 0.3
ic15 = res.get("ic_by_year", {}).get("2015")
c3 = (ic15 is None) or not ((ic15 > 0) != (icm > 0) and abs(ic15) > 0.03)
c4 = cov / pool_med >= 0.5
surv = c1 and c2 and c3 and c4
print(f"§2 终裁: c1={c1} c2={c2} c3={c3} c4={c4} -> 存活={surv}")
print(f"对比: t {old['t_value']:.4f} -> {res_t:.4f}; IC {old['eval']['ic_mean']:.4f} -> {icm:.4f}; "
      f"mono {old['eval']['monotonicity']:.4f} -> {mono:.4f}")

# ---- 交付物处置（留痕不覆盖原则）----
if not (OUT / "E16_dupcount_original.parquet").exists():
    shutil.copy2(OUT / "E16.parquet", OUT / "E16_dupcount_original.parquet")
    shutil.copy2(OUT / "E16.json", OUT / "E16_dupcount_original.json")
    print("原版已留档 E16_dupcount_original.parquet/.json")
e16_fix.write_parquet(OUT / "E16.parquet")

new_json = dict(old)
new_json["t_value"] = res_t
new_json["n_rows"] = e16_fix.height
new_json["coverage_median_symbols"] = cov
new_json["formula"] = old["formula"] + "（修复：按 (symbol,ex_date) 去重后单计）"
new_json["fix_note"] = ("2026-09-19 主对话验收发现双计缺陷：代理全行 unique 未合并同 (symbol,ex_date,cash_div) "
                        "异其他列的重复分红行（348 行/300 符号），致 12m 股利双计。修复=事件级去重后重算重评估。"
                        "原版留档 E16_dupcount_original.*；对比 t "
                        f"{old['t_value']:.4f}->{res_t:.4f}, IC {old['eval']['ic_mean']:.4f}->{icm:.4f}")
new_json["criteria"] = ["c1_abs_t>=2", "c2_mono_consistent>=0.3", "c3_2015_non_disaster",
                        "c4_coverage>=50%pool"] if surv else []
new_json["survived_prelim"] = surv
new_json["eval"] = res
(OUT / "E16.json").write_text(json.dumps(new_json, ensure_ascii=False, indent=1), encoding="utf-8")
print("E16.parquet/E16.json 已更新为修复版")
