# DeepSeek 接管留痕（2026-09-11 夜）——模型切换 · 已核读证据 · 下一阶段待办

- 性质：纯文档留痕。写集=本文件（新建）；未改生产代码/冻结协议/AGENTS.md/docs/decisions.md，未动任何旧审查证据工件，未跑测试或研究，未读真实行情，未触 VALIDATION/LOCKBOX，未提交，未作任何放行。
- 依据：本轮用户原话（模型切换指令与本轮补充）、AGENTS.md 现状、docs/plans 当前审核/验收计划、已有 R0 准备工件与旧审查记录（只读复用）。
- 角色用语：「主审」=用户侧最终拍板与放行角色；「本代理」=本轮 DeepSeek Flash 执行代理（仅文档留痕，非终裁）。

## 1. 模型切换（来源与本轮修订）

- 切换来源 = 用户原话，逐字引用：「glm不可用就换成deepseekflash模型进行」。用户原话不含「/MAX」——「Flash/MAX」中的 MAX 属主审派发配置，不得合成为用户表述。
- 本轮修订 = 用户原话，逐字引用：「后续思考强度high即可」→ 后续统一 DeepSeek Flash/high。
- 如实记录（本条非用户原话）：本代理本次启动时的运行配置 MAX 为主审派发时点的历史配置；代理无运行配置修改权，也不声称已修改任何运行配置；「后续统一 Flash/high」自后续派发生效。
- 旧 GLM 记录不改写：既有文档与工件中的执行署名（GLM-5.3/high、GLM-5.3/MAX）及历史裁决记录保持原样；本文件是本次切换的唯一新增留痕，不回填、不改写旧记录。
- 分工结构不变（D-2026-09-11-10 定格部分继续有效）：最终审核与放行由主审拍板；子代理自报 PASS 仅作证据输入、非终裁；实现与审核不得同一代理。本次变更仅及「执行模型载体」。

## 2. 本轮已核读证据（哈希均为本轮实测）

### 2.1 MT 哨兵转义修复——主审裁决：仅该修复限定 PASS

事实（本轮核读）：

- 隔离树 guard：D:/AI/workspace/mt1-isolated-20260911/mt-prep/guard/sitecustomize.py = b73dd25c0341c7d38c84a4ae10cea6a76e2f9134c71984d7c1c6c70f90fae53a（与主审引用一致）；mt_runtime.py = 5f690747d7d8e33ea83b77c3370f90b96f9b07189c81a4dd35bbf242f095977d（未动）。
- bc3cb319 单测内部日志（logs/inner/frozen_test.bc3cb319282c486eaed0d159ca6f53eb.output.log）：测试 ok / Ran 1 test in 0.000s / OK。
- 878c081f 限定模块内部日志（logs/inner/limited_module.878c081f11fa4b229c18803c97d9f0a4.output.log）：Ran 8 tests in 1.545s / OK。
- JSON 更正块：logs/inner-mapping-verification.json = f7980bc12043cfaa284d17db8376aa3ed18a8547d4f2c1872a72566e9f107496（在场）。
- 修复前 R1 反例对照：artifacts/system-audit-20260911/mt-independent-final/logs/probe_sentinel_r1.json（wrapped=INFRA、direct_open=INFRA deny）。
- 修复工件：artifacts/system-audit-20260911/mt-sentinel-fix/（一行 diff：raw 字符串恢复转义；pre-bytes 存档 c0644dc0…ab799；hashes-manifest；probes；logs）。

主审裁决（经主对话消息下达，非用户消息；摘记）：仅哨兵转义修复本身限定 PASS；不放行全量 1729 包装基线、不放行 MT276、不放行 R0。证据在 artifacts/system-audit-20260911/mt-sentinel-fix/。

留痕说明：该工件报告 §5「主审裁决记录」占位仍空；本文件为该裁决的集中留痕；占位是否回填进工件由主审裁定（本代理不改旧证据工件）。

### 2.2 preclose 修复——作者完成、主审已实际核读；独立复核未完，另一 DeepSeek 代理接手

- 作者工件：artifacts/system-audit-20260911/preclose-fix/（REPORT.md = 8ea2b91567acacd1450afe009705b3a7d997136ed29ba99518a6dba4502015b5、diff × 2、final-rerun-scope-limited.log）。
- 已核读的作者结果：final rerun 12 passed in 45.40s（test_r0_preclose_contract 6 + test_r0_pit_future_invariance 6），exit 0；针对回归 169 passed（final-identity.txt 原文）。
- 缺陷定性（A 类）：merge_rows 组装合并行仅保留 raw_preclose → STATE（market_ret/market_vol/adv_dec_ratio）全 None、limit_up_count 静默 0。
- 在盘身份（本轮实测）：experiments/mr_statarb.py = 09ff10bf2a1adcc589a7953f17d1b14056f598de15e048fecf6f6ebf4b9cc991（与 final-identity.txt 一致）；tests/test_r0_pit_future_invariance.py = 6b78aa50d7274fc876536511db8e09ec0e04ca1a04de153080a199a4776be76b；tests/test_r0_preclose_contract.py = 3370106ccbd334603284f730fdb0cbcd316c3ca93448964f8b6f8112e4bbe96d；git HEAD = f32568f3820ae5dc2d273e4e60e20cd14887d570。
- 独立复核：未完。新目录 artifacts/system-audit-20260911/preclose-independent-deepseek/ 在途（evidence/live-diff-mr_statarb.patch 2990B；logs/two-tests-rerun.log = 12 passed in 12.45s、EXITCODE=0；尚无 REVIEW.md）——由另一个 DeepSeek 代理接手完成，本代理不代办、不预判结论。
- 后续依赖（只记录）：真实启动受审身份在 preclose 审定后重锚；受影响调用路径与历史结果清单（REPORT §7）待主审调度。

### 2.3 启动器 runner fix-round4——独立复核完成，主审裁决已录入

- 工件与复核：artifacts/system-audit-20260911/runner-fixround4/（diff × 2、fix_record_round4.json、pytest 67 passed、selftest）；artifacts/system-audit-20260911/runner-independent-r4/REVIEW.md。
- 已录入裁决（REVIEW §8）：F1-F6 修复限定接受、停止扩大攻击面；F1 None-PASS 按 B 级「未确认」处理（正式运行补偿规则：先隔离、经独立确认后人工验收）；F3 措辞偏差不阻断；F2 更正（real --trusted-digest 只锚 manifest；外部 sidecar 摘要由主审保全、终验实际比对）；边界=真实 director CLI/R0-3 与 preclose 后身份重锚仍未验证；本轮不构成正式 R0 放行。
- 在盘身份（本轮实测）：experiments/r0_audited_runner.py = f5256e82e20c51238cb16a5cb5231be57f057b5d444e815677948bd7b7a155db；tests/test_r0_audited_runner.py = 3d5aac4ee48dbc88c73efd467c80e8115f5a099afc6d9ad73e4a5360c9a5d834。
- 轮次注明：715df36f…/7a0e4c9e… 为 fix-round3 受审冻结身份（已被 round4 取代）；cf9a229b…/f8b06eab… 为 fix-round2 身份——引用时必须带轮次。

### 2.4 统计线——math_verify_v2 限定数值工具验收；v4.1 与路径决策待审

- math-correction-v2：math_verify_v2.py = a9d52a47472c1cf0cd3e72de059137e335cda7c636080d19e8b2bd9481ef7d22；运行输出 = be39f44001a5afd53d7562e62a49a4bb4cc8ff0c85298186a2edfcfa07777d44；CORRECTION-REPORT.md = 29a278565d99a271a5df3dc3f43f09bae10c635e824215a46a68b9458198c082。
- 独立复核 artifacts/system-audit-20260911/math-correction-independent/REVIEW.md：复跑 22/22 PASS、exit 0、22 行 CHECK 与作者日志逐字节一致、唯一差异 1 行为输入指纹漂移（非科学字段）。
- 主审裁决（REVIEW §7，2026-09-11 20:53 录入）：接受 math_verify_v2 为限定数值工具（已测域）；不再增加验证层；明确非「R0 统计校准通过」、不解锁统计正式批/校准运行/VALIDATION/LOCKBOX。
- 仍待：v4.1 文档闭合（B.4/B.5/授权桥；statistics-review §5 阻断项）主审审核；S3 校准未闭合；路径决策 artifacts/system-audit-20260911/r0-stat-path-decision/OPTIONS.md（路径 A 工程/描述性 vs 路径 B 修订）待裁决。
- R0 描述性输出契约（可逆工程准备、未实施）：artifacts/system-audit-20260911/r0-descriptive-contract/（CONTRACT.md、CODE-CHANGES.md 8 个改动点 + 12 条验收反例、合成样例）；是否实施待主审裁决；本契约不替代统计闭合。

### 2.5 计划与停止规则（已生效状态）

- docs/plans/research-audit-scope-and-stop-rules-20260911.md = fcfcc3881caf30f2bd977d3fd9a42c9ebf222fae1eac3074bccc81cfa553ca0d（本轮实测，与 r0-progress §9 记录一致）：已生效（v3.1）；边界=非系统 PASS、非具体运行放行、统计与留出冻结不变。
- docs/plans/r0-completion-and-acceptance-plan-20260911.md：四门分离、R0-1..R0-4、S0-S7；§4.1 授权补记（门禁闭合后恢复正式 TRAIN 无须再次询问；VALIDATION/LOCKBOX 与统计协议变更仍须单独授权）。历史快照区分：该文 §4.2（及 r0-progress §2/§5/§7 的 fix-round2 状态行）为 fix-round4 交付与独立复核前的早期状态；最新口径以本文件 §2.3（fix-round4 工件 + runner-independent-r4 REVIEW §8）与 r0-progress §10 为准，不据旧快照重新打开已推进项；计划文档原文不改。
- docs/plans/r1-candidate-freeze-draft-20260911.md：R1 冻结清单工程草案（未生效）；D-1..D-12 待裁决；纯元数据准备可依既有授权先行。
- 状态总账：docs/experiments/r0-progress-and-decisions-20260911.md（含 §10 fix-round4 增补）、system-continuation-status-20260911.md、r0-launch-pack-20260911.md、r0-execution-readiness-20260911.md。注：continuation-status §1/§2 为 fix-round4 交付前时点文本，引用时以最新工件为准。

## 3. 计数与口径纪律（含本轮用户补充）

1. 248 不是总候选：248 = R0 当前冻结批的评估单元数（244 结构×1 单元 + 2 结构各 2 窗口变体；positive 189 / negative 59），不得当「历史唯一因子总数」或「全部已挖因子数」使用（stop-rules §1；本轮重申）。构成数字的两措辞口径（「拒 3」 vs 「3 组合并吸收 4 条、compile rejected 0」）待元数据核验，以最终核验为准。
2. R1/R2 lineage 与累计搜索分母需续作（本轮用户补充）。现有基础（artifacts/system-audit-20260911/candidate-lineage-prep/）：R0 250 行→246 结构→248 评估单元（冻结参照核对 PASS）；R1 215 行→213 结构（字符串归一化口径 213）、推导候选单元 215（未冻结未评估）；财务 31 构造公式层身份 UNKNOWN；R1×R0 canonical 公式交集=0；R1 批内两组精确重合（空格书写变体，同 R0 excess_ret 组型）待 D-1 裁决；EX-D 精确层命中与语义待审层已机器产出（明细见该工件 §6）。待续作：语义/结构层交集（D-4）、R1×财务 lineage、EX-D 比对键与命中处置（D-2/D-3）、以及累计搜索分母的跨轮记账口径（R0/R1/财务与 MR/事件/P4 等历史轮次及 20 个 sealed dead zones）。分母定义属主审/用户裁决事项，本文件不预填。
3. 污染分层阻断按实际结论定级：按 stop-rules §2 的 A/B/C（具体影响路径与真实风险）定级，只阻断受影响路径，不按攻击词、不自动全局阻断。
4. 纵深加固有界：不无限加层；有独立覆盖且无具体反例即停止递归（stop-rules §3.3；runner-r4 裁决「停止扩大攻击面」为已执行先例）。

## 4. 下一阶段待办（现状 + 证据路径；不猜测在途状态）

A. MT 线
1. 哨兵修复后续包：全量 1729 包装基线是否重跑、F2 句柄口径统一（Halley 实测首次失败运行 +4 后平稳 vs 作者 0/0，建议统一 GetProcessHandleCount 前后差口径）、正式 MT276 是否/何时放行与执行（独占期、字节快照恢复、未变异基线全绿前置）——待主审。证据：mt-independent-final REPORT §5、mt-sentinel-fix/。
2. 包装加固内容终审：artifacts/r0-mutation-review-20260911/hardening-evidence/（REVIEW.md、driver-vs-main.diff、mt_runtime.py.diff、guard-sitecustomize.py.diff、identity.json、process-evidence/ 等在盘）。注意：隔离树 guard 此后已因哨兵修复变更为 b73dd25c…（mt_runtime.py 未动），终审覆盖范围须以当前字节核对为准（不预判）。

B. 启动器与 R0 放行链
3. 真实 director CLI 兼容实测（R0-3 范围；real 模式双闸未解除）——runner 独立复核 §5 剩余项。
4. preclose 审定后真实启动受审身份重锚（runner/tests 新身份 + mr_statarb.py = 09ff10bf…cc991）。
5. R0-1 wave3 最终 identity 绑定收口（限定 PASS 保留）。
6. R0-2/R0-3 启动包齐备（launch-pack / readiness / 描述性契约视裁决）→ 主审运行前裁决 → R0 正式 TRAIN（TRAIN-only；VALIDATION/LOCKBOX 仍锁）。

C. 统计线
7. preclose 独立复核交付（另一 DeepSeek 代理）→ 主审终裁；受影响历史结果重算范围裁决。
8. v4.1 文档闭合审核；OPTIONS 路径 A/B 裁决；r0-descriptive-contract 8 改动点 + 12 验收反例是否实施。
9. S3 校准闭合路线（v4 系列未冻结未校准；math_verify_v2 仅数值工具）。

D. R1/R2 与累计分母
10. D-1..D-12 裁决推进；dead_zones.jsonl 迁受控位置（D-2）并登记；EX-D 比对键与处置（D-3）；语义层与财务 lineage（D-4）；R1 冻结清单 + 预登记（用户确认后生效）。
11. 累计搜索分母口径（本轮用户补充）的定义与记账草案。
12. 统考（队列 = PV1 + 财务 7 构造 + R0 幸存者，D-33）——前置 = R0-4 完成 + 经审统计路径冻结。

E. 留痕事务
13. mt-sentinel-fix REPORT §5 占位回填方式（主审定责）；模型切换类留痕今后按「新文件追加、不改旧记录」模式延续。

## 5. 已有证据路径索引（本轮实测存在）

- MT 隔离树与包装：D:/AI/workspace/mt1-isolated-20260911/mt-prep/（guard/sitecustomize.py、mt_runtime.py）
- MT 哨兵修复：artifacts/system-audit-20260911/mt-sentinel-fix/（REPORT-mt-sentinel-fix-20260911.md、hashes-manifest.txt、pre-bytes/、probes/、logs/inner/、logs/inner-mapping-verification.json）
- MT 独立复核与反例：artifacts/system-audit-20260911/mt-independent-final/（REPORT-mt-independent-final-20260911.md、probes/probe_sentinel_r1.py、logs/probe_sentinel_r1.json、logs/baseline32_recount.json）
- MT 加固材料：artifacts/r0-mutation-review-20260911/hardening-evidence/（REVIEW.md、diff × 3、identity.json、process-evidence/）
- 启动器：artifacts/system-audit-20260911/runner-fixround4/、runner-independent-r4/REVIEW.md、runner-recovery/（r3 封存）
- preclose：artifacts/system-audit-20260911/preclose-fix/（REPORT.md、final-identity.txt、MANIFEST、两条 diff、targeted-regression.log）；独立复核在途目录 preclose-independent-deepseek/
- 统计：artifacts/system-audit-20260911/math-correction-v2/、math-correction-independent/、r0-stat-path-decision/OPTIONS.md、r0-descriptive-contract/
- 候选 lineage：artifacts/system-audit-20260911/candidate-lineage-prep/（REPORT.md、raw_rows/structures/attempt_units.jsonl）、candidate-asset-map/；死区输入 artifacts/experiment-index-20260911/dead_zones.jsonl
- 计划文档：docs/plans/r0-completion-and-acceptance-plan-20260911.md、research-audit-scope-and-stop-rules-20260911.md、r1-candidate-freeze-draft-20260911.md、r0-statistical-gate-remediation-draft-20260911.md
- 状态文档：docs/experiments/r0-progress-and-decisions-20260911.md、system-continuation-status-20260911.md、r0-launch-pack-20260911.md、r0-execution-readiness-20260911.md、docs/handover-codex-20260911.md
- 启动包（旧轮）：artifacts/r0-launch-prep-20260911/fix-round2-20260911/（fix-round2 身份，已被 round4 取代）
- 计划一致性留痕：artifacts/system-audit-20260911/plan-consistency-final/REVIEW.md

## 6. 尚需主审事项（决策/放行清单）

1. MT：全量 1729 包装基线重跑与否；F2 句柄口径；加固内容终审 → 正式 MT276 放行（当前不放行）。
2. preclose：独立复核终裁；受影响调用路径/历史结果重算范围；真实启动身份重锚时点。
3. 启动器：真实 director CLI/R0-3 兼容实测放行；R0-2/R0-3 启动包运行前裁决。
4. 统计：v4.1 文档闭合审核；OPTIONS 路径 A/B 选择；r0-descriptive-contract 实施与否；S3 闭合路线。
5. R0-1 wave3 最终 identity 绑定收口方式与验收记录。
6. R1/R2：D-1..D-12 逐项裁决；dead_zones 迁移属既有 D-2 事项、仅待主审裁决（本文件不据此新增用户审批要求）；累计搜索分母口径定义（本轮用户补充要求）。
7. mt-sentinel-fix REPORT §5 占位回填方式。
8. 决策归属：R0/引擎正式 TRAIN 恢复不属用户保留项——按计划 §4.1 既有授权，门禁闭合后经主审放行即可恢复，无须再次询问用户；仍属用户保留决策（触发时请示，不自决）：VALIDATION/LOCKBOX 的读取与解锁、统计协议/阈值变更、生产规则变更、Gate C/D 解锁、新研究轮次立项、资金与账户假设变更。

## 7. 边界与不做声明

- 本文件为唯一写集：未运行任何测试/研究/变异/真实批；未读真实行情与任何分区数值；未改生产代码、冻结协议、AGENTS.md、docs/decisions.md；未动旧证据工件；无提交。
- 本文件不构成 PASS、不放行任何正式运行、不改变 MT/VALIDATION/LOCKBOX/Gate/R0 任何状态。
- 一切哈希与结论均标注来源与实测属性；遇旧文本早于新工件的情形以新工件为准；未证实事项一律标注「待核/待裁决」，不猜测代理在途状态。
