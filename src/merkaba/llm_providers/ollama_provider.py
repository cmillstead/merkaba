"""Ollama provider — wraps the existing Ollama client."""

from __future__ import annotations

import logging
from typing import Any

from merkaba.llm_providers.base import LLMProvider, ProviderResponse

logger = logging.getLogger(__name__)


class OllamaProvider:
    """LLM provider backed by a local Ollama instance."""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import ollama
            self._client = ollama.Client(host=self.base_url)
        return self._client

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> ProviderResponse:
        client = self._get_client()

        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools

        response = client.chat(**kwargs)

        tool_calls = None
        if getattr(response.message, "tool_calls", None):
            tool_calls = [
                {"name": tc.function.name, "arguments": tc.function.arguments}
                for tc in response.message.tool_calls
            ]

        return ProviderResponse(
            content=response.message.content,
            model=response.model,
            tool_calls=tool_calls,
            input_tokens=getattr(response, "prompt_eval_count", 0) or 0,
            output_tokens=getattr(response, "eval_count", 0) or 0,
            duration_ms=int((getattr(response, "total_duration", 0) or 0) / 1_000_000),
        )

    def is_available(self) -> bool:
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            return True
        except Exception:
            return False
