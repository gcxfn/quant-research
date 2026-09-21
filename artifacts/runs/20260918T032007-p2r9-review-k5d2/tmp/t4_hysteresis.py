# T4: independent rebuild of hysteresis state machines
#  - D60/D252 + hysteresis/no-hysteresis from RAW index chunk_000300.SH.csv
#  - PDD from the run's own equity curves (net) replayed through the registered semantics
# Compare with metrics.hysteresis_switch_stats_by_year per config.
import json, csv
from collections import OrderedDict
import polars as pl

RUN = r"D:\量化\artifacts\runs\20260918T030528-p2r9-risk-delivery-ef2777dc"
m = json.load(open(RUN + r"\metrics.json", encoding="utf-8"))

# --- load raw index ---
rows = []
with open(r"D:\量化\data\raw\tushare\index_daily\20260917-r1\chunk_000300.SH.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        rows.append((r["trade_date"], float(r["close"])))
rows.sort()
dates = [d for d, _ in rows]
closes = [c for _, c in rows]
print("index rows:", len(rows), dates[0], dates[-1])
print("rows in 2015:", sum(1 for d in dates if d.startswith("2015")))
n2016 = sum(1 for d in dates if d.startswith("2016"))
print("rows in 2016:", n2016)

def rolling_dd(window):
    out = {}
    for i in range(len(rows)):
        if i + 1 < window:
            out[dates[i]] = None
        else:
            pk = max(closes[i + 1 - window:i + 1])
            out[dates[i]] = 1.0 - closes[i] / pk
    return out

dd60 = rolling_dd(60)
dd252 = rolling_dd(252)

def hyst(dd_of, daylist, th, ra):
    st, out = True, {}
    for d in daylist:
        dd = dd_of[d]
        if dd is None:
            st = False
        elif st:
            if dd >= th:
                st = False
        elif dd <= ra:
            st = True
        out[d] = st
    return out

def nohyst(dd_of, daylist, th):
    return {d: (dd_of[d] is not None and dd_of[d] <= th) for d in daylist}

sim = [d for d in dates if "2016-01-04" <= d <= "2024-12-31"]
dev = [d for d in sim if d <= "2020-12-31"]
E_ON, E_LOW = 0.90, 0.40

def stats_from_state(st, daylist):
    per = OrderedDict()
    prev = None
    for d in daylist:
        y = int(d[:4])
        b = per.setdefault(y, dict(n_sessions=0, n_off_triggers=0, n_rearms=0, n_switches=0, off_sessions=0, sum_e=0.0))
        e = E_ON if st[d] else E_LOW
        b["n_sessions"] += 1
        b["sum_e"] += e
        if prev is not None and e != prev:
            b["n_switches"] += 1
            if e == E_LOW: b["n_off_triggers"] += 1
            else: b["n_rearms"] += 1
        if e == E_LOW: b["off_sessions"] += 1
        prev = e
    return {y: {"n_sessions": v["n_sessions"], "n_switches": v["n_switches"],
                "n_off_triggers": v["n_off_triggers"], "n_rearms": v["n_rearms"],
                "off_share": round(v["off_sessions"] / v["n_sessions"], 4),
                "mean_exposure": round(v["sum_e"] / v["n_sessions"], 4)}
            for y, v in per.items()}

def compare(name, mine, rec, years):
    ok = True
    for y in years:
        a, b = mine.get(y), rec.get(str(y))
        for k in ["n_sessions", "n_switches", "n_off_triggers", "n_rearms"]:
            if a[k] != b[k]: ok = False; print(f"  {name} {y} {k}: mine={a[k]} run={b[k]}")
        for k in ["off_share", "mean_exposure"]:
            if abs(a[k] - b[k]) > 6e-4: ok = False; print(f"  {name} {y} {k}: mine={a[k]} run={b[k]}")
    print(f"{name}: {'MATCH' if ok else 'MISMATCH'}")

# --- D60 no-hysteresis (C02), hysteresis ra=4% (C01/C03/C04/C05/C12), D252 ra=5% (C06/C07) ---
st_d60h = hyst(dd60, sim, 0.08, 0.04)
st_d60n = nohyst(dd60, sim, 0.08)
st_d252h = hyst(dd252, sim, 0.10, 0.05)
devY = [2016, 2017, 2018, 2019, 2020]
compare("C01/C03/C04/C05/C12 D60-8H4", stats_from_state(st_d60h, sim), m["configs"]["C01"]["hysteresis_switch_stats_by_year"], range(2016, 2025))
compare("C02 D60-8 nohyst", stats_from_state(st_d60n, sim), m["configs"]["C02"]["hysteresis_switch_stats_by_year"], range(2016, 2025))
compare("C06/C07 D252-10H5", stats_from_state(st_d252h, sim), m["configs"]["C06"]["hysteresis_switch_stats_by_year"], range(2016, 2025))

# boundary-exact-dd check + warmup fallback count for D252
exact8 = sum(1 for d in sim if dd60[d] is not None and dd60[d] == 0.08)
exact10 = sum(1 for d in sim if dd252[d] is not None and dd252[d] == 0.10)
fb = sum(1 for d in dev if dd252[d] is None)
print("boundary dd==T sessions (sim window): D60@0.08 =", exact8, ", D252@0.10 =", exact10, "| D252 unformed dev sessions =", fb)

# --- PDD rebuild from equity curves (net instance) ---
df = pl.read_parquet(RUN + r"\equity_curves.parquet")
def rebuild_pdd(cid, th=0.10, ra=0.05, e_low=0.40):
    s = df.filter(pl.col("config_id") == cid).sort("session")
    per = OrderedDict(); prev = None; peak = None; on = True
    for d, v in zip([str(x) for x in s["session"].to_list()], s["equity_net"].to_list()):
        if "2016-01-04" > d or d > "2024-12-31": continue
        y = int(d[:4])
        b = per.setdefault(y, dict(n_sessions=0, n_off_triggers=0, n_rearms=0, n_switches=0, off_sessions=0, sum_e=0.0))
        peak = v if peak is None else max(peak, v)
        dd = 1.0 - v / peak
        e_before = on
        if on:
            if dd >= th: on = False
        elif dd <= ra:
            on = True
        e = E_ON if on else e_low
        b["n_sessions"] += 1; b["sum_e"] += e
        if prev is not None and e != prev:
            b["n_switches"] += 1
            if e == e_low: b["n_off_triggers"] += 1
            else: b["n_rearms"] += 1
        if e == e_low: b["off_sessions"] += 1
        prev = e
    return {y: {"n_sessions": v["n_sessions"], "n_switches": v["n_switches"],
                "n_off_triggers": v["n_off_triggers"], "n_rearms": v["n_rearms"],
                "off_share": round(v["off_sessions"] / v["n_sessions"], 4),
                "mean_exposure": round(v["sum_e"] / v["n_sessions"], 4)} for y, v in per.items()}

for cid in ["C08", "C09", "C10"]:
    mine = rebuild_pdd(cid)
    compare(f"{cid} PDD-10H5", mine, m["configs"][cid]["hysteresis_switch_stats_by_year"], range(2016, 2025))

# --- X1 rebuild: PDD arm on C11 net equity + D60 arm state ---
s = df.filter(pl.col("config_id") == "C11").sort("session")
per = OrderedDict(); prev = None; peak = None; pdd_on = True
for d, v in zip([str(x) for x in s["session"].to_list()], s["equity_net"].to_list()):
    if "2016-01-04" > d or d > "2024-12-31": continue
    y = int(d[:4])
    b = per.setdefault(y, dict(n_sessions=0, n_off_triggers=0, n_rearms=0, n_switches=0, off_sessions=0, sum_e=0.0))
    peak = v if peak is None else max(peak, v)
    dd = 1.0 - v / peak
    if pdd_on:
        if dd >= 0.10: pdd_on = False
    elif dd <= 0.05:
        pdd_on = True
    on = pdd_on and st_d60h[d]
    e = E_ON if on else E_LOW
    b["n_sessions"] += 1; b["sum_e"] += e
    if prev is not None and e != prev:
        b["n_switches"] += 1
        if e == E_LOW: b["n_off_triggers"] += 1
        else: b["n_rearms"] += 1
    if e == E_LOW: b["off_sessions"] += 1
    prev = e
mine = {y: {"n_sessions": v["n_sessions"], "n_switches": v["n_switches"], "n_off_triggers": v["n_off_triggers"],
            "n_rearms": v["n_rearms"], "off_share": round(v["off_sessions"]/v["n_sessions"],4),
            "mean_exposure": round(v["sum_e"]/v["n_sessions"],4)} for y, v in per.items()}
compare("C11 X1", mine, m["configs"]["C11"]["hysteresis_switch_stats_by_year"], range(2016, 2025))

# doc claims: C02 2018 13/12/58.9 ; C01-path 2018 2/1/88.5 ; C08 2018 1/0 ; 2016 D60 rearm date
mine18c02 = stats_from_state(st_d60n, sim)[2018]
mine18c01 = stats_from_state(st_d60h, sim)[2018]
print("doc check C02 2018 13/12/58.9:", mine18c02)
print("doc check C01-path 2018 2/1/88.5:", mine18c01)
rearms = [d for d in sim if st_d60h[d] and not st_d60h_prev] if False else None
# find 2016 re-arm date for D60H4
prevst = None
for d in sim:
    if prevst is False and st_d60h[d] is True and d.startswith("2016"):
        print("D60H4 first 2016 re-arm date:", d)
    prevst = st_d60h[d]
