"""P2-R6 ETF rotation screen CLI (exp-20260917-p2r6-etf-rotation).

Usage:
  python src/quant/cli/p2r6_etf_rotation.py \
      [--config configs/experiments/p2r6-etf-rotation.json] [--smoke]

``--smoke`` restricts the replay to the first dev year (2016) and configs
C01/C04 for correctness and timing checks; gates are computed but marked
non-binding.  The full run evaluates all 12 configs on dev, then the frozen
gate cascade (dev -> validation -> test, at most one survivor; the test slice
comes from the same single continuous run and is only reported for the
validation survivor).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))

from quant.research import etf_rotation as er  # noqa: E402
from quant.research.etf_rotation import (  # noqa: E402
    ETF_FEE_BAND,
    GROSS_FEE_BAND,
    CodeDataBank,
    build_calendar,
    cagr,
    concentration,
    evaluate_dev_gate,
    evaluate_test,
    evaluate_val_gate,
    group_pools,
    max_drawdown,
    monthly_top_decile,
    rank_pool,
    rebalance_days,
    simulate,
    simulate_b1,
    simulate_b2,
    slice_curve,
    turnover_by_year,
    year_returns,
)
from quant.research.runs import Run, find_repo_root, write_json  # noqa: E402

WINDOWS = {'W3': (20, 60, 120), 'W2L': (60, 120), 'W2S': (20, 60)}
B3_SEEDS = list(range(17, 37))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2r6-etf-rotation.json')
    parser.add_argument('--smoke', action='store_true',
                        help='1 dev year (2016) x C01/C04 correctness smoke')
    return parser.parse_args()


def effective_config(base: dict, smoke: bool) -> dict:
    config = json.loads(json.dumps(base))
    if smoke:
        config['smoke'] = True
        config['segments']['dev'] = {'start': '2016-01-01', 'end': '2016-12-31'}
        config['segments']['validation'] = None
        config['segments']['test'] = None
        config['smoke_configs'] = ['C01', 'C04']
        config['name'] = base['name'] + '-smoke'
    return config


def segment_bounds(config: dict) -> dict[str, tuple[date, date]]:
    out = {}
    for seg in ('dev', 'validation', 'test'):
        raw = config['segments'].get(seg)
        if raw:
            out[seg] = (date.fromisoformat(raw['start']),
                        date.fromisoformat(raw['end']))
    return out


def budget_exceeded(deadline: float, limits: dict) -> None:
    if time.perf_counter() > deadline:
        raise RuntimeError(
            f"runtime budget exceeded (max_runtime_s={limits['max_runtime_s']}); "
            'stopping with partial progress recorded in metrics.json')


def main() -> int:
    args = parse_args()
    base = json.loads(args.config.read_text(encoding='utf-8'))
    config = effective_config(base, args.smoke)
    os.chdir(ROOT)
    root = find_repo_root()

    limits = config.get('limits', {'max_runtime_s': 1800, 'max_ram_gb': 11})
    deadline = time.perf_counter() + float(limits['max_runtime_s'])
    t_all = time.perf_counter()
    segs = segment_bounds(config)
    dev_start = segs['dev'][0]
    smoke_end = segs['dev'][1] if args.smoke else None
    config_ids = config.get('smoke_configs') or list(config['configs_grid']['twelve'])
    smoke = bool(args.smoke)

    with Run(root, config['name'], config) as run:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        loaded = er.load_frames(root, config)
        feat: pl.DataFrame = loaded['feat']
        calendar = build_calendar(feat)
        if smoke_end is not None:
            calendar = [d for d in calendar if d <= smoke_end]
            feat = feat.filter(pl.col('trade_date') <= smoke_end)
        timings['load_s'] = round(time.perf_counter() - t0, 2)
        run.manifest['inputs'] = [
            {'path': config['data']['fund_daily']['batch'],
             'manifest_sha256': config['data']['fund_daily']['manifest_sha256'],
             **loaded['stats']},
            {'path': config['data']['fund_adj']['batch'],
             'manifest_sha256': config['data']['fund_adj']['manifest_sha256']},
            {'path': config['data']['fund_basic']['batch'],
             'file_sha256': config['data']['fund_basic']['sha256']},
        ]
        run.metrics['load_stats'] = loaded['stats']
        run.metrics['timings'] = timings

        t0 = time.perf_counter()
        pools = group_pools(feat)
        bank = CodeDataBank(feat, calendar)
        timings['pools_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        signal_days: dict[str, list[date]] = {
            freq: rebalance_days(calendar, freq, dev_start)
            for freq in config['configs_grid']['freqs']}

        pool_sizes: dict[str, dict] = {}
        for freq, days in signal_days.items():
            by_year: dict[int, list[int]] = {}
            for d in days:
                by_year.setdefault(d.year, []).append(len(pools.get(d, [])))
            pool_sizes[freq] = {
                str(y): {'min': min(v), 'mean': round(sum(v) / len(v), 1),
                         'max': max(v), 'sizes': v}
                for y, v in sorted(by_year.items())}
        run.metrics['pool_sizes'] = pool_sizes

        ranked_cache: dict[tuple, dict[date, list[str]]] = {}

        def ranked_for(window_key: str, gate: bool, freq: str,
                       days: list[date]) -> dict[date, list[str]]:
            key = (window_key, gate, freq)  # freq matters: signal days differ
            if key not in ranked_cache:
                window = WINDOWS[window_key]
                out = {}
                for d in days:
                    ranked = rank_pool(pools.get(d, []), window)
                    if gate:
                        ranked = [r for r in ranked if r.gate_ok]
                    out[d] = [r.code for r in ranked]
                ranked_cache[key] = out
            return ranked_cache[key]

        # ---------------- benchmarks ----------------
        t0 = time.perf_counter()
        b1: dict[str, er.SimResult] = {
            freq: simulate_b1(pools, bank, calendar, dev_start, days,
                              total=200_000.0, fees=ETF_FEE_BAND)
            for freq, days in signal_days.items()}
        b2_code = '510300.SH'
        b2 = {seg: simulate_b2(b2_code, bank, calendar, s, e,
                               total=200_000.0, fees=ETF_FEE_BAND)
              for seg, (s, e) in segs.items()}
        dv_end = segs['validation'][1] if 'validation' in segs else segs['dev'][1]
        b2_dev_val = simulate_b2(b2_code, bank, calendar, segs['dev'][0], dv_end,
                                 total=200_000.0, fees=ETF_FEE_BAND)
        b3: dict[tuple[str, int], er.SimResult] = {}
        for freq, days in signal_days.items():
            for seed in B3_SEEDS:
                rng = random.Random(seed)

                def selector(t: date) -> list[str]:
                    codes = [r.code for r in pools.get(t, [])]
                    rng.shuffle(codes)
                    return codes

                b3[(freq, seed)] = simulate(
                    f'B3-{freq}-s{seed}', bank, calendar, dev_start, days,
                    selector, budget=200_000.0 / 3, fees=ETF_FEE_BAND)
        timings['benchmarks_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------------- 12 configs: continuous net+gross paths ----------------
        curves_rows: list[dict] = []
        sim_results: dict[str, dict] = {}
        for cid, spec in config['configs_grid']['twelve'].items():
            if cid not in config_ids:
                continue
            budget_exceeded(deadline, limits)
            t0 = time.perf_counter()
            days = signal_days[spec['freq']]
            ranked = ranked_for(spec['W'], spec['gate'], spec['freq'], days)
            net = simulate(cid, bank, calendar, dev_start, days,
                           lambda t, _r=ranked: _r.get(t, []),
                           budget=200_000.0 / 3, fees=ETF_FEE_BAND)
            gross = simulate(cid + '-gross', bank, calendar, dev_start, days,
                             lambda t, _r=ranked: _r.get(t, []),
                             budget=200_000.0 / 3, fees=GROSS_FEE_BAND)
            parity = ([(t['session'], t['code'], t['side'], t['kind'])
                       for t in net.trades]
                      == [(t['session'], t['code'], t['side'], t['kind'])
                          for t in gross.trades])
            if not parity:
                raise RuntimeError(f'{cid}: net/gross trade parity violated')
            sim_results[cid] = {'spec': spec, 'net': net, 'gross': gross}
            timings[f'sim_{cid}_s'] = round(time.perf_counter() - t0, 2)
            run.metrics['timings'] = timings

        for cid, sr in sim_results.items():
            for d, vn, vg in zip(sr['net'].sessions, sr['net'].equity,
                                 sr['gross'].equity):
                curves_rows.append({'config_id': cid, 'session': d,
                                    'equity_net': vn, 'equity_gross': vg})

        # ---------------- metrics per config ----------------
        metrics: dict[str, dict] = {}

        def years_of(seg: str) -> list[int]:
            if seg not in segs:
                return []
            s, e = segs[seg]
            return list(range(s.year, e.year + 1))

        def build_metrics(cid: str) -> dict:
            spec = sim_results[cid]['spec']
            net: er.SimResult = sim_results[cid]['net']
            gross: er.SimResult = sim_results[cid]['gross']
            b1r = b1[spec['freq']]
            out: dict = {'freq': spec['freq'], 'W': spec['W'], 'gate': spec['gate'],
                         'max_negative_cash': net.max_negative_cash,
                         'n_trades': len(net.trades),
                         'exec_stats': net.exec_stats.as_dict()}
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd_n, sv_n = slice_curve(net.sessions, net.equity, s, e)
                sd_g, sv_g = slice_curve(gross.sessions, gross.equity, s, e)
                sd_b, sv_b = slice_curve(b1r.sessions, b1r.equity, s, e)
                mdd_n = max_drawdown(sd_n, sv_n)
                seg_m = {
                    'net_cagr': cagr(sv_n[0], sv_n[-1], sd_n[0], sd_n[-1]),
                    'gross_cagr': cagr(sv_g[0], sv_g[-1], sd_g[0], sd_g[-1]),
                    'net_total_return': sv_n[-1] / sv_n[0] - 1.0,
                    'gross_total_return': sv_g[-1] / sv_g[0] - 1.0,
                    'b1_net_cagr': cagr(sv_b[0], sv_b[-1], sd_b[0], sd_b[-1]),
                    'max_drawdown': mdd_n['max_drawdown'],
                    'mdd_window': mdd_n,
                    'b1_max_drawdown': max_drawdown(sd_b, sv_b)['max_drawdown'],
                }
                seg_m['excess_vs_b1'] = (seg_m['net_cagr'] - seg_m['b1_net_cagr']
                                         if seg_m['net_cagr'] is not None else None)
                # execution rate is accumulated over the whole continuous run
                # (2016-2024); the gate-8 quantity is this whole-run rate
                seg_m['execution_rate'] = out['exec_stats']['execution_rate']
                strat_years = year_returns(sd_n, sv_n)
                b1_years = year_returns(sd_b, sv_b)
                seg_m['net_return_by_year'] = {str(y): strat_years.get(y)
                                               for y in years_of(seg)}
                seg_m['excess_by_year'] = {
                    str(y): (strat_years[y] - b1_years[y]
                             if y in strat_years and y in b1_years else None)
                    for y in years_of(seg)}
                gross_years = year_returns(sd_n, sv_g)
                seg_m['gross_return_by_year'] = {str(y): gross_years.get(y)
                                                 for y in years_of(seg)}
                turnover = turnover_by_year(net)
                seg_m['turnover_by_year'] = {str(y): turnover.get(y)
                                             for y in years_of(seg)}
                seg_m['max_one_side_turnover'] = max(
                    (turnover[y]['one_side_turnover'] for y in years_of(seg)
                     if turnover.get(y)), default=None)
                seg_m['concentration'] = concentration(
                    net.positions, net.final_open, bank, calendar, s, e)
                seg_m['monthly_top_decile'] = monthly_top_decile(sd_n, sv_n)
                seg_m['forced_delist'] = {
                    'count': sum(1 for p in net.positions
                                 if p['exit_kind'] == 'forced_delist_close'
                                 and s <= p['exit_date'] <= e),
                    'pnl_sum': sum(p['pnl'] for p in net.positions
                                   if p['exit_kind'] == 'forced_delist_close'
                                   and s <= p['exit_date'] <= e)}
                out[seg] = seg_m
            return out

        for cid in sim_results:
            budget_exceeded(deadline, limits)
            metrics[cid] = build_metrics(cid)
            run.metrics['configs'] = metrics

        # ---------------- benchmark metrics ----------------
        def b1_metrics(freq: str) -> dict:
            r = b1[freq]
            acc = r.extra.get('turnover_acc', {})
            out_m: dict = {}
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd, sv = slice_curve(r.sessions, r.equity, s, e)
                mean_eq = sum(sv) / len(sv) if sv else None
                buy = sum(acc.get(y, {}).get('buy_notional', 0.0)
                          for y in range(s.year, e.year + 1))
                out_m[seg] = {
                    'net_cagr': cagr(sv[0], sv[-1], sd[0], sd[-1]),
                    'net_total_return': sv[-1] / sv[0] - 1.0,
                    'max_drawdown': max_drawdown(sd, sv)['max_drawdown'],
                    'buy_notional_total': buy,
                    'one_side_turnover': (buy / mean_eq) if mean_eq else None,
                }
            return out_m

        b1_m = {freq: b1_metrics(freq) for freq in b1}
        b3_dev_means: dict[str, float] = {}
        for freq in signal_days:
            cagrs = []
            for seed in B3_SEEDS:
                sd, sv = slice_curve(b3[(freq, seed)].sessions,
                                     b3[(freq, seed)].equity, *segs['dev'])
                cagrs.append(cagr(sv[0], sv[-1], sd[0], sd[-1]))
            mean = sum(cagrs) / len(cagrs)
            b3_dev_means[freq] = mean
            b3_dev = {
                'n_seeds': len(B3_SEEDS), 'mean_net_cagr': mean,
                'min': min(cagrs), 'max': max(cagrs),
                'std': ((sum((x - mean) ** 2 for x in cagrs) / (len(cagrs) - 1))
                        ** 0.5 if len(cagrs) > 1 else None),
                'per_seed': {str(s): c for s, c in zip(B3_SEEDS, cagrs)}}
            run.metrics[f'B3_dev_{freq}'] = b3_dev
        run.metrics['benchmarks'] = {
            'B1': b1_m,
            'B2': {seg: {'net_total_return': b2[seg]['net_total_return'],
                         'gross_total_return': b2[seg]['gross_total_return'],
                         'net_cagr': cagr(200_000.0,
                                          200_000.0 * (1 + b2[seg]['net_total_return']),
                                          b2[seg]['entry_date'], b2[seg]['exit_date']),
                         'entry': b2[seg]['entry_date'].isoformat(),
                         'exit': b2[seg]['exit_date'].isoformat(),
                         'fees': {'buy': b2[seg]['buy_fee'],
                                  'sell': b2[seg]['sell_fee']}}
                   for seg in b2},
            'B2_dev_plus_val': {
                'net_total_return': b2_dev_val['net_total_return'],
                'entry': b2_dev_val['entry_date'].isoformat(),
                'exit': b2_dev_val['exit_date'].isoformat()},
            'B4_cash': 0.0,
        }

        # ---------------- gates ----------------
        gates: dict[str, dict] = {}
        for cid, m in metrics.items():
            budget_exceeded(deadline, limits)
            g = evaluate_dev_gate(
                m, b1_m[m['freq']]['dev'], b3_dev_means[m['freq']],
                freq=m['freq'])
            g['smoke_non_binding'] = smoke
            gates[cid] = {'dev': g}
        dev_pass = sorted(
            [(cid, gates[cid]['dev']['dev_excess_vs_b1'])
             for cid in gates if gates[cid]['dev']['dev_pass']],
            key=lambda kv: -kv[1])
        advanced = None
        if dev_pass and not smoke:
            advanced = dev_pass[0][0]
            m = metrics[advanced]
            gates[advanced]['validation'] = evaluate_val_gate(
                m, b1_m[m['freq']].get('validation') or {'net_cagr': None})
            if gates[advanced]['validation']['val_pass'] and 'test' in segs:
                gates[advanced]['test'] = evaluate_test(
                    m, b1_m[m['freq']]['test'])
        for cid in gates:
            if (not smoke and gates[cid]['dev']['dev_pass'] and cid != advanced):
                gates[cid]['status'] = 'dev-pass-not-advanced'
        run.metrics['gates'] = gates
        run.metrics['dev_pass_configs'] = [cid for cid, _ in dev_pass]
        run.metrics['advanced_to_validation'] = advanced
        survivors = []
        if advanced and gates[advanced].get('test', {}).get('test_pass'):
            survivors = [advanced]
        run.metrics['p3_candidates'] = survivors

        if 'validation' in segs and advanced:
            dv = ((1 + metrics[advanced]['dev']['net_total_return'])
                  * (1 + metrics[advanced]['validation']['net_total_return']) - 1)
            b2v = run.metrics['benchmarks']['B2_dev_plus_val']['net_total_return']
            run.metrics['advanced_dev_plus_val_net_total'] = dv
            run.metrics['advanced_dev_plus_val_below_b2_minus_3pp'] = dv < b2v - 0.03

        # ---------------- outputs ----------------
        pl.DataFrame(curves_rows).write_parquet(run.path / 'equity_curves.parquet')
        trades_rows = []
        for cid, sr in sim_results.items():
            for t in sr['net'].trades:
                trades_rows.append({'config_id': cid, **t})
        for (freq, seed), r in b3.items():
            for t in r.trades:
                trades_rows.append({'config_id': f'B3-{freq}-s{seed}', **t})
        for freq, r in b1.items():
            for t in r.trades:
                trades_rows.append({'config_id': f'B1-{freq}', **t})
        pl.DataFrame(trades_rows).write_parquet(run.path / 'trades.parquet')

        pos_rows = []
        for cid, sr in sim_results.items():
            for p in sr['net'].positions:
                pos_rows.append({'config_id': cid,
                                 **{k: v for k, v in p.items()
                                    if k != 'entry_session'}})
            for fo in sr['net'].final_open:
                pos_rows.append({'config_id': cid,
                                 **{k: v for k, v in fo.items()
                                    if k != 'entry_session'}})
        pl.DataFrame(pos_rows).write_parquet(run.path / 'positions.parquet')

        timings['total_s'] = round(time.perf_counter() - t_all, 2)
        run.metrics['timings'] = timings
        write_json(run.path / 'metrics.json', run.metrics)
        report = build_report(config, run.metrics, smoke)
        (run.path / 'report.md').write_text(report, encoding='utf-8')
        print(f"dev_pass: {run.metrics['dev_pass_configs']} "
              f"advanced: {advanced} p3_candidates: {survivors}")
    return 0 if run.manifest['status'] == 'completed' else 1


def build_report(config: dict, metrics: dict, smoke: bool) -> str:
    lines = ['# P2-R6 ETF 轮动/动量初筛（预登记策略级回放）', '',
             f"- experiment_id: {config['experiment_id']}"
             f"{'（SMOKE：1 年 × C01/C04，判据不生效）' if smoke else ''}",
             '- 种子 17；B3 种子 17–36；费用：佣金万1 最低5元、无印花税/过户费、滑点 0',
             '', '## 基准', '']
    b = metrics.get('benchmarks', {})
    for freq, m in b.get('B1', {}).items():
        dev = m.get('dev', {})
        lines.append(f"- B1 同池等权（{freq}）dev 净年化 {fmt(dev.get('net_cagr'))}，"
                     f"回撤 {fmt(dev.get('max_drawdown'))}")
    for seg, m in b.get('B2', {}).items():
        lines.append(f"- B2 510300 买入持有 {seg}：净 {fmt(m.get('net_total_return'))}"
                     f"（毛 {fmt(m.get('gross_total_return'))}）")
    for freq in ('monthly', 'weekly'):
        k = f'B3_dev_{freq}'
        if k in metrics:
            lines.append(f"- B3 随机（{freq}，20 种子）dev 净年化均值 "
                         f"{fmt(metrics[k].get('mean_net_cagr'))} "
                         f"[{fmt(metrics[k].get('min'))}, {fmt(metrics[k].get('max'))}]")
    lines.append('- B4 现金 0%')
    lines.append('')
    lines += ['## 配置结果（dev）', '',
              '| 配置 | 频率 | W | 门 | 毛年化 | 净年化 | B1 | 净超额 | 优势年 | 回撤 |'
              ' 换手max | top1/top3 | dev判定 |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for cid in sorted(metrics.get('configs', {})):
        m = metrics['configs'][cid]
        g = metrics['gates'][cid]['dev']
        dev = m['dev']
        c = dev['concentration']
        lines.append(
            f"| {cid} | {m['freq']} | {m['W']} | {'开' if m['gate'] else '关'} "
            f"| {fmt(dev['gross_cagr'])} | {fmt(dev['net_cagr'])} "
            f"| {fmt(dev['b1_net_cagr'])} | {fmt(dev['excess_vs_b1'])} "
            f"| {g['positive_years']}/5 | {fmt(dev['max_drawdown'])} "
            f"| {fmt(dev['max_one_side_turnover'])} "
            f"| {fmt(c['top1_share'])}/{fmt(c['top3_share'])} "
            f"| {'PASS' if g['dev_pass'] else 'fail'} |")
    if metrics.get('advanced_to_validation'):
        cid = metrics['advanced_to_validation']
        m = metrics['configs'][cid]
        lines += ['', f'## 存活者 {cid} 后续段', '']
        for seg in ('validation', 'test'):
            if seg in m:
                mm = m[seg]
                g = metrics['gates'][cid].get(seg, {})
                lines.append(
                    f"- {seg}: 净年化 {fmt(mm['net_cagr'])}（毛 {fmt(mm['gross_cagr'])}），"
                    f"B1 {fmt(mm['b1_net_cagr'])}，净超额 {fmt(mm['excess_vs_b1'])}，"
                    f"回撤 {fmt(mm['max_drawdown'])}，"
                    f"gate={'PASS' if g.get('val_pass') or g.get('test_pass') else 'fail'}")
    lines += ['', '## 逐年净超额（对 B1，百分点）', '']
    for cid in sorted(metrics.get('configs', {})):
        m = metrics['configs'][cid]
        rows = [f"{y}:{fmt(e * 100)}" for y, e in m['dev']['excess_by_year'].items()]
        val = m.get('validation')
        if val:
            rows += ['| val'] + [f"{y}:{fmt(e * 100)}"
                                 for y, e in val['excess_by_year'].items()]
        lines.append(f"- {cid}: " + ', '.join(rows))
    lines += ['', '## 判定', '',
              f"- dev 通过：{metrics.get('dev_pass_configs')}",
              f"- 进入 validation：{metrics.get('advanced_to_validation')}",
              f"- P3 候选：{metrics.get('p3_candidates')}"]
    return '\n'.join(lines) + '\n'


def fmt(value) -> str:
    if value is None:
        return '—'
    return f'{value:.3f}' if abs(value) < 10 else f'{value:.1f}'


if __name__ == '__main__':
    raise SystemExit(main())
