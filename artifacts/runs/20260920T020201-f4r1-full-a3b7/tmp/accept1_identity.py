# F4R1 全期验收第一部分：引擎 sha 亲验 + A0 锚五帧逐字节比对 + manifest 身份
import filecmp
import hashlib
import json
import os

RUN = "D:/量化/artifacts/runs/20260920T020201-f4r1-full-a3b7"
F3R3 = "D:/量化/artifacts/runs/20260919T201500-f3r3-industry-cap-4b2e/outputs"
OUT = os.path.join(RUN, "outputs")

# 1) 引擎 sha
src = "D:/量化/src/quant/backtest/band_engine.py"
h = hashlib.sha256(open(src, "rb").read()).hexdigest()
pin = "7ad35014d72711cb43ab6aedc232d70adf7eece60604b2a057ee039c9bd11e78"
print(f"engine sha: {h}")
print(f"engine sha == pin v1.4: {h == pin}")

# 2) A0 五帧逐字节
frames = ["intents", "fills", "events", "daily_equity", "clips_final"]
for f in frames:
    a = os.path.join(OUT, f"F4R1-A0_{f}.parquet")
    b = os.path.join(F3R3, f"F3R3-A0_{f}.parquet")
    same = os.path.exists(a) and os.path.exists(b) and filecmp.cmp(a, b, shallow=False)
    print(f"A0 {f}: {'BYTE-EQUAL' if same else 'DIFF/MISSING'}")

# 3) manifest 关键身份
m = json.load(open(os.path.join(RUN, "manifest.json"), encoding="utf-8"))
def dig(d, *ks, depth=0):
    for k in ks:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return None
    return d
print(f"status: {m.get('status')}")
for key in ("engine", "engine_sha256", "engine_provenance"):
    if key in m:
        print(f"manifest[{key}]: {str(m[key])[:100]}")
# 搜身份字段
s = json.dumps(m, ensure_ascii=False)
for tag in ("b09242ee542cf675", "4edffc3994fb527a", "2a414174b5df2eee",
            "18486939", "7ad35014", "d9a63f4c", "3c53abf3"):
    print(f"contains {tag}: {tag in s}")
