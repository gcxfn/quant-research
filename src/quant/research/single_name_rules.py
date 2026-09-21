"""Frozen single-name exit rules for attack seats (fixed-scheme prereg §4).

Batch-level rules driven ONLY by the live ledger's per-clip fill prices
(engine `_Clip.price` feedback) and a pre-frozen ATR20 lookup:

* stop:   stop_i = cost_i - 2*ATR20(acquired), distance clamped to
          [5%,15%] of cost_i;  R_i = cost_i - stop_i
* exits:  P <= stop_i                      -> stop (conservative: ANY clip
          triggering stop / protection exits the whole symbol)
          reached_1r_i and P <= cost_i     -> protection-line full exit
          P >= cost_i + 3R_i (all clips)   -> full clear
          P >= cost_i + 2R_i and not half  -> sell half that clip (int lots)

Exit-order classes (AGENTS section 1 / engine contract `intent`):
* risk class (intent='risk'): stop / protection whole exits.  The K=3
  open-market fallback MUST be available for them -- a stop that gaps
  limit-down for three half-days must still leave the account.
* profit class (intent='profit'): take_half / clear.  They expire at each
  half-day end (no open-market fallback); persistence comes from this
  module re-issuing while the exit event is live.

Both classes are ABSOLUTE EVENTS (2026-09-21 audit Q1, reworked twice
after reviews):

* At trigger the rule freezes ``target_shares`` (0 for a whole exit, the
  position's keep-quantity for a halving), ``source`` = the trigger day
  and ``reason``.  While the event is live the rule re-issues ONE sell
  order per decision point with the SAME frozen ``source`` -- the engine
  keeps ONE risk streak per symbol, fed only by intent='risk' rows and
  reset whenever the source changes, so a per-day source resets the
  streak and the K=3 fallback never arms (review finding:
  whole-exit rows carried source=day; first-fix finding: halving rows
  did).  An absolute target also makes a FIFO fill that consumed a
  DIFFERENT clip harmless: the target is total-share based, so the rule
  never re-counts per-clip keeps and oversells.
* A live WHOLE event absorbs later whole triggers (the order content --
  sell everything -- is identical; keeping the first trigger's source
  preserves the streak).  A halving event is replaced by a whole exit.
  One live event per symbol.
* The event completes when the ledger reaches/below ``target_shares``
  (one-lot tolerance); triggering clips are then marked ``half_done``
  and never re-halve.  A symbol that leaves the positions list entirely
  (external full exit) has its clips and any live event PURGED -- a
  later re-entry starts from a clean slate and cannot be smashed by a
  stale trigger-day target (review finding: cross-position residue).
* ``half_armed`` (level touched) and ``half_done`` (keep-quantity
  realized) are separate flags; ``clip_diagnostics``/``events`` expose
  both for ledger reconciliation.

Known engine-level property (disclosed, audit section 5.2): the engine
consumes clips FIFO, so a partial sell may eat a different lot than the
rule's per-clip intent; the TOTAL matches the frozen target, but the
surviving lot composition can differ (a later whole exit of the symbol
is unaffected; a later clear covers whatever clips remain).

* the module only decides; the engine owns fills, T+1 and streaks.

No strategy judgement lives here; parameters are frozen in
docs/research/exp-20260921-fixed-scheme-prereg.md and must not be tuned
against results.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Mapping

STOP_ATR_MULT = 2.0
STOP_DIST_MIN = 0.05
STOP_DIST_MAX = 0.15
PROFIT_1R = 1.0            # protection line arms at +1R (line = cost)
PROFIT_2R = 2.0            # sell half
PROFIT_3R = 3.0            # clear
EXIT_PRIORITY = 500_001    # before seat exits (10**6), after entries
LOT = 100

# exit_reason values on emitted rows
REASON_STOP = "stop"
REASON_PROTECTION = "protection"
REASON_TAKE_HALF = "take_half"
REASON_CLEAR = "clear"
REASON_TRAIL = "trail"       # phase-B perturbation (2): trailing line

# risk-class reasons ride intent='risk' (K=3 open-market fallback);
# profit-class reasons ride intent='profit' (half-day expiry, re-issued
# by this module while their event is live)
INTENT_OF_REASON = {
    REASON_STOP: "risk",
    REASON_PROTECTION: "risk",
    REASON_TRAIL: "risk",
    REASON_TAKE_HALF: "profit",
    REASON_CLEAR: "profit",
}


def _half_keep_target(shares0: int) -> int:
    """Whole-lot share count a +2R halving keeps from an initial clip."""
    return (int(shares0) // 2 // LOT) * LOT


class SingleNameRules:
    """Per-clip exit-state tracker for one backtest arm.

    ``atr_mult`` / ``dist_min`` / ``dist_max`` default to the frozen
    fixed-scheme values (2x ATR20, 5%..15%); the r2 exploration passes
    wider values (3x, 10%..20%) explicitly. Not tunable against results
    without a new registration.
    """

    def __init__(self, atr_getter: Callable[[str, date], float], *,
                 atr_mult: float = STOP_ATR_MULT,
                 dist_min: float = STOP_DIST_MIN,
                 dist_max: float = STOP_DIST_MAX,
                 trail_after_1r: bool = False,
                 trail_atr_mult: float = 1.0,
                 high20_getter: Callable[[str, date], float | None] | None
                 = None) -> None:
        # (symbol, acquired, session) -> {"stop":, "r":, "reached_1r":,
        #                                 "half_armed":, "half_done":,
        #                                 "shares0":, "trail_line":}
        self._clips: dict[tuple[str, str, str], dict] = {}
        # symbol -> {"target_shares": int, "source": date, "reason": str,
        #            "clip_keys": [keys covered by the event]}
        self._events: dict[str, dict] = {}
        self._atr_getter = atr_getter
        self._atr_mult = float(atr_mult)
        self._dist_min = float(dist_min)
        self._dist_max = float(dist_max)
        # phase-B registered perturbation (2): after +1R the protection
        # line TRAILS at max(20-session high) - trail_atr_mult * ATR20 and
        # the fixed +3R clear is OFF; the wide stop and the +2R half stay.
        # ``high20_getter`` must return the max high over the 20 sessions
        # STRICTLY BEFORE the day (no same-day lookahead at am decisions).
        self._trail = bool(trail_after_1r)
        self._trail_mult = float(trail_atr_mult)
        self._high20 = high20_getter
        if self._trail and high20_getter is None:
            raise ValueError("trail_after_1r requires high20_getter")

    def _clip_state(self, symbol: str, clip: Mapping) -> dict:
        key = (symbol, str(clip["acquired"]), str(clip["session"]))
        st = self._clips.get(key)
        if st is None:
            cost = float(clip["price"])
            shares0 = int(clip["shares"])
            if cost <= 0:
                # bonus-share clips carry no cash cost: no R geometry, the
                # clip only participates in whole-symbol exits
                st = {"stop": None, "r": None, "reached_1r": False,
                      "half_armed": False, "half_done": True,
                      "shares0": shares0, "trail_line": None}
            else:
                atr = float(self._atr_getter(symbol, date.fromisoformat(
                    str(clip["acquired"]))))
                dist = min(max(self._atr_mult * atr / cost,
                               self._dist_min), self._dist_max) * cost
                stop = cost - dist
                st = {"stop": stop, "r": dist, "reached_1r": False,
                      "half_armed": False, "half_done": False,
                      "shares0": shares0, "trail_line": None}
            self._clips[key] = st
        return st

    def _purge_symbol(self, symbol: str) -> None:
        """Drop all state for a symbol the ledger no longer holds."""
        self._events.pop(symbol, None)
        for key in [k for k in self._clips if k[0] == symbol]:
            del self._clips[key]

    def clip_diagnostics(self) -> dict[tuple[str, str, str], dict]:
        """Read-only per-clip exit state (audit Q1: armed-vs-done so a
        runner or test can reconcile the rule's view with the ledger)."""
        return {k: dict(v) for k, v in self._clips.items()}

    def events(self) -> dict[str, dict]:
        """Read-only view of live exit events (absolute targets)."""
        return {s: dict(e) for s, e in self._events.items()}

    def decide(self, positions: list[dict], prices: Mapping[str, float],
               *, day: date, session: str) -> list[dict]:
        """Return exit intent rows for THIS decision point.

        ``positions`` is the provider ledger's positions list; ``prices``
        maps symbol -> completed decision-point close (am bar close for an
        am decision, official close for pm).
        """
        rows: list[dict] = []
        held = set()
        for pos in positions:
            symbol = str(pos["symbol"])
            if pos["clips"]:
                held.add(symbol)
        # purge state for symbols that left the ledger entirely (external
        # full exit): a later re-entry must not inherit a stale event
        for symbol in [s for s in self._events if s not in held]:
            self._purge_symbol(symbol)
        for key in [k for k in self._clips if k[0] not in held]:
            del self._clips[key]
        for pos in positions:
            symbol = str(pos["symbol"])
            px = prices.get(symbol)
            if px is None or px <= 0 or not pos["clips"]:
                continue
            total = int(pos["shares"])
            ev = self._events.get(symbol)
            # 1. live WHOLE event (stop/protection): keep pulling to zero
            #    with the FROZEN source until the position is gone; later
            #    whole triggers are absorbed (same order content, streak
            #    preserved)
            if ev is not None and ev["target_shares"] == 0:
                rows.append(self._row(
                    symbol, "sell", day, session, source=ev["source"],
                    intent="risk", exit_reason=ev["reason"]))
                continue
            states = [(c, self._clip_state(symbol, c)) for c in pos["clips"]]
            # 2. whole-exit scan: ANY clip triggering stop/protection
            #    exits the WHOLE symbol; a live halving event is subsumed
            whole_reason: str | None = None
            for clip, st in states:
                cost = float(clip["price"])
                if st["stop"] is not None and px <= st["stop"]:
                    whole_reason = REASON_STOP
                    break
                if self._trail:
                    # perturbation (2): the fixed cost-protect line is
                    # REPLACED by the trailing line armed at +1R
                    if (st["reached_1r"]
                            and st["trail_line"] is not None
                            and px <= st["trail_line"]):
                        whole_reason = REASON_TRAIL
                        break
                elif (st["reached_1r"] and cost > 0
                        and px <= cost):
                    whole_reason = REASON_PROTECTION
                    break
            if whole_reason is not None:
                # replace a live HALVING event with the whole exit (fresh
                # source: a different order, a new engine streak); a live
                # whole event was already absorbed at step 1
                if ev is None or ev["target_shares"] > 0:
                    self._events[symbol] = {
                        "target_shares": 0, "source": day,
                        "reason": whole_reason,
                        "clip_keys": [(symbol, str(c["acquired"]),
                                       str(c["session"])) for c in pos["clips"]]}
                ev = self._events[symbol]
                rows.append(self._row(
                    symbol, "sell", day, session, source=ev["source"],
                    intent="risk", exit_reason=ev["reason"]))
                continue
            # 3. live halving event: pull the position to the frozen
            #    absolute target with the FROZEN source (streak keeps)
            if ev is not None:
                if total <= ev["target_shares"] + LOT - 1:
                    # realized: the covered clips never halve again
                    for key in ev["clip_keys"]:
                        st = self._clips.get(key)
                        if st is not None:
                            st["half_done"] = True
                    self._events.pop(symbol)
                else:
                    rows.append(self._row(
                        symbol, "sell", day, session, source=ev["source"],
                        intent="profit",
                        target_notional=ev["target_shares"] * px,
                        exit_reason=ev["reason"]))
                continue
            # 4. no live event: arm protection lines, then evaluate the
            #    per-clip ladder into ONE absolute keep-quantity
            keep_shares = 0
            covered: list[tuple[str, str, str]] = []
            for clip, st in states:
                cost = float(clip["price"])
                shares = int(clip["shares"])
                key = (symbol, str(clip["acquired"]), str(clip["session"]))
                if cost <= 0 or st["r"] is None:
                    keep_shares += shares
                    continue
                if px >= cost + PROFIT_1R * st["r"]:
                    st["reached_1r"] = True
                if self._trail and st["reached_1r"]:
                    # trailing protection line: ratchets up with the
                    # 20-session high, never down (getter is strictly
                    # prior-day, so no am-lookahead)
                    h20 = self._high20(symbol, day)
                    atr_d = self._atr_getter(symbol, day)
                    if h20 is not None and atr_d is not None \
                            and float(atr_d) > 0:
                        line = float(h20) - self._trail_mult * float(atr_d)
                        st["trail_line"] = (line if st["trail_line"] is None
                                            else max(st["trail_line"], line))
                if not self._trail and px >= cost + PROFIT_3R * st["r"]:
                    # cleared clip: contributes 0 and is covered by the
                    # event so its exit intent survives a later dip
                    covered.append(key)
                    continue
                if px >= cost + PROFIT_2R * st["r"]:
                    st["half_armed"] = True
                if st["half_armed"] and not st["half_done"]:
                    # fresh trigger: keep the halved whole-lot target of
                    # this clip's INITIAL size (shares0 snapshot)
                    keep_shares += _half_keep_target(st["shares0"])
                    covered.append(key)
                else:
                    keep_shares += shares
            if keep_shares < total and covered:
                reason = (REASON_CLEAR if keep_shares == 0
                          else REASON_TAKE_HALF)
                self._events[symbol] = {
                    "target_shares": keep_shares, "source": day,
                    "reason": reason, "clip_keys": covered}
                rows.append(self._row(
                    symbol, "sell", day, session, source=day,
                    intent="profit",
                    target_notional=keep_shares * px,
                    exit_reason=reason))
        return rows

    @staticmethod
    def _row(symbol: str, side: str, day: date, session: str, *,
             source: date,
             intent: str,
             target_weight: float | None = None,
             target_notional: float | None = None,
             exit_reason: str | None = None) -> dict:
        return {
            "symbol": symbol, "side": side, "intent": intent,
            "decision_date": day, "decision_session": session,
            "source_signal": source, "priority": EXIT_PRIORITY,
            "expiry_date": None, "target_weight": target_weight,
            "target_notional": target_notional,
            "exit_reason": exit_reason,
        }
