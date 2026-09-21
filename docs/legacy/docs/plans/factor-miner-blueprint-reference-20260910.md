# Flash模型大额度因子挖掘执行方案

Flash 模型大额度
量化因子挖掘执行方案

目标：把大量便宜模型调用，转化为可审计、可复现、受约束的因子研究流水线

适用市场：A股
重点频率：日频 / T+1～T+10 短线
首轮矿区：残差均值回归、反转、相对强弱、事件、资金、状态交互
交易成本基线：17 bps round-trip，并做 27 / 37 bps 压力测试
版本：V1.0

# 一、执行摘要

本方案的核心不是让 Flash 模型“自由发挥想因子”，而是把模型限制在一个程序化研究框架中：模型负责提出具有经济含义的结构性假设，程序负责解析、计算、回测、统计门禁和样本外验证。这样可以利用模型的大额度与高并发，同时尽量降低幻觉、重复因子、数据窥探和参数过拟合。

> 一句话架构
> Flash 负责“提出结构”，代码负责“证明或证伪”；强模型只审核最后少量通过统计门禁的候选因子。

## 1.1 第一阶段目标

- 生成 200～300 个结构不同、可编译、可解释的候选 hypothesis，而不是几千个参数微调变体。

- 从 6 个核心矿区并行研究，先覆盖宽度，再按证据把预算集中到出现矿脉的家族。

- 每个候选统一测试 T+1 / 2 / 3 / 5 / 10、IC / RankIC、分层单调性、17bps 后净收益、成本压力、年度稳定性和样本外。

- 最终把候选压缩到约 5～20 个值得强模型复核与二次研究的信号。

## 1.2 六个首轮矿区

| 矿区 | 典型方向 | 为什么优先 |
| --- | --- | --- |
| 残差均值回归 | 行业/市场残差、Z-score、half-life、回归确认 | 与你当前“偏离基准后回归”策略直接相关 |
| 短期反转×成交结构 | 反转、异常换手、量价衰竭 | A股短线常见，且容易与成交状态交互 |
| 行业相对强弱 | 个股-行业、龙头/跟随、行业内部排名 | 降低市场/行业共同波动污染 |
| 业绩预告/快报 surprise | 增速变化、上修、公告后价格反应 | 信息事件具有明确时点和经济机制 |
| 龙虎榜/融资融券异常 | 净买入占比、融资变化Z-score、席位共振 | 资金行为与短线情绪直接相关 |
| 市场状态交互 | 牛熊、波动、流动性、情绪状态 | 很多信号只在特定 regime 下有效 |

# 二、系统总架构

> [Flash Researcher Pool]
>    ├─ MR researcher
>    ├─ Reversal researcher
>    ├─ Event researcher
>    ├─ Flow researcher
>    ├─ Regime researcher
>    └─ Cross-sectional researcher
>            │
>            ▼
>  hypothesis_pool.jsonl
>            │
>            ▼
>  [Schema Validator] ──> reject_invalid.jsonl
>            │
>            ▼
>  [Dedup / Cluster / Similarity Gate]
>            │
>            ▼
>  [Factor Compiler]
>            │
>            ▼
>  [Vectorized Factor Engine]
>            │
>      ┌─────┴─────┐
>      ▼           ▼
>   IC tests   Portfolio tests
>      │           │
>      └─────┬─────┘
>            ▼
>  [Cost / Turnover / Decay / Stability]
>            │
>            ▼
>  [Statistical Gate]
>      ┌─────┴─────┐
>      ▼           ▼
>    DEAD        PASS
>      │           │
>  Flash diagnosis │
>      │            ▼
>  next hypotheses  Validation / Lockbox
>                   │
>                   ▼
>              Final candidates

## 2.1 核心职责分离

| 角色 | 允许做 | 禁止做 |
| --- | --- | --- |
| Flash Researcher | 提出假设、经济解释、选择数据字段、建议持有期 | 直接宣布因子有效；编造回测结果 |
| Schema Validator | 检查字段、算子、方向、时点、必填项 | 进行语义优化 |
| Factor Compiler | 把受限表达式编译为计算图/代码 | 自动修改研究假设 |
| Backtest Engine | 统一计算与回测 | 挑最优参数后只报最好结果 |
| Statistical Gate | 按固定规则 PASS / REJECT | 根据“好不好看”人工放宽门槛 |
| Strong Reviewer | 审核最后少量通过者、找前视/伪逻辑 | 替代样本外验证 |

# 三、因子 Schema：用程序约束模型

建议不要允许 Flash 输出任意 Python。模型只能使用事先注册的数据字段、时间序列算子、横截面算子和条件算子，并输出固定 Schema。这样可以把“提示词约束”升级成“结构化合同”。

## 3.1 允许的数据字段（第一版）

> PRICE: open, high, low, close, pre_close
> VOLUME: volume, amount, turnover_rate
> CROSS_SECTION: market_cap, circ_market_cap
> BENCHMARK: market_ret, industry_ret_l1, industry_ret_l2
> FLOW: margin_balance, margin_buy, margin_sell, lhb_net_buy, inst_net_buy
> EVENT: forecast_profit_growth, express_profit_growth, event_type
> STATE: market_vol, industry_vol, adv_dec_ratio, limit_up_count

## 3.2 允许的算子（第一版）

> RET(x,n)          # n期收益
> MEAN(x,n)         # 滚动均值
> STD(x,n)          # 滚动标准差
> MAX(x,n) / MIN(x,n)
> DELTA(x,n)
> ZSCORE(x,n)
> TS_RANK(x,n)
> CS_RANK(x)
> IND_NEUTRAL(x)
> SIZE_NEUTRAL(x)
> ABS(x), LOG(x), SIGN(x)
> IF(condition, a, b)
> +, -, *, /

## 3.3 建议的 hypothesis JSON Schema

> {
>   "id": "auto_uuid",
>   "name": "industry_residual_momentum_20",
>   "family": "momentum_residual",
>   "hypothesis": "剔除行业涨跌后，个股特异性趋势可能短期延续",
>   "formula": "RET(close,20)-RET(industry_ret_l1,20)",
>   "required_fields": ["close","industry_ret_l1"],
>   "expected_direction": "positive",
>   "holding_days": [3,5,10],
>   "economic_mechanism": "firm_specific_information_diffusion",
>   "known_failure_modes": ["industry_regime_shift","microcap_illiquidity"],
>   "novelty_note": "不同于裸20日动量，剔除行业共同成分",
>   "generation_round": 1,
>   "parent_factor_ids": []
> }

## 3.4 强制校验规则

- formula 中只能出现注册字段与白名单算子。

- 禁止未来字段、未来收益、未来公告状态进入特征。

- 同一 hypothesis 必须说明 economic_mechanism，禁止只写“可能有效”。

- 禁止仅通过 7/8/9/10/11 日窗口之类微调制造“新因子”。

- required_fields 必须与 formula 可静态推导一致。

- 若使用公告/财务数据，必须声明可用时点字段（ann_date / actual_date 等）。

# 四、Flash Agent 分工与并行研究

建议把大额度用于“研究方向的并行化”，而不是同一个提示词开几十个副本。第一版可开 12～16 个 researcher，每个只负责一个明确矿区。

| Agent | 研究边界 | 每轮预算 |
| --- | --- | --- |
| MR-1 | 行业残差均值回归 | 15 hypothesis |
| MR-2 | 稳定标的筛选/half-life/结构断裂 | 15 |
| REV-1 | 1～5日反转×换手 | 15 |
| REV-2 | 隔夜/日内拆分、跳空恢复 | 15 |
| REL-1 | 行业相对强弱/行业内排名 | 15 |
| EVT-1 | 业绩预告 surprise | 15 |
| EVT-2 | 快报/正式财报后的价格反应 | 15 |
| FLOW-1 | 龙虎榜净买入/席位结构 | 15 |
| FLOW-2 | 融资融券变化/背离 | 15 |
| STATE-1 | 市场波动/情绪 regime | 15 |
| STATE-2 | 行业状态交互 | 15 |
| META-1 | 跨家族低相关交互 | 10 |

> 首轮总量
> 12 个 Agent × 10～15 个候选 ≈ 150～180；补充第二轮即可达到约 200～300 个“结构性候选”。

# 五、Researcher 任务合同

Flash researcher 每轮应接受固定任务书。重点是让模型在“经济机制”和“结构差异”上创新，而不是在窗口参数上搜索。

> 你是因子研究员。
> 目标：在指定因子家族中提出最多 15 个结构不同的 hypothesis。
> 
> 硬约束：
> 1. 只能使用给定字段和算子。
> 2. 禁止输出 Python；只输出符合 Schema 的 JSONL。
> 3. 禁止仅靠窗口微调生成不同因子。
> 4. 每个因子必须有可证伪的经济机制。
> 5. 明确 expected_direction 与 holding_days。
> 6. 明确至少一个 known_failure_mode。
> 7. 若与已有因子高度相似，必须说明增量机制，否则不提交。
> 8. 不允许根据任何 LOCKBOX 结果提出假设。
> 
> 优先寻找：
> - 残差化
> - 变化率/加速度
> - 相对关系
> - 条件状态
> - 有理论依据的交互
> 
> 禁止：
> - “为了提高收益把20日改成17日”
> - 无机制的任意四则运算
> - 未来数据
> - 直接判断因子PASS

# 六、数据分区：防止模型额度越多，过拟合越严重

> 关键风险
> 模型调用次数越多，相当于隐形进行了更多假设检验。如果每一轮都能看到完整历史结果，几乎必然会“挖”出漂亮但假的策略。

## 6.1 三层数据保险箱

| 区域 | 用途 | Flash 是否可见 |
| --- | --- | --- |
| TRAIN | 生成、诊断、第一轮迭代 | 可见 |
| VALIDATION | 家族级筛选、减少错误方向 | 仅中后期可见 |
| LOCKBOX | 最终一次性验收 | 研究期间不可见 |

如果可用历史较长，可按“前段训练 / 中段验证 / 最近 2～3 年锁箱”划分。若数据较短，则使用 Walk-forward + 最后一段完全锁箱。具体年份应根据各数据源的可用历史统一后再定。

## 6.2 结果访问权限

- Researcher 默认只看到 TRAIN 聚合统计，不看逐日净值曲线和锁箱。

- Diagnosis Agent 可以看失败类别，但不能看所有参数组合排名。

- Strong Reviewer 只在候选通过 VALIDATION 后进入。

- LOCKBOX 只能在研究冻结（factor freeze）后运行一次；若失败，不允许继续针对锁箱调参。

# 七、统一回测与统计门禁

## 7.1 每个候选必须统一计算

| 维度 | 必须输出 |
| --- | --- |
| 预测期限 | T+1 / T+2 / T+3 / T+5 / T+10 |
| 截面有效性 | IC、RankIC、ICIR、分层单调性 |
| 组合收益 | Top/Bottom 分组、long-only 或 long-short 视约束 |
| 交易性 | 换手率、成交额过滤、不可交易事件 |
| 成本 | 17 bps 基准；27 / 37 bps 压力 |
| 稳定性 | 分年度、分行业、分市值、分市场状态 |
| 尾部风险 | 最大回撤、最差事件、MAE/MFE |
| 样本外 | VALIDATION / LOCKBOX |

## 7.2 第一版门禁逻辑（建议）

> PASS_FAMILY_CANDIDATE if:
>   sample_size >= min_sample
>   AND direction_consistent == true
>   AND not_single_year_dominated == true
>   AND not_single_stock_dominated == true
>   AND validation_not_inverted == true
>   AND cost_17bps_net_edge > 0
>   AND stress_27bps_not_catastrophic == true
> 
> NOTE:
>   这里不要先写死“IC必须>0.03”等绝对阈值。
>   不同持有期、事件型与连续型因子的统计分布不同。
>   第一版先以一致性、成本后正边际和样本外不翻转为核心。

## 7.3 家族级判定

禁止“一个 MOM10 死了 = 动量家族死了”。每个家族应预注册 5～10 个经济机制不同的代表构造；只有代表构造普遍失败，才降低该家族预算。反过来，也禁止因为一个极端赢家就宣布整个家族成立。

# 八、研究预算机制：把额度投向“矿脉”

| Round | 规则 | 预算变化 |
| --- | --- | --- |
| R0 探矿 | 每家族 10～20 个结构候选 | 平均分配 |
| R1 诊断 | 看 TRAIN 的失败类别与相关性 | 无增量家族减半 |
| R2 扩矿 | 多种构造呈一致微弱信号 | 预算 ×2～3 |
| R3 Validation | 只保留低相关、机制可解释候选 | 大幅收缩 |
| R4 Strong Review | 强模型检查数据时点、伪相关、实现风险 | 仅 5～20 个 |
| R5 Lockbox | 冻结后一次性最终测试 | 不再调参 |

## 8.1 建议的“死亡原因标签”

> NO_SIGNAL             # 无IC/无分层
> WRONG_DIRECTION       # 方向系统性相反
> HORIZON_MISMATCH      # 只在别的持有期出现
> COST_KILLED           # 毛边际有，成本后死
> REGIME_ONLY           # 仅特定市场状态有效
> INDUSTRY_EXPOSURE     # 只是行业beta
> OUTLIER_DRIVEN        # 少数事件贡献
> YEAR_DOMINATED        # 单一年份贡献
> STOCK_DOMINATED       # 少数股票贡献
> VALIDATION_FLIP       # 验证集翻转
> DATA_QUALITY_RISK     # 数据/时点不可信
> IMPLEMENTATION_RISK   # 不可成交/容量不足

# 九、工程目录建议

> factor_miner/
> ├─ config/
> │  ├─ fields.yaml
> │  ├─ operators.yaml
> │  ├─ cost_model.yaml
> │  └─ split.yaml
> ├─ schemas/
> │  └─ factor_hypothesis.schema.json
> ├─ prompts/
> │  ├─ researcher.md
> │  ├─ diagnosis.md
> │  └─ reviewer.md
> ├─ hypotheses/
> │  ├─ round_00.jsonl
> │  ├─ round_01.jsonl
> │  └─ rejected.jsonl
> ├─ engine/
> │  ├─ validator.py
> │  ├─ compiler.py
> │  ├─ operators.py
> │  ├─ factor_calc.py
> │  ├─ backtest.py
> │  └─ gates.py
> ├─ data/
> │  ├─ raw/
> │  ├─ normalized/
> │  └─ point_in_time/
> ├─ results/
> │  ├─ train/
> │  ├─ validation/
> │  └─ lockbox/
> ├─ registry/
> │  ├─ factor_registry.parquet
> │  ├─ lineage.parquet
> │  └─ family_budget.parquet
> └─ reports/
>    ├─ family_summary/
>    └─ final_review/

## 9.1 因子注册表最低字段

| 字段 | 说明 |
| --- | --- |
| factor_id | 唯一ID |
| name | 因子名 |
| family | 家族 |
| formula_hash | 公式指纹 |
| parent_ids | 父因子/来源 |
| generation_round | 生成轮次 |
| status | NEW / TESTED / DEAD / PASS / FROZEN |
| death_reason | 失败原因 |
| corr_cluster | 相关性簇 |
| train_metrics | 训练指标摘要 |
| validation_metrics | 验证指标摘要 |
| lockbox_metrics | 锁箱指标摘要 |
| prompt_version | 生成时任务书版本 |
| data_version | 数据快照版本 |

# 十、第一阶段落地：建议 7 个步骤

1. 冻结字段表和算子表：先只允许价格、成交、行业、龙虎榜、两融、业绩事件这几类数据。

1. 实现 factor_hypothesis.schema.json 与 validator：任何不符合合同的模型输出直接拒绝。

1. 实现 10～20 个基础算子，并为每个算子写单元测试；确认窗口、缺失值、复权和时点逻辑。

1. 跑 R0：12 个 Flash Researcher，各生成 10～15 个结构候选；去重后控制在 150～200 个。

1. 统一回测 TRAIN；写死结果字段与成本口径，自动生成 death_reason。

1. 把失败摘要而不是全量结果交给 Diagnosis Agent；每家族最多提出 3～5 个下一代机制候选。

1. 进入 VALIDATION 后冻结大部分候选，只让通过者进入强模型审核，最后再锁箱一次。

## 10.1 第一轮不要做的事

- 不要让 Flash 直接写数百行策略 Python 并自测。

- 不要一次生成上万公式。

- 不要允许模型看到 LOCKBOX。

- 不要因为一个候选亏钱就让它“改到赚钱为止”。

- 不要把 7 / 8 / 9 / 10 / 11 日窗口当成五个新因子。

- 不要只保存最终赢家；必须保留失败因子与 lineage，避免反复重新发明同一个垃圾因子。

# 十一、在多 Agent / Hermes 场景中的调度建议

你可以把 Hermes 作为 Director，但 Director 不参与因子数学判断。它只负责调度、收集 JSONL、调用测试程序、读取统计结果、更新研究预算。这样即使 Flash 模型“很能说”，也无法绕过程序门禁。

> Director loop:
>   1. read family_budget
>   2. dispatch researcher jobs
>   3. collect hypothesis JSONL
>   4. run schema validator
>   5. run dedup / similarity clustering
>   6. compile factors
>   7. execute TRAIN tests
>   8. assign death_reason automatically
>   9. dispatch diagnosis only for eligible families
>  10. update family_budget
>  11. when frozen -> VALIDATION
>  12. final shortlist -> strong reviewer
>  13. freeze all -> LOCKBOX once

## 11.1 任务状态建议

> DRAFT -> VALIDATED_SCHEMA -> COMPILED -> TRAIN_TESTED
>       -> DEAD
>       -> FAMILY_CANDIDATE -> VALIDATION_TESTED
>       -> REJECTED
>       -> REVIEW_CANDIDATE -> FROZEN -> LOCKBOX_TESTED

# 十二、成功标准

这个项目的成功，不是“挖出一个年化100%的神因子”。更合理的第一阶段成功标准是：

- 因子生成、校验、编译、回测、判死全自动化，模型无法跳过结构化合同。

- 200～300 个候选中，能明确区分重复、无信号、成本杀死、状态限定、样本外翻转等失败类型。

- 能够发现少量跨年份、跨股票、扣成本后仍有边际的候选或家族。

- 因子 registry 与 lineage 完整，可追溯“谁生成、依据什么、在哪一轮死、为什么死”。

- 即使最终没有强 alpha，也能把“哪些矿区不值得继续烧额度”转化为可复用研究资产。

# 十三、交给执行 Agent 的验收清单

| 验收项 | 通过条件 |
| --- | --- |
| Schema | 100% 候选均可校验；非法字段/算子自动拒绝 |
| 时点 | 公告/财务/行业历史无前视 |
| 重复控制 | 公式哈希 + 相关性聚类可识别同质因子 |
| 成本 | 17 / 27 / 37 bps 三档固定输出 |
| 样本外 | TRAIN / VALIDATION / LOCKBOX 完全分离 |
| 结果完整性 | 失败项也落库，不只保存赢家 |
| 可复现 | 相同 data_version + prompt_version + code commit 可复跑 |
| 研究预算 | 预算自动按 family evidence 调整 |
| 锁箱纪律 | 冻结前不可访问 LOCKBOX；冻结后最多一次正式运行 |

# 十四、建议首轮预注册因子家族

| 家族 | 代表构造（不是参数穷举） |
| --- | --- |
| Residual MR | 行业残差Z-score、鲁棒Z-score、回归确认、half-life筛选 |
| Reversal | 1日反转、3日反转、异常换手反转、隔夜/日内反转 |
| Relative Strength | 个股-行业、行业内rank、龙头-跟随、行业残差动量 |
| Volume/Liquidity | 换手Z-score、成交额异常、量价相关、Amihud类 |
| Event Surprise | 业绩预告变化、上修、公告后弱反应、漂移 |
| LHB/Flow | 龙虎榜净买入占比、机构净买入、融资变化、价格-融资背离 |
| Regime Interaction | 高波/低波、风险偏好、行业强弱、流动性状态 |

# 十五、结论

Flash 大额度真正的价值，不是让模型替你“算”量化，而是让它以低成本并行探索大量有经济含义的假设空间。只要把研究过程锁进 Schema、固定样本分区、统一成本、自动统计门禁和 lineage 追踪里，模型的优势会体现在“广度、交互关系发现、失败诊断和文献重组”上，而不是体现在自由调参。

> 推荐起点
> 先做 150～200 个候选的 R0，不要追求数量。等程序门禁稳定后，再把 Flash 额度扩大到多轮研究。研究框架先正确，额度才会真正变成资产。

# 附录 A：第一轮默认参数

| 项目 | 默认 |
| --- | --- |
| 预测期限 | T+1 / 2 / 3 / 5 / 10 |
| 成本 | 17 bps；压力 27 / 37 bps |
| 每个家族首轮候选 | 10～20 |
| 单个 Diagnosis 下一轮新增 | 最多 3～5 |
| 参数微调 | 禁止作为新 hypothesis |
| 强模型介入比例 | 最终约 1%～5% 候选 |
| Lockbox | 冻结后一次正式运行 |

# 附录 B：研究风险提示

本方案是研究工程设计，不构成证券投资建议。量化因子容易受到幸存者偏差、前视偏差、数据修订、样本选择、交易成本、不可成交、容量限制和制度变化影响。任何通过回测的候选，都应经过严格样本外、仿真和交易可行性验证。
