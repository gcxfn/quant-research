# 实验失败聚类与死区登记簿（2026-09-11）

- 作者：EX2 失败聚类代理（flash）。只读输入，零 git 命令，未运行任何评估管线。
- 输入（均已主对话验收，本次只读）：
  - `artifacts/experiment-index-20260911/experiments.jsonl`（EX1，109 行结构化实验索引）
  - `artifacts/evidence-graph-20260911/graph.jsonl`（EG，31 条 claim 血缘）
  - 上述两文件引用的原文档（docs/experiments、docs/plans、docs/decisions.md、configs/p4-factor-research.json、experiments/screen_pricevol.py 等）
  - `docs/experiments/r1-formula-gap-analysis-20260911.md` 与 `experiments/factor_miner/compiler.py`（formula_hash 定义）
- 产出：
  - 机器可读死区登记簿：`artifacts/experiment-index-20260911/dead_zones.jsonl`（20 条，本文 §2 为总览）
  - 本文（人类可读摘要）
- 聚类口径：按**失败机制**聚类（同一机制跨研究线重复出现才算一簇），不按 research_line/家族标签分组。verdict∈{FAIL, SEALED} 与 verdict=null 但裁决为失败/封存/搁置类的实验全部纳入聚类输入。

---

## 1. 失败机制聚类（8 簇）

### MC1 成本地板吞噬微弱毛收益

| 实验 | 证据摘录 |
|---|---|
| p4-revised-selection-conclusion | 48 格（12 候选×4 止损）全部 B2=False；F4 四档毛收益微正（+0.07059%@1.5% 止损）但约 0.20 个百分点成本全部吞没；F1 扣费前已亏 |
| p4-barrier-stream-result | 主检验 48 格全部 B2=False、pvalue=1.0；期望净收益为负；Gate A 过 7 项、同时过 A/B1 仅 3 项 |
| p4-lowvol-h10-conclusion | 10 会话毛 +0.06584% → 净 −0.13414%；53,574 配对改善 −0.00228514pp；延长持有未让毛收益积累过约 0.20pp 成本；胜率 35.61%→40.73% 但净均值未改善 |
| t0-minute-evidence | 完成轮合计 +6.9 万~+20.6 万 vs 强平轮 −42 万~−46 万；六组合年度净增益中位全非正（正T −68.31%、反T −70.72% 占名义），为正 0/6 |
| weekly-entry-research（佐证） | 冻结选出的 ETF 回撤企稳 2024 起转负、费用加倍全期也负 |
| short-target-research（佐证） | 费用及滑点加倍后年化 3.33%、夏普 0.854，仍未达标 |
| top15-cost-breakeven（描述性佐证） | k=15 时单笔名义 13,333 元触发最低佣金，双边 12.5bps、全换年化拖累 148.97bps |
| monthly-etf-t0-plan（产品层判决） | P3/P4 证据：真实成本结构下日线价量因子毛收益不覆盖成本 |

**簇级结论**：10 万元级资金、股票万 2.5 最低 5 元＋印花＋滑点的成本地板约 0.20pp/往返（ETF 万 1 约 12.5bps 双边）。任何毛收益量级不足成本地板约 2 倍的日线/日内信号（价量短线、低波延期、对称做T 档位）在此结构下都会死。**再试什么会再死**：同量级毛收益信号×换持有期/换止损档/换做T 档位的任意排列；扩大样本只会收窄同一负号区间。重开需要毛收益量级提升（月频降换手、更强信号源）或成本结构变化，二者均须重新预登记。

### MC2 事件/信号聚集×多重检验→显著性不达线

| 实验 | 证据摘录 |
|---|---|
| event-family-round1 | E1_bull h=10 超额毛均值 +0.69% 远超 34bps 线，但事件日块 bootstrap 95%CI 下界 −0.033%——差 3.3bp；解读：事件日聚集（同日多股公告）使有效样本量缩水 |
| family-screening-review-pack（②PE） | PE1-PE5 毛超额有正但 CI 下界全负；PE3 h=3 修复后 31.35bps 距 34bps 线差 2.65bps，临界不翻转 |
| mr-statarb-round1 | B 六格仅 m20_z05 过 99.1667%CI（下界 +0.000246）；阶段 C 净期望 +0.1076%、95%CI[−0.8338%,+1.2406%] 含零 |
| pv1-precision-prerun-review-pack-round7（在途，同签名警示） | in-window 净年化 +7.682%、CI[−0.8607%,+2.6450%] 含零——同一签名，统考未判，不预支结论 |

**簇级结论**：事件/信号在时间上聚集＋多重检验校正后，「点估计过线而 CI 下界差 1~3bp」是本机制的标准签名。**再试什么会再死**：同家族换参数窗、换事件类型、换持有期——有效样本量不因参数变化增加，CI 下界大概率仍在零附近。E1_bull/PE3 类临界格已被两轮原文明令禁止作为追加参数理由。

### MC3 幸存者/池构建偏差制造假阳性

| 实验 | 证据摘录 |
|---|---|
| short-foundation-research（P3 最终口径） | 旧池 +21.97% vs 严格池 −33.44%；匹配幸存者对照（同价格序列仅切掩码）掩码仅解释约 1.1pp——差距主要来自池构建/幸存者本身 |
| short-profit-research | momentum_market 全期 +28.29% 被严格池复测推翻——旧池正收益系幸存者偏差产物；基线事实=无偏池上无任何已测规则有正扣费后收益 |
| p3-p1pool-rerun-task-brief | 严格池八组×5 窗共 40 个 total_return 全负（−71.5544%~−1.5825%） |
| event-family-round1（E4 披露） | E4 回购源缺失退市公司，带幸存者偏差（note_20），不得声称代表完整无偏事件家族 |
| monthly-etf-t0-termination-coverage | ETF 清盘 5 例留档、baostock 快照无清盘覆盖→UPPER_BOUND_NOT_IDENTIFIABLE |

**簇级结论**：在市池上测出的正收益，加入退市/ST/停牌时点门禁后可整体翻负（P3 实测差 >55pp，且掩码只解释 1.1pp——偏差主体在池构建层）。**再试什么会再死**：任何先在当前在市池上看到正收益就立项的路线。新候选必须先过严格池；「在市池 +21.97%」类结果不构成立项依据。

### MC4 高频检查/提前退出使趋势择时退化

| 实验 | 证据摘录 |
|---|---|
| v3-daily-exit-conclusion | 月频→每日趋势检查：年化 10.194589%→1.988936%、夏普 0.459087→0.216957、回撤 −58.85%→−63.48%、whipsaw 10 笔 −18,612→20 笔 −43,599 元 |
| v3-repair-artifact-review-pack | 臂 B 每日排名衰减退出：年化 10.19%→0.03%、现金日 52→463；臂 A 相关性 0.80 顺延约束：回撤 −59.48% 未改善（系统性下跌期全池相关性齐高）；AB −0.76%、ABC 0.0604% 主判定 FAIL 复算落锤 |
| weekly-trade-research | 第五日强制退出 3.13%/0.753 < 允许条件续持 4.47%/1.114——缩短持有期同样退化 |
| v3-arm-c-mechanism-artifact-review-pack（对照） | M2 仅再平衡年化 11.76% > M1 固定 0.75 的 9.94%——无害的再平衡不是问题所在，问题在高频信息反应 |

**簇级结论**：V3 的收益来自月频低换手的趋势暴露；每日退出、每日排名、相关性顺延、五日强退全部把趋势段提前砍掉或制造 whipsaw。**再试什么会再死**：月频框架内任何「提高检查频率/提前退出/趋势敏感止损」变体。该方向已被 v3-daily-exit 预登记判死并在 v3-repair 预登记明文不重开。

### MC5 方向预测模型无信息增量

| 实验 | 证据摘录 |
|---|---|
| short-target-research | 概率过滤两组合 −0.41%/−1.05%；2024 方向准确率股票 49.68% vs 频率基线 48.86%，Brier 改善 −0.13%/−0.19%（均劣于基线） |
| weekly-trade-research | 模型版 0.86%/0.529 < 无模型 3.13%/0.753；2024 准确率 51.68% 低于频率基线 52.65%，Brier 改善为负 |
| D-2026-09-03-08（TimesFM q50 主方案） | 预注册主方案净值 0.891 vs 动量 1.953、Top1 月均 +0.30%；P10 事后变体按反数据窥探纪律不采纳 |
| D-2026-09-03-09（TimesFM 消融） | znorm、全历史、量比双变量、横截面联合预测全部无益或有害——瓶颈不在输入丰富度，在月频横截面收益接近不可预测 |
| D-2026-09-04-01（Kronos） | 用户决定终止；已完成 2/44 个月不作有效性判断 |

**簇级结论**：横截面方向/收益预测（ML 概率模型、时序基座模型）在月频/周频上不优于历史频率基线；「更多信息/更强模型」假说已被消融系统性排除。**再试什么会再死**：换基座模型、加特征、加数据长度。唯一出口是换标签定义（如分位带宽作风险信号，仅记录未验证）或等待前向样本积累。

### MC6 数据覆盖不足→覆盖损失/上界不可识别

| 实验 | 证据摘录 |
|---|---|
| mr-statarb-round1 | SW 指数缺 7 个交易日→60 日窗全观测规则级联：单缺日 ε 缺失约 60 交易日、z 缺失约 119 交易日；市场级近似无信号时段 2022-03~2022-11 与 2023-09~2024-03 |
| monthly-etf-t0-minute-probe | 新浪 5 分钟仅返回最近 320 根且忽略起止参数；baostock 无 ETF K 线→ETF 长历史分钟回放不可行 |
| monthly-etf-t0-termination-coverage | 缺历史全目录、逐只终止类型及末次价格/清算净值→数值幸存者偏差上界不可识别 |
| tushare-second-pull | SW 指数右端 2026-08-28 源滞后；index_member_all 5,902 行快照 out_date 全空→行业归属历史 spells 缺口 |
| short-data-coverage | baostock 无 ETF/北交所 K 线；分红明细遗漏案例（600519 两笔）须与 preclose 跳变对账后方可入账本 |
| family-batch-screening-f6-financial-ext-appendix-draft（构造级） | F13 因 profit_dedt 列不在 income 接口而 data_absent |

**簇级结论**：数据缺口先把结论级别压低（探索级/不可识别/描述性），再砍掉可测窗口（MR 级联损失约 8 个月市场级信号）。**再试什么会再死**：数据前提不补齐（ETF 长历史分钟源、行业时点 spells）而重跑同类研究——只会得到同样的覆盖损失或同样的「不可识别」。

### MC7 治理性排除（预登记纪律/事后发现/方向条款/用户决策）

| 实验 | 证据摘录 |
|---|---|
| family-screening-review-pack（PV2/PV5 终裁） | PV2 不满足冻结方向条款（记强负向探索发现 IC−0.0662）；PV5 系非预登记构造的事后发现——均无正式精测资格 |
| p4-revised-selection-conclusion | 原 48 格如实封存：F2 不反向重选、C1/C2 不追认、不扩大原网格、不打开 2024+ |
| event-family-round1 / family-screening-review-pack | E1_bull 差 3.3bp、PE3 差 2.65bp 均明令不得作为追加参数或换判据理由 |
| p4-r2-etf-mixed-pool-preregistration-draft + position-sizing-plan | 前者搁置（产品主线变更）、后者作废（用户改选改规则路线）；恢复均须用户授权 |
| D-2026-09-04-01 | Kronos 由用户决定终止 |

**簇级结论**：这一簇不是「策略被证伪」，而是冻结协议对事后发现、临界微调、路线变更的程序性拒绝。重开门槛全部是程序性的：重新预登记＋（路线级）用户授权，且不得以旧轮结果为 PASS 依据。对 R1 的含义：任何预登记若复用上述被排除构造而不声明来源，审查即应打回。

### MC8 机制本身无正向超额（无信号或方向相反）

| 实验 | 证据摘录 |
|---|---|
| event-family-round1 | E2 快报发布效应全负且随期限恶化（h=20 −1.54%）；E3 增持/E4 回购均无信号 |
| family-screening-round1（③MF） | 资金流 MF1-MF5 20 格超额全负（MF5 h=20 −566.7bps） |
| family-screening-review-pack（②PE） | PE1-PE5 CI 下界全负（非临界，是方向性缺失） |
| r1-formula-gap-analysis | BENCH/STATE 字段单独成因子无横截面分散度（结构必然，非实证） |

**簇级结论**：部分信息事件（快报、增持、回购、龙虎榜净买入）在 2020-2023 选择窗内没有可交易的正向漂移，部分方向相反。这类死不是显著性问题——**再试什么会再死**：换持有窗、换过滤器的同机制构造。连续化表达转子矿区（FLOW_CONT/RESID_REV）属新预登记，不复用本轮结论。

**未入簇单例**：token-router（DZ-012，工具链 A/B 降幅 0.0% 未过 ≥50% 门槛，非交易研究线）。

---

## 2. 死区登记簿总览（`artifacts/experiment-index-20260911/dead_zones.jsonl`，20 条）

每条字段：zone_id / name / mechanism / cluster / scope / identity_keys（机器比对键数组）/ verdict_ref{experiment_ids, decision_ids} / reopen_conditions / confidence / source_docs。

| zone_id | 死区 | 机制簇 | confidence |
|---|---|---|---|
| DZ-001-EVENT-FAMILY-R1 | 事件家族事件型策略层（E1_bull/E2/E3/E4） | MC2+MC8 | sealed |
| DZ-002-MR-STATARB-R1 | MR 残差均值回归 6 格 z 网格（含 2024+ 留出窗污染条款） | MC2+MC6+MC7 | sealed |
| DZ-003-P4-48CELLS | P4 价量短线 48 格（12 候选×4 止损） | MC1 | sealed |
| DZ-004-P4-LOWVOL-H10 | 低波动 5→10 会话延期 | MC1 | sealed |
| DZ-005-V3-DAILY-EXIT | V3 每日/加快趋势退出 | MC4 | sealed |
| DZ-006-V3-REPAIR-AB-ARMS | V3 修复轮 A/B 臂（及 AB/ABC） | MC4 | sealed |
| DZ-007-PV2-PV5-PRECISION-DENIED | PV2/PV5 无精测资格 | MC7+MC8 | sealed |
| DZ-008-WEEKLY-TWO-LINES | 周内入场三规则＋周内标签模型 | MC4+MC5 | strong |
| DZ-009-PV-DAILY-PROFIT-ENGINE | 日线价量因子当盈利引擎（产品层） | MC1+MC3+MC7 | sealed |
| DZ-010-T0-SYMMETRIC-TIERS | 做T 对称档位日内往返（分钟证据口径） | MC1 | single |
| DZ-011-TIMESFM-KRONOS | TimesFM/Kronos 基座模型接入生产排名 | MC5 | sealed |
| DZ-012-TOKEN-ROUTER | token-router（工具链，非交易） | —（单例） | sealed |
| DZ-013-ETF-MIXED-POOL-SIZING | P4 R2 ETF 混合池＋仓位分级（搁置/作废，非实证死） | MC7 | single |
| DZ-014-MONEYFLOW-EVENTTYPE-20CELLS | ③资金流事件型粗筛 20 格 | MC8 | strong |
| DZ-015-FORECAST-PE-SCREENING | ②预告家族重开批 0/5（PE1-PE5） | MC2 | strong |
| DZ-FML-LHB-WINDOW-OPS | 因子层：LHB 稀疏字段×窗口算子结构性近死 | MC6 | strong |
| DZ-FML-BENCH-STATE-STANDALONE | 因子层：BENCH/STATE 单独成因子 | MC8 | strong |
| DZ-FML-WINDOW-TUNING-PSEUDONEW | 因子层：换窗口伪新颖（哈希归一化） | MC7 | sealed |
| DZ-INDUSTRY-PIT-GAP | 行业时点归属缺口（EXPLORATORY_ONLY 封顶） | MC6 | strong |
| DZ-ETF-MINUTE-LONGHISTORY | ETF 长历史分钟数据缺口 | MC6 | single |

- 前 13 条（DZ-001…DZ-013）= EX1 §5 死线逐条入册；后 7 条 = 机制聚类补充（含 3 条因子层死区）。
- identity_keys 格式：`formula_hash:<sha256>|canonical=<窗口归一化串>`（因子结构类，由 `experiments.factor_miner.compiler.compile_formula` 现算，未改任何包代码）；`mech:<机制标签>×{参数范围}`（非因子类）；`pred:<结构谓词>`（类级死区的机器可判条件）。
- confidence 分布：sealed=11、strong=6、single=3。

---

## 3. 与 EG 血缘图（graph.jsonl）的交叉引用

**状态计数勘误**：任务简报记「COMPLETE 20/PARTIAL 10/BROKEN 0」；图文件实际为 **COMPLETE 20 / PARTIAL 10 / BROKEN 1**——BROKEN 的一条是 `C10-ETF-INCLUSION-RULE`（ETF 纳入/排除规则→实现断链：生产池含商品 ETF sh518880/sz159985，`scripts/build_pool.py` EXCLUDE 正则漏「商品」关键词，且无豁免留档）。以图文件为准；该断链同时是死区 DZ-013/ETF 排除规则继续有效的旁证。

**FAIL 结论中血缘 PARTIAL、需要补文档的**：

| claim | FAIL 结论 | PARTIAL 原因（图文件原文） | 需补 |
|---|---|---|---|
| C11-MR-R1-FAIL | MR 阶段 C FAIL（D-2026-09-09-15） | 「D-2026-09-09-15 记『待Codex复算确认后本轮封存』，后续决策仅引用『FAIL 封存』，未见复算完成记录——工件复算环未闭合」 | MR round-20260909 工件复算完成记录（决策条目或独立复算报告）。注意：DZ-002 的封存本身由预登记＋用户确认支撑（sealed），此缺口不影响封存效力，但影响证据链闭合 |
| C28-TW-CONSTARG | （非策略 FAIL，但影响 R0 幸存者）TW 组件 5 真缺陷，常量实参缺陷命中 215 冻结公式之 12，R0 官方批 9 结构静默清零 | TW 轮无独立结论文档，缺陷明细仅压缩记录于 decisions 一段，5 缺陷钉住未修待 Codex 裁方向 | TW 轮独立结论文档＋修复后受影响 9 结构重算记录——**R0 幸存者入攒批统考队列前必须闭合** |

**其余 PARTIAL（非 FAIL 结论，登记备查）**：C04（t0 生产规则属规格声明型，无单一实验工件链）、C07（arm-c 正式结果数字仅在 decisions.md，docs/experiments 下无独立结论文档）、C18（short 研究状态声明，独立审查未完成）、C21（R0 首跑死因未定、官方批无 registry 工件）、C26（修复波 Codex 终审未完成；wave1 独立复审 CHANGES_REQUESTED）、C27（B-01 全市场正式扫描未执行，命中矩阵为占位）、C30（top15 成本表一次性脚本用后即删、无落盘工件）、C31（Gate C/D 冻结为状态型结论、无单一工件）。

---

## 4. 给 R1 冻结清单的输入（待挖方向撞死区，预登记必须排除）

R0 幸存者＋财务 7 构造＋PV1 进入攒批留出窗统考后，R1 新一轮挖掘的预登记应显式排除以下方向（对应 zone_id 见 §2）：

1. **事件型策略层**：预告/快报/增持/回购事件漂移、解禁避雷过滤 → DZ-001、DZ-014、DZ-015。连续化表达须走新子矿区预登记并声明不复用原轮结论。
2. **MR z 网格邻域**：60 日滚动残差×深 z 入场×z 回归退出×17/27/37bps → DZ-002；RESID_REV 子矿区承接连续化时须声明不重开原 6 格。2024+ 留出窗对 MR/事件家族已被一次性观察（污染披露冻结；锁箱一批候选最多一次）。
3. **日线价量短线选股**：P4 12 候族×止损网格、低波十分位持有延期、以及「日线价量当盈利引擎」产品层 → DZ-003、DZ-004、DZ-009。
4. **V3 择时修改方向**：每日/加快趋势退出、每日排名衰减退出、相关性顺延约束、仓位分级 → DZ-005、DZ-006、DZ-013。
5. **周内入场规则与周内标签模型** → DZ-008。
6. **做T 对称档位增益**（未先回答逆向选择前）→ DZ-010。
7. **时序基座模型方向预测**（TimesFM/Kronos 类）→ DZ-011。
8. **因子层结构性死区**（R1 研究员逐条自查）：LHB 字段×窗口>1 算子 → DZ-FML-LHB-WINDOW-OPS；BENCH/STATE 单独成因子 → DZ-FML-BENCH-STATE-STANDALONE；换窗口伪新颖（哈希归一化下同构造同哈希，registry 查重即淘汰）→ DZ-FML-WINDOW-TUNING-PSEUDONEW。
9. **行业时点归属依赖构造**：无历史 spells 前一律 EXPLORATORY_ONLY 不得晋级 → DZ-INDUSTRY-PIT-GAP。
10. **ETF 分钟级盈利验证**：数据前提未满足 → DZ-ETF-MINUTE-LONGHISTORY。

另有去重级排除（非本登记簿条目，指向 `docs/experiments/r1-formula-gap-analysis-20260911.md` §4 饱和警告 S1-S13）：价格动量/反转本体、市场状态门控×翻符号、贝塔形态、残差动量全家族、日内微观结构主干、有符号量流、波动率期限结构、估值×X 交互、融资融券流、龙虎榜、流动性/Amihud、收益分布形态、名义价格效应——同机制外壳变体在查重/近亲判断中即被淘汰。

---

## 5. 自验记录

- dead_zones.jsonl 逐行 `json.loads` 通过（20 行）；zone_id 唯一；每条 identity_keys 非空；verdict_ref 的 experiment_ids 全部存在于 EX1 索引（DZ-011/DZ-012 为纯决策记录死线，experiment_ids 为空并在 note 字段披露）。
- 公式哈希抽查：从源文件（`artifacts/factor-miner/r0-20260910/hypotheses/_all_raw.jsonl` 的 META_flowlhb_08/09/10/13 与 r1-pool 的 FLOW_lhb_net_penetration）取公式，经 `compile_formula` 重算后与登记簿内哈希逐条比对 **5/5 一致**；另以手工渲染 canonical 串独立 sha256 复算 4 条，**4/4 一致**。哈希归一化已验证：`RET(close,10)`、`RET(close,15)`、`RET(close,20)` 同哈希（窗口占位符机制）。
- 口径披露：r1-pool 实际为 17 个 researcher_*.jsonl / 215 行（r1-formula-gap-analysis 写作时点为 12 文件/153 条，workspace-inventory-20260911 §已披露该漂移）；本文与登记簿引用的是实际文件口径。
- 本代理零 git 命令；未修改 EX1/EG 产物、factor_miner 包、Codex 证据文件及任何既有文件；仅新增本文与 dead_zones.jsonl。

---

*生成：EX2 失败聚类代理，2026-09-11。失败机制与重开条件均抄自原文档/决策，未自行发明；EG 交叉引用以 graph.jsonl 原文为准。*
