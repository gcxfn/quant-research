# 任务三：大规模分层因子挖掘

> 2026-09-16 S4 L2 门槛事前登记完成（总计划 S4，工件
> `artifacts/qlib-native-l2-gate-20260916-1/gate-config.json`）。**在任何 L2 分钟全量
> 路径结果产生之前冻结**（此前仅有 S3 冒烟且已披露，冒烟数值未参与门槛数值选择）。
> 五规则：主分钟净收益>0、压力分钟净收益>0、主最大回撤≥−30%、主平均日换手≤1.0（机械
> 上界，沿 L1 同型）、**逐候选分钟 vs L1 日线执行劣化 ≥ −5pp**（L1 基准绑定
> l1-selection.csv sha256=99c080af…；S3 冒烟实测 +0.13% 正向，5pp 为筛选界非误差安全界）。
> 无 TopK/通过比例/事后分位数。候选集合=L1_PASS_EXPLORATORY 116 项（探索级身份继承，
> 通过结论不构成确证性统计验证）。集合等式：十年应评估集合=L2 通过集合。缺分钟路径
> BLOCKED_DATA 触发补数，不记策略失败。S5 全量（232 条分钟路径）自此获得事前门槛。

> 2026-09-16 S3 Qlib 分钟回测接线与工程冒烟完成（总计划 S3，工件
> `artifacts/qlib-native-l2-wiring-smoke-20260916-1`；两次失败尝试
> `-failed-import`/`-failed-quote-window` 留证）。实现代理产出
> `qlib_research/l2_minute.py`（~1128 行）+`test_l2_minute.py`（11 测试），主对话验收
> 亲跑全包 78/78 通过。架构：外层冻结 `OpeningCashTopkDropoutStrategy`（决策层经重放门
> 与 L1 批逐位一致，最大相对差 3.3e-16）+ 5min 内层 `SimulatorExecutor`；
> `MinuteLimitStrategy` 把日级订单逐 bar 转"限价已触价"子订单（买限=日参考开×(1+滑点)，
> bar 触及才成交，成交价=min(bar开,买限) 挂单保守口径；当日有效收盘撤销不顺延）；
> 逐 bar 参与率=p×bar 量（蕴含 L1 单日约束）；涨跌停用自写 lbuy/lsell 字段（bar 收盘 vs
> 前日收×(1±0.095)，涨停禁买/跌停禁卖）；T+1/整手/opening_cash_only 由冻结外层承担；
> 费率按冻结表。冒烟=L1 淘汰候选 `CE_mom_peak_trace_20` main 2020-02-03…03-02（21 会话）：
> 217 证券日分钟全部通过 241 根聚合+日线一致门（量 1e-6/价 1e-3，实测最大 1.2e-7）+
> 12 字段读回逐位校验（124,992 值）；L1 vs 分钟期末账户差 +264 元（+0.13%，分钟 VWAP
> 挂限价口径普遍优 0.3–5bp）；账本守恒 account=cash+value 差 9.1e-12、费用独立重算
> 逐位相等；三负例全过（涨停日零成交、参与率逐 bar 截断恰 100 股/bar、缺根/NaN bar
> 构建层拒绝）。归因 27 订单逐单落档。**披露（S4 门槛须纳入）**：①部分成交逐 bar 各计
> min_cost（L1 单次）；②挂限价成交价 vs L1 无条件 open±滑点；③复权股数 vs 原始量截断
> 量纲（沿 L1 冻结行为）；④L1 日线层 `$change` 缺失使其涨跌停检查实际空转——分钟层
> 已真实实现（属执行口径增强，补日线 change 字段属公共数据变更交 T1 另议）。
> 限制：单候选单情景单窗口，不外推、不构成 S5 预览；压力情景仅参数管线+单测覆盖。

> 2026-09-16 S2 训练窗分钟接入样例批完成（总计划 S2 样例步，工件
> `artifacts/qlib-native-l2-minute-sample-20260916-2`；残缺首跑 `-1-failed` 留作
> qlib 未 init 即写 bin 的失败证据）。新增 `qlib_research/minute_provider.py`：把
> T2 冻结聚合口径（241→49→竞价并入首根→48，右端标签 09:35–15:00，零量根挂价不定
> OHLC，出处 experiments/user_minute_1m_20260913.py 与
> migration_tushare_minute_adapter_20260912.py，2026-09-13 冻结）**忠实移植**为包内
> 数据接入代码，不导入 experiments（计划 §4 纪律）；配套
> `minute_daily_disclosure.py` 做日线对账披露。选样=种子 20260916 的 80 均匀+20 与
> 冻结产物重叠（demand-set 22,392 中与 T2 冻结 `_f5.csv` 重叠 420）。**验收达成**：
> ①聚合前后量/额守恒 99/99（fsum 容差 1e-9）；②fail-closed 负例：8 个合成负例测试
> （缺根/重复/错时/非分币价/OHLC 破坏/身份错/非有限）+1 个真实拒绝
> （sz.302132 2021-07-01 网格不完整，登记不修补）；③与冻结产物等价 **20/20 证券日、
> 960/960 根逐位一致**（移植正确性证明）；④Qlib provider 写入+读回：33 日×48=1584
> 个 5min 日历戳、99 只、抽检股 288 值逐位相等；⑤日线对账披露（research_disclose）：
> 日量比 99/99 在 1e-6 内=1，开/收比例一致 99/99，比例=1/factor 99/99（容差 1e-4），
> **零未解释差异**——分钟为不复权原始价（adjustflag=3），日线为复权价，差异全由
> 复权因子解释，按 2026-09-14 用户批准口径登记接受。单元测试 15/15，四模块合计
> 29/29 通过。数据源身份：年度 ZIP 逐一 SHA256 对 transfer-manifest 核验通过。
> 限制与边界：样例批仅 100 证券日（99 成功），不等于全量 S2 接入完成；分钟执行
> 语义（限价、参与率、T+1）在 S3 接线中验证；该 provider 样例仅作管线验证。
> 下一步：S3 Qlib 分钟回测接线（嵌套执行器）与 S4 L2 门槛事前登记。

> 2026-09-16 S1 订单路径提取完成（总计划 S1，工件 `artifacts/qlib-native-l2-orderpath-20260916-1`）：
> 新增 `qlib_research/order_path.py`——与 `l1_backtest` 完全同一执行路径重放 116 个
> L1_PASS_EXPLORATORY 候选主/压力共 232 条路径，仅对 `Exchange.deal_order` 加无行为变更
> 成交记录包装（只记 `trade_account=` 真实成交，策略 dry-run 卖出 `position=` 不记；
> trade_val≤1e-5 零成交不记）；不重新求表达式，消费 L0 score-cache。**验收达成**：
> ①重放日账户与 L1 批 `-2` 逐路径逐列（account/return/turnover/cost/value/cash 等 9 列 +
> 关键指标）比对全 232 条 ok，最大列差 2.3e-10（序列化噪声级）；②需求集可从落盘
> order-path.csv 机械复算（`demand_reproducible_from_disk=true`）。产出：order-path.csv
> 106,835 笔成交（买 54,483/卖 52,352）、demand-set.csv **22,392 个去重（股票,执行日）对**
> （3,312 只股票 × 35 个调仓日；主 22,234/压力 22,315；单证券日最大 88 条路径引用），
> 与计划上界估计 ≤116×35×~20≈81,200 相比重叠后更少，符合预期。单元测试 8/8 通过；
> 冒烟批 `-smoke-20260916-1`（2 候选）先行验证。边界重申：此清单是数据需求上界快照，
> 分钟回测中限价/参与率顺延新增的证券日按 S8 同样触发补数，不回填本清单。
> S2 分钟接入以 demand-set.csv 为准，不预下载全市场。

> 2026-09-16 S0 L1 门槛独立复核完成（配对审核任务书已记）：独立只读子代理复算 116/26
> 集合**零差异**、passed_ids_sha256 与 freeze_manifest_sha256 复算一致、无边界命中案例；
> 裁定接受探索性披露口径（PASS_WITH_LIMITATIONS）。集合等式"L2 应评估集合 = 116 项
> 探索性通过集合"生效；116 项不得用作确证性统计主张。

> 2026-09-16 后续总计划已登记：[Qlib 主线 L1 之后到最终验收总计划](../plans/qlib-t3-l2-to-final-acceptance-plan-20260916.md)，
> 覆盖 S0 L1 独立复核 → S1 订单路径提取 → S2/S3 分钟接入与接线 → S4 L2 门槛事前登记 →
> S5/S6 L2 全量 → S7–S9 十年扩展 → S10 统计披露 → S11 组合 → S12 终验，另列 CS_RANK/缺字段
> 两条可选并行轨道。计划不改变任何冻结边界。

> 2026-09-16 L1 探索性门槛登记并应用（用户授权持续推进）：门槛包
> `qlib-native-l1-gate-20260916-1`（主净收益>0 ∧ 压力净收益>0 ∧ 主最大回撤≥−30% ∧ 平均日换手≤1.0；
> 无 TopK/比例/分位数），结果批 `qlib-native-l1-gate-result-20260916-1`：142 候选中
> **L1_PASS_EXPLORATORY 116 / L1_REJECTED 26**，逐项拒绝原因落档。披露：门槛在描述批次
> `-1/-2` 已被查看后登记，通过只作探索性，不等价事前冻结统计验证；集合等式
> L2 应评估集合 = 本 116 项集合。L2 当前阻断：Qlib provider 仅有日线，分钟执行所需
> 2020–2022 订单路径分钟数据尚未接入（估约 116×35×~20 符号日，重叠后更少），
> 须按实际订单触发获取，不得用日线冒充分钟成交。

> 2026-09-16 L1 `opening_cash_only` 适配全量完成（覆盖上一节 L1 描述批）：用户批准后新增
> `qlib_research/opening_cash_strategy.py::OpeningCashTopkDropoutStrategy`——继承 Qlib
> TopkDropout，仅把买入预算基准改为调仓日开始时现金，卖出、成交、费用、涨跌停与参与率
> 仍由 Qlib Exchange/SimulatorExecutor 原生处理。新批 `qlib-native-l1-full-20260916-2`
> 重跑全部 142 候选主/压力 284 条路径；`l1_report` 完整性复核 `PASS_WITH_LIMITATIONS`：
> 逐路径日账户存在，期末账户/累计费用复算零差异，`account = cash + value` 全期精确成立，
> 现金全程非负。主情景正收益 124/142、中位总收益 +17.0264%、中位最大回撤 −17.8583%；
> 压力 118/142、中位 +15.7776%。与旧批 `-1` 对比：同日卖款再投资使 84 个候选主收益被抬高、
> 58 个被压低，头部 `T3-LIQ-LQ12` 系列虚增 130–164 个百分点（如 LQ12-w120 由约 +319% 降为
> +155%），确认旧批高换手候选收益被同日资金循环显著放大，`-2` 才是符合冻结账户规则的描述基线。
> 限制不变：日线 Exchange 不能证明分钟排队；L1 晋级数值门槛未事前冻结，因此 284 条仍为
> `COMPLETED_DESCRIPTIVE_NOT_L1_PASS`，L2 不启动。

> 2026-09-16 L1 描述性账户执行更新：最新有效 L0 的 142 个 `L0_PASS` 已全部进入
> Qlib 原生日线账户主/压力评估，共 284/284 条路径完成，工件为
> `artifacts/qlib-native-l1-full-20260916-1/`。完整性复核 `PASS_WITH_LIMITATIONS`：
> 主情景训练期正收益 111/142、中位总收益 19.5805%；压力 108/142、中位 17.3447%；
> 这些不是晋级计数。Qlib `TopkDropoutStrategy` 同日使用卖出回款，不满足冻结的
> `opening_cash_only`，日线 Exchange 也不证明分钟排队，且尚无事前冻结的 L1 晋级数值门槛，
> 因此 284 条均为 `COMPLETED_DESCRIPTIVE_NOT_L1_PASS`，L2 不启动。有效输入冻结包是
> `qlib-native-l1-freeze-20260916-2`；`-1` 误把摩擦/参与率写成费用，保留作错误记录。
> 有效冒烟是 `qlib-native-l1-pilot-20260916-3`；pilot `-1` 因无点/带点代码映射零成交，
> `-2` 的账户数值有效但费用汇总字段命名错误，均不作为当前结果。

日期：2026-09-12；最近审核：2026-09-15。状态：**T3-A 登记保留；Qlib L0 结果 CHANGES_REQUIRED，旧 109 项不得晋级**。`qlib-native-l0-20260915-6c` 后续发现 provider 时间轴与公式翻译缺陷；修复 provider 上仅完成 400/2000 的中断试算，未形成有效新 L0 集合。L1/L2仍BLOCKED。用户最新批准：L0最多2000个构造；L1、L2按事前标准全量晋级，不设人数上限；2026-09-14 指示扩容须**不降低去重与质量标准**并优先 PIT 财务/事件字段。此规则替代旧5个及2000→100→20名额限制。

## 目标与并行边界

面向个股月频选股，广泛搜索不同经济机制的因子；优先复用R1和历史研究资产，同时允许生成新的机制构造。T3与T1立即并行，不限于准备：本任务登记审核通过后直接复用已有已验收能力做训练和账户评估，只有具体候选的数据/能力缺口等待T1，其余继续。

前后端接入、生产、日内/短线全面恢复不在范围。2025以后冻结，2015–2024长历史只作探索；T2仍仅诊断两套固定策略，不受本任务扩规模影响。主对话阶段审核属于已授权工作，不逐候选要求用户确认。

## 用户选定预算与计数

| 层级 | 本轮预算 | 计数与用途 |
|---|---:|---|
| L0 构造生成与信号筛选 | 目标2000个去重构造，最多2000个实际评估 | 一个规范公式×方向×参数×股票池/条件×标签期限为一个构造；变化生成新ID |
| L1 成本可行性评估 | 全部通过L0标准者，不另限数量 | 复用已有固定资金账户及费用能力，模型局限显式披露 |
| L2 分钟账户回测 | 全部通过L1标准者，不另限数量 | 每候选训练主/压力，通过冻结规则者再做十年主/压力 |
 
L1每候选至多一个主情景和一个联合压力。L2若有M个候选通过L1、其中H个通过分钟训练标准，则运行2M条训练及2H条十年路径，H≤M≤2000；不再设80条路径上限。阶段晋级不新增公式计数；生成未计算、实际评估、晋级和技术重跑分别计数。技术修复不占新公式名额，但所有运行留档。

2000是L0广度目标和新增构造评估上限，不要求用同义公式或明显无效数据凑数；少于目标必须报告去重、合法性、数据缺口及资源原因，不能完成少量构造就称2000规模任务完成。L0预算耗尽只停止新增构造，已通过者仍须完成后续阶段。不得以排名、计算资源或通过人数截断晋级，也不强行凑通过者；所有登记构造及其应有后续路径处置后收口。

## T3-A：搜索空间及运行前登记

1. 检查现有R1、失败原因及公式资产，保留继承和既往观察史。弱信号失败不能换名重测；有数据/实现修复理由者另列修复队列及预算，不暗中混进新构造计数。
2. 搜索覆盖至少8类有不同机制依据的家族，优先价量动量/反转、波动与流动性、隔夜/日内分解、价值、盈利质量、成长、投资/资产负债、公告事件等有PIT数据支持者。单家族最多400个构造，同一基础模板最多10个窗口/参数/方向变体。数据不足的家族列BLOCKED_DATA，不靠复制可用家族突破上限补数；家族划分按机制而非名字。
3. 允许预登记的有限参数枚举和公式组合；组合深度、算子白名单、窗口集合、参数组合和随机种子先冻结，复用现有编译器/生成器，不为本轮重写搜索平台。所有方向及期限变体消耗预算，禁止结果出来后临时翻方向。
4. 运行前一次冻结最多2000行候选清单、模板、家族配额及身份摘要。分20个最多100行的执行分片，分片只是调度，不根据上一分片收益重新生成下一片。若确需自适应下一轮，先结束本轮并另登记，不称本轮独立验证。
5. 每行包含candidate_id、机制/模板、规范公式及摘要、方向/参数、股票池、字段/发布时间、标签/成熟边界、缺失规则、数据覆盖、交易配置、继承关系。阈值及停止规则可按家族共用登记，不要求为2000行写2000份叙述。
6. 全局登记层间最低覆盖、年度方向一致性、信号/成本门槛，均须可机械判定。具体数值依据既有研究规范和经济含义制定，在结果前审核冻结，不边看结果边补门槛。禁止用Top K、通过比例或事后分位数变相限额。相关聚类只作关联披露/调度，不淘汰达标候选。只作覆盖/语法检查不算收益评估，未冻结不进入收益计算。
7. 用最多20个清单内构造作首片性能及正确性试跑，收益评估也计入2000。登记线程数、内存上限、预计耗时/磁盘、超时处置及命令；使用性能测量调整并发，不用试跑收益调整候选或筛选规则。先确认基础单路径正确，再扩并发。

## T3-B：批量信号筛选及全部达标候选成本评估

- 训练窗口固定2020–2022。标签须在2022年末前成熟，不借2023数据。月频机制须解释信号持续性；额外期限用于筛选即计构造，纯描述期限必须事先列出且不得据此改本轮交易结构。
- 对全部候选批量检查PIT、字段覆盖、有限数、横截面有效数量、年度RankIC、分层收益/单调性、波动、集中度及换手。收益标签使用经核公司行为总收益，不把除权跳变当损失；NaN或缺价归数据不足。
- 按登记门槛判断每个候选，所有通过者进入L1。相关聚类仅使用训练期信号/月度序列，用于关联披露与共享计算；高度相似不是删掉合格候选的理由。大规模清单不等于2000个独立检验。
- L1复用已有能力：R0/R1共享factor_miner编译、求值及信号诊断；R1现有脚本本身不是完整成本账户引擎，成本评估接fixed_capital_portfolio及已有费用/日线执行模块。实际入口、连续现金规则、输出和主压力假设在登记包固定，不重造筛选引擎、不把RankIC当成本收益。日线成本账户不称分钟成交，报告最低佣金、历史税费、换手、未成交假设和容量局限。
- 所有通过L1门槛者进入L2，保留逐项通过/拒绝/数据不足的依据。禁止只选排名靠前者或每簇代表，不能把数据缺失算策略失败。

## T3-C：全部通过L1候选的真实分钟回测

- 默认复用T2的20万元、Top10各9.5%、月末/下一会话、opening_cash_only、原限价有效期、历史费率、5bps/0.005。唯一联合压力为10bps/0.0025。确需其他结构须作为构造内容在运行前登记，不看结果改。
- 先运行训练主/压力，按登记门槛决定是否进入2015–2024连续历史主/压力；均复用任务一验收能力。缺数据标BLOCKED_DATA，不以缩短窗口的好成绩晋级。
- L2清单等于全部通过L1标准者，完整名单及通过依据在该层运行前冻结；没有名次补位机制。技术错误修复同候选重跑，新搜索另登记。
- 十年报告沿T2口径分阶段、逐年/月、成本、回撤、集中度和数据制度。2024年末仅有效估值，不读取2025退出或标签。已观察历史不称确认集，统计UNKNOWN、晋级BLOCK、executable=false。
- 候选的负收益、压力失败及未成交完整保留。任何阶段无通过者，停止后续依赖计算并交付全批结论，不为寻找赢家扩预算。

## 计算、数据和审核协作

CPU信号计算可并行，复用NumPy与共享只读缓存；不重复下载公共数据。baostock获取由T1单一队列串行，东财不并发。进程/内存上限根据试跑登记，失败分片可续跑，代码/输入身份变化必须隔离新批。Flash可用于批量构造、实现和诊断，模型调用费用不计作统计独立性证据。

内存、并发、耗时和数据额度只控制批量、排队及续跑，不构成淘汰理由。资源未就绪者记为待运行或具体受阻，不记策略失败/完成；按稳定candidate_id次序分片，不能一直跳过低排名合格者。共享计算只允许完整输入/配置身份一致且结果可逐候选追溯的复用；相关性高不等于账户轨迹等价。

机器全量校验登记、计数、边界、结果覆盖；审核者抽查家族代表和异常，逐个审核最终L2候选，不逐候选阻塞2000个计算。每一层整体审核一次，分片不要求重复请示；新增具体缺陷按影响范围处理。

## 工件、完成条件与进度

目录：`artifacts/new-factor-research-20260912-N/`。最低产出preregistration.json、candidates.csv、runs.jsonl、stage-results.csv、selection.csv、report.md及L2账户索引；分片状态和每行未计算原因可追踪。身份摘要绑定原始数据/代码/配置/种子，工件只新增不覆盖。

完成需本轮登记构造全部有处置、2000目标的实际完成数/差额原因明确、每层达标集合可复算、全部达标候选的应有路径有结果。待运行/受阻清单须完整交付，但不能标整体目标完成。研究失败可完成流程，不要求产出赢家，不只展示榜首。

配对：[任务三审核](new-factor-research-review-20260912.md)。

相关：GPU 因子引擎建设计划包（提案，未启动）见 [GPU计划](../plans/gpu-factor-engine-plan-20260913.md)。

## T3-A 历史冻结登记摘要（2026-09-13，-2已被-3取代；当前状态见末表）

批次目录 `artifacts/new-factor-research-20260912-2/`（只新增不覆盖；作废 `-1`：
该目录为 wave1 版（829行）、未审核、无收益结果，扩容后由本目录取代，旧目录保留）。
枚举器 `experiments/t3_enumerate_20260912.py` + 扩容目录
`experiments/t3_catalog_wave2_20260913.py`（复用 factor_miner compiler/validator/
merge_duplicates；不重写搜索平台）。

- **清单 1482 行**：R1 池继承 215 行（标签期限冻结20会话、parent 谱系保留；家族去重账 213 结构）+
  新目录 1267 行（201 模板×≤10变体；生成 1299 条，8 条与 R0/R1 精确同公式在登记期拦下，
  24 条 lhb 稀疏字段窗口聚合在目录期删除——全窗非None才输出，实际全None）。
  身份：`hypotheses.jsonl`、`preregistration.json`、`catalog.json`、`candidates.csv`
  sha256 见 `enumeration_report.json`。
- **家族 17 个**（MOMREV 106/VOL 181/LIQ 138/OVERNIGHT 116/VALUE 96/SIZE 40/FLOW 101/
  CORR 168/PATH 88/VOLDYN 57/COST 77/XINTER 40/SHAPE 32/TREND 64/VOLCOND 91/CANDLE 72/
  R1-STATE 15），单家族≤400、同模板≤10变体；4 个机制缺口登记不凑数：
  EVENT=BLOCKED_CAPABILITY（事件路径未解锁，交 T1）、GROWTH/INVEST_BALANCE=BLOCKED_DATA
  （无 PIT 财务字段）、STATE_CONDITIONAL=BLOCKED_LAYER（市场级序列在公式层只是
  全截面共同缩放，秩不变）。
- **设计纪律**：同义纪律（单调变换/共同缩放/倒数不单列构造）、稀疏字段只作逐点元素形态、
  无单目负号；92 个字段类全部落在真实 bundle 字段集内（机械核对 MISSING=none）。
- **门槛**（原样复用 R0 冻结协议）：L0=|月 RankIC|≥0.02 ∧ 月块 bootstrap
  (B=10000/块3/种子20260909/alpha=0.10，Bonferroni n_tests=求值槽位数，自动派生)
  CI 不含零 ∧ 方向一致；有效月<24 → P5_STAT_INSUFFICIENT（数据不足，不算策略失败）；
  年度方向一致性（3年中≥2年同向）披露与 L1 暂停条件。无 TopK/通过比例/事后分位数门槛。
- **本轮范围（用户 2026-09-13 决定）**：**先只挖因子（L0 信号筛选）**；L1 成本账户与
  L2 分钟回测等 T1/T2 能力就绪后再启动（L2 训练窗分钟数据还受 T1 G3 缺口限制）。
- **执行身份**：运行快照 `D:/AI/workspace/t3-snapshot-20260913`，快照内提交
  `d119444c`（＝主仓当前工作树状态冻结；主仓分支/工作树未改动）。原因：HEAD f32568f
  不含未提交的 `descriptive_contract.py`/`r0_audited_runner.py`/
  `fixed_capital_portfolio.py` 等受审文件，而 R0/T2 已验收证据基于该工作树状态；
  按“运行中固定代码快照”冻结，受审文件 sha256 见 `-2/snapshot_manifest.json`
  （enforce 等价校验 missing=0/dirty=0）。试跑命令
  `FACTOR_MINER_NUMPY=1 python -m experiments.factor_miner.director pipeline
  --hypotheses hypotheses-trial20.jsonl --out trial20-run --allow-real-run`；
  全量批走 `experiments/r0_audited_runner.py`（48h 超时）。
  预算缺口 518（目标2000）：算子白名单+字段表限制、同义纪律不做凑数、
  EVENT/成长/投资家族机制缺口、固定月频标签、单家族/单模板上限，
  见 `enumeration_report.json::roster`。

| 阶段 | 状态 | 执行者/批次/审核证据 | 下一步 |
|---|---|---|---|
| T3-A 登记与试跑（wave4） | **登记+试跑完成待复核**；旧 -8/-11 遗留项由本批取代 | 主对话Codex，2026-09-14：批次 [`-15`](../../artifacts/new-factor-research-20260912-15/)（2000 行 = 1430 基础 + 509 wave4 + 61 wave3 部分登记；20 片×100；[全清单审核](../../artifacts/new-factor-research-20260912-15/roster-audit-20260914.md)、[试跑报告](../../artifacts/new-factor-research-20260912-15/trial20-report.md)、[清单](../../artifacts/new-factor-research-20260912-15/hypotheses.jsonl)、`run-identity.json`）。生成期六项检查与 20 行真实试跑见文末 2026-09-14 节；`-14`（同清单，trial 未覆盖事件路径）与 `-13`（未运行）被取代，均原样保留 | 限定复核本批（登记/检查/试跑）；全量 L0 待用户恢复授权（恢复前须先处置重片内存，见试跑报告 §4） |
| T3-B L0 全量筛选 | CHANGES_REQUIRED → 三轮整改完成待定向复核 | R1–R5（`-5` 复审）与 S1–S3（`-8` 复审）已整改：身份改为分组无关的 canonical+窗口键并**用结果自身公式重算键**、`adopted_direction` 必须存在且等于登记、片完成＝**该片预期键集合精确相等**（重复+缺项即拒）、结果绑定 run_meta（code/data/候选数）、run 扫描磁盘现存 attempt 且新编号避开已存在目录、未成熟末月（2022-12-30）非空 IC 判数据异常。定版 **`artifacts/new-factor-research-20260912-11/`（1430 行＝继承205+新增1225，198 模板，20 片 72×19+62）**，`hypotheses.jsonl` `6af8d4b8ae013ed0`、`run-identity.json` `eb5dd2b07f947647`；测试：正常路径 1430/1430 接受、负例 N0–N16 全符合预期（`-11/normal-path-test.json`/`negative-tests.json`）；送审材料 `-11/SUBMISSION.md`、整改记录材料包 §11–§13 | 定向复核后按用户决定是否跑试跑/全量；R6 wave3 独立登记（PENDING） |
| T3-C L1/L2 | BLOCKED（等 T1/T2） | 用户 2026-09-13 决定：能力未就绪前不启动验证层 | T1 数据/执行能力、T2 冻结口径就绪后启动 L1 成本账户、L2 分钟回测 |
| P1 性能优化（并行轨道） | 实施完成待独立复核 | 隔离副本 `D:/AI/workspace/factor-engine-perf-isolated-20260913`；交付包 `artifacts/factor-engine-performance-20260913-2/`（`manifest.json` + `remediation-20260913.md` + `baseline.md` + `review.md` + 七项证据）。冻结身份：`director.py` `4acbda144d4d2285`、`stats_np.py` `d8d1e7a94543ec61`、`t3_l0_worker_20260913.py` `29cb6d5e491b6a40`。285 股背靠背 A/B `PASS_EXACT`（`n_diffs=0`）train_test **2.19×**；检查点/身份/门禁/恢复 29 用例 + 真实 CLI 端到端（`-8` 真实分片）全过。**主仓未切换** | 新快照 + 明确切换记录后再用于本轮余下候选；全量 20 片与全池装载实测未做 |

## P1 性能优化实施记录（2026-09-13，执行侧）

**范围**：并行轨道，不改 T3 冻结清单、不改正在运行的批次工件、不改主仓工作树。
计划入口 `docs/plans/gpu-factor-engine-plan-20260913.md` §9。

**做了什么**（隔离副本 `experiments/`）：
1. `factor_miner/stats_np.py`：排名内核游程向量化（逐位等价）；静态面板缓存
   （opt-in，默认关），**池掩码键含完整日期轴**（审核 M-4 整改）。
2. `factor_miner/director.py`：截断 close 复用（**opt-in，默认关**）、因子去重复
   计算、`preloaded` 装载复用入口、`train_test`/`evaluate_units` 显式 `n_tests`。
3. `experiments/t3_l0_worker_20260913.py`（新增）：长驻 worker（一次装载顺序消费全部
   分片）+ 冻结清单口径汇总器 + 检查点身份/attempt 恢复 + `preloaded` fail-closed 闸。

**身份与口径对齐（与 -8 复审一致）**：
- 单元身份 = 清单行自身的 **`canonical_eval_key`**（不是 dedup 派生的执行槽位 ID）。
  实测 `-8` 清单上两种口径的逐片并集相差 **212** 个 ID，canonical 键相差 **0**。
- 结果行须**用行内 formula 重算键**并比对，`adopted_direction` 必须存在且等于登记方向，
  并绑定 `window_params`/`code_commit`/`data_version` 与 `run_meta`（S1）。
- 有效月 = **冻结月末轴**内、按 YYYY-MM 唯一升序；**未成熟末月不得有 IC**（S3）。
- `n_tests` = 全清单唯一键数；`run`/`aggregate` 共用同一验证器。

**证据**（`artifacts/factor-engine-performance-20260913-2/`）：
`checkpoint-test.json`（29 用例）、`cli-test.json`（真实 CLI 端到端，`-8` 两片真实分片
× 285 股）、`equivalence/ab_compare_n300.json`（`PASS_EXACT`）、`kernel_equiv.json`、
`l0-only-vs-cost-ladder.json`、`worker-cross-slice-equiv.json`、`load-scaling.json`。

**未做 / 待办**：
- 全量 20 片未跑；全池（5552 股）装载与计算倍数**未实测**（`baseline.md` §6 披露）。
- 未做 GPU 原型（按测量停止，`review.md` §8）。
- 主仓路径未切换；性能证据绑定样本清单 `-3`（1456）与 `-8` 分片字节，切换前须按
  新快照重新绑定并重测。

---

## 实施记录：因子引擎性能优化 A/B/C/D/E 阶段（2026-09-13，批次 `-4`）

**入口**：`docs/experiments/t1-t3-implementation-review-20260913.md`（F1–F4、阶段 A–E、
§9 工件要求）。**实施位置**：隔离副本 `D:/AI/workspace/factor-engine-perf-isolated-20260913`
（主仓工作树**未改动**）；A/B 对照侧 `D:/AI/workspace/factor-engine-perf-a-20260913`（`b231c110`）。

**交付批次**：`artifacts/factor-engine-performance-20260913-5/`（57 工件，`missing: []`）。
取代 `-3` 的结论范围；`-3` 的 `manifest.json`/源码/证据原样冻结、不改写。取代原因见包内
`VERSION.md`：①`-3` 的 GPU 等价性声明未覆盖"缺失/±inf 交错"缺陷；②`-3` 的 profile 遥测
取在 `build_real_bundle` 之前（恒为 0）；③`-3` 的 VERSION 自述 B2"默认开启"与实现的
opt-in 状态不符。

### 正确性整改（A）

| 项 | 内容 | 证据 |
|---|---|---|
| F1 | `engine.input_content_digest` + `director.run_real_pipeline` 当场重算闸（缺/伪造即 fail-closed）；手工 `preloaded` 旁路入口同步补绑 | `identity-tests.json` `f1_*` 13 项 |
| F2 | 批跑入口按实际消费数据根重建清单并用 `r0_audited_runner.verify_data_manifest`（唯一实现）核内容 + 根 real-path 绑定 | `identity-tests.json` `f2_*` 15 项 |
| F3 | 比对器精确/容差分层；`float_diff>0` 不得签 `PASS_EXACT`；决定性字段容差感知 | `compare-selftest.json` 11 项（含 4 项实质性分歧负例） |
| F4 | 性能算术与口径更正（5.14–18.29%；撤回 p≈0.33；13/69.2 min 降为情景假设；三档分母分开） | 包内 `baseline.md` §2 |

### CPU 优化（B）

- **B1 默认生效**：`stats_np.spearman_np` 去两次冗余排序，300 组对抗用例逐位相同。
- **B2 opt-in**：装载备忘（loader + 路径令牌 + `(realpath, mtime_ns, size)` + 参数），
  885→实测装载 **1.34×/1.36×**，进程 wall **1.23×/1.25×**；运行状态写入
  `run_meta.perf_caches` + 证据 `load_memo` 计数（B 侧 hits 972 / misses 764，A 侧 `None`）。
- **B4 opt-in**：聚类月末值就地生成，日频因子即释放；A/B 两轮 `PASS_EXACT`。
- **B3/B5 不实施**：插桩实测 `b3.series_matrix` 0.152s / `b3.close_panel` 0.007s /
  `b5.pool_panel` 0.011s = wall 的 0.34% → 收益不支持（先测后改）。
- **缓存绑定输入身份**：`stats_np.panel_cache_bind` + `director.bind_perf_caches_to_input`，
  换 bundle/轴即整表失效；§9.3 缓存换输入负例 8 项。

### GPU 局部原型（C）：**不采用**

热点在真实截面形状 2.72–2.88× ✅（`block=None` 与协议 `block=128` 两套配置均 ≥2×），
但**同源端到端 1.32× < 1.5×** ✗ → 不切换、不扩大投资。真实衰减段只占端到端 0.455
（装载占 82.5%，GPU 不覆盖）。修正 `_average_ranks_batch_torch` 缺失/±inf 交错缺陷
（两趟稳定排序 + 压紧回填 + 每列哨兵），对抗 10 例 0 mismatch；补块边界
（1/128/129/896/972）与 OOM 减半/回落协议。

### D 阶段：不启动

进入条件"B/C 后有实测剩余热点"不满足：B3/B5 已否决（<1%），未出现新的支配性热点。

### 全量状态：**未启动**

用户取消状态未恢复；20 片 / 5552 股未跑。`load-scaling.json` 给出外推
（slope 0.1277 s/symbol、intercept 28.0s → 全池 ≈737s ≈ 12.3 min），**明确标注为外推**。

### 身份与证据纪律（本轮更正）

证据新鲜度改为**按依赖面**判定：每条证据声明其读取的源码集合与生成器，逐文件比对 mtime，
并把依赖文件当前 sha256 写进 `manifest.json::evidence_provenance`。旧口径（证据须晚于 HEAD
提交时间）既不充分也不必要——只改打包工具或文档本不应使任何证据失效。打包器同时改为
暂存后原子发布：缺件/依赖更新/文档缺失一律非零退出且不留下产物。

### 下一步

1. 独立限定复核本批次（`-4`）；2. 登记 T3 新快照并提供经 CLI 验证的启动/恢复与 CPU 回退命令；
3. 用户恢复全量授权后按新快照运行并核 1430 覆盖。

### 2026-09-13 性能包 -5 主对话独立审核（覆盖该优化轨道此前当前状态）

执行状态：CHANGES_REQUIRED；整体交付/切换准备审核：CHANGES_REQUIRED；已测CPU优化、F1/F2局部修复和F3：PASS_WITH_LIMITATIONS。其他研究阶段状态不变，整体未完成，全量保持未启动。

审核记录：[性能包-5独立审核](../experiments/factor-engine-perf-independent-review-20260913.md)。受审源码2c3a31f3、59件摘要一致；亲跑输入身份40/40、比较器11/11、检查点29/29、B1对抗300/300。独立证据在 artifacts/factor-engine-performance-review-20260913-1/，命令见审核报告末尾。

下一步仅修R1–R5：worker消费事前冻结代码/数据契约并核收尾；证据绑定运行时摘要及补齐依赖；纠正GPU计时口径；回退显式--backend pure；补小规模新进程CLI并更正交付范围。GPU局部原型已做、当前不采用，旧“未做GPU原型”不再作为当前事实。-12只登记身份，未获本审核切换放行；不修改冻结旧包，不启动全量或L1/L2。

### 2026-09-13 R1–R5 整改实施记录（批次 `-6`；`-5` 保持冻结不改写）

执行状态：R1–R5 已整改并重跑证据，待限定复核（未完成整体目标 → 不写 DONE）。受审身份见
新包 `artifacts/factor-engine-performance-20260913-6/manifest.json`（取代 `-5`）。

| 项 | 落点 |
|---|---|
| R1 | worker 消费事前冻结身份：`batch_mod._verify_identity` 在**装载前/恢复前/汇总前**各一次，摘要作为 `frozen` 段并入运行身份 → 检查点与 session 自动绑定冻结 manifest 摘要；收尾 `_verify_data_identity_tail` 复核原始文件；无装载快路径保留，但 ledger 显式标 `verification_mode=resume-artifact-only` + `data_identity_tail.checked=false`（历史工件核对）。worker 加入 `T3_SCRIPTS`，用**新批次 `-13`** 登记（`-12` 不改写） |
| R2 | 证据新鲜度改**内容比对**：运行器 `t3_perf_run_evidence_20260913.py` 在生成器**运行前后各算一次**依赖源码 SHA，不一致即不产侧车；打包器拿记录值比当前字节，mtime 仅辅助。依赖表 `t3_perf_provenance_20260913.DEPS` 为单一事实来源，补齐 `r0_audited_runner`（identity-tests）与 `director`（gpu-bench）；**并撤回反向的过度声明**：A/B 的 `MEASUREMENT_PATHS` 去掉 worker（A/B harness 不 import 它，列上会逼出一次无谓重跑） |
| R3 | GPU 判据按**实际运行配置**分别评估：blocked 热点 1.66×（不过 2×）；不分块 2.13×（过热点）但计算阶段估计 1.318×（不过 1.5×）→ `adopted=false`、通过配置数 0。合成面板数字单列 `basis`，不再冒充真实配置达标；撤回"全池占比升到 0.5–0.55"的预测（无证据假设） |
| R4 | CPU 回退更正为显式 `--backend pure` + 新输出根；"清环境变量"不是回退手段（已钉成新进程证据与反例） |
| R5 | 同进程 harness / 新进程 CLI / 全量研究三者分开表述；任务书陈旧文字更正（`-4` 标题、57 件、"未做 GPU 原型"） |

**新增证据**：`frozen-identity-negatives.json`（8 例）、`package-negatives.json`（6 例，含
"字节改变但时间戳不变仍拒绝"）、`cli-newprocess.json`（真新进程启动/中断恢复/显式回退/反例/
无身份被拒）、`label-sentinel.json`（训练尾哨兵 + 边界锐利性对照）、各证据同名 `.prov.json`。

**计数变化说明（夹具补齐，不是缩水）**：`checkpoint-test` 29 → 31（+2 条 R1 frozen 负例）；
`identity-tests` 40（不变）；`compare-selftest` 11（不变）。合成 roster 夹具现由生产入口
`cmd_identity` 铸身份、数据面换成微型根，避免 2 万文件真实数据树在测试期间漂移导致假失败。

**仍未做**：全量 20 片未跑（用户取消状态未恢复）；全池性能未实测；切换未放行；L1/L2、
统计 UNKNOWN、晋级 BLOCK、2025+ 与生产保持冻结。


### 2026-09-13 Codex续做（当前状态：RUNNING）

D1规范路径身份修复已在12根20275文件上通过；D2测量提交改正且两轮A/B PASS_EXACT；D3/D4生成器与A侧字节交付补齐；D5负例仅改临时副本并断言复原，D6夹具不能产正式门禁。检查点31/31、身份40/40、冻结负例8/8已实测。新进程pure回退已产生pure账本，剩余默认后端反例正在运行。CPU代码仍仅在隔离仓；用户已明确允许仅提交隔离仓本次整改以冻结新快照，须等在飞身份验证结束后提交。-13和-6仍待完成，不宣称已经交付。

T3全量未启动，1430分母不变，缩样结果不是研究发现。另按用户请求T2十年信号已完成（5552证券/两策略各120月）；用户将提供分钟数据，T2四账户仍未运行，记录见对应任务书。


### 2026-09-13 新快照登记完成（性能包仍待最后打包）

隔离提交 `43dba5b6ffa1500322471bb97fe7c22c05734420`，用户明确授权仅提交隔离仓本轮整改；主仓未提交。新快照 `D:/AI/workspace/t3-snapshot-20260913-3/`，55受审文件通过 `enforce_code_identity`。新登记 `artifacts/new-factor-research-20260912-13/`：20片，1430项清单不变；`identity-verification.json` 实测启动/收尾PASS，20275文件，digest=b19006a6d4797d530137247efe970dd7ce414dc291031c8680e770ec8b512015。旧-11/-12不改写。入口保留历史顶层导入，模块命令需显式 `PYTHONPATH=<快照>/experiments`。

小样本新进程CLI 7/7（8项、40证券），同进程CLI 9/9（144项、40证券），两者run_scope=validation_fixture，不签正式门禁。另 `formal-contract-newprocess.json` 实际1430项清单的新进程numpy/pure身份/分母/配置接线2/2，哨兵在数据装载前停止，无全量求值。L0-only与cost-ladder20项输出逐位一致；跨片证据和打包负例最后串行收口。T3全量仍未运行。


### 2026-09-13 CPU整改交付终核（唯一当前状态）

CPU性能整改执行状态 DONE，审核 PASS_WITH_LIMITATIONS（限定隔离实现、交付包与新快照接线；不代表T1/T2整体完成）。交付 `artifacts/factor-engine-performance-20260913-6/`：101件摘要独立重算0差异、25件证据内容来源通过、5份diff应用后源码一致、A侧5文件字节复核一致、missing=[]。最终复核 `artifacts/ten-year-infrastructure-20260912-2/performance-package-review.json`，包manifest SHA256 `6b33b880b048e65c6ecb7725af9d3f7c8466909661cf63b8fdb0bdeb8c9ea810`。

D1规范化修复实测12根20275文件mixed/canonical/repeat/verify通过；历史清单口径不再沿用且旧工件不改写。D2真实B测量提交12c5c0d54d3b2b1079dcb8676c5cb134f5088c76，机械diff证明测量路径未变，A/B两轮PASS_EXACT、0差异。D3新生成器随包交付；D4双侧SHA与A字节齐全；D5临时副本变异、mtime回拨仍拒绝且复原SHA相等、真实核心源码未动；D6夹具禁止正式gate，另真实1430清单新进程接线2/2且在装载前停止。

最终测试：身份40/40、检查点31/31、同进程CLI9/9（40股/144项）、新进程CLI7/7（40股/8项）、冻结负例8/8、打包负例6/6；L0-only20项逐位等价、跨片6文件及run_meta一致。CPU原A/B样本装载55.190/55.934s→41.134/41.122s（1.34–1.36倍），求值9.083/9.109s→8.757/8.705s（1.037–1.046倍），不是全池wall测量。GPU保留原型、不采用，未外推全池。

用户授权隔离提交已执行：运行源码43dba5b6ffa1500322471bb97fe7c22c05734420，打包器字段修复ac669ef（仅交付工具）；新快照 `D:/AI/workspace/t3-snapshot-20260913-3/` 保持43dba5b6，55受审文件干净校验通过。新批 `artifacts/new-factor-research-20260912-13/` 的启动/收尾原始数据核验PASS，20片/1430分母不变；未运行全量。模块命令需 `PYTHONPATH=<快照>/experiments`，pure回退显式 `--backend pure` 且新输出根。主仓性能源码未覆盖、主仓未提交，不能整仓覆盖较新的T1修复。

T1整体仍未完成：A DONE、B WAITING_REVIEW、C RUNNING；T2-A DONE、B BLOCKED、C PENDING。十年信号5552只、两策略各120月完成并审核，旧窗口信号回归与重叠选股/权重/日期一致；用户将提供分钟数据，四账户未启动，2015–2019缺口保持，不用日线替代。统计UNKNOWN、晋级BLOCK、2025+/生产冻结。下一步只接收分钟数据并推进实际订单依赖及四账户；T3全量取消状态未改变。

保留本轮失败记录：首次CLI批检查点旧正式gate断言与stdout格式失败，修后31/31；首次打包缺GNU工具已改difflib/git apply；正式打包旧mtime汇总字段KeyError已在ac669ef修复。预检临时目录清理被自动策略拒绝（blocked by policy），未再删除；失败staging不是交付，只有带manifest且经上述终核的-6是正式包。

---

## 2026-09-14 T3 wave4 扩容（PIT 财务/事件字段）登记、全清单审核与 20 行真实试跑（唯一当前状态）

**用户指示（2026-09-14）**：优化重点是**扩大合规构造数量**（不降低去重与质量标准）：
增加可审计机制家族、优先补齐 PIT 财务成长/投资/资产负债/事件字段、族内事前冻结有限
参数组合、单家族≤400/同模板≤10、避免仅换窗口/乘常数/反向/互补；允许复用算子与字段但
须产生新的规范结构、`candidate_id` 与身份摘要；对新增构造运行生成期检查（公式合法性/
方向一致性/空条件/同义重复/PIT 边界/数据覆盖）；先补到约 2000，再做完整清单审核与
20 行真实试跑；**引擎本身保持不变**。

**执行者/审核**：主对话 Codex（实现＋本轮阶段审核，绑定实际 diff/工件/数值）。

### 交付物

| 类别 | 工件 |
|---|---|
| 字段覆盖能力（白名单 v2） | `experiments/factor_miner/data_fields.py` 追加段：156 个 PIT 财报字段 + 24 个公告事件字段；`STMT_FIELD_MAP`/`EVENT_FIELD_MAP` 与落库表头机械核对；PIT 规则见下 |
| 引擎接线（追加式，求值路径不变） | `engine.build_real_bundle(with_statements/with_events/statement_fields/event_fields)`（显式字段集，缺则 fail-closed）；`director.extended_scope_from_units` 按实际求值单元推导字段 |
| 目录/枚举/检查脚本 | `t3_catalog_wave4_20260914.py`（222 模板）、`t3_enumerate_wave4_20260914.py`、`t3_synonym_check_wave4_20260914.py`（秩等价 v2 台阶语义）、`t3_wave4_field_coverage_20260914.py` |
| 测试 | `tests/test_factor_miner_wave4_fields.py`（19 例：PIT 边界/陈旧/冲突/真重复/事件滚动和/解禁前瞻/缺轴 fail-closed/注册表/求值）；`tests/test_factor_miner_c_components.py` data_version 契约同步 v2 |
| 批次 | [`artifacts/new-factor-research-20260912-15/`](../../artifacts/new-factor-research-20260912-15/)：`hypotheses.jsonl`（2000 行）、`slices/`（20×100）、`candidates.csv`、`catalog.json`、`preregistration.json`、`enumeration_report.json`、`field-coverage.json`、`roster-audit-20260914.md`、`trial20-report.md`、`run-identity.json`、`l0-trial20-attempt3/` |
| 运行快照 | `D:/AI/workspace/t3-snapshot-20260914-1` commit `4f44138b`（含本轮字段/接线/身份修复） |

### 时点与口径（frozen）

* 财报：`available_at=latest_report_ann_le_t`——同一报告期**最早公告组**（`max(ann_date, f_ann_date)`
  取更晚者）≤ t 才可见；`ann_date < end_date` 行剔除；同 `(ann_date, update_flag)` 真重复整期丢弃；
  字段冲突 → None（fail-closed）；陈旧上限 `FIN_STALE_DAYS=459` 自然日（沿用 R1 财务筛选口径）。
* 事件：`available_at=event_ann_le_t`（`ann_date ≤ t` 当日可见）；滚动和为轴窗口；解禁只使用
  公告时已知的未来安排；`ev_*_days` 只登记字段、**不构成构造**（避免与已封存的 E1–E4 事件漂移重测）。
* 序列形态：两 loader 均产出**包日轴等长稠密序列**（前值结转 + 陈旧上限），与算子层窗口语义兼容。
* 数据身份（v2）：`data_version()` **始终**含扩展来源（`FIN_STMT`/`EVENT_DETAIL`），使同批次内
  引用/不引用扩展字段的分片共享同一身份；实际装载字段集逐候选记入 `extended_fields`。

### 清单与生成期检查结果（[全清单审核](../../artifacts/new-factor-research-20260912-15/roster-audit-20260914.md)）

| 检查 | 结果 |
|---|---|
| 规模/身份 | 2000 行 = 1430（-11 定版 sha `6af8d4b8…`）+ 509 wave4 + 61 wave3；2000 唯一 canonical+窗口键、2000 唯一公式、1691 模板 |
| 家族/模板上限 | 单家族 ≤400 ✓、同模板 ≤10 变体 ✓（无违规） |
| 公式合法性 | wave4 512 行、wave3 520 行全部通过编译与 validator 六条（0 拒绝） |
| 方向一致性 | 同结构组方向统一 5 处（符号移入公式，假设等价） |
| 空条件 | 剔除 15 行（wave3 池恒非零 IF 条件），逐行入修复队列 |
| 同义重复 | canonical+窗口去重 1；秩等价筛查（合成面板）剔除 7（对先验 1、池内 6）；75 行合成面板退化未参与判定（已披露） |
| PIT 边界 | 注册表 available_at ∈ PIT_SAFE + loader 反例测试 19 例全绿 |
| 数据覆盖 | 全池 5552 只 × 36 个月末截面实测：主力财报字段 0.82–0.85、事件字段 0.28–0.75；覆盖门 20% 剔除 1（`W4-EVENT-EV19-now`，回购价格上限 0.178）；低覆盖字段（<20%，现金流明细类）登记为数据缺口不建构造 |
| wave3 登记规则 | 市场级序列仅允许作窗口聚合内部回归量/CORR 输入（AST 机械判定），作乘子或 IF±1 公共开关拒收（本轮 0 拒收）；按家族轮转填预算（非收益选择），余 438 行 PENDING |

### 20 行真实试跑（[试跑报告](../../artifacts/new-factor-research-20260912-15/trial20-report.md)）

* 命令：快照内 `python -m experiments.factor_miner.director pipeline --hypotheses <批>/hypotheses-trial20.jsonl --out <批>/l0-trial20-attempt3 --allow-real-run`（全池 5552 只、训练窗 2020–2022）。
* 覆盖四条数据路径：事件 6 / 财报 8 / 混合 3 / 既有价量 3。
* 结果：`COMPLETED_DESCRIPTIVE` 20/20、技术失败 0、每候选 35 个有效月；20/20 门禁未过（P8，预期——试跑只作路径证据）；`statistical_validity=UNKNOWN`、`promotion_gate=BLOCK` 不变。
* 描述性读数（仅路径证据，不作有效性结论）：`W4-EVENT-EV01-now`（预告净利中枢/市值）均值 RankIC **+0.0401**、`W4-EVENT-EV08-now`（快报净利/市值）**+0.0440**，两者 CI 均含零；杠杆族 6 行方向与先验相反（描述性，不据此翻方向/改门槛）。
* 试跑中修复的自身缺陷（留痕）：①首次接线会装载全部 155 字段（内存不可接受）→ 改显式字段集 fail-closed，attempt1 未读数据即终止；②attempt2 身份串不一致（registry 扩展串 vs candidates/run_meta 旧串）→ 统一 v2 数据身份 + `extended_fields` 落盘后重跑 attempt3（attempt2 工件保留为缺陷证据）。
* 资源画像：20 行冷缓存约 48 分钟 / 热缓存约 30 分钟（含 bundle 构建）；峰值内存抽样 5.1–6.6GB。**全量前置待办**：按 id 序分片时含扩展字段的片（15–20）需 14–37 财报字段 + 0–12 事件字段，估算 7–9GB，叠加基础 bundle 接近 15.6GB 上限 → 恢复全量前须改分片序/加片数/分两遍（三选项已登记）。

### 继承与不重测声明

* R1 财务筛选 F6–F31：同字段不同判据/口径 → 记新构造，不复用其结论；字段重合在家族机制文本披露。
* 事件族 E1–E4（round-20260909 封存）：本轮不作事件窗漂移与距公告天数读法，只用月末截面状态量；E1“差 3.3bp”不作为调参或换判据理由。
* wave3 原始池只部分登记（61 行），余 438 行 PENDING（非失败、非收益筛选）。
* 死区 DZ-001/DZ-002 与本批交集 0。

### 状态

* T3-A：本批登记/检查/试跑完成，**待限定复核**（主对话阶段审核记录见上；-8/-11 的 S1–S3 遗留项由本批的统一身份与新的 `run-identity.json` 覆盖）。
* T3-B（全量 L0）：**维持用户取消状态，未运行**；`-15/run-identity.json` 已冻结（21 文件/20 片/期望月末 36/未成熟 2022-12-30），恢复授权后可直接 `identity→run→aggregate`。
* T3-C（L1/L2）：BLOCKED（等 T1 数据与执行能力、T2 冻结口径）。
* 旧批次关系：`-13`（1430 行，未运行）与 `-14`（同清单，trial 未覆盖事件路径）被 `-15` 取代，原样保留不改写。

### 2026-09-14 独立审核（`t3-construction-review-20260914-1`）与整改终态：`-16`

独立审核对象为 `-15` 与本轮字段/枚举代码，裁决 **CHANGES_REQUIRED**（F1/F2 = P1，F3/F4 = P2）。
整改批次 `artifacts/new-factor-research-20260912-16/`（`-15` 原样保留作缺陷证据）：

| 审核项 | 处置 | 证据 |
|---|---|---|
| F1 过去解禁未检查公告可见性 | 已修（贡献区间语义：`i ≥ max(公告,解禁)` 起，轴前公告夹 0、轴前解禁跳过） | 反例测试 `test_share_float_past_requires_announcement`；影响实测：`ev_sf_past_ratio_250` 4.4% 单元读数变化、区域段 9.4% 单元由“有数”变 None |
| F2 新增源未进冻结输入清单 | 已补 `wave4-input-manifest.json`（26,966 文件 / 2,035MB / 逐文件 sha256 + 聚合摘要），绑入 `run-identity.json`，批跑器启动/aggregate/收尾核验，新增·缺失·变异一律拒绝 | `t3_wave4_input_manifest_20260914.py`；清单负例 4 例；真实核验 `ok=true` |
| F3 滚动和把轴前公告钳到首日 | 已修（轴前公告不入窗 + 引擎按同一日历回补 260 前置会话） | 反例 `test_rolling_sum_ignores_pre_axis_events`；`ev_rp_amount_250` 区域段 1.04% 单元变化 |
| F4 预告/快报差值未按报告期对齐 | 已修（新增 `ev_fx_np_gap`/`ev_fx_fc_np_mid`/`ev_fx_ex_n_income` 同期配对字段；EV15/16 改口径；EV39 新登记） | 反例 `test_paired_forecast_express_requires_same_period` |

其他审核意见：结构模板口径改为 family+canonical（2000 行 → **724 结构模板、单模板最大 10 变体、超限 0**）；
筛查复用凭据补 `catalog_sha256`/`enumerator_sha256`（本轮筛查因此**重算**未复用）；试跑证据绑定快照
`2586c1b`、与性能整合 `3af1fc1` 身份分开；内存处置须按最终实际入口（worker/逐片）分别实测，不假定改分片序可降峰。
受影响构造共 15 行（机械列出，见整改记录 §2），其余 1985 行不受影响；`-16` 试跑为修复后唯一有效读数。
整改记录：`-16/remediation-review-20260914.md`。

**当前状态（覆盖本任务书此前各段）**：T3-A = `-16` 登记/生成期检查/**20 行真实试跑（修复后）** 完成，
待独立复核（本轮为执行者自审整改，不代替独立复核）；T3-B 全量维持取消；T3-C BLOCKED。


### 2026-09-14 启动前专项任务书（仅文档，未启动计算）

用户要求编写第2、3项，已交付[引擎及接线验收、真实小批试跑任务书](t3-engine-integration-and-trial-20260914.md)。先核第三轮性能修复及最终绑定，再以最终清单完成真实小批、恢复与独立核算；进度仍写本任务书，不另开任务板。本条不改变既有执行/审核裁决，不恢复已取消的T3全量运行。
### 2026-09-14 任务2 完成，T3 全量仍未启动（当前 T3 前置状态）

依赖：任务书 `t3-engine-integration-and-trial-20260914.md` 任务2 已通过（PASS_WITH_LIMITATIONS），交付 [artifacts/t3-engine-integration-20260914-1](../artifacts/t3-engine-integration-20260914-1/report.md)；整合仓 `D:/AI/workspace/t3-engine-int-20260914-1` @ `3af1fc1`。
对 T3 的意义：正式 L0 入口（`t3_l0_batch_20260913.py` → `t3_l0_worker_20260913.py`）在该身份上完成启动 / 幂等恢复 / 中断恢复 / 汇总 / 身份拒绝验证；wave4 扩展字段候选现在按清单装载并可求值（修复前编译期硬失败）；`run_meta` 与候选行的数据版本标签随 bundle 实际版本写出。
登记状态：最终清单（≤2000 去重构造）与门槛**尚未冻结登记**；现有 `-13` 清单 1430 项为历史登记，实测 0 行引用 `fin_`/`ev_` 扩展字段，故本次接线对 `-13` 无内容影响，对后续含扩展字段的清单是必要条件。
未做：任务3（≤20 项真实小批试跑）未开始；全量 L0 未启动，用户既有取消状态未恢复；本阶段未生成新登记包、未产出试跑清单、无任何收益计算。
下一步（待授权）：冻结最终清单与门槛并送审 → 事前固定 ≤20 项试跑清单 → 按任务书 3.2 真跑（含分片边界与中断恢复、逐候选身份核对、独立重算月 RankIC 与有效月计数）→ 交付 `artifacts/t3-real-trial-20260914-N/`。


### 2026-09-14 2000构造独立审核（覆盖登记审核当前结论）

T3-A执行/审核CHANGES_REQUIRED。主对话独立核2000行、2000唯一求值单元、20×100分片精确一致，19字段测试通过；发现过去解禁字段漏公告门、最终输入清单漏财报/事件源、轴前事件滚动错位、预告/快报未对齐报告期。见[审核报告](../../artifacts/t3-construction-review-20260914-1/review.md)及evidence.json。实际当前清单为-15的2000项，覆盖旧“仅1430/未登记”描述；不同快照试跑与性能接线证据不互相替代。仅审核，不改算法、不启动真实计算、不恢复全量；整改及依赖影响按报告推进。

### 2026-09-14 VectorBT 可用性试验启动（最新用户授权）

用户批准先试 VectorBT，再写计划并派子代理执行；仅授权成熟引擎可用性及最小适配试验，不恢复 T3 全量。执行 RUNNING，审核 PENDING。公共代码所有者仍为 T1，本轮不修改公共引擎；主对话负责环境初探与最终审核，GLM-5.3/high 子代理 Carson（01a09fb9-fdad-7402-a23a-966db902fe8d）独占新试验文件和隔离环境。

隔离环境：D:/AI/workspace/vectorbt-pilot-env-20260914（Python 3.11.15）。初测 vectorbt 1.1.0 安装完成，但 import 因 Plotly 7.0.0 的 scattermapbox 模板不兼容失败，已交子代理固定兼容依赖并留痕。计划交付 docs/plans/vectorbt-t3-pilot-plan-20260914.md，证据 artifacts/vectorbt-t3-pilot-20260914/（待生成）。L0 继续理解为公式求值/RankIC，VectorBT 优先评估批量账户回测用途，不预先认定可替换 L0 或 L2。当前 T3-A 的 PIT/身份整改结论保持，先以合成夹具检查账本、费用、共享现金、整手及 T+1 边界；不读取 2025+，不改候选/门槛，不购买商业版，不改正式入口。

### 2026-09-14 VectorBT 对比扩大到10因子十年（最新用户授权）

用户在单因子同输入对比之后要求10因子回测10年；本轮按引擎性能对照解释，固定2015–2024，2014仅预热，不启动全量T3。执行RUNNING，审核PENDING。前一轮2020年30股/243会话/1因子/106成交，两引擎实际订单及逐日账本一致（最大差2.91e-11）；完整adapter热中位0.2688秒，fp 0.01075秒，仅证明当前接法该规模慢约25倍，不外推。

新批 artifacts/vectorbt-ten-factor-ten-year-20260914/，GLM-5.3/high子代理Turing（01a09fec-5e58-7c20-b7f4-aaaf1e70e5c9）独占新脚本/适配副本/结果，主对话负责审核和本状态入口。固定-15清单中仅OHLCV依赖的原顺序前10项，原方向，禁止按结果选因子；小股票池明确工程可用性偏差，不伪装完整历史选池。新进程首次及三次热运行，同输入逐笔/逐日对账，计完整适配转换时间，公共装载和因子计算单列。动态印花税按2023-08-28切换；未接公司行为等限制明确披露，结果不支持盈利结论。公共引擎、原始行情、已有工件不改写，2025+冻结保持。

### 2026-09-14 10因子十年同输入工程对照完成

执行DONE，限定工程比较审核PASS_WITH_LIMITATIONS；主对话实现并核实际VectorBT结果。子代理只读勘查后停止，无运行交付。实际新批为 artifacts/vectorbt-ten-factor-ten-year-20260914-main/，报告 report.md、comparison.json、manifest.json、benchmark.py；前条目标路径被此路径替代。

2015-01-05至2024-12-31共2431交易日，2014仅预热；按代码顺序选择十年完整有效的30只股票，10因子取原清单纯OHLCV前10项、全部ACCDIST家族，复用原compiler/NumPy和原方向；每因子119次信号，2015首月现金。总12180成交，10/10逐笔及逐日持仓/现金/净值一致，最大金额差4.37e-10。十因子整批热中位fp 1.6495秒、完整VectorBT适配路径25.5187秒（耗时15.47倍）；新进程首次整批含导入/标准输入加载分别1.7660/28.1145秒。公共原始装载4.0461秒、因子和权重计算0.5419秒单列，不重复计入账户。

这是固定工程面板、原始未复权日线、无公司行为/涨跌停价表/完整历史资格门的共同子集比较，有可用性与幸存偏差，不是完整正式十年盈利研究。印花税按历史切换、过户费/滑点零的限制披露；不支持全池/分钟或VectorBT内核速度外推。T3全量与研究晋级不因本批放行，正式公共代码未改、原始数据未改、2025+未读取数值。无需继续重复本批计时。

### 2026-09-15 全面改用 Qlib（最新用户指令）

用户明确要求“完全用qlib，不要管自研了”。本主线停止推进自研因子/回测引擎和
VectorBT适配器，改为 `qlib_research/` 独立入口；原始数据与旧工件保留。
执行者为本对话 Codex，独占 `qlib_research/` 与 `artifacts/qlib-native-*-20260915-*`。
其他任务的在飞旧测试不由本对话擅自终止；以后本入口不调用旧计算模块。

执行 RUNNING，审核 PENDING。Qlib 0.9.7 已安装在
`D:/AI/workspace/qlib-env-20260915`，pandas固定在2.x兼容范围。直接使用Qlib原生
表达式、`calc_ic`、`TopkDropoutStrategy`、`SimulatorExecutor`；不套壳旧因子或成交结果。

原 `-16/hypotheses-trial20.jsonl` 的20个候选、5552证券静态超集和2020–2022训练窗
作为迁移试验输入，2018–2019仅为预热。数据接入保留公告可见时间、459日陈旧上限、
历史上市/ST/停牌/流动性资格；采用Qlib原生float32及缺失窗口语义，同日冲突公告字段
置缺失，不承诺旧结果逐位复现。旧bootstrap晋级门禁未迁移，本轮只报告描述性IC。

已实测：7项输入/RankIC检查通过；原生账户合成测试
`artifacts/qlib-native-account-smoke-20260915-3/` 完成63会话、5个交易和扣费日，
运行时旧引擎导入列表为空。真实20候选批次
`artifacts/qlib-native-trial20-20260915-3/` 正在转换数据，尚无计算结果。
早期 `-1` 因空公告文件退出，`-2` 为修复Qlib存储初始化而主动中止，保留残留工件。
全量2000未恢复；2025+及生产冻结不变。下一步完成原生20候选计算并记录耗时/数值/限制。

### 2026-09-15 Qlib原生20候选已完成（覆盖上一条试验进度）

**本次迁移试验执行 DONE；整体T3研究未完成，未作整体最终验收。**
默认研究方向已改为Qlib，根AGENTS已记录，不再推进自研计算/回测和VectorBT适配器。

最终评估批次 `artifacts/qlib-native-trial20-20260915-5/`，
数据provider在 `artifacts/qlib-native-trial20-20260915-4/provider/`，显式复用且保留旧尝试。
报告：[Qlib原生20候选试验](../../artifacts/qlib-native-trial20-20260915-5/report.md)。
实际命令：`D:/AI/workspace/qlib-env-20260915/Scripts/python.exe -m qlib_research.run --batch artifacts/qlib-native-trial20-20260915-5`。

- 原20个候选，2020–2022训练，2018–2019预热。5552证券静态超集，5002只有区间价格，
  550只因训练/预热区间无价格排除，逐只原因留档。未用旧引擎输出代替原始输入。
- 20/20完成，全部35有效月；最后2022-12信号月无成熟标签而排除。Qlib原生因子及标签
  求值、`calc_ic`统计均已实际运行，旧引擎导入列表为空。
- 首次数据转换4进程544.62秒；Qlib读取/因子/标签及OHLC检查2进程314.48秒；
  IC/RankIC、SciPy交叉检查及导出1.33秒；含源文件复核的评估计时段375.2秒。
  不包含环境安装、编码和失败尝试；与旧31分钟完整流水线不同口径，不宣称同口径加速倍数。
- 7项输入/RankIC检查通过；每候选首个有效月与SciPy核对差0（非独立算法实现声明）。
  17267源文件收尾核对无变化；Qlib二进制输入另保存计算后摘要快照，不冒充启动前后双核。
- 原生账户合成测试63会话、5交易/扣费日完成。尚未跑这20候选的真实账户，正式月频、
  公司行为和分钟执行规则尚未迁移验证；旧bootstrap门禁未迁移，不能据本次IC宣布晋级。

最终代码入口 `qlib_research/`。`run.ps1 -BatchName <新批次> -DataBatch <已完成数据批次>`
可复用数据并拒绝覆盖旧结果；默认新建数据也可用同一入口。版本、源码及工件摘要随报告保存。
试验中的空文件、Qlib初始化/基准、负号表达式问题已修复；串行导入改为4进程。
后续继续Qlib路线；全量2000仍未恢复，2025+及生产冻结保持。正式策略迁移状态仍待后续工作。

### 2026-09-15 Qlib 原生 L0 全量完成（2000 构造，最新用户授权）

用户指令“完成 T3 的 L0，当前 qlib 已经算好了 2000 因子，继续”，解除对本批 2000 构造
L0 的既往取消；本阶段只做 Qlib 原生 L0 信号筛选，不进入 L1/L2、不放开 2025+ 与生产。
**执行侧自审完成并给出工件与数值；整体 T3 未完成，未作最终验收，独立复核见配对审核任务书。**

最终批次 artifacts/qlib-native-l0-20260915-6c/（替代中间缺陷批 -6b，-6b 保留作 Corr 崩溃缺陷证据）。
因子表达式取自 artifacts/qlib-native-trial2000-20260915-15/result.json（2000 条 qlib_expression），
方向取自 artifacts/new-factor-research-20260912-16/hypotheses.jsonl；provider 为
artifacts/qlib-native-trial2000-20260915-6b/provider（5002 股，2018–2022 日频）。训练/评估窗
2020-01-01–2022-12-31，35 个成熟 IC 月。引擎为 Qlib 0.9.7，原生表达式、calc_ic、月块 bootstrap；
未导入旧引擎、VectorBT 或 quant。

实际命令（分片加 --shard s --nshards 4）：

    python -m qlib_research.l0_2000 \
      --provider artifacts/qlib-native-trial2000-20260915-6b/provider \
      --source artifacts/qlib-native-trial2000-20260915-15/result.json \
      --out artifacts/qlib-native-l0-20260915-6c --finalize --nshards 4

门禁沿用冻结 R0 口径（l0-config.json）：|月均 RankIC|>=0.02；有效月>=24；月块 bootstrap
(块3,B=10000,种子20260909) Bonferroni 尾 alpha_total=0.10/(2x2000)=2.5e-05；方向须与经济先验一致。
四项全过才 L0_PASS。此为 Qlib 原生口径，不宣称与旧引擎逐位复现。

结果计数（selection.csv 2000 行、2000 唯一 id；summary.json/report.md 一致）：

| 状态 | 数量 |
|---|---|
| L0_PASS | 109 |
| L0_REJECTED | 1312 |
| P5_STAT_INSUFFICIENT | 575 |
| BLOCKED_MISSING_FIELD | 4 |

monthly-rankic.csv 70000 行 = 2000x35。PASS 抽验：有效月全 35、min_pairs 最小 1081、方向违规 0、
CI 含零 0、|月均 RankIC| 落在 [0.0232, 0.0991]；示例 T3-CANDLE-CD08-w040(-0.0951)、
CE_vwap_tilt_20(-0.0826)、STATE_risk_limfreq(-0.0764)、T3-CORR-CB10-w020x060(+0.0441)。

本批关键修复（provider 侧缺陷，非策略失败）：-6b 的 83 个阻断全部是含 Corr 的表达式。根因是
Qlib Corr._load_internal 在掩码 rolling 时，若某股票某字段 bin 文件不存在会拿到空序列，触发广播
ValueError，使整条表达式加载失败并被登记为阻断。修复：

1. install_corr_guard() 仅在原实现抛 ValueError 时回退（空序列→该股返回空；长度不等→reindex），
   正常路径结果不变；qlib.init 后调用。
2. global_missing_fields() 扫描 provider，识别所有证券都无 bin 的真缺字段（fail-closed）；实测 5 个：
   adv_dec_ratio、limit_up_count、ev_ht_net_ratio_250、ev_ht_net_vol_250、ev_sf_past_ratio_250。
   引用真缺字段的表达式直接阻断，其余整批加载、失败则逐条回退登记。

处置：-6c 从 -6b/checkpoint 复制，把 83 个阻断从 done 剔除重排、清空 loaderr，用修复后代码重算
再 --finalize。恢复 79 个（72 个落 P5_STAT_INSUFFICIENT、7 个落 L0_REJECTED）；L0_PASS 仍 109
且身份证与 -6b 完全相同（identical=True）；未阻断身份证逐行比对 -6b vs -6c 为 0 差异，证明复用
正确、修复无副作用。

剩余 4 个真阻断（INFO_attention_breadth、INFO_breadth_shock_response、LL_limitup_lag_absorb、
TURN_spec_heat_beta_60），reason 均为 source_field_unavailable，因 provider 缺市场宽度/涨停家数
2 个市场级字段（adv_dec_ratio、limit_up_count，转换阶段未落盘）。这是真实数据缺口，与 ev_* 三个
字段同属 provider 无 bin；如实登记为阻断，属后续可选补数，不阻断 L0 广度目标（2000 已满足）。

未做：L1 成本筛选、L2 分钟回测、十年主/压力路径、统计显著性与晋级裁决均未启动；
statistical_validity=UNKNOWN、promotion_gate=BLOCK 不变。本阶段为执行侧自审，不代替独立复核与最终验收。

### 2026-09-15 L0 缺陷处置与缓存化（唯一当前状态）

用户指出旧 109 项已知有问题且不接受每次筛选都重新运行数小时。复核确认旧
`qlib-native-l0-20260915-6c` **整体失效，不得作为 L1 或组合输入**：

1. `prepare2000.py` / 后续 repair 使用降序日期轴写入，非价格派生字段发生时间镜像；财报/事件字段另有日期键错位。修复 provider 已建于
   `artifacts/qlib-native-trial2000-20260915-16/provider`，但旧 L0 结果来自缺陷 provider。
2. 旧翻译把 105 个 `CS_RANK(x)` 错写为 Qlib `Rank(x,252)`；前者为同日横截面排名，后者为单股时序排名。旧结果中这 105 项虽无 L0_PASS，淘汰/数据不足结论同样无效。
3. 36 个含 `IF` 的公式被改写为“条件×真分支”，丢失假分支；6 个回购字段走了另一条展开表达式。按字段/公式并集计，2000 项中至少 1043 项受一种已知问题影响。旧 109 中 18 项直接依赖错位字段；其余读数也只保留为旧批描述，不能拼成新通过集合。
4. Qlib 原生滚动窗口与旧引擎全窗缺失语义不同；按 2026-09-15 用户选择，后续继续采用 Qlib 原生语义，但必须登记为新计算身份，不宣称旧公式逐位复现。`CS_RANK` 不能用 Qlib 时序 Rank 代替，须走 Qlib `CSRankNorm` 分阶段处理。

性能与实现处置：

- 新增 `qlib_research/rescreen.py`：只读有效 `monthly-rankic.parquet` 重做门槛。对旧批作算法等价验证，2000 行状态/原因 0 差异，CI 最大差 `1.11e-16`；旧逐因子 bootstrap 实测 27.9 秒，新入口 1.26 秒。该验证只证明快速筛选算法等价，不恢复旧数据有效性。
- `l0_2000.py --cache-scores` 在一次性 Qlib 求值时同步保存 35 个成熟月末的可交易截面百分位秩与标签；20 股×2 因子冒烟得到 `700x2`、35 月、20 股。以后改门槛、去冗余和组合不再重算 Qlib 表达式。
- 新增 `qlib_research/combine.py`：经济方向统一后家族内等权、家族间等权；相关矩阵只披露，不按排名或聚类淘汰 L0 达标者。本输出仍是描述性组合信号，不替代 L1 成本账户。
- 翻译入口现保留 Qlib 原生三参 `If`、直接引用修复后的 PIT 回购字段，并对 `CS_RANK` fail-closed。`--translate-only` 实测 2000 项中 READY 1895 / BLOCKED_UNSUPPORTED_CSRANK 105，不再静默生成错误时序因子。
- 定向测试 `python -m unittest qlib_research.test_inputs qlib_research.test_rescreen qlib_research.test_combine qlib_research.test_translation -v`：13/13 通过；源码编译通过；旧公式源 20 项启动负例在读取市场数据前 rc=1。未启动新的全量数小时运行。

下一步：完成 105 个 `CS_RANK` 候选的 Qlib `CSRankNorm` 分阶段入口并冻结新公式/provider/缓存身份；随后只对失效或缺失候选做一次增量 Qlib 求值并保存分数缓存，再用秒级筛选入口产生新的 L0 集合。旧 109 不用于组合；新集合产生前 L1/L2、统计结论及生产继续 BLOCK。

### 2026-09-16 L0 性能改造落地 + S4 基准（唯一当前状态）

按 `docs/plans/qlib-l0-optimization-plan-20260915.md` 完成 L0 运行器改造，代码全部在
`qlib_research/`，不改 Qlib 源码：`provider_index.py`（provider 索引+manifest 校验+缺字段
分类+bin/元数据缓存+`H["f"]` 无上限进程 memo 旁路——后者即历史页面文件耗尽的隐形来源，
纯缓存旁路不改数值）；`l0_2000.py`（run-identity 身份冻结与拒绝恢复、每批原子
checkpoint=score+rankic+done 标记、心跳/RSS/批次记录、`--workers` 监督模式带重启一次与
内存守护 20% 物理内存、分层门禁：便宜检查先行、bootstrap 参数不变）；`l0_monitor.py`
（进度/资源/performance-report）。测试 32/32 通过（fixture provider：单元/数值等价/
故障恢复/监督者/监控器），全仓旧测试 13 项不受影响。

v2 冻结公式源已建：`artifacts/qlib-native-trial2000-20260916-1/result.json`
（source_type=qlib_translation_v2，READY 1895 / BLOCKED_UNSUPPORTED_CSRANK 105，
CS_RANK 不再误译为时序 Rank）。旧 16 进程批次仅历史证据，未复用其任何结果。

S4 基准（500 只/块×100 因子×2 worker，批 25，带 score 缓存，
`artifacts/qlib-native-l0-bench-s4-20260916-1`）：墙钟 802s，91 个可计算候选全部终态
（L0_PASS 6 / L0_REJECTED 81 / BLOCKED_MISSING_FIELD 3（adv_dec_ratio、limit_up_count 真
缺字段）/ BLOCKED_EXPRESSION_ERROR 1（BETA_panic_turnover，fail-closed 隔离））+
105 CS_RANK 阻断计入汇总；单 worker 峰值 RSS 444.7MB（远低于 3.2GB 守护线），页面文件
全程 4.5% 无增长；缓存生效：bin 命中 471 万次 vs 实读 22.9 万次，stat 免除 486 万次，
glob 每进程仅 1 次。热态成本 9.2–10.6 s/因子（读取占 >99%，瓶颈是 Qlib 逐表达式求值）。
外推 1895 因子全量：2 worker≈237min、4 worker≈121min、6 worker≈82min——按计划 §6 的
S5 门槛（≤45min 估算）均不达标，现状启动正式全量将构成 PERFORMANCE_BLOCKED，除非先做
阶段 3 公共子表达式复用（目标 ≥2x）或接受计划外并发。

用户指令（2026-09-16）：正式 L0 全量不启动，等待解冻；S4 仅为基准证据。statistical_validity
=UNKNOWN、promotion_gate=BLOCK 不变；L1/L2 未启动。
