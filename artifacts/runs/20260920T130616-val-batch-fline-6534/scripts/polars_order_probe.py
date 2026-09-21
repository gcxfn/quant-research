# -*- coding: utf-8 -*-
"""Cheap synthetic probe: is polars' sort + group_by().last() reproducible
across processes for a frame with many ties?  (D-family nondeterminism
localization helper; no project data is read.)"""
import hashlib
import sys

import numpy as np
import polars as pl

rng = np.random.default_rng(12345)
n, ng = 300_000, 3200
sym = rng.integers(0, ng, n)
sd = rng.integers(0, 71, n)
ed = sd + rng.integers(0, 4, n)
val = rng.normal(size=n)
df = pl.DataFrame({"symbol": sym, "signal_date": sd, "end_date": ed,
                   "value": val})

frozen_like = (df.sort("symbol", "signal_date", "end_date")
               .group_by("symbol").last())
ordered = (df.sort(["symbol", "signal_date", "end_date"], nulls_last=True)
           .group_by("symbol", maintain_order=True).last())
h1 = hashlib.sha256(frozen_like.sort("symbol").write_csv(None).encode()).hexdigest()
h2 = hashlib.sha256(ordered.sort("symbol").write_csv(None).encode()).hexdigest()
# value-wise comparison of the (symbol -> last value) mapping
cmp_ = frozen_like.join(ordered, on="symbol", suffix="_o")
ndiff = cmp_.filter(
    (pl.col("value") - pl.col("value_o")).abs() > 0).height
print(f"frozen_like sha {h1[:16]} | ordered sha {h2[:16]} | same={h1 == h2}")
print(f"rows {frozen_like.height}/{ordered.height}; symbol rows with a "
      f"different last value: {ndiff}")
