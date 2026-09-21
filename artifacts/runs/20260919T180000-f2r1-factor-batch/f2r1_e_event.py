# -*- coding: utf-8 -*-
"""F2-R1 E 族（公告事件，E01..E20）批量因子计算与评估。

口径（冻结于 docs/research/exp-20260919-factor-round-f2r1-prereg.md §3-E）：
- 事件在 ann_date（分红按 ex_date）可见，聚合到月末 signal_date 的 trailing 窗口，
  即"月末时点已公告/已发生事件"的回看聚合，无前视；
- 信号网格 = v0 面板（baostock daily_2015_2024）月度最后交易日，dev 窗 2015-01..2020-11
  （共 71 期；2020-12 不发信号，避免 20 日前向标签跨入 val 2021）；
- 评估 = F1 harness evaluate_factor，horizon_days=20, n_groups=10, eval_freq="M",
  min_history_rows=60；signal_date 全路径 <= 2024-12-31 断言。

单位披露：repurchase.amount=元；share_float.float_share=万股、float_ratio=占总股本%；
holdertrade.change_ratio=占总股本%；dividend.cash_div=每股股利(税前,元)；
daily_basic.circ_mv=万元；forecast.net_profit_min/max=万元、p_change=%。
E07 预告净利中值按 万元*1e4 折元与快报 n_income(元) 相比。
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from datetime import date, timedelta

ROOT = r"D:\量化"
sys.path.insert(0, os.path.join(ROOT, "src"))

import polars as pl  # noqa: E402

from quant.factors.eval import (  # noqa: E402
    FREEZE_END,
    FactorEvalConfig,
    _forward_return_grid,
    _prepare_panel,
    evaluate_factor,
)

RUN = os.path.join(ROOT, "artifacts", "runs", "20260919T180000-f2r1-factor-batch")
OUT = os.path.join(RUN, "outputs", "E_event")
os.makedirs(OUT, exist_ok=True)

PANEL_PATH = os.path.join(ROOT, "data", "processed", "baostock-daily-20260917",
                          "daily_2015_2024.parquet")
TS = os.path.join(ROOT, "data", "raw", "tushare")

CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
LAST_SIGNAL = date(2020, 11, 30)  # dev 终点：2020-12 信号不发（标签不跨 dev/val 边界）

t0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time()-t0:7.1f}s] {msg}", flush=True)


def sym_expr(col: str = "ts_code") -> pl.Expr:
    """tushare 代码 -> 面板符号风格 600519.SH -> sh.600519；无后缀行在读取时剔除。"""
    parts = pl.col(col).str.split(".")
    return pl.concat_str(
        parts.list.last().str.to_lowercase(), pl.lit("."), parts.list.first()
    ).alias("symbol")


def read_chunks(pattern: str, name_lo: str, name_hi: str, nonempty_only: bool = True):
    fs = []
    for p in sorted(glob.glob(pattern)):
        base = os.path.basename(p)
        if not base.endswith(".csv"):
            continue
        key = base.replace("chunk_period_", "chunk_").replace("chunk_", "").replace(".csv", "")
        if not (name_lo <= key <= name_hi):
            continue
        if nonempty_only and os.path.getsize(p) <= 100:
            continue
        fs.append(p)
    if not fs:
        return pl.DataFrame()
    dfs = []
    for p in fs:
        try:
            dfs.append(pl.read_csv(p, infer_schema_length=0))
        except pl.exceptions.NoDataError:
            continue
    cols = set(dfs[0].columns)
    dfs = [d.select(sorted(cols & set(d.columns))) for d in dfs]
    return pl.concat(dfs, how="diagonal") if dfs else pl.DataFrame()


def parse_date(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    return df.with_columns([
        pl.col(c).cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False)
        for c in cols if c in df.columns
    ])


def cast_num(df: pl.DataFrame, cols: list[str]) -> pl.DataFrame:
    return df.with_columns([
        pl.col(c).cast(pl.Float64, strict=False) for c in cols if c in df.columns
    ])


# ---------------------------------------------------------------------------
# 1. 面板与月末网格
# ---------------------------------------------------------------------------
log("加载 v0 面板 ...")
panel = pl.read_parquet(PANEL_PATH,
                        columns=["date", "symbol", "close", "preclose",
                                 "tradestatus", "isST"])
panel = panel.with_columns(pl.col("tradestatus").cast(pl.Int64),
                           pl.col("isST").cast(pl.Int64))

me_dates = (
    panel.filter(pl.col("date") <= LAST_SIGNAL)
    .with_columns(pl.col("date").dt.truncate("1mo").alias("_m"))
    .group_by("_m").agg(pl.col("date").max().alias("date"))
    .sort("date")["date"].to_list()
)
log(f"月末信号期数 = {len(me_dates)}（{me_dates[0]} .. {me_dates[-1]}）")
assert max(me_dates) <= LAST_SIGNAL <= FREEZE_END

me_close = (
    panel.filter(pl.col("date").is_in(me_dates))
    .select("symbol", "date", "close")
)

# ---------------------------------------------------------------------------
# 2. daily_basic 月末流通市值（E08/E20 分母）
# ---------------------------------------------------------------------------
log("加载 daily_basic 月末文件 ...")
me_keys = {d.strftime("%Y%m%d") for d in me_dates}
basic_frames = []
for sub in ("20260913-r2", "20260909-r1"):
    for p in glob.glob(os.path.join(TS, "daily_basic", sub, "chunk_*.csv")):
        key = os.path.basename(p)[6:14]
        if key in me_keys:
            df = pl.read_csv(p, infer_schema_length=0)
            if df.height == 0:
                continue
            basic_frames.append(
                df.with_columns(sym_expr(), pl.col("circ_mv").cast(pl.Float64, strict=False))
                .select("symbol", "circ_mv")
                .with_columns(pl.lit(date(int(key[:4]), int(key[4:6]), int(key[6:]))).alias("date"))
            )
me_basic = pl.concat(basic_frames).unique(subset=["symbol", "date"], keep="first")
log(f"daily_basic 月末覆盖 {me_basic.height} 行")

# ---------------------------------------------------------------------------
# 3. 事件源加载（只读；窗口内需要的批次）
# ---------------------------------------------------------------------------
log("加载事件源 ...")

F = read_chunks(os.path.join(TS, "forecast", "20260909-r1", "chunk_*.csv"), "201809", "202012")
F = parse_date(F, ["ann_date", "end_date"])
F = cast_num(F, ["p_change_min", "p_change_max", "net_profit_min", "net_profit_max",
                 "last_parent_net"])
F = (F.filter(pl.col("ts_code").str.contains("."))
     .with_columns(sym_expr())
     .filter(pl.col("ann_date").is_not_null() & (pl.col("ann_date") <= LAST_SIGNAL)))
TYPE_POS = ("预增", "略增", "扭亏", "续盈")
TYPE_NEG = ("预减", "略减", "首亏", "预亏", "续亏")
sign_expr = (
    pl.when(pl.col("mid").is_not_null())
    .then(pl.col("mid").sign())
    .otherwise(
        pl.when(pl.col("type").is_in(TYPE_POS)).then(1.0)
        .when(pl.col("type").is_in(TYPE_NEG)).then(-1.0)
        .otherwise(None)
    )
)
F = F.with_columns(
    ((pl.col("p_change_min") + pl.col("p_change_max")) / 2.0).alias("mid")
).with_columns(
    pl.when(pl.col("mid").is_not_null()).then(pl.col("mid")).otherwise(
        pl.when(
            pl.col("net_profit_min").is_not_null() & pl.col("net_profit_max").is_not_null()
            & pl.col("last_parent_net").is_not_null() & (pl.col("last_parent_net") > 0)
        ).then(
            ((pl.col("net_profit_min") + pl.col("net_profit_max")) / 2.0
             / pl.col("last_parent_net") - 1.0) * 100.0
        ).otherwise(None)
    ).alias("mid")
).with_columns(sign_expr.alias("f_sign"))
log(f"forecast 行数={F.height} 符号数={F['symbol'].n_unique()}")

X = read_chunks(os.path.join(TS, "express", "20260909-r1", "chunk_*.csv"), "20181231", "20201231")
X = parse_date(X, ["ann_date", "end_date"])
X = cast_num(X, ["revenue", "n_income"])
X = (X.filter(pl.col("ts_code").str.contains("."))
     .with_columns(sym_expr())
     .filter(pl.col("ann_date").is_not_null() & (pl.col("ann_date") <= LAST_SIGNAL)))
log(f"express 行数={X.height} 符号数={X['symbol'].n_unique()}")

R = read_chunks(os.path.join(TS, "repurchase", "20260909-r3", "chunk_*.csv"), "201601", "202012")
R = parse_date(R, ["ann_date", "end_date"])
R = cast_num(R, ["amount"])
R = (R.filter(pl.col("ts_code").str.contains("."))
     .with_columns(sym_expr())
     .filter(pl.col("ann_date").is_not_null() & (pl.col("ann_date") <= LAST_SIGNAL)))
log(f"repurchase 行数={R.height} 符号数={R['symbol'].n_unique()}")

H = read_chunks(os.path.join(TS, "stk_holdertrade", "20260909-r3", "chunk_*.csv"),
                "201601", "202012")
H = parse_date(H, ["ann_date"])
H = cast_num(H, ["change_ratio"])
H = (H.filter(pl.col("ts_code").str.contains("."))
     .with_columns(sym_expr())
     .filter(pl.col("ann_date").is_not_null() & (pl.col("ann_date") <= LAST_SIGNAL)))
log(f"holdertrade 行数={H.height} 符号数={H['symbol'].n_unique()}")

S = read_chunks(os.path.join(TS, "share_float", "20260909-r3", "chunk_*.csv"),
                "201601", "202012")
S = parse_date(S, ["ann_date", "float_date"])
S = cast_num(S, ["float_share", "float_ratio"])
S = (S.filter(pl.col("ts_code").str.contains("."))
     .with_columns(sym_expr())
     .filter(pl.col("ann_date").is_not_null() & (pl.col("ann_date") <= LAST_SIGNAL)))
log(f"share_float 行数={S.height} 符号数={S['symbol'].n_unique()}")

V = pl.concat([
    read_chunks(os.path.join(TS, "dividend", "20260913-r2", "chunk_*.csv"),
                "20150101", "20171231"),
    read_chunks(os.path.join(TS, "dividend", "20260909-r3", "chunk_*.csv"),
                "20180101", "20201231"),
], how="diagonal")
V = parse_date(V, ["ann_date", "ex_date"])
V = cast_num(V, ["cash_div"])
V = (V.filter(pl.col("ts_code").str.contains("."))
     .with_columns(sym_expr())
     .filter(pl.col("div_proc") == "实施")
     .filter(pl.col("ex_date").is_not_null())
     .with_columns(pl.col("cash_div").fill_null(0.0))
     .unique()
     .filter(pl.col("ex_date") <= LAST_SIGNAL))
log(f"dividend(实施) 行数={V.height} 符号数={V['symbol'].n_unique()}")

# dev 窗事件量统计（预告/快报按 ann_date，分红按 ex_date）
DEV_LO = date(2015, 1, 1)
DEV_HI = date(2020, 12, 31)


def src_stats(df: pl.DataFrame, col: str) -> dict:
    w = df.filter(pl.col(col).is_between(DEV_LO, DEV_HI))
    return {"rows": w.height, "symbols": int(w["symbol"].n_unique()),
            "first": str(w[col].min()), "last": str(w[col].max())}


EVENT_STATS = {
    "forecast": src_stats(F, "ann_date"),
    "express": src_stats(X, "ann_date"),
    "repurchase": src_stats(R, "ann_date"),
    "stk_holdertrade": src_stats(H, "ann_date"),
    "share_float": src_stats(S, "ann_date"),
    "dividend(实施,按ex_date)": src_stats(V, "ex_date"),
}
log(f"dev 窗事件量: {json.dumps(EVENT_STATS, ensure_ascii=False)}")

# ---------------------------------------------------------------------------
# 4. 月末逐期因子计算（trailing 窗，无前视）
# ---------------------------------------------------------------------------
col_names = ["E01", "E02", "E03", "E04", "E05", "E06", "E07", "E08", "E09", "E10",
             "E11", "E12", "E13", "E14", "E15", "E16", "E17", "E18", "E19", "E20"]
ZEROFILL = {"E04", "E05", "E09", "E17", "E18", "E19"}  # 计数/0-1 型因子，无事件填 0
# 其余因子无事件 -> null（覆盖=有事件股票数）

base_syms = me_close["symbol"].unique().to_list()
acc = {k: [] for k in col_names}          # 每 (date) -> {symbol: value}
me_pairs = {d: set() for d in me_dates}   # 每月末在交收网格内的符号

for d in me_dates:
    t = d
    t120 = t - timedelta(days=120)
    t60 = t - timedelta(days=60)
    t20 = t - timedelta(days=20)
    t365 = t - timedelta(days=365)
    f60 = t + timedelta(days=60)
    f120 = t + timedelta(days=120)

    vals = {k: {} for k in col_names}
    close_d = me_close.filter(pl.col("date") == t)
    basic_d = me_basic.filter(pl.col("date") == t)
    circ = dict(zip(basic_d["symbol"].to_list(), basic_d["circ_mv"].to_list()))
    close_map = dict(zip(close_d["symbol"].to_list(), close_d["close"].to_list()))

    # ---- forecast 族 ----
    w = F.filter(pl.col("ann_date") > t120).filter(pl.col("ann_date") <= t)
    if w.height:
        cnt = (w.group_by("symbol").len())
        vals["E04"] = dict(zip(cnt["symbol"].to_list(), cnt["len"].cast(pl.Float64).to_list()))

        wm = w.filter(pl.col("mid").is_not_null()).sort("ann_date")
        if wm.height:
            last_mid = wm.group_by("symbol").last()
            vals["E01"] = dict(zip(last_mid["symbol"].to_list(), last_mid["mid"].to_list()))
            vals["E03"] = dict(zip(last_mid["symbol"].to_list(), last_mid["mid"].to_list()))
        wp = w.filter(pl.col("p_change_max").is_not_null()).sort("ann_date")
        if wp.height:
            last_pmax = wp.group_by("symbol").last()
            vals["E02"] = dict(zip(last_pmax["symbol"].to_list(), last_pmax["p_change_max"].to_list()))

        # E03: 最新预告中值 - 同期(end_date)首个预告中值（首个可早于 120d 窗，但 ann<=t）
        if wm.height:
            f_le = F.filter(pl.col("ann_date") <= t).filter(pl.col("mid").is_not_null())
            first_per = f_le.sort("ann_date").group_by("symbol", "end_date").first()
            per = (
                last_mid.select("symbol", "end_date", pl.col("mid").alias("mid_latest"))
                .join(first_per.select("symbol", "end_date", pl.col("mid").alias("mid_first")),
                      on=["symbol", "end_date"], how="left")
            ).with_columns(
                (pl.col("mid_latest") - pl.col("mid_first").fill_null(pl.col("mid_latest")))
                .alias("E03v")
            )
            vals["E03"] = dict(zip(per["symbol"].to_list(), per["E03v"].to_list()))

        w20 = w.filter(pl.col("ann_date") > t20).filter(pl.col("f_sign").is_not_null())
        if w20.height:
            s20 = w20.sort("ann_date").group_by("symbol").last()
            vals["E05"] = dict(zip(s20["symbol"].to_list(), s20["f_sign"].to_list()))

        wsg = w.filter(pl.col("f_sign").is_not_null())
        if wsg.height:
            sg = wsg.group_by("symbol").agg(pl.col("f_sign").sum())
            vals["E17"] = dict(zip(sg["symbol"].to_list(), sg["f_sign"].to_list()))

    # ---- express 族 ----
    x_le = X.filter(pl.col("ann_date") <= t)
    w = x_le.filter(pl.col("ann_date") > t120)
    if w.height:
        cnt = w.group_by("symbol").len()
        vals["E18"] = dict(zip(cnt["symbol"].to_list(), cnt["len"].cast(pl.Float64).to_list()))
    if x_le.height:
        xl = (x_le.sort("ann_date").group_by("symbol").last()
              .filter(pl.col("revenue").is_not_null() & pl.col("end_date").is_not_null()))
        if xl.height:
            prior = (x_le.filter(pl.col("revenue").is_not_null())
                     .select("symbol", "end_date", pl.col("revenue").alias("rev_prev")))
            e06 = (xl.with_columns(pl.col("end_date").dt.offset_by("-1y").alias("end_prev"))
                   .join(prior, left_on=["symbol", "end_prev"],
                         right_on=["symbol", "end_date"], how="left")
                   .with_columns(
                       pl.when(pl.col("rev_prev") > 0)
                       .then(pl.col("revenue") / pl.col("rev_prev") - 1.0)
                       .otherwise(None).alias("E06v")))
            e06 = e06.filter(pl.col("E06v").is_not_null())
            vals["E06"] = dict(zip(e06["symbol"].to_list(), e06["E06v"].to_list()))

            xinc = xl.filter(pl.col("n_income").is_not_null())
            if xinc.height:
                fm = (F.filter(pl.col("ann_date") <= t).filter(pl.col("mid").is_not_null())
                      .sort("ann_date").group_by("symbol", "end_date").last()
                      .select("symbol", "end_date", "mid"))
                e07 = (xinc.join(fm, on=["symbol", "end_date"], how="left")
                       .with_columns(
                           pl.when(pl.col("mid") > 0)
                           .then(pl.col("n_income") / (pl.col("mid") * 1e4) - 1.0)
                           .otherwise(None).alias("E07v"))
                       .filter(pl.col("E07v").is_not_null()))
                vals["E07"] = dict(zip(e07["symbol"].to_list(), e07["E07v"].to_list()))

    # ---- repurchase 族 ----
    w = R.filter(pl.col("ann_date") > t120).filter(pl.col("ann_date") <= t)
    if w.height:
        amt = (w.filter(pl.col("amount").is_not_null())
               .group_by("symbol", "end_date").agg(pl.col("amount").max())
               .group_by("symbol").agg(pl.col("amount").sum()))
        for sym, a in zip(amt["symbol"].to_list(), amt["amount"].to_list()):
            c = circ.get(sym)
            if c is not None and c > 0:
                vals["E08"][sym] = a / (c * 1e4)
        w20 = w.filter(pl.col("ann_date") > t20).group_by("symbol").len()
        vals["E09"] = {s: 1.0 for s in w20["symbol"].to_list()}

    # ---- holdertrade 族 ----
    w = H.filter(pl.col("ann_date") > t120).filter(pl.col("ann_date") <= t)
    if w.height:
        net = (w.filter(pl.col("change_ratio").is_not_null())
               .with_columns(pl.when(pl.col("in_de") == "IN").then(pl.col("change_ratio"))
                             .otherwise(-pl.col("change_ratio")).alias("signed"))
               .group_by("symbol").agg(pl.col("signed").sum()))
        vals["E10"] = dict(zip(net["symbol"].to_list(), net["signed"].to_list()))
        de = (w.filter((pl.col("in_de") == "DE") & pl.col("change_ratio").is_not_null())
              .group_by("symbol").agg(pl.col("change_ratio").sum()))
        vals["E11"] = dict(zip(de["symbol"].to_list(), de["change_ratio"].to_list()))
        wk = (w.filter(pl.col("ann_date") > t60)
              .filter(pl.col("holder_type").is_in(["C", "P"]))
              .filter(pl.col("change_ratio").is_not_null())
              .with_columns(pl.when(pl.col("in_de") == "IN").then(pl.col("change_ratio"))
                            .otherwise(-pl.col("change_ratio")).alias("signed"))
              .group_by("symbol").agg(pl.col("signed").sum()))
        vals["E12"] = dict(zip(wk["symbol"].to_list(), wk["signed"].to_list()))
        w20 = w.filter((pl.col("ann_date") > t20) & (pl.col("in_de") == "IN")).group_by("symbol").len()
        vals["E19"] = dict(zip(w20["symbol"].to_list(), w20["len"].cast(pl.Float64).to_list()))

    # ---- share_float 族 ----
    w = S.filter(pl.col("ann_date") <= t)
    if w.height:
        fwd = w.filter(pl.col("float_date") > t).filter(pl.col("float_date") <= f60)
        if fwd.height:
            r13 = fwd.filter(pl.col("float_ratio").is_not_null()).group_by("symbol").agg(
                pl.col("float_ratio").sum())
            vals["E13"] = dict(zip(r13["symbol"].to_list(), r13["float_ratio"].to_list()))
        past = w.filter(pl.col("float_date") > t20).filter(pl.col("float_date") <= t)
        if past.height:
            r14 = past.filter(pl.col("float_ratio").is_not_null()).group_by("symbol").agg(
                pl.col("float_ratio").sum())
            vals["E14"] = dict(zip(r14["symbol"].to_list(), r14["float_ratio"].to_list()))
        pr = w.filter(pl.col("float_date") > t).filter(pl.col("float_date") <= f120)
        pr = pr.filter(pl.col("float_share").is_not_null())
        if pr.height:
            fs = pr.group_by("symbol").agg(pl.col("float_share").sum())
            for sym, sh in zip(fs["symbol"].to_list(), fs["float_share"].to_list()):
                c, px = circ.get(sym), close_map.get(sym)
                if c is not None and c > 0 and px is not None:
                    vals["E20"][sym] = sh * px / c  # (万股*元)/(万元) = 解禁市值/流通市值

    # ---- dividend 族 ----
    w = V.filter(pl.col("ex_date") > t20).filter(pl.col("ex_date") <= t)
    if w.height:
        dv = w.group_by("symbol").agg(pl.col("cash_div").sum())
        for sym, dsum in zip(dv["symbol"].to_list(), dv["cash_div"].to_list()):
            px = close_map.get(sym)
            if px is not None and px > 0:
                vals["E15"][sym] = dsum / px
    w = V.filter(pl.col("ex_date") > t365).filter(pl.col("ex_date") <= t)
    if w.height:
        dv = w.group_by("symbol").agg(pl.col("cash_div").sum())
        for sym, dsum in zip(dv["symbol"].to_list(), dv["cash_div"].to_list()):
            px = close_map.get(sym)
            if px is not None and px > 0:
                vals["E16"][sym] = dsum / px

    # ---- 收集 ----
    dset = set(close_d["symbol"].to_list())
    me_pairs[t] = dset
    for k in col_names:
        acc[k].append((t, vals[k]))

log("月末逐期计算完成，组装因子帧 ...")


def build_frame(fid: str) -> pl.DataFrame:
    rows = []
    for t, m in acc[fid]:
        if fid in ZEROFILL:
            for s in me_pairs[t]:
                rows.append((s, t, float(m.get(s, 0.0))))
        else:
            for s, v in m.items():
                if v is not None:
                    rows.append((s, t, float(v)))
    df = pl.DataFrame(rows, schema={"symbol": pl.String, "signal_date": pl.Date,
                                    "value": pl.Float64}, orient="row")
    assert df["signal_date"].max() <= FREEZE_END, f"{fid} 冻结线突破"
    assert df["signal_date"].max() <= LAST_SIGNAL, f"{fid} 超 dev 窗"
    return df.unique(subset=["symbol", "signal_date"], keep="first")


# ---------------------------------------------------------------------------
# 5. 覆盖参考：全合格池月度中位
# ---------------------------------------------------------------------------
log("计算全合格池月度规模参考 ...")
prepared = _prepare_panel(panel, CFG)
fwd = _forward_return_grid(prepared, CFG.horizon_days)
me_fwd = fwd.filter(pl.col("date").is_in(me_dates))
pool_sizes = me_fwd.group_by("date").len().sort("date")
POOL_MEDIAN = float(pool_sizes["len"].median())
log(f"全合格池月末符号数中位 = {POOL_MEDIAN:.0f}")


def coverage_median(factor: pl.DataFrame) -> tuple[float, float]:
    """返回 (全部 71 期中位覆盖[缺失月计 0，淘汰标准 4 口径], 有数据月中位覆盖)。"""
    j = (factor.join(me_fwd, left_on=["symbol", "signal_date"],
                     right_on=["symbol", "date"], how="inner")
        .filter(pl.col("value").is_not_null())
        .group_by("signal_date").len())
    if j.height == 0:
        return 0.0, 0.0
    all_months = (
        pl.DataFrame({"signal_date": me_dates}, schema={"signal_date": pl.Date})
        .join(j, on="signal_date", how="left")
        .with_columns(pl.col("len").fill_null(0))
    )
    return (float(all_months["len"].median()), float(j["len"].median()))


# ---------------------------------------------------------------------------
# 6. 逐因子评估与输出
# ---------------------------------------------------------------------------
META = {
    "E01": ("fcst_np", "120d 内最新预告 (p_change_min+max)/2（p_change 缺失用净利区间/去年同期推算）", "forecast"),
    "E02": ("fcst_np_max", "120d 内最新预告 p_change_max", "forecast"),
    "E03": ("fcst_rev", "同期(end_date)最新预告中值-首个预告中值（首个不限窗龄但 ann<=t）", "forecast"),
    "E04": ("fcst_cnt120", "120d 预告次数（无事件填 0）", "forecast"),
    "E05": ("fcst_fresh20", "20d 内最新预告方向 sign(中值或类型映射)，无填 0", "forecast"),
    "E06": ("expr_rev_yoy", "最新快报营收/上年同期快报营收-1（同期= end_date-1y，ann<=t）", "express"),
    "E07": ("expr_surp", "快报 n_income(元)/(同期最新预告净利中值(万元)*1e4)-1", "express+forecast"),
    "E08": ("repo_120", "120d 回购金额(元, 每(ts_code,end_date)取进度最大额)/流通市值(元)", "repurchase+daily_basic"),
    "E09": ("repo_ann20", "20d 内有回购公告(0/1，无填 0)", "repurchase"),
    "E10": ("hb_net120", "120d 增持净比例 = ΣIN-ΣDE (change_ratio, %总股本)", "stk_holdertrade"),
    "E11": ("hs_net120", "120d 减持比例合计 = ΣDE (窗内无任何记录->null)", "stk_holdertrade"),
    "E12": ("hb_key60", "60d 关键股东(公司C+高管P)净增持 ΣIN-ΣDE", "stk_holdertrade"),
    "E13": ("float_fwd60", "已公告(ann<=t)且 float_date 在 (t, t+60d] 的解禁比例合计(%总股本)", "share_float"),
    "E14": ("float_past20", "float_date 在 (t-20d, t] 且 ann<=t 的解禁比例合计", "share_float"),
    "E15": ("div_ex20", "20d 内除息(ex_date)每股股利合计/月末收盘", "dividend+panel"),
    "E16": ("div_yld120", "12m(365d) 滚动除息股利合计/月末收盘", "dividend+panel"),
    "E17": ("fcst_sign120", "120d Σsign(预告中值；缺失按类型 预增/扭亏=+1、预亏/首亏=-1)，无填 0", "forecast"),
    "E18": ("expr_cnt120", "120d 快报次数（无填 0）", "express"),
    "E19": ("hb_ann20", "20d 增持公告数(IN 方向，无填 0)", "stk_holdertrade"),
    "E20": ("float_press", "已公告未来 120d 解禁股数(万股)*月末收盘/流通市值(万元->元)", "share_float+daily_basic"),
}

results = []
for fid in col_names:
    name, formula, source = META[fid]
    t_start = time.time()
    fac = build_frame(fid)
    fac.write_parquet(os.path.join(OUT, f"{fid}.parquet"))
    res = evaluate_factor(fac, panel, CFG)
    ic_mean = res["ic_mean"]
    ic_std = res["ic_std"]
    n = res["n_dates"]
    t_val = ic_mean / ic_std * (n ** 0.5) if ic_std > 0 else float("nan")
    cov_med, cov_med_active = coverage_median(fac)
    ic15 = res["ic_by_year"].get(2015)
    mono = res["monotonicity"]

    c1 = abs(t_val) >= 2.0
    c2 = (mono == mono) and (mono * ic_mean > 0) and abs(mono) >= 0.3
    c3 = not (ic15 is not None and ic15 * ic_mean < 0 and abs(ic15) > 0.03)
    c4 = cov_med >= 0.5 * POOL_MEDIAN
    survived = bool(c1 and c2 and c3 and c4)

    meta = {
        "factor_id": fid, "name": name, "formula": formula, "source": source,
        "fill_policy": "无事件填 0" if fid in ZEROFILL else "无事件为 null（不入因子帧）",
        "n_rows": fac.height,
        "t_value": t_val,
        "coverage_median_symbols": cov_med,
        "coverage_median_active_months": cov_med_active,
        "pool_median_symbols": POOL_MEDIAN,
        "criteria": {"c1_abs_t>=2": bool(c1), "c2_mono_consistent>=0.3": bool(c2),
                     "c3_2015_non_disaster": bool(c3), "c4_coverage>=50%pool": bool(c4)},
        "survived_prelim": survived,
        "eval": res,
    }
    with open(os.path.join(OUT, f"{fid}.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, default=str, indent=1)
    results.append(meta)
    log(f"{fid} {name}: ic={ic_mean:+.4f} t={t_val:+.2f} mono={mono:+.2f} "
        f"cov={cov_med:.0f}/{POOL_MEDIAN:.0f} 存活={survived} ({time.time()-t_start:.1f}s)")
with open(os.path.join(OUT, "batch_summary.json"), "w", encoding="utf-8") as fh:
    json.dump({"event_stats": EVENT_STATS, "pool_median": POOL_MEDIAN,
               "n_signal_dates": len(me_dates),
               "first_last_signal": [str(me_dates[0]), str(me_dates[-1])],
               "results": [{k: v for k, v in m.items() if k != "eval"} for m in results]},
              fh, ensure_ascii=False, default=str, indent=1)
log("全部完成")
