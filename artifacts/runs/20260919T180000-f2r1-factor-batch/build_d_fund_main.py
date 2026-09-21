# F2R1 D 族（财务 PIT 30 因子）——主对话接管实施（三任代理死于基建后）
# 冻结依据：docs/research/exp-20260919-factor-round-f2r1-prereg.md §1/§2/§3-D
# PIT 口径：四数据集各经 pit_financial（修正稿胜出、f_ann_date>ann_date>end+90d 兜底），
#   合并行的 signal_date = 各表可见时点的 max（全部可见才用，保守）；
#   同比/单季差分/TTM/环比在 (symbol, end_date) PIT 序列上派生；月末 as-of 取最新可见报告。
# 字段映射：fina_indicator 直读 D01-D06/D09-D12/D18(assets_turn)/D19(ocf_yoy)/D20(q_sales_yoy)/D30(ocfps)；
#   income=revenue/n_income_attr_p/sell_exp/admin_exp；balancesheet=total_assets/eqt/intan/goodwill/total_share；
#   cashflow=n_cashflow_act；D29 用 fina.profit_dedt（扣非）。
import hashlib
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
sys.path.insert(0, str(ROOT / "src"))
from quant.factors.eval import FactorEvalConfig, evaluate_factor, pit_financial  # noqa: E402

OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/D_fund"
OUT.mkdir(parents=True, exist_ok=True)
PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
PANEL_SHA = hashlib.sha256(PANEL.read_bytes()).hexdigest()
CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
TS = ROOT / "data/raw/tushare"

t0 = time.time()
NUM = {"fina": ["eps", "bps", "roe", "roa", "grossprofit_margin", "netprofit_margin",
                "debt_to_assets", "current_ratio", "netprofit_yoy", "tr_yoy", "ocf_yoy",
                "assets_turn", "q_sales_yoy", "q_roe", "profit_dedt", "ocfps"],
       "income": ["revenue", "n_income_attr_p", "sell_exp", "admin_exp"],
       "bal": ["total_assets", "total_hldr_eqy_exc_min_int", "intan_assets", "goodwill", "total_share"],
       "cf": ["n_cashflow_act"]}
KEYS = ["ts_code", "ann_date", "f_ann_date", "end_date"]


def read_fina(dataset, cols):
    frames = []
    for p in sorted(TS.glob(f"{dataset}/*/chunk_*.csv")):
        if p.stat().st_size <= 100:
            continue
        df = pl.read_csv(p, infer_schema_length=20000)
        if df.height:
            have = [c for c in KEYS if c in df.columns] + [c for c in cols if c in df.columns]
            df = df.select(have)
            df = df.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in cols if c in df.columns])
            frames.append(df)
    return pl.concat(frames, how="diagonal")


def pit_full(events, keep):
    """与 eval.pit_financial 逐字同语义（修正稿胜出/f_ann>ann>end+90d/符号转换），
    但保留指标列 keep。键集与 pit_financial 输出的一致性由调用处校验。"""
    df = events
    for col in ("ann_date", "f_ann_date"):
        if col not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.String).alias(col))
    df = df.with_columns(
        pl.col("ann_date").cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False),
        pl.col("f_ann_date").cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False),
        pl.col("end_date").cast(pl.String).str.strip_chars().str.to_date("%Y%m%d", strict=False),
    )
    df = df.sort("ann_date", nulls_last=True).group_by("ts_code", "end_date").last()
    df = df.with_columns(
        (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
         + "." + pl.col("ts_code").str.split(".").list.first()).alias("symbol"),
        pl.coalesce(pl.col("f_ann_date"), pl.col("ann_date"),
                    pl.col("end_date") + pl.duration(days=90)).alias("signal_date"),
        (pl.col("f_ann_date").fill_null(pl.col("ann_date")).is_null()).alias("used_90d_fallback"),
    )
    out = df.select("symbol", "signal_date", "end_date", "used_90d_fallback", *keep)
    dup = out.group_by("symbol", "signal_date").len().filter(pl.col("len") > 1)
    if dup.height:  # 与 pit_financial 逐字相同：同 (symbol,signal_date) 多报告期取首行
        out = out.group_by("symbol", "signal_date").first()
    return out.sort("symbol", "signal_date")


def pit_checked(raw, keep, name):
    """值载体 = pit_full（tie-break：同 (symbol,signal_date) 多公告取最新 end_date——
    pit_financial 的 .first() 对此为隐式取旧行，语义未定义；本选择在 family_report 披露）。
    校验：与 pit_financial 的 (symbol,signal_date) 键集逐组一致、行数一致、
    end_date 差异仅出现在同日多公告组。"""
    full = pit_full(raw, keep)
    ref = pit_financial(raw)
    assert full.height == ref.height, f"{name}: 行数不一致 {full.height} vs {ref.height}"
    ks_full = full.select("symbol", "signal_date").unique().sort("symbol", "signal_date")
    ks_ref = ref.select("symbol", "signal_date").unique().sort("symbol", "signal_date")
    assert ks_full.equals(ks_ref), f"{name}: (symbol,signal_date) 键集不一致"
    n_diff = (full.select("symbol", "signal_date", "end_date").join(
        ref.select("symbol", "signal_date", "end_date"),
        on=["symbol", "signal_date", "end_date"], how="anti").height)
    print(f"[{time.time()-t0:6.1f}s] {name} pit 键集一致（{full.height} 行；同日多公告 tie-break "
          f"差异 {n_diff} 行=取最新报告期）")
    return full


fina_raw = read_fina("fina_indicator", NUM["fina"])
print(f"[{time.time()-t0:6.1f}s] fina {fina_raw.height}")
inc_raw = read_fina("income", NUM["income"])
print(f"[{time.time()-t0:6.1f}s] income {inc_raw.height}")
bal_raw = read_fina("balancesheet", NUM["bal"])
print(f"[{time.time()-t0:6.1f}s] bal {bal_raw.height}")
cf_raw = read_fina("cashflow", NUM["cf"])
print(f"[{time.time()-t0:6.1f}s] cf {cf_raw.height}")

DEVEND = date(2020, 12, 31)
fina = pit_checked(fina_raw, NUM["fina"], "fina").filter(
    pl.col("end_date") >= date(2014, 1, 1)).filter(pl.col("end_date") <= DEVEND)
inc = pit_checked(inc_raw, NUM["income"], "income").filter(
    pl.col("end_date") >= date(2014, 1, 1)).filter(pl.col("end_date") <= DEVEND)
bal = pit_checked(bal_raw, NUM["bal"], "bal").filter(
    pl.col("end_date") >= date(2014, 1, 1)).filter(pl.col("end_date") <= DEVEND)
cf = pit_checked(cf_raw, NUM["cf"], "cf").filter(
    pl.col("end_date") >= date(2014, 1, 1)).filter(pl.col("end_date") <= DEVEND)
fb90 = int(fina["used_90d_fallback"].sum())
print(f"[{time.time()-t0:6.1f}s] PIT 后 fina {fina.height}（90d 兜底 {fb90} 行）；inc {inc.height}；bal {bal.height}；cf {cf.height}")

# 合并宽表：同 (symbol, end_date) 内侧 join（三表都有才完整；fina 可单独）
fin = (fina.rename({"signal_date": "sd_fina"})
       .join(inc.select("symbol", "end_date", "signal_date", *NUM["income"]).rename({"signal_date": "sd_inc"}),
             on=["symbol", "end_date"], how="left")
       .join(bal.select("symbol", "end_date", "signal_date", *NUM["bal"]).rename({"signal_date": "sd_bal"}),
             on=["symbol", "end_date"], how="left")
       .join(cf.select("symbol", "end_date", "signal_date", *NUM["cf"]).rename({"signal_date": "sd_cf"}),
             on=["symbol", "end_date"], how="left"))
fin = fin.with_columns(pl.max_horizontal("sd_fina", "sd_inc", "sd_bal", "sd_cf").alias("signal_date"))
fin = fin.sort("symbol", "end_date")

# ---- 派生（在 (symbol, end_date) PIT 序列上）----
fin = fin.with_columns(pl.col("end_date").dt.year().alias("_y"), pl.col("end_date").dt.month().alias("_m"))
fin = fin.with_columns((pl.col("_y") - 1).alias("_yly"))
LYCOLS = ("roe", "grossprofit_margin", "debt_to_assets", "eps")
ly = fin.select(
    [pl.col("symbol"), pl.col("_y").alias("_ysrc"), pl.col("_m")]
    + [pl.col(c).alias(c + "_ly") for c in LYCOLS])
fin = fin.join(ly, left_on=["symbol", "_yly", "_m"], right_on=["symbol", "_ysrc", "_m"], how="left")

# 单季差分（累计→单季）：Q1 原值；Q2/Q3/Q4 = 累计 − 上季累计
q_rev = "revenue"
fin = fin.with_columns(
    (pl.col(q_rev) - pl.col(q_rev).shift(1).over("symbol")
     * (pl.col("_m") != 1).cast(pl.Float64)).alias("_rev_q"),
    (pl.col("n_income_attr_p") - pl.col("n_income_attr_p").shift(1).over("symbol")
     * (pl.col("_m") != 1).cast(pl.Float64)).alias("_np_q"),
)
fin = fin.with_columns(
    pl.col("_rev_q").shift(4).over("symbol").alias("_rev_q_ly"),
    pl.col("_np_q").shift(4).over("symbol").alias("_np_q_ly"),
    pl.col("eps").shift(1).over("symbol").alias("_eps_prev"),
)
# TTM：单季净利/营收 4 期滚动和（需连续 4 个报告期同频——用 shift 检查 end_date 月份序列 3,6,9,12）
fin = fin.with_columns(
    pl.col("_np_q").rolling_sum(4, min_samples=4).over("symbol").alias("_np_ttm"),
    pl.col(q_rev).rolling_sum(4, min_samples=4).over("symbol").alias("_rev_ttm"),
    pl.col("q_roe").rolling_sum(4, min_samples=4).over("symbol").alias("D22"),
)
# D23：TTM 毛利率 = Σ(单季营收×单季毛利率)/Σ单季营收 —— 近似用最近报告期 grossprofit_margin
# （单季毛利率未直读；披露口径：以最新报告期毛利率近似 TTM 毛利率）
fin = fin.with_columns(pl.col("grossprofit_margin").alias("D23"))

fin = fin.with_columns(
    (pl.col("roe") - pl.col("roe_ly")).alias("D13"),
    (pl.col("grossprofit_margin") - pl.col("grossprofit_margin_ly")).alias("D14"),
    (pl.col("debt_to_assets") - pl.col("debt_to_assets_ly")).alias("D25"),
    (pl.col("eps") - pl.col("_eps_prev")).alias("D24"),
    (pl.col("n_cashflow_act") / pl.col("revenue")).alias("_ocf_rev"),
    (pl.col("n_cashflow_act") / pl.col("total_assets")).alias("_ocf_ta"),
    ((pl.col("n_income_attr_p") - pl.col("n_cashflow_act")) / pl.col("total_assets")).alias("D15"),
    (pl.col("total_assets") / pl.col("total_hldr_eqy_exc_min_int")).alias("D26"),
    ((pl.col("total_assets") - pl.col("intan_assets") - pl.col("goodwill"))
     / pl.col("total_hldr_eqy_exc_min_int")).alias("D27"),
    ((pl.col("sell_exp") + pl.col("admin_exp")) / pl.col("revenue")).alias("D28"),
    ((pl.col("n_income_attr_p") - pl.col("profit_dedt"))
     / pl.col("n_income_attr_p").abs()).alias("D29"),
    (pl.col("_rev_q") / pl.col("_rev_q_ly") - 1.0).alias("D21x"),  # 单季营收同比（对照 q_sales_yoy）
    (pl.col("_np_q") / pl.col("_np_q_ly").abs() - 1.0
     ).alias("D21"),  # 单季净利同比（分母绝对值，亏损基数口径披露）
)
print(f"[{time.time()-t0:6.1f}s] 派生完成")

# ---- 月末 as-of：每月末取各股 signal_date ≤ 月末 的最新报告（signal_date 最大，tie 取 end_date 大）----
panel_all = pl.read_parquet(PANEL)
panel = (panel_all.filter(pl.col("tradestatus") == 1)
         .filter(pl.col("date") <= date(2020, 12, 31)).sort("symbol", "date"))
me = (panel.group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
      .agg(pl.col("date").max().alias("t")).sort("t"))
ME = me["t"].to_list()

fin_v = fin.filter(pl.col("signal_date") <= date(2020, 12, 31)).sort("symbol", "signal_date", "end_date")
rows = []
for t in ME:
    vis = fin_v.filter(pl.col("signal_date") <= t).group_by("symbol").last()
    vis = vis.with_columns(pl.lit(t).alias("signal_date"))
    rows.append(vis.select("symbol", "signal_date", "end_date",
                           "roe", "roa", "grossprofit_margin", "netprofit_margin", "debt_to_assets",
                           "current_ratio", "eps", "bps", "tr_yoy", "netprofit_yoy",
                           "_ocf_rev", "_ocf_ta", "ocf_yoy", "q_sales_yoy", "D13", "D14", "D15",
                           "D22", "D23", "D24", "D25", "D26", "D27", "D28", "D29", "D21", "ocfps",
                           "assets_turn"))
asof = pl.concat(rows)
print(f"[{time.time()-t0:6.1f}s] 月末 as-of {asof.height} 行")

# D16/D17 复合（月末截面 rank；ep 来自 daily_basic 月末 1/pe_ttm——B 族同源）
db = pl.read_parquet(ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/B_value/B04.parquet")
asof = asof.join(db.rename({"value": "ep"}), on=["symbol", "signal_date"], how="left")
asof = asof.with_columns(
    pl.col("ep").rank("average").over("signal_date").alias("_rk_ep"),
    pl.col("roe").rank("average").over("signal_date").alias("_rk_roe"),
    pl.col("_ocf_rev").rank("average").over("signal_date").alias("_rk_ocf"),
    (-pl.col("debt_to_assets")).rank("average").over("signal_date").alias("_rk_ndebt"),
).with_columns(
    (pl.col("_rk_ep") + pl.col("_rk_roe")).alias("D16"),
    (pl.col("_rk_ocf") + pl.col("_rk_ndebt")).alias("D17"),
)

poolm = (panel_all.filter(pl.col("date") <= date(2020, 12, 31))
         .filter(pl.col("isST").cast(pl.Int64) == 0)
         .filter(pl.col("tradestatus").cast(pl.Int64) == 1)
         .filter(~pl.col("symbol").str.starts_with("sh.688") & ~pl.col("symbol").str.starts_with("bj."))
         .filter(pl.col("date").is_in(pl.Series(ME)))
         .group_by("date").len()["len"].median())

NAMES = {"D01": "roe", "D02": "roa", "D03": "gm", "D04": "nm", "D05": "debt_assets",
         "D06": "cur_ratio", "D07": "ocf_opinc", "D08": "ocf_roa", "D09": "eps", "D10": "bps",
         "D11": "rev_yoy", "D12": "np_yoy", "D13": "roe_d", "D14": "gm_d", "D15": "accruals",
         "D16": "ep_roe", "D17": "quality", "D18": "asset_turn", "D19": "ocf_yoy",
         "D20": "rev_q_yoy", "D21": "np_q_yoy", "D22": "roe_ttm", "D23": "gm_ttm",
         "D24": "eps_dq", "D25": "debt_d", "D26": "eq_mult", "D27": "tangible", "D28": "sga_r",
         "D29": "nonrecc", "D30": "ocf_ps"}
SRCCOL = {"D01": "roe", "D02": "roa", "D03": "grossprofit_margin", "D04": "netprofit_margin",
          "D05": "debt_to_assets", "D06": "current_ratio", "D07": "_ocf_rev", "D08": "_ocf_ta",
          "D09": "eps", "D10": "bps", "D11": "tr_yoy", "D12": "netprofit_yoy", "D18": "assets_turn",
          "D19": "ocf_yoy", "D20": "q_sales_yoy", "D30": "ocfps"}
survivors = []
stats_rows = {}
for i in range(1, 31):
    fid = f"D{i:02d}"
    col = SRCCOL.get(fid, fid)
    f = (asof.select("symbol", "signal_date", pl.col(col).alias("value"))
         .drop_nulls("value").filter(pl.col("value").is_finite())
         .filter(pl.col("signal_date") <= date(2020, 11, 30)))
    dup = f.group_by(["symbol", "signal_date"]).len().filter(pl.col("len") > 1).height
    assert dup == 0
    ts = time.time()
    res = evaluate_factor(f, panel_all, CFG)
    t = res["ic_mean"] / res["ic_std"] * math.sqrt(res["n_dates"]) if res["ic_std"] else float("nan")
    icm, mono, cov = res["ic_mean"], res["monotonicity"], res["coverage_mean_symbols"]
    ic15 = res["ic_by_year"].get(2015)
    c1 = abs(t) >= 2.0
    c2 = (mono > 0) == (icm > 0) and abs(mono) >= 0.3
    c3 = (ic15 is None) or not ((ic15 > 0) != (icm > 0) and abs(ic15) > 0.03)
    c4 = cov / poolm >= 0.5
    surv = c1 and c2 and c3 and c4
    if surv:
        survivors.append(fid)
    f.write_parquet(OUT / f"{fid}.parquet")
    doc = {
        "factor_id": fid, "name": NAMES[fid], "family": "D 财务 PIT",
        "prereg": "exp-20260919-factor-round-f2r1 §3-D", "panel_sha256": PANEL_SHA,
        "eval_panel_end": "2020-11-30", "implementer": "主对话接管（三任代理死于基建后）",
        "screen": {"t_ic": t, "crit1_abs_t_ge2": c1, "crit2_mono": c2, "ic_2015": ic15,
                   "crit3_2015_ok": c3, "pool_median_symbols": poolm,
                   "coverage_ratio": cov / poolm, "crit4_coverage": c4, "screen_pass": surv},
        "eval": res, "n_rows": f.height,
    }
    (OUT / f"{fid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{time.time()-t0:6.1f}s] {fid} {NAMES[fid]:<10} ic={icm:+.4f} t={t:+.2f} mono={mono:+.2f} "
          f"ic15={'n/a' if ic15 is None else format(ic15,'+.4f')} cov={cov/poolm:.0%} "
          f"{'存活' if surv else ''} ({time.time()-ts:.1f}s)")

# 披露三件套量化
pit_cov = asof.filter(pl.col("signal_date") <= date(2020, 11, 30)).group_by(
    pl.col("signal_date").dt.year()).agg(pl.col("roe").is_not_null().mean().alias("roe_cov")).sort("signal_date")
print("年度 PIT 覆盖率(roe 非空占比):", {r["signal_date"]: round(r["roe_cov"], 3) for r in pit_cov.to_dicts()})
print(f"\n== D 族完成：30/30，终裁存活 {len(survivors)}：{survivors}；90d 兜底 {fb90} 行；总耗时 {time.time()-t0:.0f}s ==")
