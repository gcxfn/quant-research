# factor-miner 引擎 Codex 运行前审核送审包 第 4 轮（2026-09-10）

审核性质：运行前代码审核第 4 轮。第 3 轮 5 项中 4 项修复+1 项按裁决选项 B 收窄范围；主对话复验通过。全仓 900 项 unittest OK/1 skip（pytest 899+1 skip+5 subtests）；REAL_RUN_UNLOCKED 保持 False。前包：round3。

## 一、第 3 轮处置（主对话复验）

| 项 | 处置 | 复验 |
|---|---|---|
| ①TRAIN 失败者可被 VALIDATION 标 PASS | 拆分：`pipeline`=TRAIN-only（产冻结清单 candidates.jsonl+canonical 哈希）；新增独立 `validation` 子命令（只收清单；清单哈希须与 TRAIN 批 run_meta 一致防拼批；**逐条以 registry 为唯一事实源复核 train gate_pass**，未过线者落 validation_rejected 且零 VALIDATION 读取）；`apply_validation_results` 防御：train gate_pass=False 无论验证结果不置 PASS+suppressed 标记 | 19 项新反例测试（含 TRAIN IC=0.01 伪造清单/篡改 registry 两路径、失败+全过仍不 PASS）；主对话复跑 19 项+全仓绿 |
| ②正式 universe 可缩成两只股 | 正式 pipeline/validation 拒绝 `--symbols`（PipelineScopeError）；`load_formal_universe` 引擎侧枚举全数据集→pool_mask_by_date→universe.json（清单+sha256+排除计数）落盘，validation 复核哈希 | --symbols 拒绝反例+哈希篡改拒收测试 |
| ③三区缺因子窗口预热 | `enforce_window` 新增 warmup 通道（只认 warmup_read 原样 descriptor，伪造拒）；`build_real_bundle` 缺省预热 365 日历日；`truncate_to_region` 统计前截断——预热段不产生任何观测 | 真实数据反例：60 日窗区域首月不缺值（含 warmup=0 对照）；预热统计只含区域月份 |
| ④事件路径未接入 | **采选项 B 收窄**：正式 pipeline/lockbox 显式拒绝 event 型（PipelineScopeError+范围声明）；`EVENT_SCOPE_NOTE` 入 run_meta/run_log："本轮解锁范围=连续因子引擎（R0 四矿区均连续因子）；事件路径待未来轮次补齐送审" | event 拒绝反例+scope 声明落档测试 |
| ⑤makedirs 可覆盖 | `_check_out_dir_free`：pipeline/validation/lockbox 输出目录必须不存在 | 独占目录反例 |

新增 `tests/test_factor_miner_round4_fixes.py` 19 项；factor_miner 全套 179 项；第 3 轮已通过的四项（接线/掩码/集中度/窗口展开）未动。

## 二、新增解释性读法（5 条）

1. 预热段（≤365 日历日）读取视为区域读取一部分，但预热段日期零统计观测（truncate_to_region 强制；region_start_idx 缺省 0=合成 bundle 语义不变）。
2. validation 全部候选被 TRAIN gate 拒收时不读任何 VALIDATION 数据、照常落盘（n_admitted=0 非异常）。
3. candidates.jsonl 收录全部评估单元（含未过线者留痕）；validation 仅 is_base 条目可进入；by_window 结果留 TRAIN 批次。
4. registry 为 TRAIN gate 唯一事实源；清单 train_gate 字段仅留痕，不一致以 registry 为准拒收。
5. event 型（formula 空的合法 schema）在 dedup 后、任何数据读取前被拒；dev-smoke/fixture 不受影响。

## 三、建议审核重点

1. candidates.jsonl 哈希防拼批链路（TRAIN run_meta ↔ validation 入口校验）。
2. warmup descriptor 的强校验（伪造 descriptor 拒绝路径）。
3. universe 冻结的排除计数与 P1 口径一致性。
4. 选项 B 收窄声明的完备性（是否所有正式入口都有 scope 声明）。

## 四、解锁预告（不变，范围收窄后）

PASS → 主对话显式翻转 REAL_RUN_UNLOCKED → R0 派发（REV/REL/STATE+META，**连续因子**，TRAIN-only）→ R0 工件回归审核通道。事件型引擎路径不在本轮解锁范围。
