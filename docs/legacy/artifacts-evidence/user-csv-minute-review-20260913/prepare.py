"""Freeze supplied CSV files and validate full-day repairs without altering originals."""
import csv, json, shutil, hashlib
from decimal import Decimal
from pathlib import Path
from experiments.user_minute_1m_20260913 import normalize_1m, digest

root=Path.cwd(); out=Path(__file__).resolve().parent
raw=root/'data/raw/user_csv_1m/20260913-2';raw.mkdir(parents=True,exist_ok=False)
requests=list(csv.DictReader((root/'artifacts/user-minute-1m-review-20260913-1/data-repair-request.csv').open(encoding='utf-8-sig')))
entries=[];checks=[]
for req in requests:
 if req['date']!='2015-07-01':continue
 code,day=req['code'],req['date'];name=code.replace('.','')+'_2015.csv'
 source=Path('C:/Users/ASUS/Downloads/2015_1min')/name
 before=digest(source);p=raw/name;shutil.copy2(source,p)
 assert digest(p)==before==digest(source)
 with p.open(encoding='utf-8-sig',newline='') as f:
  rows=[r for r in csv.DictReader(f) if r['时间'].startswith(day+' ')]
 normalized=[]
 for r in rows:
  assert r['代码']==code.replace('.','')
  normalized.append(dict(code=code[3:]+'.'+code[:2].upper(),date=day.replace('-',''),trade_time=r['时间'],
    open=float(r['开盘价']),high=float(r['最高价']),low=float(r['最低价']),close=float(r['收盘价']),
    vol=float(Decimal(r['成交量'])*100),amount=float(r['成交额'])))
 bars=normalize_1m(normalized,code,day)
 daily=json.loads((root/f'artifacts/ten-year-fixed-strategies-minute-accounts-20260913-2/inputs/{code}.json').read_text())
 daily=next(x for x in daily['bars'] if x['date']==day)
 aggregate=dict(open=bars[0]['open'],close=bars[-1]['close'],high=max(b['high'] for b in bars),low=min(b['low'] for b in bars),volume=sum(b['volume'] for b in bars),amount=sum(b['amount'] for b in bars))
 price_equal=all(abs(aggregate[k]-daily[k])<1e-8 for k in ('open','high','low','close'))
 volume_diff=abs(aggregate['volume']-daily['volume'])/daily['volume']
 # Empirical lot-rounded volumes: whole-day discrepancy cannot exceed 100 shares per minute.
 assert all(aggregate[k]==daily[k] for k in ('open','close'))
 assert max(abs(aggregate[k]/daily[k]-1) for k in ('high','low'))<.01
 assert abs(aggregate['volume']-daily['volume'])<=100*len(rows)
 traded=[r for r in normalized if r['vol']>0]
 plausible=sum(r['low']*.98 <= r['amount']/r['vol'] <= r['high']*1.02 for r in traded)
 assert plausible>=.95*len(traded), (code,'volume/amount unit inconsistent')
 target=raw/(code+'_'+day+'_f5.csv')
 with target.open('x',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(bars[0]));w.writeheader();w.writerows(bars)
 trailing=next((i for i,r in enumerate(reversed(sorted(normalized,key=lambda r:r['trade_time']))) if r['vol']>0),len(rows))
 entries.append(dict(code=code,date=day,path=str(target.resolve()),sha256=digest(target),error_code='0',source='user_csv_1m_lots_to_shares_aggregated_5m',raw_path=str(p.resolve()),raw_sha256=before,trailing_zero_minutes=trailing,minute_volume=aggregate['volume']))
 checks.append(dict(code=code,date=day,rows=len(rows),bars=len(bars),ohlc_exact=price_equal,volume_relative_difference=volume_diff,amount_relative_difference=abs(aggregate['amount']-daily['amount'])/daily['amount'],unit_plausible_bars=plausible,traded_bars=len(traded),aggregate=aggregate,daily=daily))
 print(code,'PASS',volume_diff,flush=True)
assert len(entries)==12
(raw/'patches.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
(out/'validation.json').write_text(json.dumps(dict(status='PASS_WITH_LIMITATIONS',scope='12 specified security-days only; empirical volume unit=100 shares; original vendor unknown; lot rounding disclosed',patch_manifest=str(raw/'patches.json'),patch_manifest_sha256=digest(raw/'patches.json'),checks=checks),indent=2),encoding='utf-8')
