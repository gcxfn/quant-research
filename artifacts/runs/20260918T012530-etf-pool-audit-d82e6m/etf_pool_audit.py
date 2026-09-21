# -*- coding: utf-8 -*-
"""etf_pool_audit.py -- ETF/基金注册表逐代码分类精化审计（纯审计，只读 raw/config）。

用法:
  python etf_pool_audit.py rules      # 阶段1: 确定性规则打标 + 生成 LLM 复核批次
  python etf_pool_audit.py finalize   # 阶段2: 合并 LLM 复核判定, 交叉核对, 写产物

规则版本: rules-v1 (2026-09-18)
输入(只读):
  data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv
  configs/experiments/p2r7-etf-exposure.json  (u1_whitelist_frozen, u2_qdii_keywords_frozen)
输出:
  阶段1: <run_dir>/tmp/rule_labels.parquet, <run_dir>/tmp/review_batches/*.txt
  阶段2: data/features/etf-registry-classification-20260918/{classification.parquet,discrepancy.csv,manifest.json}
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

RUN_DIR = Path(__file__).resolve().parent
REPO_ROOT = RUN_DIR.parents[2]
CSV_PATH = REPO_ROOT / "data/raw/tushare/fund_basic/20260909-r1/chunk_market_E.csv"
CFG_PATH = REPO_ROOT / "configs/experiments/p2r7-etf-exposure.json"
FEAT_DIR = REPO_ROOT / "data/features/etf-registry-classification-20260918"
TMP_DIR = RUN_DIR / "tmp"
REVIEW_DIR = TMP_DIR / "review_batches"

RULES_VERSION = "rules-v1"
BATCH_SIZE = 150

# U1 前缀规则（与 preflight u1_whitelist_rule 一致: {158,159}(SZ)/{51,52,53,55,56,58}(SH), 名称含 ETF 亦可）
U1_ETF_PREFIX = {("SZ", "158"), ("SZ", "159"), ("SH", "51"), ("SH", "52"),
                 ("SH", "53"), ("SH", "55"), ("SH", "56"), ("SH", "58")}
# LOF/封闭 段（用于 instrument 回退与交叉核对；SZ 按前 2 位, SH 按前 3 位）
SEG_LOF_PREFIX = {("SZ", "16"), ("SH", "501"), ("SH", "502")}
SEG_CLOSED_PREFIX = {("SZ", "18"), ("SH", "500")}
SEG_GRADED_PREFIX = {("SZ", "15")}  # 150-157: 分级/老基金子份额段 (158/159 为 ETF)
seg_is_lof = ("SZ", "16"), ("SH", "501"), ("SH", "502")
seg_is_closed = ("SZ", "18"), ("SH", "500")
seg_is_graded = ("SZ", "15"),

COMMODITY_KW = ["黄金", "白银", "豆粕", "豆油", "棕榈", "白糖", "能源化工", "商品", "铁矿", "期货"]
COMMODITY_EQUITY_TRAP = "有色"  # "有色金属"多为股票指数 ETF, 仅带"期货"字样才归商品
FEEDER_KW = "联接"
GRADING_KW = "分级"
CLOSED_KW = "封闭"
REIT_KW = re.compile(r"reit", re.IGNORECASE)

FUND_TYPE_ASSET = {
    "股票型": "股票A股",
    "债券型": "债券",
    "货币型": "货币",
    "混合型": "混合",
    "REITs": "其他",
    "其他": None,  # 规则不打, 留给名称/LLM
}
FUND_TYPE_COMMODITY = {"商品型"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def code_seg(ts_code: str):
    code, mkt = ts_code.split(".")
    return code, mkt, code[:2], code[:3]


def match_keywords(name: str, kws):
    hits = [k for k in kws if k in name]
    return hits


def classify_row(row, qdii_kws):
    """返回 instrument, subtype, asset, cross_border_qdii, evidence(list[str]),
    classified_by, needs_review_reasons(list[str])。"""
    name = row["name"] if isinstance(row["name"], str) else ""
    ftype = row["fund_type"] if isinstance(row["fund_type"], str) else ""
    ts_code = row["ts_code"]
    code, mkt, p2, p3 = code_seg(ts_code)

    evidence = []
    reasons = []

    # ---------- instrument ----------
    is_reit = bool(REIT_KW.search(name))
    if FEEDER_KW in name:
        instrument, subtype = "其他", "联接"
        evidence.append(f"name含[{FEEDER_KW}]")
    elif is_reit:
        instrument, subtype = "其他", "REITs"
        evidence.append("name含[REIT]")
    elif "LOF" in name:
        instrument, subtype = "LOF", None
        evidence.append("name含[LOF]")
    elif "ETF" in name:
        instrument, subtype = "ETF", None
        evidence.append("name含[ETF]")
    elif GRADING_KW in name:
        instrument, subtype = "其他", "分级"
        evidence.append(f"name含[{GRADING_KW}]")
    elif CLOSED_KW in name:
        instrument, subtype = "封闭式", None
        evidence.append(f"name含[{CLOSED_KW}]")
    elif (mkt, p2) in U1_ETF_PREFIX or (mkt, p3) in U1_ETF_PREFIX:
        instrument, subtype = "ETF", "前缀推断"
        evidence.append(f"前缀[{mkt}{p3[:2] if (mkt,p3) in U1_ETF_PREFIX else p2}段]")
    elif (mkt, p2) in SEG_LOF_PREFIX or (mkt, p3) in SEG_LOF_PREFIX:
        instrument, subtype = "LOF", "前缀推断"
        evidence.append(f"前缀[{mkt}{p3}]LOF段")
        reasons.append("instrument_前缀推断")
    elif (mkt, p2) in SEG_CLOSED_PREFIX or (mkt, p3) in SEG_CLOSED_PREFIX:
        instrument, subtype = "封闭式", "前缀推断"
        evidence.append(f"前缀[{mkt}{p3}]封闭段")
        reasons.append("instrument_前缀推断")
    elif (mkt, p2) in SEG_GRADED_PREFIX:
        instrument, subtype = "其他", "分级段前缀推断"
        evidence.append(f"前缀[{mkt}{p3}]分级/老基金段")
        reasons.append("instrument_分级段推断")
    else:
        instrument, subtype = "其他", None
        evidence.append("无名称标记/前缀不明")
        reasons.append("instrument_无标记")

    # LOF/封闭段 代码 + 名称含 ETF (如 160615.SZ): 名称规则误纳 LOF 联接的核心形态
    if instrument == "ETF" and ((mkt, p3) in seg_is_lof or (mkt, p2) in seg_is_lof):
        reasons.append("ETF名称落在LOF段代码")

    # ---------- cross_border (QDII 关键词, U2 冻结表) ----------
    qdii_hits = match_keywords(name, qdii_kws)
    cross_border = False
    if qdii_hits:
        cross_border = True
        evidence.append("QDII关键词" + ",".join(f"[{h}]" for h in qdii_hits))

    # ---------- asset ----------
    asset = None
    if cross_border:
        if any(k in name for k in ("原油", "油气", "石油")):
            asset = "商品"
            evidence.append("跨境商品关键词[原油/油气/石油]")
        else:
            asset = "股票跨境(QDII)"
    if asset is None and ftype == "货币型":
        asset = "货币"
        evidence.append("fund_type=货币型")
    if asset is None and "货币" in name:
        asset = "货币"
        evidence.append("name含[货币]")
    if asset is None and ("债" in name or ftype == "债券型"):
        src = "name含[债]" if "债" in name else "fund_type=债券型"
        asset = "债券"
        evidence.append(src)
    if asset is None:
        comm_hits = [k for k in COMMODITY_KW if k in name]
        if comm_hits and not (COMMODITY_EQUITY_TRAP in name and "期货" not in name and ftype == "股票型"):
            asset = "商品"
            evidence.append("商品关键词" + ",".join(f"[{h}]" for h in comm_hits))
    if asset is None and ftype in FUND_TYPE_COMMODITY:
        asset = "商品"
        evidence.append("fund_type=商品型")
    if asset is None and ftype == "混合型":
        asset = "混合"
        evidence.append("fund_type=混合型")
    if asset is None and "混合" in name:
        asset = "混合"
        evidence.append("name含[混合]")
    if asset is None and ftype == "REITs":
        asset = "其他"
        evidence.append("fund_type=REITs")
    if asset is None and ("FOF" in name.upper() or ftype == "FOF"):
        asset = "其他"
        evidence.append("FOF标记")
    if asset is None and ftype == "股票型":
        asset = "股票A股"
        evidence.append("fund_type=股票型")
    if asset is None and ftype == "其他":
        asset = "其他"
        evidence.append("fund_type=其他")
        reasons.append("asset_仅fund_type其他")
    if asset is None:
        asset = "未定"
        reasons.append("asset_未定")

    # ---------- 交叉冲突预标记 ----------
    ftype_asset = FUND_TYPE_ASSET.get(ftype)
    if ftype_asset and asset not in ("未定",):
        # 名称关键词得到的资产与 fund_type 资产不一致(货币/债/混/股 vs QDII/商品/其他)
        if asset != ftype_asset:
            name_asset = asset
            if not (ftype_asset == "股票A股" and asset in ("股票跨境(QDII)", "商品", "其他")):
                reasons.append(f"asset_名称{name_asset}_vs_ftype{ftype}")

    classified_by = "rules"
    return instrument, subtype, asset, cross_border, evidence, classified_by, reasons


def phase_rules():
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    wl = set(cfg["u1_whitelist_frozen"])
    qdii_kws = cfg["universe"]["u2_qdii_keywords_frozen"]

    df = pd.read_csv(CSV_PATH, dtype=str)
    assert len(df) == 2945, len(df)

    inst, sub, asset, cb, evid, by, rev = [], [], [], [], [], [], []
    for _, row in df.iterrows():
        r = classify_row(row, qdii_kws)
        inst.append(r[0]); sub.append(r[1]); asset.append(r[2]); cb.append(r[3])
        evid.append("|".join(r[4])); by.append(r[5]); rev.append(r[6])
    df["instrument"] = inst
    df["subtype"] = sub
    df["asset"] = asset
    df["cross_border_qdii"] = cb
    df["evidence"] = evid
    df["classified_by"] = by
    df["needs_review_reasons"] = [";".join(x) for x in rev]
    df["in_whitelist"] = df["ts_code"].isin(wl)

    # 复核集：任何 needs_review 行 + 白名单内非 ETF/非股票A股 行
    review_mask = df["needs_review_reasons"].str.len() > 0
    wl_flag = df["in_whitelist"] & ((df["instrument"] != "ETF") | (df["asset"] != "股票A股"))
    df["for_review"] = review_mask | wl_flag

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TMP_DIR / "rule_labels.parquet", index=False)

    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    # 全量白名单复核批次（LLM 逐批阅读, 覆盖规则自信行如 513310 类 QDII 漏判）
    wlv = df[df["in_whitelist"]].reset_index(drop=True)
    for b, start in enumerate(range(0, len(wlv), BATCH_SIZE)):
        chunk = wlv.iloc[start:start + BATCH_SIZE]
        lines = []
        for _, r in chunk.iterrows():
            lines.append("\t".join([
                r["ts_code"], r["name"], str(r["fund_type"]),
                f"{r['instrument']}/{r['asset']}", r["needs_review_reasons"] or "",
            ]))
        (REVIEW_DIR / f"whitelist_{b:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
    rv = df[df["for_review"]].reset_index(drop=True)
    n_batches = 0
    for b, start in enumerate(range(0, len(rv), BATCH_SIZE)):
        chunk = rv.iloc[start:start + BATCH_SIZE]
        lines = []
        for _, r in chunk.iterrows():
            lines.append("\t".join([
                r["ts_code"], r["name"], str(r["fund_type"]),
                "W" if r["in_whitelist"] else "-",
                f"{r['instrument']}/{r['asset']}",
                r["needs_review_reasons"] or "",
            ]))
        (REVIEW_DIR / f"batch_{b:02d}.txt").write_text("\n".join(lines), encoding="utf-8")
        n_batches += 1
    stats = {
        "rows": len(df),
        "whitelist": int(df["in_whitelist"].sum()),
        "for_review": int(df["for_review"].sum()),
        "review_batches": n_batches,
        "instrument_dist": df["instrument"].value_counts().to_dict(),
        "asset_dist": df["asset"].value_counts().to_dict(),
        "wl_instrument_dist": df[df["in_whitelist"]]["instrument"].value_counts().to_dict(),
        "wl_asset_dist": df[df["in_whitelist"]]["asset"].value_counts().to_dict(),
    }
    (TMP_DIR / "rule_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=1))


def phase_finalize():
    with open(CFG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    wl = set(cfg["u1_whitelist_frozen"])
    qdii_kws = cfg["universe"]["u2_qdii_keywords_frozen"]

    df = pd.read_parquet(TMP_DIR / "rule_labels.parquet")
    adj_files = sorted(TMP_DIR.glob("adjudication_*.json"))
    adj_n = 0
    for fp in adj_files:
        with open(fp, encoding="utf-8") as f:
            adj = json.load(f)
        for ts_code, lab in adj.items():
            m = df["ts_code"] == ts_code
            if not m.any():
                print(f"[warn] adjudication for unknown code {ts_code}")
                continue
            i = df.index[m][0]
            if lab.get("instrument"):
                df.at[i, "instrument"] = lab["instrument"]
            if "subtype" in lab:
                df.at[i, "subtype"] = lab["subtype"]
            if lab.get("asset"):
                df.at[i, "asset"] = lab["asset"]
            if lab.get("cross_border_qdii") is not None:
                df.at[i, "cross_border_qdii"] = lab["cross_border_qdii"]
            if lab.get("evidence"):
                df.at[i, "evidence"] = (df.at[i, "evidence"] + "|" + "|".join(lab["evidence"])).strip("|")
            df.at[i, "classified_by"] = "rules+llm"
            adj_n += 1
    print(f"adjudicated rows: {adj_n}")

    # 已知差异基线（红队 run 20260917232740 findings R1-7/R1-8）
    known_qdii3 = ["513310.SH", "513730.SH", "513800.SH"]
    known_lof20 = sorted([c for c in wl
                          if c.startswith("501") or c.startswith("502")
                          or c[:3] in ("160", "161", "162") and c.endswith(".SZ")])
    known_lof20 = [c for c in known_lof20
                   if (c.startswith("501") or c.startswith("502")
                       or c[:3] in ("160", "161", "162"))]

    disp_rows = []

    # 跨市场注记(确定性后处理): 沪港深/沪深港 指数含港股通成分但按 A 股 ETF 交易
    cm = df["name"].str.contains("沪港深|沪深港", na=False) & (df["asset"] == "股票A股")
    for i in df.index[cm]:
        if df.at[i, "subtype"] in (None, "", "None"):
            df.at[i, "subtype"] = "跨市场指数(含港股成分)"
            df.at[i, "evidence"] = (df.at[i, "evidence"] + "|跨市场注记[沪港深/沪深港]").strip("|")

    # (a) 白名单内但按新分类应为 LOF/跨境/商品
    p3_all = df["ts_code"].str.split(".").str[0].str[:3]
    p2_all = df["ts_code"].str.split(".").str[0].str[:2]
    mkt_all = df["ts_code"].str.split(".").str[1]
    seg_lof = (
        ((mkt_all == "SH") & p3_all.isin(["501", "502"]))
        | ((mkt_all == "SZ") & p2_all.isin(["16"]))
    )
    mask_a = df["in_whitelist"] & (
        (df["instrument"] == "LOF") | seg_lof | df["cross_border_qdii"] | (df["asset"] == "商品"))
    for _, r in df[mask_a].iterrows():
        kinds = []
        if r["instrument"] == "LOF":
            kinds.append("LOF")
        if seg_lof[r.name]:
            kinds.append("LOF段代码")
        if r["cross_border_qdii"]:
            kinds.append("跨境")
        if r["asset"] == "商品":
            kinds.append("商品")
        in_known = r["ts_code"] in known_lof20 or r["ts_code"] in known_qdii3
        disp_rows.append({
            "type": "a_白名单内_LOF_跨境_商品", "ts_code": r["ts_code"], "name": r["name"],
            "fund_type": r["fund_type"], "in_whitelist": True,
            "new_instrument": r["instrument"], "new_asset": r["asset"],
            "cross_border_qdii": r["cross_border_qdii"], "evidence": r["evidence"],
            "matched_known_baseline": "known_lof20" if r["ts_code"] in known_lof20
                                      else ("known_qdii3" if r["ts_code"] in known_qdii3 else ""),
            "note": "/".join(kinds),
        })
    # (b) 不在白名单但按新分类应属 A 股股票 ETF
    u1_name_etf = df["name"].str.contains("ETF", na=False) & ~df["name"].str.contains("联接", na=False)
    code_seg = df["ts_code"].str.split(".")
    p2 = code_seg.str[0].str[:2]
    p3 = code_seg.str[0].str[:3]
    mkt = code_seg.str[1]
    u1_prefix = pd.Series(False, index=df.index)
    for mktv, pref in U1_ETF_PREFIX:
        u1_prefix |= (mkt == mktv) & ((p2 == pref) | (p3 == pref))
    mask_b = ~df["in_whitelist"] & (df["instrument"] == "ETF") & (df["asset"] == "股票A股")
    for _, r in df[mask_b].iterrows():
        u1_would_pass = bool(u1_name_etf[r.name] or u1_prefix[r.name])
        disp_rows.append({
            "type": "b_白名单外_应属A股股票ETF", "ts_code": r["ts_code"], "name": r["name"],
            "fund_type": r["fund_type"], "in_whitelist": False,
            "new_instrument": r["instrument"], "new_asset": r["asset"],
            "cross_border_qdii": r["cross_border_qdii"], "evidence": r["evidence"],
            "matched_known_baseline": "",
            "note": ("U1规则本应命中(疑数据覆盖缺口)" if u1_would_pass
                     else "U1规则漏扫(名称无ETF且前缀不在规则集)"),
        })
    # (c) fund_type 与名称分类矛盾(终标签口径)
    ftype_asset = df["fund_type"].map(FUND_TYPE_ASSET)
    conflict = (ftype_asset.notna()) & (df["asset"] != ftype_asset) & (df["asset"] != "未定") & \
               ~((ftype_asset == "股票A股") & df["cross_border_qdii"] & (df["asset"] == "股票跨境(QDII)")) & \
               ~((ftype_asset == "股票A股") & (df["asset"] == "商品"))
    mask_c = conflict
    for _, r in df[mask_c].iterrows():
        disp_rows.append({
            "type": "c_fund_type与名称分类矛盾", "ts_code": r["ts_code"], "name": r["name"],
            "fund_type": r["fund_type"],
            "in_whitelist": bool(r["in_whitelist"]),
            "new_instrument": r["instrument"], "new_asset": r["asset"],
            "cross_border_qdii": r["cross_border_qdii"], "evidence": r["evidence"],
            "matched_known_baseline": "",
            "note": f"fund_type映射={ftype_asset[r.name]} vs 名称分类={r['asset']}",
        })
    # (c2) 代码段与名称 instrument 矛盾: ETF 名称落在 LOF 段代码 (160/501/502)
    mask_c2 = df["name"].str.contains("ETF", na=False) & seg_lof & ~df["name"].str.contains("联接", na=False)
    for _, r in df[mask_c2].iterrows():
        disp_rows.append({
            "type": "c2_代码段与名称instrument矛盾", "ts_code": r["ts_code"], "name": r["name"],
            "fund_type": r["fund_type"], "in_whitelist": bool(r["in_whitelist"]),
            "new_instrument": r["instrument"], "new_asset": r["asset"],
            "cross_border_qdii": r["cross_border_qdii"], "evidence": r["evidence"],
            "matched_known_baseline": "",
            "note": f"名称含[ETF]但代码为LOF段({r['ts_code'][:3]})",
        })
    disp = pd.DataFrame(disp_rows)
    FEAT_DIR.mkdir(parents=True, exist_ok=True)
    disp.to_csv(FEAT_DIR / "discrepancy.csv", index=False, encoding="utf-8-sig")

    # 输出列精简
    out = df[["ts_code", "name", "management", "fund_type", "list_date", "delist_date",
              "status", "in_whitelist", "instrument", "subtype", "asset",
              "cross_border_qdii", "evidence", "classified_by", "needs_review_reasons"]].copy()
    out.to_parquet(FEAT_DIR / "classification.parquet", index=False)

    # 对账
    a = disp[disp["type"].str.startswith("a_")]
    a_new_lof = a[a["matched_known_baseline"] == ""]
    counts = {
        "rows_total": len(df),
        "rows_adjudicated_by_llm": adj_n,
        "instrument_dist": df["instrument"].value_counts().to_dict(),
        "asset_dist": df["asset"].value_counts().to_dict(),
        "wl_instrument_dist": df[df["in_whitelist"]]["instrument"].value_counts().to_dict(),
        "wl_asset_dist": df[df["in_whitelist"]]["asset"].value_counts().to_dict(),
        "disc_a_total": int(len(a)),
        "disc_a_matched_known_lof20": int((a["matched_known_baseline"] == "known_lof20").sum()),
        "disc_a_matched_known_qdii3": int((a["matched_known_baseline"] == "known_qdii3").sum()),
        "disc_a_new_extra": int(len(a_new_lof)),
        "disc_a_new_extra_codes": a_new_lof["ts_code"].tolist(),
        "known_lof20_reconstructed": known_lof20,
        "known_qdii3": known_qdii3,
        "disc_b_total": int((disp["type"] == "b_白名单外_应属A股股票ETF").sum()),
        "disc_b_u1_miss_codes": disp[(disp["type"] == "b_白名单外_应属A股股票ETF")
                                     & (disp["note"] == "U1规则漏扫(名称无ETF且前缀不在规则集)")]["ts_code"].tolist(),
        "disc_b_data_gap_count": int((disp["type"] == "b_白名单外_应属A股股票ETF").sum()
                                     - len(disp[(disp["type"] == "b_白名单外_应属A股股票ETF")
                                                & (disp["note"] == "U1规则漏扫(名称无ETF且前缀不在规则集)")])),
        "disc_c_total": int((disp["type"] == "c_fund_type与名称分类矛盾").sum()),
        "disc_c2_total": int((disp["type"] == "c2_代码段与名称instrument矛盾").sum()),
    }
    manifest = {
        "run_id": RUN_DIR.name,
        "purpose": "ETF/基金注册表逐代码分类精化审计（纯审计参考，不改动现行冻结池）",
        "rules_version": RULES_VERSION,
        "batch_size": BATCH_SIZE,
        "input_csv": str(CSV_PATH.relative_to(REPO_ROOT)),
        "input_csv_sha256": sha256_file(CSV_PATH),
        "config": str(CFG_PATH.relative_to(REPO_ROOT)),
        "whitelist_size": len(wl),
        "u2_qdii_keywords_frozen": qdii_kws,
        "known_baseline": {
            "qdii3_source": "artifacts/runs/20260917232740-redteam-1fcda1fb/findings.md R1-7",
            "lof20_source": "artifacts/runs/20260917232740-redteam-1fcda1fb/findings.md R1-8 (按前缀重构)",
        },
        "script": Path(__file__).name,
        "script_sha256": sha256_file(Path(__file__)),
        "counts": counts,
        "scope_note": "注册表为 2026-09-09 快照(U5, 非 PIT)；list/delist 日期仅统计不外推；不涉及 2025+ 研究数据",
    }
    (FEAT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    {"rules": phase_rules, "finalize": phase_finalize}[sys.argv[1]]()
