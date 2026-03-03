# tests/test_task_queue.py
import tempfile
import os
from datetime import datetime, timedelta

import pytest
from merkaba.orchestration.queue import TaskQueue


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tasks.db")
        q = TaskQueue(db_path=db_path)
        yield q
        q.close()


# --- Connection pragmas ---


def test_wal_journal_mode(queue):
    """TaskQueue should enable WAL journal mode for better concurrent read performance."""
    cursor = queue._conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode == "wal"


# --- Task CRUD ---


def test_add_task(queue):
    task_id = queue.add_task("Test Task", "check")
    assert task_id == 1


def test_add_task_with_schedule(queue):
    task_id = queue.add_task("Cron Task", "check", schedule="*/5 * * * *")
    task = queue.get_task(task_id)
    assert task["schedule"] == "*/5 * * * *"
    assert task["next_run"] is not None


def test_add_task_with_payload(queue):
    payload = {"url": "https://example.com", "method": "GET"}
    task_id = queue.add_task("API Task", "http", payload=payload)
    task = queue.get_task(task_id)
    assert task["payload"] == payload


def test_get_task(queue):
    task_id = queue.add_task("Test Task", "check", autonomy_level=3)
    task = queue.get_task(task_id)
    assert task["name"] == "Test Task"
    assert task["task_type"] == "check"
    assert task["autonomy_level"] == 3
    assert task["status"] == "pending"


def test_get_task_not_found(queue):
    assert queue.get_task(999) is None


def test_list_tasks(queue):
    queue.add_task("Task A", "check")
    queue.add_task("Task B", "http")
    tasks = queue.list_tasks()
    assert len(tasks) == 2
    assert tasks[0]["name"] == "Task A"


def test_list_tasks_filter_status(queue):
    queue.add_task("Task A", "check")
    t2 = queue.add_task("Task B", "http")
    queue.pause_task(t2)

    pending = queue.list_tasks(status="pending")
    assert len(pending) == 1
    assert pending[0]["name"] == "Task A"

    paused = queue.list_tasks(status="paused")
    assert len(paused) == 1
    assert paused[0]["name"] == "Task B"


def test_list_tasks_filter_business(queue):
    queue.add_task("Task A", "check", business_id=1)
    queue.add_task("Task B", "check", business_id=2)

    biz1 = queue.list_tasks(business_id=1)
    assert len(biz1) == 1
    assert biz1[0]["name"] == "Task A"


def test_update_task(queue):
    task_id = queue.add_task("Old Name", "check")
    queue.update_task(task_id, name="New Name", autonomy_level=5)
    task = queue.get_task(task_id)
    assert task["name"] == "New Name"
    assert task["autonomy_level"] == 5


def test_update_task_payload(queue):
    task_id = queue.add_task("Task", "check")
    queue.update_task(task_id, payload={"key": "value"})
    task = queue.get_task(task_id)
    assert task["payload"] == {"key": "value"}


def test_pause_task(queue):
    task_id = queue.add_task("Task", "check")
    queue.pause_task(task_id)
    task = queue.get_task(task_id)
    assert task["status"] == "paused"


def test_resume_task(queue):
    task_id = queue.add_task("Task", "check", schedule="*/5 * * * *")
    queue.pause_task(task_id)
    queue.resume_task(task_id)
    task = queue.get_task(task_id)
    assert task["status"] == "pending"
    assert task["next_run"] is not None


def test_resume_task_without_schedule(queue):
    task_id = queue.add_task("Task", "check")
    queue.pause_task(task_id)
    queue.resume_task(task_id)
    task = queue.get_task(task_id)
    assert task["status"] == "pending"


# --- Due task detection ---


def test_get_due_tasks_none_due(queue):
    queue.add_task("Future Task", "check", schedule="0 0 1 1 *")  # Jan 1 midnight
    due = queue.get_due_tasks()
    assert len(due) == 0


def test_get_due_tasks_with_past_next_run(queue):
    task_id = queue.add_task("Task", "check", schedule="*/5 * * * *")
    # Manually set next_run to the past
    past = (datetime.now() - timedelta(minutes=10)).isoformat()
    queue.update_task(task_id, next_run=past)
    due = queue.get_due_tasks()
    assert len(due) == 1
    assert due[0]["id"] == task_id


def test_get_due_tasks_excludes_paused(queue):
    task_id = queue.add_task("Task", "check", schedule="*/5 * * * *")
    past = (datetime.now() - timedelta(minutes=10)).isoformat()
    queue.update_task(task_id, next_run=past)
    queue.pause_task(task_id)
    due = queue.get_due_tasks()
    assert len(due) == 0


def test_get_due_tasks_excludes_no_next_run(queue):
    queue.add_task("One-shot", "check")  # No schedule, no next_run
    due = queue.get_due_tasks()
    assert len(due) == 0


def test_compute_next_run(queue):
    task_id = queue.add_task("Task", "check", schedule="*/5 * * * *")
    next_run = queue.compute_next_run(task_id)
    assert next_run is not None
    task = queue.get_task(task_id)
    assert task["next_run"] == next_run
    assert task["last_run"] is not None


def test_compute_next_run_no_schedule(queue):
    task_id = queue.add_task("Task", "check")
    assert queue.compute_next_run(task_id) is None


# --- Run tracking ---


def test_start_run(queue):
    task_id = queue.add_task("Task", "check")
    run_id = queue.start_run(task_id)
    assert run_id == 1
    task = queue.get_task(task_id)
    assert task["status"] == "running"


def test_finish_run_success(queue):
    task_id = queue.add_task("Task", "check")
    run_id = queue.start_run(task_id)
    queue.finish_run(run_id, "success", result={"output": "done"})

    task = queue.get_task(task_id)
    assert task["status"] == "pending"

    runs = queue.get_runs(task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["result"] == {"output": "done"}
    assert runs[0]["finished_at"] is not None


def test_finish_run_failed(queue):
    task_id = queue.add_task("Task", "check")
    run_id = queue.start_run(task_id)
    queue.finish_run(run_id, "failed", error="Something broke")

    task = queue.get_task(task_id)
    assert task["status"] == "failed"

    runs = queue.get_runs(task_id)
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "Something broke"


def test_get_runs_empty(queue):
    task_id = queue.add_task("Task", "check")
    runs = queue.get_runs(task_id)
    assert runs == []


def test_multiple_runs(queue):
    task_id = queue.add_task("Task", "check")

    run1 = queue.start_run(task_id)
    queue.finish_run(run1, "success")

    run2 = queue.start_run(task_id)
    queue.finish_run(run2, "failed", error="Oops")

    runs = queue.get_runs(task_id)
    assert len(runs) == 2
    # Most recent first
    assert runs[0]["id"] == run2
    assert runs[1]["id"] == run1


# --- Stats ---


def test_stats(queue):
    queue.add_task("Task A", "check")
    queue.add_task("Task B", "http")
    t3 = queue.add_task("Task C", "check")
    queue.pause_task(t3)

    run_id = queue.start_run(1)
    queue.finish_run(run_id, "success")

    stats = queue.stats()
    assert stats["tasks"] == 3
    assert stats["task_runs"] == 1
    assert stats["tasks_pending"] == 2  # Task A (back to pending after run) + Task B
    assert stats["tasks_paused"] == 1


# --- Context manager ---


def test_context_manager_returns_self():
    """TaskQueue as context manager returns self."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tasks.db")
        with TaskQueue(db_path=db_path) as q:
            assert isinstance(q, TaskQueue)
            assert q._conn is not None


def test_context_manager_closes_connection():
    """TaskQueue connection is closed after exiting the with block."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tasks.db")
        with TaskQueue(db_path=db_path) as q:
            q.add_task("Test Task", "check")
        assert q._conn is None


def test_context_manager_closes_on_exception():
    """TaskQueue connection is closed even when an exception occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tasks.db")
        with pytest.raises(RuntimeError, match="boom"):
            with TaskQueue(db_path=db_path) as q:
                q.add_task("Test Task", "check")
                raise RuntimeError("boom")
        assert q._conn is None


# --- Transactional delete_task ---


def test_delete_task_is_transactional(queue):
    """M6: delete_task must be atomic — wrapped in BEGIN/ROLLBACK."""
    import inspect
    source = inspect.getsource(queue.delete_task)
    assert "BEGIN" in source
    assert "ROLLBACK" in source


def test_delete_task_removes_task_and_runs(queue):
    """M6: delete_task removes the task and its associated runs."""
    task_id = queue.add_task("Doomed Task", "check")
    run_id = queue.start_run(task_id)
    queue.finish_run(run_id, "success", result={"ok": True})

    assert queue.delete_task(task_id) is True
    assert queue.get_task(task_id) is None
    assert queue.get_runs(task_id) == []


def test_delete_task_returns_false_for_nonexistent(queue):
    """M6: delete_task returns False when no task exists with the given ID."""
    assert queue.delete_task(999) is False
