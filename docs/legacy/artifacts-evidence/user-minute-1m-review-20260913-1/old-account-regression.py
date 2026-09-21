"""Re-run two old minute accounts on their exact original inputs, offline."""
import contextlib
import hashlib
import json
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT))
from experiments.rev11_dynamic_minute_20260912 import Provider, read, save, sha
from experiments.three_account_migration_run_20260912 import run_account, WINDOW


class Offline(Provider):
    def __call__(self,day,orders):
        assert all((o['code'],day) in self.cached for o in orders),'regression requires cached original data'
        return super().__call__(day,orders)


def main():
    result=dict(status='RUNNING',units=[],source_hashes={})
    for name in ['experiments/rev11_dynamic_minute_20260912.py','experiments/factor_miner/fixed_capital_portfolio.py',
                 'experiments/three_account_migration_run_20260912.py','experiments/factor_miner/migration_costs.py','quant/execution.py']:
        result['source_hashes'][name]=sha(ROOT/name)
    for unit in ('REV_vola_11','PV1_REV11_RANK50_TRAIN_V1'):
        old=ROOT/'artifacts/three-account-migration-accounts-20260912-8'/unit
        m=read(old/'manifest.json');ip=ROOT/m['inputs_directory'];sp=ROOT/m['signals_path']
        signals=[json.loads(s) for s in sp.read_text(encoding='utf-8').splitlines()]
        codes=sorted({c for r in signals for c in r['weights']})
        for c in codes:
            f=ip/(c+'.json');assert sha(f)==m['source_hashes'][str(Path(m['inputs_directory'])/(c+'.json'))]
        inputs={c:read(ip/(c+'.json')) for c in codes}
        dest=OUT/('old-regression-'+unit);dest.mkdir(exist_ok=False)
        p=Offline(inputs,dest,dest,[old/'minute-sources.json'],window=WINDOW,mismatch_policy='research_disclose')
        with (dest/'run.log').open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
            account=run_account(signals,inputs,read(ip/'manifest.json')['calendar'],p)
        p.close()
        normalized=json.loads(json.dumps(account))
        assert normalized==read(old/'account.json'),unit+' ledger regression differs'
        result['units'].append(dict(unit=unit,status='PASS_EXACT',old_account_sha256=sha(old/'account.json'),
            old_signal_sha256=sha(sp),fills=len(account['fills']),daily=len(account['daily'])))
    assert all(sha(ROOT/p)==s for p,s in result['source_hashes'].items())
    result.update(status='PASS_EXACT',reviewer_sha256=sha(__file__))
    save(OUT/'old-account-regression.json',result)
    print(result,flush=True)


if __name__=='__main__':main()
