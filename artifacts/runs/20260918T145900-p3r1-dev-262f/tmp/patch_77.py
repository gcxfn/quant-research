# -*- coding: utf-8 -*-
"""Apply section 7.7 seam rulings (M1/M2/m1/m3/m4) to the v1 engine."""
from pathlib import Path
import ast

p = Path('src/quant/backtest/band_engine.py')
src = p.read_text(encoding='utf-8')
fixes = []

# 1. init decision_snapshots + drift counter
old = """    fill_counter = 0
    decision_counter = 0
"""
new = """    fill_counter = 0
    decision_counter = 0
    decision_snapshots = {}   # (day, sess) -> decision-point equity snapshot
"""
fixes.append((old, new))
old = """        "odd_lot_exits": 0, "cap_single_name_voids": 0, "cap_total_voids": 0,
        "risk_streaks": [],"""
new = """        "odd_lot_exits": 0, "cap_single_name_voids": 0,
        "single_name_drift_breaches": 0,
        "risk_streaks": [],"""
fixes.append((old, new))

# 2. cap check uses the decision snapshot; remove the implied total cap
old = """            # section 7.3 caps against last completed day's official marks
            cost = want * order.anchor_price
            fail_cap = None
            if base_eq <= 0:
                fail_cap = "cap_total"
            elif (proj_mv_sym.get(order.symbol, 0.0) + cost) \\
                    > CAP_SINGLE_NAME * base_eq + _FLOAT_TOL:
                fail_cap = "cap_single_name"
            elif (proj_total + cost + fee) > CAP_TOTAL * base_eq + _FLOAT_TOL:
                fail_cap = "cap_total"
            if fail_cap is not None:
                if fail_cap == "cap_single_name":
                    stats_acc["cap_single_name_voids"] += 1
                else:
                    stats_acc["cap_total_voids"] += 1
                bump_void(fail_cap)
                emit(day, sess, order, "void_" + fail_cap,
                     limit_price=order.anchor_price, ref_price=low, shares=want,
                     detail="section 7.3 cap: single<=%.0f%%, total<=%.0f%% "
                            "(base equity %.2f); order expires"
                            % (CAP_SINGLE_NAME * 100, CAP_TOTAL * 100, base_eq))
                close_order(day, sess, order, fail_cap, emit_event=False)
                continue"""
new = """            # section 7.3 single-name cap (section 7.7 M2): validated at
            # construction against the DECISION-POINT equity snapshot; a
            # breach voids the whole order (no downsizing).  The total<=100%
            # cap is implied by full funding (cost + fee <= cash) and is not
            # a separate check.
            cost = want * order.anchor_price
            snap_eq = decision_snapshots.get((order.decision_date,
                                              order.decision_session))
            if snap_eq is None:
                snap_eq = base_eq
            if (proj_mv_sym.get(order.symbol, 0.0) + cost) \\
                    > CAP_SINGLE_NAME * snap_eq + _FLOAT_TOL:
                stats_acc["cap_single_name_voids"] += 1
                bump_void("cap_single_name")
                emit(day, sess, order, "void_cap_single_name",
                     limit_price=order.anchor_price, ref_price=low, shares=want,
                     detail="section 7.3 cap: single-name <= %.0f%% of the "
                            "decision-point equity (%.2f); order expires"
                            % (CAP_SINGLE_NAME * 100, snap_eq))
                close_order(day, sess, order, "cap_single_name",
                            emit_event=False)
                continue"""
fixes.append((old, new))

# 3. proj marks stay at the strict previous close (construction basis);
#    remove the dead base_eq/proj_total lines
old = """        reserved = 0.0
        proj_mv_sym: dict = {}
        proj_total = 0.0
        for sym, cs in clips.items():
            px = official_close_strict(sym, day)
            if px is not None:
                mv = sum(c.shares for c in cs) * px
                proj_mv_sym[sym] = mv
                proj_total += mv
        # section 7.3 cap base: equity marked at the last completed day's
        # official closes (cash + pending + MV; no intraday look-ahead)
        base_eq = cash + pend_am_to_pm + pend_next_day + proj_total
        booked = []"""
new = """        reserved = 0.0
        proj_mv_sym: dict = {}
        for sym, cs in clips.items():
            px = official_close_strict(sym, day)
            if px is not None:
                proj_mv_sym[sym] = sum(c.shares for c in cs) * px
        booked = []"""
fixes.append((old, new))

# 4. m1: a deferred limit-down session counts toward the streak when there
#    is no live risk row for the session (otherwise step C counts it)
old = """            if down is not None and o <= down * (1 + LIMIT_DOWN_TOL):
                stats_acc["k3_deferred_limitdown"] += 1
                emit(day, sess, None, "market_exit_deferred_limitdown","""
new = """            if down is not None and o <= down * (1 + LIMIT_DOWN_TOL):
                stats_acc["k3_deferred_limitdown"] += 1
                if not any(o2.symbol == sym and id(o2) not in consumed
                           for o2 in sells):
                    st["streak"] += 1     # m1: the deferred session counts
                emit(day, sess, None, "market_exit_deferred_limitdown","""
fixes.append((old, new))

# 5. m4: split creates a NEW clip for the added shares (acquired = ex-date;
#    sellable next day -- registered conservative deviation)
old = """            ratio = split_ratio_at(symbol, day)
            if ratio is not None and ratio != 1.0:
                for c in cs:                     # half-up PER CLIP
                    c.shares = int(math.floor(c.shares * ratio + 0.5))
                clips[symbol] = [c for c in cs if c.shares > 0]
                post = sum(c.shares for c in clips[symbol])
                stats_acc["corp_action_splits"] += 1
                emit(day, "am", None, "corp_action_split", ratio=ratio,
                     shares=post,
                     detail="%s: shares %d -> %d (split_factor ratio %.10f, "
                            "per-clip half-up)" % (symbol, pre_shares, post,
                                                   ratio))"""
new = """            ratio = split_ratio_at(symbol, day)
            if ratio is not None and ratio != 1.0:
                new_clips = []
                added = 0
                for c in cs:                     # half-up PER CLIP
                    new_total = int(math.floor(c.shares * ratio + 0.5))
                    keep = min(c.shares, new_total)
                    extra = new_total - keep
                    if keep > 0:
                        new_clips.append(_Clip(shares=keep,
                                               acquired=c.acquired,
                                               seq=c.seq, session=c.session))
                    if extra > 0:
                        # m4: newly created shares are acquired TODAY
                        # (sellable next day -- registered deviation)
                        new_clips.append(_Clip(shares=extra, acquired=day,
                                               seq=clip_seq + added,
                                               session="am"))
                        added += extra
                clips[symbol] = [c for c in new_clips if c.shares > 0]
                post = sum(c.shares for c in clips[symbol])
                stats_acc["corp_action_splits"] += 1
                clip_seq += added
                emit(day, "am", None, "corp_action_split", ratio=ratio,
                     shares=post,
                     detail="%s: shares %d -> %d (split_factor ratio %.10f, "
                            "per-clip half-up; added shares acquired %s)"
                            % (symbol, pre_shares, post, ratio,
                               day.isoformat()))"""
fixes.append((old, new))

# 6. M2 drift recording in the daily mark step
old = """        daily_rows.append({
            "date": day, "settled_cash": cash,
            "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "positions_value": positions_value,
            "equity": cash + pend_am_to_pm + pend_next_day + positions_value,
            "n_positions": n_pos,
        })"""
new = """        # section 7.7 M2: price drift can push an existing position over the
        # single-name cap -- recorded only, never force-trimmed
        for symbol, cs in clips.items():
            sh = sum(c.shares for c in cs)
            px = mark_close(symbol, day)
            if sh > 0 and px is not None and equity > 0 \\
                    and sh * px > CAP_SINGLE_NAME * equity:
                stats_acc["single_name_drift_breaches"] += 1
        daily_rows.append({
            "date": day, "settled_cash": cash,
            "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "positions_value": positions_value,
            "equity": cash + pend_am_to_pm + pend_next_day + positions_value,
            "n_positions": n_pos,
        })"""
fixes.append((old, new))

for i, (old, new) in enumerate(fixes):
    if old not in src:
        raise SystemExit('fix %d not found:\n%s' % (i, old[:220]))
    src = src.replace(old, new, 1)

p.write_text(src, encoding='utf-8')
ast.parse(src)
print('%d engine edits applied' % len(fixes))
