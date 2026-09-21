# P3R2 判定运行独立复核（双签复审）

- 复核对象：`artifacts/runs/20260919T030640-p3r2-dev-ad9e`（exp-20260918-p3r2-band-v1-readjudication）
- 复核人：独立复核代理（本 run `20260919T030712-p3r2-review-8b2c`）；只读审计，未改动被审 run 的任何文件
- 判据权威：`docs/research/exp-20260918-p3r2-band-v1-readjudication-prereg.md`（§3 八门、§4 映射、§5 披露、§9 修订 1–5）；配置 `configs/experiments/p3r2-band-v1-readjudication.json`
- 方法：全部数字从 `outputs/*.parquet` + 权威源文件**独立重算**（脚本与本目录 `tmp/` 下 JSON 证据：`recompute_metrics.py`、`recompute_gate6_weight.py`、`ledger_and_gate6.py`、`recomputed_metrics.json`、`gate8_lifecycle.json`、`gate6_weights.json`、`ledger_and_gate6.json`、`positions_replay.json`、`reconciliation.json`），与 `outputs/metrics_and_gates.json`、`report.md`、`findings.md` 逐位比对。

## 结论（先行）

**判决：APPROVE**。0/8 dev_pass 判定成立，全部门级数字独立重算逐位一致（仅换手均值存在 ≤1e-15 相对量的浮点求和噪声），账本守恒、成交与费用公式、T+1、整手、公司行动、意图层对账全部通过；B1(m)/B3′ 为 R16 原值逐字节引用未被重算；val 零消费；9cc4 记 0 消耗、其约定 A 数字未作任何判定依据。发现 0 项 CRITICAL、0 项 MAJOR、5 项 MINOR（见文末）。

## 1. 八配置指标独立重算（任务 1）

口径：净 CAGR = 期末/期初权益的几何年化，年化天数约定 = **日历日/365.25**（`src/quant/research/etf_rotation.py::cagr`，窗口 2015-01-05..2020-12-31）；最大回撤 = 日收盘权益峰谷比，不涉年化。逐年收益按日历年链条（首年自窗口首值起）。

| 配置 | 净CAGR（重算/运行） | 最大回撤（重算/运行） | 优势年 | 最大单边换手 | 费用合计(元) | 逐位比对 |
|---|---|---|---|---|---|---|
| C01 | +0.6811% / +0.6811% | -21.6474% / -21.6474% | 2/6 | 1.4868 | 3,895.54 | 一致 |
| C02 | -4.9130% / -4.9130% | -38.5421% / -38.5421% | 2/6 | 2.4816 | 4,441.54 | 一致 |
| C03 | -0.8727% / -0.8727% | -45.4464% / -45.4464% | 2/6 | 1.8028 | 3,589.53 | 一致 |
| C04 | -4.3531% / -4.3531% | -55.1456% / -55.1456% | 2/6 | 2.7030 | 4,283.46 | 一致 |
| C05 | +3.8832% / +3.8832% | -21.1966% / -21.1966% | 4/6 | 1.5870 | 4,907.75 | 一致 |
| C06 | -4.9564% / -4.9564% | -39.5860% / -39.5860% | 2/6 | 2.3270 | 5,171.40 | 一致 |
| C07 | -0.6165% / -0.6165% | -42.9248% / -42.9248% | 3/6 | 1.7699 | 4,337.38 | 一致 |
| C08 | -5.6786% / -5.6786% | -55.3044% / -55.3044% | 1/6 | 2.3683 | 4,943.06 | 一致 |

- 逐年收益、优势年列表、超额、总收益：8/8 配置**逐位相等**（`year_returns_match/excess_match/advantage_years_match` 全 True）。
- 换手（年内买入名义 / 该年日均权益）：逐分量与运行值差 ≤1e-10（权益均值）与 ≤1e-15 相对（比值），为浮点求和顺序噪声，非约定差异；年化约定本身与运行一致，报告差异为零，无需约定归因。
- 年化约定敏感性（如改 244 交易日/365 日）：C05 +3.8832% → +3.8805%/+3.8805%，C01 +0.6811% → +0.6806%，量级 ~0.003pp，不改变任何门判定。
- 费用分解（自 fills 重算）：买 `commission = max(万1×名义, 5)`、卖含分段印花（全部 dev 成交早于 2023-08-28 边界 → 卖 0.1%，ETF 免）；8 配置共 5,202 笔成交**逐笔公式复算 0 违例**。vs P3R1 费用 Δ 与报告表逐项一致（C01 +1,053 … C08 +1,098，8/8）。

## 2. 八门判定逻辑核对（任务 2）

独立重判（门 6/8 见 §3/§4 的独立重算）：

| 配置 | 门1 CAGR>0 | 门2 超额≥2pp | 门3 优势年≥5/6 | 门4 DD≤20%且≤B1(m) | 门5 换手≤6 | 门6 权重≤40% | 门7 ≥B3′+1pp | 门8 成交率≥95% | dev_pass | 运行判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| C01 | P(+0.68%) | F(+0.08pp) | F(2/6) | F(-21.65%>20%; ≤B1(m)✓) | P | P(9.4%) | P | F(58.4%) | 0 | eliminated(4/8过) |
| C02 | F | F(-5.51pp) | F(2/6) | F(-38.54%) | P | P(9.0%) | F | F(57.7%) | 0 | eliminated(2/8) |
| C03 | F | F(-2.73pp) | F(2/6) | F(-45.45%) | P | P(8.6%) | F | F(56.6%) | 0 | eliminated(2/8) |
| C04 | F | F(-6.21pp) | F(2/6) | F(-55.15%) | P | P(12.3%) | F | F(58.3%) | 0 | eliminated(2/8) |
| C05 | P(+3.88%) | P(+3.28pp) | F(4/6) | F(-21.20%) | P | P(11.1%) | P | F(53.3%) | 0 | eliminated(5/8) |
| C06 | F | F(-5.56pp) | F(2/6) | F(-39.59%) | P | P(9.0%) | F | F(49.3%) | 0 | eliminated(2/8) |
| C07 | F | F(-2.47pp) | F(3/6) | F(-42.92%) | P | P(11.6%) | F | F(51.6%) | 0 | eliminated(2/8) |
| C08 | F | F(-7.53pp) | F(1/6) | F(-55.30%) | P | P(6.7%) | F | F(50.9%) | 0 | eliminated(2/8) |

与运行的 failed_gates/verdict **8/8 完全一致**；"≤B1(m)" 分句 8/8 满足（最贴者 C04 -55.15% vs B1(m) -55.60%），门 4 仅倒在 20% 硬线——与报告叙述一致。

**B1(m)/B3′ 引用核验**：运行 metrics 的 `b1m_net_cagr/b1m_max_drawdown/b1m_net_return_by_year` 与 `artifacts/runs/20260918T083650-p2r16-trend-dispersion-afab466f/metrics.json`（T200-40: 0.0059905923579064435 / -0.3982378364862026；FIX75: 0.018551675073019247 / -0.5559615161856944）**逐字节相等**；B3′（-0.01991746425477723 / -0.0035871088487231862）同源逐字节相等。基准为引用、未被重算，符合"基准不换契约"。

## 3. 成交与账本守恒抽查（任务 3，C05 深查 + 全配置扩展）

- **权益恒等**：`settled_cash + pending_am_to_pm + pending_next_day + positions_value == equity`，C05 全部 1,462 个交易日（非抽样 3 日）**0 违例**。
- **现金重放**：自 200,000 元起，逐日重放全部 737 笔成交净现金流 + 140 笔分红现金 + 6 个拆股事件（按事件日期、开盘先于成交的顺序），与引擎每日现金三桶合计逐日比对（容差 2 分）：**0 违例**。
- **持仓重放**：以成交+事件拆股重放的每日持股 × 官方收盘（tradestatus≠0、停牌桥接取 last close ≤ d）逐日比对 `positions_value`：**8 配置全窗口 0 违例**；期末股数账与 `*_clips_final.parquet` 逐 symbol 相等 **8/8**（C05 31 clips，174,299.40 元与末日持仓市值精确相等）。
- **费用公式**：买 5 元下限/万1、卖分段印花逐笔复算 0 违例（§1）；C05 费用合计 4,907.75 元（佣金+印花）与披露一致。
- **T+1**：按 clip 批次账（买入=取得日；拆股：原股保留原取得日、新增股取得日=拆股日，镜像引擎"added shares acquired"语义）重放，卖出 ≤ 当日早前可卖批次合计：**8/8 配置 0 违例**（首轮自查的 12-19 起"违例"均系我方未计拆股的假阳性，修正后清零）。
- **整手**：买单 100% 为 100 股整数倍（8/8）；零股卖出 1–6 笔/配置，全部为公司行动产生的零股余量（合法）。
- **权益为正**：8 配置全程最小权益 113,181.78（C08）~ 179,723.90（C05），与 findings "113k–180k" 一致。

## 4. 意图层对账（任务 4）

- `activated == n_intents == 意图帧行数`：8/8（C01 909、C02 1096、C03 860、C04 1033、C05 1395、C06 1662、C07 1277、C08 1533）。
- `orders_generated − k3_executed == 订单事件行数 == 唯一 order_id 数`：8/8（如 C01 7819−8=7811、C05 18827−6=18821）。
- 意图总数恒等：`帧行数 = filled + rule_blocked + 四类终止`：8/8（C05: 737+6+(136+515+0+1)=1395）。
- 生命周期事件独立解析（intent_lifecycle detail）与 `engine_reconciliation` 的 override/expired/cap 合计 8/8 相等（C05: 518/127/0；无生命周期事件的意图 13 个，宿主分类已在 `engine_reason_x_host_class` 逐格披露）。审查任务书中"四类终止+at_target+无锚跳过合计=意图总数"按字面不成立（at_target/no_anchor 为决策点级发射跳过计数，非意图级结果）；成立的意图级恒等式即上式，且逐配置通过。
- 门 8 独立重算：`(filled+rule_blocked)/(filled+rule_blocked+terminated)` 8/8 与运行逐位一致（C05 743/1395=53.2617%）。
- 零发射意图：以运行同款 `src_of` 映射独立复算，8/8 与报告一致（C01 211、C05 229 等）。
- m5-a：pm 无 bar 重挂 0–7/配置；市场级半日日 = {2016-01-07}，8 配置一致，与裁定备注一致。
- K=3：armed 7–9、executed 6–8、跌停顺延 10–24、停牌 0、T+1 锁 0，与披露一致。
- **rescale 映射**：减至目标侧 → 常设风减单（intent=risk，target=exposure/K），at_target 自中性；**加仓侧未映射 = 如实登记**（findings 发现 0 置于结果之前、report §四、metrics `rescale_topup_hole_intents`/`3_mdd_attribution` note）。该空洞不污染门级数字：门级输入全部为引擎实际账本（我方独立重放复核），空洞只使"实际模拟的系统=R16 信号减补仓腿"，其影响方向未断言、且 vs P3R1 的换手/费用/净额 delta 已声明被此空洞混杂——披露如实。若本轮有配置过门，此项将升级为判决性问题；在 0/8 全淘汰下不影响判定。

## 5. 披露完整性（任务 5）

| 项目 | 位置 | 核验 |
|---|---|---|
| §5.1 成交率（买/卖×订单口径）+ vs P3R1 delta | `1_fill_rate.order_session_fill_rate` + `vs_p3r1`（如 C01 买 3.31%、卖 61.0%；Δ -45.8/-11.8pp） | 有，数字一致 |
| §5.2 换手费用 delta（印花分段口径不变） | `2_turnover_fees`（分段印花经逐笔复算确认未变） | 有 |
| §5.3 回撤归因拆分 | `3_mdd_attribution`：机制计数器 + 明示"无 no-rescale 孪生运行，市场路径分量不可分（零试验纪律）" | 有（诚实的部分履行，见 MINOR-2） |
| §5.4 映射差异清单 | `4_mapping_diffs` 11 项（lifecycle/in-loop/重锚节奏/rescale 空洞/skips/sell/半日粒度/ proceeds/expiry/弃 2020-12-31/利润梯） | 有 |
| §5.5 增量（上限作废 0、am/pm 拆分、K=3 明细、门 8 终止单列） | `5_increments`（终四类+`gate8_expired_at_target_noop` 单列 96–121） | 有 |
| 修订 3 在环定价 | `4_mapping_diffs.in_loop_pricing` + report §五 | 有 |
| m5-a 计数 | `m5a_pm_nobar_rehangs` + 市场级半日日清单 | 有，8/8 与裁定一致 |
| m5-c 惰性键 | `m5c_static_stats_lazy_keys`（order_generation/intent_layer 全键） | 有，逐键对账通过 |
| ENGINE-3/修订 4 | `engine3_no_limit_info`：卖作废 C01 2、C02 2、C06 3（缺口日内 2/2/2），无崩溃 | 有，与事件表 `void_no_limit_info` 一致 |
| 9cc4 约定 A 无效诊断未被引用为依据 | findings/report/manifest 仅以"INVALID/废止/未进入"出现，无任何判定或预期引用其数字 | 通过 |

## 6. 身份与纪律（任务 6）

- 引擎前后哈希一致且与冻结值同：现行 `src/quant/backtest/band_engine.py` sha256 = `d7108c0eccdd77ff…970a0d`（我方独立重算），与 manifest start/end 及配置 pin 一致。
- **9 项身份 pin 全部由我方独立重算通过**：engine、r16_config（27f846a7…）、p3r2_config（b49025b4…）、daily（d9a63f4c…，16,344,349 行）、split_factor、dividends、index_000300、halfday manifest（2a414174…，18,486,939 行断言）、stk_limit 聚合（3c53abf3…，2,432 文件、301,278,245 字节，按同规则重算）。
- 输出完整性：manifest 所列 49 个产物文件哈希全部与现文件一致（含 8×5 parquet、metrics_and_gates.json、report.md、tmp/ 产物）。
- leg_log↔membership 8/8：runner §4 以 `r16.buffer_membership` 独立重算 71 信号日 × 8 配置，membership/events 双计数 0 失配（代码核验为硬失败路径；leg_log.parquet 存在，25,993 行）。未重复 R16 信号的全量再推导（该一致性检查本身即以 R16 权威工件为基准的独立复算）。
- m5-b：`(symbol, side, source)` 唯一性强断言在提交前执行，违例即 `_fail` 中止于判定前；日志含 8/8 "m5-b uniqueness PASS"（全窗段）。
- 预算：wall 47.66s / 峰值 RSS 5.08 GB（限 60 min / 8 GB）；日志逐段计时一致。
- 2025+ 零接触：输出最大日期 equity=2020-12-31、fills≤2020-12-22；`assert_frozen` 作用于 daily/halfday 面板；信号窗 2015-01-30..2020-11-30。
- docs/configs/src 零改动：runner 进程仅写运行目录；`docs/research` 预登记 mtime 02:53（先于运行 03:06:40）。窗口内 workspace 另有两处 docs mtime 与两处 data/raw mtime，属并行会话/预登记强制修订，见 MINOR-3。
- manifest `started_at_utc` 记为 1970-01-04T05:12:44（perf_counter 误作 epoch，外观缺陷）；wall_seconds 与日志时间轴一致，不影响任何数字。

## 7. 试验计账（任务 7）

- 197 → 205，本轮一次性计 8（C01–C08 沿 R16 名义）；9cc4（ABORTED）manifest 自记"no defensible gate table exists"，0 消耗，与本运行 manifest note 一致。
- 时序：判定表（§11 metrics & gates）在最终 invocation 内 [44.8s] 产出，产物与 manifest 计账声明同段写盘（[47.6s]），无先声明后产表的矛盾。日志共 7 次进程调用（2 次冒烟、1 次全窗归因崩溃、3 次全窗完成），两次归因修正（A/B）均发生在最终判定消费之前且逐条留痕；被覆盖的中间产物未出运行目录、未被发现任何外部消费。

## 发现分级

**CRITICAL**：无。

**MAJOR**：无。

**MINOR**：
1. **门 8 口径偏离预登记字面**：prereg §3 写"映射执行率口径沿 P3R1"，运行登记为 §7.7-m6 意图级口径（分母=全部意图、R16 跳过腿帧外）。偏差已在 findings 发现 2 说明并补 P3R1 可比辅助口径（66.0%–74.9%，8 配置），两种口径下门 8 全灭，判定不变。
2. **rescale 加仓侧映射空洞**（prereg §4.5 的"增持→加仓 clip"未映射）：结果前如实登记（发现 0 + §四 + 计数器），门级数字为实际账本、未被污染；但 vs P3R1 的换手/费用/净额 delta 被混杂（已声明）。若任何配置过门则此项应升格为判决性问题——本轮 0/8，不影响判决。
3. **运行窗口内 workspace docs mtime 变化**：`docs/plans/p3-band-contract.md`（03:22:17，内容核验为 prereg 修订 2 强制补写的 §7.7-M3"执行主体=引擎意图层"一句，无判据/配置语义变化）与 `docs/DATA_SOURCES.md`（03:15:36，时间上与并行会话 `20260919T021519-etf-pull-74d0` 的 data/raw/baostock etf 批次清单写入 03:13:21 相邻，归属并行会话而非本 run）。"docs/ 零修改"声明对 runner 进程成立、对窗口内 workspace 严格不成立；无 Git 可做内容级归属，留痕为 MINOR。
4. **披露行文小疵**：findings 发现 2"订单级买成交率 1.9–3.3%"实为 C05/C01 两例端点，全配置真实区间 1.54%–3.58%（方向与结论不变）；`zero_emission_intents`（211/229 等，我方 8/8 复算相符）见 report 而未入 metrics_and_gates.json；`void_days.not_penetrated` 仅计买侧（卖侧未穿透计入 K streak 设计），与事件行数差 80–122 属口径而非漏计，易误读。
5. **manifest 外观缺陷**：`started_at_utc` 为 perf_counter 误转 epoch（1970-01-04），wall_seconds/日志时间轴正确；m5-d docstring 挂账维持（与 prereg 一致）。

## 未覆盖范围（如实声明）

- 未重跑引擎（信任 v1.1 双签 APPROVE + 本轮输出级行为验证）；未重新推导 R16 信号池（依赖 runner 内置的 leg_log↔membership_events 独立一致性检查，代码为硬失败路径）；未复核 8 号位以外的 P3R1 侧数字（仅校验费用/回撤/CAGR/成交率四组 delta 引用）。

## 复核后完整性抽查

manifest 所列 49 个产物文件在复核结束时再次哈希校验，与 manifest 及复核开始时一致；本复核仅新增自身运行目录 `20260919T030712-p3r2-review-8b2c/`，被审 run 目录关键文件（manifest.json、outputs/*、report.md、findings.md、logs/runner.log）未被本复核改动。

**判决：APPROVE。**
