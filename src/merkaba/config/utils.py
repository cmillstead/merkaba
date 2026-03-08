"""Shared config file utilities."""

import copy
import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

_SECRET_KEY_NAMES = frozenset(
    {"api_key", "key", "secret", "token", "password", "encryption_key", "totp_secret"}
)


def atomic_write_json(path: str, data: dict, **kwargs) -> None:
    """Write JSON to a file atomically via tmp+rename.

    Writes to a temp file in the same directory, fsyncs, then atomically
    replaces the target.  If anything fails the original file is untouched.
    """
    dir_ = os.path.dirname(path) or "."
    os.makedirs(dir_, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, **kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError as e:
            logger.debug("Failed to clean up temp file %s: %s", tmp, e)
        raise


def deep_mask_secrets(config: dict) -> dict:
    """Return a deep copy of config with all secret-like values masked.

    Recursively walks the dict and masks any key whose name is in
    _SECRET_KEY_NAMES.  Values longer than 8 chars show first 4 + *** + last 4.
    """
    result = copy.deepcopy(config)
    _mask_recursive(result)
    return result


def _mask_recursive(d: dict) -> None:
    """In-place recursive masking of secret values."""
    for key, value in d.items():
        if isinstance(value, dict):
            _mask_recursive(value)
        elif key in _SECRET_KEY_NAMES and isinstance(value, str):
            if len(value) > 4:
                d[key] = value[:4] + "***"
            else:
                d[key] = "***"


def deep_strip_secrets(config: dict) -> dict:
    """Return a deep copy of config with all secret-like keys removed entirely.

    Unlike ``deep_mask_secrets`` (which replaces values with masked strings),
    this function *removes* the keys altogether.  Intended for backup copies
    where sensitive values should never be persisted.
    """
    result = copy.deepcopy(config)
    _strip_recursive(result)
    return result


def _strip_recursive(d: dict) -> None:
    """In-place recursive removal of secret keys."""
    keys_to_remove = [k for k in d if k in _SECRET_KEY_NAMES]
    for k in keys_to_remove:
        del d[k]
    for value in d.values():
        if isinstance(value, dict):
            _strip_recursive(value)
