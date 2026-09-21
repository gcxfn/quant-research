# F3R4 预登记：归因事件信息并入 F3 组合——"impairment 加分 / price_up 压制"三臂

- 实验 ID：exp-20260920-factor-round-f3r4（本文件 + `configs/experiments/f3r4-reason-integration.json`，2026-09-20 冻结）
- 上游：T1 事件研究 exp-20260920-t1-reason-event（H1 成立：impairment +3.8% 三年全正非单票、price_up −2.7% 三年全负但集中度 27.8%；epidemic_shock 全 2020 单年不采用）；用户批准（2026-09-20 对话："批准"）
- 引擎：band_engine v1.4.1 pin `a01cb29c…75abf3`，非 zones 路径（v1.3 语义），零改动预期
- 试验计账：策略线 293→**296**（3 实验臂；A0 锚不计，沿 F4R1 §7 惯例）

## 1. 背景与可证伪假设

- 背景：事件研究证实归因在 type 外有信息（p=7.1e-05），但效应量小（η²=0.006）且事件稀疏（dev 内池过滤后 impairment 424 个）。本实验回答"这点信息在组合层面能否提取出可测改进"。
- **诚实降级声明（前置）**：事件研究已消费 dev 数据，本实验对同一段样本二次使用——任何"改进"均为**探索级**，不得称验证；样本外结论须 val（冻结）。
- **H1（探索性）**：至少一臂净 CAGR ≥ 基线 +0.30pp 且 maxDD 恶化 ≤1.0pp → 归因信息有组合级可提取改进，值得后续（val 申请或结构化设计）。
- **H0**：三臂改进全部 <0.30pp（或回撤恶化超限）→ 事件级显著但组合级不可提取（稀疏交集稀释），归因线在 F3 管道内关闭，结论归档。
- H0 是可接受结局且先验概率不低（η² 小、K=10 月频选股与事件交集稀少），无凑改进动机。

## 2. 三臂定义（全部在 composite parquet 层实现，runner 零改动）

共用：F3R3-EW 静态路径逐字（R3-06 底盘债15+金25、K=10、行业≤2、top-2K=20、缓冲续持、50 万、w_T≡0.06、dev 2015-01-05..2020-12-31、引擎 v1.3 语义）；composite 输入换为各臂预生成 parquet（列 symbol/signal_date/value，与 F3-EW_composite.parquet 同构），sleeve/引擎/底盘代码零改动。

事件标记（共用）：signal_date ≥ ann_date 且 trading_days_between(ann_date, signal_date) ∈ [0, 60]（共享库交易日历；T+0 当日收盘后可见）；事件集 = 事件研究 run 的 `events_dev.parquet`（身份 pin；去重+池过滤+剔不确定后的 6,664 事件；2015-01..2018-08 信号月无事件，标记恒空=退化基线，披露）。多事件同股同月：impairment 与 price_up 冲突时按"后公告优先"（ann_date 最大者定性）；同类多次取最近。

| 臂 | composite 调整 | 检验什么 |
|---|---|---|
| F3R4-A 加分臂 | `value' = value_ew17 + b×(+1 若 impairment 标记 / −1 若 price_up 标记 / 0)`；b = 1.0 × median_std（见 §3 TF-S3） | 事件作为排名平移（1σ 量级）的直接加分 |
| F3R4-B 压制臂 | price_up 标记股 `value' = −10`（沉底，等价"永不入选"），impairment 不动 | 只去坏（负信号 veto 的 parquet 层等价物；与真 veto 的差异披露） |
| F3R4-C 因子臂 | 18 因子等权：`value' = mean(17 个 z_i, z_event)`，z_event = (rank_pct − 0.5)×(+1)（0/±1 事件列的截面百分位） | 归因作为第 18 因子自然融入现有结构 |

## 3. 参数冻结与来源（无调参空间）

- 回看窗 60 交易日：h=20 显著（事件研究）的 3 倍，信息存续期的保守取整；冻结不扫窗。
- b = median over 68 信号月的 composite_ew17 截面 std（从 `F3-EW_composite.parquet` 机械计算，登记数值与算式；1σ 平移的解释性量级，非优化值）。
- 压制值 −10：composite 值域 ±0.5 外的沉底常数，无信息含量差异。
- C 臂 z_event 的 rank 在全池上计算（含无事件股的并列 0 值），与 17 因子同式（rank_pct−0.5、按非空计数归一）。

## 4. 数据身份（全部已存在）

| 项 | 身份 |
|---|---|
| 事件表 | `artifacts/runs/20260920T113527-t1-reason-event-b690/outputs/events_dev.parquet`（sha256 入 manifest；列含 symbol/ann_date/primary_code） |
| composite 基底 | `artifacts/runs/20260919T191524-f3r1-factor-combo-c212/outputs/F3-EW_composite.parquet`（F3R3 逐字输入） |
| 17 因子 z | F2R1 族 outputs 逐月分数 parquet（C 臂重算 18 因子合成用；z 构造沿 F3R1 §4，归因实验已逐位验证过的重建路径可复用） |
| 底盘与引擎 | F3R3 run `20260919T201500-f3r3-industry-cap-4b2e` 的 runner（派生只换 composite 输入路径）；引擎 v1.4.1 pin |
| 锚 | leave-zero-out：原 F3-EW_composite 输入重跑，五帧与 F3R3-EW 产物逐字节一致 + net_cagr 相等（执行前置门槛；存量审计 run 已实证一次，本 run 重验） |

## 5. 冻结判定线

1. 主判定（§1 H1 线）：净 CAGR ≥ 基线（F3R3-EW +4.88%，manifest 实测值 0.048773…）+0.003 且 max_drawdown ≥ 基线 −1.0pp（即恶化 ≤1.0pp）→ 该臂过线；任一臂过线 → H1；三臂全不过 → H0。
2. 次报告（不判定）：八门指标照常输出（门 3 优势年、门 4、门 5 换手、门 6 权重、门 8 v3 口径沿 F3R3），事件标记的实际入选变化统计（各臂 vs 基线持仓差异月数、impairment/price_up 股实际进出的次数与贡献）——回答"调整到底动了哪些座位"。
3. 边缘案例（恰在 ±0.30pp/±1.0pp 线上 1e-4 内）→ 停机呈主对话。
4. 敏感性（不改变判定，披露）：回看窗 20/40 交易日两档重跑 A 臂（信息存续期稳健性）。

## 6. 运行与预算

- run 目录 `artifacts/runs/<TS>-f3r4-reason-int-<4hex>/`；composite 预生成脚本 + 派生 runner（仅换输入路径与臂标签）入 scripts/；manifest 全身份。
- 预算：锚+3 臂全期回测参考 F3R3 单臂 ~60s，合计墙钟 ≤45min、RSS ≤8GB；无 RNG。
- 敏感性 2 次重跑（A 臂 20/40 窗）+预算内。

## 7. 接缝预裁定

- **TF-S1（parquet 层等价性）**：B 臂压分法与真 veto 的差异（候选全部被压时仍可能入选）在结果文档披露；预期触发概率≈0（候选池数百股）。
- **TF-S2（runner 派生纪律）**：派生 runner 对 F3R3 原版只允许改动 composite 输入路径与产物名前缀，diff 呈 manifest；任何 sleeve/底盘/引擎语义改动 → 停机呈报。
- **TF-S3（b 与 z_event 算式）**：登记中间量（median_std 数值、每月 z_event 分布），供验收复算。
- **TF-S4（事件冲突规则）**：§2 冻结规则机械执行；冲突案例计数披露。

## 8. 停止规则

- leave-zero-out 锚不齐 → 停。
- composite 预生成后与基底的可逆性检查失败（无标记月的 value 与基底逐位一致）→ 停。
- 三臂运行超预算或引擎 sha 漂移 → 停。
- val/冻结区触碰（事件表断言 max(ann_date)≤2020-12-31 + 收益面板截断）→ 立即停。
- H0 成立 → 归档收官（合法结局）；H1 成立 → 结果标注探索级，后续动作（val 申请等）呈用户。

## 9. 勘误（2026-09-20 追加，冻结正文零改动）

§3 "b = median over 68 信号月"系笔误：composite parquet 实为 **71 个信号月**（2015-01-30..2020-11-30，F3R3 口径）；68 为归因 run 的前向收益覆盖期数。实施取 71 月中位数（b=0.10164738676824621），并加跑 68 月变体（b=0.10152821356398378）验证：两 b 值下 A 臂产物与指标**逐位相同**，歧义对判定零影响。本勘误仅修正计数描述，未改任何冻结参数或判定线。
