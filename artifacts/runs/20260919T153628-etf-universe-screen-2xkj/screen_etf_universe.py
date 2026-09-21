# -*- coding: utf-8 -*-
"""ETF 宇宙扩展筛查：纯数据质量画像（描述性，不含任何策略/绩效计算）。

输入（只读）:
  data/processed/etf-daily-20260919/daily_2015_2024.parquet  (标准化 ETF 日线)
  data/raw/tushare/fund_adj/20260917-r1/chunk_*.csv          (fund_adj 因子)

输出（全部写入 run 目录 outputs/）:
  etf_universe_screen.parquet / .csv
  jump_events_gt6pct.csv
  summary.json (供 delivery report 使用)

纪律: 2025-01-01 及以后冻结，断言数据集 2025+ 零行；不计算收益率序列/动量/
绩效指标，只用 close/preclose 单日跳变与 preclose/prev_close 参照差做画像。
"""
import hashlib
import json
import os
import sys
import time
from datetime import date

import polars as pl

BASE = r"D:/量化"
DATA_DIR = os.path.join(BASE, "data", "processed", "etf-daily-20260919")
ADJ_DIR = os.path.join(BASE, "data", "raw", "tushare", "fund_adj", "20260917-r1")
RUN_DIR = sys.argv[1]
OUT_DIR = os.path.join(RUN_DIR, "outputs")

T_START = time.time()

# ---------------------------------------------------------------- 常量与口径
JUMP_THR = 0.06          # >6% 跳变事件阈值 (close/preclose - 1)
SPLIT_JUMP_THR = 0.50    # >50% 量级跳变 -> split-class 标记
SPLIT_FACTOR_THR = 0.15  # 因子比偏离 >15% -> 拆分合并型, 否则分红型
PRECLOSE_DEFECT_THR = 0.02  # preclose/prev_close 参照差 >2% 且因子无跳变 -> 无因子缺口缺陷
COV_THR = 0.95           # 双窗覆盖率阈值
LIQ_MEDIAN_THR = 2.0e7   # 中位数成交额 <2000 万元单独标记
DEV_WIN = (date(2015, 1, 1), date(2020, 12, 31))
VAL_WIN = (date(2021, 1, 1), date(2024, 12, 31))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 1. 读取日线
daily = pl.read_parquet(os.path.join(DATA_DIR, "daily_2015_2024.parquet"))
n_rows = daily.height
n_symbols = daily["symbol"].n_unique()

# 冻结区断言（必须通过，否则中止）
rows_2025 = daily.filter(pl.col("date") >= pl.date(2025, 1, 1)).height
rows_pre2015 = daily.filter(pl.col("date") < pl.date(2015, 1, 1)).height
assert rows_2025 == 0, f"2025+ 冻结区出现 {rows_2025} 行"
assert rows_pre2015 == 0, f"2015 前出现 {rows_pre2015} 行"
assert daily["date"].max() <= date(2024, 12, 31)
dup = daily.group_by(["symbol", "date"]).len().filter(pl.col("len") > 1).height
assert dup == 0, f"重复键 {dup} 组"

# ---------------------------------------------------------------- 2. 读取因子
adj_files = sorted(
    os.path.join(ADJ_DIR, f) for f in os.listdir(ADJ_DIR) if f.endswith(".csv")
)
def _read_adj_csv(p: str) -> pl.DataFrame:
    df = pl.read_csv(p, infer_schema_length=0)
    df.columns = ["ts_code", "trade_date", "adj_factor"]  # 位置对齐, 规避个别文件表头带 \r
    return df

adj = pl.concat(
    [_read_adj_csv(p) for p in adj_files], how="vertical"
).with_columns(
    pl.col("adj_factor").cast(pl.Float64),
    pl.col("trade_date").cast(pl.Utf8),
)
adj = adj.with_columns(
    pl.col("trade_date").str.to_date("%Y%m%d", strict=True).alias("date"),
    (
        pl.col("ts_code").str.split(".").list.get(1).str.to_lowercase()
        + "."
        + pl.col("ts_code").str.split(".").list.get(0)
    ).alias("symbol"),
).select(["symbol", "date", "adj_factor"])
adj = adj.sort(["symbol", "date"]).with_columns(
    prev_factor=pl.col("adj_factor").shift(1).over("symbol")
)
adj = adj.with_columns(
    factor_ratio=pl.when(pl.col("prev_factor") > 0)
    .then(pl.col("adj_factor") / pl.col("prev_factor"))
    .otherwise(None)
)

# ---------------------------------------------------------------- 3. 并集交易日历
cal = daily.select(pl.col("date").alias("cal_date")).unique().sort("cal_date")
cal = cal.with_row_index("cal_idx")
cal_dev = cal.filter(
    (pl.col("cal_date") >= DEV_WIN[0]) & (pl.col("cal_date") <= DEV_WIN[1])
)
cal_val = cal.filter(
    (pl.col("cal_date") >= VAL_WIN[0]) & (pl.col("cal_date") <= VAL_WIN[1])
)
dev_days = cal_dev.height
val_days = cal_val.height

# ---------------------------------------------------------------- 4. 逐行画像
d = daily.sort(["symbol", "date"]).with_columns(
    prev_close=pl.col("close").shift(1).over("symbol"),
    prev_date=pl.col("date").shift(1).over("symbol"),
    jump=pl.col("close") / pl.col("preclose") - 1.0,
    holder_jump=pl.col("close") / pl.col("close").shift(1).over("symbol") - 1.0,
    preclose_ref_diff=pl.when(pl.col("preclose") > 0).then(
        pl.col("preclose")
        / pl.col("close").shift(1).over("symbol")
        - 1.0
    ).otherwise(None),
)
# 日历缺口: 并集日历中 prev_date 与 date 之间的交易日数
d = d.join(
    cal.rename({"cal_date": "prev_date", "cal_idx": "prev_idx"}),
    on="prev_date",
    how="left",
)
d = d.join(
    cal.rename({"cal_date": "date", "cal_idx": "cur_idx"}), on="date", how="left"
)
d = d.with_columns(
    gap_cal=pl.when(pl.col("prev_idx").is_not_null() & pl.col("cur_idx").is_not_null())
    .then(pl.col("cur_idx") - pl.col("prev_idx") - 1)
    .otherwise(None)
)
# 因子连接
d = d.join(
    adj.select(["symbol", "date", "adj_factor", "factor_ratio"]),
    on=["symbol", "date"],
    how="left",
)
d = d.with_columns(
    factor_jumped=pl.col("factor_ratio").is_not_null()
    & ((pl.col("factor_ratio") - 1.0).abs() > 1e-6)
)

# 事件分类（按优先级）
d = d.with_columns(
    preclose_defect=(
        (pl.col("preclose_ref_diff").abs() > PRECLOSE_DEFECT_THR)
        & ~pl.col("factor_jumped")
    )
)
d = d.with_columns(
    category=pl.when(pl.col("factor_jumped") & ((pl.col("factor_ratio").abs() - 1.0).abs() > SPLIT_FACTOR_THR))
    .then(pl.lit("split_merge"))
    .when(pl.col("factor_jumped"))
    .then(pl.lit("dividend"))
    .when(pl.col("preclose_defect"))
    .then(pl.lit("no_factor_gap_defect"))
    .when(pl.col("gap_cal") > 0)
    .then(pl.lit("halt_resume"))
    .otherwise(pl.lit("normal_move"))
)

events = d.filter(
    (pl.col("holder_jump").abs() > JUMP_THR) | (pl.col("jump").abs() > JUMP_THR)
).sort(["symbol", "date"])
events_out = events.select(
    [
        "symbol",
        "date",
        pl.col("close").round(4),
        pl.col("preclose").round(4),
        pl.col("prev_close").round(4),
        pl.col("holder_jump").round(6).alias("close_over_prev_close_minus_1"),
        pl.col("jump").round(6).alias("close_over_preclose_minus_1"),
        pl.col("preclose_ref_diff").round(6).alias("preclose_over_prev_close_minus_1"),
        pl.col("factor_ratio").round(8),
        pl.col("gap_cal"),
        "category",
    ]
)
cat_cn = {
    "split_merge": "拆分合并型",
    "dividend": "分红型",
    "no_factor_gap_defect": "无因子缺口缺陷",
    "halt_resume": "停牌复牌型",
    "normal_move": "普通大幅波动",
}
events_out = events_out.with_columns(
    pl.col("category").replace_strict(cat_cn).alias("分类")
).drop("category")

# ---------------------------------------------------------------- 5. 逐标的汇总
per_symbol_events = events.group_by("symbol").agg(
    pl.len().alias("n_events_gt6pct"),
    (pl.col("holder_jump").abs() > SPLIT_JUMP_THR).any().alias("split_class_flag"),
    pl.col("holder_jump").abs().max().alias("max_abs_jump"),
    (pl.col("category") == "split_merge").sum().alias("n_split_merge"),
    (pl.col("category") == "dividend").sum().alias("n_dividend"),
    (pl.col("category") == "halt_resume").sum().alias("n_halt_resume"),
    (pl.col("category") == "no_factor_gap_defect").sum().alias("n_no_factor_defect"),
    (pl.col("category") == "normal_move").sum().alias("n_normal_move"),
)
per_symbol_events = per_symbol_events.with_columns(
    has_split_merge_event=pl.col("n_split_merge") > 0
)

# 无因子缺口缺陷日: preclose 参照差 >2% 且因子无跳变（含因子缺失行，保守计入）
defect_days = (
    d.filter(pl.col("preclose_defect"))
    .group_by("symbol")
    .agg(
        pl.len().alias("n_unmodeled_defect_days"),
        pl.col("factor_ratio").is_null().sum().alias("n_defect_factor_null"),
        pl.col("date").min().alias("defect_first_date"),
        pl.col("date").max().alias("defect_last_date"),
    )
)
defect_detail = (
    d.filter(pl.col("preclose_defect"))
    .select(
        [
            "symbol",
            "date",
            pl.col("preclose_ref_diff").round(6).alias("preclose_over_prev_close_minus_1"),
            pl.col("factor_ratio"),
            pl.col("factor_ratio").is_null().alias("factor_missing_that_day"),
            pl.col("gap_cal"),
        ]
    )
    .sort(["symbol", "date"])
)

# 覆盖率
cov = (
    daily.with_columns(
        pl.when(pl.col("date") <= DEV_WIN[1])
        .then(pl.lit("dev"))
        .otherwise(pl.lit("val"))
        .alias("window")
    )
    .group_by(["symbol", "window"])
    .agg(pl.len().alias("rows_in_win"), pl.col("date").n_unique().alias("dates_in_win"))
    .pivot(on="window", index="symbol", values=["rows_in_win", "dates_in_win"])
)
cov = cov.with_columns(
    pl.col("dates_in_win_dev").fill_null(0),
    pl.col("dates_in_win_val").fill_null(0),
)
cov = cov.with_columns(
    dev_cov=pl.col("dates_in_win_dev") / dev_days,
    val_cov=pl.col("dates_in_win_val") / val_days,
)

# 流动性
liq = daily.group_by("symbol").agg(
    pl.col("amount").median().alias("amount_median"),
    pl.col("amount").quantile(0.25).alias("amount_p25"),
)
p25_of_medians = liq["amount_median"].quantile(0.25)
liq = liq.with_columns(
    amount_median_pct_rank=pl.col("amount_median").rank("average") / n_symbols * 100.0
)

# 因子质量
factor_q = (
    daily.join(adj.select(["symbol", "date", "adj_factor"]), on=["symbol", "date"], how="left")
    .group_by("symbol")
    .agg(pl.col("adj_factor").is_null().sum().alias("factor_missing_rows"))
)
factor_q = factor_q.with_columns(
    factor_fully_missing=pl.col("factor_missing_rows") == n_rows  # 占位，后面按各自行数重算
)
# 正确口径: 缺失行数 == 该标的日线行数
factor_q = factor_q.join(daily.group_by("symbol").agg(pl.len().alias("n_rows_sym")), on="symbol")
factor_q = factor_q.with_columns(
    factor_fully_missing=pl.col("factor_missing_rows") >= pl.col("n_rows_sym")
).drop("n_rows_sym")

# 汇总基表
base = daily.group_by("symbol").agg(
    pl.col("date").min().alias("first_date"),
    pl.col("date").max().alias("last_date"),
    pl.len().alias("n_rows"),
)

pool = pl.read_parquet(os.path.join(DATA_DIR, "pool.parquet")).select(
    ["symbol", "name", "asset_class", "list_date", "delist_date", "status"]
)

screen = (
    base.join(pool, on="symbol", how="left")
    .join(cov.select(["symbol", "dev_cov", "val_cov", "dates_in_win_dev", "dates_in_win_val"]), on="symbol", how="left")
    .join(liq, on="symbol", how="left")
    .join(per_symbol_events, on="symbol", how="left")
    .join(defect_days, on="symbol", how="left")
    .join(factor_q, on="symbol", how="left")
)
screen = screen.with_columns(
    [
        pl.col("n_events_gt6pct").fill_null(0),
        pl.col("split_class_flag").fill_null(False),
        pl.col("has_split_merge_event").fill_null(False),
        pl.col("max_abs_jump").fill_null(0.0),
        pl.col("n_split_merge").fill_null(0),
        pl.col("n_dividend").fill_null(0),
        pl.col("n_halt_resume").fill_null(0),
        pl.col("n_no_factor_defect").fill_null(0),
        pl.col("n_normal_move").fill_null(0),
        pl.col("n_unmodeled_defect_days").fill_null(0),
        pl.col("n_defect_factor_null").fill_null(0),
        pl.col("factor_missing_rows").fill_null(0),
        pl.col("factor_fully_missing").fill_null(False),
    ]
)
screen = screen.with_columns(
    min_cov=pl.min_horizontal("dev_cov", "val_cov"),
)
screen = screen.with_columns(
    coverage_pass=(pl.col("dev_cov") >= COV_THR) & (pl.col("val_cov") >= COV_THR),
    liquidity_low_flag=pl.col("amount_median") < LIQ_MEDIAN_THR,
    liquidity_pass=pl.col("amount_median") >= p25_of_medians,
)
screen = screen.with_columns(
    screen_pass=pl.col("coverage_pass")
    & (pl.col("n_unmodeled_defect_days") == 0)
    & pl.col("liquidity_pass")
)

screen_out = screen.select(
    [
        "symbol", "name", "asset_class", "status", "list_date", "delist_date",
        "first_date", "last_date", "n_rows",
        "dates_in_win_dev", "dev_cov",
        "dates_in_win_val", "val_cov",
        "min_cov", "coverage_pass",
        "amount_median", "amount_p25", "amount_median_pct_rank",
        "liquidity_low_flag", "liquidity_pass",
        "n_events_gt6pct", "n_split_merge", "n_dividend", "n_halt_resume",
        "n_no_factor_defect", "n_normal_move",
        "max_abs_jump", "split_class_flag", "has_split_merge_event",
        "n_unmodeled_defect_days", "n_defect_factor_null",
        "defect_first_date", "defect_last_date",
        "factor_missing_rows", "factor_fully_missing",
        "screen_pass",
    ]
).sort("symbol")
screen_out = screen_out.with_columns(
    pl.col("dev_cov").round(6), pl.col("val_cov").round(6), pl.col("min_cov").round(6),
    pl.col("amount_median").round(2), pl.col("amount_p25").round(2),
    pl.col("amount_median_pct_rank").round(3),
    pl.col("max_abs_jump").round(6),
)

os.makedirs(OUT_DIR, exist_ok=True)
screen_out.write_parquet(os.path.join(OUT_DIR, "etf_universe_screen.parquet"))
screen_out.write_csv(os.path.join(OUT_DIR, "etf_universe_screen.csv"))
events_out.write_csv(os.path.join(OUT_DIR, "jump_events_gt6pct.csv"))
defect_detail.write_csv(os.path.join(OUT_DIR, "unmodeled_defect_days_preclose_gt2pct.csv"))

# ---------------------------------------------------------------- 6. 校验点: 已知案例
def case(symbol: str, dstr: str) -> dict:
    r = d.filter((pl.col("symbol") == symbol) & (pl.col("date") == pl.date(*map(int, dstr.split("-")))))
    if r.height == 0:
        return {"symbol": symbol, "date": dstr, "present": False}
    row = r.row(0, named=True)
    return {
        "symbol": symbol, "date": dstr, "present": True,
        "close": row["close"], "preclose": row["preclose"], "prev_close": row["prev_close"],
        "jump": row["jump"], "factor_ratio": row["factor_ratio"],
        "gap_cal": row["gap_cal"], "category": cat_cn.get(row["category"], row["category"]),
    }

known_cases = [
    case("sz.159919", "2019-01-14"),
    case("sh.510500", "2015-04-15"),
    case("sh.513100", "2022-01-14"),
    case("sh.513500", "2022-03-30"),
]

n_pass = screen_out.filter(pl.col("screen_pass")).height
n_defect_syms = screen_out.filter(pl.col("n_unmodeled_defect_days") > 0).height
n_split_syms = screen_out.filter(pl.col("split_class_flag")).height
n_low_liq = screen_out.filter(pl.col("liquidity_low_flag")).height
n_cov_fail = screen_out.filter(~pl.col("coverage_pass")).height
n_liq_fail = screen_out.filter(~pl.col("liquidity_pass")).height

cat_counts = events.group_by("category").agg(pl.len().alias("n")).sort("n", descending=True)
cat_counts_map = {r["category"]: r["n"] for r in cat_counts.iter_rows(named=True)}

# 未通过原因分布 (仅统计 screen_pass=False 的主因, 按优先级: 缺陷>覆盖>流动性)
fail_reason = screen_out.with_columns(
    reason=pl.when(pl.col("n_unmodeled_defect_days") > 0)
    .then(pl.lit("has_unmodeled_defect"))
    .when(~pl.col("coverage_pass"))
    .then(pl.lit("coverage_fail"))
    .when(~pl.col("liquidity_pass"))
    .then(pl.lit("liquidity_fail"))
    .otherwise(pl.lit("pass"))
)
reason_counts = {r["reason"]: r["n"] for r in fail_reason.group_by("reason").agg(pl.len().alias("n")).iter_rows(named=True)}

# 完全无因子标的 / 高缺失标的
fully_missing_list = screen_out.filter(pl.col("factor_fully_missing"))["symbol"].to_list()
partial_missing = screen_out.filter((pl.col("factor_missing_rows") > 0) & ~pl.col("factor_fully_missing"))
partial_missing_list = partial_missing.select(["symbol", "factor_missing_rows"]).to_dicts()

# 通过池资产类别分布
pass_class = screen_out.filter(pl.col("screen_pass")).group_by("asset_class").agg(pl.len().alias("n")).sort("n", descending=True)
pass_class_map = {r["asset_class"]: r["n"] for r in pass_class.iter_rows(named=True)}

# 缺陷标的清单 (全部)
defect_syms = screen_out.filter(pl.col("n_unmodeled_defect_days") > 0).select(
    ["symbol", "name", "n_unmodeled_defect_days", "n_defect_factor_null", "defect_first_date", "defect_last_date", "screen_pass"]
).sort("n_unmodeled_defect_days", descending=True)

# split-class 标记清单 (>50% 量级跳变 或 存在拆分合并型因子事件)
split_syms = screen_out.filter(pl.col("split_class_flag") | pl.col("has_split_merge_event")).select(
    ["symbol", "name", "max_abs_jump", "n_split_merge", "split_class_flag", "has_split_merge_event", "screen_pass"]
).sort("max_abs_jump", descending=True)

summary = {
    "run_dir": RUN_DIR,
    "t_elapsed_sec": round(time.time() - T_START, 1),
    "assertions": {
        "rows_2025_plus": rows_2025,
        "rows_before_2015": rows_pre2015,
        "date_max": str(daily["date"].max()),
        "date_min": str(daily["date"].min()),
        "duplicate_keys": dup,
        "total_rows": n_rows,
        "symbols": n_symbols,
    },
    "calendar": {
        "union_days_total": cal.height,
        "dev_days_2015_2020": dev_days,
        "val_days_2021_2024": val_days,
    },
    "coverage": {
        "threshold": COV_THR,
        "pass": int(n_symbols - n_cov_fail),
        "fail": int(n_cov_fail),
    },
    "liquidity": {
        "p25_of_median_amounts_yuan": round(p25_of_medians, 2),
        "median_below_20m_flag_count": int(n_low_liq),
        "fail_vs_p25": int(n_liq_fail),
    },
    "events_gt6pct": {
        "total": events.height,
        "by_category": {cat_cn.get(k, k): v for k, v in cat_counts_map.items()},
    },
    "defects": {
        "symbols_with_unmodeled_defect_days": int(n_defect_syms),
        "total_unmodeled_defect_days": int(screen_out["n_unmodeled_defect_days"].sum()),
        "list": defect_syms.to_dicts(),
    },
    "split_class": {
        "symbols": int(n_split_syms),
        "list": split_syms.to_dicts(),
    },
    "factor_quality": {
        "fully_missing": fully_missing_list,
        "partial_missing": partial_missing_list,
        "total_missing_rows": int(screen_out["factor_missing_rows"].sum()),
    },
    "screen": {
        "pass_count": int(n_pass),
        "pass_rate": round(n_pass / n_symbols, 4),
        "fail_reason_counts": reason_counts,
        "pass_by_asset_class": pass_class_map,
    },
    "known_cases": known_cases,
}

with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
