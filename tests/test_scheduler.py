# tests/test_scheduler.py
import tempfile
import os
from datetime import datetime, timedelta

import pytest
from merkaba.orchestration.queue import TaskQueue
from merkaba.orchestration.scheduler import Scheduler


@pytest.fixture
def queue():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "tasks.db")
        q = TaskQueue(db_path=db_path)
        yield q
        q.close()


@pytest.fixture
def scheduler(queue):
    return Scheduler(queue=queue)


def _make_due_task(queue, name="Test Task", task_type="check"):
    """Helper: create a task with next_run in the past so it's due."""
    task_id = queue.add_task(name, task_type, schedule="*/5 * * * *")
    past = (datetime.now() - timedelta(minutes=10)).isoformat()
    queue.update_task(task_id, next_run=past)
    return task_id


# --- tick() ---


def test_tick_no_due_tasks(scheduler):
    due = scheduler.tick()
    assert due == []


def test_tick_with_due_tasks(queue, scheduler):
    task_id = _make_due_task(queue)
    due = scheduler.tick()
    assert len(due) == 1
    assert due[0]["id"] == task_id

    # Task should have a run recorded
    runs = queue.get_runs(task_id)
    assert len(runs) == 1
    assert runs[0]["status"] == "success"


def test_tick_multiple_due_tasks(queue, scheduler):
    _make_due_task(queue, "Task A")
    _make_due_task(queue, "Task B")
    due = scheduler.tick()
    assert len(due) == 2


def test_tick_updates_next_run(queue, scheduler):
    task_id = _make_due_task(queue)
    old_next = queue.get_task(task_id)["next_run"]
    scheduler.tick()
    new_next = queue.get_task(task_id)["next_run"]
    assert new_next != old_next
    assert new_next > old_next


# --- Dispatch callback ---


def test_dispatch_callback_invoked(queue):
    callback_calls = []

    def my_callback(task):
        callback_calls.append(task)
        return {"handled": True}

    scheduler = Scheduler(queue=queue, on_task_due=my_callback)
    task_id = _make_due_task(queue)
    scheduler.tick()

    assert len(callback_calls) == 1
    assert callback_calls[0]["id"] == task_id

    runs = queue.get_runs(task_id)
    assert runs[0]["result"] == {"handled": True}


def test_dispatch_stub_when_no_callback(queue, scheduler):
    task_id = _make_due_task(queue)
    scheduler.tick()
    runs = queue.get_runs(task_id)
    assert runs[0]["status"] == "success"
    assert "stub" in runs[0]["result"]["status"]


# --- Error handling ---


def test_tick_handles_dispatch_error(queue):
    def failing_callback(task):
        raise RuntimeError("dispatch failed")

    scheduler = Scheduler(queue=queue, on_task_due=failing_callback)
    task_id = _make_due_task(queue)
    due = scheduler.tick()

    assert len(due) == 1
    runs = queue.get_runs(task_id)
    assert runs[0]["status"] == "failed"
    assert "dispatch failed" in runs[0]["error"]

    task = queue.get_task(task_id)
    assert task["status"] == "failed"


def test_tick_continues_after_error(queue):
    """If one task fails, the rest still run."""
    call_count = {"n": 0}

    def sometimes_fail(task):
        call_count["n"] += 1
        if task["name"] == "Fail":
            raise RuntimeError("nope")
        return {"ok": True}

    scheduler = Scheduler(queue=queue, on_task_due=sometimes_fail)
    _make_due_task(queue, "Fail")
    _make_due_task(queue, "Succeed")

    due = scheduler.tick()
    assert len(due) == 2
    assert call_count["n"] == 2

    # One success, one failure
    all_tasks = queue.list_tasks()
    statuses = {t["name"]: t["status"] for t in all_tasks}
    assert statuses["Fail"] == "failed"
    assert statuses["Succeed"] == "pending"  # back to pending after success
