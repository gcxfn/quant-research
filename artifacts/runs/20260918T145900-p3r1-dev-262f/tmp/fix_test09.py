# -*- coding: utf-8 -*-
"""Rewrite test_09 (cap-consistent; explicit daily OHLC containing halfday ranges)."""
from pathlib import Path
from datetime import date
import ast

p = Path('tests/test_band_contract.py')
src = p.read_text(encoding='utf-8')
start = src.index('def test_09_proceeds_timing():')
end = src.index('# ---------------------------------------------------------------------------\n'
                '# item 10:')

D = date


def dl(d):
    return 'D(%d, %d, %d)' % (d.year, d.month, d.day)


# daily OHLC: (date, o, h, l, c) -- h/l contain the half-day extremes
daily_ohlc = {
    'P1': [(date(2016, 9, 1), 150.0, 150.1, 149.9, 150.0),
           (date(2016, 9, 2), 150.05, 150.1, 149.9, 150.0),
           (date(2016, 9, 5), 150.02, 150.08, 149.95, 150.0),
           (date(2016, 9, 6), 150.5, 151.0, 149.9, 150.0),
           (date(2016, 9, 7), 150.9, 151.2, 150.7, 151.0),
           (date(2016, 9, 8), 150.5, 150.55, 150.4, 150.5)],
    'P2': [(date(2016, 9, 1), 60.0, 60.1, 59.9, 60.0),
           (date(2016, 9, 2), 60.05, 60.1, 59.9, 60.0),
           (date(2016, 9, 5), 60.02, 60.08, 59.95, 60.0),
           (date(2016, 9, 6), 60.1, 60.3, 59.9, 60.0),
           (date(2016, 9, 7), 60.1, 60.3, 59.9, 60.0),
           (date(2016, 9, 8), 60.0, 60.1, 59.9, 60.0)],
    'P4': [(date(2016, 9, 1), 50.0, 50.1, 49.9, 50.0),
           (date(2016, 9, 2), 50.05, 50.1, 49.9, 50.0),
           (date(2016, 9, 5), 50.02, 50.08, 49.95, 50.0),
           (date(2016, 9, 6), 50.0, 50.1, 49.9, 50.0),
           (date(2016, 9, 7), 50.0, 50.1, 49.9, 50.0),
           (date(2016, 9, 8), 50.0, 50.1, 49.9, 50.0)],
    'P5': [(date(2016, 9, 1), 50.0, 50.1, 49.9, 50.0),
           (date(2016, 9, 2), 50.05, 50.1, 49.9, 50.0),
           (date(2016, 9, 5), 50.02, 50.08, 49.95, 50.0),
           (date(2016, 9, 6), 50.0, 50.1, 49.9, 50.0),
           (date(2016, 9, 7), 50.0, 50.1, 49.9, 50.0),
           (date(2016, 9, 8), 50.0, 50.1, 49.9, 50.0)],
}
# halfday: (date, session, o, h, l, c) -- pm close == daily close
half_ohlc = {
    'P1': [(date(2016, 9, 2), 'am', 150.02, 150.08, 149.90, 150.0),
           (date(2016, 9, 2), 'pm', 150.0, 150.05, 149.95, 150.0),
           (date(2016, 9, 6), 'am', 150.5, 151.0, 149.90, 150.0),
           (date(2016, 9, 6), 'pm', 150.1, 150.2, 149.95, 150.0)],
    'P2': [(date(2016, 9, 2), 'am', 60.02, 60.08, 59.90, 60.0),
           (date(2016, 9, 2), 'pm', 60.0, 60.05, 59.95, 60.0),
           (date(2016, 9, 5), 'am', 60.0, 60.05, 59.95, 60.0),
           (date(2016, 9, 5), 'pm', 60.0, 60.05, 59.95, 60.0),
           (date(2016, 9, 6), 'am', 60.1, 60.3, 59.90, 60.0),
           (date(2016, 9, 6), 'pm', 60.0, 60.2, 59.90, 60.0),
           (date(2016, 9, 7), 'am', 60.1, 60.3, 59.90, 60.0),
           (date(2016, 9, 7), 'pm', 60.0, 60.2, 59.90, 60.0),
           (date(2016, 9, 8), 'am', 60.0, 60.1, 59.90, 60.0),
           (date(2016, 9, 8), 'pm', 60.0, 60.1, 59.90, 60.0)],
    'P4': [(date(2016, 9, 2), 'am', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 2), 'pm', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 5), 'am', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 5), 'pm', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 6), 'am', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 6), 'pm', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 7), 'am', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 7), 'pm', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 8), 'am', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 8), 'pm', 50.0, 50.05, 49.95, 50.0)],
    'P5': [(date(2016, 9, 2), 'am', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 2), 'pm', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 5), 'am', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 5), 'pm', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 6), 'am', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 6), 'pm', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 7), 'am', 50.0, 50.05, 49.95, 50.0),
           (date(2016, 9, 7), 'pm', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 8), 'am', 50.0, 50.05, 49.90, 50.0),
           (date(2016, 9, 8), 'pm', 50.0, 50.05, 49.90, 50.0)],
}

out = []
out.append("def test_09_proceeds_timing():")
out.append('    """Section 7.2 cash timing: am-fill proceeds are usable from the SAME')
out.append("    day's pm session (P5's re-issued buy is only affordable after the")
out.append("    am-sell release); pm-fill proceeds release the NEXT day's am (P2 sell")
out.append('    -> pending carried overnight).  A same-session sell->buy path is')
out.append('    forbidden: P2\'s first add live 09-06 am sees only 42,975 even though')
out.append('    89,900 of am-sell proceeds are pending that very session."""')
out.append("    daily = pl.concat([")
for sym, rows in daily_ohlc.items():
    rows_src = ", ".join(
        "(%s, %.2f, %.2f, %.2f, %.2f)" % (dl(d), o, h, l, c) for d, o, h, l, c in rows)
    out.append("        daily_bars('%s', [%s])," % (sym, rows_src))
out.append("    ])")
out.append("    half = pl.concat([")
for sym, rows in half_ohlc.items():
    rows_src = ", ".join(
        "(%s, '%s', %.2f, %.2f, %.2f, %.2f)" % (dl(d), s, o, h, l, c)
        for d, s, o, h, l, c in rows)
    out.append("        half_bars('%s', [%s])," % (sym, rows_src))
out.append("    ])")
out.append("    signals = [")
out.append("        # setup (all live 09-02 am, all under the 25% single-name cap)")
out.append("        sig('P1', D(2016, 9, 1), 'pm', 'buy', 150.0, 1, shares=300),")
out.append("        sig('P2', D(2016, 9, 1), 'pm', 'buy', 60.0, 2, shares=700),")
out.append("        sig('P4', D(2016, 9, 1), 'pm', 'buy', 50.0, 3, shares=900),")
out.append("        sig('P5', D(2016, 9, 1), 'pm', 'buy', 50.0, 4, shares=500),")
out.append("        # 09-05 pm decisions, live 09-06 am:")
out.append("        sig('P1', D(2016, 9, 5), 'pm', 'sell', 150.0, 1, intent='risk'),")
out.append("        sig('P2', D(2016, 9, 5), 'pm', 'buy', 60.0, 1, shares=480),")
out.append("        sig('P5', D(2016, 9, 5), 'pm', 'buy', 60.0, 2, shares=1000),")
out.append("        # 09-06 am decision, live 09-06 pm:")
out.append("        sig('P5', D(2016, 9, 6), 'am', 'buy', 60.0, 1, shares=1000),")
out.append("        # 09-06 pm decision, live 09-07 am:")
out.append("        sig('P2', D(2016, 9, 6), 'pm', 'sell', 60.0, 1, intent='risk'),")
out.append("    ]")
out.append("    res = run(signals, daily, half)")
body = "\n".join(out)

body += '''
    # setup: cash 200,000 - 163,020 = 36,980
    #   (P1 45,005 + P2 42,010 + P4 45,005 + P5 25,005)
    d2 = res.daily.filter(pl.col('date') == D(2016, 9, 2)).row(0, named=True)
    assert d2['settled_cash'] == pytest.approx(36_980.0)
    # (a) same-session prohibition: the 09-06 am sells fill (P1 +44,950
    #     pending) but P2's 48,005 add sees only 42,975 of cash ->
    #     void_insufficient_cash (same-session sell->buy forbidden)
    v = res.events.filter((pl.col('symbol') == 'P2')
                          & (pl.col('date') == D(2016, 9, 6))
                          & (pl.col('session') == 'am'))
    assert v['event'].to_list() == ['void_insufficient_cash']
    p1s = res.fills.filter((pl.col('symbol') == 'P1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (p1s['date'], p1s['session'], p1s['shares']) == \\
        (D(2016, 9, 6), 'am', 300)
    # (b) am proceeds release at pm: P5's re-issued 50,005 buy fills 09-06 pm
    p5 = res.fills.filter((pl.col('symbol') == 'P5')
                          & (pl.col('side') == 'buy')).to_dicts()
    assert [(r['date'], r['session'], r['shares']) for r in p5] == \\
        [(D(2016, 9, 6), 'pm', 1000)]
    d6 = res.daily.filter(pl.col('date') == D(2016, 9, 6)).row(0, named=True)
    assert d6['settled_cash'] == pytest.approx(37_920.0)
    # (c) pm proceeds release NEXT day: P2's 09-07 am sell is pending 09-07
    p2s = res.fills.filter((pl.col('symbol') == 'P2')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (p2s['date'], p2s['session']) == (D(2016, 9, 7), 'am')
    d7 = res.daily.filter(pl.col('date') == D(2016, 9, 7)).row(0, named=True)
    assert d7['pending_next_day'] == pytest.approx(47_947.0)
    d8 = res.daily.filter(pl.col('date') == D(2016, 9, 8)).row(0, named=True)
    assert d8['settled_cash'] == pytest.approx(37_920.0 + 47_947.0)
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 1
'''

src = src[:start] + body + src[end:]
p.write_text(src, encoding='utf-8')
ast.parse(src)
print('test_09 rewritten; syntax OK')
