# F 线 val 批量检验（V2）：端口验证停机呈报

- 实验 ID：exp-20260920-val-batch（V2 = F 线 5 配置）；统管预登记
  `docs/research/exp-20260920-val-batch-prereg.md`（冻结）。
- 运行：`artifacts/runs/20260920T130616-val-batch-fline-6534`；引擎 v1.4.1 pin
  `a01cb29c…75abf3`（运行前后一致，本 run 零改动）。
- **结果一句话**：B1(m) dev/val 与归因事件 dev 三项端口验证全部通过，但 **17 个代表
  因子中有 8 个（D 族 7 个 + E16）的 dev 分数无法逐位复现**——失败根因在冻结的 F2R1
  产物本身：同一份 shipped 脚本、字节级未变的输入，四次运行产出四份互不相同的
  因子帧；按预登记 §6「任一端口验证失败 → 对应配置停机呈报」，**F 线 5 个配置全部
  停机，val 未消费**（一次性资格保留）。

## 一、结论与影响

| 项目 | 结果 |
|---|---|
| B1(m) dev 端口（1e-9 复现 R16 C05 b1m_*） | **PASS**（含 6 个年度） |
| B1(m)(val) 现算（= TL-30 −0.148%/−23.44%） | **PASS**（逐位一致，1e-9） |
| 归因事件 dev 端口（复现 events_dev） | **PASS**（7 产物中 6 个字节一致，events_dev.parquet 仅 parquet 行序不同） |
| 17 代表因子 dev 端口（逐位复现 F2R1） | **FAIL**：8/17 失败（D 族 7 + E16），6/17 字节一致，3/17 数值逐位一致（行序不同） |
| 5 臂 dev 锚（预登记 §5 前置） | 未执行（端口门先触发） |
| val 消费 | **未消费**：无 val 因子分数、无 val composite、无 val 臂运行、无 val 判定 |

因为 17 代表中有 8 个不可逐位复现（D 族 7 个 + E16），而 5 个配置的 composite
全部消费它们，所以 §6 的「对应配置」即 V2 全部 5 个配置。预登记 §4 的
「两 run 独立收官：单线停机不拖累另一线」正是为这种情形预留的条款。

## 二、停机证据：D 族 dev 产物不可复现

对同一份 shipped 脚本 `build_d_fund_main.py`（我的窗口适配版在 dev 模式下与之
逐行等价，见 §四）在**字节级未变的输入**上运行四次：

| 运行 | 触发 | D10 sha256:12 | D10 行数 |
|---|---|---|---|
| frozen_f2r1 | 2026-09-19 18:19 原始产物 | e749803de188 | 288699 |
| rerun_1 | 本 run 第一次重算 | f983dad9c50b | 289101 |
| rerun_2 | 本 run 第二次重算（同参数） | dcf4c396b168 | 289025 |
| rerun_3_threads1 | `POLARS_MAX_THREADS=1` | 68e998efd226 | 289039 |

7 个 D 代表**每一个都四次互不相同**（明细 `outputs/d_family_reproducibility.json`）。
差异不只是行序：键集不同（例：2015-01-30 的 `bj.920078` 只出现在 frozen、
`bj.920010` 只出现在重算），数值也不同（bps 最大差 440，ocf_yoy 达 1.0e7）。

已排除的其他解释：

1. **输入数据变化**：`data/_meta/sha256.tsv`（2026-09-17 深度扫描基线）覆盖的
   23,622 个财务原始文件（fina_indicator / income / balancesheet / cashflow）
   逐个重算 sha256，**0 处不一致**——输入自 F2R1 运行之前至今未变。
2. **线程数**：`POLARS_MAX_THREADS=1` 仍与其余三次不同。
3. **窗口适配引入偏差**：生成的 val 脚本与 shipped 脚本逐行 diff，dev 模式下的替换
   全部语义等价（§四）。
4. **`pit_full` 的重述 tie-break**：定向探针显示
   `sort(ann_date).group_by(ts_code,end_date).last()` 在进程内可重复、且与显式
   排序版本完全一致（差异 0 行），故不是不稳定步骤；不稳定点在
   `build_d_fund_main.py` 的 join / sort / group_by 链中，列为后续工作。

附带的口径发现（同一类问题的静态证据）：合成探针（300k 行 / 3200 组）显示冻结
惯用式 `sort(...).group_by(k).last()` 与显式有序等价式在 **8.4% 的组**上取到不同行，
即该惯用式并未实现其文档化的「tie 取 end_date 大」重述规则；D 族报告自己披露的
「同日多公告 tie-break 差异占 8–9%」正是同一量级。因此 D 族实现依赖 polars
`group_by` 未指定的行序，**其产物在定义上就不可逐位复现**。

## 三、17 代表因子 dev 端口逐项记录

| 因子 | 族 | 判定 | 说明 |
|---|---|---|---|
| A17 / A20 / A25 | A 量价 | 字节一致 | parquet sha256 相同 |
| B11 / B12 | B 估值规模 | 字节一致 | 同上 |
| C19 | C 微观结构 | 字节一致 | 同上 |
| B14 / F06 / F09 | B / F | 数值逐位一致，行序不同 | 键集相同、`max|diff|=0`；排序后 polars `.equals()` 为真 |
| E16 | E 事件 | **FAIL** | 见下 |
| D10 / D13 / D14 / D18 / D19 / D20 / D30 | D 财务 PIT | **FAIL** | 见 §二 |

**E16 专条**：冻结的 `outputs/E_event/E16.parquet` 并非由族脚本产出，而是验收后由
带外修复脚本 `tmp_accept/fix_E16_dupcount.py` 覆盖写入（原版留档
`E16_dupcount_original.*`）。我的适配脚本按该修复脚本的同口径重实现（去重
`unique(subset=["symbol","ex_date","cash_div"]).unique(subset=["symbol","ex_date"],
keep="first")`），复现到 1.15e-4 而**不是逐位**。进一步检查发现根因还是产物不可
复现：该修复的 `unique(keep="first")` 依赖未指定行序；用同一份代码、同一份输入
连跑两次，**24~27 行数值不同**（键集与行数相同，最大差 0.0238，例：
`sh.601088` 2017-07-31 0.153727 vs 0.129917——同一次除息存在两笔不同 `cash_div`，
被 `keep="first"` 任选其一）。因此 E16 判 FAIL，且「差 1.15e-4」只是单次抽样结果。

**归因事件 dev 端口**：7 个产物中 6 个与 T1 run 字节一致（`anova_main.json`、
`type_drift.csv`、`primary_within_type.csv`、`sensitivity.csv`、
`pool_filter_counts.json`、`category_diagnostics.csv`，即 ANOVA p=0.000071、
样量 6,656 等全部统计量逐位相同）；`events_dev.parquet` 仅 parquet 行序不同——
键集与全部列数值逐位一致，按 `ordinal` 排序后 `.equals()` 为真。

## 四、端口验证纪律执行记录

- **先 dev 后 val**：每个阶段都是 dev 端口（或 dev 锚）先跑通才进入 val；val 阶段
  只在 B1(m) 上执行过（预登记 §3 指定的基准现算，TL-30 已公开，不构成配置判定）。
- **只换窗口**：六族因子脚本、事件脚本均由原脚本经「断言唯一命中」的替换生成
  （生成器 `scripts/adapt_factor_scripts.py`、`scripts/adapt_event_script.py`，
  生成物在 `scripts/generated/`）。可选窗口参数只有：窗口端点常量、信号月范围、
  输入分块日期上界、输出目录。dev 模式下每个替换都退化为原表达式。
- **口径零改动**：公式、滚动窗、去重、池过滤、前向收益、判据一字未改。E16 例外
  已在 §三披露并说明理由（不修复则无法复现冻结产物）。
- **身份留档**：原始财务文件 23,622 个 sha256 对账（0 不一致）；引擎 sha 前后一致
  等于 pin；生成脚本与生成器 sha 入 manifest。

## 五、未被执行的预定事项（停机所致）

- 5 臂（F3R1-EW / F3R1-ICW / F3R2-EW / F3R3-EW / F3R4-A）的 runner 适配、dev 锚
  与 val 全期运行：**未执行**。因此本文件不给出三门判定表、逐年收益、F3R4-A 的
  60 交易日窗效应 val 存活性结论——这些检验**尚未发生**，不是「无结论」。
- 已按预登记 §2 冻结、可原样复用的部分：判据（三门逐字 = R16 `evaluate_val_gates`）、
  基准（B1(m)(val) 已验证）、事件表口径（dev 端口已验证）、因子管道（15/17 代表
  可复现）。
- dev 对照（来自各 F 线 dev run，本 run 未重新验证）：F3R1-EW +12.60% 死门 4/5/8；
  F3R1-ICW +13.23% 死门 4/5/8；F3R2-EW +3.77%/−20.20% 死门 3/4/5；F3R3-EW
  +4.88%/−17.85%，败点门 3（4/6）与门 8（83.3%）；F3R4-A +5.34%/−17.85%（探索级）。

## 六、建议的处置（供主对话裁定，本 run 不自决）

1. 修 D 族实现：把依赖未指定行序的 `group_by(...).last()/.first()`、
   `unique(keep="first")` 改为显式 tie-break（显式多键排序 + `maintain_order=True`
   或显式去重键），使产物可逐位复现。
2. 重发 F2R1 D 族（及 E16）的 dev 产物并记录新 sha；届时 17 代表的 dev 端口若
   全部通过，再按预登记重启 F 线 val 批次——**val 窗仍未被消费，一次性资格不变**。
3. 顺带核对：本 run 的 F 族 dev 端口运行覆盖写过
   `20260919T180000-f2r1-factor-batch/f_xsec_summary.json`（生成脚本继承了冻结脚本的
   写入目标；该文件无 manifest 记录、F2R1 无 manifest.json，无法还原或校验原字节；
   重写内容由同代码同 dev 输入算出，值应为 F2R1 值）。生成器已改为写本 run 输出目录，
   事件入 manifest `incidents`。

## 七、运行身份

- 输入身份：daily_1999_2024 sha256 `d9a63f4cc3032926`；R16 metrics.json、
  F3R1 dedup_clusters.csv、T1 events_dev.parquet、TL-30 metrics 各 sha 见 manifest
  `pins`；原始财务文件 23,622 个对账 0 不一致。
- 环境：python 3.11.15 / polars 1.44.2 / numpy 1.26.4；无 RNG（除 B3′ 种子 17–36，
  本 run 未触发臂运行）。
- 时间划分：dev 2015-01-05..2020-12-31（信号 71 期）；val 2021-01-04..2024-12-31
  （信号 47 期）**未消费**。2025+ 零接触（无任何 2025 信号月；财务原始数据中的
  2025+ 行由 `end_date <= 2024-12-31` 过滤，且 fina_indicator 抽样核对显示
  `end_date ≤ 2020-12-31` 而 `ann_date > 2024-12-31` 的行数为 0，52,086 行
  2025+ 公告全部对应 2021 年以后的报告期）。
- 阶段耗时（秒）：B1(m) dev 61.7 / val 39.7；因子 dev A 176、B 175、C 307、
  D 515（+复算 198、threads1 319）、E 174.8（修复版 74.6）、F 85；事件 dev 22.9；
  确定性探针 43；合计约 40 分钟墙钟。
- 试验计账：本 run 不消费任何 val 配置；策略线计数不变（B1(m) 重算与端口验证不构成
  新配置）。
- 产物：`outputs/b1m_dev.json`、`outputs/b1m_val.json`、
  `outputs/port_check_factors_dev.json`、`outputs/port_check_events_dev.json`、
  `outputs/d_family_reproducibility.json`、`outputs/d_pipeline_determinism_probe.json`、
  `tmp/stop_report.md`、`manifest.json`（status=aborted）。
