# tests/test_agent_interruption.py
"""Tests for interruption integration in agent tool execution."""

import tempfile
import pytest
from unittest.mock import MagicMock, patch

try:
    from merkaba.agent import Agent
    from merkaba.tools.base import Tool, ToolResult, PermissionTier
    from merkaba.memory import ConversationTree
    from merkaba.tools.registry import ToolRegistry
    from merkaba.orchestration.interruption import InterruptionManager, InterruptionMode
    HAS_DEPENDENCIES = True
except ImportError as e:
    HAS_DEPENDENCIES = False
    IMPORT_ERROR = str(e)

pytestmark = pytest.mark.skipif(
    not HAS_DEPENDENCIES,
    reason=f"Missing required dependencies: {IMPORT_ERROR if not HAS_DEPENDENCIES else ''}"
)


def _make_agent():
    """Create a minimal Agent for testing _execute_tools.

    Bypasses __post_init__ (which spins up LLM, memory, etc.) by using
    __new__ and setting only the fields that _execute_tools touches.
    """
    agent = Agent.__new__(Agent)
    agent.session_id = None
    agent.interruption_mgr = None
    agent.registry = ToolRegistry()
    agent.permission_manager = MagicMock()
    agent.active_skill = None
    agent._verifier = MagicMock()
    agent._verifier.enabled = False
    agent._tree = ConversationTree()
    agent._tree.append("user", "hello")
    return agent


def _make_tool(name="test_tool", output="ok"):
    """Create a real Tool object that returns a successful result."""
    def fn(**kwargs):
        return output
    return Tool(
        name=name,
        description=f"Test tool {name}",
        function=fn,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )


def _make_tool_call(name="test_tool", arguments=None):
    """Create a mock tool call (mimics ToolCall from LLM response)."""
    tc = MagicMock()
    tc.name = name
    tc.arguments = arguments or {}
    return tc


# --- Agent field tests ---


def test_agent_has_session_id_field():
    """Agent dataclass must have session_id, default None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = Agent(memory_storage_dir=tmpdir)
        assert agent.session_id is None


def test_agent_has_interruption_mgr_field():
    """Agent dataclass must have interruption_mgr, default None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = Agent(memory_storage_dir=tmpdir)
        assert agent.interruption_mgr is None


# --- No interruption (baseline) ---


def test_no_interruption_executes_normally():
    """Without interruption manager, tools execute normally."""
    agent = _make_agent()
    agent.registry.register(_make_tool("test_tool", "ok"))

    tc = _make_tool_call("test_tool")
    result = agent._execute_tools([tc])
    assert "ok" in result


# --- CANCEL interruption ---


def test_cancel_interruption_stops_execution():
    """CANCEL interruption stops tool execution and returns message."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    mgr.interrupt("test:user1", "Stop everything", InterruptionMode.CANCEL)

    # Register a tool that tracks whether it was called
    call_tracker = MagicMock()
    def fn(**kwargs):
        call_tracker()
        return "should not run"
    tool = Tool(
        name="test_tool",
        description="test",
        function=fn,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool)

    tc = _make_tool_call("test_tool")
    result = agent._execute_tools([tc])
    assert "[interrupted]" in result
    assert "Cancelled" in result
    call_tracker.assert_not_called()


# --- STEER interruption ---


def test_steer_interruption_injects_message():
    """STEER interruption injects message into tree and returns."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    mgr.interrupt("test:user1", "Actually do X instead", InterruptionMode.STEER)

    # Tool should not execute
    call_tracker = MagicMock()
    def fn(**kwargs):
        call_tracker()
        return "should not run"
    tool = Tool(
        name="test_tool",
        description="test",
        function=fn,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool)

    tc = _make_tool_call("test_tool")
    result = agent._execute_tools([tc])
    assert "[interrupted]" in result
    assert "New direction" in result
    call_tracker.assert_not_called()

    # Check the tree got the steer message
    branch = agent._tree.get_active_branch()
    steer_msgs = [
        m for m in branch
        if m.role == "user" and "Actually do X instead" in (m.content or "")
    ]
    assert len(steer_msgs) == 1


# --- APPEND interruption ---


def test_append_interruption_continues_execution():
    """APPEND interruption does not stop execution — tool still runs."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    mgr.interrupt("test:user1", "Also do Y later", InterruptionMode.APPEND)

    agent.registry.register(_make_tool("test_tool", "done"))

    tc = _make_tool_call("test_tool")
    result = agent._execute_tools([tc])
    # Tool should still execute
    assert "done" in result


def test_append_event_preserved_after_execute_tools():
    """APPEND events are NOT consumed by _execute_tools — still in queue."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    mgr.interrupt("test:user1", "Also do Y later", InterruptionMode.APPEND)

    agent.registry.register(_make_tool("test_tool", "done"))

    tc = _make_tool_call("test_tool")
    result = agent._execute_tools([tc])
    assert "done" in result

    # APPEND event should still be in the queue for the submission layer
    event = mgr.check("test:user1")
    assert event is not None
    assert event.mode == InterruptionMode.APPEND
    assert event.message == "Also do Y later"


# --- Multi-tool interruption ---


def test_cancel_before_second_tool():
    """CANCEL between two tool calls stops after the first."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    # tool1 queues a CANCEL during its execution
    def fn1(**kwargs):
        mgr.interrupt("test:user1", "Cancel now", InterruptionMode.CANCEL)
        return "first done"

    tool1 = Tool(
        name="tool1",
        description="first tool",
        function=fn1,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool1)

    call_tracker2 = MagicMock()
    def fn2(**kwargs):
        call_tracker2()
        return "second done"

    tool2 = Tool(
        name="tool2",
        description="second tool",
        function=fn2,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool2)

    tc1 = _make_tool_call("tool1")
    tc2 = _make_tool_call("tool2")

    result = agent._execute_tools([tc1, tc2])
    # tool1 should have run
    assert "first done" in result
    # tool2 should NOT have run
    call_tracker2.assert_not_called()
    assert "Cancelled" in result


# --- No session_id means no interruption check ---


def test_no_session_id_skips_interruption_check():
    """When session_id is None, interruptions are not checked."""
    agent = _make_agent()
    agent.session_id = None
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    # Queue a CANCEL for some session — should be irrelevant
    mgr.interrupt("test:user1", "Cancel", InterruptionMode.CANCEL)

    agent.registry.register(_make_tool("test_tool", "ran fine"))

    tc = _make_tool_call("test_tool")
    result = agent._execute_tools([tc])
    assert "ran fine" in result


# --- Steer between tools ---


def test_steer_before_second_tool():
    """STEER interruption between two tool calls aborts remaining tools."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    def fn1(**kwargs):
        mgr.interrupt("test:user1", "New goal", InterruptionMode.STEER)
        return "first result"

    tool1 = Tool(
        name="tool1",
        description="first tool",
        function=fn1,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool1)

    call_tracker2 = MagicMock()
    def fn2(**kwargs):
        call_tracker2()
        return "second result"

    tool2 = Tool(
        name="tool2",
        description="second tool",
        function=fn2,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool2)

    tc1 = _make_tool_call("tool1")
    tc2 = _make_tool_call("tool2")

    result = agent._execute_tools([tc1, tc2])
    assert "first result" in result
    assert "New direction" in result
    call_tracker2.assert_not_called()


# --- CANCEL prunes partial branch in run() ---


def test_cancel_in_run_does_not_append_partial_results():
    """When CANCEL fires mid-tool, run() should NOT append partial tool
    results to the tree. Instead it injects the cancel message as a user
    message and re-enters the loop."""
    agent = _make_agent()
    agent.session_id = "test:user1"
    mgr = InterruptionManager()
    agent.interruption_mgr = mgr

    # We need to mock the parts of run() that _make_agent skips:
    # llm, memory, input_classifier, retrieval, context_config, etc.
    agent.llm = MagicMock()
    agent.memory = MagicMock()
    agent.memory.append = MagicMock()
    agent.memory.save = MagicMock()
    agent.input_classifier = MagicMock()
    agent.input_classifier.classify.return_value = (True, None, "complex")
    agent.retrieval = None
    agent.active_business_id = None
    agent.plugins_enabled = False
    agent.plugin_registry = None
    agent.active_skill = None
    agent.extra_context = None
    agent.prompt_dir = None
    agent._prompt_loader = MagicMock()
    agent._prompt_loader.load.return_value = ("soul", "user")
    agent.context_config = MagicMock()
    agent.context_config.head_chars = 2000
    agent.context_config.tail_chars = 1000
    agent.context_config.target_tokens = 8000
    agent.context_config.max_tokens = 16000
    agent.max_iterations = 3

    # Register a tool that queues CANCEL during execution
    def fn(**kwargs):
        mgr.interrupt("test:user1", "Do something else", InterruptionMode.CANCEL)
        return "partial result"

    tool = Tool(
        name="test_tool",
        description="test",
        function=fn,
        permission_tier=PermissionTier.SAFE,
        parameters={},
    )
    agent.registry.register(tool)

    # First LLM response: tool call that triggers CANCEL
    tc = MagicMock()
    tc.name = "test_tool"
    tc.arguments = {}

    first_response = MagicMock()
    first_response.tool_calls = [tc]
    first_response.model = "test-model"

    # Second LLM response: final text (after cancel re-enters loop)
    second_response = MagicMock()
    second_response.tool_calls = None
    second_response.content = "OK, doing something else now."
    second_response.model = "test-model"

    agent.llm.chat_with_fallback = MagicMock(side_effect=[first_response, second_response])

    # Mock compression check (local import in run(), patch at source)
    with patch("merkaba.memory.compression.should_compress", return_value=False):
        result = agent.run("original request")

    assert result == "OK, doing something else now."

    # Verify the tree does NOT contain any "tool" role messages with partial results
    branch = agent._tree.get_active_branch()
    tool_msgs = [m for m in branch if m.role == "tool"]
    assert len(tool_msgs) == 0, "CANCEL should prevent partial tool results from being appended to tree"

    # Verify the cancel message was injected as a user message
    user_msgs = [m for m in branch if m.role == "user"]
    cancel_user_msgs = [m for m in user_msgs if "Do something else" in (m.content or "")]
    assert len(cancel_user_msgs) == 1, "Cancel message should be injected as user message"
