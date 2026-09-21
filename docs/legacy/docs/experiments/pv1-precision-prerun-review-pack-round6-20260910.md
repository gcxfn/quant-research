# PV1 精测 Codex 运行前审核送审包 第 6 轮（2026-09-10）

审核性质：运行前代码审核第 6 轮。第 5 轮唯一剩余 P1（留出门禁身份与运行身份未绑定）已修复，主对话复验通过。全仓测试：PV1 专项 55 项 OK（round0/4/5/6 四文件）；HOLDOUT_UNLOCKED 保持 False、中央台账不存在。前包：round5。

## 一、第 5 轮处置（主对话复验）

| 项 | 处置 | 复验 |
|---|---|---|
| [P1] holdout_gate 计算身份 A 写台账只返回 marker，run() 再独立算身份 B 且无 A==B 检查 | `holdout_gate`（pv1_precision_test.py:340,:378）返回 `(marker, identity)` 把预消费完整身份原样交出；`run()`（:962）holdout 模式复用 gate 身份、全程仅 gate 内一次 candidate_identity 调用（in_window 模式照旧自算 :972）；新增 `_assert_no_data_drift`（:323-338）重算 data_manifest 与身份冻结 digest 严格比较，不一致 RuntimeError（fail-closed，不写 marker/in_window.json），在写工件前对**两种模式**执行（:1090）；docstring 写明「holdout 下台账已预消费，数据被动过则该次机会作废，不得静默重试」 | 5 项新反例测试（身份只算一次且落档=gate 身份/末复核漂移 RuntimeError 且 marker 未写/in_window 不受影响/锁恒闭+解锁后返回元组）；主对话深度比对：r6 与 r5 剔除 identity 后**全部顶层字段逐位一致**，identity 仅 code_sha256.pv1_precision_test 一项不同（本文件自身哈希 7965045f…→c910b62e…），data_manifest.digest 两轮均为 f2e943134828…（数据未变）；r6 net17 年化 +7.6820%、CI 下界 −0.8607% 与 r5 一致 |

## 二、门禁-运行-复核三段链（现语义）

1. gate：锁检查 → 独占目录 → 身份计算+台账预消费（先于任何留出窗数据读取）→ 返回 (marker_path, identity)；
2. run：holdout 复用 gate 身份（无第二次计算）→ 装载计算 → 落档 data_manifest.json；
3. 末次复核：写 in_window.json/marker 前重算 manifest digest 与身份比对，漂移即 RuntimeError（fail-closed；holdout 台账已消费=该次作废，禁静默重试）。

## 三、建议审核重点

1. 复用链唯一性：holdout 模式下 candidate_identity 的调用点是否严格只剩 gate 内一处（含 aggregate/落档路径均消费同一 identity 对象）。
2. 末次复核的 fail-closed 位置：是否先于 marker 与最终工件写入；in_window 模式的复核语义（无台账消费，漂移=本批作废重跑）。
3. r6=r5 仅自身哈希差异的独立性（两批均全新独立运行）。

## 四、结论边界（不变）

选择窗年化 +7.6820%、95%CI [−0.8607%, +2.6450%] 含零——费用后盈利性不能判定。PASS → PV1 代码/数据资格冻结；留出窗按 D-2026-09-10-18 用户决定攒批后统一开考（当前队列：PV1 + 财务线 7 构造 F1/F4/F18/F20/F26/F27/F30 待精测）。
