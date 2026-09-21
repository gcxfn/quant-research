# 系统风险分层审查：范围与现状基线

日期：2026-09-10。阶段：A（固定现状、先审检查器）。状态：**CHANGES_REQUESTED**。本记录不授权 R0 重启、numpy 正式 TRAIN、VALIDATION 或 LOCKBOX，也不改变旧批次状态。

## 受审身份

- 仓库 HEAD：`46a84dbc71719c02c638b92f81bbfb4ee13c4c2c`（2026-09-10 23:16:10 +0800）。
- 增量基线：round-2 审核时的 `94581d9`；当前 HEAD 已包含 round-3 检查器修复提交。
- Python：3.11.15；numpy：2.4.6。
- `experiments/np_dualpath_diff_probe.py` Git blob：`1350c837ad572e09ecfcf3c8dd54f5d1164e33fa`。
- `experiments/np_dualpath_registry_compare.py` Git blob：`e071a8d8f5afee0cae4cc03cc98d2e308e7b0a0a`。
- `tests/test_factor_miner_np_tools.py` Git blob：`0428374d98baeda121ae5a9e2ca05a09a57eb06f`。
- numpy 送审包 Git blob：`422a66d90e93c1c901292552172dd79127875058`。

上述四个目标文件在审查开始时与 HEAD 一致。仓库另有大量既存脏文件和未跟踪研究工件，本阶段未修改、清理或纳入审查结论。A 阶段记录完成前再次检查目标文件漂移。

## A 阶段实际覆盖

1. 读取 `AGENTS.md`、系统分层审查计划、numpy 双路径送审包及三轮独立审核记录。
2. 核验当前 HEAD、提交内容、目标文件工作树状态和运行环境版本。
3. 检查 `np_dualpath_diff_probe.py` 从假设装载、编译、双跑比较、报告到返回码的链路。
4. 检查 `np_dualpath_registry_compare.py` 从 JSONL 装载、深比较、报告到 CLI 退出码的链路。
5. 用不依赖仓库 `artifacts` 的临时微型 JSONL 和 mock bundle 注入负例。

## 已核验入口与关系

- 差分探针：冻结 hypothesis JSONL → `compiler.compile_formula` → 合成 bundle → 纯 Python、numpy、numpy 重复运行 → `compare_unit` / `compare_strict` → 文本 verdict 与 `main()` 返回码。
- registry 检查：纯/加速 `registry.jsonl` → `load()` 以 `factor_id` 建 dict → `walk()` 深比较 → 文本 verdict 与 `sys.exit`。
- 送审包把上述工具作为 numpy 等价性和确定性验收证据；因此工具的完整性缺陷会直接削弱正式运行前门禁，不能按低风险报告问题处理。

## 当前协议与清单缺口

- registry 工具没有外部冻结的预期 `factor_id` 清单或预期数量参数，只检查两侧集合是否相等。因此双方同时漏掉同一单元不可发现。
- registry 工具显式跳过 `code_commit`、`code_identity` 等身份键，也没有另行验证输入工件绑定到本次冻结代码身份。
- 差分探针从固定本地路径读假设，但不验证 ID 唯一、类型、非空、预期集合或数量；`compile_fail` 仅打印，不进入失败判定。
- 送审包首段仍写 `提交 {COMMIT}`，虽然 §8/§11 记录了 `46a84db` 和 1085 项结果；应在正式绑定身份的送审记录中消除占位符歧义。

## 阶段边界

用户随后明确授权主审直接执行 B/C/D/E；主审已完成首轮风险审查与合成反例，范围、302项专项结果及尚未验收项见 `system-audit-bcde-independent-review-20260910.md`。核心工作树内容身份见 `system-audit-bcde-probe-20260910.json`。这不改变 A 未闭合、R0 暂停和正式留出窗门禁。

A 阶段尚未闭合，故不能签发 numpy 运行前 PASS，也不能据旧 `REAL_RUN_UNLOCKED=True` 恢复 R0。B～E 可继续只读梳理，但 B/C 的正式门禁验收和任何全市场运行均不得跨过本阶段阻断。
