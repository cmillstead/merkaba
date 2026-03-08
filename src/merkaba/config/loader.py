"""Centralised config loading for Merkaba.

Provides a single ``load_config()`` function that every module should use
instead of hand-rolling ``open() + json.load()`` sequences.  Supports
mtime-based caching so repeated calls within the same process are cheap.
"""

import json
import os
import threading
from typing import Any

from merkaba.paths import config_path as _default_config_path

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_mtime: float = 0.0


def load_config(
    path: str | None = None, *, use_cache: bool = True
) -> dict[str, Any]:
    """Load config.json, with optional mtime-based caching.

    Args:
        path: Override config path.  Defaults to ``merkaba.paths.config_path()``.
        use_cache: If *True*, returns cached config when the file's mtime
            has not changed since the last read.  Pass *False* to force a
            fresh read (or when using a non-default *path*).

    Returns:
        The parsed config dict.  Returns an empty dict when the file does
        not exist or contains invalid JSON.
    """
    global _cache, _cache_mtime

    import copy

    resolved = path or _default_config_path()

    if not os.path.isfile(resolved):
        return {}

    with _lock:
        mtime = os.path.getmtime(resolved)

        if use_cache and _cache is not None and mtime == _cache_mtime and path is None:
            return copy.deepcopy(_cache)

        try:
            with open(resolved, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

        if use_cache and path is None:
            _cache = data
            _cache_mtime = mtime

    return copy.deepcopy(data)


def clear_cache() -> None:
    """Clear the config cache.  Useful for testing and after config writes."""
    global _cache, _cache_mtime
    with _lock:
        _cache = None
        _cache_mtime = 0.0
