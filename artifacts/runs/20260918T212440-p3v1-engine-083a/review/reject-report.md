# v1 引擎首轮双签：REJECT 报告（留档）

- 评审对象：`src/quant/backtest/band_engine.py` v1 首版（sha256 `dcbdc73cbbcb8b01…`，1,855 行）+ 19 项测试 + 本 run 目录首版产物
- 评审方：独立审阅代理（双签链第二签）；主对话初验：sha 一致、19/19 本机重跑通过、§7.7 符号抽查在位
- 结论：**REJECT**（账户计算核心——成交/账本/现金/费用/公司行动——未发现错误；两项门禁集中在披露与兜底边缘路径）

## CRITICAL

**C1 · 桥接披露硬编码清零**（band_engine.py 首版 L311；test_18 L1204-1208；manifest.bridge）
`assert_daily_halfday_bridge` 以 0.011 容差计算了 post-cutoff 不匹配数，但返回字典写死 `"pm_close_mismatches_post_cutoff": 0`——计算结果被丢弃，真值 1,824 行。test_18 用 |diff|=0.5 的 fixture 断言返回 0，把 bug 固化为预期。缓解：pm.close 从未用作 mark/锚，成交与损益不受影响；但 fail-closed 声称对 post-cutoff 失真不成立。

## MAJOR

**M1 · K=3 市价兜底无视显式股数**（首版 L1454、L1501-1504）
兜底数量取全部可卖份额，忽略订单显式 shares——部分风减单触发兜底会整仓清仓，击穿 §7.7-m2"减至目标"与 v1 drift-trimming 原语；P3R2 的 rescale 减持映射必踩。测试未覆盖（test_08 风减单均 shares=None）。

## MINOR（8 项）

1. §7.7-m2 后半句（双卖意图成交后重估"减至目标"）无 owner——裁定：宿主下一决策点、引擎不代做；P3R2 静态映射无 profit 卖单零暴露（已写入契约 §7.7）。
2. test_02 L370-371 永真断言（自身比较），须恢复真实 T+1 违例扫描。
3. decision_step 前视：11:30 决策用当日 pm bar 存在性决定 streak 撤销——裁定：am 决策点一律冻结、仅 pm 决策点允许撤销。
4. 手算样例 3 将盯市口径损益（−1,532.50，基准=前官方收盘 29,000）与"买入 @30"并置致误读；成本口径应为 −2,537.50——文档表述缺陷，非断言错误。
5. source_signal 解析 L709-712 死分支（两分支条件相同）。
6. 送转 added 整手 clip 的次日锁定无直接测试（只钉了零股侧）。
7. docstring"无 wall-clock 依赖"与 1800s 预算守卫 raise 矛盾，声称须加限定。
8. manifest daily_official.path 用绝对路径；首版样例生成脚本三处错误靠事后 fix 脚本修补（诚实但应测试化）。

## PASS 项摘要

§7.7 全部裁定逐条对代码核实属实（M1 键控/M2 快照作废/漂移仅记录/m1/m3/m4/m5/m7）；费用现金逐分对账（test_01）；整手不变量；停牌/涨跌停；公司行动（两级拆分、per-lot 分红、真实 600000 与 F2 回归）；3/18.5M 极值越界降级披露安全；重锚责任宿主化接口完备；AGENTS 纪律（冻结线、零试验、data/raw 只读）。

## 复审指引

C1 一行 + 测试/manifest 重出；M1 数行 + 回归测试；均不触碰成交/账本主路径——修复后 diff 级复审即可，无需全项重做。修复复审通过前 P3R2 不得运行。
