# F4R1 冒烟核对报告（exp-20260919-zone-sheet-f4r1）

- 运行 `20260920T011431-f4r1-smoke-4d9e`；引擎 v1.4 sha256:16 `7ad35014d72711cb`（运行前后一致，pin `7ad35014d72711cb`）；预登记 sha256:16 `e9538bedfc33fabb`；配置 sha256:16 `aa5699aec021aa46`（冻结，唯一参数来源）。
- **性质声明：本报告仅为正确性核对（预登记 §7），不产生任何绩效结论；未跑全期（dev 2015–2020 全期运行待冒烟验收后另行发起）。**
- 冒烟窗口：W1 = 2015-01-05..2015-02-28，W2 = 2016-01-01..2016-02-29；三臂 × 两窗口各一次；σ0 前置 20 日历史取全历史（不受窗口裁剪）。
- A0 锚：R3-06 逐字（200k，rotation UNI6），五帧 filecmp 逐字节比对 F3R3-A0 输出——见下表。
- 窗口截断说明：每窗口最后一个信号日（W1 2015-02-27 / W2 2016-02-29）即窗口末 session，其月末边界退出与新月准入订单无后续 session 可成交，相关持仓残留在窗口期末；冒烟仅核对成交与账本的正确性，窗口期末状态无绩效含义。
- W2 熔断月：2016-01-04/07 熔断日早于 W2 首个信号日（2016-01-29），两窗口均无任何成交落在熔断日；熔断日以 partial session（如 2016-01-07 am 仅 8–17 分钟）如实参与面板，数据身份已 pin。停牌/跌停/ T+1 残部导致的 armed 顺延在两窗口均未发生（六次运行 armed_events 全为 0，见各窗核对）。

## 一、A0 锚比对（filecmp 逐字节）

| 帧 | 逐字节相等 | 行数相等 |
|---|---|---|
| intents | PASS | PASS |
| fills | PASS | PASS |
| events | PASS | PASS |
| daily_equity | PASS | PASS |
| clips_final | PASS | PASS |

## 二、每臂每窗口核对表

### F4R1-A / W1 —— 全部 PASS
- zones 帧 40 行（候选 40，σ0 不足/无价剔除 0 {}）；月内准入（含席位回收补位）{'2015-01-30': 18}，其中首扫 {'2015-01-30': 10, '2015-02-27': 0}（K=10，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；续持 {'2015-01-30': 0, '2015-02-27': 1}；行业受阻（重建口径）0。注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数核对通过）。
- fills 路由/限价抽验：路由 51、阶梯限价 18、止盈价 31 全部逐分核对；逐档 fill-stop（每档至多一次成交）核对通过；整手核对通过。
- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 8.73e-11；权益恒等式最大误差 0.00e+00。
- 止盈样本 12 例、止损样本 5 例：止盈成交价逐分等于 WAC+mult×σ0（WAC 按成交额加权、卖出不减），止损成交价逐分等于 min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；T+1 残部 k3 武装本窗口未发生（armed=0），该机制由引擎契约测试（t10/t20）覆盖，冒烟真实数据未触发。
- 门 8 结构：armed 0 = 兜底 0 + 其他 0 + 滞留 0；stuck==0 断言 PASS；tp_expired 372、tier_expired 20、tier_invalidated 0、below_min_lot 0。
- stats['zones'] 与 BandResult.zones 自洽核对：PASS。
- zone 事件：{"zone_admitted": 18, "zone_holding": 17, "zone_stop_triggered": 5, "zone_cooling": 8, "zone_ladder_expired": 10, "zone_done": 9, "zone_exiting_boundary": 8, "zone_continued": 1}。
- fills 总数 56；引擎警告 2 条。

- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口为 0 例；以下为止损触发与成交明细）：
  - 2015-02-06 am  zone_stop_triggered: sz.002424 (signal 2015-01-30): session low 41.0200 < stop line 41.1295; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 41.1295
  - 2015-02-06 pm  zone_stop_triggered: sz.000513 (signal 2015-01-30): session low 47.7000 < stop line 48.1525; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 48.1525
  - 2015-02-09 am  zone_stop_triggered: sh.601677 (signal 2015-01-30): session low 12.1000 < stop line 12.1136; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 12.1136
  - 2015-02-09 am  zone_stop_triggered: sh.601877 (signal 2015-01-30): session low 32.2000 < stop line 32.3380; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 32.3380
  - 2015-02-09 am  zone_stop_triggered: sz.000759 (signal 2015-01-30): session low 8.2300 < stop line 8.2947; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 8.2947
- 止损样本明细：
  - sz.002424 2015-02-06 am: 成交 41.12946247533609 = min(重建线 41.1295, 开盘 41.74)，σ0=0.9468，200 股
  - sz.000513 2015-02-06 pm: 成交 48.152504078767336 = min(重建线 48.1525, 开盘 48.51)，σ0=0.8492，100 股
  - sh.601677 2015-02-09 am: 成交 12.113612480392483 = min(重建线 12.1136, 开盘 12.12)，σ0=0.3588，900 股
  - sh.601877 2015-02-09 am: 成交 32.33796414926104 = min(重建线 32.3380, 开盘 33.01)，σ0=0.7740，100 股
  - sz.000759 2015-02-09 am: 成交 8.29470018967988 = min(重建线 8.2947, 开盘 8.45)，σ0=0.1784，1300 股

### F4R1-A / W2 —— 全部 PASS
- zones 帧 38 行（候选 40，σ0 不足/无价剔除 2 {'lookback_gap': 2}）；月内准入（含席位回收补位）{'2016-01-29': 18}，其中首扫 {'2016-01-29': 10, '2016-02-29': 0}（K=10，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；续持 {'2016-01-29': 0, '2016-02-29': 0}；行业受阻（重建口径）0。注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数核对通过）。
- fills 路由/限价抽验：路由 67、阶梯限价 22、止盈价 43 全部逐分核对；逐档 fill-stop（每档至多一次成交）核对通过；整手核对通过。
- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 5.82e-11；权益恒等式最大误差 0.00e+00。
- 止盈样本 12 例、止损样本 5 例：止盈成交价逐分等于 WAC+mult×σ0（WAC 按成交额加权、卖出不减），止损成交价逐分等于 min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；T+1 残部 k3 武装本窗口未发生（armed=0），该机制由引擎契约测试（t10/t20）覆盖，冒烟真实数据未触发。
- 门 8 结构：armed 0 = 兜底 0 + 其他 0 + 滞留 0；stuck==0 断言 PASS；tp_expired 231、tier_expired 11、tier_invalidated 0、below_min_lot 0。
- stats['zones'] 与 BandResult.zones 自洽核对：PASS。
- zone 事件：{"zone_admitted": 18, "zone_holding": 17, "zone_cooling": 12, "zone_stop_triggered": 5, "zone_ladder_expired": 6, "zone_done": 13, "zone_exiting_boundary": 5}。
- fills 总数 72；引擎警告 2 条。

- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口为 0 例；以下为止损触发与成交明细）：
  - 2016-02-29 am  zone_stop_triggered: sh.600326 (signal 2016-01-29): session low 7.2100 < stop line 7.5257; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 7.5257
  - 2016-02-29 am  zone_stop_triggered: sh.600827 (signal 2016-01-29): session low 11.8200 < stop line 11.9591; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 11.9591
  - 2016-02-29 am  zone_stop_triggered: sz.000830 (signal 2016-01-29): session low 4.8100 < stop line 4.8511; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 4.8511
  - 2016-02-29 am  zone_stop_triggered: sz.002398 (signal 2016-01-29): session low 10.5900 < stop line 11.1526; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 11.1526
  - 2016-02-29 am  zone_stop_triggered: sz.002538 (signal 2016-01-29): session low 8.1800 < stop line 8.3818; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 8.3818
- 止损样本明细：
  - sh.600326 2016-02-29 am: 成交 7.52572795715504 = min(重建线 7.5257, 开盘 7.77)，σ0=0.3514，3200 股
  - sh.600827 2016-02-29 am: 成交 11.959097244144154 = min(重建线 11.9591, 开盘 13.09)，σ0=0.5736，1800 股
  - sz.000830 2016-02-29 am: 成交 4.8510626902951755 = min(重建线 4.8511, 开盘 5.1)，σ0=0.2263，2400 股
  - sz.002398 2016-02-29 am: 成交 11.15261358521293 = min(重建线 11.1526, 开盘 11.61)，σ0=0.5958，100 股
  - sz.002538 2016-02-29 am: 成交 8.381818755786647 = min(重建线 8.3818, 开盘 8.65)，σ0=0.4027，1500 股

### F4R1-B / W1 —— 全部 PASS
- zones 帧 40 行（候选 40，σ0 不足/无价剔除 0 {}）；月内准入（含席位回收补位）{'2015-01-30': 18}，其中首扫 {'2015-01-30': 10, '2015-02-27': 0}（K=10，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；续持 {'2015-01-30': 0, '2015-02-27': 1}；行业受阻（重建口径）0。注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数核对通过）。
- fills 路由/限价抽验：路由 37、阶梯限价 18、止盈价 17 全部逐分核对；逐档 fill-stop（每档至多一次成交）核对通过；整手核对通过。
- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 1.02e-10；权益恒等式最大误差 0.00e+00。
- 止盈样本 12 例、止损样本 5 例：止盈成交价逐分等于 WAC+mult×σ0（WAC 按成交额加权、卖出不减），止损成交价逐分等于 min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；T+1 残部 k3 武装本窗口未发生（armed=0），该机制由引擎契约测试（t10/t20）覆盖，冒烟真实数据未触发。
- 门 8 结构：armed 0 = 兜底 0 + 其他 0 + 滞留 0；stuck==0 断言 PASS；tp_expired 343、tier_expired 20、tier_invalidated 0、below_min_lot 6。
- stats['zones'] 与 BandResult.zones 自洽核对：PASS。
- zone 事件：{"zone_admitted": 18, "zone_below_min_lot": 1, "zone_holding": 17, "zone_stop_triggered": 5, "zone_cooling": 8, "zone_ladder_expired": 10, "zone_done": 9, "zone_exiting_boundary": 8, "zone_continued": 1}。
- fills 总数 42；引擎警告 2 条。

- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口为 0 例；以下为止损触发与成交明细）：
  - 2015-02-06 am  zone_stop_triggered: sz.002424 (signal 2015-01-30): session low 41.0200 < stop line 41.1295; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 41.1295
  - 2015-02-09 am  zone_stop_triggered: sh.601233 (signal 2015-01-30): session low 11.0000 < stop line 11.0554; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 11.0554
  - 2015-02-09 am  zone_stop_triggered: sh.601677 (signal 2015-01-30): session low 12.1000 < stop line 12.1136; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 12.1136
  - 2015-02-09 am  zone_stop_triggered: sh.601877 (signal 2015-01-30): session low 32.2000 < stop line 32.3380; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 32.3380
  - 2015-02-09 am  zone_stop_triggered: sz.000759 (signal 2015-01-30): session low 8.2300 < stop line 8.2947; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 8.2947
- 止损样本明细：
  - sz.002424 2015-02-06 am: 成交 41.12946247533609 = min(重建线 41.1295, 开盘 41.74)，σ0=0.9468，100 股
  - sh.601233 2015-02-09 am: 成交 11.055415755478865 = min(重建线 11.0554, 开盘 11.5)，σ0=0.3849，400 股
  - sh.601677 2015-02-09 am: 成交 12.113612480392483 = min(重建线 12.1136, 开盘 12.12)，σ0=0.3588，400 股
  - sh.601877 2015-02-09 am: 成交 32.33796414926104 = min(重建线 32.3380, 开盘 33.01)，σ0=0.7740，100 股
  - sz.000759 2015-02-09 am: 成交 8.29470018967988 = min(重建线 8.2947, 开盘 8.45)，σ0=0.1784，600 股

### F4R1-B / W2 —— 全部 PASS
- zones 帧 38 行（候选 40，σ0 不足/无价剔除 2 {'lookback_gap': 2}）；月内准入（含席位回收补位）{'2016-01-29': 18}，其中首扫 {'2016-01-29': 10, '2016-02-29': 0}（K=10，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；续持 {'2016-01-29': 0, '2016-02-29': 0}；行业受阻（重建口径）0。注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数核对通过）。
- fills 路由/限价抽验：路由 54、阶梯限价 22、止盈价 30 全部逐分核对；逐档 fill-stop（每档至多一次成交）核对通过；整手核对通过。
- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 5.46e-11；权益恒等式最大误差 0.00e+00。
- 止盈样本 12 例、止损样本 5 例：止盈成交价逐分等于 WAC+mult×σ0（WAC 按成交额加权、卖出不减），止损成交价逐分等于 min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；T+1 残部 k3 武装本窗口未发生（armed=0），该机制由引擎契约测试（t10/t20）覆盖，冒烟真实数据未触发。
- 门 8 结构：armed 0 = 兜底 0 + 其他 0 + 滞留 0；stuck==0 断言 PASS；tp_expired 231、tier_expired 11、tier_invalidated 0、below_min_lot 0。
- stats['zones'] 与 BandResult.zones 自洽核对：PASS。
- zone 事件：{"zone_admitted": 18, "zone_holding": 17, "zone_cooling": 12, "zone_stop_triggered": 5, "zone_ladder_expired": 6, "zone_done": 13, "zone_exiting_boundary": 5}。
- fills 总数 59；引擎警告 2 条。

- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口为 0 例；以下为止损触发与成交明细）：
  - 2016-02-29 am  zone_stop_triggered: sh.600326 (signal 2016-01-29): session low 7.2100 < stop line 7.5257; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 7.5257
  - 2016-02-29 am  zone_stop_triggered: sh.600827 (signal 2016-01-29): session low 11.8200 < stop line 11.9591; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 11.9591
  - 2016-02-29 am  zone_stop_triggered: sz.000830 (signal 2016-01-29): session low 4.8100 < stop line 4.8511; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 4.8511
  - 2016-02-29 am  zone_stop_triggered: sz.002398 (signal 2016-01-29): session low 10.5900 < stop line 11.1526; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 11.1526
  - 2016-02-29 am  zone_stop_triggered: sz.002538 (signal 2016-01-29): session low 8.1800 < stop line 8.3818; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 8.3818
- 止损样本明细：
  - sh.600326 2016-02-29 am: 成交 7.52572795715504 = min(重建线 7.5257, 开盘 7.77)，σ0=0.3514，1400 股
  - sh.600827 2016-02-29 am: 成交 11.959097244144154 = min(重建线 11.9591, 开盘 13.09)，σ0=0.5736，800 股
  - sz.000830 2016-02-29 am: 成交 4.8510626902951755 = min(重建线 4.8511, 开盘 5.1)，σ0=0.2263，1000 股
  - sz.002398 2016-02-29 am: 成交 11.15261358521293 = min(重建线 11.1526, 开盘 11.61)，σ0=0.5958，100 股
  - sz.002538 2016-02-29 am: 成交 8.381818755786647 = min(重建线 8.3818, 开盘 8.65)，σ0=0.4027，700 股

### F4R1-C / W1 —— 全部 PASS
- zones 帧 40 行（候选 40，σ0 不足/无价剔除 0 {}）；月内准入（含席位回收补位）{'2015-01-30': 20}，其中首扫 {'2015-01-30': 10, '2015-02-27': 0}（K=10，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；续持 {'2015-01-30': 0, '2015-02-27': 0}；行业受阻（重建口径）0。注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数核对通过）。
- fills 路由/限价抽验：路由 34、阶梯限价 21、止盈价 11 全部逐分核对；逐档 fill-stop（每档至多一次成交）核对通过；整手核对通过。
- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 8.73e-11；权益恒等式最大误差 0.00e+00。
- 止盈样本 11 例、止损样本 3 例：止盈成交价逐分等于 WAC+mult×σ0（WAC 按成交额加权、卖出不减），止损成交价逐分等于 min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；T+1 残部 k3 武装本窗口未发生（armed=0），该机制由引擎契约测试（t10/t20）覆盖，冒烟真实数据未触发。
- 门 8 结构：armed 0 = 兜底 0 + 其他 0 + 滞留 0；stuck==0 断言 PASS；tp_expired 175、tier_expired 13、tier_invalidated 0、below_min_lot 0。
- stats['zones'] 与 BandResult.zones 自洽核对：PASS。
- zone 事件：{"zone_admitted": 20, "zone_holding": 19, "zone_cooling": 14, "zone_stop_triggered": 3, "zone_ladder_expired": 6, "zone_done": 15, "zone_exiting_boundary": 5}。
- fills 总数 37；引擎警告 2 条。

- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口为 0 例；以下为止损触发与成交明细）：
  - 2015-02-06 am  zone_stop_triggered: sz.002424 (signal 2015-01-30): session low 41.0200 < stop line 41.1295; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 41.1295
  - 2015-02-09 am  zone_stop_triggered: sh.601677 (signal 2015-01-30): session low 12.1000 < stop line 12.1136; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 12.1136
  - 2015-02-09 am  zone_stop_triggered: sz.000759 (signal 2015-01-30): session low 8.2300 < stop line 8.2947; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 8.2947
- 止损样本明细：
  - sz.002424 2015-02-06 am: 成交 41.12946247533609 = min(重建线 41.1295, 开盘 41.74)，σ0=0.9468，200 股
  - sh.601677 2015-02-09 am: 成交 12.113612480392483 = min(重建线 12.1136, 开盘 12.12)，σ0=0.3588，900 股
  - sz.000759 2015-02-09 am: 成交 8.29470018967988 = min(重建线 8.2947, 开盘 8.45)，σ0=0.1784，1300 股

### F4R1-C / W2 —— 全部 PASS
- zones 帧 38 行（候选 40，σ0 不足/无价剔除 2 {'lookback_gap': 2}）；月内准入（含席位回收补位）{'2016-01-29': 18}，其中首扫 {'2016-01-29': 10, '2016-02-29': 0}（K=10，首扫逐位重放比对 PASS，含 below_min_lot 顺延）；续持 {'2016-01-29': 0, '2016-02-29': 0}；行业受阻（重建口径）0。注：月内准入总数可超过 K—— prereg §3 月中席位回收，清仓后顺位下一位补入，同时占用席位恒 ≤ K（引擎内约束，单扫描准入数核对通过）。
- fills 路由/限价抽验：路由 36、阶梯限价 23、止盈价 11 全部逐分核对；逐档 fill-stop（每档至多一次成交）核对通过；整手核对通过。
- 现金守恒：每日 |Δcash −(成交净现金流+分红现金)| 最大 5.82e-11；权益恒等式最大误差 0.00e+00。
- 止盈样本 11 例、止损样本 4 例：止盈成交价逐分等于 WAC+mult×σ0（WAC 按成交额加权、卖出不减），止损成交价逐分等于 min(棘轮线, 开盘)（线=max(HWM−3σ0) 只升不降，重建核对）；T+1 残部 k3 武装本窗口未发生（armed=0），该机制由引擎契约测试（t10/t20）覆盖，冒烟真实数据未触发。
- 门 8 结构：armed 0 = 兜底 0 + 其他 0 + 滞留 0；stuck==0 断言 PASS；tp_expired 130、tier_expired 4、tier_invalidated 0、below_min_lot 0。
- stats['zones'] 与 BandResult.zones 自洽核对：PASS。
- zone 事件：{"zone_admitted": 18, "zone_holding": 18, "zone_cooling": 15, "zone_stop_triggered": 4, "zone_ladder_expired": 3, "zone_done": 15, "zone_exiting_boundary": 3}。
- fills 总数 40；引擎警告 2 条。

- 止损触发逐例（armed 留滞/停牌/跌停顺延：本窗口为 0 例；以下为止损触发与成交明细）：
  - 2016-02-29 am  zone_stop_triggered: sh.600326 (signal 2016-01-29): session low 7.2100 < stop line 7.5857; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 7.5857
  - 2016-02-29 am  zone_stop_triggered: sh.600335 (signal 2016-01-29): session low 12.1200 < stop line 12.5614; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 12.5614
  - 2016-02-29 am  zone_stop_triggered: sh.600827 (signal 2016-01-29): session low 11.8200 < stop line 11.9591; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 11.9591
  - 2016-02-29 am  zone_stop_triggered: sz.000830 (signal 2016-01-29): session low 4.8100 < stop line 4.8511; ladder tiers and TP orders cancelled for this session; fill at min(line, open) = 4.8511
- 止损样本明细：
  - sh.600326 2016-02-29 am: 成交 7.585727957155041 = min(重建线 7.5857, 开盘 7.77)，σ0=0.3514，3200 股
  - sh.600335 2016-02-29 am: 成交 12.561358827469556 = min(重建线 12.5614, 开盘 13.3)，σ0=0.6262，2000 股
  - sh.600827 2016-02-29 am: 成交 11.959097244144154 = min(重建线 11.9591, 开盘 13.09)，σ0=0.5736，1800 股
  - sz.000830 2016-02-29 am: 成交 4.8510626902951755 = min(重建线 4.8511, 开盘 5.1)，σ0=0.2263，2400 股

## 三、运行身份与预算

- 输入身份：daily d9a63f4cc3032926、halfday manifest 2a414174b5df2eee + 18486939 行、ICW 组合 b09242ee542cf675、行业 4edffc3994fb527a、stk_limit 聚合 3c53abf3b0c39b42、ETF 目录聚合 75777221a8b33502。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；随机种子：none（runner 与引擎均无 RNG）。
- 墙钟 56s（预算 900s）；峰值 RSS 1.50 GB（上限 8 GB）。
- σ0 口径（runner 层钉死）：信号日前 20 个官方交易日 close-to-close 对数收益样本标准差（ddof=1）× P0（信号日官方收盘）；21 个收盘价含信号日；不足 20 个收益或任一收盘缺失（次新/停牌）剔除并计数。
- 运行层适配（相对 F3R3，已在 manifest 披露）：ETF 腿意图优先级 10^6 → 999（BR-1 跨层护栏）；park 到期改为窗口后首个整历月月末+1；臂 B 路径仅保留 w_T 缩放（zones 模式无月末减仓原语，S-v14-15 重叠护栏禁止个股意图）。

## 四、结论

- 冒烟核对全部 PASS。未发现引擎行为与契约 §10 不符之处。全期运行待主对话验收后另行发起。