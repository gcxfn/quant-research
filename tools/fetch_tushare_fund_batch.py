# -*- coding: utf-8 -*-
"""tushare 场内基金（ETF）日线/复权因子与个股涨跌停价 raw 批次拉取工具。

纪律:
- token 只从 ~/.quant-credentials/tushare-token 读取；任何日志/manifest/异常文本
  在写出前统一 scrub，token 字面量绝不落盘、不打印。
- 研究窗口硬边界 20150101-20241231；2025-01-01 及以后一个请求都不发。
- 断点续传: manifest.json 逐 chunk 更新（原子写），已成功且 sha256 一致的 chunk 跳过。
- 限速: 默认每请求间隔 --sleep 秒；命中频控报错时退避 30s 重试，重试与失败全记录。
- 预算: --budget-min 到点后停在 chunk 边界，manifest 状态记 partial 并写 remaining。

用法:
  python tools/fetch_tushare_fund_batch.py probe --run-dir <run_dir>
  python tools/fetch_tushare_fund_batch.py funds --datasets fund_daily,fund_adj \
      --budget-min 150 --run-dir <run_dir>
  python tools/fetch_tushare_fund_batch.py stk-limit --budget-min 90 --run-dir <run_dir>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw" / "tushare"
TOKEN_PATH = Path.home() / ".quant-credentials" / "tushare-token"

BATCH = "20260917-r1"
START_DATE = "20150101"
END_DATE = "20241231"  # 硬边界: 2025+ 冻结，绝不请求

FUND_BASIC_CSV = RAW / "fund_basic" / "20260909-r1" / "chunk_market_E.csv"

FUND_DAILY_COLS = ["ts_code", "trade_date", "pre_close", "open", "high", "low", "close",
                   "change", "pct_chg", "vol", "amount"]  # 与 tushare 返回列序一致
FUND_ADJ_COLS = ["ts_code", "trade_date", "adj_factor"]
STK_LIMIT_COLS = ["trade_date", "ts_code", "up_limit", "down_limit"]  # 实测无 pre_close 列

RATE_LIMIT_HINTS = ("每分钟", "每小时", "每天最多", "频", "次数超过", "limit", "Sorry", "抱歉", "积分")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def scrub(text: str, token: str) -> str:
    """移除任何可能携带 token 字面量的片段，截断超长报错。"""
    out = str(text)
    if token:
        out = out.replace(token, "***TOKEN***")
    return re.sub(r"\s+", " ", out)[:400]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def atomic_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load_token() -> str:
    if not TOKEN_PATH.exists():
        raise SystemExit(f"token 文件不存在: {TOKEN_PATH.name}（只记录文件名，不读内容到日志）")
    return TOKEN_PATH.read_text(encoding="utf-8").strip()


def setup_logger(run_dir: Path, name: str, token: str):
    run_dir.mkdir(parents=True, exist_ok=True)
    import logging
    log_path = run_dir / "logs" / f"fetch_{name}_{BATCH}.log"
    logger = logging.getLogger(f"fetch.{name}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)

    class Scrubbing:
        def __init__(self, fn):
            self.fn = fn

        def _fmt(self, msg, a):
            return self.fn(scrub(msg % a if a else msg, token))

        def __call__(self, msg, *a):
            self._fmt(msg, a)

        def info(self, msg, *a):
            self.fn("INFO " + scrub(msg % a if a else msg, token))

        warning = info

        def error(self, msg, *a):
            self.fn("ERROR " + scrub(msg % a if a else msg, token))

    return Scrubbing(logger.info), Scrubbing(logger.warning), Scrubbing(logger.error), log_path


def load_universe(log) -> list[dict]:
    """ETF 名册: market=E、名称含 ETF、list_date<=20241231、(delist 空 或 >=20150101)。"""
    rows = list(csv.DictReader(open(FUND_BASIC_CSV, encoding="utf-8-sig")))
    sel = []
    for r in rows:
        if r["market"] != "E" or "ETF" not in (r["name"] or "").upper():
            continue
        ld = r["list_date"] or ""
        dd = r["delist_date"] or ""
        if len(ld) != 8 or ld > END_DATE:
            continue
        if dd and dd < START_DATE:
            continue
        sel.append({"ts_code": r["ts_code"], "name": r["name"], "list_date": ld,
                    "delist_date": dd, "status": r["status"]})
    sel.sort(key=lambda x: x["ts_code"])
    log.info("universe: %d ETF (from %s, filter market=E + name~ETF + list<=20241231 + delist>=20150101)",
             len(sel), FUND_BASIC_CSV.relative_to(REPO))
    return sel


def call_with_retry(pro, api_name: str, params: dict, log, token: str,
                    max_attempts: int = 5):
    """带频控退避的接口调用；返回 (df, attempts, errors)。"""
    import time as _t
    errors = []
    for attempt in range(1, max_attempts + 1):
        try:
            df = getattr(pro, api_name)(**params)
            return df, attempt, errors
        except Exception as exc:  # noqa: BLE001 - tushare 抛裸 Exception
            msg = scrub(exc, token)
            errors.append(msg)
            wait = 30 if any(h.lower() in msg.lower() for h in RATE_LIMIT_HINTS) else min(2 ** attempt, 16)
            log.error("attempt %d FAILED %s %s: %s -> backoff %ds",
                      attempt, api_name, json.dumps(params, ensure_ascii=False), msg, wait)
            _t.sleep(wait + random.random())
    raise RuntimeError(f"{api_name} failed after {max_attempts} attempts: {errors[-1]}")


def write_chunk_csv(df, path: Path, cols: list[str]) -> int:
    if df is None or len(df) == 0:
        path.write_text(",".join(cols) + "\r\n", encoding="utf-8")
        return 0
    df = df.sort_values("trade_date").reset_index(drop=True)
    df[cols].to_csv(path, index=False, encoding="utf-8", lineterminator="\r\n")
    return len(df)


def manifest_ok(batch_dir: Path, manifest: dict, fname: str) -> bool:
    ent = manifest.get("chunks", {}).get(fname)
    if not ent or "sha256" not in ent:
        return False
    f = batch_dir / fname
    return f.exists() and sha256_file(f) == ent["sha256"]


def budget_left(deadline: float) -> bool:
    return time.monotonic() < deadline


# ---------------------------------------------------------------- funds 模式
def run_funds(pro, datasets: list[str], budget_min: float, sleep_s: float,
              limit: int | None, run_dir: Path, log, wlog, elog) -> None:
    token = load_token()  # 仅用于 scrub，不输出
    universe_full = load_universe(log)
    universe = universe_full[:limit] if limit else universe_full
    if limit:
        log.info("--limit: only first %d ETF this pass", limit)
    deadline = time.monotonic() + budget_min * 60

    for ds in datasets:
        cols = FUND_DAILY_COLS if ds == "fund_daily" else FUND_ADJ_COLS
        batch_dir = RAW / ds / BATCH
        batch_dir.mkdir(parents=True, exist_ok=True)
        mpath = batch_dir / "manifest.json"
        manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {
            "dataset": ds, "batch": BATCH, "created_at": now(),
            "source": f"tushare pro {ds}",
            "token_file": "~/.quant-credentials/tushare-token (name only; content never read into logs)",
            "range": {"start": START_DATE, "end": END_DATE},
            "universe": {"source": "data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv",
                         "filter": "market==E and 'ETF' in name and list_date<=20241231 and (delist_date empty or >=20150101)",
                         "count": None},
            "chunks": {}, "skipped": [], "failed": [], "notes": [], "status": "running",
        }
        manifest["universe"]["count"] = len(universe_full)
        manifest["status"] = "running"
        manifest["updated_at"] = now()
        atomic_json(mpath, manifest)

        done = skipped = failed = 0
        for i, fund in enumerate(universe):
            code = fund["ts_code"]
            fname = f"chunk_{code}.csv"
            fpath = batch_dir / fname
            if manifest_ok(batch_dir, manifest, fname):
                skipped += 1
                continue
            if not budget_left(deadline):
                remaining = [f["ts_code"] for f in universe[i:]]
                manifest["status"] = "partial"
                manifest["notes"].append(f"{now()} budget {budget_min}min reached; remaining {len(remaining)} ETF")
                manifest["remaining"] = remaining
                atomic_json(mpath, manifest)
                log.warning("budget reached at %d/%d; stopping %s in resumable state", i, len(universe), ds)
                break
            try:
                df, attempts, _errs = call_with_retry(
                    pro, ds, {"ts_code": code, "start_date": START_DATE, "end_date": END_DATE},
                    log, token)
                rows = write_chunk_csv(df, fpath, cols)
                if rows > 0:
                    mx = str(df["trade_date"].max())
                    assert mx <= END_DATE, f"trade_date {mx} outside frozen window!"
                else:
                    mx = ""
                manifest["chunks"][fname] = {
                    "ts_code": code, "rows": int(rows),
                    "first_trade_date": str(df["trade_date"].min()) if rows else "",
                    "last_trade_date": mx,
                    "done_at": now(), "attempts": attempts,
                    "sha256": sha256_file(fpath),
                }
                manifest["updated_at"] = now()
                atomic_json(mpath, manifest)
                done += 1
                if rows == 0:
                    manifest.setdefault("skipped", []).append(f"{code}: empty result (0 rows) at {now()}")
                    atomic_json(mpath, manifest)
                log.info("[%s %d/%d] %s rows=%d span=%s..%s attempts=%d",
                         ds, i + 1, len(universe), code, rows,
                         manifest["chunks"][fname]["first_trade_date"], mx, attempts)
            except Exception as exc:  # noqa: BLE001
                manifest["failed"].append({"ts_code": code, "at": now(), "error": scrub(exc, token)})
                atomic_json(mpath, manifest)
                elog("chunk FAILED %s %s (recorded in manifest.failed)", ds, code)
                failed += 1
            time.sleep(sleep_s + random.random() * 0.1)
        else:
            manifest["status"] = "completed" if not manifest["failed"] else "completed-with-failures"
        if manifest.get("status") == "running":
            manifest["status"] = "partial"
        manifest["updated_at"] = now()
        manifest["finished_at"] = now()
        atomic_json(mpath, manifest)
        log.info("%s batch %s done: new=%d skipped(resumed)=%d failed=%d status=%s",
                 ds, BATCH, done, skipped, failed, manifest["status"])


# ------------------------------------------------------------- stk-limit 模式
def load_trade_days() -> list[str]:
    days = set()
    for p in (RAW / "trade_cal" / "20260909-r1").glob("chunk_sse_*.csv"):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r["is_open"] == "1" and START_DATE <= r["cal_date"] <= END_DATE:
                days.add(r["cal_date"])
    return sorted(days)


def run_stk_limit(pro, budget_min: float, sleep_s: float, limit: int | None,
                  run_dir: Path, log, wlog, elog) -> None:
    token = load_token()
    days = load_trade_days()
    log.info("trade days 2015-2024 (SSE open): %d", len(days))
    if limit:
        days = days[:limit]
    deadline = time.monotonic() + budget_min * 60
    ds = "stk_limit"
    batch_dir = RAW / ds / BATCH
    batch_dir.mkdir(parents=True, exist_ok=True)
    mpath = batch_dir / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {
        "dataset": ds, "batch": BATCH, "created_at": now(),
        "source": "tushare pro stk_limit (per trade_date)",
        "token_file": "~/.quant-credentials/tushare-token (name only)",
        "range": {"start": START_DATE, "end": END_DATE},
        "trade_cal": "data/raw/tushare/trade_cal/20260909-r1 (SSE is_open==1, clipped to 2015-2024)",
        "chunks": {}, "failed": [], "notes": [], "status": "running",
    }
    manifest["status"] = "running"
    atomic_json(mpath, manifest)
    done = skipped = failed = 0
    for i, d in enumerate(days):
        fname = f"chunk_{d}.csv"
        fpath = batch_dir / fname
        if manifest_ok(batch_dir, manifest, fname):
            skipped += 1
            continue
        if not budget_left(deadline):
            manifest["status"] = "partial"
            manifest["remaining"] = days[i:]
            manifest["notes"].append(f"{now()} budget {budget_min}min reached; remaining {len(days) - i} trade days")
            atomic_json(mpath, manifest)
            log.warning("budget reached at %d/%d; stopping stk_limit in resumable state", i, len(days))
            break
        try:
            df, attempts, _ = call_with_retry(pro, ds, {"trade_date": d}, log, token)
            rows = write_chunk_csv(df, fpath, STK_LIMIT_COLS)
            manifest["chunks"][fname] = {
                "trade_date": d, "rows": int(rows), "done_at": now(),
                "attempts": attempts, "sha256": sha256_file(fpath),
                "suspicious_round_rows": bool(rows >= 5000 and rows % 100 == 0),
            }
            manifest["updated_at"] = now()
            atomic_json(mpath, manifest)
            done += 1
            if i % 20 == 0 or rows == 0:
                log.info("[stk_limit %d/%d] %s rows=%d attempts=%d", i + 1, len(days), d, rows, attempts)
        except Exception as exc:  # noqa: BLE001
            manifest["failed"].append({"trade_date": d, "at": now(), "error": scrub(exc, token)})
            atomic_json(mpath, manifest)
            elog("chunk FAILED stk_limit %s", d)
            failed += 1
        time.sleep(sleep_s + random.random() * 0.1)
    if manifest.get("status") == "running":
        manifest["status"] = "completed" if not manifest["failed"] else "completed-with-failures"
    manifest["updated_at"] = now()
    manifest["finished_at"] = now()
    atomic_json(mpath, manifest)
    log.info("stk_limit batch %s done: new=%d skipped=%d failed=%d status=%s",
             BATCH, done, skipped, failed, manifest["status"])


# ------------------------------------------------------------------ probe
def run_probe(run_dir: Path, log, wlog, elog) -> int:
    import tushare as ts
    token = load_token()
    pro = ts.pro_api(token)
    ok = True
    for ds in ("fund_daily", "fund_adj"):
        try:
            df, attempts, errors = call_with_retry(
                pro, ds, {"ts_code": "510300.SH", "start_date": "20260911", "end_date": "20260917"},
                log, token, max_attempts=2)
            if errors:
                for e in errors:
                    wlog("probe %s transient error (retried ok): %s", ds, e)
            n = 0 if df is None else len(df)
            span = "" if n == 0 else f"{df['trade_date'].min()}..{df['trade_date'].max()}"
            log.info("PROBE %s 510300.SH 20260911-20260917: rows=%d span=%s cols=%s attempts=%d -> PERMISSION OK",
                     ds, n, span, list(df.columns) if n else "n/a", attempts)
            log.info("PROBE %s data discarded (2026 probe rows NOT saved to raw)", ds)
        except Exception as exc:  # noqa: BLE001
            ok = False
            elog("PROBE %s FAILED: %s", ds, scrub(exc, token))
    log.info("probe verdict: %s", "permission confirmed for fund_daily+fund_adj" if ok else "PERMISSION INSUFFICIENT / ERROR - do not proceed to full pull")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["probe", "funds", "stk-limit"])
    ap.add_argument("--datasets", default="fund_daily,fund_adj")
    ap.add_argument("--budget-min", type=float, default=150.0)
    ap.add_argument("--sleep", type=float, default=0.7)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--run-dir", required=True)
    a = ap.parse_args()

    token = load_token()
    run_dir = Path(a.run_dir)
    log, wlog, elog, log_path = setup_logger(run_dir, a.mode.replace("-", "_"), token)
    log.info("mode=%s batch=%s window=%s..%s sleep=%.2fs budget=%.0fmin run_dir=%s",
             a.mode, BATCH, START_DATE, END_DATE, a.sleep, a.budget_min, run_dir)
    log.info("token source: %s (content never logged)", TOKEN_PATH.name)

    if a.mode == "probe":
        return run_probe(run_dir, log, wlog, elog)

    import tushare as ts
    pro = ts.pro_api(token)
    if a.mode == "funds":
        run_funds(pro, [d for d in a.datasets.split(",") if d], a.budget_min,
                  a.sleep, a.limit, run_dir, log, wlog, elog)
    else:
        run_stk_limit(pro, a.budget_min, a.sleep, a.limit, run_dir, log, wlog, elog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
