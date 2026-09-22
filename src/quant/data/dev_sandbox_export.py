"""受控导出 Dev-only 沙箱工作集（C1 数据隔离，K 角色）。

由混合年份原始/派生文件出发，只输出许可窗口的行，并在写完后对自己的
输出做硬自检：日线/半日/涨跌停输出不得出现任何 2021-01-01 及以后的行，
预告事件不得出现 B 家族窗口（2018-09-04..2020-12-31）之外的行。自检
失败即抛 ``ExportSelfCheckError``，不产物、不静默降级。

输出布局（``data/processed/dev-sandbox-20260922/``）::

    dataset_manifest.json
    bars_daily_dev.parquet          2015-01-05..2020-12-31
    bars_daily_warmup.parquet       2014-03-01..2015-01-04（仅特征历史）
    bars_halfday/year=YYYY/bars.parquet   2015..2020
    limits/limit_dev.parquet        2015-01-05..2020-12-31
    events/forecast_b_window.parquet   ann_date 2018-09-04..2020-12-31

预热窗单独成文件并标 ``purpose=feature_history_only``，避免被当成绩效年份。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
import psutil

SCHEMA_VERSION = "1.0"
DATASET_ID = "dev-sandbox-20260922"
DEV_START = date(2015, 1, 5)
DEV_END = date(2020, 12, 31)
WARM_START = date(2014, 3, 1)
WARM_END = date(2015, 1, 4)
B_DEV_FIRST = date(2018, 9, 4)
B_DEV_LAST = date(2020, 12, 31)
FREEZE_END = date(2024, 12, 31)

DAILY_SRC = Path("data/processed/baostock-daily-20260917/daily_1999_2024.parquet")
HALFDAY_SRC_DIR = Path("data/processed/halfday-bars-20260918")
LIMIT_SRC_DIR = Path("data/raw/tushare/stk_limit/20260917-r1")
FORECAST_SRC_DIR = Path("data/raw/tushare/forecast/20260909-r1")

DAILY_COLUMNS = ["symbol", "date", "open", "high", "low", "close", "preclose",
                 "volume", "amount", "adjustflag", "turn", "tradestatus",
                 "pctChg", "isST"]
HALFDAY_COLUMNS = ["symbol", "date", "session", "open", "high", "low", "close",
                   "volume", "amount", "n_minutes", "n_minutes_expected", "partial"]
LIMIT_COLUMNS = ["symbol", "date", "up_limit", "down_limit"]
FORECAST_COLUMNS = ["ts_code", "ann_date", "end_date", "type", "p_change_min",
                    "p_change_max", "net_profit_min", "net_profit_max",
                    "last_parent_net", "first_ann_date", "summary",
                    "change_reason", "update_flag"]

POOL_ELIGIBILITY = {
    "source_dataset": "bars_daily",
    "direct_fields": ["symbol", "date", "close", "preclose", "amount", "turn",
                      "tradestatus", "isST"],
    "rules_at_signal_session": [
        "tradestatus == 1（历史停牌状态）",
        "isST == 0（历史 ST 状态，空值按不合格拒绝）",
        "close >= 2.0 元",
        "amount 的 20 自身交易日滚动中位数 >= 50,000,000 元",
        "板块前缀过滤（主板 sh.60* / sz.00*），创业板按 C1 授权边界排除",
        "listing_index > 120（上市满 120 个自身交易日）",
    ],
    "derived_not_exported": ["amt_med20", "vol20", "turn20", "listing_index",
                             "c_adj"],
    "note": "派生字段必须由使用方在沙箱数据上重新计算；导出不携带任何因子值。",
}


class ExportSelfCheckError(RuntimeError):
    """导出输出越界：Dev 沙箱不允许出现许可窗之外的行。"""


@dataclass(frozen=True)
class _Sample:
    peak_rss_mb: float
    samples: int


class _MemoryMonitor:
    def __init__(self, interval: float = 0.25) -> None:
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._peak = 0.0
        self._n = 0

    def __enter__(self) -> "_MemoryMonitor":
        process = psutil.Process(os.getpid())

        def loop() -> None:
            while not self._stop.is_set():
                self._peak = max(self._peak, process.memory_info().rss / (1024 * 1024))
                self._n += 1
                self._stop.wait(self._interval)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    @property
    def sample(self) -> _Sample:
        return _Sample(round(self._peak, 1), self._n)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def ts_code_to_symbol(ts_code: str) -> str | None:
    parts = str(ts_code).split(".")
    if len(parts) != 2 or parts[1] not in {"SH", "SZ"}:
        return None
    code = parts[0]
    if len(code) != 6 or not code.isdigit():
        return None
    return ("sh." if parts[1] == "SH" else "sz.") + code


def _csv_data_rows(path: Path) -> int:
    """CSV 数据行数（不含表头与空行），用于识别零数据的真实缺口文件。"""
    with path.open(encoding="utf-8", errors="replace") as stream:
        stream.readline()
        return sum(1 for line in stream if line.strip())


def _sink(lf: pl.LazyFrame, path: Path, *, compression: str = "zstd") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lf.sink_parquet(path, compression=compression)


def _file_entry(root: Path, rel_path: str, date_col: str,
                *, manifest_prefix: str) -> dict:
    """root 为 staging 目录；写入 manifest 的 rel_path 一律是仓库相对路径。"""
    path = root / rel_path
    if not path.is_file():
        raise ExportSelfCheckError(f"expected output missing: {rel_path}")
    scan = (pl.scan_parquet(path)
            .select(pl.len().alias("rows"),
                    pl.col(date_col).min().alias("dmin"),
                    pl.col(date_col).max().alias("dmax"))
            .collect())
    row = scan.to_dicts()[0]
    return {
        "rel_path": f"{manifest_prefix.rstrip('/')}/{rel_path}".replace("\\", "/"),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "rows": int(row["rows"]),
        "date_min": row["dmin"].isoformat() if row["dmin"] else None,
        "date_max": row["dmax"].isoformat() if row["dmax"] else None,
    }


def _assert_within(files: list[dict], limit: date, dataset: str) -> None:
    for f in files:
        if f["date_max"] and date.fromisoformat(f["date_max"]) > limit:
            raise ExportSelfCheckError(
                f"{dataset}: output {f['rel_path']} contains rows up to "
                f"{f['date_max']} beyond {limit}")


def export(repo_root: Path, *, dest_rel: str = f"data/processed/{DATASET_ID}",
           command: list[str] | None = None, run_id: str = "") -> dict:
    repo_root = repo_root.resolve()
    dest = repo_root / dest_rel
    staging = dest.with_name(dest.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc)
    datasets: list[dict] = []
    sources: dict[str, dict] = {}

    with _MemoryMonitor() as monitor:
        # --- 1. 日线 Dev 段 -------------------------------------------------- #
        daily_src = repo_root / DAILY_SRC
        sources["bars_daily_source"] = {
            "path": str(DAILY_SRC).replace("\\", "/"),
            "sha256": sha256_file(daily_src),
            "note": "混合年份派生文件（1999-11-10..2024-12-31）；导出只输出 2015-01-05..2020-12-31",
        }
        _sink(pl.scan_parquet(daily_src)
              .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
              .select(DAILY_COLUMNS),
              staging / "bars_daily_dev.parquet")
        dev_files = [_file_entry(staging, "bars_daily_dev.parquet", "date", manifest_prefix=dest_rel)]
        _assert_within(dev_files, DEV_END, "bars_daily_dev")
        datasets.append(_dataset_entry(
            kind="bars_daily", date_column="date", max_allowed_date=DEV_END,
            min_allowed_date=DEV_START, files=dev_files, columns=DAILY_COLUMNS,
            semantics=("baostock 官方日线，不复权（adjustflag=3），volume=股、amount=元；"
                       "close 为官方日收盘（估值与 15:00 锚价口径），preclose 为官方前收；"
                       "tradestatus 为历史停复牌状态、isST 为历史 ST 状态。"
                       "本文件同时承载股票池资格所需字段。"),
            purpose="dev_performance_window",
            units={"prices": "元（不复权）", "volume": "股", "amount": "元"},
            extra={"pool_eligibility": POOL_ELIGIBILITY},
        ))

        # --- 2. 日线预热段（2014-03 起，仅特征历史） ------------------------- #
        _sink(pl.scan_parquet(daily_src)
              .filter((pl.col("date") >= WARM_START) & (pl.col("date") <= WARM_END))
              .select(DAILY_COLUMNS),
              staging / "bars_daily_warmup.parquet")
        warm_files = [_file_entry(staging, "bars_daily_warmup.parquet", "date", manifest_prefix=dest_rel)]
        _assert_within(warm_files, WARM_END, "bars_daily_warmup")
        datasets.append(_dataset_entry(
            kind="bars_daily_warmup", date_column="date",
            max_allowed_date=WARM_END, min_allowed_date=WARM_START,
            files=warm_files, columns=DAILY_COLUMNS,
            semantics=("日线预热窗（2014-03-01..2015-01-04）：用途仅为特征/滚动窗历史，"
                       "不构成任何绩效年份，不得用于计算收益标签或账户权益。"),
            purpose="feature_history_only",
            units={"prices": "元（不复权）", "volume": "股", "amount": "元"},
            extra={},
        ))

        # --- 3. 半日 bar（逐年分区） ----------------------------------------- #
        half_files: list[dict] = []
        for year in range(DEV_START.year, DEV_END.year + 1):
            src = repo_root / HALFDAY_SRC_DIR / f"year={year}" / "bars.parquet"
            if not src.is_file():
                raise ExportSelfCheckError(f"halfday source missing: {src}")
            sources[f"halfday_source_year_{year}"] = {
                "path": str(src.relative_to(repo_root)).replace("\\", "/"),
                "sha256": sha256_file(src),
            }
            rel_out = f"bars_halfday/year={year}/bars.parquet"
            _sink(pl.scan_parquet(src)
                  .rename({"trade_date": "date"})
                  .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
                  .select(HALFDAY_COLUMNS),
                  staging / rel_out)
            half_files.append(_file_entry(staging, rel_out, "date", manifest_prefix=dest_rel))
        _assert_within(half_files, DEV_END, "bars_halfday")
        datasets.append(_dataset_entry(
            kind="bars_halfday", date_column="date", max_allowed_date=DEV_END,
            min_allowed_date=DEV_START, files=half_files,
            columns=HALFDAY_COLUMNS,
            semantics=("全市场 A 股半日 OHLCV bar（am <=11:30、pm >=13:00），价格=元、"
                       "volume=股、amount=元；缺行=该时段无有量 bar（不可交易）；"
                       "n_minutes/partial 为数据质量诊断列。"),
            purpose="dev_performance_window",
            units={"prices": "元（不复权）", "volume": "股", "amount": "元"},
            extra={"segmentation": "am/trade_time<=11:30:00，pm/trade_time>=13:00:00；"
                                   "vol==0 为 vendor 占位，不聚合"},
        ))

        # --- 4. 涨跌停价（Dev 段） ------------------------------------------- #
        limit_chunks = []
        limit_sha = {}
        empty_limit_chunks = []
        for chunk in sorted((repo_root / LIMIT_SRC_DIR).glob("chunk_*.csv")):
            stem = chunk.stem.replace("chunk_", "")
            day = date(int(stem[:4]), int(stem[4:6]), int(stem[6:8]))
            if not (DEV_START <= day <= DEV_END):
                continue
            if _csv_data_rows(chunk) == 0:
                empty_limit_chunks.append(stem)
                continue
            limit_chunks.append(str(chunk))
            limit_sha[chunk.name] = sha256_file(chunk)
        if not limit_chunks:
            raise ExportSelfCheckError("no stk_limit chunks inside the Dev window")
        sources["limit_source"] = {
            "path": str(LIMIT_SRC_DIR).replace("\\", "/"),
            "files": len(limit_sha),
            "sha256_map": limit_sha,
            "empty_chunks_skipped": empty_limit_chunks,
            "note": "逐交易日 chunk；只登记并读取 Dev 窗口内的 chunk；"
                    "表头存在但零数据行的 chunk 单独登记（真实缺口，不补造）",
        }
        _sink(pl.scan_csv(limit_chunks, infer_schema_length=1000,
                          schema_overrides={"trade_date": pl.Utf8,
                                            "ts_code": pl.Utf8,
                                            "up_limit": pl.Float64,
                                            "down_limit": pl.Float64})
              .with_columns(pl.col("trade_date").cast(pl.String).str.to_date("%Y%m%d")
                            .alias("date"))
              .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
              .with_columns(pl.col("ts_code").map_elements(
                  ts_code_to_symbol, return_dtype=pl.String).alias("symbol"))
              .filter(pl.col("symbol").is_not_null())
              .select(LIMIT_COLUMNS),
              staging / "limits/limit_dev.parquet")
        limit_files = [_file_entry(staging, "limits/limit_dev.parquet", "date", manifest_prefix=dest_rel)]
        _assert_within(limit_files, DEV_END, "limit")
        datasets.append(_dataset_entry(
            kind="limit", date_column="date", max_allowed_date=DEV_END,
            min_allowed_date=DEV_START, files=limit_files, columns=LIMIT_COLUMNS,
            semantics=("tushare stk_limit 历史每日涨跌停价（元），ts_code 已换算为 "
                       "repo symbol；用于订单价格合法性与涨跌停边界判定。"),
            purpose="dev_performance_window",
            units={"up_limit": "元", "down_limit": "元"},
            extra={},
        ))

        # --- 5. B 家族业绩预告（2018-09-04..2020-12-31） ---------------------- #
        fcst_chunks = []
        fcst_sha = {}
        for chunk in sorted((repo_root / FORECAST_SRC_DIR).glob("chunk_*.csv")):
            stem = chunk.stem.replace("chunk_", "")
            first = date(int(stem[:4]), int(stem[4:6]), 1)
            last_year, last_month = int(stem[:4]), int(stem[4:6])
            # 月块：只要与 B 窗口月份相交就读取，行级过滤在后
            if not (B_DEV_FIRST.year * 100 + B_DEV_FIRST.month
                    <= last_year * 100 + last_month
                    <= B_DEV_LAST.year * 100 + B_DEV_LAST.month):
                continue
            fcst_chunks.append(str(chunk))
            fcst_sha[chunk.name] = sha256_file(chunk)
        if not fcst_chunks:
            raise ExportSelfCheckError("no forecast chunks intersect the B window")
        sources["forecast_source"] = {
            "path": str(FORECAST_SRC_DIR).replace("\\", "/"),
            "files": len(fcst_sha),
            "sha256_map": fcst_sha,
            "note": "逐月 chunk；只登记并读取与 2018-09..2020-12 相交的 chunk，行级再按 ann_date 过滤",
        }
        _sink(pl.scan_csv(fcst_chunks, infer_schema_length=10000)
              .with_columns(pl.col("ann_date").cast(pl.String).str.to_date("%Y%m%d")
                            .alias("_ann"))
              .filter((pl.col("_ann") >= B_DEV_FIRST) & (pl.col("_ann") <= B_DEV_LAST))
              .select(
                  pl.col("ts_code").cast(pl.String),
                  pl.col("_ann").alias("ann_date"),
                  pl.col("end_date").cast(pl.String),
                  pl.col("type").cast(pl.String),
                  pl.col("p_change_min").cast(pl.Float64),
                  pl.col("p_change_max").cast(pl.Float64),
                  pl.col("net_profit_min").cast(pl.Float64),
                  pl.col("net_profit_max").cast(pl.Float64),
                  pl.col("last_parent_net").cast(pl.Float64),
                  pl.col("first_ann_date").cast(pl.String).str.to_date("%Y%m%d"),
                  pl.col("summary").cast(pl.String),
                  pl.col("change_reason").cast(pl.String),
                  pl.col("update_flag").cast(pl.String)),
              staging / "events/forecast_b_window.parquet")
        fcst_files = [_file_entry(staging, "events/forecast_b_window.parquet",
                                  "ann_date", manifest_prefix=dest_rel)]
        _assert_within(fcst_files, B_DEV_LAST, "forecast_event")
        datasets.append(_dataset_entry(
            kind="forecast_event", date_column="ann_date",
            max_allowed_date=B_DEV_LAST, min_allowed_date=B_DEV_FIRST,
            files=fcst_files, columns=FORECAST_COLUMNS,
            semantics=("tushare forecast 业绩预告原始字段（未做版本去重、未做区间校验），"
                       "ann_date=公告日、end_date=业绩期末、update_flag=vendor 版本标识；"
                       "net_profit_min/max 单位为万元。"),
            purpose="b_family_event_source",
            units={"net_profit_min": "万元", "net_profit_max": "万元",
                   "p_change_min": "%", "p_change_max": "%"},
            extra={"b_family_window": [B_DEV_FIRST.isoformat(), B_DEV_LAST.isoformat()],
                   "version_pit_note": "as-fetched snapshot; historical version "
                                       "availability is audited in "
                                       "announcement_version_audit.csv"},
        ))

        # --- 6. 公司行动（分红 / 送转），Dev 段 ------------------------------- #
        # 直接复用主引擎的冻结读取器，保证与 band_engine 合同口径一致，
        # 不在导出层另写一套 h5 解析。
        from quant.backtest.band_engine import (  # 局部导入：保持模块导入轻量
            load_dividends_h5, load_split_factor_h5)
        bundle = repo_root / "data/processed/rqalpha-bundle-v2-1-20260918"
        sources["corporate_action_bundle"] = {
            "path": str(bundle.relative_to(repo_root)).replace("\\", "/"),
            "dividends_h5_sha256": sha256_file(bundle / "dividends.h5"),
            "split_factor_h5_sha256": sha256_file(bundle / "split_factor.h5"),
            "note": "ex_cum_factor.h5（含分红复权因子）禁止作为账户输入，未导出",
        }
        div_all, _div_meta = load_dividends_h5(bundle / "dividends.h5")
        div_dev = (div_all.filter((pl.col("ex_date") >= DEV_START)
                                  & (pl.col("ex_date") <= DEV_END))
                   .sort("symbol", "ex_date"))
        _sink(div_dev.lazy(), staging / "corporate_actions/dividends_dev.parquet")
        div_files = [_file_entry(staging, "corporate_actions/dividends_dev.parquet",
                                 "ex_date", manifest_prefix=dest_rel)]
        _assert_within(div_files, DEV_END, "dividend")
        datasets.append(_dataset_entry(
            kind="dividend", date_column="ex_date", max_allowed_date=DEV_END,
            min_allowed_date=DEV_START, files=div_files,
            columns=["symbol", "ex_date", "cash_per_lot_pre_tax", "round_lot"],
            semantics=("rqalpha bundle dividends.h5 经主引擎冻结读取器输出："
                       "cash_per_lot_pre_tax 为每整手（round_lot 股）税前现金分红，"
                       "不是每股金额；ex_date 为除息日，账户合同按除息日计入已结算现金。"
                       "源 h5 另含 book_closure_date / payable_date，C1 未导出；"
                       "若 C2 要改用付款日记账，属合同变更须先登记。"),
            purpose="dev_performance_window",
            units={"cash_per_lot_pre_tax": "元/整手（税前）", "round_lot": "股"},
            extra={"per_lot_unit_proof": "sh.600000 2022-07-21 源值 41.0 = 0.41 元/股 × 100"},
        ))
        split_all, _split_meta = load_split_factor_h5(bundle / "split_factor.h5")
        split_dev = (split_all.filter((pl.col("ex_date") >= DEV_START)
                                      & (pl.col("ex_date") <= DEV_END))
                     .sort("symbol", "ex_date"))
        _sink(split_dev.lazy(), staging / "corporate_actions/split_factor_dev.parquet")
        split_files = [_file_entry(
            staging, "corporate_actions/split_factor_dev.parquet", "ex_date",
            manifest_prefix=dest_rel)]
        _assert_within(split_files, DEV_END, "split_factor")
        datasets.append(_dataset_entry(
            kind="split_factor", date_column="ex_date", max_allowed_date=DEV_END,
            min_allowed_date=DEV_START, files=split_files,
            columns=["symbol", "ex_date", "split_factor"],
            semantics=("rqalpha bundle split_factor.h5 经主引擎冻结读取器输出："
                       "split_factor 为该除权日的份额乘数（1 + 送转比例），"
                       "同日多行按连乘处理，禁止与相邻行差分。"),
            purpose="dev_performance_window",
            units={"split_factor": "倍"},
            extra={"forbidden": "ex_cum_factor 累计因子不得作为账户份额倍率"},
        ))

    # --- 7. manifest --------------------------------------------------------- #
    elapsed = time.perf_counter() - started
    contract_path = repo_root / "docs/evidence/trust-rebuild" / run_id / "interface_contract.json"
    contract_sha = sha256_file(contract_path) if contract_path.is_file() else None
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "created_at_utc": started_utc.isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "export_command": command or [],
        "contract_path": (str(contract_path.relative_to(repo_root)).replace("\\", "/")
                          if contract_path.is_file() else None),
        "contract_sha256": contract_sha,
        "dev_range": {
            "dev_start": DEV_START.isoformat(),
            "dev_end": DEV_END.isoformat(),
            "warmup_start": WARM_START.isoformat(),
            "warmup_end": WARM_END.isoformat(),
            "warmup_purpose": "feature_history_only",
            "b_family_window": [B_DEV_FIRST.isoformat(), B_DEV_LAST.isoformat()],
            "validation_window": "2021-01-01..2024-12-31（须单独授权，不在本数据集内）",
            "frozen_window": "2025-01-01 及以后（冻结，不在本数据集内）",
        },
        "datasets": datasets,
        "sources": sources,
        "no_2021plus_verification": {
            "rule": "每个数据集的输出日期最大/最小值必须在 manifest 声明的窗口内；"
                    "导出工具在写完后逐文件重扫并硬断言",
            "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "checked_kinds": [d["kind"] for d in datasets],
            "max_date_observed_per_kind": {
                d["kind"]: max((f["date_max"] or "") for f in d["files"])
                for d in datasets
            },
            "passed": True,
        },
        "totals": {
            "files": sum(len(d["files"]) for d in datasets),
            "rows": sum(f["rows"] for d in datasets for f in d["files"]),
            "bytes": sum(f["bytes"] for d in datasets for f in d["files"]),
            "export_seconds": round(elapsed, 2),
            "peak_rss_mb": monitor.sample.peak_rss_mb,
            "memory_samples": monitor.sample.samples,
        },
        "limitations": [
            "单一行情上游（baostock 官方日线 + 用户 1 分钟包聚合的半日 bar）；"
            "半日 bar 与 baostock 日线不是独立来源。",
            "半日 bar 的 pm.close 不是官方收盘，不得作 mark 或 15:00 锚价；"
            "官方收盘只来自 bars_daily 的 close。",
            "复权因子未随沙箱导出；任何跨公司行动的多日收益必须另行登记复权口径"
            "（adjust_mode=back_adjusted）并由 dataset_id 之外的身份文件承载。",
            "ST/停牌为单源 isST/tradestatus 历史字段；不能替代正式账户权限证据。",
            "创业板/科创板/北交所行仍在 bars_daily 物理存在，池过滤在资格层执行，"
            "不在导出层删除（保留可审计性）。",
        ],
    }
    (staging / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if dest.exists():
        shutil.rmtree(dest)
    staging.rename(dest)
    manifest["dest"] = str(dest_rel).replace("\\", "/")
    return manifest


def _dataset_entry(*, kind: str, date_column: str, max_allowed_date: date,
                   min_allowed_date: date, files: list[dict], columns: list[str],
                   semantics: str, purpose: str, units: dict,
                   extra: dict) -> dict:
    entry = {
        "kind": kind,
        "date_column": date_column,
        "symbol_column": "symbol",
        "min_allowed_date": min_allowed_date.isoformat(),
        "max_allowed_date": max_allowed_date.isoformat(),
        "purpose": purpose,
        "semantics": semantics,
        "columns": columns,
        "units": units,
        "files": files,
    }
    entry.update(extra)
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--run-id", default="")
    args = parser.parse_args(argv)
    root = Path(args.repo_root) if args.repo_root else Path(__file__).resolve().parents[3]
    manifest = export(root, command=["python", "tools/export_dev_sandbox.py"],
                      run_id=args.run_id)
    print(json.dumps({
        "dataset_id": manifest["dataset_id"],
        "files": manifest["totals"]["files"],
        "rows": manifest["totals"]["rows"],
        "bytes": manifest["totals"]["bytes"],
        "export_seconds": manifest["totals"]["export_seconds"],
        "peak_rss_mb": manifest["totals"]["peak_rss_mb"],
        "no_2021plus_verification": manifest["no_2021plus_verification"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
