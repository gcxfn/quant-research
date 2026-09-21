# T2/T3/T5: recompute segment metrics from equity_curves.parquet for C08 / B1(m) / anchors / B1@100
import json, math
import polars as pl

RUN = r"D:\量化\artifacts\runs\20260918T030528-p2r9-risk-delivery-ef2777dc"
R8 = r"D:\量化\artifacts\runs\20260918T021054-p2r8-daily-risk-d19a9c07"
m = json.load(open(RUN + r"\metrics.json", encoding="utf-8"))
df = pl.read_parquet(RUN + r"\equity_curves.parquet")

def curve(cid, col="equity_net"):
    s = df.filter(pl.col("config_id") == cid).sort("session")
    return s["session"].to_list(), s[col].to_list()

def slice_year(sess, eq, y0, y1):
    return [(d, v) for d, v in zip(sess, eq) if f"{y0}-01-01" <= str(d) <= f"{y1}-12-31"]

def total_ret(sl):
    return sl[-1][1] / sl[0][1] - 1.0

def yearly_returns(sl):
    # returns per calendar year, chained across the slice (first year from slice start)
    out, prev = {}, None
    import collections
    by_year = collections.OrderedDict()
    for d, v in sl:
        by_year.setdefault(str(d)[:4], []).append(v)
    for y, vals in by_year.items():
        out[y] = vals[-1] / (prev if prev is not None else vals[0]) - 1.0
        prev = vals[-1]
    return out

def mdd(sl):
    peak, worst, pw, tw = -1e18, 0.0, None, None
    for d, v in sl:
        if v > peak:
            peak, pd = v, d
        dd = v / peak - 1.0
        if dd < worst:
            worst, pw, tw = dd, pd, d
    return worst, pw, tw

def cagr_from(total, y):
    return (1.0 + total) ** (1.0 / y) - 1.0

# ---------- convention detection on C08 dev ----------
sess, eq = curve("C08")
dev = slice_year(sess, eq, 2016, 2020)
tot = total_ret(dev)
rec_dev = m["configs"]["C08"]["dev"]
print("C08 dev total recomputed:", tot, "recorded:", rec_dev["net_total_return"], "match:", abs(tot - rec_dev["net_total_return"]) < 1e-12)
import datetime
d0, d1 = dev[0][0], dev[-1][0]
n = len(dev)
cands = {
 "5.0": 5.0,
 "days/365.25": ((d1 - d0).days + 1) / 365.25,
 "days/365": ((d1 - d0).days + 1) / 365,
 "days/365.25(no+1)": ((d1 - d0).days) / 365.25,
 "sessions/244": n / 244,
 "sessions/243.5": n / 243.5,
}
target = rec_dev["net_cagr"]
for k, y in cands.items():
    print(f"  cagr conv {k}: y={y:.5f} cagr={cagr_from(tot,y):.8f} target={target:.8f} diff={cagr_from(tot,y)-target:.2e}")

# ---------- B1(m) PDD val & dev ----------
bs, be = curve("B1-PDD-10H5-L0.4")
bval = slice_year(bs, be, 2021, 2022)
rec_val = m["configs"]["C08"]["validation"]
print("\nB1(m)PDD val total:", total_ret(bval), "recorded b1m:", rec_val["b1m_net_cagr"], "(CAGR below)")
bval_mdd, bp, bt = mdd(bval)
print("B1(m)PDD val mdd:", bval_mdd, bp, bt, "recorded:", rec_val["b1m_max_drawdown"])

def years_of(sl):
    d0, d1 = sl[0][0], sl[-1][0]
    return ((d1 - d0).days + 1) / 365.25

c08_val = slice_year(sess, eq, 2021, 2022)
t = total_ret(c08_val)
y = years_of(c08_val)
c08_val_cagr = cagr_from(t, y)
b_cagr = cagr_from(total_ret(bval), years_of(bval))
print("C08 val: total", t, "years", y, "cagr", c08_val_cagr, "recorded", rec_val["net_cagr"])
print("val excess recomputed:", c08_val_cagr - b_cagr, "recorded:", rec_val["excess_vs_b1m"])
c08_val_mdd, cp, ct = mdd(c08_val)
print("C08 val mdd:", c08_val_mdd, cp, ct, "recorded:", rec_val["max_drawdown"], rec_val["mdd_window"])
yrs = yearly_returns(c08_val)
byrs = yearly_returns(bval)
print("C08 val yearly:", yrs, "recorded:", rec_val["net_return_by_year"])
print("B1 val yearly:", byrs)
print("excess arith 2021/2022:", yrs['2021'] - byrs['2021'], yrs['2022'] - byrs['2022'])
print("excess recorded:", rec_val["excess_by_year"])

# ---------- dev convention final: apply chosen conv to all ----------
print("\n--- dev recompute with winning convention ---")
for cid in ["C08", "B1-PDD-10H5-L0.4"]:
    pass
dev_b = slice_year(bs, be, 2016, 2020)
tb = total_ret(dev_b)
print("B1(m)PDD dev cagr recomputed:", cagr_from(tb, years_of(dev_b)), "recorded:", rec_dev["b1m_net_cagr"])
