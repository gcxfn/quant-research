# P3R2 v1.1 意图层重裁定（exp-20260918-p3r2-band-v1-readjudication）

- 运行 `20260919T030640-p3r2-dev-ad9e`；引擎 v1.1 sha256:16 `d7108c0eccdd77ff`（双签 APPROVE `20260919T023558-p3v1-intent-review-c4d1`，运行前后哈希一致）；执行模型=引擎侧意图层（预登记 §9 修订 2/3）：每配置单帧提交，宿主零成交感知循环、零不动点迭代。
- 窗口 dev 2015-01-05..2020-12-31，信号 2015-01-30..2020-11-30（共 71 个月末，2020-12-31 按冻结先例丢弃）；val 2021–2024 零消费。
- 判据 = R16 预登记 §2 八门逐字（prereg §3）；B1(m)/B3′ 沿 R16 原值。全部数字为历史回放，不构成盈利或实盘声称。

## 一、八门判定表

| 配置 | K/路径/Q5 | 净CAGR | B1(m) | 超额 | 优势年 | 回撤(v1.1/P3R1) | 换手 | 单票max权重 | 门8成交率(v1.1/P3R1) | 过/8 | 失败门 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | 20/T200-40/on | +0.68% | +0.60% | +0.08pp | 2/6 | -21.65%/-30.61% | 1.49 | 9.4% | 58.4%/91.4% | 4 | 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8_execution_rate_ge_95pct | eliminated |
| C02 | 20/T200-40/off | -4.91% | +0.60% | -5.51pp | 2/6 | -38.54%/-48.33% | 2.48 | 9.0% | 57.7%/93.3% | 2 | 1_net_cagr_gt_0, 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 7_vs_B3prime_plus_1pp, 8_execution_rate_ge_95pct | eliminated |
| C03 | 20/FIX75/on | -0.87% | +1.86% | -2.73pp | 2/6 | -45.45%/-49.91% | 1.80 | 8.6% | 56.6%/91.1% | 2 | 1_net_cagr_gt_0, 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 7_vs_B3prime_plus_1pp, 8_execution_rate_ge_95pct | eliminated |
| C04 | 20/FIX75/off | -4.35% | +1.86% | -6.21pp | 2/6 | -55.15%/-61.52% | 2.70 | 12.3% | 58.3%/92.8% | 2 | 1_net_cagr_gt_0, 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 7_vs_B3prime_plus_1pp, 8_execution_rate_ge_95pct | eliminated |
| C05 | 30/T200-40/on | +3.88% | +0.60% | +3.28pp | 4/6 | -21.20%/-33.57% | 1.59 | 11.1% | 53.3%/91.7% | 5 | 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 8_execution_rate_ge_95pct | eliminated |
| C06 | 30/T200-40/off | -4.96% | +0.60% | -5.56pp | 2/6 | -39.59%/-48.47% | 2.33 | 9.0% | 49.3%/91.1% | 2 | 1_net_cagr_gt_0, 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 7_vs_B3prime_plus_1pp, 8_execution_rate_ge_95pct | eliminated |
| C07 | 30/FIX75/on | -0.62% | +1.86% | -2.47pp | 3/6 | -42.92%/-46.64% | 1.77 | 11.6% | 51.6%/91.8% | 2 | 1_net_cagr_gt_0, 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 7_vs_B3prime_plus_1pp, 8_execution_rate_ge_95pct | eliminated |
| C08 | 30/FIX75/off | -5.68% | +1.86% | -7.53pp | 1/6 | -55.30%/-57.37% | 2.37 | 6.7% | 50.9%/91.4% | 2 | 1_net_cagr_gt_0, 2_excess_vs_B1m_ge_2pp, 3_advantage_years_ge_5_of_6, 4_mdd_le_20pct_and_le_B1m, 7_vs_B3prime_plus_1pp, 8_execution_rate_ge_95pct | eliminated |

### 一句话死因

- **C01**: 优势年不足(门3,信号层属性); 超额<+2pp(门2); 回撤超限(门4); 计划成交率<95%(门8)
- **C02**: 优势年不足(门3,信号层属性); 净CAGR≤0(门1); 超额<+2pp(门2); 回撤超限(门4); 低于B3′+1pp(门7); 计划成交率<95%(门8)
- **C03**: 优势年不足(门3,信号层属性); 净CAGR≤0(门1); 超额<+2pp(门2); 回撤超限(门4); 低于B3′+1pp(门7); 计划成交率<95%(门8)
- **C04**: 优势年不足(门3,信号层属性); 净CAGR≤0(门1); 超额<+2pp(门2); 回撤超限(门4); 低于B3′+1pp(门7); 计划成交率<95%(门8)
- **C05**: 优势年不足(门3,信号层属性); 回撤超限(门4); 计划成交率<95%(门8)
- **C06**: 优势年不足(门3,信号层属性); 净CAGR≤0(门1); 超额<+2pp(门2); 回撤超限(门4); 低于B3′+1pp(门7); 计划成交率<95%(门8)
- **C07**: 优势年不足(门3,信号层属性); 净CAGR≤0(门1); 超额<+2pp(门2); 回撤超限(门4); 低于B3′+1pp(门7); 计划成交率<95%(门8)
- **C08**: 优势年不足(门3,信号层属性); 净CAGR≤0(门1); 超额<+2pp(门2); 回撤超限(门4); 低于B3′+1pp(门7); 计划成交率<95%(门8)

## 二、vs P3R1 delta（披露 1–3；注意第 4 项 rescale 加仓空洞为混杂）

| 配置 | 门8成交率 Δpp | 订单口径买/卖 Δpp | 换手 Δ | 费用 Δ元 | 回撤 Δpp | 净CAGR Δpp |
|---|---|---|---|---|---|---|
| C01 | -32.9 | -45.8/-11.8 | +0.12 | +1,053 | +8.96 | -4.49 |
| C02 | -35.6 | -43.8/-27.1 | +0.28 | +1,052 | +9.78 | -2.58 |
| C03 | -34.5 | -50.9/-21.8 | +0.04 | +733 | +4.46 | -1.47 |
| C04 | -34.5 | -46.5/-16.1 | +0.31 | +896 | +6.37 | +1.33 |
| C05 | -38.4 | -31.8/-20.7 | +0.17 | +1,754 | +12.38 | -1.19 |
| C06 | -41.9 | -30.3/-9.2 | +0.24 | +1,418 | +8.89 | -5.21 |
| C07 | -40.2 | -35.0/-11.9 | +0.16 | +1,068 | +3.72 | -0.83 |
| C08 | -40.6 | -34.6/-29.2 | +0.30 | +1,098 | +2.06 | -1.82 |

## 三、增量披露（披露 5 + 修订项）

- **C01**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 18.9%/81.1%；K=3 armed/executed=8/8（跌停顺延 11、停牌 0、T+1锁 0）；门8终止：到期 110 / 同名义覆盖 268 / 上限作废 0 / 停牌放弃 0（零发射意图 211）；m5-a 无pm bar日 pm 重挂 3；ENGINE-3 缺行日卖作废 2（2017-03-07..09 占 2）；R16 跳过腿 {'r16_at_target': 357, 'r16_feemin_skipped': 216}；rescale 风减意图 284（成交 93；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=7819,at_target_skips=7949,no_anchor_skips=1200
- **C02**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 20.2%/79.8%；K=3 armed/executed=8/6（跌停顺延 8、停牌 0、T+1锁 0）；门8终止：到期 102 / 同名义覆盖 361 / 上限作废 0 / 停牌放弃 1（零发射意图 217）；m5-a 无pm bar日 pm 重挂 3；ENGINE-3 缺行日卖作废 2（2017-03-07..09 占 2）；R16 跳过腿 {'r16_at_target': 344, 'r16_feemin_skipped': 245}；rescale 风减意图 291（成交 94；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=11521,at_target_skips=8179,no_anchor_skips=1231
- **C03**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 20.2%/79.8%；K=3 armed/executed=7/7（跌停顺延 11、停牌 0、T+1锁 0）；门8终止：到期 122 / 同名义覆盖 251 / 上限作废 0 / 停牌放弃 0（零发射意图 230）；m5-a 无pm bar日 pm 重挂 1；ENGINE-3 缺行日卖作废 0（2017-03-07..09 占 0）；R16 跳过腿 {'r16_at_target': 391, 'r16_feemin_skipped': 237}；rescale 风减意图 273（成交 64；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=6658,at_target_skips=8759,no_anchor_skips=1171
- **C04**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 19.5%/80.5%；K=3 armed/executed=9/7（跌停顺延 19、停牌 0、T+1锁 0）；门8终止：到期 106 / 同名义覆盖 324 / 上限作废 0 / 停牌放弃 1（零发射意图 221）；m5-a 无pm bar日 pm 重挂 0；ENGINE-3 缺行日卖作废 0（2017-03-07..09 占 0）；R16 跳过腿 {'r16_at_target': 397, 'r16_feemin_skipped': 261}；rescale 风减意图 268（成交 66；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=9627,at_target_skips=8427,no_anchor_skips=1204
- **C05**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 19.3%/80.7%；K=3 armed/executed=7/6（跌停顺延 10、停牌 0、T+1锁 0）；门8终止：到期 136 / 同名义覆盖 515 / 上限作废 0 / 停牌放弃 1（零发射意图 229）；m5-a 无pm bar日 pm 重挂 7；ENGINE-3 缺行日卖作废 0（2017-03-07..09 占 0）；R16 跳过腿 {'r16_at_target': 501, 'r16_feemin_skipped': 320}；rescale 风减意图 353（成交 145；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=18827,at_target_skips=8683,no_anchor_skips=1423
- **C06**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 19.0%/81.0%；K=3 armed/executed=8/6（跌停顺延 12、停牌 0、T+1锁 0）；门8终止：到期 142 / 同名义覆盖 700 / 上限作废 0 / 停牌放弃 1（零发射意图 252）；m5-a 无pm bar日 pm 重挂 7；ENGINE-3 缺行日卖作废 3（2017-03-07..09 占 2）；R16 跳过腿 {'r16_at_target': 490, 'r16_feemin_skipped': 328}；rescale 风减意图 329（成交 118；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=25721,at_target_skips=8722,no_anchor_skips=2482
- **C07**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 20.8%/79.2%；K=3 armed/executed=8/7（跌停顺延 21、停牌 0、T+1锁 0）；门8终止：到期 154 / 同名义覆盖 463 / 上限作废 0 / 停牌放弃 1（零发射意图 229）；m5-a 无pm bar日 pm 重挂 4；ENGINE-3 缺行日卖作废 0（2017-03-07..09 占 0）；R16 跳过腿 {'r16_at_target': 580, 'r16_feemin_skipped': 379}；rescale 风减意图 292（成交 87；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=17206,at_target_skips=8674,no_anchor_skips=1474
- **C08**：上限作废 0（漂移越限记录 0）；am/pm 成交占比 20.3%/79.7%；K=3 armed/executed=9/7（跌停顺延 24、停牌 0、T+1锁 0）；门8终止：到期 151 / 同名义覆盖 601 / 上限作废 0 / 停牌放弃 1（零发射意图 257）；m5-a 无pm bar日 pm 重挂 4；ENGINE-3 缺行日卖作废 0（2017-03-07..09 占 0）；R16 跳过腿 {'r16_at_target': 566, 'r16_feemin_skipped': 395}；rescale 风减意图 307（成交 87；加仓侧=登记空洞）；m5-c 惰性键 order_generation=engine_intents, intent_layer.orders=21921,at_target_skips=9230,no_anchor_skips=2318

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

- 引擎 d7108c0eccdd77ff 前后一致；8/8 信号一致性 {"C01": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C02": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C03": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C04": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C05": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C06": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C07": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}, "C08": {"membership_mismatches": 0, "membership_events_mismatches": 0, "n_signal_days": 71}}
- 试验计账：197 → 205（本轮 8，判定表已产出）；9cc4 约定 A 数字为无效执行诊断（修订 1），未作任何判定依据；在环定价=修订 3（权重×决策点权益快照，零反馈），替代 P3R1 宿主外不动点（5–6 轮）。
- 判定：no config passed all dev gates (0/8); val not consumed