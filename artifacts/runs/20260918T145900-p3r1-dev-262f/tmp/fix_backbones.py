# -*- coding: utf-8 -*-
"""Extend daily backbones to cover decision dates; fix session-index asserts."""
from pathlib import Path

p = Path('tests/test_band_contract.py')
src = p.read_text(encoding='utf-8')
fixes = []

# test_02: T1 backbone must include the 03-03 decision date
fixes.append(("""    daily = daily_bars('T1', [(D(2024, 3, 4), 10.2, 10.6, 10.1, 10.5),
                              (D(2024, 3, 5), 10.5, 10.9, 10.4, 10.7),
                              (D(2024, 3, 6), 10.8, 11.0, 10.7, 10.85)])""",
"""    daily = daily_bars('T1', [(D(2024, 3, 3), 10.2, 10.3, 10.1, 10.2),
                              (D(2024, 3, 4), 10.2, 10.6, 10.1, 10.5),
                              (D(2024, 3, 5), 10.5, 10.9, 10.4, 10.7),
                              (D(2024, 3, 6), 10.8, 11.0, 10.7, 10.85)])"""))

# test_04: the calendar now starts at the 03-03 decision date; the cash
# milestone is on 03-04
fixes.append(("""    assert (res.daily['settled_cash'] >= 0).all()
    assert res.daily.row(0, named=True)['settled_cash'] == pytest.approx(
        200_000.0 - 48_005.0 - 40_005.0)""",
"""    assert (res.daily['settled_cash'] >= 0).all()
    d4 = res.daily.filter(pl.col('date') == D(2024, 3, 4)).row(0, named=True)
    assert d4['settled_cash'] == pytest.approx(200_000.0 - 48_005.0 - 40_005.0)"""))

# test_06: PD/ST backbone must include the 01-04 decision date
fixes.append(("""        daily_bars('PD', [(D(2015, 1, 5), 10.0, 10.2, 9.95, 10.0),""",
"""        daily_bars('PD', [(D(2015, 1, 4), 10.0, 10.05, 9.95, 10.0),
                          (D(2015, 1, 5), 10.0, 10.2, 9.95, 10.0),"""))
fixes.append(("""        daily_bars('ST', [(D(2015, 1, 5), 10.0, 10.2, 9.95, 10.0),""",
"""        daily_bars('ST', [(D(2015, 1, 4), 10.0, 10.05, 9.95, 10.0),
                          (D(2015, 1, 5), 10.0, 10.2, 9.95, 10.0),"""))

# test_08: KA/KB/KP backbones must include the 05-31 decision date
for sym in ('KA', 'KB', 'KP'):
    fixes.append((f"""        daily_bars('{sym}', [(D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),""",
                  f"""        daily_bars('{sym}', [(D(2016, 5, 31), 30.0, 30.05, 29.95, 30.0),
                          (D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),"""))

# test_19: clips stay as separate lots (no consolidation)
fixes.append(("""    assert res.clips_final['shares'].to_list() == [1200]""",
"""    assert sorted(res.clips_final['shares'].to_list()) == [100, 1100]"""))

# test_15: the partial sell must live 05-08 pm (clip 2 acquired 05-07)
fixes.append(("""        sig('M', D(2024, 5, 7), 'am', 'sell', 10.6, 1, intent='profit',
            shares=600),""",
"""        sig('M', D(2024, 5, 7), 'pm', 'sell', 10.6, 1, intent='profit',
            shares=600),"""))
fixes.append(("""    sell = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert sell['shares'] == 600                      # FIFO: clip1 500 + 100
    cf = res.clips_final.to_dicts()
    assert len(cf) == 1 and cf[0]['shares'] == 200
    assert cf[0]['acquired'] == D(2024, 5, 7)         # clip1 fully consumed""",
"""    sell = res.fills.filter(pl.col('side') == 'sell').row(0, named=True)
    assert sell['shares'] == 600                      # FIFO: clip1 500 + 100
    assert sell['date'] == D(2024, 5, 8)
    cf = res.clips_final.to_dicts()
    assert len(cf) == 1 and cf[0]['shares'] == 200
    assert cf[0]['acquired'] == D(2024, 5, 7)         # clip1 fully consumed"""))

for i, (old, new) in enumerate(fixes):
    if old not in src:
        raise SystemExit(f'fix {i} not found:\n{old[:200]}')
    src = src.replace(old, new, 1)
p.write_text(src, encoding='utf-8')
print(f'{len(fixes)} backbone/assert fixes applied')
