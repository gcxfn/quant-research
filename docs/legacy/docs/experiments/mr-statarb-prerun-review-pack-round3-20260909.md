# 残差均值回归主线 — Codex 运行前审核材料包·第3轮（2026-09-09）

**审核性质：第2轮 CHANGES_REQUESTED（剩3处）后的修复复审。正式全量运行仍未执行。**

## 送审文件

| 文件 | 说明 |
|---|---|
| `experiments/mr_statarb.py` | 修复版，2382 行（前轮 2259 行） |
| `tests/test_mr_statarb.py` | 单测 1142 行、59 项（前轮 51 项） |
| 前轮材料包 | `mr-statarb-prerun-review-pack-round2-20260909.md`（第1轮包同目录） |

## 第2轮3处的修复对照

| # | 问题 | 修复 | 关键测试 |
|---|---|---|---|
| 1 | 股票缺行仍压缩时间轴 | `Timeline` 按**上市区间内市场日历**建轴（`market_calendar ∩ [max(ipo, STUDY_READ_FROM), min(out, 读端)]`）；缺行日用不可成交占位行（无价格、eligible=False、volume=0）补齐；窗口与持有计数不再漂移；占位日买入按一次尝试记 `no_trade(data_missing)` 不延后。顺带修掉轴下界空串边界 bug | `test_missing_stock_row_keeps_force_date`、`test_deleted_buy_day_no_trade_not_deferred`、`test_axis_bounded_by_listed_study_window` |
| 2 | 观察期缺 z 不对称 | 先判完整 10 日观察期在窗内→再查 10 日 z 是否全齐（任一日缺失→immature 仅计数）→齐全后才判 success/fail | `test_regression_missing_z_symmetric_immature` |
| 3 | force_deferred 的 MAE/MFE 含卖出后极值 | 新增 `OPEN_EXIT_MODES=("z_open","force_deferred")` 统一不读退出日盘中极值；收盘退出（force_close/mtm）仍整天计入 | `test_force_deferred_mae_mfe_exclude_post_sell_extremes`、`test_force_close_still_includes_exit_day` |

## 第2轮6条歧义裁决的落实

- 歧义1（接受+披露覆盖损失）：新增 `z_gap_spans()`，manifest 输出 `index_market_gap_dates`/`no_signal_spans_approx` + 警示，报告口径披露。实测 7 缺日→两段无信号期 `2022-03-03→2022-11-01`、`2023-09-08→2024-03-12`（`test_z_gap_spans_merge`）。
- 歧义4（三口径区分）：`screen_stock` 记录 `n_market_days`/`n_eps_days`/`n_signal_days`（含剔除分支），manifest/report 说明。真数据冒烟：600519 A 窗 970 市场日/700 ε 日/598 可发信号日（`test_screen_three_day_counts`）。
- 歧义2/3/6 为接受既有读法，无需改代码；`interpretation_notes()` 现 15 条（note_1/10 更新，新增 note_14/15）。

## 验证

- `python -m unittest discover -s tests`：**549 项 OK（跳过 1）**，25.6s（主对话亲跑复验；前轮 541 + 新 8）。
- 真数据只读冒烟：600519 轴 1858 日、占位 0；600061 同轴但 ε/信号 0 日正常剔除。
- 未运行正式全量（run）、未 git commit、未改 quant/（仅 import 调用）。

## 修复后新暴露的 4 条歧义（请 Codex 裁决）

1. 占位日与原样停牌/ST 日在轴上的区分：缺行占位日买入记 `data_missing`、停牌/ST 日记 `status_blocked`——都不可成交且不删时间，原因标签不同。
2. 轴起点取 `max(ipo, STUDY_READ_FROM)`：上市早于 2019 的股票轴从 2019-01-02 起（与 P1/P4 读取口径一致）。
3. 市场级无信号时段的"近似"性：`z_gap_spans` 按 119 交易日逐缺日合并，未扣个股上市/in_date/自身缺口的额外影响（报告标注近似；精确覆盖由 screening.json 每股三口径反映）。
4. 真实数据若出现 qfq 缺行而 raw 有价：本实现按"无价不可成交占位"处理（不凭空补价，符合歧义2裁决），未做 raw 回填——如需回填另行裁决。

## 审核结论回执格式建议

PASS / CHANGES_REQUESTED（逐条列位置与最小修复）。PASS 后主对话将指示 flash 执行正式三阶段运行：

```
python experiments/mr_statarb.py run --out-dir artifacts/mr-statarb/round-20260909 --workers 2
```
