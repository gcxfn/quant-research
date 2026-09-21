# -*- coding: utf-8 -*-
"""Independent recompute of gate 6 max single-name weight for 8 configs.
Position shares reconstructed from fills (+split events as ratios),
marked at official close (last close <= date), divided by daily equity.
Compares against run-reported max_single_name_weight.
"""
import json
from pathlib import Path

import polars as pl

RUN = Path(r"D:\量化\artifacts\runs\20260919T030640-p3r2-dev-ad9e")
REVIEW = Path(__file__).resolve().parents[1]
DAILY = Path(r"D:\量化\data\processed\baostock-daily-20260917\daily_1999_2024.parquet")
out = {}
for i in range(1, 9):
    cid = f"C{i:02d}"
    fills = pl.read_parquet(RUN / "outputs" / f"{cid}_fills.parquet")
    ev = pl.read_parquet(RUN / "outputs" / f"{cid}_events.parquet")
    de = pl.read_parquet(RUN / "outputs" / f"{cid}_daily_equity.parquet").sort("date")
    syms = sorted(fills["symbol"].unique().to_list())
    closes = (pl.scan_parquet(DAILY)
              .filter(pl.col("symbol").is_in(syms))
              .select("date", "symbol", "close")
              .collect(streaming=True)
              .sort(["symbol", "date"]))
    close_by_sym = {}
    for sym, grp in closes.group_by("symbol", maintain_order=True):
        close_by_sym[sym[0]] = (grp["date"].to_list(), grp["close"].to_list())
    # splits: (date, symbol, ratio)
    sp = (ev.filter(pl.col("event") == "corp_action_split")
            .select("date", "symbol", "ratio")
            .sort("date"))
    sp_by_sym = {}
    for r in sp.iter_rows(named=True):
        sp_by_sym.setdefault(r["symbol"], []).append((r["date"], float(r["ratio"])))
    # fills by symbol sorted
    fl_by_sym = {}
    for r in fills.select("symbol", "date", "side", "shares").sort("date") \
                  .iter_rows(named=True):
        fl_by_sym.setdefault(r["symbol"], []).append((r["date"], r["side"], int(r["shares"])))
    dates = de["date"].to_list()
    eqs = de["equity"].to_list()
    state = {s: {"shares": 0, "i": 0, "si": 0, "last_close": 0.0, "ci": 0} for s in syms}
    wmax = 0.0
    wmax_day = wmax_sym = None
    for d, e in zip(dates, eqs):
        best = 0.0
        best_sym = None
        if e <= 0:
            continue
        for s in syms:
            st = state[s]
            cd, cv = close_by_sym.get(s, ((), ()))
            while st["ci"] < len(cd) and cd[st["ci"]] <= d:
                if cv[st["ci"]] > 0:
                    st["last_close"] = cv[st["ci"]]
                st["ci"] += 1
            sps = sp_by_sym.get(s, [])
            while st["si"] < len(sps) and sps[st["si"]][0] <= d:
                st["shares"] = int(st["shares"] * sps[st["si"]][1] + 0.5)
                st["si"] += 1
            fl = fl_by_sym.get(s, [])
            while st["i"] < len(fl) and fl[st["i"]][0] <= d:
                fd, side, sh = fl[st["i"]]
                sps2 = sp_by_sym.get(s, [])
                while st["si"] < len(sps2) and sps2[st["si"]][0] <= fd:
                    st["shares"] = int(st["shares"] * sps2[st["si"]][1] + 0.5)
                    st["si"] += 1
                st["shares"] += sh if side == "buy" else -sh
                st["i"] += 1
            if st["shares"] > 0 and st["last_close"] > 0:
                w = st["shares"] * st["last_close"] / e
                if w > best:
                    best, best_sym = w, s
        if best > wmax:
            wmax, wmax_day, wmax_sym = best, d, best_sym
    run_val = json.loads((RUN / "outputs" / "metrics_and_gates.json").read_text(encoding="utf-8"))["metrics"][cid]["max_single_name_weight"]
    out[cid] = {"wmax_recomputed": wmax, "wmax_run": run_val,
                "abs_diff": abs(wmax - run_val), "argmax_day": str(wmax_day),
                "argmax_symbol": wmax_sym, "gate6_pass": wmax <= 0.40}
    print(f"{cid}: recomputed {wmax*100:.3f}% ({wmax_sym} {wmax_day}) vs run {run_val*100:.3f}% "
          f"diff {abs(wmax-run_val)*100:.4f}pp gate6={'PASS' if wmax<=0.40 else 'FAIL'}")
(REVIEW / "tmp" / "gate6_weights.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
