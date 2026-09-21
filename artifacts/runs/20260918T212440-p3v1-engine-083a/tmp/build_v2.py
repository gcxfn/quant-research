# -*- coding: utf-8 -*-
"""Build v1 run manifest + hand-calc doc + report (simple, no complex builder)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

log_lines = []


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False), encoding='utf-8')


# 1. run contract tests
proc = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/test_band_contract.py', '-q'],
    cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8',
    errors='replace')
(RUN_DIR / 'logs' / 'pytest.log').write_text(
    proc.stdout + '\n--- stderr ---\n' + proc.stderr, encoding='utf-8')
tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1]
print(f'pytest: {tail}')
passed = int(tail.split('passed')[0].strip().split()[-1])

# 2. data identity
daily_sha = sha256_file(ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet')
half_dir = ROOT / 'data/processed/halfday-bars-20260918'


def batch_agg(folder):
    import hashlib
    h = hashlib.sha256()
    files = sorted(p for p in Path(folder).rglob('*') if p.is_file())
    total = 0
    for f in files:
        fh = hashlib.sha256()
        with f.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b''):
                fh.update(chunk)
        h.update(f'{fh.hexdigest()}  {f.relative_to(folder)}\n'.encode())
        total += f.stat().st_size
    return {'aggregate_sha256': h.hexdigest(), 'files': len(files),
            'total_bytes': total}


half_agg = batch_agg(half_dir)

engine_sha = sha256_file(SRC / 'quant' / 'backtest' / 'band_engine.py')

manifest = {
    'run_id': RUN_DIR.name,
    'status': 'completed' if proc.returncode == 0 else 'failed',
    'engine_sha256': engine_sha,
    'tests_passed': passed,
    'tests_failed': 0 if proc.returncode == 0 else 1,
}
(RUN_DIR / 'manifest.json').write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'manifest written: {RUN_DIR / "manifest.json"}')
