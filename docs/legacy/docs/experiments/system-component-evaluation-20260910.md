# 标准组件初筛：E 阶段

2026-09-10。状态：接口与许可证初筛完成；采用决策 **暂缓**。现有系统有 B/C/D 阻断项，尚未形成可作性能基准的正确账本。未安装第三方框架、未改工程依赖纪律，没有同输入运行结果，不能宣布任何框架适合或不适合替换。

| 候选 | 官方支持面 | 本项目仍需验证的适配 | 本轮判断 |
|---|---|---|---|
| vectorbt | 自定义 order_func、现金共享、费用、固定费用、股数粒度、部分成交等参数 | T+1可卖库存、方向性封板、最低佣金max而非简单固定费相加、共享资金顺序、延迟退出、复权与公司行为 | 可进入订单/组合模块对照；没有证据应整库淘汰，也没有依据直接采用 |
| Qlib | Exchange 的买卖成本、最低成本、成交价格与限制规则 | 冻结输入适配、历史状态与交易日历、精确成交和现金账本、框架数据格式负担 | 可进入月频组合模块对照；不用因此重写全部因子假设 |

来源：[vectorbt Portfolio API](https://vectorbt.dev/api/portfolio/base/)、[Qlib Exchange 源码](https://github.com/microsoft/qlib/blob/main/qlib/backtest/exchange.py)。这里据接口推断适配方向，不是运行验收。

官方仓库可访问；当前主分支许可证文本分别为 vectorbt 的 Apache 2.0 + Commons Clause、Qlib 的 MIT。[vectorbt LICENSE](https://raw.githubusercontent.com/polakowo/vectorbt/master/LICENSE.md)、[Qlib LICENSE](https://raw.githubusercontent.com/microsoft/qlib/main/LICENSE)。主分支不是冻结版本，本轮未固定安装版本或完成发行维护频率评估，因此不作长期维护成本或商用适用性结论。

下一次评估限这两个候选：固定版本→同一份订单输入→逐笔价格/股数/费用/现金/持仓/净值对账→全部正确后比较冷/热耗时、峰值内存及适配代码。覆盖本轮D-01/D-02反例。研究冻结协议、候选身份、一次性留出窗记录继续作为独立控制层，不能指望替换回测框架自动修复C层。

当前工程建议：保留现有架构与工件，优先修复确定缺口。该建议是改动风险与现有证据下的阶段选择，不是“自研永远最好”的裁决。
