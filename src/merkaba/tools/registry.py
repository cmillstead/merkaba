# src/merkaba/tools/registry.py
from merkaba.tools.base import Tool


class ToolRegistry:
    """Registry for managing available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def to_ollama_format(self) -> list[dict]:
        """Convert all tools to Ollama format."""
        return [tool.to_ollama_format() for tool in self._tools.values()]
