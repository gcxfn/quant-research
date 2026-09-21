# 扩展宇宙探索轮 v1 判定（exp-20260919-expanded-universe-v1，EU-A0 锚 + EU-01..10）

- 运行 `20260919T161737-exp-universe-v1-3eu1`；引擎 v1.2 sha256:16 `84a2443ac28fe1b8`（运行前后一致，v2 prereg §5 pin 零改动）；预登记 sha256:16 `9c753e474e66b96b`（已冻结，运行中零修改）；继承条款 v2 预登记 sha256:16 `4ced8ce1db44cef3`（其再继承 v1 sha256:16 `266a1b850373a6f7`）。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（71 个月末，2020-12-31 丢弃）；val 2021–2024 零消费（用户 2026-09-19 裁定暂不消费，继续 dev）。
- EU-A0 回归锚：intents/fills/events/daily_equity/clips_final 与 v3 run（20260919T110500-hybrid-v3-r3ld）R3-06 产物逐帧 polars `.equals()` 全部一致（5/5 PASS）+ net_cagr 1e-12 一致 + parquet 字节比对（见 manifest eu_a0_regression）；锚失败即中止整轮零结论；锚不重判。
- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。

## 〇、规格接缝状态（未静默裁定）

- **S2（腿-轮动键冲突）**：RESOLVED by the frozen v2 spec: leg symbols are removed from the ranking universe (ROT-03R/ROT-04: 7 members, ROT-05: 6 members); runner verifies disjointness at frame construction and that no entry/exit ever names a leg symbol; no duplicate first-decision points occurred
- **S4（ParkW vs 25% 上限）**：RESOLVED by the frozen v2 spec: multi-leg structures with every symbol <= 25% (park 40-60%); runner hard-checks that no leg intent is cap-voided (a cap-void would contradict the frozen structure and abort)
- **S1（park_init 源标记，v1 遗留未决）**：engine requires date-typed source_signal; pinned 'park_init' literal is un-runnable; resolved to the park decision date 2015-01-30 (no K impact: buys have no fallback); carried over from v1 unresolved; pending adjudication
- **S3（ROT 基准映射，v1 遗留未决）**：ROT arms have no stock exposure path; benchmarked against the family anchor B1m/C05 (T200-40, rate_only) + B3prime[T200-40]; carried over from v1 unresolved; pending adjudication

## 一、判定表（八门，门 8 = v3 + 8v2/R16 对照列 + 目标列）

| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | 单票max权重 | 门8v3 最终交付(市价+限价自成交/武装) | 8v2对照 | R16原口径(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| EU-A0 | +11.06% | +0.60% | +10.46pp | 5/6 | -16.22% | 1.59 | 27.5% | n/a(0 armed) | n/a(0 armed) | 33.0% | Y | 8 | - | **dev_pass** |
| EU-01 | +5.65% | +0.60% | +5.05pp | 3/6 | -27.29% | 3.19 | 27.1% | 1+0/1=100.0% | 1/1=100.0% | 55.3% | N | 6 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m | eliminated |
| EU-02 | +7.12% | +0.60% | +6.52pp | 5/6 | -18.50% | 3.52 | 26.3% | n/a(0 armed) | n/a(0 armed) | 55.4% | N | 8 | - | **dev_pass** |
| EU-03 | +6.41% | +0.60% | +5.81pp | 4/6 | -16.41% | 3.52 | 26.7% | n/a(0 armed) | n/a(0 armed) | 56.7% | N | 7 | 3_advantage_years_ge_5_of_6 | eliminated |
| EU-04 | +6.42% | +0.60% | +5.82pp | 5/6 | -21.60% | 3.38 | 26.9% | 2+0/2=100.0% | 2/2=100.0% | 60.6% | N | 7 | 4_mdd_le_20pct_and_le_B1m | eliminated |
| EU-05 | +6.89% | +0.60% | +6.29pp | 5/6 | -21.14% | 2.90 | 26.4% | 2+0/2=100.0% | 2/2=100.0% | 63.1% | N | 7 | 4_mdd_le_20pct_and_le_B1m | eliminated |
| EU-06 | +4.13% | +0.60% | +3.54pp | 4/6 | -19.65% | 3.21 | 26.9% | 2+0/2=100.0% | 2/2=100.0% | 58.4% | N | 7 | 3_advantage_years_ge_5_of_6 | eliminated |
| EU-07 | +8.07% | +0.60% | +7.47pp | 5/6 | -18.88% | 2.18 | 26.1% | 1+0/1=100.0% | 1/1=100.0% | 44.4% | N | 8 | - | **dev_pass** |
| EU-08 | +8.55% | +0.60% | +7.95pp | 5/6 | -18.68% | 3.16 | 26.3% | 1+0/1=100.0% | 1/1=100.0% | 51.5% | N | 8 | - | **dev_pass** |
| EU-09 | +6.63% | +0.60% | +6.03pp | 5/6 | -14.61% | 2.98 | 26.8% | 2+0/2=100.0% | 2/2=100.0% | 48.0% | N | 8 | - | **dev_pass** |
| EU-10 | +7.88% | +0.60% | +7.28pp | 5/6 | -18.51% | 3.33 | 26.3% | 1+0/1=100.0% | 1/1=100.0% | 54.6% | N | 8 | - | **dev_pass** |

### 一句话死因

- **EU-01**: advantage years<5/6 (gate 3); maxDD breach (gate 4)（腿 sh.511010 15%; sh.518880 25%，park 40%）
- **EU-03**: advantage years<5/6 (gate 3)（腿 sh.511010 15%; sh.518880 25%，park 40%）
- **EU-04**: maxDD breach (gate 4)（腿 sh.511010 15%; sh.518880 25%，park 40%）
- **EU-05**: maxDD breach (gate 4)（腿 sh.511010 15%; sh.518880 25%，park 40%）
- **EU-06**: advantage years<5/6 (gate 3)（腿 sh.511010 15%; sh.518880 25%，park 40%）

## 二、强制披露（v2 prereg §4 + v1 §8-10 继承项）

- **EU-A0**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 37.8%；滑点(vs源信号收盘) 买 +0.237% 卖 +0.028%；分年 {"2015": 0.0508, "2016": 0.0944, "2017": 0.1164, "2018": -0.0693, "2019": 0.2014, "2020": 0.3057}；终止 {"expiry": 2, "override_same_name": 136, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 9.1%/max 11.3% (目标 15%); sh.518880: 实际均重 21.7%/max 25.4% (目标 25%)
- **EU-01**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 47.8%；滑点(vs源信号收盘) 买 +0.419% 卖 +0.396%；分年 {"2015": -0.035, "2016": -0.0382, "2017": 0.2058, "2018": -0.2308, "2019": 0.2123, "2020": 0.3315}；终止 {"expiry": 2, "override_same_name": 125, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2019-01-02) 归因: 股票腿 146.8% / ETF腿 2.2% / 现金 -49.0%；sh.511010: 实际均重 11.0%/max 13.6% (目标 15%); sh.518880: 实际均重 22.6%/max 27.1% (目标 25%)；vs EU-A0: 轮动成交 +78 单, 现金不足作废 60 次（锚 33 次）
- **EU-02**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 50.3%；滑点(vs源信号收盘) 买 +0.602% 卖 +0.010%；分年 {"2015": -0.0325, "2016": 0.035, "2017": 0.1275, "2018": -0.1235, "2019": 0.1881, "2020": 0.2841}；终止 {"expiry": 2, "override_same_name": 123, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-25) 归因: 股票腿 268.8% / ETF腿 -172.6% / 现金 3.8%；sh.511010: 实际均重 10.2%/max 12.0% (目标 15%); sh.518880: 实际均重 22.9%/max 25.8% (目标 25%)；vs EU-A0: 轮动成交 +74 单, 现金不足作废 40 次（锚 33 次）
- **EU-03**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 48.5%；滑点(vs源信号收盘) 买 +0.566% 卖 -0.006%；分年 {"2015": -0.0192, "2016": 0.0126, "2017": 0.1275, "2018": -0.1026, "2019": 0.1237, "2020": 0.2845}；终止 {"expiry": 2, "override_same_name": 121, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-26) 归因: 股票腿 293.1% / ETF腿 -194.0% / 现金 0.9%；sh.511010: 实际均重 10.4%/max 11.8% (目标 15%); sh.518880: 实际均重 23.0%/max 26.7% (目标 25%)；vs EU-A0: 轮动成交 +78 单, 现金不足作废 49 次（锚 33 次）
- **EU-04**: 门8v3 最终交付 2+0/2=100.0%；限价直接成交率 47.6%；滑点(vs源信号收盘) 买 +0.406% 卖 +0.299%；分年 {"2015": -0.033, "2016": 0.029, "2017": 0.1276, "2018": -0.1488, "2019": 0.1987, "2020": 0.268}；终止 {"expiry": 2, "override_same_name": 125, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-26) 归因: 股票腿 195.7% / ETF腿 -108.7% / 现金 13.0%；sh.511010: 实际均重 10.4%/max 12.4% (目标 15%); sh.518880: 实际均重 23.0%/max 26.9% (目标 25%)；vs EU-A0: 轮动成交 +115 单, 现金不足作废 57 次（锚 33 次）
- **EU-05**: 门8v3 最终交付 2+0/2=100.0%；限价直接成交率 46.4%；滑点(vs源信号收盘) 买 +0.585% 卖 +0.187%；分年 {"2015": -0.0342, "2016": 0.0393, "2017": 0.1277, "2018": -0.1507, "2019": 0.232, "2020": 0.2586}；终止 {"expiry": 2, "override_same_name": 127, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-26) 归因: 股票腿 179.5% / ETF腿 -90.0% / 现金 10.5%；sh.511010: 实际均重 10.3%/max 12.3% (目标 15%); sh.518880: 实际均重 22.8%/max 26.4% (目标 25%)；vs EU-A0: 轮动成交 +142 单, 现金不足作废 66 次（锚 33 次）
- **EU-06**: 门8v3 最终交付 2+0/2=100.0%；限价直接成交率 47.1%；滑点(vs源信号收盘) 买 +0.590% 卖 +0.145%；分年 {"2015": 0.003, "2016": -0.0821, "2017": 0.1138, "2018": -0.1433, "2019": 0.211, "2020": 0.1981}；终止 {"expiry": 2, "override_same_name": 121, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-26) 归因: 股票腿 171.4% / ETF腿 -79.3% / 现金 8.0%；sh.511010: 实际均重 11.1%/max 13.4% (目标 15%); sh.518880: 实际均重 23.1%/max 26.9% (目标 25%)；vs EU-A0: 轮动成交 +90 单, 现金不足作废 57 次（锚 33 次）
- **EU-07**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 43.1%；滑点(vs源信号收盘) 买 +0.401% 卖 +0.045%；分年 {"2015": -0.0287, "2016": 0.0554, "2017": 0.1757, "2018": -0.1069, "2019": 0.1341, "2020": 0.3039}；终止 {"expiry": 2, "override_same_name": 127, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-25) 归因: 股票腿 270.7% / ETF腿 -167.5% / 现金 -3.1%；sh.511010: 实际均重 9.9%/max 11.3% (目标 15%); sh.518880: 实际均重 22.5%/max 26.1% (目标 25%)；vs EU-A0: 轮动成交 +26 单, 现金不足作废 29 次（锚 33 次）
- **EU-08**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 45.8%；滑点(vs源信号收盘) 买 +0.896% 卖 +0.083%；分年 {"2015": -0.003, "2016": 0.019, "2017": 0.1804, "2018": -0.1242, "2019": 0.1954, "2020": 0.3015}；终止 {"expiry": 2, "override_same_name": 131, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-26) 归因: 股票腿 273.6% / ETF腿 -170.4% / 现金 -3.3%；sh.511010: 实际均重 9.8%/max 11.8% (目标 15%); sh.518880: 实际均重 22.5%/max 25.9% (目标 25%)；vs EU-A0: 轮动成交 +68 单, 现金不足作废 53 次（锚 33 次）
- **EU-09**: 门8v3 最终交付 2+0/2=100.0%；限价直接成交率 45.1%；滑点(vs源信号收盘) 买 +0.619% 卖 +0.105%；分年 {"2015": -0.0162, "2016": 0.031, "2017": 0.104, "2018": -0.073, "2019": 0.1627, "2020": 0.2172}；终止 {"expiry": 2, "override_same_name": 126, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-24→2018-12-26) 归因: 股票腿 287.7% / ETF腿 -215.2% / 现金 27.5%；sh.511010: 实际均重 10.2%/max 11.7% (目标 15%); sh.518880: 实际均重 22.8%/max 26.8% (目标 25%)；vs EU-A0: 轮动成交 +40 单, 现金不足作废 38 次（锚 33 次）
- **EU-10**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 48.4%；滑点(vs源信号收盘) 买 +0.782% 卖 +0.011%；分年 {"2015": -0.0002, "2016": 0.0342, "2017": 0.1273, "2018": -0.1237, "2019": 0.1879, "2020": 0.2979}；终止 {"expiry": 2, "override_same_name": 126, "cap_void": 0, "suspension_abandon": 0}；DD窗(2018-01-23→2018-12-25) 归因: 股票腿 268.2% / ETF腿 -171.6% / 现金 3.4%；sh.511010: 实际均重 10.0%/max 11.6% (目标 15%); sh.518880: 实际均重 22.8%/max 25.9% (目标 25%)；vs EU-A0: 轮动成交 +76 单, 现金不足作废 48 次（锚 33 次）

### 配置矩阵（EU 预登记 §2 冻结）

| 配置 | 宇宙 | n | top_n×权重 | 回看 | 净CAGR | maxDD | 超额 | 优势年 | 入册资格 | 失败门 |
|---|---|---|---|---|---|---|---|---|---|---|
| EU-A0 | UNI6 | 6 | 3×0.20 | 6m | +11.06% | -16.22% | +10.46pp | 5/6 | Y | - |
| EU-01 | EQ28 | 28 | 3×0.20 | 6m | +5.65% | -27.29% | +5.05pp | 3/6 | N | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m |
| EU-02 | EQ35 | 35 | 3×0.20 | 6m | +7.12% | -18.50% | +6.52pp | 5/6 | N | - |
| EU-03 | EQ43 | 43 | 3×0.20 | 6m | +6.41% | -16.41% | +5.81pp | 4/6 | N | 3_advantage_years_ge_5_of_6 |
| EU-04 | EQ35 | 35 | 4×0.15 | 6m | +6.42% | -21.60% | +5.82pp | 5/6 | N | 4_mdd_le_20pct_and_le_B1m |
| EU-05 | EQ35 | 35 | 5×0.12 | 6m | +6.89% | -21.14% | +6.29pp | 5/6 | N | 4_mdd_le_20pct_and_le_B1m |
| EU-06 | EQ35 | 35 | 3×0.20 | 4m | +4.13% | -19.65% | +3.54pp | 4/6 | N | 3_advantage_years_ge_5_of_6 |
| EU-07 | EQ35 | 35 | 3×0.20 | 9m | +8.07% | -18.88% | +7.47pp | 5/6 | N | - |
| EU-08 | SEC20 | 20 | 3×0.20 | 6m | +8.55% | -18.68% | +7.95pp | 5/6 | N | - |
| EU-09 | BROAD15 | 15 | 3×0.20 | 6m | +6.63% | -14.61% | +6.03pp | 5/6 | N | - |
| EU-10 | SECXB25 | 25 | 3×0.20 | 6m | +7.88% | -18.51% | +7.28pp | 5/6 | N | - |
- 入册资格 = dev 八门全过 且 净年化 ≥10%（二次过手协议）；入册 ≠ 冠军，Phase B 前不改 R3-05/R3-06 在库地位。
- UNI6 成员包含于所有探索宇宙（扩展而非替换）；腿恒 sh.511010@15% + sh.518880@25%；单槽权重 ≤25%。
- 引擎现金零收益（无货基收益建模），相对现实略悲观（保守方向）。

### EU45 面板 dev 分红事件披露（EU 预登记 §4-3）

- 45 符号面板共 35 个 dev 分红事件（其中锚面板 9 符号的 18 事件为其子集，已逐帧断言一致）。
- 相对 v3 面板的新增成员事件计数：{"sh.510180": 4, "sh.510330": 3, "sh.510900": 1, "sh.511880": 6, "sz.159920": 1, "sz.160706": 2}。
- 引擎 v1.3 防误分类护栏已武装（分红隐含收益率 >10% 硬报错，fail-closed，不修数据绕过）；事件明细见 outputs/dividend_events45.csv。

### 159934 冻结披露

- sz.159934（黄金ETF）dev 内 preclose 无跳变微偏离 [{"symbol": "sz.159934", "date": "2020-02-26", "preclose": 3.614, "prev_close": 3.622, "rel_diff": -0.002208724461623457, "factor_ratio": 1.0}]——因子 ratio=1.0（无份额变动），按 v2 预登记 §2 不建模，仅披露（与 v1 159915 同类）；分红规则扫描 0 事件。

## 三、EU-A0 回归锚（= v3 R3-06 复刻）

- 5/5 帧 `.equals()` 一致：{"intents": true, "fills": true, "events": true, "daily": true, "clips_final": true, "net_cagr_matches_v3_metrics": true, "parquet_bytes_equal_vs_v3": true, "parquet_bytes_detail": {"intents.parquet": true, "fills.parquet": true, "events.parquet": true, "daily_equity.parquet": true, "clips_final.parquet": true}}
- 引擎 stats：intents 206，orders 172，filled 65。

## 四、运行身份

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee、stk_limit agg 3c53abf3b0c39b42、etf-daily 目录聚合 75777221a8b33502、fund_adj 聚合 b06242469db048a0（=etf manifest 声明值）、trade_cal 聚合 aac75421cd89d9fc。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 时间划分：dev 2015-01-05..2020-12-31；val 未消费；判定只对 dev。
- 试验计账：本轮 +10 探索试验（EU 预登记 §2/§5：252→262），锚 EU-A0 不计试验；谱系 v1 205→214、v2 214→222、v3 222→229、val 229→241、rob 241→252（如台账有异以台账为准）。
- 判定：expanded-universe exploration round v1 (EU prereg sec 0/5): all 12 config results reported at once, no mid-run selection, no champion change, R3-05/R3-06 in-library status unchanged; roster eligibility (second-pass protocol = dev 8 gates AND net CAGR >= 10%) -> EU-A0; 6/11 pass all 8 dev gates; ALL results exploration-grade; trials +10 (252->262, anchor not counted); val not consumed

## 五、关键发现与口径说明

- **本轮性质**：扩展宇宙探索轮 v1（二次过手协议 Phase A 线 1）；全部 dev 窗（2015–2020）；全部结果 exploration-grade；不产生冠军声明、不写可实盘、不改 R3-05/R3-06 在库地位；试验 252→262。
- **锚口径**：EU-A0 = v3 R3-06 逐字（含 v3 原面板与未使用的 sz.159934）；五帧产物与 v3 run R3-06 `.equals()` 逐帧一致 + net_cagr 1e-12 + parquet 字节比对；失败即中止整轮零结论。
- **corporate_actions 不传**：预登记 §1 排除后各宇宙 dev 窗零拆分事件（筛查事件表核验）；dividend_events 沿 v3 抽取规则应用于 45 符号面板；引擎 v1.3 防误分类护栏 fail-closed。
- **B1(m) dev 基准**：现算沿用已验证端口（r16.simulate_r16 fractional、rate-only bands、T200-40），对 R16 metrics 1e-9 校验，已知 dev 值（净年化 +0.60%/maxDD −39.82%）pin 通过。
- **门 8 v3 口径逐字**：最终交付 ≥99% + 期末滞留=0 硬断言；8v2 与 R16 原口径仅作对照列。
- **货币 ETF 语义（预登记 §4-4）**：货币近零动量在全市场弱势时占据 top 槽 = EU-03 防御停靠假设本身的检验；其分红/净值累计口径经因子调整后与其他成员同规则。
- **指数重复风险（预登记 §6-3）**：U-EQ28/35/43 内同指数多基金，动量排名并列时同信号多槽集中；U-SECXB25 为对照设计。
- **ETF 数据质量**：锚 9 符号面板 preclose 零空值、因子全覆盖、分红 18 事件全落带；EU45 面板断言（preclose 空值/日历并集/因子覆盖）全部通过（计数与明细见披露与 outputs/）。