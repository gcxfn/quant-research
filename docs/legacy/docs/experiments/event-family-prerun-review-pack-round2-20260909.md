# 事件家族轮 — Codex 运行前审核材料包 第 2 轮（2026-09-09）

**审核性质：第 1 轮 CHANGES_REQUESTED（4 项 P1 代码 + 1 项歧义裁决）后的修复复审。正式 stage1/stage2 仍未执行（`--allow-real-run` 守卫生效，主对话复验确认）。**

## 第 1 轮裁定 → 修复对照

### P1-1 阶段一选择窗左边界
- 修复：`run_stage1()` 事件进入任务前按 `entry_date >= 2020-01-01` 过滤；越界计数 `n_events_before_selection_window` 披露；`stage1_event_h()` 二次防御（`before_selection_window` 状态）；预热期公告只作读取预热。既有完整标签右边界不变。
- 反例单测：2019-06-04 入场被排除、窗内对照 executed。

### P1-2 基准覆盖全 universe
- 修复：`run_stage1()` 删除"无事件股跳过"——全部 board 允许股票均建任务（`n_stock_tasks` = 全 universe），无事件股照常在价格有效会话贡献同窗基准收益，驱动层跨股等权聚合。
- 反例单测：两股仅一只有事件 → 基准含两只。

### P1-3 E5 退出正式口径
- 修复：新增 `stage1_exec_records()`——正式晋级/期限选择输入 = 未叠加 E5 的全部 executed 事件（`unlock_filtered` 一并进 n 与均值）；E5 仅存 `e5_compare` 描述性字段（E1/E2 前后对照）。
- 反例单测：+10% 被 unlock_filtered 事件留在正式统计（n 与均值不变）。

### P1-4 装载失败不静默删除
- 修复：阶段一 `ax is None` → 范围事件逐 h 记 `no_trade:data_missing_axis:<reason>`；阶段二逐条记 no_trade、净 0、进机会分母。披露 `n_stock_axis_load_failures` / `axis_load_failure_reasons` / 分构造计数。某构造全部装载失败 → `aborted_data_insufficient` / `NOT_EVALUABLE`，不出统计。
- 反例单测：阶段一计数 + 阶段二分母各一。

### 裁决-5 E3 同股同日一次交易机会
- 修复：`build_e3()` 按 (symbol, ann_date) 合并（`same_day_rows_merged` 计数），`holder_types` 列表随事件，行级 `by_holder_type` 仅披露。
- 反例单测：+10% 股 10 行 + −10% 股 1 行 → 2 事件、均值 0.025（两事件简单平均），显式断言旧行级加权口径（≈0.0864）不等——判别性测试。

### 歧义 #2 裁决落实
基准资格规则与信号池门禁不同但真是全市场（见 P1-2）；#6/#7 端点读法已固定无运行时可调项。

### 披露更新
- note_20：回购源缺失退市公司 = **E4 事件覆盖的幸存者偏差风险**，E4 不得声称代表完整无偏事件家族。
- note_21/22：选择窗左界读法、E5 双口径说明；manifest warnings ⑨⑩⑪。

## 验证（主对话亲跑复验）
- `python -m unittest tests.test_event_family`：29 项 OK（含 6 个新反例/更新）。
- `python -m unittest discover -s tests`：602 项 OK（跳过 1）。
- 守卫核验：无 `--allow-real-run` 拒绝运行（主对话确认）；`mr_statarb.py` 本体 mtime 未变（仅 import 复用）。
- 主对话逐行审查：`build_e3` 合并逻辑、`stage1_exec_records` 未过滤集、`select_horizon`（超额均值最大、并列取短）、`run_stage1` 驱动（窗过滤/全 universe 任务/失败计数）均与预登记 V4 一致。

## 修复实现者新披露（供复审知悉，非阻断）
1. 全 universe 基准使阶段一任务数扩至全部 board 允许股票（~5900+），正式运行装载耗时将显著增加——语义正确，运行计划需预期。
2. 阶段一装载失败以 `no_trade:data_missing_axis:` 前缀进 `no_trade_by_reason`，与入场失败原因（如 `limit_up_open`）同桶——可按前缀区分，报告层可拆分。

## 复审重点建议
1. 五处修复路径与驱动层聚合（尤其基准跨股等权的 pairs 覆盖与豁免）；
2. 六个新反例测试的判别力（在旧实现下应失败）；
3. E3 新定义在 `prepare_events()` 链路上的传递完整性（holder_types 不进加权）。

## 运行命令（审核 PASS 后）
```
python experiments/event_family.py --stage all --out-dir artifacts/event-family/round-20260909 --workers 4 --allow-real-run
```

## 回执格式建议
PASS（解锁正式两阶段运行）/ CHANGES_REQUESTED（逐条列差异与位置）。
