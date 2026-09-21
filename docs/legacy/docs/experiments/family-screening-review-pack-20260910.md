# 家族批量粗筛轮 Codex 送审包（②③④，round-20260910）

> **终裁（Codex 第 3 轮 PASS，2026-09-10）**：②预告、③资金流家族均无构造晋级；④价量家族仅 PV1 获得精测资格；PV2 与 PV5 不具有正式精测资格。**唯一有效预告工件=forecast-reopen-r4**（r3 及更早批次仅留历史对照）。本包前半的 r3 段落与旧歧义描述为历史记录，以本段与 §五B 为准。

审核性质：运行后工件抽审（粗筛层）。预登记 `docs/plans/family-batch-screening-preregistration-draft-20260910.md`；结论文档 `docs/experiments/family-screening-round1-20260910.md`（含主对话跨家族审查记录）。全仓测试基线 677 通过+1 跳过。

## 一、工件位置

| 家族 | 工件目录 | 关键文件 |
|---|---|---|
| ② 预告重开 | `artifacts/family-screening/round-20260910/forecast-reopen/` | screen_PE1..PE5.json（逐事件+事件日池+bench_detail）、summary.json/md（**01:07 重跑版为准**，见三.4） |
| ③ 资金流 | `artifacts/family-screening/round-20260910/moneyflow/` | events.json.gz（逐事件）、event_inputs.json.gz（事件日池输入）、bench_mean.json、screen.json、summary.md |
| ④ 价量月频 | `artifacts/family-screening/round-20260910/pricevol/` | ic_series_PV*.csv（逐月IC）、sections_PV*.csv.gz（月末截面全明细）、stocks/、summary.json/md |

实现入口：`experiments/screen_forecast_reopen.py`（19 单测）/`screen_moneyflow.py`（13）/`screen_pricevol.py`（13）；均 import 复用 event_family.py/mr_statarb.py 未修改本体。

## 二、建议复算项

1. PV1/PV2/PV5 的月块 bootstrap CI（从 `ic_series_PV*.csv` 48 个月 RankIC 重放：块长 3、B=10000、种子 20260909）；主对话已复算 IC 均值逐位一致。
2. PE2 h=20 与 PE5 h=20 超额毛均值（+116.4/+112.7bps）及 CI 下界符号——晋级判定的临界格。
3. MF5 h=20（−566.7bps）极端值的逐事件明细抽查。
4. 窗口纪律抽查：任意工件中最大入场/退出/标签日期 ≤2023-12-31。

## 三、待裁决歧义（主对话已按保守读法接受，请裁决）

1. **PV2 双侧先验晋级**：预登记先验句"散户主导的日内行为有不同持续性"非方向性；实现按双侧探索处理（|IC|≥0.02 ∧ CI 不含零即晋级，方向条款对该先验为空）。若裁决不接受双侧晋级，PV2 出局，晋级者减为 PV1/PV5。
2. **PV4/PV5 换手降级**：流通股本在本地数据集/baostock 均不可得（volume 单位为股），异常换手 z 降级为当月日均成交额 z（自身前 60 交易日母体）。经济构造有偏移，已披露。
3. **PE5 PIT 日内近似**：PB 取入场日当日收盘截面，入场为同日开盘——存在日内近似（预登记原文"公告次日取最近可得"的直读实现）；截面文件缺失日事件剔除（543 事件）不外推。
4. **PE5 首运行事故**：01:01 首工件 PE5 空候选（两段式 bug），代理修复代码后 01:07 重跑覆盖同目录；判定以 01:07 工件为准。请确认该目录当前工件为重跑版（summary.json counts.pe5_pb_sections_built=801）。
5. **MF1 分母**：机构净买入占比分母=top_list `l_amount`（榜单买卖合计），非全天成交额。
6. **MF3 滚动窗**：rzye 最近 60 个**可得**观测（缺日不补、不要求自然日对齐），z≥2 事件量 21.3 万（rzye 持续上行导致自相关触发）。
7. **②渲染瑕疵**：summary.md CI 列为小数单位（非 bps），符号不受影响。
8. **基准口径**：全 universe 等权未叠加 ST/停牌门禁（事件家族 note_5 直读法沿用）。

## 四、判定摘要（供核对）

- 晋级（仅授权精测预登记）：PV1（IC +0.0261，CI [+0.0081,+0.0471]）。
- 未晋级：PE1–PE5（毛超额有正但 CI 下界全负）、MF1–MF5（20 格全负）、PV3（|IC|<0.02 且 CI 含零）、PV4（方向相反）。
- 多重检验披露：粗筛层 α=0.10/15（宽进）；晋级者逐个走全流程精测。

## 五、r3 修复批次补送（第 1 轮两项 P1 的闭合证据；第 2 轮已独立重放确认 PE5）

- 工件：`artifacts/family-screening/round-20260910/forecast-reopen-r3/`（01:07 批次保留，含 `comparison_vs_0107.md`）。
- PE5=入场日前一市场日 PB 截面：事件 2,093，h=20 均值 +140.50bps、CI 下界 −69.16bps → 未晋级（第 2 轮 Codex 独立重放一致，修复确认）。
- PE3（r3 版）=min(ann_date) 身份：事件 12,758，h=3 均值 30.95bps——第 2 轮裁决该身份不合规（first_ann_date 不一致只计数不阻断），由 §五B r4 替代。
- PE1/PE2/PE4 与 01:07 批次逐字段零差异。

## 五B、r4 批次补送（第 2 轮 PE3 身份裁决的闭合证据）

- 工件：`artifacts/family-screening/round-20260910/forecast-reopen-r4/`（r3 保留，含 `comparison_vs_r3.md`）；模块 28 项测试（+6 项 PE3 身份反例）。
- PE3 身份改用来源 `first_ann_date`，三种不一致情形整期 fail-closed（mismatch 269 期、missing 20 期剔除并计数，无静默替代）。
- **PE3 h=3：均值 31.35bps（+0.40）距 34bps 线仍差 2.65bps → 临界不翻转，未晋级**；CI 下界 +2.76bps 为正（双条件门禁下均值未过线）。h=5/10/20 CI 下界均负。五构造维持 0/5。
- PE1/PE2/PE4/PE5 与 r3 逐字段零差异（主对话 JSON 整体相等校验确认）。
- 请复算：PE3 h=3 事件日池与 bootstrap 重放；r4 vs r3 零差异抽查。
