# 做T与一周短线：使用说明与当前证据

系统仅生成建议。读取行情、生成报告、回测都不会下单，也不会把“碰到价位”写成人工已成交。买卖由你操作，账户文件由你更新。

新短线固定候选**未通过收益验证**；当前价值是正确核算交易费用、现金、数量、止损预算和持仓复评，并为策略提供账户级验证。不能把测试段盈利解读为已经找到稳定赚钱的方法。

2026-09-05盈利优化新增`configs/short-term-candidate.json`研究候选：按用户确认的费用，宽基趋势过滤规则全期+28.29%（年化2.45%）、回撤8.43%，2022—2023为+7.15%，费用加倍全期+14.50%。通过本轮历史筛选，仍缺少全新样本与独立验收。通过`short --short-config configs/short-term-candidate.json`显式调用，仍不可执行；[完整实验与复现说明](experiments/short-profit-research.md)。用户回撤偏好约20%，用于研究筛选而非损失保证。

## 1. 账户输入

复制`configs/account.example.json`到`data/account.json`并填写。`data/`不入Git。不要写入券商密码、令牌。

| 字段 | 含义 |
|---|---|
| cash | 当前可用现金，不是总资产；每次人工成交后自行更新 |
| risk_budget | 新计划单笔费用后止损预算（元），不是保证的最大实际损失 |
| max_position_pct | 单只新短线仓位/一轮做T的资金占账户估值上限，0～1 |
| allowed_boards | 已开通权限的板块：main、chinext、star、beijing、etf |
| fees.stock / fees.etf | 实际佣金、最低佣金、滑点假设；个股卖出印花税默认5bps，ETF免 |
| holdings | 人工持仓，shares总数量、sellable_shares当日可卖数量、avg_cost实际成本 |
| open_t | 已人工成交第一腿、尚待完成的做T，不是委托单 |

示例是10万元现金、500元单笔风险预算、单标33%上限，仅为研究默认。不同账户应填写不同值。CLI的`--cash`、`--risk-budget`、`--max-position-pct`覆盖账户对应字段。

费用模板已按用户确认更新：股票万2.5、最低5元；ETF万1、无最低。滑点仍是假设单边万5。新候选的`account_fees`也保存这组费用，显式账户字段优先覆盖；只填股票费用不会抹掉配置中的ETF费用。模板的空持仓与风险预算仍须人工填写，不代表真实账户没有持仓。

账户估值优先使用可得收盘价；缺少持仓行情时使用显式`mark_price`或成本作为近似，报告含输入快照。金额上限不是“必须投入的金额”，条件不足可以不交易。

一条短线持仓示例（全部为示意值）：

```json
{
  "symbol": "sh600000",
  "name": "示例股票",
  "strategy": "short",
  "shares": 1000,
  "sellable_shares": 1000,
  "avg_cost": 10.0,
  "opened": "2026-09-04",
  "stop": 9.6,
  "target": 10.8
}
```

把对象加入`holdings`。`stop`/`target`是你实际采纳的计划，不会因每次刷新而重设。采纳新的跟踪止损时自行更新。非短线底仓可省略`strategy`，仍用于资金占用估算，但不会混入短线续持规则。

## 2. 人工指定标的做T

```bash
python -m quant.cli --config configs/_tmp_tx.json t0 --symbol sh510300 --account data/account.json
python -m quant.cli --config configs/_tmp_tx.json t0 --symbol sh510300 --account data/account.json --once
# 离线演示，不代表现在可交易
python -m quant.cli --config configs/_tmp_tx.json t0 --symbol sh510300 --shares 1000 --cash 10000 --offline
```

`--shares`是当日可卖底仓。未提供账户文件/股数时，从`position`人工成交记录中扣除今日买入数量；今日整仓`set`无法区分新旧股份，需以券商显示的可卖量显式覆盖。

报告包含每档数量、第一腿价格、费用后保本价、目标价、目标净额及风险退出价。没有扣费盈利空间的档位不列入新做T对。正T需要现金先买入；反T可先卖可卖底仓，再用卖出所得买回，初始现金为零也可能可行。

联网每300秒取一次qt；仅有效时段的新快照用于当轮参考。ST/*ST及退市名称、停牌/零成交快照、失效快照、失效日线不生成新T对。获得当日涨跌停价时，限制入场价并收窄目标价，再次扣费核算；风险止损仍可能因跳空/涨跌停无法按参考价成交。离线只显示研究计算。

科创板采用最低200股、超过部分1股递增；北交所最低100股、1股递增；其余默认100股整手。现有股票池未覆盖北交所全市场，账户允许该板块不代表数据已经齐备。

### 已做第一笔，差额允许隔夜

人工成交后更新`cash`、`holdings`，并把下面格式加入`open_t`。下面仅为格式示例：

```json
{
  "symbol": "sh600000",
  "first_side": "BUY",
  "entry_price": 10.0,
  "entry_date": "2026-09-04",
  "remaining_shares": 1000,
  "risk_budget": 100.0,
  "target_net": 100.0,
  "fees": {
    "commission_bps": 5,
    "min_commission": 5,
    "stamp_sell_bps": 5,
    "slippage_bps": 5,
    "lot_size": 100
  }
}
```

`BUY`表示先买待卖，`SELL`表示先卖待买回。`entry_price`始终是该笔实际成交价；首腿不重复加模拟滑点，另一腿保留滑点假设。可把当时报告的`fees`复制下来，避免修改账户费率后重写原交易假设。

同一标的存在未完成T时，程序只给该轮的保本/目标/风险退出及当前完成条件，不额外生成新T对。未到目标可隔夜，触及风险预算仍会提示人工处理，不会自动卖出或买回。每轮刷新重读账户，完成后由你移除相应`open_t`条目并更新现金/持仓。

当前每个`open_t`对象按一笔未完成数量计算最低佣金，不是券商多笔部分成交的会计对账系统；部分成交和多轮并行应核对实际费用与可用现金，报告不会替你成交或预占券商资金。

## 3. 程序推荐一周短线

```bash
python -m quant.cli short --account data/account.json
python -m quant.cli short --account data/account.json --offline
python -m quant.cli short --cash 50000 --risk-budget 300 --max-position-pct 0.25 --offline
```

从当前55只ETF和120只股票候选池中筛选，并经过数据、ST名称、板块权限和账户约束。**不是全A股每天穷举**；缺失/陈旧数据会披露并排除。联网优先最新名称排ST，离线无法核实最新ST变化。

固定规则为：`close > SMA20 > SMA60`且`R20 > 0`，上市/历史满252个交易日、20日中位成交额至少5000万元，按R20降序。下一交易日限价为收盘价减0.5ATR20；未成交当日失效，开盘跌破原止损则取消入场。1.5ATR止损、3ATR目标，费用后盈亏比至少1.5。这是首次待验证假设，不是已找到的最优策略。

买入数量同时受当前现金、单标金额上限、止损预算和交易数量规则限制；多条计划共享现金，不会各自把整份现金花一次；已有持仓/未完成T的同标的不重复建议加仓。

一周按**5个交易日**作复评点：扣费后仍有浮盈且收盘价在SMA20之上，才建议逐日续持，同时上移止损，止损不下移。研究默认最多10个交易日；否则给退出提示。新止损从下一交易日生效，回测不会拿当天已发生的高低价倒推成交。止盈、止损或退出都只是人工建议。

参数在`configs/short-term.json`。变更参数后需要重新验证；不得继续引用旧参数的历史结果当作新策略的验收证据。

## 4. 当前历史结果与复现

```bash
python -m unittest discover -s tests
python -m quant.cli --config configs/test-fixture.json smoke --fixture tests/fixtures/rotation/pool.csv
python -m quant.cli short --backtest --fixture tests/fixtures/rotation/pool.csv
python -m quant.cli short --backtest --output artifacts/short-term/my-fixed-rule-run
```

首轮冻结参数回放使用本地腾讯前复权缓存，2016-01-04至2026-09-04共2594个交易日；175只候选经过数据门禁后纳入172只、排除3只。首轮证据目录：`artifacts/short-term/20260905-fixed-rule-backtest/`，`report.json`含配置快照、排除清单、费用与指标，`replay.json`含现金/净值/逐笔成交代理/未平仓持仓。

| 区间 | 扣费收益 | 最大回撤 |
|---|---:|---:|
| 全期 | −8.31% | −24.46% |
| 研究段 | −12.30% | −18.18% |
| 验证段 | −4.01% | −11.14% |
| 测试段 | +8.91% | −11.10% |

1175笔平仓；总费用及滑点22595.40元。测试段为正不能抵消验证段失败；本轮未再按结果搜索参数。

组合回放共享现金、下一交易日成交、T+1、止损跳空按更差开盘价、日内双触及按止损优先；一字/无成交日不虚构成交，停牌持仓继续估值；期末未平仓按收盘估值而非强行计作已卖出。

证据局限：当前在市池造成幸存者偏差和池构建前视；历史ST名单不全；前复权历史会重写；日线触价是成交代理，缺少分钟顺序与盘口；金额固定费率假设非账户真实结果。研究/验证/测试按连续时间切分，未随机打乱，但不是严格无偏样本外。报告不宣称已验证盈利，也不将其作为做T择时证据。

现有V3月频仍使用原来的`signal`/`plan`/`backtest`；旧`daily`保留作历史研究。当前改动经过实现者自测，尚未取得独立策略验收PASS。

工程验证：178项离线单元测试通过；V3 fixture smoke通过；新短线fixture回放完成11笔平仓并保存现金净值记录（仅验证工程链路，不作为收益证据）。旧daily历史报告使用当时的费用/数量实现；修复最低佣金及板块数量规则后重跑数值可能变化，旧报告原件保留。

规则与数据依据：[上交所股票ETF的T+1说明](https://www.sse.com.cn/assortment/fund/etf/question/c/c_20240118_5734755.shtml)、[上交所2026年交易规则](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml)、[北交所交易规则](https://www.bse.cn/jygl_list/200028217.html)。qt价格限制字段通过[腾讯原始快照](https://qt.gtimg.cn/q=sh510300)核对。
