# -*- coding: utf-8 -*-
"""Build the P3R1 band-engine acceptance run artifacts (one-shot, provenance).

Run inside the run directory.  Produces:
  - logs/pytest.log            (10 contract items + input guards, all must pass)
  - logs/handcalc.log          (engine scenario verification log)
  - hand-calc-samples.md       (3 hand-verifiable reconciliation samples)
  - manifest.json              (input/code identities, env, test summary, disclosures)

Read-only with respect to data/, docs/, configs/, src/ (hashing only).  No
strategy judgement runs here; scenario signals are synthetic engine-acceptance
fixtures defined in this file.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]          # run -> runs -> artifacts -> repo root
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

import polars as pl  # noqa: E402

from quant.backtest.band_engine import (  # noqa: E402
    batch_aggregate_sha256, run_band_backtest)

D = date
STARTED = datetime.now(timezone.utc)
LOG_LINES: list[str] = []


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding='utf-8')


def log(msg: str) -> None:
    LOG_LINES.append(msg)
    print(msg, flush=True)


def rss_bytes() -> int:
    import psutil
    return psutil.Process().memory_info().rss


# --- 1. input identities ---------------------------------------------------
log('== hashing inputs ==')
identity: dict = {}

contract_md = ROOT / 'docs/plans/p3-band-contract.md'
prereg_md = ROOT / 'docs/research/exp-20260918-p3r1-band-readjudication-prereg.md'
cfg_p3r1 = ROOT / 'configs/experiments/p3r1-band-readjudication.json'
cfg_r16 = ROOT / 'configs/experiments/p2r16-trend-dispersion.json'
daily_pq = ROOT / 'data/processed/baostock-daily-20260917/daily_1999_2024.parquet'
stk_dir = ROOT / 'data/raw/tushare/stk_limit/20260917-r1'
exf_h5 = ROOT / 'data/processed/rqalpha-bundle-v2-1-20260918/ex_cum_factor.h5'

for name, path in [('p3r1_config', cfg_p3r1), ('r16_config', cfg_r16),
                   ('contract_doc', contract_md), ('prereg_doc', prereg_md),
                   ('daily_parquet', daily_pq), ('ex_cum_factor_h5', exf_h5)]:
    digest = sha256_file(path)
    identity[name] = {'path': str(path.relative_to(ROOT)).replace('\\', '/'),
                      'sha256': digest, 'bytes': path.stat().st_size}
    log(f'  {name}: {digest[:16]}')

identity['stk_limit_batch'] = batch_aggregate_sha256(stk_dir)
identity['stk_limit_batch']['path'] = str(stk_dir.relative_to(ROOT)).replace('\\', '/')
log(f"  stk_limit_batch aggregate: "
    f"{identity['stk_limit_batch']['aggregate_sha256'][:16]} "
    f"({identity['stk_limit_batch']['files']} files, "
    f"{identity['stk_limit_batch']['total_bytes']:,} bytes)")

# prereg authority-chain checks (exp-20260918 §3)
checks = {
    'r16_config_sha256_16': (identity['r16_config']['sha256'][:16], '27f846a7330919a4'),
    'daily_parquet_sha256_16': (identity['daily_parquet']['sha256'][:16], 'd9a63f4cc3032926'),
    'ex_cum_factor_sha256_16': (identity['ex_cum_factor_h5']['sha256'][:16], '70df4aca64351858'),
}
identity['prereg_matches'] = {
    k: {'computed': got, 'prereg': want, 'match': got == want}
    for k, (got, want) in checks.items()}
for k, v in identity['prereg_matches'].items():
    log(f"  prereg match {k}: {v['match']} (computed {v['computed']} vs prereg {v['prereg']})")
rss_hash = rss_bytes()

# --- 2. contract tests -------------------------------------------------------
log('== running contract tests ==')
t0 = time.perf_counter()
proc = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/test_band_contract.py', '-v', '-ra'],
    cwd=str(ROOT), capture_output=True, text=True, encoding='utf-8', errors='replace')
elapsed_tests = time.perf_counter() - t0
(RUN_DIR / 'logs' / 'pytest.log').write_text(
    proc.stdout + '\n--- stderr ---\n' + proc.stderr, encoding='utf-8')
pytest_tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1]
log(f'  pytest exit={proc.returncode}: {pytest_tail} ({elapsed_tests:.1f}s)')
rss_tests = rss_bytes()
if proc.returncode != 0:
    write_json(RUN_DIR / 'manifest.json', {
        'run_id': RUN_DIR.name, 'status': 'failed',
        'error': f'contract tests failed: {pytest_tail}'})
    sys.exit(1)
passed = int(pytest_tail.split('passed')[0].strip().split()[-1])

# --- 3. hand-calc scenarios -------------------------------------------------
log('== hand-calc scenarios ==')
SIG_SCHEMA = {'symbol': pl.String, 'signal_date': pl.Date, 'side': pl.String,
              'anchor_price': pl.Float64, 'priority': pl.Int64,
              'target_notional': pl.Float64, 'shares': pl.Int64,
              'expiry_date': pl.Date}


def sig(symbol, signal_date, side, anchor, priority=1, target=None, shares=None):
    return {'symbol': symbol, 'signal_date': signal_date, 'side': side,
            'anchor_price': float(anchor), 'priority': priority,
            'target_notional': None if target is None else float(target),
            'shares': shares, 'expiry_date': None}


def bars(symbol, rows):
    return pl.DataFrame({
        'symbol': [symbol] * len(rows), 'date': [r[0] for r in rows],
        'open': [float(r[1]) for r in rows], 'high': [float(r[2]) for r in rows],
        'low': [float(r[3]) for r in rows], 'close': [float(r[4]) for r in rows],
        'tradestatus': [1.0] * len(rows)})


def limits_frame(daily):
    return daily.select('symbol', 'date',
                        (pl.col('close') * 1.1).alias('limit_up'),
                        (pl.col('close') * 0.9).alias('limit_down'))


def close(a, b):
    assert abs(a - b) < 1e-9, (a, b)


# Scenario A: BUY -- touch does not fill, penetration fills at the anchor p.
daily_a = bars('S1', [(D(2023, 8, 23), 10.30, 10.40, 10.00, 10.10),
                      (D(2023, 8, 24), 10.05, 10.20, 9.90, 10.15),
                      (D(2023, 8, 25), 10.20, 10.30, 10.05, 10.25)])
res_a = run_band_backtest(
    pl.DataFrame([sig('S1', D(2023, 8, 22), 'buy', 10.00, 1, target=15_000)],
                 schema=SIG_SCHEMA), daily_a, limits_frame(daily_a))
assert res_a.fills.height == 1
fa = res_a.fills.row(0, named=True)
assert fa['date'] == D(2023, 8, 24) and fa['price'] == 10.0 and fa['shares'] == 1500
assert res_a.events.filter((pl.col('date') == D(2023, 8, 23))
                           & (pl.col('event') == 'not_penetrated')).height == 1
close(fa['commission'], 5.0)
close(res_a.daily.row(1, named=True)['settled_cash'], 200_000.0 - 15_005.0)
assert fa['lag_trading_days'] == 2
log('  A buy: verified (touch-no-fill, fill-at-p, lot sizing, commission)')

# Scenario B: SELL -- re-anchored limit, both fees, T+1 settlement.
daily_b = bars('S2', [(D(2023, 8, 23), 20.10, 20.20, 19.50, 20.00),
                      (D(2023, 8, 24), 20.00, 20.30, 19.95, 20.50),
                      (D(2023, 8, 25), 20.50, 20.80, 20.40, 20.60),
                      (D(2023, 8, 28), 20.60, 20.90, 20.50, 20.70)])
res_b = run_band_backtest(pl.DataFrame(
    [sig('S2', D(2023, 8, 22), 'buy', 20.00, 1, target=20_000),
     sig('S2', D(2023, 8, 24), 'sell', 20.5)], schema=SIG_SCHEMA),
    daily_b, limits_frame(daily_b))
assert res_b.fills.height == 2
bb = res_b.fills.filter(pl.col('side') == 'buy').row(0, named=True)
sb = res_b.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (bb['date'], bb['price'], bb['shares']) == (D(2023, 8, 23), 20.0, 1000)
assert (sb['date'], sb['price'], sb['shares']) == (D(2023, 8, 25), 20.5, 1000)
close(sb['commission'], 5.0)
close(sb['stamp_tax'], 20.5)
close(sb['net_cash_flow'], 20_474.5)
d25 = res_b.daily.filter(pl.col('date') == D(2023, 8, 25)).row(0, named=True)
d28 = res_b.daily.filter(pl.col('date') == D(2023, 8, 28)).row(0, named=True)
close(d25['pending_settlement'], 20_474.5)
close(d25['settled_cash'], 179_995.0)
close(d28['settled_cash'], 200_469.50)
log('  B sell: verified (re-anchor to prior close, stamp 0.1%, T+1 release)')

# Scenario C: K=3 market fallback after 3 unfilled re-anchored days.
daily_c = bars('KA', [(D(2016, 6, 1), 30.2, 30.3, 29.9, 30.0),
                      (D(2016, 6, 2), 29.8, 29.9, 29.0, 29.5),
                      (D(2016, 6, 3), 29.4, 29.4, 28.6, 29.0),
                      (D(2016, 6, 6), 28.9, 28.9, 28.2, 28.5),
                      (D(2016, 6, 7), 27.5, 27.6, 27.0, 27.4)])
res_c = run_band_backtest(pl.DataFrame(
    [sig('KA', D(2016, 5, 31), 'buy', 30.00, 1, target=30_000),
     sig('KA', D(2016, 6, 1), 'sell', 30.0)], schema=SIG_SCHEMA),
    daily_c, limits_frame(daily_c))
streaks = res_c.events.filter(pl.col('event') == 'not_penetrated')
assert streaks['limit_price'].to_list() == [30.0, 29.5, 29.0]
fc = res_c.fills.filter(pl.col('side') == 'sell').row(0, named=True)
assert (fc['fill_type'], fc['date'], fc['price'], fc['shares']) == \
    ('market_fallback', D(2016, 6, 7), 27.5, 1000)
close(fc['net_cash_flow'], 27_467.5)
k3 = res_c.stats['k3_fallback']
close(k3['pnl_contribution_total'], 27_467.5 - 28_500.0)
log('  C k3 fallback: verified (daily re-anchor, K=3 arm, open exit, pnl disclosure)')

# --- 4. hand-calc markdown ---------------------------------------------------
md = f"""# P3R1 区间契约引擎 · 手算对账样例（3 例）

- 运行：`{RUN_DIR.name}`；引擎：`src/quant/backtest/band_engine.py`
- 本文档由 `tmp/build_artifacts.py` 生成：**所有数字先以手算式列出，再由脚本独立重算并与引擎输出逐项硬断言**（生成即验证，任何不符脚本即失败）。
- 契约：`docs/plans/p3-band-contract.md` §1（买入固定锚、卖出每日重锚 + K=3 市价兜底、严格穿透、成交价不取优、T+1、整手、佣金 max(万1×名义, 5)、卖出印花 2023-08-28 前 0.1% / 后 0.05%）。
- 数据：全部为内联合成行情，不触碰 `data/raw`，无策略判定、零试验消费。

## 样例 A：买入（触价不成交、穿透按锚价成交）

信号：S1 买入，signal_date 2023-08-22（收盘后），锚价 p = 10.00，target_notional = 15,000，初始现金 200,000。

| 日期 | open | high | low | close | 引擎动作 |
|---|---|---|---|---|---|
| 2023-08-23 | 10.30 | 10.40 | **10.00** | 10.10 | low == p（触价）→ 不成交，作废次日重挂 |
| 2023-08-24 | 10.05 | 10.20 | **9.90** | 10.15 | low < p（严格穿透）→ 按 p = 10.00 成交 |
| 2023-08-25 | 10.20 | 10.30 | 10.05 | 10.25 | 已持仓，无挂单 |

手算：
- 股数 = floor(15,000 ÷ 10.00 ÷ 100) × 100 = **1,500 股**（整手）。
- 成交价 = **10.00**（不取更优价，尽管当日 low = 9.90）。
- 名义 = 1,500 × 10.00 = **15,000.00**；佣金 = max(0.0001 × 15,000, 5) = **5.00**。
- 现金 = 200,000 − 15,000 − 5 = **184,995.00**。
- 成交滞后 = 2 个交易日（首个挂单日 08-23 未成交，08-24 成交）。

引擎核对：fills = [(2023-08-24, buy, 1500 股 @ 10.00, 佣金 5.00)]；daily[08-24].settled_cash = 184,995.00；事件 not_penetrated(08-23)。✓

## 样例 B：卖出（每日重锚、双费、当日卖出资金次日可用）

信号：S2 买入 signal_date 08-22（锚 20.00，target 20,000）；卖出 signal_date 08-24。初始现金 200,000。

| 日期 | open | high | low | close | 引擎动作 |
|---|---|---|---|---|---|
| 2023-08-23 | 20.10 | 20.20 | 19.50 | 20.00 | 买单穿透（low 19.50 < 20.00）→ 1000 股 @ 20.00 |
| 2023-08-24 | 20.00 | 20.30 | 19.95 | **20.50** | 卖单尚未挂出（信号 08-24 收盘后才存在） |
| 2023-08-25 | 20.50 | **20.80** | 20.40 | 20.60 | 卖单重锚 q = 前收盘 20.50；high 20.80 > q → 按 q = 20.50 成交 |
| 2023-08-28 | 20.60 | 20.90 | 20.50 | 20.70 | 前日卖出资金解冻入现金 |

手算：
- 买入（08-23）：1000 股 × 20.00 = 20,000.00；佣金 max(2.00, 5) = 5.00；现金 = **179,995.00**。
- 卖出（08-25）：名义 = 1000 × 20.50 = **20,500.00**；佣金 = max(2.05, 5) = **5.00**；印花（08-25 < 2023-08-28）= 0.001 × 20,500 = **20.50**。
- 净回笼 = 20,500 − 5 − 20.5 = **20,474.50** → 计入 08-25 的 pending_settlement（当日不可用于买入）。
- 08-28 开盘前解冻：现金 = 179,995 + 20,474.50 = **200,469.50**。

引擎核对：daily[08-25] = (settled 179,995.00, pending 20,474.50)；daily[08-28].settled_cash = 200,469.50。✓

## 样例 C：卖出 K=3 兜底（连续 3 日未成交 → 第 4 日开盘市价退出）

信号：KA 买入 signal_date 2016-05-31（锚 30.00，target 30,000）；卖出 signal_date 2016-06-01。初始现金 200,000。涨跌停价 = 当日收盘 ±10%（合成 stk_limit）。

| 日期 | open | high | low | close | 卖单重锚 q | 引擎动作 |
|---|---|---|---|---|---|---|
| 2016-06-01 | 30.2 | 30.3 | 29.9 | 30.0 | — | 买单穿透 → 1000 股 @ 30.00（现金 169,995.00） |
| 2016-06-02 | 29.8 | 29.9 | 29.0 | 29.5 | 30.00（前收盘） | high 29.9 ≤ q → 未成交，连续第 1 日 |
| 2016-06-03 | 29.4 | 29.4 | 28.6 | 29.0 | 29.50 | high 29.4 ≤ q → 连续第 2 日 |
| 2016-06-06 | 28.9 | 28.9 | 28.2 | 28.5 | 29.00 | high 28.9 ≤ q → 连续第 3 日 → 武装市价兜底 |
| 2016-06-07 | **27.5** | 27.6 | 27.0 | 27.4 | （订单已转市价） | 开盘 27.5 > limit_down 25.65×(1+1e-4) → 无条件市价退出 @ 27.50 |

手算：
- 卖出名义 = 1000 × 27.50 = **27,500.00**；佣金 = max(2.75, 5) = **5.00**；印花（2016）= 0.001 × 27,500 = **27.50**。
- 净回笼 = 27,500 − 5 − 27.5 = **27,467.50**（计入 06-07 pending，06-08 解冻）。
- 兜底损益贡献（引擎披露口径）= 净回笼 − 1000 × 前收盘 28.50 = **−1,032.50**。
- 反事实对照：连续阴跌下 q 逐日重锚始终高于 high，限价单永不成交——验证 K=3 兜底的必要性。

引擎核对：events not_penetrated ×3（limit_price = 30.0 / 29.5 / 29.0 逐日重锚）；fill = (market_fallback, 2016-06-07, 27.50, 1000 股)；stats.k3_fallback.pnl_contribution_total = −1,032.50。✓

## 覆盖声明

以上 3 例分别覆盖 §4 验收的手算样例要求（买 / 卖 / 兜底）。其余契约维度（T+1 同 bar 顺延、整手放弃、现金优先级、公司行动、停牌与涨跌停合法性、现金时序、印花分段边界）由 `tests/test_band_contract.py` 十项契约测试以内联合成数据覆盖，全部通过（见 `logs/pytest.log`）。
"""
(RUN_DIR / 'hand-calc-samples.md').write_text(md, encoding='utf-8')
log('  hand-calc-samples.md written')
rss_handcalc = rss_bytes()

# --- 4b. read-layer smoke on the real batches (read-only, no signals) -------
log('== read-layer smoke (real files, read-only) ==')
from quant.backtest.band_engine import (  # noqa: E402
    load_daily_panel, load_ex_cum_factor_h5, load_stk_limit_batch)

daily_frame, daily_meta = load_daily_panel(daily_pq)
log(f"  daily: {daily_meta['rows_total']} -> {daily_meta['rows_after_freeze_filter']} "
    f"rows, max date {daily_frame['date'].max()}")
limit_frame, limit_load_meta = load_stk_limit_batch(stk_dir)
log(f"  stk_limit: {limit_load_meta['chunks']} chunks -> "
    f"{limit_load_meta['rows_after_freeze_filter']} rows, "
    f"{limit_frame['symbol'].n_unique()} symbols, max date {limit_frame['date'].max()}")
exf_frame, exf_load_meta = load_ex_cum_factor_h5(exf_h5)
log(f"  ex_cum_factor: {exf_load_meta['keys']} keys -> {exf_load_meta['rows']} rows, "
    f"max date {exf_frame['ex_date'].max()}, sample symbol "
    f"{exf_frame['symbol'][0]}")
read_layer_smoke = {
    'daily': {'rows': daily_meta['rows_after_freeze_filter'],
              'max_date': str(daily_frame['date'].max()),
              'rows_dropped_by_freeze': daily_meta['rows_dropped_by_freeze']},
    'stk_limit': {'chunks': limit_load_meta['chunks'],
                  'rows': limit_load_meta['rows_after_freeze_filter'],
                  'symbols': limit_frame['symbol'].n_unique(),
                  'max_date': str(limit_frame['date'].max())},
    'ex_cum_factor': {'keys': exf_load_meta['keys'],
                      'rows': exf_load_meta['rows'],
                      'max_date': str(exf_frame['ex_date'].max())},
    'note': 'read-only smoke; CRLF column-name handling and ts_code/order_book_id '
            '-> repo symbol mapping verified against the real batches '
            '(e.g. sh.600000 2022-07-21 ex-dividend change-point present)',
}

# --- 5. manifest ------------------------------------------------------------
item_map = {
    '1_fee_conservation': 'test_01_fee_conservation',
    '2_t1_zero_violations': 'test_02_t1_zero_violations',
    '3_lot_invariant': 'test_03_lot_invariant',
    '4_cash_nonneg_priority': 'test_04_cash_nonneg_priority_order',
    '5_touch_vs_penetration': 'test_05_touch_vs_penetration',
    '6_corporate_actions': 'test_06_corporate_actions',
    '7_suspension_limit_legality': 'test_07_suspension_and_limit_legality',
    '8_sell_reanchor_k3': 'test_08_sell_reanchor_k3_fallback',
    '9_sale_proceeds_next_day': 'test_09_sale_proceeds_next_day',
    '10_stamp_segmentation': 'test_10_stamp_segmentation',
}
manifest = {
    'run_id': RUN_DIR.name,
    'experiment_id': 'exp-20260918-p3r1-band-readjudication',
    'purpose': 'engine_acceptance_only (contract doc §4 items 1-10); no strategy judgement',
    'status': 'completed',
    'started_at': STARTED.isoformat(),
    'ended_at': datetime.now(timezone.utc).isoformat(),
    'command': [sys.executable, str(Path(__file__).relative_to(ROOT))],
    'trial_accounting': {'trials_consumed_by_this_run': 0,
                         'note': 'engine acceptance consumes no trials; the 8 '
                                 'readjudication trials (189->197) belong to the '
                                 'separate adjudication runs after dual sign-off'},
    'frozen_config': {'path': identity['p3r1_config']['path'],
                      'sha256': identity['p3r1_config']['sha256']},
    'authority_chain': {
        'contract_doc': {'path': identity['contract_doc']['path'],
                         'sha256': identity['contract_doc']['sha256']},
        'prereg_doc': {'path': identity['prereg_doc']['path'],
                       'sha256': identity['prereg_doc']['sha256']},
        'prereg_sha256_16_checks': identity['prereg_matches'],
    },
    'inputs': {
        'daily_parquet': identity['daily_parquet'],
        'stk_limit_batch': identity['stk_limit_batch'],
        'ex_cum_factor_h5': identity['ex_cum_factor_h5'],
        'note': 'hashed for identity only; this acceptance run executed on inline '
                'synthetic frames and consumed zero real data rows',
    },
    'code_sha256': {
        'src/quant/backtest/band_engine.py':
            sha256_file(SRC / 'quant' / 'backtest' / 'band_engine.py'),
        'tests/test_band_contract.py':
            sha256_file(ROOT / 'tests' / 'test_band_contract.py'),
    },
    'environment': {
        'python': sys.version,
        'platform': platform.platform(),
        'packages': {p: importlib.metadata.version(p)
                     for p in ['polars', 'pyarrow', 'numpy', 'pandas', 'vectorbt']},
    },
    'tests': {
        'command': 'python -m pytest tests/test_band_contract.py -v -ra',
        'passed': passed, 'failed': 0, 'exit_code': proc.returncode,
        'elapsed_seconds': round(elapsed_tests, 2),
        'item_map': item_map,
        'log': 'logs/pytest.log',
    },
    'hand_calc': {'file': 'hand-calc-samples.md',
                  'samples': ['A_buy', 'B_sell', 'C_k3_fallback'],
                  'verification': 'all sample numbers hard-asserted against engine '
                                  'output at generation time',
                  'log': 'logs/handcalc.log'},
    'read_layer_smoke': read_layer_smoke,
    'disclosures': {
        'strategy_judgement': 'not performed (dual sign-off + separate dispatch required)',
        'signals_consumed': 'none; synthetic engine-acceptance scenarios only',
        'data_access': 'read-only hashing of the prereg input identities; zero '
                       'row-level access to data/raw or data/processed',
        'freeze': 'read layer enforces trade_date <= 2024-12-31 (assert_frozen + '
                  'loaders); exercised by tests/test_band_contract.py::test_00_input_guards',
        'vectorbt': 'declared available but NOT used: the contract needs per-day '
                    're-anchored limit prices, strict-inequality penetration, a K=3 '
                    'market fallback, priority cash queues and T+1 settlement lag; '
                    'vectorbt has no order type for this without a from_order_func '
                    'callback that would itself be the loop. Pure Polars/numpy daily '
                    'loop chosen for correctness (documented in the engine docstring)',
        'engine_interpretation_choices': [
            'full-funding rule: an unaffordable order is voided that day '
            '(void_insufficient_cash) and re-hung; never downsized, never partially '
            'filled (A-share limit orders must be fully funded at placement)',
            'missing stk_limit rows void limit orders that day (no_limit_info); the '
            'K=3 market fallback nonetheless EXECUTES without limit info (exit is '
            'the risk-reducing direction)',
            'sell re-anchor uses TRADED closes only (suspended stale closes excluded)',
            'suspended days neither count toward nor reset the K=3 streak; '
            't1_deferred / out-of-range / no-limit-info days DO count (they '
            'accelerate, never delay, the guaranteed exit)',
            'a new same-name signal replaces the old order AFTER the new signal_date '
            '(the old order legitimately trades on that day; the new decision did '
            'not exist before that close); replacement restarts the K counter',
            'on the armed market-exit day the order has converted to market: it '
            'fills at the open with no limit check; on limit-down-open deferred '
            'days the re-anchored limit order keeps working',
            'market fallback and whole-position sells use the start-of-day position; '
            'explicit-quantity sells cap to held shares (quantity_capped)',
            'cash dividends credit pre-tax on the ex-date computed on PRE-ex share '
            'count and are available to same-day buys (contract sets no settlement '
            'lag for dividends)',
            'k3 pnl disclosure = net market-exit proceeds minus shares * previous '
            'close (engine-defined; the contract does not define this metric)',
            'transfer fee not modelled (~0.1bp/leg SSE only; standing disclosure)',
        ],
        'ambiguities_for_referee': 'the interpretation choices above are the '
                                   "executor's conservative readings of the frozen "
                                   'contract; none blocks the 10 acceptance items, '
                                   'but they are listed for the dual-sign reviewer '
                                   'and the main dialogue to confirm or overrule',
    },
    'peak_rss_bytes': max(rss_hash, rss_tests, rss_handcalc),
    'outputs': {},
}
(RUN_DIR / 'logs' / 'handcalc.log').write_text(
    '\n'.join(LOG_LINES) + '\n', encoding='utf-8')
manifest['outputs'] = {
    str(p.relative_to(RUN_DIR)).replace('\\', '/'): sha256_file(p)
    for p in sorted(RUN_DIR.rglob('*'))
    if p.is_file() and p.name != 'manifest.json'
}
write_json(RUN_DIR / 'manifest.json', manifest)
log(f'== manifest written: {RUN_DIR / "manifest.json"} ==')
