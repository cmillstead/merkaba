# src/merkaba/memory/context_budget.py
"""Token estimation and context window budget tracking.

Provides lightweight heuristic token counting and budget allocation
for deciding when to compress conversation history. This is NOT for
billing — it's for threshold detection (are we near 80% of context?).
"""
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """Estimate token count using ~4 chars per token heuristic.

    Good enough for threshold detection — we're deciding when to
    compress, not billing. The 4-char heuristic is widely used and
    tracks within ~10% of real tokenizer counts for English text.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class ContextBudget:
    """Token budget allocation for a single LLM call.

    Tracks how tokens are distributed across system prompt, tool
    definitions, conversation history, and reserved response space.
    """

    max_total_tokens: int
    system_prompt_tokens: int = 0
    tool_definitions_tokens: int = 0
    conversation_history_tokens: int = 0
    reserved_for_response: int = 4096

    @property
    def available_for_history(self) -> int:
        """How many tokens remain for conversation history."""
        used = (
            self.system_prompt_tokens
            + self.tool_definitions_tokens
            + self.reserved_for_response
        )
        return max(0, self.max_total_tokens - used)

    @property
    def utilization(self) -> float:
        """Fraction of context window currently used (0.0 to 1.0+)."""
        if self.max_total_tokens <= 0:
            return 0.0
        used = (
            self.system_prompt_tokens
            + self.tool_definitions_tokens
            + self.conversation_history_tokens
        )
        return used / self.max_total_tokens


@dataclass
class ContextWindowConfig:
    """Configurable context management parameters.

    Used by the compression and trimming subsystems to decide when
    and how to reduce context window usage.
    """

    max_context_tokens: int = 128000
    head_chars: int = 1500
    tail_chars: int = 1500
    compaction_threshold: float = 0.80
