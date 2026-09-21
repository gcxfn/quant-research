# -*- coding: utf-8 -*-
"""汇总 deep-scan-20260917 报告: 生成 README.md 与 run_manifest.json"""
import json
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import polars as pl

ROOT = Path("D:/量化")
OUT = ROOT / "data" / "_meta" / "deep-scan-20260917"
RUN_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
PROGRESS = RUN_DIR / "progress.jsonl"

LEVEL_ORDER = {"blocker": 0, "warning": 1, "info": 2}


def collect_reports():
    rows = []
    for src in sorted(OUT.iterdir()):
        if not src.is_dir():
            continue
        for f in sorted(src.glob("*.json")):
            try:
                payload = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            for bdir, r in (payload.get("batches") or {}).items():
                cov = r.get("date_coverage") or {}
                main_col, main = None, {"min": None, "max": None, "rows_gt_20241231": 0}
                for c, v in cov.items():
                    if (v.get("rows_gt_20241231") or 0) >= (main.get("rows_gt_20241231") or 0):
                        main_col, main = c, v
                    elif main["min"] is None and v.get("min"):
                        main_col, main = c, v
                issues = r.get("issues") or []
                lv = {k: sum(1 for i in issues if i.get("level") == k) for k in LEVEL_ORDER}
                unit_concl = r.get("unit_check_conclusion")
                if not unit_concl:
                    uc = r.get("unit_check") or {}
                    unit_concl = uc.get("unit_conclusion")
                rows.append({
                    "source": src.name,
                    "dataset": f.stem,
                    "batch": bdir,
                    "status": r.get("status"),
                    "mode": r.get("mode"),
                    "rows": r.get("rows_total"),
                    "date_col": main_col,
                    "dmin": main.get("min"),
                    "dmax": main.get("max"),
                    "frozen": main.get("rows_gt_20241231") or 0,
                    "dup": r.get("duplicate_rows") if r.get("duplicate_rows") is not None else r.get("duplicate_date_rows"),
                    "files": (r.get("files") or {}).get("n_total"),
                    "unit_conclusion": unit_concl,
                    "blocker": lv["blocker"], "warning": lv["warning"], "info": lv["info"],
                    "issues": issues,
                })
    return rows


def fmt(x):
    if x is None:
        return "-"
    if isinstance(x, int) and abs(x) >= 10000:
        return f"{x:,}"
    return str(x)


def main():
    t0 = time.time()
    rows = collect_reports()
    # README
    lines = [
        "# raw 深扫补充台账 (deep-scan-20260917)",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        "- 范围: data/raw/{xiaodefa, tushare(除 20260917-r1 三批次), bigquant, em_fin, ths, tx, user_dataset, user_minute_1m(仅顶层清点)}",
        "- 冻结边界: 2025-01-01 起冻结; 所有 >2024-12-31 的数据行均只报告、未删除、未修改 data/raw。",
        "- data/raw 只读; 本目录仅新增, 不改动 data/_meta 既有文件。",
        "",
        "## 汇总表",
        "",
        "| 来源 | 数据集 | 批次 | 状态 | 文件数 | 行数 | 日期列 | 范围 | >2024-12-31 行 | 重复行 | blocker | warning | info | 单位结论 |",
        "|---|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in sorted(rows, key=lambda x: (x["source"], x["dataset"], x["batch"])):
        concl = r["unit_conclusion"]
        if isinstance(concl, dict):
            concl = "; ".join(f"{k}={v}" for k, v in concl.items())[:120]
        lines.append(
            f"| {r['source']} | {r['dataset']} | {r['batch'].split('/', 1)[-1]} | {r['status']} | "
            f"{fmt(r['files'])} | {fmt(r['rows'])} | {r['date_col'] or '-'} | "
            f"{r['dmin'] or '-'} … {r['dmax'] or '-'} | {fmt(r['frozen'])} | {fmt(r['dup'])} | "
            f"{r['blocker']} | {r['warning']} | {r['info']} | {concl or '-'} |")
    # 问题清单
    tot = {k: sum(r[k] for r in rows) for k in LEVEL_ORDER}
    lines += ["", f"## 问题分级汇总 (blocker={tot['blocker']}, warning={tot['warning']}, info={tot['info']})", ""]
    for lvl in ("blocker", "warning", "info"):
        lines += [f"### {lvl}", ""]
        n = 0
        for r in sorted(rows, key=lambda x: (x["source"], x["dataset"], x["batch"])):
            for i in r["issues"]:
                if i.get("level") == lvl:
                    code = i.get("code")
                    det = i.get("detail", "").replace("|", "\\|").replace("\n", " ")[:220]
                    lines.append(f"- `{r['source']}/{r['dataset']}` [{code}] {det}")
                    n += 1
                    if n > 400:
                        break
            if n > 400:
                lines.append("- …(更多略, 见各批次 JSON)")
                break
        lines.append("")
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    # run manifest
    started = ended = None
    n_done = n_failed = 0
    if PROGRESS.exists():
        for line in PROGRESS.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("status") in ("done", "failed"):
                n_done += 1 if rec["status"] == "done" else 0
                n_failed += 1 if rec["status"] == "failed" else 0
            started = started or rec.get("at")
            ended = rec.get("at")
    remaining = []
    fp = RUN_DIR / "remaining.json"
    if fp.exists():
        remaining = json.loads(fp.read_text(encoding="utf-8"))
    manifest = {
        "run_id": RUN_DIR.name,
        "task": "data/raw 深扫(已登记未深扫批次) → data/_meta/deep-scan-20260917",
        "status": "completed" if not remaining else "aborted-time-budget-partial",
        "started_at": started, "ended_at": ended,
        "duration_budget_min": 82,
        "command": ('"D:/量化/.venv/Scripts/python.exe" -X utf8 artifacts/runs/'
                    f"{RUN_DIR.name}/deepscan.py artifacts/runs/{RUN_DIR.name} <deadline_epoch>"),
        "engine_script": f"artifacts/runs/{RUN_DIR.name}/deepscan.py",
        "engine_sha256": __import__("hashlib").sha256(
            (RUN_DIR / "deepscan.py").read_bytes()).hexdigest(),
        "environment": {
            "python": sys.version.split()[0], "polars": pl.__version__,
            "platform": platform.platform(),
        },
        "units_done": n_done, "units_failed": n_failed,
        "units_remaining": len(remaining),
        "remaining_units": remaining[:80],
        "data_raw_touched": False,
        "notes": "data/raw 全程只读; 未修改 data/_meta 既有文件; 未初始化 git; 未联网。",
    }
    (RUN_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"README rows={len(rows)} issues={tot} elapsed={round(time.time() - t0, 1)}s")
    print(f"manifest: status={manifest['status']} done={n_done} failed={n_failed} remaining={len(remaining)}")


if __name__ == "__main__":
    main()
