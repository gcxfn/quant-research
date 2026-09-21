# -*- coding: utf-8 -*-
"""Final test_20: partial risk-exit fallback using test_08 KA fixture."""
from pathlib import Path
import ast

p = Path('tests/test_band_contract.py')
src = p.read_text(encoding='utf-8')
start = src.index('def test_20_partial_risk_exit_fallback():')
end = src.index('# ---------------------------------------------------------------------------\n'
                '# NEW 21:')

new = """def test_20_partial_risk_exit_fallback():
    \"\"\"M1: a risk sell with EXPLICIT shares (partial risk-exit) triggers the
    K=3 fallback after 3 unfilled sessions but sells only the explicit
    quantity, retaining the rest of the position.\"\"\"
    daily = pl.concat([
        daily_bars('PR', [(D(2016, 6, 1), 30.2, 30.25, 29.90, 30.0),
                          (D(2016, 6, 2), 29.8, 29.9, 29.0, 29.0),
                          (D(2016, 6, 3), 27.5, 27.5, 27.0, 27.4),
                          (D(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4)])])
    half = half_bars('PR', [
        (D(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
        (D(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
        (D(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
        (D(2016, 6, 3), 'am', 27.5, 27.5, 27.0, 27.4),
        (D(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4)])
    signals = [
        sig('PR', D(2016, 5, 31), 'pm', 'buy', 30.0, 1, target=30_000),
        sig('PR', D(2016, 6, 1), 'pm', 'sell', 30.0, intent='risk',
            shares=800),
        sig('PR', D(2016, 6, 2), 'am', 'sell', 29.5, intent='risk',
            shares=800),
        sig('PR', D(2016, 6, 2), 'pm', 'sell', 29.0, intent='risk',
            shares=800),
    ]
    res = run(signals, daily, half)
    b = res.fills.filter(pl.col('side') == 'buy').row(0, named=True)
    assert (b['date'], b['shares'], b['price']) == (D(2016, 6, 1), 1000, 30.0)
    # 3 unfilled sessions -> armed -> 06-03 pm fallback
    # (K=3 fires with explicit shares -> only 800 sold, not full position)
    kf = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert (kf['fill_type'], kf['date'], kf['session'], kf['price'],
            kf['shares']) == \\
        ('market_fallback', D(2016, 6, 3), 'pm', 27.5, 800)
    assert res.clips_final['shares'].to_list() == [200]
    assert res.stats['k3_fallback']['executed'] == 1


"""
src = src[:start] + new + src[end:]
p.write_text(src, encoding='utf-8')
ast.parse(src)
print('test_20 final rewrite OK')
