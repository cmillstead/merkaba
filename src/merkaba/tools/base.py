# src/merkaba/tools/base.py
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable
import traceback


class PermissionTier(IntEnum):
    """Permission levels for tool execution."""

    SAFE = 0  # Read-only, no side effects
    MODERATE = 1  # Write files, local APIs
    SENSITIVE = 2  # Shell commands, external APIs
    DESTRUCTIVE = 3  # Delete, publish, spend money


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: Any
    error: str | None = None


@dataclass
class Tool:
    """Definition of an agent tool."""

    name: str
    description: str
    function: Callable
    permission_tier: PermissionTier
    parameters: dict[str, Any]
    allowed_paths: list[str] = field(default_factory=list)

    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""
        try:
            result = self.function(**kwargs)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(
                success=False,
                output=None,
                error=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}",
            )

    def to_ollama_format(self) -> dict:
        """Convert to Ollama tool format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
