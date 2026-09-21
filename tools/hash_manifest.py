# -*- coding: utf-8 -*-
"""生成保留层的 SHA-256 台账（完整性基线）。

输出 TSV：`相对路径<TAB>字节数<TAB>sha256`，按路径排序；多进程分块读取。
用法: python tools/hash_manifest.py [--raw data/raw] [--out data/raw/_sha256.tsv] [--verify]
带 --verify 时只校验已有台账，不重写。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from concurrent.futures import ProcessPoolExecutor

CHUNK = 8 << 20


def digest(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def walk(root: str):
    for dp, _dn, fns in os.walk(root):
        for f in fns:
            if f.startswith("_"):  # 工具输出自身
                continue
            yield os.path.join(dp, f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    out = a.out or os.path.join(os.path.dirname(a.raw), "_meta", "sha256.tsv")

    files = sorted(walk(a.raw))
    rels = {os.path.relpath(p, a.raw).replace("\\", "/") for p in files}
    if a.verify:
        expected = {}
        with open(out, encoding="utf-8") as fh:
            for line in fh:
                rel, size, dg = line.rstrip("\n").split("\t")
                expected[rel] = (int(size), dg)
        bad = []
        with ProcessPoolExecutor(max_workers=max(4, (os.cpu_count() or 8) // 2)) as pool:
            for path, dg in zip(files, pool.map(digest, files, chunksize=8)):
                rel = os.path.relpath(path, a.raw).replace("\\", "/")
                rec = expected.get(rel)
                if rec is None:
                    bad.append((rel, "EXTRA"))
                elif os.path.getsize(path) != rec[0] or dg != rec[1]:
                    bad.append((rel, "MISMATCH"))
        bad.extend((rel, "MISSING") for rel in expected if rel not in rels)
        print(f"verify: files={len(files)} problems={len(bad)}")
        for rel, kind in bad[:50]:
            print(f"  {kind} {rel}")
        return 1 if bad else 0

    total = 0
    with ProcessPoolExecutor(max_workers=max(4, (os.cpu_count() or 8) // 2)) as pool, open(out, "w", encoding="utf-8", newline="\n") as fh:
        for path, dg in zip(files, pool.map(digest, files, chunksize=8)):
            rel = os.path.relpath(path, a.raw).replace("\\", "/")
            size = os.path.getsize(path)
            total += size
            fh.write(f"{rel}\t{size}\t{dg}\n")
    print(f"wrote {out}: files={len(files)} bytes={total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
