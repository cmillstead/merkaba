"""Cloud LLM provider adapters for Friday.

Supports Ollama (default), Anthropic, OpenAI, OpenRouter, and any
OpenAI-compatible API via configurable base_url.
"""

from friday.llm_providers.base import LLMProvider, ProviderResponse
from friday.llm_providers.registry import resolve_provider

__all__ = ["LLMProvider", "ProviderResponse", "resolve_provider"]
