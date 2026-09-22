# 决策：FIFO 消耗与「逐批风险意图」错配的处置（C4-DEF-01）

日期：2026-09-22｜性质：语义裁定（只读调查，不改码）｜状态：已裁定，文档化关闭

## 背景

C2 独立参考账本按合同（`p3-band-contract.md` §7.7-m2）以**取得日 FIFO**消耗持仓批次复算，
与主引擎一致；但策略层 `single_name_rules.py` 按**逐 clip** 维护止损线 R 与保护线。
C2 把它登记为 `C2-OBS-04`（INFO）转 C3；C3 逐 clip 对照写入 `clip_exit_trace.csv`
（59 行），登记为 `C3-OBS-03`（MINOR）并转 C4 出处置结论。

措辞上的担心是：「某批次的风险线已被穿越，但 FIFO 卖的是另一批次」是否让**数量**或
**风险语义**失真。

## 调查（证据）

1. **策略侧风险退出不是逐 clip 数量**。`src/quant/research/single_name_rules.py` 头部冻结语义
   与 `decide()` 实现：止损/保护线**任一 clip 触发即整仓退出**（whole-exit，
   `target_shares=0`，row 不带 `target_weight`/`target_notional`），引擎对 risk 类无数量字段的
   卖单按**全部可卖量**成交。因此「逐批风险线」只用于**触发判定**，不产生逐批数量委托。
2. **唯一的逐 clip 数量阶梯是 +2R 分批止盈，且它是绝对总股数量目标**。
   `_half_keep_target()` 用触发 clip 的初始股数折算保留量，`keep_shares` 累加为**整仓目标**
   （`_row(..., target_notional=keep_shares*px)`）；模块头部明文：「an absolute target also
   makes a FIFO fill that consumed a DIFFERENT clip harmless: the target is total-share based,
   so the rule never re-counts per-clip keeps and oversells」。
3. **真实 run 无超卖**。独立复算 B1 主 run 全部 46 笔卖出（`B1_fills.parquet`）与逐笔重建的
   当时持仓：`oversell_count = 0`；35 笔整仓卖出 + 11 笔部分卖出（7 笔 risk 类 + 4 笔 profit 类）。
   部分 risk 卖出来自 **D3 账户降档的持仓级减仓**（`risk_overlay_runner.py` 合成行带
   `target_weight`、`trim_intent="risk"`），不是逐批风险委托。
4. **引擎消耗口径**：`band_engine.py` `book_sell_fill` 对 `consume` 列表逐 clip 扣减
   （取得日 FIFO），对带显式数量的 risk 单按 `min(order_shares, sellable)`；`_Clip.seq` 仅作
   FIFO 平局身份，不影响总量。
5. 模块头部已把该性质列为**已知引擎级属性并披露**（「the surviving lot composition can differ
   (a later whole exit of the symbol is unaffected; a later clear covers whatever clips remain)」）。

## 裁定

**保持 FIFO，不改撮合、不改策略；语义文档化关闭。** 理由：

- 本策略**不存在逐批数量级风险退出原语**：风险退出整体清仓，分批止盈是整仓绝对目标；
  FIFO 只改变**剩余批次构成**，不改变成交总量、不产生超卖、不改变「止损=清仓」的风险含义。
- 剩余批次构成的差异有界且已披露：后续整仓退出覆盖全部剩余批次；后续 clear 覆盖剩余批次；
  每个 clip 的分档止盈仍按自身 cost/R 触发，不会对同一 clip 重复计数（`half_done` 标记）。
- 需要重新表述的不是代码，而是**结论口径**：任何依赖「逐批风险」的旧表述应读作**聚合持仓**
  风险口径。C4 起研究文档按此口径表述（`claim_correction_log.csv` 无独立行，因该结论未在
  已发表结果中被引用；本文件为口径来源）。

## 边界（未主张）

- 不主张 FIFO 构成等同于「按意图批次」的构成；差异存在且已披露。
- 不新增第二条退出路径，不为该错配引入逐批撮合原语（主计划禁止为假想需求扩构建）。
- 若未来策略引入**逐批**风险卖单（对指定 clip 数量退出），则需重新评估并新开预登记。

## 证据路径

- `src/quant/research/single_name_rules.py`（模块冻结语义 §stop/exits + `decide()`）
- `src/quant/research/risk_overlay_runner.py`（D3 trim 行带 `target_weight`）
- `src/quant/backtest/band_engine.py` `book_sell_fill` / `_Clip`
- `docs/evidence/trust-rebuild/20260922T051244-trust-c4-c4fc42/c4def01_fifo_analysis.py` 与 `.json`
- `docs/evidence/trust-rebuild/20260922T035220-trust-c3-c8af13/clip_exit_trace.csv`、
  `c3_case_report.md` §5.5
