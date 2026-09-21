"""Shared components for the fixed-scheme experiment (prereg 2026-09-21).

Everything here is parameter-frozen by docs/research/exp-20260921-fixed-scheme-prereg.md:
ATR20 stops, the defensive leg (monthly rebalance + 60d/10% drawdown exit),
the G1 market-trend gate (CSI300 T200, monthly), a constant-E overlay host
with the DynamicOverlayHost step contract, defensive-leg benchmark monthly
returns (adj-factor based) and the 40/60 monthly mix helper.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Mapping

import numpy as np
import polars as pl

from quant.research.single_name_rules import LOT

DEFENSE_SYMBOLS = ("sh.511010", "sh.518880", "sz.159934")
DEFENSE_BUDGET = 0.60          # total defensive weight
DEFENSE_CAP = 0.25             # single-name cap applies to ETFs too
DEFENSE_EXIT_LOOKBACK = 60     # sessions
DEFENSE_EXIT_DD = 0.10         # drawdown from the 60-session high
ATTACK_BUDGET_SEAT = 0.10      # per seat: 40% / 4 seats
ATTACK_TOL = 0.002
E_OFF = 0.40                   # overlay reduced exposure (G1/G2/G3)
ETF_PRIORITY_BASE = 400_000    # defensive rows: entries/rebalances
ETF_EXIT_PRIORITY = 450_000    # defensive drawdown exits


# ---------------------------------------------------------------------------
# ATR20 table
# ---------------------------------------------------------------------------
class ATRTable:
    """symbol -> (dint ndarray, atr ndarray); ATR[i] covers TR mean of the
    20 sessions STRICTLY BEFORE dint[i] (no same-day lookahead: a clip
    acquired on day d uses volatility known at the previous close)."""

    def __init__(self, data: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
        self._data = data

    def atr(self, symbol: str, day: date) -> float:
        arr = self._data.get(symbol)
        if arr is None:
            raise KeyError(f"ATR20: unknown symbol {symbol}")
        dint, atr = arr
        i = int(np.searchsorted(dint, day.year * 10_000 + day.month * 100
                                + day.day)) - 1
        if i < 0 or not np.isfinite(atr[i]):
            raise KeyError(f"ATR20: no value for {symbol} at/before {day}")
        return float(atr[i])


def build_atr20(daily: pl.DataFrame, window: int = 20) -> ATRTable:
    daily = daily.sort("symbol", "date")
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for (sym,), g in daily.partition_by("symbol", as_dict=True).items():
        d = g["date"]
        high = g["high"].to_numpy().astype(np.float64)
        low = g["low"].to_numpy().astype(np.float64)
        close = g["close"].to_numpy().astype(np.float64)
        prev_close = np.concatenate([[np.nan], close[:-1]])
        tr = np.maximum(high - low,
                        np.maximum(np.abs(high - prev_close),
                                   np.abs(low - prev_close)))
        # atr[i] = mean of tr[i-window : i]  (strictly before i)
        c = np.cumsum(np.nan_to_num(tr, nan=0.0))
        atr = np.full(len(tr), np.nan)
        if len(tr) > window:
            idx = np.arange(window, len(tr))
            atr[window:] = (c[idx - 1]
                            - np.concatenate([[0.0], c])[idx - window]) / window
        atr[: window + 1] = np.nan   # tr[0] has no prev close; full window only
        dint = (d.dt.year().cast(pl.Int64) * 10_000
                + d.dt.month().cast(pl.Int64) * 100
                + d.dt.day().cast(pl.Int64)).to_numpy().astype(np.int64)
        out[str(sym)] = (dint, atr)
    return ATRTable(out)


# ---------------------------------------------------------------------------
# Defensive leg
# ---------------------------------------------------------------------------
class DefensiveLeg:
    """Monthly rebalance to equal defensive weights + 60-session/10%
    drawdown exit (no re-entry). decide() is called at pm decision points
    only; ETF intents live on the pm-only routing."""

    def __init__(self, close_at: Callable[[str, date], float | None],
                 high60_at: Callable[[str, date], float | None]) -> None:
        self._close_at = close_at
        self._high60_at = high60_at
        self.active: set[str] = set(DEFENSE_SYMBOLS)
        self.exits: list[dict] = []

    def target_weight(self) -> float:
        n = len(self.active)
        return min(DEFENSE_BUDGET / n, DEFENSE_CAP) if n else 0.0

    def decide(self, day: date, ledger: Mapping, *, rebalance: bool,
               equity: float) -> list[dict]:
        rows: list[dict] = []
        held = {str(p["symbol"]): p for p in ledger["positions"]}
        px_of: dict[str, float] = {}
        # 1. drawdown exits (checked at every pm decision point)
        for sym in sorted(self.active):
            px = self._close_at(sym, day)
            hi = self._high60_at(sym, day)
            if px is None or hi is None or hi <= 0:
                continue
            px_of[sym] = px
            if px <= hi * (1.0 - DEFENSE_EXIT_DD):
                self.active.discard(sym)
                self.exits.append({"symbol": sym, "date": day.isoformat(),
                                   "close": px, "high60": hi})
                if sym in held:
                    rows.append(self._row(sym, "sell", day, target_weight=None,
                                          priority=ETF_EXIT_PRIORITY))
        # 2. monthly rebalance to equal weights among active legs
        if rebalance:
            tw = self.target_weight()
            for sym in sorted(self.active):
                px = px_of.get(sym) or self._close_at(sym, day)
                if px is None or equity <= 0:
                    continue
                pos = held.get(sym)
                weight = (sum(int(c["shares"]) for c in pos["clips"]) * px
                          / equity) if pos else 0.0
                if weight < tw - ATTACK_TOL:
                    rows.append(self._row(sym, "buy", day, target_weight=tw,
                                          priority=ETF_PRIORITY_BASE))
                elif weight > tw + ATTACK_TOL and pos is not None:
                    rows.append(self._row(sym, "sell", day, target_weight=tw,
                                          priority=ETF_PRIORITY_BASE))
        return rows

    @staticmethod
    def _row(symbol: str, side: str, day: date, *, target_weight, priority):
        return {"symbol": symbol, "side": side,
                # buys are plain entries (intent must be empty); drawdown
                # exits are risk-reduction (K=3 fallback); rebalance sells
                # are profit-class trim orders
                "intent": ("" if side == "buy"
                           else "risk" if target_weight is None else "profit"),
                "decision_date": day, "decision_session": "pm",
                "source_signal": day, "priority": priority,
                "expiry_date": None, "target_weight": target_weight,
                "target_notional": None}


# ---------------------------------------------------------------------------
# G1 market-trend gate (CSI300 T200, monthly)
# ---------------------------------------------------------------------------
def t200_monthly(index_csv: Path, cal: list[date],
                 sig_days: list[date], window: int = 200) -> dict[date, float]:
    """E for each signal day: 1.0 if index close >= SMA200 else E_OFF."""
    idx = pl.read_csv(index_csv)
    idx = idx.with_columns(
        (pl.col("trade_date").cast(pl.Utf8).str.slice(0, 4).cast(pl.Int32)
         .alias("y"),
         pl.col("trade_date").cast(pl.Utf8).str.slice(4, 2).cast(pl.Int32)
         .alias("m"),
         pl.col("trade_date").cast(pl.Utf8).str.slice(6, 2).cast(pl.Int32)
         .alias("d")))
    idx = idx.with_columns(
        pl.date("y", "m", "d").alias("date")).sort("date")
    dint = (idx["date"].dt.year().cast(pl.Int64) * 10_000
            + idx["date"].dt.month().cast(pl.Int64) * 100
            + idx["date"].dt.day().cast(pl.Int64)).to_numpy()
    close = idx["close"].to_numpy().astype(np.float64)
    sma = np.full(len(close), np.nan)
    c = np.cumsum(close)
    for i in range(window - 1, len(close)):
        sma[i] = (c[i] - (c[i - window] if i >= window else 0.0)) / window
    out: dict[date, float] = {}
    for t in sig_days:
        key = t.year * 10_000 + t.month * 100 + t.day
        i = int(np.searchsorted(dint, key, side="right")) - 1
        if i < 0 or not np.isfinite(sma[i]):
            out[t] = 1.0     # insufficient history: stay invested (G1 note)
            continue
        out[t] = 1.0 if close[i] >= sma[i] else E_OFF
    return out


# ---------------------------------------------------------------------------
# Constant-E overlay host (G0 / G1) -- DynamicOverlayHost step contract
# ---------------------------------------------------------------------------
@dataclass
class ConstantStep:
    decision_time: str
    e_ratio: float
    target_weight: float
    rows: tuple[dict, ...] = field(default_factory=tuple)
    entries: tuple[str, ...] = field(default_factory=tuple)
    trims: tuple[str, ...] = field(default_factory=tuple)
    topups: tuple[str, ...] = field(default_factory=tuple)
    risk_state: str = "normal"
    action: str = ""


class ConstantOverlayHost:
    """E-table-driven overlay: entries at target, trim/topup around the
    E-scaled seat weight. Shares the DynamicOverlayHost semantics minus the
    confirm/cooldown machinery (E is observed monthly, not event-triggered)."""

    def __init__(self, e_table: Mapping[date, float],
                 marks: Callable[[str, date], float | None],
                 base_seat_weight: float = ATTACK_BUDGET_SEAT,
                 tolerance: float = ATTACK_TOL) -> None:
        self.e_table = dict(e_table)
        self._marks = marks
        self.base_seat_weight = float(base_seat_weight)
        self.tolerance = float(tolerance)
        self.steps: list[ConstantStep] = []

    def step(self, ledger: Mapping, *, members: Iterable[str],
             rank_of: Mapping[str, int], source_signal: date,
             expiry: date | None) -> ConstantStep:
        equity = float(ledger["equity_snapshot"])
        e = float(self.e_table.get(source_signal, 1.0))
        target = self.base_seat_weight * e
        held = {str(p["symbol"]): int(p["shares"])
                for p in ledger["positions"] if int(p["shares"]) > 0}
        seats = {str(s) for s in members}
        rows: list[dict] = []
        entries: list[str] = []
        trims: list[str] = []
        topups: list[str] = []
        if e > 0:
            for symbol in sorted(seats - set(held)):
                rows.append(_seat_row(symbol, "buy", ledger["date"],
                                      ledger["session"], source_signal,
                                      rank_of[symbol], expiry,
                                      target_weight=target))
                entries.append(symbol)
        for symbol in sorted(set(held) & seats):
            mark = self._marks(symbol, ledger["date"])
            if mark is None:
                continue
            weight = held[symbol] * mark / equity if equity > 0 else 0.0
            if e < 1.0 and weight > target + self.tolerance:
                rows.append(_seat_row(symbol, "sell", ledger["date"],
                                      ledger["session"], source_signal,
                                      rank_of[symbol], expiry,
                                      target_weight=target, intent="risk"))
                trims.append(symbol)
            elif e >= 1.0 and weight < target - self.tolerance:
                rows.append(_seat_row(symbol, "buy", ledger["date"],
                                      ledger["session"], source_signal,
                                      rank_of[symbol], expiry,
                                      target_weight=target))
                topups.append(symbol)
        st = ConstantStep(
            decision_time=f"{ledger['date']} {ledger['session']}",
            e_ratio=e / 1.0, target_weight=target, rows=tuple(rows),
            entries=tuple(entries), trims=tuple(trims),
            topups=tuple(topups),
            risk_state="reduced" if e < 1.0 else "normal")
        self.steps.append(st)
        return st


def _seat_row(symbol: str, side: str, day, session, source, priority, expiry,
              *, target_weight, intent: str = "") -> dict:
    return {"symbol": symbol, "side": side, "intent": intent,
            "decision_date": day, "decision_session": session,
            "source_signal": source, "priority": int(priority),
            "expiry_date": expiry, "target_weight": target_weight,
            "target_notional": None}


# ---------------------------------------------------------------------------
# Defensive benchmark returns + 40/60 monthly mix
# ---------------------------------------------------------------------------
def defensive_month_returns(etf_daily: pl.DataFrame, fund_adj_dir: Path,
                            symbols: tuple[str, ...] = DEFENSE_SYMBOLS,
) -> dict[str, float]:
    """Equal-weight monthly returns of the defensive legs (adj-factor
    returns, monthly rebalance). Key 'YYYY-MM'."""
    factors: dict[str, dict[int, float]] = {}
    for sym in symbols:
        # file naming: chunk_511010.SH.csv / chunk_159934.SZ.csv
        code = sym.split(".")[1]
        p = fund_adj_dir / f"chunk_{code}.{sym.split('.')[0].upper()}.csv"
        rows = list(csv.DictReader(p.open(encoding="utf-8", newline="")))
        factors[sym] = {int(r["trade_date"]): float(r["adj_factor"])
                        for r in rows}
    out: dict[str, dict] = {}
    frame = (etf_daily.filter(pl.col("symbol").is_in(list(symbols)))
             .sort("symbol", "date"))
    for (sym,), g in frame.partition_by("symbol", as_dict=True).items():
        fac = pl.DataFrame({
            "dint": list(factors[str(sym)].keys()),
            "f": list(factors[str(sym)].values())}).sort("dint")
        # adj price = close * factor(at that date)
        gd = (g.with_columns(
            (pl.col("date").dt.year().cast(pl.Int64) * 10_000
             + pl.col("date").dt.month().cast(pl.Int64) * 100
             + pl.col("date").dt.day().cast(pl.Int64)).alias("dint"))
            .join(fac, on="dint", how="left")
            .with_columns((pl.col("close") * pl.col("f")).alias("adj")))
        monthly = (gd.group_by(
            pl.col("date").dt.strftime("%Y-%m").alias("ym"))
            .agg(pl.col("date").max().alias("d1"),
                 pl.col("adj").last().alias("adj_end")).sort("d1"))
        ends = monthly["d1"].to_list()
        series = [v for v in monthly["adj_end"].to_list() if v is not None]
        rets = [series[i] / series[i - 1] - 1.0
                for i in range(1, len(series)) if series[i - 1] > 0]
        keys = [e.strftime("%Y-%m") for e in ends][1:len(series)]
        for k, r_ in zip(keys, rets):
            out.setdefault(k, {})[str(sym)] = r_
    merged: dict[str, float] = {}
    for k, per in out.items():
        merged[k] = float(np.mean(list(per.values())))
    return merged


def monthly_returns_from_equity(sessions: list[date],
                                equity: list[float]) -> dict[str, float]:
    last: dict[str, tuple[date, float]] = {}
    for d, e in zip(sessions, equity):
        last[d.strftime("%Y-%m")] = (d, e)
    keys = sorted(last)
    rets: dict[str, float] = {}
    for i in range(1, len(keys)):
        _, e0 = last[keys[i - 1]]
        _, e1 = last[keys[i]]
        if e0 > 0:
            rets[keys[i]] = e1 / e0 - 1.0
    return rets


def mix_from_monthly(stock_m: Mapping[str, float],
                     def_m: Mapping[str, float],
                     w_stock: float = 0.4) -> dict[str, float]:
    return {k: w_stock * stock_m.get(k, 0.0) + (1 - w_stock) * def_m.get(k, 0.0)
            for k in sorted(set(stock_m) | set(def_m))}


def cagr_from_monthly(monthly: Mapping[str, float]) -> float:
    if not monthly:
        return float("nan")
    growth = 1.0
    for k in sorted(monthly):
        growth *= 1.0 + monthly[k]
    n_years = len(monthly) / 12.0
    return growth ** (1.0 / n_years) - 1.0 if n_years > 0 else float("nan")


def yearly_from_monthly(monthly: Mapping[str, float]) -> dict[int, float]:
    per: dict[int, float] = {}
    for k in sorted(monthly):
        y = int(k[:4])
        per.setdefault(y, 1.0)
        per[y] *= 1.0 + monthly[k]
    return {y: v - 1.0 for y, v in per.items()}


def mdd_from_monthly(monthly: Mapping[str, float]) -> float:
    eq, peak, mdd = 1.0, 1.0, 0.0
    for k in sorted(monthly):
        eq *= 1.0 + monthly[k]
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    return mdd
