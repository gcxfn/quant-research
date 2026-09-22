# C3 案例报告：独立成交核验与公共策略衔接

- 阶段：C3（主计划第 8 节 C3-A/B/C，验收 G3）
- 证据目录：`docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/`（下称 `<EV>`）
- 实现者：ZCode 子代理（implementation agent，new-provider-deepseek-v4.1-flash）
- 代码基线 HEAD：`ae226d9`；本阶段新增 `src/quant/research/reference_matcher.py`（重写接管）、
  `reference_matcher_reconcile.py`、`c3_semantic_chain.py`、`tests/test_reference_matcher.py`、
  `tests/test_reference_matcher_state.py`
- 解释器：`.venv/Scripts/python.exe`；数据只经 `quant.data.dev_sandbox`（C1 冻结访问层）；
  run 产物只读；未跑新回测；合成场景全部标注
- 状态：`engineering_state = pending`（等独立审阅）；本报告的所有断言都可用 `<EV>/run_records/` 里的命令复跑

---

## 0. 一句话结论

在 9 个已具订单级产物的臂上，**5,260 张限价单 + 74 次 K=3 兜底尝试**由一套完全不 import
`quant.backtest` / `quant.portfolio` 的独立实现重新判定，**成交与否 / 日期 / 半日 / 股数 / 价格 /
未成交原因 / 末状态 100% 一致**；4,948 笔成交中 4,853 笔连费用都逐分一致，其余 95 笔只差
≤0.01 元（C2 已裁定的「每笔现金变动处 HALF_UP 到分」vs 引擎 float64 的表示差）。
C-05 关闭：`×1.01` 是**签发门槛**，实际提交限价 = 决策点锚价，39/39 观测 + 引擎建单代码行互证。

---

## 1. 接管审查发现（`reference_matcher.py` 半成品）

接管时该文件 758 行、未经过任何测试、无任何调用方。逐项对照冻结合同
（`docs/plans/p3-band-contract.md` §7/§8、C0 `contract_snapshot.json`、C1 `interface_contract.json`）
核验后**保留**的结构：`Bar`/`LimitRow`/`Order`/`Verdict`/`Clip`/`Book`/`BarTable`/`LimitTable`
数据模型与原子判定骨架（严格穿透、缺涨跌停行保守拒绝、T+1 逐 clip、现金三分离、K=3 兜底）。
**修复的 10 项缺陷**（原草稿的实际行为，不是风格问题）：

| 编号 | 缺陷（原草稿行为） | 处置 |
|---|---|---|
| A1 | `match_open` 对任何卖单一律抛 `ValueError`——开环主路径实际不可用（桩） | 改为显式状态契约 `judge_open(orders, states)`；卖单缺状态时 fail-closed 报错（不臆造数量、也不静默跳过）。回归测试 `test_sell_without_state_fails_closed` |
| A2 | 卖单费率调用漏传 `symbol`，ETF 卖出被错加印花税 | 补传 symbol，并加 `set_etf_symbols()` 供开环模式注入名录 |
| A3 | `Book.book_sell` 用 `list.index(clip)` 定位批次——`Clip` 是值相等的 frozen dataclass，**同值批次会改错对象** | 改为按 `seq`（批次身份）精确消耗 |
| A4 | 无 `expires_at` 守卫：过期订单只要被放进 `run()` 就会被判定成交 | 加守卫（TV-B13） |
| A5 | 无 `replaces_order_id`/同 intent 覆盖规则，被替代单可与替代单同时成交 | 同生效半日的同 intent 多单只保留决策点最新一张，其余登记 `replaced`（TV-B13） |
| A6 | 无部分成交语义：卖单超可卖量时按可卖量成交但不区分末状态，也不登记剩余股数 | `Verdict.remaining_shares` + `partial_fill` 末状态 + `intent_requested_shares`（TV-B14） |
| A7 | 风险 K 计数在与其无关的拒绝原因上也会累加 | 收敛为白名单（`_RISK_COUNTED_REASONS`：never_crossed/limit_illegal/limit_missing/t1_locked），停牌冻结、no_position 清状态 |
| A8 | 无公司行动份额变换 → 除权日后可卖量与 K3 兜底数量会错 | 加 `Book.apply_split`（half-up、新增份额记当日取得 = m4 语义） |
| A9 | `Verdict.status` 缺 `partial_fill`，映射未与合同枚举核对 | 按 C1 `order_status` 枚举重排映射表 |
| A10 | `run()` 允许从 bar 表隐式推断日历，会静默丢掉完全停牌的半日 | 改为强制显式日历；回归测试 `test_run_requires_explicit_calendar` |

另有一处**语义判断**（保留原草稿的正确选择，但在报告中登记）：K 计数键取
`(symbol, source)`，引擎代码实际按 `symbol` 建键 + source 变化时重置。两者在「一标的一站立单」
下行为等价，matcher 的键更贴合同文字（§7.7-M1「计数键 = (标的, intent=risk, 来源信号)」）。

## 2. 对账驱动实施中发现的 7 个问题（都是我这个新驱动的，不是引擎 bug）

第一轮跑出来的差异全部定位为**驱动自己的状态重建错误**，逐条修好后归零。如实登记，因为它们
正好说明「状态重建错一处，成交判定就整体偏掉」：

| 编号 | 现象 | 根因 | 处置 |
|---|---|---|---|
| D1 | NOACCT-bin 39 笔「引擎说资金不足、matcher 说成交」 | 只在**有订单/成交事件的半日**推进结算，`pend_next_day` 一直挂着 → 可用现金少 122,800.77 元 | 按**交易日历**（沙箱日线并集）逐半日推进结算 |
| D2 | 全部臂现金比引擎少 9,975.48 元 | 公司行动只在**有订单事件的除息日**应用，无事件的除息日被静默跳过 | 按 `(上一推进日, 当日]` 区间扫全部除权/除息日 |
| D3 | sz.000711 2017-04-18 分红多算 270 元 | 同日既有送转（×2）又有分红，先变换份额再用变换后的股数算权利数 | 分红权利数用**除权前**持股快照 |
| D4 | 3 臂各 1 条兜底行标的被解析成 `no_limit_info` | `market_exit_filled` 事件不带订单号/标的，`detail` 前缀是说明文字 | 从 `fill_type == 'market_fallback'` 的**成交行**恢复标的 |
| D5 | 同上 | 兜底成交复用的是**站立风险单的 order_id**（不是 K3FB 合成号），订单号正则抓不到 | 同上；正则只作 fallback |
| D6 | 加「同半日现金预留」后 FULL-bin/NOSACCT 反而多出 59 处差异 | 既按引擎事实成交入账、又累加预留量 = **双重扣减** | 去掉预留：引擎事实成交在半日内逐笔入账，后面的同半日订单自然只看到高优先级成交后的余额 |
| D7 | NOACCT-bin 仍有 39 笔资金类差异 | 判定次序用了事件文件顺序，而不是合同 m7 的「买单按 (priority, symbol) 竞争现金」 | 判定次序改为「先买单（priority, symbol），再卖单」 |

## 3. C3-A 开环匹配（真实 run）

产物：`<EV>/order_reconciliation.csv`（5,334 行 = 5,260 限价单 + 74 兜底尝试）、`reconcile_summary.json`。

订单来源（先探明产物结构）：每臂 `outputs/<arm>_events.parquet` 是**订单级**事件日志，
`filled_limit_* / not_penetrated / void_* / below_min_lot / session_expired` 行带 `order_id` +
`limit_price`；`market_exit_*` 行不带订单号，其标的从同半日的 `market_fallback` 成交行恢复。
**缺订单日志的臂**：`20260922T002611-eventfam-attrib2-eed5cf` 只有 B1 汇总结论（无订单事件），
因此只用于 C-05 追踪与席位账，并登记为 C4 缺口（若需要该 run 的订单级对账，须重跑留产物）。

| 臂 | 限价单 | 核心字段一致 | 兜底尝试 | 兜底一致 | 成交逐字段一致 |
|---|---|---|---|---|---|
| FULL-bin | 903 | 903 | 7 | 7 | 664/670 |
| NOACCT-bin | 1246 | 1246 | 7 | 7 | 895/932 |
| NOSNR-bin | 712 | 712 | 11 | 11 | 493/498 |
| SIG-old | 847 | 847 | 4 | 4 | 642/659 |
| SIG-reg | 876 | 876 | 11 | 11 | 635/653 |
| A1 | 207 | 207 | 32 | 32 | 146/150 |
| A2 | 173 | 173 | 2 | 2 | 136/140 |
| B1 | 102 | 102 | 0 | 0 | 79/81 |
| B2 | 194 | 194 | 0 | 0 | 163/165 |
| **合计** | **5260** | **5260** | **74** | **74** | **4853/4948** |

95 笔成交的字段差**全部**落在佣金/印花/费用合计上，|差| ≤ 0.01 元（实测 max 0.0085），
股数差与价格差为 0——即 C2 已裁定的「逐笔现金变动 HALF_UP 到分（合同口径，待用户追认）vs
引擎 float64 全程不舍入」的表示差，不是经济错误。

**口径限制（登记）**：
1. 未成交**买**单的请求股数不在事件日志里。引擎的判定顺序是 bar → 限价合法性 → 穿透 → 数量/资金，
   原因类别与数量无关，因此这些单用「一手探针」复现穿透/合法性/停牌层（`probe_mode=lot_probe_penetration`）；
   `below_min_lot` 行的 `detail` 带真实目标名义，用它复现（`probe_mode=target_from_detail`）。
2. 单只 25% 帽用**自算**决策点权益快照（官方收盘 mark）判定，与引擎快照口径的差异体现在
   `core_fields_match`；本阶段 5,260 单里没有因帽判定产生的差异。
3. 涨跌停缺行（C1 数据卡：2017-03-07..09 三日整缺）按保守口径**拒绝并留痕**：这三天出现在
   `market_exit_filled`（2017-03-07，引擎 `no_limit_info` 路径下按开盘市价兜底）——matcher 同样
   在涨跌停缺行时按「无法判跌停」执行开盘兜底，与引擎一致（FULL/NOACCT/NOSNR 各 1 次，全部一致）。

## 4. C3-A 闭环对照（固定策略 + 同一段合成行情）

产物：`<EV>/state_transition_tests.xml`（2 tests / 0 failures / 0 skipped），
源码 `tests/test_reference_matcher_state.py`。

两条链跑同一段合成半日行情：①主引擎 `run_band_backtest_intents(..., execution_clock='halfday')`
②独立 matcher + 自带 `Book`。订单层输入取自引擎的**订单级事件日志**（合约要求订单层暴露
order_id/限价/生效半日/数量），本项检验的是**撮合与状态响应**是否一致，不复述引擎的穿透代码。

- **场景 1**：两笔买入当日 pm 成交；一笔 profit 卖出到期未穿透后重锚成交（**部分成交 300 股**）。
  结果：每笔成交的成交与否/股数/价格/费用逐分一致；期末每股持股与引擎 `clips_final` 完全一致；
  期末现金（含两个待结算桶）差 < 0.05 元。
- **场景 2**：风险卖出连续 3 个未成交半日 → 下一个许可半日开盘兜底；中间夹一个停牌日
  （该标的无 bar 且无日线行）。结果：兜底半日、兜底价（= session 开盘价，不是限价）、股数、费用
  与引擎 `market_fallback` 成交一致；期末持股一致。停牌日 K 计数冻结由 matcher 的
  `k3_deferred` 与引擎的 `k3_deferred_suspended` 各自登记。

## 5. C3-B 语义链

### 5.1 C-05 关闭（核心）

产物：`<EV>/intent_to_order_trace.csv`（102 行 = B1 全部事件）与 `semantic_chain_summary.json`。

| 量 | 值 |
|---|---|
| 签发单 | 39 |
| 其中 `limit_price == decision_anchor_price` | **39/39** |
| 其中 `limit_price == trigger_close × 1.01` | **0/39** |
| 全部 102 事件 | 63 条 `slot_full` 未签发；39 条签发 |

结论：**`×1.01` 是签发门槛，不是限价**。三重互证：
① provider 代码 `cap_price = 触发日收盘 × (1 + CHASE)`，`anchor > cap` 则 `skip_cap`、不签发；
② 引擎建单处 `anchor_price = anchor`（个股锚不做 tick 处理），入场意图行只带 `target_weight`；
③ 39/39 观测显示 `order_price_first` 恒等于 `decision_anchor_price` 且从不等于 cap。
与 C1 `entry_price_dual_track` 的「只登记不裁定」一致：本阶段**只关闭追踪义务**，不改合同也不改代码；
C6-E1 若要按 `limit = floor_to_tick(anchor × 1.01)` 实现，属预登记内的合同变更。

### 5.2 11:30 不变性（真实策略链重证）

产物：`<EV>/eleven_thirty_invariance.csv`（5 行）+ `.log`。

工具：真实 `EventFamilyProvider`（A 族参数）+ 真实 `run_band_backtest_intents`，合成切片
（Dev 窗内日期、全合成行情、6 个决策点）。场景含一笔固定入场与一张 standing 风险卖单，
因此 D2 的 11:30 与 15:00 两个决策点在每个变体里都有非空输出；判定输出用
「决策点产出的订单身份 + 实际限价」比较（**不用成交结果**——11:30 决策单的生效半日正是当日午后，
用成交结果做不变性会被撮合层污染）。

| 检查 | 结果 |
|---|---|
| A1 改 D2 午后（含官方收盘）后，D2 11:30 的 **provider 输出**逐位不变 | PASS |
| A2 同上，D2 11:30 的**引擎订单行**逐位不变 | PASS |
| B 正向对照：同一改动必须让 D2 **15:00** 的输出变化 | PASS |
| C 正向对照：改 D2 上午必须让 D2 **11:30** 的输出变化 | PASS |
| D 历史稳定：D1 两个决策点在三个变体下完全一致 | PASS |

这是对 C1 局限 1（「11:30 不变性只在合成单测上验过」）在**真实决策路径**上的重证。

### 5.3 席位账

产物：`<EV>/seat_lifecycle.csv`（102 行）。分组守恒：`issued 39` + `slot_full 63` = 102 = 全部事件，
无一行 `held+pending > 4`。接纳排序键登记为 `(decision_time, -rank_key, symbol)`，`rank_key = ret60`
（同点冲突时动量高者先接纳）；同证券重复事件不占两席（`held`/`pending` 都是按 symbol 的集合）；
失效挂单释放席位由「半日单每半日到期 + pending 按 TTL/cap/cancel_level 掉出」保证。

**来源差异（登记）**：B1 主 run 不落漏斗产物，席位账取自与 B1 同参数的 attrib2 run
（`20260922T002611`），两者臂配置相同但**不是同一个 run**——若要求严格的 run 内闭环，
须在 C4 让 B1 主 run 也落 `event_funnel` 级产物。

### 5.4 风险状态（D3 正常/降档/恢复）

产物：`<EV>/risk_state_trace.csv` + `risk_state_trace_hand_expected.csv`。

两条合成权益路径，各 9 个 15:00 类观测；真实 `AccountRiskDynamics("D3")` 逐 session 出状态，
并与**独立手算**的期望（高水位回撤 ≥10% 降档；回撤 ≤5% 且连续 2 个确认 session 且冷却 3 session 后恢复）
逐 session 对照：

| 路径 | 权益序列 | 真实代码状态序列 | 手算期望 | 一致 |
|---|---|---|---|---|
| rebound | 500k→505k→495k→440k→445k→470k→478k→480k→485k | normal×3 → reduced×5 → **normal** | 同 | 9/9 |
| slump | 500k→505k→495k→440k→430k→420k→415k→410k→405k | normal×3 → reduced×6（期末仍降档） | 同 | 9/9 |

两条路径的差异恰好体现「恢复需回撤回到 5% 以内并连续确认」：持续低迷路径回撤一路扩大，
确认 streak 归零，从不恢复。降档后真实暴露乘数 0.4（合同的两档暴露），期末手续费率与恢复队列
逐 session 落在 CSV 里。

### 5.5 退出 → 订单映射与批次

产物：`<EV>/clip_exit_trace.csv`（59 行 = B1 主 run 全部退出原因）。

| 退出原因 | 条数 | 映射的订单类 | 语义 |
|---|---|---|---|
| stop | 21 | risk 卖 | 止损，吃 K=3 兜底 |
| time_exit | 20 | profit 卖 | 到期静默失效，**无兜底** |
| account_trim | 7 | risk 卖 | D3 账户降档减持，吃兜底 |
| take_half | 5 | profit 卖 | 分批止盈，**触发不等于完成** |
| clear | 4 | risk 卖 | 全清（席位/信号退出） |
| protection | 2 | risk 卖 | 保护线，吃兜底 |

`take_half` 的「未成交不标完成」在合同层由 profit 类语义保证（无兜底、到期静默失效），
在 matcher 侧由 TV-B11/TV-B18 反证钉住。重发冻结同一事件 ID：引擎的站立风险单按
`(symbol, intent, source_signal)` 建键，重发只重锚、保持 K 计数（M1）。

**FIFO 消耗 vs 逐批风险意图错配（C2 转入项）**：部分卖出按取得日 FIFO 消耗，而风险意图瞄准的是
**聚合持仓**——理论上可能出现「某批次的风险线已被穿越，但 FIFO 卖的是另一批次」。逐 clip 对照
已在 CSV 每行登记；本阶段**处置建议转 C4**：保持 FIFO，明确声明「本策略不存在逐批风险退出原语」，
并把任何「逐批风险」结论重新表述为聚合口径，而不是新增第二条退出路径。

### 5.6 优先级合成反证（TV-B18/B22/B23）

在 `tests/test_reference_matcher.py`（`order_tests.xml`）内，0 skip：

- **TV-B18**：同证券同点风险卖出与买入并存 → 卖出按可卖量上限成交（不超卖，剩余股数登记）；
  买入因「同半日卖出款不可用」而资金不足被拒（无同点买回）；止盈单在它的第 4 个存活半日
  仍无兜底（止盈不升级为风险单）。
- **TV-B22**：既有持仓因价格漂移越帽时，**别的标的**的新单照常判定、**该标的**自身的新买整单作废、
  不生成任何强制减仓判定、持仓不被强制清仓（只披露被动漂移）。
- **TV-B23**：超单名帽 → `cancelled_cap` 整单作废（不缩量）；现金不足 → `cash_short`，
  闭环里账面现金与持股均不变（不为达标借款）。

## 6. C3-C 合同局限

产物：`<EV>/minute_vs_halfday_check.csv`、`contract_limitations.md`。要点：

- 已授权分钟样本（`data/processed/minute-feats-20260918/`）是**每股每日一行的投影特征表**，
  覆盖 Dev 窗 4,598,367 行 / 4,181 只，**不含分钟价格路径**。因此可以核验「半日 bar 极值是否
  落在分钟全日极值区间内」（实测 1,030 笔抽样全部在区间内，**零越界 = 没有制造数据**），
  但不能核验「订单生效半日之前是否已穿透」。
- 方向性误判计数（1,030 笔 `never_crossed` 订单抽样）：以**全日**分钟极值为细粒度一侧时，
  246 笔（23.9%）在更细粒度下本可穿透；把「另一个 session 的极值也穿价」的情形剔除后，
  严格归因于本 session 的只有 **19 笔（1.8%）**。方向恒为「半日保守少判成交」，**没有一例是半日
  判成交而分钟不可能成交**。
- 无订单簿 → 排队成交率不可证；严格穿透与跳空取限价是**模型选择**，不是交易所真相。
  任何校准只做差异披露，不改本轮正式合同与费率。

## 7. 未完成 / 转 C4

1. **attrib2 run 无订单级产物**：`20260922T002611-eventfam-attrib2-eed5cf` 只有 B1 汇总结论，
   无法做订单级对账；如需要，C4 重跑该 run 并落订单事件。
2. **席位账来源不同 run**（见 5.3）：C4 让 B1 主 run 落 `event_funnel` 级产物即可消除。
3. **FIFO vs 逐批风险意图错配**：C4 出处置结论（建议保持 FIFO + 明确无逐批退出原语的披露）。
4. **25% 帽快照口径**：matcher 与引擎各自自算快照，本阶段无差异样本；若 C4 出现差异，
   需按合同 M2 精确定义「决策点权益快照」的价格来源与时刻。
5. **未覆盖**：创业板/科创板/北交所标的、ETF 腿、日内分钟路径、排队成交率。
6. 现实可得性证据不足可限定使用范围；**本阶段的核对结论只覆盖主板股票半日合同**。

## 8. 复跑

```bash
PYTHONPATH=src .venv/Scripts/python.exe -m quant.research.reference_matcher_reconcile \
    --evidence-dir docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13
PYTHONPATH=src .venv/Scripts/python.exe -m quant.research.c3_semantic_chain \
    --evidence-dir docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13
PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_reference_matcher.py \
    --junitxml=<EV>/order_tests.xml
PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_reference_matcher_state.py \
    --junitxml=<EV>/state_transition_tests.xml
```

---

## 9. 交付检查与证据登记

`stage_report.json` 按本轮执行包的证据规格填写（`checks` 八门 + `open_issues` + `run_records`），
并实跑本包自带检查器：

```
PYTHONPATH=src .venv/Scripts/python.exe docs/quant_stage_plan_20260922/tools/check_delivery.py \
    --report <EV>/stage_report.json --root .
→ {"status": "EVIDENCE_FILES_OK", "errors": [], "verified_file_count": 27,
   "junit_summary": [{"evidence_id":"EV-04","tests":22,"failures":0,"errors":0,"skipped":0},
                     {"evidence_id":"EV-05","tests":2,"failures":0,"errors":0,"skipped":0}],
   "engineering_approval_granted": false, "research_validated": false}
```

输出原文存 `<EV>/delivery_check_output.json`。检查器只做**文件存在性/字节一致/基本一致性**，
不认证身份、不证明日志真实、不构成工程批准——因此 `engineering_state` 保持 `pending`。

全量测试回归（本次改动没有引入回归）：

```
PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q
→ 804 passed, 6 warnings in 53.36s（0 failed / 0 skipped）
```

## 10. 这次真正验证了什么、没验证什么

**已验证（有哈希证据、可复跑）**
1. 同一份具体订单在第二套独立实现下的成交判定（5,260 单 + 74 次兜底）与引擎逐字段一致。
2. 独立 matcher 的闭环状态响应（T+1、费率、现金结算、部分成交、K=3 兜底、停牌冻结）与引擎逐半日一致。
3. `×1.01` 的门槛/限价关系在 39 笔真实签发单上闭合，且与两处代码互证。
4. 真实策略链的 11:30 决策输出不受当日午后行情影响（含正向对照）。
5. D3 账户风险的降档/恢复过程在真实代码上可手算复现。

**没验证（不得据此声称）**
1. 交易所逐笔成交是否与模型相同（无订单簿、无 Tick）。
2. 订单生效半日之前是否已经穿透（分钟投影表没有路径）。
3. 排队成交率、ETF 腿、创业板/科创板/北交所标的。
4. 任何收益结论——C3 不评估策略表现，`research_state=not_evaluated`。
