# -*- coding: utf-8 -*-
"""tushare fund_mins 分钟接口可行性探测（≤3 次调用，样本 ≤2024-12-31）。

纪律：
- token 从 ~/.quant-credentials/tushare-token 读取，只在本进程内使用，
  绝不打印 / 写日志 / 落盘。
- 样本固定 510300.SH × 2024-06-03..2024-06-07（冻结边界内）。
- 每次调用记录：接口名、freq、可用性、耗时、行数、字段、起止时间、截断迹象。
- 响应只保存脱敏样本（前 3 行行情值），不含任何凭据。
"""
from __future__ import annotations

import json
import time
import traceback
from pathlib import Path

import tushare as ts

REPO = Path(r"D:/量化")
RUN = REPO / "artifacts/runs/20260918T011605-minute-probe-m7k2"
TOKEN_PATH = Path.home() / ".quant-credentials" / "tushare-token"

TS_CODE = "510300.SH"
START = "2024-06-03 09:00:00"
END = "2024-06-07 15:00:00"

calls: list[dict] = []


def do_call(pro, name: str, freq: str, call_no: int) -> None:
    rec: dict = {
        "call_no": call_no,
        "api": name,
        "freq": freq,
        "ts_code": TS_CODE,
        "start": START,
        "end": END,
    }
    t0 = time.perf_counter()
    try:
        df = getattr(pro, name)(
            ts_code=TS_CODE, freq=freq, start_date=START, end_date=END
        )
        rec["elapsed_seconds"] = round(time.perf_counter() - t0, 3)
        rec["status"] = "OK"
        rec["rows"] = int(df.height)
        rec["columns"] = list(df.columns)
        rec["min_time"] = str(df.iloc[:, 1].min()) if df.height else None
        rec["max_time"] = str(df.iloc[:, 1].max()) if df.height else None
        bars_1130 = 0
        tcol = df.columns[1]
        if df.height:
            s = df[tcol].astype(str)
            bars_1130 = int(s.str.contains("11:30").sum())
        rec["bars_at_1130"] = bars_1130
        rec["sample_rows_sanitized"] = df.head(3).to_dict("records")
        print(f"call {call_no}: {name} freq={freq} OK rows={df.height} "
              f"1130bars={bars_1130} {rec['elapsed_seconds']}s cols={list(df.columns)}")
    except Exception as e:  # noqa: BLE001
        rec["elapsed_seconds"] = round(time.perf_counter() - t0, 3)
        rec["status"] = "FAILED"
        rec["error_type"] = type(e).__name__
        rec["error_msg"] = str(e)[:500]
        rec["traceback_tail"] = traceback.format_exc()[-600:]
        print(f"call {call_no}: {name} freq={freq} FAILED {type(e).__name__}: {str(e)[:200]}")
    calls.append(rec)


def main() -> None:
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("token file empty")
    ts.set_token(token)
    pro = ts.pro_api()

    # 调用 1：fund_mins 5min —— ETF 分钟可用性的决定性测试
    do_call(pro, "fund_mins", "5min", 1)
    ok1 = calls[0]["status"] == "OK"

    # 调用 2/3：仅在调用 1 成功后验证 30min / 60min 的 11:30 bar 边界语义
    if ok1:
        do_call(pro, "fund_mins", "30min", 2)
        do_call(pro, "fund_mins", "60min", 3)
    else:
        print("call 1 failed; no further minute calls (avoid wasting quota)")

    out = {
        "tushare_version": getattr(ts, "__version__", "unknown"),
        "token_file": str(TOKEN_PATH),
        "token_content": "NOT_RECORDED",
        "probe_window": {"start": START, "end": END, "frozen_boundary_ok": True},
        "calls": calls,
    }
    (RUN / "tushare_probe_results.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("saved ->", RUN / "tushare_probe_results.json")


if __name__ == "__main__":
    main()
