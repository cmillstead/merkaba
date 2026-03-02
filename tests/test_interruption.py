# tests/test_interruption.py
"""Tests for InterruptionManager — thread-safe mid-response interruption."""

from merkaba.orchestration.interruption import InterruptionManager, InterruptionMode


def test_append_mode_queues_message():
    mgr = InterruptionManager(default_mode=InterruptionMode.APPEND)
    mgr.interrupt("sess1", "correction")
    event = mgr.check("sess1")
    assert event is not None
    assert event.message == "correction"
    assert event.mode == InterruptionMode.APPEND


def test_no_interruption_when_empty():
    mgr = InterruptionManager()
    assert mgr.check("sess1") is None


def test_multiple_interruptions_in_order():
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "first")
    mgr.interrupt("sess1", "second")
    assert mgr.check("sess1").message == "first"
    assert mgr.check("sess1").message == "second"
    assert mgr.check("sess1") is None


def test_has_cancel():
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "stop", InterruptionMode.CANCEL)
    assert mgr.has_cancel("sess1")


def test_has_cancel_false_for_steer():
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "adjust", InterruptionMode.STEER)
    assert not mgr.has_cancel("sess1")


def test_clear_removes_all():
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "a")
    mgr.interrupt("sess1", "b")
    mgr.clear("sess1")
    assert mgr.check("sess1") is None


def test_sessions_are_independent():
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "for-1")
    mgr.interrupt("sess2", "for-2")
    assert mgr.check("sess1").message == "for-1"
    assert mgr.check("sess2").message == "for-2"


def test_thread_safety():
    """Interruptions set from async boundary, checked from sync agent loop."""
    import threading

    mgr = InterruptionManager()
    results = []

    def setter():
        mgr.interrupt("sess1", "from-thread", InterruptionMode.STEER)

    def checker():
        import time
        time.sleep(0.02)
        event = mgr.check("sess1")
        results.append(event)

    t1 = threading.Thread(target=setter)
    t2 = threading.Thread(target=checker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results[0] is not None
    assert results[0].mode == InterruptionMode.STEER


def test_steer_mode_explicit():
    """STEER mode can be set explicitly on interrupt."""
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "redirect", InterruptionMode.STEER)
    event = mgr.check("sess1")
    assert event.mode == InterruptionMode.STEER
    assert event.message == "redirect"
    assert event.session_id == "sess1"


def test_cancel_mode_explicit():
    """CANCEL mode can be set explicitly on interrupt."""
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "abort", InterruptionMode.CANCEL)
    event = mgr.check("sess1")
    assert event.mode == InterruptionMode.CANCEL


def test_has_cancel_not_consumed_by_peek():
    """has_cancel peeks but does not consume the event."""
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "stop", InterruptionMode.CANCEL)
    assert mgr.has_cancel("sess1")
    # Event should still be there for check()
    event = mgr.check("sess1")
    assert event is not None
    assert event.mode == InterruptionMode.CANCEL


def test_has_cancel_empty_session():
    """has_cancel returns False for unknown sessions."""
    mgr = InterruptionManager()
    assert not mgr.has_cancel("nonexistent")


def test_check_unknown_session():
    """check returns None for sessions with no interruptions."""
    mgr = InterruptionManager()
    assert mgr.check("never-seen") is None


def test_clear_unknown_session_no_error():
    """Clearing a non-existent session should not raise."""
    mgr = InterruptionManager()
    mgr.clear("nonexistent")  # should not raise


def test_default_mode_is_append():
    """Default mode should be APPEND when not specified."""
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "msg")
    event = mgr.check("sess1")
    assert event.mode == InterruptionMode.APPEND


def test_mixed_modes_in_queue():
    """Queue can hold events of different modes."""
    mgr = InterruptionManager()
    mgr.interrupt("sess1", "append-msg", InterruptionMode.APPEND)
    mgr.interrupt("sess1", "steer-msg", InterruptionMode.STEER)
    mgr.interrupt("sess1", "cancel-msg", InterruptionMode.CANCEL)

    e1 = mgr.check("sess1")
    e2 = mgr.check("sess1")
    e3 = mgr.check("sess1")

    assert e1.mode == InterruptionMode.APPEND
    assert e2.mode == InterruptionMode.STEER
    assert e3.mode == InterruptionMode.CANCEL
    assert mgr.check("sess1") is None
