# -*- coding: utf-8 -*-
"""P2-R6 复核 项1+项2：从 metrics.json 独立实现 prereg §6 八条 dev gate，
与结果文档 §2 表、run 自带 gates 段对比；equity_curves.parquet 重算 net CAGR / 最大回撤。
只读，不修改任何既有文件。
"""
import json, math
import polars as pl

RUN = "artifacts/runs/20260917T231652-p2r6-etf-rotation-7b72501d"
CS = ["C%02d" % i for i in range(1, 13)]

m = json.load(open(f"{RUN}/metrics.json", encoding="utf-8"))

# ---------- 结果文档 §2 表（人工抄录，用于逐格对比） ----------
DOC = {
 "C01": dict(gross=12.0, net=11.9, b1=10.4, exc=1.5, posy="3/5", mdd=-26.3, to=749, top1=0.26, top3=0.52),
 "C02": dict(gross=13.7, net=13.7, b1=10.4, exc=3.2, posy="3/5", mdd=-24.8, to=720, top1=0.22, top3=0.48),
 "C03": dict(gross=11.7, net=11.6, b1=4.5,  exc=7.1, posy="4/5", mdd=-29.1, to=1798, top1=0.31, top3=0.63),
 "C04": dict(gross=9.3,  net=9.1,  b1=4.5,  exc=4.6, posy="3/5", mdd=-32.7, to=2123, top1=0.36, top3=0.78),
 "C05": dict(gross=14.9, net=14.9, b1=10.4, exc=4.5, posy="3/5", mdd=-28.7, to=797, top1=0.20, top3=0.53),
 "C06": dict(gross=16.0, net=15.9, b1=10.4, exc=5.5, posy="3/5", mdd=-27.2, to=626, top1=0.18, top3=0.49),
 "C07": dict(gross=11.4, net=11.3, b1=4.5,  exc=6.8, posy="3/5", mdd=-32.8, to=1774, top1=0.32, top3=0.68),
 "C08": dict(gross=11.4, net=11.2, b1=4.5,  exc=6.7, posy="3/5", mdd=-33.8, to=1676, top1=0.32, top3=0.69),
 "C09": dict(gross=12.8, net=12.7, b1=10.4, exc=2.3, posy="2/5", mdd=-24.3, to=573, top1=0.24, top3=0.57),
 "C10": dict(gross=14.5, net=14.4, b1=10.4, exc=4.0, posy="4/5", mdd=-23.1, to=587, top1=0.21, top3=0.51),
 "C11": dict(gross=10.2, net=10.0, b1=4.5,  exc=5.5, posy="5/5", mdd=-29.8, to=1931, top1=0.25, top3=0.61),
 "C12": dict(gross=9.4,  net=9.2,  b1=4.5,  exc=4.7, posy="3/5", mdd=-36.6, to=2153, top1=0.28, top3=0.69),
}
DOC_YEARLY = {  # 逐年 净收益/净超额(pp)，文档 §2 第二张表
 "C01": [(1.8,-7.8),(11.6,4.0),(-7.9,15.4),(14.5,-19.3),(46.5,10.9)],
 "C02": [(7.9,-1.7),(13.3,5.7),(-15.7,7.7),(25.4,-8.4),(46.5,11.0)],
 "C03": [(-2.9,0.4),(9.3,2.9),(-18.4,4.6),(24.6,-2.1),(60.0,36.0)],
 "C04": [(-9.9,-6.6),(15.0,8.6),(-21.1,1.9),(14.9,-11.8),(64.3,40.2)],
 "C05": [(1.0,-8.5),(12.4,4.8),(-11.9,11.4),(9.4,-24.4),(82.5,47.0)],
 "C06": [(8.4,-1.1),(13.5,5.9),(-20.2,3.2),(21.0,-12.8),(76.0,40.4)],
 "C07": [(0.3,3.6),(9.6,3.2),(-25.1,-2.0),(9.1,-17.6),(89.8,65.7)],
 "C08": [(-2.3,0.9),(14.0,7.6),(-26.5,-3.4),(9.2,-17.5),(90.3,66.2)],
 "C09": [(5.1,-4.4),(11.4,3.7),(-7.7,15.7),(27.6,-6.2),(31.8,-3.7)],
 "C10": [(10.7,1.1),(12.9,5.3),(-14.0,9.3),(37.5,3.7),(32.4,-3.2)],
 "C11": [(-1.1,2.1),(8.2,1.8),(-19.3,3.7),(32.3,5.6),(41.2,17.1)],
 "C12": [(-6.1,-2.9),(14.6,8.2),(-27.3,-4.2),(35.7,9.0),(45.8,21.8)],
}

# ---------- equity 曲线重算 ----------
eq = pl.read_parquet(f"{RUN}/equity_curves.parquet")

def years_frac(d0, d1):
    return (d1 - d0).days / 365.25

def recompute(cfg):
    d = eq.filter(pl.col("config_id") == cfg).sort("session")
    dev = d.filter((pl.col("session") >= pl.date(2016, 1, 1)) & (pl.col("session") <= pl.date(2020, 12, 31)))
    s0, s1 = dev["session"].min(), dev["session"].max()
    e0, e1 = dev["equity_net"][0], dev["equity_net"][-1]
    g0, g1 = dev["equity_gross"][0], dev["equity_gross"][-1]
    yf = years_frac(s0, s1)
    net_cagr = (e1 / e0) ** (1 / yf) - 1
    gross_cagr = (g1 / g0) ** (1 / yf) - 1
    tot = e1 / e0 - 1
    # max drawdown on daily net equity
    runmax = dev["equity_net"].cum_max()
    dd = dev["equity_net"] / runmax - 1.0
    imin = dd.arg_min()
    trough_date = dev["session"][imin]
    peak_date = dev["session"][:imin+1][dev["equity_net"][:imin+1].arg_max()]
    mdd = float(dd[imin])
    # yearly net returns from curve
    yr = {}
    for y in range(2016, 2021):
        seg = dev.filter(pl.col("session").dt.year() == y)
        yr[str(y)] = seg["equity_net"][-1] / dev.filter(pl.col("session").dt.year() < y)["equity_net"][-1] - 1 if y > 2016 else seg["equity_net"][-1] / e0 - 1
    return dict(start=str(s0), end=str(s1), yf=yf, net_cagr=net_cagr, gross_cagr=gross_cagr,
                total=tot, mdd=mdd, peak=str(peak_date), trough=str(trough_date), yearly=yr)

rec = {c: recompute(c) for c in CS}

# ---------- 独立 gate 实现（prereg §6 原文） ----------
B3M = m["B3_dev_monthly"]["mean_net_cagr"]
B3W = m["B3_dev_weekly"]["mean_net_cagr"]

def my_gates(c):
    dev = m["configs"][c]["dev"]
    freq = m["configs"][c]["freq"]
    b1 = dev["b1_net_cagr"]                      # B1 曲线未导出，取 metrics（B1 为同池等权基准）
    b1_mdd = dev["b1_max_drawdown"]
    nc = rec[c]["net_cagr"]                      # 用我重算的净年化
    mdd = rec[c]["mdd"]                          # 用我重算的回撤
    exc = nc - b1
    pos_years = sum(1 for v in dev["excess_by_year"].values() if v > 0)   # 逐年超额来自 metrics（B1 逐年未导出）
    cap = 6.0 if freq == "monthly" else 12.0  # 年单边换手：metrics 存小数倍数（5.871=587.1%）；月频≤600%、周频≤1200%
    g = {}
    g["1_net>0"] = nc > 0
    g["2_exc>=2pp"] = exc >= 0.020
    g["3_posyears>=4"] = pos_years >= 4
    g["4_mdd<=20%&<=B1"] = (mdd >= -0.20) and (mdd >= b1_mdd)  # 幅值比较：|mdd|<=20% 且 |mdd|<=|b1_mdd|
    g["5_turnover"] = dev["max_one_side_turnover"] <= cap
    g["6_conc"] = dev["concentration"]["top1_share"] <= 0.40 and dev["concentration"]["top3_share"] <= 0.70
    b3 = B3M if freq == "monthly" else B3W
    g["7_vs_B3+1pp"] = nc >= b3 + 0.010
    g["8_exec>=95%"] = dev["execution_rate"] >= 0.95
    g["pass"] = all(g.values())
    return dict(net_cagr=nc, gross_cagr=rec[c]["gross_cagr"], mdd=mdd, exc=exc, pos_years=pos_years,
                b1=b1, b1_mdd=b1_mdd, turnover=dev["max_one_side_turnover"], cap=cap,
                top1=dev["concentration"]["top1_share"], top3=dev["concentration"]["top3_share"],
                exec=dev["execution_rate"], b3_thr=b3 + 0.010, gates=g)

mine = {c: my_gates(c) for c in CS}

print("=" * 110)
print("A. 我方独立 gate 判定（判据实现依 prereg §6；net_cagr/mdd 用 equity_curves 重算值）")
print("=" * 110)
for c in CS:
    r = mine[c]; g = r["gates"]
    fails = [k for k, v in g.items() if k != "pass" and not v]
    print(f"{c} net={r['net_cagr']*100:6.2f}% mdd={r['mdd']*100:7.2f}% exc={r['exc']*100:+6.2f}pp posY={r['pos_years']}/5 "
          f"to={r['turnover']*100:7.1f}% top1={r['top1']:.3f} top3={r['top3']:.3f} exec={r['exec']:.4f} -> {'PASS' if g['pass'] else 'FAIL'} fails={fails}")

print()
print("=" * 110)
print("B. 我方判定 vs run 自带 gates 段 vs 结果文档 §2 表 dev 判定")
print("=" * 110)
doc_verdict = {c: "fail" for c in CS}
mismatch = 0
for c in CS:
    run_pass = m["gates"][c]["dev"]["dev_pass"]
    ok = (mine[c]["gates"]["pass"] == run_pass) and (run_pass is False)
    if not ok:
        mismatch += 1
    print(f"{c}: mine={'PASS' if mine[c]['gates']['pass'] else 'FAIL'}  run_gates={'PASS' if run_pass else 'FAIL'}  doc={doc_verdict[c]}  consistent={ok}")
print("verdict mismatches:", mismatch)

print()
print("=" * 110)
print("C. 逐格数值对比：metrics vs 文档 §2（括号内为差值，容差：净/毛/超额 0.05pp，回撤 0.05pp，换手 0.5%，top 0.005）")
print("=" * 110)
cell_mismatch = []
for c in CS:
    dev = m["configs"][c]["dev"]
    pairs = [
        ("毛%", dev["gross_cagr"]*100, DOC[c]["gross"]),
        ("净%", dev["net_cagr"]*100, DOC[c]["net"]),
        ("B1%", dev["b1_net_cagr"]*100, DOC[c]["b1"]),
        ("超额pp", dev["excess_vs_b1"]*100, DOC[c]["exc"]),
        ("优势年", f"{sum(1 for v in dev['excess_by_year'].values() if v>0)}/5", DOC[c]["posy"]),
        ("回撤%", dev["max_drawdown"]*100, DOC[c]["mdd"]),
        ("换手%", dev["max_one_side_turnover"]*100, DOC[c]["to"]),
        ("top1", dev["concentration"]["top1_share"], DOC[c]["top1"]),
        ("top3", dev["concentration"]["top3_share"], DOC[c]["top3"]),
    ]
    out = []
    for name, mv, dv in pairs:
        if isinstance(mv, str):
            if mv != dv:
                cell_mismatch.append((c, name, mv, dv)); out.append(f"{name}:{mv}!={dv}")
        else:
            tol = 0.005 if name in ("top1", "top3") else (0.5 if name == "换手%" else 0.05)
            if abs(mv - dv) > tol:
                cell_mismatch.append((c, name, round(mv, 4), dv)); out.append(f"{name}:{mv:.3f}!={dv}")
    print(f"{c}: " + ("全部一致" if not out else "; ".join(out)))
print("§2 表数值不一致格:", cell_mismatch if cell_mismatch else "无")

print()
print("=" * 110)
print("D. equity 重算 vs metrics（net_cagr / gross_cagr / mdd / mdd 窗口，全部 12 配置）")
print("=" * 110)
eq_mis = []
for c in CS:
    dev = m["configs"][c]["dev"]
    r = rec[c]
    d_nc = abs(r["net_cagr"] - dev["net_cagr"]); d_gc = abs(r["gross_cagr"] - dev["gross_cagr"])
    d_mdd = abs(r["mdd"] - dev["max_drawdown"])
    win = dev["mdd_window"]
    win_ok = (r["peak"] == win["peak_date"] and r["trough"] == win["trough_date"])
    flag = "" if (d_nc < 1e-9 and d_gc < 1e-9 and d_mdd < 1e-9 and win_ok) else "  <-- DIFF"
    if flag: eq_mis.append((c, r["net_cagr"], dev["net_cagr"], r["mdd"], dev["max_drawdown"], r["peak"], win["peak_date"], r["trough"], win["trough_date"]))
    print(f"{c}: net {r['net_cagr']:.8f} vs {dev['net_cagr']:.8f} (d={d_nc:.2e}) | gross d={d_gc:.2e} | mdd {r['mdd']:.6f} vs {dev['max_drawdown']:.6f} (d={d_mdd:.2e}) | win {r['peak']}->{r['trough']} vs {win['peak_date']}->{win['trough_date']}{flag}")
print("equity 重算不一致:", eq_mis if eq_mis else "无（12/12 逐位一致）")

print()
print("=" * 110)
print("E. C10 / C03 / C11 关键格详单（重算值）")
print("=" * 110)
for c in ["C10", "C03", "C11"]:
    r = rec[c]; dev = m["configs"][c]["dev"]
    print(f"{c}: 重算 net_cagr={r['net_cagr']*100:.4f}% metrics={dev['net_cagr']*100:.4f}% | 重算 mdd={r['mdd']*100:.4f}% ({r['peak']}->{r['trough']}) metrics={dev['max_drawdown']*100:.4f}% ({dev['mdd_window']['peak_date']}->{dev['mdd_window']['trough_date']})")
    print(f"    逐年净收益(重算): " + ", ".join(f"{y}:{v*100:.2f}%" for y, v in r["yearly"].items()))
    print(f"    逐年净超额(metrics): " + ", ".join(f"{y}:{v*100:+.2f}pp" for y, v in dev["excess_by_year"].items()))
    print(f"    优势年={sum(1 for v in dev['excess_by_year'].values() if v>0)}/5, 对B1超额={dev['excess_vs_b1']*100:+.3f}pp, 换手max={dev['max_one_side_turnover']*100:.1f}%, B3门限={mine[c]['b3_thr']*100:.2f}% vs net {r['net_cagr']*100:.2f}% -> {'过' if r['net_cagr']>=mine[c]['b3_thr'] else '不过'}")

print()
print("F. 逐年 净/超额 文档第二张表抽查（容差 0.05pp）")
ymis = []
for c in CS:
    dev = m["configs"][c]["dev"]
    for i, y in enumerate(["2016", "2017", "2018", "2019", "2020"]):
        dr, de = DOC_YEARLY[c][i]
        mr = dev["net_return_by_year"][y]*100; me = dev["excess_by_year"][y]*100
        if abs(mr-dr) > 0.05 or abs(me-de) > 0.05:
            ymis.append((c, y, round(mr,2), dr, round(me,2), de))
print("逐年表不一致:", ymis if ymis else "无（60/60 格在容差内）")

print()
print("G. gate7 文档语句核对：月频门限=%.4f 周频门限=%.4f；各配置 net_cagr" % (B3M+0.01, B3W+0.01))
for c in CS:
    r = mine[c]
    print(f"  {c}: net={r['net_cagr']*100:.2f}% thr={r['b3_thr']*100:.2f}% -> {'过' if r['gates']['7_vs_B3+1pp'] else '不过'}")

print()
print("H. 回撤相对 B1 条款计数（|mdd|<=|B1 mdd|）：")
b1m = m["configs"]["C01"]["dev"]["b1_max_drawdown"]; b1w = m["configs"]["C03"]["dev"]["b1_max_drawdown"]
print(f"  B1 monthly mdd={b1m:.6f}, weekly mdd={b1w:.6f}")
deeper = [c for c in CS if rec[c]["mdd"] < (b1m if mine[c] and m['configs'][c]['freq']=='monthly' else b1w)]
print("  深于 B1:", deeper, "count=", len(deeper))
print("  浅于 B1:", [c for c in CS if c not in deeper], "count=", 12-len(deeper))
