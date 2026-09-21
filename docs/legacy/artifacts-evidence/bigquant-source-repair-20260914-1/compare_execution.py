"""Hypothetical one-day field diagnostics, never replacement data or strategy search."""
import copy,csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from quant.execution import Replay
from experiments.ten_year_research import ten_year_fee_terms
from experiments.ten_year_account_audit_20260913 import limit_prices,fee_parts
from experiments.ten_year_account_20260913 import read,save,sha
OUT=Path(__file__).resolve().parent
BATCH=ROOT/'artifacts/ten-year-fixed-strategies-minute-accounts-20260914-6'
def compact(fills):
    return [(f['time'],f['code'],f['side'],f['shares'],f['price'],round(f['fee'],7)) for f in fills]
def main():
    report=dict(scope='ACTUAL_VENDOR_REPLACEMENT_ALL_AFFECTED_DAYS_FIXED_ORDERS_REPLAY',paths=[],inputs={})
    accepted={(r['code'],r['date']):r for r in read(OUT/'source-review.json')['repairs']}
    for path in read(BATCH/'manifest.json')['paths']:
        if path['status']!='WAITING_REVIEW':continue
        dest=BATCH/path['id'];account=read(dest/'account.json');requests=read(dest/'requests.json')
        sources={(r['code'],r['date']):r for r in read(dest/'minute-sources.json')}
        report['inputs'][str(dest/'account.json')]=sha(dest/'account.json')
        for request in requests:
            day=request['date'];orders=request['orders']
            affected=sorted({o['code'] for o in orders if (o['code'],day) in accepted})
            if not affected:continue
            prev=next((r for r in reversed(account['daily']) if r['date']<day),dict(cash=200000,shares={}))
            # Reconstruct opening holdings and cash, including same-day corporate actions.
            initial_cash=prev['cash']; positions={c:dict(shares=q,bought_today=0) for c,q in prev['shares'].items()}
            restricted=[]
            for event in account['corporate_action_entries']:
                if event['kind']=='split' and event['date']<=day<event.get('stock_sellable_date',event['date']):
                    restricted.append(dict(code=event['code'],shares=event['shares_added'],sellable_date=event['stock_sellable_date']))
                if event['date']!=day:continue
                if event['kind']=='dividend':initial_cash+=event['amount']
                if event['kind']=='split':positions[event['code']]=dict(shares=event['shares_after'],bought_today=0)
            assert not any(e['date']==day for e in account['security_code_change_entries']), 'explicit code-change reconstruction required'
            bars=[];limits={}; daily_map={}
            for code in sorted({o['code'] for o in orders}):
                source=sources[code,day]; p=Path(source['path']);assert sha(p)==source['sha256']
                report['inputs'][str(p)]=sha(p)
                daily=next(b for b in read(BATCH/'inputs'/(code+'.json'))['bars'] if b['date']==day);daily_map[code]=daily
                limits[day,code]=limit_prices(code,day,daily['preclose'],daily['isST'])
                with p.open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
                for b in rows:
                    for k in ('open','high','low','close','volume','amount'):b[k]=float(b[k])
                    for k in ('isST','tradestatus','status_eligible','st_sell_eligible'):b[k]=daily[k]
                bars.extend(rows)
            def run(changed):
                replay=Replay(initial_cash,lambda c:ten_year_fee_terms(day,c,execution_friction_bps=path['friction_bps']),
                    path['participation_rate'],opening_cash_only=True)
                replay.ledger.positions=copy.deepcopy(positions);replay.ledger.restricted_shares=copy.deepcopy(restricted)
                result=replay.run(copy.deepcopy(changed),limit_prices=limits,orders=copy.deepcopy(orders))
                for f in result['fills']:
                    assert abs(sum(fee_parts(day,f['code'],f['side'],f['price'],f['shares'],path['friction_bps']).values())-f['fee'])<1e-7
                return result['fills'],replay.ledger.cash
            base,cash=run(bars); actual=[f for f in account['fills'] if f['date']==day]
            assert compact(base)==compact(actual),'baseline fills mismatch '+path['id']+' '+day
            assert abs(cash-next(d['cash'] for d in account['daily'] if d['date']==day))<1e-6
            changed=copy.deepcopy(bars)
            for code in affected:
                entry=accepted[code,day]['new_entry'];p=Path(entry['path']);assert sha(p)==entry['sha256']
                with p.open(encoding='utf-8') as f:replacement=list(csv.DictReader(f))
                for b in replacement:
                    for k in ('open','high','low','close','volume','amount'):b[k]=float(b[k])
                    for k in ('isST','tradestatus','status_eligible','st_sell_eligible'):b[k]=daily_map[code][k]
                changed=[b for b in changed if b['code']!=code]+replacement
            fills,new_cash=run(changed)
            result=dict(id=path['id'],date=day,codes=affected,baseline_matches_full_day=True,
                fills_unchanged=base==fills,cash_delta=new_cash-cash,old_fills=base,new_fills=fills,
                fees_delta=sum(f['fee'] for f in fills)-sum(f['fee'] for f in base),
                old_starting_cash=initial_cash)
            report['paths'].append(result)
            print(path['id'],day,'fills identical',base==fills,'cash delta',new_cash-cash,flush=True)
    report['script_sha256']=sha(__file__)
    report['full_account_rerun_required']=any(not r['fills_unchanged'] or abs(r['cash_delta'])>1e-8 for r in report['paths'])
    save(OUT/'execution-comparison.json',report)
if __name__=='__main__':main()
