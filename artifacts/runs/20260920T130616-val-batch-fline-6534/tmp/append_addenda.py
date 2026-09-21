# -*- coding: utf-8 -*-
"""2026-09-20 F2R1 冻结产物不可复现——向全部下游结果文档追加补记段；val 批量预登记追加执行结果。
预登记冻结正文一律不动；历史行不改写。"""
import io, sys

BASE = r"D:\量化\docs\research"

F2R1_LONG = """

## 2026-09-20 补记：D 族与 E16 冻结产物不可复现（V2 端口停机）

- **事实**：exp-20260920-val-batch（V2，run `20260920T130616-val-batch-fline-6534`）的因子 dev 端口验证发现：17 个 F3 代表因子中 8 个（D 族 7 个：D10/D13/D14/D18/D19/D20/D30，加 E16）的本 run 冻结分数**无法逐位复现**。证据链：同一份 shipped 族脚本 + 字节级未变输入（`data/_meta/sha256.tsv` 基线覆盖的 23,622 个财务原始文件逐个重算 sha256，0 处不一致），四路运行（本 run 冻结产物、两次重跑、`POLARS_MAX_THREADS=1`）产出四份互不相同的帧（sha 全不同、行数不同）；根因定位：D 族实现的 `sort(...).group_by(k).last()` 惯用法未实现其文档声明的 tie-break（合成探针 300k 行/3200 组上 8.4% 组偏移，量级与本文档披露的 8-9% 同日多公告率一致）；`pit_full()` 的重述 tie-break 经定向探针排除。E16 的带外修复脚本 `fix_E16_dupcount.py` 同病：`unique(keep="first")` 依赖未指定行序，同代码同输入两次运行 27 行数值不同。
- **稳定部分**：D 族四路重跑的 FA-S2 存活判定集合全同（四路存活均为 D10/D13/D14/D18/D19/D20/D30 等 13 个）；A/B/C/F 族的 9 个代表逐位（或行序无关地逐值）可复现。即"哪些因子存活/入选 17 代表"的结构结论不受影响，**不可复现的是分数数值本身**。
- **影响**：本文档 D 族因子的分数表、IC/t/覆盖等统计为"一次未规定行序的随机运行"的产物（方向性结论暂持，不得作精确引用）；下游 F3R1/F3R2/F3R3/F3R4、归因审计、F4R1/F4R2 全链 dev 数字身份作废，待 D 族/E16 确定性修复（显式 tie-break）并重发 dev 产物后重走；F 线 5 配置的 val 一次性资格保留未用。处置路线呈用户裁定。
- **证据**：`artifacts/runs/20260920T130616-val-batch-fline-6534/outputs/`（`d_family_reproducibility.json`、`d_pipeline_determinism_probe.json`、`port_check_factors_dev.json`）；[V2 停机报告](exp-20260920-val-batch-fline.md)；台账 TL-40。
"""

SHORT_TEMPLATE = """

## 2026-09-20 补记：F2R1 冻结产物不可复现，本文档数字身份作废

本文档全部（或核心）dev 数字建立在 F2R1 因子分数 parquet 之上。2026-09-20 V2 端口验证证明其中 D 族 7 代表 + E16 的 F2R1 冻结产物**不可复现**（同一代码 + 字节级未变输入四路运行 sha 全不同，根因 = `group_by(...).last()` 惯用法未实现文档声明的 tie-break），详见 [F2R1 补记](exp-20260919-factor-round-f2r1.md)与 [V2 停机报告](exp-20260920-val-batch-fline.md)。{extra}详见两处引文；处置（修复后重跑）呈用户裁定。
"""

DOCS = [
    ("exp-20260919-factor-round-f3r1.md", 8,
     "因此本文档 F3-EW/F3-ICW 的净 CAGR、门判与 composite 数值均为一次随机运行的衍生，不作精确引用；17 代表构成与 A/B/C/F 族 9 个代表的分数不受影响。"),
    ("exp-20260919-factor-round-f3r2.md", 8,
     "因此本文档 A0 锚复刻、EW/ICW 臂数字均为该随机产物的衍生；R3-06 底盘（ETF 线）不受影响。"),
    ("exp-20260919-factor-round-f3r3.md", 8,
     "因此本文档三臂数字与 2026 行业快照披露、K=10 结论均为该随机产物的衍生；相对比较的方向（风险门修好、收益摊薄）在存活集合四路全同证据下暂持，不作验证声称。"),
    ("exp-20260920-factor-round-f3r4.md", 8,
     "因此本文档 A/B/C 臂数字、b=0.10164738676824621（源于 composite 截面 std）与 +5.3356%/+0.4583pp 头条均为该随机产物的衍生；事件标记本身（T1 事件表）经 V2 端口验证一致、不受影响；60 交易日窗效应的 val 存活性检验未发生。"),
    ("exp-20260920-factor-attribution.md", 8,
     "因此本文档 FA-S2 直读的 F2R1 分数中 D 族 7 代表 + E16 分量为该随机产物的衍生——\"17 因子贡献 t 全正、嫌疑名单空\"的结构性结论在存活集合四路全同证据下暂持，但全部具体 t 值与留一矩阵不作精确引用。"),
    ("exp-20260919-zone-sheet-f4r1.md", 8,
     "本文档股票腿输入为 F3 composite，三臂数字（与 C 臂 +0.86%）为该随机产物的衍生；\"分区执行=回撤换收益\"的相对比较方向暂持，不作验证声称。"),
    ("exp-20260920-zone-sheet-f4r2.md", 8,
     "本文档股票腿输入为 F3 composite，D1/D2 数字（+2.14%/+1.44%）为该随机产物的衍生；止损/止盈消融的相对比较方向暂持，不作验证声称。"),
]

PREREG_ADD = """

## 7. 执行结果追记（2026-09-20，冻结正文未动）

- **V1（混合族 7 配置）**：判定完成——**仅 H2-03 三门全过**（净 +1.81%/超额 +1.96pp/maxDD −12.11%）；H2-01 +0.24%、H2-04 −0.70%、R3-01..04 −0.29%~+0.12% 全部死于门 1。7 配置 val 已消费（不可重复）。[结果](exp-20260920-val-batch-hybrid.md)。
- **V2（F 线 5 配置）**：§6 端口门触发停机——因子 dev 端口 FAIL 8/17（D 族 7 代表 + E16 的 F2R1 冻结产物不可复现），5 配置全部停机，**val 未消费、一次性资格保留**；B1(m) dev/val 与归因事件 dev 三端口 PASS。处置（D 族/E16 确定性修复 → 重走 dev 链 → 另立预登记）呈用户裁定。[结果](exp-20260920-val-batch-fline.md)。
- 台账 TL-40（296→303）；README 与主计划第四十三次更新同步。
"""

def main():
    # 1) F2R1 源头详细段
    p = BASE + r"\exp-20260919-factor-round-f2r1.md"
    s = io.open(p, encoding="utf-8").read()
    assert "2026-09-20 补记" not in s
    io.open(p, "w", encoding="utf-8", newline="").write(s.rstrip("\n") + F2R1_LONG)
    print("OK f2r1")
    # 2) 下游短段
    for name, sec, extra in DOCS:
        p = BASE + "\\" + name
        s = io.open(p, encoding="utf-8").read()
        assert "2026-09-20 补记" not in s, name
        io.open(p, "w", encoding="utf-8", newline="").write(
            s.rstrip("\n") + SHORT_TEMPLATE.format(sec=sec, extra=extra))
        print("OK", name)
    # 3) val 批量预登记执行追记
    p = BASE + r"\exp-20260920-val-batch-prereg.md"
    s = io.open(p, encoding="utf-8").read()
    assert "执行结果追记" not in s
    io.open(p, "w", encoding="utf-8", newline="").write(s.rstrip("\n") + PREREG_ADD)
    print("OK val-batch-prereg")

if __name__ == "__main__":
    main()
