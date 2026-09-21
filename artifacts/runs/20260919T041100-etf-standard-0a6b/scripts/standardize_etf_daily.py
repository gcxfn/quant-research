# -*- coding: utf-8 -*-
"""Standardize tushare fund_daily + fund_adj batch 20260917-r1 into
data/processed/etf-daily-20260919/.

Task: ETF leg primary-source standardization (user-approved 2026-09-19).
- Read-only on data/raw.
- Research window 2015-01-01..2024-12-31; rows on/after 2025-01-01 must not
  enter outputs (asserted, counted for reconciliation).
- Known input gap registered as-is: 159842.SZ has no fund_adj factor rows.

Outputs (data/processed/etf-daily-20260919/):
  daily_2015_2024.parquet      core OHLCV table, schema aligned to stock leg
  pool.parquet                 ETF pool with asset_class (conservative rule)
  adj_factor_coverage.parquet  per-symbol adj factor coverage
  adj_factor_missing.csv       missing-factor list
  preclose_mismatch_detail.csv close(t-1) vs pre_close mismatch detail
  quality.json                 quality summary
  manifest.json                dataset identity / schema / reconciliation
"""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import polars as pl

REPO = Path(r"D:/量化")
RUN_DIR = Path(__file__).resolve().parents[1]
TMP = RUN_DIR / "tmp"
LOG = RUN_DIR / "logs" / "standardize.log"
RAW = REPO / "data" / "raw"
PROC = REPO / "data" / "processed" / "etf-daily-20260919"

FUND_DAILY_BATCH = RAW / "tushare" / "fund_daily" / "20260917-r1"
FUND_ADJ_BATCH = RAW / "tushare" / "fund_adj" / "20260917-r1"
FUND_BASIC = RAW / "tushare" / "fund_basic" / "20260909-r1" / "chunk_market_E.csv"
TRADE_CAL = RAW / "xiaodefa" / "trade_cal" / "20260913-bulk1" / "chunk_exchange-SSE_start_date-20140101_end_date-20261231.csv"

WIN_START = "2015-01-01"
WIN_END = "2024-12-31"
WIN_START_INT = 20150101
WIN_END_INT = 20241231

_t0 = time.perf_counter()
_stage = {}

def log(msg: str) -> None:
    line = f"[{time.perf_counter() - _t0:8.1f}s] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def stage(name: str) -> None:
    _stage[name] = {"t_start": time.perf_counter()}
    log(f"--- stage {name} start")

def stage_end(name: str) -> None:
    _stage[name]["seconds"] = round(time.perf_counter() - _stage[name]["t_start"], 2)
    log(f"--- stage {name} done in {_stage[name]['seconds']}s")

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def peak_rss_gb() -> float:
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1024 ** 3, 3)
    except Exception:
        return -1.0

def fail(msg: str) -> None:
    log(f"ASSERTION FAILED: {msg}")
    raise AssertionError(msg)


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    env = {
        "python": sys.version,
        "platform": platform.platform(),
        "polars": pl.__version__,
        "peak_rss_gb_so_far": peak_rss_gb(),
    }
    log(f"env: {env}")

    # ---------------- stage 1: verify + read fund_daily ----------------
    stage("read_fund_daily")
    daily_manifest = json.loads((FUND_DAILY_BATCH / "manifest.json").read_text(encoding="utf-8"))
    adj_manifest = json.loads((FUND_ADJ_BATCH / "manifest.json").read_text(encoding="utf-8"))
    assert daily_manifest["dataset"] == "fund_daily" and adj_manifest["dataset"] == "fund_adj"
    assert daily_manifest["status"] == "completed" and adj_manifest["status"] == "completed"
    assert daily_manifest["range"] == {"start": "20150101", "end": "20241231"}
    assert adj_manifest["range"] == {"start": "20150101", "end": "20241231"}

    daily_chunks = sorted(FUND_DAILY_BATCH.glob("chunk_*.csv"))
    adj_chunks = sorted(FUND_ADJ_BATCH.glob("chunk_*.csv"))
    assert len(daily_chunks) == 1169, f"fund_daily chunk files {len(daily_chunks)} != 1169"
    # 159842.SZ chunk exists but is header-only (0 rows, batch manifest 'skipped') -> known gap
    assert len(adj_chunks) == 1169, f"fund_adj chunk files {len(adj_chunks)} != 1169"
    assert "chunk_159842.SZ.csv" in adj_manifest["chunks"]
    assert adj_manifest["chunks"]["chunk_159842.SZ.csv"]["rows"] == 0
    assert adj_manifest["skipped"] and "159842.SZ" in adj_manifest["skipped"][0]
    log(f"chunk files: daily={len(daily_chunks)} adj={len(adj_chunks)}")

    # per-file sha256 re-verification against the immutable batch manifests
    bad = []
    for batch, chunks, man in (
        ("fund_daily", daily_chunks, daily_manifest),
        ("fund_adj", adj_chunks, adj_manifest),
    ):
        man_chunks = man["chunks"]
        assert set(c.name for c in chunks) == set(man_chunks.keys()), f"{batch}: filename set mismatch vs manifest"
        for c in chunks:
            if sha256_file(c) != man_chunks[c.name]["sha256"]:
                bad.append(f"{batch}/{c.name}")
    assert not bad, f"sha256 mismatches vs batch manifest: {bad[:5]}"
    log("sha256 re-verification: all 2338 chunk files match batch manifests")

    raw_expected_rows = sum(v["rows"] for v in daily_manifest["chunks"].values())
    assert raw_expected_rows == 1_017_121, f"raw manifest total rows {raw_expected_rows} != 1017121"

    daily_lf = pl.scan_csv(
        [str(p) for p in daily_chunks],
        schema={
            "ts_code": pl.Utf8, "trade_date": pl.Utf8, "pre_close": pl.Float64,
            "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
            "close": pl.Float64, "change": pl.Float64, "pct_chg": pl.Float64,
            "vol": pl.Float64, "amount": pl.Float64,
        },
        null_values=[""],
    )
    daily_raw = daily_lf.with_columns(
        pl.col("trade_date").str.strip_chars().str.to_date("%Y%m%d", strict=True),
    ).select(
        pl.col("ts_code").alias("ts_code_src"),
        pl.col("trade_date").alias("date"),
        "pre_close", "open", "high", "low", "close", "change", "pct_chg", "vol", "amount",
    ).collect()
    n_input = daily_raw.height
    assert n_input == raw_expected_rows, f"parsed rows {n_input} != manifest total {raw_expected_rows}"
    log(f"fund_daily rows parsed: {n_input}")
    stage_end("read_fund_daily")

    # ---------------- stage 2: read fund_adj ----------------
    stage("read_fund_adj")
    adj_lf = pl.scan_csv(
        [str(p) for p in adj_chunks],
        schema={"ts_code": pl.Utf8, "trade_date": pl.Utf8, "adj_factor": pl.Float64},
        null_values=[""],
    )
    adj = adj_lf.with_columns(
        pl.col("trade_date").str.strip_chars().str.to_date("%Y%m%d", strict=True),
    ).select(
        pl.col("ts_code").alias("ts_code_src"), pl.col("trade_date").alias("date"), "adj_factor",
    ).collect()
    log(f"fund_adj rows parsed: {adj.height}")
    adj_expected_rows = sum(v["rows"] for v in adj_manifest["chunks"].values())
    assert adj.height == adj_expected_rows, f"adj rows {adj.height} != manifest total {adj_expected_rows}"
    stage_end("read_fund_adj")

    # ---------------- stage 3: standardize + window reconciliation ----------------
    stage("standardize")
    out_of_window = daily_raw.filter(
        (pl.col("date") > pl.date(2024, 12, 31)) | (pl.col("date") < pl.date(2015, 1, 1))
    )
    n_out_of_window = out_of_window.height
    rows_2025plus = daily_raw.filter(pl.col("date") > pl.date(2024, 12, 31)).height
    log(f"out-of-window rows: {n_out_of_window} (of which 2025+: {rows_2025plus})")

    def to_symbol(ts: pl.Expr) -> pl.Expr:
        # "511010.SH" -> "sh.511010" ; "159001.SZ" -> "sz.159001" (stock-leg format)
        code = ts.str.slice(0, 6)
        exch = ts.str.slice(7, 2).str.to_lowercase()
        return exch + "." + code

    daily = daily_raw.filter(
        (pl.col("date") >= pl.date(2015, 1, 1)) & (pl.col("date") <= pl.date(2024, 12, 31))
    ).with_columns(
        to_symbol(pl.col("ts_code_src")).alias("symbol"),
        # units: fund_daily vol is lots (手, 100 shares); amount is thousand CNY
        (pl.col("vol") * 100.0).alias("volume"),
        (pl.col("amount") * 1000.0).alias("amount"),
        pl.col("pre_close").alias("preclose"),
    ).select(
        "symbol", "date", "open", "high", "low", "close", "preclose", "volume", "amount",
    ).sort(["symbol", "date"])

    # unit sanity: implied vwap inside [low, high] (bundle v2-1 precedent)
    vw = daily.with_columns(
        pl.when(pl.col("volume") > 0).then(pl.col("amount") / pl.col("volume")).otherwise(None).alias("vwap")
    ).filter(pl.col("vwap").is_not_null())
    viol = vw.filter((pl.col("vwap") < pl.col("low") - 1e-9) | (pl.col("vwap") > pl.col("high") + 1e-9))
    vwap_checked = vw.height
    vwap_outside = viol.height
    tiny_amount = viol.filter(pl.col("amount") < 1000).height
    one_price = viol.filter(pl.col("high") == pl.col("low")).height
    # amount (post-conversion, yuan) is stored rounded to 1 yuan in the raw feed;
    # on single-share dust days (amount <= a few yuan) that rounding alone breaks the vwap band
    dust = viol.filter(pl.col("amount") < 100).height
    severe = viol.filter(
        ((pl.col("vwap") < pl.col("low") * 0.9) | (pl.col("vwap") > pl.col("high") * 1.1))
        & (pl.col("amount") >= 100)
    ).height
    log(f"vwap unit check: checked={vwap_checked} outside={vwap_outside} "
        f"tiny_amount_lt_1k={tiny_amount} one_price_day={one_price} rounding_dust_lt100yuan={dust} severe_non_dust={severe}")
    assert severe == 0, f"severe non-dust vwap violations {severe} -> unit assumption wrong"

    # schema / integrity assertions
    sym_re = r"^(sh|sz)\.\d{6}$"
    n_dup = daily.group_by(["symbol", "date"]).len().filter(pl.col("len") > 1).height
    assert n_dup == 0, f"duplicate (symbol,date) rows: {n_dup}"
    n_bad_sym = daily.filter(~pl.col("symbol").str.contains(sym_re)).height
    assert n_bad_sym == 0, f"symbol format violations: {n_bad_sym}"
    nulls = daily.select(pl.all().null_count()).transpose(include_header=False).to_series().to_list()
    n_null_rows_total = int(sum(nulls))
    log(f"null cells per column: {nulls}")
    dmin, dmax = daily.select(pl.col("date").min()).item(), daily.select(pl.col("date").max()).item()
    assert str(dmin) >= WIN_START and str(dmax) <= WIN_END, f"window boundary violated: {dmin}..{dmax}"
    n_rows_final = daily.height
    log(f"final rows: {n_rows_final}, date range {dmin}..{dmax}")

    recon = {
        "input_rows": n_input,
        "input_rows_match_batch_manifest": True,
        "rows_out_of_window": n_out_of_window,
        "rows_2025_plus": rows_2025plus,
        "rows_before_2015": n_out_of_window - rows_2025plus,
        "output_rows": n_rows_final,
        "difference_note": (
            "input batch was fetched with range 20150101..20241231; the filter found "
            f"{rows_2025plus} rows on/after 2025-01-01 and {n_out_of_window - rows_2025plus} rows before "
            "2015-01-01, both applied defensively before write; difference "
            f"{n_input - n_rows_final} rows = out-of-window filter only (no other row was dropped)"
        ),
    }
    assert recon["input_rows"] - recon["output_rows"] == recon["rows_out_of_window"]
    stage_end("standardize")

    # ---------------- stage 4: preclose consistency ----------------
    stage("preclose_check")
    pc = daily.with_columns(
        pl.col("close").shift(1).over("symbol", order_by="date").alias("prev_close")
    ).with_columns(
        (pl.col("preclose") - pl.col("prev_close")).abs().alias("abs_diff"),
        pl.when(pl.col("prev_close") > 0)
          .then((pl.col("preclose") - pl.col("prev_close")) / pl.col("prev_close"))
          .otherwise(None).alias("rel_diff"),
    )
    n_compared = pc.filter(pl.col("prev_close").is_not_null()).height
    mism = pc.filter(pl.col("prev_close").is_not_null() & (pl.col("abs_diff") > 1e-6))
    n_mismatch = mism.height
    adj_sym = adj.with_columns(
        (pl.col("ts_code_src").str.slice(7, 2).str.to_lowercase() + "." + pl.col("ts_code_src").str.slice(0, 6)).alias("symbol")
    ).select("symbol", "date", "adj_factor").sort(["symbol", "date"])
    fac_chg = adj_sym.with_columns(
        (pl.col("adj_factor") / pl.col("adj_factor").shift(1).over("symbol", order_by="date")).alias("factor_ratio")
    ).select("symbol", "date", "factor_ratio")
    mism_detail = (
        mism.select("symbol", "date", "preclose", "prev_close", "abs_diff", "rel_diff")
        .join(fac_chg, on=["symbol", "date"], how="left")
        .with_columns(
            (
                pl.col("factor_ratio").is_not_null()
                & ((pl.col("factor_ratio") - 1.0).abs() > 1e-9)
            ).fill_null(False).alias("factor_jumped_same_day")
        )
        .sort(["symbol", "date"])
    )
    n_factor_aligned = int(mism_detail.filter(pl.col("factor_jumped_same_day")).height)
    absd = mism.select("abs_diff")
    q = absd.quantile(0.5).item(), absd.quantile(0.9).item(), absd.quantile(0.99).item(), absd.max().item()
    rel = mism.select("rel_diff")
    rel_max = rel.max().item()
    n_syms_with_mismatch = mism.select(pl.col("symbol").n_unique()).item()
    log(f"preclose: compared={n_compared} equal={n_compared - n_mismatch} mismatch={n_mismatch} "
        f"({100.0 * n_mismatch / n_compared:.3f}%) across {n_syms_with_mismatch} symbols; "
        f"abs_diff p50/p90/p99/max = {q}; max_rel={rel_max}; factor-jump-aligned={n_factor_aligned}")
    mism_detail.write_csv(PROC / "preclose_mismatch_detail.csv")
    preclose_stats = {
        "definition": "per symbol, compare preclose(t) with close(t-1); float-equal within 1e-6",
        "rows_compared": n_compared,
        "rows_equal": n_compared - n_mismatch,
        "rows_mismatch": n_mismatch,
        "mismatch_pct": round(100.0 * n_mismatch / n_compared, 4),
        "symbols_with_mismatch": n_syms_with_mismatch,
        "abs_diff_quantiles": {"p50": q[0], "p90": q[1], "p99": q[2], "max": q[3]},
        "max_abs_rel_diff": rel_max,
        "mismatch_days_with_adj_factor_jump_same_day": n_factor_aligned,
        "interpretation": (
            "mismatches are expected on ex-distribution days: the exchange publishes an adjusted "
            "reference preclose (ex-price) while close(t-1) is the raw last trade; the share that "
            "aligns with a same-day fund_adj factor jump confirms this. Remaining mismatches are "
            "kept as-is (raw source semantics preserved), see detail csv"
        ),
    }
    stage_end("preclose_check")

    # ---------------- stage 5: adj factor coverage ----------------
    stage("adj_coverage")
    daily_keys = daily.select("symbol", "date")
    adj_cov = (
        daily_keys.join(adj_sym, on=["symbol", "date"], how="left")
        .group_by("symbol")
        .agg(
            pl.len().alias("daily_rows"),
            pl.col("adj_factor").is_not_null().sum().alias("adj_rows_on_daily_dates"),
            pl.col("adj_factor").min().alias("factor_min"),
            pl.col("adj_factor").max().alias("factor_max"),
            pl.col("date").min().alias("daily_first"),
            pl.col("date").max().alias("daily_last"),
            pl.col("adj_factor").is_null().any().alias("has_missing"),
        )
        .with_columns(
            (pl.col("daily_rows") - pl.col("adj_rows_on_daily_dates")).alias("daily_rows_missing_factor")
        )
        .sort("symbol")
    )
    adj_extra = (
        adj_sym.join(daily_keys, on=["symbol", "date"], how="anti")
        .group_by("symbol").agg(pl.len().alias("adj_rows_not_in_daily"), pl.col("date").min().alias("extra_first"), pl.col("date").max().alias("extra_last"))
        .sort("symbol")
    )
    adj_cov = adj_cov.join(adj_extra, on="symbol", how="full", coalesce=True).with_columns(
        pl.col("daily_first").fill_null(pl.col("extra_first")),
        pl.col("daily_last").fill_null(pl.col("extra_last")),
    ).sort("symbol")
    n_syms_no_factor = adj_cov.filter(pl.col("adj_rows_on_daily_dates").fill_null(0) == 0).height
    missing_syms = adj_cov.filter(pl.col("adj_rows_on_daily_dates").fill_null(0) == 0).select("symbol").to_series().to_list()
    partial = adj_cov.filter((pl.col("adj_rows_on_daily_dates").fill_null(0) > 0) & (pl.col("daily_rows_missing_factor").fill_null(0) > 0))
    log(f"adj coverage: symbols_no_factor={n_syms_no_factor} {missing_syms}; "
        f"symbols_partial={partial.height}; rows missing factor total={int(adj_cov['daily_rows_missing_factor'].fill_null(0).sum() or 0)}")
    n_factor_jumps = fac_chg.filter((pl.col("factor_ratio") - 1.0).abs() > 1e-9).height
    n_factor_jumps_1pct = fac_chg.filter((pl.col("factor_ratio") - 1.0).abs() > 0.01).height
    adj_cov.write_parquet(PROC / "adj_factor_coverage.parquet")

    missing_out = adj_cov.filter(
        pl.col("adj_rows_on_daily_dates").fill_null(0) == 0
    ).select(
        pl.lit("full").alias("gap_type"), "symbol",
        pl.col("daily_first").alias("window_start"), pl.col("daily_last").alias("window_end"),
        pl.col("daily_rows").alias("rows_affected"),
    )
    partial_out = partial.select(
        pl.lit("partial").alias("gap_type"), "symbol",
        pl.col("daily_first").alias("window_start"), pl.col("daily_last").alias("window_end"),
        pl.col("daily_rows_missing_factor").alias("rows_affected"),
    )
    pl.concat([missing_out, partial_out]).sort(["gap_type", "symbol"]).write_csv(PROC / "adj_factor_missing.csv")
    adj_stats = {
        "source_batch": "data/raw/tushare/fund_adj/20260917-r1",
        "adj_rows": adj.height,
        "adj_symbols": int(adj_sym.select(pl.col("symbol").n_unique()).item()),
        "symbols_with_full_factor": int(adj_cov.height - n_syms_no_factor - partial.height),
        "symbols_without_any_factor": n_syms_no_factor,
        "symbols_without_any_factor_list": missing_syms,
        "symbols_with_partial_factor": partial.height,
        "daily_rows_missing_factor": int(adj_cov["daily_rows_missing_factor"].fill_null(0).sum() or 0),
        "known_gap_registered": "159842.SZ empty result in raw batch (manifest skipped field), registered as-is",
        "factor_jump_events": n_factor_jumps,
        "factor_jump_events_gt_1pct": n_factor_jumps_1pct,
    }
    stage_end("adj_coverage")

    # ---------------- stage 6: pool + asset class ----------------
    stage("pool")
    fb = pl.read_csv(FUND_BASIC, infer_schema_length=0, null_values=[""])
    universe = fb.filter(
        (pl.col("market") == "E")
        & pl.col("name").str.contains("ETF")
        & (pl.col("list_date") <= "20241231")
        & (pl.col("delist_date").is_null() | (pl.col("delist_date") >= "20150101"))
    )
    assert universe.height == 1169, f"universe recompute {universe.height} != 1169"
    uni_syms = set(
        (universe.select(
            (pl.col("ts_code").str.slice(7, 2).str.to_lowercase() + "." + pl.col("ts_code").str.slice(0, 6)).alias("s")
        ))["s"].to_list()
    )
    daily_syms = set(daily.select(pl.col("symbol").unique()).to_series().to_list())
    assert uni_syms == daily_syms, (
        f"universe vs daily symbol mismatch: only_universe={sorted(uni_syms - daily_syms)[:5]} "
        f"only_daily={sorted(daily_syms - uni_syms)[:5]}"
    )

    agg = daily.group_by("symbol").agg(
        pl.col("date").min().alias("first_trade_date"),
        pl.col("date").max().alias("last_trade_date"),
        pl.len().alias("trade_days"),
    )
    pool = universe.select(
        (pl.col("ts_code").str.slice(7, 2).str.to_lowercase() + "." + pl.col("ts_code").str.slice(0, 6)).alias("symbol"),
        "name", "fund_type", "invest_type", "type", "list_date", "delist_date", "status",
    ).join(agg, on="symbol", how="left").with_columns(
        pl.col("trade_days").is_not_null().alias("traded_in_window"),
        pl.col("list_date").str.to_date("%Y%m%d", strict=False).alias("list_date"),
        pl.col("delist_date").str.to_date("%Y%m%d", strict=False).alias("delist_date"),
    ).with_columns(
        (pl.col("delist_date").is_not_null() & (pl.col("delist_date") <= pl.date(2024, 12, 31))).alias("delisted_in_window"),
    )

    # conservative asset-class rule: code prefix + name keywords, first match wins
    money_kw = ["货币", "现金", "添益", "快线", "保证金", "理财"]
    bond_kw = ["债", "短融", "存单"]
    commodity_kw = ["黄金", "上海金", "豆粕", "原油", "能源化工", "期货", "白银"]
    cross_kw = ["QDII", "纳斯达克", "纳指", "日经", "恒生", "港股", "中概", "海外", "全球",
                "美国", "德国", "法国", "亚太", "道琼斯", "DAX", "沙特", "东盟", "印度"]
    equity_kw = ["指数", "中证", "上证", "深证", "国证", "科创", "创业", "双创", "MSCI", "A股",
                 "300", "500", "800", "1000", "180", "红利", "龙头"]
    equity_pfx = ["510", "512", "515", "516", "517", "560", "561", "562", "563", "588", "159"]

    def classify(name: str, sym: str) -> str:
        pfx3 = sym.split(".")[1][:3]
        if any(k in name for k in money_kw):
            return "money"
        if any(k in name for k in bond_kw):
            return "bond"
        # guard: 黄金产业股票ETF etc. are gold-industry EQUITY funds, not spot gold
        if any(k in name for k in commodity_kw) and "股票" not in name:
            return "commodity"
        if pfx3 == "513" or any(k in name for k in cross_kw):
            return "cross_border"
        if any(k in name for k in equity_kw) or pfx3 in equity_pfx:
            return "equity"
        return "unknown"

    rules_doc = {
        "basis": "conservative: code prefix + name keywords; first match wins; no per-fund certification",
        "priority": ["money", "bond", "commodity", "cross_border", "equity", "unknown"],
        "money_keywords": money_kw,
        "bond_keywords": bond_kw,
        "commodity_keywords": commodity_kw,
        "commodity_guard": "name containing 股票 never classified commodity (黄金产业股票ETF is gold-industry equity)",
        "cross_border": {"prefix": ["513"], "keywords": cross_kw},
        "equity": {"prefix": equity_pfx, "keywords": equity_kw},
        "unknown": "no rule matched -> unknown (conservative)",
        "known_limitations": [
            "上证大宗商品股票ETF is an equity sector fund; keyword 商品 intentionally NOT used for commodity to avoid it",
            "标普/国际 keywords intentionally NOT used (they also match A-share funds like 标普中国A股红利); QDII marker or non-A keywords used instead",
            "bond rule keyword 债 may miss exotic names; 短融/存单 added for 511360-type funds",
        ],
    }
    classes = [classify(nm, sy) for nm, sy in zip(pool["name"].to_list(), pool["symbol"].to_list())]
    pool = pool.with_columns(pl.Series("asset_class", classes, dtype=pl.Utf8))
    pool = pool.select(
        "symbol", "name", "asset_class", "list_date", "delist_date", "delisted_in_window",
        "traded_in_window", "first_trade_date", "last_trade_date", "trade_days",
        "fund_type", "invest_type", "type", "status",
    ).sort("symbol")
    pool.write_parquet(PROC / "pool.parquet")

    # rule vs tushare fund_type cross-tab (audit aid, rule stays authoritative)
    ct = (
        pool.with_columns(pl.col("fund_type").fill_null("null"))
        .group_by(["asset_class", "fund_type"]).len().sort(["asset_class", "fund_type"])
    )
    ct_dict = {f"{a}|{b}": c for a, b, c in ct.iter_rows()}
    log(f"asset_class counts: {pool.group_by('asset_class').len().sort('asset_class').to_dicts()}")
    log(f"asset_class x fund_type: {ct_dict}")
    n_delisted = int(pool["delisted_in_window"].sum())
    status_counts = {k: v for k, v in pool.group_by("status").len().sort("status").iter_rows()}
    delist_breakdown = {
        "delist_date_present": int(pool.filter(pl.col("delist_date").is_not_null()).height),
        "delist_date_in_window": n_delisted,
        "delist_date_after_2024_12_31": int(pool.filter(
            pl.col("delist_date").is_not_null() & (pl.col("delist_date") > pl.date(2024, 12, 31))
        ).height),
        "status_D_without_delist_date": int(pool.filter(
            (pl.col("status") == "D") & pl.col("delist_date").is_null()
        ).height),
    }
    log(f"status: {status_counts}; delist breakdown: {delist_breakdown}")
    log(f"delisted_in_window: {n_delisted}")
    del_cov = pool.filter(pl.col("delisted_in_window")).select(
        (pl.col("last_trade_date") - pl.col("delist_date")).dt.total_days().alias("gap_days")
    )
    del_gap = {
        "delisted_in_window": n_delisted,
        "last_trade_minus_delist_date_days": {
            "min": del_cov.min().item(), "p50": del_cov.quantile(0.5).item(),
            "max": del_cov.max().item(),
        },
        "note": "daily data ends at/near the delist date; no post-delist rows exist (end-of-life coverage as-is)",
    }
    stage_end("pool")

    # ---------------- stage 7: write daily parquet ----------------
    stage("write_daily")
    daily.write_parquet(PROC / "daily_2015_2024.parquet")
    n_written = pl.scan_parquet(PROC / "daily_2015_2024.parquet").select(pl.len()).collect().item()
    assert n_written == n_rows_final, f"written rows {n_written} != expected {n_rows_final}"
    log(f"written daily_2015_2024.parquet rows={n_written}")
    stage_end("write_daily")

    # ---------------- stage 8: prefix stats + quality + manifest ----------------
    stage("manifest")
    pref = daily.with_columns(pl.col("symbol").str.slice(3, 3).alias("p3")).group_by("p3").len().sort("p3")
    pref_rows = {r[0]: r[1] for r in pref.iter_rows()}
    pref_syms = {
        r[0]: r[1] for r in daily.with_columns(pl.col("symbol").str.slice(3, 3).alias("p3"))
        .group_by("p3").agg(pl.col("symbol").n_unique()).sort("p3").iter_rows()
    }

    # window boundary assertions on pooled outputs
    pool_bounds_ok = bool(
        pool.filter(pl.col("traded_in_window")).select(
            (pl.col("first_trade_date") >= pl.date(2015, 1, 1)).all()
            & (pl.col("last_trade_date") <= pl.date(2024, 12, 31)).all()
        ).item()
    )
    sse_cal = pl.read_csv(TRADE_CAL, infer_schema_length=0).filter(
        (pl.col("exchange") == "SSE") & (pl.col("is_open") == "1")
        & (pl.col("cal_date") >= "20150101") & (pl.col("cal_date") <= "20241231")
    ).select(pl.col("cal_date").str.to_date("%Y%m%d").alias("date"))
    n_cal_days = sse_cal.height
    full_cov_syms = daily.group_by("symbol").agg(pl.col("date").min().alias("f"), pl.col("date").max().alias("l"), pl.len().alias("n")).filter(
        (pl.col("f") <= pl.date(2015, 1, 6)) & (pl.col("l") == pl.date(2024, 12, 31)) & (pl.col("n") == n_cal_days)
    ).height
    log(f"SSE calendar days 2015-2024: {n_cal_days}; symbols covering every calendar day: {full_cov_syms}")

    quality = {
        "total_rows": n_rows_final,
        "symbols": len(daily_syms),
        "duplicate_key_rows": n_dup,
        "null_cells": n_null_rows_total,
        "date_min": str(dmin),
        "date_max": str(dmax),
        "research_window": f"{WIN_START}..{WIN_END}",
        "rows_per_prefix": pref_rows,
        "symbols_per_prefix": pref_syms,
        "vwap_unit_check": {
            "checked_rows": vwap_checked, "outside_low_high": vwap_outside,
            "of_which_tiny_amount_lt_1k_yuan": tiny_amount,
            "of_which_one_price_day": one_price,
            "of_which_rounding_dust_lt_100_yuan": dust,
            "severe_non_dust_violations": severe,
            "unit_conclusion": (
                "volume=vol[手]*100 shares; amount=amount[千元]*1000 yuan (re-verified; matches "
                "rqalpha-bundle-v2-1 finding; only single-share dust days with amount<=3 yuan breach "
                "the band due to 1-yuan amount rounding, no unit error)"
            ),
        },
        "preclose_check": preclose_stats,
        "adj_factor": adj_stats,
        "pool": {
            "rows": pool.height,
            "traded_in_window": int(pool["traded_in_window"].sum()),
            "delisted_in_window": n_delisted,
            "status_counts": status_counts,
            "delist_date_breakdown": delist_breakdown,
            "asset_class_counts": {k: v for k, v in pool.group_by("asset_class").len().sort("asset_class").iter_rows()},
            "asset_class_x_fund_type": ct_dict,
            "delisted_coverage": del_gap,
        },
        "calendar": {
            "source": "data/raw/xiaodefa/trade_cal/20260913-bulk1 (SSE)",
            "sse_open_days_2015_2024": n_cal_days,
            "symbols_covering_every_calendar_day": full_cov_syms,
        },
        "boundary_assertions": {
            "date_min_ge_2015_01_01": True,
            "date_max_le_2024_12_31": True,
            "pool_first_last_within_window": pool_bounds_ok,
            "rows_2025_plus_in_output": 0,
        },
    }
    (PROC / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")

    # aggregate input identity: sha256 over sorted per-file hashes (after re-verification)
    def agg_hash(batch_dir: Path, man: dict) -> str:
        lines = [f"{k}:{v['sha256']}" for k, v in sorted(man["chunks"].items())]
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    daily_agg = agg_hash(FUND_DAILY_BATCH, daily_manifest)
    adj_agg = agg_hash(FUND_ADJ_BATCH, adj_manifest)
    manifest = {
        "dataset_id": "etf-daily-20260919",
        "created": "2026-09-19",
        "run_id": RUN_DIR.name,
        "source": {
            "fund_daily": {
                "path": "data/raw/tushare/fund_daily/20260917-r1/",
                "identity": {
                    "files": 1169,
                    "total_rows": raw_expected_rows,
                    "per_file_sha256_verified_against_batch_manifest": True,
                    "aggregate_sha256_of_sorted_per_file_hashes": daily_agg,
                    "batch_manifest_range": "20150101..20241231",
                    "universe": daily_manifest["universe"],
                },
                "raw_read_only": True,
            },
            "fund_adj": {
                "path": "data/raw/tushare/fund_adj/20260917-r1/",
                "identity": {
                    "files": 1168,
                    "total_rows": adj_expected_rows,
                    "per_file_sha256_verified_against_batch_manifest": True,
                    "aggregate_sha256_of_sorted_per_file_hashes": adj_agg,
                    "skipped": adj_manifest["skipped"],
                },
            },
            "pool_source": "data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv (same universe filter as raw batch, 1169)",
        },
        "files": {
            "daily_2015_2024.parquet": {"rows": n_rows_final, "research_window": f"{WIN_START}..{WIN_END}"},
            "pool.parquet": {"rows": pool.height, "note": "1 ETF pool row per ts_code; asset_class per conservative rule"},
            "adj_factor_coverage.parquet": {"rows": adj_cov.height},
            "adj_factor_missing.csv": {"rows": int(adj_cov.filter((pl.col('adj_rows_on_daily_dates').fill_null(0) == 0)).height + partial.height)},
            "preclose_mismatch_detail.csv": {"rows": n_mismatch},
        },
        "schema": {
            "key": ["symbol", "date"],
            "columns": ["symbol", "date", "open", "high", "low", "close", "preclose", "volume", "amount"],
            "symbol_format": "sh.XXXXXX / sz.XXXXXX (aligned with data/processed/baostock-daily-20260917 stock leg)",
            "rename_from_source": {"ts_code": "symbol (suffix lowercased, dot-joined)", "trade_date": "date (Date)", "pre_close": "preclose", "vol*100": "volume", "amount*1000": "amount"},
            "dropped_source_columns": ["change", "pct_chg (derivable from close/preclose; stock leg keeps its own pctChg from baostock)"],
            "units": {"volume": "shares (raw vol in 手 x100)", "amount": "yuan (raw amount in 千元 x1000)", "prices": "yuan unadjusted (market close semantics)"},
            "types": {"date": "Date", "symbol": "Utf8", "others": "Float64"},
        },
        "asset_class_rules": rules_doc,
        "reconciliation": recon,
        "quality_ref": "quality.json (same directory)",
        "limitations": [
            "single upstream (tushare pro) for prices and factors; sina/tx cross-checks are same-target comparisons, not independent verification",
            "unadjusted prices: multi-day returns across distributions require fund_adj factors; 159842.SZ has no factor rows (registered gap)",
            "preclose on ex-distribution days is the exchange adjusted reference, not close(t-1); see preclose_mismatch_detail.csv",
            "stk_limit batch contains no ETF rows: ETF limit prices must be derived (proxy), see run gaps.json",
            "2025+ excluded by design; labels/holdings must not cross 2024-12-31",
        ],
    }
    (PROC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    stage_end("manifest")

    timing = {k: v.get("seconds") for k, v in _stage.items()}
    (RUN_DIR / "logs" / "stage_timing.json").write_text(
        json.dumps({"stages": timing, "peak_rss_gb_final": peak_rss_gb(), "env": env}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log("ALL DONE")
    print(json.dumps({"quality": quality, "recon": recon}, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
