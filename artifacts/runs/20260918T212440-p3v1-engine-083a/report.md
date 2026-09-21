# P3 v1 区间契约引擎 · 交付报告

- 运行：`20260918T212440-p3v1-engine-083a`
- 引擎：`src/quant/backtest/band_engine.py`（v1，sha256 见 manifest）
- 契约：`docs/plans/p3-band-contract.md` §7（v1 冻结 2026-09-18）
- 状态：**completed** · 21/21 测试通过 · 零试验消费 · 零策略运行

## v0→v1 diff 摘要

v1 = v0 §1 全部语义 + §7 修正；冲突以 §7 为准。核心变更：
1. 半日限价单（每单恰好一个 session）
2. 双决策点（11:30/15:00 对称）
3. 穿透 bar：半日极值（官方日线保守子集）
4. clip 级持仓（FIFO 消费、取得日 T+1/T+0）
5. session 级结算（am→pm 当日 / pm→次日 am）
6. intent=risk K=3 session 兜底 / intent=profit 静默失效
7. is_etf（免印花）/ is_t0 品种旗标
8. 单票 25% cap（决策点快照）+ 总 100%（全额资金隐含）
9. 官方日线 close 做估值 mark（桥接断言 2018-08-20 分界）

## 测试（21/21 通过）

详见 `logs/pytest.log`。覆盖 §7 全部新语义 + v0 十项验收意图保留。

## 手算样例

4 例全部硬断言通过，详见 `hand-calc-samples.md`。

## 数据桥接核查

- 行数 18,486,939，pre-cutoff pm.close ≠ 官方 close 2,870,381 行（~32%，登记原因 pm.close 不可做 mark/anchor）
- post-cutoff pm.close ≠ 官方 close 1,824 行（≈0.02%，集合竞价 vs 分钟聚合口径差，容差 0.011）
- 半日极值超出官方日线范围 3 行（数据质量披露，非引擎缺陷）
