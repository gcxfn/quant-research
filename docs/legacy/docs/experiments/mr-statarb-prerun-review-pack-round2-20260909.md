# 残差均值回归主线 — Codex 运行前审核材料包·第2轮（2026-09-09）

**审核性质：第1轮 CHANGES_REQUESTED 后的修复复审。正式全量运行仍未执行。本次不审收益工件（仍无工件）。**

## 送审文件

| 文件 | 说明 |
|---|---|
| `experiments/mr_statarb.py` | 修复版，2259 行（原 2132 行），零第三方依赖 |
| `tests/test_mr_statarb.py` | 修复版单测，973 行、51 项（原 46 项） |
| `docs/plans/mr-statarb-preregistration-draft-20260909.md` | 冻结预登记 V3.1（未改动） |
| 第1轮材料包 | `docs/experiments/mr-statarb-prerun-review-pack-20260909.md`（含9条解释项原文） |

## 第1轮8项P1的修复对照

| # | 问题 | 修复 | 关键测试 |
|---|---|---|---|
| 1 | 短历史股 KeyError | `screen_stock()` 全分支统一 schema（qualified/excluded/fail_reasons 恒有）；worker 抽纯函数 `pass1_single()`；sh600061 真数据冒烟确认 0 会话不中断 | `test_screen_schema_uniform_when_excluded`、`test_excluded_stock_passes_worker_path` |
| 2 | 压缩时间轴/日历源 | Timeline 改完整交易日轴（含停牌/ST 行），掩码只门控信号与成交；60日窗/10日回归/5日持有按市场交易日计数；行业缺失不阻断到期强退；市场日历改用 tushare `trade_cal`(SSE is_open) | `test_deleting_industry_day_does_not_move_force_date`、`test_calendar_loader_uses_trade_cal_is_open` 等 4 项 |
| 3 | C 误用 B 区间 | `grid_aggregate()` 显式收 ci 参数；B=99.1667%、C=95%；新增 C 聚合→裁决集成测试 | `test_c_aggregate_uses_95_ci_and_verdict_end_to_end` 等 3 项 |
| 4 | 事件日池未排序 | 聚合后按日期升序；乱序股票输入→池与区间逐位相等 | `test_pool_sorted_and_order_invariant` |
| 5 | 事件日≤20 退化 | `m≤block` 返回 degenerate=True、CI=None（不静默改块长）；B 门禁不通过、C 判 INSUFFICIENT_EVIDENCE | `test_degenerate_ci`、`test_c_insufficient_when_degenerate_even_with_30_events` 等 3 项 |
| 6 | A 阶段截尾不对称 | 先判完整 10 市场会话观察期在窗内，再判 success/fail；观察期 z 缺失记 immature 仅计数 | `test_event_near_window_end_immature_even_if_next_day_regresses` 等 3 项 |
| 7 | 涨跌停口径 | 全部经 `quant.market.limit_price`（Decimal ROUND_HALF_UP）；限幅按执行日期（创业板 2020-08-24 起 20%、此前 10%；科创 20%；主板 10%） | `test_reuse_market_limit_price_rounding`（1.15→1.27/1.04）、`test_chinext_pct_switch_date` |
| 8 | 强退受阻错用收盘 | 转 `force_pending` 待退出状态，次一可交易日**开盘**重试（`exit_mode='force_deferred'`） | `test_blocked_force_retries_at_next_open`（次日开盘9.5成交） |

## 解释项裁决的落实

- 项1（否决）→ 按 P1-2 修复为完整交易日轴（note_1）。
- 项7（否决）→ 删除「流动性」桶；启发式只标 assoc（announcement/industry_crash/relationship_break_assoc）；无证据案例列 `other_unidentified`（note_8，`test_failure_assoc_labels`）。
- 项3/4/6 措辞修正：不声称保守、MTM 为估算清算成本（非实际卖出）、主指标改称「每事件机会净期望」且已成交均值单独报告（报告字段改名 `opportunity_per_event`）。
- 项8 落实：报告/manifest 披露 in_date 门控排除的股票与历史区间计数。
- 新增披露：r2 指数相对 trade_cal 的 7 个缺日清单（2022-03-03/03-23/03-31/04-14/05-05/05-09、2023-09-08，note_10）；退化处理（note_11）；强退开盘重试（note_12）；限幅切换（note_13）。`interpretation_notes()` 现共 13 条。

## 验证

- `python -m unittest discover -s tests`：**541 项 OK（跳过 1）**，26.5s（主对话亲跑复验；基线 536 − 旧 mr 46 + 新 51）。
- `py_compile` 通过；真数据只读冒烟：trade_cal 研究窗内 1858 交易日、缺口函数恰报上述 7 日、600519/600061 全链路正常。
- 未运行正式全量（run）、未 git commit、未改 quant/（仅 import quant.market/quant.history）。

## 修复后新暴露的 6 条歧义（请 Codex 裁决；实现者未静默处置）

1. **【重点】60 日残差窗全观测规则 × 指数 7 缺日的级联**：按冻结「窗口内有效观测<60 则该日跳过」逐字实现——单缺日令 ε 缺失约 60 个交易日、z 缺失约 119 个交易日，导致 **2022-03~10、2023-09~2024-02 全市场无信号**（note_10 已披露）。若审核方期望「缺日不传播」，属对冻结公式的另一读法，需裁决（实现者未自行放宽为拉伸窗口——那正是第1轮#2否决的压缩/拉伸）。
2. 停牌/ST 日（价格仅参考）计入 ε 窗口观测：与 P1/P4 既有做法及第1轮#2「不删时间」一致；若要求掩码日当缺数据剔除，会引入新级联，属另一读法。
3. z 窗口（mean/std 的 60 个 ε）同样要求 60 个全定义（级联来源之一）；「ε 序列[t−59,t]的均值/样本标准差」是否允许不足 60 个值，冻结文未写死。
4. A 资格「有效会话」计数口径＝选择窗内 ε 已定义的天数（轴化后与原压缩网格口径数值不同）。
5. 回归概率观察期内 z 缺失记 immature（仅计数）——「越界未成熟」向「缺数据不可观测」的扩展，类别名沿用。
6. 5 日持有按市场日（含停牌/ST 日）计数、掩码日顺延开盘——按第1轮#2「不删除时间」取市场日口径。

**歧义1 的影响面最大**（两个时段全市场无信号会直接决定 A/B/C 的事件数与结论），建议优先裁决。

## 审核结论回执格式建议

PASS / CHANGES_REQUESTED（逐条列位置与最小修复）。PASS 后主对话将指示 flash 执行正式三阶段运行：

```
python experiments/mr_statarb.py run --out-dir artifacts/mr-statarb/round-20260909 --workers 2
```
