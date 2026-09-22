# 证据与接口规格 v1.0

本文是待实施接口合同，不声称仓库已支持这些字段。实际映射应在C1完成并经审阅，未知字段标缺失，禁止臆造。

## 1. 通用约定

所有时间必须含时区/交易日/半日。研究市场时间用 `Asia/Shanghai`；机器日志用UTC并保留偏移。不得按用户电脑或顾问所在时区猜交易日。日期取固定ISO格式；证券含交易所；金额/价格/比例明确单位，推荐JSON字符串表示Decimal，CSV保留完整原始值和展示值两列。

标识：`event_id`是信息事件；`intent_id`是经济意图；`order_id`是具体半日订单；`fill_id`是成交；`position_cycle_id`是一次持有周期；`clip_id`是取得批次。重挂生成新order_id但关联同intent_id和上一订单；不能按“股票+近三日”模糊代替唯一对应。批次ID与证券持有周期不能混用。

所有产物记录 `schema_version`、`run_id`、`code_commit`、`source_sha256`、`contract_sha256`、`dataset_id`。文件原始SHA256与规范化数据SHA256分开：前者发现文件改写，后者用于跨平台换行、Parquet元数据不同下的经济等价比较。不得更新旧哈希基线掩盖差异。

## 2. contract_snapshot.json

至少含：initial_cash、direction、universe权限、max_positions、max_new_day0_candidates、name_target_cap、total_funding_cap、fee_schema（包括每步舍入）、decision_schedule、entry_price_policy、strict_crossing、gap_fill_policy、settlement_delay、T+1/round_lot、risk_fallback及intent分类、corporate_action_policy、valuation、dev范围、label_boundary、当前有效用户授权。

每一项都有 `value / source_path / source_section / source_commit / authority / mutable_in_stage / approved_by_reference`。未知非关键项明确null；关键硬规则未知不能运行。不能让实验配置覆盖硬字段；配置校验须列出最终resolved值和全部override来源。

## 3. orders.csv（实际具体订单，不仅是目标意图）

`run_id, event_id, intent_id, order_id, replaces_order_id, symbol, side, intent_class, exit_reason, created_at, decision_at, information_cutoff, live_from, expires_at, source_signal_at, anchor_price, trigger_cap, limit_price, tick_size, requested_shares, target_weight, target_notional, priority, reserved_cash, available_cash_before, price_legal, eligibility_status, order_status, status_reason`

`target_weight`和`target_notional`的互斥语义沿合同；最终匹配必须有解算后股数与限价。`trigger_cap`非空不代表`limit_price`等于它，需显式核对。无价格锚、过期行情、未来输入必须给出拒绝原因，不填写0价替代。

## 4. fills.csv

`fill_id, order_id, intent_id, event_id, symbol, side, fill_at, session, shares, price, gross_notional, commission, stamp_tax, other_contract_cost, stress_surcharge, total_cash_effect, fill_type, clip_created_id, remaining_order_shares`

实际费用、压力附加损耗分开列。不存在“建议成交价”字段冒充price。部分成交每笔独立，订单完成状态由累计数量决定。风险K=3兜底有独立fill_type，不混入普通严格穿透。

## 5. corporate_actions.csv

`action_id, symbol, effective_at, available_at, action_type, share_ratio_num, share_ratio_den, cash_per_share, source_units, share_rounding_policy, cash_booking_at, entitlement_shares, source_path, source_sha256`

按照冻结合同记录送转比例和分红，明确每股/每手。不同权利登记与支付时点按现有模拟合同处理并披露，不为改善收益改变。分红计入现金的同时不能再把含分红复权价格用于账户市值。

## 6. ledger_snapshots.csv

`run_id, snapshot_at, free_settled_cash, reserved_cash_component, unsettled_sale_proceeds, cash_total, position_mv, equity, fee_cumulative, dividend_cumulative, realized_pnl, unrealized_pnl, pending_order_count, held_name_count`

现金字段互不重复：如果reserved是free的子项，公式必须明确；不能在两处相加。权益基本恒等式：现金总额+当前持仓市值，无虚拟未来收益。每个`positions/clip_snapshots`表另列symbol/shares/sellable_shares/clip_acquired_at/remaining_cost/mark/mark_at/mark_source。

## 7. event_funnel.csv（事件初次接纳）

`event_id, symbol, financial_period, previous_announcement_id, current_announcement_id, announcement_at, available_at, decision_at, family, type_improved, numeric_revision_up, numeric_data_valid, prior_profit_low, prior_profit_high, current_profit_low, current_profit_high, type_previous, type_current, held_before, pending_before, admission_rank, admission_rule, available_seats, portfolio_risk_state, initial_disposition, rejection_reason, first_intent_id`

`initial_disposition`互斥枚举：`accepted / already_held / already_pending / slot_full / risk_blocked / missing_anchor / invalid_eligibility / cap_failed / invalid_data / outside_scope`。一个事件只占一行；后续重新评估要有另一个episode_id，不能双计全事件数。全部事件必须能分桶守恒，包括没给出订单的事件。

## 8. event_order_lifecycle.csv

`event_id, intent_id, order_id, at, from_status, to_status, reason, filled_shares_cumulative, live_opportunities_used, ttl_deadline, seat_reserved, released_seat, source_identity`

各状态时间顺序可复核。`slot_full`属于未签发原因，不属于下单未成交；`risk_blocked`不冒充席位满。只要进入订单阶段，就用实际订单日志区分`never_crossed / suspended / limit_illegal / cash_short / below_lot / expired / cancelled_cap / cancelled_signal / replaced / partial_fill / full_fill`。

## 9. event_returns.csv

`event_id, return_kind, anchor_at, anchor_price_kind, anchor_price, fill_id, label_end_at, exit_order_id, exit_fill_id, window_complete, n_market_sessions, n_own_sessions, corporate_action_adjustment, gross_return, fees, net_return, comparator_id, comparator_weight, comparator_return, paired_increment, missing_reason, censoring_reason`

`return_kind`明确：`signal_marked_20 / fill_marked_20 / executable_fixed_horizon / realized_strategy_cycle`。标记收益不是保证可退出收益。缺窗口时net_return不得填0；样本保留，主均值只用预登记完整窗口，同时披露删失分母与缺失机制。

比较必须使用成对同起止日期；不能用A股自身第20日与对照股自身第20日落在不同日期的收益，冒充同市场窗口超额。成交价和官方估值的单位转换有显式公式，不能拿价格复权因子当股票股数比例。

## 10. 指标公式

- 无外部申赎时：`CAGR=(E_end/E_start)^(365.25/calendar_days)-1`。初始权益为入场前500000，不能以首笔成交日收盘为起点悄悄去掉首日费用/亏损。全项目窗和实际可投资窗并列。已有旧口径另列复现值。
- `MDD_magnitude=max_t(1-E_t/max_{s<=t}(E_s))`，使用所有官方日终权益，初始500000纳入高点基准。结果存正幅度，展示负号另处理，防止−30%被误判“小于20%”。
- 首年：首年末权益/评价窗初始权益−1；后续年：当年末/上年末−1。只有实际覆盖的年份，不能用缺失或空仓年份凑4/6过门。
- 每日股票暴露：实际股票市值/权益。全窗均值、实际交易期均值、峰值分别报告；不能用四席×10%替代真实暴露。
- 换手：买入、卖出名义/日均权益分别列；年化按实际观察长度，不能混用单双边。
- 成交率：订单ID口径、意图口径、股数口径、名义口径分别列；重挂与重复发单不等于新增事件；零订单时为NA，不是100%。
- 回撤恢复：峰值日、谷底日、恢复日、是否未恢复、市场交易日与日历日两个时长；期末未恢复不得截断成“恢复用时”。
- 配对净增量：同事件和对照的净收益差，再按预登记权重汇总。均值减中位数有不同解释，必须单独命名。
- 毛/净差只在同一交易路径上解释为费用；不同动态路径之间是政策对照，不能直接当费用或信号归因。

## 11. 稳健性、台账与证据验证

聚类区间需记录重采样单位、固定seed、块长/簇定义、重采样次数、缺失处理与有效簇数。不报告“未来必达概率”。信号/策略次数、工程复现、结果查看分三账；所有新增筛选与分组的探索同样留痕。

`run_manifest`必须有真实命令、UTC起止、exit_code、pid/执行器、代码/配置起止hash、输入清单、输出清单、资源、期望臂与实际臂、run_state、错误和未完成内容。不能把一个始终返回completed的wrapper当真实成功。

独立审阅证据独立路径保存，引用具体code/contract/data/config哈希。新的提交或输入改变后旧review失效。审核字符串和本包检查器不提供真实身份认证，须由用户或受保护平台执行权限边界。
