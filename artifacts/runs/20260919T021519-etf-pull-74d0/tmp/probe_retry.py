# -*- coding: utf-8 -*-
"""Retry probe: wait for one healthy stock k-data response, then A/B ETF codes.

Writes one JSON line per attempt to stdout. Stops early when a stock query
succeeds (n>=1 rows) and the ETF A/B result has been captured.
"""
from __future__ import annotations

import json
import socket
import sys
import time
from datetime import datetime

socket.setdefaulttimeout(20)
import baostock as bs  # noqa: E402

CODES = ["sh.600000", "sh.000300", "sh.510300", "sz.159915", "sh.510050"]
ATTEMPTS = 8
WAIT_SEC = 150

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def try_query(bs, code, fields="date,code,close", start="2023-01-01", end="2024-12-31"):
    rs = bs.query_history_k_data_plus(
        code, fields, start_date=start, end_date=end, frequency="d", adjustflag="3"
    )
    n = 0
    first = None
    while rs.next():
        if first is None:
            first = rs.get_row_data()
        n += 1
    return {"code": code, "err": rs.error_code, "msg": rs.error_msg,
            "rows": n, "first": first}


stock_ok = False
for attempt in range(1, ATTEMPTS + 1):
    rec = {"attempt": attempt, "at": datetime.now().isoformat(timespec="seconds"),
           "results": []}
    try:
        lg = bs.login()
        rec["login"] = lg.error_code
        for code in CODES:
            t0 = time.time()
            r = try_query(bs, code)
            r["sec"] = round(time.time() - t0, 1)
            rec["results"].append(r)
            if code == "sh.600000" and r["rows"] > 0:
                stock_ok = True
        bs.logout()
    except Exception as exc:  # noqa: BLE001
        rec["exception"] = f"{type(exc).__name__}: {exc}"
        try:
            bs.logout()
        except Exception:  # noqa: BLE001
            pass
    print(json.dumps(rec, ensure_ascii=False), flush=True)
    if stock_ok:
        print(json.dumps({"conclusion": "stock_ok_reached"}, flush=True))
        break
    if attempt < ATTEMPTS:
        time.sleep(WAIT_SEC)
