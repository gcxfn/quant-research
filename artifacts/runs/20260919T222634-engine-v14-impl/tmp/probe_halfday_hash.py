import sys
sys.path.insert(0, 'src')
from quant.backtest.band_engine import batch_aggregate_sha256
from pathlib import Path
import hashlib
agg = batch_aggregate_sha256(Path('data/processed/halfday-bars-20260918'))
print('engine batch_aggregate:', agg['aggregate_sha256'][:16], 'files:', agg.get('files'))
# other natural conventions
root = Path('data/processed/halfday-bars-20260918')
files = sorted(p for p in root.rglob('*') if p.is_file())
digests = [hashlib.sha256(p.read_bytes()).digest() for p in files]
print('concat digests no names:', hashlib.sha256(b''.join(digests)).hexdigest()[:16])
print('hex concat:', hashlib.sha256(''.join(d.hex() for d in digests).encode()).hexdigest()[:16])
print('newline hex:', hashlib.sha256('\n'.join(d.hex() for d in digests).encode()).hexdigest()[:16])
parquets = sorted(p for p in root.rglob('*.parquet'))
d2 = [hashlib.sha256(p.read_bytes()).digest() for p in parquets]
print('parquet-only concat:', hashlib.sha256(b''.join(d2)).hexdigest()[:16])
print('parquet-only newline-hex:', hashlib.sha256('\n'.join(x.hex() for x in d2).encode()).hexdigest()[:16])
