# F2R1 全轮汇总：120 因子总表 + 存活者跨族相关性（F3 去重基础）
import json
from datetime import date
from pathlib import Path

import polars as pl

BATCH = Path(r"D:/量化/artifacts/runs/20260919T180000-f2r1-factor-batch")
FAMS = {"A_price": "A", "B_value": "B", "C_micro": "C", "D_fund": "D", "E_event": "E", "F_xsec": "F"}

rows = []
for sub, fam in FAMS.items():
    for i in range(1, 121):
        fid = f"{fam}{i:02d}"
        p = BATCH / "outputs" / sub / f"{fid}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        ev = d["eval"]
        scr = d.get("screen") or {}
        ic15 = scr.get("ic_2015", ev.get("ic_by_year", {}).get("2015"))
        rows.append({
            "factor_id": fid, "family": fam, "name": d.get("name", ""),
            "n_dates": ev["n_dates"], "ic_mean": round(ev["ic_mean"], 4),
            "t_ic": round(scr.get("t_ic", d.get("t_value", float("nan"))), 2),
            "mono": round(ev["monotonicity"], 2),
            "ic_2015": round(ic15 if ic15 is not None else 0.0, 4),
            "coverage": round(scr.get("coverage_ratio",
                                      (d.get("coverage_median_symbols", 0.0) or 0.0)
                                      / (d.get("pool_median_symbols", 1.0) or 1.0)), 3),
            "turnover_top": round(ev.get("turnover_top_group", 0.0), 2),
            "screen_pass": bool(scr.get("screen_pass", d.get("survived_prelim", False))),
        })
agg = pl.DataFrame(rows).sort("factor_id")
assert agg.height == 120, f"expect 120 factors, got {agg.height}"
agg.write_csv(BATCH / "outputs/f2r1_all120.csv")
surv = agg.filter(pl.col("screen_pass"))
print(f"120 因子汇总：存活 {surv.height}")
print(surv.select("factor_id", "name", "t_ic", "ic_mean", "mono", "coverage").to_pandas().to_string(index=False))

# ---- 存活者跨族月均横截面 Spearman 相关 ----
ids = surv["factor_id"].to_list()
frames = {}
for sub, fam in FAMS.items():
    for fid in ids:
        if fid.startswith(fam):
            f = pl.read_parquet(BATCH / "outputs" / sub / f"{fid}.parquet")
            frames[fid] = f.rename({"value": fid})
base = None
for fid, f in frames.items():
    base = f if base is None else base.join(f, on=["symbol", "signal_date"], how="inner")
print(f"相关矩阵基础帧：{base.height} 行（全部存活因子 inner join）")

n = len(ids)
M = [[1.0] * n for _ in range(n)]
for a in range(n):
    for b in range(a + 1, n):
        per = base.group_by("signal_date").agg(
            pl.corr(pl.col(ids[a]).rank("average"), pl.col(ids[b]).rank("average")).alias("rho")
        ).drop_nulls()
        rho = per["rho"].mean()
        M[a][b] = M[b][a] = round(float(rho), 3) if rho is not None else float("nan")

corr_df = pl.DataFrame({ids[i]: M[i] for i in range(n)})
corr_df.insert_column(0, pl.Series("factor", ids))
corr_df.write_csv(BATCH / "outputs/f2r1_survivors_corr.csv")

# 高相关对（|ρ|≥0.6）
pairs = []
for a in range(n):
    for b in range(a + 1, n):
        if abs(M[a][b]) >= 0.6:
            pairs.append((ids[a], ids[b], M[a][b]))
pairs.sort(key=lambda x: -abs(x[2]))
print(f"\n|ρ|≥0.6 的高相关对 {len(pairs)} 对：")
for x, y, r in pairs:
    print(f"  {x} × {y}: {r:+.3f}")
