# tests/e2e/test_e2e_scheduler.py
"""End-to-end tests for scheduler dispatch and execution CLI commands.

Uses real SQLite databases (in temp dirs) and real CLI invocations.
Only the LLM layer is mocked (via global conftest).
Supervisor.handle_task is mocked to avoid LLM dependency in scheduler tests.
"""

import datetime
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. No due tasks
# ---------------------------------------------------------------------------

def test_scheduler_run_no_due_tasks(cli_runner):
    """Empty database should print 'No due tasks'."""
    runner, app = cli_runner

    result = runner.invoke(app, ["scheduler", "run"])
    assert result.exit_code == 0
    assert "No due tasks" in result.output


# ---------------------------------------------------------------------------
# 2. Run with a single due task
# ---------------------------------------------------------------------------

def test_scheduler_run_with_due_task(cli_runner, patched_dbs):
    """Add a task, set next_run to the past, run scheduler tick.

    Supervisor.handle_task is mocked so no LLM calls are made.
    Expects 'Processed 1 due tasks' in output.
    """
    runner, app = cli_runner

    # Add a scheduled task via CLI
    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Health Ping",
        "--type", "health_check",
        "--schedule", "0 * * * *",
    ])
    assert result.exit_code == 0

    # Set next_run to one hour in the past so the scheduler considers it due
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    past = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
    queue._conn.execute("UPDATE tasks SET next_run = ? WHERE id = 1", (past,))
    queue._conn.commit()
    queue.close()

    # Mock Supervisor.handle_task to avoid LLM calls
    with patch("merkaba.orchestration.supervisor.Supervisor.handle_task") as mock_handle:
        mock_handle.return_value = {"status": "success", "result": "ok"}
        result = runner.invoke(app, ["scheduler", "run"])

    assert result.exit_code == 0
    assert "Processed 1 due tasks" in result.output
    assert "Health Ping" in result.output


# ---------------------------------------------------------------------------
# 3. Workers list
# ---------------------------------------------------------------------------

def test_scheduler_workers_list(cli_runner):
    """Verify 'scheduler workers' outputs registered worker names."""
    runner, app = cli_runner

    result = runner.invoke(app, ["scheduler", "workers"])
    assert result.exit_code == 0
    # Built-in workers from merkaba.orchestration.workers
    assert "health_check" in result.output
    assert "HealthCheckWorker" in result.output
    assert "research" in result.output
    assert "ResearchWorker" in result.output


# ---------------------------------------------------------------------------
# 4. Multiple due tasks
# ---------------------------------------------------------------------------

def test_scheduler_run_multiple_due(cli_runner, patched_dbs):
    """Add two tasks with past next_run, verify 'Processed 2 due tasks'."""
    runner, app = cli_runner

    # Add two scheduled tasks
    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Task Alpha",
        "--type", "health_check",
        "--schedule", "0 * * * *",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Task Beta",
        "--type", "research",
        "--schedule", "30 * * * *",
    ])
    assert result.exit_code == 0

    # Set both tasks' next_run to the past
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    past = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
    queue._conn.execute("UPDATE tasks SET next_run = ?", (past,))
    queue._conn.commit()
    queue.close()

    # Mock Supervisor.handle_task to avoid LLM calls
    with patch("merkaba.orchestration.supervisor.Supervisor.handle_task") as mock_handle:
        mock_handle.return_value = {"status": "success", "result": "ok"}
        result = runner.invoke(app, ["scheduler", "run"])

    assert result.exit_code == 0
    assert "Processed 2 due tasks" in result.output
    assert "Task Alpha" in result.output
    assert "Task Beta" in result.output


# ---------------------------------------------------------------------------
# 5. Scheduler skips paused tasks
# ---------------------------------------------------------------------------

def test_scheduler_skips_paused_tasks(cli_runner, patched_dbs):
    """Add a task, pause it, set next_run to the past — scheduler should skip it."""
    runner, app = cli_runner

    # Add a scheduled task
    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Paused Job",
        "--type", "health_check",
        "--schedule", "0 * * * *",
    ])
    assert result.exit_code == 0

    # Extract the task ID
    output = result.output
    id_start = output.index("id=") + 3
    id_end = output.index(",", id_start)
    task_id = output[id_start:id_end].strip()

    # Pause the task
    result = runner.invoke(app, ["tasks", "pause", task_id])
    assert result.exit_code == 0
    assert "Paused" in result.output

    # Set next_run to the past (even though paused, the query filters by status)
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    past = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat()
    queue._conn.execute(
        "UPDATE tasks SET next_run = ? WHERE id = ?", (past, int(task_id))
    )
    queue._conn.commit()
    queue.close()

    # Scheduler tick should find no due tasks because the task is paused
    result = runner.invoke(app, ["scheduler", "run"])
    assert result.exit_code == 0
    assert "No due tasks" in result.output
