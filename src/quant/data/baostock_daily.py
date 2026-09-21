"""Baostock daily CSV reading with hard freeze enforcement.

Source identity: data/raw/baostock/daily/<sh|sz>.<code>.csv
Columns: date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,isST
Unadjusted (adjustflag=3), volume in shares, amount in yuan.
The files contain rows past the 2024-12-31 freeze line; every reader filters
them out here so downstream code never sees frozen dates.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import polars as pl

FREEZE_END = date(2024, 12, 31)
RAW_DAILY = Path('data/raw/baostock/daily')

SCHEMA = {
    'date': pl.Date, 'code': pl.String, 'open': pl.Float64, 'high': pl.Float64,
    'low': pl.Float64, 'close': pl.Float64, 'preclose': pl.Float64,
    'volume': pl.Float64, 'amount': pl.Float64, 'adjustflag': pl.String,
    'turn': pl.Float64, 'tradestatus': pl.Float64, 'pctChg': pl.Float64,
    'isST': pl.Float64,
}


def _repo_root() -> Path:
    from quant.research.runs import find_repo_root

    return find_repo_root()


def sample_universe(root: Path, *, size: int = 200, stride: int = 20,
                    first_row_on_or_before: date = date(2022, 1, 4),
                    last_row_on_or_after: date = FREEZE_END,
                    exclude_boards: tuple[str, ...] = ('688', '689')) -> list[str]:
    """Deterministic performance-only sample (audit 2026-09-17): sorted codes,
    first row <= 2022-01-04, last row >= 2024-12-31, fixed stride. Not
    representative returns; 2022-01-04 is the first trading day of 2022."""
    codes = sorted(p.name[:-4] for p in (root / RAW_DAILY).glob('*.csv'))
    selected: list[str] = []
    for code in codes:
        board = code.split('.', 1)[-1][:3]  # sh.688001 -> 688
        if any(board == prefix for prefix in exclude_boards):
            continue
        path = root / RAW_DAILY / f'{code}.csv'
        with path.open(encoding='utf-8') as stream:
            stream.readline()  # header
            first = stream.readline().split(',', 1)[0]
            stream.seek(0, 2)
            size_bytes = stream.tell()
            stream.seek(max(0, size_bytes - 4096))
            tail = stream.read().strip().splitlines()
            data_rows = [row for row in tail if row.split(',')[0] != 'date']
            last = data_rows[-1].split(',')[0]
        if first <= first_row_on_or_before.isoformat() and last >= last_row_on_or_after.isoformat():
            selected.append(code)
    return selected[::stride][:size]


@dataclass(frozen=True)
class DailyLoader:
    root: Path
    end: date = FREEZE_END

    def load(self, codes: list[str]) -> pl.DataFrame:
        frames = []
        for code in codes:
            path = self.root / RAW_DAILY / f'{code}.csv'
            frame = pl.read_csv(path, schema_overrides=SCHEMA, null_values=[''])
            frame = frame.filter(pl.col('date') <= self.end)
            # Factor-layer contract uses `symbol`; source column is `code`.
            frame = frame.rename({'code': 'symbol'})
            frames.append(frame)
        daily = pl.concat(frames)
        return daily.sort('symbol', 'date')


def daily_dataset_id(daily: pl.DataFrame) -> tuple[str, str]:
    """Deterministic identity for feature-cache keys: row count + content digest
    of the canonical serialization (not file mtimes). Symbols are hashed in
    sorted order so row order in the frame cannot change the identity."""
    import hashlib
    import io

    digest = hashlib.sha256()
    symbols = sorted(daily['symbol'].unique().to_list())
    for symbol in symbols:
        group = daily.filter(pl.col('symbol') == symbol).select('date', 'close').sort('date')
        digest.update(str(symbol).encode())
        digest.update(str(group.shape).encode())
        buffer = io.BytesIO()
        group.write_ipc(buffer)
        digest.update(buffer.getvalue())
    rows = str(daily.height)
    return 'baostock-daily', hashlib.sha256((rows + digest.hexdigest()).encode()).hexdigest()
