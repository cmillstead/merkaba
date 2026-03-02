# src/merkaba/protocols.py
"""Formal Protocol definitions for swappable subsystems.

These Protocols document the expected interfaces for key Merkaba components,
enabling type-safe dependency injection and alternative implementations.

Usage:
    from merkaba.protocols import MemoryBackend, VectorBackend, Observer

    def process(store: MemoryBackend) -> None:
        facts = store.get_facts(business_id=1)
        ...

Each Protocol is @runtime_checkable, so isinstance() checks work:
    assert isinstance(my_store, MemoryBackend)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MemoryBackend(Protocol):
    """Protocol for structured memory storage (implemented by MemoryStore).

    Covers the core CRUD operations for facts and decisions. Implementations
    may support additional methods (episodes, learnings, relationships, etc.)
    but these four are the minimum required interface.
    """

    def add_fact(
        self,
        business_id: int,
        category: str,
        key: str,
        value: str,
        confidence: int = 100,
        source: str | None = None,
        check_contradictions: bool = False,
    ) -> int: ...

    def get_facts(
        self,
        business_id: int,
        category: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]: ...

    def add_decision(
        self,
        business_id: int,
        action_type: str,
        decision: str,
        reasoning: str,
    ) -> int: ...

    def get_decisions(
        self,
        business_id: int,
        action_type: str | None = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class VectorBackend(Protocol):
    """Protocol for vector similarity search (implemented by VectorMemory).

    Mirrors the search and deletion interface used by MemoryRetrieval.
    Implementations should provide semantic search over facts, decisions,
    and learnings, plus the ability to remove vectors by ID.
    """

    def search_facts(
        self, query: str, business_id: int | None = None, limit: int = 5
    ) -> list[dict[str, Any]]: ...

    def search_decisions(
        self, query: str, business_id: int | None = None, limit: int = 5
    ) -> list[dict[str, Any]]: ...

    def search_learnings(
        self, query: str, limit: int = 5
    ) -> list[dict[str, Any]]: ...

    def delete_vectors(
        self, collection_name: str, ids: list[str]
    ) -> None: ...


@runtime_checkable
class Observer(Protocol):
    """Protocol for observability hooks.

    Implementations receive callbacks on LLM calls, tool invocations,
    and errors. Useful for logging, metrics, tracing, and diagnostics.
    """

    def on_llm_call(
        self, model: str, tokens_in: int, tokens_out: int, duration: float
    ) -> None: ...

    def on_tool_call(
        self, tool_name: str, arguments: dict, result: str, duration: float
    ) -> None: ...

    def on_error(
        self, component: str, error: Exception, context: dict | None = None
    ) -> None: ...


@runtime_checkable
class ConversationBackend(Protocol):
    """Protocol for conversation history storage (implemented by ConversationLog).

    Covers the append/read/persist cycle used by the agent loop.
    """

    def append(
        self, role: str, content: str, metadata: dict | None = None
    ) -> None: ...

    def get_history(
        self, limit: int | None = None
    ) -> list[dict]: ...

    def save(self) -> None: ...
