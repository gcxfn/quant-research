# F3R2 判定（exp-20260919-factor-round-f3r2，F3 股票腿 × R3-06 底盘）

- 运行 `20260919T194700-f3r2-hybrid-chassis-e7a1`；引擎 v1.3 sha256:16 `84a2443ac28fe1b8`（运行前后一致；corporate_actions=None = v1.2 行为路径）；预登记 sha256:16 `bd56fb5cfb5da4df`（已冻结，运行中零修改）；继承条款 v3 预登记 sha256:16 `8e3c534fad39e3e7`、F3R1 预登记 sha256:16 `858beb421421ccb4`。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（71 个月末，2020-12-31 丢弃）；val 2021–2024 零接触。
- F3R2-A0 回归锚：intents/fills/events/daily_equity/clips_final 与 v3 run R3-06 输出逐帧 polars `.equals()` 全部一致（5/5 PASS），判定链有效；R3-06 的 v3 判定（dev 八门全过 +11.06%）不被重判。
- 全部数字为历史回放，不构成盈利或实盘声称；2025+ 零接触。

## 〇、规格接缝状态（未静默裁定）

- **S2（腿-轮动键冲突）**：RESOLVED by the frozen v2 spec: leg symbols are removed from the ranking universe; F3R2-A0 verifies at frame construction; the F3 stock sleeve universe (R16 stock pool) is disjoint from the 9 ETF symbols by construction
- **S4（ParkW vs 25% 上限）**：RESOLVED by the frozen v2 spec: multi-leg structures with every symbol <= 25% (park 40%); runner hard-checks that no leg intent is cap-voided (a cap-void would contradict the frozen structure and abort)
- **S1（park_init 源标记，v1 遗留未决）**：engine requires date-typed source_signal; pinned 'park_init' literal is un-runnable; resolved to the park decision date 2015-01-30 (no K impact: buys have no fallback); carried over from v1 unresolved; pending adjudication
- **S3（基准映射，v1 遗留未决）**：family anchor B1m/C05 (T200-40, rate_only) + B3prime[T200-40] inherited verbatim; the F3R2 sleeve DOES carry the T200-40 path, so the anchor mapping is closer here than for pure-ROT arms (carried over from v1; pending adjudication)
- **S5（无加仓原语，P3R2 遗留）**：engine has no top-up primitive (P3R2 seam inherited): when e_T rises the sleeve does not add to existing positions; freed cash reaches the market only via new entries and the m7 cash-competition channel

## 一、判定表（八门，门 8 = v3 + 8v2/R16 对照列 + 目标列）

| 配置 | 净CAGR | B1(m) | 超额 | 优势年 | maxDD | 单边换手 | 单票max权重 | 门8v3 最终交付(市价+限价自成交/武装) | 8v2对照 | R16原口径(对照) | 目标≥10% | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F3R2-A0 | +11.06% | +0.60% | +10.46pp | 5/6 | -16.22% | 1.59 | 27.5% | n/a(0 armed) | n/a(0 armed) | 33.0% | Y | 8 | - | **dev_pass** |
| F3R2-EW | +3.77% | +0.60% | +3.17pp | 4/6 | -20.20% | 6.08 | 26.6% | 3+0/3=100.0% | 3/3=100.0% | 71.0% | N | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 5_one_side_turnover_le_6 | eliminated |
| F3R2-ICW | +6.55% | +0.60% | +5.95pp | 6/6 | -33.05% | 4.15 | 27.0% | 1+0/1=100.0% | 1/1=100.0% | 61.2% | N | 7 | 4_mdd_le_20pct_and_le_B1m | eliminated |

### 一句话死因

- **F3R2-EW**: advantage years<5/6 (gate 3); maxDD breach (gate 4); turnover>6 (gate 5)（腿 sh.511010 15%; sh.518880 25%，park 40%）
- **F3R2-ICW**: maxDD breach (gate 4)（腿 sh.511010 15%; sh.518880 25%，park 40%）

## 二、强制披露（v2 prereg §4 + v1 §8-10 继承项）

- **F3R2-A0**: 门8v3 最终交付 n/a(0 armed)；限价直接成交率 37.8%；滑点(vs源信号收盘) 买 +0.237% 卖 +0.028%；分年 {"2015": 0.0508, "2016": 0.0944, "2017": 0.1164, "2018": -0.0693, "2019": 0.2014, "2020": 0.3057}；终止 {"expiry": 2, "override_same_name": 136, "cap_void": 0, "suspension_abandon": 0}；DD窗(2020-02-13→2020-03-23) 归因: 股票腿 0.0% / ETF腿 100.0% / 现金 0.0%；sh.511010: 实际均重 9.1%/max 11.3% (目标 15%); sh.518880: 实际均重 21.7%/max 25.4% (目标 25%)
- **F3R2-EW**: 门8v3 最终交付 3+0/3=100.0%；限价直接成交率 53.8%；滑点(vs源信号收盘) 买 +0.591% 卖 +0.405%；分年 {"2015": 0.1313, "2016": 0.0693, "2017": 0.1144, "2018": -0.0872, "2019": 0.1264, "2020": -0.0998}；终止 {"expiry": 2, "override_same_name": 147, "cap_void": 0, "suspension_abandon": 6}；DD窗(2020-08-18→2020-12-30) 归因: 股票腿 75.4% / ETF腿 15.2% / 现金 9.5%；sh.511010: 实际均重 8.9%/max 10.7% (目标 15%); sh.518880: 实际均重 21.3%/max 26.6% (目标 25%)；vs F3R2-A0: 腿成交 +306 单, 现金不足作废 102 次（锚 33 次）
- **F3R2-ICW**: 门8v3 最终交付 1+0/1=100.0%；限价直接成交率 6.0%；滑点(vs源信号收盘) 买 +0.673% 卖 +0.108%；分年 {"2015": 0.2459, "2016": 0.1139, "2017": -0.0812, "2018": -0.1816, "2019": 0.1898, "2020": 0.1777}；终止 {"expiry": 7, "override_same_name": 196, "cap_void": 0, "suspension_abandon": 9}；DD窗(2016-11-24→2018-10-18) 归因: 股票腿 84.5% / ETF腿 -0.3% / 现金 25.9%；sh.511010: 实际均重 9.0%/max 11.6% (目标 15%); sh.518880: 实际均重 21.0%/max 27.0% (目标 25%)；vs F3R2-A0: 腿成交 +214 单, 现金不足作废 1945 次（锚 33 次）

### F3 股票腿预算与参考（F3R2 预登记 §3）

| 臂 | 入场次数 | 退出次数 | 风险位月数 | 均w_T | 净CAGR | maxDD | 失败门 |
|---|---|---|---|---|---|---|---|
| F3R2-EW (EW) | 183 | 180 | 32 | 0.1499 | +3.77% | -20.20% | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 5_one_side_turnover_le_6 |
| F3R2-ICW (ICW) | 194 | 191 | 32 | 0.1499 | +6.55% | -33.05% | 4_mdd_le_20pct_and_le_B1m |
- 底盘参考 R3-06（v3 判定）：净 +11.06% / maxDD -16.22% / dev_pass=True。
- 引擎现金零收益：风险位月 33.3% 现金闲置，相对现实（货基收益）略悲观，保守方向如实呈现（预登记 §3 已登记代价）。

### 159934 冻结披露

- sz.159934（黄金ETF）dev 内 preclose 无跳变微偏离 [{"symbol": "sz.159934", "date": "2020-02-26", "preclose": 3.614, "prev_close": 3.622, "rel_diff": -0.002208724461623457, "factor_ratio": 1.0}]——因子 ratio=1.0（无份额变动），按 v2 预登记 §2 不建模，仅披露（与 v1 159915 同类）；分红规则扫描 0 事件。

## 三、F3R2-A0 回归锚（= v3 R3-06 复刻）

- 5/5 帧 `.equals()` 一致：{"intents": true, "fills": true, "events": true, "daily": true, "clips_final": true, "net_cagr_matches_v3_metrics": true}
- 引擎 stats：intents 206，orders 172，filled 65。

## 四、运行身份

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee、stk_limit agg 3c53abf3b0c39b42、etf-daily 目录聚合 75777221a8b33502、fund_adj 聚合 b06242469db048a0（=etf manifest 声明值）、trade_cal 聚合 aac75421cd89d9fc。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 时间划分：dev 2015-01-05..2020-12-31；val 未消费；判定只对 dev。
- 试验计账：本轮计 3 项（F3R2-A0 锚 + EW/ICW 两臂），策略线 264→267；因子线 FT-01=120 不变（如台账有异以台账为准）。
- 判定：no ARM passed all dev gates (0/2); F-line PAUSED per the F3R2 prereg stop clause (F3R3 is a separate user decision); val not consumed

## 五、关键发现与口径说明

- **F3 股票腿口径**：F3R1 冻结组合分（EW/ICW）逐字复用，buffer 成员K=3（入≤3/留≤6），w_T=e_T×(0.20/0.90)（T200-40 路径逐字）；风险位月33.3% 现金闲置（引擎现金零收益，保守方向如实呈现）。
- **门 8 v3 口径与 v2 逐字**：最终交付 =（市价兜底成交 + 武装后限价自身成交）/兜底武装单数 ≥99%，期末滞留=0 硬断言；8v2 与 R16 原口径（F3R1 映射 78.9–80.3%）仅作对照列。
- **停止条款（F3R2 预登记 §6）**：任一臂过门且 ≥10% → 停止并呈用户（val 消费须用户明确批准）；过门但 <10% → 记账报告；两臂全灭 → F 线暂停呈用户。val 保持零接触。
- **元过拟合披露（预登记 §0）**：本轮设计受 F3R1 门 4/5/8 死因与 v4 轴 A 证据启发；dev 读数为第 10 次重用的探索性结果，不构成样本外声称。
- **v3 已判配置不重跑不重判**：R3-01..06 的 dev 判定以 v3 为准；F3R2-A0 仅为回归锚。
- **ETF 腿数据质量**：9 符号 dev 面板、preclose 零空值、因子全覆盖、分红 18 事件全落带（明细见 outputs/dividend_events.csv）；159934 的 2020-02-26 微偏离见冻结披露（本轮不使用该符号）。