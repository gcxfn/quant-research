"""主对话对批 27（混合：381 续亏 + 219 续盈）的独立验收抽检。"""
import csv, glob, json, random
import polars as pl

ROOT = r"D:\量化"
FEAT = ROOT + r"\data\features\fcst-reason-struct-full-20260918"
RAW = ROOT + r"\data\raw\tushare\forecast\20260909-r1"
GOOD = {"预增","略增","扭亏","续盈"}
BAD = {"预减","略减","首亏","续亏","增亏","减亏","预亏"}
BULL = {"demand_up","price_up","cost_down"}
BEAR = {"demand_down","price_down","cost_up","fx","impairment","epidemic_shock"}
# 好转向 non_recurring/ma_restructuring/core_ops/orders 视利好向（schema 方向表）

rows = [json.loads(x) for x in open(FEAT + r"\batch_027.jsonl", encoding="utf-8")]
idx = pl.read_parquet(FEAT + r"\row_index.parquet").filter(pl.col("batch_id") == 27)
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
bad_meta = bad_quote = bad_vocab = bad_field = sd_mismatch = 0
for i, rec in enumerate(rows):
    m = meta[15600 + i]
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
    # 方向一致性抽核（强向原因必须与 type 组别一致给出 ±1）
    p = rec["primary_code"]
    if p in BULL or p in BEAR:
        want = 1 if ((m["type"] in BAD and p in BEAR) or (m["type"] in GOOD and p in BULL)) else -1
        if rec["supports_direction"] != want:
            sd_mismatch += 1
print(f"recheck: bad_meta={bad_meta} bad_quote={bad_quote} bad_vocab={bad_vocab} "
      f"bad_field={bad_field} strong-dir mismatches={sd_mismatch}")

random.seed(27)
by_type = {}
for i in random.sample(range(600), 8):
    rec = rows[i]
    t = meta[15600 + i]["type"]
    by_type[i] = t
    orig = reasons[(rec["ts_code"], rec["end_date"], rec["ann_date"], rec["update_flag"])]
    print(f"--- ordinal {15600+i} type={t} primary={rec['primary_code']} "
          f"secondary={rec['secondary_code']} sd={rec['supports_direction']} conf={rec['confidence']}")
    print(f"    quote: {rec['key_quote']}")
    print(f"    orig : {orig[:100]}")
