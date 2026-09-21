# 事件家族轮 — Codex 运行前审核材料包（2026-09-09）

**审核性质：实现代码运行前审核（pre-run code review）。正式 stage1/stage2 运行未执行——入口带 `--allow-real-run` 守卫，无该开关即拒绝运行真实数据（退出并打印提示）；本轮交付只跑单测与合成冒烟。请审实现与预登记的一致性，不审任何真实数据结果（尚无工件）。**

## 送审文件

| 文件 | 说明 |
|---|---|
| `experiments/event_family.py` | 实现，1288 行；复用 `experiments/mr_statarb.py`（import 为 mrs，本体未改）的数据装载/Timeline/bootstrap/贡献度组件 |
| `tests/test_event_family.py` | 离线单测，495 行、23 项（零第三方依赖、合成数据） |
| `docs/plans/event-family-preregistration-draft-20260909.md` | 冻结预登记 V3（外部两轮审核闭合，用户确认，D-2026-09-09-16） |

## 审核基准

预登记 V3 每个冻结定义逐行核对。重点五类风险：

1. **无前视**：E5 可知性（仅 ann_date ≤ 决策日的解禁记录参与过滤）；入场=公告次一交易日开盘；阶段一可交易组从次日开盘起算；期限选择只用选择窗内完整标签（入场后 h 会话收盘 ≤ 2023-12-31）。
2. **时间轴**：市场日一律推进会话计数（缺行日计入、只影响估值与可成交性）——单测含"5 会话持有遇缺行日退出日不变"反例；强退=第 h 会话收盘；递延=次一可交易日**开盘**重试（继承 MR force_deferred，非收盘顺延）。
3. **事件定义与去重**：E1 同股同季最早公告+类型分层；E2 与 E1 去重先到为准；E4 (ts_code,ann_date) 首行+同股冷却 120 市场交易日；E5 窗口 [float_date−5 市场交易日, float_date] 含两端。
4. **统计协议唯一性**：块 bootstrap 复用 `mrs.block_bootstrap_mean_ci`（块长 20、B=10000、种子 20260909、事件日池升序、退化 fail-closed）；阶段一 95% CI；阶段二双侧 Bonferroni 端点 0.05/(2N) 与 1−0.05/(2N)；机会净期望分母含 no_trade；Top5 按股票聚合（复用 `mrs.contribution_stats` 冻结公式，Σ_all=0 直接不通过）。
5. **晋级与裁决**：晋级线=某 h∈{3,5,10,20} 超额毛均值 ≥34bps 且 95%CI 下界>0（只看可交易组）；期限唯一选择=超额毛均值最大、并列取短；裁决=n_executed≥30 ∧ 校正下界>0 ∧ Top5≤50%。

## MR 语义继承映射（实现者申报，供逐条核对）

- 入场：`entry_attempt`（缺行/ST停牌/无量/P1 门禁/一字涨停开盘 → no_trade 不延后，MR note_3 语义）；
- 强退：`sell_close_blocked`（第 h 会话收盘，受阻转待退出）；
- 递延：`sell_open_blocked`（次一可交易日开盘重试，开盘仍受阻继续递延；MR #8/第2轮#3）；
- 缺行：`mrs.Timeline`（上市区间×trade_cal 轴，缺行不可成交占位，市场日推进计数）；
- 期末估值：右端最后可得收盘 MTM，净=毛−成本档一次扣减（估算清算成本，MR note_4）；
- bootstrap/贡献度：直接复用 mrs 实现。

## 数据批次说明（含主对话抽审结论）

- forecast/express：20260909-r1，此前抽审 PASS（ann_date 100%）。
- repurchase/stk_holdertrade/share_float：20260909-r3，主对话抽审 **PASS（含披露）**：61,718 / 149,108 / 5,661,143 行，ann_date 100%、零失败日、月度连续、零重复；**①tushare 回购表不含已退市公司（E4 退市股事件缺失，只减样本无前视）；②解禁表早年覆盖偏薄（2016—2019 年均事件 ~1500 vs 2021+ ~3000，源覆盖与真实增长混合）；③表外代码（北交所/老三板/4 个吸收合并退市码）由 P1 池排除并计数**。
- share_float 事件粒度：27,775 个 (ts_code,ann_date,float_date) 事件 ×平均 204 持有人明细行；ann_date ≤ float_date 100%（可知性成立）。
- 日线与时点池：P1 层（本地数据集 + baostock 退市/ST/停牌）。

## 实现者自报验证（主对话已亲跑复验）

- `python -m unittest tests.test_event_family`：23 项 OK（主对话复跑确认）。
- `python -m unittest discover -s tests`：**594 项 OK（跳过 1）**（主对话复跑确认，8.4s）。
- 守卫核验：不带 `--allow-real-run` 调用即拒绝并打印提示（主对话确认）。
- `mr_statarb.py` 本体未被修改（mtime 早于实现派发时间，仅被 import）。
- 合成冒烟全链路（事件构造→晋级/期限选择→阶段二聚合裁决→工件写出）通过。

## 实现中发现的预登记歧义点（18 条随工件 `interpretation_notes()` 输出，主要 10 条）

**请 Codex 逐条裁决；不可接受者指出须改读法。**

1. 通用过滤冻结文只列 ST/停牌/<252 交易日 → 实现采用 **P1 完整门禁**（含 20 日中位成交额 ≥5000 万流动性门，从严）。
2. 基准=全 universe 价格有效即入（冻结文未定义基准池门禁；实现读法：等权基准不做流动性过滤）。
3. 阶段一可交易组均值只计实际入场事件（机会口径分母冻结文写在阶段二）。
4. E3 冻结文无去重规则 → 逐行计事件（同股同日多条增持各计一次），holder_type 分层披露。
5. E1/E2 同日同股公告 → 取 forecast 在先。
6. E4 冷却间隔必须 **>120 会话**（严格大于）；冷却基准位置=首个 ≥ann_date 的市场日。
7. E5 窗口端点按市场日历位置 bisect_left，含两端。
8. 开盘=跌停不阻断买入（冻结文只写一字涨停；MR 的避雷过滤器是 MR 策略规则，不搬入本轮）。
9. 完整标签边界按 h 逐水平判定（每个候选 h 各自判定标签是否在选择窗内完成）。
10. share_float 无后缀 ts_code（老三板 400xxx 等）松映射（6→sh、0/3→sz、其余剔除计数）。

## 运行命令（审核 PASS 后）

```
python experiments/event_family.py --stage all --out-dir artifacts/event-family/round-20260909 --workers 4 --allow-real-run
```

## 回执格式建议

PASS（解锁正式两阶段运行）/ CHANGES_REQUESTED（逐条列差异与位置）。
