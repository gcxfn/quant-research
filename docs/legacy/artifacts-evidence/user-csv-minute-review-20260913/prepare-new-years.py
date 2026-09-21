import csv,json,zipfile,shutil
from pathlib import Path
from decimal import Decimal
from experiments.user_minute_1m_20260913 import normalize_1m,digest
root=Path.cwd(); raw=root/'data/raw/user_csv_1m/20260913-4'; raw.mkdir(parents=True,exist_ok=False)
checks=[]; entries=json.loads((root/'data/raw/baostock/ten-year-repair-20260913-3/patches.json').read_text())
for code,day in [('sz.002442','2016-03-01'),('sz.300114','2016-05-03'),('sz.002812','2018-03-01'),('sh.603026','2019-05-06'),('sz.300420','2019-09-02')]:
 archive=Path(f'C:/Users/ASUS/Downloads/{day[:4]}_1min.zip'); name=code.replace('.','')+'_'+day[:4]+'.csv'
 with zipfile.ZipFile(archive) as z:
  if name not in z.namelist():
   checks.append(dict(code=code,date=day,status='MISSING_MEMBER',archive=str(archive))); print(code,day,'MISSING_MEMBER',flush=True);continue
  p=raw/name
  with z.open(name) as src,p.open('xb') as dst:shutil.copyfileobj(src,dst)
 with p.open(encoding='utf-8-sig',newline='') as f: rows=[r for r in csv.DictReader(f) if r['时间'].startswith(day+' ')]
 norm=[]
 for r in rows:
  assert r['代码']==code.replace('.','')
  norm.append(dict(code=code[3:]+'.'+code[:2].upper(),date=day.replace('-',''),trade_time=r['时间'],open=float(r['开盘价']),high=float(r['最高价']),low=float(r['最低价']),close=float(r['收盘价']),vol=float(Decimal(r['成交量'])*100),amount=float(r['成交额'])))
 try:
  bars=normalize_1m(norm,code,day)
  daily=next(x for x in json.loads((root/f'artifacts/ten-year-fixed-strategies-minute-accounts-20260913-5/inputs/{code}.json').read_text())['bars'] if x['date']==day)
  agg=dict(open=bars[0]['open'],close=bars[-1]['close'],high=max(b['high'] for b in bars),low=min(b['low'] for b in bars),volume=sum(b['volume'] for b in bars))
  traded=[r for r in norm if r['vol']>0]; plausible=sum(r['low']*.98<=r['amount']/r['vol']<=r['high']*1.02 for r in traded)
  assert traded and plausible>=.95*len(traded),'unit check'
  assert all(abs(agg[k]/daily[k]-1)<=.01 for k in ('open','high','low','close')) and abs(agg['volume']/daily['volume']-1)<=.05,('daily mismatch',agg,daily)
  target=raw/(code+'_'+day+'_f5.csv')
  with target.open('x',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=list(bars[0]));w.writeheader();w.writerows(bars)
  trailing=next((i for i,r in enumerate(reversed(sorted(norm,key=lambda r:r['trade_time']))) if r['vol']>0),len(norm))
  entry=dict(code=code,date=day,path=str(target),sha256=digest(target),error_code='0',source='user_csv_1m_lots_to_shares_aggregated_5m',raw_path=str(p),raw_sha256=digest(p),trailing_zero_minutes=trailing,minute_volume=agg['volume'])
  from experiments.ten_year_minute_execution_20260913 import require_complete_tail
  require_complete_tail(entry,daily);entries.append(entry)
  checks.append(dict(code=code,date=day,status='PASS_WITH_LIMITATIONS',rows=len(rows),aggregate=agg,daily=daily,raw_sha256=digest(p),archive=str(archive),member=name))
  print(code,day,'PASS_WITH_LIMITATIONS',agg,flush=True)
 except Exception as e:
  checks.append(dict(code=code,date=day,status='BLOCKED',error=repr(e)));print(code,day,repr(e),flush=True)
(raw/'patches.json').write_text(json.dumps(entries,indent=2),encoding='utf-8')
(raw/'validation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
