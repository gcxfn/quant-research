#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wave-20 part1 (ordinal 11400-11499) 逐行判定写入（python 文件写，非 shell heredoc）。"""
import json
import os

# (ordinal, primary_code, secondary_code, supports_direction, key_quote, confidence)
ROWS = [
 (11400, "other", None, 0, "收入和费用的匹配不同步", "high"),
 (11401, "cost_up", None, 1, "长期停产状态，产生较大的停车损失", "high"),
 (11402, "cost_up", None, 1, "长期停产状态，产生较大的停车损失", "high"),
 (11403, "cost_up", None, 1, "长期停产状态，产生较大的停工损失", "high"),
 (11404, "other", "cost_up", 1, "尚未能形成规模经济效益", "high"),
 (11405, "other", "cost_up", 1, "未形成新增效益", "high"),
 (11406, "cost_up", None, 1, "产品毛利率较低，固定费用较大", "high"),
 (11407, "cost_up", "non_recurring", 1, "总成本费用同比增长约4.90%", "high"),
 (11408, "demand_down", "cost_up", 1, "公司订单较上年同期下降较多", "high"),
 (11409, "demand_down", "cost_up", 1, "公司订单较上年同期下降较多", "high"),
 (11410, "demand_down", "cost_up", 1, "公司订单较上年同期下降较多", "high"),
 (11411, "other", None, 0, "计提了10,216.30万元的大额资产减值", "high"),
 (11412, "cost_down", None, -1, "营业成本及管理费用相较上年同期有所下降", "high"),
 (11413, "demand_up", None, -1, "销售规模较同期增加", "high"),
 (11414, "core_ops", None, -1, "7月-9月经营业绩有所提升", "high"),
 (11415, "price_down", "impairment", 1, "LED芯片行业市场持续低迷、产品价格持续下降", "high"),
 (11416, "cost_up", "demand_down", 1, "劳动力等生产要素成本上涨", "high"),
 (11417, "impairment", None, -1, "资产减值损失较上年同期下降", "high"),
 (11418, "impairment", None, -1, "资产减值损失比上年同期减少", "high"),
 (11419, "other", None, 1, "应收账款大额逾期未收回，经营现金流短缺", "high"),
 (11420, "other", None, 1, "应收账款大额逾期未收回，经营现金流短缺", "high"),
 (11421, "impairment", None, 1, "对该投资全额计提减值", "high"),
 (11422, "demand_down", "fx", 1, "主营业务收入较上年同期下降约14%左右", "high"),
 (11423, "non_recurring", None, -1, "收到了企业社保费返还资金", "high"),
 (11424, "cost_up", "other", 1, "营业费用、财务费用和销售费用均较上年有所增长", "high"),
 (11425, "demand_down", "other", 1, "订单较前两季度有所下降", "high"),
 (11426, "cost_up", "other", 1, "增加了松江厂房租金费用等支出", "high"),
 (11427, "demand_down", "cost_up", 1, "订单有所减少", "high"),
 (11428, "demand_down", "cost_down", 1, "园林园艺工程业务实现的收入及利润同比减少", "high"),
 (11429, "demand_down", "cost_up", 1, "海洋牧场养殖产品产量下降", "high"),
 (11430, "impairment", None, 1, "拟补提纺织板块相关资产减值", "high"),
 (11431, "demand_down", None, 1, "相关子公司全面停工，无业务收入", "high"),
 (11432, "cost_up", None, 1, "公司债务压力过大，财务压力持续增加", "low"),
 (11433, "impairment", None, 1, "形成的商誉存在减值迹象", "high"),
 (11434, "demand_down", None, 1, "互联网加速服务业务萎缩", "high"),
 (11435, "cost_up", None, 1, "财务费用、诉讼支出增加", "high"),
 (11436, "demand_down", "cost_up", 1, "收入减少、费用增加", "high"),
 (11437, "demand_down", "cost_up", 1, "营业收入下降较为明显", "high"),
 (11438, "demand_down", "impairment", 1, "营业收入下降较为明显", "high"),
 (11439, "demand_down", "cost_up", 1, "消费性产品需求疲软", "high"),
 (11440, "demand_down", "cost_up", 1, "业务量较上年同期下滑", "high"),
 (11441, "demand_down", "cost_up", 1, "全球半导体行业下滑", "high"),
 (11442, "demand_down", "cost_up", 1, "全球半导体市场下滑", "high"),
 (11443, "cost_up", "demand_down", 1, "原材料价格上涨及公司所处区域市场需求不足影响", "high"),
 (11444, "demand_down", "fx", 1, "市场需求减少，导致公司营收下降", "high"),
 (11445, "impairment", "non_recurring", 1, "公司计提了营业外支出约11,538万元", "high"),
 (11446, "impairment", "non_recurring", 1, "预计损失增加约15,042万元", "high"),
 (11447, "impairment", "non_recurring", 1, "预计归属于2019年1-9月期间的违约赔偿支出约13,986万元", "high"),
 (11448, "cost_up", None, 1, "计提逾期利息和罚息，财务费用较上年同期增加", "high"),
 (11449, "price_down", "cost_up", 1, "生猪销售价格较低，成本有所上升", "high"),
 (11450, "cost_up", None, 1, "贷款规模同比增加及部分子公司在建工程转固，导致财务费用增加", "high"),
 (11451, "cost_up", "non_recurring", 1, "运营初期费用增加", "high"),
 (11452, "other", "demand_down", 1, "受光伏“531”政策影响", "high"),
 (11453, "price_down", "demand_down", 1, "光伏玻璃同比市场价格下跌", "high"),
 (11454, "demand_down", "impairment", 1, "业务收缩，收入大幅下滑", "high"),
 (11455, "demand_down", "cost_up", 1, "业绩持续下滑，导致公司仍处于亏损状态", "high"),
 (11456, "demand_down", "cost_down", 1, "收入大幅降低以及资金成本居高不下", "high"),
 (11457, "demand_down", "cost_up", 1, "受市场大环境、公司业务调整及资金成本居高不下等原因影响业绩持续下滑", "high"),
 (11458, "demand_up", "cost_down", -1, "分销业务和智能制造保持持续稳定增长", "high"),
 (11459, "ma_restructuring", "impairment", -1, "不再纳入上市公司合并报表范围", "high"),
 (11460, "ma_restructuring", "cost_up", -1, "不再纳入上市公司合并报表范围", "high"),
 (11461, "price_down", "cost_up", 1, "锂电池销售单价同比下降", "high"),
 (11462, "core_ops", None, -1, "本期销售产品实际毛利率高于预计", "high"),
 (11463, "price_down", None, 1, "钴产品价格下跌导致母公司投资收益较上年同期大幅度下降", "high"),
 (11464, "price_down", "demand_down", 1, "参股公司钴产品价格下跌导致母公司投资收益较上年同期大幅下降", "high"),
 (11465, "price_down", "cost_up", 1, "锂盐产品价格持续回落", "high"),
 (11466, "demand_up", None, -1, "所生产的锂精矿实现销售产生效益", "high"),
 (11467, "price_down", None, 1, "产品的销售单价与上年同期相比出现下降", "high"),
 (11468, "price_down", None, 1, "销售单价的下行压力仍未有效缓解", "high"),
 (11469, "other", None, 0, "一季度属于季节性停工期间", "high"),
 (11470, "cost_up", None, 1, "资金成本较去年同期大幅上升", "high"),
 (11471, "non_recurring", "demand_down", -1, "计入营业外收入2807.34万元", "high"),
 (11472, "demand_up", "cost_down", -1, "部分业务较去年同期工作量有所增加", "high"),
 (11473, "demand_up", "impairment", -1, "预计主营业务工作量增加，与去年同期相比，毛利增加", "high"),
 (11474, "demand_up", "impairment", -1, "收入和毛利同比增加", "high"),
 (11475, "demand_down", None, 1, "实现的营业收入较上年同期有所下降", "high"),
 (11476, "demand_down", "cost_up", 1, "整体业务及经营规模较去年同期大幅下降", "high"),
 (11477, "cost_up", "non_recurring", 1, "加大研发和营销投入致成本增加", "high"),
 (11478, "demand_down", "cost_down", 1, "收入下降的金额较成本费用大", "high"),
 (11479, "fx", "cost_up", 1, "导致公司汇兑损失较大", "high"),
 (11480, "core_ops", None, 0, "日常运营支出稳定，未达盈亏平衡", "high"),
 (11481, "demand_down", "cost_up", 1, "受宏观经济持续影响及显著的行业特性，营业收入下降", "high"),
 (11482, "cost_up", None, 1, "一方面财务费用增加", "high"),
 (11483, "other", None, 0, "经营情况未发生重大变化", "low"),
 (11484, "other", None, 0, "经营情况未发生重大变化", "low"),
 (11485, "demand_down", "cost_down", 1, "市场竞争激烈，公司营业收入较上年同期有所下降", "high"),
 (11486, "demand_down", "cost_up", 1, "机床工具行业市场未有明显好转", "high"),
 (11487, "demand_up", "cost_down", -1, "恢复生产经营管理的各项措施的效果逐步显现，销售增长", "high"),
 (11488, "impairment", "demand_down", 1, "对其计提大额资产减值损失", "high"),
 (11489, "cost_up", "price_down", 1, "原材料价格较去年同期上涨", "high"),
 (11490, "cost_up", "demand_down", 1, "控制气量和提高原料气价，导致2019年上半年生产量低，成本加大", "high"),
 (11491, "cost_up", None, 1, "计提违约利息较去年同期大幅增加", "high"),
 (11492, "impairment", "cost_up", 1, "存在合同违约可能性，增加减值准备约1,900万元", "high"),
 (11493, "cost_down", "other", -1, "通航业务所产生的费用同比大幅降低", "high"),
 (11494, "cost_down", "other", -1, "通航业务相关的各项费用同比大幅降低", "high"),
 (11495, "non_recurring", "cost_down", -1, "进行债务重组,因而使公司净利润增加约805万元", "high"),
 (11496, "cost_up", "demand_up", 1, "设备产能得不到有效释放，导致成本上升", "high"),
 (11497, "impairment", None, -1, "相应冲销资产减值损失增加本报告期利润", "high"),
 (11498, "demand_up", None, -1, "销售收入较上年同期有所增长", "high"),
 (11499, "impairment", "non_recurring", -1, "相应冲销信用减值损失增加利润", "high"),
]


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "batch_020_judge_part1.jsonl")
    lines = []
    for oid, pc, sc, sd, q, cf in ROWS:
        rec = {"ordinal": oid, "primary_code": pc, "secondary_code": sc,
               "supports_direction": sd, "key_quote": q, "confidence": cf}
        lines.append(json.dumps(rec, ensure_ascii=False, separators=(",", ":")))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    qlen = sorted(len(r[4]) for r in ROWS)
    print(json.dumps({"part": 1, "rows": len(ROWS), "ordinals": [ROWS[0][0], ROWS[-1][0]],
                      "quote_len_max": qlen[-1]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
