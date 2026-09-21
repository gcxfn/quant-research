# -*- coding: utf-8 -*-
"""补充核验: 对走了 per-file fallback 的数据集(stk_limit/moneyflow)做单位抽查,
并把结果合并进 deep-scan-20260917 报告。只读 data/raw, 只写 data/_meta/deep-scan-20260917。"""
import json
from pathlib import Path

import polars as pl

RAW = Path("D:/量化/data/raw")
B = Path("D:/量化/data/_meta/deep-scan-20260917")
BS = RAW / "baostock" / "daily" / "sh.600519.csv"


def merge(report_name, batch_key, patch):
    p = B / report_name
    d = json.loads(p.read_text(encoding="utf-8"))
    r = d["batches"][batch_key]
    uc = r.get("unit_check") or {}
    uc.update(patch)
    r["unit_check"] = uc
    if "unit_conclusion" in patch:
        r["unit_check_conclusion"] = patch["unit_conclusion"]
    r["supplemental_check"] = "deepscan_supplement.py (per-file fallback 批次的补查)"
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print("merged:", report_name)


bs = pl.read_csv(BS, infer_schema=False).select(
    pl.col("date").str.replace_all("-", "").alias("d"),
    pl.col("close").cast(pl.Float64).alias("c"),
)

# ---- stk_limit: 600519 涨跌停价 vs 昨收±10%
slf = RAW / "xiaodefa/stk_limit/20260913-bulk1"
mine = pl.read_csv(slf / "chunk_20241231.csv", infer_schema=False).filter(
    pl.col("ts_code") == "600519.SH")
bsmap = dict(zip(bs["d"], bs["c"]))
rows = []
dates = ["20240102", "20240603", "20240930", "20241231"]
for dt in dates:
    f = slf / f"chunk_{dt}.csv"
    if not f.exists():
        continue
    m = pl.read_csv(f, infer_schema=False).filter(pl.col("ts_code") == "600519.SH")
    if m.height:
        prev = bsmap.get(str(int(dt) - 1))
        # 用 baostock 上一交易日: 直接取 d < dt 的最近一天
        earlier = bs.filter(pl.col("d") < dt).sort("d").tail(1)
        prev = earlier["c"][0] if earlier.height else None
        up = float(m["up_limit"][0])
        dn = float(m["down_limit"][0])
        rows.append({"date": dt, "prev_close": round(prev, 2), "up_limit": up, "down_limit": dn,
                     "up_dev_vs_x10": round(up / (prev * 1.1) - 1, 6),
                     "dn_dev_vs_x10": round(dn / (prev * 0.9) - 1, 6)})
ok = rows and all(abs(r["up_dev_vs_x10"]) < 0.005 and abs(r["dn_dev_vs_x10"]) < 0.005 for r in rows)
merge("xiaodefa/stk_limit.json", "xiaodefa/stk_limit/20260913-bulk1", {
    "600519_limit_vs_prevclose_x10pct": {"checked_dates": rows},
    "unit_conclusion": {"limit_price": "元; 与前收盘 ±10% 关系成立" if ok else "与 ±10% 关系不符, 存疑",
                        "confidence": "high" if ok else "low"},
})

# ---- moneyflow: 600519 关键金额列量级 (tushare moneyflow 金额单位通常为万元)
mf = RAW / "xiaodefa/moneyflow/20260913-bulk1"
f24 = mf / "chunk_20240930.csv"
m = pl.read_csv(f24, infer_schema=False).filter(pl.col("ts_code") == "600519.SH")
cols = [c for c in ("net_amount", "buy_lg_amount", "sell_lg_amount", "buy_elg_amount") if c in m.columns]
mag = {}
for c in cols:
    v = float(m[c][0])
    mag[c] = v
# 茅台当日成交额约 30-80 亿元; net_magnitudes 应落在 1e3~1e5 (万元) 或 1e6~1e8 (元)
tot = sum(abs(v) for v in mag.values())
verdict = ("万元量级(单票主力净额数千至数万元档)" if 1e3 < tot < 1e7 else
           "元量级(若各分项绝对值合计落在亿元档)" if 1e8 < tot < 1e10 else
           "量级不确定, 需与成交额交叉核验")
merge("xiaodefa/moneyflow.json", "xiaodefa/moneyflow/20260913-bulk1", {
    "600519_20240930_amounts": mag,
    "unit_note": "tushare moneyflow 文档口径金额为万元; 以上为原始值量级, verdict 基于常识区间",
    "unit_conclusion": {"amount_like_cols": verdict, "confidence": "medium"},
})

# ---- margin_detail: 600519 融资余额量级 (tushare 文档单位: 元)
md = sorted((RAW / "tushare/margin_detail/20260909-r1").glob("chunk_20241*.csv"))
f = md[-1] if md else None
res_md = None
if f:
    m = pl.read_csv(f, infer_schema=False)
    codecol = "ts_code" if "ts_code" in m.columns else m.columns[1]
    row = m.filter(pl.col(codecol) == "600519.SH")
    if row.height:
        pick = {}
        for c in ("rzye", "rqye", "rzyte", "rzche"):
            if c in row.columns:
                pick[c] = float(row[c][0])
        rzye = pick.get("rzye")
        verdict = ("元量级: 茅台融资余额数十亿元 ≈ 1e10" if rzye and 5e9 < rzye < 1e11 else
                   "万元/元量级存疑" if rzye else "n/a")
        res_md = {"file": f.name, "600519": pick, "rzye_verdict": verdict,
                  "unit_conclusion": {"rzye": verdict, "confidence": "medium"}}
p = B / "tushare/margin_detail.json"
d = json.loads(p.read_text(encoding="utf-8"))
for bk, r in d["batches"].items():
    uc = r.get("unit_check") or {}
    uc.update(res_md or {})
    r["unit_check"] = uc
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("merged: margin_detail")
print("moneyflow mag:", mag)
print("stk_limit rows:", rows)
print("margin:", res_md)
