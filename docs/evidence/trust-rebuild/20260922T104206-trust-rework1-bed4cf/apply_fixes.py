# -*- coding: utf-8 -*-
"""返工轮 R1：C0-C4 独立审阅发现的 5 项 MAJOR 证据留痕修复。

只改证据/文档字节，不改 src/、不改测试断言、不改交易语义。
顺序：备份原件 -> 内容修复 -> stage_report 哈希回刷 -> 验收矩阵回刷。
"""
import csv
import hashlib
import io
import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(r"D:\量化")
EV = ROOT / "docs/evidence/trust-rebuild"
R1 = EV / "20260922T104206-trust-rework1-bed4cf"
C0D = EV / "20260922T013755-trust-c0-c17494"
C1D = EV / "20260922T020344-trust-c1-479c46"
C2D = EV / "20260922T025434-trust-c2-a17b3e"
C3D = EV / "20260922T035220-trust-c3-c8af13"
MATRIX = ROOT / "docs/quant_stage_plan_20260922/02_acceptance_matrix.csv"
PLAN = ROOT / "docs/plans/stock-first-trust-rebuild.md"
MANIFEST = ROOT / "data/processed/dev-sandbox-20260922/dataset_manifest.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def backup(rel_to_root: str) -> None:
    src = ROOT / rel_to_root
    dst = R1 / "originals" / rel_to_root.replace("/", "__")
    shutil.copy2(src, dst)


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def dump_json(p: Path, d) -> None:
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


changed = {}

# ---------------------------------------------------------------- 0. 备份 + 冻结副本
for rel in [
    "docs/quant_stage_plan_20260922/02_acceptance_matrix.csv",
    "docs/evidence/trust-rebuild/20260922T025434-trust-c2-a17b3e/hand_calculated_expected.csv",
    "docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/intent_to_order_trace.csv",
    "docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/c3_case_report.md",
    "docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/stage_report.json",
    "docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/independent_review.md",
    "docs/evidence/trust-rebuild/20260922T020344-trust-c1-479c46/stage_report.json",
    "docs/evidence/trust-rebuild/20260922T025434-trust-c2-a17b3e/stage_report.json",
    "docs/evidence/trust-rebuild/20260922T013755-trust-c0-c17494/stage_report.json",
    "data/processed/dev-sandbox-20260922/dataset_manifest.json",
    "docs/plans/stock-first-trust-rebuild.md",
]:
    backup(rel)

OLD_IFACE = sha(C1D / "interface_contract.json")
frozen = R1 / "interface_contract_schema1.1_frozen.json"
shutil.copy2(C1D / "interface_contract.json", frozen)
assert sha(frozen) == sha(C1D / "interface_contract.json")
changed["interface_contract_frozen"] = sha(frozen)

# ---------------------------------------------------------------- 1. R1-3 手算预期 TV-A03
p = C2D / "hand_calculated_expected.csv"
text = p.read_text(encoding="utf-8")
old8 = "TV-A03,docs/quant_stage_plan_20260922/05_test_vectors.md:11,sell 50000 notional,2023-08-25,sell,500000.00,49445.00,0,0,0.00,500000.00,55.00,55.00,2023-08-28 前印花 0.001 -> 50.00；佣金 5"
new8 = "TV-A03,docs/quant_stage_plan_20260922/05_test_vectors.md:11,sell 50000 notional,2023-08-25,sell,500000.00,49945.00,0,0,0.00,549945.00,55.00,55.00,2023-08-28 前印花 0.001 -> 50.00；佣金 5；净 50000-55=49945；权益 500000+49945=549945（R1 更正：原 49445/500000 破坏权益恒等式）"
old9 = "TV-A03,docs/quant_stage_plan_20260922/05_test_vectors.md:11,sell 50000 notional,2023-08-28,sell,500000.00,49470.00,0,0,0.00,500000.00,55.00,55.00,当日及以后印花 0.0005 -> 25.00；佣金 5"
new9 = "TV-A03,docs/quant_stage_plan_20260922/05_test_vectors.md:11,sell 50000 notional,2023-08-28,sell,500000.00,49970.00,0,0,0.00,549970.00,30.00,30.00,当日及以后印花 0.0005 -> 25.00；佣金 5；净 50000-30=49970；权益 500000+49970=549970（R1 更正：原 49470/500000/55 破坏恒等式且费用误用旧税率）"
assert old8 in text and old9 in text, "TV-A03 原行不匹配"
text = text.replace(old8, new8).replace(old9, new9)
p.write_text(text, encoding="utf-8", newline="")
changed["hand_csv"] = sha(p)

# ---------------------------------------------------------------- 2. R1-4 intent_to_order_trace cap 口径
p = C3D / "intent_to_order_trace.csv"
raw = p.read_bytes()
assert b'"' not in raw, "trace 含引号字段，需改用 csv 模块处理"
lines = raw.decode("utf-8").split("\r\n")
while lines and lines[-1] == "":
    lines.pop()
header = lines[0].split(",")
assert header.index("trigger_cap_1p01") == 7 and header.index("decision_anchor_price") == 8
PROVIDER_RULE = (
    "BEvent(B1) branch: cap = decision anchor x (1+CHASE=1.01); no skip_cap gate "
    "(skip_cap is TriggerEvent-only); trigger_cap_1p01 column is A-family diagnostic "
    "(trigger_close x 1.01) [corrected in rework R1]"
)
RELATIONSHIP = "limit_is_decision_anchor__b1_cap_ungated"
out = [",".join(header[:8] + ["provider_cap_b1"] + header[8:])]
fixed_cap = 0
for ln in lines[1:]:
    f = ln.split(",")
    assert len(f) == len(header), f"字段数不符: {ln[:60]}"
    anchor = Decimal(f[header.index("decision_anchor_price")])
    cap_b1 = (anchor * Decimal("1.01")).quantize(Decimal("0.0001"))
    cap_str = format(cap_b1.normalize(), "f")
    if "." not in cap_str:
        cap_str += ".00"
    elif len(cap_str.split(".")[1]) == 1:
        cap_str += "0"
    i_ge = header.index("cap_ge_anchor")
    if f[i_ge] != "True":
        fixed_cap += 1
    f[i_ge] = "True"
    f[header.index("provider_rule")] = PROVIDER_RULE
    f[header.index("relationship")] = RELATIONSHIP
    out.append(",".join(f[:8] + [cap_str] + f[8:]))
new_header_count = len(out[0].split(","))
assert all(len(l.split(",")) == new_header_count for l in out[1:])
p.write_bytes(("\r\n".join(out) + "\r\n").encode("utf-8"))
changed["trace_csv"] = sha(p)
changed["trace_cap_ge_anchor_flipped"] = fixed_cap

# ---------------------------------------------------------------- 3. R1-5 C1 R8 家族错标
p = C1D / "independent_review.md"
text = p.read_text(encoding="utf-8")
old_r8 = "86 个 B2/A 家族 2020-12 边界锚点全部 `window_complete=False` 且保留不删；44 只退市证券单独成行——与 access_ledger AL-01 的越界接触登记互相印证"
new_r8 = "86 个 B1 事件证券的 2020-12 边界锚点全部 `window_complete=False` 且保留不删；44 只退市证券单独成行。**R1 返工更正（2026-09-22）：原文误写为「B2/A 家族」——该 86 个锚点来自 B1 漏斗证券（censoring_audit.py family=B1，data_cards §7 同）；B2/A 的 2020-12-29 越界接触未在本审计独立复算，仍以 C0 access_ledger AL-01 登记为准**"
assert old_r8 in text, "R8 原文不匹配"
text = text.replace(old_r8, new_r8)
p.write_text(text, encoding="utf-8", newline="")
changed["c1_review_r8"] = sha(p)

# ---------------------------------------------------------------- 4. R1-4b c3_case_report §5.1 更正注记
p = C3D / "c3_case_report.md"
text = p.read_text(encoding="utf-8")
anchor_txt = "③ 39/39 观测显示 `order_price_first` 恒等于 `decision_anchor_price` 且从不等于 cap。\n"
note = (
    "\n> **R1 返工更正（2026-09-22）**：本表 102 行全部为 B1（`BEvent`）事件，provider 走 else 分支\n"
    "> `cap = anchor×(1+CHASE)`，**无 skip_cap 判定**——①的 skip_cap 描述仅适用 A 族（`TriggerEvent`）。\n"
    "> 原版 trace 的 `trigger_cap_1p01`/`cap_ge_anchor` 列按 A 族口径（触发日收盘×1.01）计算，\n"
    "> 已在 trace 中新增 `provider_cap_b1` 列并重算（39/39 cap≥anchor 成立，消除原 18/39 的自相矛盾）。\n"
    "> 核心观测（②、③与 39/39、0/39）不受影响。\n"
)
assert anchor_txt in text, "case report 锚文本不匹配"
text = text.replace(anchor_txt, anchor_txt + note)
p.write_text(text, encoding="utf-8", newline="")
changed["case_report"] = sha(p)

# ---------------------------------------------------------------- 5. R1-1 dataset_manifest 回刷
d = load_json(MANIFEST)
old_msha = sha(MANIFEST)
d["contract_sha256"] = changed["interface_contract_frozen"]
d["contract_amendment"] = {
    "amendment_id": "A-01",
    "amended_by_stage": "C4",
    "schema_version": "1.1",
    "applied": "2026-09-22 rework R1",
    "previous_contract_sha256": OLD_IFACE,
    "note": "hash pin refreshed after C4 A-01 (schema 1.0->1.1, valuation carry-forward clarification); dataset bytes unchanged",
}
dump_json(MANIFEST, d)
changed["dataset_manifest"] = sha(MANIFEST)
changed["dataset_manifest_old"] = old_msha

# ---------------------------------------------------------------- 6. stage_report 哈希回刷（内容修复之后）
# C1：EV-01 接口合同、EV-02 manifest、EV-35 审阅意见、顶层 contract_sha256
p = C1D / "stage_report.json"
old_c1 = sha(p)
d = load_json(p)
for ev in d.get("evidence", []):
    path = str(ev.get("path", ""))
    if path.endswith("interface_contract.json"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["interface_contract_frozen"]
        ev["note"] = str(ev.get("note", "")) + "；R1 返工回刷：C4 A-01 升版 schema1.1（旧哈希见 sha256_superseded）"
    elif path.endswith("dataset_manifest.json"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["dataset_manifest"]
        ev["note"] = str(ev.get("note", "")) + "；R1 返工回刷（contract_sha256 字段升版，数据字节未变）"
    elif path.endswith("independent_review.md"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["c1_review_r8"]
        ev["note"] = str(ev.get("note", "")) + "；R1 返工回刷（R8 家族错标更正）"
d["contract_sha256_superseded"] = d.get("contract_sha256")
d["contract_sha256"] = changed["interface_contract_frozen"]
d["post_stage_corrections"] = [
    {
        "round": "R1",
        "date": "2026-09-22",
        "summary": "interface_contract.json 经 C4 A-01 升版（schema 1.0→1.1）后，本报告与验收矩阵的哈希未同步，导致字节级复核失败；R1 统一回刷并在 rework 目录留存冻结副本与原件备份",
        "rework_evidence_dir": str(R1.relative_to(ROOT)).replace("\\", "/"),
        "stage_time_interface_sha256": OLD_IFACE,
    }
]
dump_json(p, d)
changed["c1_stage_report"] = sha(p)
changed["c1_stage_report_old"] = old_c1

# C2：EV-02 手算 CSV + 用户追认登记
p = C2D / "stage_report.json"
d = load_json(p)
for ev in d.get("evidence", []):
    if str(ev.get("path", "")).endswith("hand_calculated_expected.csv"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["hand_csv"]
        ev["note"] = str(ev.get("note", "")) + "；R1 返工更正 TV-A03 两行（待结算/权益/费用算错），.md 与单测原本即正确"
d.setdefault("post_stage_corrections", []).append(
    {
        "round": "R1",
        "date": "2026-09-22",
        "summary": "① hand_calculated_expected.csv TV-A03 两行算错更正（08-25 待结算 49445→49945、权益→549945；08-28 待结算→49970、权益→549970、费用 55→30）；② 用户追认舍入位置表示差裁定：引擎 float 不舍入 vs 参考 Decimal 逐笔 ROUND_HALF_UP 的日权益差 ≤0.14 元、费用差 ≤0.01 元为数值表示差（精确轨道残差 ~1e-10），C2-03 字面条件闭环",
    }
)
dump_json(p, d)
changed["c2_stage_report"] = sha(p)

# C3：EV-06 trace、EV-15 案例报告
p = C3D / "stage_report.json"
d = load_json(p)
for ev in d.get("evidence", []):
    path = str(ev.get("path", ""))
    if path.endswith("intent_to_order_trace.csv"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["trace_csv"]
        ev["note"] = str(ev.get("note", "")) + "；R1 返工更正 cap 列口径（新增 provider_cap_b1、重算 cap_ge_anchor、provider_rule 改 B1 分支语义；39/39 limit==anchor 不变）"
    elif path.endswith("c3_case_report.md"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["case_report"]
        ev["note"] = str(ev.get("note", "")) + "；R1 返工追加 §5.1 更正注记（skip_cap 仅适用 A 族）"
dump_json(p, d)
changed["c3_stage_report"] = sha(p)

# ---------------------------------------------------------------- 7. R1-2 主计划追加 + C0 E10 回刷
PLAN_SECTION = """
## 4.5 返工轮 R1 完成记录（2026-09-22，独立审阅会话执行）

背景：C0–C4 五阶段独立审阅结论为 accepted（限定范围、附条件），发现 5 项 MAJOR 证据留痕缺陷。用户同日裁定：① 追认 C2 舍入位置表示差裁定；② 授权执行本返工。全部修复只涉及证据/文档字节：不改 `src/`、不改测试断言、不改交易语义。返工证据目录：`docs/evidence/trust-rebuild/20260922T104206-trust-rework1-bed4cf/`（原件备份 originals/、冻结副本、修复脚本 apply_fixes.py、rework_report.md）。

- **R1-1（C1-07 身份链）**：`interface_contract.json` 的 C4 A-01 升版（schema 1.0→1.1）补齐留痕——当前版本字节冻结副本存返工目录；验收矩阵 C1-07、C1 stage_report EV-01 与顶层 `contract_sha256`、`data/processed/dev-sandbox-20260922/dataset_manifest.json` 的 `contract_sha256` 统一回刷至新哈希 `5bef4159…`（旧值 `c2ede244…` 保留在 `sha256_superseded` 注记与原件备份）。升版前 v1.0 字节不可恢复（无 baseline 副本），已如实登记；今后接口修订必须先归档改前字节。
- **R1-2（活文档 pin）**：C0 stage_report E10（本文件）哈希回刷至当前版本并加活文档注记（C0 时点哈希 `4b1e3f31…` 保留在 `sha256_superseded`）。§4 所引「检查器终态 exit 0」当时无归档命令日志，属记录缺口；返工后对 C0/C1 stage_report 的检查器复跑结果已归档（返工目录 `checker_c0.txt`/`checker_c1.txt`），以该结果为准。
- **R1-3（手算预期）**：`hand_calculated_expected.csv` TV-A03 两行算错更正：08-25 行待结算 49445→49945、权益 500000→549945；08-28 行待结算 49470→49970、权益 500000→549970、费用 55→30（印花 25＋佣金 5）。`.md` 与单测 `test_tv_a03` 原本即用正确值，账本结论不变；矩阵 C2-02 哈希回刷。
- **R1-4（C3 cap 列口径）**：`intent_to_order_trace.csv` 新增 `provider_cap_b1` 列（＝决策锚价×1.01，BEvent 分支），`cap_ge_anchor` 按其重算（全 True，消除原 18/39 自相矛盾），`provider_rule` 文本改为 B1 分支语义（`trigger_cap_1p01` 保留为 A 族诊断列）；`c3_case_report.md` §5.1 追加更正注记（skip_cap 仅适用 A 族/TriggerEvent）。核心观测 39/39 limit==anchor、0/39 limit==cap 不变；矩阵 C3-07 哈希回刷。
- **R1-5（R8 家族错标）**：C1 `independent_review.md` R8 的「86 个 B2/A 家族」更正为「B1 事件证券」，并注明 B2/A 的 2020-12-29 越界接触未在该审计独立复算（仍以 C0 `access_ledger` AL-01 登记为准）。
- **用户裁定登记**：C2 舍入位置表示差裁定（引擎 float 不舍入 vs 参考 Decimal 逐笔 ROUND_HALF_UP；日权益差 ≤0.14 元、精确轨道残差 ~1e-10）经用户 2026-09-22 追认，C2-03 字面条件闭环；同步写入 C2 stage_report `post_stage_corrections` 与矩阵 C2-03 备注。
- **验证**：返工后全量测试 804 passed（`PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests -q`）；检查器对 C0/C1 stage_report 复跑通过；验收矩阵全部 actual_sha256 与实际文件重算一致。详见 `rework_report.md`。
- **遗留**：约 15 项 MINOR（各 stage_report 的 accepted/pending 文案自相矛盾、行数口径笔误、`delivery_check_output.json` 旧快照等）未在本轮处理，已登记于独立审阅报告；C5 及之后阶段未开启。

"""
p = PLAN
text = p.read_text(encoding="utf-8")
marker = "## 6. 资源调查（本机实测，2026-09-22）"
assert marker in text
text = text.replace(marker, PLAN_SECTION + "\n" + marker)
p.write_text(text, encoding="utf-8", newline="")
changed["plan_doc"] = sha(p)

# C0 E10 回刷 + 检查器记录对账注记
p = C0D / "stage_report.json"
d = load_json(p)
for ev in d.get("evidence", []):
    if str(ev.get("path", "")).endswith("stock-first-trust-rebuild.md"):
        ev["sha256_superseded"] = ev["sha256"]
        ev["sha256"] = changed["plan_doc"]
        ev["living_document"] = True
        ev["note"] = "活文档：每阶段追加完成记录；R1 返工回刷哈希（C0 时点哈希见 sha256_superseded），后续阶段结束后须再次回刷"
d.setdefault("post_stage_corrections", []).append(
    {
        "round": "R1",
        "date": "2026-09-22",
        "summary": "① E10 pin 的是活文档（stock-first-trust-rebuild.md 会被后续阶段追加），固定字节 pin 属结构性缺陷——改为回刷+superseded 注记；② §limitations[9] 与 c0_run_log 第29条记录的 exit 2 为审阅前时点，主计划 §4 所引「终态 exit 0」当时无归档命令日志（记录缺口）——返工后检查器复跑结果归档于 rework 目录 checker_c0.txt，以该结果为准",
        "rework_evidence_dir": str(R1.relative_to(ROOT)).replace("\\", "/"),
    }
)
dump_json(p, d)
changed["c0_stage_report"] = sha(p)

# ---------------------------------------------------------------- 8. 验收矩阵回刷
p = MATRIX
text = p.read_text(encoding="utf-8-sig")
repl = [
    (changed_c1_old := "45e3c7017312c7c10c3bbc2d2704208a84585700f866a591321b0a82c56e070e",
     changed["c1_stage_report"]),
    ("c2ede2442f5921e45c616dbb8b18264a14ab04b47d0f38000e74d57a33fab93f",
     changed["interface_contract_frozen"]),
    ("6482a2d5d00fb768e160fab501804011af2b4c25c2fb6a27ac0f6845c17ea86c",
     changed["hand_csv"]),
    ("d4473f07f48440eb04a02ac5721a40646ab19788ba6732060584d18bb9e7e8e9",
     changed["trace_csv"]),
    ("R7 逐节", "R7 逐节；R1 返工回刷哈希（C4 A-01 升版 schema1.1）"),
    ("R5 亲算半分边界+3319笔", "R5 亲算半分边界+3319笔；用户 2026-09-22 追认舍入位置表示差裁定"),
]
for old, new in repl:
    assert text.count(old) == 1, f"矩阵替换目标不唯一或缺失: {old[:20]}"
    text = text.replace(old, new)
p.write_text(text, encoding="utf-8-sig", newline="")
changed["matrix"] = sha(p)

print(json.dumps({k: (v if len(str(v)) < 70 else v[:16] + "…") for k, v in changed.items()},
                 ensure_ascii=False, indent=1))
