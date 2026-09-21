# VectorBT T3 试点计划（2026-09-14）

## 背景与授权边界

- 用户 2026-09-14 批准：先试点 VectorBT 能否用于 T3，产出计划与报告，可行再做最小 adapter 原型。
- 前置事实：vectorbt 1.1.0 已装入独立环境 `D:/AI/workspace/vectorbt-pilot-env-20260914`，但 import 失败：plotly 7.0.0 移除 `scattermapbox`，vectorbt `_settings.py` 主题模板仍引用。本批修复：plotly 固定 6.9.0（<7），import 恢复，失败说明保留于报告。
- 项目最新状态：T3-A CHANGES_REQUIRED，四条 PIT/身份问题阻断真实候选；本批只用合成夹具，不碰真实数据、不启动 T3 全量。
- 硬边界：不改现有研究代码与正式入口（`experiments/`、`quant/` 只读复用）；不把现有 L0 改名成 VectorBT；不改冻结口径；工件只新增不覆盖。

## 阶段一：探针（已完成，证据 `artifacts/vectorbt-t3-pilot-20260914/probes/`）

| 探针 | 结果 |
|---|---|
| 环境 `env.json` | Python 3.11.15 / vectorbt 1.1.0 / plotly 6.9.0 / numpy 2.4.6 / pandas 3.0.5 / numba 0.67.0，进程内 import 约 9.5s（首日冷），日常新进程约 3.5s |
| 能力 `caps.json` | from_orders 具备 size_type/direction/price/fees/fixed_fees/slippage/min_size/size_granularity/allow_partial/call_seq/cash_sharing/group_by 全部关键参数 |
| 语义 `semantics.json` | 7/7 通过：共享现金部分成交且现金永不为负、组合价值恒等式误差 0；费用+滑点算术误差 0；逐单元格费率矩阵可精确表达 max(最低佣金, 费率) 加卖出单边印花税；整手 137到100、250到200、50不成交；同 bar 买卖冲突不产生当日来回；订单可落在下一 bar 并按其开盘价成交；call_seq 可强制组内先卖后买 |
| 手算账本 `handcalc.json` | 81/81 断言通过：独立字典模拟器（整手网格、权重降序买入、最低佣金、印花税）与 vectorbt 在每笔订单（代码/日/向/量/价/费）与每日现金/持仓/净值完全一致（容差 1e-6 至 1e-9） |
| 计时 `timing_run1/2.json` | 合成面板实测：300资产*250天*12次调仓 模拟约 0.015-0.025s；800*500*24（1.87万笔订单）约 0.074-0.097s；结果可复现；numba 预热 0.4-2.9s |
| fp 基线 `fp_baseline.json` | 同规模合成面板 fixed_capital_portfolio 实测：50*250*12=0.024s（301 笔成交）、150*250*12=0.060s（395 笔），对账全部 matches |

计时结论（只按实测说话）：L1 月频调仓规模下 fp 本身不是瓶颈，vectorbt 的速度优势在该场景不构成替换理由；其潜在价值在更大规模批量或作为独立交叉核算器。未实测的规模不外推。

## 阶段二：最小 adapter 原型（本批执行，范围收窄）

位置：`artifacts/vectorbt-t3-pilot-20260914/adapter/`，独立于正式入口。

输入兼容 fixed_capital_portfolio 子集：weights_series（date/signal_at/data_as_of/weights）、日线 bars、fees_by_code（commission_bps/min_commission/stamp_sell_bps/slippage_bps/lot_size/min_shares）、initial_cash、cash_policy。

实现要点：
1. 规划层移植 fp 语义子集：执行日=信号日后首个有行情交易日；参考价=信号日收盘；目标股数=整手网格向下；卖出（代码升序）后买入（权重降序、代码升序）；现金约束按 cash_policy（legacy 含预计卖出净额 / opening_cash_only 仅开盘现金）；费用公式直接调用仓库 `quant.execution`（只读复用，保证逐分一致）。
2. 执行层用 vbt from_orders：price=执行日开盘、逐单元格有效费率矩阵（复刻 max(最低佣金,费率) 加卖印花税）、min_size/size_granularity=手数、group_by 加 cash_sharing、call_seq 卖列在前。
3. 涨跌停近似：执行日开盘越出限价（参考价加减速 bps）则该单当日不成交（对齐 Replay 日线行为）；停牌日无 bar 不下单。参与率、逐笔量约束不建模（合成夹具量充足），差异显式披露。
4. 结构性 T+1：月频执行日本身间隔至少 1 个交易日，当日买不可当日卖由订单生成规则保证；分钟级 T+1 不在本批范围。

验收标准（合成夹具交叉对照，`adapter/crosscheck.json`）：
- 场景 A：手算全账本场景；场景 B：现金争用（A 0.5/B 0.5 缩量）；场景 C：最低佣金小单；场景 D：opening_cash_only 卖款不得垫资。
- fp 与 adapter 的成交（代码/向/量/价/费）、期末现金、逐日净值全部相等（容差 1e-6）或差异逐项可解释并披露。

## 明确不做

- 不接入 L2 分钟回放、公司行为、代码变更、外部现金流、独立日历路径（fp 已有能力继续作为权威）。
- 不替换 T3 冻结清单、不改 L0 现有 NumPy 引擎身份与结果。
- 不据本批结果宣布任何研究结论（合成数据无研究含义）。

## 产出

- 计划（本文件）、试验报告 `artifacts/vectorbt-t3-pilot-20260914/report.md`（含安装版本、命令、结果、限制、L0/L1/L2 建议）。
- 所有脚本与 JSON 证据同目录留档，只新增不覆盖。
