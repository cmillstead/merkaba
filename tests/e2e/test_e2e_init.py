# tests/e2e/test_e2e_init.py
"""E2E tests for merkaba init onboarding wizard."""

import json
import os
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from merkaba.cli import app

runner = CliRunner()
pytestmark = pytest.mark.e2e


@pytest.fixture()
def init_home(tmp_path, monkeypatch):
    """Temp merkaba home for init tests."""
    home = tmp_path / "merkaba_home"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    return home


def _mock_ollama_unavailable():
    """Mock check_ollama to return unavailable."""
    return patch(
        "merkaba.init.check_ollama",
        return_value=MagicMock(available=False, installed_models=[], missing_models=[]),
    )


def _mock_ollama_available(models=None):
    """Mock check_ollama to return available with given models."""
    if models is None:
        models = ["qwen3:8b"]
    return patch(
        "merkaba.init.check_ollama",
        return_value=MagicMock(
            available=True,
            installed_models=models,
            missing_models=[m for m in ["qwen3:8b", "qwen3.5:122b", "qwen3:4b"] if m not in models],
        ),
    )


class TestInitPreflight:
    def test_creates_directory_structure(self, init_home):
        with _mock_ollama_unavailable():
            result = runner.invoke(app, ["init", "--no-interview"], input="n\nn\nn\n")
        assert result.exit_code == 0
        assert init_home.is_dir()
        assert (init_home / "logs").is_dir()
        assert (init_home / "conversations").is_dir()
        assert (init_home / "plugins").is_dir()

    def test_creates_config_json(self, init_home):
        with _mock_ollama_unavailable():
            result = runner.invoke(app, ["init", "--no-interview"], input="n\nn\nn\n")
        assert result.exit_code == 0
        config = json.loads((init_home / "config.json").read_text())
        assert config["models"]["simple"] == "qwen3:8b"
        assert config["models"]["complex"] == "qwen3.5:122b"

    def test_creates_soul_and_user(self, init_home):
        with _mock_ollama_unavailable():
            result = runner.invoke(app, ["init", "--no-interview"], input="n\nn\nn\n")
        assert result.exit_code == 0
        assert (init_home / "SOUL.md").exists()
        assert (init_home / "USER.md").exists()
        assert "Merkaba" in (init_home / "SOUL.md").read_text()

    def test_ollama_not_running_message(self, init_home):
        with _mock_ollama_unavailable():
            result = runner.invoke(app, ["init", "--no-interview"], input="n\nn\nn\n")
        assert "Ollama is not running" in result.output

    def test_preserves_user_edited_files(self, init_home):
        init_home.mkdir(parents=True)
        (init_home / "SOUL.md").write_text("my custom soul")
        with _mock_ollama_unavailable():
            # 's' to skip the customized file, then 'n' for all extras
            result = runner.invoke(app, ["init", "--no-interview"], input="s\nn\nn\nn\n")
        assert result.exit_code == 0
        assert (init_home / "SOUL.md").read_text() == "my custom soul"

    def test_force_backs_up_edited_files(self, init_home):
        init_home.mkdir(parents=True)
        (init_home / "SOUL.md").write_text("my custom soul")
        with _mock_ollama_unavailable():
            result = runner.invoke(app, ["init", "--no-interview", "--force"], input="n\nn\nn\n")
        assert result.exit_code == 0
        assert (init_home / "SOUL.md.bak").exists()
        assert (init_home / "SOUL.md.bak").read_text() == "my custom soul"


class TestInitInterview:
    def test_interview_with_mocked_llm(self, init_home, monkeypatch):
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [
            MagicMock(content="What's your name?"),
            MagicMock(content="[DONE]"),
            MagicMock(content="SOUL:\nPersonalized soul\n---\nUSER:\nPersonalized user"),
        ]
        monkeypatch.setattr("merkaba.llm.LLMClient", lambda **kw: mock_llm)

        with _mock_ollama_available():
            # depth=1 (quick), answer, review=y, extras=n,n,n
            result = runner.invoke(app, ["init"], input="1\nTest User\ny\nn\nn\nn\n")

        assert result.exit_code == 0
        assert "Personalized soul" in (init_home / "SOUL.md").read_text()

    def test_no_interview_flag_skips(self, init_home):
        with _mock_ollama_available():
            result = runner.invoke(app, ["init", "--no-interview"], input="n\nn\nn\n")
        assert result.exit_code == 0
        assert "Quick intro" not in result.output


class TestInitSummary:
    def test_prints_next_steps(self, init_home):
        with _mock_ollama_unavailable():
            result = runner.invoke(app, ["init", "--no-interview"], input="n\nn\nn\n")
        assert "Setup complete" in result.output
        assert "merkaba chat" in result.output
