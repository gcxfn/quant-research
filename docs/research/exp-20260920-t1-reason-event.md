# exp-20260920-t1-reason-event：T1 业绩预告归因的事件研究（结果）

- 预登记：[exp-20260920-t1-reason-event-prereg.md](exp-20260920-t1-reason-event-prereg.md)（2026-09-20 冻结，逐字执行）
- 运行：`artifacts/runs/20260920T113527-t1-reason-event-b690/`（scripts / outputs / logs / manifest，status=completed）
- 上游：T1 数据集 `data/features/fcst-reason-struct-full-20260918/`（65 批 38,567 行）

## 结果一句话

**控制 type 与公告月后，primary_code 归因类别对公告后 20 日收益仍有统计显著的区分度（ANOVA F=3.343，p=7.13e-05 < 0.05 → H1 成立），方向由 impairment（正）、epidemic_shock（负）、price_up（负）驱动；四种敏感性全维持 H1，不脆弱——按预登记 §5.1，下一轮设计归因因子进 F3 管道须另行预登记。**

## 事件表规模与池过滤漏斗

连接断言全过：65 个 jsonl 合计 38,567 行、连接键（ts_code+end_date+ann_date+update_flag）双侧无重复、与 row_index 1:1 全匹配、struct_version 全部 llm-v1。

| 步骤 | 事件数 | 说明 |
|---|---|---|
| 合并全量 | 38,567 | ann_date 2018-09-04..2024-12-31 |
| dev 窗（≤2020-12-31） | 17,582 | 其余 20,985 行（val/冻结区）零接触 |
| §2 去重 (ts_code, end_date) | 16,202 | 取 ann_date 最大、同日 update_flag 最大，剔被取代公告 1,380 |
| 剔除 type=不确定 | 15,803 | 399 行（计数披露） |
| 板块排除（board_ok_expr） | −6,426 | 仅 sh.60*/sz.00* 主板；含 28 行无法转换的 ts_code（非 SZ/SH 后缀） |
| 事件日可交易 | −2,098 | 当日无该股 traded 行；其中公告日非市场交易日 1,843、交易日内停牌 255 |
| 上市≥60 交易日 | −24 | listing_index≥60（own-session 计数，含事件日） |
| 非 ST（事件日 isST=0） | −591 | |
| **池过滤后** | **6,664** | 门槛：总数≥5,000 ✓；进检验 type 各≥100 ✓ |
| 缺 h=20 前向窗 | −8 | 公告后 20 个自身交易日内退市/长停 |
| **分析样本** | **6,656** | 27 个公告月；primary_code 无缺失 |

池过滤后 type 计数：预增 2,070 / 首亏 1,229 / 预减 1,119 / 续亏 513 / 略增 644 / 扭亏 537 / 略减 384 / 续盈 168。

### 口径实现披露（预登记 §7 接缝）

- 池资格为预登记 §2 四条件的事件日口径（上市≥60 交易日、非 ST、板块排除、事件日可交易），实现复用 R16 共享库（`market_calendar` / `build_history_r16` / `board_ok_expr`），未含月频 top-K 席位与流动性排序（预登记四条件未列流动性项）。
- 前向收益与 F2R1 eval harness 同式自写：close/preclose 复利链、T+1 起、h=20、链行宇宙=tradestatus==1 且 isST==0（harness 同式；事件日资格由池四条件另行保证）。h=20 为自身交易日窗：多数事件窗口右端自然溢出到 2021-01-2x（允许的价格数据使用），长期停牌股 42 事件（0.6%）日历跨度更长、极端至 2024-09-10（sh.600666 多年重组停牌），均为冻结口径内结果，manifest 量化披露。
- **TE-S2 通过**：抽 3 股（sh.600008 / sz.002104 / sz.002973）× 3 事件，自写实现 vs harness 网格 max|diff|=0.0（容差 1e-9）；且分析样本全部 6,655 个可对照键（1 键因 harness min_history_rows=60 的 universe 截断缺失）全局 max|diff|=0.0。
- val 2021-2024 与冻结区 2025+ 零接触：合并后 / 池过滤后 / 各变体样本三处断言 max(ann_date)≤2020-12-31 全过。

## 基准层 sanity（type 8 类，只验证不判定）

月份调整后 h=20 漂移：**预增 −0.43% vs 预亏组（首亏+续亏，操作化披露）+0.38%——方向与文献共识相反（sanity direction_ok=false），原样呈报不做判定**；原始漂移同向（+3.93% vs +4.70%）。原始漂移全表见 `outputs/type_drift.csv`（续盈 +9.24% 最高、预增 +3.93% 最低，type 层面无文献式单调性）。此反向本身与主检验独立：主判定检验的是 type 之外的 primary 增量。

## 主判定（预登记 §4/§5 冻结口径）

月份固定效应（减同公告月全体事件均值）→ type 组内去均值 → primary_code 类别间单因素 ANOVA（dev 内 n≥100 的类别保留，不足并入 other）：

- 组：13 组（core_ops 358 / cost_down 199 / cost_up 305 / demand_down 568 / demand_up 1,555 / epidemic_shock 1,178 / impairment 424 / ma_restructuring 255 / non_recurring 813 / orders 143 / price_down 241 / price_up 204 / other 413；accounting、fx 并入 other 并披露）
- **F=3.3426，df=(12, 6643)，p=7.134e-05 < 0.05 → H1 成立**；效应量 η²=0.0060（如实记录：统计显著但方差解释占比小）

## 类别级报告（Welch t：类别 vs 其余，BH 校正，仅报告不单独判定）

| 类别 | n | 组内去均值收益均值差 | t | p | p (BH) | BH 后 |
|---|---|---|---|---|---|---|
| epidemic_shock | 1,178 | −1.76% | −4.03 | 5.9e-05 | **7.1e-04** | 显著（负） |
| impairment | 424 | +3.81% | +3.65 | 2.9e-04 | **1.7e-03** | 显著（正） |
| price_up | 204 | −2.73% | −2.55 | 0.0116 | **0.046** | 显著（负） |
| demand_up | 1,555 | +0.61% | +1.35 | 0.178 | 0.534 | 不显著 |
| price_down | 241 | +0.68% | +0.74 | 0.462 | 0.906 | 不显著 |
| demand_down | 568 | −0.64% | −0.94 | 0.345 | 0.829 | 不显著 |
| 其余 6 类 | | | \|t\|≤0.36 | | ≥0.90 | 不显著 |

- other 桶（含并入小类）不进两两比较（残差混合体，实现披露）；ANOVA 组间检验含 other 组。
- **epidemic_shock 全部 1,178 事件集中在 2020 年**（词表语义使然），其负漂移是单一年份现象，解读归用户。

## 敏感性三件（预登记 §5.2，不改变主判定）

| 变体 | n | F | p | 判定 |
|---|---|---|---|---|
| S1 剔除 sd=−1 与 low 行 | 6,360 | 3.449 | 4.40e-05 | H1（不变） |
| S2 h=5 短窗 | 6,656 | 2.259 | 7.55e-03 | H1（不变） |
| S2 h=10 短窗 | 6,656 | 2.370 | 4.83e-03 | H1（不变） |
| S3 不去重原始样本 | 7,423 | 4.129 | 1.77e-06 | H1（不变） |

主判定为 H1 而任一敏感性不再成立才记"脆弱"（操作化披露）：**无一翻转，不脆弱**。

## 分年方向一致性与集中度（描述性）

- 分年（2018 9-12 月 / 2019 / 2020 月份调整收益，方向一致段数）：impairment **3/3 为正**（+2.2% / +6.5% / +1.3%）；price_up **3/3 为负**（−7.1% / −3.3% / −0.6%）；epidemic_shock 仅 2020 有事件（−1.2%）；demand_up 不一致（−1.1% / −2.4% / +2.9%）；其余类别多为 1/3。
- 类别内 top1 股票收益贡献占比（防单票驱动）：impairment 2.7%、epidemic_shock 收益合计为负（占比不定义）、demand_up 2.8%——显著类别非单票驱动；price_up 27.8%（top 股 sz.002458）、cost_down 15.7%、ma_restructuring 12.3% 有集中度，解读须打折。

## §5 判定结论

- **主判定 p=7.134e-05 < 0.05 → H1 成立**（判定线逐字执行；输出 `outputs/anova_main.json`）。
- 按预登记 §5.1：下一轮设计归因因子进 F3 管道须另行预登记；η²=0.006、epidemic_shock 单年份结构、price_up 集中度等限制如实带入设计。
- 试验计账：因子线 FT-02（事件研究 1 项试验，敏感性不另计），因子线 120→121。

## 运行身份

- run：`artifacts/runs/20260920T113527-t1-reason-event-b690`，status=completed，无 RNG 全确定性
- 环境：Python 3.11.15 / polars 1.44.2 / numpy 1.26.4 / scipy 1.17.1 / Windows；墙钟 8.2s（上限 1h）、峰值 RSS 5.93GB（上限 8GB）
- 身份 pin（manifest.json）：预登记、row_index、65 批 jsonl 清单（tmp/t1_batch_sha256.txt）、合并标注 parquet、两个日线面板、p2r13/p2r16/eval 共享库与本脚本 sha256
- 产物：`outputs/`（events_dev.parquet、type_drift.csv、primary_within_type.csv、anova_main.json、sensitivity.csv、pool_filter_counts.json、category_diagnostics.csv）
- 开发期停机记录：TE-S2 抽样机械规则两次停机（字典序首/尾股可对照事件 <3），抽样改为"可对照事件 ≥3 的股票集合取首/中/尾"后完成；全局对照在首次运行即为 max|diff|=0，判定数字不受影响
