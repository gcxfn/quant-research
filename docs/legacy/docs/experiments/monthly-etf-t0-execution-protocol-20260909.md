# 月频 ETF + 做T：执行协议（2026-09-09）

**状态：运行前审核及本轮限定验收已完成，最终裁决见同目录 `monthly-etf-t0-independent-review-20260909.md`。** 本文件不构成交易建议。V3排名、门禁及T+1规则保留，开盘预算未来读取已纠正；Gate C/D继续冻结，P4不推进。

## 0. 工作树基线与文件白名单

2026-09-09 实施开始前，`git status --porcelain=v1` 已记录 9 个已跟踪修改和 24 个未跟踪 P4/文档文件；它们均为既有工作，绝不 reset、clean、覆盖或提交。本轮允许新增或修改的文件只有：

- `D:/AI/workspace/个人量化/quant/analysis.py`
- `D:/AI/workspace/个人量化/quant/market.py`（仅在 ETF 限价 tick 需要独立帮助函数时）
- `D:/AI/workspace/个人量化/quant/cli.py`（仅将 ETF 限价元数据传入研究 bar）
- `D:/AI/workspace/个人量化/configs/etf-limit-pct-schedules.json`
- `D:/AI/workspace/个人量化/tests/test_analysis.py`
- `D:/AI/workspace/个人量化/tests/test_market.py`（如变更 market）
- `D:/AI/workspace/个人量化/tests/test_backtest.py`、`D:/AI/workspace/个人量化/quant/backtest.py`、`D:/AI/workspace/个人量化/quant/short_strategy.py`（仅为元数据传递）或新增的同范围测试
- `D:/AI/workspace/个人量化/docs/experiments/monthly-etf-t0-execution-protocol-20260909.md`

主审已允许在本协议范围内新增 `experiments/monthly_etf_t0*.py`、`configs/monthly-etf-t0*.json`、`tests/test_monthly_etf_t0*.py`、`docs/experiments/monthly-etf-t0*`、`artifacts/monthly-etf-t0/<新批次>` 和 `data/raw/<source>/<新批次>`；P4 既有差异仍不可触碰。

## 1. 涨跌停工程修复

目标是令 `analysis.bar_side_locked` 按每个 ETF 的已核验限幅和生效日判断一字锁单，避免把所有 ETF 固定为 10%。普通股票仍沿用代码板块规则。

- ETF 不能仅由名称（例如含“科技”）推断为 20%。上海证券交易所 2020-08-21 通知只将明确范围内的基金列为 20%，并要求公布名单；该规则自发布日起实施。深交所同样存在制度生效日，历史回放不能将创业板 ETF 倒灌为全历史 20%。
- 元数据模型为显式、可审计的 `limit_pct_schedule`：每段含 `effective_from` 与 `pct`；研究调用链把池条目的该元数据随行传递。缺少 ETF 逐只核验证据时 fail-closed 为不从 `preclose` 推断锁板；显式 `limit_up`/`limit_down` 字段仍优先使用。
- ETF tick 为 0.001，股票仍为 0.01；不能把 `market.limit_price` 的 0.01 结果直接用于 ETF 锁板对账。若需要派生价格，仅使用标的 tick 做 `ROUND_HALF_UP`，并建立 0.001 回归测试。
- 验收：覆盖普通 ETF 10%、已核验 ETF 在生效日后的 20%、生效日前的 10%、缺元数据不猜测、0.001 ETF 价格与方向性买卖锁单；再跑离线 V3 `smoke`。该 smoke 只证明 V3 不变量和 T+1 时序，不是历史研究结论。

## 2. 做T 5分钟限价成交回放

计划中“baostock 5分钟 ETF 回放”与已核验数据边界冲突：`docs/experiments/short-data-coverage.md` 已记录 `sh.510050` 日线请求 0 行，baostock 对 ETF 没有 K 线。因此不得调用 baostock 生成 ETF 回放，也不得用股票分钟结果代替 ETF 结论。

运行前须先对公开、允许的 ETF 分钟数据源做小样本覆盖探查；原始响应只追加到 `data/raw/<source>/<batch>/`，串行、带节律，记录请求参数、日期覆盖、字段定义、输入清单、截止日和配置快照。只有覆盖 V3 池 ETF 与实际持仓、且保留 5 分钟 OHLCV 的来源，才能建立独立研究批次。

固定回放口径待审核后写入研究配置：

- 历史 `t0` 建议价位从当时已知数据重建，时间戳不得晚于提交的限价订单；不会读取未来 bar。
- 成交需 bar 内**穿越**限价（买入 `low < limit`，卖出 `high > limit`），等于限价仅触及视为未成交；可成交量受 bar 量、参与率和共享容量限制。
- 保留未成交、部分成交、超时、反T 与 T+1 可卖底仓状态；费用为 ETF 万1、无最低、免印花税，研究滑点双边万5，独立配置覆盖，不修改 `configs/strategy.json` 当前生产成本。
- 报告将明确 5分钟粒度、看不到盘口排队的偏乐观方向；结果只评估历史建议在该代理下的成交与费用后结果，不更改择时或自动交易。

如果没有可用 ETF 5分钟源，本项输出 `DATA_SOURCE_UNAVAILABLE_FOR_ETF`，不运行股票替代实验，也不作盈利结论。合成数据可验证保守撮合工程，但不能替代实证。

## 3. V3 时间切分验证

由于现有 ETF 历史已经被看过，本轮不能称任何历史段为“全新严格 OOS”。可交付的是固定规则的时间切分复核：冻结 V3 R20/R60/R120 等权百分位、Top3、月末信号/t+1 开盘、原始池和成本；不进行参数搜索。

- 运行前锁定 2020-01-01 至 2026-09-04、描述段 2020--2023 / 2024--2025 / 2026 至截止、池快照、输入清单、费用（ETF 万1、无最低、每边滑点万5、初始资金10万元）和 `rf=0` 年化约定；不搜索参数。
- 日收益序列必须包含现金日。夏普使用日超额收益均值除样本标准差后按 `sqrt(252)` 年化；不得复用 `portfolio_candidate.metrics` 中 `CAGR / annualized volatility` 标作 Sharpe。
- 概率评价需预先定义预测事件、基线频率、Brier/log loss 或同等固定评分，并逐段比较；若 V3 不产生概率，报告明确“不适用”，不会伪造概率指标。
- 输出只能称“历史已观察数据上的冻结时间切分复核”，并披露当前在市 ETF 池、前复权与清盘缺失的局限；未来前瞻 shadow 才可能成为真正未见 OOS。

## 4. ETF 清盘/退市幸存者偏差上界

不具备经核验的历史 ETF 清盘全名单和对应日线前，不能估计数值上界，更不能把股票退市资料替代为 ETF 证据。运行前需先建立带来源、抓取日期、基金代码、简称、上市/终止上市或清盘日期、终止类型的逐只清单，并与当前 55 只池及研究时间窗做集合对账。

可能的上界方法也必须预先冻结：对每一缺失清盘 ETF，按可验证的最后净值/交易价、清盘回收假设和可交易日期构造悲观损失路径，逐交易日重建可选集合；如缺少价格或终止价值，只报告“无法量化”，不以任意跌幅填补。报告同时给出清单覆盖率、无价格条数、截尾个数和上界是否真正可计算。

## 5. 运行与验收顺序

1. 主对话审核本协议及数据源选择；未获审核仅完成第1节离线工程。
2. 工程变更先跑针对性单测和 `python -m quant.cli --config configs/test-fixture.json smoke --fixture tests/fixtures/rotation/pool.csv`。
3. 获准后才新建数据批次与研究配置；输出原始数据、参数、代码版本、命令和结果工件。
4. 主对话独立检查原始数据、配置和反例后裁决。实现者不宣布独立 PASS。
