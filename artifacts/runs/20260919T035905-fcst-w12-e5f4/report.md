# w12 运行报告：fcst-reason-struct batch_012（第 6,601–7,200 行）

- run_id: 20260919T035905-fcst-w12-e5f4
- 状态: completed（batch_012 官方校验 600/600 OK，progress.json 已更新）
- 上游: 沿用 w11 目录（20260919T031423-fcst-w11-9b30）脚本与 schema v1（llm-v1），未改动 w11 任何文件

## 实际改动
- 本运行目录新建：`scripts/`（extract_cues.py、check_batch_full.py、quality_stats.py 原样复制；merge_batch12.py 由 merge_batch11.py 复制改参 batch=12、ordinal 基 6600）、`work/`（cues 视图、judge_part1..6、part1..6 中间产物）、本报告。
- 特征集写入：`data/features/fcst-reason-struct-full-20260918/batch_012.jsonl`（600 行）与 `progress.json`（新增 "12" 批条目、batches_completed 1..12、rows_completed=7200、cumulative 重算）。
- 未改动：既有批次文件、row_index.parquet、schema.md、源数据、docs、configs、src。

## 输入与标注口径
- extract_cues.py --batch 12 渲染紧凑视图：600 行、长文（>400 字符）句子级摘录 51 行、文件字符数 95,718（与批 10/11 口径一致，记录于 progress.json batch_input_chars）。
- 本批 type 分布（row_index 程序确认）：ordinal 06600–06789 为 略减（190 行），06790–07199 为 略增（410 行）；冻结区断言 ann_date≥20250101 = 0 行。
- 逐行标注 primary/secondary/supports_direction/key_quote/confidence，遵循 schema v1 固化细则（政策/基数/季节性/来水等→other；仅复述结果→other+low；原文方向与 type 矛盾→sd=-1）。

## 校验与 fix_loop
1. merge_batch12.py 合并前预检首轮捕获 2 处失败：
   - 06750 key_quote 误引同批 06775 的"煤炭平均销售价格下降"文本（300763.SZ 原文实为光伏和储能逆变器接单向好、净利润同比上升，与 type 略减矛盾，改为 primary=demand_up、sd=-1）；
   - 07028 key_quote 误引同批 07078 的"国家自主创新产业政策驱动"文本（002883.SZ 原文实为工程咨询行业形势向好 + 股权激励费用摊销）。
   定点修复 part2/part5 后预检 600/600 OK（引文逐字、词表闭合、secondary≠primary、冻结区通过）。
2. check_batch_full.py 官方校验：首轮 600/600 OK。
3. 交付后复核：batch_012.jsonl 主键全局唯一、与 row_index 键集合一致、struct_version 全为 llm-v1。

## 批次质量摘要（详见 progress.json）
- other_rate_primary 0.0633；secondary_null_rate 0.5783；confidence high/low = 581/19。
- supports_direction：+1 570 / 0 17 / -1 13（-1 均为原文方向与 type 矛盾的数据质量信号，如 06663/06676 型"原因利好 vs type 略减"及 06720/06750/06764/06773、06696 型"原因利空 vs type 略增"）。
- primary 主要代码：demand_up 为主（本批 2018–2019 及 2023–2024 增长样本占比较高），price_down、cost_up、non_recurring、ma_restructuring 次之。

## 未完成内容
- batch_013（第 7,201 行起）未开始；上下文预算考虑，本轮 012 通过后干净收尾。
