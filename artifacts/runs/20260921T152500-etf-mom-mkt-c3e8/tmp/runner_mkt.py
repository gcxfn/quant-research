# -*- coding: utf-8 -*-
"""ETF momentum COMBINED-level replay: 40% sleeve + 60% defensive + D3.

Prereg (frozen): docs/research/exp-20260921-etf-momentum-mkt-prereg.md
Stage A: signal-level monthly composition (19-ETF pool, 126d momentum,
top3 equal weight, abs-momentum gate, 3bp one-side cost) vs pool
equal-weight and CSI300 benchmarks; gates A1/A2/A3.
Stage B (only if A passes all gates): band_engine v1.5 pm-only replay,
40% momentum sleeve x D3 account overlay + 60% defensive leg, 500k,
eight gates vs the fixed-scheme-r2 B1mix/B3' benchmarks.
Smoke: env ETF_WINDOW="2015-01-01:2015-06-30" (stage paths only, no gates).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import polars as pl

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

from quant.research.fixed_scheme_lib import (  # noqa: E402
    DEFENSE_SYMBOLS, DefensiveLeg, defensive_month_returns,
    mix_from_monthly, monthly_returns_from_equity, cagr_from_monthly,
    mdd_from_monthly, yearly_from_monthly)
from quant.backtest.band_engine import (  # noqa: E402
    assert_frozen, run_band_backtest_intents)
from quant.portfolio.risk_overlay import AccountRiskDynamics  # noqa: E402

PREREG = ROOT / "docs/research/exp-20260921-etf-momentum-prereg.md"
ETF_PARQUET = ROOT / "data/processed/etf-daily-20260919/daily_2015_2024.parquet"
POOL_PARQUET = ROOT / "data/processed/etf-daily-20260919/pool.parquet"
FUND_ADJ_DIR = ROOT / "data/raw/tushare/fund_adj/20260917-r1"
FS_GATE_JSON = (ROOT / "artifacts/runs/20260921T121615-fixed-scheme-6e8be"
                "/outputs/metrics_and_gates.json")

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
POOL = (
    "sh.510050", "sh.510500", "sz.159915", "sh.510880",
    "sh.510900", "sh.513100", "sh.513500",
    "sh.512880", "sh.512800", "sz.159938", "sz.159928", "sz.159939",
    "sh.512980", "sh.512660", "sh.512400", "sh.510610", "sh.510620",
    "sh.512200", "sh.512580")
MOM_WINDOW = 126          # trading days (~6 months), frozen
TOP_N = 3
COST_ONE_SIDE = 0.0003    # frozen: 3bp per side
ATTACK_BUDGET = 0.40
BASELINE_EXPOSURE = 0.90  # D3 policy normal level

_win = os.environ.get("ETF_WINDOW", "full")
SMOKE = _win != "full"
if SMOKE:
    _a, _b = _win.split(":")
    WIN_START, WIN_END = date.fromisoformat(_a), date.fromisoformat(_b)
else:
    WIN_START, WIN_END = DEV_START, DEV_END

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
BUDGET_S = 900.0 if SMOKE else 1800.0
LOG_LINES: list[str] = []
_logf = (RUN_DIR / "logs" / "runner.log").open("a", encoding="utf-8")


def log(msg: object) -> None:
    line = f"[{time.perf_counter() - T0:7.1f}s] {msg}"
    LOG_LINES.append(str(line))
    _logf.write(line + "\n")
    _logf.flush()
    print(line, flush=True)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail(reason: str) -> None:
    log(f"!! FAIL: {reason}")
    (RUN_DIR / "manifest.json").write_text(json.dumps({
        "run_id": RUN_DIR.name,
        "experiment_id": "exp-20260921-etf-momentum-mkt",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


log(f"etf-momentum; window={WIN_START}..{WIN_END}"
    f"{' (SMOKE)' if SMOKE else ''}")

# === 0. pins ================================================================
pins: dict = {}
pins["prereg"] = {"sha256": sha256_file(PREREG)}
pins["etf_daily"] = {"path": str(ETF_PARQUET), "sha256": sha256_file(ETF_PARQUET)}
pins["pool"] = {"path": str(POOL_PARQUET), "sha256": sha256_file(POOL_PARQUET)}
pins["fs_gates"] = {"path": str(FS_GATE_JSON), "sha256": sha256_file(FS_GATE_JSON)}
h = hashlib.sha256()
for p in sorted(FUND_ADJ_DIR.glob("chunk_*.csv")):
    h.update(f"{sha256_file(p)}  {p.name}\n".encode())
pins["fund_adj_aggregate"] = {"sha256": h.hexdigest()}
log("pins done")

# === stage A: signal-level monthly composition ==============================
log("== stage A: monthly composition ==")
raw = pl.read_parquet(ETF_PARQUET).filter(
    (pl.col("date") >= WIN_START - timedelta(days=400))
    & (pl.col("date") <= WIN_END)).sort("symbol", "date")
factors: dict[str, dict[int, float]] = {}
for sym in POOL:
    code, exch = sym.split(".")[1], sym.split(".")[0].upper()
    p = FUND_ADJ_DIR / f"chunk_{code}.{exch}.csv"
    if not p.exists():
        _fail(f"missing fund_adj chunk for {sym}")
    factors[sym] = {int(r["trade_date"]): float(r["adj_factor"])
                    for r in csv.DictReader(p.open(encoding="utf-8", newline=""))}


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


series: dict[str, tuple[np.ndarray, np.ndarray]] = {}
for sym in POOL:
    g = raw.filter(pl.col("symbol") == sym)
    dint = np.array(sorted(factors[sym]))
    fmap = factors[sym]
    rows = [(dint_of(r["date"]), float(r["close"]) * fmap.get(dint_of(r["date"]), np.nan))
            for r in g.iter_rows(named=True)]
    rows.sort()
    if not rows:
        continue          # listed after this window (e.g. 2016+ members)
    arr = np.array(rows, dtype=float)
    keep = np.isfinite(arr[:, 1]) & (arr[:, 1] > 0)
    series[sym] = (arr[keep, 0].astype(np.int64), arr[keep, 1])

cal_set = sorted({int(v) for s in POOL if s in series
                  for v in series[s][0].tolist()})
cal_arr = np.array(cal_set, dtype=np.int64)
month_last: dict[str, int] = {}
for v in cal_arr.tolist():
    month_last[f"{v // 10_000:04d}-{v // 100 % 100:02d}"] = v
sig_keys = sorted(month_last)
sig_keys = [k for k in sig_keys
            if WIN_START.year * 100 + 1 <= int(k[:4]) * 100 + int(k[5:7])
            <= WIN_END.year * 100 + 12]


def px_at(sym: str, dint: int) -> float | None:
    a = series.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint, side="right")) - 1
    return float(a[1][i]) if i >= 0 else None


def px_le(sym: str, dint: int) -> float | None:
    """last bar strictly BEFORE dint (for forward returns)."""
    a = series[sym]
    i = int(np.searchsorted(a[0], dint, side="left")) - 1
    return float(a[1][i]) if i >= 0 else None


mom_at: dict[str, dict[str, float]] = {}
eligible_n: dict[str, int] = {}
for k in sig_keys:
    t = month_last[k]
    m: dict[str, float] = {}
    for sym in POOL:
        if sym not in series:
            continue
        a = series[sym]
        i = int(np.searchsorted(a[0], t, side="right"))
        if i >= MOM_WINDOW + 1:
            mom = float(a[1][i - 1] / a[1][i - 1 - MOM_WINDOW] - 1.0)
            if np.isfinite(mom):
                m[sym] = mom
    mom_at[k] = m
    eligible_n[k] = len(m)
log(f"  momentum available from {next(k for k in sig_keys if eligible_n[k] > 0)};"
    f" median eligible {int(np.median([eligible_n[k] for k in sig_keys]))}")

# forward monthly returns (own last-bar prices, month-end to month-end)
fwd: dict[str, dict[str, float]] = {}
for i, k in enumerate(sig_keys[:-1]):
    k1 = sig_keys[i + 1]
    t, t1 = month_last[k], month_last[k1]
    fwd[k] = {}
    for sym in POOL:
        p0, p1 = px_at(sym, t), px_at(sym, t1)
        if p0 and p1 and p0 > 0:
            fwd[k][sym] = p1 / p0 - 1.0

# strategy monthly returns with turnover cost (cost charged at the
# rebalance that starts each holding month, incl. inception)
strat_m: dict[str, float] = {}
holdings: dict[str, tuple[str, ...]] = {}
w_prev = {s: 0.0 for s in POOL}
for i, k in enumerate(sig_keys[:-1]):
    picks = [s for s, _ in sorted(mom_at[k].items(), key=lambda kv: -kv[1])
             if mom_at[k][s] > 0][:TOP_N]
    holdings[k] = tuple(picks)
    w_new = {s: (1.0 / TOP_N if s in picks else 0.0) for s in POOL}
    gross = float(np.mean([fwd[k].get(s, 0.0) for s in picks])) if picks else 0.0
    cost = sum(abs(w_new[s] - w_prev[s]) for s in POOL) * COST_ONE_SIDE
    strat_m[sig_keys[i + 1]] = gross - cost
    w_prev = w_new

# benchmark 1: pool equal-weight monthly rebalance, same cost caliber
ew_m: dict[str, float] = {}
w_prev = {s: 0.0 for s in POOL}
for i, k in enumerate(sig_keys[:-1]):
    live = [s for s in POOL if s in fwd.get(k, {})]
    if not live:
        continue
    w_new = {s: (1.0 / len(live) if s in live else 0.0) for s in POOL}
    gross = float(np.mean([fwd[k][s] for s in live]))
    cost = sum(abs(w_new[s] - w_prev[s]) for s in POOL) * COST_ONE_SIDE
    ew_m[sig_keys[i + 1]] = gross - cost
    w_prev = w_new

# benchmark 2: CSI300 buy & hold (510300 adjusted, no cost)
c300 = pl.read_parquet(ETF_PARQUET).filter(pl.col("symbol") == "sh.510300")
f300 = factors.get("sh.510300")
if f300 is None:
    p = FUND_ADJ_DIR / "chunk_510300.SH.csv"
    f300 = {int(r["trade_date"]): float(r["adj_factor"])
            for r in csv.DictReader(p.open(encoding="utf-8", newline=""))}
rows300 = sorted((dint_of(r["date"]), float(r["close"])
                  * f300.get(dint_of(r["date"]), np.nan))
                 for r in c300.iter_rows(named=True))
arr300 = np.array([(d, v) for d, v in rows300 if np.isfinite(v) and v > 0])
b300_m: dict[str, float] = {}
for i, k in enumerate(sig_keys[:-1]):
    k1 = sig_keys[i + 1]
    p0 = float(arr300[np.searchsorted(arr300[:, 0], month_last[k], "right") - 1, 1])
    p1 = float(arr300[np.searchsorted(arr300[:, 0], month_last[k1], "right") - 1, 1])
    b300_m[k1] = p1 / p0 - 1.0

strat_cagr = cagr_from_monthly(strat_m)
strat_mdd = mdd_from_monthly(strat_m)
ew_cagr = cagr_from_monthly(ew_m)
ew_mdd = mdd_from_monthly(ew_m)
b300_cagr = cagr_from_monthly(b300_m)
stageA = {
    "months": len(strat_m),
    "period": f"{min(strat_m)}..{max(strat_m)}",
    "strat": {"cagr": strat_cagr, "mdd": strat_mdd,
              "by_year": {str(k): v for k, v in yearly_from_monthly(strat_m).items()},
              "monthly": strat_m},
    "pool_ew": {"cagr": ew_cagr, "mdd": ew_mdd,
                "by_year": {str(k): v for k, v in yearly_from_monthly(ew_m).items()}},
    "csi300": {"cagr": b300_cagr,
               "by_year": {str(k): v for k, v in yearly_from_monthly(b300_m).items()}},
}
gatesA = {
    "A1_cagr_ge_8pct": strat_cagr >= 0.08,
    "A2_mdd_le_20pct": abs(strat_mdd) <= 0.20 + 1e-12,
    "A3_beat_pool_ew_2pp": strat_cagr - ew_cagr >= 0.020,
}
gatesA["pass_all"] = all(v for k_, v in gatesA.items() if k_.startswith("A"))
log(f"  A: cagr {strat_cagr*100:+.2f}% mdd {strat_mdd*100:.2f}% "
    f"({stageA['period']}, {len(strat_m)}m) | poolEW {ew_cagr*100:+.2f}% "
    f"mdd {ew_mdd*100:.2f}% | 300 {b300_cagr*100:+.2f}% "
    f"-> {'PASS' if gatesA['pass_all'] else 'fail ' + str([k_ for k_, v in gatesA.items() if not v and k_ != 'pass_all'])}")

stageA_out = RUN_DIR / "outputs" / "stageA.json"
stageA_out.write_text(json.dumps({"metrics": stageA, "gates": gatesA,
                                  "holdings": {k: list(v) for k, v in holdings.items()}},
                                 ensure_ascii=False, indent=1, default=str),
                      encoding="utf-8")
if not gatesA["pass_all"]:
    log("  note: stage-A caliber recorded, NOT gating this experiment")

# === stage B: engine replay ================================================
log("== stage B: engine replay ==")
ALL_ETFS = sorted(set(POOL) | set(DEFENSE_SYMBOLS))
daily = (raw.filter(pl.col("symbol").is_in(ALL_ETFS))
         .filter((pl.col("date") >= WIN_START) & (pl.col("date") <= WIN_END))
         .select("symbol", "date", "open", "high", "low", "close", "preclose")
         .with_columns(pl.lit(1.0, dtype=pl.Float64).alias("tradestatus"))
         .sort("symbol", "date"))
assert_frozen(daily, "date", "etf-momentum")
limits = pl.DataFrame(schema={"symbol": pl.String, "date": pl.Date,
                              "limit_up": pl.Float64, "limit_down": pl.Float64})
splits = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                              "split_factor": pl.Float64})
dividends = pl.DataFrame(schema={"symbol": pl.String, "ex_date": pl.Date,
                                 "cash_per_lot_pre_tax": pl.Float64,
                                 "round_lot": pl.Int64})
half = pl.DataFrame(schema={"trade_date": pl.Date, "symbol": pl.String,
                            "session": pl.String, "open": pl.Float64,
                            "high": pl.Float64, "low": pl.Float64,
                            "close": pl.Float64})
instruments = pl.DataFrame({
    "symbol": ALL_ETFS,
    "is_etf": [True] * len(ALL_ETFS),
    "is_t0": [True] * len(ALL_ETFS)})
symbol_meta = {s: {"asset_class": "etf", "band": 0.10, "t_plus": 0}
               for s in ALL_ETFS}

_close_ix: dict[str, tuple] = {}
for (sym,), g in daily.partition_by("symbol", as_dict=True).items():
    _close_ix[str(sym)] = (
        np.array([dint_of(d) for d in g["date"]], dtype=np.int64),
        g["close"].to_numpy().astype(np.float64),
        g["high"].to_numpy().astype(np.float64))


def close_le(sym: str, d: date) -> float | None:
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d), side="right")) - 1
    return float(a[1][i]) if i >= 0 else None


def high60_le(sym: str, d: date) -> float | None:
    a = _close_ix.get(sym)
    if a is None:
        return None
    j = int(np.searchsorted(a[0], dint_of(d), side="right"))
    lo = max(j - 60, 0)
    return float(np.max(a[2][lo:j])) if j > lo else None


sig_days = [date(month_last[k] // 10_000, month_last[k] // 100 % 100,
                 month_last[k] % 100) for k in sig_keys]
sig_sorted = sorted(sig_days)
next_sig = {sig_sorted[i]: (sig_sorted[i + 1] if i + 1 < len(sig_sorted) else None)
            for i in range(len(sig_sorted))}


def sig_eff(day: date) -> date | None:
    import bisect
    i = bisect.bisect_right(sig_sorted, day) - 1
    return sig_sorted[i] if i >= 0 else None


machine = AccountRiskDynamics("D3")
dleg = DefensiveLeg(close_at=close_le, high60_at=high60_le)
seats: set = set()
mom_picks: dict[date, tuple[str, ...]] = {
    date(month_last[k] // 10_000, month_last[k] // 100 % 100, month_last[k] % 100):
        holdings[k] for k in holdings}
n_state = {"observe": 0, "reduced_pts": 0}


def provider(day: date, sess: str, ledger: dict) -> list[dict] | None:
    if sess != "pm":
        return None
    T = sig_eff(day)
    rows: list[dict] = []
    if T is not None:
        picks = mom_picks.get(T, ())
        # account overlay FIRST (needs today's equity snapshot)
        machine.observe_close(day, float(ledger["equity_snapshot"]))
        n_state["observe"] += 1
        row = machine.step(day)
        ratio = float(row.exposure_multiplier) / BASELINE_EXPOSURE
        n_state["ratio"] = ratio
        if ratio < 1.0:
            n_state["reduced_pts"] += 1
        targets = {s: (ATTACK_BUDGET * ratio) / TOP_N for s in picks}
        expiry = (date.fromordinal(next_sig[T].toordinal() + 1)
                  if next_sig.get(T) else None)
        # BUGFIX (logged): positions carry no top-level price field; the
        # sleeve must value holdings off the daily close like DefensiveLeg
        pos_val = {p["symbol"]: p["shares"] * (close_le(p["symbol"], day) or 0.0)
                   for p in ledger["positions"]}
        eq = float(ledger["equity_snapshot"]) or 1.0
        cur_w = {s: pos_val.get(s, 0.0) / eq for s in POOL}
        for s in sorted(set(targets) | {x for x, w in cur_w.items() if w > 1e-9}):
            tw = targets.get(s, 0.0)
            cw = cur_w.get(s, 0.0)
            if tw <= 1e-9 and cw > 1e-9:
                rows.append({"symbol": s, "side": "sell", "intent": "risk",
                             "decision_date": day, "decision_session": sess,
                             "source_signal": T, "priority": 10**5,
                             "expiry_date": expiry, "target_weight": None,
                             "target_notional": None})
            elif tw > 1e-9 and cw < tw - 0.004:
                rows.append({"symbol": s, "side": "buy", "intent": "",
                             "decision_date": day, "decision_session": sess,
                             "source_signal": T, "priority": 200,
                             "expiry_date": expiry, "target_weight": tw,
                             "target_notional": None})
            elif tw > 1e-9 and cw > tw + 0.004:
                rows.append({"symbol": s, "side": "sell", "intent": "profit",
                             "decision_date": day, "decision_session": sess,
                             "source_signal": T, "priority": 150,
                             "expiry_date": expiry, "target_weight": tw,
                             "target_notional": None})
        # defensive leg (its own 60% budget; unchanged component)
        drows = dleg.decide(day, ledger, rebalance=True,
                            equity=ledger["equity_snapshot"])
        rows.extend(drows)
    for r in rows:
        seats.add((r["symbol"], r["side"], r["source_signal"]))
    return rows or None


t_c = time.perf_counter()
res = run_band_backtest_intents(
    None, daily, half, limits, splits, dividends, instruments,
    symbol_meta=symbol_meta, initial_cash=500_000.0,
    execution_clock="halfday", etf_routing="pm_only",
    intent_provider=provider, etf_market_fill=0.001)
log(f"  engine: {time.perf_counter() - t_c:.1f}s; overlay observed "
    f"{n_state['observe']} closes, reduced pts {n_state['reduced_pts']}; "
    f"defensive exits {len(dleg.exits)}; warnings {len(res.warnings)}")
(RUN_DIR / "outputs" / "engine_warnings.json").write_text(
    json.dumps(list(res.warnings)[:100], ensure_ascii=False, indent=1,
               default=str), encoding="utf-8")

res.fills.write_parquet(RUN_DIR / "outputs" / "momD3_fills.parquet")
res.events.write_parquet(RUN_DIR / "outputs" / "momD3_events.parquet")
res.daily.write_parquet(RUN_DIR / "outputs" / "momD3_daily_equity.parquet")
res.clips_final.write_parquet(RUN_DIR / "outputs" / "momD3_clips_final.parquet")

if SMOKE:
    log("smoke: stage B path OK; done")
    _logf.close()
    sys.exit(0)

# --- combined-level eight gates ---------------------------------------------
fs = json.loads(FS_GATE_JSON.read_text(encoding="utf-8"))
b1mix = fs["benchmarks"]["b1mix"]
b3p = float(fs["benchmarks"]["b3mix_mean"])
def_m = defensive_month_returns(pl.read_parquet(ETF_PARQUET), FUND_ADJ_DIR)
eqmix_m = mix_from_monthly(ew_m, def_m, 0.40)
eqmix_cagr = cagr_from_monthly(eqmix_m)
sd = res.daily["date"].to_list()
sv = res.daily["equity"].to_list()
net = (sv[-1] / sv[0]) ** (365.25 / ((sd[-1] - sd[0]).days)) - 1.0
peak_e, mdd = sv[0], 0.0
for e in sv:
    peak_e = max(peak_e, e)
    mdd = min(mdd, e / peak_e - 1.0)
yr: dict[int, float] = {}
per: dict[int, float] = {}
for d, e in zip(sd, sv):
    y = d.year
    per.setdefault(y, e)
    yr[y] = e / per[y] - 1.0
b1y = {int(k): v for k, v in b1mix["by_year"].items()}
adv = [y for y in yr if y in b1y and yr[y] > b1y[y]]
dfy = res.daily.with_columns(pl.col("date").dt.year().alias("yy"))
mean_eq = {int(r["yy"]): r["equity"] for r in dfy.group_by("yy")
           .agg(pl.col("equity").mean()).iter_rows(named=True)}
buy_by = {int(r["yy"]): r["n"] for r in
          res.fills.filter(pl.col("side") == "buy")
          .with_columns(pl.col("date").dt.year().alias("yy"))
          .group_by("yy").agg(pl.col("notional").sum().alias("n"))
          .iter_rows(named=True)}
tby = {y: buy_by.get(y, 0.0) / mean_eq[y] for y in sorted(mean_eq)}
max_turn = max(tby.values())
wmax = 0.0
state: dict[str, int] = {}
per_fill: dict[str, list] = {}
for r in res.fills.select("symbol", "date", "side", "shares")                   .iter_rows(named=True):
    per_fill.setdefault(r["symbol"], []).append(
        (dint_of(r["date"]), r["side"], int(r["shares"])))
for v in per_fill.values():
    v.sort(key=lambda e: e[0])
for d, e in zip(sd, sv):
    if e <= 0:
        continue
    td = dint_of(d)
    for sym, evs in per_fill.items():
        st = state.setdefault(sym, [0, 0])
        while st[1] < len(evs) and evs[st[1]][0] <= td:
            ev = evs[st[1]]
            st[0] += ev[2] if ev[1] == "buy" else -ev[2]
            st[1] += 1
        if st[0] > 0:
            px = close_le(sym, d)
            if px and px > 0:
                wmax = max(wmax, st[0] * px / e)
filled = set()
for r in res.fills.select("symbol", "side", "decision_date",
                          "decision_session").iter_rows(named=True):
    best = None
    for (y, sc, T) in seats:
        if y != r["symbol"] or sc != r["side"]:
            continue
        if (T < r["decision_date"]
                or (T == r["decision_date"] and r["decision_session"] == "pm")):
            if best is None or T > best:
                best = T
    if best is not None:
        filled.add((r["symbol"], r["side"], best))
exec_rate = len(filled) / len(seats) if seats else 1.0

g8 = {
    "1_net_cagr_gt_0": net > 0,
    "2_excess_vs_B1mix_ge_2pp": net - b1mix["cagr"] >= 0.020,
    "3_excess_vs_EQmix_ge_1pp": net - eqmix_cagr >= 0.010,
    "4_advantage_years_ge_5_of_6": len(adv) >= 5 and len(b1y) == 6,
    "5_mdd_le_20pct_and_le_B1mix":
        abs(mdd) <= 0.20 + 1e-12 and abs(mdd) <= abs(b1mix["mdd"]) + 1e-12,
    "6_one_side_turnover_le_6": max_turn <= 6.0,
    "7_single_name_weight_le_25pct": wmax <= 0.25,
    "8_execution_rate_ge_95pct": exec_rate >= 0.95,
}
g8["failed_gates"] = sorted(k_ for k_, v in g8.items() if not v)
g8["dev_pass"] = not g8["failed_gates"]
g8["goal_ge_6pct"] = net >= 0.06
g8["goal_cagr_ge_10pct"] = net >= 0.10
metricsB = {"net_cagr": net, "max_drawdown": mdd,
            "excess_vs_b1mix": net - b1mix["cagr"],
            "excess_vs_eqmix": net - eqmix_cagr,
            "eqmix_cagr": eqmix_cagr,
            "net_by_year": {str(k): v for k, v in yr.items()},
            "advantage_years": len(adv), "max_turnover": max_turn,
            "max_single_weight": wmax, "exec_rate": exec_rate,
            "b1mix_cagr": b1mix["cagr"], "b1mix_mdd": b1mix["mdd"],
            "b3mix_mean": b3p,
            "overlay": {"observed_closes": n_state["observe"],
                        "reduced_pm_points": n_state["reduced_pts"]},
            "defensive_exits": list(dleg.exits)}
log(f"  B: net {net*100:+.2f}% vs B1mix {net - b1mix['cagr']:+.2%} "
    f"vs EQmix {net - eqmix_cagr:+.2%} ({eqmix_cagr*100:+.2f}%) "
    f"adv {len(adv)}/6 mdd {mdd*100:.2f}% turn {max_turn:.2f} "
    f"w {wmax*100:.1f}% exec {exec_rate*100:.1f}% -> "
    f"{'PASS' if g8['dev_pass'] else 'fail ' + str(g8['failed_gates'])}")

(RUN_DIR / "outputs" / "metrics_and_gates.json").write_text(
    json.dumps({"stageA": {"metrics": stageA, "gates": gatesA},
                "stageB": {"metrics": metricsB, "gates": g8}},
               ensure_ascii=False, indent=1, default=str), encoding="utf-8")

rep = ["# ETF 动量组合层回放（40/60 + D3）dev 报告", "",
       f"- 运行 `{RUN_DIR.name}`；预登记已冻结；dev 2015-2020；初始 50 万。",
       f"- 袖套参照（阶段 A 口径，非判据）：{strat_cagr*100:+.2f}%/"
       f"{strat_mdd*100:.2f}%；全池等权 {ew_cagr*100:+.2f}%。", "",
       "| 曲线 | 净CAGR | vs B1mix | vs EQmix | 优势年 | 回撤 | 换手 | 单票max | 执行率 | 过/8 | ≥6% | ≥10% | 判定 |",
       "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
       f"| MoM组合 | {net*100:+.2f}% | {(net - b1mix['cagr'])*100:+.2f}pp "
       f"| {(net - eqmix_cagr)*100:+.2f}pp | {len(adv)}/6 | {mdd*100:.2f}% "
       f"| {max_turn:.2f} | {wmax*100:.1f}% | {exec_rate*100:.1f}% "
       f"| {8 - len(g8['failed_gates'])} | {'MET' if g8['goal_ge_6pct'] else 'no'} "
       f"| {'MET' if g8['goal_cagr_ge_10pct'] else 'no'} "
       f"| {'**PASS**' if g8['dev_pass'] else 'eliminated'} |",
       f"| EQmix基准 | {eqmix_cagr*100:+.2f}% | | | | | | | | | | | |",
       f"| B1mix基准 | {b1mix['cagr']*100:+.2f}% | | | | "
       f"{b1mix['mdd']*100:.2f}% | | | | | | | |"]
n_pass = 1 if g8["dev_pass"] else 0
rep += ["", f"## 组合级八门 {n_pass}/1 过；"
        + ("val 消费须用户批准" if n_pass else "val 不消费"), ""]
(RUN_DIR / "report.md").write_text("\n".join(rep), encoding="utf-8")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-etf-momentum-mkt",
    "status": "completed", "mode": "smoke" if SMOKE else "full",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "command": [sys.executable,
                "artifacts/runs/" + RUN_DIR.name + "/tmp/runner_etf_mom.py"],
    "engine": {"version": "v1.6+etf-market-fill", "clock": "halfday+pm_only",
               "etf_market_fill": 0.001},
    "pins": pins,
    "pool": list(POOL),
    "trial_accounting": {"strategy_line": {
        "before": 290, "this_round": 0 if SMOKE else 1,
        "after": 290 if SMOKE else 291}},
    "known_simplifications": [
        "ETF cash dividends not modelled in engine (same as fixed-scheme); "
        "stage-A signal uses adj-factor returns so sleeve is comparable",
        "D3 overlay observed once per pm point (engine pm-only routing)"],
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(RUN_DIR.rglob("*"))
                if p.is_file() and p.name not in ("manifest.json", "runner.log")},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter() - T0:.0f}s")
_logf.close()
