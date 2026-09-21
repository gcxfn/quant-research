# PV1 精测 Codex 运行前审核送审包 第 4 轮（2026-09-10）

审核性质：运行前代码审核第 4 轮（我方 round4 修复）。第 3 轮 2 项阻断修复+主对话复验通过。模块测试 44 项全过；全仓 926 项 OK/1 skip；HOLDOUT_UNLOCKED 保持 False。前包：round3。

## 一、第 3 轮处置（主对话复验）

| 项 | 处置 | 复验 |
|---|---|---|
| ①跨月未成交差额卖单重复冻结并超卖 | `simulate()` 每个调仓执行日开始时**取消全部旧 `pending_trims`/`pending_sells`**（派生自上月目标，跨月即陈旧；取消数以 `trim/sell_cancelled_at_rebalance` 披露），当日卖出循环随即按"当前持仓 vs 新目标"重推导；同股重复挂单由去重断言拒绝（`assert sym not in pending_sells` / trim 同理）。顺带修复同类陈旧性：上月出局受阻、本月重新入榜的股票不再被旧 `pending_sells` 误全卖 | 8 项合成反例（round4_fixes 文件）：(a) Codex 原反例——首月 0.05 受阻跨月，解锁后总卖出=新月差额 0.05 非 0.10，持仓=新月目标，无多余费用；(b) 受阻跨**两个**调仓日，两轮旧挂单全取消只按第三月目标执行一次；(c) 出局受阻→重新入榜不被误卖；(d) 出局受阻→仍出局全卖重挂一次不重复卖 |
| ②一次性候选身份不完整 | `_CODE_DEP_FILES` 扩为 5 路径：quant/history.py、quant/market.py、configs/short-foundation-research.json、data/raw/tushare/trade_cal/20260909-r1/chunk_sse_20180101_20261231.csv、data/history/baostock/stock_basic_20260905.csv（任一读取失败→RuntimeError）；basic manifest 扩为 (code, type, ipoDate, outDate, status) 全字段哈希；`data_version_string` import 失败抛 RuntimeError（静默回退删除）。**收尾代理自查补一处**：`universe_identity()` 新增 `index_daily_sha256`（INDEX_R2_DIR 全部 chunk_*.csv 内容哈希——申万指数日线经 `no_index` 门禁影响 P1 池资格，缺失/空 fail-closed） | 主对话实测 identity：code_sha256 9 文件、universe 三哈希（basic/member/index_daily）齐备；反例：清单文件缺失→RuntimeError、basic 字段变化→哈希变化、data_version import 失败→RuntimeError |

身份语义披露（不变）：任一成分变化=新候选=新的唯一留出窗机会；holdout 台账按候选哈希记账，**至今零消费**。

## 二、in-window 正式重跑（新批次 r4）

`artifacts/pv1-precision/round-20260910-inwindow-r4/`（独占新批次；r3 保留作历史——其顶层 `{"resumed":5546}` 系曾复用缓存，r4 为全新独立运行）。

| 指标 | r3 | r4 | 差异 |
|---|---|---|---|
| 净年化 17bps | +7.6820059% | +7.6820059% | **逐位一致** |
| 月收益 95%CI | [−0.8606834%, +2.6450247%] | 同 | 逐位一致 |
| 27/37bps 年化 | +6.5814% / +5.4916% | 同 | 逐位一致 |
| 月均换手/夏普/MDD | 86.3157% / 0.4349 / −28.50% | 同 | 逐位一致 |

**差异归因（如实披露）**：窗内唯一 `trim_deferred_limit_down_open=1` 在当月末前已成交、未跨调仓日，2020–2023 无跨月受阻样本——超卖 bug 在本窗零触发，修复①为正确性保持（主对话独立核对 r4/r3 的 stats/bootstrap/monthly_returns/turnover JSON 全等）。CI 仍含零，PV1 仍不能证明费用后盈利。

## 三、锁与纪律证据（主对话实测）

- `--mode holdout` 实跑立即 `RuntimeError: holdout locked: HOLDOUT_UNLOCKED is False...`；`holdout_ledger.jsonl` 不存在（0 行）；探测无目录残留。
- 按用户决定 D-2026-09-10-18：留出窗攒批后统一开考，本包审核通过后也**不运行** holdout。
- 测试：`tests.test_pv1_precision_test` + `tests.test_pv1_precision_round4_fixes` 44 项全过（主对话复跑）；全仓 discover 926 OK/1 skip。

## 四、建议审核重点

1. 调仓日"取消旧挂单→按新目标重推导"的完备性（退出/留任/重新入榜三路径与计数器对应）。
2. 身份覆盖边界：quant/backtest.py 未入清单（PV1 未用其撮合引擎，费用模型为本文件自有口径）——是否需要纳入请裁决。
3. r4=r3 的归因口径（无跨月受阻样本）与"r3 为 buggy 代码产物但数字有效"的表述一致性。

## 五、裁决后分岔

PASS → 代码资格冻结（holdout 继续锁，按 D-18 攒批）；CHANGES_REQUESTED → 修复循环。
