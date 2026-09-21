# 预登记：F3R3 动态引擎因子组合重测（exp-20260921-factor-round-f3r3）

运行前冻结。本文件在任何引擎运行之前写定，判据不得事后修改。

## 1. 目的与可证伪假设

引擎已于 2026-09-21 重建完成动态主线路径（`execution_clock='halfday'` 半日时钟
+ `intent_provider` 决策点账本反馈入口）。F3R1 的 0/8 门结论是在旧引擎
v1.3 legacy 时钟 + 静态意图帧上取得的；本实验在重建后的引擎上重测同一组合，
检验结论对执行模型的敏感性。

- **假设 H（可证伪）**：F3R1 的淘汰结论（两臂均未过八门）在动态引擎上成立。
  若任一臂在动态引擎上通过全部八门，H 被拒绝，执行模型差异成为主导因子，
  F 线结论必须重写。
- **预期方向（非判据）**：动态半日重发预期显著提高成交率（门 8），但收益、
  回撤、换手门的失败结构预期大体保持。
- 组合本身（因子、去重、加权、席位规则）与 F3R1 完全相同，**零新试验消费**：
  本实验不搜索参数、不比较变体，只换执行引擎。

## 2. 输入（与 F3R1 相同，逐字复用）

- F2R1 存活者：`artifacts/runs/20260920T190224-f2r1-rebuild-85e7f7e5/f3_inputs/`
  （43 存活、`f2r1_survivors_corr.csv`、族目录因子帧）；
- 去重：|ρ|≥0.6 连通分量，代表 = max |t_ic|（并列取覆盖率高者、再取字典序），
  与 F3R1 逐字相同；确定性重算应得到同样的 20 个代表，若不一致即运行失败；
- 组合：可执行池 = R16 池 ∩ 覆盖（≥ceil(M/2) 代表非空）；分量 =
  (rank_pct−0.5)×sign(ic)；两臂 F3-EW（等权）与 F3-ICW（|icir| 权重）；
- 席位：buffer membership K=10、entry top-10、exit rank>20、q5 关闭；
- 数据 pin：daily `baostock-daily-20260917`、halfday `halfday-bars-20260918`
  （manifest sha 前缀 `2a414174b5df2eee`）、stk_limit 聚合
  （前缀 `3c53abf3b0c39b42`）、rqalpha bundle v2-1；开发窗 2015-01-05..
  2020-12-31，val 2021–2024 零接触，2025+ 冻结零接触。

## 3. 执行模型（与 F3R1 的全部差异，仅此一处）

| 项 | F3R1（旧） | F3R3（本轮） |
|---|---|---|
| 引擎 | band_engine v1.3（sha16 `31022babbc2858ea`） | 重建版（sha16 `bcbdd44bb855b803`，见 §8 冒烟修订；运行时 pin 校验） |
| 时钟 | legacy | `execution_clock='halfday'` |
| 意图来源 | 单张静态帧，一次性提交 | `intent_provider`，每决策点注入 |
| 买入生命周期 | 意图存活一个月，引擎自动 re-anchor | 意图半日失效；provider 每决策点按账本重发 |
| 席位置空 | 买入整月未成交即空仓至再入池 | 取消：在池未持有即持续重发 |
| 卖出生命周期 | risk 意图月内顺延 | 同左（引擎 m3 顺延 + K=3 兜底不变） |
| 初始现金 | 200,000 | 200,000 |

provider 语义（预登记冻结，运行前不可改）：

1. 信号日 T 的月末 pm 决策点起，生效信号 = 最近满足
   `T' < day 或 (T' == day 且 sess == 'pm')` 的信号日；
2. 买入条件：symbol ∈ 当前 member 集合 且 决策点账本未持有 → 发
   buy（target_weight=0.10，priority=composite 排名，source=T，expiry=下月
   信号日+1 历日）；已持有则不发；
3. 卖出条件：账本持有 且 symbol ∉ 当前 member 集合 → 发 sell
   intent=risk（source=T，priority=10^6，expiry=下月信号日+1）；卖出由引擎
   m3 顺延 + K=3 兜底负责跨半日执行，provider 不重复发；
4. provider 只读本账本 ledger（cash、equity_snapshot、positions），不读
   控制组权益、不读未来行情；
5. 买入/卖出条件互斥，同 symbol 不会同时存在活跃 buy 与 risk sell。

数量口径：引擎对 buy 用 `target_weight × 决策点权益快照` 重算整手数量
（真实账本反馈，引擎内建）；卖出 full 退出、T+1 可卖约束、当日新买冻结
均由引擎处理。

## 4. 判据（与 F3R1 逐字相同）

八门 + 目标列，基准 B1(m)_F3 与 B3′_F3 在同一可执行池重算（与 F3R1 同
代码路径，确定性）：

1. 净 CAGR > 0；
2. 对 B1(m) 净超额 ≥ +2.0pp；
3. 优势年 ≥ 5/6（对 B1(m) 逐年）；
4. 回撤 ≤ 20% 且 ≤ B1(m) 回撤；
5. 单边年换手 ≤ 6；
6. 单票最大权重 ≤ 40%；
7. 净 CAGR ≥ B3′ + 1.0pp；
8. 执行率 ≥ 95%（7.7-m6 归因口径：座位-信号聚合，(filled+rule_blocked)/
   (filled+rule_blocked+terminated)；动态重发下同一座位同一信号的多次
   重发按一个座位计）；
9. 目标列（非门）：dev 净 CAGR ≥ 10%。

门 8 归因在动态模式下的座位定义：一个 (symbol, side, source=信号日) 为一个
座位；该座位的全部意图中任一成交即 filled；整月（至下一信号日）无成交为
terminated:expired_seat；曾被订单规则阻断（below_min_lot / void_no_position /
void_insufficient_cash）且未成交为 rule_blocked。

## 5. 冒烟与预算

- 冒烟：2015-01-01..2015-03-31 小窗先跑两臂，只验证工程链路（provider 合并、
  意图生命周期、成交入账、曲线产出），冒烟数字不进入任何结论；
- 全期预算：墙钟 60 分钟、峰值内存 8GB，超限即 failed 留痕；
- 预计规模：约 71 个信号月、每臂意图数千条（半日重发），引擎合并规则为
  O(意图数²) 级，冒烟阶段实测外推确认预算后再跑全期。

## 6. 台账与停止规则

- 试验台账：strategy_line 264 → 266（两臂各 1 次）；factor_line 零消费；
- 停止规则：全期两臂跑完即停；≥1 臂过八门也不自动进入 val，须用户单独
  批准（与 F3R1 相同）；val 2021–2024 零接触；
- 失败语义：任何 pin 不匹配、去重代表与 F3R1 不一致、provider 违反合并
  规则（引擎 fail-closed 拒绝）均为运行失败，留痕不重试。

## 7. 运行前登记

- 运行目录：`artifacts/runs/20260921T024449-f3r3-dynamic-45037d/`；
- 引擎 sha256 运行时重新计算并写入 manifest，与 `bcbdd44bb855b803` 前缀
  比对，不匹配即失败；
- manifest 时间缺陷修复：started_at 用系统 UTC 时钟（不再从 perf_counter
  换算，F3R1 的 1970 错时间不重现）。

## 8. 冒烟发现与运行前修订（判据不变）

2015Q1 冒烟暴露引擎缺陷并已在正式运行前修复，预登记同步更新：

1. **缺陷**：半日时钟下 am 决策点对持仓符号一律要求当日 am bar
   （fail-closed）。真实数据中停牌日无半日 bar，守卫把正常停牌当数据
   缺陷拒绝运行（sz.000333 于 2015-03-26..30 停牌触发）。
2. **修复**：持仓符号当日停牌（日线无成交行）时，am 快照用冻结的最近
   成交收盘（`official_close_strict`，严格早于当日、无未来信息）估值；
   当日有成交却缺 am bar 仍为硬数据缺陷，保持拒绝。判据、门阈值、
   provider 语义均未改动。
3. 修复后引擎 sha256 前缀 `689e2ba11bd21d0a` → `bcbdd44bb855b803`，
   新增合成测试 d8/d8b（停牌冻结 mark 手算 + 交易日照缺 bar 拒绝），
   全仓 617 passed。冒烟数字不进入结论。
