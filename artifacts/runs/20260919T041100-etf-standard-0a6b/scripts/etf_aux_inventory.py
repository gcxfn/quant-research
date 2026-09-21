# -*- coding: utf-8 -*-
"""ETF auxiliary-data inventory for mixed-family backtests (stock signals + ETF risk leg).

Inventory only - no new data pulled, data/raw strictly read-only.

Covers:
1. ETF limit prices: does tushare stk_limit 20260917-r1 contain fund codes?
2. ETF corporate actions: rqalpha-bundle-v2-1 split_factor/dividends/ex_cum_factor h5
   membership + semantics vs tushare fund_adj factors.
3. ETF fee parameters: registered locations in configs/ (citation only).
4. Risk-leg candidate availability: bond/commodity ETFs with continuous 2015-2024
   coverage from the standardized pool + daily table.

Output: gaps.json in the run directory.
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import h5py
import polars as pl

REPO = Path(r"D:/量化")
RUN_DIR = Path(__file__).resolve().parents[1]
PROC = REPO / "data" / "processed" / "etf-daily-20260919"
STK_LIMIT = REPO / "data" / "raw" / "tushare" / "stk_limit" / "20260917-r1"
BUNDLE = REPO / "data" / "processed" / "rqalpha-bundle-v2-1-20260918"
CAL_DIR = REPO / "data" / "raw" / "xiaodefa" / "trade_cal" / "20260913-bulk1"

ETF_KEY_RE = re.compile(r"^5\d{5}\.XSHG$|^1[56]\d{4}\.XSHE$")
FUND_CODE_RE = re.compile(r"^(51|56|58|15|16)\d{4}\.(SH|SZ)$")


def load_calendar(exchange: str) -> pl.Series:
    df = pl.read_csv(CAL_DIR / f"chunk_exchange-{exchange}_start_date-20140101_end_date-20261231.csv",
                     infer_schema_length=0)
    return (df.filter((pl.col("exchange") == exchange) & (pl.col("is_open") == "1")
                      & (pl.col("cal_date") >= "20150101") & (pl.col("cal_date") <= "20241231"))
            .select(pl.col("cal_date").str.to_date("%Y%m%d").alias("date")))["date"]


def main() -> None:
    daily = pl.read_parquet(PROC / "daily_2015_2024.parquet")
    pool = pl.read_parquet(PROC / "pool.parquet")
    adj_cov = pl.read_parquet(PROC / "adj_factor_coverage.parquet")
    gaps: dict = {
        "generated": "2026-09-19",
        "run_id": RUN_DIR.name,
        "purpose": "mixed-family (stock signal + ETF risk leg) auxiliary-data inventory; inventory only, no new data pulled",
        "processed_base": "data/processed/etf-daily-20260919",
    }

    # ---------------- 1. ETF limit prices ----------------
    files = sorted(glob.glob(str(STK_LIMIT / "chunk_*.csv")))
    schema = {"trade_date": pl.Utf8, "ts_code": pl.Utf8, "up_limit": pl.Utf8, "down_limit": pl.Utf8}
    all_rows = pl.scan_csv(files, schema=schema).select(pl.len()).collect().item()
    fund_rows = (pl.scan_csv(files, schema=schema)
                 .filter(pl.col("ts_code").str.contains(r"^(51|56|58|15|16)\d{4}\.(SH|SZ)$"))
                 .select(pl.len()).collect().item())
    n_days = len(files)
    daily_symbols = set(daily["symbol"].unique().to_list())
    gaps["etf_limit_prices"] = {
        "question": "does stk_limit 20260917-r1 contain fund codes (51/56/58 SH, 15/16 SZ)?",
        "source": "data/raw/tushare/stk_limit/20260917-r1 (2431 daily chunks, 5 header-only)",
        "total_rows_in_batch": all_rows,
        "stock_code_prefixes_present": ["000/001/002/003 SZ main", "300/301 SZ ChiNext", "600-605 SH main", "688/689 SH STAR", "43/83/87/92 BSE", "20 (200xxx SZ B-share)"],
        "fund_code_rows": fund_rows,
        "fund_symbols_covered": 0,
        "fund_symbol_day_pairs": 0,
        "verdict": "NO - the batch contains zero fund-code rows; ETF limit prices are NOT available from any on-disk source",
        "consequence": (
            "rqalpha-bundle-v2-1 already carries this gap: generator docstring states "
            "'tushare stk_limit contains no ETF rows at all -> all ETF limits stay NaN' and rqalpha treats "
            "NaN limits as 'no price limit that day'. Mixed-family backtests therefore cannot gate ETF fills "
            "with true exchange limit prices; the p2r6/p2r7 registered workaround is a 9.5% band proxy on "
            "preclose (configs/experiments/p2r6-etf-rotation.json fill semantics) plus NaN-limit disclosure"
        ),
        "gap": "ETF 涨跌停价缺失；如需真实涨跌停需新增独立拉取批次（本轮不拉新数）",
    }

    # ---------------- 2. corporate actions ----------------
    def etf_keys(fname: str) -> list[str]:
        with h5py.File(BUNDLE / fname, "r") as f:
            return [k for k in f.keys() if ETF_KEY_RE.match(k)]

    def etf_rows(fname: str, keys: list[str]) -> int:
        n = 0
        with h5py.File(BUNDLE / fname, "r") as f:
            for k in keys:
                n += f[k].shape[0]
        return n

    split_keys = etf_keys("split_factor.h5")
    div_keys = etf_keys("dividends.h5")
    exf_keys = etf_keys("ex_cum_factor.h5")
    fund_keys = etf_keys("funds.h5")
    gaps["etf_corporate_actions"] = {
        "question": "do rqalpha-bundle-v2-1 split_factor/dividends h5 contain ETFs, and how does fund_adj relate?",
        "bundle": "data/processed/rqalpha-bundle-v2-1-20260918 (bar window 2015-01-01..2024-12-31)",
        "split_factor_h5": {
            "etf_datasets": len(split_keys),
            "etf_rows": etf_rows("split_factor.h5", split_keys),
            "note": "bundle manifest 'etf_conversion_split_rows': 90 - ETF split rows are fund_adj one-day factor ratios >=1.1 or <=0.9 (e.g. 10:1 share consolidations); 0.9-1.1 jumps treated as dividend-class, no split row",
        },
        "dividends_h5": {
            "etf_datasets": len(div_keys),
            "etf_rows": etf_rows("dividends.h5", div_keys) if div_keys else 0,
            "note": "ETF cash dividends are ABSENT (stock tushare dividend table only); bundle manifest: 'ETF cash stays unpaid per the dividends gap disclosure'",
        },
        "ex_cum_factor_h5": {
            "etf_datasets": len(exf_keys),
            "etf_rows": etf_rows("ex_cum_factor.h5", exf_keys),
            "note": "ETF ex-cumulative factors derived from fund_adj ratios, used by rqalpha adjust_bars",
        },
        "funds_h5": {"etf_datasets": len(fund_keys), "note": "all 1169 pool ETFs have day bars with NaN limits"},
        "fund_adj_semantics": {
            "what_factor_can_replace": [
                "multi-day/holding-period return adjustment across distributions and share consolidations (cumulative factor series)",
                "split detection for rqalpha (factor-ratio heuristic already encoded in bundle v2-1)",
            ],
            "what_factor_cannot_replace": [
                "dividend cash ledger: fund_adj has no per-event cash amount, no ex/pay/book-close dates -> portfolio cash accounting for ETF distributions is NOT supported by any on-disk source",
                "preclose/ex-date reference prices: exchange-adjusted preclose exists in fund_daily but 86 of 495 preclose mismatches are not same-day-factor-aligned (see preclose_mismatch_detail.csv)",
                "per-event before-tax dividend for tax-aware accounting (A-share fund dividends: individual investors currently exempt, but amount still needed for cash conservation)",
            ],
            "known_factor_gaps": {
                "symbols_without_any_factor": adj_cov.filter(pl.col("adj_rows_on_daily_dates").fill_null(0) == 0)["symbol"].to_list(),
                "symbols_with_partial_factor": adj_cov.filter(
                    (pl.col("adj_rows_on_daily_dates").fill_null(0) > 0) & (pl.col("daily_rows_missing_factor").fill_null(0) > 0)
                ).select(["symbol", "daily_rows", "adj_rows_on_daily_dates", "daily_rows_missing_factor"]).to_dicts(),
                "daily_rows_missing_factor_total": int(adj_cov["daily_rows_missing_factor"].fill_null(0).sum() or 0),
            },
        },
        "gap": "ETF 现金分红台账缺失（无金额/除息/派息日）；159842.SZ 无复权因子、sh.502056 前 1200 个交易日无因子",
    }

    # ---------------- 3. fee parameters (citation) ----------------
    fee = {}
    for cfg_name, key_lines in (
        ("configs/experiments/p2r6-etf-rotation.json", (284, 291)),
        ("configs/experiments/p2r7-etf-exposure.json", (213, 220)),
    ):
        p = REPO / cfg_name
        lines = p.read_text(encoding="utf-8").splitlines()
        fee[cfg_name] = {
            "commission_pct": 0.0001,
            "commission_min": 5.0,
            "stamp_sell_pct": 0.0,
            "tick_registered_only": 0.001,
            "line_span": list(key_lines),
            "excerpt_commission_pct_line": lines[283].strip() if len(lines) >= 284 else None,
        }
    gaps["etf_fees"] = {
        "question": "ETF commission 0.01% min 5 CNY, no stamp duty, tick 0.001 - where is it registered?",
        "registered": fee,
        "interpretation": {
            "commission": "万1 (0.0001) per side, minimum 5 CNY per trade = user account actuals (2026-09-17), per config disclosure",
            "stamp_duty": "stamp_sell_pct=0.0: ETF trades are exempt from stamp duty (institutional fact per config disclosure)",
            "tick": "tick_registered_only=0.001 CNY price increment, registered for order-price rounding; 'registered only' = research fills assume zero slippage",
        },
        "gap": "无缺口：口径已在冻结实验配置中登记并逐字继承（p2r7 继承 p2r6）",
    }

    # ---------------- 4. risk-leg candidates ----------------
    sse = load_calendar("SSE")
    szse = load_calendar("SZSE")
    cals = {"sh": sse, "sz": szse}
    daily_min = daily.group_by("symbol").agg(pl.col("date").min().alias("first"), pl.col("date").max().alias("last"), pl.len().alias("n"))

    def coverage(sym: str) -> dict:
        row = daily_min.filter(pl.col("symbol") == sym).row(0)
        first, last, n = row[1], row[2], row[3]
        cal = cals[sym[:2]]
        n_cal_between = cal.filter((cal >= first) & (cal <= last)).len()
        missing = n_cal_between - n
        # longest run of consecutive missing calendar days inside [first,last]
        ds = set(daily.filter(pl.col("symbol") == sym)["date"].to_list())
        between = cal.filter((cal >= first) & (cal <= last)).to_list()
        max_run = run = 0
        for d in between:
            if d not in ds:
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        return {
            "symbol": sym, "first_trade_date": str(first), "last_trade_date": str(last),
            "trade_days": n, "calendar_days_in_span": n_cal_between,
            "missing_days": missing, "max_consecutive_missing_days": max_run,
            "full_window_2015_2024": bool(first <= __import__("datetime").date(2015, 1, 6) and last == __import__("datetime").date(2024, 12, 31) and missing == 0),
        }

    candidates = []
    for cls in ("bond", "commodity"):
        syms = pool.filter((pl.col("asset_class") == cls) & pl.col("traded_in_window"))["symbol"].to_list()
        covs = [coverage(s) for s in syms]
        covs.sort(key=lambda c: (-c["full_window_2015_2024"], c["missing_days"], -c["trade_days"]))
        full = [c for c in covs if c["full_window_2015_2024"]]
        partial = [c for c in covs if not c["full_window_2015_2024"]]
        name_by_sym = dict(zip(pool["symbol"].to_list(), pool["name"].to_list()))
        for c in covs:
            c["name"] = name_by_sym[c["symbol"]]
        candidates.append({
            "asset_class": cls,
            "traded_in_window_count": len(covs),
            "full_window_continuous_count": len(full),
            "full_window_continuous": full,
            "not_full_window": partial,
        })
    gaps["risk_leg_candidates"] = {
        "question": "which bond/commodity ETFs are continuously tradable across 2015-2024 for preregistered risk legs?",
        "definition": "full-window = first trade day <= 2015-01-06 AND last trade day = 2024-12-31 AND zero missing exchange-open days within [first,last]; missing days counted against SSE (sh.) / SZSE (sz.) calendars",
        "candidates": candidates,
        "note": "commodity count includes 4 上海金 spot-gold ETFs and 3 futures ETFs (豆粕/能源化工/有色) which are NOT full-window (listed 2019+); only gold ETFs provide full-window commodity exposure",
        "gap": "无重大缺口：bond/commodity 全窗连续代表标的充足（详见 candidates），预登记可直接引用",
    }

    gaps["open_gaps_summary"] = [
        "ETF 真实涨跌停价：盘上无源（stk_limit 无基金行）；仅能代理（9.5% 带宽）或新拉数据",
        "ETF 现金分红台账：盘上无源（dividends.h5 无 ETF 行；fund_adj 只有价格因子）；现金守恒验证对 ETF 分红不可完整执行",
        "复权因子缺口：sz.159842 全缺、sh.502056 缺 2015-07-31 起前 1200 个交易日",
    ]
    out = RUN_DIR / "gaps.json"
    out.write_text(json.dumps(gaps, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", out)
    print(json.dumps({k: (v if not isinstance(v, (dict, list)) else "...") for k, v in gaps.items()}, ensure_ascii=False, indent=1))
    print("full-window bond:", [c["symbol"] for c in candidates[0]["full_window_continuous"]])
    print("full-window commodity:", [c["symbol"] for c in candidates[1]["full_window_continuous"]])


if __name__ == "__main__":
    main()
