# -*- coding: utf-8 -*-
"""raw 深扫引擎 (deep-scan-20260917)。
只读扫描 data/raw 指定来源批次，产出 data/_meta/deep-scan-20260917/<source>/<dataset>.json。
用法: python deepscan.py <run_dir> <deadline_epoch>
支持断点续扫: run_dir/progress.jsonl 记录已完成单元。
"""
import hashlib
import json
import os
import platform
import re
import sys
import time
import traceback
import zipfile
from datetime import datetime
from pathlib import Path

import polars as pl

ROOT = Path("D:/量化")
RAW = ROOT / "data" / "raw"
META = ROOT / "data" / "_meta"
OUT = META / "deep-scan-20260917"
FROZEN = "20241231"

RUN_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
DEADLINE = float(sys.argv[2]) if len(sys.argv) > 2 else float("inf")
PROGRESS = RUN_DIR / "progress.jsonl"

SOURCES = ["xiaodefa", "tushare", "bigquant", "em_fin", "ths", "tx", "user_dataset", "user_minute_1m"]
# 跳过(近期已验收)
SKIP_PREFIXES = [
    "tushare/fund_daily/20260917-r1",
    "tushare/fund_adj/20260917-r1",
    "tushare/stk_limit/20260917-r1",
]

INV = {}
with (META / "inventory.json").open(encoding="utf-8") as f:
    _inv = json.load(f)
for b in _inv["batches"]:
    INV[b["path"].replace("\\", "/")] = b

# ---------------- 主键候选 ----------------
KEYS = {
    "adj_factor": ["ts_code", "trade_date"],
    "stk_limit": ["ts_code", "trade_date"],
    "trade_cal": ["exchange", "cal_date"],
    "moneyflow": ["ts_code", "trade_date"],
    "daily_basic": ["ts_code", "trade_date"],
    "margin_detail": ["trade_date", "ts_code", "exchange_id"],
    "top_list": ["trade_date", "ts_code", "exchanges", "side"],
    "top_inst": ["trade_date", "ts_code", "exchanges", "side", "brk_code"],
    "income": ["ts_code", "end_date", "report_type"],
    "balancesheet": ["ts_code", "end_date", "report_type"],
    "cashflow": ["ts_code", "end_date", "report_type"],
    "fina_indicator": ["ts_code", "end_date", "ann_date"],
    "forecast": ["ts_code", "end_date", "ann_date"],
    "express": ["ts_code", "end_date", "ann_date"],
    "dividend": ["ts_code", "end_date", "div_proc"],
    "repurchase": ["ts_code", "ann_date"],
    "share_float": ["ts_code", "ann_date", "float_date"],
    "stk_holdertrade": ["ts_code", "ann_date", "holder_name"],
    "disclosure_date": ["ts_code", "end_date"],
    "index_member_all": ["index_code", "con_code", "in_date"],
    "sw_index_daily": ["ts_code", "trade_date"],
    "sw_index_daily_l2": ["ts_code", "trade_date"],
    "stock_basic": ["ts_code"],
    "fund_basic": ["fund_code"],
    "suspend_d": ["ts_code", "trade_date"],
    "stk_auction_c": ["ts_code", "trade_date"],
    "stk_auction_o": ["ts_code", "trade_date"],
    "cyq_perf": ["ts_code", "trade_date"],
    "stk_nineturn": ["ts_code", "trade_date"],
    "idx_factor_pro": ["ts_code", "trade_date"],
    "ths_daily": ["ts_code", "trade_date"],
    "dc_daily": ["ts_code", "trade_date"],
    "sw_daily": ["ts_code", "trade_date"],
    "ci_daily": ["ts_code", "trade_date"],
    "hk_hold": ["trade_date", "ts_code"],
    "limit_list_d": ["trade_date", "ts_code", "limit_type"],
    "top10_holders": ["ts_code", "end_date", "holder_name"],
    "top10_floatholders": ["ts_code", "end_date", "holder_name"],
    "block_trade": ["ts_code", "trade_date", "price", "vol"],
    "st": ["ts_code", "ann_date"],
    "stock_st": ["ts_code", "ann_date"],
    "namechange": ["ts_code", "start_date", "change_reason"],
    "pledge_detail": ["ts_code", "ann_date"],
    "hm_detail": ["ts_code", "trade_date"],
    "ggt_daily": ["trade_date", "money_type"],
    "daily_info": ["trade_date"],
    "sz_daily_info": ["trade_date"],
    "cn_m": ["month", "indicator"],
    "cn_cpi": ["month", "indicator_id"],
    "cn_ppi": ["month", "indicator_id"],
    "cn_pmi": ["month", "indicator_id"],
    "sf_month": ["month"],
    "cn_schedule": ["date", "name"],
}
KEY_FALLBACK = [
    ["ts_code", "trade_date"], ["trade_date", "ts_code"], ["ts_code", "ann_date"],
    ["ts_code", "end_date"], ["ts_code", "cal_date"], ["index_code", "trade_date"],
    ["ts_code", "trade_dt"], ["ts_code", "date"], ["trade_date"], ["cal_date"], ["ts_code"],
]

DATE_RE = re.compile(r"date$|_date$|month$|quarter$|week$")
DATE_EXACT = {"trade_dt", "date", "datetime", "time", "时间"}

NUMERIC_PRIORITY = [
    "close", "open", "high", "low", "pre_close", "preclose", "vol", "volume", "amount",
    "adj_factor", "net_amount", "rzye", "rqye", "rzmre", "turnover_rate", "turnover",
    "total_mv", "circ_mv", "dv_ratio", "pe", "pb", "up_limit", "down_limit",
]


def now_s():
    return datetime.now().isoformat(timespec="seconds")


def log(msg):
    print(f"[{now_s()}] {msg}", flush=True)


def jdefault(o):
    if isinstance(o, (int, float, str, bool)) or o is None:
        if isinstance(o, float) and (o != o):
            return None
        return o
    try:
        import numpy as np
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if o != o else float(o)
    except Exception:
        pass
    return str(o)


def r2(x, nd=4):
    try:
        if x is None:
            return None
        return round(float(x), nd)
    except Exception:
        return None


def progress(unit, status, extra=None):
    rec = {"unit": unit, "status": status, "at": now_s()}
    for k, v in (extra or {}).items():
        if k != "status":
            rec[k] = v
    rec["unit_status"] = (extra or {}).get("status")
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def done_units():
    if not PROGRESS.exists():
        return set()
    out = set()
    for line in PROGRESS.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("status") in ("done", "skipped"):
            out.add(r["unit"])
    return out


# ---------------- 单元枚举 ----------------
def list_units():
    units = []
    for src in SOURCES:
        base = RAW / src
        if not base.exists():
            continue
        for name in sorted(os.listdir(base)):
            d = base / name
            if not d.is_dir():
                continue  # 源根目录散文件单独记录
            subs = [x for x in d.iterdir() if x.is_dir()]
            if subs:
                # 两层: dataset/batch 或更深 (bigquant years)
                for b in sorted(subs):
                    bsubs = [x for x in b.iterdir() if x.is_dir()]
                    if bsubs and b.name in ("years",):
                        for y in sorted(bsubs):
                            units.append(y)
                    else:
                        units.append(b)
            else:
                units.append(d)
    units = [u for u in units if not any(u.relative_to(RAW).as_posix().startswith(p) for p in SKIP_PREFIXES)]
    # 排序: 来源优先级
    order = {s: i for i, s in enumerate(SOURCES)}
    units.sort(key=lambda p: (order.get(p.relative_to(RAW).as_posix().split("/")[0], 99), p.as_posix()))
    return units


def dataset_of(u: Path):
    rel = u.relative_to(RAW)
    return rel.parts[1] if len(rel.parts) > 1 else rel.parts[0]


def batch_of(u: Path):
    return "/".join(u.relative_to(RAW).parts[2:]) if len(u.relative_to(RAW).parts) > 2 else u.name


def mode_of(u: Path):
    rel = u.relative_to(RAW).as_posix()
    if rel.startswith("user_minute_1m"):
        return "inventory-only"
    if rel.startswith("bigquant/minute-bulk-20260915-1/years/"):
        suffixes = {p.suffix.lower() for p in u.iterdir() if p.is_file()}
        year = u.name
        if ".parquet" in suffixes:
            return "frozen-name-only" if year in ("2025", "2026") else "parquet-meta"
        if ".csv" in suffixes:
            return "sampled-csv"
        return "inventory-only"
    if rel.split("/")[0] in ("em_fin", "ths", "tx"):
        return "json"
    if rel.startswith("user_dataset"):
        return "zip"
    return "full"


# ---------------- tabular 扫描 ----------------
def probe_schema(u: Path):
    """从首个数据文件探测列名与类型(含类型推断与 utf8 全字符串两种)。"""
    csvs = sorted(p for p in u.glob("*.csv") if p.stat().st_size > 0)
    pqs = sorted([p for p in u.iterdir() if p.suffix.lower() in (".parquet", ".pq")])
    if pqs:
        sch = pl.read_parquet_schema(pqs[0])
        return {c: str(t) for c, t in sch.items()}, "parquet"
    if not csvs:
        raise RuntimeError("no non-empty csv to probe")
    f = csvs[0]
    df = pl.read_csv(f, infer_schema_length=2000, encoding="utf8-lossy", truncate_ragged_lines=True, n_rows=200)
    return {c: str(t) for c, t in df.schema.items()}, "csv"


def pick_key(cols, dataset):
    cands = []
    if dataset in KEYS:
        cands.append(KEYS[dataset])
    cands += KEY_FALLBACK
    for k in cands:
        if all(c in cols for c in k):
            return k
    return None


def bulk_lf(u: Path, kind: str):
    if kind == "csv":
        return pl.scan_csv(
            str(u / "*.csv"), infer_schema=False, encoding="utf8-lossy",
            truncate_ragged_lines=True,
        )
    return pl.scan_parquet(str(u / "*.parquet"))


def scan_tabular(u: Path, mode: str):
    rel = u.relative_to(RAW).as_posix()
    dataset = dataset_of(u)
    files = sorted(p for p in u.rglob("*") if p.is_file())
    csvs = [p for p in files if p.suffix.lower() == ".csv" and p.stat().st_size > 0]
    empty_csvs = [p for p in files if p.suffix.lower() == ".csv" and p.stat().st_size == 0]
    pqs = [p for p in files if p.suffix.lower() in (".parquet", ".pq")]
    manifests = [p for p in files if p.name == "manifest.json" or "sha256" in p.name.lower()
                 or p.name.endswith(".meta.json")]
    others = [p for p in files if p not in csvs and p not in pqs and p not in manifests]
    total_bytes = sum(p.stat().st_size for p in files)
    res = {
        "batch_dir": rel,
        "mode": mode,
        "files": {
            "n_total": len(files), "n_csv": len(csvs), "n_parquet": len(pqs),
            "n_empty_csv": len(empty_csvs),
            "n_manifest": len(manifests), "n_other": len(others),
            "manifest_names": [p.name for p in manifests][:10],
            "other_names": [p.name for p in others][:10],
            "total_bytes": total_bytes,
        },
        "issues": [],
    }
    if empty_csvs:
        res["issues"].append({"level": "info", "code": "empty_csv_chunks",
                              "detail": f"{len(empty_csvs)} 个 0 字节空 CSV(如按日抓取无数据日), 例: "
                                        f"{[p.name for p in empty_csvs[:5]]}; 未计入行数统计"})
    inv = INV.get(rel)
    if inv:
        res["inventory_registration"] = {"files": inv["files"], "bytes": inv["bytes"]}
        if inv["files"] != len(files):
            res["issues"].append({"level": "warning", "code": "inventory_file_count_mismatch",
                                  "detail": f"登记 {inv['files']} 个文件, 实际 {len(files)}"})
        if abs(inv["bytes"] - total_bytes) > 1024:
            res["issues"].append({"level": "info", "code": "inventory_bytes_diff",
                                  "detail": f"登记 {inv['bytes']}B, 实际 {total_bytes}B"})
    else:
        res["issues"].append({"level": "warning", "code": "not_in_inventory",
                              "detail": "批次未在 data/_meta/inventory.json 登记"})
    if (csvs or pqs) and not manifests:
        res["issues"].append({"level": "blocker", "code": "manifest_missing",
                              "detail": "批次目录内无 manifest.json/sha256/meta 清单"})

    if not csvs and not pqs:
        res["status"] = "no_tabular_data"
        if others or manifests:
            res["issues"].append({"level": "info", "code": "no_data_files",
                                  "detail": f"无 csv/parquet 数据文件; 仅 {len(others)} 个其他文件"})
        return res

    schema, kind = probe_schema(u)
    res["schema"] = schema
    res["n_columns"] = len(schema)
    date_cols = [c for c in schema if DATE_RE.search(c.lower()) or c.lower() in DATE_EXACT][:8]
    num_cols = [c for c in schema if schema[c] in ("Int64", "Int32", "Float64", "Float32", "Int8", "UInt32", "Int16")]
    num_cols = sorted(set(num_cols), key=lambda c: (NUMERIC_PRIORITY.index(c) if c in NUMERIC_PRIORITY else 999, c))[:40]
    res["date_columns"] = date_cols
    res["numeric_columns_checked"] = num_cols

    try:
        lf = bulk_lf(u, kind)
        lf.head(1).collect(engine="streaming")  # 提前暴露 schema 冲突
    except Exception as e:
        res["issues"].append({"level": "warning", "code": "bulk_scan_failed_perfile_fallback",
                              "detail": f"{type(e).__name__}: {str(e)[:200]}"})
        return scan_tabular_perfile(u, res, kind, date_cols, dataset)
    return scan_tabular_bulk(u, res, lf, kind, date_cols, num_cols, dataset, mode)


def scan_tabular_bulk(u, res, lf, kind, date_cols, num_cols, dataset, mode):
    aggs = [pl.len().alias("_n")]
    for c in date_cols:
        d = pl.col(c).cast(pl.Utf8).str.replace_all("-", "").str.slice(0, 8)
        aggs += [d.min().alias(f"_min_{c}"), d.max().alias(f"_max_{c}"),
                 (d > pl.lit(FROZEN)).sum().alias(f"_frz_{c}"),
                 pl.col(c).is_null().sum().alias(f"_nul_{c}")]
    for c in num_cols:
        x = pl.col(c).cast(pl.Float64, strict=False)
        aggs += [x.min().alias(f"_nmin_{c}"), x.max().alias(f"_nmax_{c}")]
    st = lf.select(aggs).collect(engine="streaming").row(0, named=True)
    res["rows_total"] = int(st["_n"])
    cov = {}
    for c in date_cols:
        cov[c] = {
            "min": st.get(f"_min_{c}"), "max": st.get(f"_max_{c}"),
            "rows_gt_20241231": int(st.get(f"_frz_{c}") or 0),
            "null_rows": int(st.get(f"_nul_{c}") or 0),
        }
    res["date_coverage"] = cov
    frozen_any = sum(v["rows_gt_20241231"] for v in cov.values())
    res["frozen_rows_gt_20241231_maxcol"] = max([v["rows_gt_20241231"] for v in cov.values()] or [0])
    if frozen_any:
        worst = max(cov.items(), key=lambda kv: kv[1]["rows_gt_20241231"])
        ref_cal = dataset in ("trade_cal",)
        res["issues"].append({
            "level": "warning" if ref_cal else "blocker",
            "code": "frozen_window_rows" if not ref_cal else "frozen_window_rows_reference_calendar",
            "detail": f"日期列 {worst[0]} 有 {worst[1]['rows_gt_20241231']} 行 > 2024-12-31"
                      f" (max={worst[1]['max']}); 冻结边界审查: 只报告不删除"
                      + ("; 参考日历类数据, 2025+ 为日历定义而非行情观测" if ref_cal else "")})
    nummag = {}
    for c in num_cols:
        mn, mx = st.get(f"_nmin_{c}"), st.get(f"_nmax_{c}")
        if mn is not None or mx is not None:
            nummag[c] = {"min": r2(mn), "max": r2(mx)}
    res["numeric_magnitude"] = nummag

    # 主键唯一性
    key = pick_key(set(lf.collect_schema().names()), dataset)
    res["primary_key"] = key

    def _dup_count(keycols):
        d = (lf.group_by([pl.col(k) for k in keycols]).agg(pl.len().alias("_c")).filter(pl.col("_c") > 1)
             .select(pl.len().alias("dup_keys"), pl.col("_c").sum().alias("dup_rows"))
             .collect(engine="streaming").row(0, named=True))
        return int(d["dup_keys"] or 0), int(d["dup_rows"] or 0)

    if key:
        res["duplicate_keys"], res["duplicate_rows"] = _dup_count(key)
        # 版本列(update_flag): 财务数据集按 (键+update_flag) 复核, 判断是否版本快照而非缺陷
        if res["duplicate_rows"] and "update_flag" in lf.collect_schema().names() and "update_flag" not in key:
            vkey = key + ["update_flag"]
            vk, vr = _dup_count(vkey)
            res["duplicate_rows_with_version_col"] = vr
            if vr == 0:
                res["issues"].append({"level": "info", "code": "duplicate_rows_version_snapshots",
                                      "detail": f"主键 {key} 重复 {res['duplicate_rows']} 行, 但 {vkey} 下唯一"
                                                " (update_flag 版本快照, 非缺陷; 使用时须按 update_flag 取最新)"})
            else:
                res["issues"].append({"level": "warning", "code": "duplicate_primary_key_rows",
                                      "detail": f"主键 {key} 重复 {res['duplicate_rows']} 行; 含 update_flag 后仍重复 {vr} 行"})
        elif res["duplicate_rows"]:
            res["issues"].append({"level": "warning", "code": "duplicate_primary_key_rows",
                                  "detail": f"主键 {key} 重复: {res['duplicate_keys']} 个键 / {res['duplicate_rows']} 行"})

    # 抽样 5 行
    cols = list(lf.collect_schema().names())
    keep = cols[:24]
    samp = lf.select(keep).head(5).collect(engine="streaming")
    res["sample_rows"] = [
        {k: (str(v)[:48] if v is not None else None) for k, v in zip(keep, row)}
        for row in samp.iter_rows()
    ]

    targeted_checks(u, dataset, lf, res, kind)
    header_manifest_checks(u, res, kind)
    res["status"] = "completed"
    return res


def header_manifest_checks(u: Path, res, kind):
    """CSV 批次表头一致性 + manifest 声明行数抽查(采样)"""
    if kind != "csv":
        return
    csvs = sorted(p for p in u.glob("*.csv") if p.stat().st_size > 0)
    if len(csvs) < 20:
        return
    try:
        headers = {}
        for f in csvs:
            with f.open("r", encoding="utf-8", errors="replace") as fh:
                headers[f.name] = fh.readline().rstrip("\r\n")
        from collections import Counter
        cnt = Counter(headers.values())
        modal, modal_n = cnt.most_common(1)[0]
        dev = [(n, h) for n, h in headers.items() if h != modal]
        res["header_consistency"] = {
            "n_files": len(csvs), "distinct_headers": len(cnt),
            "modal_header_cols": modal.count(",") + 1,
            "deviating_files": len(dev),
        }
        empty_dev = [n for n, h in dev if not h.strip()]
        order_dev = [n for n, h in dev if h.strip()]
        if empty_dev:
            res["issues"].append({"level": "blocker", "code": "csv_missing_header_row",
                                  "detail": f"{len(empty_dev)} 个文件首行为空(缺表头, 首行数据被当作列名): {empty_dev[:5]}"})
        if order_dev:
            res["issues"].append({"level": "warning", "code": "csv_header_inconsistent",
                                  "detail": f"{len(order_dev)}/{len(csvs)} 个文件表头与主流不一致(列序/列集不同), "
                                            f"例: {order_dev[:3]} ; 主流表头列数 {modal.count(',') + 1}"})
        # manifest 声明 rows 抽查
        mf = u / "manifest.json"
        if mf.exists():
            man = json.loads(mf.read_text(encoding="utf-8"))
            chunks = man.get("chunks") or {}
            with_rows = {k: v for k, v in chunks.items() if isinstance(v, dict) and v.get("rows") is not None}
            if with_rows:
                import random
                rnd = random.Random(20260917)
                sample_keys = rnd.sample(sorted(with_rows), min(8, len(with_rows)))
                # 缺表头文件必查
                for n in empty_dev:
                    k = n.replace("chunk_", "").replace(".csv", "")
                    if k in with_rows and k not in sample_keys:
                        sample_keys[0] = k
                checked, mismatch = [], []
                for k in sample_keys:
                    f = u / k if (u / k).exists() else u / f"chunk_{k}.csv"
                    if not f.exists():
                        mismatch.append({"chunk": k, "problem": "manifest 声明的 chunk 文件不存在"})
                        continue
                    n_act = pl.scan_csv(f, infer_schema=False, encoding="utf8-lossy",
                                        truncate_ragged_lines=True, skip_rows=1).select(pl.len()).collect().item()
                    checked.append(k)
                    if n_act != with_rows[k]["rows"]:
                        mismatch.append({"chunk": k, "manifest_rows": with_rows[k]["rows"], "actual_rows": int(n_act)})
                res["manifest_rows_spot_check"] = {"checked": len(checked), "mismatches": mismatch}
                if mismatch:
                    diffs = [m["manifest_rows"] - m["actual_rows"] for m in mismatch if "actual_rows" in m]
                    if diffs and set(diffs) == {1} and len(mismatch) == len(checked):
                        res["issues"].append({"level": "info", "code": "manifest_rows_off_by_one_convention",
                                              "detail": "manifest.rows 一律比实际数据行数多 1 (统计口径含表头行), 系统一致, 非缺陷"})
                    else:
                        res["issues"].append({"level": "warning", "code": "manifest_rows_mismatch",
                                              "detail": f"manifest 声明行数与实际不符 {len(mismatch)}/{len(checked)} 例 "
                                                        f"(差 1 可能是口径, 差更多为真实缺行): {str(mismatch[:3])[:220]}"})
    except Exception as e:
        res["issues"].append({"level": "info", "code": "header_check_failed",
                              "detail": f"{type(e).__name__}: {str(e)[:120]}"})


def scan_tabular_perfile(u, res, kind, date_cols, dataset):
    csvs = sorted(p for p in u.glob("*.csv") if p.stat().st_size > 0)
    pqs = sorted([p for p in u.iterdir() if p.suffix.lower() in (".parquet", ".pq")])
    files = pqs if kind == "parquet" else csvs
    total = 0
    cov = {c: {"min": None, "max": None, "rows_gt_20241231": 0, "null_rows": 0} for c in date_cols}
    key = pick_key(set(res.get("schema", {}).keys()), dataset)
    seen = {}
    dup_rows = 0
    n_read = 0
    samples = []
    lim = len(files)
    for p in files:
        try:
            df = pl.read_csv(p, infer_schema=False, encoding="utf8-lossy", truncate_ragged_lines=True) \
                if kind == "csv" else pl.read_parquet(p)
        except Exception as e:
            res["issues"].append({"level": "warning", "code": "file_read_error",
                                  "detail": f"{p.name}: {type(e).__name__} {str(e)[:120]}"})
            continue
        total += df.height
        n_read += 1
        for c in date_cols:
            if c not in df.columns:
                continue
            d = df.select(pl.col(c).cast(pl.Utf8).str.replace_all("-", "").str.slice(0, 8).alias("_d"))["_d"]
            cell = cov[c]
            vals = [x for x in (d.min(), cell["min"]) if x is not None]
            cell["min"] = min(vals) if vals else None
            vals = [x for x in (d.max(), cell["max"]) if x is not None]
            cell["max"] = max(vals) if vals else None
            cell["rows_gt_20241231"] += int((d > FROZEN).sum())
            cell["null_rows"] += int(d.is_null().sum())
        if key and all(k in df.columns for k in key):
            for k in df.select(key).iter_rows():
                if k in seen:
                    dup_rows += 1
                else:
                    seen[k] = 1
        if len(samples) < 5:
            samples += [{k: (str(v)[:48] if v is not None else None) for k, v in zip(df.columns[:24], row)}
                        for row in df.head(5 - len(samples)).iter_rows()]
        if n_read >= lim and len(seen) > 4_000_000:
            break
    res["rows_total"] = total
    res["rows_counted_files"] = n_read
    res["date_coverage"] = cov
    res["frozen_rows_gt_20241231_maxcol"] = max([v["rows_gt_20241231"] for v in cov.values()] or [0])
    if res["frozen_rows_gt_20241231_maxcol"]:
        worst = max(cov.items(), key=lambda kv: kv[1]["rows_gt_20241231"])
        res["issues"].append({"level": "blocker", "code": "frozen_window_rows",
                              "detail": f"日期列 {worst[0]} 有 {worst[1]['rows_gt_20241231']} 行 > 2024-12-31"})
    res["primary_key"] = key
    res["duplicate_rows"] = dup_rows if key else None
    if dup_rows:
        res["issues"].append({"level": "warning", "code": "duplicate_primary_key_rows",
                              "detail": f"主键 {key} 重复 {dup_rows} 行"})
    res["sample_rows"] = samples
    res["status"] = "completed(per-file fallback)"
    return res


# ---------------- 针对性核验 ----------------
BAOSTOCK_600519 = RAW / "baostock" / "daily" / "sh.600519.csv"


def _bs600519():
    if not BAOSTOCK_600519.exists():
        return None
    df = pl.read_csv(BAOSTOCK_600519, infer_schema=False)
    df = df.select(
        pl.col("date").str.replace_all("-", "").alias("trade_date"),
        pl.col("close").cast(pl.Float64).alias("bs_close"),
        pl.col("volume").cast(pl.Float64).alias("bs_volume"),
        pl.col("amount").cast(pl.Float64).alias("bs_amount"),
    )
    return df


def targeted_checks(u, dataset, lf, res, kind):
    uc = {}
    cols = set(lf.collect_schema().names())
    try:
        if dataset == "adj_factor" and "adj_factor" in cols and "ts_code" in cols:
            sub = (lf.filter(pl.col("ts_code") == "600519.SH")
                   .select("trade_date", "adj_factor")
                   .sort("trade_date").collect(engine="streaming"))
            uc["600519.SH"] = {
                "n_rows": sub.height,
                "first": sub.row(0) if sub.height else None,
                "last3": sub.tail(3).rows(),
                "known_reference": "adj_factor 应随分红送转单调不减; 绝对基准随供应商/基准日不同而不同",
            }
            d = (lf.sort(["ts_code", "trade_date"])
                 .with_columns(pl.col("adj_factor").cast(pl.Float64, strict=False).diff().over("ts_code").alias("_d"))
                 .select((pl.col("_d") < -1e-9).sum().alias("dec")))
            uc["monotonic_decrease_rows"] = int(d.collect(engine="streaming").row(0)[0])
            if uc["monotonic_decrease_rows"]:
                top = (lf.sort(["ts_code", "trade_date"])
                       .with_columns([
                           pl.col("adj_factor").cast(pl.Float64, strict=False).diff().over("ts_code").alias("_d"),
                           pl.col("adj_factor").cast(pl.Float64, strict=False).shift(1).over("ts_code").alias("prev_af"),
                       ])
                       .filter(pl.col("_d") < -1e-9)
                       .select("ts_code", "trade_date", "_d", "prev_af",
                               pl.col("adj_factor").cast(pl.Float64, strict=False).alias("af"))
                       .sort("_d").limit(5).collect(engine="streaming"))
                uc["largest_decreases"] = [
                    {"ts_code": r[0], "trade_date": r[1], "drop": r2(r[2], 4), "from": r2(r[3], 4), "to": r2(r[4], 4)}
                    for r in top.iter_rows()]
                res["issues"].append({"level": "warning", "code": "adj_factor_decrease",
                                      "detail": f"{uc['monotonic_decrease_rows']} 个 (股票内) 复权因子下降点; "
                                                f"最大下降例: {uc['largest_decreases'][:3]} "
                                                "(降至 1.0 多为借壳/重整因子重置; 反复振荡需人工复核)"})
        elif dataset == "daily_basic":
            bs = _bs600519()
            if bs is not None and "ts_code" in cols:
                sel = ["trade_date", "close"] + [c for c in ("total_share", "total_mv") if c in cols]
                mine = (lf.filter((pl.col("ts_code") == "600519.SH"))
                        .select(sel).collect(engine="streaming"))
                j = mine.join(bs, on="trade_date", how="inner")
                if "total_share" in cols and "total_mv" in cols:
                    j = j.with_columns([
                        (pl.col("close").cast(pl.Float64, strict=False) - pl.col("bs_close")).abs().alias("close_diff"),
                        (pl.col("total_mv").cast(pl.Float64, strict=False) * 10000 /
                         (pl.col("close").cast(pl.Float64, strict=False) * pl.col("total_share").cast(pl.Float64, strict=False) * 10000)
                         ).alias("mv_ratio"),
                    ])
                    med_mv = j.select(pl.col("mv_ratio").median()).row(0)[0]
                else:
                    j = j.with_columns([
                        (pl.col("close").cast(pl.Float64, strict=False) - pl.col("bs_close")).abs().alias("close_diff"),
                    ])
                    med_mv = None
                if j.height:
                    last = j.sort("trade_date").tail(1).row(0, named=True)
                    med_close_diff = j.select(pl.col("close_diff").median()).row(0)[0]
                    uc["600519_cross_check_vs_baostock"] = {
                        "joined_days": j.height,
                        "last_row": {k: r2(last.get(k)) for k in ("trade_date", "close", "bs_close", "close_diff")},
                        "median_close_diff_vs_baostock": r2(med_close_diff),
                        "median_total_mv_x1e4_over_close_x_total_share": r2(med_mv, 6),
                    }
                    close_ok = med_close_diff is not None and med_close_diff < 0.01
                    mv_ok = med_mv is not None and 0.98 < med_mv < 1.02
                    uc["unit_conclusion"] = {
                        "close": "元, 与 baostock 不复权收盘一致" if close_ok else "与 baostock 收盘不一致, 存疑",
                        "total_mv": "万元 (total_mv*1e4 ≈ close*total_share)" if mv_ok else "total_mv 单位关系不成立, 存疑",
                        "confidence": "high" if (close_ok and (mv_ok or med_mv is None)) else "medium",
                    }
                    res["unit_check_conclusion"] = uc["unit_conclusion"]
        elif dataset == "stk_limit":
            bs = _bs600519()
            if bs is not None and "ts_code" in cols and "up_limit" in cols:
                prev = bs.select(["trade_date", "bs_close"]).with_columns(
                    pl.col("bs_close").shift(1).alias("prev_close")).drop_nulls()
                mine = (lf.filter(pl.col("ts_code") == "600519.SH")
                        .select("trade_date", "up_limit", "down_limit").collect(engine="streaming"))
                j = (mine.join(prev, on="trade_date", how="inner")
                     .with_columns([
                         (pl.col("up_limit").cast(pl.Float64, strict=False) /
                          (pl.col("prev_close") * 1.1) - 1).alias("up_dev"),
                         (pl.col("down_limit").cast(pl.Float64, strict=False) /
                          (pl.col("prev_close") * 0.9) - 1).alias("dn_dev"),
                     ]))
                if j.height:
                    up = j.select(pl.col("up_dev").abs().median()).row(0)[0]
                    dn = j.select(pl.col("dn_dev").abs().median()).row(0)[0]
                    uc["600519_limit_vs_prevclose_x10pct"] = {
                        "joined_days": j.height, "median_abs_up_dev": r2(up, 6), "median_abs_dn_dev": r2(dn, 6),
                    }
                    ok = up is not None and dn is not None and up < 0.005 and dn < 0.005
                    uc["unit_conclusion"] = {"limit_price": "元(与昨日收盘±10%一致)" if ok else "存疑",
                                             "confidence": "high" if ok else "low"}
                    res["unit_check_conclusion"] = uc["unit_conclusion"]
        elif dataset == "trade_cal" and "is_open" in cols:
            st = (lf.select(pl.col("is_open").cast(pl.Utf8).is_in(["0", "1"]).all().alias("ok"),
                            pl.len().alias("n"))
                  .collect(engine="streaming").row(0, named=True))
            uc["is_open_in_0_1"] = bool(st["ok"])
            uc["n_rows"] = int(st["n"])
            cov = res.get("date_coverage", {})
            if "cal_date" in cov:
                uc["calendar_range"] = [cov["cal_date"]["min"], cov["cal_date"]["max"]]
        # 通用: close 价格量级抽查
        close_col = next((c for c in ("close", "close_price", "收盘价") if c in cols), None)
        if close_col and "ts_code" in cols:
            sub = (lf.filter(pl.col("ts_code").is_in(["600519.SH", "000001.SZ"]))
                   .select("ts_code", close_col).collect(engine="streaming"))
            if sub.height:
                g = (sub.with_columns(pl.col(close_col).cast(pl.Float64, strict=False).alias("_c"))
                     .group_by("ts_code").agg(pl.col("_c").min().alias("min"), pl.col("_c").max().alias("max"),
                                              pl.col("_c").median().alias("med")))
                uc["close_magnitude"] = {row[0]: {"min": r2(row[1]), "median": r2(row[2]), "max": r2(row[3])}
                                         for row in g.rows()}
                ref = uc["close_magnitude"].get("600519.SH")
                if ref:
                    verdict = "合理(数百~数千元)" if 50 <= (ref["median"] or 0) <= 5000 else "量级可疑"
                    uc["close_magnitude"]["600519_verdict"] = verdict
                    if verdict != "合理(数百~数千元)":
                        res["issues"].append({"level": "warning", "code": "price_magnitude_suspect",
                                              "detail": f"600519 close 中位数 {ref['median']} 量级可疑"})
        res["unit_check"] = {k: v for k, v in uc.items()}
    except Exception as e:
        res["unit_check"] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
        res["issues"].append({"level": "info", "code": "targeted_check_failed",
                              "detail": f"{type(e).__name__}: {str(e)[:160]}"})


# ---------------- 其他模式 ----------------
def sha256_small(p: Path):
    h = hashlib.sha256()
    with p.open("rb") as f:
        h.update(f.read())
    return h.hexdigest()


def scan_json_unit(u: Path):
    rel = u.relative_to(RAW).as_posix()
    files = sorted(p for p in u.iterdir() if p.is_file())
    res = {"batch_dir": rel, "mode": "json", "status": "completed", "issues": []}
    inv = INV.get(rel)
    if inv:
        res["inventory_registration"] = {"files": inv["files"], "bytes": inv["bytes"]}
        if inv["files"] != len(files):
            res["issues"].append({"level": "warning", "code": "inventory_file_count_mismatch",
                                  "detail": f"登记 {inv['files']}, 实际 {len(files)}"})
    meta = {}
    metap = u / "meta.json"
    if metap.exists():
        meta = json.loads(metap.read_text(encoding="utf-8"))
    else:
        res["issues"].append({"level": "blocker", "code": "manifest_missing", "detail": "缺 meta.json"})
    resp_files = [p for p in files if p.name.startswith("response")]
    res["files"] = {"n_total": len(files), "response_pages": [p.name for p in resp_files],
                    "total_bytes": sum(p.stat().st_size for p in files)}
    # sha256: 尝试两种方案(逐页 / 分页顺序拼接); 都不符则记 info(方案可能基于原始响应流)
    expect = meta.get("sha256")
    sha_page_ok, sha_concat_ok = 0, None
    if expect and resp_files:
        hcat = hashlib.sha256()
        order = meta.get("pages") or [p.name for p in resp_files]
        for name in order:
            fp = u / name
            if not fp.exists():
                res["issues"].append({"level": "warning", "code": "meta_page_file_missing", "detail": name})
                continue
            hcat.update(fp.read_bytes())
            if sha256_small(fp) == expect:
                sha_page_ok += 1
        sha_concat_ok = hcat.hexdigest() == expect
        if sha_page_ok == 0 and not sha_concat_ok:
            res["issues"].append({"level": "info", "code": "sha256_scheme_unreproduced",
                                  "detail": "meta.sha256 无法用逐页或分页拼接复现(可能基于未拆分原始响应), 身份未独立验证"})
    total_rows = 0
    dates = []
    closes = []
    samples = []
    struct_note = None
    for p in resp_files:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            res["issues"].append({"level": "warning", "code": "json_parse_error", "detail": f"{p.name}: {e}"})
            continue
        recs = None
        if isinstance(obj, dict):
            data = obj.get("data")
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, dict) and isinstance(v.get("qfqday"), list):
                        recs = v["qfqday"]
                        break
                    if isinstance(v, dict) and isinstance(v.get("day"), list):
                        recs = v["day"]
                        break
                    if isinstance(v, dict) and isinstance(v.get("item"), list):
                        recs = v["item"]
                        break
                    if isinstance(v, list) and v and isinstance(v[0], (list, dict)):
                        recs = v
                        break
                if recs is None and isinstance(data, list):
                    recs = data
            elif isinstance(data, list):
                recs = data
        if recs is None:
            res["issues"].append({"level": "warning", "code": "response_structure_unknown",
                                  "detail": f"{p.name} 未识别到记录列表"})
            continue
        total_rows += len(recs)
        for r in (recs[:200000] if len(recs) <= 200000 else recs[:200000]):
            if isinstance(r, list):
                d = str(r[0])[:10].replace("-", "")
                dates.append(d)
                if len(samples) < 4:
                    samples.append({"date": r[0], "ohlc": r[1:5], "volume": r[5] if len(r) > 5 else None})
                try:
                    closes.append(float(r[2]))
                except Exception:
                    pass
            elif isinstance(r, dict):
                if "date_ms" in r:
                    d = datetime.fromtimestamp(r["date_ms"] / 1000).strftime("%Y%m%d")
                    dates.append(d)
                    if len(samples) < 4:
                        samples.append({"date": d, "close": r.get("close_price"), "volume": r.get("volume")})
                    closes.append(r.get("close_price") or 0)
                else:
                    if len(samples) < 4:
                        samples.append({k: str(v)[:30] for k, v in list(r.items())[:8]})
                    for dk in ("REPORT_DATE", "NOTICE_DATE", "UPDATE_DATE", "ann_date", "end_date"):
                        if r.get(dk):
                            dates.append(str(r[dk])[:10].replace("-", ""))
                            break
    if struct_note:
        res["issues"].append({"level": "info", "code": "structure_note", "detail": struct_note})
    if meta.get("n_rows") is not None and total_rows:
        uniq_dates = len(set(d for d in dates if d))
        dup_dates = total_rows - uniq_dates if dates else 0
        if meta["n_rows"] != total_rows:
            res["issues"].append({"level": "warning", "code": "meta_row_count_mismatch",
                                  "detail": f"meta n_rows={meta['n_rows']}, 实际解析 {total_rows} 行"
                                            + (f", 其中跨页重复日期 {dup_dates} 行" if dup_dates else "")})
        if dup_dates:
            seen = {}
            for d in dates:
                seen[d] = seen.get(d, 0) + 1
            ex = sorted([k for k, v in seen.items() if v > 1])[:6]
            res["duplicate_date_rows"] = dup_dates
            res["issues"].append({"level": "warning", "code": "duplicate_kline_dates_across_pages",
                                  "detail": f"跨页重复日期 {dup_dates} 行, 例: {ex}"})
    pages = meta.get("pages")
    if pages is not None and [p.name for p in resp_files] != pages:
        res["issues"].append({"level": "warning", "code": "meta_page_list_mismatch",
                              "detail": "meta.pages 与实际 response 文件不一致"})
    dates = sorted(d for d in dates if d and len(d) == 8 and d.isdigit())
    frozen = sum(1 for d in dates if d > FROZEN)
    res["rows_total"] = total_rows
    res["date_coverage"] = {"record_date": {"min": dates[0] if dates else None,
                                            "max": dates[-1] if dates else None,
                                            "rows_gt_20241231": frozen}}
    if frozen:
        res["issues"].append({"level": "blocker", "code": "frozen_window_rows",
                              "detail": f"{frozen} 个记录日期 > 2024-12-31 (max={dates[-1] if dates else None}); 冻结边界: 只报告"})
    if closes:
        med = sorted(closes)[len(closes) // 2]
        res["numeric_magnitude"] = {"close": {"min": r2(min(closes)), "median": r2(med), "max": r2(max(closes))}}
        sym = meta.get("symbol", "")
        if sym == "sh510300":
            ok = 2 <= med <= 8
            res["unit_check_conclusion"] = {
                "close_510300": f"中位 {r2(med)} 元, {'符合沪深300ETF量级(2-8元)' if ok else '量级可疑'}",
                "confidence": "high" if ok else "low"}
            res["unit_check"] = res["unit_check_conclusion"]
    res["sample_rows"] = samples[:4]
    res["sha256_verified_pages"] = sha_page_ok if expect else None
    res["sha256_concat_ok"] = sha_concat_ok if expect else None
    return res


def scan_zip_unit(u: Path):
    rel = u.relative_to(RAW).as_posix()
    res = {"batch_dir": rel, "mode": "zip", "status": "completed", "issues": [], "zips": []}
    inv = INV.get(rel)
    if inv and inv["files"] != len(list(u.rglob('*'))):
        res["issues"].append({"level": "info", "code": "inventory_count_note",
                              "detail": f"登记 {inv['files']} 个顶层条目(目录层)"})
    for z in sorted(u.glob("*.zip")):
        info = {"zip": z.name, "bytes": z.stat().st_size, "adjust": z.stem}
        try:
            with zipfile.ZipFile(z) as zf:
                names = zf.namelist()
                csvs = [n for n in names if n.lower().endswith(".csv")]
                info["members"] = len(names)
                info["csv_members"] = len(csvs)
                info["uncompressed_bytes"] = sum(i.file_size for i in zf.infolist())
                # 抽一个成员看头两行
                if csvs:
                    with zf.open(csvs[0]) as f:
                        head = f.read(1200).decode("utf-8", errors="replace").splitlines()[:2]
                    info["sample_member"] = csvs[0]
                    info["sample_head"] = head
                    # 抽 600519 成员(如有)
                    tgt = [n for n in csvs if "600519" in n]
                    if tgt:
                        with zf.open(tgt[0]) as f:
                            h2 = f.read(2000).decode("utf-8", errors="replace").splitlines()
                        info["sh600519_member"] = tgt[0]
                        info["sh600519_head"] = h2[:2]
                        info["sh600519_tail_note"] = "仅抽样头部, 未全量读取"
        except Exception as e:
            res["issues"].append({"level": "warning", "code": "zip_read_error", "detail": f"{z.name}: {e}"})
        res["zips"].append(info)
    res["files"] = {"n_total": len(list(u.rglob('*')))}
    return res


def scan_bigquant_year(u: Path, mode: str):
    rel = u.relative_to(RAW).as_posix()
    res = {"batch_dir": rel, "mode": mode, "status": "completed", "issues": []}
    files = sorted(p for p in u.iterdir() if p.is_file())
    res["files"] = {"n_total": len(files), "total_bytes": sum(p.stat().st_size for p in files)}
    inv = INV.get(rel)
    if inv:
        res["inventory_registration"] = {"files": inv["files"], "bytes": inv["bytes"]}
        if inv["files"] != len(files):
            res["issues"].append({"level": "warning", "code": "inventory_file_count_mismatch",
                                  "detail": f"登记 {inv['files']}, 实际 {len(files)}"})
    year = u.name
    if mode == "frozen-name-only":
        bym = {}
        for p in files:
            d = p.stem
            bym.setdefault("daily_file_dates", []).append(d)
        ds = sorted(bym["daily_file_dates"])
        frozen_files = [d for d in ds if d > FROZEN]
        res["date_coverage"] = {"file_date": {"min": ds[0] if ds else None, "max": ds[-1] if ds else None,
                                              "rows_gt_20241231": None,
                                              "frozen_files_gt_20241231": len(frozen_files)}}
        res["issues"].append({"level": "blocker", "code": "frozen_window_data_present",
                              "detail": f"{year} 年目录全部 {len(files)} 个文件属于冻结区(2025/2026), 按文件名登记未读取内容"})
        # 抽 1 个文件读 schema+1 行供 schema 记录(内容仍为冻结区, 只记录)
        if files:
            sch = pl.read_parquet_schema(files[0])
            res["schema"] = {c: str(t) for c, t in sch.items()}
            df = pl.read_parquet(files[0], n_rows=2)
            res["sample_rows"] = [{k: str(v)[:30] for k, v in zip(df.columns, row)} for row in df.iter_rows()]
            res["rows_note"] = "未统计行数(冻结区, 仅登记)"
        return res
    if mode == "parquet-meta":
        total = 0
        ds = []
        for p in files:
            n = pl.scan_parquet(p).select(pl.len()).collect().item()
            total += n
            ds.append(p.stem)
        ds = sorted(ds)
        res["rows_total"] = total
        res["date_coverage"] = {"file_date": {"min": ds[0], "max": ds[-1], "rows_gt_20241231": 0}}
        sch = pl.read_parquet_schema(files[0])
        res["schema"] = {c: str(t) for c, t in sch.items()}
        df = pl.read_parquet(files[0], n_rows=3)
        res["sample_rows"] = [{k: str(v)[:30] for k, v in zip(df.columns, row)} for row in df.iter_rows()]
        res["rows_note"] = "行数来自 parquet 元数据; 未逐行读取内容"
        return res
    # sampled-csv
    sample = files[:3] + files[len(files) // 2:len(files) // 2 + 3]
    total_rows_sampled = 0
    schemas = []
    samples = []
    dmin, dmax = None, None
    closes = []
    vols = []
    for p in sample:
        df = pl.read_csv(p, infer_schema_length=2000, encoding="utf8-lossy", truncate_ragged_lines=True, n_rows=200000)
        total_rows_sampled += df.height
        schemas.append({c: str(t) for c, t in df.schema.items()})
        if len(samples) < 3:
            samples += [{k: str(v)[:28] for k, v in zip(df.columns, row)} for row in df.head(3).iter_rows()]
        tcol = next((c for c in ("datetime", "time", "date", "trade_time", "时间") if c in df.columns), None)
        if tcol:
            d = df.select(pl.col(tcol).cast(pl.Utf8).str.slice(0, 10).str.replace_all("-", "").alias("_d"))["_d"]
            dmin = min(x for x in (d.min(), dmin) if x) if (d.min() or dmin) else dmin
            dmax = max(x for x in (d.max(), dmax) if x) if (d.max() or dmax) else dmax
            frozen_in_file = int((d > FROZEN).sum())
            if frozen_in_file:
                res.setdefault("frozen_sample_rows", 0)
                res["frozen_sample_rows"] += frozen_in_file
        for c in ("close", "close_price", "收盘价"):
            if c in df.columns:
                closes += [x for x in df[c].cast(pl.Float64, strict=False).drop_nulls().head(5000).to_list()]
        for c in ("volume", "vol", "成交量"):
            if c in df.columns:
                vols += [x for x in df[c].cast(pl.Float64, strict=False).drop_nulls().head(5000).to_list()]
    res["rows_sampled"] = total_rows_sampled
    res["sampled_files"] = [p.name for p in sample]
    res["schema"] = schemas[0]
    res["schema_consistent_across_samples"] = all(s == schemas[0] for s in schemas)
    res["date_coverage"] = {"sampled_file_date": {"min": dmin, "max": dmax, "rows_gt_20241231": res.get("frozen_sample_rows", 0),
                                                  "note": "仅抽样文件的日期范围, 非全量"}}
    if res.get("frozen_sample_rows"):
        res["issues"].append({"level": "warning", "code": "frozen_window_rows_in_sample",
                              "detail": f"抽样中出现 {res['frozen_sample_rows']} 行 > 2024-12-31 (仅抽样)"})
    if closes:
        res["numeric_magnitude"] = {"close_sample": {"min": r2(min(closes)), "max": r2(max(closes))}}
    res["sample_rows"] = samples
    res["status"] = f"completed(sampled {len(sample)}/{len(files)} files)"
    return res


def scan_inventory_only(u: Path):
    """user_minute_1m 顶层清点"""
    rel = u.relative_to(RAW).as_posix()
    res = {"batch_dir": rel, "mode": "inventory-only", "status": "completed",
           "issues": [], "year_dirs": {}}
    files = sorted(p for p in u.iterdir() if p.is_file())
    subdirs = sorted(p for p in u.iterdir() if p.is_dir())
    res["top_files"] = [p.name for p in files]
    n, byts = 0, 0
    for sd in subdirs:
        cnt, b = 0, 0
        for p in sd.rglob("*"):
            if p.is_file():
                cnt += 1
                b += p.stat().st_size
        res["year_dirs"][sd.name] = {"files": cnt, "bytes": b}
        n += cnt
        byts += b
    res["files"] = {"n_total": n + len(files), "data_files_in_year_dirs": n, "total_bytes": byts}
    inv = INV.get(rel)
    if inv:
        res["inventory_registration"] = {"files": inv["files"], "bytes": inv["bytes"]}
        if inv["files"] != len(files) + n:
            res["issues"].append({"level": "info", "code": "inventory_count_granularity_note",
                                  "detail": f"登记 {inv['files']} 个顶层条目; 年度子目录实际含 {n} 个数据文件 + "
                                            f"{len(files)} 个顶层文件(登记时点可能仅含清单文件)"})
    mf = u / "transfer-manifest.json"
    if not mf.exists() and (u.parent / "transfer-manifest.json").exists():
        mf = u.parent / "transfer-manifest.json"
    if mf.exists():
        try:
            res["transfer_manifest_summary"] = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(res["transfer_manifest_summary"], dict):
                res["transfer_manifest_summary"] = {k: (v if not isinstance(v, (list, dict)) else f"<{type(v).__name__} len={len(v)}>") for k, v in list(res["transfer_manifest_summary"].items())[:20]}
        except Exception as e:
            res["issues"].append({"level": "warning", "code": "manifest_unreadable", "detail": str(e)[:120]})
    else:
        res["issues"].append({"level": "warning", "code": "manifest_missing", "detail": "无 transfer-manifest.json"})
    res["note"] = "按任务要求仅顶层清点, 未读取数据文件内容"
    return res


def root_files_note(src: Path):
    fs = [p.name for p in src.iterdir() if p.is_file()]
    return fs


# ---------------- 报告落盘 ----------------
def write_report(source, dataset, payload):
    d = OUT / source
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{dataset}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=jdefault), encoding="utf-8")
    return p


# ---------------- 主流程 ----------------
def main():
    t0 = time.time()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    units = list_units()
    done = done_units()
    log(f"共 {len(units)} 个扫描单元, 已完成 {len(done)}")
    aborted = False
    remaining = []
    for i, u in enumerate(units):
        rel = u.relative_to(RAW).as_posix()
        if rel in done:
            continue
        if time.time() > DEADLINE:
            aborted = True
            remaining.append(rel)
            continue
        mode = mode_of(u)
        source = rel.split("/")[0]
        dataset = dataset_of(u)
        ts = time.time()
        log(f"[{i + 1}/{len(units)}] {rel} mode={mode}")
        try:
            if mode == "full":
                r = scan_tabular(u, mode)
            elif mode == "json":
                r = scan_json_unit(u)
            elif mode == "zip":
                r = scan_zip_unit(u)
            elif mode in ("parquet-meta", "sampled-csv", "frozen-name-only"):
                r = scan_bigquant_year(u, mode)
            elif mode == "inventory-only":
                r = scan_inventory_only(u)
            else:
                r = {"status": "unknown_mode", "issues": []}
        except Exception as e:
            r = {"batch_dir": rel, "mode": mode, "status": "failed",
                 "error": f"{type(e).__name__}: {str(e)[:300]}",
                 "trace": traceback.format_exc()[-800:], "issues": []}
            progress(rel, "failed", {"error": str(e)[:200]})
        dur = round(time.time() - ts, 1)
        r["duration_s"] = dur
        r["finished_at"] = now_s()
        # 聚合到 dataset 报告
        rp = OUT / source / f"{dataset}.json"
        payload = {"source": source, "dataset": dataset, "batches": {}, "updated_at": now_s()}
        if rp.exists():
            try:
                payload = json.loads(rp.read_text(encoding="utf-8"))
            except Exception:
                pass
        payload.setdefault("batches", {})[r.get("batch_dir", u.name)] = r
        payload["updated_at"] = now_s()
        write_report(source, dataset, payload)
        progress(rel, "done" if r.get("status") not in ("failed",) else "failed",
                 {"duration_s": dur, "status": r.get("status")})
    # 源根目录散文件记录
    notes = {s: root_files_note(RAW / s) for s in SOURCES if (RAW / s).exists()}
    (RUN_DIR / "source_root_files.json").write_text(
        json.dumps(notes, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"扫描循环结束: aborted={aborted}, 剩余 {len(remaining)}")
    with (RUN_DIR / "remaining.json").open("w", encoding="utf-8") as f:
        json.dump(remaining, f, ensure_ascii=False, indent=1)
    print("FINAL_STATUS", "aborted-timeout" if aborted else "all-units-processed")
    print(f"ELAPSED {round(time.time() - t0, 1)}s")


if __name__ == "__main__":
    main()
