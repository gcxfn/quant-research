# -*- coding: utf-8 -*-
"""Phase-B candidate families: signal construction + engine provider.

Prereg: docs/research/stock_event_research_prereg.md (frozen 2026-09-21
before any phase-B Dev run; 22-attempt budget).  This module holds ALL
phase-B signal logic so every arm (main / perturbation / random control /
ablation) is a parameterisation of the same audited code path.

Families
--------
A1 breakout participation / A2 pullback participation
    Eligibility is frozen at each month-end cross-section over the R16
    executable pool: 60-own-session return cross-section quantile >=
    ``rs_quantile`` AND mean-TR(10)/mean-TR(60) <= ``vc_ratio``.  Daily
    triggers are detected on COMPLETED daily closes only; a trigger
    observed at day T's close is issued at T's pm decision and may fill
    from the next half-day (engine contract: pm orders execute next
    morning).  Entries chase at most ``trigger_close * (1 + CHASE)`` --
    the registered x1.01 cap is enforced at issuance and at every
    re-issue (the provider stops re-issuing once the decision-point
    anchor runs above the cap).  A pending entry lapses after
    ``ENTRY_TTL_SESSIONS`` half-day execution opportunities without a
    fill, or on the registered close-based invalidation.  At most one
    trigger per symbol per month (first wins).

B1 verifiable forecast revision / B2 improvement + price confirmation
    Conservative clock: an announcement becomes visible strictly after
    its ann_date close, so the earliest decision point is the NEXT
    trading day's 11:30 (am) session (prereg section 4); B2 additionally
    waits ``confirm_sessions`` own trading sessions and decides at that
    day's pm.  B positions exit at ``B_HOLD_SESSIONS`` own trading
    sessions after the fill's earliest live clip (profit-class
    whole-exit event re-issued until done -- no K=3 fallback: a horizon
    exit is not a risk-reduction order).

Frozen interpretive choices (prereg left open; recorded here and in
every run manifest):
* TYPE_ORDER -- a total "goodness" order over forecast types for B1
  strict-improvement detection (worst -> best:
  首亏 续亏 预减 略减 不确定 续盈 略增 扭亏 预增).
* IMPROVE_CODES -- B2's "improvement" primary_code set: the schema's
  favourable-direction codes PLUS impairment (the prereg parenthetical
  "impairment 方向为正类" follows the T1 empirical finding; the schema
  alone files impairment under the adverse direction).
* A1 volume condition uses the mean of the PRIOR 20 sessions excluding
  the trigger day; the 60-day high is strictly above the prior 60
  closes; the 20-day MA includes the day itself.
* B1 compares each announcement to the immediately previous version by
  (ann_date, update_flag); same-day version pairs never fire.

Provider wiring mirrors the baseline replay: SingleNameRules (v4 exit
semantics) decides per-clip exits; DynamicOverlayHost manages the D3
trim/top-up legs for HELD symbols only (a stable month-end anchor keeps
trim streaks from resetting daily); this module issues entry rows
itself, gated on the host's latest risk state allowing new attack
entries.  Seats = held + pending entries, hard-capped at MAX_SEATS.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from typing import Callable, Mapping, Sequence

import numpy as np

import quant.portfolio.risk_overlay as ro

# --- frozen dictionaries -----------------------------------------------------

TYPE_ORDER: dict[str, int] = {
    "首亏": -4, "续亏": -3, "预减": -2, "略减": -1, "不确定": 0,
    "续盈": 1, "略增": 2, "扭亏": 3, "预增": 4,
}

IMPROVE_CODES: frozenset[str] = frozenset({
    "demand_up", "price_up", "orders", "cost_down", "core_ops",
    "ma_restructuring", "non_recurring", "impairment"})

SEAT_WEIGHT = 0.10
MAX_SEATS = 4
ENTRY_TTL_SESSIONS = 3
CHASE = 0.01
BREAKOUT_LOOKBACK = 60
VOL_MULT = 0.8
MA_WINDOW = 20
RS_WINDOW = 60
VC_SHORT, VC_LONG = 10, 60
TRAIL_ATR_MULT = 1.0
B_HOLD_SESSIONS = 20
TIME_EXIT_PRIORITY = 500_002       # after SingleNameRules (500_001)


@dataclass(frozen=True)
class FamilyParams:
    """One arm's frozen parameters (main / perturbation / ablation)."""

    family: str                       # 'A1' | 'A2' | 'B1' | 'B2' | 'RND'
    label: str = ""
    rs_quantile: float = 0.80
    vc_ratio: float = 0.70
    use_rs_filter: bool = True        # ablation: drop the rel-strength leg
    pullback_days: int = 10           # A2(1) uses 15
    b1_floor_must_rise: bool = False  # perturbation B1(1)
    b1_cooldown: int | None = None    # perturbation B1(2), own sessions
    confirm_sessions: int = 5         # perturbation B2(1) uses 10
    b2_types: tuple[str, ...] = ("预增", "扭亏")   # B2(2) narrows to 预增
    use_price_confirm: bool = True    # ablation: drop the confirmation leg
    rnd_seed: int | None = None

    @property
    def is_b(self) -> bool:
        return self.family in ("B1", "B2")

    def describe(self) -> str:
        bits = [self.family]
        if self.label:
            bits.append(self.label)
        if self.vc_ratio != 0.70:
            bits.append(f"vc={self.vc_ratio}")
        if not self.use_rs_filter:
            bits.append("no-rs")
        if self.pullback_days != 10:
            bits.append(f"pb={self.pullback_days}")
        if self.b1_floor_must_rise:
            bits.append("floor-rise")
        if self.b1_cooldown is not None:
            bits.append(f"cool={self.b1_cooldown}")
        if self.confirm_sessions != 5:
            bits.append(f"cf={self.confirm_sessions}")
        if self.b2_types != ("预增", "扭亏"):
            bits.append("types=" + "+".join(self.b2_types))
        if not self.use_price_confirm:
            bits.append("no-confirm")
        if self.rnd_seed is not None:
            bits.append(f"seed={self.rnd_seed}")
        return "/".join(bits)


# --- per-symbol daily panel --------------------------------------------------

class SymbolSeries:
    """Own-session arrays for one symbol (completed daily bars only)."""

    __slots__ = ("symbol", "dates", "dints", "close", "high", "low",
                 "volume", "ma20", "mx60_prior", "vol20_prior",
                 "atr10", "atr60", "ret60")

    def __init__(self, symbol: str, d: Sequence[date], close: np.ndarray,
                 high: np.ndarray, low: np.ndarray, volume: np.ndarray):
        self.symbol = symbol
        self.dates = list(d)
        self.dints = np.array(
            [x.year * 10000 + x.month * 100 + x.day for x in self.dates],
            dtype=np.int64)
        self.close = close
        self.high = high
        self.low = low
        self.volume = volume
        n = len(close)
        prev_close = np.concatenate(([close[0]], close[:-1]))
        tr = np.maximum.reduce([
            high - low, np.abs(high - prev_close),
            np.abs(low - prev_close)])
        self.ma20 = _roll_mean(close, MA_WINDOW)
        self.mx60_prior = _roll_max_prior(close, BREAKOUT_LOOKBACK)
        self.vol20_prior = _roll_mean_prior(volume, MA_WINDOW)
        self.atr10 = _roll_mean(tr, VC_SHORT)
        self.atr60 = _roll_mean(tr, VC_LONG)
        self.ret60 = np.full(n, np.nan)
        if n > RS_WINDOW:
            self.ret60[RS_WINDOW:] = (
                close[RS_WINDOW:] / close[:-RS_WINDOW] - 1.0)

    def idx_of(self, d: date) -> int:
        di = d.year * 10000 + d.month * 100 + d.day
        i = int(np.searchsorted(self.dints, di))
        return i if i < len(self.dints) and int(self.dints[i]) == di else -1

    def idx_le(self, d: date) -> int:
        di = d.year * 10000 + d.month * 100 + d.day
        return int(np.searchsorted(self.dints, di, side="right")) - 1

    def idx_lt(self, d: date) -> int:
        di = d.year * 10000 + d.month * 100 + d.day
        return int(np.searchsorted(self.dints, di, side="left")) - 1


def _roll_mean(a: np.ndarray, w: int) -> np.ndarray:
    """Mean of the w sessions ending AT index i (NaN while warming up)."""
    c = np.cumsum(np.insert(a.astype(np.float64), 0, 0.0))
    out = np.full(len(a), np.nan)
    if len(a) >= w:
        out[w - 1:] = (c[w:] - c[:-w]) / w
    return out


def _roll_mean_prior(a: np.ndarray, w: int) -> np.ndarray:
    """Mean of the w sessions strictly BEFORE index i (NaN while warm)."""
    n = len(a)
    out = np.full(n, np.nan)
    if n >= w + 1:
        c = np.cumsum(np.insert(a.astype(np.float64), 0, 0.0))
        out[w:] = (c[w:n] - c[:n - w]) / w
    return out


def _roll_max_prior(a: np.ndarray, w: int) -> np.ndarray:
    """Max of the w sessions strictly BEFORE index i (NaN while warm)."""
    from numpy.lib.stride_tricks import sliding_window_view
    n = len(a)
    out = np.full(n, np.nan)
    if n > w:
        wins = sliding_window_view(a.astype(np.float64), w)
        # window j covers a[j .. j+w-1]; out[i] needs j = i-w for i in [w, n)
        out[w:] = wins.max(axis=1)[:n - w]
    return out


# --- A-family eligibility + triggers -----------------------------------------

@dataclass
class TriggerEvent:
    symbol: str
    trigger_day: date
    family: str                    # 'A1' | 'A2' | 'RND'
    cap_price: float               # trigger close * (1 + CHASE)
    cancel_level: float            # a completed close below this cancels
    cancel_below_ma: bool = False  # A2: also cancel when close < MA20
    rank_key: float = 0.0          # higher = issued first on slot竞争


def a_family_eligibility(pool: Sequence[str],
                         series: Mapping[str, SymbolSeries], day: date,
                         p: FamilyParams) -> tuple[set[str], dict]:
    rets: list[tuple[str, float]] = []
    vcs: dict[str, float] = {}
    for s in pool:
        ser = series.get(s)
        if ser is None:
            continue
        i = ser.idx_of(day)
        if i < 0 or not np.isfinite(ser.ret60[i]) \
                or not np.isfinite(ser.atr10[i]) \
                or not np.isfinite(ser.atr60[i]) or ser.atr60[i] <= 0:
            continue
        rets.append((s, float(ser.ret60[i])))
        vcs[s] = float(ser.atr10[i]) / float(ser.atr60[i])
    if not rets:
        return set(), {"n_pool": len(pool), "n_data": 0}
    rs_cut = float(np.quantile([r for _, r in rets], p.rs_quantile))
    elig = {s for s, r in rets if r >= rs_cut} if p.use_rs_filter \
        else {s for s, _ in rets}
    elig = {s for s in elig if vcs.get(s, float("inf")) <= p.vc_ratio}
    return elig, {"n_pool": len(pool), "n_data": len(rets),
                  "rs_cut": rs_cut, "n_elig": len(elig)}


def _is_breakout(ser: SymbolSeries, i: int) -> bool:
    return (np.isfinite(ser.mx60_prior[i]) and ser.mx60_prior[i] > 0
            and ser.close[i] > ser.mx60_prior[i]
            and np.isfinite(ser.vol20_prior[i]) and ser.vol20_prior[i] > 0
            and ser.volume[i] >= VOL_MULT * ser.vol20_prior[i])


def scan_a_triggers(pool_by_month: Sequence[tuple[date, Sequence[str]]],
                    series: Mapping[str, SymbolSeries],
                    atr_getter: Callable[[str, date], float],
                    p: FamilyParams) -> list[TriggerEvent]:
    """Scan A1/A2 triggers over each month's eligible set (one trigger
    per symbol per month, first wins).  Uses completed closes only."""
    events: list[TriggerEvent] = []
    for k, (t0, pool) in enumerate(pool_by_month):
        t1 = pool_by_month[k + 1][0] if k + 1 < len(pool_by_month) else None
        elig, _st = a_family_eligibility(pool, series, t0, p)
        for sym in sorted(elig):
            ser = series[sym]
            i0 = ser.idx_le(t0) + 1
            i1 = ser.idx_le(t1) if t1 is not None else len(ser.dates) - 1
            fired = False
            i = i0
            while 0 <= i <= i1 and not fired:
                if not _is_breakout(ser, i):
                    i += 1
                    continue
                lvl = float(ser.close[i])
                atr = float(atr_getter(sym, ser.dates[i]) or 0.0)
                if atr <= 0:
                    i += 1
                    continue
                if p.family == "A1":
                    events.append(TriggerEvent(
                        symbol=sym, trigger_day=ser.dates[i], family="A1",
                        cap_price=lvl * (1 + CHASE),
                        cancel_level=lvl - TRAIL_ATR_MULT * atr,
                        rank_key=float(ser.ret60[i])))
                    fired = True
                else:
                    trig = _a2_after_breakout(
                        ser, i, lvl, atr, p.pullback_days)
                    if trig is not None and trig <= (t1 or ser.dates[-1]) \
                            and ser.idx_le(trig) <= i1:
                        ti = ser.idx_of(trig)
                        events.append(TriggerEvent(
                            symbol=sym, trigger_day=trig, family="A2",
                            cap_price=float(ser.close[ti]) * (1 + CHASE),
                            cancel_level=lvl - TRAIL_ATR_MULT * atr,
                            cancel_below_ma=True,
                            rank_key=float(ser.ret60[ti])))
                        fired = True
                    i += 1
    events.sort(key=lambda e: (e.trigger_day, -e.rank_key, e.symbol))
    return events


def _a2_after_breakout(ser: SymbolSeries, bi: int, lvl: float, atr: float,
                       window: int) -> date | None:
    i = bi + 1
    pulled = False
    while i < len(ser.dates) and i - bi <= window:
        c = float(ser.close[i])
        if not np.isfinite(ser.ma20[i]) or c < float(ser.ma20[i]):
            return None
        if not pulled:
            if lvl - atr <= c <= lvl + atr:
                pulled = True
        elif c > lvl:
            return ser.dates[i]
        i += 1
    return None


def random_month_picks(pool_by_month: Sequence[tuple[date, Sequence[str]]],
                       seed: int,
                       max_seats: int = MAX_SEATS) -> list[TriggerEvent]:
    """Random controls: same seat structure, no signal."""
    rng = np.random.default_rng(seed)
    events: list[TriggerEvent] = []
    for t0, pool in pool_by_month:
        names = sorted(pool)
        if not names:
            continue
        k = min(max_seats, len(names))
        for s in rng.choice(len(names), size=k, replace=False):
            events.append(TriggerEvent(
                symbol=names[int(s)], trigger_day=t0, family="RND",
                cap_price=float("inf"), cancel_level=float("-inf"),
                rank_key=float(t0.toordinal())))
    events.sort(key=lambda e: (e.trigger_day, -e.rank_key, e.symbol))
    return events


# --- B-family events ----------------------------------------------------------

@dataclass(frozen=True)
class BEvent:
    symbol: str
    ann_date: date
    decision_day: date
    decision_sess: str        # 'am' for B1, 'pm' for B2
    kind: str                 # 'B1' | 'B2'
    rank_key: float = 0.0


def b1_revision_events(rows: Sequence[Mapping[str, object]],
                       series: Mapping[str, SymbolSeries],
                       pool_member: Callable[[str, date], bool],
                       trading_day_after: Callable[[date], date],
                       p: FamilyParams) -> list[BEvent]:
    """B1: verifiable upward revision of the same (ts_code, end_date)."""
    groups: dict[tuple[str, str], list[Mapping[str, object]]] = {}
    for r in rows:
        groups.setdefault((str(r["symbol"]), str(r["end_date"])), []).append(r)
    events: list[BEvent] = []
    last_fire: dict[str, date] = {}
    for (_sym, _ed), versions in sorted(groups.items()):
        versions = sorted(
            versions, key=lambda r: (str(r["ann_date"]),
                                     str(r.get("update_flag") or "0")))
        for prev, cur in zip(versions, versions[1:]):
            a_prev, a_cur = str(prev["ann_date"]), str(cur["ann_date"])
            if a_prev >= a_cur:
                continue
            d_cur = date(int(a_cur[:4]), int(a_cur[4:6]), int(a_cur[6:8]))
            improved = (TYPE_ORDER.get(str(cur["type"]), 0)
                        > TYPE_ORDER.get(str(prev["type"]), 0))
            med_floor_ok = False
            try:
                pmin, pmax = (float(prev["net_profit_min"]),
                              float(prev["net_profit_max"]))
                cmin, cmax = (float(cur["net_profit_min"]),
                              float(cur["net_profit_max"]))
                assert pmax > pmin and cmax > cmin
            except (TypeError, ValueError, AssertionError, KeyError):
                pmin = pmax = cmin = cmax = None
            if None not in (pmin, pmax, cmin, cmax):
                med_prev, med_cur = (pmin + pmax) / 2.0, (cmin + cmax) / 2.0
                floor_ok = (cmin > pmin if p.b1_floor_must_rise
                            else cmin >= pmin)
                med_floor_ok = med_cur > med_prev and floor_ok
            if not (improved or med_floor_ok):
                continue
            sym = str(cur["symbol"])
            if not pool_member(sym, d_cur):
                continue
            if p.b1_cooldown is not None:
                ser = series.get(sym)
                prev_fire = last_fire.get(sym)
                if prev_fire is not None and ser is not None:
                    dist = ser.idx_le(d_cur) - ser.idx_le(prev_fire)
                    if 0 <= dist < p.b1_cooldown:
                        continue
            last_fire[sym] = d_cur
            events.append(BEvent(
                symbol=sym, ann_date=d_cur,
                decision_day=trading_day_after(d_cur), decision_sess="am",
                kind="B1", rank_key=float(d_cur.toordinal())))
    events.sort(key=lambda e: (e.decision_day, -e.rank_key, e.symbol))
    return events


def b2_announcement_events(rows: Sequence[Mapping[str, object]],
                           series: Mapping[str, SymbolSeries],
                           pool_by_month: Sequence[tuple[date, Sequence[str]]],
                           pool_member: Callable[[str, date], bool],
                           p: FamilyParams) -> list[BEvent]:
    """B2: type in b2_types + improvement attribution + price confirmation
    (own confirm-window return > 0 and > the pool median of the same
    measure; the pool active at the confirmation day)."""
    month_ends = [t for t, _ in pool_by_month]
    pool_at = {t: list(pool) for t, pool in pool_by_month}
    events: list[BEvent] = []
    for r in rows:
        sym = str(r["symbol"])
        if str(r["type"]) not in p.b2_types:
            continue
        if str(r.get("primary_code")) not in IMPROVE_CODES:
            continue
        a = str(r["ann_date"])
        ann = date(int(a[:4]), int(a[4:6]), int(a[6:8]))
        if not pool_member(sym, ann):
            continue
        ser = series.get(sym)
        if ser is None:
            continue
        ai = ser.idx_le(ann)
        if ai < 0:
            continue
        if not p.use_price_confirm:
            ci = min(ai + 1, len(ser.dates) - 1)
            events.append(BEvent(
                symbol=sym, ann_date=ann, decision_day=ser.dates[ci],
                decision_sess="pm", kind="B2",
                rank_key=float(ann.toordinal())))
            continue
        ci = ai + p.confirm_sessions
        if ci >= len(ser.dates):
            continue
        cday = ser.dates[ci]
        ret = float(ser.close[ci]) / float(ser.close[ai]) - 1.0
        if ret <= 0:
            continue
        j = bisect_right(month_ends, cday)
        t_pool = month_ends[max(j - 1, 0)]
        pool_rets: list[float] = []
        for s2 in pool_at[t_pool]:
            s2r = series.get(s2)
            if s2r is None:
                continue
            a2i = s2r.idx_le(ann)
            if a2i < 0:
                continue
            c2i = a2i + p.confirm_sessions
            if c2i < len(s2r.dates) and s2r.dates[c2i] <= cday:
                pool_rets.append(
                    float(s2r.close[c2i]) / float(s2r.close[a2i]) - 1.0)
        if len(pool_rets) < 20 or ret <= float(np.median(pool_rets)):
            continue
        events.append(BEvent(
            symbol=sym, ann_date=ann, decision_day=cday,
            decision_sess="pm", kind="B2", rank_key=float(ann.toordinal())))
    events.sort(key=lambda e: (e.decision_day, -e.rank_key, e.symbol))
    return events


def _attack_entries_allowed(risk_state_value: str) -> bool:
    """DynamicStep carries the state as its .value string; map it back to
    the enum the gate expects.  Unknown states fail CLOSED."""
    try:
        return bool(ro.attack_entry_allowed(ro.OverlayState(
            str(risk_state_value))))
    except ValueError:
        return False


# --- engine provider ----------------------------------------------------------

class EventFamilyProvider:
    """Dynamic intent provider for one phase-B arm.

    Row classes per decision point:
      * SingleNameRules exit rows (module owns per-clip risk exits);
      * B-family time-exit rows (profit-class whole exit, frozen source);
      * DynamicOverlayHost trim/top-up rows for HELD symbols only;
      * entry rows issued here (re-issued each point while pending),
        gated on the host's latest risk state allowing attack entries.
    """

    def __init__(self, params: FamilyParams,
                 events: Sequence[TriggerEvent | BEvent],
                 series: Mapping[str, SymbolSeries],
                 host, snr, price_at: Callable[[str, date, str], float | None],
                 month_ends: Sequence[date],
                 session_index: Mapping[tuple[date, str], int]):
        self.p = params
        self.events = list(events)
        self.series = series
        self.host = host
        self.snr = snr
        self.price_at = price_at
        self.month_ends = sorted(month_ends)
        self.session_index = dict(session_index)
        self.events_at: dict[tuple[date, str], list] = {}
        for ev in self.events:
            if isinstance(ev, TriggerEvent):
                key = (ev.trigger_day, "pm")     # A/RND: pm issuance
            else:
                key = (ev.decision_day, ev.decision_sess)
            self.events_at.setdefault(key, []).append(ev)
        self.pending: dict[str, dict] = {}   # sym -> state
        self.time_exits: dict[str, date] = {}
        self.reason_log: list[dict] = []
        self.trig = {"events": len(self.events), "issued": 0, "filled": 0,
                     "cancel_ttl": 0, "cancel_level": 0, "cancel_cap": 0,
                     "skip_slots": 0, "skip_anchor": 0, "skip_cap": 0,
                     "skip_held": 0}
        self._rank_seq = 0

    # -- helpers ----------------------------------------------------------

    def _month_anchor(self, day: date) -> date:
        j = bisect_right(self.month_ends, day)
        return self.month_ends[max(j - 1, 0)]

    def _latest_close_idx(self, sym: str, day: date, sess: str) -> int:
        ser = self.series.get(sym)
        if ser is None:
            return -1
        # a pm decision may use the same day's completed close; an am
        # decision only yesterday's (or older)
        return ser.idx_le(day) if sess == "pm" else ser.idx_lt(day)

    def _entry_invalidated(self, st: dict, day: date, sess: str) -> bool:
        ev = st["ev"]
        if not isinstance(ev, TriggerEvent) or ev.family == "RND":
            return False
        ser = self.series.get(ev.symbol)
        if ser is None:
            return False
        i = self._latest_close_idx(ev.symbol, day, sess)
        if i < 0:
            return False
        c = float(ser.close[i])
        if c < ev.cancel_level:
            return True
        if ev.cancel_below_ma and np.isfinite(ser.ma20[i]) \
                and c < float(ser.ma20[i]):
            return True
        return False

    def _entry_row(self, sym: str, day: date, sess: str, source: date,
                   weight: float) -> dict:
        return {"symbol": sym, "side": "buy", "intent": "",
                "decision_date": day, "decision_session": sess,
                "source_signal": source, "priority": self._rank_seq,
                "expiry_date": None, "target_weight": float(weight),
                "target_notional": None, "exit_reason": None}

    def _time_exit_row(self, sym: str, day: date, sess: str,
                       source: date) -> dict:
        return {"symbol": sym, "side": "sell", "intent": "profit",
                "decision_date": day, "decision_session": sess,
                "source_signal": source, "priority": TIME_EXIT_PRIORITY,
                "expiry_date": None, "target_weight": None,
                "target_notional": None, "exit_reason": "time_exit"}

    def _b_holding_age(self, sym: str, clips: list[dict], day: date) -> int:
        ser = self.series.get(sym)
        if ser is None or not clips:
            return -1
        anchor = min(date.fromisoformat(str(c["acquired"])) for c in clips)
        ai = ser.idx_of(anchor)
        if ai < 0:
            ai = ser.idx_le(anchor)
            if ai < 0:
                return -1
        return ser.idx_le(day) - ai

    # -- main -------------------------------------------------------------

    def provider(self, day: date, sess: str, ledger: dict):
        held = {str(p["symbol"]): p for p in ledger["positions"]
                if int(p["shares"]) > 0}
        si = self.session_index.get((day, sess))

        # 1. host first: D3 trims/top-ups for held symbols + risk state
        rank_of = {s: i + 1 for i, s in enumerate(sorted(held))}
        step = self.host.step(ledger, members=sorted(held), rank_of=rank_of,
                              source_signal=self._month_anchor(day),
                              expiry=None)
        entry_allowed = _attack_entries_allowed(step.risk_state)
        target_w = step.target_weight

        # 2. pending-entry lifecycle
        for sym in sorted(list(self.pending)):
            st = self.pending[sym]
            if sym in held:
                del self.pending[sym]
                self.trig["filled"] += 1
                continue
            if si is not None and st["first_si"] is not None \
                    and si - st["first_si"] >= ENTRY_TTL_SESSIONS:
                del self.pending[sym]
                self.trig["cancel_ttl"] += 1
                continue
            if self._entry_invalidated(st, day, sess):
                del self.pending[sym]
                self.trig["cancel_level"] += 1
                continue
            anchor = self.price_at(sym, day, sess)
            if anchor is not None and anchor > st["cap"]:
                del self.pending[sym]
                self.trig["cancel_cap"] += 1

        # 3. new triggers at this decision point
        if entry_allowed:
            for ev in self.events_at.get((day, sess), []):
                sym = ev.symbol
                if sym in held or sym in self.pending:
                    self.trig["skip_held"] += 1
                    continue
                if len(held) + len(self.pending) + 1 > MAX_SEATS:
                    self.trig["skip_slots"] += 1
                    continue
                anchor = self.price_at(sym, day, sess)
                if anchor is None or anchor <= 0:
                    self.trig["skip_anchor"] += 1
                    continue
                if isinstance(ev, TriggerEvent):
                    cap = float(ev.cap_price)
                    if anchor > cap:
                        self.trig["skip_cap"] += 1
                        continue
                else:
                    cap = float(anchor) * (1 + CHASE)
                self._rank_seq += 1
                self.pending[sym] = {
                    "ev": ev,
                    "source": (ev.trigger_day if isinstance(ev, TriggerEvent)
                               else ev.decision_day),
                    "first_si": si, "cap": cap}
                self.trig["issued"] += 1

        # 4. SNR exits
        positions = list(ledger["positions"])
        prices = {p["symbol"]: self.price_at(p["symbol"], day, sess)
                  for p in positions}
        sn_rows = self.snr.decide(positions, prices, day=day, session=sess)
        for r in sn_rows:
            r["decision_date"] = day
            r["decision_session"] = sess
            self.reason_log.append({
                "day": day.isoformat(), "sess": sess,
                "symbol": r["symbol"], "reason": r["exit_reason"],
                "source": r["source_signal"].isoformat(),
                "intent": r["intent"]})

        # 5. B-family time exits
        te_rows: list[dict] = []
        if self.p.is_b:
            for sym, pos in sorted(held.items()):
                age = self._b_holding_age(sym, pos.get("clips") or [], day)
                if age < 0:
                    continue
                if sym not in self.time_exits and age >= B_HOLD_SESSIONS:
                    self.time_exits[sym] = day
                if sym in self.time_exits:
                    te_rows.append(self._time_exit_row(
                        sym, day, sess, self.time_exits[sym]))
                    self.reason_log.append({
                        "day": day.isoformat(), "sess": sess, "symbol": sym,
                        "reason": "time_exit",
                        "source": self.time_exits[sym].isoformat(),
                        "intent": "profit"})
        for sym in [s for s in self.time_exits if s not in held]:
            del self.time_exits[sym]

        # 6. assemble: SNR first, then time exits, then host rows, entries
        taken = {r["symbol"] for r in sn_rows}
        te_rows = [r for r in te_rows if r["symbol"] not in taken]
        taken |= {r["symbol"] for r in te_rows}
        overlay_rows = []
        for r in step.rows:
            if r["symbol"] in taken:
                continue
            r = dict(r)
            r["exit_reason"] = ("account_trim" if r["side"] == "sell"
                                else None)
            if r["side"] == "sell":
                self.reason_log.append({
                    "day": day.isoformat(), "sess": sess,
                    "symbol": r["symbol"], "reason": "account_trim",
                    "source": r["source_signal"].isoformat(),
                    "intent": str(r.get("intent") or "risk")})
            overlay_rows.append(r)
        taken |= {r["symbol"] for r in overlay_rows}
        new_rows: list[dict] = []
        for sym, st in sorted(self.pending.items()):
            if sym in taken:
                continue
            new_rows.append(self._entry_row(
                sym, day, sess, st["source"], target_w))
        rows = sn_rows + te_rows + overlay_rows + new_rows
        return rows or None


def make_delayed_provider(provider: Callable, n_sessions: int):
    """Wrap a provider so every decision point's rows are RELEASED one
    (``n_sessions``) decision point(s) later (execution-delay stress).

    The inner provider still sees the live ledger in real time; only the
    order issuance lags.  Releasing re-stamps decision_date/decision_
    session to the release point; source_signal and expiry are kept.
    """
    queue: list[list[dict]] = []

    def wrapped(day: date, sess: str, ledger: dict):
        rows = provider(day, sess, ledger) or []
        queue.append(list(rows))
        release = queue.pop(0) if len(queue) > n_sessions else []
        out = []
        for r in release:
            r = dict(r)
            r["decision_date"] = day
            r["decision_session"] = sess
            out.append(r)
        return out or None

    return wrapped
