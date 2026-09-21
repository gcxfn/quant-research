"""Pre-flight verification for exp-20260917-p2r6-etf-rotation (read-only).

Runs the three preregistered execution prerequisites BEFORE any signal code:

1. U1 whitelist: fund_basic registry rule (market='E' AND (name contains 'ETF'
   OR numeric prefix in {158,159} SZ / {51,52,53,55,56,58} SH)) crossed with
   fund_daily batch coverage (has >=1 quote row) and fund_adj batch coverage
   (has >=1 factor row; required to build the adjusted series).  The final
   code list is emitted for one-time freezing into the config snapshot.
2. amount/vol units of fund_daily (expected thousand-yuan / lots of 100
   shares; must be measured, never assumed): implied VWAP per row is
   amount_unit*1000 / (vol_lots*100), compared against the session's (H+L)/2.
3. fund_adj coverage of ETF distributions / share conversions: factor rows on
   non-quoted days, quoted days missing a factor, factor-jump events vs the
   adjusted return on the jump day (a correctly captured action keeps the
   adjusted return in normal daily bounds), plus a downgraded cross-check of
   total-window growth ratios against the tx qfqday samples.

No writes outside the JSON output path; no network; no signal generation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
BASIC = ROOT / 'data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv'
DAILY = ROOT / 'data/raw/tushare/fund_daily/20260917-r1'
ADJ = ROOT / 'data/raw/tushare/fund_adj/20260917-r1'
OUT = ROOT / 'tmp/p2r6-preflight.json'

SZ_PREFIX = ('158', '159')
SH_PREFIX = ('51', '52', '53', '55', '56', '58')


def code_prefix(ts_code: str) -> str:
    return ts_code.split('.')[0]


def u1_registry_rule(name: str, ts_code: str, market: str) -> bool:
    if market != 'E':
        return False
    if 'ETF' in name:
        return True
    p = code_prefix(ts_code)
    return (p[:3] in SZ_PREFIX) if p.startswith(('1',)) else (p[:2] in SH_PREFIX)


def main() -> int:
    basic = pl.read_csv(BASIC, infer_schema_length=0)
    codes = basic['ts_code'].to_list()
    names = basic['name'].to_list()
    markets = basic['market'].to_list()
    registry_pass = [c for c, n, m in zip(codes, names, markets)
                     if u1_registry_rule(n, c, m)]
    registry_pass_set = set(registry_pass)

    daily_files = {p.stem.removeprefix('chunk_'): p for p in DAILY.glob('chunk_*.csv')}
    adj_files = {p.stem.removeprefix('chunk_'): p for p in ADJ.glob('chunk_*.csv')}

    daily_rows: dict[str, int] = {}
    daily_span: dict[str, tuple[str, str]] = {}
    for code, path in daily_files.items():
        if code not in registry_pass_set:
            continue
        n = pl.scan_csv(path, infer_schema_length=0).select(pl.len()).collect().item()
        if n > 0:
            daily_rows[code] = n
    for code in daily_rows:
        head = pl.read_csv(daily_files[code], infer_schema_length=0, n_rows=1)
        tail = pl.read_csv(daily_files[code], infer_schema_length=0).tail(1)
        daily_span[code] = (head['trade_date'][0], tail['trade_date'][0])
    adj_rows: dict[str, int] = {}
    for code, path in adj_files.items():
        if code not in registry_pass_set:
            continue
        n = pl.scan_csv(path, infer_schema_length=0).select(pl.len()).collect().item()
        if n > 0:
            adj_rows[code] = n

    reg_only = sorted(registry_pass_set - set(daily_files))
    zero_quote = sorted(c for c in registry_pass_set
                        if c in daily_files and c not in daily_rows)
    no_adj = sorted(c for c in daily_rows if c not in adj_rows)
    whitelist = sorted(set(daily_rows) & set(adj_rows))

    b2 = daily_span.get('510300.SH')
    print(f'[1] U1 registry rule passes: {len(registry_pass)}')
    print(f'    fund_daily coverage (rows>0): {len(daily_rows)}; '
          f'registry-rule codes without any file: {len(reg_only)} {reg_only[:10]}')
    print(f'    zero-row daily files: {len(zero_quote)} {zero_quote[:10]}')
    print(f'    covered-by-daily but fund_adj empty: {len(no_adj)} {no_adj[:10]}')
    print(f'    final whitelist (daily x adj): {len(whitelist)}')
    print(f'    510300.SH span: {b2} rows={daily_rows.get("510300.SH")}')

    # ---- check 2: amount/vol units ---------------------------------------- #
    sample_codes = [c for c in ('510300.SH', '159915.SZ', '510880.SH', '512010.SH',
                                '518800.SH', '159001.SZ', '512880.SH') if c in daily_rows]
    ratios: list[float] = []
    for code in sample_codes:
        df = pl.read_csv(daily_files[code], infer_schema_length=0).slice(0, 400)
        num = (df.with_columns(
            pl.col('amount').cast(pl.Float64, strict=False),
            pl.col('vol').cast(pl.Float64, strict=False),
            pl.col('high').cast(pl.Float64, strict=False),
            pl.col('low').cast(pl.Float64, strict=False))
            .filter((pl.col('vol') > 0) & pl.col('high').is_finite()))
        implied = num.select(
            ((pl.col('amount') * 1000.0) / (pl.col('vol') * 100.0)
             / ((pl.col('high') + pl.col('low')) / 2.0)).alias('r'))['r'].drop_nulls()
        ratios.extend(implied.to_list())
    r = pl.Series(ratios)
    print(f'[2] amount[千元]/vol[手] hypothesis: implied-VWAP/(H+L)/2 median='
          f'{r.median():.4f} q10={r.quantile(0.1):.4f} q90={r.quantile(0.9):.4f} '
          f'(n={len(ratios)})')

    # ---- check 3: fund_adj coverage --------------------------------------- #
    adj_extra = 0
    missing_factor = 0
    head_null = 0
    jump_events = 0
    jump_bad = 0
    jump_examples: list[dict] = []
    jump_sizes: list[float] = []
    for code in whitelist:
        d = (pl.read_csv(daily_files[code], infer_schema_length=0)
             .select(pl.col('trade_date'), pl.col('close').cast(pl.Float64, strict=False)))
        a = (pl.read_csv(adj_files[code], infer_schema_length=0)
             .select(pl.col('trade_date'), pl.col('adj_factor').cast(pl.Float64, strict=False)))
        adj_extra += a.height - d.join(a, on='trade_date', how='semi').height
        j = (d.join(a, on='trade_date', how='left').sort('trade_date')
             .with_columns(pl.col('adj_factor').forward_fill().alias('f')))
        missing_factor += int(j['f'].is_null().sum())
        if int(j['f'].null_count()) > 0:
            head_null += 1
        if a.height < 2 or d.height < 2:
            continue
        jf = (d.join(a, on='trade_date', how='inner').sort('trade_date')
              .with_columns([
                  (pl.col('adj_factor') / pl.col('adj_factor').shift(1) - 1.0).alias('jf'),
                  (pl.col('close') / pl.col('close').shift(1) - 1.0).alias('rpct'),
                  ((pl.col('close') * pl.col('adj_factor'))
                   / (pl.col('close').shift(1) * pl.col('adj_factor').shift(1)) - 1.0).alias('apct'),
              ]).drop_nulls())
        ev = jf.filter(pl.col('jf').abs() > 0.001)
        jump_events += ev.height
        jump_sizes.extend(ev['jf'].abs().to_list())
        bad = ev.filter(pl.col('apct').abs() > 0.04)
        jump_bad += bad.height
        if bad.height and len(jump_examples) < 12:
            for row in bad.head(3).to_dicts():
                jump_examples.append({'code': code, 'trade_date': row['trade_date'],
                                      'jf': round(row['jf'], 6), 'rpct': round(row['rpct'], 6),
                                      'apct': round(row['apct'], 6)})
    print(f'[3] fund_adj rows on non-quoted days (full whitelist): {adj_extra}')
    print(f'    quoted rows missing a factor before ffill (full whitelist): {missing_factor}; '
          f'codes with any leading null: {head_null}')
    print(f'    factor-jump events (|jf|>0.1%) full whitelist: {jump_events}; '
          f'jump-day |adj ret|>4% (suspect): {jump_bad}')
    print(f'    jump size p50={pl.Series(jump_sizes).median():.4f} '
          f'p95={pl.Series(jump_sizes).quantile(0.95):.4f} '
          f'max={max(jump_sizes):.4f}' if jump_sizes else '    no jumps')
    for ex in jump_examples:
        print(f'    suspect example: {ex}')

    # tx qfq cross-check (downgraded source, growth-ratio comparison)
    tx_checks: list[dict] = []
    tx_root = ROOT / 'data/raw/tx'
    for d in sorted(tx_root.glob('sh*'))[:10]:
        code = d.name
        resp = sorted(d.glob('*/response_*.json'))
        if not resp:
            continue
        rows = []
        for rp in resp:
            payload = json.loads(rp.read_text(encoding='utf-8'))
            data = payload.get('data') or {}
            qfq = data.get(code) or {}
            rows.extend(qfq.get('qfqday') or [])
        if len(rows) < 100:
            continue
        tx = pl.DataFrame(rows, schema=['date', 'open', 'close', 'high', 'low', 'vol'],
                          orient='row')
        ts_code = code[2:] + '.SH'
        if ts_code not in whitelist:
            continue
        mine = (pl.read_csv(daily_files[ts_code], infer_schema_length=0)
                .select(pl.col('trade_date'), pl.col('close').cast(pl.Float64))
                .join(pl.read_csv(adj_files[ts_code], infer_schema_length=0)
                      .select(pl.col('trade_date'),
                              pl.col('adj_factor').cast(pl.Float64)),
                      on='trade_date', how='inner')
                .with_columns((pl.col('close') * pl.col('adj_factor')).alias('adjc')))
        tx_w = tx.with_columns(pl.col('date').str.replace_all('-', '').alias('d'),
                               pl.col('close').cast(pl.Float64))
        common = mine.join(tx_w, left_on='trade_date', right_on='d', how='inner').sort('trade_date')
        if common.height < 100:
            continue
        growth_mine = common['adjc'][-1] / common['adjc'][0]
        growth_tx = common['close_right'][-1] / common['close_right'][0]
        tx_checks.append({'code': ts_code, 'n_common': common.height,
                          'growth_mine': round(growth_mine, 6),
                          'growth_tx': round(growth_tx, 6),
                          'diff_bps': round((growth_mine / growth_tx - 1) * 1e4, 2)})
    for c in tx_checks:
        print(f'[3b] tx qfq cross-check {c}')

    out = {
        'u1_whitelist': whitelist,
        'u1_counts': {
            'registry_rule_pass': len(registry_pass), 'daily_covered': len(daily_rows),
            'registry_without_file': len(reg_only), 'zero_row_daily': len(zero_quote),
            'daily_without_adj': len(no_adj), 'whitelist': len(whitelist),
        },
        'b2_510300': {'span': b2, 'rows': daily_rows.get('510300.SH')},
        'amount_vol_units': {
            'hypothesis': 'amount in thousand CNY, vol in lots of 100 shares',
            'implied_vwap_over_midpoint_median': round(float(r.median()), 4),
            'q10': round(float(r.quantile(0.1)), 4), 'q90': round(float(r.quantile(0.9)), 4),
            'n': len(ratios),
        },
        'fund_adj': {
            'adj_rows_on_nonquoted_days_first400': adj_extra,
            'quoted_rows_missing_factor_before_ffill_first400': missing_factor,
            'codes_with_leading_null_first400': head_null,
            'factor_jump_events_full_whitelist': jump_events,
            'jump_day_abs_adj_ret_gt_4pct': jump_bad,
            'jump_size_p50': float(pl.Series(jump_sizes).median()) if jump_sizes else None,
            'jump_size_p95': float(pl.Series(jump_sizes).quantile(0.95)) if jump_sizes else None,
            'jump_size_max': max(jump_sizes) if jump_sizes else None,
            'suspect_examples': jump_examples,
            'tx_qfq_cross_check': tx_checks,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'[ok] written {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
