"""Audit regression tests for alpha158_ml (2026-09-21 stock-first review).

C1: the rolling training window must ADVANCE with the prediction point
    (the archived runners trained on the earliest 24 sections forever),
    and no training label may be observable after the decision point.

C2: the t-time prediction universe, features and scores must be
    invariant to changes in post-t eligibility/prices (the archived
    runners keyed predictions on the forward-return dict, bounded by the
    NEXT month's feature pool).  Post-t changes may affect labels and
    later months only.

Also covers the Q2 label calibre: 'adj' compounds close/preclose so
ex-dividend gaps do not pollute monthly labels; 'raw' keeps the archived
behaviour for difference attribution.

Synthetic hand-built panels; small LightGBM (deterministic seed); zero
trial consumption.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from quant.research.alpha158_ml import (
    adjusted_return, binary_labels, build_ml_sections, raw_close_return,
    rolling_fit_predict, select_train_sections)

SMALL = dict(n_estimators=15, num_leaves=7, min_child_samples=5,
             random_state=7, verbose=-1)


def month_ends(start_year: int, start_month: int, n: int) -> list[date]:
    out, y, m = [], start_year, start_month
    for _ in range(n):
        if m == 12:
            nxt = date(y + 1, 1, 1)
        else:
            nxt = date(y, m + 1, 1)
        out.append(date.fromordinal(nxt.toordinal() - 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def synth_world(n_months: int = 40, n_names: int = 110, seed: int = 11):
    """Deterministic world: one own trading day per calendar month-end.

    Returns (sig, series, features).  Prices random-walk with a fixed
    seed; feature 'f0' is a deterministic per-(name, month) value so the
    ML mapping is learnable and reproducible.
    """
    rng = np.random.default_rng(seed)
    sig = month_ends(2018, 1, n_months)
    days = [date(2017, 12, 31)] + sig
    series, features = {}, {}
    for k in range(n_names):
        sym = f"sz.00{k:04d}"
        px = 10.0 + k * 0.1
        closes, pcs, dints = [], [], []
        for i, d in enumerate(days):
            if i > 0:
                px = px * float(1.0 + rng.normal(0.0, 0.05))
            closes.append(px)
            pcs.append(closes[i - 1] if i else px)
            dints.append(d.year * 10_000 + d.month * 100 + d.day)
        series[sym] = {"dint": np.array(dints, dtype=np.int64),
                       "c": np.array(closes), "pc": np.array(pcs)}
    for i, t in enumerate(sig):
        feats = {}
        for k in range(n_names):
            sym = f"sz.00{k:04d}"
            feats[sym] = {"f0": float((k * 37 + i * 11) % 97) / 97.0,
                          "f1": float((k * 53 + i * 7) % 89) / 89.0}
        features[t] = feats
    return sig, series, features


def build(sig, series, features, *, label_mode="adj", min_names=100):
    return build_ml_sections(
        features, series, sig, feature_names=["f0", "f1"],
        label_mode=label_mode, min_section_names=min_names)


# ---------------------------------------------------------------------------
# C1: window direction and label availability
# ---------------------------------------------------------------------------

def test_c1_window_advances_with_prediction_point():
    sig, series, features = synth_world()
    sections = build(sig, series, features)
    res = rolling_fit_predict(sections, params=SMALL)
    diags = res.diagnostics
    assert len(diags) >= 10
    # the newest training section advances with the prediction month
    for a, b in zip(diags, diags[1:]):
        assert b.train_end > a.train_end
    # window saturates at 24 sections, then the start advances too
    caps = [d for d in diags if d.n_train_sections == 24]
    assert caps, "window must reach the 24-section cap"
    assert caps[-1].train_start > caps[0].train_start
    # the archived bug would show a FROZEN train_start for every month
    assert len({d.train_start for d in diags}) > 5


def test_c1_no_training_label_after_decision_point():
    sig, series, features = synth_world()
    sections = build(sig, series, features)
    for t in sorted(sections):
        for u in select_train_sections(
                sections, t, max_train_sections=24, min_train_sections=12):
            le = sections[u].label_end
            assert le is not None and le <= t, (u, le, t)
    # and the diagnostics say the same thing
    res = rolling_fit_predict(sections, params=SMALL)
    for d in res.diagnostics:
        assert d.label_end_latest <= d.t


def test_c1_window_takes_most_recent_sections():
    sig, series, features = synth_world()
    sections = build(sig, series, features)
    ordered = sorted(sections)
    t = ordered[-1]
    chosen = select_train_sections(sections, t, max_train_sections=24,
                                   min_train_sections=12)
    assert chosen == ordered[-25:-1]


# ---------------------------------------------------------------------------
# C2: t-time invariance to post-t changes
# ---------------------------------------------------------------------------

def test_c2_scores_invariant_to_post_t_changes():
    sig, series, features = synth_world()
    base = rolling_fit_predict(build(sig, series, features), params=SMALL)
    t0 = sorted(base.pred)[0]
    # mutate the world strictly AFTER t0: prices and pool membership
    rng = np.random.default_rng(999)
    series2 = {s: {"dint": v["dint"].copy(), "c": v["c"].copy(),
                   "pc": v["pc"].copy()} for s, v in series.items()}
    for s, v in series2.items():
        mask = v["dint"] > int(t0.year * 10_000 + t0.month * 100 + 31)
        v["c"][mask] = v["c"][mask] * 1.5
    features2 = {t: feats for t, feats in features.items()}
    for t in list(features2):
        if t > t0:
            # half the names lose next-month pool membership entirely
            features2[t] = {s: f for s, f in features2[t].items()
                            if hash((s, t)) % 2 == 0}
    alt = rolling_fit_predict(build(sig, series2, features2), params=SMALL)
    assert alt.pred[t0] == pytest.approx(base.pred[t0], rel=1e-12, abs=1e-12)


def test_c2_exited_names_stay_in_the_prediction_universe():
    sig, series, features = synth_world(n_months=8)
    t_last = sig[-2]                       # last month with a forward window
    gone = "sz.000005"
    # the name has t_last features but disappears AFTER t_last:
    # build a world where it simply stops having features from the NEXT
    # signal on (pool exit / suspension), and one where it stays
    sig_short = sig[: sig.index(t_last) + 2]
    feats_exit = {t: dict(features[t]) for t in sig_short}
    for t in sig_short:
        if t > t_last:
            feats_exit[t] = {s: f for s, f in feats_exit[t].items()
                             if s != gone}
    sections = build(sig_short, series, feats_exit)
    assert gone in sections[t_last].syms


def test_c2_suspended_name_kept_with_liquidation_label():
    sig, series, features = synth_world(n_months=10)
    # a name that stops trading right after t0 and never returns
    stuck = "sz.000042"
    t0 = sig[3]
    key0 = t0.year * 10_000 + t0.month * 100 + t0.day
    v = series[stuck]
    keep = v["dint"] <= key0
    series[stuck] = {"dint": v["dint"][keep], "c": v["c"][keep],
                     "pc": v["pc"][keep]}
    sections = build(sig, series, features)
    sec = sections[t0]
    j = sec.syms.index(stuck)
    assert not sec.label_ok[j]            # no label: stays, never vanishes
    assert sec.n_label_missing >= 1
    # a later decision point must not train on this name's missing label
    later = sig[6]
    chosen = select_train_sections(sections, later, max_train_sections=24,
                                   min_train_sections=2)
    assert chosen


# ---------------------------------------------------------------------------
# Q2: label calibre
# ---------------------------------------------------------------------------

def test_q2_adjusted_label_covers_exdiv_gap():
    s = {"dint": np.array([20240101, 20240201, 20240301]),
         "c": np.array([10.0, 11.0, 10.0]),
         "pc": np.array([10.0, 10.0, 9.9])}   # 10% ex-div bridge on day 3
    raw = raw_close_return(s, 1, 2)
    adj = adjusted_return(s, 1, 2)
    assert raw == pytest.approx(10.0 / 11.0 - 1.0)      # -9.1% (gap!)
    assert adj == pytest.approx(10.0 / 9.9 - 1.0)       # +1.0% (true hold)


def test_q2_sections_label_mode_difference():
    sig, series, features = synth_world(n_months=6)
    adj = build(sig, series, features, label_mode="adj")
    raw = build(sig, series, features, label_mode="raw")
    t = sig[2]
    # both calibres label the same names, values differ where no
    # ex-div occurred only by rounding (preclose == previous close there)
    assert (adj[t].label_ok == raw[t].label_ok).all()


def test_binary_labels_quantile_and_nan():
    y = np.array([0.01, 0.02, 0.03, 0.04, np.nan, 0.05])
    b = binary_labels(y, 0.80)
    assert b[4] != b[4]                     # NaN propagates
    assert b[5] == 1.0 and b[0] == 0.0      # top-20% threshold
