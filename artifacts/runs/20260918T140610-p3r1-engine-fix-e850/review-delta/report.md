# P3R1 引擎返工 · 双签增量复审报告（第二签 · delta）

- 审阅代理：独立审阅（双签第二签）；对象：REJECT 后返工运行 `20260918T140610-p3r1-engine-fix-e850`
- 范围：仅公司行动线与本审阅 F1–F8 的处置；机制面未重做（见"机制回归说明"）
- 留痕：`hash_check_delta.py/.log`（17/17）、`pytest_delta_rerun.log`（13/13）、`delta_adv.py/.log`（22/22）；只审不改，零网络零 git

## 结论：APPROVE

**F1（CRITICAL）与 F2（MAJOR）的修复经真实数据与独立合成探针双重验证正确；F3–F8 处置逐条属实。13 项契约测试独立复跑通过，manifest 身份链（含修正版契约钉死 1d3c5c1f398102ee）全部一致，旧 REJECT 运行目录原样保留为档案。P3R1 八配置重裁定可以进入判定流程；判定报告须携带已在引擎文档中登记的 F6/F7 披露义务（顺延双记口径、除权日锚依赖 stk_limit 质量）。**

## F1–F8 处置逐条验收

| 项 | 处置声称 | 独立验收结果 |
|---|---|---|
| F1 CRITICAL | 账户输入改 split_factor.h5（逐事件送转比）+ dividends.h5（每手税前 ÷ round_lot × 除权前股数）；ex_cum_factor 移出账户路径，保留 audit-only loader | **通过**。`run_band_backtest(signals, daily, stk_limit, splits, cash_dividends)` 签名无 ex_cum_factor；全文件 grep 仅剩文档字符串与 audit loader；防御性验证——把 ex_cum_factor 帧误传为 `splits` 被列名校验拒绝（缺 `split_factor` 列）。每手换算四路径一致：loader（读 per-lot 列，round_lot≤0 即中止）→ `_validate_dividends`（每手口径校验）→ `_build_dividends`（÷round_lot 折每股）→ 入账（×除权前股数）。同日送转+分红：`pre_shares` 在份额调整前捕获，分红按除权前股数（真实 2017-05-25 案例实证 0.2×1000=200，见下） |
| F2 MAJOR | split 值逐事件直接生效（无差分、无累计链）；锚点行丢弃；回归测试 test_06/test_06c | **通过**。自建合成 h5（非复用 test_06c）：锚点 (0,1.0) 丢弃（meta anchors_dropped=1），行值 1.05/1.1 原样保留；引擎跨首事件持仓 ×1.05=105 股、跨第二事件 ×1.1→116 股——首事件比值即行值本身，7.82 类累计污染在结构上不可能。真实 600000 首个 split 行即其首个真实送转 1.1（无锚点行，anchors_dropped=0，丢弃逻辑为防御性） |
| F3 MINOR | 修正版契约钉死 sha256:16=1d3c5c1f398102ee；旧 REJECT 目录不动作档案 | **通过**。新契约全文 sha256 逐字匹配 pin；`supersedes` 字段指回旧运行；旧目录 4 个产物 + manifest 哈希逐一复算未变 |
| F4 MINOR | 样例 C limit_down 更正为实际喂入值 24.66 | **通过**。新手算文档明示"当日收盘×0.9（本样例即 F4 更正点：此前误写前收口径 25.65）"；新增样例 D 手算逐数人工复核正确（1300 股、分红 200、现金 184,195、净回笼 16,163.815 含全精度印花 16.185） |
| F5 MINOR | 验收项 3 改口径：买入整手；公司行动零股一次性卖出；odd_lot_exits 计数 | **通过**。显式非整手买入/卖出均被输入校验拒绝；300 股 ×1.3→390 零股单笔整仓卖出，`odd_lot_exits.count=1` 且带定义；所有买入成交整手断言存在（test_03 + 本次复验） |
| F6 LOW | deferred_limitdown_days 定义为"顺延事件数"，嵌入 stats 与 docstring | **通过**。`stats['k3_fallback']['deferred_limitdown_definition']` 存在，措辞与我的原始发现一致（顺延日限价可并行成交，一次兜底可既顺延又成交，不得据此算兜底率） |
| F7 LOW | 除权日锚=除权前收盘（当日唯一良定义）；保护依赖交易所口径 stk_limit；判定报告须披露触发数 | **通过（文档级，符合约定）**。docstring + 代码注释 + manifest 均写明数据质量依赖与披露义务 |
| F8 INFO | 测试临时文件移至系统 TEMP；其余记录为 INFO 不改行为 | **通过**。test_00 现用 `tempfile.gettempdir()`；void_days 命名与不可达分支按约定保留为已记录 INFO |

## 对抗复验（真实数据，`delta_adv.py` 22/22）

- **(a) 600000 2022-07-21 纯派息（真实日线 + 真实 dividends 行 41.0/手、round_lot 100）**：07-20 建仓 1000@7.81；除息日**份额不变**、现金 +410.00；07-22 卖出仍 1000 股 @7.33。权益恒等式：Δequity = −50.00 = 分红 410 + 市值变动 (−460)，**无重复计入**（旧引擎在同场景会虚增 410 + 股数膨胀 5.6%）。
- **(b) 600000 2017-05-25 送转×1.3 + 分红同日（真实日线 + 真实行）**：1000→1300 股（行值直接生效）；分红 0.2×1000（除权前）=200.00；权益恒等式 Δequity = 1539 = 200 + (1300×12.93 − 1000×15.47) 精确成立；期末持仓 1300 股=真实可执行量。对照记录：ex_cum_factor 同日比值 1.3166（含分红价格链）≠ split_factor 行值 1.3——修复取后者的依据成立。
- **(c) 50 只样本扫描（split 与 dividends 各抽 50）**：loader 输出与 h5 原行的行数/日期/值/round_lot 逐行一致（mismatch=0/100）。全库：split 2,878 键/4,930 行、无同日重复行、无非正值；dividends 4,512 键/28,450 行、round_lot 全为 100、641 行 cash==0（送转-only 事件，引擎跳过零额）。
- **(d)–(g)**：见处置表（合成 h5 loader 回归、F5、F6、防御性误传拒绝）。

## 新观察（均不阻塞）

- **N1 INFO（已核实无碍）**：split_factor.h5 有 19 行比值 <1.0（16 只标的），**全部为 ETF**（51/15/56/58 前缀，份额折算）——P3R1 v0 纯股票池零接触；该语义恰是 v0.5 ETF 阶段所需（对应红队 R3-1 折算修复）。建议：判定运行的接线层断言传入 `splits` 仅含股票池标的（池过滤天然满足，加一道断言更稳）。
- **N2 INFO**：真实 split_factor.h5 无锚点行（anchors_dropped=0）；锚点丢弃逻辑由 test_06c 合成样例钉住。
- **N3 INFO**：预登记 §4 的逐字引用行仍含旧短语"公司行动按 ex_cum_factor 份额调整"，由 §3 修正后输入表与 §7 修正记录管辖；预登记已冻结不宜回改，下次触碰文档时可加一行指针。

## 复跑记录

- `pytest tests/test_band_contract.py -v -ra`：**13 passed in 4.75s**（本机独立执行；与 manifest 13 passed 一致）。
- 哈希：17/17 通过（新引擎 05829491…、新测试 e1bf25c2…、修正版契约 1d3c5c1f398102ee…、预登记 §7 版 ebb73059…、p3r1 配置 9839ff07…、split_factor 2f436b2f…、dividends 46121c09…、daily/stk_limit/r16/exf audit pin 不变、4 个 run 产物、旧 REJECT 目录 5 项未变）。
- 增量对抗：22/22（脚本 `delta_adv.py`，真实数据只读）。

## 机制回归说明

按指令未重做机制面对抗（旧 46 断言）。回归覆盖依据：新测试 01/02/04/05/07/08/09/10 与旧版逐字相同且全部通过（重钉费用守恒、T+1、优先级现金、触价、停牌/涨跌停、K=3 全家族、现金时序、印花分段）；本次逐行比读新旧引擎，差异仅限：模块 docstring、新增两个 loader、`run_band_backtest` 签名与公司行动块、odd_lot_exits 统计、F6/F7 注释——买卖主循环、arm_k3_if_due、sweep_deaths、费用与标记逻辑与旧版一致（旧版已被我 46 断言对抗验证，含武装+停牌、5 日跌停顺延、缺涨跌停数据兜底、零股现金竞争重挂等场景）。
