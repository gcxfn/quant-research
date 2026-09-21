# P3R1 引擎双签放行记录

- 2026-09-18 初审：REJECT（F1 CRITICAL 公司行动接线 / F2 MAJOR 锚点），报告 artifacts/runs/20260918T125211-p3r1-engine-ea06/review/report.md
- 2026-09-18 返工：本目录 20260918T140610-p3r1-engine-fix-e850（13/13 测试，6 项哈希 pin）
- 2026-09-18 增量复审：**APPROVE**，报告 review-delta/report.md（17/17 哈希含旧档案未动验证、22/22 增量对抗、600000 真实权益恒等式精确、50 只抽样事件数对账 mismatch=0）
- 主对话复验：13/13 本机重跑、pin 逐项核对、主循环公司行动段走查（三签）
- 放行范围：P3R1 八配置 dev（2015–2020）重裁定；val（2021–2024）不在本放行内，须 dev 全过后另批
- 附带条件（转 adjudication runner）：① 接线层断言 splits 仅含股票池标的（split_factor.h5 有 19 行 ETF 份额折算 <1.0，零股票但须结构性排除）；② 报告披露 stk_limit 缺行市价兜底触发次数（RULINGS #2 义务）
