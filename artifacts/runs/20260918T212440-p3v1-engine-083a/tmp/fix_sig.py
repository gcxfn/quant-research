# -*- coding: utf-8 -*-
"""Fix the builder's local sig to the test-file convention (decision_session
3rd, side 4th, anchor 5th)."""
from pathlib import Path

p = Path('artifacts/runs/20260918T212440-p3v1-engine-083a/tmp/build_v1.py')
src = p.read_text(encoding='utf-8')
old = """def sig(symbol, decision_date, side, anchor, priority=1, intent=None,
        target=None, shares=None, decision_session='pm'):
    return {'symbol': symbol, 'decision_date': decision_date, 'side': side,
            'intent': intent, 'decision_session': decision_session,
            'anchor_price': float(anchor), 'priority': priority,
            'target_notional': None if target is None else float(target),
            'shares': shares}"""
new = """def sig(symbol, decision_date, decision_session, side, anchor,
        priority=1, *, intent=None, target=None, shares=None):
    return {'symbol': symbol, 'decision_date': decision_date,
            'decision_session': decision_session, 'side': side,
            'anchor_price': float(anchor), 'priority': priority,
            'intent': intent,
            'target_notional': None if target is None else float(target),
            'shares': shares}"""
assert old in src
p.write_text(src.replace(old, new, 1), encoding='utf-8')
print('sig fixed')
