"""Thin entry: build the RQAlpha-native bundle (see src/quant/data/rqalpha_bundle.py).

Creates an artifacts/runs/<run_id>/ manifest (status/started/finished/command/
inputs/environment/timings) around one deterministic bundle build.  Default
output is data/processed/rqalpha-bundle-v2-1-20260918 (full v2.1 pool: v2 scope
plus ETF share-conversion split rows and five real index series); pass
--pool-limit N for a budgeting pilot (output defaults under data/cache/ and
input hashing is skipped there -- disclosed in the pilot manifest).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from quant.data import rqalpha_bundle as etl
from quant.research.runs import find_repo_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-id', default='rqalpha-bundle-v2-1-20260918')
    parser.add_argument('--pool-limit', type=int, default=None,
                        help='pilot mode: trim each pool to N sorted oids')
    parser.add_argument('--out', default=None,
                        help='override output dir (default data/processed/<dataset-id>, '
                             'pilot default data/cache/rqalpha-pilot-<N>)')
    args = parser.parse_args()

    root = find_repo_root()
    if args.out:
        out_dir = root / args.out
    elif args.pool_limit is not None:
        out_dir = root / 'data' / 'cache' / f'rqalpha-pilot-{args.pool_limit}'
    else:
        out_dir = root / 'data' / 'processed' / args.dataset_id

    now = datetime.now()
    topic = 'rqalpha-bundle-v21' if args.pool_limit is None else 'rqalpha-bundle-v21-pilot'
    run_id = now.strftime('%Y%m%dT%H%M%S') + '-' + topic + '-' + uuid.uuid4().hex[:8]
    run_dir = root / 'artifacts' / 'runs' / run_id
    (run_dir / 'logs').mkdir(parents=True, exist_ok=False)

    manifest = {
        'run_id': run_id,
        'status': 'running',
        'started_at': now.isoformat(timespec='seconds'),
        'task': ('RQAlpha self-built bundle v2.1 ETL: v2 scope (4745 stocks + 1169 '
                 'ETFs, tushare fund_daily primary source, real stk_limit, stock '
                 'dividends/splits, ETF fund_adj factors) PLUS red-team R3-1 fix '
                 '(ETF share-conversion events -> split_factor.h5) and index '
                 'backfill (five real tushare index_daily series, full window)'),
        'command': [sys.executable, '-X', 'utf8', *sys.argv],
        'env': {
            'python': sys.version.split()[0],
            'cwd': str(Path.cwd()),
            'PYTHONPATH': os.environ.get('PYTHONPATH', ''),
            'pythonpath_note': 'PYTHONPATH=src makes quant.* resolve to src/, '
                               'not the copied site-packages install',
        },
        'inputs': {
            'generator': 'src/quant/data/rqalpha_bundle.py',
            'generator_sha256': etl._module_sha256(),
            'output_dir': str(out_dir),
            'pool_limit': args.pool_limit,
        },
        'outputs': [str(run_dir), str(out_dir)],
        'notes': [
            'freeze line: no 2025+ data enters the bundle (asserted by build_bundle)',
            'engine built-in A-share semantics are exempted from independent '
            're-verification by user decision (docs/decisions/2026-09-17-rqalpha-account-engine.md)',
            'budget: measured v2 build total 120.8s (20260917T231506 run); v2.1 adds '
            'only the index_daily reads + fund_adj event rescan (~10s), far below '
            'the 45-minute ceiling, so the build runs in one pass without staging',
        ],
    }
    (run_dir / 'manifest.json').write_text(
        json.dumps(manifest, indent=1, ensure_ascii=False), encoding='utf-8')

    status, error = 'completed', None
    t0 = time.perf_counter()
    bundle_manifest = None
    try:
        bundle_manifest = etl.build_bundle(
            root, out_dir,
            etl.BundleSpec(dataset_id=args.dataset_id, window=etl.FULL_WINDOW,
                           calendar_range=(etl.RESEARCH_START, etl.FREEZE_END)),
            pool_limit=args.pool_limit,
            hash_inputs=args.pool_limit is None)
        manifest['bundle_manifest_summary'] = {
            k: bundle_manifest[k] for k in
            ('dataset_id', 'created_at', 'params', 'data_quality', 'freeze')}
        manifest['bundle_placeholders'] = bundle_manifest['placeholders']
        if args.pool_limit is None:
            manifest['bundle_inputs'] = bundle_manifest['inputs']
    except Exception:
        status, error = 'failed', traceback.format_exc()
        raise
    finally:
        manifest['status'] = status
        manifest['finished_at'] = datetime.now().isoformat(timespec='seconds')
        manifest['elapsed_seconds'] = round(time.perf_counter() - t0, 2)
        manifest['error'] = error
        (run_dir / 'manifest.json').write_text(
            json.dumps(manifest, indent=1, ensure_ascii=False, default=str),
            encoding='utf-8')
        sys.stdout.write(f'status={status} elapsed={manifest["elapsed_seconds"]}s '
                         f'out={out_dir}\n')
    return 0 if status == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
