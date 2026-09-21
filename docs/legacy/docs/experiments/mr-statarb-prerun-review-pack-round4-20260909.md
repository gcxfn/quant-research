# 残差均值回归主线 — Codex 运行前审核材料包·第4轮（2026-09-09）

**审核性质：第3轮 CHANGES_REQUESTED（仅剩1处P2）后的窄范围修复复审。正式全量运行仍未执行。**

## 送审文件

| 文件 | 说明 |
|---|---|
| `experiments/mr_statarb.py` | 修复版（`_mae_mfe` 重构） |
| `tests/test_mr_statarb.py` | 单测 60 项（前轮 59 项） |
| 前轮材料包 | `mr-statarb-prerun-review-pack-round3-20260909.md`（第1/2轮包同目录） |

## 第3轮P2的修复对照

| 问题 | 修复 | 关键测试 |
|---|---|---|
| 开盘退出的 MAE/MFE 漏纳入退出开盘价本身（买10元、持仓期最低9元、顺延开盘8.5卖出→毛收益−15%但MAE只有−10%，低估隔夜跳空） | 开盘退出日仍排除当日 high/low（卖出后极值不进），但把**退出开盘价**作为持仓期价格点并入 MAE/MFE 更新（实现重构为 `_absorb()` 统一吸收，low≤high 性质保证与"低点进MAE、高点进MFE"等价）；顺带修掉实现初稿的双重相除 bug；收盘退出（force_close/mtm）仍整天计入 | `test_open_exit_price_enters_mae_mfe`（改变卖出后极值→MAE/MFE不变；退出开盘价9.5→8.2→MAE −5%→−18%）+ 3 项既有断言按新口径更新 |

## 验证

- `python -m unittest discover -s tests`：**550 项 OK（跳过 1）**，29.5s（主对话亲跑复验；前轮 549 + 新 1）。
- 未运行正式全量（run）、未 git commit、未改 quant/。
- 披露措辞核对：无信号时段均标注"市场级**近似**"，逐股实际覆盖以 screening.json 每股三口径为准，未表述为精确覆盖。

## 修复后新暴露的 1 条歧义（请 Codex 裁决）

1. **退出开盘价在 MAE/MFE 中的定位**：实现把退出开盘价同时视为该时点的高/低点候选（min/max 语义）。退出开盘价介于持仓期 low/high 之间时不改变结果；仅当低于历史低点（加深MAE）或高于历史高点（抬升MFE）时生效。极端情形（跳空高开获利了结时，高于买价的退出价是否应计入MFE）的语义请确认。

其余歧义（占位日vs停牌分桶、2019读取起点、无信号区间近似、qfq缺行不混填raw、回归缺z记immature、60日全观测窗级联）均已被前轮裁决接受或披露，`interpretation_notes()` 现 16 条。

## 审核结论回执格式建议

PASS / CHANGES_REQUESTED（逐条列位置与最小修复）。PASS 后主对话将指示 flash 执行正式三阶段运行：

```
python experiments/mr_statarb.py run --out-dir artifacts/mr-statarb/round-20260909 --workers 2
```
