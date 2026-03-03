# tests/e2e/test_e2e_forge.py
"""E2E tests for Skill Forge CLI."""

import os
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from merkaba.cli import app

pytestmark = pytest.mark.e2e


MOCK_GITHUB_SKILL = """---
name: code-reviewer
description: Automated code review assistant
---
# Code Reviewer

Analyze code diffs and provide review comments.
"""

MOCK_LLM_OUTPUT = """---
name: code-reviewer
description: Automated code review assistant
version: 0.1.0
---
# Code Reviewer

Use file_read to examine changed files and provide structured review feedback.
"""

MOCK_CLAWHUB_HTML = """
<html>
<head><title>Test Skill - ClawHub</title></head>
<body>
<h1>Test Skill</h1>
<div class="skill-description">
<p>A test skill for demos.</p>
</div>
<div class="security-verdict">
<span class="verdict-label">Overall Assessment:</span>
<span class="verdict-value">Benign</span>
</div>
</body>
</html>
"""


@pytest.fixture
def forge_dest(tmp_path):
    """Temporary destination for forged plugins."""
    dest = tmp_path / "plugins"
    dest.mkdir()
    return dest


_PUBLIC_IP = "140.82.121.3"


@pytest.fixture
def mock_httpx_github():
    mock_resp = MagicMock()
    mock_resp.text = MOCK_GITHUB_SKILL
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.fixture
def mock_httpx_clawhub():
    mock_resp = MagicMock()
    mock_resp.text = MOCK_CLAWHUB_HTML
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


@pytest.fixture
def mock_llm():
    from merkaba.llm import LLMResponse
    mock = MagicMock()
    mock.chat_with_fallback.return_value = LLMResponse(
        content=MOCK_LLM_OUTPUT, model="test"
    )
    return mock


def _make_expanduser(tmp_home):
    """Return an expanduser replacement that redirects ~ to tmp_home."""
    _real = os.path.expanduser

    def _patched(path):
        if path.startswith("~"):
            return str(tmp_home) + path[1:]
        return _real(path)

    return _patched


class TestForgeE2E:
    def test_forge_from_github(self, tmp_path, mock_httpx_github, mock_llm):
        runner = CliRunner()
        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_httpx_github), \
             patch("merkaba.llm.LLMClient", return_value=mock_llm), \
             patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value=_PUBLIC_IP), \
             patch("os.path.expanduser", _make_expanduser(tmp_path)):
            result = runner.invoke(app, [
                "skills", "forge",
                "--from", "https://github.com/user/repo/blob/main/SKILL.md",
            ])

        assert result.exit_code == 0
        assert "forged successfully" in result.output.lower() or "Plugin forged" in result.output

    def test_forge_with_custom_name(self, tmp_path, mock_httpx_github, mock_llm):
        runner = CliRunner()
        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_httpx_github), \
             patch("merkaba.llm.LLMClient", return_value=mock_llm), \
             patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value=_PUBLIC_IP), \
             patch("os.path.expanduser", _make_expanduser(tmp_path)):
            result = runner.invoke(app, [
                "skills", "forge",
                "--from", "https://github.com/user/repo/blob/main/SKILL.md",
                "--name", "my-reviewer",
            ])

        assert result.exit_code == 0
        assert "my-reviewer" in result.output

    def test_forge_from_clawhub(self, tmp_path, mock_httpx_clawhub, mock_llm):
        runner = CliRunner()
        with patch("merkaba.plugins.forge.httpx.get", return_value=mock_httpx_clawhub), \
             patch("merkaba.llm.LLMClient", return_value=mock_llm), \
             patch("merkaba.tools.builtin.web.socket.gethostbyname", return_value=_PUBLIC_IP), \
             patch("os.path.expanduser", _make_expanduser(tmp_path)):
            result = runner.invoke(app, [
                "skills", "forge",
                "--from", "https://clawhub.ai/skills/test-skill",
            ])

        assert result.exit_code == 0

    def test_forge_invalid_url(self):
        runner = CliRunner()
        result = runner.invoke(app, [
            "skills", "forge",
            "--from", "https://example.com/not-a-skill",
        ])

        assert result.exit_code != 0
        assert "unsupported" in result.output.lower() or "error" in result.output.lower()

    def test_forge_help(self):
        runner = CliRunner()
        result = runner.invoke(app, ["skills", "forge", "--help"])

        assert result.exit_code == 0
        assert "--from" in result.output
        assert "--name" in result.output
        assert "--force" in result.output

    def test_forge_missing_url(self):
        runner = CliRunner()
        result = runner.invoke(app, ["skills", "forge"])

        assert result.exit_code != 0

    def test_forge_http_rejected(self):
        runner = CliRunner()
        result = runner.invoke(app, [
            "skills", "forge",
            "--from", "http://clawhub.ai/skills/test",
        ])

        assert result.exit_code != 0
        assert "HTTPS" in result.output or "https" in result.output.lower()
