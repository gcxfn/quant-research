"""Independent standard-library aggregation and exact scope verification."""
import csv,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    base=read(ROOT/'data/raw/xiaodefa/minute-repairs-20260914-3/patches.json')
    newpath=ROOT/'data/raw/bigquant/minute-repairs-20260914-1/patches.json';new=read(newpath)
    old={(r['code'],r['date']):r for r in base};updated={(r['code'],r['date']):r for r in new}
    targets={('sh.603026','2019-05-06'),('sz.300420','2019-09-02'),('sh.600452','2016-06-01')}
    assert len(old)==len(updated)==33 and set(old)==set(updated)
    assert {k for k in old if old[k]!=updated[k]}==targets
    records=[]
    for key,e in updated.items():
        assert sha(e['path'])==e['sha256'] and sha(e['raw_path'])==e['raw_sha256']
        if key not in targets:continue
        code,day=key
        with Path(e['raw_path']).open(encoding='utf-8-sig') as f:rows=[r for r in csv.DictReader(f) if r['instrument']==code[3:]+'.'+code[:2].upper()]
        rows.sort(key=lambda r:r['date']);groups={}
        for r in rows:
            hhmm=r['date'][11:16];hour,minute=map(int,hhmm.split(':'));m=hour*60+minute
            end=575 if hhmm=='09:25' else ((m+4)//5)*5
            groups.setdefault(day.replace('-','')+f'{end//60:02}{end%60:02}00000',[]).append(r)
        with Path(e['path']).open(encoding='utf-8') as f:bars=list(csv.DictReader(f))
        assert len(groups)==len(bars)==48
        for b in bars:
            g=groups[b['time']];traded=[r for r in g if float(r['volume'])>0] or g
            expected=dict(open=float(traded[0]['open']),close=float(traded[-1]['close']),
                high=max(float(r['high']) for r in traded),low=min(float(r['low']) for r in traded),
                volume=sum(float(r['volume']) for r in g),amount=sum(float(r['amount']) for r in g))
            assert all(abs(float(b[k])-v)<1e-6 for k,v in expected.items()),(key,b,expected)
        records.append(dict(code=code,date=day,independent_groups=48,fields_compared=288,sha256=e['sha256']))
    account=ROOT/'artifacts/ten-year-fixed-strategies-minute-accounts-20260914-6'
    manifest=read(account/'manifest.json');requests=[];files={}
    for path in manifest['paths']:
        p=account/path['id']/'requests.json';files[str(p)]=sha(p)
        for r in read(p):
            for code in {o['code'] for o in r['orders']}:
                if (code,r['date']) in targets:requests.append((path['id'],code,r['date']))
                assert (code,r['date'])!=('sz.300114','2016-05-03')
    comparison=read(OUT/'execution-comparison.json')
    compared=[(r['id'],code,r['date']) for r in comparison['paths'] for code in r['codes']]
    assert sorted(requests)==sorted(compared) and len(requests)==4
    assert all(r['fills_unchanged'] and r['cash_delta']==r['fees_delta']==0 for r in comparison['paths'])
    assert all(sha(k)==v for k,v in manifest['source_hashes'].items())
    status=read(ROOT/'data/raw/xiaodefa/20260914-300114-status/daily_20160503.json')['data']
    row=dict(zip(status['fields'],status['items'][0]));daily=next(b for b in read(account/'inputs/sz.300114.json')['bars'] if b['date']=='2016-05-03')
    assert row['ts_code']=='300114.SZ' and row['trade_date']=='20160503' and row['vol']*100==daily['volume']>0
    assert all(row[k]==daily[k] for k in ('open','high','low','close')) and daily['tradestatus']==1
    result=dict(status='PASS_WITH_LIMITATIONS',independent_aggregation=records,unchanged_patch_entries=30,
        actual_dependencies=len(requests),all_actual_dependencies_replayed=True,all_fills_cash_fees_unchanged=True,
        full_account_rerun_required=False,explanation='Same daily valuations, strategy and initial state; every changed security-day actual dependency gives identical fills/cash. No change in downstream holdings or signals. Old account artifacts retain old source identity.',
        missing_300114=dict(status='TRADING_DAY_MINUTE_MISSING',daily_volume_shares=daily['volume'],actual_T2_dependency=False,
            local_input_sha256=sha(account/'inputs/sz.300114.json'),proxy_daily_sha256=sha(ROOT/'data/raw/xiaodefa/20260914-300114-status/daily_20160503.json')),
        patch_manifest_sha256=sha(newpath),requests_sha256=files,script_sha256=sha(__file__),
        limitation='Conditional source revision, not independent vendor accuracy certification or T3/new engine acceptance')
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
