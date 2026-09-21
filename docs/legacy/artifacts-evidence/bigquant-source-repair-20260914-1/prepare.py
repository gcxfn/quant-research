"""Whole security-day vendor replacement; no cross-vendor OHLC/volume splicing."""
import copy,csv,json,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.ten_year_account_20260913 import read,save,sha
from experiments.user_minute_1m_20260913 import normalize_1m
from experiments.ten_year_minute_execution_20260913 import TenYearProvider,require_complete_tail
OUT=Path(__file__).resolve().parent
DEST=ROOT/'data/raw/bigquant/minute-repairs-20260914-1'
BASE=ROOT/'data/raw/xiaodefa/minute-repairs-20260914-3/patches.json'
BATCH=ROOT/'artifacts/ten-year-fixed-strategies-minute-accounts-20260914-6'
CASES=[('sh.603026','2019-05-06'),('sz.300420','2019-09-02'),('sh.600452','2016-06-01')]
def convert(rows,code,day):
    times=[day+' 09:25:00']+[day+f' {m//60:02}:{m%60:02}:00' for lo,hi in ((571,690),(781,900)) for m in range(lo,hi+1)]
    rows=sorted(rows,key=lambda r:r['date'])
    if [r['date'] for r in rows]!=times:raise ValueError('BigQuant auction/continuous grid mismatch')
    # Intermediate adapter coordinate only: 09:25 auction included in first 09:35 bar.
    # Vendor raw timestamp retained separately; no claim that a trade occurred at 09:30.
    intermediate=[]
    for i,r in enumerate(rows):
        if r['instrument']!=code[3:]+'.'+code[:2].upper():raise ValueError('vendor identity mismatch')
        intermediate.append(dict(code=r['instrument'],date=day.replace('-',''),trade_time=day+' 09:30:00' if i==0 else r['date'],
            **{k:float(r[k]) for k in ('open','high','low','close')},vol=float(r['volume']),amount=float(r['amount'])))
    bars=normalize_1m(intermediate,code,day)
    assert sum(b['volume'] for b in bars)==sum(float(r['volume']) for r in rows)
    assert abs(sum(b['amount'] for b in bars)-sum(float(r['amount']) for r in rows))<.01
    return bars
def main():
    DEST.mkdir(parents=True,exist_ok=False);patches=read(BASE);record=[]
    source_manifest=read(ROOT/'data/raw/bigquant/minute-check-20260914-1/manifest.json')
    for code,day in CASES:
        old=next(e for e in patches if (e['code'],e['date'])==(code,day));previous=copy.deepcopy(old)
        assert sha(old['path'])==old['sha256'] and sha(old['raw_path'])==old['raw_sha256']
        src=ROOT/'data/raw/bigquant/minute-check-20260914-1'/(day+'.csv')
        assert sha(src)==source_manifest['completed'][day]['sha256']
        with src.open(encoding='utf-8-sig') as f:rows=[r for r in csv.DictReader(f) if r['instrument']==code[3:]+'.'+code[:2].upper()]
        bars=convert(rows,code,day)
        # Negative cases test the vendor bridge, not just the downstream provider.
        for bad in (rows[:-1],rows+rows[:1], [dict(r,date=day+' 09:30:00') if i==0 else r for i,r in enumerate(rows)]):
            try:convert(bad,code,day)
            except ValueError:pass
            else:raise AssertionError('bad source grid accepted')
        p=DEST/(code+'_'+day+'_f5.csv')
        with p.open('x',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(bars[0]));w.writeheader();w.writerows(bars)
        with Path(old['path']).open(encoding='utf-8') as f:oldbars=list(csv.DictReader(f))
        changes=[dict(time=b['time'],field=k,before=float(a[k]),after=b[k]) for a,b in zip(oldbars,bars)
            for k in ('open','high','low','close','volume','amount') if abs(float(a[k])-b[k])>1e-6]
        agg=dict(open=bars[0]['open'],close=bars[-1]['close'],high=max(b['high'] for b in bars),low=min(b['low'] for b in bars),volume=sum(b['volume'] for b in bars))
        payload=read(BATCH/'inputs'/(code+'.json'));daily=next(b for b in payload['bars'] if b['date']==day)
        trailing=next((i for i,r in enumerate(reversed(rows)) if float(r['volume'])>0),len(rows))
        for key in ('reviewed_low_only_missing_print','reviewed_opening_buy_discrepancy','accepted_source_baseline'):old.pop(key,None)
        old.update(path=str(p),sha256=sha(p),raw_path=str(src),raw_sha256=sha(src),source='bigquant_cn_stock_bar1m_whole_security_day',
            previous_entry=previous,trailing_zero_minutes=trailing,minute_volume=agg['volume'],
            normalization='RAW_0925_AUCTION_INCLUDED_IN_0935;CONTINUOUS_RIGHT_END_TIMES_PRESERVED',
            volume_unit='shares; checked against baseline daily and minute records',amount_unit='yuan',
            scope='Three user-authorized vendor corrections; full source OHLCV, not selected fields')
        if code=='sh.600452':
            approval=copy.deepcopy(previous['accepted_source_baseline']);approval.update(sha256=sha(p),minute=agg,
                scope='Same previously accepted opening discrepancy retained on BigQuant whole-day replacement; close corrected')
            old['accepted_source_baseline']=approval
        require_complete_tail(old,daily)
        dest=OUT/(code+'-provider');dest.mkdir(exist_ok=False)
        archive=SimpleNamespace(archives={day[:4]:{}},source=lambda c,d:old)
        provider=TenYearProvider({code:payload},dest,dest,archive,mismatch_policy='research_disclose')
        real=[]
        for path in read(BATCH/'manifest.json')['paths']:
            for request in read(BATCH/path['id']/'requests.json'):
                if request['date']==day:real.extend(o for o in request['orders'] if o['code']==code)
        got=provider(day,real or [dict(code=code,side='buy',otype='limit',price=daily['open'],shares=100)])
        assert len(got)==48
        record.append(dict(code=code,date=day,previous_entry=previous,new_entry=copy.deepcopy(old),changes=changes,
            minute=agg,daily={k:daily[k] for k in agg},daily_difference={k:agg[k]-daily[k] for k in agg},
            actual_orders=len(real),provider='PASS_RESEARCH_DISCLOSE',provenance_file=str(src),raw_sha256=sha(src)))
    assert len(patches)==33
    save(DEST/'patches.json',patches)
    save(OUT/'source-review.json',dict(status='WAITING_REVIEW',kind='WHOLE_SECURITY_DAY_VENDOR_REPLACEMENT',
        base_patch_sha256=sha(BASE),patch_sha256=sha(DEST/'patches.json'),repairs=record,
        daily_not_replaced=True,other_open_discrepancies_unchanged=True,script_sha256=sha(__file__)))
    print([(r['code'],len(r['changes']),r['actual_orders'],r['daily_difference']) for r in record])
if __name__=='__main__':main()
