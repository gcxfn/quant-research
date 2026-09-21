# -*- coding: utf-8 -*-
"""数据台账生成器：扫描 data/raw，产出机器可读清单与人类可读台账。

对每个「批次目录」（含数据文件的最小目录）记录：文件数、字节数、扩展名分布、
文件名首末、若为 chunk_YYYYMMDD.* 形式则解析日期覆盖；并在同一数据集目录下
检测不同批次之间的日期区间重叠（重复拉取的信号）。

用法:
    python tools/inventory.py data/raw --json data/raw/_inventory.json --md docs/DATA_INVENTORY.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict

CHUNK_RE = re.compile(r"^chunk[_-]?(\d{8})")
DAY_RE = re.compile(r"(\d{8})")


def dataset_key(rel_parts: list[str]) -> str:
    return "/".join(rel_parts)


def scan(root: str) -> dict:
    batches: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        data_files = [f for f in filenames if not f.startswith(".")]
        if not data_files:
            continue
        rel = os.path.relpath(dirpath, root).replace("\\", "/")
        total = 0
        sizes: dict[str, int] = defaultdict(int)
        for f in data_files:
            try:
                sz = os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                continue
            total += sz
            ext = os.path.splitext(f)[1].lower() or "(noext)"
            sizes[ext] += 1
        dates = sorted({m.group(1) for f in data_files if (m := CHUNK_RE.match(f))})
        named = sorted(data_files)
        batches.append(
            {
                "path": rel,
                "files": len(data_files),
                "bytes": total,
                "ext": dict(sorted(sizes.items(), key=lambda kv: -kv[1])),
                "first": named[0],
                "last": named[-1],
                "chunk_dates": len(dates),
                "range": [dates[0], dates[-1]] if dates else None,
            }
        )

    # 日期区间重叠检测：同一父目录下、不同批次子目录
    overlaps = []
    by_parent: dict[str, list[dict]] = defaultdict(list)
    for b in batches:
        if b["range"]:
            parent = b["path"].rsplit("/", 1)[0]
            by_parent[parent].append(b)
    for parent, items in by_parent.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                lo = max(a["range"][0], b["range"][0])
                hi = min(a["range"][1], b["range"][1])
                if lo <= hi:
                    overlaps.append({"parent": parent, "a": a["path"], "b": b["path"], "overlap": [lo, hi]})

    return {"root": root, "batches": batches, "chunk_overlaps": overlaps}


def markdown(scan_result: dict) -> str:
    from collections import defaultdict as dd

    by_source: dict[str, list[dict]] = dd(list)
    for b in scan_result["batches"]:
        src = b["path"].split("/")[0]
        by_source[src].append(b)

    lines = ["# 数据台账（自动生成）", "", f"根目录: `{scan_result['root']}`", ""]
    tot_files = sum(b["files"] for b in scan_result["batches"])
    tot_bytes = sum(b["bytes"] for b in scan_result["batches"])
    lines += [f"批次目录数: {len(scan_result['batches'])}", f"文件数: {tot_files}", f"字节数: {tot_bytes:,}", ""]
    lines += ["## 按来源汇总", "", "| 来源 | 批次目录 | 文件数 | 体积 |", "|---|---:|---:|---:|"]
    for src in sorted(by_source):
        bs = by_source[src]
        lines.append(f"| {src} | {len(bs)} | {sum(b['files'] for b in bs):,} | {sum(b['bytes'] for b in bs)/2**30:.2f} GiB |")
    lines += ["", "## 明细", ""]
    for src in sorted(by_source):
        lines += [f"### {src}", "", "| 批次路径 | 文件数 | 体积 | 扩展名 | 名称区间 | chunk 日期覆盖 |", "|---|---:|---:|---|---|---|"]
        for b in sorted(by_source[src], key=lambda x: x["path"]):
            rng = f"{b['range'][0]}..{b['range'][1]} ({b['chunk_dates']})" if b["range"] else "-"
            ext = ", ".join(f"{k}×{v}" for k, v in list(b["ext"].items())[:4])
            name_range = b["first"] if b["first"] == b["last"] else f"{b['first']} … {b['last']}"
            lines.append(f"| `{b['path']}` | {b['files']:,} | {b['bytes']/2**20:,.1f} MiB | {ext} | {name_range} | {rng} |")
        lines.append("")
    if scan_result["chunk_overlaps"]:
        lines += ["## 同目录批次日期区间重叠（潜在重复拉取）", "", "| 数据集 | 批次 A | 批次 B | 重叠区间 |", "|---|---|---|---|"]
        for o in scan_result["chunk_overlaps"]:
            lines.append(f"| `{o['parent']}` | `{o['a']}` | `{o['b']}` | {o['overlap'][0]}..{o['overlap'][1]} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json", default=None)
    ap.add_argument("--md", default=None)
    a = ap.parse_args()
    res = scan(a.root)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
    if a.md:
        os.makedirs(os.path.dirname(os.path.abspath(a.md)), exist_ok=True)
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(markdown(res))
    tot = sum(b["bytes"] for b in res["batches"])
    print(f"batches={len(res['batches'])} files={sum(b['files'] for b in res['batches'])} bytes={tot} overlaps={len(res['chunk_overlaps'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
