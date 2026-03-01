# tests/e2e/test_e2e_models.py
"""End-to-end tests for model configuration CLI commands.

Uses real CLI invocations with patched CONFIG_PATH to isolate from
the user's actual ~/.merkaba/config.json.
"""

import json
import os
from functools import partial
from unittest.mock import patch, MagicMock

import pytest

from merkaba.orchestration.supervisor import load_model_config as _real_load

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config_path(tmp_path):
    """Temp config path for model tests."""
    return str(tmp_path / "config.json")


@pytest.fixture()
def patched_config(config_path):
    """Patch CONFIG_PATH and load_model_config to use a temp config file."""
    redirected_load = partial(_real_load, config_path=config_path)
    with (
        patch("merkaba.orchestration.supervisor.CONFIG_PATH", config_path),
        patch("merkaba.orchestration.supervisor.load_model_config", redirected_load),
    ):
        yield config_path


# ---------------------------------------------------------------------------
# 1. List defaults
# ---------------------------------------------------------------------------

def test_models_list_defaults(cli_runner, patched_config):
    """With no config file, models list should show MODEL_DEFAULTS entries."""
    runner, app = cli_runner

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "health_check" in result.output
    assert "code" in result.output
    assert "phi4:14b" in result.output
    assert "qwen3.5:122b" in result.output


# ---------------------------------------------------------------------------
# 2. Set then list
# ---------------------------------------------------------------------------

def test_models_set_and_list(cli_runner, patched_config):
    """Set a model override, then list to verify it appears with 'config' source."""
    runner, app = cli_runner
    config_path = patched_config

    # Set a custom model for a task type
    result = runner.invoke(app, ["models", "set", "summarize", "llama3:70b"])
    assert result.exit_code == 0
    assert "summarize" in result.output
    assert "llama3:70b" in result.output

    # Verify config was written
    with open(config_path) as f:
        data = json.load(f)
    assert data["models"]["task_types"]["summarize"] == "llama3:70b"

    # List should show the override with "config" source
    result = runner.invoke(app, ["models", "list"])
    assert result.exit_code == 0
    assert "summarize" in result.output
    assert "llama3:70b" in result.output
    assert "config" in result.output


# ---------------------------------------------------------------------------
# 3. Check with models
# ---------------------------------------------------------------------------

def test_models_check_with_models(cli_runner):
    """Mock LLMClient and load_fallback_chains, verify check shows loaded models."""
    runner, app = cli_runner

    mock_client = MagicMock()
    mock_client.get_available_models.return_value = ["qwen3.5:122b", "phi4:14b"]

    with (
        patch("merkaba.llm.LLMClient") as MockLLM,
        patch("merkaba.llm.load_fallback_chains") as mock_chains,
    ):
        MockLLM.return_value = mock_client
        mock_chains.return_value = {}

        result = runner.invoke(app, ["models", "check"])

    assert result.exit_code == 0
    assert "qwen3.5:122b" in result.output
    assert "phi4:14b" in result.output
    assert "Loaded models" in result.output


# ---------------------------------------------------------------------------
# 4. List shows fallback entry
# ---------------------------------------------------------------------------

def test_models_list_shows_fallback(cli_runner, patched_config):
    """The list output should include a '(other)' fallback entry."""
    runner, app = cli_runner

    result = runner.invoke(app, ["models", "list"])

    assert result.exit_code == 0
    assert "(other)" in result.output
    assert "fallback" in result.output
