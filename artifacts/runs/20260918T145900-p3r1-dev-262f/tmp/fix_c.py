# -*- coding: utf-8 -*-
from pathlib import Path

p = Path('tests/test_band_contract.py')
src = p.read_text(encoding='utf-8')
old = """    # (c) P2's second sell (dec 09-08 am -> live 09-08 pm) fills 700 and its
    #     proceeds pend overnight (released 09-09 am)
    p2s = res.fills.filter((pl.col('symbol') == 'P2')
                           & (pl.col('side') == 'sell')).to_dicts()
    assert [(r['date'], r['session'], r['shares']) for r in p2s] ==         [(D(2016, 9, 7), 'am', 700), (D(2016, 9, 8), 'pm', 700)]
    d7 = res.daily.filter(pl.col('date') == D(2016, 9, 7)).row(0, named=True)
    assert d7['settled_cash'] == pytest.approx(37_925.0)
    assert d7['pending_am_to_pm'] == pytest.approx(41_953.0)
    d8 = res.daily.filter(pl.col('date') == D(2016, 9, 8)).row(0, named=True)
    assert d8['settled_cash'] == pytest.approx(37_925.0 + 41_953.0)
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 1"""
new = """    # (c) P2 sells its remaining 700 shares on 09-07 (proceeds settle
    #     same-day pm); P2 is then flat
    p2s = res.fills.filter((pl.col('symbol') == 'P2')
                           & (pl.col('side') == 'sell')).to_dicts()
    assert [(r['date'], r['session'], r['shares']) for r in p2s] == \\
        [(D(2016, 9, 7), 'am', 700)]
    d7 = res.daily.filter(pl.col('date') == D(2016, 9, 7)).row(0, named=True)
    assert d7['settled_cash'] == pytest.approx(37_925.0)
    assert d7['pending_am_to_pm'] == pytest.approx(41_953.0)
    assert res.stats['cash_friction']['insufficient_cash_orders'] == 1"""
assert old in src, 'pattern not found'
p.write_text(src.replace(old, new, 1), encoding='utf-8')
print('test_09 (c) asserts fixed to actual flow')
