"""Independent inventory, CRC, derived-file and daily discrepancy review."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import zipfile

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]


def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    calendar=json.loads((ROOT/'artifacts/ten-year-fixed-strategies-20260912-1/signals/calendar.json').read_text())['dates']
    report=dict(status='RUNNING',vendor='User purchased on Xianyu; original vendor not verified',
                scope='2015-2024 only; old planned selections are source probes, not actual orders',
                reviewer_sha256=sha(Path(__file__)),archives=[],probes=[],blocking_examples=[])
    def save(): (OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save()
    for suffix in ('20260913-143215','20260913-2020-2024'):
        raw=ROOT/'data/raw/user_minute_1m'/suffix
        manifest=json.loads((raw/'transfer-manifest.json').read_text(encoding='utf-8-sig'))
        for entry in manifest['files']:
            path=raw/Path(entry['destination']).name
            assert sha(path)==entry['sha256']
            with zipfile.ZipFile(path) as z:
                names=z.namelist()
                expected=[d.replace('-','')+'.parquet' for d in calendar if d[:4]==path.stem]
                assert sorted(names)==sorted(expected)
                bad=z.testzip()
                assert bad is None,bad
            report['archives'].append(dict(year=path.stem,days=len(names),sha256=entry['sha256'],all_member_crc='PASS',calendar='PASS'))
            save();print('CRC/calendar',path.stem,len(names),flush=True)
    for n in (1,2):
        folder=ROOT/f'artifacts/user-minute-1m-source-probe-20260913-{n}'
        m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        assert m['status']=='CONVERTED_AWAITING_SOURCE_REVIEW'
        assert m['source_sha256']==sha(ROOT/'experiments/user_minute_1m_20260913.py')
        counts=collections.Counter()
        for row in m['results']:
            path=Path(row['path']);assert sha(path)==row['sha256']
            with path.open(encoding='utf-8') as f:bars=list(csv.DictReader(f))
            assert len(bars)==48
            agg=dict(open=float(bars[0]['open']),close=float(bars[-1]['close']),
                     high=max(float(b['high']) for b in bars),low=min(float(b['low']) for b in bars),
                     volume=sum(float(b['volume']) for b in bars))
            assert agg==row['aggregate']
            delta=row['daily_difference']
            if delta is None:
                counts['missing_daily']+=1;continue
            daily={k:agg[k]-delta[k] for k in agg}
            vol_ok=abs(delta['volume'])<=1 or (daily['volume']>0 and abs(delta['volume'])/daily['volume']<=1e-6 and int(.005*agg['volume'])==int(.005*daily['volume']))
            exact=vol_ok and all(abs(delta[k])<=1e-6 for k in ('open','high','low','close'))
            bounded=all(daily[k]>0 and abs(delta[k])/daily[k]<=.01 for k in ('open','high','low','close')) and daily['volume']>0 and abs(delta['volume'])/daily['volume']<=.05
            state='match_or_rounding' if exact else 'bounded_disclose' if bounded else 'block'
            counts[state]+=1
            if state=='block':report['blocking_examples'].append(row)
        report['blocking_examples'].extend(m['issues'])
        report['probes'].append(dict(path=str(folder),manifest_sha256=sha(folder/'manifest.json'),
            converted=len(m['results']),structural_failures=len(m['issues']),classification=dict(counts)))
    report.update(status='PASS_WITH_LIMITATIONS',
        capability='241-to-48 conversion and existing research_disclose guards; source files are not globally approved',
        limitations=['Unknown original vendor','Float32 prices recovered only if exact encoding of a cent value',
                     'Volume and amount retained; source differences never overwrite raw data',
                     '1% OHLC / 5% volume are operational anomaly lines, not an error-safety guarantee',
                     'Every actual security-day must independently pass structural and daily guards',
                     'Code-lifetime corrected signals require a new batch; probes are not a final order list'])
    save();print(report['status'],report['probes'],flush=True)


if __name__=='__main__':main()
