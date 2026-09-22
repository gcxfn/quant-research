# -*- coding: utf-8 -*-
"""C1 Dev 沙箱加载器测试（合成数据，不依赖真实行情）。

验证数据隔离的四条强制路径：
1. 只有 manifest 登记的 dataset_id 与文件可读；
2. 未登记路径（真实原始/混合年份/Val 路径写法）一律拒绝；
3. 请求日期或实际数据超出 Dev 上限即拒绝（含“manifest 谎报窗口”场景）；
4. 缓存键包含 dataset_id + 输入 SHA256 + 池/日期范围 + 复权口径 + 代码摘要。

运行：``PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_dev_sandbox.py``
"""
from __future__ import annotations

import json
import sys
from datetime import date

import polars as pl
import pytest

sys.path.insert(0, "src")

from quant.data.dev_sandbox import (  # noqa: E402
    SANDBOX_DATASET_ID_DEFAULT, DateRangeError, PathNotAllowedError,
    SandboxAccessError, SandboxRegistry, UnknownDatasetError, sha256_file)


def build_sandbox(root, *, extra_2021_row: bool = False, declare_max="2020-12-31",
                  tamper: bool = False):
    """在 ``root`` 下构造一个最小合成 Dev 沙箱。"""
    sandbox = root / "data/processed" / SANDBOX_DATASET_ID_DEFAULT
    sandbox.mkdir(parents=True, exist_ok=True)
    dates = [date(2020, 12, 24), date(2020, 12, 28), date(2020, 12, 29)]
    symbols = ["sh.600000", "sz.000001"]
    if extra_2021_row:
        dates.append(date(2021, 1, 4))
        symbols.append("sh.600519")
    frame = pl.DataFrame({
        "symbol": symbols * len(dates),
        "date": sorted(dates * len(symbols)),
        "close": [10.0 + i for i in range(len(symbols) * len(dates))],
        "tradestatus": [1.0] * (len(symbols) * len(dates)),
        "isST": [0.0] * (len(symbols) * len(dates)),
    })
    rel = "bars_daily_dev.parquet"
    repo_rel = f"data/processed/{SANDBOX_DATASET_ID_DEFAULT}/{rel}"
    frame.write_parquet(sandbox / rel)
    declared_sha = sha256_file(sandbox / rel)
    if tamper:  # 声明一个不同的 sha，模拟登记身份被改写
        declared_sha = "f" * 64
    manifest = {
        "schema_version": "1.0",
        "dataset_id": SANDBOX_DATASET_ID_DEFAULT,
        "contract_sha256": "0" * 64,
        "datasets": [{
            "kind": "bars_daily",
            "date_column": "date",
            "symbol_column": "symbol",
            "min_allowed_date": "2015-01-05",
            "max_allowed_date": declare_max,
            "purpose": "dev_performance_window",
            "semantics": "synthetic",
            "columns": ["symbol", "date", "close", "tradestatus", "isST"],
            "units": {"close": "CNY"},
            "files": [{
                "rel_path": repo_rel,
                "sha256": declared_sha,
                "rows": frame.height,
                "date_min": "2020-12-24",
                "date_max": declare_max,
            }],
        }],
    }
    (sandbox / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return root, SandboxRegistry.load(root)


def test_registered_dataset_reads(tmp_path):
    _, registry = build_sandbox(tmp_path)
    frame = registry.read("bars_daily")
    assert frame.height == 6
    assert registry.dataset("bars_daily").purpose == "dev_performance_window"


def test_unknown_kind_refused(tmp_path):
    _, registry = build_sandbox(tmp_path)
    with pytest.raises(UnknownDatasetError):
        registry.read("bars_from_2024")


def test_unknown_dataset_id_refused(tmp_path):
    root, _ = build_sandbox(tmp_path)
    for bad in ["baostock-daily-20260917", "halfday-bars-20260918",
                "etf-daily-20260919", "dev-sandbox-20260923"]:
        with pytest.raises(UnknownDatasetError):
            SandboxRegistry.load(root, dataset_id=bad)


@pytest.mark.parametrize("bad_path", [
    "data/raw/baostock/daily/sh.600000.csv",
    "data/processed/baostock-daily-20260917/daily_1999_2024.parquet",
    "data/processed/halfday-bars-20260918/year=2021/bars.parquet",
    "data/raw/tushare/forecast/20260909-r1/chunk_202101.csv",
    "data/features/fcst-reason-struct-full-20260918/row_index.parquet",
    "../outside.parquet",
    "data/processed/dev-sandbox-20260922/../../raw/leak.csv",
])
def test_unregistered_paths_refused(tmp_path, bad_path):
    _, registry = build_sandbox(tmp_path)
    with pytest.raises(PathNotAllowedError):
        registry.resolve(bad_path)


def test_request_end_beyond_dev_end_refused(tmp_path):
    _, registry = build_sandbox(tmp_path)
    with pytest.raises(DateRangeError):
        registry.read("bars_daily", end=date(2021, 1, 1))
    with pytest.raises(DateRangeError):
        registry.read("bars_daily", start=date(2010, 1, 1))


def test_declared_columns_enforced(tmp_path):
    _, registry = build_sandbox(tmp_path)
    with pytest.raises(SandboxAccessError):
        registry.read("bars_daily", columns=["open"])  # 未登记列


def test_post_read_assertion_catches_over_declared_window(tmp_path):
    """即使 manifest 谎报窗口，读取后的实测断言也必须拦住越界行。"""
    _, registry = build_sandbox(tmp_path, extra_2021_row=True,
                                declare_max="2020-12-31")
    with pytest.raises(DateRangeError):
        registry.read("bars_daily")  # 无过滤读取 → 实测到 2021 行 → 拒绝
    # 明确限定 Dev 窗口时只返回 Dev 行（故障安全：永远拿不到 2021+ 行）
    frame = registry.read("bars_daily", end=date(2020, 12, 31))
    assert frame["date"].max() <= date(2020, 12, 31)
    assert date(2021, 1, 4) not in set(frame["date"].to_list())


def test_tampered_input_detected(tmp_path):
    _, registry = build_sandbox(tmp_path, tamper=True)
    assert registry.verify_files("bars_daily") == {
        f"data/processed/{SANDBOX_DATASET_ID_DEFAULT}/bars_daily_dev.parquet": False}
    with pytest.raises(SandboxAccessError):
        registry.read("bars_daily", verify_sha=True)


def test_cache_key_is_deterministic_and_covers_required_components(tmp_path):
    _, registry = build_sandbox(tmp_path)
    base = dict(start=date(2020, 12, 24), end=date(2020, 12, 31),
                symbols=["sh.600000", "sz.000001"], adjust_mode="unadjusted",
                code_digest="code-v1", params_digest="p-v1")
    key = registry.cache_key("bars_daily", **base)
    assert key == registry.cache_key("bars_daily", **base)
    assert len(key) == 64

    # 股票池变化
    other_pool = dict(base, symbols=["sh.600000", "sh.600519"])
    assert registry.cache_key("bars_daily", **other_pool) != key
    # 日期范围变化
    assert registry.cache_key("bars_daily", **dict(base, end=date(2020, 12, 28))) != key
    # 复权口径变化
    assert registry.cache_key("bars_daily", **dict(base, adjust_mode="back_adjusted")) != key
    # 代码/参数摘要变化
    assert registry.cache_key("bars_daily", **dict(base, code_digest="code-v2")) != key
    assert registry.cache_key("bars_daily", **dict(base, params_digest="p-v2")) != key
    # 列集合变化
    assert registry.cache_key("bars_daily", **dict(base, columns=["symbol", "date"])) != key


def test_cache_key_changes_when_input_sha_changes(tmp_path):
    root, registry = build_sandbox(tmp_path)
    key_before = registry.cache_key("bars_daily")
    manifest_path = (root / "data/processed" / SANDBOX_DATASET_ID_DEFAULT
                     / "dataset_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["datasets"][0]["files"][0]["sha256"] = "a" * 64
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    registry_after = SandboxRegistry.load(root)
    assert registry_after.cache_key("bars_daily") != key_before


def test_unknown_adjust_mode_refused(tmp_path):
    _, registry = build_sandbox(tmp_path)
    with pytest.raises(SandboxAccessError):
        registry.cache_key("bars_daily", adjust_mode="magic")


def test_manifest_dataset_id_mismatch_refused(tmp_path):
    root, _ = build_sandbox(tmp_path)
    manifest_path = (root / "data/processed" / SANDBOX_DATASET_ID_DEFAULT
                     / "dataset_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dataset_id"] = "some-other-sandbox"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(SandboxAccessError):
        SandboxRegistry.load(root)
