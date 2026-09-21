from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psutil


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def _find_lock(root: Path) -> Path:
    for candidate in (root / 'uv.lock', Path.cwd() / 'uv.lock'):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError('uv.lock not found under repo root or cwd')


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from start (default cwd) to the directory holding pyproject.toml + AGENTS.md.

    Installation location (site-packages) is never used: a non-editable install
    must still write artifacts into the checked-out repo, not into .venv.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / 'pyproject.toml').is_file() and (candidate / 'AGENTS.md').is_file():
            return candidate
    raise FileNotFoundError(f'no repo root (pyproject.toml + AGENTS.md) above {current}')


class Run:
    def __init__(self, root: Path, name: str, config: dict, artifacts_root: Path | None = None):
        if not (root / 'pyproject.toml').is_file():
            raise ValueError(f'repo root must contain pyproject.toml, got {root}')
        self.root = root
        self.artifacts_root = artifacts_root if artifacts_root is not None else root / 'artifacts'
        self.config = config
        self.id = datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + name + '-' + uuid.uuid4().hex[:8]
        self.path = self.artifacts_root / 'runs' / self.id
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / 'logs').mkdir()
        self.metrics: dict = {}
        self.started = time.perf_counter()
        self.peak = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample_memory, daemon=True)
        self.manifest = {
            'run_id': self.id, 'experiment_id': config['experiment_id'],
            'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat(),
            'command': [sys.executable, *sys.argv], 'config_sha256': hashlib.sha256(
                json.dumps(config, sort_keys=True).encode()).hexdigest(),
            'source_sha256': {str(p.relative_to(root)): sha256(p) for p in sorted((root / 'src').rglob('*.py'))},
            'lock_sha256': sha256(_find_lock(root)), 'python': sys.version,
            'packages': {p: importlib.metadata.version(p) for p in ['polars','pyarrow','numpy','pandas','vectorbt','backtrader','psutil']},
            'machine': {'platform': platform.platform(), 'logical_cpus': os.cpu_count(),
                        'ram_bytes': psutil.virtual_memory().total,
                        'disk_free_bytes': psutil.disk_usage(str(root)).free},
            'seed': config.get('seed'), 'date_range': [config.get('start'), config.get('end')],
            'inputs': [], 'limits': config.get('limits', {}),
        }
        write_json(self.path / 'config.json', config)
        write_json(self.path / 'manifest.json', self.manifest)

    def _sample_memory(self):
        process = psutil.Process()
        while not self.stop.is_set():
            self.peak = max(self.peak, process.memory_info().rss)
            self.stop.wait(0.02)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, kind, value, tb):
        self.stop.set()
        self.thread.join()
        self.manifest.update(status='completed' if kind is None else 'aborted' if issubclass(kind, KeyboardInterrupt) else 'failed',
                             ended_at=datetime.now(timezone.utc).isoformat(),
                             elapsed_seconds=time.perf_counter()-self.started,
                             peak_rss_bytes=self.peak,
                             memory_method='20ms process RSS sampling; includes imported libraries, excludes children')
        if kind:
            self.manifest['error'] = str(value)
            (self.path / 'logs' / 'error.txt').write_text(''.join(traceback.format_exception(kind,value,tb)), encoding='utf-8')
        write_json(self.path / 'metrics.json', self.metrics)
        if not (self.path / 'report.md').exists():
            (self.path / 'report.md').write_text(f'# {self.id}\n\nStatus: {self.manifest["status"]}\n', encoding='utf-8')
        self.manifest['outputs'] = {str(p.relative_to(self.path)): sha256(p) for p in self.path.rglob('*') if p.is_file() and p.name != 'manifest.json'}
        write_json(self.path / 'manifest.json', self.manifest)
        print(self.path)
        return False
