# 系统风险分层审查：影响矩阵与后续工作量

日期：2026-09-10。当前仅记录 A 阶段已证实影响；不据此泛化判定整个系统有效或无效。

## 影响矩阵

| 发现 | 代码路径 | 直接证据风险 | 可能受影响批次/结论 | 当前处置 |
|---|---|---|---|---|
| A-01 重复/无效 ID 被接受 | registry JSONL → `load()` → dict 覆盖 | gate、计数或统计冲突记录可消失 | numpy dev-smoke registry 对照及依赖其 PASS 的运行前声明 | numpy 裁决阻断；不删除旧工件 |
| A-02 双空/共同漏单元通过 | 两侧集合互比，无独立 expected set | 无证据或不完整证据可被写成 PASS | round-3 真实 registry 对照；未来 R0 对照 | 需用冻结候选清单重验；R0 保持停止 |
| A-03 探针零覆盖/编译失败通过 | hypothesis → compile → compare | 部分或零公式被评估仍可 PASS | “250 冻结公式合成差分 PASS”证据链 | 修复后以独立 expected set 重验；无需当前重跑全市场 |
| A-04 身份未绑定 | identity keys 被跳过 | 跨代码/配置工件可被错误配对 | 旧 dev-smoke 与任何后续跨路径 registry 对照 | 先裁决身份模型，再重验已有 TRAIN 内工件 |

现有证据没有证明真实 round-2 registry 已发生重复或共同漏单元，因此不能直接宣布其数值结果作废；但当前检查器也不能证明它完整。该证据状态应标记为“待修复检查器后复核”，不能用于授权正式 numpy 路径。

R0 已终止且用户明确暂停重启。本阶段未启动 TRAIN、VALIDATION、LOCKBOX，未读取留出窗，未恢复一次性预算，未终止其他进程。

## 必要重验顺序

1. 实现者只修 A-01～A-04 的检查器和测试，不改因子数学、统计协议或被审实现。
2. 固定提交及 expected hypothesis/registry 清单、代码与配置身份。
3. 独立复跑所有负例；再复跑 56 项 numpy 专项。
4. 用冻结 expected set 复核已有合成探针和已有 TRAIN 内 dev-smoke registry。已有工件身份不满足新模型时，只能标记不可作为绑定身份证据，不得伪造匹配。
5. A 阶段闭合后再提交 numpy 路径裁决和 R0 恢复方案；恢复仍由用户决定。

## B～E 工作量重估

### 主审执行 B～E 后的影响补充

用户已授权直接开始 B/C/D/E，以下取代“等待后续发现”的进度描述，但不解锁运行。

| 缺陷 | 实际依赖链 | 批次/候选当前状态 | 修复后最早复核点 |
|---|---|---|---|
| B-01 常数数值错误 | operators→compiler→train_test→registry | R0含相关算子的单元待TRAIN触发扫描；META_flowlhb_12已在旧独立审查给出合成传播反例，真实命中未知 | 命中窗口因子值、排名、IC、门禁 |
| B-02 公共行情非有限漏检 | validation→cli日线门禁 | V3/做T相关入口须加固；未证明历史数据命中，不全盘作废旧V3工件 | 输入门禁及输出降级 |
| B-03 日轴压缩 | build_market_axis→所有滚动/期限 | 仅在全样本共同缺行时触发，正式R0/小样本覆盖待定 | 固定日历与缺行对齐 |
| C-01 粗筛N未进入门禁 | train_test→continuous_gate→TRAIN gate→registry | R0粗筛资格待校正复核；不能将其影响无依据扩展到独立财务筛选器 | 若IC身份有效可直接重算校正门禁；若同时命中B则先重算因子 |
| C-02 NaN门禁 | continuous_gate | 真实触发未证实，异常输入门禁明确失守 | 输入/区间有效性与门禁 |
| C-03 锁箱访问记录/集合身份 | run_lockbox→本地ledger | 未读取或修改任何真实ledger，不能声称曾有重复考试 | 合成失败/并发/换序反例；真实访问审计另列 |
| C-04 并列十分位 | train_test→decile_spread描述统计 | 描述指标待复核，不能据此宣称TRAIN gate翻转 | 仅同输入描述性指标 |
| D-01/02 月频执行和账本 | cost_ladder→TRAIN指标与VALIDATION gate | 受影响成本阶梯与净边际不得支持晋级；旧批次真实触发数量未确认 | 逐笔执行/现金/配对月份，再重算净边际 |

PV1与财务7构造有独立脚本和旧身份；本轮117项专项绿不等于新工件验收，也没有证据可直接将factor_miner/backtest缺陷套到它们。Top15产品尚需自己的真实成本、共享资金和分档交易验收，不能继承因子代理回测PASS。MR/事件旧失败家族保持封存。

不按收益挑样本，不擅自重看留出窗。批次逐候选触发扫描未完成，故 E 最终状态为待闭合，未给出臆测的重跑数量。组件接口初筛见 `system-component-evaluation-20260910.md`。

A 阶段发现四项门禁缺口，修复面集中在两个验证工具，预计实现与独立复审为一个小工作包；是否需要重新生成 dev-smoke 取决于身份模型，不能预先承诺。

- B（数据与因子）：风险高、范围大。优先审公告时点、稀疏覆盖、常数/近零方差和两路径离散传播；先做合成与 TRAIN 边界小样本，暂不安排全市场计算。
- C（统计与留出控制）：风险高。A 的 expected-set/identity 机制将成为 C 的候选数、registry 和阶段访问验收前置；需单独工作包。
- D（成交、资金与输出）：与 A 缺陷没有直接代码耦合，可只读并行梳理，但正式逐笔账本验收仍是独立工作包。
- E（历史影响与组件取舍）：必须等待 B～D 的具体缺陷触发范围，当前不能可靠估算重跑量，也不安装或选择外部组件。

因此不采用固定“半天完成全系统”估计。下一阶段应先闭合 A，再按 B、C、D 各自发现数量更新范围；全市场重算和任何留出窗动作单列授权。

---

# E 阶段补充：静态影响矩阵、TRAIN 定位扫描与组件适配面（代理⑥，2026-09-11）

## E-0 方法与证据边界（先读）

- **本文是静态追溯**：对 B-01/B-02/B-03/C-01/C-02/C-04/D-01/D-02 逐项 grep 调用链（只读），从触发条件追到入口、批次与下游消费。**真实命中范围以定位扫描（B-01，见 E-4）与修复后重算为准**，本文的「可能受影响」不等于「已证实受影响」。
- **工件影响三档**：`可能受影响`＝生成路径经过缺陷代码；`不经过`＝生成路径可证未流经缺陷实现（独立脚本/纯输入文件）；`待定位`＝依赖数据实况或未完成扫描，不许臆断。
- **工作树时点声明**：本轮观察期间工作树正被并行修复代理持续修改。T1≈2026-09-11 00:20、T2≈同会话稍后两次核对（先读 engine/backtest 仍为缺陷实现，数十分钟后重查已含 B-03/D-01/D-02 修复）。按纪律未运行任何 git 命令，**提交状态未核实**；下述修复状态是「工作树观察」，最终闭合以修复包+独立复审为准（送审包见 `system-audit-fix-wave1-review-pack-20260910.md`）。

## E-1 缺陷→修复状态快照

| 缺陷 | 审计时点（46a84db+工作树） | 工作树 T1 观察 | T2 观察 | 修复落点（观察到的） |
|---|---|---|---|---|
| B-01 常数窗伪信号 | 存在 | **修复在位** | 同 | `operators.py` `_std_sample/_zscore/_corr` 零方差规则（max==min→None） |
| B-02 inf/NaN 漏检 | 存在 | **修复在位** | 同 | `quant/validation.py` `validate_bars` 价格与 volume 均 `math.isfinite` 校验 |
| B-03 日轴压缩 | 存在 | 未修复（行日期并集轴） | **修复在位** | `engine.py` `build_market_axis(calendar=)` 冻结交易日历轴，calendar 缺失 fail-closed |
| C-01 TRAIN 无 N 收紧 | 存在 | **修复在位** | 同 | `stats.py` `_ci_spec`（alpha_total/(2N)）＋`director.py` `evaluate_units` 自动派生 `n_tests=len(units)`，registry 落 `train_multiple_testing` |
| C-02 NaN 过门禁 | 存在 | **修复在位** | 同 | `stats.py` `continuous_gate` 入口/输出有限性校验（`invalid_ic_input` fail-closed） |
| C-03 锁箱无中断留痕 | 存在 | 未修复 | 未复核 | `director.py` `run_lockbox` 仍「计算先于落盘、异常不消费台账」；`manifest_hash` 保序不规范化 |
| C-04 十分位序依赖 | 存在 | **修复在位** | 同 | `stats.py` `decile_top_bottom_spread` 改并列平均秩分档＋sorted 规范化求和 |
| D-01 停牌/零量算成交 | 存在 | 未修复 | **修复在位** | `backtest.py` `execution_status` 执行日资格（tradestatus/volume/isST），no_fill 逐笔原因 |
| D-02 账本无统一约束 | 存在 | 未修复 | **修复在位** | `backtest.py` 实际持仓 prev_hold、实际退出日、net-bench 同月配对（`n_paired_months`）、逐笔精确费用 |

## E-2 逐缺陷静态矩阵

### B-01 常数窗口伪信号（operators.py `_std_sample`/`_zscore`/`_corr`）

- **触发条件**：公式中 STD/ZSCORE/CORR 的某输入滚动窗在轴上**完全常数**（max==min）且窗内全为有限值。浮点残差级近常数窗在旧实现同样产生伪值（同根因）；近常数不在修复范围（已知边界，operators.py 模块注释声明）。
- **实际调用路径**（三条全部收口于 `operators.apply_window_op`）：
  1. `director.run_real_pipeline` → `evaluate_units` → `train_test`/`engine.evaluate_plan` → `compiler.evaluate` → `operators._eval_node`（纯 Python）；
  2. 同上 + `FACTOR_MINER_NUMPY` 环境变量 → `operators_np.evaluate`（numpy 复刻路径，同语义缺陷）；
  3. `director.run_dev_smoke` / `run_validation_stage` / `lockbox_evaluate` → 同 1。
  门禁下游：`stats.monthly_rank_ic_series` → `continuous_gate`（伪因子值→伪 RankIC→伪 gate_pass→registry `status`/`train_metrics`）。另核过：`engine._add_derived_state` 的 `market_vol` 用引擎本地 `_std_sample`（无 max==min 保护，常数窗会给出近零而非严格定义的样本标准差）——它是 20 日市场收益窗，实际恒常数概率趋零，且偏差是残差级而非 ZSCORE 型伪大值，审计未将其列为缺陷；此处仅作保守披露，不据此扩大范围。
- **已产出工件**：
  - `artifacts/factor-miner/r0-20260910/hypotheses/`（250 条假设）与 `r1-pool-20260911/`：**不经过**（研究员原始输出，未经任何计算）。
  - `artifacts/factor-miner/dev-smoke/20260910_082210|082248|094308`、`dev-probe-out/dev-smoke/20260910_190004`：**可能受影响**（真实 TRAIN 数据经旧 operators 计算；4 只小样本，registry 含 gate_pass 与 094308/19:00 两批的 cost_ladder 净边际）。DEV_SMOKE 性质＝引擎开发冒烟，不构成晋级证据。
  - `r0-20260910` 官方批次：目录内**无 registry/candidates/universe**（运行已终止，仅 hypotheses＋空 run log）→ 无已产出计算工件受影响。
  - PV1/财务扩展批次：**不经过**（独立脚本，见 E-3 公共行）。
  - 具体哪些 (因子,窗口,股票) 命中：**待定位** → 已交付定位扫描（E-4）。
- **必要重跑**：命中单元在修复后代码下从因子值节点重算（重算结果进新批次目录，不覆盖旧工件）；dev-smoke 冒烟在修复包闭合后以新代码重跑一次作为回归证据；若扫描全零命中且双轴一致，则无因子值级重算义务（统计层重算义务由 C-01 独立成立）。

### B-02 公共行情验证器接受无穷价格/NaN 成交量（quant/validation.py `validate_bars`）

- **触发条件**：进入验证器的日线行含 OHLC=±inf 或 volume=NaN（修复前仅拒 NaN/非正价格、负 volume）。
- **实际调用路径**：`validate_bars` ← `quant/cli.py _gate_symbol_bars` ← `_collect_pool`（V3 轮动池/daily/short 共用）← **生产与研究会话入口**：`cmd_daily`（daily-swing-v1）、`cmd_t0`（做T）、`cmd_short`（一周短线）、`cmd_forecast`、`cmd_smoke`；另 `cmd_fetch_all`（`fetch-daily --all` 落盘前门禁）、`quant/data.py` 修复路径（删行后须过 validate_bars）、`experiments/kronos_analyze.py`/`ak_probe.py`/`daily_swing_oos.py`。**factor_miner 引擎不经此函数**（其装载语义为 mr_statarb merge+fail-closed）。
- **已产出工件**：审计已定级「明确漏检但不能断言真实数据已含该输入」→ 全部 V3/做T/daily/short/forecast 历史工件 **待定位**（需证明历史数据无 inf/NaN 行才可解除；直接证据是源数据审计，非重算）。factor-miner 系工件 **不经过**。
- **必要重跑**：无需数值重跑；修复后用负例验证（审计验收条款），并在下一次数据完整性检查中加 inf/NaN 抽样核对（建议项，非本轮交付）。

### B-03 因子日轴依赖已存在价格行（engine.py `build_market_axis`）

- **触发条件**：bundle 内**全体样本共同缺行**的交易日——轴被压缩、RET/滚动窗/持有期限越过真实会话。个股独有缺行不触发（该日其他股票在轴上，缺行者=None 传播）。
- **实际调用路径**：`build_real_bundle` → `build_market_axis` → 一切 bundle 消费者：`evaluate_units`（因子值/IC/衰减/十分位）、`bt_mod.cost_ladder`、`run_validation_stage`、`corr_cluster`（月末截面取值位置）、`_add_derived_state`（market_ret 等值日错位）。dev-smoke 与正式 pipeline 共用。
- **已产出工件**：dev-smoke 4 批 **可能受影响**（4 只共同缺行概率低但未验证——需要「TRAIN 窗口 并集轴 vs 交易日历」比对，**待定位**）；官方批次无计算工件；PV1/财务 **不经过**（自有装载与 Timeline）。
- **必要重跑**：待修复闭合后，以「并集轴∩TRAIN vs 日历∩TRAIN」差集检查证明历史 bundle 无共同缺日（一次数据审计即可豁免全部历史）；不能证明则受影响日期的因子值/统计从修复后 bundle 构建重算。B-01 扫描的 compressed_axis 列提供每股级行缺口信息，可作辅助证据但不等价于「全 bundle 共同缺日」。

### C-01 TRAIN 未落实多重检验收紧（director.train_test → stats.continuous_gate）

- **触发条件**：任何 TRAIN 门禁判定（旧代码 CI 恒 [0.025,0.975]，N 未进入）。
- **实际调用路径**：`evaluate_units`（正式 pipeline / dev-smoke / fixture 管线）→ `train_test` → `continuous_gate` → `update_registry`（`gate_pass` → `status`=TESTED/NO_SIGNAL/WRONG_DIRECTION → VALIDATION 准入 `_registry_train_gate_ok`）。
- **已产出工件**：4 批 dev-smoke registry（8 条 gate 记录，含旧 CI 下 pass=True 的 `devsmoke_vr5`（082248）与 `META_flowlhb_05`（19:00 探针））**可能受影响**——它们作为「门禁在旧口径下产生该结果」的工程证据已失效，作为晋级证据本就不成立（DEV_SMOKE/探针非晋级通道）。官方批次无计算工件。⑤财务粗筛（F1/F4）与 PV1：**不经过**（独立脚本自有门禁，`screen_financial_stmt.py`/`pv1_precision_test.py` 不 import factor_miner；复用 mrs.bootstrap 协议为其自有冻结口径）。
- **必要重跑**：无历史晋级判定需要撤销；修复闭合后 TRAIN 判定一律以新口径（α=0.10/N 自动派生）在新批次产生。核过修复链：`n_tests=len(units)` 由 `evaluation_units` 输出自动派生、registry 可见 `train_multiple_testing`，与审计验收条款方向一致（最终以独立复审为准）。

### C-02 NaN 显著性输入过门禁（stats.continuous_gate）

- **触发条件**：IC 序列含 NaN/inf/越界值或 bootstrap 输出 lo>hi/非有限。正常路径 `spearman` 只返回 None 或有限浮点（零方差→None），**真实数据流不自然生成该输入**——审计原话「历史触发范围未证明」。
- **实际调用路径**：同 C-01 的 `continuous_gate`。
- **已产出工件**：**待定位**（无证据曾发生；静态上无法排除损坏中间件输入）。修复后门禁对非法值 fail-closed。
- **必要重跑**：无；负例验收即可。

### C-04 十分位描述统计随字典顺序翻转（stats.decile_top_bottom_spread）

- **触发条件**：月末截面存在并列因子值＋字典构造顺序变化。
- **实际调用路径**：`train_test` → `decile_top_bottom_spread`（描述性输出，落 train_test 返回值）。核过：**gate 判定只消费 `gate`（mean_ic/bootstrap），不消费 decile_spread**——无门禁影响路径。
- **已产出工件**：dev-smoke 4 批的描述性十分位列 **可能受影响**（数值级微小，且不入 registry status）；无下游消费证据。
- **必要重跑**：仅报告描述列在修复后重算（低优先级，随下一次 dev-smoke 自然覆盖）。

### D-01 因子月频回测把停牌/零量算作成交（factor_miner/backtest.py `_holding_return`/`_exit_open_index`/`monthly_backtest`）

- **触发条件**：持仓股票在**执行日**停牌（tradestatus=0）、成交量 0、ST 状态变化，而信号日 P1 掩码合格——信号日资格≠成交日资格。真实 TRAIN 数据中停牌股-日以千计，凡 cost_ladder 跑过真实 bundle 即**结构性可能命中**；具体命中笔数待修复后重算时由逐笔原因清单给出。
- **实际调用路径**：`evaluate_units(cost_bps_ladder=True)`（正式 TRAIN 粗筛与 dev-smoke 共用）→ `bt_mod.cost_ladder` → `monthly_backtest` → `validation_family_gate` 条件④⑤（17/27bps net_edge）→ `apply_validation_results`（VALIDATION 晋级）。锁箱描述性 17/27/37bps 同路径。
- **已产出工件**：dev-smoke 094308（3 单元 cost_ladder 净边际）与 19:00 探针批（5 单元）**可能受影响**——该两批净边际不得用于任何晋级语义（本来也不具备）；官方批次无计算工件；PV1/财务 **不经过**（自有执行语义；PV1 已有独立审核链）。
- **必要重跑**：修复闭合（含人工逐笔账本验收）后，所有未来 TRAIN/VALIDATION 成本阶梯与净边际必须由修复后实现产生；旧两批 dev-smoke 重跑作回归证据。**不可用 quant.execution 的既有 PASS 替代本模块验收**（审计明确）。

### D-02 非成交/递延/基准无统一账本约束（同文件 monthly_backtest）

- **触发条件**：同 D-01（未成交剔除后重等权、prev_hold 用目标持仓、锁单递延不返回实际退出日、net/bench 各自过滤缺月）＋任何把 `net_edge` 当真实组合净边际的下游解读。
- **实际调用路径**：`monthly_backtest` → `cost_ladder` → `validation_family_gate`（net_edge ④⑤）；下游消费声明：Top15 组合精测（未启动）**不得**继承该模块结果作为执行资格（审计 D-02 证据等级：静态数据流确认，未做全链人工账本）。
- **已产出工件**：同 D-01 两批 dev-smoke **可能受影响**；其余同上。
- **必要重跑**：以人工账本（未成交留现金、递延资金占用、同月基准配对、逐笔费用）验收修复实现后重算；20 万元/15 只名义低于「单笔≥5 万最低佣金不生效」前提的问题属新产品成本模型重新冻结范围，不是本模块重跑能解决的（审计已单列）。

## E-3 工件盘点汇总（三档）

| 工件 | 生成路径 | 档 |
|---|---|---|
| `artifacts/factor-miner/r0-20260910/hypotheses/_all_raw.jsonl`（250 条）及家族 jsonl | 研究员原始输出 | **不经过** |
| `artifacts/factor-miner/r1-pool-20260911/`（下轮研究员假设） | 同上 | **不经过** |
| `artifacts/factor-miner/dev-smoke/20260910_082210|082248`（3 只×3 单元，无 cost_ladder） | 旧 operators+旧 CI+旧轴 | **可能受影响**（B-01/C-01/C-03/C-04/B-03；无 D 路径） |
| `artifacts/factor-miner/dev-smoke/20260910_094308`（4 只×3 单元，含 cost_ladder） | 上述全部＋旧 backtest | **可能受影响**（B-01/C-01/C-04/B-03/D-01/D-02） |
| `artifacts/factor-miner/dev-probe-out/dev-smoke/20260910_190004`（META_flowlhb 5 单元，含 cost_ladder，1 个旧 CI gate_pass=True） | 同上 | **可能受影响** |
| `artifacts/factor-miner/r0-20260910/` 官方批次计算产物 | 运行终止，目录无 registry/candidates/universe/run_meta | 无受影响对象（仅输入） |
| `artifacts/pv1-precision/round-*`（含 in-window r2..r7） | `experiments/pv1_precision_test.py`（自有门禁/回放；不 import factor_miner/validate_bars/build_market_axis） | **不经过**（8 项缺陷） |
| `artifacts/family-screening/f5-*`（F1/F4 等）与 `f6-ext-*`（财务扩展 26 构造） | `experiments/screen_financial_stmt.py`/`screen_financial_ext_r1.py`（同上独立） | **不经过**（8 项缺陷） |
| V3 / 做T / daily / short / forecast 历史信号与工件 | 经 `quant/cli.py` `validate_bars` 门禁 | **待定位**（B-02 唯一相关；是否曾有 inf/NaN 行进入＝源数据实况） |
| MR/事件家族封存工件 | 独立 mr_statarb 链 | **不经过**（封存状态不变） |

注：三档均指上表 8 项缺陷的代码路径关系，「不经过」不构成对独立脚本自身正确性的背书（PV1/财务的独立验收链照旧）。

## E-4 B-01 TRAIN 定位扫描（已交付，待正式运行）

- 脚本：`experiments/system_audit_b01_train_scan_20260911.py`（只读、流式、有界内存、零第三方依赖；双轴计数＝B-01×B-03 交互量化；引擎派生 STATE 字段输入与 CS_RANK 输入单列 skipped 不臆断）。
- 解析（--parse-only 实测）：250/250 解析成功，**parse_fail 清单为空**；67 个因子含 STD/ZSCORE/CORR（STATE 25/REV 18/REL 13/META 11）；38 个去重 B-01 需求（29 个可直接逐股扫描，9 个引用引擎派生 STATE 字段须 bundle 级复算）；CS_RANK 输入需求 0 个。
- 自检（--self-test 实测）：18/18 断言通过（常数窗检出、None 断窗、expr 输入、双轴分歧、路由归类、报告结构）。
- 报告：`docs/experiments/system-audit-b01-train-scan-20260911.md`（含正式扫描命令；命中矩阵由脚本写入 SCAN 标记块，0 命中也列出）。**全市场扫描未运行**（避免与在途批次争内存），由主对话集成阶段择机执行。

## E-5 必要重跑清单（静态结论，按缺陷闭合顺序）

1. **无重算对象**：r0-20260910 官方 TRAIN 批（无计算产物）；研究员假设输入。
2. **修复闭合后重跑（引擎回归证据）**：dev-smoke 4 批以修复后代码重跑一次（新时间戳目录），核对 gate/decile/cost_ladder 语义变化——这是冒烟证据，不是研究重算。
3. **条件重算（待 E-4 扫描命中）**：B-01 命中的 (因子,输入,窗口) 在修复后 operators 下从因子值节点重算；0 命中且双轴一致的需求解除 B-01 重算义务。
4. **条件豁免检查（B-03）**：一次「TRAIN 并集轴 vs 交易日历」差集数据审计；有共同缺日则该日期范围 bundle 级重算。
5. **阻断中重算（D-01/D-02）**：所有 TRAIN/VALIDATION 成本阶梯与净边际在修复实现通过人工逐笔账本验收后重算；此前任何 net_edge 标注「待复核，不可用于晋级」。
6. **无需重跑**：C-02（负例验收）；C-04（描述列随 2 覆盖）；B-02（负例验收＋数据完整性检查加 inf/NaN 抽样）；PV1/财务/封存家族（不经过）。
7. **留出窗**：VALIDATION/LOCKBOX 未读取、未消费，攒批统考决定不变；上述重算全部限 TRAIN 与合成证据。

## E-6 E 阶段组件初筛补充：替换映射与适配面（静态，不安装）

对照审计计划 §6（因子标准算子、组合回测、绩效统计三类模块；与 `system-component-evaluation-20260910.md` 的接口初筛一致并细化映射）：

| 本系统模块 | 若换 vectorbt | 若换 qlib | 适配面静态评估 |
|---|---|---|---|
| `factor_miner/operators*.py`（冻结算子白名单 v1＋零方差规则） | 无对应算子层（组合框架不自带公式语言） | Alpha158/360 等内置算子库 | 替换＝重写全部 250 条冻结公式语义＋双路径差分机制；**不适配，仅可作外部对照实现**（§4「独立实现对照」角色，替代自写第二实现） |
| `factor_miner/stats*.py`（Spearman/月块 bootstrap/门禁） | 无 | 有 IC 统计但非冻结协议 | 协议已冻结（B=10000/种子 20260909/块 3）；替换须重新预登记，**不适配** |
| `factor_miner/backtest.py`（月频 Top 分位、成本阶梯）——D-01/D-02 缺陷所在 | Portfolio.from_orders/from_signals＋费用/现金模型 | qlib.backtest Exchange＋PortAnaRecord | **唯一适配面有限的候选**：约 215→修复后 ~450 行模块，同输入（因子月末截面＋执行日状态表）可构造订单流。但 T+1 可卖库存、开盘跌停顺延上限 20 会话、A 股费用（万 2.5 最低 5 元/ETF 万 1/印花税 5bps）、停牌无量拒成交均须自定义 order_func/exchange 规则——静态估计自定义代码量≈或＞现有模块，且引入 numpy/pandas/numba 重依赖，违反「离线测试零第三方依赖」工程纪律 |
| `quant/execution.py`（生产撮合：limit/stop/T+1/方向性封板/参与上限/做T） | 无现成语义 | 无现成语义 | A 股日内规则深度定制＋已通过独立复审（P2 整包 PASS），**不适配，不评估替换** |
| 绩效统计（年化/夏普/回撤，散布各报告层） | 内置 stats | 内置分析 | 适配面小但属报告层；引擎统计已冻结，收益限于减少自研报告函数，**优先级最低** |

静态结论（不构成选型决定）：三条评估路线中，唯一在「替换一个模块」粒度上有意义的候选是 **vectorbt ↔ `factor_miner/backtest.py`**，且其适配面（T+1/封板顺延/A 股费用/执行日状态四项自定义）与重依赖成本使得在 D-01/D-02 修复包已落地工作树的情况下**倾向「暂缓」**——先完成修复包的人工账本验收；若验收失败或维护成本证伪自研，再按 §6「固定版本→同输入订单→逐笔对账→性能对比」流程对该单一模块做有界实测。qlib 的现实角色是**因子算子与 IC 统计的外部对照实现**（校验双重路径共定义风险），非替换。任何组件替换都须独立变更方案＋用户授权＋离线零依赖纪律的例外裁决，本节不授权任何安装。

## E-7 待主对话裁决/移交事项

1. E-4 全市场扫描的执行时机与资源窗（建议：修复包复审闭合后、R0 重启决定前；先 `--max-symbols`/`--symbols-file` 试点）。
2. dev-smoke 4 批「旧口径证据」的处置：建议在修复包验收记录中标注「已被 T2 观察的修复取代，仅存档」，避免后续被引用为门禁证据。
3. B-02 的历史数据 inf/NaN 抽样审计归属（数据完整性检查 vs 单独小任务）。
4. C-03（锁箱留痕/集合身份）未在本文 8 项矩阵内（任务范围），其修复排期见 findings 文档。
5. 工作树 T1/T2 之间观察到的修复（B-03/D-01/D-02 及此前 B-01/B-02/C-01/C-02/C-04）均属并行修复代理在途工作：本文仅记录观察，不签发 PASS；提交固定与独立复审按修复包流程。
