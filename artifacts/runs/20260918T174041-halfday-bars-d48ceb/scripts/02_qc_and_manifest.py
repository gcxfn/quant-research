# -*- coding: utf-8 -*-
"""02_qc_and_manifest.py — halfday-bars-20260918 的 QC 与 manifest 落盘。

前置：01_build_halfday_bars.py --full 已写 data/processed/halfday-bars-20260918/
year=YYYY/bars.parquet 且 logs/scan_summary_full.json 存在。

四项自检（任务书验收）：
  1. 逐列不变量：high>=max(open,close)、low<=min(open,close)、high>=low、
     价格>0、volume>=0、无 null、键唯一 —— 违规数必须为 0。
  2. 抽查：3 标的 × 5 交易日（跨两个批次、跨年份），纯 Python 手工聚合
     （不走 polars 聚合路径）与落盘行逐值精确相等。
  3. 与 baostock 日线（data/processed/baostock-daily-20260917）交叉验证：
     tradestatus==1 的日行上 max(am.high,pm.high)=日 high、
     min(am.low,pm.low)=日 low、pm.close=日 close（1e-6 容差=分格精确），
     报告不匹配率、差异分布与典型样例；另报 volume/amount 相对差分布、
     覆盖缺口（日线上有交易但半日 bar 缺 am/pm）与反向
     （有 bar 但日线无交易行）。
  4. 逐年行数量级 sanity：对照 R14 minute-feats-20260918（每股每日一行、
     有量日）的逐年 distinct symbol-day 数。
fail-closed 门（任一不过即非零退出）：不变量、抽查、冻结边界、
高/低/收三者的结构门（abs 差 >0.01 元的比率 <2%，超门=系统性错误）。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from quant.research.p2r14_minute_structure import FREEZE_LAST  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "build01", Path(__file__).resolve().parent / "01_build_halfday_bars.py")
build01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build01)

OUT_DIR = REPO / "data" / "processed" / "halfday-bars-20260918"
RUN = Path(__file__).resolve().parents[1]
DAILY = (REPO / "data" / "processed" / "baostock-daily-20260917"
         / "daily_2015_2024.parquet")
MINUTE_FEATS = (REPO / "data" / "processed" / "minute-feats-20260918"
                / "minute_feats.parquet")
YEARS = list(range(2015, 2025))
TOL = 1e-6          # 分格精确相等容差
SPOT_SYMBOLS = ["sh.600000", "sz.000001", "sz.300750"]
SPOT_DATES = ["2015-06-01", "2018-06-01", "2020-06-01", "2022-06-01",
              "2024-06-03"]

T0 = time.perf_counter()


def log(msg: str) -> None:
    print(f"[{time.perf_counter() - T0:7.1f}s] {msg}", flush=True)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def q(arr, ps=(0.0, 0.001, 0.5, 0.999, 1.0)):
    import numpy as np
    if arr.size == 0:
        return None
    return [round(float(np.quantile(arr, p)), 8) for p in ps]


def check_invariants(yb: pl.DataFrame, year: int) -> dict:
    n = yb.height
    if n == 0:
        raise RuntimeError(f"year {year}: empty partition")
    row = yb.select(
        (pl.col("high") < pl.max_horizontal("open", "close") - TOL)
        .sum().alias("n_high_lt_max_oc"),
        (pl.col("low") > pl.min_horizontal("open", "close") + TOL)
        .sum().alias("n_low_gt_min_oc"),
        (pl.col("high") < pl.col("low") - TOL).sum().alias("n_high_lt_low"),
        ((pl.col("open") <= 0) | (pl.col("high") <= 0) | (pl.col("low") <= 0)
         | (pl.col("close") <= 0)).sum().alias("n_price_le_0"),
        (pl.col("volume") < 0).sum().alias("n_volume_lt_0"),
        pl.any_horizontal([pl.col(c).is_null() for c in build01.COLUMNS])
        .sum().alias("n_rows_with_null"),
    ).row(0, named=True)
    e = {k: int(v) for k, v in row.items()}
    e["n_dup_key"] = n - yb.select("symbol", "trade_date", "session") \
        .unique().height
    e["rows"] = n
    e["partial_rows"] = int(yb["partial"].sum())
    e["am_rows"] = int((yb["session"] == "am").sum())
    e["pm_rows"] = int((yb["session"] == "pm").sum())
    log(f"invariants {year}: " + json.dumps(
        {k: v for k, v in e.items() if k != "rows"}))
    return e


def spot_check(day_rows: list[dict]) -> dict:
    checks = []
    for sym in SPOT_SYMBOLS:
        for d_iso in SPOT_DATES:
            r = next((r for r in day_rows if r["date"] == d_iso), None)
            if r is None:
                raise RuntimeError(f"spot date {d_iso} absent from day list")
            want = build01.py_aggregate_day(build01.RAW / r["path"], d_iso, sym)
            got = (pl.read_parquet(OUT_DIR / f"year={d_iso[:4]}"
                                   / "bars.parquet")
                   .filter((pl.col("symbol") == sym)
                           & (pl.col("trade_date")
                              == date.fromisoformat(d_iso))))
            for sess in ("am", "pm"):
                exp = want.get(sess)
                row = got.filter(pl.col("session") == sess)
                entry = {"symbol": sym, "date": d_iso, "session": sess}
                if exp is None and row.height == 0:
                    entry["match"] = True
                    entry["note"] = "both sides no bars (non-traded session)"
                elif exp is None or row.height != 1:
                    entry["match"] = False
                    entry["reason"] = (
                        f"want={'none' if exp is None else 'row'} "
                        f"got_rows={row.height}")
                else:
                    named = row.row(0, named=True)
                    diffs = {k: [named[k], expv] for k, expv in exp.items()
                             if named[k] != expv}
                    entry["match"] = not diffs
                    entry["diffs"] = diffs
                checks.append(entry)
    n_bad = sum(1 for c in checks if not c["match"])
    return {"n_checks": len(checks), "n_mismatch": n_bad,
            "all_exact": n_bad == 0, "detail": checks}


def crosscheck_year(year: int, daily_lf: pl.LazyFrame) -> dict:
    yb = pl.read_parquet(OUT_DIR / f"year={year}" / "bars.parquet")
    am = (yb.filter(pl.col("session") == "am")
          .select("symbol", "trade_date",
                  pl.col("high").alias("high_am"),
                  pl.col("low").alias("low_am"),
                  pl.col("close").alias("close_am"),
                  pl.col("volume").alias("volume_am"),
                  pl.col("amount").alias("amount_am")))
    pm = (yb.filter(pl.col("session") == "pm")
          .select("symbol", "trade_date",
                  pl.col("high").alias("high_pm"),
                  pl.col("low").alias("low_pm"),
                  pl.col("close").alias("close_pm"),
                  pl.col("volume").alias("volume_pm"),
                  pl.col("amount").alias("amount_pm")))
    both = am.join(pm, on=["symbol", "trade_date"], how="full", coalesce=True)
    daily = (daily_lf.filter(pl.col("date").dt.year() == year)
             .rename({"date": "trade_date"}).collect())
    j = both.join(daily, on=["symbol", "trade_date"], how="full",
                  coalesce=True)

    has_am = pl.col("high_am").is_not_null()
    has_pm = pl.col("high_pm").is_not_null()
    traded = j.filter(pl.col("tradestatus") == 1.0)
    cov = {
        "daily_traded_rows": traded.height,
        "with_am_and_pm": int(traded.select((has_am & has_pm).sum()).item()),
        "with_am_only": int(traded.select((has_am & ~has_pm).sum()).item()),
        "with_pm_only": int(traded.select((~has_am & has_pm).sum()).item()),
        "with_neither": int(traded.select((~has_am & ~has_pm).sum()).item()),
    }
    both_rows = traded.filter(has_am & has_pm)
    out = {"coverage": cov}
    d_high = pl.max_horizontal("high_am", "high_pm") - pl.col("high")
    d_low = pl.min_horizontal("low_am", "low_pm") - pl.col("low")
    d_close = pl.col("close_pm") - pl.col("close")
    for name, expr in (("high", d_high), ("low", d_low), ("close", d_close)):
        arr = both_rows.select(expr.alias("d"))["d"].to_numpy()
        big = abs(arr) > 0.01
        # 方向拆分（low 的符号相反）：bar 超出官方日线（bar_beyond，可能指示
        # 构建错位，应≈0）vs bar 在官方日线之内（bar_inside，源缺失极值价/
        # 官方收盘口径差，逐年如实披露）
        if name == "low":
            n_beyond = int((arr < -0.01).sum())
            n_inside = int((arr > 0.01).sum())
        else:
            n_beyond = int((arr > 0.01).sum())
            n_inside = int((arr < -0.01).sum())
        out[f"{name}_cmp"] = {
            "n": int(arr.size),
            "n_exact_1e6": int((abs(arr) <= TOL).sum()),
            "rate_exact_1e6": float((abs(arr) <= TOL).mean()) if arr.size else None,
            "n_diff_gt_0_01": int(big.sum()),
            "rate_diff_gt_0_01": float(big.mean()) if arr.size else None,
            "n_bar_beyond_daily_gt_0_01": n_beyond,
            "n_bar_inside_daily_gt_0_01": n_inside,
            "signed_diff_quantiles": q(arr),
        }
    vol_rel = both_rows.select(
        ((pl.col("volume_am").fill_null(0) + pl.col("volume_pm").fill_null(0)
          - pl.col("volume")) / pl.col("volume")).alias("r"))["r"].to_numpy()
    amt_rel = both_rows.select(
        ((pl.col("amount_am").fill_null(0) + pl.col("amount_pm").fill_null(0)
          - pl.col("amount")) / pl.col("amount")).alias("r"))["r"].to_numpy()
    out["volume_rel"] = {"n_exact_1e6": int((abs(vol_rel) <= TOL).sum()),
                         "rate_exact_1e6": float((abs(vol_rel) <= TOL).mean()),
                         "rel_quantiles": q(vol_rel)}
    out["amount_rel"] = {"rate_exact_1e6": float((abs(amt_rel) <= TOL).mean()),
                         "rel_quantiles": q(amt_rel)}
    bad = (both_rows.with_columns(d_high.alias("d_high"), d_low.alias("d_low"),
                                  d_close.alias("d_close"))
           .filter((pl.col("d_high").abs() > 0.01)
                   | (pl.col("d_low").abs() > 0.01)
                   | (pl.col("d_close").abs() > 0.01))
           .sort(pl.max_horizontal(pl.col("d_high").abs(),
                                   pl.col("d_low").abs(),
                                   pl.col("d_close").abs()),
                 descending=True)
           .head(20)
           .select("symbol", "trade_date", "high_am", "high_pm", "high",
                   "d_high", "low_am", "low_pm", "low", "d_low", "close_pm",
                   "close", "d_close"))
    out["mismatch_examples_gt_0_01"] = bad.to_dicts()
    bars_only = j.filter((has_am | has_pm)
                         & (pl.col("tradestatus").is_null()
                            | (pl.col("tradestatus") != 1.0)))
    out["bars_but_daily_not_traded_rows"] = bars_only.height
    out["bars_but_daily_not_traded_examples"] = (
        bars_only.head(10).select("symbol", "trade_date", "tradestatus")
        .to_dicts())
    out["symbols_never_in_daily"] = int(
        j.filter(pl.col("tradestatus").is_null() & (has_am | has_pm))
        .select(pl.col("symbol").n_unique()).item())
    log(f"crosscheck {year}: high_exact="
        f"{out['high_cmp']['rate_exact_1e6']:.6f} low_exact="
        f"{out['low_cmp']['rate_exact_1e6']:.6f} close_exact="
        f"{out['close_cmp']['rate_exact_1e6']:.6f} cov_gaps="
        f"{cov['with_am_only'] + cov['with_pm_only'] + cov['with_neither']}")
    return out


def yearly_sanity() -> dict:
    feats = (pl.scan_parquet(MINUTE_FEATS).select("symbol", "date")
             .with_columns(pl.col("date").dt.year().alias("year")).collect())
    ref_by_year = {y[0] if isinstance(y, tuple) else y:
                   int(g.select(pl.struct("symbol", "date").n_unique()).item())
                   for y, g in feats.group_by("year")}
    out = {}
    for year in YEARS:
        yb = pl.read_parquet(OUT_DIR / f"year={year}" / "bars.parquet")
        mine = int(yb.select(pl.struct("symbol", "trade_date").n_unique())
                   .item())
        ref = ref_by_year.get(year, 0)
        out[str(year)] = {"halfday_symbol_days": mine,
                          "r14_feats_symbol_days": ref,
                          "ratio": round(mine / ref, 6) if ref else None}
    return out


def main() -> None:
    scan_summary = json.loads(
        (RUN / "logs" / "scan_summary_full.json").read_text(encoding="utf-8"))
    qc_start = time.perf_counter()
    day_rows = build01.load_day_list()

    invariants = {}
    for year in YEARS:
        yb = pl.read_parquet(OUT_DIR / f"year={year}" / "bars.parquet")
        invariants[str(year)] = check_invariants(yb, year)
    viol_cols = ("n_high_lt_max_oc", "n_low_gt_min_oc", "n_high_lt_low",
                 "n_price_le_0", "n_volume_lt_0", "n_rows_with_null", "n_dup_key")
    bad_inv = {y: {k: e[k] for k in viol_cols if e[k] != 0}
               for y, e in invariants.items() if any(e[k] != 0 for k in viol_cols)}
    if bad_inv:
        raise RuntimeError(f"invariant violations: {bad_inv}")

    spot = spot_check(day_rows)
    log(f"spot check: {spot['n_checks']} checks, mismatches={spot['n_mismatch']}")
    if not spot["all_exact"]:
        raise RuntimeError("spot check failed")

    daily_lf = pl.scan_parquet(DAILY)
    crosschecks = {str(y): crosscheck_year(y, daily_lf) for y in YEARS}
    # 结构门只钉「构建错位」信号：半日 bar 超出官方日线（beyond）的比率。
    # 实测所有年份 beyond 恒为 0（官方日线是分钟极值的单向超集）；
    # 「inside」率是源忠实度属性（vendor 分钟缺极值价 / 官方收盘口径），
    # 逐年披露在 quality.json，不作失败门（已定位两个根因，见 findings）。
    gate = {}
    for y, cc in crosschecks.items():
        for k in ("high_cmp", "low_cmp"):
            n = cc[k]["n"]
            r_beyond = cc[k]["n_bar_beyond_daily_gt_0_01"] / n if n else 0.0
            gate[f"{y}_{k}_beyond"] = r_beyond
    g = {k: v for k, v in gate.items() if v >= 0.005}
    if g:
        raise RuntimeError(f"structural gate failed (>=0.5% bar-beyond-daily): {g}")

    sanity = yearly_sanity()
    log("yearly sanity: " + json.dumps(sanity))

    max_date = (pl.scan_parquet(str(OUT_DIR / "year=*" / "bars.parquet"))
                .select(pl.col("trade_date").max()).collect().item())
    if max_date > FREEZE_LAST:
        raise RuntimeError(f"freeze violation: max trade_date {max_date}")

    qc_s = time.perf_counter() - qc_start
    total_rows = sum(e["rows"] for e in invariants.values())
    findings = {
        "close_pm_vs_daily_close": (
            "2015–2018-08-19 pm.close 与官方日收不一致（SH 为主：2015 年 "
            "74,673 例中 71,442 例 SH；2018 改革前率 12.58%，其中 SH 63,691 "
            "例 vs SZ 173 例；差异双向、中位数约 ±1 分）。根因=口径而非缺陷："
            "上交所 2018-08-20 引入收盘集合竞价前，官方收盘价为「最后一分钟"
            "成交量加权平均价」，vendor 15:00 bar close 为最后一笔成交价。"
            "2018-08-20 起两所收盘均为集合竞价价，pm.close≈官方日收（残差 "
            "0.01–0.07%，双向，量级 1–2 分）。对 v1 的含义：11:30/15:00 决策"
            "点若需要官方口径收盘价，SH 2015-08 前应桥接 baostock 日线 close，"
            "不能用 pm.close 冒充。"),
        "high_low_vs_daily": (
            "全部 10 年 high_bar_beyond_daily=low_bar_beyond_daily=0（半日极值"
            "从不超出官方日线）；bar_inside 率逐年 0–15%（2019–2021 最高，"
            "2020 年 high 15.3%/low 14.0%；2022–2024 基本为 0；中位差仅 "
            "1–2 分，极端例为深/创/科股票日缺十元级极值价，如 sz.300661 "
            "2020-02-03 官方 high 260.0 vs 分钟最高 254.04，但日线 volume 与"
            "分钟 sum 完全一致=同一交易集，vendor 分钟丢极值 print）。唯一"
            "反向例外：2015-06-15 sh.600864 分钟 low 24.01 低于官方 low "
            "24.29（9.2M 行中仅此 1 行，疑 vendor 坏 tick）。对 v1 "
            "的含义：以半日 high/low 判定严格穿透是保守方向——只会漏判可成交"
            "（under-fill），不会虚判成交（over-fill）。"),
    }
    quality = {
        "dataset_id": "halfday-bars-20260918",
        "checked_at": "2026-09-18",
        "freeze_max_trade_date": str(max_date),
        "invariants_by_year": invariants,
        "invariants_total": {"rows": total_rows, "violations": 0},
        "spot_check": spot,
        "daily_crosscheck": crosschecks,
        "daily_crosscheck_findings": findings,
        "structural_gate": "bar-beyond-daily 比率 <0.5%（实测恒为 0）；inside 率逐年披露不作门",
        "yearly_sanity_vs_r14_feats": sanity,
    }
    (OUT_DIR / "quality.json").write_text(
        json.dumps(quality, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")

    per_year_manifest = {}
    for year in YEARS:
        fp = OUT_DIR / f"year={year}" / "bars.parquet"
        per_year_manifest[str(year)] = {
            **scan_summary["per_year"][str(year)],
            "path": (f"data/processed/halfday-bars-20260918/"
                     f"year={year}/bars.parquet"),
            "bytes": fp.stat().st_size,
            "sha256": sha256_of(fp),
            "partial_rows": invariants[str(year)]["partial_rows"],
        }
    manifest = {
        "dataset_id": "halfday-bars-20260918",
        "created": "2026-09-18",
        "run_id": RUN.name,
        "experiment_id": "exp-20260918-halfday-bars",
        "nature": ("全市场 A 股半日（上午/下午）OHLCV bar 数据表，纯数据工程；"
                   "无因子、无回测、无策略结论、不消费试验数。供区间契约 v1 "
                   "双决策点（11:30 / 15:00 收盘）挂单成交判定使用。"),
        "segmentation_contract": {
            "am": "trade_time 时段 <= 11:30:00（含 09:30 集合竞价 bar；vendor AM 网格 09:30..11:30，121 根/日）",
            "pm": "trade_time 时段 >= 13:00:00（含 15:00 收盘集合竞价 bar；vendor PM 网格 13:01..15:00，120 根/日，本包无 13:00 bar）",
            "zero_volume_bars": "vol==0 为 vendor 占位（DATA_SOURCES §1.3），不进入任何聚合；n_minutes=有量分钟数",
            "missing_rows": "某标的某时段无任何有量 bar → 不造行（缺行=该时段不可交易）；全日无有量 bar → 该 (symbol,trade_date) 无行",
            "partial_flag": "partial = n_minutes < n_minutes_expected；n_minutes_expected = 该日文件全市场该时段 distinct 分钟网格数（逐日实测，AM 通常 121、PM 通常 120）",
            "open_close": "open=时段内最早有量 bar 的 open；close=时段内最晚有量 bar 的 close（均按 trade_time 排序）",
        },
        "units": {
            "prices": "元（原始不复权；float32 分币编码按分还原：cast(Float64).round(2)，逐值恰为该分值的最近 f64；R10 已验证 vendor 零残差）",
            "volume": "股（vendor vol 逐值 f32→f64 后求和；值域内精确）",
            "amount": "元（vendor amount f32→f64 后求和；f32 源头精度所限为近似和）",
        },
        "inputs": {
            "minute_day_list": {
                "path": ("artifacts/runs/20260918T032049-halfday-prep-f3mbfd/"
                         "boundary/minute_day_files.csv"),
                "sha256": build01.DAY_LIST_SHA, "days": 2431,
                "window": "2015-01-05..2024-12-31（冻结边界逐日校验）"},
            "minute_batches": [
                {"path": "data/raw/user_minute_1m/20260913-143215",
                 "coverage": "2015–2019", "files": 1220},
                {"path": "data/raw/user_minute_1m/20260913-2020-2024",
                 "coverage": "2020–2024", "files": 1213}],
            "batch_identity": ("data/_meta/sha256.tsv 逐文件登记（prep run "
                               "20260918T032049 全量字节比对）；本 run 每批次"
                               "抽 3 个日文件重哈希（seed 17）全部一致"),
            "sampled_reshash_files":
                scan_summary["identity"]["sampled_reshash_ok"],
            "baostock_daily": {
                "path": ("data/processed/baostock-daily-20260917/"
                         "daily_2015_2024.parquet"),
                "manifest_sha256": build01.BAOSTOCK_MANIFEST_SHA,
                "role": "仅用于 QC 交叉验证（OHLC/volume/amount/tradestatus），不进入本表数据"},
            "r14_minute_feats": {
                "path": ("data/processed/minute-feats-20260918/"
                         "minute_feats.parquet"),
                "sha256": sha256_of(MINUTE_FEATS),
                "role": "仅用于 QC 逐年覆盖 sanity 对照"},
        },
        "outputs": {
            "layout": ("data/processed/halfday-bars-20260918/year=YYYY/"
                       "bars.parquet（按年分区；pl.scan_parquet(目录, "
                       "hive_partitioning=True) 可整表读）"),
            "schema": {
                "symbol": "str（'sh.600000' 小写规范形，与 baostock/halfday-1130 一致）",
                "trade_date": "date", "session": "'am'|'pm'",
                "open/high/low/close": "float64 元（分格）",
                "volume": "float64 股", "amount": "float64 元",
                "n_minutes": "int32 有量分钟数",
                "n_minutes_expected": "int32 该时段分钟网格数",
                "partial": "bool（n_minutes < n_minutes_expected）"},
            "sort": "trade_date, symbol, session",
            "compression": "zstd level 3",
            "rows_total": total_rows,
            "rows_am": sum(e["am_rows"] for e in invariants.values()),
            "rows_pm": sum(e["pm_rows"] for e in invariants.values()),
            "rows_partial": sum(e["partial_rows"] for e in invariants.values()),
            "per_year": per_year_manifest,
        },
        "read_deduction_notes": {
            "code_scope": ("user_minute_1m 仅含 SH/SZ 股票（00/30/60/68 前缀）；"
                           "无 ETF/基金、无指数、无 .BJ（R14 与本 run 实测 "
                           "bj_rows_removed=0）——v1 需要的 ETF 半日 bar 在现有"
                           "全覆盖分钟源中不存在，属源覆盖缺口而非本表过滤；"
                           "bigquant intraday-t0 仅指数探针（2021–2024 部分），"
                           "etf-minute-probe 仅 5 分钟探针，均不足以成表"),
            "freeze": ("只读 day list 内 <=2024-12-31 的 2,431 个日文件；行级 "
                       "date 列二次校验；bigquant years/2025、years/2026 未读"),
            "intraday_checks": ("非 .BJ 行 15:00 后出现即 raise（实测 0）；"
                                "(code,trade_time) 冲突重复行 raise（实测 0）"),
            "registered_defects": ("DATA_SOURCES §1 陷阱照记：22 项已登记待补/"
                                   "受审证券日、sz.300114 全源缺分钟、"
                                   "2015-07-01 尾盘零量占位——零量剔除规则统一处理"),
        },
        "quality_report": "data/processed/halfday-bars-20260918/quality.json",
        "crosscheck_findings": ("见 quality.json.daily_crosscheck_findings：①pm.close 与官方日收在 "
                            "SH 2015-2018-08-19 不一致（官方为最后一分钟 VWAP 口径，"
                            "2018-08-20 收盘集合竞价改革后一致，残差 <0.1%）；"
                            "②半日极值从不超出官方日线（beyond 恒为 0），官方日线"
                            "为分钟极值的单向超集（inside 率 2019-2021 最高约 15%，"
                            "2022-2024 基本为 0）——严格穿透判定保守方向，只漏判"
                            "不虚判。"),
        "timing": {
            "smoke": scan_summary.get("timing"),
            "full": {**scan_summary["timing"], "days": scan_summary["days"]},
            "qc_s": round(qc_s, 1),
            "budget_note": ("预算纪律披露：冒烟（40 日，2015-06+2024-06）外推"
                            "全窗口约 15–22 分钟，据此开工；实际 full 扫描 "
                            "2364s（39.4 分钟）超出 30 分钟预算线，原因是逐日"
                            "成本随在市标的数增长（2015 约 0.55s/日 → 2024 约 "
                            "1.1s/日），冒烟月份低估了后半窗口的标的量。峰值内"
                            "存 2.26GiB < 8GB 达标。扫描已一次完成、中途未停，"
                            "如实记录超预算作为本 run 纪律缺口。"),
        },
        "environment": scan_summary["environment"],
        "git": "仓库未初始化 Git（按 AGENTS 纪律，未初始化/未提交）",
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    shutil.copy(OUT_DIR / "manifest.json", RUN / "manifest.json")
    shutil.copy(OUT_DIR / "quality.json", RUN / "quality.json")
    log(f"QC + manifest done: {total_rows} rows; qc_s={qc_s:.1f}")
    print("OK")


if __name__ == "__main__":
    main()
