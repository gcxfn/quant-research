"""Dev 沙箱加载器（C1 数据隔离）。

目标：研究运行只能读受控导出的 Dev-only 工作集
``data/processed/dev-sandbox-20260922/``，不能读混合年份原始文件或任何
Val 路径。隔离靠三层强制，而不是靠“读全文件后在内存里过滤”：

1. **数据集白名单**：只有 ``dataset_manifest.json`` 登记的 ``dataset_id``
   可用，其他 id（例如 ``baostock-daily-20260917``、``halfday-bars-20260918``
   这类含 2021+ 行的产物）直接拒绝；
2. **文件白名单**：``resolve()`` 只接受 manifest 逐文件登记的相对路径，
   任何未登记路径（包括真实 Val 文件路径）抛 ``PathNotAllowedError``；
3. **日期上限**：每个数据集在 manifest 里带 ``max_allowed_date``；请求
   超出上限即拒绝，读取后再断言一次实际最大日期，越界即报错。

``cache_key()`` 实现主计划要求的缓存键：dataset_id + 输入文件 SHA256 +
股票池/日期范围 + 复权口径 + 代码/参数摘要，不靠文件名或修改时间。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

import polars as pl

SANDBOX_DATASET_ID_DEFAULT = "dev-sandbox-20260922"
SANDBOX_ROOT_REL = Path("data/processed")
MANIFEST_NAME = "dataset_manifest.json"
ALLOWED_DATASET_IDS = frozenset({SANDBOX_DATASET_ID_DEFAULT})
KINDS = ("bars_daily", "bars_daily_warmup", "bars_halfday", "limit", "forecast_event")


class SandboxAccessError(RuntimeError):
    """沙箱访问被拒绝（未知数据集、未登记路径、越界日期）。"""


class UnknownDatasetError(SandboxAccessError):
    pass


class PathNotAllowedError(SandboxAccessError):
    pass


class DateRangeError(SandboxAccessError):
    pass


class StaleDataError(SandboxAccessError):
    pass


@dataclass(frozen=True)
class SandboxFile:
    rel_path: str
    sha256: str
    rows: int
    date_min: str | None
    date_max: str | None


@dataclass(frozen=True)
class SandboxDataset:
    kind: str
    dataset_id: str
    date_column: str
    symbol_column: str
    max_allowed_date: date | None
    min_allowed_date: date | None
    purpose: str
    semantics: str
    files: tuple[SandboxFile, ...]
    columns: tuple[str, ...]
    units: dict

    def rel_paths(self) -> list[str]:
        return [f.rel_path for f in self.files]


@dataclass(frozen=True)
class SandboxManifest:
    dataset_id: str
    contract_sha256: str
    datasets: dict[str, SandboxDataset]
    raw: dict


def find_repo_root(start: Path | None = None) -> Path:
    """向上找含 src/quant 与 data/ 的项目根。"""
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "src" / "quant").is_dir() and (candidate / "data").is_dir():
            return candidate
    raise SandboxAccessError(f"cannot locate repo root from {here}")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class SandboxRegistry:
    """按 manifest 强制访问权限的 Dev 沙箱。"""

    def __init__(self, repo_root: Path, manifest: SandboxManifest,
                 sandbox_dir: Path) -> None:
        self.repo_root = repo_root
        self.manifest = manifest
        self.sandbox_dir = sandbox_dir
        self.dataset_id = manifest.dataset_id
        self._by_rel: dict[str, SandboxFile] = {
            f.rel_path: f for ds in manifest.datasets.values() for f in ds.files
        }

    # -- 构造 --------------------------------------------------------------- #
    @classmethod
    def load(cls, repo_root: Path | None = None,
             dataset_id: str = SANDBOX_DATASET_ID_DEFAULT) -> "SandboxRegistry":
        root = (repo_root or find_repo_root()).resolve()
        if dataset_id not in ALLOWED_DATASET_IDS:
            raise UnknownDatasetError(
                f"dataset_id {dataset_id!r} is not an allowed Dev sandbox dataset; "
                f"allowed: {sorted(ALLOWED_DATASET_IDS)}. Mixed-year or validation "
                f"products must not be mounted into research runs."
            )
        sandbox_dir = root / SANDBOX_ROOT_REL / dataset_id
        manifest_path = sandbox_dir / MANIFEST_NAME
        if not manifest_path.is_file():
            raise UnknownDatasetError(f"sandbox manifest not found: {manifest_path}")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if raw.get("dataset_id") != dataset_id:
            raise SandboxAccessError(
                f"manifest dataset_id={raw.get('dataset_id')!r} != requested {dataset_id!r}")
        datasets: dict[str, SandboxDataset] = {}
        for entry in raw.get("datasets", []):
            files = tuple(
                SandboxFile(f["rel_path"], f["sha256"], int(f.get("rows", 0)),
                            f.get("date_min"), f.get("date_max"))
                for f in entry["files"]
            )
            ds = SandboxDataset(
                kind=entry["kind"], dataset_id=dataset_id,
                date_column=entry["date_column"],
                symbol_column=entry.get("symbol_column", "symbol"),
                max_allowed_date=_as_date(entry.get("max_allowed_date")),
                min_allowed_date=_as_date(entry.get("min_allowed_date")),
                purpose=entry.get("purpose", ""),
                semantics=entry.get("semantics", ""),
                files=files,
                columns=tuple(entry.get("columns", [])),
                units=entry.get("units", {}),
            )
            datasets[ds.kind] = ds
        return cls(root, SandboxManifest(dataset_id, raw.get("contract_sha256", ""),
                                         datasets, raw), sandbox_dir)

    # -- 访问强制 ----------------------------------------------------------- #
    def dataset(self, kind: str) -> SandboxDataset:
        if kind not in self.manifest.datasets:
            raise UnknownDatasetError(
                f"unknown dataset kind {kind!r}; manifest declares "
                f"{sorted(self.manifest.datasets)}")
        return self.manifest.datasets[kind]

    def resolve(self, rel_path: str) -> Path:
        """只解析 manifest 登记过的文件；其余一律拒绝。"""
        normalized = rel_path.replace("\\", "/").lstrip("./")
        entry = self._by_rel.get(normalized)
        if entry is None:
            raise PathNotAllowedError(
                f"path {rel_path!r} is not registered in the {self.dataset_id} manifest; "
                f"raw/mixed-year or validation files are not readable through the sandbox"
            )
        path = (self.repo_root / normalized).resolve()
        if not path.is_relative_to(self.sandbox_dir.resolve()):
            raise PathNotAllowedError(f"registered path escapes the sandbox: {rel_path!r}")
        if not path.is_file():
            raise PathNotAllowedError(f"registered sandbox file is missing: {rel_path!r}")
        return path

    def verify_files(self, kind: str) -> dict[str, bool]:
        """重算登记文件 SHA256，返回逐文件是否一致。"""
        ds = self.dataset(kind)
        return {f.rel_path: sha256_file(self.resolve(f.rel_path)) == f.sha256
                for f in ds.files}

    # -- 读取 --------------------------------------------------------------- #
    def read(
        self,
        kind: str,
        *,
        columns: Sequence[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        symbols: Iterable[str] | None = None,
        verify_sha: bool = False,
    ) -> pl.DataFrame:
        ds = self.dataset(kind)
        if start is not None and end is not None and start > end:
            raise DateRangeError(f"start {start} is after end {end}")
        for bound, label in ((ds.max_allowed_date, "max_allowed_date"),
                             (ds.min_allowed_date, "min_allowed_date")):
            if bound is None:
                continue
            if label == "max_allowed_date":
                if end is not None and end > bound:
                    raise DateRangeError(
                        f"requested end {end} exceeds dataset {kind} {label} {bound}; "
                        f"the Dev sandbox must never read validation/frozen dates")
            else:
                if start is not None and start < bound:
                    raise DateRangeError(
                        f"requested start {start} precedes dataset {kind} {label} {bound}")
        if columns is not None and ds.columns:
            unknown = [c for c in columns if c not in ds.columns]
            if unknown:
                raise SandboxAccessError(
                    f"columns {unknown} are not declared for dataset {kind}")
        if verify_sha:
            bad = [p for p, ok in self.verify_files(kind).items() if not ok]
            if bad:
                raise SandboxAccessError(f"SHA256 mismatch for {kind}: {bad}")

        paths = [str(self.resolve(rel)) for rel in ds.rel_paths()]
        lf = pl.scan_parquet(paths, hive_partitioning=False)
        expr: list[pl.Expr] = []
        if start is not None:
            expr.append(pl.col(ds.date_column) >= start)
        if end is not None:
            expr.append(pl.col(ds.date_column) <= end)
        if symbols is not None:
            syms = sorted(set(str(s) for s in symbols))
            expr.append(pl.col(ds.symbol_column).is_in(syms))
        if expr:
            lf = lf.filter(*expr)
        if columns is not None:
            lf = lf.select(list(columns))
        frame = lf.collect()
        if frame.height:
            observed_max = frame[ds.date_column].max()
            observed_min = frame[ds.date_column].min()
            if ds.max_allowed_date is not None and observed_max > ds.max_allowed_date:
                raise DateRangeError(
                    f"dataset {kind} returned a row dated {observed_max} beyond "
                    f"max_allowed_date {ds.max_allowed_date}; sandbox is not Dev-only")
            if ds.min_allowed_date is not None and observed_min < ds.min_allowed_date:
                raise DateRangeError(
                    f"dataset {kind} returned a row dated {observed_min} before "
                    f"min_allowed_date {ds.min_allowed_date}")
        return frame

    # -- 缓存键 -------------------------------------------------------------- #
    def cache_key(
        self,
        kind: str,
        *,
        start: date | None = None,
        end: date | None = None,
        symbols: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
        adjust_mode: str = "unadjusted",
        code_digest: str = "",
        params_digest: str = "",
    ) -> str:
        """因子/数据缓存键：dataset_id + 输入 SHA256 + 池/日期 + 复权 + 代码摘要。"""
        ds = self.dataset(kind)
        if adjust_mode not in {"unadjusted", "back_adjusted", "total_return"}:
            raise SandboxAccessError(f"unknown adjust_mode {adjust_mode!r}")
        symbol_digest = ""
        if symbols is not None:
            syms = sorted(set(str(s) for s in symbols))
            symbol_digest = hashlib.sha256("\n".join(syms).encode()).hexdigest()
            symbol_count = len(syms)
        else:
            symbol_count = None
        payload = {
            "key_version": 1,
            "dataset_id": self.dataset_id,
            "kind": kind,
            "inputs": sorted(
                {"rel_path": f.rel_path, "sha256": f.sha256} for f in ds.files
            ),
            "date_range": [start.isoformat() if start else None,
                           end.isoformat() if end else None],
            "symbol_count": symbol_count,
            "symbol_digest": symbol_digest,
            "columns": sorted(columns) if columns else sorted(ds.columns),
            "adjust_mode": adjust_mode,
            "code_digest": code_digest,
            "params_digest": params_digest,
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(blob).hexdigest()


def _as_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    assert isinstance(value, str)
    return date.fromisoformat(value)
