# -*- coding: utf-8 -*-
"""exp-20260920-factor-round-f3r4 -- doc patches (ledger / README / main plan).

Literal replacement + assertions; UTF-8 without BOM, LF.  Nothing else in the
three documents is touched.
"""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
LEDGER = ROOT / "docs/evidence/trial-ledger.md"
README = ROOT / "README.md"
PLAN = ROOT / "docs/plans/daily-short-term-rebuild.md"
RUN_ID = "20260920T122905-f3r4-reason-int-2301"

# --- ledger: insert TL-39 after the TL-38 row -------------------------------
tl39 = (
    "| TL-39 | 2026-09-20 | exp-20260920-factor-round-f3r4 | "
    "F3R4 归因事件信息并入 F3 组合（T1 下游：impairment 加分 / price_up 压制 / "
    "归因当第 18 因子；三臂全部在 composite parquet 层实现，底盘 runner 只换"
    "输入路径+产物前缀+引擎 pin，锚为前置门槛） | 3 | 0 | "
    "**H1 成立（1/3 过线，探索级）**：A 加分臂（impairment +1σ/price_up −1σ，"
    "b=0.10164738676824621=71 信号月截面 std 中位数）净 CAGR **+5.3356%**、"
    "Δ 基线 **+0.4583pp** ≥ 冻结 +0.30pp 线，maxDD −17.8485% 与基线逐位相同"
    "（优于 −1.0pp 恶化线）；B 压制臂 +4.9440%（+0.0667pp）与 C 第 18 因子臂 "
    "+4.8485%（−0.0288pp）未过线；三臂失败门与基线完全相同（门 3 优势年 4/6、"
    "门 8 v3 交付 83.3~85.7%），风险门 4/5/6 全过、无臂达 ≥10% 目标列；"
    "**座位机制清晰：A 把 impairment 座位月 3→33（26 只、单只 ≤2 月）、"
    "price_up 13→0；只做去坏的 B 仅 +0.067pp（price_up 在基线本就几乎不入选）"
    "——增益在加分侧**；**窗口敏感性为主要折扣项**：窗 20/40 重跑 +4.6791%/"
    "+4.7364%（均低于基线，非单调），只有冻结 60 交易日窗过线；b 的 68/71 月"
    "歧义零影响（Δ 0.0000pp）；标记 1,248 对/27 月/365 股、冲突 0 例、"
    "可逆性与 FA-S2（max diff 0）与 C 对齐门全过；**探索级重申：事件研究已消费"
    "同段 dev，本轮为同一样本二次使用，不得称验证；val 2021-2024 零接触** | "
    "293→**296** | run `20260920T122905-f3r4-reason-int-2301`；锚（未改动 "
    "F3-EW composite 跑派生 runner）五帧 .equals 5/5 + net_cagr/maxDD 逐位相等"
    "（v1.4.1≡v1.3 非 zones 再实证）；独立复核五项全过（标记向前重算一致、"
    "调整恒等式 106,266 行、座位独立重建 71/71 月×3 臂、头条数字独立公式差 0、"
    "判定算术）；墙钟 71.3s/峰值 RSS 4.76GB；[结果](../research/"
    "exp-20260920-factor-round-f3r4.md) | val 零接触 |\n"
)

t = LEDGER.read_text(encoding="utf-8")
assert "TL-38 |" in t and "TL-39" not in t, t.count("TL-38 |")
i = t.index("| TL-38 |")
j = t.index("\n", i) + 1
t2 = t[:j] + tl39 + t[j:]
assert t2.count("| TL-38 |") == 1 and t2.count("| TL-39 |") == 1
assert "| TL-40 |" not in t2
LEDGER.write_text(t2, encoding="utf-8", newline="\n")
print("ledger: TL-39 inserted after TL-38")

# --- README: append one status paragraph -----------------------------------
readme_add = (
    "**F3R4 归因事件信息并入 F3 组合收官（[预登记](docs/research/"
    "exp-20260920-factor-round-f3r4-prereg.md) + [配置](configs/experiments/"
    "f3r4-reason-integration.json) + [结果](docs/research/"
    "exp-20260920-factor-round-f3r4.md)；T1 下游应用，三臂全部在 composite "
    "parquet 层实现）**：**H1 成立（1/3 过线，探索级）**——A 加分臂"
    "（impairment +1σ / price_up −1σ）净 CAGR **+5.3356%**，Δ 基线 "
    "**+0.4583pp** ≥ 冻结 +0.30pp 线、maxDD 与基线逐位相同（−17.85%）；"
    "B 压制臂 +4.9440%（+0.0667pp）、C 第 18 因子臂 +4.8485%（−0.0288pp）"
    "未过线；三臂失败门与基线完全相同（门 3 优势年 4/6、门 8 v3 交付 "
    "83.3~85.7%），风险门 4/5/6 全过、无臂达 ≥10% 目标列。座位机制：A 把 "
    "impairment 座位月 3→33（26 只、分散）、price_up 13→0；只做去坏的 B 仅 "
    "+0.067pp——**增益在加分侧**。**折扣项**：窗口敏感性（20/40 窗为 +4.68%/"
    "+4.74%，均低于基线、非单调，只有冻结 60 交易日窗过线）与“同段 dev 二次"
    "使用”的探索级身份——**不得称验证，val 2021-2024 零接触**；下一步（A 臂 "
    "val 一次性验证申请 / 结构化另立预登记）呈用户决定。锚（未改动 F3-EW "
    "composite 跑派生 runner）五帧逐字节 5/5、独立复核五项全过、墙钟 71.3s。"
    "试验累计 **296**（TL-39）。"
)
t = README.read_text(encoding="utf-8")
anchor = "不修改旧环境，无任何盈利承诺。"
assert t.count(anchor) == 1
t2 = t.replace(anchor, readme_add + anchor)
assert t2 != t and readme_add in t2
README.write_text(t2, encoding="utf-8", newline="\n")
print("README: status paragraph appended")

# --- main plan: append the 42nd update paragraph ----------------------------
plan_add = (
    "2026-09-20（第四十二次更新，F3R4 归因事件并入 F3 组合：H1 成立但受窗口"
    "敏感性限制）：① **预登记零口径偏离执行**（exp-20260920-factor-round-f3r4，"
    "run `20260920T122905-f3r4-reason-int-2301`）：b=71 信号月 composite 截面 "
    "std 中位数 0.10164738676824621（预登记写 68 月——实为归因 run 前向收益"
    "覆盖期，已披露并用 68 月变体复跑证明 Δ 0.0000pp）；事件标记按 §2 窗口"
    "规则（signal_date≥ann_date 且距离 ∈[0,60]，共享库日历）得 1,248 对/"
    "27 月/365 股（impairment 797 + price_up 451），冲突 0 例（后公告优先"
    "未触发、同日期平局 0）；A/B 可逆性逐位（无标记月变动 0）、FA-S2 重建 "
    "17 因子 composite 与 F3R1 parquet 全局 max diff 0、C 臂 44 个无标记月与 "
    "17 因子合成逐位一致。② **锚与 runner 纪律**：派生 runner 只换 composite "
    "输入路径、臂标签/产物前缀与引擎 pin（v1.3 84a2443a→工作区 v1.4.1 "
    "a01cb29c，与归因 run 同先例），用未改动 F3-EW composite 跑锚：五帧 "
    ".equals 5/5 + net_cagr/maxDD 逐位相等（v1.4.1≡v1.3 非 zones 再实证）；"
    "diff 全文 +639/−1,549 行入 manifest（删除项为 F3R3-A0 轮动锚、ICW 臂、"
    "轮动构造器与 F3R3 报告文本，不影响任一臂）。③ **主判定**：A 加分臂净 "
    "+5.3356%（Δ +0.4583pp ≥ +0.30pp 线、maxDD −17.8485% 与基线相同）**过线**；"
    "B 压制 +4.9440%（+0.0667pp）/C 第 18 因子 +4.8485%（−0.0288pp）不过线 → "
    "**H1 成立（探索级）**；边缘条款未触发。④ **机制与次报告**：三臂失败门"
    "与基线相同（门 3 4/6、门 8 v3 83.3~85.7%），风险门 4/5/6 全过、无臂达 "
    "≥10%；座位差异——A 把 impairment 座位月 3→33（26 只分散）、price_up "
    "13→0，B 只去坏仅 +0.067pp（price_up 基线本就极少入选）、C 两者都动"
    "净为负 → **可提取增益在加分侧**。⑤ **折扣与敏感性**：窗 20/40 重跑 "
    "+4.6791%/+4.7364%（均低于基线、非单调），只有冻结 60 交易日窗过线；"
    "叠加“事件研究已消费同段 dev”的二次使用身份——**H1 为探索级、不得按 "
    "+0.46pp 稳定效应解读、不得称验证**。⑥ 独立复核五项全过（标记向前重算、"
    "调整恒等式 106,266 行、座位独立重建 71/71 月×3 臂、头条数字独立公式"
    "差 0、判定算术）、墙钟 71.3s/4.76GB；台账 TL-39、试验 293→296；val "
    "零接触；下一步（A 臂 val 一次性验证申请 / 结构化另立预登记）呈用户决定。"
)
t = PLAN.read_text(encoding="utf-8")
assert "第四十一次更新" in t and "第四十二次更新" not in t
if not t.endswith("\n"):
    t += "\n"
t2 = t + plan_add + "\n"
assert t2.count("第四十二次更新") == 1
PLAN.write_text(t2, encoding="utf-8", newline="\n")
print("main plan: 42nd update appended")
