# -*- coding: utf-8 -*-
"""Fixed gate-6 recompute (splits parsed from event detail) + split-coverage
audit vs split_factor.h5 + C05 full ledger replay and fills audit for ALL configs.
"""
import json
import math
import re
from datetime import date
from pathlib import Path

import polars as pl

RUN = Path(r"D:\量化\artifacts\runs\20260919T030640-p3r2-dev-ad9e")
REVIEW = Path(__file__).resolve().parents[1]
DAILY = Path(r"D:\量化\data\processed\baostock-daily-20260917\daily_1999_2024.parquet")
BUNDLE = Path(r"D:\量化\data\processed\rqalpha-bundle-v2-1-20260918")
CIDS = [f"C{i:02d}" for i in range(1, 9)]
import sys
sys.path.insert(0, r"D:\量化\src")
from quant.backtest.band_engine import load_split_factor_h5, load_dividends_h5

mg = json.loads((RUN / "outputs" / "metrics_and_gates.json").read_text(encoding="utf-8"))
splits_h5, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
splits_h5 = splits_h5.filter(pl.col("ex_date") <= date(2020, 12, 31))

out = {"gate6": {}, "split_coverage": {}, "fills_audit": {}, "c05_replay": {}}

SPLIT_EV = re.compile(r"^([a-z]{2}\.[0-9]{6}): shares (\d+) -> (\d+) \(split_factor ratio ([0-9.]+),")
DIV_EV = re.compile(r"^([a-z]{2}\.[0-9]{6}): ([0-9.]+) yuan/share pre-tax")

for cid in CIDS:
    fills = pl.read_parquet(RUN / "outputs" / f"{cid}_fills.parquet")
    ev = pl.read_parquet(RUN / "outputs" / f"{cid}_events.parquet")
    de = pl.read_parquet(RUN / "outputs" / f"{cid}_daily_equity.parquet").sort("date")

    # ---- splits from engine events (the engine's actual ledger) ----
    sp_by = {}
    for r in ev.filter(pl.col("event") == "corp_action_split").iter_rows(named=True):
        m = SPLIT_EV.match(r["detail"])
        assert m, r["detail"]
        sp_by.setdefault(m.group(1), []).append((r["date"], int(m.group(3)) / int(m.group(2))))
    div_rows = []
    for r in ev.filter(pl.col("event") == "corp_action_dividend").iter_rows(named=True):
        div_rows.append((r["date"], float(r["cash_amount"])))

    # ---- gate 6: daily max single-name weight on engine ledger ----
    syms = sorted(fills["symbol"].unique().to_list())
    closes = (pl.scan_parquet(DAILY).filter(pl.col("symbol").is_in(syms))
              .filter(pl.col("tradestatus") != 0)
              .select("date", "symbol", "close").collect().sort(["symbol", "date"]))
    cbs = {}
    for sym, grp in closes.group_by("symbol", maintain_order=True):
        cbs[sym[0]] = (grp["date"].to_list(), grp["close"].to_list())
    fl_by = {}
    for r in fills.select("symbol", "date", "side", "shares").sort("date").iter_rows(named=True):
        fl_by.setdefault(r["symbol"], []).append((r["date"], r["side"], int(r["shares"])))
    dates = de["date"].to_list()
    eqs = de["equity"].to_list()
    state = {s: {"sh": 0, "i": 0, "si": 0, "px": 0.0, "ci": 0} for s in syms}
    wmax, wday, wsym = 0.0, None, None
    for d, e in zip(dates, eqs):
        if e <= 0:
            continue
        best, bs = 0.0, None
        for s in syms:
            st = state[s]
            cd, cv = cbs.get(s, ((), ()))
            while st["ci"] < len(cd) and cd[st["ci"]] <= d:
                if cv[st["ci"]] > 0:
                    st["px"] = cv[st["ci"]]
                st["ci"] += 1
            spl = sp_by.get(s, [])
            while st["si"] < len(spl) and spl[st["si"]][0] <= d:
                st["sh"] = int(st["sh"] * spl[st["si"]][1] + 0.5)
                st["si"] += 1
            fl = fl_by.get(s, [])
            while st["i"] < len(fl) and fl[st["i"]][0] <= d:
                fd, side, sh = fl[st["i"]]
                while st["si"] < len(spl) and spl[st["si"]][0] <= fd:
                    st["sh"] = int(st["sh"] * spl[st["si"]][1] + 0.5)
                    st["si"] += 1
                st["sh"] += sh if side == "buy" else -sh
                st["i"] += 1
            if st["sh"] > 0 and st["px"] > 0:
                w = st["sh"] * st["px"] / e
                if w > best:
                    best, bs = w, s
        if best > wmax:
            wmax, wday, wsym = best, d, bs
    run_val = mg["metrics"][cid]["max_single_name_weight"]
    out["gate6"][cid] = {"recomputed": wmax, "run": run_val,
                         "match_1e-9": abs(wmax - run_val) < 1e-9,
                         "argmax": f"{wsym} {wday}", "pass_le_40pct": wmax <= 0.40}

    # ---- split coverage audit: h5 splits while held must appear as events ----
    # reconstruct holding intervals per symbol from fills (+event splits)
    held = {}
    for s in syms:
        st = {"sh": 0, "si": 0}
        spl = sorted(sp_by.get(s, []))
        events_hit = {d for d, _ in spl}
        for fd, side, sh in fl_by.get(s, []):
            while st["si"] < len(spl) and spl[st["si"]][0] <= fd:
                st["sh"] = int(st["sh"] * spl[st["si"]][1] + 0.5)
                st["si"] += 1
            st["sh"] += sh if side == "buy" else -sh
        # positions after last fill; walk remaining splits
        for d, _ in spl[st["si"]:]:
            pass
        held[s] = (st, spl, fl_by.get(s, []))
    missed = []
    extra_events = []
    for s in syms:
        # walk timeline of (ex_date) from h5 and check held-at-ex-date
        st = {"sh": 0, "i": 0, "si": 0}
        spl_h5 = sorted([(d, r) for d, r in
                         splits_h5.filter(pl.col("symbol") == s)
                         .select("ex_date", "split_factor").iter_rows()])
        spl_ev = {(d, round(r, 9)) for d, r in sp_by.get(s, [])}
        fl = fl_by.get(s, [])
        for xd, ratio in spl_h5:
            while st["i"] < len(fl) and fl[st["i"]][0] <= xd:
                fd, side, sh = fl[st["i"]]
                while st["si"] < len(spl_h5) and spl_h5[st["si"]][0] <= fd:
                    st["sh"] = int(st["sh"] * spl_h5[st["si"]][1] + 0.5)
                    st["si"] += 1
                st["sh"] += sh if side == "buy" else -sh
                st["i"] += 1
            while st["si"] < len(spl_h5) and spl_h5[st["si"]][0] <= xd:
                st["sh"] = int(st["sh"] * spl_h5[st["si"]][1] + 0.5)
                st["si"] += 1
            if st["sh"] > 0:
                # held across this h5 ex-date: engine event must exist
                if not any(d == xd for d, _ in sp_by.get(s, [])):
                    missed.append((s, str(xd), st["sh"], ratio))
    out["split_coverage"][cid] = {"h5_splits_while_held_missing_event": missed}

    # ---- fills audit (all configs): fee formulas, lot, T+1 ----
    fa = {"n_fills": fills.height}
    buys = fills.filter(pl.col("side") == "buy")
    sells = fills.filter(pl.col("side") == "sell")
    fa["buy_shares_all_round_lots"] = bool((buys["shares"] % 100 == 0).all())
    fa["sell_shares_odd_lots"] = int((sells["shares"] % 100 != 0).sum())
    # buy fee: net = -(notional + commission); commission = max(1e-4*n, 5)
    bad_buy = 0
    for r in buys.select("notional", "commission", "stamp_tax", "net_cash_flow",
                         "fees_total", "is_etf").iter_rows(named=True):
        c = max(1e-4 * r["notional"], 5.0)
        if (abs(r["commission"] - c) > 1e-6 or abs(r["stamp_tax"]) > 1e-12
                or abs(r["net_cash_flow"] + r["notional"] + r["commission"]) > 1e-6
                or abs(r["fees_total"] - r["commission"]) > 1e-9):
            bad_buy += 1
    fa["buy_formula_violations"] = bad_buy
    bad_sell = 0
    for r in sells.select("date", "notional", "commission", "stamp_tax",
                          "net_cash_flow", "fees_total", "is_etf").iter_rows(named=True):
        c = max(1e-4 * r["notional"], 5.0)
        st_rate = 0.0 if r["is_etf"] else (0.001 if r["date"] < date(2023, 8, 28) else 0.0005)
        st = st_rate * r["notional"]
        if (abs(r["commission"] - c) > 1e-6 or abs(r["stamp_tax"] - st) > 1e-6
                or abs(r["net_cash_flow"] - (r["notional"] - r["commission"] - r["stamp_tax"])) > 1e-6
                or abs(r["fees_total"] - (r["commission"] + r["stamp_tax"])) > 1e-9):
            bad_sell += 1
    fa["sell_formula_violations"] = bad_sell
    # T+1: sells on day D <= shares in lots acquired strictly before D.
    # Buy -> lot(acq=buy date). Split -> each lot grows to int(sh*ratio+0.5)
    # keeping its original acq date; the ADDED shares form a new lot with
    # acq = split date (mirrors engine "added shares acquired <split date>").
    t1_bad = []
    per = {}
    for r in fills.select("symbol", "date", "side", "shares").sort("date").iter_rows(named=True):
        per.setdefault(r["symbol"], []).append((r["date"], r["side"], int(r["shares"])))
    for s, lst in per.items():
        lots = []  # [acq_date, shares]
        events = sorted(sp_by.get(s, []))
        by_date = {}
        for fd, side, sh in lst:
            by_date.setdefault(fd, []).append((side, sh))
        ei = 0
        for fd in sorted(by_date):
            # apply splits at/before today's open (engine acts at ex-date
            # open; today's buys are post-split and must not be multiplied)
            while ei < len(events) and events[ei][0] <= fd:
                sd, ratio = events[ei]
                newlots = []
                for acq, sh in lots:
                    ns = int(sh * ratio + 0.5)
                    if ns != sh:
                        newlots.append([sd, ns - sh])
                for lot, nl in zip(lots, newlots):
                    lot[1] = int(lot[1] * ratio + 0.5)
                lots.extend(newlots)
                ei += 1
            sellable = sum(sh for acq, sh in lots if acq < fd)
            sold_today = sum(sh for sd, sh in by_date[fd] if sd == "sell")
            if sold_today > sellable:
                t1_bad.append((s, str(fd), sold_today, sellable))
            for sd, sh in by_date[fd]:
                if sd == "buy":
                    lots.append([fd, sh])
                else:
                    rem = sh
                    for lot in lots:
                        take = min(rem, lot[1])
                        lot[1] -= take
                        rem -= take
                        if rem == 0:
                            break
                    lots = [lot for lot in lots if lot[1] > 0]
    out["fills_audit"][cid] = fa
    out["fills_audit"][cid]["t1_violations"] = t1_bad

    if cid == "C05":
        # ---- full daily replay: cash + positions vs engine daily rows ----
        div_by_day = {}
        for d, amt in div_rows:
            div_by_day[d] = div_by_day.get(d, 0.0) + amt
        # per-day fill cash
        cash = 200000.0
        bad_days = []
        pos_val_bad = []
        # simple aggregate ledger (symbol-level; splits from events)
        shares = {}
        rows = {r["date"]: r for r in de.iter_rows(named=True)}
        fill_by_day = {}
        for r in fills.iter_rows(named=True):
            fill_by_day.setdefault(r["date"], []).append(r)
        prev_eq = None
        for d in dates:
            row = rows[d]
            day_fills = fill_by_day.get(d, [])
            # splits act at the open, before the day's fills
            for s, spl in sp_by.items():
                for sd, ratio in spl:
                    if sd == d:
                        shares[s] = int(shares.get(s, 0) * ratio + 0.5)
            for r in day_fills:
                cash += r["net_cash_flow"]
                shares[r["symbol"]] = shares.get(r["symbol"], 0) + (
                    r["shares"] if r["side"] == "buy" else -r["shares"])
            cash += div_by_day.get(d, 0.0)
            total_cash = (row["settled_cash"] + row["pending_am_to_pm"]
                          + row["pending_next_day"])
            if abs(total_cash - cash) > 0.02:
                bad_days.append((str(d), total_cash, cash, total_cash - cash))
            if abs(row["settled_cash"] + row["pending_am_to_pm"] + row["pending_next_day"]
                   + row["positions_value"] - row["equity"]) > 0.02:
                pos_val_bad.append(str(d))
        out["c05_replay"] = {
            "days": len(dates),
            "equity_identity_violations": pos_val_bad,
            "cash_replay_violations": bad_days[:10],
            "cash_replay_violation_count": len(bad_days),
            "min_equity": float(de["equity"].min()),
            "final_positions_value_vs_clips": None,
        }
        clips = pl.read_parquet(RUN / "outputs" / "C05_clips_final.parquet")
        last = de.row(de.height - 1, named=True)
        mv_clips = float(clips["market_value"].sum())
        out["c05_replay"]["final_positions_value_vs_clips"] = {
            "daily_positions_value": last["positions_value"],
            "clips_sum": mv_clips,
            "diff": last["positions_value"] - mv_clips,
            "clips_rows": clips.height,
            "equity_minus_pos_eq_cash": abs(
                last["settled_cash"] + last["pending_am_to_pm"]
                + last["pending_next_day"] - (last["equity"] - last["positions_value"])) < 0.02,
        }

(REVIEW / "tmp" / "ledger_and_gate6.json").write_text(
    json.dumps(out, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
print(json.dumps({k: (v if k != "gate6" else {c: {kk: vv for kk, vv in d.items()}
                                                 for c, d in v.items()})
                  for k, v in out.items()}, indent=1, ensure_ascii=False, default=str)[:6000])
