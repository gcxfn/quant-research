# T1 执行报告：batch_010（fcst-reason-struct-full-20260918, llm-v1）

- 执行时间：2026-09-19；运行目录：`artifacts/runs/20260919T024020-fcst-w10-7399/`（新建）
- 依据：用户授权"持续恢复 T1"；上一状态 batch_009 完成（9/65 批、5,400/38,567 行）

## 1. 任务范围

- batch_010 = row_index.parquet 中 batch_id=10，ordinal 5400–5999 共 600 行（batch_idx 0–599，顺序以 row_index 为准）。
- 本批全部为 type=略减 行（恶化组），ann_date 2019-01-10 至 2020-12-31；本批处于 2019 成本/需求下行与 2020 疫情冲击交界。
- 冻结区检查：程序断言本批 600 行 ann_date < 20250101（merge 脚本内置断言），无 2025+ 行需跳过，符合预期。

## 2. 执行过程（fix_loop 如实记录）

1. **准备**：完整读 schema.md（v1 全文含补充判定细则 10 条）；复用 w9 目录 render_batch.py、check_batch_full.py、quality_stats.py（零修改），复制改参生成 merge_batch10.py（batch=9→10、ordinal 基 4800→5400、文件名 batch_009→batch_010，校验逻辑逐行保留，另加冻结区断言）。w9 目录任何文件未改动。
2. **上下文预算控制**：w9 全文渲染输入约 18.6 万字符（本批 186,270），一次会话无法承载。新增 `scripts/extract_cues.py` 生成 `work/batch_010_cues.txt`（"ordinal|REASON"紧凑视图：≤400 字符整行原文；>400 字符做句子级**原文连续**摘录、单句截断 320 字符并标 `[...]`）。标注仍逐行人工判定；2 行（05524、05543）摘录不足以判定，另从源 CSV 取全文补看。key_quote 只取单个所示句子的连续子串，官方 checker 仍 100% 逐字校验。
3. **标注**：600 行由执行 agent 本人逐行标注，输出 `work/batch_010_judge_part1..6.jsonl`（每段 100 行）。口径沿用 schema v1 固化细则：政策/基数/季节性/天气灾害/IPO 募投投产→other；非洲猪瘟≠epidemic_shock（05411→other）；仅复述结果无因果→other+low（如 05435、05003 类 18 行 low）；原文方向与 type 矛盾→sd=-1（如 05425/05483/05534/05538/05539/05544 等利好复述或利好原因对略减）；sd 以 primary_code 方向按细则 2 机械判定（本批 05487 叙述为增长但 primary=cost_up，仍按细则取 +1，留作数据质量信号）。
4. **合并**：`merge_batch10.py` 合并前预检**首轮捕获 6 处失败**：05681/05779/05810 key_quote 超 40 字符（43/46/41），05785/05977 摘录跨标点拼接致非连续子串，05805 全角/半角逗号与原文不符。定点修复 6 行后重跑，预检 **600/600 OK**，产出 `data/features/fcst-reason-struct-full-20260918/batch_010.jsonl`（600 行，UTF-8 无 BOM，行序=row_index 顺序；元信息全部由脚本从 row_index 合入，零手抄）。
5. **官方校验**：`check_batch_full.py --batch 10` **首轮 600/600 OK**（退出码 0，0 失败）。
6. **progress.json 更新**：`quality_stats.py --batch 10` 追加 "10" 批统计（shape 与既有批次一致），batches_completed=[1..10]，rows_completed=6000，updated_at=2026-09-19T03:11:46+08:00，cumulative 按 6000 行重算。批 1–9、row_index.parquet、schema.md、源数据零改动；docs/、configs/、src/ 零修改；未做 git、未联网。

## 3. 校验结果

| 项目 | 结果 |
|---|---|
| 行数 | 600/600 |
| merge 预检 | 首轮 6 失败 → 定点修复 → 600/600 OK |
| check_batch_full 官方校验 | 首轮 OK（0 失败，退出码 0） |
| key_quote 逐字通过率 | 1.0 |
| 冻结区（ann_date≥20250101） | 0 行 |

## 4. 质量分布（详见 progress.json "10" 批）

- other_rate_primary：0.1517（91 行：政策/基数/油价/贸易摩擦/竞争/募投投产等词表外明示因子 + 18 行 low 兜底）
- secondary_null_rate：0.4767
- supports_direction：+1=580 / 0=9 / -1=11（-1 与 0 为 type 与原因方向矛盾或无因果的数据质量信号）
- confidence：high=582 / low=18
- primary 前列：epidemic_shock=290（本批 2020 上半年疫情冲击占主体，与批 9 的 2019 成本/需求结构衔接合理）、other=91、non_recurring=51、cost_up=48、price_down=42、demand_down=40、impairment=22
- key_quote 长度：mean=22.1 / p50=21 / p90=33 / max=40
- batch_input_chars：186,270

## 5. 产物清单

- `data/features/fcst-reason-struct-full-20260918/batch_010.jsonl`（600 行交付物）
- `data/features/fcst-reason-struct-full-20260918/progress.json`（追加批 10，累计重算）
- 本目录 `scripts/`（render_batch.py、check_batch_full.py、quality_stats.py 原样复制；merge_batch10.py 改参版；extract_cues.py 新增标注辅助）
- `work/`（batch_010_input.txt、batch_010_cues.txt、judge_part1..6.jsonl、part1..6.jsonl 合并中间产物）
- `logs/`（render_batch.log、merge_precheck.log、merge_precheck_r2.log、check_batch_full_r1.log、quality_stats.log）

## 6. 未完成内容

- **batch_011（ord 6000–6599，batch_id=11）未开始**：本轮 600 行标注已耗尽上下文预算，按"宁可少而全对"在 010 全部校验通过后干净收尾。下一波起点：batch_id=11、ordinal 基 6000；复用本目录脚本即可（merge_batch10.py 再改参为 batch=11/基 6000，extract_cues.py 传 `--batch 11`），流程与本批完全相同。建议下一波同样按 6×100 分段标注、以 cues 视图控制预算。
- 未连接网络、未重拉数据（源身份以 data/_meta/sha256.tsv 既有基线为准）。
