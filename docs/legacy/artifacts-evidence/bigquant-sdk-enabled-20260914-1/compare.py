"""Compare vendor records without modifying accepted inputs or mapping timestamps."""
import csv,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
RAW=ROOT/'data/raw/bigquant/minute-check-20260914-1'
def main():
    manifest=json.loads((RAW/'manifest.json').read_text(encoding='utf-8'))
    targets=json.loads((ROOT/'artifacts/minute-bulk-source-check-20260914-1/query-targets.json').read_text(encoding='utf-8'))
    days={};results=[]
    for day,entry in manifest['completed'].items():
        p=Path(entry['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==entry['sha256']
        groups={}
        for b in csv.DictReader(p.open(encoding='utf-8-sig')):groups.setdefault(b['instrument'],[]).append(b)
        days[day]=groups
    for t in targets:
        code,day=t['code'],t['date'];symbol=code[3:]+'.'+code[:2].upper()
        rows=days.get(day,{}).get(symbol,[])
        result=dict(code=code,date=day,priority=t['status'],rows=len(rows),status='EMPTY' if not rows else 'RETURNED')
        if rows:
            rows.sort(key=lambda b:b['date'])
            values=[{k:float(b[k]) for k in ('open','high','low','close','volume','amount')} for b in rows]
            import math
            valid=all(all(math.isfinite(v) for v in b.values()) and min(b[k] for k in ('open','high','low','close'))>0 and b['volume']>=0 and b['amount']>=0 and b['low']<=min(b['open'],b['close'])<=max(b['open'],b['close'])<=b['high'] for b in values)
            traded=[b for b in values if b['volume']>0]
            agg=None if not traded else dict(open=traded[0]['open'],close=traded[-1]['close'],high=max(b['high'] for b in traded),low=min(b['low'] for b in traded),volume=sum(b['volume'] for b in values))
            daily=t.get('daily')
            result.update(valid_ohlcv=valid,unique_times=len({b['date'] for b in rows})==len(rows),
                first=rows[0],last=rows[-1],positive_volume_aggregate=agg,daily=daily,previous_minute=t.get('minute'),
                daily_difference=None if agg is None or daily is None else {k:agg[k]-daily[k] for k in agg})
            if t['status']=='SOURCE_CHECK' and daily:
                result['daily_low_hits']=[b for b in rows if abs(float(b['low'])-daily['low'])<1e-8]
        results.append(result)
    report=dict(scope='Vendor comparison only; no accepted source replacement, no timestamp conversion or new account acceptance',
        raw_manifest_sha256=hashlib.sha256((RAW/'manifest.json').read_bytes()).hexdigest(),
        total=len(results),nonempty=sum(r['rows']>0 for r in results),empty=sum(r['rows']==0 for r in results),
        invalid=sum(r.get('valid_ohlcv') is False or r.get('unique_times') is False for r in results),results=results)
    (OUT/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in report.items() if k!='results'})
if __name__=='__main__':main()
