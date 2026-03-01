"""Base types for LLM provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ProviderResponse:
    """Normalized response from any LLM provider."""

    content: str | None
    model: str
    tool_calls: list[dict[str, Any]] | None = None  # [{name, arguments}]
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM provider backends."""

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> ProviderResponse:
        """Send messages and return a normalized response."""
        ...

    def is_available(self) -> bool:
        """Check whether this provider is reachable and configured."""
        ...
