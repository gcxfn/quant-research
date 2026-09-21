# -*- coding: utf-8 -*-
"""1 分钟数据清单：逐年统计文件数、字节、首末交易日与形态，供覆盖矩阵核对。

压缩原件于 2026-09-16 解压为目录层：
  data/raw/bigquant/<batch>/years/<year>/      按日 parquet 或按证券 CSV
  data/raw/user_minute_1m/<batch>/<year>/      按日 parquet
输出 docs/evidence/minute-manifest.json。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

DAY_SUFFIX = ".parquet"


def scan_year(path: str) -> dict:
    files = []
    total = 0
    for root, _dirs, names in os.walk(path):
        for n in names:
            fp = os.path.join(root, n)
            files.append(n)
            total += os.path.getsize(fp)
    files.sort()
    days = sorted(n[: -len(DAY_SUFFIX)] for n in files if n.endswith(DAY_SUFFIX) and n[:8].isdigit())
    return {
        "files": len(files),
        "bytes": total,
        "kind": "day-parquet" if days else "symbol-csv",
        "sessions": len(days) if days else None,
        "first_day": days[0] if days else None,
        "last_day": days[-1] if days else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join("data", "raw"))
    ap.add_argument("--out", default=os.path.join("docs", "evidence", "minute-manifest.json"))
    a = ap.parse_args()

    rows = []
    bq = os.path.join(a.raw, "bigquant")
    for batch in sorted(os.listdir(bq)) if os.path.isdir(bq) else []:
        ydir = os.path.join(bq, batch, "years")
        if not os.path.isdir(ydir):
            continue
        for year in sorted(os.listdir(ydir)):
            p = os.path.join(ydir, year)
            if os.path.isdir(p):
                rows.append({"pack": "bigquant", "batch": batch, "year": year, **scan_year(p)})
    um = os.path.join(a.raw, "user_minute_1m")
    for batch in sorted(os.listdir(um)) if os.path.isdir(um) else []:
        bdir = os.path.join(um, batch)
        if not os.path.isdir(bdir):
            continue
        for year in sorted(os.listdir(bdir)):
            p = os.path.join(bdir, year)
            if len(year) == 4 and year.isdigit() and os.path.isdir(p):
                rows.append({"pack": "user_minute_1m", "batch": batch, "year": year, **scan_year(p)})

    out = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "rows": rows,
        "totals": {
            pack: {
                "years": sum(1 for r in rows if r["pack"] == pack),
                "files": sum(r["files"] for r in rows if r["pack"] == pack),
                "bytes": sum(r["bytes"] for r in rows if r["pack"] == pack),
            }
            for pack in sorted({r["pack"] for r in rows})
        },
    }
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    for r in rows:
        print(f'{r["pack"]:15s} {r["year"]}  {r["kind"]:12s} files={r["files"]:6d}'
              f'  {r["bytes"]:>13d}  {r["first_day"]}..{r["last_day"]}')
    for pack, t in out["totals"].items():
        print(f'{pack:15s} years={t["years"]} files={t["files"]} bytes={t["bytes"]}')
    print(f"record -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
