# V3 臂C 机制拆分轮 — Codex 运行前审核材料包（2026-09-10）

**审核性质：实现代码运行前审核。M1/M2 正式回测未执行；唯一已执行的是 M3 复现校验（实现正确性校验）。**

## 送审文件

| 文件 | 说明 |
|---|---|
| `experiments/v3_arm_c_mechanism.py` | 新入口，457 行（三形态运行/深度族指标/比较规则/M3 复现校验/summary 渲染） |
| `experiments/v3_repair_round.py` | 引擎最小改动：`run_repair_portfolio` 新增 `weight_source`/`fixed_weight` 可选参数（默认 vol_target，默认行为有专测保证逐位不变） |
| `tests/test_v3_arm_c_mechanism.py` | 247 行、22 项离线单测 |
| `docs/plans/v3-arm-c-mechanism-split-preregistration-draft-20260910.md` | 冻结预登记（用户已批准） |
| `artifacts/v3-arm-c-mechanism/round-20260910/` | M3 复现校验工件（run_meta.json 含 reproduction_check 双 True） |

## 审核基准

- 预登记每个冻结定义逐行核对：M1=固定 0.75（区间中点非拟合）/M2=1.00 仅再平衡/M3=上轮 C 原样；比较规则三分支（两指标相对改善均<10% 无增量 / 至少一项>20% 且另一项不劣于有增量 / 其余不确定）。
- 重点：①`weight_source` 注入路径不改任何选股/门禁/成本/执行规则；②深度族指标定义（新高相等日不计、严格低于才计连续、≥20% 切段、未修复段含样本末）；③M3 复现校验的严格性（equity/trades 逐位）。
- 本轮为**描述性机制拆分**：无 PASS/FAIL 门禁，产出=指标表+比较结论+披露；不构成生产变更依据。

## M3 复现校验（实现正确性第一道校验，主对话已复核 run_meta）

- equity_bitwise_equal = True；trades_bitwise_equal = True（对 `round-20260909-formal/variant-C.json`）。
- M3 深度族（新指标首次产出）：最长连续水下 **1,123 日**；平均回撤深度 **19.78%**；≥20% 深回撤 **11 段**（最长 2023-06-21→2025-08-22 共 528 交易日、最深 36.91%）。

## 实现者自报验证（主对话已亲跑复验）

- `python -m unittest tests.test_v3_arm_c_mechanism`：22 项 OK。
- `python -m unittest discover -s tests`：628 项 OK（跳过 1）。
- M3 复现校验 PASS 落档；未跑 M1/M2；批次目录只增不覆盖（"x" 模式）。

## 实现者歧义清单（5 条，均保守读法）

1. 深回撤段切分：深度回落到 20% 以下即切段（字面读法，段数偏多的保守披露）。
2. 恰等于阈值：≥20% 计入；比较规则恰等 10%/20% 落"不确定"（1e-12 容差防浮点噪声）。
3. 无水下日时 avg_drawdown_depth 返回 None（不伪装零深度）。
4. fixed 源月度披露：reason=fixed_weight_source、sigma_ann=None，不进豁免计数（结构兼容上轮渲染）。
5. 比较分母为 0/缺失：相对幅度 None → "不确定"。

## 运行命令（审核 PASS 后）

```
python experiments/v3_arm_c_mechanism.py --variant all
```

## 回执格式建议

PASS（解锁三形态正式回测）/ CHANGES_REQUESTED（逐条列差异与位置）。
