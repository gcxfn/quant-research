# band engine v1.4.1 独立复核留证（2026-09-20）

复核代理独立执行；本文件仅汇总已在复核对话中给出的证据，不产生新结论。

## 1. sha256 亲验
- `src/quant/backtest/band_engine.py`：200562 字节，
  sha256 = a01cb29ce4cf214814dd51679295f70ac780dc5dffb270ea1f0a466b0675abf3
  （hashlib 现算，与任务书期望一致）。

## 2. §10.8 五条语义对照（band_engine.py 行号）
1. tp1 列可选：L1181-1184 `_ZONES_REQUIRED` 无 tp1_mult/tp1_frac；L1300-1303
   四个 tp 列均 `row.get`。PASS
2. null/缺列 ⇒ 零止盈意图：L2373-2377 `tp_specs` 仅在 `zone["tp1"] is not None`
   时填充；tp1 为 None 时 for 循环零次，无任何 `ztp` 订单；ladder/止损/失效/
   回收代码路径未包入该条件。NaN 进供值分支被 L1313 `math.isfinite` 拒绝。
   PASS
3. tp1 有值断言逐字保留：L1307-1310 供值成对、L1313-1315 finite>0、
   L1316-1318 frac∈(0,1]；既有 28 项 zones 测试（t01-t29，含 t28
   tp2_frac!=1 拒绝）全部在 463 passed 内。PASS
4. tp1 null + tp2 非空 ⇒ BandContractError：L1345-1349 elif 分支，
   tp2 任一字段非 None 即拒（含 tp2 half-supplied）。PASS
5. 零档卖点语义：止损 L2464-2468（low<line 触发、fill=min(line,open)）、
   失效 L2578-2592（会话 low vs p0-invalid_mult×sigma0，仅清未成交档）、
   expiry/席位回收未触碰。PASS

## 3. pytest 全量
- `python -m pytest tests -q` → **463 passed**（14.50s，6 个 polars
  UserWarning 来自 p2r13_lowfreq，与本引擎无关）。

## 4. W9/t30 手工重推（初始现金 200000，佣金 max(万1×名义,5)，
   卖出印花税 0.0005，2024-01 在边界后）
- a1 限价 = p0−0.5σ = 9.5；(D1,pm) 决策挂单 → live (D2,am)；
  D2am low 9.2 触及 → 400×9.5 = 3800，佣金 5 → 现金 −3805 = 196195。
- (D2,am) 决策锚 close 9.3 → HWM 9.3 → 止损线 9.3−3×1 = 6.3（棘轮）。
- (D2,pm) 会话 low 7.9 < 失效线 10−2×1 = 8.0 → 取消 a2/a3
  （tier_invalidated=2，ref=7.9），止损线不动。
- D3am low 6.2 < 6.3 → 止损触发，成交 min(6.3, open 7.5) = 6.3；
  400×6.3 = 2520，佣金 5 + 印花税 1.26 → 净 +2513.74。
- 期末 settled_cash = 196195 + 2513.74 = **198708.74**，与 t30 断言
  逐分一致。PASS

## 5. 锚比对（compare_anchors.py 重跑 + 独立抽验）
- 重跑 compare_anchors.py（只读）：16/16 filecmp(shallow=False)
  BYTE-EQUAL；锚2/锚3 stats.stats 剔除 {engine_version, wall_s} 后逐键
  EQUAL；exit=0。
- hashlib 独立抽 3 帧（每锚一帧）EQUAL，哈希前缀 11f8af46… / 2dde9457… /
  123e4cb3… 与锚 manifest 内 pin 记录互证。
- manifest 引擎 sha：锚1/锚2 sha_at_start == sha_at_end == c5c07303…；
  锚3 == a01cb29c…（与当前工作区引擎逐字一致），锚3 report 记录
  5/5 帧 .equals() 一致。
- stats 版本标签：新锚2 = "band_engine v1.4"（标签前），新锚3 =
  "band_engine v1.4.1"；pin 参照分别为 v1.2 / v1.3。剔除 engine_version
  后两者均 EQUAL —— 两版引擎的可见差异正落在被剔除字段上，§10.7 惯例
  恰好覆盖。
- 判断：锚1/2 产于标签前版本，其对最终 sha 的覆盖依赖"仅标签差异"声明；
  锚3 以最终 sha 直接复验 F3R3 世界零回归，zones 行为面由 t30/t31/t32
  与全量测试覆盖。结论有效。

## 6. 探针证据链
- 原始探针（030215-f4r2，pin v1.4 = 7ad35014，engine_pin_match=true）：
  null→TypeError、NaN→BandContractError、缺列→missing required column，
  三形式全拒 → §10.8 触发依据成立。
- rerun 探针（本 run tmp，03:19）：null→RAN 零 ztp、缺列→RAN 零 ztp、
  NaN→BandContractError —— 与 §10.8 条款 2"null/缺列可用、NaN 属供值
  非法拒绝"自洽。
- 备注（MINOR）：rerun JSON 的 `frame_level_feasible: false` 是旧判定
  规则（要求 NaN 也 RAN）的残留字段，不能读作"新引擎不可行"；rerun JSON
  未记录实际引擎 sha，行为面以 t30/t31（463 内通过）为准。

## 7. MINOR 事项汇总
1. `outputs/anchor3_relabel/` 为空目录残留（03:26 创建未使用）。
2. 锚1/2 产物来自标签前版本 c5c07303，对最终 sha 的覆盖经锚3 直接复验
   与"仅版本常量差异"证据链间接闭合（stats 剔除字段恰为唯一可见差异）。
3. rerun 探针 JSON 的 feasible=false 字段语义残留、缺实际引擎 sha 记录。

## 结论：APPROVE（无 BLOCKER）
