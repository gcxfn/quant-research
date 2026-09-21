# -*- coding: utf-8 -*-
"""V2 (F line) -- generate the val-window factor build scripts from the frozen
F2R1 family implementations.

Each replacement asserts a unique hit (or an exact expected count) and the
script aborts on any mismatch: no silent partial adaptation (TL-30
adapt_v3_to_val.py discipline).  ONLY the window is parametrized -- every
formula, filter, rolling window and output schema is the F2R1 implementation
verbatim.  Generated scripts read VAL_WINDOW=dev|val and write
outputs/factor_<window>/<FAM>/.

dev  = the F2R1 frozen window (byte-for-byte port check prereq)
val  = signal months 2021-01..2024-11 (prereg exp-20260920-val-batch sec 3)
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE.parent
F2R1 = RUN_DIR.parent / "20260919T180000-f2r1-factor-batch"

HEADER = '''
# =============================================================================
# V2 val-batch window parametrization (exp-20260920-val-batch, F line).
# dev = the F2R1 frozen window (port check: rebuild must be byte-identical);
# val = signal months 2021-01-01..2024-11-30.
# ONLY the window parameters below are new; every formula / rolling window /
# filter expression is the F2R1 implementation verbatim.
# =============================================================================
import os as _os
_WINDOW = _os.environ.get("VAL_WINDOW", "dev")
assert _WINDOW in ("dev", "val"), _WINDOW
_OUT_ROOT = Path(__file__).resolve().parents[2] / "outputs"
WINDOW_END = date(2024, 12, 31) if _WINDOW == "val" else date(2020, 12, 31)


def sig_cap(fr, hi):
    """Signal-month cap: F2R1's own cap in dev (identity to the frozen
    implementation); the val signal-month window [2021-01-01, 2024-11-30]
    in val mode."""
    if _WINDOW == "val":
        return fr.filter(pl.col("signal_date").is_between(
            date(2021, 1, 1), date(2024, 11, 30)))
    return fr.filter(pl.col("signal_date") <= hi)

'''


def adapt(src: Path, dst: Path, reps: list[tuple[str, str, int]],
          insert_after: str | None = None,
          insert_before: str | None = None) -> None:
    s = io.open(src, encoding="utf-8").read()
    n0 = len(s)
    done = []
    for old, new, cnt in reps:
        c = s.count(old)
        assert c == cnt, (f"{src.name}: expected {cnt} hit(s) for "
                          f"{old[:90]!r}, got {c}")
        s = s.replace(old, new)
        done.append((old.splitlines()[0][:70], cnt))
    if insert_after is not None:
        assert s.count(insert_after) == 1, f"{src.name}: anchor {insert_after!r}"
        s = s.replace(insert_after, insert_after + HEADER)
        done.append((f"INSERT HEADER after {insert_after[:50]!r}", 1))
    if insert_before is not None:
        assert s.count(insert_before) == 1
        s = s.replace(insert_before, HEADER + insert_before)
        done.append((f"INSERT HEADER before {insert_before[:50]!r}", 1))
    dst.parent.mkdir(parents=True, exist_ok=True)
    io.open(dst, "w", encoding="utf-8", newline="\n").write(s)
    print(f"adapted {src.name} -> {dst.name}: {len(done)} groups, "
          f"{n0} -> {len(s)} chars")
    for name, cnt in done:
        print(f"   x{cnt}  {name}")


GEN = RUN_DIR / "scripts/generated"
GEN.mkdir(parents=True, exist_ok=True)


def _out_anchor(fam: str, quote: str = '"') -> str:
    return (f'{quote}artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/'
            f'{fam}{quote}')


# ---------------------------------------------------------------------------
# A family
# ---------------------------------------------------------------------------
A_SRC = F2R1 / "build_a_price_main.py"
adapt(A_SRC, GEN / "f2val_A_price.py", [
    ('OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/A_price"',
     'OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "A_price"', 1),
    ('.filter(pl.col("date") <= date(2020, 12, 31))',
     '.filter(pl.col("date") <= WINDOW_END)', 2),
    ('    assert f["signal_date"].max() <= date(2020, 12, 31)\n',
     '    f = sig_cap(f, date(2020, 12, 31))\n'
     '    assert f["signal_date"].max() <= WINDOW_END\n', 1),
], insert_after='ROOT = Path(r"D:/量化")\n')

# ---------------------------------------------------------------------------
# B family
# ---------------------------------------------------------------------------
B_SRC = F2R1 / "build_b_value_main.py"
adapt(B_SRC, GEN / "f2val_B_value.py", [
    ('OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/B_value"',
     'OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "B_value"', 1),
    ('    read_db("20260909-r1", "20190101", "20201231"),',
     '    read_db("20260909-r1", "20190101",\n'
     '            "20241231" if _WINDOW == "val" else "20201231"),', 1),
    ('.filter(pl.col("date") <= date(2020, 12, 31)).sort("symbol", "date"))',
     '.filter(pl.col("date") <= WINDOW_END).sort("symbol", "date"))', 1),
    ('.filter(pl.col("date") <= date(2020, 12, 31))',
     '.filter(pl.col("date") <= WINDOW_END)', 1),
    ('.filter(pl.col("signal_date") <= date(2020, 11, 30)))',
     '.pipe(lambda _f: sig_cap(_f, date(2020, 11, 30))))', 1),
    ('assert dup == 0 and f["signal_date"].max() <= date(2020, 12, 31)',
     'assert dup == 0 and f["signal_date"].max() <= WINDOW_END', 1),
], insert_after='ROOT = Path(r"D:/量化")\n')

# ---------------------------------------------------------------------------
# C family
# ---------------------------------------------------------------------------
C_SRC = F2R1 / "build_c_micro_main.py"
adapt(C_SRC, GEN / "f2val_C_micro.py", [
    ('OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/C_micro"',
     'OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "C_micro"', 1),
    ('        if not ("20150101" <= k <= "20201231") or p.stat().st_size <= 100:',
     '        _hi = "20241231" if _WINDOW == "val" else "20201231"\n'
     '        if not ("20150101" <= k <= _hi) or p.stat().st_size <= 100:', 1),
    ('.filter(pl.col("date") <= date(2020, 12, 31)).sort("symbol", "date"))',
     '.filter(pl.col("date") <= WINDOW_END).sort("symbol", "date"))', 1),
    ('.filter(pl.col("date") <= date(2020, 12, 31))',
     '.filter(pl.col("date") <= WINDOW_END)', 1),
    ('    f = f.filter(pl.col("signal_date") <= date(2020, 11, 30))\n',
     '    f = sig_cap(f, date(2020, 11, 30))\n', 1),
], insert_after='ROOT = Path(r"D:/量化")\n')

# ---------------------------------------------------------------------------
# D family
# ---------------------------------------------------------------------------
D_SRC = F2R1 / "build_d_fund_main.py"
adapt(D_SRC, GEN / "f2val_D_fund.py", [
    ('OUT = ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/D_fund"',
     'OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "D_fund"', 1),
    ('DEVEND = date(2020, 12, 31)', 'DEVEND = WINDOW_END', 1),
    ('         .filter(pl.col("date") <= date(2020, 12, 31)).sort("symbol", "date"))',
     '         .filter(pl.col("date") <= WINDOW_END).sort("symbol", "date"))', 1),
    ('fin_v = fin.filter(pl.col("signal_date") <= date(2020, 12, 31))',
     'fin_v = fin.filter(pl.col("signal_date") <= WINDOW_END)', 1),
    ('.filter(pl.col("date") <= date(2020, 12, 31))\n         .filter(pl.col("isST")',
     '.filter(pl.col("date") <= WINDOW_END)\n         .filter(pl.col("isST")', 1),
    ('db = pl.read_parquet(ROOT / "artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/B_value/B04.parquet")',
     'db = pl.read_parquet(\n'
     '    _OUT_ROOT / f"factor_{_WINDOW}" / "B_value" / "B04.parquet")', 1),
    ('         .filter(pl.col("signal_date") <= date(2020, 11, 30)))\n',
     '         .pipe(lambda _f: sig_cap(_f, date(2020, 11, 30))))\n', 1),
    ('pit_cov = asof.filter(pl.col("signal_date") <= date(2020, 11, 30))',
     'pit_cov = sig_cap(asof, date(2020, 11, 30))', 1),
], insert_after='ROOT = Path(r"D:/量化")\n')

# ---------------------------------------------------------------------------
# E family
# ---------------------------------------------------------------------------
E_SRC = F2R1 / "f2r1_e_event.py"
_HI = '            "20241231" if _WINDOW == "val" else "20201231"),'
adapt(E_SRC, GEN / "f2val_E_event.py", [
    ('from datetime import date, timedelta',
     'from datetime import date, timedelta\nfrom pathlib import Path', 1),
    ('OUT = os.path.join(RUN, "outputs", "E_event")',
     'OUT = str(_OUT_ROOT / f"factor_{_WINDOW}" / "E_event")', 1),
    ('LAST_SIGNAL = date(2020, 11, 30)  # dev 终点：2020-12 信号不发（标签不跨 dev/val 边界）',
     'LAST_SIGNAL = (date(2024, 11, 30) if _WINDOW == "val"\n'
     '               else date(2020, 11, 30))', 1),
    ('F = read_chunks(os.path.join(TS, "forecast", "20260909-r1", "chunk_*.csv"), "201809", "202012")',
     'F = read_chunks(os.path.join(TS, "forecast", "20260909-r1", "chunk_*.csv"),\n'
     '                "201809",\n'
     '                "202412" if _WINDOW == "val" else "202012")', 1),
    ('X = read_chunks(os.path.join(TS, "express", "20260909-r1", "chunk_*.csv"), "20181231", "20201231")',
     'X = read_chunks(os.path.join(TS, "express", "20260909-r1", "chunk_*.csv"),\n'
     '                "20181231",\n'
     '                "20241231" if _WINDOW == "val" else "20201231")', 1),
    ('R = read_chunks(os.path.join(TS, "repurchase", "20260909-r3", "chunk_*.csv"), "201601", "202012")',
     'R = read_chunks(os.path.join(TS, "repurchase", "20260909-r3",\n'
     '                             "chunk_*.csv"), "201601",\n'
     '                "202412" if _WINDOW == "val" else "202012")', 1),
    ('H = read_chunks(os.path.join(TS, "stk_holdertrade", "20260909-r3", "chunk_*.csv"),\n                "201601", "202012")',
     'H = read_chunks(os.path.join(TS, "stk_holdertrade", "20260909-r3",\n'
     '                             "chunk_*.csv"), "201601",\n'
     '                "202412" if _WINDOW == "val" else "202012")', 1),
    ('S = read_chunks(os.path.join(TS, "share_float", "20260909-r3", "chunk_*.csv"),\n                "201601", "202012")',
     'S = read_chunks(os.path.join(TS, "share_float", "20260909-r3",\n'
     '                             "chunk_*.csv"), "201601",\n'
     '                "202412" if _WINDOW == "val" else "202012")', 1),
    ('    read_chunks(os.path.join(TS, "dividend", "20260909-r3", "chunk_*.csv"),\n                "20180101", "20201231"),',
     '    read_chunks(os.path.join(TS, "dividend", "20260909-r3", "chunk_*.csv"),\n'
     '                "20180101",\n'
     '                "20241231" if _WINDOW == "val" else "20201231"),', 1),
    ('DEV_LO = date(2015, 1, 1)\nDEV_HI = date(2020, 12, 31)',
     'DEV_LO = date(2021, 1, 1) if _WINDOW == "val" else date(2015, 1, 1)\n'
     'DEV_HI = date(2024, 12, 31) if _WINDOW == "val" else date(2020, 12, 31)', 1),
    ('            for s in me_pairs[t]:\n                rows.append((s, t, float(m.get(s, 0.0))))',
     '            for s in me_pairs[t]:\n'
     '                if _WINDOW == "val" and not (\n'
     '                        date(2021, 1, 1) <= t <= date(2024, 11, 30)):\n'
     '                    continue\n'
     '                rows.append((s, t, float(m.get(s, 0.0))))', 1),
    ('            for s, v in m.items():\n                if v is not None:\n                    rows.append((s, t, float(v)))',
     '            for s, v in m.items():\n'
     '                if _WINDOW == "val" and not (\n'
     '                        date(2021, 1, 1) <= t <= date(2024, 11, 30)):\n'
     '                    continue\n'
     '                if v is not None:\n'
     '                    rows.append((s, t, float(v)))', 1),
    # --- E16 correction: the FROZEN F2R1 E16.parquet was overwritten by
    # tmp_accept/fix_E16_dupcount.py after a double-count defect was found
    # (348 duplicate dividend rows / 300 symbols survived the agent-level
    # all-column unique()).  Reproducing the frozen artifact requires the same
    # event-level dedup, so this block re-implements that correction verbatim
    # (only the ex_date chunk ranges are window-parametrized).  No other E
    # factor is touched.
    ('def build_frame(fid: str) -> pl.DataFrame:\n    rows = []\n',
     '''def _e16_fixed_frame():
    """fix_E16_dupcount.py verbatim: 5-column dividend load + event dedup."""
    def read5(pattern, lo, hi):
        fr = []
        for p in sorted(glob.glob(pattern)):
            key = (os.path.basename(p).replace("chunk_period_", "chunk_")
                   .replace("chunk_", "").replace(".csv", ""))
            if not (lo <= key <= hi) or os.path.getsize(p) <= 100:
                continue
            df = pl.read_csv(p, infer_schema_length=10000)
            if df.height:
                cols = [c for c in ["ts_code", "div_proc", "ann_date",
                                    "ex_date", "cash_div"] if c in df.columns]
                df = df.select(cols).with_columns(
                    [pl.col(c).cast(pl.Float64, strict=False)
                     for c in ("cash_div",)])
                fr.append(df)
        return pl.concat(fr, how="diagonal")

    v = pl.concat([
        read5(os.path.join(TS, "dividend", "20260913-r2", "chunk_*.csv"),
              "20150101", "20171231"),
        read5(os.path.join(TS, "dividend", "20260909-r3", "chunk_*.csv"),
              "20180101", "20241231" if _WINDOW == "val" else "20201231"),
    ], how="diagonal")
    v = v.with_columns(pl.col("cash_div").cast(pl.Float64, strict=False)
                       .fill_null(0.0))
    v = v.with_columns(
        pl.col("ann_date").cast(pl.String).str.to_date("%Y%m%d"),
        pl.col("ex_date").cast(pl.String).str.to_date("%Y%m%d"))
    v = (v.filter(pl.col("ts_code").str.contains("."))
         .with_columns((pl.col("ts_code").str.split(".").list.last()
                        .str.to_lowercase() + "." +
                        pl.col("ts_code").str.split(".").list.first())
                       .alias("symbol"))
         .filter(pl.col("div_proc") == "实施")
         .filter(pl.col("ex_date").is_not_null())
         .filter(pl.col("ex_date") <= LAST_SIGNAL))
    v = (v.unique(subset=["symbol", "ex_date", "cash_div"])
         .unique(subset=["symbol", "ex_date"], keep="first"))
    rows = []
    for t in me_dates:
        w = v.filter((pl.col("ex_date") > t - timedelta(days=365))
                     & (pl.col("ex_date") <= t))
        dv = w.group_by("symbol").agg(pl.col("cash_div").sum().alias("_d"))
        cl = me_close.filter(pl.col("date") == t).select("symbol", "close")
        rows.append(dv.join(cl, on="symbol").with_columns(
            (pl.col("_d") / pl.col("close")).alias("value"),
            pl.lit(t).alias("signal_date")).select("symbol", "signal_date",
                                                   "value"))
    return pl.concat(rows).sort("symbol", "signal_date")


def build_frame(fid: str) -> pl.DataFrame:
    if fid == "E16":
        df = _e16_fixed_frame()
        assert df["signal_date"].max() <= FREEZE_END, f"{fid} 冻结线突破"
        assert df["signal_date"].max() <= LAST_SIGNAL, f"{fid} 超 dev 窗"
        if _WINDOW == "val":
            df = df.filter(pl.col("signal_date").is_between(
                date(2021, 1, 1), date(2024, 11, 30)))
        return df
    rows = []
''', 1),
], insert_after='ROOT = r"D:\\量化"\n')


# ---------------------------------------------------------------------------
# F family
# ---------------------------------------------------------------------------
F_SRC = F2R1 / "f_xsec_build.py"
adapt(F_SRC, GEN / "f2val_F_xsec.py", [
    ('OUT = RUN / "outputs/F_xsec"',
     'OUT = _OUT_ROOT / f"factor_{_WINDOW}" / "F_xsec"', 1),
    ('DEV_PANEL_END = date(2020, 12, 31)   # 评估面板硬截断（val 2021-2024 零接触）',
     'DEV_PANEL_END = WINDOW_END', 1),
    ('SIG_END = date(2020, 12, 31)         # 因子 signal_date 上限（断言 <= 2024-12-31）',
     'SIG_END = (date(2024, 11, 30) if _WINDOW == "val"\n'
     '           else date(2020, 12, 31))', 1),
    ('me_sig = month_ends_all.filter(pl.col("me") <= SIG_END)["me"].to_list()',
     'me_sig = month_ends_all.filter(pl.col("me") <= SIG_END)["me"].to_list()\n'
     'if _WINDOW == "val":\n'
     '    me_sig = [d for d in me_sig if date(2021, 1, 1) <= d <= SIG_END]', 1),
    ('.filter(pl.col("me") < date(2020, 12, 1))  # 2020-12 信号标签跨年不入评估',
     '.filter(pl.col("me") < (date(2024, 12, 1) if _WINDOW == "val"\n'
     '                            else date(2020, 12, 1)))', 1),
    ('(RUN / "f_xsec_summary.json").write_text(',
     '(_OUT_ROOT / f"factor_{_WINDOW}" / "f_xsec_summary.json").write_text(',
     1),
], insert_after='ROOT = Path(r"D:/\u91cf\u5316")\n')

print("\nall 6 factor family scripts adapted")
