# 事件家族轮 R1 — Codex 工件复算验证材料包（2026-09-10）

**审核性质：运行后工件复算。三阶段运行前审核已三轮 PASS（round3 窄范围）；OOM 修复为内存/管线层（D-2026-09-10-02，统计语义零变更，含 note_23 解禁索引事件级语义披露）。正式运行已完成，判定待复算确认。**

> **v1.1 更新（2026-09-10）：Codex 工件审核 P1/P2 修复已完成，复算材料以新批次 `artifacts/event-family/round-20260909-r2/` 为准**——统计判定与原批次逐位一致（manifest.reproduction_check：h_tables/bootstrap/selection 全字段浮点逐位对照 **n_diffs=0**）。r2 新增：`event_day_pools`（与 bootstrap 同池，E1_bull h=10 实测 586 日/Σ7,354）、`benchmark_detail`（9,613 窗口）、`exclusion_chain`（raw→窗内→可入场→完整标签→执行全链）、`stage1_events_<构造>.json`×5（逐事件含超额与缺失原因）。计数字段更正：原 `n_events=29,781` 实为 E3+E4 之和（正确分层：E1_bull 24,384/E1_bear 21,375/E1_other 1,050/E2 3,011/E3 16,181/E4 13,600）；`n_tradable_*` 更名 `n_entry_possible_*`（仅"存在下一市场日"，未经成交门禁）；`same_day_dup_dropped=2,800` 为 E4 专用（`e4_same_day_dup_dropped`）。本包下文旧计数按原批次字段名保留作对照。结论文档已附"v1.1 计数字段更正"（`docs/experiments/event-family-round1-20260910.md` 文末）。

## 工件

| 文件 | 说明 |
|---|---|
| `artifacts/event-family/round-20260909-r2/` | **复算目标批次**（v1.1：含 event_day_pools/benchmark_detail/exclusion_chain/逐事件文件，reproduction_check n_diffs=0） |
| `artifacts/event-family/round-20260909/stage1.json` | 阶段一全量表（h_tables×4构造×6期限、selection_trace、counts、e1_bear_filter_artifact、interpretation_notes 23 条） |
| `artifacts/event-family/round-20260909/stage2.json` | 阶段二（n_constructs=0，无晋级构造，仅计数与工件结构） |
| `artifacts/event-family/round-20260909/summary.md`、`manifest.json` | 汇总与运行元数据 |
| `docs/experiments/event-family-round1-20260910.md` | 轮次结论摘要（本文的对表目标） |

## 关键结果（供复算对表）

- **晋级判定：四构造 × h∈{3,5,10,20} 全部未过线**（超额毛均值 ≥34bps 且 95%CI 下界>0 双条件）：
  - E1_bull：h=5 均值 +0.357%/CI[−0.104%,+0.814%]；h=10 +0.692%/CI[−0.033%,+1.407%]；h=20 +0.732%/CI[−0.476%,+1.948%]——均值过线、CI 下界均<0；
  - E2/E3/E4：均值亦不过线（E2 h=20 低至 −1.54%）。
- selection 全 null；stage2 n_constructs=0。
- 计数：n_events=29,781；n_tradable E1_bull=24,384 / E2=3,011 / E3=16,137 / E4=13,593；窗前剔除 19,536；基准任务 5,551、装载失败 104（no_rows 101/no_data 3）；解禁索引 25,691（自 5,661,143 行流式去重）；周末公告 15,232。
- bootstrap 协议：事件日块、块长 20、B=10000、种子 20260909、2.5/97.5 分位（bootstrap_excess 字段含 n_days/n_events/degenerate=false 全记录）。
- E5 对照（描述性）：E1_bull h=10 剔除前后 0.309%→0.304%，被过滤 82 事件自身均值 +0.759%。

## 运行期代码改动披露（如实）

1. OOM 修复两处（D-2026-09-10-02，主对话实施）：`build_unlock_index_from_dir` 流式去重（n_records 语义改事件级，note_23）；`_run_pool` consume 流式聚合（基准均值=累计和/计数，与列表均值等价）。期间一处主对话手误（raw_rows 键路径）已修，全程单测+全仓回归绿。
2. 统计语义零变更声明：无冻结定义改动；判据/晋级线/窗口/成本口径与预登记 V4 完全一致。

## 建议复算路径

1. 从 stage1.json h_tables 复核晋级判定逻辑（双条件）与 selection_trace 一致性；
2. 抽 E1_bull h=10 的 bootstrap_excess 复算（事件日池、块自助、种子）对表 lower=−0.0331%；
3. 抽 3 只股票的事件构造（E1 去重/E3 同日合并/E4 冷却）与源表对表；抽 2 条解禁记录核 E5 可知性（ann_date≤决策日）；
4. 核对计数链（rows→events→tradable）与左界/周末/装载失败披露齐备性；
5. 核对 stage2 n_constructs=0 与"无晋级→FAIL 封存"的判定渲染。

## 回执格式建议

PASS（工件与判定可落锤）/ CHANGES_REQUESTED（逐条列差异与位置）。
