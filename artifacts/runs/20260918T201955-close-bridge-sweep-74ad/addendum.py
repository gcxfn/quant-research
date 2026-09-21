# -*- coding: utf-8 -*-
"""addendum: 残余不匹配的细分刻画（fen 差、板块集中度、SZ 2015 日期聚类）。只读。"""
import json
import sys

import polars as pl

sys.path.insert(0, r"D:\量化\artifacts\runs\20260918T201955-close-bridge-sweep-74ad")
from sweep import HALFDAY_DIR, OFFICIAL_PQ, RUN_DIR, exchange  # noqa: E402

YEARS = list(range(2015, 2025))
sh_post_rows = []
sz_rows = []
board_den = []

for y in YEARS:
    pm = (
        pl.scan_parquet(rf"{HALFDAY_DIR}\year={y}\bars.parquet")
        .filter(pl.col("session") == "pm")
        .select("symbol", "trade_date", "close")
        .collect()
    )
    off = (
        pl.scan_parquet(OFFICIAL_PQ)
        .filter(pl.col("date").dt.year() == y)
        .select("symbol", pl.col("date").alias("trade_date"), pl.col("close").alias("off_close"))
        .collect()
    )
    # 分母：沪市按板块（688 vs 非六八八）
    board_den.append(
        pm.filter(exchange(pl.col("symbol")) == "sh")
        .group_by(pl.col("symbol").str.starts_with("sh.688").alias("is_688"))
        .len()
        .with_columns(pl.lit(y).alias("year"))
    )
    j = pm.join(off, on=["symbol", "trade_date"], how="inner")
    rel = (pl.col("close") / pl.col("off_close") - 1.0).abs()
    j = j.with_columns(rel.alias("abs_rel"), (rel > 1e-6).alias("mm6"))
    sh_post_rows.append(
        j.filter((exchange(pl.col("symbol")) == "sh") & pl.col("mm6")
                 & (pl.col("trade_date") >= pl.date(2018, 8, 20)))
        .select("trade_date", "symbol", "close", "off_close")
    )
    sz_rows.append(
        j.filter((exchange(pl.col("symbol")) == "sz") & pl.col("mm6"))
        .select(pl.lit(y).alias("year"), "trade_date", "symbol", "close", "off_close")
    )

sh_post = pl.concat(sh_post_rows).with_columns(
    ((pl.col("close") - pl.col("off_close")) * 100).round(2).abs().alias("diff_fen")
)
sz = pl.concat(sz_rows).with_columns(
    ((pl.col("close") - pl.col("off_close")) * 100).round(2).abs().alias("diff_fen")
)
sh_post.write_csv(rf"{RUN_DIR}\outputs\sh_post_switch_detail.csv")
sz.write_csv(rf"{RUN_DIR}\outputs\sz_mismatch_detail.csv")

den = pl.concat(board_den).group_by("year", "is_688").sum().select("year", "is_688", "len")
sh_post_bd = (
    sh_post.with_columns(pl.col("symbol").str.starts_with("sh.688").alias("is_688"))
    .group_by("is_688").len()
)
den_tot = den.group_by("is_688").sum().select("is_688", "len")
print("== SH post-switch residual by board ==")
print(sh_post_bd.join(den_tot, on="is_688", suffix="_den").with_columns(
    (pl.col("len") / pl.col("len_den")).alias("rate")))
print("== SH post diff_fen distribution ==")
print(sh_post.group_by("diff_fen").len().sort("diff_fen").head(10))
print(sh_post.select(pl.col("diff_fen").max().alias("max_fen"),
                     (pl.col("diff_fen") <= 1.01).mean().alias("share_le_1fen")))
print("== SZ diff_fen distribution (all years) ==")
print(sz.group_by("diff_fen").len().sort("diff_fen").head(10))
print(sz.select((pl.col("diff_fen") <= 1.01).mean().alias("share_le_1fen"),
                pl.col("diff_fen").max().alias("max_fen")))
print("== SZ per-year mismatch rows ==")
print(sz.group_by("year").len().sort("year"))
print("== SZ 2015 top dates ==")
print(sz.filter(pl.col("year") == 2015).group_by("trade_date").len()
      .filter(pl.col("len") > 20).sort("len", descending=True).head(12))
print("== SZ 2015 sample rows ==")
print(sz.filter(pl.col("year") == 2015).sort("diff_fen", descending=True).head(5))
print("== SH post sample rows (largest diff) ==")
print(sh_post.sort("diff_fen", descending=True).head(5))
print("== SH post top residual dates ==")
print(sh_post.group_by("trade_date").len().sort("len", descending=True).head(10))
