# tests/test_init.py
"""Tests for merkaba init onboarding wizard."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from merkaba.init import check_file_safety, FileAction, check_ollama, ModelStatus


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
