from pathlib import Path
from quant.research.factor_eval_run import run_factor_evaluation
root=Path('artifacts/runs/20260919T180000-f2r1-factor-batch/outputs')
paths=[]
for fam in ['A_price','B_value','C_micro','F_xsec']:
 paths += sorted((root/fam).glob('[A-F][0-9][0-9].parquet'))
paths += sorted((root/'E_event').glob('[A-E][0-9][0-9].parquet'))
paths=[p for p in paths if p.name!='E16.parquet']
paths.append(Path('artifacts/runs/20260920T180001-e16-rebuild-real/E16.parquet'))
paths += sorted(Path('artifacts/runs/20260920T190000-d-fund-rebuild-real/D_fund').glob('D*.parquet'))
print('inputs',len(paths))
config=Path('configs/experiments/exp-20260920-f2r1-rebuild.json')
p=run_factor_evaluation(repo_root=Path('.'),panel_path=Path('data/processed/baostock-daily-20260917/daily_2015_2024.parquet'),factor_paths=paths,artifacts_root=Path('artifacts'),config_path=config)
print(p)
