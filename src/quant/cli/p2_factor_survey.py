"""P2 round-4 factor survey CLI: cross-section + tail exam + combinations.

Usage:
  python src/quant/cli/p2_factor_survey.py [--config configs/experiments/p2-round4-factor-survey.json]
      [--symbols 200]
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

from quant.research.factor_survey import (  # noqa: E402
    FACTOR_COLUMNS,
    build_factor_panel,
    build_screen_config,
    ic_series,
    load_cyq,
    load_daily_basic,
    load_margin,
    load_moneyflow,
    quintile_spread,
    sign_consistency,
    tail_events,
    window_ic_stats,
)
from quant.research.p2_first_screen import (  # noqa: E402
    DEV_END,
    VALIDATION_START,
    _window_frame,
    build_eligible,
    load_daily,
    pool_daily_returns,
    run_random_config,
    window_summary,
)
from quant.research.runs import Run, find_repo_root, sha256, write_json  # noqa: E402
from quant.research.screen import STATUS_COMPLETED  # noqa: E402

DEVELOPMENT_END = DEV_END
PARTIAL_COVERAGE = {'winner_rate': 2018, 'margin_buy_ratio': 2019}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2-round4-factor-survey.json')
    parser.add_argument('--symbols', type=int, default=None)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.symbols:
        config = dict(config)
        config['smoke_symbols'] = args.symbols

    import os
    os.chdir(ROOT)

    root = find_repo_root()
    start = date.fromisoformat(config['start'])
    end = date.fromisoformat(config['end'])
    with Run(root, config['name'], config) as run:
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        daily = load_daily(root, config, symbol_limit=args.symbols)
        from quant.research.p2_first_screen import attach_factors
        daily = attach_factors(daily, root, config)
        timings['daily_load_s'] = time.perf_counter() - t0
        run.manifest['inputs'] = [{
            'path': config['data']['file'], 'sha256': sha256(root / config['data']['file']),
            'rows': daily.height, 'symbols': daily['symbol'].n_unique(),
            'dataset_id': config['data']['dataset_id']}]

        t0 = time.perf_counter()
        eligible = build_eligible(daily, config)
        timings['eligible_gate_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        extras = {
            'moneyflow': load_moneyflow(root, start, end),
            'daily_basic': load_daily_basic(root, start, end),
            'cyq_perf': load_cyq(root, start, end),
            'margin_detail': load_margin(root, start, end),
        }
        timings['extra_sources_s'] = time.perf_counter() - t0
        run.metrics['extra_source_rows'] = {k: v.height for k, v in extras.items()}

        t0 = time.perf_counter()
        panel = build_factor_panel(daily, eligible, root, start, end, extras)
        timings['factor_panel_s'] = time.perf_counter() - t0
        run.metrics['panel'] = {'rows': panel.height,
                                'symbols': panel['symbol'].n_unique(),
                                'fwd_ret_coverage': panel['fwd_ret'].is_not_null().sum()}
        panel.write_parquet(run.path / 'factor_panel.parquet')

        calendar = daily.select('date').unique().sort('date')['date']
        cfg = build_screen_config(config, int(config['protocol']['hold_days']))

        t0 = time.perf_counter()
        pool = pool_daily_returns(daily, eligible, int(config['protocol']['hold_days']))
        pool.write_parquet(run.path / 'pool_hold5.parquet')
        random_w = _window_frame(run_random_config(
            daily, eligible, calendar, int(config['protocol']['hold_days']),
            config).with_columns(pl.lit(5).alias('hold')))
        timings['benchmarks_s'] = time.perf_counter() - t0

        # ---- per-factor survey on dev; validation touched only for reporting
        t0 = time.perf_counter()
        factor_results: dict[str, dict] = {}
        screened_in: list[str] = []
        for factor in FACTOR_COLUMNS:
            entry = survey_factor(factor, panel, pool, daily, calendar, cfg, config)
            factor_results[factor] = entry
            if entry['survey_pass']:
                screened_in.append(factor)
        timings['factor_survey_s'] = time.perf_counter() - t0

        # ---- preregistered combinations (weights frozen by dev signs)
        combos: dict[str, dict] = {}
        t0 = time.perf_counter()
        for combo_id, members in combination_members(config, factor_results):
            combo_events = combination_events(members, factor_results, panel,
                                              daily, calendar, cfg)
            entry = evaluate_events(combo_id, combo_events, pool, config)
            combos[combo_id] = {**entry, 'members': members}
        timings['combinations_s'] = time.perf_counter() - t0

        survivors = [cid for cid, c in combos.items()
                     if c['dev_pass'] and c['validation_pass']][:2]

        run.metrics['timings'] = timings
        run.metrics['factors'] = factor_results
        run.metrics['screened_in'] = screened_in
        run.metrics['combinations'] = combos
        run.metrics['p2_survivors'] = survivors
        report = build_report(config, factor_results, screened_in, combos,
                              survivors, run.metrics['panel'], timings)
        (run.path / 'report.md').write_text(report, encoding='utf-8')
        print(f'screened_in: {screened_in}; survivors: {survivors}')
    return 0 if run.manifest['status'] == 'completed' else 1


def survey_factor(factor: str, panel: pl.DataFrame, pool: pl.DataFrame,
                  daily: pl.DataFrame, calendar: pl.Series, cfg: ScreenConfig,
                  config: dict) -> dict:
    ic = ic_series(panel, factor)
    dev = window_ic_stats(ic, date(2015, 1, 5), DEVELOPMENT_END)
    val = window_ic_stats(ic, VALIDATION_START, date(2024, 12, 31))
    # partial-coverage factors are graded on their covered dev years only
    required_years = 4
    if factor in PARTIAL_COVERAGE:
        covered = [y for y, _ in dev['yearly']] if dev.get('yearly') else []
        required_years = max(1, len([y for y in covered if y >= PARTIAL_COVERAGE[factor]]))
    consistent, detail = sign_consistency(dev, required_years)
    spread = quintile_spread(panel, factor)
    dev_spread = spread.filter(pl.col('date') <= DEVELOPMENT_END)
    direction = 1.0 if (dev['mean_ic'] or 0) >= 0 else -1.0
    events = tail_events(panel, factor, direction, daily, calendar, cfg)
    events_w = _window_frame(events)
    dev_tail = window_summary(events_w, 'dev', pool, cfg.holding_days)
    val_tail = window_summary(events_w, 'validation', pool, cfg.holding_days)
    pool_dev_mean = dev_tail['pool_mean_pct']
    ic_threshold = float(config['screening_rule_dev']['ic_threshold'])
    passes = {
        'ic_ok': dev['mean_ic'] is not None and abs(dev['mean_ic']) >= ic_threshold,
        'consistency_ok': consistent,
        'consistency_detail': detail,
        'tail_ok': (dev_tail['mean_net_pct'] is not None and pool_dev_mean is not None
                    and dev_tail['mean_net_pct'] > pool_dev_mean),
    }
    passes['survey_pass'] = (passes['ic_ok'] and passes['consistency_ok']
                             and passes['tail_ok'])
    return {'dev_ic': dev, 'val_ic': val, 'direction': direction,
            'dev_q5_q1_pct': (float(dev_spread['spread_q5_q1'].mean()) * 100.0
                              if dev_spread.height else None),
            'dev_tail': dev_tail, 'val_tail': val_tail,
            'n_events': events_w.height, **passes}


def combination_members(config: dict,
                        factor_results: dict[str, dict]) -> list[tuple[str, list[str]]]:
    screened = [f for f, r in factor_results.items() if r['survey_pass']]
    plans = [('C1-all-z', screened)]
    by_ir = sorted(screened,
                   key=lambda f: abs(factor_results[f]['dev_ic']['ic_ir'] or 0.0),
                   reverse=True)
    plans.append(('C2-top3-icir', by_ir[:3]))
    return [(cid, members) for cid, members in plans if members]


def combination_events(members: list[str], factor_results: dict[str, dict],
                       panel: pl.DataFrame, daily: pl.DataFrame,
                       calendar: pl.Series, cfg) -> pl.DataFrame:
    """Equal-weight sum of per-day z-scores, each signed by its dev IC sign."""
    frame = panel
    zcols = []
    for i, factor in enumerate(members):
        direction = factor_results[factor]['direction']
        frame = frame.with_columns(
            pl.when(pl.col(factor).is_not_null() & pl.col(factor).is_finite())
              .then(((pl.col(factor) - pl.col(factor).mean().over('date'))
                     / pl.col(factor).std().over('date')) * direction)
              .otherwise(None).alias(f'_z{i}'))
        zcols.append(f'_z{i}')
    combo = frame.with_columns(
        pl.sum_horizontal(pl.col(zcols)).alias('combo_score'))
    feats = (combo.filter(pl.col('combo_score').is_not_null())
             .select('symbol', 'date',
                     pl.col('combo_score').alias('score')))
    from quant.research.screen import daily_rank_picks, screen_returns
    picks = daily_rank_picks(feats, pl.col('score'), n_per_day=cfg.top_n)
    prices = daily.select('symbol', 'date', 'open', 'adj_factor',
                          'tradestatus', 'isST', 'preclose')
    return screen_returns(picks, prices, cfg, calendar=calendar)


def evaluate_events(config_id: str, events: pl.DataFrame, pool: pl.DataFrame,
                    config: dict) -> dict:
    events_w = _window_frame(events)
    dev = window_summary(events_w, 'dev', pool, 5)
    val = window_summary(events_w, 'validation', pool, 5)
    from quant.research.p2_first_screen import concentration, selection_verdicts, validation_verdicts
    conc = concentration(events_w, 'dev')
    return {'config_id': config_id, 'dev': dev, 'validation': val,
            'concentration_dev': conc,
            'dev_pass': selection_verdicts(dev, conc)['dev_pass'],
            'validation_pass': validation_verdicts(val)['validation_pass']}


def build_report(config: dict, factor_results: dict, screened_in: list[str],
                 combos: dict, survivors: list[str], panel_stats: dict,
                 timings: dict) -> str:
    lines = [
        '# P2 第 4 轮：因子截面普查（预登记）', '',
        f"- 实验ID：{config['experiment_id']}；池 {panel_stats['symbols']} 只 /"
        f" {panel_stats['rows']} 行；前瞻收益覆盖 {panel_stats['fwd_ret_coverage']} 行",
        f"- 协议：持有 5 日；IC=日频 Spearman（≥{50} 只）；分位 Q5-Q1（毛）；尾部=按 dev IC 方向每日 top-3 过全费用管线",
        f"- 筛选（dev）：|IC|≥{config['screening_rule_dev']['ic_threshold']}、年度符号一致、尾部净收益胜池",
        f"- 计时（秒）：{json.dumps({k: round(v, 1) for k, v in timings.items()}, ensure_ascii=False)}",
        '',
        '## 因子普查结果（dev 窗口 2015–2020）', '',
        '| 因子 | dev IC | ICIR | 年度一致 | Q5-Q1(毛)% | 尾部净/池% | 判定 |',
        '|---|---|---|---|---|---|---|',
    ]
    for factor, r in factor_results.items():
        ic = r['dev_ic']
        icir = ic.get('ic_ir')
        tail = r['dev_tail']
        verdict = '**入组**' if r['survey_pass'] else '淘汰'
        lines.append(
            f"| {factor} | {fmt3(ic.get('mean_ic'))} | {fmt3(icir)} "
            f"| {r['consistency_detail']} | {fmt3(r['dev_q5_q1_pct'])} "
            f"| {fmt3(tail['mean_net_pct'])} / {fmt3(tail['pool_mean_pct'])} | {verdict} |")
    lines += ['', f'## 入组因子：{screened_in if screened_in else "无"}', '']
    if not screened_in:
        lines.append('无因子通过筛选：组合规则无输入，第 4 轮以负面结果结束。')
    lines += ['', '## 组合（预登记规则）', '']
    if combos:
        lines.append('| 组合 | 成员 | dev 净/池% | dev 通过 | val 净/池% | val 通过 |')
        lines.append('|---|---|---|---|---|---|')
        for cid, c in combos.items():
            lines.append(
                f"| {cid} | {len(c['members'])} 个 | "
                f"{fmt3(c['dev']['mean_net_pct'])} / {fmt3(c['dev']['pool_mean_pct'])} "
                f"| {'是' if c['dev_pass'] else '否'} | "
                f"{fmt3(c['validation']['mean_net_pct'])} / {fmt3(c['validation']['pool_mean_pct'])} "
                f"| {'是' if c['validation_pass'] else '否'} |")
    lines += [
        '',
        '## 声明', '',
        '- 分位收益为毛口径（无费用）；尾部为全费用历史分段口径。',
        '- moneyflow/daily_basic/cyq/margin 为单源 tushare 兼容代理，未独立复核；',
        '  winner_rate 2018+、margin_buy_ratio 2019+ 为部分覆盖，按覆盖年评估。',
        '- 验证窗在筛选与组合权重冻结后只计算一次。',
        f'- 存活（至多 2 个进 P3）：{survivors if survivors else "无"}',
    ]
    return '\n'.join(lines) + '\n'


def fmt3(value) -> str:
    return '—' if value is None else f'{value:.4f}'


if __name__ == '__main__':
    raise SystemExit(main())
