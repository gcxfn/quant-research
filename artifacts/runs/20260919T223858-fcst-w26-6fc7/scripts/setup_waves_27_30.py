#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T1 波次 27–30 机械适配器（主对话 2026-09-19 22:45 冻结）。

对每个批 N in {27,28,29,30}：
1. 建 artifacts/runs/<ts>-fcst-wN-<4hex>/，复制 w25 的四脚本；
2. merge 脚本改 batch 号、ordinal 基、文件名，docstring 沿承记录如实；
3. extract_cues 改默认批号；批 27/28（混合 type）输出加 type 列（ordinal|type|REASON）；
   批 29/30（单一预减）沿用 ordinal|REASON 简化格式；
4. 运行 extract_cues 生成 cues 并打印身份摘要。

只创建新目录、不碰既有文件；merge/extract 改动为纯机械替换。
"""
import hashlib
import os
import random
import subprocess
import sys
import time

ROOT = r"D:\量化"
SRC = os.path.join(ROOT, "artifacts", "runs", "20260919T150323-fcst-w25-a125", "scripts")
PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")

WAVES = {
    27: {"base": 15600, "mixed": True},
    28: {"base": 16200, "mixed": True},
    29: {"base": 16800, "mixed": False},
    30: {"base": 17400, "mixed": False},
}

MERGE_SUBS = [
    ("batch_id == 25", "batch_id == {n}"),
    ("batch_id=25", "batch_id={n}"),
    ("batch_025", "batch_{nnn}"),
    ("14400", "{base}"),
    ("wave-25", "wave-{n}"),
    ("merge_batch25.py", "merge_batch{n}.py"),
    ("--batch 25", "--batch {n}"),
]
EXTRACT_SUBS = [
    ("default=25", "default={n}"),
    ("batch 25", "batch {n}"),
    ("batch_025", "batch_{nnn}"),
    ("--batch 25", "--batch {n}"),
    ("wave-25", "wave-{n}"),
]


def apply_subs(text, subs, n, base):
    out = text
    for old, tpl in subs:
        out = out.replace(old, tpl.format(n=n, nnn=f"{n:03d}", base=base))
    return out


def main():
    ts = time.strftime("%Y%m%dT%H%M%S")
    made = []
    for n, cfg in WAVES.items():
        suffix = "".join(random.choice("0123456789abcdef") for _ in range(4))
        run_dir = os.path.join(ROOT, "artifacts", "runs",
                               f"{ts}-fcst-w{n}-{suffix}")
        scripts = os.path.join(run_dir, "scripts")
        work = os.path.join(run_dir, "work")
        os.makedirs(scripts)
        os.makedirs(work)
        base, mixed = cfg["base"], cfg["mixed"]

        merge = open(os.path.join(SRC, "merge_batch25.py"), encoding="utf-8").read()
        merge = apply_subs(merge, MERGE_SUBS, n, base)
        # 沿承行如实化（sed 链产生的复合行统一重写）
        merge = merge.replace(
            f"沿自 wave-25 merge_batch25.py（源 sha 见 w25 run 目录），仅改 batch=25→{n}、"
            f"ordinal 基 14400→{base}、\n文件名 batch_024→batch_{n:03d}，校验逻辑逐行保留（含冻结区断言）。",
            f"沿自 wave-25 merge_batch25.py（源 sha 见 w25 run 目录），仅改 batch=25→{n}、"
            f"ordinal 基 14400→{base}、文件名 batch_025→batch_{n:03d}，校验逻辑逐行保留（含冻结区断言）。"
        ) if n == 26 else merge
        with open(os.path.join(scripts, f"merge_batch{n}.py"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(merge)

        ext = open(os.path.join(SRC, "extract_cues.py"), encoding="utf-8").read()
        ext = apply_subs(ext, EXTRACT_SUBS, n, base)
        if mixed:
            ext = ext.replace(
                'lines.append(f"{m[\'ordinal\']:05d}|{body}")',
                'lines.append(f"{m[\'ordinal\']:05d}|{m[\'type\']}|{body}")')
            ext = ext.replace(
                f'本批 ordinals 14400–14999 共 600 行 type 分布为\n'
                f'600 行全部续亏（单一 type），故沿用批 14-18/20/21 的"ordinal|REASON"简化口径\n'
                f'（不保留 type 字段）；supports_direction 按 恶化组=续亏 判定\n'
                f'（利空向原因 +1、利好向原因 -1、中性/基数 0）。',
                f'本批为混合 type 批，行格式为"ordinal|type|REASON"（type 逐行给出）；\n'
                f'supports_direction 按行内 type 所属组判定（改善组=预增/略增/扭亏/续盈、\n'
                f'恶化组=预减/略减/首亏/续亏/增亏/减亏/预亏；利空向原因在恶化组 +1/在改善组 -1，\n'
                f'利好向原因在改善组 +1/在恶化组 -1，中性/基数 0）。')
        with open(os.path.join(scripts, "extract_cues.py"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(ext)

        for aux in ("check_batch_full.py", "quality_stats.py"):
            with open(os.path.join(SRC, aux), encoding="utf-8") as f_in, \
                    open(os.path.join(scripts, aux), "w", encoding="utf-8",
                         newline="\n") as f_out:
                f_out.write(f_in.read())

        # 生成 cues（确定性脚本，主对话亲自跑）
        r = subprocess.run([PY, os.path.join(scripts, "extract_cues.py"),
                            "--repo-root", ROOT, "--batch", str(n)],
                           capture_output=True, text=True, encoding="utf-8",
                           cwd=ROOT)
        if r.returncode != 0:
            print(f"[w{n}] EXTRACT FAILED:\n{r.stdout}\n{r.stderr}")
            sys.exit(1)
        cues = os.path.join(work, f"batch_{n:03d}_cues.txt")
        h = hashlib.sha256(open(cues, "rb").read()).hexdigest()[:16]
        print(f"[w{n}] dir={run_dir} cues_sha16={h} "
              f"merge_sha16="
              f"{hashlib.sha256(open(os.path.join(scripts, f'merge_batch{n}.py'),'rb').read()).hexdigest()[:16]}")
        print(f"      {r.stdout.strip()}")
        made.append(run_dir)
    print("CREATED:", *made, sep="\n  ")


if __name__ == "__main__":
    main()
