# tests/test_agent_hot_reload.py
"""Tests for hot-reloadable config integration in Agent."""

import json
import sys
import time
from unittest.mock import MagicMock

import pytest

if "ollama" not in sys.modules:
    mock_ollama = MagicMock()
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})
    sys.modules["ollama"] = mock_ollama

from merkaba.agent import Agent
from merkaba.config.hot_reload import HotConfig


def _make_agent(**overrides):
    """Create a minimal Agent for testing _resolve_model.

    Bypasses __post_init__ by using __new__ and setting only the fields
    that _resolve_model touches.
    """
    agent = Agent.__new__(Agent)
    agent.model = overrides.get("model", "qwen3.5:122b")
    agent.simple_model = overrides.get("simple_model", "qwen3:8b")
    agent._hot_config = overrides.get("hot_config", None)
    return agent


def test_agent_picks_up_model_change(tmp_path):
    """Agent uses updated model from HotConfig without restart."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "models": {"complex": "qwen3.5:122b", "simple": "qwen3:8b"}
    }))

    agent = _make_agent(hot_config=HotConfig(config_file))

    # Initial models match config
    assert agent._resolve_model("complex") == "qwen3.5:122b"
    assert agent._resolve_model("simple") == "qwen3:8b"

    # Change config on disk
    time.sleep(0.05)  # ensure mtime advances
    config_file.write_text(json.dumps({
        "models": {"complex": "llama3:70b", "simple": "llama3:8b"}
    }))

    # Should pick up new models without restart
    assert agent._resolve_model("complex") == "llama3:70b"
    assert agent._resolve_model("simple") == "llama3:8b"


def test_agent_falls_back_without_hot_config():
    """Without HotConfig, agent uses static model fields."""
    agent = _make_agent()

    assert agent._resolve_model("complex") == "qwen3.5:122b"
    assert agent._resolve_model("simple") == "qwen3:8b"


def test_agent_survives_missing_models_key(tmp_path):
    """If config has no 'models' key, falls back to static fields."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"other": "stuff"}))

    agent = _make_agent(hot_config=HotConfig(config_file))

    assert agent._resolve_model("complex") == "qwen3.5:122b"
    assert agent._resolve_model("simple") == "qwen3:8b"


def test_agent_survives_models_not_dict(tmp_path):
    """If config 'models' is not a dict, falls back to static fields."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"models": "not a dict"}))

    agent = _make_agent(hot_config=HotConfig(config_file))

    assert agent._resolve_model("complex") == "qwen3.5:122b"
    assert agent._resolve_model("simple") == "qwen3:8b"


def test_resolve_model_partial_config(tmp_path):
    """Config with only 'complex' key — simple falls back to static."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "models": {"complex": "deepseek:33b"}
    }))

    agent = _make_agent(hot_config=HotConfig(config_file))

    assert agent._resolve_model("complex") == "deepseek:33b"
    assert agent._resolve_model("simple") == "qwen3:8b"  # static fallback


def test_resolve_model_unknown_tier_uses_complex(tmp_path):
    """An unknown tier falls back to complex model resolution."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({
        "models": {"complex": "big-model:100b"}
    }))

    agent = _make_agent(hot_config=HotConfig(config_file))

    # Anything not "simple" should resolve as complex
    assert agent._resolve_model("complex") == "big-model:100b"
    assert agent._resolve_model("standard") == "big-model:100b"


def test_post_init_creates_hot_config(tmp_path):
    """Agent.__post_init__ creates _hot_config when config file exists."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"models": {"complex": "test:1b"}}))

    from unittest.mock import patch
    with patch("merkaba.agent.SecurityScanner"), \
         patch("merkaba.agent.PluginRegistry"), \
         patch("merkaba.memory.vectors.VectorMemory", side_effect=ImportError), \
         patch("merkaba.agent.MERKABA_CONFIG_PATH", str(config_file)):
        agent = Agent(
            plugins_enabled=False,
            memory_storage_dir=str(tmp_path / "conversations"),
            prompt_dir=str(tmp_path / "prompts"),
        )

    assert agent._hot_config is not None
    assert agent._resolve_model("complex") == "test:1b"


def test_post_init_no_config_file(tmp_path):
    """Agent.__post_init__ sets _hot_config to None when no config file."""
    from unittest.mock import patch
    with patch("merkaba.agent.SecurityScanner"), \
         patch("merkaba.agent.PluginRegistry"), \
         patch("merkaba.memory.vectors.VectorMemory", side_effect=ImportError), \
         patch("merkaba.agent.MERKABA_CONFIG_PATH", str(tmp_path / "nonexistent.json")):
        agent = Agent(
            plugins_enabled=False,
            memory_storage_dir=str(tmp_path / "conversations"),
            prompt_dir=str(tmp_path / "prompts"),
        )

    assert agent._hot_config is None
    # Still resolves via static fields
    assert agent._resolve_model("complex") == "qwen3.5:122b"
    assert agent._resolve_model("simple") == "qwen3:8b"
