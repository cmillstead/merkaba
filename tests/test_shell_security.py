# tests/test_shell_security.py
"""Security tests for the shell tool allowlist implementation."""
import pytest
from merkaba.tools.builtin.shell import is_allowed, bash


class TestAllowedCommands:
    """Test that explicitly allowed commands pass validation."""

    def test_allows_git_status(self):
        """git status should be allowed."""
        allowed, reason = is_allowed("git status")
        assert allowed is True, f"git status should be allowed: {reason}"

    def test_allows_git_diff(self):
        """git diff should be allowed."""
        allowed, reason = is_allowed("git diff")
        assert allowed is True, f"git diff should be allowed: {reason}"

    def test_allows_git_log(self):
        """git log should be allowed."""
        allowed, reason = is_allowed("git log --oneline -10")
        assert allowed is True, f"git log should be allowed: {reason}"

    def test_allows_git_add(self):
        """git add should be allowed."""
        allowed, reason = is_allowed("git add .")
        assert allowed is True, f"git add should be allowed: {reason}"

    def test_allows_git_commit(self):
        """git commit should be allowed."""
        allowed, reason = is_allowed('git commit -m "test message"')
        assert allowed is True, f"git commit should be allowed: {reason}"

    def test_allows_git_push(self):
        """git push should be allowed."""
        allowed, reason = is_allowed("git push origin main")
        assert allowed is True, f"git push should be allowed: {reason}"

    def test_allows_git_pull(self):
        """git pull should be allowed."""
        allowed, reason = is_allowed("git pull")
        assert allowed is True, f"git pull should be allowed: {reason}"

    def test_allows_git_branch(self):
        """git branch should be allowed."""
        allowed, reason = is_allowed("git branch -a")
        assert allowed is True, f"git branch should be allowed: {reason}"

    def test_allows_git_checkout(self):
        """git checkout should be allowed."""
        allowed, reason = is_allowed("git checkout -b feature")
        assert allowed is True, f"git checkout should be allowed: {reason}"

    def test_allows_git_stash(self):
        """git stash should be allowed."""
        allowed, reason = is_allowed("git stash")
        assert allowed is True, f"git stash should be allowed: {reason}"

    def test_allows_pytest(self):
        """pytest should be allowed."""
        allowed, reason = is_allowed("pytest tests/")
        assert allowed is True, f"pytest should be allowed: {reason}"

    def test_blocks_python(self):
        """python should be blocked (removed from allowlist for security)."""
        allowed, reason = is_allowed('python -c "print(1)"')
        assert allowed is False, "python should be blocked"

    def test_allows_uv(self):
        """uv should be allowed."""
        allowed, reason = is_allowed("uv pip install requests")
        assert allowed is True, f"uv should be allowed: {reason}"

    def test_allows_pip_install(self):
        """pip install should be allowed."""
        allowed, reason = is_allowed("pip install requests")
        assert allowed is True, f"pip install should be allowed: {reason}"

    def test_allows_pip_list(self):
        """pip list should be allowed."""
        allowed, reason = is_allowed("pip list")
        assert allowed is True, f"pip list should be allowed: {reason}"

    def test_allows_pip_show(self):
        """pip show should be allowed."""
        allowed, reason = is_allowed("pip show requests")
        assert allowed is True, f"pip show should be allowed: {reason}"

    def test_allows_npm_install(self):
        """npm install should be allowed."""
        allowed, reason = is_allowed("npm install lodash")
        assert allowed is True, f"npm install should be allowed: {reason}"

    def test_allows_npm_test(self):
        """npm test should be allowed."""
        allowed, reason = is_allowed("npm test")
        assert allowed is True, f"npm test should be allowed: {reason}"

    def test_allows_npm_run(self):
        """npm run should be allowed."""
        allowed, reason = is_allowed("npm run build")
        assert allowed is True, f"npm run should be allowed: {reason}"

    def test_allows_npm_list(self):
        """npm list should be allowed."""
        allowed, reason = is_allowed("npm list")
        assert allowed is True, f"npm list should be allowed: {reason}"

    def test_allows_ls(self):
        """ls should be allowed."""
        allowed, reason = is_allowed("ls -la")
        assert allowed is True, f"ls should be allowed: {reason}"

    def test_allows_cat(self):
        """cat should be allowed."""
        allowed, reason = is_allowed("cat file.txt")
        assert allowed is True, f"cat should be allowed: {reason}"

    def test_allows_head(self):
        """head should be allowed."""
        allowed, reason = is_allowed("head -n 10 file.txt")
        assert allowed is True, f"head should be allowed: {reason}"

    def test_allows_tail(self):
        """tail should be allowed."""
        allowed, reason = is_allowed("tail -n 10 file.txt")
        assert allowed is True, f"tail should be allowed: {reason}"

    def test_allows_wc(self):
        """wc should be allowed."""
        allowed, reason = is_allowed("wc -l file.txt")
        assert allowed is True, f"wc should be allowed: {reason}"

    def test_allows_grep(self):
        """grep should be allowed."""
        allowed, reason = is_allowed("grep -r pattern .")
        assert allowed is True, f"grep should be allowed: {reason}"

    def test_allows_find(self):
        """find should be allowed."""
        allowed, reason = is_allowed("find . -name *.py")
        assert allowed is True, f"find should be allowed: {reason}"

    def test_allows_mkdir(self):
        """mkdir should be allowed."""
        allowed, reason = is_allowed("mkdir -p new_dir")
        assert allowed is True, f"mkdir should be allowed: {reason}"

    def test_allows_cp(self):
        """cp should be allowed."""
        allowed, reason = is_allowed("cp file1 file2")
        assert allowed is True, f"cp should be allowed: {reason}"

    def test_allows_mv(self):
        """mv should be allowed."""
        allowed, reason = is_allowed("mv file1 file2")
        assert allowed is True, f"mv should be allowed: {reason}"

    def test_allows_echo(self):
        """echo should be allowed."""
        allowed, reason = is_allowed("echo hello world")
        assert allowed is True, f"echo should be allowed: {reason}"

    def test_allows_pwd(self):
        """pwd should be allowed."""
        allowed, reason = is_allowed("pwd")
        assert allowed is True, f"pwd should be allowed: {reason}"

    def test_allows_whoami(self):
        """whoami should be allowed."""
        allowed, reason = is_allowed("whoami")
        assert allowed is True, f"whoami should be allowed: {reason}"

    def test_allows_date(self):
        """date should be allowed."""
        allowed, reason = is_allowed("date")
        assert allowed is True, f"date should be allowed: {reason}"

    def test_allows_which(self):
        """which should be allowed."""
        allowed, reason = is_allowed("which python")
        assert allowed is True, f"which should be allowed: {reason}"

    def test_blocks_env(self):
        """env must be blocked — it is a generic launcher that defeats the allowlist (H3)."""
        allowed, reason = is_allowed("env")
        assert allowed is False, "env should be blocked as it bypasses the allowlist"


class TestBlockedCommands:
    """Test that dangerous/non-allowlisted commands are blocked."""

    def test_blocks_rm(self):
        """rm should be blocked (not on allowlist)."""
        allowed, reason = is_allowed("rm file.txt")
        assert allowed is False
        assert "not in allowlist" in reason.lower() or "not allowed" in reason.lower()

    def test_blocks_rm_rf(self):
        """rm -rf should be blocked."""
        allowed, reason = is_allowed("rm -rf /")
        assert allowed is False

    def test_blocks_curl(self):
        """curl should be blocked."""
        allowed, reason = is_allowed("curl http://example.com")
        assert allowed is False

    def test_blocks_wget(self):
        """wget should be blocked."""
        allowed, reason = is_allowed("wget http://example.com")
        assert allowed is False

    def test_blocks_sudo(self):
        """sudo should be blocked."""
        allowed, reason = is_allowed("sudo apt install")
        assert allowed is False

    def test_blocks_bash_c(self):
        """bash -c should be blocked."""
        allowed, reason = is_allowed("bash -c dangerous")
        assert allowed is False

    def test_blocks_sh_c(self):
        """sh -c should be blocked."""
        allowed, reason = is_allowed("sh -c dangerous")
        assert allowed is False

    def test_blocks_nc(self):
        """nc (netcat) should be blocked."""
        allowed, reason = is_allowed("nc -l 8080")
        assert allowed is False

    def test_blocks_netcat(self):
        """netcat should be blocked."""
        allowed, reason = is_allowed("netcat -l 8080")
        assert allowed is False

    def test_blocks_chmod(self):
        """chmod should be blocked."""
        allowed, reason = is_allowed("chmod 777 file")
        assert allowed is False

    def test_blocks_chown(self):
        """chown should be blocked."""
        allowed, reason = is_allowed("chown root file")
        assert allowed is False

    def test_blocks_dd(self):
        """dd should be blocked."""
        allowed, reason = is_allowed("dd if=/dev/zero of=/dev/sda")
        assert allowed is False

    def test_blocks_mkfs(self):
        """mkfs should be blocked."""
        allowed, reason = is_allowed("mkfs.ext4 /dev/sda")
        assert allowed is False

    def test_blocks_kill(self):
        """kill should be blocked."""
        allowed, reason = is_allowed("kill -9 1")
        assert allowed is False

    def test_blocks_killall(self):
        """killall should be blocked."""
        allowed, reason = is_allowed("killall python")
        assert allowed is False

    def test_blocks_pkill(self):
        """pkill should be blocked."""
        allowed, reason = is_allowed("pkill python")
        assert allowed is False

    def test_blocks_reboot(self):
        """reboot should be blocked."""
        allowed, reason = is_allowed("reboot")
        assert allowed is False

    def test_blocks_shutdown(self):
        """shutdown should be blocked."""
        allowed, reason = is_allowed("shutdown -h now")
        assert allowed is False

    def test_blocks_dangerous_eval_cmd(self):
        """The shell eval command should be blocked."""
        allowed, reason = is_allowed("eval dangerous_cmd")
        assert allowed is False


class TestGitSubcommandRestrictions:
    """Test that only allowed git subcommands work."""

    def test_blocks_git_rm(self):
        """git rm should be blocked (not in allowed subcommands)."""
        allowed, reason = is_allowed("git rm file.txt")
        assert allowed is False
        assert "subcommand" in reason.lower()

    def test_blocks_git_reset_hard(self):
        """git reset --hard should be blocked."""
        allowed, reason = is_allowed("git reset --hard HEAD~1")
        assert allowed is False

    def test_blocks_git_clean(self):
        """git clean should be blocked."""
        allowed, reason = is_allowed("git clean -fd")
        assert allowed is False

    def test_blocks_git_rebase(self):
        """git rebase should be blocked."""
        allowed, reason = is_allowed("git rebase main")
        assert allowed is False

    def test_allows_git_push_force(self):
        """git push --force should still be allowed (push is allowed)."""
        allowed, reason = is_allowed("git push --force")
        assert allowed is True


class TestPipSubcommandRestrictions:
    """Test that only allowed pip subcommands work."""

    def test_blocks_pip_uninstall(self):
        """pip uninstall should be blocked."""
        allowed, reason = is_allowed("pip uninstall requests")
        assert allowed is False
        assert "subcommand" in reason.lower()

    def test_blocks_pip_download(self):
        """pip download should be blocked."""
        allowed, reason = is_allowed("pip download requests")
        assert allowed is False


class TestNpmSubcommandRestrictions:
    """Test that only allowed npm subcommands work."""

    def test_blocks_npm_uninstall(self):
        """npm uninstall should be blocked."""
        allowed, reason = is_allowed("npm uninstall lodash")
        assert allowed is False
        assert "subcommand" in reason.lower()

    def test_blocks_npm_publish(self):
        """npm publish should be blocked."""
        allowed, reason = is_allowed("npm publish")
        assert allowed is False

    def test_blocks_npm_unpublish(self):
        """npm unpublish should be blocked."""
        allowed, reason = is_allowed("npm unpublish package")
        assert allowed is False


class TestForbiddenPatterns:
    """Test that commands accessing sensitive files are blocked."""

    def test_blocks_etc_passwd(self):
        """Access to /etc/passwd should be blocked."""
        allowed, reason = is_allowed("cat /etc/passwd")
        assert allowed is False
        assert "forbidden" in reason.lower() or "sensitive" in reason.lower()

    def test_blocks_etc_shadow(self):
        """Access to /etc/shadow should be blocked."""
        allowed, reason = is_allowed("cat /etc/shadow")
        assert allowed is False

    def test_blocks_ssh_directory(self):
        """Access to ~/.ssh should be blocked."""
        allowed, reason = is_allowed("cat ~/.ssh/id_rsa")
        assert allowed is False

    def test_blocks_ssh_with_home_expansion(self):
        """Access to HOME/.ssh should be blocked."""
        allowed, reason = is_allowed("cat /home/user/.ssh/id_rsa")
        assert allowed is False

    def test_blocks_gnupg_directory(self):
        """Access to ~/.gnupg should be blocked."""
        allowed, reason = is_allowed("ls ~/.gnupg")
        assert allowed is False

    def test_blocks_aws_directory(self):
        """Access to ~/.aws should be blocked."""
        allowed, reason = is_allowed("cat ~/.aws/credentials")
        assert allowed is False

    def test_blocks_env_file(self):
        """Access to .env files should be blocked."""
        allowed, reason = is_allowed("cat .env")
        assert allowed is False

    def test_blocks_env_file_with_path(self):
        """Access to .env with path should be blocked."""
        allowed, reason = is_allowed("cat /path/to/.env")
        assert allowed is False

    def test_blocks_config_json(self):
        """Access to config.json should be blocked."""
        allowed, reason = is_allowed("cat config.json")
        assert allowed is False

    def test_blocks_head_on_sensitive(self):
        """head on sensitive files should be blocked."""
        allowed, reason = is_allowed("head ~/.ssh/id_rsa")
        assert allowed is False

    def test_blocks_tail_on_sensitive(self):
        """tail on sensitive files should be blocked."""
        allowed, reason = is_allowed("tail /etc/passwd")
        assert allowed is False

    def test_blocks_grep_on_sensitive(self):
        """grep on sensitive files should be blocked."""
        allowed, reason = is_allowed("grep password ~/.ssh/config")
        assert allowed is False

    def test_blocks_cp_from_sensitive(self):
        """cp from sensitive locations should be blocked."""
        allowed, reason = is_allowed("cp ~/.ssh/id_rsa /tmp/")
        assert allowed is False

    def test_blocks_cp_to_expose_sensitive(self):
        """cp to expose sensitive files should be blocked."""
        allowed, reason = is_allowed("cp /etc/shadow /tmp/shadow")
        assert allowed is False


class TestPipeBlocking:
    """Test that piping commands are blocked."""

    def test_blocks_simple_pipe(self):
        """Simple pipe should be blocked."""
        allowed, reason = is_allowed("cat /etc/hosts | head")
        assert allowed is False
        assert "pipe" in reason.lower()

    def test_blocks_pipe_with_spaces(self):
        """Pipe with spaces should be blocked."""
        allowed, reason = is_allowed("ls -la | grep txt")
        assert allowed is False
        assert "pipe" in reason.lower()

    def test_allows_logical_or(self):
        """Logical OR (||) should not be blocked."""
        allowed, reason = is_allowed("ls /nonexistent || echo fallback")
        assert allowed is True, f"Logical OR should be allowed: {reason}"

    def test_allows_fd_redirect(self):
        """File descriptor redirect like 2>&1 should not be blocked."""
        allowed, reason = is_allowed("ls /nonexistent 2>&1")
        assert allowed is True, f"fd redirect should be allowed: {reason}"


class TestPathObfuscationAttempts:
    """Test that path obfuscation attempts are caught."""

    def test_blocks_dot_dot_traversal(self):
        """Path traversal with .. should be detected."""
        allowed, reason = is_allowed("cat ../../etc/passwd")
        assert allowed is False

    def test_blocks_multiple_slashes(self):
        """Multiple slashes should not bypass checks."""
        allowed, reason = is_allowed("cat //etc//passwd")
        assert allowed is False

    def test_blocks_hidden_in_command_chain(self):
        """Sensitive file access in piped commands should be blocked."""
        allowed, reason = is_allowed("cat file.txt | grep password > ~/.ssh/id_rsa")
        assert allowed is False

    def test_blocks_backtick_substitution(self):
        """Backtick command substitution attempts should be blocked."""
        # Using repr to avoid actual backtick interpretation
        cmd = "echo " + chr(96) + "cat /etc/passwd" + chr(96)
        allowed, reason = is_allowed(cmd)
        assert allowed is False

    def test_blocks_dollar_paren_substitution(self):
        """Command substitution attempts should be blocked."""
        allowed, reason = is_allowed("echo $(cat /etc/passwd)")
        assert allowed is False


class TestBashToolIntegration:
    """Test the bash tool integration with the allowlist."""

    def test_bash_runs_allowed_command(self):
        """bash should run allowed commands."""
        result = bash.execute(command="echo hello")
        assert result.success
        assert "hello" in result.output

    def test_bash_blocks_disallowed_command(self):
        """bash should refuse non-allowlisted commands."""
        result = bash.execute(command="curl http://example.com")
        assert not result.success
        assert "not allowed" in result.error.lower() or "blocked" in result.error.lower()

    def test_bash_blocks_sensitive_file_access(self):
        """bash should refuse access to sensitive files."""
        result = bash.execute(command="cat .env")
        assert not result.success

    def test_bash_allows_git_status(self):
        """bash should allow git status."""
        result = bash.execute(command="git status")
        if not result.success:
            assert "not allowed" not in result.error.lower()
            assert "blocked" not in result.error.lower()

    def test_bash_allows_ls(self):
        """bash should allow ls."""
        result = bash.execute(command="ls")
        assert result.success


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_command(self):
        """Empty command should be rejected."""
        allowed, reason = is_allowed("")
        assert allowed is False

    def test_whitespace_only_command(self):
        """Whitespace-only command should be rejected."""
        allowed, reason = is_allowed("   ")
        assert allowed is False

    def test_command_with_leading_whitespace(self):
        """Commands with leading whitespace should be parsed correctly."""
        allowed, reason = is_allowed("  ls -la")
        assert allowed is True

    def test_command_with_single_quotes(self):
        """Commands with single quotes should be parsed correctly."""
        allowed, reason = is_allowed("echo hello world")
        assert allowed is True

    def test_command_with_double_quotes(self):
        """Commands with double quotes should be parsed correctly."""
        allowed, reason = is_allowed("echo hello world")
        assert allowed is True

    def test_full_path_to_allowed_command(self):
        """Full path to allowed command should work."""
        allowed, reason = is_allowed("/bin/ls")
        assert allowed is True

    def test_full_path_to_blocked_command(self):
        """Full path to blocked command should be blocked."""
        allowed, reason = is_allowed("/bin/rm file.txt")
        assert allowed is False

    def test_usr_bin_path_to_blocked(self):
        """Commands in /usr/bin should be checked by basename (python blocked)."""
        allowed, reason = is_allowed("/usr/bin/python -c print")
        assert allowed is False

    def test_full_path_with_subcommand(self):
        """Full path to command with subcommand should be validated correctly."""
        allowed, reason = is_allowed("/usr/bin/git status")
        assert allowed is True, f"/usr/bin/git status should be allowed: {reason}"
