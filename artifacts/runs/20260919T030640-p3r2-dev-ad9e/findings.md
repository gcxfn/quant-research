# P3R2 v1.1 意图层重裁定运行 · 运行发现（exp-20260918-p3r2-band-v1-readjudication）

- 运行：`20260919T030640-p3r2-dev-ad9e`；状态：**completed（判定表已产出，0/8 dev_pass）**
- 引擎 v1.1 `d7108c0eccdd77ff3fcbff01e7bd84bfdd2e7cad716b646e357c5644da970a0d`，运行前后哈希一致，**字节零修改**
- 执行模型：每配置**单帧静态意图**提交 `run_band_backtest_intents`；宿主零成交感知循环、零不动点迭代（预登记 §9 修订 2/3；9cc4 四种宿主约定全部废止，其约定 A 全窗数字未进入本运行任何环节）
- 预算：全窗 47.7 s / 峰值 RSS 5.08 GB（限 60 min / 8 GB）；随机种子：无（runner 与引擎均无 RNG）
- 全部身份 pins 匹配：r16_config `27f846a7330919a4`、p3r2_config `b49025b44c719685`、daily `d9a63f4cc3032926`、halfday manifest `2a414174b5df2eee`（18,486,939 行断言通过）、stk_limit 聚合 `3c53abf3b0c39b42`（2432 文件）、split_factor `2f436b2f13d09a9b`、dividends `46121c09cddde72e`、index `05aaa8183a11c674`；8/8 leg_log↔buffer_membership 一致性 PASS（71 信号日逐配置）；m5-b 意图帧 (symbol, side, source) 唯一性断言 8/8 PASS 于提交前

## 发现 0（映射登记，先于结果）：rescale 加仓侧 = 映射空洞

- R16 rescale 腿的"减至目标"侧映射为**常设风减单**（sell/risk，target_weight=exposure/K）——引擎逐决策点按"减至目标权重"自中性执行（低于/等于目标时 at_target 跳过，不产生错误方向交易）。
- **加仓（top-up）侧无法零反馈映射**：引擎买入原语只有"按权重/名义买入新 clip"，没有"补足到目标权重"语义；若按整座席权重发买单会把座席翻倍。按 §4.8 利润梯先例登记为**映射空洞，非原语无效**。
- 后果（诚实方向未知，必须先披露）：月内权益漂移导致的补仓不发生（低换手方向）；vs P3R1 的换手/费用/净额 delta 因此**被此空洞混杂**，不能全部归因于契约修复。P3R1/9cc4 是用宿主外不动点迭代映射了加仓侧——该迭代本身即修订 2 废止的对象。
- 空洞的量级痕迹：at_target_skips 7949–9230/配置（大部分为减仓意图的整窗无操作）；门8 终止中"到期且零发射（窗内有交易→判 at_target 无操作到期）"96–97/配置（C01 96、C05 97，详 metrics_and_gates.json `gate8_expired_at_target_noop`）。

## 发现 1（runner 机制修正，全部发生在判定消费前，逐条留痕）

1. 意图帧编码（设计）：首决策=(T,'pm')（§4.1）；expiry=T′+1 自然日 → 引擎 live_d≥expiry 语义下最后发射=(T′,'am') 决策、live (T′,'pm')，即 9cc4 冻结窗；buy_open=target_weight exposure/K（修订 3 在环定价：在 (T,'pm') 快照上恰为 R16 座席公式，零反馈）；sell_full=全额 risk；R16 outcome∈{at_target, feemin_skipped} 的 rescale 腿不入帧（9cc4 at_target 映射资产）。
2. 冒烟后为手算核验补了冒烟产物落盘（tmp/smoke/，不影响判定路径）。
3. **归因解析修正 A**：order_id 内 ISO 日期含连字符，`rsplit('-',2)` 越界崩溃 → 改为按右侧 4 个连字符切分（引擎未动；首次全窗引擎段已完整跑完且对账 PASS 后才发生）。
4. **归因解析修正 B**：引擎 lifecycle detail 是长文本（"overridden by a later same-symbol intent…"），等值比较漏配导致 override 全被误记 expiry（总量守恒、filled==stopped_filled 断言未受影响）→ 改前缀匹配。修正后 override 与引擎计数逐配置相等（如 C01 268==268）。
5. **m6 语义精细化**："零发射+到期"的减仓意图按"标的是否窗内有交易"二分：有交易→判 **at_target 无操作到期**（计入到期、单列披露），无交易→**停牌放弃**。修正后停牌放弃仅 0–1/配置（此前 81–122 为误记）。
6. 以上均为宿主披露层修正；配置、判据、池、窗口、引擎字节零改动。

## 发现 2（门8 口径 vs P3R1 不可直接比，已补辅助口径）

- 门8 注册口径（§7.7-m6 + 9cc4 惯例）：意图级，R16 不成交跳过腿（at_target/feemin）在帧外不计入分母；重锚发射中性。结果 49.3%–58.4%，全部 <95%，门8 全灭。
- P3R1 的 91–93% 是订单级口径且把 R16 的 no_lots/cash_capped/at_target 类全部计入分子。为可比性补了**辅助口径**（把 R16 跳过腿视作已执行的无操作）：C01 74.5%、C05 70.6%（全配置见 `1_fill_rate.p3r1_comparable_rate_supplementary`）——仍 <95%。**无论哪种口径门8 都不通过**，判定不变。
- 残差结构（§6 要求）：订单级买成交率 1.9–3.3% 属重锚节奏的稀释（每意图每月 ~42 次发射、成交即停，"重锚中性不计入"正是为此）；意图级买入成交率 39.4%–60.8%（C01 245/411=59.6%、C05 352/774=45.5%，K=30 配置因座席更多现金竞争更紧而偏低），较 P3R1 挂单日 8.7–17.0% 显著回升——H 的机制 (a) 在意图层成立、在订单层被稀释。below_min_lot 弃单 5205–21783/配置，集中于 16–68 只高价股（座席预算≈4–9 千元 vs 股价），结构性；insufficient_cash=0；上限作废=0。

## 发现 3（m5 修订项执行情况）

- **m5-a**：无 pm bar symbol-day 上的 pm 决策重挂 = 0–7 次/配置（C01 3、C05 7）；市场级半日日（pm<50% am 且 am>500 行）**仅 2016-01-07 一日**，与裁定备注完全一致。语义=官方收盘重锚、次一 am 生效（v1.1 正式语义）。
- **m5-b**：提交前 (symbol, side, source) 唯一性强断言，8/8 PASS；无中止。
- **m5-c**：静态 stats 惰性键如数披露：`order_generation="engine_intents"`、`intent_layer`（n_intents/activated/orders_generated/stopped_filled/terminated_*/at_target_skips/emissions_skipped_no_anchor 等）逐配置入 `5_increments.m5c_static_stats_lazy_keys`。对账恒等式全过：activated==n_intents（8 配置全部激活）；orders_generated≥stopped_filled；order_events == orders_generated − k3_executed（逐配置相等，如 C01 7811+8==7819：兜底消费的 live 限价行不发订单事件，市价退出事件 order_id 为空——引擎既定行为，披露）。
- **m5-d**：挂账项（模块 docstring cap 表述），本轮引擎字节未动，维持挂账。
- **ENGINE-3 / 修订 4**：缺行日（2017-03-07..09）风减卖单走 `void_no_limit_info`（作废+计入 K+披露），无崩溃；卖侧作废计数 C01 2、C02 2、C06 3（其余 0），全部落在 3 个缺口日内；9cc4 的宿主侧跳过偏差已废止。

## 发现 4（判定摘要，详见 report.md / metrics_and_gates.json）

- **0/8 dev_pass**。门3（优势年≥5/6）全灭（1–4/6）——与登记预期一致（信号层属性，契约不可修复）。
- 门4：回撤全部较 P3R1 收窄 2.1–12.4pp（C01 −21.65% vs −30.61%；C05 −21.20% vs −33.57%），风减映射方向有效；≤B1(m) 分句 8/8 满足（多配置贴近 B1(m)，如 C04 −55.15% vs −55.60%、C08 −55.30% vs −55.60%），但 ≤20% 硬线全灭（最近者 C05 −21.20%、C01 −21.65%）——门4 仍全灭。
- 门1/2/7：q5 关（C02/C04/C06/C08）与 FIX75 关（C03/C04/C07/C08）配置深度恶化（净 CAGR −0.62%~−5.68%）；仅 C05 净 CAGR +3.88%、超额 +3.28pp 过门1/门2，仍倒门3/门4/门8。
- K=3 兜底 armed 7–9、executed 6–8（跌停顺延为主）；换手 1.49–2.70 过门5；单票最大权重 6.7–12.3% 过门6（契约 25% 结构性满足并核验）；每日权益全程为正（最小 113k–180k）。
- **H-P3R2 裁定输入**：机制 (b)（风减/分批）成立——回撤全部收窄；机制 (a)（重锚修复逆向选择）在意图层成立（买入意图成交率 ~60% vs P3R1 8.7–17%）、在 m6 门8 口径下不达 95%。两契约级死因修复都不足以翻转信号层门3——与冻结时的诚实预期一致。
- 试验计账：197→205（判定表产出，一次性）；9cc4 记 0 消耗。val（2021–2024）零消费、未进入任何计算。

## 纪律声明

- 引擎字节零改动（前后哈希一致）；`docs/`、`configs/`、`src/` 零修改；`data/raw` 只读；2025+ 零接触（所有帧 assert_frozen 通过）；不做 git、不联网。
- 临时文件全部在运行目录 `tmp/`（runner、冒烟产物、smoke_reconciliation.json）；失败与中间记录全部留档（logs/runner.log 含三次全窗运行的完整轨迹与两次归因修正前的记录）。
- 试验台账、假说登记簿、主计划未更新，留主对话独立复算与双签。
