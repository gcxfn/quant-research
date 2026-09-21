# daily-swing-oos 方法学：daily-swing-v1 持有 1/2/3 日历史 walk-forward 验证

- 实验模块：`experiments/daily_swing_oos.py`
- 冻结配置：`configs/daily-swing-oos.json`（`zones`/`costs`/`top_n`/门禁阈值运行前强制与生产 `configs/daily-swing.json` 逐项一致，见 `check_production_consistency`，不一致直接拒绝运行）
- 性质：**研究证据生成**。本实验不判断 daily-swing-v1 是否有效或可执行，不修改生产语义，不改 `risk_status`，需独立 Reviewer 审查。
- 产物：`artifacts/experiments/daily-swing-oos/<run_id>/`（config_snapshot.json、sample_ledger.csv、summary.json、report.md、evidence-index.json）

## 1. 研究问题

对日常主入口 daily-swing-v1（每日最多 3 只、费用覆盖倍数排序、ATR20 波动带区间），
在历史日线上分别评估持有 1、2、3 个交易日时：

1. 买入/短线卖出/风险离场区间的触达情况；
2. 最大有利波动 MFE 与最大不利波动 MAE；
3. 扣除双边佣金、最低佣金分段、滑点、个股卖出印花税（5bps；ETF 免）后的结果；
4. ETF 与个股差异、不同时间段稳定性、数据缺失与池偏差的影响。

## 2. 信号形成时间（防未来函数）

- 主验证在 **t 日收盘后形成历史研究信号**；特征（ATR20、20 日流动性、日内典型振幅、
  费用覆盖倍数、区间）只用不晚于 t 日的数据；t 之后的数据只作标签。
- 历史腾讯 qt 盘中锚点不可还原，锚点用 t 日收盘价代理，逐行标记
  **HISTORICAL_CLOSE_PROXY_FOR_QT**。
- **历史收盘价代理不能证明实时盘中运行效果，本验证只检验固定规则在日线级别的
  研究表现，不是真实实盘回放。**
- 排名复用生产函数链（`t0.evaluate_daily_candidate` → `t0.select_daily_top3`），
  与生产 daily 唯一差异是行情来源（收盘代理 vs qt 快照）。
- 测试证明：改动 t 日之后的全部价格，t 日候选与选择逐字段不变
  （`tests/test_daily_swing_oos.py::TestNoFutureLeak`）。

## 3. 入场与区间触达（两套分离指标）

信号日为 t；观察窗 = t+1..t+h（h∈{1,2,3}，按该标的自身交易日序列计数，停牌日不计）。

**A. 区间覆盖指标（不假设成交）**：后续窗口的 [low,high] 是否与买入/卖出/风险离场
区间相交（`zone_coverage`）。对全部行计算，包括未入场样本。

**B. 保守路径模拟**（`simulate_trade`，全部规则冻结于配置）：

- 入场：入场窗内**首个**与买入区间相交的交易日才视为可能入场；
  成交代理价 = `min(open, buy_high)`——开盘 ≤ 区间上沿按集合竞价/跳空穿过价成交，
  否则按挂单 buy_high 成交；**不假设理想边界**。
- 整窗未触达买入区间记 `NO_ENTRY`（不得记为零收益成交）；资金买不足一手记
  `UNSIZEABLE_AT_FILL`。
- **T+1 硬约束**：出场只扫描入场日之后的交易日，入场当日不平仓。
  出场窗 = 入场日后 1..h 个交易日（持有期从入场日起算；入场窗内晚入场时出场窗
  可超出 t+h，此扩展显式披露，不影响入场窗=任务书标签窗的口径）。
- 卖出区间触发 = `high ≥ sell_low`；`open ≥ sell_low` 时按开盘价成交（隔夜挂单的
  集合竞价真实行为），否则按 sell_low 成交。
- 风险离场触发 = `low ≤ exit_high`；`open ≤ exit_high` 时按开盘价成交
  （跳空穿过止损价，保守），否则按 exit_high 成交。
- **同日同时触达卖出与风险离场区间**：日线无法判断先后 → 标记
  `AMBIGUOUS_INTRADAY_ORDER`；主结果保守假设风险离场先发生；乐观上界（卖出先发生）
  记入 `optimistic_*` 单列字段，不混入主结果。开盘已落在某侧区间外的情形按集合竞价
  确定成交处理，不属于歧义。
- 出场窗未触发：按出场窗最后一日收盘离场（`WINDOW_CLOSE`）；可用日不足 h 记
  `TRUNCATED_FORWARD`；入场后无任何交易日记 `OPEN_NO_FORWARD_BARS`（未解决，不计收益）。
- MFE/MAE 仅在入场日之后（含出场日）计算：MFE=max(high)/entry−1，MAE=min(low)/entry−1；
  入场当日区间不可归因（日内先后不可知）。

## 4. 排名（与生产 v1 完全一致，无新增因子）

每个信号日：合并 ETF 池与个股池 → 按 symbol 去重 → 当日可得数据门禁
（20 日流动性、ATR20 有效、资金可买至少一手、费用覆盖倍数 ≥ 1.0）→
按 fee_cover 降序、symbol 升序 → 最多 3 只，不足不补位。
**不含**动量方向、PE/PB、ROE、新闻、外盘、模型预测，未新增任何看完结果后的过滤条件。

## 5. 费用

全部复用 `quant/t0.py` 生产费用函数（`buy_cost`/`sell_proceeds`/
`hypothetical_shares`/`fee_cover_ratio`），未另写简化公式：双边佣金含最低佣金分段、
滑点 5bps、整手 100、个股卖出印花税 5bps、ETF 0。资金口径与生产 daily 相同：
`initial_capital(10 万) ÷ top_n(3)` 每标的等分。费用区分 ETF/个股与不同资金情景
（见敏感性）。`net_return` 以买入名义本金归一；`total_fees` = 双腿费用合计。

## 6. 样本划分：blocked walk-forward

信号日升序连续切块 research 60% / validation 20% / test 20%（边界写入快照）；
禁止随机打乱。所有参数在运行前冻结于配置文件并写入 config_snapshot.json；
final test 只运行一次主报告（同一次运行内完成，不据其返调参数）。

**final test 状态 = `INSUFFICIENT_STRICT_OOS`**：池为当前在市 ETF/个股，
基于当前在市池的时间外推验证，仍含幸存者偏差和池构建前视影响；即便时间切分正确，
也不得宣称严格无偏样本外。

## 7. 已知偏差与局限（完整披露）

1. **幸存者偏差 + 池构建前视**：当前在市池回放历史，越早年份池越窄且未含已退市标的。
2. **HISTORICAL_CLOSE_PROXY_FOR_QT**：收盘价代理盘中 qt 锚，区间在盘中被触达的
   真实概率与本研究估计可能有系统性差异（如开盘集合竞价即穿越区间的处理只能用
   代理规则近似）。
3. **前复权重写**：历史价格随新分红变化；本实验读清洗缓存，数据清单记录
   bars.csv 与原始响应 SHA-256，复现以原始响应哈希为准。
4. 停牌代理：信号日无该标的日线即排除（生产环境中 qt 快照仍可能有价，口径更保守）。
5. 未构造组合净值：重叠信号存在资金占用冲突，无法无歧义映射为组合持仓，
   故不报告 max_drawdown。
6. 数据源通道：akshare(东财) 为既定 primary，本机东财断连期间读腾讯(tx)清洗缓存
   （tx≡ak 等价性已经双源验证，D-2026-09-04-04），配置显式标注。

## 8. 统计口径

按 hold_days=1/2/3 分别统计（不混并），另按 ETF/个股、research/validation/test、
年度分层：signal_count、selected_count、no_entry_count/rate、entry_touch_rate、
sell_zone_touch_rate、risk_exit_touch_rate（A 套相交口径）、ambiguous_order_rate
（÷有入场样本）、average/median MFE/MAE、average/median net_return、
positive_net_return_rate（历史样本正收益占比，不是胜率）、total_fees、fee_drag
（平均毛净差）、turnover（年化名义换手/资金）、valid_count、missing_rate、
未解决/不足一手计数、歧义乐观上界平均抬升。

敏感性**只**改变费用与资金情景（现金 ×0.5/×1/×2；佣金减半、免最低佣金、免滑点），
不搜索、不优化任何策略参数；入场/出场价格与选择不受情景影响。

## 9. 复现命令

```bash
python -m unittest tests.test_daily_swing_oos -v
python -m unittest discover -s tests -v
python -m quant.cli --config configs/test-fixture.json smoke --fixture tests/fixtures/rotation/pool.csv
python experiments/daily_swing_oos.py --config configs/daily-swing-oos.json
```

同一输入重跑逐字段一致（无随机源；`generated_at` 用固定戳 `HISTORICAL_RESEARCH_PROXY`，
真实时间只出现在 summary.json 与 evidence-index.json 的运行元数据中）。
