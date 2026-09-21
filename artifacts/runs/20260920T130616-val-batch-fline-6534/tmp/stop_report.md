# STOP REPORT -- exp-20260920-val-batch (V2 / F 线)

- 停机时间：2026-09-20T06:14:02.452555+00:00
- 停机阶段：F 线 dev 端口验证（17 因子 val 分数展开之前）
- 触发条款：预登记 `docs/research/exp-20260920-val-batch-prereg.md` §6
  「任一端口验证（B1(m) dev、H2 dev、因子 dev、事件 dev）失败 → 对应配置停机呈报，
  其余继续」；§3 F 线「dev 端口验证=重算 dev 分数须逐位复现 F2R1 原产物……后才展开 val」。
- 原因：**17 个代表因子中 8 个（D 族 7 + E16）的 dev 分数无法逐位复现**，且失败根因在
  冻结产物本身——同一份 shipped 脚本、同一份字节级未变的输入，四次运行给出四份
  互不相同的因子帧：

  | 运行 | D10 sha256:12 | 行数 |
  |---|---|---|
  | frozen_f2r1 | e749803de188 | 288699 |
  | rerun_1 | f983dad9c50b | 289101 |
  | rerun_2 | dcf4c396b168 | 289025 |
  | rerun_3_threads1 | 68e998efd226 | 289039 |

  （7 个 D 代表全部如此；明细 `outputs/d_family_reproducibility.json`）
- 排除的其他解释：
  1. **输入数据变化**：`data/_meta/sha256.tsv`（2026-09-17 深度扫描基线）覆盖的
     23,622 个财务原始文件逐个重算 sha256，**0 处不一致**——输入自 F2R1 运行之前
     至今未变。
  2. **我的窗口适配引入偏差**：生成的 val 脚本与 shipped 脚本逐行 diff，仅窗口常量、
     输出路径、sig_cap 包装与 B04 读取路径不同；dev 模式下每一项语义等价
     （diff 已留档于 `tmp/`、`logs/`）。
  3. **线程数**：`POLARS_MAX_THREADS=1` 运行仍与其余三次不同（threads1 列）。
  4. **pit_full 的重述 tie-break**：定向探针显示该表达式在进程内可重复、且与显式
     排序等价（`outputs/d_pipeline_determinism_probe.json`），故不是不稳定步骤；
     不稳定点在 `build_d_fund_main.py` 的 join/sort/group_by 链中，列为后续工作。
- 受影响配置：**V2 全部 5 个配置**（F3R1-EW / F3R1-ICW / F3R2-EW / F3R3-EW /
  F3R4-A）——17 代表中有 7 个来自 D 族，全部 5 个配置的 composite 都消费它们。
- **val 未消费**：未生成任何因子 val 分数、未构建 val composite、未跑任何 val 臂。
  唯一算到 val 的量是预登记 §3 指定的基准 B1(m)(val)（TL-30 已公开 −0.148%/−23.44%，
  本轮逐位复现），不构成任何配置的 val 判定。
- 已通过的端口（留档）：
  - B1(m) dev：与 R16 metrics.json configs.C05 b1m_* 逐位一致（1e-9，含 6 个年度）。
  - B1(m)(val)：与 TL-30 −0.00148060230384095 / −0.23441429674947534 逐位一致（1e-9）。
  - 归因事件 dev：7 个产物中 6 个字节一致；events_dev.parquet 仅 parquet 行序不同，
    键集与全部数值逐位一致，且 6 个下游统计产物（ANOVA p、分类统计、漂移、敏感性、
    池漏斗）字节一致。
  - 因子 dev（最终）：字节一致 6（A17/A20/A25/B11/B12/C19）、数值逐位一致但行序不同 3
    （B14/F06/F09）、**失败 8**（D 族 7 + E16 1）。E16 的失败同样是产物不可复现：
    冻结 E16 由带外修复脚本产出，该修复的按 (symbol,ex_date) 去重
     依赖未指定行序；本 run 用同口径连跑两次，
    24~27 行数值不同（键集与行数相同，最大差 0.0238），故「差 1.15e-4」只是
    单次抽样结果，不是可复现的固定偏差。
- 因子 dev（分项）：17 代表中 6 个字节一致、3 个数值逐位一致（仅行序不同）、1 个（E16）
    最大差 1.15e-4（冻结 E16 由带外修复脚本 `fix_E16_dupcount.py` 产出，其按
    (symbol,ex_date) 去重的 `unique(keep="first")` 本身依赖未指定的行序）、7 个
    失败（D 族）。
- 处置建议（不在本 run 决定）：先让 D 族实现对显式 tie-break 与稳定排序（例如
  `maintain_order=True` 或显式 `sort(...).unique(...)` 去重）后重发 dev 产物，
  再按预登记重启 F 线 val 批次；val 窗保持未消费、一次性资格不变。
- 本 run 未做：5 臂 runner 适配与 dev 锚、val composite、任何 val 判定。
- 试验计账：本 run 不消费任何 val 配置；策略线计数不增加（B1(m) 重算与端口验证
  不构成新配置）。
