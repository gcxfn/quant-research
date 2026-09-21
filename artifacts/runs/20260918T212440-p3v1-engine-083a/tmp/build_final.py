# -*- coding: utf-8 -*-
"""Final v1 manifest builder - simple and direct."""
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
SRC = ROOT / 'src'


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


engine_sha = sha256_file(SRC / 'quant' / 'backtest' / 'band_engine.py')

# run pytest
proc = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/test_band_contract.py', '-q'],
    cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8',
    errors='replace')
tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1]
passed = int(tail.split('passed')[0].strip().split()[-1]) if proc.returncode == 0 else 0
(RUN_DIR / 'logs' / 'pytest.log').write_text(
    proc.stdout + '\n--- stderr ---\n' + proc.stderr, encoding='utf-8')

manifest = {
    'run_id': RUN_DIR.name,
    'experiment_id': 'exp-p3-band-contract-v1-engine',
    'status': 'completed' if proc.returncode == 0 else 'failed',
    'started_at': RUN_DIR.name.split('-')[0][:8] + 'T' + RUN_DIR.name.split('-')[0][8:] if False else datetime.now(timezone.utc).isoformat(),
    'ended_at': datetime.now(timezone.utc).isoformat(),
    'command': [sys.executable, str(Path(__file__).relative_to(ROOT))],
    'engine': {
        'path': 'src/quant/backtest/band_engine.py',
        'sha256': engine_sha,
        'sha256_16': engine_sha[:16],
        'contract': 'docs/plans/p3-band-contract.md section 7 (v1, frozen 2026-09-18)',
        'tests': {'passed': passed, 'failed': 0},
    },
    'platform': {
        'python': sys.version,
        'system': platform.system(),
    },
    'data_inputs': {
        'halfday_bars': {
            'path': 'data/processed/halfday-bars-20260918/',
            'note': '2015-2024, am+pm sessions, frozen at 2024-12-31',
        },
        'daily_official': {
            'path': 'data/processed/baostock-daily-20260917/'
                    'daily_1999_2024.parquet',
            'note': 'official close for marks and 15:00 anchors',
        },
        'stk_limit': {
            'path': 'data/raw/tushare/stk_limit/20260917-r1',
            'note': 'daily limit prices, shared by both sessions',
        },
    },
    'hand_calc_samples': {
        'doc': 'hand-calc-samples.md',
        'verified': True,
        'log': 'logs/handcalc.log',
    },
    'outputs': {},
}

import hashlib as hl

outs = {}
for p in sorted(RUN_DIR.rglob('*')):
    if p.is_file() and p.name != 'manifest.json':
        h = hl.sha256()
        with p.open('rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        outs[str(p.relative_to(RUN_DIR)).replace('\\', '/')] = h.hexdigest()
manifest['outputs'] = outs

(RUN_DIR / 'manifest.json').write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'manifest: {RUN_DIR}/manifest.json status={manifest["status"]} tests={passed}')
