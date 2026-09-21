# -*- coding: utf-8 -*-
"""重复文件扫描：按字节级别找出 data/raw 下的完全重复文件。

策略：先按文件大小分组，只对「同尺寸 ≥2 文件」的组计算 BLAKE2b 摘要（多进程），
因此唯一的模型/数据大文件不会浪费时间。

用法:
    python tools/dedupe_scan.py <root> [--out dupes.json]
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

CHUNK = 8 << 20


def digest(path: str) -> tuple[str, str]:
    h = hashlib.blake2b(digest_size=16)
    size = 0
    try:
        with open(path, "rb") as fh:
            while True:
                buf = fh.read(CHUNK)
                if not buf:
                    break
                size += len(buf)
                h.update(buf)
    except OSError as exc:  # 权限/占用
        return ("", f"ERROR {exc}")
    return (h.hexdigest(), "")


def main() -> int:
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    default_out = os.path.join(os.path.dirname(root), "_meta", "dupes.json")
    out = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--out" else default_out

    sizes: dict[int, list[str]] = defaultdict(list)
    total_files = 0
    total_bytes = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
            except OSError:
                continue
            sizes[st.st_size].append(p)
            total_files += 1
            total_bytes += st.st_size

    candidates = [p for sz, ps in sizes.items() if sz > 0 and len(ps) > 1 for p in ps]
    print(f"files={total_files} bytes={total_bytes} size_collision_candidates={len(candidates)}", flush=True)

    hashes: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    with ProcessPoolExecutor(max_workers=max(4, (os.cpu_count() or 8) // 2)) as pool:
        for path, (dg, err) in zip(candidates, pool.map(digest, candidates, chunksize=4)):
            if err:
                errors.append(f"{path}\t{err}")
                continue
            hashes[dg].append(path)

    groups = {dg: sorted(ps) for dg, ps in hashes.items() if len(ps) > 1}
    wasted = 0
    for dg, ps in groups.items():
        wasted += os.path.getsize(ps[0]) * (len(ps) - 1)

    rel = lambda p: os.path.relpath(p, root).replace("\\", "/")
    report = {
        "root": root,
        "total_files": total_files,
        "total_bytes": total_bytes,
        "candidate_files": len(candidates),
        "duplicate_groups": len(groups),
        "redundant_bytes": wasted,
        "errors": errors,
        "groups": [
            {"digest": dg, "size": os.path.getsize(ps[0]), "count": len(ps), "paths": [rel(p) for p in ps]}
            for dg, ps in sorted(groups.items(), key=lambda kv: -os.path.getsize(kv[1][0]) * (len(kv[1]) - 1))
        ],
    }
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"duplicate_groups={len(groups)} redundant_bytes={wasted} errors={len(errors)} -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
