# wave-24 交付说明（batch_024，ordinal 13800–14399）

- 完成时间：2026-09-19T16:23+08:00
- 交付物：`data/features/fcst-reason-struct-full-20260918/batch_024.jsonl`（600/600 行，struct_version=llm-v1）；`progress.json` 的 batch "24" 条目已更新，`batches_completed` 现为 1–24，`rows_completed`=14400（全池收口）。

## 本代理（收尾代理）实际完成

1. **part6 补判**：`work/batch_024_judge_part6.jsonl`，ordinal 14300–14399 共 100 行，为本代理唯一新判定范围。判定依据 `work/batch_024_cues.txt` 第 501–600 行；其中 14376 在 cues 中被截断（[...]），已回读原始 CSV 全文（存档 `work/w24_14376_full.txt`）后定码。type 程序化核验为本批 600 行全部 `续亏`（恶化组），supports_direction 沿批内既定口径：利空向原因 +1、利好向原因 −1、中性/季节性/基数 0。part1–5 的判定一概未重判。
2. **merge 预检修复循环（第 1 轮即通过）**：`merge_batch24.py` 首轮捕获 part1–5 遗留 4 处 key_quote 非逐字（前一代理死于合并步骤之前，故未暴露）。按"只修失败行、不改码不改脚本不改数据"处理，修复指纹：
   - 13920（part2）：原引文不在原文，改为 `多项在研品种新推进至临床研究阶段导致公司研发费用金额较高`（primary cost_up 不变）；
   - 13936（part2）：语序与原文不符，改为 `2021年公司芯片产品销售收入快速增长`（primary demand_up 不变）；
   - 13937（part2）：全角逗号改回原文半角，`销售价格大幅下调,导致公司营业收入规模同比下降`（primary price_down 不变）;
   - 14018（part3）：去掉原文中不存在的前缀"公司"，改为 `产品销量等同比有所增长`（primary demand_up 不变）。
3. **校验结果**：merge 预检 600/600 OK（ordinal 连续、词表闭合、secondary≠primary、冻结区清白、key_quote 反向逐字）；`check_batch_full.py --batch 24` 600/600 OK（三道全过）。quote_verbatim_pass_rate=1.0，fix 共 4 行、1 轮。
4. **统计**：`quality_stats.py` 已写入 batch 24 条目（other_rate_primary=0.065，secondary_null_rate=0.3133，confidence high=590/low=10，key_quote len mean=20.4 / max=39）。

## 遗留披露

- part1–5 的 4 处 quote 修复系机械性逐字对齐，未触碰任何 primary/secondary/supports_direction/confidence 判断；其语义判定质量仍以前一代理产出为准，本代理仅做反幻觉层修复。
- part6 中 14326 原文无因果陈述（纯业务描述），按 schema 落 other + confidence=low + supports_direction=0；该行属数据工程产出，不入研究判据。
- 判定性边界（同批一致口径）：竞争加剧→demand_down、集采/季节性/行业政策→other(high)、预重整/出表并表→ma_restructuring（按原文极性定 sd）、续亏+改善向原因→sd=-1（数据质量信号）。
