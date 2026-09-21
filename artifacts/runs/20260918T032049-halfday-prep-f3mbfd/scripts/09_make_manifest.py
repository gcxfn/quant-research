# -*- coding: utf-8 -*-
"""09_make_manifest.py — 汇总 run manifest（AGENTS §5.3 最低清单）。"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(r"D:\量化")
RUN = REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def main() -> int:
    scripts = sorted((RUN / "scripts").glob("*.py"))
    scripts_meta = {p.name: {"bytes": p.stat().st_size, "sha256": sha256_file(p)} for p in scripts}
    logs = sorted((RUN / "logs").glob("*.log"))
    cache = REPO / "data" / "cache" / "halfday_1130_proto_20260918"
    cache_files = {p.name: p.stat().st_size for p in sorted(cache.glob("*"))} if cache.exists() else {}
    manifest = {
        "run_id": RUN.name,
        "experiment_id": "exp-20260918-halfday-prep",
        "task": "G2（股票侧 11:30 半天截面）前置工程准备：身份核验/冻结边界/快照原型/约束清点/窗口审计",
        "nature": "纯数据工程：无因子、无回测、无策略结论、不消费试验数（未读改任何研究结论文档）",
        "started_at": "2026-09-18T03:20:49",
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "completed",
        "environment": {
            "platform": "win32 (Windows 10.0.26200 x64), Git Bash",
            "python": "3.11.15 (D:/量化/.venv/Scripts/python.exe, -X utf8)",
            "polars": "1.44.2",
            "pyarrow": "25.0.1",
            "git": "仓库未初始化 Git（按 AGENTS 纪律，不擅自初始化/提交）",
        },
        "commands": [
            "PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 artifacts/runs/<rid>/scripts/01_verify_identity.py",
            "PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 artifacts/runs/<rid>/scripts/02_boundary_scan.py",
            "PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 artifacts/runs/<rid>/scripts/03_schema_symbol_check.py",
            "PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 artifacts/runs/<rid>/scripts/04_extract_1130_prototype.py",
            "PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 artifacts/runs/<rid>/scripts/05_constraint_checks.py",
            "PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 artifacts/runs/<rid>/scripts/06_close_crosscheck.py",
        ],
        "inputs": {
            "minute_batches": [
                {"path": "data/raw/user_minute_1m/20260913-143215", "files": 1220,
                 "identity": "data/_meta/sha256.tsv 逐文件登记；本 run 01 脚本全量字节数比对 + 抽样 5 文件重算 sha256 一致"},
                {"path": "data/raw/user_minute_1m/20260913-2020-2024", "files": 1213,
                 "identity": "同上"},
            ],
            "pool_reference": "data/processed/baostock-daily-20260917/（P1 已验收：5,328 只、9,532,019 行，manifest/quality 齐全）",
            "stk_limit": "data/raw/xiaodefa/stk_limit/20260913-bulk1/（2014-01-02 起按日 chunk；按列名归一读取；只读抽样 3 日）",
            "read_only_discipline": "data/raw 与 data/_meta 全程只读；未修改 sha256.tsv；未读取任何 2025+ 数据内容（见 boundary_report）",
        },
        "outputs": {
            "run_artifacts": {
                "identity/identity_verification.json": "登记状态：REGISTERED_VERIFIED",
                "boundary/boundary_report.json": "冻结边界：FREEZE_CLEAN（文件级 2,431 + 行级投影全扫 + 7 文件全列读）",
                "boundary/minute_day_files.csv": "逐日文件清单（bytes/num_rows/trade_time min-max）供全窗口抽取复用",
                "schema_check/schema_symbol_report.json": "5 日 schema 一致 + 与 baostock 池交集",
                "extract_1130_proto.json": "3 个抽样日 11:30 快照计时与全窗口外推",
                "constraint_checks.json": "停牌/复权/ST/涨跌停/已登记缺陷五项核验",
                "close_crosscheck.json": "分钟 15:00 收盘 vs baostock 日线收盘分市场一致率",
                "scripts/": scripts_meta,
                "logs/": [p.name for p in logs],
            },
            "rebuildable_cache": {"path": "data/cache/halfday_1130_proto_20260918/", "files": cache_files,
                                  "note": "3 个抽样日 11:30 快照 parquet(zstd)+计时；可随时重建，git 已忽略"},
        },
        "config_and_code_summary": "六个只读脚本：01 身份核验（全量 stat + 抽样重哈希）；02 边界扫描（文件名解析 + trade_time 投影 min/max + parquet 元数据行数）；03 schema/交集（5 日抽样 vs baostock 池）；04 11:30 抽取原型（3 日，分币还原 + baostock preclose 互证 + zstd/snappy 计时）；05 约束核验（停牌占位/除权口径/ST/涨跌停/2015-07-01 缺陷）；06 收盘口径差量化",
        "random_seed": "不适用（无随机成分）",
        "time_splits": "不适用（未计算任何标签/信号/收益；仅触及 ≤2024-12-31 数据）",
        "timing": {"identity": "≈1 s", "boundary_scan": "16.1 s（2,431 文件投影）", "schema_symbol": "≈3 s",
                   "extract_3_days": "<0.5 s/日", "constraint_checks": "≈8 s", "peak_memory": "未逐脚本测量；全部为单文件流式处理，缓存目录 3 日快照合计 <1 MB"},
        "known_limitations": [
            "3 个抽样日（2015-06-01/2020-06-01/2024-06-03）未覆盖 2016/2018/2022/2023 年；外推按 02 脚本全窗口 num_rows 元数据线性外推",
            "峰值内存未逐脚本测量",
            "15:00 收盘口径差仅抽 5 日量化（2015/2017 两年各 1 日），未做全窗口普查",
            "未做全窗口 11:30 快照抽取（等预登记批准）；未设计任何因子、未跑任何回测",
        ],
    }
    (RUN / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] manifest -> {RUN / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
