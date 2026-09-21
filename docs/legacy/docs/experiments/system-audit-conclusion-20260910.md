# 系统分层审查首轮结论

2026-09-10，受审HEAD `46a84dbc71719c02c638b92f81bbfb4ee13c4c2c` + 工作树文件身份（见BCDE探针JSON）。

| 阶段 | 审查者 | 结果 |
|---|---|---|
| A | Sol | CHANGES_REQUESTED：ID、覆盖全集和身份检查仍有缺口 |
| B | 主审Codex | CHANGES_REQUESTED：常数伪信号、非有限行情漏检、价格并集日轴 |
| C | 主审Codex | CHANGES_REQUESTED：粗筛未随N校正、NaN可PASS、锁箱访问记录/集合身份、并列统计顺序 |
| D | 主审Codex | CHANGES_REQUESTED：因子月频执行状态漏检、组合账本与净边际口径缺口 |
| E | 主审Codex | 首轮影响及接口初筛已交付；最终影响清单与组件运行对照尚未验收 |

详见 `system-audit-bcde-independent-review-20260910.md` 与 `system-component-evaluation-20260910.md`。本轮没有修改受审实现，没有宣称旧PASS全面失效。

修复顺序：A 检查器加固与 C 粗筛候选数绑定→B 科学定义和数据缺失规范→C 锁箱访问台账→D 执行与账本→按实际触发候选复核工件；各包固定身份后独立审查。普通修复实现与审查分离。科学语义、费用/组合结构、异常后重考规则须形成具体差异与影响再裁决，不能静默改冻结协议。

R0 继续暂停。A及numpy单项PASS也不覆盖本轮新发现的B/C/D风险；不得据其直接推进受影响候选。VALIDATION/LOCKBOX 不启动，历史工件不覆盖，重跑范围依据触发扫描收窄。B～E仍有报告列明的未验收项，必须在对应门禁签PASS前完成。
