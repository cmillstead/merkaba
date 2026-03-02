# tests/test_init.py
"""Tests for merkaba init onboarding wizard."""

import json
from pathlib import Path

from merkaba.init import check_file_safety, FileAction


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
