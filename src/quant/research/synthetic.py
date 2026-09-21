from __future__ import annotations

import numpy as np
import pandas as pd
import polars as pl


def synthetic_daily(symbols: int = 200, start: str = '2022-01-01', end: str = '2024-12-31', seed: int = 17) -> pl.DataFrame:
    """Synthetic weekdays are not an exchange calendar or profitability evidence."""
    dates = pd.bdate_range(start, end)
    day_values = dates.to_numpy().astype('datetime64[D]')
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(symbols):
        close = 10 * np.exp(np.cumsum(rng.normal(0, .008, len(dates))))
        opening = close * np.exp(rng.normal(0, .003, len(dates)))
        volume = rng.integers(100000, 1000000, len(dates)).astype(float)
        frames.append(pl.DataFrame({'date': day_values, 'symbol':[f'SYN{i:04d}']*len(dates),
            'open':opening, 'high':np.maximum(opening,close)*1.01,
            'low':np.minimum(opening,close)*.99, 'close':close,
            'volume':volume, 'amount':volume*close}).with_columns(pl.col('date').cast(pl.Date)))
    return pl.concat(frames)
