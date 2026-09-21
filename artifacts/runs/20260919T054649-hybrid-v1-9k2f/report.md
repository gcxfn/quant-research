# 混合族 v1 判定（exp-20260919-hybrid-family-v1）

- 运行 `20260919T054649-hybrid-v1-9k2f`；引擎 v1.2 sha256:16 `ceb7be6414280e4c`（运行前后一致，prereg §6 冻结版）；预登记 sha256:16 `266a1b850373a6f7`（已冻结，运行中零修改）。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（71 个月末，2020-12-31 丢弃）；val 2021–2024 零消费。
- HYB-00 回归锚：fills/events/daily_equity/clips_final 与 P3R2 C05 逐帧 polars `.equals()` 全部一致（4/4 PASS），判定链有效。
- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。

## 〇、规格接缝与阻塞（未静默裁定）

- **S2 ROT-03 阻塞**：ROT-03 pinned ranking universe (8 members) includes the 50% leg sh.511010; in months where 511010 enters/exits top-2 the rotation intent and the leg monthly reduce share the same (symbol, first decision point), which _validate_intents hard-rejects (m5-b violated). Materialized months: entries 2015-08-31/2016-01-29/2018-04-27/2018-12-28; exits 2015-10-30/2016-02-29/2018-07-31/2019-02-28. NOT run; resolution (exclude leg from ranking / skip colliding leg sells / merge) requires user adjudication
- **S4 ParkW vs 25% 上限**：frozen ParkW grid {30,40,50}% exceeds the equally frozen engine single-name 25% construction cap (contract sec 8.5: cap applies to ETF legs identically); HYB-01..04 park buys are voided+terminated at first emission (cap_single_name) -- configs ran as pinned and the engine outcome is reported verbatim; any ParkW > 25% needs a re-spec (multi-tranche / cap-aware) by adjudication
- **S1 park_init 源标记**：engine requires date-typed source_signal; pinned 'park_init' literal is un-runnable; resolved to the park decision date 2015-01-30 (no K impact: buys have no fallback); pending adjudication
- **S3 ROT 基准映射**：ROT arms have no stock exposure path; benchmarked against the family anchor B1m/C05 (T200-40, rate_only) + B3prime[T200-40]; pending adjudication

## 一、判定表（八门 v2 + 目标列）

| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | 单票max权重 | 门8v2 K3交付 | R16原执行率(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HYB-00 | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20% | 1.59 | 11.1% | 6/7=85.7% | 53.3% | N | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8v2_k3_fallback_delivery_ge_99pct | eliminated |
| HYB-01 | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20% | 1.59 | 11.1% | 6/7=85.7% | 50.7% | N | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8v2_k3_fallback_delivery_ge_99pct | eliminated |
| HYB-02 | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20% | 1.59 | 11.1% | 6/7=85.7% | 50.7% | N | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8v2_k3_fallback_delivery_ge_99pct | eliminated |
| HYB-03 | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20% | 1.59 | 11.1% | 6/7=85.7% | 50.7% | N | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8v2_k3_fallback_delivery_ge_99pct | eliminated |
| HYB-04 | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20% | 1.59 | 11.1% | 6/7=85.7% | 50.7% | N | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8v2_k3_fallback_delivery_ge_99pct | eliminated |
| HYB-05 | +6.43% | +0.60% | +5.83pp | 5/6 | -20.00% | 1.52 | 21.4% | 6/7=85.7% | 48.4% | N | 6 | 4_mdd_le_20pct_and_le_B1m, 8v2_k3_fallback_delivery_ge_99pct | eliminated |
| ROT-01 | +7.87% | +0.60% | +7.27pp | 4/6 | -16.60% | 2.73 | 36.3% | 2/2=100.0% | 93.8% | N | 7 | 3_advantage_years_ge_5_of_6 | eliminated |
| ROT-02 | +2.71% | +0.60% | +2.11pp | 2/6 | -16.13% | 3.42 | 32.6% | 2/2=100.0% | 92.6% | N | 7 | 3_advantage_years_ge_5_of_6 | eliminated |
| ROT-03 | - | - | - | - | - | - | - | - | - | - | - | 规格接缝S2阻塞 | blocked |

### 一句话死因

- **HYB-00**: advantage years<5/6 (gate 3); maxDD breach (gate 4); K3 delivery<99% (gate 8v2)
- **HYB-01**: advantage years<5/6 (gate 3); maxDD breach (gate 4); K3 delivery<99% (gate 8v2)（腿 sh.511010 ParkW=40%；上限作废终止 1）
- **HYB-02**: advantage years<5/6 (gate 3); maxDD breach (gate 4); K3 delivery<99% (gate 8v2)（腿 sh.518880 ParkW=40%；上限作废终止 1）
- **HYB-03**: advantage years<5/6 (gate 3); maxDD breach (gate 4); K3 delivery<99% (gate 8v2)（腿 sh.518880 ParkW=50%；上限作废终止 1）
- **HYB-04**: advantage years<5/6 (gate 3); maxDD breach (gate 4); K3 delivery<99% (gate 8v2)（腿 sh.518880 ParkW=30%；上限作废终止 1）
- **HYB-05**: maxDD breach (gate 4); K3 delivery<99% (gate 8v2)（腿 sh.511010 ParkW=20%; sh.518880 ParkW=20%；上限作废终止 0）
- **ROT-01**: advantage years<5/6 (gate 3)
- **ROT-02**: advantage years<5/6 (gate 3)

## 二、强制披露（prereg §8-10 逐项）

- **HYB-00**: 限价直接成交率 3.9%；K3 触发(armed/风险意图) 7/621，交付 6/7；滑点(vs源信号收盘) 买 -0.593% 卖 +0.394%；分年 {"2015": -0.0129, "2016": -0.0457, "2017": 0.1139, "2018": -0.0771, "2019": 0.129, "2020": 0.149}；终止 {"expiry": 136, "override_same_name": 515, "cap_void": 0, "suspension_abandon": 1}；DD窗(2015-06-08→2016-02-29) 归因: 股票腿 39.3% / ETF腿 0.0% / 现金 60.7%；
- **HYB-01**: 限价直接成交率 3.9%；K3 触发(armed/风险意图) 7/691，交付 6/7；滑点(vs源信号收盘) 买 -0.593% 卖 +0.394%；分年 {"2015": -0.0129, "2016": -0.0457, "2017": 0.1139, "2018": -0.0771, "2019": 0.129, "2020": 0.149}；终止 {"expiry": 137, "override_same_name": 584, "cap_void": 1, "suspension_abandon": 1}；DD窗(2015-06-08→2016-02-29) 归因: 股票腿 39.3% / ETF腿 0.0% / 现金 60.7%；sh.511010: mean 0.0%/max 0.0% (ParkW 40%)；vs HYB-00: 股票成交 +0 单, 首成交延迟 +0 日, 现金不足作废 0
- **HYB-02**: 限价直接成交率 3.9%；K3 触发(armed/风险意图) 7/691，交付 6/7；滑点(vs源信号收盘) 买 -0.593% 卖 +0.394%；分年 {"2015": -0.0129, "2016": -0.0457, "2017": 0.1139, "2018": -0.0771, "2019": 0.129, "2020": 0.149}；终止 {"expiry": 137, "override_same_name": 584, "cap_void": 1, "suspension_abandon": 1}；DD窗(2015-06-08→2016-02-29) 归因: 股票腿 39.3% / ETF腿 0.0% / 现金 60.7%；sh.518880: mean 0.0%/max 0.0% (ParkW 40%)；vs HYB-00: 股票成交 +0 单, 首成交延迟 +0 日, 现金不足作废 0
- **HYB-03**: 限价直接成交率 3.9%；K3 触发(armed/风险意图) 7/691，交付 6/7；滑点(vs源信号收盘) 买 -0.593% 卖 +0.394%；分年 {"2015": -0.0129, "2016": -0.0457, "2017": 0.1139, "2018": -0.0771, "2019": 0.129, "2020": 0.149}；终止 {"expiry": 137, "override_same_name": 584, "cap_void": 1, "suspension_abandon": 1}；DD窗(2015-06-08→2016-02-29) 归因: 股票腿 39.3% / ETF腿 0.0% / 现金 60.7%；sh.518880: mean 0.0%/max 0.0% (ParkW 50%)；vs HYB-00: 股票成交 +0 单, 首成交延迟 +0 日, 现金不足作废 0
- **HYB-04**: 限价直接成交率 3.9%；K3 触发(armed/风险意图) 7/691，交付 6/7；滑点(vs源信号收盘) 买 -0.593% 卖 +0.394%；分年 {"2015": -0.0129, "2016": -0.0457, "2017": 0.1139, "2018": -0.0771, "2019": 0.129, "2020": 0.149}；终止 {"expiry": 137, "override_same_name": 584, "cap_void": 1, "suspension_abandon": 1}；DD窗(2015-06-08→2016-02-29) 归因: 股票腿 39.3% / ETF腿 0.0% / 现金 60.7%；sh.518880: mean 0.0%/max 0.0% (ParkW 30%)；vs HYB-00: 股票成交 +0 单, 首成交延迟 +0 日, 现金不足作废 0
- **HYB-05**: 限价直接成交率 3.9%；K3 触发(armed/风险意图) 7/761，交付 6/7；滑点(vs源信号收盘) 买 -0.501% 卖 +0.295%；分年 {"2015": -0.036, "2016": -0.0153, "2017": 0.1036, "2018": -0.0503, "2019": 0.1814, "2020": 0.2356}；终止 {"expiry": 149, "override_same_name": 643, "cap_void": 0, "suspension_abandon": 1}；DD窗(2015-06-08→2016-01-28) 归因: 股票腿 80.3% / ETF腿 -1.5% / 现金 21.2%；sh.511010: mean 16.0%/max 18.3% (ParkW 20%); sh.518880: mean 18.2%/max 21.4% (ParkW 20%)；vs HYB-00: 股票成交 -16 单, 首成交延迟 +0 日, 现金不足作废 677
- **ROT-01**: 限价直接成交率 17.0%；K3 触发(armed/风险意图) 2/40，交付 2/2；滑点(vs源信号收盘) 买 +0.665% 卖 +0.300%；分年 {"2015": 0.0079, "2016": 0.152, "2017": 0.1025, "2018": -0.0688, "2019": 0.0816, "2020": 0.2208}；终止 {"expiry": 4, "override_same_name": 1, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-24→2020-03-23) 归因: 股票腿 0.0% / ETF腿 87.5% / 现金 12.5%；
- **ROT-02**: 限价直接成交率 16.5%；K3 触发(armed/风险意图) 2/68，交付 2/2；滑点(vs源信号收盘) 买 +0.693% 卖 +0.321%；分年 {"2015": 0.0321, "2016": -0.0385, "2017": 0.0954, "2018": -0.0965, "2019": 0.1108, "2020": 0.076}；终止 {"expiry": 8, "override_same_name": 2, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 96.7% / 现金 3.3%；

## 三、HYB-00 回归锚

- 4/4 帧 `.equals()` 一致：{"fills": true, "events": true, "daily": true, "clips_final": true, "net_cagr_matches_p3r2_metrics": true}
- 引擎 stats：intents 1395，orders 18827，filled 737。

## 四、运行身份

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee、stk_limit agg 3c53abf3b0c39b42、etf-daily 目录聚合 75777221a8b33502、fund_adj 聚合 b06242469db048a0（=etf manifest 声明值）、trade_cal 聚合 aac75421cd89d9fc。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 时间划分：dev 2015-01-05..2020-12-31；val 未消费；判定只对 dev。
- 试验计账：本族判定计 1 项（9 配置，其中 8 实跑、ROT-03 构建期阻塞）；谱系累计 205（P3R2 后）+1 = 206（如台账有异以台账为准）。
- 判定：no config passed all dev gates (0/8); val not consumed

## 五、关键发现与口径说明

- **门 8v2 口径发现**：各 HYB 配置唯一的 armed 未交付兜底是 sh.600518（2019-06）：武装后连续 8 个时段开盘跌停顺延，2019-06-12 由其**限价单自身成交**完成风险离场——按冻结口径（兜底市价成交单/兜底武装单）计为未交付，6/7=85.7%<99%，门按冻结执行；'顺延期间限价离场是否计入交付'属判据变更，须用户裁定。
- **HYB-05 门 4 差距**：maxDD −20.0027%，仅超 20% 绝对线 0.3bp（≤B1(m) 腿 −39.82% 通过）。
- **HYB-01..04 退化**：ParkW>25% 腿买入在首次发射即触单票 25% 构造上限被整体作废并终止意图（接缝 S4），fills 与 daily_equity 经核验与 HYB-00 逐字节一致——四配置的引擎结果即 C05+闲置现金。
- **成交率口径**：限价直接成交率为逐发射订单口径（意图在每个决策点重挂直到终态），R16 对照列为逐意图口径，两者不可互比，均已披露。
- **腿实际权重 vs ParkW**：仅 HYB-05 有效成交（两腿 mean 16.0%/18.2% vs ParkW 20%，现金竞争 677 次股票买单现金不足作废、股票成交 −16 单；腿资金次日 pm 回笼的代价如实呈现）；HYB-01..04 腿权重恒 0。
- **ETF 腿数据质量**：宇宙成员 dev 面板 11,696 行、preclose 零空值、volume≤0 零行、因子全覆盖、分红 18 事件全落带（明细见 outputs/dividend_events.csv）。