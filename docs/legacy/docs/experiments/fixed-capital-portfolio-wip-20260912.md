# 固定20万元组合适配层 WIP 状态（2026-09-12）

状态：**未验收 / 不可用于研究结论 / 不是推荐规则冻结 / 不授权真实运行**。
本批因用户收缩验证范围暂停：保存当前代码、测试与已知缺陷，不再新增实现、
测试或修复轮；不回滚他人修改，不提交上线。恢复需候选统计证据与主审重新授权。

## 已落盘交付物（未提交）

- 适配层：experiments/factor_miner/fixed_capital_portfolio.py（新文件，未跟踪）
- 合成测试：tests/test_fixed_capital_portfolio.py（新文件，未跟踪）
- 契约草案（主审设计稿，本批未改动）：docs/plans/fixed-capital-portfolio-integration-20260912.md
- 本 WIP 说明替代原计划的正式交付报告。

未触碰项（已核）：本批未编辑 quant/execution.py 与 quant/market.py。工作区中
quant/portfolio_candidate.py 与 experiments/factor_miner/backtest.py 的既有改动
来自他人/先前批次，本批既未改动也未回滚、未提交。

## 已完成的接线（仅合成验证，非真实对账）

- 外部冻结目标权重输入；初始现金200000仅注入一次；外部现金流单列并从收益
  剥离；禁止自动补资。
- 复用 execution.Replay 的 T+1、可卖库存、方向限幅、参与量上限与逐笔费用。
- 时序门禁：data_as_of 不得早于日线可得时刻（收盘前输入拒绝）；PriceBook
  拒绝同日同码多行与同日多时点（只支持日线每股一行）。
- 公司行为每日恰一次入账，先于目标股数与可卖量计算，不依赖当日是否有调仓
  订单或净值是否有效；送转只改股数。
- 规划口径披露：卖出预期净额只用于订单规划，真实现金由 Replay 按 bar 实时
  校验，未成交卖出不垫资。
- 净值：缺价在 strict 模式拒绝有效净值、绝不默认0；stale_ok 使用带日期的
  既知价并标陈旧。

## 测试现状（本次运行记录）

- tests.test_fixed_capital_portfolio：40 tests OK（约0.011s），全部为合成手算断言。
- 共享套件回归：tests.test_execution + tests.test_execution_audit_boundaries +
  tests.test_backtest + tests.test_factor_miner_engine = 103 tests OK（约8.6s）。
- 修复前后对照（同一合成反例，独立复算脚本，非正式验收）：
  无订单调仓日分红 pre-fix cash=950.25/div=0 → fixed 10900.25/9950；
  送转 pre-fix 卖出19900股 → fixed 39800股；
  净值无效早退 pre-fix div=0 → fixed 9950；
  有订单分红日两版一致（无重复计）。

## 已知缺陷与未决项（不得据此下研究结论）

1. 全部为合成 fixture，未经任何真实行情或 TRAIN 抽样对账；未读 VALIDATION/LOCKBOX。
2. 除权价调整由输入价格序列负责：适配层按原始价读取、不重定除权价。若输入
   序列未含除权跳变，分红/送转日净值会出现人为跳变，属已知未验证假设。
3. 只支持日线日频（每股每日一行、同日单一时点）；不扩建分钟能力。
4. 主审预读指出的时序缺口已在现有模块内修复并覆盖反例，但尚未经独立复核与终裁。
5. 主审对 _apply_ca 的前提「Ledger.apply_dividend 返回 None 会 TypeError」与
   当前 quant/execution.py 不符（实测返回500.0并写入 kind=dividend 流水）；
   本实现改为从新增流水推导金额、不依赖返回值，属加固而非修正既有错误。
6. 原计划正式报告中的代码 diff、共享文件未改动理由、Ledger.equity 缺省0风险
   说明因范围收缩未单独成文，要点已并入本说明。
7. 与本批无关的既有失败（先于本批存在，本批未修）：discover 因子挖掘套件
   （test_factor_miner_*.py）628 tests 中 4 failures + 8 errors，全部为
   lockbox-admission（LockboxDisciplineError: upstream statistical validity
   missing or not VALID），源头 experiments/factor_miner/director.py 对 R0
   描述性契约写入的 statistical_validity=UNKNOWN 采取 fail-closed。经临时
   移走本批两个文件复跑，失败集合相同，确认为先前存在。

## 恢复条件

有候选统计证据且主审重新授权后恢复。届时应先独立复核本模块，再按授权范围做
TRAIN 抽样对账，然后决定是否进入下一步。本 WIP 不构成任何放行。