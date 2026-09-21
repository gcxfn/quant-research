# -*- coding: utf-8 -*-
"""exp-20260920-t1-reason-event -- 文档补丁：台账 FT-02 / README 状态段 /
主计划第四十一次更新。字面量替换 + 唯一性断言；UTF-8 无 BOM、LF。"""
from __future__ import annotations

import sys
from pathlib import Path

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]

LEDGER = ROOT / "docs/evidence/trial-ledger.md"
README = ROOT / "README.md"
PLAN = ROOT / "docs/plans/daily-short-term-rebuild.md"
RESULTS = "docs/research/exp-20260920-t1-reason-event.md"

FT02_ROW = (
    "| FT-02 | 2026-09-20 | exp-20260920-t1-reason-event | "
    "T1 下游事件研究（\"归因标签有没有 type 之外的增量信息\"；预登记冻结口径："
    "dev 2018-09-04..2020-12-31、(ts_code,end_date) 去重取最新公告、剔不确定、"
    "R16 池事件日四条件（主板/非ST/上市≥60 own-session/事件日可交易）、月份"
    "固定效应+type 组内去均值后 primary_code 类别 ANOVA p<0.05→H1；TE-S2 与 "
    "F2R1 harness 同式自写抽 3 股×3 事件 1e-9 核对；敏感性 S1 剔 sd=-1/low、"
    "S2 h=5/10、S3 不去重不另计试验） | 1 | 1 | **H1 成立：F=3.343 "
    "(df 12,6643)、p=7.13e-05、η²=0.006**；BH 后 3 类显著：epidemic_shock "
    "−1.8%/t=−4.0（1,178 事件全部在 2020 单年份）、impairment +3.8%/t=+3.7"
    "（分年 3/3 正、top1 集中度 2.7% 非单票驱动）、price_up −2.7%/t=−2.5"
    "（分年 3/3 负但 top1 集中 27.8% 须打折）；**type 层 sanity 方向反向如实"
    "呈报**（月调后预增 −0.43% vs 预亏组=首亏+续亏 +0.38%，只验证不判定）；"
    "敏感性 4 臂全 H1 不脆弱（S3 不去重 p=1.8e-06）；TE-S2 分析样本全部 "
    "6,655 可对照键 max diff=0（另 1 键 harness min_history universe 截断）"
    " | 因子线 120→**121**（策略线 293 不变） | run "
    "20260920T113527-t1-reason-event-b690；漏斗 38,567→dev 17,582→去重 "
    "16,202（−1,380）→剔不确定 399→池 6,664（板块 −6,426 含 28 行不可转换 "
    "ts_code、无 traded 行 −2,098、上市 −24、ST −591）→分析 6,656（27 公告"
    "月、缺 h20 窗 −8）；长停股 42 事件（0.6%）交易日窗日历跨年（极端 "
    "2024-09，own-session 冻结口径内，manifest 量化）；开发期停机 2 次系 "
    "TE-S2 抽样机械规则（字典序首/尾股可对照事件<3），全局对照首次运行即 "
    "0 误差、判定数字不受影响；8.2s/5.93GB；"
    "[结果](../research/exp-20260920-t1-reason-event.md) | val 2021–2024 与"
    "冻结区零接触（三处断言）；归因因子进 F3 管道须另行预登记 |")

README_SEG = (
    "**T1 归因事件研究收官（exp-20260920-t1-reason-event，"
    "[预登记](docs/research/exp-20260920-t1-reason-event-prereg.md)+"
    "[结果](docs/research/exp-20260920-t1-reason-event.md)）**：控制 type 与"
    "公告月后 primary_code 归因对公告后 T+20 收益仍有增量——ANOVA F=3.343、"
    "p=7.13e-05<0.05 **H1 成立**（η²=0.006 如实记录）；BH 后 3 类显著："
    "epidemic_shock（负，全部为 2020 事件）、impairment（正，分年 3/3、"
    "集中度低）、price_up（负，分年 3/3 但集中度 27.8%）；type 层 sanity "
    "方向反向（预增弱于预亏组）只验证不判定、如实呈报；S1 剔 sd=−1/low、"
    "S2 h=5/10、S3 不去重全维持 H1 不脆弱；TE-S2 同式自写与 harness 全局"
    "逐位一致；dev 分析样本 6,656 事件（38,567 标注行连接断言全过）、val "
    "零接触。因子线试验 120→**121**（FT-02）。归因因子进 F3 管道须另行"
    "预登记。")

PLAN_SEG = (
    "\n2026-09-20（第四十一次更新，T1 归因事件研究 H1 成立：primary 有 type "
    "外增量）：① **预登记零口径偏离执行**（exp-20260920-t1-reason-event，run "
    "`20260920T113527-t1-reason-event-b690`）：T1 全量 38,567 行连接断言全过"
    "（键 1:1、struct_version 全 llm-v1）；dev 17,582→去重 16,202→剔不确定 "
    "399→R16 池事件日四条件（主板/非 ST/上市≥60 own-session/事件日可交易，"
    "复用 p2r16 共享库不自造池）→6,664 过样本量门槛（各 type≥100，最低续盈 "
    "168）→分析样本 6,656（27 公告月）；val 2021-2024 与冻结区三处断言零"
    "接触。② **TE-S2 逐位一致**：前向收益与 F2R1 harness 同式自写"
    "（close/preclose 链、T+1 起、停牌过滤、h=20），抽 3 股×3 事件 1e-9 "
    "核对，且分析样本全部 6,655 可对照键全局 max diff=0；长停股 42 事件"
    "（0.6%）交易日窗日历跨年（极端 2024-09，own-session 口径内正常结果，"
    "manifest 量化披露）。③ **主判定 H1**：月调+type 组内去均值后 primary "
    "类别 ANOVA F=3.343 (df 12,6643)、p=7.13e-05<0.05、η²=0.006；BH 后 3 类"
    "显著：epidemic_shock（负，1,178 事件全部 2020 单年份）、impairment"
    "（正，分年 3/3、集中度 2.7%）、price_up（负，分年 3/3、集中度 27.8% "
    "打折看）；**type 层 sanity 方向反向**（月调预增 −0.43% vs 预亏组 +0.38%"
    "，只验证不判定）如实呈报。④ 敏感性 4 臂（剔 sd=-1/low、h=5/10、不去重"
    " n=7,423）全维持 H1 不脆弱；开发期 TE-S2 抽样机械规则停机 2 次（非语义"
    "失败，判定数字不受影响）。⑤ 计账与交付：台账 FT-02（因子线 120→121）、"
    "README 已更；run 8.2s/5.93GB、manifest 全身份 pin。**按预登记 §5.1，"
    "归因因子进 F3 管道须另行预登记**。悬置不变：R3-05/R3-06 等 6 配置 val "
    "与 F 线生产化方向待用户批准。\n")


def patch(path: Path, anchor: str, insert: str, after: bool = True,
          append_end: bool = False) -> None:
    text = path.read_text(encoding="utf-8")
    assert "\r\n" not in text, f"{path}: unexpected CRLF"
    if append_end:
        new = text.rstrip("\n") + "\n" + insert
    else:
        n = text.count(anchor)
        assert n == 1, f"{path}: anchor count {n} != 1 for {anchor[:60]!r}"
        new = (text.replace(anchor, anchor + insert) if after
               else text.replace(anchor, insert + anchor))
    assert "\r\n" not in new
    path.write_text(new, encoding="utf-8", newline="\n")
    print(f"patched {path.name}: +{len(insert)} chars")


# 1) 台账：FT-02 行接在 FT-01（文件末行）之后
led = LEDGER.read_text(encoding="utf-8")
assert led.count("| FT-01 |") == 1, "FT-01 anchor not unique"
assert led.count("| FT-02 |") == 0, "FT-02 already present"
assert led.count("因子线 0→**120**") == 1, "FT-01 count anchor missing"
patch(LEDGER, "", FT02_ROW + "\n", append_end=True)

# 2) README：状态段内、F3 计数核对句之后插入 T1 段
README_ANCHOR = "台账补登 TL-33~35（F3R1/R2/R3）后计数一致。"
patch(README, README_ANCHOR, README_SEG, after=True)

# 3) 主计划：第四十一次更新段接在文件末尾（第四十次更新段之后）
plan = PLAN.read_text(encoding="utf-8")
assert plan.count("第四十次更新") == 1, "40th update anchor not unique"
assert plan.count("第四十一次更新") == 0, "41st update already present"
patch(PLAN, "", PLAN_SEG, append_end=True)

print("all doc patches applied")
