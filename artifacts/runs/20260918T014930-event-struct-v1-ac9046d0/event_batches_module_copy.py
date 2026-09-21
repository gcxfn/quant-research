"""Event-family raw batches -> structured event factor tables (v1).

Pure data engineering: dictionary/rule structuring of the six tushare event
batches (forecast, express, repurchase, share_float, stk_holdertrade,
disclosure_date) into the uniform event schema drafted in
docs/research/exp-20260917-event-data-scout.md section 3.

No strategy logic, no return labels, no backtest semantics.  Time contract:

* ``ts_knowledge`` = announcement day (ann_date); rows without it are
  dropped fail-closed and counted.
* ``ts_available`` = first trading day STRICTLY AFTER ``ts_knowledge``
  (closing signal is executable no earlier than next trading day).
  Knowledge before the calendar start maps to the calendar's first day
  and is counted; knowledge past the calendar end yields null (the row
  then falls outside the research freeze line and is only counted).
* Freeze line: research rows are ``ts_available <= 2024-12-31``; the rest
  are only counted, never written.

Duplicated-key policy: candidate primary keys come from the scout doc
(section 1).  Exact full-row duplicates are fetch-side dedup misses and
raise.  Candidate-key collisions whose row content differs are legitimately
distinct records (multiple campaigns / lots / successive filings); they are
kept row-for-row, counted, sampled into the manifest and disambiguated by
``event_id`` sequence -- nothing is ever silently deduplicated.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import polars as pl

DIRECTION_DICTIONARY_VERSION = 'event-direction-dict-v1'
FREEZE_END = date(2024, 12, 31)
STANDARD_CODE_RE = r'^\d{6}\.(SH|SZ)$'

# direction dictionaries (closed enums only; anything outside maps to 0)
FORECAST_DIRECTION: dict[str, int] = {
    '预增': 1, '略增': 1, '扭亏': 1, '续盈': 1,
    '预减': -1, '略减': -1, '首亏': -1, '续亏': -1,
}
HOLDERTRADE_DIRECTION: dict[str, int] = {'IN': 1, 'DE': -1}

EVENT_COLUMNS = [
    'event_id', 'event_type', 'ts_code', 'ts_event', 'ts_knowledge',
    'ts_available', 'direction', 'direction_source', 'confidence',
    'magnitude', 'raw_text', 'source_batch', 'in_pool',
]
FORECAST_EXTRA_COLUMNS = ['magnitude_max', 'summary']
SHARE_FLOAT_EXTRA_COLUMNS = ['float_share_sum', 'agg_row_count', 'agg_ann_date_count']

EVENT_SCHEMA = {
    'event_id': pl.String, 'event_type': pl.String, 'ts_code': pl.String,
    'ts_event': pl.Date, 'ts_knowledge': pl.Date, 'ts_available': pl.Date,
    'direction': pl.Int8, 'direction_source': pl.String,
    'confidence': pl.String, 'magnitude': pl.Float64, 'raw_text': pl.String,
    'source_batch': pl.String, 'in_pool': pl.Boolean,
    'magnitude_max': pl.Float64, 'summary': pl.String,
    'float_share_sum': pl.Float64, 'agg_row_count': pl.Int64,
    'agg_ann_date_count': pl.Int64,
}


# --------------------------------------------------------------------------- #
# shared primitives
# --------------------------------------------------------------------------- #
def _parse_yyyymmdd(frame: pl.DataFrame, col: str) -> pl.DataFrame:
    """String YYYYMMDD -> pl.Date; invalid strings become null."""
    return frame.with_columns(
        pl.col(col).cast(pl.String).str.strip_chars()
        .str.to_date('%Y%m%d', strict=False)
    )


def _to_float(frame: pl.DataFrame, col: str) -> pl.DataFrame:
    return frame.with_columns(pl.col(col).cast(pl.Float64, strict=False))


def load_trade_calendar(csv_path: Path) -> list[date]:
    """Trade dates from an index_daily CSV, asserted inside 2015..freeze."""
    cal = pl.read_csv(csv_path, infer_schema_length=0)
    days = (
        cal['trade_date'].str.strip_chars()
        .str.to_date('%Y%m%d', strict=False)
        .drop_nulls().sort().to_list()
    )
    if not days:
        raise ValueError(f'empty trade calendar: {csv_path}')
    if days[0].year < 2015 or days[-1] > FREEZE_END:
        raise ValueError(f'calendar outside 2015..{FREEZE_END}: {days[0]}..{days[-1]}')
    return days


def filter_standard_codes(frame: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """Keep ts_code matching ^\\d{6}\\.(SH|SZ)$; count .BJ / other rejects."""
    codes = frame['ts_code'].cast(pl.String).str.strip_chars()
    is_standard = codes.str.contains(STANDARD_CODE_RE).fill_null(False)
    is_bj = codes.str.ends_with('.BJ').fill_null(False)
    kept = frame.filter(is_standard).with_columns(pl.col('ts_code').str.strip_chars())
    stats = {
        'removed_bj': int((~is_standard & is_bj).sum()),
        'removed_nonstandard': int((~is_standard & ~is_bj).sum()),
    }
    return kept, stats


def assert_pk_unique(frame: pl.DataFrame, keys: list[str], label: str) -> dict:
    """Report candidate-key collisions; raise on exact full-row duplicates."""
    exact = frame.group_by(frame.columns).len().filter(pl.col('len') > 1)
    if exact.height:
        sample = exact.head(5).to_dicts()
        extra = int(exact['len'].sum() - exact.height)
        raise RuntimeError(
            f'{label}: {exact.height} exact duplicate row groups '
            f'({extra} extra rows), sample {sample}'
        )
    collisions = frame.group_by(keys).len().filter(pl.col('len') > 1)
    return {
        'candidate_key': keys,
        'exact_duplicate_groups': 0,
        'collision_groups': int(collisions.height),
        'collision_rows': int(collisions['len'].sum()) if collisions.height else 0,
        'collision_samples': collisions.sort('len', descending=True).head(20).to_dicts(),
    }


def compute_ts_available(frame: pl.DataFrame, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """Add ts_available = first trading day strictly after ts_knowledge.

    Knowledge before the calendar start maps to the calendar's first day
    (counted); no trading day after ts_knowledge inside the calendar yields
    null ts_available (the row is then beyond the freeze line).  Null
    ts_knowledge must be dropped before calling this.
    """
    if frame['ts_knowledge'].null_count():
        raise ValueError('null ts_knowledge reached compute_ts_available (fail-closed)')
    cal_df = pl.DataFrame({'cal_day': cal}).with_columns(pl.col('cal_day').cast(pl.Date))
    out = (
        frame.with_row_index('_row')
        .with_columns((pl.col('ts_knowledge') + timedelta(days=1)).alias('_k_next'))
        .sort('_k_next')
        .join_asof(cal_df, left_on='_k_next', right_on='cal_day', strategy='forward')
        .sort('_row')
        .drop('_row')
        .rename({'cal_day': 'ts_available'})
    )
    stats = {
        'knowledge_before_calendar_mapped_to_first_day': int(
            (frame['ts_knowledge'] < cal[0]).sum()
        ),
        'available_beyond_calendar_null': int(out['ts_available'].null_count()),
    }
    return out, stats


def assign_event_id(events: pl.DataFrame, order_by: list[str]) -> pl.DataFrame:
    """event_id = {event_type}.{ts_code}.{YYYYMMDD}.{seq}, seq 1-based within
    (ts_code, ts_event) ordered by order_by (deterministic; nulls last)."""
    return (
        events.sort(['ts_code', 'ts_event', *order_by], nulls_last=True)
        .with_columns(
            (
                pl.col('event_type') + '.' + pl.col('ts_code') + '.'
                + pl.col('ts_event').dt.strftime('%Y%m%d') + '.'
                + (pl.int_range(pl.len()).over(['ts_code', 'ts_event']) + 1).cast(pl.String)
            ).alias('event_id')
        )
    )


def split_freeze(events: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Research rows have ts_available <= FREEZE_END; the rest only count."""
    keep = events.filter(pl.col('ts_available') <= FREEZE_END)
    return keep, int(events.height - keep.height)


def flag_pool(events: pl.DataFrame, pool_codes: set[str]) -> pl.DataFrame:
    return events.with_columns(
        pl.col('ts_code').is_in(sorted(pool_codes)).cast(pl.Boolean).alias('in_pool')
    )


def _finalize(
    events: pl.DataFrame, event_type: str, source_batch: str, order_by: list[str]
) -> pl.DataFrame:
    """Add event_type/source_batch, event_id; cast and order output columns.

    Helper columns used only for event_id ordering (leading underscore) are
    dropped here.
    """
    events = events.with_columns(
        pl.lit(event_type, dtype=pl.String).alias('event_type'),
        pl.lit(source_batch, dtype=pl.String).alias('source_batch'),
    )
    events = assign_event_id(events, order_by)
    base = [c for c in EVENT_COLUMNS if c != 'in_pool']
    cols = []
    for c in base:
        if c in ('event_type', 'source_batch'):
            continue
        if c in events.columns:
            cols.append(pl.col(c).cast(EVENT_SCHEMA[c]))
        else:
            cols.append(pl.lit(None, dtype=EVENT_SCHEMA[c]).alias(c))
    events = events.with_columns(cols)
    extras = [c for c in FORECAST_EXTRA_COLUMNS + SHARE_FLOAT_EXTRA_COLUMNS
              if c in events.columns]
    return events.select(base + extras)


# --------------------------------------------------------------------------- #
# per-family builders (chunk concat -> events with ts_available + event_id)
# --------------------------------------------------------------------------- #
def build_forecast(raw: pl.DataFrame, source_batch: str, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """forecast -> event_type=forecast.

    Correction chain: one row per (ts_code, end_date) -- the earliest
    disclosed version ordered by (first_ann_date, ann_date), ann_date as
    fallback when first_ann_date is null (counted).  Versions are never
    field-merged (no first-non-null): only the single earliest row survives.
    direction from the closed `type` enum; magnitude = p_change_min (extra
    magnitude_max = p_change_max); raw_text = change_reason, extra column
    summary kept verbatim.
    """
    raw, code_stats = filter_standard_codes(raw)
    pk = assert_pk_unique(raw, ['ts_code', 'end_date', 'ann_date', 'update_flag'], 'forecast')
    raw = _parse_yyyymmdd(raw, 'ann_date')
    raw = _parse_yyyymmdd(raw, 'first_ann_date')
    fallback = int(raw['first_ann_date'].null_count())
    raw = raw.with_columns(pl.col('first_ann_date').fill_null(pl.col('ann_date')))
    raw = _parse_yyyymmdd(raw, 'end_date')

    known = raw.filter(pl.col('ann_date').is_not_null())
    fail_closed = int(raw.height - known.height)

    ordered = known.sort(
        ['ts_code', 'end_date', 'first_ann_date', 'ann_date', 'update_flag'],
        nulls_last=True,
    )
    chain = ordered.group_by(['ts_code', 'end_date'], maintain_order=True).agg(pl.all().first())
    minima = ordered.group_by(['ts_code', 'end_date']).agg(
        pl.col('first_ann_date').first().alias('_fa'),
        pl.col('ann_date').first().alias('_an'),
    )
    ties = (
        ordered.join(minima, on=['ts_code', 'end_date'])
        .filter(
            (pl.col('first_ann_date') == pl.col('_fa'))
            & (pl.col('ann_date') == pl.col('_an'))
        )
        .group_by(['ts_code', 'end_date']).len().filter(pl.col('len') > 1)
    )
    chain = chain.rename({'ann_date': 'ts_knowledge'})
    chain, ts_stats = compute_ts_available(chain, cal)

    events = chain.select(
        pl.col('ts_code'),
        pl.col('end_date').alias('ts_event'),
        pl.col('ts_knowledge'),
        pl.col('ts_available'),
        pl.col('type').fill_null('').alias('type'),
        pl.col('p_change_min').cast(pl.Float64, strict=False).alias('magnitude'),
        pl.col('p_change_max').cast(pl.Float64, strict=False).alias('magnitude_max'),
        pl.col('change_reason').cast(pl.String).alias('raw_text'),
        pl.col('summary').cast(pl.String).alias('summary'),
    ).with_columns(
        pl.col('type').replace_strict(FORECAST_DIRECTION, default=0, return_dtype=pl.Int64)
        .cast(pl.Int8).alias('direction')
    ).with_columns(
        pl.lit('field_enum', dtype=pl.String).alias('direction_source'),
        pl.lit('high', dtype=pl.String).alias('confidence'),
    ).drop('type')
    events = _finalize(events, 'forecast', source_batch, [])
    stats = {
        **code_stats,
        'pk_report': pk,
        'chain_groups': int(minima.height),
        'chain_tie_groups': int(ties.height),
        'first_ann_date_fallback_to_ann_date': fallback,
        'fail_closed_missing_knowledge_dropped': fail_closed,
        **ts_stats,
    }
    return events, stats


def build_express(raw: pl.DataFrame, source_batch: str, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """express -> event_type=express.

    direction = sign(yoy_net_profit) (derived; null/zero -> 0, counted),
    magnitude = yoy_net_profit (yuan), confidence=high.
    """
    raw, code_stats = filter_standard_codes(raw)
    pk = assert_pk_unique(raw, ['ts_code', 'end_date', 'ann_date'], 'express')
    raw = _parse_yyyymmdd(raw, 'ann_date')
    raw = _parse_yyyymmdd(raw, 'end_date')
    known = raw.filter(pl.col('ann_date').is_not_null())
    fail_closed = int(raw.height - known.height)
    known = known.rename({'ann_date': 'ts_knowledge'})
    known, ts_stats = compute_ts_available(known, cal)

    events = known.select(
        pl.col('ts_code'),
        pl.col('end_date').alias('ts_event'),
        pl.col('ts_knowledge'),
        pl.col('ts_available'),
        pl.col('yoy_net_profit').cast(pl.Float64, strict=False).alias('magnitude'),
    ).with_columns(
        pl.when(pl.col('magnitude') > 0).then(pl.lit(1, dtype=pl.Int8))
        .when(pl.col('magnitude') < 0).then(pl.lit(-1, dtype=pl.Int8))
        .otherwise(pl.lit(0, dtype=pl.Int8)).alias('direction')
    ).with_columns(
        pl.lit('derived', dtype=pl.String).alias('direction_source'),
        pl.lit('high', dtype=pl.String).alias('confidence'),
    )
    events = _finalize(events, 'express', source_batch, ['ts_knowledge'])
    stats = {
        **code_stats,
        'pk_report': pk,
        'fail_closed_missing_knowledge_dropped': fail_closed,
        'null_magnitude_rows': int(events['magnitude'].null_count()),
        'zero_magnitude_rows': int((events['magnitude'] == 0).sum()),
        **ts_stats,
    }
    return events, stats


def build_repurchase(raw: pl.DataFrame, source_batch: str, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """repurchase -> event_type=repurchase_plan (proc=预案 rows only).

    Aligned to the FIRST plan announcement (no look-ahead status use).  All
    same-day campaigns are kept row-for-row and distinguished by event_id
    seq.  direction=+1, confidence=high, magnitude null in v1.
    """
    raw, code_stats = filter_standard_codes(raw)
    pk = assert_pk_unique(raw, ['ts_code', 'ann_date', 'proc'], 'repurchase')
    raw = _parse_yyyymmdd(raw, 'ann_date')
    known = raw.filter(pl.col('ann_date').is_not_null())
    fail_closed = int(raw.height - known.height)
    plans = known.filter(pl.col('proc') == '预案')
    same_day = plans.group_by(['ts_code', 'ann_date']).len().filter(pl.col('len') > 1)
    plans = plans.rename({'ann_date': 'ts_knowledge'})
    plans, ts_stats = compute_ts_available(plans, cal)

    events = plans.select(
        pl.col('ts_code'),
        pl.col('ts_knowledge').alias('ts_event'),
        pl.col('ts_knowledge'),
        pl.col('ts_available'),
        pl.lit(None, dtype=pl.Float64).alias('magnitude'),
        pl.col('vol').cast(pl.Float64, strict=False).alias('_ord_vol'),
        pl.col('amount').cast(pl.Float64, strict=False).alias('_ord_amount'),
        pl.col('exp_date').cast(pl.String).alias('_ord_exp'),
    ).with_columns(
        pl.lit(1, dtype=pl.Int8).alias('direction'),
        pl.lit('field_enum', dtype=pl.String).alias('direction_source'),
        pl.lit('high', dtype=pl.String).alias('confidence'),
    )
    events = _finalize(
        events, 'repurchase_plan', source_batch, ['_ord_exp', '_ord_vol', '_ord_amount']
    )
    stats = {
        **code_stats,
        'pk_report': pk,
        'fail_closed_missing_knowledge_dropped': fail_closed,
        'non_plan_rows_filtered_out': int(known.height - plans.height),
        'same_day_campaign_groups_kept': int(same_day.height),
        **ts_stats,
    }
    return events, stats


def build_share_float(raw: pl.DataFrame, source_batch: str, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """share_float -> event_type=unlock, aggregated to (ts_code, float_date,
    share_type): float_share summed, float_ratio summed ("summed ratio",
    percent of total share capital); ts_knowledge = earliest ann_date in the
    group.  direction=-1 (supply pressure), confidence=medium.
    """
    raw, code_stats = filter_standard_codes(raw)
    pk = assert_pk_unique(raw, ['ts_code', 'float_date', 'holder_name', 'ann_date'], 'share_float')
    raw = _parse_yyyymmdd(raw, 'ann_date')
    raw = _parse_yyyymmdd(raw, 'float_date')
    known = raw.filter(pl.col('ann_date').is_not_null())
    fail_closed = int(raw.height - known.height)

    agg = (
        known.with_columns(
            pl.col('float_share').cast(pl.Float64, strict=False),
            pl.col('float_ratio').cast(pl.Float64, strict=False),
        )
        .group_by(['ts_code', 'float_date', 'share_type'])
        .agg(
            pl.col('float_share').sum().alias('_fs_sum'),
            pl.col('float_share').is_not_null().sum().alias('_fs_n'),
            pl.col('float_ratio').sum().alias('_fr_sum'),
            pl.col('float_ratio').is_not_null().sum().alias('_fr_n'),
            pl.col('ann_date').min().alias('ts_knowledge'),
            pl.col('ann_date').n_unique().alias('_n_ann'),
            pl.len().alias('_n_rows'),
        )
        .with_columns(
            pl.when(pl.col('_fr_n') > 0).then(pl.col('_fr_sum')).alias('magnitude'),
            pl.when(pl.col('_fs_n') > 0).then(pl.col('_fs_sum')).alias('float_share_sum'),
        )
    )
    multi_ann = agg.filter(pl.col('_n_ann') > 1)
    agg, ts_stats = compute_ts_available(agg, cal)

    events = agg.select(
        pl.col('ts_code'),
        pl.col('float_date').alias('ts_event'),
        pl.col('ts_knowledge'),
        pl.col('ts_available'),
        pl.col('magnitude'),
        pl.col('float_share_sum'),
        pl.col('_n_rows').alias('agg_row_count'),
        pl.col('_n_ann').alias('agg_ann_date_count'),
        pl.col('share_type').alias('_ord_stype'),
    ).with_columns(
        pl.lit(-1, dtype=pl.Int8).alias('direction'),
        pl.lit('field_enum', dtype=pl.String).alias('direction_source'),
        pl.lit('medium', dtype=pl.String).alias('confidence'),
    )
    events = _finalize(events, 'unlock', source_batch, ['_ord_stype'])
    stats = {
        **code_stats,
        'pk_report': pk,
        'fail_closed_missing_knowledge_dropped': fail_closed,
        'aggregated_groups': int(agg.height),
        'source_rows_aggregated': int(known.height),
        'groups_with_multiple_ann_dates': int(multi_ann.height),
        'groups_with_null_magnitude_all_ratio_null': int(events['magnitude'].null_count()),
        **ts_stats,
    }
    return events, stats


def build_holdertrade(raw: pl.DataFrame, source_batch: str, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """stk_holdertrade -> event_type=holder_trade.

    in_de IN->+1 / DE->-1 (field_enum), confidence=medium (post-hoc
    announcement, behaviour day unknown), magnitude=change_ratio (%).
    Behaviour day is absent from the batch, so ts_event = ts_knowledge =
    ann_date.  Rows with in_de outside {IN, DE} are dropped and counted.
    """
    raw, code_stats = filter_standard_codes(raw)
    pk = assert_pk_unique(
        raw, ['ts_code', 'ann_date', 'holder_name', 'in_de', 'change_vol'],
        'stk_holdertrade',
    )
    raw = _parse_yyyymmdd(raw, 'ann_date')
    known = raw.filter(pl.col('ann_date').is_not_null())
    fail_closed = int(raw.height - known.height)
    valid = known.filter(pl.col('in_de').is_in(['IN', 'DE']))
    unknown_inde = int(known.height - valid.height)
    valid = valid.rename({'ann_date': 'ts_knowledge'})
    valid, ts_stats = compute_ts_available(valid, cal)

    events = valid.select(
        pl.col('ts_code'),
        pl.col('ts_knowledge').alias('ts_event'),
        pl.col('ts_knowledge'),
        pl.col('ts_available'),
        pl.col('change_ratio').cast(pl.Float64, strict=False).alias('magnitude'),
        pl.col('in_de').fill_null('').alias('_ord_inde'),
        pl.col('holder_name').cast(pl.String).alias('_ord_holder'),
        pl.col('change_vol').cast(pl.Float64, strict=False).alias('_ord_cvol'),
    ).with_columns(
        pl.col('_ord_inde').replace_strict(HOLDERTRADE_DIRECTION, default=0, return_dtype=pl.Int64)
        .cast(pl.Int8).alias('direction')
    ).with_columns(
        pl.lit('field_enum', dtype=pl.String).alias('direction_source'),
        pl.lit('medium', dtype=pl.String).alias('confidence'),
    )
    events = _finalize(events, 'holder_trade', source_batch,
                       ['_ord_inde', '_ord_holder', '_ord_cvol'])
    stats = {
        **code_stats,
        'pk_report': pk,
        'fail_closed_missing_knowledge_dropped': fail_closed,
        'unknown_in_de_dropped': unknown_inde,
        'null_magnitude_rows': int(events['magnitude'].null_count()),
        **ts_stats,
    }
    return events, stats


def build_disclosure(raw: pl.DataFrame, source_batch: str, cal: list[date]) -> tuple[pl.DataFrame, dict]:
    """disclosure_date -> event_type=disclosure_shift.

    ts_event = pre_date (scheduled disclosure day), ts_knowledge = ann_date,
    direction=0, confidence=medium, magnitude=null.  v1 keeps the plain
    event stream; same (ts_code, end_date) revisions order into a chain by
    ann_date via the event_id seq ordering.
    """
    raw, code_stats = filter_standard_codes(raw)
    pk = assert_pk_unique(raw, ['ts_code', 'end_date', 'ann_date'], 'disclosure_date')
    raw = _parse_yyyymmdd(raw, 'ann_date')
    raw = _parse_yyyymmdd(raw, 'end_date')
    raw = _parse_yyyymmdd(raw, 'pre_date')
    known = raw.filter(pl.col('ann_date').is_not_null())
    fail_closed = int(raw.height - known.height)
    valid = known.filter(pl.col('pre_date').is_not_null())
    null_pre = int(known.height - valid.height)
    valid = valid.rename({'ann_date': 'ts_knowledge'})
    valid, ts_stats = compute_ts_available(valid, cal)

    events = valid.select(
        pl.col('ts_code'),
        pl.col('pre_date').alias('ts_event'),
        pl.col('ts_knowledge'),
        pl.col('ts_available'),
        pl.lit(None, dtype=pl.Float64).alias('magnitude'),
        pl.col('end_date').alias('_ord_end'),
    ).with_columns(
        pl.lit(0, dtype=pl.Int8).alias('direction'),
        pl.lit('field_enum', dtype=pl.String).alias('direction_source'),
        pl.lit('medium', dtype=pl.String).alias('confidence'),
    )
    events = _finalize(events, 'disclosure_shift', source_batch, ['_ord_end', 'ts_knowledge'])
    stats = {
        **code_stats,
        'pk_report': pk,
        'fail_closed_missing_knowledge_dropped': fail_closed,
        'null_pre_date_dropped': null_pre,
        **ts_stats,
    }
    return events, stats
