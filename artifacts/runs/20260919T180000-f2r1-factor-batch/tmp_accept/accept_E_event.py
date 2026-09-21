# E 族主对话独立验收（E 代理死于报告撰写前，20/20 因子产出已落地）
# 复算 E16 div_yld120（存活者）+ E04 fcst_cnt120（零填充代表）+ 判定核对 + 冻结断言
# 运行：D:/量化/.venv/Scripts/python.exe accept_E_event.py
import glob
import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
BATCH = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch"
OUT = BATCH / "outputs/E_event"
PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
TS = ROOT / "data/raw/tushare"
FREEZE = date(2020, 12, 31)

ok = True


def check(name, cond, detail=""):
    global ok
    tag = "PASS" if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{tag}] {name} {detail}")


def read_chunks(pattern, cols=None, num_cols=(), name_lo="", name_hi=""):
    frames = []
    for p in sorted(glob.glob(str(pattern))):
        base = Path(p).name
        if not base.endswith(".csv"):
            continue
        key = base.replace("chunk_period_", "chunk_").replace("chunk_", "").replace(".csv", "")
        if name_lo and not (name_lo <= key <= name_hi):  # 与代理一致：按 chunk 文件名日期过滤
            continue
        if Path(p).stat().st_size <= 100:  # 空文件跳过（对齐代理阈值 100B）
            continue
        df = pl.read_csv(p, infer_schema_length=10000)
        if df.height:
            if cols is not None:  # 早选列，避免无关列跨 chunk 类型冲突
                df = df.select([c for c in cols if c in df.columns])
            if num_cols:
                df = df.with_columns([  # 同名列跨 chunk 类型不一，统一 Float64
                    pl.col(c).cast(pl.Float64, strict=False) for c in num_cols if c in df.columns
                ])
            frames.append(df)
    return pl.concat(frames, how="diagonal") if frames else pl.DataFrame()


def to_date(df, cols):
    return df.with_columns([
        pl.col(c).cast(pl.String).str.to_date("%Y%m%d") for c in cols
    ])


def sym(df):
    return df.with_columns(
        (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
         + "." + pl.col("ts_code").str.split(".").list.first()).alias("symbol")
    )


panel = pl.read_parquet(PANEL)
me = (
    panel.filter(pl.col("date") <= FREEZE)
    .group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
    .agg(pl.col("date").max().alias("signal_date"))
    .sort("signal_date")
)
ME = me["signal_date"].to_list()
ME = [d for d in ME if d <= date(2020, 11, 30)]  # 与代理一致：2020-12-31 信号因 h=20 标签跨年剔除
check("月末网格首末", ME[0] == date(2015, 1, 30) and ME[-1] == date(2020, 11, 30) and len(ME) == 71,
      f"{ME[0]}..{ME[-1]} n={len(ME)}")
me_close = panel.filter(pl.col("date").is_in(pl.Series(ME))).select("symbol", "date", "close")

# ---------- E16 复算 ----------
V = pl.concat([
    read_chunks(TS / "dividend/20260913-r2/chunk_*.csv",
                cols=["ts_code", "div_proc", "ann_date", "ex_date", "cash_div"],
                num_cols=("cash_div",), name_lo="20150101", name_hi="20171231"),
    read_chunks(TS / "dividend/20260909-r3/chunk_*.csv",
                cols=["ts_code", "div_proc", "ann_date", "ex_date", "cash_div"],
                num_cols=("cash_div",), name_lo="20180101", name_hi="20201231"),
], how="diagonal")
V = V.with_columns(pl.col("cash_div").cast(pl.Float64, strict=False).fill_null(0.0))
V = to_date(V, ["ann_date", "ex_date"])
LAST_SIGNAL = date(2020, 11, 30)  # 代理 E 脚本网格末期（2020-12-31 信号因标签跨年剔除）
V = (V.filter(pl.col("ts_code").str.contains(".")).pipe(sym)
     .filter(pl.col("div_proc") == "实施")
     .filter(pl.col("ex_date").is_not_null())
     .with_columns(pl.col("cash_div").fill_null(0.0))
     .unique()
     .filter(pl.col("ex_date") <= LAST_SIGNAL))
check("dividend(实施) 行数与代理一致", V.height == 16979 and V["symbol"].n_unique() == 3957,
      f"= {V.height} 行 / {V['symbol'].n_unique()} 符号")

rows = []
for t in ME:
    w = V.filter((pl.col("ex_date") > t - timedelta(days=365)) & (pl.col("ex_date") <= t))
    dv = w.group_by("symbol").agg(pl.col("cash_div").sum().alias("_d"))
    cl = me_close.filter(pl.col("date") == t).select("symbol", "close")
    j = dv.join(cl, on="symbol").with_columns(
        (pl.col("_d") / pl.col("close")).alias("value"),
        pl.lit(t).alias("signal_date"),
    )
    rows.append(j.select("symbol", "signal_date", "value"))
e16_ref = pl.concat(rows)
e16_del = pl.read_parquet(OUT / "E16.parquet")
j16 = e16_ref.join(e16_del, on=["symbol", "signal_date"], how="inner", suffix="_del")
check("E16 交付行全部被参考帧匹配", j16.height == e16_del.height, f"join/del = {j16.height}/{e16_del.height}")
rel16 = (j16["value"] - j16["value_del"]).abs() / j16["value"].abs().clip(lower_bound=1e-12)
check("E16 值相对差 ≤1e-12", rel16.max() <= 1e-12, f"max rel = {rel16.max():.3e}")
if rel16.max() > 1e-12:  # 诊断：差异最大的行
    bad = j16.with_columns(rel16.alias("_rel")).sort("_rel", descending=True).head(5)
    print("[INFO] E16 差异 top5:", bad.select("symbol", "signal_date", "value", "value_del", "_rel").to_dicts())

# ---------- E04 复算（代理未对 forecast 去重——按行计数如实复算，另披露重复行）----------
F = read_chunks(TS / "forecast/20260909-r1/chunk_*.csv")
dupf = F.height - F.unique().height
print(f"[INFO] forecast 原始重复行 = {dupf} / {F.height}（代理按行计数，如实对齐复算）")
F = to_date(F, ["ann_date"]).pipe(sym).filter(
    pl.col("ann_date").is_not_null() & (pl.col("ann_date") <= FREEZE)
)
rows4 = []
for t in ME:
    w = F.filter((pl.col("ann_date") > t - timedelta(days=120)) & (pl.col("ann_date") <= t))
    cnt = w.group_by("symbol").len().with_columns(pl.col("len").cast(pl.Float64).alias("value"), pl.lit(t).alias("signal_date")).select("symbol", "signal_date", "value")
    cl = me_close.filter(pl.col("date") == t).select("symbol").with_columns(
        pl.lit(0.0).alias("value"), pl.lit(t).alias("signal_date"))
    rows4.append(pl.concat([cl.select("symbol", "signal_date", "value"), cnt], how="vertical")
                 .group_by(["symbol", "signal_date"]).agg(pl.col("value").sum().alias("value")).sort("symbol"))
e4_ref = pl.concat(rows4)
e4_del = pl.read_parquet(OUT / "E04.parquet")
j4 = e4_ref.join(e4_del, on=["symbol", "signal_date"], how="inner", suffix="_del")
check("E04 交付行全部被参考帧匹配", j4.height == e4_del.height, f"join/del = {j4.height}/{e4_del.height}")
d4 = ((j4["value"] - j4["value_del"]).abs()).max()
check("E04 值逐位一致", d4 <= 1e-12, f"max|Δ| = {d4:.3e}")

# ---------- 20 个 JSON 主对话终裁：按预登记 §2 逐字从 eval 数据算四条 ----------
n_surv = 0
for i in range(1, 21):
    fid = f"E{i:02d}"
    r = json.loads((OUT / f"{fid}.json").read_text(encoding="utf-8"))
    ev = r["eval"]
    t = r.get("t_value", ev.get("t_ic"))
    mono = ev["monotonicity"]
    icm = ev["ic_mean"]
    ic15 = ev.get("ic_by_year", {}).get("2015")
    cov_ratio = r.get("coverage_median_symbols", 0.0) / r.get("pool_median_symbols", 1.0)
    c1 = abs(t) >= 2.0
    c2 = (mono > 0) == (icm > 0) and abs(mono) >= 0.3
    c3 = (ic15 is None) or not ((ic15 > 0) != (icm > 0) and abs(ic15) > 0.03)
    c4 = cov_ratio >= 0.5
    mine = c1 and c2 and c3 and c4
    sp = bool(r.get("survived_prelim"))
    detail = (f"t={t:+.2f} mono={mono:+.2f} ic={icm:+.4f} ic15={'n/a' if ic15 is None else format(ic15, '+.4f')} "
              f"cov={cov_ratio:.1%}")
    check(f"{fid} 主对话终裁==代理初判({sp})", mine == sp, detail)
    if mine:
        n_surv += 1
check("终裁存活数=1(E16)", n_surv == 1, f"= {n_surv}")

# ---------- 冻结断言 ----------
for i in range(1, 21):
    p = pl.read_parquet(OUT / f"E{i:02d}.parquet")
    smax, dup = p["signal_date"].max(), p.group_by(["symbol", "signal_date"]).len().filter(pl.col("len") > 1).height
    if not (smax <= FREEZE and dup == 0):
        check(f"E{i:02d} 冻结断言", False, f"max={smax}, dup={dup}")
check("全部 20 个 parquet signal_date≤2020-12-31 且键唯一", True)

print("\n== E 族验收总结:", "ALL PASS" if ok else "存在 FAIL", "==")
