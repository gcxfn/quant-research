"""Synthetic hand-checked tests for SingleNameRules (fixed-scheme prereg §4).

All numbers hand-derived from the frozen parameters: stop = cost - 2*ATR20
clamped to [5%,15%] of cost; R = cost - stop; +1R arms the protection line
(line = cost); +2R sells half the clip; +3R clears; ANY stop/protection
trigger exits the whole symbol. Zero trial consumption.
"""
from __future__ import annotations

from datetime import date

from quant.research.single_name_rules import SingleNameRules

D1, D2, D3 = (date(2024, 1, 2 + i) for i in range(3))
SYM = "sh.600001"


def rules_with(atr: float) -> SingleNameRules:
    return SingleNameRules(lambda s, d: atr)


def position(clips, shares=None):
    return {"symbol": SYM, "shares": shares if shares is not None
            else sum(c["shares"] for c in clips), "clips": clips}


def clip(shares, price, acquired=D1, session="am"):
    return {"shares": shares, "acquired": acquired.isoformat(),
            "session": session, "price": price}


def test_t1_full_lifecycle_hand_check():
    r = rules_with(atr=0.4)   # cost 10.0 -> dist 0.8 (8% in band), stop 9.2, R 0.8
    pos = position([clip(10_000, 10.0)])

    # +1.125R: arms protection, no exit
    assert r.decide([pos], {SYM: 10.9}, day=D2, session="pm") == []

    # +2.0R exactly: sell half -> keep 5,000; retained-notional 5,000*11.6
    rows = r.decide([pos], {SYM: 11.6}, day=D2, session="pm")
    assert len(rows) == 1
    row = rows[0]
    assert row["side"] == "sell" and row["intent"] == "risk"
    assert row["target_weight"] is None
    assert row["target_notional"] == 5_000 * 11.6
    # half_taken latches: same price next point emits nothing
    assert r.decide([pos], {SYM: 11.6}, day=D3, session="am") == []

    # +3.25R: clear everything (half already taken, remaining clip cleared)
    rows = r.decide([pos], {SYM: 12.6}, day=D3, session="pm")
    assert len(rows) == 1 and rows[0]["target_weight"] is None  # full exit


def test_t2_stop_and_protection_line():
    # fresh instance: stop hit at 9.2 -> whole-symbol exit
    r = rules_with(atr=0.4)
    pos = position([clip(10_000, 10.0)])
    rows = r.decide([pos], {SYM: 9.2}, day=D2, session="am")
    assert len(rows) == 1 and rows[0]["target_weight"] is None

    # protection line: arm at +1R, then fall back to cost -> whole exit
    r2 = rules_with(atr=0.4)
    assert r2.decide([pos], {SYM: 10.81}, day=D1, session="pm") == []
    rows = r2.decide([pos], {SYM: 10.0}, day=D2, session="am")
    assert len(rows) == 1 and rows[0]["target_weight"] is None

    # WITHOUT the +1R arm, cost-touch is NOT an exit
    r3 = rules_with(atr=0.4)
    assert r3.decide([pos], {SYM: 10.0}, day=D2, session="am") == []


def test_t3_atr_clamps():
    # cost 10, ATR 2.0 -> raw 20% clamped to 15% -> stop 8.5
    r = rules_with(atr=2.0)
    pos = position([clip(10_000, 10.0)])
    assert r.decide([pos], {SYM: 8.6}, day=D2, session="pm") == []
    assert len(r.decide([pos], {SYM: 8.5}, day=D3, session="am")) == 1
    # cost 10, ATR 0.1 -> raw 1% clamped to 5% -> stop 9.5
    r2 = rules_with(atr=0.1)
    assert r2.decide([pos], {SYM: 9.51}, day=D2, session="pm") == []
    assert len(r2.decide([pos], {SYM: 9.5}, day=D3, session="am")) == 1


def test_t4_multi_clip_any_stop_exits_all():
    # clip A: 6,000 @10.0 (ATR .4 -> stop 9.2); clip B: 4,000 @9.0
    # (ATR .36 -> dist .72, stop 8.28). P = 9.1 <= 9.2 -> whole exit.
    r = rules_with(atr=0.4)
    atr_by_price = {10.0: 0.4, 9.0: 0.36}
    r2 = SingleNameRules(
        lambda s, d: {D1: 0.4, D2: 0.36}[d])
    pos = position([clip(6_000, 10.0, acquired=D1),
                    clip(4_000, 9.0, acquired=D2)])
    rows = r2.decide([pos], {SYM: 9.1}, day=D3, session="pm")
    assert len(rows) == 1 and rows[0]["target_weight"] is None


def test_t5_bonus_clip_and_partial_keep():
    # bonus clip (price 0) participates in whole exits but has no R ladder;
    # paid clip at +2R halves itself only
    r = SingleNameRules(lambda s, d: 0.4)
    pos = position([clip(6_000, 10.0, acquired=D1),
                    clip(2_000, 0.0, acquired=D1)])
    rows = r.decide([pos], {SYM: 11.6}, day=D2, session="pm")
    assert len(rows) == 1
    # keep = 3,000 paid + 2,000 bonus = 5,000
    assert rows[0]["target_notional"] == 5_000 * 11.6
