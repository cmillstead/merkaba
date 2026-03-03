# tests/test_search_tools.py
"""Security tests for grep/glob search tool path access control."""
import os
import tempfile
import pytest
from merkaba.tools.builtin.search import (
    DENIED_SEARCH_PATHS,
    _is_search_path_allowed,
    grep,
    glob,
)


class TestIsSearchPathAllowed:
    """Unit tests for the _is_search_path_allowed helper function."""

    def test_allows_current_directory(self):
        """The current working directory should be allowed."""
        allowed, reason = _is_search_path_allowed(".")
        assert allowed is True
        assert reason == ""

    def test_allows_merkaba_project_directory(self):
        """The merkaba project source directory should be allowed."""
        allowed, reason = _is_search_path_allowed("/Users/cevin/src/merkaba")
        assert allowed is True
        assert reason == ""

    def test_allows_tmp_directory(self):
        """/tmp should be allowed."""
        allowed, reason = _is_search_path_allowed("/tmp")
        assert allowed is True

    def test_allows_home_subdirectory(self):
        """Regular home subdirectory (not restricted) should be allowed."""
        allowed, reason = _is_search_path_allowed(os.path.expanduser("~/Documents"))
        assert allowed is True

    def test_blocks_ssh_directory(self):
        """~/.ssh should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.ssh")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_ssh_key_file(self):
        """A file inside ~/.ssh should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.ssh/id_rsa")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_ssh_config_file(self):
        """~/.ssh/config should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.ssh/config")
        assert allowed is False

    def test_blocks_aws_directory(self):
        """~/.aws should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.aws")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_aws_credentials(self):
        """~/.aws/credentials should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.aws/credentials")
        assert allowed is False

    def test_blocks_aws_config(self):
        """~/.aws/config should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.aws/config")
        assert allowed is False

    def test_blocks_gnupg_directory(self):
        """~/.gnupg should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.gnupg")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_gnupg_subpath(self):
        """Files inside ~/.gnupg should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.gnupg/private-keys-v1.d")
        assert allowed is False

    def test_blocks_gcloud_directory(self):
        """~/.config/gcloud should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.config/gcloud")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_gcloud_subpath(self):
        """Files inside ~/.config/gcloud should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.config/gcloud/credentials.db")
        assert allowed is False

    def test_blocks_kube_directory(self):
        """~/.kube should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.kube")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_kube_config(self):
        """~/.kube/config should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.kube/config")
        assert allowed is False

    def test_blocks_azure_directory(self):
        """~/.azure should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.azure")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_azure_subpath(self):
        """Files inside ~/.azure should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.azure/credentials")
        assert allowed is False

    def test_blocks_merkaba_config_json(self):
        """~/.merkaba/config.json should be blocked."""
        allowed, reason = _is_search_path_allowed("~/.merkaba/config.json")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_etc_shadow(self):
        """/etc/shadow should be blocked."""
        allowed, reason = _is_search_path_allowed("/etc/shadow")
        assert allowed is False
        assert "restricted" in reason.lower()

    def test_blocks_path_traversal_to_ssh(self):
        """Path traversal to ~/.ssh should be blocked when the intermediate dir exists."""
        home = os.path.expanduser("~")
        # Use an existing subdirectory so realpath resolves the traversal correctly.
        # ~/src exists in this repo's environment; the traversal lands at ~/.ssh.
        traversal = f"{home}/src/../.ssh/id_rsa"
        resolved = os.path.realpath(os.path.expanduser(traversal))
        ssh_resolved = os.path.realpath(os.path.expanduser("~/.ssh"))
        if not resolved.startswith(ssh_resolved):
            # If ~/src doesn't exist, realpath can't resolve the traversal correctly;
            # skip rather than give a false failure.
            pytest.skip("~/src does not exist; traversal test skipped")
        allowed, reason = _is_search_path_allowed(traversal)
        assert allowed is False

    def test_allows_expanded_path_with_no_match(self):
        """An absolute path outside all denied paths should be allowed."""
        allowed, reason = _is_search_path_allowed("/usr/local/lib")
        assert allowed is True

    def test_denied_search_paths_list_is_populated(self):
        """DENIED_SEARCH_PATHS should contain expected entries."""
        home = os.path.expanduser("~")
        assert os.path.join(home, ".ssh") in DENIED_SEARCH_PATHS
        assert os.path.join(home, ".aws") in DENIED_SEARCH_PATHS
        assert os.path.join(home, ".gnupg") in DENIED_SEARCH_PATHS
        assert "/etc/shadow" in DENIED_SEARCH_PATHS


class TestGrepPathAccessControl:
    """Integration tests for path access control in the grep tool."""

    def test_grep_blocks_ssh_directory(self):
        """grep should not be allowed to search ~/.ssh."""
        result = grep.execute(pattern="Host", path="~/.ssh")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_grep_blocks_aws_directory(self):
        """grep should not be allowed to search ~/.aws."""
        result = grep.execute(pattern="aws_access_key", path="~/.aws")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_grep_blocks_gnupg_directory(self):
        """grep should not be allowed to search ~/.gnupg."""
        result = grep.execute(pattern="key", path="~/.gnupg")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_grep_blocks_etc_shadow(self):
        """grep should not be allowed to search /etc/shadow."""
        result = grep.execute(pattern="root", path="/etc/shadow")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_grep_blocks_kube_directory(self):
        """grep should not be allowed to search ~/.kube."""
        result = grep.execute(pattern="apiVersion", path="~/.kube")
        assert result.success is False
        assert "PermissionError" in result.error

    def test_grep_blocks_azure_directory(self):
        """grep should not be allowed to search ~/.azure."""
        result = grep.execute(pattern="token", path="~/.azure")
        assert result.success is False
        assert "PermissionError" in result.error

    def test_grep_allows_project_directory(self):
        """grep should be allowed to search the project directory."""
        result = grep.execute(
            pattern="def _grep",
            path="/Users/cevin/src/merkaba/src/merkaba/tools/builtin/search.py",
        )
        assert result.success is True

    def test_grep_allows_tmp_file(self):
        """grep should be allowed to search a file in /tmp."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmp:
            tmp.write("hello world\nfoo bar\n")
            tmp_path = tmp.name

        try:
            result = grep.execute(pattern="hello", path=tmp_path)
            assert result.success is True
            assert "hello world" in result.output
        finally:
            os.unlink(tmp_path)

    def test_grep_allows_cwd(self):
        """grep called on the current directory should not be blocked by path control."""
        # We just want to confirm it isn't blocked — it may raise FileNotFoundError
        # for "." if tests run outside of a file-containing dir, but not PermissionError.
        result = grep.execute(pattern="DENIED_SEARCH_PATHS", path=".")
        # success depends on cwd, but if it fails it must NOT be a PermissionError
        if not result.success:
            assert "PermissionError" not in (result.error or "")


class TestGlobPathAccessControl:
    """Integration tests for path access control in the glob tool."""

    def test_glob_blocks_ssh_directory(self):
        """glob should not be allowed to search ~/.ssh."""
        result = glob.execute(pattern="*", path="~/.ssh")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_glob_blocks_aws_directory(self):
        """glob should not be allowed to search ~/.aws."""
        result = glob.execute(pattern="**/*", path="~/.aws")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_glob_blocks_gnupg_directory(self):
        """glob should not be allowed to search ~/.gnupg."""
        result = glob.execute(pattern="*.key", path="~/.gnupg")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_glob_blocks_etc_shadow(self):
        """glob should not be allowed to search /etc/shadow (treated as a path)."""
        result = glob.execute(pattern="*", path="/etc/shadow")
        assert result.success is False
        assert "PermissionError" in result.error
        assert "restricted" in result.error.lower()

    def test_glob_blocks_kube_directory(self):
        """glob should not be allowed to search ~/.kube."""
        result = glob.execute(pattern="*", path="~/.kube")
        assert result.success is False
        assert "PermissionError" in result.error

    def test_glob_blocks_azure_directory(self):
        """glob should not be allowed to search ~/.azure."""
        result = glob.execute(pattern="**/*", path="~/.azure")
        assert result.success is False
        assert "PermissionError" in result.error

    def test_glob_allows_project_directory(self):
        """glob should be allowed to search the project source directory."""
        result = glob.execute(
            pattern="*.py",
            path="/Users/cevin/src/merkaba/src/merkaba/tools/builtin",
        )
        assert result.success is True
        assert "search.py" in result.output

    def test_glob_allows_tmp_directory(self):
        """glob should be allowed to search /tmp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file so glob returns results
            open(os.path.join(tmpdir, "test.txt"), "w").close()
            result = glob.execute(pattern="*.txt", path=tmpdir)
            assert result.success is True

    def test_glob_allows_no_path_equivalent(self):
        """glob called on a normal non-restricted directory should pass access control."""
        allowed, reason = _is_search_path_allowed("/usr/local")
        assert allowed is True
        assert reason == ""
