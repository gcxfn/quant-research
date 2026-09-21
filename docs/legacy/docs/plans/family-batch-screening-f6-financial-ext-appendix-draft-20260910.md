# 家族批量粗筛 F6+ 财务扩展附录（2026-09-10）

状态：用户授权（2026-09-10 对话指示"之前死掉的家族里面再挖点因子，最好几百个几千个一起去测…当然要合理"；⑤ 财务家族 F1/F4 已晋级说明该信息维度有矿）。
定位：⑤ 财务家族的**字段空间扩容批**——同一冻结协议、更多报表字段。只做毛筛（无成本、无交易结构、选择窗专用），2024-01-01 起零接触，晋级≠有效。

## 1. 继承（全部逐字冻结，零改动）

- 基础协议：`docs/plans/family-batch-screening-preregistration-draft-20260910.md` §2（因子型：月末截面 RankIC vs 下月收益；月块 bootstrap 块长 3、B=10000、种子 20260909；晋级线 |RankIC 均值|≥0.02 ∧ CI 不含零 ∧ 方向与先验一致）与 §3 纪律。
- ⑤ 附录全部机制：四条取数契约（最早公告日为准/ann<end 剔除断言/同键字段冲突 fail-closed/四字段去重键+真重复整组剔除）、15 月（459 天）陈旧上限、金融排除 comp_type∈{2,3,4,7}（最新可得报告）、三表同报告期配对与同期对同期规则、**F4/F5 配对行同样受 ann_date≤t 约束**（r2 修复后语义）、daily_basic total_mv 单位万元→元、月末截面对齐规则、工件要求（逐月 IC 序列+截面明细+逐股文件+identity）。
- 实现约束：复用 `experiments/screen_financial_stmt.py` 的契约函数（import 不复制，单一事实源）；新脚本 `experiments/screen_financial_ext_r1.py`；批次 `artifacts/family-screening/f6-ext-round-20260910`（只新增不覆盖）。

## 2. 本批构造清单（N=30，事前冻结；方向=预期 IC 符号）

### 2.1 盈利质量与边际（8）
| id | 构造 | 字段 | 方向 | 机制一句话 |
|---|---|---|---|---|
| F6 | 毛利率 | fina grossprofit_margin | + | 定价权/成本优势持续 |
| F7 | 净利率 | fina netprofit_margin | + | 终端盈利能力 |
| F8 | 扣非 ROE | fina roe_dt | + | 盈利质量高于 roe（⑤F2 用 roe 未过线，本为口径对照非重测）|
| F9 | ROA | fina roa | + | 资产回报独立于杠杆 |
| F10 | ROIC | fina roic | + | 投入资本回报，剔除杠杆与冗余现金 |
| F11 | 经营利润/营收 | fina op_of_gr（或 ebit_of_gr） | + | 主营盈利占比 |
| F12 | 毛利率改善 | DELTA(grossprofit_margin)（当期−上年同期） | + | 边际改善的信息含量 |
| F13 | 扣非利润占比 | income profit_dedt ÷ n_income | + | 非经常损益占比低的盈余质量 |

### 2.2 费用与营运效率（7）
| id | 构造 | 字段 | 方向 | 机制 |
|---|---|---|---|---|
| F14 | 销售费用率 | fina saleexp_to_gr | − | 高销售依赖=弱护城河 |
| F15 | 管理费用率 | fina adminexp_of_gr | − | 代理成本/低效 |
| F16 | 财务费用率 | fina finaexp_of_gr | − | 债务负担侵蚀 |
| F17 | 应收周转 | fina ar_turn | + | 回款能力/收入质量 |
| F18 | 流动资产周转 | fina ca_turn | + | 营运效率 |
| F19 | 固定资产周转 | fina fa_turn | + | 产能利用 |
| F20 | 总资产周转 | fina assets_turn | + | 综合运营效率 |

### 2.3 杠杆与流动性（5）
| id | 构造 | 字段 | 方向 | 机制 |
|---|---|---|---|---|
| F21 | 资产负债率 | fina debt_to_assets（缺则 (total_assets−equity)/total_assets 三表算） | − | 财务风险折价 |
| F22 | 净债务/有形资产 | (netdebt)÷(tangible_asset)，均 fina | − | 去现金真实杠杆 |
| F23 | 流动比率 | fina current_ratio | + | 短期偿付安全垫（方向弱先验，作对照） |
| F24 | 速动比率 | fina quick_ratio | + | 严口径流动性 |
| F25 | 营运资本/总资产 | fina working_capital ÷ balancesheet total_assets | + | 滞压资金少的运营健康 |

### 2.4 现金流与增长质量（6）
| id | 构造 | 字段 | 方向 | 机制 |
|---|---|---|---|---|
| F26 | 经营现金流/营收 | cashflow n_cashflow_act ÷ income total_revenue（同报告期） | + | 收入的现金含量 |
| F27 | 每股经营现金流 | fina ocfps | + | 现金创造 |
| F28 | 每股净资产 | fina bps（与⑤F1 相关，作口径对照与相关性披露） | + | 账面价值锚 |
| F29 | 营收增长质量 | income total_revenue 同期同比（⑤F3 用 or_yoy，本为报表原值口径对照） | + | 需求侧成长 |
| F30 | 盈利稳定性 | 近 ≤8 个已公告报告期 roe 的 STD（ann≤t） | − | 盈余波动=低质量 |
| F31 | FCFF/总资产 | fina fcff ÷ balancesheet total_assets | + | 自由现金流创造 |

### 2.5 披露
- F8/F28/F29 是 ⑤ 同族口径对照（novelty：字段口径差异），与 F2/F1/F3 的相关性在报告中披露；高相关晋级者合并进同一精测预登记考量。
- 字段在数据中整列缺失的构造 → 计 data_absent 落档，不得静默剔除（fail-closed 披露）。
- 本批 N=30，粗筛 α=0.10/30；家族级结论仍按"代表构造未过线"表述，不判死字段空间。

## 3. 分工与流程

flash 实现（复用⑤契约函数）→ 22+30 项单测（新增构造各至少一条取数反例）→ 主对话运行前审查 → 正式跑 → 主对话工件审查 → 晋级者并入攒批队列（与 F1/F4、PV1 同队列）。批考预登记时统一定资格。
