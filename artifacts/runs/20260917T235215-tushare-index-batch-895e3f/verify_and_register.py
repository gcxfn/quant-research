# -*- coding: utf-8 -*-
"""核验 index_daily 批次并登记台账（只追加，不改既有行/条目）。

- 每指数：行数、日期范围、close 非空率。
- 与本地 trade_cal（SSE，data/raw/tushare/trade_cal/20260909-r1）2015-2024 开市日比对缺口。
- 抽查 000300.SH 三个已知日期的收盘（只记录批次内 API 返回值，不与其他源对账）。
- 核验通过后：更新批次 manifest（verification/notes）→ 追加 sha256.tsv → 追加 inventory.json。
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(r"D:/量化")
RAW = ROOT / "data" / "raw"
BATCH_DIR = RAW / "tushare" / "index_daily" / "20260917-r1"
BATCH = "20260917-r1"
SHA_TSV = ROOT / "data" / "_meta" / "sha256.tsv"
INVENTORY = ROOT / "data" / "_meta" / "inventory.json"
TRADE_CAL_DIR = RAW / "tushare" / "trade_cal" / "20260909-r1"
START, END = "20150101", "20241231"
INDICES = ["000001.SH", "000300.SH", "000905.SH", "000852.SH", "399006.SZ"]
SPOT_DATES = ["20240930", "20150612", "20200709"]
SPOT_TSCODE = "000300.SH"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trade_cal_days() -> set[str]:
    days: set[str] = set()
    for f in sorted(TRADE_CAL_DIR.glob("chunk_*.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["is_open"] == "1" and START <= row["cal_date"] <= END:
                    days.add(row["cal_date"])
    return days


def main() -> int:
    cal_days = load_trade_cal_days()
    verification = {"trade_cal_reference": "tushare/trade_cal/20260909-r1 (SSE, is_open=1, 20150101-20241231)",
                    "trade_cal_days": len(cal_days), "per_index": {}, "spot_checks": []}
    problems: list[str] = []

    spot_rows: dict[str, dict] = {}
    for ts_code in INDICES:
        f = BATCH_DIR / f"chunk_{ts_code}.csv"
        with open(f, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        dates = [r["trade_date"] for r in rows]
        close_null = sum(1 for r in rows if r["close"].strip() == "")
        idx_days = set(dates)
        missing = sorted(cal_days - idx_days)
        extra = sorted(idx_days - cal_days)
        dup = len(dates) - len(idx_days)
        entry = {
            "rows": len(rows),
            "first_date": min(dates),
            "last_date": max(dates),
            "close_non_null": len(rows) - close_null,
            "close_non_null_rate": round((len(rows) - close_null) / len(rows), 6),
            "missing_vs_trade_cal": len(missing),
            "extra_vs_trade_cal": len(extra),
            "duplicate_dates": dup,
        }
        if missing:
            entry["missing_dates"] = missing
            problems.append(f"{ts_code}: {len(missing)} trading days missing")
        if extra:
            entry["extra_dates"] = extra
            problems.append(f"{ts_code}: {len(extra)} dates not in trade_cal")
        if dup:
            problems.append(f"{ts_code}: {dup} duplicate dates")
        if close_null:
            problems.append(f"{ts_code}: {close_null} null close")
        if ts_code == SPOT_TSCODE:
            by_date = {r["trade_date"]: r for r in rows}
            for d in SPOT_DATES:
                if d in by_date:
                    spot_rows[d] = {"ts_code": ts_code, "trade_date": d, "close": by_date[d]["close"]}
                else:
                    problems.append(f"spot date {d} not found in {ts_code}")
        verification["per_index"][ts_code] = entry

    for d in SPOT_DATES:
        if d in spot_rows:
            verification["spot_checks"].append(spot_rows[d])

    print(json.dumps(verification, ensure_ascii=False, indent=2))
    print("PROBLEMS:", problems if problems else "none")

    # ---- 更新批次 manifest（追加 verification 与 notes）----
    mpath = BATCH_DIR / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["verification"] = verification
    manifest["notes"].append(
        "抽查 close（000300.SH，批次内 API 返回值，未与其他源对账）: "
        + "; ".join(f"{r['trade_date']}={r['close']}" for r in verification["spot_checks"])
    )
    manifest["notes"].append(
        f"trade_cal 覆盖比对: 参考 {verification['trade_cal_reference']}, "
        f"各指数缺失/多余交易日=0"
        if not problems
        else f"trade_cal 覆盖比对: 存在问题 {problems}"
    )
    manifest["notes"].append("研究范围硬边界 20150101-20241231；2025+ 未拉取。")
    manifest["updated_at"] = datetime.now().isoformat(timespec="seconds")
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if problems:
        print("ABORT: verification failed; ledgers NOT updated")
        return 3

    # ---- sha256.tsv 只追加 ----
    append_lines = []
    for f in sorted(BATCH_DIR.iterdir()):
        rel = f"tushare/index_daily/{BATCH}/{f.name}"
        append_lines.append(f"{rel}\t{f.stat().st_size}\t{sha256_file(f)}")
    with open(SHA_TSV, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(append_lines) + "\n")
    print(f"sha256.tsv appended {len(append_lines)} rows")

    # ---- inventory.json 追加条目 ----
    inv = json.loads(INVENTORY.read_text(encoding="utf-8"))
    ext: dict[str, int] = {}
    total_bytes = 0
    names = sorted(f.name for f in BATCH_DIR.iterdir())
    for f in BATCH_DIR.iterdir():
        e = f.suffix.lower()
        ext[e] = ext.get(e, 0) + 1
        total_bytes += f.stat().st_size
    entry = {
        "path": f"tushare/index_daily/{BATCH}",
        "files": len(names),
        "bytes": total_bytes,
        "ext": dict(sorted(ext.items(), key=lambda kv: -kv[1])),
        "first": names[0],
        "last": names[-1],
        "chunk_dates": 0,
        "range": [START, END],
    }
    if any(b["path"] == entry["path"] for b in inv["batches"]):
        print("inventory entry already exists; skip append")
    else:
        inv["batches"].append(entry)
        INVENTORY.write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"inventory.json appended entry: {entry['path']} files={entry['files']} bytes={entry['bytes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
