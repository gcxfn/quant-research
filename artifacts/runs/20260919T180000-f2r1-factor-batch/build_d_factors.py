# -*- coding: utf-8 -*-
"""F2-R1 D 族（财务 PIT，30 因子）构建与评估脚本。

预登记：docs/research/exp-20260919-factor-round-f2r1-prereg.md §3-D（公式冻结）。
PIT 契约：src/quant/factors/eval.py::pit_financial（f_ann_date > ann_date > 期末+90 天兜底，
修正稿（最新 ann_date）胜出）。数据只读；dev 窗 2015–2020 月频；signal_date ≤ 2024-12-31 断言。

口径（写入 family_report）：
- 累计值差分 = 单季（Q1 单季=累计；其余须存在上季累计行，缺失即 null）；
- 同比 = 本期(单季/比率) vs 去年同报期（比率类为差值，成长类为比值-1，分母≤0 置 null）；
- TTM = 本期累计 − 去年同期累计 + 去年年报累计；
- 三表合并因子的可见日 = 三表各自 coalesce(f_ann_date, ann_date) 的最大值（等三表全披露，保守）；
- fina_indicator 无 f_ann_date 列，PIT 取 ann_date（缺失行走期末+90 天兜底并计数）；
- 去重（修正稿胜出）：按 ann_date 升序取每 (ts_code, end_date) 末行，ann_date 缺失行不优先于有日期行。
"""

from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

import polars as pl

ROOT = Path("D:/量化")
sys.path.insert(0, str(ROOT / "src"))

from quant.factors.eval import (  # noqa: E402
    FREEZE_END,
    FactorEvalConfig,
    evaluate_factor,
    pit_financial,
)

OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/D_fund"
PANEL_PATH = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
TS = ROOT / "data/raw/tushare"

CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
DEV_START = pl.date(2015, 1, 1)
DEV_END = pl.date(2020, 12, 31)

S = pl.String
F = pl.Float64

log_lines: list[str] = []


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    log_lines.append(line)


# ---------------------------------------------------------------------------
# 读取与去重
# ---------------------------------------------------------------------------

def read_ds(datasets: list[str], cols: dict[str, object]) -> pl.DataFrame:
    """按 glob 读取一个或多个 tushare 逐股数据集，只取需要的列。"""
    pats = [str(TS / d / "*" / "chunk_*.csv") for d in datasets]
    try:
        df = pl.scan_csv(pats, schema_overrides=cols).select(list(cols)).collect()
        log(f"  scan_csv ok: {datasets}, {df.height} rows")
        return df
    except Exception as e:  # noqa: BLE001 — 个别文件列缺失时退化为逐文件对角拼接
        log(f"  scan_csv failed ({e!r:.140}); fallback per-file read")
    frames = []
    for pat in pats:
        for fp in sorted(glob.glob(pat)):
            try:
                raw = pl.read_csv(fp, infer_schema_length=0)
            except Exception:
                continue
            take = [c for c in cols if c in raw.columns]
            frames.append(
                raw.select(take).with_columns(
                    [pl.col(c).cast(dt, strict=False) for c, dt in cols.items() if c in take]
                )
            )
    df = pl.concat(frames, how="diagonal_relaxed")
    log(f"  fallback read: {datasets}, {df.height} rows")
    return df


def dedup_latest(df: pl.DataFrame, value_cols: list[str]) -> pl.DataFrame:
    """每 (ts_code, end_date) 保留 ann_date 最晚（修正稿胜出）；ann_date 缺失行不优先。"""
    keep = [c for c in ["ts_code", "ann_date", "f_ann_date", "end_date"] if c in df.columns]
    return (
        df.sort("ann_date", nulls_last=False, maintain_order=True)
        .group_by("ts_code", "end_date", maintain_order=True)
        .agg(pl.all().last())
        .select(keep + value_cols)
    )


def to_symbol(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.concat_str(
            pl.col("ts_code").str.split(".").list.last().str.to_lowercase(),
            pl.lit("."),
            pl.col("ts_code").str.split(".").list.first(),
        ).alias("symbol")
    )


def to_pkey(col: str) -> pl.Expr:
    """end_date(Date) -> Int 报告期键 yyyymmdd。"""
    d = pl.col(col)
    return (d.dt.year() * 10000 + d.dt.month() * 100 + d.dt.day()).cast(pl.Int64)


def with_keys(df: pl.DataFrame) -> pl.DataFrame:
    """报告期键：_j 本期、_j_ly 去年同期、_j_pq 上季、_j_fy 去年年报。"""
    y = pl.col("end_date").dt.year()
    m = pl.col("end_date").dt.month()
    return df.with_columns(
        to_pkey("end_date").alias("_j"),
        ((y - 1) * 10000 + m * 100 + pl.col("end_date").dt.day()).cast(pl.Int64).alias("_j_ly"),
        pl.when(m == 3).then((y - 1) * 10000 + 1231)
        .when(m == 6).then(y * 10000 + 331)
        .when(m == 9).then(y * 10000 + 630)
        .otherwise(y * 10000 + 930).cast(pl.Int64).alias("_j_pq"),
        ((y - 1) * 10000 + 1231).cast(pl.Int64).alias("_j_fy"),
    )


def standard_q(df: pl.DataFrame) -> pl.DataFrame:
    """标准季报期 + 冻结纪律：报告期止于 2020-12-31（dev 末信号之后披露的报告不可用，
    同时剔除原始数据中混入的 2025+/2026 报告期，杜绝任何冻结区消费）。"""
    return df.filter(
        pl.col("end_date").dt.month().is_in([3, 6, 9, 12])
        & (pl.col("end_date") == pl.col("end_date").dt.month_end())
        & (pl.col("end_date") <= pl.date(2020, 12, 31))
    )


def prep_for_pit(df: pl.DataFrame) -> pl.DataFrame:
    """pit_financial 要求 %Y%m%d 字符串日期；end_date 已是 Date 的转回，f_ann_date 缺则补 null。"""
    out = df.with_columns(pl.col("end_date").dt.to_string("%Y%m%d"))
    if "f_ann_date" not in out.columns:
        out = out.with_columns(pl.lit(None, dtype=S).alias("f_ann_date"))
    return out.select(["ts_code", "ann_date", "f_ann_date", "end_date"])


# ---------------------------------------------------------------------------
# 1) 面板、月末网格（= 评估池：trading、非 ST、剔板块、hist_depth>=60）
# ---------------------------------------------------------------------------
log("加载 v0 面板 …")
panel = pl.read_parquet(PANEL_PATH).select(
    "date", "symbol", "close", "preclose", "tradestatus", "isST")
panel = panel.with_columns(pl.col("tradestatus").cast(pl.Int64), pl.col("isST").cast(pl.Int64))
assert panel["date"].max() <= FREEZE_END, "面板冻结纪律破坏"

panel_raw_depth = panel.select("date", "symbol").sort("symbol", "date").with_columns(
    pl.int_range(pl.len()).over("symbol").alias("hist_depth")
)

me_dates = (
    panel.filter(pl.col("tradestatus") == 1)
    .select("date").unique()
    .with_columns(pl.col("date").dt.truncate("1mo").alias("_m"))
    .group_by("_m").agg(pl.col("date").max().alias("date"))
    .filter(pl.col("date").is_between(DEV_START, DEV_END))
    .sort("date")
)
n_me = me_dates.height

grid = (
    panel.join(me_dates, left_on="date", right_on="signal_date")
    .join(panel_raw_depth, on=["date", "symbol"])
    .filter(
        (pl.col("tradestatus") == 1)
        & (pl.col("isST") == 0)
        & ~pl.col("symbol").str.starts_with("sh.688")
        & ~pl.col("symbol").str.starts_with("bj.")
        & (pl.col("hist_depth") >= 60)
    )
    .select(pl.col("date").alias("signal_date"), "symbol")
    .unique()
)
POOL_BY_MONTH = grid.group_by("signal_date").len().sort("signal_date")
POOL_MEDIAN = float(POOL_BY_MONTH["len"].median())
log(f"月末网格：{n_me} 期 × 池中位 {POOL_MEDIAN:.0f} 只，共 {grid.height} 行")
assert n_me == 72 and grid.height > 0

# ---------------------------------------------------------------------------
# 2) fina_indicator：直读比率 + 差分衍生
# ---------------------------------------------------------------------------
log("读取 fina_indicator …")
FI_COLS = {
    "ts_code": S, "ann_date": S, "end_date": S,
    "roe": F, "roa": F, "grossprofit_margin": F, "netprofit_margin": F,
    "debt_to_assets": F, "currentratio": F, "eps": F, "bps": F,
    "or_yoy": F, "netprofit_yoy": F, "ocf_yoy": F, "ocfps": F,
    "extra_item": F, "profit_dedt": F,
}
fi = read_ds(["fina_indicator"], FI_COLS)
fi = fi.with_columns(pl.col("end_date").str.strip_chars().str.to_date("%Y%m%d", strict=False))
fi = standard_q(fi)
fi_dedup = dedup_latest(
    fi, [c for c in FI_COLS if c not in ("ts_code", "ann_date", "end_date")])
log(f"fina_indicator 报告期去重后 {fi_dedup.height} 行"
    f"（ann_date 缺失 {fi_dedup['ann_date'].null_count()} 行）")

# 去年同期 / 上季自连接（差值类衍生）
fi_k = fi_dedup.with_columns(to_pkey("end_date").alias("_j"))
ly = fi_k.select(["ts_code", "_j", "roe", "grossprofit_margin", "debt_to_assets"]).with_columns(
    (pl.col("_j") // 10000 - 1) * 10000 + pl.col("_j") % 10000
).rename({"_j": "_k", "roe": "roe_ly", "grossprofit_margin": "gm_ly", "debt_to_assets": "debt_ly"})
fi_k = fi_k.join(ly, left_on=["ts_code", "_j"], right_on=["ts_code", "_k"], how="left")

pq = fi_k.select(["ts_code", "_j", "eps"]).with_columns(
    pl.when(pl.col("_j") % 10000 == 331).then((pl.col("_j") // 10000 - 1) * 10000 + 1231)
    .when(pl.col("_j") % 10000 == 1231).then(pl.col("_j") - 301)
    .otherwise(pl.col("_j") - 300)
).rename({"_j": "_k", "eps": "eps_pq"})
fi_k = fi_k.join(pq, left_on=["ts_code", "_j"], right_on=["ts_code", "_k"], how="left")

fi_k = fi_k.with_columns(
    (pl.col("roe") - pl.col("roe_ly")).alias("roe_d"),
    (pl.col("grossprofit_margin") - pl.col("gm_ly")).alias("gm_d"),
    (pl.col("debt_to_assets") - pl.col("debt_ly")).alias("debt_d"),
    (pl.col("eps") - pl.col("eps_pq")).alias("eps_dq"),
)

FI_FACTORS = {
    "D01": "roe", "D02": "roa", "D03": "grossprofit_margin", "D04": "netprofit_margin",
    "D05": "debt_to_assets", "D06": "currentratio", "D09": "eps", "D10": "bps",
    "D11": "or_yoy", "D12": "netprofit_yoy", "D13": "roe_d", "D14": "gm_d",
    "D19": "ocf_yoy", "D24": "eps_dq", "D25": "debt_d", "D30": "ocfps",
}

# ---------------------------------------------------------------------------
# 3) 三表：单季/TTM/同比/合并比率
# ---------------------------------------------------------------------------
log("读取三表（income / balancesheet / cashflow）…")
INC_COLS = {
    "ts_code": S, "ann_date": S, "f_ann_date": S, "end_date": S, "report_type": S, "update_flag": S,
    "revenue": F, "oper_cost": F, "n_income_attr_p": F, "sell_exp": F, "admin_exp": F,
}
BS_COLS = {
    "ts_code": S, "ann_date": S, "f_ann_date": S, "end_date": S, "report_type": S, "update_flag": S,
    "total_assets": F, "total_hldr_eqy_exc_min_int": F, "intan_assets": F, "goodwill": F,
}
CF_COLS = {
    "ts_code": S, "ann_date": S, "f_ann_date": S, "end_date": S, "report_type": S, "update_flag": S,
    "n_cashflow_act": F,
}


def load_stmt(datasets: str, cols: dict) -> pl.DataFrame:
    df = read_ds([datasets], cols)
    df = df.filter(pl.col("report_type") == "1")
    df = df.with_columns(pl.col("end_date").str.strip_chars().str.to_date("%Y%m%d", strict=False))
    return standard_q(df)


inc_d = dedup_latest(load_stmt("income", INC_COLS),
                     ["revenue", "oper_cost", "n_income_attr_p", "sell_exp", "admin_exp"])
log(f"income 去重后 {inc_d.height} 行")
bs_d = dedup_latest(load_stmt("balancesheet", BS_COLS),
                    ["total_assets", "total_hldr_eqy_exc_min_int", "intan_assets", "goodwill"])
log(f"balancesheet 去重后 {bs_d.height} 行")
cf_d = dedup_latest(load_stmt("cashflow", CF_COLS), ["n_cashflow_act"])
log(f"cashflow 去重后 {cf_d.height} 行")

# --- income：单季差分 + 同比 + TTM ---
ik = with_keys(inc_d)
pq_inc = ik.select(["ts_code", "_j", "revenue", "n_income_attr_p"]).rename(
    {"_j": "_k", "revenue": "rev_pq", "n_income_attr_p": "np_pq"})
ik = ik.join(pq_inc, left_on=["ts_code", "_j_pq"], right_on=["ts_code", "_k"], how="left")
ly_inc = ik.select(["ts_code", "_j", "revenue", "n_income_attr_p", "oper_cost"]).rename(
    {"_j": "_k", "revenue": "rev_ly", "n_income_attr_p": "np_ly", "oper_cost": "cost_ly"})
ik = ik.join(ly_inc, left_on=["ts_code", "_j_ly"], right_on=["ts_code", "_k"], how="left")
fy_inc = ik.select(["ts_code", "_j", "revenue", "n_income_attr_p", "oper_cost"]).rename(
    {"_j": "_k", "revenue": "rev_fy", "n_income_attr_p": "np_fy", "oper_cost": "cost_fy"})
ik = ik.join(fy_inc, left_on=["ts_code", "_j_fy"], right_on=["ts_code", "_k"], how="left")
# 单季（累计差分；Q1 单季=累计；上季行缺失即 null）
sq_rev = pl.when(pl.col("end_date").dt.month() == 3).then(pl.col("revenue")).otherwise(
    pl.col("revenue") - pl.col("rev_pq"))
sq_np = pl.when(pl.col("end_date").dt.month() == 3).then(pl.col("n_income_attr_p")).otherwise(
    pl.col("n_income_attr_p") - pl.col("np_pq"))
ik = ik.with_columns(sq_rev.alias("sq_rev"), sq_np.alias("sq_np"))
# 单季同比（去年同季单季，分母≤0 置 null）
sqy = ik.select(["ts_code", "_j", "sq_rev", "sq_np"]).with_columns(
    (pl.col("_j") // 10000 - 1) * 10000 + pl.col("_j") % 10000
).rename({"_j": "_k", "sq_rev": "sq_rev_ly", "sq_np": "sq_np_ly"})
ik = ik.join(sqy, left_on=["ts_code", "_j"], right_on=["ts_code", "_k"], how="left")
# TTM = 本期累计 − 去年同期累计 + 去年年报
ik = ik.with_columns(
    (pl.col("n_income_attr_p") - pl.col("np_ly") + pl.col("np_fy")).alias("ttm_np"),
    (pl.col("revenue") - pl.col("rev_ly") + pl.col("rev_fy")).alias("ttm_rev"),
    (pl.col("oper_cost") - pl.col("cost_ly") + pl.col("cost_fy")).alias("ttm_cost"),
)

# --- 合并三表（含 fina 的 extra_item 供 D29）；可见日 = 三表 coalesce(f_ann, ann) 最大值 ---
m = (
    ik.select(["ts_code", "ann_date", "f_ann_date", "end_date", "revenue", "oper_cost",
               "n_income_attr_p", "sell_exp", "admin_exp", "sq_rev", "sq_np",
               "sq_rev_ly", "sq_np_ly", "ttm_np", "ttm_rev", "ttm_cost"])
    .join(bs_d.select(["ts_code", "end_date", "ann_date", "f_ann_date", "total_assets",
                       "total_hldr_eqy_exc_min_int", "intan_assets", "goodwill"]),
          on=["ts_code", "end_date"], how="left", suffix="_bs")
    .join(cf_d.select(["ts_code", "end_date", "ann_date", "f_ann_date", "n_cashflow_act"]),
          on=["ts_code", "end_date"], how="left", suffix="_cf")
    .join(fi_dedup.select(["ts_code", "end_date", "extra_item"]),
          on=["ts_code", "end_date"], how="left")
)
m = m.with_columns(
    pl.max_horizontal(
        pl.coalesce("f_ann_date", "ann_date"),
        pl.coalesce("f_ann_date_bs", "ann_date_bs"),
        pl.coalesce("f_ann_date_cf", "ann_date_cf"),
    ).alias("ann_date"),
).with_columns(pl.lit(None, dtype=S).alias("f_ann_date"))

eq = pl.col("total_hldr_eqy_exc_min_int")
q = pl.col("end_date").dt.month() // 3
m = m.with_columns(
    pl.when(pl.col("revenue") > 0).then(pl.col("n_cashflow_act") / pl.col("revenue")).alias("ocf_opinc"),
    pl.when(pl.col("total_assets") > 0).then(pl.col("n_cashflow_act") / pl.col("total_assets")).alias("ocf_roa"),
    pl.when(pl.col("total_assets") > 0)
      .then((pl.col("n_income_attr_p") - pl.col("n_cashflow_act")) / pl.col("total_assets")).alias("accruals"),
    pl.when(pl.col("total_assets") > 0)
      .then(pl.col("revenue") * (4.0 / q.cast(F)) / pl.col("total_assets")).alias("asset_turn"),
    pl.when(pl.col("sq_rev_ly") > 0).then(pl.col("sq_rev") / pl.col("sq_rev_ly") - 1).alias("rev_q_yoy"),
    pl.when(pl.col("sq_np_ly") > 0).then(pl.col("sq_np") / pl.col("sq_np_ly") - 1).alias("np_q_yoy"),
    pl.when(eq > 0).then(pl.col("ttm_np") / eq).alias("roe_ttm"),
    pl.when(pl.col("ttm_rev") > 0)
      .then((pl.col("ttm_rev") - pl.col("ttm_cost")) / pl.col("ttm_rev")).alias("gm_ttm"),
    pl.when(eq > 0).then(pl.col("total_assets") / eq).alias("eq_mult"),
    pl.when(eq > 0)
      .then((pl.col("total_assets") - pl.fill_null(pl.col("intan_assets"), 0.0)
             - pl.fill_null(pl.col("goodwill"), 0.0)) / eq).alias("tangible"),
    pl.when(pl.col("revenue") > 0)
      .then((pl.fill_null(pl.col("sell_exp"), 0.0) + pl.fill_null(pl.col("admin_exp"), 0.0))
            / pl.col("revenue")).alias("sga_r"),
    pl.when(pl.col("n_income_attr_p").abs() > 0)
      .then(pl.col("extra_item") / pl.col("n_income_attr_p").abs()).alias("nonrecc"),
)

MERGED_FACTORS = {
    "D07": "ocf_opinc", "D08": "ocf_roa", "D15": "accruals", "D18": "asset_turn",
    "D20": "rev_q_yoy", "D21": "np_q_yoy", "D22": "roe_ttm", "D23": "gm_ttm",
    "D26": "eq_mult", "D27": "tangible", "D28": "sga_r", "D29": "nonrecc",
}

# ---------------------------------------------------------------------------
# 4) PIT 对齐（必经 pit_financial）+ 月末 as-of 快照
# ---------------------------------------------------------------------------
log("pit_financial 对齐 …")
fi_pit = pit_financial(prep_for_pit(fi_dedup))
m_pit = pit_financial(prep_for_pit(m.select(
    ["ts_code", "ann_date", "f_ann_date", "end_date"])))
log(f"fina PIT 行 {fi_pit.height}（90 天兜底 {fi_pit['used_90d_fallback'].mean():.4f}）；"
    f"三表合并 PIT 行 {m_pit.height}（兜底 {m_pit['used_90d_fallback'].mean():.4f}）")

fi_vals = to_symbol(fi_k)   # 含衍生列
m_vals = to_symbol(m)


def monthend_factor(pit: pl.DataFrame, vals: pl.DataFrame, col: str) -> pl.DataFrame:
    """PIT 行 → 月末 as-of 快照 → (symbol, signal_date, value)。"""
    b = (
        pit.join(vals.select(["symbol", "end_date", col]), on=["symbol", "end_date"], how="left")
        .select("symbol", "signal_date", "end_date", col)
        .drop_nulls(col)
        .sort("symbol", "signal_date", "end_date")
        .unique(subset=["symbol", "signal_date"], keep="last")
        .sort("signal_date")
    )
    out = (
        grid.sort("signal_date")
        .join_asof(b, on="signal_date", by="symbol", strategy="backward")
        .select("symbol", "signal_date", pl.col(col).alias("value"))
        .drop_nulls("value")
    )
    assert out["signal_date"].max() is None or out["signal_date"].max() <= FREEZE_END
    return out


FACTOR_COL = dict(FI_FACTORS)
FACTOR_COL.update(MERGED_FACTORS)
FI_IDS = set(FI_FACTORS)
frames: dict[str, pl.DataFrame] = {}
for fid, col in FACTOR_COL.items():
    src_vals = fi_vals if fid in FI_IDS else m_vals
    src_pit = fi_pit if fid in FI_IDS else m_pit
    frames[fid] = monthend_factor(src_pit, src_vals, col)
    log(f"  {fid} ({col}): {frames[fid].height} 行")

# ---------------------------------------------------------------------------
# 5) 复合因子 D16/D17（横截面 rank 和）
# ---------------------------------------------------------------------------
log("构建 D16/D17 复合因子 …")
db = pl.scan_csv(str(TS / "daily_basic" / "*" / "chunk_*.csv"),
                 schema_overrides={"ts_code": S, "trade_date": S, "pe_ttm": F})
me_str = me_dates.with_columns(pl.col("date").dt.to_string("%Y%m%d").alias("d"))["d"].to_list()
db_me = (
    db.filter(pl.col("trade_date").is_in(me_str))
    .select("ts_code", "trade_date", "pe_ttm")
    .collect()
    .with_columns(
        pl.concat_str(
            pl.col("ts_code").str.split(".").list.last().str.to_lowercase(),
            pl.lit("."),
            pl.col("ts_code").str.split(".").list.first(),
        ).alias("symbol"),
        pl.col("trade_date").str.to_date("%Y%m%d"),
    )
    .select("symbol", pl.col("trade_date").alias("signal_date"), "pe_ttm")
    .with_columns(pl.when(pl.col("pe_ttm") > 0).then(1.0 / pl.col("pe_ttm")).alias("ep"))
    .select("symbol", "signal_date", "ep")
    .drop_nulls("ep")
)
log(f"daily_basic 月末快照 {db_me.height} 行")

frames["D16"] = (
    db_me.join(frames["D01"], on=["symbol", "signal_date"], how="inner")
    .with_columns(
        (pl.col("ep").rank(method="average").over("signal_date")
         + pl.col("value").rank(method="average").over("signal_date")).cast(pl.Float64).alias("value")
    )
    .select("symbol", "signal_date", "value")
)
frames["D17"] = (
    frames["D07"].join(frames["D05"], on=["symbol", "signal_date"], how="inner", suffix="_debt")
    .with_columns(
        (pl.col("value").rank(method="average").over("signal_date")
         - pl.col("value_debt").rank(method="average").over("signal_date")).cast(pl.Float64).alias("value")
    )
    .select("symbol", "signal_date", "value")
)
for fid in ("D16", "D17"):
    log(f"  {fid}: {frames[fid].height} 行")

# ---------------------------------------------------------------------------
# 6) 评估 + 逐因子落盘
# ---------------------------------------------------------------------------
log("逐因子评估 …")
NAMES = {
    "D01": "roe", "D02": "roa", "D03": "gm", "D04": "nm", "D05": "debt_assets", "D06": "cur_ratio",
    "D07": "ocf_opinc", "D08": "ocf_roa", "D09": "eps", "D10": "bps", "D11": "rev_yoy",
    "D12": "np_yoy", "D13": "roe_d", "D14": "gm_d", "D15": "accruals", "D16": "ep_roe",
    "D17": "quality", "D18": "asset_turn", "D19": "ocf_yoy", "D20": "rev_q_yoy", "D21": "np_q_yoy",
    "D22": "roe_ttm", "D23": "gm_ttm", "D24": "eps_dq", "D25": "debt_d", "D26": "eq_mult",
    "D27": "tangible", "D28": "sga_r", "D29": "nonrecc", "D30": "ocf_ps",
}
SOURCE = {f: "fina_indicator" for f in FI_FACTORS}
SOURCE.update({f: "三表合并(income+bs+cf)" for f in MERGED_FACTORS})
SOURCE.update({"D16": "daily_basic(ep)+fina(roe)", "D17": "复合(D07+D05)"})

results: dict[str, dict] = {}
for fid in sorted(frames):
    f = frames[fid]
    assert f["signal_date"].max() <= FREEZE_END, f"{fid} 冻结破坏"
    n_by_date = f.group_by("signal_date").len().sort("signal_date")
    cov_all = float(n_by_date["len"].mean())
    cov_2015h1 = float(n_by_date.filter(pl.col("signal_date") < pl.date(2015, 7, 1))["len"].mean() or 0)
    try:
        res = evaluate_factor(f, panel, CFG)
        status = "ok"
    except Exception as e:  # noqa: BLE001 — fail 如实记录
        res, status = {"error": repr(e)}, "fail"
        log(f"  {fid} 评估失败：{e!r:.160}")

    out = {"factor_id": fid, "name": NAMES[fid], "source": SOURCE[fid], "status": status,
           "n_rows": f.height, "n_symbols": f["symbol"].n_unique(),
           "signal_min": str(f["signal_date"].min()), "signal_max": str(f["signal_date"].max()),
           "coverage_mean": cov_all, "coverage_2015h1_mean": cov_2015h1,
           "pool_median": POOL_MEDIAN, "result": res}
    if status == "ok":
        t_stat = res["icir"] * (res["n_dates"] ** 0.5) if res["ic_std"] > 0 else float("nan")
        ic15 = res["ic_by_year"].get(2015)
        out["t_stat"] = t_stat
        out["survival"] = {
            "t_ge_2": bool(abs(t_stat) >= 2.0),
            "mono": bool(abs(res["monotonicity"]) >= 0.3
                         and (res["monotonicity"] > 0) == (res["ic_mean"] > 0)),
            "y2015_ok": bool(ic15 is not None
                             and not ((ic15 < 0) == (res["ic_mean"] > 0) and abs(ic15) > 0.03)),
            "coverage_ok": bool(cov_all >= 0.5 * POOL_MEDIAN),
            "ic_2015": ic15,
        }
        out["survived_all"] = all(out["survival"][k] for k in
                                  ("t_ge_2", "mono", "y2015_ok", "coverage_ok"))
    results[fid] = out
    f.write_parquet(OUT / f"{fid}.parquet")
    (OUT / f"{fid}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    log(f"  {fid} done: ic={res.get('ic_mean')}, t={out.get('t_stat')}, "
        f"survived={out.get('survived_all')}")

# ---------------------------------------------------------------------------
# 7) 族级 PIT 披露统计
# ---------------------------------------------------------------------------
log("族级 PIT 统计 …")


def cov_series(pit: pl.DataFrame, vals: pl.DataFrame, col: str) -> pl.DataFrame:
    b = (pit.join(vals.select(["symbol", "end_date", col]), on=["symbol", "end_date"], how="left")
         .select("symbol", "signal_date", col).drop_nulls(col)
         .sort("symbol", "signal_date").unique(subset=["symbol", "signal_date"], keep="last")
         .sort("signal_date"))
    return (grid.sort("signal_date")
            .join_asof(b, on="signal_date", by="symbol", strategy="backward")
            .group_by("signal_date").agg(pl.col(col).is_not_null().mean().alias("cov"))
            .sort("signal_date"))


cov_fi = cov_series(fi_pit, fi_vals, "roe")
cov_3s = cov_series(m_pit, m_vals, "ocf_opinc")
pit_stats = {
    "pool_median": POOL_MEDIAN,
    "pool_by_month": POOL_BY_MONTH.with_columns(
        pl.col("signal_date").dt.to_string("%Y-%m-%d")).to_dicts(),
    "fina_pit_rows": fi_pit.height,
    "fina_90d_fallback_share": float(fi_pit["used_90d_fallback"].mean()),
    "fina_ann_null_rows": int(fi_dedup["ann_date"].null_count()),
    "fina_f_ann_date_note": "fina_indicator 无 f_ann_date 列，PIT 取 ann_date",
    "threestmt_pit_rows": m_pit.height,
    "threestmt_90d_fallback_share": float(m_pit["used_90d_fallback"].mean()),
    "threestmt_visibility_note": "可见日 = max(三表各自 coalesce(f_ann_date, ann_date))，等三表全披露",
    "fina_coverage_by_month_mean": float(cov_fi["cov"].mean()),
    "fina_coverage_2015H1_mean": float(cov_fi.filter(pl.col("signal_date") < pl.date(2015, 7, 1))["cov"].mean()),
    "fina_coverage_2015H2_2020_mean": float(
        cov_fi.filter(pl.col("signal_date") >= pl.date(2015, 7, 1))["cov"].mean()),
    "threestmt_coverage_by_month_mean": float(cov_3s["cov"].mean()),
    "threestmt_coverage_2015H1_mean": float(
        cov_3s.filter(pl.col("signal_date") < pl.date(2015, 7, 1))["cov"].mean()),
    "threestmt_coverage_2015H2_2020_mean": float(
        cov_3s.filter(pl.col("signal_date") >= pl.date(2015, 7, 1))["cov"].mean()),
    "fina_coverage_series": cov_fi.with_columns(
        pl.col("signal_date").dt.to_string("%Y-%m-%d")).to_dicts(),
    "threestmt_coverage_series": cov_3s.with_columns(
        pl.col("signal_date").dt.to_string("%Y-%m-%d")).to_dicts(),
}
(OUT / "D_family_pit_stats.json").write_text(
    json.dumps(pit_stats, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
(OUT / "D_family_results.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
(OUT / "build_log.txt").write_text("\n".join(log_lines), encoding="utf-8")
log("全部完成")
