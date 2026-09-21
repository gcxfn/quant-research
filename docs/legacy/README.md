# 个人量化 · 做T与一周短线建议

新增：[三类周内入场条件固定对照](docs/experiments/weekly-entry-research.md)，股票和ETF分开，共7组；固定费用和五日退出，记录成交率与利润集中度。独立审查尚未完成。

周内短线是当前优化重点：新增限价成交、止盈止损与第五日退出的实际交易标签研究；[方法、复现与完整证据](docs/experiments/weekly-trade-research.md)。仍为研究，未完成独立验收。

最新研究：年化10%/夏普1.5目标**尚未达成**，方向模型未证明可靠准确率优势。已补充时间滚动验证、夏普、上市行情修复及用户授权的独立概率留档；[结果与运行说明](docs/experiments/short-target-research.md)。下面上一轮数字对应原172只池，保留作为历史记录。

A股股票/ETF，排除ST/*ST。输入资金、可卖底仓、费用与风险预算，输出价格、数量及费用后盈亏；所有买卖由人操作。**新短线候选尚未完成独立盈利验证**，不要把研究计划当作已验证盈利策略。

2026-09-05按用户资金10万元、股票万2.5最低5元、ETF万1无最低校准，新增“宽基趋势较强时才开新仓”的研究配置：全期累计+28.29%（年化2.45%）、最大回撤8.43%，费用压力全期+14.50%。通过本轮历史筛选，仍缺少全新样本与独立验收。运行：`python -X utf8 -m quant.cli short --short-config configs/short-term-candidate.json --offline`。详见[盈利策略实验](docs/experiments/short-profit-research.md)。

```bash
# 账户示例是演示值，复制后填写实况。实时做T须指定你选定的标的。
python -m quant.cli t0 --symbol sh510300 --account configs/account.example.json --once

# 一周短线：本地收盘数据生成下一交易日研究计划
python -m quant.cli short --account configs/account.example.json --offline

# 固定参数的短线组合回放（纯本地数据）
python -m quant.cli short --backtest
```

做T差额可隔夜；一周短线满足条件可延长。账户字段、人工成交录入、续持规则和实际回测结果见 **[使用说明](docs/short-term-usage.md)**。当前新短线固定规则回放：全期−8.31%、验证段−4.01%、测试段+8.91%，全期最大回撤24.46%；不能据此宣称有稳定盈利能力。

其他入口：

1. **V3 月频轮动（`signal` / `plan` / `backtest`）**：R20/R60/R120 横截面百分位 Top3 等权。V2 Top1 已退役。
2. **有底仓做 T（`t0 --symbol`）**：对人工指定标的按费用后保本口径给出正T/反T价位。联网默认每 **300秒**刷新。必须有当日可卖底仓；已成交首笔在账户`open_t`里人工记录后，程序提供原交易的后续建议。

`daily`（daily-swing-v1）是研究入口，不是日常选股。

只产出可审计的区间、仓位建议和费用后保本价位。不连接券商、不自动下单、不报会涨会跌或胜率。

## 日常操作

```bash
# 月频信号（Top3 组合 + 候补）
python -m quant.cli --config configs/strategy.json signal --top 8

# 持仓 vs 月频推荐 → 换仓/止损检查
python -m quant.cli --config configs/strategy.json plan

# 有底仓做 T：默认 5 分钟刷新；Ctrl+C 正常退出
python -m quant.cli t0 --symbol sh510300 --shares 20000 --cash 30000
python -m quant.cli t0 --symbol sh510300 --once
python -m quant.cli t0 --symbol sh510300 --cash 100000 --risk-budget 500 --once

# 持仓录入（人工成交后记录）
python -m quant.cli position buy --symbol sh510300 --shares 1000 --price 4.5 --date 2026-09-01
python -m quant.cli position show
```

`t0` 每轮含：生成时间、行情时点、策略版本、费用、风险状态；无底仓时 `forward_t`/`reverse_t` 为 `None`。产物在 `artifacts/t0/`。

## 策略（日常：V3，D-2026-09-05-01）

ETF 月频动量轮动是日常选组合：`backtest` / `signal` / `plan` / `experiments/forward_shadow.py`。V2 Top1 不再生新信号。

- **池**：55 只 A 股 ETF（宽基 + 行业 + 主题 + 国内商品），由 `scripts/build_pool.py` 自动构建：全市场 ETF 按名称分主题组、组内按 20 日中位成交额取第一名、剔除跨境 QDII/债券/货币/北交所。规则不使用任何回测收益。
- **选组合**：月末收盘后按 R20/R60/R120 各自的**横截面百分位排名**等权合成动量分，取 **Top3 等权持有**（各 1/3）；门槛为 `close > SMA120` 且 `R60 > 0`、上市满 252 日、20 日中位成交额 ≥ 5000 万。确定性 tie-break。回测日历为日期并集，新上市 ETF 从历史达标之日起自然进入候选。
- **持仓纪律**：已持有且仍在组合内的标的不强制月月再平衡（降低无意义换手）；月末只卖出跌出组合的、买入新进的。
- **买卖区间**（ATR20 波动率带，研究假设）：
  - 买入区间 = `[close − 1.0×ATR20, close + 0.5×ATR20]`，区间外不追价
  - **新建仓初始止损参考带** = `[close − 3.0×ATR20, close − 2.0×ATR20]`；建仓后 `plan` 改用“持仓以来最高收盘价 − 2×ATR20”作为跟踪触发线（−3×ATR 为硬底线参考）
  - **止盈参考带** = `[120日最高收盘, +1.0×ATR20]`，收盘进入该带可分批止盈或收紧跟踪止损
  - **重要**：正式轮动回测目前只验证月频换仓，不含日频止损/止盈；执行层止损必须单独做前向验证，避免把趋势右尾切掉
- **执行**：信号 t 日收盘生成，t+1 开盘人工执行。
- **附加门禁候选**（RSI / 已实现波动 / 量能比 / 距高点）：未进生产，须独立样本外验证。
- **做 T**：对 V3 底仓刷新 qt，费用后保本；不是 5 分钟 K 线策略。

## 研究入口（daily-swing-v1，D-2026-09-04-06，已降级）

`python -m quant.cli daily` 仍可用，不作为日常选股。v1 只按 20 日流动性 + 费用覆盖倍数排序，不含动量。产物在 `artifacts/daily-swing/<as_of>/`。

## 数据源

| 源 | 角色 | 说明 |
|---|---|---|
| akshare(东财) | ETF/个股日线 primary | `fund_etf_hist_em`/`stock_zh_a_hist_em` 前复权全历史（免 key）；volume 由手 ×100 折算为份，amount 为真实历史元值。**push2his 对同 IP 连续请求限流**：内置 12s 节律 + 90s 冷却重试。探针报告见 `docs/data-source-ak-probe.md` |
| 同花顺 API | ETF 日线备用 | 前复权 ETF 日线 + 成交额，仅近 5 年；key 经环境变量 `THS_API_KEY` 使用，禁止写入仓库 |
| 腾讯行情 | 个股日线复核 + 批量快照 | 前复权日线（全历史，回溯分页）；`qt.gtimg.cn` 批量快照（PE-TTM/PB/市值/换手）。免 key。**量纲陷阱**：科创板 volume 原始为股，其余板块为手（见个股探针报告） |
| 新浪财经 | 复核 + 全市场列表 + 行业 | 未复权 K 线（跳变交叉复核与降级备选）；A 股全列表（池构建）；行业分类（部分覆盖，科创板缺） |
| 东财 F10 | 个股财务 | 季报主要指标（ROE/毛利率/增速/负债率等，最近 9 期）。emweb 主机稳定；push2 行情主机有 IP 限流（备用） |
| xiaodefa(Tushare 兼容) | 研究与执行补数 | 复权因子、涨跌停价、停复牌、集合竞价、资金流、筹码、股通持股、指数与板块等按交易日/逐股拉取；token 只存 `~/.quant-credentials/xiaodefa-token`。批次与口径见 `docs/experiments/xiaodefa-data-pull-20260913.md` |
| baostock | 历史 5 分钟主源(2020 起) + 退市/ST/停牌补齐 | 串行、login/logout 配对、节流续传；2020 前无分钟数据，早年分钟缺口按日另补 |

数据门禁：OHLC 不变量、日期递增唯一、单日 >21% 跳变检测（公司行为断层即排除，除息伪影经原始价复核后保留并披露）。详见 `docs/data-source-ths-probe.md`（ETF）与 `docs/data-source-stock-probe.md`（个股/基本面）。

财务数据的时点纪律：报告期 Q 的数据在 Q 结束后 90 天才对回测/排名可见（保守披露滞后，防未来函数）。

## 命令

```bash
# 全部单元测试（离线）
python -m unittest discover -s tests -v

# 离线端到端 smoke（fixture 驱动，回归 V3 回测/信号链）
python -m quant.cli --config configs/test-fixture.json smoke --fixture tests/fixtures/rotation/pool.csv

# ---- 日常入口见上文 signal / plan / t0 ----

# 联网：抓取池内全部 ETF（akshare 东财源，免 key；限流下 55 只约 12~20 分钟）
python -m quant.cli --config configs/strategy.json fetch-all

# ---- 回测与前向（V3） ----

# 轮动回测（V3 Top3 等权；产物在 artifacts/backtests/<run_id>/）
python -m quant.cli --config configs/strategy.json backtest

# 生成月频推荐信号（Top3 组合 + 候补，artifacts/signals/<as_of>/，--top 候选总长度）
python -m quant.cli --config configs/strategy.json signal --top 8

# 执行计划：持仓 vs 月频推荐 → 换仓/止损检查
python -m quant.cli --config configs/strategy.json plan

# V3 前向纸面记录（每月信号生成后跑一次；数据到齐自动结算）
python experiments/forward_shadow.py

# 长历史对照实验：V3 vs V2 全历史（复现 docs/experiments/strategy-v3-long-history.json）
python experiments/strategy_v3_long_history.py

# ---- 个股研究线 / 分析面板 ----

# 构建个股池（新浪全列表门禁 + 腾讯日线复核流动性 + 行业分散；写入 configs/stocks.json）
python scripts/build_stock_pool.py

# 抓取池内个股日线（腾讯前复权全历史 + 新浪原始价复核；免 key）
python -m quant.cli --config configs/stocks.json fetch-all

# 抓取池内基本面（腾讯批量快照 + 东财 F10 季报）
python -m quant.cli --config configs/stocks.json fetch-fund

# 个股池轮动对照回测（研究对照，含印花税成本模型）
python -m quant.cli --config configs/stocks.json backtest

# 单标的分析：基本面+技术面面板与买卖推荐价（个股或 ETF 均可）
python -m quant.cli --config configs/stocks.json analyze --symbol sh600519
python -m quant.cli --config configs/strategy.json analyze --symbol sh510300
```

## 目录

```
quant/            data.py(取数) validation.py(门禁) factors.py(技术因子)
                  fundamentals.py(基本面因子+时点规则) selector.py(选择与区间)
                  analysis.py(标的分析+短线区间) t0.py(费用后保本/做T)
                  backtest.py(轮动回测) signal.py(信号) plan.py(执行计划)
                  positions.py(持仓) cli.py(daily / t0 / V3 命令)
configs/          strategy.json(V3 日常) daily-swing.json(研究短线)
                  stocks.json(个股池) test-fixture.json(测试)
scripts/          build_pool.py(ETF池) build_stock_pool.py(个股池) show_signal.py
tests/            单元测试 + fixtures/rotation/（确定性合成数据，generate.py 可重生成）
data/raw/         原始响应（只追加，含 SHA-256），不入库
data/processed/   清洗日线 + 基本面(em_fund_*) + manifest，不入库
artifacts/        回测产物、信号与分析报告，不入库
experiments/      因子 IC / TimesFM / Kronos 等研究实验（不进生产）
```

## 文档索引

| 文档 | 内容 |
|---|---|
| `CHANGELOG.md` | 更新日志：每个版本改了什么 |
| `docs/decisions.md` | 决策记录：每个重大方向性决定的理由、证据与状态 |
| `docs/data-source-ths-probe.md` | 同花顺数据接口探针报告（鉴权/复权口径/断层对比实测） |
| `docs/data-source-stock-probe.md` | 个股与基本面数据源探针报告（腾讯/新浪/东财、量纲陷阱、限流实测、90 天时点规则） |
| `docs/experiments/xiaodefa-data-pull-20260913.md` | xiaodefa 全量取数：数据集登记、去重与续传、已砍项原因、分钟覆盖核定与剩余缺口 |
| `docs/experiments/user-minute-ingestion-20260913.md` | 用户 1 分钟归档接入、241→48 聚合、代码身份修复与分钟能力审核 |
| `configs/pool-generated.json` | `build_pool.py` 生成的 ETF 候选池快照 |
| `configs/stock-pool.json` | `build_stock_pool.py` 生成的个股池快照 |

## 已知局限（每次报告自动披露）

1. **幸存者偏差**：池为当前在市 ETF/个股，历史回放未含已退市/清盘标的。全历史口径下回放越早年份池越窄（eligible_count 按年披露于长历史实验报告），幸存者偏差比 5 年窗口更严重。
2. **个股池行业分类不完整**：新浪行业分类未覆盖科创板（约 6 成池内标的行业记"未知"），行业分散约束仅对已知行业生效。
3. **前复权重写**：历史价格随新分红变化，复现以原始响应哈希为准。
4. 回测成本假设（佣金/最低佣金/滑点；个股另含卖出印花税 5bps）为研究默认，非账户实况。
5. 网页接口（东财/腾讯/新浪）无 SLA 且有 IP 限流：控制节律，重跑即可恢复。
