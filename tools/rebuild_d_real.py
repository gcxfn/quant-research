from pathlib import Path
from datetime import date, datetime, timezone
import json, time
from quant.research.d_fund_rebuild import rebuild_intermediate
out=Path('artifacts/runs/20260920T190000-d-fund-rebuild-real'); out.mkdir(parents=True,exist_ok=False)
t=time.time(); frame, report=rebuild_intermediate(raw_root=Path('data/raw/tushare'),dev_end=date(2020,12,31)); frame.write_parquet(out/'financial_intermediate.parquet'); (out/'report.json').write_text(json.dumps({'status':'completed','rows':frame.height,'columns':frame.columns,'seconds':time.time()-t,'report':report},ensure_ascii=False,indent=2,default=str),encoding='utf-8'); print('saved',frame.height,'seconds',round(time.time()-t,1))
