# tests/test_file_permissions.py
"""Tests for file permission enforcement on sensitive data paths."""
import os
import stat
import tempfile
from unittest.mock import patch

import pytest

from merkaba.security.file_permissions import ensure_secure_permissions


def _mode(path: str) -> int:
    """Return the permission bits (mode) of a path."""
    return stat.S_IMODE(os.stat(path).st_mode)


class TestEnsureSecurePermissionsDirectory:
    def test_sets_700_on_directory(self):
        """A directory should be chmod'd to 0o700."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Widen permissions first so we can verify the change.
            os.chmod(tmpdir, 0o755)
            assert _mode(tmpdir) == 0o755

            ensure_secure_permissions(tmpdir)

            assert _mode(tmpdir) == 0o700

    def test_directory_already_700_is_no_op(self):
        """Calling on a directory already at 0o700 should not raise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.chmod(tmpdir, 0o700)
            ensure_secure_permissions(tmpdir)  # must not raise
            assert _mode(tmpdir) == 0o700


class TestEnsureSecurePermissionsFile:
    def test_sets_600_on_file(self):
        """A file should be chmod'd to 0o600."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            os.chmod(tmp_path, 0o644)
            assert _mode(tmp_path) == 0o644

            ensure_secure_permissions(tmp_path)

            assert _mode(tmp_path) == 0o600
        finally:
            os.unlink(tmp_path)

    def test_file_already_600_is_no_op(self):
        """Calling on a file already at 0o600 should not raise."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name

        try:
            os.chmod(tmp_path, 0o600)
            ensure_secure_permissions(tmp_path)  # must not raise
            assert _mode(tmp_path) == 0o600
        finally:
            os.unlink(tmp_path)


class TestEnsureSecurePermissionsNonexistent:
    def test_nonexistent_path_does_not_raise(self):
        """A path that does not exist should be handled gracefully (log warning, no crash)."""
        ensure_secure_permissions("/tmp/merkaba_nonexistent_test_path_xyz_12345")
        # If we get here without an exception the test passes.


class TestLogAndUploadDirPermissions:
    """M18, M19: Log and upload directories must have secure permissions."""

    def test_log_dir_has_secure_permissions(self, tmp_path):
        """M18: Log directory must have 0o700 permissions."""
        log_dir = str(tmp_path / "logs")
        os.makedirs(log_dir)
        ensure_secure_permissions(log_dir)
        assert _mode(log_dir) == 0o700

    def test_upload_dir_has_secure_permissions(self, tmp_path):
        """M19: Upload directory must have 0o700 permissions."""
        upload_dir = str(tmp_path / "uploads")
        os.makedirs(upload_dir)
        ensure_secure_permissions(upload_dir)
        assert _mode(upload_dir) == 0o700

    def test_tracing_setup_calls_ensure_secure_permissions(self):
        """M18: setup_logging must call ensure_secure_permissions on log_dir."""
        import inspect
        from merkaba.observability.tracing import setup_logging
        source = inspect.getsource(setup_logging)
        assert "ensure_secure_permissions" in source

    def test_chat_upload_calls_ensure_secure_permissions(self):
        """M19: upload_file must call ensure_secure_permissions on UPLOAD_DIR."""
        import inspect
        from merkaba.web.routes.chat import upload_file
        source = inspect.getsource(upload_file)
        assert "ensure_secure_permissions" in source


class TestEnsureSecurePermissionsWindows:
    def test_windows_skips_chmod(self):
        """On Windows, ensure_secure_permissions should be a no-op (no chmod called)."""
        with patch("merkaba.security.file_permissions.platform.system", return_value="Windows"), \
             patch("merkaba.security.file_permissions.os.chmod") as mock_chmod, \
             patch("merkaba.security.file_permissions.os.stat"):
            ensure_secure_permissions("/some/path")
            mock_chmod.assert_not_called()
