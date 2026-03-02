# tests/e2e/test_e2e_init.py
"""End-to-end tests for the `merkaba init` onboarding command.

Uses a temporary MERKABA_HOME to avoid touching ~/.merkaba/.
Tests the init module directly and via the CLI runner.
"""

import json

import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from merkaba.cli import app
from merkaba.init import run_init, DEFAULT_CONFIG

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_cli_init(tmp_path, args=None):
    """Run `merkaba init` via CLI with MERKABA_HOME pointed at tmp_path."""
    home = tmp_path / "merkaba_home"
    runner = CliRunner()

    cli_args = ["init"] + (args or [])

    with patch("merkaba.cli.os.path.expanduser", return_value=str(home)):
        with patch("merkaba.init._check_ollama", return_value=False):
            result = runner.invoke(app, cli_args)
    return result, home


# ---------------------------------------------------------------------------
# 1. Fresh init creates directory structure
# ---------------------------------------------------------------------------

class TestInitCreatesDirectories:
    """Test: run_init creates ~/.merkaba/ and all subdirectories."""

    def test_creates_home_and_subdirs(self, tmp_path):
        home = tmp_path / "merkaba_home"
        result = run_init(home, skip_ollama_check=True)

        assert home.is_dir()
        assert (home / "conversations").is_dir()
        assert (home / "plugins").is_dir()
        assert (home / "businesses").is_dir()
        assert (home / "backups").is_dir()
        assert (home / "logs").is_dir()
        assert len(result.created_dirs) > 0


# ---------------------------------------------------------------------------
# 2. Config.json is written with defaults
# ---------------------------------------------------------------------------

class TestInitWritesConfig:
    """Test: run_init writes config.json with default model routing."""

    def test_config_written_with_defaults(self, tmp_path):
        home = tmp_path / "merkaba_home"
        result = run_init(home, skip_ollama_check=True)

        config_path = home / "config.json"
        assert config_path.is_file()
        assert result.config_written is True

        config = json.loads(config_path.read_text())
        assert config["models"]["complex"] == DEFAULT_CONFIG["models"]["complex"]
        assert config["models"]["simple"] == DEFAULT_CONFIG["models"]["simple"]
        assert config["models"]["classifier"] == DEFAULT_CONFIG["models"]["classifier"]


# ---------------------------------------------------------------------------
# 3. SOUL.md and USER.md copied from templates
# ---------------------------------------------------------------------------

class TestInitCopiesTemplates:
    """Test: run_init copies SOUL.md and USER.md from .example templates."""

    def test_soul_md_copied(self, tmp_path):
        home = tmp_path / "merkaba_home"
        result = run_init(home, skip_ollama_check=True)

        soul_path = home / "SOUL.md"
        assert soul_path.is_file()
        assert result.soul_copied is True
        # Should contain content from the example
        content = soul_path.read_text()
        assert "Merkaba" in content

    def test_user_md_copied(self, tmp_path):
        home = tmp_path / "merkaba_home"
        result = run_init(home, skip_ollama_check=True)

        user_path = home / "USER.md"
        assert user_path.is_file()
        assert result.user_copied is True


# ---------------------------------------------------------------------------
# 4. Databases are initialized
# ---------------------------------------------------------------------------

class TestInitDatabases:
    """Test: run_init creates and initializes SQLite databases."""

    def test_databases_created(self, tmp_path):
        home = tmp_path / "merkaba_home"
        result = run_init(home, skip_ollama_check=True)

        assert (home / "memory.db").is_file()
        assert (home / "tasks.db").is_file()
        assert (home / "actions.db").is_file()
        assert "memory.db" in result.databases_initialized
        assert "tasks.db" in result.databases_initialized
        assert "actions.db" in result.databases_initialized


# ---------------------------------------------------------------------------
# 5. Already initialized -- no overwrite without --force
# ---------------------------------------------------------------------------

class TestInitAlreadyInitialized:
    """Test: running init twice without --force detects existing setup."""

    def test_already_initialized_flag(self, tmp_path):
        home = tmp_path / "merkaba_home"
        # First run
        run_init(home, skip_ollama_check=True)

        # Second run without force
        result2 = run_init(home, skip_ollama_check=True)
        assert result2.already_initialized is True
        assert result2.config_written is False
        assert result2.soul_copied is False
        assert result2.user_copied is False


# ---------------------------------------------------------------------------
# 6. Force re-initializes config and templates
# ---------------------------------------------------------------------------

class TestInitForce:
    """Test: --force re-creates config.json and templates."""

    def test_force_rewrites_config(self, tmp_path):
        home = tmp_path / "merkaba_home"
        # First init
        run_init(home, skip_ollama_check=True)

        # Modify config
        config_path = home / "config.json"
        config_path.write_text(json.dumps({"custom": True}))

        # Force re-init
        result = run_init(home, force=True, skip_ollama_check=True)
        assert result.config_written is True

        config = json.loads(config_path.read_text())
        assert "models" in config
        assert "custom" not in config


# ---------------------------------------------------------------------------
# 7. CLI command -- fresh init
# ---------------------------------------------------------------------------

class TestCliInit:
    """Test: `merkaba init` CLI command works end-to-end."""

    def test_cli_init_fresh(self, tmp_path):
        result, home = _run_cli_init(tmp_path)

        assert result.exit_code == 0
        assert "initialized" in result.output.lower()
        assert (home / "config.json").is_file()
        assert (home / "memory.db").is_file()


# ---------------------------------------------------------------------------
# 8. CLI command -- already initialized shows message
# ---------------------------------------------------------------------------

class TestCliInitAlreadyInitialized:
    """Test: `merkaba init` when already initialized shows warning."""

    def test_cli_init_already_initialized(self, tmp_path):
        home = tmp_path / "merkaba_home"
        # Pre-create the home with config
        run_init(home, skip_ollama_check=True)

        runner = CliRunner()
        with patch("merkaba.cli.os.path.expanduser", return_value=str(home)):
            with patch("merkaba.init._check_ollama", return_value=False):
                result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert "already initialized" in result.output.lower()


# ---------------------------------------------------------------------------
# 9. CLI command -- force flag
# ---------------------------------------------------------------------------

class TestCliInitForce:
    """Test: `merkaba init --force` re-initializes even if already set up."""

    def test_cli_init_force(self, tmp_path):
        home = tmp_path / "merkaba_home"
        # First init
        run_init(home, skip_ollama_check=True)

        runner = CliRunner()
        with patch("merkaba.cli.os.path.expanduser", return_value=str(home)):
            with patch("merkaba.init._check_ollama", return_value=False):
                result = runner.invoke(app, ["init", "--force"])

        assert result.exit_code == 0
        assert "initialized" in result.output.lower()
        # "already initialized" should NOT appear with --force
        assert "already initialized" not in result.output.lower()
