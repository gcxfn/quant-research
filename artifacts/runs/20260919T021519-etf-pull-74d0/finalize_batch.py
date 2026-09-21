# -*- coding: utf-8 -*-
"""Finalize batch dir after blocker: failed manifest + sha256.tsv."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(r"D:\量化")
RUN_DIR = REPO / "artifacts" / "runs" / "20260919T021519-etf-pull-74d0"
BATCH_DIR = REPO / "data" / "raw" / "baostock" / "etf-daily-20260919-r1"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    pool = list(csv.DictReader(open(BATCH_DIR / "pool_type5.csv", encoding="utf-8")))
    diff = json.load(open(RUN_DIR / "pool_diff.json", encoding="utf-8"))

    manifest = {
        "dataset": "etf_daily",
        "batch": "etf-daily-20260919-r1",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "failed",
        "status_note": (
            "拉取被阻断: baostock 不提供 2015-01-01..2024-12-31 的任何 ETF 日线。"
            "本批次仅含 ETF 名录 (pool_type5.csv) 与本 manifest, 无行情数据。"
        ),
        "blocker": {
            "summary": (
                "baostock 两条 K 线接口对 2015-2024 窗口均无 ETF 数据: "
                "(1) query_history_k_data_plus 对基金代码确定性地返回空集 "
                "(err=0, 0 行, 510050/510300/159915/159503 多次验证); "
                "(2) 0.9.x 专用端点 query_daily_history_k_ETF 仅含约 2026-02 起的近期数据, "
                "窗口内 12 个抽查交易日全部 err=0/0 行, 唯一非空样本为 2026-02-04 (1,419 行)。"
            ),
            "evidence": "artifacts/runs/20260919T021519-etf-pull-74d0/endpoint_probes.json",
            "corroboration": (
                "股票腿 data/raw/baostock/daily (1999-2024) 不含任何基金代码 (0/5410); "
                "recon 报告 artifacts/runs/20260918T202734-etf-recon-1d83 的分钟层无 ETF 结论一致"
            ),
        },
        "source": "baostock query_daily_history_k_ETF / query_history_k_data_plus (均无窗口内数据)",
        "range": {
            "start": "2015-01-01",
            "end": "2024-12-31",
            "hard_boundary": "请求与落盘不得越过 2024-12-31 (本次无行情行落盘, 边界未被触碰)",
        },
        "fields_note": (
            "ETF 专用端点字段 (来自 canary): date,code,open,high,low,close,preclose,"
            "volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
        ),
        "universe": {
            "source": (
                "baostock query_stock_basic 全量 type=5 (8,967 行全表; 名录仅含在市 ETF, "
                "退市缺失用 tushare fund_basic market=E, 名称含 ETF, list_date<=20241231 补齐, "
                "pool_source 列区分)"
            ),
            "count": len(pool),
            "pool_file": "pool_type5.csv",
            "status_listed": sum(1 for r in pool if r["status"] == "1"),
            "status_delisted": sum(1 for r in pool if r["status"] == "0"),
        },
        "diff_vs_tushare_fund_daily": {
            "tushare_batch": "data/raw/tushare/fund_daily/20260917-r1 (1169 codes)",
            "overlap_count": diff["overlap_count"],
            "baostock_only_count": len(diff["baostock_only"]),
            "baostock_only_note": "652 只全部 ipoDate>2024-12-31 (窗口外新上市)",
            "tushare_only_count": len(diff["tushare_only"]),
            "tushare_only_note": "143 只中 123 只有退市日 (2015-08-27..2025-10-14), 20 只无退市日 (疑似转型/更名)",
            "supplement_from_fund_basic_count": diff["supplement_from_fund_basic_count"],
            "supplement_delisted_count": diff["supplement_delisted_count"],
            "detail_file": "artifacts/runs/20260919T021519-etf-pull-74d0/pool_diff.json",
        },
        "totals": {
            "codes_in_pool": len(pool),
            "codes_with_kline_rows": 0,
            "rows_total": 0,
            "out_of_window_rows_dropped": 0,
        },
        "run_dir": "artifacts/runs/20260919T021519-etf-pull-74d0",
        "env": {
            "python": "3.11.15",
            "baostock": "0.9.3",
            "install_note": (
                "baostock 0.9.3 于本次运行经 uv pip 装入仓库 .venv "
                "(纯 Python, 未改 pyproject/uv.lock, 未动其他包); hermes venv 亦为 0.9.3, 结果一致"
            ),
            "os": "Windows",
        },
        "sha256_file": "sha256.tsv",
    }
    (BATCH_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    rows = []
    for p in sorted(BATCH_DIR.iterdir()):
        if p.name in ("manifest.json", "sha256.tsv") or not p.is_file():
            continue
        rows.append(f"{p.name}\t{p.stat().st_size}\t{sha256_of(p)}")
    (BATCH_DIR / "sha256.tsv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8", newline=""
    )
    print(f"manifest.json written (status=failed); sha256.tsv rows={len(rows)}")


if __name__ == "__main__":
    main()
