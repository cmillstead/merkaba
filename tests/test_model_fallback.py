# tests/test_model_fallback.py
"""Tests for Phase 10: Graceful Degradation & Model Fallbacks."""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest

# Use the ollama mock installed by conftest (which has proper exception classes).
# If conftest hasn't run yet (shouldn't happen), install a proper mock.
import ollama as _ollama_mod
FakeResponseError = _ollama_mod.ResponseError
FakeRequestError = _ollama_mod.RequestError

from merkaba.llm import (
    AllModelsUnavailableError,
    LLMClient,
    LLMResponse,
    LLMUnavailableError,
    MODEL_CHAINS,
    ModelTier,
    RetryConfig,
    load_fallback_chains,
)


# --- ModelTier & chains ---


class TestModelTierAndChains:
    def test_model_chains_have_expected_tiers(self):
        assert "complex" in MODEL_CHAINS
        assert "simple" in MODEL_CHAINS
        assert "classifier" in MODEL_CHAINS

    def test_model_tier_defaults(self):
        assert MODEL_CHAINS["complex"].primary == "qwen3.5:122b"
        assert "qwen3:8b" in MODEL_CHAINS["complex"].fallbacks
        assert MODEL_CHAINS["simple"].primary == "qwen3:8b"
        assert MODEL_CHAINS["classifier"].primary == "qwen3:4b"
        assert MODEL_CHAINS["classifier"].fallbacks == []

    def test_load_fallback_chains_from_config(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "models": {
                "fallback_chains": {
                    "complex": {
                        "primary": "llama3:70b",
                        "fallbacks": ["llama3:8b", "phi4:14b"],
                        "timeout": 60.0,
                    }
                }
            }
        }))
        chains = load_fallback_chains(str(config))
        assert chains["complex"].primary == "llama3:70b"
        assert chains["complex"].fallbacks == ["llama3:8b", "phi4:14b"]
        assert chains["complex"].timeout == 60.0
        # Other tiers unchanged
        assert chains["simple"].primary == "qwen3:8b"

    def test_load_fallback_chains_missing_config(self, tmp_path):
        chains = load_fallback_chains(str(tmp_path / "nonexistent.json"))
        assert chains == {k: ModelTier(primary=v.primary, fallbacks=list(v.fallbacks), timeout=v.timeout)
                          for k, v in MODEL_CHAINS.items()}


# --- get_available_models ---


class TestGetAvailableModels:
    def test_returns_set_of_model_names(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        fake_response = MagicMock()
        fake_response.json.return_value = {
            "models": [
                {"name": "qwen3.5:122b"},
                {"name": "qwen3:8b"},
            ]
        }
        fake_response.raise_for_status = MagicMock()
        with patch("httpx.get", return_value=fake_response):
            result = client.get_available_models()
        assert result == {"qwen3.5:122b", "qwen3:8b"}

    def test_returns_empty_on_failure(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        with patch("httpx.get", side_effect=ConnectionError("down")):
            result = client.get_available_models()
        assert result == set()


# --- select_best_available ---


class TestSelectBestAvailable:
    def test_picks_primary_when_available(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        with patch.object(client, "get_available_models", return_value={"qwen3.5:122b", "qwen3:8b"}):
            result = client.select_best_available("complex")
        assert result == "qwen3.5:122b"

    def test_picks_fallback_when_primary_missing(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        with patch.object(client, "get_available_models", return_value={"qwen3:8b"}):
            result = client.select_best_available("complex")
        assert result == "qwen3:8b"

    def test_raises_all_unavailable_when_none_loaded(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        with patch.object(client, "get_available_models", return_value={"unrelated:model"}):
            with pytest.raises(AllModelsUnavailableError, match="No models available"):
                client.select_best_available("complex")

    def test_returns_primary_when_ollama_unreachable(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        with patch.object(client, "get_available_models", return_value=set()):
            result = client.select_best_available("complex")
        assert result == "qwen3.5:122b"

    def test_unknown_tier_raises_key_error(self):
        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"
        with pytest.raises(KeyError, match="Unknown model tier"):
            client.select_best_available("nonexistent")


# --- chat_with_fallback ---


class TestChatWithFallback:
    def test_succeeds_on_primary(self):
        client = LLMClient.__new__(LLMClient)
        expected = LLMResponse(content="hello", model="qwen3.5:122b")
        with patch.object(client, "chat_with_retry", return_value=expected):
            result = client.chat_with_fallback("hi", tier="complex")
        assert result.content == "hello"

    def test_tries_secondary_on_unavailable(self):
        client = LLMClient.__new__(LLMClient)
        expected = LLMResponse(content="from fallback", model="qwen3:8b")
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=[LLMUnavailableError("down"), expected],
        ):
            result = client.chat_with_fallback("hi", tier="complex")
        assert result.content == "from fallback"

    def test_tries_secondary_on_request_error(self):
        client = LLMClient.__new__(LLMClient)
        expected = LLMResponse(content="from fallback", model="qwen3:8b")
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=[FakeRequestError("model not found"), expected],
        ):
            result = client.chat_with_fallback("hi", tier="complex")
        assert result.content == "from fallback"

    def test_raises_all_unavailable_when_chain_exhausted(self):
        client = LLMClient.__new__(LLMClient)
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=LLMUnavailableError("down"),
        ):
            with pytest.raises(AllModelsUnavailableError, match="All models unavailable"):
                client.chat_with_fallback("hi", tier="complex")

    def test_unknown_tier_raises_key_error(self):
        client = LLMClient.__new__(LLMClient)
        with pytest.raises(KeyError, match="Unknown model tier"):
            client.chat_with_fallback("hi", tier="nonexistent")

    def test_records_audit_decision_on_fallback(self):
        client = LLMClient.__new__(LLMClient)
        expected = LLMResponse(content="ok", model="qwen3:8b")
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=[LLMUnavailableError("down"), expected],
        ):
            with patch("merkaba.observability.audit.record_decision") as mock_record:
                result = client.chat_with_fallback("hi", tier="complex")

        assert result.content == "ok"
        mock_record.assert_called_once()
        call_kwargs = mock_record.call_args
        assert call_kwargs.kwargs["decision_type"] == "model_fallback"
        assert "qwen3.5:122b" in call_kwargs.kwargs["decision"]
        assert "qwen3:8b" in call_kwargs.kwargs["decision"]

    def test_with_custom_config_chain(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "models": {
                "fallback_chains": {
                    "complex": {
                        "primary": "custom:big",
                        "fallbacks": ["custom:small"],
                    }
                }
            }
        }))
        client = LLMClient.__new__(LLMClient)
        expected = LLMResponse(content="from custom", model="custom:small")
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=[LLMUnavailableError("nope"), expected],
        ):
            with patch("merkaba.llm.CONFIG_PATH", str(config)):
                result = client.chat_with_fallback("hi", tier="complex")
        assert result.content == "from custom"

    def test_classifier_tier_has_no_fallback(self):
        """Classifier tier has empty fallbacks — single failure raises immediately."""
        client = LLMClient.__new__(LLMClient)
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=LLMUnavailableError("down"),
        ):
            with pytest.raises(AllModelsUnavailableError):
                client.chat_with_fallback("hi", tier="classifier")

    def test_llm_last_fallback_set(self):
        """last_fallback is set to the fallback model name when primary is unavailable."""
        client = LLMClient.__new__(LLMClient)
        client.last_fallback = None
        expected = LLMResponse(content="from fallback", model="qwen3:8b")
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=[LLMUnavailableError("primary down"), expected],
        ):
            result = client.chat_with_fallback("hi", tier="complex")
        assert result.content == "from fallback"
        assert client.last_fallback == "qwen3:8b"

    def test_llm_last_fallback_not_set_on_primary_success(self):
        """last_fallback remains None when primary model succeeds."""
        client = LLMClient.__new__(LLMClient)
        client.last_fallback = None
        expected = LLMResponse(content="primary result", model="qwen3.5:122b")
        with patch.object(client, "chat_with_retry", return_value=expected):
            result = client.chat_with_fallback("hi", tier="complex")
        assert result.content == "primary result"
        assert client.last_fallback is None


# --- Integration: Agent ---


class TestAgentIntegration:
    def test_agent_run_uses_fallback(self, tmp_path):
        with patch("merkaba.agent.SecurityScanner") as MockScanner:
            MockScanner.return_value.quick_scan.return_value = MagicMock(has_issues=False)
            from merkaba.agent import Agent
            agent = Agent(plugins_enabled=False, memory_storage_dir=str(tmp_path))
        agent.input_classifier.enabled = False

        expected = LLMResponse(content="hi!", model="qwen3:8b")
        # Primary fails, fallback succeeds
        agent.llm.chat_with_retry = MagicMock(
            side_effect=[LLMUnavailableError("primary down"), expected],
        )
        result = agent.run("hello")
        assert result == "hi!"
        # chat_with_retry was called twice (primary + fallback)
        assert agent.llm.chat_with_retry.call_count == 2

    def test_agent_returns_error_when_all_unavailable(self, tmp_path):
        with patch("merkaba.agent.SecurityScanner") as MockScanner:
            MockScanner.return_value.quick_scan.return_value = MagicMock(has_issues=False)
            from merkaba.agent import Agent
            agent = Agent(plugins_enabled=False, memory_storage_dir=str(tmp_path))
        agent.input_classifier.enabled = False

        agent.llm.chat_with_retry = MagicMock(
            side_effect=LLMUnavailableError("all down"),
        )
        result = agent.run("hello")
        assert "unable to reach" in result.lower()


# --- Integration: Worker ---


class TestWorkerIntegration:
    def test_worker_ask_llm_uses_fallback(self):
        from merkaba.orchestration.workers import HealthCheckWorker

        worker = HealthCheckWorker(business_id=1, model="test-model")
        llm_mock = MagicMock()
        expected = LLMResponse(content='{"status": "healthy"}', model="test-model")
        llm_mock.chat_with_fallback.return_value = expected
        worker._llm = llm_mock

        result = worker._ask_llm("test prompt")
        assert result == '{"status": "healthy"}'
        llm_mock.chat_with_fallback.assert_called_once()
        call_kwargs = llm_mock.chat_with_fallback.call_args
        assert call_kwargs.kwargs["tier"] == "complex"
