"""P0 end-to-end benchmark: synthetic daily data -> polars factors/signals ->
vectorbt and backtrader identical scheduled orders -> parity + timings.

Fixed pre-registered semantics: signal at close of day D, order scheduled with
decision_date=D executes at the OPEN of the first session after D, hold_days
exit sells scheduled at close D+hold_days (decision date), same execution rule.
No raw data, no frozen years, no claims of profitability.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from quant.factors import build_signals, compute_factors  # noqa: E402
from quant.research.runs import Run, write_json  # noqa: E402
from quant.research.synthetic import synthetic_daily  # noqa: E402


def schedule_orders(signals: pl.DataFrame, *, quantity: int, hold_days: int,
                    max_per_day: int) -> list:
    """Pre-fixed rule: buy next open after first signal day, sell next open
    after close of hold_days later. No parameter search."""
    from quant.backtest import Order

    by_date = {d: s for d, s in zip(signals['date'].to_list(), signals['signal'].to_list())}
    dates = signals['date'].unique().sort().to_list()
    orders: list[Order] = []
    open_until: dict[str, int] = {}
    for i, day in enumerate(dates):
        if open_until.get(day):
            for sym, left in list(open_until.items()):
                if left == 1:
                    orders.append(Order(day, sym, -quantity))
                    del open_until[sym]
                else:
                    open_until[sym] = left - 1
        if not bool(by_date.get(day)):
            continue
        picks = (signals.filter(pl.col('date') == day, pl.col('signal'))
                 .sort('volatility_20').head(max_per_day)['symbol'].to_list())
        for sym in picks:
            if sym in open_until:
                continue
            orders.append(Order(day, sym, quantity))
            exit_day = dates[min(i + hold_days, len(dates) - 1)]
            orders.append(Order(exit_day, sym, -quantity))
            open_until[sym] = hold_days
    return orders


def panel_from(df: pl.DataFrame):
    import pandas as pd
    from quant.backtest import PricePanel

    wide_open = df.pivot(on='symbol', index='date', values='open').sort('date').to_pandas()
    wide_close = df.pivot(on='symbol', index='date', values='close').sort('date').to_pandas()
    wide_open['date'] = pd.to_datetime(wide_open['date'])
    wide_close['date'] = pd.to_datetime(wide_close['date'])
    wide_open = wide_open.set_index('date').astype(float)
    wide_close = wide_close.set_index('date').astype(float)
    return PricePanel(open=wide_open, close=wide_close)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/benchmarks/p0-benchmark.json')
    parser.add_argument('--symbols', type=int, default=None, help='small smoke scale override')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    if args.symbols:
        config['universe']['synthetic_symbols'] = args.symbols

    import os
    os.chdir(ROOT)  # non-editable install: keep artifacts under the repo, not site-packages

    from quant.research.runs import find_repo_root

    with Run(find_repo_root(), config['name'], config) as run:
        timings: dict[str, float] = {}

        t0 = time.perf_counter()
        daily = synthetic_daily(symbols=config['universe']['synthetic_symbols'],
                                start=config['start'], end=config['end'], seed=config['seed'])
        timings['synthetic_generate_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        features = compute_factors(daily)
        timings['factors_cold_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        signals = build_signals(features)
        timings['signals_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        orders = schedule_orders(signals, quantity=config['orders']['order_quantity'],
                                 hold_days=config['orders']['hold_days'],
                                 max_per_day=config['orders']['daily_target_orders'])
        timings['schedule_s'] = time.perf_counter() - t0

        panel = panel_from(signals)

        from quant.backtest import BacktestConfig, compare_results, run_backtrader, run_vectorbt

        bt_config = BacktestConfig(initial_cash=config['account']['initial_cash'],
                                   commission_pct=config['orders']['commission_pct'])
        t0 = time.perf_counter()
        vbt_result = run_vectorbt(panel, orders, config=bt_config)
        timings['vectorbt_run_s'] = time.perf_counter() - t0

        t0 = time.perf_counter()
        bt_result = run_backtrader(panel, orders, config=bt_config)
        timings['backtrader_run_s'] = time.perf_counter() - t0

        parity = compare_results(vbt_result, bt_result)

        run.metrics = {'timings': timings, 'orders_scheduled': len(orders),
                       'vectorbt': vbt_result.summary(), 'backtrader': bt_result.summary(),
                       'parity': {'ok': parity.ok, 'max_abs_diff': parity.max_abs_diff,
                                  'fills_diff': len(parity.fills_diff),
                                  'cash_diff_points': len(parity.cash_diff),
                                  'positions_diff_points': len(parity.positions_diff),
                                  'equity_diff_points': len(parity.equity_diff),
                                  'messages': parity.messages}}
        perf_target = {'factor_signal_pipeline_minutes_target': 2,
                       'measured_pipeline_seconds': sum(timings[k] for k in
                                                        ('factors_cold_s', 'signals_s', 'schedule_s')),
                       'account_sample_minutes_target': 5,
                       'measured_both_frameworks_seconds': timings['vectorbt_run_s'] + timings['backtrader_run_s']}
        write_json(run.path / 'parity_summary.json', {**perf_target, 'parity_ok': parity.ok})
        print(json.dumps(run.metrics, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if run.manifest['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
