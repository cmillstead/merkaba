"""Tests for the LLMGate priority-aware concurrency gate."""

import logging
import threading
import time

import pytest

from merkaba.llm import GateConfig, LLMGate, RequestPriority


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gate(**kwargs) -> LLMGate:
    """Create an isolated LLMGate (not the global singleton)."""
    return LLMGate(config=GateConfig(**kwargs))


# ---------------------------------------------------------------------------
# 1. Priority ordering
# ---------------------------------------------------------------------------


def test_priority_ordering_interactive_before_background():
    """INTERACTIVE (0) requests are dispatched before BACKGROUND (3)."""
    gate = _make_gate(max_concurrent=1)

    dispatch_order: list[str] = []
    barrier = threading.Barrier(3)  # 1 holder + 2 waiters

    def holder():
        """Acquires the sole slot and holds it until the two waiters are queued."""
        gate.acquire(RequestPriority.SCHEDULED)
        barrier.wait(timeout=5)
        # Give the two waiters time to enqueue
        time.sleep(0.1)
        gate.release()

    def waiter(priority: RequestPriority, label: str):
        """Waits for a slot, records when it is dispatched."""
        barrier.wait(timeout=5)
        gate.acquire(priority)
        dispatch_order.append(label)
        gate.release()

    threads = [
        threading.Thread(target=holder),
        threading.Thread(target=waiter, args=(RequestPriority.BACKGROUND, "bg")),
        threading.Thread(target=waiter, args=(RequestPriority.INTERACTIVE, "interactive")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert dispatch_order == ["interactive", "bg"]


def test_priority_ordering_all_four_levels():
    """All four priority levels are dispatched in correct order."""
    gate = _make_gate(max_concurrent=1)

    dispatch_order: list[str] = []
    ready_event = threading.Event()

    def holder():
        gate.acquire(RequestPriority.SCHEDULED)
        ready_event.set()
        # Wait until all waiters are queued
        time.sleep(0.2)
        gate.release()

    def waiter(priority: RequestPriority, label: str):
        ready_event.wait(timeout=5)
        # Small stagger so they all see the gate as full
        time.sleep(0.05)
        gate.acquire(priority)
        dispatch_order.append(label)
        gate.release()

    holder_t = threading.Thread(target=holder)
    holder_t.start()

    waiters = [
        (RequestPriority.BACKGROUND, "bg"),
        (RequestPriority.SCHEDULED, "sched"),
        (RequestPriority.APPROVAL, "approval"),
        (RequestPriority.INTERACTIVE, "interactive"),
    ]
    threads = []
    for pri, label in waiters:
        t = threading.Thread(target=waiter, args=(pri, label))
        threads.append(t)
        t.start()

    holder_t.join(timeout=5)
    for t in threads:
        t.join(timeout=5)

    assert dispatch_order == ["interactive", "approval", "sched", "bg"]


def test_fifo_within_same_priority():
    """Requests at the same priority level are dispatched FIFO (by counter)."""
    gate = _make_gate(max_concurrent=1)

    dispatch_order: list[int] = []
    ready_event = threading.Event()

    def holder():
        gate.acquire(RequestPriority.INTERACTIVE)
        ready_event.set()
        time.sleep(0.2)
        gate.release()

    def waiter(index: int):
        ready_event.wait(timeout=5)
        # Stagger slightly so they queue in order
        time.sleep(0.02 * index)
        gate.acquire(RequestPriority.BACKGROUND)
        dispatch_order.append(index)
        gate.release()

    holder_t = threading.Thread(target=holder)
    holder_t.start()

    threads = []
    for i in range(4):
        t = threading.Thread(target=waiter, args=(i,))
        threads.append(t)
        t.start()

    holder_t.join(timeout=5)
    for t in threads:
        t.join(timeout=5)

    assert dispatch_order == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# 2. Concurrent access
# ---------------------------------------------------------------------------


def test_concurrent_two_proceed_third_blocks():
    """With max_concurrent=2, two requests proceed; third must wait."""
    gate = _make_gate(max_concurrent=2)

    inside = threading.Event()
    second_inside = threading.Event()
    third_started = threading.Event()
    third_acquired = threading.Event()

    def slot_holder(event_to_set):
        gate.acquire(RequestPriority.INTERACTIVE)
        event_to_set.set()
        # Hold slot until third_acquired is set or timeout
        third_acquired.wait(timeout=2)
        gate.release()

    def third_requester():
        third_started.set()
        gate.acquire(RequestPriority.INTERACTIVE)
        third_acquired.set()
        gate.release()

    t1 = threading.Thread(target=slot_holder, args=(inside,))
    t2 = threading.Thread(target=slot_holder, args=(second_inside,))
    t1.start()
    t2.start()

    inside.wait(timeout=2)
    second_inside.wait(timeout=2)

    # Both slots are occupied, active_count should be 2
    assert gate.active_count == 2

    t3 = threading.Thread(target=third_requester)
    t3.start()
    third_started.wait(timeout=2)
    time.sleep(0.1)

    # Third should be queued, not yet acquired
    assert gate.queue_depth == 1
    assert not third_acquired.is_set()

    # Release one slot by signaling holders to stop
    third_acquired.wait(timeout=3)

    t1.join(timeout=3)
    t2.join(timeout=3)
    t3.join(timeout=3)


# ---------------------------------------------------------------------------
# 3. Queue depth warning
# ---------------------------------------------------------------------------


def test_queue_depth_warning_logged(caplog):
    """When queue depth exceeds queue_depth_warning, a warning is logged."""
    gate = _make_gate(max_concurrent=1, queue_depth_warning=2)

    # Fill the one slot
    gate.acquire(RequestPriority.INTERACTIVE)

    events: list[threading.Event] = []

    def waiter():
        gate.acquire(RequestPriority.BACKGROUND)
        gate.release()

    # Queue 3 requests (exceeding warning threshold of 2)
    threads = []
    for _ in range(3):
        t = threading.Thread(target=waiter)
        threads.append(t)

    with caplog.at_level(logging.WARNING, logger="merkaba.llm"):
        for t in threads:
            t.start()

        # Wait for threads to queue up
        time.sleep(0.2)

        # Release the gate so everything finishes
        gate.release()

        for t in threads:
            t.join(timeout=5)

    # At least one warning about queue depth
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("queue depth" in msg.lower() for msg in warning_messages)


def test_no_warning_below_threshold(caplog):
    """No warning when queue depth is at or below queue_depth_warning."""
    gate = _make_gate(max_concurrent=1, queue_depth_warning=5)

    gate.acquire(RequestPriority.INTERACTIVE)

    def waiter():
        gate.acquire(RequestPriority.BACKGROUND)
        gate.release()

    # Queue only 2 requests (well below threshold of 5)
    threads = []
    for _ in range(2):
        t = threading.Thread(target=waiter)
        threads.append(t)

    with caplog.at_level(logging.WARNING, logger="merkaba.llm"):
        for t in threads:
            t.start()
        time.sleep(0.1)
        gate.release()
        for t in threads:
            t.join(timeout=5)

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("queue depth" in msg.lower() for msg in warning_messages)


# ---------------------------------------------------------------------------
# 4. Acquire/release cycle
# ---------------------------------------------------------------------------


def test_basic_acquire_release():
    """Basic acquire and release cycle works correctly."""
    gate = _make_gate(max_concurrent=2)

    assert gate.active_count == 0
    assert gate.queue_depth == 0

    gate.acquire(RequestPriority.INTERACTIVE)
    assert gate.active_count == 1

    gate.acquire(RequestPriority.SCHEDULED)
    assert gate.active_count == 2

    gate.release()
    assert gate.active_count == 1

    gate.release()
    assert gate.active_count == 0


def test_active_count_tracks_correctly_through_lifecycle():
    """active_count increments on acquire and decrements on release."""
    gate = _make_gate(max_concurrent=5)

    for i in range(5):
        gate.acquire(RequestPriority.SCHEDULED)
        assert gate.active_count == i + 1

    for i in range(5):
        gate.release()
        assert gate.active_count == 4 - i


# ---------------------------------------------------------------------------
# 5. Disabled gate
# ---------------------------------------------------------------------------


def test_disabled_gate_acquire_is_noop():
    """When gate.enabled = False, acquire returns immediately without blocking."""
    gate = _make_gate(max_concurrent=1)
    gate.enabled = False

    # Should not block even though max_concurrent=1
    gate.acquire(RequestPriority.INTERACTIVE)
    gate.acquire(RequestPriority.INTERACTIVE)
    gate.acquire(RequestPriority.INTERACTIVE)

    # active_count should remain 0 (no tracking when disabled)
    assert gate.active_count == 0
    assert gate.queue_depth == 0


def test_disabled_gate_release_is_noop():
    """When gate.enabled = False, release does nothing."""
    gate = _make_gate(max_concurrent=1)
    gate.enabled = False

    # Should not decrement active_count below 0
    gate.release()
    gate.release()
    assert gate.active_count == 0


def test_disable_mid_session():
    """Disabling the gate after some acquires still allows release to be noop."""
    gate = _make_gate(max_concurrent=2)
    gate.acquire(RequestPriority.INTERACTIVE)
    assert gate.active_count == 1

    gate.enabled = False

    # Release is now a no-op (active_count stays at 1 from the earlier acquire)
    gate.release()
    assert gate.active_count == 1

    # Acquire is also a no-op
    gate.acquire(RequestPriority.BACKGROUND)
    assert gate.active_count == 1


# ---------------------------------------------------------------------------
# 6. Reset
# ---------------------------------------------------------------------------


def test_reset_clears_all_state():
    """reset() clears queue, counter, and active count."""
    gate = _make_gate(max_concurrent=2)

    gate.acquire(RequestPriority.INTERACTIVE)
    gate.acquire(RequestPriority.SCHEDULED)
    assert gate.active_count == 2

    gate.reset()

    assert gate.active_count == 0
    assert gate.queue_depth == 0
    assert gate._counter == 0


def test_reset_allows_reuse():
    """After reset, the gate can be used normally again."""
    gate = _make_gate(max_concurrent=1)

    gate.acquire(RequestPriority.INTERACTIVE)
    assert gate.active_count == 1

    gate.reset()
    assert gate.active_count == 0

    # Should be able to acquire again
    gate.acquire(RequestPriority.SCHEDULED)
    assert gate.active_count == 1
    gate.release()
    assert gate.active_count == 0


# ---------------------------------------------------------------------------
# 7. Properties: queue_depth and active_count
# ---------------------------------------------------------------------------


def test_queue_depth_reflects_waiting_requests():
    """queue_depth returns the number of requests waiting in the queue."""
    gate = _make_gate(max_concurrent=1)

    # Fill the one slot
    gate.acquire(RequestPriority.INTERACTIVE)
    assert gate.queue_depth == 0

    finished = threading.Event()

    def waiter():
        gate.acquire(RequestPriority.BACKGROUND)
        finished.wait(timeout=5)
        gate.release()

    threads = []
    for _ in range(3):
        t = threading.Thread(target=waiter)
        threads.append(t)
        t.start()

    time.sleep(0.1)
    assert gate.queue_depth == 3

    # Release original holder, one waiter gets dispatched
    gate.release()
    time.sleep(0.1)
    assert gate.queue_depth == 2

    # Release second
    finished.set()
    for t in threads:
        t.join(timeout=5)

    assert gate.queue_depth == 0
    assert gate.active_count == 0


def test_active_count_reflects_running_requests():
    """active_count returns the number of requests currently holding a slot."""
    gate = _make_gate(max_concurrent=3)

    assert gate.active_count == 0
    gate.acquire(RequestPriority.INTERACTIVE)
    assert gate.active_count == 1
    gate.acquire(RequestPriority.APPROVAL)
    assert gate.active_count == 2
    gate.acquire(RequestPriority.SCHEDULED)
    assert gate.active_count == 3

    gate.release()
    assert gate.active_count == 2
    gate.release()
    assert gate.active_count == 1
    gate.release()
    assert gate.active_count == 0


# ---------------------------------------------------------------------------
# 8. Thread safety
# ---------------------------------------------------------------------------


def test_thread_safety_many_acquire_release():
    """Multiple threads can acquire/release without data corruption."""
    gate = _make_gate(max_concurrent=4)
    num_threads = 20
    iterations = 50
    errors: list[str] = []

    def worker():
        for _ in range(iterations):
            try:
                gate.acquire(RequestPriority.SCHEDULED)
                # Simulate brief work
                time.sleep(0.001)
                gate.release()
            except Exception as e:
                errors.append(str(e))

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"Thread safety errors: {errors}"
    assert gate.active_count == 0
    assert gate.queue_depth == 0


def test_thread_safety_mixed_priorities():
    """Threads with mixed priorities can acquire/release safely."""
    gate = _make_gate(max_concurrent=2)
    num_threads = 16
    completed = []
    lock = threading.Lock()

    priorities = list(RequestPriority)

    def worker(thread_id: int):
        pri = priorities[thread_id % len(priorities)]
        gate.acquire(pri)
        time.sleep(0.005)
        with lock:
            completed.append(thread_id)
        gate.release()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert len(completed) == num_threads
    assert gate.active_count == 0
    assert gate.queue_depth == 0


def test_thread_safety_active_count_never_negative():
    """active_count never goes negative under concurrent load."""
    gate = _make_gate(max_concurrent=3)
    min_observed = []
    lock = threading.Lock()

    def worker():
        gate.acquire(RequestPriority.SCHEDULED)
        count = gate.active_count
        with lock:
            min_observed.append(count)
        time.sleep(0.002)
        gate.release()
        count_after = gate.active_count
        with lock:
            min_observed.append(count_after)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert all(c >= 0 for c in min_observed), f"Negative active_count observed: {min(min_observed)}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_default_priority_is_scheduled():
    """acquire() without a priority argument defaults to SCHEDULED."""
    gate = _make_gate(max_concurrent=1)

    dispatch_order: list[str] = []
    ready = threading.Event()

    def holder():
        gate.acquire(RequestPriority.INTERACTIVE)
        ready.set()
        time.sleep(0.15)
        gate.release()

    def default_waiter():
        ready.wait(timeout=5)
        time.sleep(0.05)
        gate.acquire()  # default priority
        dispatch_order.append("default")
        gate.release()

    def interactive_waiter():
        ready.wait(timeout=5)
        time.sleep(0.05)
        gate.acquire(RequestPriority.INTERACTIVE)
        dispatch_order.append("interactive")
        gate.release()

    threads = [
        threading.Thread(target=holder),
        threading.Thread(target=default_waiter),
        threading.Thread(target=interactive_waiter),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # INTERACTIVE (0) should come before default SCHEDULED (2)
    assert dispatch_order == ["interactive", "default"]


def test_gate_config_defaults():
    """GateConfig has sensible defaults."""
    config = GateConfig()
    assert config.max_concurrent == 2
    assert config.queue_depth_warning == 5


def test_gate_custom_config():
    """LLMGate respects custom GateConfig."""
    config = GateConfig(max_concurrent=10, queue_depth_warning=20)
    gate = LLMGate(config=config)
    assert gate.config.max_concurrent == 10
    assert gate.config.queue_depth_warning == 20


def test_gate_default_config_when_none():
    """LLMGate uses default GateConfig when None is passed."""
    gate = LLMGate(config=None)
    assert gate.config.max_concurrent == 2
    assert gate.config.queue_depth_warning == 5
