# F2R1 C 族（微观结构 20 因子）——主对话接管实施
# 冻结依据：docs/research/exp-20260919-factor-round-f2r1-prereg.md §1/§2/§3-C（语义公式）
# 字段映射（最重要披露，见 family_report.md 首节）：
#   竞价 = xiaodefa stk_auction_c（竞价时点聚合：open=竞价价、vol=竞价量；已核验
#          open≠面板 open、vol≈面板 volume 的 11%——是竞价口径而非全天）；
#   主力 = moneyflow (buy_lg+buy_elg)−(sell_lg+sell_elg)（大+特大单，提示词定义）；
#   涨跌停 = stk_limit（名义价，已核验 = preclose×1.1/0.9 四舍五入，与面板一致）；
#   九转 = stk_nineturn 的 nine_up_turn−nine_down_turn（净 TD 计数，映射披露）。
# 口径：全部逐日比率在日频帧按交易日行序滚动后切月末；评估信号 ≤2020-11-30（68 期统一）。
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

OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "C_micro"
OUT.mkdir(parents=True, exist_ok=True)
PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
PANEL_SHA = hashlib.sha256(PANEL.read_bytes()).hexdigest()
CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
XD = ROOT / "data/raw/xiaodefa"

t0 = time.time()


def read_xd(dataset, cols, num_cols=()):
    frames = []
    for p in sorted((XD / dataset / "20260913-bulk1").glob("chunk_*.csv")):
        k = p.stem.replace("chunk_", "")
        _hi = "20241231" if _WINDOW == "val" else "20201231"
        # Validation only needs rolling warm-up before 2021-01; retaining
        # 2020 onward avoids loading the full 2015-2024 micro tables.
        _lo = "20200101" if _WINDOW == "val" else "20150101"
        if not (_lo <= k <= _hi) or p.stat().st_size <= 100:
            continue
        df = pl.read_csv(p, infer_schema_length=10000)
        if df.height:
            df = df.select([c for c in cols if c in df.columns])
            if num_cols:
                df = df.with_columns([pl.col(c).cast(pl.Float64, strict=False)
                                      for c in num_cols if c in df.columns])
            frames.append(df)
    return pl.concat(frames, how="diagonal")


def sym(df):
    d = pl.col("trade_date").cast(pl.String)
    date_parsed = pl.coalesce(
        d.str.to_date("%Y%m%d", strict=False),  # 20150602
        d.str.slice(0, 10).str.replace_all("-", "").str.to_date("%Y%m%d", strict=False),  # 2015-06-02 …
    )
    return df.with_columns(
        (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
         + "." + pl.col("ts_code").str.split(".").list.first()).alias("symbol"),
        date_parsed.alias("date"),
    ).drop("ts_code", "trade_date")


auc = sym(read_xd("stk_auction_c", ["ts_code", "trade_date", "open", "vol"]).rename({"open": "auct_open", "vol": "auct_vol"}))
print(f"[{time.time()-t0:6.1f}s] auction {auc.height}")
mf_cols = ["ts_code", "trade_date"] + [f"{b}_{s}_amount" for b in ("buy", "sell") for s in ("sm", "md", "lg", "elg")]
mf = sym(read_xd("moneyflow", mf_cols))
print(f"[{time.time()-t0:6.1f}s] moneyflow {mf.height}")
lim = sym(read_xd("stk_limit", ["ts_code", "trade_date", "up_limit", "down_limit"]))
print(f"[{time.time()-t0:6.1f}s] limit {lim.height}")
nt = sym(read_xd("stk_nineturn", ["ts_code", "trade_date", "nine_up_turn", "nine_down_turn"],
                 num_cols=("nine_up_turn", "nine_down_turn")))
nt = nt.with_columns((pl.col("nine_up_turn").fill_null(0) - pl.col("nine_down_turn").fill_null(0)).alias("td"))
print(f"[{time.time()-t0:6.1f}s] nineturn {nt.height}")

panel_all = pl.read_parquet(PANEL).filter(
    pl.col("date").is_between(date(2020, 1, 1), WINDOW_END)
)
panel = (panel_all.filter(pl.col("tradestatus") == 1)
         .filter(pl.col("date") <= WINDOW_END).sort("symbol", "date"))

g = (panel.select("symbol", "date", "open", "high", "low", "close", "preclose", "volume", "amount")
     .join(auc, on=["symbol", "date"], how="left")
     .join(mf, on=["symbol", "date"], how="left")
     .join(lim, on=["symbol", "date"], how="left")
     .join(nt.select("symbol", "date", "td"), on=["symbol", "date"], how="left"))
g = g.with_columns(
    (pl.col("auct_open") / pl.col("preclose") - 1.0).alias("auct_prem"),
    (pl.col("auct_vol") / pl.col("volume")).alias("auct_volr"),
    ((pl.col("buy_lg_amount").fill_null(0) + pl.col("buy_elg_amount").fill_null(0)
      - pl.col("sell_lg_amount").fill_null(0) - pl.col("sell_elg_amount").fill_null(0))
     / pl.col("amount")).alias("mf_main_r"),
    ((pl.col("buy_sm_amount").fill_null(0) + pl.col("buy_md_amount").fill_null(0)
      + pl.col("buy_lg_amount").fill_null(0) + pl.col("buy_elg_amount").fill_null(0))
     / pl.col("amount")).alias("buy_r"),
    ((pl.col("sell_sm_amount").fill_null(0) + pl.col("sell_md_amount").fill_null(0)
      + pl.col("sell_lg_amount").fill_null(0) + pl.col("sell_elg_amount").fill_null(0))
     / pl.col("amount")).alias("sell_r"),
    ((pl.col("buy_lg_amount").fill_null(0) + pl.col("buy_elg_amount").fill_null(0))
     / pl.col("amount")).alias("lgbuy_r"),
    ((pl.col("sell_lg_amount").fill_null(0) + pl.col("sell_elg_amount").fill_null(0))
     / pl.col("amount")).alias("lgsell_r"),
    (pl.col("close") / pl.col("up_limit")).alias("up_r"),
    (pl.col("close") / pl.col("down_limit")).alias("dn_r"),
    (pl.col("close") == pl.col("up_limit")).cast(pl.Float64).alias("is_limup"),
    ((pl.col("close") - pl.col("low")) / (pl.col("high") - pl.col("low"))).alias("cls_str"),
)
# 20/60 滚动（fill_null(0) 的资金比率行保留；auction/limit 缺失行 prem/volr 为 null 不填）
g = g.with_columns(
    pl.col("auct_prem").rolling_mean(20, min_samples=20).over("symbol").alias("C01"),
    pl.col("auct_prem").rolling_std(20, min_samples=20).over("symbol").alias("C02"),
    pl.col("auct_volr").rolling_mean(20, min_samples=20).over("symbol").alias("C03"),
    pl.col("mf_main_r").rolling_mean(20, min_samples=20).over("symbol").alias("C04"),
    pl.col("mf_main_r").rolling_mean(5, min_samples=5).over("symbol").alias("_mf5"),
    pl.col("mf_main_r").rolling_mean(20, min_samples=20).over("symbol").alias("_mf20"),
    pl.col("buy_r").rolling_mean(20, min_samples=20).over("symbol").alias("C07"),
    pl.col("sell_r").rolling_mean(20, min_samples=20).over("symbol").alias("C08"),
    pl.col("lgbuy_r").rolling_mean(20, min_samples=20).over("symbol").alias("C09"),
    pl.col("lgsell_r").rolling_mean(20, min_samples=20).over("symbol").alias("C10"),
    pl.col("up_r").rolling_mean(20, min_samples=20).over("symbol").alias("C11"),
    pl.col("dn_r").rolling_mean(20, min_samples=20).over("symbol").alias("C12"),
    pl.col("is_limup").rolling_sum(20, min_samples=20).over("symbol").alias("C13"),
    pl.col("is_limup").rolling_sum(60, min_samples=60).over("symbol").alias("C14"),
    pl.col("auct_prem").rolling_mean(5, min_samples=5).over("symbol").alias("_ap5"),
    # C17: 20 日偏度（总体矩 g1，与 F06 口径一致）
    ((pl.col("mf_main_r") * pl.col("mf_main_r") * pl.col("mf_main_r")).rolling_mean(20, min_samples=20).over("symbol")).alias("_m3"),
    (pl.col("mf_main_r").rolling_var(20, min_samples=20).over("symbol")).alias("_v2"),
    pl.col("cls_str").rolling_mean(20, min_samples=20).over("symbol").alias("C19"),
    pl.col("cls_str").rolling_mean(60, min_samples=60).over("symbol").alias("C20"),
    pl.col("td").rolling_sum(20, min_samples=20).over("symbol").alias("C16"),
)
g = g.with_columns(
    (pl.col("_mf5") - pl.col("_mf20")).alias("C06"),
    (pl.col("_ap5") - pl.col("C01")).alias("C18"),
    (pl.col("_m3") / (pl.col("_v2") ** 1.5)).alias("C17"),
)
print(f"[{time.time()-t0:6.1f}s] 滚动完成")

me = (panel.group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
      .agg(pl.col("date").max().alias("signal_date")).sort("signal_date"))
ME = me["signal_date"].to_list()
month_end = g.filter(pl.col("date").is_in(pl.Series(ME)))

poolm = (panel_all.filter(pl.col("date") <= WINDOW_END)
         .filter(pl.col("isST").cast(pl.Int64) == 0)
         .filter(pl.col("tradestatus").cast(pl.Int64) == 1)
         .filter(~pl.col("symbol").str.starts_with("sh.688") & ~pl.col("symbol").str.starts_with("bj."))
         .filter(pl.col("date").is_in(pl.Series(ME)))
         .group_by("date").len()["len"].median())

NAMES = {
    "C01": "auct_prem20", "C02": "auct_premstd", "C03": "auct_volr20", "C04": "mf_net20",
    "C05": None, "C06": "mf_mom", "C07": "buy_r20", "C08": "sell_r20", "C09": "lgbuy_r20",
    "C10": "lgsell_r20", "C11": "lim_dist_up", "C12": "lim_dist_dn", "C13": "lim_up20",
    "C14": "lim_up60", "C15": "td_setup", "C16": "td_sum20", "C17": "mf_skew20",
    "C18": "auct_premmom", "C19": "cls_str20", "C20": "cls_str60",
}
survivors = []
for i in (1, 11, 12, 19):
    fid = f"C{i:02d}"
    ts = time.time()
    if fid == "C15":  # 月末九转原值（不滚动）
        f = month_end.select(pl.col("symbol"), signal_date=pl.col("date"), value=pl.col("td")).drop_nulls("value")
    elif fid == "C05":  # mf_net5 = _mf5
        f = month_end.select(pl.col("symbol"), signal_date=pl.col("date"), value=pl.col("_mf5")).drop_nulls("value")
    else:
        f = month_end.select(pl.col("symbol"), signal_date=pl.col("date"), value=pl.col(fid)).drop_nulls("value")
    f = sig_cap(f, date(2020, 11, 30))
    dup = f.group_by(["symbol", "signal_date"]).len().filter(pl.col("len") > 1).height
    assert dup == 0
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
        "factor_id": fid, "name": NAMES[fid] or "mf_net5", "family": "C 微观结构",
        "prereg": "exp-20260919-factor-round-f2r1 §3-C", "panel_sha256": PANEL_SHA,
        "eval_panel_end": "2020-11-30", "implementer": "主对话接管（代理派发死于基建后）",
        "screen": {"t_ic": t, "crit1_abs_t_ge2": c1, "crit2_mono": c2, "ic_2015": ic15,
                   "crit3_2015_ok": c3, "pool_median_symbols": poolm,
                   "coverage_ratio": cov / poolm, "crit4_coverage": c4, "screen_pass": surv},
        "eval": res, "n_rows": f.height,
    }
    (OUT / f"{fid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{time.time()-t0:6.1f}s] {fid} {NAMES[fid] or 'mf_net5':<12} ic={icm:+.4f} t={t:+.2f} "
          f"mono={mono:+.2f} ic15={'n/a' if ic15 is None else format(ic15,'+.4f')} "
          f"cov={cov/poolm:.0%} {'存活' if surv else ''} ({time.time()-ts:.1f}s)")

print(f"\n== C 族完成：20/20，终裁存活 {len(survivors)}：{survivors}；总耗时 {time.time()-t0:.0f}s ==")


