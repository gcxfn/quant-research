# -*- coding: utf-8 -*-
"""Fetch baostock ETF daily bars per trading day, then pivot to per-code files.

Endpoint: bs.query_daily_history_k_ETF(date=...)  (0.9.x dedicated fund endpoint;
query_history_k_data_plus returns empty result sets for fund codes).

Modes (argv[1]):
  canary  - one health probe (2026-02-04, expect >500 rows), exit 0 if healthy
  daemon  - wait for healthy canary, then pull every trading day in window
            (checkpointed staging, retries), pivot to per-code csv+meta, done.
            manifest phase is run separately via pull_etf_daily.py manifest.
"""
from __future__ import annotations

import csv
import json
import socket
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

socket.setdefaulttimeout(30)
import baostock as bs  # noqa: E402

REPO = Path(r"D:\量化")
RUN_DIR = REPO / "artifacts" / "runs" / "20260919T021519-etf-pull-74d0"
TMP = RUN_DIR / "tmp"
STAGING = TMP / "staging"
BATCH_DIR = REPO / "data" / "raw" / "baostock" / "etf-daily-20260919-r1"

START = "2015-01-01"
END = "2024-12-31"  # hard boundary
CANARY_DATE = "2026-02-04"
CANARY_MIN_ROWS = 500
SLEEP_SEC = 0.35
RETRY_PASSES = 4

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def bs_login() -> str:
    lg = bs.login()
    return f"{lg.error_code}/{lg.error_msg}"


def read_rows(rs) -> tuple[str, str, list[list[str]]]:
    """Drain a ResultData. Returns (error_code, error_msg, rows)."""
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    return rs.error_code, rs.error_msg, rows


def canary() -> bool:
    log(f"login: {bs_login()}")
    rs = bs.query_daily_history_k_ETF(date=CANARY_DATE)
    err, msg, rows = read_rows(rs)
    ok = err == "0" and len(rows) >= CANARY_MIN_ROWS
    log(f"canary {CANARY_DATE}: err={err}/{msg} rows={len(rows)} "
        f"fields={rs.fields} -> {'HEALTHY' if ok else 'NOT HEALTHY'}")
    bs.logout()
    return ok


def trading_days() -> list[str]:
    rs = bs.query_trade_dates(start_date=START, end_date=END)
    err, msg, rows = read_rows(rs)
    if err != "0":
        raise RuntimeError(f"query_trade_dates failed: {err}/{msg}")
    days = [r[0] for r in rows if len(r) > 1 and r[1] == "1"]
    log(f"trading days in [{START}, {END}]: {len(days)}")
    return days


def daemon() -> None:
    STAGING.mkdir(parents=True, exist_ok=True)
    wait_start = time.time()
    while not canary():
        if time.time() - wait_start > 2.5 * 3600:
            log("giving up after 2.5h of unhealthy canary; aborting daemon")
            (RUN_DIR / "DAEMON_ABORTED.txt").write_text(
                f"canary unhealthy until {datetime.now().isoformat()}\n", encoding="utf-8"
            )
            return
        log("sleeping 180s before next canary...")
        time.sleep(180)

    days = trading_days()
    todo = [d for d in days if not (STAGING / f"day_{d.replace('-', '')}.csv").exists()]
    log(f"days to fetch: {len(todo)} (staging already has {len(days) - len(todo)})")

    day_log_path = RUN_DIR / "fetch_day_log.jsonl"
    failed: list[str] = []
    t0 = time.time()
    for n, day in enumerate(todo, 1):
        stamp = day.replace("-", "")
        out_path = STAGING / f"day_{stamp}.csv"
        status, error = "ok", None
        for attempt in range(1, 4):
            try:
                rs = bs.query_daily_history_k_ETF(date=day)
                err, msg, rows = read_rows(rs)
                if err != "0":
                    raise RuntimeError(f"{err}/{msg}")
                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f, lineterminator="\n")
                    w.writerow(rs.fields)
                    w.writerows(rows)  # rows are already window-bounded by day list
                break
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                status = "failed"
                log(f"  attempt {attempt} {day} failed: {error}")
                time.sleep(3 * attempt)
                bs_login()
        else:
            failed.append(day)

        with open(day_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "day": day, "status": status, "error": error,
                "rows": 0 if status == "failed" else sum(1 for _ in open(out_path, encoding="utf-8")) - 1,
                "at": datetime.now().isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
        if n % 50 == 0:
            rate = n / max(time.time() - t0, 1e-6)
            log(f"progress {n}/{len(todo)} failed_so_far={len(failed)} "
                f"rate={rate:.2f}/s eta={(len(todo) - n) / max(rate, 1e-6) / 60:.1f}min")
        time.sleep(SLEEP_SEC)

    # retry passes for failed days
    for p in range(2, RETRY_PASSES + 1):
        if not failed:
            break
        log(f"retry pass {p}: {len(failed)} days")
        still = []
        for day in failed:
            stamp = day.replace("-", "")
            out_path = STAGING / f"day_{stamp}.csv"
            try:
                rs = bs.query_daily_history_k_ETF(date=day)
                err, msg, rows = read_rows(rs)
                if err != "0":
                    raise RuntimeError(f"{err}/{msg}")
                with open(out_path, "w", encoding="utf-8", newline="") as f:
                    w = csv.writer(f, lineterminator="\n")
                    w.writerow(rs.fields)
                    w.writerows(rows)
                with open(day_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "day": day, "status": "ok", "error": None,
                        "rows": len(rows), "retry_pass": p,
                        "at": datetime.now().isoformat(timespec="seconds"),
                    }, ensure_ascii=False) + "\n")
            except Exception as exc:  # noqa: BLE001
                still.append(day)
                log(f"  retry pass {p} {day} failed: {exc}")
                time.sleep(3)
                bs_login()
            time.sleep(SLEEP_SEC)
        failed = still

    log(f"day loop done: failed_days={len(failed)} {failed[:20]}")
    bs.logout()
    (RUN_DIR / "FETCH_DAYS_STATUS.json").write_text(json.dumps({
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "days_total": len(days),
        "days_failed": failed,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    pivot()
    log("daemon done")


def pivot() -> None:
    """Turn staging day files into per-code csv + meta.json in the batch dir."""
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    with open(BATCH_DIR / "pool_type5.csv", encoding="utf-8", newline="") as f:
        pool = {r["code"]: r for r in csv.DictReader(f)}

    per_code: dict[str, list[list[str]]] = defaultdict(list)
    fields: list[str] = []
    bad_days: list[str] = []
    for day_path in sorted(STAGING.glob("day_*.csv")):
        with open(day_path, encoding="utf-8", newline="") as f:
            rd = csv.reader(f)
            head = next(rd)
            if not fields:
                fields = head
            elif head != fields:
                bad_days.append(day_path.name)
            for row in rd:
                if row and row[0] <= END:
                    per_code[row[1]].append(row)
    if bad_days:
        log(f"WARNING inconsistent header days: {bad_days}")
    if not fields:
        fields = ["date", "code", "open", "high", "low", "close", "preclose",
                  "volume", "amount", "adjustflag", "turn", "tradestatus",
                  "pctChg", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "isST"]
    idx = {name: i for i, name in enumerate(fields)}
    log(f"pivot: codes_with_data={len(per_code)} pool={len(pool)}")

    adj_values: dict[str, int] = {}
    for code, rows in per_code.items():
        rows.sort(key=lambda r: r[idx["date"]])
        code_adj: set[str] = set()
        for r in rows:
            v = r[idx["adjustflag"]] if "adjustflag" in idx else ""
            adj_values[v] = adj_values.get(v, 0) + 1
            code_adj.add(v)
        csv_path = BATCH_DIR / f"{code}.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(fields)
            w.writerows(rows)
        nonempty = {fld: 0 for fld in fields}
        for r in rows:
            for i, fld in enumerate(fields):
                if r[i] != "":
                    nonempty[fld] += 1
        dates = [r[idx["date"]] for r in rows]
        meta = {
            "code": code,
            "code_name": pool.get(code, {}).get("code_name", ""),
            "fields": fields,
            "n_rows": len(rows),
            "start": min(dates),
            "end": max(dates),
            "adjustflag_observed": sorted(code_adj),
            "frequency": "d (daily snapshot endpoint)",
            "nonempty": nonempty,
            "out_of_window_rows_dropped": 0,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        (BATCH_DIR / f"{code}.csv.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    # codes in pool with no data in window -> explicit zero-row files
    zero = sorted(set(pool) - set(per_code))
    for code in zero:
        with open(BATCH_DIR / f"{code}.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(fields)
        meta = {
            "code": code,
            "code_name": pool.get(code, {}).get("code_name", ""),
            "fields": fields,
            "n_rows": 0,
            "start": None,
            "end": None,
            "adjustflag_observed": "",
            "frequency": "d (daily snapshot endpoint)",
            "nonempty": {fld: 0 for fld in fields},
            "out_of_window_rows_dropped": 0,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        (BATCH_DIR / f"{code}.csv.meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    log(f"pivot done: codes_with_data={len(per_code)} zero_row={len(zero)} "
        f"adjustflag_observed_values={adj_values}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "canary"
    if mode == "canary":
        sys.exit(0 if canary() else 3)
    elif mode == "pivot":
        pivot()
    elif mode == "daemon":
        daemon()
    else:
        raise SystemExit(f"unknown mode {mode}")
