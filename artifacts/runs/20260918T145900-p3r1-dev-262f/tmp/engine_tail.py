    def process_session(day: date, sess: str) -> None:
        nonlocal cash, pend_am_to_pm, pend_next_day, clip_seq
        live = live_orders.get((day, sess), [])
        buys = [o for o in live if o.side == "buy"]
        sells = [o for o in live if o.side == "sell"]

        # -- A. buy evaluation in priority order -------------------------
        # Cash is reserved as decided (lower priorities see the remainder);
        # fills are BOOKED after the sell/fallback passes for event ordering.
        reserved = 0.0
        base_eq = cash + pend_am_to_pm + pend_next_day
        proj_mv_sym: dict = {}
        proj_total = 0.0
        for sym, cs in clips.items():
            px = official_close_strict(sym, day)
            if px is not None:
                mv = sum(c.shares for c in cs) * px
                proj_mv_sym[sym] = mv
                proj_total += mv
        booked = []
        for order in buys:
            stats_acc["orders"]["buy"] += 1
            bar = halfbar(order.symbol, day, sess)
            if bar is None:
                bump_void("suspended")
                emit(day, sess, order, "void_suspended",
                     limit_price=order.anchor_price,
                     detail="no half-day bar this session; order expires "
                            "(host may re-issue at the next decision point)")
                close_order(day, sess, order, "void_suspended", emit_event=False)
                continue
            _o, _h, low, _c = bar
            up, down = limits_at(order.symbol, day)
            if not legal_limit(order.anchor_price, up, down):
                reason = ("no_limit_info" if up is None and down is None
                          else "limit_out_of_range")
                bump_void(reason)
                emit(day, sess, order, "void_" + reason,
                     limit_price=order.anchor_price, ref_price=low,
                     detail="day limits [%s, %s] (shared by both sessions)"
                            % (down, up))
                close_order(day, sess, order, "void_" + reason, emit_event=False)
                continue
            if not (low < order.anchor_price):
                bump_void("not_penetrated")
                emit(day, sess, order, "not_penetrated",
                     limit_price=order.anchor_price, ref_price=low,
                     detail="strict penetration required: session low < p")
                close_order(day, sess, order, "not_penetrated", emit_event=False)
                continue
            if order.shares is not None:
                want = order.shares
            else:
                want = int(math.floor(order.target_notional
                                      / order.anchor_price / LOT)) * LOT
                if want < LOT:
                    emit(day, sess, order, "below_min_lot",
                         limit_price=order.anchor_price, ref_price=low,
                         detail="target %.2f at p %.4f affords < %d shares; "
                                "abandoned" % (order.target_notional,
                                               order.anchor_price, LOT))
                    close_order(day, sess, order, "below_min_lot",
                                emit_event=False)
                    continue
            available = cash - reserved
            if not full_quantity_affordable(order.anchor_price, want, available):
                stats_acc["insufficient_cash_orders"] += 1
                bump_void("insufficient_cash")
                emit(day, sess, order, "void_insufficient_cash",
                     limit_price=order.anchor_price, ref_price=low, shares=want,
                     detail="need %d x %.4f fully funded, available %.2f; "
                            "same-session sale proceeds not available"
                            % (want, order.anchor_price, available))
                close_order(day, sess, order, "void_insufficient_cash",
                            emit_event=False)
                continue
            # section 7.3 caps against last completed day's official marks
            cost = want * order.anchor_price
            fee = fees.commission(cost)
            fail_cap = None
            if base_eq <= 0:
                fail_cap = "cap_total"
            elif (proj_mv_sym.get(order.symbol, 0.0) + cost) \
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
                continue
            reserved += cost + fee
            proj_mv_sym[order.symbol] = proj_mv_sym.get(order.symbol, 0.0) + cost
            proj_total += cost + fee
            booked.append((order, want, low))

        # -- B. armed risk fallbacks (section 7.2, K=3 session exit) -------
        consumed: set[int] = set()
        for sym in sorted(s for s, st in risk_state.items() if st["armed"]):
            st = risk_state[sym]
            bar = halfbar(sym, day, sess)
            if bar is None:
                stats_acc["k3_deferred_suspended"] += 1
                emit(day, sess, None, "market_exit_deferred_suspended",
                     detail=sym + ": no half-day bar; fallback stays armed")
                continue                      # stays armed, retries next session
            o, _h, _l, _c = bar
            up, down = limits_at(sym, day)
            sell_sh, sell_list = sellable_shares(sym, day)
            pos = total_shares(sym)
            if sell_sh <= 0:
                if pos > 0:
                    stats_acc["k3_deferred_t1locked"] += 1
                    emit(day, sess, None, "market_exit_deferred_t1locked",
                         detail="%s: all %d shares acquired today (T+1); "
                                "fallback stays armed" % (sym, pos))
                    continue                  # stays armed
                emit(day, sess, None, "market_exit_void_no_position",
                     detail=sym + ": nothing held; fallback state cleared")
                risk_state.pop(sym, None)
                continue
            if down is not None and o <= down * (1 + LIMIT_DOWN_TOL):
                stats_acc["k3_deferred_limitdown"] += 1
                emit(day, sess, None, "market_exit_deferred_limitdown",
                     ref_price=o,
                     detail="%s: open %.4f <= limit_down %.4f x (1+%s); "
                            "fallback stays armed, the limit order keeps "
                            "working this session"
                            % (sym, o, down, LIMIT_DOWN_TOL))
                continue                      # limit keeps working (fall through)
            # execute at the session open, unconditionally
            prev_px = official_close_strict(sym, day)
            live_row = st.get("order")
            use_row = (live_row if (live_row is not None and not live_row.closed
                                    and live_row.live_date == day
                                    and live_row.live_session == sess)
                       else _FallbackOrder(sym, day, sess))
            detail = "" if down is not None else "no_limit_info: fallback executed"
            emit(day, sess, None, "market_exit_filled", ref_price=o,
                 shares=sell_sh, detail=detail or "K=3 market fallback at open")
            book_sell_fill(day, sess, use_row, "market_fallback", o, sell_sh,
                           sell_list, prev_close=prev_close,
                           detail=detail or "K=3 market exit at open")
            if use_row is live_row:
                consumed.add(id(live_row))   # the live risk row is consumed
            risk_state.pop(sym, None)

        # -- C. sell limit orders -----------------------------------------
        for order in sells:
            if id(order) in consumed:
                continue
            bucket = "sell_risk" if order.intent == "risk" else "sell_profit"
            stats_acc["orders"][bucket] += 1
            bar = halfbar(order.symbol, day, sess)
            if bar is None:
                bump_void("suspended")
                emit(day, sess, order, "void_suspended",
                     limit_price=order.anchor_price,
                     detail="no half-day bar this session; order expires"
                            + ("" if order.intent == "profit" else
                               "; K streak frozen (risk re-issue continues it)"))
                close_order(day, sess, order, "void_suspended", emit_event=False)
                continue
            _o, high, _l, _c = bar
            up, down = limits_at(order.symbol, day)
            if not legal_limit(order.anchor_price, up, down):
                reason = ("no_limit_info" if up is None and down is None
                          else "limit_out_of_range")
                bump_void(reason)
                if order.intent == "risk":
                    bump_streak(order, day, sess, filled=False)
                emit(day, sess, order, "void_" + reason,
                     limit_price=order.anchor_price, ref_price=high,
                     detail="sell anchor %.4f not validateable; day limits "
                            "[%.4f, %.4f]" % (order.anchor_price, down, up))
                close_order(day, sess, order, "void_" + reason, emit_event=False)
                continue
            sell_sh, sell_list = sellable_shares(order.symbol, day)
            pos = total_shares(order.symbol)
            if pos == 0:
                stats_acc["no_position_voids"] += 1
                emit(day, sess, order, "void_no_position",
                     detail="nothing held; order expires")
                close_order(day, sess, order, "void_no_position",
                            emit_event=False)
                if order.intent == "risk":
                    risk_state.pop(order.symbol, None)
                continue
            if sell_sh <= 0:
                stats_acc["t1_locked_voids"] += 1
                if order.intent == "risk":
                    bump_streak(order, day, sess, filled=False)
                    emit(day, sess, order, "void_t1_locked",
                         limit_price=order.anchor_price, ref_price=high,
                         shares=pos,
                         detail="all %d shares acquired today (T+1); risk K "
                                "streak counts this session" % pos)
                else:
                    emit(day, sess, order, "void_t1_locked",
                         limit_price=order.anchor_price, ref_price=high,
                         shares=pos,
                         detail="all %d shares acquired today (T+1)" % pos)
                close_order(day, sess, order, "void_t1_locked", emit_event=False)
                continue
            if high > order.anchor_price:
                qty = sell_sh if order.shares is None \
                    else min(order.shares, sell_sh)
                if order.shares is not None and qty < order.shares:
                    stats_acc["quantity_capped"] += 1
                    detail = "quantity_capped to sellable clips"
                else:
                    detail = "strict penetration: session high > q; fill at q"
                consume = []
                remaining = qty
                for c in sell_list:
                    if remaining <= 0:
                        break
                    take = min(c.shares, remaining)
                    consume.append((c, take))
                    remaining -= take
                emit(day, sess, order, "filled_limit_sell",
                     limit_price=order.anchor_price, ref_price=high, shares=qty,
                     detail=detail)
                book_sell_fill(day, sess, order, "limit", order.anchor_price,
                               qty, consume, prev_close=None, detail=detail)
                if order.intent == "risk":
                    risk_state.pop(order.symbol, None)   # filled: streak reset
                continue
            # unfilled this session: every half-day order expires
            if order.intent == "risk":
                st_after = risk_state.get(order.symbol)
                bump_streak(order, day, sess, filled=False)
                st_after = risk_state.get(order.symbol)
                emit(day, sess, order, "not_penetrated",
                     limit_price=order.anchor_price, ref_price=high,
                     detail="strict penetration required: session high > q; "
                            "risk K streak %d"
                            % (st_after["streak"] if st_after else 0)
                            + ("; market fallback armed for next session"
                               if st_after and st_after["armed"] else ""))
            else:
                emit(day, sess, order, "session_expired",
                     limit_price=order.anchor_price, ref_price=high,
                     detail="profit order expires silently (no fallback)")
            close_order(day, sess, order, "session_unfilled", emit_event=False)

        # -- D. book buy fills --------------------------------------------
        for order, shares, low in booked:
            emit(day, sess, order, "filled_limit_buy",
                 limit_price=order.anchor_price, ref_price=low, shares=shares,
                 detail="strict penetration: session low < p; fill at p")
            book_buy_fill(day, sess, order, order.anchor_price, shares)

    for day in calendar:
        # ======== S_am ========
        cash += pend_next_day                    # yesterday pm -> today am
        pend_next_day = 0.0
        # corporate actions on ex-date (before any trading)
        for symbol in sorted(clips):
            cs = clips[symbol]
            if not cs:
                continue
            pre_shares = sum(c.shares for c in cs)
            ratio = split_ratio_at(symbol, day)
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
                                                   ratio))
            div = divs.get(symbol, {}).get(_dint(day))
            if div:
                amount = div * pre_shares
                cash += amount
                stats_acc["corp_action_dividends"] += 1
                stats_acc["dividend_cash_total"] += amount
                emit(day, "am", None, "corp_action_dividend", cash_amount=amount,
                     detail="%s: %.6f yuan/share pre-tax (per-lot row / "
                            "round_lot) x %d pre-ex shares"
                            % (symbol, div, pre_shares))
        process_session(day, "am")

        # ======== decision point 11:30 (day, am) ========
        decision_step(day, "am")

        # ======== S_pm ========
        cash += pend_am_to_pm                    # same-day am -> pm
        pend_am_to_pm = 0.0
        process_session(day, "pm")

        # ======== decision point 15:00 (day, pm) ========
        decision_step(day, "pm")

        # ======== daily mark (OFFICIAL daily close only, section 7.4) =====
        positions_value = 0.0
        n_pos = 0
        for symbol, cs in clips.items():
            sh = sum(c.shares for c in cs)
            if sh <= 0:
                continue
            n_pos += 1
            px = mark_close(symbol, day)
            if px is None:
                stats_acc["stale_mark_days"] += 1
                continue
            positions_value += sh * px
            s = series.get(symbol)
            if s is not None:
                i = int(np.searchsorted(s["trade_dint"], _dint(day), side="right"))
                if i == 0 or int(s["trade_dint"][i - 1]) != _dint(day):
                    stats_acc["stale_mark_days"] += 1
        daily_rows.append({
            "date": day, "settled_cash": cash,
            "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "positions_value": positions_value,
            "equity": cash + pend_am_to_pm + pend_next_day + positions_value,
            "n_positions": n_pos,
        })

    # ---- outcome bookkeeping for the result frames -----------------------
    for order in orders:
        if not order.closed and order.close_reason != "expired_no_live_session":
            order.closed = True
            order.close_reason = "end_of_data_unfilled"
            key = "sell" if order.side == "sell" else "buy"
            sub = order.intent if order.side == "sell" else "_"
            b = stats_acc["unfilled_exit"][key]
            b.setdefault(sub, {})
            b[sub]["end_of_data_unfilled"] = \
                b[sub].get("end_of_data_unfilled", 0) + 1

    for sym, st in risk_state.items():
        if st["streak"]:
            stats_acc["risk_streaks"].append(
                {"symbol": sym, "final_streak": st["streak"],
                 "armed": st["armed"]})

    unfilled_buys = sum(stats_acc["unfilled_exit"]["buy"].get("_", {}).values())
    k3_pnl = stats_acc.pop("k3_pnl_contribution")
    streaks = stats_acc.pop("risk_streaks")
    k3_def = stats_acc.pop("k3_pnl_definition")
    stats = {
        "initial_cash": initial_cash,
        "contract": "v1 (docs/plans/p3-band-contract.md section 7)",
        "fees": {
            "commission_rate": fees.commission_rate,
            "commission_min": fees.commission_min,
            "stamp_sell_before": fees.stamp_sell_before,
            "stamp_sell_from": fees.stamp_sell_from,
            "stamp_boundary": fees.stamp_boundary.isoformat(),
            "etf_stamp": "exempt (is_etf)",
            "transfer_fee": "not modelled (~0.1bp/leg SSE only; standing "
                            "disclosure)",
        },
        "contract_constants": {
            "K_FALLBACK_SESSIONS": K_FALLBACK_SESSIONS,
            "LIMIT_DOWN_TOL": LIMIT_DOWN_TOL, "LOT": LOT,
            "FREEZE_END": FREEZE_END.isoformat(),
            "commission_warning_notional": COMMISSION_WARNING_NOTIONAL,
            "cap_single_name": CAP_SINGLE_NAME, "cap_total": CAP_TOTAL,
            "pm_close_official_cutoff": PM_CLOSE_OFFICIAL_CUTOFF.isoformat(),
        },
        "signals": stats_acc["orders"],
        "orders_filled": stats_acc["orders_filled"],
        "fill_rate_order_session": {
            "buy": (stats_acc["orders_filled"]["buy"]
                    / stats_acc["orders"]["buy"]
                    if stats_acc["orders"]["buy"] else None),
            "sell_risk": (stats_acc["orders_filled"]["sell_risk"]
                          / stats_acc["orders"]["sell_risk"]
                          if stats_acc["orders"]["sell_risk"] else None),
            "sell_profit": (stats_acc["orders_filled"]["sell_profit"]
                            / stats_acc["orders"]["sell_profit"]
                            if stats_acc["orders"]["sell_profit"] else None),
        },
        "unfilled_exit_reasons": stats_acc["unfilled_exit"],
        "unfilled_exit_share_buys": (unfilled_buys / stats_acc["orders"]["buy"]
                                     if stats_acc["orders"]["buy"] else None),
        "k3_fallback": {
            "armed": stats_acc["k3_armed"],
            "executed": stats_acc["k3_executed"],
            "deferred_limitdown_sessions": stats_acc["k3_deferred_limitdown"],
            "deferred_suspended": stats_acc["k3_deferred_suspended"],
            "deferred_t1locked": stats_acc["k3_deferred_t1locked"],
            "pnl_contribution_total": sum(k3_pnl) if k3_pnl else 0.0,
            "pnl_contribution_list": k3_pnl,
            "pnl_definition": k3_def,
            "definition": "risk-intent sells unfilled for %d consecutive live "
                          "sessions are market-exited at the next session open "
                          "(opening limit-down / suspension / T+1-lock defer)"
                          % K_FALLBACK_SESSIONS,
        },
        "corp_actions": {
            "splits": stats_acc["corp_action_splits"],
            "dividends": stats_acc["corp_action_dividends"],
            "dividend_cash_total_pre_tax": stats_acc["dividend_cash_total"],
        },
        "turnover": {
            "buy_notional_total": stats_acc["buy_notional_total"],
            "sell_notional_total": stats_acc["sell_notional_total"],
        },
        "cash_friction": {
            "insufficient_cash_orders": stats_acc["insufficient_cash_orders"],
            "below_min_lot_abandons": stats_acc["below_min_lot_abandons"],
            "quantity_capped_fills": stats_acc["quantity_capped"],
            "no_position_voids": stats_acc["no_position_voids"],
            "t1_locked_voids": stats_acc["t1_locked_voids"],
        },
        "caps": {
            "single_name_voids": stats_acc["cap_single_name_voids"],
            "total_voids": stats_acc["cap_total_voids"],
            "definition": "section 7.3: single-name MV <= 25% equity, total "
                          "MV <= 100% incl. fee reserve; enforced against last "
                          "completed day's official-close marks (conservative, "
                          "no intraday look-ahead)",
        },
        "odd_lot_exits": stats_acc["odd_lot_exits"],
        "commission_warnings": stats_acc["commission_warnings"],
        "risk_streaks_open_at_end": streaks,
        "void_days": stats_acc["void_days"],
        "stale_mark_days": stats_acc["stale_mark_days"],
        "final": {
            "settled_cash": cash, "pending_am_to_pm": pend_am_to_pm,
            "pending_next_day": pend_next_day,
            "n_open_clips": sum(1 for cs in clips.values()
                                for c in cs if c.shares > 0),
        },
        "definitions": {
            "fill_rate_order_session": "filled orders / orders (every order "
                                       "lives exactly one session)",
            "unfilled_exit_share_buys": "buy orders never filled / buy orders",
            "k3_pnl_contribution": k3_def,
            "caps": "section 7.3 limits enforced at fill evaluation against "
                    "last completed day's official-close marks (conservative, "
                    "no intraday look-ahead)",
        },
    }

    clips_final = []
    last_day = calendar[-1] if calendar else date(1900, 1, 1)
    for symbol in sorted(clips):
        s = series.get(symbol)
        px = mark_close(symbol, last_day)
        for c in clips[symbol]:
            if c.shares <= 0:
                continue
            clips_final.append({
                "symbol": symbol, "shares": c.shares, "acquired": c.acquired,
                "last_close": px if px is not None else float("nan"),
                "market_value": c.shares * px if px is not None else float("nan"),
            })

    return BandResult(
        fills=_frame(fills, _FILL_SCHEMA),
        events=_frame(events, _EVENT_SCHEMA),
        daily=_frame(daily_rows, _DAILY_SCHEMA),
        clips_final=_frame(clips_final, _CLIP_SCHEMA),
        stats=stats,
        warnings=warnings,
    )
