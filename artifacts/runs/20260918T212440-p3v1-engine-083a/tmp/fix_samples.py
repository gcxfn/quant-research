# -*- coding: utf-8 -*-
"""Clean up builder samples 1-4: consistent sig convention, correct fixtures."""
from pathlib import Path
import ast

p = Path('artifacts/runs/20260918T212440-p3v1-engine-083a/tmp/build_v1.py')
src = p.read_text(encoding='utf-8')
start = src.index('# ---- sample 1:')
end = src.index('# ---------------------------------------------------------------------\n'
                '# 3. manifest')
new = '''# ---- sample 1: T+0 same-day round trip (S_am buy -> S_pm sell) ----------
half1 = bars('E', [(D(2024, 6, 2), 'pm', 5.02, 5.04, 4.98, 5.00),
                   (D(2024, 6, 3), 'am', 5.00, 5.02, 4.98, 5.00),
                   (D(2024, 6, 3), 'pm', 5.00, 5.15, 4.98, 5.10)])
res1 = run([sig('E', D(2024, 6, 2), 'pm', 'buy', 5.00, target=10_000),
            sig('E', D(2024, 6, 3), 'am', 'sell', 5.10, intent='risk')],
           half1, instruments=t.instruments_frame([('E', True, True)]))
eb = res1.fills.filter(pl.col('side') == 'buy').row(0, named=True)
es = res1.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (eb['date'], eb['session'], eb['shares'], eb['price']) == \\
    (D(2024, 6, 3), 'am', 2000, 5.0)
assert (es['date'], es['session'], es['shares'], es['price']) == \\
    (D(2024, 6, 3), 'pm', 2000, 5.10)
close(eb['stamp_tax'], 0.0)          # ETF: exempt
close(es['stamp_tax'], 0.0)
d_am = res1.daily.filter(pl.col('date') == D(2024, 6, 3)).row(0, named=True)
close(d_am['settled_cash'], 189_995.0)
close(d_am['pending_next_day'], 10_395.0)
close(res1.daily[1, 'settled_cash'], 189_995.0 + 10_395.0)
log('  1 T+0 round trip verified')

# ---- sample 2: session settlement (am proceeds -> same-day pm buy) ------
half2 = bars('F', [(D(2024, 3, 4), 'am', 10.02, 10.05, 9.90, 10.00),
                   (D(2024, 3, 4), 'pm', 10.00, 10.05, 9.95, 10.00),
                   (D(2024, 3, 5), 'am', 10.00, 10.05, 9.95, 10.00),
                   (D(2024, 3, 5), 'pm', 10.00, 10.05, 9.95, 10.00)])
res2 = run([sig('F', D(2024, 3, 3), 'pm', 'buy', 10.00, target=10_000),
            sig('F', D(2024, 3, 4), 'am', 'sell', 10.05, intent='risk')],
           half2)
b2 = res2.fills.filter(pl.col('side') == 'buy').row(0, named=True)
s2 = res2.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (b2['date'], b2['session']) == (D(2024, 3, 4), 'am')
assert (s2['date'], s2['session'], s2['price']) == (D(2024, 3, 5), 'am', 10.0)
d5 = res2.daily.filter(pl.col('date') == D(2024, 3, 5)).row(0, named=True)
close(d5['pending_am_to_pm'], 9_985.0)
log('  2 session settlement verified')

# ---- sample 3: K=3 session fallback (risk intent, 3 unfilled sessions) ---
half3 = bars('K', [(D(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
                   (D(2016, 6, 1), 'pm', 30.0, 30.1, 29.95, 30.0),
                   (D(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
                   (D(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
                   (D(2016, 6, 3), 'am', 27.5, 27.5, 27.0, 27.4),
                   (D(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4)])
res3 = run([sig('K', D(2016, 5, 31), 'pm', 'buy', 30.0, 1, target=30_000),
            sig('K', D(2016, 6, 1), 'pm', 'sell', 30.0, 1, intent='risk')],
           half3)
streaks = res3.events.filter(pl.col('event') == 'not_penetrated')
assert streaks.height == 3
kf = res3.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (kf['fill_type'], kf['date'], kf['price'], kf['shares']) == \\
    ('market_fallback', D(2016, 6, 3), 27.5, 1000)
close(kf['net_cash_flow'], 27_500.0 - 5.0 - 27.5)
close(res3.stats['k3_fallback']['pnl_contribution_total'], 27_467.5 - 28_500.0)
log('  3 K=3 fallback verified (3 sessions -> open exit)')

# ---- sample 4: close bridge (official daily close is the mark) ----------
half4 = bars('G', [(D(2017, 5, 23), 'pm', 15.9, 15.98, 15.85, 15.9),
                   (D(2017, 5, 24), 'am', 15.95, 16.05, 15.85, 15.9),
                   (D(2017, 5, 24), 'pm', 15.9, 16.0, 15.80, 15.85)])
res4 = run([sig('G', D(2017, 5, 23), 'pm', 'buy', 15.9, 1, shares=1000),
            sig('G', D(2017, 5, 24), 'pm', 'sell', 15.9, 1, intent='risk')],
           half4)
d24 = res4.daily.filter(pl.col('date') == D(2017, 5, 24)).row(0, named=True)
# mark = OFFICIAL daily close 16.0 (pre-2018-08-20 cutoff: NOT pm.close 15.85)
close(d24['positions_value'], 1000 * 16.0)
close(d24['equity'], 200_000.0 - 15_905.0 + 16_000.0)
log('  4 close bridge verified (mark = official daily close 16.0)')
handcalc_ok = True
log('== hand-calc samples all verified ==')

'''
