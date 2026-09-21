# -*- coding: utf-8 -*-
"""event-scout 只读清点脚本。

用途：盘点 data/raw/tushare 下事件类批次的行数、时间范围、schema、PIT 属性
（公告日覆盖/缺失率）、冻结边界（>2024-12-31）行数、文本字段长度分布、
标的覆盖与 baostock 池映射。只读数据；所有输出写入本 run 目录。

方法约定：
- knowledge_date（可得时间）：ann_date 优先，无 ann_date 的行情类批次用 trade_date。
- 冻结边界统计：knowledge_date > 2024-12-31 的行数（只统计，不删除、不修改数据）。
- 文本字段：对指定自由文本列统计非空率、平均/最大字符长度（UTF-16 码元近似字符数）。
- 抽样：从 2020 年附近的 chunk 取 3-5 行，长字段截断到 48 字符。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(r"D:/量化")
RAW = REPO / "data/raw/tushare"
RUN_DIR = REPO / "artifacts/runs/20260917T231747-event-scout-f2d1ea"
FREEZE = "20241231"  # 研究窗口上界（不含）；>FREEZE 计入冻结区统计

# baostock 日线池：data/raw/baostock/daily/sh.600000.csv -> 600000.SH
POOL_DIR = REPO / "data/raw/baostock/daily"


def load_baostock_pool() -> set[str]:
    pool = set()
    for p in POOL_DIR.glob("*.csv"):
        code = p.stem  # e.g. sh.600000
        mkt, num = code.split(".")
        pool.add(f"{num}.{mkt.upper()}")
    return pool


def sha256_file(path: Path, limit: int = 4) -> dict:
    """仅对 run 内文件取 sha256；数据文件按 manifest 记录路径与行数身份。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return {"path": str(path), "sha256": h.hexdigest()}


def is_missing(s: pd.Series) -> pd.Series:
    return s.isna() | (s.fillna("").str.strip() == "")


def date_diff_days(a: pd.Series, b: pd.Series) -> pd.Series:
    da = pd.to_datetime(a, format="%Y%m%d", errors="coerce")
    db = pd.to_datetime(b, format="%Y%m%d", errors="coerce")
    return (da - db).dt.days


def lag_stats(diffs: pd.Series) -> dict:
    d = diffs.dropna()
    if d.empty:
        return {"n": 0}
    return {
        "n": int(d.size),
        "median": float(d.median()),
        "p10": float(d.quantile(0.10)),
        "p90": float(d.quantile(0.90)),
        "share_lag_le_0": round(float((d <= 0).mean()), 6),  # 公告早于/等于参照日
        "share_lag_lt_0": round(float((d < 0).mean()), 6),
    }


BATCHES = {
    "forecast": {
        "dir": "forecast/20260909-r1",
        "know": "ann_date",
        "event": "end_date",  # 报告期（披露滞后参照）
        "text_cols": ["type", "summary", "change_reason"],
        "categoricals": ["type", "update_flag"],
        "extra_dates": ["first_ann_date"],
    },
    "express": {
        "dir": "express/20260909-r1",
        "know": "ann_date",
        "event": "end_date",
        "text_cols": ["perf_summary"],
        "categoricals": ["update_flag"],
        "extra_dates": [],
    },
    "repurchase": {
        "dir": "repurchase/20260909-r3",
        "know": "ann_date",
        "event": "exp_date",
        "text_cols": ["proc"],
        "categoricals": ["proc"],
        "extra_dates": [],
    },
    "share_float": {
        "dir": "share_float/20260909-r3",
        "know": "ann_date",
        "event": "float_date",
        "text_cols": ["holder_name", "share_type"],
        "categoricals": ["share_type"],
        "extra_dates": [],
    },
    "stk_holdertrade": {
        "dir": "stk_holdertrade/20260909-r3",
        "know": "ann_date",
        "event": None,
        "text_cols": ["holder_name", "holder_type", "in_de"],
        "categoricals": ["holder_type", "in_de"],
        "extra_dates": [],
    },
    "top_list": {
        "dir": "top_list/20260909-r1",
        "know": "trade_date",
        "event": "trade_date",
        "text_cols": ["reason", "name"],
        "categoricals": ["reason"],
        "extra_dates": [],
    },
    "top_inst": {
        "dir": "top_inst/20260909-r3",
        "know": "trade_date",
        "event": "trade_date",
        "text_cols": ["exalter", "reason", "side"],
        "categoricals": ["side"],
        "extra_dates": [],
    },
    "margin_detail": {
        "dir": "margin_detail/20260909-r1",
        "know": "trade_date",
        "event": "trade_date",
        "text_cols": [],
        "categoricals": [],
        "extra_dates": [],
    },
    "disclosure_date": {
        "dir": "disclosure_date/20260909-r1",
        "know": "ann_date",
        "event": "actual_date",
        "text_cols": [],
        "categoricals": [],
        "extra_dates": ["pre_date", "actual_date"],
    },
    "index_member_all": {
        "dir": "index_member_all/20260909-r1",
        "know": "in_date",
        "event": "out_date",
        "text_cols": ["l1_name", "l2_name", "l3_name", "name"],
        "categoricals": ["is_new"],
        "extra_dates": [],
        "code_col": "con_code_like",  # 实际列名为 ts_code（成分证券码）
    },
}

SAMPLE_TARGET = "2020"  # 抽样文件目标年份


def pick_sample_file(files: list[Path]) -> Path:
    nonempty = [f for f in files if f.stat().st_size > 0]
    for f in nonempty:
        if SAMPLE_TARGET + "01" in f.name or SAMPLE_TARGET in f.name:
            return f
    return nonempty[len(nonempty) // 2] if nonempty else files[0]


def scan_batch(name: str, cfg: dict, pool: set[str]) -> dict:
    bdir = RAW / cfg["dir"]
    files = sorted(bdir.glob("*.csv"))
    t0 = time.time()
    code_col = "ts_code"
    rows_total = 0
    know_missing = 0
    know_min, know_max = None, None
    know_frozen = 0          # knowledge_date > 20241231
    event_frozen = 0         # event date > 20241231（与可得日不同的行数）
    event_min, event_max = None, None
    codes: set[str] = set()
    bj_codes: set[str] = set()
    schema: dict[str, int] = {}          # 列名 -> 非空出现次数（跨文件累计）
    text_stats: dict[str, dict] = {}
    cat_counts: dict[str, dict] = {}
    lag_know_event: list[float] = []     # know - event 天数
    extra_lags: dict[str, list[float]] = {}

    empty_files = 0
    for fi, f in enumerate(files):
        try:
            df = pd.read_csv(f, dtype=str, low_memory=False)
        except pd.errors.EmptyDataError:
            empty_files += 1
            continue
        rows_total += len(df)
        for c in df.columns:
            schema[c] = schema.get(c, 0) + int(df[c].notna().sum())
        know = df[cfg["know"]] if cfg["know"] in df.columns else pd.Series([None] * len(df))
        km = is_missing(know)
        know_missing += int(km.sum())
        kv = know[~km]
        if len(kv):
            kmin, kmax = kv.min(), kv.max()
            know_min = kmin if know_min is None else min(know_min, kmin)
            know_max = kmax if know_max is None else max(know_max, kmax)
            know_frozen += int((kv > FREEZE).sum())
        if code_col in df.columns:
            cv = df[code_col].dropna()
            codes.update(cv)
            bj_codes.update(cv[cv.str.endswith(".BJ")])
        if cfg["event"] and cfg["event"] in df.columns and len(kv):
            ev = df[cfg["event"]]
            em = is_missing(ev)
            evv = ev[~em]
            if len(evv):
                event_min = evv.min() if event_min is None else min(event_min, evv.min())
                event_max = evv.max() if event_max is None else max(event_max, evv.max())
                event_frozen += int((evv > FREEZE).sum())
            both = (~km) & (~em)
            if both.any():
                d = date_diff_days(df.loc[both, cfg["know"]], df.loc[both, cfg["event"]])
                lag_know_event.extend(d.dropna().tolist())
        for ed in cfg["extra_dates"]:
            if ed in df.columns and cfg["know"] in df.columns:
                m = (~km) & (~is_missing(df[ed]))
                if m.any():
                    d = date_diff_days(df.loc[m, cfg["know"]], df.loc[m, ed])
                    extra_lags.setdefault(ed, []).extend(d.dropna().tolist())
        for tc in cfg["text_cols"]:
            if tc in df.columns:
                s = df[tc].fillna("").astype(str).str.strip()
                nn = s[s != ""]
                st = text_stats.setdefault(tc, {"nonnull": 0, "sum_len": 0, "max_len": 0})
                st["nonnull"] += int(len(nn))
                if len(nn):
                    lens = nn.str.len()
                    st["sum_len"] += int(lens.sum())
                    st["max_len"] = max(st["max_len"], int(lens.max()))
        for cc in cfg["categoricals"]:
            if cc in df.columns:
                vc = df[cc].fillna("").astype(str).str.strip()
                vc = vc[vc != ""].value_counts().head(12)
                dst = cat_counts.setdefault(cc, {})
                for k, v in vc.items():
                    dst[k] = dst.get(k, int(v)) + int(v) if k in dst else int(v)
        if fi % 200 == 0:
            print(f"  [{name}] file {fi + 1}/{len(files)} rows={rows_total} "
                  f"elapsed={time.time() - t0:.0f}s", flush=True)

    in_pool = codes & pool
    sample_file = pick_sample_file(files)
    sdf = pd.read_csv(sample_file, dtype=str, low_memory=False)
    sdf = sdf.dropna(how="all").head(5)
    samples = []
    for _, r in sdf.iterrows():
        samples.append({k: (str(v)[:48] if pd.notna(v) else None) for k, v in r.items()})

    text_summary = {}
    for tc, st in text_stats.items():
        text_summary[tc] = {
            "nonnull": st["nonnull"],
            "avg_len": round(st["sum_len"] / st["nonnull"], 1) if st["nonnull"] else 0.0,
            "max_len": st["max_len"],
        }

    result = {
        "batch": name,
        "dir": cfg["dir"],
        "files": len(files),
        "empty_files": empty_files,
        "rows_total": rows_total,
        "schema": dict(sorted(schema.items())),
        "know_date_col": cfg["know"],
        "know_missing": know_missing,
        "know_missing_rate": round(know_missing / rows_total, 6) if rows_total else None,
        "know_range": [know_min, know_max],
        "know_frozen_gt20241231": know_frozen,
        "know_window_2015_2024": rows_total - know_frozen - know_missing
        if rows_total else None,
        "event_date_col": cfg["event"],
        "event_range": [event_min, event_max] if cfg["event"] else None,
        "event_frozen_gt20241231": event_frozen if cfg["event"] else None,
        "lag_know_minus_event": lag_stats(pd.Series(lag_know_event)) if lag_know_event else None,
        "extra_lags": {k: lag_stats(pd.Series(v)) for k, v in extra_lags.items()},
        "text_fields": text_summary,
        "categorical_top": cat_counts,
        "unique_codes": len(codes),
        "codes_in_baostock_pool": len(in_pool),
        "codes_bj_not_in_pool": len(bj_codes),
        "sample_file": sample_file.name,
        "samples": samples,
        "elapsed_s": round(time.time() - t0, 1),
    }
    print(f"[{name}] done rows={rows_total} elapsed={result['elapsed_s']}s", flush=True)
    return result


def main() -> None:
    t0 = time.time()
    pool = load_baostock_pool()
    print(f"baostock pool codes: {len(pool)}", flush=True)
    out = {
        "run_id": "20260917T231747-event-scout-f2d1ea",
        "purpose": "事件类批次只读清点（无因子计算、无回测）",
        "freeze_rule": f"knowledge_date > {FREEZE} 仅统计（研究窗口 2015-2024，2025+ 冻结）",
        "baostock_pool_codes": len(pool),
        "env": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__,
        },
        "batches": {},
    }
    for name in ["forecast", "express", "repurchase", "share_float", "stk_holdertrade",
                 "top_list", "top_inst", "margin_detail", "disclosure_date",
                 "index_member_all"]:
        out["batches"][name] = scan_batch(name, BATCHES[name], pool)

    out["elapsed_s_total"] = round(time.time() - t0, 1)
    out["status"] = "completed"
    out_path = RUN_DIR / "scan_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"saved -> {out_path} total={out['elapsed_s_total']}s", flush=True)


if __name__ == "__main__":
    main()
