# tests/test_shell_tool.py
"""Tests for H2/H3 shell tool security fixes:
- env removed from ALLOWED_COMMANDS (H3)
- find -exec and related flags blocked (H2)
- cp/mv restricted from sensitive paths (H2)
"""
import os

import pytest
from merkaba.tools.builtin.shell import ALLOWED_COMMANDS, is_allowed


class TestEnvRemovedFromAllowlist:
    """H3: env command must not be in ALLOWED_COMMANDS."""

    def test_env_not_in_allowed_commands(self):
        """env must be removed from ALLOWED_COMMANDS to prevent allowlist bypass."""
        assert "env" not in ALLOWED_COMMANDS, (
            "env is a generic program launcher that defeats the entire allowlist"
        )

    def test_env_command_is_blocked(self):
        """Running 'env' bare should be blocked."""
        allowed, reason = is_allowed("env")
        assert allowed is False

    def test_env_as_launcher_is_blocked(self):
        """env used to launch another program should be blocked."""
        allowed, reason = is_allowed("env python3 -c 'print(1)'")
        assert allowed is False

    def test_env_with_var_assignment_is_blocked(self):
        """env VAR=value cmd bypass should be blocked."""
        allowed, reason = is_allowed("env HOME=/tmp cat /etc/passwd")
        assert allowed is False


class TestFindDangerousFlags:
    """H2: find -exec and related flags bypass pipe detection."""

    def test_find_exec_is_blocked(self):
        """find -exec should be blocked (classic exec bypass).

        The command may be rejected either because the .env pattern matches first
        or because the -exec flag check fires — either way, it must be blocked.
        """
        allowed, reason = is_allowed(r"find / -name '*.env' -exec cat {} \;")
        assert allowed is False

    def test_find_exec_without_env_pattern_is_blocked(self):
        """find -exec blocked even when there is no .env pattern to catch it early."""
        allowed, reason = is_allowed("find /tmp -name '*.log' -exec cat {} \\;")
        assert allowed is False
        assert (
            "find" in reason.lower()
            or "dangerous" in reason.lower()
            or "exec" in reason.lower()
        )

    def test_find_exec_plus_is_blocked(self):
        """find -exec with + terminator should also be blocked."""
        allowed, reason = is_allowed("find . -name '*.py' -exec rm {} +")
        assert allowed is False

    def test_find_execdir_is_blocked(self):
        """find -execdir should be blocked."""
        allowed, reason = is_allowed("find /tmp -execdir sh -c 'id' \\;")
        assert allowed is False

    def test_find_ok_is_blocked(self):
        """find -ok (interactive exec) should be blocked."""
        allowed, reason = is_allowed("find . -name '*.conf' -ok cat {} \\;")
        assert allowed is False

    def test_find_okdir_is_blocked(self):
        """find -okdir should be blocked."""
        allowed, reason = is_allowed("find . -okdir cat {} \\;")
        assert allowed is False

    def test_find_delete_is_blocked(self):
        """find -delete should be blocked (mass deletion risk)."""
        allowed, reason = is_allowed("find /tmp -name '*.tmp' -delete")
        assert allowed is False

    def test_find_safe_name_filter_is_allowed(self):
        """find . -name '*.py' (no dangerous flags) should still be allowed."""
        allowed, reason = is_allowed("find . -name '*.py'")
        assert allowed is True, f"safe find should be allowed: {reason}"

    def test_find_safe_type_filter_is_allowed(self):
        """find . -type f -name '*.txt' should still be allowed."""
        allowed, reason = is_allowed("find . -type f -name '*.txt'")
        assert allowed is True, f"safe find with -type should be allowed: {reason}"

    def test_find_safe_maxdepth_is_allowed(self):
        """find . -maxdepth 2 should still be allowed."""
        allowed, reason = is_allowed("find . -maxdepth 2")
        assert allowed is True, f"find with -maxdepth should be allowed: {reason}"

    def test_find_safe_mtime_is_allowed(self):
        """find . -mtime -7 should still be allowed."""
        allowed, reason = is_allowed("find . -mtime -7")
        assert allowed is True, f"find with -mtime should be allowed: {reason}"


class TestCpMvPathRestrictions:
    """H2: cp/mv must not be allowed to touch sensitive data directories."""

    def test_cp_from_merkaba_config_is_blocked(self):
        """Copying out of ~/.merkaba should be blocked."""
        allowed, reason = is_allowed("cp ~/.merkaba/config.json /tmp/stolen")
        assert allowed is False
        assert (
            "forbidden" in reason.lower()
            or "path" in reason.lower()
            or "restricted" in reason.lower()
        )

    def test_mv_merkaba_db_is_blocked(self):
        """Moving ~/.merkaba/memory.db out should be blocked."""
        allowed, reason = is_allowed("mv ~/.merkaba/memory.db /tmp/")
        assert allowed is False

    def test_cp_to_merkaba_is_blocked(self):
        """Copying a file into ~/.merkaba should be blocked."""
        allowed, reason = is_allowed("cp /tmp/payload ~/.merkaba/config.json")
        assert allowed is False

    def test_mv_to_merkaba_is_blocked(self):
        """Moving a file into ~/.merkaba should be blocked."""
        allowed, reason = is_allowed("mv /tmp/malicious ~/.merkaba/plugin.py")
        assert allowed is False

    def test_cp_from_ssh_is_blocked(self):
        """Copying SSH keys out should be blocked."""
        allowed, reason = is_allowed("cp ~/.ssh/id_rsa /tmp/stolen_key")
        assert allowed is False

    def test_cp_from_aws_is_blocked(self):
        """Copying AWS credentials out should be blocked."""
        allowed, reason = is_allowed("cp ~/.aws/credentials /tmp/stolen_creds")
        assert allowed is False

    def test_cp_from_gnupg_is_blocked(self):
        """Copying GPG keys out should be blocked."""
        allowed, reason = is_allowed("cp ~/.gnupg/secring.gpg /tmp/stolen")
        assert allowed is False

    def test_cp_safe_paths_is_allowed(self):
        """cp between safe paths should still be allowed."""
        allowed, reason = is_allowed("cp README.md /tmp/backup.md")
        assert allowed is True, f"safe cp should be allowed: {reason}"

    def test_mv_safe_paths_is_allowed(self):
        """mv between safe paths should still be allowed."""
        allowed, reason = is_allowed("mv /tmp/old.txt /tmp/new.txt")
        assert allowed is True, f"safe mv should be allowed: {reason}"

    def test_cp_relative_paths_is_allowed(self):
        """cp with safe relative paths should be allowed."""
        allowed, reason = is_allowed("cp src/foo.py tests/foo_copy.py")
        assert allowed is True, f"cp with relative paths should be allowed: {reason}"

    def test_mv_relative_paths_is_allowed(self):
        """mv with safe relative paths should be allowed."""
        allowed, reason = is_allowed("mv output/report.txt archive/report.txt")
        assert allowed is True, f"mv with relative paths should be allowed: {reason}"

    def test_cp_expanded_merkaba_path_is_blocked(self):
        """cp using the expanded absolute ~/.merkaba path should be blocked."""
        merkaba_path = os.path.expanduser("~/.merkaba")
        allowed, reason = is_allowed(f"cp {merkaba_path}/config.json /tmp/")
        assert allowed is False
