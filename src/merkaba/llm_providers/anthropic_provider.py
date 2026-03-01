"""Anthropic provider — Claude models via the Anthropic SDK."""

from __future__ import annotations

import logging
from typing import Any

from friday.llm_providers.base import ProviderResponse

logger = logging.getLogger(__name__)


def _convert_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert Ollama/OpenAI tool format to Anthropic format.

    Ollama: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
    Anthropic: {"name": ..., "description": ..., "input_schema": ...}
    """
    converted = []
    for tool in tools:
        func = tool.get("function", tool)
        converted.append({
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        })
    return converted


def _extract_system_message(messages: list[dict[str, str]]) -> tuple[str | None, list[dict]]:
    """Separate system message from conversation messages.

    Anthropic requires system as a separate parameter, not in messages.
    """
    system = None
    filtered = []
    for msg in messages:
        if msg.get("role") == "system":
            system = msg.get("content", "")
        else:
            filtered.append(msg)
    return system, filtered


class AnthropicProvider:
    """LLM provider backed by the Anthropic API."""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> ProviderResponse:
        client = self._get_client()

        system, filtered_messages = _extract_system_message(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "messages": filtered_messages,
            "max_tokens": 4096,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _convert_tools_to_anthropic(tools)

        response = client.messages.create(**kwargs)

        # Extract text content and tool use blocks
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                content_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "arguments": block.input,
                })

        content = "\n".join(content_parts) if content_parts else None

        return ProviderResponse(
            content=content,
            model=response.model,
            tool_calls=tool_calls if tool_calls else None,
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )

    def is_available(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False
