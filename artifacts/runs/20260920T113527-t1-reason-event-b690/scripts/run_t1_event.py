# -*- coding: utf-8 -*-
"""exp-20260920-t1-reason-event -- T1 业绩预告归因的事件研究主脚本。

预登记：docs/research/exp-20260920-t1-reason-event-prereg.md（逐字执行）。
- H1 主判定：月份固定效应 + type 组内去均值后 primary_code 类别间 ANOVA，
  p < 0.05 -> H1；p in [0.05, 0.20) -> 边缘；p >= 0.20 -> H0。
- 事件窗 dev ann_date 2018-09-04..2020-12-31；val 2021-2024 与冻结区 2025+
  零接触（合并后 / 池过滤后 / 各变体样本三处断言；h=20 窗口右端允许自然
  溢出到 2021-01 交易日价格——事件在 dev 内、价格数据正常使用，与"使用
  2021 事件"不同；manifest 注明并记录窗口右端最大日期）。
- 池：R16 共享库逐字（p2r16_trend_dispersion / p2r13_lowfreq），事件日口径
  上市>=60 交易日（build_history_r16 的 listing_index>=60，own-session 计数
  含事件日）、非 ST（事件日 isST==0）、板块排除（board_ok_expr 逐字，
  sh.60*/sz.00* 主板）、事件日可交易（该股当日有 tradestatus==1 行）。
  不含月频 top-K 席位与流动性排序（预登记 §2 事件日口径四条件，无流动性项）。
- 前向收益：与 F2R1 eval harness 同式自写（close/preclose 复利链、T+1 起、
  停牌行过滤、h=20；敏感性 h=5/10）。链的行宇宙 = harness 同式
  （tradestatus==1 且 isST==0），事件日资格由 R16 池四条件另行保证；
  TE-S2 抽 3 股 x 3 事件对 harness 网格值核对，容差 1e-9，对不上即停。
- 无 RNG（确定性等距抽样）；确定性全流程。

停机规则：样本量门槛 / TE-S2 失败 / 2021+ 事件混入 / 并组后类别数<2 -> 写
tmp/stop_report.md + manifest status=aborted 并退出。
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from datetime import date
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
import scipy  # noqa: E402
import scipy.stats  # noqa: E402

from quant.factors.eval import (  # noqa: E402
    FactorEvalConfig, _forward_return_grid, _prepare_panel, _validate_panel)
from quant.research import p2r13_lowfreq as p13  # noqa: E402
from quant.research import p2r16_trend_dispersion as r16  # noqa: E402

T1_DIR = ROOT / "data/features/fcst-reason-struct-full-20260918"
DAILY_CAL = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
DAILY_EVAL = ROOT / "data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
PREREG_MD = ROOT / "docs/research/exp-20260920-t1-reason-event-prereg.md"

DEV_FIRST, DEV_LAST = "20180904", "20201231"
DEV_LAST_D = date(2020, 12, 31)
H_MAIN = 20
H_SENS = (5, 10)
MIN_CLASS_N = 100          # 类别进两两比较门槛（不足并入 other）
GATE_MIN_TOTAL = 5_000     # §2 样本量门槛
GATE_MIN_TYPE = 100
TYPE8 = ["预增", "首亏", "预减", "续亏", "略增", "扭亏", "略减", "续盈"]
LOSS_TYPES = ("首亏", "续亏")   # sanity "预亏组" 的操作化（报告披露）
# 15 类封闭词表（pilot schema.md 逐字）
VOCAB15 = ["demand_up", "demand_down", "price_up", "price_down", "orders",
           "cost_up", "cost_down", "fx", "impairment", "non_recurring",
           "ma_restructuring", "epidemic_shock", "accounting", "core_ops",
           "other"]
YEARS_SEG = [("2018H2", date(2018, 9, 1), date(2018, 12, 31)),
             ("2019", date(2019, 1, 1), date(2019, 12, 31)),
             ("2020", date(2020, 1, 1), date(2020, 12, 31))]
# F2R1 冻结评估配置（TE-S2 harness 参照值用，与 attribution 先例逐字一致）
EVAL_CFG = FactorEvalConfig(horizon_days=H_MAIN, n_groups=10, eval_freq="M",
                            min_history_rows=60)

T0 = time.perf_counter()
PEAK_RSS = 0.0
STAGES: dict[str, float] = {}


def log(msg: object) -> None:
    global PEAK_RSS
    try:
        import psutil
        PEAK_RSS = max(PEAK_RSS, psutil.Process().memory_info().rss / 1e9)
    except Exception:
        pass
    print(f"[{time.perf_counter() - T0:7.1f}s] {msg}", flush=True)


def stage(name: str) -> None:
    STAGES[name] = time.perf_counter() - T0
    log(f"== stage done: {name} ({STAGES[name]:.1f}s) ==")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


MANIFEST: dict = {
    "experiment_id": "exp-20260920-t1-reason-event",
    "run_id": RUN_DIR.name,
    "status": "running",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "prereg": str(PREREG_MD),
    "stages_s": STAGES,
    # 预登记 §2/任务书：收益窗口右端可自然溢出到 dev 之后的交易日价格（事件
    # 在 dev 内、价格数据正常使用），与"使用 2021+ 事件"不同——此处显式注明；
    # 长期停牌股的 own-session 窗口日历跨度量化见 results。
    "window_spill_note": "all events have ann_date<=2020-12-31 (asserted at "
                         "merge, pool filter and every variant sample); the "
                         "h=20 forward window right edge uses traded prices "
                         "after the event (price data only, never a 2021+ "
                         "event); most windows end 2021-01, multi-year "
                         "suspensions stretch a few (quantified in results)",
}


def write_manifest() -> None:
    MANIFEST["stages_s"] = dict(STAGES)
    MANIFEST["wall_seconds"] = time.perf_counter() - T0
    MANIFEST["peak_rss_gb"] = PEAK_RSS
    MANIFEST["env"] = {"python": platform.python_version(),
                       "polars": pl.__version__, "numpy": np.__version__,
                       "scipy": scipy.__version__,
                       "platform": platform.platform()}
    (RUN_DIR / "manifest.json").write_text(
        json.dumps(MANIFEST, ensure_ascii=False, indent=1, default=str),
        encoding="utf-8")


def stop(reason: str) -> None:
    """停机纪律：写 tmp/stop_report.md + manifest status=aborted，退出码 2。"""
    log(f"!! STOP: {reason}")
    (RUN_DIR / "tmp" / "stop_report.md").write_text(
        "# STOP REPORT -- exp-20260920-t1-reason-event\n\n"
        f"- stopped_at: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n"
        f"- elapsed_s: {time.perf_counter() - T0:.1f}\n"
        f"- reason: {reason}\n"
        f"- stages_completed_s: {json.dumps(dict(STAGES))}\n"
        "- completed_artifacts: 见 outputs/ 与 manifest.json（status=aborted，"
        "含停机前已写入的判定中间量）\n",
        encoding="utf-8")
    MANIFEST["status"] = "aborted"
    MANIFEST["stop_reason"] = reason
    write_manifest()
    sys.exit(2)


def ts_to_symbol(ts_code: str) -> str | None:
    """tushare '000750.SZ' -> baostock 'sz.000750'；无法转换返回 None。"""
    parts = ts_code.split(".")
    if len(parts) != 2 or len(parts[0]) != 6:
        return None
    suf = parts[1].upper()
    if suf not in ("SZ", "SH"):
        return None
    return f"{suf.lower()}.{parts[0]}"


def symbol_to_ts(symbol: str) -> str:
    pre, code = symbol.split(".")
    return f"{code}.{pre.upper()}"


def bh_adjust(ps: list[float]) -> list[float]:
    """Benjamini-Hochberg step-up 校正（返回与输入同序的 adjusted p）。"""
    m = len(ps)
    order = sorted(range(m), key=lambda i: ps[i])
    adj = [0.0] * m
    prev = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        val = min(prev, ps[i] * m / rank)
        adj[i] = val
        prev = val
    return adj


def anova_f(vals: np.ndarray, groups: np.ndarray) -> dict:
    """单因素 ANOVA F 检验（manual SS + scipy f.sf）。"""
    levels = sorted(set(groups.tolist()))
    k = len(levels)
    n = len(vals)
    grand = float(vals.mean())
    ssb = 0.0
    ssw = 0.0
    gmeans: dict[str, float] = {}
    gns: dict[str, int] = {}
    for lv in levels:
        x = vals[groups == lv]
        gns[lv] = int(x.size)
        gm = float(x.mean())
        gmeans[lv] = gm
        ssb += x.size * (gm - grand) ** 2
        ssw += float(((x - gm) ** 2).sum())
    df1, df2 = k - 1, n - k
    f_stat = (ssb / df1) / (ssw / df2)
    p = float(scipy.stats.f.sf(f_stat, df1, df2))
    return {"F": float(f_stat), "p": p, "df1": df1, "df2": df2, "k": k,
            "n": n, "ss_between": ssb, "ss_within": ssw,
            "eta_squared": (ssb / (ssb + ssw)) if (ssb + ssw) > 0 else None,
            "grand_mean": grand, "group_means": gmeans, "group_ns": gns}


def verdict_of(p: float) -> str:
    if p < 0.05:
        return "H1"
    if p < 0.20:
        return "边缘"
    return "H0"


def own_fwd(panel: pl.DataFrame, horizons: tuple[int, ...]) -> pl.DataFrame:
    """自写前向收益：fwd(t) = prod(1+day_ret[t+1..t+h]) - 1。

    与 F2R1 eval harness 同式：close/preclose 链、T+1 起、行过滤后的
    own-session 网格（本实验链宇宙 = tradestatus==1 且 isST==0）、窗口不足
    h 行 -> 缺失；suffix cum_prod 实现与 harness 同序。另返回 h=20 窗口
    右端日期（wend_h20）供溢出披露。
    """
    g = panel.sort("symbol", "date").with_columns(
        (pl.col("close") / pl.col("preclose") - 1.0).alias("day_ret"))
    g = g.with_columns((1.0 + pl.col("day_ret")).alias("_gross"))
    g = g.with_columns(
        pl.col("_gross").reverse().cum_prod().reverse().over("symbol")
        .alias("_cump"))
    exprs = []
    for h in horizons:
        g = g.with_columns(
            pl.col("_cump").shift(-1).over("symbol").alias(f"_c0_{h}"),
            pl.col("_cump").shift(-(h + 1)).over("symbol")
            .fill_null(1.0).alias(f"_c1_{h}"),
            pl.col("day_ret").shift(-h).over("symbol").is_not_null()
            .alias(f"_ok_{h}"))
        exprs.append(
            pl.when(pl.col(f"_c0_{h}").is_not_null() & pl.col(f"_ok_{h}"))
            .then(pl.col(f"_c0_{h}") / pl.col(f"_c1_{h}") - 1.0)
            .otherwise(None).alias(f"fwd_h{h}"))
    g = g.with_columns(exprs)
    g = g.with_columns(
        pl.col("date").shift(-H_MAIN).over("symbol").alias("wend_h20"))
    keep = ["symbol", "date", "wend_h20"] + [f"fwd_h{h}" for h in horizons]
    return g.select(keep)


def build_groups(df: pl.DataFrame) -> tuple[pl.DataFrame, list[str], list[str]]:
    """类别 >=MIN_CLASS_N 保留，其余并入 other；返回 (df+group 列, 组列表,
    并入类列表)。group='other' 可含词表内原生 other（>=门槛时）与并入桶。"""
    cnt = df.group_by("primary_code").len().sort("primary_code")
    keep = [r["primary_code"] for r in cnt.iter_rows(named=True)
            if r["len"] >= MIN_CLASS_N]
    merged_out = [r["primary_code"] for r in cnt.iter_rows(named=True)
                  if r["len"] < MIN_CLASS_N]
    out = df.with_columns(
        pl.when(pl.col("primary_code").is_in(keep))
        .then(pl.col("primary_code")).otherwise(pl.lit("other"))
        .alias("group"))
    groups = sorted(set(keep) | ({"other"} if merged_out else set()))
    return out, groups, merged_out


def run_main_pipeline(df: pl.DataFrame, h_col: str, label: str) -> dict:
    """变体重跑主判定：月份 FE（变体样本内）-> type 组内去均值 -> 类别并组
    （门槛在变体样本内重算）-> ANOVA。机械规则与主判定完全一致。"""
    d = df.with_columns(
        (pl.col(h_col) - pl.col(h_col).mean().over("month")).alias("_adj"))
    d = d.with_columns(
        (pl.col("_adj") - pl.col("_adj").mean().over("type")).alias("y_wd"))
    d_g, gs, mc = build_groups(d)
    if len(gs) < 2:
        stop(f"敏感性 {label}: 并组后类别数 {len(gs)} < 2 -> 停机呈报")
    v = d_g["y_wd"].to_numpy().astype(float)
    g = d_g["group"].to_numpy()
    rr = anova_f(v, g)
    return {"variant": label, "n": rr["n"], "k_groups": rr["k"],
            "F": rr["F"], "p": rr["p"], "verdict": verdict_of(rr["p"]),
            "eta_squared": rr["eta_squared"], "groups": ",".join(gs),
            "merged_into_other": ",".join(mc)}


# === 0. identity pins ========================================================
log("== 0. identity pins ==")
pins: dict = {}
for name, p in [("prereg", PREREG_MD),
                ("row_index", T1_DIR / "row_index.parquet"),
                ("daily_calendar_pools", DAILY_CAL),
                ("daily_eval_panel", DAILY_EVAL),
                ("lib_p2r13_lowfreq",
                 ROOT / "src/quant/research/p2r13_lowfreq.py"),
                ("lib_p2r16_trend_dispersion",
                 ROOT / "src/quant/research/p2r16_trend_dispersion.py"),
                ("lib_factors_eval", ROOT / "src/quant/factors/eval.py"),
                ("script", Path(__file__).resolve())]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
    log(f"  {name}: {pins[name]['sha256'][:16]}")
# 65 个批文件：逐文件 sha 落清单文件，清单本身登记 manifest
batch_files = sorted(T1_DIR.glob("batch_*.jsonl"))
assert len(batch_files) == 65, f"expected 65 batch jsonl, got {len(batch_files)}"
listing_lines = [f"{sha256_file(bf)}  {bf.name}" for bf in batch_files]
(RUN_DIR / "tmp" / "t1_batch_sha256.txt").write_text(
    "\n".join(listing_lines) + "\n", encoding="utf-8", newline="\n")
pins["t1_batch_files"] = {
    "n_files": len(batch_files),
    "listing": str(RUN_DIR / "tmp" / "t1_batch_sha256.txt"),
    "listing_sha256": sha256_file(RUN_DIR / "tmp" / "t1_batch_sha256.txt")}
MANIFEST["pins"] = pins
write_manifest()

# === 1. merge annotations + row_index, dev filter (assertions) ==============
log("== 1. merge 65 jsonl + row_index; dev filter ==")
rows = []
for bf in batch_files:
    with bf.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
ann = pl.DataFrame(rows, schema_overrides={"supports_direction": pl.Int64})
log(f"  annotation rows: {ann.height}")
KEY = ["ts_code", "end_date", "ann_date", "update_flag"]
dup_ann = ann.group_by(KEY).len().filter(pl.col("len") > 1)
if dup_ann.height:
    stop(f"jsonl 连接键重复 {dup_ann.height} 组: {dup_ann.head(3).to_dicts()}")
ri = pl.read_parquet(T1_DIR / "row_index.parquet")
dup_ri = ri.group_by(KEY).len().filter(pl.col("len") > 1)
if dup_ri.height:
    stop(f"row_index 连接键重复 {dup_ri.height} 组")
merged = ri.join(ann, on=KEY, how="inner", validate="1:1")
if merged.height != ri.height:
    stop(f"连接后行数 {merged.height} != row_index 行数 {ri.height}"
         f"（unmatched {ri.height - merged.height}）")
merged.write_parquet(RUN_DIR / "tmp" / "annotations_merged.parquet")
MANIFEST["pins"]["annotations_merged"] = {
    "path": str(RUN_DIR / "tmp" / "annotations_merged.parquet"),
    "sha256": sha256_file(RUN_DIR / "tmp" / "annotations_merged.parquet")}
bad_sv = merged.filter(pl.col("struct_version") != "llm-v1").height
if bad_sv:
    stop(f"struct_version != llm-v1 行数 {bad_sv}")
# dev 窗过滤（断言之一：合并后）
dev = merged.filter((pl.col("ann_date") >= DEV_FIRST)
                    & (pl.col("ann_date") <= DEV_LAST))
if dev["ann_date"].max() > DEV_LAST:
    stop(f"dev 窗断言失败: max ann_date {dev['ann_date'].max()}")
n_dev = dev.height
log(f"  dev rows: {n_dev} ({DEV_FIRST}..{DEV_LAST}); non-dev excluded: "
    f"{merged.height - n_dev} (val/frozen never touched)")
MANIFEST["stage_a"] = {"rows_merged": merged.height, "rows_dev": n_dev,
                       "ann_date_min": dev["ann_date"].min(),
                       "ann_date_max": dev["ann_date"].max()}
stage("merge_dev")

# === 2. dedup (ts_code, end_date): max ann_date, then max update_flag ======
log("== 2. dedup + drop 不确定 ==")
n_before_dedup = dev.height
dedup = dev.sort(["ann_date", "update_flag"]).group_by(
    "ts_code", "end_date").last()
n_after_dedup = dedup.height
n_uncertain = dedup.filter(pl.col("type") == "不确定").height
ev = dedup.filter(pl.col("type") != "不确定")
log(f"  dedup: {n_before_dedup} -> {n_after_dedup} "
    f"(-{n_before_dedup - n_after_dedup}); 不确定 dropped: {n_uncertain}")
MANIFEST["stage_a"]["dedup"] = {
    "before": n_before_dedup, "after": n_after_dedup,
    "dropped_superseded": n_before_dedup - n_after_dedup,
    "dropped_uncertain": n_uncertain}
stage("dedup")

# === 3. R16 pool eligibility (event-day caliber) ============================
log("== 3. R16 pool eligibility (event-day) ==")
ev = ev.with_columns(
    pl.col("ts_code").map_elements(ts_to_symbol, return_dtype=pl.String)
    .alias("symbol"))
n_bad_sym = ev.filter(pl.col("symbol").is_null()).height
ev = ev.with_columns(pl.col("ann_date").str.to_date("%Y%m%d"),
                     pl.col("end_date").str.to_date("%Y%m%d"))
if ev["ann_date"].max() > DEV_LAST_D:  # 断言之二（池过滤前）
    stop(f"ann_date 断言失败(池过滤前): {ev['ann_date'].max()}")
syms = ev.filter(pl.col("symbol").is_not_null())["symbol"].unique().to_list()
bad_rt = [s for s in syms if ts_to_symbol(symbol_to_ts(s)) != s]
if bad_rt:
    stop(f"ts_code<->symbol 往返不一致: {bad_rt[:5]}")
log(f"  symbols: {len(syms)} unique; unconvertible ts_code rows: {n_bad_sym}")

cal = r16.market_calendar(DAILY_CAL)
cal_dates = sorted(cal["date"].to_list())
hist = r16.build_history_r16(DAILY_CAL, cal)
pool_rows = hist.select("symbol", "date", "listing_index", "isST").filter(
    p13.board_ok_expr())
del hist
# 输入面板一致性：1999 与 2015 文件 2015+ traded 行数一致（R16 DEVIATIONS-1 复核）
n_traded_99 = pl.scan_parquet(DAILY_CAL).filter(
    (pl.col("tradestatus") == 1.0) & (pl.col("date") >= date(2015, 1, 1))
).select(pl.len()).collect().item()
n_traded_15 = pl.scan_parquet(DAILY_EVAL).filter(
    (pl.col("tradestatus") == 1.0) & (pl.col("date") >= date(2015, 1, 1))
).select(pl.len()).collect().item()
if n_traded_99 != n_traded_15:
    stop(f"输入面板 2015+ traded 行数不一致: {n_traded_99} vs {n_traded_15}")
log(f"  panel identity ok: 2015+ traded rows {n_traded_15}")

funnel: dict = {"rows_after_dedup_and_type": ev.height,
                "unconvertible_ts_code": n_bad_sym}
board_ok_syms = sorted(
    pool_rows.select("symbol").unique()
    .filter(p13.board_ok_expr())["symbol"].to_list())
ev_board = ev.filter(pl.col("symbol").is_in(board_ok_syms))
funnel["board_excluded"] = ev.height - ev_board.height
ev_pool = ev_board.join(pool_rows, left_on=["symbol", "ann_date"],
                        right_on=["symbol", "date"], how="inner")
funnel["no_traded_row_on_ann_date"] = ev_board.height - ev_pool.height
closed = ev_board.filter(~pl.col("ann_date").is_in(cal_dates))
funnel["of_which_ann_date_not_market_session"] = closed.height
funnel["of_which_suspended_on_session"] = (
    funnel["no_traded_row_on_ann_date"] - closed.height)
n_before_list = ev_pool.height
ev_pool = ev_pool.filter(pl.col("listing_index") >= 60)
funnel["listing_lt60_sessions"] = n_before_list - ev_pool.height
n_before_st = ev_pool.height
ev_pool = ev_pool.filter(pl.col("isST") == 0.0)
funnel["is_st_at_event"] = n_before_st - ev_pool.height
funnel["pool_pass"] = ev_pool.height
if ev_pool["ann_date"].max() > DEV_LAST_D:  # 断言之二复核
    stop("2021+ 事件混入（池过滤后断言失败）-> 立即停")
type_counts = {t: int((ev_pool["type"] == t).sum()) for t in TYPE8}
funnel["type_counts_after_pool"] = type_counts
log(f"  funnel: {json.dumps(funnel, ensure_ascii=False)}")
# §2 样本量门槛
if ev_pool.height < GATE_MIN_TOTAL:
    stop(f"样本量门槛触发: 池过滤后总数 {ev_pool.height} < {GATE_MIN_TOTAL}")
small_types = {t: c for t, c in type_counts.items() if c < GATE_MIN_TYPE}
if small_types:
    stop(f"样本量门槛触发: 进检验 type <{GATE_MIN_TYPE}: {small_types}")
MANIFEST["pool_filter_counts"] = funnel
MANIFEST["panel_identity"] = {
    "traded_rows_2015plus": n_traded_15,
    "daily_1999_2024_sha256": pins["daily_calendar_pools"]["sha256"],
    "daily_2015_2024_sha256": pins["daily_eval_panel"]["sha256"]}
stage("pool_filter")

# === 4. own forward returns + TE-S2 =========================================
log("== 4. own forward returns (h=20 main; 5/10 sensitivity) ==")
panel_all = pl.read_parquet(DAILY_EVAL)
chain = panel_all.filter((pl.col("tradestatus").cast(pl.Int64) == 1)
                         & (pl.col("isST").cast(pl.Int64) == 0))
del panel_all
if chain["date"].max() > date(2024, 12, 31):
    stop(f"冻结区违例: 收益链日期 {chain['date'].max()}")
fwd = own_fwd(chain, (H_MAIN,) + H_SENS)
del chain
ev_ret = ev_pool.join(fwd, left_on=["symbol", "ann_date"],
                      right_on=["symbol", "date"], how="left")
n_no_fwd = ev_ret.filter(pl.col("fwd_h20").is_null()).height
log(f"  events without h20 forward window: {n_no_fwd}")

# TE-S2: harness 参照值（完整 2015-2024 面板进 harness，F2R1 EVAL_CFG 逐字；
# 窗口可自然溢出 2020-12-31 之后的交易日价格——面板本身止于 2024-12-31）
log("== 4b. TE-S2 harness cross-check (3 stocks x 3 events, tol 1e-9) ==")
panel_h = pl.read_parquet(DAILY_EVAL)
_validate_panel(panel_h)
ready = _prepare_panel(panel_h, EVAL_CFG)
harness_grid = _forward_return_grid(ready, EVAL_CFG.horizon_days)
del ready, panel_h
main_events = (ev_ret.filter(pl.col("fwd_h20").is_not_null())
               .filter(pl.col("primary_code").is_not_null())
               .sort("symbol", "ann_date"))
# 可对照键：分析样本 ∩ harness 网格（universe 差异=min_history_rows=60 截断，
# 属 universe 差异而非数值差异，披露）
both = main_events.join(
    harness_grid.select(pl.col("symbol"),
                        pl.col("date").alias("ann_date"), "fwd_ret"),
    on=["symbol", "ann_date"], how="inner")
n_harness_missing = main_events.height - both.height
gdiff = (both.with_columns((pl.col("fwd_h20") - pl.col("fwd_ret"))
                           .abs().alias("_d")))
gmax = float(gdiff["_d"].max()) if gdiff.height else float("nan")
g_bad = int((gdiff["_d"] > 1e-9).sum())
log(f"  harness-comparable keys: {both.height}/{main_events.height} "
    f"(missing {n_harness_missing}, universe truncation); global max|diff| "
    f"{gmax:.3e}; keys>1e-9: {g_bad}")
# 确定性抽样：可对照键内 3 股 x 3 事件。先筛出可对照事件 >=3 的股票集合
# （两次试运行表明字典序首/尾股可对照事件可 <3，属抽样机械规则问题、非
# 语义失败——全局 6,655 键 max|diff|=0），再取其首/中/尾；每股事件取等距
# 首/中/尾。全程确定性，无 RNG。
both_small = both.select("symbol", "ann_date", "fwd_h20", "fwd_ret")
n_map = {r["symbol"]: r["len"]
         for r in both_small.group_by("symbol").len().iter_rows(named=True)}
cmp_syms = sorted(s for s, n in n_map.items() if n >= 3)
if len(cmp_syms) < 3:
    stop(f"TE-S2: 可对照事件 >=3 的股票数 {len(cmp_syms)} < 3")
pick_syms = [cmp_syms[0], cmp_syms[len(cmp_syms) // 2], cmp_syms[-1]]
if len(set(pick_syms)) < 3:
    stop(f"TE-S2: 抽样股去重后 <3: {pick_syms}")
te_rows = []
for s in pick_syms:
    ds = sorted(both_small.filter(pl.col("symbol") == s)["ann_date"]
                .to_list())
    for d in (ds[0], ds[len(ds) // 2], ds[-1]):
        r = (both_small.filter((pl.col("symbol") == s)
                               & (pl.col("ann_date") == d))
             .head(1).iter_rows(named=True).__next__())
        te_rows.append({"symbol": s, "event_date": str(d),
                        "own": float(r["fwd_h20"]),
                        "harness": float(r["fwd_ret"]),
                        "abs_diff": abs(float(r["fwd_h20"])
                                        - float(r["fwd_ret"]))})
max_diff = max(r["abs_diff"] for r in te_rows)
log(f"  TE-S2 sampled {len(te_rows)} pairs on {pick_syms}: "
    f"max|diff| {max_diff:.3e}")
MANIFEST["te_s2"] = {
    "tolerance": 1e-9, "sampled_pairs": te_rows, "n_pairs": len(te_rows),
    "max_abs_diff_sampled": max_diff,
    "global_checked_keys": both.height,
    "global_missing_in_harness": n_harness_missing,
    "global_max_abs_diff": gmax, "global_keys_gt_tol": g_bad,
    "harness_cfg": EVAL_CFG.canonical(),
    "note": "harness 参照 = F2R1 EVAL_CFG 逐字；min_history_rows=60 使部分"
            "上市较晚键不在 harness 网格（universe 截断，披露，非数值差异）"}
if max_diff > 1e-9 or g_bad > 0:
    stop(f"TE-S2 对不上 harness: sampled max|diff| {max_diff:.3e}, "
         f"global keys>1e-9 {g_bad}")
log(f"  TE-S2 PASS")
stage("fwd_returns")

# === 5. month FE + type baseline (sanity direction) =========================
log("== 5. month FE + type baseline ==")
ana = main_events.with_columns(
    pl.col("ann_date").dt.strftime("%Y-%m").alias("month"))
ana = ana.with_columns(
    (pl.col("fwd_h20") - pl.col("fwd_h20").mean().over("month"))
    .alias("adj_h20"))
if ana["adj_h20"].null_count():
    stop("月份固定效应出现缺失（不应发生）")
n_primary_null = ev_ret.filter(
    pl.col("fwd_h20").is_not_null() & pl.col("primary_code").is_null()).height
bad_vocab = sorted(set(ana["primary_code"].unique().to_list())
                   - set(VOCAB15))
if bad_vocab:
    stop(f"primary_code 超出 15 类封闭词表: {bad_vocab}")
drift = (ana.group_by("type")
         .agg(n=pl.len(), mean_raw_h20=pl.col("fwd_h20").mean(),
              mean_adj_h20=pl.col("adj_h20").mean(),
              sd_raw_h20=pl.col("fwd_h20").std())
         .sort("type"))
drift.write_csv(RUN_DIR / "outputs" / "type_drift.csv")
good_adj = float(ana.filter(pl.col("type") == "预增")["adj_h20"].mean())
loss_adj = float(ana.filter(pl.col("type").is_in(LOSS_TYPES))["adj_h20"]
                 .mean())
good_raw = float(ana.filter(pl.col("type") == "预增")["fwd_h20"].mean())
loss_raw = float(ana.filter(pl.col("type").is_in(LOSS_TYPES))["fwd_h20"]
                 .mean())
sanity = {"definition": "预增 vs 预亏组(=首亏+续亏，操作化披露)；只验证不判定",
          "mean_adj_prezeng": good_adj, "mean_adj_loss": loss_adj,
          "mean_raw_prezeng": good_raw, "mean_raw_loss": loss_raw,
          "direction_ok_adj": good_adj > loss_adj,
          "direction_ok_raw": good_raw > loss_raw}
log(f"  sanity: 预增 {good_adj:+.5f} vs 预亏组 {loss_adj:+.5f} (adj) "
    f"-> direction_ok={sanity['direction_ok_adj']}")
MANIFEST["sanity"] = sanity
MANIFEST["analysis_sample"] = {
    "n": ana.height, "n_no_fwd_h20": n_no_fwd,
    "n_primary_code_null": n_primary_null,
    "n_months": ana["month"].n_unique()}
stage("baseline")

# === 6. main test: within-type demean -> primary_code ANOVA ================
log("== 6. main ANOVA (within-type demeaned primary_code classes) ==")
ana = ana.with_columns(
    (pl.col("adj_h20") - pl.col("adj_h20").mean().over("type")).alias("y_wd"))
ana_g, groups, merged_classes = build_groups(ana)
if len(groups) < 2:
    stop(f"并组后类别数 {len(groups)} < 2 -> 停机呈报")
vals = ana_g["y_wd"].to_numpy().astype(float)
grp = ana_g["group"].to_numpy()
res = anova_f(vals, grp)
main_p = res["p"]
main_verdict = verdict_of(main_p)
log(f"  groups {groups}; merged-into-other {merged_classes}")
log(f"  ANOVA F={res['F']:.4f} df=({res['df1']},{res['df2']}) "
    f"p={main_p:.6f} eta2={res['eta_squared']:.5f} -> {main_verdict}")
anova_main = {
    "judgment_line": "prereg §5.1: p<0.05 -> H1; [0.05,0.20) -> 边缘呈用户; "
                     ">=0.20 -> H0",
    "caliber": f"月份固定效应(adj_h20)上 type 组内去均值(y_wd)后 primary_code "
               f"类别间 ANOVA; 类别门槛 n>={MIN_CLASS_N}, 不足并入 other",
    **res, "groups": groups, "merged_into_other": merged_classes,
    "verdict": main_verdict}
(RUN_DIR / "outputs" / "anova_main.json").write_text(
    json.dumps(anova_main, ensure_ascii=False, indent=1),
    encoding="utf-8", newline="\n")
MANIFEST["decision"] = {"anova_F": res["F"], "anova_p": main_p,
                        "df": [res["df1"], res["df2"]], "k_groups": res["k"],
                        "n": res["n"], "eta_squared": res["eta_squared"],
                        "verdict": main_verdict}
stage("main_anova")

# === 6b. category-level report: class vs rest Welch t + BH =================
log("== 6b. category-level Welch t + BH ==")
mat_rows = list(
    ana_g.group_by("type", "group")
    .agg(n=pl.len(), mean_raw=pl.col("fwd_h20").mean(),
         mean_adj=pl.col("adj_h20").mean(), mean_ywd=pl.col("y_wd").mean())
    .sort("type", "group").iter_rows(named=True))
# 类别级检验：group!='other' 的保留类（other=残差桶含并入小类，不进两两比较，
# 披露）
tested_classes = [g for g in groups if g != "other"]
welch: dict[str, dict] = {}
for c in tested_classes:
    a = ana_g.filter(pl.col("group") == c)["y_wd"].to_numpy().astype(float)
    b = ana_g.filter(pl.col("group") != c)["y_wd"].to_numpy().astype(float)
    tw = scipy.stats.ttest_ind(a, b, equal_var=False)
    welch[c] = {"n_class": int(a.size),
                "mean_diff_vs_rest": float(a.mean() - b.mean()),
                "t": float(tw.statistic), "p": float(tw.pvalue)}
adj_ps = bh_adjust([welch[c]["p"] for c in tested_classes])
for c, pa in zip(tested_classes, adj_ps):
    welch[c]["p_bh"] = pa
log("  " + "; ".join(f"{c}: t={welch[c]['t']:+.2f} p={welch[c]['p']:.4g} "
                     f"p_bh={welch[c]['p_bh']:.4g}" for c in tested_classes))
mrows = []
for r in mat_rows:
    w = welch.get(r["group"]) if r["group"] != "other" else None
    mrows.append({"type": r["type"], "primary_code": r["group"],
                  "n": r["n"], "mean_raw_h20": r["mean_raw"],
                  "mean_adj_h20": r["mean_adj"], "mean_y_wd": r["mean_ywd"],
                  "class_n": w["n_class"] if w else None,
                  "class_mean_diff_vs_rest":
                      w["mean_diff_vs_rest"] if w else None,
                  "class_t": w["t"] if w else None,
                  "class_p": w["p"] if w else None,
                  "class_p_bh": w["p_bh"] if w else None})
pl.DataFrame(mrows).write_csv(
    RUN_DIR / "outputs" / "primary_within_type.csv")
MANIFEST["category_tests"] = {c: welch[c] for c in tested_classes}
stage("category_tests")

# === 7. sensitivities + yearly consistency + concentration =================
log("== 7. sensitivities (3) + yearly + concentration ==")
sens_rows = []
# S1: 剔除 sd=-1 与 low 行后重跑
s1 = ana.filter((pl.col("supports_direction") != -1)
                & (pl.col("confidence") != "low"))
n_dropped_s1 = ana.height - s1.height
sens_rows.append(run_main_pipeline(s1, "fwd_h20", "S1_drop_sd-1_and_low"))
log(f"  S1: dropped {n_dropped_s1} rows -> p={sens_rows[-1]['p']:.6f} "
    f"({sens_rows[-1]['verdict']})")
# S2: h=5 / h=10 短窗
for h in H_SENS:
    col = f"fwd_h{h}"
    s2 = ana.filter(pl.col(col).is_not_null())
    sens_rows.append(run_main_pipeline(s2, col, f"S2_h{h}"))
    log(f"  S2 h={h}: n={sens_rows[-1]['n']} -> p={sens_rows[-1]['p']:.6f} "
        f"({sens_rows[-1]['verdict']})")
# S3: 不去重原始样本（dev + 剔不确定 + 池过滤，仅跳过去重步；披露）
dev_all = merged.filter((pl.col("ann_date") >= DEV_FIRST)
                        & (pl.col("ann_date") <= DEV_LAST))
dev_all = dev_all.filter(pl.col("type") != "不确定")
dev_all = dev_all.with_columns(
    pl.col("ts_code").map_elements(ts_to_symbol, return_dtype=pl.String)
    .alias("symbol"), pl.col("ann_date").str.to_date("%Y%m%d"))
dev_all = dev_all.filter(pl.col("symbol").is_in(board_ok_syms))
dev_all = dev_all.join(
    pool_rows.select(pl.col("symbol"),
                     pl.col("date").alias("ann_date"),
                     "listing_index", "isST"),
    on=["symbol", "ann_date"], how="inner")
dev_all = dev_all.filter((pl.col("listing_index") >= 60)
                         & (pl.col("isST") == 0.0)
                         & (pl.col("ann_date") <= DEV_LAST_D))
dev_all = dev_all.with_columns(
    pl.col("ann_date").dt.strftime("%Y-%m").alias("month"))
dev_all = dev_all.join(
    fwd.select(pl.col("symbol"), pl.col("date").alias("ann_date"),
               "fwd_h20"),
    on=["symbol", "ann_date"], how="left")
s3 = dev_all.filter(pl.col("fwd_h20").is_not_null()
                    & pl.col("primary_code").is_not_null())
if s3["ann_date"].max() > DEV_LAST_D:
    stop("2021+ 事件混入（S3 不去重样本断言失败）-> 立即停")
sens_rows.append(run_main_pipeline(s3, "fwd_h20", "S3_no_dedup"))
log(f"  S3: n={sens_rows[-1]['n']} (dedup main={ana.height}) -> "
    f"p={sens_rows[-1]['p']:.6f} ({sens_rows[-1]['verdict']})")
# 脆弱性（操作化披露）：主判定 H1 而任一敏感性判定不再成立 -> "脆弱"
flip = [r["variant"] for r in sens_rows
        if main_verdict == "H1" and r["verdict"] != "H1"]
fragile = main_verdict == "H1" and bool(flip)
MANIFEST["sensitivity"] = {
    "main": {"p": main_p, "verdict": main_verdict}, "fragile": fragile,
    "flips": flip,
    "operationalization": "方向翻转操作化=主判定结论(H1)在任一敏感性下不再"
                          "成立(p>=0.05)；F 检验无方向，附 eta_squared 对照",
    "rows": sens_rows}
pl.DataFrame([{k: r[k] for k in ("variant", "n", "k_groups", "F", "p",
                                 "verdict", "eta_squared", "groups",
                                 "merged_into_other")}
              for r in sens_rows]).write_csv(
    RUN_DIR / "outputs" / "sensitivity.csv")
log(f"  fragile={fragile} (flips: {flip})")

# 分年方向一致性（描述性）+ 集中度
seg_rows = []
for c in tested_classes:
    sub = ana_g.filter(pl.col("group") == c)
    row: dict = {"primary_code": c, "n": int(sub.height)}
    signs = []
    for seg_name, d0, d1 in YEARS_SEG:
        ssub = sub.filter((pl.col("ann_date") >= d0)
                          & (pl.col("ann_date") <= d1))
        m = float(ssub["adj_h20"].mean()) if ssub.height else None
        row[f"mean_adj_{seg_name}"] = m
        row[f"n_{seg_name}"] = ssub.height
        if m is not None:
            signs.append(1 if m > 0 else -1)
    row["sign_consistent_segments"] = (
        abs(sum(signs)) if len(signs) == len(YEARS_SEG) else None)
    seg_rows.append(row)
conc_rows = []
for c in tested_classes:
    sub = ana_g.filter(pl.col("group") == c)
    by_sym = (sub.group_by("symbol").agg(s=pl.col("fwd_h20").sum())
              .sort("s", descending=True))
    tot = float(by_sym["s"].sum())
    ss = by_sym["s"].to_list()
    conc_rows.append({"primary_code": c, "n_symbols": int(by_sym.height),
                      "sum_ret": tot,
                      "top1_share": (float(ss[0]) / tot) if tot > 0 else None,
                      "top3_share": (float(sum(ss[:3])) / tot)
                      if tot > 0 else None,
                      "top1_symbol": by_sym["symbol"][0]})
diag = pl.DataFrame(seg_rows).join(pl.DataFrame(conc_rows),
                                   on="primary_code", suffix="_conc")
diag.write_csv(RUN_DIR / "outputs" / "category_diagnostics.csv")
MANIFEST["concentration_top1"] = {r["primary_code"]: r["top1_share"]
                                  for r in conc_rows}
stage("sensitivity_diagnostics")

# === 8. events_dev.parquet + pool counts + manifest =========================
log("== 8. outputs + manifest ==")
out_cols = ["ordinal", "batch_id", "ts_code", "symbol", "end_date",
            "ann_date", "update_flag", "type", "primary_code",
            "secondary_code", "supports_direction", "confidence",
            "struct_version", "month", "listing_index", "fwd_h20", "fwd_h5",
            "fwd_h10", "wend_h20", "adj_h20", "y_wd", "group"]
ev_out = ana_g.select(out_cols)
assert ev_out["fwd_h20"].null_count() == 0
ev_out.write_parquet(RUN_DIR / "outputs" / "events_dev.parquet")
(RUN_DIR / "outputs" / "pool_filter_counts.json").write_text(
    json.dumps({"funnel": funnel, "type_counts_after_pool": type_counts,
                "gate": {"min_total": GATE_MIN_TOTAL,
                         "min_type": GATE_MIN_TYPE,
                         "total_pass": ev_pool.height >= GATE_MIN_TOTAL,
                         "types_pass": not small_types}},
               ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
MANIFEST["outputs"] = {
    name: sha256_file(RUN_DIR / "outputs" / name) for name in
    ("events_dev.parquet", "type_drift.csv", "primary_within_type.csv",
     "anova_main.json", "sensitivity.csv", "pool_filter_counts.json",
     "category_diagnostics.csv")}
# 首次尝试曾因 TE-S2 抽样机械规则停机（全局对照已 0 误差）；成功完成后该
# 停机报告已被本完成清单取代，删除以免与 manifest status=completed 矛盾
_sr = RUN_DIR / "tmp" / "stop_report.md"
if _sr.exists():
    _sr.unlink()
    log("  removed superseded tmp/stop_report.md from the aborted first "
        "attempt (sampling mechanics; recorded in run report)")
MANIFEST["results"] = {
    "main_p": main_p, "main_verdict": main_verdict,
    "max_event_date": str(ev_out["ann_date"].max()),
    "window_end_max": str(ev_out["wend_h20"].max()),
    "window_end_beyond_2021_02": int(
        ev_out.filter(pl.col("wend_h20") > date(2021, 2, 1)).height),
    "window_end_beyond_2022_01": int(
        ev_out.filter(pl.col("wend_h20") > date(2022, 1, 1)).height),
    "window_end_note": "h=20 为 own-session 交易日窗（harness 同式）：多数"
                       "事件窗口右端自然溢出到 2021-01-2x；长期停牌股"
                       "（约 0.6%）的 20 个交易日窗在日历上跨越数年，极端"
                       "至 window_end_max（冻结口径内的正常结果，量化披露）"}
MANIFEST["status"] = "completed"
write_manifest()
log(f"== complete: main p={main_p:.6f} ({main_verdict}); n={res['n']}; "
    f"wall {time.perf_counter() - T0:.0f}s, rss {PEAK_RSS:.2f} GB ==")
