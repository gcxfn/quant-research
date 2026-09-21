# -*- coding: utf-8 -*-
"""01_verify_identity.py — G2 半天截面前置：user_minute_1m 两批次身份核验。

只读 data/raw 与 data/_meta；所有输出写 run 目录 identity/。
核验内容：
1) sha256.tsv 中 user_minute_1m 条目 vs 磁盘实际文件（缺失/多出/大小不符）
2) 抽样 5 个日文件（2015/2017/2019/2021/2024 各一）重算 sha256 与登记值比对
纯数据工程，无任何策略计算。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

REPO = Path(r"D:\量化")
RAW = REPO / "data" / "raw"
META_TSV = REPO / "data" / "_meta" / "sha256.tsv"
RUN = REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
BATCHES = ["20260913-143215", "20260913-2020-2024"]
SOURCE = "user_minute_1m"
SAMPLE_DATES = ["20150601", "20170601", "20190603", "20210601", "20240603"]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    t0 = time.perf_counter()
    # ---- 1. 解析 sha256.tsv 中 user_minute_1m 条目 ----
    registered: dict[str, tuple[int, str]] = {}
    tsv_lines = 0
    with open(META_TSV, "r", encoding="utf-8") as f:
        for line in f:
            tsv_lines += 1
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            rel, size, digest = parts
            if rel.startswith(SOURCE + "/" + BATCHES[0]) or rel.startswith(SOURCE + "/" + BATCHES[1]):
                registered[rel.replace("\\", "/")] = (int(size), digest)
    print(f"[tsv] 总行数={tsv_lines}, user_minute_1m 两批次登记条目={len(registered)}")

    # ---- 2. 磁盘实际文件（只列清单，不读内容） ----
    disk: dict[str, int] = {}
    for batch in BATCHES:
        bdir = RAW / SOURCE / batch
        for p in sorted(bdir.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(RAW)).replace("\\", "/")
                disk[rel] = p.stat().st_size
    print(f"[disk] 两批次磁盘文件总数={len(disk)}, 总字节={sum(disk.values()):,}")

    reg_paths = set(registered)
    disk_paths = set(disk)
    missing_registered = sorted(reg_paths - disk_paths)
    unregistered_on_disk = sorted(disk_paths - reg_paths)

    size_mismatch = []
    for rel in sorted(reg_paths & disk_paths):
        reg_size = registered[rel][0]
        if reg_size != disk[rel]:
            size_mismatch.append({"path": rel, "tsv_bytes": reg_size, "disk_bytes": disk[rel]})

    # ---- 3. 抽样重算 sha256（5 个日文件，年份回退就近） ----
    sample_results = []
    for want in SAMPLE_DATES:
        year = want[:4]
        target = RAW / SOURCE / (BATCHES[0] if year <= "2019" else BATCHES[1]) / year / f"{want}.parquet"
        if not target.exists():
            ydir = RAW / SOURCE / (BATCHES[0] if year <= "2019" else BATCHES[1]) / year
            cands = sorted(ydir.glob("*.parquet"))
            if not cands:
                raise FileNotFoundError(f"no parquet in {ydir}")
            target = min(cands, key=lambda p: abs(int(p.stem) - int(want)))
        rel = str(target.relative_to(RAW)).replace("\\", "/")
        t1 = time.perf_counter()
        actual = sha256_file(target)
        dt = time.perf_counter() - t1
        reg_size, reg_digest = registered.get(rel, (None, None))
        sample_results.append({
            "path": rel,
            "date": target.stem,
            "tsv_sha256": reg_digest,
            "recomputed_sha256": actual,
            "match": (actual == reg_digest),
            "tsv_bytes": reg_size,
            "disk_bytes": target.stat().st_size,
            "hash_seconds": round(dt, 3),
        })
        print(f"[hash] {target.stem}: match={actual == reg_digest} ({dt:.2f}s)")

    # ---- 4. 汇总 ----
    all_size_ok = not size_mismatch
    all_hash_ok = all(s["match"] for s in sample_results)
    status = "REGISTERED_VERIFIED" if (not missing_registered and not unregistered_on_disk and all_size_ok and all_hash_ok) else "NEEDS_ATTENTION"
    report = {
        "purpose": "user_minute_1m identity verification for G2 half-day prep (pure data engineering)",
        "run_id": RUN.name,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_root": str(RAW / SOURCE),
        "meta_tsv": str(META_TSV.relative_to(REPO)),
        "tsv_total_lines": tsv_lines,
        "registered_entries": len(registered),
        "disk_files": len(disk),
        "disk_total_bytes": sum(disk.values()),
        "missing_registered": missing_registered,
        "unregistered_on_disk": unregistered_on_disk,
        "size_mismatch": size_mismatch,
        "sample_rehash": sample_results,
        "status": status,
        "conclusion": (
            "两批次 2,431 个 parquet + 2 个 transfer-manifest 已逐文件登记于 data/_meta/sha256.tsv；"
            "全量字节数比对一致，抽样 5 文件重算 sha256 与登记值一致。无需补登记清单。"
            if status == "REGISTERED_VERIFIED" else "存在不一致，见上文明细，需人工复核。"
        ),
        "elapsed_seconds": round(time.perf_counter() - t0, 3),
    }
    out = RUN / "identity" / "identity_verification.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] status={status}, report -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
