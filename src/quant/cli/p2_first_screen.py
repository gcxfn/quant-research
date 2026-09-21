"""P2 first screen CLI: run the preregistered event study and archive evidence.

Usage:
  python src/quant/cli/p2_first_screen.py [--config configs/experiments/p2-first-screen.json]
      [--symbols 200]   # deterministic smoke subset
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research.p2_first_screen import (  # noqa: E402
    DEV_END,
    VALIDATION_START,
    attach_factors,
    benchmark_series_mean,
    build_eligible,
    concentration,
    h3_gate_check,
    index_daily_returns,
    load_daily,
    pool_daily_returns,
    run_random_config,
    run_signal_config,
    selection_verdicts,
    validation_verdicts,
    window_summary,
    _window_frame,
)
from quant.research.runs import Run, find_repo_root, sha256, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2-first-screen.json')
    parser.add_argument('--symbols', type=int, default=None,
                        help='deterministic smoke subset size')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.symbols:
        config = dict(config)
        config['smoke_symbols'] = args.symbols

    import os
    os.chdir(ROOT)

    root = find_repo_root()
    with Run(root, config['name'], config) as run:
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        daily = load_daily(root, config, symbol_limit=args.symbols)
        timings['load_parquet_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        daily = attach_factors(daily, root, config)
        timings['adjustment_join_s'] = time.perf_counter() - t0
        run.manifest['inputs'] = [
            {'path': config['data']['file'], 'sha256': sha256(root / config['data']['file']),
             'rows': daily.height, 'symbols': daily['symbol'].n_unique(),
             'dataset_id': config['data']['dataset_id']},
            {'path': config['data']['adj_factors'], 'rows': None,
             'note': 'xiaodefa adj_factor chunks, read window-filtered'},
        ]
        run.metrics['timings'] = timings
        run.metrics['data_identity'] = run.manifest['inputs'][0]

        t0 = time.perf_counter()
        eligible = build_eligible(daily, config)
        timings['eligible_gate_s'] = time.perf_counter() - t0
        run.metrics['eligible'] = {
            'rows': eligible.height,
            'symbols': eligible['symbol'].n_unique(),
            'date_min': str(eligible['date'].min()),
            'date_max': str(eligible['date'].max()),
        }

        calendar = daily.select('date').unique().sort('date')['date']

        signal_sets = list(config['signal_sets'])
        holds = [int(h) for h in config['execution']['holds']]

        benchmarks: dict[str, dict] = {}
        t0 = time.perf_counter()
        for hold in holds:
            pool = pool_daily_returns(daily, eligible, hold)
            pool.write_parquet(run.path / f'pool_hold{hold}.parquet')
            benchmarks[f'hold_{hold}'] = {
                'pool': pool,
                'random': run_random_config(daily, eligible, calendar, hold, config),
                'index': {name: index_daily_returns(daily, sym, hold)
                          for name, sym in config['benchmarks']['broad_index'].items()},
            }
        timings['benchmarks_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        all_events = []
        results: dict[str, dict] = {}
        for signal_set in signal_sets:
            for hold in holds:
                outcome = run_signal_config(daily, eligible, calendar, signal_set,
                                            hold, config)
                config_id = f'{signal_set}-h{hold}'
                events = outcome.events.with_columns(
                    pl.lit(config_id).alias('config_id'),
                    pl.lit(signal_set).alias('signal_set'),
                    pl.lit(hold).alias('hold'))
                all_events.append(events)
                events_w = _window_frame(events)
                pool = benchmarks[f'hold_{hold}']['pool']
                dev = window_summary(events_w, 'dev', pool, hold)
                val = window_summary(events_w, 'validation', pool, hold)
                conc = concentration(events_w, 'dev')
                verdicts = {
                    'dev': selection_verdicts(dev, conc),
                    'validation': validation_verdicts(val),
                    'benchmarks_dev': {
                        'random_net_mean_pct': None,
                        'csi500_mean_pct': None,
                        'csi1000_mean_pct': None,
                    },
                    'benchmarks_validation': {},
                    'n_purged_at_boundary': outcome.n_purged_boundary,
                }
                random_w = _window_frame(
                    benchmarks[f'hold_{hold}']['random'].with_columns(
                        pl.lit(hold).alias('hold')))
                for window in ('dev', 'validation'):
                    done = random_w.filter((pl.col('window') == window)
                                           & (pl.col('status') == 'completed_label'))
                    verdicts[f'benchmarks_{window}']['random_net_mean_pct'] = (
                        done['net_return_pct'].mean() if done.height else None)
                    for name in config['benchmarks']['broad_index']:
                        verdicts[f'benchmarks_{window}'][f'{name.lower()}_mean_pct'] = (
                            benchmark_series_mean(
                                benchmarks[f'hold_{hold}']['index'][name], 'idx_ret', window))
                results[config_id] = {
                    'signal_set': signal_set, 'hold': hold,
                    'dev': dev, 'validation': val,
                    'concentration_dev': conc, 'verdicts': verdicts,
                }
        timings['event_study_s'] = time.perf_counter() - t0

        # H3 gate falsifier: pooled H1 events across holds, dev window
        # (rounds without H1-reversal configs record the check as not applicable)
        h1_frames = [e for e in all_events
                     if 'H1-reversal' in e['signal_set'].unique().to_list()]
        if h1_frames and 'h3_gate_check' in config:
            h3 = h3_gate_check(_window_frame(pl.concat(h1_frames)), 'dev')
            threshold = float(config['h3_gate_check']['falsify_if_above'])
            results['H3_gate_check'] = {
                **h3,
                'falsify_if_above': threshold,
                'falsified': (h3.get('bottom_tercile_share') is not None
                              and h3['bottom_tercile_share'] > threshold),
            }
        else:
            results['H3_gate_check'] = {'n_completed': 0, 'bottom_tercile_share': None,
                                        'falsified': False,
                                        'note': 'not applicable this round (no H1 configs)'}

        events_frame = pl.concat(all_events).sort('config_id', 'signal_date', 'symbol')
        events_frame.write_parquet(run.path / 'events.parquet')
        run.metrics['timings'] = timings
        run.metrics['n_events_total'] = events_frame.height
        run.metrics['configs'] = results
        survivors = sorted(cid for cid, r in results.items()
                           if cid != 'H3_gate_check'
                           and r['verdicts']['dev']['dev_pass']
                           and r['verdicts']['validation']['validation_pass'])
        run.metrics['p2_survivors'] = survivors[:2]

        report = build_report(config, results, survivors, run.metrics['eligible'],
                              timings)
        (run.path / 'report.md').write_text(report, encoding='utf-8')
        print(f"survivors: {run.metrics['p2_survivors']}")
    return 0 if run.manifest['status'] == 'completed' else 1


def build_report(config: dict, results: dict, survivors: list[str],
                 eligible_stats: dict, timings: dict) -> str:
    lines = [
        '# P2 first screen（预登记事件研究）', '',
        f'- 实验ID：{config["experiment_id"]}，种子 {config["seed"]}',
        f"- 入选池：{eligible_stats['symbols']} 只 / {eligible_stats['rows']} 行"
        f"（{eligible_stats['date_min']}..{eligible_stats['date_max']}）",
        f"- 窗口：dev 2015-01-05..2020-12-31（出口端隔离），validation 2021-01-01..2024-12-31",
        f"- 费用：历史分段（印花税千1→2023-08-28 万5；佣金为保守假设分段，非用户实参）",
        f"- 计时（秒）：{json.dumps({k: round(v, 2) for k, v in timings.items()})}",
        '',
        '## 各配置结果（净收益为每笔完成事件的百分比均值）', '',
        '| 配置 | dev 笔数/完成率 | dev 净/池净 | 正优势年 | 集中度 | 验证 净/池净 | 验证正优势年 | 判定 |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for config_id, r in sorted(results.items()):
        if config_id == 'H3_gate_check':
            continue
        dev, val, conc = r['dev'], r['validation'], r['concentration_dev']
        verdict = ('**存活**' if config_id in survivors else
                   'dev 通过/验证未过' if r['verdicts']['dev']['dev_pass'] else '淘汰')
        lines.append(
            f"| {config_id} | {dev['n_events']}/{(dev['completion_rate'] or 0):.0%} "
            f"| {fmt(dev['mean_net_pct'])} / {fmt(dev['pool_mean_pct'])} "
            f"| {r['verdicts']['dev']['positive_edge_years']} "
            f"| {fmt_pct(conc['top_decile_share'])} "
            f"| {fmt(val['mean_net_pct'])} / {fmt(val['pool_mean_pct'])} "
            f"| {r['verdicts']['validation']['positive_edge_years']} "
            f"| {verdict} |")
    h3 = results['H3_gate_check']
    h3_note = h3.get('note')
    lines += [
        '',
        '## H3 流动性门禁检验', '',
        f"- H1 dev 完成事件 {h3.get('n_completed', 0)} 笔，"
        f"低成交额三分位利润占比 {fmt_pct(h3.get('bottom_tercile_share'))}"
        f"（>{fmt_pct(h3.get('falsify_if_above')) if h3.get('falsify_if_above') is not None else '—'} 判伪）→ "
        f"{'**判伪**' if h3['falsified'] else ('不适用' if h3_note else '未判伪')}", '',
        '## 逐年净优势（对池基准，百分点）', '',
    ]
    for config_id, r in sorted(results.items()):
        if config_id == 'H3_gate_check':
            continue
        rows = [f"{y['year']}:{fmt(y.get('net_edge_pct'))}"
                for y in r['dev']['per_year'] + r['validation']['per_year']]
        lines.append(f'- {config_id}: ' + ', '.join(rows))
    lines += [
        '',
        '## 声明', '',
        '- 本表为初筛事件研究：日线触价代理、按建议口径成交、无滑点（P3 三档敏感性）。',
        '- 佣金分段为保守假设，非用户实参（实参 万1 全包，P3 使用）。',
        '- 2015–2024 曾被旧项目查看：滚动历史验证，不构成样本外证明。',
        f'- 存活配置（至多 2 个进入 P3）：{survivors if survivors else "无"}',
    ]
    return '\n'.join(lines) + '\n'


def fmt(value: float | None) -> str:
    return '—' if value is None else f'{value:.3f}'


def fmt_pct(value: float | None) -> str:
    return '—' if value is None else f'{value:.1%}'


if __name__ == '__main__':
    raise SystemExit(main())
