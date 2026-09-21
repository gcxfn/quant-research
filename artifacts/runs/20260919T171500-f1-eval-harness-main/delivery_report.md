# F1 因子评估 harness 交付报告（主对话实施）

- run：`artifacts/runs/20260919T171500-f1-eval-harness-main/`；性质：**纯代码建设**（零试验、零选因子证据）；执行链披露：F1 实施代理死于基础设施（Captcha 启动期，零残留）后由主对话亲自实施。
- 交付物：`src/quant/factors/eval.py`（新模块）+ `tests/test_factors_eval.py`（12 项测试）+ 本目录集成冒烟产物。

## 一、模块 API（`src/quant/factors/eval.py`）

1. **`FactorEvalConfig`**（frozen dataclass）：`horizon_days`（前向窗口交易日数，默认 10）、`n_groups`（默认 10）、`eval_freq`（"D"/"M"）、池过滤（`exclude_st`/`require_trading`/`exclude_boards`——科创板 sh.688 与北交所 bj. 前缀剔除，创业板保留）、`min_history_rows`（默认 60）；`__post_init__` 校验；`canonical()` 输出缓存键成分。
2. **`evaluate_factor(factor, panel, cfg, *, others)`**：因子表 `(symbol, signal_date, value)` → 统计字典：
   - 逐期 Spearman IC（平均秩 Pearson）→ `ic_mean/ic_std/icir/ic_win_rate`；
   - 分位数组（rank-qcut，组 1=低值）→ `group_mean_ret`（低→高）、`long_short_mean`、`monotonicity`（组序 vs 组均收益 Pearson）；
   - **逐年分解 `ic_by_year`/`long_short_by_year`（2015 独立键）**；
   - `coverage_mean_symbols`、`turnover_top_group`（top 组相邻期成员变动）；
   - `corr_with_others`（与传入其他因子表的横截面 Spearman 均值——防重复计数）；
   - `config`（冻结配置回显）。
3. **对齐口径（核心契约）**：`signal_date t` 的因子 → 前向收益 = `t+1..t+h` 交易日的 `close/preclose` 复合；**信号日当日收益永不入窗**（有专门测试钉死）；preclose 为交易所参考价（公司行动已内含，无需复权因子）；窗口不完整（t+h 行不存在）或 t 为面板末行 → 丢弃不填补。
4. **`pit_financial(events)`**：tushare 财务/事件行 → `(symbol, signal_date, end_date)`；每 `(ts_code, end_date)` 取 `ann_date` 最晚行（修正稿胜出）；`signal_date = f_ann_date 优先，缺则 ann_date，双缺则期末+90 天兜底`（`used_90d_fallback` 布尔列可查比例）；符号风格转面板风格（600519.SH→sh.600519）。
5. **`eval_cache_key(factor_meta, panel_sha256, cfg)`**：SHA-256 缓存键 = 因子身份+面板 sha+评估参数+冻结端点（AGENTS §5.4；F2 运行层据此持久化）。
6. **冻结纪律**：`FREEZE_END=2024-12-31`；因子 signal_date、面板 date 超 freezing 立即抛 `FactorEvalError`；空网格/无有效 IC 期均显式报错不静默。

## 二、测试（12/12 通过；全仓 432 通过零回归）

| # | 测试 | 钉死内容 |
|---|---|---|
| 1 | rank_ic_exact_and_alignment | 手算分组均值/多空/单调性；窗口=第 2、3 天（非第 1、2 天）——泄漏陷阱数字级钉死 |
| 2 | alignment_uses_next_day_window | 均值回归行情下"当日收益因子"IC=−1（若同日泄漏会得 +1） |
| 3 | forward_return_compound_from_preclose_chain | 两日复合 1.10×1.05−1=0.155 手算；单符号 IC 未定义走护栏报错 |
| 4 | freeze_breach | 因子/面板任一 2025+ 日期 → 报错 |
| 5 | pool_filters_st_halt_board | ST/停牌/科创板/北交所成员不入截面（覆盖数=3 精确断言） |
| 6 | yearly_breakdown_has_2015_key | 2015 独立年份键 |
| 7 | month_end_frequency | 月频只取每月最后交易日（两月 → 2 期） |
| 8 | turnover_hand_case | 排名逐期翻转 → turnover=1.0 手算 |
| 9 | pit_financial_dedup_priority_and_fallback | 修正稿胜出、f_ann_date 优先、90 天兜底计数 |
| 10 | config_validation_and_cache_key_stability | 非法配置报错；缓存键对参数/面板 sha 敏感且可复现 |
| 11 | duplicate_factor_keys_rejected | 重复 (symbol, signal_date) 拒绝 |
| 12 | corr_with_others | 与反向因子相关 = −1 手算 |

实施过程中主对话自查修掉三处实现缺陷（反向累乘 over() 对齐、截断窗口误补 1.0、shift 方向反）与一处 API 兼容（polars 1.44 `str.strip_chars`）——全部由测试暴露后修复，测试先行钉死行为。

## 三、集成冒烟（工程验证，非选因子证据）

- 输入：真实 v0 面板（sha 前缀入产物）、50 随机符号（seed 20260919）、月频 116 期、**种子化伪随机因子**（无任何预测内容）。
- 结果：IC_mean=−0.016（≈0——随机因子不得显示技能，这本身就是泄漏检查通过的证据）、十年 IC 键齐全、随机因子换手 0.88（高换手合理）、0.5 秒。
- 产物：`f1_integration_smoke.py` + `outputs/f1_integration_smoke.json`；标注 "engineering validation only — NOT selection evidence, zero trials"。

## 四、已知限制（F2 预登记须继承）

1. 涨跌停/停牌日的收益照算、分组照排（执行可行性留给 F3 band 引擎判定——与既有死因记录一致）；
2. 池过滤用面板字段（isST/tradestatus/上市历史深度），板块过滤按符号前缀；历史时点 ST 以面板当日 isST 为准；
3. `others` 相关性为横截面 Spearman 的时间平均，非因子正交化；
4. index_member_all 单快照问题（F0 披露）未在本层解决——行业类因子在 F2 须自行披露该限制。

## 五、试验计账

零试验消费（代码建设+冒烟）；F2 起每个预登记因子的评估计入因子试验台账。
