# -*- coding: utf-8 -*-
"""Register the new batch into data/_meta (append-only; existing lines untouched).

1. Append sha256 rows for every file in the batch dir to data/_meta/sha256.tsv
   (skips any path that already exists in the file; refuses to rewrite existing rows).
2. Append a batch entry to data/_meta/inventory.json (backup first, into run tmp/).
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(r"D:\量化")
RUN_DIR = REPO / "artifacts" / "runs" / "20260919T021519-etf-pull-74d0"
BATCH_DIR = REPO / "data" / "raw" / "baostock" / "etf-daily-20260919-r1"
META = REPO / "data" / "_meta"
REL = f"baostock/{BATCH_DIR.name}"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    tsv_path = META / "sha256.tsv"
    existing = set()
    with open(tsv_path, encoding="utf-8", newline="") as f:
        for line in f:
            if line.strip():
                existing.add(line.split("\t", 1)[0])
    print(f"existing sha256.tsv rows: {len(existing)}")

    files = sorted(p for p in BATCH_DIR.iterdir() if p.is_file())
    new_rows = []
    for p in files:
        rel = f"{REL}/{p.name}"
        if rel in existing:
            print(f"SKIP (already registered): {rel}")
            continue
        new_rows.append(f"{rel}\t{p.stat().st_size}\t{sha256_of(p)}")

    if new_rows:
        with open(tsv_path, "a", encoding="utf-8", newline="") as f:
            f.write("\n".join(new_rows) + "\n")
    print(f"sha256.tsv appended rows: {len(new_rows)}")

    inv_path = META / "inventory.json"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(inv_path, RUN_DIR / "tmp" / f"inventory.json.bak-{stamp}")
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    before = len(inv["batches"])
    if any(b["path"] == f"baostock/{BATCH_DIR.name}" for b in inv["batches"]):
        print("inventory.json already has batch entry, skip append")
    else:
        ext: dict[str, int] = {}
        total_bytes = 0
        for p in files:
            ext[p.suffix.lower()] = ext.get(p.suffix.lower(), 0) + 1
            total_bytes += p.stat().st_size
        inv["batches"].append({
            "path": f"baostock/{BATCH_DIR.name}",
            "files": len(files),
            "bytes": total_bytes,
            "ext": ext,
            "first": files[0].name if files else None,
            "last": files[-1].name if files else None,
            "chunk_dates": 0,
            "range": ["2015-01-01", "2024-12-31"],
            "registered_at": stamp,
        })
        inv_path.write_text(
            json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"inventory.json batches: {before} -> {len(inv['batches'])}")

    # verify still valid
    json.loads(inv_path.read_text(encoding="utf-8"))
    print("inventory.json re-parsed OK; backup at tmp/inventory.json.bak-", stamp, sep="")


if __name__ == "__main__":
    main()
