"""P2-R7 ETF rotation dynamic-exposure CLI (exp-20260917-p2r7-etf-exposure).

Usage:
  python src/quant/cli/p2r7_etf_exposure.py \
      [--config configs/experiments/p2r7-etf-exposure.json] [--smoke]

Extends the P2-R6 pipeline with the three registered exposure mechanisms
(FIX 75% control / VOLT target-vol / TREND index SMA200), per-config TopN in
{3, 5} and the registered sizing rule min(exposure/N, 25%) x signal-close
equity with a never-negative portfolio cash pool.  ``--smoke`` restricts the
replay to the first dev year (2016) x C01 (FIX) / C03 (TREND) for exposure,
cash and fee checks; gates are computed but marked non-binding.

The full run evaluates all 12 frozen configs on dev (exploratory reuse of the
P2-R6-consumed window), then the frozen gate cascade (dev -> validation ->
test, at most one survivor; the test slice comes from the same single
continuous run and is reported only for the validation survivor).

dev is EXPLORATORY (REUSE): the P2-R6 round already consumed 2016-2020.
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
    simulate_b1_exposure,
    simulate_exposure,
    slice_curve,
    turnover_by_year,
    year_returns,
)
from quant.research.runs import Run, find_repo_root, write_json  # noqa: E402

WINDOWS = {'W3': (20, 60, 120), 'W2L': (60, 120), 'W2S': (20, 60)}
MECHS = ('FIX', 'VOLT', 'TREND')
B1_KEYS = ('FIX', 'VOLT', 'TREND', '100')
B3_SEEDS = list(range(17, 37))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2r7-etf-exposure.json')
    parser.add_argument('--smoke', action='store_true',
                        help='1 dev year (2016) x C01(FIX)/C03(TREND) smoke')
    return parser.parse_args()


def effective_config(base: dict, smoke: bool) -> dict:
    config = json.loads(json.dumps(base))
    if smoke:
        config['smoke'] = True
        config['segments']['dev'] = {'start': '2016-01-01', 'end': '2016-12-31'}
        config['segments']['validation'] = None
        config['segments']['test'] = None
        config['smoke_configs'] = ['C01', 'C03']
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


def summarize_exposure_path(exposure_of: dict[date, float]) -> dict:
    """Per calendar year: share of signal days per exposure level (exact when
    <= 3 distinct levels, else the registered bands)."""
    by_year: dict[int, list[float]] = {}
    for d in sorted(exposure_of):
        by_year.setdefault(d.year, []).append(exposure_of[d])
    distinct = sorted({round(v, 6) for v in exposure_of.values()})
    exact = len(distinct) <= 3
    out: dict = {'distinct_levels': distinct[:8], 'exact_levels': exact,
                 'years': {}}
    for y, vals in sorted(by_year.items()):
        n = len(vals)
        entry: dict = {'n_signal_days': n,
                       'mean_exposure': round(sum(vals) / n, 4)}
        if exact:
            for lv in distinct:
                entry[f'at_{lv:.2f}'] = round(
                    sum(1 for v in vals if round(v, 6) == lv) / n, 4)
        else:
            entry['at_0.40'] = round(sum(1 for v in vals if v <= 0.4001) / n, 4)
            entry['b_0.40-0.70'] = round(
                sum(1 for v in vals if 0.4001 < v < 0.6999) / n, 4)
            entry['b_0.70-1.00'] = round(
                sum(1 for v in vals if 0.6999 <= v < 0.9999) / n, 4)
            entry['at_1.00'] = round(sum(1 for v in vals if v >= 0.9999) / n, 4)
        out['years'][str(y)] = entry
    return out


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
    twelve = config['configs_grid']['twelve']
    config_ids = config.get('smoke_configs') or list(twelve)
    mech_params = config['exposure_mechanisms']

    with Run(root, config['name'], config) as run:
        timings: dict[str, float] = {}
        t0 = time.perf_counter()
        loaded = er.load_frames(root, config)
        feat: pl.DataFrame = loaded['feat']
        full_calendar = build_calendar(feat)

        # exposure series are computed from the UNTRIMMED data (2015 warmup
        # feeds the first dev signals; identical values in smoke and full)
        signal_days_all = rebalance_days(full_calendar, 'monthly', dev_start)
        pool_ret = er.pool_daily_returns(feat)
        idx_batch = root / config['data']['index_daily']['batch']
        index_close = er.load_index_close(
            idx_batch / config['data']['index_daily']['trend_file'])
        volt_p = mech_params['VOLT']
        trend_p = mech_params['TREND']
        exposures: dict[str, dict[date, float]] = {
            'FIX': er.fix_exposures(signal_days_all,
                                    float(mech_params['FIX']['exposure'])),
            'VOLT': er.volt_exposures(
                full_calendar, signal_days_all, pool_ret,
                target_vol=float(volt_p['target_vol']),
                clip_min=float(volt_p['clip_min']),
                clip_max=float(volt_p['clip_max']),
                window=int(volt_p['vol_window_sessions']),
                sessions_per_year=244),
            'TREND': er.trend_exposures(
                index_close, signal_days_all,
                sma_sessions=int(trend_p['sma_sessions']),
                level_on=float(trend_p['levels']['on']),
                level_off=float(trend_p['levels']['off'])),
        }
        run.metrics['exposure_paths'] = {m: summarize_exposure_path(exposures[m])
                                         for m in MECHS}
        run.manifest['inputs'] = [
            {'path': config['data']['fund_daily']['batch'],
             'manifest_sha256': config['data']['fund_daily']['manifest_sha256'],
             **loaded['stats']},
            {'path': config['data']['fund_adj']['batch'],
             'manifest_sha256': config['data']['fund_adj']['manifest_sha256']},
            {'path': config['data']['fund_basic']['batch'],
             'file_sha256': config['data']['fund_basic']['sha256']},
            {'path': config['data']['index_daily']['batch'],
             'manifest_sha256': config['data']['index_daily']['manifest_sha256'],
             'chunk_000300_sha256':
                 config['data']['index_daily']['chunk_000300_sha256'],
             'trend_rows': config['data']['index_daily']['trend_rows']},
        ]
        if smoke_end is not None:
            calendar = [d for d in full_calendar if d <= smoke_end]
            feat = feat.filter(pl.col('trade_date') <= smoke_end)
        else:
            calendar = full_calendar
        timings['load_and_exposure_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['load_stats'] = loaded['stats']
        run.metrics['timings'] = timings

        t0 = time.perf_counter()
        pools = group_pools(feat)
        bank = CodeDataBank(feat, calendar)
        timings['pools_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        signal_days = rebalance_days(calendar, 'monthly', dev_start)
        pool_sizes: dict[str, dict] = {}
        by_year: dict[int, list[int]] = {}
        for d in signal_days:
            by_year.setdefault(d.year, []).append(len(pools.get(d, [])))
        pool_sizes['monthly'] = {
            str(y): {'min': min(v), 'mean': round(sum(v) / len(v), 1),
                     'max': max(v)}
            for y, v in sorted(by_year.items())}
        run.metrics['pool_sizes'] = pool_sizes

        ranked_cache: dict[tuple, dict[date, list[str]]] = {}

        def ranked_for(window_key: str, days: list[date]) -> dict[date, list[str]]:
            # absolute momentum gate is OFF for every R7 config (registered)
            key = (window_key, False, 'monthly')
            if key not in ranked_cache:
                window = WINDOWS[window_key]
                ranked_cache[key] = {
                    d: [r.code for r in rank_pool(pools.get(d, []), window)]
                    for d in days}
            return ranked_cache[key]

        # ---------------- B1 family: matched / 100% reference, net+gross ----
        t0 = time.perf_counter()
        b1_results: dict[str, dict[str, er.SimResult]] = {}
        for key in B1_KEYS:
            expo = (exposures[key] if key in MECHS
                    else {d: 1.0 for d in signal_days_all})
            b1_results[key] = {
                'net': simulate_b1_exposure(pools, bank, calendar, dev_start,
                                            signal_days, expo, total=200_000.0,
                                            fees=ETF_FEE_BAND,
                                            config_id=f'B1-{key}'),
                'gross': simulate_b1_exposure(pools, bank, calendar, dev_start,
                                              signal_days, expo,
                                              total=200_000.0,
                                              fees=GROSS_FEE_BAND,
                                              config_id=f'B1-{key}-gross')}
        b2_code = '510300.SH'
        b2 = {seg: er.simulate_b2(b2_code, bank, calendar, s, e,
                                  total=200_000.0, fees=ETF_FEE_BAND)
              for seg, (s, e) in segs.items()}
        dv_end = (segs['validation'][1] if 'validation' in segs
                  else segs['dev'][1])
        b2_dev_val = er.simulate_b2(b2_code, bank, calendar, segs['dev'][0],
                                    dv_end, total=200_000.0, fees=ETF_FEE_BAND)
        timings['b1_b2_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------------- B3prime: same N + same exposure path, 20 seeds ----
        t0 = time.perf_counter()
        b3: dict[tuple[str, int], er.SimResult] = {}
        for mech in MECHS:
            for n_slots in (3, 5):
                for seed in B3_SEEDS:
                    rng = random.Random(seed)

                    def selector(t: date, _rng=rng) -> list[str]:
                        codes = [r.code for r in pools.get(t, [])]
                        _rng.shuffle(codes)
                        return codes

                    b3[(mech, n_slots, seed)] = simulate_exposure(
                        f'B3-{mech}-N{n_slots}-s{seed}', bank, calendar,
                        dev_start, signal_days, selector, exposures[mech],
                        n_slots=n_slots, fees=ETF_FEE_BAND, total=200_000.0)
        timings['b3prime_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------------- 12 configs: continuous net+gross paths -----------
        curves_rows: list[dict] = []
        sim_results: dict[str, dict] = {}
        for cid, spec in twelve.items():
            if cid not in config_ids:
                continue
            budget_exceeded(deadline, limits)
            t0 = time.perf_counter()
            ranked = ranked_for(spec['W'], signal_days)
            net = simulate_exposure(
                cid, bank, calendar, dev_start, signal_days,
                lambda t, _r=ranked: _r.get(t, []), exposures[spec['mech']],
                n_slots=int(spec['N']), fees=ETF_FEE_BAND, total=200_000.0)
            gross = simulate_exposure(
                cid + '-gross', bank, calendar, dev_start, signal_days,
                lambda t, _r=ranked: _r.get(t, []), exposures[spec['mech']],
                n_slots=int(spec['N']), fees=GROSS_FEE_BAND, total=200_000.0)
            parity = ([(t['session'], t['code'], t['side'], t['kind'])
                       for t in net.trades]
                      == [(t['session'], t['code'], t['side'], t['kind'])
                          for t in gross.trades])
            sim_results[cid] = {'spec': spec, 'net': net, 'gross': gross,
                                'net_gross_parity': parity}
            timings[f'sim_{cid}_s'] = round(time.perf_counter() - t0, 2)
            run.metrics['timings'] = timings

        for cid, sr in sim_results.items():
            for d, vn, vg in zip(sr['net'].sessions, sr['net'].equity,
                                 sr['gross'].equity):
                curves_rows.append({'config_id': cid, 'session': d,
                                    'equity_net': vn, 'equity_gross': vg})
            run.metrics.setdefault('net_gross_parity', {})[cid] = \
                sr['net_gross_parity']

        # ---------------- metrics per config -------------------------------
        metrics: dict[str, dict] = {}

        def years_of(seg: str) -> list[int]:
            if seg not in segs:
                return []
            s, e = segs[seg]
            return list(range(s.year, e.year + 1))

        def b1_metrics(key: str) -> dict:
            out_m: dict = {}
            net_r = b1_results[key]['net']
            gross_r = b1_results[key]['gross']
            acc = net_r.extra.get('turnover_acc', {})
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd, sv = slice_curve(net_r.sessions, net_r.equity, s, e)
                _, svg = slice_curve(gross_r.sessions, gross_r.equity, s, e)
                mean_eq = sum(sv) / len(sv) if sv else None
                buy = sum(acc.get(y, {}).get('buy_notional', 0.0)
                          for y in range(s.year, e.year + 1))
                out_m[seg] = {
                    'net_cagr': cagr(sv[0], sv[-1], sd[0], sd[-1]),
                    'gross_cagr': cagr(svg[0], svg[-1], sd[0], sd[-1]),
                    'net_total_return': sv[-1] / sv[0] - 1.0,
                    'gross_total_return': svg[-1] / svg[0] - 1.0,
                    'max_drawdown': max_drawdown(sd, sv)['max_drawdown'],
                    'one_side_turnover': (buy / mean_eq) if mean_eq else None,
                }
            return out_m

        b1_m = {key: b1_metrics(key) for key in B1_KEYS}

        def build_metrics(cid: str) -> dict:
            spec = sim_results[cid]['spec']
            mech = spec['mech']
            net: er.SimResult = sim_results[cid]['net']
            gross: er.SimResult = sim_results[cid]['gross']
            b1r = b1_results[mech]['net']
            b1g = b1_results[mech]['gross']
            out: dict = {'freq': 'monthly', 'W': spec['W'], 'N': spec['N'],
                         'mech': mech,
                         'max_negative_cash': net.max_negative_cash,
                         'n_trades': len(net.trades),
                         'exec_stats': net.exec_stats.as_dict()}
            dev_exec = None
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd_n, sv_n = slice_curve(net.sessions, net.equity, s, e)
                sd_g, sv_g = slice_curve(gross.sessions, gross.equity, s, e)
                sd_b, sv_b = slice_curve(b1r.sessions, b1r.equity, s, e)
                _, sv_bg = slice_curve(b1g.sessions, b1g.equity, s, e)
                mdd_n = max_drawdown(sd_n, sv_n)
                seg_m = {
                    'net_cagr': cagr(sv_n[0], sv_n[-1], sd_n[0], sd_n[-1]),
                    'gross_cagr': cagr(sv_g[0], sv_g[-1], sd_g[0], sd_g[-1]),
                    'net_total_return': sv_n[-1] / sv_n[0] - 1.0,
                    'gross_total_return': sv_g[-1] / sv_g[0] - 1.0,
                    'b1m_net_cagr': cagr(sv_b[0], sv_b[-1], sd_b[0], sd_b[-1]),
                    'b1m_gross_cagr': cagr(sv_bg[0], sv_bg[-1],
                                           sd_b[0], sd_b[-1]),
                    'max_drawdown': mdd_n['max_drawdown'],
                    'mdd_window': mdd_n,
                    'b1m_max_drawdown': max_drawdown(sd_b, sv_b)['max_drawdown'],
                }
                seg_m['excess_vs_b1m'] = (seg_m['net_cagr']
                                          - seg_m['b1m_net_cagr']
                                          if seg_m['net_cagr'] is not None
                                          else None)
                seg_m['gross_excess_vs_b1m'] = (seg_m['gross_cagr']
                                                - seg_m['b1m_gross_cagr']
                                                if seg_m['gross_cagr'] is not None
                                                else None)
                if seg == 'dev':
                    # registered gate-8 scope (revision-2 item 5): dev window
                    dev_exec = er.window_execution_rate(net.leg_log, s, e)
                    seg_m['execution_rate'] = dev_exec['execution_rate']
                    seg_m['execution_rate_dev_window'] = dev_exec
                else:
                    seg_m['execution_rate'] = None
                seg_m['execution_rate_full_window'] = \
                    out['exec_stats']['execution_rate']
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
                conc = concentration(net.positions, net.final_open, bank,
                                     calendar, s, e)
                seg_m['concentration'] = conc
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

        # ---------------- benchmark metrics --------------------------------
        run.metrics['benchmarks'] = {
            'B1': {key: b1_m[key] for key in B1_KEYS},
            'B2': {seg: {'net_total_return': b2[seg]['net_total_return'],
                         'gross_total_return': b2[seg]['gross_total_return'],
                         'net_cagr': cagr(200_000.0,
                                          200_000.0 * (1 + b2[seg]['net_total_return']),
                                          b2[seg]['entry_date'],
                                          b2[seg]['exit_date']),
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

        b3_means: dict[tuple[str, int], float] = {}
        for mech in MECHS:
            for n_slots in (3, 5):
                cagrs = []
                for seed in B3_SEEDS:
                    r = b3[(mech, n_slots, seed)]
                    sd, sv = slice_curve(r.sessions, r.equity, *segs['dev'])
                    cagrs.append(cagr(sv[0], sv[-1], sd[0], sd[-1]))
                mean = sum(cagrs) / len(cagrs)
                b3_means[(mech, n_slots)] = mean
                run.metrics[f'B3prime_{mech}_N{n_slots}'] = {
                    'n_seeds': len(B3_SEEDS), 'mean_net_cagr': mean,
                    'min': min(cagrs), 'max': max(cagrs),
                    'std': ((sum((x - mean) ** 2 for x in cagrs)
                             / (len(cagrs) - 1)) ** 0.5
                            if len(cagrs) > 1 else None),
                    'per_seed': {str(s): c for s, c in zip(B3_SEEDS, cagrs)}}

        # ---------------- mechanism trade-off (descriptive, not a gate) -----
        # saved drawdown (pp) vs the FIX control of the same (W, N), divided
        # by the rally given up (net CAGR pp); registered definition
        def find_config(w_key: str, n_slots: int, mech: str) -> str | None:
            for cid, s in twelve.items():
                if (s['W'] == w_key and s['N'] == n_slots and s['mech'] == mech
                        and cid in metrics):
                    return cid
            return None

        tradeoff = []
        for w_key in ('W2S', 'W2L'):
            for n_slots in (3, 5):
                fix_id = find_config(w_key, n_slots, 'FIX')
                if fix_id is None:
                    continue  # smoke may not include this FIX config
                fix = metrics[fix_id]
                for mech in ('VOLT', 'TREND'):
                    cid = find_config(w_key, n_slots, mech)
                    if cid is None:
                        continue
                    m = metrics[cid]
                    saved_dd = (abs(fix['dev']['max_drawdown'])
                                - abs(m['dev']['max_drawdown'])) * 100.0
                    lost_ret = (fix['dev']['net_cagr']
                                - m['dev']['net_cagr']) * 100.0
                    tradeoff.append({
                        'pair': f'{w_key}-N{n_slots}', 'mech': mech,
                        'config_id': cid,
                        'saved_drawdown_pp': round(saved_dd, 2),
                        'lost_net_cagr_pp': round(lost_ret, 2),
                        'saved_per_lost': (round(saved_dd / lost_ret, 3)
                                           if lost_ret > 1e-9 else None)})
        run.metrics['mechanism_tradeoff_vs_fix'] = tradeoff

        # ---------------- gates ---------------------------------------------
        gates: dict[str, dict] = {}
        for cid, m in metrics.items():
            budget_exceeded(deadline, limits)
            spec = twelve[cid]
            b1_dev = b1_m[spec['mech']]['dev']
            g = evaluate_dev_gate(
                m, {'net_cagr': b1_dev['net_cagr'],
                    'max_drawdown': b1_dev['max_drawdown']},
                b3_means[(spec['mech'], int(spec['N']))], freq='monthly')
            g['smoke_non_binding'] = args.smoke
            gates[cid] = {'dev': g}
        dev_pass = sorted(
            [(cid, gates[cid]['dev']['dev_excess_vs_b1'])
             for cid in gates if gates[cid]['dev']['dev_pass']],
            key=lambda kv: (-kv[1], kv[0]))
        advanced = None
        if dev_pass and not args.smoke:
            advanced = dev_pass[0][0]
            m = metrics[advanced]
            spec = twelve[advanced]
            b1_val = b1_m[spec['mech']].get('validation')
            gates[advanced]['validation'] = evaluate_val_gate(
                m, b1_val or {'net_cagr': None})
            if gates[advanced]['validation']['val_pass'] and 'test' in segs:
                gates[advanced]['test'] = evaluate_test(
                    m, b1_m[spec['mech']]['test'])
        for cid in gates:
            if (not args.smoke and gates[cid]['dev']['dev_pass']
                    and cid != advanced):
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
                  * (1 + metrics[advanced]['validation']['net_total_return'])
                  - 1)
            b2v = run.metrics['benchmarks']['B2_dev_plus_val']['net_total_return']
            run.metrics['advanced_dev_plus_val_net_total'] = dv
            run.metrics['advanced_dev_plus_val_below_b2_minus_3pp'] = \
                dv < b2v - 0.03

        # ---------------- outputs -------------------------------------------
        for key in B1_KEYS:
            for variant in ('net', 'gross'):
                r = b1_results[key][variant]
                for d, v in zip(r.sessions, r.equity):
                    curves_rows.append(
                        {'config_id': f'B1-{key}' if variant == 'net'
                         else f'B1-{key}-gross', 'session': d,
                         'equity_net': v, 'equity_gross': None})
        pl.DataFrame(curves_rows).write_parquet(run.path / 'equity_curves.parquet')

        trades_rows = []
        for cid, sr in sim_results.items():
            for t in sr['net'].trades:
                trades_rows.append({'config_id': cid, **t})
        for key in B1_KEYS:
            for t in b1_results[key]['net'].trades:
                trades_rows.append({'config_id': f'B1-{key}', **t})
        for (mech, n_slots, seed), r in b3.items():
            for t in r.trades:
                trades_rows.append({'config_id': f'B3-{mech}-N{n_slots}-s{seed}',
                                    **t})
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
        report = build_report(config, run.metrics, args.smoke)
        (run.path / 'report.md').write_text(report, encoding='utf-8')
        if args.smoke:
            print_smoke_verification(run.metrics, sim_results, exposures,
                                     signal_days)
        print(f"dev_pass: {run.metrics['dev_pass_configs']} "
              f"advanced: {advanced} p3_candidates: {survivors}")
    return 0 if run.manifest['status'] == 'completed' else 1


def print_smoke_verification(metrics: dict, sim_results: dict,
                             exposures: dict, signal_days: list[date]) -> None:
    """Registered smoke checks: exposure path, cash floor, fee totals."""
    print('\n=== SMOKE VERIFICATION (non-binding) ===')
    for mech in MECHS:
        vals = {d: v for d, v in exposures[mech].items()
                if d in set(signal_days)}
        sample = list(vals.items())[:4]
        print(f"exposure[{mech}]: {len(vals)} signal days, "
              f"first {[(str(d), round(v, 4)) for d, v in sample]}")
    for cid, sr in sim_results.items():
        net = sr['net']
        fees = sum(t['fee'] for t in net.trades)
        buys = [(t['session'], t['code'], round(t['notional'], 2))
                for t in net.trades if t['side'] == 'buy']
        print(f"{cid}: trades={len(net.trades)} buys={buys[:6]}"
              f"{'...' if len(buys) > 6 else ''} fees_total={fees:.2f} "
              f"min_cash={net.max_negative_cash:.6f} "
              f"final_equity={net.equity[-1]:.2f} "
              f"parity={sr['net_gross_parity']}")
        assert net.max_negative_cash >= 0.0, f'{cid}: NEGATIVE CASH'


def build_report(config: dict, metrics: dict, smoke: bool) -> str:
    lines = ['# P2-R7 ETF 轮动动态敞口（预登记策略级回放）', '',
             f"- experiment_id: {config['experiment_id']}"
             f"{'（SMOKE：1 年 × C01/C03，判据不生效）' if smoke else ''}",
             '- dev 段为探索性（重用）；种子 17；B3prime 种子 17–36；'
             '费用：佣金万1 最低5元、无印花税/过户费、滑点 0',
             '', '## 敞口路径（信号日档位占比）', '']
    for mech, path in metrics.get('exposure_paths', {}).items():
        yrs = path.get('years', {})
        y2016 = yrs.get('2016') or (next(iter(yrs.values())) if yrs else {})
        lines.append(f"- {mech}: 档位 {path.get('distinct_levels')}，"
                     f"2016: {y2016}")
    lines += ['', '## 基准', '']
    for key, segs_m in metrics.get('benchmarks', {}).get('B1', {}).items():
        dev = segs_m.get('dev', {})
        lines.append(f"- B1({key}) dev 净年化 {fmt(dev.get('net_cagr'))}（毛 "
                     f"{fmt(dev.get('gross_cagr'))}），回撤 "
                     f"{fmt(dev.get('max_drawdown'))}")
    for seg, m in metrics.get('benchmarks', {}).get('B2', {}).items():
        lines.append(f"- B2 510300 买入持有 {seg}：净 {fmt(m.get('net_total_return'))}"
                     f"（毛 {fmt(m.get('gross_total_return'))}）")
    for mech in MECHS:
        for n in (3, 5):
            k = f'B3prime_{mech}_N{n}'
            if k in metrics:
                lines.append(f"- B3prime 随机 Top{n}（{mech} 敞口，20 种子）dev 净年化均值 "
                             f"{fmt(metrics[k].get('mean_net_cagr'))} "
                             f"[{fmt(metrics[k].get('min'))}, {fmt(metrics[k].get('max'))}]")
    lines.append('- B4 现金 0%')
    lines += ['', '## 配置结果（dev，探索性重用）', '',
              '| 配置 | W | N | 机制 | 毛% | 净% | B1(m)净% | 净超额pp | 毛超额pp |'
              ' 优势年 | 回撤% | 换手max | top1/top3 | dev判定 |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for cid in sorted(metrics.get('configs', {})):
        m = metrics['configs'][cid]
        g = metrics['gates'][cid]['dev']
        dev = m['dev']
        c = dev['concentration']
        lines.append(
            f"| {cid} | {m['W']} | {m['N']} | {m['mech']} "
            f"| {fmt(dev['gross_cagr'])} | {fmt(dev['net_cagr'])} "
            f"| {fmt(dev['b1m_net_cagr'])} | {fmt(dev['excess_vs_b1m'])} "
            f"| {fmt(dev['gross_excess_vs_b1m'])} "
            f"| {g['positive_years']}/5 | {fmt(dev['max_drawdown'])} "
            f"| {fmt(dev['max_one_side_turnover'])} "
            f"| {fmt(c['top1_share'])}/{fmt(c['top3_share'])} "
            f"| {'PASS' if g['dev_pass'] else 'fail'} |")
    if metrics.get('mechanism_tradeoff_vs_fix'):
        lines += ['', '## 省回撤 ÷ 丢反弹（对同 W/N 的 FIX 对照，描述性）', '']
        for row in metrics['mechanism_tradeoff_vs_fix']:
            lines.append(
                f"- {row['pair']} {row['mech']}（{row['config_id']}）: "
                f"省回撤 {row['saved_drawdown_pp']}pp，丢净年化 "
                f"{row['lost_net_cagr_pp']}pp，比值 "
                f"{row['saved_per_lost'] if row['saved_per_lost'] is not None else '—'}")
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
                    f"B1(m) {fmt(mm['b1m_net_cagr'])}，净超额 {fmt(mm['excess_vs_b1m'])}，"
                    f"回撤 {fmt(mm['max_drawdown'])}，"
                    f"gate={'PASS' if g.get('val_pass') or g.get('test_pass') else 'fail'}")
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
