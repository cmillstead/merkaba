# tests/test_dead_letter_queue.py
import tempfile
import os

import pytest

from merkaba.orchestration.queue import TaskQueue


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmp:
        q = TaskQueue(db_path=os.path.join(tmp, "test.db"))
        yield q
        q.close()


def test_dead_letter_table_created(queue):
    cursor = queue._conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dead_letter_queue'")
    assert cursor.fetchone() is not None


def test_task_runs_has_failure_count_column(queue):
    cursor = queue._conn.cursor()
    cursor.execute("PRAGMA table_info(task_runs)")
    columns = [row[1] for row in cursor.fetchall()]
    assert "failure_count" in columns
    assert "last_error" in columns


def test_record_failure_under_threshold(queue):
    task_id = queue.add_task("test-task", "health_check")
    # Create failures under threshold (MAX_TASK_FAILURES = 3)
    run_id = queue.start_run(task_id)
    queue.finish_run(run_id, "failed", error="oops")

    task = queue.get_task(task_id)
    assert task["status"] == "failed"
    assert queue.list_dead_letters() == []


def test_record_failure_moves_to_dlq_after_threshold(queue):
    task_id = queue.add_task("test-task", "health_check")

    # Fail MAX_TASK_FAILURES times
    for i in range(TaskQueue.MAX_TASK_FAILURES):
        run_id = queue.start_run(task_id)
        queue.finish_run(run_id, "failed", error=f"error {i}")

    task = queue.get_task(task_id)
    assert task["status"] == "dead_letter"

    dlq = queue.list_dead_letters()
    assert len(dlq) == 1
    assert dlq[0]["task_id"] == task_id
    assert dlq[0]["failure_count"] == TaskQueue.MAX_TASK_FAILURES


def test_resolve_dead_letter(queue):
    task_id = queue.add_task("test-task", "health_check")
    for i in range(TaskQueue.MAX_TASK_FAILURES):
        run_id = queue.start_run(task_id)
        queue.finish_run(run_id, "failed", error=f"error {i}")

    dlq = queue.list_dead_letters()
    assert len(dlq) == 1

    queue.resolve_dead_letter(dlq[0]["id"], notes="manually fixed")

    assert queue.list_dead_letters(resolved=False) == []
    resolved = queue.list_dead_letters(resolved=True)
    assert len(resolved) == 1
    assert resolved[0]["resolution_notes"] == "manually fixed"


def test_list_dead_letters_empty_by_default(queue):
    assert queue.list_dead_letters() == []
