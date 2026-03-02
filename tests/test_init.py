# tests/test_init.py
"""Tests for merkaba init onboarding wizard."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from merkaba.init import check_file_safety, FileAction, check_ollama, ModelStatus, run_preflight, pull_model
from merkaba.config.prompts import DEFAULT_SOUL, DEFAULT_USER


def test_check_file_safety_missing_file(tmp_path):
    """File doesn't exist — should write without warning."""
    path = tmp_path / "SOUL.md"
    result = check_file_safety(path, "default content", force=False)
    assert result == FileAction.WRITE


def test_check_file_safety_matches_default(tmp_path):
    """File exists but matches default — safe to overwrite."""
    path = tmp_path / "SOUL.md"
    path.write_text("default content")
    result = check_file_safety(path, "default content", force=False)
    assert result == FileAction.WRITE


def test_check_file_safety_user_edited(tmp_path, monkeypatch):
    """File exists and differs from default — should prompt (mock returns 'skip')."""
    path = tmp_path / "SOUL.md"
    path.write_text("my custom soul")
    monkeypatch.setattr("builtins.input", lambda _: "s")
    result = check_file_safety(path, "default content", force=False)
    assert result == FileAction.SKIP


def test_check_file_safety_user_edited_backup(tmp_path, monkeypatch):
    """User chooses backup when file differs."""
    path = tmp_path / "SOUL.md"
    path.write_text("my custom soul")
    monkeypatch.setattr("builtins.input", lambda _: "b")
    result = check_file_safety(path, "default content", force=False)
    assert result == FileAction.BACKUP
    assert (tmp_path / "SOUL.md.bak").read_text() == "my custom soul"


def test_check_file_safety_force_backs_up(tmp_path):
    """--force auto-backs up user-edited files."""
    path = tmp_path / "SOUL.md"
    path.write_text("my custom soul")
    result = check_file_safety(path, "default content", force=True)
    assert result == FileAction.BACKUP
    assert (tmp_path / "SOUL.md.bak").read_text() == "my custom soul"


def test_check_ollama_running_all_models(monkeypatch):
    """Ollama running with all models present."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "models": [
            {"name": "qwen3:8b"},
            {"name": "qwen3.5:122b"},
            {"name": "qwen3:4b"},
        ]
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = check_ollama()

    assert result.available is True
    assert "qwen3:8b" in result.installed_models
    assert result.missing_models == []


def test_check_ollama_running_missing_models(monkeypatch):
    """Ollama running but some models missing."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "models": [{"name": "qwen3:8b"}]
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = check_ollama()

    assert result.available is True
    assert "qwen3:8b" in result.installed_models
    assert "qwen3.5:122b" in result.missing_models


def test_check_ollama_not_running():
    """Ollama not reachable."""
    with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
        result = check_ollama()

    assert result.available is False
    assert result.installed_models == []


def test_preflight_creates_directories(tmp_path, monkeypatch):
    """Preflight creates ~/.merkaba/ and subdirs."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    with patch("merkaba.init.check_ollama") as mock_ollama:
        mock_ollama.return_value = ModelStatus(available=False, missing_models=[])
        run_preflight(force=False)

    assert (home / "logs").is_dir()
    assert (home / "conversations").is_dir()
    assert (home / "plugins").is_dir()


def test_preflight_writes_default_config(tmp_path, monkeypatch):
    """Preflight creates config.json with sensible defaults."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    with patch("merkaba.init.check_ollama") as mock_ollama:
        mock_ollama.return_value = ModelStatus(available=False, missing_models=[])
        run_preflight(force=False)

    config = json.loads((home / "config.json").read_text())
    assert config["models"]["simple"] == "qwen3:8b"
    assert config["models"]["complex"] == "qwen3.5:122b"


def test_preflight_seeds_soul_and_user(tmp_path, monkeypatch):
    """Preflight creates SOUL.md and USER.md from defaults."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    with patch("merkaba.init.check_ollama") as mock_ollama:
        mock_ollama.return_value = ModelStatus(available=False, missing_models=[])
        run_preflight(force=False)

    assert (home / "SOUL.md").read_text() == DEFAULT_SOUL
    assert (home / "USER.md").read_text() == DEFAULT_USER


def test_preflight_skips_user_edited_files(tmp_path, monkeypatch):
    """Preflight doesn't overwrite user-customized files."""
    home = tmp_path / "merkaba"
    home.mkdir()
    (home / "SOUL.md").write_text("my custom soul")
    (home / "config.json").write_text("{}")
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    # Mock input to return 's' (skip) for the prompt
    monkeypatch.setattr("builtins.input", lambda _: "s")
    with patch("merkaba.init.check_ollama") as mock_ollama:
        mock_ollama.return_value = ModelStatus(available=False, missing_models=[])
        run_preflight(force=False)

    # SOUL.md should not have been overwritten
    assert (home / "SOUL.md").read_text() == "my custom soul"


def test_preflight_returns_model_status(tmp_path, monkeypatch):
    """Preflight returns the ModelStatus from check_ollama."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    expected = ModelStatus(available=True, installed_models=["qwen3:8b"], missing_models=[])
    with patch("merkaba.init.check_ollama", return_value=expected):
        result = run_preflight(force=False)

    assert result.available is True


def test_pull_model_success(monkeypatch):
    """pull_model calls ollama pull and returns True on success."""
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr("subprocess.run", mock_run)
    result = pull_model("qwen3:8b")
    assert result is True
    mock_run.assert_called_once()
    args = mock_run.call_args
    assert args[0][0] == ["ollama", "pull", "qwen3:8b"]


def test_pull_model_failure(monkeypatch):
    """pull_model returns False when ollama pull fails."""
    mock_run = MagicMock(return_value=MagicMock(returncode=1))
    monkeypatch.setattr("subprocess.run", mock_run)
    result = pull_model("qwen3:8b")
    assert result is False
