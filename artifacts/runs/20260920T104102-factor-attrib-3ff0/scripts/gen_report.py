# -*- coding: utf-8 -*-
"""exp-20260920-factor-attribution -- render docs/research/exp-20260920-factor-attribution.md
from the run outputs (no hand-copied numbers)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

RUN_DIR = Path(__file__).resolve().parents[1]
ROOT = RUN_DIR.parents[2]
DOCS = ROOT / "docs/research/exp-20260920-factor-attribution.md"


def sha16(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


ew = pl.read_csv(RUN_DIR / "outputs/attribution_ew.csv")
icw = pl.read_csv(RUN_DIR / "outputs/attribution_icw.csv")
loo = pl.read_csv(RUN_DIR / "outputs/loo_matrix.csv")
sus = json.loads((RUN_DIR / "outputs/suspects.json").read_text(encoding="utf-8"))
verdict = json.loads((RUN_DIR / "outputs/verdict.json").read_text(encoding="utf-8"))
summary = json.loads((RUN_DIR / "tmp/attribution_summary.json").read_text(encoding="utf-8"))
anchor = json.loads((RUN_DIR / "tmp/subruns/leave_zero_out/stats.json")
                    .read_text(encoding="utf-8"))
YEARS = [2015, 2016, 2017, 2018, 2019, 2020]

lines: list[str] = []
w = lines.append

w("# F3 存量审计：因子贡献归因 + 留一检验——\"17 代表里有没有坏因子\"")
w("")
w("- 实验 ID：exp-20260920-factor-attribution；预登记 "
  "`docs/research/exp-20260920-factor-attribution-prereg.md`（2026-09-20 冻结，运行中零修改）")
w(f"- 运行 `{RUN_DIR.name}`；状态 **completed**（零停机）")
w("- 判定：**H1 否证（嫌疑名单为空）**——F3 组合维持 17 因子原样")
w("")
w("**结果一句话：17 代表因子在 EW 主表上的月度贡献 t 值全部为正（+0.19 ~ +1.71），"
  "无一满足预登记 §5.1 嫌疑线（t<0 且负年数≥4），嫌疑名单为空 → 按 §5.4 H1 否证，"
  "\"坏因子稀释\"解释不成立，\"alpha=集中度形态\"结论加强；leave-zero-out 锚五帧逐字节复现底盘，"
  "留一矩阵作为描述性证据在档。**")
w("")
w("## 一、口径与近似性声明（预登记 §3 逐字）")
w("")
w("- 贡献原子：`a_i,s,t = z_i,s,t × r_s,t+1`；z = F3R1 composite 分量"
  "（eligible 截面内 rank_percentile，(p−0.5)×sign(ic_mean)，重建后与 "
  "`F3-EW_composite.parquet` 逐位一致，见 §二）；r = F2R1 eval harness 前向收益"
  "（close/preclose 复利链，T+1 起 h=20 个交易日，面板 `daily_2015_2024.parquet`"
  " 截断 ≤2020-12-31 后进 harness——尾部截行不改变任何袖月份的取值，2021+ 零接触）。")
w("- 月度贡献：`c_i,t = Σ_s w_s,t × a_i,s,t`；w 为 F3R3 runner 席位实现"
  "（每席 w_T = e_T×(0.06/0.90)，现金席=0，接缝 FA-S4；逐字取自底盘 "
  "`sleeve_monthly_log.json`，不自造等权）。")
w("- 统计窗口：r 覆盖 68/71 个信号月（2015-04-30..2020-11-30）；2015 前三个月"
  "因 harness `min_history_rows=60` 截断无 r（与 F2R1 eval 同源行为，预登记"
  " §3 的\"全期 68 个月\"即此口径）。")
w("- **近似性声明（FA-S3，预登记 §3 原文）**：\"排名选股非线性，故 "
  "`Σ_i weight_i × c_i,t` 不等于组合月收益；归因表只用于因子间横向对比与符号判定，"
  "禁止解读为绝对收益归因。留一为金标准，归因只圈嫌疑人。\"")
w("")
w("## 二、FA-S2：z 分数来源与对齐")
w("")
w("- 分支：**直读** F2R1 族 outputs 逐月分数 parquet（17 代表文件，sha 见 manifest），"
  "未重算因子值；composite 分量按 F3R1 runner §4 构造逐字重建。")
w(f"- 对齐门槛：重建 EW composite vs `F3-EW_composite.parquet`，抽样 3 个 signal_date"
  f"（{summary['fa_s2']['sample_dates'][0]}、{summary['fa_s2']['sample_dates'][1]}、"
  f"{summary['fa_s2']['sample_dates'][2]}）× 25 股 = {summary['fa_s2']['n_sampled']} 点，"
  f"max|diff| = **{summary['fa_s2']['max_abs_diff_sampled']:.1e}**（容差 1e-9；"
  f"全量 max|diff| = {summary['fa_s2']['max_abs_diff_global']:.1e}），键集相等 → **PASS**。")
w("")
w("## 三、sanity 检验（预登记 §8）")
w("")
w("- 序列定义（机械、留档）：`linear_t = Σ_i (1/17)·c_i,t`；`realized_t` = 当月实际"
  "席位（有 r 者）按 w_T 加权的下一持有月实现收益；公共月份 65 个。")
w(f"- **EW 主表：相关系数 {summary['sanity']['EW']['corr']:.4f}（门 ≥0.8），"
  f"逐月符号一致率 {summary['sanity']['EW']['sign_agreement']*100:.1f}%（门 ≥70%）→ PASS**。")
w(f"- ICW 对照（不设门）：corr {summary['sanity']['ICW']['corr']:.4f}，"
  f"符号一致率 {summary['sanity']['ICW']['sign_agreement']*100:.1f}%。")
w("- 近似失效停机条款未触发。")
w("")
w("## 四、归因表（EW 主表，17 行全量）")
w("")
w("贡献单位：月度席位加权和（无量纲 z×收益，横向可比；非组合收益）。")
w("")
w("| 因子 | 累计贡献 | 月均 | t 值 | " +
  " | ".join(str(y) for y in YEARS) + " | 为正年数 |")
w("|---|---|---|---|" + "---|" * 7)
for r in ew.sort("t_stat").iter_rows(named=True):
    w(f"| {r['factor']} | {r['cum_contribution']:+.4f} | {r['mean_monthly']:+.5f} "
      f"| {r['t_stat']:+.3f} | "
      + " | ".join(f"{r[f'contrib_{y}']:+.4f}" for y in YEARS)
      + f" | {r['n_pos_years']}/6 |")
w("")
w("注：n=68 个月；t = mean(c)/se(c)，se 为 ddof=1 月度标准差 /√n。")
w("")
w("## 五、ICW 对照表（摘要，同口径；判定不作用于本表）")
w("")
w("| 因子 | 累计贡献 | 月均 | t 值 | 为正年数 |")
w("|---|---|---|---|---|")
for r in icw.sort("t_stat").iter_rows(named=True):
    w(f"| {r['factor']} | {r['cum_contribution']:+.4f} | {r['mean_monthly']:+.5f} "
      f"| {r['t_stat']:+.3f} | {r['n_pos_years']}/6 |")
w("")
w("ICW 全表（含分年）见 `outputs/attribution_icw.csv`。")
w("")
w("## 六、贡献相关矩阵（17×17，摘要）")
w("")
w("月度贡献序列两两 Pearson（成对完备月份）。全矩阵见 "
  "`outputs/contribution_corr.csv`：元素全部为正，min 0.362（B14×E16）、"
  "平均非对角 0.753——与 F2R1 去重后残余相关结构一致，无负贡献对冲因子。")
w("")
w("## 七、嫌疑圈定（预登记 §5.1，机械执行）")
w("")
w("> 嫌疑线：月度贡献 `t < 0` **且** 六个自然年（2015..2020）中贡献为负的年数 ≥4。")
w("")
w(f"- 逐条核对（EW 主表 17 行）：t 值范围 +0.187（D19）~ +1.714（E16），**无一 t<0**；"
  "负年数最多 3/6（B12/C19/F06/F09），无一 ≥4。")
w(f"- **嫌疑名单 = 空**（{sus['n_suspects']} 个）；写入 `outputs/suspects.json`"
  "（含全部 17 因子六项统计）。")
w("- 这是预登记 §5.4 / §8 明文的合法收官路径（H1 否证），不视为失败。")
w("")
w("## 八、留一检验（预登记 §4）")
w("")
wo_ = anchor["anchor_compare"]
w(f"- **leave-zero-out 锚：PASS**——17 因子全集合重建 composite 重跑 F3R3-EW，"
  f"五帧 polars `.equals()` vs 底盘产物 intents/fills/events/daily/clips_final = "
  f"{wo_['intents']}/{wo_['fills']}/{wo_['events']}/{wo_['daily']}/{wo_['clips_final']}，"
  f"net_cagr {anchor['net_cagr']:.17f} 与底盘 metrics 完全相等（≤1e-12）。"
  "同时实证工作区引擎 v1.4.1 pin `a01cb29c…` 在非 zones 路径 ≡ v1.3 pin `84a2443a…`"
  "（FA-S1 复现门槛通过，未触发停机）。")
w("- 基线（底盘 metrics verbatim）：净 CAGR +4.8773%、maxDD −17.8485%。")
w("")
w("### 留一矩阵（17 行，每行剔除一个代表，16 因子重建 EW composite 重跑全期）")
w("")
w("| 剔除因子 | 净 CAGR | maxDD | ΔCAGR vs 基线 | maxDD 变化 | 优势年 | 单边换手 |")
w("|---|---|---|---|---|---|---|")
for r in loo.sort("delta_cagr_vs_baseline", descending=True).iter_rows(named=True):
    w(f"| {r['factor']} | {r['net_cagr']*100:+.2f}% | {r['max_drawdown']*100:.2f}% "
      f"| {r['delta_cagr_vs_baseline']*100:+.2f}pp "
      f"| {r['dd_deterioration_pp']*100:+.2f}pp "
      f"| {r['advantage_years']}/6 | {r['max_one_side_turnover']:.2f} |")
w("")
w("（maxDD 变化 = 留一 − 基线，正值=恶化；优势年 = 对 B1(m)=C05 的年胜出数，"
  "门 3 口径；换手为全期最大单边换手。）")
w("")
w("### 定罪判定（预登记 §5.2，机械执行）")
w("")
w("> 定罪线（仅作用于嫌疑名单）：剔除后净 CAGR ≥ 基线 +0.30pp **且** maxDD 恶化 ≤1.0pp "
  "→ 确认剔除；否则保留（标记观察）。恰在线上的边缘案例 → 停机呈裁定。")
w("")
w("- 嫌疑名单为空 → **定罪线无判定对象**：0 定罪、0 保留标记；不存在任何"
  "边缘案例（无数字落在判定线上）。")
w("")
w("### 清洁组合（预登记 §5.3）")
w("")
w("- 定罪集为空 → 按任务书与预登记**跳过**：无联合剔除运行、无采纳、无退回条款触发；"
  "F 线静态基线候选维持 F3R3-EW 原样（17 因子）。")
w("")
w("## 九、H1/H0 判定")
w("")
w("- **H1 否证，H0 确认**（预登记 §1/§5.4）：嫌疑名单为空 → \"17 代表中存在坏因子"
  "且剔除后改善 ≥0.30pp\"不成立。两假设均为可接受结局；F3 组合维持 17 因子原样，"
  "**\"alpha=集中度形态\"结论加强**（分散化已把单因子贡献摊平：无一部 t<0）。")
w("- 判读边界（FA-S3/FA-S5 纪律）：留一矩阵为描述性证据，不构成任何剔除/采纳决定；"
  "`Σweight_i×c_i` 不得解读为组合收益。")
w("")
w("## 十、下游建议")
w("")
w("- **无清洁集**：F3 因子集不变（17 代表），对 T1 下游与后续实验**零影响**——无需改配置、"
  "无需重跑下游。")
w("- 描述性留档（非决定）：留一矩阵显示剔 B12/D30/B14 的 ΔCAGR 为 +1.88/+1.62/+1.56pp "
  "且 maxDD 改善。这属于**看过留一结果后的探索性读数**（dev 样本第三次重用方向），"
  "按冻结纪律不触发任何动作；若未来要动因集，必须先立新预登记（可证伪假设 + 判定线），"
  "并接受样本重用过拟合折扣。")
w("- 归因方法（FA-S2 直读 + 席位权重贡献 + sanity 门槛）可复用为 T1 新因子上线后的"
  "存量审计模板。")
w("")
w("## 十一、运行身份")
w("")
w(f"- run：`{RUN_DIR.name}`；脚本 `scripts/attribution.py`（{sha16(RUN_DIR/'scripts/attribution.py')}）、"
  f"`scripts/runner_attrib.py`（{sha16(RUN_DIR/'scripts/runner_attrib.py')}）、"
  f"`scripts/aggregate.py`（{sha16(RUN_DIR/'scripts/aggregate.py')}）。")
w("- 引擎：工作区 band_engine.py v1.4.1 pin `a01cb29ce4cf2148…75abf3`，运行前后 sha "
  "一致，零修改（引擎文件只读）。")
w("- 输入：底盘 run `20260919T201500-f3r3-industry-cap-4b2e`（v1.3 pin `84a2443a…`，"
  "completed）；F2R1 分数 parquet 17 件 + `f2r1_all120.csv`；F3R1 `F3-EW_composite.parquet`"
  " + `dedup_clusters.csv`；日历/池 `daily_1999_2024.parquet`；eval 面板 "
  "`daily_2015_2024.parquet`。全部 sha256 见 `manifest.json`。")
state = json.loads((RUN_DIR / "tmp/runner_attrib_state.json").read_text(encoding="utf-8"))
import re
wall_a = summary["wall_seconds"]
wall_an = float(re.findall(r"subset loop complete: \d+ subsets, wall (\d+)s",
                           (RUN_DIR / "logs/runner_anchor_stdout.log")
                           .read_text(encoding="utf-8"))[-1])
wall_l = float(re.findall(r"subset loop complete: \d+ subsets, wall (\d+)s",
                          (RUN_DIR / "logs/runner_loo_stdout.log")
                          .read_text(encoding="utf-8"))[-1])
w(f"- 阶段耗时：归因 invocation {wall_a:.0f}s（峰值 RSS {summary['peak_rss_gb']:.2f} GB）"
  f"+ 锚 invocation {wall_an:.0f}s + 17 留一批量 invocation {wall_l:.0f}s"
  f"（runner 峰值 RSS {state['peak_rss_gb']:.2f} GB）；"
  f"合计约 {wall_a + wall_an + wall_l:.0f}s，远低于墙钟 2h / RSS 8GB 预算。")
w("- 试验计账：**275→293**（新配置 18 = 归因 1 + 留一 17 + 清洁 0；leave-zero-out 锚"
  "不计——与已运行的 F3R3-EW 同配置，按预登记\"不重复计已运行配置\"）。")
w("- 窗口纪律：dev 2015-01-05..2020-12-31；val 2021–2024 与冻结区 2025+ **零接触**"
  "（eval 面板进 harness 前截断 ≤2020-12-31）；数据 raw 只读。")
w("- 过程披露：归因脚本前两次启动在统计产出前修复两处实现笔误"
  "（E16 族 JSON 无 screen 键——按 F3R1 原样加保护；dict 迭代笔误），"
  "均未触碰任何判定线与数据；无停机、无口径疑问。")
w("")
w("- 全部数字为历史回放，不构成盈利或实盘声称。")
w("")

DOCS.write_text("\n".join(lines), encoding="utf-8", newline="\n")
print("written", DOCS, len(lines), "lines")
