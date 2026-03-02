# tests/test_lane_queue.py
import threading
import time

from merkaba.orchestration.lane_queue import LaneQueue


def test_serial_execution_same_session():
    """Messages for the same session execute serially, not overlapping."""
    lane = LaneQueue()
    execution_log = []

    def slow_handler(msg):
        execution_log.append(f"start:{msg}")
        time.sleep(0.1)
        execution_log.append(f"end:{msg}")
        return msg

    threads = []
    for i in range(3):
        t = threading.Thread(target=lane.submit_sync, args=("sess1", slow_handler, f"msg{i}"))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify serial: each "end" comes before the next "start"
    starts = [i for i, x in enumerate(execution_log) if x.startswith("start:")]
    ends = [i for i, x in enumerate(execution_log) if x.startswith("end:")]
    for s, e in zip(starts[1:], ends[:-1]):
        assert s > e, f"Overlapping execution detected: {execution_log}"


def test_concurrent_different_sessions():
    """Different sessions can execute concurrently."""
    lane = LaneQueue()
    start_times = {}

    def handler(msg):
        start_times[msg] = time.time()
        time.sleep(0.1)
        return msg

    t1 = threading.Thread(target=lane.submit_sync, args=("sess1", handler, "a"))
    t2 = threading.Thread(target=lane.submit_sync, args=("sess2", handler, "b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Both started within 50ms of each other (concurrent)
    assert abs(start_times["a"] - start_times["b"]) < 0.05


def test_is_busy():
    lane = LaneQueue()
    busy_during = []

    def handler(msg):
        busy_during.append(lane.is_busy("sess1"))
        time.sleep(0.05)
        return msg

    lane.submit_sync("sess1", handler, "test")
    assert busy_during == [True]
    assert not lane.is_busy("sess1")


def test_exception_doesnt_block_queue():
    lane = LaneQueue()

    def failing_handler(msg):
        raise ValueError("boom")

    def ok_handler(msg):
        return "ok"

    try:
        lane.submit_sync("sess1", failing_handler, "bad")
    except ValueError:
        pass

    result = lane.submit_sync("sess1", ok_handler, "good")
    assert result == "ok"


def test_remove_session():
    lane = LaneQueue()
    lane.submit_sync("sess1", lambda x: x, "test")
    assert "sess1" in lane._locks
    lane.remove_session("sess1")
    assert "sess1" not in lane._locks


def test_active_session_count():
    lane = LaneQueue()
    assert lane.active_session_count() == 0

    entered = threading.Event()
    entered2 = threading.Event()
    release = threading.Event()

    def handler1(msg):
        entered.set()
        release.wait(timeout=2)
        return msg

    def handler2(msg):
        entered2.set()
        release.wait(timeout=2)
        return msg

    t1 = threading.Thread(target=lane.submit_sync, args=("s1", handler1, "a"))
    t2 = threading.Thread(target=lane.submit_sync, args=("s2", handler2, "b"))
    t1.start()
    t2.start()
    entered.wait(timeout=2)
    entered2.wait(timeout=2)
    assert lane.active_session_count() == 2
    release.set()
    t1.join()
    t2.join()
