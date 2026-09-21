# T1 执行报告：batch_011（fcst-reason-struct-full-20260918, llm-v1）

- 执行时间：2026-09-19；运行目录：`artifacts/runs/20260919T031423-fcst-w11-9b30/`（新建）
- 依据：用户授权"持续恢复 T1"；上一状态 batch_010 完成（10/65 批、6,000/38,567 行）

## 1. 任务范围

- batch_011 = row_index.parquet 中 batch_id=11，ordinal 6000–6599 共 600 行（batch_idx 0–599，顺序以 row_index 为准）。
- 本批全部为 type=略减 行（恶化组，sd 判定口径与批 10 相同）；ann_date 2020-01-10 至 2023-12-28，覆盖 2020 疫情冲击、2021 原材料/汇率/海运涨价、2022 封控与地缘冲突、2023 需求疲软与去库存四个阶段。
- 冻结区检查：merge 脚本内置断言本批 600 行 ann_date < 20250101（实际最大 20231228），无 2025+ 行需跳过，符合预期。

## 2. 执行过程（fix_loop 如实记录）

1. **准备**：完整读 schema.md（v1 全文含补充判定细则 10 条）；复用 w10 目录 extract_cues.py、check_batch_full.py、quality_stats.py（零修改），复制改参生成 merge_batch11.py（batch=10→11、ordinal 基 5400→6000、文件名 batch_010→batch_011，校验逻辑逐行保留，含冻结区断言）。w10 目录任何文件未改动。
2. **上下文预算控制**：`extract_cues.py --batch 11` 生成 `work/batch_011_cues.txt`（"ordinal|REASON"紧凑视图：≤400 字符整行原文、>400 做句子级连续摘录标 `[...]`；600 行、74 行长文摘录、122,557 字符）。标注仍逐行人工判定；key_quote 只取单句连续子串。
3. **标注**：600 行由执行 agent 本人逐行标注，输出 `work/batch_011_judge_part1..6.jsonl`（每段 100 行）。口径沿用 schema v1 固化细则：ETC 政策抢装/拆解基金补贴下调/集采/排放法规等政策类→other；上年非经常收益高基数（非经常性损益、处置收益、补贴、坏账转回）→ primary=non_recurring/impairment 且 sd=0；疫情驱动的新冠业务基数回落（口罩/检测/熔喷料/社保减免退坡）→ epidemic_shock；纯复述结果或无因果占位文本→other+low。对 9 行截断摘录（06154、06172、06190、06207、06218、06225、06229、06242、06250）回看源 CSV 全文后再定码。
4. **合并**：`merge_batch11.py` 合并前预检**首轮捕获 3 处失败**：06017 key_quote 误加前缀"受"字（原文句首无"受"）、06427 key_quote 41 字符超限、06512 引文含原文没有的"2022年"前缀（原文为"2022年全年净利润下滑主要系上半年"）。定点修复 3 行后重跑，预检 **600/600 OK**，产出 `data/features/fcst-reason-struct-full-20260918/batch_011.jsonl`（600 行，UTF-8 无 BOM，行序=row_index 顺序；元信息全部由脚本从 row_index 合入，零手抄）。
5. **官方校验**：`check_batch_full.py --batch 11` **首轮 600/600 OK**（退出码 0，0 失败）。
6. **progress.json 更新**：`quality_stats.py --batch 11` 追加 "11" 批统计（shape 与既有批次一致），batches_completed=[1..11]，rows_completed=6600，updated_at=2026-09-19T03:55:47+08:00，cumulative 按 6600 行重算；batch_input_chars 因 w11 未做全文渲染、按任务约定回填为 cues 视图文件字符数 122,557（口径差异已写入 fix_loop 注记）。批 1–10、row_index.parquet、schema.md、源数据零改动（batch_010.jsonl 复核 sha1 未变）；docs/、configs/、src/ 零修改；未做 git、未联网。

## 3. 校验结果

| 项目 | 结果 |
|---|---|
| 行数 | 600/600 |
| merge 预检 | 首轮 3 失败 → 定点修复 → 600/600 OK |
| check_batch_full 官方校验 | 首轮 OK（0 失败，退出码 0） |
| key_quote 逐字通过率 | 1.0 |
| 冻结区（ann_date≥20250101） | 0 行 |

## 4. 质量分布（详见 progress.json "11" 批）

- other_rate_primary：0.1350（81 行：ETC/集采/拆解补贴/排放法规等政策与基数、竞争、战略转型、芯片紧缺等词表外明示因子 + 21 行 low 兜底）
- secondary_null_rate：0.4550
- supports_direction：+1=509 / 0=79 / -1=12（-1 为利好文本对略减的方向矛盾数据质量信号，如 06384 降本增效、06365 土地收储并表、06528 并表增利；0 主要为基数类与无因果行）
- confidence：high=552 / low=48（low 集中于招股书式"经营正常/无重大变化"与纯数字预告占位行，为全项目单批最高，与 2021–2023 年占位型 change_reason 增多一致）
- primary 前列：epidemic_shock=237、cost_up=111、other=81、demand_down=47、non_recurring=43、price_down=36、fx=16、impairment=15。疫情项占比 39.5%，较批 10（48.3%）回落但仍是主因，符合 2020–2022 的时间结构；cost_up 抬升至 18.5%（2021–2022 原材料/海运/汇率成本冲击），与批 8（2022 前段）衔接。
- key_quote 长度：mean=23.8 / p50=24 / p90=35 / max=40
- batch_input_chars：122,557（cues 视图口径，非全文渲染）

## 5. 产物清单

- `data/features/fcst-reason-struct-full-20260918/batch_011.jsonl`（600 行交付物）
- `data/features/fcst-reason-struct-full-20260918/progress.json`（追加批 11，累计重算至 6,600 行）
- 本目录 `scripts/`（extract_cues.py、check_batch_full.py、quality_stats.py 原样复制；merge_batch11.py 改参版）
- `work/`（batch_011_cues.txt、judge_part1..6.jsonl、part1..6.jsonl 合并中间产物）
- `logs/`（render_batch.log、merge_precheck.log、merge_precheck_r2.log、check_batch_full_r1.log、quality_stats.log）

## 6. 未完成内容

- **batch_012（ord 6600–7199，batch_id=12）未开始**：本轮 600 行标注与校验已消耗大部分上下文预算，按"宁可少而全对"在 011 全部通过后干净收尾。下一波起点：batch_id=12、ordinal 基 6600；复用本目录脚本即可（merge_batch11.py 再改参为 batch=12/基 6600，extract_cues.py 传 `--batch 12`），流程与本批完全相同（6×100 分段标注、cues 视图控预算、截断行回看全文）。
- 未连接网络、未重拉数据（源身份以 data/_meta/sha256.tsv 既有基线为准）。
