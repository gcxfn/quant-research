# -*- coding: utf-8 -*-
"""tushare fund 批次覆盖报告与台账登记（只追加，不改既有记录）。

- 覆盖统计: 每 batch 的 ETF 数、分年行数、起止日期、对照交易日历(SSE 开市日 2015-2024)的缺口、
  复权因子覆盖率（fund_adj 相对 fund_daily）。
- 台账: data/_meta/sha256.tsv 追加新行（既有行不动）；data/_meta/inventory.json 追加批次条目
  （read-modify-write，既有条目原样保留）。
用法: python tools/report_tushare_fund_batch.py [--register-ledger]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw" / "tushare"
META = REPO / "data" / "_meta"
BATCH = "20260917-r1"
DATASETS = ("fund_daily", "fund_adj", "stk_limit")
START, END = "20150101", "20241231"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def trade_days() -> set[str]:
    days = set()
    for p in (RAW / "trade_cal" / "20260909-r1").glob("chunk_sse_*.csv"):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r["is_open"] == "1" and START <= r["cal_date"] <= END:
                days.add(r["cal_date"])
    return days


def fund_universe() -> set[str]:
    rows = list(csv.DictReader(open(RAW / "fund_basic" / "20260909-r1" / "chunk_market_E.csv", encoding="utf-8-sig")))
    sel = set()
    for r in rows:
        if r["market"] != "E" or "ETF" not in (r["name"] or "").upper():
            continue
        ld, dd = r["list_date"] or "", r["delist_date"] or ""
        if len(ld) == 8 and ld <= END and (not dd or dd >= START):
            sel.add(r["ts_code"])
    return sel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register-ledger", action="store_true")
    a = ap.parse_args()
    cal = trade_days()
    uni = fund_universe()
    print(f"trade days 2015-2024 (SSE open): {len(cal)}; universe ETF: {len(uni)}")
    summary = {}
    for ds in DATASETS:
        bdir = RAW / ds / BATCH
        if not bdir.exists():
            print(f"[{ds}] batch dir missing - not fetched")
            continue
        man = json.loads((bdir / "manifest.json").read_text(encoding="utf-8"))
        chunks = man["chunks"]
        rows_total = 0
        per_year = Counter()
        codes = set()
        dates_seen = set()
        code_dates = {}
        first_last = {}
        for fname, ent in sorted(chunks.items()):
            f = bdir / fname
            n = ent["rows"]
            rows_total += n
            key = ent.get("ts_code") or ent.get("trade_date")
            if ds in ("fund_daily", "fund_adj"):
                codes.add(ent["ts_code"])
                if n:
                    first_last[ent["ts_code"]] = (ent["first_trade_date"], ent["last_trade_date"])
            if n == 0:
                continue
            # 从文件直接读分年与日期集合（manifest 只有首尾）
            with open(f, encoding="utf-8") as fh:
                rd = csv.DictReader(fh)
                ds_dates = set()
                for r in rd:
                    d = r["trade_date"]
                    per_year[d[:4]] += 1
                    ds_dates.add(d)
            code_dates[key] = ds_dates
            dates_seen |= ds_dates
        print(f"\n[{ds}] status={man['status']} chunks={len(chunks)} rows={rows_total} "
              f"codes={len(codes)} years={dict(sorted(per_year.items()))}")
        if ds in ("fund_daily", "fund_adj"):
            if dates_seen:
                print(f"  span={min(dates_seen)}..{max(dates_seen)}; calendar-missing days "
                      f"(in fund files but not SSE cal): {len(dates_seen - cal)}")
            missing_cal = cal - dates_seen
            print(f"  trade-cal days with no rows at all: {len(missing_cal)}")
            not_pulled = uni - codes
            print(f"  universe not pulled yet: {len(not_pulled)}")
        if ds == "stk_limit" and code_dates:
            all_dates = set(code_dates)
            print(f"  days pulled={len(all_dates)}/{len(cal)}; missing cal days={len(cal - all_dates)}")
        summary[ds] = {"status": man["status"], "chunks": len(chunks), "rows": rows_total,
                       "codes": sorted(codes) if ds != "stk_limit" else [],
                       "per_year": {k: per_year[k] for k in sorted(per_year)}}
        if ds == "fund_adj" and "fund_daily" in summary:
            # 复权因子覆盖率: adj 有因子且 >0 的 (code,date) / fund_daily 行数
            fd = summary["fund_daily"]
            fd_rows = fd["rows"]
            adj_rows = rows_total
            print(f"  adj/daily row ratio: {adj_rows}/{fd_rows} = {adj_rows / max(fd_rows, 1):.4f}")
    if a.register_ledger:
        # sha256.tsv 追加
        tsv = META / "sha256.tsv"
        existing = set()
        if tsv.exists():
            for line in open(tsv, encoding="utf-8"):
                if line.strip():
                    existing.add(line.split("\t")[0])
        added = 0
        with open(tsv, "a", encoding="utf-8") as out:
            for ds in DATASETS:
                bdir = RAW / ds / BATCH
                if not bdir.exists():
                    continue
                for p in sorted(bdir.iterdir()):
                    if p.suffix not in (".csv", ".json") or p.name.endswith(".tmp"):
                        continue
                    rel = f"tushare/{ds}/{BATCH}/{p.name}"
                    if rel in existing:
                        continue
                    out.write(f"{rel}\t{p.stat().st_size}\t{sha256_file(p)}\n")
                    added += 1
        print(f"\nsha256.tsv appended {added} lines (existing untouched)")
        # inventory.json 追加批次条目
        invp = META / "inventory.json"
        inv = json.loads(invp.read_text(encoding="utf-8"))
        have = {b["path"] for b in inv["batches"]}
        n_added = 0
        for ds in DATASETS:
            bdir = RAW / ds / BATCH
            rel = f"tushare/{ds}/{BATCH}"
            if not bdir.exists() or rel in have:
                continue
            files = [p for p in bdir.iterdir() if p.is_file()]
            ext = Counter(p.suffix for p in files)
            names = sorted(p.name for p in files)
            entry = {"path": rel, "files": len(files),
                     "bytes": sum(p.stat().st_size for p in files),
                     "ext": {k: v for k, v in sorted(ext.items())},
                     "first": names[0], "last": names[-1], "chunk_dates": 0, "range": None}
            if ds == "stk_limit":
                days = sorted(f[6:14] for f in names if f.startswith("chunk_"))
                entry["range"] = [days[0], days[-1]] if days else None
                entry["chunk_dates"] = len(days)
            inv["batches"].append(entry)
            n_added += 1
        tmp = invp.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, invp)
        print(f"inventory.json appended {n_added} batch entries (existing entries preserved)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
