# -*- coding: utf-8 -*-
"""Baseline-rebuild replay v4: 500k stock+cash, five-layer attribution
(prereg exp-20260921-baseline-rebuild §3).

Curves (one switch per layer, prereg table):
  FULL-bin   new binary scores  G3  snr on   <- reference
  SIG-old    archived head scores (C1/C2 contaminated)
  SIG-reg    new regression scores
  NOACCT-bin G0 (no account-level de-risking)
  NOSNR-bin  single-name exits off (seat exits only)
  IDEAL-bin  fractional next-open simulation, no lot/limit/suspension
             constraints (r16.simulate_r16, 500k via capital=)
  FEE        post-hoc: FULL-bin daily equity + cumulative fees paid

Replay v4 (second-review remediation round).  Exit-semantics changes vs
v3, all in src/quant/research/single_name_rules.py:
  * stop/protection whole exits are now EVENTS with a FROZEN source --
    the engine's (symbol, risk, source) streak no longer resets daily, so
    the K=3 open-market fallback actually arms for the risk-reduction
    class (v3 defect: source=day on every re-issue);
  * take_half/clear re-issues ride intent='profit' -- profit-taking
    orders expire each half-day (module re-issue keeps the leg alive)
    and NO LONGER receive the K=3 open-market fallback they wrongly got
    in v3 (AGENTS section 1 risk/profit split);
  * a symbol leaving the ledger entirely purges its clips/events -- a
    re-entry can no longer be smashed by a stale trigger-day target.
  * the NOSNR control arm (module off) must stay BIT-IDENTICAL to v3's,
    proving the infrastructure outside the module did not move.

Audit-trail hardening (review: replay3's archived runner was not the
executed one): this script records its OWN sha256 at start and end, the
git HEAD/branch/dirty state, dependency versions and peak memory.  The
archived tmp/runner_replay.py is the executed file; do not edit it.

Report additions: per-curve turnover (single-sided notional / mean
equity), drawdown duration (longest peak-to-recovery span in trading
sessions + open underwater span), engine unfilled/k3 attribution, raw
reason-row counts next to the event-merged trigger counts.
"""
from __future__ import annotations

import hashlib
import importlib.metadata as _im
import json
import subprocess
import sys
import time
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import polars as pl  # noqa: E402
import psutil  # noqa: E402

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.fixed_scheme_lib import (  # noqa: E402
    ATTACK_BUDGET_SEAT, ConstantOverlayHost, build_atr20)
from quant.research.single_name_rules import SingleNameRules  # noqa: E402
from quant.research.risk_overlay_runner import (  # noqa: E402
    DynamicOverlayHost, LedgerMarks)
from quant.backtest.band_engine import (  # noqa: E402
    FREEZE_END, assert_frozen, batch_aggregate_sha256,
    load_daily_panel, load_dividends_h5, load_halfday_bars,
    load_split_factor_h5, load_stk_limit_batch, run_band_backtest_intents)

TRAIN_RUN = ROOT / "artifacts/runs/20260921T182503-a158-fix-4d8e2f"
OLD_SCORES = (ROOT / "artifacts/runs/20260921T142710-a158-head-b41d"
              "/outputs/ml_scores.json")
PREREG = ROOT / "docs/research/exp-20260921-baseline-rebuild-prereg.md"
V3_RUN = ROOT / "artifacts/runs/20260921T194738-baseline-replay3-c5d8h2"
DAILY_PARQUET = ROOT / "data/processed/baostock-daily-20260917/daily_1999_2024.parquet"
HALFDAY_DIR = ROOT / "data/processed/halfday-bars-20260918"
STK_DIR = ROOT / "data/raw/tushare/stk_limit/20260917-r1"
BUNDLE = ROOT / "data/processed/rqalpha-bundle-v2-1-20260918"
ENGINE_PY = ROOT / "src/quant/backtest/band_engine.py"
SNR_PY = ROOT / "src/quant/research/single_name_rules.py"

DEV_START, DEV_END = date(2015, 1, 5), date(2020, 12, 31)
INITIAL_CASH = 500_000.0
STOP_MODE = "wide"        # 3xATR20, 10%..20% (same as archived HEAD replay)
K = 4
BUDGET_S = 1200.0

T0 = time.perf_counter()
T0_WALL = datetime.now(timezone.utc)
LOG_PATH = RUN_DIR / "logs" / "runner.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_LINES: list[str] = []
_logf = LOG_PATH.open("a", encoding="utf-8")


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
        "experiment_id": "exp-20260921-baseline-rebuild",
        "status": "failed", "failure_reason": reason,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "log_tail": LOG_LINES[-200:]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    _logf.close()
    sys.exit(1)


def check_budget(what: str) -> None:
    el = time.perf_counter() - T0
    if el > BUDGET_S:
        _fail(f"budget exceeded at {what}: {el:.0f}s > {BUDGET_S:.0f}s")


# === audit-trail: self pin / git / deps =====================================
SELF_PY = Path(__file__).resolve()
SELF_SHA_START = sha256_file(SELF_PY)


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        _fail("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


GIT_HEAD = _git("rev-parse", "HEAD")
GIT_BRANCH = _git("rev-parse", "--abbrev-ref", "HEAD")
GIT_PORCELAIN = _git("status", "--porcelain")
DEPS = {p: _im.version(p) for p in ("polars", "numpy", "lightgbm", "psutil")}
log(f"self {SELF_SHA_START[:16]}; git {GIT_BRANCH} {GIT_HEAD[:12]} "
    f"({len([l for l in GIT_PORCELAIN.splitlines() if l.strip()])} dirty)")

log(f"baseline replay v4; window={DEV_START}..{DEV_END}; "
    f"cash {INITIAL_CASH:.0f}; K={K}; stop={STOP_MODE}")

# === 0. pins ================================================================
pins: dict = {}
engine_got = sha256_file(ENGINE_PY)
pins["engine"] = {"path": str(ENGINE_PY), "sha256": engine_got,
                  "note": "current HEAD engine; archived pin "
                          "f3650f8440c713b8 matches no git version"}
for name, p in [("daily", DAILY_PARQUET),
                ("split_factor", BUNDLE / "split_factor.h5"),
                ("dividends", BUNDLE / "dividends.h5"),
                ("prereg", PREREG), ("snr_module", SNR_PY),
                ("train_run_manifest", TRAIN_RUN / "manifest.json"),
                ("old_scores", OLD_SCORES)]:
    pins[name] = {"path": str(p), "sha256": sha256_file(p)}
hm = sha256_file(HALFDAY_DIR / "manifest.json")
pins["halfday_manifest"] = {"sha256": hm,
                            "match": hm.startswith("2a414174b5df2eee")}
if not pins["halfday_manifest"]["match"]:
    _fail("halfday manifest pin mismatch")
stk_agg = batch_aggregate_sha256(STK_DIR)
pins["stk_limit_aggregate"] = {
    **stk_agg, "match":
        stk_agg["aggregate_sha256"].startswith("3c53abf3b0c39b42")}
if not pins["stk_limit_aggregate"]["match"]:
    _fail("stk_limit pin mismatch")
log(f"  engine {engine_got[:16]}; pins OK")

# === 1. calendar & signals ==================================================
cal = r16.market_calendar(DAILY_PARQUET)
calendar_full = cal["date"].to_list()
idx_of_full = {d: i for i, d in enumerate(calendar_full)}
all_mes = r16.month_end_sessions(cal).filter(
    (pl.col("s") >= DEV_START) & (pl.col("s") <= DEV_END))
sig_days = [d for d in all_mes["s"].to_list() if
            idx_of_full[d] + 1 < len(calendar_full)
            and calendar_full[idx_of_full[d] + 1] <= DEV_END]
next_sig = {sig_days[i]: (sig_days[i + 1] if i + 1 < len(sig_days) else None)
            for i in range(len(sig_days))}
log(f"  {len(sig_days)} signal days ({sig_days[0]}..{sig_days[-1]})")

# === 2. pools ===============================================================
hist = r16.build_history_r16(DAILY_PARQUET, cal)
pool_frame = r16.signal_pools(hist, pl.DataFrame({"s": sig_days}))
pools_at = r16.pools_by_signal(pool_frame)
pool_set = {t: set(pools_at[t]["ranked"]) for t in sig_days}
check_budget("pools")

# === 3. score sources -> ranked legs =======================================
ML_BIN = json.loads((TRAIN_RUN / "outputs/ml_scores_bin.json")
                    .read_text(encoding="utf-8"))
ML_REG = json.loads((TRAIN_RUN / "outputs/ml_scores_reg.json")
                    .read_text(encoding="utf-8"))
ML_OLD = json.loads(OLD_SCORES.read_text(encoding="utf-8"))
SCORES = {"bin": ML_BIN, "reg": ML_REG, "old": ML_OLD}
ranked_by_src: dict[str, dict[date, list[str]]] = {}
for src, scores in SCORES.items():
    ranked_by_src[src] = {}
    for t in sig_days:
        s = scores.get(t.isoformat(), {})
        pool = pool_set[t] & set(s)
        ranked_by_src[src][t] = sorted(pool, key=lambda x: (-s[x], x))
    n_r = [len(ranked_by_src[src][t]) for t in sig_days]
    log(f"  scores[{src}]: ranked/month min {min(n_r)} max {max(n_r)}")

members_by_src: dict[str, dict[date, list[str]]] = {}
for src in SCORES:
    prev: list[str] = []
    members_by_src[src] = {}
    for t in sig_days:
        members, _ = r16.buffer_membership(prev, ranked_by_src[src][t],
                                           {}, K, False)
        members_by_src[src][t] = members
        prev = members
check_budget("legs")

# === 4. market frames (stocks only) ========================================
_union = sorted({s for src in SCORES for t in sig_days
                 for s in members_by_src[src][t]})
daily_full, daily_meta = load_daily_panel(DAILY_PARQUET)
daily = (daily_full.filter(pl.col("symbol").is_in(_union))
         .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
         .sort("symbol", "date"))
assert_frozen(daily, "date", "daily-stocks")
daily_ext = (daily_full.filter(pl.col("symbol").is_in(_union))
             .filter((pl.col("date") >= DEV_START - timedelta(days=90))
                     & (pl.col("date") <= DEV_END))
             .sort("symbol", "date"))
atr_tbl = build_atr20(daily_ext)
del daily_ext, daily_full
parts = sorted(HALFDAY_DIR.glob("year=*/bars.parquet"))
half_parts = []
for part in parts:
    f = pl.read_parquet(part)
    f = f.filter(pl.col("trade_date") <= FREEZE_END)
    f = f.filter((pl.col("trade_date") >= DEV_START)
                 & (pl.col("trade_date") <= DEV_END))
    f = f.filter(pl.col("symbol").is_in(_union))
    if f.height:
        half_parts.append(f)
half = pl.concat(half_parts, how="vertical") if half_parts else pl.DataFrame(
    schema={"trade_date": pl.Date, "symbol": pl.String, "session": pl.String,
            "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
            "close": pl.Float64})
del half_parts
assert_frozen(half, "trade_date", "halfday")
limits_full, _ = load_stk_limit_batch(STK_DIR)
limits = (limits_full.rename({"up_limit": "limit_up",
                              "down_limit": "limit_down"})
          .filter(pl.col("symbol").is_in(_union))
          .filter((pl.col("date") >= DEV_START) & (pl.col("date") <= DEV_END))
          .sort("symbol", "date"))
del limits_full
splits_all, _ = load_split_factor_h5(BUNDLE / "split_factor.h5")
divs_all, _ = load_dividends_h5(BUNDLE / "dividends.h5")
splits = splits_all.filter(pl.col("symbol").is_in(_union))
dividends = divs_all.filter(pl.col("symbol").is_in(_union))
del splits_all, divs_all
instruments = pl.DataFrame({"symbol": _union,
                            "is_etf": [False] * len(_union),
                            "is_t0": [False] * len(_union)})
log(f"  frames: {len(_union)} stocks; daily {daily.height}; "
    f"half {half.height}; limits {limits.height}")
check_budget("frames")


def _dint(col: pl.Series) -> np.ndarray:
    return (col.dt.year().cast(pl.Int64) * 10_000
            + col.dt.month().cast(pl.Int64) * 100
            + col.dt.day().cast(pl.Int64)).to_numpy()


def dint_of(d: date) -> int:
    return d.year * 10_000 + d.month * 100 + d.day


_close_ix: dict[str, tuple] = {}
for (sym,), g in (daily.filter(pl.col("tradestatus") != 0)
                  .partition_by("symbol", as_dict=True)).items():
    _close_ix[str(sym)] = (_dint(g["date"]),
                           g["close"].to_numpy().astype(np.float64),
                           g["high"].to_numpy().astype(np.float64))


def close_le(sym: str, d: date) -> float | None:
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d), side="right")) - 1
    return float(a[1][i]) if i >= 0 else None


_am_ix: dict[str, tuple] = {}
if half.height:
    amf = half.filter(pl.col("session") == "am")
    for (sym,), g in amf.partition_by("symbol", as_dict=True).items():
        _am_ix[str(sym)] = (_dint(g["trade_date"]),
                            g["close"].to_numpy().astype(np.float64))


def price_at(sym: str, d: date, sess: str) -> float | None:
    if sess == "am":
        a = _am_ix.get(sym)
        if a is None:
            return None
        i = int(np.searchsorted(a[0], dint_of(d)))
        return float(a[1][i]) if i < len(a[0]) and int(a[0][i]) == dint_of(d) \
            else None
    a = _close_ix.get(sym)
    if a is None:
        return None
    i = int(np.searchsorted(a[0], dint_of(d)))
    return float(a[1][i]) if i < len(a[0]) and int(a[0][i]) == dint_of(d) \
        else None


# === 5. provider factory ====================================================
ledger_marks = LedgerMarks(daily, half)
sig_sorted = sorted(sig_days)


def sig_eff(day: date, sess: str) -> date | None:
    idx = bisect_left(sig_sorted, day)
    if idx < len(sig_sorted) and sig_sorted[idx] == day:
        return day if sess == "pm" else (sig_sorted[idx - 1] if idx else None)
    return sig_sorted[idx - 1] if idx else None


G_DYN = {"G3": "D3"}


def make_provider(src: str, gcfg: str, snr_on: bool):
    members_by_t = {t: set(members_by_src[src][t]) for t in sig_days}
    rank_by_t = {t: {s: i + 1 for i, s in enumerate(ranked_by_src[src][t])}
                 for t in sig_days}
    seats_spy: dict = {}
    calls = {"n": 0, "rows": 0}
    reason_log: list[dict] = []          # C3: provider-side exit reasons
    host = (DynamicOverlayHost(G_DYN[gcfg], ledger_marks, trim_intent="risk")
            if gcfg in G_DYN else
            ConstantOverlayHost({t: 1.0 for t in sig_days},
                                lambda s, d, sess: price_at(s, d, sess),
                                base_seat_weight=ATTACK_BUDGET_SEAT))
    _snr_kw = ({} if STOP_MODE == "original" else
               {"atr_mult": 3.0, "dist_min": 0.10, "dist_max": 0.20})
    snr = SingleNameRules(lambda s, d: atr_tbl.atr(s, d), **_snr_kw)

    def provider(day: date, sess: str, ledger: dict) -> list[dict] | None:
        calls["n"] += 1
        T = sig_eff(day, sess)
        rows: list[dict] = []
        if T is not None:
            members = members_by_t[T]
            rank_of = rank_by_t[T]
            expiry = (date.fromordinal(next_sig[T].toordinal() + 1)
                      if next_sig.get(T) else None)
            held = {p["symbol"] for p in ledger["positions"]}
            exit_rows = []
            for sym in sorted(held - members):
                if (sym, "sell", T) in seats_spy:
                    continue
                exit_rows.append({
                    "symbol": sym, "side": "sell", "intent": "risk",
                    "decision_date": day, "decision_session": sess,
                    "source_signal": T, "priority": 10**6,
                    "expiry_date": expiry, "target_weight": None,
                    "target_notional": None, "exit_reason": "seat_exit"})
                reason_log.append({
                    "day": day.isoformat(), "sess": sess, "symbol": sym,
                    "reason": "seat_exit", "source": T.isoformat(),
                    "intent": "risk"})
                seats_spy[(sym, "sell", T)] = 1
            stock_pos = [p for p in ledger["positions"]]
            prices = {p["symbol"]: price_at(p["symbol"], day, sess)
                      for p in stock_pos}
            sn_rows = snr.decide(stock_pos, prices, day=day,
                                 session=sess) if snr_on else []
            for r in sn_rows:
                r["decision_date"] = day
                r["decision_session"] = sess
                reason_log.append({
                    "day": day.isoformat(), "sess": sess,
                    "symbol": r["symbol"], "reason": r["exit_reason"],
                    "source": r["source_signal"].isoformat(),
                    "intent": r["intent"]})
            st = host.step(ledger, members=members, rank_of=rank_of,
                           source_signal=T, expiry=expiry)
            taken = {x["symbol"] for x in sn_rows}
            overlay_rows = [r for r in st.rows if r["symbol"] not in taken]
            for r in overlay_rows:
                r["exit_reason"] = ("account_trim" if r["side"] == "sell"
                                    else None)
                if r["side"] == "sell":
                    reason_log.append({
                        "day": day.isoformat(), "sess": sess,
                        "symbol": r["symbol"], "reason": "account_trim",
                        "source": r["source_signal"].isoformat(),
                        "intent": str(r.get("intent") or "risk")})
            taken |= {r["symbol"] for r in overlay_rows}
            exit_rows = [r for r in exit_rows if r["symbol"] not in taken]
            rows.extend(sn_rows + overlay_rows + exit_rows)
            calls["rows"] += len(rows)
        return rows or None

    return {"provider": provider, "calls": calls, "host": host, "snr": snr,
            "reasons": reason_log}


# === 6. engine curves =======================================================
CURVES = [("FULL-bin", "bin", "G3", True),
          ("SIG-old", "old", "G3", True),
          ("SIG-reg", "reg", "G3", True),
          ("NOACCT-bin", "bin", "G0", True),
          ("NOSNR-bin", "bin", "G3", False)]
results: dict[str, dict] = {}
log("== engine curves ==")
for name, src, gcfg, snr_on in CURVES:
    pack = make_provider(src, gcfg, snr_on)
    t_c = time.perf_counter()
    res = run_band_backtest_intents(
        None, daily, half, limits, splits, dividends, instruments,
        symbol_meta={}, initial_cash=INITIAL_CASH,
        execution_clock="halfday", intent_provider=pack["provider"])
    wall = time.perf_counter() - t_c
    il = res.stats.get("intent_layer") or {}
    k3 = res.stats.get("k3_fallback") or {}
    log(f"  {name}: {wall:.1f}s; injected {il.get('dynamic_injected')} "
        f"orders {il.get('orders_generated')} "
        f"filled {il.get('stopped_filled')}; k3 armed {k3.get('armed')} "
        f"exec {k3.get('executed')}; warnings {len(res.warnings)}")
    results[name] = {"res": res, "wall_s": wall, "pack": pack}
    check_budget(name)

# NOSNR control arm must be BIT-IDENTICAL to v3's (module off, engine and
# every other input unchanged) -- infrastructure-stability proof
_v3_nosnr = pl.read_parquet(V3_RUN / "outputs/NOSNR-bin_daily_equity.parquet")
_n4 = results["NOSNR-bin"]["res"].daily
nosnr_identical = (
    _v3_nosnr["date"].to_list() == _n4["date"].to_list()
    and _v3_nosnr["equity"].to_list() == _n4["equity"].to_list())
log(f"  NOSNR v3-identity: {nosnr_identical}")
if not nosnr_identical:
    _fail("NOSNR control arm differs from v3 -- infrastructure moved; "
          "the exit-module fix must not touch the module-off curve")

# === 7. IDEAL fractional curve ==============================================
log("== IDEAL-bin (fractional, no execution constraints) ==")
# dev-only world: truncate hist at DEV_END and remap mkt_idx so the
# ideal curve cannot touch val data (prereg zero-contact rule)
calendar_dev = [d for d in calendar_full if d <= DEV_END]
idx_df = pl.DataFrame({"date": calendar_dev,
                       "mkt_idx_new": list(range(len(calendar_dev)))},
                      schema={"date": pl.Date, "mkt_idx_new": pl.Int64})
hist_dev = (hist.filter(pl.col("date") <= DEV_END)
            .join(idx_df, on="date", how="inner")
            .drop("mkt_idx").rename({"mkt_idx_new": "mkt_idx"}))
bank_syms = sorted({s for t in sig_days
                    for s in ranked_by_src["bin"][t][:K]})
bank = r16.PriceBank(hist_dev, calendar_dev, bank_syms)
pools_ideal = {t: {"ranked": ranked_by_src["bin"][t][:K], "q5": {},
                   "n": min(K, len(ranked_by_src["bin"][t]))}
               for t in sig_days}
# exposure aligned with the engine curves: 4 seats x 10% attack budget
exposures = {t: 4 * ATTACK_BUDGET_SEAT for t in sig_days}
ideal = r16.simulate_r16("IDEAL-bin", bank, calendar_dev, DEV_START,
                         sig_days, pools_ideal, exposures, K=0,
                         fractional=True,
                         fee_bands=r16.STOCK_FEE_SCHEDULE,
                         capital=INITIAL_CASH)
assert ideal.sessions[-1] <= DEV_END, "IDEAL curve leaked past DEV_END"
check_budget("ideal")


def _tally_reasons(reasons: list[dict]) -> dict:
    """Provider-side TRIGGER counts by exit_reason, merged per EVENT
    (symbol, source, reason): an exit re-issued across decision points
    shares its frozen source and is ONE trigger, not many (audit C3).
    In v4 every module exit -- whole (stop/protection) and halving
    (take_half/clear) alike -- re-issues with the frozen trigger-day
    source, so the merge is exact for all reasons."""
    out: dict[str, int] = {}
    for key in {(r["symbol"], r["source"], r["reason"]) for r in reasons}:
        out[key[2]] = out.get(key[2], 0) + 1
    return out


def _tally_rows(reasons: list[dict]) -> dict:
    """RAW provider-row counts by reason (transparency: how many decision
    points the average event spans = rows / events)."""
    out: dict[str, int] = {}
    for r in reasons:
        out[r["reason"]] = out.get(r["reason"], 0) + 1
    return out


def _tally_filled_reasons(reasons: list[dict], fills) -> dict:
    """COMPLETED-EXIT counts, one per EVENT (audit C3: "the same exit
    re-issued across decision points must not count as several completed
    trades").  Each provider reason row carries the event source (the
    exit trigger day or the seat's signal day); fills are attributed to
    the newest reason event at/before the fill's decision point and
    merged per (symbol, source, reason)."""
    events: dict[str, list[tuple[date, str, str]]] = {}
    for r in reasons:
        events.setdefault(r["symbol"], []).append(
            (date.fromisoformat(r["source"]), r["reason"],
             r["day"] + r["sess"]))
    for v in events.values():
        v.sort()
    done: set[tuple[str, str, str]] = set()
    if fills.height:
        for r in fills.select("symbol", "side", "decision_date",
                              "decision_session").iter_rows(named=True):
            if r["side"] != "sell":
                continue
            evs = events.get(r["symbol"], [])
            best = None
            for src_d, rsn, first_key in evs:
                if src_d <= r["decision_date"]:
                    if best is None or (src_d, first_key) > (best[0], best[2]):
                        best = (src_d, rsn, first_key)
            if best is not None:
                done.add((r["symbol"], best[0].isoformat(), best[1]))
    out: dict[str, int] = {}
    for _sym, _src, rsn in done:
        out[rsn] = out.get(rsn, 0) + 1
    return out


def monthly_returns_from_equity(sessions, equity):
    last: dict[str, tuple] = {}
    for d, e in zip(sessions, equity):
        last[d.strftime("%Y-%m")] = (d, e)
    keys = sorted(last)
    return {keys[i]: last[keys[i]][1] / last[keys[i - 1]][1] - 1.0
            for i in range(1, len(keys)) if last[keys[i - 1]][1] > 0}


def cagr_from_equity(sessions, equity):
    if len(sessions) < 2 or equity[0] <= 0:
        return float("nan")
    days = (sessions[-1] - sessions[0]).days
    return (equity[-1] / equity[0]) ** (365.25 / max(days, 1)) - 1.0


def mdd_from_equity(equity):
    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1.0)
    return mdd


def year_returns(sessions, equity):
    per: dict[int, float] = {}
    for d, e in zip(sessions, equity):
        per[d.year] = e
    years = sorted(per)
    return {years[i + 1]: per[years[i + 1]] / per[years[i]] - 1.0
            for i in range(len(years) - 1)}


# === 8. metrics & five-layer attribution ====================================
log("== metrics & five-layer attribution ==")


def exposure_stats(res) -> dict:
    """Stock-market-value / equity share from the fill ledger, marked at
    each day's close (review: the report must distinguish the 40% SEAT
    BUDGET from the realized exposure path)."""
    dates = res.daily["date"].to_list()
    eq = res.daily["equity"].to_list()
    per: dict[str, list] = {}
    if res.fills.height:
        for r in (res.fills.select("symbol", "date", "side", "shares")
                  .iter_rows(named=True)):
            per.setdefault(r["symbol"], []).append(
                (dint_of(r["date"]), r["side"], int(r["shares"])))
    for v in per.values():
        v.sort(key=lambda e: e[0])
    state: dict[str, list] = {}
    w_sum = w_n = 0
    w_peak = 0.0
    for d, e in zip(dates, eq):
        if e <= 0:
            continue
        td = dint_of(d)
        mv = 0.0
        for sym, evs in per.items():
            st = state.setdefault(sym, [0, 0])
            while st[1] < len(evs) and evs[st[1]][0] <= td:
                ev = evs[st[1]]
                st[0] += ev[2] if ev[1] == "buy" else -ev[2]
                st[1] += 1
            if st[0] > 0:
                px = close_le(sym, d)
                if px and px > 0:
                    mv += st[0] * px
        w = mv / e
        w_sum += w
        w_n += 1
        w_peak = max(w_peak, w)
    return {"mean": w_sum / max(w_n, 1), "peak": w_peak}


def turnover_stats(res) -> dict:
    """Single-sided traded notional over the mean of daily closing
    equity (formula stated in the report; same window as net_cagr)."""
    eq = res.daily["equity"].to_list()
    mean_eq = sum(eq) / max(len(eq), 1)
    sell_n = buy_n = 0.0
    if res.fills.height:
        for r in (res.fills.select("side", "shares", "price")
                  .iter_rows(named=True)):
            notional = float(r["shares"]) * float(r["price"])
            if r["side"] == "sell":
                sell_n += notional
            else:
                buy_n += notional
    return {"sell_notional": sell_n, "buy_notional": buy_n,
            "mean_equity": mean_eq,
            "sell_over_mean_equity": sell_n / mean_eq if mean_eq > 0
            else None,
            "buy_over_mean_equity": buy_n / mean_eq if mean_eq > 0
            else None}


def drawdown_spans(sessions, equity) -> dict:
    """Longest peak-to-recovery span in TRADING sessions, plus the span
    still open at the window end (report conclusion element: how long
    the account stayed underwater, not just how deep)."""
    spans: list[dict] = []
    peak_i = 0
    trough_i = 0
    for i in range(1, len(equity)):
        if equity[i] >= equity[peak_i]:
            spans.append({
                "peak": sessions[peak_i].isoformat(),
                "trough": sessions[trough_i].isoformat(),
                "end": sessions[i].isoformat(),
                "len_sessions": i - peak_i,
                "depth": equity[trough_i] / equity[peak_i] - 1.0,
                "recovered": True})
            peak_i = i
            trough_i = i
        elif equity[i] < equity[trough_i]:
            trough_i = i
    open_span = None
    if peak_i < len(equity) - 1:
        open_span = {
            "peak": sessions[peak_i].isoformat(),
            "trough": sessions[trough_i].isoformat(),
            "end": sessions[-1].isoformat(),
            "len_sessions": len(equity) - 1 - peak_i,
            "depth": equity[trough_i] / equity[peak_i] - 1.0,
            "recovered": False}
    best = max(spans + ([open_span] if open_span else []),
               key=lambda s: s["len_sessions"], default=None)
    return {"longest": best, "open_at_end": open_span}


def engine_stats_summary(res) -> dict:
    """Unfilled-order / fallback attribution straight from the engine
    stats (report conclusion element: where unfilled orders went)."""
    keys = ("signals", "orders_filled", "fill_rate_order_session",
            "unfilled_exit_reasons", "unfilled_exit_share_buys",
            "k3_fallback", "intent_layer", "void_days")
    return {k: res.stats.get(k) for k in keys if k in res.stats}


metrics: dict[str, dict] = {}
for name, *_ in CURVES:
    res = results[name]["res"]
    sd = res.daily["date"].to_list()
    sv = res.daily["equity"].to_list()
    net = cagr_from_equity(sd, sv)
    # investable-start caliber: CAGR from the FIRST FILL day (the first
    # day the strategy could hold anything), disclosed next to the
    # full-window number; the anchor is that day's CLOSING equity
    if res.fills.height:
        t0 = res.fills["date"].min()
        i0 = next(i for i, d in enumerate(sd) if d >= t0)
        net_inv = cagr_from_equity(sd[i0:], sv[i0:])
        inv_start = t0.isoformat()
    else:
        net_inv, inv_start = float("nan"), None
    metrics[name] = {
        "net_cagr": net, "net_cagr_investable_start": net_inv,
        "investable_start": inv_start,
        "max_drawdown": mdd_from_equity(sv),
        "net_by_year": {int(k): v for k, v in
                        year_returns(sd, sv).items()},
        "n_fills": res.fills.height,
        "final_equity": sv[-1],
        "total_fees": float(res.fills["fees_total"].sum())
        if res.fills.height else 0.0,
        "exposure": exposure_stats(res),
        "turnover": turnover_stats(res),
        "drawdown": drawdown_spans(sd, sv),
        "engine_stats": engine_stats_summary(res),
        "reasons_provider": _tally_reasons(results[name]["pack"]["reasons"]),
        "reasons_provider_rows": _tally_rows(
            results[name]["pack"]["reasons"]),
        "reasons_completed": _tally_filled_reasons(
            results[name]["pack"]["reasons"], res.fills)}
    dd = metrics[name]["drawdown"]["longest"]
    log(f"  {name}: net {net*100:+.2f}% (inv-start {net_inv*100:+.2f}%) "
        f"mdd {metrics[name]['max_drawdown']*100:.2f}% "
        f"dd-len {dd['len_sessions'] if dd else 0} "
        f"expo mean {metrics[name]['exposure']['mean']*100:.1f}% "
        f"peak {metrics[name]['exposure']['peak']*100:.1f}% "
        f"turn {metrics[name]['turnover']['sell_over_mean_equity']:.2f}x "
        f"fees {metrics[name]['total_fees']:.0f} fills {res.fills.height} "
        f"trig {metrics[name]['reasons_provider']} "
        f"done {metrics[name]['reasons_completed']}")

i_sd, i_sv = ideal.sessions, ideal.equity
metrics["IDEAL-bin"] = {
    "net_cagr": cagr_from_equity(i_sd, i_sv),
    "max_drawdown": mdd_from_equity(i_sv),
    "net_by_year": {int(k): v for k, v in
                    year_returns(i_sd, i_sv).items()},
    "drawdown": drawdown_spans(i_sd, i_sv),
    "n_fills": None, "final_equity": i_sv[-1], "total_fees": None}

# FEE layer: gross-of-fee equity path for FULL-bin
full = results["FULL-bin"]["res"]
fills_sorted = full.fills.sort(["date"])
cum_fee: list[tuple[date, float]] = []
run_f = 0.0
for r in fills_sorted.iter_rows(named=True):
    run_f += float(r["fees_total"])
    cum_fee.append((r["date"], run_f))
fee_by_date = {d: f for d, f in cum_fee}
sd = full.daily["date"].to_list()
sv = full.daily["equity"].to_list()
gross = []
acc = 0.0
fi = 0
for d, e in zip(sd, sv):
    while fi < len(cum_fee) and cum_fee[fi][0] <= d:
        acc = cum_fee[fi][1]
        fi += 1
    gross.append(e + acc)
metrics["FEE"] = {
    "net_cagr_gross_of_fees": cagr_from_equity(sd, gross),
    "net_cagr": metrics["FULL-bin"]["net_cagr"],
    "max_drawdown": mdd_from_equity(gross)}

layers = {
    "signal_C1C2": metrics["FULL-bin"]["net_cagr"]
    - metrics["SIG-old"]["net_cagr"],
    "objective_reg_vs_bin": metrics["SIG-reg"]["net_cagr"]
    - metrics["FULL-bin"]["net_cagr"],
    "legal_entry_friction": metrics["IDEAL-bin"]["net_cagr"]
    - metrics["FULL-bin"]["net_cagr"],
    "fees_drag": metrics["FEE"]["net_cagr_gross_of_fees"]
    - metrics["FULL-bin"]["net_cagr"],
    "single_name_exits": metrics["FULL-bin"]["net_cagr"]
    - metrics["NOSNR-bin"]["net_cagr"],
    "account_overlay": metrics["FULL-bin"]["net_cagr"]
    - metrics["NOACCT-bin"]["net_cagr"],
}
log(f"  five layers (CAGR pp): "
    + " ".join(f"{k}={v*100:+.2f}" for k, v in layers.items()))

# === 9. outputs =============================================================
out_dir = RUN_DIR / "outputs"
out_dir.mkdir(parents=True, exist_ok=True)
for name, *_ in CURVES:
    res = results[name]["res"]
    tag = name.replace("/", "_")
    res.fills.write_parquet(out_dir / f"{tag}_fills.parquet")
    res.events.write_parquet(out_dir / f"{tag}_events.parquet")
    res.daily.write_parquet(out_dir / f"{tag}_daily_equity.parquet")
    res.clips_final.write_parquet(out_dir / f"{tag}_clips_final.parquet")
pl.DataFrame({"date": sd, "gross_equity": gross}).write_csv(
    out_dir / "FULL-bin_gross_equity.csv")
for name, *_ in CURVES:
    rows_log = results[name]["pack"]["reasons"]
    pl.DataFrame(rows_log, schema={"day": pl.String, "sess": pl.String,
                                   "symbol": pl.String,
                                   "reason": pl.String,
                                   "source": pl.String,
                                   "intent": pl.String}).write_csv(
        out_dir / f"{name}_exit_reason_log.csv")

SELF_SHA_END = sha256_file(SELF_PY)
if SELF_SHA_END != SELF_SHA_START:
    _fail("runner script changed during execution -- archived != executed")

manifest = {
    "run_id": RUN_DIR.name,
    "experiment_id": "exp-20260921-baseline-rebuild",
    "status": "completed",
    "started_at_utc": T0_WALL.isoformat(),
    "ended_at_utc": datetime.now(timezone.utc).isoformat(),
    "wall_seconds": time.perf_counter() - T0,
    "command": [sys.executable,
                f"artifacts/runs/{RUN_DIR.name}/tmp/runner_replay.py"],
    "runner_self": {"sha256_at_start": SELF_SHA_START,
                    "sha256_at_end": SELF_SHA_END,
                    "note": "the archived tmp/runner_replay.py IS the "
                            "executed file; edit-breaking is fail-closed"},
    "git": {"head": GIT_HEAD, "branch": GIT_BRANCH,
            "dirty_untracked_lines": len(
                [l for l in GIT_PORCELAIN.splitlines() if l.strip()]),
            "porcelain_head": GIT_PORCELAIN.splitlines()[:12],
            "committed": False,
            "note": "working tree carries this remediation round's "
                    "uncommitted changes; module pins below pin the "
                    "executed bytes regardless of git state"},
    "dependencies": {"python": sys.version.split()[0], **DEPS},
    "peak_memory_mb": psutil.Process().memory_info().peak_wset / (1 << 20),
    "account": {"initial_cash": INITIAL_CASH, "legs": "stocks+cash "
                "(no ETF, cash earns nothing)"},
    "engine": {"sha256_at_start": engine_got,
               "sha256_at_end": sha256_file(ENGINE_PY)},
    "exit_semantics_v4": [
        "stop/protection whole exits: frozen-source events, intent=risk, "
        "K=3 fallback arms (v3 defect: source=day reset the streak daily)",
        "take_half/clear: intent=profit -- expire each half-day, module "
        "re-issue keeps the leg, NO open-market fallback (v3 wrongly gave "
        "profit orders the risk fallback)",
        "symbols leaving the ledger purge module state (stale-event fix)",
        "NOSNR control arm verified bit-identical to v3"],
    "nosnr_bit_identical_v3": nosnr_identical,
    "pins": pins,
    "module_pins": {
        name: sha256_file(ROOT / rel) for name, rel in [
            ("single_name_rules", "src/quant/research/single_name_rules.py"),
            ("fixed_scheme_lib", "src/quant/research/fixed_scheme_lib.py"),
            ("risk_overlay_runner", "src/quant/research/risk_overlay_runner.py"),
            ("p2r16_trend_dispersion",
             "src/quant/research/p2r16_trend_dispersion.py"),
            ("alpha158_ml", "src/quant/research/alpha158_ml.py")]},
    "environment": {"python": sys.version.split()[0],
                    "platform": sys.platform},
    "seeds": {"lightgbm": "fixed random_state=7 in the training run "
                          "(ml_scores inputs are frozen files here)",
              "engine": "deterministic, no RNG"},
    "curves": [c[0] for c in CURVES] + ["IDEAL-bin", "FEE"],
    "metrics": metrics,
    "five_layers_cagr_pp": {k: v * 100 for k, v in layers.items()},
    "known_simplifications": [
        "IDEAL-bin uses fractional next-open execution with no lot / "
        "limit / suspension / T+1 constraints (B1(m) precedent); its fee "
        "schedule is the literal STOCK_FEE_SCHEDULE with the 5-CNY minimum",
        "G0 marks now take the session-aware price (audit Q2 fix); the "
        "archived G0/G1 replays marked am decisions at the same-day close",
        "engine FIFO consumption means a partial sell may eat a different "
        "lot than the per-clip intent; totals match the frozen absolute "
        "target, surviving lot composition can differ (disclosed)"],
    "outputs": {p.relative_to(RUN_DIR).as_posix(): sha256_file(p)
                for p in sorted(out_dir.rglob("*")) if p.is_file()},
}
(RUN_DIR / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=1, default=str),
    encoding="utf-8")
log(f"== done; wall {time.perf_counter()-T0:.0f}s; "
    f"peak {manifest['peak_memory_mb']:.0f}MB ==")
_logf.close()
