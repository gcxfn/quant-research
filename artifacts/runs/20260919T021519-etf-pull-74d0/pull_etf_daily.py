# -*- coding: utf-8 -*-
"""Baostock ETF daily bar pull (run 20260919T021519-etf-pull-74d0).

Phases:
  pool      - query_stock_basic full pull, filter type=5, diff vs tushare fund_daily 1169
  fetch     - per-code query_history_k_data_plus d/adjustflag=3, 2015-01-01..2024-12-31
  manifest  - build batch manifest.json + sha256.tsv from on-disk state

Hard boundary: end date is pinned to 2024-12-31; any row outside
[2015-01-01, 2024-12-31] is dropped before writing and counted.
"""
from __future__ import annotations

import csv
import hashlib
import json
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

import baostock as bs

socket.setdefaulttimeout(30)  # baostock 内部走默认 socket, 防单条查询无限挂起

REPO = Path(r"D:\量化")
RUN_DIR = REPO / "artifacts" / "runs" / "20260919T021519-etf-pull-74d0"
TMP = RUN_DIR / "tmp"
BATCH_DIR = REPO / "data" / "raw" / "baostock" / "etf-daily-20260919-r1"
TUSHARE_FUND_DAILY = REPO / "data" / "raw" / "tushare" / "fund_daily" / "20260917-r1"

START = "2015-01-01"
END = "2024-12-31"  # hard boundary, never extend
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,tradestatus"
FIELD_LIST = FIELDS.split(",")
SLEEP_SEC = 0.4
MAX_RETRY = 3

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)


def bs_call(fn, *args, **kwargs):
    """Call a baostock query with retry + re-login on failure."""
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            rs = fn(*args, **kwargs)
            if rs.error_code != "0":
                raise RuntimeError(
                    f"baostock error {rs.error_code}: {rs.error_msg}"
                )
            rows = []
            while (rs.next()):
                rows.append(rs.get_row_data())
            return rs.fields, rows
        except Exception as exc:  # noqa: BLE001 - need broad retry on network
            last_err = exc
            log(f"  attempt {attempt} failed: {exc}")
            time.sleep(2 * attempt)
            try:
                bs.login()
            except Exception:  # noqa: BLE001
                pass
    raise RuntimeError(f"baostock call failed after {MAX_RETRY} attempts: {last_err}")


def to_ts_code(bs_code: str) -> str:
    exch, num = bs_code.split(".")
    suffix = "SH" if exch.lower() == "sh" else "SZ"
    return f"{num}.{suffix}"


def to_bs_code(ts_code: str) -> str:
    num, suffix = ts_code.split(".")
    return f"{'sh' if suffix == 'SH' else 'sz'}.{num}"


TUSHARE_FUND_BASIC = (
    REPO / "data" / "raw" / "tushare" / "fund_basic" / "20260909-r1" / "chunk_market_E.csv"
)


# ---------------------------------------------------------------- pool phase
def phase_pool() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    lg = bs.login()
    log(f"login: {lg.error_code} {lg.error_msg}")

    fields, rows = bs_call(bs.query_stock_basic)
    log(f"query_stock_basic: {len(rows)} rows, fields={fields}")

    with open(TMP / "stock_basic_all.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(fields)
        w.writerows(rows)

    idx = {name: i for i, name in enumerate(fields)}
    pool_rows = [r for r in rows if r[idx["type"]] == "5"]
    pool_rows.sort(key=lambda r: r[idx["code"]])
    log(f"type=5 ETF pool: {len(pool_rows)} codes "
        f"(listed={sum(1 for r in pool_rows if r[idx['status']] == '1')}, "
        f"delisted={sum(1 for r in pool_rows if r[idx['status']] == '0')})")
    bs_codes_ts = [to_ts_code(r[idx["code"]]) for r in pool_rows]
    bs_set = set(bs_codes_ts)

    # baostock stock_basic 名录里的 ETF 全部在市 (全表 1,187 条退市记录均非 type=5)。
    # 为满足"含已退市"，用盘上 tushare fund_basic (market=E, 名称含 ETF, list_date<=20241231)
    # 补齐名录缺失的退市 ETF，逐行标注 pool_source。
    with open(TUSHARE_FUND_BASIC, encoding="utf-8", newline="") as f:
        fb = list(csv.DictReader(f))
    fb_etf = [
        r for r in fb
        if r["market"] == "E" and "ETF" in r["name"] and r["list_date"] <= "20241231"
    ]
    supp = [r for r in fb_etf if r["ts_code"] not in bs_set]
    supp_delisted = [r for r in supp if r["delist_date"] not in ("", "None")]
    log(f"tushare fund_basic ETF(list<=20241231): {len(fb_etf)}, "
        f"supplement not in baostock 名录: {len(supp)} "
        f"(delisted={len(supp_delisted)})")

    pool_path = BATCH_DIR / "pool_type5.csv"
    with open(pool_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["code", "code_name", "ipoDate", "outDate", "type", "status", "pool_source"])
        for r in pool_rows:
            w.writerow([
                r[idx["code"]], r[idx["code_name"]], r[idx["ipoDate"]],
                r[idx["outDate"]], "5", r[idx["status"]],
                "baostock_query_stock_basic_type5",
            ])
        for r in sorted(supp, key=lambda r: to_bs_code(r["ts_code"])):
            w.writerow([
                to_bs_code(r["ts_code"]), r["name"], r["list_date"],
                "" if r["delist_date"] in ("", "None") else r["delist_date"],
                "5", "0", "tushare_fund_basic_supplement",
            ])

    tushare_codes = sorted(
        p.stem.removeprefix("chunk_")
        for p in TUSHARE_FUND_DAILY.glob("chunk_*.csv")
    )
    ts_set = set(tushare_codes)
    diff = {
        "generated_at": now(),
        "note": (
            "差集以 baostock query_stock_basic type=5 名录 (1678) 为一侧; "
            "baostock 名录不含退市 ETF (全表退市记录均非 type=5), "
            "退市缺失已用 tushare fund_basic 补齐进 pool_type5.csv (pool_source 列)"
        ),
        "baostock_pool_count": len(pool_rows),
        "tushare_fund_daily_count": len(tushare_codes),
        "overlap_count": len(bs_set & ts_set),
        "baostock_only": sorted(bs_set - ts_set),
        "tushare_only": sorted(ts_set - bs_set),
        "supplement_from_fund_basic_count": len(supp),
        "supplement_delisted_count": len(supp_delisted),
        "supplement_codes": sorted(to_bs_code(r["ts_code"]) for r in supp),
    }
    (RUN_DIR / "pool_diff.json").write_text(
        json.dumps(diff, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    log(f"diff: overlap={diff['overlap_count']}, "
        f"baostock_only={len(diff['baostock_only'])}, "
        f"tushare_only={len(diff['tushare_only'])} -> pool_diff.json")

    # 探针: 验证 baostock 对退市 ETF 代码是否仍返回历史 K 线
    probe = next(
        (r for r in supp
         if r["delist_date"] not in ("", "None")
         and r["delist_date"] <= "20241231" and r["list_date"] >= "20150101"),
        None,
    )
    if probe:
        pcode = to_bs_code(probe["ts_code"])
        try:
            _, prows = bs_call(
                bs.query_history_k_data_plus, pcode, FIELDS,
                startdate=START, enddate=END, frequency="d", adjustflag="3",
            )
            log(f"probe delisted {pcode} ({probe['name']}, "
                f"list {probe['list_date']} delist {probe['delist_date']}): "
                f"{len(prows)} rows in window")
        except Exception as exc:  # noqa: BLE001
            log(f"probe delisted {pcode} FAILED: {exc}")
    bs.logout()


# --------------------------------------------------------------- fetch phase
def phase_fetch() -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    pool_csv = BATCH_DIR / "pool_type5.csv"
    with open(pool_csv, encoding="utf-8", newline="") as f:
        pool = list(csv.DictReader(f))
    log(f"pool loaded: {len(pool)} codes")

    lg = bs.login()
    log(f"login: {lg.error_code} {lg.error_msg}")

    log_path = RUN_DIR / "fetch_log.jsonl"
    done, skipped, failed = 0, 0, 0
    t0 = time.time()
    for n, row in enumerate(pool, 1):
        code = row["code"]
        csv_path = BATCH_DIR / f"{code}.csv"
        meta_path = BATCH_DIR / f"{code}.csv.meta.json"
        if csv_path.exists() and meta_path.exists():
            skipped += 1
            continue

        status, error, dropped = "ok", None, 0
        try:
            _, rows = bs_call(
                bs.query_history_k_data_plus,
                code, FIELDS,
                start_date=START, end_date=END,
                frequency="d", adjustflag="3",
            )
            kept = []
            for r in rows:
                d = r[0]
                if START <= d <= END:
                    kept.append(r)
                else:
                    dropped += 1
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(FIELD_LIST)
                w.writerows(kept)
            nonempty = {fld: 0 for fld in FIELD_LIST}
            for r in kept:
                for i, fld in enumerate(FIELD_LIST):
                    if r[i] != "":
                        nonempty[fld] += 1
            dates = [r[0] for r in kept]
            meta = {
                "code": code,
                "code_name": row.get("code_name", ""),
                "fields": FIELD_LIST,
                "n_rows": len(kept),
                "start": min(dates) if dates else None,
                "end": max(dates) if dates else None,
                "adjustflag": "3",
                "frequency": "d",
                "nonempty": nonempty,
                "out_of_window_rows_dropped": dropped,
                "fetched_at": now(),
            }
            meta_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            if dropped:
                log(f"  WARNING {code}: dropped {dropped} out-of-window rows")
        except Exception as exc:  # noqa: BLE001 - record and continue
            status, error = "failed", str(exc)
            failed += 1
            log(f"  FAILED {code}: {error}")

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "code": code, "status": status, "error": error,
                "at": now(),
            }, ensure_ascii=False) + "\n")
        done += 1
        if done % 25 == 0:
            rate = done / max(time.time() - t0, 1e-6)
            remain = (len(pool) - skipped - done) / max(rate, 1e-6)
            log(f"progress {done + skipped}/{len(pool)} "
                f"(failed={failed}) rate={rate:.2f}/s eta={remain/60:.1f}min")
        time.sleep(SLEEP_SEC)

    log(f"fetch loop done: new={done} skipped={skipped} failed={failed}")
    bs.logout()


# ------------------------------------------------------------ manifest phase
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def phase_manifest() -> None:
    with open(BATCH_DIR / "pool_type5.csv", encoding="utf-8", newline="") as f:
        pool = list(csv.DictReader(f))

    metas = {}
    for p in sorted(BATCH_DIR.glob("*.csv.meta.json")):
        metas[p.name.removesuffix(".meta.json")] = json.loads(
            p.read_text(encoding="utf-8")
        )

    fetch_log = RUN_DIR / "fetch_log.jsonl"
    failed_codes = []
    if fetch_log.exists():
        last = {}
        for line in fetch_log.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            last[rec["code"]] = rec["status"]
        failed_codes = sorted(c for c, s in last.items() if s == "failed")

    zero_rows = sorted(c for c, m in metas.items() if m["n_rows"] == 0)
    total_rows = sum(m["n_rows"] for m in metas.values())
    nonempty = {fld: 0 for fld in FIELD_LIST}
    for m in metas.values():
        for fld, cnt in m.get("nonempty", {}).items():
            nonempty[fld] += cnt
    dropped_total = sum(m.get("out_of_window_rows_dropped", 0) for m in metas.values())
    missing = sorted({r["code"] for r in pool} - set(metas))

    diff_path = RUN_DIR / "pool_diff.json"
    diff = json.loads(diff_path.read_text(encoding="utf-8")) if diff_path.exists() else None

    status = "completed"
    if failed_codes or missing:
        status = "partial"

    chunks = {
        code: {
            "code": code,
            "code_name": m.get("code_name", ""),
            "rows": m["n_rows"],
            "first_date": m["start"],
            "last_date": m["end"],
            "out_of_window_rows_dropped": m.get("out_of_window_rows_dropped", 0),
            "sha256": sha256_of(BATCH_DIR / f"{code}.csv"),
        }
        for code, m in sorted(metas.items())
    }

    manifest = {
        "dataset": "etf_daily",
        "batch": "etf-daily-20260919-r1",
        "created_at": now(),
        "status": status,
        "source": "baostock query_history_k_data_plus",
        "frequency": "d",
        "adjustflag": "3 (不复权, 与股票腿 data/raw/baostock/daily 同口径)",
        "range": {
            "start": START,
            "end": END,
            "hard_boundary": "请求与落盘均不得越过 2024-12-31; 窗口外行丢弃并计数",
        },
        "fields_requested": FIELD_LIST,
        "fields_nonempty_counts": nonempty,
        "universe": {
            "source": (
                "baostock query_stock_basic 全量 type=5 (名录仅含在市 ETF); "
                "名录不含退市 ETF, 已用 tushare fund_basic "
                "(market=E, 名称含 ETF, list_date<=20241231) 补齐退市, pool_source 列区分"
            ),
            "count": len(pool),
            "pool_file": "pool_type5.csv",
            "status_listed": sum(1 for r in pool if r["status"] == "1"),
            "status_delisted": sum(1 for r in pool if r["status"] == "0"),
            "pool_source_counts": {
                src: sum(1 for r in pool if r["pool_source"] == src)
                for src in sorted({r["pool_source"] for r in pool})
            },
        },
        "diff_vs_tushare_fund_daily": (
            {
                "tushare_batch": "data/raw/tushare/fund_daily/20260917-r1 (1169 codes)",
                "overlap_count": diff["overlap_count"],
                "baostock_only_count": len(diff["baostock_only"]),
                "tushare_only_count": len(diff["tushare_only"]),
                "supplement_from_fund_basic_count": diff["supplement_from_fund_basic_count"],
                "supplement_delisted_count": diff["supplement_delisted_count"],
                "detail_file": "artifacts/runs/20260919T021519-etf-pull-74d0/pool_diff.json",
            }
            if diff
            else "pool_diff.json missing"
        ),
        "totals": {
            "codes_in_pool": len(pool),
            "codes_fetched": len(metas),
            "codes_missing": len(missing),
            "codes_zero_rows": len(zero_rows),
            "codes_failed": len(failed_codes),
            "rows_total": total_rows,
            "out_of_window_rows_dropped": dropped_total,
        },
        "zero_row_codes": zero_rows,
        "failed_codes": failed_codes,
        "missing_codes": missing,
        "run_dir": "artifacts/runs/20260919T021519-etf-pull-74d0",
        "env": {
            "python": sys.version.split()[0],
            "baostock": "0.9.3",
            "install_note": (
                "baostock 0.9.3 于本次运行经 uv pip 装入仓库 .venv "
                "(纯 Python, 未改 pyproject/uv.lock, 未动其他包)"
            ),
            "os": "Windows",
        },
        "chunks": chunks,
        "sha256_file": "sha256.tsv",
    }
    (BATCH_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    rows = []
    for p in sorted(BATCH_DIR.iterdir()):
        if p.name in ("manifest.json", "sha256.tsv"):
            continue
        if p.is_file():
            rows.append(f"{p.name}\t{p.stat().st_size}\t{sha256_of(p)}")
    (BATCH_DIR / "sha256.tsv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8", newline=""
    )
    log(f"manifest: status={status}, codes={len(metas)}, rows={total_rows}, "
        f"zero_rows={len(zero_rows)}, failed={len(failed_codes)}, missing={len(missing)}")


if __name__ == "__main__":
    phases = sys.argv[1].split(",") if len(sys.argv) > 1 else ["pool", "fetch", "manifest"]
    for ph in phases:
        log(f"=== phase {ph} start ===")
        {"pool": phase_pool, "fetch": phase_fetch, "manifest": phase_manifest}[ph]()
        log(f"=== phase {ph} done ===")
