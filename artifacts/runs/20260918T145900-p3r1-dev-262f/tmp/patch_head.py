# -*- coding: utf-8 -*-
"""One-shot patcher: apply the head edits to band_engine.py (v1 wiring)."""
from pathlib import Path
import ast

p = Path('src/quant/backtest/band_engine.py')
src = p.read_text(encoding='utf-8')

# 1. import time
old = "import bisect\nimport math\n"
assert old in src
src = src.replace(old, "import bisect\nimport math\nimport time\n", 1)

# 2. _FallbackOrder dataclass after _Order (before _validate_signals)
old = """    closed: bool = False
    close_reason: str = ""


def _validate_signals("""
new = """    closed: bool = False
    close_reason: str = ""


@dataclass
class _FallbackOrder:
    \\"\\"\\"Synthetic order metadata for a K=3 market fallback executed without
    a live risk row (the host stopped re-issuing after the fallback armed).
    Carries the standing order's last known decision metadata.\\"\\"\\"

    order_id: str
    symbol: str
    side: str
    intent: str
    decision_date: date
    decision_session: str
    priority: int
    live_date: date
    live_session: str
    closed: bool = False
    close_reason: str = ""


def _validate_signals("""
new = new.replace('\\"', '"')
assert old in src, 'block2'
src = src.replace(old, new, 1)

# 3. drop last_decision_seen; add decision_counter / orders_no_live_session
old = """    fill_counter = 0
    last_decision_seen: dict[str, int] = {}   # symbol -> decision order index
"""
new = """    fill_counter = 0
    decision_counter = 0
    orders_no_live_session = 0
"""
assert old in src
src = src.replace(old, new, 1)

# 4. fix stats_acc keys
old = """        "k3_armed": 0, "k3_executed": 0, "k3_deferred_limitdown": 0,
        "k3_deferred_buyconflict": 0, "k3_deferred_suspended": 0,
        "k3_deferred_t1locked": 0, "k3_pnl_contribution": [],"""
new = """        "k3_armed": 0, "k3_executed": 0, "k3_deferred_limitdown": 0,
        "k3_deferred_suspended": 0,
        "k3_deferred_t1locked": 0, "k3_pnl_contribution": [],
        "k3_pnl_definition": "net market-exit proceeds minus shares * "
                             "previous official close","""
assert old in src
src = src.replace(old, new, 1)

old = """        "risk_streaks": [], "same_session_proceeds_reuse_attempts": 0,
        "stale_mark_days": 0,
    }"""
new = """        "risk_streaks": [],
        "stale_mark_days": 0,
    }
    _t0 = time.perf_counter()

    def check_day_budget() -> None:
        if time.perf_counter() - _t0 > 1800.0:
            raise BandContractError("engine budget exceeded: computation "
                                    ">1800s in run_band_backtest")
"""
assert old in src
src = src.replace(old, new, 1)

# 5. count no-live-session orders
old = """            if nd is None:
                # no live session inside the panel: dies at validation time
                order.closed = True
                order.close_reason = "expired_no_live_session"
                continue"""
new = """            if nd is None:
                # no live session inside the panel: the order dies unborn
                order.closed = True
                order.close_reason = "expired_no_live_session"
                orders_no_live_session += 1
                continue"""
assert old in src
src = src.replace(old, new, 1)

# 6. replace the v0 record_fill with v1 bookers + risk-state machinery
start = src.index("    def record_fill(day: date, sess: str, order: _Order, fill_type: str,")
end = src.index("    def process_session(day: date, sess: str) -> None:")

new_block = '''    def bump_void(reason: str) -> None:
        stats_acc["void_days"][reason] = stats_acc["void_days"].get(reason, 0) + 1

    def bump_streak(order, day: date, sess: str) -> None:
        """Count one unfilled live session for the standing risk order; arm
        the K=3 fallback at the frozen session count."""
        st = risk_state.get(order.symbol)
        if st is None:
            return
        st["streak"] += 1
        if st["streak"] >= K_FALLBACK_SESSIONS and not st["armed"]:
            st["armed"] = True
            stats_acc["k3_armed"] += 1

    def decision_step(day: date, sess: str) -> None:
        """Decision-point bookkeeping for standing risk orders (section 7.2):
        states not re-issued at this decision point are withdrawn (streak
        reset); re-issued states re-anchor and keep their streak.  Armed
        states are NEVER withdrawn here -- the K=3 mechanical fallback
        overrides host withdrawal until it executes."""
        nonlocal decision_counter
        decision_counter += 1
        rows = risk_rows_by_decision.get((day, sess), [])
        refreshed = {o.symbol for o in rows}
        for sym in list(risk_state):
            st = risk_state[sym]
            if st["armed"] or sym in refreshed:
                continue
            emit(day, sess, None, "risk_state_dropped",
                 detail=sym + ": no re-issue at this decision point; standing "
                              "risk order withdrawn (streak reset)")
            risk_state.pop(sym, None)
        for o in rows:
            st = risk_state.get(o.symbol)
            if st is None:
                risk_state[o.symbol] = {"anchor": o.anchor_price, "streak": 0,
                                        "armed": False,
                                        "refreshed_at": decision_counter,
                                        "order": o}
            else:
                st["anchor"] = o.anchor_price
                st["refreshed_at"] = decision_counter
                st["order"] = o

    def book_buy_fill(day: date, sess: str, order, price: float,
                      shares: int) -> None:
        nonlocal cash, clip_seq
        notional = price * shares
        commission = fees.commission(notional)
        net = -(notional + commission)
        cash += net
        clips.setdefault(order.symbol, []).append(
            _Clip(shares=int(shares), acquired=day, seq=clip_seq))
        clip_seq += 1
        stats_acc["buy_notional_total"] += notional
        if notional > COMMISSION_WARNING_NOTIONAL + _FLOAT_TOL:
            stats_acc["commission_warnings"] += 1
            warnings.append(
                "commission guard: %s fill %s %s notional %.2f > %.0f "
                "(commission %.2f; the 5-yuan minimum no longer binds)"
                % (order.side, order.symbol, day.isoformat(), notional,
                   COMMISSION_WARNING_NOTIONAL, commission))
        fill_counter += 1
        fills.append({
            "fill_id": "F%06d" % fill_counter, "order_id": order.order_id,
            "symbol": order.symbol, "side": order.side, "intent": order.intent,
            "fill_type": "limit", "date": day, "session": sess,
            "decision_date": order.decision_date,
            "decision_session": order.decision_session,
            "priority": order.priority, "shares": int(shares),
            "price": float(price), "notional": notional,
            "commission": commission, "stamp_tax": 0.0,
            "fees_total": commission, "net_cash_flow": net,
            "is_etf": is_etf.get(order.symbol, False), "detail": "buy clip",
        })
        stats_acc["orders_filled"]["buy"] += 1
        order.closed = True
        order.close_reason = "filled"

    def book_sell_fill(day: date, sess: str, order, fill_type: str,
                       price: float, shares: int, consume, *,
                       prev_close, detail: str) -> None:
        nonlocal cash, pend_am_to_pm, pend_next_day
        is_etf_sym = is_etf.get(order.symbol, False)
        notional = price * shares
        commission = fees.commission(notional)
        stamp = fees.stamp_sell(day, notional, is_etf_sym)
        net = notional - commission - stamp
        if sess == "am":
            pend_am_to_pm += net      # section 7.2: usable from same-day pm
        else:
            pend_next_day += net      # usable from next day's am
        for c, take in consume:
            c.shares -= take
        clips[order.symbol] = [c for c in clips.get(order.symbol, [])
                               if c.shares > 0]
        stats_acc["sell_notional_total"] += notional
        if shares % LOT != 0:
            stats_acc["odd_lot_exits"] += 1
            detail = (detail + "; " if detail else "") + \\
                "odd_lot_exit (corp-action remainder, single order)"
        if fill_type == "market_fallback":
            stats_acc["k3_executed"] += 1
            stats_acc["k3_pnl_contribution"].append(net - shares * prev_close)
        if notional > COMMISSION_WARNING_NOTIONAL + _FLOAT_TOL:
            stats_acc["commission_warnings"] += 1
            warnings.append(
                "commission guard: %s fill %s %s notional %.2f > %.0f "
                "(commission %.2f; the 5-yuan minimum no longer binds)"
                % (order.side, order.symbol, day.isoformat(), notional,
                   COMMISSION_WARNING_NOTIONAL, commission))
        fill_counter += 1
        fills.append({
            "fill_id": "F%06d" % fill_counter, "order_id": order.order_id,
            "symbol": order.symbol, "side": order.side, "intent": order.intent,
            "fill_type": fill_type, "date": day, "session": sess,
            "decision_date": order.decision_date,
            "decision_session": order.decision_session,
            "priority": order.priority, "shares": int(shares),
            "price": float(price), "notional": notional,
            "commission": commission, "stamp_tax": stamp,
            "fees_total": commission + stamp, "net_cash_flow": net,
            "is_etf": is_etf_sym, "detail": detail,
        })
        bucket = ("sell_risk" if (order.side == "sell"
                                  and order.intent == "risk")
                  else "sell_profit")
        stats_acc["orders_filled"][bucket] += 1
        order.closed = True
        order.close_reason = "filled"

'''
src = src[:start] + new_block + src[end:]

p.write_text(src, encoding='utf-8')
ast.parse(src)
print('head edits applied; syntax OK; lines:', len(src.splitlines()))
