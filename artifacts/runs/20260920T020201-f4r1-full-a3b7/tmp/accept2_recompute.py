# F4R1 全期验收第二部分：从 parquet 独立重算八门关键数字
import json

import polars as pl

RUN = "D:/量化/artifacts/runs/20260920T020201-f4r1-full-a3b7/outputs"
B1M_YEAR = {"2015": 0.22735356961586017, "2016": -0.036271319473570096,
            "2017": -0.11258228102926204, "2018": -0.1962740727688722,
            "2019": 0.12375649932752708, "2020": 0.09319791239431541}
CAPITAL = 500_000.0

mg = json.load(open(f"{RUN}/metrics_and_gates.json", encoding="utf-8"))

for arm in ("F4R1-A", "F4R1-B", "F4R1-C"):
    eq = pl.read_parquet(f"{RUN}/{arm}_daily_equity.parquet").sort("date")
    e = eq["equity"]
    total = e[-1] / e[0] - 1
    n_years = eq["date"].dt.year().unique().len()
    cagr = (e[-1] / e[0]) ** (1 / (n_years - 0)) - 1 if False else (e[-1] / e[0]) ** (1 / 6) - 1
    # maxDD
    peak = e.cum_max()
    dd = (e / peak - 1).min()
    # 分年收益
    eq2 = eq.with_columns(pl.col("date").dt.year().alias("y"))
    yr = {}
    for (y,), g in eq2.group_by("y"):
        ye = g.sort("date")["equity"]
        prev_last = eq2.filter(pl.col("y") == y - 1).sort("date")["equity"][-1] if y > 2015 else CAPITAL
        yr[str(y)] = ye[-1] / prev_last - 1
    adv = sum(1 for y in B1M_YEAR if yr.get(y, 0) > B1M_YEAR[y])
    # 换手（分年买入名义额/年均权益）
    fl = pl.read_parquet(f"{RUN}/{arm}_fills.parquet")
    fl2 = fl.with_columns(pl.col("date").dt.year().alias("y"))
    mean_eq_by_year = {str(y): g.sort("date")["equity"].mean() for (y,), g in
                       eq2.group_by("y")}
    to = {}
    for (y,), g in fl2.filter(pl.col("side") == "buy").group_by("y"):
        to[str(y)] = g["notional"].sum() / mean_eq_by_year[str(y)]
    # 门 8：armed/k3/自行成交/stuck
    ev = pl.read_parquet(f"{RUN}/{arm}_events.parquet")
    n_armed = ev.filter(pl.col("event") == "stop_armed").height if "stop_armed" in ev["event"].unique().to_list() else None
    armed_events = sorted(ev["event"].unique().to_list())
    rep = mg["metrics"][arm]
    g = mg["gates"][arm]["dev"]
    print(f"== {arm} ==")
    print(f"  net_total: mine={total:.6f} rep={rep['net_total_return']:.6f}")
    print(f"  net_cagr(1/6): mine={cagr:.6f} rep={rep['net_cagr']:.6f}")
    print(f"  maxDD: mine={dd:.6f} rep={rep['max_drawdown']:.6f}")
    print(f"  adv_years: mine={adv} rep={g['advantage_years']}")
    print(f"  year_ret: mine={ {k: round(v,4) for k,v in yr.items()} }")
    print(f"  turnover/yr: { {k: round(v,2) for k,v in to.items()} } max={max(to.values()):.2f}")
    print(f"  events vocab: {armed_events}")
