# R0 重启 MT 前置就绪核对（任务M，只读核对+本轮独占产物）

- 日期：2026-09-11。执行：GLM-5.3/MAX 子代理；主对话派发并裁决。
- 边界：只读限定文件核对；未修改任何被测文件；未运行整批 MT；未触碰 R0 正式入口与 VALIDATION/LOCKBOX；B-01 只读查状态未干预。本轮仅两处写入：本文件与 artifacts/r0-mutation-review-20260911/。

## 1. 结论速览

| 问题 | 答案 |
|---|---|
| 非等价幸存者实际清单 | **空**。MT 真实变异从未运行：全仓无任何 mutants.jsonl（Get-ChildItem -Recurse 零命中）；artifacts/mutation-testing-20260911/README.md 自述「真实变异尚未运行;本目录当前只含自验产物」。276 条是 dry-run 全 VALID 的规格，不是幸存者。 |
| 当前受审身份是否受影响 | **代码身份未受影响**（零变异记录、白名单 17 文件 HEAD 干净、0fb349b→HEAD 白名单零改动、历批 FINAL_TREE_CLEAN=true）。**但规格集对 HEAD 漂移 3 条锚点**：本轮新鲜 dry-run = 273 VALID / 3 INVALID。交接书 L25 与 wave3 送审包 §4 的「276/276 VALID」是对 8:17 提交前工作树的状态，对 HEAD 0332347 已过时。 |
| B-01 资源占用 | 已解除：B-01 完成并入库（0332347，2026-09-11 14:58:25），当前系统零 python 进程（只读核查，未干预）。 |
| 计划文档与用户前置的一致性 | docs/plans/r0-completion-and-acceptance-plan-20260911.md 全文无 MT/变异/幸存者字样（仅 MTM 估值三处）；其前置链未列 MT 清零。用户前置（D-2026-09-11-01）仍有效，需在计划复核（readiness B6）时补入或注明用户保留门优先。 |

## 2. 用户前置核对（原文与路径）

- docs/decisions.md D-2026-09-11-01 末条：**「R0 重启新增前置(用户 2026-09-11 批准):MT 变异测试幸存者清零——清零定义:全部幸存 mutant 完成分诊;真盲区类(未来函数/费用/掩码时序/对齐/缓存键/排序方向/np 双路径分歧)补测试杀灭;语义等价变异留档豁免(非字面零幸存)。与既有前置(Codex PASS/AUDIT-1 类缺陷修复/引擎身份冻结/OS 分离启动器+资源独占)并列。」**
- docs/handover-codex-20260911.md L28 同口径：R0 重启前置 = round-3 Codex PASS + MT 幸存者清零 + 引擎身份冻结 + OS 级分离启动器。
- 旧计划附录A L61「276 项变异测试：不是本次 R0 启动必要门禁」已被上述用户决策超越；r0-launch-pack-20260911.md §6 已并列两文并引原文。wave3 送审包「MT 不作为门禁」指 wave3 复审本身，与 R0 重启用户门不冲突。
- readiness 清单（docs/experiments/r0-execution-readiness-20260911.md §3）B3 已登记：「MT 变异测试幸存者清零（用户 2026-09-11 批准前置）｜未执行｜MT-run 独占期执行+分诊」。

## 3. 已有 MT 工件盘点（路径 + hash）

- 驱动器：experiments/mutation_driver_20260911.py，sha256 8450072E1543949B71BB383B4C4072876CCB240AF1D65A0FF9A24C9A43A12FA1，tracked 干净（b9373ba 入库），mtime 2026-09-11 03:34 后未变（排除驱动器版本差异导致锚点判定漂移）。测试 tests/test_mutation_driver_20260911.py，sha256 C8C634868249BD28BCC197D530A0D828BCEFC0F659A326C7BD780FD8272B4EBA，28 项（MT-0 验收 PASS 见 decisions.md D-2026-09-11-03）。
- 规格：artifacts/mutation-testing-20260911/specs_wave2_20260911.json，sha256 661D8A0B107C25FF42F33BE5E419C86B2BF8B14FF7A69AF082F7138E9E8707D0，276 条，9 类目（None/boundary 48、alignment/date 38、fee/cost 19、ledger/backtest 24、lookahead/shift 23、mask/eligibility 35、np-dual-path 30、sort/direction 25、stats/protocol 34）。
- 目标文件分布（9 文件有变异目标；白名单 17 文件 = factor_miner 直接子文件 15 + quant/validation.py + quant/execution.py）：

| 文件 | 条数 |
|---|---|
| experiments/factor_miner/director.py | 52 |
| quant/execution.py | 38 |
| experiments/factor_miner/backtest.py | 39 |
| experiments/factor_miner/operators_np.py | 34 |
| experiments/factor_miner/stats.py | 29 |
| experiments/factor_miner/operators.py | 28 |
| experiments/factor_miner/engine.py | 25 |
| experiments/factor_miner/compiler.py | 21 |
| quant/validation.py | 10 |

- dry-run 批次（均 FINAL_TREE_CLEAN=true）：toy 3 条（03:34，1 VALID/2 INVALID 自验）；dryrun-postwave2（05:28）；dryrun-wave2-specs（05:52）；dryrun-wave2-verify（05:54）；dryrun-postreboot（08:17，276/276 VALID——本轮证实其对 HEAD 过时）。
- 真实变异运行：无。

## 4. 本轮新鲜复验（独占目录，dry-run 不写源文件）

命令：python experiments/mutation_driver_20260911.py --specs artifacts/mutation-testing-20260911/specs_wave2_20260911.json --out artifacts/r0-mutation-review-20260911/dryrun-current-tree --dry-run

输出尾部：「[mutation-driver] totals: INVALID=3 | VALID=273 | kill_rate=None ／ FINAL_TREE_CLEAN: true」。summary.json sha256 81FEDBEA961D53A84C96DF4B78C5B489FD6819AB382D358BE96D327E115D5B6D。

3 条漂移明细：

| ID | 文件/类目 | 锚点 | 现况 |
|---|---|---|---|
| M-0017 | backtest.py / sort/direction | return op_out / op_in - 1.0, "executed", False, j | count=0：0fb349b 重写 backtest.py（+323 行）后该语句形态不存在（rg 零命中） |
| M-0022 | backtest.py / ledger | and p["sale_j"] <= next_e_in]: | count=2：现 L669/L771 两处——W2-03 基准同窗修复为基准侧复制了同式槽位解决逻辑；重锚须加上下文消歧（组合侧 vs 基准侧，按语义裁决） |
| M-0057 | compiler.py / lookahead | cross = {sym: (vals[i] if i < len(vals) else None) | count=0：W2-05 轴入口校验重写后仅存 cross = {}（L591） |

漂移根因时间线：规格 05:51 重锚（MT-2，13 条等价改写）→ 08:17 postreboot 276/276 → 08:17–09:47 wave2 最终编辑（backtest.py/compiler.py/operators_np.py，git show 0fb349b --stat：3 文件 +409/−92）→ 09:47 提交 0fb349b → HEAD 0332347（14:58，B-01 收尾）未再触碰白名单（git diff 0fb349b..HEAD 白名单路径为空；工作树 git status 白名单路径干净）。

## 5. 最小关闭任务（维持 276，不扩数量目标）

1. **MT-2b 重锚 3 条**（等价改写纪律，同 MT-2 模式）：M-0017/M-0057 按当前代码形态重写锚点；M-0022 上下文消歧（若组合侧与基准侧语义相同可选其一并留档，不同则需裁决覆盖范围）。产出新规格文件（建议 specs_postwave3_20260911.json，批次只新增不覆盖）；验收 = 对 HEAD dry-run 276/276 VALID + 程序化 diff 恰 3 条 + 语义复核留档。
2. **MT-1 整批执行前置**（全部满足才可运行，缺一不可）：独占窗口（无任何并行写代码任务；B-01 已清，运行前再核代理队列）；独占隔离完整副本（可用 r0_audited_runner snapshot-prepare 快照——J4 路径裁决后——或整仓副本）；副本内**未变异基线** python -m unittest discover 全绿（对齐 1697/0）先行落档；副本内 dry-run 276/276；随后真实运行（--confirm-full、新 out-dir、字节快照恢复红线不变）；FINAL_TREE_CLEAN=true 为结果可信前提。
3. **分诊闭合（用户定义）**：全部幸存者逐条分诊——真盲区类（未来函数/费用/掩码时序/对齐/缓存键/排序方向/np 双路径分歧）补测试杀灭（新测试入主树）；语义等价留档豁免；INVALID/TIMEOUT 处置留痕；总数维持 276。
4. **证据与状态翻转**：run 目录 mutants.jsonl + summary.json + 分诊台账文档；readiness B3 翻绿；decisions.md 记录。风险路径明示：若分诊揭出引擎真缺陷并修复 → 引擎受审身份变更 → 受影响证据按 S2 纪律复审，R0 启动包身份重冻结。
5. **计划复核补缺（并入 B6）**：把 MT 幸存者清零写入计划 R0 前置链，或显式注明用户保留门优先于计划 §4 顺序，消除「计划未列 MT」与用户前置的表述差。

预算提示：每 mutant 仅跑其映射测试模块子集；--confirm-full 对每个幸存者追加一次全仓 discover；总预算小时级起估（无实测数据，不虚构具体时长）；执行沿用 OS 分离启动与资源独占纪律（22:53 无工件消失事故教训）。

## 6. B-01 只读状态（2026-09-11 本轮实测）

系统零 python/uv 进程（Get-CimInstance 全表过滤复核）；B-01 已由 0332347 收尾入库（27760 股次/110 需求/23966s/parse_fail=0），不再占用资源。readiness B5 的「占用中」表述可更新为「已清，待 OS 分离启动器纪律落实」。

