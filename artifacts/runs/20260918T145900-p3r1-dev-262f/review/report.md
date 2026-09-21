# P3R1 dev 裁定 · 收官双签复核报告（第二签）

- 审阅代理：独立审阅（第二签）；此前链路：引擎双签 REJECT（ea06）→ 修复 APPROVE（fix-e850 delta）→ 本轮裁定收官复核
- 对象：`artifacts/runs/20260918T145900-p3r1-dev-262f/`（0/8 eliminated、val 零消费、189→197）
- 纪律：只审不改；留痕脚本与日志在本目录（`consistency_check.py/.log` 44 断言、`sizing_convergence.py/.log` 30 断言，全部通过）；零网络零 git

## 结论：PASS（对应 APPROVE）

六项复核全部通过，未发现 CRITICAL/MAJOR。裁定结果（0/8 全部 eliminated、val 一次性纪律未消费、试验 189→197）在独立复算下成立且**对 sizing 未收敛稳健**。以下发现均为 INFO/LOW，无阻塞项。

## 六项复核结论

| # | 项 | 结论 |
|---|---|---|
| 1 | 门评估逐字性 | **PASS**。runner 第 483 行 `gates = r16.evaluate_dev_gates(m, b3_means[path])` 直接调用 R16 冻结模块函数，无重实现；传入 metrics 的键与函数所需一一对应。门 4 在 R16 模块内为 `abs(mdd) ≤ 0.20 且 abs(mdd) ≤ abs(b1m_max_drawdown)`（`p2r16_trend_dispersion.py:1105-1109`）——"≤20% 且 ≤B1(m)"逐字，"16%"确系转写笔误（主对话裁定成立）。B1(m) 三件套与 B3′（均值+分种子）从 R16 权威 `metrics.json` 原样复用，逐值完全相等（校验 1 第 3 组） |
| 2 | 映射与 sizing | **PASS**。rescale 不映射、expiry=下信号日（末日映射至 2020-12-31，仍在 dev）、priority=信号日流动性排名（离场无排名者 10^6）、target=exposure×equity/K 迭代——与 manifest `mapping_decisions` 逐条一致。sizing 残差实证：C06 复跑至第 9 次迭代收敛，不动点净CAGR +0.2405% vs 报告（第 6 次）+0.2523%，差 **−0.0118pp**；C08 第 7 次收敛，与报告**完全相同**（差 0.0000pp）。不动点处重评门 1/2/3/4/8：方向与集合零翻转，仍 eliminated。"无边际影响"的说法成立并升级为实证。关于"C06 门 2 差 0.35pp"的口径澄清见 N1 |
| 3 | 门 8 双口径 | **PASS**。映射口径（filled + below_min_lot + void_no_position + 现金阻塞至过期，runner 第 449-462 行）= 91.1–93.3%（8/8 < 95%，门 8 全败——这是 0/8 的机械性主因之一，源于区间契约限价不成交，与 sizing 无关）；原始订单口径逐配置复算一致（买 31.8–54.5% / 卖 78.3–85.6%）；混合口径 (买成交+卖成交)/总订单 = **44.0%（C06）–65.4%（C03）**，与披露"44–65%"在整数舍入下成立（见 N3）。两口径均 <95% 对 8/8 成立 |
| 4 | 抽查一致性 | **PASS**。C01–C08 全部 8 配置的 gates 表与 `outputs/metrics_and_gates.json` 逐字段核对一致（校验 1 第 2 组）；C01 的 5.17%/−30.61%/3-of-6 与主对话独立复算一致（复用该结论）；37 个输出文件哈希与 manifest 逐一匹配 |
| 5 | val 零接触 | **PASS（附 N4 精确刻画）**。引擎面板/涨跌停显式裁剪至 2020-12-31（runner 第 256/270 行 + 我复现的面板 max date 断言）；指标全部来自 dev 曲线；`evaluate_val_gates` 未被调用；`advanced_to_validation=false, val_consumed=false`；2020-12-31 信号按冻结先例丢弃（71 信号末位 2020-11-30，复现验证）。精确注记见 N4 |
| 6 | 交付物诚实性 | **PASS**。5 项身份 pin + R8 机制身份 + T200 行为锚 + stk_limit 聚合全部 match；信号重建 8/8 一致性（leg_log 权威 + r16 逐字重算逐 (config,signal) 比对）由我独立复刻流程再验证；ENGINE-1 修复记录与实际 diff 逐字一致（见 N5）；43b7 档案完好（status=failed、根因 ENGINE DEFECT、无 outputs、manifest 独立）；SIGN-OFF.md 在 fix-e850 目录存在 |

## 分级发现

- **N1 INFO（口径澄清）**："C06 门 2 差 0.35pp"中的 0.35pp 是 C06 **excess 值本身**（−0.35pp = 净CAGR +0.25% − B1 +0.60%）；门 2 通过阈值 +2pp，实际短差 **2.35pp**——sizing 不可能翻转。C06 真正最窄的边际是门 1（净CAGR>0）+0.25pp，其不动点残差 0.012pp，相差 20 倍；且即便门 1 翻转，门 2/3/4/8 仍失败，判定不变。
- **N2 INFO（实证补充）**：sizing 迭代呈衰减振荡收敛（C06 CAGR 序列 3.669→1.680→0.318→0.308→0.341→0.252→0.384→0.241→0.241，第 9 次帧相等）；runner 的 6 次截断值与不动点差 0.012pp。建议未来 runner 把收敛上限提高到 ~10 次或以 end_eq 相对变化 <0.1% 为停机条件（工具性建议，不影响本轮）。
- **N3 INFO**：混合口径 fill 上限实为 **65.4%**（C03），"44–65%"为整数舍入；建议未来披露写 44.0–65.4% 以免歧义。
- **N4 INFO（val 零消费的精确刻画）**：`build_history_r16` 与 `market_calendar` 在内存中加载 ≤2024-12-31 的行（2021–2024 价格行进入历史帧），但池为**点时构造**——仅在 71 个 dev 信号日 join、全部滚动窗口 trailing（20 自身交易日，warmup 2012 起），2021+ 值对 dev 信号/暴露/指标零影响；引擎面板与涨跌停显式裁剪，权益/成交/门指标零 2021+ 消费。即：字节级有读取、结果级零消费。与预登记"一次性 val"纪律的冲突不存在；如需字面"零读取"，未来可对 history 构造加 `date <= DEV_END` 裁剪（warmup 不受影响），属工具性建议。
- **N5 INFO（ENGINE-1 验证）**：当前引擎 sha256 `68f10252…` = manifest `engine.sha256` = `ENGINE-1.sha256_after`；`_frame` diff 与声明逐字一致（`pl.DataFrame(rows, schema=schema)` + 授权注释，文件 1432→1438 行精确吻合 ±7/−1）；修复根因（polars 前 100 行类型推断遇 corp-action 列建 Null builder 致 43b7 崩溃）与 43b7 失败记录互证；14 tests passed（13 旧测试未动 + test_14 回归）。授权链（编排方 14:56 裁定、prereg §7）齐备。经我逐行比读，除 `_frame` 与注释外与双签批准版无差异。
- **N6 LOW（鲁棒性边角，本轮未触发）**：runner 给 sell 信号写 `anchor_price = close_at.get((sym, t), NaN)`——若某离场标的在信号日无 bar（停牌），NaN 会被引擎输入校验拒绝并使整个 run 失败。本轮 71 信号未触发。未来可用"该标的最近可得收盘"或跳过并记录（不影响本轮结论）。
- **N7 INFO**：runner 的 `weights_max` 复放用"严格前一日收盘"作 mark（`bisect_left` 取 i−1），引擎权益曲线用"≤当日最后交易收盘"——单日差；门 6 阈值 40% vs 实测最高 21.8%（C01），无判定影响。
- **N8 INFO**：manifest `finding_for_referee` 自曝 loader 列名桥接（tushare `up_limit/down_limit` → 引擎 `limit_up/down_limit` 的 caller-side rename）——定性准确（纯命名、无计算影响、引擎字节未动），与我的历次双签认知一致；建议未来工具化批次对齐 loader 列名。

## 复跑记录

- 校验 1（`consistency_check.py`）：**44/44**——37 输出哈希、8 配置 JSON vs 报告逐字段、B1/B3′ vs R16 逐值相等、门 8 双口径 8/8 <95%、C06/C08 边距、判定与 val 标记。
- 校验 2（`sizing_convergence.py`）：**30/30**——71 信号与 2020-12-31 丢弃复现、确定性复现（我的第 6 次迭代 = runner 报告值逐位）、C06/C08 不动点复跑（残差 0.012pp/0.000pp、门零翻转）、8 配置订单口径成交率从 outputs 事件/成交 parquet 复算一致、混合口径 44.0–65.4%。
- 复核过程中我方脚本的 3 次断言失败均为审阅脚本自身笔误（门 2 用错基、量纲取整错位），修正后全绿；引擎/runner/输出文件未做任何修改。
