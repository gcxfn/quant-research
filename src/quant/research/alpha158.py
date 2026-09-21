# -*- coding: utf-8 -*-
"""Alpha158-style feature block: 158 daily price/volume features computed on
a signal-date cross-section from trailing windows (right edge = the signal
day's close; the decision happens after that close -- no leakage).

Structure (Qlib Alpha158 main layout, formulas in this file are the
authority; not byte-aligned to qlib):
  13 instant candle features
  19 rolling operators x 5 windows (5/10/20/30/60) on close/volume
  ROC family: 5 variables x 5 windows
  CORR family: 5 pairs x 5 windows
"""
from __future__ import annotations

import numpy as np
import polars as pl

WINDOWS = (5, 10, 20, 30, 60)
EPS = 1e-12


def _linfit(y: np.ndarray) -> tuple[float, float, float]:
    """slope, r2, residual(last) of y against 0..n-1."""
    n = len(y)
    x = np.arange(n, dtype=np.float64)
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx <= 0:
        return 0.0, 0.0, 0.0
    slope = ((x - xm) * (y - ym)).sum() / sxx
    fit = ym + slope * (x - xm)
    ss_res = ((y - fit) ** 2).sum()
    ss_tot = ((y - ym) ** 2).sum() + EPS
    return float(slope), float(1.0 - ss_res / ss_tot), float(y[-1] - fit[-1])


def alpha158_cross_section(window: pl.DataFrame) -> dict[str, float | None]:
    """One symbol's features from its trailing window frame (sorted by date,
    last row = signal day). Columns: date, open, high, low, close, volume,
    amount. Returns 158 features; None when the window is too short."""
    o = window["open"].to_numpy().astype(np.float64)
    h = window["high"].to_numpy().astype(np.float64)
    lo = window["low"].to_numpy().astype(np.float64)
    c = window["close"].to_numpy().astype(np.float64)
    v = window["volume"].to_numpy().astype(np.float64)
    a = window["amount"].to_numpy().astype(np.float64)
    n = len(c)
    if n < 6 or c[-1] <= 0 or v[-1] <= 0:
        return {}
    ret = np.concatenate([[0.0], c[1:] / c[:-1] - 1.0])
    f: dict[str, float | None] = {}

    def put(name: str, val):
        f[name] = None if val is None or not np.isfinite(val) else float(val)

    # --- 13 instant candle features (last row) ---
    oo, hh, ll, cc = o[-1], h[-1], lo[-1], c[-1]
    rng = hh - ll + EPS
    put("KMID", (cc - oo) / (abs(oo) + EPS))
    put("KLEN", rng / (abs(oo) + EPS))
    put("KMID2", (cc - oo) / rng)
    put("KUP", (hh - max(cc, oo)) / (abs(oo) + EPS))
    put("KUP2", (hh - max(cc, oo)) / rng)
    put("KLOW", (min(cc, oo) - ll) / (abs(oo) + EPS))
    put("KLOW2", (min(cc, oo) - ll) / rng)
    put("KSFT", (2 * cc - hh - ll) / (abs(oo) + EPS))
    put("KSFT2", (2 * cc - hh - ll) / rng)
    put("OPEN0", oo / cc)
    put("HIGH0", hh / cc)
    put("LOW0", ll / cc)
    put("VWAP0", (a[-1] / (v[-1] + EPS)) / cc)

    # --- 19 rolling operators x 5 windows ---
    for w in WINDOWS:
        if n < w:
            for name in ("ROC", "MA", "STD", "BETA", "MAX", "MIN", "QTLU",
                         "QTLD", "RANK", "RSV", "RSQ", "RESI", "CNTP",
                         "CNTN", "SUMP", "SUMN", "VMA", "VSTD", "WVMA"):
                put(f"{name}{w}", None)
            continue
        cw, vw = c[-w:], v[-w:]
        rw = ret[-w:]
        put(f"ROC{w}", cw[-1] / (cw[0] + EPS) - 1.0)
        put(f"MA{w}", cw.mean() / (cw[-1] + EPS) - 1.0)
        put(f"STD{w}", cw.std() / (cw[-1] + EPS))
        slope, r2, resi = _linfit(cw)
        put(f"BETA{w}", slope / (cw.mean() + EPS))
        put(f"MAX{w}", cw.max() / (cw[-1] + EPS) - 1.0)
        put(f"MIN{w}", cw.min() / (cw[-1] + EPS) - 1.0)
        put(f"QTLU{w}", np.quantile(cw, 0.8) / (cw[-1] + EPS))
        put(f"QTLD{w}", np.quantile(cw, 0.2) / (cw[-1] + EPS))
        rank = (cw < cw[-1]).mean()
        put(f"RANK{w}", rank)
        rng_w = cw.max() - cw.min() + EPS
        put(f"RSV{w}", (cw[-1] - cw.min()) / rng_w)
        put(f"RSQ{w}", r2)
        put(f"RESI{w}", resi / (cw[-1] + EPS))
        sgn = np.sign(rw)
        put(f"CNTP{w}", (sgn > 0).mean())
        put(f"CNTN{w}", (sgn < 0).mean())
        pos = rw[rw > 0].sum()
        neg = -rw[rw < 0].sum()
        tot = pos + neg + EPS
        put(f"SUMP{w}", pos / tot)
        put(f"SUMN{w}", neg / tot)
        put(f"VMA{w}", vw.mean() / (vw[-1] + EPS))
        put(f"VSTD{w}", vw.std() / (vw[-1] + EPS))
        pv = rw * vw
        put(f"WVMA{w}", pv.std() / (np.abs(pv).mean() + EPS))

    # --- ROC family: 5 variables x 5 windows ---
    for tag, arr in (("OPN", o), ("HIH", h), ("LOL", lo), ("VOL", v),
                     ("CLS", c)):
        for w in WINDOWS:
            if n >= w:
                put(f"ROC{tag}{w}", arr[-1] / (arr[-w] + EPS) - 1.0)
            else:
                put(f"ROC{tag}{w}", None)

    # --- CORR family: 5 pairs x 5 windows ---
    pairs = (("CV", c, v), ("CA", c, np.abs(ret) * v), ("RV", ret, v),
             ("HV", h, v), ("LV", lo, v))
    for tag, x, y in pairs:
        for w in WINDOWS:
            if n >= w + 1:
                xw, yw = x[-w:], y[-w:]
                if xw.std() > 0 and yw.std() > 0:
                    put(f"COR{tag}{w}",
                        float(np.corrcoef(xw, yw)[0, 1]))
                else:
                    put(f"COR{tag}{w}", None)
            else:
                put(f"COR{tag}{w}", None)
    return f


N_FEATURES = (13 + 19 * len(WINDOWS) + 5 * len(WINDOWS) + 5 * len(WINDOWS))
assert N_FEATURES == 158, N_FEATURES
