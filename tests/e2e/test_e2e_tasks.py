# tests/e2e/test_e2e_tasks.py
"""End-to-end tests for task queue lifecycle CLI commands.

Uses real SQLite databases (in temp dirs) and real CLI invocations.
Only the LLM layer is mocked (via global conftest).
"""

import pytest

pytestmark = [pytest.mark.e2e]


# ---------------------------------------------------------------------------
# 1. List empty
# ---------------------------------------------------------------------------

def test_tasks_list_empty(cli_runner):
    """Fresh database should show 'No tasks found'."""
    runner, app = cli_runner

    result = runner.invoke(app, ["tasks", "list"])
    assert result.exit_code == 0
    assert "No tasks found" in result.output


# ---------------------------------------------------------------------------
# 2. Add basic task
# ---------------------------------------------------------------------------

def test_tasks_add_basic(cli_runner):
    """Add a task and verify 'Task created' appears in output."""
    runner, app = cli_runner

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Daily Report",
        "--type", "report",
    ])
    assert result.exit_code == 0
    assert "Task created" in result.output
    assert "Daily Report" in result.output


# ---------------------------------------------------------------------------
# 3. Add with schedule
# ---------------------------------------------------------------------------

def test_tasks_add_with_schedule(cli_runner):
    """Add a task with a cron schedule and verify schedule in output."""
    runner, app = cli_runner

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Morning Sync",
        "--type", "sync",
        "--schedule", "0 9 * * *",
    ])
    assert result.exit_code == 0
    assert "Task created" in result.output
    assert "0 9 * * *" in result.output


# ---------------------------------------------------------------------------
# 4. Add then list
# ---------------------------------------------------------------------------

def test_tasks_add_then_list(cli_runner):
    """Add a task, then list — the task name should appear."""
    runner, app = cli_runner

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Inventory Check",
        "--type", "inventory",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, ["tasks", "list"])
    assert result.exit_code == 0
    assert "Inventory Check" in result.output


# ---------------------------------------------------------------------------
# 5. Pause and resume
# ---------------------------------------------------------------------------

def test_tasks_pause_and_resume(cli_runner):
    """Add a task, pause it, then resume it — verify both transitions."""
    runner, app = cli_runner

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Price Monitor",
        "--type", "monitor",
    ])
    assert result.exit_code == 0

    # Extract the task ID from "Task created: id=X, name=..."
    output = result.output
    id_start = output.index("id=") + 3
    id_end = output.index(",", id_start)
    task_id = output[id_start:id_end].strip()

    # Pause
    result = runner.invoke(app, ["tasks", "pause", task_id])
    assert result.exit_code == 0
    assert "Paused" in result.output
    assert "Price Monitor" in result.output

    # Resume
    result = runner.invoke(app, ["tasks", "resume", task_id])
    assert result.exit_code == 0
    assert "Resumed" in result.output
    assert "Price Monitor" in result.output


# ---------------------------------------------------------------------------
# 6. Pause not found
# ---------------------------------------------------------------------------

def test_tasks_pause_not_found(cli_runner):
    """Pausing a non-existent task should exit with code 1."""
    runner, app = cli_runner

    result = runner.invoke(app, ["tasks", "pause", "999"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# 7. Runs empty
# ---------------------------------------------------------------------------

def test_tasks_runs_empty(cli_runner):
    """Add a task, check its runs — should show 'No runs' or empty."""
    runner, app = cli_runner

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Data Export",
        "--type", "export",
    ])
    assert result.exit_code == 0

    output = result.output
    id_start = output.index("id=") + 3
    id_end = output.index(",", id_start)
    task_id = output[id_start:id_end].strip()

    result = runner.invoke(app, ["tasks", "runs", task_id])
    assert result.exit_code == 0
    assert "No runs" in result.output


# ---------------------------------------------------------------------------
# 8. List filter by status
# ---------------------------------------------------------------------------

def test_tasks_list_filter_by_status(cli_runner):
    """Add two tasks, pause one, list --status paused shows only the paused one."""
    runner, app = cli_runner

    # Add two tasks
    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Active Task",
        "--type", "worker",
    ])
    assert result.exit_code == 0

    result = runner.invoke(app, [
        "tasks", "add",
        "--name", "Paused Task",
        "--type", "worker",
    ])
    assert result.exit_code == 0
    output = result.output
    id_start = output.index("id=") + 3
    id_end = output.index(",", id_start)
    paused_task_id = output[id_start:id_end].strip()

    # Pause the second task
    result = runner.invoke(app, ["tasks", "pause", paused_task_id])
    assert result.exit_code == 0

    # List with --status paused
    result = runner.invoke(app, ["tasks", "list", "--status", "paused"])
    assert result.exit_code == 0
    assert "Paused Task" in result.output
    assert "Active Task" not in result.output
