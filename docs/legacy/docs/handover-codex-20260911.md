# 交接文件：个人量化项目 → Codex 推进（2026-09-11）

> 2026-09-12新交接：本交接已由 `docs/handover-strategy-backend-20260912.md` 接续。保留历史内容，当前规则以根AGENTS和新主计划为准，勿按下方旧运行状态重新启动任务。

- **交接指令（用户原话，2026-09-11）**："完成交接文件，后面都由codex推进"
- **交接性质**：主对话（规划/派单/对抗验收角色）自此退位，由 Codex 担任推进者（规划+执行+审核）。**不因本交接改变的事项**：用户保留决策权清单见 §6；安全与冻结纪律见 §5，全部继续有效。
- **编写者**：主对话（本轮协调者）。本文件自包含，无需会话上下文即可续作。

---

## 1. 仓库与基线状态

- **HEAD**：`0fb349b`（round-3 修复波单一 commit）。关键链：`7eb7a67`（wave-1 审计）→ `b9373ba`（wave1 修复=round-2 送审对象）→ `0712d9e`（V3 池对照回测）→ `0fb349b`（wave2 修复=round-3 送审对象）。
- **测试基线**：`python -m unittest discover -s tests` = **1697 tests OK（skipped=1，0 失败）**（在 0fb349b 上两连跑验证）。
- **工作树脏文件**：除下述"在飞"项外，其余 M 文件（AGENTS.md、quant/*、p4 系列、tests/test_analysis 等）为**历史波次未提交残留**，不属于本交接范围；纪律：他人未提交修改不碰不清理。
- **artifacts/ 整体 gitignore**：一切工件按路径引用；`data/raw/`、`data/history/` 批次目录只新增不覆盖。

## 2. 程序主线状态（三句话版）

1. **因子考试流水线**（factor-miner）：矿已挖（R0 250 假设/246 结构、R1 池 215 行、财务 26+5 构造；粗筛晋级 F1/F4/PV1 等），但**考试系统在检修**——系统审计已两轮 Codex 复审（round-1/2 均 CHANGES_REQUESTED、共 11 缺陷全修复），round-3 送审包已就绪待审。
2. **生产 V3**（月频 ETF 轮动，收益引擎）：生产池已修商品/跨境污染（55→52，`b9373ba`），修正池与 R3 存档逐位复现（`0712d9e`）；反事实显示剔除三只的历史代价约 3pp 年化——**用户重议选项开放中**（§6）。
3. **一切正式运行冻结**：R0 挂起、VALIDATION/LOCKBOX 不变、Gate C/D 冻结、无任何信号标可执行。

## 3. 最高优先级队列（按序执行）

1. **round-3 送审**：`docs/experiments/system-audit-fix-wave3-review-pack-20260911.md`（commit `0fb349b`）。Codex 审核其中六项 W2 修复+协调者裁决（重点 §4.3 集中度期望值手算、§4.4 五文件改判）。若 CHANGES_REQUESTED：按既往循环处理（主对话时代的循环模式已终结，由 Codex 自行裁决修复与复审的执行方式，或指定 flash 子代理实现——实现与审核不得同一代理）。
2. **MT 变异整批**（round-3 PASS 后）：规格就绪 `artifacts/mutation-testing-20260911/specs_wave2_20260911.json`（276 条，重锚后 dry-run 276/276 VALID，主对话已独立复验）。执行纪律（Codex round-2 §3.4 裁决）：**独占期**（无任何并行写代码任务）+ 先确认未变异基线 `discover` 全绿 + 驱动器 `experiments/mutation_driver_20260911.py`（字节快照恢复、严禁 git 恢复）+ 新 out-dir + `--confirm-full`。MT 非门禁、不报杀伤率作承诺；幸存者须逐条裁决（真缺陷修复或证明测试缺口）。
3. ~~**B-01 收尾**~~ **已完成**（`0332347`，结果见 §4）。
4. **R1 冻结清单+预登记草案**：R1 池 215 行冻结（含去重裁决与 EX-D 机器比对条款——用 `artifacts/experiment-index-20260911/dead_zones.jsonl`，**须先移至受控位置**（configs/ 或 docs/data/）并在冻结清单登记）；邻域稳健性冻结矩阵条款（家族分层判定规则见 `docs/plans/factor-mining-program-20260909.md`）。**草案须用户确认后方可生效**。
5. **R0 重启**（用户保留决策，前置全齐后向用户请示）：前置=round-3 Codex PASS + MT 幸存者清零 + 引擎身份冻结（round6 清单已入）+ OS 级分离启动器。授权边界：REAL_RUN_UNLOCKED=True 仅限 R0 TRAIN-only；VALIDATION/LOCKBOX 入口 enforce 在位。
6. R0 TRAIN 批跑完后：幸存者→VALIDATION（独立子命令）→攒批统考（队列=PV1+财务 7 构造+R0 幸存者，D-33 授权）。

## 4. B-01 全市场扫描（已完成，commit `0332347`）

- **结果**：27,760 股次（5,552 只×5 pass）×110 需求×23,966s，parse_fail=0。命中全部集中在**停牌类常数窗**：价格类短窗 STD((close/open)−1,10)=2,516 次/290 只、STD(RET(close,1),10)=1,852 次/207 只、长窗 CORR/ZSCORE 千余次/5-11 只；**margin/lhb/估值字段零命中**；calendar 与 compressed 两轴计数逐行一致。完整命中矩阵见 `docs/experiments/system-audit-b01-train-scan-20260911.md` 的 SCAN 标记块。
- **含义**：命中>0 的（算子,输入,窗口）组合=旧代码下 TRAIN 统计含伪值成分，按该文档 §5 重算衔接条款办理（R0 全量重算已由语义修复强制，本扫描界定范围并留档）；命中=0 的组合获得静态清白证明。**此结果是 §3 第 4 项 R1 冻结清单的直接输入。**
- **附带修复**（同 commit 入库）：扫描器最小 bundle 补 close 轴（TW-2 交互，仅作长度契约，计数语义与修复前逐位一致）。
- **边界**：TRAIN-only 只读（loaders 显式 allow_validation/allow_lockbox=False）。

## 5. 纪律与冻结（全部继续有效，交接不豁免）

1. 用户保留决策（不得自主执行）：R0/引擎正式批次重启、VALIDATION/LOCKBOX 解锁、生产规则变更（V3 池/择时/费用）、Gate C/D 解锁、新研究轮次立项、资金与账户假设变更。
2. VALIDATION（2023-2024）/LOCKBOX（2025-2026.09）绝对禁触；粗筛选择窗 2024-01-01 起零接触（MR/事件轮的历史污染披露冻结在案）。
3. tushare token 仅存 `~/.tushare/`，严禁入仓库；有界并发 2-4 workers；东财/baostock 串行。
4. 禁自动下单/资金划转/绕过人工确认；禁保存任何凭据。
5. 每审次单一 commit；送审包不预填 hash；Codex 证据文件（两轮 review md+probe py）不得修改。
6. 变异驱动器严禁 git checkout/restore/stash 恢复（只许字节快照）；MT 独占期执行。
7. 离线单元测试零第三方依赖；变更后跑 `discover` + smoke。
8. 不得将未验证信号标"可执行"；输出含生成时间/数据截止/版本/成本假设。
9. 双路径一致异常不豁免为成功覆盖；不得见结果后删候选/缩 N/改写 PASS。
10. 批次目录只新增不覆盖；原始数据不可被结果覆盖。

## 6. 用户待决事项（Codex 推进中遇到即向用户请示，不得自决）

1. **商品排除规则重议与否**：修正池历史代价约 3pp 年化（`docs/experiments/v3-pool-correction-comparison-20260911.md`）；重议须走预登记流程。规则与 52 池现状冻结。
2. **sh517520 跨境剔除判断追认**：V3P 扩展判断+W2-06 代码级排除已修（含依据留档），等用户确认。
3. **AGENTS.md 的 t0 量级表述修正授权**（TA 证据全负）；授权后连同四个 t0 文件（`experiments/t0_minute_evidence_20260911.py`、`t0_range_calibration_20260911.py` + 两个 md，均未入库）一并提交。**AGENTS.md 同步本交接的分工变更也挂在此批**（该文件有历史未提交残留，合并提交时注意甄别）。
4. **现金归一模型→组合精测冻结**（round-2 §3.2 裁决方向）：Top15 文字改历史示例等，留待组合精测预登记。

## 7. 证据地图

| 类别 | 路径 |
|---|---|
| 决策链 | `docs/decisions.md`（D-2026-09-11-01..09，倒序） |
| round-3 送审包 | `docs/experiments/system-audit-fix-wave3-review-pack-20260911.md` |
| round-2 裁决+探针 | `docs/experiments/system-audit-wave2-independent-review-20260911.md` + `experiments/system_audit_wave2_independent_probe_20260911.py`（勿改） |
| round-1 裁决+探针 | `docs/experiments/system-audit-wave1-independent-review-20260911.md` + `experiments/system_audit_wave1_independent_probe_20260911.py`（勿改） |
| 探针输出三份 | `docs/experiments/system-audit-wave2-independent-probe-20260911{,-rerun,-postfix}.json` |
| 预登记与修正案 | `docs/plans/factor-miner-engine-preregistration-draft-20260910.md` + `amendment-20260910.md`（§5 为账本/估值/基准冻结口径权威） |
| MT | 驱动器 `experiments/mutation_driver_20260911.py`；规格 `artifacts/mutation-testing-20260911/specs_wave2_20260911.json` |
| 索引/死区/证据图 | `artifacts/experiment-index-20260911/`（experiments.jsonl/dead_zones.jsonl）+ `docs/experiments/{experiment-index,experiment-clustering,evidence-graph}-20260911.md` |
| B-01 | 脚本 `experiments/system_audit_b01_train_scan_20260911.py`；报告含 SCAN 块 `docs/experiments/system-audit-b01-train-scan-20260911.md` |
| V3 池 | `configs/strategy.json`(52) + `strategy-v3-55pool-frozen-20260911.json`(反事实冻结副本) + 对照 `docs/experiments/v3-pool-correction-comparison-20260911.md` |
| 测试验证命令 | `python -m unittest discover -s tests`；探针 `python experiments/system_audit_wave2_independent_probe_20260911.py --output <路径>` |

## 8. 残留与开放项（自 round-3 包 §6 延续）

1. 递延超限持仓永不自动重卖（amendment §5.6 保守冻结；补卖须另预登记）。
2. 静态数据轴下跨月恢复不可端到端触发（机制级测试覆盖）。
3. bench 口径变更：旧工件 bench 数值不可比（§5.9 作废声明）。
4. bcde 探针 B 段钉 pre-B-03 API，历史仪器留档不改。
5. registry 身份历史限制如实界定（get 引用无快照；fresh-dict 重放增长 LOW）。
6. MT 锚点随代码演进会漂移：每次代码修复波后须重跑 dry-run 重锚（本次 13 条由 MT-2 处理，模式见 specs_wave1→wave2 diff）。
7. R0 官方批双一致异常清单：真实批次触发时按 round-2 §3.1 政策送门禁责任人裁决。
8. B-01 扫描器向量量化改造（下次复用前做；记录于本轮对话，未入正式文档——Codex 可自行判断纳入）。

## 9. 交接即时状态快照

- **无任何在飞任务**（B-01 已完成收尾，`0332347`，见 §4；本快照随结果更新）。
- round-3 送审包**未送出**（等待用户或 Codex 自取）。
- 全仓测试绿（1697/0）；无变异残留（factor_miner 工作树与 HEAD 一致）。
- 本文件与 D-2026-09-11-09 同 commit 入库（`7d01490`）；B-01 结果更新随后续 commit 补记。
---

## 10. 2026-09-11 晚间状态增补（文档状态轮；不改变 §1–§9 历史记录）

- **分工细化（细化 §0/§1 的推进分工）**：最终审核与放行由主对话拍板；一切具体执行统一 GLM-5.3/MAX；子代理 PASS 仅证据输入非终裁；实现与审核不得同一代理（D-2026-09-11-10）。
- **用户授权（本会话）**：推进至 R0 可启动/完成；门禁闭合后恢复正式 TRAIN 无须再次询问重启（计划 §4.1）；VALIDATION/LOCKBOX 与统计协议变更仍须单独授权。当前 R0 未放行。
- **§3 队列进度**：
  1. round-3 送审：wave3 六项修复经复审**限定 PASS**（最终 identity 绑定留待收口），保留。
  2. MT（§3 第 2 项）：隔离副本限定基线 PASS（1729 tests OK skipped=6）+3 spec 重锚 276/276 VALID 已被主对话接受；正式 MT 未放行（超时子孙清理/正式进程访问拒绝未继承）；作者 Meitner 包装加固报完成（guard/sitecustomize.py+mt_runtime.py；先 Job 再启动、确认 active=0 才恢复、INFRA 不计 KILLED 且停批；round2 基线 1729 OK skipped=6 46.725s/包装 48.218s，探针 JSON 已核实）——待主对话审核后按独占期执行；真实 MT 未评估，不得写幸存者数。
  3. B-01：已完成（0332347）。
  4. R0 重启（§3 第 5 项）前置更新：OS 级分离启动器=experiments/r0_audited_runner.py，独立审查 §11 CHANGES_REQUESTED 三项（正向 command list 被 json.loads、运行后 expected 误改仍 PASS、超时后代清理缺口）；作者 Faraday fix-round2 报 5 项修复完成（36 tests OK 0 跳过、合成 selftest PASS；runner/tests sha256 与工件核对一致）——待独立复核+主对话裁决。统计门禁：处置草案 v3 被主对话退回（CP 须上界、不接受 f1.5/K12/合成外推/改冻结 tail），v4 已交待审（未冻结未校准）。S3 未闭合。
- **写集纪律**：本轮仅状态文档（AGENTS.md 顶部、decisions.md D-2026-09-11-10、本文件、计划 §4.2、进度记录 §7）；不动统计草案/启动器/MT 报告与代码本体；无测试、无提交。
