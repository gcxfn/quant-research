# 混合族 v2 判定（exp-20260919-hybrid-family-v2）

- 运行 `20260920T031746-engine-v141-anchors-9de3`；引擎 v1.2 sha256:16 `c5c073035d63c59d`（运行前后一致，v2 prereg §5 pin 零改动）；预登记 sha256:16 `4ced8ce1db44cef3`（已冻结，运行中零修改）；继承条款 v1 预登记 sha256:16 `266a1b850373a6f7`。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（71 个月末，2020-12-31 丢弃）；val 2021–2024 零消费。
- H2-A0 回归锚：fills/events/daily_equity/clips_final 与 P3R2 C05 逐帧 polars `.equals()` 全部一致（4/4 PASS），判定链有效。
- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。

## 〇、规格接缝状态（未静默裁定）

- **S2（腿-轮动键冲突）**：RESOLVED by the frozen v2 spec: leg symbols are removed from the ranking universe (ROT-03R/ROT-04: 7 members, ROT-05: 6 members); runner verifies disjointness at frame construction and that no entry/exit ever names a leg symbol; no duplicate first-decision points occurred
- **S4（ParkW vs 25% 上限）**：RESOLVED by the frozen v2 spec: multi-leg structures with every symbol <= 25% (park 40-60%); runner hard-checks that no leg intent is cap-voided (a cap-void would contradict the frozen structure and abort)
- **S1（park_init 源标记，v1 遗留未决）**：engine requires date-typed source_signal; pinned 'park_init' literal is un-runnable; resolved to the park decision date 2015-01-30 (no K impact: buys have no fallback); carried over from v1 unresolved; pending adjudication
- **S3（ROT 基准映射，v1 遗留未决）**：ROT arms have no stock exposure path; benchmarked against the family anchor B1m/C05 (T200-40, rate_only) + B3prime[T200-40]; carried over from v1 unresolved; pending adjudication

## 一、判定表（八门，门 8 = v3 + 8v2/R16 对照列 + 目标列）

| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | 单票max权重 | 门8v3 最终交付(市价+限价自成交/武装) | 8v2对照 | R16原口径(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H2-A0 | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20% | 1.59 | 11.1% | 6+1/7=100.0% | 6/7=85.7% | 53.3% | N | 6 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m | eliminated |

### 一句话死因

- **H2-A0**: advantage years<5/6 (gate 3); maxDD breach (gate 4)

## 二、强制披露（v2 prereg §4 + v1 §8-10 继承项）

- **H2-A0**: 门8v3 最终交付 6+1/7=100.0%；限价自成交 sh.600518 2019-06-12；限价直接成交率 3.9%；滑点(vs源信号收盘) 买 -0.593% 卖 +0.394%；分年 {"2015": -0.0129, "2016": -0.0457, "2017": 0.1139, "2018": -0.0771, "2019": 0.129, "2020": 0.149}；终止 {"expiry": 136, "override_same_name": 515, "cap_void": 0, "suspension_abandon": 1}；DD窗(2015-06-08→2016-02-29) 归因: 股票腿 39.3% / ETF腿 0.0% / 现金 60.7%；

### 159934 冻结披露

- sz.159934（黄金ETF）dev 内 preclose 无跳变微偏离 [{"symbol": "sz.159934", "date": "2020-02-26", "preclose": 3.614, "prev_close": 3.622, "rel_diff": -0.002208724461623457, "factor_ratio": 1.0}]——因子 ratio=1.0（无份额变动），按 v2 预登记 §2 不建模，仅披露（与 v1 159915 同类）；分红规则扫描 0 事件。

## 三、H2-A0 回归锚

- 4/4 帧 `.equals()` 一致：{"fills": true, "events": true, "daily": true, "clips_final": true, "net_cagr_matches_p3r2_metrics": true}
- 引擎 stats：intents 1395，orders 18827，filled 737。

## 四、运行身份

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee、stk_limit agg 3c53abf3b0c39b42、etf-daily 目录聚合 75777221a8b33502、fund_adj 聚合 b06242469db048a0（=etf manifest 声明值）、trade_cal 聚合 aac75421cd89d9fc。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 时间划分：dev 2015-01-05..2020-12-31；val 未消费；判定只对 dev。
- 试验计账：本族判定计 1 项（8 配置族）；谱系 205→214 已含 v1，v2 判定后 214→222（如台账有异以台账为准）。
- 判定：no config passed all dev gates (0/1); hybrid line PAUSED per the v2 stop clause (direction re-evaluation is a separate user decision); val not consumed

## 五、关键发现与口径说明

- **门 8 v3 口径**：最终交付 =（市价兜底成交 + 武装后限价自身成交）/兜底武装单数 ≥99%，期末武装后滞留持仓=0 硬断言；两分子分列于判定表，8v2 与 R16 原口径仅作对照列。v1 的 sh.600518（2019-06，8 时段跌停顺延后限价自成交、无滞留）在本口径下重建精确（armed=7=6+1，残差 0）。v1 已判配置不因 8v3 重判（HYB-05 门 4 失败与门 8 无关）。
- **S4 结构修复生效**：v1 的 HYB-01..04 因 ParkW>25% 首发射即被上限作废（退化=C05+现金）；v2 多腿结构逐符号 ≤25%，腿真实建仓（本表各配置腿实际均重 vs 目标列可对照），现金竞争代价体现在 insufficient-cash 作废与股票 displacement（vs H2-A0 差值列）。
- **park 50/60 的代价**：H2-01（50%）/H2-03（60%）相对 H2-A0 的股票成交差、成交率差与入场延迟见判定披露二；若 displacement 侵蚀了腿收益带来的超额，以净数字为准如实呈现。
- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、分红 18 事件全落带（明细见 outputs/dividend_events.csv）；159934 的 2020-02-26 微偏离见冻结披露。