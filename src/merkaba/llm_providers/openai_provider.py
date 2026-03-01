"""OpenAI-compatible provider — covers OpenAI, OpenRouter, Together, Groq, etc."""

from __future__ import annotations

import json
import logging
from typing import Any

from friday.llm_providers.base import ProviderResponse

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """LLM provider for OpenAI and any OpenAI-compatible API.

    Set base_url to use OpenRouter, Together, Groq, or any compatible endpoint.
    """

    def __init__(self, api_key: str, base_url: str | None = None):
        self._api_key = api_key
        self._base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import openai
            kwargs: dict[str, Any] = {"api_key": self._api_key}
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = openai.OpenAI(**kwargs)
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

        response = client.chat.completions.create(**kwargs)

        choice = response.choices[0]
        message = choice.message

        tool_calls = None
        if message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                tool_calls.append({"name": tc.function.name, "arguments": args})

        usage = response.usage

        return ProviderResponse(
            content=message.content,
            model=response.model,
            tool_calls=tool_calls,
            input_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )

    def is_available(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False
