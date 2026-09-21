# F2 首轮因子假设批量预登记（exp-20260919-factor-round-f2r1）

**冻结时间：2026-09-19 18:0x（运行前冻结）**

## 0. 定位与用户裁定

- 用户裁定（2026-09-19）："12 个估计全死，120 个吧，多个子代理"——首轮扩至 **120 个因子假设、6 个子代理按族并行**。
- 本轮 = **筛漏斗宽口**：全部 120 个结果一次性报告、无静默淘汰；幸存者仅获 F3 组合候选资格，永久携带 N=120 多重性披露（t≥2 下预期约 6 个纯随机幸存者）；真正的验证在 F3 组合 + band 引擎八门 + 二次过手协议。
- 计账：**因子试验 120 项（F2-R1，独立于策略试验 262 单列台账）**；判据与池看完结果后不得改。
- 引擎无关（本轮纯评估层，F1 harness）；PIT 对齐契约 = `pit_financial`（f_ann_date>ann_date>期末+90 天兜底）；冻结 ≤2024-12-31 全路径断言。

## 1. 统一评估口径（全部因子一致）

- **评估窗 = dev 2015–2020（月频信号，约 71 期）；val 2021–2024 零接触**（留作 F3 后二次过手协议的保留窗；本预登记 2026-09-19 18:05 运行前澄清补钉，未发生任何运行）。
- 评估网格：**月频**（每月最后交易日的信号），前向窗口 h=20 交易日；池 = F1 默认（非 ST、交易中、剔 sh.688*/bj.*、min_history 60）。
- 每因子输出：IC 均值/ICIR/t 值（t=ic_mean/ic_std×√n）/胜率、十分位组均值、多空差、单调性、**逐年 IC（2015 独立）**、覆盖度、top 组换手。
- 数据源全部为 F0 认证的 dev 全覆盖或 PIT 可行清单（`20260919T170000-f0-factor-inputs-main`）；行业中性化不做（index_member_all 单快照前视风险，F0 已披露）。
- 日频因子在月末快照或月末 trailing 窗口计算（公式逐因子冻结于 §3）；财务因子 = 月末时点 PIT 可见的最新报告期。

## 2. 淘汰标准（冻结；双向符号均可过）

一个因子"存活"须同时满足：

1. **|t(IC)| ≥ 2.0**（月频 t 值）；
2. **单调性方向一致且 |monotonicity| ≥ 0.3**（sign(mono)=sign(ic_mean)）；
3. **2015 非灾难**：非（sign(IC₂₀₁₅)=−sign(IC 总) 且 |IC₂₀₁₅|>0.03）；
4. **覆盖**：横截面中位符号数 ≥ 全合格池月度中位的 50%。

未存活 ≠ 因子死亡声明——只是本轮不入 F3；全部数字留档。

## 3. 因子目录（120 = A25 + B15 + C20 + D30 + E20 + F10；公式即冻结定义）

### A 量价族（25；v0 面板+preclose 链复权）

| ID | 名称 | 公式（t=月末；窗口=交易日） | 理由 |
|---|---|---|---|
| A01 | mom_20 | adj_ret(t−20,t) | 短期动量/惯性 |
| A02 | mom_60 | adj_ret(t−60,t) | 中期动量（JT 经典） |
| A03 | mom_120 | adj_ret(t−120,t) | 长期动量 |
| A04 | mom_240 | adj_ret(t−240,t) | 年度动量 |
| A05 | mom_20sk5 | adj_ret(t−20,t−5) | 短窗跳空动量（隔日噪声） |
| A06 | mom_60sk20 | adj_ret(t−60,t−20) | 中窗跳月动量 |
| A07 | mom_12_1 | adj_ret(t−240,t−20) | 12−1 月动量（经典规格） |
| A08 | rev_1 | adj_ret(t−1,t) | 隔日反转 |
| A09 | rev_5 | adj_ret(t−5,t) | 周反转（A 股经典强效应） |
| A10 | rev_10 | adj_ret(t−10,t) | 双周反转 |
| A11 | vol_20 | std(day_ret,20) | 短期波动（低波动异象） |
| A12 | vol_60 | std(day_ret,60) | 中期波动 |
| A13 | vol_ratio | std(20)/std(120) | 波动聚集变化 |
| A14 | amp_20 | mean((H−L)/C,20) | 振幅（博彩性代理） |
| A15 | range_pos_60 | (C−min60)/(max60−min60) | 区间位置 |
| A16 | dist_52wH | C/max(C,252)−1 | 52 周高点距离（锚定效应） |
| A17 | liq_amt20 | ln(mean(amount,20)) | 流动性规模 |
| A18 | liq_ratio | mean(amt,5)/mean(amt,60) | 流动性突变 |
| A19 | amihud_20 | mean(|day_ret|/amount,20)×1e9 | Amihud 非流动性 |
| A20 | pv_corr_20 | corr(C,vol,20) | 量价相关性 |
| A21 | vol_updown | Σvol(涨日)/Σvol(跌日)，20 | 资金方向偏斜 |
| A22 | vol_trend | mean(vol,5)/mean(vol,60) | 量能趋势 |
| A23 | sma20_gap | C/SMA20−1 | 均线乖离 |
| A24 | sma60_gap | C/SMA60−1 | 长均线乖离 |
| A25 | days_hi60 | t−argmax(C,60) | 距高点天数（趋势新鲜度） |

### B 估值/规模族（15；daily_basic 月末快照/窗口）

| ID | 名称 | 公式 | 理由 |
|---|---|---|---|
| B01 | ln_tmv | ln(total_mv) | 规模效应 |
| B02 | ln_cmv | ln(circ_mv) | 流通规模 |
| B03 | circ_ratio | circ_mv/total_mv | 供给结构 |
| B04 | ep_ttm | 1/pe_ttm | 价值（盈利收益率） |
| B05 | bp | 1/pb | 价值（账面市值比） |
| B06 | sp_ttm | 1/ps_ttm | 价值（销售市值比） |
| B07 | dv_yield | dv_ratio | 股息率 |
| B08 | ep_static | 1/pe | 静态盈利收益率 |
| B09 | turn_20 | mean(turnover_rate,20) | 换手水平（情绪/流动性） |
| B10 | turn_60 | mean(turnover_rate,60) | 长窗换手 |
| B11 | turn_vol20 | std(turnover_rate,20) | 换手波动 |
| B12 | turn_abn | mean(turn,5)/mean(turn,120) | 异常换手 |
| B13 | ep_bp | rank(ep_ttm)+rank(bp) | 双价值复合 |
| B14 | small_value | rank(−ln_tmv)+rank(bp) | 小盘价值复合 |
| B15 | mv_ret20 | tmv(t)/tmv(t−20)−1 | 市值动量（含增发噪声，披露） |

### C 微观结构族（20；竞价/资金流/涨跌停/九转；字段名以实际列映射并在交付披露）

| ID | 名称 | 公式 | 理由 |
|---|---|---|---|
| C01 | auct_prem20 | mean(open/preclose−1,20) | 竞价溢价（隔夜需求） |
| C02 | auct_premstd | std(open/preclose−1,20) | 竞价分歧 |
| C03 | auct_volr20 | mean(竞价量/当日量,20) | 竞价参与度 |
| C04 | mf_net20 | mean(主力净流入/成交额,20) | 主力资金流向 |
| C05 | mf_net5 | mean(主力净流入/成交额,5) | 短窗资金 |
| C06 | mf_mom | mf_net5−mf_net20 | 资金加速 |
| C07 | buy_r20 | mean(买方总额/成交额,20) | 主动性买占比 |
| C08 | sell_r20 | mean(卖方总额/成交额,20) | 主动性卖占比 |
| C09 | lgbuy_r20 | mean(大单买/成交额,20) | 大单买入 |
| C10 | lgsell_r20 | mean(大单卖/成交额,20) | 大单卖出 |
| C11 | lim_dist_up | mean(C/涨停价,20)−1 | 涨停距离 |
| C12 | lim_dist_dn | mean(C/跌停价,20)−1 | 跌停距离 |
| C13 | lim_up20 | count(C==涨停价,20) | 涨停频次（博彩性） |
| C14 | lim_up60 | count(C==涨停价,60) | 长窗涨停 |
| C15 | td_setup | 月末九转字段原值 | TD 序列位置 |
| C16 | td_sum20 | sum(九转字段,20) | TD 强度 |
| C17 | mf_skew20 | skew(日主力净流入比,20) | 资金偏斜 |
| C18 | auct_premmom | 竞价溢价 5 日−20 日 | 竞价动量 |
| C19 | cls_str20 | mean((C−L)/(H−L),20) | 收盘强度 |
| C20 | cls_str60 | mean((C−L)/(H−L),60) | 长窗收盘强度 |

### D 财务 PIT 族（30；fina_indicator+三表，pit_financial 对齐，月末取最新可见报告）

| ID | 名称 | 公式 | 理由 |
|---|---|---|---|
| D01 | roe | fina roe | 盈利质量 |
| D02 | roa | fina roa | 资产回报 |
| D03 | gm | grossprofit_margin | 毛利率护城河 |
| D04 | nm | netprofit_margin | 净利率 |
| D05 | debt_assets | debt_to_assets | 杠杆风险 |
| D06 | cur_ratio | currentratio | 短期偿债 |
| D07 | ocf_opinc | OCF/营业收入 | 现金流质量 |
| D08 | ocf_roa | OCF/总资产 | 现金回报 |
| D09 | eps | 最新 eps | 每股盈利 |
| D10 | bps | 每股净资产 |
| D11 | rev_yoy | 营收同比（fina 或自算） | 成长 |
| D12 | np_yoy | 净利同比 | 成长 |
| D13 | roe_d | roe−roe(去年同期) | 盈利改善 |
| D14 | gm_d | gm−gm(去年同期) | 毛利改善 |
| D15 | accruals | (NI−OCF)/总资产 | 应计异象 |
| D16 | ep_roe | rank(ep)+rank(roe) | 便宜且好 |
| D17 | quality | rank(ocf_opinc)+rank(−debt) | 质量复合 |
| D18 | asset_turn | 营收/总资产（年化） | 运营效率 |
| D19 | ocf_yoy | OCF 同比 |
| D20 | rev_q_yoy | 单季营收同比（累计差分） | 单季动量 |
| D21 | np_q_yoy | 单季净利同比 | 单季动量 |
| D22 | roe_ttm | 4 季滚动 ROE |
| D23 | gm_ttm | 4 季滚动毛利 |
| D24 | eps_dq | eps−eps(上季) | 环比改善 |
| D25 | debt_d | debt_assets−去年同期 |
| D26 | eq_mult | 资产/权益 |
| D27 | tangible | (资产−无形−商誉)/权益 |
| D28 | sga_r | 销售+管理费用/营收 | 费用纪律 |
| D29 | nonrecc | (NI−扣非NI)/|NI| | 非经常损益占比 |
| D30 | ocf_ps | 每股 OCF |

### E 事件族（20；ann_date→月末聚合窗；全部 PIT）

| ID | 名称 | 公式 | 理由 |
|---|---|---|---|
| E01 | fcst_np | 120d 内最新预告 (p_change_min+max)/2 | 业绩预告方向 |
| E02 | fcst_np_max | 最新预告 p_change_max | 预告上限 |
| E03 | fcst_rev | 同期最新−首个预告中值 | 预告修正 |
| E04 | fcst_cnt120 | 120d 预告次数 | 信息密度 |
| E05 | fcst_fresh20 | 20d 内有预告(0/1)×方向 | 新鲜预告 |
| E06 | expr_rev_yoy | 最新快报营收同比 | 快报确认 |
| E07 | expr_surp | 快报净利/同期预告中值−1 | 预告兑现差 |
| E08 | repo_120 | 120d 回购金额/流通市值 | 回购信号 |
| E09 | repo_ann20 | 20d 有回购公告(0/1) | 新鲜回购 |
| E10 | hb_net120 | 120d 增持净比例 | 内部人买入 |
| E11 | hs_net120 | 120d 减持净比例 | 内部人卖出 |
| E12 | hb_key60 | 60d 关键股东净增持 | 关键人信号 |
| E13 | float_fwd60 | 已公告未来 60d 解禁比例 | 前瞻解禁压力 |
| E14 | float_past20 | 过去 20d 已解禁比例 | 已落地压力 |
| E15 | div_ex20 | 20d 内除息每股股利/收盘 | 分红事件 |
| E16 | div_yld120 | 12m 滚动股利/价格 | 分红收益 |
| E17 | fcst_sign120 | Σsign(预告中值),120d | 方向累计 |
| E18 | expr_cnt120 | 120d 快报次数 |
| E19 | hb_ann20 | 20d 增持公告数 | 新鲜增持 |
| E20 | float_press | 未来 120d 已公告解禁/流通市值 | 中期压力 |

### F 横截面/组合特征族（10；含指数对冲）

| ID | 名称 | 公式 | 理由 |
|---|---|---|---|
| F01 | beta_60 | vs 上证综指 60d β | 市场暴露 |
| F02 | beta_240 | 240d β |
| F03 | resid_mom120 | β 对冲残差 120d 收益 | 残差动量 |
| F04 | dvol_60 | 60d 下行波动（仅负日） | 下行风险 |
| F05 | mdd_120 | 120d 最大回撤 | 路径风险 |
| F06 | skew_60 | 60d 偏度 | 彩票偏好 |
| F07 | kurt_60 | 60d 峰度 | 尾部风险 |
| F08 | overnight20 | mean(open/preclose−1,20) | 隔夜收益分解 |
| F09 | intraday20 | mean((C−open)/preclose,20) | 日内收益分解 |
| F10 | idio_vol60 | 60d 残差波动 | 特质风险 |

## 4. 执行拓扑（6 子代理并行；每代理一族）

- 每代理：读冻结预登记与 F0 报告 → 建族子目录 `artifacts/runs/20260919T180000-f2r1-factor-batch/outputs/<族>/` → 按冻结公式计算因子表（月末网格）→ 逐因子跑 `evaluate_factor`（h=20，月频，F1 默认池）→ 每因子一份 JSON + 因子帧 parquet（F3 复用）→ 族交付报告（含 C 族字段映射披露、D 族 PIT 覆盖率与 90 天兜底比例）。
- 主对话：验收（抽因子复算、口径核对）、汇总 120 结果、按 §2 淘汰标准出存活名单、台账记 120 因子试验、多重性披露。
- 预算：每代理 ≤60 分钟；数据只读；中文 Write 工具；无 git；零策略回测。

## 5. 风险预登记

1. 120 重多重性：t≥2 预期 ~6 个随机幸存者（若检验正相关则更多）——幸存名单永不称"已验证因子"。
2. C 族字段映射依赖实际列名（竞价/资金流口径以数据为准，映射入交付）；E 族部分事件早期覆盖薄，覆盖率如实报告并在淘汰标准 4 卡关。
3. D 族 2015 年初可见报告依赖 2014 年报（4 月底前 2014 年报未披完）——2015 上半年覆盖天然偏低，逐年 IC 已单列。
4. 涨跌停/停牌日收益照算（F1 已知限制）；执行层过滤留给 F3。
5. 同族因子高度相关（如 B04/B05/B13）——存活名单按簇解读，F3 组合前先做相关性去重。
