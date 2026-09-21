# -*- coding: utf-8 -*-
"""05_constraint_checks.py — G2 半天截面前置：复权/PIT/停牌/涨跌停四项约束核验（抽样级，不实现任何因子）。

只读 data/raw、data/processed、docs；输出写 run 目录。
核验项：
A. 停牌表现：日线 tradestatus=0 最长的 2 只股，抽停牌日验证分钟缺失、复牌日恢复 241 bar；
B. 复权口径：高分红股除权日两侧，分钟 15:00 close vs baostock 未复权 close、
   分钟 09:30 pre_close vs baostock preclose（除权昨收）与原始前收，判断分钟价是否原始价；
C. ST 股：isST=1 的股票日在分钟中是否正常有 bar（ST 只是涨跌幅不同，不缺 bar）；
D. stk_limit：3 个抽样日 11:30 high/low 是否全部落在 [down_limit, up_limit] 内（语义可用性验证）；
E. 已知缺陷复核：2015-07-01 尾盘零量占位（11 只深市股 14:54–15:00）是否与登记一致。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
import time
from pathlib import Path

import polars as pl

REPO = Path(r"D:\量化")
RAW = REPO / "data" / "raw"
POOL = REPO / "data" / "processed" / "baostock-daily-20260917" / "daily_2015_2024.parquet"
RUN = REPO / "artifacts" / "runs" / "20260918T032049-halfday-prep-f3mbfd"
STK_LIMIT_DIR = RAW / "xiaodefa" / "stk_limit" / "20260913-bulk1"


def minute_path(d: dt.date) -> Path:
    y = d.year
    batch = "20260913-143215" if y <= 2019 else "20260913-2020-2024"
    return RAW / "user_minute_1m" / batch / str(y) / f"{d:%Y%m%d}.parquet"


def load_minute_day(d: dt.date, cols: list[str]) -> pl.DataFrame | None:
    p = minute_path(d)
    if not p.exists():
        return None
    return pl.read_parquet(p, columns=cols)


def main() -> int:
    t0 = time.perf_counter()
    report: dict = {"purpose": "adjustment/PIT/suspension/limit constraint verification (sample-level, pure data engineering)",
                    "run_id": RUN.name, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    daily = pl.read_parquet(POOL)

    # ---------- A. 停牌 ----------
    dl = daily.sort(["symbol", "date"]).with_columns(
        (pl.col("tradestatus") == 0).alias("susp"),
        ((pl.col("tradestatus") == 0) != (pl.col("tradestatus") == 0).shift(1).over("symbol").fill_null(True))
        .cum_sum().over("symbol").alias("run"))
    runs = (dl.filter(pl.col("susp")).group_by(["symbol", "run"])
            .agg(pl.len().alias("days"), pl.col("date").min().alias("start"), pl.col("date").max().alias("end"))
            .filter(pl.col("days") >= 60).sort("days", descending=True))
    top2 = runs.head(2).to_dicts()
    susp_checks = []
    for tr in top2:
        sym = tr["symbol"]
        code = sym[3:] + "." + sym[:2].upper()
        run_days = dl.filter((pl.col("symbol") == sym) & (pl.col("susp")) & (pl.col("run") == tr["run"]))
        sample_days = run_days.select(pl.col("date")).to_series().to_list()
        step = max(1, len(sample_days) // 6)
        picked = sample_days[::step][:6]
        for d in picked:
            df = load_minute_day(d, ["code", "vol"])
            sub = None if df is None else df.filter(pl.col("code") == code)
            n_rows = 0 if sub is None else len(sub)
            zero_vol = 0 if sub is None else int((sub["vol"] == 0).sum())
            susp_checks.append({"symbol": sym, "date": str(d),
                                "suspension_day_rows_in_minute": n_rows,
                                "rows_with_zero_vol": zero_vol,
                                "finding": "占位 bar（241 根、价冻结、全零量）" if (n_rows == 241 and zero_vol == 241) else "异常，需人工复核",
                                "ok_placeholder_not_real_trades": (n_rows == 241 and zero_vol == 241)})
        # 复牌日 = run 结束后的第一个交易日
        after = dl.filter((pl.col("symbol") == sym) & (pl.col("date") > tr["end"])).head(1)
        res_day = after["date"][0]
        df = load_minute_day(res_day, ["code", "trade_time", "vol"])
        sub = None if df is None else df.filter(pl.col("code") == code)
        n_rows = 0 if sub is None else len(sub)
        susp_checks.append({"symbol": sym, "date": str(res_day), "resumption_day_rows_in_minute": n_rows,
                            "expect": 241, "ok": n_rows == 241})
        # 停牌前最后交易日
        before = dl.filter((pl.col("symbol") == sym) & (pl.col("date") < tr["start"])).tail(1)
        pre_day = before["date"][0]
        df = load_minute_day(pre_day, ["code", "trade_time", "vol"])
        sub = None if df is None else df.filter(pl.col("code") == code)
        n_rows = 0 if sub is None else len(sub)
        susp_checks.append({"symbol": sym, "date": str(pre_day), "last_traded_day_rows_in_minute": n_rows,
                            "expect": 241, "ok": n_rows == 241})
        print(f"[A] {sym}: run {tr['start']}..{tr['end']} ({tr['days']}d), "
              f"占位判定 ok={all(c.get('ok_placeholder_not_real_trades', c.get('ok', False)) for c in susp_checks if c['symbol'] == sym)}")
    report["A_suspension"] = {"top_long_runs": [{k: (str(v) if isinstance(v, dt.date) else v) for k, v in t.items()} for t in top2],
                              "checks": [{k: (str(v) if isinstance(v, dt.date) else v) for k, v in c.items()} for c in susp_checks]}

    # ---------- B. 复权口径（高分红股除权日两侧） ----------
    TICKERS = ["sh.601288", "sz.000651", "sh.600519"]
    adj_checks = []
    for sym in TICKERS:
        hist = daily.filter(pl.col("symbol") == sym).sort("date").with_columns(
            pl.col("close").shift(1).alias("prev_close_raw"),
            (pl.col("preclose").cast(pl.Float64) - pl.col("close").shift(1).cast(pl.Float64)).abs().alias("gap"))
        exdays = hist.filter((pl.col("gap") > 0.005) & pl.col("prev_close_raw").is_not_null())["date"].to_list()
        picked = exdays[len(exdays) // 2: len(exdays) // 2 + 2] if len(exdays) > 2 else exdays
        for d in picked:
            row = hist.filter(pl.col("date") == d).row(0, named=True)
            df = load_minute_day(d, ["code", "trade_time", "close", "pre_close"])
            code = sym[3:] + "." + sym[:2].upper()
            m = df.filter((pl.col("code") == code))
            m_first = m.filter(pl.col("trade_time").str.contains(" 09:30:00"))["pre_close"][0]
            m_last = m.filter(pl.col("trade_time").str.contains(" 15:00:00"))["close"][0]
            adj_checks.append({
                "symbol": sym, "ex_div_date": str(d),
                "baostock_prev_day_close_raw": round(row["prev_close_raw"], 4),
                "baostock_preclose_exchange_adj": round(row["preclose"], 4),
                "minute_0930_pre_close": round(float(m_first), 4),
                "minute_preclose_matches": ("exchange_adj" if abs(m_first - row["preclose"]) <= 0.005
                                            else "raw_prev_close" if abs(m_first - row["prev_close_raw"]) <= 0.005
                                            else "neither"),
                "baostock_close": round(row["close"], 4),
                "minute_1500_close": round(float(m_last), 4),
                "minute_close_matches_daily": abs(float(m_last) - row["close"]) <= 0.005,
            })
            print(f"[B] {sym} ex-div {d}: preclose_matches={adj_checks[-1]['minute_preclose_matches']}, "
                  f"close_match={adj_checks[-1]['minute_close_matches_daily']}")
    report["B_adjustment"] = {"note": "实测结论：分钟价为原始未复权价（除权日两侧 15:00 close 与 baostock 未复权 close 一致）；"
                                       "分钟 09:30 pre_close 在除权日 = 原始前收，而非交易所除权昨收（baostock preclose）；"
                                       "G2 若需除权日隔夜腿，昨收应取 baostock preclose",
                              "checks": adj_checks}

    # ---------- C. ST 股在分钟中正常有 bar ----------
    st_syms = (daily.filter(pl.col("isST") == 1).group_by("symbol").agg(pl.len().alias("st_days"))
               .sort("st_days", descending=True).head(3))
    st_checks = []
    for sym in st_syms["symbol"].to_list():
        sdays = daily.filter((pl.col("symbol") == sym) & (pl.col("isST") == 1) & (pl.col("tradestatus") == 1))
        for d in sdays["date"].to_list()[:: max(1, len(sdays) // 3)][:3]:
            df = load_minute_day(d, ["code", "trade_time"])
            code = sym[3:] + "." + sym[:2].upper()
            n = 0 if df is None else int((df["code"] == code).sum())
            st_checks.append({"symbol": sym, "date": str(d), "rows": n, "ok_241": n == 241})
            print(f"[C] {sym} ST-day {d}: rows={n}")
    report["C_st"] = {"checks": st_checks}

    # ---------- D. stk_limit 约束 11:30 触价语义（3 个抽样日） ----------
    limit_checks = []
    for dstr in ["2015-06-01", "2020-06-01", "2024-06-03"]:
        d = dt.date.fromisoformat(dstr)
        p = STK_LIMIT_DIR / f"chunk_{d:%Y%m%d}.csv"
        lim = pl.read_csv(p)  # 列名归一：trade_date,ts_code,up_limit,down_limit
        lim = lim.rename({c: c.strip() for c in lim.columns})
        snap = pl.read_parquet(REPO / "data" / "cache" / "halfday_1130_proto_20260918" / f"snap1130_{d:%Y%m%d}.parquet")
        j = (snap.select(["code", "high", "low"])
             .join(lim.select([pl.col("ts_code").alias("code"), pl.col("up_limit").cast(pl.Float64), pl.col("down_limit").cast(pl.Float64)]),
                   on="code", how="inner"))
        j = j.with_columns(pl.col("high").cast(pl.Float64), pl.col("low").cast(pl.Float64))
        n = len(j)
        out_of_bounds = int(((j["high"] > j["up_limit"] + 0.005) | (j["low"] < j["down_limit"] - 0.005)).sum())
        touched_up = int((j["high"] >= j["up_limit"] - 0.005).sum())
        touched_dn = int((j["low"] <= j["down_limit"] + 0.005).sum())
        limit_checks.append({"date": dstr, "joined": n, "snapshot_rows": len(snap),
                             "outside_limit_bounds": out_of_bounds,
                             "morning_touched_up_limit": touched_up, "morning_touched_down_limit": touched_dn})
        print(f"[D] {dstr}: joined={n}/{len(snap)}, 越界={out_of_bounds}, 上午触板 up={touched_up} down={touched_dn}")
    report["D_stk_limit"] = {
        "batch": "data/raw/xiaodefa/stk_limit/20260913-bulk1（2014-01-02 起，按日 chunk，元=价格单位）",
        "caveats": ["按列名归一读取（深扫已登记文件间列序不一致）；chunk_20220705.csv 首行为空表头，载入需显式列名",
                    "stk_limit 是日级全天涨跌停价，11:30 触价语义只能约束“上午是否触板”，不能证明触板即成交"],
        "checks": limit_checks}

    # ---------- E. 2015-07-01 尾盘零量占位复核（连续 14:54–15:00 全零量 + 日量缺口） ----------
    d = dt.date(2015, 7, 1)
    df = load_minute_day(d, ["code", "trade_time", "close", "vol"])
    tail = df.filter((pl.col("trade_time") >= "2015-07-01 14:54:00") & (pl.col("trade_time") <= "2015-07-01 15:00:00"))
    g = tail.group_by("code").agg(pl.len().alias("bars"), pl.col("vol").sum().alias("tail_vol"))
    cont_zero = g.filter((pl.col("bars") == 7) & (pl.col("tail_vol") == 0))["code"].to_list()
    # 日量缺口：分钟全日总量 vs baostock 日线 volume
    day_total = df.group_by("code").agg(pl.col("vol").sum().alias("min_vol")).filter(pl.col("code").is_in(cont_zero))
    dj = daily.filter(pl.col("date") == d).select(["symbol", "volume"])
    dj = dj.with_columns((pl.col("symbol").str.slice(3) + "." + pl.col("symbol").str.slice(0, 2).str.to_uppercase()).alias("code"))
    cmp_vol = day_total.join(dj, on="code", how="inner").with_columns(
        (pl.col("min_vol") - pl.col("volume").cast(pl.Float64)).abs().alias("vol_gap"))
    n_gap = int((cmp_vol["vol_gap"] > 0.5).sum())
    report["E_20150701_tail_zero_vol"] = {
        "symbols_1454_1500_all_zero_vol": len(cont_zero),
        "of_which_daily_volume_gap": n_gap,
        "examples": cont_zero[:12],
        "matches_registered_defect": "登记为 11 只深市股；实测见上（连续零量口径更宽，含涨停锁死等）",
    }
    print(f"[E] 2015-07-01 连续尾盘零量={len(cont_zero)}, 其中日量缺口={n_gap}")
    if cont_zero:
        b = df.filter(pl.col("code").is_in(cont_zero) & pl.col("trade_time").str.contains(" 11:30:00"))
        report["E_20150701_tail_zero_vol"]["affected_1130_vol_zero"] = int((b["vol"] == 0).sum())
        print(f"[E] 其中 11:30 bar 零量数={int((b['vol'] == 0).sum())}/{len(b)}")

    report["elapsed_seconds"] = round(time.perf_counter() - t0, 1)
    out = RUN / "constraint_checks.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
