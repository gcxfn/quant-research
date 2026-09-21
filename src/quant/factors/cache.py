"""Content-addressed, verifiable feature cache.

A cache key captures every input that can change feature values:

* input dataset identity (``dataset_id`` + ``dataset_sha256``);
* the sha256 of the actual factor source code that computed the values;
* the factor parameters (windows, ddof, definitions);
* the date range and the exact sorted universe of symbols;
* adjustment semantics (which price series the input represents);
* missing-value semantics;
* a schema version for the key/cache layout itself.

On every cache hit the stored Parquet file is re-hashed and compared with the
sha256 recorded in ``manifest.json``; a mismatch (truncated, edited or
unreadable file, missing/invalid manifest, wrong identity, wrong row count)
is never returned.  Existing cache directories are immutable: a corrupt entry
is left on disk for inspection and a rebuild is written to a new unique
directory instead of overwriting it.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import polars as pl

from .core import (
    FACTOR_COLUMNS,
    FactorError,
    default_factor_params,
    validate_daily_frame,
)

__all__ = [
    "FEATURE_CACHE_SCHEMA_VERSION",
    "FeatureCache",
    "FeatureCacheConflictError",
    "FeatureCacheCorruptionError",
    "FeatureCacheError",
    "FeatureCacheKey",
    "FeatureCacheResult",
    "feature_source_files",
    "sha256_file",
    "source_code_sha256",
]

FEATURE_CACHE_SCHEMA_VERSION = 1

#: Source files whose bytes determine factor values.  Editing any of them
#: changes the cache identity, so stale features can never be served silently.
_FEATURE_SOURCE_FILES = ("core.py",)

_PARQUET_NAME = "features.parquet"
_MANIFEST_NAME = "manifest.json"


class FeatureCacheError(FactorError):
    """Base class for feature cache errors."""


class FeatureCacheCorruptionError(FeatureCacheError):
    """A cache entry exists but fails integrity verification."""


class FeatureCacheConflictError(FeatureCacheError):
    """The same cache identity was asked to store different content."""


def feature_source_files() -> tuple[Path, ...]:
    """Absolute paths of the source files that define factor values."""

    here = Path(__file__).resolve().parent
    return tuple(here / name for name in _FEATURE_SOURCE_FILES)


def sha256_file(path: str | Path) -> str:
    """Return the sha256 hex digest of a file, read in chunks."""

    digest = hashlib.sha256()
    with open(Path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_value(value: Any) -> Any:
    """Convert ``value`` to a JSON-deterministic structure or raise."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FeatureCacheError(f"params contain non-finite float: {value!r}")
        return value
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_canonical_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise FeatureCacheError(
        f"unsupported params value type {type(value).__name__}: {value!r}"
    )


def source_code_sha256(paths: Iterable[str | Path] | None = None) -> str:
    """sha256 over the actual bytes of the factor source files.

    The digest covers each file name and its bytes, so renaming, editing or
    adding a source file changes the cache identity.
    """

    files = (
        feature_source_files()
        if paths is None
        else tuple(Path(path) for path in paths)
    )
    if not files:
        raise FeatureCacheError("no source files given for source_code_sha256")
    digest = hashlib.sha256()
    digest.update(b"quant.factors.source.v1\0")
    for path in sorted(files, key=lambda item: str(item)):
        if not path.is_file():
            raise FeatureCacheError(f"factor source file not found: {path}")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _require_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise FeatureCacheError(f"{field_name} must be a 64-char sha256 hex string")
    try:
        int(value, 16)
    except ValueError as exc:  # pragma: no cover - defensive
        raise FeatureCacheError(f"{field_name} is not valid hex") from exc
    return value.lower()


@dataclass(frozen=True)
class FeatureCacheKey:
    """Frozen, content-addressed identity of a feature set."""

    dataset_id: str
    dataset_sha256: str
    source_sha256: str
    universe: tuple[str, ...]
    params: Mapping[str, Any] = field(default_factory=default_factor_params)
    date_start: str | None = None
    date_end: str | None = None
    adjustment: str = "none"
    missing: str = "preserve"
    schema_version: int = FEATURE_CACHE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise FeatureCacheError("dataset_id must be a non-empty string")
        object.__setattr__(
            self, "dataset_sha256", _require_sha256(self.dataset_sha256, "dataset_sha256")
        )
        object.__setattr__(
            self, "source_sha256", _require_sha256(self.source_sha256, "source_sha256")
        )
        symbols = tuple(str(s) for s in self.universe)
        if len(set(symbols)) != len(symbols):
            raise FeatureCacheError("universe must not contain duplicate symbols")
        object.__setattr__(self, "universe", tuple(sorted(symbols)))
        object.__setattr__(self, "params", _canonical_json_value(dict(self.params)))
        for name in ("adjustment", "missing"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise FeatureCacheError(f"{name} must be a non-empty string")
        for name in ("date_start", "date_end"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise FeatureCacheError(f"{name} must be an ISO date string or None")
        if self.date_start and self.date_end and self.date_start > self.date_end:
            raise FeatureCacheError("date_start must not be after date_end")
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise FeatureCacheError("schema_version must be a positive integer")

    def canonical(self) -> dict[str, Any]:
        """Deterministic, JSON-serialisable description of the identity."""

        return {
            "schema_version": self.schema_version,
            "dataset": {
                "dataset_id": self.dataset_id,
                "sha256": self.dataset_sha256,
            },
            "source_sha256": self.source_sha256,
            "params": self.params,
            "universe": list(self.universe),
            "date_start": self.date_start,
            "date_end": self.date_end,
            "adjustment": self.adjustment,
            "missing": self.missing,
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def key_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def feature_set_id(self) -> str:
        return f"fset-{self.key_sha256()[:16]}"


@dataclass(frozen=True)
class FeatureCacheResult:
    """Outcome of a cache lookup or compute-and-store."""

    features: pl.DataFrame
    hit: bool
    rebuilt: bool
    path: Path


def _validate_feature_frame(features: pl.DataFrame) -> None:
    if not isinstance(features, pl.DataFrame):
        raise TypeError(f"expected polars.DataFrame, got {type(features).__name__}")
    validate_daily_frame(features)
    missing = [name for name in FACTOR_COLUMNS if name not in features.columns]
    if missing:
        raise FeatureCacheError(
            f"feature frame is missing factor columns {missing}; the cache stores "
            "the output of quant.factors.compute_factors"
        )


def _plan(frame: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


class FeatureCache:
    """Content-addressed feature cache rooted at a ``data/features`` directory."""

    def __init__(
        self,
        root: str | Path,
        *,
        source_files: Sequence[str | Path] | None = None,
        source_sha256: str | None = None,
    ) -> None:
        if source_files is not None and source_sha256 is not None:
            raise FeatureCacheError("pass either source_files or source_sha256, not both")
        self.root = Path(root)
        if source_sha256 is not None:
            self._source_sha256 = _require_sha256(source_sha256, "source_sha256")
            self._source_files: tuple[Path, ...] = ()
        else:
            self._source_files = tuple(
                Path(path)
                for path in (
                    source_files if source_files is not None else feature_source_files()
                )
            )
            self._source_sha256 = source_code_sha256(self._source_files)

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def source_files(self) -> tuple[Path, ...]:
        return self._source_files

    def key_for(
        self,
        *,
        dataset_id: str,
        dataset_sha256: str,
        universe: Iterable[str],
        params: Mapping[str, Any] | None = None,
        date_start: str | date | None = None,
        date_end: str | date | None = None,
        adjustment: str = "none",
        missing: str = "preserve",
    ) -> FeatureCacheKey:
        """Build a key with this cache's factor source digest."""

        return FeatureCacheKey(
            dataset_id=dataset_id,
            dataset_sha256=dataset_sha256,
            source_sha256=self._source_sha256,
            universe=tuple(universe),
            params=default_factor_params() if params is None else params,
            date_start=None if date_start is None else str(date_start),
            date_end=None if date_end is None else str(date_end),
            adjustment=adjustment,
            missing=missing,
        )

    def key_for_frame(
        self,
        df: pl.DataFrame,
        *,
        dataset_id: str,
        dataset_sha256: str,
        params: Mapping[str, Any] | None = None,
        adjustment: str = "none",
        missing: str = "preserve",
    ) -> FeatureCacheKey:
        """Build a key whose date range and universe come from ``df``."""

        validate_daily_frame(df)
        dates = df["date"]
        return self.key_for(
            dataset_id=dataset_id,
            dataset_sha256=dataset_sha256,
            universe=df["symbol"].unique().sort().to_list(),
            params=params,
            date_start=dates.min(),
            date_end=dates.max(),
            adjustment=adjustment,
            missing=missing,
        )

    def directory_for(self, key: FeatureCacheKey, *, rebuild: str | None = None) -> Path:
        name = key.feature_set_id()
        if rebuild is not None:
            name = f"{name}-r{rebuild}"
        return self.root / name

    def _candidate_dirs(self, key: FeatureCacheKey) -> list[Path]:
        canonical = self.directory_for(key)
        siblings = sorted(
            path
            for path in self.root.glob(f"{canonical.name}-r*")
            if path.is_dir()
        )
        return [canonical, *siblings]

    def _verify(
        self, key: FeatureCacheKey, directory: Path
    ) -> tuple[dict[str, Any], str, pl.DataFrame]:
        """Verify a cache directory; return ``(manifest, parquet_sha256, frame)``."""

        def corrupt(reason: str) -> FeatureCacheCorruptionError:
            return FeatureCacheCorruptionError(
                f"feature cache entry {directory} failed verification: {reason}"
            )

        manifest_path = directory / _MANIFEST_NAME
        if not manifest_path.is_file():
            raise corrupt("manifest.json is missing")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise corrupt(f"manifest.json cannot be parsed ({exc})") from exc
        if not isinstance(manifest, dict):
            raise corrupt("manifest.json is not a JSON object")
        if manifest.get("schema_version") != key.schema_version:
            raise corrupt(
                f"manifest schema_version {manifest.get('schema_version')!r} != "
                f"{key.schema_version}"
            )
        if manifest.get("key_sha256") != key.key_sha256():
            raise corrupt("manifest key_sha256 does not match the requested identity")
        if manifest.get("key") != key.canonical():
            raise corrupt("manifest key payload does not match the requested identity")
        if manifest.get("source_sha256") != key.source_sha256:
            raise corrupt("manifest source code sha256 does not match the key")

        parquet_name = manifest.get("parquet_file", _PARQUET_NAME)
        if not isinstance(parquet_name, str) or parquet_name != _PARQUET_NAME:
            raise corrupt(f"unexpected parquet_file {parquet_name!r}")
        data_path = directory / _PARQUET_NAME
        if not data_path.is_file():
            raise corrupt(f"{_PARQUET_NAME} is missing")

        actual_sha = sha256_file(data_path)
        expected_sha = manifest.get("parquet_sha256")
        if not isinstance(expected_sha, str) or actual_sha != expected_sha:
            raise corrupt(
                f"{_PARQUET_NAME} sha256 {actual_sha} != manifest {expected_sha}"
            )
        actual_bytes = data_path.stat().st_size
        if manifest.get("parquet_bytes") != actual_bytes:
            raise corrupt(
                f"{_PARQUET_NAME} size {actual_bytes} != manifest "
                f"{manifest.get('parquet_bytes')}"
            )

        try:
            frame = pl.read_parquet(data_path)
        except Exception as exc:  # noqa: BLE001 - any read failure is corruption
            raise corrupt(f"{_PARQUET_NAME} cannot be read ({exc})") from exc
        if frame.columns != manifest.get("columns"):
            raise corrupt("stored columns do not match the manifest")
        if frame.height != manifest.get("row_count"):
            raise corrupt(
                f"row count {frame.height} != manifest {manifest.get('row_count')}"
            )
        if frame.width != manifest.get("column_count"):
            raise corrupt(
                f"column count {frame.width} != manifest {manifest.get('column_count')}"
            )
        _validate_feature_frame(frame)
        return manifest, actual_sha, frame

    def get(self, key: FeatureCacheKey) -> FeatureCacheResult | None:
        """Return a verified cache entry, or ``None`` when nothing is cached.

        Raises :class:`FeatureCacheCorruptionError` when an entry exists but
        no candidate directory passes verification.
        """

        corruption: FeatureCacheCorruptionError | None = None
        for directory in self._candidate_dirs(key):
            if not directory.is_dir():
                continue
            try:
                _, _, frame = self._verify(key, directory)
            except FeatureCacheCorruptionError as exc:
                corruption = corruption or exc
                continue
            return FeatureCacheResult(
                features=frame, hit=True, rebuilt=False, path=directory
            )
        if corruption is not None:
            raise corruption
        return None

    def put(self, key: FeatureCacheKey, features: pl.DataFrame) -> Path:
        """Store ``features`` under ``key``; return the directory.

        Idempotent for identical content.  Never overwrites an existing entry:
        identical content returns the existing path, different content raises
        :class:`FeatureCacheConflictError`, and a corrupt entry raises
        :class:`FeatureCacheCorruptionError` (use
        :meth:`get_or_compute` for an automatic safe rebuild).
        """

        _validate_feature_frame(features)
        data = _plan(features)
        parquet_sha = hashlib.sha256(data).hexdigest()

        target = self.directory_for(key)
        if target.is_dir():
            _, existing_sha, _ = self._verify(key, target)
            if existing_sha == parquet_sha:
                return target
            raise FeatureCacheConflictError(
                f"cache entry {target} already holds different content for the same "
                f"identity (existing sha256 {existing_sha}, new sha256 {parquet_sha}); "
                "feature computation must be deterministic for a given key"
            )
        if target.exists():
            raise FeatureCacheConflictError(f"{target} exists and is not a directory")

        return self._write(key, features, data=data, parquet_sha=parquet_sha)

    def _write(
        self,
        key: FeatureCacheKey,
        features: pl.DataFrame,
        *,
        data: bytes,
        parquet_sha: str,
        rebuild: str | None = None,
    ) -> Path:
        canonical_dir = self.directory_for(key)
        target = (
            canonical_dir
            if rebuild is None
            else self.directory_for(key, rebuild=rebuild)
        )
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".tmp-{uuid.uuid4().hex}"
        try:
            tmp.mkdir()
            (tmp / _PARQUET_NAME).write_bytes(data)
            manifest = {
                "schema_version": key.schema_version,
                "feature_set_id": key.feature_set_id(),
                "key_sha256": key.key_sha256(),
                "key": key.canonical(),
                "dataset": key.canonical()["dataset"],
                "source_sha256": key.source_sha256,
                "source_files": [
                    {"name": path.name, "sha256": sha256_file(path)}
                    for path in self._source_files
                ],
                "params": key.params,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "parquet_file": _PARQUET_NAME,
                "parquet_sha256": parquet_sha,
                "parquet_bytes": len(data),
                "row_count": features.height,
                "column_count": features.width,
                "columns": features.columns,
                "factors": list(FACTOR_COLUMNS),
                "sorted_by": ["symbol", "date"],
                "adjustment": key.adjustment,
                "missing": key.missing,
                "producer": "quant.factors.compute_factors",
                "rebuild": rebuild,
                "rebuilt_from": canonical_dir.name if rebuild is not None else None,
            }
            (tmp / _MANIFEST_NAME).write_text(
                json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                os.rename(tmp, target)
            except OSError:
                # Another writer won the race, or the target already exists.
                if not target.is_dir():
                    raise
                _, existing_sha, _ = self._verify(key, target)
                if existing_sha != parquet_sha:
                    raise FeatureCacheConflictError(
                        f"cache entry {target} already holds different content for the "
                        f"same identity (existing sha256 {existing_sha}, new sha256 "
                        f"{parquet_sha})"
                    )
            return target
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    def get_or_compute(
        self,
        key: FeatureCacheKey,
        compute: Callable[[], pl.DataFrame],
    ) -> FeatureCacheResult:
        """Return a verified entry, computing and storing it when needed.

        A corrupt entry is never returned and never overwritten: the frame is
        recomputed and written to a new unique rebuild directory next to the
        corrupt one, and the corrupt entry stays on disk as evidence.
        """

        corruption: FeatureCacheCorruptionError | None = None
        try:
            cached = self.get(key)
        except FeatureCacheCorruptionError as exc:
            corruption = exc
            cached = None
        if cached is not None:
            return cached

        features = compute()
        _validate_feature_frame(features)
        data = _plan(features)
        parquet_sha = hashlib.sha256(data).hexdigest()

        if corruption is None:
            path = self.put(key, features)
            return FeatureCacheResult(
                features=features, hit=False, rebuilt=False, path=path
            )

        token = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex[:8]
        )
        path = self._write(
            key, features, data=data, parquet_sha=parquet_sha, rebuild=token
        )
        return FeatureCacheResult(
            features=features, hit=False, rebuilt=True, path=path
        )
