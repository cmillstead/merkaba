# tests/test_session_pool.py
import asyncio
import sys
import time
import threading
from unittest.mock import MagicMock

import pytest
from merkaba.orchestration.session_pool import SessionPool

# Ensure ollama mock is available
if "ollama" not in sys.modules:
    mock_ollama = MagicMock()
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})
    sys.modules["ollama"] = mock_ollama


def _make_pool(**kwargs):
    """Create a pool with mocked Agent creation."""
    pool = SessionPool(**kwargs)
    # Mock the agent factory so we don't need real LLM
    mock_agent = MagicMock()
    mock_agent.run.return_value = "response"
    pool._create_agent = MagicMock(return_value=mock_agent)
    return pool


def test_creates_agent_on_first_message():
    pool = _make_pool()
    pool.submit_sync("web:user1", "hello")
    assert "web:user1" in pool._agents
    pool._create_agent.assert_called_once()


def test_reuses_agent_on_subsequent_messages():
    pool = _make_pool()
    pool.submit_sync("web:user1", "hello")
    pool.submit_sync("web:user1", "world")
    pool._create_agent.assert_called_once()


def test_different_sessions_get_different_agents():
    pool = _make_pool()
    pool.submit_sync("web:user1", "hello")
    pool.submit_sync("web:user2", "hello")
    assert pool._create_agent.call_count == 2


def test_max_sessions_evicts_oldest():
    pool = _make_pool(max_sessions=2)
    pool.submit_sync("s1", "a")
    pool.submit_sync("s2", "b")
    pool.submit_sync("s3", "c")  # Should evict s1
    assert "s1" not in pool._agents
    assert "s2" in pool._agents
    assert "s3" in pool._agents


def test_idle_timeout_evicts():
    pool = _make_pool(idle_timeout=0.1)
    pool.submit_sync("s1", "hello")
    time.sleep(0.15)
    pool.evict_idle()
    assert "s1" not in pool._agents


def test_serial_within_session():
    """Verify LaneQueue integration -- same session serializes."""
    pool = _make_pool()
    execution_order = []

    def slow_run(msg, **kwargs):
        execution_order.append(f"start:{msg}")
        time.sleep(0.05)
        execution_order.append(f"end:{msg}")
        return msg

    pool._create_agent.return_value.run.side_effect = slow_run

    threads = [
        threading.Thread(target=pool.submit_sync, args=("s1", f"msg{i}"))
        for i in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify serial execution
    starts = [i for i, x in enumerate(execution_order) if x.startswith("start:")]
    ends = [i for i, x in enumerate(execution_order) if x.startswith("end:")]
    for s, e in zip(starts[1:], ends[:-1]):
        assert s > e


def test_active_session_count():
    pool = _make_pool()
    assert pool.active_session_count() == 0
    pool.submit_sync("s1", "hello")
    assert pool.active_session_count() == 1
    pool.submit_sync("s2", "hello")
    assert pool.active_session_count() == 2


@pytest.mark.asyncio
async def test_async_submit():
    pool = _make_pool()
    result = await pool.submit("web:user1", "hello")
    assert result == "response"
