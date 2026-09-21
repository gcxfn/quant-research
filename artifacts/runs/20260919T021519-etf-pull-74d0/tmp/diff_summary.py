# -*- coding: utf-8 -*-
"""Summarize pool diff composition for the report."""
import csv
import json
from pathlib import Path

RUN = Path(r"D:\量化\artifacts\runs\20260919T021519-etf-pull-74d0")
BATCH = Path(r"D:\量化\data\raw\baostock\etf-daily-20260919-r1")

pool = list(csv.DictReader(open(BATCH / "pool_type5.csv", encoding="utf-8")))
diff = json.load(open(RUN / "pool_diff.json", encoding="utf-8"))
bs_only = set(diff["baostock_only"])
ts_only = set(diff["tushare_only"])


def conv(r):
    exch, num = r["code"].split(".")
    return f"{num}.{'SH' if exch == 'sh' else 'SZ'}"


b = [r for r in pool if conv(r) in bs_only and r["pool_source"] == "baostock_query_stock_basic_type5"]
t = [r for r in pool if conv(r) in ts_only]
ip25 = sum(1 for r in b if r["ipoDate"] > "2024-12-31")
ip24 = sum(1 for r in b if r["ipoDate"] <= "2024-12-31")
print("baostock_only:", len(b), "| ipo>2024-12-31:", ip25, "| ipo<=2024-12-31:", ip24)
print("  ipo<=2024 samples:", [(r["code"], r["code_name"], r["ipoDate"]) for r in b if r["ipoDate"] <= "2024-12-31"][:8])
dl = [r for r in t if r["outDate"]]
print("tushare_only:", len(t), "| with outDate:", len(dl), "| without:", len(t) - len(dl))
print("  outDate range:", min((r["outDate"] for r in dl), default=None), "..", max((r["outDate"] for r in dl), default=None))
print("  samples:", [(r["code"], r["code_name"], r["outDate"]) for r in dl[:5]])
sup = [r for r in pool if r["pool_source"] != "baostock_query_stock_basic_type5"]
print("supplement total:", len(sup))
