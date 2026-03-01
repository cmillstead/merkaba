# tests/test_file_security.py
"""Security tests for file operation path restrictions."""
import os
import tempfile
import pytest
from pathlib import Path
from merkaba.tools.builtin.files import is_path_allowed, file_read, file_write


class TestAllowedPaths:
    """Test that legitimate paths are allowed."""

    def test_allows_regular_file_in_cwd(self):
        """Regular files in current directory should be allowed."""
        allowed, reason = is_path_allowed("./test_file.txt")
        assert allowed is True, f"Regular file should be allowed: {reason}"

    def test_allows_absolute_path_in_tmp(self):
        """Files in /tmp should be allowed."""
        allowed, reason = is_path_allowed("/tmp/test_file.txt")
        assert allowed is True, f"/tmp files should be allowed: {reason}"

    def test_allows_home_directory_file(self):
        """Regular files in home directory should be allowed."""
        allowed, reason = is_path_allowed("~/Documents/test.txt")
        assert allowed is True, f"Home directory files should be allowed: {reason}"

    def test_allows_project_files(self):
        """Project source files should be allowed."""
        allowed, reason = is_path_allowed("/Users/test/project/src/main.py")
        assert allowed is True, f"Project files should be allowed: {reason}"

    def test_allows_regular_json_file(self):
        """Regular JSON files (not credentials.json) should be allowed."""
        allowed, reason = is_path_allowed("./config/settings.json")
        assert allowed is True, f"Regular JSON files should be allowed: {reason}"

    def test_allows_regular_yaml_file(self):
        """Regular YAML files (not secrets.yaml) should be allowed."""
        allowed, reason = is_path_allowed("./config/app.yaml")
        assert allowed is True, f"Regular YAML files should be allowed: {reason}"


class TestDeniedDirectoryPaths:
    """Test that sensitive directories are blocked."""

    def test_blocks_ssh_directory(self):
        """~/.ssh should be blocked."""
        allowed, reason = is_path_allowed("~/.ssh/id_rsa")
        assert allowed is False
        assert "restricted" in reason.lower() or "denied" in reason.lower()

    def test_blocks_ssh_config(self):
        """~/.ssh/config should be blocked."""
        allowed, reason = is_path_allowed("~/.ssh/config")
        assert allowed is False

    def test_blocks_gnupg_directory(self):
        """~/.gnupg should be blocked."""
        allowed, reason = is_path_allowed("~/.gnupg/private-keys-v1.d")
        assert allowed is False

    def test_blocks_aws_directory(self):
        """~/.aws should be blocked."""
        allowed, reason = is_path_allowed("~/.aws/credentials")
        assert allowed is False

    def test_blocks_aws_config(self):
        """~/.aws/config should be blocked."""
        allowed, reason = is_path_allowed("~/.aws/config")
        assert allowed is False

    def test_blocks_gcloud_directory(self):
        """~/.config/gcloud should be blocked."""
        allowed, reason = is_path_allowed("~/.config/gcloud/credentials.db")
        assert allowed is False

    def test_blocks_kube_directory(self):
        """~/.kube should be blocked."""
        allowed, reason = is_path_allowed("~/.kube/config")
        assert allowed is False

    def test_blocks_azure_directory(self):
        """~/.azure should be blocked."""
        allowed, reason = is_path_allowed("~/.azure/credentials")
        assert allowed is False

    def test_blocks_netrc(self):
        """~/.netrc should be blocked."""
        allowed, reason = is_path_allowed("~/.netrc")
        assert allowed is False

    def test_blocks_git_credentials(self):
        """~/.git-credentials should be blocked."""
        allowed, reason = is_path_allowed("~/.git-credentials")
        assert allowed is False

    def test_blocks_etc_passwd(self):
        """/etc/passwd should be blocked."""
        allowed, reason = is_path_allowed("/etc/passwd")
        assert allowed is False

    def test_blocks_etc_shadow(self):
        """/etc/shadow should be blocked."""
        allowed, reason = is_path_allowed("/etc/shadow")
        assert allowed is False

    def test_blocks_etc_sudoers(self):
        """/etc/sudoers should be blocked."""
        allowed, reason = is_path_allowed("/etc/sudoers")
        assert allowed is False


class TestDeniedFilenamePatterns:
    """Test that sensitive filename patterns are blocked."""

    def test_blocks_env_file(self):
        """.env should be blocked."""
        allowed, reason = is_path_allowed(".env")
        assert allowed is False
        assert "restricted pattern" in reason.lower()

    def test_blocks_env_file_in_path(self):
        """.env in a path should be blocked."""
        allowed, reason = is_path_allowed("/path/to/project/.env")
        assert allowed is False

    def test_blocks_env_local(self):
        """.env.local should be blocked."""
        allowed, reason = is_path_allowed(".env.local")
        assert allowed is False

    def test_blocks_env_production(self):
        """.env.production should be blocked."""
        allowed, reason = is_path_allowed("/app/.env.production")
        assert allowed is False

    def test_blocks_credentials_json(self):
        """credentials.json should be blocked."""
        allowed, reason = is_path_allowed("credentials.json")
        assert allowed is False

    def test_blocks_credentials_json_in_path(self):
        """credentials.json in a path should be blocked."""
        allowed, reason = is_path_allowed("/path/to/credentials.json")
        assert allowed is False

    def test_blocks_secrets_yaml(self):
        """secrets.yaml should be blocked."""
        allowed, reason = is_path_allowed("secrets.yaml")
        assert allowed is False

    def test_blocks_id_rsa(self):
        """id_rsa should be blocked."""
        allowed, reason = is_path_allowed("id_rsa")
        assert allowed is False

    def test_blocks_id_rsa_in_path(self):
        """id_rsa in a path should be blocked."""
        allowed, reason = is_path_allowed("/backup/id_rsa")
        assert allowed is False

    def test_blocks_id_ed25519(self):
        """id_ed25519 should be blocked."""
        allowed, reason = is_path_allowed("id_ed25519")
        assert allowed is False


class TestPathTraversalAttempts:
    """Test that path traversal attempts are blocked."""

    def test_blocks_traversal_to_etc_passwd(self):
        """/var/log/../../etc/passwd should be blocked."""
        # Use an absolute path with traversal to ensure we land at /etc/passwd
        allowed, reason = is_path_allowed("/var/log/../../etc/passwd")
        assert allowed is False

    def test_blocks_traversal_to_ssh(self):
        """Path traversal to .ssh should be blocked."""
        # This test uses the actual home directory
        home = os.path.expanduser("~")
        # Create a path that traverses from a subdirectory
        traversal_path = f"{home}/projects/../../.ssh/id_rsa"
        allowed, reason = is_path_allowed(traversal_path)
        assert allowed is False

    def test_blocks_traversal_to_env(self):
        """Path traversal to .env should be blocked."""
        allowed, reason = is_path_allowed("../../../.env")
        assert allowed is False

    def test_blocks_multiple_traversal(self):
        """Multiple levels of traversal should still be blocked."""
        allowed, reason = is_path_allowed("../../../../../../../../etc/shadow")
        assert allowed is False

    def test_blocks_traversal_with_absolute_path(self):
        """Absolute path with traversal should be blocked."""
        allowed, reason = is_path_allowed("/var/log/../../etc/passwd")
        assert allowed is False


class TestShellConfigFilesWriteOnly:
    """Test that shell config files are blocked for write but allowed for read."""

    def test_blocks_bashrc_write(self):
        """~/.bashrc should be blocked for write."""
        allowed, reason = is_path_allowed("~/.bashrc", for_write=True)
        assert allowed is False
        assert "shell config" in reason.lower()

    def test_allows_bashrc_read(self):
        """~/.bashrc should be allowed for read."""
        allowed, reason = is_path_allowed("~/.bashrc", for_write=False)
        assert allowed is True

    def test_blocks_zshrc_write(self):
        """~/.zshrc should be blocked for write."""
        allowed, reason = is_path_allowed("~/.zshrc", for_write=True)
        assert allowed is False

    def test_allows_zshrc_read(self):
        """~/.zshrc should be allowed for read."""
        allowed, reason = is_path_allowed("~/.zshrc", for_write=False)
        assert allowed is True

    def test_blocks_profile_write(self):
        """~/.profile should be blocked for write."""
        allowed, reason = is_path_allowed("~/.profile", for_write=True)
        assert allowed is False

    def test_blocks_bash_profile_write(self):
        """~/.bash_profile should be blocked for write."""
        allowed, reason = is_path_allowed("~/.bash_profile", for_write=True)
        assert allowed is False

    def test_blocks_zprofile_write(self):
        """~/.zprofile should be blocked for write."""
        allowed, reason = is_path_allowed("~/.zprofile", for_write=True)
        assert allowed is False


class TestFileReadIntegration:
    """Test file_read tool integration with path restrictions."""

    def test_file_read_allows_regular_file(self):
        """file_read should work with regular files."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = file_read.execute(path=temp_path)
            assert result.success is True
            assert result.output == "test content"
        finally:
            os.unlink(temp_path)

    def test_file_read_blocks_env_file(self):
        """file_read should block .env files."""
        result = file_read.execute(path="/tmp/.env")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted pattern" in result.error.lower()

    def test_file_read_blocks_ssh_directory(self):
        """file_read should block ~/.ssh files."""
        result = file_read.execute(path="~/.ssh/id_rsa")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower() or "denied" in result.error.lower()

    def test_file_read_blocks_etc_passwd(self):
        """file_read should block /etc/passwd."""
        result = file_read.execute(path="/etc/passwd")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower() or "denied" in result.error.lower()


class TestFileWriteIntegration:
    """Test file_write tool integration with path restrictions."""

    def test_file_write_allows_regular_file(self):
        """file_write should work with regular files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "test_file.txt")
            result = file_write.execute(path=test_path, content="test content")
            assert result.success is True
            assert "Successfully wrote" in result.output

            # Verify file was written
            with open(test_path, "r") as f:
                assert f.read() == "test content"

    def test_file_write_blocks_env_file(self):
        """file_write should block .env files."""
        result = file_write.execute(path="/tmp/.env", content="SECRET=value")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted pattern" in result.error.lower()

    def test_file_write_blocks_credentials_json(self):
        """file_write should block credentials.json."""
        result = file_write.execute(path="/tmp/credentials.json", content="{}")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted pattern" in result.error.lower()

    def test_file_write_blocks_ssh_directory(self):
        """file_write should block ~/.ssh files."""
        result = file_write.execute(path="~/.ssh/authorized_keys", content="ssh-rsa ...")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower() or "denied" in result.error.lower()

    def test_file_write_blocks_bashrc(self):
        """file_write should block ~/.bashrc."""
        result = file_write.execute(path="~/.bashrc", content="malicious command")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "shell config" in result.error.lower()

    def test_file_write_blocks_zshrc(self):
        """file_write should block ~/.zshrc."""
        result = file_write.execute(path="~/.zshrc", content="malicious command")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "shell config" in result.error.lower()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_case_insensitive_env_pattern(self):
        """Pattern matching should be case insensitive."""
        allowed, reason = is_path_allowed(".ENV")
        assert allowed is False

    def test_case_insensitive_credentials(self):
        """credentials.json should be case insensitive."""
        allowed, reason = is_path_allowed("CREDENTIALS.JSON")
        assert allowed is False

    def test_allows_env_in_middle_of_filename(self):
        """Files with .env in the middle should be allowed."""
        allowed, reason = is_path_allowed("my.env.backup.txt")
        assert allowed is True, f"Should allow .env in middle: {reason}"

    def test_allows_similar_but_different_filename(self):
        """Files similar to restricted patterns should be allowed."""
        allowed, reason = is_path_allowed("environment.json")
        assert allowed is True, f"environment.json should be allowed: {reason}"

    def test_allows_credentials_txt(self):
        """credentials.txt should be allowed (not .json)."""
        allowed, reason = is_path_allowed("credentials.txt")
        assert allowed is True, f"credentials.txt should be allowed: {reason}"

    def test_empty_path(self):
        """Empty path should be handled gracefully."""
        allowed, reason = is_path_allowed("")
        # Should either fail validation or allow (empty path would fail on actual read/write)
        # The important thing is it doesn't crash
        assert isinstance(allowed, bool)

    def test_path_with_spaces(self):
        """Paths with spaces should work correctly."""
        allowed, reason = is_path_allowed("/path/to/my file.txt")
        assert allowed is True, f"Path with spaces should be allowed: {reason}"

    def test_normalized_path_detection(self):
        """Paths should be normalized before checking."""
        home = os.path.expanduser("~")
        # Use double slashes which should be normalized
        allowed, reason = is_path_allowed(f"{home}//.ssh//id_rsa")
        assert allowed is False
