"""File permission enforcement for sensitive data files."""
import logging
import os
import platform
import stat

logger = logging.getLogger(__name__)


def ensure_secure_permissions(path: str) -> None:
    """Set restrictive permissions on sensitive files/directories.

    - Directories: 0o700 (owner rwx only)
    - Files: 0o600 (owner rw only)
    - No-op on non-Unix platforms (Windows).
    """
    if platform.system() == "Windows":
        logger.debug("Skipping file permission enforcement on Windows: %s", path)
        return

    try:
        st = os.stat(path)
    except OSError as exc:
        logger.warning("Could not stat path for permission check: %s — %s", path, exc)
        return

    if stat.S_ISDIR(st.st_mode):
        target_mode = 0o700
        kind = "directory"
    else:
        target_mode = 0o600
        kind = "file"

    current_mode = stat.S_IMODE(st.st_mode)
    if current_mode != target_mode:
        try:
            os.chmod(path, target_mode)
            logger.debug(
                "Set %s permissions on %s (%s → %s)",
                kind,
                path,
                oct(current_mode),
                oct(target_mode),
            )
        except OSError as exc:
            logger.warning(
                "Could not set permissions on %s %s: %s", kind, path, exc
            )
    else:
        logger.debug(
            "Permissions already correct on %s %s (%s)",
            kind,
            path,
            oct(current_mode),
        )
