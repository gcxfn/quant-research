# T1 恢复执行报告：batch_009（fcst-reason-struct-full-20260918, llm-v1）

- 执行时间：2026-09-19（恢复依据：用户 2026-09-19 批复"恢复"；暂停记录见本目录 `PAUSE-NOTE.md`，未改动）
- 复用运行目录：`artifacts/runs/20260918T105312-fcst-full-w9-p3m8t6/`（暂停前已建，脚本原样复用，校验逻辑零修改）

## 1. 任务范围

- batch_009 = row_index.parquet 中 batch_id=9，ordinal 4800–5399 共 600 行（batch_idx 0–599，顺序以 row_index 为准）。
- 本批全部为 type=略减 行（按 (type, year) 分层全序落位），ann_date 均在 2018-12/2019-10 区间。
- 冻结区检查：程序断言本批 600 行 ann_date < 20250101，无 2025+ 行需跳过。

## 2. 执行过程（fix_loop 如实记录）

1. **恢复预检**：读取 schema.md（v1 全文，含补充判定细则 10 条）、check_batch_full.py、merge_batch9.py、render_batch.py、quality_stats.py 及暂停前 work/ 产物。
2. **part1–3 复用**：暂停前已完成 ord 4800–5099（300 行 judge 结果）。按 PAUSE-NOTE "以复用时校验为准"，恢复后先做独立预检（词表闭合、secondary≠primary、sd/confidence 合法、key_quote 为 raw change_reason 逐字子串），结果 300/300 通过、0 失败，予以复用、未改动。
3. **part4–6 新标注**：本轮对 ord 5100–5399（300 行）逐行标注（标注器为执行 agent 本人），元信息（ts_code/end_date/ann_date/update_flag）不手抄，由 merge 脚本从 row_index 程序化合入。标注口径沿用 schema v1 固化细则（如：明确点名政策因子→other；非洲猪瘟不算 epidemic_shock；无因果仅复述结果→other+low；type 与原因方向相反→-1 留作数据质量信号）。
4. **合并**：`merge_batch9.py` 合并前预检**首轮通过**（600/600，含 key_quote 逐字校验、词表闭合、secondary≠primary、sd/confidence 合法），产出 `data/features/fcst-reason-struct-full-20260918/batch_009.jsonl`（600 行，UTF-8 无 BOM，行序=row_index 顺序）。
5. **官方校验**：`check_batch_full.py --batch 9` **首轮 600/600 OK**（退出码 0，0 失败）。无定点修复项，故无修复-复检循环。
6. **progress.json 更新**：`quality_stats.py --batch 9` 追加 "9" 批统计（shape 与既有批次一致），batches_completed=[1..9]，rows_completed=5400，updated_at 刷新，cumulative 按 5400 行重算。批 1–8 与 row_index.parquet、schema.md、源数据零改动。

## 3. 校验结果

| 项目 | 结果 |
|---|---|
| 行数 | 600/600 |
| check_batch_full 官方校验 | 首轮 OK（0 失败） |
| key_quote 逐字通过率 | 1.0 |
| merge 预检 | 首轮 OK |

## 4. 质量分布（详见 progress.json "9" 批）

- other_rate_primary：0.1717（103 行；主要为政策类/结构类/基数类明示因子及 5 行 low 兜底）
- secondary_null_rate：0.4767
- supports_direction：+1=586 / 0=5 / -1=9（-1 为 type 与原因方向矛盾的数据质量信号，如 ord 5246/5249/5275 原文陈述增长但 type=略减）
- confidence：high=585 / low=15
- primary 前列：cost_up=171、demand_down=142、other=103、price_down=60、non_recurring=60（本批集中于 2019 年成本上升与需求走弱环境，与批 8 的 2018 略减结构衔接合理）
- key_quote 长度：mean=21.8 / p50=21 / p90=31 / max=40
- batch_input_chars：182,348

## 5. 产物清单

- `data/features/fcst-reason-struct-full-20260918/batch_009.jsonl`（600 行交付物）
- `data/features/fcst-reason-struct-full-20260918/progress.json`（追加批 9）
- `work/batch_009_judge_part4/5/6.jsonl`（本轮标注）、`work/batch_009_part1..6.jsonl`（合并中间产物）
- `work/batch_009_input.txt`、`work/batch_009_judge_part1-3.jsonl`、`work/tmp_check_part1.txt`（暂停前留档，未改动）
- `logs/merge_precheck.log`、`logs/check_batch_full_r1.log`、`logs/quality_stats.log`

## 6. 未完成内容

- **batch_010（ord 5400–5999）未开始**：本轮上下文预算已消耗大部分，按"宁可少而全对，不追量"约束在 009 完成并全量校验通过后干净收尾，未渲染 010 输入、未写任何 010 判定文件。下一轮可直接复用本目录脚本，流程与批 9 相同（先改 merge_batch9.py 的 batch/ordinal 基数，或另写 merge_batch10.py）。
- 未连接网络、未重拉数据（源身份以 data/_meta/sha256.tsv 既有基线为准）；docs/、configs/、src/ 零修改；未做 git。
