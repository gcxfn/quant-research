# -*- coding: utf-8 -*-
"""Phase-B signal library tests (prereg stock_event_research_prereg).

All cases are hand-computed synthetic samples -- no market data, no
network, no LightGBM.  They pin the frozen interpretive choices recorded
in event_family_signals.__doc__.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from quant.research.event_family_signals import (  # noqa: E402
    BEvent, B_HOLD_SESSIONS, CHASE, ENTRY_TTL_SESSIONS, FamilyParams,
    IMPROVE_CODES, MAX_SEATS, SymbolSeries, TriggerEvent,
    EventFamilyProvider, _attack_entries_allowed, _roll_max_prior,
    _roll_mean, _roll_mean_prior, a_family_eligibility,
    b1_revision_events, b2_announcement_events, make_delayed_provider,
    random_month_picks, scan_a_triggers)


def _biz_dates(start: date, n: int) -> list[date]:
    """Mon-Fri session dates from start."""
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


# --- rolling helpers ---------------------------------------------------------

def test_roll_helpers_math():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    m = _roll_mean(a, 3)
    assert np.isnan(m[1]) and m[2] == 2.0 and m[4] == 4.0
    mp = _roll_mean_prior(a, 2)
    assert np.isnan(mp[1]) and mp[2] == 1.5 and mp[4] == 3.5
    xp = _roll_max_prior(a, 2)
    assert np.isnan(xp[1]) and xp[2] == 2.0 and xp[4] == 4.0


def test_series_ret60_and_atr_ratio():
    n = 130
    d = _biz_dates(date(2015, 1, 1), n)
    close = np.linspace(10.0, 13.0, n)
    high = close + 0.1
    low = close - 0.1
    vol = np.full(n, 1e6)
    ser = SymbolSeries("sz.000001", d, close, high, low, vol)
    # ret60 at i: close[i]/close[i-60] - 1
    assert ser.ret60[60] == pytest.approx(close[60] / close[0] - 1.0)
    # constant TR = 0.2 -> atr10/atr60 == 1 (never eligible for vc<=0.7)
    assert ser.atr10[60] == pytest.approx(0.2)
    assert ser.atr60[60] == pytest.approx(0.2)
    assert ser.idx_lt(d[60]) == 59 and ser.idx_le(d[60]) == 60


# --- A eligibility -----------------------------------------------------------

def _mk_series(symbol: str, d, closes, vols=None, daily_range=0.05):
    closes = np.asarray(closes, dtype=float)
    high = closes * (1 + daily_range)
    low = closes * (1 - daily_range)
    vols = np.asarray(vols, dtype=float) if vols is not None \
        else np.full(len(closes), 1e6)
    return SymbolSeries(symbol, d, closes, high, low, vols)


def test_eligibility_quantile_and_vc():
    n = 130
    d = _biz_dates(date(2015, 1, 1), n)
    # s1: strong + CONTRACTED (recent range 0.2%, past 5%); s2: weak + wide
    rng1 = np.concatenate([np.full(n - 10, 0.05), np.full(10, 0.002)])
    rng2 = np.full(n, 0.09)
    s1 = _mk_series("sz.1", d, np.linspace(10, 20, n), daily_range=rng1)
    s2 = _mk_series("sz.2", d, np.linspace(10, 8, n), daily_range=rng2)
    p = FamilyParams("A1")
    elig, st = a_family_eligibility(["sz.1", "sz.2"], {"sz.1": s1, "sz.2": s2},
                                    d[-1], p)
    # s2: negative ret60 AND atr10/atr60 = 1 -> excluded both ways
    assert "sz.1" in elig and "sz.2" not in elig
    assert st["n_elig"] == 1
    # ablation: drop the rel-strength leg; s2 still fails vol contraction
    p_nors = FamilyParams("A1", use_rs_filter=False)
    elig2, _ = a_family_eligibility(["sz.1", "sz.2"],
                                    {"sz.1": s1, "sz.2": s2}, d[-1], p_nors)
    assert "sz.2" not in elig2 and "sz.1" in elig2


# --- A1 / A2 triggers --------------------------------------------------------

def test_a1_breakout_trigger_and_monthly_dedupe():
    n = 200
    d = _biz_dates(date(2015, 1, 1), n)
    closes = np.full(n, 10.0)
    # walk up so every day closes above the prior-60 max, volume expands
    closes[120:] = np.linspace(10.0, 13.0, n - 120)
    vol = np.full(n, 1e6)
    vol[120:] = 2e6
    ser = _mk_series("sz.1", d, closes, vols=vol, daily_range=0.01)
    # month ends inside the sample
    me = [d[130], d[150]]
    pools = [(me[0], ["sz.1"]), (me[1], ["sz.1"])]
    atr = lambda s, dd: 0.2  # noqa: E731
    # eligibility at d[130]: ret60 positive, atr ratio 1.0 -> NOT eligible
    # (constant range).  Relax vc to pass eligibility via params.
    p = FamilyParams("A1", vc_ratio=1.10)
    evs = scan_a_triggers(pools, {"sz.1": ser}, atr, p)
    # one trigger per month window (first eligible breakout wins); the
    # sample has two windows -> at most one trigger in each
    trig = [e for e in evs if e.family == "A1"]
    assert len(trig) == 2
    assert me[0] < trig[0].trigger_day <= me[1]
    assert trig[1].trigger_day > me[1]
    assert trig[0].cap_price == pytest.approx(
        ser.close[ser.idx_of(trig[0].trigger_day)] * (1 + CHASE))
    assert trig[0].cancel_level < trig[0].cap_price / (1 + CHASE)


def test_a2_pullback_state_machine():
    n = 220
    d = _biz_dates(date(2015, 1, 1), n)
    closes = np.full(n, 10.0)
    # breakout at index 130 (first day of the ramp above prior-60 max)
    closes[130] = 12.0
    # pullback days 131..134 into the band [12-atr, 12+atr] above MA20
    closes[131:135] = [11.5, 11.3, 11.4, 11.6]
    # reclaim above the breakout level on day 135
    closes[135] = 12.2
    vol = np.full(n, 1e6)
    vol[130] = 2e6
    ser = _mk_series("sz.1", d, closes, vols=vol, daily_range=0.01)
    me = [d[120], d[160]]
    pools = [(me[0], ["sz.1"]), (me[1], ["sz.1"])]
    atr = lambda s, dd: 0.4  # noqa: E731  -> band [11.6, 12.4]
    p = FamilyParams("A2", vc_ratio=1.10)
    evs = scan_a_triggers(pools, {"sz.1": ser}, atr, p)
    assert [e.trigger_day for e in evs] == [d[135]]
    assert evs[0].family == "A2" and evs[0].cancel_below_ma

    # MA break during the pullback invalidates: day-131 close far below
    # the MA20 (which sits near 9.1 given the surrounding 10.0 closes)
    closes2 = closes.copy()
    closes2[131] = 8.5
    ser2 = _mk_series("sz.1", d, closes2, vols=vol, daily_range=0.01)
    evs2 = scan_a_triggers(pools, {"sz.1": ser2}, atr, p)
    assert evs2 == []


def test_random_picks_deterministic_and_capped():
    d = _biz_dates(date(2015, 1, 1), 40)
    me = [d[10], d[20], d[30]]
    pools = [(t, ["sz.a", "sz.b", "sz.c", "sz.d", "sz.e"]) for t in me]
    e1 = random_month_picks(pools, seed=11)
    e2 = random_month_picks(pools, seed=11)
    assert [(e.symbol, e.trigger_day) for e in e1] == \
        [(e.symbol, e.trigger_day) for e in e2]
    assert all(e.family == "RND" for e in e1)
    per_month = {}
    for e in e1:
        per_month[e.trigger_day] = per_month.get(e.trigger_day, 0) + 1
    assert all(v <= MAX_SEATS for v in per_month.values())


# --- B1 ----------------------------------------------------------------------

def _b1_rows():
    return [
        {"symbol": "sz.1", "end_date": "20200331", "ann_date": "20200120",
         "update_flag": "0", "type": "预减", "net_profit_min": 100.0,
         "net_profit_max": 200.0},
        {"symbol": "sz.1", "end_date": "20200331", "ann_date": "20200210",
         "update_flag": "1", "type": "略增", "net_profit_min": 180.0,
         "net_profit_max": 260.0},
        # type NOT improved and median DOWN -> no event
        {"symbol": "sz.2", "end_date": "20200331", "ann_date": "20200121",
         "update_flag": "0", "type": "预增", "net_profit_min": 500.0,
         "net_profit_max": 600.0},
        {"symbol": "sz.2", "end_date": "20200331", "ann_date": "20200211",
         "update_flag": "1", "type": "预增", "net_profit_min": 400.0,
         "net_profit_max": 550.0},
        # same-day pair -> never fires
        {"symbol": "sz.3", "end_date": "20200331", "ann_date": "20200122",
         "update_flag": "0", "type": "首亏", "net_profit_min": None,
         "net_profit_max": None},
        {"symbol": "sz.3", "end_date": "20200331", "ann_date": "20200122",
         "update_flag": "1", "type": "扭亏", "net_profit_min": None,
         "net_profit_max": None},
    ]


def test_b1_revision_detection():
    pool_ok = lambda s, d: True  # noqa: E731
    tda = lambda d: d + timedelta(days=1)  # noqa: E731
    evs = b1_revision_events(_b1_rows(), {}, pool_ok, tda,
                             FamilyParams("B1"))
    # sz.1: type 预减->略增 improves AND median 150->220 up, floor up: fires
    assert [(e.symbol, e.decision_day, e.decision_sess) for e in evs] == \
        [("sz.1", date(2020, 2, 11), "am")]
    # sz.2: same type, median down -> nothing; sz.3 same-day -> nothing

    # floor perturbation: sz.1 floor 100->180 rises, still fires; craft a
    # median-up/floor-flat case that only the main config accepts
    rows = _b1_rows() + [
        {"symbol": "sz.4", "end_date": "20200630", "ann_date": "20200401",
         "update_flag": "0", "type": "略增", "net_profit_min": 100.0,
         "net_profit_max": 200.0},
        {"symbol": "sz.4", "end_date": "20200630", "ann_date": "20200420",
         "update_flag": "1", "type": "略增", "net_profit_min": 100.0,
         "net_profit_max": 300.0}]
    evs_main = b1_revision_events(rows, {}, pool_ok, tda, FamilyParams("B1"))
    evs_strict = b1_revision_events(rows, {}, pool_ok, tda,
                                    FamilyParams("B1", b1_floor_must_rise=True))
    syms_main = {e.symbol for e in evs_main}
    syms_strict = {e.symbol for e in evs_strict}
    assert "sz.4" in syms_main and "sz.4" not in syms_strict


def test_b1_cooldown_skips_repeat_revisions():
    rows = [
        {"symbol": "sz.1", "end_date": "20200331", "ann_date": "20200210",
         "update_flag": "0", "type": "预减", "net_profit_min": 100.0,
         "net_profit_max": 200.0},
        {"symbol": "sz.1", "end_date": "20200331", "ann_date": "20200214",
         "update_flag": "1", "type": "略增", "net_profit_min": 150.0,
         "net_profit_max": 260.0},
        {"symbol": "sz.1", "end_date": "20200331", "ann_date": "20200220",
         "update_flag": "1", "type": "预增", "net_profit_min": 200.0,
         "net_profit_max": 300.0},
    ]
    d = _biz_dates(date(2020, 1, 1), 60)
    ser = _mk_series("sz.1", d, np.linspace(10, 12, 60), daily_range=0.02)
    pool_ok = lambda s, dd: True  # noqa: E731
    tda = lambda dd: dd + timedelta(days=1)  # noqa: E731
    evs_plain = b1_revision_events(rows, {"sz.1": ser}, pool_ok, tda,
                                   FamilyParams("B1"))
    assert len(evs_plain) == 2
    evs_cool = b1_revision_events(rows, {"sz.1": ser}, pool_ok, tda,
                                  FamilyParams("B1", b1_cooldown=20))
    assert [e.ann_date for e in evs_cool] == [date(2020, 2, 14)]


# --- B2 ----------------------------------------------------------------------

def test_b2_confirmation_vs_pool_median():
    d = _biz_dates(date(2019, 6, 3), 60)
    ann_i = 10

    def _flat(peak=None):
        c = np.full(len(d), 10.0)
        if peak is not None:
            c[ann_i + 5] = peak
        return c

    ser = _mk_series("sz.1", d, _flat(12.0), daily_range=0.01)
    peers = {f"sz.p{i}": _mk_series(f"sz.p{i}", d, _flat(10.5),
                                    daily_range=0.01)
             for i in range(25)}
    series = {"sz.1": ser, **peers}
    rows = [{"symbol": "sz.1", "ann_date": d[ann_i].strftime("%Y%m%d"),
             "type": "预增", "primary_code": "demand_up"}]
    me = [d[0], d[40]]
    pools = [(me[0], ["sz.1"] + list(peers)), (me[1], ["sz.1"] + list(peers))]
    pool_ok = lambda s, dd: s == "sz.1"  # noqa: E731
    p = FamilyParams("B2")
    evs = b2_announcement_events(rows, series, pools, pool_ok, p)
    assert len(evs) == 1
    assert evs[0].decision_day == d[ann_i + 5] and evs[0].decision_sess == "pm"
    # attribution outside IMPROVE_CODES -> dropped
    rows_bad = [dict(rows[0], primary_code="cost_up")]
    assert b2_announcement_events(rows_bad, series, pools, pool_ok, p) == []
    # ablation: no confirmation -> decision the first session after ann
    p_nc = FamilyParams("B2", use_price_confirm=False)
    evs_nc = b2_announcement_events(rows, series, pools, pool_ok, p_nc)
    assert evs_nc[0].decision_day == d[ann_i + 1]
    # B2(2): narrowing the type set to {预增} drops 扭亏 announcements
    assert b2_announcement_events(
        [dict(rows[0], type="扭亏")], series, pools, pool_ok,
        FamilyParams("B2", b2_types=("预增",))) == []


# --- provider ----------------------------------------------------------------

class _FakeStep:
    def __init__(self, rows=(), risk_state="normal", target_weight=0.10):
        self.rows = list(rows)
        self.risk_state = risk_state
        self.target_weight = target_weight


class _FakeHost:
    def __init__(self, step=None):
        self.step_obj = step or _FakeStep()

    def step(self, ledger, **kw):
        return self.step_obj


class _FakeSNR:
    def __init__(self):
        self.calls = 0

    def decide(self, positions, prices, *, day, session):
        self.calls += 1
        return []


def _provider(events, series, sess_idx, *, risk_state="normal",
              is_b=False, price_map=None):
    p = FamilyParams("B1") if is_b else FamilyParams("A1")
    prices = price_map or {}
    price_at = lambda s, d, ss: prices.get((s, d, ss))  # noqa: E731
    host = _FakeHost(_FakeStep(risk_state=risk_state))
    prov = EventFamilyProvider(p, events, series, host, _FakeSNR(),
                               price_at, [date(2020, 1, 31)],
                               sess_idx)
    return prov


def test_provider_slot_cap_and_entry_rows():
    d = _biz_dates(date(2020, 2, 3), 6)
    sess_idx = {}
    k = 0
    for dd in d:
        for ss in ("am", "pm"):
            sess_idx[(dd, ss)] = k
            k += 1
    day = d[0]
    evs = [TriggerEvent(f"sz.{i}", day, "A1", cap_price=11.0,
                        cancel_level=9.0, rank_key=float(i))
           for i in range(6)]
    ser = _mk_series("sz.0", d, np.full(len(d), 10.0))
    series = {f"sz.{i}": ser for i in range(6)}
    prices = {(f"sz.{i}", day, "pm"): 10.0 for i in range(6)}
    prov = _provider(evs, series, sess_idx, price_map=prices)
    ledger = {"positions": [], "date": day, "session": "pm",
              "cash": 500_000.0, "equity_snapshot": 500_000.0,
              "pending_am_to_pm": [], "pending_next_day": []}
    rows = prov.provider(day, "pm", ledger)
    buys = [r for r in rows if r["side"] == "buy"]
    assert len(buys) == MAX_SEATS                    # slot cap
    assert all(r["target_weight"] == 0.10 for r in buys)
    assert prov.trig["issued"] == MAX_SEATS
    assert prov.trig["skip_slots"] == 6 - MAX_SEATS
    # entry allowed while reduced too (registered); target weight differs
    prov2 = _provider(evs, series, sess_idx, risk_state="reduced",
                      price_map=prices)
    rows2 = prov2.provider(day, "pm", ledger)
    assert len([r for r in (rows2 or []) if r["side"] == "buy"]) == MAX_SEATS
    # an unknown risk state fails CLOSED (no entries)
    prov3 = _provider(evs, series, sess_idx, risk_state="garbage",
                      price_map=prices)
    rows3 = prov3.provider(day, "pm", ledger)
    assert not [r for r in (rows3 or []) if r["side"] == "buy"]


def test_provider_ttl_cancel_and_invalidation():
    d = _biz_dates(date(2020, 2, 3), 10)
    sess_idx = {}
    k = 0
    for dd in d:
        for ss in ("am", "pm"):
            sess_idx[(dd, ss)] = k
            k += 1
    ser = _mk_series("sz.1", d, np.full(len(d), 10.0))
    prices = {("sz.1", dd, ss): 10.0 for dd in d for ss in ("am", "pm")}
    ev = TriggerEvent("sz.1", d[0], "A1", cap_price=10.1, cancel_level=9.5)
    prov = _provider([ev], {"sz.1": ser}, sess_idx, price_map=prices)
    led = {"positions": [], "date": d[0], "session": "pm",
           "cash": 500_000.0, "equity_snapshot": 500_000.0,
           "pending_am_to_pm": [], "pending_next_day": []}
    prov.provider(d[0], "pm", led)                     # issue at si=1
    prov.provider(d[1], "am", led)                     # si=2 re-issue
    prov.provider(d[1], "pm", led)                     # si=3 re-issue
    prov.provider(d[2], "am", led)                     # si=4: 4-1>=3 -> TTL
    assert prov.trig["cancel_ttl"] == 1 and not prov.pending


def test_provider_b_time_exit_at_20_sessions():
    d = _biz_dates(date(2020, 1, 2), 30)
    sess_idx = {}
    k = 0
    for dd in d:
        for ss in ("am", "pm"):
            sess_idx[(dd, ss)] = k
            k += 1
    ser = _mk_series("sz.1", d, np.full(len(d), 10.0))
    prices = {("sz.1", dd, ss): 10.0 for dd in d for ss in ("am", "pm")}
    prov = _provider([], {"sz.1": ser}, sess_idx, is_b=True,
                     price_map=prices)
    pos = [{"symbol": "sz.1", "shares": 1000,
            "clips": [{"shares": 1000, "acquired": d[2].isoformat(),
                       "session": "pm", "price": 10.0}]}]
    led = {"positions": pos, "date": d[2], "session": "pm",
           "cash": 400_000.0, "equity_snapshot": 500_000.0,
           "pending_am_to_pm": [], "pending_next_day": []}
    # age counted in own sessions: day d[22] is exactly 20 after d[2]
    rows = prov.provider(d[22], "pm", led)
    te = [r for r in rows if r.get("exit_reason") == "time_exit"]
    assert len(te) == 1
    assert te[0]["intent"] == "profit" and te[0]["target_weight"] is None
    assert te[0]["source_signal"] == d[22]
    # frozen source across re-issues while still held
    rows2 = prov.provider(d[23], "am", led)
    te2 = [r for r in rows2 if r.get("exit_reason") == "time_exit"]
    assert te2[0]["source_signal"] == d[22]
    # position gone -> state purged
    led0 = {"positions": [], "date": d[24], "session": "pm",
            "cash": 500_000.0, "equity_snapshot": 500_000.0,
            "pending_am_to_pm": [], "pending_next_day": []}
    prov.provider(d[24], "pm", led0)
    assert prov.time_exits == {}


def test_delayed_provider_releases_one_session_later():
    inner_calls = []

    def inner(day, sess, ledger):
        inner_calls.append((day, sess))
        return [{"symbol": "sz.1", "side": "buy", "intent": "",
                 "decision_date": day, "decision_session": sess,
                 "source_signal": day, "priority": 1}]

    wrapped = make_delayed_provider(inner, 1)
    d = _biz_dates(date(2020, 3, 2), 3)
    led = {"positions": []}
    r0 = wrapped(d[0], "am", led)      # queues d0-am rows, nothing out
    r1 = wrapped(d[0], "pm", led)      # releases d0-am rows, stamped d0-pm
    r2 = wrapped(d[1], "am", led)      # releases d0-pm rows, stamped d1-am
    assert r0 is None
    assert r1 and r1[0]["decision_date"] == d[0] \
        and r1[0]["decision_session"] == "pm" \
        and r1[0]["source_signal"] == d[0]
    assert r2 and r2[0]["decision_date"] == d[1] \
        and r2[0]["decision_session"] == "am" \
        and r2[0]["source_signal"] == d[0]


def test_attack_entries_allowed_maps_state():
    # registered semantics: entries stay allowed while REDUCED (target is
    # E-scaled); unknown states fail CLOSED
    assert _attack_entries_allowed("normal") is True
    assert _attack_entries_allowed("reduced") is True
    assert _attack_entries_allowed("no-such-state") is False


def test_improve_codes_include_impairment():
    assert "impairment" in IMPROVE_CODES
    assert "cost_up" not in IMPROVE_CODES
