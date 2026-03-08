# tests/test_timestamps.py
"""Verify all _now() helpers produce naive UTC ISO-8601 timestamps.

Timestamps are stored WITHOUT timezone suffix (+00:00) so that SQLite
string comparisons work correctly against existing naive records.
The actual time is still UTC — we just strip tzinfo before serializing.
"""

from datetime import datetime, timezone

import pytest


class TestMemoryStoreTimestamps:
    """MemoryStore._now() returns naive UTC ISO-8601 timestamps."""

    def test_now_returns_naive_utc(self, tmp_path):
        from merkaba.memory.store import MemoryStore

        db = str(tmp_path / "mem.db")
        store = MemoryStore(db_path=db)
        ts = store._now()
        assert "+00:00" not in ts, f"Timestamp should be naive (no tz suffix): {ts}"
        assert "T" in ts, f"Expected ISO-8601 format: {ts}"
        store.close()

    def test_now_is_parseable(self, tmp_path):
        from merkaba.memory.store import MemoryStore

        db = str(tmp_path / "mem.db")
        store = MemoryStore(db_path=db)
        ts = store._now()
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is None, "Timestamp should be naive (no tzinfo)"
        store.close()

    def test_now_close_to_actual_utc(self, tmp_path):
        from merkaba.memory.store import MemoryStore

        db = str(tmp_path / "mem.db")
        store = MemoryStore(db_path=db)
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        ts = store._now()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        parsed = datetime.fromisoformat(ts)
        assert before <= parsed <= after
        store.close()


class TestTaskQueueTimestamps:
    """TaskQueue._now() returns naive UTC ISO-8601 timestamps."""

    def test_now_returns_naive_utc(self, tmp_path):
        from merkaba.orchestration.queue import TaskQueue

        db = str(tmp_path / "tasks.db")
        tq = TaskQueue(db_path=db)
        ts = tq._now()
        assert "+00:00" not in ts, f"Timestamp should be naive: {ts}"
        tq.close()

    def test_now_is_parseable(self, tmp_path):
        from merkaba.orchestration.queue import TaskQueue

        db = str(tmp_path / "tasks.db")
        tq = TaskQueue(db_path=db)
        ts = tq._now()
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is None
        tq.close()


class TestActionQueueTimestamps:
    """ActionQueue._now() returns naive UTC ISO-8601 timestamps."""

    def test_now_returns_naive_utc(self, tmp_path):
        from merkaba.approval.queue import ActionQueue

        db = str(tmp_path / "actions.db")
        aq = ActionQueue(db_path=db)
        ts = aq._now()
        assert "+00:00" not in ts, f"Timestamp should be naive: {ts}"
        aq.close()

    def test_now_is_parseable(self, tmp_path):
        from merkaba.approval.queue import ActionQueue

        db = str(tmp_path / "actions.db")
        aq = ActionQueue(db_path=db)
        ts = aq._now()
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is None
        aq.close()


class TestTimestampComparisons:
    """Naive UTC timestamps sort correctly and can be compared."""

    def test_timestamps_sort_chronologically(self, tmp_path):
        """Timestamps generated sequentially must sort in order."""
        from merkaba.memory.store import MemoryStore

        db = str(tmp_path / "mem.db")
        store = MemoryStore(db_path=db)
        ts1 = store._now()
        ts2 = store._now()
        assert ts1 <= ts2
        store.close()

    def test_naive_timestamps_comparable_with_naive_datetime(self, tmp_path):
        """Stored timestamps can be compared against fresh naive UTC datetimes."""
        from merkaba.memory.store import MemoryStore

        db = str(tmp_path / "mem.db")
        store = MemoryStore(db_path=db)
        ts = store._now()
        parsed = datetime.fromisoformat(ts)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        diff = abs((now - parsed).total_seconds())
        assert diff < 1.0, f"Timestamp drift too large: {diff}s"
        store.close()

    def test_all_three_queues_produce_consistent_format(self, tmp_path):
        """All three _now() implementations produce the same naive format."""
        from merkaba.memory.store import MemoryStore
        from merkaba.orchestration.queue import TaskQueue
        from merkaba.approval.queue import ActionQueue

        mem = MemoryStore(db_path=str(tmp_path / "mem.db"))
        tq = TaskQueue(db_path=str(tmp_path / "tasks.db"))
        aq = ActionQueue(db_path=str(tmp_path / "actions.db"))

        ts_mem = mem._now()
        ts_tq = tq._now()
        ts_aq = aq._now()

        for label, ts in [("MemoryStore", ts_mem), ("TaskQueue", ts_tq), ("ActionQueue", ts_aq)]:
            assert "+00:00" not in ts, f"{label}._now() should not have tz suffix: {ts}"
            parsed = datetime.fromisoformat(ts)
            assert parsed.tzinfo is None, f"{label}._now() should be naive"

        mem.close()
        tq.close()
        aq.close()
