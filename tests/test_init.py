# tests/test_init.py
"""Tests for merkaba init onboarding wizard."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call

from typer.testing import CliRunner
from merkaba.cli import app
from merkaba.init import check_file_safety, FileAction, check_ollama, ModelStatus, run_preflight, pull_model, run_interview, InterviewDepth, run_extras, run_init, check_first_run
from merkaba.config.prompts import DEFAULT_SOUL, DEFAULT_USER

cli_runner = CliRunner()


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


def test_interview_returns_soul_and_user(monkeypatch):
    """Interview runs LLM conversation and returns generated SOUL.md and USER.md."""
    # Mock LLMClient
    mock_llm = MagicMock()
    # First call: interview questions (3 turns)
    # The LLM asks a question, user answers, repeat until [DONE]
    mock_llm.chat.side_effect = [
        MagicMock(content="What's your name?"),
        MagicMock(content="What are you building?"),
        MagicMock(content="What do you want Merkaba to help with?"),
        MagicMock(content="[DONE]"),
        # Synthesis call
        MagicMock(content="SOUL:\nYou are Merkaba, Cevin's AI partner.\n---\nUSER:\nCevin is building digital products."),
    ]
    monkeypatch.setattr("merkaba.llm.LLMClient", lambda **kw: mock_llm)

    # Mock user input
    inputs = iter(["Cevin", "Digital products", "Business automation"])
    monkeypatch.setattr("builtins.input", lambda _="": next(inputs))

    soul, user = run_interview(
        model="qwen3:8b",
        depth=InterviewDepth.QUICK,
    )
    assert "Cevin" in soul or "Cevin" in user
    assert soul != ""
    assert user != ""


def test_interview_depth_quick_has_fewer_topics():
    """Quick depth should have 3-4 topic areas."""
    from merkaba.init import INTERVIEW_TOPICS
    assert len(INTERVIEW_TOPICS[InterviewDepth.QUICK]) <= 4


def test_interview_depth_deep_has_more_topics():
    """Deep depth should have 8-12 topic areas."""
    from merkaba.init import INTERVIEW_TOPICS
    assert len(INTERVIEW_TOPICS[InterviewDepth.DEEP]) >= 8


def test_extras_skips_all_on_no(monkeypatch):
    """All extras declined — no side effects."""
    monkeypatch.setattr("builtins.input", lambda _: "n")
    # Should not raise or call anything
    run_extras()


def test_extras_scheduler_on_yes(monkeypatch):
    """Scheduler offer accepted — calls scheduler_install."""
    responses = iter(["y", "n", "n"])  # scheduler=yes, telegram=no, web=no
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    mock_install = MagicMock()
    monkeypatch.setattr("merkaba.init._install_scheduler", mock_install)
    run_extras()
    mock_install.assert_called_once()


def test_run_init_full_flow(tmp_path, monkeypatch):
    """Full init: preflight + interview + extras."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)

    # Mock Ollama as available with simple model
    mock_status = ModelStatus(available=True, installed_models=["qwen3:8b"], missing_models=["qwen3.5:122b", "qwen3:4b"])
    monkeypatch.setattr("merkaba.init.check_ollama", lambda: mock_status)

    # Mock interview conversation
    mock_llm = MagicMock()
    mock_llm.chat.side_effect = [
        MagicMock(content="What's your name?"),
        MagicMock(content="[DONE]"),
        MagicMock(content="SOUL:\nCustom soul\n---\nUSER:\nCustom user"),
    ]
    monkeypatch.setattr("merkaba.llm.LLMClient", lambda **kw: mock_llm)

    # Mock all user inputs: depth=1, interview answer, review=y, extras=n,n,n
    all_inputs = iter(["1", "Test user", "y", "n", "n", "n"])
    monkeypatch.setattr("builtins.input", lambda _="": next(all_inputs))

    run_init(no_interview=False, force=False)

    assert (home / "config.json").exists()
    assert (home / "SOUL.md").exists()
    assert (home / "USER.md").exists()


def test_run_init_no_interview(tmp_path, monkeypatch):
    """Init with --no-interview skips interview phase."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    mock_status = ModelStatus(available=False, missing_models=[])
    monkeypatch.setattr("merkaba.init.check_ollama", lambda: mock_status)

    # Only extras inputs needed (all no)
    monkeypatch.setattr("builtins.input", lambda _="": "n")

    run_init(no_interview=True, force=False)

    assert (home / "config.json").exists()
    # SOUL.md should have the default (not interview-generated)
    assert (home / "SOUL.md").read_text() == DEFAULT_SOUL


def test_cli_init_no_interview(tmp_path, monkeypatch):
    """CLI `merkaba init --no-interview` runs preflight and extras."""
    home = tmp_path / "merkaba"
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    mock_status = ModelStatus(available=False, missing_models=[])
    monkeypatch.setattr("merkaba.init.check_ollama", lambda: mock_status)
    monkeypatch.setattr("builtins.input", lambda _="": "n")

    result = cli_runner.invoke(app, ["init", "--no-interview"])
    assert result.exit_code == 0
    assert "Welcome to Merkaba" in result.output
    assert (home / "config.json").exists()


def test_first_run_nudge_when_no_config(tmp_path, capsys, monkeypatch):
    """Prints nudge when config.json doesn't exist."""
    home = tmp_path / "merkaba"
    home.mkdir()
    # No config.json
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    monkeypatch.setattr("merkaba.init._nudge_shown", False)
    check_first_run()
    captured = capsys.readouterr()
    assert "merkaba init" in captured.out


def test_first_run_no_nudge_when_config_exists(tmp_path, capsys, monkeypatch):
    """No nudge when config.json exists."""
    home = tmp_path / "merkaba"
    home.mkdir()
    (home / "config.json").write_text("{}")
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    monkeypatch.setattr("merkaba.init._nudge_shown", False)
    check_first_run()
    captured = capsys.readouterr()
    assert "merkaba init" not in captured.out


def test_first_run_nudge_only_once(tmp_path, capsys, monkeypatch):
    """Nudge prints only once per process."""
    home = tmp_path / "merkaba"
    home.mkdir()
    monkeypatch.setattr("merkaba.init.MERKABA_DIR", home)
    monkeypatch.setattr("merkaba.init._nudge_shown", False)
    check_first_run()
    check_first_run()  # second call should be silent
    captured = capsys.readouterr()
    assert captured.out.count("merkaba init") == 1
