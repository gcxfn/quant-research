# 派生 Runner：账户级风险 overlay 接入 band_engine

本次只新增派生接入层，没有修改历史 F3R2 runner、F3R2 artifacts 或
`src/quant/backtest/band_engine.py`。

代码入口是 `src/quant/research/risk_overlay_runner.py`，可执行 smoke 是
`tools/overlay_runner_contract.py`。它把 `risk_overlay.resolve_overlay()` 的
机器行转换为 band engine 的 intent 重挂目标：攻击袖套的目标权重按
`E / 0.90` 缩放，防御标的不动；完整卖出（`target_weight=null`）保持完整卖出。

## 已完成

- C0：控制组使用 `E=0.90`，与 F3R2 已登记的基准权重恒等映射；harness 会运行未修改的
  `run_band_backtest_intents()`，并可与参考 `BandResult` 的 fills/events/daily/clips_final
  逐帧比较。
- C1：支持提供完整的决策点和 `000300` 收盘序列，按登记的 as-of、SMA、恢复确认和冷却规则
  生成 overlay 行，并在攻击持仓仍有有效目标时发出后续决策点的目标重挂。
- C2：支持生成带账户回撤状态的计划对象；2026-09-21修复后，一次性执行入口始终拒绝C2，
  即使传入确认标志或将动态元数据置假也不能绕过。动态账本反馈入口尚未实现。

## 未宣称的部分

C2 的完整动态回放是路径依赖的：下一决策点的权益来自上一段 band engine 成交、费用、T+1
持仓和官方收盘估值，不能把历史基准曲线一次性塞给 overlay 后称为动态结果。当前模块保留了
计划和 fail-closed 接口，尚未实现按决策点切段、账本续接、再把真实权益反馈给 C2 的完整循环。
因此这次交付不产生 C1/C2 的收益、回撤或年化结论。

## 验证

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
.venv\Scripts\python.exe tools\overlay_runner_contract.py
.venv\Scripts\python.exe -m pytest tests\unit\test_risk_overlay_runner.py -q
```

测试包含C0合成数据引擎冒烟、C1降档后的目标重挂，以及C2确认标志为真/假和动态元数据被篡改时的拒绝运行。风险接入与风险层测试31 passed；这是源码工程检查，未产生策略收益证据。

## 2026-09-21 半日时钟进度

`band_engine.py` 增加 `execution_clock='halfday'`，默认legacy仍为历史对照。ETF两类决策路由、缺栏拒绝、上午权益手算与午盘未来价格扰动测试通过；引擎三个测试文件合计44 passed。stats记录实际execution_clock及ETF路由。

半日时钟不是完整主线执行器：未成交意图仍存在自动续挂，账户动态反馈尚未完成，不能作正式策略验收。下一步先修建议失效、显式续发与连续风险兜底计数，再接单账本反馈。

## 2026-09-21 动态意图入口（状态转换完成）

`run_band_backtest_intents(..., intent_provider=provider)` 落地：每个决策点在半日成交入账后、下一半日订单生成前，以本账本快照调用宿主回调。`ledger` 含已结算现金、`pending_am_to_pm`/`pending_next_day` 两桶、M2 权益快照、每个持仓的取得批次与下一半日可卖数量——正是上文 C2 所缺的"动态账本反馈入口"的引擎侧。半日时钟下普通意图生成即标记半日有效、无法定价（停牌/无行情）即 `expired_halfday_no_anchor` 失效，自动续挂只保留给 risk 意图（streak 冻结顺延）；风险兜底 K=3 连续计数跨半日成立（合成回放 armed 后开盘市价离场）。合并规则 fail-closed：行必须盖当前决策点时间戳、(symbol, 日期, 时段) 重复拒绝、更早同 symbol 意图显式 overridden（armed 兜底存续）。

验证：`tests/test_band_dynamic.py` 7 项（d1–d7，含费用手算与守卫负例）；band 四文件合计 52 passed；全仓 615 项 613 passed（2 failed 为预先存在的 factor_correlation_dedupe，与本轮无关）。零试验消费。

C2 的完整回放仍需在本入口之上实现：把 `resolve_overlay` 的 as-of 权益计算改接 `ledger['equity_snapshot']`、按决策点生成降档/恢复意图。本入口不改变 C0/C1 静态路径与历史 runner。
