# tests/test_rate_limiting.py
"""Tests for LLM rate limiting and resource management."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from merkaba.llm import (
    GateConfig,
    LLMClient,
    LLMGate,
    LLMResponse,
    LLMUnavailableError,
    RequestPriority,
    get_llm_gate,
)


# --- RequestPriority ---


def test_priority_ordering():
    """INTERACTIVE < APPROVAL < SCHEDULED < BACKGROUND."""
    assert RequestPriority.INTERACTIVE < RequestPriority.APPROVAL
    assert RequestPriority.APPROVAL < RequestPriority.SCHEDULED
    assert RequestPriority.SCHEDULED < RequestPriority.BACKGROUND


# --- GateConfig ---


def test_gate_config_defaults():
    config = GateConfig()
    assert config.max_concurrent == 2
    assert config.queue_depth_warning == 5


# --- LLMGate basic ---


def test_gate_acquire_release():
    """Basic acquire/release cycle works without deadlocking."""
    gate = LLMGate(config=GateConfig(max_concurrent=1))
    gate.acquire(RequestPriority.SCHEDULED)
    assert gate.active_count == 1
    gate.release()
    assert gate.active_count == 0


def test_gate_priority_ordering():
    """Higher-priority requests are dispatched before lower-priority ones."""
    gate = LLMGate(config=GateConfig(max_concurrent=1))

    # Fill the single slot
    gate.acquire(RequestPriority.SCHEDULED)

    dispatch_order = []

    def waiter(priority, label):
        gate.acquire(priority)
        dispatch_order.append(label)
        gate.release()

    # Queue a BACKGROUND and an INTERACTIVE request
    t_bg = threading.Thread(target=waiter, args=(RequestPriority.BACKGROUND, "bg"))
    t_interactive = threading.Thread(target=waiter, args=(RequestPriority.INTERACTIVE, "interactive"))

    t_bg.start()
    time.sleep(0.05)  # ensure bg is queued first
    t_interactive.start()
    time.sleep(0.05)  # ensure interactive is queued

    # Release the slot — interactive should be dispatched first
    gate.release()

    t_bg.join(timeout=2)
    t_interactive.join(timeout=2)

    assert dispatch_order[0] == "interactive"
    assert dispatch_order[1] == "bg"


def test_gate_fifo_within_same_priority():
    """Same-priority requests are served in FIFO order."""
    gate = LLMGate(config=GateConfig(max_concurrent=1))
    gate.acquire(RequestPriority.SCHEDULED)

    dispatch_order = []

    def waiter(label):
        gate.acquire(RequestPriority.SCHEDULED)
        dispatch_order.append(label)
        gate.release()

    t1 = threading.Thread(target=waiter, args=("first",))
    t2 = threading.Thread(target=waiter, args=("second",))

    t1.start()
    time.sleep(0.05)
    t2.start()
    time.sleep(0.05)

    gate.release()

    t1.join(timeout=2)
    t2.join(timeout=2)

    assert dispatch_order == ["first", "second"]


def test_gate_queue_depth_warning(caplog):
    """Warning is logged when queue depth exceeds threshold."""
    import logging
    gate = LLMGate(config=GateConfig(max_concurrent=1, queue_depth_warning=2))
    gate.acquire(RequestPriority.SCHEDULED)

    events = []

    def waiter():
        gate.acquire(RequestPriority.BACKGROUND)
        events.append("done")
        gate.release()

    threads = []
    for _ in range(3):
        t = threading.Thread(target=waiter)
        threads.append(t)
        t.start()
        time.sleep(0.02)

    with caplog.at_level(logging.WARNING, logger="merkaba.llm"):
        # The warning should already have been logged during acquire
        pass

    # Release all
    gate.release()
    for t in threads:
        t.join(timeout=2)

    assert any("queue depth" in r.message.lower() for r in caplog.records)


def test_gate_disabled_mode():
    """When disabled, acquire/release are no-ops."""
    gate = LLMGate(config=GateConfig(max_concurrent=1))
    gate.enabled = False
    # Should not block even though max_concurrent=1
    gate.acquire(RequestPriority.SCHEDULED)
    gate.acquire(RequestPriority.SCHEDULED)
    gate.release()
    gate.release()
    # active_count stays 0 since acquire is a no-op
    assert gate.active_count == 0


def test_gate_reset():
    """Reset clears all state."""
    gate = LLMGate(config=GateConfig(max_concurrent=2))
    gate.acquire(RequestPriority.SCHEDULED)
    assert gate.active_count == 1
    gate.reset()
    assert gate.active_count == 0
    assert gate.queue_depth == 0


# --- Integration with chat_with_retry ---


def test_chat_with_retry_acquires_gate(mock_ollama, make_llm_response):
    """chat_with_retry should acquire and release the gate."""
    gate = get_llm_gate()
    gate.enabled = True  # override autouse fixture
    gate.reset()

    mock_ollama.RequestError = type("RequestError", (Exception,), {})
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})

    mock_response = MagicMock()
    mock_response.message.content = "hello"
    mock_response.message.tool_calls = None
    mock_response.model = "test"
    mock_response.prompt_eval_count = 0
    mock_response.eval_count = 0
    mock_response.total_duration = 0

    client = LLMClient(model="test")
    client._client = MagicMock()
    client._client.chat.return_value = mock_response

    result = client.chat_with_retry(message="test", priority=RequestPriority.INTERACTIVE)
    assert result.content == "hello"
    # Gate should be released after call
    assert gate.active_count == 0

    gate.enabled = False  # restore


def test_gate_released_on_exception(mock_ollama):
    """Gate is released even when chat_with_retry raises."""
    gate = get_llm_gate()
    gate.enabled = True
    gate.reset()

    mock_ollama.RequestError = type("RequestError", (Exception,), {})
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})

    client = LLMClient(model="test")
    client._client = MagicMock()
    client._client.chat.side_effect = ConnectionError("fail")

    from merkaba.llm import RetryConfig
    with pytest.raises(LLMUnavailableError):
        client.chat_with_retry(
            message="test",
            retry_config=RetryConfig(max_retries=0, base_delay=0),
            priority=RequestPriority.SCHEDULED,
        )

    assert gate.active_count == 0
    gate.enabled = False


def test_chat_with_fallback_passes_priority(mock_ollama, make_llm_response):
    """chat_with_fallback passes priority through to chat_with_retry."""
    mock_ollama.RequestError = type("RequestError", (Exception,), {})
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})

    client = LLMClient(model="test")

    with patch.object(client, "chat_with_retry") as mock_retry:
        mock_retry.return_value = make_llm_response("ok")

        client.chat_with_fallback(
            message="test",
            tier="complex",
            priority=RequestPriority.INTERACTIVE,
        )

        call_kwargs = mock_retry.call_args.kwargs
        assert call_kwargs["priority"] == RequestPriority.INTERACTIVE


def test_default_priority_is_scheduled(mock_ollama, make_llm_response):
    """Default priority for chat_with_fallback is SCHEDULED."""
    mock_ollama.RequestError = type("RequestError", (Exception,), {})
    mock_ollama.ResponseError = type("ResponseError", (Exception,), {})

    client = LLMClient(model="test")

    with patch.object(client, "chat_with_retry") as mock_retry:
        mock_retry.return_value = make_llm_response("ok")

        client.chat_with_fallback(message="test", tier="complex")

        call_kwargs = mock_retry.call_args.kwargs
        assert call_kwargs["priority"] == RequestPriority.SCHEDULED


# --- Concurrent stress test ---


def test_concurrent_no_deadlock():
    """5 threads using the gate concurrently should complete without deadlocks."""
    gate = LLMGate(config=GateConfig(max_concurrent=2))
    results = []

    def worker(idx):
        gate.acquire(RequestPriority(idx % 4))
        time.sleep(0.01)
        results.append(idx)
        gate.release()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert len(results) == 5
    assert gate.active_count == 0
