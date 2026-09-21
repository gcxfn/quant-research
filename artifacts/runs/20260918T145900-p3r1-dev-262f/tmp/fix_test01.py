# -*- coding: utf-8 -*-
"""Rewrite test_01 with anchor-consistent sells and a T+1-clean timeline."""
from pathlib import Path

p = Path('tests/test_band_contract.py')
src = p.read_text(encoding='utf-8')

start = src.index('def test_01_fee_conservation():')
end = src.index('# ---------------------------------------------------------------------------\n'
                '# item 2 (v1): clip-level T+1')
new = '''def test_01_fee_conservation():
    daily = pl.concat([
        daily_bars('S1', [(D(2023, 8, 24), 10.0, 10.1, 9.9, 10.0),
                          (D(2023, 8, 25), 10.02, 10.08, 9.90, 10.0),
                          (D(2023, 8, 28), 10.3, 10.45, 10.25, 10.0),
                          (D(2023, 8, 29), 10.0, 10.05, 9.95, 10.0),
                          (D(2023, 8, 30), 10.0, 10.05, 9.95, 10.0)]),
        daily_bars('S2', [(D(2023, 8, 23), 20.0, 20.05, 19.9, 20.0),
                          (D(2023, 8, 24), 20.0, 20.1, 19.9, 20.0),
                          (D(2023, 8, 25), 20.0, 20.8, 19.50, 20.0),
                          (D(2023, 8, 28), 20.0, 20.05, 19.95, 20.0),
                          (D(2023, 8, 29), 20.0, 20.05, 19.95, 20.0),
                          (D(2023, 8, 30), 20.0, 20.05, 19.95, 20.0)]),
        daily_bars('E1', [(D(2023, 8, 24), 5.0, 5.05, 4.95, 5.0),
                          (D(2023, 8, 25), 5.0, 5.02, 4.95, 5.0),
                          (D(2023, 8, 28), 5.2, 5.3, 5.15, 5.2),
                          (D(2023, 8, 29), 5.2, 5.25, 5.15, 5.2),
                          (D(2023, 8, 30), 5.2, 5.25, 5.15, 5.2)]),
        daily_bars('S3', [(D(2023, 8, 28), 30.05, 30.1, 29.9, 30.0),
                          (D(2023, 8, 29), 30.02, 30.08, 29.90, 30.0),
                          (D(2023, 8, 30), 30.0, 30.1, 29.9, 30.0)]),
    ])
    half = pl.concat([
        half_bars('S1', [(D(2023, 8, 25), 'am', 10.02, 10.08, 9.90, 10.0),
                         (D(2023, 8, 25), 'pm', 10.0, 10.05, 9.98, 10.0),
                         (D(2023, 8, 28), 'am', 10.0, 10.45, 10.25, 10.0),
                         (D(2023, 8, 28), 'pm', 10.0, 10.05, 9.98, 10.0),
                         (D(2023, 8, 29), 'am', 10.0, 10.02, 9.98, 10.0),
                         (D(2023, 8, 29), 'pm', 10.0, 10.02, 9.98, 10.0),
                         (D(2023, 8, 30), 'am', 10.0, 10.02, 9.98, 10.0),
                         (D(2023, 8, 30), 'pm', 10.0, 10.02, 9.98, 10.0)]),
        half_bars('S2', [(D(2023, 8, 24), 'am', 20.02, 20.05, 19.90, 20.0),
                         (D(2023, 8, 24), 'pm', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 25), 'am', 20.02, 20.08, 19.50, 20.0),
                         (D(2023, 8, 25), 'pm', 20.0, 20.8, 19.98, 20.0),
                         (D(2023, 8, 28), 'am', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 28), 'pm', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 29), 'am', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 29), 'pm', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 30), 'am', 20.0, 20.05, 19.95, 20.0),
                         (D(2023, 8, 30), 'pm', 20.0, 20.05, 19.95, 20.0)]),
        half_bars('E1', [(D(2023, 8, 25), 'am', 4.99, 5.01, 4.95, 5.0),
                         (D(2023, 8, 25), 'pm', 5.0, 5.02, 4.98, 5.0),
                         (D(2023, 8, 28), 'am', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 28), 'pm', 5.2, 5.30, 5.18, 5.2),
                         (D(2023, 8, 29), 'am', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 29), 'pm', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 30), 'am', 5.2, 5.22, 5.18, 5.2),
                         (D(2023, 8, 30), 'pm', 5.2, 5.22, 5.18, 5.2)]),
        half_bars('S3', [(D(2023, 8, 29), 'am', 30.02, 30.08, 29.90, 30.0),
                         (D(2023, 8, 29), 'pm', 30.0, 30.05, 29.95, 30.0),
                         (D(2023, 8, 30), 'am', 30.0, 30.05, 29.95, 30.0),
                         (D(2023, 8, 30), 'pm', 30.0, 30.05, 29.95, 30.0)]),
    ])
    instruments = instruments_frame([('E1', True, False)])
    signals = [
        sig('S2', D(2023, 8, 23), 'pm', 'buy', 20.00, 1, target=20_000),
        sig('S1', D(2023, 8, 24), 'pm', 'buy', 10.00, 1, target=15_000),
        sig('E1', D(2023, 8, 24), 'pm', 'buy', 5.00, 1, target=10_000),
        sig('S2', D(2023, 8, 25), 'am', 'sell', 20.00, 1, intent='risk'),
        sig('S1', D(2023, 8, 25), 'pm', 'sell', 10.00, 1, intent='risk'),
        sig('E1', D(2023, 8, 28), 'am', 'sell', 5.20, 1, intent='profit'),
        sig('S3', D(2023, 8, 28), 'pm', 'buy', 30.00, 1, target=60_000),
    ]
    res = run(signals, daily, half, instruments=instruments)

    assert res.fills.height == 7
    # -- independent per-fill fee re-derivation (the fee-conservation core) --
    for row in res.fills.iter_rows(named=True):
        notional = row['price'] * row['shares']
        assert row['notional'] == pytest.approx(notional, abs=1e-9)
        commission = max(1e-4 * notional, 5.0)
        if row['side'] == 'sell':
            stamp = 0.0 if row['is_etf'] else \\
                (0.001 if row['date'] < D(2023, 8, 28) else 0.0005) * notional
        else:
            stamp = 0.0
        assert row['commission'] == pytest.approx(commission, abs=1e-9), row
        assert row['stamp_tax'] == pytest.approx(stamp, abs=1e-9), row
        expected_net = (-notional - commission if row['side'] == 'buy'
                        else notional - commission - stamp)
        assert row['net_cash_flow'] == pytest.approx(expected_net, abs=1e-9)
    # hand-checked rows: anchors are the section 7.4 references and fills are
    # AT the limit
    s1b = res.fills.filter((pl.col('symbol') == 'S1')
                           & (pl.col('side') == 'buy')).row(0, named=True)
    assert (s1b['shares'], s1b['price'], s1b['commission'],
            s1b['session']) == (1500, 10.0, 5.0, 'am')
    s1s = res.fills.filter((pl.col('symbol') == 'S1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (s1s['date'], s1s['price'], s1s['stamp_tax']) == \\
        (D(2023, 8, 28), 10.0, 15000.0 * 0.0005)       # on/after boundary
    s2s = res.fills.filter((pl.col('symbol') == 'S2')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert (s2s['date'], s2s['session'], s2s['price'], s2s['stamp_tax']) == \\
        (D(2023, 8, 25), 'pm', 20.0, 20000.0 * 0.001)  # before boundary
    e1s = res.fills.filter((pl.col('symbol') == 'E1')
                           & (pl.col('side') == 'sell')).row(0, named=True)
    assert e1s['stamp_tax'] == 0.0 and e1s['is_etf']   # v1 ETF exemption
    s3b = res.fills.filter((pl.col('symbol') == 'S3')).row(0, named=True)
    assert s3b['commission'] == pytest.approx(6.0)     # max(1e-4*60000, 5)
    assert res.stats['commission_warnings'] == 1       # S3 notional 60,000
    assert not [w for w in res.warnings if 'anchor mismatch' in w]

    # -- session-level cash/pending ledger rebuilt from fills alone ----------
    calendar = res.daily['date'].to_list()
    cash = 200_000.0
    pend_am, pend_nd = 0.0, 0.0
    qty = {}
    daily_marks = {}
    for key, part in daily.partition_by('symbol', as_dict=True).items():
        daily_marks[key[0]] = dict(zip(part['date'].to_list(),
                                       part['close'].to_list()))
    for day in calendar:
        cash += pend_nd
        pend_nd = 0.0
        cash += pend_am
        pend_am = 0.0
        for row in res.fills.iter_rows(named=True):
            if row['date'] != day:
                continue
            if row['side'] == 'buy':
                cash += row['net_cash_flow']
                qty[row['symbol']] = qty.get(row['symbol'], 0) + row['shares']
            else:
                if row['session'] == 'am':
                    pend_am += row['net_cash_flow']     # usable same-day pm
                else:
                    pend_nd += row['net_cash_flow']     # usable next day am
                qty[row['symbol']] = qty.get(row['symbol'], 0) - row['shares']
        mv = sum(n * daily_marks[sym][max(d for d in daily_marks[sym] if d <= day)]
                 for sym, n in qty.items() if n)
        row = res.daily.filter(pl.col('date') == day).row(0, named=True)
        assert row['settled_cash'] == pytest.approx(cash, abs=1e-9), (day, row)
        assert row['pending_am_to_pm'] == pytest.approx(pend_am, abs=1e-9)
        assert row['pending_next_day'] == pytest.approx(pend_nd, abs=1e-9)
        assert row['equity'] == pytest.approx(cash + pend_am + pend_nd + mv,
                                              abs=1e-9)
    # hand-checked milestones
    d25 = res.daily.filter(pl.col('date') == D(2023, 8, 25)).row(0, named=True)
    assert d25['settled_cash'] == pytest.approx(
        200_000.0 - 20_005.0 - 15_005.0 - 10_005.0)
    assert d25['pending_next_day'] == pytest.approx(19_975.0)  # S2 pm sell
    d28 = res.daily.filter(pl.col('date') == D(2023, 8, 28)).row(0, named=True)
    assert d28['settled_cash'] == pytest.approx(
        154_985.0 + 19_975.0 + 14_987.5)
    assert d28['pending_next_day'] == pytest.approx(10_395.0)  # pm ETF sell
    d29 = res.daily.filter(pl.col('date') == D(2023, 8, 29)).row(0, named=True)
    assert d29['settled_cash'] == pytest.approx(
        189_947.5 + 10_395.0 - 60_006.0)


'''
src = src[:start] + new + src[end:]

# remove the duplicated events_of definition (kept once in the helpers)
dup = '''def events_of(res, event):
    return res.events.filter(pl.col('event') == event)


# ---------------------------------------------------------------------------
# item 3: lot invariant'''
assert dup in src
src = src.replace(dup, '''# ---------------------------------------------------------------------------
# item 3: lot invariant''', 1)

p.write_text(src, encoding='utf-8')
import ast
ast.parse(src)
print('test_01 rewritten; syntax OK')
