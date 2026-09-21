# -*- coding: utf-8 -*-
"""Cross-source close check: baostock ETF batch vs tushare fund_daily 20260917-r1.

同目标跨源复核 (供应商不同、目标行情相同) - 不构成独立验证。
Output: crosscheck_close.json in run dir.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO = Path(r"D:\量化")
RUN_DIR = REPO / "artifacts" / "runs" / "20260919T021519-etf-pull-74d0"
BATCH_DIR = REPO / "data" / "raw" / "baostock" / "etf-daily-20260919-r1"
TUSHARE = REPO / "data" / "raw" / "tushare" / "fund_daily" / "20260917-r1"

TOL = 0.005  # tushare close 3-4位小数 vs baostock 4位小数的舍入容差

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def to_ts_code(bs_code: str) -> str:
    exch, num = bs_code.split(".")
    return f"{num}.{'SH' if exch.lower() == 'sh' else 'SZ'}"


def percentile(sorted_vals: list[float], q: float) -> float | None:
    if not sorted_vals:
        return None
    k = min(len(sorted_vals) - 1, max(0, round(q * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def main() -> None:
    per_code = {}
    diffs = []          # |diff| of all comparable pairs
    nonzero = []        # |diff| > 0
    n_pairs = n_exact = n_tol = n_mismatch = 0
    n_bs_only_dates = n_ts_only_dates = 0
    worst = []
    codes_with_rows = 0

    for csv_path in sorted(BATCH_DIR.glob("*.csv")):
        if csv_path.name == "pool_type5.csv":
            continue
        bs_code = csv_path.stem
        ts_code = to_ts_code(bs_code)
        chunk = TUSHARE / f"chunk_{ts_code}.csv"
        if not chunk.exists():
            continue

        with open(csv_path, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            bs_rows = [(r["date"], r["close"]) for r in rd]
        if not bs_rows:
            per_code[ts_code] = {"bs_rows": 0, "pairs": 0}
            continue
        codes_with_rows += 1
        bs_map = dict(bs_rows)

        with open(chunk, encoding="utf-8", newline="") as f:
            rd = csv.DictReader(f)
            ts_map = {
                f"{r['trade_date'][:4]}-{r['trade_date'][4:6]}-{r['trade_date'][6:]}": r["close"]
                for r in rd
            }

        common = set(bs_map) & set(ts_map)
        n_bs_only_dates += len(set(bs_map) - set(ts_map))
        n_ts_only_dates += len(set(ts_map) - set(bs_map))
        code_diffs = []
        code_mismatch = 0
        for d in sorted(common):
            b, t = bs_map[d], ts_map[d]
            if b == "" or t == "":
                continue
            diff = abs(float(b) - float(t))
            n_pairs += 1
            diffs.append(diff)
            code_diffs.append(diff)
            if diff == 0.0:
                n_exact += 1
            elif diff <= TOL:
                n_tol += 1
            else:
                n_mismatch += 1
                code_mismatch += 1
                worst.append((diff, ts_code, d, b, t))
        nonzero.extend(x for x in code_diffs if x > 0)
        per_code[ts_code] = {
            "bs_rows": len(bs_map),
            "ts_rows": len(ts_map),
            "pairs": len(common),
            "mismatches_gt_tol": code_mismatch,
            "max_abs_diff": max(code_diffs) if code_diffs else 0.0,
        }

    diffs.sort()
    nonzero.sort()
    worst.sort(reverse=True)
    out = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "declaration": "同目标跨源复核 (baostock vs tushare, 两供应商同一目标行情); 不构成独立验证",
        "tolerance": TOL,
        "codes_compared": codes_with_rows,
        "pairs_compared": n_pairs,
        "exact_match": n_exact,
        "within_tol": n_tol,
        "mismatch_gt_tol": n_mismatch,
        "exact_rate": round(n_exact / n_pairs, 6) if n_pairs else None,
        "within_tol_rate": round((n_exact + n_tol) / n_pairs, 6) if n_pairs else None,
        "abs_diff_all": {
            "p50": percentile(diffs, 0.5),
            "p90": percentile(diffs, 0.9),
            "p99": percentile(diffs, 0.99),
            "max": diffs[-1] if diffs else None,
        },
        "abs_diff_nonzero": {
            "n": len(nonzero),
            "p50": percentile(nonzero, 0.5),
            "p90": percentile(nonzero, 0.9),
            "max": nonzero[-1] if nonzero else None,
        },
        "date_coverage": {
            "baostock_dates_missing_in_tushare": n_bs_only_dates,
            "tushare_dates_missing_in_baostock": n_ts_only_dates,
        },
        "worst_examples": [
            {"abs_diff": round(d, 6), "ts_code": c, "date": dt,
             "baostock_close": b, "tushare_close": t}
            for d, c, dt, b, t in worst[:5]
        ],
        "per_code": per_code,
    }
    (RUN_DIR / "crosscheck_close.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    summary = {k: v for k, v in out.items() if k != "per_code"}
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
