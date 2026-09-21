# factor-miner 引擎 Codex 运行前审核送审包 第 3 轮（2026-09-10）

审核性质：运行前代码审核第 3 轮。第 2 轮 3 项阻断全部修复并经主对话复验（全仓 874 项 unittest OK/1 skip；pytest 复跑 873+1 skip+5 subtests 全绿）；`REAL_RUN_UNLOCKED` 保持 False。前包：第 1 轮 `…review-pack-20260910.md`、第 2 轮 `…review-pack-round2-20260910.md`。

## 一、第 2 轮阻断处置（主对话复验证据）

### 阻断 1：正式真实数据入口
- 新增 `run_real_pipeline`：`pipeline --allow-real-run`（无 `--fixture`）构建真实 bundle 全流程——TRAIN 粗筛→VALIDATION 家族门禁（六条件+死亡标签）→TRAIN 通过者相关性聚类（0.7 并查集）→预算调整→registry/run_meta（mode=REAL_PIPELINE）。
- **LOCKBOX 实际计算三合一**：纪律三道全过后用 LOCKBOX 真实数据逐候选 `lockbox_evaluate`（清单 formula 重编译且哈希须与 formula_hash 一致；月末 RankIC→月块 bootstrap 块3/B=10000/种子20260909；CI 端点 `(0.025/N, 1−0.025/N)` Bonferroni）→run_log+lockbox_results.json+registry 回填 lockbox_metrics+台账四件齐落。清单须携带 formula/expected_direction/factor_type（缺一拒，主对话实测拒收且不消费台账）；计算异常同样不消费台账（可修复后重跑同一冻结批）。
- 窗口收口统一 `data_fields.enforce_window`（TRAIN 缺省；VALIDATION/LOCKBOX 显式授权参数，单区域完整包含不变）。

### 阻断 2：BENCH/龙虎榜接线（真实数据验证）
- `industry_ret_l1` 改按**指数代码**读 `sw_index_daily/20260909-r3` 全历史 chunk（弃 r2）；top_list→`20260909-r1`、top_inst→`20260909-r3`（按表分批）；`inst_net_buy` 列改真实字段 `net_buy`；t+1 对齐语义不变。
- **接线测试 fail-closed**（`tests/test_factor_miner_round2_fixes.py` 4 项，读真实 TRAIN）：industry_ret_l1 2020 全年>200 日、lhb/inst 真实榜样股窗内非零——零行/配错即测试失败。主对话复跑 15 项全过。
- **dev-smoke 证据**：`artifacts/factor-miner/dev-smoke/20260910_094308/field_wiring_evidence.json`——industry_ret_l1 非空 2,888（4 股×722 日）、lhb_net_buy 36、inst_net_buy 36、turnover_rate 2,903（TRAIN 全窗）。

### 阻断 3：冻结统计闭合
- **集中度改逐样本绝对贡献**（`contrib[sym] += abs(g)`；反例单测显式排除旧实现 0.7059 的符号抵消路径）。
- **P1 完整掩码**：`pool_mask_by_date`（复用 mr_statarb Timeline 冻结语义，2019 起全历史保证 252 会话/20 日流动性正确，失败 RuntimeError fail-closed）接入 RankIC/衰减/十分位/因子值/回测全部入口；掩码缺失=不合格。
- **合并组每窗口公式都执行**：`evaluation_units` 按 merged_lineage 逐条编译（去重键=原始公式串，非 formula_hash）；结果按 `<fid>|w:N` 记入 `train_metrics.by_window`（含 window_params/formula/mean_ic/gate）；反例：ZSCORE(volume,7)+(…,8) 合并组产出 2 单元。
- 新增测试 15 项；factor_miner 全套 160 项。

## 二、剩余解释性读法（第 2 轮 16 条基础上新增 5 条）

(a) `enforce_window` 将 VALIDATION/LOCKBOX 读取授权编码为 loader 显式参数（解锁后正式路径与实现期 TRAIN-only 并存的实现方式）。
(b) lockbox 计算异常不消费一次性台账（可修复后重跑同一冻结批）。
(c) 锁箱清单 formula 重编译哈希必须与 formula_hash 逐字一致。
(d) 家族预算 n_consistent=TRAIN mean_ic 与经济先验同号者（无论是否过线）——预登记 §6 措辞的代码化。
(e) 聚类/VALIDATION 基于合并组基准公式，其余窗口结果仅落 by_window。

## 三、建议审核重点

1. `run_real_pipeline` 与 `run_lockbox` 的路径完整性（是否仍有 n_train_tested=0 的静默分支）。
2. 接线 fail-closed 测试的三字段样板（000016/000030 龙虎榜样板股）抽查。
3. `evaluation_units` 的 by_window 记录与 registry 的一致性。
4. lockbox Bonferroni 端点 `(0.025/N, 1−0.025/N)` 与预登记 α=0.05/N 的对应关系。

## 四、解锁预告（不变）

PASS → 主对话显式翻转 REAL_RUN_UNLOCKED（提交留痕）→ R0 派发（REV/REL/STATE+META，TRAIN-only）→ R0 工件回归审核通道。
