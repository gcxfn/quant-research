# F2R1 B 族（估值/规模 15 因子）——主对话接管实施（基建持续死亡后）
# 冻结依据：docs/research/exp-20260919-factor-round-f2r1-prereg.md §1/§2/§3-B
# 口径：daily_basic 两批（20260913-r2=2015-2018、20260909-r1=2019 起）；
#       快照类=月末行直接取；窗口类（B09-B12/B15）在日频帧滚动后切月末；
#       B09-B11 用 daily_basic.turnover_rate，B12 按冻结公式用面板 turn 列；
#       负 pe 保留符号（负盈利收益率），pe=0/null → null；
#       B13/B14 为月末截面 rank 复合；评估信号 ≤2020-11-30（68 期统一口径）。
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

OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "B_value"
OUT.mkdir(parents=True, exist_ok=True)
PANEL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
PANEL_SHA = hashlib.sha256(PANEL.read_bytes()).hexdigest()
CFG = FactorEvalConfig(horizon_days=20, n_groups=10, eval_freq="M", min_history_rows=60)
DB_COLS = ["ts_code", "trade_date", "turnover_rate", "pe", "pe_ttm", "pb",
           "ps_ttm", "dv_ratio", "total_mv", "circ_mv"]

t0 = time.time()


def read_db(sub, lo, hi):
    frames = []
    for p in sorted((ROOT / f"data/raw/tushare/daily_basic/{sub}").glob("chunk_*.csv")):
        key = p.stem.replace("chunk_", "")
        if not (lo <= key <= hi) or p.stat().st_size <= 100:
            continue
        df = pl.read_csv(p, infer_schema_length=10000)
        if df.height:
            frames.append(df.select([c for c in DB_COLS if c in df.columns]))
    return pl.concat(frames, how="diagonal")


db = pl.concat([
    read_db("20260913-r2", "20150101", "20181231"),
    read_db("20260909-r1", "20190101",
            "20241231" if _WINDOW == "val" else "20201231"),
], how="diagonal")
db = db.with_columns(
    (pl.col("ts_code").str.split(".").list.last().str.to_lowercase()
     + "." + pl.col("ts_code").str.split(".").list.first()).alias("symbol"),
    pl.col("trade_date").cast(pl.String).str.to_date("%Y%m%d").alias("date"),
).drop("ts_code", "trade_date").unique(subset=["symbol", "date"])
print(f"[{time.time()-t0:6.1f}s] daily_basic {db.height} 行 {db['symbol'].n_unique()} 符号 "
      f"{db['date'].min()}..{db['date'].max()}")

panel_all = pl.read_parquet(PANEL)
panel = (panel_all.filter(pl.col("tradestatus") == 1)
         .filter(pl.col("date") <= WINDOW_END).sort("symbol", "date"))
me = (panel.group_by(pl.col("date").dt.year().alias("_y"), pl.col("date").dt.month().alias("_m"))
      .agg(pl.col("date").max().alias("signal_date")).sort("signal_date"))
ME = me["signal_date"].to_list()

# ---- 窗口类（日频，join 面板 turn）----
dbd = (db.join(panel.select("symbol", "date", "turn"), on=["symbol", "date"], how="left")
       .sort("symbol", "date"))
dbd = dbd.with_columns(
    pl.col("turnover_rate").rolling_mean(20, min_samples=20).over("symbol").alias("B09"),
    pl.col("turnover_rate").rolling_mean(60, min_samples=60).over("symbol").alias("B10"),
    pl.col("turnover_rate").rolling_std(20, min_samples=20).over("symbol").alias("B11"),
    (pl.col("turn").rolling_mean(5, min_samples=5).over("symbol")
     / pl.col("turn").rolling_mean(120, min_samples=120).over("symbol")).alias("B12"),
    (pl.col("total_mv") / pl.col("total_mv").shift(20).over("symbol") - 1.0).alias("B15"),
)
me_db = dbd.filter(pl.col("date").is_in(pl.Series(ME)))
print(f"[{time.time()-t0:6.1f}s] 窗口类完成")

# ---- 快照类（月末行）----
snap = db.filter(pl.col("date").is_in(pl.Series(ME)))
snap = snap.with_columns(
    pl.col("total_mv").log().alias("B01"),
    pl.col("circ_mv").log().alias("B02"),
    (pl.col("circ_mv") / pl.col("total_mv")).alias("B03"),
    (1.0 / pl.col("pe_ttm")).alias("B04"),
    (1.0 / pl.col("pb")).alias("B05"),
    (1.0 / pl.col("ps_ttm")).alias("B06"),
    pl.col("dv_ratio").alias("B07"),
    (1.0 / pl.col("pe")).alias("B08"),
)
# B13/B14：月末截面 rank 复合
snap = snap.with_columns(
    pl.col("B04").rank("average").over("date").alias("_rk_ep"),
    pl.col("B05").rank("average").over("date").alias("_rk_bp"),
    (-pl.col("B01")).rank("average").over("date").alias("_rk_small"),
).with_columns(
    (pl.col("_rk_ep") + pl.col("_rk_bp")).alias("B13"),
    (pl.col("_rk_small") + pl.col("_rk_bp")).alias("B14"),
)

COLS = {f"B{i:02d}": me_snap for i in []}  # noqa: placeholder
FRAMES = {}
for i in list(range(1, 16)):
    fid = f"B{i:02d}"
    src = snap if i <= 8 or i in (13, 14) else me_db
    f = (src.select(pl.col("symbol"), signal_date=pl.col("date"), value=pl.col(fid))
         .drop_nulls("value").filter(pl.col("value").is_finite())
         .pipe(lambda _f: sig_cap(_f, date(2020, 11, 30))))
    dup = f.group_by(["symbol", "signal_date"]).len().filter(pl.col("len") > 1).height
    assert dup == 0 and f["signal_date"].max() <= WINDOW_END
    FRAMES[fid] = f

poolm = (panel_all.filter(pl.col("date") <= WINDOW_END)
         .filter(pl.col("isST").cast(pl.Int64) == 0)
         .filter(pl.col("tradestatus").cast(pl.Int64) == 1)
         .filter(~pl.col("symbol").str.starts_with("sh.688") & ~pl.col("symbol").str.starts_with("bj."))
         .filter(pl.col("date").is_in(pl.Series(ME)))
         .group_by("date").len()["len"].median())

NAMES = {
    "B01": "ln_tmv", "B02": "ln_cmv", "B03": "circ_ratio", "B04": "ep_ttm", "B05": "bp",
    "B06": "sp_ttm", "B07": "dv_yield", "B08": "ep_static", "B09": "turn_20", "B10": "turn_60",
    "B11": "turn_vol20", "B12": "turn_abn", "B13": "ep_bp", "B14": "small_value", "B15": "mv_ret20",
}
survivors = []
for fid, f in sorted(FRAMES.items()):
    ts = time.time()
    res = evaluate_factor(f, panel_all, CFG)
    t = res["ic_mean"] / res["ic_std"] * math.sqrt(res["n_dates"]) if res["ic_std"] else float("nan")
    icm, mono, cov = res["ic_mean"], res["monotonicity"], res["coverage_mean_symbols"]
    ic15 = res["ic_by_year"].get(2015)  # int 键！
    c1 = abs(t) >= 2.0
    c2 = (mono > 0) == (icm > 0) and abs(mono) >= 0.3
    c3 = (ic15 is None) or not ((ic15 > 0) != (icm > 0) and abs(ic15) > 0.03)
    c4 = cov / poolm >= 0.5
    surv = c1 and c2 and c3 and c4
    if surv:
        survivors.append(fid)
    f.write_parquet(OUT / f"{fid}.parquet")
    doc = {
        "factor_id": fid, "name": NAMES[fid], "family": "B 估值/规模",
        "prereg": "exp-20260919-factor-round-f2r1 §3-B", "panel_sha256": PANEL_SHA,
        "eval_panel_end": "2020-11-30", "implementer": "主对话接管（代理派发死于基建后）",
        "screen": {"t_ic": t, "crit1_abs_t_ge2": c1, "crit2_mono": c2, "ic_2015": ic15,
                   "crit3_2015_ok": c3, "pool_median_symbols": poolm,
                   "coverage_ratio": cov / poolm, "crit4_coverage": c4, "screen_pass": surv},
        "eval": res, "n_rows": f.height,
    }
    (OUT / f"{fid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{time.time()-t0:6.1f}s] {fid} {NAMES[fid]:<12} ic={icm:+.4f} t={t:+.2f} mono={mono:+.2f} "
          f"ic15={'n/a' if ic15 is None else format(ic15,'+.4f')} cov={cov/poolm:.0%} "
          f"n={f.height} {'存活' if surv else ''} ({time.time()-ts:.1f}s)")

print(f"\n== B 族完成：15/15，终裁存活 {len(survivors)}：{survivors}；池中位 {poolm}；总耗时 {time.time()-t0:.0f}s ==")
