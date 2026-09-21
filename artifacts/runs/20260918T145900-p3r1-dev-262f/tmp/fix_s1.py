# -*- coding: utf-8 -*-
from pathlib import Path

p = Path('artifacts/runs/20260918T212440-p3v1-engine-083a/tmp/build_v1.py')
src = p.read_text(encoding='utf-8')
old = """res1 = run([sig('E', D(2024, 6, 3), 'am', 'buy', 5.00, 1, target=10_000),
            sig('E', D(2024, 6, 3), 'am', 'sell', 5.10, intent='risk')],
           half1, instruments=t.instruments_frame([('E', True, True)]))"""
new = """res1 = run([sig('E', D(2024, 6, 2), 'pm', 'buy', 5.00, target=10_000),
            sig('E', D(2024, 6, 3), 'am', 'sell', 5.10, intent='risk')],
           half1, instruments=t.instruments_frame([('E', True, True)]))"""
assert old in src, 'call'
src = src.replace(old, new, 1)
old2 = """half1 = bars('E', [(D(2024, 6, 3), 'am', 5.00, 5.02, 4.98, 5.00),
                   (D(2024, 6, 3), 'pm', 5.00, 5.15, 4.98, 5.10)])"""
new2 = """half1 = bars('E', [(D(2024, 6, 2), 'pm', 5.02, 5.04, 4.98, 5.00),
                   (D(2024, 6, 3), 'am', 5.00, 5.02, 4.98, 5.10)])"""
assert old2 in src, 'bars'
src = src.replace(old2, new2, 1)
p.write_text(src, encoding='utf-8')
print('sample 1 timeline fixed: buy 06-02 pm decision -> 06-03 am fill')
