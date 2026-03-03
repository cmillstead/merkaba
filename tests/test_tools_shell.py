# tests/test_tools_shell.py
import inspect
import subprocess
from unittest.mock import patch

import pytest
from merkaba.tools.builtin.shell import (
    bash,
    is_blocked,
    is_allowed,
    _bash,
    COMMAND_TIMEOUT_SECONDS,
)


class TestBashBlocklist:
    def test_blocks_rm_rf_root(self):
        """Should block rm -rf /"""
        assert is_blocked("rm -rf /")
        assert is_blocked("rm  -rf  /")

    def test_blocks_sudo(self):
        """Should block sudo commands."""
        assert is_blocked("sudo apt install")
        assert is_blocked("sudo rm file")

    def test_allows_safe_commands(self):
        """Should allow normal commands."""
        assert not is_blocked("ls -la")
        assert not is_blocked("git status")
        assert not is_blocked("echo hello")


class TestBashTool:
    def test_executes_command(self):
        """bash should execute safe commands."""
        result = bash.execute(command="echo hello")
        assert result.success
        assert "hello" in result.output

    def test_blocks_dangerous_command(self):
        """bash should refuse dangerous commands."""
        result = bash.execute(command="sudo rm -rf /")
        assert not result.success
        assert "blocked" in result.error.lower() or "not allowed" in result.error.lower()

    def test_captures_stderr(self):
        """bash should capture stderr."""
        result = bash.execute(command="ls /nonexistent 2>&1 || true")
        assert result.success


class TestShellInjectionBlocking:
    """Tests for dangerous shell construct detection."""

    def test_backtick_substitution_blocked(self):
        """Backtick command substitution should be blocked."""
        allowed, reason = is_allowed("echo `whoami`")
        assert not allowed
        assert "backtick" in reason.lower()

    def test_dollar_paren_substitution_blocked(self):
        """$() command substitution should be blocked."""
        allowed, reason = is_allowed("echo $(cat /etc/passwd)")
        assert not allowed
        assert "command substitution" in reason.lower()

    def test_pipe_blocked(self):
        """Single pipe should be blocked."""
        allowed, reason = is_allowed("ls | cat")
        assert not allowed
        assert "pipe" in reason.lower()

    def test_logical_or_allowed(self):
        """Logical OR (||) should NOT be blocked."""
        allowed, reason = is_allowed("ls || true")
        assert allowed

    def test_empty_command_blocked(self):
        """Empty command should be blocked."""
        allowed, reason = is_allowed("")
        assert not allowed
        assert "empty" in reason.lower()

    def test_whitespace_only_command_blocked(self):
        """Whitespace-only command should be blocked."""
        allowed, reason = is_allowed("   ")
        assert not allowed
        assert "empty" in reason.lower()


class TestSubcommandAllowlist:
    """Tests for subcommand-level validation."""

    def test_git_rebase_blocked(self):
        """git rebase is not in the git subcommand allowlist."""
        allowed, reason = is_allowed("git rebase main")
        assert not allowed
        assert "rebase" in reason.lower()

    def test_git_status_allowed(self):
        """git status is in the git subcommand allowlist."""
        allowed, reason = is_allowed("git status")
        assert allowed

    def test_git_diff_allowed(self):
        """git diff is in the git subcommand allowlist."""
        allowed, reason = is_allowed("git diff HEAD~1")
        assert allowed

    def test_git_bare_allowed(self):
        """git without a subcommand should be allowed (shows help)."""
        allowed, reason = is_allowed("git")
        assert allowed


class TestForbiddenPatterns:
    """Tests for sensitive file access blocking."""

    def test_ssh_key_blocked(self):
        """Accessing ~/.ssh/id_rsa should be blocked."""
        allowed, reason = is_allowed("cat ~/.ssh/id_rsa")
        assert not allowed
        assert "sensitive" in reason.lower() or "forbidden" in reason.lower()

    def test_dotenv_blocked(self):
        """Accessing .env files should be blocked."""
        allowed, reason = is_allowed("cat .env")
        assert not allowed
        assert "forbidden" in reason.lower() or "sensitive" in reason.lower()

    def test_etc_passwd_blocked(self):
        """Accessing /etc/passwd should be blocked."""
        allowed, reason = is_allowed("cat /etc/passwd")
        assert not allowed


class TestTimeoutHandling:
    """Tests for shell command timeout behavior."""

    def test_timeout_returns_error_message(self):
        """When subprocess.run raises TimeoutExpired, _bash returns error string."""
        with patch("merkaba.tools.builtin.shell.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="sleep 999", timeout=COMMAND_TIMEOUT_SECONDS
            )
            result = _bash("echo hello")
            assert "timed out" in result.lower()
            assert str(COMMAND_TIMEOUT_SECONDS) in result


class TestFullPathCommands:
    """Tests for commands specified with absolute paths."""

    def test_full_path_python_blocked(self):
        """python removed from allowlist to prevent upload-to-execute RCE."""
        allowed, reason = is_allowed("/usr/bin/python script.py")
        assert not allowed

    def test_full_path_unknown_blocked(self):
        """Full path to a command not in the allowlist should be blocked."""
        allowed, reason = is_allowed("/usr/bin/curl http://example.com")
        assert not allowed
        assert "not in allowlist" in reason.lower()


class TestShellFalse:
    """Verify _bash() invokes subprocess without shell=True."""

    def test_shell_no_shell_true_simple_command(self):
        """subprocess.run must be called with shell=False for simple commands.

        The allowlist blocks pipes, redirects, and command-substitution, so
        every command reaching _bash() is a plain executable + args that can
        be exec'd directly via shlex.split() without invoking a shell interpreter.
        """
        captured_calls = []

        original_run = subprocess.run

        def tracking_run(args, **kwargs):
            captured_calls.append({"args": args, "kwargs": kwargs})
            # Actually run the command so the function behaves correctly
            return original_run(args, **kwargs)

        with patch("merkaba.tools.builtin.shell.subprocess.run", side_effect=tracking_run):
            _bash("echo hello")

        assert len(captured_calls) == 1, "subprocess.run should have been called once"
        call = captured_calls[0]
        assert call["kwargs"].get("shell") is False, (
            "shell=False is required to prevent shell injection; "
            f"got shell={call['kwargs'].get('shell')!r}"
        )
        # args must be a list, not the raw string
        assert isinstance(call["args"], list), (
            "subprocess.run must receive a list (from shlex.split), not a raw string"
        )

    def test_shell_false_source_code_check(self):
        """The _bash source must not contain shell=True.

        This is a belt-and-suspenders check: even if the runtime mock above
        passes, the literal string 'shell=True' must not appear in the
        implementation so that future refactors cannot silently reintroduce it.
        """
        import merkaba.tools.builtin.shell as shell_module

        source = inspect.getsource(shell_module._bash)
        assert "shell=True" not in source, (
            "_bash() must not use shell=True. Use shell=False with shlex.split()."
        )
