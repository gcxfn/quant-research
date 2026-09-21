import json
from pathlib import Path
from experiments.ten_year_minute_execution_20260913 import TenYearProvider
from experiments.rev11_dynamic_minute_20260912 import Provider
from experiments.user_minute_1m_20260913 import digest
raw=Path('data/raw/user_csv_1m/20260913-4'); out=Path('artifacts/user-csv-minute-review-20260913/new-years');out.mkdir(exist_ok=False)
code='sz.002812';day='2018-03-01';inputs={code:json.loads(Path(f'artifacts/ten-year-fixed-strategies-minute-accounts-20260913-5/inputs/{code}.json').read_text())}
p=TenYearProvider(inputs,raw,out,None,[raw/'patches.json'],mismatch_policy='research_disclose')
try:
 bars=Provider.__call__(p,day,[dict(code=code,side='buy',shares=100,price=102.2)]);assert len(bars)==48
finally:p.close()
(out/'review.json').write_text(json.dumps(dict(status='PASS_WITH_LIMITATIONS',scope='sz.002812 2018-03-01 only; 48 bars passed existing Provider, empirical lot unit, vendor unknown',patch_manifest_sha256=digest(raw/'patches.json'),validation_sha256=digest(raw/'validation.json'),review_script_sha256=digest(Path(__file__)),discrepancies=p.data_discrepancies),indent=2),encoding='utf-8')
print('real Provider PASS, 48 bars; discrepancies',len(p.data_discrepancies))
