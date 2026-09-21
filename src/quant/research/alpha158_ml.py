"""Rolling Alpha158 ML with the 2026-09-21 stock-first audit fixes.

C1 (rolling window direction): the archived runners selected
``ordered[:i][:24]`` -- the EARLIEST 24 sections, so the training window
never advanced.  Here training sections are filtered by label
availability first (a section enters training only when its label end
date is on/before the decision day) and the MOST RECENT
``max_train_sections`` are taken; every prediction month emits explicit
train_start / train_end / label_end_latest / sample-count diagnostics.

C2 (prediction universe depends on the future pool): the archived
runners keyed the prediction matrix on the forward-return dict, whose
keys were bounded by the NEXT month's feature pool, so a name that lost
next-month pool membership vanished from THIS month's predictions.  Here
the prediction universe at t is exactly the features computed at t (the
t-time pool); training sections and evaluation labels are separate
structures.  Labels use a liquidation caliber for suspended/delisted
names (first own close at/after the next signal day) instead of dropping
them from the cross-section.

Label adjustment (audit Q2 finding, separate from C1/C2): the archived
runners compounded RAW closes, so ex-dividend gaps polluted monthly
labels.  ``label_mode='adj'`` compounds close/preclose daily returns
(corporate actions flow through the preclose bridge) and is the
registered caliber for rebuilt baselines; ``'raw'`` reproduces the
archived behaviour for difference attribution only.

No strategy judgement lives here; parameters must be frozen in a
preregistration before any result is consumed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Mapping

import numpy as np

LOT = 100


def _dint_of(day: date) -> int:
    return day.year * 10_000 + day.month * 100 + day.day


@dataclass
class MLSection:
    """One signal month's matrices with the C2 separation baked in."""

    t: date                          # signal day (decision at its close)
    syms: list[str]                  # prediction universe: t-time features
    x: np.ndarray                    # (n, d) cross-sectionally rank-normalised
    y_cont: np.ndarray               # label value, NaN where unavailable
    label_ok: np.ndarray             # bool mask: label observable at all
    label_end: date | None           # date the section's labels complete
    n_label_missing: int             # universe names without any label


@dataclass
class PredictionDiagnostics:
    t: date
    train_start: date
    train_end: date
    label_end_latest: date           # label end of the newest train section
    n_train_sections: int
    n_train_samples: int
    n_predict: int

    def as_dict(self) -> dict:
        return {
            "t": self.t.isoformat(),
            "train_start": self.train_start.isoformat(),
            "train_end": self.train_end.isoformat(),
            "label_end_latest": self.label_end_latest.isoformat(),
            "n_train_sections": self.n_train_sections,
            "n_train_samples": self.n_train_samples,
            "n_predict": self.n_predict,
        }


def _index_on_or_before(dint: np.ndarray, key: int) -> int:
    return int(np.searchsorted(dint, key, side="right")) - 1


def _first_index_at_or_after(dint: np.ndarray, key: int) -> int | None:
    i = int(np.searchsorted(dint, key, side="left"))
    return i if i < len(dint) else None


def raw_close_return(s: Mapping[str, np.ndarray], i_from: int,
                     i_to: int) -> float:
    """Unadjusted close-to-close return (archived calibre)."""
    base = float(s["c"][i_from])
    return float(s["c"][i_to]) / base - 1.0 if base > 0 else float("nan")


def adjusted_return(s: Mapping[str, np.ndarray], i_from: int,
                    i_to: int) -> float:
    """Corporate-action-adjusted return over (i_from, i_to] via the
    close/preclose bridge (ex-dividend gaps cancel)."""
    ret = 1.0
    for i in range(i_from + 1, i_to + 1):
        pc = float(s["pc"][i])
        if pc <= 0:
            return float("nan")
        ret *= float(s["c"][i]) / pc
    return ret - 1.0


def build_ml_sections(
    features: Mapping[date, Mapping[str, Mapping]],
    series: Mapping[str, Mapping],
    sig: list[date],
    *,
    feature_names: list[str],
    label_mode: str = "adj",
    binary_quantile: float | None = None,
    min_section_names: int = 100,
) -> dict[date, MLSection]:
    """Build per-month matrices with the C1/C2-fixed semantics.

    ``features[t]``: symbol -> feature dict (computed on t-time pool
    membership and t-time history only).  ``series[sym]`` must carry
    ``dint`` (int dates), ``c`` (closes) and, for ``label_mode='adj'``,
    ``pc`` (precloses).  ``sig`` ascending.  Returns sections keyed by
    signal day; the LAST signal day gets no label (its forward window is
    outside the data) and is prediction-only.
    """
    if label_mode not in ("adj", "raw"):
        raise ValueError(f"label_mode must be 'adj'/'raw', got {label_mode!r}")
    ret_fn = adjusted_return if label_mode == "adj" else raw_close_return
    sections: dict[date, MLSection] = {}
    for i, t in enumerate(sig):
        feats = features.get(t, {})
        syms = sorted(feats)
        if len(syms) < min_section_names:
            continue
        mat = np.array([[feats[s].get(n) if feats[s].get(n) is not None
                         else 0.0 for n in feature_names] for s in syms])
        # cross-sectional rank-normalise each feature to 0..1 (archived
        # calibre preserved; the audit fixes concern time, not scaling)
        for k in range(mat.shape[1]):
            col = mat[:, k]
            order = np.argsort(np.argsort(col))
            mat[:, k] = order / max(len(col) - 1, 1)
        n = len(syms)
        y = np.full(n, np.nan)
        label_ok = np.zeros(n, dtype=bool)
        label_end: date | None = None
        if i + 1 < len(sig):
            nxt = sig[i + 1]
            for j, s in enumerate(syms):
                sr = series.get(s)
                if sr is None:
                    continue
                key = _dint_of(t)
                i_at = _index_on_or_before(sr["dint"], key)
                if i_at < 0:
                    continue
                i_lbl = _first_index_at_or_after(sr["dint"], _dint_of(nxt))
                if i_lbl is None:
                    continue          # no own close at/after the next signal
                y[j] = ret_fn(sr, i_at, i_lbl)
                label_ok[j] = np.isfinite(y[j])
                d_lbl = int(sr["dint"][i_lbl])
                end = date(d_lbl // 10_000, d_lbl // 100 % 100, d_lbl % 100)
                if label_end is None or end > label_end:
                    label_end = end
        sections[t] = MLSection(
            t=t, syms=syms, x=mat, y_cont=y, label_ok=label_ok,
            label_end=label_end, n_label_missing=int((~label_ok).sum()))
    return sections


def binary_labels(y_cont: np.ndarray, quantile: float) -> np.ndarray:
    """Per-section top-quantile binary labels (NaN labels stay NaN)."""
    finite = y_cont[np.isfinite(y_cont)]
    if finite.size == 0:
        return np.full(y_cont.shape, np.nan)
    thr = np.quantile(finite, quantile)
    return np.where(np.isfinite(y_cont),
                    (y_cont >= thr).astype(np.float64), np.nan)


def select_train_sections(sections: Mapping[date, MLSection], t: date, *,
                          max_train_sections: int,
                          min_train_sections: int) -> list[date]:
    """C1 fix: label-complete sections at the decision point, MOST RECENT
    ``max_train_sections``.  A section u qualifies when its label end date
    is on/before t (the decision is made at t's close, so a label ending
    exactly at t is observable)."""
    avail = [u for u in sorted(sections)
             if u < t
             and sections[u].label_end is not None
             and sections[u].label_end <= t]
    chosen = avail[-max_train_sections:]
    if len(chosen) < min_train_sections:
        return []
    return chosen


def spearman(x: np.ndarray, y: np.ndarray, *, min_n: int = 10) -> float | None:
    if len(x) < min_n:
        return None
    rx = np.argsort(np.argsort(x)).astype(np.float64)
    ry = np.argsort(np.argsort(y)).astype(np.float64)
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else None


DEFAULT_PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31,
                      min_child_samples=100, feature_fraction=0.8,
                      random_state=7, verbose=-1)


@dataclass
class RollingResult:
    pred: dict[date, dict[str, float]]
    ic_series: list[dict]
    diagnostics: list[PredictionDiagnostics] = field(default_factory=list)


def rolling_fit_predict(
    sections: Mapping[date, MLSection],
    *,
    objective: str = "regression",
    binary_quantile: float = 0.80,
    max_train_sections: int = 24,
    min_train_sections: int = 12,
    params: dict | None = None,
    log: Callable[[str], None] | None = None,
) -> RollingResult:
    """Walk-forward fit/predict with the C1/C2-fixed semantics.

    objective='regression' trains on continuous labels (archived runner
    alpha158 calibre); 'binary' trains on per-section top-quantile labels
    and outputs probabilities (archived runner_head_ml calibre).  In both
    cases the prediction universe is the t-time feature set and Rank IC
    is computed on continuous labels that exist.
    """
    import lightgbm as lgb

    if objective not in ("regression", "binary"):
        raise ValueError(f"objective must be regression/binary, got {objective!r}")
    say = log if log is not None else (lambda _m: None)
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)
    ordered = sorted(sections)
    pred: dict[date, dict[str, float]] = {}
    ic_series: list[dict] = []
    diags: list[PredictionDiagnostics] = []
    for t in ordered:
        train_ts = select_train_sections(
            sections, t, max_train_sections=max_train_sections,
            min_train_sections=min_train_sections)
        if not train_ts:
            say(f"{t}: skipped (no label-complete train sections)")
            continue
        sec_t = sections[t]
        xt_parts, yt_parts = [], []
        for u in train_ts:
            sec = sections[u]
            mask = sec.label_ok
            if not mask.any():
                continue
            xt_parts.append(sec.x[mask])
            if objective == "binary":
                yt_parts.append(binary_labels(sec.y_cont[mask],
                                              binary_quantile))
            else:
                yt_parts.append(sec.y_cont[mask])
        if not xt_parts:
            say(f"{t}: skipped (no labelled train samples)")
            continue
        xt = np.vstack(xt_parts)
        yt = np.concatenate(yt_parts)
        last = sections[train_ts[-1]]
        diags.append(PredictionDiagnostics(
            t=t, train_start=train_ts[0], train_end=train_ts[-1],
            label_end_latest=last.label_end,
            n_train_sections=len(train_ts), n_train_samples=int(xt.shape[0]),
            n_predict=len(sec_t.syms)))
        if objective == "binary":
            model = lgb.LGBMClassifier(objective="binary", **p)
            model.fit(xt, yt)
            score = model.predict_proba(sec_t.x)[:, 1]
        else:
            model = lgb.LGBMRegressor(objective="regression", **p)
            model.fit(xt, yt)
            score = model.predict(sec_t.x)
        pred[t] = {s: float(v) for s, v in zip(sec_t.syms, score)}
        if sec_t.label_ok.any():
            ic = spearman(score[sec_t.label_ok],
                          sec_t.y_cont[sec_t.label_ok])
            if ic is not None:
                ic_series.append({"t": str(t), "rank_ic": ic,
                                  "n_eval": int(sec_t.label_ok.sum())})
    return RollingResult(pred=pred, ic_series=ic_series, diagnostics=diags)


__all__ = [
    "MLSection", "PredictionDiagnostics", "RollingResult",
    "adjusted_return", "binary_labels", "build_ml_sections",
    "raw_close_return", "rolling_fit_predict", "select_train_sections",
    "spearman",
]
