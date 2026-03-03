# tests/test_llm_providers.py
"""Tests for cloud LLM provider adapters and registry."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from merkaba.llm_providers.base import LLMProvider, ProviderResponse
from merkaba.llm_providers.registry import (
    clear_cache,
    get_configured_providers,
    is_cloud_model,
    resolve_provider,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Clear provider cache between tests."""
    clear_cache()
    yield
    clear_cache()


# --- ProviderResponse ---


class TestProviderResponse:
    def test_basic_response(self):
        r = ProviderResponse(content="hello", model="test")
        assert r.content == "hello"
        assert r.model == "test"
        assert r.tool_calls is None
        assert r.input_tokens == 0

    def test_response_with_tool_calls(self):
        r = ProviderResponse(
            content=None,
            model="test",
            tool_calls=[{"name": "web_search", "arguments": {"q": "test"}}],
        )
        assert r.tool_calls is not None
        assert r.tool_calls[0]["name"] == "web_search"


# --- Provider Registry ---


class TestProviderRegistry:
    def test_unprefixed_model_resolves_to_ollama(self):
        provider, model = resolve_provider("qwen3:8b")
        assert model == "qwen3:8b"
        assert provider is not None

    def test_ollama_tag_not_treated_as_cloud(self):
        provider, model = resolve_provider("qwen3.5:122b")
        assert model == "qwen3.5:122b"

    def test_anthropic_prefix_resolves(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"anthropic": {"api_key": "sk-ant-test"}}
        }))
        with patch.dict(sys.modules, {"anthropic": MagicMock()}):
            provider, model = resolve_provider(
                "anthropic:claude-sonnet-4-20250514", str(config)
            )
        assert model == "claude-sonnet-4-20250514"
        assert provider is not None

    def test_openai_prefix_resolves(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"openai": {"api_key": "sk-test"}}
        }))
        with patch.dict(sys.modules, {"openai": MagicMock()}):
            provider, model = resolve_provider("openai:gpt-4o", str(config))
        assert model == "gpt-4o"
        assert provider is not None

    def test_openrouter_prefix_resolves(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"openrouter": {
                "api_key": "sk-or-test",
                "base_url": "https://openrouter.ai/api/v1",
            }}
        }))
        with patch.dict(sys.modules, {"openai": MagicMock()}):
            provider, model = resolve_provider(
                "openrouter:meta-llama/llama-3-70b", str(config)
            )
        assert model == "meta-llama/llama-3-70b"
        assert provider is not None

    def test_custom_provider_resolves(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"together": {
                "api_key": "test-key",
                "base_url": "https://api.together.xyz/v1",
            }}
        }))
        with patch.dict(sys.modules, {"openai": MagicMock()}):
            provider, model = resolve_provider(
                "together:meta-llama/Llama-3-70b", str(config)
            )
        assert model == "meta-llama/Llama-3-70b"
        assert provider is not None

    def test_unknown_prefix_falls_to_ollama(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({}))
        provider, model = resolve_provider("unknownprefix:model", str(config))
        # Unknown prefix not in cloud_providers → treated as Ollama model name
        assert model == "unknownprefix:model"

    def test_missing_api_key_returns_none(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"cloud_providers": {"anthropic": {}}}))
        with patch.dict(os.environ, {}, clear=True):
            provider, model = resolve_provider(
                "anthropic:claude-sonnet-4-20250514", str(config)
            )
        assert provider is None
        assert model == "claude-sonnet-4-20250514"

    def test_env_var_api_key_fallback(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"cloud_providers": {"anthropic": {}}}))
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-key"}):
            with patch.dict(sys.modules, {"anthropic": MagicMock()}):
                provider, model = resolve_provider(
                    "anthropic:claude-sonnet-4-20250514", str(config)
                )
        assert provider is not None

    def test_missing_sdk_returns_none(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"anthropic": {"api_key": "sk-test"}}
        }))
        # Remove anthropic from sys.modules to simulate missing SDK
        with patch.dict(sys.modules, {"anthropic": None}):
            provider, model = resolve_provider(
                "anthropic:claude-sonnet-4-20250514", str(config)
            )
        assert provider is None


class TestIsCloudModel:
    def test_unprefixed_is_not_cloud(self):
        assert not is_cloud_model("qwen3:8b")

    def test_anthropic_is_cloud(self):
        assert is_cloud_model("anthropic:claude-sonnet-4-20250514")

    def test_openai_is_cloud(self):
        assert is_cloud_model("openai:gpt-4o")

    def test_openrouter_is_cloud(self):
        assert is_cloud_model("openrouter:meta-llama/llama-3-70b")

    def test_custom_prefix_is_cloud_when_configured(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"together": {"api_key": "k", "base_url": "https://x"}}
        }))
        assert is_cloud_model("together:model", str(config))

    def test_unknown_prefix_is_not_cloud(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({}))
        assert not is_cloud_model("randomprefix:model", str(config))


# --- Anthropic Provider ---


class TestAnthropicProvider:
    def test_chat_basic(self):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello!"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_client.messages.create.return_value = mock_response

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            from merkaba.llm_providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-test")
            provider._client = mock_client

            result = provider.chat(
                "claude-sonnet-4-20250514",
                [{"role": "user", "content": "Hi"}],
            )

        assert result.content == "Hello!"
        assert result.model == "claude-sonnet-4-20250514"
        assert result.input_tokens == 10
        assert result.output_tokens == 5

    def test_chat_with_tools(self):
        mock_client = MagicMock()

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "web_search"
        tool_block.input = {"query": "test"}

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage.input_tokens = 15
        mock_response.usage.output_tokens = 8
        mock_client.messages.create.return_value = mock_response

        with patch.dict(sys.modules, {"anthropic": MagicMock()}):
            from merkaba.llm_providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-test")
            provider._client = mock_client

            tools = [{"type": "function", "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }}]
            result = provider.chat(
                "claude-sonnet-4-20250514",
                [{"role": "user", "content": "Search for cats"}],
                tools=tools,
            )

        assert result.tool_calls is not None
        assert result.tool_calls[0]["name"] == "web_search"
        assert result.tool_calls[0]["arguments"] == {"query": "test"}

    def test_tool_schema_conversion(self):
        with patch.dict(sys.modules, {"anthropic": MagicMock()}):
            from merkaba.llm_providers.anthropic_provider import _convert_tools_to_anthropic

        ollama_tools = [{"type": "function", "function": {
            "name": "file_read",
            "description": "Read a file",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }}]
        result = _convert_tools_to_anthropic(ollama_tools)
        assert result[0]["name"] == "file_read"
        assert result[0]["description"] == "Read a file"
        assert result[0]["input_schema"]["type"] == "object"
        assert "path" in result[0]["input_schema"]["properties"]

    def test_system_message_extraction(self):
        with patch.dict(sys.modules, {"anthropic": MagicMock()}):
            from merkaba.llm_providers.anthropic_provider import _extract_system_message

        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ]
        system, filtered = _extract_system_message(messages)
        assert system == "You are helpful"
        assert len(filtered) == 1
        assert filtered[0]["role"] == "user"

    def test_system_message_extraction_no_system(self):
        with patch.dict(sys.modules, {"anthropic": MagicMock()}):
            from merkaba.llm_providers.anthropic_provider import _extract_system_message

        messages = [{"role": "user", "content": "Hi"}]
        system, filtered = _extract_system_message(messages)
        assert system is None
        assert len(filtered) == 1

    def test_is_available_with_valid_key(self):
        with patch.dict(sys.modules, {"anthropic": MagicMock()}):
            from merkaba.llm_providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key="sk-test")
            assert provider.is_available() is True

    def test_is_available_with_import_error(self):
        with patch.dict(sys.modules, {"anthropic": None}):
            # Can't even import, so we test at registry level
            pass  # Covered by registry tests


# --- OpenAI Provider ---


class TestOpenAIProvider:
    def test_chat_basic(self):
        mock_client = MagicMock()

        mock_message = MagicMock()
        mock_message.content = "Hello from GPT!"
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 12
        mock_usage.completion_tokens = 7

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4o"
        mock_response.usage = mock_usage
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(sys.modules, {"openai": MagicMock()}):
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            provider._client = mock_client

            result = provider.chat(
                "gpt-4o",
                [{"role": "user", "content": "Hi"}],
            )

        assert result.content == "Hello from GPT!"
        assert result.model == "gpt-4o"
        assert result.input_tokens == 12
        assert result.output_tokens == 7

    def test_chat_with_tools(self):
        mock_client = MagicMock()

        mock_tc = MagicMock()
        mock_tc.function.name = "web_search"
        mock_tc.function.arguments = '{"query": "cats"}'

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tc]

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(sys.modules, {"openai": MagicMock()}):
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            provider._client = mock_client

            tools = [{"type": "function", "function": {
                "name": "web_search",
                "description": "Search",
                "parameters": {"type": "object", "properties": {}},
            }}]
            result = provider.chat(
                "gpt-4o",
                [{"role": "user", "content": "Search"}],
                tools=tools,
            )

        assert result.tool_calls is not None
        assert result.tool_calls[0]["name"] == "web_search"
        assert result.tool_calls[0]["arguments"] == {"query": "cats"}

    def test_custom_base_url(self):
        mock_openai_mod = MagicMock()

        with patch.dict(sys.modules, {"openai": mock_openai_mod}):
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(
                api_key="sk-test",
                base_url="https://openrouter.ai/api/v1",
            )
            provider._get_client()

        mock_openai_mod.OpenAI.assert_called_once_with(
            api_key="sk-test",
            base_url="https://openrouter.ai/api/v1",
        )

    def test_tool_args_already_dict(self):
        mock_client = MagicMock()

        mock_tc = MagicMock()
        mock_tc.function.name = "test_tool"
        mock_tc.function.arguments = {"key": "value"}  # Already a dict

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tc]

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock(prompt_tokens=0, completion_tokens=0)
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(sys.modules, {"openai": MagicMock()}):
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            provider._client = mock_client

            result = provider.chat("gpt-4o", [{"role": "user", "content": "Hi"}])

        assert result.tool_calls[0]["arguments"] == {"key": "value"}

    def test_is_available(self):
        with patch.dict(sys.modules, {"openai": MagicMock()}):
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key="sk-test")
            assert provider.is_available() is True


# --- Cloud Fallback Integration ---


class TestCloudFallbackIntegration:
    def test_ollama_fails_cloud_succeeds(self):
        """When Ollama model fails, cloud fallback in the chain should be tried."""
        from merkaba.llm import LLMClient, LLMResponse, LLMUnavailableError, ModelTier

        client = LLMClient.__new__(LLMClient)

        custom_chains = {
            "complex": ModelTier(
                primary="qwen3.5:122b",
                fallbacks=["anthropic:claude-sonnet-4-20250514"],
            ),
        }

        # First call (ollama) fails, second call (anthropic) succeeds
        expected = LLMResponse(content="from cloud", model="claude-sonnet-4-20250514")
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=[LLMUnavailableError("ollama down"), expected],
        ) as mock_retry:
            with patch("merkaba.llm.load_fallback_chains", return_value=custom_chains):
                result = client.chat_with_fallback("hi", tier="complex")
            assert mock_retry.call_count == 2

        assert result.content == "from cloud"

    def test_cloud_model_in_chat_routes_to_provider(self, tmp_path):
        """LLMClient.chat() with cloud-prefixed model routes through provider."""
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"anthropic": {"api_key": "sk-test"}}
        }))

        mock_provider = MagicMock()
        mock_provider.chat.return_value = ProviderResponse(
            content="cloud response",
            model="claude-sonnet-4-20250514",
            input_tokens=10,
            output_tokens=5,
        )

        from merkaba.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.model = "qwen3:8b"

        with patch("merkaba.llm_providers.registry.CONFIG_PATH", str(config)):
            with patch(
                "merkaba.llm_providers.registry._get_provider",
                return_value=mock_provider,
            ):
                result = client.chat(
                    "Hello",
                    model_override="anthropic:claude-sonnet-4-20250514",
                )

        assert result.content == "cloud response"
        assert result.model == "claude-sonnet-4-20250514"
        assert result.input_tokens == 10

    def test_no_api_key_raises_unavailable(self, tmp_path):
        """Cloud model with no API key raises LLMUnavailableError."""
        config = tmp_path / "config.json"
        config.write_text(json.dumps({"cloud_providers": {"anthropic": {}}}))

        from merkaba.llm import LLMClient, LLMUnavailableError

        client = LLMClient.__new__(LLMClient)
        client.model = "qwen3:8b"

        with patch("merkaba.llm_providers.registry.CONFIG_PATH", str(config)):
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(LLMUnavailableError, match="Provider unavailable"):
                    client.chat(
                        "Hello",
                        model_override="anthropic:claude-sonnet-4-20250514",
                    )

    def test_all_fail_raises_all_unavailable(self):
        """When all models in chain fail, AllModelsUnavailableError is raised."""
        from merkaba.llm import AllModelsUnavailableError, LLMClient, LLMUnavailableError

        client = LLMClient.__new__(LLMClient)
        with patch.object(
            client,
            "chat_with_retry",
            side_effect=LLMUnavailableError("all down"),
        ):
            with pytest.raises(AllModelsUnavailableError):
                client.chat_with_fallback("hi", tier="complex")

    def test_select_best_available_with_cloud_fallback(self):
        """select_best_available picks cloud model when local models unavailable."""
        from merkaba.llm import LLMClient, ModelTier

        client = LLMClient.__new__(LLMClient)
        client.base_url = "http://localhost:11434"

        custom_chains = {
            "complex": ModelTier(
                primary="qwen3.5:122b",
                fallbacks=["anthropic:claude-sonnet-4-20250514"],
            ),
        }
        mock_provider = MagicMock()

        with patch.object(client, "get_available_models", return_value={"unrelated:model"}):
            with patch("merkaba.llm.load_fallback_chains", return_value=custom_chains):
                with patch(
                    "merkaba.llm_providers.registry._get_provider",
                    return_value=mock_provider,
                ):
                    result = client.select_best_available("complex")

        assert result == "anthropic:claude-sonnet-4-20250514"

    def test_token_recording_for_cloud_calls(self, tmp_path):
        """Token counts from cloud providers are recorded in token store."""
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"anthropic": {"api_key": "sk-test"}}
        }))

        mock_provider = MagicMock()
        mock_provider.chat.return_value = ProviderResponse(
            content="response",
            model="claude-sonnet-4-20250514",
            input_tokens=100,
            output_tokens=50,
        )

        from merkaba.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.model = "qwen3:8b"

        with patch("merkaba.llm_providers.registry.CONFIG_PATH", str(config)):
            with patch(
                "merkaba.llm_providers.registry._get_provider",
                return_value=mock_provider,
            ):
                result = client.chat(
                    "Hello",
                    model_override="anthropic:claude-sonnet-4-20250514",
                )

        assert result.input_tokens == 100
        assert result.output_tokens == 50


# --- GetConfiguredProviders ---


class TestGetConfiguredProviders:
    def test_returns_empty_when_no_config(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({}))
        with patch("merkaba.llm_providers.registry.CONFIG_PATH", str(config)):
            with patch.dict(os.environ, {}, clear=True):
                result = get_configured_providers(str(config))
        assert result == {}

    def test_returns_configured_providers(self, tmp_path):
        config = tmp_path / "config.json"
        config.write_text(json.dumps({
            "cloud_providers": {"anthropic": {"api_key": "sk-test"}}
        }))
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        with patch(
            "merkaba.llm_providers.registry._get_provider",
            return_value=mock_provider,
        ):
            result = get_configured_providers(str(config))
        assert result["anthropic"] is True


# --- API Key Keychain Resolution ---


class TestGetApiKeyKeychainResolution:
    """Tests for the updated _get_api_key() resolution order."""

    @pytest.mark.requires_keyring
    def test_get_api_key_keychain_priority(self):
        """Keychain key is preferred over env var when both are present."""
        from merkaba.llm_providers.registry import _get_api_key

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "sk-keychain-key"

        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-key"}):
                key = _get_api_key("anthropic", {})

        assert key == "sk-keychain-key"
        mock_keyring.get_password.assert_called_once_with("merkaba", "anthropic_api_key")

    @pytest.mark.requires_keyring
    def test_get_api_key_env_fallback(self):
        """Env var is used when keychain returns None."""
        from merkaba.llm_providers.registry import _get_api_key

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None

        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-env-openai"}):
                key = _get_api_key("openai", {})

        assert key == "sk-env-openai"

    @pytest.mark.requires_keyring
    def test_get_api_key_config_deprecation_warning(self, caplog):
        """Config.json key triggers deprecation warning when keychain and env are empty."""
        import logging
        from merkaba.llm_providers.registry import _get_api_key

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None

        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with patch.dict(os.environ, {}, clear=True):
                with caplog.at_level(logging.WARNING, logger="merkaba.llm_providers.registry"):
                    key = _get_api_key("anthropic", {"api_key": "sk-config-key"})

        assert key == "sk-config-key"
        assert "config.json" in caplog.text
        assert "merkaba security migrate-keys" in caplog.text

    def test_get_api_key_no_keyring(self):
        """Falls back to env var gracefully when keyring is not installed."""
        from merkaba.llm_providers.registry import _get_api_key

        # Simulate keyring not installed by raising ImportError on import
        original = sys.modules.get("keyring")
        try:
            sys.modules["keyring"] = None  # None causes ImportError on `import keyring`
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-env-fallback"}):
                key = _get_api_key("anthropic", {})
        finally:
            if original is None:
                sys.modules.pop("keyring", None)
            else:
                sys.modules["keyring"] = original

        assert key == "sk-env-fallback"

    @pytest.mark.requires_keyring
    def test_get_api_key_all_empty_returns_none(self):
        """Returns None when keychain, env var, and config are all empty."""
        from merkaba.llm_providers.registry import _get_api_key

        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None

        with patch.dict(sys.modules, {"keyring": mock_keyring}):
            with patch.dict(os.environ, {}, clear=True):
                key = _get_api_key("anthropic", {})

        assert key is None
