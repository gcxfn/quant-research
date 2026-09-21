# PV1 精测 送审包（第 7 轮）：末次复核升级为完整身份逐字段比对 + r7 一致性重跑

- 送审轮次：第 7 轮（第 6 轮 CHANGES_REQUESTED 1 项 P1）
- 日期：2026-09-10
- 审核请求：**P1 修复后请审核；PASS 后请求放行 PV1 留出窗（攒批统考队列）**

## 1. 第 7 轮 P1 与修复

**P1 原文要点**：holdout_gate 先冻结并消费完整 identity，但 run() 随后才读取交易日历、basic、行业成员和指数数据；末次复核 `_assert_no_data_drift()` 只重算 data_manifest 的价格 digest——非价格输入在 gate 后变化时计算用新数据、工件声明旧身份、复核照常通过。定向反例 `ASSERT_ACCEPTED_NONPRICE_IDENTITY_CHANGE` 证实。

**修复**（`experiments/pv1_precision_test.py`，仅 `_assert_no_data_drift` 及注释）：
- 末次复核改为**重算完整身份**：调用模块级 `candidate_identity()`（保持可测试性），与传入的（gate 或 in_window 自算的）冻结身份做**逐顶层字段并集比对**（各字段 canonical_hash 比较）；缺字段亦判漂移。
- 不一致 → RuntimeError，错误信息点名差异字段清单 + 各字段 frozen/current canonical hash 前 16 位（确定性、可读）。调用点不变：`aggregate()` 内、写 in_window.json 与 marker 之前。
- **gate 身份仍是唯一权威**：本次是校验性复算——重算结果仅用于比对，匹配即弃用，绝不写工件/台账；不违反 round6 确立的"holdout 全 run 只允许 gate 内一次权威 candidate_identity 调用"（那次是权威计算，本次是终态校验）。docstring 已写明该区分。

身份完整覆盖面（重申，均经 candidate_identity 单次调用捕获）：`code_sha256`（本文件+screen_pricevol+mr_statarb+预登记+`_CODE_DEP_FILES` 五依赖含交易日历 csv 与 stock_basic csv 文件级哈希）、`data_version`、`universe`（basic manifest/member snapshot/index daily）、`data_manifest`（价格全目录 digest）。

## 2. 反例测试（Codex 建议项全数落实）

`tests/test_pv1_precision_round7_fixes.py`（6 项，合成 stub，不触真实数据/装载/中央台账）：
- **四类非价格漂移 fail-closed**（第 2 次调用只改一个字段、其余含 data_manifest 逐位相同）：universe（member_snapshot_sha256）、data_version、code_sha256（本文件哈希）、`_CODE_DEP_FILES` 日历 csv dep 哈希 → 均 RuntimeError、marker 未写、in_window.json 未写、异常消息含字段名。
- **对照（无漂移）**：第 2 次完全相同 → 不抛错、marker 与 in_window.json 均写出（render_summary 因空数据 stub，aggregate 真实执行）。
- **in_window 模式同样受益**：自算身份后末复核发现 universe 漂移 → RuntimeError、工件未写。

## 3. r7 一致性重跑（修复后代码首次实战）

- 命令：`python experiments/pv1_precision_test.py --out artifacts/pv1-precision/round-20260910-inwindow-r7 --mode in_window --workers 2`（与 r6 同参数；新批次目录）。
- **主指标逐位一致**：net17 annualized = 0.0768200586568688（=r6）；bootstrap CI 下界 −0.86068%（=r6/Codex 复核值）。
- **深比较（剔除 identity 后递归逐字段）**：非 identity 差异 **0** 项；identity 差异仅 `code_sha256["pv1_precision_test"]`（本文件自身，预期内）；data_manifest digest 相等；universe/data_version/其余 code 依赖哈希全等。**VERDICT: PASS**。
- 运行末完整身份复核在 r7 实际执行（生产路径首跑）：价格 11,792 文件重摘要 + 全字段比对通过。
- r6 工件留档不覆盖；r7 为当前权威 in-window 工件。

## 4. 测试汇总（主对话独立重跑）

| 模块 | 结果 |
|---|---|
| tests.test_pv1_precision_round7_fixes（6 项） | OK |
| tests.test_pv1_precision_round6_fixes（5 项） | OK |
| tests.test_pv1_precision_test（34 项） | OK |

round6 文件头 docstring 的"全 run 只允许一次 candidate_identity 调用"表述已同步更新为"权威一次+校验性复算一次"；round6 既有 5 项断言零改动、全绿（identity 复用测试中 aggregate 被 stub，权威调用计数仍为 1）。

## 5. 纪律声明

- `HOLDOUT_UNLOCKED=False` 未动；中央留出台账不存在、未触碰；本包全部工作在 in_window（2020-01-01→2023-12-31，读取右端 2023-12-31）。
- 统计协议（17/27/37bps、月块 bootstrap B=10000/块3/种子20260909、十分位、末信号丢弃）零改动；本包唯一语义变更为末次复核覆盖面扩大（fail-closed 方向）。
- r7 判定仍为管线验证展示，in-window 已看过数据不参与判定；留出窗判定待本包 PASS 后按攒批纪律解锁执行。

## 6. 工件路径

- r7：`artifacts/pv1-precision/round-20260910-inwindow-r7/`（in_window.json / in_window_summary.md / data_manifest.json / stocks/ / daily/）
- r6（对照基线）：`artifacts/pv1-precision/round-20260910-inwindow-r6/`
