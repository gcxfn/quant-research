# -*- coding: utf-8 -*-
"""Cross-check 3 representative ETFs: tushare fund_daily (primary) vs sina / tx sub-sources.

- Sina kline: unadjusted daily closes.
- TX qfqday: forward-adjusted, anchored to latest snapshot (NOT unadjusted).
- Comparison restricted to the research window 2015-01-01..2024-12-31
  (freeze discipline: 2025+ rows on either side are excluded, not inspected).
- This is a same-target cross-source consistency check, NOT independent verification.

Output: crosscheck.json in the run directory.
"""
from __future__ import annotations

import glob
import json
from datetime import date
from pathlib import Path

import polars as pl

REPO = Path(r"D:/量化")
RUN_DIR = Path(__file__).resolve().parents[1]
PROC = REPO / "data" / "processed" / "etf-daily-20260919"
WIN_END = date(2024, 12, 31)
WIN_START = date(2015, 1, 1)

PAIRS = [
    # (processed symbol, sina dir name, tx dir name, asset_class)
    ("sh.510050", "sh510050", "sh510050", "equity"),
    ("sh.518880", "sh518880", "sh518880", "commodity"),
    ("sz.159915", "sz159915", "sz159915", "equity"),
]


def latest_snapshot(base: Path) -> Path | None:
    dirs = sorted([d for d in base.iterdir() if d.is_dir()])
    return dirs[-1] if dirs else None


def load_sina(sym_dir: str) -> dict[date, float]:
    snap = latest_snapshot(REPO / "data" / "raw" / "sina" / sym_dir)
    with open(snap / "response.json", encoding="utf-8") as f:
        rows = json.load(f)
    out = {}
    for r in rows:
        d = date.fromisoformat(r["day"])
        if WIN_START <= d <= WIN_END:
            out[d] = float(r["close"])
    return out, snap.name


def load_tx(sym_dir: str) -> dict[date, float]:
    snap = latest_snapshot(REPO / "data" / "raw" / "tx" / sym_dir)
    out = {}
    for p in sorted(glob.glob(str(snap / "response_*.json"))):
        with open(p, encoding="utf-8") as f:
            payload = json.load(f)
        node = payload["data"]
        for _, node_sym in node.items():
            arr = node_sym.get("qfqday", []) if isinstance(node_sym, dict) else node_sym
            for row in arr:
                d = date.fromisoformat(row[0])
                if WIN_START <= d <= WIN_END:
                    # qfqday row layout: [date, open, close, high, low, volume]
                    out[d] = float(row[2])
    return out, snap.name


def stats(diffs: list[float]) -> dict:
    if not diffs:
        return {"n": 0}
    s = sorted(diffs)
    n = len(s)

    def q(p: float) -> float:
        return s[min(n - 1, int(p * n))]

    return {
        "n": n, "mean_abs": sum(abs(x) for x in s) / n,
        "p50_abs": q(0.5), "p90_abs": q(0.9), "p99_abs": q(0.99),
        "max_abs": max(abs(x) for x in s),
    }


def adj_factor_series(sym_dir: str) -> dict[date, float]:
    """fund_adj factor rows for one symbol, read from the raw batch (read-only).
    sym_dir like 'sh510050' -> tushare chunk file chunk_510050.SH.csv"""
    code, suf = sym_dir[2:], sym_dir[:2].upper()
    p = REPO / "data" / "raw" / "tushare" / "fund_adj" / "20260917-r1" / f"chunk_{code}.{suf}.csv"
    if not p.exists():
        return {}
    df = pl.read_csv(p, infer_schema_length=0)
    out = {}
    for ts, f in zip(df["trade_date"].to_list(), df["adj_factor"].to_list()):
        d = date(int(ts[:4]), int(ts[4:6]), int(ts[6:]))
        if WIN_START <= d <= WIN_END:
            out[d] = float(f)
    return out


def compare_tx(ts_closes: dict, src_closes: dict, src_snapshot: str, adj_factors: dict) -> dict:
    common = sorted(set(ts_closes) & set(src_closes))
    abs_diffs = [abs(src_closes[d] - ts_closes[d]) for d in common]
    n_exact = sum(1 for x in abs_diffs if x <= 5e-4)
    res = {
        "source": "tx",
        "source_semantics": "forward-adjusted (qfq, latest anchor); piecewise-constant ratio vs unadjusted prices for dividend payers",
        "snapshot_used": src_snapshot,
        "source_days_in_window": len(src_closes),
        "joined_days": len(common),
        "join_rate_vs_primary": round(len(common) / len(ts_closes), 4),
        "raw_exact_agree_within_half_tick": n_exact,
        "raw_agree_rate_pct": round(100.0 * n_exact / len(common), 3) if common else None,
    }
    ratios = {d: src_closes[d] / ts_closes[d] for d in common if ts_closes[d] > 0}
    rvals = list(ratios.values())
    # quantize levels at 1e-6 to absorb float noise
    levels: dict[float, list[date]] = {}
    for d, r in ratios.items():
        levels.setdefault(round(r, 6), []).append(d)
    res["ratio"] = {
        "min": round(min(rvals), 8), "max": round(max(rvals), 8),
        "n_distinct_levels": len(levels),
        "dominant_level": max(levels.items(), key=lambda kv: len(kv[1]))[0],
        "dominant_level_days": max(len(v) for v in levels.values()),
        "per_level_head": [
            {"ratio_level": lv, "days": len(dlist), "span": f"{min(dlist)}..{max(dlist)}"}
            for lv, dlist in sorted(levels.items(), key=lambda kv: -len(kv[1]))[:8]
        ],
        "note": "per-level scaled agreement is trivially true for singleton levels (level derived from the same pair); the meaningful check is dominant-level agreement and level stability",
    }
    dom = max(levels.items(), key=lambda kv: len(kv[1]))
    dom_ag = sum(1 for d in dom[1] if abs(src_closes[d] / dom[0] - ts_closes[d]) <= 5e-4)
    res["dominant_level_agree_pct"] = round(100.0 * dom_ag / len(dom[1]), 3)
    # characterize a drifting series: is tx ratio consistent with a NAV-style cumulative
    # adjustment (ratio ~ C / fund_adj)? report correlation and level-jump alignment
    if adj_factors:
        pairs_ = [(d, ratios[d], adj_factors[d]) for d in sorted(ratios) if d in adj_factors]
        if len(pairs_) > 10:
            import math
            xs = [1.0 / f for _, _, f in pairs_]
            ys = [r for _, r, _ in pairs_]
            mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
            cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
            vx = math.sqrt(sum((x - mx) ** 2 for x in xs))
            vy = math.sqrt(sum((y - my) ** 2 for y in ys))
            corr = cov / (vx * vy) if vx > 0 and vy > 0 else None
            if corr is not None and abs(corr) > 0.9:
                res["drift_vs_fund_adj"] = {
                    "pearson_corr_ratio_vs_inv_factor": round(corr, 6),
                    "interpretation": (
                        "tx adjusted series tracks the fund_adj cumulative adjustment (|corr|>0.9): same "
                        "corporate actions embedded, but the adjustment basis differs from a piecewise-constant "
                        "latest-anchor qfq, so the series is NOT comparable to unadjusted closes point-by-point"
                    ),
                }
            elif corr is not None:
                res["drift_vs_fund_adj"] = {"pearson_corr_ratio_vs_inv_factor": round(corr, 6)}
        jump_dates = set()
        prev = None
        for d in common:
            lv = round(ratios[d], 6)
            if prev is not None and lv != prev:
                jump_dates.add(d)
            prev = lv
        fsorted = sorted(adj_factors)
        factor_jump_days = {fsorted[i] for i in range(1, len(fsorted))
                            if abs(adj_factors[fsorted[i]] / adj_factors[fsorted[i - 1]] - 1) > 1e-9}
        inter = jump_dates & factor_jump_days
        res["level_jump_alignment"] = {
            "tx_level_jump_days": len(jump_dates),
            "fund_adj_factor_jump_days_in_window": len(factor_jump_days),
            "jump_days_coinciding": len(inter),
            "note": "for piecewise-constant qfq (no/daily-stable levels) re-anchors should coincide with fund_adj factor jumps",
        }
    return res


def compare(name: str, ts_closes: dict, src_closes: dict, src_snapshot: str, kind: str) -> dict:
    common = sorted(set(ts_closes) & set(src_closes))
    diffs = [src_closes[d] - ts_closes[d] for d in common]
    abs_diffs = [abs(x) for x in diffs]
    n_exact = sum(1 for x in abs_diffs if x <= 5e-4)
    n_tick = sum(1 for x in abs_diffs if x <= 1.5e-3)
    res = {
        "source": name,
        "source_semantics": kind,
        "snapshot_used": src_snapshot,
        "source_days_in_window": len(src_closes),
        "joined_days": len(common),
        "join_rate_vs_primary": round(len(common) / len(ts_closes), 4),
        "exact_agree_within_half_tick": n_exact,
        "agree_rate_pct": round(100.0 * n_exact / len(common), 3) if common else None,
        "agree_within_1p5_tick_pct": round(100.0 * n_tick / len(common), 3) if common else None,
        "abs_diff_stats": stats(diffs),
    }
    mism_dates = [(str(d), round(src_closes[d] - ts_closes[d], 6)) for d in common
                  if abs(src_closes[d] - ts_closes[d]) > 5e-4][:10]
    res["mismatch_sample_dates_max10"] = mism_dates
    return res


def main() -> None:
    out = {"generated": "2026-09-19", "run_id": RUN_DIR.name,
           "window": "2015-01-01..2024-12-31 (both sides filtered; 2025+ excluded)",
           "primary": "data/processed/etf-daily-20260919/daily_2015_2024.parquet (tushare fund_daily 20260917-r1, unadjusted)",
           "declaration": "同目标跨源一致性复核，非独立验证 (same-target cross-source consistency check, NOT independent verification: sina/tx and tushare may share upstream exchange data)",
           "pairs": []}
    for sym, sina_dir, tx_dir, cls in PAIRS:
        ts = pl.read_parquet(PROC / "daily_2015_2024.parquet") \
               .filter((pl.col("symbol") == sym) & (pl.col("date") <= pl.date(2024, 12, 31)))
        ts_closes = dict(zip(ts["date"].to_list(), ts["close"].to_list()))
        entry = {"symbol": sym, "asset_class": cls, "primary_days_in_window": len(ts_closes)}
        sina_closes, sina_snap = load_sina(sina_dir)
        entry["vs_sina"] = compare("sina", ts_closes, sina_closes, sina_snap, "unadjusted daily close")
        tx_res = None
        if (REPO / "data" / "raw" / "tx" / tx_dir).exists():
            tx_closes, tx_snap = load_tx(tx_dir)
            adj = adj_factor_series(tx_dir)
            tx_res = compare_tx(ts_closes, tx_closes, tx_snap, adj)
        else:
            tx_res = {"source": "tx", "snapshot_used": None, "note": "no tx snapshot on disk for this symbol"}
        entry["vs_tx"] = tx_res
        out["pairs"].append(entry)

    dest = RUN_DIR / "crosscheck.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", dest)
    for p in out["pairs"]:
        print(f"== {p['symbol']} ({p['asset_class']}) primary_days={p['primary_days_in_window']}")
        s = p["vs_sina"]
        print(f"   sina: joined={s['joined_days']} agree_rate={s['agree_rate_pct']}% max_abs={s['abs_diff_stats']['max_abs']:.4f}")
        t = p["vs_tx"]
        if t.get("joined_days") is not None:
            r = t["ratio"]
            line = (f"   tx:   joined={t['joined_days']} raw_agree={t['raw_agree_rate_pct']}% "
                    f"levels={r['n_distinct_levels']} dominant={r['dominant_level']} ({r['dominant_level_days']}d, "
                    f"agree={t['dominant_level_agree_pct']}%)")
            if "drift_vs_fund_adj" in t:
                line += f" drift_corr={t['drift_vs_fund_adj'].get('pearson_corr_ratio_vs_inv_factor')}"
            print(line)
        else:
            print("   tx: no snapshot")


if __name__ == "__main__":
    main()
