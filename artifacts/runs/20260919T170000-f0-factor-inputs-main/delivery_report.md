# F0 因子输入数据审计 — 交付报告（主对话接管执行）

- run：`artifacts/runs/20260919T170000-f0-factor-inputs-main/`（性质：**纯描述性数据画像**；零试验、零策略计算、零收益/IC 计算；data/ 零写入；未做 git）。
- 执行链披露：F0 三次分派子代理均死于基础设施（Captcha 启动期超时，各 50–211 秒零残留）后，由主对话接管执行；审计脚本 `f0_scan.py`（39 数据集结构化扫描 + 接缝核查 + 面板交叉抽验 + 骨架盘点），产物 `outputs/factor_inputs_scan.csv` + `outputs/f0_scan.json`。
- 输入（只读）：`data/raw/tushare/`（财务/事件/基金/指数）+ `data/raw/xiaodefa/`（量价/微观结构日频，63 数据集 13.11GB 代理全量）+ `data/processed/baostock-daily-20260917/`（v0 股票日面板）+ `src/quant/factors/`。

## 一、总体结论

**F2 可直接使用（dev 2015–2020 全覆盖 1462 交易日 + val 全覆盖 + PIT 可行）：**

| 因子族 | 数据集 | dev 覆盖 | PIT 机制 | 备注 |
|---|---|---|---|---|
| 量价/复权 | xiaodefa/adj_factor（3088 日，2014-01 起） | 1462/1462 | 日频无需 | 2025+ 412 行须钳制 |
| 日频估值 | tushare/daily_basic（换手/市值/PE/PB 等） | 1462/1462 | 日频无需 | **r1/r2 接缝实测干净**（r2=2015-2018 共 975 日、r1=2019 起共 1866 日、零重叠零缺口、列一致） |
| 微观结构 | moneyflow 资金流、stk_auction_c/o 竞价 | 1462/1462 | 日频无需 | 3088/3088 完整 |
| 微观结构 | stk_nineturn、idx_factor_pro、ths_daily 行业 | 1462/1462 | 日频无需 | 完整 |
| 停复牌 | suspend_d | 1462/1462 | 日频无需 | |
| 财务 | income/balancesheet/cashflow（逐股 5,901+，1990s 起） | 报告期 | **ann_date + f_ann_date + update_flag 全有 → 真 PIT 可行** | 逐股分块 |
| 财务 | fina_indicator（396MB 逐股） | 报告期 | ann_date 有 | 财务比率直读 |
| 公告事件 | forecast 预告 / express 快报（T1 同源） | 2018-09 起 | ann_date + update_flag | T1 结构化已 24/65 批 |
| 公告事件 | repurchase 回购 / stk_holdertrade 增减持 / share_float 解禁 | 2016 年中起 | ann_date | 事件粒度 |
| 涨跌停 | tushare/stk_limit（**天然无 2025+ 行**，2015-2024 完整） | 1462/1462 | 日频无需 | |
| 行业指数 | sw_daily（dev 缺 1 日 2015-01-20）、ci_daily（val 止 2025-05） | 1461/1462 | 日频无需 | 申万日线为中文列名 |
| 参考 | stock_basic（list_date/delist_date）、trade_cal | — | — | 池构建用 |

**dev 窗不可用/残缺（val 可用，因子只能做 val 段或不用）：**
- margin_detail 两融、top_list/top_inst 龙虎榜：2019-01-02 起 → dev 仅 487/1462；
- cyq_perf 筹码：2018-01-02 起 → dev 730/1462（2015-2017 段全缺）；
- hk_hold 港股通持股：2017-01 起 → dev 948/1462；ccass_hold：2020-11 起 dev 仅 36 日；ggt_daily：dev 1363/1462；
- dc_daily、limit_list_d：2020 年起 → dev 仅 243 日。

**关键缺陷与口径（须写入 F1/F2 预登记）：**
1. **PIT 双轨**：财务三表 + forecast/express 有 ann_date/f_ann_date/update_flag（真 PIT）；disclosure_date 数据集仅 2018-12 起（2019 前用报表自身 ann_date）；其余无披露字段的数据集不适用（日频数据当日可得）。90 天保守滞后规则仅作为 ann_date 缺失时的兜底，须逐行记录适用比例。
2. **index_member_all 是单快照**（l1/l2/l3 行业归属），非时变成分——行业中性化用它存在前视偏差风险，F2 行业因子须披露此限制或改用 ths_daily 成分口径。
3. 涨跌停/停复牌与 v0 面板可用（stk_limit 天然止于 2024-12-31）；adj_factor 与面板 close 抽验同源可乘（面板 16,344,349 行/5,410 符号，含 preclose/turn/tradestatus/isST）。
4. 2025+ 行普遍存在（410–412 日），全部取数路径必须钳制 ≤2024-12-31（冻结纪律）；唯一例外 stk_limit 已天然无 2025+ 行。
5. xiaodefa 为 Tushare 兼容代理单源；与 baostock 面板互为部分交叉验证（价格类），非全独立双源。

## 二、factors/ 骨架复用结论（F1 直接构建于其上）

- `core.py`（254 行）：FactorError 体系 + validate_daily_frame + compute_factors——F1 的因子计算与校验入口已具备。
- `cache.py`（587 行）：FeatureCache 含 canonical_json/key_sha256/source_files/source_sha256/feature_set_id——**AGENTS §5.4 缓存键纪律已实现**（输入版本+参数+源码哈希入键），F1 评估结果直接走此缓存。
- `signals.py`（85 行）：build_signals 薄入口。
- 结论：F1 不需要新建缓存/校验层，只加评估模块（rank IC/分组/逐年/换手/PIT 对齐/冻结断言）。

## 三、F2 首轮可用性判定（供预登记起草）

- **第一批（数据全干净）**：量价族（动量/反转/波动/换手，基于 v0 面板+adj_factor）、日频估值族（daily_basic：市值/PE/PB/换手率）、竞价/资金流微观族、stk_limit 相关（涨停距离/连板状态）。
- **第二批（真 PIT 财务）**：fina_indicator 直读比率 + 三表衍生（成长/质量/杠杆），ann_date 对齐；2015 dev 段可得性依赖 2014 年报+2015 一季报披露，F1 需输出覆盖率实测。
- **第三批（事件，与 T1 汇合）**：forecast/express（T1 结构化中）+ 回购/增减持/解禁（ann_date 事件）。
- 两融/筹码/港股通/龙虎榜：dev 段残缺，首轮不用，披露为"val-only 可用性"。

## 四、产物清单

`f0_scan.py`、`outputs/factor_inputs_scan.csv`（39 数据集结构化行）、`outputs/f0_scan.json`（含接缝/交叉抽验/骨架全量）、本报告。不构成任何策略或绩效结论；零试验消费。
