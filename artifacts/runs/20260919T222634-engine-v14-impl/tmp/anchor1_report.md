# P3R2 v1.1 意图层重裁定（exp-20260918-p3r2-band-v1-readjudication）

- 运行 `20260919T222634-engine-v14-impl`；引擎 v1.1 sha256:16 `7ad35014d72711cb`（双签 APPROVE `20260919T023558-p3v1-intent-review-c4d1`，运行前后哈希一致）；执行模型=引擎侧意图层（预登记 §9 修订 2/3）：每配置单帧提交，宿主零成交感知循环、零不动点迭代。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（共 71 个月末，2020-12-31 按冻结先例丢弃）；val 2021–2024 零消费。
- 判据 = R16 预登记 §2 八门逐字（prereg §3）；B1(m)/B3′ 沿 R16 原值。全部数字为历史回放，不构成盈利或实盘声称。

## 一、八门判定表

| 配置 | K/路径/Q5 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤(v1.1/P3R1) | 换手 | 单票max权重 | 门8成交率(v1.1/P3R1) | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C05 | 30/T200-40/on | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20%/-33.57% | 1.59 | 11.1% | 53.3%/91.7% | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8_execution_rate_ge_95pct | eliminated |

### 一句话死因

- **C05**: 优势年不足(门3,信号层属性); 回撤超限(门4); 计划成交率<95%(门8)

## 二、vs P3R1 delta（披露 1–3；注意第 4 项 rescale 加仓空洞为混杂）

| 配置 | 门8成交率 Δpp | 订单口径买/卖 Δpp | 换手 Δ | 费用 Δ元 | 回撤 Δpp | 净CAGR Δpp |
|---|---|---|---|---|---|---|
| C05 | -38.4 | -31.8/-20.7 | +0.17 | +1,754 | +12.38 | -1.19 |

## 三、增量披露（披露 5 + 修订项）

- **C05**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 19.3%/80.7%；K=3 armed/executed=7/6（跌停顺延 10、停牌 0、T+1锁 0）；门8终止：到期 136 / 同名义覆盖 515 / 上限作废 0 / 停牌放弃 1（零发射意图 229）；m5-a 无pm bar日 pm 重挂 7；ENGINE-3 缺行日卖作废 0（2017-03-07..09 占 0）；R16 跳过腿 {'r16_at_target': 501, 'r16_feemin_skipped': 320}；rescale 风减意图 353（成交 145；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=18827,at_target_skips=8683,no_anchor_skips=1423

## 四、映射差异清单（披露 4，全配置相同）

- **lifecycle_ownership**: revision 2: the ENGINE intent layer owns the order lifecycle (re-anchor at every decision point, re-hang, fill-stop, expiry/override/cap-void); host submits ONE static frame -- replaces 9cc4's dead host-side conventions (convention-A full-window numbers are INVALID diagnostics, prereg rev 1)
- **in_loop_pricing**: revision 3: buy/rescale sizing = target_weight x decision-point equity snapshot recomputed by the engine at every decision point; replaces P3R1's host-side fixed-point iteration (5-6 rounds) -- deterministic, zero feedback
- **re_anchor_cadence**: v0 dead anchor (signal-day close) -> v1.1 mechanical re-anchor at EVERY decision point (am = am.close, pm = official close), qty recomputed in-loop (7.7-M3); fill-rate uplift is a RULE difference, disclosed not celebrated
- **rescale_mapping**: R16 rescale legs -> standing reduce-to-target risk sell (target_weight = exposure/K), self-neutralizing via engine at_target skips. REGISTERED HOLE: the top-up side is NOT mapped (no engine buy top-up primitive; a full-seat buy would double the seat); P3R1/9cc4 mapped it via fixed-point sizing -- vs-P3R1 turnover/fee deltas are confounded by this hole
- **rescale_skips**: R16 outcome at_target/feemin_skipped rescale legs are outside the frame (9cc4 mapping-fidelity asset; R16 no-trade record)
- **sell_intent_mapping**: sell_full -> intent=risk full exit; K=3 SESSION-level fallback keyed (symbol, intent, source) (7.7-M1); rescale-down same intent semantics with explicit target weight
- **fill_granularity**: official daily extremes -> half-day bar extremes (conservative subset; gaps fill at the limit)
- **proceeds**: sale proceeds usable next SESSION (v0: next day)
- **expiry_boundary**: expiry_date = T'+1 cal day -> last emission is the (T','am') decision living (T','pm'), i.e. the frozen 9cc4 window; same-name override fires at (T','pm')
- **signal_day_drop**: same as P3R1: 2020-12-31 signal dropped (execution would cross into 2021)
- **profit_ladder**: intent=profit still unmapped (R16 has no profit-ladder signal) -- prereg sec 4.8 mapping hole, unchanged

## 五、运行身份

- 引擎 7ad35014d72711cb 前后一致；8/8 信号一致性 {"C05": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}}
- 试验计账：197 → 205（本轮 8，判定表已产出）；9cc4 约定 A 数字为无效执行诊断（修订 1），未作任何判定依据；在环定价=修订 3（权重×决策点权益快照，零反馈），替代 P3R1 宿主外不动点（5–6 轮）。
- 判定：no config passed all dev gates (0/8); val not consumed