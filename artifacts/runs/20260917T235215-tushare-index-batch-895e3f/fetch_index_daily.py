# -*- coding: utf-8 -*-
"""tushare index_daily 批次拉取：5 个宽基指数，2015-01-01..2024-12-31（硬边界）。

- token 只从 ~/.quant-credentials/tushare-token 读取；所有输出在打印前经 scrub，
  token 字面量绝不打印、不落盘；异常文本截断后再输出。
- 先探针（000300.SH 近 5 个交易日）验证指数接口权限；失败则原样记录并停止。
- 逐年调用 index_daily，合并为 chunk_<ts_code>.csv；范围外日期强制丢弃。
- 断点续跑：已存在且非空的 chunk 直接跳过。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:/量化")
RAW = ROOT / "data" / "raw"
BATCH_DIR = RAW / "tushare" / "index_daily" / "20260917-r1"
TOKEN_PATH = Path.home() / ".quant-credentials" / "tushare-token"
TOKEN_FILE_NOTE = "~/.quant-credentials/tushare-token (name only; content never logged)"

INDICES = ["000001.SH", "000300.SH", "000905.SH", "000852.SH", "399006.SZ"]
START, END = "20150101", "20241231"
YEARS = list(range(2015, 2025))
PROBE_TSCODE = "000300.SH"
PROBE_START, PROBE_END = "20260901", "20260917"
SLEEP_SECONDS = 0.3
MAX_RETRY = 5


def load_token() -> str:
    if not TOKEN_PATH.exists():
        raise SystemExit(f"token 文件不存在: {TOKEN_PATH.name}（只记录文件名，不读取内容到日志）")
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


def make_log(token: str, log_path: Path):
    def scrub(text: object, limit: int = 600) -> str:
        out = str(text)
        if token:
            out = out.replace(token, "***TOKEN***")
        return out[:limit]

    fh = open(log_path, "a", encoding="utf-8")

    def log(level: str, msg: object):
        line = f"{datetime.now().isoformat(timespec='seconds')} {level} {scrub(msg)}"
        fh.write(line + "\n")
        fh.flush()
        print(line, flush=True)

    log.scrub = scrub
    return log


def call_with_retry(fn, log, **kwargs):
    last = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            return fn(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last = exc
            wait = min(2 ** attempt, 30)
            log("WARN", f"attempt {attempt}/{MAX_RETRY} failed: {exc!r}; retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"API failed after {MAX_RETRY} attempts: {last!r}")


def main() -> int:
    token = load_token()
    RUN_DIR = Path(__file__).resolve().parent
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    log = make_log(token, RUN_DIR / "fetch_console.log")
    log("INFO", f"run start; token_file={TOKEN_FILE_NOTE}")
    log("INFO", f"params: indices={INDICES} range=[{START},{END}] probe={PROBE_TSCODE}")

    import tushare as ts

    pro = ts.pro_api(token)

    # ---- 探针：验证指数接口权限（000300.SH 近 5 个交易日；探针数据不落盘）----
    try:
        probe = pro.index_daily(ts_code=PROBE_TSCODE, start_date=PROBE_START, end_date=PROBE_END)
    except Exception as exc:  # noqa: BLE001
        log("ERROR", f"probe failed (verbatim): {exc!r}")
        return 2
    probe = probe.sort_values("trade_date", ascending=False).head(5)
    if probe.empty:
        log("ERROR", "probe returned 0 rows; 权限或参数异常，停止")
        return 2
    log("INFO", f"probe OK rows={len(probe)}")
    for _, r in probe.iterrows():
        log("INFO", f"probe {r['ts_code']} {r['trade_date']} close={r['close']}")

    # ---- 全量拉取 ----
    manifest = {
        "dataset": "index_daily",
        "batch": "20260917-r1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "tushare pro index_daily",
        "range": [START, END],
        "indices": INDICES,
        "chunks": {},
        "skipped": [],
        "failed": [],
        "notes": [],
        "updated_at": None,
    }
    for ts_code in INDICES:
        out = BATCH_DIR / f"chunk_{ts_code}.csv"
        if out.exists() and out.stat().st_size > 0:
            log("INFO", f"{ts_code}: chunk exists, skip (resume)")
            manifest["skipped"].append(ts_code)
            continue
        parts = []
        for year in YEARS:
            df = call_with_retry(
                pro.index_daily, log,
                ts_code=ts_code, start_date=f"{year}0101", end_date=f"{year}1231",
            )
            log("INFO", f"{ts_code} {year}: rows={len(df)}")
            parts.append(df)
            time.sleep(SLEEP_SECONDS)
        import pandas as pd

        full = pd.concat(parts, ignore_index=True)
        before = len(full)
        full = full[(full["trade_date"] >= START) & (full["trade_date"] <= END)]
        dropped = before - len(full)
        full = full.sort_values("trade_date").reset_index(drop=True)
        full.to_csv(out, index=False, encoding="utf-8")
        manifest["chunks"][ts_code] = {
            "rows": int(len(full)),
            "dropped_out_of_range": int(dropped),
            "done_at": datetime.now().isoformat(timespec="seconds"),
        }
        manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
        log("INFO", f"{ts_code}: written rows={len(full)} dropped_out_of_range={dropped}")

    (BATCH_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    log("INFO", f"manifest written; chunks={list(manifest['chunks'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
