# -*- coding: utf-8 -*-
"""close-bridge-sweep: 全市场验证 §7.4 收盘桥接规则作用域（只读校验，无回测、无试验消耗）。

对 data/processed/halfday-bars-20260918 的 session=pm 行左连
baostock 官方日线 close，按 交易所×年份 统计不匹配率（1e-4 与 1e-6 两口径），
并输出沪市 2018 逐月/逐日切换点、切换后残余标的、深市异常清单、桥接期幅度分布。
"""
import hashlib
import json
import platform
import sys
import time
from datetime import date

import polars as pl

RUN_DIR = r"D:\量化\artifacts\runs\20260918T201955-close-bridge-sweep-74ad"
HALFDAY_DIR = r"D:\量化\data\processed\halfday-bars-20260918"
OFFICIAL_PQ = r"D:\量化\data\processed\baostock-daily-20260917\daily_1999_2024.parquet"
YEARS = list(range(2015, 2025))


def sha256_16(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def exchange(sym: pl.Expr) -> pl.Expr:
    return sym.str.slice(0, 2)


def run(years, tag):
    t0 = time.time()
    stats = []
    sh_pre_mm6 = []   # 沪市切换前不匹配（幅度分布用）
    sh_post_mm6 = []  # 沪市 2018-08-20 起不匹配（残余标的清单）
    sh_2018_daily = []  # 沪市 2018-07..09 逐日计数（精确定位切换点）
    sz_mm6 = []       # 深市全部不匹配明细
    miss_reasons = []

    for y in years:
        ty = time.time()
        pm = (
            pl.scan_parquet(rf"{HALFDAY_DIR}\year={y}\bars.parquet")
            .filter(pl.col("session") == "pm")
            .select("symbol", "trade_date", "close")
            .collect()
        )
        off = (
            pl.scan_parquet(OFFICIAL_PQ)
            .filter(pl.col("date").dt.year() == y)
            .select("symbol", "date", "close", "tradestatus")
            .collect()
        )

        for name, df, keys in (("pm", pm, ["symbol", "trade_date"]), ("official", off, ["symbol", "date"])):
            dup = df.group_by(keys).len().filter(pl.col("len") > 1)
            if dup.height:
                raise SystemExit(f"DATA ANOMALY [{tag} {y}] {name} duplicate keys: {dup.head()}")

        j = pm.join(off.rename({"date": "trade_date"}), on=["symbol", "trade_date"], how="left")
        rel = (pl.col("close") / pl.col("close_right") - 1.0).abs()
        j = j.with_columns(
            exchange(pl.col("symbol")).alias("exch"),
            rel.alias("abs_rel"),
            (rel > 1e-4).alias("mm4"),
            (rel > 1e-6).alias("mm6"),
        )

        off_syms = set(off["symbol"].unique())
        off_dates = set(off["date"].unique())
        miss = j.filter(pl.col("close_right").is_null())
        miss_reasons.append({
            "year": y,
            "join_miss": miss.height,
            "miss_symbol_not_in_official": miss.filter(~pl.col("symbol").is_in(sorted(off_syms))).height,
            "miss_date_not_in_official": miss.filter(~pl.col("trade_date").is_in(sorted(off_dates))).height,
        })

        agg = (
            j.group_by("exch")
            .agg(
                pl.len().alias("pm_rows"),
                pl.col("close_right").is_null().sum().alias("join_miss"),
                pl.col("mm4").sum().alias("mm4_cnt"),
                pl.col("mm6").sum().alias("mm6_cnt"),
                (pl.col("abs_rel") * 1e4).filter(pl.col("mm6")).quantile(0.5).alias("bps_p50"),
                (pl.col("abs_rel") * 1e4).filter(pl.col("mm6")).quantile(0.9).alias("bps_p90"),
                (pl.col("abs_rel") * 1e4).filter(pl.col("mm6")).max().alias("bps_max"),
            )
            .with_columns(pl.lit(y).alias("year"))
            .sort("exch")
        )
        stats.append(agg)

        sh = j.filter((pl.col("exch") == "sh") & pl.col("mm6"))
        sh_pre_mm6.append(sh.filter(pl.col("trade_date") < pl.date(2018, 8, 20)).select("trade_date", "abs_rel"))
        sh_post_mm6.append(sh.filter(pl.col("trade_date") >= pl.date(2018, 8, 20)).select(
            "trade_date", "symbol", "close", "close_right", "abs_rel"))
        if y == 2018:
            d18 = (
                j.filter((pl.col("exch") == "sh") & (pl.col("trade_date") >= pl.date(2018, 7, 1))
                         & (pl.col("trade_date") <= pl.date(2018, 9, 30)))
                .group_by("trade_date")
                .agg(pl.len().alias("rows"), pl.col("mm6").sum().alias("mm6_cnt"))
                .sort("trade_date")
            )
            d18.write_csv(rf"{RUN_DIR}\outputs\sh_2018_julsep_daily.csv")
            m18 = (
                j.filter(pl.col("exch") == "sh")
                .group_by(pl.col("trade_date").dt.month().alias("month"))
                .agg(pl.len().alias("rows"), pl.col("mm6").sum().alias("mm6_cnt"),
                     (pl.col("abs_rel") * 1e4).filter(pl.col("mm6")).max().alias("bps_max"))
                .sort("month")
            )
            m18.write_csv(rf"{RUN_DIR}\outputs\sh_2018_monthly.csv")
        sz = j.filter((pl.col("exch") == "sz") & pl.col("mm6")).select(
            pl.lit(y).alias("year"), "trade_date", "symbol", "close", "close_right", "abs_rel")
        sz_mm6.append(sz)

        print(f"[{tag}] year={y} pm_rows={pm.height} off_rows={off.height} took {time.time()-ty:.1f}s", flush=True)

    out = {
        "stats": pl.concat(stats).select(
            "year", "exch", "pm_rows", "join_miss", "mm4_cnt", "mm6_cnt",
            (pl.col("mm4_cnt") / (pl.col("pm_rows") - pl.col("join_miss"))).alias("mm4_rate"),
            (pl.col("mm6_cnt") / (pl.col("pm_rows") - pl.col("join_miss"))).alias("mm6_rate"),
            "bps_p50", "bps_p90", "bps_max",
        ),
        "sh_pre": pl.concat(sh_pre_mm6) if sh_pre_mm6 else pl.DataFrame(),
        "sh_post": pl.concat(sh_post_mm6) if sh_post_mm6 else pl.DataFrame(),
        "sz": pl.concat(sz_mm6) if sz_mm6 else pl.DataFrame(),
        "miss_reasons": miss_reasons,
        "elapsed_s": time.time() - t0,
    }
    return out


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "smoke":
        t0 = time.time()
        res = run([2017], "smoke")
        print(res["stats"])
        print(f"SMOKE total {time.time()-t0:.1f}s")
    elif mode == "full":
        res = run(YEARS, "full")
        st = res["stats"]
        st.write_csv(rf"{RUN_DIR}\outputs\per_year_exchange.csv")

        pre = res["sh_pre"]
        post = res["sh_post"]
        sz = res["sz"]

        # 沪市切换前幅度分布（bps）
        bps = (pre["abs_rel"] * 1e4).abs().sort()
        n = len(bps)
        mag = {
            "sh_pre_mm6_rows": n,
            "first_mm6_date": str(pre["trade_date"].min()),
            "last_mm6_date_pre_switch": str(pre["trade_date"].max()),
            "p50_bps": round(float(bps[int(0.50 * (n - 1))]), 2) if n else None,
            "p90_bps": round(float(bps[int(0.90 * (n - 1))]), 2) if n else None,
            "p99_bps": round(float(bps[int(0.99 * (n - 1))]), 2) if n else None,
            "max_bps": round(float(bps[-1]), 2) if n else None,
        }
        # 沪市切换后残余
        if post.height:
            resid = (
                post.group_by("symbol")
                .agg(pl.len().alias("days"), pl.col("trade_date").min().alias("first_date"),
                     pl.col("trade_date").max().alias("last_date"))
                .sort("days", descending=True)
            )
            resid.write_csv(rf"{RUN_DIR}\outputs\sh_post_switch_residuals.csv")
            mag["sh_post_mm6_rows"] = post.height
            mag["sh_post_mm6_symbols"] = resid.height
            mag["sh_post_first_date"] = str(post["trade_date"].min())
            mag["sh_post_last_date"] = str(post["trade_date"].max())
        else:
            mag["sh_post_mm6_rows"] = 0
            mag["sh_post_mm6_symbols"] = 0
        # 深市明细
        mag["sz_mm6_rows"] = sz.height
        if sz.height:
            sz.write_csv(rf"{RUN_DIR}\outputs\sz_mismatch_detail.csv")
            top = sz.group_by("symbol").agg(pl.len().alias("days")).sort("days", descending=True).head(10)
            mag["sz_mm6_top_symbols"] = top.to_dicts()
            mag["sz_mm6_date_range"] = [str(sz["trade_date"].min()), str(sz["trade_date"].max())]

        summary = {"magnitude": mag, "join_miss_reasons": res["miss_reasons"],
                   "elapsed_s": round(res["elapsed_s"], 1),
                   "python": platform.python_version(), "polars": pl.__version__}
        with open(rf"{RUN_DIR}\tmp\summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        print(st.sort(["exch", "year"]))
        print(f"FULL total {res['elapsed_s']:.1f}s")
