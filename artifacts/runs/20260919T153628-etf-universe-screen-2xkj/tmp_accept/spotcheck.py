# Main-conversation acceptance spot-checks for etf-universe-screen-2xkj (ASCII only)
import polars as pl, hashlib, json

RUN = r"D:\量化\artifacts\runs\20260919T153628-etf-universe-screen-2xkj"
PQ = r"D:\量化\data\processed\etf-daily-20260919\daily_2015_2024.parquet"

# input identity
h = hashlib.sha256(open(PQ, "rb").read()).hexdigest()
print("parquet sha256:", h[:16], "expect b7225d50523106f5:", h.startswith("b7225d50523106f5"))

df = pl.read_parquet(PQ)
print("rows:", df.height, "symbols:", df["symbol"].n_unique())
import datetime as dt
D25, D21 = dt.date(2025, 1, 1), dt.date(2021, 1, 1)
assert df.filter(pl.col("date") >= D25).height == 0, "freeze violated"

def prev_close(sym, d):
    sub = df.filter((pl.col("symbol") == sym) & (pl.col("date") < d)).sort("date")
    return sub["close"][-1], sub["date"][-1]

# 1) 159932 2015-06-30 new defect claim
for sym, d in [("sz.159932", dt.date(2015,6,30)), ("sz.159919", dt.date(2019,1,14))]:
    row = df.filter((pl.col("symbol") == sym) & (pl.col("date") == d))
    pc, pdate = prev_close(sym, d)
    pre = row["preclose"][0]
    print(f"{sym} {d}: preclose={pre} prev_close={pc} ({pdate}) preclose/prev-1={pre/pc-1:+.4%} rows_ok={row.height}")

# 2) pass pool composition
scr = pl.read_parquet(RUN + r"\outputs\etf_universe_screen.parquet")
pool = scr.filter(pl.col("screen_pass"))
print("pool size:", pool.height)
print(pool.group_by("asset_class").len().sort("len", descending=True).to_dicts() if "asset_class" in scr.columns else "no asset_class col; cols:", scr.columns)
print("pool symbols:", sorted(pool["symbol"].to_list()))

# 3) coverage arithmetic for two pool members and one fail (listed-late)
cal = df["date"].unique().sort()
dev_cal = [d for d in cal if d < D21]
val_cal = [d for d in cal if d >= D21]
print("dev days:", len(dev_cal), "val days:", len(val_cal))
for sym in ["sh.510300", "sh.513100", "sz.159915"]:
    sub = df.filter(pl.col("symbol") == sym)
    dc = sub.filter(pl.col("date") < D21).height / len(dev_cal)
    vc = sub.filter(pl.col("date") >= D21).height / len(val_cal)
    row = scr.filter(pl.col("symbol") == sym)
    print(f"{sym}: dev_cov={dc:.4f} val_cov={vc:.4f} screen_pass={row['screen_pass'][0] if row.height else 'NA'}")

# 4) 513100 split in jump table classified as split/merge, factor ~5
je = pl.read_csv(RUN + r"\outputs\jump_events_gt6pct.csv")
r513 = je.filter(pl.col("symbol") == "sh.513100")
print("513100 jump events:", r513.select(["date", "classification" if "classification" in je.columns else je.columns[-1]]).to_dicts() if r513.height else "none")
print("je cols:", je.columns)

# 5) money members in pool (need to know for prereg drafting)
if "asset_class" in pool.columns:
    print("money pool:", sorted(pool.filter(pl.col("asset_class") == "money")["symbol"].to_list()))
