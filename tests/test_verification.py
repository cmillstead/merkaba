# tests/test_verification.py
"""Tests for DeterministicVerifier, agent integration, and ReviewWorker."""

import subprocess
import sys
from unittest.mock import MagicMock, patch, call

import pytest

# Mock ollama before importing anything that touches LLMClient
sys.modules.setdefault("ollama", MagicMock())

from merkaba.verification.deterministic import (
    DeterministicVerifier,
    CheckResult,
    VerificationResult,
    _build_summary,
)


# --- DeterministicVerifier ---


class TestDeterministicVerifier:
    def test_verify_python_runs_ruff(self):
        """Ruff passes — result should be passing."""
        verifier = DeterministicVerifier()
        fake_proc = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", return_value=fake_proc) as mock_run,
        ):
            result = verifier.verify("app.py")

        assert result is not None
        assert result.passed is True
        assert any(c.name == "ruff" for c in result.checks)
        # Verify subprocess was called with ruff
        calls = mock_run.call_args_list
        ruff_calls = [c for c in calls if "ruff" in c[0][0]]
        assert len(ruff_calls) >= 1

    def test_verify_python_ruff_failure(self):
        """Ruff fails — result should contain error output."""
        verifier = DeterministicVerifier()
        fake_proc = MagicMock(returncode=1, stdout="app.py:1:1: F401 unused import", stderr="")
        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", return_value=fake_proc),
        ):
            result = verifier.verify("app.py")

        assert result is not None
        assert result.passed is False
        ruff_check = next(c for c in result.checks if c.name == "ruff")
        assert "F401" in ruff_check.output
        assert "FAILED" in result.summary

    def test_verify_skips_missing_tools(self):
        """If no tools on PATH, should return None (nothing to check)."""
        verifier = DeterministicVerifier()
        with patch("shutil.which", return_value=None):
            result = verifier.verify("app.py")
        assert result is None

    def test_verify_unknown_extension(self):
        """Non-code files return None."""
        verifier = DeterministicVerifier()
        result = verifier.verify("notes.txt")
        assert result is None

    def test_verify_timeout_handled(self):
        """subprocess.TimeoutExpired is caught gracefully."""
        verifier = DeterministicVerifier(timeout=1)
        with (
            patch("shutil.which", return_value="/usr/bin/ruff"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ruff", timeout=1)),
        ):
            result = verifier.verify("app.py")

        assert result is not None
        assert result.passed is False
        assert any("Timed out" in c.output for c in result.checks)

    def test_verification_result_summary(self):
        """Summary includes failure details."""
        checks = [
            CheckResult(name="ruff", passed=True, output=""),
            CheckResult(name="mypy", passed=False, output="error: Missing return type"),
        ]
        summary = _build_summary(checks)
        assert "mypy" in summary
        assert "FAILED" in summary
        assert "Missing return type" in summary

    def test_verify_disabled(self):
        """Disabled verifier returns None."""
        verifier = DeterministicVerifier(enabled=False)
        result = verifier.verify("app.py")
        assert result is None

    def test_verify_javascript(self):
        """JS files trigger eslint check."""
        verifier = DeterministicVerifier()
        fake_proc = MagicMock(returncode=0, stdout="", stderr="")
        with (
            patch("shutil.which", return_value="/usr/bin/npx"),
            patch("subprocess.run", return_value=fake_proc) as mock_run,
        ):
            result = verifier.verify("index.js")

        assert result is not None
        assert result.passed is True
        calls = mock_run.call_args_list
        assert any("eslint" in str(c) for c in calls)


# --- Agent integration ---


class TestAgentVerification:
    @pytest.fixture
    def agent(self, tmp_path):
        from merkaba.agent import Agent
        from merkaba.tools.base import PermissionTier

        with patch("merkaba.agent.SecurityScanner") as MockScanner:
            MockScanner.return_value.quick_scan.return_value = MagicMock(has_issues=False)
            a = Agent(plugins_enabled=False, memory_storage_dir=str(tmp_path))
        a.input_classifier.enabled = False
        a.permission_manager.auto_approve_level = PermissionTier.MODERATE
        return a

    def test_file_write_triggers_verification(self, agent):
        """After file_write success, verifier.verify() is called."""
        from merkaba.llm import LLMResponse, ToolCall
        from merkaba.tools.base import ToolResult

        mock_verify = MagicMock(return_value=VerificationResult(
            passed=True, checks=[], summary="All checks passed",
        ))
        agent._verifier.verify = mock_verify

        # Mock file_write tool to return success without actually writing
        fw_tool = agent.registry.get("file_write")
        fw_tool.execute = MagicMock(return_value=ToolResult(success=True, output="Wrote 3 bytes"))

        tool_resp = LLMResponse(
            content=None, model="test",
            tool_calls=[ToolCall(name="file_write", arguments={"path": "/tmp/test.py", "content": "x=1"})],
        )
        final_resp = LLMResponse(content="Done.", model="test")
        agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, final_resp])

        agent.run("Write a file")
        mock_verify.assert_called_once_with("/tmp/test.py")

    def test_verification_failure_in_context(self, agent):
        """Verification failure text appears in tool results added to conversation."""
        from merkaba.llm import LLMResponse, ToolCall
        from merkaba.tools.base import ToolResult

        fail_result = VerificationResult(
            passed=False,
            checks=[CheckResult(name="ruff", passed=False, output="E001: syntax error")],
            summary="[ruff] FAILED:\nE001: syntax error",
        )
        agent._verifier.verify = MagicMock(return_value=fail_result)

        # Mock file_write tool to return success without actually writing
        fw_tool = agent.registry.get("file_write")
        fw_tool.execute = MagicMock(return_value=ToolResult(success=True, output="Wrote 2 bytes"))

        tool_resp = LLMResponse(
            content=None, model="test",
            tool_calls=[ToolCall(name="file_write", arguments={"path": "/tmp/bad.py", "content": "x="})],
        )
        final_resp = LLMResponse(content="Fixed it.", model="test")
        agent.llm.chat_with_retry = MagicMock(side_effect=[tool_resp, final_resp])

        agent.run("Write broken code")

        # Check the tool result in conversation contains the failure
        tool_msgs = [m for m in agent.conversation if m["role"] == "tool"]
        assert len(tool_msgs) >= 1
        assert "VERIFICATION FAILED" in tool_msgs[0]["content"]
        assert "E001" in tool_msgs[0]["content"]
