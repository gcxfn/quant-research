# F1 integration smoke (engineering validation ONLY — NOT selection evidence, zero trials)
import json, random, sys, time
sys.path.insert(0, ".")
import polars as pl
from src.quant.factors.eval import evaluate_factor, FactorEvalConfig, eval_cache_key
import hashlib, io

t0 = time.time()
PANEL = r"data/processed/baostock-daily-20260917/daily_2015_2024.parquet"
sha = hashlib.sha256(open(PANEL, "rb").read()).hexdigest()
panel = pl.read_parquet(PANEL)
rng = random.Random(20260919)
syms = sorted(panel["symbol"].unique().to_list())
sample = rng.sample(syms, 50)
sub = panel.filter(pl.col("symbol").is_in(sample))
assert sub["date"].max().isoformat() <= "2024-12-31"

# seeded pseudo-random factor on month-end trading days (no predictive content)
me = (sub.select("date").unique()
      .with_columns(pl.col("date").dt.truncate("1mo").alias("_m"))
      .group_by("_m").agg(pl.col("date").max().alias("d")).sort("d"))
me_dates = me["d"].to_list()
frows = []
for d in me_dates:
    for s in sample:
        frows.append((s, d, rng.gauss(0.0, 1.0)))
factor = pl.DataFrame({
    "symbol": [r[0] for r in frows],
    "signal_date": [r[1] for r in frows],
    "value": [r[2] for r in frows],
}).with_columns(pl.col("signal_date").cast(pl.Date))

cfg = FactorEvalConfig(horizon_days=10, n_groups=10, eval_freq="M", min_history_rows=60)
res = evaluate_factor(factor, sub, cfg)
res["elapsed_s"] = round(time.time() - t0, 1)
res["panel_sha256_16"] = sha[:16]
res["n_symbols"] = len(sample)
res["cache_key_demo"] = eval_cache_key(
    {"code": "integration-smoke-random", "params": {"seed": 20260919}}, sha[:16] + "...", cfg)
out = "artifacts/runs/20260919T170000-f0-factor-inputs-main/outputs/f1_integration_smoke.json"
io.open(out, "w", encoding="utf-8").write(
    json.dumps(res, ensure_ascii=False, indent=1, default=str))
print(json.dumps({k: res[k] for k in
      ("n_dates", "coverage_mean_symbols", "ic_mean", "ic_std", "icir",
       "long_short_mean", "monotonicity", "turnover_top_group", "elapsed_s")}, default=str))
print("ic_by_year keys:", sorted(res["ic_by_year"]))
print("saved:", out)
