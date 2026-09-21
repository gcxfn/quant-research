# 引擎 v1.3 交付报告 —— §9.3 A–D（ETF 份额变换：时变公司行动扩展）

- 运行 `20260919T132557-engine-v13-b7e2`；状态 **completed**；试验次数消费 0；val 零接触。
- 权威规格：`docs/plans/p3-band-contract.md` §9（含 2026-09-19 修订 1：份额乘数取公告整数比例）+ §1/§7/§8 既有语义；`AGENTS.md` 仓库纪律。
- 引擎：`src/quant/backtest/band_engine.py`；基线 v1.2 sha256 `ceb7be64…746d`（开工校验一致，2627 行）→ **v1.3 sha256 `84a2443ac28fe1b87e4a18f988fd38cc67cf706d5778e262f11465147234082c`**（**尚未 pin**——pin 属 §9.3-E，由主对话复核后执行）。

## 一、实际改动明细（A 项）

全部改动集中在 `src/quant/backtest/band_engine.py` + 新测试文件；未动任何其他源码、configs、docs、data。

1. **接口**（§9.2-8）：`run_band_backtest_intents` 与 `run_band_backtest` 追加可选参数 `corporate_actions=None`（位于 `dividend_events` 之后、keyword-only 参数之前）；None 时逐字节走 v1.2 路径（锚 1/锚 2 回放 + 既有 402 测试证明）。
2. **事件归一**：新增 `_normalize_corporate_actions`——接受 None / dict / polars / pandas；必需列 (symbol, date, ratio)，可选列 factor_jump（缺则补 null 列）；ratio 有限 >0；factor_jump 有限 >0 或 null；重复 (symbol, date) 拒绝；冻结断言 ≤2024-12-31。
3. **入口硬断言**（全部在模拟交易开始前 fail-closed）：
   - §9.2-5 护栏：`|preclose × ratio − close(t−1)| / close(t−1) ≤ 2%`，其中 preclose 只取日行情 `preclose` 列（无该列值 → 专用报错，不用重构价充当），close(t−1) = 除权日前最后一个交易日官方收盘；**护栏是合法性断言，不是零连续性要求**（停牌期净值漂移 = 真实损益，经复牌参考价进入估值，引擎不调整）。
   - §9.2-1 factor 交叉核验：事件携带 factor_jump 时 `|factor_jump / ratio − 1| ≤ 2%`。
   - §9.2-7 防误分类：`dividend_events` 任一（日面板内标的）事件隐含收益率 `(close(t−1) − preclose)/close(t−1) > 10%` → 硬报错（该检查无条件运行；无 preclose 列或无前收盘时不可评估则跳过——与 v1.2 的 stock 测试面板兼容，dev 分红最大隐含收益率 +5.44% 不受影响）；同 (symbol, date) 同时出现分红与份额变换 → 硬报错。
   - 附加数据完整性护栏：corporate_actions 与 v0 `split_factor`（送转路径）同 (symbol, 除权日) 冲突 → 硬报错（防双重变换）；事件标的必须存在于日面板。
4. **执行时点与变换**（§9.2-2/3，日历循环顶部公司行动块内、先于当日任何成交判定与估值）：逐 clip 变换全部持仓——
   - **整数比例**（修订 1）：`new = old × ratio` 精确整数，零零头零折现；clip 结构镜像 stock 送转路径：`keep = min(shares, new_total)`（保留原取得日），`extra = new_total − keep` 作为新 clip 取得日=除权日（m4 镜像，次日可卖；T+0 品种当日下午会话可卖，创建会话标记为 am）。
   - **非整数 fallback**（仅为未来事件保留，两真实事件断言零触发）：floor + 零头 `frac × preclose` 计入已结算现金。
   - 事件 `corp_action_share_change`（ratio/shares/cash_amount/detail 含 preclose、close(t−1)、残差、路径标注）。
   - **与 stock 侧路径的关系：并行不复用**。stock 侧 v0 F1 `split_factor` half-up 路径的函数体一行未改（锚 1 逐字节等价 + test_06/06b/21 原样通过）；v1.3 路径独立成块，因其需要公告整数比例精确性、护栏/factor/冲突断言与独立事件名。`extra` clip 的取得日/会话结构与 stock 路径相同（m4 语义共享）。
5. **stats**：仅在 `corporate_actions` 非空时新增顶层键 `share_changes`（events / odd_lot_cash_total / shares_before / shares_after）——无事件运行 stats 与 v1.2 键集完全一致；`engine_version` 更新为 `"band_engine v1.3"`（见接缝 S-v13-3）。`stats["corp_actions"]` 子字典形状未动（test_06 的精确断言原样通过）。
6. **在途订单**（§9.2-6）：零新代码——停牌沿 m3 冻结、除权日旧锚依赖既有"限价合法性作废并计数"与"15:00 机械重锚"安全网；用测试证明（见下），并登记可达性澄清接缝 S-v13-4。

## 二、测试清单与结果（B + C 项）

新文件 `tests/test_band_engine_v13_corporate_actions.py`（18 项，全部通过；sha256 `4e9d5c8e…02b5`）：

| # | 测试 | 覆盖 |
|---|---|---|
| 1 | ca1_integer_exact_transform | 整数比例 300×2→600 手算：零零头、价值恒等逐分对账（Decimal：600×1.0 == 300×2.0）、现金手算 199,993、守恒 |
| 2 | ca1b_integer_m4_structure | keep(300, 原取得日)/extra(300, 除权日) clip 结构 |
| 3 | ca2_fractional_fallback | 非整数 300×1.9848→595 份 + 零头 0.44×preclose=1.32 元，Decimal 逐分对账（300×5.9544 == 595×3.0+1.32）、零头现金入账、595 尘埃单整笔卖出 |
| 4 | ca3_real_513100_ex_date_void | **真实事件回放**（单标的日历）：2021-12-30 买入 1800×5.402 → 2022-01-14 变换 9000（残差 +0.0385%）；旧锚 5.192 买单在 01-14 对 [0.934, 1.142] 计算涨停作废且 void_days≥1；意图 15:00 被卖出意图覆盖；01-17 卖出 9000×1.015；现金到分（199,401.40） |
| 5 | ca3b_real_513100_freeze | **真实事件回放**（混合日历，510300 陪伴 01-13 交易）：01-13 void_suspended + K 冻结、无锚跳过重挂、01-14 15:00 重锚新价格域、01-17 成交、守恒 |
| 6 | ca4_real_513500 | **真实事件回放**：03-24 买 3600×2.722 → 03-30 变换 7200（残差 +0.7678%）；旧卖单 03-30 限价合法性作废（[1.24, 1.516]）；重锚后 03-31 7200×1.39 成交；现金到分 |
| 7 | ca5_t0_same_day_sell | K=3 兜底于除权日 pm 开市执行：T+0 下变换新增 clip 当日可卖（5000 股含新增 4000） |
| 8 | ca5b_t1_lock_control | 对照：t_plus=1 时新增 clip 当日锁定（只卖 1000，余 4000 取得日=除权日） |
| 9 | ca6_misclassification_raises | 513100 型跳变（隐含收益率 ~80%）喂 dividend_events → 硬报错；正常 ~2% 分红对照通过 |
| 10 | ca7_conflict_raises | 同 (symbol, date) 分红+变换 → 硬报错 |
| 11 | ca8_guardrail_raises | 错比例（残差 185%）→ 护栏硬报错 |
| 12 | ca9_factor_jump_check | factor_jump 5.2（偏差 4%）→ 报错；5.0019（真实因子比）→ 通过 |
| 13 | ca10_stats_shape | 无事件运行无新增 stats 键；有事件运行出现 share_changes 计数 |
| 14 | c1_dividend_ex_date_same_day_etf | **C 债①**：dividend_events 路径——除权日当日买入的份额不参与分红（day-open 口径），存量 clip 正常收取（50 元），现金逐分手算 |
| 15 | c1b_dividend_ex_date_same_day_stock | **C 债①**：v0 每手分红路径同边角（410 元，当日买入者不参与） |
| 16 | c2a_m7_equal_priority_cash | **C 债② m7**：同决策点同优先级现金稀缺 → 确定性裁决（(priority, symbol) 稳定排序 + 意图帧生成序）；PD 成交、PE insufficient_cash 作废 |
| 17 | c2b_m7_fifo_consumption | **C 债② m7**：部分减持按 clip 创建序 FIFO 消耗（A 1000 + B 500，余 1500 归属较晚 clip） |
| 18 | c2c_m7_independent_clips | **C 债② m7**：同标的多 clip 独立判穿透——当日取得（T+1 锁定）的 clip 不阻塞可卖 clip 的成交 |

**既有测试等价性排查（C 项要求）**：搜索 tests/ 后确认无等价测试——test_04_cash_priority 覆盖不同优先级现金竞争（非平局、非 m7）、test_06/06b 公司行动但买入均先于除权日（非同日边角）、test_15_multi_clip_fifo 覆盖 FIFO 但非 m7 现金/穿透语义。故 C 项两条债务均为新增覆盖。

**全量测试**：`python -m pytest tests -q` → **420 passed / 0 failed / 0 skipped**（基线 402 + 新增 18，满足 ≥415 且无 skip）；6 条 warning 为无关研究模块的 polars join_asof 既有提示。引擎测试迭代期间逐次通过：41 项既有引擎测试（contract 21 + intents 8 + hybrid 12）在实现后首跑即全绿。

## 三、锚回放证据（D 项，均不传 corporate_actions）

### 锚 1：P3R2 C05（源 `artifacts/runs/20260919T030640-p3r2-dev-ad9e/`）

- 复放方式：源 `tmp/runner_p3r2_intents.py` 复制进本运行 `tmp/`，最小适配（CONFIG_IDS→[C05]、引擎 sha pin→v1.3、PANEL_BY_CFG setdefault、报告/清单写入重定向 tmp/），命令与数据 pin 逻辑逐行未动。
- 结果：**C05_fills / C05_events / C05_daily_equity / C05_clips_final / C05_intents 五个 parquet 与源 outputs 逐字节相等**（sha256 逐一比对一致）；84s 墙钟、峰值 RSS 4.85 GB；全部身份 pin match（含引擎新 sha）。
- 未比对项：`metrics_and_gates.json`——含本次复放的引擎 sha 字符串、计时与本运行仅 C05 的范围差异（本次复放产出的该文件在本运行 outputs/，来源已在 manifest 注明）。源该文件由 v1.1 引擎产出（源运行时引擎为 v1.1，sha d7108c0e…），其四帧与 v1.2/v1.3 输出帧相等已由逐字节 parquet 比对证明。

### 锚 2：混合族 H2-A0（=ROT-05；源 `artifacts/runs/20260919T063022-hybrid-v2-2k5b/`）

- 复放方式：源 `scripts/runner_hybrid_v2.py` 复制进本运行 `tmp/`，适配同上（CONFIG_IDS→[H2-A0]、引擎 sha pin→v1.3、写入重定向）。
- 结果：**H2-A0 五个 parquet + dividend_events.csv 与源 outputs 逐字节相等**；runner 内建回归断言（H2-A0 四帧 .equals P3R2 C05 + net_cagr 1e-12 一致）PASS；37s 墙钟、峰值 RSS 3.26 GB。
- `H2-A0_stats.json`：**归一化后逐字节相等**——仅两个字段不同：①`stats.engine_version`（v1.2→v1.3 版本标签，接缝 S-v13-3）；②`wall_s`（墙钟计时，源文件本身即含非确定值，逐字节比对天然不可用）。其余全部键值（含全部披露计数）逐字节一致。
- `rotation_monthly_log.json`：差异纯属复放范围——源含全部 8 配置条目，本次仅 H2-A0（两边的 H2-A0 条目同为 null，相等）。

## 四、接缝登记（S-v13-N；S-v13-1/2 已在任务书关闭，此处为实施新发现）

- **S-v13-3（版本标签 vs 逐字节零回归）**：v1.2 交付时以"新增键"方式引入 `stats["engine_version"]`，v1.3 将其值更新为 `"band_engine v1.3"`——这使锚 2 的 `H2-A0_stats.json` 该单字段与源不同（连同本来就非确定的 wall_s）。本交付按"归一化后逐字节相等 + 全部行为帧逐字节相等"处理并在此申报。请主对话在 pin 时裁定：接受标签随版本推进（现状），或要求版本标签退回字符串 `"band_engine v1.2"`（改回一行即可恢复含 stats 的完整逐字节等价，v1.3 身份仅由 sha256 记录）。若裁定改回，pin 前改一行 + 重跑锚 2 比对即可。
- **S-v13-4（§9.2-6 买单作废安全网的可达性澄清，非缺陷）**：意图模式下 ETF pm 决策 live 次日 pm。混合日历（生产形态，停牌日为全市场交易日）下，除权日前最后决策的订单 live 于**停牌日**会话（void_suspended、K 冻结），停牌日 15:00 决策因无锚跳过重挂——旧锚订单**到不了除权日会话**，保护链为"void_suspended + 无锚跳过 + 15:00 新域重锚"（ca3b 真实数据验证）。**单标的日历**形态下停牌日不在引擎日历，旧锚订单直接 live 于除权日会话，限价合法性作废路径真实触发（ca3 真实数据：作废计数 ≥1、limits [0.934, 1.142]）。两条保护链均不曾在旧价格域成交。语义与 §9.2-6 的意图一致，仅"作废计数"一条在混合日历下不可达——是否需要为混合日历补一条可观测的披露计数，请主对话裁定（不裁定不影响正确性）。
- **S-v13-5（m7 "clip 创建序（早者优先）"的现行为澄清）**：买入现金竞争的引擎现行为 (priority, symbol) 稳定排序叠加意图帧生成序（first_key 早者先生成）；跨标的同优先级平局由 symbol 名仲裁（c2a 钉住）。同标的同时刻两个买入订单在两种入口下均被结构性排除（首决策点去重/覆盖链），故"创建序早者优先"的可观测绑定在 **clip 消耗 FIFO**（c2b）。若主对话裁定 m7 要求其他平局规则，需另行授权修改（现行为自 v1.1 起未变，非本轮引入）。
- **S-v13-6（披露统计已知失真，非账务缺陷）**：份额变换后若 K=3 兜底在除权日市价执行，`k3_fallback.pnl_contribution` 披露值将以除权日前旧域收盘为 prev_close，数字失真（现金/权益不受影响；ca5 合成场景触发该路径但现金守恒断言通过）。建议 val 预登记披露该字段口径或忽略；本轮真实回放未触发兜底。

## 五、未完成内容与边界

- §9.3-E（双签/pin）、F（主计划/README 记账）未做——按任务分工属主对话；本报告与 manifest 已含 pin 所需的新 sha256。
- 运行层 val 事件表构建、任何 val 运行：未做（非目标）。
- `engine_version` 字符串、S-v13-3/4/5 的裁定：等待主对话。
- 未初始化/操作 git；data/raw、既有 artifacts 运行目录零改动（锚复放脚本对源目录只读）；未拉取任何新数据（公告核验走 Wind MCP 文本检索，摘录存 `tmp/corporate-action-announcements-evidence.md`）。

## 六、运行身份

- 环境：Python 3.11.15 / polars 1.44.2 / Windows（Git Bash）；venv `D:/量化/.venv`。
- 输入身份：etf-daily parquet `b7225d50…d661`（1,017,121 行）、批次 manifest `8b5b3fe5…1c8a`；锚 1/2 的其余 pin 见 `tmp/anchor1_manifest.json`、`tmp/anchor2_manifest.json`（全部 match=true）。
- 本报告不构成盈利或性能声称；全部数字为历史回放与契约测试。
