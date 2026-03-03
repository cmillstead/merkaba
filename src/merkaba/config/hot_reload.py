# src/merkaba/config/hot_reload.py
"""Hot-reloadable configuration with mtime checking.

On every .get() call, checks file stat().st_mtime against cached value.
If changed, re-reads. If JSON is malformed, logs warning and keeps previous config.
"""

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("merkaba.config")

# Keys that require restart — security-critical changes log a warning.
# Values ARE loaded immediately; restart is recommended but not enforced.
SECURITY_KEYS = frozenset({
    "permissions",
    "permission_tiers",
    "path_restrictions",
    "shell_allowlist",
    "auto_approve_level",
    "auto_approve",
    "encryption_key",
    "api_key",
})


@dataclass
class ConfigSnapshot:
    """Tracks a config file's content and mtime."""

    path: Path
    data: dict = field(default_factory=dict)
    _mtime: float = 0.0

    def __post_init__(self):
        self.path = Path(self.path)

    def reload(self) -> bool:
        """Reload config from disk. Returns True if content changed."""
        try:
            new_mtime = self.path.stat().st_mtime
            with open(self.path) as f:
                new_data = json.load(f)
            old_data = self.data
            self.data = new_data
            self._mtime = new_mtime
            return new_data != old_data
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.warning("Config reload failed for %s: %s", self.path, e)
            return False

    def is_stale(self) -> bool:
        """Check if the file has been modified since last reload."""
        try:
            current_mtime = self.path.stat().st_mtime
            return current_mtime > self._mtime
        except (FileNotFoundError, OSError):
            return False


ChangeCallback = Callable[[set, dict, dict], None]


class HotConfig:
    """Hot-reloadable configuration wrapper.

    Checks file mtime on every get() call. If the file has changed,
    re-reads it. If JSON is malformed, keeps previous valid config.

    Security-critical keys log a warning when changed but the new
    values are still loaded (restart is recommended but not enforced).
    """

    def __init__(self, config_path: "Path | str"):
        self._snapshot = ConfigSnapshot(Path(config_path))
        self._snapshot.reload()
        self._callbacks: list = []
        self._lock = threading.Lock()

        # Automatically clear the provider cache when config changes, so
        # updated API keys and cloud_providers settings take effect immediately.
        def _clear_provider_cache(
            changed_keys: set, old_data: dict, new_data: dict
        ) -> None:
            try:
                from merkaba.llm_providers.registry import clear_cache
                clear_cache()
                logger.debug("Provider cache cleared after config change (keys: %s)", changed_keys)
            except Exception as exc:
                logger.warning("Failed to clear provider cache on config change: %s", exc)

        self._callbacks.append(_clear_provider_cache)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value, reloading from disk if file changed."""
        self._maybe_reload()
        return self._snapshot.data.get(key, default)

    def get_all(self) -> dict:
        """Get the full config dict, reloading from disk if file changed."""
        self._maybe_reload()
        return dict(self._snapshot.data)

    def on_change(self, callback: ChangeCallback):
        """Register a callback for config changes.

        Callback receives (changed_keys: set[str], old_data: dict, new_data: dict).
        """
        self._callbacks.append(callback)

    def _maybe_reload(self):
        """Check mtime and reload if stale. Thread-safe with double-checked locking."""
        if not self._snapshot.is_stale():
            return

        with self._lock:
            if not self._snapshot.is_stale():  # Double-check under lock
                return

            old_data = dict(self._snapshot.data)
            changed = self._snapshot.reload()
            if not changed:
                return

            new_data = self._snapshot.data
            changed_keys = {
                k for k in set(old_data) | set(new_data)
                if old_data.get(k) != new_data.get(k)
            }

            # Log security-relevant changes
            security_changed = changed_keys & SECURITY_KEYS
            if security_changed:
                logger.warning(
                    "Security-relevant config changed: %s. "
                    "Restart recommended to confirm these changes.",
                    ", ".join(sorted(security_changed)),
                )

            # Fire callbacks
            for cb in self._callbacks:
                try:
                    cb(changed_keys, old_data, new_data)
                except Exception as e:
                    logger.warning("Config change callback failed: %s", e)
