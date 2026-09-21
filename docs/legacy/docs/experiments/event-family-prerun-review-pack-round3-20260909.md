# 事件家族轮 — Codex 运行前审核材料包 第 3 轮（2026-09-09，窄范围）

**审核性质：第 2 轮唯一残留 P1（基准端点日期错配）的修复复审，只审该基准路径。其余项第 2 轮已通过。**

## 第 2 轮裁定 → 修复

- **P1：晚于窗口上市的股票，基准两端点 bisect 落在上市首日，用未来价格冒充历史基准（+20% 反例）。**
- 修复（`experiments/event_family.py` `stage1_task()` 基准取价处）：取价前必须同时满足 `ax.dates[i1] == d1 and ax.dates[i2] == d2`，不满足则该股票不贡献该窗口基准（无价格观测，不凭空补价）。
- **实施说明（如实披露）**：flash 子代理在用量上限中断前完成了该处代码编辑但未及写测试与报告；3 个反例单测由主对话补写并验证。事件族其余代码无任何改动。

## 新增反例单测（`tests/test_event_family.py`，主对话补写）
1. `test_round2_benchmark_window_before_listing_no_contribution`：上市 2021-01-04（open10→close12），请求 2020-01-02→2020-01-06 → bench 为空（旧实现返回 +20%，测试具判别性）；
2. `test_round2_benchmark_window_straddling_listing_no_contribution`：左端点 2020-12-31 在上市前 → 无贡献；
3. `test_round2_benchmark_exact_match_contributes_correctly`：端点精确匹配 → 贡献 = 12.5/10.0−1。

## 验证（主对话亲跑）
- `python -m unittest tests.test_event_family`：32 项 OK（含 3 个新反例）。
- `python -m unittest discover -s tests`：全仓 OK（跳过 1）。
- 守卫与 mr_statarb 本体未动确认。

## 复审重点建议
仅核对该基准取价处的日期相等守卫与三个反例的判别性。

## 回执格式建议
PASS（解锁正式两阶段运行）/ CHANGES_REQUESTED。
