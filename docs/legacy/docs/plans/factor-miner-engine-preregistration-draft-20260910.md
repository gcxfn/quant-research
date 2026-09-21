# 统一因子挖掘引擎（factor-miner）预登记（2026-09-10）

状态：用户批准（2026-09-10 对话指示"都按你推进。反正把flash模型用起来"——框架采纳、数据切法、先引擎后放大三项均按主对话建议执行）。
蓝本：`docs/plans/factor-miner-blueprint-reference-20260910.md`（外部方案《Flash模型大额度因子挖掘执行方案》V1.0 存档副本）。
定位：把"每家族手写研究脚本+主对话人肉跨家族口径对齐"升级为"结构化假设合同+统一引擎"。**Flash 研究员只输出 hypothesis JSON，不写统计代码；全部统计由引擎按本预登记冻结协议计算。**
生效边界：R0 挖掘运行须待 ①引擎实现完成 ②主对话独立审查（含全仓测试）③Codex 运行前审核 PASS。引擎实现本身按本预登记直接派发。
与在途轮次关系：N=15 家族粗筛（②③④）、事件工件修复、statements 下载按各自已批预登记继续，不受影响；MR/事件/C 机制轮结论不重开。生产主线与 Gate 冻结不变。

## 1. 数据分区（冻结；用户批准的切法）

| 区间 | 日期 | 用途 | researcher 可见性 |
|---|---|---|---|
| TRAIN | 2020-01-01 → 2022-12-31 | 假设生成、诊断、第一轮迭代 | 仅本区聚合统计 |
| VALIDATION | 2023-01-01 → 2024-12-31 | 家族级筛选 | 不可见（中后期仅看通过者聚合） |
| LOCKBOX | 2025-01-01 → 2026-09-08 | 冻结后一次性验收 | 不可见 |

- **污染披露（冻结措辞，正式报告必须携带）**：2024-01-01→2026-09-08 已被 MR R1 C 阶段与事件家族阶段二以一次性样本外方式观察过（两轮结论均为负）。对新家族属于元层面知情而非因子层面泄漏；引擎不得因此放宽任何门禁。
- LOCKBOX 纪律：只有 `director --lockbox` 专用入口可读取该区；每次运行落档留痕；同一批冻结候选最多一次正式运行，失败不得针对锁箱调参。
- 时点纪律：一切特征只用决策日 t 收盘可得数据；公告表用 `ann_date ≤ t`（可知性）；执行 t+1 开盘（与事件家族/MR 冻结口径一致）；top_list/top_inst 上榜数据时点=上榜日+1。

## 2. 字段白名单 v1（映射到已有数据资产；未列字段禁用）

| 组 | 字段 | 来源 | 时点规则 |
|---|---|---|---|
| PRICE | open, high, low, close, preclose, volume, amount | P1 时点池日线（本地数据集+baostock 退市，mr_statarb 装载器） | t 日收盘可得 |
| VALUATION | turnover_rate, turnover_rate_f, volume_ratio, pe_ttm, pb, ps_ttm, dv_ttm, total_mv, circ_mv | daily_basic 20260909-r1 | trade_date=t 当日可得 |
| BENCH | industry_ret_l1 | sw_index_daily 20260909-r3（r4-verify 已对账） | t 日收盘可得 |
| BENCH | market_ret | 引擎内部派生：当日 P1 可交易池等权收益（冻结公式） | t 日收盘可得 |
| FLOW | margin_balance, margin_buy, margin_sell | margin_detail 20260909-r1 | t 日可得 |
| FLOW | lhb_net_buy, inst_net_buy | top_list/top_inst 20260909-r3 | 上榜日+1 |
| EVENT | forecast/express/repurchase/stk_holdertrade/share_float/dividend 的事件字段 | 各表已存批次 | ann_date ≤ t |
| STATE | market_vol（market_ret 20日std）, adv_dec_ratio（当日涨跌家数比）, limit_up_count（收盘=涨停家数） | 引擎内部派生（冻结公式） | t 日收盘可得 |

- **行业归属限制（硬规则）**：index_member_all 为快照、out_date 全空，历史行业 spells 有缺口。凡 formula 引入行业成员归属（行业中性化、行业内排名）的构造一律标记 `status=EXPLORATORY_ONLY`，**不得正式晋级**（validator 强制）。仅引用 industry_ret_l1（行业指数收益）不触发此限制。
- 数据版本：registry 记录 data_version=各来源批次目录 id 串联；换批次=新研究身份。

## 3. 算子白名单 v1

`RET(x,n)`, `MEAN(x,n)`, `STD(x,n)`, `MAX(x,n)`, `MIN(x,n)`, `SUM(x,n)`, `DELTA(x,n)`, `ZSCORE(x,n)`, `TS_RANK(x,n)`, `CS_RANK(x)`, `CORR(x,y,n)`, `ABS(x)`, `LOG(x)`, `SIGN(x)`, `IF(cond,a,b)`, 四则 `+ - * /`。
- 缺失值语义：NaN 传播不填充；滚动窗 min_periods=全窗（窗口不足→NaN，不得部分计算）。
- 时序算子只用 ≤t 数据（编译期静态保证，禁止负偏移/未来引用）。
- 白名单外算子/字段 → validator 拒收（reject_invalid.jsonl），无人工豁免通道。
- **事件型构造不走公式层**：以事件表+过滤条件声明表达，统计沿用事件家族冻结口径（见 §5）。

## 4. hypothesis JSON Schema（冻结字段）

```
id, name, family, hypothesis(经济机制一句话), formula, required_fields,
expected_direction(positive|negative), factor_type(event|continuous),
holding_days[], economic_mechanism, known_failure_modes[],
novelty_note, generation_round, parent_factor_ids[], prompt_version
```
强制校验（validator 实现，逐条单测）：
1. formula 只含白名单字段与算子；
2. formula 与 required_fields 静态推导一致；
3. 禁未来字段（对照字段注册表的时点元数据）；
4. economic_mechanism / expected_direction / known_failure_modes 必填非空；
5. **公式哈希去重**：窗口参数归一化后哈希（防 7/8/9/10/11 日微调伪装新因子）；同类构造不同窗口 → 合并为一个 hypothesis 的 holding_days 扫描，不另立 id；
6. 行业归属字段触发 EXPLORATORY_ONLY 标记。

## 5. 统计协议（整体沿用已冻结版本，不重新发明）

- **连续型（因子）**：月末截面 RankIC（因子值 vs 下月收益）；持有期衰减曲线 h∈{1,2,3,5,10,20} 日 IC（描述性）；月块 bootstrap（块长 3 个月、B=10000、种子 20260909）95%CI；Top-Bottom 十分位组合月频毛收益差（描述性）。
- **事件型**：事件=公告/上榜次日开盘入场（P1 完整门禁：ST/上市<252会话/20日中位成交额<5000万剔除；一字涨停开盘 no_trade）；h∈{3,5,10,20}；超额=可交易口径绝对收益 − 全 universe 等权同窗基准；事件日块 bootstrap（块长 20、B=10000、种子 20260909）95%CI。
- **成本**：17bps 基线（用户 20 万资金、单笔≥5 万、最低佣金不生效的推导口径）/27/37bps 压力，仅精测阶段应用。
- **A股现实**：T+1；方向性涨跌停统一复用 `quant/market.limit_price`；佣金/印花税口径沿用既有引擎。
- **门禁（两阶段，冻结）**：
  - 粗筛（TRAIN）：事件型 某 h∈{3,5,10,20} 毛超额均值≥34bps ∧ CI 下界>0；连续型 |RankIC 均值|≥0.02 ∧ CI 不含零 ∧ 方向=经济先验。
  - 家族候选（VALIDATION，全部满足）：①TRAIN/VALID 方向一致；②非单年主导（VALID 内分年同号占比≥2/3）；③非单股主导（贡献度 top1 股票占比<20%，公式冻结：该股票样本绝对贡献之和/全部样本绝对贡献之和）；④成本 17bps 净边际>0；⑤27bps 压力下净边际>0；⑥37bps 仅描述性披露。
  - LOCKBOX：冻结候选一次性验收，双侧端点 Bonferroni α=0.05/N_frozen。
- **多重检验**：每轮粗筛 α=0.10/N（N=该轮正式检验构造数）；**晋级≠有效，仅授权进入精测**。
- **死亡原因 12 标签**（引擎自动打，喂预算机制）：NO_SIGNAL / WRONG_DIRECTION / HORIZON_MISMATCH / COST_KILLED / REGIME_ONLY / INDUSTRY_EXPOSURE / OUTLIER_DRIVEN / YEAR_DOMINATED / STOCK_DOMINATED / VALIDATION_FLIP / DATA_QUALITY_RISK / IMPLEMENTATION_RISK。

## 6. 家族预算轮次

| 轮 | 规则 | 预算 |
|---|---|---|
| R0 探矿 | 每家族 10–20 个结构候选（**2026-09-10 用户授权两次修订：D-2026-09-10-28"让他们多挖一点…只要合理就去挖"→REV/REL≤60/STATE≤40/META≤20；D-2026-09-10-29"死掉的家族里面再挖点因子…最好几百个"→再扩容 REV≤120/REL≤90/STATE≤60/META≤120，并新增三个子矿区（family 记账归属不变）：FLOW_CONT（③资金流连续化：lhb_net_buy/inst_net_buy 时序聚合与 margin 深层结构，归 META；③事件型 R1 无晋级封存不重开，本子矿区为连续信息含量探矿；LHB 退市覆盖偏差须披露）、VAL_CONT（估值组 pe_ttm/pb/ps_ttm/dv_ttm/total_mv/circ_mv 连续构造与条件交互，归 META；与引擎外 F1/F4 粗筛晋级者的相关性由聚类层暴露披露）、RESID_REV（MR 残差信息内容的连续反转表达，归 REV；披露：MR R1 策略封存且其 2024+ 留出窗曾被一次性观察——本子矿区构造晋级后的一次性考试资格须在批考预登记中逐候选披露该家族级污染）。多研究员分工、单人 ≤15、公式哈希去重计数、α=0.10/N 自动收紧，其余协议零改动**） | 均分 |
| R1 诊断 | TRAIN 失败类别+相关性 | 无增量家族减半 |
| R2 扩矿 | 多构造一致微弱信号 | ×2–3 |
| R3 VALIDATION | 收缩至低相关可解释者 | 大幅收缩 |
| R4 Codex 强审 | 数据时点/伪相关/可实现性 | 仅 5–20 个 |
| R5 LOCKBOX | 冻结后一次 | 不再调参 |

- **R0 首轮矿区（新，均未测过）**：REV（短期反转×成交结构）、REL（相对强弱/残差动量）、STATE（市场状态交互）+ META（跨家族低相关交互，修订后 ≤20 个）。MR 家族（R1 C 阶段 FAIL 封存）与事件家族（R1 无晋级封存）非新机制不重开；③资金流家族在途（N=15 粗筛），结论并入家族档案。
- ⑤财务家族待 statements 下载完成+主对话抽审后以附录补充构造。
- 家族判级：某家族 ≥30% 代表构造在 TRAIN 出现同方向一致信号（无论是否过线）→ R2 可扩矿；普遍无信号 → 预算减半。禁单因子判死家族、禁单赢家判活家族。

## 7. 工程与工件

- 模块布局：`experiments/factor_miner/`（schema, validator, operators, compiler, data_fields, partition, engine, stats, backtest, registry, director）+ `experiments/factor_miner/prompts/researcher_v1.md`（任务书冻结版本）。
- 假设流：`hypotheses/round_NN/*.jsonl` + `rejected.jsonl`（失败也落库，禁只存赢家）。
- 工件：`artifacts/factor-miner/<round>/{train,validation,lockbox}/`，粗筛层即保存可复算明细（事件逐事件+事件日池+基准明细；因子逐月 IC 序列+截面抽样）。
- registry 最低字段：factor_id, name, family, formula_hash, parent_ids, generation_round, status(NEW/TESTED/DEAD/PASS/FROZEN/EXPLORATORY_ONLY), death_reason, corr_cluster, train/validation/lockbox_metrics, prompt_version, data_version, code_commit。
- 测试纪律：每算子窗口/NaN/时点单测；validator 每条规则的反例单测；partition 越区访问拒绝单测；零第三方依赖离线可跑；全仓回归保持绿。
- 验收清单（Codex 运行前审核覆盖）：Schema 100% 可校验、时点无前视、公式哈希+相关性聚类去重、17/27/37 固定输出、三区完全分离、失败项落库、可复现（data_version+prompt_version+code commit）、预算自动调整、锁箱纪律。

## 8. 分工

- Flash 子代理：引擎实现（本轮派发）、R0+ 假设生成（只产 JSONL）、诊断代理。
- 主对话：调度、收集、校验执行、跨家族抽审、打包送审；不担任数学审核（Codex 职责）。
- Codex：引擎运行前审核（重点=validator/compiler/partition 三处单点故障——引擎 bug 会同时污染所有家族）；R4 强审；LOCKBOX 结果复算。
- 用户：预登记批准、最终晋级批准。

## 9. 批准记录

- 2026-09-10 用户对话："都按你推进。反正把flash模型用起来"（三项：采纳蓝本为放大轮框架；数据切法 TRAIN 2020–2022 / VALIDATION 2023–2024 / LOCKBOX 2025–2026.09；先引擎后放大）。
