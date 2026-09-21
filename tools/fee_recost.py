"""Thin CLI: re-cost saved P2 event studies under the user's real fee rates.

Loads each input run's ``events.parquet`` plus the fee schedule recorded in
that run's own ``config.json`` (the "old" basis), re-prices every completed
trade under the target account fee schedule ("new" basis), verifies the old
fees reproduce exactly, and writes per-event + per-config outputs plus a
manifest into a new run directory.  No strategy is re-run; quantities and
entry notionals are frozen at their saved values.

Usage (from the repo root)::

    PYTHONPATH=src python -X utf8 tools/fee_recost.py \
        --out artifacts/runs/<run_id> tag=<run_dir> [tag=<run_dir> ...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from datetime import date, datetime
from pathlib import Path

import polars as pl

from quant.research.screen import FeeBand
from quant.research.fee_recost import (
    FeeRecostError,
    recost_events,
    summarize,
    validate_target_schedule,
)

# User account actual rates as research input (2026-09-17).  Stocks:
# commission 0.025% both legs with a 5 CNY minimum, stamp duty 0.05% on sells
# (current single-sided rate -- ASSUMPTION to verify against the live
# account).  ETFs: commission 0.01% no minimum, no stamp -- recorded here for
# disclosure only; every re-costed run is stock-only.
TARGET_SCHEDULE: tuple[FeeBand, ...] = (
    FeeBand(date(2015, 1, 1), 0.00025, 5.0, 0.0005),
)
TARGET_ETF_RATE = {'commission_pct': 0.0001, 'commission_min': 0.0,
                   'stamp_sell_pct': 0.0, 'applies_to': 'none of these runs'}

ASSUMPTIONS = {
    'commission_stock_pct': 0.00025,
    'commission_stock_min': 5.0,
    'stamp_sell_pct': 0.0005,
    'stamp_note': ('current single-sided 0.05% rate applied to ALL exit '
                   'dates, including 2015-2023-08 when the historical rate '
                   'was 0.1%; verify against the live account'),
    'slippage': 0.0,
    'quantity_frozen': True,
    'etf_rate': TARGET_ETF_RATE,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def old_schedule_from_config(config: dict) -> tuple[FeeBand, ...]:
    bands = tuple(
        FeeBand(date.fromisoformat(b['from']), float(b['commission_pct']),
                float(b['commission_min']), float(b.get('stamp_sell_pct', 0.0)))
        for b in config['fees']['schedule'])
    return bands


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path,
                        help='output run directory (created, must not exist)')
    parser.add_argument('runs', nargs='+', metavar='tag=run_dir',
                        help='input run directory with events.parquet')
    args = parser.parse_args(argv)

    if args.out.exists():
        parser.error(f'output directory already exists: {args.out}')

    started = datetime.now().astimezone()
    inputs = []
    frames = []
    for spec in args.runs:
        tag, _, run_dir_text = spec.partition('=')
        run_dir = Path(run_dir_text).resolve()
        manifest_path = run_dir / 'manifest.json'
        config_path = run_dir / 'config.json'
        events_path = run_dir / 'events.parquet'
        for path in (manifest_path, config_path, events_path):
            if not path.exists():
                print(f'ERROR: missing {path}', file=sys.stderr)
                return 2
        run_manifest = json.loads(
            manifest_path.read_text(encoding='utf-8'))
        config = json.loads(config_path.read_text(encoding='utf-8'))
        old_schedule = old_schedule_from_config(config)
        events = pl.read_parquet(events_path)
        recosted = recost_events(events, run_tag=tag, old_schedule=old_schedule,
                                 target_schedule=TARGET_SCHEDULE)
        frames.append(recosted)
        inputs.append({
            'tag': tag,
            'run_id': run_manifest.get('run_id'),
            'experiment_id': run_manifest.get('experiment_id'),
            'run_status': run_manifest.get('status'),
            'path': str(run_dir),
            'config_sha256': run_manifest.get('config_sha256'),
            'events_sha256': sha256_file(events_path),
            'n_events_total': events.height,
            'n_completed_recosted': recosted.height,
        })
        print(f'{tag}: {run_manifest.get("run_id")} recosted '
              f'{recosted.height}/{events.height} events', flush=True)

    all_events = pl.concat(frames, how='vertical')
    summary = summarize(all_events)

    args.out.mkdir(parents=True)
    tmp = args.out / 'tmp'
    tmp.mkdir()
    events_out = args.out / 'recost_events.parquet'
    summary_csv = args.out / 'recost_summary.csv'
    summary_json = args.out / 'recost_summary.json'
    all_events.write_parquet(events_out)
    summary.write_csv(summary_csv)

    overall = summarize(
        all_events.with_columns(pl.lit('ALL').alias('run_tag'),
                                pl.lit('ALL').alias('config_id'),
                                pl.col('window')))
    summary_payload = {
        'assumptions': ASSUMPTIONS,
        'target_schedule': [{'from': b.from_date.isoformat(),
                             'commission_pct': b.commission_pct,
                             'commission_min': b.commission_min,
                             'stamp_sell_pct': b.stamp_sell_pct}
                            for b in TARGET_SCHEDULE],
        'per_config_window': summary.to_dicts(),
        'grand_total': overall.to_dicts(),
    }
    summary_json.write_text(json.dumps(summary_payload, ensure_ascii=False,
                                       indent=1), encoding='utf-8')

    here = Path(__file__).resolve()
    repo_root = here.parent.parent
    module_path = repo_root / 'src' / 'quant' / 'research' / 'fee_recost.py'
    ended = datetime.now().astimezone()
    manifest = {
        'run_id': args.out.name,
        'experiment_id': 'exp-20260917-fee-recost',
        'status': 'completed',
        'started_at': started.isoformat(),
        'ended_at': ended.isoformat(),
        'duration_s': round((ended - started).total_seconds(), 3),
        'command': [sys.executable, '-X', 'utf8',
                    str(here.relative_to(repo_root)), *argv],        'inputs': inputs,
        'assumptions': ASSUMPTIONS,
        'environment': {
            'python': sys.version.split()[0],
            'platform': platform.platform(),
            'polars': pl.__version__,
        },
        'source_sha256': {
            'tools/fee_recost.py': sha256_text(here.read_text(encoding='utf-8')),
            'src/quant/research/fee_recost.py': sha256_text(
                module_path.read_text(encoding='utf-8')),
        },
        'outputs': {
            'recost_events.parquet': events_out.name,
            'recost_summary.csv': summary_csv.name,
            'recost_summary.json': summary_json.name,
        },
    }
    (args.out / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding='utf-8')
    tmp.rmdir()
    print(f'wrote {args.out}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except FeeRecostError as error:
        print(f'FEE RECOST FAILED: {error}', file=sys.stderr)
        raise SystemExit(1)
