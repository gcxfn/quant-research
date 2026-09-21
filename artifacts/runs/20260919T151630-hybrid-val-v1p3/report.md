# 混合族 v3 判定（exp-20260919-hybrid-family-v3，降债阶梯）

- 运行 `20260919T151630-hybrid-val-v1p3`；引擎 v1.2 sha256:16 `84a2443ac28fe1b8`（运行前后一致，v2 prereg §5 pin 零改动）；预登记 sha256:16 `8e3c534fad39e3e7`（已冻结，运行中零修改）；继承条款 v2 预登记 sha256:16 `4ced8ce1db44cef3`（其再继承 v1 sha256:16 `266a1b850373a6f7`）。
- 窗口 val 2021-01-04..2024-12-31，信号 2021-01-29..2024-11-29（47 个月末，2020-12-31 丢弃）；val 2021–2024 零消费（用户 2026-09-19 裁定暂不消费，继续 dev）。
- R3-A0 回归锚：intents/fills/events/daily_equity/clips_final 与 v2 ROT-05 输出逐帧 polars `.equals()` 全部一致（5/5 PASS），判定链有效；R3-A0 判定以 v2 为准，不重判。
- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。

## 〇、规格接缝状态（未静默裁定）

- **S2（腿-轮动键冲突）**：RESOLVED by the frozen v2 spec: leg symbols are removed from the ranking universe (ROT-03R/ROT-04: 7 members, ROT-05: 6 members); runner verifies disjointness at frame construction and that no entry/exit ever names a leg symbol; no duplicate first-decision points occurred
- **S4（ParkW vs 25% 上限）**：RESOLVED by the frozen v2 spec: multi-leg structures with every symbol <= 25% (park 40-60%); runner hard-checks that no leg intent is cap-voided (a cap-void would contradict the frozen structure and abort)
- **S1（park_init 源标记，v1 遗留未决）**：engine requires date-typed source_signal; pinned 'park_init' literal is un-runnable; resolved to the park decision date 2015-01-30 (no K impact: buys have no fallback); carried over from v1 unresolved; pending adjudication
- **S3（ROT 基准映射，v1 遗留未决）**：ROT arms have no stock exposure path; benchmarked against the family anchor B1m/C05 (T200-40, rate_only) + B3prime[T200-40]; carried over from v1 unresolved; pending adjudication

## 一、判定表（八门，门 8 = v3 + 8v2/R16 对照列 + 目标列）

| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | 单票max权重 | 门8v3 最终交付(市价+限价自成交/武装) | 8v2对照 | R16原口径(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R3-A0 | +0.30% | -0.15% | +0.45pp | 2/4 | -18.45% | 2.75 | 29.0% | n/a(0 armed) | n/a(0 armed) | 52.1% | N | 7 | 1_excess_ge_1pp | eliminated |
| R3-05 | +2.33% | -0.15% | +2.47pp | 2/4 | -14.59% | 2.02 | 29.0% | 0+1/1=100.0% | 0/1=0.0% | 67.3% | N | 8 | - | **dev_pass** |
| R3-06 | +1.77% | -0.15% | +1.92pp | 2/4 | -15.14% | 2.41 | 27.0% | 1+0/1=100.0% | 1/1=100.0% | 53.2% | N | 8 | - | **dev_pass** |

### 一句话死因

- **R3-A0**: excess<+1pp (val gate 1)（腿 sh.511010 25%; sh.518880 25%，park 50%）

## 二、强制披露（v2 prereg §4 + v1 §8-10 继承项）

- **R3-A0**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 46.2%；滑点(vs源信号收盘) 买 +1.886% 卖 -0.233%；分年 {"2021": 0.0274, "2022": -0.169, "2023": 0.0742, "2024": 0.1036}；终止 {"expiry": 2, "override_same_name": 68, "cap_void": 0, "suspension_abandon": 0}；DD窗(2022-01-04→2023-06-08) 归因: 股票腿 0.0% / ETF腿 -69.0% / 现金 169.0%；sh.511010: 实际均重 20.9%/max 25.0% (目标 25%); sh.518880: 实际均重 23.9%/max 26.9% (目标 25%)
- **R3-05**: 门8v3 最终交付 0+1/1=100.0%；限价自成交 sh.518880 2022-03-01；限价直接成交率 11.4%；滑点(vs源信号收盘) 买 +1.703% 卖 -0.333%；分年 {"2021": 0.0042, "2022": -0.122, "2023": 0.0855, "2024": 0.1451}；终止 {"expiry": 5, "override_same_name": 30, "cap_void": 0, "suspension_abandon": 0}；DD窗(2021-11-22→2022-11-03) 归因: 股票腿 0.0% / ETF腿 60.6% / 现金 39.4%；sh.518880: 实际均重 23.8%/max 27.4% (目标 25%)；vs R3-A0: 轮动成交 -11 单, 现金不足作废 166 次（锚 21 次）
- **R3-06**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 32.0%；滑点(vs源信号收盘) 买 +1.154% 卖 -0.161%；分年 {"2021": 0.0067, "2022": -0.1333, "2023": 0.0588, "2024": 0.161}；终止 {"expiry": 2, "override_same_name": 70, "cap_void": 0, "suspension_abandon": 0}；DD窗(2021-11-22→2022-11-03) 归因: 股票腿 0.0% / ETF腿 -20.9% / 现金 120.9%；sh.511010: 实际均重 9.5%/max 15.0% (目标 15%); sh.518880: 实际均重 23.9%/max 27.0% (目标 25%)；vs R3-A0: 轮动成交 +5 单, 现金不足作废 50 次（锚 21 次）

### 债权重阶梯单调性（v3 预登记 §4-3）

| 配置 | 债权重 | top_n | 净CAGR | maxDD | 超额 | 优势年 | 失败门 |
|---|---|---|---|---|---|---|---|
| R3-A0 | 25% | 2 | +0.30% | -18.45% | +0.45pp | 2/4 | 1_excess_ge_1pp |
| R3-05 | 0% | 3 | +2.33% | -14.59% | +2.47pp | 2/4 | - |
| R3-06 | 15% | 3 | +1.77% | -15.14% | +1.92pp | 2/4 | - |
- 轨迹若非单调 = 结构敏感而非线性机会成本；R3-A0 即 0.25 基点。
- 引擎现金零收益：R3-01..04 腾出的债权重闲置为现金，相对现实（货基收益）略悲观，保守方向如实呈现。

### 159934 冻结披露

- sz.159934（黄金ETF）dev 内 preclose 无跳变微偏离 []——因子 ratio=1.0（无份额变动），按 v2 预登记 §2 不建模，仅披露（与 v1 159915 同类）；分红规则扫描 0 事件。

## 三、R3-A0 回归锚（= v2 ROT-05 复刻）

- 5/5 帧 `.equals()` 一致：{"intents": false, "fills": false, "events": false, "daily": false, "clips_final": false, "net_cagr_matches_v2_metrics": false}
- 引擎 stats：intents 146，orders 160，filled 74。

## 四、运行身份

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee、stk_limit agg 3c53abf3b0c39b42、etf-daily 目录聚合 75777221a8b33502、fund_adj 聚合 b06242469db048a0（=etf manifest 声明值）、trade_cal 聚合 aac75421cd89d9fc。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 时间划分：dev 2021-01-04..2024-12-31；val 未消费；判定只对 dev。
- 试验计账：本族判定计 7 项（7 配置族）；谱系 v1 205→214、v2 214→222，v3 判定后 222→229（如台账有异以台账为准）。
- 判定：2/3 configs pass all dev gates but none reaches the 10% goal column -> bookkeep and CONTINUE dev exploration per the user's 2026-09-19 ruling (val held); val not consumed

## 五、关键发现与口径说明

- **降债阶梯口径**：债权重 0.25→0，腾出的权重或闲置为现金（R3-01..04）或给第三轮动槽（R3-05 top3×25%、R3-06 top3×20%）；引擎现金零收益（无货基收益建模），现金变体相对现实略悲观（保守方向，不修补）。
- **门 8 v3 口径与 v2 逐字**：最终交付 =（市价兜底成交 + 武装后限价自身成交）/兜底武装单数 ≥99%，期末滞留=0 硬断言；8v2 与 R16 原口径仅作对照列。
- **停止条款（用户 2026-09-19 裁定编码）**：过门且 ≥10% → 停止并报告（目标列首达）；过门但 <10% → 记账后继续 dev；全淘汰 → ROT 支线暂停。val 保持未消费。
- **v2 已判配置不重跑不重判**：H2-01/03/04、ROT-05 的 dev 判定以 v2 为准；R3-A0 仅为回归锚。
- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、分红 18 事件全落带（明细见 outputs/dividend_events.csv）；159934 的 2020-02-26 微偏离见冻结披露（v3 不使用该符号）。