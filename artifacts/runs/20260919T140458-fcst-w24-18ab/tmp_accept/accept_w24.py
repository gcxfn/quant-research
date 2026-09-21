# Main-conversation acceptance for T1 batch_024 v2 (ASCII-safe): natural-key join
import csv, glob, io, json, os, random, sys
import polars as pl

root = r"D:\量化"
feat = os.path.join(root, "data", "features", "fcst-reason-struct-full-20260918")
raw_dir = os.path.join(root, "data", "raw", "tushare", "forecast", "20260909-r1")
VOCAB = {"demand_up","demand_down","price_up","price_down","orders","cost_up","cost_down",
         "fx","impairment","non_recurring","ma_restructuring","epidemic_shock","accounting",
         "core_ops","other"}

rows = [json.loads(l) for l in open(os.path.join(feat,"batch_024.jsonl"), encoding="utf-8") if l.strip()]
assert len(rows) == 600, len(rows)
assert all(r["struct_version"] == "llm-v1" for r in rows)
assert all(r["primary_code"] in VOCAB for r in rows)
assert all(r["secondary_code"] is None or r["secondary_code"] in VOCAB for r in rows)
assert all(r["supports_direction"] in (-1,0,1) and r["confidence"] in ("high","low") for r in rows)
assert all(0 < len(r["key_quote"]) <= 40 for r in rows)
keys = [(r["ts_code"], r["end_date"], r["ann_date"], r["update_flag"]) for r in rows]
assert len(set(keys)) == 600, "duplicate natural keys"
print("structure: 600 rows, llm-v1, vocab/sd/conf/quote-len OK, unique natural keys")

# natural-key join to row_index must be bijective onto ordinals 13800-14399
idx = pl.read_parquet(os.path.join(feat, "row_index.parquet")).filter(pl.col("ordinal").is_between(13800, 14399))
idxmap = {}
for r in idx.to_dicts():
    k = (r["ts_code"], str(r["end_date"]), str(r["ann_date"]), str(r["update_flag"]))
    idxmap[k] = r["ordinal"]
miss = [k for k in keys if k not in idxmap]
assert not miss, f"join misses: {miss[:3]}"
ords = sorted(idxmap[k] for k in keys)
assert ords == list(range(13800, 14400)), "ordinal span mismatch"
print("join: 600/600 bijective onto ordinals 13800-14399")

# raw CSVs: map natural key -> change_reason list
raw = {}
for fp in sorted(glob.glob(os.path.join(raw_dir, "chunk_*.csv"))):
    with io.open(fp, encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            k = (r.get("ts_code"), r.get("end_date"), r.get("ann_date"), r.get("update_flag"))
            raw.setdefault(k, []).append(r.get("change_reason") or "")
print("raw chunks keys:", len(raw))

random.seed(20260919)
fixed = [13920, 13936, 13937, 14018]
p6 = random.sample(range(14300, 14400), 5)
others = random.sample([o for o in range(13800, 14300) if o not in fixed], 3)
byord = {idxmap[k]: r for k, r in zip(keys, rows)}
fails = 0; used = 0
for o in fixed + p6 + others:
    row = byord[o]
    cands = raw.get((row["ts_code"], row["end_date"], row["ann_date"], row["update_flag"]), [])
    ok = any(row["key_quote"] in c for c in cands)
    used += 1
    if not ok:
        fails += 1
        print("VERBATIM FAIL ordinal", o)
print(f"verbatim spot-check: {used-fails}/{used} pass; fixed={fixed} part6={sorted(p6)} others={sorted(others)}")

prog = json.load(io.open(os.path.join(feat, "progress.json"), encoding="utf-8"))
b24 = prog["batches"]["24"]
assert b24["n_rows"] == 600 and b24["check_passed"] is True and b24["quote_verbatim_pass_rate"] == 1.0
done = sorted(int(k) for k in prog["batches"])
print("progress: batch24 OK, batches recorded 1..%d continuous=%s" % (max(done), done == list(range(1, max(done)+1))))
print("batch24: other_rate_primary=%.4f secondary_null=%.4f conf_high=%d" % (
    b24["other_rate_primary"], b24["secondary_null_rate"],
    b24["confidence_distribution"]["high"]))
sys.exit(1 if fails else 0)
