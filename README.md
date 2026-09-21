# 量化研究（新工作区）

## 最新进度（2026-09-21）

尚未找到符合完整策略契约且费用后年化达到10%的策略。**量价+ML 路线正式关闭**：Alpha158 特征 + LightGBM 滚动训练首次获得稳定截面信号（月度 Rank IC 0.046、t=4.94、五年全正），但 top-K 集中持有的两种宽度全部为负（K=4 −0.34%、K=10 −1.67%，后者回撤 −53%）——该信号的兑现方式是机构级统计套利（全池+多空），与个人账户集中多头结构根本不兼容。八轮实验的证据链完整：当前账户契约下没有任何选股路线产生正超额；防御底盘、账户级降仓、执行引擎被反复验证有效。方向待用户定。引擎层全部就绪，全仓 649 项测试通过。

连续 F3R1 / F3R3 / 固定方案三轮无候选过门——研究总预算检查已触发，主线方向待与用户重新讨论。2026-09-21 另登记一次未经授权的验证期数据访问事件（详见[策略状态](docs/research/strategy-selection-status-20260921.md)末节）。

详见[主计划](docs/plans/daily-short-term-rebuild.md)、[固定方案结果](docs/research/exp-20260921-fixed-scheme.md)、[账户级风险对照](docs/research/exp-20260921-account-risk-dynamic.md)及[ETF 路由决策](docs/decisions/2026-09-21-etf-pm-only-routing.md)。测试必须显式设置 `PYTHONPATH=src`。

2026-09-16 重建。**只保留原始数据**：旧库 `D:/AI/workspace/个人量化` 的代码、回测产物、
依赖环境全部不迁入；旧库的可读结论与证据留在 [`docs/legacy/`](docs/legacy/)（只读参考，非当前事实）。
迁移与删除的完整记录见 [`docs/MIGRATION_REPORT.md`](docs/MIGRATION_REPORT.md)。

## 重建计划与工作规范

- [AGENTS.md](AGENTS.md)：目录归属、数据保护、研究纪律、性能预算与交付要求。
- [日频短线重建主计划](docs/plans/daily-short-term-rebuild.md)：从最小性能验收到因子筛选、账户回测及离线交易计划的阶段安排。
- 当前状态（2026-09-19）：**P0/P1 验收；P2 全系关闭；P3 区间契约线收官（P3R1/P3R2 重裁 0 过；混合族 v1 0/8）**——个股五轮、ETF 轮动（R6/R7）、日频风控（R8/R9）、半天截面（R10/R11）、低频普查（R13）、事件否决（R12）、分钟微观结构（R14）、趋势+极度分散（R16）全部负面淘汰。契约引擎 **v1.4.1**（[契约](docs/plans/p3-band-contract.md) §7+§8+§9+§10、[引擎](src/quant/backtest/band_engine.py)，双签链：v1.3 全部能力 + zones 模式（ladder_buy 三档限价建仓、take_profit 成本锚定双档止盈、stop_sell 棘轮移动止损 + T+1 残部兜底、月内席位回收；zone/intent 互斥与 tp2_frac=1.0 两护栏 fail-closed）+ v1.4.1 tp1 列可选（零档止盈语义，§10.8：tp1 null/缺省⇒不发射止盈意图，tp2 不得脱离 tp1），463 测试；sha `a01cb29c…75abf3`，三锚 16 产物逐字节零回归实证）。**混合族 v2 首批 4 配置 dev 全门通过**（ROT-05 +8.99%/−12.46%）；用户裁定 val 暂不消费、继续 dev；**混合族 v3（ROT-05 降债阶梯，用户假设）7/7 dev 全过，R3-05/R3-06 净年化 11.06% 首达 ≥10% 目标列**——纯降债闲置现金单调变差（8.99→8.51%），增益来自第三轮动槽；R3-06（债15+金25+top3×20%）+11.06%/−16.22% 为风险结构最优。**混合族 v4（用户三轴指令：降债腾股票/债改红利/金波段）0/8 新配置过门，三轴全部证伪**——降债腾股票收益升但回撤破 20% 线（债=过门所需的缓冲）；债改红利收益升但 maxDD 恶化 7-13pp（红利=股票贝塔）；金入轮动 77-83% 时间被卖飞（金=静态腿用法）。R3-06 保持全场最优。累计 **238 项试验**（台账 [docs/evidence/trial-ledger.md](docs/evidence/trial-ledger.md)）。**当前状态（val 已消费 + 稳健性轮/扩展宇宙轮收官，方向转个股因子线）：R3-05/R3-06 通过全部 R16 冻结 val 三门（样本外 +2.33%/超额+2.47pp/−14.59% 与 +1.77%/+1.92pp/−15.14%，241 项试验首批）；稳健性轮（12 配置）确认家族优势是平台（9/9 有效邻域八门全过、回撤 11/11 受控）而 +11.06% 冠军点是邻域峰（超额 ±1pp 内 0/11，平台 +6.0~+8.4pp）——诚实期望 ≈dev +8%/样本外 +2%；dev 的 ≥10% 未样本外复现。QDII 513100/513500 合计约半数超额=最集中单一风险。扩展宇宙轮 v1（12 配置，二次过手协议 Phase A）：宇宙扩展=稀释而非增强——10 探索配置净 +4.13~+8.55% 全部低于 UNI6 锚 ≥2.5pp、入册资格 0/10，R3-06 的 dev 优势在参数与宇宙两维均呈尖峰、族内可挖空间系统性穷尽。用户方向裁定：收益主引擎回归个股（ETF 线降为覆盖层）；"挖因子后组合"路径已批准并完成基建——F0 因子输入审计（dev 全覆盖清单/PIT 双轨/接缝实测）+ F1 评估 harness（`src/quant/factors/eval.py`，12 项新测试；对齐契约 t+1..t+h 无同日泄漏、§5.4 缓存键、冻结断言全路径）。试验累计 262。**F2R1 因子首轮收官**（[结果](docs/research/exp-20260919-factor-round-f2r1.md)，用户裁定 12→120 多代理并行）：120 因子=六族（A 量价 25/B 估值 15/C 微观 20/D 财务 PIT 30/E 事件 20/F 横截面 10）全部计算评估（dev 2015–2020 月频 68 期、h=20、val 零接触），冻结 §2 四条终裁**存活 42/120**，|ρ|≥0.6 共 65 对聚成约 8 信息簇（反转巨簇 ~14）——42 为 F3 组合候选资格（多重性：纯随机预期 ~6 假阳性），非验证声明；台账另记因子线 120 项（FT-01）。全天代理基建 Captcha 故障 11+ 次死亡，A/B/C/D 四族由主对话接管实施；E 族验收发现并修复 E16 分红双计缺陷（判定不变）。**F3 组合轮收官（F3R1+F3R2，[R1 结果](docs/research/exp-20260919-factor-round-f3r1.md)/[R2 结果](docs/research/exp-20260919-factor-round-f3r2.md)）**：F3R1 去重 42→17 代表、EW/ICW 两组合臂经引擎 v1.3 裁定 0/2——净 +12.60/+13.23%、超额 +10.9/+11.6pp、优势年 6/6 与 5/6（**首个优势年结构完整的股票线 alpha**），死于门 4（长仓回撤 −38.9/−35.6%）、门 5（换手 6.12/6.75）、门 8（限价成交率 78.9/80.3%，纯限价范式结构性 <95%）；F3R2 把 R3-06 底盘（债15+金25）的轮动腿换成 F3 股票腿（K=3 buffer、T200-40 路径缩放）0/2：ICW 优势年 6/6 全胜但 K=3 两年期回撤 −33.05% 独死门 4，EW +3.77%/−20.20%（距线 0.20pp）死于门 3/4/5——死结=K=3 集中度 vs 路径唯一性，**按预登记停止条款 F 线暂停**；锚五帧逐字节复刻 R3-06（+11.06%）。dev 双达标最优仍为 R3-06，6 配置待 val（须用户批准）。**F3R3（用户三指令：行业约束/50 万资金/K=10，[结果](docs/research/exp-20260919-factor-round-f3r3.md)）0/2：风险门全修好（门 4 首过 −17.9%/−19.3%，门 5/6 过）但收益被摊薄（+4.88%/+3.42%，优势年 4/6 与 3/6）+ 门 8 v3 边缘案例 83.3%（1/6 无持仓清退计未交付）——三轮并观 F3 alpha 为集中度形态，门 3×门 4 权衡带内无双过点，F 线停轮呈用户**。试验累计 270。T1 **全量收官：65 批 / 38,567 行**（2026-09-20；65 批官方校验+独立复检全 0 错、深抽 6 轮+直查约 40 行、验收回改 5 起全留痕；全量分布 sd +1 92.3%/0 4.1%/-1 3.6%（矛盾行=数据质量信号）、low 1.7%；口径体系与回改台账见数据集 [SUMMARY.md](data/features/fcst-reason-struct-full-20260918/SUMMARY.md)）**。**F4R1 分区执行表收官（用户产品定调：a1/a2/吃反弹三档买入区 + b 止盈 + c 止损、每半天刷新、月中席位回收；[预登记](docs/research/exp-20260919-zone-sheet-f4r1-prereg.md) + [配置](configs/experiments/f4r1-zone-sheet.json) + [结果](docs/research/exp-20260919-zone-sheet-f4r1.md)；引擎 **v1.4 zones** 双签 pin `7ad35014…11e78`，契约 [§10](docs/plans/p3-band-contract.md)）：0/3 dev_pass——A 阶梯止盈去路径 +0.02%、B 保留路径对照 −0.01%、C 用户原版一步全卖 +0.86%，远低 ≥10% 目标列；门 4 首次全过（回撤 −9~−12% vs 锚 −39.8%，止损控回撤假设成立）但强年收益被截断（门 3 全灭 3/6：2015 锚 +22.7% vs 臂 ≤+2.2%）、止盈×ladder 鞭打换手超限（门 5 6.40~6.96）；门 8 v1.4 交付率 100%（armed 全 k3 兜底、stuck=0）；三臂低于 F3R3 与 R3-06——分区执行=回撤换收益，按预登记停止条款 F 线停止（F4R2 未开）呈用户决策点（转 val 申请 / 解冻参数另立预登记）**。试验累计 **275**（TL-36/37）**。**F4R2 纯止损消融收官（用户批准路径一；引擎 **v1.4.1** pin `a01cb29c…75abf3` 首用——tp1 列可选零档止盈语义经双签链；[预登记](docs/research/exp-20260920-zone-sheet-f4r2-prereg.md)+[配置](configs/experiments/f4r2-zone-sheet-notp.json)+[结果](docs/research/exp-20260920-zone-sheet-f4r2.md)）：0/2（D1 无止盈 +2.14%/D2 宽档 +1.44%，各破门 2/3/5），D1 落预登记中间地带 [2%,3%) 呈用户**——去止盈方向证实（2019 年差距 8.9pp→1.4pp）但未回 F3R3 量级；门 4 过（−17.09%，棘轮止损独立控回撤）；换手不降反升 7.34（主因=月度轮换+止损再建仓，非止盈鞭打）；剂量梯度 C<A 乱序（止盈档位非唯一折损源）；**F 线六轮定论：执行层折损多因素、门 3×门 4 无双过点，推荐转 R3-06 生产化前置**。**F3 存量审计收官（归因+留一，"17 代表里有没有坏因子"；[预登记](docs/research/exp-20260920-factor-attribution-prereg.md)+[结果](docs/research/exp-20260920-factor-attribution.md)；引擎 v1.4.1 非 zones 路径）**：**H1 否证（嫌疑名单空）**——17 代表贡献 t 值全为正（+0.19~+1.71）、无一过 §5.1 嫌疑线；FA-S2 重建 composite 与 F3R1 parquet 逐位一致；sanity corr 0.9979/符号 100%；leave-zero-out 锚五帧逐字节=底盘（v1.4.1≡v1.3 再实证）；留一矩阵描述性在档（剔 B12/D30/B14 ΔCAGR +1.88/+1.62/+1.56pp 且回撤改善，看过结果不动作、动因集须新预登记）；**F3 组合维持 17 因子原样，"alpha=集中度形态"结论加强，对 T1 下游零影响**。试验累计 **293**（TL-38）。台账补登 TL-33~35（F3R1/R2/R3）后计数一致。**T1 归因事件研究收官（exp-20260920-t1-reason-event，[预登记](docs/research/exp-20260920-t1-reason-event-prereg.md)+[结果](docs/research/exp-20260920-t1-reason-event.md)）**：控制 type 与公告月后 primary_code 归因对公告后 T+20 收益仍有增量——ANOVA F=3.343、p=7.13e-05<0.05 **H1 成立**（η²=0.006 如实记录）；BH 后 3 类显著：epidemic_shock（负，全部为 2020 事件）、impairment（正，分年 3/3、集中度低）、price_up（负，分年 3/3 但集中度 27.8%）；type 层 sanity 方向反向（预增弱于预亏组）只验证不判定、如实呈报；S1 剔 sd=−1/low、S2 h=5/10、S3 不去重全维持 H1 不脆弱；TE-S2 同式自写与 harness 全局逐位一致；dev 分析样本 6,656 事件（38,567 标注行连接断言全过）、val 零接触。因子线试验 120→**121**（FT-02）。归因因子进 F3 管道须另行预登记。研究代码在 `src/quant/`、测试 463 项；运行产物在 `artifacts/runs/`。**F3R4 归因事件信息并入 F3 组合收官（[预登记](docs/research/exp-20260920-factor-round-f3r4-prereg.md) + [配置](configs/experiments/f3r4-reason-integration.json) + [结果](docs/research/exp-20260920-factor-round-f3r4.md)；T1 下游应用，三臂全部在 composite parquet 层实现）**：**H1 成立（1/3 过线，探索级）**——A 加分臂（impairment +1σ / price_up −1σ）净 CAGR **+5.3356%**，Δ 基线 **+0.4583pp** ≥ 冻结 +0.30pp 线、maxDD 与基线逐位相同（−17.85%）；B 压制臂 +4.9440%（+0.0667pp）、C 第 18 因子臂 +4.8485%（−0.0288pp）未过线；三臂失败门与基线完全相同（门 3 优势年 4/6、门 8 v3 交付 83.3~85.7%），风险门 4/5/6 全过、无臂达 ≥10% 目标列。座位机制：A 把 impairment 座位月 3→33（26 只、分散）、price_up 13→0；只做去坏的 B 仅 +0.067pp——**增益在加分侧**。**折扣项**：窗口敏感性（20/40 窗为 +4.68%/+4.74%，均低于基线、非单调，只有冻结 60 交易日窗过线）与“同段 dev 二次使用”的探索级身份——**不得称验证，val 2021-2024 零接触**；下一步（A 臂 val 一次性验证申请 / 结构化另立预登记）呈用户决定。锚（未改动 F3-EW composite 跑派生 runner）五帧逐字节 5/5、独立复核五项全过、墙钟 71.3s。试验累计 **296**（TL-39）。**val 批量检验收官（[预登记](docs/research/exp-20260920-val-batch-prereg.md)+[V1 结果](docs/research/exp-20260920-val-batch-hybrid.md)+[V2 结果](docs/research/exp-20260920-val-batch-fline.md)；用户指令 12 配置=混合族 7+F 线 5；判据=R16 冻结 val 三门逐字；引擎 v1.4.1 pin）**：**V1 混合族 7 配置仅 H2-03 三门全过（净 +1.81%/超额 +1.96pp/maxDD −12.11%）**——H2-01/H2-04/R3-01..04 全部死于门 1（超额 +0.24%/−0.70%/−0.29%~+0.12%），R3 降债阶梯 4 臂与母型 ROT-05 样本外一致覆没（dev→val 收缩 −8.8pp）；**样本外三门全过配置累计 3 个（R3-05 +2.33%、R3-06 +1.77%、H2-03 +1.81%），全部 ETF 线 +2% 级**。**V2 F 线 5 配置因子 dev 端口 FAIL 8/17 停机、val 未消费（一次性资格保留）**：D 族 7 代表+E16 的 F2R1 冻结产物不可复现——同代码同输入（23,622 文件 sha 0 不一致）四路运行（含单线程）sha 全不同，根因=shipped 脚本 `sort(...).group_by(k).last()` 惯用法未实现文档 tie-break（合成探针 8.4% 组偏移≈D 族 8-9% 同日多公告率）；FA-S2 存活集合四路全同（结构结论稳、分数值不稳）；B1(m) dev/val 与事件 dev 三端口 PASS。**推论：F 线 dev 第一梯队数字（F3R1..F3R4）建立在不可复现产物上、身份作废，须修复确定性后重走 dev 链再议 val（处置呈用户裁定）**；附带事故：V2 端口运行覆盖写 F2R1 `f_xsec_summary.json`（同代码重算、原哈希不可还原、已登记 incidents，其余先例目录 0 改动亲核）。试验累计 **303**（TL-40）。**2026-09-20 策略审查与修复（[审查报告](docs/research/exp-20260920-strategy-review.md)）**：13 项已核实缺陷中 9 项当日完成代码/环境修复（R1/R2/R5/R6/R7/R8–R13，全部带合成反例回归测试，485 项测试全过；引擎升 v1.4.2，新增 `quant.factors.fund_derive` 与 `quant.research.t1_event`）；F2R1 产物确定性（R3）、运行目录治理（R4）与受影响 dev 链路重走须新一轮预登记。**口径更正**：历次"样本外"应读作二次过手 holdout（证据折扣）；"三门全过 3 个……全部 ETF 线"有误——H2-03 含 C05 股票腿，为混合配置；当前状态三分：筛选条件通过（R3-05/R3-06/H2-03）/ 研究目标未达成（10% 年化无一触及）/ 尚未验证（2025+ 冻结区）。不修改旧环境，无任何盈利承诺。
- 已验证运行命令（仓库 `.venv`，Windows）：
  ```powershell
  .venv\Scripts\python.exe -m pytest tests -q                          # 全量测试（485 项，含 90+ 契约/zones 测试）
  .venv\Scripts\python.exe src\quant\cli\p2_factor_survey.py         # 因子普查全量（约 152s / 9.2GB）
  .venv\Scripts\python.exe src\quant\cli\p2_factor_survey.py --symbols 200   # 冒烟
  .venv\Scripts\quant.exe --version                                    # CLI 独立进程验证
  .venv\Scripts\python.exe src\quant\cli\factor_eval_run.py --panel <panel.parquet> --factor <factor.parquet> --artifacts-root artifacts
                                                                       # 因子评估入口：显式输入，自动创建不可覆盖的新 run
  uv pip install --python .venv\Scripts\python.exe --no-deps .         # 修改 src/quant 后必须重装（.venv 为非 editable wheel：中文路径下 editable .pth 按本地编码读取而失效）
  ```
- 下方是现有数据目录；未来代码、配置、实验产物和私有账户按 AGENTS.md 分开存放，按需创建，不迁动原件。

## 目录

```
data/raw/            原始数据层，只新增不覆盖；每个批次目录自带 manifest/校验文件
  bigquant/          1 分钟（years/2010-2016、2018、2019、2025、2026）+ 探针/补丁批
  user_minute_1m/    1 分钟（<批次>/2015…2024，全市场按日 parquet，含 2017）
  user_dataset/      用户日线数据集（百度网盘，沪深 × 不复权/前复权/后复权，仍为 zip）
  baostock/          日线、复权因子、5 分钟补数、停牌/ST/退市补齐
  tushare/           Tushare 官方财务与日指标（24 个数据集，按交易日/逐股分块）
  xiaodefa/          Tushare 兼容代理全量取数（63 个数据集）+ 分钟补丁清单
  em_fin/ ths/ tx/ sina/ sina_industries/ sina_universe/   基本面 / 日线复核 / 列表 / 行业
  etf-minute-probe/  ETF 5 分钟探针批
  hf_minute_1m/      第三方 1 分钟来源探针记录（数据副本已去重删除）
  user_csv_1m/       仅保留补丁清单与迁移 manifest（数据内容已并入 bigquant）
data/_meta/          工具输出：inventory.json / dupes.json / sha256.tsv
docs/                台账、数据源口径、覆盖矩阵、去重报告、迁移报告、证据
docs/evidence/       迁移与解压证据：minute-extract.json / minute-manifest.json / …
docs/legacy/         旧库文本结论与证据：docs/（217 篇）、artifacts-evidence/、old-source-snapshot.zip、old-history.bundle
tools/               台账 / 去重 / 校验 / 哈希 / 1 分钟解压工具
```

## 数据规模（2026-09-16，1 分钟解压后）

| 来源 | 批次目录 | 文件数 | 体积 |
|---|---:|---:|---:|
| bigquant（1 分钟 years/ + 探针） | 16 | 14,004 | 69.26 GiB |
| user_minute_1m（1 分钟 2015–2024） | 12 | 2,433 | 35.67 GiB |
| xiaodefa | 63 | 66,631 | 13.11 GiB |
| tushare | 46 | 35,757 | 4.31 GiB |
| user_dataset | 2 | 6 | 1.98 GiB |
| baostock | 19 | 17,805 | 1.87 GiB |
| 其余（sina/tx/ths/em_fin/etf-minute-probe/hf_minute_1m/user_csv_1m/sina_universe/sina_industries） | 930 | 2,251 | ~0.11 GiB |

合计 **1,088 个批次目录 / 138,887 个文件 / 135,634,263,041 B（126.3 GiB）**。
精确清单：[`docs/DATA_INVENTORY.md`](docs/DATA_INVENTORY.md)、`data/_meta/inventory.json`。

> **数据不干净**：本库是有缺陷的历史数据，不是干净数据源——1 分钟包 2015-07-01 有 11 只深市股票尾盘
> 零量重复价格、22 项待补/受审证券日、`sz.300114` 全网缺分钟、`xiaodefa` 部分数据集未拉全。
> 用前必读 [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) 与下方「已知数据缺陷」。

## 数据覆盖（详见 [docs/DATA_COVERAGE.md](docs/DATA_COVERAGE.md)）

- **1 分钟全市场**：2010–2026 全覆盖，**全部已解压为目录层**——2010-2014、2025、2026 与
  2015/2016/2018/2019 按证券 CSV 在 `bigquant/.../years/<年>/`；2015-2024 按日 parquet 在
  `user_minute_1m/<批次>/<年>/`（2017 仅此一处）。压缩包已于 2026-09-16 解压后删除，
  聚合与单位口径见 [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)。
- **日线**：`user_dataset`（3 种复权形态，仍为 zip）+ `baostock`（在市日线 5552 只、复权因子 343 只、停牌/ST/退市）。
- **截面与执行参数**：`xiaodefa`（复权因子、涨跌停、停复牌、集合竞价、资金流、筹码、两融、港股通…）、
  `tushare`（财报三表、财务指标、每日指标、分红、股本、两融、龙虎榜）。
- 2025 年以后与生产发布按旧库约束继续冻结（`years/2025`、`years/2026` 仅作留存）。

## 工具

需要一个带 pandas/pyarrow 的 Python（当前用工作区外的 `D:\AI\workspace\qlib-env-20260915`）：

```powershell
$PY = "D:\AI\workspace\qlib-env-20260915\Scripts\python.exe"

# 1) 数据台账：文件数/体积/扩展名/批次日期覆盖 + 同目录批次区间重叠
& $PY -X utf8 tools\inventory.py data\raw --json data\_meta\inventory.json --md docs\DATA_INVENTORY.md

# 2) 字节级重复扫描：先按尺寸分组，只对同尺寸候选算 BLAKE2b 摘要
& $PY -X utf8 tools\dedupe_scan.py data\raw

# 3) 全量 SHA-256 台账（约 135 GiB，2 分钟）；--verify 只校验不重写
& $PY -X utf8 tools\hash_manifest.py
& $PY -X utf8 tools\hash_manifest.py --verify

# 4) 1 分钟清单：逐年文件数/字节/首末交易日
& $PY -X utf8 tools\minute_manifest.py

# 5) 1 分钟压缩包解压（已完成，留作复核）：--verify-only 只核对已解压目录
& $PY -X utf8 tools\extract_minute_zips.py --verify-only
```

`tools/migration/` 里是 2026-09-16 迁移时的一次性脚本（旧库证据抢救、legacy 结构重建、旧库删除），
仅作留痕与复核，不影响日常使用。

## 数据纪律

- `data/raw/` **只新增不覆盖**：修正数据进新批次目录，不覆盖原件；批次目录名是数据身份的一部分。
- 各目录内的 `manifest.json` / `*.sha256.txt` / `transfer-manifest.json` 是身份与校验凭据，
  不重命名、不移动、不手工编辑（其内记录的绝对路径属历史身份，见迁移报告 §8）。
- 凭据（token）只放 `~/.quant-credentials/`，不入库、不入日志。
- 时间/单位陷阱（1 分钟包 float32 分币编码、241→48 聚合、CSV 包单位为手、财务披露滞后 90 天、
  腾讯量纲分板块不同…）集中登记在 [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md)，写新代码前先读。

## 已知数据缺陷（不要当成干净数据用）

- 1 分钟包 2015-07-01 有 11 只深市股票尾盘 14:54–15:00 零量重复价格、日量存在缺口；
  另有 22 项已登记待补/受审证券日。清单见
  `docs/legacy/artifacts-evidence/user-minute-1m-review-20260913-1/` 与
  `data/raw/xiaodefa/minute-repairs-*/patches.json`。
- `xiaodefa` 代理 token 于 2026-09-14 过期，部分数据集未拉全（清单见
  `docs/legacy/artifacts-evidence/xiaodefa-bulk-20260913/inventory-20260914.json`）。
- `sz.300114` 2016-05-03 在任何来源都无分钟数据。
- 同区间的两种分钟封装（按证券 CSV 与按日 Parquet）数值不逐字段相等，且 `xiaodefa` 的 `stk_mins`
  与整包同源；三者之间**不能互为独立验证**（见 [docs/DEDUPE_REPORT.md](docs/DEDUPE_REPORT.md)）。

## 文档

- [研究总账与规则（全部实验+规则总账）](docs/research/research-ledger-20260921.md)
