# ETF 腿标准化与辅助数据盘点 — 质量报告

- run_id: `20260919T041100-etf-standard-0a6b`
- 日期: 2026-09-19 · 状态: completed · 耗时 ~3s · 离线（无网络访问）
- 输出: `data/processed/etf-daily-20260919/`（manifest.json / quality.json / daily_2015_2024.parquet / pool.parquet / adj_factor_coverage.parquet / adj_factor_missing.csv / preclose_mismatch_detail.csv）
- 输入批次（只读）: `data/raw/tushare/fund_daily/20260917-r1/`、`data/raw/tushare/fund_adj/20260917-r1/`（用户 2026-09-19 批准为 ETF 腿主源）

## 1. 标准化结果（任务一）

| 项 | 值 |
|---|---|
| 输入行数 | 1,017,121（= 批次 manifest 逐文件行数合计，1,169 个 chunk 全部 sha256 复核一致） |
| 输出行数 | 1,017,121 |
| 2025+ 行 | 输入 0、输出 0（输入批本身就是 20150101..20241231 拉取；读取层仍做了防御性过滤并断言） |
| 窗口边界 | date_min = 2015-01-05，date_max = 2024-12-31；pool 逐标的 first/last 全部在窗内（断言通过） |
| 重复 (symbol,date) | 0 |
| 空值 | 0 |
| 标的数 | 1,169（与 fund_basic universe 过滤重算结果逐一对齐） |

- **schema 对齐**: `symbol = sh.XXXXXX / sz.XXXXXX`（与股票腿 `data/processed/baostock-daily-20260917` 完全一致）；`date` 为 Date；`open/high/low/close/preclose/volume/amount` 均为 Float64。列集合 = 股票腿核心 9 列；tushare 的 `change/pct_chg` 未带入（可由 close/preclose 推导，manifest 已注明）。
- **单位复核（vwap 检验）**: volume = vol[手]×100 股、amount = amount[千元]×1000 元。1,017,121 行逐行隐含 vwap∈[low,high] 检验：越界 9,172 行（0.90%），其中小额(<1k元) 3,336、单一路径日 8,094、<100 元"粉尘日" 326；剔除 1 元取整粉尘后严重越界 = **0**。单位结论与 rqalpha-bundle-v2-1 的既有验证一致，无单位错误。
- **退市 ETF 末段覆盖**: 状态 D = 128 只（与批次口径一致）；其中 delist_date 落在 2015–2024 的 116 只、2025+ 的 11 只（其行情止于 2024-12-31，冻结纪律天然覆盖）、无 delist_date 的 1 只。窗内退市 116 只的 last_trade 相对 delist_date 差：p50 = -48 天（长期停牌后退市所致）、min = -770 天、max = -1 天，全部如实截断、无退市后行。
- **复权因子覆盖**: 1,169 只中 1,167 只全覆盖；**缺失清单**（`adj_factor_missing.csv`）：
  - `sz.159842` 全缺（920 行）——输入批 known gap（fund_adj 拉取时空结果），如实登记；
  - `sh.502056` 部分缺（2,252 行中缺 1,200 行，2015-07-31 起；2020 年后才有因子且恒为 1.0）。
  - 窗内因子跳变事件（分红/份额折算）共 ~数百次（>1% 的跳变见 quality.json）。
- **preclose 一致性**: 1,015,952 对可比较中 495 对（0.0487%）preclose(t) ≠ close(t-1)，涉及 200 只。其中 **409 对与当日复权因子跳变对齐**——即除息/份额折算日交易所发布的除权参考价（最大偏差如 511030 2021-01-11 的 10:1 份额折算，abs diff 91.499、factor_ratio≈9.9），属预期语义而非数据错误；其余 86 对无当日因子跳变（如 511230 两次 -1.3%、159919 2019-01-14 -9.98%），已在 `preclose_mismatch_detail.csv` 附 factor_ratio 供逐日审计，**未做修饰**。使用建议：跨日收益一律走 fund_adj 因子，不要用 preclose 直连。

## 2. ETF 池与类别（保守规则）

`pool.parquet`：1,169 行，含 symbol、name、list_date、delist_date、traded_in_window、first/last_trade_date、trade_days、asset_class 及 tushare fund_type/invest_type（参照列）。类别规则 = 代码前缀 + 名称关键词（优先级 money→bond→commodity→cross_border→equity→unknown），完整关键词表与护栏写进 processed manifest 的 `asset_class_rules`：

| asset_class | 数量 | 与 fund_type 交叉 |
|---|---|---|
| equity | 940 | 全部 股票型 |
| cross_border | 151 | 全部 股票型 |
| money | 30 | 全部 货币型 |
| bond | 29 | 全部 债券型 |
| commodity | 19 | 全部 其他型（黄金/上海金/期货类） |
| unknown | 0 | — |

护栏要点：黄金产业**股票**ETF（6 只）判 equity 而非 commodity；"商品"一词不入关键词（上证大宗商品股票ETF 是股票型）；标普/国际等词会造成 A 股误判，改用 QDII 标记与限定词。本表仅规则判类，**不做精确认证**。

## 3. 辅助数据盘点（任务二，gaps.json）

1. **ETF 涨跌停价**：`stk_limit/20260917-r1`（2,431 个日文件）**不含任何基金代码**（51/56/58/15/16 前缀命中 0 行，全批仅股票/北交所/B 股前缀）。rqalpha-bundle-v2-1 生成器已明示该缺口：ETF limit_up/down 全为 NaN（rqalpha 语义=无涨跌停约束）。混合族回测若要 ETF 涨跌停门槛，只能沿用已登记的 9.5% 带宽代理或新增拉取批次（本轮不拉新数）。**= 缺口**
2. **ETF 公司行动**：bundle v2-1 中 `funds.h5` 1,169 只 ETF 日线、`ex_cum_factor.h5` 1,169 只（2,746 段，源自 fund_adj 比值）、`split_factor.h5` 76 只/90 行（fund_adj 单日比值 ≥1.1 或 ≤0.9 折算的"份额折算"行）、**`dividends.h5` 0 只 ETF**（ETF 现金分红完全缺失，bundle 也披露"ETF cash stays unpaid"）。fund_adj 因子**能替代**：跨分红/折算的持期收益调整、折算检测；**不能替代**：分红现金台账（无金额、无除息/派息日）→ ETF 分红的现金守恒校验在盘上数据下不可完整执行。**= 缺口（现金分红）**
3. **ETF 费用口径**：已登记，出处——`configs/experiments/p2r6-etf-rotation.json` 第 284–291 行（commission_pct 0.0001 万1、commission_min 5.0、stamp_sell_pct 0.0、tick_registered_only 0.001，disclosure 注明万1+min5 为用户账户实际、免印花与 tick 为机构事实、零滑点为研究假设）；`configs/experiments/p2r7-etf-exposure.json` 第 213–220 行逐字继承。**= 无缺口**
4. **风险腿候选可用性**（全窗 = 2015-01-05 前上市、2024-12-31 仍在、区间内相对对应交易所日历 0 缺失日）：
   - **bond 全窗连续：仅 `sh.511010` 国泰上证5年期国债ETF（2,431/2,431 日）**。其余 28 只均为 2017-2024 间上市（511260 缺 1 日、511270 缺 4 日等），不能全窗。
   - **commodity 全窗连续：4 只黄金 ETF**——`sh.518800`、`sh.518880`、`sz.159934`、`sz.159937`（各 2,431/2,431 日）。豆粕/有色/能化期货 ETF 与上海金系列均 2019 年后上市，不能全窗。
   - 混合族预登记若需要"全窗连续"的风险腿，bond 腿目前只有 511010 单一代表（期限单一，缺 10 年/30 年段），这是结构性的样本内限制，须写进预登记。

## 4. 跨源复核（sina / tx，声明：同目标跨源复核，非独立验证）

抽样 sh.510050（equity、有分红）、sh.518880（commodity）、sz.159915（equity），比较窗 2015-01-05..2024-12-31，全部交易日均入比（join 率 100%）：

| 标的 | sina 不复权收盘 | tx 前复权收盘 |
|---|---|---|
| sh.510050 | 一致率 99.753%（2,431 中 6 日差 1–3 tick，max 0.003） | 原始一致率 0%——tx 序列为**日度连续复权价**（比值 0.73→0.97 漂移，与 1/fund_adj 相关 -0.96；9 个 fund_adj 跳变日 9/9 落在 tx 比值变动日内），分红再投资口径，与不复权价逐点不可比，不作为一致率证据 |
| sh.518880 | 一致率 100%（max diff 0） | 一致率 100%，比值恒 1.0（无分红） |
| sz.159915 | 一致率 99.959%（仅 2020-02-25 差 1 tick） | 原始一致率 99.918%，主水平 1.0 覆盖 2,428/2,430 日；其余 2 日为 ±1 tick 级噪声 |

- 结论：**sina 与主源高度一致**（≥99.75%，残差全部 ≤3 tick）；tx 对无分红标的完全一致，对分红标的属于不同复权口径（非数据错误），故只用 sina 作不复权等价证据。
- 有趣的一条：159915 在 2020-02-25 上 tushare 比 sina、tx 双双低 1 tick——单 tick 级、无研究影响，登记备查。
- 声明：sina/tx 与 tushare 可能同源于交易所行情，本复核证明的是"同一目标的跨源一致性"，**不是独立验证**。

## 5. 纪律与限制

- `data/raw` 全程只读；未联网；未修改 docs/configs/src；未做 git 操作；临时文件仅在运行目录 `tmp/`（本次实际未产生临时文件）。
- 主要限制：单一上游（tushare）出价与因子；159842.SZ 无因子、502056 前段无因子；ETF 分红现金台账缺失；ETF 真实涨跌停价缺失；asset_class 为规则判类非认证；2025+ 冻结未动。

## 6. 复现命令

```bash
D:/量化/.venv/Scripts/python.exe artifacts/runs/20260919T041100-etf-standard-0a6b/scripts/standardize_etf_daily.py
D:/量化/.venv/Scripts/python.exe artifacts/runs/20260919T041100-etf-standard-0a6b/scripts/etf_aux_inventory.py
D:/量化/.venv/Scripts/python.exe artifacts/runs/20260919T041100-etf-standard-0a6b/scripts/crosscheck_sina_tx.py
```
