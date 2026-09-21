# 任务三审核：大规模分层因子挖掘

> 2026-09-16 S3 执行侧阶段审核（主对话，实现由独立子代理完成后亲验）：**PASS_WITH_LIMITATIONS**。
> 验收实做：全包 78/78 测试亲跑通过；conservation.json 费用独立重算与报告逐位相等
> （0.0 差）、账本恒等 9.1e-12；negatives.json 三负例均有数值证据（涨停 48 bar 零成交
> 且现金不动、逐 bar 截断恰=100 股/bar、47 根/NaN 在构建层被拒）；day-consistency 全部
> 证券日过日线一致门；attribution.json 27 订单逐单 L1 vs 分钟对比可机械复核；决策层重放
> 门与 L1 批逐位一致（3.3e-16）保证订单输入同源。代码审阅：`MinuteLimitStrategy` 触价
> 才提交/剩余量扣减/当日失效语义正确，`MinuteDealRecorder` 与 S1 同款无行为变更包装，
> AST+运行时双断言无 quant/experiments/vectorbt 导入。限制（维持）：挂限价成交价、
> 逐 bar min_cost、复权股数量纲三处口径差已披露并须进 S4 门槛包分母；L1 日线层
> `$change` 缺失致涨跌停检查空转是既有公共数据缺口（交 T1，不阻塞 S5 但须披露）；
> 冒烟单候选单窗口，压力情景未跑真实路径。统计 UNKNOWN、promotion BLOCK、
> 2025+/生产冻结不变。

> 2026-09-16 S1/S2 执行侧阶段审核（主对话）：**S1 PASS、S2 样例批 PASS_WITH_LIMITATIONS**。
> S1：重放身份绑定齐（gate selection/freeze manifest/candidates/score-cache/provider/
> l1-batch SHA+代码 SHA），232 路径日账户 9 列+关键指标与 L1 批 `-2` 逐位核对全过
> （最大列差 2.3e-10），需求集可从落盘 order-path.csv 机械复算；重放窗口用完整冻结
> 清单首候选推导，不随子集漂移。S2：口径移植未导入 experiments（纪律达成）；等价
> 验收 20/20 证券日 960 根逐位一致是最强证据；真实缺陷日被 fail-closed 拒绝而非修补；
> 日线对账 99/99 差异全由复权因子机械解释、日量一致，符合 2026-09-14 批准的
> research_disclose 登记口径；ZIP SHA 对 transfer-manifest 全核验。限制（维持）：
> S2 仅样例 100 证券日，全量接入未启动；分钟执行语义（限价/参与率/T+1/顺延）未验证，
> 待 S3；"比例=1/factor" 容差 1e-4 是披露判据不是数值安全界。统计 UNKNOWN、
> promotion BLOCK、2025+/生产冻结不变。

> 2026-09-16 S0 独立复核记录（独立只读子代理复算，主对话采纳）：对
> `qlib-native-l1-gate-result-20260916-1` 裁 **PASS_WITH_LIMITATIONS（接受探索性披露口径）**。
> 子代理未 import `l1_gate.py`，从 `qlib-native-l1-full-20260916-2/results.json` 284 条按
> gate-config.json 四规则独立实现判定，与 `l1-selection.csv` 142 行逐行比对**零差异**
> （状态、reasons、四个指标列；116/26 计数一致）；批 `summary.csv` 与 `results.json`
> 指标字段 284 行零不一致；候选集合三方一致（results ∪ = 冻结 142 = selection）。
> `passed_ids_sha256`（排序 id 以 `\n` 连接 UTF-8 sha256）与 `freeze_manifest_sha256`
> 复算一致。边界检查：无精确命中边界案例，最近案例方向均正确（压力收益 +0.000784 过 /
> -0.006061 拒；回撤 -0.297413 过 / -0.309263 拒）；mean_turnover 全批 0.0130–0.0457，
> ≤1.0 规则本批不具区分力（如实披露）。284 条全 COMPLETED、metrics 无缺失、主压力成对。
> 26 条拒绝原因组合：主+压力非正 17、仅压力 5、仅回撤 2、压力+回撤 1、三项 1。
> 限制（维持）：门槛登记晚于描述批查看，116 项只能作探索性集合，不得用作确证性统计主张；
> 若后续任何环节把"L1 通过"用作确证性结论或实盘依据，须就新批事前冻结门槛重评。
> 集合等式"L2 应评估集合 = 116 项探索性通过集合"自本条生效。

> 2026-09-16 L1 门槛登记审核记录（主对话，执行侧自审补强）：门槛四规则均可机械判定，
> 无排名截断；`l1_gate.py` 集合等式校验通过（结果集合=冻结 142 集合，主压力成对），
> 输入摘要绑定 batch summary/freeze manifest/gate config sha256；边界单测 3 例通过
> （0 收益严格拒绝、回撤/换手边界含双侧）。限制：门槛登记晚于两轮描述结果，
> 116 项通过只能按探索性集合使用；正式晋级需独立复核接受该披露或另行登记新门槛后重评。
> L2 分钟数据缺口为真实阻断，不得以日线近似替代。

> 2026-09-16 L1 `opening_cash_only` 批次执行侧完整性自审（覆盖上一节，非晋级裁决）：
> `qlib-native-l1-full-20260916-2` 的 284 条路径全部完成，身份绑定 runner/freeze/provider/
> score-cache 摘要；独立复核 `PASS_WITH_LIMITATIONS`（`report.md`/`audit.json`）。核验项：
> 主压力集合精确成对、逐路径日账户存在、期末账户与累计费用与汇总零差异、
> `account = cash + value` 全期零差异、现金非负。与旧批 `-1` 的差异归因明确：同日卖款
> 再投资约束改变 142 个候选中的全部路径，旧批头部收益不可沿用。
> 晋级仍 BLOCK：日线执行不能证明分钟排队，且 L1 数值门槛未在看结果前冻结；
> 124/118 个正收益仅为训练期描述。统计有效性 UNKNOWN 不变。

> 2026-09-16 L1 执行侧完整性自审（非最终晋级裁决）：142 个候选主/压力 284 条 Qlib
> 日线账户均完成，主压力集合精确成对，逐路径日账户存在，期末账户与累计费用复算零差异，
> 汇总裁决 `PASS_WITH_LIMITATIONS`，见
> `artifacts/qlib-native-l1-full-20260916-1/report.md` 与 `audit.json`。限制构成晋级阻断：
> 原生 Topk 同日卖出回款可用于买入，不符合 `opening_cash_only`；日线不能证明分钟执行；
> L1 晋级数值门槛未事前冻结。因此当前没有任何合法 `L1_PASS`，111/108 个正收益只作
> 训练期描述，不能进入 L2；统计有效性 `UNKNOWN`、promotion gate `BLOCK` 不变。

> 2026-09-16 阶段 1、2 复核更新：**PASS_WITH_LIMITATIONS**。provider 索引、块级 checkpoint/恢复、内存与失败分类已整改；25/25 聚焦测试通过，2000 候选全量 L0 已完成并形成终态。限制是四路并发曾触发内存门禁，最终通过检查点顺序恢复；严格一小时总墙钟未满足。详见[阶段 1、2 复核-2](../../artifacts/qlib-native-l0-phase12-review-20260916-2/review.md)和[全量结果](../../artifacts/qlib-native-l0-full-20260916-1/report.md)。L1/L2 未启动，统计有效性仍为 UNKNOWN。

> 2026-09-16 阶段 1、2 定向审核：**阶段 1 = CHANGES_REQUIRED；阶段 2 = CHANGES_REQUIRED**。19 项聚焦测试通过，S4 证明 provider 缓存和 500 只股票分块主路径可运行且未重现内存耗尽；但 provider 索引未覆盖 calendar/instrument/frequency 与逐文件 start/end/length，多 worker 会重复扫描并并发重建索引；score cache 仍在整批股票块拼接后才落盘，缺块级 Private Bytes/耗时记录，持续性块故障会被误归类为表达式故障。完整证据和整改条件见[阶段 1、2 审核](../../artifacts/qlib-native-l0-phase12-review-20260916-1/review.md)。正式全量仍为 `PERFORMANCE_BLOCKED`，L1/L2 未启动。
>
> 2026-09-15 后续缺陷复核（覆盖下方 `-6c` 执行侧自审）：**T3-B / Qlib L0 = CHANGES_REQUIRED**。
> `-6c` 的 109 项不得晋级或组合。确认 provider 非价格字段时间镜像/财报事件日期错位，且翻译器把
> 105 个横截面 `CS_RANK` 错换为时序 `Rank(252)`、36 个含 IF 的公式丢失假分支；按字段/公式并集
> 至少影响 1043/2000 项。修复 provider 的中断批只完成 400/2000，未形成新结论。已补缓存重筛与
> 家族均衡组合入口，13 项定向测试通过，旧缓存门槛复算 1.26 秒且状态/原因 0 差异；这些只证明
> 工程路径，不恢复旧数据有效性。下一步先完成 Qlib `CSRankNorm` 分阶段求值与新身份，再做一次性
> 增量重算。statistical_validity=UNKNOWN、promotion_gate=BLOCK、L1/L2 与 2025+/生产冻结不变。

> 2026-09-15 Qlib 原生 L0 全量执行侧自审登记（**非独立裁决**）：最终批次
> [artifact/qlib-native-l0-20260915-6c](../../artifacts/qlib-native-l0-20260915-6c/report.md)，2000 构造，
> 结果 L0_PASS 109 / L0_REJECTED 1312 / P5_STAT_INSUFFICIENT 575 / BLOCKED_MISSING_FIELD 4。
> 执行侧已核 selection.csv 2000 行唯一、monthly-rankic.csv = 2000x35、-6b->-6c 复用 0 差异、
> PASS 身份证一致；修复 Qlib Corr 崩溃（83->4 阻断）并区分真缺字段（adv_dec_ratio、limit_up_count、
> ev_ht_net_ratio_250、ev_ht_net_vol_250、ev_sf_past_ratio_250）。按用户“只做修复不做最终验收”，
> 本条不写 PASS；**B 段状态待独立复核**。statistical_validity=UNKNOWN、promotion_gate=BLOCK 不变。

> 2026-09-14 wave4 扩容批次（`-15`）自审记录：登记 2000 行（1430 基础 + 509 wave4 + 61 wave3 部分登记）、生成期六项检查与 20 行真实试跑均已完成，审核材料为[-15 全清单审核](../../artifacts/new-factor-research-20260912-15/roster-audit-20260914.md)与[-15 试跑报告](../../artifacts/new-factor-research-20260912-15/trial20-report.md)。裁决 **PASS_WITH_LIMITATIONS**（限定：登记/检查/试跑三条路径；全量 L0 未运行、L1/L2 未启动；重片内存待处置；秩等价筛查为合成面板筛查且 75 行未参与判定；本次为**同一执行者的自审**，未派独立子代理，限定复核建议由独立方执行）。该裁决不改变 statistical_validity=UNKNOWN、promotion_gate=BLOCK、2025+ 与生产冻结。

> 2026-09-14 后续（覆盖上一条对 `-15` 的裁决）：独立审核[`t3-construction-review-20260914-1`](../../artifacts/t3-construction-review-20260914-1/review.md)对 `-15` 裁 **CHANGES_REQUIRED**（F1 过去解禁未做公告可见性、F2 新增源未进冻结输入清单 = P1；F3 滚动和轴前公告钳到首日、F4 预告/快报未按报告期对齐 = P2）。执行侧已逐条整改并**整批重建为 `-16`**，记录见[-16 整改记录](../../artifacts/new-factor-research-20260912-16/remediation-review-20260914.md)：F1/F3/F4 各有反例测试，F2 建成 26,966 文件输入清单（绑入身份、启动/收尾核验、变异拒绝），结构模板口径改为 family+canonical（2000 行→724 模板、最大 10 变体、超限 0），受影响构造 15 行已机械列出、其余 1985 行不受影响。`-15` 及其试跑工件保留作缺陷证据；`-16` 试跑为修复后唯一有效读数。**`-16` 待独立复核**（本轮为执行者自审整改，不代替独立裁决）。统计 UNKNOWN、晋级 BLOCK、2025+/生产冻结不变。

> 2026-09-13 本次实施综合复核：最新 -11 合成正常路径亲跑1430/1430接受；运行准备与P1优化均为 **CHANGES_REQUIRED**。新增具体阻断：旧批跑器只核数据清单文件SHA，worker只核输入长度/计数，均不足以绑定实际数据内容。worker三种数据扰动摘要不变已独立复现。P1检查点测试通过不覆盖此反例；全量L0仍PENDING、未启动。详情与修改优先级见[本次审核报告](../experiments/t1-t3-implementation-review-20260913.md)。本条覆盖下文“整改待复核”的相关状态，不重开已关闭的其他缺陷。

日期：2026-09-12；最近审核：2026-09-13。状态：登记/运行准备 CHANGES_REQUIRED；已完成trial20证据 PASS_WITH_LIMITATIONS；全量L0及L1/L2结果未审。配对：[执行任务](new-factor-research-20260912.md)。

> 同日方案补充：用户要求将详细优化路线写入[实施审核报告](../experiments/t1-t3-implementation-review-20260913.md)。报告已登记CPU去重复、输入身份修复、GPU批量排名/IC衰减、资源预算、逐阶段验收与新快照切换条件。局部GPU原型值得验证，原“无批量收益来源而停止GPU”的技术判断被修订；本次只改方案，不启动真实全量、不改变CHANGES_REQUIRED裁决。

## 职责与调度

独立审核L0最多2000构造、L1/L2达标全进的登记、筛选、计算和结论，主对话最终裁决。T3与T1立即并行，既有已验收能力可直接使用；T1未完成只阻塞确实依赖新增能力的候选。审核按搜索登记、L0、L1、L2阶段进行，分片不逐一请示，不要求2000个构造逐个手工预审。

主审不替执行者调参后自签。研究流程通过与盈利候选资格分开；不恢复V5，不用大量探索结果宣称统计显著。

## A：搜索登记及试跑审核

- 仅L0最多2000个实际构造评估；L1/L2无独立人数上限，所有达标者进入下一层。M个候选通过L1、H个通过分钟训练时，应有2M条训练及2H条十年路径，H≤M≤2000；不得沿用100/20名额或80条路径限制。
- 搜索至少8个机制家族，单家族最多400、同模板最多10变体；数据不足须记录而非复制模板凑数。家族定义按经济机制核查。
- 全量机器检查候选ID、公式规范摘要、模板/参数/方向、窗口、标签、PIT、继承、缺失规则；同义公式不计新增独立结构，方向/期限/条件改变计尝试。
- 清单及分层数值门槛先冻结，模板/参数/算子/种子齐全。不允许分片之间根据收益改写余下候选。门槛不得含Top K、通过比例或事后分位数等变相数量截断；聚类不能只放行代表。
- 试跑最多20个清单内候选，收益计算计入总预算。核验预计耗时、内存和线程预算、恢复命令；可按性能调并发，不按收益改清单。
- 每家族至少抽2个候选，覆盖不同模板；异常、未复用的算子/数据转换须针对性检查。缺可判定门槛或日期边界为CHANGES_REQUIRED，不让执行者运行后再补。

## B：L0信号及L1成本筛选审核

- 对全部2000以内登记行自动核对完成/未运行原因、有效覆盖、数值质量及排除规则；提出未计算、实际尝试、技术重跑和晋级分开计数。
- 训练2020–2022，标签在2022末前成熟；未来公告、重述数据及2023标签不进入训练。原始除权跳变不作总收益；NaN/缺价不误判策略失败。
- 从完整结果独立重算达标集合，并核对集合等式：L1应评估集合=通过L0集合，L2应评估集合=通过L1集合。每个暂未运行者有排队/受阻记录；核查门槛边界、各家族代表和异常，不只看榜首。
- L1复用已有R0/R1信号能力和固定资金账户/费用模块，不能把R1信号脚本当完整成本账户。核实际连续现金、最低佣金、历史税率、换手和容量假设与登记一致；日线近似不宣称分钟成交。已验收底层证据复用，不全仓重测。
- 相关聚类使用训练数据，仅作披露/调度；近似公式、参数邻居和共享因子不计独立Alpha，也不成为少算合格候选的理由。共享结果必须完整身份等价及可追溯。无法复算达标集合或隐藏失败则阻塞该阶段结论。

## C：L2分钟及历史结论审核

- 全部通过L1的名单及依据先冻结，每个均核身份、账户配置、主压力、运行日志和数据状态，不按排名截断或设置补位。
- 训练通过条件事前固定，未通过不执行依赖的长历史。2015–2024完整路径按T2口径；缺失不得改短窗后晋级，不读2025估值/退出/标签。
- 全部账户执行机器账本核查；独立手工/独立公式核算至少覆盖一例正常成交、部分成交、最低佣金/历史税率及实际依赖公司行为，优先最坏差异。复用同版本引擎证据，不为每个候选各建同一套审核器。
- 每个候选保留年度/月度收益、费用、回撤、集中度、未成交、数据问题和失败。声明实际红利税范围，十年正收益不抹掉失败阶段。
- 所有研究保持探索身份；不能根据存活候选数缩减历史搜索分母，未知重叠如实披露。

## 审核产出、整改与停止

在批次内产出review-new-factors.md，记录审核者/时间、冻结摘要、检查命令、抽样ID及选择理由、全量计数、选择复算、逐L2候选处置、缺陷影响和下一步。裁决PASS/PASS_WITH_LIMITATIONS/CHANGES_REQUIRED/BLOCKED；未审为PENDING。

区分阻断正确性、影响结论、一般文档问题；只暂停相关分片/候选，但公共算子错误须冻结全部受影响候选并核影响范围。整改后只复核相关项；规则变更生成新版本，旧PASS不沿用。

达到L0登记预算仅停止新增构造，全部达标者的应有后续路径仍须运行及审核。资源限制只影响并发/排队/续跑，不能截断合格候选或把待运行写为失败、完成。无赢家可通过流程，数据受阻不能算完整研究目标完成。下一轮必须明确新预算及机制差异后登记，不无限滚动。全量自动检查、家族/异常抽查和全部L2候选的记录审核足够后停止，禁止增设无具体反例的第三层审计。

| 阶段 | 审核状态 | 证据路径/审核者 | 下一步 |
|---|---|---|---|
| A 登记与试跑（wave4） | `-15`：**CHANGES_REQUIRED**（独立审核，F1–F4）→ `-16`：**整改完成待独立复核** | `-15` 证据（保留作缺陷证据）：[全清单审核](../../artifacts/new-factor-research-20260912-15/roster-audit-20260914.md)、[试跑报告](../../artifacts/new-factor-research-20260912-15/trial20-report.md)、[独立审核](../../artifacts/t3-construction-review-20260914-1/review.md)。`-16` 材料：[整改记录](../../artifacts/new-factor-research-20260912-16/remediation-review-20260914.md)、[清单](../../artifacts/new-factor-research-20260912-16/hypotheses.jsonl)、[枚举报告](../../artifacts/new-factor-research-20260912-16/enumeration_report.json)、`wave4-input-manifest.json`（26,966 文件/digest 2fe65869…）、`run-identity.json`、`l0-trial20-attempt1/`。核验项：2000 行=1430+510+60、724 结构模板（最大 10 变体、超限 0）、F1/F3/F4 反例测试 + F2 清单负例 4 例、受影响构造 15 行机械列出 | 独立复核 `-16`（F1–F4 反例与影响表、输入清单核验、试跑数值）；复核通过前不放行全量 |
| A 已完成trial20 | PASS_WITH_LIMITATIONS | 两批011620/030908均20/20、P8=17/P9=3、35有效月；40次完成评估为同20构造，第二批属技术重跑；54底层文件主仓/快照身份一致，门槛复算一致 | 仅认可路径/描述性工件，不作为全量L0或盈利通过 |
| B 全量L0结果 | **执行侧自审完成，待独立复核**（非 PASS） | [qlib-native-l0-20260915-6c](../../artifacts/qlib-native-l0-20260915-6c/report.md)：2000 构造，PASS 109 / REJECTED 1312 / P5_STAT_INSUFFICIENT 575 / BLOCKED_MISSING_FIELD 4；-6b 保留作 Corr 缺陷证据 | 独立复核选择复算、集合等式与 4 个真缺字段阻断；L1/L2 未启动 |
| L1/L2结果 | PENDING | 尚无账户运行结果，执行侧BLOCKED | 按用户既定T1/T2能力依赖处理；无本次新增放行 |
| wave3正式登记 | PENDING | 520行原始池语法/字段检查成立；现有秩报告445可比较、75不可比较，14匹配记录涉及13个ID，不是14项已裁决排除 | 独立登记与逐项同义处置，不能直接拼入当前清单 |
| P1 性能优化（并行轨道） | 一轮独立审核已执行：CHANGES_REQUIRED → 整改完成待**限定复核** | 审核：[`-1/independent-review-20260913.md`](../../artifacts/factor-engine-performance-20260913-1/independent-review-20260913.md)（问题 1–6 + 结论限制）；整改：[`-2/remediation-20260913.md`](../../artifacts/factor-engine-performance-20260913-2/remediation-20260913.md)（M-1…M-10）；证据：[`-2/`](../../artifacts/factor-engine-performance-20260913-2/)（`manifest.json` 登记全部工件 sha256）。冻结身份 `director 4acbda144d4d2285` / `stats_np d8d1e7a94543ec61` / worker `29cb6d5e491b6a40` | 限定复核 M-1…M-10 及性能算术；**不**放行切换或全量 |

## P1 性能优化 · 限定复核范围（2026-09-13）

审核对象：交付包 `artifacts/factor-engine-performance-20260913-2/`（取代 `-1`；版本关系
见 `-1/VERSION.md`）。**本审不改统计门槛、不放行 L1/L2 或新窗口、不批准切换或全量运行。**

### 逐项整改对照（只需复核这些点）

| 审核发现 | 整改位置 | 负例/证据 |
|---|---|---|
| P1-1 汇总绕过检查点与身份校验 | worker `_verify_slice_dir`（run/aggregate 共用） | `aggregate_without_ck`、`missing_slice`、`wrong_keys_attempt_rejected` |
| P1-2 恢复未绑定代码/配置/结果内容 | worker `run_identity` + `candidates_sha256` | `cand_tamper_rejected`、`code_identity_rejected`、`config_identity_rejected`、`input_digest_rejected`、`row_*_tamper`、`run_meta_*` |
| P1-3 门禁分歧仍签发正式结果 | worker `_gate_diffs` → `GATE_MISMATCH` | `gate_flag_mismatch`、`gate_reasons_mismatch`、`gate_ci_mismatch` |
| P1-4 池缓存遗漏日期轴 | `stats_np._pool_panel` 键含完整日期轴 + 精确复核 | `pool_cache_date_axis` |
| P2-5 正式 worker 与验证配置不一致 | worker `--backend/--panel-cache` + 实际值校验并写入身份；截断缓存改 opt-in | `cli-test.json` ledger/身份字段 |
| P2-6 中断后不能恢复失败片 | attempt-N 目录 + 磁盘扫描发现 + 原子检查点 + 先扫描后装载 | `attempt_recovery`、`interrupted_only`、`next_attempt_after_interrupt`、`idempotent_resume_no_reload` |
| 性能算术与"装载占比<3%" | `baseline.md` §4.1/§4.2/§5/§6 改区间口径 | `load-scaling.json`（三点标定） |
| `preloaded` 信任面 | worker `_assert_preloaded_ok`（空池/空轴/无预热/`n_tests` 不符即拒） | `preloaded_fail_closed`（6 变体） |
| 截断缓存"opt-in"表述不符 | `director.enable_truncated_close_cache`（默认关）+ 各 harness 显式开启 | `worker-cross-slice-equiv.json` 缓存计数；`cli-test.json` 身份 |
| 身份口径（并行 `-8` 复审 R1/S1） | worker 改用清单行 `canonical_eval_key` | `identity_scheme`、`row_formula_tamper`、`row_direction_tamper` |
| 标签成熟边界（`-8` 复审 S3） | worker `_month_end_axis` + aggregate 成熟度判定 | `immature_month_null_ok`、`immature_month_ic_rejected`、`off_axis_month_rejected` |

### 本审**未覆盖**（不得据本表当作已通过）

- 全量 20 片运行、全池（5552 股）装载/计算实测、GPU 分支。
- `experiments/t3_l0_batch_20260913.py`（`-8`/`-11` 批跑入口）本身；本包不依赖它。
- 任何因子有效性/统计结论：性能包只处理耗时与工件身份，统计 UNKNOWN、晋级 BLOCK 不变。

### 2026-09-13 性能包 -5 主对话独立审核（覆盖该优化轨道此前当前状态）

执行状态：CHANGES_REQUIRED；整体交付/切换准备审核：CHANGES_REQUIRED；已测CPU优化、F1/F2局部修复和F3：PASS_WITH_LIMITATIONS。其他研究阶段状态不变，整体未完成，全量保持未启动。

审核记录：[性能包-5独立审核](../experiments/factor-engine-perf-independent-review-20260913.md)。受审源码2c3a31f3、59件摘要一致；亲跑输入身份40/40、比较器11/11、检查点29/29、B1对抗300/300。独立证据在 artifacts/factor-engine-performance-review-20260913-1/，命令见审核报告末尾。

下一步仅修R1–R5：worker消费事前冻结代码/数据契约并核收尾；证据绑定运行时摘要及补齐依赖；纠正GPU计时口径；回退显式--backend pure；补小规模新进程CLI并更正交付范围。GPU局部原型已做、当前不采用，旧“未做GPU原型”不再作为当前事实。-12只登记身份，未获本审核切换放行；不修改冻结旧包，不启动全量或L1/L2。
### 2026-09-14 审核登记：任务2 前置通过、任务3 未开始（PENDING）

本任务书范围内本轮无新工件：全量 L0 未启动、无新登记包、无试跑清单，A/B/C 阶段结论沿用既有状态。
登记要点：① 任务2（引擎整合与 L0 入口接线）的裁决见 T1 审核 2026-09-14 条，结论 PASS_WITH_LIMITATIONS，可支持后续正式 L0；② 现有 `-13` 清单 1430 项实测 0 行引用 `fin_`/`ev_` 扩展字段，整合期新增的扩展字段接线对该清单不产生内容差异；③ 整合仓已达「入口可运行」状态，但不构成 T3 阶段推进——最终清单 / 门槛登记与试跑授权仍未发生。
下一步：最终清单与门槛登记送审 + 真实试跑授权后，按任务书 3.1–3.3 执行并审核；在此之前不写 DONE、不恢复全量取消状态。



### 2026-09-14 2000构造独立审核（覆盖登记审核当前结论）

T3-A执行/审核CHANGES_REQUIRED。主对话独立核2000行、2000唯一求值单元、20×100分片精确一致，19字段测试通过；发现过去解禁字段漏公告门、最终输入清单漏财报/事件源、轴前事件滚动错位、预告/快报未对齐报告期。见[审核报告](../../artifacts/t3-construction-review-20260914-1/review.md)及evidence.json。实际当前清单为-15的2000项，覆盖旧“仅1430/未登记”描述；不同快照试跑与性能接线证据不互相替代。仅审核，不改算法、不启动真实计算、不恢复全量；整改及依赖影响按报告推进。
