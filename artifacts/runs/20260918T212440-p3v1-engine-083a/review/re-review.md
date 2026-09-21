# v1 引擎 diff 级复审：APPROVE（双签放行）

- 复审时间：2026-09-18 晚；对象：修复版引擎 sha256:16 `494310195438cbfb`（1,873 行）+ 21 项测试 + 本 run 目录补齐物
- 范围：按首轮 REJECT 的复审指引，仅 C1/M1 + 新测试 + 主对话补齐项；全项评审见 `reject-report.md`
- 结论：**APPROVE，P3R2 可按预登记运行**

## 核验结果

| 项 | 结果 |
|---|---|
| C1 | L311 返回 `int(pm_mismatch_post.height)`；全引擎 grep 无其他"计算后丢弃/硬编码"披露点（仅存字面 0 为累加器初值与 `total_voids: 0` 资金不变量常量，test_19 钉死）；test_18 以 0.5 元失真 fixture 断言真实计数 | PASS |
| M1 | L1491 取 order_shares、L1507 `qty = sell_sh if order_shares is None else min(order_shares, sell_sh)`，live row 与合成 `_FallbackOrder` 两路径同覆盖；test_20 三重钉死（兜底只卖 800、留存 clip [200]、executed==1） | PASS |
| test_02 | 永真断言已移除，替换为 fixture 级日期守卫 + FIFO/锁定断言（LOW 备注：未来可在 fill detail 带消费 clip 取得日做全量扫描） | PASS |
| am 冻结 | `if sess == "am": pass`（裁定注释在位），撤销仅 pm 决策点，无前视残留 | PASS |
| test_20/21 | 断言质量好；test_21 未断言 added clip 次日可卖（LOW，由 acquired 机制隐含） | PASS |
| 补齐物 | reject-report.md / fix-chain.md / manifest data_checks.bridge（rows=18,486,939、range=3 含样本、pre=2,870,381、post=1,824）/ 样例 3 双口径——与全部已知事实一致 | PASS |
| 偏差留档 | fix-chain.md 四条偏差如实入档，充分；过程偏差不要求返工 | PASS |

## 残余备注（均 LOW，不阻塞）

1. test_02 全量 T+1 扫描、test_21 次日可卖断言——可在 P3R2 前工具化批次顺手补强。
2. bridge 函数 L296-300 两段重复草稿注释，下次触碰时合并。
3. 执行者"11,742 行"口误已留档（实际 1,873）。

## 附带披露义务（转 P3R2 报告）

P3R2 报告须携带两项已登记披露：F6 顺延双记口径、F7/除权日锚依赖 stk_limit 质量（沿前轮口径）。
