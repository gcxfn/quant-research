import json,shutil,zipfile
from pathlib import Path
from experiments.user_minute_1m_20260913 import digest
out=Path('data/raw/user_csv_1m/20260913-4'); records=[]
for y in (2016,2018,2019):
 src=Path(f'C:/Users/ASUS/Downloads/{y}_1min.zip'); dst=out/src.name
 before=digest(src);shutil.copy2(src,dst);assert digest(dst)==before==digest(src)
 with zipfile.ZipFile(dst) as z:
  names=z.namelist(); assert len(names)==len(set(names)); count=len(names)
 records.append(dict(source=str(src),destination=str(dst.resolve()),sha256=before,members=count,status='COPY_VERIFIED',source_retained=True))
 (out/'transfer-manifest.json').write_text(json.dumps(dict(status='COMPLETE' if len(records)==3 else 'RUNNING',files=records),indent=2),encoding='utf-8')
 print(y,'COPY_VERIFIED',count,flush=True)
