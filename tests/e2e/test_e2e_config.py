# tests/e2e/test_e2e_config.py
"""End-to-end tests for config show/validate/set and top-level status commands.

Uses real SQLite databases (in temp dirs) and real CLI invocations.
Config file I/O is redirected to a temp path to isolate from the user's
actual ~/.merkaba/config.json.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def cli_runner_config(patched_dbs):
    """CliRunner with MERKABA_DIR patched to the temp merkaba_home.

    patched_dbs (from conftest) already provides merkaba_home with a
    minimal config.json.  We write a richer config on top of it and
    patch MERKABA_DIR so all config commands use the temp dir.
    """
    from typer.testing import CliRunner
    from merkaba.cli import app

    home = patched_dbs  # patched_dbs yields the merkaba_home Path
    # Overwrite config.json with a richer fixture config
    cfg = {
        "models": {"simple": "qwen3:8b", "complex": "qwen3.5:122b"},
        "cloud_providers": {
            "openai": {"api_key": "sk-secret-key", "model": "gpt-4o"},
        },
        "security": {"classifier_fail_mode": "allow"},
    }
    (home / "config.json").write_text(json.dumps(cfg, indent=2))

    runner = CliRunner()
    with patch("merkaba.cli.MERKABA_DIR", str(home)):
        yield runner, app, home


# ---------------------------------------------------------------------------
# 1. config show
# ---------------------------------------------------------------------------

def test_config_show(cli_runner_config):
    """config show prints config content and redacts api_key fields."""
    runner, app, home = cli_runner_config

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0, result.output
    # Model values should appear
    assert "qwen3:8b" in result.output
    assert "qwen3.5:122b" in result.output
    # api_key must be redacted
    assert "sk-secret-key" not in result.output
    assert "***redacted***" in result.output
    # Non-sensitive fields still present
    assert "openai" in result.output


def test_config_show_missing_file(cli_runner_config):
    """config show with no config.json prints a dim message, no error."""
    runner, app, home = cli_runner_config
    (home / "config.json").unlink()

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "No config.json" in result.output


def test_config_show_redacts_secret_key(cli_runner_config):
    """config show redacts keys containing 'secret' too."""
    runner, app, home = cli_runner_config
    cfg = {"webhook_secret": "super-secret-value", "name": "visible"}
    (home / "config.json").write_text(json.dumps(cfg))

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "super-secret-value" not in result.output
    assert "***redacted***" in result.output
    assert "visible" in result.output


# ---------------------------------------------------------------------------
# 2. config validate
# ---------------------------------------------------------------------------

def test_config_validate_clean(cli_runner_config):
    """config validate with a valid config reports no issues."""
    runner, app, home = cli_runner_config

    result = runner.invoke(app, ["config", "validate"])

    assert result.exit_code == 0
    assert "valid" in result.output.lower() or "no issues" in result.output.lower()


def test_config_validate_missing_models(cli_runner_config):
    """config validate with a config missing models produces warnings.

    We stub validate_config to return a WARNING so we can assert the
    command formats and displays it properly, independent of the
    patched_dbs blanket stub.
    """
    from merkaba.config.validation import ConfigIssue, Severity

    runner, app, home = cli_runner_config
    (home / "config.json").write_text(json.dumps({"security": {}}))

    warning = ConfigIssue(
        severity=Severity.WARNING,
        component="model_routing",
        message="Model routing incomplete: missing simple, complex model(s)",
        hint="Set models.simple and models.complex in config.json",
    )

    with patch("merkaba.config.validation.validate_config", return_value=[warning]):
        result = runner.invoke(app, ["config", "validate"])

    assert result.exit_code == 0, result.output
    assert "model_routing" in result.output
    assert "Model routing incomplete" in result.output


def test_config_validate_no_file(cli_runner_config):
    """config validate with no config.json uses empty config and shows warnings."""
    runner, app, home = cli_runner_config
    (home / "config.json").unlink()

    result = runner.invoke(app, ["config", "validate"])

    # Empty config → missing models → warning (exit 0)
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# 3. config set
# ---------------------------------------------------------------------------

def test_config_set_simple_key(cli_runner_config):
    """config set writes a top-level key to config.json."""
    runner, app, home = cli_runner_config

    result = runner.invoke(app, ["config", "set", "debug", "true"])

    assert result.exit_code == 0, result.output
    assert "debug" in result.output

    with open(home / "config.json") as f:
        data = json.load(f)
    assert data["debug"] is True


def test_config_set_dotted_path(cli_runner_config):
    """config set navigates a dotted path and writes the value."""
    runner, app, home = cli_runner_config

    result = runner.invoke(app, ["config", "set", "security.classifier_fail_mode", "block"])

    assert result.exit_code == 0, result.output
    with open(home / "config.json") as f:
        data = json.load(f)
    assert data["security"]["classifier_fail_mode"] == "block"


def test_config_set_creates_intermediate_dicts(cli_runner_config):
    """config set creates intermediate dicts if the path does not exist."""
    runner, app, home = cli_runner_config

    result = runner.invoke(app, ["config", "set", "new.nested.key", "hello"])

    assert result.exit_code == 0, result.output
    with open(home / "config.json") as f:
        data = json.load(f)
    assert data["new"]["nested"]["key"] == "hello"


def test_config_set_int_coercion(cli_runner_config):
    """config set auto-coerces numeric strings to int."""
    runner, app, home = cli_runner_config

    runner.invoke(app, ["config", "set", "max_retries", "5"])

    with open(home / "config.json") as f:
        data = json.load(f)
    assert data["max_retries"] == 5
    assert isinstance(data["max_retries"], int)


def test_config_set_float_coercion(cli_runner_config):
    """config set auto-coerces float strings to float."""
    runner, app, home = cli_runner_config

    runner.invoke(app, ["config", "set", "temperature", "0.7"])

    with open(home / "config.json") as f:
        data = json.load(f)
    assert data["temperature"] == 0.7
    assert isinstance(data["temperature"], float)


# ---------------------------------------------------------------------------
# 4. status
# ---------------------------------------------------------------------------

def test_status_runs_without_error(cli_runner_config):
    """status command exits 0 and prints a Rich table."""
    runner, app, home = cli_runner_config

    with (
        patch("urllib.request.urlopen", side_effect=OSError("connection refused")),
    ):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    # Table headers / check names present
    assert "Ollama" in result.output
    assert "memory.db" in result.output
    assert "Approvals" in result.output
    assert "Workers" in result.output


def test_status_ollama_ok(cli_runner_config):
    """status shows OK for Ollama when the endpoint is reachable."""
    runner, app, home = cli_runner_config

    from unittest.mock import MagicMock
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "OK" in result.output


def test_status_ollama_fail(cli_runner_config):
    """status shows FAIL for Ollama when the endpoint is unreachable."""
    runner, app, home = cli_runner_config

    with patch("urllib.request.urlopen", side_effect=OSError("refused")):
        result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "FAIL" in result.output
