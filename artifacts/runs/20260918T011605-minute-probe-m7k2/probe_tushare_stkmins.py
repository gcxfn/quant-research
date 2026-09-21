# -*- coding: utf-8 -*-
"""tushare stk_mins 分钟接口探测（第 2、3 次调用，样本 ≤2024-12-31）。

fund_mins 在 SDK/服务端不存在（第 1 次调用已证实，见 tushare_probe_results.json）；
SDK 源码 data_pro.py L176-177 显示 pro_bar(asset='FD', freq='min') 路由到 stk_mins，
故 ETF 分钟的正确探测接口为 stk_mins。

纪律：token 只在本进程内读取使用，绝不打印/落盘；样本固定 510300.SH ×
2024-06-03..2024-06-07（冻结边界内）；只保存脱敏行情样本。
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
RESULT = RUN / "tushare_probe_results.json"

START = "2024-06-03 09:00:00"
END = "2024-06-07 15:00:00"


def do_call(pro, ts_code: str, name: str, freq: str, call_no: int) -> dict:
    rec: dict = {
        "call_no": call_no,
        "api": name,
        "freq": freq,
        "ts_code": ts_code,
        "start": START,
        "end": END,
    }
    t0 = time.perf_counter()
    try:
        df = getattr(pro, name)(ts_code=ts_code, freq=freq, start_date=START, end_date=END)
        rec["elapsed_seconds"] = round(time.perf_counter() - t0, 3)
        rec["rows"] = int(df.height)
        if df.height:
            rec["status"] = "OK"
            rec["columns"] = list(df.columns)
            tcol = "trade_time" if "trade_time" in df.columns else df.columns[1]
            s = df[tcol].astype(str)
            rec["min_time"] = str(s.min())
            rec["max_time"] = str(s.max())
            rec["bars_at_1130"] = int(s.str.contains("11:30").sum())
            rec["sample_rows_sanitized"] = df.head(3).to_dict("records")
        else:
            rec["status"] = "EMPTY"
        print(f"call {call_no}: {name} {ts_code} freq={freq} -> {rec['status']} "
              f"rows={rec.get('rows')} 1130bars={rec.get('bars_at_1130')} "
              f"{rec.get('elapsed_seconds')}s")
    except Exception as e:  # noqa: BLE001
        rec["status"] = "FAILED"
        rec["error_type"] = type(e).__name__
        rec["error_msg"] = str(e)[:500]
        rec["traceback_tail"] = traceback.format_exc()[-400:]
        rec["elapsed_seconds"] = round(time.perf_counter() - t0, 3)
        print(f"call {call_no}: {name} {ts_code} freq={freq} FAILED {type(e).__name__}: {str(e)[:200]}")
    return rec


def main() -> None:
    token = TOKEN_PATH.read_text(encoding="utf-8").strip()
    ts.set_token(token)
    pro = ts.pro_api()

    out = json.loads(RESULT.read_text(encoding="utf-8"))
    calls = out["calls"]

    # 调用 2：stk_mins 5min —— ETF 是否能通过 stk_mins 取得分钟数据
    rec2 = do_call(pro, "510300.SH", "stk_mins", "5min", 2)
    calls.append(rec2)

    # 调用 3：若 ETF 可取，验证 60min 的 11:30 bar 边界；否则用一只股票
    # 诊断 token 是否根本无分钟权限（为风险节提供事实）。
    if rec2["status"] in ("OK", "EMPTY"):
        rec3 = do_call(pro, "510300.SH", "stk_mins", "60min", 3)
    else:
        rec3 = do_call(pro, "600000.SH", "stk_mins", "5min", 3)
    calls.append(rec3)

    out["note_api_routing"] = (
        "SDK data_pro.py: pro_bar(asset='FD', freq='min') routes to stk_mins; "
        "fund_mins does not exist (call 1 server error)"
    )
    RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("updated ->", RESULT)


if __name__ == "__main__":
    main()
