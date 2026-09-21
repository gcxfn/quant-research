# T1/T3: independent recomputation of the 96 dev gate cells (12 configs x 8 criteria)
# Reads ONLY artifacts (metrics.json); thresholds from frozen config p2r9-risk-delivery.json
import json

RUN = r"D:\量化\artifacts\runs\20260918T030528-p2r9-risk-delivery-ef2777dc"
m = json.load(open(RUN + r"\metrics.json", encoding="utf-8"))
cfgs, gates, B3 = m["configs"], m["gates"], {k: v for k, v in m.items() if k.startswith("B3prime_")}

rows = []
for cid in [f"C{i:02d}" for i in range(1, 13)]:
    d = cfgs[cid]["dev"]
    g = gates[cid]["dev"]
    c = cfgs[cid]
    cell = "B3prime_" + c["mech_key"] + f"-N{c['N']}"
    b3 = B3[cell]["mean_net_cagr"]
    rec = {
        "cid": cid,
        "mech_key": c["mech_key"], "N": c["N"], "cell": cell,
        "net": d["net_cagr"], "gross": d["gross_cagr"],
        "b1m": d["b1m_net_cagr"], "excess": d["excess_vs_b1m"],
        "pos_years": sum(1 for v in d["excess_by_year"].values() if v > 0),
        "dd": d["max_drawdown"], "b1m_dd": d["b1m_max_drawdown"],
        "to_max": d["max_one_side_turnover"],
        "top1": d["concentration"]["top1_share"], "top3": d["concentration"]["top3_share"],
        "top4": d["concentration"].get("top4_share"),
        "b3": b3, "exec": d["execution_rate"],
        "excess_by_year": d["excess_by_year"],
    }
    # independent criteria
    r = {}
    r["1"] = rec["net"] > 0
    r["2"] = rec["excess"] >= 0.020
    r["3"] = rec["pos_years"] >= 4
    r["4"] = (rec["dd"] >= -0.20) and (rec["dd"] >= rec["b1m_dd"])
    r["5"] = rec["to_max"] <= 6.0
    r["6"] = rec["top1"] <= 0.40 and rec["top3"] <= 0.70
    r["7"] = rec["net"] >= rec["b3"] + 0.010
    r["8"] = rec["exec"] >= 0.95
    rec["recomputed"] = r
    # gates as recorded
    rec["recorded"] = {k: g[k] for k in ["1_net_cagr_gt_0","2_excess_vs_B1_ge_2pp","3_positive_years_ge_4_of_5",
        "4_mdd_le_20_and_le_B1","5_turnover_le_cap","6_top1_le_40_top3_le_70","7_vs_random_plus_1pp","8_execution_ge_95pct"]}
    rec["recorded_pass"] = g["dev_pass"]
    rec["recomputed_pass"] = all(r.values())
    rec["fails"] = sorted([k for k, v in r.items() if not v])
    rec["match"] = all(rec["recorded"][rk] == r[k] for k, rk in
        [("1","1_net_cagr_gt_0"),("2","2_excess_vs_B1_ge_2pp"),("3","3_positive_years_ge_4_of_5"),
         ("4","4_mdd_le_20_and_le_B1"),("5","5_turnover_le_cap"),("6","6_top1_le_40_top3_le_70"),
         ("7","7_vs_random_plus_1pp"),("8","8_execution_ge_95pct")]) and rec["recorded_pass"] == rec["recomputed_pass"]
    # doc table claims (section 3): net%, excess pp, pos years, dd%, b1m dd%, turnover max %, top1/top3, fails
    doc = {
     "C01": dict(net=11.84, ex=+5.50, py=5, dd=-18.94, bdd=-17.24, to=607.7, t1=21, t3=55, fails=["4","5"]),
     "C02": dict(net=12.82, ex=+7.95, py=3, dd=-23.43, bdd=-25.98, to=692.9, t1=29, t3=62, fails=["3","4","5"]),
     "C03": dict(net=13.26, ex=+6.92, py=3, dd=-19.77, bdd=-17.24, to=562.3, t1=27, t3=61, fails=["3","4"]),
     "C04": dict(net=10.07, ex=+3.72, py=4, dd=-18.62, bdd=-17.24, to=697.8, t1=21, t3=56, fails=["4","5"]),
     "C05": dict(net=13.39, ex=+7.04, py=3, dd=-22.71, bdd=-17.24, to=609.3, t1=30, t3=65, fails=["3","4","5"]),
     "C06": dict(net=11.39, ex=+8.01, py=3, dd=-21.69, bdd=-20.59, to=481.7, t1=30, t3=67, fails=["3","4"]),
     "C07": dict(net=11.07, ex=+7.70, py=3, dd=-25.76, bdd=-20.59, to=495.9, t1=33, t3=70, fails=["3","4","6"]),
     "C08": dict(net=9.65,  ex=+4.44, py=4, dd=-16.56, bdd=-17.23, to=470.7, t1=25, t3=61, fails=[]),
     "C09": dict(net=13.52, ex=+8.31, py=3, dd=-17.61, bdd=-17.23, to=472.3, t1=20, t3=55, fails=["3","4"]),
     "C10": dict(net=9.32,  ex=+4.11, py=3, dd=-18.03, bdd=-17.23, to=425.7, t1=26, t3=55, fails=["3","4"]),
     "C11": dict(net=4.19,  ex=+0.14, py=3, dd=-16.24, bdd=-16.45, to=566.1, t1=52, t3=146, fails=["2","3","6","7"]),
     "C12": dict(net=11.27, ex=+5.54, py=5, dd=-18.11, bdd=-15.61, to=621.4, t1=21, t3=55, fails=["4","5"]),
    }[cid]
    dd_doc = all([
        abs(rec["net"]*100 - doc["net"]) < 0.005,
        abs(rec["excess"]*100 - doc["ex"]) < 0.005,
        rec["pos_years"] == doc["py"],
        abs(rec["dd"]*100 - doc["dd"]) < 0.005,
        abs(rec["b1m_dd"]*100 - doc["bdd"]) < 0.005,
        abs(rec["to_max"]*100 - doc["to"]) < 0.05,
        abs(rec["top1"]*100 - doc["t1"]) < 0.05,
        abs(rec["top3"]*100 - doc["t3"]) < 0.05,
        rec["fails"] == doc["fails"],
    ])
    rec["doc_match"] = dd_doc
    rows.append(rec)

print(f"{'cid':4} {'net%':>7} {'expp':>6} {'py':>2} {'dd%':>7} {'b1mdd%':>7} {'to%':>6} {'top1%':>6} {'top3%':>6} {'b3%':>6} {'exec':>6}  recomputed_fails  recorded==recomp  doc==metrics  pass")
for r in rows:
    print(f"{r['cid']:4} {r['net']*100:7.2f} {r['excess']*100:6.2f} {r['pos_years']:2d} {r['dd']*100:7.2f} {r['b1m_dd']*100:7.2f} "
          f"{r['to_max']*100:6.1f} {r['top1']*100:6.1f} {r['top3']*100:6.1f} {r['b3']*100:6.2f} {r['exec']*100:6.2f}  "
          f"{','.join(r['fails']) or '-':10} {str(r['match']):5} {str(r['doc_match']):5} {r['recomputed_pass']}")

passes = [r["cid"] for r in rows if r["recomputed_pass"]]
print("\nall-pass configs (recomputed):", passes)
print("metrics dev_pass_configs:", m["dev_pass_configs"], "| advanced_to_validation:", m["advanced_to_validation"])
print("recorded dev_pass flags:", [r["cid"] for r in rows if r["recorded_pass"]])
print("ALL 96 cells recorded==recomputed:", all(r["match"] for r in rows))
print("ALL 12 doc rows == metrics:", all(r["doc_match"] for r in rows))
for r in rows:
    if not r["doc_match"]:
        print("  doc mismatch detail:", r["cid"], r["fails"])
