# Main-conversation acceptance recompute for exp-universe-v1 (ASCII-safe)
import json
import polars as pl

RUN = r"D:\量化\artifacts\runs\20260919T161737-exp-universe-v1-3eu1"
mg = json.load(open(RUN + r"\outputs\metrics_and_gates.json", encoding="utf-8"))
mets = mg["metrics"]

def recompute(cid):
    de = pl.read_parquet(RUN + rf"\outputs\{cid}_daily_equity.parquet").sort("date")
    eq = de["equity"].to_list()
    n = len(eq)
    cagr = (eq[-1] / eq[0]) ** (252.0 / n) - 1 if False else None
    # actual convention: engine uses trading-day count; approximate both ways
    yrs = n / 243.5  # ~243.5 dev trading days/yr (1462/6)
    cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1
    peak, mdd = eq[0], 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    return cagr, -mdd, n

for cid in ("EU-A0", "EU-02", "EU-07", "EU-08", "EU-09"):
    m = mets[cid]
    c, d, n = recompute(cid)
    print(f"{cid}: reported net_cagr={m['net_cagr']:.6f} mdd={m['max_drawdown']:.6f} | "
          f"recompute(days={n}) cagr={c:.6f} mdd={d:.6f} | "
          f"diff_cagr={abs(c-m['net_cagr']):.2e} diff_mdd={abs(d-m['max_drawdown']):.2e}")

# gates arithmetic spot: EU-01 failed gates 3 and 4 only; EU-04/05 gate 4 only; EU-03/06 gate 3 only
for cid in ("EU-01", "EU-03", "EU-04"):
    g = mg["gates"][cid]["dev"]
    print(cid, "failed:", g["failed_gates"], "dev_pass:", g["dev_pass"],
          "roster:", g["roster_eligible"])

# roster column across all
roster = {c: mg["gates"][c]["dev"]["roster_eligible"] for c in mets}
print("roster_eligible:", {c: v for c, v in roster.items() if v})
print("goal10 column:", {c: mets[c]["goal_dev_net_cagr_ge_10pct"] for c in mets})
