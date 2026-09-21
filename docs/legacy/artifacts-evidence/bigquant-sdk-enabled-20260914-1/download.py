"""Read only selected minute fields; immutable per-day CSV and resumable manifest."""
import csv,hashlib,json,time
from collections import defaultdict
from pathlib import Path
import bigquant
from bigquant import dai

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/raw/bigquant/minute-check-20260914-1'
TARGETS=ROOT/'artifacts/minute-bulk-source-check-20260914-1/query-targets.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    bigquant.init_from_config();OUT.mkdir(parents=True,exist_ok=True)
    mp=OUT/'manifest.json'
    m=json.loads(mp.read_text(encoding='utf-8')) if mp.exists() else dict(status='RUNNING',table='cn_stock_bar1m',targets_sha256=sha(TARGETS),completed={},failures=[])
    assert m['targets_sha256']==sha(TARGETS)
    groups=defaultdict(list)
    targets=json.loads(TARGETS.read_text(encoding='utf-8'))
    major={r['date'] for r in targets if r['status']=='SOURCE_CHECK'}
    for r in targets:groups[r['date']].append(r['code'][3:]+'.'+r['code'][:2].upper())
    days=sorted(groups,key=lambda d:(d!='2016-06-01',d not in major,d))
    def save():mp.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    for n,day in enumerate(days,1):
        p=OUT/(day+'.csv')
        if day in m['completed']:
            assert sha(p)==m['completed'][day]['sha256'];continue
        if p.exists():raise ValueError('Unregistered file; inspect before any repeated download '+str(p))
        symbols=groups[day]
        sql="SELECT date,instrument,open,high,low,close,volume,amount FROM cn_stock_bar1m WHERE instrument IN ("+','.join("'"+s+"'" for s in symbols)+") AND date >= '"+day+" 00:00:00' AND date <= '"+day+" 23:59:59' ORDER BY instrument,date"
        try:
            frame=dai.query(sql,filters={'date':[day+' 00:00:00',day+' 23:59:59'],'instrument':symbols}).df()
            assert frame['instrument'].isin(symbols).all() and frame['date'].astype(str).str.startswith(day).all()
            frame.to_csv(p,index=False,encoding='utf-8-sig',mode='x')
            coverage={s:int((frame['instrument']==s).sum()) for s in symbols}
            m['completed'][day]=dict(path=str(p),sha256=sha(p),rows=len(frame),bytes=p.stat().st_size,coverage=coverage,sql=sql,
                duplicate_rows=int(frame.duplicated(['date','instrument']).sum()))
            save();print(n,'/',len(days),day,'rows',len(frame),'empty',sum(v==0 for v in coverage.values()),flush=True)
        except Exception as exc:
            m.update(status='BLOCKED');m['failures'].append(dict(date=day,error_type=type(exc).__name__,error=str(exc)));save()
            print(type(exc).__name__,str(exc)[:700],flush=True);return
        time.sleep(.5)
    m.update(status='DOWNLOADED_NOT_SOURCE_VALIDATED',security_days=len(targets),rows=sum(r['rows'] for r in m['completed'].values()),
        csv_bytes=sum(r['bytes'] for r in m['completed'].values()),empty=sum(v==0 for r in m['completed'].values() for v in r['coverage'].values()))
    save();print({k:v for k,v in m.items() if k not in ('completed','failures')},flush=True)
if __name__=='__main__':main()
