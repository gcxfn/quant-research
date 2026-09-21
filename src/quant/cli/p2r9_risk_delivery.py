"""P2-R9 risk-delivery engineering round CLI
(exp-20260918-p2r9-risk-delivery).

Usage:
  python src/quant/cli/p2r9_risk_delivery.py \
      [--config configs/experiments/p2r9-risk-delivery.json] [--smoke]

Fourth ETF-rotation round on the SAME frozen pool / monthly Top-N momentum
engine / data batches: the R8 daily-risk overlay is reused VERBATIM and the
only new mechanism is the registered HYSTERESIS state machine (OFF at
drawdown >= T; re-arm ON at drawdown <= T/2 from the SAME reference peak;
PDD peak = instance all-time running peak, never resets; D-family peak =
rolling window, the window keeps rolling; X1 off = either arm, on = both
re-armed).  12 frozen configs C01-C12 (W2S/W2L x N=3/4 x D60/D252/PDD/X1 x
e_low 0.40/0.30) plus two NON-JUDGED anchors (A1 = FIX75/W2S/N3 must be
bit-exact vs R8 C01; A2 = D60(8%)->0.40 no-hysteresis/W2S/N3 must be
bit-exact vs R8 C09).  dev (2016-2020) is EXPLORATORY (third reuse:
R6/R7/R8 consumed it); val (2021-22) / test (2023-24, one-shot) are the
only real filters.  STOP RULE: this line gets NO further rounds tonight
regardless of outcome.

Ordering guarantees (registered):
- ALL data pins (inheritance sha256 + 5 batch/file hashes) are verified
  against disk BEFORE the run directory exists (fail-closed; the R9 config
  carries the corrected fund_adj pin, cross-checked against disk here);
- anchor regressions run BEFORE any gate is consumed; a failure aborts the
  run (failed status, kept for the record, results never consumed).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
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
    FREEZE_END,
    GROSS_FEE_BAND,
    CodeDataBank,
    build_calendar,
    cagr,
    concentration,
    evaluate_dev_gate,
    evaluate_test,
    evaluate_val_gate,
    group_pools,
    hysteresis_switch_stats,
    max_drawdown,
    monthly_top_decile,
    rank_pool,
    rebalance_days,
    rolling_dd_series,
    simulate_b1_exposure,
    simulate_daily_risk,
    slice_curve,
    turnover_by_year,
    turnover_decomposition,
    year_returns,
)
from quant.research.runs import Run, find_repo_root, write_json  # noqa: E402

R8_RUN_DIR = ROOT / 'artifacts/runs/20260918T021054-p2r8-daily-risk-d19a9c07'
B3_SEEDS = list(range(17, 37))
E_ON = 0.90
RISK_KINDS = frozenset({'retarget_buy', 'retarget_sell'})
WINDOWS = {'W2S': (20, 60), 'W2L': (60, 120)}
EQUITY_INDEPENDENT_MECHS = frozenset({'FIX75', 'D60', 'D252'})

# registered deviations fixed before any run (disclosed in metrics + report)
DEVIATIONS = [
    {'id': 1, 'item': 'R9 hysteresis machine start point (prereg does not '
     'spell it out, fixed BEFORE any run): the machine starts at the FIRST '
     'SIMULATED session (dev start 2016-01-04) with the registered init '
     'state ON; the D-family drawdown series it consumes is computed over '
     'the full loaded calendar so the rolling windows reach into the 2015 '
     'warmup exactly as in R8 (registered warmup purpose).  PDD instance '
     'peaks start at the first simulated session (R8 semantics carried: '
     '"all-time" = the instance own path, fresh closure per instance incl. '
     'B1(m) and every B3prime seed).'},
    {'id': 2, 'item': 'D252 warmup: the index batch has 244 rows in 2015, so '
     'the 252-session rolling peak is not formed for the first 8 sessions of '
     '2016; the REGISTERED fallback (insufficient history = treated as '
     'triggered, risk-off e_low) applies to C06/C07 (and their B1(m)/B3prime '
     'instances).  Count recorded in metrics.warmup_fallback_sessions; D60 '
     'is fully formed throughout the simulated window.'},
    {'id': 3, 'item': 'boundary conventions: the hysteresis machine uses the '
     'preregistered triggers verbatim on floats (OFF at dd >= T; re-arm at '
     'dd <= T/2), while the NO-hysteresis path (C02/A2) reuses the R8 '
     'rolling_dd_state verbatim (on iff dd <= T).  The two differ only at '
     'exact float equality dd == T; metrics.boundary_exact_dd_sessions '
     'records that count (0 expected) on the pinned index data.'},
    {'id': 4, 'item': 'C11 re-arm values are parsed from the frozen config '
     'string field ("D60 arm <=0.04, PDD arm <=0.05") by pattern match; a '
     'parse failure hard-fails the run (fail-closed, frozen file never '
     'edited).'},
    {'id': 5, 'item': 'PDD/X1 net-vs-gross parity is structurally not '
     'guaranteed (fees feed back into the instance own-equity peak); parity '
     'is ASSERTED for every equity-independent config (C01-C07, C12, A1, '
     'A2) and reported as-is for C08-C11 (R8 deviation 5 carried).'},
    {'id': 6, 'item': 'position bookkeeping on partial re-sizes: a retarget '
     'sell reduces the position cumulative net-spend proportionally by '
     'units, a retarget buy adds its budget; close-out pnl stays cash-flow '
     'consistent (R8 deviation 6 carried; attribution only, no cash '
     'effect).'},
    {'id': 7, 'item': 'B1(m) rescale postponement details and de-minimis '
     'guards (R8 deviations 7/8/9 carried): postponed rescales retry at '
     'later opens, latest target wins, buys capped by the idle pool '
     '(never negative), a sell whose gross notional is at/below the 5-CNY '
     'commission minimum is skipped as a rule-compliant cash slot; the same '
     'guards apply to N=4.'},
    {'id': 8, 'item': 'effective-config materialization (in memory, pre-run; '
     'R7/R8 precedent deviation class): u1_whitelist_frozen / universe / '
     'preflight are injected VERBATIM from the sha256-verified R7 '
     'inheritance source; the frozen R9 file is never modified and defines '
     'none of the three blocks (conflict-checked); run-dir config.json '
     'records the effective snapshot.'},
    {'id': 9, 'item': 'gate-6 concentration for N=4 configs stays top-1 '
     '<=40% / top-3 <=70% as frozen; the top-4 share is DISCLOSURE only '
     '(metrics configs.{cid}.{seg}.concentration.top4_share).'},
    {'id': 10, 'item': 'B3prime matching: random Top-N runs the SAME '
     'mechanism+hysteresis AND the config own N (benchmark block "random '
     'Top-N same mechanism+hysteresis"); gate-7 compares each config '
     'against the B3prime mean of its own (mechanism, N) cell.'},
    {'id': 11, 'item': 'latent key-name defect found at the FIRST full run '
     '(kept for the record as a FAILED run, anchors had already passed): '
     'evaluate_val_gate reads m["val"] while build_metrics stores the '
     'segment under m["validation"] -- unreachable in R8 because no R8 '
     'config ever passed dev.  Fixed at the call site with a read-only '
     'adapter view (no engine/gate-semantics change, no frozen-file '
     'change); run discarded and re-executed from scratch.'},
    {'id': 12, 'item': 'metrics DISPLAY-key defect found at the SECOND full '
     'run (completed, kept for the record): B3prime summary keys omitted N, '
     'so three (mechanism, N) cells sharing a mechanism key overwrote each '
     'other in metrics.json.  GATE INPUTS WERE NOT AFFECTED (gate-7 reads '
     'the (mechanism, N)-keyed internal map; verified by recomputing the '
     'overwritten cells from the run equity_curves.parquet bit-for-bit).  '
     'Display keys now carry N; run superseded by a fresh identical-'
     'semantics run.'},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path,
                        default=ROOT / 'configs/experiments/p2r9-risk-delivery.json')
    parser.add_argument('--smoke', action='store_true',
                        help='1 dev year (2016) x C01(D60-hyst)/C03(W2L D60-hyst) smoke')
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pins(config: dict, root: Path) -> list[dict]:
    """Fail-closed identity checks BEFORE the run directory is created.
    Every pin must match the disk bytes; the R9 config carries the corrected
    fund_adj pin (R8 lesson), so there is NO transcription-resolution path
    here: any mismatch aborts the run."""
    checks: list[dict] = []
    inh = config['inherits_from']
    p = root / inh['file']
    got = sha256_file(p)
    checks.append({'what': 'inherits_from (R7 config)', 'path': inh['file'],
                   'expected': inh['sha256'], 'actual': got,
                   'ok': got == inh['sha256'], 'resolution': 'primary'})
    if got != inh['sha256']:
        raise SystemExit(f'FAIL-CLOSED: inheritance pin mismatch for {p}: '
                         f'{got} != {inh["sha256"]}')
    d = config['data']
    for name, path, key in (
            ('fund_basic', root / d['fund_basic']['batch']
             / d['fund_basic']['file'], d['fund_basic']['sha256']),
            ('fund_daily_manifest',
             root / d['fund_daily']['batch'] / 'manifest.json',
             d['fund_daily']['manifest_sha256']),
            ('fund_adj_manifest', root / d['fund_adj']['batch'] / 'manifest.json',
             d['fund_adj']['manifest_sha256']),
            ('index_000300', root / d['index_daily']['batch']
             / d['index_daily']['risk_file'],
             d['index_daily']['chunk_000300_sha256']),
            ('index_manifest', root / d['index_daily']['batch'] / 'manifest.json',
             d['index_daily']['manifest_sha256'])):
        got = sha256_file(path)
        ok = got == key
        checks.append({'what': name, 'path': str(path.relative_to(root)),
                       'expected': key, 'actual': got, 'ok': ok,
                       'resolution': 'primary' if ok else 'unresolvable-mismatch'})
        if not ok:
            raise SystemExit(f'FAIL-CLOSED: data pin mismatch for {path}: '
                             f'{got} != {key}')
    return checks


def effective_config(base: dict, r7: dict, smoke: bool) -> tuple[dict, list[str]]:
    """Materialize the effective config: the frozen R9 file plus the three
    inheritance blocks injected VERBATIM from the hash-verified R7 config
    (deviation 8; the frozen file itself is never modified)."""
    config = json.loads(json.dumps(base))
    injected = []
    for key in ('u1_whitelist_frozen', 'universe', 'preflight'):
        if key in config:
            raise SystemExit(f'FAIL-CLOSED: R9 config defines {key!r} itself; '
                             'inheritance injection would conflict')
        if key not in r7:
            raise SystemExit(f'FAIL-CLOSED: R7 config lacks {key!r}')
        config[key] = json.loads(json.dumps(r7[key]))
        injected.append(key)
    if smoke:
        config['smoke'] = True
        config['segments']['dev'] = {'start': '2016-01-01', 'end': '2016-12-31'}
        config['segments']['validation'] = None
        config['segments']['test'] = None
        config['smoke_configs'] = ['C01', 'C03']
        config['name'] = base['name'] + '-smoke'
    return config, injected


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


def parse_x1_rearms(raw: str) -> tuple[float, float]:
    """Deviation 4: parse the two arm re-arm thresholds from the frozen
    string description; a parse failure hard-fails (fail-closed)."""
    m = re.search(r'D60 arm <=(0?\.\d+).*?PDD arm <=(0?\.\d+)', raw)
    if not m:
        raise SystemExit(f'FAIL-CLOSED: cannot parse C11 re-arm spec: {raw!r}')
    return float(m.group(1)), float(m.group(2))


def build_mechs(specs: dict[str, dict], states: dict, calendar: list[date],
                start: date) -> dict[str, tuple]:
    """Per config -> (make_risk_fn factory, mech_key).  Equity-independent
    states (drawdown series, hysteresis dicts) are shared through ``states``;
    PDD/X1 factories return FRESH closures per instance."""
    mechs: dict[str, tuple] = {}
    for cid, spec in specs.items():
        mech = spec['mech']
        e_low = float(spec['e_low'])
        if mech == 'FIX75':
            mechs[cid] = ((lambda: er.constant_risk_fn(0.75)), 'FIX75')
            continue
        if mech in ('D60', 'D252'):
            w = 60 if mech == 'D60' else 252
            th = float(spec['T'])
            rearm = spec.get('rearm')
            if rearm is None:
                # registered NO-hysteresis path: R8 state function VERBATIM
                st = er.rolling_dd_state(states['index'], calendar, w, th)
                key = f'{mech}-{th * 100:g}-L{e_low:g}'
            else:
                ra = float(rearm)
                hkey = ('hyst', w, th, ra)
                if hkey not in states:
                    states[hkey] = er.hysteresis_state(
                        states[('dd', w)], calendar, th, ra, start)
                st = states[hkey]
                key = f'{mech}-{th * 100:g}H{ra * 100:g}-L{e_low:g}'
            expo = er.exposures_from_state(st, E_ON, e_low)
            mechs[cid] = (
                (lambda expo=expo: (lambda d, e, _e=expo: _e[d])), key)
            continue
        if mech == 'PDD':
            th = float(spec['T'])
            ra = float(spec['rearm'])
            key = f'PDD-{th * 100:g}H{ra * 100:g}-L{e_low:g}'
            mechs[cid] = (
                (lambda th=th, ra=ra, el=e_low:
                 er.pdd_hysteresis_risk_fn(th, ra, E_ON, el)), key)
            continue
        if mech == 'X1':
            arms = spec['arms']
            d_th = float(arms[0]['T'])
            p_th = float(arms[1]['T'])
            d_ra, p_ra = parse_x1_rearms(spec['rearm'])
            hkey = ('hyst', 60, d_th, d_ra)
            if hkey not in states:
                states[hkey] = er.hysteresis_state(
                    states[('dd', 60)], calendar, d_th, d_ra, start)
            d_state = states[hkey]
            key = (f'X1-D60-{d_th * 100:g}H{d_ra * 100:g}'
                   f'+PDD-{p_th * 100:g}H{p_ra * 100:g}-L{e_low:g}')
            mechs[cid] = (
                (lambda ds=d_state, pt=p_th, pr=p_ra, el=e_low:
                 er.x1_hysteresis_risk_fn(ds, pt, pr, E_ON, el)), key)
            continue
        raise SystemExit(f'FAIL-CLOSED: unknown mechanism {mech!r}')
    return mechs


def risk_trade_stats(trades: list[dict], s: date, e: date) -> dict:
    rt = [t for t in trades
          if t['kind'] in RISK_KINDS and s <= t['session'] <= e]
    fees = sum(t['fee'] for t in rt)
    all_fees = sum(t['fee'] for t in trades if s <= t['session'] <= e)
    return {'n_trades': len(rt),
            'n_buys': sum(1 for t in rt if t['side'] == 'buy'),
            'n_sells': sum(1 for t in rt if t['side'] == 'sell'),
            'buy_notional': sum(t['notional'] for t in rt if t['side'] == 'buy'),
            'sell_notional': sum(t['notional'] for t in rt
                                 if t['side'] == 'sell'),
            'fees': fees,
            'fee_share_of_total': (fees / all_fees) if all_fees else 0.0}


def curves_bit_exact(a: list, b: list) -> bool:
    return len(a) == len(b) and all(x == y for x, y in zip(a, b))


def verify_anchors(curves_rows: list[dict], b1_100_dev: dict,
                   smoke_end: date | None) -> dict:
    """Registered anchors, run BEFORE any gate consumption; any failure
    raises (run marked failed, kept for the record, never consumed).
    A1 = FIX75/W2S/N3 vs R8 run C01 (net AND gross); A2 = D60(8)->0.40
    no-hysteresis/W2S/N3 vs R8 run C09 (net AND gross); B1@100% dev
    +10.40%/+63.9%/-27.47% (exact vs the R8 run metrics and within the
    published tolerance)."""
    r8_curves = pl.read_parquet(R8_RUN_DIR / 'equity_curves.parquet')
    r8_metrics = json.loads(
        (R8_RUN_DIR / 'metrics.json').read_text(encoding='utf-8'))

    def r8_series(cid: str) -> tuple[list, list, list]:
        dfr = r8_curves.filter(pl.col('config_id') == cid).sort('session')
        if smoke_end is not None:
            dfr = dfr.filter(pl.col('session') <= smoke_end)
        return (dfr['session'].to_list(), dfr['equity_net'].to_list(),
                dfr['equity_gross'].to_list())

    out: dict = {'r8_run': str(R8_RUN_DIR.relative_to(ROOT)),
                 'r8_run_trial_count': r8_metrics.get('trial_count_cumulative'),
                 'scope': ('sessions<=' + smoke_end.isoformat()
                           if smoke_end else 'full')}
    for anchor, r8_cid in (('A1', 'C01'), ('A2', 'C09')):
        s8, n8, g8 = r8_series(r8_cid)
        rows = sorted((r for r in curves_rows if r['config_id'] == anchor),
                      key=lambda r: r['session'])
        out[f'{anchor}_vs_{r8_cid}_sessions_equal'] = \
            s8 == [r['session'] for r in rows]
        out[f'{anchor}_vs_{r8_cid}_net_bit_exact'] = curves_bit_exact(
            [r['equity_net'] for r in rows], n8)
        out[f'{anchor}_vs_{r8_cid}_gross_bit_exact'] = curves_bit_exact(
            [r['equity_gross'] for r in rows], g8)
    s8b, n8b, _ = r8_series('B1-100')
    rows = sorted((r for r in curves_rows if r['config_id'] == 'B1-100'),
                  key=lambda r: r['session'])
    out['b1_100_vs_r8_sessions_equal'] = s8b == [r['session'] for r in rows]
    out['b1_100_vs_r8_bit_exact'] = curves_bit_exact(
        [r['equity_net'] for r in rows], n8b)
    if smoke_end is None:
        r8_100 = r8_metrics['benchmarks']['B1']['100']['dev']
        out['b1_100_dev_net_cagr_exact'] = \
            b1_100_dev['net_cagr'] == r8_100['net_cagr']
        out['b1_100_dev_total_exact'] = \
            b1_100_dev['net_total_return'] == r8_100['net_total_return']
        out['b1_100_dev_mdd_exact'] = \
            b1_100_dev['max_drawdown'] == r8_100['max_drawdown']
        out['b1_100_published_check'] = {
            'net_cagr_10.40pct': abs(b1_100_dev['net_cagr'] - 0.1040) < 0.0005,
            'net_total_63.9pct': abs(b1_100_dev['net_total_return'] - 0.639) < 0.0005,
            'mdd_-27.47pct': abs(b1_100_dev['max_drawdown'] + 0.2747) < 0.0005}
    else:
        out['b1_100_dev_metrics'] = 'skipped in smoke (dev window is 2016 only)'
    failed = [k for k, v in out.items()
              if v is False or (isinstance(v, dict)
                                and not all(v.values()))]
    out['all_pass'] = not failed
    if failed:
        raise RuntimeError(f'ANCHOR REGRESSION FAILED: {failed}; results must '
                           'not be consumed (failed run kept for the record)')
    return out


def fmt(value) -> str:
    if value is None:
        return '—'
    return f'{value * 100:.2f}' if abs(value) < 10 else f'{value * 100:.1f}'


def main() -> int:
    args = parse_args()
    base = json.loads(args.config.read_text(encoding='utf-8'))
    os.chdir(ROOT)
    root = find_repo_root()
    pin_checks = verify_pins(base, root)  # fail-closed BEFORE the run exists
    r7 = json.loads((root / base['inherits_from']['file']).read_text(
        encoding='utf-8'))
    config, injected = effective_config(base, r7, args.smoke)
    limits = config.get('limits', {'max_runtime_s': 1800, 'max_ram_gb': 11})
    deadline = time.perf_counter() + float(limits['max_runtime_s'])
    t_all = time.perf_counter()
    segs = segment_bounds(config)
    dev_start = segs['dev'][0]
    smoke_end = segs['dev'][1] if args.smoke else None
    twelve = config['configs_grid']['twelve']
    anchor_specs = {
        'A1': {'W': 'W2S', 'N': 3, 'mech': 'FIX75', 'e_low': 0.75},
        'A2': {'W': 'W2S', 'N': 3, 'mech': 'D60', 'T': 0.08, 'e_low': 0.40,
               'rearm': None},
    }
    config_ids = config.get('smoke_configs') or list(twelve)
    all_sims = config_ids + ['A1', 'A2']  # anchors simulated, never judged

    with Run(root, config['name'], config) as run:
        timings: dict[str, float] = {}
        run.metrics['pin_checks'] = pin_checks
        run.metrics['inherited_blocks_injected'] = injected
        run.metrics['deviations'] = DEVIATIONS
        run.metrics['dev_label'] = 'exploratory (third reuse: R6/R7/R8 consumed dev)'
        run.metrics['anchors_non_judged'] = ['A1', 'A2']

        # ---------- data -----------------------------------------------------
        t0 = time.perf_counter()
        d = config['data']
        loaded = er.load_frames(root, config)
        feat: pl.DataFrame = loaded['feat']
        full_calendar = build_calendar(feat)
        if smoke_end is not None:
            calendar = [x for x in full_calendar if x <= smoke_end]
            feat = feat.filter(pl.col('trade_date') <= smoke_end)
        else:
            calendar = full_calendar
        timings['load_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        run.metrics['load_stats'] = loaded['stats']
        run.manifest['inputs'] = [
            {'path': d['fund_daily']['batch'],
             'manifest_sha256': d['fund_daily']['manifest_sha256'],
             **loaded['stats']},
            {'path': d['fund_adj']['batch'],
             'manifest_sha256': d['fund_adj']['manifest_sha256']},
            {'path': d['fund_basic']['batch'],
             'file_sha256': d['fund_basic']['sha256']},
            {'path': d['index_daily']['batch'],
             'manifest_sha256': d['index_daily']['manifest_sha256'],
             'chunk_000300_sha256': d['index_daily']['chunk_000300_sha256'],
             'r7_inheritance_verified': True},
        ]

        t0 = time.perf_counter()
        pools = group_pools(feat)
        bank = CodeDataBank(feat, calendar)
        timings['pools_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------- mechanism inputs (index only) ----------------------------
        index_close = er.load_index_close(
            root / d['index_daily']['batch'] / d['index_daily']['risk_file'])
        index_close = index_close.filter(pl.col('trade_date') <= FREEZE_END)
        dd60 = rolling_dd_series(index_close, calendar, 60)
        dd252 = rolling_dd_series(index_close, calendar, 252)
        states = {'index': index_close, ('dd', 60): dd60, ('dd', 252): dd252}
        run.metrics['warmup_fallback_sessions'] = {
            'D60': sum(1 for x in calendar
                       if x >= dev_start and dd60[x] is None),
            'D252': sum(1 for x in calendar
                        if x >= dev_start and dd252[x] is None)}
        # deviation 3 evidence: exact float equality at the trigger boundary
        run.metrics['boundary_exact_dd_sessions'] = {
            f'D60@0.08': sum(1 for x in calendar
                             if x >= dev_start and dd60[x] is not None
                             and dd60[x] == 0.08),
            f'D252@0.10': sum(1 for x in calendar
                              if x >= dev_start and dd252[x] is not None
                              and dd252[x] == 0.10)}
        mechs = build_mechs({**twelve, **anchor_specs}, states, calendar,
                            dev_start)
        run.metrics['mech_keys'] = {cid: mechs[cid][1] for cid in all_sims}

        signal_days = rebalance_days(calendar, 'monthly', dev_start)
        ranked_cache: dict[tuple, dict[date, list[str]]] = {}

        def ranked_for(window: tuple[int, int]) -> dict[date, list[str]]:
            key = (window, 'monthly')
            if key not in ranked_cache:
                ranked_cache[key] = {
                    x: [r.code for r in rank_pool(pools.get(x, []), window)]
                    for x in signal_days}
            return ranked_cache[key]

        ranked_by_w = {w: ranked_for(WINDOWS[w]) for w in WINDOWS}
        budget_exceeded(deadline, limits)

        # ---------------- B1 family (mechanism daily path, net+gross) -------
        t0 = time.perf_counter()
        judged_keys = sorted({mechs[cid][1] for cid in config_ids})
        b1_makes: dict[str, object] = {}
        for cid in config_ids:
            b1_makes.setdefault(mechs[cid][1], mechs[cid][0])
        b1_makes.setdefault('FIX75', lambda: er.constant_risk_fn(0.75))
        b1_makes['100'] = lambda: er.constant_risk_fn(1.0)
        b1_keys = judged_keys + ['FIX75', '100']
        b1_results: dict[str, dict[str, er.SimResult]] = {}
        for key in b1_keys:
            b1_results[key] = {}
            for variant, fees in (('net', ETF_FEE_BAND),
                                  ('gross', GROSS_FEE_BAND)):
                b1_results[key][variant] = simulate_b1_exposure(
                    pools, bank, calendar, dev_start, signal_days, {},
                    total=200_000.0, fees=fees,
                    config_id=f'B1-{key}' if variant == 'net'
                    else f'B1-{key}-gross',
                    risk_fn=b1_makes[key]())
        b2_code = '510300.SH'
        b2 = {seg: er.simulate_b2(b2_code, bank, calendar, s, e,
                                  total=200_000.0, fees=ETF_FEE_BAND)
              for seg, (s, e) in segs.items()}
        timings['b1_b2_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        budget_exceeded(deadline, limits)

        # ---------------- B3prime: random Top-N, same mech, 20 seeds --------
        t0 = time.perf_counter()
        b3_combos = sorted({(mechs[cid][1], int(twelve[cid]['N']))
                            for cid in config_ids})
        b3: dict[tuple[str, int, int], er.SimResult] = {}
        for key, n_slots in b3_combos:
            make = b1_makes[key]
            for seed in B3_SEEDS:
                rng = random.Random(seed)

                def selector(t: date, _rng=rng) -> list[str]:
                    codes = [r.code for r in pools.get(t, [])]
                    _rng.shuffle(codes)
                    return codes

                b3[(key, n_slots, seed)] = simulate_daily_risk(
                    f'B3-{key}-N{n_slots}-s{seed}', bank, calendar, dev_start,
                    signal_days, selector, make(), n_slots=n_slots,
                    fees=ETF_FEE_BAND, total=200_000.0)
        timings['b3prime_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings
        run.metrics['b3prime_cells'] = [f'{k}|N={n}' for k, n in b3_combos]
        budget_exceeded(deadline, limits)

        # ---------------- configs + anchors: continuous net+gross paths -----
        curves_rows: list[dict] = []
        sim_results: dict[str, dict] = {}
        for cid in all_sims:
            budget_exceeded(deadline, limits)
            t0 = time.perf_counter()
            spec = twelve.get(cid) or anchor_specs[cid]
            ranked = ranked_by_w[spec['W']]
            make, mech_key = mechs[cid]
            n_slots = int(spec['N'])
            net = simulate_daily_risk(
                cid, bank, calendar, dev_start, signal_days,
                lambda t, _r=ranked: _r.get(t, []), make(), n_slots=n_slots,
                fees=ETF_FEE_BAND, total=200_000.0)
            gross = simulate_daily_risk(
                cid + '-gross', bank, calendar, dev_start, signal_days,
                lambda t, _r=ranked: _r.get(t, []), make(), n_slots=n_slots,
                fees=GROSS_FEE_BAND, total=200_000.0)
            parity = ([(t['session'], t['code'], t['side'], t['kind'])
                       for t in net.trades]
                      == [(t['session'], t['code'], t['side'], t['kind'])
                          for t in gross.trades])
            sim_results[cid] = {'spec': spec, 'net': net, 'gross': gross,
                                'net_gross_parity': parity,
                                'mech_key': mech_key,
                                'equity_independent':
                                    spec['mech'] in EQUITY_INDEPENDENT_MECHS}
            timings[f'sim_{cid}_s'] = round(time.perf_counter() - t0, 2)
            run.metrics['timings'] = timings

        for cid, sr in sim_results.items():
            for x, vn, vg in zip(sr['net'].sessions, sr['net'].equity,
                                 sr['gross'].equity):
                curves_rows.append({'config_id': cid, 'session': x,
                                    'equity_net': vn, 'equity_gross': vg})
            run.metrics.setdefault('net_gross_parity', {})[cid] = \
                sr['net_gross_parity']
            if sr['equity_independent'] and not sr['net_gross_parity']:
                raise RuntimeError(
                    f'{cid}: net/gross trade-sequence parity violated for an '
                    'equity-independent mechanism (engine defect)')
        for key in b1_keys:
            for variant in ('net', 'gross'):
                r = b1_results[key][variant]
                for x, v in zip(r.sessions, r.equity):
                    curves_rows.append(
                        {'config_id': f'B1-{key}' if variant == 'net'
                         else f'B1-{key}-gross', 'session': x,
                         'equity_net': v, 'equity_gross': None})

        # ---------------- ANCHOR REGRESSIONS (before any gate) --------------
        def b1_dev_metrics(key: str) -> dict:
            r = b1_results[key]['net']
            s, e = segs['dev']
            sd, sv = slice_curve(r.sessions, r.equity, s, e)
            return {'net_cagr': cagr(sv[0], sv[-1], sd[0], sd[-1]),
                    'net_total_return': sv[-1] / sv[0] - 1.0,
                    'max_drawdown': max_drawdown(sd, sv)['max_drawdown']}

        t0 = time.perf_counter()
        run.metrics['anchor_regressions'] = verify_anchors(
            curves_rows, b1_dev_metrics('100'), smoke_end)
        timings['anchors_s'] = round(time.perf_counter() - t0, 2)
        run.metrics['timings'] = timings

        # ---------------- metrics per config --------------------------------
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

        b1_m = {key: b1_metrics(key) for key in b1_keys}

        def build_metrics(cid: str) -> dict:
            sr = sim_results[cid]
            spec = sr['spec']
            net: er.SimResult = sr['net']
            gross: er.SimResult = sr['gross']
            mech_key = sr['mech_key']
            e_low = float(spec.get('e_low', 0.0))
            out: dict = {'freq': 'monthly', 'W': WINDOWS[spec['W']],
                         'W_name': spec['W'], 'N': int(spec['N']),
                         'mech': spec['mech'], 'mech_key': mech_key,
                         'e_low': e_low, 'rearm': spec.get('rearm'),
                         'max_negative_cash': net.max_negative_cash,
                         'n_trades': len(net.trades),
                         'exec_stats': net.exec_stats.as_dict(),
                         'hysteresis_switch_stats_by_year':
                             hysteresis_switch_stats(net.sessions,
                                                     net.extra['e_series'],
                                                     e_low),
                         'turnover_decomposition_by_year':
                             {str(y): v for y, v in
                              turnover_decomposition(net).items()}}
            for seg in ('dev', 'validation', 'test'):
                if seg not in segs:
                    continue
                s, e = segs[seg]
                sd_n, sv_n = slice_curve(net.sessions, net.equity, s, e)
                sd_g, sv_g = slice_curve(gross.sessions, gross.equity, s, e)
                b1r = b1_results[mech_key]['net']
                b1g = b1_results[mech_key]['gross']
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
                seg_m['dd_margin_vs_b1m_pp'] = (
                    (seg_m['b1m_max_drawdown'] - seg_m['max_drawdown']) * 100.0
                    if seg_m['max_drawdown'] is not None else None)
                if seg == 'dev':
                    # registered gate-8 scope: dev-window legs planned on
                    # signal days AND risk state-change days
                    dev_exec = er.window_execution_rate(net.leg_log, s, e)
                    seg_m['execution_rate'] = dev_exec['execution_rate']
                    seg_m['execution_rate_dev_window'] = dev_exec
                seg_m['execution_rate_full_window'] = \
                    er.window_execution_rate(net.leg_log, calendar[0],
                                             calendar[-1])['execution_rate']
                strat_years = year_returns(sd_n, sv_n)
                b1_years = year_returns(sd_b, sv_b)
                seg_m['net_return_by_year'] = {str(y): strat_years.get(y)
                                               for y in years_of(seg)}
                seg_m['excess_by_year'] = {
                    str(y): (strat_years[y] - b1_years[y]
                             if y in strat_years and y in b1_years else None)
                    for y in years_of(seg)}
                turnover = turnover_by_year(net)
                seg_m['turnover_by_year'] = {str(y): turnover.get(y)
                                             for y in years_of(seg)}
                seg_m['max_one_side_turnover'] = max(
                    (turnover[y]['one_side_turnover'] for y in years_of(seg)
                     if turnover.get(y)), default=None)
                seg_m['risk_trades'] = risk_trade_stats(net.trades, s, e)
                conc = concentration(net.positions, net.final_open, bank,
                                     calendar, s, e)
                seg_m['concentration'] = conc
                seg_m['monthly_top_decile'] = monthly_top_decile(sd_n, sv_n)
                seg_m['forced_delist'] = {
                    'count': sum(1 for p in net.positions
                                 if p['exit_kind'] == 'forced_delist_close'
                                 and s <= p['exit_date'] <= e)}
                out[seg] = seg_m
            return out

        for cid in config_ids:
            budget_exceeded(deadline, limits)
            metrics[cid] = build_metrics(cid)
            run.metrics['configs'] = metrics
        for cid in ('A1', 'A2'):  # non-judged anchors: headline dev metrics only
            sr = sim_results[cid]
            net, gross = sr['net'], sr['gross']
            s, e = segs['dev']
            sd_n, sv_n = slice_curve(net.sessions, net.equity, s, e)
            sd_g, sv_g = slice_curve(gross.sessions, gross.equity, s, e)
            metrics[cid] = {
                'non_judged_anchor': True, 'mech': sr['spec']['mech'],
                'mech_key': sr['mech_key'], 'W': sr['spec']['W'],
                'N': int(sr['spec']['N']),
                'max_negative_cash': net.max_negative_cash,
                'dev': {'net_cagr': cagr(sv_n[0], sv_n[-1], sd_n[0], sd_n[-1]),
                        'gross_cagr': cagr(sv_g[0], sv_g[-1], sd_g[0], sd_g[-1]),
                        'max_drawdown': max_drawdown(sd_n, sv_n)['max_drawdown']},
            }
            run.metrics['configs'] = metrics

        # ---------------- benchmark metrics ---------------------------------
        run.metrics['benchmarks'] = {
            'B1': {key: b1_m[key] for key in b1_keys},
            'B2': {seg: {'net_total_return': b2[seg]['net_total_return'],
                         'gross_total_return': b2[seg]['gross_total_return'],
                         'entry': b2[seg]['entry_date'].isoformat(),
                         'exit': b2[seg]['exit_date'].isoformat(),
                         'fees': {'buy': b2[seg]['buy_fee'],
                                  'sell': b2[seg]['sell_fee']}}
                   for seg in b2},
            'B4_cash': 0.0,
        }

        b3_means: dict[tuple[str, int], float] = {}
        for key, n_slots in b3_combos:
            cagrs = []
            for seed in B3_SEEDS:
                r = b3[(key, n_slots, seed)]
                sd, sv = slice_curve(r.sessions, r.equity, *segs['dev'])
                cagrs.append(cagr(sv[0], sv[-1], sd[0], sd[-1]))
            mean = sum(cagrs) / len(cagrs)
            b3_means[(key, n_slots)] = mean
            # key carries N: two configs can share a mechanism key with
            # different N (e.g. C01/C04), and each gate-7 comparison uses
            # its own (mechanism, N) cell
            run.metrics[f'B3prime_{key}-N{n_slots}'] = {
                'n_slots': n_slots, 'n_seeds': len(B3_SEEDS),
                'mean_net_cagr': mean, 'min': min(cagrs), 'max': max(cagrs),
                'per_seed': {str(s): c for s, c in zip(B3_SEEDS, cagrs)}}

        # ---------------- gates ----------------------------------------------
        gates: dict[str, dict] = {}
        for cid in config_ids:
            budget_exceeded(deadline, limits)
            m = metrics[cid]
            key = sim_results[cid]['mech_key']
            n_slots = int(twelve[cid]['N'])
            b1_dev = b1_m[key]['dev']
            g = evaluate_dev_gate(
                m, {'net_cagr': b1_dev['net_cagr'],
                    'max_drawdown': b1_dev['max_drawdown']},
                b3_means[(key, n_slots)], freq='monthly')
            g['smoke_non_binding'] = args.smoke
            gates[cid] = {'dev': g}
        dev_pass = sorted(
            [(cid, gates[cid]['dev']['dev_excess_vs_b1'])
             for cid in config_ids if gates[cid]['dev']['dev_pass']],
            key=lambda kv: (-kv[1], kv[0]))
        advanced = None
        if dev_pass and not args.smoke:
            advanced = dev_pass[0][0]
            key = sim_results[advanced]['mech_key']
            b1_val = b1_m[key].get('validation')
            # adapter: evaluate_val_gate reads the 'val' key; build_metrics
            # stores the segment under 'validation' (R8 latent path: never
            # reached there because no R8 config passed dev)
            val_view = {'freq': metrics[advanced]['freq'],
                        'val': metrics[advanced]['validation']}
            gates[advanced]['validation'] = evaluate_val_gate(
                val_view, b1_val or {'net_cagr': None})
            if gates[advanced]['validation']['val_pass'] and 'test' in segs:
                gates[advanced]['test'] = evaluate_test(
                    metrics[advanced], b1_m[key]['test'])
        for cid in config_ids:
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
        run.metrics['trial_count_cumulative'] = 127 + 12
        run.metrics['stop_rule'] = ('this line gets NO further rounds tonight '
                                    'regardless of outcome (prereg section 0)')

        # ---------------- outputs --------------------------------------------
        b2_sess = [x for x in calendar
                   if segs['dev'][0] <= x <= segs['dev'][1]]
        for x, v in zip(b2_sess, b2['dev']['net_curve']):
            curves_rows.append({'config_id': 'B2-510300', 'session': x,
                                'equity_net': v, 'equity_gross': None})
        for (key, n_slots, seed), r in b3.items():
            for x, v in zip(r.sessions, r.equity):
                curves_rows.append({'config_id': f'B3-{key}-N{n_slots}-s{seed}',
                                    'session': x, 'equity_net': v,
                                    'equity_gross': None})
        pl.DataFrame(curves_rows).write_parquet(run.path / 'equity_curves.parquet')

        trades_rows = []
        for cid in all_sims:
            for t in sim_results[cid]['net'].trades:
                trades_rows.append({'config_id': cid, **t})
        for (key, n_slots, seed), r in b3.items():
            for t in r.trades:
                trades_rows.append({'config_id': f'B3-{key}-N{n_slots}-s{seed}',
                                    **t})
        pl.DataFrame(trades_rows).write_parquet(run.path / 'trades.parquet')

        pos_rows = []
        for cid in all_sims:
            for p in sim_results[cid]['net'].positions:
                pos_rows.append({'config_id': cid,
                                 **{k: v for k, v in p.items()
                                    if k != 'entry_session'}})
            for fo in sim_results[cid]['net'].final_open:
                pos_rows.append({'config_id': cid,
                                 **{k: v for k, v in fo.items()
                                    if k != 'entry_session'}})
        pl.DataFrame(pos_rows).write_parquet(run.path / 'positions.parquet')

        timings['total_s'] = round(time.perf_counter() - t_all, 2)
        run.metrics['timings'] = timings
        write_json(run.path / 'metrics.json', run.metrics)
        (run.path / 'report.md').write_text(
            build_report(config, run.metrics, args.smoke), encoding='utf-8')
        if args.smoke:
            print_smoke_verification(run.metrics, sim_results)
        print(f"dev_pass: {run.metrics['dev_pass_configs']} "
              f"advanced: {advanced} p3_candidates: {survivors}")
    return 0 if run.manifest['status'] == 'completed' else 1


def print_smoke_verification(metrics: dict, sim_results: dict) -> None:
    print('\n=== SMOKE VERIFICATION (non-binding) ===')
    print('anchors:', json.dumps(metrics['anchor_regressions']))
    for cid, sr in sim_results.items():
        net = sr['net']
        stats = net.exec_stats
        fees = sum(t['fee'] for t in net.trades)
        risk_fees = sum(t['fee'] for t in net.trades
                        if t['kind'] in RISK_KINDS)
        print(f"{cid}: trades={len(net.trades)} "
              f"risk_trades={stats.risk_buys_filled + stats.risk_sells_filled} "
              f"fees={fees:.2f} risk_fees={risk_fees:.2f} "
              f"min_cash={net.max_negative_cash:.6f} "
              f"final_equity={net.equity[-1]:.2f} "
              f"parity={sr['net_gross_parity']}")
        assert net.max_negative_cash >= 0.0, f'{cid}: NEGATIVE CASH'


def build_report(config: dict, metrics: dict, smoke: bool) -> str:
    reuse = '重用三：R6/R7/R8 已消费 dev'
    lines = ['# P2-R9 日频风控交付工程轮（换手×相对回撤×集中度；预登记策略级回放）', '',
             f"- experiment_id: {config['experiment_id']}"
             f"{'（SMOKE：1 年 × C01/C03，判据不生效）' if smoke else ''}",
             f'- dev 段为探索性（{reuse}）；种子 17；B3prime 种子 17–36；'
             '费用：佣金万1 最低5元、无印花税/过户费、滑点 0',
             '', '## 锚定回归（先于任何判据消费）', '']
    a = metrics.get('anchor_regressions', {})
    for k, v in a.items():
        lines.append(f'- {k}: {v}')
    lines += ['', '## 基准（dev）', '']
    for key, segs_m in metrics.get('benchmarks', {}).get('B1', {}).items():
        dev = segs_m.get('dev', {})
        lines.append(f"- B1({key}) dev 净年化 {fmt(dev.get('net_cagr'))}%（毛 "
                     f"{fmt(dev.get('gross_cagr'))}%），回撤 "
                     f"{fmt(dev.get('max_drawdown'))}%")
    for seg, m in metrics.get('benchmarks', {}).get('B2', {}).items():
        lines.append(f"- B2 510300 买入持有 {seg}：净 {fmt(m.get('net_total_return'))}%"
                     f"（毛 {fmt(m.get('gross_total_return'))}%）")
    for k, v in metrics.items():
        if k.startswith('B3prime_'):
            lines.append(f"- {k[8:]} N={v.get('n_slots')}（20 种子）dev 净年化均值 "
                         f"{fmt(v.get('mean_net_cagr'))}% "
                         f"[{fmt(v.get('min'))}, {fmt(v.get('max'))}]")
    lines.append('- B4 现金 0%')
    lines += ['', '## 配置结果（dev，探索性重用三）', '',
              '| 配置 | W/N | 机制 | 毛% | 净% | B1(m)净% | 净超额pp | 优势年 '
              '| 回撤% | B1(m)回撤% | 余量pp | 换手max% | top1/top3 '
              '| 风控交易 | 过x/8 | 失败判据 |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for cid in sorted(k for k in metrics.get('configs', {}) if not k.startswith('A')):
        m = metrics['configs'][cid]
        g = metrics['gates'][cid]['dev']
        dev = m['dev']
        c = dev['concentration']
        failed = [k.split('_')[0] for k, v in g.items()
                  if k[0].isdigit() and not v]
        rt = dev['risk_trades']
        top4 = (f"/t4 {fmt(c['top4_share'])}" if m['N'] == 4 else '')
        lines.append(
            f"| {cid} | {m['W_name']}/{m['N']} | {m['mech']} {m['mech_key']} "
            f"| {fmt(dev['gross_cagr'])} | {fmt(dev['net_cagr'])} "
            f"| {fmt(dev['b1m_net_cagr'])} | {fmt(dev['excess_vs_b1m'])} "
            f"| {g['positive_years']}/5 | {fmt(dev['max_drawdown'])} "
            f"| {fmt(dev['b1m_max_drawdown'])} "
            f"| {fmt(dev['dd_margin_vs_b1m_pp'])} "
            f"| {fmt(dev['max_one_side_turnover'])} "
            f"| {fmt(c['top1_share'])}/{fmt(c['top3_share'])}{top4} "
            f"| {rt['n_trades']} | {'PASS' if g['dev_pass'] else 'fail'} "
            f"| {','.join(failed) if failed else '—'} |")
    lines += ['', '## 换手分解（dev，逐年最大；选币基础 vs 风控缩放增量）', '',
              '| 配置 | 年 | 选币换手% | 风控增量% | 合计% |', '|---|---|---|---|---|']
    for cid in sorted(k for k in metrics.get('configs', {}) if not k.startswith('A')):
        td = metrics['configs'][cid]['turnover_decomposition_by_year']
        for y in sorted(td):
            v = td[y]
            lines.append(
                f"| {cid} | {y} | {fmt(v['selection_turnover'])} "
                f"| {fmt(v['risk_increment_turnover'])} "
                f"| {fmt(v['one_side_turnover'])} |")
    lines += ['', '## 相对回撤余量（策略 dd − B1(m) dd，负 = 深于基准）', '']
    for cid in sorted(k for k in metrics.get('configs', {}) if not k.startswith('A')):
        dev = metrics['configs'][cid]['dev']
        lines.append(f"- {cid}: 策略 {fmt(dev['max_drawdown'])}% vs B1(m) "
                     f"{fmt(dev['b1m_max_drawdown'])}%，余量 "
                     f"{fmt(dev['dd_margin_vs_b1m_pp'])}pp")
    lines += ['', '## 迟滞切换统计（dev；off 触发 / re-arm / 关闭占比）', '']
    for cid in sorted(k for k in metrics.get('configs', {}) if not k.startswith('A')):
        st = metrics['configs'][cid]['hysteresis_switch_stats_by_year']
        dev_years = [y for y in sorted(st) if y < '2021']
        parts = [f"{y}: {st[y]['n_off_triggers']}/{st[y]['n_rearms']}"
                 f"/{st[y]['off_share'] * 100:.0f}%" for y in dev_years]
        lines.append(f"- {cid}: " + ' | '.join(parts))
    if metrics.get('advanced_to_validation'):
        cid = metrics['advanced_to_validation']
        m = metrics['configs'][cid]
        lines += ['', f'## 存活者 {cid} 后续段', '']
        for seg in ('validation', 'test'):
            if seg in m:
                mm = m[seg]
                g = metrics['gates'][cid].get(seg, {})
                lines.append(
                    f"- {seg}: 净年化 {fmt(mm['net_cagr'])}%，B1(m) "
                    f"{fmt(mm['b1m_net_cagr'])}%，净超额 {fmt(mm['excess_vs_b1m'])}pp，"
                    f"回撤 {fmt(mm['max_drawdown'])}%，"
                    f"gate={'PASS' if g.get('val_pass') or g.get('test_pass') else 'fail'}")
    lines += ['', '## 判定', '',
              f"- dev 通过（探索性{reuse}）：{metrics.get('dev_pass_configs')}",
              f"- 进入 validation：{metrics.get('advanced_to_validation')}",
              f"- P3 候选：{metrics.get('p3_candidates')}",
              f"- 试验累计：{metrics.get('trial_count_cumulative')}",
              f"- 停机规则：{metrics.get('stop_rule')}"]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    raise SystemExit(main())
