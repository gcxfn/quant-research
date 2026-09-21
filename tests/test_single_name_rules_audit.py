"""Audit regression tests (2026-09-21 stock-first review, C3 + Q1).

C3: exit rows must carry an explicit exit_reason so counters attribute
    stops / protection / take-half / clear correctly; classifying rows by
    ``target_weight is None`` miscounted every protection and take-half
    row as a stop (the retained-notional form also leaves target_weight
    empty), which produced the false "107 stops / 0 takes" reading.

Q1: the +2R halving state must distinguish ARMED (level touched) from
    DONE (ledger shares actually at/below the halved target).  While
    armed and not done and price is still >= +2R the rule re-issues the
    halving order; the engine's risk-intent sizing is idempotent
    (already-at-target orders skip), so re-issuing cannot double-sell,
    and an order lost to override/suspension is recovered at the next
    decision point instead of silently dropping the halving leg.

Unit layer here; the full engine chain (buy -> trigger -> not
penetrated -> replaced -> refilled) is in test_single_name_rules_e2e.py.
All numbers hand-derived from the frozen parameters. Zero trial
consumption.
"""
from __future__ import annotations

from datetime import date

from quant.research.single_name_rules import SingleNameRules

D1, D2, D3, D4 = (date(2024, 1, 2 + i) for i in range(4))
SYM = "sh.600001"


def rules_with(atr: float = 0.4) -> SingleNameRules:
    # cost 10.0 -> dist 0.8 (8% in band), stop 9.2, R 0.8
    # +1R 10.8 / +2R 11.6 / +3R 12.4
    return SingleNameRules(lambda s, d: atr)


def position(clips, shares=None):
    return {"symbol": SYM, "shares": shares if shares is not None
            else sum(c["shares"] for c in clips), "clips": clips}


def clip(shares, price, acquired=D1, session="am"):
    return {"shares": shares, "acquired": acquired.isoformat(),
            "session": session, "price": price}


# ---------------------------------------------------------------------------
# C3: exit_reason attribution
# ---------------------------------------------------------------------------

def test_c3_reason_stop():
    r = rules_with()
    rows = r.decide([position([clip(10_000, 10.0)])], {SYM: 9.2},
                    day=D2, session="am")
    assert len(rows) == 1
    assert rows[0]["exit_reason"] == "stop"
    assert rows[0]["target_weight"] is None and rows[0]["target_notional"] is None


def test_c3_reason_protection():
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    assert r.decide([pos], {SYM: 10.9}, day=D1, session="pm") == []  # arm
    rows = r.decide([pos], {SYM: 10.0}, day=D2, session="am")
    assert len(rows) == 1
    assert rows[0]["exit_reason"] == "protection"


def test_c3_reason_take_half_and_clear():
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    rows = r.decide([pos], {SYM: 11.6}, day=D2, session="pm")
    assert rows[0]["exit_reason"] == "take_half"
    # +3R on a FRESH instance (no live event): keep 0 -> clear event
    # via the retained-notional form (0.0).  While a halving event is
    # live the +3R clear is deferred to the next decision point after
    # the event completes (one absolute event at a time).
    r2 = rules_with()
    rows = r2.decide([position([clip(10_000, 10.0)])], {SYM: 12.6},
                     day=D2, session="pm")
    assert len(rows) == 1
    assert rows[0]["exit_reason"] == "clear"
    assert rows[0]["target_notional"] == 0.0


def test_c3_multi_clip_mixed_ladder_reports_take_half():
    # clip A 6,000@10 (+2R at 11.6), clip B 4,000@9.0 with ATR .36 ->
    # dist .72, R .72, +3R at 11.16: at 11.7 clip A halves (keep 3,000),
    # clip B clears (keep 0) -> keep 3,000 > 0 -> take_half, not clear
    r = SingleNameRules(lambda s, d: {D1: 0.4, D2: 0.36}[d])
    pos = position([clip(6_000, 10.0, acquired=D1),
                    clip(4_000, 9.0, acquired=D2)])
    rows = r.decide([pos], {SYM: 11.7}, day=D3, session="pm")
    assert len(rows) == 1
    assert rows[0]["exit_reason"] == "take_half"
    assert rows[0]["target_notional"] == 3_000 * 11.7


# ---------------------------------------------------------------------------
# Q1: armed vs done, re-issue until the halving has landed
# ---------------------------------------------------------------------------

def test_q1_halving_reissued_while_ledger_unchanged():
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    first = r.decide([pos], {SYM: 11.6}, day=D2, session="pm")
    assert len(first) == 1
    # ledger untouched -> identical halving target again (idempotent)
    second = r.decide([pos], {SYM: 11.65}, day=D3, session="am")
    assert len(second) == 1
    assert second[0]["target_notional"] == 5_000 * 11.65
    assert second[0]["exit_reason"] == "take_half"
    diags = r.clip_diagnostics()
    st = diags[(SYM, D1.isoformat(), "am")]
    assert st["half_armed"] is True and st["half_done"] is False


def test_q1_partial_fill_still_reissues_until_target():
    r = rules_with()
    # the rule snapshots shares0 at FIRST SIGHT of the clip (in production
    # that is the buy lot): arm on the full 10,000 ...
    full = position([clip(10_000, 10.0)])
    r.decide([full], {SYM: 11.6}, day=D2, session="pm")   # arm, keep 5,000
    # ... an external order then sells 2,000: the ledger clip holds 8,000,
    # still above the 5,000 halving target -> keep re-issuing the SAME
    # keep-5,000 form
    mid = position([clip(8_000, 10.0)])
    rows = r.decide([mid], {SYM: 11.6}, day=D3, session="am")
    assert len(rows) == 1 and rows[0]["target_notional"] == 5_000 * 11.6
    # clip reaches the halved target -> done, nothing more to issue
    done_pos = position([clip(5_000, 10.0)])
    assert r.decide([done_pos], {SYM: 11.7}, day=D4, session="am") == []
    st = r.clip_diagnostics()[(SYM, D1.isoformat(), "am")]
    assert st["half_armed"] is True and st["half_done"] is True
    assert st["shares0"] == 10_000


def test_q1_armed_intent_persists_through_dip():
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    r.decide([pos], {SYM: 11.6}, day=D2, session="pm")   # arm at +2R
    # price dips to +1.5R: the halving event PERSISTS (absolute target
    # frozen at trigger); the sell order keeps pulling to keep-5,000 at
    # the CURRENT price.  Cancelling on the dip would reopen the exact
    # dropped-leg hole the audit found.
    rows = r.decide([pos], {SYM: 11.2}, day=D3, session="am")
    assert len(rows) == 1 and rows[0]["target_notional"] == 5_000 * 11.2
    st = r.clip_diagnostics()[(SYM, D1.isoformat(), "am")]
    assert st["half_armed"] is True and st["half_done"] is False


def test_q1_event_source_frozen_for_streak():
    # the K=3 fallback streak is keyed on (symbol, intent, source); a
    # re-issued halving row must carry the TRIGGER day as its source or
    # the engine treats every re-issue as a new signal and resets the
    # streak to zero (review finding 2)
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    r.decide([pos], {SYM: 11.6}, day=D2, session="pm")
    for probe_day, px in ((D3, 11.4), (D4, 11.2)):
        rows = r.decide([pos], {SYM: px}, day=probe_day, session="am")
        assert rows and rows[0]["source_signal"] == D2


def test_q1_multiclip_no_oversell_after_fifo_fill():
    # review finding 1: old batch 3,700@10 (ATR .75 -> R 1.5, +2R 13.0,
    # NOT triggered at 12.3) + new batch 4,700@11 (ATR .30 -> R .6,
    # +2R 12.2, triggered at 12.3).  Event target = 3,700 + 2,300 = 6,000
    # ABSOLUTE.  After the engine's FIFO sell of 2,400 consumed the OLD
    # batch (old 1,300 + new 4,700 = 6,000 held), the rule must see the
    # event COMPLETE -- not re-count per-clip keeps and sell again.
    atr_by_day = {D1: 0.75, D2: 0.30}
    r = SingleNameRules(lambda s, d: atr_by_day[d])
    old_c = clip(3_700, 10.0, acquired=D1)
    new_c = clip(4_700, 11.0, acquired=D2)
    pos = position([old_c, new_c])
    rows = r.decide([pos], {SYM: 12.3}, day=D3, session="am")
    assert len(rows) == 1
    assert rows[0]["target_notional"] == 6_000 * 12.3
    ev = r.events()[SYM]
    assert ev["target_shares"] == 6_000 and ev["source"] == D3
    # FIFO landed: old batch consumed down to 1,300, new batch untouched
    after = position([clip(1_300, 10.0, acquired=D1),
                      clip(4_700, 11.0, acquired=D2)])
    assert r.decide([after], {SYM: 12.3}, day=D4, session="am") == []
    st_new = r.clip_diagnostics()[(SYM, D2.isoformat(), "am")]
    assert st_new["half_armed"] is True and st_new["half_done"] is True
    st_old = r.clip_diagnostics()[(SYM, D1.isoformat(), "am")]
    assert st_old["half_armed"] is False    # never reached its own +2R
    # and no new event appears later at the same price: keep == total
    assert r.decide([after], {SYM: 12.3}, day=date(2024, 1, 5),
                    session="pm") == []


def test_q1_multiclip_second_batch_halves_later():
    # continuation of the no-oversell scenario: after the first event
    # completed (old 3,700 -> 1,300 via FIFO, new 4,700 untouched with
    # half_done), a later push to 13.1 opens a FRESH event on the OLD
    # batch's own +2R (13.0).  Note 13.1 is also past the NEW batch's
    # +3R line (12.8), so the new batch is cleared entirely in the same
    # event -- the per-clip ladder is evaluated per clip, the order is
    # always ONE absolute whole-position target.
    atr_by_day = {D1: 0.75, D2: 0.30}
    r = SingleNameRules(lambda s, d: atr_by_day[d])
    pos = position([clip(3_700, 10.0, acquired=D1),
                    clip(4_700, 11.0, acquired=D2)])
    assert len(r.decide([pos], {SYM: 12.3}, day=D3, session="am")) == 1
    after = position([clip(1_300, 10.0, acquired=D1),
                      clip(4_700, 11.0, acquired=D2)])   # FIFO landed
    assert r.decide([after], {SYM: 12.3}, day=D4, session="am") == []
    # 13.1 crosses BOTH the old batch's +2R (13.0 -> halve 1,300 to
    # half_keep_target(shares0=3,700)=1,800) and the NEW batch's +3R
    # (11+1.8=12.8 -> cleared, keep 0): target = 1,800 + 0 = 1,800
    rows = r.decide([after], {SYM: 13.1}, day=date(2024, 1, 5),
                    session="pm")
    assert len(rows) == 1
    assert rows[0]["target_notional"] == 1_800 * 13.1


def test_q1_done_judgement_is_conservative_towards_reissue():
    r = rules_with()
    full = position([clip(10_000, 10.0)])
    r.decide([full], {SYM: 11.6}, day=D2, session="pm")   # arm, keep 5,000
    # 5,100 shares is one lot above the 5,000 target: still "not done"
    # (re-issue; the engine skips the order when actually at target) ...
    above = position([clip(5_100, 10.0)])
    assert len(r.decide([above], {SYM: 11.6}, day=D3, session="am")) == 1
    # ... 5,099 (one lot below plus the boundary lot) already counts as done
    at_target = position([clip(5_099, 10.0)])
    assert r.decide([at_target], {SYM: 11.6}, day=D4, session="am") == []


def test_q1_odd_lot_halving_targets_whole_lots():
    r = rules_with()
    # 10,300 shares: keep target = (10_300 // 2 // 100) * 100 = 5,100
    pos = position([clip(10_300, 10.0)])
    rows = r.decide([pos], {SYM: 11.6}, day=D2, session="pm")
    assert rows[0]["target_notional"] == 5_100 * 11.6


# ---------------------------------------------------------------------------
# second-review findings (2026-09-21): whole-exit K=3 fallback, exit-class
# split, stale-event purge
# ---------------------------------------------------------------------------

def test_whole_exit_event_freezes_source_for_k3():
    # review finding: whole-exit rows carried source=each new decision day,
    # so the engine's (symbol, risk, source) streak reset daily and the
    # K=3 open-market fallback could never arm for stop/protection orders
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    first = r.decide([pos], {SYM: 9.2}, day=D2, session="am")
    assert len(first) == 1
    assert first[0]["source_signal"] == D2 and first[0]["intent"] == "risk"
    assert first[0]["exit_reason"] == "stop"
    # still held & unfilled the next day -- even with price back ABOVE the
    # stop: the standing whole exit re-issues with the SAME frozen source
    # (a triggered risk exit cannot un-trigger)
    again = r.decide([pos], {SYM: 9.5}, day=D3, session="am")
    assert len(again) == 1
    assert again[0]["source_signal"] == D2 and again[0]["intent"] == "risk"
    assert again[0]["exit_reason"] == "stop"
    ev = r.events()[SYM]
    assert ev["target_shares"] == 0 and ev["source"] == D2
    assert ev["reason"] == "stop"


def test_whole_event_absorbs_later_trigger_keeps_first_source():
    # a live whole event absorbs a later whole trigger (same order content
    # -- sell everything), keeping the FIRST trigger's source so the
    # engine streak is preserved; a live HALVING event is replaced by a
    # whole exit with a fresh source (a different order, a new streak)
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    r.decide([pos], {SYM: 9.2}, day=D2, session="am")      # stop event
    rows = r.decide([pos], {SYM: 9.0}, day=D3, session="am")
    assert rows[0]["source_signal"] == D2 and rows[0]["exit_reason"] == "stop"

    r2 = rules_with()
    r2.decide([pos], {SYM: 11.6}, day=D2, session="pm")    # halving event
    rows = r2.decide([pos], {SYM: 9.2}, day=D3, session="am")
    assert rows[0]["exit_reason"] == "stop" and rows[0]["source_signal"] == D3
    ev = r2.events()[SYM]
    assert ev["target_shares"] == 0 and ev["source"] == D3


def test_purge_on_external_full_exit():
    # review finding: a position sold out externally (account trim etc.)
    # kept a stale halving event in module state; a later re-entry ABOVE
    # the old target got smashed down by the stale trigger-day target
    r = rules_with()
    pos = position([clip(10_000, 10.0)])
    r.decide([pos], {SYM: 11.6}, day=D2, session="pm")     # target 5,000
    # the symbol leaves the ledger entirely -> all state purged
    assert r.decide([], {}, day=D3, session="am") == []
    assert r.events() == {} and r.clip_diagnostics() == {}
    # re-entry 8,000 @ 11.0, price 11.3 below its own +1R (11.8): the
    # stale keep-5,000 event must NOT resurface and sell 3,000
    reentry = position([clip(8_000, 11.0, acquired=D4)])
    assert r.decide([reentry], {SYM: 11.3}, day=D4, session="pm") == []
    assert r.events() == {}


def test_exit_reason_intent_classes():
    # AGENTS section 1 / engine contract: risk-reduction orders
    # (stop/protection) ride intent='risk' (K=3 open-market fallback);
    # profit-taking orders (take_half/clear) ride intent='profit'
    # (expire each half-day; persistence comes from module re-issue)
    pos = position([clip(10_000, 10.0)])
    r = rules_with()
    assert r.decide([pos], {SYM: 9.2}, day=D2, session="am")[0]["intent"] == "risk"
    r2 = rules_with()
    r2.decide([pos], {SYM: 10.9}, day=D1, session="pm")    # arm +1R
    assert r2.decide([pos], {SYM: 10.0}, day=D2, session="am")[0]["intent"] == "risk"
    r3 = rules_with()
    assert r3.decide([pos], {SYM: 11.6}, day=D2, session="pm")[0]["intent"] == "profit"
    r4 = rules_with()
    assert r4.decide([pos], {SYM: 12.6}, day=D2, session="pm")[0]["intent"] == "profit"


# ---------------------------------------------------------------------------
# phase-B registered perturbation (2): trailing protection after +1R
# (3R clear OFF, fixed cost-protect replaced by the ratcheting trail)
# ---------------------------------------------------------------------------

def test_trail_mode_replaces_protection_line():
    highs: dict = {}
    r = SingleNameRules(lambda s, d: 0.4, trail_after_1r=True,
                        high20_getter=lambda s, d: highs.get(d))
    pos = position([clip(10_000, 10.0)])
    highs[D1] = 11.0                       # trail line = 11.0 - 0.4 = 10.6
    assert r.decide([pos], {SYM: 10.9}, day=D1, session="pm") == []  # +1R
    # 10.0 sits at cost: default mode fires protection here; trail mode
    # exits via the TRAILING line instead
    rows = r.decide([pos], {SYM: 10.0}, day=D2, session="am")
    assert rows and rows[0]["exit_reason"] == "trail"
    assert rows[0]["intent"] == "risk"


def test_trail_mode_no_3r_clear_and_ratchet():
    highs: dict = {}
    r = SingleNameRules(lambda s, d: 0.4, trail_after_1r=True,
                        high20_getter=lambda s, d: highs.get(d))
    pos = position([clip(10_000, 10.0)])
    highs[D1] = 12.5                       # line = 12.1; price 12.5 > +3R
    rows = r.decide([pos], {SYM: 12.5}, day=D1, session="pm")
    # the fixed +3R clear is OFF in trail mode; only the +2R half may fire
    assert all(x["exit_reason"] != "clear" for x in rows)
    assert [x["exit_reason"] for x in rows] in (["take_half"], [])
    # ratchet: a lower later high must NOT lower the line; 12.0 is above
    # cost (no default-mode protection) but below the ratcheted 12.1
    highs[D2] = 11.5                       # naive recompute would give 11.1
    rows2 = r.decide([pos], {SYM: 12.0}, day=D2, session="am")
    assert rows2 and rows2[-1]["exit_reason"] == "trail"
