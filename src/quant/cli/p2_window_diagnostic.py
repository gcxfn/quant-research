"""Exploratory lookback-window diagnostic (NOT a selection round).

Question (user, 2026-09-17): do 4/10-session lookbacks reveal harvestable
long-side structure that the fixed 20-session windows of round 4 missed?

For each (family, window) we report on the dev window only:
- mean daily Spearman IC,
- quintile mean forward returns (5-session forward, gross),
- best_long_edge = (better of Q1/Q5, on the IC-signed side) - pool mean.

Decision yardstick: historical round-trip fee ~0.15pp per 5-session window;
any window whose best_long_edge does not clearly exceed that cannot matter
for this account.  Exploratory output: no survivor claims, no roster changes.
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

from quant.research.factor_survey import forward_returns, ic_series  # noqa: E402
from quant.research.p2_first_screen import (  # noqa: E402
    DEV_END,
    attach_factors,
    build_eligible,
    load_daily,
)
from quant.research.runs import Run, find_repo_root, write_json  # noqa: E402

RET_WINDOWS = [1, 2, 3, 4, 5, 10, 15, 20, 25, 40, 50, 60, 100, 150, 300]
VOL_WINDOWS = [5, 10, 20, 25, 50, 100, 150, 300]
TURN_WINDOWS = [5, 10, 20, 25, 50, 100, 150, 300]
Z_WINDOWS = [5, 10, 20, 25, 50]
RANGE_WINDOWS = [5, 10, 20, 25, 50, 100, 150, 300]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2-round4-factor-survey.json')
    parser.add_argument('--symbols', type=int, default=None)
    args = parser.parse_args()
    config = dict(json.loads(args.config.read_text(encoding='utf-8')))
    config['experiment_id'] = 'exp-20260917-p2-window-diagnostic'
    config['name'] = 'p2-window-diagnostic'
    config['exploratory'] = True
    config['question'] = ('do 4/10-session lookbacks show harvestable long-side '
                          'quintile edges that 20-session windows miss? '
                          'diagnostic only, no selection, no survivor claims')

    import os
    os.chdir(ROOT)
    root = find_repo_root()

    with Run(root, config['name'], config) as run:
        t0 = time.perf_counter()
        daily = attach_factors(load_daily(root, config, symbol_limit=args.symbols),
                               root, config)
        eligible = build_eligible(daily, config)
        fwd = forward_returns(daily, 5)
        frame = (eligible.select('symbol', 'date')
                 .join(daily.select('symbol', 'date', 'adj_close', 'turn', 'high',
                                    'low', 'close', 'ret_1_adj'),
                       on=['symbol', 'date'], how='inner')
                 .join(fwd, on=['symbol', 'date'], how='inner')
                 .sort('symbol', 'date'))
        timings = {'prep_s': time.perf_counter() - t0}

        exprs: list[pl.Expr] = []
        names: list[str] = []


        def _add(expr: pl.Expr, name: str) -> None:
            exprs.append(expr.alias(name))
            names.append(name)
        for w in RET_WINDOWS:
            _add((pl.col('adj_close') / pl.col('adj_close').shift(w)
                  .over('symbol') - 1.0), f'ret_{w}')
        for w in VOL_WINDOWS:
            _add(pl.col('ret_1_adj').rolling_std(w, min_samples=w)
                 .over('symbol'), f'vol_{w}')
        for w in TURN_WINDOWS:
            _add(pl.col('turn').rolling_mean(w, min_samples=w)
                 .over('symbol'), f'turnmean_{w}')
        for w in Z_WINDOWS:
            mean = pl.col('adj_close').rolling_mean(w, min_samples=w).over('symbol')
            std = pl.col('adj_close').rolling_std(w, min_samples=w).over('symbol')
            _add(pl.when(std > 1e-12)
                 .then((pl.col('adj_close') - mean) / std).otherwise(None), f'z_{w}')
        for w in RANGE_WINDOWS:
            _add(((pl.col('high') - pl.col('low')) / pl.col('close'))
                 .rolling_mean(w, min_samples=w).over('symbol'), f'range_{w}')
        t0 = time.perf_counter()
        frame = frame.with_columns(exprs)
        timings['windows_s'] = time.perf_counter() - t0

        dev = frame.filter(pl.col('date') <= DEV_END)
        pool_mean = float(dev['fwd_ret'].mean()) * 100.0
        run.metrics['pool_mean_dev_pct'] = pool_mean
        run.metrics['fee_yardstick_pp'] = 0.15

        t0 = time.perf_counter()
        rows = []
        for name in names:
            sub = dev.filter(pl.col(name).is_not_null()
                             & pl.col(name).is_finite() & pl.col('fwd_ret').is_not_null())
            if not sub.height:
                continue
            ic = ic_series(frame.rename({name: 'f'}), 'f')
            ic_dev = ic.filter(pl.col('date') <= DEV_END)
            mean_ic = float(ic_dev['ic'].mean()) if ic_dev.height else None
            q = (sub.with_columns(
                (((pl.col(name).rank(method='min').over('date') - 1)
                  / pl.len().over('date') * 5 + 1).floor().clip(1, 5))
                .cast(pl.Int32).alias('q'))
                .group_by('q').agg((pl.col('fwd_ret').mean() * 100).alias('m')))
            means = {r['q']: r['m'] for r in q.iter_rows(named=True)}
            if mean_ic is None or not means:
                continue
            good_side = means.get(1) if mean_ic < 0 else means.get(5)
            best_edge = (good_side - pool_mean) if good_side is not None else None
            rows.append({'window': name, 'mean_ic': mean_ic,
                         'q1': means.get(1), 'q3': means.get(3), 'q5': means.get(5),
                         'best_long_edge_pp': best_edge,
                         'best_edge_net_of_fee_pp': (best_edge - 0.15
                                                     if best_edge is not None else None)})
        rows.sort(key=lambda r: -(r['best_long_edge_pp'] or -9))
        timings['scan_s'] = time.perf_counter() - t0
        run.metrics['timings'] = timings
        run.metrics['scan'] = rows
        run.metrics['n_windows'] = len(rows)

        lines = ['# 回看窗口诊断（探索性，非筛选轮）', '',
                 f"- dev 池均值 {pool_mean:.3f}%/5日窗口；费用标尺 0.15pp；"
                 f"窗口数 {len(rows)}",
                 '', '| 窗口 | IC | Q1% | Q3% | Q5% | 多头最优边(pp,毛) | 费后 |', '|---|---|---|---|---|---|---|']
        for r in rows:
            lines.append(
                f"| {r['window']} | {r['mean_ic']:+.4f} | {r['q1']:+.3f} "
                f"| {r['q3']:+.3f} | {r['q5']:+.3f} "
                f"| {r['best_long_edge_pp']:+.3f} | {r['best_edge_net_of_fee_pp']:+.3f} |")
        (run.path / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        for r in rows[:6]:
            print(r)
    return 0 if run.manifest['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
