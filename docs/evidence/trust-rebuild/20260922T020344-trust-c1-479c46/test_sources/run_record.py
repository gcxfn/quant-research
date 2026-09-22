#!/usr/bin/env python
"""跑一条真实命令并产出符合模板的 run_record（C1 证据工具）。

作用：把「实际执行的命令 / 退出码 / 起止时间 / 资源 / 代码与配置身份 /
输出臂」写成一个 JSON，供 ``check_delivery.py`` 与审阅者核对。它不是
验收工具，也不替代真实运行日志。

身份摘要的诚实边界：``code_sha256`` = 显式 ``--code-file`` 清单的
``sha256("relpath\\0entry_sha256\\n" 排序拼接)``，只覆盖列出的文件，不是
整个仓库树；命令运行前后各算一次并要求相等，用来发现“运行中被改写”。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:  # psutil 是项目依赖；缺它就明确失败，不静默降级
    raise SystemExit("psutil is required for run_record resource sampling")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def digest_files(root: Path, files: list[str]) -> str:
    lines = []
    for rel in sorted(files):
        path = root / rel
        if not path.is_file():
            raise SystemExit(f"code file missing: {rel}")
        lines.append(f"{rel.replace(chr(92), '/')}\0{sha256_file(path)}\n")
    return hashlib.sha256("".join(lines).encode()).hexdigest()


class MemoryMonitor:
    """采样**子进程**及其后代进程的峰值 RSS（不是采样本 harness 自己）。

    早期版本采样的是 harness 自身，导致 run 记录的 peak_rss_mb 恒为 ~21 MB，
    会低报真实资源占用；这里改为跟随被测命令的进程树。
    """

    def __init__(self, interval: float = 0.2) -> None:
        self.interval = interval
        self.peak = 0.0
        self.samples = 0
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def follow(self, proc: subprocess.Popen) -> "MemoryMonitor":
        self._proc = proc

        def loop() -> None:
            while proc.poll() is None:
                rss = 0
                try:
                    parent = psutil.Process(proc.pid)
                    rss = parent.memory_info().rss
                    for child in parent.children(recursive=True):
                        try:
                            rss += child.memory_info().rss
                        except psutil.Error:
                            pass
                except psutil.Error:
                    rss = 0
                self.peak = max(self.peak, rss / (1024 * 1024))
                self.samples += 1
                time.sleep(self.interval)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()
        return self

    def join(self) -> None:
        if self._thread:
            self._thread.join(timeout=5.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stage-id", default="C1")
    parser.add_argument("--kind", default="engineering_run")
    parser.add_argument("--code-file", action="append", default=[])
    parser.add_argument("--config-file", action="append", default=[])
    parser.add_argument("--arm", action="append", default=[],
                        help="NAME=OUTPUT_PATH；输出存在且非空才算实际产出")
    parser.add_argument("--out", required=True)
    parser.add_argument("--stdout", required=True)
    parser.add_argument("--stderr", required=True)
    parser.add_argument("--approval-reference", default=None)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("no command given (use -- <cmd> ...)")

    root = Path(args.repo_root).resolve()
    code_before = digest_files(root, args.code_file) if args.code_file else None
    # 规则（交付包检查器要求 HEX64 标量）：config_sha256_at_* 是配置**集合**的
    # 单一摘要；逐文件摘要另存 config_files_sha256_at_*，两者都可追溯。
    config_rel = list(args.config_file)
    config_before = digest_files(root, config_rel) if config_rel else None
    config_files_before = ([sha256_file(root / c) for c in config_rel]
                           if config_rel else None)

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stdout_path = root / args.stdout
    stderr_path = root / args.stderr
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)

    started_utc = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    monitor = MemoryMonitor()
    with stdout_path.open("w", encoding="utf-8") as so, \
            stderr_path.open("w", encoding="utf-8") as se:
        process = subprocess.Popen(command, cwd=str(root), stdout=so, stderr=se,
                                   text=True)
        monitor.follow(process)
        returncode = process.wait()
        monitor.join()
    elapsed = time.perf_counter() - t0
    ended_utc = datetime.now(timezone.utc)

    code_after = digest_files(root, args.code_file) if args.code_file else None
    config_after = digest_files(root, config_rel) if config_rel else None
    config_files_after = ([sha256_file(root / c) for c in config_rel]
                          if config_rel else None)

    expected_arms: list[str] = []
    actual_arms: list[str] = []
    for spec in args.arm:
        if "=" not in spec:
            raise SystemExit(f"--arm expects NAME=PATH, got {spec!r}")
        name, rel = spec.split("=", 1)
        expected_arms.append(name)
        p = root / rel
        if p.is_file() and p.stat().st_size > 0:
            actual_arms.append(name)

    status = "completed" if returncode == 0 else "failed"
    if set(expected_arms) != set(actual_arms):
        status = "failed"

    record = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "kind": args.kind,
        "status": status,
        "stage_id": args.stage_id,
        "command": command,
        "cwd": str(root),
        "started_at_utc": started_utc.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": ended_utc.isoformat().replace("+00:00", "Z"),
        "wall_seconds": round(elapsed, 3),
        "exit_code": returncode,
        "code_sha256_at_start": code_before,
        "code_sha256_at_end": code_after,
        "code_files": sorted(args.code_file),
        "config_sha256_at_start": config_before,
        "config_sha256_at_end": config_after,
        "config_files": args.config_file,
        "config_files_sha256_at_start": config_files_before,
        "config_files_sha256_at_end": config_files_after,
        "input_manifest_sha256": None,
        "expected_arms": expected_arms,
        "actual_arms": actual_arms,
        "resource_usage": {
            "peak_rss_mb": round(monitor.peak, 1),
            "memory_samples": monitor.samples,
            "workers": 1,
        },
        "stdout_path": args.stdout,
        "stderr_path": args.stderr,
        "junit_path": None,
        "outputs": [spec.split("=", 1)[1] for spec in args.arm],
        "approval_reference": args.approval_reference,
    }
    out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({"status": status, "exit_code": returncode,
                      "wall_seconds": record["wall_seconds"],
                      "peak_rss_mb": record["resource_usage"]["peak_rss_mb"],
                      "actual_arms": actual_arms}, ensure_ascii=False))
    return returncode if status == "completed" else max(returncode, 1)


if __name__ == "__main__":
    raise SystemExit(main())
