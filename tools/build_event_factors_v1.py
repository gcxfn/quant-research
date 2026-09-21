"""Build event factor tables v1 from the six tushare event batches.

Pure data engineering (no strategy conclusions, no backtest):
reads data/raw/tushare/{forecast,express,repurchase,share_float,
stk_holdertrade,disclosure_date} read-only, structures each family with
quant.data.event_batches, applies the 2024-12-31 freeze line on
ts_available, flags baostock-pool membership, and writes one parquet per
family plus a merged manifest under
data/features/event-factors-v1-20260918/.

Run record: artifacts/runs/<run_id>/ (manifest, script copies, console log).
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from quant.data import event_batches as eb  # noqa: E402
from quant.research.runs import Run, sha256  # noqa: E402

FEATURE_SET_ID = 'event-factors-v1-20260918'
OUT_DIR = ROOT / 'data' / 'features' / FEATURE_SET_ID
CALENDAR_CSV = ROOT / 'data/raw/tushare/index_daily/20260917-r1/chunk_000300.SH.csv'
POOL_PARQUET = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
POOL_RAW_DIR = ROOT / 'data/raw/baostock/daily'

FAMILIES = {
    'forecast': {
        'batch': 'data/raw/tushare/forecast/20260909-r1',
        'glob': 'chunk_*.csv', 'builder': eb.build_forecast,
        'event_type': 'forecast', 'output': 'forecast.parquet',
        'ts_event': 'end_date (报告期期末)',
        'magnitude': 'p_change_min（%，相对上年同期净利润区间下界）',
        'magnitude_unit': 'percent (yoy net profit interval lower bound; magnitude_max holds upper bound)',
        'raw_text': 'change_reason（另保留 summary 列）',
    },
    'express': {
        'batch': 'data/raw/tushare/express/20260909-r1',
        'glob': 'chunk_period_*.csv', 'builder': eb.build_express,
        'event_type': 'express', 'output': 'express.parquet',
        'ts_event': 'end_date (报告期期末)',
        'magnitude': 'yoy_net_profit（元，tushare express 口径原值）',
        'magnitude_unit': 'yuan (yoy_net_profit as published)',
        'raw_text': None,
    },
    'repurchase': {
        'batch': 'data/raw/tushare/repurchase/20260909-r3',
        'glob': 'chunk_*.csv', 'builder': eb.build_repurchase,
        'event_type': 'repurchase_plan', 'output': 'repurchase.parquet',
        'ts_event': 'ann_date（首次预案公告日，禁用后视状态）',
        'magnitude': 'null（v1 不带规模字段）',
        'magnitude_unit': 'null',
        'raw_text': None,
    },
    'share_float': {
        'batch': 'data/raw/tushare/share_float/20260909-r3',
        'glob': 'chunk_*.csv', 'builder': eb.build_share_float,
        'event_type': 'unlock', 'output': 'share_float.parquet',
        'ts_event': 'float_date（解禁日）',
        'magnitude': '聚合 float_ratio（%，占总股本比例，同组各行求和）',
        'magnitude_unit': 'percent of total share capital (summed ratio)',
        'raw_text': None,
    },
    'stk_holdertrade': {
        'batch': 'data/raw/tushare/stk_holdertrade/20260909-r3',
        'glob': 'chunk_*.csv', 'builder': eb.build_holdertrade,
        'event_type': 'holder_trade', 'output': 'stk_holdertrade.parquet',
        'ts_event': 'ann_date（行为日缺失，事后公告）',
        'magnitude': 'change_ratio（%，占 总股本 比例变动）',
        'magnitude_unit': 'percent (change_ratio as published)',
        'raw_text': None,
    },
    'disclosure_date': {
        'batch': 'data/raw/tushare/disclosure_date/20260909-r1',
        'glob': 'chunk_period_*.csv', 'builder': eb.build_disclosure,
        'event_type': 'disclosure_shift', 'output': 'disclosure_date.parquet',
        'ts_event': 'pre_date（预约披露日）',
        'magnitude': 'null',
        'magnitude_unit': 'null',
        'raw_text': None,
    },
}


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def read_family_chunks(batch_dir: Path, pattern: str) -> tuple[pl.DataFrame, dict]:
    files = sorted(batch_dir.glob(pattern))
    frames, empty = [], 0
    for f in files:
        try:
            df = pl.read_csv(f, infer_schema_length=0)
        except Exception:
            empty += 1
            continue
        if df.height:
            frames.append(df)
        else:
            empty += 1
    if not frames:
        raise RuntimeError(f'no data rows in {batch_dir}')
    return pl.concat(frames, how='vertical_relaxed'), {
        'chunk_files': len(files), 'empty_chunk_files': empty,
    }


def load_pool_codes() -> tuple[set[str], set[str], dict]:
    syms = (
        pl.scan_parquet(POOL_PARQUET).select(pl.col('symbol').unique())
        .collect()['symbol'].sort().to_list()
    )
    codes = {f"{s.split('.')[1]}.{s.split('.')[0].upper()}" for s in syms}
    raw_universe = {
        f"{p.stem.split('.')[1]}.{p.stem.split('.')[0].upper()}"
        for p in POOL_RAW_DIR.glob('*.csv')
    }
    raw_files = len(raw_universe)
    return codes, raw_universe, {
        'dataset_id': 'baostock-daily-20260917',
        'source_parquet': str(POOL_PARQUET.relative_to(ROOT)),
        'n_codes_freeze_filtered': len(codes),
        'raw_universe_files': raw_files,
        'note': (
            '池取 processed 数据集 distinct symbol（冻结过滤后）；raw baostock/daily '
            f'全宇宙 {raw_files} 只，差额为 2025 年后上市、仅存在于冻结线外的代码——'
            '这些代码不可能有 ts_available<=2024-12-31 的事件行，对入界行无影响'
        ),
    }


def main() -> None:
    config = {
        'experiment_id': 'exp-20260918-event-structuring',
        'feature_set_id': FEATURE_SET_ID,
        'freeze_boundary': '2024-12-31',
        'direction_dictionary_version': eb.DIRECTION_DICTIONARY_VERSION,
    }
    with Run(ROOT, 'event-struct-v1', config) as run:
        log_path = run.path / 'logs' / 'console.log'
        with log_path.open('w', encoding='utf-8') as log_file:
            sys.stdout = _Tee(sys.stdout, log_file)
            print(f'== {FEATURE_SET_ID} build, run {run.id} ==')

            cal = eb.load_trade_calendar(CALENDAR_CSV)
            pool_codes, raw_universe, pool_meta = load_pool_codes()
            print(f'calendar: {len(cal)} days {cal[0]}..{cal[-1]}; pool codes: {len(pool_codes)} '
                  f'(raw universe {len(raw_universe)})')

            families_manifest = {}
            for family, spec in FAMILIES.items():
                batch_dir = ROOT / spec['batch']
                raw, chunk_stats = read_family_chunks(batch_dir, spec['glob'])
                print(f'[{family}] raw rows: {raw.height} from {chunk_stats["chunk_files"]} files '
                      f'({chunk_stats["empty_chunk_files"]} empty)')
                events, stats = spec['builder'](
                    raw, f'tushare/{family}/{Path(spec["batch"]).name}', cal
                )
                kept, oob = eb.split_freeze(events)
                kept = eb.flag_pool(kept, pool_codes)
                col_order = eb.EVENT_COLUMNS + [
                    c for c in eb.FORECAST_EXTRA_COLUMNS + eb.SHARE_FLOAT_EXTRA_COLUMNS
                    if c in kept.columns
                ]
                kept = kept.select(col_order)
                out_path = OUT_DIR / spec['output']
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                kept.write_parquet(out_path, compression='zstd')

                families_manifest[family] = {
                    'input_batch': spec['batch'],
                    'batch_manifest': 'manifest.json',
                    'batch_manifest_sha256': sha256(batch_dir / 'manifest.json'),
                    'event_type': spec['event_type'],
                    'output_file': spec['output'],
                    'output_rows': int(kept.height),
                    'output_sha256': sha256(out_path),
                    'raw_rows': int(raw.height),
                    'in_bounds_rows': int(kept.height),
                    'out_of_bounds_rows': oob,
                    'in_pool_true': int(kept['in_pool'].sum()),
                    'in_pool_false': int((~kept['in_pool']).sum()),
                    'outside_raw_universe_rows': int(
                        kept.filter(~pl.col('ts_code').is_in(sorted(raw_universe))).height
                    ),
                    'direction_zero_rows': int((kept['direction'] == 0).sum()),
                    **chunk_stats,
                    **stats,
                }
                print(f'[{family}] kept {kept.height} (oob {oob}, in_pool_false '
                      f'{families_manifest[family]["in_pool_false"]}) -> {out_path.name}')

            manifest = {
                'feature_set_id': FEATURE_SET_ID,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'run_id': run.id,
                'purpose': '纯数据工程：事件类原始批次结构化为统一事件表 v1；不含策略、回测或收益结论',
                'freeze_boundary': eb.FREEZE_END.isoformat(),
                'research_window': '2015-2024',
                'time_contract': {
                    'ts_knowledge': 'ann_date（缺失 fail-closed 剔除并计数）',
                    'ts_event': '见 families.*.field_spec',
                    'ts_available': 'ts_knowledge 的次一交易日（严格大于；早于日历首日映射到首日并计数）',
                    'in_bounds': 'ts_available <= 2024-12-31；超界行仅计数不写表',
                },
                'direction_dictionary': {
                    'version': eb.DIRECTION_DICTIONARY_VERSION,
                    'forecast': {**eb.FORECAST_DIRECTION,
                                 '_else': '其余 type（不确定/增亏/减亏/其他/null）→ 0'},
                    'express': 'sign(yoy_net_profit)；null/0 → 0',
                    'repurchase_plan': '常量 +1（proc=预案）',
                    'unlock': '常量 -1（供给压力）',
                    'holder_trade': {**eb.HOLDERTRADE_DIRECTION,
                                     '_else': 'IN/DE 之外剔除并计数'},
                    'disclosure_shift': '常量 0',
                },
                'field_spec': {
                    fam: {
                        'event_type': spec['event_type'],
                        'ts_event': spec['ts_event'],
                        'ts_knowledge': 'ann_date',
                        'direction_source': (
                            'derived' if fam == 'express' else 'field_enum'
                        ),
                        'confidence': (
                            'high' if fam in ('forecast', 'express', 'repurchase')
                            else 'medium'
                        ),
                        'magnitude': spec['magnitude'],
                        'raw_text': spec['raw_text'],
                        'candidate_pk_note': '见 pk_report.candidate_key',
                    }
                    for fam, spec in FAMILIES.items()
                },
                'magnitude_units': {fam: spec['magnitude_unit'] for fam, spec in FAMILIES.items()},
                'calendar': {
                    'path': str(CALENDAR_CSV.relative_to(ROOT)),
                    'sha256': sha256(CALENDAR_CSV),
                    'n_days': len(cal),
                    'first': cal[0].isoformat(),
                    'last': cal[-1].isoformat(),
                },
                'pool': pool_meta,
                'source_code': {
                    'module': 'src/quant/data/event_batches.py',
                    'module_sha256': sha256(ROOT / 'src/quant/data/event_batches.py'),
                    'tool': 'tools/build_event_factors_v1.py',
                    'tool_sha256': sha256(Path(__file__).resolve()),
                },
                'families': families_manifest,
            }
            (OUT_DIR / 'manifest.json').write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False),
                encoding='utf-8',
            )
            run.metrics['families'] = {
                fam: {
                    'in_bounds': m['in_bounds_rows'],
                    'out_of_bounds': m['out_of_bounds_rows'],
                    'in_pool_false': m['in_pool_false'],
                    'removed_bj': m['removed_bj'],
                    'removed_nonstandard': m['removed_nonstandard'],
                    'fail_closed_missing_knowledge': m['fail_closed_missing_knowledge_dropped'],
                }
                for fam, m in families_manifest.items()
            }
            run.manifest['inputs'] = {
                'calendar': manifest['calendar'],
                'pool': pool_meta,
                'batches': {
                    fam: {
                        'path': m['input_batch'],
                        'manifest_sha256': m['batch_manifest_sha256'],
                        'raw_rows': m['raw_rows'],
                    }
                    for fam, m in families_manifest.items()
                },
                'outputs': {
                    'dir': str(OUT_DIR.relative_to(ROOT)),
                    'manifest_sha256': sha256(OUT_DIR / 'manifest.json'),
                },
            }

        # script copies into the run directory
        shutil.copy2(Path(__file__).resolve(), run.path / 'build_event_factors_v1.py')
        shutil.copy2(ROOT / 'src/quant/data/event_batches.py',
                     run.path / 'event_batches_module_copy.py')
        sys.stdout = sys.__stdout__
        print(f'features manifest: {OUT_DIR / "manifest.json"}')


if __name__ == '__main__':
    main()
