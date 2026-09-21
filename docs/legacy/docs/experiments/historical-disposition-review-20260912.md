# B05/B06 历史处置与首轮复测裁决

本次只读历史结果，不新增因子计算。全248单元的公式、原方向、窗口、旧/修正批和逐项分类在 `artifacts/historical-disposition-20260912-1/r0-disposition.json`，来源和 SHA 绑定。信号缺值不算亏损，旧门槛不算统计通过。

| 候选/组 | 原结论证据 | 已知问题与当前处置 | 本轮新增复测 |
|---|---|---|---|
| R0 全248单元 | repair2-research-diagnosis.json；r0-repair2-research-diagnosis-20260912.md | PRICE/IPO问题已修复且原方向重跑；不再重复整个批次 | 0 |
| META_flowlhb_08/09/10/13、07 | 同上 | 无有效月或稀疏截面；改事件语义属新假设，未修复为可评估输入 | 0 |
| 16个 industry_ret_l1 不完整单元 | 同上 | 实际行业代理缺日，历史归属不足；分钟源不解决覆盖 | 0 |
| IM_open_pos_20、IM_gap_turn_coupling_20、ACCDIST_down_absorb_20 | r1-existing-three-review-20260912.md，原负/负/正方向 | 原方向不支持或年度不一致；35月数值已独立复算，无新实现反例 | 0 |
| LIQ_turn_term_slope、LIQ_disagree_turn、TURN_cv_20 | r1-turnover-three-review-20260912.md，均原负方向 | 年度不稳/原方向负；不因分钟源变更翻案 | 0 |
| IM_open_prevrange_pos_20 | r0-repair2-research-diagnosis-20260912.md | DELTA语义错误已隔离；没有既有完成有效成本结论可原式重跑，修公式须新身份 | 0 |
| F4/F18 | financial-mechanism-cost-pilot-review-20260912.md，负/正方向 | 送转整股已修复且6路径已重跑；F4成本后负，F18集中98.47% | 0 |
| F1/F20/F26/F27/F30 | financial-seven-train-review-20260912.md | 已做信号、未做该组成本；不记策略失败 | 0 |
| PV1原十分位、PV1_TOP10_TRAIN_V1 | pv1-capital-feasibility-review-20260912.md；pv1-small-portfolio-cost-review-20260912.md | 原结构整手不可行；新Top10成本后负。无未修复撮合反例 | 0 |
| META_combo_02/10bps | r0-mechanism-cost-pilot-review-20260912.md | 持有603879送转/除权条款问题未解决，收益不可报告；源切换不能解决公司行为 | 0 |
| META_pxval_10、REL_cond_13、REV_vola_14、VAL_R0_004_pe_tsrank | 同上 | 集中/增量不足；ST误禁卖已修复重跑。未发现日线触价反例足以新增分钟复测 | 0 |
| REV11、固定50%组合、低换手 | 当前新计划B02/B04 | 已进入冻结三账户迁移；不重复列为新增候选 | 0 |
| MR/事件/P3/P4历史家族及R1其余资产 | 原计划/研究报告保留 | 本次未逐项重新审核，不宣称全部失败/全部修复；没有具体提名，不恢复短线全研究 | 0 |

主审：首轮额外历史复测清单冻结为空，预算0（允许上限5并不要求凑数），B06以“无有据提名”收口。价格源变化不足以解释信号弱/年度不稳/集中问题。新增修复证据出现时另记修订及预算，不能滚动试到盈利。

统计UNKNOWN、晋级BLOCK保持。此处不把248、215、财务26+5加成独立搜索数。下一步依三账户实际迁移和压力结果形成B07；B08仅在候选不足且有明确新机制预登记时启动。
