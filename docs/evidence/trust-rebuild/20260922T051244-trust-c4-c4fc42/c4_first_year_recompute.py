"""C4-06 证据：首年收益与分年收益的独立复算（不改 runner，只读归档权益曲线）。

正确公式：2015 年收益 = 2015 年末权益 / 初始 500000 - 1（runner year_returns()
漏掉该段，只输出相邻年末比值）。同时给出 2016-2020 链式收益与全窗口净 CAGR，
用于核对 exp-20260921-event-families.md 的更正值与基线锚。
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[4]
INIT = 500_000.0


def arm_table(run: str, arms: list[str]) -> dict:
    base = ROOT / f"artifacts/runs/{run}/outputs"
    out: dict = {}
    for arm in arms:
        d = pl.read_parquet(base / f"{arm}_daily_equity.parquet").sort("date")
        years = sorted({x.year for x in d["date"].to_list()})
        prev = INIT
        per_year = {}
        first_ret = None
        for y in years:
            e = d.filter(pl.col("date").dt.year() == y)["equity"][-1]
            per_year[str(y)] = round(e / prev - 1.0, 6)
            if first_ret is None:
                first_ret = e / INIT - 1.0
            prev = e
        eq = d["equity"]
        peak = eq.cum_max()
        mdd = float((eq / peak - 1.0).min())
        span_years = (d["date"][-1] - d["date"][0]).days / 365.25
        out[arm] = {
            "first_year": years[0],
            "first_year_return": round(first_ret, 6),
            "per_year": per_year,
            "final_equity": round(float(eq[-1]), 2),
            "net_cagr": round((float(eq[-1]) / INIT) ** (1.0 / span_years) - 1.0, 6),
            "max_dd": round(mdd, 6),
        }
    return out


def main() -> int:
    out = {
        "formula": "year_return = equity(year_end)/eq_start_of_year - 1; "
                   "2015 = equity(2015-12-31)/500000 - 1",
        "eventfam_main": arm_table(
            "20260921T223157-eventfam-main-cb4cff", ["A1", "A2", "B1", "B2"]),
        "baseline_v4": arm_table(
            "20260921T210100-baseline-replay4-9x4q2",
            ["FULL-bin", "NOSNR-bin", "NOACCT-bin", "SIG-reg", "SIG-old"]),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
