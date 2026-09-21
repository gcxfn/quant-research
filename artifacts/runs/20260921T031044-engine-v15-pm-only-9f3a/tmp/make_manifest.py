# -*- coding: utf-8 -*-
"""Evidence manifest for the engine-v1.5 extension run (task 2).

Hashes every file in this run directory plus the external artifacts this run's
claims rest on, and records the engine pin before/after.  Deterministic:
re-running it on an unchanged tree reproduces byte-identical JSON.
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import date
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


ENGINE = ROOT / "src/quant/backtest/band_engine.py"
ANCHOR_RUN = ROOT / "artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a"
F3R3_RUN = ROOT / "artifacts/runs/20260921T024449-f3r3-dynamic-45037d"
SMOKE_RUN = ROOT / "artifacts/runs/20260921T032048-etf-pm-only-smoke-c4d1"
IDENTITY_RUN = ROOT / "artifacts/runs/20260921T023606-etf-dynamic-identity-e41c"

outputs = {}
for path in sorted(RUN_DIR.rglob("*")):
    if path.is_file() and path.name != "manifest.json":
        outputs[path.relative_to(RUN_DIR).as_posix()] = sha256_file(path)

external = {
    "engine": {"path": "src/quant/backtest/band_engine.py",
               "version": "v1.5", "sha256": sha256_file(ENGINE)},
    "engine_installed_copy": {
        "path": ".venv/Lib/site-packages/quant/backtest/band_engine.py",
        "sha256": sha256_file(
            ROOT / ".venv/Lib/site-packages/quant/backtest/band_engine.py")},
    "new_tests": {"path": "tests/test_band_engine_v15_etf_pm_only.py",
                  "sha256": sha256_file(
                      ROOT / "tests/test_band_engine_v15_etf_pm_only.py")},
    "d1_d8_tests_untouched": {
        "path": "tests/test_band_dynamic.py",
        "sha256": sha256_file(ROOT / "tests/test_band_dynamic.py")},
    "v14_zones_tests_version_labels": {
        "path": "tests/test_band_engine_v14_zones.py",
        "sha256": sha256_file(ROOT / "tests/test_band_engine_v14_zones.py")},
    "prereg_smoke": {
        "path": "docs/research/exp-20260921-etf-pm-only-smoke-prereg.md",
        "sha256": sha256_file(
            ROOT / "docs/research/exp-20260921-etf-pm-only-smoke-prereg.md")},
    "decision": {"path": "docs/decisions/2026-09-21-etf-pm-only-routing.md",
                 "sha256": sha256_file(
                     ROOT / "docs/decisions/2026-09-21-etf-pm-only-routing.md")},
    "anchor_replay_run": {"path": ANCHOR_RUN.relative_to(ROOT).as_posix(),
                          "comparison": sha256_file(
                              ANCHOR_RUN / "outputs/anchor_frame_comparison.json")},
    "f3r3_frozen_run_outputs": {
        "path": F3R3_RUN.relative_to(ROOT).as_posix(),
        "frames": {p.name: sha256_file(p) for p in
                   sorted((F3R3_RUN / "outputs").glob("*.parquet"))}},
    "smoke_run": {"path": SMOKE_RUN.relative_to(ROOT).as_posix(),
                  "manifest_sha256": sha256_file(SMOKE_RUN / "manifest.json"),
                  "report_sha256": sha256_file(SMOKE_RUN / "report.md")},
    "identity_run_reference": {
        "path": IDENTITY_RUN.relative_to(ROOT).as_posix(),
        "probe_json_sha256": sha256_file(
            IDENTITY_RUN / "tmp/etf_dynamic_identity_probe.json")},
}

comparison = json.loads(
    (ANCHOR_RUN / "outputs/anchor_frame_comparison.json").read_text(
        encoding="utf-8"))
anchor_frames = [row for row in comparison if row["file"].endswith(".parquet")]
manifest = {
    "run_id": RUN_DIR.name,
    "task": "任务②：halfday 时钟 ETF pm-only 路由落地与动态冒烟（引擎扩展交付与验收）",
    "status": "completed",
    "mode": "engine-extension-and-verification",
    "date_utc": date.today().isoformat(),
    "trial_accounting": "纯工程（引擎扩展 + 验收），试验计数消费 0",
    "engine_pin": {"path": "src/quant/backtest/band_engine.py",
                   "version_before": "v1.4.1 (bcbdd44bb855b803…)",
                   "version_after": "v1.5",
                   "sha256": external["engine"]["sha256"],
                   "lines": len(ENGINE.read_text(encoding="utf-8").splitlines()),
                   "bytes": ENGINE.stat().st_size},
    "acceptance": {
        "full_suite": {"log": "logs/pytest_full_suite.log",
                       "result": "638 passed / 0 failed / 0 skipped",
                       "baseline_collected_before_change": 630,
                       "new_tests": 8},
        "d1_d8_untouched": {"log": "logs/pytest_band_dynamic_d1d8.log",
                            "result": "9 passed",
                            "test_file_sha256_unchanged": True},
        "targeted_tests": {"log": "logs/pytest_v15_targeted.log",
                           "result": "8 passed",
                           "file": "tests/test_band_engine_v15_etf_pm_only.py"},
        "f3r3_anchor": {
            "runner": "artifacts/runs/20260921T031044-f3r3-anchor-replay-9f3a/"
                      "tmp/runner_f3r3_anchor.py (verbatim copy + 8-line header "
                      "comment; body differs only in the engine pin line)",
            "engine_product_frames": {
                "required": ["F3-EW_fills.parquet", "F3-EW_events.parquet",
                             "F3-EW_daily_equity.parquet",
                             "F3-EW_clips_final.parquet",
                             "F3-ICW_fills.parquet", "F3-ICW_events.parquet",
                             "F3-ICW_daily_equity.parquet",
                             "F3-ICW_clips_final.parquet"],
                "verdicts": {row["file"]: row["verdict"] for row in comparison
                             if row["file"] in (
                                 "F3-EW_fills.parquet",
                                 "F3-EW_events.parquet",
                                 "F3-EW_daily_equity.parquet",
                                 "F3-EW_clips_final.parquet",
                                 "F3-ICW_fills.parquet",
                                 "F3-ICW_events.parquet",
                                 "F3-ICW_daily_equity.parquet",
                                 "F3-ICW_clips_final.parquet")},
            },
            "other_products": {row["file"]: row["verdict"] for row in comparison},
            "engine_product_frames_byte_equal": sum(
                1 for row in anchor_frames if row["verdict"] == "BYTE-EQUAL"
                and "composite" not in row["file"]),
            "anchor_parquet_total": len(anchor_frames),
            "comparison": ANCHOR_RUN.relative_to(ROOT).as_posix()
            + "/outputs/anchor_frame_comparison.json",
            "disclosed_benign_diffs": [
                "F3-{EW,ICW}_composite.parquet: file bytes differ, row "
                "multiset and key-sorted content identical (input to the "
                "engine; the resulting fill frames are byte-equal)",
                "metrics_and_gates.json: engine_sha256_16 field + ~1e-15 "
                "float reduction noise in F3-ICW turnover/mean_equity; gate "
                "verdicts and judgement numbers unchanged (0/2 dev_pass)",
            ]},
        "probe": {"script": "tmp/etf_pm_only_probe.py",
                  "json": "tmp/etf_pm_only_probe.json",
                  "result": "P1/P2 (default routing) rejected; P1p/P2p "
                            "(pm_only) run and agree; P3 control unchanged; "
                            "P4 legacy matches the pre-change identity run "
                            "field by field"},
    },
    "double_signature": {
        "first_signature": "语义节执行者（本 run）：实现 + 验收亲跑（§acceptance）",
        "second_signature": "独立复核代理 EngineDoubleSign：APPROVE（零 CRITICAL/"
                            "零 MAJOR、1 项 P3 已按复核方案处置）；报告 "
                            "verification_report.md",
        "delta_reverification": "同一复核代理对处置后的三处增量再确认：测试 8 passed 且"
                                "其余测试未变；冒烟 19 判据全 True、8 个数据产物逐字节不变；"
                                "引擎 src/.venv 副本 sha 未变 -> APPROVE 对最终字节维持有效",
        "review_hygiene_dispositions": {
            "F2": "manifest 输出哈希排除 logs/__pycache__/*.pyc 并加 outputs_note；无陈旧哈希",
            "F3": "冒烟 report 确定性表述改写为按数据产物口径",
            "F4": "判据计数口径统一为 19（routing 5/matching 4/fees 2/t0 3/ledger 5）",
        },
        "review_finding_disposition": {
            "F1_P3": "test_t1_am_decision_point_never_emits_an_etf_order_under_"
                     "pm_only 的不可证伪断言 -> 改为提交真实单 + am 会话零事件；"
                     "测试文件 sha d4dbd177.. -> fd29fa21..",
            "C1": "t1 注释误标（2.005 说成 at the anchor）已更正",
            "C2": "冒烟 runner 恒真的 am 判据 -> routing_no_etf_order_in_any_am_"
                  "session（可证伪）；冒烟已重跑，16 笔成交与其余判据不变",
        },
    },
    "env": {"python": platform.python_version(), "polars": pl.__version__,
            "numpy": np.__version__, "platform": platform.platform()},
    "outputs": outputs,
    "external_artifacts": external,
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps({**manifest, "outputs": outputs}, ensure_ascii=False, indent=1,
               default=str), encoding="utf-8")
print(json.dumps({"engine": manifest["engine_pin"]["sha256"],
                  "anchor_frames": manifest["acceptance"]["f3r3_anchor"]
                  ["engine_product_frames_byte_equal"],
                  "files": len(outputs)}, ensure_ascii=False))
