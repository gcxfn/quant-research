# 家族批量粗筛轮 ⑤ 财务家族附录草案（2026-09-10）

状态：**草案待用户批准**。基础协议完全继承 `family-batch-screening-preregistration-draft-20260910.md` §2/§3（本附录为其 §1 预留的"⑤财务家族待数据抽审后另行附录补充"）。
前提：statements 第三批数据主对话抽审 PASS（`docs/experiments/tushare-third-pull-20260910.md`，2026-09-10），四条取数契约**原文冻结**于本附录 §2.2。

## 1. 构造清单（事前冻结，本轮 N=5；因子型·月频慢因子）

| id | 构造 | 公式（事前冻结） | 经济先验（方向） |
|---|---|---|---|
| F1 | 账面市值比（价值） | B/P = 归母净资产（balancesheet `total_hldr_eqy_exc_min_int`）÷ 月末总市值（daily_basic `total_mv`，PIT=月末当日最近可得） | 便宜（高 B/P）修复空间大（+） |
| F2 | 盈利能力（质量） | ROE = fina_indicator `roe`（as-reported 加权，见 §2.2 对齐） | 高盈利持续（+） |
| F3 | 营收增长（成长） | `or_yoy`（tushare 口径营收同比，as-reported） | 成长溢价（+） |
| F4 | 应计（盈利质量） | (净利润 `n_income` − 经营现金流 `n_cashflow_act`) ÷ `total_assets`，三表**同一报告期**（见 §2.2） | 高应计=低质量盈余（−） |
| F5 | 资产扩张（投资异象） | total_assets 同比增速（期末 vs 一年前同报告期，两期均须可得） | 激进资产扩张低估回报（−） |

- 数据：balancesheet/income/cashflow/fina_indicator 20260909-r3 ∪ 20260910-r1 补拉覆盖（读取顺序：r1 非空 chunk 覆盖同 (接口,代码) 的 r3 空块；confirmed_empty 即最终边界）；daily_basic 20260909-r1；价格与 P1 时点池用 mr_statarb 装载器（与 ④ 同源）。
- 不与已封存结论重开：MR/事件/价量轮构造不复用；F1–F5 为总计划 ⑤ 轮明文方向（价值/质量/成长）+ 应计/资产扩张两个经典财报异象。

## 2. ⑤ 特有冻结项

### 2.1 对齐与窗口（因子型协议之上）

- 月末截面 t：报表值 = ann_date ≤ t 的披露中，**报告期（end_date）最新**者的 as-reported 值；报告期距 t > 15 个月（约 459 天）→ 视为缺失（陈旧披露不入截面，计数披露）。
- F4 要求 income/cashflow/balancesheet 三接口都存在该报告期行（各自取最早披露行后配对），任一缺失 → 该股该月缺失。
- F5 的"一年前同报告期"= end_date 早整 1 年的同期行（如 1231 对 1231、0630 对 0630）；无同期行 → 缺失。
- 收益与 RankIC：月末 t 因子值 vs t→t+1 月末收益（P1 时点池完整门禁；月块 bootstrap 块长 3、B=10000、种子 20260909，95%CI）；Top-Bottom 十分位毛收益差描述性。
- **金融业排除**：最新报告 comp_type∈{2,3,4,7}（保险/银行/证券/其他金融）的股票从 F1–F5 全部截面剔除（会计口径不可比，约 1.2%，计数披露）。

### 2.2 取数契约（抽审四条，原文冻结，fail-closed）

1. **update_flag 不是披露次序**：同 (ts_code, end_date) 一律取 **ann_date 最早**的行为准；更晚 ann_date 的同期末行仅作重述感知，不入因子值；f_ann_date 不作首披依据。
2. **ann_date < end_date 的行直接剔除**（r3 实测仅 3 行：920185.BJ×2、603400.SH×1）。
3. **fina_indicator 同 (ts_code, end_date, ann_date) 多行**：使用任一字段时该字段非空值必须唯一，冲突 → 该 (股票, 报告期) 该字段缺失（实测冲突组：roe 2,233 / netprofit_margin 976 / debt_to_assets 860 / eps 535 / gross_margin 482 / or_yoy 617）。
4. **income/balancesheet/cashflow 去重键** = (ts_code, end_date, ann_date, update_flag)；与第 1 条叠加后仍重复的行（实测 339）整组剔除该 (股票, 报告期)。

### 2.3 数据与工件身份

- 运行前记录：四接口 r3+r1 全部 chunk 的 sha256 清单（含 confirmed_empty 名单）、daily_basic 批次身份、P1 池清单哈希、脚本内容哈希；写入新批次目录（独占，已存在即拒）。
- 工件：逐月 RankIC 序列+截面明细（构造值可得数、缺失原因分类计数：stale>15m / conflict / 三表不齐 / 金融排除 / comp_type 缺失）；选择窗 2020-01-01→2023-12-31，**2024 起零接触**。

## 3. 判据与纪律（继承基础预登记 §2/§3）

- 晋级线（因子型）：|RankIC 均值| ≥0.02 且 95%CI 不含零 且方向与 §1 先验一致。
- 多重检验：本轮 N=5，粗筛层 α=0.10/5；晋级≠有效，仅授权进入精测预登记（净成本+交易结构+留出窗一次性验证）。
- 家族级结论按"代表构造在本口径未过粗筛线"表述，不判死家族；判据层不批量。
- 分工：flash 子代理实现+运行；主对话工件审查；Codex 抽审粗筛口径、全审晋级者精测。

## 4. 批准记录

- 2026-09-10 用户对话批准（"都批准"）——附录冻结，授权派 flash 子代理实现+运行粗筛；主对话工件审查，Codex 抽审口径。
