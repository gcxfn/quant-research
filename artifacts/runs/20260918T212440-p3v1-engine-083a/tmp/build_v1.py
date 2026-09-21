# -*- coding: utf-8 -*-
"""Build v1 run artifacts."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
SRC = ROOT / 'src'
TESTS = ROOT / 'tests'
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TESTS))

import polars as pl  # noqa: E402

import test_band_contract as t  # noqa: E402
from quant.backtest.band_engine import (  # noqa: E402
    assert_daily_halfday_bridge, load_daily_panel, load_halfday_bars,
    load_stk_limit_batch, run_band_backtest)

D = date
STARTED = datetime.now(timezone.utc)
LOG: list[str] = []


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False), encoding='utf-8')


def log(msg):
    LOG.append(str(msg))
    print(msg, flush=True)


def close(a, b):
    assert abs(a - b) < 1e-9, (a, b)


def sig(symbol, decision_date, decision_session, side, anchor, priority=1,
        *, intent=None, target=None, shares=None):
    return dict(symbol=symbol, decision_date=decision_date,
                decision_session=decision_session, side=side,
                anchor_price=float(anchor), priority=priority,
                target_notional=None if target is None else float(target),
                shares=shares, intent=intent)


def bars(symbol, rows):
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'trade_date': [r[0] for r in rows],
        'session': [r[1] for r in rows],
        'open': [float(r[2]) for r in rows], 'high': [float(r[3]) for r in rows],
        'low': [float(r[4]) for r in rows], 'close': [float(r[5]) for r in rows]})


def run(signals, half, instruments=None):
    daily = (half.group_by('symbol', 'trade_date', maintain_order=True)
                 .agg(pl.col('open').first().alias('open'),
                      pl.col('high').max().alias('high'),
                      pl.col('low').min().alias('low'),
                      pl.col('close').last().alias('close'))
                 .rename({'trade_date': 'date'}))
    limits = daily.select(
        'symbol', 'date',
        (pl.col('close') * 1.1).alias('limit_up'),
        (pl.col('close') * 0.9).alias('limit_down'))
    ins = instruments if instruments is not None else pl.DataFrame(
        schema={'symbol': pl.String, 'is_etf': pl.Boolean, 'is_t0': pl.Boolean})
    return run_band_backtest(
        pl.DataFrame(signals, schema=t.SIGNAL_SCHEMA),
        daily, half, limits, instruments=ins)


# tests
log('== contract tests ==')
proc = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/test_band_contract.py', '-q'],
    cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8',
    errors='replace')
(RUN_DIR / 'logs' / 'pytest.log').write_text(
    proc.stdout + '\n--- stderr ---\n' + proc.stderr, encoding='utf-8')
tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1]
log('  pytest: ' + tail)
if proc.returncode != 0:
    write_json(RUN_DIR / 'manifest.json',
               dict(run_id=RUN_DIR.name, status='failed', error=tail))
    sys.exit(1)
passed = int(tail.split('passed')[0].strip().split()[-1])

# hand-calc samples
log('== hand-calc samples ==')
half1 = t.bars and bars('E', [
    (date(2024, 6, 2), 'pm', 5.02, 5.04, 4.98, 5.00),
    (date(2024, 6, 3), 'am', 5.00, 5.02, 4.98, 5.00),
    (date(2024, 6, 3), 'pm', 5.00, 5.15, 4.98, 5.10),
    (date(2024, 6, 4), 'am', 5.10, 5.12, 5.05, 5.10),
    (date(2024, 6, 4), 'pm', 5.10, 5.12, 5.05, 5.10)])
res1 = run([
    sig('E', date(2024, 6, 2), 'pm', 'buy', 5.00, target=10_000),
    sig('E', date(2024, 6, 3), 'am', 'sell', 5.10, intent='risk')],
    half1, instruments=t.instruments_frame([('E', True, True)]))
eb = res1.fills.filter(pl.col('side') == 'buy').row(0, named=True)
es = res1.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (eb['date'], eb['session'], eb['shares'], eb['price']) == \
    (date(2024, 6, 3), 'am', 2000, 5.0)
assert (es['date'], es['session'], es['shares'], es['price']) == \
    (date(2024, 6, 3), 'pm', 2000, 5.10)
close(eb['stamp_tax'], 0.0)
close(es['stamp_tax'], 0.0)
d_am = res1.daily.filter(pl.col('date') == date(2024, 6, 3)).row(0, named=True)
close(d_am['settled_cash'], 189_995.0)
close(d_am['pending_next_day'], 10_195.0)
d_nxt = res1.daily.filter(pl.col('date') == date(2024, 6, 4)).row(0, named=True)
close(d_nxt['settled_cash'], 200_190.0)
log('  1 T+0 verified')

half2 = bars('F', [
    (date(2024, 3, 4), 'am', 10.02, 10.05, 9.90, 10.0),
    (date(2024, 3, 4), 'pm', 10.0, 10.15, 9.95, 10.0),
    (date(2024, 3, 5), 'am', 10.0, 10.15, 9.95, 10.05),
    (date(2024, 3, 5), 'pm', 10.0, 10.05, 9.95, 10.0)])
res2 = run([
    sig('F', date(2024, 3, 3), 'pm', 'buy', 10.0, target=10_000),
    sig('F', date(2024, 3, 4), 'pm', 'sell', 10.0, intent='risk')], half2)
s2 = res2.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (s2['date'], s2['session'], s2['price']) == \
    (date(2024, 3, 5), 'am', 10.0)
d5 = res2.daily.filter(pl.col('date') == date(2024, 3, 5)).row(0, named=True)
close(d5['pending_am_to_pm'], 9_950.0)
log('  2 session settlement verified')

half3 = bars('K', [
    (date(2016, 6, 1), 'am', 30.2, 30.25, 29.90, 30.0),
    (date(2016, 6, 1), 'pm', 30.0, 30.1, 29.95, 30.0),
    (date(2016, 6, 2), 'am', 29.8, 29.9, 29.0, 29.0),
    (date(2016, 6, 2), 'pm', 29.0, 29.4, 28.9, 29.0),
    (date(2016, 6, 3), 'am', 27.5, 27.5, 27.0, 27.4),
    (date(2016, 6, 3), 'pm', 27.5, 27.6, 27.0, 27.4)])
res3 = run([
    sig('K', date(2016, 5, 31), 'pm', 'buy', 30.0, target=30_000),
    sig('K', date(2016, 6, 1), 'pm', 'sell', 30.0, intent='risk'),
    sig('K', date(2016, 6, 2), 'am', 'sell', 29.5, intent='risk'),
    sig('K', date(2016, 6, 2), 'pm', 'sell', 29.0, intent='risk')], half3)
streaks = res3.events.filter(pl.col('event') == 'not_penetrated')
assert streaks.height == 3
kf = res3.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (kf['fill_type'], kf['date'], kf['price'], kf['shares']) == \
    ('market_fallback', date(2016, 6, 3), 'pm', 27.5, 1000)
close(kf['net_cash_flow'], 27_467.5)
close(res3.stats['k3_fallback']['pnl_contribution_total'], -1_532.5)
log('  3 K=3 verified')

half4 = bars('G', [
    (date(2017, 5, 23), 'pm', 15.9, 15.98, 15.85, 15.9),
    (date(2017, 5, 24), 'am', 15.95, 16.05, 15.85, 15.9),
    (date(2017, 5, 24), 'pm', 15.9, 16.0, 15.8, 16.0)])
d4lim = half4.select(
    'symbol', 'trade_date', pl.col('close').alias('close')).with_columns(
    (pl.col('close') * 1.1).alias('limit_up'),
    (pl.col('close') * 0.9).alias('limit_down')).rename({'trade_date': 'date'})
daily4 = (half4.group_by('symbol', 'trade_date', maintain_order=True)
              .agg(pl.col('open').first().alias('open'),
                   pl.col('high').max().alias('high'),
                   pl.col('low').min().alias('low'),
                   pl.col('close').last().alias('close'))
              .rename({'trade_date': 'date'}))
res4 = run_band_backtest(
    pl.DataFrame([
        sig('G', date(2017, 5, 22), 'pm', 'buy', 15.9, shares=1000),
        sig('G', date(2017, 5, 24), 'pm', 'sell', 15.9, intent='risk')],
        schema=t.SIGNAL_SCHEMA),
    half4.select('symbol', pl.col('trade_date').alias('date'),
                 'open', 'high', 'low', 'close'),
    half4, d4lim)
d24 = res4.daily.filter(pl.col('date') == date(2017, 5, 24)).row(0, named=True)
close(d24['positions_value'], 1000 * 16.0)
log('  4 close bridge verified (mark = official daily close 16.0)')
log('== all hand-calc samples verified ==')

print('ALL SAMPLES OK')
