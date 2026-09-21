# R1 公式空间覆盖缺口分析（第三波因子研究员选题输入）

- 日期：2026-09-11
- 作者：分析代理 R（只读分析；本文档为唯一产出）
- 状态：分析工件，非预登记、非可执行结论；所有数字来自对 403 条冻结公式的实际运行统计（临时脚本已删除，方法可按方法论节复现）
- 输入：
  - `artifacts/factor-miner/r0-20260910/hypotheses/_all_raw.jsonl`（250 条）
  - `artifacts/factor-miner/r1-pool-20260911/researcher_*.jsonl`（12 个文件，153 条）
  - 算子白名单：`experiments/factor_miner/operators.py` / `compiler.py`
  - 字段注册表：`experiments/factor_miner/data_fields.py`
- 用途：供第三波因子研究员规避已饱和结构、选择结构性空白方向；不改变引擎冻结协议、生产主线与 Gate。

---

## 1. 方法论（原型编码，可复现）

### 1.1 样本与计数口径

- 实际载入 **403 条**：r0 冻结批 250 条 + r1-pool 12 个研究员文件共 **153 条**（任务简报写 141，实际逐文件解析合计 153，以实际为准：A13/B14/C11/D15/E13/F12/G14/H11/I12/J12/K12/L14）。
- 403 条全部通过 `compiler.compile_formula` 编译（0 条失败），因此本文全部结构统计基于引擎真实 AST，而非字符串近似。
- **注意哈希归一化的含义**：引擎 formula_hash 把窗口参数按出现顺序归一化为 N1/N2 占位符（同窗口数、同窗口相等结构的构造同哈希）。因此"换个窗口值"不是新因子——本分析同样在窗口归一化层做，**凡属"已有结构 × 未用过的窗口"一律不算缺口**（30/40/120 日窗各只有 0—7 条使用，但这不是空白，是同一哈希）。

### 1.2 结构原型编码

原型不是公式哈希，而是"骨架"。定义三级编码（对每条公式，用引擎 AST 自底向上渲染）：

**第一级 `shape`（结构骨架，窗口折叠）**：AST 渲染串，其中
- 字段 → 字段族标签（9 族，见 1.2.1）；
- 窗口整数字面量 → 统一记 `N`（不做值区分——防窗口微调伪新颖）；
- 数字常量 → `C`；算子名与四则结构原样保留。

**第二级 `skeleton`（窗口等值结构）**：同上，但窗口按值共享占位符（N1/N2/…，同值同占位），用于区分"两窗相等"与"两窗不等"的结构。

**第三级 `prototype`（原型三元组）**：
- P1 外层模式 = 根节点角色：`F:level`（裸字段）、`A:+/-/*/÷`（纯四则根）、`CS:RANK`、`W:<op>`（窗口/标量算子根，op ∈ 白名单）；
- P2 输入字段族集合 = required_fields 映射到 9 族的有序集合；
- P3 条件化方式 = 非互斥标志集：`field_gate`（IF 条件含非价格族字段）、`px_gate`（IF 条件含 PX）、`rank_gate`（IF 条件含 CS_RANK）、`size_norm`（除法右侧含 SIZE 族）。

渲染伪代码（与本次运行实现一一对应）：

```
def skel(node, winmap, mode):          # mode ∈ {shape, skeleton}
    num   -> "C"
    win   -> "N" if mode==shape else winmap.setdefault(value, "N%d"%(len+1))
    field -> FAMILY[field]
    neg   -> "(-" + skel(child) + ")"
    bin   -> "(" + skel(L) + OP + skel(R) + ")"
    call  -> NAME + "(" + join(skel(arg_i)) + ")"

def prototype(formula):
    ast   = compile_formula(formula).ast        # 引擎真实解析器
    shape = skel(ast, mode="shape")
    P1    = outer_pattern(ast)                  # 根节点角色，neg 不改变外层
    P2    = sorted({FAMILY[f] for f in required_fields})
    P3    = {flags 扫描 IF 条件与除法右枝}
    return (P1, P2, P3), shape, skel(ast, mode="skeleton")
```

### 1.2.1 字段族映射（9 族）

| 族 | 字段 | 数据语义 |
|---|---|---|
| PX | open/high/low/close/preclose | 价格（前复权+原始合并行） |
| VOLQ | volume/amount | 量、额 |
| TURN | turnover_rate/turnover_rate_f/volume_ratio | 换手率/自由流通换手/量比（daily_basic） |
| MULT | pe_ttm/pb/ps_ttm/dv_ttm | 估值乘数 |
| SIZE | total_mv/circ_mv | 市值 |
| MARGIN | margin_balance/margin_buy/margin_sell | 融资融券（t 日可得） |
| LHB | lhb_net_buy/inst_net_buy | 龙虎榜净买入/机构席位（**上榜日 t+1 对齐，其余日期 None**） |
| BENCH | market_ret/industry_ret_l1 | 市场等权收益 / SW L1 等权行业均值收益（单一市场级序列） |
| STATE | market_vol/adv_dec_ratio/limit_up_count | 引擎派生市场状态（单一市场级序列） |

### 1.3 引擎可表达性约束（缺口可行性硬边界）

以下边界决定某些"形式上空白"的格子**不可作为缺口派工**：

1. **滚动窗 min_periods=全窗 + NaN 不填充**：窗口内任一日缺失 → 该日输出 None。LHB 字段只在上榜日+1 有值（稀疏），故 **任何窗口 >1 的算子作用于 LHB 字段结构性近死**（如 `MEAN(SIGN(lhb_net_buy),20)`、`ZSCORE(lhb_net_buy,60)`、`SUM(lhb_net_buy,20)` 实际几乎全 None——r0 META_flowlhb 08/09/10/13 即此类，留档勿仿）。LHB 只能做：当日水平/比值 + CS_RANK，或作为与稠密字段的同日交互项（稀疏激活）。
2. **无滞后/位移算子**：无法直接引用 x_{t-k}。自身滞后只能用恒等式近似（如"昨日收益" = `(1+RET(close,2))/(1+RET(close,1))-1`，r1 INFO 已用此技巧），因此**自相关/领先-滞后类构造须显式写出该恒等式**才算可表达。
3. **无逐元素双序列极值**：`MAX(x,N)` 是滚动窗极值，不能取 max(open,close)。K 线形态若需要两序列逐点取极值则不可表达（影线类用 `(high-close)/(high-low)` 等代数绕行，已被 r0/r1 大量使用）。
4. **无幂算子**：高阶矩靠同一子树重复相乘实现（`r*r*r`），可表达但公式冗长。
5. **纯 BENCH/STATE 字段单独成因子**：BENCH/STATE 是单一市场级序列（截面常数），单独成因子无横截面分散度，必须与个股变化项组合（门控/交互/残差剥离）。
6. **除零 → None**（fail-safe）：一字板日 high=low 会使 `(high-low)` 类分母产出 None，属已知边界，构造时应在 failure_modes 披露。
7. **本分析排除**（任务指定）：`industry_member` 相关（冻结，EXPLORATORY_ONLY）；事件/财报公告类（EVENT 家族已封存，且事件表不走公式层）；任何需要未来数据的构造（编译期已拒绝负偏移）。

## 2. 覆盖矩阵

### 2.1 总体形态统计

| 指标 | 数值 |
|---|---|
| 公式总数 | 403（r0 250 + r1 153） |
| 编译失败 | 0 |
| 不同 `shape`（窗口折叠骨架×字段族） | **363** |
| 不同 `skeleton`（窗口等值结构） | 369 |
| 不同 (shape × 字段族集合) 组合 | 363 |
| 外层模式类别（出现≥1 次） | 16 |
| AST 深度分布 | 2层19 / 3层55 / 4层104 / 5层76 / 6层36 / 7层72 / 8层23 / 9层12 / 10层5 / 11层1 |

在窗口折叠粒度下 403 条公式有 363 个不同骨架——**逐条精确骨架层面几乎不存在重复**，覆盖缺口必须在"机制模板 × 字段族"的粗粒度上讨论（下文 2.4）。这也意味着：第三波研究员提交的任何公式都几乎必然是"新哈希"，**哈希新颖性不等于结构新颖性**，必须对照本文第 3/4 节做机制级查重。

### 2.2 算子 × 字段族矩阵（15×9）

统计口径：字段 f 出现在算子 op 的子树内即计 1 次（每条公式每 (op,f) 至多计 1）；单元格 = 公式条数。**135 格中 91 格非零、44 格为零**。

| op | PX | VOLQ | TURN | MULT | SIZE | MARGIN | LHB | BENCH | STATE |
|---|---|---|---|---|---|---|---|---|---|
| RET | 256 | 1 | **0** | 1 | **0** | 7 | **0** | 1 | **0** |
| MEAN | 72 | 14 | 7 | **0** | **0** | 1 | 1 | 10 | 31 |
| STD | 44 | 3 | **0** | **0** | **0** | 2 | **0** | 5 | **0** |
| MAX | 27 | 3 | **0** | **0** | **0** | **0** | **0** | 3 | **0** |
| MIN | 21 | 1 | **0** | **0** | **0** | **0** | **0** | 10 | **0** |
| SUM | 47 | 26 | **0** | **0** | **0** | 2 | 1 | 34 | **0** |
| DELTA | **0** | 3 | 5 | 5 | 2 | 10 | 1 | 5 | 8 |
| ZSCORE | 15 | 5 | 6 | **0** | **0** | 7 | 1 | 4 | 2 |
| TS_RANK | 10 | 4 | **0** | 3 | 1 | 4 | 1 | 1 | 5 |
| CORR | 56 | 7 | 8 | **0** | **0** | 2 | **0** | 41 | 8 |
| ABS | 38 | 1 | 2 | **0** | **0** | **0** | 1 | 3 | **0** |
| LOG | **0** | 1 | **0** | 9 | 7 | **0** | **0** | **0** | **0** |
| SIGN | 47 | 5 | 10 | 2 | 2 | 2 | 1 | 13 | 44 |
| IF | 64 | 13 | 15 | 4 | 4 | 2 | 1 | 16 | 42 |
| CS_RANK | 49 | 16 | 25 | 26 | 14 | 13 | 14 | 9 | **0** |

零格读法（重要）：
- **DELTA|PX = 0**：从未对价格水平直接做 `DELTA(close,N)`（价格变化一律走 RET），这是口径习惯而非缺口。
- **LOG 几乎只在 MULT/SIZE**（9+7）：对数只用于估值/市值水平，量类从未取对数。
- **CS_RANK|STATE = 0**：市场级序列截面常数，做秩无意义（可表达性约束 1.3.5 的体现）。
- **TURN 列整体稀疏**（RET/STD/SUM/TS_RANK/MIN/MAX 全零）：换手率族只有水平秩、短窗 z、增量、均值斜率和相关性——这是最大的一块连贯空白（见第 3 节区块 A）。
- LHB 列的零格大多因 1.3.1 稀疏约束**不可派工**。

### 2.3 外层模式 × 字段族矩阵

外层分布：`A:*` 102、`A:-` 60、`A:/` 58、`W:IF` 58、`CS:RANK` 23、`W:CORR` 22、`W:MEAN` 21、`W:DELTA` 13、`W:ZSCORE` 11、`W:TS_RANK` 9、`W:SUM` 9、`A:+` 7、`W:STD` 5、`W:MIN` 3、`W:MAX` 1、`W:ABS` 1（`F:level/W:RET/W:LOG/W:SIGN` 未以外层出现）。16×9=144 格中 85 格非零。

| 外层 | PX | VOLQ | TURN | MULT | SIZE | MARGIN | LHB | BENCH | STATE |
|---|---|---|---|---|---|---|---|---|---|
| A:+ | 5 | 0 | 0 | 1 | 0 | 1 | 0 | 1 | 0 |
| A:- | 55 | 12 | 4 | 3 | 1 | 5 | 0 | 22 | 0 |
| A:* | 85 | 19 | 31 | 27 | 9 | 14 | 4 | 18 | 3 |
| A:/ | 51 | 14 | 2 | 0 | 1 | 5 | 0 | 7 | 1 |
| CS:RANK | 8 | 3 | 0 | 2 | 3 | 3 | 9 | 2 | 0 |
| W:MEAN | 19 | 2 | 0 | 0 | 0 | 1 | 1 | 1 | 0 |
| W:STD | 3 | 1 | 0 | 0 | 0 | 2 | 0 | 2 | 0 |
| W:MAX/MIN | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 |
| W:SUM | 8 | 2 | 0 | 0 | 0 | 1 | 1 | 4 | 0 |
| W:DELTA | 8 | 1 | 0 | 2 | 2 | 2 | 0 | 3 | 0 |
| W:ZSCORE | 9 | 2 | 1 | 0 | 0 | 0 | 1 | 4 | 0 |
| W:TS_RANK | 4 | 0 | 0 | 2 | 1 | 2 | 1 | 1 | 0 |
| W:CORR | 18 | 5 | 5 | 0 | 0 | 2 | 0 | 6 | 8 |
| W:ABS | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| W:IF | 46 | 4 | 14 | 4 | 4 | 2 | 1 | 10 | 41 |

`W:IF` 外层集中在 PX（46）与 STATE（41）——大量"市场状态门控 × 价格动量翻转"构造（见第 4 节饱和警告 S2）。

### 2.4 机制模板 × 字段族网格（18×9）

在 skeleton 串上做确定性模式匹配（18 个常见机制模板 × 9 族 = 162 格，**54 格非零、108 格为零**）。模板→骨架正则（可复现）：

| 模板 | 骨架匹配式 |
|---|---|
| MOM_core | `RET({F},N` |
| SURPRISE_ratio | `{F}/MEAN({F},` |
| TERM_SLOPE | `MEAN({F},N?)/MEAN({F},` |
| MEAN_spread | `MEAN({F},N?)-MEAN({F},` |
| ZSURPRISE | `ZSCORE({F},` |
| TSRANK_level | `TS_RANK({F},` |
| PATH_from_high / low | `{F}/MAX({F},` / `{F}/MIN({F},` |
| STOCH_pos | `({F}-MIN({F},` |
| DELTA_level | `DELTA({F},` |
| ACCUM | `SUM({F},` |
| VOLA_of_level | `STD({F},` |
| CORR_w_SELFRET | `CORR(RET({F},` |
| CORR_w_level | `CORR({F},` |
| SIGN_persist | `MEAN(SIGN({F}` |
| CS_level | `CS_RANK({F})` |
| CS_selfratio | `CS_RANK(({F}/{F}))` |
| MA_level | `MEAN({F},` |

命中数矩阵（行=模板，列=字段族；**0=结构空白格**）：

| 模板 | PX | VOLQ | TURN | MULT | SIZE | MARGIN | LHB | BENCH | STATE |
|---|---|---|---|---|---|---|---|---|---|
| MOM_core | 256 | 1 | **0** | **0** | **0** | 7 | **0** | 1 | **0** |
| SURPRISE_ratio | 1 | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| TERM_SLOPE | **0** | **0** | 1 | **0** | **0** | **0** | **0** | **0** | **0** |
| MEAN_spread | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| ZSURPRISE | 1 | 2 | 6 | **0** | **0** | 7 | 1 | **0** | 2 |
| TSRANK_level | 4 | 4 | **0** | 2 | **0** | 1 | 1 | **0** | 5 |
| PATH_from_high | 7 | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| PATH_from_low | 2 | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| STOCH_pos | 1 | **0** | **0** | **0** | **0** | **0** | **0** | **0** | **0** |
| DELTA_level | **0** | 1 | 5 | 3 | **0** | 8 | 1 | **0** | 8 |
| ACCUM | **0** | 20 | **0** | **0** | **0** | 1 | 1 | 23 | **0** |
| VOLA_of_level | **0** | 1 | **0** | **0** | **0** | **0** | **0** | 1 | **0** |
| CORR_w_SELFRET | 38 | **0** | **0** | **0** | **0** | 1 | **0** | **0** | **0** |
| CORR_w_level | 2 | 1 | 5 | **0** | **0** | **0** | **0** | 1 | **0** |
| SIGN_persist | 0* | **0** | **0** | **0** | **0** | **0** | 1 | **0** | **0** |
| CS_level | 9 | 1 | 22 | 23 | 2 | 3 | 3 | **0** | **0** |
| CS_selfratio | **0** | **0** | **0** | **0** | 1 | **0** | 1 | **0** | **0** |
| MA_level | 4 | 2 | 7 | **0** | **0** | **0** | **0** | 4 | 31 |

\* SIGN_persist|PX 计 0 是模板正则只匹配 `MEAN(SIGN(字段` 的口径假象：`MEAN(SIGN(RET(PX,N)),N)` 存在（2 条 r0 + r1 UVOL_volfreq_mismatch 等），**该格实际非空白，勿派工**。同理 SURPRISE_ratio 各格为 0 时须先对照 ZSURPRISE 近亲（z 形与比率形机制同族），PATH/STOCH 的 0 格须对照 TSRANK_level 分位形——本文第 3 节只保留通过近亲检验的格子。

### 2.5 条件化方式与窗口分布

- 条件化标志（非互斥，403 条）：无条件 **315（78.2%）**、field_gate 57、size_norm 11、px_gate 11、field_gate+rank_gate 7、field_gate+px_gate 2。
- 算子使用频次：RET 259（64.3%）、SIGN 120、MEAN 113、CS_RANK 106（26.3%）、IF 77（19.1%）、SUM 74、CORR 61、STD 47、DELTA 45、ABS 42、ZSCORE 33、MAX 28、TS_RANK 26、MIN 21、LOG 17。四则：`-` 242、`*` 218、`/` 160、`+` 92。
- 窗口使用（条数）：1日 161、2日 4、5日 81、10日 28、**20日 273**、30日 1、40日 1、**60日 104**、120日 7、250日 4。窗口值经哈希归一化，**不存在"窗口缺口"这种东西**。
- r1 研究员分工板块（153 条）：ACCDIST 筹码分布 12、BETA 贝塔形态 12、DIST 收益分布形态 12、FLOW 资金流结构 11、INFO 信息扩散 12、LIQ 流动性 13、NOMINAL 名义价格 11、PATH 路径效率 13、STATE 波动状态 15、UVOL 量方向结构 14、VALPX 估值×价格 14、VOLEST 波动估计量 14。

## 3. 空白清单（21 项，可直接粘贴进第三波任务书）

筛选规则：2.2/2.4 的空白格 → 近亲检验（同机制不同算子外壳视为已覆盖，否决）→ 经济机制过滤（A 股语境有可信机制才入选，纯算子排列组合否决）→ 可表达性检验（1.3）。每项含：骨架公式（窗口为示例值，注册时自定并被哈希归一化）、建议字段、机制一句话、最近邻差异声明、预判方向。**预判方向只是研究员的注册假设草案，不构成结论；全部 21 项已用引擎解析器验证可编译、且骨架在 403 条中零命中（截至 2026-09-11）。**

### 区块 A：换手率族的二阶时序结构（4 项）

> TURN 列在 MOM_core/STD/SUM/TS_RANK 全零（2.2/2.4），是最大的一块连贯空白。该族机制均围绕"注意力/分歧的过程量"。

- **A1 换手动量**：`RET(turnover_rate, 20)`
  - 字段：turnover_rate
  - 机制：换手率抬升=注意力与分歧加速；A 股散户注意力驱动下，换手加速往往透支未来买盘。
  - 最近邻差异：已有 ZSCORE(turnover_rate,20)（VALPX_B06 等水平脉冲）、DELTA(turnover_rate,20)（META_pxval_03 绝对增量）、MEAN(turnover,5)/MEAN(turnover,60)（r1 LIQ_turn_term_slope 比率斜率）；本构造是**相对变化率**（scale-free 动量），与绝对增量/水平 z/斜率均为不同骨架，且与三者单调性不同（涨后回落期 RET<0 而 z 可为正）。
  - 预判：negative（注意力透支）。
- **A2 换手变异系数**：`STD(turnover_rate, 20) / MEAN(turnover_rate, 20)`
  - 字段：turnover_rate
  - 机制：换手波动大=分歧状态不稳定、资金进出脉冲化，是投机度（speculation）的强度口径，而非水平口径。
  - 最近邻差异：LIQ_vol_cv_20 已做 `STD(volume,20)/MEAN(volume,20)`（量口径）；本构造用换手率口径——**换手率已除以流通股本，剔除了解释股变动与规模的影响**，量口径的变异系数会被送转/解禁造成的量能跳变污染。骨架 STD(TURN)=0（2.2）。
  - 预判：negative（投机度异象）。
- **A3 累计换手**：`SUM(turnover_rate, 60)`
  - 字段：turnover_rate
  - 机制：60 日累计换手=筹码交换充分度；A 股筹码理论下过度换手（击鼓传花）预示接力资金枯竭。
  - 最近邻差异：ACCUM 模板在 TURN=0；与 A1 的区别是**活跃度积分**（绝对量级）而非变化率；与 LIQ_turn_term_slope 的区别是绝对和而非短长比（比率对低基线敏感，和对基线不敏感）。
  - 预判：negative。
- **A4 注意力长窗分位**：`TS_RANK(turnover_rate, 250)`
  - 字段：turnover_rate（变体可用 volume_ratio 做同构）
  - 机制：当前换手在自身一年中的分位=注意力的历史相对位置；处于历史高位=拥挤末端，低位=冷门。
  - 最近邻差异：ZSCORE(turnover,20) 是短窗 z（对换手中枢漂移敏感），本构造是**非参数长窗分位**，抗分布漂移；与 TS_RANK(volume,5)（REL_cond_15）字段与窗长均不同。
  - 预判：negative。

### 区块 B：高阶共矩（1 项）

- **B1 协偏度（系统性偏度暴露）**：`MEAN(RET(close,1) * RET(close,1) * market_ret, 20)`
  - 字段：close、market_ret（变体 `MEAN(RET(close,1) * market_ret * market_ret, 20)`）
  - 机制：负协偏度（市场大跌时跌得更狠）的股票承担系统性偏度风险，应有补偿溢价（co-skewness premium）；A 股涨跌停与杠杆结构放大尾部不对称。
  - 最近邻差异：DIST_skew_m3_20 已做**自身**三阶中心矩、DIST_skew_hitrans_20 做了换手条件的三阶矩、BETA_semibeta_asym/crash_response 是二阶条件量；本构造是**与市场的三阶交叉矩**，度量的是偏度的系统性分量，非自身分布形状。
  - 预判：factor 值越负未来收益越高（即按 -co-skew 排序正向）；注册时需明确符号约定。

### 区块 C：量价与资金的领先-滞后结构（4 项）

> 领先项用恒等式"昨日值 = 今日值 − DELTA(今日值,1)"表达（1.3.2）。同字段领先-滞后不对称是信息扩散速度的直接度量。

- **C1 有符号量价共振（连续式）**：`CORR(RET(close,1), turnover_rate, 20)`
  - 字段：close、turnover_rate
  - 机制：量价同向（涨时放量）=需求真实推动；量价背离=对倒/诱多嫌疑。
  - 最近邻差异：VOLEST_turn_couple_div/B10 内含 `CORR(turnover_rate, ABS(RET(close,1)),20)`（**绝对**收益=振幅耦合，无方向）；META_pxval_10 是 `CORR(close, volume,20)`（水平-水平）；本构造是**带方向收益**与量的相关——区分"健康放量上涨"与"放量滞涨/放量下跌"。
  - 预判：positive（同向度=趋势质量）。
- **C2 量价领先不对称**：`CORR(RET(close,1), DELTA(turnover_rate,1), 20) - CORR(RET(close,1), turnover_rate - DELTA(turnover_rate,1), 20)`
  - 字段：close、turnover_rate
  - 机制："量先价行"（吸筹在先）与"价先量行"（对倒在后）的相对强度；前者预示延续，后者预示诱多反转。
  - 最近邻差异：INFO_attention_mkt_lag 用同一恒等式做的是**市场收益滞后 × 换手**（市场级领先）；本构造是**个股自身量与自身价的领先结构**，骨架在 403 条中零命中。
  - 预判：positive（量先价行主导时）。
- **C3 杠杆资金领先性**：`CORR(RET(close,1), DELTA(margin_balance,1), 20) - CORR(RET(close,1), margin_balance - DELTA(margin_balance,1), 20)`
  - 字段：close、margin_balance
  - 机制：融资盘增量领先价格=杠杆资金抢跑；价格领先融资盘=杠杆盘追高（脆弱买盘）。
  - 最近邻差异：META_pxflow_08 是 `CORR(RET(close,1), RET(margin_balance,1),20)` 纯**同步**相关；FLOW_lev_turnover_comove 是杠杆×换手；本构造用同步项减滞后项把**领先分量**分离出来。
  - 预判：positive（杠杆先行=知情/强需求）。
- **C4 波动冲击的投机弹性**：`CORR(turnover_rate, DELTA(market_vol,1), 60)`
  - 字段：turnover_rate、market_vol
  - 机制：市场波动上升时换手放大的股票=高投机需求载体（彩票偏好在高波动期加剧），拥挤且脆弱。
  - 最近邻差异：INFO_volshock_stance 是 `CORR(RET(close,1), DELTA(market_vol,1),60)`（**价格侧**反应）；BETA_panic_turnover 是急跌日（market_ret 门控）换手与市场**收益**的相关；本构造是换手对市场**波动率变化**的反应斜率。
  - 预判：negative。

### 区块 D：日内微观结构残余（3 项）

> 隔夜/日内分解（REV_path、STATE_risk、PATH、INFO、BETA_gap_beta）已相当饱和，但"序列相关""区间内位置""量加权质量"三个角仍空白。

- **D1 隔夜-日内序列相关**：`CORR(open/preclose - 1, close/open - 1, 60)`
  - 字段：open、preclose、close
  - 机制：隔夜跳空被日内延续（正相关=信息定价一致）还是被日内回补（负相关=散户日内对冲、定价低效）；回补型个股的跳空信息含量低。
  - 最近邻差异：REV_path_07/08/13、STATE_risk_onvolratio、PATH_overnight_length_share 都是**均值/方差/幅度**层面的分解；CORR(gap, intraday)=0 命中（2.4 核查），是**序列相关结构**层面。
  - 预判：positive（同向性=隔夜信息真实、动量延续）。
- **D2 开盘位置**：`MEAN((open - low) / (high - low), 20)`
  - 字段：open、low、high（一字板日分母 0 → None，failure_modes 披露）
  - 机制：开盘落在当日区间的位置——持续"高开收在区间上部"=隔夜信息被日内买盘确认；"高开落在区间下部"=高开出货。
  - 最近邻差异：REV_vola_06/14 是 **close** 在日内区间的位置（收盘承接），DIST_gap_confirm 是 gap×日内方向的**符号一致性**；开盘位置是隔夜信息在日内区间中的落点幅度，三者互不同构。
  - 预判：negative（开盘位置长期偏高=出货型高开）。
- **D3 放量跳空质量**：`MEAN(turnover_rate * (open/preclose - 1), 20)`
  - 字段：turnover_rate、open、preclose
  - 机制：换手加权的隔夜跳空=带真实成交的跳空（需求）与无量跳空（噪声/操纵）之别；无量跳空易回补。
  - 最近邻差异：META_margin_08 是 gap × ZSCORE(margin_buy)（杠杆条件）；VALPX_B02 是 gap × 估值秩；LIQ_gap_z_fade 是 gap 自身 z。gap×换手乘积零命中，度量的是跳空的**量能背书**。
  - 预判：positive。

### 区块 E：筹码成本结构（1 项）

- **E1 成本线期限结构（成本线上移速度）**：`(SUM(close*amount,5)/SUM(amount,5)) / (SUM(close*amount,60)/SUM(amount,60)) - 1`
  - 字段：close、amount
  - 机制：短期成交成本线相对长期成本线的抬升=近期买家愿意付更高价格（承接强度）；下移=套牢盘加深。A 股筹码结构语境下成本线斜率是获利/套牢结构迁移的直接度量。
  - 最近邻差异：LIQ_amount_anchor_dev 已做 close 相对 **20 日成本锚的水平偏离**（获利盘厚度，水平量）；本构造是**成本线自身的短长斜率**（迁移速度、差分量），与水平偏离对横盘/阴跌的判别不同。注意窗口值经哈希归一化后与 20 日锚版本不同骨架（分子分母结构不同）。
  - 预判：positive。

### 区块 F：事件密度与路径残余（3 项）

- **F1 新高事件密度**：`SUM(0.5*(1+SIGN(DELTA(MAX(close,20),1))), 60)`
  - 字段：close（变体：MIN 版为"新低密度"，方向相反）
  - 机制：DELTA(MAX(close,N),1)>0 即"创 20 日新高"事件；60 日内新高事件密度=突破的持续性/动量事件流。
  - 最近邻差异：PATH_box_expansion_60_20 是箱体**宽度**变化（振幅动力学）；STATE_risk_maxtail 是单日极值**水平**；PATH_dirflip_freq 是方向翻转密度。新高**事件计数**骨架零命中（DELTA(MAX=1 命中，仅 box_expansion 一条且语义不同）。
  - 预判：positive（新低密度变体 negative）。
- **F2 动量峰值痕迹**：`MAX(SUM(RET(close,1),5), 20)`
  - 字段：close（变体：MIN 版=最弱 5 日动量谷）
  - 机制：终点动量相同的情况下，"曾经出现过的最快 5 日加速"留下急涨痕迹；A 股短动量反转主导，急涨痕迹预示透支。
  - 最近邻差异：REV_resid_03 是 `MIN(SUM(残差,5),20)`（残差侧、谷值）；PATH_jump_concentration 是单日跳点占比（日粒度）；本构造是**原始价格、滚动 5 日收益在 20 日窗内的峰值**——"速度的极值"，非"极值日的速度"。
  - 预判：negative。
- **F3 高振幅日换手占比**（边缘候选，低优先）：`SUM(turnover_rate*(high-low)/close, 20) / SUM((high-low)/close, 20)`
  - 字段：turnover_rate、high、low、close
  - 机制：换手集中在高振幅日=博弈型/投机型换手结构；换手均匀=配置型资金主导。
  - 最近邻差异：ACCDIST_quiet_ad_20 是**低量日**条件化的 CLV 流（条件变量是量能分位、对象是方向流）；本构造条件变量是振幅、对象是换手强度本身，骨架零命中。列为本区块边缘项：若近亲检验收紧可放弃。
  - 预判：negative。

### 区块 G：横截面代数与条件化结构（4 项）

- **G1 跨乘数质量因子（净利率）**：`CS_RANK(ps_ttm / pe_ttm)`
  - 字段：ps_ttm、pe_ttm（failure_modes：pe≤0 的亏损股使比值语义翻转，须声明处理策略，如改用 `CS_RANK(LOG(ps_ttm) - LOG(pe_ttm))` 并披露亏损股处置）
  - 机制：ps/pe = E/S = 净利率——不用任何财报表、纯由 daily_basic 乘数代数得到的盈利质量代理（定价权/护城河）。
  - 最近邻差异：VAL_R0_001 是 `CS_RANK(pb)+CS_RANK(ps_ttm)`（加法组合，两个独立水平量）；MULT×MULT 比值全 corpus 零命中（CS_selfratio|MULT=0）。乘数相除 = 嵌入第三种基本面量纲，非组合。
  - 预判：positive。
- **G2 跨乘数质量因子（ROE 倒数）**：`CS_RANK(pe_ttm / pb)`
  - 字段：pe_ttm、pb（同上亏损股披露要求）
  - 机制：pe/pb = B/E = 1/ROE，低值=高净资产回报率质量暴露（价值之外的纯质量维度）。
  - 最近邻差异：同 G1；与 VALPX_B04（低价×低波）的"质量"是代理路径完全不同（本构造直接含 ROE 信息）。
  - 预判：negative（pe/pb 越小越好）。
- **G3 跨家族风格门控**：`IF(0.5*(1+SIGN(market_vol - MEAN(market_vol,60))), CS_RANK(RET(close,20)), CS_RANK(dv_ttm))`
  - 字段：market_vol、close、dv_ttm
  - 机制：A 股风格切换剧烈——高波动环境动量占优、低波动环境股息/低波占优；门控在**不同信号家族之间切换**，而非翻转同一信号的符号。
  - 最近邻差异：现有全部 IF 门控（r0 STATE_vol/STATE_width、META_combo）都是**同族翻符号或换窗口**（如 META_combo_11/14 对 pb 翻符号、STATE_vol_10 对 LOG(pb) 翻符号）；跨家族分支选择零命中。这是条件化方式维度上真正的未开发结构。
  - 预判：分支各自方向（高波支 positive 动量、低波支 positive 股息）。
- **G4 复合状态 AND 门控**：`IF(SIGN(SIGN(market_vol-MEAN(market_vol,60)) * SIGN(adv_dec_ratio-MEAN(adv_dec_ratio,60)) - 0.5), -RET(close,5), RET(close,20))`
  - 字段：market_vol、adv_dec_ratio、close
  - 机制：单条件门控只能区分"一种状态"；波动抬升**且**广度扩张的共振态（情绪与风险同时恶化/改善）下反转结构不同——复合态是情绪周期的更有辨识度的切分。
  - 最近邻差异：77 条 IF 全部是**单条件**（或单字段的算术组合条件）；STATE_width_09 的 `ZSCORE(adv)-ZSCORE(limit)` 是两状态的算术差仍属单条件；`SIGN(乘积-常数)` 的严格 AND 骨架零命中。
  - 预判：分支各自方向，注册时声明。

### 区块 H：换手连续性（1 项）

- **H1 换手连升占比**：`MEAN(SIGN(DELTA(turnover_rate,1)), 20)`
  - 字段：turnover_rate（变体：量能自相关连续式 `CORR(volume, volume-DELTA(volume,1), 20)`，机制同族）
  - 机制：连续多日换手抬升=持续吸筹（或持续派发），是注意力的"过程持续性"；单日脉冲（已有构造覆盖）与连续性是不同信息。
  - 最近邻差异：FLOW_lev_inflow_persistence 是 `MEAN(SIGN(DELTA(margin_balance,1)),20)`（**杠杆余额**侧同构）；MEAN(SIGN(RET(close,1)),20) 是**价格方向**侧；换手侧零命中。与 A1 的差异：只看方向天数占比，对幅度免疫。
  - 预判：negative（连续放量后透支）。

## 4. 已饱和方向警告（避免撞车）

以下方向在 403 条中已有密集覆盖。第三波研究员若仍提交"同机制 + 外壳变体"，将在查重与近亲判断中被淘汰。每条附证据密度与已覆盖的具体变体。

- **S1 价格动量/反转本体**：RET×PX 嵌套 256 次、`A:-` 外层 55 条；单窗动量、残差动量（market/industry 双基准）、IR 形（`rel_path_ret_per_vol_20`、`rel_path_ir_20`——风险调整动量**已存在**，勿再提交"Sharpe 动量"）、z 形、TS_RANK 形、加速度、峰值谷值、期限结构（`rel_rank_10` 20v60 秩差）。**任何窗口上的价格动量/反转变体都已无结构空间**。
- **S2 市场状态门控 × 信号翻符号**：`W:IF` 外层 58 条 + STATE 列 IF 42 次。r0 STATE_beta/vol/width 三波把 market_vol/adv_dec_ratio/limit_up_count 的门控 × {动量、反转、波动、换手、pb、dv_ttm、total_mv、margin、volume_ratio、CORR-beta} 全部做过。唯一残余是**跨家族分支选择**（G3）与**复合 AND 条件**（G4），其余门控变体视为撞车。
- **S3 贝塔/市场相关形态**：CORR×BENCH 41 次；r0 STATE_beta 13 条 + r1 BETA 12 条已覆盖：半贝塔不对称、压力贝塔、贝塔迁移、贝塔不稳定、系统性占比、stampede（β×换手）、quiet drift、fairweather、gap-beta、恐慌换手响应、crash response、vol-beta。该板块关闭。
- **S4 残差动量全家族**：REL_*（15 条）+ REV_resid（15 条）+ rel_path_*：市场/行业残差动量的和、均值、IR、z、加速度、TS_RANK、MIN/MAX 尾部、下行天数占比、残差×流动性/换手/振幅交互全部存在。行业成员映射冻结（industry_ret_l1 只是 31 行业等权均值，非个股行业收益），"真行业中性"不可表达，勿再派工。
- **S5 日内微观结构主干**：K 线解剖（实体/影线/CLV/振幅）、隔夜-日内分解（均值/方差/幅度占比/频率/β）、gap 确认（DIST_gap_confirm）、上影下影不对称（REV_vola_07/13/14、VOLEST_updown_swing_var_asym）已覆盖约 40 条。残余仅 D1/D2/D3 三个角。
- **S6 有符号量流（OBV/CMF/AD 家族）**：r0 rel_path_volw/REV_path_14 + r1 UVOL 14 条（水平、加速度、极化、频率错配、动量确认、swing、大单纯度、广度门控）+ ACCDIST 的 CLV×成交量全家族（含 MFI 比值 `ACCDIST_mfi_ratio_20`、低量日条件 `ACCDIST_quiet_ad_20`、下跌吸收 `ACCDIST_down_absorb_20`）。带符号量流的一切常见变体已做完。
- **S7 波动率估计量与期限结构**：STD(RET) 及其与振幅估计量的差/比（VOLEST 14 条：term slope、stability gap、squeeze `STATE_risk_squeeze`、vol-of-vol `STATE_risk_volofvol`、ARCH 持续性、半方差份额 `dsvar_share`、波动态自分位）、波动加速度。注意 STD(RET,N1)/STD(RET,N2) 与 5/20 版同哈希——"新窗口的波动期限结构"=撞车。
- **S8 估值水平与估值×X 交互**：CS_RANK(MULT) 26 次、pb 交互 23 条（r0 META_pxval/VAL_* + r1 VALPX 14 条：价值×非流动性/低波/重估/再发现/注意力弹性/隔夜/提价、名义价差）。估值**动量**也已被 DELTA(LOG(pb/pe))（VAL_R0_009/010、META_pxval_06、VALPX_B05）与动量分解 `VALPX_B01_mom_decomp_rerating`（RET(close)−RET(close/pe)）覆盖。残余仅跨乘数**比值代数**（G1/G2）。
- **S9 融资融券流**：META_margin/pxflow + r1 FLOW 共 30+ 条：水平、增量、二阶差分（加速度）、z、RET、买卖秩差、余额/成交额渗透及其 STD/DELTA、余额/circ_mv 拥挤 250 日分位、余额波动、涨跌门控、杠杆-价格同步相关、杠杆×换手共振。TERM_SLOPE|MARGIN 空白格经近亲检验否决（与加速度 META_margin_01、渗透率族同机制）。该板块实质关闭，残余仅 C3 领先性一角。
- **S10 龙虎榜**：META_flowlhb 14 条 + r1 渗透率 2 条已做：水平秩、规模归一、机构占比/乘积、净额结构变换、Δ、密度、z、TS_RANK、SUM。**其中窗口算子版（08/09/10/13）因稀疏字段结构性近死（1.3.1），属于"占坑但不可用"——既不要模仿也不要重复**。LHB 可行空间仅剩同日交互组合，且 r0/r1 已布满；建议整体回避。
- **S11 流动性/Amihud**：r1 LIQ 13 条（Amihud 斜率、冲击不对称、量变异系数、VWAP 溢价、成交额成本锚偏离、量峰集中度、流动性共同性、迁移）+ r0 REV_liq/META_pxflow。Amihud 水平/z/斜率/交互、换手-振幅深度比、量能 CV 全部存在。
- **S12 收益分布形态**：r1 DIST 12 条：三阶标准化偏度、四阶峰度、1.5σ 尾频率、尾概率不对称、高换手条件三阶矩、上行为主占比、爆发度、崩盘深度、跳空确认。**自身分布的 2—4 阶矩已饱和**；残余是与市场的交叉矩（B1）。
- **S13 名义价格效应**：r1 NOMINAL 11 条（价格秩、低价×高换手、tick 非流动性门控、价-市值秩差、价-pb 秩差、股本扩张错觉、低价×涨停潮门控、价格秩迁移、低价×彩票、高价×低换手）。低价股组合空间已布满。

## 5. 附录：被经济机制过滤或近亲检验否决的空白格

形式上空白、但经检验**不予派工**的格子（记录否决理由，供第三波查重申诉时对表）：

| 空白格 / 候选构造 | 否决理由 |
|---|---|
| MOM_core × SIZE（`RET(circ_mv,N)` 市值动量） | A 股无稳健的市值动量机制；size 是水平异象非动量异象 |
| MOM_core × LHB、TERM_SLOPE/CORR 等 × LHB | 1.3.1 稀疏约束，窗口算子结构性近死 |
| STD × MULT（`STD(pb,60)` 估值波动） | pb≈price/book，book 缓变 → 机制上≈价格波动率（S7 已覆盖），伪空白 |
| MOM_core × MULT（`RET(pe_ttm,N)` 估值动量） | 已被 DELTA(LOG(pb/pe)) 与 VALPX_B01 动量分解近亲覆盖（S8） |
| SURPRISE_ratio × VOLQ（`volume/MEAN(volume,N)` 量能突变比） | 与 ZSCORE(volume,20)（REV_liq_volz_x_rev）机制同族，z 形与比率形近单调 |
| PATH_from_high/low、STOCH_pos × VOLQ/MULT/TURN | 与 TS_RANK(volume,·)/TS_RANK(pb,250) 分位形同机制（量能/估值异常位置） |
| MEAN_spread × PX（双均线差/乖离率） | 近亲链已覆盖：REL_rank_13 `CS_RANK(close/MEAN(close,120)-1)` 长乖离秩 + rel_rank_10 动量期限结构 + REV_path 系列；MA spread 在数学上≈动量差的平滑版，机制增量不足 |
| turnover_rate/turnover_rate_f（换手口径锁仓比） | 与 VALPX_B12 `CS_RANK(total_mv/circ_mv)×CS_RANK(turnover)` 同为股本锁仓结构代理 |
| STD(margin_buy,N) 杠杆脉冲不稳 | 与 META_margin_07 `STD(RET(margin_balance,1),20)` 近亲 |
| TERM_SLOPE × MARGIN（`MEAN(margin_buy,5)/MEAN(margin_buy,20)`） | 与 META_margin_01 二阶差分（加速度）同机制 |
| TERM_SLOPE × VOLQ（量能期限结构） | r1 LIQ_turn_term_slope 已做换手率版；时序上 turnover_rate 与 volume 对单只股票成比例，同一哈希级近亲 |
| CORR(RET, turnover) 之外的纯量价领先（如 price-lag×volume） | 需要滞后恒等式嵌套过深且与 C1/C2、INFO_attention_mkt_lag 近亲 |
| MAX/SUM 量能事件密度（`MAX(amount,N)/SUM(amount,N)` 类集中度） | LIQ_vol_max_share `MAX(volume,20)/SUM(volume,20)` 已做 |
| 涨停触及频率（`SUM(0.5*(1+SIGN(RET(close,1)-0.095)),N)`） | **STATE_risk_limfreq 已存在**（r1 STATE 波段）；事件密度骨架在 gap（STATE_risk_gapfreq）、尾部（DIST_tailfreq_20）、上行占比（DIST_updom_share_20）也已布满；振幅事件密度同样按此否决 |
| BIAS 单独派工 | 见 MEAN_spread × PX 行 |
| 任何 BENCH/STATE 字段单独成因子 | 截面常数无分散度（1.3.5）；CS_RANK×STATE=0 是结构必然不是缺口 |
| 任何"换窗口"变体 | 哈希归一化后同构（1.1） |
| industry_member 相关、事件表引用 | 冻结/封存（任务指定排除） |

## 6. 复现说明

分析用临时脚本已按协议删除（未入仓库）。复现路径：解析两处 JSONL → 逐条 `experiments.factor_miner.compiler.compile_formula` → 按 1.2 伪代码渲染 shape/skeleton 与 P1/P2/P3 → 按 1.2.1 字段族映射聚合 2.2—2.4 矩阵 → 对候选构造在 403 条 skeleton 串上做确定性正则检索确认零命中 → 近亲检索用公式全文正则（本文所有"零命中"结论均同时给出检索口径）。所有窗口值在矩阵层面折叠，检索层面用具体示例值——两条口径互不冲突，因哈希归一化保证窗口值不影响结构判定。

> 快照注记(2026-09-11 送审前):本文写作时点池为 12 文件/153 条;后续 W3C/W4D/W4EF 波次增量至 17 文件/215 行,本文矩阵与饱和结论基于写作时点语料,冻结清单另出。
