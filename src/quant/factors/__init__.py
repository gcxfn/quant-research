"""Factor layer: backward-looking factors, close-time signals, feature cache.

Concrete entry points
---------------------

``compute_factors(df) -> pl.DataFrame``
    Validate a daily OHLCV frame (unique ``(symbol, date)`` key, sorted,
    positive prices, finite, nulls allowed) and append exactly seven
    ``Float64`` factors in this order: ``ret_1``, ``ret_5``, ``ret_20``,
    ``volatility_20`` (rolling std of ``ret_1``, ``ddof=1``),
    ``amount_mean_20``, ``sma_20``, ``range_pct = (high - low) / close``.
    Original columns are preserved unchanged.  Warm-up rows stay ``null``;
    ``inf`` can never be returned.

``build_signals(df, *, sma_window=20, ret_window=5, signal_column="signal")``
    Add ``above_sma_20`` (close > sma_20), ``ret_5_positive`` (ret_5 > 0) and
    the combined boolean ``signal``; all are known at the close of the bar and
    stay ``null`` while their inputs are unavailable.

``FeatureCache(root, *, source_files=None, source_sha256=None)``
    Content-addressed cache under ``data/features``.
    ``key_for(...)`` / ``key_for_frame(...)`` build a
    :class:`FeatureCacheKey` from dataset identity + dataset sha256, the
    factor source-code sha256, params, date range, universe, adjustment and
    missing semantics.  ``put``, ``get`` and ``get_or_compute`` verify
    ``manifest.json`` against a freshly computed Parquet sha256 on every hit;
    corrupt entries are reported (``get``) or rebuilt into a new unique
    directory (``get_or_compute``) and never silently returned or overwritten.
"""

from .cache import (
    FEATURE_CACHE_SCHEMA_VERSION,
    FeatureCache,
    FeatureCacheConflictError,
    FeatureCacheCorruptionError,
    FeatureCacheError,
    FeatureCacheKey,
    FeatureCacheResult,
    feature_source_files,
    sha256_file,
    source_code_sha256,
)
from .core import (
    DEFAULT_FACTOR_PARAMS,
    FACTOR_COLUMNS,
    KEY_COLUMNS,
    NUMERIC_COLUMNS,
    PRICE_COLUMNS,
    REQUIRED_COLUMNS,
    FactorComputationError,
    FactorError,
    FactorValidationError,
    compute_factors,
    default_factor_params,
    validate_daily_frame,
)
from .signals import DEFAULT_SIGNAL_COLUMN, build_signals

__all__ = [
    "DEFAULT_FACTOR_PARAMS",
    "DEFAULT_SIGNAL_COLUMN",
    "FACTOR_COLUMNS",
    "FEATURE_CACHE_SCHEMA_VERSION",
    "FactorComputationError",
    "FactorError",
    "FactorValidationError",
    "FeatureCache",
    "FeatureCacheConflictError",
    "FeatureCacheCorruptionError",
    "FeatureCacheError",
    "FeatureCacheKey",
    "FeatureCacheResult",
    "KEY_COLUMNS",
    "NUMERIC_COLUMNS",
    "PRICE_COLUMNS",
    "REQUIRED_COLUMNS",
    "build_signals",
    "compute_factors",
    "default_factor_params",
    "feature_source_files",
    "sha256_file",
    "source_code_sha256",
    "validate_daily_frame",
]
