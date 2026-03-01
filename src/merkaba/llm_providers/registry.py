"""Provider registry — resolves model names to provider instances."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from merkaba.llm_providers.base import LLMProvider, ProviderResponse

logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.expanduser("~/.merkaba/config.json")

# Cached provider instances (lazy-init)
_providers: dict[str, LLMProvider] = {}


def _load_cloud_config(config_path: str = CONFIG_PATH) -> dict[str, dict[str, str]]:
    """Load cloud_providers section from config.json."""
    try:
        with open(config_path) as f:
            data = json.load(f)
        return data.get("cloud_providers", {})
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return {}


def _get_api_key(provider_name: str, provider_config: dict[str, str]) -> str | None:
    """Get API key from config or environment variable."""
    key = provider_config.get("api_key")
    if key:
        return key
    env_var = f"{provider_name.upper()}_API_KEY"
    return os.environ.get(env_var)


def _get_provider(prefix: str, config_path: str = CONFIG_PATH) -> LLMProvider | None:
    """Get or create a provider instance for the given prefix."""
    if prefix in _providers:
        return _providers[prefix]

    cloud_config = _load_cloud_config(config_path)

    provider: LLMProvider | None = None

    if prefix == "ollama":
        from merkaba.llm_providers.ollama_provider import OllamaProvider
        provider = OllamaProvider()
        _providers[prefix] = provider
        return provider

    if prefix == "anthropic":
        api_key = _get_api_key("anthropic", cloud_config.get("anthropic", {}))
        if not api_key:
            logger.debug("No API key for anthropic provider")
            return None
        try:
            import anthropic as _  # noqa: F811 — verify SDK is installed
            from merkaba.llm_providers.anthropic_provider import AnthropicProvider
            provider = AnthropicProvider(api_key=api_key)
        except (ImportError, ModuleNotFoundError):
            logger.debug("anthropic package not installed")
            return None
        _providers[prefix] = provider
        return provider

    if prefix == "openai":
        api_key = _get_api_key("openai", cloud_config.get("openai", {}))
        if not api_key:
            logger.debug("No API key for openai provider")
            return None
        try:
            import openai as _  # noqa: F811 — verify SDK is installed
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key=api_key)
        except (ImportError, ModuleNotFoundError):
            logger.debug("openai package not installed")
            return None
        _providers[prefix] = provider
        return provider

    if prefix == "openrouter":
        config = cloud_config.get("openrouter", {})
        api_key = _get_api_key("openrouter", config)
        if not api_key:
            logger.debug("No API key for openrouter provider")
            return None
        base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        try:
            import openai as _  # noqa: F811 — verify SDK is installed
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key=api_key, base_url=base_url)
        except (ImportError, ModuleNotFoundError):
            logger.debug("openai package not installed")
            return None
        _providers[prefix] = provider
        return provider

    # Custom prefix — look for it in cloud_providers config
    if prefix in cloud_config:
        config = cloud_config[prefix]
        api_key = _get_api_key(prefix, config)
        base_url = config.get("base_url")
        if not api_key:
            logger.debug("No API key for custom provider '%s'", prefix)
            return None
        if not base_url:
            logger.debug("No base_url for custom provider '%s'", prefix)
            return None
        try:
            import openai as _  # noqa: F811 — verify SDK is installed
            from merkaba.llm_providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(api_key=api_key, base_url=base_url)
        except (ImportError, ModuleNotFoundError):
            logger.debug("openai package not installed")
            return None
        _providers[prefix] = provider
        return provider

    return None


def resolve_provider(
    model_name: str, config_path: str = CONFIG_PATH
) -> tuple[LLMProvider | None, str]:
    """Resolve a model name to (provider, actual_model_name).

    Model name convention:
        "qwen3:8b"           → Ollama, model="qwen3:8b"
        "anthropic:claude-sonnet-4-20250514" → Anthropic, model="claude-sonnet-4-20250514"
        "openai:gpt-4o"      → OpenAI, model="gpt-4o"
        "openrouter:meta-llama/llama-3-70b" → OpenRouter, model="meta-llama/llama-3-70b"
        "together:meta-llama/Llama-3-70b" → custom, model="meta-llama/Llama-3-70b"

    Returns (None, model_name) if the provider can't be created (missing SDK/key).
    Unprefixed models always resolve to Ollama.
    """
    known_prefixes = {"anthropic", "openai", "openrouter"}

    # Check for prefix
    if ":" in model_name:
        prefix, _, actual_model = model_name.partition(":")

        # Ollama models use colons for tags (e.g. "qwen3:8b")
        # Only treat as cloud prefix if it's a known prefix or in cloud_providers config
        cloud_config = _load_cloud_config(config_path)
        if prefix in known_prefixes or prefix in cloud_config:
            provider = _get_provider(prefix, config_path)
            return provider, actual_model

    # No prefix or unknown prefix — use Ollama
    provider = _get_provider("ollama", config_path)
    return provider, model_name


def is_cloud_model(model_name: str, config_path: str = CONFIG_PATH) -> bool:
    """Check if a model name refers to a cloud provider."""
    if ":" not in model_name:
        return False
    prefix = model_name.split(":")[0]
    known = {"anthropic", "openai", "openrouter"}
    if prefix in known:
        return True
    cloud_config = _load_cloud_config(config_path)
    return prefix in cloud_config


def get_configured_providers(config_path: str = CONFIG_PATH) -> dict[str, bool]:
    """Return a dict of provider_name → is_available for all configured cloud providers."""
    cloud_config = _load_cloud_config(config_path)
    result: dict[str, bool] = {}

    for name in cloud_config:
        provider = _get_provider(name, config_path)
        result[name] = provider is not None and provider.is_available()

    # Also check env-var-only providers
    for name in ("anthropic", "openai", "openrouter"):
        if name not in result:
            env_key = os.environ.get(f"{name.upper()}_API_KEY")
            if env_key:
                provider = _get_provider(name, config_path)
                result[name] = provider is not None and provider.is_available()

    return result


def clear_cache() -> None:
    """Clear cached provider instances. For use in tests."""
    _providers.clear()
