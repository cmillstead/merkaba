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


# --- Database indexes ---


def test_task_queue_indexes_exist(queue):
    """TaskQueue should create indexes on commonly queried columns."""
    cursor = queue._conn.cursor()

    # Collect index names for the tasks table
    cursor.execute("PRAGMA index_list(tasks)")
    task_indexes = {row[1] for row in cursor.fetchall()}

    # Collect index names for the task_runs table
    cursor.execute("PRAGMA index_list(task_runs)")
    run_indexes = {row[1] for row in cursor.fetchall()}

    # Verify all expected indexes exist
    assert "idx_tasks_status_next_run" in task_indexes
    assert "idx_tasks_task_type" in task_indexes
    assert "idx_task_runs_task_id" in run_indexes
    assert "idx_task_runs_status" in run_indexes


def test_task_queue_index_columns(queue):
    """Indexes should cover the correct columns."""
    cursor = queue._conn.cursor()

    # idx_tasks_status_next_run should be a composite index on (status, next_run)
    cursor.execute("PRAGMA index_info(idx_tasks_status_next_run)")
    columns = [row[2] for row in cursor.fetchall()]
    assert columns == ["status", "next_run"]

    # idx_tasks_task_type should index task_type
    cursor.execute("PRAGMA index_info(idx_tasks_task_type)")
    columns = [row[2] for row in cursor.fetchall()]
    assert columns == ["task_type"]

    # idx_task_runs_task_id should index task_id
    cursor.execute("PRAGMA index_info(idx_task_runs_task_id)")
    columns = [row[2] for row in cursor.fetchall()]
    assert columns == ["task_id"]

    # idx_task_runs_status should index status
    cursor.execute("PRAGMA index_info(idx_task_runs_status)")
    columns = [row[2] for row in cursor.fetchall()]
    assert columns == ["status"]


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


# --- get_recent_runs ---


def test_get_recent_runs_empty(queue):
    """get_recent_runs() returns empty list when no runs exist."""
    result = queue.get_recent_runs()
    assert result == []


def test_get_recent_runs_returns_list(queue):
    """get_recent_runs() returns a list of dicts with expected keys."""
    task_id = queue.add_task("Test Task", "check")
    run_id = queue.start_run(task_id)
    queue.finish_run(run_id, "success", result={"ok": True})

    runs = queue.get_recent_runs()
    assert len(runs) == 1
    assert isinstance(runs[0], dict)
    assert runs[0]["task_id"] == task_id
    assert runs[0]["status"] == "success"
    # Should include joined columns from tasks table
    assert runs[0]["name"] == "Test Task"
    assert runs[0]["task_type"] == "check"


def test_get_recent_runs_with_status_filter(queue):
    """get_recent_runs(status=...) filters by run status."""
    task_id = queue.add_task("Multi Run", "check")

    run1 = queue.start_run(task_id)
    queue.finish_run(run1, "success")
    run2 = queue.start_run(task_id)
    queue.finish_run(run2, "failed", error="boom")

    success_runs = queue.get_recent_runs(status="success")
    assert len(success_runs) == 1
    assert success_runs[0]["status"] == "success"

    failed_runs = queue.get_recent_runs(status="failed")
    assert len(failed_runs) == 1
    assert failed_runs[0]["status"] == "failed"


def test_get_recent_runs_respects_limit(queue):
    """get_recent_runs() respects the limit parameter."""
    task_id = queue.add_task("Many Runs", "check")
    for _ in range(5):
        rid = queue.start_run(task_id)
        queue.finish_run(rid, "success")

    runs = queue.get_recent_runs(limit=2)
    assert len(runs) == 2


# --- get_runs_for_tasks ---


def test_get_runs_for_tasks_empty_input(queue):
    """get_runs_for_tasks() returns empty dict when given no task IDs."""
    result = queue.get_runs_for_tasks([])
    assert result == {}


def test_get_runs_for_tasks_returns_dict_keyed_by_task_id(queue):
    """get_runs_for_tasks() returns a dict mapping each task_id to its runs."""
    t1 = queue.add_task("Task A", "check")
    t2 = queue.add_task("Task B", "review")
    r1 = queue.start_run(t1)
    queue.finish_run(r1, "success")
    r2 = queue.start_run(t2)
    queue.finish_run(r2, "failed", error="boom")

    result = queue.get_runs_for_tasks([t1, t2])
    assert isinstance(result, dict)
    assert t1 in result
    assert t2 in result
    assert len(result[t1]) == 1
    assert result[t1][0]["status"] == "success"
    assert len(result[t2]) == 1
    assert result[t2][0]["status"] == "failed"


def test_get_runs_for_tasks_respects_limit_per_task(queue):
    """get_runs_for_tasks() caps runs per task to limit_per_task."""
    t1 = queue.add_task("Many", "check")
    for _ in range(8):
        rid = queue.start_run(t1)
        queue.finish_run(rid, "success")

    result = queue.get_runs_for_tasks([t1], limit_per_task=3)
    assert len(result[t1]) == 3


def test_get_runs_for_tasks_returns_most_recent_first(queue):
    """get_runs_for_tasks() returns runs ordered most recent first."""
    import time

    t1 = queue.add_task("Ordered", "check")
    for i in range(3):
        rid = queue.start_run(t1)
        queue.finish_run(rid, "success", result={"seq": i})

    result = queue.get_runs_for_tasks([t1])
    seqs = [r["result"]["seq"] for r in result[t1]]
    assert seqs == [2, 1, 0]


def test_get_runs_for_tasks_missing_task_returns_empty(queue):
    """get_runs_for_tasks() returns empty list for task IDs with no runs."""
    t1 = queue.add_task("No Runs", "check")
    result = queue.get_runs_for_tasks([t1])
    assert result[t1] == []


def test_get_runs_for_tasks_single_query(queue):
    """get_runs_for_tasks() uses a single query regardless of task count (no N+1)."""
    # Create 10 tasks with 3 runs each
    task_ids = []
    for i in range(10):
        tid = queue.add_task(f"Task {i}", "check")
        task_ids.append(tid)
        for _ in range(3):
            rid = queue.start_run(tid)
            queue.finish_run(rid, "success")

    # Use SQLite's trace callback to count SELECT queries
    select_queries = []

    def trace_callback(statement):
        if statement.strip().upper().startswith("SELECT"):
            select_queries.append(statement)

    queue._conn.set_trace_callback(trace_callback)
    try:
        result = queue.get_runs_for_tasks(task_ids, limit_per_task=5)
    finally:
        queue._conn.set_trace_callback(None)

    # Should issue exactly 1 SELECT query for any number of tasks
    assert len(select_queries) == 1, (
        f"Expected 1 SELECT query, got {len(select_queries)}: {select_queries}"
    )

    # Verify we got data for all tasks
    assert len(result) == 10
    for tid in task_ids:
        assert len(result[tid]) == 3


# --- count_by_status ---


def test_count_by_status_empty(queue):
    """count_by_status() returns empty dict when no tasks exist."""
    result = queue.count_by_status()
    assert result == {}


def test_count_by_status(queue):
    """count_by_status() returns correct counts grouped by status."""
    queue.add_task("Task A", "check")
    queue.add_task("Task B", "check")
    queue.add_task("Task C", "check")
    # Pause one
    tasks = queue.list_tasks()
    queue.pause_task(tasks[2]["id"])

    result = queue.count_by_status()
    assert isinstance(result, dict)
    assert result.get("pending") == 2
    assert result.get("paused") == 1
