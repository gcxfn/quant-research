# -*- coding: utf-8 -*-
"""P2-R6 复核 项9：配置冻结时间与哈希、代码未变核对、run 内 config 副本对比。只读。
"""
import hashlib, json, os, datetime

CFG = "configs/experiments/p2r6-etf-rotation.json"
RUN = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

man = json.load(open(f"{RUN}/manifest.json", encoding="utf-8"))
print("run started_at:", man["started_at"], "(UTC) -> 本地", 
      datetime.datetime.fromisoformat(man["started_at"]).astimezone().strftime("%Y-%m-%d %H:%M:%S"))
st = os.stat(CFG)
print("configs/experiments/p2r6-etf-rotation.json mtime:", datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"))
print("frozen config sha256:", sha(CFG))
print("manifest.config_sha256:", man["config_sha256"])
print("一致:", sha(CFG) == man["config_sha256"])

print("\n源码 sha256 vs manifest（运行后代码未变？）:")
for rel in ["src/quant/research/etf_rotation.py", "src/quant/cli/p2r6_etf_rotation.py"]:
    key = rel.replace("/", "\\")
    got = sha(rel)
    print(f"  {rel}: {'一致' if got == man['source_sha256'][key] else '<-- 不一致: '+got+' vs '+man['source_sha256'][key]}")

print("\nuv.lock sha256 一致:", sha("uv.lock") == man["lock_sha256"] if os.path.exists("uv.lock") else "uv.lock 不存在")

cfg_run = json.load(open(f"{RUN}/config.json", encoding="utf-8"))
cfg_frozen = json.load(open(CFG, encoding="utf-8"))
print("\nrun 内 config 副本 vs 冻结配置：")
print("  冻结文件含 liquidity_min_units:", cfg_frozen["universe"]["u3_pit_rules"].get("liquidity_min_units"))
print("  副本含 liquidity_min_units:", cfg_run["universe"]["u3_pit_rules"].get("liquidity_min_units"))
def diffkeys(a, b, prefix=""):
    out = []
    for k in set(list(a.keys()) + list(b.keys())):
        va, vb = a.get(k, "<缺失>"), b.get(k, "<缺失>")
        if isinstance(va, dict) and isinstance(vb, dict):
            out += diffkeys(va, vb, prefix + k + ".")
        elif va != vb:
            out.append((prefix + k, str(va)[:60], str(vb)[:60]))
    return out
d = diffkeys(cfg_frozen, cfg_run)
print("  内容差异键数:", len(d))
for k, a, b in d[:10]:
    print(f"    {k}: 冻结={a} | 副本={b}")

print("\n三次运行的 config_sha256 / lock_sha256:")
for r in ["20260917T230609-p2r6-etf-rotation-f1f60270", "20260917T231139-p2r6-etf-rotation-cf10be51", RUN]:
    mm = json.load(open(f"artifacts/runs/{r}/manifest.json", encoding="utf-8"))
    print(f"  {r.split('-')[-1]}: config={mm['config_sha256'][:16]}… lock={mm['lock_sha256'][:16]}… started={mm['started_at']}")

print("\n冻结配置 status 字段:", cfg_frozen.get("status"), "| preregistered_at:", cfg_frozen.get("preregistered_at"))
print("u1_whitelist_frozen 代码数:", len(cfg_frozen.get("u1_whitelist_frozen", [])))
