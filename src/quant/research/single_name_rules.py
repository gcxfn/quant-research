"""Frozen single-name exit rules for attack seats (fixed-scheme prereg §4).

Batch-level rules driven ONLY by the live ledger's per-clip fill prices
(engine `_Clip.price` feedback) and a pre-frozen ATR20 lookup:

* stop:   stop_i = cost_i - 2*ATR20(acquired), distance clamped to
          [5%, 15%] of cost_i;  R_i = cost_i - stop_i
* exits:  P <= stop_i                      -> stop (conservative: ANY clip
          triggering stop / protection exits the whole symbol)
          reached_1r_i and P <= cost_i     -> protection-line full exit
          P >= cost_i + 3R_i (all clips)   -> full clear
          P >= cost_i + 2R_i and not half  -> sell half that clip (int lots)
* every exit row is intent='risk' (K=3 open fallback, partial quantity);
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
                 dist_max: float = STOP_DIST_MAX) -> None:
        # (symbol, acquired, session) -> {"stop":, "r":, "reached_1r":,
        #                                 "half_taken":}
        self._clips: dict[tuple[str, str, str], dict] = {}
        self._atr_getter = atr_getter
        self._atr_mult = float(atr_mult)
        self._dist_min = float(dist_min)
        self._dist_max = float(dist_max)

    def _clip_state(self, symbol: str, clip: Mapping) -> dict:
        key = (symbol, str(clip["acquired"]), str(clip["session"]))
        st = self._clips.get(key)
        if st is None:
            cost = float(clip["price"])
            if cost <= 0:
                # bonus-share clips carry no cash cost: no R geometry, the
                # clip only participates in whole-symbol exits
                st = {"stop": None, "r": None, "reached_1r": False,
                      "half_taken": False}
            else:
                atr = float(self._atr_getter(symbol, date.fromisoformat(
                    str(clip["acquired"]))))
                dist = min(max(self._atr_mult * atr / cost,
                               self._dist_min), self._dist_max) * cost
                stop = cost - dist
                st = {"stop": stop, "r": dist, "reached_1r": False,
                      "half_taken": False}
            self._clips[key] = st
        return st

    def decide(self, positions: list[dict], prices: Mapping[str, float],
               *, day: date, session: str) -> list[dict]:
        """Return exit intent rows for THIS decision point.

        ``positions`` is the provider ledger's positions list; ``prices``
        maps symbol -> completed decision-point close (am bar close for an
        am decision, official close for pm).
        """
        rows: list[dict] = []
        for pos in positions:
            symbol = str(pos["symbol"])
            px = prices.get(symbol)
            if px is None or px <= 0 or not pos["clips"]:
                continue
            states = [(c, self._clip_state(symbol, c)) for c in pos["clips"]]
            # 1. stop / protection: any clip triggering exits the WHOLE symbol
            whole_exit = False
            for clip, st in states:
                cost = float(clip["price"])
                if st["stop"] is not None and px <= st["stop"]:
                    whole_exit = True
                    break
                if (st["reached_1r"] and cost > 0
                        and px <= cost):
                    whole_exit = True
                    break
            if whole_exit:
                rows.append(self._row(symbol, "sell", day, session,
                                      target_weight=None))
                continue
            # 2. arm protection lines (done BEFORE the exit scan next point)
            #    and evaluate profit taking per clip
            keep_shares = 0
            for clip, st in states:
                cost = float(clip["price"])
                shares = int(clip["shares"])
                if cost <= 0 or st["r"] is None:
                    keep_shares += shares
                    continue
                if px >= cost + PROFIT_1R * st["r"]:
                    st["reached_1r"] = True
                if px >= cost + PROFIT_3R * st["r"]:
                    continue                      # cleared clip
                if (px >= cost + PROFIT_2R * st["r"]
                        and not st["half_taken"]):
                    keep_shares += (shares // 2 // LOT) * LOT
                    st["half_taken"] = True
                else:
                    keep_shares += shares
            if keep_shares < int(pos["shares"]):
                # partial exit to keep_shares via the retained-notional form
                rows.append(self._row(symbol, "sell", day, session,
                                      target_notional=keep_shares * px))
        return rows

    @staticmethod
    def _row(symbol: str, side: str, day: date, session: str, *,
             target_weight: float | None = None,
             target_notional: float | None = None) -> dict:
        return {
            "symbol": symbol, "side": side, "intent": "risk",
            "decision_date": day, "decision_session": session,
            "source_signal": day, "priority": EXIT_PRIORITY,
            "expiry_date": None, "target_weight": target_weight,
            "target_notional": target_notional,
        }
