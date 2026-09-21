# -*- coding: utf-8 -*-
"""Red-team check 2: P2R6 pool PIT probes.
- Do delisted-in-window ETFs ever appear in signal-day eligible pools?
- fund_adj factor direction (decreasing factors = silent corruption)
- identify jump events with |adj ret| > 4% on factor-jump days
"""
import json
import sys
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(r'D:/量化')
sys.path.insert(0, str(ROOT / 'src'))
from quant.research import etf_rotation as er  # noqa: E402

cfg = json.loads((ROOT / 'configs/experiments/p2r6-etf-rotation.json').read_text(encoding='utf-8'))

basic = pl.read_csv(ROOT / cfg['data']['fund_basic']['batch'] / cfg['data']['fund_basic']['file'],
                    infer_schema_length=0).with_columns(pl.col('delist_date').fill_null(''))
delisted = set(basic.filter((pl.col('delist_date') >= '20150101')
                            & (pl.col('delist_date') <= '20241231'))['ts_code'].to_list())

loaded = er.load_frames(ROOT, cfg)
feat = loaded['feat']
print('stats:', loaded['stats'])

elig = feat.filter(pl.col('eligible'))
delisted_elig = elig.filter(pl.col('ts_code').is_in(delisted))
print('delisted-in-window codes EVER eligible:', delisted_elig['ts_code'].n_unique())
print('delisted eligible row-days:', delisted_elig.height)
if delisted_elig.height:
    per = (delisted_elig.group_by('ts_code').agg(pl.col('trade_date').min().alias('first'),
                                                 pl.col('trade_date').max().alias('last'),
                                                 pl.len().alias('days'))
           .sort('days', descending=True).head(15))
    print(per)

# signal-day pools: monthly signal days
cal = er.build_calendar(feat)
days = er.rebalance_days(cal, 'monthly', date(2016, 1, 1))
elig_by_day = {d: set(g['ts_code'].to_list()) for d, g in elig.group_by('trade_date')}
hits = {}
for d in days:
    pool = elig_by_day.get(d, set())
    n = len(pool & delisted)
    if n:
        hits[d] = n
print('monthly signal days whose eligible pool contains a delisted-in-window ETF:', len(hits))
print(dict(list(hits.items())[:20]))

# fund_adj direction over whitelist
adj_dir = ROOT / cfg['data']['fund_adj']['batch']
dec = 0
dec_examples = []
for code in sorted(cfg['u1_whitelist_frozen']):
    p = adj_dir / f'chunk_{code}.csv'
    try:
        a = pl.read_csv(p, infer_schema_length=0)
    except Exception:
        continue
    if a.height < 2:
        continue
    vals = a.select(pl.col('adj_factor').cast(pl.Float64, strict=False)).drop_nulls()
    if vals.height < 2:
        continue
    v = vals['adj_factor']
    if v[-1] < v[0]:
        dec += 1
        dec_examples.append((code, float(v[0]), float(v[-1])))
print('fund_adj codes with LAST factor < FIRST factor (decreasing):', dec, dec_examples[:10])

# jump events with |adj ret| > 4%
adj_dir_rows = []
for code in sorted(cfg['u1_whitelist_frozen']):
    dp = ROOT / cfg['data']['fund_daily']['batch'] / f'chunk_{code}.csv'
    ap = adj_dir / f'chunk_{code}.csv'
    try:
        d = pl.read_csv(dp, infer_schema_length=0).select(
            'trade_date', pl.col('close').cast(pl.Float64, strict=False))
        a = pl.read_csv(ap, infer_schema_length=0).select(
            'trade_date', pl.col('adj_factor').cast(pl.Float64, strict=False))
    except Exception:
        continue
    j = (d.join(a, on='trade_date', how='inner').sort('trade_date')
         .with_columns([
             (pl.col('adj_factor') / pl.col('adj_factor').shift(1) - 1.0).alias('jf'),
             ((pl.col('close') * pl.col('adj_factor'))
              / (pl.col('close').shift(1) * pl.col('adj_factor').shift(1)) - 1.0).alias('apct'),
             (pl.col('close') / pl.col('close').shift(1) - 1.0).alias('rpct'),
         ]).drop_nulls())
    bad = j.filter((pl.col('jf').abs() > 0.001) & (pl.col('apct').abs() > 0.04))
    if bad.height:
        for r in bad.iter_rows(named=True):
            adj_dir_rows.append({'code': code, 'date': r['trade_date'],
                                 'jf': round(r['jf'], 5), 'raw_ret': round(r['rpct'], 4),
                                 'adj_ret': round(r['apct'], 4)})
print('suspect factor-jump days (|adj ret|>4%):', len(adj_dir_rows))
for r in adj_dir_rows:
    print(r)
