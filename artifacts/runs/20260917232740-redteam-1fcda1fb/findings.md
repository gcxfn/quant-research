# 红队审查发现（exp 审查轮，只读攻击性审查）

- run_id: `20260917232740-redteam-1fcda1fb`
- 日期：2026-09-17。审查者：红队子代理（未修改任何仓库文件；临时脚本在本目录 `tmp/`）。
- 审查对象按任务优先级：① `docs/research/exp-20260917-p2r6-etf-rotation-prereg.md`（+实现 `src/quant/research/etf_rotation.py`、`src/quant/cli/p2r6_etf_rotation.py`）；② `src/quant/research/screen.py`、`fee_recost.py`；③ `src/quant/data/rqalpha_bundle.py`（对照 .venv rqalpha 6.3.0 源码）；④ `docs/research/exp-20260917-fee-recost.md`。
- 执行状态声明：P2R6 已有三份 completed 全量 run（`20260917T230609/231139/231652`，config_sha 相同、结果相同），结果文档尚未落盘。以下涉及 P2R6 的问题凡属"协议定稿后、结果文档写出前发现"，均标注**事后披露项**——照报，由结果文档如实披露。
- 严重度定义：critical=会改变结论；major=会改变数值；minor=披露不足/口径瑕疵。

---

## 汇总

| 严重度 | 数量 |
|---|---|
| critical | 0 |
| major | 4（R1-1、R1-3、R2-1、R3-1） |
| minor | 18 |
| 正面核验（未发现问题） | 6 项，见文末 |

---

## Target 1：ETF 轮动预登记（exp-20260917-p2r6-etf-rotation）+ 实现

### R1-1 [major] B1 同池等权基准被最低佣金制度性抬高，"净超额 vs B1"（gate-2 锚）系统性虚高 —— 事后披露项

- 角度：经济逻辑 / 基准构造 / 费用口径。
- 证据：
  - 预登记 §1.2（prereg 第 30 行）与 §4.2（149 行）：B1 每腿名义 200,000/N，佣金 max(万1, 5元)。N≥5 时每腿 5 元最低佣金必然生效。
  - `etf_rotation.py:688`（`_buy_fee(budget, fees)`，budget=base×1/n）与 `p2r6_etf_rotation.py:177`（total=200,000）。
  - 实测（本 run metrics）：B1 weekly dev 买入名义合计 **50,516,752 元**、单边换手 **253.67x**、dev 净年化仅 **4.50%**（monthly B1 为 10.40%）。解析计算 B1 weekly 年费用（n 腿 × 5 元 × 每年 52 次，按当年池均值）：2016 年 1,898 元 → 2018 年 2,782 元 → **2020 年 11,544 元**（≈5.8%/20 万本金/年）；monthly 2020 年 2,742 元。
  - 对照：策略 C02 全程 9 年总费用仅 **2,948 元**（trades.parquet，441 笔）。
  - 后果：weekly 配置对 B1 的表观净超额（+4.6~+7.1pp/年）中相当大部分是基准费用假象；monthly 配置超额也被抬高 ~0.5-1.5pp/年。
  - 预登记虽有披露（"早年腿多名义小时最低佣金抬高 B1 费用，与换手不对称一并披露"，30 行），但把它定性为"早年"现象；实测它随池扩大而**恶化**（2024 年池 88-206 只，weekly B1 年费用解析值 32,890 元 ≈16%/年，若 B1 延续）。
  - 不改变终局结论：12/12 全部死于 gate-3/4/5（正收益年数、回撤、换手），仅 C01 另死 gate-2；公平化 B1 只会让 C01 多活一条（仍死于 3/4/5）。
- 建议处置：结果文档报告对 B1 的超额时同时给出"费用可比化 B1"（组合层面按一笔名义计佣或费用中性 B1）的敏感性；把本条写入披露；后续轮次的同池基准改为按腿名义不低于最低佣金生效阈值的加权方案或直接披露上下界。

### R1-2 [minor] gate-8 执行率口径偏离预登记且分子分母不对称 —— 事后披露项

- 角度：预登记一致性 / 判据口径。
- 证据：
  - 预登记 §6 第 8 条（178 行）：dev gate 的"执行完整性 ≥95%"。实现 `p2r6_etf_rotation.py:273-275` 自认："execution rate is accumulated over the whole continuous run (2016-2024); the gate-8 quantity is this whole-run rate"，并把它填进每个段的 metrics（275 行）——dev 判据使用了 dev 之外（val/test）期间的数据。
  - `etf_rotation.py:368-374`：`buys_no_candidate`（无任何可成交候选、槽位空仓）计入分子"已执行"；`sells_forced_delist` 计入分子但从不计入分母（planned_sell_legs 只在 build_plan 累加）→ 执行率可被推高甚至可能 >100%。
  - 实测影响：各配置 99.72%-100%，无 gate-8 翻转；本轮无数值后果。
- 建议处置：结果文档披露 gate-8 实际口径为"全程率"并解释为何不改变判定；后续轮改为 dev 段率，并把 no-candidate 单列。

### R1-3 [major] B3 随机基准不带绝对动量门，gate-7（胜随机 +1pp）把"择时门"贡献冒充"选币"证据 —— 事后披露项

- 角度：基准严格性 / 经济逻辑。
- 证据：
  - 预登记 §1.2（32 行）："B3……同管线、无动量门"；gate-7（177 行）要求 dev 净年化 ≥ B3 均值 +1.0pp。
  - 实现 `p2r6_etf_rotation.py:191-194`：B3 的 selector 直接洗牌全合格池（含 gate 不通过者），从不空仓（除成交失败）。
  - 实测：B3 monthly dev 净年化均值 8.49% [5.33%, 13.46%]，而 gate-on 配置的动量+门设计允许 2020-03/2018 等时段整槽空仓——gate-7 的 +1pp 阈值无法区分"门在下跌段躲掉了"与"排序选出了更好的币"。本轮 12/12 配置 gate-7 全部通过（净 9.1%-15.9% vs 8.5%/7.1%），即该判据从未构成约束，也未提供选币证据。
- 建议处置：结果文档把 gate-7 解释为"策略 vs 无门随机"而非选币检验；若后续继续该方向，应加一个"随机 among gate-passers"的 B3' 对照。

### R1-4 [minor] 9.5% 涨跌停代理产生双向错误成交假设（向上假阻断为主），预登记 §8.3 待确认项仍未与交易所规则核对 —— 事后披露项

- 角度：可成交性 / 代理规则错误。
- 证据：
  - `etf_rotation.py:57`（LIMIT_PCT=0.095）、`:322-331`（开盘 vs pre_close 单一阈值）。ETF 真实规则：10% 品种的涨停价是 round(preclose×1.1, 2)（低价 ETF 折算比例可偏离 10%），创业板/科创板 ETF 为 20%。
  - 实测（白名单 fund_daily 全量 2016-2024）：开盘 gap ≥ +9.5% 共 **1,353 行**（2020-02: 94、2016-01: 42、2018-10: 11），top codes 多为 501 段 LOF（501302/501047/510580…）；≤ -9.5% 共 263 行。
  - 策略端后果：entry_limit_blocked 每配置 87-101 次（metrics exec_stats），由排名顺延吸收；exit_limit_blocked 仅 0-1 次。对 20% 限制品种，[9.5%, 20%) 的合法开盘被误判为不可买/不可卖；对 10% 品种，[9.5%, limit) 的合法开盘同样被误判。方向混合（对动量买入偏保守），量级有限但非零。
  - 预登记 145 行与 §8.3（212 行）均已声明为保守代理待核对。
- 建议处置：结果文档披露阻断计数与发生日期分布；执行前或结果文档内把代理改为"开盘 ≥ round(pre_close×1.1,2)（10% 品种）/ ×1.2（创/科品种按跟踪指数判别）"，或引用用户确认。

### R1-5 [minor] 退市强退机制零触发：幸存者控制"建好了但从未被检验"，§7 承诺的证据为空 —— 事后披露项

- 角度：幸存者偏差 / 机制有效性。
- 证据：
  - 正面：116 只窗内退市 ETF **全部**在 fund_daily 批次与冻结白名单中（本审查实测，whitelist 1,168 = fund_daily 覆盖 1,169 − 1 无因子），数据面幸存者偏差已覆盖；registry_without_file=704 均为边界后上市等非池内对象。
  - 但 eligibility 过滤后仅 7 只退市 ETF 共 88 个行日曾合格（510420/159962/510610/159911/510260/510430/510620），**0 个**月频信号日合格池含任何退市 ETF；全 run `forced_delist=0`（trades/positions/metrics 三处一致）。
  - 预登记 §7（203 行）要求报告"退市 ETF 在窗内被持有的事例数（幸存者控制生效证据）"——该证据是 0，结果文档不得写成"控制已生效"，应写"流动性门槛使退市标的从未进入可选池，U4 机制未被检验"。
  - 附带：退市定价 = 最后可得收盘价计费强制卖出（`etf_rotation.py:293-297, 460-471`）未获实证；`delist_ok`（149-150 行）用 `trade_date < delist_date`，退市日当天仍可入池的边界也未发生。
- 建议处置：结果文档如实写 0 事例并说明原因；后续若重跑，考虑输出"退市 ETF 距离流动性门槛的余量分布"作为池纯度证据。

### R1-6 [minor] fund_adj 存在 4 个调整断层日，产生 +4%~+8.9% 幻影单日收益进入动量与门控 —— 事后披露项

- 角度：数据口径 / 前视外失真。
- 证据：preflight（`tmp/p2r6-preflight.json`）记录 jump_day_abs_adj_ret_gt_4pct=4；本审查复算定位为：160615.SZ 2022-06-28（因子 +17.0%，raw -6.9%，adj **+8.9%**）、160615.SZ 2022-10-26（+4.0%）、510230.SH 2020-08-17（因子 ×4.9，raw -78.8%，adj +4.2%）、512670.SH 2021-08-23（因子 ×2.0，raw -47.9%，adj +4.5%）。这些是份额折算/分拆类事件未完全被因子吸收，R20/R60 与 SMA120 在事件后若干日含幻影动量。
- 建议处置：结果文档列明 4 例及所影响配置/时段；后续把"因子跳变日 |adj ret|>4%"设为硬校验。

### R1-7 [minor] U2 QDII 关键词漏判 3 只跨境 ETF 且被策略实际持有（主要在 test 段）—— 事后披露项

- 角度：池规则 PIT / 披露完整性。
- 证据：513310.SH（中韩半导体 QDII）、513730.SH（新交所泛东南亚科技 QDII）、513800.SH（TOPIX QDII）名称不含关键词表任何词，通过 U2。positions.parquet：513310 8 笔、513730 15 笔、513800 4 笔（含 513730 于 2024-10-08 买入）。B3 亦持有（42/33/6 腿）。预登记 70 行允许"残留漏判风险在结果文档披露"——现已从风险变为实例清单。
- 建议处置：结果文档列实例并给出剔除后 dev/test 指标的敏感性（3 只对 1,168 只池影响小，但必须落字）。

### R1-8 [minor] 白名单含 20 只 LOF 段代码，预登记 U1 前缀规则并不覆盖 —— 事后披露项

- 证据：whitelist 中 501×12、502×1、160×3、161×2、162×2 共 20 只（config `u2_note` 已披露"Name rule admits ETF-named LOF feeders"，但预登记 §2.3 U1 文本无此说）。LOF 的价差与可成交性与 ETF 不同，9.5% 阻断计数也集中于这些代码。
- 建议处置：结果文档披露清单与流动性门槛后的实际残留；后续把 U1 白名单按"前缀 or 名称且非 LOF 段"收紧重审。

### R1-9 [minor] 槽位负现金 = 零息杠杆，最深 -40,344 元（约 20% 资金），预登记未登记该机制 —— 事后披露项

- 证据：`etf_rotation.py:437`（每槽固定 budget 入金）、`:558-575`（`_open` 无视 slot.cash 余额按固定 budget 买入）、`:489`（max_negative_cash 仅记录、无判据约束）。metrics：C12 max_negative_cash=-40,344、C07 -35,711。代码 docstring（28 行）有"disclosed"，预登记正文无。对策略与 B3 同向、对 B1（全额再平衡口径）不适用。
- 建议处置：结果文档披露负现金分布；后续轮为 slot.cash 设下限或在权益中计融资费用。

### R1-10 [minor] 三次全量 run 均为 completed，结果文档须指定唯一权威 run_id

- 证据：`20260917T230609-f1f60270`、`20260917T231139-cf10be51`、`20260917T231652-7b72501d`：config_sha256 相同（f3ee90cc8019…）、关键指标相同（C02 dev 超额均 0.0325）——是重复执行而非挑选，但留档义务要求指明以哪个 run 为准、为何重复。

### R1-11 [正面核验] 池 PIT 与协议一致性检查通过项

- 116/116 窗内退市 ETF 有行情并在白名单（防数据面幸存者偏差，§0 承诺达成）。
- `amount`/`vol` 单位实测（preflight [2]：implied vwap/(H+L)/2 中位数 1.0000，n=2800；bundle 侧 1,017,121 行 vwap guard severe=0），liquidity_min_units=50,000 千元换算正确。
- B2 510300 全窗 2,431 行在批内（§8.2 前置条件已满足，B2 dev +51.2%/val -23.3%/test +6.0% 合理）。
- 信号日定义（月末/ISO 周末日，`rebalance_days`）无隐藏选择偏差；并列按 (值,代码) 升序确定性排序；段间市值结转、test 只对 val 通过者评估一次（`p2r6_etf_rotation.py:386-390`）；12 配置全评估全披露；gate 过滤发生在排序后、build_plan 的留任/顺延与 §4.2 一致；T+1（`entry_session < si`，`etf_rotation.py:469`）成立。
- 2016-2018 池薄（月频 6-11 只）已被 §2.4 预见，逐年池规模已记录。

---

## Target 2：src/quant/research/screen.py 与 fee_recost.py

### R2-1 [major] 事件研究的尾部截断：被阻断退出的事件无标签且不进均值，反事实为灾难性亏损，系统性抬高全部五轮已发表均值

- 角度：前视/幸存者（事件内条件剔除）/ 费用归因之外的性能口径。
- 证据：
  - `screen.py:11-13`（"a missing/blocked exit yields a null label rather than a dropped row"）与 `:500-511`（exit_limit_down/exit_unavailable → 无 net_return_pct）；下游报告均值均按 completed 计算。
  - 反事实实测（下一可交易日开盘退出，raw 价近似）：R1 `20260917T161253`：completed 均值 -1.478pp，被阻断退出 1,206 笔，反事实均值 **-15.8pp**（中位 -18.5pp，最差 -68.6pp）；**乐观界**（按被阻断当日开盘成交）均值 **-6.64pp**。R3：completed -0.369pp，674 笔，反事实 -27.7pp，乐观界 -13.6pp。
  - 量级换算：按受影响占比，各配置每笔均值约被抬高 +0.1~+0.2pp（个别高阻断配置更多）——与 fee-recost 全部 +0.05pp 的费率效应相比大 2-4 倍，且足以吞噬唯一 dev 转正者 R2-near52w-dip（+0.18→+0.23pp）的全部优势。
  - 不翻终局：聚合均值仍深负，"27 配置全部淘汰"的方向不变，但所有已发表的每笔均值数字带一个未量化的乐观偏置。
- 建议处置：结果文档给出"含阻断退出的界（乐观界/下一开盘界）"作为均值的区间；后续轮把 blocked exit 以显式延后退出路径计价而非丢弃；fee-recost 类重估应同时发布截断修正后的均值。

### R2-2 [minor] 持有期内转为 ST 的股票以 10% 代理检查退出，漏掉 ST 5% 跌停 → 把实际不可成交的跌停开盘记为成交

- 角度：可成交性 / 代理规则盲区。
- 证据：`screen.py:481-486` exit_ok 不检查 exit 侧 isST；`:491-495` limit_pct=0.10 固定。实测 R3：完成事件中 exit_isST==1 共 62 笔，其中 **48 笔**开盘 gap ∈ [-9.5%, -4.95%]（多为 -5.0% 整，即 ST 跌停开盘）被记为成交（例：sz.002680 2018-07-26 -5.02%、sh.600666 2019-04-29 -5.07%）。R5 同类 23 笔。对均值影响 ≈0.016pp（ST 退出行均值更差，含之使结果更悲观，但"按跌停价逃逸"本身对后续路径偏乐观）。docstring（18-21 行）只登记了 10% 近似与 P3 分钟复核，未提 ST 5%。
- 建议处置：披露 ST 5% 盲区；后续退出侧按当日 isST 选择 5%/10% 两档。

### R2-3 [info] gross 标签为复权比推算而非公司行动现金账本

- `screen.py:14-17` 已声明；持有期 ≤10 日时分红进入标签的概率低；P3 账户级契约另核。维持现有披露即可。

### R2-4 [minor] fee_band_for 对早于首档日期静默返回首档

- `screen.py:114-122`：`selected = schedule[0]` 起步，早于所有 from_date 的 day 也返回首档。当前首档 2015-01-01 覆盖全样本无实害；若未来登记晚于样本起点的费率表会静默错档。
- 建议处置：早于首档时抛错或要求首档覆盖研究起点。

### R2-5 [正面核验] fee_recost.py 逐笔复现与防篡改机制有效

- 实测 178,724/178,724 笔旧费用按各 run 原 config 费率复现（1e-6 内），`exit_notional = entry_notional×(1+gross)` 校验通过；基金代码拒绝、窗口归属（signal_date ≤2020-12-31 → dev）与五轮报告一致；无发现可静默错数据的路径。

---

## Target 3：src/quant/data/rqalpha_bundle.py（对照 rqalpha 6.3.0 源码）

### R3-1 [major，当前潜伏] ETF 份额折算在账户级引擎是静默资金蒸发路径：fund_adj 有因子、dividends/split 均无行、持仓按原始价估值

- 角度：数据口径 / ETL 静默错数据 / 账户级未来漏洞。
- 证据链：
  - fund_adj 记录了折算：510230.SH 2020-08-17 raw **-78.8%**、因子 ×4.9；512670.SH 2021-08-23 raw -47.9%、因子 ×2.0（本审查复算）。
  - `rqalpha_bundle.py:71-72`（"ETF cash-dividend EVENTS have no on-disk source -> ETF dividends.h5 keys are absent"）且 split_factor 仅由股票 stk_div 生成（`:57, :629-669`），ETF 无 split 行。
  - 引擎持仓估值走原始价：`portfolio/position.py:162`（market_value=last_price×quantity）、`data/data_proxy.py:289-290`（get_last_price→price_board 原始价）；ex_cum_factor 仅用于 `data/base_data_source/adjust.py:34-74` 的序列视图，不进持仓。
  - 结果：账户若在折算日持有该 ETF → 数量不变、原始价 -50%~-79%、权益无声减半，无任何报错。placeholders（`:1110-1141`）只披露"ETF 现金分红不付"与股票 share_transformation 为空，**没有一条覆盖 ETF 份额折算**。
  - P2R6 策略级用调整序列（×fund_adj），不受影响；这是 P3 账户级验证前的硬前置。
- 建议处置：把"ETF split/折算事件源缺失"加入 placeholders 显式披露；P3 前从 fund_adj 折算跳变 + 公告构建 ETF split_factor 行，或在账户引擎禁用含折算标的。

### R3-2 [minor] 退市处理与引擎默认值交互未在模块文档写全

- `mod/rqalpha_mod_sys_accounts/__init__.py:29`：cash_return_by_stock_delisted 默认 True → 退市仓位按最后 last_price 返现，与 P2R6 预登记 U4 口径基本一致（正面）；但 `share_transformation.json` 为空（`rqalpha_bundle.py:1089-1093`）时换股吸收类退市按零对价消失（placeholders 已披露）。另外 fallback 股票（不在 stock_basic 的代码）以"最后一根 bar < 冻结线"推定退市（`:269-274`）——数据尾缺口会被误当退市并在该日按市价清仓返还。minor，需在 manifest 里给出 fallback 代码数与清单。

### R3-3 [minor] ex_cum_factor 微步过滤的声明与实测矛盾：1,003 个真实分红事件无对应因子行

- 证据：模块 docstring `:709-711` 声称"every real A-share cash/股票 dividend moves the factor by >= ~0.1%"；bundle manifest `dividend_row_without_adj_change.count=1,003`（例：600010.XSHG 20180712、600055.XSHG 20150723）——小额分红（<0.1%）因子步被 `min_step=1e-3`（`:711`）抑制。账户现金不受影响（dividends.h5 照付），仅策略级调整序列在这些除息日少计 <0.1% 微步；反向 `adj_change_without_dividend_row=176`（如 600030.XSHG 20220127，送转未配 split 行或源数据噪声），守卫为 reporting-only（`:1004-1023`）。
- 建议处置：docstring 改口为"绝大多数"；把 1,003/176 清单留档；P3 前对 adj_no_div 176 例逐条定性（送转 vs 噪声）。

### R3-4 [minor] NaN 涨跌停回退的实测量级：26,954/约 900 万 bar 行无涨跌停价

- 证据：bundle manifest（`data/processed/rqalpha-bundle-v2-20260917/manifest.json`）：bar_rows_with_nan_limit=26,954（其中 8,360 为停牌行），≈0.3%；rqalpha `utils/price_limits.py` 对非有效价返回 False → 这些日按无涨跌停撮合（乐观）。已知 5 个 header-only 日 + 停牌日缺行构成，已披露、有界。
- 建议处置：维持披露；账户级 run 报告输出"NaN 限价日成交笔数"以便审计。

### R3-5 [minor] 基准指数 bars 仅覆盖 2021-08-05 起，而探针伪装全程覆盖

- 证据：`rqalpha_bundle.py:169-170`（BENCHMARK_CSV 2021-08-05 起）、`:1050-1058`（RANGE_PROBE_OID 用全日历 NaN 行使 `available_data_range` 返回全窗，`data_source.py:402-411`）。账户级 run 在 2015-2021-08 无基准对比且不会报错（静默缺失）；yield_curve 全零、ETF 无 suspended 键已披露。
- 建议处置：补齐 000300 全窗源或在使用文档中声明基准有效区间。

### R3-6 [正面核验] 契约核对通过项（源码逐条对照）

- 日期编码双约定：day-bar/factor 14 位（`adjust.py:54` 直接与 bars['datetime'] searchsorted）、calendar/dividend 8 位（`position_model.py:241-247` convert_date_to_date_int 比较）、split ex_date 14 位且引擎 //1e6 归一（`position_model.py:235`）——bundle 写法全部吻合。
- 分红现金语义：`position_model.py:254` `dividend_cash_before_tax/round_lot` = 每股；bundle `cash_div×100 + round_lot=100`（`:623`）映射正确。同日"先分红（按拆股前数量，`:167,261`）后拆股（数量 ROUND_HALF_UP 放大，`:304-316`）"与 A 股除权除息语义一致。
- ex_cum_factor 只用比值（`adjust.py:43-58`）、`(0,1.0)` 前缀被 `data_source.py` get_ex_cum_factor 过滤后重补——bundle 的 hfq 变化点映射成立（510050 等实例已验证）。
- NaN 限价→无限制（price_limits.py）、storages dtype、instruments.pk 为 dict 列表可被 `load_instruments_from_pkl` 消费、board_type 避开 KSH round_lot=1 分支（`model/instrument.py:90-94`）。
- 冻结线三重检查（`:1144-1151`）；stock suspended 行 close=preclose、volume=0（无 0 值毒化，本审查实测 277,689 行）；ETF 单位 guard（severe=0）；`known_empty_limit_days` 与 manifest zero_row_days 一致。

---

## Target 4：docs/research/exp-20260917-fee-recost.md

### R4-1 [minor] "2023-08-28 及以后卖出的 24,892 笔变差"实为 24,813 笔

- 实测（recost_events.parquet）：变差共 24,892 笔（13.9%）正确，但其中 79 笔退出日在 2023-08-28 之前（最低佣金咬合：名义小于约 3.3 万时旧佣金 min 5 元高于按量的 1.5bp），均值同为 -0.0198pp。结论不受影响；文档归因措辞应改为"其中 24,813 笔为 2023-08-28 后卖出，另 79 笔为小额名义最低佣金咬合"。

### R4-2 [minor] 印花税外推口径已充分披露，标题化表述仍可能被断章

- 第 9 行明确"会低估当年实际费用"，且本审查实测旧口径确为历史分段印花税（implied old stamp 0.001 → 2023-08-28 后 0.0005；旧佣金万 2.5/万 1.5 分段，与文档"旧佣金 1.5bp"一致）——原始 run 的费率模型没有问题，重估是"今日费率反事实"。因毛收益为负主导，"淘汰判定稳健"在外推不成立时同样成立。无实质漏洞；仅建议摘要句避免裸写"用户实况费率整体低于原实验"而不带外推限定。

### R4-3 [minor] 数量冻结与事件独立累计——披露充分，量级已注明

- 实测：mean entry notional 48,849 元（最低佣金咬合仅 59+27 笔）；总量 11,890,583→8,670,890（-27.1%）与文档一致；54 行汇总表与 parquet 重算一致；neg→pos 翻转 0 个（文档"无一处由负转正"成立）；"R2-near52w-dip" 实际 config_id 为 R2-near52w-dip-h5（+0.177→+0.229），文档缩写了 id，引用时注意。

### R4-4 [minor] "+0.19 同池基准"的口径未在本文档写明

- "仍未胜同池基准（+0.19）"——每笔事件均值与基准的每期均值可加性假设应注明出处（R2 报告的对应口径），避免跨口径比较。

---

## 检查过且未发现问题的清单（抽样核验）

1. rqalpha 6.3.0 源码 9 项契约（datetime 双编码、dividend 现金/日期、split 归一与数量舍入、ex_cum_factor 比值语义与前缀、NaN 限价、storages dtype、instruments.pk、available_data_range 探针、delisting 返现默认值）——全部与 bundle 写法一致。
2. standardized parquet 停牌行质量（277,689 行：close=preclose、volume=0、无 0 值）——bundle 无毒化路径。
3. P2R6：PIT 池成员规则逐条对实现（list/delist 界、120 行历史、20 日中位成交额、当日有行情、asof 因子）、月/周信号日定义、留任纪律、gate 过滤位置、T+1、段间结转、test 一次性、12 配置网格完整、net/gross 平行校验（parity check）。
4. fee_recost：逐笔旧费复现、费率反推（旧=万2.5/万1.5 分段佣金+历史印花税；新=万2.5+0.05% 全期）、汇总表、27.1% 降幅、24,892/13.9%、dev +0.052pp/val +0.016pp、neg→pos=0。
5. screen.py：T+1（holding_days≥1）、入口 ST 拒绝（含 null）、涨跌停取整容差、`_affordable_lots` 最低佣金咬合、费率分段按入/出场日取档。
6. etf_rotation：净/毛两路径 trade parity 由运行时强制（`p2r6_etf_rotation.py:216-224`）；执行率、换手、集中度、月度集中度指标的实现与预登记判据映射。

## 最危险的一条（攻击链）

**R2-1 事件研究尾部截断**：涨跌停/停牌 → 退出被阻断 → 标签置空 → "completed only" 均值 → 五轮个股报告与 fee-recost 全部继承一个 +0.1~+0.2pp/笔 的系统性乐观偏置 → 该偏置比已发表的全部费率讨论（+0.05pp）大数倍，且恰好覆盖唯一 dev 转正配置（R2-near52w-dip +0.18→+0.23pp）的全部优势 → 任何以这些均值做横向比较的新实验（包括"距存活门槛还有多远"的表述）都在与一个被截断美化的基线对话。它不推翻"全部淘汰"的终局（反事实更差），但它意味着仓库中所有"每笔净均值"数字在 P3 之前必须以区间口径重述。
