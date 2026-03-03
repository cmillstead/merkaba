# tests/test_agent.py
import tempfile
import pytest
from unittest.mock import Mock, MagicMock, patch

# Check if required dependencies are available
try:
    from merkaba.agent import Agent
    from merkaba.llm import LLMResponse, ToolCall
    from merkaba.tools.base import PermissionTier
    from merkaba.security.scanner import SecurityReport
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)
    Agent = None
    LLMResponse = None
    ToolCall = None
    PermissionTier = None
    SecurityReport = None

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


@pytest.fixture
def temp_memory_dir():
    """Provide a temporary directory for memory storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_agent_initialization(temp_memory_dir):
    agent = Agent(memory_storage_dir=temp_memory_dir)
    assert agent.llm is not None
    assert agent.registry is not None
    assert agent.memory is not None


def test_agent_has_builtin_tools(temp_memory_dir):
    agent = Agent(memory_storage_dir=temp_memory_dir)
    tools = agent.registry.list_tools()
    assert "file_read" in tools
    assert "file_write" in tools
    assert "file_list" in tools


def test_agent_processes_simple_response(temp_memory_dir):
    agent = Agent(memory_storage_dir=temp_memory_dir)

    with patch.object(agent.llm, "chat_with_fallback") as mock_chat:
        mock_chat.return_value = LLMResponse(
            content="Hello! I'm Merkaba.",
            model="test",
            tool_calls=None,
        )

        response = agent.run("Hello")
        assert "Hello" in response or "Merkaba" in response


def test_agent_executes_tool_calls(temp_memory_dir):
    agent = Agent(memory_storage_dir=temp_memory_dir)

    # First call returns tool use, second returns final response
    call_count = 0

    def mock_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LLMResponse(
                content=None,
                model="test",
                tool_calls=[
                    ToolCall(name="file_list", arguments={"path": "/tmp"})
                ],
            )
        else:
            return LLMResponse(
                content="I listed the /tmp directory for you.",
                model="test",
                tool_calls=None,
            )

    with patch.object(agent.llm, "chat_with_fallback", side_effect=mock_chat):
        response = agent.run("List the /tmp directory")
        assert call_count == 2  # Tool call + final response


def test_agent_hits_iteration_limit(temp_memory_dir):
    agent = Agent(max_iterations=2, memory_storage_dir=temp_memory_dir)

    # Always return tool calls, never a final response
    def always_tool_call(*args, **kwargs):
        return LLMResponse(
            content=None,
            model="test",
            tool_calls=[ToolCall(name="file_list", arguments={"path": "/tmp"})],
        )

    with patch.object(agent.llm, "chat", side_effect=always_tool_call):
        response = agent.run("Do something")
        assert "iteration limit" in response.lower()


def test_agent_has_permission_manager(temp_memory_dir):
    """Test that Agent has a PermissionManager initialized."""
    agent = Agent(memory_storage_dir=temp_memory_dir)
    assert agent.permission_manager is not None


def test_agent_permission_denial_in_tool_execution(temp_memory_dir):
    """Test that permission denial is handled in tool execution."""
    agent = Agent(memory_storage_dir=temp_memory_dir)

    # Set auto_approve_level to a level below MODERATE to deny file_write
    # file_write has MODERATE tier, so setting to SAFE will deny it
    agent.permission_manager.auto_approve_level = PermissionTier.SAFE

    # First call returns tool use for file_write, second returns final response
    call_count = 0

    def mock_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LLMResponse(
                content=None,
                model="test",
                tool_calls=[
                    ToolCall(
                        name="file_write",
                        arguments={"path": "/tmp/test.txt", "content": "test"}
                    )
                ],
            )
        else:
            return LLMResponse(
                content="The write operation was denied.",
                model="test",
                tool_calls=None,
            )

    with patch.object(agent.llm, "chat_with_fallback", side_effect=mock_chat):
        response = agent.run("Write a file")
        # Check that conversation includes permission denied message
        tool_result = next(
            (msg for msg in agent.conversation if msg["role"] == "tool"),
            None
        )
        assert tool_result is not None
        assert "Permission denied" in tool_result["content"]


def test_agent_has_core_tools(temp_memory_dir):
    """Test that Agent has core framework tools registered."""
    agent = Agent(memory_storage_dir=temp_memory_dir)
    tools = agent.registry.list_tools()
    assert "file_read" in tools
    assert "file_write" in tools
    assert "bash" in tools
    assert "memory_search" in tools


def test_agent_runs_security_check_on_init():
    """Agent should run security quick scan on initialization."""
    with patch("merkaba.agent.SecurityScanner") as MockScanner:
        mock_scanner = MagicMock()
        mock_scanner.quick_scan.return_value = SecurityReport()
        MockScanner.return_value = mock_scanner

        agent = Agent(plugins_enabled=False)

        mock_scanner.quick_scan.assert_called_once()


def test_agent_encryption_key_from_keychain(temp_memory_dir):
    """Encryption key from keychain is wired into ConversationLog.encryptor."""
    import sys
    from merkaba.security.encryption import ConversationEncryptor

    mock_encryptor = MagicMock(spec=ConversationEncryptor)

    with patch("merkaba.security.encryption.ConversationEncryptor.from_keychain",
               return_value=mock_encryptor):
        agent = Agent(memory_storage_dir=temp_memory_dir, plugins_enabled=False)

    assert agent.memory.encryptor is mock_encryptor


def test_agent_encryption_no_keyring(temp_memory_dir):
    """Agent initializes without error when keyring is not installed."""
    import sys

    # Simulate ImportError raised inside from_keychain by having it return None
    # (the actual from_keychain already swallows ImportError and returns None)
    with patch("merkaba.security.encryption.ConversationEncryptor.from_keychain",
               return_value=None):
        agent = Agent(memory_storage_dir=temp_memory_dir, plugins_enabled=False)

    # No encryptor set — should default to None
    assert agent.memory.encryptor is None


def test_agent_encryption_exception_is_non_fatal(temp_memory_dir):
    """Agent continues initialization even if encryption wiring raises."""
    with patch("merkaba.security.encryption.ConversationEncryptor.from_keychain",
               side_effect=RuntimeError("keychain unavailable")):
        # Should not raise
        agent = Agent(memory_storage_dir=temp_memory_dir, plugins_enabled=False)

    assert agent.memory is not None
