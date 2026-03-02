# tests/test_session_pool.py
import asyncio
import sys
import time
import threading
from unittest.mock import MagicMock

import pytest
from merkaba.orchestration.session_pool import SessionPool, PAIRING_PROMPT
from merkaba.security.pairing import GatewayPairing

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


# --- Gateway pairing integration ---


def test_cli_bypasses_pairing():
    """CLI sessions are always trusted, even when pairing is configured."""
    gp = GatewayPairing()
    pool = _make_pool(pairing=gp)
    result = pool.submit_sync("cli:local", "hello")
    assert result == "response"
    pool._create_agent.assert_called_once()


def test_unpaired_telegram_returns_prompt():
    """Unpaired non-CLI sessions receive a pairing prompt."""
    gp = GatewayPairing()
    pool = _make_pool(pairing=gp)
    result = pool.submit_sync("telegram:user1", "hello")
    assert result == PAIRING_PROMPT
    pool._create_agent.assert_not_called()


def test_paired_telegram_proceeds():
    """After pairing, non-CLI sessions process messages normally."""
    gp = GatewayPairing()
    code = gp.initiate("telegram", "telegram:user1")
    gp.confirm("telegram:user1", code)

    pool = _make_pool(pairing=gp)
    result = pool.submit_sync("telegram:user1", "hello")
    assert result == "response"
    pool._create_agent.assert_called_once()


def test_no_pairing_configured_allows_all():
    """Without pairing configured (None), all sessions proceed."""
    pool = _make_pool(pairing=None)
    result = pool.submit_sync("telegram:user1", "hello")
    assert result == "response"


def test_unpaired_web_returns_prompt():
    """Web sessions also require pairing when configured."""
    gp = GatewayPairing()
    pool = _make_pool(pairing=gp)
    result = pool.submit_sync("web:user1", "hello")
    assert result == PAIRING_PROMPT


def test_unpaired_does_not_create_agent():
    """An unpaired session should not allocate an agent."""
    gp = GatewayPairing()
    pool = _make_pool(pairing=gp)
    pool.submit_sync("discord:user1", "hello")
    assert pool.active_session_count() == 0


def test_pairing_with_complex_session_id():
    """Pairing works with full session IDs containing topic and biz segments."""
    gp = GatewayPairing()
    session_id = "telegram:user1:topic:42:biz:etsy"
    code = gp.initiate("telegram", session_id)
    gp.confirm(session_id, code)

    pool = _make_pool(pairing=gp)
    result = pool.submit_sync(session_id, "hello")
    assert result == "response"


def test_revoked_identity_blocked():
    """After revoking a paired identity, it is blocked again."""
    gp = GatewayPairing()
    code = gp.initiate("slack", "slack:user1")
    gp.confirm("slack:user1", code)

    pool = _make_pool(pairing=gp)
    assert pool.submit_sync("slack:user1", "hello") == "response"

    gp.revoke("slack:user1")
    assert pool.submit_sync("slack:user1", "hello again") == PAIRING_PROMPT


@pytest.mark.asyncio
async def test_async_submit_respects_pairing():
    """Async submit also enforces pairing."""
    gp = GatewayPairing()
    pool = _make_pool(pairing=gp)
    result = await pool.submit("telegram:user1", "hello")
    assert result == PAIRING_PROMPT
