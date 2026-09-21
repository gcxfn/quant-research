"""解压 1 分钟压缩原件为可直接读取的目录层，校验通过后删除压缩包。

范围（只碰 1 分钟数据，不动 user_dataset 的日线前/后复权包）：
  data/raw/bigquant/<batch>/zips/<year>[_1min].zip  -> data/raw/bigquant/<batch>/years/<year>/
  data/raw/user_minute_1m/<batch>/<year>.zip        -> data/raw/user_minute_1m/<batch>/<year>/

每包逐个成员解压到临时目录，校验（成员数 / 字节数 / 2010-2013 逐文件 sha256 / CRC）全过再原子改名到位；
只有全部通过的包才会被 --delete-zips 删除。记录写到 docs/evidence/minute-extract.json。

用法：
  python tools/extract_minute_zips.py                     # 只解压并校验
  python tools/extract_minute_zips.py --delete-zips       # 校验通过后删除压缩包
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime

def sha256_file(path: str, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def discover(raw: str, verify_only: bool = False) -> list[dict]:
    """列出 1 分钟数据单元。压缩包还在就按包列；已解压（包已删）就按目录列。"""
    jobs = []

    def add(family, zip_path, dest, year):
        jobs.append({"family": family, "zip": zip_path, "dest": dest, "year": year})

    bq = os.path.join(raw, "bigquant")
    if os.path.isdir(bq):
        for batch in sorted(os.listdir(bq)):
            bdir = os.path.join(bq, batch)
            zdir = os.path.join(bdir, "zips")
            if os.path.isdir(zdir) and not verify_only:
                for name in sorted(os.listdir(zdir)):
                    if name.lower().endswith(".zip"):
                        year = os.path.basename(name)[:-4].split("_")[0]
                        add("bigquant", os.path.join(zdir, name), os.path.join(bdir, "years", year), year)
            else:
                ydir = os.path.join(bdir, "years")
                if not os.path.isdir(ydir):
                    continue
                for year in sorted(os.listdir(ydir)):
                    if os.path.isdir(os.path.join(ydir, year)):
                        add("bigquant", os.path.join(zdir, f"{year}.zip"),
                            os.path.join(ydir, year), year)
    um = os.path.join(raw, "user_minute_1m")
    if os.path.isdir(um):
        for batch in sorted(os.listdir(um)):
            bdir = os.path.join(um, batch)
            if not os.path.isdir(bdir):
                continue
            names = [n for n in sorted(os.listdir(bdir)) if n.lower().endswith(".zip")]
            if names and not verify_only:
                for name in names:
                    add("user_minute_1m", os.path.join(bdir, name),
                        os.path.join(bdir, os.path.basename(name)[:-4]), os.path.basename(name)[:-4])
            else:
                for year in sorted(os.listdir(bdir)):
                    if len(year) == 4 and year.isdigit() and os.path.isdir(os.path.join(bdir, year)):
                        add("user_minute_1m", os.path.join(bdir, f"{year}.zip"),
                            os.path.join(bdir, year), year)
    return jobs


def load_year_digests(raw: str) -> dict:
    """2010-2013 的逐文件 sha256 清单（basename -> digest）。"""
    out = {}
    for root, dirs, files in os.walk(os.path.join(raw, "bigquant")):
        if os.path.basename(root) != "years" or "manifest" not in root:
            continue
        for f in files:
            if not f.endswith(".sha256.txt"):
                continue
            year = f.split(".")[0]
            d = {}
            with open(os.path.join(root, f), encoding="utf-8") as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) == 2:
                        d[parts[1]] = parts[0]
            if d:
                out[year] = d
    return out


def load_extract_summary(raw: str) -> dict:
    p = os.path.join(raw, "bigquant", "minute-bulk-20260915-1", "manifest", "extract-summary.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def load_recorded_digests(raw: str, legacy_manifest: str | None) -> dict:
    """压缩包级 SHA-256 的历史记录（非本次重算）：(family, year) -> {sha256, source}。"""
    out = {}
    p = os.path.join(raw, "bigquant", "minute-bulk-20260915-1", "manifest", "zips.sha256.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            for r in json.load(fh).get("records", []):
                d = r.get("sha256_copy") or r.get("sha256_source")
                if d:
                    out[("bigquant", r["year"])] = {
                        "sha256": d, "zip_name": r.get("zip_name"), "source": "manifest/zips.sha256.json"}
    if legacy_manifest and os.path.exists(legacy_manifest):
        with open(legacy_manifest, encoding="utf-8") as fh:
            arch = json.load(fh).get("archives", {})
        for year, v in arch.items():
            if isinstance(v, dict) and v.get("sha256"):
                out[("user_minute_1m", year)] = {
                    "sha256": v["sha256"], "source": os.path.relpath(legacy_manifest).replace("\\", "/")}
    return out


def merge_prior(path: str, recs: list[dict]) -> None:
    """保留上一份记录里的包级摘要等字段（verify-only 不重算摘要时用）。"""
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as fh:
            prior = json.load(fh)
    except (OSError, ValueError):
        return
    idx = {(r["family"], r["year"]): r for r in prior.get("records", [])}
    for r in recs:
        old = idx.get((r["family"], r["year"]))
        if not old:
            continue
        for k in ("zip_sha256", "zip_sha256_documented", "sha256_checked"):
            if r.get(k) is None and old.get(k) is not None:
                r[k] = old[k]


def run_job(job: dict, year_digests: dict, summary: dict, recorded: dict) -> dict:
    src, dest, year = job["zip"], job["dest"], job["year"]
    t0 = time.time()
    rec = {"family": job["family"], "zip": src, "dest": dest, "year": year,
           "zip_bytes": os.path.getsize(src), "problems": []}
    rec["zip_sha256"] = sha256_file(src)
    doc = recorded.get((job["family"], year))
    if doc:
        rec["zip_sha256_documented"] = doc
        if doc["sha256"] != rec["zip_sha256"]:
            rec["problems"].append(f"zip sha256 != recorded ({doc['source']}): {doc['sha256']}")
    staging = dest + ".__extracting__"
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(staging, exist_ok=True)
    files = 0
    total = 0
    with zipfile.ZipFile(src) as z:
        infos = z.infolist()
        expect_files = len(infos)
        expect_bytes = sum(i.file_size for i in infos)
        for info in infos:
            z.extract(info, staging)          # 读到 EOF 会校验 CRC，不一致则 BadZipFile
            files += 1
            total += info.file_size
    if files != expect_files:
        rec["problems"].append(f"member count {files} != {expect_files}")
    if total != expect_bytes:
        rec["problems"].append(f"bytes {total} != {expect_bytes}")

    digests = year_digests.get(year)
    checked = 0
    if digests:
        for name, digest in digests.items():
            fp = os.path.join(staging, name)
            if not os.path.exists(fp):
                rec["problems"].append(f"missing {name}")
                continue
            if sha256_file(fp) != digest:
                rec["problems"].append(f"digest mismatch {name}")
            checked += 1
        rec["sha256_checked"] = checked
    sum_year = summary.get(year) if job["family"] == "bigquant" else None
    if sum_year:
        if sum_year.get("files_extracted") not in (None, files):
            rec["problems"].append(f"extract-summary files {sum_year['files_extracted']} != {files}")
        if sum_year.get("total_bytes") not in (None, total):
            rec["problems"].append(f"extract-summary bytes {sum_year['total_bytes']} != {total}")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.replace(staging, dest)
    rec.update({"files": files, "bytes": total, "seconds": round(time.time() - t0, 1),
                "verified": not rec["problems"]})
    return rec


def verify_job(job: dict, year_digests: dict, summary: dict, recorded: dict) -> dict:
    """已解压目录核对：压缩包仍在则比成员集合/字节；包已删则只做清单摘要核对。"""
    src, dest, year = job["zip"], job["dest"], job["year"]
    t0 = time.time()
    rec = {"family": job["family"], "zip": src, "dest": dest, "year": year,
           "zip_bytes": os.path.getsize(src) if os.path.exists(src) else None,
           "archive_present": os.path.exists(src), "problems": []}
    doc = recorded.get((job["family"], year))
    if doc:
        rec["zip_sha256_recorded"] = doc
    if not os.path.isdir(dest):
        rec["problems"].append("dest missing")
        rec.update({"files": 0, "bytes": 0, "seconds": 0.0, "verified": False})
        return rec
    got = {}
    for root, _dirs, files in os.walk(dest):
        for f in files:
            fp = os.path.join(root, f)
            got[os.path.relpath(fp, dest).replace("\\", "/")] = os.path.getsize(fp)
    if rec["archive_present"]:
        with zipfile.ZipFile(src) as z:
            infos = z.infolist()
            want = {i.filename.replace("\\", "/"): i.file_size for i in infos}
        for name, size in want.items():
            if name not in got:
                rec["problems"].append(f"missing {name}")
            elif got[name] != size:
                rec["problems"].append(f"size {name}: {got[name]} != {size}")
        for name in got:
            if name not in want:
                rec["problems"].append(f"extra {name}")
    digests = year_digests.get(year) if job["family"] == "bigquant" else None
    checked = 0
    if digests:
        for name, digest in digests.items():
            fp = os.path.join(dest, name)
            if not os.path.exists(fp):
                rec["problems"].append(f"missing {name}")
                continue
            if sha256_file(fp) != digest:
                rec["problems"].append(f"digest mismatch {name}")
            checked += 1
        rec["sha256_checked"] = checked
    sum_year = summary.get(year) if job["family"] == "bigquant" else None
    if sum_year:
        if sum_year.get("files_extracted") not in (None, len(got)):
            rec["problems"].append(f"extract-summary files {sum_year['files_extracted']} != {len(got)}")
        if sum_year.get("total_bytes") not in (None, sum(got.values())):
            rec["problems"].append(f"extract-summary bytes {sum_year['total_bytes']} != {sum(got.values())}")
    rec.update({"files": len(got), "bytes": sum(got.values()),
                "seconds": round(time.time() - t0, 1), "verified": not rec["problems"]})
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--json", default=os.path.join("docs", "evidence", "minute-extract.json"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--delete-zips", action="store_true")
    ap.add_argument("--verify-only", action="store_true", help="不重新解压，只核对已解压目录")
    ap.add_argument("--legacy-identity", default=os.path.join(
        "docs", "legacy", "artifacts-evidence",
        "ten-year-fixed-strategies-minute-accounts-20260913-12", "manifest.json"),
        help="旧库记录的压缩包 sha256（仅作历史身份引用，不重算）")
    a = ap.parse_args()

    jobs = discover(a.raw)
    print(f"archives={len(jobs)}", flush=True)
    if not jobs:
        return 2
    year_digests = load_year_digests(a.raw)
    summary = load_extract_summary(a.raw)
    recorded = load_recorded_digests(a.raw, a.legacy_identity)
    for j in jobs:                      # 包已删时，用历史 manifest 里的真实包名回填路径
        if not os.path.exists(j["zip"]):
            d = recorded.get((j["family"], j["year"]))
            if d and d.get("zip_name"):
                j["zip"] = os.path.join(os.path.dirname(j["zip"]), d["zip_name"])
    print(f"year digest manifests={sorted(year_digests)}  extract-summary={sorted(summary)}"
          f"  recorded zip digests={len(recorded)}", flush=True)

    fn = verify_job if a.verify_only else run_job
    recs = []
    with ProcessPoolExecutor(max_workers=a.workers) as pool:
        futs = [pool.submit(fn, j, year_digests, summary, recorded) for j in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            recs.append(r)
            flag = "OK  " if r["verified"] else "FAIL"
            print(f"{flag} {r['family']:15s} {r['year']}  files={r['files']:6d} bytes={r['bytes']:>13d}"
                  f"  {r['seconds']:6.1f}s  {r['zip']}", flush=True)
            for p in r["problems"]:
                print(f"       ! {p}", flush=True)
    recs.sort(key=lambda r: (r["family"], r["year"]))
    merge_prior(a.json, recs)

    good = [r for r in recs if r["verified"]]
    print(f"verified={len(good)}/{len(recs)}  files={sum(r['files'] for r in recs)}"
          f"  bytes={sum(r['bytes'] for r in recs)}", flush=True)

    out = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "verify-only" if a.verify_only else "extract",
        "note": ("解压时逐个成员校验 zip CRC 并核对成员数/字节数；bigquant 2010-2013 另有逐文件 sha256 清单比对"
                 "（见 sha256_checked）。zip_sha256_recorded 是历史记录的包级摘要（来源见 source 字段），"
                 "非本次重算——压缩包已删除，无法重算包级摘要。解压内容的当前身份见 data/_meta/sha256.tsv。"),
        "archives": len(recs),
        "verified": len(good),
        "files": sum(r["files"] for r in recs),
        "bytes": sum(r["bytes"] for r in recs),
        "records": recs,
    }
    os.makedirs(os.path.dirname(a.json), exist_ok=True)
    with open(a.json, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"record -> {a.json}", flush=True)

    if a.delete_zips:
        if len(good) != len(recs):
            print("refuse to delete zips: some archives failed verification", flush=True)
            return 1
        freed = 0
        for r in recs:
            if not os.path.exists(r["zip"]):
                print(f"skip (already gone): {r['zip']}", flush=True)
                continue
            freed += os.path.getsize(r["zip"])
            os.remove(r["zip"])
        print(f"deleted {len(recs)} zips, freed {freed} bytes ({freed/2**30:.2f} GiB)", flush=True)
    return 0 if len(good) == len(recs) else 1


if __name__ == "__main__":
    sys.exit(main())
