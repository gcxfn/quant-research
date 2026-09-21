# -*- coding: utf-8 -*-
"""02_judge.py — exp-20260918-p2r14-minute-structure 判定阶段。

消费 data/processed/minute-feats-20260918/minute_feats.parquet（sha256
fail-closed 对照表 manifest），构建冻结池面板，dev（2015–2020）判定
U1..U6 六单元 + 沪市 2018-08-20 分段臂；过门单元 val（2021–2024）一次性。
输出 metrics.json / report.md 到 run 目录。无盈利声称；全部为
过滤/标记/裁决用途。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))

from quant.research.p2r14_minute_structure import (  # noqa: E402
    DEV_END, DEV_START, VAL_END, VAL_START, build_panel, run_dev_and_val)

FEATS_DIR = REPO / "data" / "processed" / "minute-feats-20260918"
RUN = Path(__file__).resolve().parents[1]
T0 = time.perf_counter()


def log(msg: str) -> None:
    print(f"[{time.perf_counter() - T0:7.1f}s] {msg}", flush=True)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jsonable(obj):
    """Recursively convert numpy/polars scalars and dataclasses to JSON."""
    if hasattr(obj, "_asdict"):
        return {k: jsonable(v) for k, v in obj._asdict().items()}
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (pl.DataFrame, pl.Series)):
        return jsonable(obj.to_dicts() if isinstance(obj, pl.DataFrame)
                        else obj.to_list())
    if isinstance(obj, date):
        return obj.isoformat()
    import numpy as np
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, float) and obj != obj:
        return "NaN"
    return obj


def main() -> None:
    manifest = json.loads(
        (FEATS_DIR / "manifest.json").read_text(encoding="utf-8"))
    digest = sha256_of(FEATS_DIR / "minute_feats.parquet")
    if digest != manifest["outputs"]["sha256"]:
        raise RuntimeError(f"identity fail-closed: feats sha256 {digest} != "
                           f"manifest {manifest['outputs']['sha256']}")
    log(f"feature table verified: {manifest['outputs']['rows']} rows")

    feats = pl.read_parquet(FEATS_DIR / "minute_feats.parquet")
    panel, waterfall = build_panel(REPO, feats)
    log(f"panel built: {waterfall['pool_rows']} pool rows "
        f"({waterfall['names_per_day_mean']:.0f} names/day)")
    del feats

    log("dev judgment U1..U6 ...")
    results = run_dev_and_val(panel)
    passed = [u for u, r in results.items() if r["dev"]["passed"]]
    log(f"dev passers: {passed or 'none'}")

    metrics = {
        "experiment_id": "exp-20260918-p2r14-minute-structure",
        "run_id": RUN.name,
        "window": {"dev": [str(DEV_START), str(DEV_END)],
                   "val": [str(VAL_START), str(VAL_END)],
                   "val_rule": "仅过门单元一次性消费"},
        "pool_waterfall": waterfall,
        "units": results,
        "pass_rule": ">=2 单元过门 → 微观结构过滤线有候选（组合资格）",
        "n_units_passed_dev": len(passed),
        "passed_units": passed,
        "trials_this_round": 6,
        "trials_cumulative_after": 189,
        "disclaimers": [
            "全部单元为过滤/事件/标记/裁决用途，非独立入场触发",
            "无盈利声称；dev 为第 8 次重用（淘汰用）；val 一次性",
            "2025+ 零接触（结构性与文件级双重保证）"],
        "elapsed_s": round(time.perf_counter() - T0, 1),
    }
    (RUN / "metrics.json").write_text(
        json.dumps(jsonable(metrics), ensure_ascii=False, indent=2),
        encoding="utf-8")
    log(f"metrics written ({metrics['elapsed_s']:.0f}s total)")


if __name__ == "__main__":
    main()
