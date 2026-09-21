# F 族主对话独立验收（复算 F09/F10 + 冻结断言 + 边缘判定核对）
# 运行：D:/量化/.venv/Scripts/python.exe accept_F_xsec.py
import hashlib
import json
from datetime import date

import polars as pl
from pathlib import Path

FREEZE = date(2020, 12, 31)

BATCH = Path(r"D:/量化/artifacts/runs/20260919T180000-f2r1-factor-batch")
OUT = BATCH / "outputs" / "F_xsec"
PANEL = Path(r"D:/量化/data/processed/baostock-daily-20260917/daily_2015_2024.parquet")
INDEX = Path(r"D:/量化/data/raw/tushare/index_daily/20260917-r1/chunk_000001.SH.csv")

ok = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    tag = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{tag}] {name} {detail}")


# ---------- 0. 面板身份 ----------
sha = hashlib.sha256(PANEL.read_bytes()).hexdigest()
check("panel sha256", sha.startswith("1cbb09a11f7c1013"), f"= {sha[:16]}…")

panel = pl.read_parquet(PANEL).filter(pl.col("tradestatus") == 1).filter(
    pl.col("date") <= pl.date(2020, 12, 31)
)
# 与代理实现口径对齐：因子帧层面即剔科创板/北交所（脚本 f_xsec_build.py line 90；评估池反正也会剔）
panel = panel.filter(~pl.col("symbol").str.starts_with("sh.688") & ~pl.col("symbol").str.starts_with("bj."))

# 月末网格：dev 窗全市场并集日历每月最后交易日
me = (
    panel.group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
    .agg(pl.col("date").max().alias("signal_date"))
    .sort("signal_date")
)

# ---------- 1. F09 intraday20 = mean((close-open)/preclose, 20) ----------
ME_DATES = me["signal_date"]
f9_ref = (
    panel.sort("symbol", "date")
    .with_columns(((pl.col("close") - pl.col("open")) / pl.col("preclose")).alias("_intra"))
    .with_columns(pl.col("_intra").rolling_mean(20, min_samples=20).over("symbol").alias("value"))
    .filter(pl.col("date").is_in(ME_DATES))
    .select(symbol=pl.col("symbol"), signal_date=pl.col("date"), value=pl.col("value"))
)
f9_del = pl.read_parquet(OUT / "F09.parquet")
j9 = f9_ref.join(f9_del, on=["symbol", "signal_date"], how="inner", suffix="_del")
cov = j9.height / f9_del.height
ref_nulls = f9_ref["value"].null_count()
ref_nonnull = f9_ref.height - ref_nulls
cov2 = j9.height / ref_nonnull
diff = (j9["value"] - j9["value_del"]).abs().max()
check("F09 交付行全部被参考帧匹配", cov == 1.0, f"join/del = {j9.height}/{f9_del.height}")
check(
    "F09 覆盖率(交付/参考非空行)",
    cov2 > 0.999,
    f"= {cov2:.6f} (ref {f9_ref.height} 行含 {ref_nulls} 空值行 → 非空 {ref_nonnull}; del {f9_del.height})",
)
check("F09 值逐位一致(≤1e-12)", diff <= 1e-12, f"max|Δ| = {diff:.3e}")

# ---------- 2. F10 idio_vol60 = 60d 滚动有截距 OLS 残差的 60d 滚动 std ----------
idx = (
    pl.read_csv(INDEX, schema_overrides={"trade_date": pl.String})
    .with_columns(
        pl.col("trade_date").str.to_date("%Y%m%d").alias("date"),
        (pl.col("close") / pl.col("pre_close") - 1.0).alias("mret"),
    )
    .select("date", "mret")
)

f10 = (
    panel.sort("symbol", "date")
    .with_columns((pl.col("close") / pl.col("preclose") - 1.0).alias("ret"))
    .join(idx, on="date", how="left")
)
g = f10.with_columns(
    pl.col("ret").rolling_mean(60, min_samples=60).over("symbol").alias("_mr"),
    pl.col("mret").rolling_mean(60, min_samples=60).over("symbol").alias("_mm"),
    (pl.col("ret") * pl.col("mret")).rolling_mean(60, min_samples=60).over("symbol").alias("_mrm"),
    (pl.col("mret") * pl.col("mret")).rolling_mean(60, min_samples=60).over("symbol").alias("_m2"),
)
# beta = cov(r,m)/var(m)，矩形式（ddof 因子分子分母同，β 下约掉）
g = g.with_columns(
    ((pl.col("_mrm") - pl.col("_mr") * pl.col("_mm"))
     / (pl.col("_m2") - pl.col("_mm") * pl.col("_mm"))).alias("_beta")
)
g = g.with_columns(
    (pl.col("ret") - (pl.col("_mr") - pl.col("_beta") * pl.col("_mm")) - pl.col("_beta") * pl.col("mret")).alias("_eps"),
)
f10_ref = (
    g.with_columns(pl.col("_eps").rolling_std(60, min_samples=60).over("symbol").alias("value"))
    .filter(pl.col("date").is_in(ME_DATES))
    .select(symbol=pl.col("symbol"), signal_date=pl.col("date"), value=pl.col("value"))
)
f10_del = pl.read_parquet(OUT / "F10.parquet")
j10 = f10_ref.join(f10_del, on=["symbol", "signal_date"], how="inner", suffix="_del")
check("F10 交付行全部被参考帧匹配", j10.height == f10_del.height, f"join/del = {j10.height}/{f10_del.height}")
rel = (j10["value"] - j10["value_del"]).abs() / j10["value"].abs().clip(lower_bound=1e-12)
check("F10 值相对差逐位", rel.max() <= 1e-9, f"max rel = {rel.max():.3e}")
# 参考帧多出的行：按年分布披露（生效门槛差异对账）
extra = f10_ref.join(f10_del, on=["symbol", "signal_date"], how="anti")
by_year = extra.group_by(pl.col("signal_date").dt.year()).len().sort("signal_date")
print(f"[INFO] F10 参考帧多出 {extra.height} 行（生效门槛实现差异），按年: {by_year.to_dicts()}")
cov10 = j10.height / f10_del.height
check("F10 覆盖(交集/交付)", cov10 == 1.0, f"= {cov10:.6f} (del {f10_del.height} 全部一致)")

# ---------- 3. 冻结断言：全部 10 个 parquet ----------
for i in range(1, 11):
    p = pl.read_parquet(OUT / f"F{i:02d}.parquet")
    smax = p["signal_date"].max()
    dup = p.group_by(["symbol", "signal_date"]).len().filter(pl.col("len") > 1).height
    check(f"F{i:02d} signal_date ≤2020-12-31 且键唯一", smax <= FREEZE and dup == 0, f"max={smax}, dup={dup}")

# ---------- 4. 边缘判定核对（F02 mono 差 0.004 淘汰 / F08 2015 反号淘汰）----------
f02 = json.loads((OUT / "F02.json").read_text(encoding="utf-8"))
f08 = json.loads((OUT / "F08.json").read_text(encoding="utf-8"))
s2, s8 = f02["screen"], f08["screen"]
check("F02 crit2 判 False", s2["crit2_mono"] is False, f"mono={f02['eval']['monotonicity']:.4f}, t={s2['t_ic']:.2f} (crit1 过)")
check("F08 crit3 判 False", s8["crit3_2015_ok"] is False, f"ic_2015={s8['ic_2015']:.4f} vs 主IC {f08['eval']['ic_mean']:.4f}")
check("F02/F08 screen_pass 均 False", s2["screen_pass"] is False and s8["screen_pass"] is False)

# 存活三者的 screen 全过
for fid in ("F06", "F09", "F10"):
    s = json.loads((OUT / f"{fid}.json").read_text(encoding="utf-8"))["screen"]
    check(f"{fid} screen_pass", s["screen_pass"] is True, f"t={s['t_ic']:.2f}")

# ---------- 5. 期数一致性（各因子生效门槛不同 → n_dates 可 < 68；上限 68 且族内最大=68）----------
nd = {}
for i in range(1, 11):
    nd[f"F{i:02d}"] = json.loads((OUT / f"F{i:02d}.json").read_text(encoding="utf-8"))["eval"]["n_dates"]
check("n_dates 全部 ≤68 且 >0", all(0 < v <= 68 for v in nd.values()), f"= {nd}")
check("族内最大期数=68（低门槛因子达满窗）", max(nd.values()) == 68)

print("\n== F 族验收总结:", "ALL PASS" if ok else "存在 FAIL", "==")
