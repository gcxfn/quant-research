# 混合族稳健性验证轮（exp-20260919-hybrid-robustness，邻域描述性）

- 运行 `20260919T151047-hybrid-rob-05bf`；引擎 v1.2 sha256:16 `84a2443ac28fe1b8`（运行前后一致，v2 prereg §5 pin 零改动）；预登记 sha256:16 `ad308f0a107d0257`（已冻结，运行中零修改）；继承条款 v2 预登记 sha256:16 `4ced8ce1db44cef3`（其再继承 v1 sha256:16 `266a1b850373a6f7`）。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（71 个月末，2020-12-31 丢弃）；val 2021–2024 零消费（用户 2026-09-19 裁定暂不消费，继续 dev）。
- RB-A0 回归锚：intents/fills/events/daily_equity/clips_final 与 v3 run（20260919T110500-hybrid-v3-r3ld）R3-06 产物逐帧 polars `.equals()` 全部一致（5/5 PASS）+ net_cagr 1e-12 一致；判定链有效；锚不重判。
- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。

## 〇、规格接缝状态（未静默裁定）

- **S2（腿-轮动键冲突）**：RESOLVED by the frozen v2 spec: leg symbols are removed from the ranking universe (ROT-03R/ROT-04: 7 members, ROT-05: 6 members); runner verifies disjointness at frame construction and that no entry/exit ever names a leg symbol; no duplicate first-decision points occurred
- **S4（ParkW vs 25% 上限）**：RESOLVED by the frozen v2 spec: multi-leg structures with every symbol <= 25% (park 40-60%); runner hard-checks that no leg intent is cap-voided (a cap-void would contradict the frozen structure and abort)
- **S1（park_init 源标记，v1 遗留未决）**：engine requires date-typed source_signal; pinned 'park_init' literal is un-runnable; resolved to the park decision date 2015-01-30 (no K impact: buys have no fallback); carried over from v1 unresolved; pending adjudication
- **S3（ROT 基准映射，v1 遗留未决）**：ROT arms have no stock exposure path; benchmarked against the family anchor B1m/C05 (T200-40, rate_only) + B3prime[T200-40]; carried over from v1 unresolved; pending adjudication

## 一、判定表（八门，门 8 = v3 + 8v2/R16 对照列 + 目标列）

| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | 单票max权重 | 门8v3 最终交付(市价+限价自成交/武装) | 8v2对照 | R16原口径(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RB-A0 | +11.06% | +0.60% | +10.46pp | 5/6 | -16.22% | 1.59 | 27.5% | n/a(0 armed) | n/a(0 armed) | 33.0% | Y | 8 | - | **dev_pass** |
| RB-01 | +8.23% | +0.60% | +7.63pp | 5/6 | -16.06% | 1.79 | 26.9% | n/a(0 armed) | n/a(0 armed) | 38.9% | N | 8 | - | **dev_pass** |
| RB-02 | +8.03% | +0.60% | +7.43pp | 5/6 | -16.17% | 1.77 | 27.9% | 1+0/1=100.0% | 1/1=100.0% | 36.4% | N | 8 | - | **dev_pass** |
| RB-03 | +2.00% | +0.60% | +1.40pp | 3/6 | -4.46% | 0.36 | 27.5% | n/a(0 armed) | n/a(0 armed) | 24.5% | N | 6 | 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6 | eliminated |
| RB-04 | +8.34% | +0.60% | +7.74pp | 5/6 | -14.21% | 1.21 | 26.5% | n/a(0 armed) | n/a(0 armed) | 34.3% | N | 8 | - | **dev_pass** |
| RB-05 | +8.04% | +0.60% | +7.44pp | 5/6 | -19.21% | 2.00 | 34.1% | n/a(0 armed) | n/a(0 armed) | 53.8% | N | 8 | - | **dev_pass** |
| RB-06 | +6.59% | +0.60% | +5.99pp | 5/6 | -17.11% | 1.74 | 36.3% | n/a(0 armed) | n/a(0 armed) | 54.1% | N | 8 | - | **dev_pass** |
| RB-07 | +1.72% | +0.60% | +1.12pp | 3/6 | -4.40% | 0.26 | 27.6% | 2+0/2=100.0% | 2/2=100.0% | 37.6% | N | 6 | 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6 | eliminated |
| RB-08 | +7.72% | +0.60% | +7.12pp | 5/6 | -17.16% | 1.53 | 28.1% | n/a(0 armed) | n/a(0 armed) | 49.6% | N | 8 | - | **dev_pass** |
| RB-09 | +7.40% | +0.60% | +6.80pp | 5/6 | -16.65% | 1.64 | 29.8% | n/a(0 armed) | n/a(0 armed) | 34.3% | N | 8 | - | **dev_pass** |
| RB-10 | +8.99% | +0.60% | +8.39pp | 5/6 | -14.88% | 1.62 | 26.8% | n/a(0 armed) | n/a(0 armed) | 29.5% | N | 8 | - | **dev_pass** |
| RB-11 | +8.41% | +0.60% | +7.81pp | 5/6 | -16.25% | 1.40 | 29.6% | n/a(0 armed) | n/a(0 armed) | 32.3% | N | 8 | - | **dev_pass** |

### 一句话死因

- **RB-03**: excess<+2pp (gate 2); advantage years<5/6 (gate 3)（腿 sh.511010 15%; sh.518880 25%，park 40%）
- **RB-07**: excess<+2pp (gate 2); advantage years<5/6 (gate 3)（腿 sh.518880 25%，park 25%）

## 二、强制披露（v2 prereg §4 + v1 §8-10 继承项）

- **RB-A0**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 37.8%；滑点(vs源信号收盘) 买 +0.237% 卖 +0.028%；分年 {"2015": 0.0508, "2016": 0.0944, "2017": 0.1164, "2018": -0.0693, "2019": 0.2014, "2020": 0.3057}；终止 {"expiry": 2, "override_same_name": 136, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 9.1%/max 11.3% (目标 15%); sh.518880: 实际均重 21.7%/max 25.4% (目标 25%)
- **RB-01**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 38.8%；滑点(vs源信号收盘) 买 +0.230% 卖 -0.387%；分年 {"2015": 0.0117, "2016": -0.0014, "2017": 0.1, "2018": -0.0643, "2019": 0.2359, "2020": 0.2496}；终止 {"expiry": 2, "override_same_name": 130, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 10.1%/max 12.2% (目标 15%); sh.518880: 实际均重 22.3%/max 26.2% (目标 25%)；vs RB-A0: 轮动成交 +10 单, 现金不足作废 35 次（锚 33 次）
- **RB-02**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 38.7%；滑点(vs源信号收盘) 买 +0.371% 卖 +0.247%；分年 {"2015": -0.0287, "2016": 0.1074, "2017": 0.1095, "2018": -0.0529, "2019": 0.1589, "2020": 0.2125}；终止 {"expiry": 2, "override_same_name": 129, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.7% / 现金 -0.7%；sh.511010: 实际均重 9.6%/max 11.4% (目标 15%); sh.518880: 实际均重 22.5%/max 26.3% (目标 25%)；vs RB-A0: 轮动成交 +0 单, 现金不足作废 20 次（锚 33 次）
- **RB-03**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 2.7%；滑点(vs源信号收盘) 买 +0.865% 卖 -1.137%；分年 {"2015": -0.0287, "2016": 0.0417, "2017": 0.0051, "2018": 0.0175, "2019": 0.0506, "2020": 0.0353}；终止 {"expiry": 2, "override_same_name": 121, "cap_void": 31, "suspension_abandon": 0}；DD窗(2020-08-07→2020-11-30) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 10.8%/max 11.3% (目标 15%); sh.518880: 实际均重 23.8%/max 27.5% (目标 25%)；vs RB-A0: 轮动成交 -61 单, 现金不足作废 0 次（锚 33 次）
- **RB-04**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 34.6%；滑点(vs源信号收盘) 买 +0.756% 卖 -0.530%；分年 {"2015": -0.0136, "2016": 0.0652, "2017": 0.1151, "2018": -0.0787, "2019": 0.2077, "2020": 0.2393}；终止 {"expiry": 2, "override_same_name": 132, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 9.9%/max 12.0% (目标 15%); sh.518880: 实际均重 22.2%/max 26.5% (目标 25%)；vs RB-A0: 轮动成交 -3 单, 现金不足作废 21 次（锚 33 次）
- **RB-05**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 19.8%；滑点(vs源信号收盘) 买 -0.183% 卖 -0.141%；分年 {"2015": 0.0161, "2016": -0.0199, "2017": 0.1259, "2018": -0.0708, "2019": 0.2365, "2020": 0.2333}；终止 {"expiry": 5, "override_same_name": 62, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.518880: 实际均重 21.9%/max 26.5% (目标 25%)；vs RB-A0: 轮动成交 +3 单, 现金不足作废 121 次（锚 33 次）
- **RB-06**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 15.9%；滑点(vs源信号收盘) 买 +0.454% 卖 -0.130%；分年 {"2015": -0.0342, "2016": 0.1376, "2017": 0.1367, "2018": -0.0712, "2019": 0.1246, "2020": 0.1234}；终止 {"expiry": 5, "override_same_name": 57, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 102.3% / 现金 -2.3%；sh.518880: 实际均重 22.2%/max 26.1% (目标 25%)；vs RB-A0: 轮动成交 -11 单, 现金不足作废 129 次（锚 33 次）
- **RB-07**: 门8v3 最终交付 2+0/2=100.0%；限价直接成交率 2.7%；滑点(vs源信号收盘) 买 +1.731% 卖 -1.176%；分年 {"2015": -0.0342, "2016": 0.0411, "2017": 0.0064, "2018": 0.0104, "2019": 0.0475, "2020": 0.0339}；终止 {"expiry": 1, "override_same_name": 51, "cap_void": 31, "suspension_abandon": 0}；DD窗(2020-08-07→2020-11-30) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.518880: 实际均重 23.8%/max 27.6% (目标 25%)；vs RB-A0: 轮动成交 -61 单, 现金不足作废 0 次（锚 33 次）
- **RB-08**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 17.0%；滑点(vs源信号收盘) 买 +0.463% 卖 -0.771%；分年 {"2015": -0.0153, "2016": 0.0662, "2017": 0.1132, "2018": -0.1102, "2019": 0.2251, "2020": 0.2249}；终止 {"expiry": 4, "override_same_name": 63, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.518880: 实际均重 22.1%/max 26.5% (目标 25%)；vs RB-A0: 轮动成交 -12 单, 现金不足作废 85 次（锚 33 次）
- **RB-09**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 37.8%；滑点(vs源信号收盘) 买 +0.518% 卖 -0.422%；分年 {"2015": -0.0085, "2016": 0.0655, "2017": 0.1053, "2018": -0.1102, "2019": 0.1808, "2020": 0.2495}；终止 {"expiry": 2, "override_same_name": 128, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-24→2018-12-26) 归因: 股票腿 0.0% / ETF腿 93.8% / 现金 6.2%；sh.511010: 实际均重 10.1%/max 12.3% (目标 15%); sh.518880: 实际均重 22.2%/max 26.5% (目标 25%)；vs RB-A0: 轮动成交 -8 单, 现金不足作废 25 次（锚 33 次）
- **RB-10**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 35.3%；滑点(vs源信号收盘) 买 +0.367% 卖 -0.727%；分年 {"2015": -0.0016, "2016": 0.0226, "2017": 0.1471, "2018": -0.0888, "2019": 0.1905, "2020": 0.3183}；终止 {"expiry": 2, "override_same_name": 132, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-24→2018-12-26) 归因: 股票腿 0.0% / ETF腿 82.5% / 现金 17.5%；sh.511010: 实际均重 9.9%/max 12.4% (目标 15%); sh.518880: 实际均重 22.0%/max 26.5% (目标 25%)；vs RB-A0: 轮动成交 -16 单, 现金不足作废 19 次（锚 33 次）
- **RB-11**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 37.7%；滑点(vs源信号收盘) 买 +0.434% 卖 -0.309%；分年 {"2015": -0.0157, "2016": 0.0802, "2017": 0.1146, "2018": -0.0447, "2019": 0.2233, "2020": 0.1712}；终止 {"expiry": 2, "override_same_name": 132, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 9.6%/max 11.7% (目标 15%); sh.518880: 实际均重 22.1%/max 25.7% (目标 25%)；vs RB-A0: 轮动成交 -8 单, 现金不足作废 22 次（锚 33 次）

### 邻域分布统计（预登记 §2 冻结口径；描述性，非判定）

- 邻域 n=11；八门全过比例 82%；超额落在锚 ±1pp 内比例 0%；maxDD≤20% 比例 100%。
- 逐门通过数（11 邻域中）：{"1_net_cagr_gt_0": 11, "2_excess_vs_B1m_ge_2pp": 9, "3_advantage_years_ge_5_of_6": 9, "4_mdd_le_20pct_and_le_B1m": 11, "5_one_side_turnover_le_6": 11, "6_single_name_weight_le_40pct": 11, "7_vs_B3prime_plus_1pp": 11, "8v3_final_delivery_ge_99pct": 11}

| 配置 | 净CAGR | 超额 | Δ超额vs锚 | maxDD | 优势年 | 失败门 |
|---|---|---|---|---|---|---|
| RB-01 | +8.23% | +7.63pp | -2.83pp | -16.06% | 5/6 | - |
| RB-02 | +8.03% | +7.43pp | -3.03pp | -16.17% | 5/6 | - |
| RB-03 | +2.00% | +1.40pp | -9.07pp | -4.46% | 3/6 | 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6 |
| RB-04 | +8.34% | +7.74pp | -2.72pp | -14.21% | 5/6 | - |
| RB-05 | +8.04% | +7.44pp | -3.02pp | -19.21% | 5/6 | - |
| RB-06 | +6.59% | +5.99pp | -4.47pp | -17.11% | 5/6 | - |
| RB-07 | +1.72% | +1.12pp | -9.35pp | -4.40% | 3/6 | 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6 |
| RB-08 | +7.72% | +7.12pp | -3.35pp | -17.16% | 5/6 | - |
| RB-09 | +7.40% | +6.80pp | -3.67pp | -16.65% | 5/6 | - |
| RB-10 | +8.99% | +8.39pp | -2.07pp | -14.88% | 5/6 | - |
| RB-11 | +8.41% | +7.81pp | -2.65pp | -16.25% | 5/6 | - |
- 全部为 exploration-grade（dev-only、post-val、元过拟合折扣）；不产生过/灭判定，不改变 R3-05/R3-06 在库地位。

### 159934 冻结披露

- sz.159934（黄金ETF）dev 内 preclose 无跳变微偏离 [{"symbol": "sz.159934", "date": "2020-02-26", "preclose": 3.614, "prev_close": 3.622, "rel_diff": -0.002208724461623457, "factor_ratio": 1.0}]——因子 ratio=1.0（无份额变动），按 v2 预登记 §2 不建模，仅披露（与 v1 159915 同类）；分红规则扫描 0 事件。

## 三、RB-A0 回归锚（= v3 R3-06 复刻）

- 5/5 帧 `.equals()` 一致：{"intents": true, "fills": true, "events": true, "daily": true, "clips_final": true, "net_cagr_matches_v3_metrics": true}
- 引擎 stats：intents 206，orders 172，filled 65。

## 四、运行身份

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee、stk_limit agg 3c53abf3b0c39b42、etf-daily 目录聚合 75777221a8b33502、fund_adj 聚合 b06242469db048a0（=etf manifest 声明值）、trade_cal 聚合 aac75421cd89d9fc。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 时间划分：dev 2015-01-05..2020-12-31；val 未消费；判定只对 dev。
- 试验计账：本轮 +11 邻域试验（预登记 §4：241→252），锚 RB-A0 不计；谱系 v1 205→214、v2 214→222、v3 222→229（如台账有异以台账为准）。
- 判定：robustness round (prereg exp-20260919-hybrid-robustness sec 0/2/4): anchor RB-A0 regression PASS; 10/12 configs pass all 8 dev gates (descriptive count only); ALL neighborhood results are exploration-grade (dev-only, post-val, meta-overfitting discount) -- NO selection, NO champion change, NO ledger elimination semantics; val not consumed

## 五、关键发现与口径说明

- **本轮性质**：R3-05/R3-06 邻域稳健性验证（robustness, NOT selection）；全部 dev 窗（2015–2020），无新样本外证据；邻域结果一律 exploration-grade（dev-only、post-val、元过拟合折扣），不产生新冠军、不改变 R3-05/R3-06 在库地位。
- **锚口径**：RB-A0 = R3-06 逐字；5 帧产物（intents/fills/events/daily_equity/clips_final）与 v3 run R3-06 逐字节 `.equals()` + net_cagr 1e-12 一致；锚失败即中止零结论（未触发则记 PASS）。
- **门 8 v3 口径逐字保留**：最终交付 =（市价兜底成交 + 武装后限价自身成交）/兜底武装单数 ≥99%，期末滞留=0 硬断言；8v2 与 R16 原口径仅作对照列。
- **试验计账（预登记 §4）**：+11 邻域试验（241→252），锚不计；val 保持未消费。
- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、分红 18 事件全落带（明细见 outputs/dividend_events.csv）；159934 的 2020-02-26 微偏离见冻结披露（本轮不使用该符号）。