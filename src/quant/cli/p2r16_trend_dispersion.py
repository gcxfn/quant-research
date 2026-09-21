"""P2-R16 trend + extreme dispersion CLI (exp-20260918-p2r16-trend-dispersion).

Preregistered by ``docs/research/exp-20260918-p2r16-trend-dispersion-prereg.md``
with frozen config ``configs/experiments/p2r16-trend-dispersion.json``.

Usage:
  PYTHONPATH=D:/量化/src .venv/Scripts/python.exe -X utf8 \
      src/quant/cli/p2r16_trend_dispersion.py [--smoke]

``--smoke``  identical pipeline on 2015-01-05..2015-06-30 (correctness +
             timing; numbers labelled SMOKE, gates non-binding).
Default:     full window.  Dev 2015-01-05..2020-12-31 gates (8 configs x 8
gates); val 2021-2024 consumed ONLY when at least one config passes all dev
gates (fixed priority C01..C08, first passer only - one-shot discipline).
Trial accounting: 175 + 8 = 183.  Budget 1800 s / 8 GB (frozen config).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research import p2r16_trend_dispersion as r16  # noqa: E402
from quant.research.p2r13_lowfreq import (  # noqa: E402
    load_ledger, verify_raw_dir)
from quant.research.runs import Run, find_repo_root, sha256  # noqa: E402

CONFIG_PATH = ROOT / 'configs/experiments/p2r16-trend-dispersion.json'
DAILY_1999 = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
DAILY_2015 = ROOT / 'data/processed/baostock-daily-20260917/daily_2015_2024.parquet'
PROCESSED_MANIFEST = 'data/processed/baostock-daily-20260917/manifest.json'
EXPECTED_MANIFEST_SHA = ('2b89bef9ef6f4ae58b69ca43021552db067'
                         'b185551c92a05ef6ac71d2be59bd3')
R8_CONFIG = ROOT / 'configs/experiments/p2r8-daily-risk.json'
INDEX_BATCH = 'data/raw/tushare/index_daily/20260917-r1'
INDEX_CHUNK = 'chunk_000300.SH.csv'
BUDGET_S = 1800.0
CONFIG_PRIORITY = ['C01', 'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08']


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    parser.add_argument('--smoke', action='store_true')
    return parser.parse_args()


def check_budget(start: float, phase: str) -> None:
    elapsed = time.perf_counter() - start
    if elapsed > BUDGET_S:
        raise TimeoutError(f'budget exceeded ({elapsed:.0f}s > '
                           f'{BUDGET_S:.0f}s) at {phase}')


def verify_identities(root: Path) -> dict:
    """Fail-closed data + mechanism identity, before any consumed read."""
    out: dict = {'mechanism': r16.assert_mechanism_identity()}
    out['processed'] = r16.verify_processed_manifest(
        root, PROCESSED_MANIFEST, EXPECTED_MANIFEST_SHA)
    out['daily_2015_2024_sha256'] = sha256(DAILY_2015)
    out['daily_1999_2024_sha256'] = sha256(DAILY_1999)
    n_2015 = pl.scan_parquet(DAILY_2015).select(pl.len()).collect().item()
    n_1999_slice = (pl.scan_parquet(DAILY_1999)
                    .filter(pl.col('date') >= date(2015, 1, 5))
                    .select(pl.len()).collect().item())
    if n_1999_slice != n_2015:
        raise RuntimeError(
            f'identity fail-closed: 1999-file 2015+ slice has {n_1999_slice} '
            f'rows vs pinned file {n_2015}')
    out['row_count_2015_slice_matches_pinned'] = True
    # index identity pinned through the R8 frozen config (same batch)
    r8 = json.loads(R8_CONFIG.read_text(encoding='utf-8'))
    idx = r8['data']['index_daily']
    chunk_path = root / INDEX_BATCH / INDEX_CHUNK
    got_chunk = r16.sha256_file(chunk_path)
    if got_chunk != idx['chunk_000300_sha256']:
        raise RuntimeError(
            f'identity fail-closed: {INDEX_CHUNK} sha256 {got_chunk} != R8 '
            f"pin {idx['chunk_000300_sha256']}")
    got_manifest = r16.sha256_file(root / INDEX_BATCH / 'manifest.json')
    if got_manifest != idx['manifest_sha256']:
        raise RuntimeError(
            f'identity fail-closed: index manifest sha256 {got_manifest} '
            f"!= R8 pin {idx['manifest_sha256']}")
    out['index_chunk_000300_sha256'] = got_chunk
    out['index_manifest_sha256'] = got_manifest
    out['index_pin_source'] = 'configs/experiments/p2r8-daily-risk.json'
    ledger = load_ledger(root)
    out['index_batch_ledger'] = verify_raw_dir(
        root, INDEX_BATCH.removeprefix('data/raw/'), ledger)
    if out['index_batch_ledger']['files_verified'] == 0:
        raise RuntimeError('identity fail-closed: index batch ledger check '
                           'verified 0 files')
    return out


def fmt(value) -> str:
    if value is None:
        return '-'
    return f'{value * 100:.2f}%'


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    os.chdir(ROOT)
    root = find_repo_root()
    t_start = time.perf_counter()
    smoke = bool(args.smoke)
    if smoke:
        dev_start, dev_end = date(2015, 1, 5), date(2015, 6, 30)
    else:
        d0, d1 = config['gates']['dev_window']
        dev_start, dev_end = date.fromisoformat(d0), date.fromisoformat(d1)
    v0, v1 = config['gates']['val_window']
    val_start, val_end = date.fromisoformat(v0), date.fromisoformat(v1)

    with Run(root, 'p2r16-trend-dispersion', config) as run:
        run.manifest['mode'] = 'smoke' if smoke else 'full'
        run.manifest['prereg'] = config['prereg']
        run.manifest['config_frozen_at'] = config['frozen_at']
        run.manifest['config_file_sha256'] = sha256(args.config)
        run.manifest['deviations_registered_before_run'] = r16.DEVIATIONS
        run.manifest['trial_count'] = {
            'prior_cumulative': config['trials_cumulative_before'],
            'this_round_configs': config['trials_counted_this_round'],
            'cumulative_after': config['trials_cumulative_after']}
        run.manifest['window_declarations'] = {
            'dev': '2015-01-05..2020-12-31, 7th reuse, elimination use only',
            'val': '2021-01..2024-12 one-shot; 5th declared consumption of '
                   'this window (C08, R11 not reached, R12 if reached, R13 '
                   'not consumed, this round); consumed ONLY for the first '
                   'dev-passer in the frozen priority order',
            'freeze': 'no rows on/after 2025-01-01; the 2024-12-31 signal is '
                      'dropped (its execution would land in 2025)'}

        # ---------------- identity (fail-closed) -------------------------
        t0 = time.perf_counter()
        run.manifest['identity_checks'] = verify_identities(root)
        run.metrics['timings'] = {'identity_s': time.perf_counter() - t0}
        check_budget(t_start, 'identity verification')

        # ---------------- calendar / signals / index ---------------------
        t0 = time.perf_counter()
        cal = r16.market_calendar(DAILY_1999)
        calendar_full = cal['date'].to_list()
        if smoke:
            # run calendar = contiguous reindex of the smoke slice; the
            # T200 anchor still runs on the FULL calendar below
            cal_run = (cal.filter(pl.col('date') <= dev_end)
                       .with_columns(pl.int_range(pl.len())
                                     .cast(pl.Int64)
                                     .alias('mkt_idx')))
            calendar = cal_run['date'].to_list()
        else:
            cal_run = cal
            calendar = calendar_full
        idx_of = {d: i for i, d in enumerate(calendar)}
        signals_all = (r16.month_end_sessions(cal)
                       .filter((pl.col('s') >= dev_start)
                               & (pl.col('s') <= val_end)))
        if smoke:
            signals_all = signals_all.filter(pl.col('s') <= dev_end)
        # keep only signals whose EXECUTION session exists inside the
        # (freeze-respecting) calendar; the 2024-12-31 signal has none
        keep, dropped = [], []
        for s in signals_all['s'].to_list():
            i = idx_of.get(s)
            if i is not None and i + 1 < len(calendar):
                keep.append(s)
            else:
                dropped.append(s)
        signal_days = keep
        run.metrics['signals'] = {
            'n_signals': len(signal_days),
            'first': str(signal_days[0]), 'last': str(signal_days[-1]),
            'dropped_execution_beyond_calendar': [str(d) for d in dropped]}
        index_close = r16.load_index_close(
            root / INDEX_BATCH / INDEX_CHUNK).filter(
            pl.col('trade_date') <= r16.FREEZE_LAST)
        anchor = r16.t200_behavioral_anchor_check(index_close,
                                                  calendar_full)
        run.metrics['t200_behavioral_anchor'] = anchor
        exposures_by_path = {
            'T200-40': r16.t200_month_end_exposures(
                index_close, calendar_full,
                [d for d in signal_days]),
            'FIX75': r16.fix75_exposures(signal_days),
        }
        fallback = r16.t200_fallback_signal_dates(
            index_close, calendar_full, signal_days)
        run.metrics['t200_fallback_signals'] = {
            'n': len(fallback), 'dates': [str(d) for d in fallback],
            'rule': 'registered fallback: SMA200 unavailable -> risk-off '
                    'e_low (R8 sma_trend_state docstring)'}
        run.metrics['timings']['calendar_signals_s'] = (
            time.perf_counter() - t0)
        check_budget(t_start, 'calendar/signals/index')

        # ---------------- pools + price bank ------------------------------
        t0 = time.perf_counter()
        hist = r16.build_history_r16(DAILY_1999, cal_run)
        pool_frame = r16.signal_pools(hist, signals_all)
        pools_at = r16.pools_by_signal(pool_frame)
        symbols = sorted({s for p in pools_at.values()
                          for s in p['ranked']})
        bank = r16.PriceBank(hist, calendar, symbols)
        run.metrics['pool_stats'] = {
            'n_symbols_ever_in_pool': len(symbols),
            'mean_pool_size': (sum(p['n'] for p in pools_at.values())
                               / len(pools_at)),
            'min_pool_size': min(p['n'] for p in pools_at.values()),
            'mean_q5_share': (sum(sum(1 for v in p['q5'].values() if v)
                                  for p in pools_at.values())
                              / sum(p['n'] for p in pools_at.values()))}
        hist = None
        run.metrics['timings']['pools_bank_s'] = (
            time.perf_counter() - t0)
        check_budget(t_start, 'pools + price bank')

        def buffered(K: int, q5_on: bool):
            return lambda prev, ranked, q5, rng: r16.buffer_membership(
                prev, ranked, q5, K, q5_on)

        def random_sel(K: int):
            return lambda prev, ranked, q5, rng: r16.random_membership(
                prev, ranked, q5, rng, K)

        def full_reb(K: int, q5_on: bool):
            return lambda prev, ranked, q5, rng: \
                r16.full_rebalance_membership(prev, ranked, q5, K, q5_on)

        # ---------------- 8 strategy configs ------------------------------
        t0 = time.perf_counter()
        results: dict[str, r16.R16Result] = {}
        for cid in CONFIG_PRIORITY:
            spec = config['configs'][cid]
            K = int(spec['K'])
            path = spec['path']
            q5_on = spec['filter'] == 'on'
            results[cid] = r16.simulate_r16(
                cid, bank, calendar, dev_start, signal_days, pools_at,
                exposures_by_path[path], K=K,
                membership_fn=buffered(K, q5_on))
            run.metrics['timings'][f'sim_{cid}_s'] = round(
                time.perf_counter() - t0, 2)
            check_budget(t_start, f'sim {cid}')

        # ---------------- B1(m): mechanism-matched, 2 fee variants --------
        t0 = time.perf_counter()
        b1_results: dict[tuple[str, str], r16.R16Result] = {}
        for path in ('T200-40', 'FIX75'):
            for fee_name, bands in (
                    ('rate_only', r16.B1_FEE_SCHEDULE_RATE_ONLY),
                    ('literal_min5', r16.STOCK_FEE_SCHEDULE)):
                b1_results[(path, fee_name)] = r16.simulate_r16(
                    f'B1-{path}-{fee_name}', bank, calendar, dev_start,
                    signal_days, pools_at, exposures_by_path[path], K=0,
                    fractional=True, fee_bands=bands)
        run.metrics['timings']['b1_s'] = round(time.perf_counter() - t0, 2)
        check_budget(t_start, 'B1(m)')

        # ---------------- B3prime per path (seeds 17-36) ------------------
        t0 = time.perf_counter()
        b3_results: dict[tuple[str, int], r16.R16Result] = {}
        for path in ('T200-40', 'FIX75'):
            for seed in r16.B3_SEEDS:
                b3_results[(path, seed)] = r16.simulate_r16(
                    f'B3-{path}-s{seed}', bank, calendar, dev_start,
                    signal_days, pools_at, exposures_by_path[path], K=20,
                    membership_fn=random_sel(20), seed=seed)
            run.metrics['timings'][f'b3_{path}_s'] = round(
                time.perf_counter() - t0, 2)
            check_budget(t_start, f'B3prime {path}')

        # ---------------- H-47 evidence arm: full-rebalance baselines ----
        t0 = time.perf_counter()
        baseline_results: dict[tuple[int, str], r16.R16Result] = {}
        for K in (20, 30):
            for q5_state in ('on', 'off'):
                baseline_results[(K, q5_state)] = r16.simulate_r16(
                    f'BASE-FULLREB-K{K}-Q5{q5_state}', bank, calendar,
                    dev_start, signal_days, pools_at,
                    exposures_by_path['FIX75'], K=K,
                    membership_fn=full_reb(K, q5_state == 'on'))
        run.metrics['timings']['baselines_s'] = round(
            time.perf_counter() - t0, 2)

        # ---------------- metrics + gates ---------------------------------
        t0 = time.perf_counter()

        def b3_dev_mean(path: str) -> float:
            cagrs = []
            for seed in r16.B3_SEEDS:
                rr = b3_results[(path, seed)]
                sd, sv = r16.slice_curve(rr.sessions, rr.equity,
                                         dev_start, dev_end)
                cagrs.append(r16.cagr(sv[0], sv[-1], sd[0], sd[-1]))
            return sum(cagrs) / len(cagrs)

        metrics: dict[str, dict] = {}
        gates: dict[str, dict] = {}
        b3_means = {}
        for path in ('T200-40', 'FIX75'):
            b3_means[path] = b3_dev_mean(path)
        run.metrics['B3prime_dev_mean_net_cagr'] = b3_means
        run.metrics['B3prime_per_seed_dev_net_cagr'] = {
            f'{path}-s{seed}': _dev_cagr(b3_results[(path, seed)],
                                         dev_start, dev_end)
            for path in ('T200-40', 'FIX75') for seed in r16.B3_SEEDS}
        for cid in CONFIG_PRIORITY:
            spec = config['configs'][cid]
            path = spec['path']
            b1_primary = b1_results[(path, 'rate_only')]
            m = r16.segment_metrics(results[cid], dev_start, dev_end,
                                    b1_primary)
            m['config'] = spec
            m['b1m_variant'] = 'rate_only (deviation 2 primary)'
            metrics[cid] = m
            gates[cid] = {'dev': r16.evaluate_dev_gates(m, b3_means[path])}
            gates[cid]['dev']['smoke_non_binding'] = smoke
        run.metrics['configs'] = metrics
        run.metrics['gates'] = gates

        # B1 metrics (both fee variants, both paths)
        run.metrics['benchmarks'] = {
            f'B1m[{path}][{fee_name}]': r16.segment_metrics(
                b1_results[(path, fee_name)], dev_start, dev_end, None,
                fractional=True)
            for path in ('T200-40', 'FIX75')
            for fee_name in ('rate_only', 'literal_min5')}

        # H-47 evidence: buffer band vs full-rebaseline turnover
        h47 = {}
        for K in (20, 30):
            for q5_state in ('on', 'off'):
                cid = next(c for c in CONFIG_PRIORITY
                           if config['configs'][c]['K'] == K
                           and config['configs'][c]['filter'] == q5_state)
                buf = metrics[cid]['max_membership_one_side_turnover']
                base = r16.segment_metrics(
                    baseline_results[(K, q5_state)], dev_start, dev_end,
                    None)['max_membership_one_side_turnover']
                h47[f'K{K}_Q5{q5_state}'] = {
                    'buffer_config': cid,
                    'buffer_max_membership_turnover': buf,
                    'full_rebalance_max_membership_turnover': base,
                    'reduction': (buf - base) if (buf is not None
                                                  and base is not None
                                                  and base > 0) else None,
                    'reduction_share': ((buf - base) / base
                                        if (buf is not None
                                            and base not in (None, 0))
                                        else None)}
        run.metrics['h47_buffer_turnover_effect'] = h47
        run.metrics['timings']['metrics_gates_s'] = round(
            time.perf_counter() - t0, 2)

        # ---------------- val: first dev-passer in priority (one-shot) ----
        dev_passers = [cid for cid in CONFIG_PRIORITY
                       if gates[cid]['dev']['dev_pass']]
        run.metrics['dev_pass_configs'] = dev_passers
        advanced = None
        if dev_passers and not smoke:
            advanced = dev_passers[0]
            spec = config['configs'][advanced]
            m_val = r16.segment_metrics(
                results[advanced], val_start, val_end,
                b1_results[(spec['path'], 'rate_only')])
            metrics[advanced]['val'] = m_val
            gates[advanced]['val'] = r16.evaluate_val_gates(m_val)
            gates[advanced]['val']['consumption_note'] = \
                config['gates']['val_consumption_note']
        run.metrics['advanced_to_validation'] = advanced
        run.metrics['val_pass'] = bool(
            advanced and gates[advanced].get('val', {}).get('val_pass'))
        run.metrics['trial_count_cumulative'] = \
            config['trials_cumulative_after']

        # ---------------- mechanism获证 double-valued condition -----------
        mech_flags = {cid: gates[cid]['dev']['mechanism_only_gate2_fail']
                      for cid in CONFIG_PRIORITY}
        run.metrics['mechanism_only_gate2_fail'] = mech_flags

        # ---------------- evidence files ----------------------------------
        t0 = time.perf_counter()
        curve_rows = []
        for cid, rr in results.items():
            for d, v in zip(rr.sessions, rr.equity):
                curve_rows.append({'config_id': cid, 'session': d,
                                   'equity_net': v})
        for (path, fee_name), rr in b1_results.items():
            for d, v in zip(rr.sessions, rr.equity):
                curve_rows.append({'config_id': f'B1-{path}-{fee_name}',
                                   'session': d, 'equity_net': v})
        for (path, seed), rr in b3_results.items():
            for d, v in zip(rr.sessions, rr.equity):
                curve_rows.append({'config_id': f'B3-{path}-s{seed}',
                                   'session': d, 'equity_net': v})
        for key, rr in baseline_results.items():
            for d, v in zip(rr.sessions, rr.equity):
                curve_rows.append({'config_id': f'BASE-FULLREB-K{key[0]}'
                                                 f'-Q5{key[1]}',
                                   'session': d, 'equity_net': v})
        pl.DataFrame(curve_rows).write_parquet(
            run.path / 'equity_curves.parquet')

        trade_rows = []
        for cid, rr in results.items():
            for tr in rr.trades:
                trade_rows.append({'config_id': cid, **tr})
        for (path, seed), rr in b3_results.items():
            for tr in rr.trades:
                trade_rows.append({'config_id': f'B3-{path}-s{seed}', **tr})
        pl.DataFrame(trade_rows).write_parquet(run.path / 'trades.parquet')

        leg_rows = []
        for cid, rr in results.items():
            for row in rr.leg_log:
                leg_rows.append({'config_id': cid, **row})
        pl.DataFrame(leg_rows).write_parquet(run.path / 'leg_log.parquet')

        mem_rows = []
        for cid, rr in results.items():
            for e in rr.membership_events:
                mem_rows.append({'config_id': cid, **e})
        pl.DataFrame(mem_rows).write_parquet(
            run.path / 'membership_events.parquet')
        run.metrics['timings']['evidence_write_s'] = round(
            time.perf_counter() - t0, 2)
        run.metrics['timings']['total_s'] = round(
            time.perf_counter() - t_start, 2)
        run.metrics = r16.jsonable(run.metrics)

        (run.path / 'report.md').write_text(
            render_report(config, run.metrics, smoke), encoding='utf-8')
        check_budget(t_start, 'total')
        print(f"dev_pass: {dev_passers}; advanced: {advanced}; "
              f"val_pass: {run.metrics['val_pass']}; run={run.path}")
    return 0


def _dev_cagr(rr: r16.R16Result, start: date, end: date) -> float:
    sd, sv = r16.slice_curve(rr.sessions, rr.equity, start, end)
    return r16.cagr(sv[0], sv[-1], sd[0], sd[-1])


def render_report(config: dict, metrics: dict, smoke: bool) -> str:
    tag = ' - SMOKE（判据不生效）' if smoke else ''
    lines = [f'# P2-R16 趋势+极度分散（预登记策略级回放）{tag}', '',
             f"- experiment_id: {config['experiment_id']}",
             '- dev 2015-01-05..2020-12-31（第 7 次重用，只作淘汰）；'
             'T200-40 = R8 机制逐字 import（000300 指数口径，锚定断言通过）；'
             'FIX75 = 0.75；费用 = 佣金万1 最低5元 + 印花分段；200k 资金；整手',
             '', '## 锚定与身份（先于任何判据消费）', '']
    a = metrics.get('t200_behavioral_anchor', {})
    lines.append(f"- T200 行为锚（R8 已发表 C02 日频状态统计 2016-2020）: "
                 f"all_match={a.get('all_match')}")
    fb = metrics.get('t200_fallback_signals', {})
    lines.append(f"- SMA200 不可用而按注册回退（risk-off）的月末信号数: "
                 f"{fb.get('n')}（{', '.join(fb.get('dates', []))}）")
    ps = metrics.get('pool_stats', {})
    lines.append(f"- 池: 平均 {ps.get('mean_pool_size'):.0f} 只/月，最小 "
                 f"{ps.get('min_pool_size')}，Q5 命中率均值 "
                 f"{ps.get('mean_q5_share'):.4f}")
    lines += ['', '## 基准（dev）', '']
    for key, m in metrics.get('benchmarks', {}).items():
        lines.append(f"- {key}: 净年化 {fmt(m.get('net_cagr'))}，回撤 "
                     f"{fmt(m.get('max_drawdown'))}，换手max "
                     f"{fmt(m.get('max_one_side_turnover'))}")
    for path, mean in metrics.get('B3prime_dev_mean_net_cagr', {}).items():
        lines.append(f"- B3'（随机K=20, 20种子）[{path}] dev 净年化均值 "
                     f"{fmt(mean)}")
    lines += ['', '## 8 配置 x 8 门（dev，探索性）', '',
              '| 配置 | K/路径/过滤 | 净% | B1(m)净% | 超额pp | 优势年 | 回撤% | '
              'B1回撤% | 换手max | 权重max | 成交率 | 过x/8 | 失败门 |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for cid, m in metrics.get('configs', {}).items():
        g = metrics['gates'][cid]['dev']
        spec = m['config']
        failed = ','.join(x.split('_')[0]
                          for x in g['failed_gates']) or '-'
        lines.append(
            f"| {cid} | {spec['K']}/{spec['path']}/{spec['filter']} "
            f"| {fmt(m['net_cagr'])} | {fmt(m.get('b1m_net_cagr'))} "
            f"| {fmt(m.get('excess_vs_b1m'))} | {g['advantage_years']}/6 "
            f"| {fmt(m['max_drawdown'])} "
            f"| {fmt(m.get('b1m_max_drawdown'))} "
            f"| {fmt(m.get('max_one_side_turnover'))} "
            f"| {fmt(m.get('max_single_name_weight'))} "
            f"| {fmt(m.get('execution_rate'))} "
            f"| {'PASS' if g['dev_pass'] else 'fail'} | {failed} |")
    lines += ['', '## H-47 缓冲带换手效应（描述性，非判据）', '']
    for key, e in metrics.get('h47_buffer_turnover_effect', {}).items():
        red = e.get('reduction_share')
        lines.append(f"- {key}: 缓冲带成员换手max "
                     f"{fmt(e['buffer_max_membership_turnover'])} vs 全重排 "
                     f"{fmt(e['full_rebalance_max_membership_turnover'])}"
                     f"（降幅 {fmt(red) if red is not None else '-'}）")
    if metrics.get('advanced_to_validation'):
        cid = metrics['advanced_to_validation']
        m = metrics['configs'][cid]['val']
        g = metrics['gates'][cid]['val']
        lines += ['', f'## 存活者 {cid} → validation（2021-2024 一次性）', '',
                  f"- 净年化 {fmt(m['net_cagr'])}，B1(m) "
                  f"{fmt(m.get('b1m_net_cagr'))}，超额 "
                  f"{fmt(m.get('excess_vs_b1m'))}，回撤 "
                  f"{fmt(m['max_drawdown'])}（B1 "
                  f"{fmt(m.get('b1m_max_drawdown'))}），优势年 "
                  f"{g['advantage_years']}/4，"
                  f"gate={'PASS' if g['val_pass'] else 'fail'} "
                  f"({','.join(x.split('_')[0] for x in g['failed_gates']) or '-'})"]
    mech = metrics.get('mechanism_only_gate2_fail', {})
    if any(mech.values()):
        lines += ['', '## 机制获证条款（双值结论）', '',
                  f"- 仅败于判据 2 的配置: {[c for c, v in mech.items() if v]}"]
    lines += ['', '## 判定', '',
              f"- dev 过门: {metrics.get('dev_pass_configs') or '无'}",
              f"- 进入 validation: {metrics.get('advanced_to_validation')}",
              f"- 试验累计: {metrics.get('trial_count_cumulative')}",
              '- 无盈利/实盘声称；全部结论限于本预登记判据。']
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    raise SystemExit(main())
