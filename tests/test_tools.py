# tests/test_tools.py
import pytest
from merkaba.tools.base import Tool, ToolResult, PermissionTier
from merkaba.tools.registry import ToolRegistry


def test_permission_tier_ordering():
    assert PermissionTier.SAFE < PermissionTier.MODERATE
    assert PermissionTier.MODERATE < PermissionTier.SENSITIVE
    assert PermissionTier.SENSITIVE < PermissionTier.DESTRUCTIVE


def test_tool_definition():
    def my_func(x: int) -> int:
        return x * 2

    tool = Tool(
        name="double",
        description="Doubles a number",
        function=my_func,
        permission_tier=PermissionTier.SAFE,
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
    )
    assert tool.name == "double"
    assert tool.permission_tier == PermissionTier.SAFE


def test_tool_execution():
    def my_func(x: int) -> int:
        return x * 2

    tool = Tool(
        name="double",
        description="Doubles a number",
        function=my_func,
        permission_tier=PermissionTier.SAFE,
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
    )
    result = tool.execute(x=5)
    assert result.success is True
    assert result.output == 10


def test_tool_registry():
    registry = ToolRegistry()

    def my_func(x: int) -> int:
        return x * 2

    tool = Tool(
        name="double",
        description="Doubles a number",
        function=my_func,
        permission_tier=PermissionTier.SAFE,
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
    )

    registry.register(tool)
    assert registry.get("double") is tool
    assert "double" in registry.list_tools()


def test_registry_to_ollama_format():
    registry = ToolRegistry()

    def my_func(x: int) -> int:
        return x * 2

    tool = Tool(
        name="double",
        description="Doubles a number",
        function=my_func,
        permission_tier=PermissionTier.SAFE,
        parameters={
            "type": "object",
            "properties": {"x": {"type": "integer"}},
            "required": ["x"],
        },
    )

    registry.register(tool)
    ollama_tools = registry.to_ollama_format()

    assert len(ollama_tools) == 1
    assert ollama_tools[0]["type"] == "function"
    assert ollama_tools[0]["function"]["name"] == "double"
