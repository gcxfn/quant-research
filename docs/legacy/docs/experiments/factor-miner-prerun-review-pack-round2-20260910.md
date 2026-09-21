# factor-miner 引擎 Codex 运行前审核送审包 第 2 轮（2026-09-10）

审核性质：运行前代码审核第 2 轮。第 1 轮 4 项 P1 全部处置：P1-2/3/4 本轮结构修复+主对话对抗复验；P1-1（真实数据执行路径）第二阶段交付+主对话复验。`REAL_RUN_UNLOCKED` 保持 False（R0 解锁仍待本轮 PASS）。第 1 轮包：`factor-miner-prerun-review-pack-20260910.md`。
全仓基线：848 项（factor_miner 全套 143 OK；唯一失败为并行在途的 test_pv1_precision_test，属 PV1 精测代理半成品，与引擎无关，其闭合另行送审）。

## 一、第 1 轮 P1 处置清单

| P1 | 处置 | 主对话复验 |
|---|---|---|
| P1-2 哈希碰撞 | 窗口归一化改按出现顺序分配 N1/N2…（同值窗口共用占位符）；合并保存 merged_lineage（每来源 id/原始 formula/window_params/holding_days） | Codex 原例异哈希✓、RET7vs8 同哈希✓、谱系留痕✓ |
| P1-3 分区 | train_only_window 起点<2020-01-01 拒；check_window 完整包含单一区域（跨区拒）；warmup_read 显式通道（≤365 日历日、warmup_only 标记+ensure_not_warmup 守卫、LOCKBOX 预热需授权） | 2010 起点/跨区/预热越界/锁箱预热 四拒✓、守卫✓ |
| P1-4 锁箱 | run_lockbox(out_dir, manifest, registry)：清单↔registry 双向一致（含 FROZEN 全集不得漏报）、canonical-JSON sha256 台账一次性消费、out_dir 已存在拒 | 首跑+台账✓、二次消费拒✓、目录已存在拒✓、哈希不符拒✓（第二阶段 director 大改后复验仍全过） |
| P1-1 真实路径 | 第二阶段交付（见 §二） | 见 §三 |

lhb 处置：PIT_SAFE 曾整体移除（fail-closed）；第二阶段交付 t+1 对齐 loader+三层反例测试后**已恢复**（t 日榜值 t 日不可见/t+1 可见/窗口右界丢弃）。

## 二、第二阶段交付（P1-1）

| 模块 | 行数 | 内容 |
|---|---|---|
| data_fields.py（扩） | 190→394 | 真实 loader：daily_basic（t 对齐）、margin（rzye/rzche/rqmcl 映射）、**lhb（上榜日 t→t+1 强制对齐）**、industry_ret_l1（SW L1 等权单序列）；逐日 chunk 流式、经 train_only_window 收口 |
| engine.py | 228 | build_real_bundle（P1 池日线+真实字段+派生 STATE：market_ret/market_vol/adv_dec_ratio/limit_up_count）→ evaluate_plan → 月末 RankIC 序列 |
| backtest.py | 193 | 17/27/37bps 冻结档（随换手双边扣）、T+1 次日开盘、涨跌停（raw 价、一字 no_trade）、跌停卖出顺延≤20 会话超限 MTM、net_edge/turnover/top1_contribution_share |
| event_stats.py | 184 | 声明式事件过滤（match 等值+ann_date 收口）→ SimpleAxis（pool_ok 缺省全 False fail-closed）→ 复用 event_family 冻结统计（块20/B=10000/种子20260909） |
| director.py（扩） | 437→739 | validation_family_gate（§5 六条件+死亡标签自动映射）、corr_cluster（并查集）、budget_multiplier、apply_validation_results、dev-smoke-train CLI |

dev-smoke 端到端（真实 TRAIN 日线，两轮）：`artifacts/factor-miner/dev-smoke/20260910_082210`、`_082248`——run_meta 含 mode=DEV_SMOKE、real_run_unlocked=false、window=TRAIN、六源 data_version 谱系；registry 自动打标示例（DEAD/WRONG_DIRECTION、DEAD/NO_SIGNAL）与 17/27/37 净边际逐档落盘均验证。

新增测试 20 项（lhb PIT 反例三层、bundle 集成、成本/涨跌停/top1、聚类正反例、预算分支、门禁逐条反例、事件 fail-closed）；第二阶段+结构修复合计 factor_miner 143 项。

## 三、主对话复验记录（2026-09-10）

结构修复 14 项对抗验证（第 1 轮包§三同口径）+ 第二阶段：53 项定向测试复跑✓、锁箱三路拒绝在 director 大改后复验✓、dev-smoke 留痕与 data_version 检查✓、lhb 对齐 4 项测试+PIT_SAFE 恢复+R3 放行实测✓。

## 四、待裁决解释性读法（16 条：结构修复 6 + 第二阶段 10）

结构修复：
1. warmup 边界单位=日历日（上限 365≈252 交易日保守换算）；交易日精确计数留 loader 层。
2. warmup_only 以返回结构标记+ensure_not_warmup 守卫实现"不用于统计/标签"；是否要求 loader 行级再嵌标记请裁决。
3. 锁箱双向一致（registry 全部 FROZEN 必须出现在清单，防漏报）——严于任务书原文。
4. 清单哈希=解析后 canonical JSON sha256（空白/键序无关）。
5. 等窗不同窗宽同哈希合并（MEAN(20)-MEAN(20)≡MEAN(60)-MEAN(60)）——符合"合并为 holding_days 扫描"语义。
6. check_window 返回值改单区域名字符串（仓库内无外部调用方）。

第二阶段：
7. 相关性阈值 0.7（|Spearman|≥0.7 聚簇，反向高相关共享信息源不算独立证据；有效对<30 不相关）。
8. 聚类输入=TRAIN 月末截面 (month,symbol) 交集成对秩相关；簇 id=字典序最小成员。
9. 预算公式：同向一致 share≥0.60→×3、≥0.30→×2、=0→×0.5、其余×1。
10. industry_ret_l1=SW L1 全行业日收益等权单序列广播（不做个股行业映射——index_member_all 时点缺口，与预登记 EXPLORATORY_ONLY 政策一致）。
11. market_ret=bundle 内可交易池等权（全市场口径须显式全池注入）。
12. margin 映射：margin_buy=rzche（元）、margin_sell=rqmcl（**融券卖出量·股**，与买入侧单位不同——只可秩类/比值构造，如实披露）。
13. inst_net_buy=top_inst 席位明细按 (trade_date,ts_code) 求和；lhb_net_buy=top_list net_amount。
14. lhb 对齐用市场日轴=窗口内实际 chunk 日期；缺日=数据缺口丢弃不后移（宁缺勿错移）。
15. backtest 基准=全池等权同窗毛收益；门禁②"分年同号"=月 IC 按年聚合符号。
16. event_stats 的 SimpleAxis 未接 P1 全池掩码时 pool_ok 全 False（一切 no_trade），正式轮须显式注入掩码——事件路径正式可用前的强制项，请确认是否作为 R0 前置。

## 五、建议审核重点

1. lhb t+1 对齐 loader（PIT 关键路径，三层反例已配，请独立构造反例复核）。
2. validation_family_gate 六条件与死亡标签映射的完备性（有无漏判路径）。
3. backtest 成本/涨跌停/顺延与 mr_statarb·P2 执行引擎口径的一致性。
4. 预算公式与聚类实现相对预登记 §6/§7 文字的忠实度（读法 7–9）。
5. dev-smoke 与正式运行的代码路径隔离（mode 标记+train_only_window）是否足以防误用。

## 六、解锁预告

本轮 PASS 后：主对话显式翻转 REAL_RUN_UNLOCKED（提交留痕）→ 派 R0（REV/REL/STATE+META，researcher_v1.md 任务书，TRAIN-only）；R0 工件回归本审核通道（抽审）。
