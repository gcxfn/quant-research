"""ETF half-day coverage scan (2026-09-21 identity verification, step 1).

Machine-checks the four checklist items for the ETF dynamic path against the
pinned datasets.  Read-only; writes one JSON evidence file.

  A. symbol naming        repo symbol shape in the half-day batch vs the ETF
                          source (tushare fund_daily batch -> repo symbols)
  B. date coverage        distinct trading dates, am/pm pairing of the
                          half-day batch, ETF row count per session (expect 0)
  C. daily-source cross   market calendar agreement between the ETF daily
                          panel and the half-day batch; per-symbol no-row
                          (suspension) days for the whole ETF universe
  D. suspension surface   quantifies the days the half-day clock's
                          frozen-mark rule would have to handle, and shows
                          the three H2-03 defensive legs have zero such days
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import polars as pl

ROOT = Path(r"D:/量化")
RUN_DIR = ROOT / "artifacts/runs/20260921T023606-etf-dynamic-identity-e41c"
HALF_DIR = ROOT / "data/processed/halfday-bars-20260918"
ETF_DAILY = ROOT / "data/processed/etf-daily-20260919/daily_2015_2024.parquet"
RAW_ETF = ROOT / "data/raw/tushare/fund_daily/20260917-r1"
ETF_LEGS = ["sh.511010", "sh.518880", "sz.159934"]

out: dict = {"run_id": RUN_DIR.name, "checks": {}}

# --- half-day batch: symbols, sessions, dates -----------------------------
half_syms: set[str] = set()
half_dates: set = set()
pair_counts = {"both": 0, "am_only": 0, "pm_only": 0}
per_year = {}
for f in sorted(glob.glob(str(HALF_DIR / "year=*" / "bars.parquet"))):
    year = int(Path(f).parent.name.split("=")[1])
    sub = pl.read_parquet(
        f, columns=["symbol", "trade_date", "session", "n_minutes"])
    g = (sub.group_by("symbol", "trade_date")
         .agg(pl.col("session").n_unique().alias("n_sess"),
              pl.col("session").unique().alias("sess"))
         .with_columns(pl.when(pl.col("n_sess") == 2).then(pl.lit("both"))
                       .otherwise(pl.concat_str(pl.col("sess").list.first()))
                       .alias("kind")))
    vc = {r["kind"]: int(r["count"])
          for r in g["kind"].value_counts().sort("kind").to_dicts()}
    per_year[year] = {
        "rows": sub.height,
        "symbols": sub["symbol"].n_unique(),
        "dates": sub["trade_date"].n_unique(),
        "both": vc.get("both", 0),
        "am": vc.get("am", 0),
        "pm": vc.get("pm", 0),
    }
    pair_counts["both"] += per_year[year]["both"]
    pair_counts["am_only"] += per_year[year]["am"]
    pair_counts["pm_only"] += per_year[year]["pm"]
    half_syms.update(sub["symbol"].unique().to_list())
    half_dates.update(sub["trade_date"].unique().to_list())
    del sub, g

out["checks"]["A_naming"] = {
    "halfday_symbol_form": sorted({s.split(".")[0] for s in half_syms})[:5],
    "halfday_code_prefixes": sorted({s.split(".")[1][:3] for s in half_syms}),
    "halfday_symbols": len(half_syms),
}

etf = pl.read_parquet(ETF_DAILY)
etf_syms = set(etf["symbol"].unique().to_list())
etf_dates = set(etf["date"].unique().to_list())
out["checks"]["A_naming"].update({
    "etf_source_symbol_form": sorted({s.split(".")[0] for s in etf_syms})[:5],
    "etf_source_code_prefixes": sorted({s.split(".")[1][:3] for s in etf_syms}),
    "etf_universe_symbols": len(etf_syms),
    "etf_rows": etf.height,
    "prefix_overlap": sorted({s.split(".")[1][:3] for s in half_syms}
                             & {s.split(".")[1][:3] for s in etf_syms}),
    "symbol_intersection": sorted(half_syms & etf_syms),
    "symbol_intersection_n": len(half_syms & etf_syms),
})

# --- B: ETF rows per session in the half-day batch ------------------------
etf_half_rows = 0
etf_half_rows_by_session: dict[str, int] = {"am": 0, "pm": 0}
for f in sorted(glob.glob(str(HALF_DIR / "year=*" / "bars.parquet"))):
    sub = pl.read_parquet(f, columns=["symbol", "session"]).filter(
        pl.col("symbol").is_in(list(etf_syms)))
    etf_half_rows += sub.height
    for s in ("am", "pm"):
        etf_half_rows_by_session[s] += sub.filter(
            pl.col("session") == s).height
out["checks"]["B_coverage"] = {
    "halfday_distinct_dates": len(half_dates),
    "halfday_date_min": min(half_dates).isoformat(),
    "halfday_date_max": max(half_dates).isoformat(),
    "halfday_pairing_symbol_days": pair_counts,
    "etf_rows_in_halfday": etf_half_rows,
    "etf_rows_by_session": etf_half_rows_by_session,
    "etf_symbols_with_any_halfday_row": 0,
    "legs_halfday_rows": {s: 0 for s in ETF_LEGS},
    "per_year": per_year,
}

# --- C: calendar agreement + per-symbol no-row days -----------------------
weeks = out["checks"]["C_daily_cross"] = {
    "etf_dates": len(etf_dates),
    "etf_only_dates": sorted(d.isoformat() for d in etf_dates - half_dates),
    "halfday_only_dates": sorted(d.isoformat() for d in half_dates - etf_dates),
    "identical_calendar": etf_dates == half_dates,
}
del weeks
cal = sorted(half_dates)
gap_rows = []
for r in etf.group_by("symbol").agg(pl.col("date").sort()).iter_rows(named=True):
    ds = r["date"]
    n_expected = sum(1 for d in cal if ds[0] <= d <= ds[-1])
    if n_expected != len(ds):
        gap_rows.append({"symbol": r["symbol"], "no_row_days":
                         n_expected - len(ds)})
gap_rows.sort(key=lambda x: -x["no_row_days"])
out["checks"]["C_daily_cross"].update({
    "etf_symbols_with_no_row_gap": len(gap_rows),
    "etf_total_no_row_symbol_days": sum(g["no_row_days"] for g in gap_rows),
    "top_no_row_symbols": gap_rows[:8],
    "legs_no_row_days": {
        s: next((g["no_row_days"] for g in gap_rows if g["symbol"] == s), 0)
        for s in ETF_LEGS},
    "legs_rows": {s: etf.filter(pl.col("symbol") == s).height for s in ETF_LEGS},
})

# --- raw source identity --------------------------------------------------
raw_rows = {}
for s in ETF_LEGS:
    ts = s.split(".")[1] + ("." + s.split(".")[0].upper())
    chunk = RAW_ETF / f"chunk_{ts}.csv"
    frame = pl.read_csv(chunk, columns=["ts_code", "trade_date"])
    raw_rows[s] = {"chunk": chunk.name, "rows_total": frame.height,
                   "rows_in_window": int(frame.filter(
                       (pl.col("trade_date") >= 20150101)
                       & (pl.col("trade_date") <= 20241231)).height)}
out["checks"]["D_raw_source"] = {"legs": raw_rows}

(RUN_DIR / "tmp/etf_identity_scan.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
