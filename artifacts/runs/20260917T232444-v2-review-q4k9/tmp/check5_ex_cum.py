# -*- coding: utf-8 -*-
"""Check 5: ex_cum_factor mapping vs tushare fund_adj + dividend jump consistency."""
import sys

import h5py
import numpy as np
import polars as pl

sys.path.insert(0, "D:/量化/artifacts/runs/20260917T232444-v2-review-q4k9/tmp")
from common import BUNDLE, RAW, oid_to_ts, result  # noqa: E402

out = {}
CHUNK_ADJ = f"{RAW}/fund_adj/20260917-r1"
CHUNK_DAILY = f"{RAW}/fund_daily/20260917-r1"

etfs = ["510880.XSHG", "510050.XSHG", "510300.XSHG"]
per = {}
with h5py.File(f"{BUNDLE}/ex_cum_factor.h5", "r") as f:
    for oid in etfs:
        ts = oid_to_ts(oid)
        rows = f[oid][:]
        adj = pl.read_csv(f"{CHUNK_ADJ}/chunk_{ts}.csv", schema_overrides={"trade_date": pl.Int64})
        adj_d = adj["trade_date"].to_numpy()
        adj_f = adj["adj_factor"].to_numpy()
        # anchor row (0, 1.0)
        anchor = rows[0]
        body = rows[1:]
        d = body["start_date"] // 10**6  # stored as 14-digit YYYYMMDDHHMMSS
        fac = body["ex_cum_factor"]
        pos = np.searchsorted(adj_d, d)
        in_bounds = pos < adj_d.size
        matched = np.zeros(d.size, dtype=bool)
        matched[in_bounds] = adj_d[pos[in_bounds]] == d[in_bounds]
        missing_dates = d[~matched].tolist()
        src = np.full(d.size, np.nan)
        src[matched] = adj_f[pos[matched]]
        ratio = np.where(matched, fac / src, np.nan)
        # also check normalization hypothesis: factor / first fund_adj factor
        norm_ratio = fac / src[0] if src.size else None
        per[oid] = {
            "anchor_row": [int(anchor["start_date"]), float(anchor["ex_cum_factor"])],
            "n_change_points": int(body.shape[0]),
            "first_rows": [[int(a), float(b)] for a, b in list(zip(body["start_date"], fac))[:3]],
            "last_rows": [[int(a), float(b)] for a, b in list(zip(body["start_date"], fac))[-3:]],
            "max_abs_ratio_minus_1": float(np.nanmax(np.abs(ratio - 1.0))) if matched.any() else None,
            "identity_holds_on_matched": bool(np.all(ratio[matched] == 1.0)) if matched.any() else None,
            "n_matched": int(matched.sum()),
            "change_dates_missing_in_fund_adj": [int(x) for x in missing_dates],
            "monotonic_nondecreasing": bool(np.all(np.diff(fac) >= 0)),
            "tushare_adj_first": float(adj_f[0]),
            "tushare_adj_last": float(adj_f[-1]),
        }
        # dividend-jump consistency at every change point
        daily = pl.read_csv(f"{CHUNK_DAILY}/chunk_{ts}.csv", schema_overrides={"trade_date": pl.Int64})
        dd = daily["trade_date"].to_numpy()
        cl = daily["close"].to_numpy()
        pre = daily["pre_close"].to_numpy()
        jumps = []
        for i in range(1, len(d)):
            d_ex = int(d[i])
            f_ex = float(fac[i])
            f_pre = float(fac[i - 1])  # effective factor on the day before ex-date
            j = int(np.searchsorted(dd, d_ex))
            if j >= dd.size or dd[j] != d_ex or j == 0:
                jumps.append({"ex_date": d_ex, "skipped": True})
                continue
            implied_div = pre[j] * (1.0 - f_pre / f_ex)
            close_drop = pre[j] - cl[j]
            tr = (cl[j] + implied_div) / pre[j] - 1.0
            jumps.append({
                "ex_date": d_ex,
                "pre_close": float(pre[j]),
                "close_ex": float(cl[j]),
                "factor_step": f_ex - f_pre,
                "implied_div_per_unit": round(float(implied_div), 4),
                "unadj_close_drop": round(float(close_drop), 4),
                "exday_total_return": round(float(tr), 4),
            })
        per[oid]["change_points_detail"] = jumps

out["per_etf"] = per

# known announced case: 510050 20161129 per-unit 0.053 (public announcement, cited in A13)
k = [x for x in per["510050.XSHG"]["change_points_detail"] if x.get("ex_date") == 20161129]
out["known_case_510050_20161129"] = k

result("check5_ex_cum_factor", out)
print(out)
