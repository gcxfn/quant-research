"""主对话对批 25 的独立验收抽检（独立代码路径，种子 25）。"""
import csv, glob, json, random
import polars as pl

ROOT = r"D:\量化"
FEAT = ROOT + r"\data\features\fcst-reason-struct-full-20260918"
RAW = ROOT + r"\data\raw\tushare\forecast\20260909-r1"

rows = [json.loads(x) for x in open(FEAT + r"\batch_025.jsonl", encoding="utf-8")]
assert len(rows) == 600
idx = pl.read_parquet(FEAT + r"\row_index.parquet").filter(pl.col("batch_id") == 25)
meta = {r["ordinal"]: r for r in idx.iter_rows(named=True)}

reasons = {}
for fp in sorted(glob.glob(RAW + r"\chunk_*.csv")):
    with open(fp, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            reasons[(r["ts_code"].strip(), (r.get("end_date") or "").strip(),
                      (r.get("ann_date") or "").strip(),
                      (r.get("update_flag") or "").strip())] = (r.get("change_reason") or "").strip()

VOCAB = {"demand_up","demand_down","price_up","price_down","orders","cost_up","cost_down",
         "fx","impairment","non_recurring","ma_restructuring","epidemic_shock","accounting",
         "core_ops","other"}
bad_meta = bad_quote = bad_vocab = bad_field = 0
for i, rec in enumerate(rows):
    m = meta[14400 + i]
    if (rec["ts_code"], rec["end_date"], rec["ann_date"], rec["update_flag"]) != \
       (m["ts_code"], m["end_date"], m["ann_date"], m["update_flag"]):
        bad_meta += 1
    orig = reasons[(rec["ts_code"], rec["end_date"], rec["ann_date"], rec["update_flag"])]
    if rec["key_quote"] not in orig or not (0 < len(rec["key_quote"]) <= 40):
        bad_quote += 1
    if rec["primary_code"] not in VOCAB or (
            rec["secondary_code"] is not None and
            (rec["secondary_code"] not in VOCAB or rec["secondary_code"] == rec["primary_code"])):
        bad_vocab += 1
    if rec["supports_direction"] not in (-1, 0, 1) or rec["confidence"] not in ("high", "low") \
            or rec["struct_version"] != "llm-v1":
        bad_field += 1
print(f"independent full recheck: bad_meta={bad_meta} bad_quote={bad_quote} "
      f"bad_vocab={bad_vocab} bad_field={bad_field}")

random.seed(25)
for i in random.sample(range(600), 8):
    rec = rows[i]
    orig = reasons[(rec["ts_code"], rec["end_date"], rec["ann_date"], rec["update_flag"])]
    print(f"--- ordinal {14400+i} type=续亏 primary={rec['primary_code']} "
          f"secondary={rec['secondary_code']} sd={rec['supports_direction']} conf={rec['confidence']}")
    print(f"    quote: {rec['key_quote']}")
    print(f"    orig : {orig[:110]}")

# 代理披露的 14886 与 14530 同文核对
for tgt in (14530, 14886):
    m = meta[tgt]
    print(f"dup-check ordinal {tgt}: {m['ts_code']} ann={m['ann_date']} reason[:50]="
          f"{reasons[(m['ts_code'], m['end_date'], m['ann_date'], m['update_flag'])][:50]}")
